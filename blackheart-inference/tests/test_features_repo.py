"""Pure-Python units of the features repo: as-of resolution for global
features and pinned-version preference. The SQL paths need a real DB and
belong in an integration suite; the boundary semantics live here.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from blackheart_inference.repo.features import FeatureMeta, asof_pick


_T0 = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


def test_asof_picks_latest_at_or_before_ts() -> None:
    series = [
        (_T0 - timedelta(hours=3), 1.0),
        (_T0 - timedelta(hours=1), 2.0),
        (_T0 + timedelta(hours=1), 3.0),  # future — never visible at _T0
    ]
    assert asof_pick(series, _T0, cap_hours=24) == 2.0


def test_asof_exact_ts_match_counts() -> None:
    series = [(_T0, 5.0)]
    assert asof_pick(series, _T0, cap_hours=1) == 5.0


def test_asof_respects_cap() -> None:
    """A value older than the cap must NOT forward-fill — stale macro
    data silently propagating was the failure mode train's merge_asof
    tolerance exists to prevent; serve-time must match."""
    series = [(_T0 - timedelta(hours=30), 1.0)]
    assert asof_pick(series, _T0, cap_hours=24) is None


def test_asof_cap_boundary_inclusive() -> None:
    """Exactly cap-old is still valid (<=, mirroring merge_asof tolerance)."""
    series = [(_T0 - timedelta(hours=24), 1.0)]
    assert asof_pick(series, _T0, cap_hours=24) == 1.0


def test_asof_empty_and_all_future() -> None:
    assert asof_pick([], _T0, cap_hours=24) is None
    assert asof_pick([(_T0 + timedelta(hours=1), 9.0)], _T0, cap_hours=24) is None


def test_feature_meta_default_cap_mirrors_train() -> None:
    """blackheart-train falls back to 24*7 hours when the registry has
    no max_ffill_age_hours; the serving side must use the same default."""
    m = FeatureMeta(
        name="fear_greed_value", version=1, is_global=True,
        ffill_policy="last_value", max_ffill_age_hours=None,
    )
    assert m.ffill_cap_hours == 24 * 7
    m2 = FeatureMeta(
        name="x", version=1, is_global=True,
        ffill_policy="last_value", max_ffill_age_hours=48,
    )
    assert m2.ffill_cap_hours == 48.0
