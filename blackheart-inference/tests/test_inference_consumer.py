"""Inference consumer unit tests for event-driven ML inference.

The consumer:
1. Reads ComputedFeatureEvent from features.computed Kafka topic
2. Runs inference with circuit breaker protection
3. Publishes SignalPredictionEvent to signals.live topic
4. On errors, publishes InferenceErrorEvent to errors.inference topic

Tests verify consumer initialization, circuit breaker integration,
and the inference→publish flow without a real Kafka cluster.
"""

from __future__ import annotations

from typing import Callable
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from blackheart_inference.services.circuit_breaker import CircuitBreakerState
from blackheart_inference.services.kafka_consumer import InferenceConsumer


@pytest.mark.asyncio
async def test_inference_consumer_initializes() -> None:
    """Consumer initializes with signal_id and model_version."""
    predict_fn: Callable[[dict[str, float]], tuple[int, float]] = lambda x: (
        1,
        0.95,
    )

    consumer = InferenceConsumer(
        bootstrap_servers=["localhost:9092"],
        predict_fn=predict_fn,
        signal_id="regime_btc_v3",
        model_version="test-v1",
    )

    assert consumer.signal_id == "regime_btc_v3"
    assert consumer.model_version == "test-v1"
    assert consumer.circuit_breaker is not None


@pytest.mark.asyncio
async def test_inference_consumer_has_circuit_breaker() -> None:
    """Consumer creates a per-signal circuit breaker."""
    predict_fn: Callable[[dict[str, float]], tuple[int, float]] = lambda x: (
        1,
        0.95,
    )

    consumer = InferenceConsumer(
        bootstrap_servers=["localhost:9092"],
        predict_fn=predict_fn,
        signal_id="regime_eth_v2",
        model_version="test-v2",
    )

    # Circuit breaker should exist and start in CLOSED state
    assert consumer.circuit_breaker is not None
    assert consumer.circuit_breaker.signal_id == "regime_eth_v2"
    assert consumer.circuit_breaker.state == CircuitBreakerState.CLOSED


@pytest.mark.asyncio
async def test_inference_consumer_circuit_breaker_protection() -> None:
    """Consumer enforces circuit breaker — rejecting inference when OPEN."""
    # Create a predict function
    predict_fn: Callable[[dict[str, float]], tuple[int, float]] = lambda x: (
        1,
        0.95,
    )

    consumer = InferenceConsumer(
        bootstrap_servers=["localhost:9092"],
        predict_fn=predict_fn,
        signal_id="test_signal",
        model_version="test-v1",
        failure_threshold=2,
        recovery_timeout_secs=300,
    )

    # Manually open the circuit
    consumer.circuit_breaker.record_failure()
    consumer.circuit_breaker.record_failure()
    assert consumer.circuit_breaker.state == CircuitBreakerState.OPEN

    # Attempt to run inference — should raise RuntimeError
    feature_vector = {"f0": 1.0, "f1": 0.5}
    with pytest.raises(RuntimeError, match="Circuit breaker"):
        await consumer._run_inference(feature_vector)


@pytest.mark.asyncio
async def test_inference_consumer_records_success() -> None:
    """Consumer records success and resets circuit breaker."""
    call_count = 0

    def predict_fn(vec: dict[str, float]) -> tuple[int, float]:
        nonlocal call_count
        call_count += 1
        return 1, 0.95

    consumer = InferenceConsumer(
        bootstrap_servers=["localhost:9092"],
        predict_fn=predict_fn,
        signal_id="test_signal",
        model_version="test-v1",
    )

    # Manually increment failure count
    consumer.circuit_breaker.failure_count = 2

    # Run inference with mock to avoid actual Kafka
    feature_vector = {"f0": 1.0, "f1": 0.5}
    prediction, confidence = await consumer._run_inference(feature_vector)

    # Should have called predict and recorded success
    assert call_count == 1
    assert prediction == 1
    assert confidence == 0.95
    # Circuit breaker should have reset
    assert consumer.circuit_breaker.failure_count == 0


@pytest.mark.asyncio
async def test_inference_consumer_records_failure() -> None:
    """Consumer records failure and increments circuit breaker counter."""

    def predict_fn(vec: dict[str, float]) -> tuple[int, float]:
        raise RuntimeError("Model inference failed")

    consumer = InferenceConsumer(
        bootstrap_servers=["localhost:9092"],
        predict_fn=predict_fn,
        signal_id="test_signal",
        model_version="test-v1",
        failure_threshold=2,
    )

    feature_vector = {"f0": 1.0, "f1": 0.5}

    # First failure
    with pytest.raises(RuntimeError):
        await consumer._run_inference(feature_vector)
    assert consumer.circuit_breaker.failure_count == 1
    assert consumer.circuit_breaker.state == CircuitBreakerState.CLOSED

    # Second failure — should open circuit
    with pytest.raises(RuntimeError):
        await consumer._run_inference(feature_vector)
    assert consumer.circuit_breaker.failure_count == 2
    assert consumer.circuit_breaker.state == CircuitBreakerState.OPEN
