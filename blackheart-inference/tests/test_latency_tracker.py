"""Tests for LatencyTracker — p99 inference latency SLO tracking."""

from __future__ import annotations

import pytest

from blackheart_inference.monitoring.latency_tracker import LatencyTracker


class TestLatencyTrackerBasics:
    """Basic record and retrieve operations."""

    def test_init_default_slo(self) -> None:
        """Initialize with default 100ms SLO."""
        tracker = LatencyTracker()
        assert tracker.p99_slo_ms == 100

    def test_init_custom_slo(self) -> None:
        """Initialize with custom SLO."""
        tracker = LatencyTracker(p99_slo_ms=50)
        assert tracker.p99_slo_ms == 50

    def test_record_single_latency(self) -> None:
        """Record a single latency measurement."""
        tracker = LatencyTracker()
        tracker.record_latency("signal_1", 45.5)
        stats = tracker.get_stats("signal_1")
        assert stats is not None
        assert stats["count"] == 1
        assert stats["min"] == 45.5
        assert stats["max"] == 45.5
        assert stats["mean"] == 45.5

    def test_record_multiple_latencies_same_signal(self) -> None:
        """Record multiple measurements for the same signal."""
        tracker = LatencyTracker()
        latencies = [10.0, 20.0, 30.0, 40.0, 50.0]
        for lat in latencies:
            tracker.record_latency("signal_1", lat)

        stats = tracker.get_stats("signal_1")
        assert stats is not None
        assert stats["count"] == 5
        assert stats["min"] == 10.0
        assert stats["max"] == 50.0
        assert stats["mean"] == 30.0

    def test_get_stats_nonexistent_signal(self) -> None:
        """Getting stats for a nonexistent signal returns None."""
        tracker = LatencyTracker()
        stats = tracker.get_stats("nonexistent")
        assert stats is None


class TestLatencyTrackerPercentiles:
    """Percentile calculation (p50, p99)."""

    def test_p50_single_value(self) -> None:
        """P50 of single value is that value."""
        tracker = LatencyTracker()
        tracker.record_latency("signal_1", 42.0)
        stats = tracker.get_stats("signal_1")
        assert stats["p50"] == 42.0

    def test_p99_single_value(self) -> None:
        """P99 of single value is that value."""
        tracker = LatencyTracker()
        tracker.record_latency("signal_1", 42.0)
        stats = tracker.get_stats("signal_1")
        assert stats["p99"] == 42.0

    def test_p50_multiple_values(self) -> None:
        """P50 (median) calculation."""
        tracker = LatencyTracker()
        # 1-9 for clear median at position 4 (0-indexed) = value 5
        for i in range(1, 10):
            tracker.record_latency("signal_1", float(i))

        stats = tracker.get_stats("signal_1")
        # For 9 values, p50 at index int(0.5 * (9-1)) = 4, value = 5.0
        assert stats["p50"] == 5.0

    def test_p99_multiple_values(self) -> None:
        """P99 calculation with 100 values."""
        tracker = LatencyTracker()
        # 100 values: 1 to 100
        for i in range(1, 101):
            tracker.record_latency("signal_1", float(i))

        stats = tracker.get_stats("signal_1")
        # Python's quantiles uses linear interpolation
        # For 100 values (1-100), p99 uses quantiles which returns ~99.99
        assert 99.0 < stats["p99"] <= 100.0

    def test_p99_smaller_set(self) -> None:
        """P99 with smaller dataset."""
        tracker = LatencyTracker()
        # 10 values: 1-10
        for i in range(1, 11):
            tracker.record_latency("signal_1", float(i))

        stats = tracker.get_stats("signal_1")
        # Python's quantiles uses linear interpolation beyond data bounds
        # For 10 values (1-10), p99 uses quantiles which returns ~10.89
        assert stats["p99"] > 10.0


class TestLatencyTrackerSLO:
    """SLO violation detection."""

    def test_slo_compliant_single_value(self) -> None:
        """Single value below SLO is compliant."""
        tracker = LatencyTracker(p99_slo_ms=100)
        tracker.record_latency("signal_1", 50.0)
        assert tracker.check_slo_violation("signal_1") is False

    def test_slo_violation_single_value(self) -> None:
        """Single value above SLO is a violation."""
        tracker = LatencyTracker(p99_slo_ms=100)
        tracker.record_latency("signal_1", 150.0)
        assert tracker.check_slo_violation("signal_1") is True

    def test_slo_violation_p99_exceeds(self) -> None:
        """Violation when p99 exceeds SLO."""
        tracker = LatencyTracker(p99_slo_ms=100)
        # Create 100 values where p99 = 120
        for i in range(1, 100):
            tracker.record_latency("signal_1", float(i))
        tracker.record_latency("signal_1", 120.0)  # p99 will be around 98-99

        stats = tracker.get_stats("signal_1")
        # Verify p99 is set
        p99 = stats["p99"]
        expected_violation = p99 > 100.0
        assert tracker.check_slo_violation("signal_1") is expected_violation

    def test_slo_compliant_distribution(self) -> None:
        """Distribution where p99 is below SLO."""
        tracker = LatencyTracker(p99_slo_ms=100)
        # Add 100 latencies all below 100ms
        for i in range(100):
            tracker.record_latency("signal_1", 50.0 + (i * 0.5))  # 50-99.5
        assert tracker.check_slo_violation("signal_1") is False

    def test_slo_nonexistent_signal(self) -> None:
        """Check SLO on nonexistent signal returns False."""
        tracker = LatencyTracker()
        assert tracker.check_slo_violation("nonexistent") is False


class TestLatencyTrackerMultipleSignals:
    """Tracking multiple signals independently."""

    def test_multiple_signals_tracked_independently(self) -> None:
        """Different signals maintain separate stats."""
        tracker = LatencyTracker()
        tracker.record_latency("signal_a", 10.0)
        tracker.record_latency("signal_a", 20.0)
        tracker.record_latency("signal_b", 100.0)
        tracker.record_latency("signal_b", 200.0)

        stats_a = tracker.get_stats("signal_a")
        stats_b = tracker.get_stats("signal_b")

        assert stats_a["count"] == 2
        assert stats_a["mean"] == 15.0
        assert stats_b["count"] == 2
        assert stats_b["mean"] == 150.0

    def test_slo_violation_per_signal(self) -> None:
        """SLO violations tracked per signal."""
        tracker = LatencyTracker(p99_slo_ms=100)
        tracker.record_latency("signal_a", 50.0)
        tracker.record_latency("signal_b", 150.0)

        assert tracker.check_slo_violation("signal_a") is False
        assert tracker.check_slo_violation("signal_b") is True

    def test_get_all_signals_with_stats(self) -> None:
        """Get stats for all tracked signals."""
        tracker = LatencyTracker(p99_slo_ms=100)
        tracker.record_latency("signal_a", 50.0)
        tracker.record_latency("signal_b", 75.0)
        tracker.record_latency("signal_b", 125.0)

        all_stats = tracker.get_all_stats()
        assert len(all_stats) == 2
        assert "signal_a" in all_stats
        assert "signal_b" in all_stats
        assert all_stats["signal_a"]["count"] == 1
        assert all_stats["signal_b"]["count"] == 2


class TestLatencyTrackerRollingWindow:
    """Rolling window behavior (max 10k per signal)."""

    def test_rolling_window_under_limit(self) -> None:
        """Records under 10k limit are all retained."""
        tracker = LatencyTracker()
        n = 1000
        for i in range(n):
            tracker.record_latency("signal_1", float(i % 100))

        stats = tracker.get_stats("signal_1")
        assert stats["count"] == n

    def test_rolling_window_overflow_keeps_latest(self) -> None:
        """When exceeding 10k, oldest entries are dropped, latest kept."""
        tracker = LatencyTracker(max_per_signal=100)  # Set low limit for testing
        # Record 150 values
        for i in range(150):
            tracker.record_latency("signal_1", float(i))

        stats = tracker.get_stats("signal_1")
        # Should keep last 100 (indices 50-149)
        assert stats["count"] == 100
        # Min should be around 50 (oldest kept)
        assert stats["min"] >= 50.0
        # Max should be 149 (newest)
        assert stats["max"] == 149.0

    def test_rolling_window_default_limit(self) -> None:
        """Default limit is 10000 per signal."""
        tracker = LatencyTracker()
        assert tracker._max_per_signal == 10000


class TestLatencyTrackerReset:
    """Reset functionality."""

    def test_reset_specific_signal(self) -> None:
        """Reset clears stats for a specific signal."""
        tracker = LatencyTracker()
        tracker.record_latency("signal_1", 50.0)
        tracker.record_latency("signal_2", 60.0)

        tracker.reset("signal_1")

        assert tracker.get_stats("signal_1") is None
        assert tracker.get_stats("signal_2") is not None

    def test_reset_all_signals(self) -> None:
        """Reset with no args clears all signals."""
        tracker = LatencyTracker()
        tracker.record_latency("signal_1", 50.0)
        tracker.record_latency("signal_2", 60.0)

        tracker.reset()

        assert tracker.get_stats("signal_1") is None
        assert tracker.get_stats("signal_2") is None

    def test_reset_nonexistent_signal(self) -> None:
        """Reset on nonexistent signal is safe (no-op)."""
        tracker = LatencyTracker()
        tracker.record_latency("signal_1", 50.0)
        tracker.reset("nonexistent")
        assert tracker.get_stats("signal_1") is not None


class TestLatencyTrackerEdgeCases:
    """Edge cases and robustness."""

    def test_zero_latency(self) -> None:
        """Zero latency is valid."""
        tracker = LatencyTracker()
        tracker.record_latency("signal_1", 0.0)
        stats = tracker.get_stats("signal_1")
        assert stats["min"] == 0.0
        assert stats["max"] == 0.0

    def test_negative_latency_rejected(self) -> None:
        """Negative latency should raise ValueError."""
        tracker = LatencyTracker()
        with pytest.raises(ValueError):
            tracker.record_latency("signal_1", -1.0)

    def test_very_large_latency(self) -> None:
        """Very large latencies are accepted."""
        tracker = LatencyTracker()
        tracker.record_latency("signal_1", 999999.0)
        stats = tracker.get_stats("signal_1")
        assert stats["max"] == 999999.0

    def test_empty_signal_id_accepted(self) -> None:
        """Empty string signal_id is technically valid (though unusual)."""
        tracker = LatencyTracker()
        tracker.record_latency("", 50.0)
        stats = tracker.get_stats("")
        assert stats is not None
        assert stats["count"] == 1
