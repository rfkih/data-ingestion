"""Test model registry and canary deployment functionality.

Tests for:
- ModelRegistry: register, get, deploy, retire models
- CanaryDeployer: choose model for canary/fallback routing, promote, rollback
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

import pytest

from blackheart_inference.models.model_registry import (
    DeploymentType,
    ModelRegistry,
)
from blackheart_inference.models.canary_deployment import CanaryDeployer


class TestDeploymentType:
    """Test DeploymentType enum."""

    def test_deployment_type_full_exists(self) -> None:
        assert DeploymentType.FULL.value == "FULL"

    def test_deployment_type_canary_exists(self) -> None:
        assert DeploymentType.CANARY.value == "CANARY"


class TestModelRegistry:
    """Test ModelRegistry class."""

    def test_register_model_stores_metadata(self) -> None:
        registry = ModelRegistry()
        model_id = "model-001"
        signal_id = "regime_btc_v3"
        artifact_path = "/path/to/artifact.pkl"
        feature_version = "v1"

        registry.register_model(
            model_id=model_id,
            signal_id=signal_id,
            artifact_path=artifact_path,
            feature_version=feature_version,
        )

        model = registry.get_model(model_id)
        assert model is not None
        assert model["model_id"] == model_id
        assert model["signal_id"] == signal_id
        assert model["artifact_path"] == artifact_path
        assert model["feature_version"] == feature_version

    def test_register_model_with_metrics(self) -> None:
        registry = ModelRegistry()
        model_id = "model-002"
        metrics = {
            "auc": 0.85,
            "logloss": 0.42,
            "win_rate": 0.55,
        }

        registry.register_model(
            model_id=model_id,
            signal_id="regime_btc_v3",
            artifact_path="/path/to/artifact.pkl",
            feature_version="v1",
            metrics=metrics,
        )

        model = registry.get_model(model_id)
        assert model["metrics"] == metrics

    def test_register_model_without_metrics_defaults_to_empty_dict(self) -> None:
        registry = ModelRegistry()
        registry.register_model(
            model_id="model-003",
            signal_id="regime_btc_v3",
            artifact_path="/path/to/artifact.pkl",
            feature_version="v1",
        )

        model = registry.get_model("model-003")
        assert model["metrics"] == {}

    def test_get_nonexistent_model_returns_none(self) -> None:
        registry = ModelRegistry()
        model = registry.get_model("nonexistent")
        assert model is None

    def test_deploy_full_deployment(self) -> None:
        registry = ModelRegistry()
        model_id = "model-004"
        registry.register_model(
            model_id=model_id,
            signal_id="regime_btc_v3",
            artifact_path="/path/to/artifact.pkl",
            feature_version="v1",
        )

        registry.deploy(
            model_id=model_id,
            deployment_type=DeploymentType.FULL,
        )

        deployment = registry.get_deployment(model_id)
        assert deployment is not None
        assert deployment["deployment_type"] == DeploymentType.FULL
        assert deployment["canary_percentage"] == 0

    def test_deploy_canary_deployment_with_percentage(self) -> None:
        registry = ModelRegistry()
        model_id = "model-005"
        fallback_model_id = "model-004"

        registry.register_model(
            model_id=model_id,
            signal_id="regime_btc_v3",
            artifact_path="/path/to/artifact.pkl",
            feature_version="v1",
        )
        registry.register_model(
            model_id=fallback_model_id,
            signal_id="regime_btc_v3",
            artifact_path="/path/to/fallback.pkl",
            feature_version="v1",
        )

        registry.deploy(
            model_id=model_id,
            deployment_type=DeploymentType.CANARY,
            canary_percentage=10,
            fallback_model_id=fallback_model_id,
        )

        deployment = registry.get_deployment(model_id)
        assert deployment["deployment_type"] == DeploymentType.CANARY
        assert deployment["canary_percentage"] == 10
        assert deployment["fallback_model_id"] == fallback_model_id

    def test_deploy_canary_without_fallback_raises(self) -> None:
        registry = ModelRegistry()
        model_id = "model-006"
        registry.register_model(
            model_id=model_id,
            signal_id="regime_btc_v3",
            artifact_path="/path/to/artifact.pkl",
            feature_version="v1",
        )

        with pytest.raises(
            ValueError,
            match="CANARY deployment requires fallback_model_id",
        ):
            registry.deploy(
                model_id=model_id,
                deployment_type=DeploymentType.CANARY,
                canary_percentage=10,
            )

    def test_deploy_canary_percentage_zero_raises(self) -> None:
        registry = ModelRegistry()
        model_id = "model-007"
        fallback_model_id = "model-008"

        registry.register_model(
            model_id=model_id,
            signal_id="regime_btc_v3",
            artifact_path="/path/to/artifact.pkl",
            feature_version="v1",
        )
        registry.register_model(
            model_id=fallback_model_id,
            signal_id="regime_btc_v3",
            artifact_path="/path/to/fallback.pkl",
            feature_version="v1",
        )

        with pytest.raises(
            ValueError,
            match="CANARY deployment requires canary_percentage",
        ):
            registry.deploy(
                model_id=model_id,
                deployment_type=DeploymentType.CANARY,
                canary_percentage=0,
                fallback_model_id=fallback_model_id,
            )

    def test_get_deployment_nonexistent_returns_none(self) -> None:
        registry = ModelRegistry()
        deployment = registry.get_deployment("nonexistent")
        assert deployment is None

    def test_retire_model_marks_as_retired(self) -> None:
        registry = ModelRegistry()
        model_id = "model-009"
        registry.register_model(
            model_id=model_id,
            signal_id="regime_btc_v3",
            artifact_path="/path/to/artifact.pkl",
            feature_version="v1",
        )

        registry.retire_model(model_id)

        model = registry.get_model(model_id)
        assert model["status"] == "retired"

    def test_retire_nonexistent_model_raises(self) -> None:
        registry = ModelRegistry()
        with pytest.raises(ValueError, match="Model .* not found"):
            registry.retire_model("nonexistent")

    def test_register_model_timestamped(self) -> None:
        registry = ModelRegistry()
        model_id = "model-010"

        before = datetime.now(UTC)
        registry.register_model(
            model_id=model_id,
            signal_id="regime_btc_v3",
            artifact_path="/path/to/artifact.pkl",
            feature_version="v1",
        )
        after = datetime.now(UTC)

        model = registry.get_model(model_id)
        registered_at = datetime.fromisoformat(model["registered_at"])
        assert before <= registered_at <= after

    def test_deploy_updates_deployment_timestamp(self) -> None:
        registry = ModelRegistry()
        model_id = "model-011"
        registry.register_model(
            model_id=model_id,
            signal_id="regime_btc_v3",
            artifact_path="/path/to/artifact.pkl",
            feature_version="v1",
        )

        before = datetime.now(UTC)
        registry.deploy(
            model_id=model_id,
            deployment_type=DeploymentType.FULL,
        )
        after = datetime.now(UTC)

        deployment = registry.get_deployment(model_id)
        deployed_at = datetime.fromisoformat(deployment["deployed_at"])
        assert before <= deployed_at <= after


class TestCanaryDeployer:
    """Test CanaryDeployer class."""

    def test_choose_model_full_deployment_returns_primary(self) -> None:
        registry = ModelRegistry()
        primary_id = "model-primary"
        fallback_id = "model-fallback"

        registry.register_model(
            model_id=primary_id,
            signal_id="regime_btc_v3",
            artifact_path="/path/to/primary.pkl",
            feature_version="v1",
        )
        registry.register_model(
            model_id=fallback_id,
            signal_id="regime_btc_v3",
            artifact_path="/path/to/fallback.pkl",
            feature_version="v1",
        )
        registry.deploy(
            model_id=primary_id,
            deployment_type=DeploymentType.FULL,
        )

        deployer = CanaryDeployer(registry)
        chosen = deployer.choose_model("regime_btc_v3", primary_id)
        assert chosen == primary_id

    def test_choose_model_canary_routes_to_fallback_based_on_percentage(self) -> None:
        """Test that canary percentage routing works correctly."""
        registry = ModelRegistry()
        primary_id = "model-canary"
        fallback_id = "model-fallback"

        registry.register_model(
            model_id=primary_id,
            signal_id="regime_btc_v3",
            artifact_path="/path/to/canary.pkl",
            feature_version="v1",
        )
        registry.register_model(
            model_id=fallback_id,
            signal_id="regime_btc_v3",
            artifact_path="/path/to/fallback.pkl",
            feature_version="v1",
        )
        registry.deploy(
            model_id=primary_id,
            deployment_type=DeploymentType.CANARY,
            canary_percentage=10,
            fallback_model_id=fallback_id,
        )

        deployer = CanaryDeployer(registry)

        # With 10% canary, we should see some traffic to canary and some to fallback
        # In this test, we just verify the logic is working (deterministic hash-based routing)
        # Make multiple calls with the same signal_id and expect routing consistency
        results = []
        for i in range(100):
            # Use deterministic seed to simulate multiple requests
            chosen = deployer.choose_model(
                "regime_btc_v3", primary_id, request_id=f"req-{i:03d}"
            )
            results.append(chosen)

        # Should have traffic to both models
        assert primary_id in results or fallback_id in results
        # With 10% canary, we expect approximately 10% primary and 90% fallback
        primary_count = results.count(primary_id)
        # Allow for some variance in small sample
        canary_rate = primary_count / len(results)
        assert 0 < canary_rate <= 0.20, f"Canary rate {canary_rate} not in expected range"

    def test_choose_model_canary_high_percentage_mostly_primary(self) -> None:
        registry = ModelRegistry()
        primary_id = "model-high-canary"
        fallback_id = "model-fallback"

        registry.register_model(
            model_id=primary_id,
            signal_id="regime_btc_v3",
            artifact_path="/path/to/canary.pkl",
            feature_version="v1",
        )
        registry.register_model(
            model_id=fallback_id,
            signal_id="regime_btc_v3",
            artifact_path="/path/to/fallback.pkl",
            feature_version="v1",
        )
        registry.deploy(
            model_id=primary_id,
            deployment_type=DeploymentType.CANARY,
            canary_percentage=99,
            fallback_model_id=fallback_id,
        )

        deployer = CanaryDeployer(registry)
        # Most requests should go to primary with 99% canary
        results = []
        for i in range(100):
            chosen = deployer.choose_model(
                "regime_btc_v3", primary_id, request_id=f"req-{i:03d}"
            )
            results.append(chosen)

        primary_count = results.count(primary_id)
        # With 99% canary, expect ~99% to go to primary
        assert primary_count >= 90  # Allow some variance

    def test_choose_model_no_deployment_returns_primary(self) -> None:
        """When model has no deployment, return primary."""
        registry = ModelRegistry()
        model_id = "model-undeployed"

        registry.register_model(
            model_id=model_id,
            signal_id="regime_btc_v3",
            artifact_path="/path/to/artifact.pkl",
            feature_version="v1",
        )

        deployer = CanaryDeployer(registry)
        chosen = deployer.choose_model("regime_btc_v3", model_id)
        assert chosen == model_id

    def test_promote_canary_to_full(self) -> None:
        registry = ModelRegistry()
        canary_id = "model-canary-promote"
        fallback_id = "model-fallback"

        registry.register_model(
            model_id=canary_id,
            signal_id="regime_btc_v3",
            artifact_path="/path/to/canary.pkl",
            feature_version="v1",
        )
        registry.register_model(
            model_id=fallback_id,
            signal_id="regime_btc_v3",
            artifact_path="/path/to/fallback.pkl",
            feature_version="v1",
        )
        registry.deploy(
            model_id=canary_id,
            deployment_type=DeploymentType.CANARY,
            canary_percentage=10,
            fallback_model_id=fallback_id,
        )

        deployer = CanaryDeployer(registry)
        deployer.promote_canary(canary_id)

        # Check that the deployment is now FULL
        deployment = registry.get_deployment(canary_id)
        assert deployment["deployment_type"] == DeploymentType.FULL
        assert deployment["canary_percentage"] == 0
        assert deployment["fallback_model_id"] is None

    def test_promote_non_canary_raises(self) -> None:
        registry = ModelRegistry()
        model_id = "model-full"

        registry.register_model(
            model_id=model_id,
            signal_id="regime_btc_v3",
            artifact_path="/path/to/artifact.pkl",
            feature_version="v1",
        )
        registry.deploy(
            model_id=model_id,
            deployment_type=DeploymentType.FULL,
        )

        deployer = CanaryDeployer(registry)
        with pytest.raises(ValueError, match="Cannot promote non-CANARY model"):
            deployer.promote_canary(model_id)

    def test_promote_undeployed_model_raises(self) -> None:
        registry = ModelRegistry()
        model_id = "model-undeployed"

        registry.register_model(
            model_id=model_id,
            signal_id="regime_btc_v3",
            artifact_path="/path/to/artifact.pkl",
            feature_version="v1",
        )

        deployer = CanaryDeployer(registry)
        with pytest.raises(ValueError, match="Model .* has no deployment"):
            deployer.promote_canary(model_id)

    def test_rollback_canary_retires_model(self) -> None:
        registry = ModelRegistry()
        canary_id = "model-canary-rollback"
        fallback_id = "model-fallback"

        registry.register_model(
            model_id=canary_id,
            signal_id="regime_btc_v3",
            artifact_path="/path/to/canary.pkl",
            feature_version="v1",
        )
        registry.register_model(
            model_id=fallback_id,
            signal_id="regime_btc_v3",
            artifact_path="/path/to/fallback.pkl",
            feature_version="v1",
        )
        registry.deploy(
            model_id=canary_id,
            deployment_type=DeploymentType.CANARY,
            canary_percentage=10,
            fallback_model_id=fallback_id,
        )

        deployer = CanaryDeployer(registry)
        deployer.rollback_canary(canary_id)

        # Check that the model is retired
        model = registry.get_model(canary_id)
        assert model["status"] == "retired"

    def test_rollback_non_canary_raises(self) -> None:
        registry = ModelRegistry()
        model_id = "model-full"

        registry.register_model(
            model_id=model_id,
            signal_id="regime_btc_v3",
            artifact_path="/path/to/artifact.pkl",
            feature_version="v1",
        )
        registry.deploy(
            model_id=model_id,
            deployment_type=DeploymentType.FULL,
        )

        deployer = CanaryDeployer(registry)
        with pytest.raises(ValueError, match="Cannot rollback non-CANARY model"):
            deployer.rollback_canary(model_id)

    def test_rollback_undeployed_model_raises(self) -> None:
        registry = ModelRegistry()
        model_id = "model-undeployed"

        registry.register_model(
            model_id=model_id,
            signal_id="regime_btc_v3",
            artifact_path="/path/to/artifact.pkl",
            feature_version="v1",
        )

        deployer = CanaryDeployer(registry)
        with pytest.raises(ValueError, match="Model .* has no deployment"):
            deployer.rollback_canary(model_id)
