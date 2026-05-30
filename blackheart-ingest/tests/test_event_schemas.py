"""
Test suite for Kafka event schemas.

Tests verify that all 5 event types serialize correctly to JSON with
ISO8601 timestamps and include required fields.
"""

import json
from datetime import datetime, timezone

import pytest

from blackheart_ingest.schemas.events import (
    MarketBarEvent,
    ComputedFeatureEvent,
    SignalPredictionEvent,
    InferenceErrorEvent,
    ModelDeploymentEvent,
    CircuitBreakerState,
)


class TestMarketBarEvent:
    """Test OHLCV market bar events."""

    def test_market_bar_serialization(self):
        """MarketBarEvent should serialize with ISO8601 timestamp."""
        ts = datetime(2026, 5, 30, 14, 30, 45, 123456, tzinfo=timezone.utc)
        event = MarketBarEvent(
            symbol="BTCUSDT",
            interval="1h",
            ts=ts,
            open=45000.50,
            high=45500.75,
            low=44999.00,
            close=45250.25,
            volume=1500000.0,
        )

        json_data = json.loads(event.model_dump_json())

        assert json_data["symbol"] == "BTCUSDT"
        assert json_data["open"] == 45000.50
        assert json_data["high"] == 45500.75
        assert json_data["low"] == 44999.00
        assert json_data["close"] == 45250.25
        assert json_data["volume"] == 1500000.0
        # ISO8601 timestamp validation (Pydantic uses Z suffix for UTC)
        assert json_data["ts"] == "2026-05-30T14:30:45.123456Z"

    def test_market_bar_fields_required(self):
        """MarketBarEvent requires all fields."""
        ts = datetime(2026, 5, 30, 14, 30, 45, tzinfo=timezone.utc)
        with pytest.raises(Exception):  # Pydantic ValidationError
            MarketBarEvent(
                symbol="BTCUSDT",
                interval="1h",
                ts=ts,
                open=45000.50,
                high=45500.75,
                low=44999.00,
                # Missing close and volume
            )


class TestComputedFeatureEvent:
    """Test computed feature vector events."""

    def test_computed_feature_serialization(self):
        """ComputedFeatureEvent should serialize with ISO8601 timestamp."""
        ts = datetime(2026, 5, 30, 14, 30, 0, tzinfo=timezone.utc)
        feature_vector = {
            "rsi_14": 65.5,
            "macd": -0.25,
            "bb_upper": 45600.0,
            "bb_lower": 44400.0,
        }
        event = ComputedFeatureEvent(
            signal_id="regime_btc_v3",
            symbol="BTCUSDT",
            interval="1h",
            ts=ts,
            feature_vector=feature_vector,
            feature_version="1.0.0",
        )

        json_data = json.loads(event.model_dump_json())

        assert json_data["signal_id"] == "regime_btc_v3"
        assert json_data["symbol"] == "BTCUSDT"
        assert json_data["interval"] == "1h"
        assert json_data["feature_version"] == "1.0.0"
        assert json_data["feature_vector"] == feature_vector
        assert json_data["ts"] == "2026-05-30T14:30:00Z"

    def test_computed_feature_vector_is_dict(self):
        """ComputedFeatureEvent feature_vector must be a dict."""
        ts = datetime(2026, 5, 30, 14, 30, 0, tzinfo=timezone.utc)
        event = ComputedFeatureEvent(
            signal_id="regime_btc_v3",
            symbol="BTCUSDT",
            interval="1h",
            ts=ts,
            feature_vector={"rsi": 65.5},
            feature_version="1.0.0",
        )
        assert isinstance(event.feature_vector, dict)


class TestSignalPredictionEvent:
    """Test ML signal prediction events."""

    def test_signal_prediction_serialization(self):
        """SignalPredictionEvent should serialize with all fields."""
        ts = datetime(2026, 5, 30, 14, 31, 15, tzinfo=timezone.utc)
        event = SignalPredictionEvent(
            signal_id="regime_btc_v3",
            symbol="BTCUSDT",
            interval="1h",
            ts=ts,
            prediction=1,
            confidence=0.87,
            model_version="69619e36-4e14-4a28-b1c4-fbdb7ac8a7ca",
            latency_ms=42,
        )

        json_data = json.loads(event.model_dump_json())

        assert json_data["signal_id"] == "regime_btc_v3"
        assert json_data["symbol"] == "BTCUSDT"
        assert json_data["interval"] == "1h"
        assert json_data["prediction"] == 1
        assert json_data["confidence"] == 0.87
        assert json_data["model_version"] == "69619e36-4e14-4a28-b1c4-fbdb7ac8a7ca"
        assert json_data["latency_ms"] == 42
        assert json_data["ts"] == "2026-05-30T14:31:15Z"

    def test_signal_prediction_confidence_bounds(self):
        """SignalPredictionEvent confidence must be between 0.0 and 1.0."""
        ts = datetime(2026, 5, 30, 14, 31, 15, tzinfo=timezone.utc)
        # Should accept 0.0 and 1.0
        event = SignalPredictionEvent(
            signal_id="regime_btc_v3",
            symbol="BTCUSDT",
            interval="1h",
            ts=ts,
            prediction=1,
            confidence=1.0,
            model_version="test-model",
            latency_ms=10,
        )
        assert event.confidence == 1.0


class TestInferenceErrorEvent:
    """Test inference error/circuit breaker events."""

    def test_inference_error_serialization(self):
        """InferenceErrorEvent should serialize with circuit breaker state."""
        ts = datetime(2026, 5, 30, 14, 32, 30, tzinfo=timezone.utc)
        event = InferenceErrorEvent(
            signal_id="regime_btc_v3",
            symbol="BTCUSDT",
            ts=ts,
            error_type="inference_timeout",
            error_message="Model inference exceeded 5s timeout",
            circuit_breaker_state=CircuitBreakerState.OPEN,
        )

        json_data = json.loads(event.model_dump_json())

        assert json_data["signal_id"] == "regime_btc_v3"
        assert json_data["symbol"] == "BTCUSDT"
        assert json_data["error_type"] == "inference_timeout"
        assert json_data["error_message"] == "Model inference exceeded 5s timeout"
        assert json_data["circuit_breaker_state"] == "open"
        assert json_data["ts"] == "2026-05-30T14:32:30Z"

    def test_circuit_breaker_state_enum(self):
        """CircuitBreakerState should have three values."""
        assert CircuitBreakerState.CLOSED.value == "closed"
        assert CircuitBreakerState.OPEN.value == "open"
        assert CircuitBreakerState.HALF_OPEN.value == "half_open"

    def test_inference_error_with_different_states(self):
        """InferenceErrorEvent should accept all circuit breaker states."""
        ts = datetime(2026, 5, 30, 14, 32, 30, tzinfo=timezone.utc)
        for state in [
            CircuitBreakerState.CLOSED,
            CircuitBreakerState.OPEN,
            CircuitBreakerState.HALF_OPEN,
        ]:
            event = InferenceErrorEvent(
                signal_id="test",
                symbol="BTCUSDT",
                ts=ts,
                error_type="test",
                error_message="test error",
                circuit_breaker_state=state,
            )
            assert event.circuit_breaker_state == state


class TestModelDeploymentEvent:
    """Test model deployment/canary events."""

    def test_model_deployment_serialization(self):
        """ModelDeploymentEvent should serialize with all fields."""
        event = ModelDeploymentEvent(
            model_version="69619e36-4e14-4a28-b1c4-fbdb7ac8a7ca",
            signal_id="regime_btc_v3",
            deployment_type="canary",
            canary_percentage=15,
            fallback_model_version="62bc99f1-3d1c-4a18-a1c3-edbf7ac8a7cb",
        )

        json_data = json.loads(event.model_dump_json())

        assert json_data["model_version"] == "69619e36-4e14-4a28-b1c4-fbdb7ac8a7ca"
        assert json_data["signal_id"] == "regime_btc_v3"
        assert json_data["deployment_type"] == "canary"
        assert json_data["canary_percentage"] == 15
        assert json_data["fallback_model_version"] == "62bc99f1-3d1c-4a18-a1c3-edbf7ac8a7cb"

    def test_model_deployment_without_fallback(self):
        """ModelDeploymentEvent fallback_model_version is optional."""
        event = ModelDeploymentEvent(
            model_version="69619e36-4e14-4a28-b1c4-fbdb7ac8a7ca",
            signal_id="regime_btc_v3",
            deployment_type="stable",
            canary_percentage=100,
        )

        json_data = json.loads(event.model_dump_json())

        assert json_data["fallback_model_version"] is None

    def test_model_deployment_canary_percentage_bounds(self):
        """ModelDeploymentEvent canary_percentage must be 0-100."""
        # Valid boundaries
        event = ModelDeploymentEvent(
            model_version="test",
            signal_id="test",
            deployment_type="canary",
            canary_percentage=0,
        )
        assert event.canary_percentage == 0

        event = ModelDeploymentEvent(
            model_version="test",
            signal_id="test",
            deployment_type="canary",
            canary_percentage=100,
        )
        assert event.canary_percentage == 100
