"""Binance USDT-M futures liquidation stream -> ``macro_raw``.

Always-on accrual worker for the all-market force-liquidation websocket:

    wss://fstream.binance.com/market/ws/!forceOrder@arr

Liquidation events are **not backfillable** -- Binance exposes no historical
endpoint -- so every hour the stream is down is an hour of history lost
forever (Alpha Surface Expansion Plan 2026-06-12, WS-D1). Hence:

* the worker runs as an asyncio task inside the served app's lifespan
  (``workers/server.py`` -- NOT the dead ``app.py``);
* auto-reconnect with exponential backoff + jitter;
* a disconnect window is logged at WARN as a permanently-lost gap;
* status surfaced via ``GET /liquidation/status`` for the operator.

Default OFF: set ``INGEST_LIQUIDATION_STREAM_ENABLED=true`` to start
accruing (mirrors the blackheart-inference streaming-worker convention).

Persistence -- one ``macro_raw`` row per liquidation order:

    source       = 'binance_liquidation'
    symbol       = e.g. 'BTCUSDT'            (ALL symbols accrued -- no filter)
    series_id    = 'binance_liquidation_<symbol_lower>'
    event_time   = order trade time (``o.T``, ms -> naive UTC)
    value        = notional in USDT (price x original qty)
    value_text   = compact JSON {side, price, qty, avgPrice, orderStatus}
    content_hash = sha256 over the identifying fields (dedupe)

``source_uri`` embeds the event-time ms AND a hash fragment: ``macro_raw``
has a UNIQUE index on (source, source_uri, event_time), and two same-symbol
liquidations can theoretically share a millisecond -- a series-level
source_uri would silently drop the second row via ON CONFLICT DO NOTHING
(the historical binance_orderbook bug; see ``_store_macro_series`` there).

Rows are buffered and flushed in batches (size- or time-triggered) through
``write_macro_raw_rows`` (executemany, single round-trip). A failed flush
retains the rows for retry on the next trigger -- bounded by a hard cap so
a long DB outage cannot grow memory without limit.

Volume note: Binance throttles ``!forceOrder@arr`` to at most one event per
symbol per second, so throughput is modest even in a cascade.

NOT registered in ``_KNOWN_SOURCES``: that registry is for one-shot
``fetch(request)`` pull sources dispatched via ``POST /pull/{source}``.
This module is a streaming worker with no ``fetch``. PIT guards are also
skipped -- events arrive in real time by construction.

``ml_source_health`` is not updated (no V67-style seed row exists for this
source; adding one is a trading-engine Flyway concern). The status endpoint
is the observability surface.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import websockets

from ..shared.db import content_hash, write_macro_raw_rows

logger = logging.getLogger(__name__)

name = "binance_liquidation"
raw_table = "macro_raw"

# /market/ is REQUIRED (2026-04-23 Binance WS migration): forceOrder is a
# "market"-category stream. The legacy /ws/ path still ACCEPTS connections
# and acks SUBSCRIBE but pushes NO data -- it fails silently, not loudly.
DEFAULT_WS_URL = "wss://fstream.binance.com/market/ws/!forceOrder@arr"

# Reconnect backoff: initial x 2^n, capped, +/-50% jitter. Reset on connect.
_BACKOFF_INITIAL_SECONDS = 1.0
_BACKOFF_MAX_SECONDS = 60.0
_BACKOFF_JITTER = 0.5

# recv() poll timeout so time-based flushes fire during quiet markets.
_RECV_POLL_SECONDS = 1.0

# Binance sends a ping every ~3 min and closes idle/unresponsive sockets;
# the websockets client auto-pongs. Client-side pings keep NATs warm.
_PING_INTERVAL_SECONDS = 20.0
_PING_TIMEOUT_SECONDS = 20.0

# If the DB is down for a long stretch, retain at most this many rows in
# memory before dropping the OLDEST (newest data wins -- a cascade in
# progress matters more than the stale head of the buffer).
_BUFFER_HARD_CAP = 50_000


def _utcnow() -> datetime:
    """Naive-UTC now (project convention for DB timestamps)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# -- Event -> macro_raw row mapping -------------------------------------------


def parse_force_order_event(
    payload: dict[str, Any],
    *,
    ingestion_time: datetime | None = None,
) -> dict[str, Any] | None:
    """Map one decoded ``forceOrder`` event object to a ``macro_raw`` row.

    Returns ``None`` for anything that is not a well-formed forceOrder
    event (wrong ``e`` type, missing order block, unparseable numerics) --
    the stream must never die on a malformed frame.
    """
    if not isinstance(payload, dict):
        return None
    # Combined-stream framing ({"stream": ..., "data": {...}}) -- defensive;
    # we connect via /ws/ which sends the raw event, but unwrap if present.
    if "data" in payload and "e" not in payload:
        payload = payload["data"]
        if not isinstance(payload, dict):
            return None
    if payload.get("e") != "forceOrder":
        return None
    order = payload.get("o")
    if not isinstance(order, dict):
        return None

    symbol_raw = order.get("s")
    price = _to_float(order.get("p"))
    qty = _to_float(order.get("q"))
    trade_time_ms = order.get("T")
    if not isinstance(trade_time_ms, (int, float)):
        trade_time_ms = payload.get("E")  # fall back to event time
    if not symbol_raw or price is None or qty is None or not isinstance(
        trade_time_ms, (int, float)
    ):
        return None

    symbol = str(symbol_raw).upper()
    event_ms = int(trade_time_ms)
    event_time = datetime.fromtimestamp(event_ms / 1000.0, tz=timezone.utc).replace(tzinfo=None)
    series_id = f"binance_liquidation_{symbol.lower()}"

    side = order.get("S")
    avg_price = _to_float(order.get("ap"))
    order_status = order.get("X")
    notional = price * qty

    digest = content_hash(series_id, event_ms, side, price, qty, avg_price, order_status)
    value_text = json.dumps(
        {
            "side": side,
            "price": price,
            "qty": qty,
            "avgPrice": avg_price,
            "orderStatus": order_status,
        },
        separators=(",", ":"),
    )

    return {
        "source": name,
        # ms timestamp + hash fragment keeps (source, source_uri, event_time)
        # unique even when two same-symbol events share a millisecond --
        # see the uq_macro_raw_source_uri lesson in the module docstring.
        "source_uri": f"binance/forceOrder/{symbol}/{event_ms}/{digest[:16]}",
        "symbol": symbol,
        "series_id": series_id,
        "event_time": event_time,
        "ingestion_time": ingestion_time if ingestion_time is not None else _utcnow(),
        "value": notional,
        "value_text": value_text,
        "content_hash": digest,
        "schema_version": 1,
    }


def parse_force_order_message(
    message: str | bytes | dict[str, Any] | list[Any],
    *,
    ingestion_time: datetime | None = None,
) -> list[dict[str, Any]]:
    """Decode one websocket frame into zero or more ``macro_raw`` rows.

    Accepts a raw JSON str/bytes frame or an already-decoded object.
    Despite the ``@arr`` stream name Binance pushes one event object per
    frame, but a JSON array is handled too (defensive).
    """
    if isinstance(message, (str, bytes)):
        try:
            message = json.loads(message)
        except (ValueError, TypeError):
            logger.warning("binance_liquidation: undecodable frame dropped")
            return []
    items: list[Any] = message if isinstance(message, list) else [message]
    rows: list[dict[str, Any]] = []
    for item in items:
        row = parse_force_order_event(item, ingestion_time=ingestion_time)
        if row is not None:
            rows.append(row)
    return rows


# -- Batching buffer -----------------------------------------------------------


class _RowBuffer:
    """Accumulates rows; flush is due at ``max_rows`` or ``flush_seconds``
    after the first buffered row (monotonic clock), whichever comes first."""

    def __init__(
        self,
        *,
        max_rows: int,
        flush_seconds: float,
        hard_cap: int = _BUFFER_HARD_CAP,
    ) -> None:
        self.max_rows = max(1, int(max_rows))
        self.flush_seconds = float(flush_seconds)
        self.hard_cap = max(self.max_rows, int(hard_cap))
        self.rows: list[dict[str, Any]] = []
        self.dropped_overflow = 0
        self._deadline: float | None = None

    def add(self, row: dict[str, Any], *, now: float) -> None:
        if not self.rows:
            self._deadline = now + self.flush_seconds
        self.rows.append(row)
        if len(self.rows) > self.hard_cap:
            overflow = len(self.rows) - self.hard_cap
            self.rows = self.rows[overflow:]
            self.dropped_overflow += overflow
            logger.warning(
                "binance_liquidation buffer hard cap %d hit -- dropped %d oldest row(s) "
                "(total dropped=%d). Is the DB reachable?",
                self.hard_cap, overflow, self.dropped_overflow,
            )

    def due(self, *, now: float) -> bool:
        if not self.rows:
            return False
        if len(self.rows) >= self.max_rows:
            return True
        return self._deadline is not None and now >= self._deadline

    def drain(self) -> list[dict[str, Any]]:
        rows = self.rows
        self.rows = []
        self._deadline = None
        return rows

    def restore(self, rows: list[dict[str, Any]], *, now: float | None = None) -> None:
        """Re-queue rows at the FRONT after a failed flush; next retry waits
        one flush interval rather than hot-looping against a down DB."""
        self.rows[:0] = rows
        self._deadline = (now if now is not None else time.monotonic()) + self.flush_seconds


# -- Worker state (config + rolling status; exposed via /liquidation/status) --


@dataclass
class LiquidationStreamState:
    enabled: bool
    ws_url: str = DEFAULT_WS_URL
    flush_max_rows: int = 200
    flush_seconds: float = 5.0
    started_at: datetime | None = None
    connected: bool = False
    connected_at: datetime | None = None
    last_message_at: datetime | None = None   # wall clock of last received frame
    last_event_at: datetime | None = None     # exchange event_time of last parsed event
    last_flush_at: datetime | None = None
    events_received: int = 0                  # frames received
    events_parsed: int = 0                    # valid liquidation rows parsed
    events_written: int = 0                   # rows inserted into macro_raw
    events_skipped_duplicate: int = 0         # ON CONFLICT DO NOTHING skips
    rows_buffered: int = 0
    rows_dropped_overflow: int = 0
    flushes: int = 0
    reconnect_count: int = 0                  # disconnects / failed connect attempts
    last_disconnect_at: datetime | None = None
    last_gap_seconds: float | None = None     # last permanently-lost window length
    last_error: str | None = None
    last_error_at: datetime | None = None


# -- Stream loop ----------------------------------------------------------------


def _mark_connected(state: LiquidationStreamState) -> None:
    now = _utcnow()
    state.connected = True
    state.connected_at = now
    if state.last_disconnect_at is not None:
        # Events between the last received frame and now are gone forever --
        # Binance has no historical liquidation endpoint.
        gap_start = state.last_message_at or state.last_disconnect_at
        gap_seconds = max(0.0, (now - gap_start).total_seconds())
        state.last_gap_seconds = gap_seconds
        logger.warning(
            "binance_liquidation reconnected -- gap window %s -> %s (%.1fs) "
            "is PERMANENTLY LOST (liquidations are not backfillable) | reconnects=%d",
            gap_start.isoformat(), now.isoformat(), gap_seconds, state.reconnect_count,
        )
    else:
        logger.info("binance_liquidation stream connected | url=%s", state.ws_url)


def _mark_disconnected(state: LiquidationStreamState, exc: BaseException) -> None:
    state.connected = False
    state.last_disconnect_at = _utcnow()
    state.reconnect_count += 1
    state.last_error = repr(exc)[:300]
    state.last_error_at = state.last_disconnect_at


def _handle_message(
    message: str | bytes | dict[str, Any],
    state: LiquidationStreamState,
    buffer: _RowBuffer,
) -> None:
    state.events_received += 1
    state.last_message_at = _utcnow()
    for row in parse_force_order_message(message):
        state.events_parsed += 1
        state.last_event_at = row["event_time"]
        buffer.add(row, now=time.monotonic())
    state.rows_buffered = len(buffer.rows)
    state.rows_dropped_overflow = buffer.dropped_overflow


async def _flush(buffer: _RowBuffer, state: LiquidationStreamState) -> None:
    """Drain the buffer into macro_raw. On failure the rows are restored
    for retry on the next trigger -- never raises (except cancellation)."""
    rows = buffer.drain()
    if not rows:
        return
    try:
        # write_macro_raw_rows is sync psycopg -- keep the event loop free.
        inserted, skipped = await asyncio.to_thread(write_macro_raw_rows, rows)
    except Exception as exc:  # noqa: BLE001 -- CancelledError propagates (BaseException)
        buffer.restore(rows)
        state.rows_buffered = len(buffer.rows)
        state.last_error = f"flush: {exc!r}"[:300]
        state.last_error_at = _utcnow()
        logger.exception(
            "binance_liquidation flush failed -- %d row(s) retained for retry", len(rows)
        )
        return
    state.events_written += inserted
    state.events_skipped_duplicate += skipped
    state.flushes += 1
    state.last_flush_at = _utcnow()
    state.rows_buffered = len(buffer.rows)
    logger.info(
        "binance_liquidation flush | rows=%d inserted=%d skipped_dup=%d total_written=%d",
        len(rows), inserted, skipped, state.events_written,
    )


async def _consume(ws: Any, state: LiquidationStreamState, buffer: _RowBuffer) -> None:
    """Receive loop for one connection. Returns only by raising -- the
    connection-closed exception bubbles to the reconnect handler."""
    while True:
        try:
            message = await asyncio.wait_for(ws.recv(), timeout=_RECV_POLL_SECONDS)
        except TimeoutError:
            message = None  # quiet market -- fall through to the time-based flush check
        if message is not None:
            _handle_message(message, state, buffer)
        if buffer.due(now=time.monotonic()):
            await _flush(buffer, state)


async def run_liquidation_stream(state: LiquidationStreamState) -> None:
    """Long-running loop started from the server lifespan when
    ``INGEST_LIQUIDATION_STREAM_ENABLED=true``. Exits only on cancellation;
    every connection error reconnects with exponential backoff + jitter.
    """
    state.started_at = _utcnow()
    buffer = _RowBuffer(max_rows=state.flush_max_rows, flush_seconds=state.flush_seconds)
    backoff = _BACKOFF_INITIAL_SECONDS
    logger.info(
        "binance_liquidation stream starting | url=%s flush_max_rows=%d flush_seconds=%.1f",
        state.ws_url, state.flush_max_rows, state.flush_seconds,
    )
    try:
        while True:
            try:
                async with websockets.connect(
                    state.ws_url,
                    ping_interval=_PING_INTERVAL_SECONDS,
                    ping_timeout=_PING_TIMEOUT_SECONDS,
                    max_queue=4096,
                ) as ws:
                    _mark_connected(state)
                    backoff = _BACKOFF_INITIAL_SECONDS
                    await _consume(ws, state, buffer)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 -- any WS/connect error -> backoff+retry
                _mark_disconnected(state, exc)
                delay = backoff * random.uniform(1.0 - _BACKOFF_JITTER, 1.0 + _BACKOFF_JITTER)
                logger.warning(
                    "binance_liquidation stream down -- events during the outage are "
                    "permanently lost | error=%s reconnect_in=%.1fs reconnects=%d",
                    repr(exc)[:200], delay, state.reconnect_count,
                )
                await asyncio.sleep(delay)
                backoff = min(backoff * 2.0, _BACKOFF_MAX_SECONDS)
    except asyncio.CancelledError:
        # Best-effort drain so buffered rows survive a clean shutdown.
        await _flush(buffer, state)
        state.connected = False
        logger.info(
            "binance_liquidation stream cancelled | events_written=%d reconnects=%d",
            state.events_written, state.reconnect_count,
        )
        raise
