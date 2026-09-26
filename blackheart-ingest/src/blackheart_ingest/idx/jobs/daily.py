"""``daily`` job — one whole-market Ringkasan Saham day → silver.

fetch → bronze → etl → upsert ``daily_summary`` + ``bar`` → corporate-action
detection from ``Previous`` vs the prior close → ``adj_factor`` rewrite for
earlier bars. ``replay`` runs the same pipeline from the archive.

Weekends are never fetched. A trading day whose payload is empty (holiday,
or IDX has not published yet) finishes ``ok`` with ``rows_in = 0`` — the
scheduler decides whether that is late (retry) or a holiday.
"""
from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import psycopg

from .. import bronze, etl, runlog
from ..client import FetchResult, IdxClient

logger = logging.getLogger(__name__)
JOB = "daily"

_SUMMARY_COLS = [
    "trade_date", "code", "name", "remarks", "previous", "open", "first_trade", "high", "low", "close",
    "change", "volume", "value", "frequency", "index_individual", "bid", "bid_volume", "offer",
    "offer_volume", "listed_shares", "tradeable_shares", "weight_for_index", "foreign_buy",
    "foreign_sell", "delisting_date", "nonreg_volume", "nonreg_value", "nonreg_frequency",
    "source_id", "bronze_id", "fetched_at",
]
_SUMMARY_SQL = (
    f"INSERT INTO idx.daily_summary ({', '.join(_SUMMARY_COLS)}) VALUES ({', '.join('%(' + c + ')s' for c in _SUMMARY_COLS)}) "
    "ON CONFLICT (trade_date, code) DO UPDATE SET "
    + ", ".join(f"{c} = EXCLUDED.{c}" for c in _SUMMARY_COLS if c not in ("trade_date", "code"))
)
_BAR_SQL = """
INSERT INTO idx.bar (code, trade_date, source, basis, open, high, low, close, volume, value, open_missing, quality_flags, open_src)
VALUES (%(code)s, %(trade_date)s, %(source)s, %(basis)s, %(open)s, %(high)s, %(low)s, %(close)s, %(volume)s, %(value)s,
        %(open_missing)s, %(quality_flags)s, CASE WHEN %(open)s::numeric IS NULL THEN NULL ELSE 'idx' END)
ON CONFLICT (code, trade_date) DO UPDATE SET
    source = EXCLUDED.source, basis = EXCLUDED.basis, high = EXCLUDED.high,
    low = EXCLUDED.low, close = EXCLUDED.close, volume = EXCLUDED.volume, value = EXCLUDED.value,
    open_missing = EXCLUDED.open_missing, quality_flags = EXCLUDED.quality_flags, updated_at = now(),
    -- IDX's own open wins; without one, an open filled by jobs/bar_open.py survives the re-run while it still lies
    -- inside the day's (possibly corrected) low-high
    open = CASE WHEN EXCLUDED.open IS NOT NULL THEN EXCLUDED.open
                WHEN idx.bar.open_src IN ('yahoo', 'stockbit') AND idx.bar.open BETWEEN EXCLUDED.low AND EXCLUDED.high THEN idx.bar.open END,
    open_src = CASE WHEN EXCLUDED.open IS NOT NULL THEN 'idx'
                    WHEN idx.bar.open_src IN ('yahoo', 'stockbit') AND idx.bar.open BETWEEN EXCLUDED.low AND EXCLUDED.high THEN idx.bar.open_src END
"""
# adj_factor is deliberately NOT in the upsert: it is owned by corporate-action detection.


def _prior_rows(conn: psycopg.Connection, d: date, codes: list[str]) -> dict[str, dict[str, Any]]:
    """Latest daily_summary row strictly before d, per code (close + listed shares)."""
    if not codes:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (code) code, trade_date, close, listed_shares
              FROM idx.daily_summary
             WHERE code = ANY(%s) AND trade_date < %s AND trade_date >= %s - INTERVAL '400 days'
             ORDER BY code, trade_date DESC
            """,
            (codes, d, d),
        )
        rows = cur.fetchall()
    out = {}
    for r in rows:
        rr = r if isinstance(r, dict) else dict(zip(["code", "trade_date", "close", "listed_shares"], r, strict=True))
        out[rr["code"]] = rr
    return out


def _ensure_listings(conn: psycopg.Connection, summaries: list[dict[str, Any]], d: date) -> int:
    """Codes in the day-dump but unknown to idx.listing get a stub row: delisted since, or a
    share class Daftar Saham never lists (e.g. GOTOM multiple-voting shares). The universe job
    flips a stub to ACTIVE if the code ever appears in Daftar Saham."""
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO idx.listing (code, name, listed_shares, status, first_seen, last_seen)
            VALUES (%(code)s, %(name)s, %(listed_shares)s, 'NOT_IN_DAFTAR', %(trade_date)s, %(trade_date)s)
            ON CONFLICT (code) DO UPDATE SET
                first_seen = LEAST(idx.listing.first_seen, EXCLUDED.first_seen),
                last_seen  = GREATEST(idx.listing.last_seen, EXCLUDED.last_seen),
                name       = COALESCE(idx.listing.name, EXCLUDED.name)
            """,
            [{"code": s["code"], "name": s["name"], "listed_shares": s["listed_shares"], "trade_date": d} for s in summaries],
        )
        return cur.rowcount


def _one(conn: psycopg.Connection, sql: str, params: tuple) -> tuple:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
    return tuple(row.values()) if isinstance(row, dict) else tuple(row)


def _last_sessions(conn: psycopg.Connection, d: date) -> tuple[date | None, date | None]:
    """(latest daily_summary date, latest bar date) strictly before d - they differ when a session has only fallback bars."""
    return _one(conn, "SELECT (SELECT max(trade_date) FROM idx.daily_summary WHERE trade_date < %s AND trade_date >= %s - 30),"
                      "       (SELECT max(trade_date) FROM idx.bar WHERE trade_date < %s AND trade_date >= %s - 30)", (d, d, d, d))


def _redetect_next_session(conn: psycopg.Connection, d: date, r: runlog.RunResult) -> None:
    """A backfilled day d: its new bars take the adj_factor of the actions already known after d, and the next stored
    session is detected again, now against d's close (it was skipped, or compared with a stale prior, when it ran first)."""
    (nxt,) = _one(conn, "SELECT min(trade_date) FROM idx.daily_summary WHERE trade_date > %s", (d,))
    if nxt is None:
        return
    with conn.cursor() as cur:
        cur.execute("""UPDATE idx.bar b SET adj_factor = round(a.f, 10), updated_at = now()
                         FROM (SELECT code, exp(sum(ln(factor))) AS f FROM idx.corporate_action
                                WHERE ex_date > %s AND factor > 0 GROUP BY code) a
                        WHERE b.code = a.code AND b.trade_date = %s AND b.adj_factor = 1 AND round(a.f, 10) <> 1""", (d, d))
        cur.execute("SELECT code, previous, listed_shares FROM idx.daily_summary WHERE trade_date = %s", (nxt,))
        rows = [x if isinstance(x, dict) else dict(zip(["code", "previous", "listed_shares"], x, strict=True)) for x in cur.fetchall()]
    conn.commit()
    r.detail["next_session_actions_n"] = _detect_actions(conn, nxt, rows, r)


def _detect_actions(conn: psycopg.Connection, d: date, summaries: list[dict[str, Any]], r: runlog.RunResult) -> int:
    prior = _prior_rows(conn, d, [s["code"] for s in summaries])
    n = 0
    resets: list[tuple[dict[str, Any], dict[str, Any], Decimal]] = []
    with conn.cursor() as cur:
        for s in summaries:
            p = prior.get(s["code"])
            if not p:
                continue
            factor = etl.previous_reset(p["close"], s["previous"])
            if factor is None:
                if p["close"] and s["previous"] and p["close"] != s["previous"]:
                    cur.execute(
                        "UPDATE idx.bar SET quality_flags = array_append(quality_flags, 'previous_mismatch_small') "
                        "WHERE code = %s AND trade_date = %s AND NOT ('previous_mismatch_small' = ANY(quality_flags))",
                        (s["code"], d))
                continue
            resets.append((s, p, factor))
        why = etl.detection_blocked(*_last_sessions(conn, d), len(resets), len(prior))
        if why:
            resets = []
            r.warn(f"corporate-action detection skipped for {d}: {why}")
            runlog.alert_once(conn, "warning", JOB, f"corporate-action detection skipped for {d}: {why}")
        for s, p, factor in resets:
            kind, f = etl.classify_action(factor, p["listed_shares"], s["listed_shares"])
            cur.execute(
                """
                INSERT INTO idx.corporate_action (code, ex_date, kind, factor, listed_shares_before, listed_shares_after, source, note)
                VALUES (%s, %s, %s, %s, %s, %s, 'previous_reset', %s)
                ON CONFLICT (code, ex_date, kind) DO NOTHING
                """,
                (s["code"], d, kind, f, p["listed_shares"], s["listed_shares"],
                 f"previous={s['previous']} prior_close={p['close']} prior_date={p['trade_date']}"),
            )
            if cur.rowcount == 1:
                cur.execute("UPDATE idx.bar SET adj_factor = adj_factor * %s, updated_at = now() WHERE code = %s AND trade_date < %s",
                            (f, s["code"], d))
                n += 1
                r.detail.setdefault("actions", []).append(f"{s['code']} {kind} {f:.6f}")
    conn.commit()
    return n


def process(conn: psycopg.Connection, d: date, rows: list[dict[str, Any]], fetched_at: datetime,
            bronze_id: int | None, r: runlog.RunResult) -> None:
    summaries = etl.summary_rows(rows, fetched_at, bronze_id)
    r.rows_in = len(rows)
    bad_date = [s for s in summaries if s["trade_date"] != d]
    if bad_date:
        r.warn(f"{len(bad_date)} rows carry a different Date than requested; dropped")
        summaries = [s for s in summaries if s["trade_date"] == d]
    if not summaries:
        r.detail["empty"] = True
        return
    bars = [b for b in (etl.bar_row(s) for s in summaries) if b is not None]
    with conn.cursor() as cur:
        cur.executemany(_SUMMARY_SQL, summaries)
        cur.executemany(_BAR_SQL, bars)
    conn.commit()
    _ensure_listings(conn, summaries, d)
    conn.commit()
    r.rows_out = len(summaries)
    r.detail["bars"] = len(bars)
    r.detail["no_close"] = len(summaries) - len(bars)
    r.detail["open_missing"] = sum(1 for b in bars if b["open_missing"])
    r.detail["actions_n"] = _detect_actions(conn, d, summaries, r)
    _redetect_next_session(conn, d, r)


def run(conn: psycopg.Connection, client: IdxClient, d: date) -> runlog.RunResult:
    r = runlog.RunResult(JOB, d.isoformat())
    if d.weekday() >= 5:
        r.status = "skipped"
        r.detail["reason"] = "weekend"
        return r
    run_id = runlog.start(conn, JOB, r.run_key)
    try:
        res: FetchResult = client.stock_summary(d)
        drift = bronze.drift(conn, res)
        bid = bronze.write(conn, res)
        if drift:
            r.warn(f"payload fingerprint drift: {drift[0]} -> {drift[1]}")
            runlog.alert(conn, "warning", JOB, f"stock_summary field drift on {d}: {drift[1]}")
        process(conn, d, res.rows(), res.fetched_at, bid, r)
    except Exception as e:
        conn.rollback()
        r.status = "failed"
        r.error = f"{type(e).__name__}: {e}"[:500]
        logger.exception("idx daily %s failed", d)
    runlog.finish(conn, run_id, r)
    return r


def replay(conn: psycopg.Connection, d: date) -> runlog.RunResult:
    """Re-derive silver for one day from the latest archived payload (no network)."""
    r = runlog.RunResult(JOB + ":replay", d.isoformat())
    row = bronze.latest(conn, "stock_summary", d.isoformat())
    if row is None:
        r.status = "failed"
        r.error = "no bronze payload for this date"
        return r
    payload = bronze.read(None, row["path"])
    rows = payload.get("data") or [] if isinstance(payload, dict) else []
    run_id = runlog.start(conn, r.job, r.run_key)
    try:
        process(conn, d, rows, row["fetched_at"], row["id"], r)
    except Exception as e:
        conn.rollback()
        r.status = "failed"
        r.error = f"{type(e).__name__}: {e}"[:500]
    runlog.finish(conn, run_id, r)
    return r


_FALLBACK_SQL = """
INSERT INTO idx.bar (code, trade_date, source, basis, open, high, low, close, volume, value, open_missing, quality_flags, open_src)
VALUES (%(code)s, %(trade_date)s, 'yahoo', 'split_only', %(open)s, %(high)s, %(low)s, %(close)s, %(volume)s, %(value)s, false, '{fallback}',
        CASE WHEN %(open)s::numeric IS NULL THEN NULL ELSE 'yahoo' END)
ON CONFLICT (code, trade_date) DO UPDATE SET
    open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low, close = EXCLUDED.close, volume = EXCLUDED.volume,
    value = EXCLUDED.value, open_src = EXCLUDED.open_src, updated_at = now()
WHERE idx.bar.source <> 'idx'
"""


def fallback_yahoo(conn: psycopg.Connection, d: date, codes: list[str], index_symbol: str = "^JKSE") -> runlog.RunResult:
    """The day's closes from Yahoo Finance when IDX has not published (or answers with a challenge) by the evening.
    Rows carry source 'yahoo' and the flag 'fallback'; an IDX row for the same day replaces them later. The index goes
    into idx.index_daily as COMPOSITE only if that day is missing. Value is close x volume (Yahoo has no traded value)."""
    r = runlog.RunResult(JOB + ":fallback", d.isoformat())
    run_id = runlog.start(conn, JOB + ":fallback", r.run_key)
    try:
        import yfinance as yf
        rows: list[dict[str, Any]] = []
        for i in range(0, len(codes), 100):
            batch = codes[i:i + 100]
            df = yf.download([f"{c}.JK" for c in batch], start=d.isoformat(), end=(d + timedelta(days=1)).isoformat(), auto_adjust=False,
                             progress=False, group_by="ticker", threads=True)
            for c in batch:
                try:
                    sub = df[f"{c}.JK"] if len(batch) > 1 else df
                    if sub.empty or sub["Close"].dropna().empty:
                        continue
                    last = sub.dropna(subset=["Close"]).iloc[-1]
                    if last.name.date() != d:
                        continue
                    close = float(last["Close"])
                    vol = float(last["Volume"]) if last["Volume"] == last["Volume"] else 0.0
                    rows.append({"code": c, "trade_date": d, "open": float(last["Open"]) if last["Open"] == last["Open"] else None,
                                 "high": float(last["High"]) if last["High"] == last["High"] else None,
                                 "low": float(last["Low"]) if last["Low"] == last["Low"] else None,
                                 "close": close, "volume": int(vol), "value": int(close * vol)})
                except (KeyError, IndexError, TypeError):
                    continue
        r.rows_in = len(codes)
        with conn.cursor() as cur:
            cur.executemany(_FALLBACK_SQL, rows)
            cur.execute("SELECT 1 FROM idx.index_daily WHERE index_code = 'COMPOSITE' AND trade_date = %s", (d,))
            if cur.fetchone() is None:
                jk = yf.download(index_symbol, start=d.isoformat(), end=(d + timedelta(days=1)).isoformat(), auto_adjust=False, progress=False)
                if not jk.empty:
                    last = jk.iloc[-1]
                    closev = float(last["Close"].iloc[0] if hasattr(last["Close"], "iloc") else last["Close"])
                    cur.execute("""INSERT INTO idx.index_daily (trade_date, index_code, previous, open, high, low, close, volume, value, bronze_id, fetched_at)
                                   VALUES (%s, 'COMPOSITE', NULL, NULL, NULL, NULL, %s, NULL, NULL, NULL, now()) ON CONFLICT DO NOTHING""", (d, closev))
                    r.detail["index"] = closev
        conn.commit()
        r.rows_out = len(rows)
        if not rows:
            r.status, r.error = "failed", "Yahoo returned no closes for the day"
        runlog.alert(conn, "warning", JOB, f"{d}: IDX bar missing; {len(rows)} closes taken from Yahoo as a fallback (flag 'fallback'); "
                                            f"replaced when IDX publishes")
    except Exception as e:
        conn.rollback()
        r.status, r.error = "failed", f"{type(e).__name__}: {e}"[:500]
        logger.exception("idx daily fallback %s failed", d)
    runlog.finish(conn, run_id, r)
    return r


def latest_bar_date(conn: psycopg.Connection) -> date | None:
    with conn.cursor() as cur:
        cur.execute("SELECT max(trade_date) FROM idx.bar WHERE source = 'idx'")
        row = cur.fetchone()
    v = row[0] if isinstance(row, tuple) else next(iter(row.values()))
    return v


def now_utc() -> datetime:
    return datetime.now(UTC)


_ = Decimal  # re-export guard for type checkers
