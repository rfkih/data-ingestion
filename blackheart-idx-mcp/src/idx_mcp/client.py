"""Thin HTTP client for the ingest IDX API (``/idx/*`` served by blackheart-ingest, local default ``:8001``).

Every tool in ``server.py`` goes through one ``IdxApi``; nothing here knows about the database. Mutation routes on
the ingest side are gated by ``X-Ingest-Token`` when ``INGEST_AUTH_TOKEN`` is set there — the same value is read
from the environment here and sent on every request (harmless on the open read routes). Every request also carries
``X-Idx-Actor: agent`` so the server applies the agent's guardrails (phase 1 of the agent-desk plan) regardless of
what the client-side ``guard`` lets through.
"""
from __future__ import annotations

import os
from typing import Any

import httpx

DEFAULT_URL = "http://127.0.0.1:8001"
ACTOR = "agent"          # X-Idx-Actor: the server's guardrails (two-key, operator-only settings/fills, turnover) key off it
# IDX_AGENT_USER (email): the desk is multi-user; the agent is scoped to this one account's books (X-Idx-User). Unset = every book.


class IdxApiError(Exception):
    """A non-2xx answer from the ingest API, carrying the server's ``detail`` so the agent sees the real reason
    (validation messages, ``no pack``, ``no ticket`` ...)."""

    def __init__(self, status: int, detail: str, path: str):
        super().__init__(f"{path} -> HTTP {status}: {detail}")
        self.status = status
        self.detail = detail
        self.path = path


class IdxApi:
    def __init__(self, base_url: str | None = None, token: str | None = None, timeout: float = 120.0,
                 transport: httpx.BaseTransport | None = None, user: str | None = None):
        self.base_url = (base_url or os.environ.get("IDX_API_URL") or DEFAULT_URL).rstrip("/")
        self.token = token if token is not None else os.environ.get("INGEST_AUTH_TOKEN", "")
        self.user = (user if user is not None else os.environ.get("IDX_AGENT_USER", "")).strip().lower()
        headers = {"X-Idx-Actor": ACTOR, **({"X-Ingest-Token": self.token} if self.token else {}),
                   **({"X-Idx-User": self.user} if self.user else {})}          # the one account whose desk the agent works
        self._client = httpx.Client(base_url=self.base_url, headers=headers, timeout=timeout, transport=transport)

    # -- verbs ------------------------------------------------------------------------------------------------------
    def get(self, path: str, **params: Any) -> Any:
        return self._request("GET", path, params=params)

    def post(self, path: str, json: Any = None, **params: Any) -> Any:
        return self._request("POST", path, params=params, json=json)

    def put(self, path: str, json: Any = None) -> Any:
        return self._request("PUT", path, json=json)

    def _request(self, method: str, path: str, params: dict[str, Any] | None = None, json: Any = None) -> Any:
        clean = {k: (str(v).lower() if isinstance(v, bool) else v) for k, v in (params or {}).items() if v is not None}
        try:
            r = self._client.request(method, "/idx" + path, params=clean, json=json)
        except httpx.HTTPError as e:
            hint = "start it: .venv/Scripts/python -m uvicorn blackheart_ingest.workers.server:app --port 8001"
            raise IdxApiError(0, f"ingest API unreachable at {self.base_url} ({e.__class__.__name__}: {e}) — {hint}", path) from None
        if r.status_code >= 400:
            detail: Any
            try:
                detail = r.json().get("detail", r.text)
            except ValueError:
                detail = r.text
            raise IdxApiError(r.status_code, str(detail), path)
        if r.headers.get("content-type", "").startswith("application/json"):
            return r.json()
        return r.text

    def close(self) -> None:
        self._client.close()
