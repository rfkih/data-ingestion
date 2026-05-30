"""Tests for bar_event_consumer."""
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from blackheart_ingest.schemas.events import MarketBarEvent
from blackheart_ingest.workers.bar_event_consumer import (
    _features_for_bar,
    _handle_bar_event,
)


# ── _features_for_bar ─────────────────────────────────────────────────────────

def _make_feature(name, symbols=(), intervals=(), raw_tables=("market_data",)):
    f = MagicMock()
    f.name = name
    f.version = 1
    f.raw_tables = raw_tables
    f.symbols = symbols
    f.intervals = intervals
    return f


def test_features_for_bar_filters_by_symbol_and_interval():
    btc_1h = _make_feature("rsi", symbols=("BTCUSDT",), intervals=("1h",))
    btc_4h = _make_feature("vol", symbols=("BTCUSDT",), intervals=("4h",))
    eth_1h = _make_feature("atr", symbols=("ETHUSDT",), intervals=("1h",))
    macro = _make_feature("vix", symbols=(), intervals=(), raw_tables=("macro_raw",))

    result = _features_for_bar("BTCUSDT", "1h", [btc_1h, btc_4h, eth_1h, macro])

    assert result == [btc_1h]


def test_features_for_bar_excludes_macro():
    macro = _make_feature("vix", symbols=(), intervals=(), raw_tables=("macro_raw",))
    result = _features_for_bar("BTCUSDT", "1h", [macro])
    assert result == []


def test_features_for_bar_empty_symbols_matches_all():
    """A feature with empty symbols tuple matches any symbol."""
    any_sym = _make_feature("broad", symbols=(), intervals=("1h",))
    result = _features_for_bar("SOLUSDT", "1h", [any_sym])
    assert result == [any_sym]


def test_features_for_bar_empty_intervals_matches_all():
    """A feature with empty intervals tuple matches any interval."""
    any_int = _make_feature("broad2", symbols=("BTCUSDT",), intervals=())
    result = _features_for_bar("BTCUSDT", "4h", [any_int])
    assert result == [any_int]


# ── _handle_bar_event ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handle_bar_event_triggers_compute_and_webhook():
    ts = datetime(2026, 5, 30, 14, 0, 0, tzinfo=timezone.utc)
    bar = MarketBarEvent(
        symbol="BTCUSDT", interval="1h", ts=ts,
        open=45000.0, high=45500.0, low=44999.0, close=45250.0, volume=1500.0,
    )

    feat = _make_feature("rsi", symbols=("BTCUSDT",), intervals=("1h",))

    with patch("blackheart_ingest.workers.bar_event_consumer.FEATURES", [feat]), \
         patch("blackheart_ingest.workers.bar_event_consumer._compute_bar_features",
               new_callable=AsyncMock) as mock_compute, \
         patch("blackheart_ingest.workers.bar_event_consumer.notify_inference_batch_ready",
               new_callable=AsyncMock) as mock_webhook:

        mock_compute.return_value = 5  # rows written

        await _handle_bar_event(bar)

        mock_compute.assert_called_once_with(
            symbol="BTCUSDT",
            interval="1h",
            features=[feat],
        )
        mock_webhook.assert_called_once()


@pytest.mark.asyncio
async def test_handle_bar_event_skips_webhook_when_no_features():
    ts = datetime(2026, 5, 30, 14, 0, 0, tzinfo=timezone.utc)
    bar = MarketBarEvent(
        symbol="BTCUSDT", interval="1h", ts=ts,
        open=45000.0, high=45500.0, low=44999.0, close=45250.0, volume=1500.0,
    )

    with patch("blackheart_ingest.workers.bar_event_consumer.FEATURES", []), \
         patch("blackheart_ingest.workers.bar_event_consumer.notify_inference_batch_ready",
               new_callable=AsyncMock) as mock_webhook:

        await _handle_bar_event(bar)

        mock_webhook.assert_not_called()


@pytest.mark.asyncio
async def test_handle_bar_event_does_not_raise_on_compute_error():
    ts = datetime(2026, 5, 30, 14, 0, 0, tzinfo=timezone.utc)
    bar = MarketBarEvent(
        symbol="BTCUSDT", interval="1h", ts=ts,
        open=45000.0, high=45500.0, low=44999.0, close=45250.0, volume=1500.0,
    )
    feat = _make_feature("rsi", symbols=("BTCUSDT",), intervals=("1h",))

    with patch("blackheart_ingest.workers.bar_event_consumer.FEATURES", [feat]), \
         patch("blackheart_ingest.workers.bar_event_consumer._compute_bar_features",
               new_callable=AsyncMock, side_effect=RuntimeError("db down")):

        # Must not raise — consumer loop must continue
        await _handle_bar_event(bar)
