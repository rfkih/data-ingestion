"""Analyst consensus snapshots: mean/low/high target, number of analysts, recommendation, forward P/E, per name,
recorded weekly from Yahoo Finance so that in a year the desk can test what the free sources cannot show today: the
level of the consensus and, more usefully, its revisions. Snapshots only; nothing here is a signal yet.

Table ``idx.consensus`` (code, snapshot_date, ...). Job: the universe plus every book holding, one Yahoo call per name
at a gentle pace (this is Yahoo, not IDX, but the same manners apply).
"""
from __future__ import annotations

import logging
import time
from datetime import date
from decimal import Decimal
from typing import Any

import psycopg

from . import runlog

logger = logging.getLogger(__name__)
JOB = "idx.consensus"
FIELDS = ("currentPrice", "targetMeanPrice", "targetMedianPrice", "targetLowPrice", "targetHighPrice", "numberOfAnalystOpinions",
          "recommendationMean", "recommendationKey", "forwardPE", "trailingPE")


def _dec(v: Any) -> Decimal | None:
    try:
        return None if v is None else Decimal(str(round(float(v), 4)))
    except (TypeError, ValueError):
        return None


def snapshot_row(code: str, info: dict[str, Any], d: date) -> dict[str, Any] | None:
    """Pure. Yahoo's info dict -> one consensus row; None when Yahoo has no target for the name."""
    if not info or (info.get("targetMeanPrice") is None and info.get("numberOfAnalystOpinions") is None):
        return None
    price = _dec(info.get("currentPrice") or info.get("regularMarketPrice"))
    mean = _dec(info.get("targetMeanPrice"))
    return {"code": code, "snapshot_date": d, "price": price, "target_mean": mean, "target_median": _dec(info.get("targetMedianPrice")),
            "target_low": _dec(info.get("targetLowPrice")), "target_high": _dec(info.get("targetHighPrice")),
            "n_analysts": int(info.get("numberOfAnalystOpinions") or 0), "reco_mean": _dec(info.get("recommendationMean")),
            "reco_key": info.get("recommendationKey"), "fwd_pe": _dec(info.get("forwardPE")), "ttm_pe": _dec(info.get("trailingPE")),
            "upside_pct": None if not (price and mean and price > 0) else _dec((mean / price - 1) * 100)}


def upsert(conn: psycopg.Connection, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    with conn.cursor() as cur:
        cur.executemany("""INSERT INTO idx.consensus (code, snapshot_date, price, target_mean, target_median, target_low, target_high, n_analysts,
                                                      reco_mean, reco_key, fwd_pe, ttm_pe, upside_pct)
                           VALUES (%(code)s, %(snapshot_date)s, %(price)s, %(target_mean)s, %(target_median)s, %(target_low)s, %(target_high)s,
                                   %(n_analysts)s, %(reco_mean)s, %(reco_key)s, %(fwd_pe)s, %(ttm_pe)s, %(upside_pct)s)
                           ON CONFLICT (code, snapshot_date) DO UPDATE SET price = EXCLUDED.price, target_mean = EXCLUDED.target_mean,
                               target_median = EXCLUDED.target_median, target_low = EXCLUDED.target_low, target_high = EXCLUDED.target_high,
                               n_analysts = EXCLUDED.n_analysts, reco_mean = EXCLUDED.reco_mean, reco_key = EXCLUDED.reco_key,
                               fwd_pe = EXCLUDED.fwd_pe, ttm_pe = EXCLUDED.ttm_pe, upside_pct = EXCLUDED.upside_pct, fetched_at = now()""", rows)
    conn.commit()
    return len(rows)


def run(conn: psycopg.Connection, codes: list[str], d: date | None = None, pause_s: float = 1.5) -> runlog.RunResult:
    import yfinance as yf
    d = d or date.today()
    r = runlog.RunResult(JOB, d.isoformat())
    run_id = runlog.start(conn, JOB, r.run_key)
    rows, failed = [], []
    for c in codes:
        try:
            info = yf.Ticker(f"{c}.JK").info
            row = snapshot_row(c, info, d)
            if row:
                rows.append(row)
        except Exception as e:  # one name must not stop the sweep
            failed.append(c)
            logger.debug("consensus %s: %s", c, e)
        time.sleep(pause_s)
    r.rows_in, r.rows_out = len(codes), upsert(conn, rows)
    r.detail = {"covered": len(rows), "no_coverage": len(codes) - len(rows) - len(failed), "failed": failed[:20]}
    if failed and len(failed) > len(codes) // 5:
        r.status = "partial"
        r.warn(f"{len(failed)} names failed on Yahoo")
    runlog.finish(conn, run_id, r)
    return r


def latest(conn: psycopg.Connection, codes: list[str] | None = None) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute("""SELECT DISTINCT ON (code) code, snapshot_date, price, target_mean, target_low, target_high, n_analysts, reco_mean, reco_key,
                              fwd_pe, upside_pct FROM idx.consensus WHERE (%s::text[] IS NULL OR code = ANY(%s)) ORDER BY code, snapshot_date DESC""",
                    (codes, codes))
        rows = cur.fetchall()
    cols = ["code", "snapshot_date", "price", "target_mean", "target_low", "target_high", "n_analysts", "reco_mean", "reco_key", "fwd_pe", "upside_pct"]
    return [r if isinstance(r, dict) else dict(zip(cols, r, strict=True)) for r in rows]
