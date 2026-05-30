"""Kafka consumer: market.bars → per-bar feature compute → inference webhook.

Replaces the Windows Task Scheduler hourly cron (ops/compute_eth_features.ps1)
with an event-driven trigger. On each closed bar received from the trading JVM:

1. Identify all FeatureDef entries whose raw_tables=("market_data",) and
   whose symbols/intervals include the bar's (symbol, interval).
2. Run ``_compute_bar_features`` — calls the existing compute() + write_values()
   pipeline over a 40-day rolling window so all rolling-window features have
   their full lookback available.
3. Fire the inference webhook (notify_inference_batch_ready) so the inference
   streaming worker picks up the new feature_values rows immediately.

The macro feature auto-loop (_compute_loop in server.py) is kept unchanged —
macro features (VIX, DXY, funding) arrive from external APIs on their own
schedule and are not bar-driven.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from functools import partial

try:
    from aiokafka import AIOKafkaConsumer
except ImportError:
    AIOKafkaConsumer = None  # type: ignore

from ..features.compute import compute as compute_feature
from ..features.definitions import FEATURES, FeatureDef
from ..features.persistence import fail_run, finish_run, start_run, write_values
from ..schemas.events import MarketBarEvent
from ..shared.db import get_connection
from ..shared.settings import Settings, get_settings
from ..webhooks import notify_inference_batch_ready

logger = logging.getLogger(__name__)

# Rolling window passed to compute() for per-bar features.
# 40 days covers btc_realized_vol_30d's 720-bar lookback with slack.
_LOOKBACK_DAYS = 40


def _features_for_bar(
    symbol: str,
    interval: str,
    features: list[FeatureDef] | None = None,
) -> list[FeatureDef]:
    """Return FeatureDef entries that should be (re)computed for this bar.

    Filters to market_data features whose symbol + interval scope includes
    the incoming bar. An empty symbols or intervals tuple means "all".
    """
    all_features = features if features is not None else list(FEATURES)
    return [
        f for f in all_features
        if f.raw_tables == ("market_data",)
        and (not f.symbols or symbol in f.symbols)
        and (not f.intervals or interval in f.intervals)
    ]


async def _compute_bar_features(
    symbol: str,
    interval: str,
    features: list[FeatureDef],
) -> int:
    """Run compute + persist for each feature in the list. Returns total rows written."""
    now = datetime.now(tz=timezone.utc).replace(tzinfo=None)
    start = now - timedelta(days=_LOOKBACK_DAYS)
    loop = asyncio.get_event_loop()
    total_rows = 0

    for feat in features:
        t0 = time.monotonic()
        try:
            def _run_one(f: FeatureDef) -> int:
                with get_connection() as conn:
                    run_id = start_run(
                        f, range_start=start, range_end=now,
                        symbol=symbol, interval=interval, conn=conn,
                    )
                    try:
                        df = compute_feature(
                            f, start=start, end=now, conn=conn,
                            symbol=symbol, interval=interval,
                        )
                    except Exception as e:
                        conn.rollback()
                        fail_run(run_id, error_message=str(e), conn=conn)
                        raise
                    if df is None or df.empty:
                        finish_run(run_id, rows_written=0, conn=conn)
                        return 0
                    written = write_values(
                        f, df, run_id=run_id, symbol=symbol, interval=interval, conn=conn,
                    )
                    finish_run(run_id, rows_written=written, conn=conn)
                    return written

            rows = await loop.run_in_executor(None, partial(_run_one, feat))
            total_rows += rows
            logger.debug(
                "bar_event.feature_computed | feature=%s symbol=%s interval=%s rows=%d dur=%.2fs",
                feat.name, symbol, interval, rows, time.monotonic() - t0,
            )
        except Exception as e:  # noqa: BLE001
            logger.exception(
                "bar_event.feature_failed | feature=%s symbol=%s interval=%s error=%s",
                feat.name, symbol, interval, e,
            )
    return total_rows


async def _handle_bar_event(bar: MarketBarEvent) -> None:
    """Process one closed-bar event end-to-end. Errors are caught and logged."""
    features = _features_for_bar(bar.symbol, bar.interval)
    if not features:
        logger.debug(
            "bar_event.no_features | symbol=%s interval=%s", bar.symbol, bar.interval,
        )
        return

    logger.info(
        "bar_event.received | symbol=%s interval=%s ts=%s features=%d",
        bar.symbol, bar.interval, bar.ts, len(features),
    )

    try:
        rows = await _compute_bar_features(
            symbol=bar.symbol, interval=bar.interval, features=features,
        )
        if rows > 0:
            cfg = get_settings()
            await notify_inference_batch_ready(
                base_url=cfg.inference_base_url,
                auth_token=cfg.inference_auth_token.get_secret_value(),
                compute_run_id="bar_event",
            )
    except Exception as e:  # noqa: BLE001
        logger.exception(
            "bar_event.handle_failed | symbol=%s interval=%s error=%s",
            bar.symbol, bar.interval, e,
        )


async def run_bar_event_consumer(settings: Settings | None = None) -> None:
    """Run the Kafka consumer loop. Runs until cancelled.

    Subscribes to ``market.bars``, deserialises each message as
    ``MarketBarEvent``, and calls ``_handle_bar_event``. Parse/handle errors
    are logged and skipped — the consumer never stops on a bad message.
    """
    if AIOKafkaConsumer is None:
        raise RuntimeError(
            "aiokafka not installed. Install with: pip install 'blackheart-ingest[kafka]'"
        )

    cfg = settings or get_settings()
    consumer = AIOKafkaConsumer(
        "market.bars",
        bootstrap_servers=cfg.kafka_bootstrap_servers,
        group_id=cfg.kafka_group_id,
        value_deserializer=lambda m: m.decode("utf-8") if m else None,
        auto_offset_reset="latest",
    )

    await consumer.start()
    logger.info(
        "bar_event_consumer.started | bootstrap=%s group=%s",
        cfg.kafka_bootstrap_servers, cfg.kafka_group_id,
    )

    try:
        async for message in consumer:
            if not message or not message.value:
                continue
            try:
                data = json.loads(message.value)
                bar = MarketBarEvent(**data)
                await _handle_bar_event(bar)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                logger.error(
                    "bar_event_consumer.parse_error | error=%s raw=%s",
                    e, message.value[:200],
                )
    finally:
        await consumer.stop()
        logger.info("bar_event_consumer.stopped")
