"""Binance SPOT klines → ``macro_raw`` (close price per bar).

The platform already ingests Binance USD-M *perp* bars (market_data) but no *spot*
price. The delta-neutral funding-carry engine needs spot to measure the basis
(perp − spot) leg honestly — without it the carry looks riskless (basis ≡ 0). This
source plumbs the missing spot close as a macro_raw series so the carry backtest can
read it like any other publisher series.

Endpoint (free, unauthenticated, full history):
    GET ``https://api.binance.com/api/v3/klines?symbol=…&interval=…&startTime=…&limit=1000``

Kline row shape (we use [0]=openTime ms, [4]=close):
    [openTime, open, high, low, close, volume, closeTime, quoteVol, trades, ...]

Series written (one per symbol; ``symbol`` column ALSO stamped so the row is
queryable both ways)::

    binance_spot_close_btcusdt   BTC spot close (USDT)
    binance_spot_close_ethusdt   ETH spot close (USDT)

Config:
    symbols: list[str]   default ["BTCUSDT", "ETHUSDT"] (ignored when request.symbol set)
    interval: str        default "1h" (Binance kline interval: 1m/5m/15m/1h/4h/1d…)
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

import httpx
from tenacity import (
    retry_if_exception,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ..shared.base import IngestionRequest, IngestionResult
from ..shared.binance_http import binance_should_retry
from ..shared.db import content_hash, get_connection, update_source_health, write_macro_raw_rows
from ..shared.pit_guards import PitConfig, partition_by_pit

logger = logging.getLogger(__name__)

name = "binance_spot"
raw_table = "macro_raw"

_BASE_URL = "https://api.binance.com"
_PATH = "/api/v3/klines"
_LIMIT = 1000  # Binance max rows per klines call
# Spot bars publish at bar-close; 12h PIT slop matches the other macro sources.
_PIT_CONFIG = PitConfig(max_backfill_lag_hours=12)
_DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT"]
_DEFAULT_INTERVAL = "1h"
# Bars per interval in milliseconds — drives forward pagination.
_INTERVAL_MS: dict[str, int] = {
    "1m": 60_000, "3m": 180_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000,
    "1h": 3_600_000, "2h": 7_200_000, "4h": 14_400_000, "6h": 21_600_000,
    "8h": 28_800_000, "12h": 43_200_000, "1d": 86_400_000,
}
_MAX_PAGES = 2000  # ~2M bars cap — well above any realistic backfill


@retry(
    reraise=True,
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    # Ban-safe policy (shared.binance_http): retry transport/5xx only —
    # HTTPStatusError is a subclass of HTTPError, so the old predicate
    # blindly retried 429/418 and risked an IP ban on the SAME public IP
    # the live trading JVM places orders from.
    retry=retry_if_exception(binance_should_retry),
)
def _http_get(client: httpx.Client, params: dict[str, Any]) -> list[Any]:
    response = client.get(f"{_BASE_URL}{_PATH}", params=params)
    response.raise_for_status()
    payload = response.json()
    # Binance returns HTTP 200 with a JSON object {"code":...,"msg":...} on bad params
    # / rate-limit, not a list — surface it loud rather than silently truncating.
    if isinstance(payload, dict):
        raise httpx.HTTPError(f"Binance klines error: {payload}")
    return payload


def _to_utc_ms(dt: datetime) -> int:
    """Naive datetime -> epoch ms, treating naive as UTC (project
    convention). Plain ``.timestamp()`` on a naive value applies the
    HOST's local timezone — see the H4 fix note at the call sites."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _fetch_spot_close(
    client: httpx.Client,
    symbol: str,
    interval: str,
    start: datetime,
    end: datetime,
    now: datetime,
) -> list[dict[str, Any]]:
    """Page spot klines for ``symbol`` over [start, end]; emit one close row per bar."""
    series_id = f"binance_spot_close_{symbol.lower()}"
    step_ms = _INTERVAL_MS.get(interval)
    if step_ms is None:
        raise ValueError(f"binance_spot: unsupported interval {interval!r}")
    # H4 fix: naive .timestamp() applies the HOST's local timezone —
    # invisible on the UTC container, but on the UTC+7 home backfill
    # box every window shifted 7h earlier, silently never fetching
    # the final 7h of each requested window. Coerce naive -> UTC
    # (project convention, same as binance_macro._to_ms).
    cursor_ms = _to_utc_ms(start)
    end_ms = _to_utc_ms(end)
    rows: list[dict[str, Any]] = []
    seen_ts: set[int] = set()
    truncated = True  # flips False when the loop exits via a stop condition

    for _ in range(_MAX_PAGES):
        data = _http_get(
            client,
            {
                "symbol": symbol,
                "interval": interval,
                "startTime": cursor_ms,
                "endTime": end_ms,
                "limit": _LIMIT,
            },
        )
        if not data:
            truncated = False
            break
        last_open_ms = cursor_ms
        for k in data:
            if not k or len(k) < 5:
                continue
            open_ms = int(k[0])
            close = k[4]
            last_open_ms = max(last_open_ms, open_ms)
            if open_ms < cursor_ms or open_ms > end_ms or open_ms in seen_ts or close is None:
                continue
            seen_ts.add(open_ms)
            # Naive UTC — codebase convention (request.start arrives naive,
            # macro_raw.event_time is naive; mixing aware datetimes breaks the
            # PIT comparison in partition_by_pit).
            event_time = datetime.fromtimestamp(open_ms / 1000.0, tz=timezone.utc).replace(tzinfo=None)
            iso_ts = event_time.isoformat()
            value = float(close)
            rows.append(
                {
                    "source": name,
                    # source_uri MUST include series_id + iso_ts — the UNIQUE
                    # (source, source_uri, event_time) constraint on macro_raw would
                    # otherwise collapse rows sharing a source_uri.
                    "source_uri": f"binance_spot/{series_id}/{iso_ts}",
                    "symbol": symbol,
                    "series_id": series_id,
                    "event_time": event_time,
                    "ingestion_time": now,
                    "value": value,
                    "value_text": None,
                    "content_hash": content_hash(series_id, iso_ts, value),
                }
            )

        # Advance past the last bar we saw. Stop when the window is covered or the
        # page returned fewer than a full batch (history exhausted).
        next_cursor = last_open_ms + step_ms
        if next_cursor > end_ms or len(data) < _LIMIT or next_cursor <= cursor_ms:
            truncated = False
            break
        cursor_ms = next_cursor
        time.sleep(0.2)  # be polite to the public endpoint

    if truncated:
        # M16 fix: page cap fired mid-window — surface instead of reporting
        # a healthy, complete pull with silently missing data.
        logger.warning(
            "binance_spot pagination cap (%d pages) hit mid-window for %s %s",
            _MAX_PAGES, symbol, interval,
        )
    return rows, truncated


def fetch(request: IngestionRequest) -> IngestionResult:
    started = time.monotonic()
    now = datetime.utcnow()  # naive UTC — matches request.start / macro_raw convention
    interval = str(request.config.get("interval") or _DEFAULT_INTERVAL)
    if request.symbol:
        symbols = [request.symbol.upper()]
    else:
        symbols = [str(s).upper() for s in (request.config.get("symbols") or _DEFAULT_SYMBOLS)]

    all_rows: list[dict[str, Any]] = []
    series_seen: list[str] = []
    any_truncated = False
    try:
        with httpx.Client(timeout=30.0) as client:
            for i, symbol in enumerate(symbols):
                if i > 0:
                    time.sleep(0.3)
                logger.info(
                    "binance_spot fetching symbol=%s interval=%s window %s → %s",
                    symbol, interval, request.start, request.end,
                )
                rows, truncated = _fetch_spot_close(
                    client, symbol, interval, request.start, request.end, now
                )
                any_truncated = any_truncated or truncated
                all_rows.extend(rows)
                if rows:
                    series_seen.append(f"binance_spot_close_{symbol.lower()}")
    except Exception as e:  # noqa: BLE001
        logger.exception("binance_spot fetch failed")
        update_source_health(name, success=False, error_message=str(e)[:500])
        raise

    accepted, rejected = partition_by_pit(
        all_rows, config=_PIT_CONFIG, now=now, request_start=request.start
    )

    rows_inserted = 0
    rows_skipped_duplicate = 0
    try:
        with get_connection() as conn:
            rows_inserted, rows_skipped_duplicate = write_macro_raw_rows(accepted, conn=conn)
            update_source_health(
                name,
                success=True,
                rows_inserted=rows_inserted,
                rows_rejected_pit=len(rejected),
                force_degraded=any_truncated,
                error_message=(
                    f"pagination cap ({_MAX_PAGES} pages) truncated the window"
                    if any_truncated else None
                ),
                conn=conn,
            )
    except Exception as e:  # noqa: BLE001
        logger.exception("binance_spot DB write failed")
        update_source_health(name, success=False, error_message=str(e)[:500])
        raise

    duration = time.monotonic() - started
    result = IngestionResult(
        source=name,
        symbol=request.symbol,
        start=request.start,
        end=request.end,
        rows_fetched=len(all_rows),
        rows_inserted=rows_inserted,
        rows_rejected_pit=len(rejected),
        rows_skipped_duplicate=rows_skipped_duplicate,
        series_seen=series_seen,
        duration_seconds=duration,
        note=(
            f"interval={interval} symbols={symbols}"
            + (f" TRUNCATED: pagination cap ({_MAX_PAGES} pages) hit" if any_truncated else "")
        ),
    )
    logger.info(
        "binance_spot fetch complete | series=%d fetched=%d inserted=%d skipped=%d pit_reject=%d duration=%.2fs",
        len(series_seen), len(all_rows), rows_inserted, rows_skipped_duplicate,
        len(rejected), duration,
    )
    return result
