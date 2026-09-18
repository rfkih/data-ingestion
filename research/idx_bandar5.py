#!/usr/bin/env python3
"""IDX menu 5 — bandarmologi re-read on 5-trading-day windows (operator "okay boleh", 2026-09-17): the same feed at four times
the sampling density for the last 12 months (46 names, windows of 5 trading days), read at H = 5 / 10 / 20.

Why a new menu: menu 4's 20-day windows gave 37 observations per name over 3 years and a +2–5 pp after-cost gap over random with
t 0.6–1.6. Denser windows are the only way to tell a tilt from noise without waiting years.

PRE-REGISTERED MENU (9 trials; cumulative 258 + 9 = 267). Declared before the run; nothing tuned afterwards.
  Signal at the close of a 5-day window's last day t; entry close t+1 (offer), exit close t+1+H (bid), Stockbit fees; K = 5
  names per signal date (every name has a signal date every 5 trading days, so the dates coincide across names).
  Universe = fetched names in BLUE on t. Features as menu 4 (API detector labels and per-broker rows, per 5-day window).
  Arms:
    acc|5, acc|10, acc|20             broker_accdist == Acc, ranked by top5_pct
    big_acc|5, big_acc|10, big_acc|20 top1_label == Big Acc, ranked by top1_pct
    persist|5, persist|10, persist|20 the same top-1 net buyer in this window and the previous one, ranked by top1_pct
  References (not trials): random on the same signal dates and universe at each H; dist (broker_accdist == Dist) as the mirror.
READING RULE (declared before the run; per-trade, because window signals leave a tranche portfolio 1–4 % invested and its
  Sharpe says nothing): an arm is a candidate only if ALL hold after costs: >= 300 trades; mean net basket-day return > 0
  with t >= 2.5 (names on one date = one observation); net per trade at least +1.0 pp above random at the same H; hit rate
  >= 50 %; net positive in >= 3 of the 4 quarters of the sample. A candidate goes to a paper book for >= 60 trades.
READ-ONLY. INGEST_DB_DSN=... PYTHONIOENCODING=utf-8 blackheart-ingest/.venv/Scripts/python research/idx_bandar5.py
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
import idx_bandar as B  # noqa: E402
import idx_swing2 as S  # noqa: E402

N_BEFORE = 258
HS = (5, 10, 20)
ARMS = [f"{a}|{h}" for a in ("acc", "big_acc", "persist") for h in HS]
assert len(ARMS) == 9


def main():
    dsn = os.environ["INGEST_DB_DSN"]
    with psycopg.connect(dsn) as conn:
        bars, listing, idx, macro, buyb, splits, pead = S.load(conn)
        f = B.load_features(conn)
    f["span"] = (pd.to_datetime(f["date_to"]) - pd.to_datetime(f["date_from"])).dt.days
    f = f[(f["span"] <= 9) & (pd.to_datetime(f["date_to"]) >= pd.Timestamp("2025-09-16"))].copy()   # 5-day windows of the last 12 months only
    #   (20-day windows span >= 26 days; the 2023-09 remainder window of the 20-day run is short too, hence the date floor)
    f = f.sort_values(["code", "date_to"])
    f["top1_persist"] = f.groupby("code")["top1_broker"].shift(1) == f["top1_broker"]
    P = S.panels(bars, listing)
    _, unis, comp = S.build(P, listing, idx, macro, buyb, splits, pead)
    c_in, c_out = S.costs(P)
    adj = P["adj"]
    blue = unis["BLUE"]
    r20 = adj / adj.shift(20) - 1
    arms, all_sig = B.masks(f, adj.index, adj.columns, r20)
    sig_uni = blue & all_sig
    n_trials = N_BEFORE + len(ARMS)
    rng = np.random.default_rng(S.SEED)
    refs, res, verd = {}, {}, {}
    for H in HS:
        R, tr, ex = S.simulate(adj, sig_uni, adj * 0, H, 5, c_in, c_out, rng=rng, uni=sig_uni)
        refs[H] = S.stats(R, tr, ex, n_trials)

    def quarters_positive(trades):
        q = {}
        for e, _, _, net in trades:
            d = adj.index[e]
            q.setdefault((d.year, (d.month - 1) // 3), []).append(net)
        return sum(1 for v in q.values() if np.mean(v) > 0), len(q)
    for arm in ARMS + ["dist|5", "dist|20"]:
        name, H = arm.split("|"); H = int(H)
        m, sc = arms[name]
        R, tr, ex = S.simulate(adj, blue & m, sc.fillna(-np.inf), H, 5, c_in, c_out)
        s = S.stats(R, tr, ex, n_trials)
        s["q_pos"], s["q_n"] = quarters_positive(tr)
        res[arm] = s
        if arm in ARMS:
            why = []
            if s["n_trades"] < 300:
                why.append("n<300")
            if not (s["avg_net"] > 0 and s["tstat"] >= 2.5):
                why.append("t<2.5")
            if s["avg_net"] - refs[H]["avg_net"] < 0.010:
                why.append("<random+1pp")
            if s["hit"] < 0.50:
                why.append("hit<50%")
            if s["q_pos"] < 3:
                why.append("quarters<3/4")
            verd[arm] = "CANDIDATE" if not why else "tested: " + ",".join(why)
    lines = [f"# IDX menu 5 — bandarmologi on 5-day windows — {date.today()} — {len(ARMS)} trials, cumulative N = {n_trials}", "",
             f"Feed: {f['code'].nunique()} names, {len(f)} windows of 5 trading days, {f['date_to'].min().date()} -> {f['date_to'].max().date()}; "
             f"entry close t+1 @offer, exit @bid, fees {S.FEE_BUY * 100:.2f}/{S.FEE_SELL * 100:.2f} %.", "",
             "| arm | H | trades | hit | gross/trade | net/trade | vs random | t(basket) | quarters + | verdict |", "|---|---|---|---|---|---|---|---|---|---|"]
    for H, s in sorted(refs.items()):
        lines.append(f"| random (signal dates) | {H} | {s['n_trades']} | {s['hit'] * 100:.0f} % | {s['avg_gross'] * 100:+.2f} % | {s['avg_net'] * 100:+.2f} % | - | {s['tstat']:.1f} | - | reference |")
    for arm in ARMS + ["dist|5", "dist|20"]:
        s = res[arm]; name, H = arm.split("|"); H = int(H)
        lines.append(f"| {name} | {H} | {s['n_trades']} | {s['hit'] * 100:.0f} % | {s['avg_gross'] * 100:+.2f} % | {s['avg_net'] * 100:+.2f} % | "
                     f"{(s['avg_net'] - refs[H]['avg_net']) * 100:+.2f} pp | {s['tstat']:.1f} | {s['q_pos']}/{s['q_n']} | {verd.get(arm, 'reference (mirror)')} |")
    n_c = sum(1 for v in verd.values() if v == "CANDIDATE")
    # label table, gross, all names
    ev = []
    fwd = {H: adj.shift(-H - 1) / adj.shift(-1) - 1 for H in HS}
    for r in f.itertuples(index=False):
        if r.code in adj.columns and r.date_to in adj.index:
            ev.append({"label": r.broker_accdist, **{f"r{H}": fwd[H].at[r.date_to, r.code] for H in HS}})
    ev = pd.DataFrame(ev).dropna()
    lines += ["", "Gross forward returns by the API's accumulation label (no costs, every fetched name, equal weight):", "",
              "| label | n | P(up 5d) | med 5d | P(up 10d) | med 10d | P(up 20d) | med 20d | avg 20d |", "|---|---|---|---|---|---|---|---|---|"]
    for lab, g in [("all", ev)] + list(ev.groupby("label")):
        lines.append(f"| {lab} | {len(g)} | {(g['r5'] > 0).mean() * 100:.0f} % | {g['r5'].median() * 100:+.2f} % | {(g['r10'] > 0).mean() * 100:.0f} % | "
                     f"{g['r10'].median() * 100:+.2f} % | {(g['r20'] > 0).mean() * 100:.0f} % | {g['r20'].median() * 100:+.2f} % | {g['r20'].mean() * 100:+.2f} % |")
    lines += ["", f"Reading rule applied as declared: {n_c} candidate(s) of {len(ARMS)}.", "",
              "Limits: 12 months, 46 names; the API's labels are Stockbit's definitions computed per 5-day window; close-to-close execution."]
    text = "\n".join(lines); print(text)
    out = os.path.join(HERE, f"IDX_BANDAR5_{date.today().isoformat()}.md")
    open(out, "w", encoding="utf-8").write(text + "\n"); print("wrote", out)
    from blackheart_ingest.idx import research_store as rs
    with psycopg.connect(dsn) as conn:
        sid = rs.record_study(conn, "bandar5", adj.index[-1].date(), params={"trials": ARMS, "n_trials_cumulative": n_trials, "windows": len(f)},
                              summary={"results": {k: {kk: vv for kk, vv in v.items() if kk != "years"} for k, v in res.items()}, "random": refs, "verdicts": verd, "candidates": n_c},
                              names=[], report_path=out, note=f"{n_c} candidates of {len(ARMS)}")
        print("study", sid)


if __name__ == "__main__":
    main()
