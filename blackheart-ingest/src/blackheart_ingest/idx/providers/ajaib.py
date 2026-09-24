"""Ajaib - the standby. Declared, health-checkable, and honest about what it cannot do yet.

What is known as of 2026-09-23, from watching https://trade.ajaib.co.id with the network log open:

  the market data is a WEBSOCKET. Two full page loads produced 80 HTTP requests and not one belonged to Ajaib - every
  single one was Google/Facebook/TikTok/Bing/New Relic. The Multi Orderbook layout updates eight order books live with
  no HTTP traffic at all, which only leaves a socket. The New Relic beacon lists ``xhr`` instrumentation, so REST does
  exist; it just is not used for the tape.

  therefore the feed adapter cannot be written from observation alone. It needs the socket's handshake, subscribe
  message and frame format - the same reverse-engineering the Stockbit feed needed, not an afternoon's work.

  the order endpoint has NOT been captured. It will only appear when a real order is sent, which is the operator's
  action to take, never this code's.

What works today: a separate session row (paste it in Blackridge > More > Brokers; nothing can overwrite Stockbit's).
What raises ``NotSupported`` on purpose: renewing (no refresh flow captured), the feed, orders. That is the point:
``registry.set_active`` asks the adapter whether it can serve a role before writing the toggle, so the desk physically
cannot be switched onto a provider that would fail at the next scan. The toggle turns on when the adapter is real.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import psycopg

from .base import Health, NotSupported, TokenState

PROVIDER = "ajaib"


def classify_paste(text: str) -> dict[str, Any]:
    """Pure. What the operator pasted for Ajaib, and when it expires if that can be read. Refuses a paste that is
    plainly Stockbit's (the ``credentialStorage`` cookie) so a slip of the clipboard cannot store the wrong broker's
    session under this provider."""
    from ..feed.store import _jwt_claims, _looks_jwt
    t = (text or "").strip()
    if not t:
        raise NotSupported(PROVIDER, "nothing pasted")
    low = t.lower()
    if "credentialstorage" in low or '"stockbit' in low or "stockbit.com" in low:
        raise NotSupported(PROVIDER, "that is a Stockbit cookie - paste it under Stockbit, not Ajaib")
    if _looks_jwt(t):
        claims = _jwt_claims(t)
        exp = datetime.fromtimestamp(int(claims["exp"]), tz=UTC) if claims.get("exp") else None
        return {"access_token": t, "refresh_token": None, "user_id": str(claims.get("sub") or "") or None, "expires_at": exp,
                "raw_keys": {"kind": "jwt", "claims": sorted(claims)}}
    return {"access_token": t, "refresh_token": None, "user_id": None, "expires_at": None,
            "raw_keys": {"kind": "opaque", "len": len(t)}}


class AjaibTokens:
    """Ajaib's session lives on its own ``idx.feed_token`` row. Storing and reading work; RENEWING does not - no refresh
    flow has been captured from trade.ajaib.co.id yet, so the operator pastes again when the session runs out, and the
    token guard treats an Ajaib session as warn-only unless Ajaib is the active feed provider."""

    provider = PROVIDER

    def token_state(self, conn: psycopg.Connection) -> TokenState:
        from ..feed import store as fs
        s = fs.token_status(fs.load_token(conn, provider=PROVIDER))
        return TokenState(present=bool(s.get("present")), valid=bool(s.get("valid")), expires_at=s.get("expires_at"),
                          minutes_left=s.get("minutes_left"), source=s.get("source"), user_id=s.get("user_id"),
                          refresh_present=False)

    def renew(self, conn: psycopg.Connection, *, force: bool = False, need_until: datetime | None = None) -> TokenState:
        raise NotSupported(PROVIDER, "no refresh flow is known for Ajaib yet - paste a fresh session instead")

    def accept_paste(self, conn: psycopg.Connection, payload: str) -> TokenState:
        from ..feed import store as fs
        fields = classify_paste(payload)
        fs.save_token(conn, fields, source="paste", provider=PROVIDER)
        return self.token_state(conn)


class AjaibFeed:
    provider = PROVIDER

    def health(self, conn: psycopg.Connection) -> Health:
        return Health(provider=PROVIDER, role="feed", ok=False,
                      detail="websocket protocol not reverse-engineered yet - standby only",
                      checked_at=datetime.now(UTC))

    def subscribe(self, conn: psycopg.Connection, codes: list[str]) -> None:
        raise NotSupported(PROVIDER, "no feed adapter yet")


TOKENS = AjaibTokens()
# feed and orders stay None: registry.set_active reads these to refuse a toggle onto a role this provider cannot serve.
ADAPTER: dict[str, Any] = {"tokens": TOKENS, "feed": None, "orders": None}
