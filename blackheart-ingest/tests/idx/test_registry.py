"""The desk registry: the static half is self-consistent, and the record half only ever comes from a stored study."""
from __future__ import annotations

import os

import psycopg
import pytest

from blackheart_ingest.idx import registry as R

# a roi_scorecard summary in every shape the real study uses: a plain number, a dict of variants, a dash for "no book"
SUMMARY = {
    "ranked": [
        {"key": "trend_small", "rank": 3, "label": "trend small", "cagr_pct": 29.5, "sharpe": 1.31, "mdd_pct": -30,
         "window": "2020-26", "status": "ROBUST; fails money rule on drawdown", "sources": [23, 62], "live": "-"},
        {"key": "gapfade_deployed", "rank": 1, "label": "gap fade", "cagr_pct": {"full_span_2021_26": 26, "recent": 57},
         "sharpe": {"77": 3.86, "89": 5.71}, "mdd_pct": {"77": -4, "89": -8.3}, "window": "2020-09..2026-09",
         "status": "BOUNDARY", "caveat": "denominator unverified", "sources": [77, 89, "menu 29"],
         "live": {"book": "paper_gapfade", "capital": 100000000}},
    ],
    "overlays": {
        "regime_gate": {"effect": "mDD -30% -> -18%", "status": "PARTIAL", "sources": [62, 63]},
        "ara_sell": {"effect": "holding through ARA costs -227 bps", "verdict": "SELL AT ARA (H0)", "source": 101,
                     "years_consistent": "7/7"},
    },
    "closed": ["swing 2-5d (46)", "bandarmologi (19)"],
}


def test_static_registry_is_consistent() -> None:
    keys = [e["key"] for e in R.REGISTRY]
    assert len(keys) == len(set(keys)) and len(keys) >= 10
    for e in R.REGISTRY:
        where = f"entry {e['key']}"
        assert e["family"] in R.FAMILIES, where
        assert e["status"] in R.STATUSES, where
        assert e["cadence"] in R.CADENCES, where
        assert e["rule"] and e["note"] and e["runs_in"], where
        assert all(isinstance(i, int) for i in e["evidence"]), where
        if e["status"] != "reference":                       # a yardstick needs no falsifier; a strategy the desk runs does
            assert e["falsifier"], where
        if e.get("roi") is not None:
            block, name = e["roi"]
            assert block in ("ranked", "overlays") and name, where
        if e.get("books"):
            assert set(e["books"]) <= {"rule", "strategy", "trend_variant", "flag"}, where
    assert R.BY_KEY["value_strict"]["status"] == "live"      # the only one with real fills


def test_scorecard_is_read_out_of_the_study_in_every_shape() -> None:
    by = {e["key"]: e for e in R.REGISTRY}
    sc = R.scorecard_from_study(SUMMARY, by["trend_small"])
    assert (sc["cagr_pct"], sc["sharpe"], sc["mdd_pct"], sc["roi_rank"]) == (29.5, 1.31, -30.0, 3)
    assert sc["live"] is None and sc["sources"] == [23, 62]           # "-" is not a book; the string source is dropped
    gf = R.scorecard_from_study(SUMMARY, by["gapfade"])
    assert gf["cagr_pct"] == 26.0 and gf["sharpe"] == 5.71 and gf["mdd_pct"] == -8.3   # the deployed variant, not the first
    assert gf["live"] == "paper_gapfade" and gf["caveat"] and gf["sources"] == [77, 89]
    ov = R.scorecard_from_study(SUMMARY, by["regime_gate"])
    assert ov["effect"].startswith("mDD") and ov["verdict"] == "PARTIAL" and ov["sources"] == [62, 63]
    ara = R.scorecard_from_study(SUMMARY, by["ara_sell"])
    assert ara["verdict"] == "SELL AT ARA (H0)" and ara["sources"] == [101] and ara["years_consistent"] == "7/7"
    # a strategy the study says nothing about, and one that claims no record at all, both stay empty
    assert R.scorecard_from_study({"ranked": [], "overlays": {}}, by["trend_small"]) is None
    assert R.scorecard_from_study(SUMMARY, by["exec_timing"]) is None


def test_live_book_shapes() -> None:
    assert R._live_book({"book": "trend_live"}) == "trend_live"
    assert R._live_book("live") == "live"
    assert R._live_book("-") is None and R._live_book(None) is None and R._live_book(" ") is None


def test_book_filter_never_matches_everything() -> None:
    assert R._book_filter_sql(None) == ("", [])
    assert R._book_filter_sql({}) == ("false", [])                     # an empty filter matches no book, not all books
    sql, params = R._book_filter_sql({"rule": "trend", "trend_variant": "small"})
    assert sql == "b.rule = %s AND b.trend_variant = %s" and params == ["trend", "small"]
    assert R._book_filter_sql({"flag": "regime_filter"}) == ("b.regime_filter", [])


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


def test_refresh_import_and_read_round_trip(conn) -> None:
    if R.latest_scorecard(conn) is None:
        pytest.skip("no roi_scorecard study stored")
    res = R.refresh_scorecard(conn)
    assert res["written"] == len(R.REGISTRY) and res["with_record"] >= 8 and res["study"]
    again = R.refresh_scorecard(conn)                                   # idempotent: same counts, no duplicate rows
    assert again["written"] == res["written"] and again["with_record"] == res["with_record"]

    d = R.desk(conn)
    assert len(d["strategies"]) == len(R.REGISTRY)
    by = {e["key"]: e for e in d["strategies"]}
    assert by["value_strict"]["has_record"] and by["value_strict"]["scorecard"]["cagr_pct"] > 0
    assert by["exec_timing"]["has_record"] is False and by["exec_timing"]["scorecard"] is None   # no study, no figure
    assert all(e["refreshed_at"] for e in d["strategies"])
    assert d["closed"]["families"] and d["scorecard_study"]
    # books resolve live from idx.book, archived ones excluded
    assert all(not b["archived"] for e in d["strategies"] for b in e["books"])
    assert {b["book"] for b in by["trend_small"]["books"]} <= {"paper_trend", "trend_live"}

    det = R.detail(conn, "trend_small")
    assert det["studies"] and [s["id"] for s in det["studies"]] == sorted(det["evidence"])
    assert all(s.get("name") for s in det["studies"])
    assert R.detail(conn, "value_strict").get("catalog_history")        # the annual families keep their per-size record
    assert R.detail(conn, "no_such_strategy") is None


def test_years_pointer_only_reads_paths_that_exist(conn) -> None:
    """A per-year row is read from the entry's own study by a declared path - or the entry simply has none."""
    assert R._dig({"a": {"b": [{"c": 1}]}}, ["a", "b", 0, "c"]) == 1
    assert R._dig({"a": 1}, ["a", "b"]) is None and R._dig([], [0]) is None and R._dig({}, ["x"]) is None
    for e in R.REGISTRY:                                    # every declared pointer resolves, or it should not be declared
        y = R.years_for(conn, e)
        if e.get("years"):
            assert y and y["years"], f"{e['key']} declares a years pointer that reads nothing"
            assert all(1990 < int(k) < 2100 for k in y["years"]), e["key"]
        else:
            assert y is None, e["key"]
    trend = R.years_for(conn, R.BY_KEY["trend_small"])
    assert trend["source"] == "study #23" and round(trend["years"]["2025"]) == 137     # percent, not a fraction
    assert R.years_for(conn, R.BY_KEY["value_strict"])["source"] == "research record"
