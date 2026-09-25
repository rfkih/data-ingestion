"""The combined book (idx/combo_book.py): settings, sleeve attribution from fills, line sizing, the plan composer (sells,
trend buys, ML watches, slot cap), the session clock, and the plan text."""
from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from blackheart_ingest.idx import combo_book as cb

WIB = ZoneInfo("Asia/Jakarta")
BOOK = {"book": "paper-c0mb0", "fee_buy_pct": Decimal("0.15"), "fee_sell_pct": Decimal("0.25"), "params": {}}


def test_settings_defaults_overlay_and_validate() -> None:
    s = cb.settings({"params": {}})
    assert s["sleeves"] == {"trend": 0.05, "ml": 0.05, "gap": 0.10} and s["slots"] == 20 and s["ml"]["confirm"] == 0.05
    s = cb.settings({"params": {"sleeves": {"trend": 0.025}, "slots": 10, "ml": {"margin": 1.5}}})
    assert s["sleeves"]["trend"] == 0.025 and s["sleeves"]["gap"] == 0.10 and s["slots"] == 10 and s["ml"]["margin"] == 1.5 and s["ml"]["ema"] == 3
    with pytest.raises(ValueError):
        cb.settings({"params": {"sleeves": {"gap": 0.9}}})


def test_attribute_tracks_lots_and_entry_per_sleeve() -> None:
    fills = [
        {"code": "AAAA", "side": "buy", "flags": ["sleeve:ml", "ml:entry"], "trade_date": date(2026, 9, 1), "lots": 10, "price": 1000},
        {"code": "AAAA", "side": "buy", "flags": ["sleeve:trend", "trend:entry"], "trade_date": date(2026, 9, 2), "lots": 5, "price": 1100},
        {"code": "AAAA", "side": "sell", "flags": ["sleeve:ml", "ml:exit"], "trade_date": date(2026, 9, 10), "lots": 10, "price": 1200},
        {"code": "BBBB", "side": "buy", "flags": ["sleeve:gap", "gapfade:entry"], "trade_date": date(2026, 9, 10), "lots": 20, "price": 500},
        {"code": "BBBB", "side": "sell", "flags": ["sleeve:gap"], "trade_date": date(2026, 9, 10), "lots": 20, "price": 520},
        {"code": "CCCC", "side": "buy", "flags": ["sleeve:ml"], "trade_date": date(2026, 9, 11), "lots": 4, "price": 200},
        {"code": "CCCC", "side": "buy", "flags": ["sleeve:ml"], "trade_date": date(2026, 9, 12), "lots": 4, "price": 300},
    ]
    pos = cb.attribute(fills)
    assert "AAAA" not in pos["ml"] and pos["trend"]["AAAA"]["lots"] == 5 and pos["trend"]["AAAA"]["entry_date"] == date(2026, 9, 2)
    assert pos["gap"] == {}
    assert pos["ml"]["CCCC"]["lots"] == 8 and pos["ml"]["CCCC"]["entry_price"] == Decimal(250) and pos["ml"]["CCCC"]["entry_date"] == date(2026, 9, 11)
    assert cb.held_codes(pos) == {"AAAA", "CCCC"}
    assert cb.sleeve_of(["x", "sleeve:gap"]) == "gap" and cb.sleeve_of(None) == "manual"


def test_size_line_buys_whole_lots_within_slot_and_cash_and_refuses_dust() -> None:
    nav = Decimal(20_000_000)
    ln = cb.size_line("AAAA", "buy", Decimal(1000), None, Decimal(1_000_000), Decimal(5_000_000), Decimal("0.0015"), nav, "why", ["sleeve:ml"])
    assert ln["limit_price"] == Decimal(1005) and ln["lots"] == 9 and ln["notional"] == Decimal(9 * 100 * 1005)      # 9 lots x 100 x 1,005 x 1.0015 <= 1 M
    assert cb.size_line("AAAA", "buy", Decimal(1000), None, Decimal(1_000_000), Decimal(50_000), Decimal("0.0015"), nav, "why", []) is None   # no cash
    assert cb.size_line("ZZZZ", "buy", Decimal(9000), None, Decimal(1_000_000), Decimal(5_000_000), Decimal("0.0015"), nav, "why", []) is not None
    assert cb.size_line("ZZZZ", "buy", Decimal(12000), None, Decimal(1_000_000), Decimal(5_000_000), Decimal("0.0015"), nav, "why", []) is None  # 1 lot > slot
    s = cb.size_line("AAAA", "sell", Decimal(1000), Decimal(9), Decimal(0), Decimal(0), Decimal("0.0025"), nav, "exit", ["sleeve:ml"])
    assert s["side"] == "sell" and s["limit_price"] == Decimal(995) and s["lots"] == 9


def _ml(rows):
    return pd.DataFrame(rows, columns=["code", "e", "rt", "close", "v60"])


def test_compose_sells_exits_buys_trend_and_watches_ml_within_slots() -> None:
    S = cb.settings({"params": {"slots": 4}})
    nav, cash = Decimal(20_000_000), Decimal(12_000_000)
    pos = {"gap": {}, "trend": {"TTTT": {"lots": Decimal(10), "entry_date": date(2026, 8, 1), "entry_price": Decimal(900)}},
           "ml": {"MMMM": {"lots": Decimal(10), "entry_date": date(2026, 6, 1), "entry_price": Decimal(400)},
                  "NNNN": {"lots": Decimal(10), "entry_date": date(2026, 9, 1), "entry_price": Decimal(400)}}, "manual": {}}
    closes = {"TTTT": Decimal(1000), "MMMM": Decimal(410), "NNNN": Decimal(420), "AAAA": Decimal(500), "BBBB": Decimal(700), "CCCC": Decimal(300), "DDDD": Decimal(250)}
    trend_entries = [{"code": "AAAA", "vol_ratio": 2.1}, {"code": "BBBB", "vol_ratio": 1.8}]
    trend_exits = [{"code": "TTTT", "lots": Decimal(10), "reason": "trailing stop", "close": Decimal(1000)}]
    ml = _ml([("MMMM", -0.02, 0.01, 410, 6e9), ("NNNN", 0.01, 0.01, 420, 6e9), ("CCCC", 0.05, 0.01, 300, 6e9), ("DDDD", 0.03, 0.01, 250, 6e9),
              ("AAAA", 0.04, 0.01, 500, 6e9)])
    res = cb.compose(BOOK, S, nav, cash, pos, closes, trend_entries, trend_exits, ml, {"MMMM": 70, "NNNN": 15}, set(), set(), date(2026, 9, 25))
    sells = {ln["code"]: ln for ln in res["lines"] if ln["side"] == "sell"}
    buys = [ln["code"] for ln in res["lines"] if ln["side"] == "buy"]
    assert "TTTT" in sells and sells["TTTT"]["flags"][0] == "sleeve:trend"
    assert "MMMM" in sells and "expiry" in sells["MMMM"]["reason"]             # 70 d > max_hold
    assert "NNNN" not in sells                                                 # e > 0, young: held
    # slots 4: held after exits = NNNN (1); free = 3 -> trend buys take AAAA, BBBB (2) ... AAAA is also an ML candidate but trend gets it first
    assert buys == ["AAAA", "BBBB"]
    assert [w["code"] for w in res["watches"]] == ["CCCC"] and res["free_slots"] == 0
    w = res["watches"][0]
    assert w["level_price"] == Decimal(316) and w["ref_price"] == Decimal(300)  # 300 x 1.05 = 315 -> snapped up on the Rp 2 tick
    assert w["until_date"] > date(2026, 9, 25) and abs(w["e_bps"] - 500) < 1e-6
    assert w["rule"] == "+5/10" and w["size_frac"] == 1.0 and res["floor_held"] == []
    assert set(res["targets"]) >= {"AAAA", "BBBB", "NNNN"} and "TTTT" not in res["targets"]


def test_confirm_rules_make_one_watch_per_rule_with_a_share_of_the_slot() -> None:
    S = cb.settings({"params": {"ml": {"confirm_rules": [[0.05, 10], [0.08, 10], [0.10, 10], [0.08, 5]]}}})
    assert S["ml"]["rule_names"] == ["+5/10", "+8/10", "+10/10", "+8/5"] and abs(S["ml"]["size_frac"] - 0.25) < 1e-9
    pos = {"gap": {}, "trend": {}, "ml": {}, "manual": {}}
    ml = _ml([("CCCC", 0.05, 0.01, 300, 6e9)])
    res = cb.compose(BOOK, S, Decimal(20_000_000), Decimal(20_000_000), pos, {"CCCC": Decimal(300)}, [], [], ml, {}, set(), set(), date(2026, 9, 25))
    ws = res["watches"]
    assert [w["rule"] for w in ws] == ["+5/10", "+8/10", "+10/10", "+8/5"] and all(w["code"] == "CCCC" for w in ws)
    assert [w["level_price"] for w in ws] == [Decimal(316), Decimal(324), Decimal(330), Decimal(324)]
    assert ws[3]["until_date"] < ws[1]["until_date"] and res["free_slots"] == S["slots"] - 1        # four rules, one slot
    with pytest.raises(ValueError):
        cb.settings({"params": {"ml": {"confirm_rules": [[0.05, 10], [0.05, 10]]}}})               # duplicates
    with pytest.raises(ValueError):
        cb.settings({"params": {"cash_floor": 0.95}})


def test_cash_floor_holds_back_new_buys() -> None:
    assert cb.invested_ok(Decimal(20_000_000), Decimal(20_000_000), Decimal(1_000_000), 0.30)
    assert cb.invested_ok(Decimal(20_000_000), Decimal(7_000_000), Decimal(1_000_000), 0.30)          # 65 % + 5 % = 70 %: at the line
    assert not cb.invested_ok(Decimal(20_000_000), Decimal(6_500_000), Decimal(1_000_000), 0.30)      # 67.5 % + 5 % > 70 %
    assert cb.invested_ok(Decimal(20_000_000), Decimal(0), Decimal(1_000_000), 0.0)                   # floor off
    S = cb.settings({"params": {"cash_floor": 0.30}})
    pos = {"gap": {}, "trend": {}, "ml": {}, "manual": {}}
    ml = _ml([])
    # NAV 20 M, cash 6.5 M (67.5 % invested): a 5 % trend buy would breach 70 % -> held back, reported
    res = cb.compose(BOOK, S, Decimal(20_000_000), Decimal(6_500_000), pos, {"AAAA": Decimal(500)}, [{"code": "AAAA", "vol_ratio": 2.0}], [], ml, {}, set(), set(),
                     date(2026, 9, 25))
    assert res["lines"] == [] and res["floor_held"] == ["AAAA"]
    res = cb.compose(BOOK, S, Decimal(20_000_000), Decimal(8_000_000), pos, {"AAAA": Decimal(500)}, [{"code": "AAAA", "vol_ratio": 2.0}], [], ml, {}, set(), set(),
                     date(2026, 9, 25))
    assert [ln["code"] for ln in res["lines"]] == ["AAAA"] and res["floor_held"] == []


def test_adv_cap_limits_trend_buys_to_a_share_of_adv20() -> None:
    assert cb.adv_capped(Decimal(100), Decimal(1000), 0.05) == Decimal(50)
    assert cb.adv_capped(Decimal(100), Decimal(10_000), 0.05) == Decimal(100)          # the slot binds first
    assert cb.adv_capped(Decimal(100), None, 0.05) == Decimal(100)                     # no ADV: leave the slot alone
    assert cb.adv_capped(Decimal(100), Decimal(1000), None) == Decimal(100)            # cap off (the ML default)
    S = cb.settings({"params": {}})
    assert S["adv_cap"] == {"trend": 0.05, "ml": None}
    with pytest.raises(ValueError):
        cb.settings({"params": {"adv_cap": {"trend": 1.5}}})
    pos = {"gap": {}, "trend": {}, "ml": {}, "manual": {}}
    ml = _ml([])
    entry = [{"code": "AAAA", "vol_ratio": 2.0}]
    # NAV 2 B -> trend slot 100 M; AAAA trades 1 B a day -> 5 % = 50 M: the line is cut to the cap and flagged
    res = cb.compose(BOOK, S, Decimal(2_000_000_000), Decimal(2_000_000_000), pos, {"AAAA": Decimal(500)}, entry, [], ml, {}, set(), set(),
                     date(2026, 9, 25), {"AAAA": Decimal(1_000_000_000)})
    (ln,) = res["lines"]
    assert ln["notional"] <= Decimal(50_000_000) and ln["notional"] > Decimal(49_000_000) and "capped:adv20" in ln["flags"]
    # Rp 20 M book, same name: the 1 M slot is far under the cap -> sized by the slot, no flag
    res = cb.compose(BOOK, S, Decimal(20_000_000), Decimal(20_000_000), pos, {"AAAA": Decimal(500)}, entry, [], ml, {}, set(), set(),
                     date(2026, 9, 25), {"AAAA": Decimal(1_000_000_000)})
    (ln,) = res["lines"]
    assert ln["notional"] <= Decimal(1_000_000) and "capped:adv20" not in ln["flags"]


def test_compose_skips_names_already_held_open_or_watched() -> None:
    S = cb.settings({"params": {}})
    pos = {"gap": {}, "trend": {}, "ml": {"CCCC": {"lots": Decimal(1), "entry_date": date(2026, 9, 20), "entry_price": Decimal(300)}}, "manual": {}}
    ml = _ml([("CCCC", 0.05, 0.01, 300, 6e9), ("DDDD", 0.05, 0.01, 250, 6e9), ("EEEE", 0.05, 0.01, 250, 6e9)])
    res = cb.compose(BOOK, S, Decimal(20_000_000), Decimal(20_000_000), pos, {"CCCC": Decimal(300)}, [], [], ml, {"CCCC": 3}, {"DDDD"}, {"EEEE"}, date(2026, 9, 25))
    assert res["lines"] == [] and res["watches"] == []                       # held, open line, already watched


def test_compose_without_ml_scores_still_plans_trend_and_exits() -> None:
    S = cb.settings({"params": {}})
    pos = {"gap": {}, "trend": {}, "ml": {"MMMM": {"lots": Decimal(10), "entry_date": date(2026, 9, 1), "entry_price": Decimal(400)}}, "manual": {}}
    ml = _ml([])
    res = cb.compose(BOOK, S, Decimal(20_000_000), Decimal(20_000_000), pos, {"MMMM": Decimal(410), "AAAA": Decimal(500)}, [{"code": "AAAA", "vol_ratio": 2.0}], [], ml, {"MMMM": 5},
                     set(), set(), date(2026, 9, 25))
    assert [ln["code"] for ln in res["lines"]] == ["MMMM", "AAAA"]           # no score -> the ML position is sold ("gone"), the trend buy still sized
    assert res["watches"] == [] and res["ml_candidates"] == 0


def test_in_session_and_plan_text() -> None:
    assert cb.in_session(datetime.combine(date(2026, 9, 25), time(10, 0), tzinfo=WIB))
    assert not cb.in_session(datetime.combine(date(2026, 9, 25), time(16, 30), tzinfo=WIB))
    assert not cb.in_session(datetime.combine(date(2026, 9, 26), time(10, 0), tzinfo=WIB))
    res = {"book": "live-x", "run_date": date(2026, 9, 25), "nav": Decimal(20_000_000), "cash": Decimal(15_000_000), "free_slots": 3,
           "lines": [{"side": "sell", "code": "TTTT", "lots": 10, "limit_price": Decimal(995), "reason": "trailing stop"},
                     {"side": "buy", "code": "AAAA", "lots": 9, "limit_price": Decimal(1005), "notional": Decimal(904500), "reason": "trend"}],
           "regime": {"on": True}, "trend_signals": 2, "held_back": [], "ml_scored": True}
    txt = cb.render_plan(res, [{"code": "CCCC", "level_price": Decimal(316), "ref_price": Decimal(300), "until_date": date(2026, 10, 9), "e_bps": 500.0, "cost_bps": 90.0}], "Combo")
    assert "JUAL" in txt and "TTTT" in txt and "BELI" in txt and "AAAA" in txt and "AWASI" in txt and "316" in txt and "terbuka" in txt
