"""IDX menu 32 - stock-only: what is the right weight between the value book and the trend book?
2026-09-23. The operator ruled out the allocation layer (menu 31, gold): equities only.

Menu 21 family B found the value+trend combination ROBUST (4/5 weights pass the money rule, 50/50 passes in 2/2 halves).
The desk's live capital is NOT at that weight: Rp 20 M value (IPOT) + Rp 10 M trend (Stockbit) = 67/33. This menu measures
the whole weight surface so the choice is made on the shape of the surface, not on its peak.

Arms: value weight 100 -> 0 in the fixed grid below, monthly rebalance, 0.30 % switch cost on the drift.
Trend sleeve in two forms: plain trail10, and with the regime gate that is actually deployed (regime_filter=on, 2026-09-22).

PRE-REGISTERED before the run:
  reference  67/33 (the live split today)
  BETTER     Sharpe >= reference + 0.15 AND max drawdown no deeper than the reference
  ROBUST     the verdict must also hold in BOTH halves; a weight that only wins in one half is reported as tested
  The peak of the grid is NOT the recommendation - a flat surface is the finding, a sharp peak would be a warning.
  Window is the value book's, 2020-05 on: ~6.4 years. Short, as menu 31.

INGEST_DB_DSN=... blackheart-ingest/.venv/Scripts/python research/idx_stockmix.py [--no-store] [--report PATH]
Reads the desk; its only write is the idx.study row 'stockmix' (added 2026-09-26: the 2026-09-23 run #93 was stored by hand).
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import idx_beyond as B  # noqa: E402
import idx_exit as E  # noqa: E402
import idx_swing2 as S  # noqa: E402

SWITCH_COST = 0.003
GRID = [100, 80, 67, 60, 50, 40, 33, 20, 0]
REF_W = 67
N_TRIALS_CUMULATIVE = 603            # menu 32: 18 arms, cumulative as stored on #93


def monthly(d: pd.Series) -> pd.Series:
    return (1 + d).resample("ME").prod() - 1


def stats(m: pd.Series):
    m = m.dropna()
    if len(m) < 18:
        return None
    yrs = len(m) / 12
    cagr = float((1 + m).prod()) ** (1 / yrs) - 1
    vol = float(m.std() * np.sqrt(12))
    sharpe = float(m.mean() * 12 / vol) if vol > 0 else 0.0
    eq = (1 + m).cumprod()
    return {"cagr": cagr, "vol": vol, "sharpe": sharpe, "mdd": float((eq / eq.cummax() - 1).min())}


def mix(v: pd.Series, t: pd.Series, wv: float) -> pd.Series:
    wt = 1 - wv
    if wv == 0:
        return t
    if wt == 0:
        return v
    out = []
    for i in v.index:
        r = wv * v.loc[i] + wt * t.loc[i]
        drift = (abs(wv * (1 + v.loc[i]) / (1 + r) - wv) + abs(wt * (1 + t.loc[i]) / (1 + r) - wt)) / 2 if r > -1 else 0
        out.append(r - SWITCH_COST * drift)
    return pd.Series(out, index=v.index)


def table(title, v, t, ref_w=67):
    print(f"\n{title}")
    ref = stats(mix(v, t, ref_w / 100))
    print(f"{'value/trend':>12} {'CAGR':>8} {'vol':>6} {'Sharpe':>7} {'mDD':>8}   verdict")
    best = None
    for w in GRID:
        st = stats(mix(v, t, w / 100))
        if st is None:
            continue
        ok = st["sharpe"] >= ref["sharpe"] + 0.15 and st["mdd"] >= ref["mdd"]
        tag = "<- live today" if w == ref_w else ("BETTER" if ok else "tested")
        if best is None or st["sharpe"] > best[1]:
            best = (w, st["sharpe"])
        print(f"{w:>7}/{100-w:<4} {st['cagr']*100:>7.1f}% {st['vol']*100:>5.0f}% {st['sharpe']:>7.2f} {st['mdd']*100:>7.1f}%   {tag}")
    print(f"   peak Sharpe at {best[0]}/{100-best[0]} ({best[1]:.2f})")
    return ref


def surface(v, t) -> dict:
    return {w: stats(mix(v, t, w / 100)) for w in GRID}


def better(st, ref) -> bool:
    return st is not None and st["sharpe"] >= ref["sharpe"] + 0.15 and st["mdd"] >= ref["mdd"]


def summarize(v_m, t_m, g_m, idx) -> tuple[dict, str]:
    """The stored summary, with #93's keys (of, robust, peak_gated, w50_50_gated, live_67_33_gated, gate_effect_at_67_33, H2_weaker,
    surface, direction_67_to_50) plus the plain 50/50 and the per-half tables. ROBUST = BETTER than the 67/33 reference over the full
    window AND in both halves, for the plain and the gated trend sleeve alike (9 weights x 2 = 18 arms)."""
    half = len(idx) // 2
    wins = {"full": idx, "H1": idx[:half], "H2": idx[half:]}
    tabs = {(kind, wn): surface(v_m.reindex(sl), tr.reindex(sl))
            for kind, tr in (("plain", t_m), ("gated", g_m)) for wn, sl in wins.items()}
    robust, better_by = 0, {}
    for kind in ("plain", "gated"):
        for w in GRID:
            flags = {wn: better(tabs[(kind, wn)][w], tabs[(kind, wn)][REF_W]) for wn in wins}
            better_by[f"{kind} {w}/{100 - w}"] = [wn for wn, ok in flags.items() if ok]
            robust += all(flags.values())
    g = tabs[("gated", "full")]
    peak = max((w for w in GRID if g[w]), key=lambda w: g[w]["sharpe"])
    top = sorted(g[w]["sharpe"] for w in (50, 40, 33))
    r = lambda st: {"mdd": round(st["mdd"], 3), "cagr": round(st["cagr"], 3), "sharpe": round(st["sharpe"], 2)}  # noqa: E731
    d = {wn: tabs[("gated", wn)][50]["sharpe"] - tabs[("gated", wn)][REF_W]["sharpe"] for wn in wins}
    summary = {
        "of": 2 * len(GRID), "robust": robust,
        "surface": (f"flat 50/50..33/67 ({top[0]:.2f}-{top[-1]:.2f}); gated peak " + ", ".join(
            f"{p}/{100 - p} {wn}" for wn in wins
            for p in [max((w for w in GRID if tabs[('gated', wn)][w]), key=lambda w, wn=wn: tabs[('gated', wn)][w]['sharpe'])])),
        "operator": "stay 20M/10M; add to trading once track record reproduces the profile",
        "H2_weaker": {"value_only_sharpe": {"H1": round(tabs[("gated", "H1")][100]["sharpe"], 2),
                                            "H2": round(tabs[("gated", "H2")][100]["sharpe"], 2)}},
        "peak_gated": {"sharpe": round(g[peak]["sharpe"], 2), "weight": f"{peak}/{100 - peak}"},
        "w50_50_gated": r(g[50]), "live_67_33_gated": r(g[REF_W]),
        "w50_50_plain": r(tabs[("plain", "full")][50]), "live_67_33_plain": r(tabs[("plain", "full")][REF_W]),
        "direction_67_to_50": (f"{'positive' if all(x > 0 for x in d.values()) else 'mixed'} "
                               f"{sum(1 for x in d.values() if x > 0)}/3 windows, size "
                               f"{'under' if max(d.values()) < 0.15 else 'over'} the bar"),
        "gate_effect_at_67_33": {"gated": round(g[REF_W]["sharpe"], 2), "plain": round(tabs[("plain", "full")][REF_W]["sharpe"], 2)},
        "better_in": {k: v for k, v in better_by.items() if v},
        "window": f"{idx[0]:%Y-%m}..{idx[-1]:%Y-%m}", "months": len(idx),
        "tables": {f"{kind}_{wn}": {f"{w}/{100 - w}": r(st) for w, st in tab.items() if st} for (kind, wn), tab in tabs.items()},
    }
    ge = summary["gate_effect_at_67_33"]
    note = (f"{robust}/{2 * len(GRID)} ROBUST; 50/50 gated {g[50]['cagr']:.1%}/yr Sharpe {g[50]['sharpe']:.2f} mDD {g[50]['mdd']:.1%}; "
            f"live 67/33 gated Sharpe {g[REF_W]['sharpe']:.2f}; regime gate at 67/33 {ge['plain']:.2f} -> {ge['gated']:.2f}")
    return summary, note


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-store", action="store_true")
    ap.add_argument("--report", default=None, help="report_path recorded on the study row (e.g. this run's log)")
    args = ap.parse_args()
    dsn = os.environ["INGEST_DB_DSN"]
    nav_v = B.value_nav(dsn)
    nav_v.index = pd.to_datetime(nav_v.index)
    v_m = monthly(nav_v.pct_change().dropna())

    P, unis, comp, Hp, Lp, sectors, brent = B.load_all(dsn, os.environ.get("IDX_BEYOND_CACHE"))
    c_in, c_out = S.costs(P)
    A, H, L, entry, score, ATR, SIG, trail10, universes = B.prep_panels(P, unis, Hp, Lp)
    dates = pd.to_datetime(P["adj"].index)
    uni = universes["small"]

    Rt, _, _ = E.run_book(A, H, L, c_in, c_out, entry, score, trail10, uni)
    Rt.index = dates
    t_m = monthly(Rt)

    off = B.regime_off_mask(comp, P["adj"].index)
    size_gate = lambda tt, j: 0.0 if off[tt] else (1.0 / B.K)  # noqa: E731
    Rg, _, _ = B.run_book_sized(A, H, c_in, c_out, entry, score, trail10, uni, size_gate)
    Rg.index = dates
    g_m = monthly(Rg)

    idx = v_m.index.intersection(t_m.index)
    v_m, t_m, g_m = v_m.reindex(idx), t_m.reindex(idx), g_m.reindex(idx)
    print(f"overlap {idx[0]:%Y-%m} .. {idx[-1]:%Y-%m}  ({len(idx)} months, {len(idx)/12:.1f} years)")

    table("=== A. value + trend (plain trail10) ===", v_m, t_m)
    table("=== B. value + trend WITH the deployed regime gate ===", v_m, g_m)

    half = len(idx) // 2
    for name, sl in (("H1", idx[:half]), ("H2", idx[half:])):
        table(f"--- {name} {sl[0]:%Y-%m}..{sl[-1]:%Y-%m} (value + gated trend) ---",
              v_m.reindex(sl), g_m.reindex(sl))

    summary, note = summarize(v_m, t_m, g_m, idx)
    print("\n" + note)
    if not args.no_store:
        import psycopg
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "blackheart-ingest", "src"))
        from blackheart_ingest.idx import research_store as rs
        params = {"bar": "Sharpe >= ref(67/33)+0.15 AND mdd no deeper, in BOTH halves", "menu": 32,
                  "trials": [f"{k} value{w}/trend{100 - w}" for k in ("plain", "gated") for w in GRID],
                  "window": summary["window"], "rebalance": "monthly, 0.30% switch cost", "n_trials_cumulative": N_TRIALS_CUMULATIVE}
        with psycopg.connect(dsn) as conn:
            sid = rs.record_study(conn, "stockmix", date(2026, 9, 23), params=params, summary=summary, names=[],
                                  report_path=args.report, note=note)
        print(f"study #{sid} stored")


if __name__ == "__main__":
    main()
