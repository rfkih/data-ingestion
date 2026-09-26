"""Phase 0 (2026-09-26): the pre-registered kill rules (idx/killrules.py) and the combo book freeze (combo_book.freeze_*)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import numpy as np

from blackheart_ingest.idx import combo_book as cb
from blackheart_ingest.idx import killrules as kr


def test_closed_trades_average_cost_fees_and_partial_sells() -> None:
    fills = [
        {"code": "AAAA", "side": "buy", "flags": ["sleeve:ml"], "trade_date": date(2026, 10, 1), "lots": 10, "price": 1000, "fee": 1500},
        {"code": "AAAA", "side": "buy", "flags": ["sleeve:ml"], "trade_date": date(2026, 10, 2), "lots": 10, "price": 1200, "fee": 1800},
        {"code": "AAAA", "side": "sell", "flags": ["sleeve:ml"], "trade_date": date(2026, 10, 9), "lots": 10, "price": 1320, "fee": 3300},
        {"code": "AAAA", "side": "sell", "flags": ["sleeve:ml"], "trade_date": date(2026, 10, 10), "lots": 10, "price": 990, "fee": 2475},
        {"code": "BBBB", "side": "sell", "flags": ["sleeve:gap"], "trade_date": date(2026, 10, 10), "lots": 5, "price": 500, "fee": 0},
    ]
    t = kr.closed_trades(fills, cb.sleeve_of)
    assert [x["code"] for x in t] == ["AAAA", "AAAA"]                   # a sell with nothing held is not a trade
    cost_half = (Decimal(1_000_000) + 1500 + Decimal(1_200_000) + 1800) / 2
    assert abs(t[0]["ret"] - float((Decimal(1_320_000) - 3300) / cost_half - 1)) < 1e-12
    assert abs(t[1]["ret"] - float((Decimal(990_000) - 2475) / cost_half - 1)) < 1e-12
    assert t[0]["d_in"] == date(2026, 10, 1) and t[0]["sleeve"] == "ml"


def test_edge_check_needs_min_n_then_compares_to_band() -> None:
    ref = np.random.default_rng(1).normal(0.04, 0.10, 500)
    assert kr.edge_check("trend", [0.01] * 5, ref)["status"] == "insufficient"
    ok = kr.edge_check("trend", [0.04] * 20, ref)
    assert ok["status"] == "ok" and 30 < ok["pct"] < 70
    bad = kr.edge_check("trend", [-0.05] * 20, ref)
    assert bad["status"] == "breach" and bad["live_mean"] < bad["band"] and bad["pct"] < 5
    assert kr.edge_check("gap", [0.1] * 30, np.array([]))["status"] == "no_reference"


def test_band_is_deterministic_and_widens_with_fewer_trades() -> None:
    ref = np.random.default_rng(2).normal(0.03, 0.08, 300)
    assert kr.mean_band(ref, 20) == kr.mean_band(ref, 20)
    assert kr.mean_band(ref, 10) < kr.mean_band(ref, 40) < ref.mean()


def test_fill_slip_ic_dd_checks() -> None:
    assert kr.fill_check("ml", 9, 1)["status"] == "insufficient"
    assert kr.fill_check("ml", 10, 7)["status"] == "breach" and kr.fill_check("ml", 10, 8)["status"] == "ok"
    assert kr.slip_check("gap", [60.0] * 9)["status"] == "insufficient"
    assert kr.slip_check("gap", [60.0] * 10)["status"] == "breach" and kr.slip_check("gap", [40.0] * 10)["status"] == "ok"
    assert kr.ic_check([-0.01] * 7)["status"] == "insufficient"
    assert kr.ic_check([-0.01] * 8 + [0.02] * 4)["status"] == "breach"            # 8/12 negative > 60 %
    assert kr.ic_check([-0.01] * 7 + [0.02] * 5)["status"] == "ok"                # 7/12 = 58 %
    assert kr.dd_check([])["status"] == "insufficient"
    assert kr.dd_check([100, 120, 95])["status"] == "ok"
    assert kr.dd_check([100, 120, 89])["status"] == "warning"
    w = kr.dd_check([100, 120, 80, 83])
    assert w["status"] == "breach" and round(w["mdd"], 4) == round(80 / 120 - 1, 4)


def test_twin_gap_sign() -> None:
    assert cb.twin_gap_bps("buy", Decimal(1010), Decimal(1000)) == 100.0          # paid more than the twin
    assert cb.twin_gap_bps("sell", Decimal(990), Decimal(1000)) == 100.0          # got less than the twin
    assert cb.twin_gap_bps("buy", Decimal(990), Decimal(1000)) == -100.0


FROZEN = {"rule": "combo", "regime_filter": True,
          "params": {"sleeves": {"ml": 0.1, "gap": 0.1, "trend": 0.05}, "cash_floor": 0.3, "twin": "paper-x",
                     "freeze": {"since": "2026-09-26", "until": "2027-03-26", "reason": "phase 0"}}}


def _params(**kw):
    p = {k: (dict(v) if isinstance(v, dict) else v) for k, v in FROZEN["params"].items()}
    p.update(kw)
    return p


def test_freeze_blocks_config_allows_off_and_admin() -> None:
    d = date(2026, 10, 1)
    assert cb.freeze_of(FROZEN["params"], d) and cb.freeze_of(FROZEN["params"], date(2027, 3, 27)) is None
    assert cb.freeze_violations(FROZEN, {"params": _params(sleeves={"ml": 0.05, "gap": 0.1, "trend": 0.05})}, d) == ["params"]
    assert cb.freeze_violations(FROZEN, {"params": _params(off=["gap"])}, d) == []                   # a kill rule's action
    assert cb.freeze_violations(FROZEN, {"cash": 25_000_000, "note": "top-up", "label": "x"}, d) == []
    assert cb.freeze_violations(FROZEN, {"regime_filter": False}, d) == ["regime_filter"]
    assert "params.freeze" in cb.freeze_violations(FROZEN, {"params": {k: v for k, v in _params().items() if k != "freeze"}}, d)
    was_off = {**FROZEN, "params": _params(off=["gap"])}
    assert cb.freeze_violations(was_off, {"params": _params(off=[])}, d) == ["params.off (a sleeve back on)"]
    assert cb.freeze_violations(FROZEN, {"params": _params(cash_floor=0.1)}, date(2027, 4, 1)) == []  # expired
    assert cb.freeze_violations({**FROZEN, "rule": "annual"}, {"regime_filter": False}, d) == []      # combo books only
