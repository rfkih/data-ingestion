"""Smoke tests for the SERVED application (workers/server.py).

H8 regression (CODE_REVIEW_INGEST_2026-06-12): CI used to exercise only the
dead ``api/app.py`` surface — the served app's routes, lifespan wiring and
auth could break while CI stayed green. These tests boot ``workers.server:app``
WITH its lifespan (``with TestClient(...)``) so a broken lifespan import or
route-table change fails loudly.

The background workers (kafka consumer / compute loop / liquidation stream)
are all default-OFF in settings, so the lifespan is side-effect-free here.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from blackheart_ingest.workers import server as server_mod
from blackheart_ingest.workers.server import app


def test_served_app_boots_with_lifespan_and_serves_routes():
    with TestClient(app) as client:
        # /healthz is the non-gating liveness/info surface.
        r = client.get("/healthz")
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert "bar_consumer" in body
        assert "compute_loop" in body

        # The mutation routes the platform actually calls must exist on
        # THIS app (the dead api/ app carried /compute/refresh, which no
        # deployed caller could ever reach).
        openapi = client.get("/openapi.json").json()
        paths = set(openapi["paths"])
        assert "/pull/{source}" in paths
        assert "/compute/incremental" in paths
        assert "/compute/{feature_name}/v/{version}" in paths
        assert "/compute/refresh" not in paths


def test_health_gates_on_db(monkeypatch):
    """/health is the Docker healthcheck + deploy rollback gate — it must
    actually probe the DB (the old static 200 made the gate meaningless)."""
    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(server_mod, "_db_probe", boom)
    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 503

    def ok():
        return True

    monkeypatch.setattr(server_mod, "_db_probe", ok)
    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["db"] is True


def test_mutation_routes_reject_bad_token_when_configured(monkeypatch):
    """C1 defense-in-depth: when INGEST_AUTH_TOKEN is set, mutation routes
    require X-Ingest-Token; reads stay open."""
    from pydantic import SecretStr

    settings = server_mod.get_settings()
    monkeypatch.setattr(settings, "auth_token", SecretStr("sekrit"))
    with TestClient(app) as client:
        r = client.post(
            "/compute/incremental", json={"lookback_hours": 1}
        )
        assert r.status_code == 401
        r = client.get("/sources")
        assert r.status_code == 200


def test_mutation_routes_open_when_token_unset(monkeypatch):
    """Empty token (default) keeps back-compat: the port binding is the
    primary boundary. The request still EXECUTES (it will fail later on a
    missing DB in this environment, but not with a 401)."""
    from pydantic import SecretStr

    settings = server_mod.get_settings()
    monkeypatch.setattr(settings, "auth_token", SecretStr(""))
    with TestClient(app) as client:
        r = client.post("/pull/not-a-real-source", json={
            "start": "2026-01-01T00:00:00",
            "end": "2026-01-02T00:00:00",
        })
        assert r.status_code == 404  # unknown source, NOT 401
