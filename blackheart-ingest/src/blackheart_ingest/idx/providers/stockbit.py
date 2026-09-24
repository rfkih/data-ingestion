"""Stockbit behind the provider seam - the wired one, and the default for both roles.

This is deliberately a thin wrapper, not a rewrite: ``feed/collector.py``, ``feed/store.py`` and ``broker.py`` already
stream, store and renew, and they have been running since 2026-09-21. Moving them behind the protocol changes who calls
them, not what they do.

``feed.store``'s token and status functions take a ``provider`` since the 2026-09-23 review (#2): this adapter always
passes its own, so a Stockbit paste lands on Stockbit's row and nowhere else.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

import psycopg

from .base import Health, ProviderError, TokenState

WIB = ZoneInfo("Asia/Jakarta")

PROVIDER = "stockbit"
STALE_LIMIT_S = 120.0


def _state(tok: dict[str, Any] | None, refresh: dict[str, Any] | None) -> TokenState:
    from ..feed import store as fs
    s = fs.token_status(tok)
    r = refresh or {}
    return TokenState(
        present=bool(s.get("present")), valid=bool(s.get("valid")),
        expires_at=s.get("expires_at"), minutes_left=s.get("minutes_left"),
        source=s.get("source"), user_id=s.get("user_id"),
        refresh_present=bool(r.get("present")), refresh_expires_at=r.get("expires_at"),
        refresh_days_left=r.get("days_left"),
    )


class StockbitTokens:
    provider = PROVIDER

    def token_state(self, conn: psycopg.Connection) -> TokenState:
        from .. import broker
        from ..feed import store as fs
        return _state(fs.load_token(conn, provider=PROVIDER), broker.refresh_status(conn=conn))

    def renew(self, conn: psycopg.Connection, *, force: bool = False, need_until: datetime | None = None) -> TokenState:
        from .. import broker
        try:
            broker.renew_if_needed(conn, force=force, need_until=need_until)
        except broker.BrokerFetchError as e:
            raise ProviderError(PROVIDER, f"renew failed: {e}") from None
        return self.token_state(conn)

    def accept_paste(self, conn: psycopg.Connection, payload: str) -> TokenState:
        from ..feed import store as fs
        fields = fs.parse_relay(payload)
        if not fields.get("access_token"):
            raise ProviderError(PROVIDER, "that paste carries no Stockbit session token")
        fs.save_token(conn, fields, source="relay", provider=PROVIDER)
        return self.token_state(conn)


class StockbitFeed:
    provider = PROVIDER

    def health(self, conn: psycopg.Connection) -> Health:
        from ..feed import store as fs
        now = datetime.now(UTC)
        # feed.store.status() nests the heartbeat under "collector"; reading the top level silently
        # reports "unknown" and would trip a false failover.
        st = (fs.status(conn) or {}).get("collector") or {}
        tok = StockbitTokens().token_state(conn)
        stale = st.get("stale_s")
        streaming = str(st.get("state") or "unknown")
        # "waiting" is the collector idling outside the session with a fresh heartbeat - healthy, not down
        ok = bool(tok.valid) and streaming in ("live", "waiting") and (stale is None or float(stale) <= STALE_LIMIT_S)
        if not tok.valid:
            detail = "session expired - renew it or paste a fresh cookie"
        elif streaming not in ("live", "waiting"):
            detail = f"collector is {streaming}"
        elif streaming == "waiting" and (stale is None or float(stale) <= STALE_LIMIT_S):
            detail = "waiting for the next session, heartbeat fresh"
        elif stale is not None and float(stale) > STALE_LIMIT_S:
            # The timestamp the feed stopped at, NOT "53367s ago": a message that grows by 300 every five minutes can
            # never match the alert already open, so one dead collector wrote a fresh warning every five minutes all
            # night. The age is still on Health.stale_seconds for the screen, where a moving number belongs.
            since = st.get("last_frame_at") or st.get("updated_at")
            detail = (f"no frames since {since.astimezone(WIB):%Y-%m-%d %H:%M} WIB" if since else
                      "no frames and no heartbeat - the collector never started")
        else:
            detail = f"live, {st.get('n_symbols') or 0} symbols"
        return Health(provider=PROVIDER, role="feed", ok=ok, detail=detail, checked_at=now,
                      expires_at=tok.expires_at, stale_seconds=float(stale) if stale is not None else None)

    def subscribe(self, conn: psycopg.Connection, codes: list[str]) -> None:
        from ..feed import store as fs
        fs.set_symbols(conn, codes, reason="provider.subscribe")


TOKENS = StockbitTokens()
FEED = StockbitFeed()
ADAPTER: dict[str, Any] = {"tokens": TOKENS, "feed": FEED, "orders": None}
