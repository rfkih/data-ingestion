"""The alert bus: typed rows, dedupe in place, who may see what, and the SSE framing."""
from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime, time, timedelta

import psycopg
import pytest

from blackheart_ingest.idx import prefs, runlog, stream


# -------------------------------------------------------------------------------------------------- pure framing
def test_sse_frames_carry_an_id_and_survive_multiline_data() -> None:
    out = stream.sse("alert", '{"a":1}', event_id=7)
    assert out == 'id: 7\nevent: alert\ndata: {"a":1}\n\n'
    two = stream.sse("gap", "line one\nline two")
    assert two == "event: gap\ndata: line one\ndata: line two\n\n"   # every line needs its own data: prefix


def test_row_json_keeps_timestamps_readable() -> None:
    ts = datetime(2026, 9, 24, 8, 30, tzinfo=UTC)
    doc = json.loads(stream.row_json({"id": 1, "ts": ts, "payload": {"x": 2}, "book": None}))
    assert doc["ts"].startswith("2026-09-24T08:30") and doc["payload"] == {"x": 2} and doc["book"] is None


def test_scoping_never_leaks_another_account() -> None:
    mine, other = "u1", "u2"
    desk = {"id": 1, "job": "feed", "book": None, "user_id": None}
    my_book = {"id": 2, "job": None, "book": "paper_trend", "user_id": None}
    legacy = {"id": 3, "job": "book:paper_trend", "book": None, "user_id": None}
    someone_elses = {"id": 4, "job": None, "book": "live-x", "user_id": None}
    addressed = {"id": 5, "job": None, "book": None, "user_id": other}
    books = {"paper_trend"}
    for row, seen in ((desk, True), (my_book, True), (legacy, True), (someone_elses, False), (addressed, False)):
        assert stream.visible_to(row, books=books, user_id=mine, scoped=True) is seen, row
        assert stream.visible_to(row, books=None, user_id=None, scoped=False) is True, row  # a service sees everything


def test_kind_filter() -> None:
    assert stream.wanted({"kind": "exec"}, {"exec", "ara"}) is True
    assert stream.wanted({"kind": "signal"}, {"exec"}) is False
    assert stream.wanted({"kind": None}, {"ops"}) is True            # an untyped legacy row reads as ops
    assert stream.wanted({"kind": "signal"}, None) is True


# ------------------------------------------------------------------------------------------------------- the hub
@pytest.mark.asyncio
async def test_hub_fans_out_and_tells_a_slow_page_it_fell_behind() -> None:
    h = stream.Hub()
    a, b = asyncio.Queue(maxsize=stream.QUEUE_MAX), asyncio.Queue(maxsize=stream.QUEUE_MAX)
    h._subs.update({a, b})                                           # subscribe() would start the listener; not wanted here
    h.publish({"id": 5, "kind": "signal"})
    assert a.get_nowait()["id"] == 5 and b.get_nowait()["id"] == 5 and h.last_id == 5
    h.unsubscribe(b)
    h.publish({"id": 6, "kind": "ara"})
    assert a.get_nowait()["id"] == 6 and b.empty()
    slow = asyncio.Queue(maxsize=2)
    h._subs = {slow}
    for i in range(4):
        h.publish({"id": 10 + i, "kind": "exec"})
    drained = []
    while not slow.empty():
        drained.append(slow.get_nowait())
    assert None in drained and h.dropped > 0                          # the gap marker, not a silently short stream


@pytest.mark.asyncio
async def test_events_replays_then_streams_and_heartbeats() -> None:
    q: asyncio.Queue = asyncio.Queue()
    replay = [{"id": 1, "kind": "signal", "book": None, "user_id": None, "job": None},
              {"id": 2, "kind": "exec", "book": "live-x", "user_id": None, "job": None}]
    gen = stream.events(q, replay=replay, kinds=None, books={"paper_trend"}, user_id="u1", scoped=True,
                        heartbeat=0.01)
    assert json.loads((await anext(gen)).split("data: ")[1])["replayed"] == 2
    first = await anext(gen)
    assert "id: 1" in first and '"kind": "signal"' in first          # row 2 belongs to another book and is skipped
    assert (await anext(gen)) == ": keep-alive\n\n"                   # nothing to send: a comment keeps the pipe open
    await q.put({"id": 3, "kind": "ara", "book": "paper_trend", "user_id": None, "job": None})
    assert "id: 3" in (await anext(gen))
    await q.put(None)
    assert "event: gap" in (await anext(gen))
    await gen.aclose()


# ------------------------------------------------------------------------------------------- the bus, against a db
@pytest.fixture(scope="module")
def conn():
    dsn = os.environ.get("INGEST_DB_DSN")
    if not dsn:
        pytest.skip("INGEST_DB_DSN not set")
    try:
        c = psycopg.connect(dsn, connect_timeout=5)
    except Exception as e:
        pytest.skip(f"db unreachable: {e}")
    yield c
    c.close()


def _clean(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM idx.alert WHERE job = 'test:bus'")
        cur.execute("DELETE FROM idx.alert_pref WHERE user_id = 'test-user'")
    conn.commit()


def test_typed_alert_dedupes_in_place_and_reads_back(conn) -> None:
    _clean(conn)
    try:
        first = runlog.alert(conn, "info", "test:bus", "leaning up", kind="exec", strategy="exec_timing", code="BBCA",
                             book="paper_trend", payload={"lean": "bid"}, dedupe_key="test:exec:1",
                             valid_until=datetime.now(UTC) + timedelta(seconds=30), notify_channels=False)
        again = runlog.alert(conn, "info", "test:bus", "take the offer", kind="exec", strategy="exec_timing",
                             code="BBCA", book="paper_trend", payload={"lean": "offer"}, dedupe_key="test:exec:1",
                             valid_until=datetime.now(UTC) + timedelta(seconds=30), notify_channels=False)
        assert first == again                                        # one open row per key: updated, never duplicated
        rows = runlog.open_alerts(conn, 50, kind="exec")
        row = next(r for r in rows if r["id"] == first)
        assert row["message"] == "take the offer" and row["payload"] == {"lean": "offer"}
        assert row["strategy"] == "exec_timing" and row["code"] == "BBCA" and row["book"] == "paper_trend"

        # an expired row is clutter, not news: left out unless asked for
        runlog.alert(conn, "info", "test:bus", "stale read", kind="exec", dedupe_key="test:exec:2",
                     valid_until=datetime.now(UTC) - timedelta(seconds=1), notify_channels=False)
        ids = {r["id"] for r in runlog.open_alerts(conn, 50, kind="exec")}
        all_ids = {r["id"] for r in runlog.open_alerts(conn, 50, kind="exec", include_expired=True)}
        assert all_ids - ids                                          # the expired one only shows when asked for

        # filters and `since`, which is what a page uses after a stream gap
        assert all(r["kind"] == "exec" for r in runlog.open_alerts(conn, 50, kind="exec"))
        assert all(r["id"] > first for r in runlog.open_alerts(conn, 50, since=first))
        assert [r["id"] for r in runlog.open_alerts(conn, 50, strategy="exec_timing") if r["id"] == first]

        # an untyped alert still works exactly as it did
        plain = runlog.alert(conn, "warning", "test:bus", "the old shape", notify_channels=False)
        plain_row = next(r for r in runlog.open_alerts(conn, 50) if r["id"] == plain)
        assert plain_row["kind"] is None and plain_row["payload"] is None
    finally:
        _clean(conn)


def test_preferences_mute_a_kind_without_hiding_it_from_the_stream(conn) -> None:
    _clean(conn)
    try:
        assert prefs.allows(conn, "test-user", "exec") is True        # no rows: everything is delivered
        prefs.set_pref(conn, "test-user", kind="exec", muted=True)
        assert prefs.allows(conn, "test-user", "exec") is False
        assert prefs.allows(conn, "test-user", "ara") is True         # the mute is that kind's, not everything's
        assert prefs.allows(conn, None, "exec") is True               # desk news has no owner to have muted it
        prefs.set_pref(conn, "test-user", kind="exec", muted=False)   # unmuting with no quiet hours removes the row
        assert prefs.list_prefs(conn, "test-user") == []
        prefs.set_pref(conn, "test-user", muted=True, quiet_from=time(22, 0), quiet_to=time(7, 0))
        night = datetime(2026, 9, 24, 23, 30, tzinfo=prefs.WIB)
        day = datetime(2026, 9, 24, 10, 0, tzinfo=prefs.WIB)
        assert prefs.allows(conn, "test-user", "ara", now=night) is False
        assert prefs.allows(conn, "test-user", "ara", now=day) is True
    finally:
        _clean(conn)


def test_quiet_hours_window_maths() -> None:
    wrap = {"quiet_from": time(22, 0), "quiet_to": time(7, 0)}
    same_day = {"quiet_from": time(9, 0), "quiet_to": time(17, 0)}
    assert prefs.in_quiet_hours(wrap, time(23, 0)) and prefs.in_quiet_hours(wrap, time(3, 0))
    assert not prefs.in_quiet_hours(wrap, time(12, 0))
    assert prefs.in_quiet_hours(same_day, time(12, 0)) and not prefs.in_quiet_hours(same_day, time(20, 0))
    assert not prefs.in_quiet_hours({"quiet_from": None, "quiet_to": None}, time(3, 0))


# ---------------------------------------------------------------------- the stream route, replay and headers
# httpx's ASGI transport collects a response body before handing it over, so a TestClient cannot read an endless
# one - it simply hangs (measured 2026-09-24). The route is an ordinary coroutine returning a StreamingResponse, so
# it is called directly here and its body iterator is read with a timeout: the same code, without an HTTP server.

def _route(path: str):
    from blackheart_ingest.workers.server import app
    for r in app.routes:
        if getattr(r, "path", None) == path and "GET" in getattr(r, "methods", set()):
            return r.endpoint
    raise AssertionError(f"no GET route {path}")


class _Req:
    """The two things the stream route asks of a Request."""

    def __init__(self, headers: dict[str, str] | None = None):
        self.headers = headers or {}

    async def is_disconnected(self) -> bool:
        return False


def _service_caller():
    from blackheart_ingest.idx.who import Caller
    return Caller(actor="scheduler", user_id=None, email=None, service=True)


async def _frames(resp, want: int, timeout: float = 5.0) -> list[str]:
    """Read `want` complete SSE frames off a StreamingResponse, then stop."""
    sep = "\n\n"
    frames, buf = [], ""
    it = resp.body_iterator.__aiter__()
    while len(frames) < want:
        chunk = await asyncio.wait_for(it.__anext__(), timeout)
        buf += chunk if isinstance(chunk, str) else chunk.decode()
        while sep in buf:
            frame, buf = buf.split(sep, 1)
            if frame.strip():
                frames.append(frame + sep)
    return frames


def _ids(frames: list[str]) -> list[int]:
    return [int(f.split("id: ")[1].split("\n")[0]) for f in frames if f.startswith("id: ")]


@pytest.mark.asyncio
async def test_a_reconnect_replays_exactly_what_it_missed(conn) -> None:
    """The point of `since`: a dropped connection costs latency, never rows."""
    _clean(conn)
    try:
        first = runlog.alert(conn, "info", "test:bus", "one", kind="signal", notify_channels=False)
        second = runlog.alert(conn, "info", "test:bus", "two", kind="signal", notify_channels=False)
        third = runlog.alert(conn, "info", "test:bus", "three", kind="signal", notify_channels=False)
        route = _route("/idx/stream")

        resp = await route(_Req(), since=first, kinds="signal", c=_service_caller())
        assert resp.media_type == "text/event-stream"
        assert "no-cache" in resp.headers["cache-control"] and resp.headers["x-accel-buffering"] == "no"
        frames = await _frames(resp, 3)
        assert frames[0].startswith("event: hello")
        assert _ids(frames[1:]) == [second, third]            # in order, and the row it already had is not repeated
        await resp.body_iterator.aclose()

        # the browser's own header is read when the query string does not say
        resp2 = await route(_Req({"last-event-id": str(second)}), since=None, kinds="signal", c=_service_caller())
        frames2 = await _frames(resp2, 2)
        assert _ids(frames2[1:]) == [third]
        await resp2.body_iterator.aclose()
    finally:
        _clean(conn)


@pytest.mark.asyncio
async def test_the_kind_filter_applies_to_the_replay_too(conn) -> None:
    _clean(conn)
    try:
        base = runlog.alert(conn, "info", "test:bus", "anchor", kind="ops", notify_channels=False)
        runlog.alert(conn, "info", "test:bus", "an ara touch", kind="ara", code="BBCA", notify_channels=False)
        wanted_id = runlog.alert(conn, "info", "test:bus", "a signal", kind="signal", notify_channels=False)
        resp = await _route("/idx/stream")(_Req(), since=base, kinds="signal", c=_service_caller())
        frames = await _frames(resp, 2)
        assert _ids(frames[1:]) == [wanted_id]
        await resp.body_iterator.aclose()
    finally:
        _clean(conn)


@pytest.mark.asyncio
async def test_a_page_with_no_since_starts_from_now(conn) -> None:
    """No `since` means no replay: a fresh page shows what the API gave it, not a week of history."""
    _clean(conn)
    try:
        runlog.alert(conn, "info", "test:bus", "before", kind="signal", notify_channels=False)
        resp = await _route("/idx/stream")(_Req(), since=None, kinds=None, c=_service_caller())
        frames = await _frames(resp, 1)
        assert json.loads(frames[0].split("data: ")[1])["replayed"] == 0
        await resp.body_iterator.aclose()
    finally:
        _clean(conn)


def test_status_says_whether_this_worker_is_listening() -> None:
    body = _route("/idx/stream/status")()
    assert set(body) == {"connected", "subscribers", "last_id", "dropped"}
    assert isinstance(body["connected"], bool) and body["subscribers"] >= 0
