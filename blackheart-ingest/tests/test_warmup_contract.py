"""Warm-up contract regression tests (C2 fix, 2026-06-12).

Before the contract, every driver read exactly [start, end] and the
ON CONFLICT DO UPDATE upsert made each timestamp's permanent value
whatever the most TRUNCATED sliding window computed last — degrading
rolling features (sign_streak -> +-1 everywhere, 90d pctranks -> 30d
ranks on the live edge). compute() must now pad its read window by
``feat.lookback_hours`` and trim the warm-up rows, so an incremental
window produces values IDENTICAL to a full recompute.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from blackheart_ingest.features import compute as compute_mod
from blackheart_ingest.features.compute import compute
from blackheart_ingest.features.definitions import (
    FeatureDef,
    _passthrough,
    _sign_streak,
)


def _funding_long_df(start: datetime, end: datetime) -> pd.DataFrame:
    """Synthetic 8h-cadence funding series: positive throughout, so the
    sign streak at row N is N+1 under full history."""
    idx = pd.date_range("2026-01-01", "2026-03-01", freq="8h")
    df = pd.DataFrame(
        {
            "series_id": "F",
            "event_time": idx,
            "ingestion_time": idx + pd.Timedelta(minutes=1),
            "value": 0.0001,
        }
    )
    return df[(df["event_time"] >= start) & (df["event_time"] <= end)].reset_index(
        drop=True
    )


def _streak_feat(lookback_hours: int) -> FeatureDef:
    return FeatureDef(
        name="t_streak",
        version=1,
        family="derivatives",
        inputs=("F",),
        transformer=_sign_streak("F"),
        ffill_policy=None,
        lookback_hours=lookback_hours,
    )


def _patch_macro_read(monkeypatch):
    captured: dict = {}

    def fake_read(conn, table, series_ids, start, end):
        captured["start"] = start
        captured["end"] = end
        return _funding_long_df(start, end)

    monkeypatch.setattr(compute_mod, "_read_raw_long", fake_read)
    return captured


def test_compute_pads_read_window_by_lookback(monkeypatch):
    captured = _patch_macro_read(monkeypatch)
    start = datetime(2026, 2, 20)
    end = datetime(2026, 2, 23)
    compute(_streak_feat(lookback_hours=240), start=start, end=end, conn=object())
    assert captured["start"] == start - timedelta(hours=240)
    assert captured["end"] == end


def test_warmup_rows_are_trimmed_from_output(monkeypatch):
    _patch_macro_read(monkeypatch)
    start = datetime(2026, 2, 20)
    end = datetime(2026, 2, 23)
    tidy = compute(_streak_feat(lookback_hours=240), start=start, end=end, conn=object())
    assert not tidy.empty
    assert tidy["ts"].min() >= pd.Timestamp(start)


def test_incremental_with_lookback_matches_full_recompute(monkeypatch):
    """THE core C2 regression: a short incremental window with proper
    lookback must produce the same values a deep full window does. The
    pre-fix behaviour returned streak=1 for the first row of any window
    (sign_streak counts only within the loaded frame)."""
    _patch_macro_read(monkeypatch)
    feat = _streak_feat(lookback_hours=2160)  # 90d — full synthetic history

    incremental = compute(
        feat, start=datetime(2026, 2, 20), end=datetime(2026, 2, 23), conn=object()
    )
    full = compute(
        feat, start=datetime(2026, 1, 1), end=datetime(2026, 2, 23), conn=object()
    )
    overlap = full[full["ts"] >= pd.Timestamp(datetime(2026, 2, 20))]

    inc_map = dict(zip(incremental["ts"], incremental["value"]))
    full_map = dict(zip(overlap["ts"], overlap["value"]))
    assert inc_map == full_map
    # And the values are genuine long streaks, not the degenerate +-1.
    assert max(inc_map.values()) > 100


def test_zero_lookback_keeps_legacy_window(monkeypatch):
    captured = _patch_macro_read(monkeypatch)
    start = datetime(2026, 2, 20)
    end = datetime(2026, 2, 23)
    feat = FeatureDef(
        name="t_pass",
        version=1,
        family="macro",
        inputs=("F",),
        transformer=_passthrough("F"),
        ffill_policy=None,
    )
    compute(feat, start=start, end=end, conn=object())
    assert captured["start"] == start


def test_nonfinite_output_rows_are_dropped(monkeypatch):
    """H6 regression: pd.notna(inf) is True and Postgres float8 accepts
    'Infinity' — the engine must drop +-inf before persistence."""

    def fake_read(conn, table, series_ids, start, end):
        idx = pd.date_range(start, end, freq="1D")
        return pd.DataFrame(
            {
                "series_id": "F",
                "event_time": idx,
                "ingestion_time": idx,
                "value": 1.0,
            }
        )

    monkeypatch.setattr(compute_mod, "_read_raw_long", fake_read)

    def inf_transformer(df: pd.DataFrame) -> pd.Series:
        s = df["F"].astype("float64").copy()
        s.iloc[0] = np.inf
        s.iloc[1] = -np.inf
        return s

    feat = FeatureDef(
        name="t_inf",
        version=1,
        family="macro",
        inputs=("F",),
        transformer=inf_transformer,
        ffill_policy=None,
    )
    tidy = compute(
        feat, start=datetime(2026, 2, 1), end=datetime(2026, 2, 10), conn=object()
    )
    assert np.isfinite(tidy["value"]).all()
    assert len(tidy) == 8  # 10 daily rows minus the two inf rows


def test_pct_change_does_not_fabricate_zero_across_gaps():
    """H5 regression: pandas' default pad-fill turned NaN holes (left by
    the max_ffill_age_hours cap) into fabricated 0.0% changes."""
    from blackheart_ingest.features.definitions import _change_pct

    df = pd.DataFrame(
        {"X": [1.0, np.nan, np.nan, 2.0]},
        index=pd.date_range("2026-01-01", periods=4, freq="1D"),
    )
    out = _change_pct("X", periods=1)(df)
    # Rows landing on/after a hole must be NaN, not 0.0 / pad-filled.
    assert np.isnan(out.iloc[1])
    assert np.isnan(out.iloc[2])
    assert np.isnan(out.iloc[3])
