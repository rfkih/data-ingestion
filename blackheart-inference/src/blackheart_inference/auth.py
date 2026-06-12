"""Shared-secret bearer auth — copy-shape from the orchestrator.

Public endpoints (``/healthz``, ``/readyz`` and the read-only
``/metrics/latency``) skip the check; everything else — including the
state-mutating ``POST /metrics/reset``, which wipes latency/SLO
tracking — requires ``X-Inference-Token``. ``X-Agent-Name`` is stamped
onto ``request.state.agent_name`` for forensic logging.
"""

from __future__ import annotations

import logging
import secrets
from typing import Awaitable, Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from .errors import ErrorEnvelope
from .settings import Settings

logger = logging.getLogger(__name__)

# NOTE: ``/metrics/reset`` is deliberately NOT public — it is a state-mutating
# POST that clears SLO/latency evidence, so it must carry ``X-Inference-Token``.
# Only read-only/liveness paths belong here.
_PUBLIC_PATHS: frozenset[str] = frozenset({"/healthz", "/readyz", "/metrics/latency"})


class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings: Settings) -> None:
        super().__init__(app)
        self._settings = settings

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        path = request.url.path
        request.state.agent_name = request.headers.get("X-Agent-Name", "anonymous")
        request.state.idempotency_key = request.headers.get("Idempotency-Key")

        if path in _PUBLIC_PATHS:
            return await call_next(request)

        token = request.headers.get("X-Inference-Token")
        if not token:
            return _envelope(401, "auth_missing_token",
                             "X-Inference-Token header is required.")
        expected = self._settings.auth_token.get_secret_value()
        # compare_digest on bytes: constant-time, and byte-encoding avoids
        # its non-ASCII str TypeError.
        if not secrets.compare_digest(token.encode("utf-8"), expected.encode("utf-8")):
            logger.warning("auth_bad_token | path=%s agent=%s",
                           path, request.state.agent_name)
            return _envelope(401, "auth_bad_token",
                             "X-Inference-Token did not match the configured secret.")
        return await call_next(request)


def _envelope(status_code: int, error_code: str, message: str) -> Response:
    from starlette.responses import JSONResponse
    return JSONResponse(
        status_code=status_code,
        content=ErrorEnvelope(
            error_code=error_code, message=message, retryable=False,
        ).model_dump(exclude_none=True),
    )
