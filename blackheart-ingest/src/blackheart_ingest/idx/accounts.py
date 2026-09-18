"""Desk accounts: anyone can register, sign in, and carry a session.

The routes, envelope, token and cookie are the trading JVM's user API shape (``/api/v1/users/register|login|me|logout``,
``ResponseDto``, HS256 JWT in ``blackheart-token``), so the Blackridge app talks to this exactly as it would to the platform:
``INTERNAL_TRADING_URL`` pointed here. Accounts live in ``idx.app_user``; passwords are scrypt hashes; the token is signed
with ``IDX_JWT_SECRET`` (base64), which the app also holds as ``JWT_SECRET`` to verify sessions on its own.

Pure parts (hashing, tokens, the password policy, the throttle) take no connection and are unit-tested; the routes are
thin shells over them.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import psycopg
from fastapi import APIRouter, Body, Request, Response
from fastapi.responses import JSONResponse

from ..shared.db import get_connection

COOKIE = "blackheart-token"
SESSION_DAYS = int(os.environ.get("IDX_SESSION_DAYS", "30") or 30)
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1
_BODY = Body(...)

# ---- password policy (8+ chars with lower, upper, digit, symbol — relaxed from the JVM's 12 on 2026-09-17; the app mirrors it)


def password_problem(pw: str) -> str | None:
    if not 8 <= len(pw) <= 100:
        return "Password must be between 8 and 100 characters"
    if not (re.search(r"[a-z]", pw) and re.search(r"[A-Z]", pw) and re.search(r"\d", pw) and re.search(r"[^\w\s]", pw)):
        return "Password needs a lower-case letter, an upper-case letter, a digit and a symbol"
    return None


def email_ok(email: str) -> bool:
    return bool(re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email)) and len(email) <= 254


# ---- password hashing (scrypt from the standard library; self-describing so parameters can change later)


def hash_password(pw: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${base64.b64encode(salt).decode()}${base64.b64encode(h).decode()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, h = stored.split("$")
        if algo != "scrypt":
            return False
        calc = hashlib.scrypt(pw.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(calc, base64.b64decode(h))
    except Exception:
        return False


# ---- tokens (HS256, the JVM's shape: sub = email, userId, iat, exp)


def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64u(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def secret() -> bytes:
    raw = os.environ.get("IDX_JWT_SECRET", "").strip()
    if not raw:
        raise RuntimeError("IDX_JWT_SECRET is not set (base64); accounts cannot sign sessions")
    return base64.b64decode(raw)


def sign_token(user: dict[str, Any], key: bytes, now: float | None = None, days: int = SESSION_DAYS) -> tuple[str, int]:
    """The token and its lifetime in milliseconds."""
    t = int(now if now is not None else time.time())
    head = _b64u(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    body = _b64u(json.dumps({"sub": user["email"], "userId": str(user["id"]), "iat": t, "exp": t + days * 86400},
                            separators=(",", ":")).encode())
    sig = _b64u(hmac.new(key, f"{head}.{body}".encode(), hashlib.sha256).digest())
    return f"{head}.{body}.{sig}", days * 86400 * 1000


def read_token(token: str | None, key: bytes, now: float | None = None) -> dict[str, Any] | None:
    """The claims of a valid, unexpired token; None otherwise."""
    if not token or token.count(".") != 2:
        return None
    try:
        head, body, sig = token.split(".")
        want = hmac.new(key, f"{head}.{body}".encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(want, _unb64u(sig)):
            return None
        claims = json.loads(_unb64u(body))
        if float(claims.get("exp", 0)) <= (now if now is not None else time.time()):
            return None
        return claims
    except Exception:
        return None


# ---- a small throttle on failed sign-ins per email (in memory; enough for one desk)


class Throttle:
    def __init__(self, limit: int = 10, window_s: int = 600):
        self.limit, self.window, self.hits = limit, window_s, {}

    def blocked(self, key: str, now: float | None = None) -> bool:
        now = now if now is not None else time.time()
        hits = [t for t in self.hits.get(key, []) if now - t < self.window]
        self.hits[key] = hits
        return len(hits) >= self.limit

    def fail(self, key: str, now: float | None = None) -> None:
        self.hits.setdefault(key, []).append(now if now is not None else time.time())

    def clear(self, key: str) -> None:
        self.hits.pop(key, None)


THROTTLE = Throttle()

# ---- storage


def public(u: dict[str, Any]) -> dict[str, Any]:
    iso = lambda v: v.isoformat() if isinstance(v, datetime) else v  # noqa: E731
    return {"userId": str(u["id"]), "email": u["email"], "fullName": u["full_name"], "phoneNumber": u.get("phone"),
            "role": u.get("role", "USER"), "status": u.get("status", "ACTIVE"), "emailVerified": False,
            "lastLoginAt": iso(u.get("last_login_at")), "createdTime": iso(u.get("created_at")), "updatedTime": iso(u.get("updated_at"))}


def get_user(conn: psycopg.Connection, email: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute("SELECT id, email, full_name, phone, password_hash, role, status, created_at, updated_at, last_login_at "
                    "FROM idx.app_user WHERE email = %s", (email,))
        row = cur.fetchone()
    return dict(row) if row else None


def create_user(conn: psycopg.Connection, email: str, full_name: str, phone: str | None, pw: str) -> dict[str, Any]:
    uid = uuid.uuid4()
    with conn.cursor() as cur:
        cur.execute("INSERT INTO idx.app_user (id, email, full_name, phone, password_hash) VALUES (%s, %s, %s, %s, %s)",
                    (uid, email, full_name, phone or None, hash_password(pw)))
    conn.commit()
    return get_user(conn, email)


# ---- password reset: a one-time link made on the desk, used once in the app

RESET_MINUTES = 30


def make_reset(conn: psycopg.Connection, email: str, minutes: int = RESET_MINUTES) -> str | None:
    """A fresh reset token for an account (None when there is no such account). Older unused tokens are voided."""
    user = get_user(conn, email.strip().lower())
    if not user:
        return None
    token = secrets.token_urlsafe(32)
    with conn.cursor() as cur:
        cur.execute("UPDATE idx.password_reset SET used_at = now() WHERE user_id = %s AND used_at IS NULL", (user["id"],))
        cur.execute("INSERT INTO idx.password_reset (user_id, token_hash, expires_at) VALUES (%s, %s, now() + (%s || ' minutes')::interval)",
                    (user["id"], hashlib.sha256(token.encode()).hexdigest(), str(int(minutes))))
    conn.commit()
    return token


def use_reset(conn: psycopg.Connection, token: str, new_password: str) -> dict[str, Any]:
    """Set a new password with a valid, unused, unexpired token; the token is spent. Raises ValueError with the reason."""
    if (why := password_problem(new_password)) is not None:
        raise ValueError(why)
    h = hashlib.sha256((token or "").strip().encode()).hexdigest()
    with conn.cursor() as cur:
        cur.execute("SELECT id, user_id, expires_at, used_at FROM idx.password_reset WHERE token_hash = %s", (h,))
        row = cur.fetchone()
        row = dict(row) if row else None
        if not row:
            raise ValueError("This reset link is not valid")
        if row["used_at"] is not None:
            raise ValueError("This reset link has already been used")
        if row["expires_at"] < now_utc():
            raise ValueError("This reset link has expired; ask for a new one")
        cur.execute("UPDATE idx.app_user SET password_hash = %s, updated_at = now() WHERE id = %s", (hash_password(new_password), row["user_id"]))
        cur.execute("UPDATE idx.password_reset SET used_at = now() WHERE id = %s", (row["id"],))
        cur.execute("SELECT email FROM idx.app_user WHERE id = %s", (row["user_id"],))
        email = dict(cur.fetchone())["email"]
    conn.commit()
    THROTTLE.clear(email)
    return {"email": email}


def change_password(conn: psycopg.Connection, email: str, current: str, new_password: str) -> None:
    """A signed-in person changes their own password."""
    user = get_user(conn, email)
    if not user or not verify_password(current, user["password_hash"]):
        raise PermissionError("The current password is wrong")
    if (why := password_problem(new_password)) is not None:
        raise ValueError(why)
    with conn.cursor() as cur:
        cur.execute("UPDATE idx.app_user SET password_hash = %s, updated_at = now() WHERE id = %s", (hash_password(new_password), user["id"]))
    conn.commit()


def touch_login(conn: psycopg.Connection, uid: Any) -> None:
    with conn.cursor() as cur:
        cur.execute("UPDATE idx.app_user SET last_login_at = now() WHERE id = %s", (uid,))
    conn.commit()


# ---- routes


def envelope(status: int, data: Any = None, error: str | None = None, token: str | None = None) -> Response:
    res = JSONResponse(status_code=status, content={"responseCode": f"{status}00", "responseDesc": "ok" if error is None else "error",
                                                    "data": data, "errorMessage": error})
    if token:
        res.set_cookie(COOKIE, token, httponly=True, samesite="lax", path="/", max_age=SESSION_DAYS * 86400)
    return res


def _auth_payload(user: dict[str, Any]) -> tuple[dict[str, Any], str]:
    token, ms = sign_token(user, secret())
    return {"accessToken": token, "tokenType": "Bearer", "expiresIn": ms, "user": public(user)}, token


def make_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1/users", tags=["accounts"])

    @router.post("/register")
    def register(body: dict[str, Any] = _BODY) -> Response:
        email = str(body.get("email") or "").strip().lower()
        name = str(body.get("fullName") or "").strip()
        phone = str(body.get("phoneNumber") or "").strip() or None
        pw = str(body.get("password") or "")
        if not email or not name:
            return envelope(400, error="Email and name are required")
        if not email_ok(email):
            return envelope(400, error="That email does not look right")
        if (why := password_problem(pw)) is not None:
            return envelope(400, error=why)
        with get_connection() as conn:
            if get_user(conn, email):
                return envelope(409, error=f"An account with email '{email}' already exists")
            user = create_user(conn, email, name, phone, pw)
        data, token = _auth_payload(user)
        return envelope(201, data, token=token)

    @router.post("/login")
    def login(body: dict[str, Any] = _BODY) -> Response:
        email = str(body.get("email") or "").strip().lower()
        pw = str(body.get("password") or "")
        if THROTTLE.blocked(email):
            return envelope(429, error="Too many attempts; try again in a few minutes")
        with get_connection() as conn:
            user = get_user(conn, email)
            if not user or user.get("status") != "ACTIVE" or not verify_password(pw, user["password_hash"]):
                THROTTLE.fail(email)
                return envelope(401, error="Invalid email or password")
            touch_login(conn, user["id"])
        THROTTLE.clear(email)
        data, token = _auth_payload(user)
        return envelope(200, data, token=token)

    @router.get("/me")
    def me(request: Request) -> Response:
        auth = request.headers.get("authorization") or ""
        token = auth[7:] if auth.startswith("Bearer ") else request.cookies.get(COOKIE)
        claims = read_token(token, secret())
        if not claims:
            return envelope(401, error="Unauthorized")
        with get_connection() as conn:
            user = get_user(conn, str(claims.get("sub") or ""))
        if not user or user.get("status") != "ACTIVE":
            return envelope(401, error="Unauthorized")
        return envelope(200, public(user))

    @router.post("/password-reset")
    def password_reset(body: dict[str, Any] = _BODY) -> Response:
        """{token, password}: set a new password with a reset link's token (made by `idx account reset-link EMAIL`)."""
        with get_connection() as conn:
            try:
                r = use_reset(conn, str(body.get("token") or ""), str(body.get("password") or ""))
            except ValueError as e:
                return envelope(400, error=str(e))
        return envelope(200, {"email": r["email"]})

    @router.post("/password")
    def password_change(request: Request, body: dict[str, Any] = _BODY) -> Response:
        """{currentPassword, newPassword} for the signed-in person (Bearer / cookie)."""
        auth = request.headers.get("authorization") or ""
        token = auth[7:] if auth.startswith("Bearer ") else request.cookies.get(COOKIE)
        claims = read_token(token, secret())
        if not claims:
            return envelope(401, error="Unauthorized")
        with get_connection() as conn:
            try:
                change_password(conn, str(claims.get("sub") or ""), str(body.get("currentPassword") or ""), str(body.get("newPassword") or ""))
            except PermissionError as e:
                return envelope(401, error=str(e))
            except ValueError as e:
                return envelope(400, error=str(e))
        return envelope(200, {"changed": True})

    @router.post("/logout")
    def logout() -> Response:
        res = envelope(200, {"logout": True})
        res.delete_cookie(COOKIE, path="/")
        return res

    return router


def count_users(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM idx.app_user")
        return int(dict(cur.fetchone())["n"])


def now_utc() -> datetime:
    return datetime.now(UTC)
