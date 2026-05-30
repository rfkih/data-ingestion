"""
Test suite for KafkaProducerClient.

Tests verify that the Kafka producer wrapper correctly serializes events,
calls send_and_wait, and manages async context (start/stop lifecycle).
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from blackheart_ingest.schemas.events import ComputedFeatureEvent
from blackheart_ingest.services.kafka_producer import KafkaProducerClient


@pytest.mark.asyncio
async def test_kafka_producer_context_manager_start_stop():
    """Test that context manager calls start() and stop() on producer."""
    with patch('blackheart_ingest.services.kafka_producer.AIOKafkaProducer') as mock_producer_cls:
        mock_producer = AsyncMock()
        mock_producer_cls.return_value = mock_producer

        async with KafkaProducerClient(bootstrap_servers="localhost:9092") as client:
            # Verify producer was created and started
            mock_producer_cls.assert_called_once_with(
                bootstrap_servers="localhost:9092",
            )
            mock_producer.start.assert_called_once()

        # Verify stop was called after exiting context
        mock_producer.stop.assert_called_once()


@pytest.mark.asyncio
async def test_kafka_producer_publishes_event():
    """Test that publish() serializes event and calls send_and_wait."""
    with patch('blackheart_ingest.services.kafka_producer.AIOKafkaProducer') as mock_producer_cls:
        mock_producer = AsyncMock()
        mock_producer_cls.return_value = mock_producer
        # Mock send_and_wait to be an async method
        mock_producer.send_and_wait = AsyncMock(return_value=None)

        # Create a test event
        ts = datetime(2026, 5, 30, 14, 30, 0, tzinfo=timezone.utc)
        event = ComputedFeatureEvent(
            signal_id="regime_btc_v3",
            symbol="BTCUSDT",
            interval="1h",
            ts=ts,
            feature_vector={"rsi_14": 65.5, "macd": -0.25},
            feature_version="1.0.0",
        )

        async with KafkaProducerClient(bootstrap_servers="localhost:9092") as client:
            await client.publish(topic="features.computed", key="regime_btc_v3", event=event)

        # Verify send_and_wait was called with correct topic and serialized value
        mock_producer.send_and_wait.assert_called_once()
        call_args = mock_producer.send_and_wait.call_args
        assert call_args[1]["topic"] == "features.computed"
        assert call_args[1]["key"] == b"regime_btc_v3"

        # Verify value is JSON-encoded bytes
        value_bytes = call_args[1]["value"]
        assert isinstance(value_bytes, bytes)
        decoded_value = json.loads(value_bytes.decode())
        assert decoded_value["signal_id"] == "regime_btc_v3"
        assert decoded_value["symbol"] == "BTCUSDT"
        assert decoded_value["feature_version"] == "1.0.0"


@pytest.mark.asyncio
async def test_kafka_producer_publish_raises_on_failure():
    """Test that publish() raises exception when send_and_wait fails."""
    with patch('blackheart_ingest.services.kafka_producer.AIOKafkaProducer') as mock_producer_cls:
        mock_producer = AsyncMock()
        mock_producer_cls.return_value = mock_producer
        # Mock send_and_wait to raise an exception
        test_error = Exception("Kafka send failed")
        mock_producer.send_and_wait = AsyncMock(side_effect=test_error)

        ts = datetime(2026, 5, 30, 14, 30, 0, tzinfo=timezone.utc)
        event = ComputedFeatureEvent(
            signal_id="regime_btc_v3",
            symbol="BTCUSDT",
            interval="1h",
            ts=ts,
            feature_vector={"rsi_14": 65.5},
            feature_version="1.0.0",
        )

        async with KafkaProducerClient(bootstrap_servers="localhost:9092") as client:
            with pytest.raises(Exception):
                await client.publish(topic="features.computed", key="regime_btc_v3", event=event)
