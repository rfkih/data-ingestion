"""ARA watch (menus 16 / ML-3 / 34 / study #146): the limit price, the bar + closing-book features that feed the model,
the calibration, the intraday state machine, the list a holder gets, and the wording it uses."""
from __future__ import annotations

import importlib.util
import os
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg
import pytest

from blackheart_ingest.idx import ara, ara_model

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
    # the vectorised twin in the model agrees with the scalar rule
    prevs = np.array([100.0, 190.0, 1000.0, 4000.0, 4900.0, 6000.0])
    assert list(ara_model.ara_of(prevs)) == [ara.ara_price(p) for p in prevs]


# ---- features ------------------------------------------------------------------------------------------------------------
def _tape(with_book: bool = False) -> pd.DataFrame:
    days = pd.bdate_range("2026-06-01", periods=70)
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
        r = {"code": "AAA", "d": d, "high": high, "low": min(close, close_new) * 0.99, "close": close_new, "volume": 1e6 * (3 if i in (10, 20, 21) else 1), "value": 2e9}
        if with_book:
            locked = i in (20, 21)
            r.update({"bid": close_new, "bid_volume": 5e6 if locked else 1e5, "offer": None if locked else close_new + 5, "offer_volume": 0 if locked else 1e5,
                      "frequency": 500 * (4 if i in (10, 20, 21) else 1), "foreign_buy": 2e5, "foreign_sell": 1e5, "nonreg_volume": 0, "tradeable_shares": 1e9, "open": close})
        rows.append(r)
        close = close_new
    for d in days:                                                       # a name that never gets near the limit
        rows.append({"code": "BBB", "d": d, "high": 505, "low": 495, "close": 500, "volume": 1e6, "value": 2e9})
    return pd.DataFrame(rows)


def test_features_mark_touch_lock_streak_days_since_ara_and_the_labels() -> None:
    F = ara_model.features(_tape()).set_index(["code", "d"])
    a = F.loc["AAA"].reset_index()
    assert bool(a.loc[10, "touch"]) and not bool(a.loc[10, "lock"])          # touched and faded
    assert bool(a.loc[20, "lock"]) and bool(a.loc[21, "lock"])
    assert a.loc[20, "streak"] == 1 and a.loc[21, "streak"] == 2 and a.loc[22, "streak"] == 0
    assert a.loc[19, "days_since_ara"] == 60 and a.loc[20, "days_since_ara"] == 0 and a.loc[25, "days_since_ara"] == 4
    assert a.loc[19, "LOCK1"] == 1.0 and a.loc[20, "LOCK1"] == 1.0 and a.loc[21, "LOCK1"] == 0.0
    assert a.loc[9, "TOUCH1"] == 1.0 and a.loc[9, "LOCK1"] == 0.0 and a.loc[11, "TOUCH1"] == 0.0
    assert a.loc[10, "vr"] > 2.0 and a.loc[20, "n_ara20"] == 1 and a.loc[21, "n_ara20"] == 2
    assert a.loc[69, "ara_px_next"] == ara.ara_price(a.loc[69, "close"])
    assert np.isnan(a.loc[30, "qimb"]) and np.isnan(a.loc[30, "freq_ratio"])   # a bar-only tape has no book features
    b = F.loc["BBB"]
    assert not b["touch"].any() and (b["days_since_ara"] == 60).all()
    assert set(ara_model.FEATS) <= set(F.columns) and ara.FEATS == ara_model.FEATS


def test_closing_book_features_read_the_queue_and_the_tape() -> None:
    F = ara_model.features(_tape(with_book=True)).set_index(["code", "d"])
    a = F.loc["AAA"].reset_index()
    assert a.loc[20, "qimb"] == pytest.approx(1.0) and a.loc[20, "no_offer"] == 1.0          # locked: bid queue only
    assert a.loc[30, "qimb"] == pytest.approx(0.0) and a.loc[30, "no_offer"] == 0.0 and a.loc[30, "sprd_t"] == pytest.approx(1.0)
    assert a.loc[30, "close_at_bid"] == 1.0 and a.loc[30, "fnet"] == pytest.approx(0.1) and a.loc[30, "fpart"] == pytest.approx(0.15)
    assert a.loc[20, "freq_ratio"] == pytest.approx(4.0) and a.loc[30, "turnover"] == pytest.approx(1e-3)
    assert a.loc[20, "buyable"] == 0.0 and a.loc[30, "buyable"] == 1.0


# ---- calibration and confidence -------------------------------------------------------------------------------------------
def test_platt_is_monotone_and_pulls_inflated_scores_to_the_observed_rate() -> None:
    rng = np.random.default_rng(1)
    y = (rng.random(20000) < 0.01).astype(float)
    raw = 1 / (1 + np.exp(-(3 * y + rng.normal(0, 1.5, 20000) + 1.5)))       # right about the order, wrong about the level
    ab = ara_model.platt_fit(raw, y)
    cal = ara_model.platt_apply(raw, ab)
    assert abs(cal.mean() - y.mean()) < 0.003 and raw.mean() > 0.5                # level fixed, ...
    o = np.argsort(raw)
    assert (np.diff(cal[o]) >= -1e-12).all()                                       # ...order kept
    assert ara_model.confidence(0.25) == "high" and ara_model.confidence(0.05) == "medium" and ara_model.confidence(0.01) == "low"
    assert ara_model.confidence(float("nan")) == "low"


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
        r = {"code": code, "p_lock": 0.4 - 0.1 * i, "p_touch": 0.5 - 0.1 * i, "p_dl": 0.3 - 0.05 * i, "score": 1 - 0.1 * i, "close": 1000.0 + i,
             "ara_px_next": ara.ara_price(1000.0 + i), "locked_today": i == 0, "buyable": i != 0}
        r.update({k: float(i) for k in ara.FEATS})
        rows.append(r)
    return pd.DataFrame(rows)


def test_select_rows_keeps_every_score_and_marks_the_list() -> None:
    """Every scored name comes back ranked, so any of them can be looked up later; `listed` is the part the evening
    list and the push are built from - the top N plus anything a book holds."""
    rows = ara.select_rows(_scored(), {"BBB": ["trend_live"], "DDD": ["live", "paper"]}, top=2)
    assert [r["code"] for r in rows] == ["AAA", "BBB", "CCC", "DDD"]         # the whole ranking, in order
    assert [r["rank"] for r in rows] == [1, 2, 3, 4]
    assert [r["listed"] for r in rows] == [True, True, False, True]          # CCC scored but out of the list; DDD held
    assert rows[0]["rank"] == 1 and not rows[0]["held"] and rows[0]["locked_today"] and not rows[0]["buyable"]
    assert rows[0]["p"] == rows[0]["p_lock"] == pytest.approx(0.4) and rows[0]["confidence"] == "high" and rows[0]["p_touch"] == pytest.approx(0.5)
    assert rows[1]["rank"] == 2 and rows[1]["held"] and rows[1]["books"] == ["trend_live"] and rows[1]["confidence"] == "high"
    assert rows[3]["held"] and rows[3]["p"] == pytest.approx(0.1)
    assert rows[3]["confidence"] == "medium"                                 # 0.4 - 3 x 0.1 lands a hair under the 10 % band
    assert rows[3]["ara_px"] == ara.ara_price(1003.0) and set(rows[0]["features"]) == set(ara.FEATS)


def test_render_watch_shows_only_the_listed_part() -> None:
    """A scored name that missed the list must not appear in the evening text, however many are kept behind it."""
    rows = ara.select_rows(_scored(), {"DDD": ["live"]}, top=2)
    text = ara.render_watch(rows, date(2026, 9, 24), 0.0055)
    assert "AAA" in text and "BBB" in text and "DDD" in text
    assert "CCC" not in text


def test_watch_and_touch_texts_carry_the_facts_and_no_directive_words() -> None:
    rows = ara.select_rows(_scored(), {"DDD": ["live"]}, top=2)
    text = ara.render_watch(rows, pd.Timestamp("2026-09-23").date(), 0.006)
    assert "AAA" in text and "DDD" in text and "studi #101" in text and "studi #146" in text and "Bukan tiket" in text
    assert "P kunci 40 %" in text and "sentuh 50 %" in text and "keyakinan tinggi" in text and "sudah terkunci hari ini" in text
    spec = importlib.util.spec_from_file_location("lint_words", ROOT / "scripts" / "lint-words.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for t in (text, ara.FACT_LOCKED, ara.FACT_FADED, ara.FACT_AT_ARA, ara.FACT_MODEL, ara.render_touches([]), ara_model.FACTS["note"]):
        assert not mod.PATTERN.search(t), t
    assert "Belum ada" in ara.render_touches([])
    one = ara.render_touches([{"code": "AAA", "state": "locked", "ara_px": 1250, "last_price": 1250, "first_ts": None}])
    assert one.startswith("AAA: terkunci") and "1,250" in one


# ---- prediction vs actual -----------------------------------------------------------------------------------------------------
def test_outcome_reads_the_next_session_with_the_limit_from_idx_previous() -> None:
    lock = ara.outcome_of(1000, 1250, 1250, 5e5)
    assert lock["next_ara_px"] == 1250 and lock["locked"] and lock["touched"] and lock["outcome"] == "lock"
    assert lock["ret_close"] == pytest.approx(0.25) and lock["ret_high"] == pytest.approx(0.25)
    touch = ara.outcome_of(1000, 1250, 1180, 5e5)                               # reached the limit, closed under it
    assert touch["touched"] and not touch["locked"] and touch["outcome"] == "touch" and touch["ret_close"] == pytest.approx(0.18)
    none = ara.outcome_of(1000, 1100, 1040, 5e5)
    assert not none["touched"] and not none["locked"] and none["outcome"] == "none"
    idle = ara.outcome_of(1000, 0, 1000, 0)                                     # no trade that session: labels false, marked
    assert idle["outcome"] == "no_trade" and idle["locked"] is False and idle["ret_close"] == 0
    gone = ara.outcome_of(None, None, None, None)                               # no usable bar: no label at all
    assert gone["outcome"] == "no_trade" and gone["locked"] is None and gone["touched"] is None
    # a corporate action moves IDX's previous: the limit follows it, not the run day's stored ara_px
    assert ara.outcome_of(200, 270, 270, 1e6)["next_ara_px"] == 270 and ara.outcome_of(200, 270, 270, 1e6)["locked"]


def test_outcome_labels_are_the_models_training_labels() -> None:
    """The record grades the model by the labels it was trained on: LOCK1 / TOUCH1 of day t == outcome_of(next day)."""
    tape = _tape()
    F = ara_model.features(tape).set_index(["code", "d"])
    a = tape[tape["code"] == "AAA"].reset_index(drop=True)
    lab = F.loc["AAA"].reset_index()
    for t in range(len(a) - 1):
        o = ara.outcome_of(a.loc[t, "close"], a.loc[t + 1, "high"], a.loc[t + 1, "close"], a.loc[t + 1, "volume"])
        assert float(o["locked"]) == lab.loc[t, "LOCK1"], t
        assert float(o["touched"]) == lab.loc[t, "TOUCH1"], t


def _run_rows(n: int = 40, whole: bool = True) -> list[dict]:
    """A run of n ranked names: ranks 1, 3 and 12 lock, rank 2 touches only, rank 30 locks; the top 10 are listed."""
    rows = []
    for i in range(1, n + 1):
        locked = i in (1, 3, 12, 30)
        rows.append({"code": f"C{i:02d}", "rank": i, "listed": i <= 10, "p_lock": 0.30 - 0.007 * i, "score": 1 - i / n,
                     "buyable": i % 2 == 0, "locked": locked, "touched": locked or i == 2})
    return rows if whole else [r for r in rows if r["listed"]]


def test_score_run_counts_precision_recall_and_ranks_the_whole_list() -> None:
    sc = ara.score_run(_run_rows(), universe=800, universe_locks=8, universe_touches=12)
    assert (sc["top5_locks"], sc["top10_locks"], sc["top20_locks"]) == (2, 2, 3)
    assert (sc["top5_touches"], sc["top5_n"], sc["top20_n"]) == (3, 5, 20)
    assert sc["prec5"] == pytest.approx(0.4) and sc["prec10"] == pytest.approx(0.2) and sc["prec20"] == pytest.approx(0.15)
    assert sc["recall20"] == pytest.approx(3 / 8) and sc["base_rate"] == pytest.approx(8 / 800)
    assert sc["listed_locks"] == 2 and sc["listed_buyable"] == 5 and sc["listed_buyable_locks"] == 0   # ranks 1 and 3 had no offer
    assert sc["mean_p_top10"] == pytest.approx(np.mean([0.30 - 0.007 * i for i in range(1, 11)]))
    assert sc["whole_ranking"] and 0.5 < sc["auc_lock"] <= 1 and sc["brier_lock"] > 0


def test_score_run_on_a_list_only_run_has_no_auc_and_drops_names_without_a_bar() -> None:
    rows = _run_rows(whole=False)
    rows[0].update(locked=None, touched=None)                                   # rank 1 had no bar next session
    sc = ara.score_run(rows, universe=None, universe_locks=None, universe_touches=None)
    assert not sc["whole_ranking"] and sc["auc_lock"] is None and sc["brier_lock"] is None
    assert sc["top5_n"] == 4 and sc["top5_locks"] == 1 and sc["prec5"] == pytest.approx(0.25)
    assert sc["recall20"] is None and sc["base_rate"] is None


def test_record_texts_render_pending_and_settled_rows() -> None:
    base = {"run_date": date(2026, 9, 25), "bar_date": date(2026, 9, 25), "rank": 1, "p_lock": 0.21, "p_touch": 0.3, "buyable": False}
    settled = {**base, "code": "AAA", "next_date": date(2026, 9, 28), "outcome": "lock", "ret_close": 0.25, "ret_high": 0.25,
               "next_ara_px": 1250, "next_close": 1250}
    pending = {**base, "code": "BBB", "rank": 2, "next_date": None, "outcome": None, "ret_close": None, "ret_high": None,
               "next_ara_px": None, "next_close": None}
    text = ara.render_record({"run_date": date(2026, 9, 25), "rows": [settled, pending], "scorecard": {"top5_locks": 1}})
    assert "AAA" in text and "lock" in text and "+25.0%" in text and "BBB" in text and "belum" in text
    one = ara.render_record({"code": "AAA", "rows": [settled, pending]})
    assert one.startswith("AAA: prediksi ARA vs aktual (2 malam)")


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
    # the facts cite the run that currently stands for study #146 (re-run on corrected opens 2026-09-26 -> #237)
    with conn.cursor() as cur:
        cur.execute("SELECT current_id FROM idx.study_current WHERE id = 146")
        current = cur.fetchone()[0]
    assert "rows" in lw and lw["facts"]["study"] == current
    for r in lw["rows"]:
        assert r["p_lock"] is not None and r["confidence"] in ("high", "medium", "low")
    rows = ara.touches_today(conn)
    assert isinstance(rows, list)
    codes, held = ara.watched_codes(conn)
    assert isinstance(codes, list) and isinstance(held, dict)
    assert ara.prev_closes(conn, pd.Timestamp("2026-09-23").date(), ["BBRI"]).get("BBRI", 0) > 0


def test_record_and_scorecard_reads(conn) -> None:
    """Read-only: the prediction-vs-actual views answer whether or not anything has been settled yet."""
    rec = ara.record(conn)
    assert "rows" in rec and "scorecard" in rec
    for r in rec["rows"]:
        assert r["settled_at"] is not None and (r["outcome"] in ("lock", "touch", "none", "no_trade", "no_bar"))
    s = ara.scorecards(conn, 10)
    assert set(s) >= {"rows", "pooled", "pending_runs", "study"} and isinstance(ara.render_scorecards(s), str)
