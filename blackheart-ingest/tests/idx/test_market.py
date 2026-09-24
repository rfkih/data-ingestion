"""The market overview: real figures, and flags on the ones that are not exact (needs DB)."""
from __future__ import annotations

import os

import psycopg
import pytest
from psycopg.rows import dict_row

from blackheart_ingest.idx import market


@pytest.fixture
def db():
    dsn = os.environ.get("INGEST_DB_DSN")
    if not dsn:
        pytest.skip("INGEST_DB_DSN not set")
    try:
        conn = psycopg.connect(dsn, connect_timeout=5, row_factory=dict_row)
    except Exception as e:
        pytest.skip(f"db unreachable: {e}")
    yield conn
    conn.close()


def _day(db):
    d = market.latest_day(db)
    if d is None:
        pytest.skip("no day summary in this database")
    return d


def test_breadth_adds_up_to_the_names_that_traded(db) -> None:
    b = market.breadth(db, _day(db))
    assert b["up"] + b["down"] + b["flat"] + b["unknown"] == b["listed"]
    assert b["listed"] > 0


def test_foreign_value_is_flagged_as_an_estimate(db) -> None:
    """IDX publishes the two legs in shares. The rupiah figure is those shares at the close, and a screen
    that prints it without saying so is stating a number the exchange never published."""
    f = market.foreign(db, _day(db))
    assert f["value_is_estimated"] is True and "shares" in f["why"]
    assert f["series"], "expected at least one session"
    assert [x["date"] for x in f["series"]] == sorted(x["date"] for x in f["series"])


def test_sectors_report_one_taxonomy_and_own_up_to_the_rest(db) -> None:
    """idx.listing carries IDX-IC sectors, a residue of the old JASICA scheme, and a lot of nulls. Only the
    first is reported; the others are counted so the screen can say what is missing."""
    s = market.sectors(db, _day(db))
    assert 0 < len(s["rows"]) <= 11, "IDX-IC has eleven sectors"
    assert all(not r["sector"][:2].rstrip().endswith(".") for r in s["rows"]), "the ordering key is not part of the name"
    assert s["covered"] + s["unclassified"] == s["listed"]


def test_movers_keep_out_the_name_that_printed_once(db) -> None:
    m = market.movers(db, _day(db))
    assert m["gainers"] and m["losers"]
    assert all(x["value"] >= m["min_value"] for x in m["gainers"] + m["losers"])
    gains = [x["chg_pct"] for x in m["gainers"]]
    assert gains == sorted(gains, reverse=True)
    assert [x["chg_pct"] for x in m["losers"]] == sorted(x["chg_pct"] for x in m["losers"])


def test_world_changes_against_the_series_own_previous_observation(db) -> None:
    """These series publish at different cadences - a monthly one has no yesterday to compare with."""
    w = market.world(db)
    assert w, "expected some macro series"
    assert all(x["value"] is not None and x["at"] for x in w)
