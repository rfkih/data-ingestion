"""Unit tests for the EVENT_PROXIMITY (V202) macro-event features.

Covers the three pure transformers (_hours_to_next_event,
_days_since_last_event, _event_window_flag) on synthetic hourly bar indices,
plus the 15 registered FeatureDefs (3 features x 5 majors at 1h).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from blackheart_ingest.features.definitions import (
    CPI_RELEASES,
    FOMC_DECISIONS,
    NFP_RELEASES,
    _days_since_last_event,
    _event_window_flag,
    _hours_to_next_event,
    get_feature,
)


def _hourly_df(start: str, end: str) -> pd.DataFrame:
    """Hourly market_data-shaped frame: DatetimeIndex + a dummy close column
    (the event transformers read only df.index and ignore OHLCV)."""
    idx = pd.date_range(start=start, end=end, freq="h")
    return pd.DataFrame({"close_price": np.arange(len(idx), dtype="float64")}, index=idx)


# ── _hours_to_next_event ──────────────────────────────────────────────────────


def test_hours_to_next_decreases_to_zero_then_jumps() -> None:
    schedule = (pd.Timestamp("2022-01-01 12:00"), pd.Timestamp("2022-01-03 12:00"))
    df = _hourly_df("2022-01-01 00:00", "2022-01-04 00:00")
    out = _hours_to_next_event(schedule)(df)

    # Counts down hour-by-hour to exactly 0 at the first event.
    assert out.loc["2022-01-01 00:00"] == 12.0
    assert out.loc["2022-01-01 11:00"] == 1.0
    assert out.loc["2022-01-01 12:00"] == 0.0
    # One bar past the event it jumps to the gap to the FOLLOWING event.
    assert out.loc["2022-01-01 13:00"] == 47.0
    assert out.loc["2022-01-03 12:00"] == 0.0
    # Strictly decreasing across the approach to the first event.
    approach = out.loc["2022-01-01 00:00":"2022-01-01 12:00"]
    assert (approach.diff().dropna() == -1.0).all()


def test_hours_to_next_after_schedule_is_nan() -> None:
    schedule = (pd.Timestamp("2022-01-01 12:00"), pd.Timestamp("2022-01-03 12:00"))
    df = _hourly_df("2022-01-03 12:00", "2022-01-05 00:00")
    out = _hours_to_next_event(schedule)(df)
    # At the last event -> 0; strictly after the last event -> NaN (no next).
    assert out.loc["2022-01-03 12:00"] == 0.0
    assert np.isnan(out.loc["2022-01-03 13:00"])
    assert np.isnan(out.loc["2022-01-05 00:00"])


# ── _days_since_last_event ────────────────────────────────────────────────────


def test_days_since_last_resets_at_each_event() -> None:
    # Hour-aligned synthetic events so each release lands on a bar.
    schedule = (pd.Timestamp("2022-02-10 12:00"), pd.Timestamp("2022-03-10 12:00"))
    df = _hourly_df("2022-02-01 00:00", "2022-03-12 00:00")
    out = _days_since_last_event(schedule)(df)

    # Before the first event there is no prior event -> NaN edge.
    assert np.isnan(out.loc["2022-02-01 00:00"])
    assert np.isnan(out.loc["2022-02-10 11:00"])
    # Resets to 0 exactly at each release, then grows again.
    assert out.loc["2022-02-10 12:00"] == 0.0
    assert out.loc["2022-02-11 12:00"] == 1.0
    assert out.loc["2022-03-10 12:00"] == 0.0
    # Just before the second release it is ~28 days since the first.
    just_before = out.loc["2022-03-10 11:00"]
    assert 27.9 < just_before < 28.1


# ── _event_window_flag ────────────────────────────────────────────────────────


def test_event_window_flag_within_and_outside() -> None:
    schedule = (pd.Timestamp("2022-01-01 12:00"), pd.Timestamp("2022-01-10 12:00"))
    df = _hourly_df("2022-01-01 00:00", "2022-01-11 00:00")
    out = _event_window_flag(schedule, 24.0, 24.0)(df)

    # On the event and within +/-24h -> 1.0.
    assert out.loc["2022-01-01 12:00"] == 1.0
    assert out.loc["2022-01-02 00:00"] == 1.0      # 12h after event 1
    assert out.loc["2022-01-09 13:00"] == 1.0      # 23h before event 2
    # Covered (between first and last) but far from any event -> 0.0.
    assert out.loc["2022-01-02 13:00"] == 0.0      # 25h after event 1
    assert out.loc["2022-01-05 00:00"] == 0.0
    # Outside the schedule coverage (before first / after last) -> NaN.
    assert np.isnan(out.loc["2022-01-01 00:00"])   # 12h before first event
    assert np.isnan(out.loc["2022-01-11 00:00"])   # after last event


def test_event_window_flag_asymmetric() -> None:
    schedule = (pd.Timestamp("2022-06-15 12:00"),)
    df = _hourly_df("2022-06-15 12:00", "2022-06-16 12:00")
    out = _event_window_flag(schedule, 2.0, 6.0)(df)
    # Only the event instant is covered for a single-event schedule
    # (coverage = [first, last] = one point); all later bars are NaN.
    assert out.loc["2022-06-15 12:00"] == 1.0
    assert np.isnan(out.loc["2022-06-15 18:00"])


# ── Real embedded schedules ───────────────────────────────────────────────────


def test_real_schedules_sorted_and_sized() -> None:
    for sched in (FOMC_DECISIONS, CPI_RELEASES, NFP_RELEASES):
        arr = list(sched)
        assert arr == sorted(arr)           # chronologically ordered
        assert len(arr) == len(set(arr))    # no duplicates
    # 8 FOMC/yr and 12 CPI+NFP/yr across 2018..2027 (10 years).
    assert len(FOMC_DECISIONS) == 80
    assert len(CPI_RELEASES) == 120
    assert len(NFP_RELEASES) == 120
    # All tz-naive UTC wall-clock stamps.
    assert all(ts.tzinfo is None for ts in FOMC_DECISIONS)
    assert FOMC_DECISIONS[0] == pd.Timestamp("2018-01-31 19:00")
    assert CPI_RELEASES[0] == pd.Timestamp("2018-01-12 12:30")


def test_hours_to_next_on_real_fomc_schedule() -> None:
    # 2024-01-31 19:00 UTC is a known FOMC decision stamp in the schedule.
    df = _hourly_df("2024-01-31 17:00", "2024-01-31 21:00")
    out = _hours_to_next_event(FOMC_DECISIONS)(df)
    assert out.loc["2024-01-31 18:00"] == 1.0
    assert out.loc["2024-01-31 19:00"] == 0.0
    assert out.loc["2024-01-31 20:00"] > 0.0


# ── Registered FeatureDefs (3 x 5 majors @ 1h) ────────────────────────────────

_MAJORS = ("btcusdt", "ethusdt", "solusdt", "bnbusdt", "xrpusdt")
_SYMBOL_UPPER = {
    "btcusdt": "BTCUSDT",
    "ethusdt": "ETHUSDT",
    "solusdt": "SOLUSDT",
    "bnbusdt": "BNBUSDT",
    "xrpusdt": "XRPUSDT",
}


def test_all_15_featuredefs_registered_and_shaped() -> None:
    bases = ("hours_to_next_fomc", "days_since_last_cpi", "fomc_event_window_flag")
    count = 0
    for base in bases:
        for sym in _MAJORS:
            feat = get_feature(f"{base}_{sym}", 1)
            count += 1
            assert feat.family == "event"
            assert feat.pit_safe is True
            assert feat.ffill_policy is None
            assert feat.lookback_hours == 0
            assert feat.raw_tables == ("market_data",)
            assert feat.symbols == (_SYMBOL_UPPER[sym],)
            assert feat.intervals == ("1h",)
            assert feat.inputs == ("close_price",)
    assert count == 15


def test_featuredef_transformer_runs_end_to_end() -> None:
    df = _hourly_df("2024-01-31 17:00", "2024-01-31 21:00")
    feat = get_feature("hours_to_next_fomc_btcusdt", 1)
    out = feat.transformer(df)
    assert out.loc["2024-01-31 19:00"] == 0.0

    feat_flag = get_feature("fomc_event_window_flag_ethusdt", 1)
    out_flag = feat_flag.transformer(df)
    assert out_flag.loc["2024-01-31 19:00"] == 1.0
