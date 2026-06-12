"""Unit tests for the Binance spot klines source. Pure-mock: ``_http_get`` is
patched, so no real HTTP and no DB writes."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import httpx
import pytest

from blackheart_ingest.sources import binance_spot


def _k(ts_ms: int, close: float) -> list:
    # Binance kline: [openTime, open, high, low, close, volume, closeTime, ...]
    return [ts_ms, "1", "2", "0.5", str(close), "10", ts_ms + 1, "1", 5, "1", "1", "0"]


def test_fetch_spot_builds_macro_raw_rows():
    now = datetime(2024, 1, 2, tzinfo=timezone.utc)
    start = datetime(2024, 1, 1, 0, tzinfo=timezone.utc)
    end = datetime(2024, 1, 1, 2, tzinfo=timezone.utc)
    base = int(start.timestamp() * 1000)
    hour = 3600 * 1000
    klines = [_k(base, 46000.0), _k(base + hour, 46100.0), _k(base + 2 * hour, 46200.0)]

    with patch("blackheart_ingest.sources.binance_spot._http_get", return_value=klines) as mock_get:
        rows, _truncated = binance_spot._fetch_spot_close(None, "BTCUSDT", "1h", start, end, now)

    assert mock_get.called
    assert len(rows) == 3
    r = sorted(rows, key=lambda x: x["event_time"])[0]
    assert r["series_id"] == "binance_spot_close_btcusdt"
    assert r["symbol"] == "BTCUSDT"
    assert r["source"] == "binance_spot"
    assert r["value"] == 46000.0  # close = kline index 4
    assert r["value_text"] is None
    assert r["content_hash"]
    # event_time MUST be naive UTC (server passes naive request.start; mixing
    # aware/naive crashes partition_by_pit).
    assert r["event_time"].tzinfo is None
    assert r["event_time"] == start.replace(tzinfo=None)
    # source_uri unique per (series_id, event_time) — guards the macro_raw
    # UNIQUE(source, source_uri, event_time) collision class.
    assert len({row["source_uri"] for row in rows}) == len(rows)
    assert r["source_uri"] == "binance_spot/binance_spot_close_btcusdt/" + start.replace(tzinfo=None).isoformat()


def test_fetch_spot_dedupes_and_filters_window():
    now = datetime(2024, 1, 2, tzinfo=timezone.utc)
    start = datetime(2024, 1, 1, 1, tzinfo=timezone.utc)  # excludes the 00:00 bar
    end = datetime(2024, 1, 1, 2, tzinfo=timezone.utc)
    day = datetime(2024, 1, 1, 0, tzinfo=timezone.utc)
    base = int(day.timestamp() * 1000)
    hour = 3600 * 1000
    klines = [_k(base, 46000.0), _k(base + hour, 46100.0), _k(base + hour, 46100.0)]

    with patch("blackheart_ingest.sources.binance_spot._http_get", return_value=klines):
        rows, _truncated = binance_spot._fetch_spot_close(None, "ETHUSDT", "1h", start, end, now)

    assert len(rows) == 1
    assert rows[0]["series_id"] == "binance_spot_close_ethusdt"
    assert rows[0]["event_time"] == datetime(2024, 1, 1, 1)  # naive UTC


def test_fetch_spot_pages_forward(monkeypatch):
    monkeypatch.setattr(binance_spot, "_LIMIT", 2)  # force multi-page
    now = datetime(2024, 1, 3, tzinfo=timezone.utc)
    start = datetime(2024, 1, 1, 0, tzinfo=timezone.utc)
    end = datetime(2024, 1, 1, 3, tzinfo=timezone.utc)
    base = int(start.timestamp() * 1000)
    hour = 3600 * 1000
    page1 = [_k(base, 1.0), _k(base + hour, 2.0)]                 # full batch → continue
    page2 = [_k(base + 2 * hour, 3.0), _k(base + 3 * hour, 4.0)]  # full batch, then end_ms stops

    with patch("blackheart_ingest.sources.binance_spot._http_get", side_effect=[page1, page2]) as mock_get:
        rows, _truncated = binance_spot._fetch_spot_close(None, "BTCUSDT", "1h", start, end, now)

    assert mock_get.call_count == 2
    assert len({r["event_time"] for r in rows}) == 4


def test_http_get_raises_on_dict_error_body():
    client = MagicMock()
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"code": -1121, "msg": "Invalid symbol."}
    client.get.return_value = resp
    with pytest.raises(httpx.HTTPError):
        binance_spot._http_get(client, {"symbol": "NOPE"})


def test_fetch_spot_empty_response_stops():
    now = datetime(2024, 1, 2, tzinfo=timezone.utc)
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 2, tzinfo=timezone.utc)
    with patch("blackheart_ingest.sources.binance_spot._http_get", return_value=[]) as mock_get:
        rows, _truncated = binance_spot._fetch_spot_close(None, "BTCUSDT", "1h", start, end, now)
    assert rows == []
    assert mock_get.call_count == 1


def test_unsupported_interval_raises():
    now = datetime(2024, 1, 2, tzinfo=timezone.utc)
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 2, tzinfo=timezone.utc)
    with patch("blackheart_ingest.sources.binance_spot._http_get", return_value=[]):
        with pytest.raises(ValueError):
            binance_spot._fetch_spot_close(None, "BTCUSDT", "7h", start, end, now)
