"""What a broker has to be able to do for this desk, and nothing more.

The desk talks to a broker for three unrelated reasons, and they fail independently: a websocket that streams prints, an
HTTP session that has to be renewed, and (soon) an order gateway. Bundling them into one "Broker" class would mean a
provider that can stream but cannot trade is either a lie or a pile of NotImplementedError. So each reason is its own
protocol, and a provider implements the ones it actually has.

  MarketFeed   the live tape: connect, subscribe, yield frames. Stockbit has one; Ajaib's is a websocket too but its
               protocol is not reverse-engineered yet.
  TokenSource  the session behind the feed: what state is it in, renew it, accept a pasted cookie. Credentials are per
               provider and never shared - ``idx.feed_token`` is keyed by provider for exactly this reason.
  OrderGateway execution. NOTHING implements this yet, on purpose: an adapter is written only once its real request has
               been captured from the broker's own app, and it ships dry-run-by-default behind hard limits.

Two rules that are not negotiable, because getting them wrong is a correctness bug rather than an outage:

  pin the provider for the length of a decision. A job resolves its provider ONCE at the start (``registry.pin``) and
  uses that handle throughout. A scan that reads opening prints from Stockbit and then, after a mid-flight failover,
  reads offers from Ajaib has compared two different markets and will size a book on the difference.

  a switch is an event, never a side effect. Changing provider writes ``idx.provider_event``. Automatic failover is off
  by default; when it is on, it still cannot fire inside a pinned job - it takes effect on the next one.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable

ROLES = ("feed", "order")
PROVIDERS = ("stockbit", "ajaib")


@dataclass(frozen=True)
class Health:
    """Whether a provider can do its job right now. ``ok`` is the only field a caller should branch on; the rest is for
    the operator's screen and the alert text."""
    provider: str
    role: str
    ok: bool
    detail: str
    checked_at: datetime
    expires_at: datetime | None = None      # when the credential runs out, if that is the limiting factor
    stale_seconds: float | None = None      # how long since the last frame, for a feed

    @property
    def summary(self) -> str:
        return f"{self.provider}/{self.role}: {'ok' if self.ok else 'DOWN'} - {self.detail}"


@dataclass(frozen=True)
class TokenState:
    present: bool
    valid: bool
    expires_at: datetime | None
    minutes_left: float | None
    source: str | None                      # relay | paste | env | refresh
    user_id: str | None
    refresh_present: bool = False
    refresh_expires_at: datetime | None = None
    refresh_days_left: float | None = None


@runtime_checkable
class TokenSource(Protocol):
    """The session behind everything else. Each provider keeps its own row in ``idx.feed_token`` and its own relay page:
    one login must never overwrite the other's."""

    provider: str

    def token_state(self, conn: Any) -> TokenState: ...

    def renew(self, conn: Any, *, force: bool = False, need_until: datetime | None = None) -> TokenState:
        """Renew from the stored refresh token. ``need_until``: the session must still be valid at this instant (the
        token guard passes today's close plus a margin) - a provider renews if the current token will not last that
        long. Raises on failure - the caller alerts; it must never return a stale state as if it were fresh."""

    def accept_paste(self, conn: Any, payload: str) -> TokenState:
        """Take whatever the operator copied out of the broker's site and store what is usable. Must reject a paste
        belonging to a DIFFERENT provider rather than storing it under this one."""


@runtime_checkable
class MarketFeed(Protocol):
    """The live tape. Only one provider streams at a time; the other is health-checked but not subscribed.

    Deliberately NOT a frame iterator (2026-09-23 review, #10): the desk's collector is a long-running process that
    writes ``idx.feed_trade`` / ``idx.feed_book`` itself, and every reader downstream reads those tables, never a
    socket. A ``frames()`` method here would be raised by the only real implementation. What the seam owns for the
    feed role is therefore: is this provider streaming (``health``), which names it streams (``subscribe``), and the
    provenance of what is in the tables (``feed_status.provider``, checked by ``registry.pin``'s callers)."""

    provider: str

    def health(self, conn: Any) -> Health: ...

    def subscribe(self, conn: Any, codes: list[str]) -> None: ...


@dataclass(frozen=True)
class OrderRequest:
    code: str
    side: str                               # buy | sell
    lots: Decimal
    limit_price: Decimal
    client_ref: str                         # our idempotency key; a retry must never double-send


@dataclass(frozen=True)
class OrderAck:
    accepted: bool
    broker_order_id: str | None
    status: str                             # open | rejected | filled | cancelled | unknown
    detail: str
    raw: dict[str, Any]


@runtime_checkable
class OrderGateway(Protocol):
    """Execution. Deliberately unimplemented by every provider today.

    An implementation may only be written from a request captured from the broker's own app, and must ship with:
    dry-run as the default, a per-order and per-day notional cap, a symbol whitelist, a kill switch that defaults to
    off, and ``status()`` consulted before any retry - a timed-out place is of UNKNOWN status, never a failed one.
    """

    provider: str

    def health(self, conn: Any) -> Health:
        """Can this gateway take an order right now (session, kill switch, limits)? ``registry.health`` reports it
        next to the feed's, so the toggle screen shows both roles the same way."""

    def place(self, conn: Any, req: OrderRequest, *, dry_run: bool = True) -> OrderAck: ...

    def cancel(self, conn: Any, broker_order_id: str, *, dry_run: bool = True) -> OrderAck: ...

    def status(self, conn: Any, broker_order_id: str) -> OrderAck: ...


class ProviderError(RuntimeError):
    """A provider could not do what was asked. Carries the provider so an alert names it."""

    def __init__(self, provider: str, message: str) -> None:
        super().__init__(f"{provider}: {message}")
        self.provider = provider


class NotSupported(ProviderError):
    """This provider does not implement this role at all - a configuration mistake, not an outage."""
