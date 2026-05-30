"""Tests for /metrics endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient


class TestMetricsEndpoint:
    """Tests for GET /metrics/latency and POST /metrics/reset."""

    def test_get_latency_metrics_empty(self, client: TestClient) -> None:
        """GET /metrics/latency with no data returns empty metrics list."""
        r = client.get("/metrics/latency")
        assert r.status_code == 200
        data = r.json()
        assert "metrics" in data
        assert data["metrics"] == []
        assert data["p99_slo_ms"] == 100.0

    def test_get_latency_metrics_single_signal(self, client: TestClient) -> None:
        """GET /metrics/latency after recording data for one signal."""
        # First, record some latencies via internal tracker manipulation
        # We need to access the tracker through the app state
        from blackheart_inference.monitoring.latency_tracker import LatencyTracker

        app = client.app
        tracker = LatencyTracker()
        tracker.record_latency("signal_1", 25.0)
        tracker.record_latency("signal_1", 50.0)
        tracker.record_latency("signal_1", 75.0)
        app.state.latency_tracker = tracker

        r = client.get("/metrics/latency")
        assert r.status_code == 200
        data = r.json()
        assert len(data["metrics"]) == 1

        metric = data["metrics"][0]
        assert metric["signal_id"] == "signal_1"
        assert metric["count"] == 3
        assert metric["min"] == 25.0
        assert metric["max"] == 75.0
        assert metric["mean"] == 50.0
        assert metric["slo_compliant"] is True
        assert "p50" in metric
        assert "p99" in metric

    def test_get_latency_metrics_multiple_signals(self, client: TestClient) -> None:
        """GET /metrics/latency with multiple signals."""
        from blackheart_inference.monitoring.latency_tracker import LatencyTracker

        app = client.app
        tracker = LatencyTracker()
        tracker.record_latency("signal_a", 10.0)
        tracker.record_latency("signal_a", 20.0)
        tracker.record_latency("signal_b", 50.0)
        tracker.record_latency("signal_b", 100.0)
        tracker.record_latency("signal_b", 150.0)
        app.state.latency_tracker = tracker

        r = client.get("/metrics/latency")
        assert r.status_code == 200
        data = r.json()
        assert len(data["metrics"]) == 2

        signal_ids = {m["signal_id"] for m in data["metrics"]}
        assert signal_ids == {"signal_a", "signal_b"}

    def test_get_latency_metrics_slo_violation(self, client: TestClient) -> None:
        """GET /metrics/latency shows slo_compliant=False when p99 > SLO."""
        from blackheart_inference.monitoring.latency_tracker import LatencyTracker

        app = client.app
        tracker = LatencyTracker(p99_slo_ms=100)
        # Add values that will cause p99 > 100
        for i in range(100):
            tracker.record_latency("signal_1", 99.0 + (i * 0.1))
        tracker.record_latency("signal_1", 150.0)
        app.state.latency_tracker = tracker

        r = client.get("/metrics/latency")
        assert r.status_code == 200
        data = r.json()

        metric = data["metrics"][0]
        assert metric["signal_id"] == "signal_1"
        assert metric["slo_compliant"] is False

    def test_reset_metrics_all(self, client: TestClient) -> None:
        """POST /metrics/reset with no args resets all metrics."""
        from blackheart_inference.monitoring.latency_tracker import LatencyTracker

        app = client.app
        tracker = LatencyTracker()
        tracker.record_latency("signal_a", 50.0)
        tracker.record_latency("signal_b", 75.0)
        app.state.latency_tracker = tracker

        # Verify data exists
        r = client.get("/metrics/latency")
        assert len(r.json()["metrics"]) == 2

        # Reset all
        r = client.post("/metrics/reset")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert "all" in data["message"].lower()

        # Verify data is gone
        r = client.get("/metrics/latency")
        assert len(r.json()["metrics"]) == 0

    def test_reset_metrics_specific_signal(self, client: TestClient) -> None:
        """POST /metrics/reset with signal_id resets only that signal."""
        from blackheart_inference.monitoring.latency_tracker import LatencyTracker

        app = client.app
        tracker = LatencyTracker()
        tracker.record_latency("signal_a", 50.0)
        tracker.record_latency("signal_b", 75.0)
        app.state.latency_tracker = tracker

        # Reset signal_a only
        r = client.post("/metrics/reset?signal_id=signal_a")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert "signal_a" in data["message"]

        # Verify signal_a is gone but signal_b remains
        r = client.get("/metrics/latency")
        metrics = r.json()["metrics"]
        assert len(metrics) == 1
        assert metrics[0]["signal_id"] == "signal_b"

    def test_reset_nonexistent_signal_is_safe(self, client: TestClient) -> None:
        """POST /metrics/reset on nonexistent signal is safe (no error)."""
        from blackheart_inference.monitoring.latency_tracker import LatencyTracker

        app = client.app
        tracker = LatencyTracker()
        tracker.record_latency("signal_a", 50.0)
        app.state.latency_tracker = tracker

        # Reset nonexistent signal
        r = client.post("/metrics/reset?signal_id=nonexistent")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"

        # Verify signal_a still exists
        r = client.get("/metrics/latency")
        metrics = r.json()["metrics"]
        assert len(metrics) == 1
        assert metrics[0]["signal_id"] == "signal_a"
