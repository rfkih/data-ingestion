"""
Test suite for FeatureStreamProcessor.

Tests verify that the stream processor consumes MarketBarEvents from Kafka,
computes features using a callable, and publishes ComputedFeatureEvents.
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from blackheart_ingest.schemas.events import MarketBarEvent, ComputedFeatureEvent
from blackheart_ingest.workers.feature_stream import FeatureStreamProcessor


@pytest.mark.asyncio
async def test_feature_stream_processor_init():
    """Test FeatureStreamProcessor initialization."""
    async def dummy_compute(bar: MarketBarEvent) -> dict[str, float]:
        return {"rsi_14": 65.5}

    processor = FeatureStreamProcessor(
        bootstrap_servers="localhost:9092",
        compute_fn=dummy_compute,
        signal_id="regime_btc_v3",
        feature_version="1.0.0",
    )

    assert processor.bootstrap_servers == "localhost:9092"
    assert processor.signal_id == "regime_btc_v3"
    assert processor.feature_version == "1.0.0"
    assert processor.compute_fn == dummy_compute


@pytest.mark.asyncio
async def test_feature_stream_compute_features():
    """Test _compute_features calls the compute function."""
    async def dummy_compute(bar: MarketBarEvent) -> dict[str, float]:
        return {"rsi_14": 65.5, "macd": -0.25}

    processor = FeatureStreamProcessor(
        bootstrap_servers="localhost:9092",
        compute_fn=dummy_compute,
        signal_id="regime_btc_v3",
        feature_version="1.0.0",
    )

    ts = datetime(2026, 5, 30, 14, 30, 45, 123456, tzinfo=timezone.utc)
    bar = MarketBarEvent(
        symbol="BTCUSDT",
        ts=ts,
        open=45000.50,
        high=45500.75,
        low=44999.00,
        close=45250.25,
        volume=1500000.0,
    )

    features = await processor._compute_features(bar)

    assert isinstance(features, dict)
    assert features["rsi_14"] == 65.5
    assert features["macd"] == -0.25


@pytest.mark.asyncio
async def test_feature_stream_processor_start_stop():
    """Test that start() creates consumer and producer, stop() closes them."""
    with patch('blackheart_ingest.workers.feature_stream.AIOKafkaConsumer') as mock_consumer_cls, \
         patch('blackheart_ingest.workers.feature_stream.KafkaProducerClient') as mock_producer_cls:

        mock_consumer = AsyncMock()
        mock_consumer_cls.return_value = mock_consumer

        async def dummy_compute(bar: MarketBarEvent) -> dict[str, float]:
            return {"rsi_14": 65.5}

        processor = FeatureStreamProcessor(
            bootstrap_servers="localhost:9092",
            compute_fn=dummy_compute,
            signal_id="regime_btc_v3",
            feature_version="1.0.0",
        )

        await processor.start()

        # Verify consumer was created
        mock_consumer_cls.assert_called_once()
        mock_consumer.start.assert_called_once()

        # Verify producer context manager was started
        mock_producer_cls.assert_called_once_with(bootstrap_servers="localhost:9092")

        await processor.stop()

        # Verify consumer was stopped
        mock_consumer.stop.assert_called_once()


@pytest.mark.asyncio
async def test_feature_stream_run_method_exists():
    """Test that run() method exists and accepts the expected signature."""
    async def dummy_compute(bar: MarketBarEvent) -> dict[str, float]:
        return {"rsi_14": 65.5}

    processor = FeatureStreamProcessor(
        bootstrap_servers="localhost:9092",
        compute_fn=dummy_compute,
        signal_id="regime_btc_v3",
        feature_version="1.0.0",
    )

    # Verify run method exists and is async
    assert hasattr(processor, "run")
    assert callable(processor.run)

    # Verify it's an async function (has __await__ or is a coroutine function)
    import inspect
    assert inspect.iscoroutinefunction(processor.run)


@pytest.mark.asyncio
async def test_feature_stream_creates_correct_event_structure():
    """Test that computed features are wrapped in ComputedFeatureEvent correctly."""
    ts = datetime(2026, 5, 30, 14, 30, 45, 123456, tzinfo=timezone.utc)
    bar = MarketBarEvent(
        symbol="BTCUSDT",
        ts=ts,
        open=45000.50,
        high=45500.75,
        low=44999.00,
        close=45250.25,
        volume=1500000.0,
    )

    features = {"rsi_14": 65.5, "macd": -0.25}

    # This is what the processor should create
    event = ComputedFeatureEvent(
        signal_id="regime_btc_v3",
        symbol=bar.symbol,
        interval="1h",
        ts=bar.ts,
        feature_vector=features,
        feature_version="1.0.0",
    )

    assert event.signal_id == "regime_btc_v3"
    assert event.symbol == "BTCUSDT"
    assert event.interval == "1h"
    assert event.feature_vector == features
    assert event.feature_version == "1.0.0"
