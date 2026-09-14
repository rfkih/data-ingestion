"""Macro series the desk watches next to the market: the BI policy rate, the rupiah, growth, inflation, global rates,
risk and commodities. One table, ``idx.macro`` (series, obs_date, value), filled daily by the scheduler from free
sources; the app shows the latest reading and its 1-, 3- and 12-month change; the research scripts read the same table.

Sources (probed 2026-09-14):
  fred        FRED (needs INGEST_FRED_API_KEY): OECD/IMF series for Indonesia plus US rates, VIX, Brent. The OECD
              policy-rate series stops at 2023-12 and CPI lags ~17 months; they are kept for history.
  bi          Bank Indonesia's BI-Rate page (the decision table). Python's TLS stack is refused by the site
              (connection reset); Windows curl (Schannel) is not, so the page is fetched through ``curl``.
  yahoo       Yahoo Finance daily closes (rupiah, gold, CPO, Brent futures).
  worldbank   annual GDP growth (no key).
No free source was found for the 10-year government bond yield; it is the gap.

Pure parts: the series catalog, the BI table parser, the change table. Shell: fetchers and storage.
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import urllib.request
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import psycopg

from ..shared.settings import get_settings
from . import runlog

logger = logging.getLogger(__name__)
JOB = "idx.macro"


@dataclass(frozen=True)
class Series:
    key: str
    label: str
    source: str            # fred | yahoo | bi | worldbank
    source_id: str
    freq: str              # D | M | Q | A | event
    unit: str              # pct | idr | usd | index | myr
    group: str             # indonesia | global | commodity


CATALOG: tuple[Series, ...] = (
    Series("bi_rate", "BI-Rate (policy rate)", "bi", "https://www.bi.go.id/id/statistik/indikator/bi-rate.aspx", "event", "pct", "indonesia"),
    Series("bi_rate_hist", "BI policy rate, monthly (OECD, to 2023)", "fred", "IRSTCB01IDM156N", "M", "pct", "indonesia"),
    Series("usdidr", "USD/IDR", "yahoo", "IDR=X", "D", "idr", "indonesia"),
    Series("id_gdp_qoq", "Indonesia GDP growth, q/q (OECD)", "fred", "NAEXKP01IDQ657S", "Q", "pct", "indonesia"),
    Series("id_gdp_annual", "Indonesia GDP growth, annual (World Bank)", "worldbank", "NY.GDP.MKTP.KD.ZG", "A", "pct", "indonesia"),
    Series("id_cpi", "Indonesia CPI index (OECD, lagged)", "fred", "IDNCPIALLMINMEI", "M", "index", "indonesia"),
    Series("us10y", "US 10-year Treasury yield", "fred", "DGS10", "D", "pct", "global"),
    Series("fedfunds", "Fed funds effective rate", "fred", "FEDFUNDS", "M", "pct", "global"),
    Series("vix", "VIX", "fred", "VIXCLS", "D", "index", "global"),
    Series("brent", "Brent crude, USD/bbl", "fred", "DCOILBRENTEU", "D", "usd", "commodity"),
    Series("gold", "Gold futures, USD/oz", "yahoo", "GC=F", "D", "usd", "commodity"),
    Series("cpo", "Crude palm oil futures", "yahoo", "CPO=F", "D", "myr", "commodity"),
)
BY_KEY = {s.key: s for s in CATALOG}
ID_MONTHS = {"januari": 1, "februari": 2, "maret": 3, "april": 4, "mei": 5, "juni": 6, "juli": 7, "agustus": 8, "september": 9,
             "oktober": 10, "november": 11, "desember": 12}

# ---------------------------------------------------------------------------
# pure
# ---------------------------------------------------------------------------


def parse_bi_rate_page(html: str) -> list[tuple[date, Decimal]]:
    """The BI-Rate decision table: '<td>19 Agustus 2026</td><td>5.75 %</td>' pairs -> [(date, rate)], oldest first."""
    out = []
    for m in re.finditer(r"<td[^>]*>\s*(\d{1,2})\s+([A-Za-z]+)\s+(20\d\d)\s*</td>\s*<td[^>]*>\s*(\d{1,2}[.,]\d{2})\s*%", html):
        mon = ID_MONTHS.get(m.group(2).lower())
        if not mon:
            continue
        out.append((date(int(m.group(3)), mon, int(m.group(1))), Decimal(m.group(4).replace(",", "."))))
    return sorted(set(out))


def changes(points: list[tuple[date, Decimal]], asof: date | None = None) -> dict[str, Any]:
    """Latest value and the change over 1, 3 and 12 months (value at or before the earlier date)."""
    if not points:
        return {"date": None, "value": None, "chg_1m": None, "chg_3m": None, "chg_12m": None}
    pts = sorted(points)
    last_d, last_v = pts[-1]
    asof = asof or last_d

    def at(d: date) -> Decimal | None:
        prev = [v for dd, v in pts if dd <= d]
        return prev[-1] if prev else None

    out: dict[str, Any] = {"date": last_d, "value": last_v}
    for name, days in (("chg_1m", 30), ("chg_3m", 91), ("chg_12m", 365)):
        v = at(asof - timedelta(days=days))
        out[name] = None if v is None else last_v - v
        out[name + "_pct"] = None if (v is None or v == 0) else (last_v / v - 1) * 100
    return out


# ---------------------------------------------------------------------------
# fetchers
# ---------------------------------------------------------------------------


def fetch_fred(series_id: str, since: date) -> list[tuple[date, Decimal]]:
    key = get_settings().fred_api_key
    if not key:
        raise RuntimeError("INGEST_FRED_API_KEY not configured")
    from fredapi import Fred
    s = Fred(api_key=key).get_series(series_id, observation_start=since.isoformat()).dropna()
    return [(d.date(), Decimal(str(round(float(v), 6)))) for d, v in s.items()]


def fetch_yahoo(symbol: str, since: date) -> list[tuple[date, Decimal]]:
    import yfinance as yf
    h = yf.Ticker(symbol).history(start=since.isoformat(), auto_adjust=False)
    return [(d.date(), Decimal(str(round(float(v), 6)))) for d, v in h["Close"].dropna().items()]


def fetch_bi_rate(url: str) -> list[tuple[date, Decimal]]:
    curl = shutil.which("curl")
    html = None
    if curl:
        try:
            res = subprocess.run([curl, "-s", "--max-time", "60", "-A", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128 Safari/537.36", url],
                                 capture_output=True, timeout=90, check=False)
            if res.returncode == 0 and res.stdout:
                html = res.stdout.decode("utf-8", "ignore")
        except (subprocess.SubprocessError, OSError) as e:
            logger.warning("bi-rate via curl failed: %s", e)
    if html is None:                                                       # last resort; the site usually resets this
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        html = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "ignore")
    rows = parse_bi_rate_page(html)
    if not rows:
        raise RuntimeError("BI-Rate page fetched but no decision rows parsed")
    return rows


def fetch_worldbank(indicator: str, since: date) -> list[tuple[date, Decimal]]:
    url = f"https://api.worldbank.org/v2/country/ID/indicator/{indicator}?format=json&per_page=100"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    doc = json.loads(urllib.request.urlopen(req, timeout=60).read())
    out = []
    for row in doc[1] or []:
        if row.get("value") is None:
            continue
        d = date(int(row["date"]), 12, 31)
        if d >= since:
            out.append((d, Decimal(str(round(float(row["value"]), 6)))))
    return sorted(out)


def fetch(series: Series, since: date) -> list[tuple[date, Decimal]]:
    if series.source == "fred":
        return fetch_fred(series.source_id, since)
    if series.source == "yahoo":
        return fetch_yahoo(series.source_id, since)
    if series.source == "bi":
        return [p for p in fetch_bi_rate(series.source_id) if p[0] >= since]
    if series.source == "worldbank":
        return fetch_worldbank(series.source_id, since)
    raise ValueError(series.source)


# ---------------------------------------------------------------------------
# storage and the job
# ---------------------------------------------------------------------------


def upsert(conn: psycopg.Connection, key: str, source: str, points: list[tuple[date, Decimal]]) -> int:
    if not points:
        return 0
    with conn.cursor() as cur:
        cur.executemany("""INSERT INTO idx.macro (series, obs_date, value, source) VALUES (%s, %s, %s, %s)
                           ON CONFLICT (series, obs_date) DO UPDATE SET value = EXCLUDED.value, source = EXCLUDED.source, fetched_at = now()""",
                        [(key, d, v, source) for d, v in points])
    conn.commit()
    return len(points)


def last_date(conn: psycopg.Connection, key: str) -> date | None:
    with conn.cursor() as cur:
        cur.execute("SELECT max(obs_date) FROM idx.macro WHERE series = %s", (key,))
        row = cur.fetchone()
    v = row[0] if not isinstance(row, dict) else row["max"]
    return v


def pull(conn: psycopg.Connection, keys: list[str] | None = None, full: bool = False) -> runlog.RunResult:
    """Fetch every series (or ``keys``) from its source. Incremental: from 60 days before the last stored point; ``full``
    reloads from 2005. One failing source does not stop the others (status 'partial')."""
    r = runlog.RunResult(JOB + ":pull", "full" if full else "incremental")
    run_id = runlog.start(conn, JOB + ":pull", r.run_key)
    todo = [BY_KEY[k] for k in keys] if keys else list(CATALOG)
    failed = []
    for s in todo:
        last = None if full else last_date(conn, s.key)
        since = date(2005, 1, 1) if last is None else last - timedelta(days=60)
        try:
            pts = fetch(s, since)
            n = upsert(conn, s.key, s.source, pts)
            r.rows_out += n
            r.detail[s.key] = {"points": n, "last": str(pts[-1][0]) if pts else None}
        except Exception as e:  # one source down must not hide the rest
            conn.rollback()
            failed.append(s.key)
            r.warn(f"{s.key}: {type(e).__name__}: {str(e)[:120]}")
            logger.warning("macro %s failed: %s", s.key, e)
    r.rows_in = len(todo)
    r.detail["failed"] = failed
    if failed and len(failed) == len(todo):
        r.status, r.error = "failed", "every source failed"
    elif failed:
        r.status = "partial"
    runlog.finish(conn, run_id, r)
    return r


def points(conn: psycopg.Connection, key: str, since: date | None = None) -> list[tuple[date, Decimal]]:
    with conn.cursor() as cur:
        cur.execute("SELECT obs_date, value FROM idx.macro WHERE series = %s AND (%s::date IS NULL OR obs_date >= %s) ORDER BY obs_date",
                    (key, since, since))
        rows = cur.fetchall()
    return [(row[0], row[1]) if not isinstance(row, dict) else (row["obs_date"], row["value"]) for row in rows]


def board(conn: psycopg.Connection, history_months: int = 24) -> list[dict[str, Any]]:
    """Every series with its latest reading, changes, and a monthly history for a sparkline. bi_rate merges the OECD
    history with the BI page so one row carries the whole policy-rate path."""
    out = []
    cutoff = date.today() - timedelta(days=31 * history_months)
    for s in CATALOG:
        if s.key == "bi_rate_hist":
            continue
        pts = points(conn, s.key)
        if s.key == "bi_rate":
            hist = [p for p in points(conn, "bi_rate_hist") if not pts or p[0] < pts[0][0]]
            pts = sorted(hist + pts)
        c = changes(pts)
        monthly: dict[str, Decimal] = {}
        for d, v in pts:
            if d >= cutoff:
                monthly[d.strftime("%Y-%m")] = v                             # last value of each month
        row = {"key": s.key, "label": s.label, "source": s.source, "freq": s.freq, "unit": s.unit, "group": s.group,
               "history": [{"month": m, "value": v} for m, v in sorted(monthly.items())]}
        row.update(c)
        if s.key == "id_cpi" and len(pts) > 12:                            # the index is meaningless; show inflation y/y
            last_d, last_v = pts[-1]
            prev = [v for dd, v in pts if dd <= last_d - timedelta(days=360)]
            row["yoy_pct"] = None if not prev or prev[-1] == 0 else (last_v / prev[-1] - 1) * 100
        out.append(row)
    return out


def now_utc() -> datetime:
    return datetime.now(UTC)
