"""Desk accounts: the pure parts (hashing, tokens, policy, throttle) and, with the local DB, the routes."""
from __future__ import annotations

import base64
import os
import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient

from blackheart_ingest.idx import accounts as AC

KEY = b"k" * 32


def test_password_hashes_verify_and_differ_per_salt() -> None:
    h1, h2 = AC.hash_password("Correct-Horse-9!"), AC.hash_password("Correct-Horse-9!")
    assert h1 != h2 and h1.startswith("scrypt$")
    assert AC.verify_password("Correct-Horse-9!", h1) and AC.verify_password("Correct-Horse-9!", h2)
    assert not AC.verify_password("wrong", h1) and not AC.verify_password("x", "garbage")


def test_password_policy_is_the_platforms() -> None:
    assert AC.password_problem("short1!A") is not None
    assert AC.password_problem("alllowercase123!") is not None
    assert AC.password_problem("Correct-Horse-9!") is None
    assert AC.email_ok("a@b.co") and not AC.email_ok("nope") and not AC.email_ok("a @b.co")


def test_tokens_round_trip_and_reject_tampering_and_expiry() -> None:
    user = {"id": uuid.uuid4(), "email": "a@b.co"}
    tok, ms = AC.sign_token(user, KEY, now=1_000_000, days=1)
    assert ms == 86_400_000
    claims = AC.read_token(tok, KEY, now=1_000_000 + 10)
    assert claims and claims["sub"] == "a@b.co" and claims["userId"] == str(user["id"])
    assert AC.read_token(tok, KEY, now=1_000_000 + 86_400 + 1) is None          # expired
    assert AC.read_token(tok, b"other-key" * 4, now=1_000_000) is None           # wrong key
    head, body, sig = tok.split(".")
    assert AC.read_token(f"{head}.{body}x.{sig}", KEY, now=1_000_000) is None    # tampered
    assert AC.read_token(None, KEY) is None and AC.read_token("a.b", KEY) is None


def test_throttle_counts_failures_in_a_window() -> None:
    t = AC.Throttle(limit=3, window_s=100)
    for i in range(3):
        assert not t.blocked("x", now=1000 + i)
        t.fail("x", now=1000 + i)
    assert t.blocked("x", now=1005)
    assert not t.blocked("x", now=1200)                                          # window passed
    t.fail("x", now=1200)
    t.clear("x")
    assert not t.blocked("x", now=1201)


@pytest.fixture(scope="module")
def client():
    dsn = os.environ.get("INGEST_DB_DSN")
    if not dsn:
        pytest.skip("INGEST_DB_DSN not set")
    try:
        psycopg.connect(dsn, connect_timeout=5).close()
    except Exception as e:
        pytest.skip(f"db unreachable: {e}")
    os.environ.setdefault("IDX_JWT_SECRET", base64.b64encode(b"t" * 48).decode())
    from blackheart_ingest.workers.server import app
    with TestClient(app) as c:
        yield c
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM idx.app_user WHERE email LIKE 'test-%@papan.test'")
        conn.commit()


def test_register_login_me_logout(client) -> None:
    email = f"test-{uuid.uuid4().hex[:8]}@papan.test"
    r = client.post("/api/v1/users/register", json={"email": email, "fullName": "Test Person", "password": "Correct-Horse-9!"})
    assert r.status_code == 201, r.text
    d = r.json()["data"]
    assert d["accessToken"] and d["user"]["email"] == email and d["user"]["fullName"] == "Test Person"
    assert client.post("/api/v1/users/register", json={"email": email, "fullName": "Again", "password": "Correct-Horse-9!"}).status_code == 409
    assert client.post("/api/v1/users/register", json={"email": "x@y.z", "fullName": "Weak", "password": "weak"}).status_code == 400
    r = client.post("/api/v1/users/login", json={"email": email.upper(), "password": "Correct-Horse-9!"})
    assert r.status_code == 200 and r.json()["data"]["accessToken"]
    token = r.json()["data"]["accessToken"]
    assert client.post("/api/v1/users/login", json={"email": email, "password": "nope"}).status_code == 401
    r = client.get("/api/v1/users/me", headers={"authorization": f"Bearer {token}"})
    assert r.status_code == 200 and r.json()["data"]["email"] == email and "password_hash" not in r.text
    assert client.get("/api/v1/users/me", headers={"authorization": "Bearer nonsense"}).status_code == 401
    assert client.post("/api/v1/users/logout").status_code == 200
