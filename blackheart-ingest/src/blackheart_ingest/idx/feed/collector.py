"""The collector: one long-running asyncio process that keeps ONE datafeed websocket open through the trading session,
turns frames into rows and keeps a heartbeat the API and the scheduler can read.

Lifecycle
  waiting        outside the session window (Mon-Fri 08:40-16:20 WIB): heartbeat only, wakes at the next window
  token_expired  no usable session token: alerts once, re-checks every minute (the operator logs in -> pastes the cookie at
                 /idx/feed/relay or STOCKBIT_TOKEN in idx-local.env -> resume). With a refresh token in that paste the
                 collector renews the session itself 45 min before the access token runs out (broker.refresh_and_persist,
                 in a worker thread) and only asks for a paste when that fails.
  connecting     websocket open -> HTTP key -> auth frame -> subscribe frame
  live           frames flowing
  reconnecting   backoff 1, 2, 4 ... 30 s, forever within the window; an alert after 5 straight failures

How a dead connection is noticed (three independent watchdogs, all inside the receive loop):
  1. transport: the websocket library raises ConnectionClosed / OSError the moment TCP or the WS close handshake fails.
  2. liveness: after 15 s without any frame we send an application ping; a pong later than 13 s -> we close and reconnect.
     A half-open TCP connection (laptop sleep, NAT timeout, upstream crash) is caught here within ~30 s.
  3. data: during the continuous phases (Mon-Thu 09:00-12:00 / 13:30-15:50, Fri 09:00-11:30 / 14:00-15:50) a connection that
     pongs but delivers no liveprice/orderbook frame for 90 s is a zombie subscription: we resubscribe; 180 s -> reconnect.
Reconnect flow: close -> backoff -> new socket -> fresh HTTP key -> auth -> re-read idx.feed_symbol -> subscribe. Frames
missed while down are gone (the feed has no replay) - the outage is logged in idx.feed_event and shows up as low coverage
in idx.feed_day; a reconnect re-delivers the current book state and duplicates are dropped by the primary keys.

Writes never block the receive loop: rows go to a writer thread with its own database connection, a bounded queue and
its own retry (a database hiccup keeps up to 500k rows in memory, then drops the oldest and counts them). Every frame is
also appended to a per-day gzip archive (flushed every second, kept 7 days) so a parser change or a database outage can be
replayed with ``idx feed run --replay FILE``.
"""
from __future__ import annotations

import asyncio
import gzip
import logging
import os
import queue
import signal
import struct
import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import psycopg
import websockets

from .. import notify
from . import proto, store
from .parse import WIB, Side, book_key, book_row, parse_book_body, parse_ts, trade_row

logger = logging.getLogger(__name__)

WS_URL = "wss://wss-jkt.trading.stockbit.com/ws"
KEY_URL = "https://exodus.stockbit.com/auth/websocket/key"
ORIGIN = "https://stockbit.com"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
HEARTBEAT_S = 15.0          # silence before we ping
PONG_GRACE_S = 13.0         # pong late by this much -> close and reconnect
STALL_RESUB_S = 90.0        # no data frame in a continuous phase -> resubscribe
STALL_RECONNECT_S = 180.0   # still nothing -> reconnect
FLUSH_S = 1.0
STATUS_S = 10.0
BOOK_SAMPLE_S = 1.0
SYMBOL_RELOAD_S = 300.0
TOKEN_WARN_MIN = 45         # warn when the session token has this many minutes left
SESSION_OPEN = (8, 40)      # WIB; pre-opening starts 08:45
SESSION_CLOSE = (16, 20)    # post-closing ends 16:15
LOCK_KEY = "idx-feed-collector"
RAW_ENV, RAW_KEEP_ENV = "IDX_FEED_RAW", "IDX_FEED_RAW_KEEP_DAYS"
QUEUE_MAX = 500_000


def in_session(now: datetime | None = None) -> bool:
    d = (now or datetime.now(UTC)).astimezone(WIB)
    if d.weekday() >= 5:
        return False
    t = (d.hour, d.minute)
    return SESSION_OPEN <= t < SESSION_CLOSE


def data_expected(now: datetime | None = None) -> bool:
    """Continuous-trading phases, when a healthy 100-name subscription is never silent for long."""
    d = (now or datetime.now(UTC)).astimezone(WIB)
    if d.weekday() >= 5:
        return False
    t = (d.hour, d.minute)
    if d.weekday() == 4:
        return (9, 0) <= t < (11, 30) or (14, 0) <= t < (15, 50)
    return (9, 0) <= t < (12, 0) or (13, 30) <= t < (15, 50)


def next_session_start(now: datetime | None = None) -> datetime:
    d = (now or datetime.now(UTC)).astimezone(WIB)
    start = d.replace(hour=SESSION_OPEN[0], minute=SESSION_OPEN[1], second=0, microsecond=0)
    if d >= start:
        start += timedelta(days=1)
    while start.weekday() >= 5:
        start += timedelta(days=1)
    return start


# ---- raw archive ----------------------------------------------------------------------------------------------------

class RawArchive:
    """Per-day gzip of every frame (``<u32 length><u64 receipt ms><frame>``), sync-flushed every second so a killed process
    loses at most a second, older days deleted after ``keep_days``."""

    def __init__(self, directory: Path, keep_days: int = 7):
        self.dir = directory
        self.keep_days = keep_days
        self.fh = None
        self.day: str | None = None
        self.last_flush = 0.0
        self.bytes = 0

    def write(self, frame: bytes, recv_ms: int) -> None:
        day = datetime.fromtimestamp(recv_ms / 1000, tz=UTC).astimezone(WIB).date().isoformat()
        if day != self.day:
            self.close()
            self.dir.mkdir(parents=True, exist_ok=True)
            self.fh = gzip.open(self.dir / f"{day}.frames.gz", "ab")
            self.day = day
            self._prune()
        self.fh.write(struct.pack("<IQ", len(frame), recv_ms) + frame)
        self.bytes += len(frame) + 12
        if time.monotonic() - self.last_flush >= 1.0:
            self.fh.flush()
            self.last_flush = time.monotonic()

    def _prune(self) -> None:
        cutoff = (datetime.now(UTC).astimezone(WIB).date() - timedelta(days=self.keep_days)).isoformat()
        for p in self.dir.glob("*.frames.gz"):
            if p.name[:10] < cutoff:
                try:
                    p.unlink()
                except OSError:
                    pass

    def close(self) -> None:
        if self.fh:
            self.fh.close()
            self.fh = None

    @staticmethod
    def iter_frames(path: Path) -> Iterator[tuple[bytes, float]]:
        """(frame, receipt time in seconds) from an archive; a truncated tail (killed mid-write) ends the iteration."""
        with gzip.open(path, "rb") as fh:
            while True:
                try:
                    head = fh.read(12)
                    if len(head) < 12:
                        return
                    ln, ms = struct.unpack("<IQ", head)
                    frame = fh.read(ln)
                except (EOFError, gzip.BadGzipFile, OSError):
                    return
                if len(frame) < ln:
                    return
                yield frame, ms / 1000


# ---- frame processing (shared by live and replay) -------------------------------------------------------------------

class Processor:
    """Decoded frames -> pending trade rows and sampled book rows. Pure in-memory; ``drain()`` hands the rows to a writer."""

    def __init__(self):
        self.trades: list[dict[str, Any]] = []
        self.books: dict[str, dict[str, Any]] = {}
        self.last_freq: dict[str, int] = {}
        self.n_frames = self.n_data = self.n_trades = self.n_books = self.n_skipped_matches = self.n_undecodable = 0
        self.last_data = 0.0            # receipt time of the last liveprice/orderbook frame

    def on_frame(self, frame: bytes, now: float) -> dict[str, Any] | None:
        self.n_frames += 1
        try:
            msg = proto.decode_frame(frame)
        except ValueError:
            self.n_undecodable += 1
            return None
        kind = msg["kind"]
        if kind == "liveprice":
            self.n_data += 1
            self.last_data = now
            row = trade_row(msg, datetime.fromtimestamp(now, tz=UTC))
            if row:
                self.trades.append(row)
                f = row.get("cum_freq")
                if f is not None:
                    prev = self.last_freq.get(row["code"])
                    if prev is not None and f > prev + 1:
                        self.n_skipped_matches += f - prev - 1
                    self.last_freq[row["code"]] = f
        elif kind == "orderbook":
            self.n_data += 1
            self.last_data = now
            self.on_book(msg, now)
        return msg

    def on_book(self, msg: dict[str, Any], now: float) -> None:
        parsed = parse_book_body(msg.get("body") or "")
        if not parsed:
            return
        code, side, levels = parsed
        st = self.books.setdefault(code, {"bid": Side(), "offer": Side(), "ts": None, "seq": 0, "dirty": False, "updates": 0,
                                          "last_sample": 0.0, "key": None})
        st["bid" if side == "BID" else "offer"] = levels
        st["ts"] = parse_ts(msg.get("datetime") or msg.get("itch_incoming_time"), datetime.fromtimestamp(now, tz=UTC))
        st["seq"] = int(msg.get("sequence_number") or 0)
        st["updates"] += 1
        k = book_key(st["bid"], st["offer"])
        if k != st["key"]:
            st["key"] = k
            st["dirty"] = True

    def drain(self, now: float, *, force: bool = False) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        trades, self.trades = self.trades, []
        books = []
        for code, st in self.books.items():
            if st["dirty"] and st["ts"] is not None and (force or now - st["last_sample"] >= BOOK_SAMPLE_S):
                books.append(book_row(code, st["ts"], st["seq"], st["bid"], st["offer"], st["updates"]))
                st["dirty"] = False
                st["updates"] = 0
                st["last_sample"] = now
        self.n_trades += len(trades)
        self.n_books += len(books)
        return trades, books

    def reset_books(self) -> None:
        self.books.clear()


# ---- writer thread --------------------------------------------------------------------------------------------------

class Writer(threading.Thread):
    """Owns its database connection; drains a bounded queue of (kind, rows) batches; retries with backoff and keeps the
    batch on failure. Never touches the event loop."""

    def __init__(self, dsn: str, maxlen: int = QUEUE_MAX):
        super().__init__(name="feed-writer", daemon=True)
        self.dsn = dsn
        self.q: queue.Queue = queue.Queue()
        self.maxlen = maxlen
        self.pending = 0
        self.written = {"trade": 0, "book": 0}
        self.dropped = 0
        self.failures = 0
        self.last_error: str | None = None
        self.stop_ev = threading.Event()
        self.conn: psycopg.Connection | None = None

    def put(self, kind: str, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        if self.pending + len(rows) > self.maxlen:
            self.dropped += len(rows)
            return
        self.pending += len(rows)
        self.q.put((kind, rows))

    def _db(self) -> psycopg.Connection:
        if self.conn is None or self.conn.closed:
            self.conn = psycopg.connect(self.dsn, autocommit=False, connect_timeout=10)
            with self.conn.cursor() as cur:
                cur.execute("SET TIME ZONE 'UTC'")
            self.conn.commit()
        return self.conn

    def run(self) -> None:
        backoff = 1.0
        while not (self.stop_ev.is_set() and self.q.empty()):
            try:
                kind, rows = self.q.get(timeout=0.5)
            except queue.Empty:
                continue
            while True:
                try:
                    (store.insert_trades if kind == "trade" else store.insert_books)(self._db(), rows)
                    self.written[kind] += len(rows)
                    self.pending -= len(rows)
                    backoff = 1.0
                    break
                except Exception as e:
                    self.failures += 1
                    self.last_error = f"{type(e).__name__}: {e}"[:200]
                    logger.warning("feed writer: %s (retry in %.0fs, %d rows pending)", self.last_error, backoff, self.pending)
                    try:
                        if self.conn:
                            self.conn.close()
                    except Exception:
                        pass
                    self.conn = None
                    if self.stop_ev.wait(backoff):
                        self.dropped += len(rows)
                        self.pending -= len(rows)
                        break
                    backoff = min(backoff * 2, 15.0)

    def stop(self, timeout: float = 10.0) -> None:
        self.stop_ev.set()
        self.join(timeout)


# ---- the collector --------------------------------------------------------------------------------------------------

class Collector:
    def __init__(self, dsn: str, *, raw_dir: Path | None = None, keep_days: int = 7):
        self.dsn = dsn
        self.conn: psycopg.Connection | None = None
        self.ws = None
        self.stop = asyncio.Event()
        self.proc = Processor()
        self.writer = Writer(dsn)
        self.reconnects = 0
        self.fails = 0
        self.last_frame = 0.0
        self.ping_sent = 0.0
        self.channels: dict[str, list[str]] = {}
        self.symbols_loaded = 0.0
        self.token: dict[str, Any] | None = None
        self.key: str | None = None
        self.state = "off"
        self.raw = RawArchive(raw_dir, keep_days) if raw_dir else None
        self.alerted_token = False
        self.warned_expiry = False
        self.renew_tried = False
        self.started = datetime.now(UTC)
        self.connected_at: datetime | None = None

    # ---- db (loop thread only) -----------------------------------------------------------------------------------
    def db(self) -> psycopg.Connection:
        if self.conn is None or self.conn.closed:
            self.conn = psycopg.connect(self.dsn, autocommit=False, connect_timeout=10)
            with self.conn.cursor() as cur:
                cur.execute("SET TIME ZONE 'UTC'")
            self.conn.commit()
        return self.conn

    def _reset_db(self) -> None:
        try:
            if self.conn:
                self.conn.close()
        except Exception:
            pass
        self.conn = None

    def set_state(self, state: str, detail: str | None = None) -> None:
        self.state = state
        p, w = self.proc, self.writer
        if detail is None and state == "live":
            detail = (f"data {p.n_data:,} frames, queue {w.pending}, skipped matches {p.n_skipped_matches:,}"
                      + (f", writer errors {w.failures} ({w.last_error})" if w.failures else "") + (f", dropped {w.dropped}" if w.dropped else ""))
        try:
            store.set_status(self.db(), state, detail, n_frames=p.n_frames, n_trades=w.written["trade"], n_books=w.written["book"],
                             n_symbols=sum(len(v) for v in self.channels.values()), reconnects=self.reconnects, pid=os.getpid(),
                             started_at=self.started, connected_at=self.connected_at,
                             last_frame_at=datetime.fromtimestamp(self.last_frame, tz=UTC) if self.last_frame else None)
        except Exception as e:
            logger.warning("feed status write failed: %s", e)
            self._reset_db()

    def event(self, kind: str, detail: str | None = None, data: dict[str, Any] | None = None) -> None:
        logger.info("feed %s: %s %s", kind, detail or "", data or "")
        try:
            store.event(self.db(), kind, detail, data)
        except Exception as e:
            logger.warning("feed event write failed: %s", e)
            self._reset_db()

    def singleton(self) -> bool:
        with self.db().cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(hashtext(%s))", (LOCK_KEY,))
            got = bool(cur.fetchone()[0])
        self.db().commit()
        return got

    # ---- token + key ---------------------------------------------------------------------------------------------
    def load_token(self) -> bool:
        tok = store.load_token(self.db())
        st = store.token_status(tok)
        if not st["valid"]:
            self.token = None
            if not self.alerted_token:
                self.alerted_token = True
                self.event("token", "no valid session token - waiting for a paste", st)
                notify.send("IDX feed: Stockbit session token missing or expired. Log in to stockbit.com and paste the "
                            "credentialStorage cookie at http://127.0.0.1:8001/idx/feed/relay (or STOCKBIT_TOKEN in idx-local.env); "
                            "the collector resumes within a minute.", title="IDX feed")
            return False
        if self.token is None or self.token["access_token"] != tok["access_token"]:
            self.event("token", f"using token from {tok.get('source')}", {"expires_at": st["expires_at"], "user_id": tok.get("user_id")})
            self.warned_expiry = False
            self.renew_tried = False
        self.token = tok
        self.alerted_token = False
        return True

    def renew_token(self) -> str | None:
        """Worker thread: refresh the session from the newest refresh token (relay row / env) on its own connection and
        write the new pair back; the loop thread picks it up through load_token(). Returns the error text on failure."""
        from .. import broker
        try:
            with psycopg.connect(self.dsn, connect_timeout=10) as conn:
                if not broker.newest_refresh_token(conn=conn):
                    return "no refresh token known (paste the credentialStorage cookie, not just the access JWT)"
                broker.refresh_and_persist(conn=conn)
        except (broker.BrokerFetchError, psycopg.Error, OSError) as e:
            return f"{type(e).__name__}: {e}"[:300]
        return None

    async def check_expiry(self) -> None:
        """45 min before the token runs out: renew it from the refresh token (once per token); warn once, asking for a
        paste, only when that is not possible."""
        if not self.token or not self.token.get("expires_at"):
            return
        left = (self.token["expires_at"] - datetime.now(UTC)).total_seconds() / 60
        if left > TOKEN_WARN_MIN:
            return
        if not self.renew_tried:
            self.renew_tried = True
            err = await asyncio.to_thread(self.renew_token)
            if err is None and self.load_token() and self.token and self.token["expires_at"] > datetime.now(UTC) + timedelta(minutes=TOKEN_WARN_MIN):
                return                                                           # load_token logged "using token from refresh"
            self.event("token", f"renewal failed: {err or 'no fresher token after refresh'}")
        if not self.warned_expiry:
            self.warned_expiry = True
            self.event("token", f"session token expires in {left:.0f} min")
            notify.send(f"IDX feed: Stockbit session token expires in {left:.0f} min and could not be renewed. Log in and paste "
                        "the new cookie at http://127.0.0.1:8001/idx/feed/relay to keep streaming.", title="IDX feed")

    async def fetch_key(self) -> str:
        headers = {"Authorization": f"Bearer {self.token['access_token']}", "Origin": ORIGIN, "Referer": ORIGIN + "/orderbook",
                   "User-Agent": UA, "Accept": "application/json", "X-Platform": "web"}
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(KEY_URL, headers=headers)
        if r.status_code == 401:
            raise PermissionError("websocket key: 401 (token rejected)")
        r.raise_for_status()
        body = r.json()
        key = (body.get("data") or {}).get("key") if isinstance(body, dict) else None
        if not key:
            raise RuntimeError(f"websocket key: unexpected body keys {list(body)[:6] if isinstance(body, dict) else type(body).__name__}")
        return key

    # ---- session -------------------------------------------------------------------------------------------------
    def load_symbols(self) -> bool:
        try:
            chans = store.symbols(self.db())
        except Exception as e:
            logger.warning("feed symbols reload failed: %s", e)
            self._reset_db()
            return False
        self.symbols_loaded = time.monotonic()
        changed = chans != self.channels
        self.channels = chans
        return changed

    async def send_auth(self) -> None:
        uid = self.token.get("user_id") or ""
        self.key = await self.fetch_key()
        await self.ws.send(proto.encode_request(user_id=uid, key=self.key, access_token=self.token["access_token"]))
        self.event("auth", "auth frame sent", {"user_id": uid, "key_len": len(self.key)})

    async def send_subscribe(self, why: str = "subscribed") -> None:
        uid = self.token.get("user_id") or ""
        await self.ws.send(proto.encode_request(user_id=uid, key=self.key, access_token=self.token["access_token"], channels=self.channels))
        self.event("subscribe", why, {k: len(v) for k, v in self.channels.items()})

    async def run_session(self) -> str:
        """One websocket lifetime. Returns why it ended: closed | pong | stall | window | token_expired | stopped."""
        self.set_state("connecting")
        headers = {"Origin": ORIGIN, "User-Agent": UA}
        async with websockets.connect(WS_URL, subprotocols=["web"], additional_headers=headers, max_size=None,
                                      ping_interval=None, open_timeout=20, close_timeout=5) as ws:
            self.ws = ws
            self.connected_at = datetime.now(UTC)
            self.event("connect", "websocket open", {"url": WS_URL, "attempt": self.fails + 1})
            await self.send_auth()
            self.load_symbols()
            if not self.channels:
                self.event("subscribe", "no symbols enabled - idle connection")
            else:
                await self.send_subscribe()
            self.set_state("live")
            self.fails = 0
            now = time.time()
            self.last_frame = now
            self.proc.last_data = now
            self.ping_sent = 0.0
            self.proc.reset_books()
            reauth = 0
            resub_at = 0.0
            while not self.stop.is_set():
                if not in_session():
                    self.event("close", "session window closed")
                    return "window"
                now = time.time()
                if self.ping_sent:
                    timeout = max(0.2, PONG_GRACE_S - (now - self.ping_sent))
                else:
                    timeout = max(0.5, HEARTBEAT_S - (now - self.last_frame))
                try:
                    frame = await asyncio.wait_for(ws.recv(), timeout=timeout)
                except TimeoutError:
                    now = time.time()
                    if self.ping_sent and now - self.ping_sent >= PONG_GRACE_S:
                        self.event("close", "pong late - closing", {"silence_s": round(now - self.last_frame)})
                        return "pong"
                    if not self.ping_sent and now - self.last_frame >= HEARTBEAT_S:
                        await ws.send(proto.encode_request(ping="ping"))
                        self.ping_sent = now
                    stalled = await self._stall_check(now, resub_at)
                    if stalled == "resub":
                        resub_at = now
                    elif stalled == "reconnect":
                        return "stall"
                    continue
                now = time.time()
                self.last_frame = now
                self.ping_sent = 0.0
                if isinstance(frame, str):
                    frame = frame.encode()
                if self.raw:
                    try:
                        self.raw.write(frame, int(now * 1000))
                    except OSError as e:
                        logger.warning("raw archive write failed: %s", e)
                        self.raw = None
                msg = self.proc.on_frame(frame, now)
                if msg and msg["kind"] == "error":
                    self.event("error", f"feed error {msg.get('code')}: {msg.get('message')}", msg)
                    if msg.get("code") == 401 or "auth" in (msg.get("message") or "").lower():
                        reauth += 1
                        if reauth > 3:
                            self.set_state("token_expired", "feed refused the token 3x")
                            self.token = None
                            self.alerted_token = False
                            return "token_expired"
                        await self.send_auth()
                        if self.channels:
                            await self.send_subscribe("re-subscribed after auth error")
                stalled = await self._stall_check(now, resub_at)
                if stalled == "resub":
                    resub_at = now
                elif stalled == "reconnect":
                    return "stall"
                if time.monotonic() - self.symbols_loaded > SYMBOL_RELOAD_S:
                    if self.load_symbols() and self.channels:
                        await self.send_subscribe("symbol list changed")
        return "stopped" if self.stop.is_set() else "closed"

    async def _stall_check(self, now: float, resub_at: float) -> str | None:
        """Zombie-subscription watchdog: pongs arrive but no data does during a continuous phase."""
        if not self.channels or not data_expected():
            return None
        silent = now - max(self.proc.last_data, resub_at)
        if resub_at and silent >= STALL_RECONNECT_S - STALL_RESUB_S:
            self.event("close", f"no data for {now - self.proc.last_data:.0f}s after a resubscribe - reconnecting")
            return "reconnect"
        if not resub_at and silent >= STALL_RESUB_S:
            await self.send_subscribe(f"no data for {silent:.0f}s - resubscribed")
            return "resub"
        return None

    # ---- periodic writers ----------------------------------------------------------------------------------------
    async def flusher(self) -> None:
        last_status = 0.0
        while not self.stop.is_set():
            await asyncio.sleep(FLUSH_S)
            self.flush()
            if time.monotonic() - last_status >= STATUS_S:
                last_status = time.monotonic()
                self.set_state(self.state)
                await self.check_expiry()

    def flush(self, *, force: bool = False) -> None:
        trades, books = self.proc.drain(time.monotonic(), force=force)
        self.writer.put("trade", trades)
        self.writer.put("book", books)

    # ---- main loop -----------------------------------------------------------------------------------------------
    async def run(self) -> int:
        if not self.singleton():
            logger.error("another collector holds the advisory lock %r - exiting", LOCK_KEY)
            return 2
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self.stop.set)
            except NotImplementedError:      # Windows: no add_signal_handler; KeyboardInterrupt still lands in the loop
                pass
        self.writer.start()
        self.event("start", "collector started", {"pid": os.getpid(), "raw": bool(self.raw)})
        flusher = asyncio.create_task(self.flusher())
        try:
            while not self.stop.is_set():
                if not in_session():
                    nxt = next_session_start()
                    self.set_state("waiting", f"next session {nxt.strftime('%a %Y-%m-%d %H:%M')} WIB")
                    await self._sleep(min(60.0, max(1.0, (nxt - datetime.now(UTC).astimezone(WIB)).total_seconds())))
                    continue
                if not self.load_token():
                    self.set_state("token_expired", "waiting for a session token")
                    await self._sleep(60)
                    continue
                why = "error"
                try:
                    why = await self.run_session()
                except (websockets.exceptions.WebSocketException, OSError, httpx.HTTPError, RuntimeError, TimeoutError) as e:
                    self.event("error", f"{type(e).__name__}: {e}"[:300])
                except PermissionError as e:
                    self.event("error", str(e))
                    self.set_state("token_expired", str(e))
                    self.token = None
                    self.alerted_token = False
                    continue
                finally:
                    self.ws = None
                    self.flush(force=True)
                if self.stop.is_set() or why in ("token_expired", "window"):
                    continue
                self.fails += 1
                self.reconnects += 1
                delay = min(30.0, 2 ** min(self.fails, 5))
                self.set_state("reconnecting", f"after {why}: attempt {self.fails} in {delay:.0f}s")
                if self.fails == 5:
                    notify.send(f"IDX feed: 5 reconnects in a row (last: {why}); still trying.", title="IDX feed")
                await self._sleep(delay)
        finally:
            self.stop.set()
            flusher.cancel()
            self.flush(force=True)
            self.writer.stop()
            if self.raw:
                self.raw.close()
            self.set_state("off", "collector stopped")
            self.event("stop", "collector stopped", {"frames": self.proc.n_frames, "trades": self.writer.written["trade"],
                                                     "books": self.writer.written["book"], "dropped": self.writer.dropped})
        return 0

    async def _sleep(self, s: float) -> None:
        try:
            await asyncio.wait_for(self.stop.wait(), timeout=s)
        except TimeoutError:
            pass


# ---- replay ---------------------------------------------------------------------------------------------------------

def replay(dsn: str, path: Path) -> dict[str, int]:
    """Re-run the parser over an archived day and insert what it yields (duplicates are no-ops): after a database outage
    or a parser fix. Book sampling is re-done on the archived receipt times."""
    proc = Processor()
    conn = psycopg.connect(dsn, autocommit=False)
    with conn.cursor() as cur:
        cur.execute("SET TIME ZONE 'UTC'")
    conn.commit()
    n = {"frames": 0, "trades": 0, "books": 0}
    last_drain = 0.0
    for frame, at in RawArchive.iter_frames(path):
        proc.on_frame(frame, at)
        n["frames"] += 1
        if at - last_drain >= BOOK_SAMPLE_S:
            trades, books = proc.drain(at)
            n["trades"] += store.insert_trades(conn, trades)
            n["books"] += store.insert_books(conn, books)
            last_drain = at
    trades, books = proc.drain(last_drain + BOOK_SAMPLE_S, force=True)
    n["trades"] += store.insert_trades(conn, trades)
    n["books"] += store.insert_books(conn, books)
    conn.close()
    return n


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="idx feed run", description="Stockbit datafeed collector")
    ap.add_argument("--raw", action="store_true", help=f"archive raw frames (default on; {RAW_ENV}=0 or --no-raw turns it off)")
    ap.add_argument("--no-raw", action="store_true")
    ap.add_argument("--raw-dir", default=None)
    ap.add_argument("--replay", default=None, help="re-ingest one archived day (path to *.frames.gz) and exit")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    dsn = os.environ.get("INGEST_DB_DSN")
    if not dsn:
        from ...shared.settings import get_settings
        s = get_settings()
        dsn = s.db_dsn or psycopg.conninfo.make_conninfo(**s.db_kwargs())
    if a.replay:
        n = replay(dsn, Path(a.replay))
        print(f"replayed {n['frames']:,} frames -> {n['trades']:,} trades, {n['books']:,} book samples")
        return 0
    env_raw = os.environ.get(RAW_ENV, "").strip().lower()
    raw = not a.no_raw and env_raw not in ("0", "false", "no", "off")
    raw_dir = Path(a.raw_dir) if a.raw_dir else Path(os.environ.get("IDX_LOG_DIR", "../logs/idx")) / "feed"
    keep = int(os.environ.get(RAW_KEEP_ENV, "7") or 7)
    c = Collector(dsn, raw_dir=raw_dir if raw else None, keep_days=keep)
    try:
        return asyncio.run(c.run())
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
