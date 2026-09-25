"""The daily board: the five it shows, the shape each card promises the app, and the two readings that are easy
to get wrong - an annual list is not a buy order outside its May window, and a gate refusal must stay visible
instead of quietly vanishing from the board."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from blackheart_ingest.idx import signalboard as sb

D = date(2026, 9, 24)


def test_board_is_the_five_equity_engines_in_roi_order() -> None:
    assert sb.KEYS == ["gapfade", "trend_small", "combined_book", "value_strict", "trend_liq"]
    assert [e["roi_rank"] for e in sb.BOARD] == sorted(e["roi_rank"] for e in sb.BOARD)
    for key in ("book_gold", "ew3", "gem_idr", "trend_small_base_rate", "regime_gate", "ara_sell"):
        assert key not in sb.BY_KEY                          # gold/foreign engines and overlays are not board entries
    for e in sb.BOARD:
        assert e["rule"] and e["horizon"] and e["decided_at"]  # every card explains itself on the screen


def test_rows_for_rejects_a_strategy_that_is_not_on_the_board() -> None:
    with pytest.raises(ValueError, match="not a board strategy"):
        sb.rows_for(None, "book_gold", D)                    # type: ignore[arg-type]


def test_j_makes_a_reason_json_safe() -> None:
    out = sb._j({"px": Decimal("1234.5"), "d": date(2026, 1, 2), "n": [Decimal(1), "x"], "deep": {"v": Decimal(3)}})
    assert out == {"px": "1234.5", "d": "2026-01-02", "n": ["1", "x"], "deep": {"v": "3"}}
    assert out["n"][0] == "1" and isinstance(out["px"], str)


class _FakeTrendBook:
    """Stands in for trend_book: a universe of two, one of which breaks out today."""
    K = 10

    @staticmethod
    def universe(conn: Any, d: date, variant: str) -> dict[str, dict[str, Any]]:
        return {"AAA": {"code": "AAA", "close": Decimal(500)}, "BBB": {"code": "BBB", "close": Decimal(200)}}

    @staticmethod
    def history(conn: Any, codes: list[str], d: date) -> Any:
        return None

    @staticmethod
    def entry_signals(hist: Any, d: date) -> list[dict[str, Any]]:
        return [{"code": "AAA", "vol_ratio": 2.4, "hi60": 500.0, "ma200": 410.0}]

    @staticmethod
    def hold_back(entries: list[dict[str, Any]], regime_on: bool) -> tuple[list[dict[str, Any]], list[str]]:
        return (entries, []) if regime_on else ([], [e["code"] for e in entries])


def _patch_trend(monkeypatch: pytest.MonkeyPatch, *, gate_on: bool) -> None:
    import blackheart_ingest.idx.trend_book as real
    for name in ("universe", "history", "entry_signals", "hold_back", "K"):
        monkeypatch.setattr(real, name, getattr(_FakeTrendBook, name), raising=True)
    monkeypatch.setattr(sb, "_regime", lambda conn, d: {"index": "COMPOSITE", "date": str(d), "close": "6000",
                                                        "sma": "7000", "on": gate_on, "n": 200})


def test_trend_rows_size_the_slot_and_carry_the_breakout_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_trend(monkeypatch, gate_on=True)
    rows, meta = sb.trend_rows(None, D, "small")             # type: ignore[arg-type]
    assert [r["code"] for r in rows] == ["AAA"]
    assert rows[0]["action"] == "buy" and rows[0]["ref_price"] == Decimal(500)
    assert rows[0]["size_pct"] == Decimal("10.00")           # one of K = 10 slots, as a percent of NAV
    assert rows[0]["reason"]["vol_ratio"] == 2.4 and rows[0]["reason"]["ma200"] == 410.0
    assert meta["universe"] == 2 and meta["slots"] == 10 and meta["why"] is None


def test_a_refused_name_stays_on_the_board_as_hold_back(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_trend(monkeypatch, gate_on=False)
    rows, meta = sb.trend_rows(None, D, "small")             # type: ignore[arg-type]
    assert [(r["code"], r["action"]) for r in rows] == [("AAA", "hold_back")]
    assert rows[0]["size_pct"] is None                       # nothing is being sized: the gate refused it
    assert "200-day average" in rows[0]["reason"]["why"]
    assert meta["regime"]["on"] is False                     # the card can say why without re-deriving it


def test_an_empty_trend_card_says_why_rather_than_going_silent(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_trend(monkeypatch, gate_on=True)
    import blackheart_ingest.idx.trend_book as real
    monkeypatch.setattr(real, "entry_signals", staticmethod(lambda hist, d: []))
    rows, meta = sb.trend_rows(None, D, "small")             # type: ignore[arg-type]
    assert rows == [] and meta["why"] == "no name made a new 60-day high on volume"


def _fake_candidates(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [{"code": "AAA", "price": Decimal(1000), "rank": 1}, {"code": "BBB", "price": Decimal(2000), "rank": 2}]
    monkeypatch.setattr(sb, "_candidate_rows", lambda conn, d: (rows, date(2026, 9, 24)))
    import blackheart_ingest.idx.strategies as st
    monkeypatch.setattr(st, "pick", lambda key, rs, size=None, weight=None: [
        {**r, "selected": True, "weight": Decimal("0.5"), "strategy_rank": i + 1} for i, r in enumerate(rs)])


def test_the_annual_list_is_a_hold_outside_its_may_window(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_candidates(monkeypatch)
    rows, meta = sb.value_rows(None, date(2026, 9, 24))      # type: ignore[arg-type]
    assert {r["action"] for r in rows} == {"hold"}           # September: the list is a target, not an order
    assert meta["in_window"] is False and meta["next_window"] == "May 2027"
    assert "May window" in rows[0]["reason"]["why"]
    assert rows[0]["size_pct"] == Decimal("50.0")            # weight 0.5 -> 50 % of NAV


def test_the_annual_list_becomes_a_buy_inside_the_may_window(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_candidates(monkeypatch)
    rows, meta = sb.value_rows(None, date(2027, 5, 4))       # type: ignore[arg-type]
    assert {r["action"] for r in rows} == {"buy"}
    assert meta["in_window"] is True and meta["next_window"] == "May 2027"
    assert rows[0]["reason"]["why"] is None


def test_value_card_reports_a_missing_candidate_run_instead_of_an_empty_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sb, "_candidate_rows", lambda conn, d: ([], None))
    rows, meta = sb.value_rows(None, D)                      # type: ignore[arg-type]
    assert rows == [] and meta["run_date"] is None and "no candidate run" in meta["why"]


def test_combined_halves_each_sleeve_and_tags_where_a_row_came_from(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_candidates(monkeypatch)
    _patch_trend(monkeypatch, gate_on=True)
    rows, meta = sb.combined_rows(None, D)                   # type: ignore[arg-type]
    sleeves = {r["code"]: r["reason"]["sleeve"] for r in rows}
    assert sleeves == {"AAA": "trend 50 %", "BBB": "value 50 %"} or sleeves["BBB"] == "value 50 %"
    value = next(r for r in rows if r["reason"]["sleeve"] == "value 50 %")
    trend = next(r for r in rows if r["reason"]["sleeve"] == "trend 50 %")
    assert value["size_pct"] == Decimal("25.0")              # 50 % of NAV in the sleeve, half the money in it
    assert trend["size_pct"] == Decimal("5.00")              # one of ten trend slots, halved
    assert meta["value"]["run_date"] == "2026-09-24" and meta["trend"]["slots"] == 10


def test_one_broken_engine_does_not_blank_the_board(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(conn: Any, key: str, d: date) -> Any:
        if key == "gapfade":
            raise RuntimeError("the feed is down")
        return ([], {"why": "nothing"})
    monkeypatch.setattr(sb, "rows_for", boom)
    import blackheart_ingest.idx.registry as reg
    monkeypatch.setattr(reg, "books_following", lambda conn, key: [])
    res = sb.build(None, D)                                  # type: ignore[arg-type]
    cards = {c["key"]: c for c in res["strategies"]}
    assert cards["gapfade"]["error"] == "the feed is down"   # named, not silently empty
    assert len(res["strategies"]) == 5 and res["as_of"] == "2026-09-24"
    assert all(c["by_action"] == {} for c in res["strategies"])


def test_render_names_every_card_and_the_books_that_follow_it(monkeypatch: pytest.MonkeyPatch) -> None:
    res = {"as_of": "2026-09-24", "strategies": [
        {**sb.BY_KEY["trend_small"], "books": [{"book": "trend_live"}], "error": None, "by_action": {"buy": 1},
         "meta": {}, "rows": [{"code": "AAA", "action": "buy", "ref_price": Decimal(500), "size_pct": Decimal(10),
                               "reason": {"why": "breakout"}}]},
        {**sb.BY_KEY["gapfade"], "books": [], "error": None, "by_action": {}, "rows": [],
         "meta": {"why": "the market is closed"}}]}
    out = sb.render(res)
    assert "trend_live" in out and "AAA" in out and "10.0%" in out
    assert "nothing today: the market is closed" in out
