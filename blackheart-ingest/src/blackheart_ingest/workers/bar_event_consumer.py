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
from ..features.definitions import FEATURES, FeatureDef, get_feature
from ..features.persistence import (
    acquire_feature_lock,
    fail_run,
    finish_run,
    start_run,
    write_values,
)
from ..schemas.events import MarketBarEvent
from ..shared.db import get_connection
from ..shared.settings import Settings, get_settings
from ..sources.binance_orderbook import fetch_and_store as _ob_fetch_and_store
from ..webhooks import notify_inference_batch_ready

logger = logging.getLogger(__name__)

# Surfaced via the server's /healthz so the restart loop and schema-drift
# parse failures are VISIBLE — a crash-looping or silently-skipping
# consumer previously looked identical to a healthy one from outside.
CONSUMER_STATUS: dict[str, object] = {
    "enabled": False,
    "started_at": None,
    "last_bar_at": None,
    "bars_processed": 0,
    "parse_failures_total": 0,
    "consecutive_parse_failures": 0,
    "restarts": 0,
}

# Rolling window passed to compute() for per-bar features.
# 40 days covers btc_realized_vol_30d's 720-bar lookback with slack.
_LOOKBACK_DAYS = 40

# Symbols and intervals for which we fetch an L2 OB snapshot at each bar-close.
# Mirrors the symbols/intervals declared on the ob_spread_pct / ob_depth_imbalance
# / ob_spread_zscore_24h FeatureDefs. Kept as a module constant so tests can
# assert against it without importing definitions.
_OB_SYMBOLS: frozenset[str] = frozenset({"BTCUSDT", "ETHUSDT"})
_OB_INTERVALS: frozenset[str] = frozenset({"1h", "4h"})

# V137: macro_raw OB features to (re)compute after the snapshot writes the
# binance_ob_*_{sym} series. Symbol-agnostic single series (computed with
# symbol=None → stored symbol=NULL), so they aren't picked up by the
# market_data-only _features_for_bar path and must be computed explicitly.
# Auto-derived from FEATURES: macro_raw microstructure features whose names
# embed the symbol slug (e.g. "ob_spread_bps_btc" → BTCUSDT).
# Adding a new OB FeatureDef automatically appears here at next import.
_OB_MACRO_FEATURES_BY_SYMBOL: dict[str, tuple[str, ...]] = {
    symbol: tuple(
        f.name
        for f in FEATURES
        if f.family == "microstructure"
        and f.raw_tables == ("macro_raw",)
        and not f.symbols  # global scope (no per-symbol stamp)
        and symbol.lower().replace("usdt", "") in f.name
    )
    for symbol in _OB_SYMBOLS
}


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
                    # M3: serialise vs the other four writers of the same
                    # feature rows (see persistence.acquire_feature_lock).
                    acquire_feature_lock(
                        conn, f"{f.name}:{symbol}:{interval}"
                    )
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
                    # M5: a write/finish failure used to skip fail_run,
                    # leaving the run row stuck 'running' forever.
                    try:
                        written = write_values(
                            f, df, run_id=run_id, symbol=symbol, interval=interval, conn=conn,
                        )
                        finish_run(run_id, rows_written=written, conn=conn)
                    except Exception as e:
                        conn.rollback()
                        fail_run(run_id, error_message=f"persist: {e}", conn=conn)
                        raise
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


async def _fetch_ob_snapshot(bar: MarketBarEvent) -> None:
    """Fetch and store an L2 OB snapshot for this bar if the symbol/interval is in scope.

    Runs in a thread-pool executor so the HTTP call doesn't block the event loop.
    Failures are logged as warnings and swallowed — the OB snapshot is best-effort
    and must not prevent the main feature-compute pipeline from proceeding.
    """
    if bar.symbol not in _OB_SYMBOLS or bar.interval not in _OB_INTERVALS:
        return
    # M4 (PIT skew): under a processing backlog the snapshot is fetched
    # minutes after the bar closed but stored at bar.ts with pit_safe=True
    # — and the skew grows exactly during cascades, when the queue is
    # deepest and the microstructure matters most. If we're already more
    # than half an interval past the close, skip: an honest gap beats a
    # mislabeled snapshot.
    interval_s = {"1h": 3600, "4h": 14400}.get(bar.interval, 3600)
    bar_ts = bar.ts
    if bar_ts.tzinfo is not None:  # events may carry tz-aware timestamps
        bar_ts = bar_ts.astimezone(timezone.utc).replace(tzinfo=None)
    lag_s = (
        datetime.now(tz=timezone.utc).replace(tzinfo=None) - bar_ts
    ).total_seconds() - interval_s  # bar.ts is the bar OPEN; close = ts + interval
    if lag_s > interval_s / 2:
        logger.warning(
            "bar_event.ob_snapshot_skipped_stale | symbol=%s interval=%s ts=%s lag_s=%.0f",
            bar.symbol, bar.interval, bar.ts, lag_s,
        )
        return
    loop = asyncio.get_event_loop()

    def _run() -> None:
        with get_connection() as conn:
            _ob_fetch_and_store(bar.symbol, bar.interval, bar.ts, conn=conn)

    try:
        await loop.run_in_executor(None, _run)
        logger.debug(
            "bar_event.ob_snapshot_stored | symbol=%s interval=%s ts=%s",
            bar.symbol, bar.interval, bar.ts,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "bar_event.ob_snapshot_failed | symbol=%s interval=%s ts=%s error=%s",
            bar.symbol, bar.interval, bar.ts, e,
        )


async def _compute_ob_macro_features(bar: MarketBarEvent) -> None:
    """Compute the macro_raw OB features (ob_spread_bps_*/ob_imbalance_*/…) after
    the snapshot has written their input series. These are symbol-agnostic single
    series (symbol in the name), so they are NOT selected by the market_data-only
    ``_features_for_bar`` path and must be computed explicitly here — with
    ``symbol=None`` so they store under ``symbol=NULL`` (matching the V137 registry).
    Best-effort: failures are logged and swallowed.
    """
    names = _OB_MACRO_FEATURES_BY_SYMBOL.get(bar.symbol)
    if not names or bar.interval not in _OB_INTERVALS:
        return
    try:
        feats = [get_feature(n) for n in names]
        await _compute_bar_features(symbol="", interval="", features=feats)
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "bar_event.ob_macro_compute_failed | symbol=%s ts=%s error=%s",
            bar.symbol, bar.ts, e,
        )


async def _handle_bar_event(bar: MarketBarEvent) -> None:
    """Process one closed-bar event end-to-end. Errors are caught and logged."""
    # Fetch the OB snapshot first so orderbook_snapshots features see the
    # current bar's L2 state when the compute pipeline runs below. The snapshot
    # also writes the binance_ob_*_{sym} macro_raw series → compute the OB
    # macro features right after so they fill on the same bar.
    await _fetch_ob_snapshot(bar)
    await _compute_ob_macro_features(bar)

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
        # Fire the inference webhook unconditionally — the bar just closed so
        # features for its timestamp are ready whether _compute_bar_features
        # wrote them now (rows > 0) or the orchestrator feature_refresh already
        # UPSERTed them (rows == 0). Gating on rows > 0 caused source='stream'
        # to silently degrade to 'catchup_scan' whenever the feature_refresh
        # race-won by ~1s.
        cfg = get_settings()
        await notify_inference_batch_ready(
            base_url=cfg.inference_base_url,
            auth_token=cfg.inference_auth_token.get_secret_value(),
            compute_run_id="bar_event",
        )
        if rows > 0:
            logger.debug(
                "bar_event.features_written | symbol=%s interval=%s rows=%d",
                bar.symbol, bar.interval, rows,
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
        # H2 fix (2026-06-12): auto-commit made the consumer at-most-once —
        # offsets committed (background task, <=5s; and again by stop() on
        # graceful shutdown) while the multi-minute handler was still
        # running, so every deploy landing mid-bar PERMANENTLY skipped the
        # bar, including its unrecoverable bar-close L2 snapshot
        # (ob features are live-only, no backfill). Manual commit AFTER the
        # handler = at-least-once; the handler is idempotent (UPSERTs).
        enable_auto_commit=False,
        # Top-of-hour bursts (1h+4h x all symbols, serial handling, OB HTTP
        # retries) can exceed the 300s default between polls -> rebalance
        # churn. 10 min of headroom.
        max_poll_interval_ms=600_000,
    )

    await consumer.start()
    logger.info(
        "bar_event_consumer.started | bootstrap=%s group=%s",
        cfg.kafka_bootstrap_servers, cfg.kafka_group_id,
    )

    CONSUMER_STATUS["enabled"] = True
    CONSUMER_STATUS["started_at"] = (
        datetime.now(tz=timezone.utc).replace(tzinfo=None).isoformat()
    )
    try:
        async for message in consumer:
            if not message or not message.value:
                await consumer.commit()
                continue
            try:
                data = json.loads(message.value)
                bar = MarketBarEvent(**data)
                await _handle_bar_event(bar)
                CONSUMER_STATUS["bars_processed"] = (
                    int(CONSUMER_STATUS["bars_processed"]) + 1
                )
                CONSUMER_STATUS["last_bar_at"] = (
                    datetime.now(tz=timezone.utc).replace(tzinfo=None).isoformat()
                )
                CONSUMER_STATUS["consecutive_parse_failures"] = 0
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                # M14: a schema change on market.bars lands here for EVERY
                # bar — count it loudly so /healthz shows the drift instead
                # of features silently going stale until MlSignalStale fires.
                CONSUMER_STATUS["parse_failures_total"] = (
                    int(CONSUMER_STATUS["parse_failures_total"]) + 1
                )
                CONSUMER_STATUS["consecutive_parse_failures"] = (
                    int(CONSUMER_STATUS["consecutive_parse_failures"]) + 1
                )
                logger.error(
                    "bar_event_consumer.parse_error | consecutive=%s error=%s raw=%s",
                    CONSUMER_STATUS["consecutive_parse_failures"], e,
                    message.value[:200],
                )
            # At-least-once: commit only after the handler (or a logged
            # skip decision) — never let a deploy mid-bar lose the bar.
            await consumer.commit()
    finally:
        await consumer.stop()
        logger.info("bar_event_consumer.stopped")
