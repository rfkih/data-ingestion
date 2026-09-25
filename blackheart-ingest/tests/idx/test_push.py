"""Phone push (Papan app via FCM): the message shape, the service-account token exchange with a fake endpoint, device
registration and the fan-out that disables tokens FCM reports gone; notify's split of a text into title/body and its
fan-out to the app channel."""
from __future__ import annotations

import json
import os
import uuid

import psycopg
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from blackheart_ingest.idx import notify, push


@pytest.fixture
def sa_file(tmp_path, monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_key_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode() \
        if hasattr(key, "private_key_bytes") else key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    p = tmp_path / "sa.json"
    p.write_text(json.dumps({"project_id": "papan-test", "client_email": "svc@papan-test.iam.gserviceaccount.com", "private_key": pem}))
    monkeypatch.setenv(push.SA_ENV, str(p))
    monkeypatch.setattr(push, "_sa", None)
    monkeypatch.setattr(push, "_tok", {"value": None, "exp": 0.0})
    return p


def test_unconfigured_is_a_noop(monkeypatch) -> None:
    monkeypatch.delenv(push.SA_ENV, raising=False)
    assert not push.configured() and push.broadcast("t", "b")["sent"] == 0
    monkeypatch.setenv(push.SA_ENV, "C:/nowhere/sa.json")
    assert not push.configured()                                          # the file must exist


def test_message_shape_stringifies_data() -> None:
    m = push.message("tok", "Ticket #9", "BUY AYAM 19 lot", {"route": "/m/ticket?book=trend_live", "ticket": 9, "none": None})["message"]
    assert m["token"] == "tok" and m["notification"] == {"title": "Ticket #9", "body": "BUY AYAM 19 lot"}
    assert m["data"] == {"route": "/m/ticket?book=trend_live", "ticket": "9"} and m["android"]["notification"]["channel_id"] == push.CHANNEL_ID


def test_token_exchange_signs_a_jwt_and_caches(sa_file) -> None:
    calls = []

    def sender(url, payload, headers):
        calls.append((url, payload, headers))
        assert url == push.TOKEN_URL and payload["grant_type"].endswith("jwt-bearer")
        _head, claims, sig = payload["assertion"].split(".")
        c = json.loads(push.base64.urlsafe_b64decode(claims + "=="))
        assert c["iss"] == "svc@papan-test.iam.gserviceaccount.com" and c["scope"] == push.SCOPE and c["exp"] - c["iat"] == 3600 and sig
        return 200, {"access_token": "ya29.x", "expires_in": 3599}

    assert push.access_token(sender=sender, now=1_000_000) == "ya29.x"
    assert push.access_token(sender=sender, now=1_000_100) == "ya29.x" and len(calls) == 1        # cached
    assert push.access_token(sender=sender, now=1_003_600) == "ya29.x" and len(calls) == 2        # refreshed near expiry
    with pytest.raises(RuntimeError, match="token exchange failed"):
        push._tok.update(value=None, exp=0.0)
        push.access_token(sender=lambda u, p, h: (400, {"error": "invalid_grant"}), now=1_000_000)


def test_send_one_classifies_errors(sa_file) -> None:
    ok = push.send_one("tok", "t", "b", sender=lambda u, p, h: (200, {"name": "projects/papan-test/messages/1"}), bearer="x")
    assert ok == {"ok": True, "gone": False, "error": None}
    gone = push.send_one("tok", "t", "b", sender=lambda u, p, h: (404, {"error": {"status": "NOT_FOUND", "message": "Requested entity was not found.",
                                                                                   "details": [{"errorCode": "UNREGISTERED"}]}}), bearer="x")
    assert not gone["ok"] and gone["gone"] and "NOT_FOUND" in gone["error"]
    auth = push.send_one("tok", "t", "b", sender=lambda u, p, h: (401, {"error": {"status": "UNAUTHENTICATED", "message": "bad"}}), bearer="x")
    assert not auth["ok"] and not auth["gone"]


def test_notify_split_title() -> None:
    assert notify.split_title("drafted by scheduler\nTicket #9 trend_live trend (draft)\nBUY AYAM") == ("drafted by scheduler", "Ticket #9 trend_live trend (draft)\nBUY AYAM")
    assert notify.split_title("one liner") == ("one liner", "one liner")
    assert notify.split_title("x\ny", "Given") == ("Given", "x\ny")
    assert notify.ticket_data({"id": 3, "book": "trend_live"}) == {"route": "/m/ticket?book=trend_live", "kind": "ticket", "book": "trend_live", "ticket": 3}


def _fake_broadcast(calls, devices_of):
    """push.broadcast with a device count per account: {user_id or None: n}."""
    def broadcast(title, body, data=None, *, sender=None, user_id=None):
        n = devices_of.get(user_id, 0)
        calls.append({"user_id": user_id, "title": title, "devices": n})
        return {"sent": n, "failed": 0, "gone": 0, "devices": n, "configured": True}
    return broadcast


def test_desk_alert_falls_back_to_every_phone(monkeypatch) -> None:
    """The 2026-09-24 silent outage: the ops account had no phone (the only one was signed in as another account), so
    twelve feed-down alerts went nowhere. Desk news now reaches every phone on the desk rather than being dropped."""
    calls: list[dict] = []
    monkeypatch.setattr(push, "configured", lambda: True)
    monkeypatch.delenv(notify.TOKEN_ENV, raising=False)
    monkeypatch.setenv(notify.OPS_ENV, "ops@example.com")
    monkeypatch.setattr(notify, "ops_user_id", lambda: "ops-uid")
    monkeypatch.setattr(notify, "owner_of", lambda book: "owner-uid" if book == "someones-book" else None)
    monkeypatch.setattr(push, "broadcast", _fake_broadcast(calls, {None: 1}))          # one phone, on neither account

    assert notify.on_alert("warning", "feed", "stockbit/feed: DOWN - last frame 50614s ago")
    assert [c["user_id"] for c in calls] == ["ops-uid", None]                          # tried ops, then the whole desk
    assert calls[-1]["title"] == "[WARNING] feed"

    calls.clear()                                                                      # a book alert stays with its owner
    assert notify.on_alert("critical", "book:someones-book", "level hit") is False
    assert [c["user_id"] for c in calls] == ["owner-uid"]

    calls.clear()                                                                      # ops account unset: still desk news
    monkeypatch.setattr(notify, "ops_user_id", lambda: None)
    assert notify.send("feed is back")
    assert [c["user_id"] for c in calls] == [None]

    calls.clear()                                                                      # a database hiccup is not "no phone"
    monkeypatch.setattr(notify, "ops_user_id", lambda: "ops-uid")
    monkeypatch.setattr(push, "broadcast", lambda t, b, d=None, *, sender=None, user_id=None: {
        "sent": 0, "devices": 0, "configured": True, "error": "OperationalError: connection refused"})
    assert notify.send("feed is down") is False


def test_send_all_says_when_nothing_is_registered(conn, sa_file, caplog) -> None:
    """A push with no device to land on is a warning in the log, not a silent return."""
    with caplog.at_level("WARNING"):
        rep = push.send_all(conn, "Feed", "DOWN", user_id=str(uuid.uuid4()))
    assert rep["devices"] == 0 and rep["sent"] == 0
    assert any("no enabled device" in r.getMessage() for r in caplog.records)


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


def _clean(conn):
    with conn.cursor() as cur:
        cur.execute("DELETE FROM idx.push_device WHERE token LIKE 'test-device-%'")
    conn.commit()


def test_devices_round_trip_and_fan_out(conn, sa_file, monkeypatch) -> None:
    _clean(conn)
    try:
        with pytest.raises(ValueError):
            push.register(conn, "short")
        uid = str(uuid.uuid4())
        a = push.register(conn, "test-device-aaaaaaaaaaaaaaaaaaaa", username="rifki", label="Pixel / papan 1.2", user_id=uid)
        b = push.register(conn, "test-device-bbbbbbbbbbbbbbbbbbbb", user_id=uid)
        assert a["username"] == "rifki" and a["label"].startswith("Pixel") and b["username"] is None
        again = push.register(conn, a["token"])                                                  # idempotent, keeps what it knew
        assert again["username"] == "rifki" and again["label"] == a["label"]
        toks = {d["token"] for d in push.devices(conn) if d["token"].startswith("test-device-")}
        assert toks == {a["token"], b["token"]}

        sent = []

        def sender(url, payload, headers):
            if url == push.TOKEN_URL:
                return 200, {"access_token": "ya29.t", "expires_in": 3600}
            assert headers["Authorization"] == "Bearer ya29.t" and url.endswith("/projects/papan-test/messages:send")
            tok = payload["message"]["token"]
            sent.append(tok)
            if tok == b["token"]:
                return 404, {"error": {"status": "NOT_FOUND", "details": [{"errorCode": "UNREGISTERED"}]}}
            return 200, {"name": "ok"}

        rep = push.send_all(conn, "Papan", "hello", {"route": "/m"}, sender=sender)
        mine = [t for t in sent if t.startswith("test-device-")]
        assert set(mine) == {a["token"], b["token"]} and rep["sent"] >= 1 and rep["gone"] == 1
        live = {d["token"]: d for d in push.devices(conn, include_disabled=True) if d["token"].startswith("test-device-")}
        assert not live[a["token"]]["disabled"] and live[a["token"]]["last_sent"] is not None
        assert live[b["token"]]["disabled"] and "NOT_FOUND" in live[b["token"]]["error"]
        assert b["token"] not in {d["token"] for d in push.devices(conn)}                       # gone: skipped from now on
        assert push.register(conn, b["token"])["token"] == b["token"] and b["token"] in {d["token"] for d in push.devices(conn)}   # re-register revives

        # notify fans out to the app channel with a title/body split and the route in the data
        monkeypatch.delenv(notify.TOKEN_ENV, raising=False)
        got = []

        def psender(url, payload, headers):
            if url == push.TOKEN_URL:
                return 200, {"access_token": "ya29.t", "expires_in": 3600}
            got.append(payload["message"])
            return 200, {"name": "ok"}

        monkeypatch.setattr(push, "broadcast", lambda t, b_, d=None, sender=None, user_id=None: push.send_all(conn, t, b_, d, sender=psender, user_id=user_id))
        monkeypatch.setattr(notify, "owner_of", lambda book: uid if book == "test-book" else None)
        monkeypatch.delenv(notify.OPS_ENV, raising=False)
        assert notify.channels() == ["app"] and notify.configured()
        assert notify.send("drafted by scheduler\nTicket #9 trend_live", data={"route": "/m/ticket?book=trend_live"}, user_id=uid)
        m = next(x for x in got if x["token"] == a["token"])
        assert m["notification"] == {"title": "drafted by scheduler", "body": "Ticket #9 trend_live"} and m["data"]["route"] == "/m/ticket?book=trend_live"
        assert notify.on_alert("critical", "book:test-book", "level hit") and any(x["notification"]["title"] == "[CRITICAL] book:test-book" for x in got)
        assert notify.on_alert("info", "book:live", "quiet") is False
        assert notify.send("nobody's", book="other-book") is False                                # no owner, no ops account: dropped
        assert push.unregister(conn, a["token"]) and push.unregister(conn, b["token"]) and not push.unregister(conn, a["token"])
    finally:
        _clean(conn)
