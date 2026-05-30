"""Test feature store with versioning and lineage tracking.

Tests for:
- FeatureStore: register schema, store features with version validation, retrieve by version
- Feature lineage and schema consistency
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from blackheart_inference.models.feature_store import FeatureStore


class TestFeatureStoreSchemaRegistration:
    """Test feature schema registration."""

    def test_register_schema_stores_feature_names(self) -> None:
        """Register schema with version and feature names."""
        store = FeatureStore()
        version = "v1"
        feature_names = ["momentum", "rsi", "macd"]

        store.register_schema(version=version, feature_names=feature_names)

        schema = store.get_schema(version)
        assert schema is not None
        assert schema["feature_names"] == feature_names

    def test_register_multiple_schema_versions(self) -> None:
        """Register multiple schema versions."""
        store = FeatureStore()

        store.register_schema(version="v1", feature_names=["momentum", "rsi"])
        store.register_schema(version="v2", feature_names=["momentum", "rsi", "macd"])

        schema_v1 = store.get_schema("v1")
        schema_v2 = store.get_schema("v2")

        assert schema_v1["feature_names"] == ["momentum", "rsi"]
        assert schema_v2["feature_names"] == ["momentum", "rsi", "macd"]

    def test_get_nonexistent_schema_returns_none(self) -> None:
        """Getting non-registered schema returns None."""
        store = FeatureStore()
        schema = store.get_schema("nonexistent")
        assert schema is None


class TestFeatureStoreStorage:
    """Test storing and retrieving features."""

    def test_store_features_with_registered_schema(self) -> None:
        """Store features matching registered schema."""
        store = FeatureStore()
        version = "v1"
        store.register_schema(version=version, feature_names=["momentum", "rsi"])

        signal_id = "regime_btc_v3"
        symbol = "BTCUSDT"
        ts = int(datetime.now(UTC).timestamp())
        features = {"momentum": 0.75, "rsi": 65.5}

        store.store_features(
            signal_id=signal_id,
            symbol=symbol,
            ts=ts,
            features=features,
            feature_version=version,
        )

        # Verify stored
        retrieved = store.get_features(signal_id=signal_id, symbol=symbol)
        assert retrieved is not None
        assert retrieved["momentum"] == 0.75
        assert retrieved["rsi"] == 65.5

    def test_store_features_validates_schema_consistency(self) -> None:
        """Storing features with wrong names raises ValueError."""
        store = FeatureStore()
        version = "v1"
        store.register_schema(version=version, feature_names=["momentum", "rsi"])

        signal_id = "regime_btc_v3"
        symbol = "BTCUSDT"
        ts = int(datetime.now(UTC).timestamp())
        features = {"momentum": 0.75, "invalid_feature": 65.5}

        with pytest.raises(
            ValueError,
            match="Feature names do not match schema",
        ):
            store.store_features(
                signal_id=signal_id,
                symbol=symbol,
                ts=ts,
                features=features,
                feature_version=version,
            )

    def test_store_features_missing_required_features_raises(self) -> None:
        """Storing features missing required fields raises ValueError."""
        store = FeatureStore()
        version = "v1"
        store.register_schema(version=version, feature_names=["momentum", "rsi"])

        signal_id = "regime_btc_v3"
        symbol = "BTCUSDT"
        ts = int(datetime.now(UTC).timestamp())
        features = {"momentum": 0.75}  # Missing 'rsi'

        with pytest.raises(
            ValueError,
            match="Feature names do not match schema",
        ):
            store.store_features(
                signal_id=signal_id,
                symbol=symbol,
                ts=ts,
                features=features,
                feature_version=version,
            )

    def test_store_features_without_registered_schema_raises(self) -> None:
        """Storing with unregistered version raises ValueError."""
        store = FeatureStore()

        signal_id = "regime_btc_v3"
        symbol = "BTCUSDT"
        ts = int(datetime.now(UTC).timestamp())
        features = {"momentum": 0.75, "rsi": 65.5}

        with pytest.raises(
            ValueError,
            match="Schema version .* not registered",
        ):
            store.store_features(
                signal_id=signal_id,
                symbol=symbol,
                ts=ts,
                features=features,
                feature_version="unregistered",
            )


class TestFeatureStoreRetrieval:
    """Test retrieving features."""

    def test_get_features_returns_latest(self) -> None:
        """get_features returns the most recent features for signal/symbol."""
        store = FeatureStore()
        version = "v1"
        store.register_schema(version=version, feature_names=["momentum", "rsi"])

        signal_id = "regime_btc_v3"
        symbol = "BTCUSDT"

        # Store first version
        ts1 = 1000
        store.store_features(
            signal_id=signal_id,
            symbol=symbol,
            ts=ts1,
            features={"momentum": 0.50, "rsi": 50.0},
            feature_version=version,
        )

        # Store second version (newer)
        ts2 = 2000
        store.store_features(
            signal_id=signal_id,
            symbol=symbol,
            ts=ts2,
            features={"momentum": 0.75, "rsi": 65.5},
            feature_version=version,
        )

        retrieved = store.get_features(signal_id=signal_id, symbol=symbol)
        assert retrieved["momentum"] == 0.75  # Latest
        assert retrieved["rsi"] == 65.5

    def test_get_features_nonexistent_returns_none(self) -> None:
        """get_features returns None if no features stored."""
        store = FeatureStore()
        retrieved = store.get_features(
            signal_id="nonexistent", symbol="BTCUSDT"
        )
        assert retrieved is None

    def test_get_features_includes_metadata(self) -> None:
        """Retrieved features include timestamp and version metadata."""
        store = FeatureStore()
        version = "v1"
        store.register_schema(version=version, feature_names=["momentum", "rsi"])

        signal_id = "regime_btc_v3"
        symbol = "BTCUSDT"
        ts = 1234567890
        features = {"momentum": 0.75, "rsi": 65.5}

        store.store_features(
            signal_id=signal_id,
            symbol=symbol,
            ts=ts,
            features=features,
            feature_version=version,
        )

        retrieved = store.get_features(signal_id=signal_id, symbol=symbol)
        assert retrieved["__ts__"] == ts
        assert retrieved["__version__"] == version


class TestFeatureStoreLineage:
    """Test feature lineage tracking."""

    def test_get_feature_lineage_by_version(self) -> None:
        """get_feature_lineage returns features matching specific schema version."""
        store = FeatureStore()

        # Register v1 and v2 schemas
        store.register_schema(
            version="v1", feature_names=["momentum", "rsi"]
        )
        store.register_schema(
            version="v2", feature_names=["momentum", "rsi", "macd"]
        )

        signal_id = "regime_btc_v3"
        symbol = "BTCUSDT"

        # Store v1 features
        store.store_features(
            signal_id=signal_id,
            symbol=symbol,
            ts=1000,
            features={"momentum": 0.50, "rsi": 50.0},
            feature_version="v1",
        )

        # Store v2 features
        store.store_features(
            signal_id=signal_id,
            symbol=symbol,
            ts=2000,
            features={"momentum": 0.75, "rsi": 65.5, "macd": 0.10},
            feature_version="v2",
        )

        # Retrieve by specific version
        lineage_v1 = store.get_feature_lineage(
            signal_id=signal_id, symbol=symbol, feature_version="v1"
        )
        lineage_v2 = store.get_feature_lineage(
            signal_id=signal_id, symbol=symbol, feature_version="v2"
        )

        assert lineage_v1 is not None
        assert lineage_v1["__version__"] == "v1"
        assert "macd" not in lineage_v1

        assert lineage_v2 is not None
        assert lineage_v2["__version__"] == "v2"
        assert lineage_v2["macd"] == 0.10

    def test_get_feature_lineage_nonexistent_returns_none(self) -> None:
        """get_feature_lineage returns None if no features with version exist."""
        store = FeatureStore()
        store.register_schema(version="v1", feature_names=["momentum", "rsi"])

        lineage = store.get_feature_lineage(
            signal_id="nonexistent",
            symbol="BTCUSDT",
            feature_version="v1",
        )
        assert lineage is None

    def test_feature_lineage_reproducibility(self) -> None:
        """Features can be reproduced by pinning feature version."""
        store = FeatureStore()

        store.register_schema(version="v1", feature_names=["momentum", "rsi"])
        store.register_schema(
            version="v2", feature_names=["momentum", "rsi", "macd"]
        )

        signal_id = "regime_btc_v3"
        symbol = "BTCUSDT"

        # Store different versions at same timestamp
        ts = 1500
        store.store_features(
            signal_id=signal_id,
            symbol=symbol,
            ts=ts,
            features={"momentum": 0.50, "rsi": 50.0},
            feature_version="v1",
        )

        # Later, store v2 with additional features
        store.store_features(
            signal_id=signal_id,
            symbol=symbol,
            ts=ts,  # Same timestamp
            features={"momentum": 0.50, "rsi": 50.0, "macd": 0.05},
            feature_version="v2",
        )

        # Lineage should be reproducible
        v1_lineage = store.get_feature_lineage(
            signal_id=signal_id,
            symbol=symbol,
            feature_version="v1",
        )
        v2_lineage = store.get_feature_lineage(
            signal_id=signal_id,
            symbol=symbol,
            feature_version="v2",
        )

        assert v1_lineage["momentum"] == v2_lineage["momentum"]
        assert v1_lineage["rsi"] == v2_lineage["rsi"]
        assert "macd" not in v1_lineage
        assert v2_lineage["macd"] == 0.05


class TestFeatureStoreMultipleSignals:
    """Test storing features for multiple signals/symbols."""

    def test_store_features_multiple_signals(self) -> None:
        """Store features for different signals independently."""
        store = FeatureStore()
        version = "v1"
        store.register_schema(
            version=version, feature_names=["momentum", "rsi"]
        )

        # Store for signal 1
        store.store_features(
            signal_id="regime_btc_v3",
            symbol="BTCUSDT",
            ts=1000,
            features={"momentum": 0.50, "rsi": 50.0},
            feature_version=version,
        )

        # Store for signal 2
        store.store_features(
            signal_id="flow_eth_v2",
            symbol="ETHUSDT",
            ts=1000,
            features={"momentum": 0.60, "rsi": 60.0},
            feature_version=version,
        )

        # Retrieve independently
        btc_features = store.get_features(
            signal_id="regime_btc_v3", symbol="BTCUSDT"
        )
        eth_features = store.get_features(
            signal_id="flow_eth_v2", symbol="ETHUSDT"
        )

        assert btc_features["momentum"] == 0.50
        assert eth_features["momentum"] == 0.60

    def test_store_features_multiple_symbols_same_signal(self) -> None:
        """Store features for same signal across different symbols."""
        store = FeatureStore()
        version = "v1"
        store.register_schema(
            version=version, feature_names=["momentum", "rsi"]
        )

        signal_id = "regime_btc_v3"

        # Store for BTC
        store.store_features(
            signal_id=signal_id,
            symbol="BTCUSDT",
            ts=1000,
            features={"momentum": 0.50, "rsi": 50.0},
            feature_version=version,
        )

        # Store for ETH
        store.store_features(
            signal_id=signal_id,
            symbol="ETHUSDT",
            ts=1000,
            features={"momentum": 0.60, "rsi": 60.0},
            feature_version=version,
        )

        # Retrieve independently
        btc_features = store.get_features(signal_id=signal_id, symbol="BTCUSDT")
        eth_features = store.get_features(signal_id=signal_id, symbol="ETHUSDT")

        assert btc_features["momentum"] == 0.50
        assert eth_features["momentum"] == 0.60
