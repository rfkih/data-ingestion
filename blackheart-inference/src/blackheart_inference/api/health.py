"""``/healthz`` (no I/O) and ``/readyz`` (DB probe)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .. import __version__

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict[str, Any]:
    return {"status": "ok", "version": __version__}


@router.get("/readyz")
async def readyz(request: Request) -> JSONResponse:
    """Readiness probe. Returns HTTP 503 when degraded — the CI deploy
    gate and the compose healthcheck both branch on the status CODE
    (``curl -f`` / urllib), so a degraded body behind a 200 would pass
    the gate, skip rollback, and tag a broken deploy as healthy."""
    db_ok = await request.app.state.db.health_probe()
    artifact_dir_exists = request.app.state.settings.artifact_dir.exists()
    ready = db_ok and artifact_dir_exists
    return JSONResponse(
        status_code=200 if ready else 503,
        content={
            "status": "ok" if ready else "degraded",
            "db": db_ok,
            "artifact_dir": artifact_dir_exists,
        },
    )
