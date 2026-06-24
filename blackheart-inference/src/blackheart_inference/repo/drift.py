"""DB access for feature-drift (PSI) monitoring — pulls a feature's values over
a time window from ``feature_values``. Read-only. Mirrors the asyncpg / raw-SQL
pattern in ``repo/features.py``."""

from __future__ import annotations

from datetime import datetime

import asyncpg


async def fetch_feature_window(
    conn: asyncpg.Connection,
    feature_name: str,
    version: int,
    symbol: str,
    interval: str,
    start: datetime,
    end: datetime,
) -> list[float]:
    """Non-null values of one feature for a (symbol, interval) in [start, end).

    Global/macro features use the empty-string sentinels for symbol+interval
    (same convention as the inference feature loader)."""
    rows = await conn.fetch(
        """
        SELECT fv.value
          FROM feature_values fv
         WHERE fv.feature_name = $1
           AND fv.version      = $2
           AND fv.symbol       = $3
           AND fv.interval     = $4
           AND fv.ts >= $5
           AND fv.ts <  $6
           AND fv.value IS NOT NULL
         ORDER BY fv.ts ASC
        """,
        feature_name,
        version,
        symbol,
        interval,
        start,
        end,
    )
    return [float(r["value"]) for r in rows]
