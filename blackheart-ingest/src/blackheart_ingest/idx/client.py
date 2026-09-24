"""Polite HTTP client for the JSON endpoints behind idx.co.id.

The endpoints are the ones the public website's own JavaScript calls — not a
documented API. They sit behind Cloudflare, which occasionally answers a
"Just a moment..." challenge page (HTTP 403, HTML) instead of JSON. The
client therefore:

* talks through ``curl_cffi`` (libcurl-impersonate), which reproduces a real browser's TLS
  handshake AND its HTTP/2 settings, falling back to a ``curl`` subprocess and then stdlib
  ``urllib``. Cloudflare fingerprints the connection, not the headers, and it has tightened
  twice: ``httpx``/``requests`` were challenged from the start, ``urllib`` passed until
  2026-09-14, plain curl passed until 2026-09-22 and was challenged from 16:29 that day
  (measured 2026-09-24: identical headers, every plain-curl request 403 - the whole site,
  not just the API - while impersonate="chrome" returned all 963 rows over HTTP/3; neither
  curl on that host had HTTP/2 at all, which is by itself a tell no browser sends). The
  impersonation PROFILE matters as much as the library: ``chrome`` and ``safari`` passed,
  the pinned older ``chrome124`` and ``edge101`` were still challenged, so the profile
  tracks "current browser" and is worth re-checking when challenges come back.
  ``INGEST_IDX_TRANSPORT`` = ``impersonate`` | ``curl`` | ``urllib`` | ``auto`` (default)
  picks the transport, ``INGEST_IDX_IMPERSONATE`` the profile (default ``chrome``),
* paces requests (``idx_rps``) and enforces a per-day request budget,
* retries challenges / 5xx / non-JSON bodies with exponential backoff,
* opens a circuit after N consecutive failures (one long pause, then raise),
* fingerprints every payload's row shape so the ETL can detect field drift.

Every successful fetch is returned as a :class:`FetchResult` carrying the raw
bytes; callers hand it to :mod:`bronze` before any parsing so the archive is
the source of truth and silver can always be replayed.
"""
from __future__ import annotations

import http.cookiejar
import json
import logging
import os
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import quote

from ..shared.settings import get_settings

FetchFn = Callable[[str, dict[str, str]], tuple[int, bytes]]

logger = logging.getLogger(__name__)

BASE = "https://www.idx.co.id"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
BACKOFF_S = (5, 10, 20, 40, 80)

# endpoint name -> (path template, referer path, key for the row list in the payload)
ENDPOINTS: dict[str, tuple[str, str, str | None]] = {
    "securities_stock": ("/primary/StockData/GetSecuritiesStock?start=0&length=9999&code=&sector=&board=&language=id-id",
                         "/id/data-pasar/data-saham/daftar-saham/", "data"),
    "stock_summary": ("/primary/TradingSummary/GetStockSummary?length=9999&start=0&date={date}",
                      "/id/data-pasar/ringkasan-perdagangan/ringkasan-saham/", "data"),
    "index_summary": ("/primary/TradingSummary/GetIndexSummary?length=9999&start=0&date={date}",
                      "/id/data-pasar/ringkasan-perdagangan/ringkasan-indeks/", "data"),
    "trading_info": ("/primary/ListedCompany/GetTradingInfoSS?code={code}&start=0&length=10000",
                     "/id/perusahaan-tercatat/profil-perusahaan-tercatat/{code}", "replies"),
    "financial_report": ("/primary/ListedCompany/GetFinancialReport?indexFrom={index_from}&pageSize={page_size}"
                         "&year={year}&reportType={report_type}&EmitenType=s&periode={period}&kodeEmiten={code}"
                         "&SortColumn=KodeEmiten&SortOrder=asc",
                         "/id/perusahaan-tercatat/laporan-keuangan-dan-tahunan/", "Results"),
    "announcement": ("/primary/ListedCompany/GetAnnouncement?kodeEmiten={code}&indexFrom={index_from}"
                     "&pageSize={page_size}&dateFrom={date_from}&dateTo={date_to}&lang=id&keyword=",
                     "/id/perusahaan-tercatat/keterbukaan-informasi/", "Replies"),
}


class IdxFetchError(RuntimeError):
    """The endpoint did not return usable JSON after all retries."""


class CircuitOpen(IdxFetchError):
    """Too many consecutive failures; the caller should stop for now."""


class BudgetExceeded(IdxFetchError):
    """The per-day request budget is spent."""


@dataclass(frozen=True)
class FetchResult:
    endpoint: str
    key: str
    url: str
    status: int
    body: bytes
    payload: Any
    fetched_at: datetime
    fingerprint: str | None

    def rows(self) -> list[dict[str, Any]]:
        list_key = ENDPOINTS[self.endpoint][2]
        if list_key is None:
            return self.payload if isinstance(self.payload, list) else []
        rows = self.payload.get(list_key) if isinstance(self.payload, dict) else None
        return rows or []


def fingerprint_of(rows: list[dict[str, Any]]) -> str | None:
    """Sorted, comma-joined top-level field names of the first row (None if no rows)."""
    if not rows or not isinstance(rows[0], dict):
        return None
    return ",".join(sorted(rows[0].keys()))


def yyyymmdd(d: date) -> str:
    return d.strftime("%Y%m%d")


def _urllib_fetcher(timeout: float = 60.0) -> FetchFn:
    """Default transport: one opener with a cookie jar for the client's lifetime. INGEST_IDX_PROXY (e.g.
    http://127.0.0.1:8118, an HTTP CONNECT proxy reached over an SSH forward) routes the calls through another host for
    a recovery session; unset = this machine's own address."""
    handlers: list[urllib.request.BaseHandler] = [urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())]
    proxy = os.environ.get("INGEST_IDX_PROXY", "").strip()
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
        logger.info("idx client: via proxy %s", proxy)
    opener = urllib.request.build_opener(*handlers)

    def fetch(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
        req = urllib.request.Request(url, headers=headers)
        try:
            with opener.open(req, timeout=timeout) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read() if e.fp else b""

    return fetch


def find_curl() -> str | None:
    """The system curl (Schannel on Windows) first, then whatever the PATH offers."""
    sysroot = os.environ.get("SystemRoot")
    if sysroot:
        cand = os.path.join(sysroot, "System32", "curl.exe")
        if os.path.exists(cand):
            return cand
    return shutil.which("curl")


def _curl_fetcher(timeout: float = 60.0) -> FetchFn | None:
    """Transport through a ``curl`` subprocess: same headers, same cookie jar for the client's lifetime, body written to
    a temp file (binary-safe), status code read from ``-w``. None when no curl is installed."""
    curl = find_curl()
    if not curl:
        return None
    jfd, jar = tempfile.mkstemp(prefix="idx-cookies-", suffix=".txt")
    os.close(jfd)
    proxy = os.environ.get("INGEST_IDX_PROXY", "").strip()
    if proxy:
        logger.info("idx client: via proxy %s", proxy)

    def fetch(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
        fd, out = tempfile.mkstemp(prefix="idx-body-")
        os.close(fd)
        cmd = [curl, "-sS", "--compressed", "--max-time", str(int(timeout)), "-b", jar, "-c", jar, "-o", out,
               "-w", "%{http_code}"]
        for k, v in headers.items():
            cmd += ["-H", f"{k}: {v}"]
        if proxy:
            cmd += ["-x", proxy]
        cmd.append(url)
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 15)
            if res.returncode != 0:
                raise OSError(f"curl exit {res.returncode}: {(res.stderr or '').strip()[:120]}")
            try:
                status = int((res.stdout or "").strip()[-3:])
            except ValueError as e:
                raise OSError(f"curl: no status code ({res.stdout[:40]!r})") from e
            with open(out, "rb") as f:
                return status, f.read()
        finally:
            try:
                os.unlink(out)
            except OSError:
                pass

    fetch.jar = jar                                                      # type: ignore[attr-defined]  # removed by close()
    return fetch


IMPERSONATE_ENV = "INGEST_IDX_IMPERSONATE"
IMPERSONATE_DEFAULT = "chrome"                  # the moving "current Chrome" profile, not a pinned one - see the module docstring


def _impersonate_fetcher(timeout: float = 60.0) -> FetchFn | None:
    """Transport through ``curl_cffi``: libcurl-impersonate speaks a real browser's TLS handshake and HTTP/2 settings,
    which is what Cloudflare actually measures. One session, so the challenge cookies it does hand out are reused.
    None when the package is missing (it is a declared dependency; this only guards a half-installed environment)."""
    try:
        from curl_cffi import requests as cr
    except ImportError:
        return None
    profile = os.environ.get(IMPERSONATE_ENV, "").strip() or IMPERSONATE_DEFAULT
    proxy = os.environ.get("INGEST_IDX_PROXY", "").strip()
    session = cr.Session(impersonate=profile, timeout=timeout,
                         proxies={"http": proxy, "https": proxy} if proxy else None)
    logger.info("idx client: impersonating %s%s", profile, f" via proxy {proxy}" if proxy else "")

    def fetch(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
        r = session.get(url, headers=headers)
        return r.status_code, r.content

    fetch.session = session                                              # type: ignore[attr-defined]  # closed by close()
    return fetch


def default_fetcher(timeout: float = 60.0) -> FetchFn:
    """INGEST_IDX_TRANSPORT: ``impersonate`` / ``curl`` (each fails if unavailable), ``urllib``, or ``auto`` (default) =
    impersonate, then curl, then urllib. Order is by how well each survives a Cloudflare challenge."""
    mode = os.environ.get("INGEST_IDX_TRANSPORT", "auto").strip().lower() or "auto"
    if mode == "urllib":
        return _urllib_fetcher(timeout)
    if mode in ("auto", "impersonate"):
        fetch = _impersonate_fetcher(timeout)
        if fetch is not None:
            return fetch
        if mode == "impersonate":
            raise RuntimeError("INGEST_IDX_TRANSPORT=impersonate but curl_cffi is not installed")
        logger.warning("idx client: curl_cffi missing, falling back to curl (Cloudflare challenged plain curl on 2026-09-22)")
    fetch = _curl_fetcher(timeout)
    if fetch is None:
        if mode == "curl":
            raise RuntimeError("INGEST_IDX_TRANSPORT=curl but no curl executable was found")
        logger.warning("idx client: no curl on this host, falling back to urllib (Cloudflare may challenge it)")
        return _urllib_fetcher(timeout)
    return fetch


class IdxClient:
    def __init__(self, *, rps: float | None = None, daily_budget: int | None = None,
                 circuit_threshold: int | None = None, circuit_pause_s: int | None = None,
                 backoff: tuple[int, ...] = BACKOFF_S, fetch_fn: FetchFn | None = None,
                 sleep=time.sleep) -> None:
        s = get_settings()
        self.rps = rps if rps is not None else s.idx_rps
        self.daily_budget = daily_budget if daily_budget is not None else s.idx_daily_budget
        self.circuit_threshold = circuit_threshold if circuit_threshold is not None else s.idx_circuit_threshold
        self.circuit_pause_s = circuit_pause_s if circuit_pause_s is not None else s.idx_circuit_pause_s
        self.backoff = backoff
        self._sleep = sleep
        self._lock = threading.Lock()
        self._last_request = 0.0
        self._budget_day: date | None = None
        self._budget_used = 0
        self._consecutive_failures = 0
        self._circuit_paused_once = False
        self.requests_made = 0
        self._fetch = fetch_fn or default_fetcher()

    # -- public endpoint methods --------------------------------------------------------------

    def securities_stock(self) -> FetchResult:
        return self.fetch("securities_stock", key=datetime.now(UTC).date().isoformat())

    def stock_summary(self, d: date) -> FetchResult:
        return self.fetch("stock_summary", key=d.isoformat(), date=yyyymmdd(d))

    def index_summary(self, d: date) -> FetchResult:
        return self.fetch("index_summary", key=d.isoformat(), date=yyyymmdd(d))

    def trading_info(self, code: str) -> FetchResult:
        return self.fetch("trading_info", key=code.upper(), code=quote(code.upper()))

    def financial_report(self, year: int, period: str, code: str = "", index_from: int = 0,
                         page_size: int = 100, report_type: str = "rdf") -> FetchResult:
        """``report_type`` rdf = financial statements (the default, key unchanged), ar = annual reports."""
        key = f"{year}:{period}:{code.upper() or '*'}:{index_from}" + ("" if report_type == "rdf" else f":{report_type}")
        return self.fetch("financial_report", key=key, year=year, period=period,
                          code=quote(code.upper()), index_from=index_from, page_size=page_size, report_type=report_type)

    def announcement(self, code: str, date_from: date, date_to: date, index_from: int = 0,
                     page_size: int = 100) -> FetchResult:
        key = f"{code.upper() or '*'}:{date_from.isoformat()}:{date_to.isoformat()}:{index_from}"
        return self.fetch("announcement", key=key, code=quote(code.upper()), index_from=index_from,
                          page_size=page_size, date_from=yyyymmdd(date_from), date_to=yyyymmdd(date_to))

    # -- core ---------------------------------------------------------------------------------

    def fetch(self, endpoint: str, *, key: str, **params: Any) -> FetchResult:
        path_t, referer_t, _ = ENDPOINTS[endpoint]
        path = path_t.format(**params)
        referer = BASE + referer_t.format(**params)
        last_err = ""
        challenged = 0
        for wait in (0, *self.backoff):
            if wait:
                logger.info("idx fetch retry %s key=%s in %ss (%s)", endpoint, key, wait, last_err)
                self._sleep(wait)
            self._pace()
            url = BASE + path
            try:
                status, body = self._fetch(url, {"User-Agent": UA, "Referer": referer,
                                                 "Accept": "application/json, text/plain, */*"})
            except OSError as e:
                last_err = f"{type(e).__name__}: {str(e)[:80]}"
                self._failure()
                continue
            if status == 200:
                try:
                    payload = json.loads(body)
                except ValueError:
                    last_err = "non-JSON body (challenge page?)"
                    self._failure()
                    continue
                self._consecutive_failures = 0
                res = FetchResult(endpoint, key, url, status, body, payload, datetime.now(UTC), None)
                return FetchResult(**{**res.__dict__, "fingerprint": fingerprint_of(res.rows())})
            last_err = f"HTTP {status}"
            self._failure()
            if status == 404:
                break
            if status == 403:                                              # one retry clears a transient challenge; a second
                challenged += 1                                            # 403 is a block, and retrying only feeds it
                if challenged >= 2:
                    last_err += " (Cloudflare challenge; not retried further)"
                    break
        raise IdxFetchError(f"{endpoint} key={key}: {last_err}")

    def download(self, path: str, referer_path: str = "/id/perusahaan-tercatat/laporan-keuangan-dan-tahunan/") -> bytes:
        """Binary attachment (xlsx/zip/pdf) under www.idx.co.id with the same pacing/backoff/circuit as fetch().
        ``path`` is the site-relative File_Path (spaces allowed; quoted here)."""
        url = BASE + quote(path)
        last_err = ""
        challenged = 0
        for wait in (0, *self.backoff):
            if wait:
                logger.info("idx download retry %s in %ss (%s)", path[-60:], wait, last_err)
                self._sleep(wait)
            self._pace()
            try:
                status, body = self._fetch(url, {"User-Agent": UA, "Referer": BASE + referer_path, "Accept": "*/*"})
            except OSError as e:
                last_err = f"{type(e).__name__}: {str(e)[:80]}"
                self._failure()
                continue
            if status == 200 and body:
                self._consecutive_failures = 0
                return body
            last_err = f"HTTP {status}" if status != 200 else "empty body"
            self._failure()
            if status == 404:
                break
            if status == 403:
                challenged += 1
                if challenged >= 2:
                    last_err += " (Cloudflare challenge; not retried further)"
                    break
        raise IdxFetchError(f"download {path[-80:]}: {last_err}")

    def _pace(self) -> None:
        with self._lock:
            today = datetime.now(UTC).date()
            if self._budget_day != today:
                self._budget_day, self._budget_used = today, 0
            if self._budget_used >= self.daily_budget:
                raise BudgetExceeded(f"daily budget {self.daily_budget} spent")
            min_gap = 1.0 / self.rps if self.rps > 0 else 0.0
            wait = self._last_request + min_gap - time.monotonic()
            if wait > 0:
                self._sleep(wait)
            self._last_request = time.monotonic()
            self._budget_used += 1
            self.requests_made += 1

    def _failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures < self.circuit_threshold:
            return
        if self._circuit_paused_once:
            raise CircuitOpen(f"{self._consecutive_failures} consecutive failures; circuit open")
        logger.warning("idx circuit: %d consecutive failures, pausing %ss",
                       self._consecutive_failures, self.circuit_pause_s)
        self._circuit_paused_once = True
        self._sleep(self.circuit_pause_s)
        self._consecutive_failures = 0

    def close(self) -> None:
        jar = getattr(self._fetch, "jar", None)
        if jar:
            try:
                os.unlink(jar)
            except OSError:
                pass
        session = getattr(self._fetch, "session", None)
        if session is not None:
            try:
                session.close()
            except Exception:                                            # closing a transport must never fail a job
                logger.debug("idx client: session close failed", exc_info=True)

    def __enter__(self) -> IdxClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
