#!/usr/bin/env python3
"""IDX menu 3 — "follow the accumulation" (operator, 2026-09-17 09:10 WIB). The only accumulation measure the desk holds
with history is foreign net buying (IDX publishes foreign buy/sell shares per name per day); broker-level flow ("bandar")
is not public data and is not in the data plane. Menu 2 already showed 5-day foreign flow and quiet 1-day accumulation do
nothing at 2–10 days; this menu asks the longer question: does sustained foreign accumulation over 20–60 days pay over the
next 20–60 days? Same engine, universes, costs (closing offer/bid + Stockbit fees) and reading rule as menu 2.

PRE-REGISTERED (6 trials; cumulative 242 + 6 = 248):
  f20_top|20, f20_top|60        BLUE, top decile of 20-day foreign net share (net foreign shares / volume), H = 20 / 60
  f60_top|20, f60_top|60        BLUE, top decile of the 60-day foreign net share, H = 20 / 60
  quiet60|20                    BLUE, 60-day foreign net share > 0 and the 60-day price return within +-5 % (bought without
                                the price moving), ranked by foreign share, H = 20
  f20_top_liq|20                LIQ (wider, cheaper names), top decile of 20-day foreign net share, H = 20
READING RULE: as menu 2 (>= 300 trades, basket-day t >= 2.5, >= 5 of 7 years positive, Sharpe >= 1.0, max DD <= 25 %,
  Sharpe >= random + 0.5 on the same universe and H).
READ-ONLY. INGEST_DB_DSN=... blackheart-ingest/.venv/Scripts/python research/idx_accum.py
"""
from __future__ import annotations

import os
import sys
from datetime import date

import numpy as np
import pandas as pd
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import idx_swing2 as S  # noqa: E402

N_BEFORE = 242
ARMS = [("f20_top|20", "BLUE"), ("f20_top|60", "BLUE"), ("f60_top|20", "BLUE"), ("f60_top|60", "BLUE"), ("quiet60|20", "BLUE"), ("f20_top_liq|20", "LIQ")]


def main():
    dsn = os.environ["INGEST_DB_DSN"]
    with psycopg.connect(dsn) as conn:
        bars, listing, idx, macro, buyb, splits, pead = S.load(conn)
    P = S.panels(bars, listing)
    _, unis, comp = S.build(P, listing, idx, macro, buyb, splits, pead)
    c_in, c_out = S.costs(P)
    adj, close, vol = P["adj"], P["close"], P["volume"]
    blue, liq = unis["BLUE"], unis["LIQ"]
    fnet_sh = P["fnet"] / close                                     # net foreign shares per day
    f60 = fnet_sh.rolling(60, min_periods=40).sum() / vol.rolling(60, min_periods=40).sum()
    f20 = P["f20"]
    r60 = adj / adj.shift(60) - 1
    arms = {
        "f20_top": (blue & (f20.where(blue).rank(axis=1, ascending=False, pct=True) <= 0.10), f20),
        "f60_top": (blue & (f60.where(blue).rank(axis=1, ascending=False, pct=True) <= 0.10), f60),
        "quiet60": (blue & (f60 > 0) & (r60.abs() <= 0.05), f60),
        "f20_top_liq": (liq & (f20.where(liq).rank(axis=1, ascending=False, pct=True) <= 0.10), f20),
    }
    n_trials = N_BEFORE + len(ARMS)
    rng = np.random.default_rng(S.SEED)
    refs, res, verd = {}, {}, {}
    for arm, u in ARMS:
        name, H = arm.split("|"); H = int(H)
        if (u, H) not in refs:
            R, tr, ex = S.simulate(adj, unis[u], adj * 0, H, 5, c_in, c_out, rng=rng, uni=unis[u])
            refs[(u, H)] = S.stats(R, tr, ex, n_trials)
        m, sc = arms[name]
        R, tr, ex = S.simulate(adj, m, sc, H, 5, c_in, c_out)
        res[arm] = S.stats(R, tr, ex, n_trials)
        ok, why = S.passes(name, res[arm], refs[(u, H)])
        verd[arm] = "CANDIDATE" if ok else "tested: " + ",".join(why)

    def yrs(d):
        return " ".join(f"{y % 100:02d}:{v * 100:+.0f}" for y, v in sorted(d.items()))
    lines = [f"# IDX menu 3 — follow the accumulation — {date.today()} — {len(ARMS)} trials, cumulative N = {n_trials}", "",
             "| arm | H | trades | hit | gross/trade | net/trade | t(basket) | total | Sharpe | mDD | expo | years | verdict |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for (u, H), s in sorted(refs.items()):
        lines.append(f"| random {u} | {H} | {s['n_trades']} | {s['hit'] * 100:.0f} % | {s['avg_gross'] * 100:+.2f} % | {s['avg_net'] * 100:+.2f} % | {s['tstat']:.1f} | {s['total'] * 100:+.0f} % | {s['sharpe']:.2f} | {s['mdd'] * 100:.0f} % | {s['exposure'] * 100:.0f} % | {yrs(s['years'])} | reference |")
    for arm, u in ARMS:
        s = res[arm]; name, H = arm.split("|")
        lines.append(f"| {name} [{u}] | {H} | {s['n_trades']} | {s['hit'] * 100:.0f} % | {s['avg_gross'] * 100:+.2f} % | {s['avg_net'] * 100:+.2f} % | {s['tstat']:.1f} | {s['total'] * 100:+.0f} % | {s['sharpe']:.2f} | {s['mdd'] * 100:.0f} % | {s['exposure'] * 100:.0f} % | {yrs(s['years'])} | {verd[arm]} |")
    n_c = sum(1 for v in verd.values() if v == "CANDIDATE")
    lines += ["", f"Reading rule applied as declared: {n_c} candidate(s) of {len(ARMS)}."]
    text = "\n".join(lines); print(text)
    out = os.path.join(HERE, f"IDX_ACCUM_{date.today().isoformat()}.md")
    open(out, "w", encoding="utf-8").write(text + "\n"); print("wrote", out)
    from blackheart_ingest.idx import research_store as rs
    with psycopg.connect(dsn) as conn:
        sid = rs.record_study(conn, "accum", adj.index[-1].date(), params={"trials": [a for a, _ in ARMS], "n_trials_cumulative": n_trials},
                              summary={"results": res, "random": {f"{u}|{h}": v for (u, h), v in refs.items()}, "verdicts": verd, "candidates": n_c},
                              names=[], report_path=out, note=f"{n_c} candidates of {len(ARMS)}")
        print("study", sid)


if __name__ == "__main__":
    main()
