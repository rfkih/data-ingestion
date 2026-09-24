"""Which provider serves which role right now, and the one safe way to ask.

Everything downstream calls ``pin()`` and holds the handle. Nothing downstream reads ``idx.provider_role`` directly, and
nothing downstream branches on a provider name - if code has to ask "is this Stockbit?", the abstraction has leaked and
the fix belongs in the adapter, not in the caller.

Why pinning rather than a lookup per call: a gap-fade scan reads opening prints, then the resting offers, then sizes a
book. Those three reads must come from the same market. A failover between them compares two markets and sizes on the
difference - a silent correctness bug that no alert would catch. ``pin()`` resolves once; the handle it returns keeps
serving the provider chosen at that moment even if the toggle moves underneath.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import psycopg

from ..card import _rows
from .base import ROLES, Health, MarketFeed, NotSupported, OrderGateway, ProviderError, TokenSource

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Pinned:
    """A provider chosen for the length of one job. Immutable on purpose: the toggle can move, this cannot."""
    role: str
    provider: str
    at: datetime

    def __str__(self) -> str:
        return f"{self.role}={self.provider}"


def _adapters() -> dict[str, dict[str, Any]]:
    """Imported lazily so a broken adapter cannot stop the whole worker from starting."""
    from . import ajaib, stockbit
    return {"stockbit": stockbit.ADAPTER, "ajaib": ajaib.ADAPTER}


def roles(conn: psycopg.Connection) -> list[dict[str, Any]]:
    return _rows(conn, """SELECT role, provider, fallback, auto_failover, changed_at, changed_by, note
                            FROM idx.provider_role ORDER BY role""", (),
                 ["role", "provider", "fallback", "auto_failover", "changed_at", "changed_by", "note"])


def active(conn: psycopg.Connection, role: str) -> str:
    """The provider configured for ``role``. Falls back to stockbit only if the row is missing, and says so loudly."""
    if role not in ROLES:
        raise ValueError(f"unknown role {role!r}; expected one of {ROLES}")
    rows = _rows(conn, "SELECT provider FROM idx.provider_role WHERE role = %s", (role,), ["provider"])
    if not rows:
        logger.warning("idx provider: no row for role %s - defaulting to stockbit", role)
        return "stockbit"
    return str(rows[0]["provider"])


def pin(conn: psycopg.Connection, role: str) -> Pinned:
    """Resolve the provider for one job. Call this ONCE, at the top, and pass the handle down."""
    p = Pinned(role=role, provider=active(conn, role), at=datetime.now(UTC))
    logger.info("idx provider pinned %s", p)
    return p


def _capability(pinned: Pinned, attr: str) -> Any:
    ad = _adapters().get(pinned.provider)
    if ad is None:
        raise ProviderError(pinned.provider, "no adapter is registered for this provider")
    cap = ad.get(attr)
    if cap is None:
        raise NotSupported(pinned.provider, f"does not implement {attr}; check the {pinned.role} toggle")
    return cap


def feed_of(pinned: Pinned) -> MarketFeed:
    return _capability(pinned, "feed")


def tokens_of(provider: str) -> TokenSource:
    """Credentials are addressed by provider, not by role: the operator renews Ajaib's session whether or not Ajaib is
    currently serving anything."""
    ad = _adapters().get(provider)
    if ad is None:
        raise ProviderError(provider, "no adapter is registered for this provider")
    src = ad.get("tokens")
    if src is None:
        raise NotSupported(provider, "has no session to renew")
    return src


def orders_of(pinned: Pinned) -> OrderGateway:
    return _capability(pinned, "orders")


def health(conn: psycopg.Connection) -> list[Health]:
    """Every provider's state for every role it claims, active or standby. Never raises: a provider that blows up while
    being asked how it is IS the answer."""
    out: list[Health] = []
    now = datetime.now(UTC)
    for name, ad in _adapters().items():
        for role, attr in (("feed", "feed"), ("order", "orders")):
            cap = ad.get(attr)
            if cap is None:
                continue
            try:
                out.append(cap.health(conn))
            except Exception as e:
                out.append(Health(provider=name, role=role, ok=False,
                                  detail=f"{type(e).__name__}: {e}", checked_at=now))
    return out


def set_active(conn: psycopg.Connection, role: str, provider: str, *, actor: str | None = None,
               reason: str = "operator", note: str | None = None) -> dict[str, Any]:
    """Move a role to another provider. Always journalled; refuses a provider that cannot serve the role, so the desk
    cannot be toggled into a state where the next job raises."""
    if role not in ROLES:
        raise ValueError(f"unknown role {role!r}")
    ad = _adapters().get(provider)
    if ad is None:
        raise ProviderError(provider, "no adapter is registered for this provider")
    if ad.get("feed" if role == "feed" else "orders") is None:
        raise NotSupported(provider, f"cannot serve the {role} role yet")
    before = active(conn, role)
    with conn.cursor() as cur:
        cur.execute("""UPDATE idx.provider_role SET provider = %s, changed_at = now(), changed_by = %s, note = %s
                        WHERE role = %s""", (provider, actor, note, role))
        cur.execute("""INSERT INTO idx.provider_event (role, from_provider, to_provider, reason, actor)
                       VALUES (%s, %s, %s, %s, %s)""", (role, before, provider, reason, actor))
    conn.commit()
    logger.info("idx provider %s: %s -> %s (%s)", role, before, provider, reason)
    return {"role": role, "from": before, "to": provider, "reason": reason}


def streaming_provider(conn: psycopg.Connection) -> str | None:
    """Which provider's collector filled the feed tables most recently - the ``feed_status`` row whose heartbeat moved
    last. This is the session-level provenance migration 0031 chose over a per-row column."""
    rows = _rows(conn, "SELECT provider FROM idx.feed_status ORDER BY updated_at DESC NULLS LAST LIMIT 1", (), ["provider"])
    return str(rows[0]["provider"]) if rows else None


def provenance_problem(streaming: str | None, pinned: Pinned) -> str | None:
    """Pure. The one sentence that stops a job when the tables were filled by a provider other than the one the toggle
    names. A scan that prices gaps off Stockbit's prints because the toggle says Ajaib (or the reverse) has compared two
    markets; refusing is the only safe answer, and the sentence names both so the operator can fix the toggle."""
    if streaming and streaming != pinned.provider:
        return (f"the feed tables were filled by {streaming} but the {pinned.role} toggle says {pinned.provider} - "
                f"refusing to act on mixed provenance (fix the toggle in Blackridge > More > Brokers)")
    return None


def token_states(conn: psycopg.Connection) -> dict[str, Any]:
    """Every provider's session, for the toggle screen. A provider whose token source blows up is reported, not raised."""
    out: dict[str, Any] = {}
    for name, ad in _adapters().items():
        src = ad.get("tokens")
        if src is None:
            continue
        try:
            out[name] = src.token_state(conn)
        except Exception as e:  # the failure is the report
            out[name] = {"error": f"{type(e).__name__}: {e}"}
    return out
