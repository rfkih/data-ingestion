"""Binance L2 order book snapshot source → ``orderbook_snapshots``.

Fetches a depth-N L2 snapshot from the Binance spot REST API at each
bar-close and stores the aggregated bid/ask depth data in the
``orderbook_snapshots`` table for downstream microstructure feature
computation (V137).

Endpoint: GET /api/v3/depth?symbol=BTCUSDT&limit=<depth>

Response shape::

    {
        "lastUpdateId": 123456,
        "bids": [["price", "qty"], ...],   # best bid first
        "asks": [["price", "qty"], ...],   # best ask first
    }

Derived fields stored:
    best_bid       — float price of the best (highest) bid
    best_ask       — float price of the best (lowest) ask
    bid_depth_sum  — total base-asset qty across the top N bid levels
    ask_depth_sum  — total base-asset qty across the top N ask levels

Design notes:
* The snapshot is taken as close to bar-close as the consumer can fire.
  Network latency means it may lag the true bar-close by a few seconds,
  but that's acceptable for a feature intended to capture regime state,
  not HFT-precision quotes.
* Upserts on (symbol, interval, bar_ts) so re-runs on the same bar
  simply overwrite with the latest fetch rather than creating duplicates.
* No PIT partition applied — the snapshot represents a point-in-time
  L2 state and has no meaningful backfill semantics (Binance does not
  provide historical L2 depth via public API).
"""
from __future__ import annotations

import logging
import sys
import time
from datetime import datetime
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ..shared.db import get_connection

logger = logging.getLogger(__name__)

name = "binance_orderbook"

_BINANCE_BASE = "https://api.binance.com"
_DEFAULT_DEPTH = 20
_MAX_DEPTH = 100


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
)
def _http_get(client: httpx.Client, path: str, params: dict[str, Any]) -> Any:
    response = client.get(
        f"{_BINANCE_BASE}{path}",
        params=params,
        timeout=10.0,
    )
    response.raise_for_status()
    return response.json()


def _parse_depth_response(data: dict[str, Any]) -> dict[str, float | None]:
    """Extract best_bid, best_ask, bid_depth_sum, ask_depth_sum from a raw depth response."""
    bids: list[list[str]] = data.get("bids") or []
    asks: list[list[str]] = data.get("asks") or []

    best_bid: float | None = None
    best_ask: float | None = None
    bid_depth_sum: float | None = None
    ask_depth_sum: float | None = None

    if bids:
        try:
            best_bid = float(bids[0][0])
            bid_depth_sum = sum(float(qty) for _, qty in bids)
        except (IndexError, ValueError, TypeError):
            logger.warning("binance_orderbook: failed to parse bids from response")

    if asks:
        try:
            best_ask = float(asks[0][0])
            ask_depth_sum = sum(float(qty) for _, qty in asks)
        except (IndexError, ValueError, TypeError):
            logger.warning("binance_orderbook: failed to parse asks from response")

    return {
        "best_bid": best_bid,
        "best_ask": best_ask,
        "bid_depth_sum": bid_depth_sum,
        "ask_depth_sum": ask_depth_sum,
    }


def fetch_snapshot(symbol: str, *, depth: int = _DEFAULT_DEPTH) -> dict[str, float | None]:
    """Fetch a fresh L2 snapshot from Binance and return parsed depth metrics.

    Args:
        symbol: Binance symbol, e.g. "BTCUSDT".
        depth:  Number of price levels to aggregate (default 20, max 100).

    Returns:
        Dict with keys: best_bid, best_ask, bid_depth_sum, ask_depth_sum.
        Any value may be None if the response was malformed.
    """
    depth = min(max(1, depth), _MAX_DEPTH)
    with httpx.Client(headers={"Accept": "application/json"}) as client:
        data = _http_get(client, "/api/v3/depth", {"symbol": symbol, "limit": depth})
    return _parse_depth_response(data)


def _store_snapshot(
    symbol: str,
    interval: str,
    bar_ts: datetime,
    snapshot: dict[str, float | None],
    *,
    depth: int = _DEFAULT_DEPTH,
    conn: Any = None,
) -> None:
    """Upsert one L2 snapshot row into orderbook_snapshots."""
    sql = """
        INSERT INTO orderbook_snapshots
            (symbol, interval, bar_ts, best_bid, best_ask, bid_depth_sum, ask_depth_sum, snapshot_depth)
        VALUES
            (%(symbol)s, %(interval)s, %(bar_ts)s,
             %(best_bid)s, %(best_ask)s, %(bid_depth_sum)s, %(ask_depth_sum)s,
             %(depth)s)
        ON CONFLICT (symbol, interval, bar_ts)
        DO UPDATE SET
            best_bid      = EXCLUDED.best_bid,
            best_ask      = EXCLUDED.best_ask,
            bid_depth_sum = EXCLUDED.bid_depth_sum,
            ask_depth_sum = EXCLUDED.ask_depth_sum,
            snapshot_depth = EXCLUDED.snapshot_depth
    """
    params = {
        "symbol": symbol,
        "interval": interval,
        "bar_ts": bar_ts,
        "depth": depth,
        **snapshot,
    }

    owned = conn is None
    if owned:
        ctx = get_connection()
        conn = ctx.__enter__()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
        conn.commit()
    except Exception:
        if owned:
            conn.rollback()
        raise
    finally:
        if owned:
            ctx.__exit__(*sys.exc_info())


def fetch_and_store(
    symbol: str,
    interval: str,
    bar_ts: datetime,
    *,
    depth: int = _DEFAULT_DEPTH,
    conn: Any = None,
) -> dict[str, float | None]:
    """Fetch an L2 snapshot from Binance and persist it to orderbook_snapshots.

    Args:
        symbol:   Binance symbol (e.g. "BTCUSDT").
        interval: Bar interval string (e.g. "1h", "4h").
        bar_ts:   Bar-close timestamp (naive UTC) used as the PK anchor.
        depth:    Number of price levels to aggregate (default 20).
        conn:     Optional existing psycopg connection. If None, opens a new one.

    Returns:
        The parsed snapshot dict (best_bid, best_ask, bid_depth_sum, ask_depth_sum).
    """
    t0 = time.monotonic()
    snapshot = fetch_snapshot(symbol, depth=depth)
    _store_snapshot(symbol, interval, bar_ts, snapshot, depth=depth, conn=conn)
    logger.info(
        "binance_orderbook.snapshot_stored | symbol=%s interval=%s bar_ts=%s "
        "best_bid=%s best_ask=%s elapsed=%.2fs",
        symbol, interval, bar_ts,
        snapshot.get("best_bid"), snapshot.get("best_ask"),
        time.monotonic() - t0,
    )
    return snapshot
