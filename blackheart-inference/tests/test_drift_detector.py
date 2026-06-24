"""Pure-logic tests for the PSI feature-drift detector (no DB)."""

from __future__ import annotations

from blackheart_inference.services.drift_detector import (
    DriftVerdict,
    _verdict,
    build_drift_report,
    compute_feature_psi,
)


def _ramp(n: int, shift: float = 0.0) -> list[float]:
    return [float(i) + shift for i in range(n)]


def test_identical_distribution_is_ok() -> None:
    base = _ramp(1000)
    res = compute_feature_psi("f", base, list(base))
    assert res.psi < 0.01
    assert res.verdict is DriftVerdict.OK
    assert res.baseline_n == 1000


def test_large_shift_flags_drift() -> None:
    base = _ramp(1000)
    live = _ramp(1000, shift=700.0)
    res = compute_feature_psi("f", base, live)
    assert res.psi >= 0.25
    assert res.verdict is DriftVerdict.DRIFT


def test_verdict_thresholds() -> None:
    assert _verdict(0.05) is DriftVerdict.OK
    assert _verdict(0.15) is DriftVerdict.WARN
    assert _verdict(0.40) is DriftVerdict.DRIFT


def test_insufficient_data_is_surfaced_not_crashed() -> None:
    res = compute_feature_psi("f", [1.0, 2.0], [])
    assert res.verdict is DriftVerdict.INSUFFICIENT
    assert res.live_n == 0


def test_report_recommends_retrain_and_sorts_by_psi() -> None:
    base = _ramp(1000)
    drifted = _ramp(1000, shift=700.0)
    report = build_drift_report(
        {"stable": (base, list(base)), "drifted": (base, drifted)}
    )
    assert report.drift_count == 1
    assert report.retrain_recommended is True
    assert report.features[0].feature == "drifted"  # highest PSI first


def test_report_ok_when_all_stable() -> None:
    base = _ramp(1000)
    report = build_drift_report({"a": (base, list(base)), "b": (base, list(base))})
    assert report.drift_count == 0
    assert report.warn_count == 0
    assert report.retrain_recommended is False
    assert report.note == "OK"
