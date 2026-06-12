"""``/readyz`` must signal degradation via the HTTP STATUS CODE.

The CI deploy gate (``curl -fsS .../readyz``) and the compose
healthcheck branch on the status code only — a degraded body behind a
200 passes the gate, skips rollback, and tags a broken deploy healthy.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from blackheart_inference.main import create_app
from blackheart_inference.settings import Settings


class _FakeDb:
    def __init__(self, ok: bool) -> None:
        self._ok = ok

    async def health_probe(self) -> bool:
        return self._ok


def _client(settings: Settings, *, db_ok: bool) -> TestClient:
    app = create_app(settings)
    # No lifespan in unit tests — wire the state the probe reads directly.
    app.state.settings = settings
    app.state.db = _FakeDb(db_ok)
    return TestClient(app, raise_server_exceptions=False)


def test_readyz_200_when_healthy(settings: Settings) -> None:
    c = _client(settings, db_ok=True)
    r = c.get("/readyz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "db": True, "artifact_dir": True}


def test_readyz_503_when_db_down(settings: Settings) -> None:
    c = _client(settings, db_ok=False)
    r = c.get("/readyz")
    assert r.status_code == 503
    assert r.json()["status"] == "degraded"
    assert r.json()["db"] is False


def test_readyz_503_when_artifact_dir_missing(settings: Settings, tmp_path: Path) -> None:
    settings = settings.model_copy(update={"artifact_dir": tmp_path / "nope"})
    c = _client(settings, db_ok=True)
    r = c.get("/readyz")
    assert r.status_code == 503
    assert r.json()["artifact_dir"] is False


def test_readyz_stays_public(settings: Settings) -> None:
    """No token required — it's the deploy/compose probe."""
    c = _client(settings, db_ok=True)
    r = c.get("/readyz")
    assert r.status_code != 401
