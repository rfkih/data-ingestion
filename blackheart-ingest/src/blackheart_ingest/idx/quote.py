"""Latest prices for a few names - what the desk needs when working a ticket: the last close and its date, the day's change,
liquidity (60-day median traded value), and the market mechanics around that price (tick size, auto-rejection band).
End-of-day only: the data plane holds no intraday quotes."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

import psycopg

from .card import _rows
from .ticket import reject_band, tick_size


def latest(conn: psycopg.Connection, codes: list[str]) -> list[dict[str, Any]]:
    codes = [c.upper().strip() for c in codes if c and c.strip()]
    if not codes:
        return []
    rows = _rows(conn, """
        WITH last2 AS (
            SELECT code, trade_date, close, open, volume,
                   row_number() OVER (PARTITION BY code ORDER BY trade_date DESC) AS rn
              FROM idx.bar WHERE code = ANY(%s) AND source IN ('idx', 'yahoo'))
        SELECT a.code, l.name, a.trade_date, a.close, a.open, a.volume, b.close AS prev_close, f.value_60d_median AS v60
          FROM last2 a LEFT JOIN last2 b ON b.code = a.code AND b.rn = 2
          LEFT JOIN idx.listing l ON l.code = a.code
          LEFT JOIN idx.feature_daily f ON f.code = a.code AND f.trade_date = a.trade_date
         WHERE a.rn = 1 ORDER BY a.code""", (codes,), ["code", "name", "trade_date", "close", "open", "volume", "prev_close", "v60"])
    out = []
    for r in rows:
        close = Decimal(r["close"])
        lo, hi = reject_band(close)
        chg = ((close - Decimal(r["prev_close"])) / Decimal(r["prev_close"]) * 100) if r["prev_close"] else None
        out.append({"code": r["code"], "name": r["name"], "trade_date": r["trade_date"], "close": close, "open": r["open"], "volume": r["volume"],
                    "prev_close": r["prev_close"], "chg_pct": chg.quantize(Decimal("0.01")) if chg is not None else None, "v60": r["v60"],
                    "tick": tick_size(close), "band_lo": lo, "band_hi": hi})
    found = {o["code"] for o in out}
    out.extend({"code": c, "name": None, "trade_date": None, "close": None, "error": "no bar"} for c in codes if c not in found)
    return out
