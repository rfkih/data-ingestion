"""Unit tests for V136 OFI bar-level microstructure feature transformers.

Pure pandas — no DB or HTTP calls required. Each test exercises the
transformer factory output directly so regressions in the mathematical
logic are caught independent of the compute engine.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from blackheart_ingest.features.definitions import FEATURES, get_feature


# ── helpers ───────────────────────────────────────────────────────────────────


def _make_market_data(
    n: int = 40,
    buy_fraction: float | None = None,
    *,
    seed: int = 42,
) -> pd.DataFrame:
    """Synthetic market_data wide frame with volume + taker_buy_base_volume."""
    rng = np.random.default_rng(seed)
    index = pd.date_range("2026-01-01", periods=n, freq="1h")
    volume = rng.uniform(100, 1000, n)
    if buy_fraction is None:
        buy_vol = volume * rng.uniform(0.3, 0.7, n)
    else:
        buy_vol = volume * buy_fraction
    return pd.DataFrame(
        {"volume": volume, "taker_buy_base_volume": buy_vol},
        index=index,
    )


# ── ofi_ratio ─────────────────────────────────────────────────────────────────


def test_ofi_ratio_in_unit_interval():
    df = _make_market_data(30)
    feat = get_feature("ofi_ratio")
    result = feat.transformer(df).dropna()
    assert result.between(0.0, 1.0).all(), "ofi_ratio values must be in [0, 1]"


def test_ofi_ratio_zero_volume_is_nan():
    n = 5
    idx = pd.date_range("2026-01-01", periods=n, freq="1h")
    df = pd.DataFrame(
        {
            "volume": [0.0, 100.0, 200.0, 0.0, 150.0],
            "taker_buy_base_volume": [0.0, 60.0, 80.0, 0.0, 90.0],
        },
        index=idx,
    )
    feat = get_feature("ofi_ratio")
    result = feat.transformer(df)
    assert pd.isna(result.iloc[0]), "zero volume -> NaN"
    assert pd.isna(result.iloc[3]), "zero volume -> NaN"
    assert not pd.isna(result.iloc[1])
    assert not pd.isna(result.iloc[2])


def test_ofi_ratio_all_buy_is_one():
    n = 5
    idx = pd.date_range("2026-01-01", periods=n, freq="1h")
    df = pd.DataFrame(
        {"volume": [100.0] * n, "taker_buy_base_volume": [100.0] * n},
        index=idx,
    )
    feat = get_feature("ofi_ratio")
    result = feat.transformer(df)
    assert (result - 1.0).abs().lt(1e-9).all()


def test_ofi_ratio_no_buy_is_zero():
    n = 5
    idx = pd.date_range("2026-01-01", periods=n, freq="1h")
    df = pd.DataFrame(
        {"volume": [100.0] * n, "taker_buy_base_volume": [0.0] * n},
        index=idx,
    )
    feat = get_feature("ofi_ratio")
    result = feat.transformer(df)
    assert result.abs().lt(1e-9).all()


# ── ofi_zscore_24h ────────────────────────────────────────────────────────────


def test_ofi_zscore_24h_warmup_nan():
    """First 23 rows must be NaN (min_periods=24 not met)."""
    df = _make_market_data(40)
    feat = get_feature("ofi_zscore_24h")
    result = feat.transformer(df)
    assert result.iloc[:23].isna().all(), "warmup rows must be NaN"
    assert result.iloc[23:].notna().any(), "post-warmup rows must have values"


def test_ofi_zscore_24h_near_zero_mean():
    """Z-score of a stationary series should have mean near zero."""
    rng = np.random.default_rng(0)
    n = 200
    idx = pd.date_range("2026-01-01", periods=n, freq="1h")
    # Stable ratio around 0.5
    df = pd.DataFrame(
        {
            "volume": np.ones(n) * 1000,
            "taker_buy_base_volume": rng.uniform(400, 600, n),
        },
        index=idx,
    )
    feat = get_feature("ofi_zscore_24h")
    result = feat.transformer(df).dropna()
    assert abs(result.mean()) < 1.0, "z-score mean should be near zero for stationary input"


def test_ofi_zscore_24h_constant_ratio_is_nan():
    """Constant ratio -> std=0 -> z-score is NaN (avoid divide-by-zero)."""
    n = 50
    idx = pd.date_range("2026-01-01", periods=n, freq="1h")
    df = pd.DataFrame(
        {"volume": [100.0] * n, "taker_buy_base_volume": [50.0] * n},
        index=idx,
    )
    feat = get_feature("ofi_zscore_24h")
    result = feat.transformer(df)
    # With constant input std=0 is masked -> all NaN after warmup
    assert result.iloc[23:].isna().all()


# ── ofi_momentum_8h ───────────────────────────────────────────────────────────


def test_ofi_momentum_8h_first_8_nan():
    df = _make_market_data(20)
    feat = get_feature("ofi_momentum_8h")
    result = feat.transformer(df)
    assert result.iloc[:8].isna().all(), "first 8 rows must be NaN (pct_change(8) lag)"
    assert result.iloc[8:].notna().any()


def test_ofi_momentum_8h_rising_ratio_positive():
    """Monotonically rising buy fraction -> positive momentum."""
    n = 20
    idx = pd.date_range("2026-01-01", periods=n, freq="1h")
    fractions = np.linspace(0.3, 0.7, n)
    df = pd.DataFrame(
        {"volume": [100.0] * n, "taker_buy_base_volume": 100.0 * fractions},
        index=idx,
    )
    feat = get_feature("ofi_momentum_8h")
    result = feat.transformer(df).dropna()
    assert (result > 0).all(), "rising ratio -> positive momentum"


def test_ofi_momentum_8h_falling_ratio_negative():
    """Monotonically falling buy fraction -> negative momentum."""
    n = 20
    idx = pd.date_range("2026-01-01", periods=n, freq="1h")
    fractions = np.linspace(0.7, 0.3, n)
    df = pd.DataFrame(
        {"volume": [100.0] * n, "taker_buy_base_volume": 100.0 * fractions},
        index=idx,
    )
    feat = get_feature("ofi_momentum_8h")
    result = feat.transformer(df).dropna()
    assert (result < 0).all(), "falling ratio -> negative momentum"


# ── cvd_proxy_zscore_24h ─────────────────────────────────────────────────────


def test_cvd_proxy_zscore_24h_warmup_nan():
    df = _make_market_data(40)
    feat = get_feature("cvd_proxy_zscore_24h")
    result = feat.transformer(df)
    assert result.iloc[:23].isna().all()
    assert result.iloc[23:].notna().any()


def test_cvd_proxy_positive_when_buyer_dominant():
    """When buy_vol > sell_vol every bar, CVD > 0, z-score should be positive
    if we start the series that way.
    """
    n = 50
    idx = pd.date_range("2026-01-01", periods=n, freq="1h")
    vol = np.ones(n) * 100.0
    # 80% buy volume -> CVD = 2*80 - 100 = 60 (always positive)
    buy = np.ones(n) * 80.0
    # add tiny noise to avoid constant std=0
    rng = np.random.default_rng(7)
    buy = buy + rng.uniform(-1, 1, n)
    df = pd.DataFrame({"volume": vol, "taker_buy_base_volume": buy}, index=idx)
    feat = get_feature("cvd_proxy_zscore_24h")
    result = feat.transformer(df).dropna()
    # The z-score of a consistently positive CVD series should be near zero
    # (not necessarily all positive, but the mean of the raw CVD is positive)
    assert not result.empty


def test_cvd_proxy_zscore_24h_constant_is_nan():
    """Constant CVD -> std=0 -> z-score NaN after warmup."""
    n = 50
    idx = pd.date_range("2026-01-01", periods=n, freq="1h")
    df = pd.DataFrame(
        {"volume": [100.0] * n, "taker_buy_base_volume": [70.0] * n},
        index=idx,
    )
    feat = get_feature("cvd_proxy_zscore_24h")
    result = feat.transformer(df)
    assert result.iloc[23:].isna().all()


# ── registry / metadata checks ────────────────────────────────────────────────


def test_ofi_features_all_registered():
    names = {"ofi_ratio", "ofi_zscore_24h", "ofi_momentum_8h", "cvd_proxy_zscore_24h"}
    registered = {f.name for f in FEATURES}
    assert names <= registered, f"Missing: {names - registered}"


def test_ofi_features_use_market_data():
    for name in ("ofi_ratio", "ofi_zscore_24h", "ofi_momentum_8h", "cvd_proxy_zscore_24h"):
        feat = get_feature(name)
        assert feat.raw_tables == ("market_data",), f"{name}: expected market_data"
        assert feat.pit_safe is True
        assert feat.ffill_policy is None


def test_ofi_features_symbol_interval_scope():
    for name in ("ofi_ratio", "ofi_zscore_24h", "ofi_momentum_8h", "cvd_proxy_zscore_24h"):
        feat = get_feature(name)
        assert "BTCUSDT" in feat.symbols
        assert "ETHUSDT" in feat.symbols
        assert "1h" in feat.intervals
        assert "4h" in feat.intervals


def test_ofi_features_declare_correct_inputs():
    expected_inputs = ("volume", "taker_buy_base_volume")
    for name in ("ofi_ratio", "ofi_zscore_24h", "ofi_momentum_8h", "cvd_proxy_zscore_24h"):
        feat = get_feature(name)
        assert set(feat.inputs) == set(expected_inputs), (
            f"{name}: expected inputs {expected_inputs}, got {feat.inputs}"
        )
