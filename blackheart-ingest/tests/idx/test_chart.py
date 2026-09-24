"""The one-name screen: candles, the order book, and the trend rule's reading of a name (needs DB)."""
from __future__ import annotations

import os

import psycopg
import pytest
from psycopg.rows import dict_row

from blackheart_ingest.idx import chart, trend_book


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


def _a_name(db) -> str:
    with db.cursor() as cur:
        cur.execute("SELECT code FROM idx.bar WHERE source = 'idx' GROUP BY code HAVING count(*) > 250 ORDER BY code LIMIT 1")
        row = cur.fetchone()
    if not row:
        pytest.skip("no name with enough history in this database")
    return row["code"]


def test_daily_candles_are_oldest_first_and_adjusted(db) -> None:
    code = _a_name(db)
    rows = chart.daily(db, code, bars=40)
    assert 2 <= len(rows) <= 40
    assert [r["date"] for r in rows] == sorted(r["date"] for r in rows), "the chart draws left to right"
    for r in rows:
        assert r["low"] <= r["close"] <= r["high"] and r["low"] <= r["open"] <= r["high"]


def test_bars_are_capped_so_one_url_cannot_ask_for_the_whole_history(db) -> None:
    assert len(chart.daily(db, _a_name(db), bars=99_999)) <= chart.MAX_DAILY_BARS


def test_trend_state_reports_the_rule_not_a_forecast(db) -> None:
    """Every threshold must come from trend_book, so the screen cannot drift away from the book the desk follows."""
    st = chart.trend_state(db, _a_name(db))
    assert st["rule"]["high_window"] == trend_book.HI_N
    assert st["rule"]["average_window"] == trend_book.MA_N
    assert st["rule"]["volume_multiple"] == float(trend_book.VOL_X)
    assert st["rule"]["trail_pct"] == float(trend_book.TRAIL) * 100
    assert set(st["tests"]) == {"at_60d_high", "above_200d_avg", "volume_surge"}
    assert st["entry_today"] is all(t["ok"] for t in st["tests"].values())
    assert "not a price forecast" in st["means"]


def test_a_name_outside_the_tick_feed_is_not_an_error(db) -> None:
    """Most listed names have no minute bars and no book. The screen degrades to the daily panel; it does not fail."""
    d = chart.depth(db, "ZZZZ")
    assert d["levels"] == [] and d["imbalance"] is None and "not in the tick feed" in d["why"]
    assert chart.intraday(db, "ZZZZ") == []


def test_depth_reports_the_spread_next_to_the_imbalance(db) -> None:
    """The imbalance is only ever read against the spread it would have to cross - never on its own."""
    codes = chart.feed_codes(db)
    if not codes:
        pytest.skip("the tick feed has no subscribed names in this database")
    seen = [chart.depth(db, c) for c in codes[:12]]
    live = [d for d in seen if d["levels"]]
    if not live:
        pytest.skip("no order book captured yet")
    d = live[0]
    assert len(d["levels"]) <= 10
    if d["imbalance"] is not None:
        assert 0.0 <= d["imbalance"] <= 1.0
        assert "spread_bps" in d, "an imbalance without its spread is the reading research rejected"
    if d["best_bid"] and d["best_off"]:
        assert d["best_off"] > d["best_bid"], "the offer must sit above the bid"


def test_the_index_is_never_given_an_open_it_does_not_have(db) -> None:
    """IDX publishes previous/high/low/close for an index and no open. Filling it with the close would draw a candle
    asserting the day opened where it closed, which nobody said - so it stays null and the screen draws a line."""
    rows = chart.index_daily(db, bars=30)
    if not rows:
        pytest.skip("no index history in this database")
    assert all(r["close"] is not None for r in rows)
    assert all(r["open"] is None for r in rows), "an index open must not be invented from the close"


def test_index_view_carries_the_regime_gate_the_books_actually_use(db) -> None:
    v = chart.index_view(db, bars=30, minutes=10)
    if not v["daily"]:
        pytest.skip("no index history in this database")
    assert v["code"] == chart.INDEX_CODE and v["sma_days"] == 200
    if v["sma"] is not None and v["close"] is not None:
        assert v["regime_on"] is (v["close"] > v["sma"])
