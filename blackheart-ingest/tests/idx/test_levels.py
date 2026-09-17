"""levels — stop / take-profit / warn levels fire once at the close that crosses them; round trip needs a DSN."""
from __future__ import annotations

import os
from decimal import Decimal

import pytest

from blackheart_ingest.idx import levels

pytestmark_db = pytest.mark.skipif(not os.environ.get("INGEST_DB_DSN"), reason="needs INGEST_DB_DSN")


def test_evaluate_directions():
    assert levels.evaluate({"kind": "stop", "level": Decimal(100)}, Decimal(100))
    assert levels.evaluate({"kind": "stop", "level": Decimal(100)}, Decimal(99))
    assert not levels.evaluate({"kind": "stop", "level": Decimal(100)}, Decimal(101))
    assert levels.evaluate({"kind": "warn", "level": Decimal(100)}, Decimal(90))
    assert levels.evaluate({"kind": "take_profit", "level": Decimal(200)}, Decimal(200))
    assert not levels.evaluate({"kind": "take_profit", "level": Decimal(200)}, Decimal(199))


@pytestmark_db
def test_round_trip_fires_once(monkeypatch):
    from blackheart_ingest.shared.db import get_connection
    fired: list[tuple[str, str]] = []
    monkeypatch.setattr(levels.runlog, "alert", lambda conn, sev, job, msg: fired.append((sev, msg)))
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO idx.book (book, cash) VALUES ('test_levels', 0) ON CONFLICT (book) DO NOTHING")
        conn.commit()
        try:
            with pytest.raises(ValueError):
                levels.set_level(conn, "test_levels", "SSIA", "trailing", 1)
            row = levels.set_level(conn, "test_levels", "ssia", "stop", "999999", "sell everything")   # far above any close: fires
            assert row["code"] == "SSIA" and row["active"]
            levels.set_level(conn, "test_levels", "SSIA", "take_profit", 10**9)                        # never fires
            levels.set_level(conn, "test_levels", "COMPOSITE", "warn", 10**7)                          # index code, fires
            r = levels.check(conn, "test_levels")
            assert r.status == "ok" and r.rows_in == 3 and r.rows_out == 2
            assert [s for s, _ in fired] == ["critical", "warning"] or sorted(s for s, _ in fired) == ["critical", "warning"]
            assert any("STOP LOSS SSIA" in m and "sell everything" in m for _, m in fired)
            r2 = levels.check(conn, "test_levels")                                                       # stamped: nothing fires again
            assert r2.rows_in == 1 and r2.rows_out == 0
            rows = levels.levels(conn, "test_levels")
            assert sum(1 for x in rows if x["triggered_at"]) == 2
            assert levels.reset(conn, "test_levels", "SSIA", "stop") == 1
            assert levels.check(conn, "test_levels").rows_out == 1                                       # re-armed: fires again
            assert "SSIA" in levels.render(rows, {"SSIA": (None, Decimal(1720))})
            assert levels.clear(conn, "test_levels", "SSIA") == 2 and levels.clear(conn, "test_levels", "COMPOSITE") == 1
        finally:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM idx.price_level WHERE book = 'test_levels'")
                cur.execute("DELETE FROM idx.book WHERE book = 'test_levels'")
            conn.commit()
