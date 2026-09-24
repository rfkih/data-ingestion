"""ARA watch (menus 16 / ML-3 / 34): the limit price, the bar features that feed the model, the intraday state machine, the
list a holder gets, and the wording it uses."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pandas as pd
import psycopg
import pytest

from blackheart_ingest.idx import ara

ROOT = Path(__file__).resolve().parents[3]


# ---- the limit ---------------------------------------------------------------------------------------------------------
def test_ara_price_uses_the_band_of_the_previous_close_and_the_tick_of_the_limit_price() -> None:
    assert ara.ara_price(100) == 135                    # +35 % under Rp 200, Rp 1 tick
    assert ara.ara_price(190) == 256                    # 256.5 rounded DOWN on the Rp 2 tick it lands on
    assert ara.ara_price(1000) == 1250                  # +25 %, Rp 5 tick
    assert ara.ara_price(4000) == 5000                  # +25 % lands exactly on the Rp 25 tick
    assert ara.ara_price(4900) == 6125                  # 6,125 on the Rp 25 tick
    assert ara.ara_price(6000) == 7200                  # +20 % above Rp 5,000
    assert ara.limit_of(200) == 0.35 and ara.limit_of(201) == 0.25 and ara.limit_of(5000) == 0.25 and ara.limit_of(5001) == 0.20


# ---- features ------------------------------------------------------------------------------------------------------------
def _tape() -> pd.DataFrame:
    days = pd.bdate_range("2026-08-03", periods=30)
    rows = []
    close = 1000.0
    for i, d in enumerate(days):
        # a name that touches on day 10 (faded), locks on days 20 and 21, and is quiet otherwise
        if i == 10:
            high, close_new = ara.ara_price(close), close * 1.10
        elif i in (20, 21):
            high = close_new = ara.ara_price(close)
        else:
            high, close_new = close * 1.01, close * 1.002
        rows.append({"code": "AAA", "d": d, "high": high, "low": min(close, close_new) * 0.99, "close": close_new, "volume": 1e6 * (3 if i in (10, 20, 21) else 1), "value": 2e9})
        close = close_new
    for d in days:                                                       # a name that never gets near the limit
        rows.append({"code": "BBB", "d": d, "high": 505, "low": 495, "close": 500, "volume": 1e6, "value": 2e9})
    return pd.DataFrame(rows)


def test_features_mark_touch_lock_streak_and_days_since_touch() -> None:
    F = ara.features(_tape()).set_index(["code", "d"])
    a = F.loc["AAA"].reset_index()
    assert bool(a.loc[10, "touch"]) and not bool(a.loc[10, "lock"])          # touched and faded
    assert bool(a.loc[20, "lock"]) and bool(a.loc[21, "lock"])
    assert a.loc[20, "streak"] == 1 and a.loc[21, "streak"] == 2 and a.loc[22, "streak"] == 0
    assert a.loc[11, "days_since_touch"] == 1 and a.loc[19, "days_since_touch"] == 9 and a.loc[20, "days_since_touch"] == 0
    assert a.loc[9, "touch_next"] == 1.0 and a.loc[19, "touch_next"] == 1.0 and a.loc[11, "touch_next"] == 0.0
    assert a.loc[21, "lock_yday"] == 1.0 and a.loc[22, "touch_yday"] == 1.0
    assert a.loc[10, "vol_ratio"] > 2.0
    b = F.loc["BBB"]
    assert not b["touch"].any() and (b["days_since_touch"] == 60).all()
    assert set(ara.FEATS) <= set(F.columns)


# ---- the intraday state -----------------------------------------------------------------------------------------------
def test_classify_locked_queued_faded_and_not_touched() -> None:
    ara_px = 1250.0
    assert ara.classify(1200, 1200, ara_px, 1205, 100) is None                 # never reached the limit
    assert ara.classify(1250, 1250, ara_px, None, None) == "locked"            # at the limit, no offer
    assert ara.classify(1250, 1250, ara_px, 0, 0) == "locked"
    assert ara.classify(1250, 1250, ara_px, 1250, 5000) == "at_ara"            # sellers still queued at the limit
    assert ara.classify(1250, 1245, ara_px, 1250, 5000) == "faded"             # touched, trading under it now
    assert ara.classify(1250, None, ara_px, 1250, 5000) == "faded"
    assert ara.classify(None, 1250, ara_px, None, None) is None


# ---- the list ---------------------------------------------------------------------------------------------------------------
def _scored() -> pd.DataFrame:
    rows = []
    for i, code in enumerate(["AAA", "BBB", "CCC", "DDD"]):
        r = {"code": code, "p": 0.4 - 0.1 * i, "close": 1000.0 + i, "ara_next": ara.ara_price(1000.0 + i)}
        r.update({k: float(i) for k in ara.FEATS})
        rows.append(r)
    return pd.DataFrame(rows)


def test_select_rows_top_n_then_every_held_name() -> None:
    rows = ara.select_rows(_scored(), {"BBB": ["trend_live"], "DDD": ["live", "paper"]}, top=2)
    assert [r["code"] for r in rows] == ["AAA", "BBB", "DDD"]
    assert rows[0]["rank"] == 1 and not rows[0]["held"]
    assert rows[1]["rank"] == 2 and rows[1]["held"] and rows[1]["books"] == ["trend_live"]
    assert rows[2]["rank"] is None and rows[2]["held"] and rows[2]["p"] == pytest.approx(0.1)
    assert rows[2]["ara_px"] == ara.ara_price(1003.0) and set(rows[0]["features"]) == set(ara.FEATS)


def test_watch_and_touch_texts_carry_the_facts_and_no_directive_words() -> None:
    rows = ara.select_rows(_scored(), {"DDD": ["live"]}, top=2)
    text = ara.render_watch(rows, pd.Timestamp("2026-09-23").date(), 0.006)
    assert "AAA" in text and "DDD" in text and "studi #101" in text and "Bukan tiket" in text
    spec = importlib.util.spec_from_file_location("lint_words", ROOT / "scripts" / "lint-words.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for t in (text, ara.FACT_LOCKED, ara.FACT_FADED, ara.FACT_AT_ARA, ara.render_touches([])):
        assert not mod.PATTERN.search(t), t
    assert "Belum ada" in ara.render_touches([])
    one = ara.render_touches([{"code": "AAA", "state": "locked", "ara_px": 1250, "last_price": 1250, "first_ts": None}])
    assert one.startswith("AAA: terkunci") and "1,250" in one


# ---- read-only against the desk's tables (skipped without a database) ------------------------------------------------------
@pytest.fixture(scope="module")
def conn():
    dsn = os.environ.get("INGEST_DB_DSN")
    if not dsn:
        pytest.skip("INGEST_DB_DSN not set")
    with psycopg.connect(dsn) as c:
        yield c


def test_tables_exist_and_reads_work(conn) -> None:
    lw = ara.latest_watch(conn)
    assert "rows" in lw
    rows = ara.touches_today(conn)
    assert isinstance(rows, list)
    codes, held = ara.watched_codes(conn)
    assert isinstance(codes, list) and isinstance(held, dict)
    assert ara.prev_closes(conn, pd.Timestamp("2026-09-23").date(), ["BBRI"]).get("BBRI", 0) > 0
