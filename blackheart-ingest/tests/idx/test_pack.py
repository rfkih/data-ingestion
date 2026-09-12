"""Analysis pack: answer validation (pure) and the build -> store -> import round trip (needs the local DB)."""
from __future__ import annotations

import json
import os
from datetime import date

import psycopg
import pytest

from blackheart_ingest.idx import pack

D = date(2026, 9, 11)
CODES = ["GJTL", "CTRA"]


def _ans(**over):
    a = {"pack_date": "2026-09-11", "prompt_version": pack.PROMPT_VERSION,
         "names": [{"code": "GJTL", "stance": "buy", "conviction": 4, "thesis": "cheap on TTM", "risks": "tyre demand", "veto": False, "veto_reason": None},
                   {"code": "CTRA", "stance": "avoid", "conviction": 3, "thesis": "revenue falling", "risks": "presales", "veto": True,
                    "veto_reason": "marketing sales down 12% with rising leverage"}],
         "notes": "property concentration"}
    a.update(over)
    return a


def test_validate_accepts_fenced_json_and_normalises() -> None:
    text = "```json\n" + json.dumps(_ans()) + "\n```"
    a = pack.validate_answer(text, CODES, D)
    assert [n["code"] for n in a["names"]] == CODES and a["missing"] == []
    assert a["names"][1]["veto"] and a["names"][1]["veto_reason"].startswith("marketing")
    assert pack.validate_answer(_ans(names=_ans()["names"][:1]), CODES, D)["missing"] == ["CTRA"]


@pytest.mark.parametrize("bad, msg", [
    ({"pack_date": "2026-09-10"}, "pack_date"),
    ({"names": [dict(_ans()["names"][0], code="ZZZZ")]}, "not in the pack"),
    ({"names": [dict(_ans()["names"][0], stance="strong buy")]}, "stance"),
    ({"names": [dict(_ans()["names"][0], conviction=7)]}, "conviction"),
    ({"names": [dict(_ans()["names"][1], veto_reason="")]}, "veto without veto_reason"),
    ({"names": [_ans()["names"][0], _ans()["names"][0]]}, "duplicate"),
    ({"names": [dict(_ans()["names"][0], thesis="")]}, "empty thesis"),
])
def test_validate_rejects(bad, msg) -> None:
    with pytest.raises(pack.AnswerError, match=msg):
        pack.validate_answer(_ans(**bad), CODES, D)


def test_validate_rejects_non_json() -> None:
    with pytest.raises(pack.AnswerError, match="not valid JSON"):
        pack.validate_answer("Sure! Here is my analysis...", CODES, D)


@pytest.fixture(scope="module")
def conn():
    dsn = os.environ.get("INGEST_DB_DSN")
    if not dsn:
        pytest.skip("INGEST_DB_DSN not set")
    try:
        c = psycopg.connect(dsn, connect_timeout=5)
    except Exception as e:
        pytest.skip(f"db unreachable: {e}")
    yield c
    c.close()


def test_round_trip(conn) -> None:
    p = pack.build(conn, date(2024, 6, 3), codes=CODES)          # a historical date so the live pack is untouched
    d = p["pack_date"]
    assert p["codes"] == CODES and "### GJTL" in p["md"] and "## Answer" in p["md"]
    assert p["json"]["names"][0]["code"] == "GJTL" and "ep" in p["json"]["names"][0]
    try:
        pack.store(conn, p)
        loaded = pack.load(conn, d)
        assert loaded and loaded["pack_json"]["codes"] == CODES and loaded["answer_json"] is None
        a = pack.import_answer(conn, d, _ans(pack_date=d.isoformat()))
        assert len(a["names"]) == 2
        rows = pack.answers(conn, "CTRA", 5)
        mine = [r for r in rows if r["pack_date"] == d.isoformat()]
        assert mine and mine[0]["veto"] == "skip" and mine[0]["stance"] == "avoid" and int(mine[0]["conviction"]) == 3
        assert pack.load(conn, d)["imported_at"] is not None
        with pytest.raises(pack.AnswerError):
            pack.import_answer(conn, d, _ans(pack_date="1999-01-01"))
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM idx.sentiment_score WHERE doc_type = 'pack' AND doc_id = %s", (d.isoformat(),))
            cur.execute("DELETE FROM idx.nightly_pack WHERE pack_date = %s", (d,))
        conn.commit()
