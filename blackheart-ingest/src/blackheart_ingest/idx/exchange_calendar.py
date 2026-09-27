"""The exchange's trading calendar (operator 2026-09-27: "implement tanggal merah hari libur, dan tanggal bursa, dan sesuaikan
job-nya supaya sesuai tanggal bursa buka").

Until now every job treated Monday-Friday as a trading day, so on an exchange holiday (Idul Fitri, cuti bersama, Christmas...)
the desk still scanned for gaps, armed intents, expected a bar, planned "tomorrow" and raised "no bar" alerts.

Source: the exchange's own announcement "Kalender Libur Bursa Tahun <Y>" (published each year around September, code IDX in
the announcement feed), whose PDF lists every holiday as dd-mm-yyyy per month with its name. ``sync`` finds every such
announcement (and any later amendment - a title with "Libur" from the exchange) over the last 15 months, downloads the PDF,
parses it and upserts idx.exchange_holiday (migration 0058). ``validate`` checks the parsed calendar against history: every
past weekday without a single traded name must be a listed holiday, and no listed holiday may have trading.

    is_trading_day(d)      Monday-Friday and not a holiday (in-process cache, refreshed hourly; if the table cannot be read the
                           answer falls back to Monday-Friday and says so in the log - a wrong "open" is safer than a silent stop)
    next_trading_day(d) / prev_trading_day(d)
"""
from __future__ import annotations

import io
import json
import logging
import re
import time
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import unquote
from zoneinfo import ZoneInfo

import psycopg

logger = logging.getLogger(__name__)
WIB = ZoneInfo("Asia/Jakarta")
MONTHS = ("januari", "februari", "maret", "april", "mei", "juni", "juli", "agustus", "september", "oktober", "november", "desember")
WEEKDAYS = ("senin", "selasa", "rabu", "kamis", "jumat", "sabtu", "minggu")
DATE_RE = re.compile(r"\b(\d{2})-(\d{2})-(\d{4})\b")
CACHE_TTL = 3600.0
_cache: dict[str, Any] = {"at": 0.0, "days": None}


# ---------------------------------------------------------------------------------------------------------------- pure
def parse_calendar_text(text: str) -> list[tuple[date, str | None]]:
    """The PDF's text -> [(day, name)]. Dates are read exactly (dd-mm-yyyy); names are paired with the dates of the same month
    block in order when their counts match (the PDF lays out dates, weekdays and names as separate runs), else None."""
    out: list[tuple[date, str | None]] = []
    blocks: list[tuple[list[date], list[str]]] = []
    cur: tuple[list[date], list[str]] | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        low = line.lower()
        if cur is not None and (low.startswith("jumlah hari bursa") or low.startswith("catatan")):
            break                                                       # the table ends; notes and the English copy follow
        first = low.split()[0] if low.split() else ""
        if first in MONTHS:
            cur = ([], [])
            blocks.append(cur)
            line = line[len(first):].strip()
            low = line.lower()
        if cur is None:
            continue
        dates = [date(int(y), int(m), int(d)) for d, m, y in DATE_RE.findall(line)]
        cur[0].extend(dates)
        rest = DATE_RE.sub(" ", line)
        words = [w for w in rest.split() if w.lower() not in WEEKDAYS]
        rest = " ".join(words)
        rest = re.sub(r"\s+\d{1,2}$", "", rest).strip()                 # the trailing "trading days in the month" count
        if not rest or re.fullmatch(r"\d{1,2}", rest) or "tidak ada hari libur" in rest.lower():
            continue
        cur[1].append(rest)
    for dates, names in blocks:
        paired = len(names) == len(dates)
        out += [(d, names[i] if paired else None) for i, d in enumerate(dates)]
    return sorted({d: n for d, n in out}.items())


def trading_day(d: date, holidays: set[date]) -> bool:
    return d.weekday() < 5 and d not in holidays


# ---------------------------------------------------------------------------------------------------------------- cache
def holidays(conn: psycopg.Connection | None = None, refresh: bool = False) -> set[date]:
    now = time.monotonic()
    if not refresh and _cache["days"] is not None and now - _cache["at"] < CACHE_TTL:
        return _cache["days"]
    try:
        # always its own short connection with a 3 s connect timeout: a caller's transaction is never touched (a failed read
        # would abort it), and an unreachable database (tests, CI) falls back at once instead of hanging the job
        from ..shared.settings import get_settings
        with psycopg.connect(**get_settings().db_kwargs(), connect_timeout=3) as c:
            rows = c.execute("SELECT day FROM idx.exchange_holiday").fetchall()
        days = {(r["day"] if isinstance(r, dict) else r[0]) for r in rows}
        _cache.update(at=now, days=days)
    except Exception as e:                                            # the fallback is Monday-Friday, loudly
        logger.warning("exchange calendar unreadable (%s) - treating Monday-Friday as trading days", e)
        _cache.update(at=now, days=_cache["days"] or set())
    return _cache["days"]


def is_trading_day(d: date | datetime | None = None, conn: psycopg.Connection | None = None) -> bool:
    if d is None:
        d = datetime.now(WIB).date()
    if isinstance(d, datetime):
        d = d.astimezone(WIB).date() if d.tzinfo else d.date()
    return trading_day(d, holidays(conn))


def next_trading_day(d: date, conn: psycopg.Connection | None = None) -> date:
    h = holidays(conn)
    d += timedelta(days=1)
    while not trading_day(d, h):
        d += timedelta(days=1)
    return d


def add_trading_days(d: date, n: int, conn: psycopg.Connection | None = None) -> date:
    """The n-th trading day after ``d`` (n >= 1)."""
    for _ in range(n):
        d = next_trading_day(d, conn)
    return d


def prev_trading_day(d: date, conn: psycopg.Connection | None = None) -> date:
    h = holidays(conn)
    d -= timedelta(days=1)
    while not trading_day(d, h):
        d -= timedelta(days=1)
    return d


# ---------------------------------------------------------------------------------------------------------------- sync
def _announcements(client: Any, since: date, until: date) -> list[dict[str, Any]]:
    out, lo = [], since
    while lo <= until:
        hi = min(lo + timedelta(days=89), until)
        for start in range(0, 1000, 100):
            rows = client.announcement("IDX", lo, hi, start, 100).rows()
            out += rows
            if len(rows) < 100:
                break
        lo = hi + timedelta(days=1)
    return out


def _title(a: dict[str, Any]) -> str:
    p = a.get("pengumuman") if isinstance(a.get("pengumuman"), dict) else a
    return str(p.get("JudulPengumuman") or p.get("title") or "")


def sync(conn: psycopg.Connection, client: Any, since: date | None = None) -> dict[str, Any]:
    """Find the exchange's holiday-calendar announcements, parse each PDF, upsert idx.exchange_holiday."""
    import pypdf

    from .client import BASE
    today = datetime.now(WIB).date()
    since = since or today - timedelta(days=460)
    found = [a for a in _announcements(client, since, today) if "libur" in _title(a).lower()]
    added, parsed = 0, []
    for a in sorted(found, key=lambda x: str((x.get("pengumuman") or x).get("TglPengumuman") or "")):
        p = a.get("pengumuman") if isinstance(a.get("pengumuman"), dict) else a
        pdfs = [x for x in (a.get("attachments") or []) if str(x.get("FullSavePath", "")).lower().endswith(".pdf")]
        if not pdfs:
            continue
        body = client.download(unquote(pdfs[0]["FullSavePath"].replace(BASE, "")))
        text = "\n".join(pg.extract_text() or "" for pg in pypdf.PdfReader(io.BytesIO(body)).pages)
        days = parse_calendar_text(text)
        src = f"{_title(a)} ({p.get('NoPengumuman') or pdfs[0].get('OriginalFilename')})"
        pub = p.get("TglPengumuman")
        with conn.cursor() as cur:
            for d, name in days:
                cur.execute("""INSERT INTO idx.exchange_holiday (day, name, source, published_at) VALUES (%s, %s, %s, %s)
                               ON CONFLICT (day) DO UPDATE SET name = COALESCE(EXCLUDED.name, idx.exchange_holiday.name),
                                   source = EXCLUDED.source, published_at = EXCLUDED.published_at, fetched_at = now()""",
                            (d, name, src, pub))
                added += 1
        conn.commit()
        parsed.append({"title": _title(a), "days": len(days), "years": sorted({d.year for d, _ in days})})
    holidays(conn, refresh=True)
    return {"announcements": parsed, "rows": added}


def validate(conn: psycopg.Connection, since: date = date(2020, 1, 1)) -> dict[str, Any]:
    """Past weekdays with no traded name must be listed holidays, and listed holidays must have no trading (years covered only)."""
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT trade_date FROM idx.daily_summary WHERE trade_date >= %s AND volume > 0", (since,))
        traded = {(r["trade_date"] if isinstance(r, dict) else r[0]) for r in cur.fetchall()}
    h = holidays(conn, refresh=True)
    years = {d.year for d in h}
    last = max(traded) if traded else since
    d, closed_unlisted, listed_traded = since, [], []
    while d <= last:
        if d.year in years and d.weekday() < 5:
            if d not in traded and d not in h:
                closed_unlisted.append(str(d))
            if d in traded and d in h:
                listed_traded.append(str(d))
        d += timedelta(days=1)
    return {"years": sorted(years), "through": str(last), "closed_but_not_listed": closed_unlisted, "listed_but_traded": listed_traded,
            "ok": not closed_unlisted and not listed_traded}


def main() -> int:
    import sys

    from ..shared.db import get_connection
    from .client import IdxClient
    with get_connection() as conn:
        if "--sync" in sys.argv:
            with IdxClient() as cl:
                print(json.dumps(sync(conn, cl), indent=1, default=str))
        print(json.dumps(validate(conn), indent=1, default=str))
        rows = conn.execute("SELECT day, name FROM idx.exchange_holiday WHERE day >= current_date ORDER BY day LIMIT 12").fetchall()
        for r in rows:
            print(*(r.values() if isinstance(r, dict) else r))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
