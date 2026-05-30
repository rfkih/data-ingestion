"""
Pydantic event schemas for Kafka topics in the event-driven ML pipeline.

These schemas define the structure of events published to 5 Kafka topics:
- market.bars: OHLCV market data from trading JVM
- features.computed: Feature vectors from stream processor
- signals.live: ML predictions from inference
- errors.inference: Inference failures and circuit breaker states
- models.deployed: Model deployment/canary state changes
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class CircuitBreakerState(str, Enum):
    """Circuit breaker states for inference failures."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class MarketBarEvent(BaseModel):
    """
    OHLCV market bar from trading JVM, published to market.bars topic.

    Represents a single candle (bar) of market data for a symbol at a
    specific timestamp. Published by the trading JVM at the end of each
    interval (1h, 4h, 1d, etc.).
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "symbol": "BTCUSDT",
                "ts": "2026-05-30T14:30:45.123456Z",
                "open": 45000.50,
                "high": 45500.75,
                "low": 44999.00,
                "close": 45250.25,
                "volume": 1500000.0,
            }
        }
    )

    symbol: str = Field(..., description="Trading pair symbol (e.g., BTCUSDT)")
    ts: datetime = Field(..., description="Bar timestamp (UTC)")
    open: float = Field(..., description="Opening price")
    high: float = Field(..., description="Highest price in period")
    low: float = Field(..., description="Lowest price in period")
    close: float = Field(..., description="Closing price")
    volume: float = Field(..., description="Trade volume in base asset")


class ComputedFeatureEvent(BaseModel):
    """
    Feature vector computed from market data, published to features.computed.

    Contains the full set of features computed by the feature stream processor
    for a given signal, symbol, and interval. Features are stored as a
    dictionary of feature name → value (float).
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "signal_id": "regime_btc_v3",
                "symbol": "BTCUSDT",
                "interval": "1h",
                "ts": "2026-05-30T14:30:00Z",
                "feature_vector": {
                    "rsi_14": 65.5,
                    "macd": -0.25,
                    "bb_upper": 45600.0,
                    "bb_lower": 44400.0,
                },
                "feature_version": "1.0.0",
            }
        }
    )

    signal_id: str = Field(..., description="ML signal identifier (e.g., regime_btc_v3)")
    symbol: str = Field(..., description="Trading pair symbol (e.g., BTCUSDT)")
    interval: str = Field(..., description="Candle interval (1h, 4h, 1d, etc.)")
    ts: datetime = Field(..., description="Feature computation timestamp (UTC)")
    feature_vector: dict[str, float] = Field(
        ..., description="Dictionary of feature name → float value"
    )
    feature_version: str = Field(..., description="Feature definition version (e.g., 1.0.0)")


class SignalPredictionEvent(BaseModel):
    """
    ML prediction from inference engine, published to signals.live.

    Contains a single prediction from a trained ML model (e.g., regime_btc_v3),
    along with confidence score and latency metrics. Latency is useful for
    monitoring inference performance and circuit breaker decisions.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "signal_id": "regime_btc_v3",
                "symbol": "BTCUSDT",
                "interval": "1h",
                "ts": "2026-05-30T14:31:15Z",
                "prediction": 1,
                "confidence": 0.87,
                "model_version": "69619e36-4e14-4a28-b1c4-fbdb7ac8a7ca",
                "latency_ms": 42,
            }
        }
    )

    signal_id: str = Field(..., description="ML signal identifier (e.g., regime_btc_v3)")
    symbol: str = Field(..., description="Trading pair symbol (e.g., BTCUSDT)")
    interval: str = Field(..., description="Candle interval (1h, 4h, 1d, etc.)")
    ts: datetime = Field(..., description="Prediction timestamp (UTC)")
    prediction: int = Field(..., description="Model output (typically 0 or 1 for binary)")
    confidence: float = Field(
        ..., description="Prediction confidence (0.0 to 1.0)", ge=0.0, le=1.0
    )
    model_version: str = Field(
        ..., description="Model version identifier (UUID or semantic version)"
    )
    latency_ms: int = Field(
        ..., description="Model inference latency in milliseconds", ge=0
    )


class InferenceErrorEvent(BaseModel):
    """
    Inference failure or circuit breaker state change, published to errors.inference.

    Emitted when an inference request fails (timeout, OOM, model error, etc.)
    or when the circuit breaker transitions between states (closed → open,
    half_open → closed, etc.). Used for monitoring, alerting, and fallback
    decision-making.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "signal_id": "regime_btc_v3",
                "symbol": "BTCUSDT",
                "ts": "2026-05-30T14:32:30Z",
                "error_type": "inference_timeout",
                "error_message": "Model inference exceeded 5s timeout",
                "circuit_breaker_state": "open",
            }
        }
    )

    signal_id: str = Field(..., description="ML signal identifier (e.g., regime_btc_v3)")
    symbol: str = Field(..., description="Trading pair symbol (e.g., BTCUSDT)")
    ts: datetime = Field(..., description="Error timestamp (UTC)")
    error_type: str = Field(
        ..., description="Error category (inference_timeout, oom, model_error, etc.)"
    )
    error_message: str = Field(..., description="Human-readable error description")
    circuit_breaker_state: CircuitBreakerState = Field(
        ..., description="Circuit breaker state after error (closed, open, half_open)"
    )


class ModelDeploymentEvent(BaseModel):
    """
    Model deployment or canary state change, published to models.deployed.

    Emitted when a new model version is deployed (fully or as a canary),
    or when a canary percentage is adjusted. Consumers can use this to
    route a percentage of inference requests to the new model for A/B testing.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "model_version": "69619e36-4e14-4a28-b1c4-fbdb7ac8a7ca",
                "signal_id": "regime_btc_v3",
                "deployment_type": "canary",
                "canary_percentage": 15,
                "fallback_model_version": "62bc99f1-3d1c-4a18-a1c3-edbf7ac8a7cb",
            }
        }
    )

    model_version: str = Field(
        ..., description="New model version identifier (UUID or semantic version)"
    )
    signal_id: str = Field(..., description="ML signal identifier (e.g., regime_btc_v3)")
    deployment_type: str = Field(
        ..., description="Deployment strategy (stable, canary, rollback, etc.)"
    )
    canary_percentage: int = Field(
        ..., description="Percentage of traffic to new model (0-100)", ge=0, le=100
    )
    fallback_model_version: Optional[str] = Field(
        None, description="Previous model version for fallback (if canary fails)"
    )
