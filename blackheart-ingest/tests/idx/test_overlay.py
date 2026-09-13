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
