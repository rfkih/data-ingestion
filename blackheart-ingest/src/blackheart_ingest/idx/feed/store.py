"""Database side of the collector: the relayed session token, the subscription list, batched inserts, heartbeat, events
and the daily coverage audit. Every function takes an open psycopg connection and commits what it writes."""
from __future__ import annotations

import base64
import json
import logging
import os
import urllib.parse
from datetime import UTC, date, datetime, timedelta
from typing import Any

import psycopg
from psycopg.rows import dict_row, tuple_row

logger = logging.getLogger(__name__)

TOKEN_ENV = "STOCKBIT_TOKEN"


# ---- token ----------------------------------------------------------------------------------------------------------


def _jwt_claims(tok: str) -> dict[str, Any]:
    try:
        p = tok.split(".")[1]
        p += "=" * (-len(p) % 4)
        return json.loads(base64.urlsafe_b64decode(p))
    except Exception:
        return {}


def _looks_jwt(s: Any) -> bool:
    return isinstance(s, str) and s.count(".") == 2 and s.startswith("eyJ") and len(s) > 60


def looks_like_refresh_jwt(s: Any) -> bool:
    """A bare JWT whose lifetime is over two days is Stockbit's refresh token (7 d), not the 24 h access token."""
    if not _looks_jwt(s):
        return False
    c = _jwt_claims(s)
    try:
        issued = int(c.get("iat") or datetime.now(UTC).timestamp())               # no iat: measure from now
        return int(c.get("exp", 0)) - issued > 2 * 86400
    except (TypeError, ValueError):
        return False


def _shape(v: Any, depth: int = 0) -> Any:
    """Keys only - never values - so a stored relay payload can be debugged without keeping secrets twice."""
    if depth > 6:
        return "..."
    if isinstance(v, dict):
        return {k: _shape(x, depth + 1) for k, x in list(v.items())[:40]}
    if isinstance(v, list):
        return [_shape(v[0], depth + 1)] if v else []
    return type(v).__name__


def _walk(v: Any, path: tuple = ()):
    if isinstance(v, dict):
        for k, x in v.items():
            yield from _walk(x, (*path, str(k).lower()))
    elif isinstance(v, list):
        for x in v:
            yield from _walk(x, path)
    else:
        yield path, v


def _user_id_from(claims: dict[str, Any], doc: Any) -> str | None:
    for path, v in _walk(doc):
        if path and path[-1] in ("id", "user_id", "userid", "uid") and "user" in "".join(path[:-1]) and isinstance(v, (int, str)) and str(v).isdigit():
            return str(v)
    data = claims.get("data") if isinstance(claims.get("data"), dict) else claims
    for k in ("user_id", "userid", "id", "uid", "userId"):
        v = data.get(k)
        if isinstance(v, (int, str)) and str(v).isdigit():
            return str(v)
    return None


def parse_relay(payload: str | bytes | dict[str, Any]) -> dict[str, Any]:
    """Accept what a browser can send: a JSON object ({access_token, refresh_token?, expires_at?, user_id?}), the raw
    ``credentialStorage`` cookie value (URL-encoded JSON of the app's auth state), or a bare JWT. Returns the fields for
    ``idx.feed_token``; raises ValueError when no access token is found."""
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8", "replace")
    doc: Any = payload
    if isinstance(payload, str):
        s = payload.strip()
        if s.startswith("{") or s.startswith("%7B"):
            s = urllib.parse.unquote(s) if s.startswith("%7B") else s
            try:
                doc = json.loads(s)
            except json.JSONDecodeError:
                doc = urllib.parse.unquote(s)
                doc = json.loads(doc)
        elif _looks_jwt(s):
            doc = {"access_token": s}
        else:
            raise ValueError("relay payload is neither JSON nor a JWT")
    access = refresh = None
    expires: datetime | None = None
    if isinstance(doc, dict) and doc.get("access_token"):
        access = doc["access_token"]
        refresh = doc.get("refresh_token")
        if doc.get("expires_at"):
            expires = datetime.fromisoformat(str(doc["expires_at"]).replace("Z", "+00:00"))
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=UTC)
    else:
        for path, v in _walk(doc):
            if not path:
                continue
            if path[-1] == "token" and "access" in path[:-1] and _looks_jwt(v):
                access = v
            elif path[-1] == "token" and "refresh" in path[:-1] and isinstance(v, str) and len(v) > 20:
                refresh = v
            elif path[-1] in ("expired_at", "expires_at", "expiredat") and "access" in path[:-1]:
                try:
                    expires = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
                    if expires.tzinfo is None:
                        expires = expires.replace(tzinfo=UTC)
                except ValueError:
                    pass
        if not access:
            jwts = [v for _, v in _walk(doc) if _looks_jwt(v)]
            access = jwts[0] if jwts else None
    if not access:
        raise ValueError("no access token in relay payload")
    claims = _jwt_claims(access)
    if expires is None and claims.get("exp"):
        expires = datetime.fromtimestamp(int(claims["exp"]), tz=UTC)
    return {"access_token": access, "refresh_token": refresh, "expires_at": expires,
            "user_id": _user_id_from(claims, doc if isinstance(doc, (dict, list)) else {}), "raw_keys": _shape(doc)}


def save_token(conn: psycopg.Connection, fields: dict[str, Any], source: str = "relay") -> dict[str, Any]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""INSERT INTO idx.feed_token (id, access_token, refresh_token, user_id, expires_at, received_at, source, raw_keys)
                       VALUES (1, %s, %s, %s, %s, now(), %s, %s)
                       ON CONFLICT (id) DO UPDATE SET access_token = EXCLUDED.access_token, refresh_token = EXCLUDED.refresh_token,
                           user_id = COALESCE(EXCLUDED.user_id, idx.feed_token.user_id), expires_at = EXCLUDED.expires_at,
                           received_at = now(), source = EXCLUDED.source, raw_keys = EXCLUDED.raw_keys
                       RETURNING user_id, expires_at, received_at, source""",
                    (fields["access_token"], fields.get("refresh_token"), fields.get("user_id"), fields.get("expires_at"), source,
                     json.dumps(fields.get("raw_keys") or {})))
        row = cur.fetchone()
    conn.commit()
    event(conn, "token", f"token received via {source}", {"user_id": row["user_id"], "expires_at": row["expires_at"].isoformat() if row["expires_at"] else None})
    return dict(row)


def env_file_token() -> str | None:
    """``STOCKBIT_TOKEN`` as it stands in the env file right now (re-read on every call, so a token pasted into
    idx-local.env is picked up without restarting anything), else from the process environment."""
    from ..broker import _default_env_file
    path = _default_env_file()
    if path:
        try:
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    if line.startswith(TOKEN_ENV + "="):
                        v = line[len(TOKEN_ENV) + 1:].strip().strip('"').strip("'")
                        if v:
                            return v
        except OSError:
            pass
    return os.environ.get(TOKEN_ENV)


def load_token(conn: psycopg.Connection) -> dict[str, Any] | None:
    """The newest of: the token pasted/relayed into ``idx.feed_token`` and ``STOCKBIT_TOKEN`` in idx-local.env (the broker
    feed's pasted token) - whichever expires later."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT access_token, refresh_token, user_id, expires_at, received_at, source FROM idx.feed_token WHERE id = 1")
        row = cur.fetchone()
    env = env_file_token()
    if env and _looks_jwt(env):
        claims = _jwt_claims(env)
        exp = datetime.fromtimestamp(int(claims.get("exp", 0)), tz=UTC) if claims.get("exp") else None
        if row is None or (exp and row.get("expires_at") and exp > row["expires_at"]):
            return {"access_token": env, "refresh_token": None, "user_id": (row or {}).get("user_id") or _user_id_from(claims, {}),
                    "expires_at": exp, "received_at": None, "source": "env"}
    return dict(row) if row else None


def token_status(tok: dict[str, Any] | None, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    if not tok:
        return {"present": False, "valid": False, "expires_at": None, "minutes_left": None, "source": None}
    exp = tok.get("expires_at")
    left = (exp - now).total_seconds() / 60 if exp else None
    return {"present": True, "valid": bool(exp and exp > now), "expires_at": exp.isoformat() if exp else None,
            "minutes_left": round(left) if left is not None else None, "source": tok.get("source"), "user_id": tok.get("user_id"),
            "received_at": tok["received_at"].isoformat() if tok.get("received_at") else None}


# ---- symbols --------------------------------------------------------------------------------------------------------


def symbols(conn: psycopg.Connection) -> dict[str, list[str]]:
    """channel -> codes, from the enabled rows."""
    out: dict[str, list[str]] = {}
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute("SELECT code, channels FROM idx.feed_symbol WHERE enabled ORDER BY code")
        for code, chans in cur.fetchall():
            for ch in chans or []:
                out.setdefault(ch, []).append(code)
    return out


def list_symbols(conn: psycopg.Connection) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT code, channels, reason, enabled, added_at FROM idx.feed_symbol ORDER BY enabled DESC, code")
        return [dict(r) for r in cur.fetchall()]


def set_symbols(conn: psycopg.Connection, codes: list[str], *, reason: str = "manual", channels: list[str] | None = None,
                replace: bool = False) -> int:
    chans = channels or ["order_book", "liveprice"]
    codes = sorted({c.strip().upper() for c in codes if c and c.strip()})
    with conn.cursor() as cur:
        if replace:
            cur.execute("UPDATE idx.feed_symbol SET enabled = false WHERE reason = %s AND NOT (code = ANY(%s))", (reason, codes))
        for c in codes:
            cur.execute("""INSERT INTO idx.feed_symbol (code, channels, reason, enabled) VALUES (%s, %s, %s, true)
                           ON CONFLICT (code) DO UPDATE SET channels = EXCLUDED.channels, enabled = true,
                               reason = CASE WHEN idx.feed_symbol.reason = 'manual' THEN 'manual' ELSE EXCLUDED.reason END""", (c, chans, reason))
    conn.commit()
    return len(codes)


def disable_symbols(conn: psycopg.Connection, codes: list[str]) -> int:
    with conn.cursor() as cur:
        cur.execute("UPDATE idx.feed_symbol SET enabled = false WHERE code = ANY(%s)", ([c.upper() for c in codes],))
        n = cur.rowcount
    conn.commit()
    return n


def liquid_codes(conn: psycopg.Connection, n: int = 100) -> list[str]:
    """The n most traded main-board names by 60-day median value on the latest feature day, plus every name any active
    book holds and every watchlist name - the default subscription."""
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute("""WITH d AS (SELECT max(trade_date) AS d FROM idx.feature_daily)
                       SELECT f.code FROM idx.feature_daily f, d
                        WHERE f.trade_date = d.d AND f.value_60d_median IS NOT NULL
                        ORDER BY f.value_60d_median DESC NULLS LAST LIMIT %s""", (n,))
        codes = [r[0] for r in cur.fetchall()]
        cur.execute("SELECT DISTINCT p.code FROM idx.position p JOIN idx.book b ON b.book = p.book WHERE p.lots > 0 AND b.archived_at IS NULL")
        codes += [r[0] for r in cur.fetchall()]
        cur.execute("SELECT DISTINCT code FROM idx.watchlist")
        codes += [r[0] for r in cur.fetchall()]
    return sorted(set(codes))


# ---- writes ---------------------------------------------------------------------------------------------------------

TRADE_COLS = ("ts", "code", "seq", "price", "qty", "verb", "board", "cum_volume", "cum_value", "cum_freq", "recv_at")
BOOK_COLS = ("ts", "code", "seq", "bid_px", "bid_vol", "bid_n", "off_px", "off_vol", "off_n", "bid_total", "off_total", "bid_levels", "off_levels", "n_updates")


def insert_trades(conn: psycopg.Connection, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    sql = f"INSERT INTO idx.feed_trade ({', '.join(TRADE_COLS)}) VALUES ({', '.join('%s' for _ in TRADE_COLS)}) ON CONFLICT DO NOTHING"
    with conn.cursor() as cur:
        cur.executemany(sql, [tuple(r[c] for c in TRADE_COLS) for r in rows])
    conn.commit()
    return len(rows)


def insert_books(conn: psycopg.Connection, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    sql = (f"INSERT INTO idx.feed_book ({', '.join(BOOK_COLS)}) VALUES ({', '.join('%s' for _ in BOOK_COLS)}) "
           "ON CONFLICT (code, ts) DO UPDATE SET n_updates = idx.feed_book.n_updates + EXCLUDED.n_updates")
    with conn.cursor() as cur:
        cur.executemany(sql, [tuple(r[c] for c in BOOK_COLS) for r in rows])
    conn.commit()
    return len(rows)


# ---- heartbeat + events -------------------------------------------------------------------------------------------


def set_status(conn: psycopg.Connection, state: str, detail: str | None = None, **counts: Any) -> None:
    cols = {"state": state, "detail": detail, **counts}
    sets = ", ".join(f"{k} = EXCLUDED.{k}" for k in cols)
    with conn.cursor() as cur:
        cur.execute(f"INSERT INTO idx.feed_status (id, {', '.join(cols)}, updated_at) VALUES (1, {', '.join('%s' for _ in cols)}, now()) "
                    f"ON CONFLICT (id) DO UPDATE SET {sets}, updated_at = now()", tuple(cols.values()))
    conn.commit()


def status(conn: psycopg.Connection) -> dict[str, Any]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT * FROM idx.feed_status WHERE id = 1")
        st = cur.fetchone()
        cur.execute("SELECT count(*) AS n FROM idx.feed_symbol WHERE enabled")
        n_sym = cur.fetchone()["n"]
        cur.execute("""SELECT count(*) AS trades, count(DISTINCT code) AS codes, min(ts) AS first_at, max(ts) AS last_at
                         FROM idx.feed_trade WHERE ts >= (now() AT TIME ZONE 'Asia/Jakarta')::date::timestamp AT TIME ZONE 'Asia/Jakarta'""")
        today = cur.fetchone()
        cur.execute("SELECT at, kind, detail FROM idx.feed_event ORDER BY at DESC LIMIT 8")
        events = [dict(r) for r in cur.fetchall()]
    tok = token_status(load_token(conn))
    out = {"collector": dict(st) if st else {"state": "off", "detail": "never started"}, "token": tok, "symbols_enabled": n_sym,
           "today": dict(today), "events": events}
    if st and st.get("updated_at"):
        out["collector"]["stale_s"] = round((datetime.now(UTC) - st["updated_at"]).total_seconds())
    return out


def event(conn: psycopg.Connection, kind: str, detail: str | None = None, data: dict[str, Any] | None = None) -> None:
    with conn.cursor() as cur:
        cur.execute("INSERT INTO idx.feed_event (kind, detail, data) VALUES (%s, %s, %s)", (kind, detail, json.dumps(data or {}, default=str)))
    conn.commit()


# ---- daily audit ----------------------------------------------------------------------------------------------------


def audit_day(conn: psycopg.Connection, d: date) -> list[dict[str, Any]]:
    """Coverage per subscribed name for one trading day, against the official day summary (which the daily chain fetches
    the same evening). Idempotent; returns the rows written."""
    lo = datetime(d.year, d.month, d.day, tzinfo=UTC) - timedelta(hours=7)
    hi = lo + timedelta(days=1)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""WITH t AS (
                           SELECT code, count(*) AS n_trades, sum(qty) AS volume, min(ts) AS first_at, max(ts) AS last_at,
                                  max(gap) AS max_gap
                             FROM (SELECT code, ts, qty, extract(epoch FROM ts - lag(ts) OVER (PARTITION BY code ORDER BY ts)) AS gap
                                     FROM idx.feed_trade WHERE ts >= %s AND ts < %s) x
                            GROUP BY code),
                       b AS (SELECT code, count(*) AS n_books FROM idx.feed_book WHERE ts >= %s AND ts < %s GROUP BY code)
                       INSERT INTO idx.feed_day (trade_date, code, n_trades, volume, official_vol, official_frq, coverage, first_at, last_at, n_books, max_gap_s)
                       SELECT %s, t.code, t.n_trades, t.volume, s.volume, s.frequency,
                              CASE WHEN s.volume > 0 THEN least(t.volume::numeric / s.volume, 9.9999) END,
                              t.first_at, t.last_at, COALESCE(b.n_books, 0), t.max_gap::int
                         FROM t LEFT JOIN b USING (code) LEFT JOIN idx.daily_summary s ON s.code = t.code AND s.trade_date = %s
                       ON CONFLICT (trade_date, code) DO UPDATE SET n_trades = EXCLUDED.n_trades, volume = EXCLUDED.volume,
                           official_vol = EXCLUDED.official_vol, official_frq = EXCLUDED.official_frq, coverage = EXCLUDED.coverage,
                           first_at = EXCLUDED.first_at, last_at = EXCLUDED.last_at, n_books = EXCLUDED.n_books, max_gap_s = EXCLUDED.max_gap_s
                       RETURNING *""", (lo, hi, lo, hi, d, d))
        rows = [dict(r) for r in cur.fetchall()]
    conn.commit()
    return rows
