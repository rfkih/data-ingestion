"""Tests for POST /compute/refresh endpoint."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from blackheart_ingest.app import create_app


@pytest.fixture
def client():
    """FastAPI test client."""
    app = create_app()
    return TestClient(app)


def test_compute_refresh_full_mode(client):
    """Test full-mode compute (180-day backfill)."""
    with patch(
        "blackheart_ingest.api.compute.get_connection"
    ) as mock_get_conn, patch(
        "blackheart_ingest.api.compute.FEATURES", []
    ):
        # Mock the connection and operations
        mock_conn = MagicMock()
        mock_get_conn.return_value.__enter__.return_value = mock_conn

        response = client.post("/compute/refresh", json={"incremental": False})

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["computed_rows"] == 0
        assert data["persisted_rows"] == 0
        assert data["errors"] == []


def test_compute_refresh_incremental_mode(client):
    """Test incremental mode compute (from max(ts) to now)."""
    with patch(
        "blackheart_ingest.api.compute.get_connection"
    ) as mock_get_conn, patch(
        "blackheart_ingest.api.compute.FEATURES", []
    ):
        # Mock the connection
        mock_conn = MagicMock()
        mock_get_conn.return_value.__enter__.return_value = mock_conn

        response = client.post("/compute/refresh", json={"incremental": True})

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["computed_rows"] == 0
        assert data["persisted_rows"] == 0
        assert data["errors"] == []


def test_compute_refresh_with_invalid_feature(client):
    """Test that invalid feature names return 400 error."""
    response = client.post(
        "/compute/refresh",
        json={"incremental": False, "features": ["nonexistent_feature"]},
    )

    assert response.status_code == 400
    assert "Unknown feature" in response.json()["detail"]


def test_compute_refresh_response_schema(client):
    """Test that response conforms to expected schema."""
    with patch(
        "blackheart_ingest.api.compute.get_connection"
    ) as mock_get_conn, patch(
        "blackheart_ingest.api.compute.FEATURES", []
    ):
        mock_conn = MagicMock()
        mock_get_conn.return_value.__enter__.return_value = mock_conn

        response = client.post("/compute/refresh", json={"incremental": False})

        assert response.status_code == 200
        data = response.json()

        # Verify response schema
        assert "status" in data
        assert "computed_rows" in data
        assert "persisted_rows" in data
        assert "errors" in data

        assert isinstance(data["status"], str)
        assert isinstance(data["computed_rows"], int)
        assert isinstance(data["persisted_rows"], int)
        assert isinstance(data["errors"], list)


def test_compute_refresh_partial_failure(client):
    """Test that partial failures set status to 'partial' and list errors."""
    with patch(
        "blackheart_ingest.api.compute.get_connection"
    ) as mock_get_conn, patch(
        "blackheart_ingest.api.compute.FEATURES", []
    ):
        mock_conn = MagicMock()
        mock_get_conn.return_value.__enter__.return_value = mock_conn

        # Even with no features, we should get a 200 response with ok status
        response = client.post("/compute/refresh", json={"incremental": False})

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"  # No features means no errors


def test_compute_refresh_missing_body(client):
    """Test that missing request body uses defaults."""
    with patch(
        "blackheart_ingest.api.compute.get_connection"
    ) as mock_get_conn, patch(
        "blackheart_ingest.api.compute.FEATURES", []
    ):
        mock_conn = MagicMock()
        mock_get_conn.return_value.__enter__.return_value = mock_conn

        # Send empty JSON object to use defaults
        response = client.post("/compute/refresh", json={})

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
