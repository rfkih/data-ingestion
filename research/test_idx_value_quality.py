"""Synthetic checks for the portfolio simulator in idx_value_quality: costs, dividends net of tax, a name that cannot be
sold on the rebalance day (carried), a delisted name (worth zero), and the tick spread.
Run: blackheart-ingest/.venv/Scripts/python -m pytest research/test_idx_value_quality.py"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import idx_value_quality as VQ  # noqa: E402

DAYS = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"])
C = VQ.COST_SIDE


def _frame(rows):
    return pd.DataFrame(rows, index=DAYS, columns=["A", "B", "C"], dtype=float)


def _setup(c_sellable_on_rebalance: bool):
    # A: 100 -> 110 -> 120 -> 120 -> 130 (dividend 10 ex day 3); B: 200 flat, no trade on the rebalance day; C: 50, last bar day 2
    close = _frame([[100, 200, 50], [110, 200, 50], [120, 200, 50], [120, 200, np.nan], [130, 200, np.nan]])
    vol = _frame([[1, 1, 1], [1, 1, 1], [1, 0, 1 if c_sellable_on_rebalance else 0], [1, 0, 0], [1, 1, 0]])
    div = pd.DataFrame([("A", pd.Timestamp("2024-01-05"), 10.0), ("Z", pd.Timestamp("2024-01-05"), 99.0)], columns=["code", "ex", "dps"])
    sel = {DAYS[0]: {"A", "B", "C"}, DAYS[2]: {"A"}}
    return close, vol, div, sel


def test_buy_hold_rebalance_dividend_and_carried_name():
    close, vol, div, sel = _setup(c_sellable_on_rebalance=True)
    nav = VQ.simulate(sel, close, vol, {"C": DAYS[2]}, div, DAYS[0], DAYS[-1], spread=False)
    w = 1 / 3
    assert abs(nav.iloc[0] - (1 - C)) < 1e-12                               # three equal buys, 25 bps on the lot
    assert abs(nav.iloc[1] - (1 - C + w * 0.1)) < 1e-12                     # A +10 %
    # day 2: C sold (cost), B carried (no trade), everything investable goes into A (cost on the addition only)
    investable = (-C + w * (1 - C)) + w * 1.2
    nav2 = 1 + 0.2 / 3 - C * (5 / 3) + (4 / 3) * C * C
    assert abs(nav.iloc[2] - nav2) < 1e-12
    units_a = investable / 120
    assert abs(nav.iloc[3] - (nav2 + units_a * 10 * (1 - VQ.DIV_TAX))) < 1e-12   # dividend net of the 10 % final tax
    assert abs(nav.iloc[4] - (nav2 + units_a * 10 * (1 - VQ.DIV_TAX) + units_a * 10)) < 1e-12   # A 120 -> 130; B still 200


def test_delisted_name_goes_to_zero_after_its_last_bar():
    close, vol, div, sel = _setup(c_sellable_on_rebalance=False)             # C cannot be sold on day 2 either
    nav = VQ.simulate(sel, close, vol, {"C": DAYS[2]}, div, DAYS[0], DAYS[-1], spread=False)
    w = 1 / 3
    # day 2: only A is re-weighted with the cash; B and C are carried at their day-2 value
    investable = -C + w * 1.2
    nav2 = -C + w * 1.2 + w + w - C * abs(investable - w * 1.2)
    assert abs(nav.iloc[2] - nav2) < 1e-12
    units_a = investable / 120
    assert abs(nav.iloc[3] - (nav2 - w + units_a * 10 * (1 - VQ.DIV_TAX))) < 1e-12     # C worth zero from day 3


def test_weighted_targets_renormalise_over_buyable_names():
    close, vol, div, _ = _setup(c_sellable_on_rebalance=True)
    # A gets 3 parts, B 1 part, C is wanted but cannot be bought on day 0 (no trade) -> A 75 %, B 25 %
    vol.iloc[0, 2] = 0
    nav = VQ.simulate({DAYS[0]: {'A': 3.0, 'B': 1.0, 'C': 2.0}}, close, vol, {}, div.iloc[0:0], DAYS[0], DAYS[1], spread=False)
    assert abs(nav.iloc[0] - (1 - C)) < 1e-12
    assert abs(nav.iloc[1] - (1 - C + 0.75 * 0.1)) < 1e-12               # only A moved, +10 % on a 75 % weight


def test_drift_mode_keeps_winners_and_funds_entrants_from_cash():
    close, vol, div, _ = _setup(c_sellable_on_rebalance=True)
    vol.iloc[2] = [1, 1, 1]                                                 # everyone tradable on the rebalance day
    # day 0: A, B ; day 2: A stays, B leaves, C enters -> B sold, its cash buys C; A is not touched
    plan = {DAYS[0]: {'A', 'B'}, DAYS[2]: lambda held: (held & {'A'}) | {'C'}}
    nav = VQ.simulate(plan, close, vol, {}, div.iloc[0:0], DAYS[0], DAYS[2], spread=False, mode='drift')
    units_a = 0.5 / 100
    # day 2 before trades: A = 0.5 * 1.2, B = 0.5, cash = -C ; sell B -> cash = 0.5 (1 - C) - C ; buy C with it
    cash_after_sell = 0.5 * (1 - C) - C
    units_c = cash_after_sell / 50
    expected = units_a * 120 + units_c * 50 - units_c * 50 * C            # A untouched, C bought, cost on C only
    assert abs(nav.iloc[2] - expected) < 1e-12
    reset = VQ.simulate(plan, close, vol, {}, div.iloc[0:0], DAYS[0], DAYS[2], spread=False, mode='reset')
    assert reset.iloc[2] < nav.iloc[2]                                     # the reset trims A and pays for it


def test_cost_side_includes_half_tick_spread():
    assert VQ.cost_side(120.0, False) == C
    assert abs(VQ.cost_side(120.0, True) - (C + 0.5 * 1 / 120)) < 1e-15
    assert abs(VQ.cost_side(3000.0, True) - (C + 0.5 * 10 / 3000)) < 1e-15


def test_drift_cap_limits_one_entrant_to_a_slice_of_nav():
    close, vol, div, _ = _setup(c_sellable_on_rebalance=True)
    nav = VQ.simulate({DAYS[0]: {'A'}}, close, vol, {}, div.iloc[0:0], DAYS[0], DAYS[1], spread=False, mode='drift', cap=0.5)
    units_a = 0.5 / (100 * (1 + C))                                        # half the NAV, cost inside the budget
    assert abs(nav.iloc[0] - (0.5 + units_a * 100)) < 1e-12
    assert abs(nav.iloc[1] - (0.5 + units_a * 110)) < 1e-12               # the other half sat in cash
    full = VQ.simulate({DAYS[0]: {'A'}}, close, vol, {}, div.iloc[0:0], DAYS[0], DAYS[1], spread=False, mode='drift')
    assert full.iloc[1] > nav.iloc[1]                                      # uncapped: all in, more upside


def test_cash_earns_the_rate_and_the_cap_can_follow_the_date():
    close, vol, div, _ = _setup(c_sellable_on_rebalance=True)
    # nothing bought: 1.0 of cash at 5 %/yr for four trading days after day 0
    nav = VQ.simulate({}, close, vol, {}, div.iloc[0:0], DAYS[0], DAYS[-1], spread=False, cash_rate=0.05)
    daily = (1.05) ** (1 / 252) - 1
    assert abs(nav.iloc[-1] - (1 + daily) ** 5) < 1e-12
    # a date-dependent cap: 25 % on day 0
    nav = VQ.simulate({DAYS[0]: {'A'}}, close, vol, {}, div.iloc[0:0], DAYS[0], DAYS[1], spread=False, mode='drift',
                      cap=lambda d: 0.25 if d == DAYS[0] else 1.0)
    units_a = 0.25 / (100 * (1 + C))
    assert abs(nav.iloc[1] - (0.75 + units_a * 110)) < 1e-12


def test_capped_drift_does_not_depend_on_the_order_of_the_names():
    close, vol, div, _ = _setup(c_sellable_on_rebalance=True)
    vol.iloc[0] = [1, 1, 1]
    a = VQ.simulate({DAYS[0]: {'A', 'B', 'C'}}, close, vol, {}, div.iloc[0:0], DAYS[0], DAYS[2], spread=False, mode='drift', cap=0.4)
    b = VQ.simulate({DAYS[0]: ['C', 'A', 'B']}, close, vol, {}, div.iloc[0:0], DAYS[0], DAYS[2], spread=False, mode='drift', cap=0.4)
    assert list(a.round(12)) == list(b.round(12))
    # three names, cap 40 % each: everyone gets a third of the cash (the cap does not bind), nothing is left over
    units_a = (1 / 3) / (100 * (1 + C))
    assert abs(a.iloc[0] - (units_a * 100 + (1 / 3) / (1 + C) + (1 / 3) / (1 + C))) < 1e-12


def test_exposure_scales_the_targets_and_leaves_the_rest_in_cash():
    close, vol, div, _ = _setup(c_sellable_on_rebalance=True)
    nav = VQ.simulate({DAYS[0]: {'A'}}, close, vol, {}, div.iloc[0:0], DAYS[0], DAYS[1], spread=False, exposure=lambda d: 0.4)
    # 40 % of the book in A (cost on the bought amount), 60 % in cash
    assert abs(nav.iloc[0] - (1 - 0.4 * C)) < 1e-12
    assert abs(nav.iloc[1] - (1 - 0.4 * C + 0.4 * 0.1)) < 1e-12
