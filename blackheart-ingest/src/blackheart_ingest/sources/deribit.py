"""Deribit DVOL (implied-volatility index) → ``macro_raw``.

Deribit's DVOL is the crypto analogue of the VIX: a 30-day forward
implied-volatility index derived from the full Deribit options book per
currency. It is *forward-looking* (option-implied), structurally orthogonal
to realized-vol / ATR features computed from spot OHLCV — which is exactly
the property Step 4 (alternative data) wants.

**Free + historical.** The public ``get_volatility_index_data`` endpoint
returns DVOL OHLC candles back to each index's launch (BTC ~Mar 2021), no
auth — so this backfills full history. (The rest of the Deribit options
surface — per-strike book snapshots — is only served live on the free tier;
DVOL is the one signal with deep free history, which is why we start here.)

Series written (``symbol=NULL``, asset encoded in ``series_id`` — matching
the ``macro_raw`` convention used by funding / coinmetrics):

    deribit_btc_dvol   BTC DVOL index (implied vol, %)
    deribit_eth_dvol   ETH DVOL index (implied vol, %)

Config:
    currencies: list[str]   default ["BTC", "ETH"]
    resolution: int (sec)   default 3600 (hourly); Deribit allows 60/3600/43200/1D
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ..shared.base import IngestionRequest, IngestionResult
from ..shared.db import content_hash, get_connection, update_source_health, write_macro_raw_rows
from ..shared.pit_guards import PitConfig, partition_by_pit

logger = logging.getLogger(__name__)

name = "deribit"
raw_table = "macro_raw"

_BASE_URL = "https://www.deribit.com/api/v2"
_PATH = "/public/get_volatility_index_data"
# DVOL is published continuously; 12h PIT slop matches the other macro sources.
_PIT_CONFIG = PitConfig(max_backfill_lag_hours=12)
_DEFAULT_CURRENCIES = ["BTC", "ETH"]
_DEFAULT_RESOLUTION = 3600  # seconds (hourly)
# Deribit returns a bounded number of candles per call; we page backward from
# end_timestamp until the window is covered or the index history runs out.
_MAX_PAGES = 200


@retry(
    reraise=True,
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
)
def _http_get(client: httpx.Client, params: dict[str, Any]) -> dict[str, Any]:
    response = client.get(f"{_BASE_URL}{_PATH}", params=params)
    response.raise_for_status()
    payload = response.json()
    # Deribit returns HTTP 200 with a JSON-RPC ``error`` body for rate-limits
    # and bad params. Without this, an error response degrades to "no data"
    # and silently truncates the backfill instead of failing loud / retrying.
    if isinstance(payload, dict) and payload.get("error"):
        raise httpx.HTTPError(f"Deribit API error: {payload['error']}")
    return payload


def _to_utc_ms(dt: datetime) -> int:
    """Naive datetime -> epoch ms, treating naive as UTC (project
    convention). Plain ``.timestamp()`` applies the host's local TZ."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _fetch_dvol(
    client: httpx.Client,
    currency: str,
    start: datetime,
    end: datetime,
    resolution: int | str,
    now: datetime,
) -> list[dict[str, Any]]:
    """Page DVOL OHLC candles for ``currency`` over [start, end].

    Deribit caps points per response, so we walk backward: request up to
    ``cursor`` (= end), then re-request up to the earliest returned bar minus
    one resolution, until we reach ``start``, the history runs out, or the
    page cap fires. Idempotent at the DB layer, so an overlap on the seam is
    harmless.
    """
    series_id = f"deribit_{currency.lower()}_dvol"
    # H4 fix: naive .timestamp() applies the HOST's local timezone —
    # on the UTC+7 home backfill box every window shifted 7h earlier.
    start_ms = _to_utc_ms(start)
    cursor_ms = _to_utc_ms(end)
    ingestion_time = now
    rows: list[dict[str, Any]] = []
    seen_ts: set[int] = set()
    truncated = True  # flips False when the loop exits via a stop condition

    for _ in range(_MAX_PAGES):
        payload = _http_get(
            client,
            {
                "currency": currency,
                "start_timestamp": start_ms,
                "end_timestamp": cursor_ms,
                "resolution": resolution,
            },
        )
        data = (payload.get("result") or {}).get("data") or []
        if not data:
            truncated = False
            break

        earliest_ms = cursor_ms
        for candle in data:
            # Deribit candle shape: [timestamp_ms, open, high, low, close].
            if not candle or len(candle) < 5:
                continue
            ts_ms = int(candle[0])
            close = candle[4]
            if ts_ms < earliest_ms:
                earliest_ms = ts_ms
            if ts_ms < start_ms or ts_ms in seen_ts or close is None:
                continue
            seen_ts.add(ts_ms)
            # Naive UTC — the codebase convention (request.start arrives naive,
            # macro_raw.event_time is naive; mixing aware datetimes breaks the
            # PIT comparison in partition_by_pit).
            event_time = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).replace(tzinfo=None)
            iso_ts = event_time.isoformat()
            value = float(close)
            rows.append(
                {
                    "source": name,
                    # source_uri MUST include series_id + iso_ts — the UNIQUE
                    # constraint (source, source_uri, event_time) on macro_raw
                    # would otherwise collapse rows that share a source_uri
                    # (the binance_ob_imbalance collision class). Matches the
                    # coingecko / coinmetrics convention.
                    "source_uri": f"deribit/{series_id}/{iso_ts}",
                    "symbol": None,
                    "series_id": series_id,
                    "event_time": event_time,
                    "ingestion_time": ingestion_time,
                    "value": value,
                    "value_text": None,
                    "content_hash": content_hash(series_id, iso_ts, value),
                }
            )

        # Reached the start of the window or the index history — stop.
        if earliest_ms <= start_ms or earliest_ms >= cursor_ms:
            truncated = False
            break
        step_seconds = 86400 if resolution == "1D" else int(resolution)
        cursor_ms = earliest_ms - (step_seconds * 1000)
        time.sleep(0.2)  # be polite to the public endpoint

    if truncated:
        # M16 fix: the page cap fired mid-window. The old behaviour exited
        # silently and reported a healthy, complete pull — green with
        # missing data. Surface it so health degrades and the note says so.
        logger.warning(
            "deribit pagination cap (%d pages) hit mid-window for %s — "
            "window truncated at cursor=%s",
            _MAX_PAGES, series_id, cursor_ms,
        )
    return rows, truncated


def fetch(request: IngestionRequest) -> IngestionResult:
    started = time.monotonic()
    now = datetime.utcnow()  # naive UTC — matches request.start / macro_raw convention
    currencies = request.config.get("currencies") or _DEFAULT_CURRENCIES
    raw_resolution = request.config.get("resolution") or _DEFAULT_RESOLUTION
    # Deribit's documented resolutions are 60/3600/43200 (seconds) and
    # the string "1D". int("1D") raised ValueError BEFORE the try-block,
    # bypassing source-health bookkeeping entirely (L4 fix).
    resolution = "1D" if str(raw_resolution).upper() == "1D" else int(raw_resolution)

    all_rows: list[dict[str, Any]] = []
    series_seen: list[str] = []
    any_truncated = False
    try:
        with httpx.Client(timeout=30.0) as client:
            for i, currency in enumerate(currencies):
                if i > 0:
                    time.sleep(0.5)
                logger.info(
                    "deribit fetching DVOL currency=%s resolution=%ss window %s → %s",
                    currency, resolution, request.start, request.end,
                )
                rows, truncated = _fetch_dvol(
                    client, currency, request.start, request.end, resolution, now
                )
                any_truncated = any_truncated or truncated
                all_rows.extend(rows)
                if rows:
                    series_seen.append(f"deribit_{currency.lower()}_dvol")
    except Exception as e:  # noqa: BLE001
        logger.exception("deribit DVOL fetch failed")
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
        logger.exception("deribit DB write failed")
        update_source_health(name, success=False, error_message=str(e)[:500])
        raise

    duration = time.monotonic() - started
    result = IngestionResult(
        source=name,
        symbol=None,
        start=request.start,
        end=request.end,
        rows_fetched=len(all_rows),
        rows_inserted=rows_inserted,
        rows_rejected_pit=len(rejected),
        rows_skipped_duplicate=rows_skipped_duplicate,
        series_seen=series_seen,
        duration_seconds=duration,
        note=(
            f"TRUNCATED: pagination cap ({_MAX_PAGES} pages) hit mid-window"
            if any_truncated else None
        ),
    )
    logger.info(
        "deribit fetch complete | series=%d fetched=%d inserted=%d skipped=%d pit_reject=%d duration=%.2fs",
        len(series_seen), len(all_rows), rows_inserted, rows_skipped_duplicate,
        len(rejected), duration,
    )
    return result
