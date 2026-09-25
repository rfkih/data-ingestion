"""agent: the paper fill walk, the tick-grid brackets, the posterior fit, the choice rule, the decision minutes."""
from __future__ import annotations

from datetime import date, datetime

import numpy as np
import pandas as pd

from blackheart_ingest.idx import agent as ag
from blackheart_ingest.idx.ml.common import WIB

NAN = float("nan")


def test_brackets_sit_on_the_tick_grid_and_never_better_than_asked():
    tp, sl = ag.tp_sl_prices(1000.0, 0.01, 0.01)                   # tick 5 at 1000
    assert tp == 1010.0 and sl == 990.0
    tp, sl = ag.tp_sl_prices(123.0, 0.01, 0.01)                    # tick 1: 124.23 -> 125, 121.77 -> 121
    assert tp == 125.0 and sl == 121.0


def test_outcome_take_profit_stop_and_close():
    hi = np.array([1002.0, 1011.0, 1020.0])
    lo = np.array([998.0, 1000.0, 1005.0])
    assert ag.outcome(1000.0, 0.01, 0.01, hi, lo, 1015.0, 1015.0) == (1010.0, "tp", 2)
    lo2 = np.array([998.0, 989.0, 1005.0])
    ex, why, k = ag.outcome(1000.0, 0.01, 0.01, np.array([1002.0, 1012.0, 1020.0]), lo2, 1015.0, 1015.0)
    assert why == "sl" and ex == 985.0 and k == 2                  # a minute touching both counts as the stop, one tick below
    flat = np.array([1002.0, 1011.0, 1015.0])
    assert ag.outcome(1000.0, 0.02, 0.02, flat, lo, 1004.0, 1005.0) == (1004.0, "time", 3)
    assert ag.outcome(1000.0, 0.02, 0.02, flat, lo, NAN, 1005.0)[0] == 1000.0   # no bid: the close less one tick


def test_outcome_gap_through_the_stop_sells_at_the_open():
    # held overnight: the next morning opens at 950, far under the 970 stop -> sold at 950, not at the stop
    opens = np.array([1001.0, 950.0])
    hi, lo = np.array([1005.0, 960.0]), np.array([998.0, 940.0])
    assert ag.outcome(1000.0, 0.03, 0.03, hi, lo, 955.0, 955.0, opens) == (950.0, "sl", 2)


def test_horizon_end_counts_sessions_and_says_if_it_has_happened():
    s = [date(2026, 9, 22), date(2026, 9, 23), date(2026, 9, 24), date(2026, 9, 25)]
    assert ag.horizon_end(s, date(2026, 9, 23), 0) == (date(2026, 9, 23), True)
    assert ag.horizon_end(s, date(2026, 9, 23), 2) == (date(2026, 9, 25), True)
    assert ag.horizon_end(s, date(2026, 9, 24), 5) == (date(2026, 9, 25), False)   # not matured: known up to the last session


def test_reward_pays_both_fees():
    assert abs(ag.reward(1000.0, 1000.0) - (0.998 / 1.001 - 1)) < 1e-12


def test_fit_learns_a_signal_and_choose_takes_positive_only():
    rng = np.random.default_rng(0)
    n = 3000
    X = pd.DataFrame(rng.normal(size=(n, len(ag.FEATS))), columns=ag.FEATS)
    rows = []
    for a in ag.ACTIONS:
        y = 0.01 * X["obi"] - 0.005 + rng.normal(0, 0.002, n)          # same signal for every action
        rows.append(X.assign(action=a, reward=y))
    model = ag.fit(pd.concat(rows, ignore_index=True))
    obi = ag.FEATS.index("obi") + 1
    assert all(p["mu"][obi] > 0 for p in model["actions"].values())
    F = pd.DataFrame(np.zeros((3, len(ag.FEATS))), columns=ag.FEATS)
    F["obi"] = [3.0, 0.0, -3.0]                                    # drawn reward ~ +2.5 % / -0.5 % / -3.5 %
    sc = ag.scores(model, F, np.random.default_rng(1))
    picks = ag.choose(["A", "B", "C"], sc, set(), 10)
    assert [c for c, _, _ in picks] == ["A"]                         # only the name with a positive expected reward
    assert ag.choose(["A", "B", "C"], sc, {"A"}, 10) == []            # already taken today
    assert ag.choose(["A", "B", "C"], sc, set(), 0) == []             # no room left
    tiny = {a: np.array([ag.MIN_EDGE / 2, -1.0, -1.0]) for a in sc}
    assert ag.choose(["A", "B", "C"], tiny, set(), 10) == []          # positive but under the +0.3 % bar


def test_decision_minutes_and_window():
    assert [m.strftime("%H:%M") for m in ag.decision_minutes(date(2026, 9, 28))] == ["09:15", "10:00", "11:00", "13:45", "14:30"]
    assert [m.strftime("%H:%M") for m in ag.decision_minutes(date(2026, 10, 2))][-2:] == ["14:15", "14:45"]   # Friday
    assert ag.decision_minutes(date(2026, 9, 27)) == []
    assert ag.in_decision_window(datetime(2026, 9, 28, 10, 1, tzinfo=WIB)).strftime("%H:%M") == "10:00"
    assert ag.in_decision_window(datetime(2026, 9, 28, 10, 5, tzinfo=WIB)) is None


def test_fit_needs_sessions_and_inflates_for_same_day_samples():
    rng = np.random.default_rng(3)
    n_days, m = 4, 300
    rows = []
    for k in range(n_days):
        X = pd.DataFrame(rng.normal(size=(m, len(ag.FEATS))), columns=ag.FEATS)
        day_shock = rng.normal(0, 0.02)                                 # every name of a session shares its market move
        for a in ag.ACTIONS:
            rows.append(X.assign(action=a, reward=day_shock + rng.normal(0, 0.01, m), d=date(2026, 9, 21 + k)))
    S = pd.concat(rows, ignore_index=True)
    assert ag.fit(S[S["d"] < date(2026, 9, 23)])["actions"] == {}      # two sessions: not tradeable yet
    p = ag.fit(S)["actions"]["TP1"]
    assert p["sessions"] == 4 and p["design_effect"] > 10                 # 1,200 rows, but ~4 days of evidence
