"""Strategy catalog: picking and weighting (pure) and the research-output -> history mapping (pure)."""
from __future__ import annotations

from decimal import Decimal

import pytest

from blackheart_ingest.idx import strategies as ST
from blackheart_ingest.idx.candidates import rank_pool


def _rows(n: int = 40) -> list[dict]:
    out = []
    for i in range(n):
        out.append({"code": f"S{i:02d}", "ep": Decimal(f"0.{40 - i:02d}"), "bp": Decimal("0.5") + Decimal(i) / 100,
                    "dy": Decimal("0.0") + Decimal(i % 7) / 100, "np_yoy": Decimal(i - 20) / 10, "mom": Decimal(20 - i) / 20,
                    "gate_loose": True, "gate_strict": i % 3 != 0, "sector": "X"})
    out[5]["mom"] = None                                                   # one name without a momentum figure
    return out


def test_rule_matches_rank_pool_and_sizes_cut_the_selection() -> None:
    rows = _rows()
    base = rank_pool([dict(r) for r in rows])
    picked = ST.pick("rule", rows)
    assert [r["code"] for r in picked] == [r["code"] for r in base]
    assert [r["selected"] for r in picked] == [r["selected"] for r in base]
    n = sum(r["selected"] for r in picked)
    assert n == 10 and all(r["weight"] == Decimal(1) / 10 for r in picked if r["selected"])
    ten = ST.pick("rule", rows, size=10)
    fifteen = ST.pick("rule", rows, size=15)
    assert sum(r["selected"] for r in ten) == 10 and sum(r["selected"] for r in fifteen) == 10     # the fifth is only 10 here
    assert [r["code"] for r in ten if r["selected"]] == [r["code"] for r in picked if r["selected"]][:10]


def test_strict_family_orders_its_own_pool() -> None:
    rows = _rows()
    picked = ST.pick("strict", rows, size=10)
    assert all(r["gate_strict"] for r in picked) and sum(r["selected"] for r in picked) == 10
    assert [r["strategy_rank"] for r in picked] == list(range(1, len(picked) + 1))


def test_feature_families_order_the_rules_fifth() -> None:
    rows = _rows()
    fifth = {r["code"] for r in ST.pick("rule", rows) if r["selected"]}
    mom = ST.pick("momentum", rows, size=5)
    assert {r["code"] for r in mom} <= fifth                                # only names from the rule's list
    chosen = [r for r in mom if r["selected"]]
    assert len(chosen) == 5 and all(chosen[i]["mom"] >= chosen[i + 1]["mom"] for i in range(4))
    assert "S05" not in {r["code"] for r in chosen}                         # no momentum figure -> never chosen
    growth = [r for r in ST.pick("growth", rows, size=3) if r["selected"]]
    assert all(growth[i]["np_yoy"] >= growth[i + 1]["np_yoy"] for i in range(2))
    value = [r for r in ST.pick("value", rows, size=3) if r["selected"]]
    assert all(value[i]["ep"] >= value[i + 1]["ep"] for i in range(2))


def test_weight_schemes() -> None:
    codes = [f"C{i}" for i in range(10)]
    eq, top, rank = ST.weights(codes, "eq"), ST.weights(codes, "top5x2"), ST.weights(codes, "rank")
    for w in (eq, top, rank):
        assert abs(sum(w.values()) - 1) < Decimal("1e-12")
    assert eq["C0"] == Decimal(1) / 10
    assert top["C0"] == 2 * top["C9"] and top["C4"] == top["C0"] and top["C5"] == top["C9"]
    assert rank["C0"] == Decimal(10) / 55 and rank["C9"] == Decimal(1) / 55
    lead = [r for r in ST.pick("momentum_rank", _rows(), size=10) if r["selected"]]
    n = len(lead)                                                          # 9: the fifth is 10 names, one has no momentum
    assert n == 9 and lead[0]["weight"] == Decimal(n) / (n * (n + 1) // 2) and lead[-1]["weight"] == Decimal(1) / (n * (n + 1) // 2)
    assert ST.weights([], "eq") == {}
    with pytest.raises(ValueError):
        ST.pick("nope", _rows())


def test_history_rows_from_both_research_formats() -> None:
    rev3 = {"generated": "2026-09-12T12:00:00+00:00",
            "months": {"5": {"n_trials": 13, "summary": {
                "composite_qloose": {"total_pct": 106.4, "cagr_pct": 14.5, "sharpe": 0.83, "mdd_pct": 21.8, "dsr": 0.56, "psr": 0.97,
                                     "from": "2021-05-04", "yearly": {"2021": 12.0}, "periods": {"2021-05-03": 31.0},
                                     "holdings": [{"date": "2021-05-03", "n": 10, "names": ["A"]}]},
                "bench": {"total_pct": 46.6, "cagr_pct": 7.4, "sharpe": 0.37, "mdd_pct": 43.7, "yearly": {"2021": 19.0}}}}},
            "benchmarks": {"IDXV30": {"total_pct": 0.0, "cagr_pct": 0.0, "sharpe": 0.0, "mdd_pct": 38.2, "yearly": {"2021": 3.0}}}}
    rows = ST.history_rows_from_json(rev3)
    by = {(r["strategy"], r["size"], r["month"]): r for r in rows}
    assert by[("rule", 0, 5)]["stats"]["total_pct"] == 106.4 and by[("rule", 0, 5)]["n_trials"] == 13
    assert by[("rule", 0, 5)]["holdings"][0]["names"] == ["A"]
    assert by[("bench", 0, 5)]["stats"]["cagr_pct"] == 7.4 and by[("index:IDXV30", 0, 5)]["stats"]["mdd_pct"] == 38.2
    topn = {"generated": "2026-09-12T13:00:00+00:00", "n_trials": 32, "size": 10,
            "months": {"2": {"table": {"strict/eq": {"total_pct": 132.3, "cagr_pct": 20.1, "sharpe": 1.05, "mdd_pct": 26.0, "dsr": 0.52,
                                                     "psr": 0.99, "yearly": {"2022": 16.0}, "periods": {"2022-02-02": 16.0},
                                                     "holdings": {"2022-02-02": ["X", "Y"]}},
                                       "momentum/rank": {"total_pct": 193.6, "cagr_pct": 26.4, "sharpe": 1.07, "mdd_pct": 27.0}}}}}
    rows = ST.history_rows_from_json(topn)
    by = {(r["strategy"], r["size"], r["month"]): r for r in rows}
    assert by[("strict", 10, 2)]["holdings"] == [{"date": "2022-02-02", "n": 2, "names": ["X", "Y"]}]
    assert by[("momentum_rank", 10, 2)]["stats"]["total_pct"] == 193.6 and by[("momentum_rank", 10, 2)]["n_trials"] == 32
    assert ("rule", 10, 2) not in by                                        # not in that table -> no row


def test_strict_cash_adds_cash_conversion_as_a_fourth_rank() -> None:
    rows = _rows()
    for i, r in enumerate(rows):
        r["conv"] = Decimal(i) / 10                                        # the cheapest names convert the least cash
    strict = [r["code"] for r in ST.pick("strict", rows) if r["selected"]]
    cash = ST.pick("strict_cash", rows)
    chosen = [r["code"] for r in cash if r["selected"]]
    assert all(r["gate_strict"] for r in cash) and len(chosen) == len(strict)
    assert chosen != strict and "rank_conv" in cash[0]                    # the fourth rank moved the list
    assert all(r["score"] == r["rank_ep"] + r["rank_bp"] + r["rank_dy"] + r["rank_conv"] for r in cash)
    assert ST.get("strict")["status"] == "deployed" and ST.get("rule")["status"] == "baseline"


def test_history_rows_from_the_cash_conversion_format() -> None:
    doc = {"generated": "2026-09-12T16:00:00+00:00", "n_trials": 71, "verdict": {"strict+conv": {"adopt": True}},
           "months": {"5": {"table": {"strict": {"total_pct": 146.4, "trial": False},
                                      "strict+conv": {"total_pct": 263.0, "cagr_pct": 27.2, "sharpe": 1.16, "mdd_pct": 27.0, "dsr": 0.57,
                                                      "psr": 0.99, "yearly": {"2021": 40.0}, "periods": {"2021-05-03": 56.0},
                                                      "holdings": {"2021-05-03": ["A", "B"]}},
                                      "strict10+conv": {"total_pct": 273.7, "cagr_pct": 27.9, "sharpe": 1.11, "mdd_pct": 30.0}}}}}
    by = {(r["strategy"], r["size"], r["month"]): r for r in ST.history_rows_from_json(doc)}
    assert by[("strict_cash", 0, 5)]["stats"]["total_pct"] == 263.0 and by[("strict_cash", 0, 5)]["n_trials"] == 71
    assert by[("strict_cash", 0, 5)]["holdings"] == [{"date": "2021-05-03", "n": 2, "names": ["A", "B"]}]
    assert by[("strict_cash", 10, 5)]["stats"]["mdd_pct"] == 30.0
    assert ("strict", 0, 5) not in by                                        # reference lines are not re-imported


def test_history_rows_from_the_overlay_format() -> None:
    doc = {"generated": "2026-09-13T01:00:00+00:00", "n_trials": 83,
           "part_a": {"table": {}},
           "part_b": {"5": {"table": {"none": {"total_pct": 107.0, "sharpe": 1.11, "mdd_pct": 18.0},
                                      "index": {"total_pct": 66.0, "cagr_pct": 9.9, "sharpe": 1.03, "mdd_pct": 14.0, "yearly": {"2021": 10.0}},
                                      "entry_only": {"total_pct": 131.0, "sharpe": 1.18, "mdd_pct": 15.0}}}}}
    by = {(r["strategy"], r["size"], r["month"]): r for r in ST.history_rows_from_json(doc)}
    assert by[("overlay:regime", 0, 5)]["stats"]["total_pct"] == 66.0 and by[("overlay:regime", 0, 5)]["n_trials"] == 83
    assert by[("overlay:entry_gate", 0, 5)]["stats"]["total_pct"] == 131.0 and by[("overlay:none", 0, 5)]["stats"]["mdd_pct"] == 18.0
    cat = ST.catalog()
    assert {s["key"] for s in cat} >= {"overlay:regime", "overlay:entry_gate"} and ST.get_any("overlay:regime")["status"] == "option"
