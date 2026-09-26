"""Rights (HMETD) and warrants: the universe, the rights' terms and daily prices (Phase 2, operator 2026-09-26: "Tetap IDX saja").

Sources (research/IDX_RIGHTS_WARRANTS_FEASIBILITY_2026-09-26.md):
  universe  IDX DigitalStatistic LINK_TRADING_SUMMARY_RIGHT / _WARRANT, one row per security per MONTH -> idx.deriv_month.
            A right's code carries its expiry ('COCO-R20260721'); a warrant's does not ('COCO-W').
  terms     IDX DigitalStatistic LINK_RIGHT_OFFERING, yearly + cumulative (the only parameter set that answers; monthly and the
            non-cumulative yearly return subsets) -> idx.right_offering: ratio old:new, exercise price, ex/record dates.
            The table lags: the current year holds only the issues IDX has already tabulated.
  prices    Stockbit company-price-feed/historical/summary/{CODE} (the endpoint jobs/bar_open.py uses), by the series' window,
            volume > 0 only (expired codes are padded with zero-volume rows) -> idx.deriv_bar.
Series: the exchange code is reused by later issues, so a bar belongs to a series - a right's IDX code with its expiry, a
warrant's code plus the first month of an unbroken run of monthly listings ('COCO-W@2025-10').
"""
from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import psycopg
from psycopg.rows import tuple_row

from .. import runlog
from .bar_open import STOCKBIT_PACE, STOCKBIT_URL, StockbitStop

logger = logging.getLogger(__name__)
JOB = "deriv"
KINDS = {"right": "LINK_TRADING_SUMMARY_RIGHT", "warrant": "LINK_TRADING_SUMMARY_WARRANT"}
OFFERING = "LINK_RIGHT_OFFERING"
FIRST = date(2020, 1, 1)
SPAN_DAYS = 350                                    # Stockbit answers about a year per request


# ---------------------------------------------------------------------------------------------------------------- pure
def month_iter(a: date, b: date) -> list[date]:
    out, d = [], date(a.year, a.month, 1)
    while d <= b:
        out.append(d)
        d = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return out


def month_end(m: date) -> date:
    return date(m.year + (m.month == 12), m.month % 12 + 1, 1) - timedelta(days=1)


def right_expiry(idx_code: str) -> date | None:
    m = re.search(r"-R(\d{8})$", idx_code)
    return date(int(m.group(1)[:4]), int(m.group(1)[4:6]), int(m.group(1)[6:])) if m else None


def exchange_code(idx_code: str) -> str:
    """'COCO-R20260721' -> 'COCO-R'; warrant codes are already exchange codes."""
    return re.sub(r"(-R)\d{8}$", r"\1", idx_code.strip().upper())


def parse_ratio(raw: str | None) -> tuple[Decimal, Decimal] | None:
    """'100 : 111' / '1:1' / '5 : 2' -> (old, new). None when it does not read as two numbers."""
    if not raw:
        return None
    nums = re.findall(r"\d+(?:[.,]\d+)?", raw)
    if len(nums) != 2:
        return None
    a, b = (Decimal(x.replace(",", ".")) for x in nums)
    return (a, b) if a > 0 and b > 0 else None


def series(months: list[tuple[str, str, date]]) -> list[dict[str, Any]]:
    """Pure. (kind, idx_code, month) rows -> fetch windows. A right whose IDX code carries its expiry ('COCO-R20260721', from mid
    2020): one series, first day of its first month to the expiry. Everything else - warrants, and the older rights printed
    without an expiry ('AGRS-R' = five issues 2020-24) - one series per unbroken run of months under the same code."""
    by: dict[tuple[str, str], list[date]] = {}
    for kind, code, m in months:
        by.setdefault((kind, code), []).append(m)
    out = []
    for (kind, code), ms in sorted(by.items()):
        ms = sorted(set(ms))
        exp = right_expiry(code) if kind == "right" else None
        if exp:
            out.append({"series": code, "code": exchange_code(code), "kind": kind, "start": ms[0], "end": exp})
            continue
        run = [ms[0]]
        for m in ms[1:]:
            prev = run[-1]
            if m == date(prev.year + (prev.month == 12), prev.month % 12 + 1, 1):
                run.append(m)
            else:
                out.append({"series": f"{code}@{run[0]:%Y-%m}", "code": code, "kind": kind, "start": run[0], "end": month_end(run[-1])})
                run = [m]
        out.append({"series": f"{code}@{run[0]:%Y-%m}", "code": code, "kind": kind, "start": run[0], "end": month_end(run[-1])})
    return out


def spans(a: date, b: date, days: int = SPAN_DAYS) -> list[tuple[date, date]]:
    out = []
    while a <= b:
        e = min(b, a + timedelta(days=days))
        out.append((a, e))
        a = e + timedelta(days=1)
    return out


def keep_bars(rows: list[dict[str, Any]], start: date, end: date) -> list[dict[str, Any]]:
    """Pure. Stockbit rows -> the traded days inside the window, one per date."""
    out: dict[date, dict[str, Any]] = {}
    for x in rows:
        try:
            d = date.fromisoformat(str(x["date"])[:10])
        except (KeyError, ValueError):
            continue
        if start <= d <= end and float(x.get("volume") or 0) > 0 and x.get("close") is not None:
            out[d] = {**x, "date": d}
    return [out[d] for d in sorted(out)]


# ---------------------------------------------------------------------------------------------------------------- fetch
def fetch_stockbit_rows(code: str, start: date, end: date, headers: dict[str, str],
                        get: Callable[[str, dict[str, str]], tuple[int, bytes]] | None = None) -> list[dict[str, Any]]:
    def _get(url: str, h: dict[str, str]) -> tuple[int, bytes]:
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=30) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()
    rows: list[dict[str, Any]] = []
    for a, b in spans(start, end):
        for page in range(1, 25):
            status, body = (get or _get)(STOCKBIT_URL.format(code=code, start=a, end=b, page=page), headers)
            if status in (401, 402, 403, 429):
                raise StockbitStop(f"HTTP {status} on {code}")
            if status != 200:
                break
            got = json.loads(body).get("data", {}).get("result") or []
            rows += got
            if get is None:
                time.sleep(STOCKBIT_PACE)
            if len(got) < 50:
                break
    return rows


# ---------------------------------------------------------------------------------------------------------------- store
def store_months(conn: psycopg.Connection, kind: str, month: date, rows: list[dict[str, Any]]) -> int:
    n = 0
    with conn.cursor() as cur:
        for x in rows:
            code = str(x.get("Code") or "").strip().upper()
            if not code:
                continue
            cur.execute("""INSERT INTO idx.deriv_month (kind, idx_code, month, board, name, high, low, close, volume, value, freq, days)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                           ON CONFLICT (idx_code, month, board) DO UPDATE SET name = EXCLUDED.name, high = EXCLUDED.high, low = EXCLUDED.low,
                               close = EXCLUDED.close, volume = EXCLUDED.volume, value = EXCLUDED.value, freq = EXCLUDED.freq,
                               days = EXCLUDED.days, fetched_at = now()""",
                        (kind, code, month, str(x.get("Board") or ""), x.get("Name"), x.get("High"), x.get("Low"), x.get("Close"),
                         x.get("Volume"), x.get("Value"), x.get("Freq"), x.get("Day")))
            n += 1
    conn.commit()
    return n


def store_offerings(conn: psycopg.Connection, rows: list[dict[str, Any]]) -> int:
    n = 0
    with conn.cursor() as cur:
        for x in rows:
            code, ex = str(x.get("code") or "").strip().upper(), x.get("exDate")
            if not code or not ex:
                continue
            ratio = parse_ratio(x.get("ratio"))
            cur.execute("""INSERT INTO idx.right_offering (code, ex_date, rec_date, issuer, ratio_raw, ratio_old, ratio_new, ex_price,
                                                          shares_issued, fund_raised, trading_note, raw)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                           ON CONFLICT (code, ex_date) DO UPDATE SET rec_date = EXCLUDED.rec_date, issuer = EXCLUDED.issuer,
                               ratio_raw = EXCLUDED.ratio_raw, ratio_old = EXCLUDED.ratio_old, ratio_new = EXCLUDED.ratio_new,
                               ex_price = EXCLUDED.ex_price, shares_issued = EXCLUDED.shares_issued, fund_raised = EXCLUDED.fund_raised,
                               trading_note = EXCLUDED.trading_note, raw = EXCLUDED.raw, fetched_at = now()""",
                        (code, str(ex)[:10], str(x["recDate"])[:10] if x.get("recDate") else None, x.get("issuerName"), x.get("ratio"),
                         ratio[0] if ratio else None, ratio[1] if ratio else None, x.get("exPrice"), x.get("sharesIssued"),
                         x.get("fundRaised"), x.get("rightCert"), json.dumps(x, default=str)))
            n += 1
    conn.commit()
    return n


def store_bars(conn: psycopg.Connection, s: dict[str, Any], rows: list[dict[str, Any]]) -> int:
    with conn.cursor() as cur:
        cur.executemany("""INSERT INTO idx.deriv_bar (series, code, trade_date, open, high, low, close, volume, value, frequency)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                           ON CONFLICT (series, trade_date) DO UPDATE SET open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
                               close = EXCLUDED.close, volume = EXCLUDED.volume, value = EXCLUDED.value, frequency = EXCLUDED.frequency,
                               fetched_at = now()""",
                        [(s["series"], s["code"], x["date"], x.get("open"), x.get("high"), x.get("low"), x.get("close"), x.get("volume"),
                          x.get("value"), x.get("frequency")) for x in rows])
    conn.commit()
    return len(rows)


# ---------------------------------------------------------------------------------------------------------------- run
def _tuples(conn: psycopg.Connection, sql: str) -> list[tuple]:
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(sql)
        return cur.fetchall()


def run_universe(conn: psycopg.Connection, client: Any, since: date = FIRST, until: date | None = None, *, skip_known: bool = True) -> runlog.RunResult:
    """Monthly rights/warrant tables since ``since`` (past months already stored are skipped) + the rights' terms, every year."""
    until = until or date.today()
    r = runlog.RunResult(JOB + ":universe", f"{since}..{until}")
    run_id = runlog.start(conn, r.job, r.run_key)
    try:
        have = set(_tuples(conn, "SELECT DISTINCT kind, month FROM idx.deriv_month")) if skip_known else set()
        this_month = date(until.year, until.month, 1)
        for m in month_iter(since, until):
            for kind, name in KINDS.items():
                if (kind, m) in have and m < this_month - timedelta(days=31):
                    continue
                rows = client.digital_stat(name, m.year, m.month).rows()
                r.rows_in += len(rows)
                r.rows_out += store_months(conn, kind, m, rows)
        for y in range(since.year, until.year + 1):
            rows = client.digital_stat(OFFERING, y, 0, period="yearly", cumulative=True).rows()
            r.detail[f"offerings_{y}"] = store_offerings(conn, rows)
    except Exception as e:
        conn.rollback()
        r.status, r.error = "failed", str(e)[:500]
        logger.warning("deriv universe failed: %s", e)
    runlog.finish(conn, run_id, r)
    return r


def run_bars(conn: psycopg.Connection, headers: dict[str, str], *, since: date = FIRST, refetch: bool = False,
             get: Callable[[str, dict[str, str]], tuple[int, bytes]] | None = None) -> runlog.RunResult:
    """Daily bars for every series whose window ends on/after ``since``; a series with bars through its window end is skipped
    unless ``refetch`` (an open series - a live warrant, a right still trading - is always refreshed)."""
    r = runlog.RunResult(JOB + ":bars", str(since))
    run_id = runlog.start(conn, r.job, r.run_key)
    try:
        months = _tuples(conn, "SELECT kind, idx_code, month FROM idx.deriv_month")
        done = dict(_tuples(conn, "SELECT series, max(trade_date) FROM idx.deriv_bar GROUP BY series"))
        today = date.today()
        for s in series(months):
            if s["end"] < since:
                continue
            last = done.get(s["series"])
            if last and not refetch and s["end"] < today - timedelta(days=5):
                continue
            start = s["start"] if refetch or not last else last - timedelta(days=3)
            rows = keep_bars(fetch_stockbit_rows(s["code"], start, min(s["end"], today), headers, get), s["start"], s["end"])
            r.rows_in += 1
            r.rows_out += store_bars(conn, s, rows) if rows else 0
            if not rows:
                r.warn(f"{s['series']}: no traded bars {s['start']}..{s['end']}")
    except StockbitStop as e:
        r.status, r.error = "partial", str(e)
    except Exception as e:
        conn.rollback()
        r.status, r.error = "failed", str(e)[:500]
        logger.warning("deriv bars failed: %s", e)
    r.warnings = r.warnings[:50]
    runlog.finish(conn, run_id, r)
    return r
