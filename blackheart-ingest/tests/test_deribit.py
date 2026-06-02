"""Unit tests for the Deribit DVOL source. Pure-mock: ``_http_get`` is
patched, so no real HTTP and no DB writes."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import httpx
import pytest

from blackheart_ingest.sources import deribit


def _candle(ts_ms: int, close: float) -> list:
    # Deribit shape: [timestamp_ms, open, high, low, close]
    return [ts_ms, close, close, close, close]


def _page(candles: list) -> dict:
    return {"result": {"data": candles, "continuation": None}}


def test_fetch_dvol_builds_macro_raw_rows():
    now = datetime(2024, 1, 2, tzinfo=timezone.utc)
    start = datetime(2024, 1, 1, 0, tzinfo=timezone.utc)
    end = datetime(2024, 1, 1, 2, tzinfo=timezone.utc)
    base = int(start.timestamp() * 1000)
    hour = 3600 * 1000
    candles = [_candle(base, 60.0), _candle(base + hour, 61.0), _candle(base + 2 * hour, 62.0)]

    with patch("blackheart_ingest.sources.deribit._http_get", return_value=_page(candles)) as mock_get:
        rows = deribit._fetch_dvol(None, "BTC", start, end, 3600, now)

    assert mock_get.called
    assert len(rows) == 3
    r = sorted(rows, key=lambda x: x["event_time"])[0]
    assert r["series_id"] == "deribit_btc_dvol"
    assert r["symbol"] is None
    assert r["source"] == "deribit"
    assert r["value"] == 60.0
    assert r["value_text"] is None
    assert r["content_hash"]
    # event_time MUST be naive UTC — the server passes naive request.start, and
    # mixing aware/naive crashes partition_by_pit. Guard the bug class directly.
    assert r["event_time"].tzinfo is None
    assert r["event_time"] == start.replace(tzinfo=None)
    # source_uri must be unique per (series_id, event_time) — guards the
    # macro_raw UNIQUE(source, source_uri, event_time) collision class.
    assert len({row["source_uri"] for row in rows}) == len(rows)
    assert r["source_uri"] == "deribit/deribit_btc_dvol/" + start.replace(tzinfo=None).isoformat()


def test_fetch_dvol_dedupes_and_filters_window():
    now = datetime(2024, 1, 2, tzinfo=timezone.utc)
    start = datetime(2024, 1, 1, 1, tzinfo=timezone.utc)  # excludes the 00:00 bar
    end = datetime(2024, 1, 1, 2, tzinfo=timezone.utc)
    day = datetime(2024, 1, 1, 0, tzinfo=timezone.utc)
    base = int(day.timestamp() * 1000)
    hour = 3600 * 1000
    # 00:00 is before `start` → filtered; duplicate 01:00 → deduped.
    candles = [_candle(base, 60.0), _candle(base + hour, 61.0), _candle(base + hour, 61.0)]

    with patch("blackheart_ingest.sources.deribit._http_get", return_value=_page(candles)):
        rows = deribit._fetch_dvol(None, "ETH", start, end, 3600, now)

    assert len(rows) == 1
    assert rows[0]["series_id"] == "deribit_eth_dvol"
    assert rows[0]["event_time"] == datetime(2024, 1, 1, 1)  # naive UTC


def test_fetch_dvol_pages_backward_until_start():
    now = datetime(2024, 1, 3, tzinfo=timezone.utc)
    start = datetime(2024, 1, 1, 0, tzinfo=timezone.utc)
    end = datetime(2024, 1, 1, 3, tzinfo=timezone.utc)
    base = int(start.timestamp() * 1000)
    hour = 3600 * 1000
    # Page 1 (newest two bars), page 2 (oldest two, overlaps page1's earliest).
    page1 = _page([_candle(base + 2 * hour, 62.0), _candle(base + 3 * hour, 63.0)])
    page2 = _page([_candle(base, 60.0), _candle(base + hour, 61.0), _candle(base + 2 * hour, 62.0)])

    with patch("blackheart_ingest.sources.deribit._http_get", side_effect=[page1, page2]) as mock_get:
        rows = deribit._fetch_dvol(None, "BTC", start, end, 3600, now)

    # Two pages requested; 4 unique bars after dedup of the overlapping 02:00.
    assert mock_get.call_count == 2
    assert len({r["event_time"] for r in rows}) == 4


def test_http_get_raises_on_json_error_body():
    # Deribit returns HTTP 200 + JSON-RPC error for rate-limits / bad params.
    client = MagicMock()
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"error": {"code": 10028, "message": "too_many_requests"}}
    client.get.return_value = resp
    with pytest.raises(httpx.HTTPError):
        deribit._http_get(client, {"currency": "BTC"})


def test_fetch_dvol_empty_response_stops():
    now = datetime(2024, 1, 2, tzinfo=timezone.utc)
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 2, tzinfo=timezone.utc)
    with patch("blackheart_ingest.sources.deribit._http_get", return_value=_page([])) as mock_get:
        rows = deribit._fetch_dvol(None, "BTC", start, end, 3600, now)
    assert rows == []
    assert mock_get.call_count == 1
