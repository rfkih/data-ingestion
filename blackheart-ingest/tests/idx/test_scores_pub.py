"""Factor scores, quality gates, signal statistics and the public /pub routes (open-research plan phase 2)."""
from __future__ import annotations

import os
from datetime import date

import psycopg
import pytest
from fastapi import HTTPException

from blackheart_ingest.idx import pub, quality, scores


def test_percentile_ranks_ties_and_none() -> None:
    p = scores._pct({"a": 1.0, "b": 2.0, "c": 2.0, "d": None, "e": 5.0})
    assert p["d"] is None and p["e"] == 100.0 and p["a"] == 25.0 and p["b"] == p["c"] == 62.5


def test_bucket_bands() -> None:
    assert scores.bucket_of(1e12, 0.2) == "mcap:<3T,mom:<=150"
    assert scores.bucket_of(8e12, 2.0) == "mcap:3-20T,mom:>150"
    assert scores.bucket_of(50e12, None) == "mcap:>20T,mom:?"
    assert scores.bucket_of(None, 1.0) is None


def _fy(y, np_, sh=1e9, eq=5e12, roe=0.18, cfo=None, capex=0.1e12, debt=0.2e12, cash=0.5e12, div=0.3e12):
    return {"fy": date(y, 12, 31), "np": np_, "rev": 10e12, "eq": eq, "debt": debt, "cash": cash, "cfo": cfo if cfo is not None else np_ * 1.1,
            "capex": capex, "div": div, "sh": sh, "roe": roe, "der": 0.1, "sector": "D. Consumer"}


def test_quality_gates_pass_for_a_steady_business() -> None:
    rows = [_fy(y, 1.0e12 * (1 + 0.1 * i)) for i, y in enumerate(range(2021, 2026))]
    ttm = {"net_profit_ttm": 1.45e12, "equity_latest": 5e12}
    res = quality.evaluate("STEADY", rows, ttm, close=10_000, sector="D. Consumer", split_list=[], dividend_recent=True)   # mcap 10 T, P/E 6.9
    assert res["passed"] == 8, res["gates"]
    assert res["metrics"]["pe_ttm"] == pytest.approx(10e12 / 1.45e12)
    table = quality.gate_table(res)
    assert len(table) == 8 and all(g["pass"] for g in table)


def test_quality_gates_fail_on_loss_year_dilution_and_price() -> None:
    rows = [_fy(2021, -0.2e12), *[_fy(y, 1.0e12, sh=1.3e9 if y == 2025 else 1e9) for y in range(2022, 2026)]]
    ttm = {"net_profit_ttm": 1.0e12, "equity_latest": 5e12}
    res = quality.evaluate("SHAKY", rows, ttm, close=30_000, sector="D. Consumer", split_list=[], dividend_recent=False)     # mcap 39 T, P/E 39
    g = res["gates"]
    assert not g["laba5"] and not g["dilusi_dividen"] and not g["harga"]
    assert res["metrics"]["loss_years"] == 1


def test_quality_needs_five_years() -> None:
    assert quality.evaluate("NEW", [_fy(2024, 1e12), _fy(2025, 1e12)], {}, 1000, None)["gates"] is None


def test_split_adjusted_shares_do_not_look_like_dilution() -> None:
    rows = [_fy(y, 1.0e12, sh=1e9 if y < 2024 else 5e9) for y in range(2021, 2026)]          # 1:5 split in 2024
    ttm = {"net_profit_ttm": 1.0e12, "equity_latest": 5e12}
    res = quality.evaluate("SPLIT", rows, ttm, close=2_000, sector=None, split_list=[(date(2024, 3, 1), 0.2)], dividend_recent=True)
    assert res["metrics"]["dilution"] == pytest.approx(0.0)
    assert res["gates"]["eps"]


def test_matches_and_criteria_text() -> None:
    row = {"value": 85.0, "trend_flag": True, "gates": 7, "inputs": {"mom_12_1": 0.4, "sector": "A. Energy", "gate_strict": True}}
    assert pub.matches(row, [{"field": "value", "op": "gte", "value": 80}, {"field": "trend_flag", "op": "eq", "value": True},
                             {"field": "mom_12_1", "op": "lte", "value": 1.5}, {"field": "sector", "op": "contains", "value": "energy"}])
    assert not pub.matches(row, [{"field": "gates", "op": "gte", "value": 8}])
    assert not pub.matches({"value": None, "inputs": {}}, [{"field": "value", "op": "gte", "value": 1}])
    with pytest.raises(HTTPException):
        pub.matches(row, [{"field": "nope", "op": "eq", "value": 1}])
    text = pub.criteria_text([{"field": "trend_flag", "op": "eq", "value": True}, {"field": "mom_12_1", "op": "lte", "value": 1.5}, {"field": "value", "op": "gte", "value": 80}])
    assert text[0].startswith("memenuhi rule breakout") and "+150 %" in text[1] and "≥ 80" in text[2]


@pytest.fixture(scope="module")
def db():
    dsn = os.environ.get("INGEST_DB_DSN")
    if not dsn:
        pytest.skip("INGEST_DB_DSN not set")
    try:
        conn = psycopg.connect(dsn, connect_timeout=5, row_factory=psycopg.rows.dict_row)
    except Exception as e:
        pytest.skip(f"db unreachable: {e}")
    yield conn
    conn.close()


def test_compute_scores_invariants(db) -> None:
    res = scores.compute(db)
    assert res["n"] > 50
    for r in res["rows"]:
        for k in ("value", "quality", "trend"):
            assert r[k] is None or 0 <= r[k] <= 100
        i = r["inputs"]
        if r["value"] is not None:
            assert i["ep"] is not None and i["ep"] > 0
        if r["trend_flag"]:
            assert i["close_hi60"] >= 1 and i["close_ma200"] > 1 and i["vol_ratio"] >= 1.5
        if r["gates"] is not None:
            assert 0 <= r["gates"] <= 8 and i["quality_years"] >= 5
        assert i["close"] >= 100


def test_pub_routes(db) -> None:
    from fastapi.testclient import TestClient

    from blackheart_ingest.workers.server import app
    with TestClient(app) as c:
        t = c.get("/pub/templates").json()
        assert [x["key"] for x in t] == ["value_strict", "trend_breakout", "quality8", "turnaround"]
        assert all(x["criteria_text"] for x in t)
        r = c.post("/pub/screener", json={"criteria": t[1]["criteria"], "sort": "trend", "template": "trend_breakout"})
        assert r.status_code == 200
        body = r.json()
        assert body["universe"] >= body["n"] and body["criteria_text"]
        assert all(x["trend_flag"] for x in body["rows"])
        assert c.post("/pub/screener", json={"criteria": [{"field": "nope", "op": "eq", "value": 1}]}).status_code == 400
        assert c.get("/pub/screener/fields").status_code == 200
        assert c.get("/pub/scores/ZZZZ").status_code == 404
        one = c.get("/pub/scores").json()
        if one["rows"]:
            code = one["rows"][0]["code"]
            page = c.get(f"/pub/scores/{code}").json()
            assert set(page) >= {"row", "history", "gates", "cards", "disclaimer"}
        assert c.get("/pub/research").status_code == 200
