#!/usr/bin/env python3
"""IDX ROI scorecard, built from the stored studies (2026-09-26). Replaces the hand-compiled study #102 (2026-09-23).

The Strategies page headline for most strategies is idx.strategy_state, which registry.refresh_scorecard() fills from the newest
idx.study named 'roi_scorecard'. #102 was typed by hand from #23, 46, 62, 63, 66, 77, 86, 87, 89, 91, 92, 93, 101, so when those
studies were re-run on the corrected data (2026-09-26) the headline kept the old numbers. This script rebuilds the same summary
(same keys, same row keys, same rounding) from an explicit per-row map: every figure names its source study and the JSON path
inside that study's summary. Nothing is typed except the constants in CONST, which have no idx.study row (menu 21 D dividend
variants, menu 27 dividend harvest, the live-book notes, the hand replication of the gap-fade events) and are marked as such.

Modes
  --as-of-originals   resolve every source to the ORIGINAL id #102 was built from (no idx.study_current). Must reproduce #102's
                      cagr / sharpe / mdd row by row; prints the diff table and stores nothing. This is the validation.
  (default)           resolve every source through idx.study_current (the newest re-run) and print the table vs #102.
  --store             with the default mode: store a new 'roi_scorecard' row and supersede the previous scorecard with it.

Statuses are derived from the source study's own verdict fields (see the status_* functions); the prose #102 carried is kept
only where the stored figures still say it.

INGEST_DB_DSN=... PYTHONIOENCODING=utf-8 blackheart-ingest/.venv/Scripts/python research/idx_roi_scorecard.py [--as-of-originals] [--store]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import date
from typing import Any

import psycopg
from psycopg.rows import dict_row

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "blackheart-ingest", "src"))

BASELINE = 102                       # the hand-compiled scorecard this reproduces / replaces
REASON = "rebuilt 2026-09-26 from the stored (re-run) studies by research/idx_roi_scorecard.py; #102 was compiled by hand"
GF_ARM = "deployed: -7 %, K=5, deepest"
TREND_LEAD = "lead 60/10/1.5"

# ------------------------------------------------------------------------------------------ constants (no idx.study row)
CONST = {
    # hand replication of the gap-fade event population (#102, 2026-09-23): not stored by any study
    "gapfade_events_by_year": {"2021": 2, "2022": 4, "2023": 11, "2024": 25, "2025": 186, "2026": 363},
    "gapfade_population_replicated": 591,
    "gapfade_full_span": ("2021-03-31", "2026-09-14", 5.46),   # first..last replicated event, years (#102 reconciliation)
    # menu 21 D (idx_beyond family D report, not stored as a study row): dividend-inclusive variants
    "ew3_with_dividends": {"cagr_pct": 14.2, "sharpe": 1.27},
    "gem_with_dividends": {"cagr_pct": 12.7},
    # IHSG 2020-05..2026-09: from the allocbook report (#92 did not store it; its re-run #352 does - used when present)
    "ihsg_2020_26": {"cagr_pct": 5.2, "sharpe": 0.41, "mdd_pct": -34.7},
    # menu 27 dividend harvest (no study row)
    "dividend_harvest": {"effect": "~+3 pp/yr, 3 names/day", "source": "menu 27", "status": "weak"},
    "ara_sell_book_effect": "est +1..3 pp/yr on a 10-name book",
    # live-book facts: operator state, not research results
    "live": {
        "gapfade_deployed": {"book": "paper_gapfade", "capital": 100000000, "sessions": "0/20"},
        "trend_small_gated": {"book": "trend_live", "capital": 10000000, "closed_trades": "0/60"},
        "trend_small": None,
        "combined_50_50_gated": "split 67/33 across IPOT+Stockbit",
        "book_gold_70_30": "parked by operator (equities only)",
        "value_strict": {"book": "live", "note": "archived by mis-tap 2026-09-18; un-archive pending", "names": 6, "broker": "IPOT",
                         "nav_est": 18971778, "only_strategy_with_real_fills": True},
        "trend_liq": None, "trend_small_2005_2019": None, "ew3_ihsg_sp_gold": "no book", "gem_idr": "no book",
    },
    "closed_static": ["ara_hunter #56 (0/24)", "ml_ara_predict #59", "swing 2-5d (46)", "bandarmologi (19)", "sideways/range #68 (15)",
                      "base breakout #69", "sleepers (0/8)", "day trading #76", "maker/two-sided #75 (0/10)",
                      "per-name sizing/vol target/pyramid (10)", "sector rotation (3)"],
    "closed_tail": ["micro TP/LOB ML/run exhaustion/edge sweep/maker cancel #94-#100 (2-session prelims)"],
    "how_to_read": [
        "evidence column outranks CAGR: only value_strict has real fills",
        "windows not comparable: rows 1-7 are 2020-26 (best block in 22 yrs), 2023-26 weaker everywhere",
        "hold the blend (combined_50_50), not the winner; gap-fade joins as a third sleeve only after 20 paper sessions",
    ],
}


# ---------------------------------------------------------------------------------------------------------- helpers
def dig(doc: Any, path: str | list) -> Any:
    """'a/b/c' into a summary (split on '/'), or a list of keys when a key itself holds '/' (e.g. 'lead 60/10/1.5')."""
    for step in (path if isinstance(path, list) else path.split("/")):
        if isinstance(doc, dict):
            doc = doc.get(step)
        elif isinstance(doc, list) and step.lstrip("-").isdigit():
            doc = doc[int(step)]
        else:
            return None
        if doc is None:
            return None
    return doc


def rnd(x: float | None, nd: int, scale: float = 1.0) -> float | int | None:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    v = round(float(x) * scale, nd)
    return int(v) if nd == 0 else v


class Src:
    """Resolves an original study id to the id used in this mode and reads its summary / params."""

    def __init__(self, conn, originals: bool):
        self.conn, self.originals, self.cache, self.used = conn, originals, {}, {}

    def id(self, sid: int) -> int:
        if self.originals:
            return sid
        r = self.conn.execute("SELECT current_id FROM idx.study_current WHERE id = %s", (sid,)).fetchone()
        return int(r["current_id"]) if r else sid

    def row(self, sid: int) -> dict:
        rid = self.id(sid)
        if rid not in self.cache:
            r = self.conn.execute("SELECT id, name, as_of, params, summary, note FROM idx.study WHERE id = %s", (rid,)).fetchone()
            if r is None:
                raise SystemExit(f"study #{rid} (for #{sid}) not found")
            self.cache[rid] = r
        self.used[sid] = rid
        return self.cache[rid]

    def get(self, sid: int, path: str) -> Any:
        return dig(self.row(sid)["summary"], path)


# ----------------------------------------------------------------------------------------------------- the row map
# key -> {field: (original study id, path, scale, decimals)}. Scale 100 turns a fraction into percent.
TREND = {
    "trend_small_gated": {"cagr_pct": (62, "A3/res/regime_gate|small/cagr", 100, 1), "sharpe": (62, "A3/res/regime_gate|small/sharpe", 1, 2),
                          "mdd_pct": (62, "A3/res/regime_gate|small/mdd", 100, 0), "hit_pct": (62, "A3/res/regime_gate|small/hit", 100, 0),
                          "payoff": (62, "A3/res/regime_gate|small/payoff", 1, 2), "trades": (62, "A3/res/regime_gate|small/n", 1, 0)},
    "trend_small": {"cagr_pct": (62, "A3/refs/small/cagr", 100, 1), "sharpe": (62, "A3/refs/small/sharpe", 1, 2),
                    "mdd_pct": (62, "A3/refs/small/mdd", 100, 0), "hit_pct": (62, "A3/refs/small/hit", 100, 0),
                    "payoff": (62, "A3/refs/small/payoff", 1, 2), "trades": (62, "A3/refs/small/n", 1, 0)},
    "value_strict": {"cagr_pct": (66, "S1/rule/cagr_pct", 1, 1), "sharpe": (66, "S1/rule/sharpe", 1, 2),
                     "mdd_pct": (66, "S1/rule/mdd_pct", -1, 0), "dsr": (66, "S1/rule/dsr", 1, 3)},
    "trend_liq": {"cagr_pct": (23, ["results", TREND_LEAD, "cagr"], 100, 1), "sharpe": (23, ["results", TREND_LEAD, "sharpe"], 1, 2),
                  "mdd_pct": (23, ["results", TREND_LEAD, "mdd"], 100, 0)},
    "trend_small_2005_2019": {"cagr_pct": (46, "results/small/cagr", 100, 1), "sharpe": (46, "results/small/sharpe", 1, 2),
                              "mdd_pct": (46, "results/small/mdd", 100, 0)},
    "book_gold_70_30": {"cagr_pct": (92, "gold30/cagr", 100, 1), "sharpe": (92, "gold30/sharpe", 1, 2), "mdd_pct": (92, "gold30/mdd", 100, 1)},
    "combined_50_50_gated": {"cagr_pct": (93, "w50_50_gated/cagr", 100, 1), "sharpe": (93, "w50_50_gated/sharpe", 1, 2),
                             "mdd_pct": (93, "w50_50_gated/mdd", 100, 1)},
    # the long-run allocation rows: menu 21 D figures, stored in the robustness scorecard's S8 (#66)
    "ew3_ihsg_sp_gold": {"cagr_pct": (66, "S8/res/EW3/cagr", 100, 1), "sharpe": (66, "S8/res/EW3/sharpe", 1, 2),
                         "mdd_pct": (66, "S8/res/EW3/mdd", 100, 0)},
    "gem_idr": {"cagr_pct": (66, "S8/res/gem_12m/cagr", 100, 1), "sharpe": (66, "S8/res/gem_12m/sharpe", 1, 2),
                "mdd_pct": (66, "S8/res/gem_12m/mdd", 100, 0)},
}


def fill(src: Src, spec: dict) -> dict:
    return {f: rnd(src.get(sid, path), nd, sc) for f, (sid, path, sc, nd) in spec.items()}


# ---------------------------------------------------------------------------------------------------- statuses
def trend_rule(src: Src) -> tuple[str, int, int]:
    """The rule's robustness read from idx_trend2.py (#23): ROBUST if >= 5 of the 7 grid neighbours hold."""
    s, p = src.row(23)["summary"], src.row(23)["params"]
    n = len((p or {}).get("grid") or {}) or 7
    return ("ROBUST" if s.get("robust") else "FRAGILE"), int(s.get("robust_n") or 0), n


def money_fails(verdict: str | None) -> str:
    """'tested: mdd>25%' -> 'drawdown'; the money rule's failing checks in words."""
    words = {"mdd>25%": "drawdown", "sharpe<1": "Sharpe", "t<2.5": "t", "vs random": "vs random", "years<5/7": "years"}
    if not verdict or not verdict.startswith("tested"):
        return ""
    fails = [words.get(x.strip(), x.strip()) for x in verdict.split(":", 1)[1].split(",")]
    return ", ".join(fails)


def gate_word(src: Src) -> str:
    return str(src.get(63, "verdict") or "").split(":")[0].strip() or "?"


def status_trend_small_gated(src: Src) -> str:
    rule, n, of = trend_rule(src)
    late = src.get(63, "V5/late/gate/sharpe")
    gate = src.get(63, "gate/sharpe")
    late_txt = (f", {'fragile' if late < 0.75 * gate else 'holds up'} to 1-day-late fill: Sharpe {late:.2f} vs {gate:.2f}"
                if late is not None and gate is not None else "")
    ref_mdd, g_mdd = src.get(63, "ref/mdd"), src.get(63, "gate/mdd")
    ret_ok = (src.get(63, "checks/V1 robust") and src.get(63, "checks/V2 additive"))
    return (f"rule {rule} ({n}/{of} neighbours{late_txt}); gate {gate_word(src)} (drawdown cut real, {ref_mdd*100:.0f}% -> "
            f"{g_mdd*100:.0f}%; return gain {'robust' if ret_ok else 'not'})")


def status_trend_small(src: Src) -> str:
    rule, n, of = trend_rule(src)
    f = money_fails(src.get(23, "verdicts/small"))
    return f"{rule} ({n}/{of} neighbours)" + (f"; fails money rule on {f}" if f else "; passes money rule")


def status_trend_liq(src: Src) -> str:
    r = src.get(23, ["results", TREND_LEAD]) or {}
    fails = [w for w, bad in (("t", r.get("tstat", 9) < 2.5), ("Sharpe", r.get("sharpe", 9) < 1), ("drawdown", r.get("mdd", 0) < -0.25)) if bad]
    rule, n, of = trend_rule(src)
    return f"{rule} ({n}/{of} neighbours)" + (f"; fails money rule ({', '.join(fails)})" if fails else "")


def status_combined(src: Src) -> str:
    s7 = src.get(66, "S7") or {}
    w = s7.get("weights") or {}
    txt = (f"{s7.get('verdict')} (menu 21 B: {sum(1 for v in w.values() if v.get('money'))}/{len(w)} weights pass money rule; "
           f"50/50 in {s7.get('t_pass')}/{len(s7.get('blocks') or {})} halves)")
    rob, of = src.get(93, "robust"), src.get(93, "of")
    return txt + (f"; stockmix {rob}/{of} weightings robust" if of is not None else "")


def status_gold(src: Src) -> str:
    g, r, h = src.get(92, "gold30"), src.get(92, "ref"), src.get(92, "halves") or {}
    word = "BETTER" if (src.get(92, "better") or 0) > 0 else "PARTIAL"
    sh_ok = g["sharpe"] >= r["sharpe"] + 0.15
    dd = (r["mdd"] - g["mdd"]) * 100
    halves = sum(1 for k, a, b in (("H1_gold_flat", "gold40_sharpe", "ref_sharpe"), ("H2_gold_boom", "gold50_sharpe", "ref_sharpe"))
                 if (h.get(k) or {}).get(a, 0) > (h.get(k) or {}).get(b, 9))
    return (f"{word}: Sharpe bar {'cleared' if sh_ok else 'missed'}, mDD {abs(dd):.1f}pt {'deeper' if dd > 0 else 'shallower'}; "
            f"{halves}/2 halves")


def status_value(src: Src) -> str:
    s1 = src.get(66, "S1") or {}
    return (f"{s1.get('verdict')}: placebo pct {s1['placebo']['pct']['sharpe']:.0f}, "
            f"{s1.get('n_pass')}/{len(s1.get('neighbours') or {})} neighbours")


def status_s8(src: Src, which: str, through_2008: bool) -> str:
    s8 = src.get(66, "S8") or {}
    v = s8.get(which) or {}
    txt = f"{v.get('verdict')}"
    if through_2008:
        txt += f", {v.get('t_pass')}/{len(s8.get('blocks') or {})} blocks, through 2008"
    return txt


def status_base_rate(src: Src) -> str:
    v = src.get(46, "verdict")
    return "long-run base rate" + (f"; the 2005-19 test itself: {v}" if v else "")


def gapfade(src: Src) -> dict:
    g7, dep = src.get(77, "arms/g7") or {}, src.get(89, f"arms/{GF_ARM}") or {}
    start, end, yrs = CONST["gapfade_full_span"]
    total = dep["total_pct"] / 100
    full = rnd((1 + total) ** (1 / yrs) - 1, 0, 100)
    implied = math.log(1 + total) / math.log(1 + dep["cagr_pct"] / 100)
    checks = g7.get("checks") or {}
    failed = [k for k, ok in checks.items() if not ok]
    word = "PASS" if not failed else ("BOUNDARY" if failed == ["t>=3"] else "FAILS " + ",".join(failed))
    means = [src.get(77, f"arms/{a}/mean_bps") for a in ("g5", "g7", "g10")]
    mono = all(a is not None and b is not None and a < b for a, b in zip(means, means[1:]))
    by_year = CONST["gapfade_events_by_year"]
    share = (by_year.get("2025", 0) + by_year.get("2026", 0)) / max(1, sum(by_year.values()))
    pop = src.get(89, "population") or {}
    return {
        "key": "gapfade_deployed", "rank": 1, "label": "gap-fade, deployed (-7%, K=5, deepest, liq>=5bn)",
        "live": CONST["live"]["gapfade_deployed"],
        "caveat": (f"#89's CAGR denominator implies ~{implied:.1f} yrs; the planning number re-annualises its total "
                   f"(+{dep['total_pct']:.0f}%) over the replicated {start[:7]}..{end[:7]} span ({yrs} yrs, hand replication of #102)"),
        "events": {"77": g7.get("trades"), "89": dep.get("events"), "by_year": by_year,
                   "population_replicated": CONST["gapfade_population_replicated"]},
        "sharpe": {"77": rnd(g7["sleeve"]["sharpe"], 2), "89": rnd(dep["sharpe"], 2)},
        "status": f"{word} (t {g7['t']:.2f} vs 3.0; placebo pct {g7['pct']:.0f}; {'monotone' if mono else 'not monotone'} in gap)",
        "window": f"{str(pop.get('start', '2020-09'))[:7]}..{str(pop.get('end', '2026-09'))[:7]} IDX opens; {share:.0%} of events in 2025-26",
        "hit_pct": {"77": rnd(g7["hit"], 0, 100), "89": rnd(dep["hit"], 0, 100)},
        "mdd_pct": {"77": rnd(g7["sleeve"]["mdd_pct"], 0), "89": rnd(dep["mdd_pct"], 1)},
        "sources": [77, 86, 87, 89],
        "cagr_pct": {"full_span_2021_26": full, "equal_weight_k10_77": rnd(g7["sleeve"]["cagr_pct"], 1),
                     "recent_regime_as_reported_89": rnd(dep["cagr_pct"], 0)},
        "per_event_bps": {"77": rnd(g7["mean_bps"], 0), "89": rnd(dep["mean_bps"], 0)},
        "planning_number_pct": full,
        "_reconciliation": {str(full): f"#89 total +{dep['total_pct']:.0f}% over the replicated full span {yrs} yrs ({start}..{end})",
                            str(rnd(dep["cagr_pct"], 0)): f"#89 as reported; implies ~{implied:.1f}-yr denominator",
                            str(rnd(g7["sleeve"]["cagr_pct"], 1)): "#77 equal-weight K=10, full span"},
    }


def ara_sell(src: Src) -> dict:
    liq, al = src.get(101, "reads/LIQ/H0"), src.get(101, "reads/ALL/H0")
    yrs = liq.get("by_year") or {}
    neg = sum(1 for v in yrs.values() if v.get("mean", 0) < 0)
    verdict = src.get(101, "verdict/LIQ/H0")
    p = max(liq["p_pos"], al["p_pos"])
    return {"t": {"LIQ": rnd(liq["t"], 1), "all": rnd(al["t"], 1)},
            "effect": (f"holding through ARA costs {liq['mean']:.0f} bps (LIQ) .. {al['mean']:.0f} (all) vs ARA price; "
                       f"P(hold>ARA) {p:.0%}; {CONST['ara_sell_book_effect']}"),
            "source": 101, "verdict": f"{'SELL' if verdict == 'SELL' else 'HOLD' if verdict == 'HOLD' else 'NO READ'} AT ARA (H0)",
            "years_consistent": f"{neg}/{len(yrs)}"}


def regime_gate(src: Src) -> dict:
    ref, gate = src.get(62, "A3/refs/small"), src.get(62, "A3/res/regime_gate|small")
    ret_ok = src.get(63, "checks/V1 robust") and src.get(63, "checks/V2 additive")
    return {"effect": f"mDD {ref['mdd']*100:.0f}% -> {gate['mdd']*100:.0f}%; return gain {'robust' if ret_ok else 'not robust'}",
            "status": gate_word(src), "sources": [62, 63]}


def build(src: Src) -> tuple[dict, dict]:
    ranked = [gapfade(src)]
    gf = ranked[0].pop("_reconciliation")
    rows = [
        ("trend_small_gated", 2, "trend small + regime gate", "2020-26", [62, 63, 66], status_trend_small_gated),
        ("trend_small", 3, "trend small, no gate", "2020-26", [23, 62], status_trend_small),
        ("combined_50_50_gated", 4, "value 50 / trend 50, gated", "2020-05..2026-09", [93, 66], status_combined),
        ("book_gold_70_30", 5, "book 70 / gold 30", "2020-05..2026-09", [92], status_gold),
        ("value_strict", 6, "value strict composite, annual May", None, [66], status_value),
        ("trend_liq", 7, "trend LIQ", "2020-26", [23], status_trend_liq),
        ("trend_small_2005_2019", 8, "trend small, 2005-2019 survivors", "2005-2019", [46], status_base_rate),
        ("ew3_ihsg_sp_gold", 9, "EW3 IHSG/S&P/gold", "2006-2026", [66, "menu 21 D"], lambda s: status_s8(s, "ew3", True)),
        ("gem_idr", 10, "rupiah dual momentum", "2006-2026", [66, "menu 21 D"], lambda s: status_s8(s, "gem", False)),
    ]
    for key, rank, label, window, sources, st in rows:
        r = {"key": key, "rank": rank, "label": label, "live": CONST["live"][key], **fill(src, TREND[key])}
        r["status"] = st(src)
        r["sources"] = sources
        if key == "value_strict":
            r["window"] = f"2020-26, {len(src.get(66, 'S1/rebalances') or [])} rebalances"
        else:
            r["window"] = window
        if key == "combined_50_50_gated":
            plain = src.get(92, "ref")
            live = src.get(93, "live_67_33_gated")
            r["variants"] = {"plain": {"sharpe": rnd(plain["sharpe"], 2), "mdd_pct": rnd(plain["mdd"], 1, 100), "cagr_pct": rnd(plain["cagr"], 1, 100)},
                             "live_67_33_gated": {"sharpe": rnd(live["sharpe"], 2), "mdd_pct": rnd(live["mdd"], 1, 100),
                                                  "cagr_pct": rnd(live["cagr"], 1, 100)}}
            r["sources"] = [93, 92, 66]
        if key == "ew3_ihsg_sp_gold":
            r["sharpe_with_dividends"] = CONST["ew3_with_dividends"]["sharpe"]
            r["cagr_with_dividends_pct"] = CONST["ew3_with_dividends"]["cagr_pct"]
        if key == "gem_idr":
            r["cagr_with_dividends_pct"] = CONST["gem_with_dividends"]["cagr_pct"]
        ranked.append(r)
    ih = src.get(66, "S8/res/IHSG") or {}
    ih2 = src.get(92, "ihsg")
    ih2 = ({"cagr_pct": rnd(ih2["cagr"], 1, 100), "sharpe": rnd(ih2["sharpe"], 2), "mdd_pct": rnd(ih2["mdd"], 1, 100)}
           if ih2 else CONST["ihsg_2020_26"])
    ranked.append({"key": "ihsg", "rank": None, "label": "IHSG buy & hold", "status": "benchmark",
                   "sharpe": {"2006_26": rnd(ih["sharpe"], 2), "2020_26": ih2["sharpe"]},
                   "mdd_pct": {"2006_26": rnd(ih["mdd"], 0, 100), "2020_26": ih2["mdd_pct"]},
                   "cagr_pct": {"2006_26": rnd(ih["cagr"], 1, 100), "2020_05_2026_09": ih2["cagr_pct"]},
                   "sources": [66, 92] if src.get(92, "ihsg") else [66]})
    av = src.row(91)
    closed = CONST["closed_static"] + [f"averaging down #{av['id']} ({av['summary'].get('better')}/{av['summary'].get('of')})"] + CONST["closed_tail"]
    summary = {"closed": closed, "ranked": ranked,
               "overlays": {"ara_sell": ara_sell(src), "regime_gate": regime_gate(src), "dividend_harvest": CONST["dividend_harvest"]},
               "how_to_read": CONST["how_to_read"]}
    return summary, gf


# ------------------------------------------------------------------------------------------------------ compare
FIELDS = ("cagr_pct", "sharpe", "mdd_pct", "hit_pct", "payoff", "trades")


def flat(v: Any) -> dict:
    if isinstance(v, dict):
        return {k: x for k, x in v.items() if isinstance(x, int | float)}
    return {"": v} if isinstance(v, int | float) else {}


def diff_table(new: dict, old: dict) -> list[tuple]:
    out = []
    olds = {r["key"]: r for r in old["ranked"]}
    for r in new["ranked"]:
        o = olds.get(r["key"], {})
        for f in FIELDS:
            a, b = flat(o.get(f)), flat(r.get(f))
            for k in sorted(set(a) | set(b)):
                out.append((r["key"], f + (f"[{k}]" if k else ""), a.get(k), b.get(k), a.get(k) == b.get(k)))
    for k, o in old["overlays"].items():
        n = new["overlays"].get(k, {})
        for f in ("t", "effect", "verdict", "status", "years_consistent"):
            if f in o or f in n:
                out.append((f"overlay:{k}", f, json.dumps(o.get(f)), json.dumps(n.get(f)), o.get(f) == n.get(f)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of-originals", action="store_true")
    ap.add_argument("--store", action="store_true")
    ap.add_argument("--baseline", type=int, default=BASELINE)
    ap.add_argument("--json", default="", help="also write the built summary to this file")
    args = ap.parse_args()
    if args.store and args.as_of_originals:
        raise SystemExit("--store is for the current build only")
    with psycopg.connect(os.environ["INGEST_DB_DSN"], row_factory=dict_row) as conn:
        src = Src(conn, args.as_of_originals)
        summary, gf = build(src)
        old = conn.execute("SELECT summary FROM idx.study WHERE id = %s", (args.baseline,)).fetchone()["summary"]
        mode = "ORIGINAL sources (no study_current)" if args.as_of_originals else "CURRENT sources (idx.study_current)"
        print(f"roi_scorecard rebuilt from {mode}; sources " + ", ".join(f"#{k}->#{v}" if k != v else f"#{k}" for k, v in sorted(src.used.items())))
        rows = diff_table(summary, old)
        print(f"\n{'row':24} {'field':32} {'#' + str(args.baseline):>10} {'built':>10}  same")
        for key, f, a, b, same in rows:
            if f in ("effect", "verdict", "status"):
                print(f"{key:24} {f:32} {'':>10} {'':>10}  {'yes' if same else 'NO'}\n    {a}\n    {b}")
            else:
                print(f"{key:24} {f:32} {str(a):>10} {str(b):>10}  {'yes' if same else 'NO'}")
        miss = [r for r in rows if not r[4] and r[1].split("[")[0] in ("cagr_pct", "sharpe", "mdd_pct")]
        print(f"\ncagr/sharpe/mdd cells: {sum(1 for r in rows if r[1].split('[')[0] in ('cagr_pct', 'sharpe', 'mdd_pct'))}, differing: {len(miss)}")
        print("\nstatus strings:")
        olds = {r["key"]: r for r in old["ranked"]}
        for r in summary["ranked"]:
            print(f"  {r['key']:24} #{args.baseline}: {olds.get(r['key'], {}).get('status')}\n  {'':24} built: {r['status']}")
        if args.json:
            with open(args.json, "w", encoding="utf-8") as fh:
                json.dump(summary, fh, indent=2)
        if args.store:
            from blackheart_ingest.idx import research_store as rs
            cum = max((int((c["params"] or {}).get("n_trials_cumulative") or 0) for c in src.cache.values()), default=0)
            ids = sorted({v for v in src.used.values()})
            params = {"kind": "scorecard", "as_of": date.today().isoformat(), "trials": [], "sources": ids,
                      "source_map": {str(k): v for k, v in sorted(src.used.items())}, "n_trials_cumulative": cum,
                      "built_by": "research/idx_roi_scorecard.py", "replaces": args.baseline,
                      "gapfade_reconciliation": gf,
                      "constants": "non-study figures carried from #102: menu 21 D dividend variants, menu 27 dividend harvest, "
                                   "live-book notes, gap-fade event replication (by_year, 591, the 5.46-yr span), ROI rank order"}
            note = (f"programmatic rebuild of #{args.baseline} from the current studies ({', '.join('#' + str(i) for i in ids)}); "
                    "statuses derived from each source's verdict fields")
            sid = rs.record_study(conn, "roi_scorecard", date.today(), params=params, summary=summary, names=[], note=note)
            prev = conn.execute("""SELECT id FROM idx.study WHERE name = 'roi_scorecard' AND id <> %s AND superseded_by IS NULL
                                   ORDER BY as_of DESC, id DESC LIMIT 1""", (sid,)).fetchone()
            if prev:
                rs.supersede(conn, prev["id"], sid, REASON)
            print(f"\nstudy #{sid} stored" + (f"; #{prev['id']} superseded" if prev else ""))


if __name__ == "__main__":
    main()
