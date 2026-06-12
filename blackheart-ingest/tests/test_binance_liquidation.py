"""Unit tests for the binance_liquidation streaming source (WS-D1).

Pure-mock: no DB writes, no network, no real websocket. The websockets
client and ``write_macro_raw_rows`` are patched so every test runs offline.
Conventions mirror test_binance_orderbook.py / test_bar_event_consumer.py.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import blackheart_ingest.sources.binance_liquidation as liq
from blackheart_ingest.sources.binance_liquidation import (
    LiquidationStreamState,
    _flush,
    _RowBuffer,
    parse_force_order_event,
    parse_force_order_message,
    run_liquidation_stream,
)
from blackheart_ingest.workers.server import _KNOWN_SOURCES, _lifespan, app

# -- Fixtures / helpers --------------------------------------------------------

# 2024-06-11T00:00:00.123Z
_TRADE_MS = 1718064000123


def _make_event(
    symbol: str = "BTCUSDT",
    side: str = "SELL",
    price: str = "67000.10",
    qty: str = "0.014",
    ap: str = "66980.00",
    status: str = "FILLED",
    trade_ms: int = _TRADE_MS,
) -> dict:
    """One !forceOrder@arr frame as documented by Binance USDT-M futures."""
    return {
        "e": "forceOrder",
        "E": trade_ms + 5,  # event time lags trade time slightly
        "o": {
            "s": symbol,
            "S": side,
            "o": "LIMIT",
            "f": "IOC",
            "q": qty,
            "p": price,
            "ap": ap,
            "X": status,
            "l": qty,
            "z": qty,
            "T": trade_ms,
        },
    }


# -- parse_force_order_event: event -> macro_raw row mapping --------------------


def test_parse_event_maps_macro_raw_row():
    row = parse_force_order_event(_make_event())

    assert row is not None
    assert row["source"] == "binance_liquidation"
    assert row["symbol"] == "BTCUSDT"
    assert row["series_id"] == "binance_liquidation_btcusdt"
    # event_time = order trade time o.T (NOT the event time E)
    assert row["event_time"] == datetime(2024, 6, 11, 0, 0, 0, 123000)
    # value = notional USDT = price x original qty
    assert row["value"] == pytest.approx(67000.10 * 0.014)
    assert row["schema_version"] == 1
    assert row["source_uri"].startswith(f"binance/forceOrder/BTCUSDT/{_TRADE_MS}/")

    payload = json.loads(row["value_text"])
    assert payload == {
        "side": "SELL",
        "price": 67000.10,
        "qty": 0.014,
        "avgPrice": 66980.00,
        "orderStatus": "FILLED",
    }


def test_parse_event_content_hash_stable_across_reparses():
    """Dedupe key must not depend on ingestion time / parse order."""
    row_a = parse_force_order_event(_make_event(), ingestion_time=datetime(2026, 6, 12, 1, 0))
    row_b = parse_force_order_event(_make_event(), ingestion_time=datetime(2026, 6, 12, 2, 0))
    assert row_a["content_hash"] == row_b["content_hash"]
    assert row_a["source_uri"] == row_b["source_uri"]


def test_parse_event_content_hash_differs_when_fields_differ():
    base = parse_force_order_event(_make_event())
    other_qty = parse_force_order_event(_make_event(qty="0.015"))
    other_side = parse_force_order_event(_make_event(side="BUY"))
    assert base["content_hash"] != other_qty["content_hash"]
    assert base["content_hash"] != other_side["content_hash"]


def test_parse_event_same_ms_distinct_unique_key():
    """Regression guard (binance_orderbook lesson): macro_raw has
    UNIQUE(source, source_uri, event_time). Two same-symbol events in the
    same millisecond must not collide or ON CONFLICT DO NOTHING silently
    drops the second row."""
    row_a = parse_force_order_event(_make_event(side="SELL"))
    row_b = parse_force_order_event(_make_event(side="BUY", price="66999.0"))
    keys = {
        (r["source"], r["source_uri"], r["event_time"]) for r in (row_a, row_b)
    }
    assert len(keys) == 2


def test_parse_event_falls_back_to_event_time_when_trade_time_missing():
    event = _make_event()
    event["o"].pop("T")
    row = parse_force_order_event(event)
    assert row is not None
    # E = trade_ms + 5
    assert row["event_time"] == datetime(2024, 6, 11, 0, 0, 0, 128000)


def test_parse_event_rejects_malformed():
    assert parse_force_order_event({"e": "aggTrade"}) is None          # wrong type
    assert parse_force_order_event({"e": "forceOrder"}) is None        # no order block
    assert parse_force_order_event("nope") is None                     # not a dict
    bad_price = _make_event(price="not-a-number")
    assert parse_force_order_event(bad_price) is None
    no_symbol = _make_event()
    no_symbol["o"].pop("s")
    assert parse_force_order_event(no_symbol) is None


# -- parse_force_order_message: frame decoding ----------------------------------


def test_parse_message_accepts_raw_json_string_and_bytes():
    frame = json.dumps(_make_event())
    assert len(parse_force_order_message(frame)) == 1
    assert len(parse_force_order_message(frame.encode("utf-8"))) == 1


def test_parse_message_rejects_undecodable_frame():
    assert parse_force_order_message("{not json") == []


def test_parse_message_unwraps_combined_stream_frame():
    wrapped = {"stream": "!forceOrder@arr", "data": _make_event()}
    rows = parse_force_order_message(json.dumps(wrapped))
    assert len(rows) == 1
    assert rows[0]["symbol"] == "BTCUSDT"


def test_parse_message_handles_array_payload():
    frame = json.dumps([_make_event(), _make_event(symbol="ETHUSDT")])
    rows = parse_force_order_message(frame)
    assert [r["symbol"] for r in rows] == ["BTCUSDT", "ETHUSDT"]


def test_parse_message_accrues_any_symbol():
    """No symbol allowlist -- breadth is the point (WS-A universe expansion)."""
    rows = parse_force_order_message(json.dumps(_make_event(symbol="1000PEPEUSDT")))
    assert rows[0]["series_id"] == "binance_liquidation_1000pepeusdt"


# -- _RowBuffer: batching triggers ----------------------------------------------


def test_buffer_due_at_max_rows():
    buf = _RowBuffer(max_rows=2, flush_seconds=600.0)
    buf.add({"a": 1}, now=100.0)
    assert buf.due(now=100.0) is False
    buf.add({"a": 2}, now=100.1)
    assert buf.due(now=100.1) is True


def test_buffer_due_after_time_deadline():
    buf = _RowBuffer(max_rows=1000, flush_seconds=5.0)
    buf.add({"a": 1}, now=100.0)
    assert buf.due(now=104.9) is False
    assert buf.due(now=105.0) is True


def test_buffer_empty_never_due():
    buf = _RowBuffer(max_rows=1, flush_seconds=0.5)
    assert buf.due(now=10_000.0) is False


def test_buffer_drain_clears_and_resets_deadline():
    buf = _RowBuffer(max_rows=10, flush_seconds=5.0)
    buf.add({"a": 1}, now=100.0)
    rows = buf.drain()
    assert rows == [{"a": 1}]
    assert buf.rows == []
    assert buf.due(now=10_000.0) is False


def test_buffer_restore_requeues_at_front_with_fresh_deadline():
    buf = _RowBuffer(max_rows=10, flush_seconds=5.0)
    buf.add({"a": "new"}, now=100.0)
    buf.restore([{"a": "old"}], now=100.0)
    assert [r["a"] for r in buf.rows] == ["old", "new"]
    # failed-flush retry waits a full interval -- no hot loop against a down DB
    assert buf.due(now=100.1) is False
    assert buf.due(now=105.0) is True


def test_buffer_hard_cap_drops_oldest():
    # hard_cap is clamped to >= max_rows, so keep max_rows below it here.
    buf = _RowBuffer(max_rows=1, flush_seconds=600.0, hard_cap=3)
    for i in range(5):
        buf.add({"i": i}, now=float(i))
    assert [r["i"] for r in buf.rows] == [2, 3, 4]
    assert buf.dropped_overflow == 2


def test_buffer_hard_cap_never_below_max_rows():
    buf = _RowBuffer(max_rows=1000, flush_seconds=600.0, hard_cap=3)
    assert buf.hard_cap == 1000


# -- _flush: batch insert + state accounting ------------------------------------


@pytest.mark.asyncio
async def test_flush_writes_batch_and_updates_state():
    state = LiquidationStreamState(enabled=True)
    buf = _RowBuffer(max_rows=10, flush_seconds=600.0)
    for i in range(3):
        row = parse_force_order_event(_make_event(trade_ms=_TRADE_MS + i))
        buf.add(row, now=float(i))

    with patch.object(liq, "write_macro_raw_rows", return_value=(2, 1)) as mock_write:
        await _flush(buf, state)

    mock_write.assert_called_once()
    rows = mock_write.call_args[0][0]
    assert len(rows) == 3
    assert state.events_written == 2
    assert state.events_skipped_duplicate == 1
    assert state.flushes == 1
    assert state.last_flush_at is not None
    assert buf.rows == []


@pytest.mark.asyncio
async def test_flush_failure_retains_rows_for_retry():
    state = LiquidationStreamState(enabled=True)
    buf = _RowBuffer(max_rows=10, flush_seconds=600.0)
    for i in range(3):
        buf.add({"i": i}, now=float(i))

    with patch.object(
        liq, "write_macro_raw_rows", side_effect=RuntimeError("db down")
    ) as mock_write:
        await _flush(buf, state)  # must NOT raise

    mock_write.assert_called_once()
    assert len(buf.rows) == 3                  # retained, not lost
    assert state.flushes == 0
    assert state.events_written == 0
    assert state.last_error is not None
    assert "db down" in state.last_error


@pytest.mark.asyncio
async def test_flush_empty_buffer_is_noop():
    state = LiquidationStreamState(enabled=True)
    buf = _RowBuffer(max_rows=10, flush_seconds=600.0)
    with patch.object(liq, "write_macro_raw_rows") as mock_write:
        await _flush(buf, state)
    mock_write.assert_not_called()


# -- run_liquidation_stream: reconnect / backoff / gap logging -------------------


class _FakeWS:
    """Async-context websocket double: yields queued frames then dies."""

    def __init__(self, frames: list[str]):
        self._frames = list(frames)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def recv(self):
        if self._frames:
            return self._frames.pop(0)
        raise RuntimeError("connection closed by server")


@pytest.mark.asyncio
async def test_reconnect_backoff_and_gap_warning(monkeypatch, caplog):
    state = LiquidationStreamState(
        enabled=True, ws_url="wss://unit-test",
        flush_max_rows=100, flush_seconds=600.0,
    )

    # Deterministic backoff: no jitter, recorded (not slept) delays.
    monkeypatch.setattr(liq, "random", SimpleNamespace(uniform=lambda a, b: 1.0))
    sleeps: list[float] = []
    real_sleep = asyncio.sleep
    attempts = {"n": 0}

    async def fake_sleep(delay, *args, **kwargs):
        sleeps.append(delay)
        # Throttle the spin once we have what we need; otherwise just yield.
        await real_sleep(0.05 if attempts["n"] >= 4 else 0)

    monkeypatch.setattr(liq.asyncio, "sleep", fake_sleep)

    def fake_connect(url, **kwargs):
        attempts["n"] += 1
        if attempts["n"] == 2:
            return _FakeWS([json.dumps(_make_event())])
        raise OSError("connection refused")

    monkeypatch.setattr(liq, "websockets", SimpleNamespace(connect=fake_connect))

    with patch.object(liq, "write_macro_raw_rows", return_value=(1, 0)) as mock_write, \
         caplog.at_level(logging.WARNING, logger="blackheart_ingest.sources.binance_liquidation"):
        task = asyncio.create_task(run_liquidation_stream(state))
        for _ in range(400):
            if attempts["n"] >= 4 and state.events_received >= 1:
                break
            await real_sleep(0.005)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    # One frame received + parsed on the successful connection.
    assert state.events_received == 1
    assert state.events_parsed == 1

    # refused, success-then-close, refused, refused -> >= 3 reconnect events.
    assert state.reconnect_count >= 3

    # Exponential backoff: 1.0 (refused), 1.0 (reset after success), 2.0, 4.0...
    assert sleeps[:3] == [1.0, 1.0, 2.0]
    if len(sleeps) >= 4:
        assert sleeps[3] == 4.0

    # Reconnect after an outage logs the permanently-lost gap window at WARN.
    warn_messages = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("PERMANENTLY LOST" in m for m in warn_messages)

    # Cancellation drains the buffer -- the received event reached the DB layer.
    mock_write.assert_called()
    assert state.events_written == 1


# -- GET /liquidation/status -----------------------------------------------------


def test_status_endpoint_disabled_returns_enabled_false():
    client = TestClient(app)  # lifespan NOT run; flag defaults to off anyway
    resp = client.get("/liquidation/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is False
    assert "INGEST_LIQUIDATION_STREAM_ENABLED" in body["reason"]


def test_status_endpoint_reports_live_state():
    state = LiquidationStreamState(
        enabled=True, ws_url="wss://unit-test", flush_max_rows=200, flush_seconds=5.0
    )
    state.connected = True
    state.events_received = 10
    state.events_parsed = 9
    state.events_written = 8
    state.events_skipped_duplicate = 1
    state.reconnect_count = 2
    state.last_event_at = datetime(2026, 6, 12, 9, 30, 0)
    state.last_gap_seconds = 12.5

    app.state.liquidation = state
    try:
        resp = TestClient(app).get("/liquidation/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["enabled"] is True
        assert body["connected"] is True
        assert body["ws_url"] == "wss://unit-test"
        assert body["events_received"] == 10
        assert body["events_parsed"] == 9
        assert body["events_written"] == 8
        assert body["events_skipped_duplicate"] == 1
        assert body["reconnect_count"] == 2
        assert body["last_event_at"] == "2026-06-12T09:30:00"
        assert body["last_gap_seconds"] == 12.5
        assert "now" in body
    finally:
        delattr(app.state, "liquidation")


# -- Lifespan wiring: env flag gates the task -------------------------------------


def _settings(**overrides) -> SimpleNamespace:
    base = {
        "compute_auto": False,
        "kafka_enabled": False,
        "liquidation_stream_enabled": False,
        "liquidation_ws_url": "wss://unit-test",
        "liquidation_flush_max_rows": 42,
        "liquidation_flush_seconds": 7.0,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_lifespan_flag_off_starts_no_stream_task():
    test_app = FastAPI()
    with patch(
        "blackheart_ingest.sources.binance_liquidation.run_liquidation_stream"
    ) as mock_run:
        async with _lifespan(_settings(), test_app):
            assert getattr(test_app.state, "liquidation", None) is None
        mock_run.assert_not_called()


@pytest.mark.asyncio
async def test_lifespan_flag_on_starts_stream_and_cancels_on_shutdown():
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def fake_stream(state):
        started.set()
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    test_app = FastAPI()
    with patch(
        "blackheart_ingest.sources.binance_liquidation.run_liquidation_stream",
        new=fake_stream,
    ):
        async with _lifespan(_settings(liquidation_stream_enabled=True), test_app):
            await asyncio.wait_for(started.wait(), timeout=2.0)
            st = test_app.state.liquidation
            assert st.enabled is True
            assert st.ws_url == "wss://unit-test"
            assert st.flush_max_rows == 42
            assert st.flush_seconds == 7.0
    assert cancelled.is_set()


# -- Registry hygiene --------------------------------------------------------------


def test_liquidation_is_not_a_pull_source():
    """The /pull/{source} registry is for one-shot fetch() sources; the
    liquidation stream is lifespan-hosted and must NOT be listed there
    (it has no fetch and would 500 on dispatch)."""
    assert "binance_liquidation" not in _KNOWN_SOURCES
