"""Trend book: the pure rule (entries, exits, sizing) on synthetic data, then a round trip on a paper test book (build -> store ->
issue -> validate) and the is_live/is_paper split that the two-key rule now keys off."""
from __future__ import annotations

import os
from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
import psycopg
import pytest

from blackheart_ingest.idx import book, ticket, trend_book

D = date(2026, 9, 16)
BOOK = {"fee_buy_pct": Decimal("0.10"), "fee_sell_pct": Decimal("0.20"), "cash": Decimal(100_000_000)}


def _hist(code, closes, vols):
    n = len(closes)
    days = [D - timedelta(days=int((n - 1 - i) * 1.45)) for i in range(n)]
    days[-1] = D
    return pd.DataFrame({"code": code, "trade_date": days, "adj": closes, "volume": vols})


def test_entry_signals_breakout_above_ma200_on_volume() -> None:
    up = [100 + i * 0.5 for i in range(220)]                 # rising: today is a 60-day high, above MA200
    vol = [1_000_000] * 219 + [2_000_000]                    # 2x median volume today
    flat = [100.0] * 220
    h = pd.concat([_hist("UPUP", up, vol), _hist("FLAT", flat, vol), _hist("LOWV", up, [1_000_000] * 220), _hist("SHRT", up[-100:], vol[-100:])])
    sig = trend_book.entry_signals(h, D)
    assert [s["code"] for s in sig] == ["UPUP"] and sig[0]["vol_ratio"] == 2.0                    # FLAT: not a high above MA; LOWV: no volume; SHRT: < 200 bars
    assert trend_book.entry_signals(h, D - timedelta(days=1)) == []                                # no bar on that date


def test_exit_signals_trailing_stop_and_no_bar() -> None:
    pos = [{"code": "A", "lots": Decimal(10), "avg_price": Decimal(1000)}, {"code": "B", "lots": Decimal(5), "avg_price": Decimal(500)},
           {"code": "C", "lots": Decimal(7), "avg_price": Decimal(300)}]
    closes = {"A": Decimal(1100), "B": Decimal(449)}
    peaks = {"A": Decimal(1200), "B": Decimal(500)}
    ex = trend_book.exit_signals(pos, closes, peaks)
    assert [x["code"] for x in ex] == ["B", "C"]                                                   # A: 1100 > 90 % of 1200; B: 449 <= 450; C: no bar
    assert "trailing stop" in ex[0]["reason"] and "no bar" in ex[1]["reason"]


def test_plan_sizes_slots_and_respects_cash() -> None:
    entries = [{"code": "X", "vol_ratio": 3.0}, {"code": "Y", "vol_ratio": 2.0}, {"code": "Z", "vol_ratio": 1.6}]
    closes = {"X": Decimal(1000), "Y": Decimal(200), "Z": Decimal(5000), "H": Decimal(400)}
    positions = [{"code": "H", "lots": Decimal(100), "avg_price": Decimal(380)}]                  # Rp 4 M held
    res = trend_book.plan(entries, [], positions, closes, Decimal(BOOK["cash"]), BOOK, k=10)
    assert res["nav"] == Decimal(104_000_000) and [ln["side"] for ln in res["lines"]] == ["buy"] * 3
    x = res["lines"][0]
    assert x["code"] == "X" and x["limit_price"] == Decimal(1005) and x["lots"] == Decimal(103)     # slot 10.4 M / (1005 x 100 x 1.001)
    assert res["cash_after"] < Decimal(BOOK["cash"]) and res["targets"] == ["X", "Y", "Z", "H"]
    # an exit frees cash before buys; a stopped name sells at its average when it has no close
    big = [{"code": "H", "lots": Decimal(1000), "avg_price": Decimal(380)}]                         # Rp 40 M held, cash 1 M
    ex = [{"code": "H", "lots": Decimal(1000), "reason": "trailing stop", "close": Decimal(400)}]
    res2 = trend_book.plan(entries, ex, big, closes, Decimal(60_000_000), BOOK, k=10)
    assert res2["lines"][0]["side"] == "sell" and res2["lines"][0]["limit_price"] == Decimal(398)
    assert sum(1 for ln in res2["lines"] if ln["side"] == "buy") >= 1                             # NAV 100 M: slot 10 M, funded by cash + the sale
    tiny = trend_book.plan(entries, [], [], closes, Decimal(20_000_000), BOOK, k=10)               # slot 2 M: sized as 1/K, never above the slot
    assert tiny["lines"] and all(ln["notional"] <= Decimal(2_000_000) for ln in tiny["lines"]) and tiny["cash_after"] > 0
    dust = trend_book.plan(entries, [], [], closes, Decimal(400_000), BOOK, k=10)                   # slot 40 k: Z @ 5,000 cannot buy a lot; X/Y can
    assert [ln["code"] for ln in dust["lines"]] == ["Y"] and all(ln["lots"] >= 1 for ln in dust["lines"])   # X: one lot (100 k) > slot


def test_live_paper_split() -> None:
    assert ticket.is_live("live") and ticket.is_live("trend_live") and ticket.is_live("LIVE_x")
    assert not ticket.is_live("paper") and not ticket.is_live("paper_trend") and not ticket.is_live("test_guard")
    assert ticket.is_paper("paper_trend") and not ticket.is_paper("trend_live") and not ticket.is_paper("test_x")
    assert trend_book.variant_of({"note": "trend:small (Stockbit)"}) == "small" and trend_book.variant_of({"note": "trend:all"}) == "all"
    assert trend_book.variant_of({"note": "operator's positions"}) is None and trend_book.variant_of({"note": "trend:weird"}) == "small"
    assert trend_book.variant_of({"rule": "trend", "trend_variant": "all", "note": None}) == "all" and trend_book.variant_of({"rule": "trend"}) == "small"
    assert trend_book.variant_of({"rule": "annual", "note": "x"}) is None
    assert ticket.is_paper("paper-3fa9c1") and not ticket.is_live("paper-3fa9c1") and ticket.is_live("live-3fa9c1")


@pytest.fixture(scope="module")
def conn():
    dsn = os.environ.get("INGEST_DB_DSN")
    if not dsn:
        pytest.skip("INGEST_DB_DSN not set")
    try:
        c = psycopg.connect(dsn, connect_timeout=5)
    except Exception as e:
        pytest.skip(f"db unreachable: {e}")
    yield c
    c.close()


def _clean(conn, bk):
    with conn.cursor() as cur:
        cur.execute("DELETE FROM idx.ticket WHERE book = %s", (bk,))
        for t in ("book_mark", "book_nav", "position", "fill", "decision"):
            cur.execute(f"DELETE FROM idx.{t} WHERE book = %s", (bk,))
        cur.execute("DELETE FROM idx.alert WHERE job IN (%s, %s)", (f"book:{bk}", f"ticket:{bk}"))
        cur.execute("DELETE FROM idx.book WHERE book = %s", (bk,))
    conn.commit()


def test_round_trip_on_a_paper_test_book(conn) -> None:
    bk = "paper_test_trend"
    _clean(conn, bk)
    try:
        book.ensure_book(conn, bk, cash=Decimal(100_000_000), rule="trend", trend_variant="small", note="test", fee_buy_pct="0.10", fee_sell_pct="0.20",
                         max_weight_pct=15, max_sector_pct=40)
        with pytest.raises(ValueError, match="not a trend book"):
            trend_book.build(conn, "paper")
        res = trend_book.build(conn, bk, date(2026, 9, 16))
        assert res["mode"] == "trend" and res["variant"] == "small" and res["universe"] > 20 and res["nav"] == Decimal(100_000_000)
        assert all(ln["side"] == "buy" for ln in res["lines"]) and len(res["lines"]) <= trend_book.K
        rep = trend_book.run(conn, bk, actor="operator", d=date(2026, 9, 16))
        assert rep["book"] == bk and rep["signals"] == res["signals"]
        if rep["ticket"]:
            t = ticket.load(conn, rep["ticket"])
            assert t["mode"] == "trend" and t["status"] == "issued" and t["params"]["actor"] == "operator"     # paper: auto-issued
            v = ticket.validate(conn, rep["ticket"])
            assert v["ok"] and v["actor"] == "operator"
            assert rep["checks_ok"]
        assert bk in trend_book.trend_books(conn)
    finally:
        _clean(conn, bk)


def test_history_is_row_factory_agnostic(conn) -> None:
    """The API and the scheduler hand trend_book a dict_row connection; the bars must come back the same as on a plain one
    (2026-09-17: pandas' read_sql on dict rows produced a frame of column names and the nightly run saw no market)."""
    from psycopg.rows import dict_row
    d = trend_book._rows(conn, "SELECT max(trade_date) AS d FROM idx.bar WHERE source = 'idx'", (), ["d"])[0]["d"]
    codes = list(trend_book.universe(conn, d, "small"))[:5]
    if not codes:
        pytest.skip("no bars")
    plain = trend_book.history(conn, codes, d)
    with psycopg.connect(os.environ["INGEST_DB_DSN"], row_factory=dict_row) as c2:
        dicty = trend_book.history(c2, codes, d)
    assert len(plain) > 0 and plain["code"].nunique() == len(codes)
    assert len(dicty) == len(plain) and set(dicty["code"]) == set(plain["code"]) and dicty["adj"].notna().all()


def test_regime_gate_holds_back_new_entries_only() -> None:
    from blackheart_ingest.idx import overlay
    entries = [{"code": "AAAA", "vol_ratio": 2.0}, {"code": "BBBB", "vol_ratio": 1.6}]
    assert trend_book.hold_back(entries, True) == (entries, [])
    assert trend_book.hold_back(entries, False) == ([], ["AAAA", "BBBB"])                        # signals recorded, nothing bought
    assert overlay.regime_from_closes([100] * 200 + [90])["on"] is False                        # COMPOSITE under its 200-day average
    assert overlay.regime_from_closes([100] * 200 + [110])["on"] is True
    assert overlay.regime_from_closes([100] * 50)["on"] is True                                  # no history yet -> not a reason to sit out
