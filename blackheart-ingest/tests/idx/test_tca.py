"""Weekly TCA (idx/tca.py): the pure per-sleeve summary - fill rate, slippage and twin gap in bps and rupiah, missed winners."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from blackheart_ingest.idx import tca

T0 = datetime(2026, 10, 5, 21, 10)


def line(code, side, status, sleeve, ref, fill=None, lots=10, d=date(2026, 10, 6), skip=None):
    return {"ticket": 1, "ticket_date": d, "issued_at": T0, "code": code, "side": side, "ref_close": Decimal(ref), "status": status,
            "skip_reason": skip, "flags": [f"sleeve:{sleeve}"], "filled_lots": lots if fill else 0,
            "fill_price": Decimal(fill) if fill else None, "filled_at": T0 + timedelta(hours=13) if fill else None, "fill_date": d if fill else None}


def test_summary_in_bps_and_rupiah() -> None:
    lines = [line("AAAA", "buy", "filled", "ml", 1000, 1010),                       # paid 100 bps over the plan
             line("BBBB", "sell", "filled", "ml", 500, 495),                        # got 100 bps less
             line("CCCC", "buy", "skipped", "ml", 200, skip="missed: not executed on its day"),
             line("DDDD", "buy", "skipped", "trend", 300, skip="missed: not executed on its day")]
    twin = {("ml", "AAAA", "buy", date(2026, 10, 6)): Decimal(1000)}
    twin_pnl = {("ml", "CCCC", date(2026, 10, 6)): 150_000.0}
    s = tca.summarize(lines, twin, twin_pnl)
    ml = s["ml"]
    assert ml["lines"] == 3 and ml["filled"] == 2 and ml["missed"] == 1 and abs(ml["fill_rate"] - 2 / 3) < 1e-9
    assert abs(ml["slip_bps_mean"] - 100.0) < 1e-9
    assert abs(ml["slip_rp"] - (0.01 * 1010 * 10 * 100 + 0.01 * 495 * 10 * 100)) < 1e-6
    assert abs(ml["twin_bps_mean"] - 100.0) < 1e-9 and abs(ml["twin_rp"] - 0.01 * 1010 * 1000) < 1e-6
    assert ml["missed_twin"] == 1 and ml["missed_twin_rp"] == 150_000.0 and ml["delay_h_median"] == 13.0
    assert s["trend"]["missed_twin"] == 0 and s["trend"]["fill_rate"] == 0.0


def test_week_window_and_render() -> None:
    lines = [line("AAAA", "buy", "filled", "gap", 1000, 1000, d=date(2026, 9, 1)), line("BBBB", "buy", "filled", "gap", 1000, 1005)]
    s = tca.summarize(lines, {}, {}, since=date(2026, 10, 1))
    assert s["gap"]["lines"] == 1
    text = tca.render({"book": "live-x", "end": "2026-10-09", "week": s, "all": tca.summarize(lines, {}, {})})
    assert "[TCA mingguan] live-x" in text and "gap: 1/1 terisi" in text and "Sejak awal" in text


def test_vs_open_and_preopen_queue() -> None:
    a = line("AAAA", "buy", "filled", "trend", 1000, 1010, lots=10) | {"day_open": Decimal(1000)}     # paid 100 bps over the open
    b = line("BBBB", "sell", "filled", "trend", 500, 495, lots=20) | {"day_open": Decimal(500)}       # sold 100 bps under the open
    books = {("AAAA", date(2026, 10, 6)): {"off_px": [1005, 1010, 1015], "off_vol": [1000, 3000, 9999], "bid_px": [], "bid_vol": []},
             ("BBBB", date(2026, 10, 6)): {"bid_px": [500, 495, 490], "bid_vol": [5000, 5000, 5000], "off_px": [], "off_vol": []}}
    s = tca.summarize([a, b], {}, {}, books=books)["trend"]
    assert abs(s["open_bps_mean"] - 100.0) < 1e-9 and s["n_open_bps"] == 2
    # AAAA: 1,000 shares vs 4,000 offered at <= 1010 = 25 %; BBBB: 2,000 vs 10,000 bid at >= 495 = 20 %; median 22.5 %
    assert abs(s["queue_median"] - 0.225) < 1e-9 and s["n_queue"] == 2
    assert "vs open +100 bps" in tca.render({"book": "trend_live", "end": "2026-10-09", "week": {}, "all": {"trend": s}})


def test_unflagged_lines_take_the_default_sleeve() -> None:
    ln = line("AAAA", "buy", "filled", "x", 1000, 1000) | {"flags": ["trend:entry"]}
    assert set(tca.summarize([ln], {}, {}, default_sleeve="trend")) == {"trend"}
    assert tca.depth_within("buy", 100, None, None) is None
