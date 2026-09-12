"""Pure parts of the value/quality candidate list: TTM arithmetic, gates, warnings, composite ranking."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from blackheart_ingest.idx.candidates import MIN_NAMES, board_from_remarks, rank_pool
from blackheart_ingest.idx.metrics import COLS, evaluate, prior_from_yoy


def _row(**kw):
    base = dict.fromkeys(COLS)
    base.update({"code": "T", "pub": datetime(2026, 3, 1), "sector": "B. Basic Materials", "currency": "IDR"})
    base.update(kw)
    return base


A = _row(period_end=date(2025, 12, 31), label="TAHUNAN", months=12, net_profit=Decimal(100), revenue=Decimal(1000),
         equity=Decimal(800), debt=Decimal(200), cfo=Decimal(120), roe=Decimal("0.125"), der=Decimal("0.25"),
         np_yoy=Decimal("0.25"), rev_yoy=Decimal("0.10"))
Q = _row(period_end=date(2026, 6, 30), label="TW2", months=6, pub=datetime(2026, 7, 30), net_profit=Decimal(60),
         revenue=Decimal(550), equity=Decimal(830), debt=Decimal(210), np_yoy=Decimal("0.20"), rev_yoy=Decimal("0.10"))


def test_prior_from_yoy() -> None:
    assert prior_from_yoy(Decimal(120), Decimal("0.2")) == Decimal(100)
    assert prior_from_yoy(Decimal(120), Decimal(-1)) is None
    assert prior_from_yoy(None, Decimal(1)) is None
    # a profit with yoy > 1 is ambiguous (strong growth or a turnaround from a loss): never guess
    assert prior_from_yoy(Decimal(100), Decimal(3)) is None
    # a loss whose comparative was also a loss: (-30 - (-50)) / 50 = 0.4 -> -50 ; (-100 - (-50)) / 50 = -1 -> -50
    assert prior_from_yoy(Decimal(-30), Decimal("0.4")) == Decimal(-50)
    assert prior_from_yoy(Decimal(-100), Decimal(-1)) == Decimal(-50)
    # a loss after a profit (yoy < -1) is ambiguous too
    assert prior_from_yoy(Decimal(-30), Decimal("-1.6")) is None


def test_stored_comparative_beats_the_ratio() -> None:
    a = dict(A, np_yoy=Decimal(3), np_prior=Decimal(-50))          # turnaround: the prior loss is carried by the report
    m = evaluate("T", a, None)
    assert m["net_profit_prior"] == Decimal(-50) and "prior_year_loss" in m["strict_fails"]
    m = evaluate("T", dict(A, np_yoy=Decimal(3)), None)              # no stored comparative -> unknown, still fails strict
    assert m["net_profit_prior"] is None and "prior_year_unknown" in m["strict_fails"]
    q = dict(Q, np_yoy=Decimal(5), np_prior=Decimal(-20))            # H1 2025 was a loss of 20: TTM = 100 + 60 + 20
    assert evaluate("T", A, q)["net_profit_ttm"] == Decimal(180)
    assert "scale_mismatch" in evaluate("T", dict(A, flags=["scale_mismatch"]), None)["warnings"]


def test_ttm_combines_annual_and_quarter() -> None:
    m = evaluate("T", A, Q)
    # FY 100 + H1 2026 60 - H1 2025 (60 / 1.2 = 50) = 110
    assert m["net_profit_ttm"] == Decimal(110)
    assert m["revenue_ttm"] == Decimal(1000) + Decimal(550) - Decimal(500)
    assert m["ttm_basis"] == "FY2025 + TW2 2026 YTD"
    assert m["equity_latest"] == Decimal(830)
    assert m["gate_loose"] and m["gate_strict"] and m["strict_fails"] == [] and m["warnings"] == []


def test_annual_only_and_quarter_only() -> None:
    m = evaluate("T", A, None)
    assert m["net_profit_ttm"] == Decimal(100) and m["ttm_basis"] == "FY2025"
    m = evaluate("T", None, Q)
    assert not m["gate_loose"] and m["strict_fails"] == ["no_audited_report"] and m["ttm_basis"] == "TW2 2026 only"


def test_strict_gate_reasons_and_financial_exemption() -> None:
    a = dict(A, roe=Decimal("0.07"), cfo=Decimal(-5), der=Decimal("2.0"), np_yoy=Decimal(3), np_prior=Decimal(-50))   # prior year was a loss
    m = evaluate("T", a, None)
    assert m["gate_loose"] and not m["gate_strict"]
    assert m["strict_fails"] == ["roe<10%", "prior_year_loss", "cfo<=0", "der>1.5"]
    bank = dict(a, sector="G. Financials", der=Decimal("6.0"), roe=Decimal("0.15"), cfo=Decimal(1), np_yoy=Decimal("0.1"), np_prior=None)
    assert evaluate("B", bank, None)["strict_fails"] == []
    assert not evaluate("L", dict(A, net_profit=Decimal(-1)), None)["gate_loose"]


def test_warnings_from_latest_quarter() -> None:
    q = dict(Q, net_profit=Decimal(-30), np_yoy=Decimal("-1.6"), np_prior=Decimal(50))
    m = evaluate("T", A, q)
    assert m["net_profit_ttm"] == Decimal(100) + Decimal(-30) - Decimal(50)    # 20
    assert "latest_quarter_ytd_loss" in m["warnings"] and "ytd_profit_down_>50%" in m["warnings"]
    q2 = dict(Q, net_profit=Decimal(-120), np_yoy=Decimal("-3"), np_prior=Decimal(40))
    assert "ttm_loss" in evaluate("T", A, q2)["warnings"]


def _c(code, ep, bp, dy, loose=True):
    return {"code": code, "ep": Decimal(ep), "bp": Decimal(bp), "dy": Decimal(dy), "gate_loose": loose}


def test_rank_pool_composite_and_minimum() -> None:
    rows = [_c(f"C{i:02d}", f"0.{i + 1:02d}", f"0.{(i * 7) % 50 + 10:02d}", f"0.0{i % 9}") for i in range(30)]
    rows.append(_c("XX", "0.99", "9", "0.5", loose=False))          # cheapest of all but fails the gate
    rows.append(_c("NEG", "-0.10", "9", "0.5"))                      # E/P <= 0 never ranks
    pool = rank_pool(rows)
    assert len(pool) == 30 and all(r["code"] not in ("XX", "NEG") for r in pool)
    assert sum(r["selected"] for r in pool) == max(MIN_NAMES, 30 // 5)      # 10
    assert [r["rank"] for r in pool] == list(range(1, 31))
    assert pool[0]["score"] >= pool[1]["score"] >= pool[-1]["score"]
    small = rank_pool([_c(f"S{i}", "0.1", "0.5", "0.02") for i in range(MIN_NAMES - 1)])
    assert small and not any(r["selected"] for r in small)


def test_rank_pool_average_ranks_and_determinism() -> None:
    rows = [_c(f"D{i:02d}", f"0.{10 + i:02d}", "0.5", "0") for i in range(25)]          # every DY = 0: one tie group
    rows[0]["dy"] = Decimal("0.05")
    pool = rank_pool(rows)
    tied = [r["rank_dy"] for r in pool if r["dy"] == 0]
    assert len(set(tied)) == 1 and tied[0] == Decimal(25) / 2            # positions 1..24 share 12.5
    assert max(r["rank_dy"] for r in pool) == 25                           # the one payer ranks 25
    assert pool[0]["code"] == "D24"                                        # highest E/P + tied B/P + tied DY wins
    again = rank_pool([dict(r) for r in reversed(rows)])
    assert [r["code"] for r in again] == [r["code"] for r in pool]      # input (DB row) order never matters
    missing = rank_pool([_c("M", "0.2", "0.5", "0.01"), {**_c("N", "0.1", "0.5", "0.01"), "bp": None}])
    assert next(r for r in missing if r["code"] == "N")["rank_bp"] < next(r for r in missing if r["code"] == "M")["rank_bp"]


def test_rank_pool_pool_floor_gate_and_sector_cap() -> None:
    rows = [_c(f"P{i:02d}", f"0.{30 - i:02d}", "0.5", "0.01") for i in range(19)]
    assert not any(r["selected"] for r in rank_pool(rows))               # 19 < MIN_POOL -> cash
    rows += [_c("P19", "0.11", "0.5", "0.01"), _c("P20", "0.10", "0.5", "0.01")]
    assert sum(r["selected"] for r in rank_pool(rows)) == MIN_NAMES        # 21 -> max(10, 4)
    for i, r in enumerate(rows):
        r["gate_strict"] = i % 2 == 0
        r["sector"] = "A. Energy" if i < 12 else ("G. Financials" if i < 17 else "C. Industrials")
        r["tradable"] = i != 0
    strict = rank_pool(rows, gate="strict")
    assert all(r["gate_strict"] for r in strict) and len(strict) == 10 and not any(r["selected"] for r in strict)
    everyone = rank_pool(rows, gate=None)
    assert "P00" not in {r["code"] for r in everyone} and len(everyone) == 20   # no trade that day -> not buyable
    capped = rank_pool(rows, sector_cap=1 / 3)
    chosen = [r for r in capped if r["selected"]]
    assert len(chosen) == MIN_NAMES and sum(r["sector"] == "A. Energy" for r in chosen) == 4    # ceil(10 / 3) = 4 per sector
    assert sum(r["sector"] == "G. Financials" for r in chosen) == 4 and sum(r["sector"] == "C. Industrials" for r in chosen) == 2
    assert [r["rank"] for r in capped] == list(range(1, 21))               # ranks are positions; the cap only changes selection


def test_board_from_remarks() -> None:
    assert board_from_remarks("--U-1805580000E413M-----------") == "Utama"
    assert board_from_remarks("--UO2130000000H111------------") == "Pengembangan"
    assert board_from_remarks("--U-4105000000E413ME-L-------X") == "Pemantauan Khusus"
    assert board_from_remarks("--U-3000000000E211------------") == "Akselerasi"
    assert board_from_remarks(None) is None and board_from_remarks("--U") is None
