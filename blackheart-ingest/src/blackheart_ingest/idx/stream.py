"""The alert stream: one Postgres LISTEN per worker process, fanned out to every open browser.

Phase 2 of the strategies + alert-stream plan. A producer inserts into ``idx.alert``; a trigger fires
``pg_notify('idx_alert', id)``; this module holds the single listening connection and pushes the row to every
subscriber's queue. Server-sent events carry it to the page.

Why this shape:

* **One listener, many subscribers.** A connection per browser tab would put a Postgres backend behind every open
  laptop. The hub is started lazily by the first subscriber and kept for the life of the process.
* **SSE, not a websocket.** The traffic is one-way, the browser reconnects on its own, and a reconnect can say where it
  got to (``Last-Event-ID`` / ``?since=``) so nothing is silently lost across a dropped connection.
* **The queue is bounded.** A slow tab must not grow the server's memory: past ``QUEUE_MAX`` its oldest rows are
  dropped and it is told (``event: gap``) to re-sync with ``since`` rather than being fed a quietly incomplete stream.
* **No preferences here.** An open page is somebody looking on purpose; mutes and quiet hours belong to the phone
  channel (``idx/prefs.py``). The stream filters only by what the caller is allowed to see and by the kinds they asked for.
* **The listener is a thread, not a coroutine.** psycopg's async mode refuses to run on Windows' default
  ProactorEventLoop (measured 2026-09-24: ``InterfaceError`` on every connect), and the desk runs on Windows. A daemon
  thread with an ordinary sync connection behaves the same on both platforms and needs no surgery on the event loop
  the rest of the server uses; it hands rows back with ``call_soon_threadsafe``.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import threading
import time
from collections.abc import AsyncIterator
from datetime import date, datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row

from ..shared.settings import get_settings
from .runlog import ALERT_COLS

logger = logging.getLogger(__name__)

CHANNEL = "idx_alert"
QUEUE_MAX = 200                 # rows a single slow subscriber may fall behind before it is told to re-sync
HEARTBEAT_S = 15.0              # a comment line often enough to keep proxies from closing an idle connection
RECONNECT_S = 3.0
REPLAY_MAX = 200


def _jsonable(v: Any) -> Any:
    if isinstance(v, datetime | date):
        return v.isoformat()
    return v


def row_json(row: dict[str, Any]) -> str:
    return json.dumps({k: _jsonable(v) for k, v in row.items()}, default=str)


def sse(event: str, data: str, *, event_id: int | None = None) -> str:
    """One server-sent event. The id lets the browser resume with Last-Event-ID after a dropped connection."""
    head = f"id: {event_id}\n" if event_id is not None else ""
    body = "\n".join(f"data: {line}" for line in data.split("\n"))
    return f"{head}event: {event}\n{body}\n\n"


class Hub:
    """The process-wide listener. ``subscribe()`` yields a queue that receives every alert row as it lands."""

    def __init__(self) -> None:
        self._subs: set[asyncio.Queue[dict[str, Any] | None]] = set()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._ready = threading.Event()
        self._stop = threading.Event()
        self.connected = False
        self.last_id = 0
        self.dropped = 0

    # -- subscription ------------------------------------------------------------------------------------------
    def subscribe(self) -> asyncio.Queue[dict[str, Any] | None]:
        q: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(maxsize=QUEUE_MAX)
        self._subs.add(q)
        self._loop = asyncio.get_running_loop()
        if self._thread is None or not self._thread.is_alive():
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="idx-alert-listener", daemon=True)
            self._thread.start()
        return q

    def unsubscribe(self, q: asyncio.Queue[dict[str, Any] | None]) -> None:
        self._subs.discard(q)

    def publish(self, row: dict[str, Any]) -> None:
        """Hand one row to every subscriber; a queue that is full loses its oldest row and is sent a gap marker.
        Runs on the event loop thread (the listener hands rows over with ``call_soon_threadsafe``)."""
        self.last_id = max(self.last_id, int(row.get("id") or 0))
        for q in list(self._subs):
            try:
                q.put_nowait(row)
            except asyncio.QueueFull:
                self.dropped += 1
                with contextlib.suppress(asyncio.QueueEmpty):
                    q.get_nowait()                                  # drop the oldest, keep the newest
                with contextlib.suppress(asyncio.QueueFull):
                    q.put_nowait(None)                              # None = "you missed rows, re-sync with ?since="

    def _hand_over(self, row: dict[str, Any]) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        loop.call_soon_threadsafe(self.publish, row)

    # -- the listening thread ----------------------------------------------------------------------------------
    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._listen_once()
            except Exception:
                self.connected = False
                logger.exception("idx stream: listener failed; reconnecting in %.0fs", RECONNECT_S)
                self._stop.wait(RECONNECT_S)

    def _listen_once(self) -> None:
        kwargs = get_settings().db_kwargs()
        with (psycopg.connect(**kwargs, autocommit=True, row_factory=dict_row) as listen,
              psycopg.connect(**kwargs, autocommit=True, row_factory=dict_row) as reader):
            listen.execute(f"LISTEN {CHANNEL}")
            self.connected = True
            self._ready.set()
            logger.info("idx stream: listening on %s", CHANNEL)
            while not self._stop.is_set():
                for note in listen.notifies(timeout=1.0):            # returns on the timeout so the thread can stop
                    try:
                        alert_id = int(note.payload)
                    except (TypeError, ValueError):
                        continue
                    with reader.cursor() as cur:
                        cur.execute(f"SELECT {', '.join(ALERT_COLS)} FROM idx.alert WHERE id = %s", (alert_id,))
                        row = cur.fetchone()
                    if row:
                        self._hand_over(dict(row))
        self.connected = False

    async def wait_ready(self, timeout: float = 5.0) -> bool:
        """Give the listener a moment to come up, without blocking the event loop while it does."""
        deadline = time.monotonic() + timeout
        while not self._ready.is_set() and time.monotonic() < deadline:
            await asyncio.sleep(0.05)
        return self.connected

    def stop(self) -> None:
        self._stop.set()

    def status(self) -> dict[str, Any]:
        return {"connected": self.connected, "subscribers": len(self._subs), "last_id": self.last_id,
                "dropped": self.dropped}


_hub: Hub | None = None


def hub() -> Hub:
    global _hub
    if _hub is None:
        _hub = Hub()
    return _hub


# -- what a subscriber is allowed to see ---------------------------------------------------------------------------
def visible_to(row: dict[str, Any], *, books: set[str] | None, user_id: str | None, scoped: bool) -> bool:
    """A service sees everything. A person sees the desk's own rows plus anything about their books or addressed to
    them - never another account's position. The ``book:X`` / ``ticket:X`` job convention is read too, so the rows that
    predate the typed columns are scoped the same way."""
    if not scoped:
        return True
    owner = row.get("user_id")
    if owner and owner != user_id:
        return False
    book = row.get("book") or _book_from_job(row.get("job"))
    if book is None:
        return True
    return book in (books or set())


def _book_from_job(job: str | None) -> str | None:
    if job and ":" in job and job.split(":", 1)[0] in ("book", "ticket"):
        return job.split(":", 1)[1]
    return None


def wanted(row: dict[str, Any], kinds: set[str] | None) -> bool:
    if not kinds:
        return True
    return (row.get("kind") or "ops") in kinds


async def events(queue: asyncio.Queue[dict[str, Any] | None], *, replay: list[dict[str, Any]], kinds: set[str] | None,
                 books: set[str] | None, user_id: str | None, scoped: bool,
                 heartbeat: float = HEARTBEAT_S) -> AsyncIterator[str]:
    """The SSE body: what was missed, then everything as it lands, with a heartbeat in the quiet."""
    yield sse("hello", json.dumps({"connected": hub().connected, "replayed": len(replay)}))
    for row in replay:
        if wanted(row, kinds) and visible_to(row, books=books, user_id=user_id, scoped=scoped):
            yield sse("alert", row_json(row), event_id=int(row["id"]))
    while True:
        try:
            item = await asyncio.wait_for(queue.get(), timeout=heartbeat)
        except TimeoutError:
            yield ": keep-alive\n\n"                                  # a comment: valid SSE, ignored by the client
            continue
        if item is None:
            yield sse("gap", json.dumps({"reason": "the connection fell behind; reconnect with ?since="}))
            continue
        if wanted(item, kinds) and visible_to(item, books=books, user_id=user_id, scoped=scoped):
            yield sse("alert", row_json(item), event_id=int(item["id"]))
