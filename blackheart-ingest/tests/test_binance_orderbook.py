"""Unit tests for the V137 binance_orderbook source module and OB feature transformers.

All tests are pure-mock: no DB writes, no real HTTP calls. The http helper
and DB write function are patched so every test runs offline.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch

import pandas as pd
import pytest

from blackheart_ingest.features.definitions import FEATURES, get_feature
from blackheart_ingest.sources.binance_orderbook import (
    _parse_depth_response,
    fetch_snapshot,
    fetch_and_store,
    _store_snapshot,
    _store_macro_series,
)
from blackheart_ingest.workers.bar_event_consumer import (
    _OB_INTERVALS,
    _OB_SYMBOLS,
)


# ── Fixtures / helpers ────────────────────────────────────────────────────────

_FAKE_DEPTH = {
    "lastUpdateId": 99999,
    "bids": [
        ["50000.00", "1.500"],
        ["49999.00", "2.000"],
        ["49998.00", "0.500"],
    ],
    "asks": [
        ["50001.00", "0.800"],
        ["50002.00", "1.200"],
        ["50003.00", "3.000"],
    ],
}

_BAR_TS = datetime(2026, 5, 31, 12, 0, 0, tzinfo=timezone.utc)


# ── _parse_depth_response ────────────────────────────────────────────────────


def test_parse_depth_response_best_bid_ask():
    result = _parse_depth_response(_FAKE_DEPTH)
    assert result["best_bid"] == pytest.approx(50000.0)
    assert result["best_ask"] == pytest.approx(50001.0)


def test_parse_depth_response_depth_sums():
    result = _parse_depth_response(_FAKE_DEPTH)
    assert result["bid_depth_sum"] == pytest.approx(1.5 + 2.0 + 0.5)
    assert result["ask_depth_sum"] == pytest.approx(0.8 + 1.2 + 3.0)


def test_parse_depth_response_empty_book():
    result = _parse_depth_response({"lastUpdateId": 1, "bids": [], "asks": []})
    assert result["best_bid"] is None
    assert result["best_ask"] is None
    assert result["bid_depth_sum"] is None
    assert result["ask_depth_sum"] is None


def test_parse_depth_response_missing_keys():
    result = _parse_depth_response({})
    assert result["best_bid"] is None
    assert result["best_ask"] is None


# ── fetch_snapshot ────────────────────────────────────────────────────────────


def test_fetch_snapshot_calls_http_get_and_returns_parsed():
    with patch("blackheart_ingest.sources.binance_orderbook._http_get") as mock_get:
        mock_get.return_value = _FAKE_DEPTH
        result = fetch_snapshot("BTCUSDT", depth=20)

    mock_get.assert_called_once()
    # Verify symbol + limit are passed (exact call args depend on client)
    call_args = mock_get.call_args
    assert call_args[0][1] == "/api/v3/depth"
    assert call_args[0][2]["symbol"] == "BTCUSDT"
    assert call_args[0][2]["limit"] == 20

    assert result["best_bid"] == pytest.approx(50000.0)
    assert result["best_ask"] == pytest.approx(50001.0)


def test_fetch_snapshot_clamps_depth_to_max():
    with patch("blackheart_ingest.sources.binance_orderbook._http_get") as mock_get:
        mock_get.return_value = _FAKE_DEPTH
        fetch_snapshot("BTCUSDT", depth=9999)
    # depth should be clamped to _MAX_DEPTH (100)
    assert mock_get.call_args[0][2]["limit"] == 100


# ── _store_snapshot ───────────────────────────────────────────────────────────


def test_store_snapshot_executes_upsert():
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    snapshot = {
        "best_bid": 50000.0,
        "best_ask": 50001.0,
        "bid_depth_sum": 4.0,
        "ask_depth_sum": 5.0,
    }

    _store_snapshot("BTCUSDT", "1h", _BAR_TS, snapshot, conn=mock_conn)

    mock_cur.execute.assert_called_once()
    sql_arg = mock_cur.execute.call_args[0][0]
    assert "orderbook_snapshots" in sql_arg
    assert "ON CONFLICT" in sql_arg
    # When conn is externally supplied the caller owns the transaction;
    # _store_snapshot must NOT commit so snapshot + macro_raw share one txn.
    mock_conn.commit.assert_not_called()


# ── fetch_and_store ───────────────────────────────────────────────────────────


def test_fetch_and_store_calls_fetch_then_store():
    snapshot = {
        "best_bid": 50000.0,
        "best_ask": 50001.0,
        "bid_depth_sum": 4.0,
        "ask_depth_sum": 5.0,
    }
    with patch("blackheart_ingest.sources.binance_orderbook.fetch_snapshot",
               return_value=snapshot) as mock_fetch, \
         patch("blackheart_ingest.sources.binance_orderbook._store_snapshot") as mock_store:

        mock_conn = MagicMock()
        result = fetch_and_store("BTCUSDT", "1h", _BAR_TS, conn=mock_conn)

    mock_fetch.assert_called_once_with("BTCUSDT", depth=20)
    mock_store.assert_called_once()
    assert result == snapshot


def test_store_macro_series_distinct_source_uri_per_series():
    """Regression: macro_raw has UNIQUE(source, source_uri, event_time).

    The two derived OB series (spread_bps + imbalance) share the same symbol and
    bar, so if source_uri does not include the series_id they collide on that
    unique index — the second row is silently dropped by ON CONFLICT DO NOTHING,
    leaving only spread_bps. This guards that both rows are emitted with a
    distinct (source, source_uri, event_time) key.
    """
    snapshot = {
        "best_bid": 50000.0, "best_ask": 50001.0,
        "bid_depth_sum": 4.0, "ask_depth_sum": 5.0,
        "spread_bps": 0.2, "imbalance": -0.8,  # negative imbalance must still persist
    }
    with patch(
        "blackheart_ingest.sources.binance_orderbook.write_macro_raw_rows"
    ) as mock_write:
        _store_macro_series("BTCUSDT", _BAR_TS, snapshot, conn=MagicMock())

    mock_write.assert_called_once()
    rows = mock_write.call_args[0][0]
    assert {r["series_id"] for r in rows} == {
        "binance_ob_spread_bps_btcusdt",
        "binance_ob_imbalance_btcusdt",
    }
    unique_keys = {(r["source"], r["source_uri"], r["event_time"]) for r in rows}
    assert len(unique_keys) == len(rows) == 2, (
        "each series must have a distinct (source, source_uri, event_time) "
        "or it collides on uq_macro_raw_source_uri"
    )


# ── OB feature transformer unit tests ────────────────────────────────────────


def _make_ob_frame(n: int = 30) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=n, freq="1h")
    return pd.DataFrame(
        {
            "best_bid": [49990.0 + i * 0.1 for i in range(n)],
            "best_ask": [50010.0 + i * 0.1 for i in range(n)],
            "bid_depth_sum": [100.0 + i for i in range(n)],
            "ask_depth_sum": [80.0 + i for i in range(n)],
        },
        index=idx,
    )


def test_ob_spread_pct_positive():
    feat = get_feature("ob_spread_pct")
    df = _make_ob_frame(10)
    result = feat.transformer(df)
    assert result.dropna().gt(0).all(), "spread_pct must be positive"


def test_ob_spread_pct_zero_mid_is_nan():
    feat = get_feature("ob_spread_pct")
    n = 5
    idx = pd.date_range("2026-01-01", periods=n, freq="1h")
    df = pd.DataFrame(
        {
            "best_bid": [0.0] * n,
            "best_ask": [0.0] * n,
            "bid_depth_sum": [10.0] * n,
            "ask_depth_sum": [10.0] * n,
        },
        index=idx,
    )
    result = feat.transformer(df)
    assert result.isna().all(), "zero mid price -> all NaN"


def test_ob_depth_imbalance_positive_when_bid_heavy():
    feat = get_feature("ob_depth_imbalance")
    n = 5
    idx = pd.date_range("2026-01-01", periods=n, freq="1h")
    df = pd.DataFrame(
        {
            "best_bid": [50000.0] * n,
            "best_ask": [50001.0] * n,
            "bid_depth_sum": [150.0] * n,
            "ask_depth_sum": [50.0] * n,
        },
        index=idx,
    )
    result = feat.transformer(df)
    # (150-50)/(150+50) = 0.5
    assert result.dropna().gt(0).all()
    assert (result.dropna() - 0.5).abs().lt(1e-6).all()


def test_ob_depth_imbalance_negative_when_ask_heavy():
    feat = get_feature("ob_depth_imbalance")
    n = 5
    idx = pd.date_range("2026-01-01", periods=n, freq="1h")
    df = pd.DataFrame(
        {
            "best_bid": [50000.0] * n,
            "best_ask": [50001.0] * n,
            "bid_depth_sum": [50.0] * n,
            "ask_depth_sum": [150.0] * n,
        },
        index=idx,
    )
    result = feat.transformer(df)
    assert result.dropna().lt(0).all()


def test_ob_depth_imbalance_zero_total_is_nan():
    feat = get_feature("ob_depth_imbalance")
    n = 3
    idx = pd.date_range("2026-01-01", periods=n, freq="1h")
    df = pd.DataFrame(
        {
            "best_bid": [50000.0] * n,
            "best_ask": [50001.0] * n,
            "bid_depth_sum": [0.0] * n,
            "ask_depth_sum": [0.0] * n,
        },
        index=idx,
    )
    result = feat.transformer(df)
    assert result.isna().all()


def test_ob_spread_zscore_24h_warmup_nan():
    feat = get_feature("ob_spread_zscore_24h")
    df = _make_ob_frame(40)
    result = feat.transformer(df)
    assert result.iloc[:23].isna().all()
    assert result.iloc[23:].notna().any()


def test_ob_spread_zscore_24h_constant_spread_is_nan():
    feat = get_feature("ob_spread_zscore_24h")
    n = 50
    idx = pd.date_range("2026-01-01", periods=n, freq="1h")
    df = pd.DataFrame(
        {
            "best_bid": [50000.0] * n,
            "best_ask": [50010.0] * n,
            "bid_depth_sum": [100.0] * n,
            "ask_depth_sum": [80.0] * n,
        },
        index=idx,
    )
    result = feat.transformer(df)
    assert result.iloc[23:].isna().all()


# ── Registry metadata checks ──────────────────────────────────────────────────


def test_ob_features_all_registered():
    names = {"ob_spread_pct", "ob_depth_imbalance", "ob_spread_zscore_24h"}
    registered = {f.name for f in FEATURES}
    assert names <= registered, f"Missing: {names - registered}"


def test_ob_features_use_orderbook_snapshots():
    for name in ("ob_spread_pct", "ob_depth_imbalance", "ob_spread_zscore_24h"):
        feat = get_feature(name)
        assert feat.raw_tables == ("orderbook_snapshots",), f"{name}: wrong raw_tables"
        assert feat.pit_safe is True
        assert feat.ffill_policy is None


def test_ob_features_symbol_interval_scope():
    for name in ("ob_spread_pct", "ob_depth_imbalance", "ob_spread_zscore_24h"):
        feat = get_feature(name)
        assert "BTCUSDT" in feat.symbols
        assert "ETHUSDT" in feat.symbols
        assert "1h" in feat.intervals
        assert "4h" in feat.intervals


# ── bar_event_consumer OB hook scope ─────────────────────────────────────────


def test_ob_scope_includes_btcusdt_ethusdt():
    assert "BTCUSDT" in _OB_SYMBOLS
    assert "ETHUSDT" in _OB_SYMBOLS


def test_ob_scope_includes_1h_4h():
    assert "1h" in _OB_INTERVALS
    assert "4h" in _OB_INTERVALS


def test_ob_scope_excludes_solusdt():
    assert "SOLUSDT" not in _OB_SYMBOLS
