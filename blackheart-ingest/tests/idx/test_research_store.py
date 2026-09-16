"""research_store — a study run and its evidence round-trip through the DB (migration 0020); skipped without a DSN."""
from __future__ import annotations

import os
from datetime import UTC, date, datetime

import pytest

from blackheart_ingest.idx import research_store as rs

pytestmark = pytest.mark.skipif(not os.environ.get("INGEST_DB_DSN"), reason="needs INGEST_DB_DSN")


@pytest.fixture
def conn():
    from blackheart_ingest.shared.db import get_connection
    with get_connection() as c:
        yield c
        with c.cursor() as cur:
            cur.execute("DELETE FROM idx.evidence WHERE code = 'TEST'")
            cur.execute("DELETE FROM idx.study WHERE name = 'test_round_trip'")
        c.commit()


def test_jsonable_handles_decimals_numpy_and_nan():
    from decimal import Decimal

    import numpy as np
    out = rs._jsonable({"a": Decimal("1.5"), "b": np.bool_(True), "c": np.float64("nan"), "d": [np.int64(3), date(2026, 9, 17)]})
    assert out == {"a": 1.5, "b": True, "c": None, "d": [3, "2026-09-17"]}


def test_study_and_evidence_round_trip(conn):
    sid = rs.record_study(conn, "test_round_trip", date(2026, 9, 16), params={"trials": 1}, summary={"base": 0.17},
                          names=[{"code": "test", "screens": ["D"], "score": 0.5, "rank": 1, "features": {"ep": 0.1}, "context": {}}],
                          report_path="x.md")
    st = rs.study(conn, None, "test_round_trip")
    assert st["id"] == sid and st["names"][0]["code"] == "TEST" and st["names"][0]["features"]["ep"] == 0.1
    assert rs.studies(conn, "test_round_trip")[0]["names"] == 1
    assert rs.add_evidence(conn, "TEST", "web", "Title", ts=datetime.now(UTC), url="https://x", tags=["operational"], study_id=sid)
    assert not rs.add_evidence(conn, "TEST", "web", "Title", url="https://x")          # same (code, kind, url, title): deduplicated
    with pytest.raises(ValueError):
        rs.add_evidence(conn, "TEST", "rumour", "x")
    view = rs.name_view(conn, "test")
    assert view["studies"][0]["name"] == "test_round_trip" and view["evidence"]["web"][0]["url"] == "https://x"
    assert "TEST" in rs.render_name(view)
