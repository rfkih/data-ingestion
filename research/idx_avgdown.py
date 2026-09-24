"""IDX menu 30 - averaging down: add to a losing position after it falls X % (operator's question 2026-09-23).

READ-ONLY. INGEST_DB_DSN=... PYTHONIOENCODING=utf-8 blackheart-ingest/.venv/Scripts/python research/idx_avgdown.py

The incumbent trend rule SELLS at -10 % from the peak (trail10). Adding at -10 % is therefore not an extra rule on top of the
incumbent - it replaces the exit with an entry at the same trigger. Every arm below is that swap, made honestly:

  half           the control: start at half a slot and never add. Isolates "smaller first tranche" from "averaging down".
  addfall10_tN   start at half a slot; add the other half at the close after the price first trades <= 90 % of the ENTRY price;
                 exit on a trail of N % from the peak. With N = 10 the trail fires on the same bar the add triggers, so the add
                 can never execute - that is the point, and the arm is kept to show it.
  addfall15_t20  a deeper add trigger with the widest stop.

Verdict rule, fixed BEFORE the run (the desk's usual bar): an arm is BETTER only if Sharpe >= reference + 0.15 AND its drawdown
is no deeper than the reference. Anything else is reported as tested.
"""
from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import idx_beyond as B  # noqa: E402
import idx_exit as E  # noqa: E402
import idx_swing2 as S  # noqa: E402

K = B.K
N_TRIALS = 512


def make_add_on_fall(A, k, drop=0.10, frac=0.5):
    """Add ``frac`` of a slot at the next close once the price has fallen ``drop`` below the ENTRY price. Once only."""
    def add(t, j, p):
        st = p["state"]
        if st.get("added_dn"):
            return 0
        if A[t, j] <= (1 - drop) * p["a0"]:
            st["added_dn"] = True
            return frac / k
        return 0
    return add



def make_add_dip_then_up(A, k, drop=0.07, frac=0.5, ref="peak", confirm=1):
    """Family B - the operator's refinement (2026-09-23): arm when the price is ``drop`` below ``ref`` (entry or running peak),
    then add ``frac`` of a slot at the next close after ``confirm`` consecutive up closes. Unlike a naive add-on-fall this CAN
    execute under trail10: the arming band (-7 %) sits inside the stop (-10 %), so there is a live window. If the fall continues
    to the stop, the exit fires first and no add is made - the engine checks ``rule`` before ``add``."""
    def add(t, j, p):
        st = p["state"]
        if st.get("added_dip"):
            return 0
        px = A[t, j]
        if not np.isfinite(px):
            return 0
        base = p["a0"] if ref == "entry" else p["peak"]
        if px <= (1 - drop) * base:
            st["armed"] = True
            st["up"] = 0
            return 0
        if st.get("armed"):
            prev = A[t - 1, j]
            if np.isfinite(prev) and px > prev:
                st["up"] = st.get("up", 0) + 1
                if st["up"] >= confirm:
                    st["added_dip"] = True
                    return frac / k
            else:
                st["up"] = 0
        return 0
    return add


def row(name, st, ref):
    better = st["sharpe"] >= ref["sharpe"] + 0.15 and st["mdd"] >= ref["mdd"]
    print(f"{name:22s} n={st['n']:4d} hit={st['hit']*100:3.0f}% net={st['avg_net']*100:+6.2f}% "
          f"t={st['tstat']:4.1f} cagr={st['cagr']*100:+6.1f}% sharpe={st['sharpe']:5.2f} mdd={st['mdd']*100:4.0f}%"
          f"   {'BETTER' if better else 'tested'}", flush=True)


def main():
    dsn = os.environ["INGEST_DB_DSN"]
    P, unis, comp, Hp, Lp, sectors, brent = B.load_all(dsn, os.environ.get("IDX_BEYOND_CACHE"))
    c_in, c_out = S.costs(P)
    dates = P["adj"].index
    A, H, L, entry, score, ATR, SIG, trail10, universes = B.prep_panels(P, unis, Hp, Lp)

    trailN = {x: (lambda t, j, p, x=x: 1.0 if A[t, j] <= (1 - x) * p["peak"] else 0) for x in (0.10, 0.12, 0.15, 0.20)}

    for u in ("small", "LIQ"):
        uni = universes[u]
        sizes = B.make_sizes(A, ATR, SIG, uni, K)
        print(f"\n=== universe {u} ===")
        R0, tr0, _ = E.run_book(A, H, L, c_in, c_out, entry, score, trail10, uni)
        ref_st = E.stats(R0, tr0, dates, N_TRIALS)
        row("eq 1/K + trail10 (REF)", ref_st, ref_st)

        Rh, trh, _ = B.run_book_sized(A, H, c_in, c_out, entry, score, trail10, uni, sizes["half"])
        row("half, no add", E.stats(Rh, trh, dates, N_TRIALS), ref_st)

        for drop, tr_x in ((0.10, 0.10), (0.10, 0.15), (0.10, 0.20), (0.15, 0.20)):
            add = make_add_on_fall(A, K, drop=drop)
            Rs, trs, _ = B.run_book_sized(A, H, c_in, c_out, entry, score, trailN[tr_x], uni, sizes["half"], add=add)
            row(f"addfall{int(drop*100)} + trail{int(tr_x*100)}", E.stats(Rs, trs, dates, N_TRIALS), ref_st)


        print(f"--- family B: dip X then up (confirmation add) ---")
        for drop, ref, conf, tr_x in ((0.07, "peak", 1, 0.10), (0.07, "entry", 1, 0.10), (0.07, "peak", 2, 0.10),
                                      (0.07, "peak", 1, 0.12), (0.05, "peak", 1, 0.10), (0.10, "peak", 1, 0.15)):
            addb = make_add_dip_then_up(A, K, drop=drop, ref=ref, confirm=conf)
            Rb, trb, _ = B.run_book_sized(A, H, c_in, c_out, entry, score, trailN[tr_x], uni, sizes["half"], add=addb)
            row(f"dip{int(drop*100)}_{ref[:3]}_up{conf} + trail{int(tr_x*100)}", E.stats(Rb, trb, dates, N_TRIALS), ref_st)

        add_up = B.make_add(A, ATR, K)
        Rp, trp, _ = B.run_book_sized(A, H, c_in, c_out, entry, score, trail10, uni, sizes["half"], add=add_up)
        row("pyramid (add on UP)", E.stats(Rp, trp, dates, N_TRIALS), ref_st)


if __name__ == "__main__":
    main()
