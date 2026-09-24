"""Track record scorecard (the desk's "is it proven yet?" number): round-trip accounting and the profile comparison."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from blackheart_ingest.idx import track as tk


def _f(day: int, code: str, side: str, lots: str, price: str, fee: str = "0", i: int = 0) -> dict:
    return {"id": i or day, "trade_date": date(2026, 9, day), "code": code, "side": side,
            "lots": Decimal(lots), "price": Decimal(price), "fee": Decimal(fee)}


# ---- pure: round trips -------------------------------------------------------------------------------------------
def test_one_round_trip_nets_fees_and_counts_hold_days() -> None:
    trips = tk.round_trips([_f(1, "AAA", "buy", "10", "1000", "5000"),
                            _f(11, "AAA", "sell", "10", "1100", "6000")])
    assert len(trips) == 1
    t = trips[0]
    assert t["code"] == "AAA" and t["hold_d"] == 10
    assert t["cost"] == Decimal(10 * 100 * 1000 + 5000)          # 1,005,000
    assert t["proceeds"] == Decimal(10 * 100 * 1100 - 6000)      # 1,094,000
    assert round(t["net_pct"], 6) == round(1094000 / 1005000 - 1, 6)


def test_open_position_is_not_a_closed_trade() -> None:
    assert tk.round_trips([_f(1, "AAA", "buy", "10", "1000")]) == []


def test_partial_sell_stays_in_the_same_trip_until_flat() -> None:
    fills = [_f(1, "AAA", "buy", "10", "1000"),
             _f(5, "AAA", "sell", "4", "1200"),
             _f(9, "AAA", "sell", "6", "900")]
    trips = tk.round_trips(fills)
    assert len(trips) == 1                                        # one trip, not two
    t = trips[0]
    assert t["sells"] == 2 and t["buys"] == 1 and t["hold_d"] == 8
    assert t["proceeds"] == Decimal(4 * 100 * 1200 + 6 * 100 * 900)


def test_rebuying_after_a_close_starts_a_new_trip() -> None:
    fills = [_f(1, "AAA", "buy", "10", "1000"), _f(3, "AAA", "sell", "10", "1100"),
             _f(8, "AAA", "buy", "10", "1000"), _f(9, "AAA", "sell", "10", "900")]
    trips = tk.round_trips(fills)
    assert len(trips) == 2
    assert trips[0]["net_pct"] > 0 and trips[1]["net_pct"] < 0
    assert trips[1]["opened"] == date(2026, 9, 8)                 # the second trip does not inherit the first's cost


def test_two_names_are_independent() -> None:
    fills = [_f(1, "AAA", "buy", "10", "1000", i=1), _f(1, "BBB", "buy", "10", "500", i=2),
             _f(4, "BBB", "sell", "10", "600", i=3)]
    trips = tk.round_trips(fills)
    assert [t["code"] for t in trips] == ["BBB"]


def test_hold_is_counted_in_sessions_when_a_counter_is_supplied() -> None:
    # 1 Sep -> 11 Sep is 10 calendar days but, say, 7 trading days
    fake_sessions = lambda a, b: 7  # noqa: E731
    trips = tk.round_trips([_f(1, "AAA", "buy", "10", "1000"), _f(11, "AAA", "sell", "10", "1100")], sessions=fake_sessions)
    assert trips[0]["hold_d"] == 10 and trips[0]["hold_sessions"] == 7
    a = tk._agg(trips)
    assert a["hold_d"] == 7 and a["hold_unit"] == "sessions"          # the research profiles quote bars, so prefer them


def test_hold_falls_back_to_calendar_days_without_a_counter() -> None:
    trips = tk.round_trips([_f(1, "AAA", "buy", "10", "1000"), _f(11, "AAA", "sell", "10", "1100")])
    assert trips[0]["hold_sessions"] is None
    assert tk._agg(trips)["hold_unit"] == "days"


# ---- pure: aggregation -------------------------------------------------------------------------------------------
def test_agg_hit_payoff_and_average() -> None:
    a = tk._agg([{"net_pct": 0.10, "hold_d": 10}, {"net_pct": 0.20, "hold_d": 20},
                 {"net_pct": -0.05, "hold_d": 5}, {"net_pct": -0.05, "hold_d": 5}])
    assert a["n"] == 4
    assert a["hit"] == 0.5
    assert round(a["payoff"], 6) == round(0.15 / 0.05, 6)         # mean win / mean loss
    assert round(a["avg_net"], 6) == 0.05
    assert a["hold_d"] == 10


def test_agg_of_nothing_is_empty_not_zero() -> None:
    a = tk._agg([])
    assert a["n"] == 0 and a["hit"] is None and a["avg_net"] is None


# ---- profiles ----------------------------------------------------------------------------------------------------
def test_every_profile_has_a_bar_and_a_source() -> None:
    for rule, p in tk.PROFILES.items():
        assert p["bar"] > 0 and p["source"], rule
        assert 0 < p["hit"] < 1, rule


def test_render_shows_progress_towards_the_bar() -> None:
    sc = {"book": "trend_live", "label": "Trend", "rule": "trend", "profile": tk.PROFILES["trend"],
          "live": tk._agg([]), "trades": [], "open_positions": 3, "halted": False,
          "archived": False, "progress": (0, 60)}
    out = tk.render(sc)
    assert "0/60" in out and "belum ada trade tertutup" in out and "AMBANG" not in out


def test_render_flags_the_bar_once_reached_and_a_halt() -> None:
    trades = [{"net_pct": 0.05, "hold_d": 20}] * 60
    sc = {"book": "trend_live", "label": "Trend", "rule": "trend", "profile": tk.PROFILES["trend"],
          "live": tk._agg(trades), "trades": trades, "open_positions": 0, "halted": True,
          "archived": False, "progress": (60, 60)}
    out = tk.render(sc)
    assert "AMBANG TERCAPAI" in out and "HALTED" in out
    assert "target 44%" in out                                     # compared against the backtest, not against zero
