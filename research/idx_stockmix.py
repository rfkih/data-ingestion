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

READ-ONLY. INGEST_DB_DSN=... blackheart-ingest/.venv/Scripts/python research/idx_stockmix.py
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import idx_beyond as B  # noqa: E402
import idx_exit as E  # noqa: E402
import idx_swing2 as S  # noqa: E402

SWITCH_COST = 0.003
GRID = [100, 80, 67, 60, 50, 40, 33, 20, 0]


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


def main():
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


if __name__ == "__main__":
    main()
