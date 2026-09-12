"""Gold projection: ``idx.bar`` (+ the pre-2020 Yahoo segment) -> ``public.market_data``.

``market_data`` is the research contract (screen scripts, research JVM, Book
Authority). Rows published here are DERIVED — ``idx.bar`` and the bronze
archive are the record. Symbol convention ``<CODE>.JK``, interval ``1d``,
split-only basis:

* 2020-01-02 onward: ``idx.bar`` raw prices * ``adj_factor``.
* before that: the Yahoo split-only cache (``research-scratch/idx/<CODE>.JK.csv``,
  built with ``yf_fetch(adjust=False)``), re-based by the median close ratio on
  the first overlapping days so a split Yahoo missed cannot create a step.

``market_data.open_price`` is NOT NULL; a missing open is published as the close
and the truth stays in ``idx.bar.open_missing``.
"""
from __future__ import annotations

import csv
import logging
import statistics
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg

from . import runlog

logger = logging.getLogger(__name__)
JOB = "publish"
INTERVAL = "1d"
SPLICE_TOL = Decimal("0.01")     # |ratio-1| above this on overlap days = flagged (re-based)
SPLICE_REJECT = Decimal("0.15")  # beyond this the Yahoo segment is untrustworthy (stale placeholder, missed
                                 # consolidation): publish IDX 2020+ only for that code
OVERLAP_DAYS = 5

_UPSERT = """
INSERT INTO market_data (symbol, interval, start_time, end_time, open_price, close_price, high_price, low_price,
                         volume, trade_count, quote_asset_volume, taker_buy_base_volume, taker_buy_quote_volume, created_time)
VALUES (%(symbol)s, %(interval)s, %(start_time)s, %(end_time)s, %(open)s, %(close)s, %(high)s, %(low)s,
        %(volume)s, 0, 0, 0, 0, %(created)s)
ON CONFLICT (symbol, interval, start_time) DO UPDATE SET
    end_time = EXCLUDED.end_time, open_price = EXCLUDED.open_price, close_price = EXCLUDED.close_price,
    high_price = EXCLUDED.high_price, low_price = EXCLUDED.low_price, volume = EXCLUDED.volume
"""


def _md_row(symbol: str, d: date, o: Decimal | None, h: Decimal, lo: Decimal, c: Decimal, v: Any, created: datetime) -> dict[str, Any]:
    return {"symbol": symbol, "interval": INTERVAL, "start_time": datetime(d.year, d.month, d.day),
            "end_time": datetime(d.year, d.month, d.day, 23, 59, 59, 999000),
            "open": o if o is not None else c, "close": c, "high": h, "low": lo, "volume": v or 0, "created": created}


def _idx_bars(conn: psycopg.Connection, code: str, since: date | None) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT trade_date, open, high, low, close, volume, adj_factor
              FROM idx.bar WHERE code = %s AND source = 'idx' AND (%s::date IS NULL OR trade_date >= %s)
             ORDER BY trade_date
            """,
            (code, since, since),
        )
        rows = cur.fetchall()
    cols = ["trade_date", "open", "high", "low", "close", "volume", "adj_factor"]
    return [r if isinstance(r, dict) else dict(zip(cols, r, strict=True)) for r in rows]


def _first_idx_date(conn: psycopg.Connection, code: str) -> date | None:
    with conn.cursor() as cur:
        cur.execute("SELECT min(trade_date) FROM idx.bar WHERE code = %s AND source = 'idx'", (code,))
        row = cur.fetchone()
    return row[0] if isinstance(row, tuple) else next(iter(row.values()))


def _yahoo(yahoo_dir: Path, code: str) -> list[dict[str, Any]]:
    p = yahoo_dir / f"{code}.JK.csv"
    if not p.exists():
        return []
    out = []
    with p.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out.append({"trade_date": date.fromisoformat(r["date"]), "open": Decimal(r["open"]), "high": Decimal(r["high"]),
                        "low": Decimal(r["low"]), "close": Decimal(r["close"]), "volume": int(float(r["volume"]))})
    return out


def _yahoo_basis_ok(yahoo_dir: Path) -> bool:
    import json
    m = yahoo_dir / "manifest.json"
    if not m.exists():
        return False
    meta = json.loads(m.read_text(encoding="utf-8")).get("_meta", {})
    return meta.get("basis") == "split_only"


def _adj(b: dict[str, Any]) -> tuple[Decimal | None, Decimal, Decimal, Decimal]:
    f = b["adj_factor"]
    o = b["open"] * f if b["open"] is not None else None
    return o, b["high"] * f, b["low"] * f, b["close"] * f


def publish_code(conn: psycopg.Connection, code: str, *, since: date | None, yahoo_dir: Path | None,
                 created: datetime) -> dict[str, Any]:
    symbol = f"{code}.JK"
    stats: dict[str, Any] = {"code": code, "idx_rows": 0, "yahoo_rows": 0, "splice_ratio": None, "flag": None}
    bars = _idx_bars(conn, code, since)
    rows = []
    for b in bars:
        o, h, lo, c = _adj(b)
        rows.append(_md_row(symbol, b["trade_date"], o, h, lo, c, b["volume"], created))
    stats["idx_rows"] = len(rows)

    if yahoo_dir is not None and since is None:
        first = _first_idx_date(conn, code)
        ys = _yahoo(yahoo_dir, code)
        if ys and first is not None:
            idx_by_date = {b["trade_date"]: _adj(b)[3] for b in _idx_bars(conn, code, None)}
            ratios = [idx_by_date[y["trade_date"]] / y["close"] for y in ys
                      if y["trade_date"] in idx_by_date and y["close"] > 0][:OVERLAP_DAYS]
            ratio = Decimal(str(statistics.median([float(x) for x in ratios]))) if ratios else Decimal(1)
            stats["splice_ratio"] = float(ratio)
            if len(ratios) < 3 or abs(ratio - 1) > SPLICE_REJECT:
                stats["flag"] = (f"yahoo segment REJECTED (splice ratio {float(ratio):.4f}, overlap {len(ratios)}d); "
                                 f"pre-{first} rows removed")
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM market_data WHERE symbol = %s AND interval = %s AND start_time < %s",
                                (symbol, INTERVAL, datetime(first.year, first.month, first.day)))
                conn.commit()
                pre = []
            else:
                if abs(ratio - 1) > SPLICE_TOL:
                    stats["flag"] = f"yahoo re-based by {float(ratio):.4f} (basis mismatch on overlap)"
                pre = [y for y in ys if y["trade_date"] < first]
                for y in pre:
                    rows.append(_md_row(symbol, y["trade_date"], y["open"] * ratio, y["high"] * ratio, y["low"] * ratio,
                                        y["close"] * ratio, y["volume"], created))
            stats["yahoo_rows"] = len(pre)
    if rows:
        with conn.cursor() as cur:
            cur.executemany(_UPSERT, rows)
        conn.commit()
    return stats


def publish(conn: psycopg.Connection, *, codes: list[str] | None = None, since: date | None = None,
            yahoo_dir: Path | None = None) -> runlog.RunResult:
    """Publish all (or the given) codes. ``since`` limits to bars on/after that date (daily incremental);
    the Yahoo segment is only added on a full publish (``since=None``)."""
    r = runlog.RunResult(JOB, since.isoformat() if since else "full")
    run_id = runlog.start(conn, JOB, r.run_key)
    try:
        # market_data is a compressed hypertable: DELETE/UPDATE on compressed chunks is capped at
        # 100k decompressed tuples per transaction by default; a rejected Yahoo segment can exceed it.
        with conn.cursor() as cur:
            cur.execute("SET timescaledb.max_tuples_decompressed_per_dml_transaction TO 0")
        conn.commit()
        if yahoo_dir is not None and not _yahoo_basis_ok(yahoo_dir):
            r.warn("yahoo cache manifest is not basis=split_only; pre-2020 segment skipped")
            yahoo_dir = None
        if codes is None:
            with conn.cursor() as cur:
                cur.execute("SELECT DISTINCT code FROM idx.bar WHERE source = 'idx' ORDER BY code")
                codes = [x[0] if isinstance(x, tuple) else x["code"] for x in cur.fetchall()]
        created = datetime.now(UTC).replace(tzinfo=None)
        total = 0
        flagged = []
        for code in codes:
            st = publish_code(conn, code, since=since, yahoo_dir=yahoo_dir, created=created)
            total += st["idx_rows"] + st["yahoo_rows"]
            if st["flag"]:
                flagged.append(f"{code}: {st['flag']}")
        r.rows_in = len(codes)
        r.rows_out = total
        r.detail["codes"] = len(codes)
        if flagged:
            r.detail["splice_flags"] = len(flagged)
            for fl in flagged[:60]:
                r.warn(fl)
    except Exception as e:
        conn.rollback()
        r.status = "failed"
        r.error = f"{type(e).__name__}: {e}"[:500]
        logger.exception("idx publish failed")
    runlog.finish(conn, run_id, r)
    return r


def default_since(days: int = 7) -> date:
    return datetime.now(UTC).date() - timedelta(days=days)
