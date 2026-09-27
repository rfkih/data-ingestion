"""Shared fixtures for the idx tests."""
from __future__ import annotations

import time

import pytest


@pytest.fixture(autouse=True)
def _exchange_calendar_offline(monkeypatch):
    """Every session / window check reads the exchange calendar (idx/exchange_calendar.py). Tests run with an empty holiday set
    (Monday-Friday) and never reach for the database; a test that needs holidays sets its own."""
    from blackheart_ingest.idx import exchange_calendar as xc
    monkeypatch.setitem(xc._cache, "days", set())
    monkeypatch.setitem(xc._cache, "at", time.monotonic())
