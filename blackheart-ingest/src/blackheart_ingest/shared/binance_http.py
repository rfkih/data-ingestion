"""Shared Binance HTTP hardening (2026-06-12).

Two recurring source-module bugs live here so they can't regress per-module:

1. **Ban-safe retry predicate.** ``httpx.HTTPStatusError`` is a subclass of
   ``httpx.HTTPError``, so the old per-module retry policies blindly retried
   EVERY status — including 429 (rate limit) and 418 (IP ban) — 3-5 times
   with backoff, ignoring ``Retry-After``. Binance's documented escalation
   is 429 → 418 → progressively longer IP bans, and ingest shares the VPS
   public IP with the LIVE trading JVM's order placement: an aggressive
   backfill could ban live trading. Policy: retry transport/timeout errors
   and 5xx; NEVER retry 4xx (429/418 abort the pull loudly — the scheduled
   re-pull is the retry).

2. **HTTP-200 error payloads.** Binance returns HTTP 200 with a JSON object
   ``{"code":...,"msg":...}`` on bad params / soft rate-limits instead of
   the expected list. Paginators that treated "not a list" as end-of-data
   silently truncated backfills with health left green.
"""
from __future__ import annotations

from typing import Any

import httpx


def binance_should_retry(exc: BaseException) -> bool:
    """tenacity ``retry_if_exception`` predicate — see module docstring."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return isinstance(exc, (httpx.TransportError, httpx.TimeoutException))


def raise_on_error_payload(payload: Any, *, context: str) -> list[Any]:
    """Binance list endpoints: a dict body is an in-band error, not data.

    Surface it loud rather than letting a paginator read it as a clean
    end-of-data (the bug that silently truncated funding/OI backfills
    mid-window while the source health stayed green).
    """
    if isinstance(payload, dict):
        raise httpx.HTTPError(f"Binance {context} error payload: {payload}")
    if not isinstance(payload, list):
        raise httpx.HTTPError(
            f"Binance {context} unexpected payload type "
            f"{type(payload).__name__}: {str(payload)[:300]}"
        )
    return payload
