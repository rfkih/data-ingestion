"""The overlay rules are pure: the regime from a close series, and which listed names an entry gate holds back."""
from __future__ import annotations

from decimal import Decimal

import pytest

from blackheart_ingest.idx import overlay as OV


def test_regime_needs_a_full_window_and_compares_close_to_its_average() -> None:
    short = OV.regime_from_closes([100] * 50)
    assert short["on"] is True and short["sma"] is None and short["n"] == 50     # no average yet: invested
    rising = OV.regime_from_closes(list(range(1, 301)))                          # 101..300 in the window, close 300
    assert rising["on"] is True and rising["sma"] == Decimal("200.5") and rising["close"] == 300
    falling = OV.regime_from_closes(list(range(300, 0, -1)))
    assert falling["on"] is False and falling["close"] == 1
    flat = OV.regime_from_closes([Decimal("7000")] * 200)
    assert flat["on"] is False                                                    # equal to the average is not above it
    with pytest.raises(ValueError):
        OV.regime_from_closes([])


def test_gate_holds_back_listed_names_under_their_average_unless_already_held() -> None:
    targets = {"UP": Decimal("0.25"), "DOWN": Decimal("0.25"), "HELD": Decimal("0.25"), "NEW": Decimal("0.25")}
    trend = {"UP": {"close": 10, "sma": Decimal(9), "on": True}, "DOWN": {"close": 8, "sma": Decimal(9), "on": False},
             "HELD": {"close": 8, "sma": Decimal(9), "on": False}, "NEW": {"close": 5, "sma": None, "on": True}}
    assert OV.gate(targets, trend, held={"HELD"}) == ["DOWN"]                     # held stays, young listing is bought
    assert OV.gate(targets, {}, held=set()) == []                                  # no trend data: nothing held back


def test_take_profit_hits_compare_the_close_to_the_average_purchase_price() -> None:
    positions = [{"code": "UP", "avg_price": 1000}, {"code": "FLAT", "avg_price": 1000}, {"code": "NOAVG", "avg_price": None}]
    hits = OV.take_profit_hits(positions, {"UP": 2000, "FLAT": 1500, "NOAVG": 9000}, 100)
    assert set(hits) == {"UP"} and "+100 %" in hits["UP"]
    assert OV.take_profit_hits(positions, {"UP": 2000}, None) == {}
    assert set(OV.take_profit_hits(positions, {"UP": 2000, "FLAT": 1500}, 50)) == {"UP", "FLAT"}


def test_rsi_and_the_oversold_clause_of_the_gate() -> None:
    from decimal import Decimal

    falling = [100 - i for i in range(40)]                                 # 40 straight down days
    rising = [100 + i for i in range(40)]
    assert OV.rsi_from_closes(falling) == 0 and OV.rsi_from_closes(rising) == 100
    assert OV.rsi_from_closes([100] * 10) is None                          # not enough history
    mixed = [100, 101, 100, 102, 101, 103, 102, 104, 103, 105, 104, 106, 105, 107, 106, 108, 107, 109]
    r = OV.rsi_from_closes(mixed)
    assert r is not None and 50 < r < 100
    targets = {"DOWN": Decimal("0.5"), "OVERSOLD": Decimal("0.5")}
    trend = {"DOWN": {"close": 8, "sma": Decimal(9), "on": False}, "OVERSOLD": {"close": 7, "sma": Decimal(9), "on": False}}
    assert OV.gate(targets, trend, set()) == ["DOWN", "OVERSOLD"]          # without RSI both are held back
    assert OV.gate(targets, trend, set(), {"OVERSOLD": Decimal(25), "DOWN": Decimal(45)}) == ["DOWN"]   # oversold is bought


def test_trend_breaks_need_a_cross_from_above() -> None:
    from decimal import Decimal

    prev = {"A": {"close": 10, "sma": Decimal(9), "on": True}, "B": {"close": 8, "sma": Decimal(9), "on": False}, "C": {"close": 10, "sma": Decimal(9), "on": True}}
    now = {"A": {"close": 8, "sma": Decimal(9), "on": False}, "B": {"close": 7, "sma": Decimal(9), "on": False}, "C": {"close": 11, "sma": Decimal(9), "on": True}}
    hits = OV.trend_breaks(prev, now, {"A", "B", "C"})
    assert set(hits) == {"A"}                                              # B was already below (no cross), C still above


def test_stress_signals_and_the_cash_target() -> None:
    from decimal import Decimal

    flat = [100.0] * 1000
    s = OV.stress_from_series(flat, breadth=0.6)
    assert s["n_on"] == 0 and not any(s["signals"].values())
    crash = [100.0] * 900 + [100.0 * (0.97 ** i) for i in range(1, 101)]      # a hundred days of -3 %: under MA200, vol spike, -95 % from high
    s = OV.stress_from_series(crash, breadth=0.2)
    assert s["signals"] == {"ma": True, "vol": True, "dd": True, "breadth": True} and s["n_on"] == 4
    assert OV.stress_on(s, "ma") and OV.stress_on(s, "any2")
    mild = OV.stress_from_series([100.0 + 0.5 * (i % 2) for i in range(990)] + [99.0] * 10, breadth=0.5)   # a touch under the average only
    assert mild["signals"]["ma"] and mild["n_on"] == 1 and OV.stress_on(mild, "ma") and not OV.stress_on(mild, "any2")
    book = {"cash_floor_pct": Decimal("30"), "stress_cash_pct": Decimal("50")}
    assert OV.cash_target(book, False) == Decimal("0.3") and OV.cash_target(book, True) == Decimal("0.5")
    assert OV.cash_target({"cash_floor_pct": 0, "stress_cash_pct": 0}, True) == 0 and not OV.uses_cash_buffer({"cash_floor_pct": 0, "stress_cash_pct": 0})
    assert OV.cash_target({"cash_floor_pct": 30, "stress_cash_pct": 0}, True) == Decimal("0.3")   # no stress level set: the floor holds
