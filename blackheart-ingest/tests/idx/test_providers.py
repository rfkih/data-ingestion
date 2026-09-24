"""The provider seam (2026-09-23): a role is served by one provider, a job pins it, and a provider that cannot serve a
role cannot be toggled on. The guards matter more than the happy path - every one of them prevents a silent wrong trade
rather than an outage."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from blackheart_ingest.idx.providers import ajaib, registry, stockbit
from blackheart_ingest.idx.providers.base import Health, NotSupported, ProviderError
from blackheart_ingest.idx.providers.registry import Pinned


def test_roles_and_providers_are_closed_sets() -> None:
    from blackheart_ingest.idx.providers.base import PROVIDERS, ROLES
    assert ROLES == ("feed", "order")
    assert set(PROVIDERS) == {"stockbit", "ajaib"}


def test_every_adapter_declares_all_three_capabilities() -> None:
    for ad in (stockbit.ADAPTER, ajaib.ADAPTER):
        assert set(ad) == {"tokens", "feed", "orders"}, "a missing key reads as 'unsupported' by accident"


def test_nobody_implements_orders_yet() -> None:
    # If this ever fails, an order gateway was added - it must ship dry-run-by-default behind hard limits first.
    assert stockbit.ADAPTER["orders"] is None
    assert ajaib.ADAPTER["orders"] is None


# ---- the guards ---------------------------------------------------------------------------------------------------
def test_a_provider_cannot_serve_a_role_it_has_no_adapter_for() -> None:
    p = Pinned(role="feed", provider="ajaib", at=datetime.now(UTC))
    with pytest.raises(NotSupported) as e:
        registry.feed_of(p)
    assert "feed" in str(e.value)


def test_an_unknown_provider_is_an_error_not_a_silent_default() -> None:
    p = Pinned(role="feed", provider="mandiri_sekuritas", at=datetime.now(UTC))
    with pytest.raises(ProviderError):
        registry.feed_of(p)


def test_ajaib_refuses_a_stockbit_cookie_before_touching_the_database() -> None:
    # accept_paste classifies first; a Stockbit cookie is refused before any connection is used (conn=None proves it)
    with pytest.raises(NotSupported) as e:
        ajaib.TOKENS.accept_paste(None, "credentialStorage=whatever")
    assert "Stockbit" in str(e.value)


def test_ajaib_registers_no_feed_adapter_at_all() -> None:
    # The stronger statement than "reports itself down": nothing is registered, so registry.set_active refuses the
    # toggle before any health check could be consulted. (Replaces a tautological test - 2026-09-23 review, #11.)
    assert ajaib.ADAPTER["feed"] is None
    assert "feed" not in {k for k, v in ajaib.ADAPTER.items() if v is not None}


def test_the_feed_protocol_has_no_frame_iterator() -> None:
    # The collector is a process that writes tables; readers read tables. A frames() on the protocol would be raised
    # by the only real implementation (review #10), so its absence is a contract worth pinning.
    from blackheart_ingest.idx.providers.base import MarketFeed
    assert not hasattr(MarketFeed, "frames")
    assert not hasattr(stockbit.FEED, "frames")


def test_ajaib_feed_class_is_honest_when_asked_directly() -> None:
    h = ajaib.AjaibFeed().health(None)
    assert h.ok is False and "not reverse-engineered" in h.detail


def test_tokens_are_addressed_by_provider_not_by_role() -> None:
    assert registry.tokens_of("stockbit").provider == "stockbit"
    assert registry.tokens_of("ajaib").provider == "ajaib"
    with pytest.raises(ProviderError):
        registry.tokens_of("nope")


# ---- pinning ------------------------------------------------------------------------------------------------------
def test_a_pin_is_immutable_so_a_toggle_cannot_move_it_mid_job() -> None:
    p = Pinned(role="feed", provider="stockbit", at=datetime.now(UTC))
    with pytest.raises(FrozenInstanceError):
        p.provider = "ajaib"          # type: ignore[misc]
    assert str(p) == "feed=stockbit"


def test_unknown_role_is_rejected_before_any_query() -> None:
    with pytest.raises(ValueError):
        registry.active(None, "portfolio")
    with pytest.raises(ValueError):
        registry.set_active(None, "portfolio", "stockbit")


def test_health_summary_reads_as_an_alert_line() -> None:
    h = Health(provider="stockbit", role="feed", ok=False, detail="session expired",
               checked_at=datetime.now(UTC))
    assert h.summary == "stockbit/feed: DOWN - session expired"


# ---- provenance (review #2) ---------------------------------------------------------------------------------------
def test_mixed_provenance_is_refused_and_names_both_providers() -> None:
    from blackheart_ingest.idx.providers.registry import provenance_problem
    p = Pinned(role="feed", provider="ajaib", at=datetime.now(UTC))
    why = provenance_problem("stockbit", p)
    assert why and "stockbit" in why and "ajaib" in why and "refusing" in why


def test_matching_or_unknown_provenance_passes() -> None:
    from blackheart_ingest.idx.providers.registry import provenance_problem
    p = Pinned(role="feed", provider="stockbit", at=datetime.now(UTC))
    assert provenance_problem("stockbit", p) is None
    assert provenance_problem(None, p) is None            # no collector has ever written: nothing to contradict


# ---- ajaib paste classification -----------------------------------------------------------------------------------
def test_ajaib_refuses_a_stockbit_cookie_and_an_empty_paste() -> None:
    with pytest.raises(NotSupported):
        ajaib.classify_paste("credentialStorage=eyJ...; path=/")
    with pytest.raises(NotSupported):
        ajaib.classify_paste("   ")


def test_ajaib_reads_expiry_from_a_jwt_and_keeps_an_opaque_token_as_is() -> None:
    import base64
    import json
    hdr = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).decode().rstrip("=")
    body = base64.urlsafe_b64encode(json.dumps({"sub": "u1", "exp": 4102444800}).encode()).decode().rstrip("=")
    f = ajaib.classify_paste(f"{hdr}.{body}.sig")
    assert f["raw_keys"]["kind"] == "jwt" and f["expires_at"].year == 2100 and f["user_id"] == "u1"
    g = ajaib.classify_paste("opaque-session-abc123")
    assert g["raw_keys"]["kind"] == "opaque" and g["expires_at"] is None
