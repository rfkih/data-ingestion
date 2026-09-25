"""Push notifications to the Blackridge Android app through Firebase Cloud Messaging (HTTP v1).

Configuration: ``IDX_FCM_SERVICE_ACCOUNT`` = path of the Firebase project's service-account JSON, placed on the server by the
operator (it is a credential: it lives next to ``idx-local.env``, never in the repo, never in a chat). Without it every call
is a no-op that reports ``sent=0``. Device tokens are what the app registers through ``POST /idx/push/register``
(``idx.push_device``); a token FCM reports as gone is disabled, so a re-install re-registers cleanly.

Best-effort like Telegram: nothing here raises into the job that produced the notification. The access token is a
service-account JWT (RS256, ``cryptography``) exchanged at Google's token endpoint and cached until it expires.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

import psycopg

logger = logging.getLogger(__name__)
SA_ENV = "IDX_FCM_SERVICE_ACCOUNT"
SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
TOKEN_URL = "https://oauth2.googleapis.com/token"
CHANNEL_ID = "desk"                      # the Android notification channel the app creates on registration
GONE_CODES = ("UNREGISTERED", "NOT_FOUND")   # FCM: the device token is no longer valid
Sender = Callable[[str, dict[str, Any], dict[str, str]], tuple[int, dict[str, Any]]]
_sa: dict[str, Any] | None = None
_tok: dict[str, Any] = {"value": None, "exp": 0.0}


def configured() -> bool:
    p = os.environ.get(SA_ENV)
    return bool(p and os.path.isfile(p))


def _service_account() -> dict[str, Any]:
    global _sa
    if _sa is None:
        with open(os.environ[SA_ENV], encoding="utf-8") as f:
            _sa = json.load(f)
        for k in ("project_id", "client_email", "private_key"):
            if not _sa.get(k):
                raise ValueError(f"{SA_ENV}: not a service-account file (missing {k})")
    return _sa


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _jwt(sa: dict[str, Any], now: float) -> str:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    head = _b64(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    claims = _b64(json.dumps({"iss": sa["client_email"], "scope": SCOPE, "aud": TOKEN_URL, "iat": int(now), "exp": int(now) + 3600}).encode())
    key = serialization.load_pem_private_key(sa["private_key"].encode(), password=None)
    sig = key.sign(f"{head}.{claims}".encode(), padding.PKCS1v15(), hashes.SHA256())
    return f"{head}.{claims}.{_b64(sig)}"


def _post(url: str, payload: dict[str, Any], headers: dict[str, str]) -> tuple[int, dict[str, Any]]:
    """POST JSON (or a form when the content type says so); the status and the decoded body, also for HTTP errors."""
    form = headers.get("Content-Type", "").startswith("application/x-www-form-urlencoded")
    data = urllib.parse.urlencode(payload).encode() if form else json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", **headers}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15.0) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode() or "{}")
        except ValueError:
            body = {}
        return e.code, body


def access_token(*, sender: Sender | None = None, now: float | None = None) -> str:
    """A bearer token for the FCM API, cached until a minute before it expires."""
    now = time.time() if now is None else now
    if _tok["value"] and now < _tok["exp"] - 60:
        return str(_tok["value"])
    sa = _service_account()
    status, body = (sender or _post)(TOKEN_URL, {"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": _jwt(sa, now)},
                                     {"Content-Type": "application/x-www-form-urlencoded"})
    if status != 200 or not body.get("access_token"):
        raise RuntimeError(f"fcm token exchange failed: {status} {body.get('error_description') or body.get('error') or body}")
    _tok.update(value=body["access_token"], exp=now + float(body.get("expires_in") or 3600))
    return str(_tok["value"])


# -- devices ---------------------------------------------------------------------------------------------------------------

def register(conn: psycopg.Connection, token: str, *, platform: str = "android", username: str | None = None, label: str | None = None,
             user_id: str | None = None) -> dict[str, Any]:
    """Upsert a device token (the app calls this on every start); a previously disabled token comes back enabled. A phone
    that signs in as someone else moves to that account (a token belongs to one account at a time)."""
    token = (token or "").strip()
    if len(token) < 20:
        raise ValueError("token is required")
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO idx.push_device (token, platform, username, label, user_id)
                       VALUES (%s, %s, %s, %s, %s)
                       ON CONFLICT (token) DO UPDATE SET platform = EXCLUDED.platform, username = COALESCE(EXCLUDED.username, idx.push_device.username),
                           label = COALESCE(EXCLUDED.label, idx.push_device.label), user_id = COALESCE(EXCLUDED.user_id, idx.push_device.user_id),
                           disabled = false, error = NULL, last_seen = now()
                       RETURNING token, platform, username, label, user_id, created_at, last_seen""",
                    (token, platform or "android", username, label, user_id))
        row = cur.fetchone()
    conn.commit()
    out = _row(row, ["token", "platform", "username", "label", "user_id", "created_at", "last_seen"])
    out["user_id"] = str(out["user_id"]) if out.get("user_id") else None
    return out


def unregister(conn: psycopg.Connection, token: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM idx.push_device WHERE token = %s", (token,))
        n = cur.rowcount
    conn.commit()
    return n > 0


def devices(conn: psycopg.Connection, *, include_disabled: bool = False, user_id: str | None = None) -> list[dict[str, Any]]:
    """Phones, one account's (``user_id``) or everyone's (None)."""
    cols = ["token", "platform", "username", "label", "disabled", "error", "created_at", "last_seen", "last_sent", "user_id"]
    with conn.cursor() as cur:
        cur.execute(f"""SELECT {', '.join(cols)} FROM idx.push_device WHERE (%s OR NOT disabled) AND (%s::uuid IS NULL OR user_id = %s::uuid)
                         ORDER BY last_seen DESC""", (include_disabled, user_id, user_id))
        rows = cur.fetchall()
    out = [_row(r, cols) for r in rows]
    for d in out:
        d["user_id"] = str(d["user_id"]) if d.get("user_id") else None
    return out


def _row(r: Any, cols: list[str]) -> dict[str, Any]:
    return r if isinstance(r, dict) else dict(zip(cols, r, strict=True))


# -- sending -----------------------------------------------------------------------------------------------------------------

def message(token: str, title: str, body: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Pure: the FCM v1 message for one device. Data values must be strings (FCM rejects anything else)."""
    return {"message": {
        "token": token,
        "notification": {"title": title[:200], "body": body[:1000]},
        "data": {str(k): str(v) for k, v in (data or {}).items() if v is not None},
        "android": {"priority": "high", "notification": {"channel_id": CHANNEL_ID, "sound": "default"}},
    }}


def send_one(token: str, title: str, body: str, data: dict[str, Any] | None = None, *, sender: Sender | None = None,
             bearer: str | None = None) -> dict[str, Any]:
    """Send to one device: {ok, gone, error}. ``gone`` means the token should be disabled."""
    sa = _service_account()
    url = f"https://fcm.googleapis.com/v1/projects/{sa['project_id']}/messages:send"
    bearer = bearer or access_token(sender=sender)
    status, res = (sender or _post)(url, message(token, title, body, data), {"Authorization": f"Bearer {bearer}"})
    if status == 200:
        return {"ok": True, "gone": False, "error": None}
    err = res.get("error") or {}
    codes = {d.get("errorCode") for d in err.get("details") or [] if isinstance(d, dict)} | {err.get("status")}
    gone = status == 404 or bool(codes & set(GONE_CODES))
    return {"ok": False, "gone": gone, "error": f"{status} {err.get('status') or ''} {err.get('message') or ''}".strip()}


def send_all(conn: psycopg.Connection, title: str, body: str, data: dict[str, Any] | None = None, *, sender: Sender | None = None,
             bearer: str | None = None, user_id: str | None = None) -> dict[str, Any]:
    """Send to one account's enabled devices (``user_id``; None = every device on the desk); disable the ones FCM reports gone.
    {sent, failed, gone, devices}. Never raises."""
    out = {"sent": 0, "failed": 0, "gone": 0, "devices": 0, "configured": configured()}
    if not configured():
        logger.info("idx push: not configured (%s unset); dropped: %s", SA_ENV, title)
        return out
    try:
        devs = devices(conn, user_id=user_id)
        out["devices"] = len(devs)
        if not devs:                                                    # FCM works, the message has nowhere to land: say so.
            logger.warning("idx push: no enabled device for %s; dropped: %s",                  # silent before 2026-09-24, so a
                           f"user {user_id}" if user_id else "the desk", title)                # feed-down alert vanished unseen
            return out
        bearer = bearer or access_token(sender=sender)
    except Exception as e:
        logger.warning("idx push: cannot send: %s: %s", type(e).__name__, e)
        out["error"] = f"{type(e).__name__}: {e}"
        return out
    for d in devs:
        try:
            r = send_one(d["token"], title, body, data, sender=sender, bearer=bearer)
        except Exception as e:                                          # a network hiccup on one device must not stop the rest
            r = {"ok": False, "gone": False, "error": f"{type(e).__name__}: {e}"}
        with conn.cursor() as cur:
            if r["ok"]:
                cur.execute("UPDATE idx.push_device SET last_sent = now(), error = NULL WHERE token = %s", (d["token"],))
            else:
                cur.execute("UPDATE idx.push_device SET disabled = disabled OR %s, error = %s WHERE token = %s", (r["gone"], r["error"], d["token"]))
        out["sent" if r["ok"] else "failed"] += 1
        out["gone"] += int(r["gone"])
        if not r["ok"]:
            logger.warning("idx push: %s%s: %s", d["token"][:12], " (gone)" if r["gone"] else "", r["error"])
    conn.commit()
    return out


def broadcast(title: str, body: str, data: dict[str, Any] | None = None, *, sender: Sender | None = None,
              user_id: str | None = None) -> dict[str, Any]:
    """``send_all`` on its own short connection - what ``notify`` calls from inside other jobs' transactions."""
    if not configured():
        return {"sent": 0, "failed": 0, "gone": 0, "devices": 0, "configured": False}
    from ..shared.db import get_connection
    try:
        with get_connection() as conn:
            return send_all(conn, title, body, data, sender=sender, user_id=user_id)
    except Exception as e:                                              # no database, no notification - never a failed job
        logger.warning("idx push: broadcast failed: %s: %s", type(e).__name__, e)
        return {"sent": 0, "failed": 0, "gone": 0, "devices": 0, "configured": True, "error": f"{type(e).__name__}: {e}"}
