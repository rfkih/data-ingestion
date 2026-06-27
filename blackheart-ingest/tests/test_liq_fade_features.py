"""LIQ_FADE liquidation-intensity feature tests (V201).

Covers the OPT-IN raw-aggregation path added so event-level macro_raw
streams (binance_liquidation: many force-orders share an event_time) are
SUM/COUNT-bucketed onto a regular grid before the wide pivot, instead of
being silently deduped to one row per timestamp by ``_pivot_wide``.

The load-bearing assertion throughout: dedupe is NOT applied to the
aggregated path -- every event in a bucket contributes.
"""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from blackheart_ingest.features import compute as compute_mod
from blackheart_ingest.features.compute import (
    _aggregate_raw_long,
    _pivot_wide,
    compute,
)
from blackheart_ingest.features.definitions import (
    FeatureDef,
    RawAggregation,
    _passthrough,
    _rolling_sum,
    _second_difference,
    get_feature,
)

SID = "binance_liquidation_btcusdt"


def _long(rows):
    """Build an event-level macro_raw long frame from (series_id, ts, value)."""
    ts = pd.to_datetime([r[1] for r in rows])
    return pd.DataFrame(
        {
            "series_id": [r[0] for r in rows],
            "event_time": ts,
            "ingestion_time": ts,
            "value": [float(r[2]) for r in rows],
        }
    )


def _agg_feat(func):
    return FeatureDef(
        name="t_agg",
        version=1,
        family="liquidation",
        inputs=(SID,),
        transformer=_passthrough(SID),
        raw_aggregation=RawAggregation(func=func, freq="1h"),
        ffill_policy=None,
    )


def test_sum_aggregation_does_not_dedupe_shared_timestamps():
    """Three force-orders at the EXACT same event_time must all sum in -- the
    standard pivot would dedupe (series_id, event_time) to just the first."""
    df = _long(
        [
            (SID, "2026-06-13 10:05:00", 100.0),
            (SID, "2026-06-13 10:05:00", 200.0),
            (SID, "2026-06-13 10:45:00", 300.0),
            (SID, "2026-06-13 11:30:00", 50.0),
        ]
    )
    out = _aggregate_raw_long(df, _agg_feat("sum"))
    m = dict(zip(out["event_time"], out["value"], strict=True))
    assert m[pd.Timestamp("2026-06-13 11:00:00")] == 600.0
    assert m[pd.Timestamp("2026-06-13 12:00:00")] == 50.0
    assert m[pd.Timestamp("2026-06-13 11:00:00")] != 100.0


def test_count_aggregation_counts_every_event():
    df = _long(
        [
            (SID, "2026-06-13 10:05:00", 100.0),
            (SID, "2026-06-13 10:05:00", 200.0),
            (SID, "2026-06-13 10:45:00", 300.0),
            (SID, "2026-06-13 11:30:00", 50.0),
        ]
    )
    out = _aggregate_raw_long(df, _agg_feat("count"))
    m = dict(zip(out["event_time"], out["value"], strict=True))
    assert m[pd.Timestamp("2026-06-13 11:00:00")] == 3.0
    assert m[pd.Timestamp("2026-06-13 12:00:00")] == 1.0


def test_bucket_label_is_right_edge():
    df = _long([(SID, "2026-06-13 10:30:00", 7.0)])
    out = _aggregate_raw_long(df, _agg_feat("sum"))
    assert list(out["event_time"]) == [pd.Timestamp("2026-06-13 11:00:00")]
    assert out["value"].iloc[0] == 7.0


def test_empty_buckets_are_zero_and_grid_is_contiguous():
    df = _long(
        [
            (SID, "2026-06-13 10:30:00", 10.0),
            (SID, "2026-06-13 13:30:00", 20.0),
        ]
    )
    out = _aggregate_raw_long(df, _agg_feat("sum"))
    m = dict(zip(out["event_time"], out["value"], strict=True))
    assert m[pd.Timestamp("2026-06-13 12:00:00")] == 0.0
    assert m[pd.Timestamp("2026-06-13 13:00:00")] == 0.0
    assert m[pd.Timestamp("2026-06-13 11:00:00")] == 10.0
    assert m[pd.Timestamp("2026-06-13 14:00:00")] == 20.0


def test_default_path_still_dedupes_keep_first():
    """Regression: features WITHOUT raw_aggregation keep legacy dedupe-first."""
    df = pd.DataFrame(
        {
            "series_id": ["S", "S"],
            "event_time": pd.to_datetime(
                ["2026-06-13 10:00:00", "2026-06-13 10:00:00"]
            ),
            "ingestion_time": pd.to_datetime(
                ["2026-06-13 10:01:00", "2026-06-13 10:02:00"]
            ),
            "value": [1.0, 2.0],
        }
    )
    feat = FeatureDef(
        name="t_plain",
        version=1,
        family="macro",
        inputs=("S",),
        transformer=_passthrough("S"),
        ffill_policy=None,
    )
    value_wide, _ = _pivot_wide(df, feat)
    assert value_wide["S"].iloc[0] == 1.0


def test_rolling_sum_transformer():
    idx = pd.date_range("2026-06-13", periods=6, freq="1h")
    df = pd.DataFrame({"X": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]}, index=idx)
    out = _rolling_sum("X", window=3, min_periods=3)(df)
    assert np.isnan(out.iloc[0]) and np.isnan(out.iloc[1])
    assert list(out.iloc[2:]) == [6.0, 9.0, 12.0, 15.0]


def test_second_difference_transformer():
    idx = pd.date_range("2026-06-13", periods=6, freq="1h")
    df = pd.DataFrame({"X": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]}, index=idx)
    out = _second_difference("X", periods=1)(df)
    assert np.isnan(out.iloc[0]) and np.isnan(out.iloc[1])
    assert (out.iloc[2:] == 0.0).all()


def test_second_difference_stays_finite_on_zero_buckets():
    """Why abs diff not pct_change: $0 hours are routine and must not -> inf."""
    idx = pd.date_range("2026-06-13", periods=5, freq="1h")
    df = pd.DataFrame({"X": [0.0, 0.0, 5.0, 0.0, 0.0]}, index=idx)
    out = _second_difference("X", periods=1)(df)
    defined = out.dropna()
    assert np.isfinite(defined.to_numpy()).all()


def test_raw_aggregation_rejected_on_non_macro_raw():
    with pytest.raises(ValueError, match="raw_aggregation"):
        FeatureDef(
            name="bad",
            version=1,
            family="market_structure",
            inputs=("close_price",),
            transformer=_passthrough("close_price"),
            raw_aggregation=RawAggregation(func="sum"),
            raw_tables=("market_data",),
            ffill_policy=None,
        )


def _gen_events(series_id, per_hour, value_fn, start, end):
    """Synthetic event stream: ``per_hour`` force-orders every hour, ALL at the
    same sub-hour minute (HH:05) to stress the shared-timestamp dedupe case.
    Filtered to [start, end] like the real _read_raw_long."""
    anchors = pd.date_range("2026-06-12", "2026-07-02", freq="1h")
    rows = []
    for i, h in enumerate(anchors):
        ts = (h + pd.Timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
        for _ in range(per_hour):
            rows.append((series_id, ts, float(value_fn(i))))
    df = _long(rows)
    mask = (df["event_time"] >= start) & (df["event_time"] <= end)
    return df[mask].reset_index(drop=True)


def _patch_read(monkeypatch, per_hour, value_fn):
    def fake_read(conn, table, series_ids, start, end):
        return _gen_events(series_ids[0], per_hour, value_fn, start, end)

    monkeypatch.setattr(compute_mod, "_read_raw_long", fake_read)


def test_compute_liq_event_count_4h(monkeypatch):
    # 3 events/hour sharing one timestamp -> count/hour 3, rolling-4 = 12.
    # Dedupe-first would give count/hour 1 -> 4, so 12 proves the aggregation
    # path bypasses the (series_id, event_time) dedupe end-to-end.
    _patch_read(monkeypatch, 3, lambda i: 100.0)
    feat = get_feature("liq_event_count_4h_btcusdt")
    tidy = compute(
        feat, start=datetime(2026, 6, 20), end=datetime(2026, 6, 25), conn=object()
    )
    assert not tidy.empty
    assert (tidy["value"] == 12.0).all()
    assert tidy["ts"].min() >= pd.Timestamp(datetime(2026, 6, 20))


def test_compute_liq_usd_rate_accel_constant_rate_is_zero(monkeypatch):
    # constant hourly USD rate -> 2nd difference == 0 and FINITE (no inf).
    _patch_read(monkeypatch, 2, lambda i: 500.0)
    feat = get_feature("liq_usd_rate_accel_1h_btcusdt")
    tidy = compute(
        feat, start=datetime(2026, 6, 20), end=datetime(2026, 6, 25), conn=object()
    )
    assert not tidy.empty
    assert np.isfinite(tidy["value"].to_numpy()).all()
    assert (tidy["value"] == 0.0).all()


def test_compute_liq_usd_rate_zscore_is_finite(monkeypatch):
    _patch_read(monkeypatch, 1, lambda i: 100.0 + (i % 7) * 25.0)
    feat = get_feature("liq_usd_rate_zscore_24h_btcusdt")
    tidy = compute(
        feat, start=datetime(2026, 6, 20), end=datetime(2026, 6, 25), conn=object()
    )
    assert not tidy.empty
    assert np.isfinite(tidy["value"].to_numpy()).all()
    assert tidy["ts"].min() >= pd.Timestamp(datetime(2026, 6, 20))


def test_compute_incremental_matches_full_for_count(monkeypatch):
    """Warm-up contract holds for the aggregated path too."""
    _patch_read(monkeypatch, 3, lambda i: 100.0)
    feat = get_feature("liq_event_count_4h_btcusdt")
    inc = compute(
        feat, start=datetime(2026, 6, 24), end=datetime(2026, 6, 25), conn=object()
    )
    full = compute(
        feat, start=datetime(2026, 6, 15), end=datetime(2026, 6, 25), conn=object()
    )
    overlap = full[full["ts"] >= pd.Timestamp(datetime(2026, 6, 24))]
    inc_map = dict(zip(inc["ts"], inc["value"], strict=True))
    full_map = dict(zip(overlap["ts"], overlap["value"], strict=True))
    assert inc_map == full_map
    assert inc_map


def test_all_15_liquidation_features_registered():
    syms = ["btcusdt", "ethusdt", "solusdt", "bnbusdt", "xrpusdt"]
    feats = ["liq_usd_rate_zscore_24h", "liq_event_count_4h", "liq_usd_rate_accel_1h"]
    for f in feats:
        for s in syms:
            fd = get_feature(f + "_" + s)
            assert fd.family == "liquidation"
            assert fd.pit_safe is True
            assert fd.raw_aggregation is not None
            assert fd.raw_tables == ("macro_raw",)
            assert fd.ffill_policy is None
            assert fd.inputs == ("binance_liquidation_" + s,)
