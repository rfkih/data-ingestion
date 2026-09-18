#!/usr/bin/env python3
"""IDX menu 4 — "bandarmologi": does broker-level accumulation predict the next 20–60 days? (operator, 2026-09-17; the data
menus 1–3 could not have: idx.broker_summary / idx.broker_detector, fetched from the operator's Stockbit data account in
20-trading-day windows for the 46 most-traded names, 2023-09 → 2026-09).

PRE-REGISTERED MENU (10 trials; cumulative 248 + 10 = 258). Declared before the run; nothing tuned afterwards.
  Signal at the close of a window's last day t (the window is [t-19, t]); entry at the close of t+1 (closing offer), exit at
  the close of t+1+H (closing bid), Stockbit fees; K = 5 names per signal date ranked as stated; H = 20 (the next window) or 60.
  Universe = the fetched names that are in BLUE on t (60-day value >= Rp 20 bn, close >= Rp 1,000). Same engine and costs as menu 2.
  Features per (name, window), from the API's own detector block and the per-broker rows:
    top1_pct / top3_pct / top5_pct   share of the window's traded value net-bought by the top 1/3/5 net buyers (%)
    top1_label, broker_accdist       the API's labels (Big Acc / Small Acc / Neutral / Dist; Acc / Dist / Neutral)
    nbs                              number_broker_buysell = net buyers - net sellers (breadth of buying)
    asing / lokal / pemerintah       net value by the API's investor class of each broker, as % of the window's traded value
    top1_persist                     the same broker is the top-1 net buyer in this window and the previous one
  Arms:
    big_acc|20, big_acc|60           top1_label == Big Acc, ranked by top1_pct
    acc|20, acc|60                   broker_accdist == Acc, ranked by top5_pct
    breadth|20                       nbs >= +10 (many more net buyers than net sellers), ranked by nbs
    asing|20, asing|60               foreign-class net buying >= 5 % of traded value, ranked by it
    lokal_quiet|20                   local-class net buying >= 5 % of value while the window's price return is within +-5 %
    persist|20, persist|60           top1_persist and top1_pct >= 15 %, ranked by top1_pct
  References (not trials): random on the same signal dates and universe (K = 5, H = 20 / 60); dist|20 (broker_accdist == Dist)
    as the mirror image - informational, not a long trade.
READING RULE (declared before the run): candidate only if ALL hold after costs: >= 150 trades; mean net basket-day return > 0
  with t >= 2.5; net portfolio return positive in >= 3 of the 4 calendar years 2023–2026; annualised Sharpe >= 1.0; max
  drawdown <= 25 %; Sharpe >= random + 0.5 at the same H. Candidates go to a paper book for >= 60 trades before money.
READ-ONLY. INGEST_DB_DSN=... blackheart-ingest/.venv/Scripts/python research/idx_bandar.py
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

N_BEFORE = 248
ARMS = ["big_acc|20", "big_acc|60", "acc|20", "acc|60", "breadth|20", "asing|20", "asing|60", "lokal_quiet|20", "persist|20", "persist|60"]
assert len(ARMS) == 10


def load_features(conn) -> pd.DataFrame:
    det = pd.read_sql("""SELECT code, date_from, date_to, value, total_buyer, total_seller, number_broker_buysell AS nbs, broker_accdist,
                                top1_pct, top3_pct, top5_pct, top10_pct, top1_label FROM idx.broker_detector WHERE code <> 'TEST'""", conn)
    cls = pd.read_sql("""SELECT code, date_from, date_to, investor, sum(net_value) AS net FROM idx.broker_summary WHERE code <> 'TEST'
                         GROUP BY 1, 2, 3, 4""", conn)
    top = pd.read_sql("""SELECT DISTINCT ON (code, date_from, date_to) code, date_from, date_to, broker AS top1_broker
                           FROM idx.broker_summary WHERE code <> 'TEST' ORDER BY code, date_from, date_to, net_value DESC""", conn)
    for c in ("value", "top1_pct", "top3_pct", "top5_pct", "top10_pct"):
        det[c] = pd.to_numeric(det[c], errors="coerce")
    cls["net"] = pd.to_numeric(cls["net"], errors="coerce")
    wide = cls.pivot_table(index=["code", "date_from", "date_to"], columns="investor", values="net", aggfunc="sum").reset_index()
    f = det.merge(wide, on=["code", "date_from", "date_to"], how="left").merge(top, on=["code", "date_from", "date_to"], how="left")
    for c in ("Asing", "Lokal", "Pemerintah"):
        if c not in f:
            f[c] = np.nan
        f[c.lower()] = f[c] / f["value"] * 100
    f = f.sort_values(["code", "date_to"])
    f["top1_persist"] = f.groupby("code")["top1_broker"].shift(1) == f["top1_broker"]
    f["date_to"] = pd.to_datetime(f["date_to"])
    return f


def masks(f: pd.DataFrame, dates, cols, r20: pd.DataFrame):
    """(name -> (mask, score)) on the panel grid; every signal sits on the window's last day."""
    def grid(sel: pd.DataFrame, score_col: str):
        m = pd.DataFrame(False, index=dates, columns=cols)
        sc = pd.DataFrame(np.nan, index=dates, columns=cols)
        for r in sel.itertuples(index=False):
            if r.code in cols and r.date_to in m.index:
                m.at[r.date_to, r.code] = True
                sc.at[r.date_to, r.code] = float(getattr(r, score_col))
        return m, sc
    out = {}
    out["big_acc"] = grid(f[f["top1_label"] == "Big Acc"], "top1_pct")
    out["acc"] = grid(f[f["broker_accdist"] == "Acc"], "top5_pct")
    out["breadth"] = grid(f[f["nbs"] >= 10], "nbs")
    out["asing"] = grid(f[f["asing"] >= 5], "asing")
    lk = f[f["lokal"] >= 5].copy()
    lk["r20"] = [r20.at[d, c] if (c in r20.columns and d in r20.index) else np.nan for c, d in zip(lk["code"], lk["date_to"])]
    out["lokal_quiet"] = grid(lk[lk["r20"].abs() <= 0.05], "lokal")
    out["persist"] = grid(f[f["top1_persist"] & (f["top1_pct"] >= 15)], "top1_pct")
    out["dist"] = grid(f[f["broker_accdist"] == "Dist"], "top5_pct")
    all_sig = grid(f, "top1_pct")[0]                    # every (name, window end): the random reference draws from these dates
    return out, all_sig


def main():
    dsn = os.environ["INGEST_DB_DSN"]
    with psycopg.connect(dsn) as conn:
        bars, listing, idx, macro, buyb, splits, pead = S.load(conn)
        f = load_features(conn)
    P = S.panels(bars, listing)
    _, unis, comp = S.build(P, listing, idx, macro, buyb, splits, pead)
    c_in, c_out = S.costs(P)
    adj = P["adj"]
    blue = unis["BLUE"]
    r20 = adj / adj.shift(20) - 1
    arms, all_sig = masks(f, adj.index, adj.columns, r20)
    sig_uni = blue & all_sig                                        # random draws only on signal dates, among fetched BLUE names
    n_trials = N_BEFORE + len(ARMS)
    rng = np.random.default_rng(S.SEED)
    refs, res, verd = {}, {}, {}
    for H in (20, 60):
        R, tr, ex = S.simulate(adj, sig_uni, adj * 0, H, 5, c_in, c_out, rng=rng, uni=sig_uni)
        refs[H] = S.stats(R, tr, ex, n_trials)
    for arm in ARMS + ["dist|20"]:
        name, H = arm.split("|"); H = int(H)
        m, sc = arms[name]
        R, tr, ex = S.simulate(adj, blue & m, sc.fillna(-np.inf), H, 5, c_in, c_out)
        res[arm] = S.stats(R, tr, ex, n_trials)
        if arm in ARMS:
            s = res[arm]
            why = []
            if s["n_trades"] < 150:
                why.append("n")
            if not (s["avg_net"] > 0 and s["tstat"] >= 2.5):
                why.append("t<2.5")
            if sum(1 for y, v in s["years"].items() if y >= 2023 and v > 0) < 3:
                why.append("years")
            if s["sharpe"] < 1.0:
                why.append("sharpe<1")
            if s["mdd"] < -0.25:
                why.append("mdd")
            if s["sharpe"] < refs[H]["sharpe"] + 0.5:
                why.append("vs random")
            verd[arm] = "CANDIDATE" if not why else "tested: " + ",".join(why)

    def yrs(d):
        return " ".join(f"{y % 100:02d}:{v * 100:+.0f}" for y, v in sorted(d.items()) if y >= 2023)
    n_win = len(f)
    lines = [f"# IDX menu 4 — bandarmologi — {date.today()} — {len(ARMS)} trials, cumulative N = {n_trials}", "",
             f"Feed: {f['code'].nunique()} names, {n_win} windows of 20 trading days, {f['date_to'].min().date()} -> {f['date_to'].max().date()}; "
             f"signals on window ends; entry close t+1 @offer, exit @bid, fees {S.FEE_BUY * 100:.2f}/{S.FEE_SELL * 100:.2f} %.", "",
             "| arm | H | trades | hit | gross/trade | net/trade | t(basket) | total | Sharpe | mDD | expo | years | verdict |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for H, s in sorted(refs.items()):
        lines.append(f"| random (signal dates) | {H} | {s['n_trades']} | {s['hit'] * 100:.0f} % | {s['avg_gross'] * 100:+.2f} % | {s['avg_net'] * 100:+.2f} % | {s['tstat']:.1f} | {s['total'] * 100:+.0f} % | {s['sharpe']:.2f} | {s['mdd'] * 100:.0f} % | {s['exposure'] * 100:.0f} % | {yrs(s['years'])} | reference |")
    for arm in ARMS + ["dist|20"]:
        s = res[arm]; name, H = arm.split("|")
        v = verd.get(arm, "reference (mirror)")
        lines.append(f"| {name} | {H} | {s['n_trades']} | {s['hit'] * 100:.0f} % | {s['avg_gross'] * 100:+.2f} % | {s['avg_net'] * 100:+.2f} % | {s['tstat']:.1f} | {s['total'] * 100:+.0f} % | {s['sharpe']:.2f} | {s['mdd'] * 100:.0f} % | {s['exposure'] * 100:.0f} % | {yrs(s['years'])} | {v} |")
    n_c = sum(1 for v in verd.values() if v == "CANDIDATE")
    # plain event view: forward 20/60-day returns by label, no portfolio (what the operator asked: does a buyback/accumulation label predict up?)
    A = adj
    fwd = {}
    for H in (20, 60):
        fr = A.shift(-H - 1) / A.shift(-1) - 1               # close t+1 -> close t+1+H
        fwd[H] = fr
    ev = []
    for r in f.itertuples(index=False):
        if r.code not in A.columns or r.date_to not in A.index:
            continue
        ev.append({"label": r.broker_accdist, "top1": r.top1_label, "r20": fwd[20].at[r.date_to, r.code], "r60": fwd[60].at[r.date_to, r.code]})
    ev = pd.DataFrame(ev).dropna()
    lines += ["", "Gross forward returns by the API's own label (no costs, every fetched name, equal weight):", "",
              "| label | n | P(up 20d) | avg 20d | median 20d | P(up 60d) | avg 60d | median 60d |", "|---|---|---|---|---|---|---|---|"]
    for col, key in (("label", "broker_accdist"), ("top1", "top1_label")):
        for lab, g in ev.groupby(col):
            lines.append(f"| {key}={lab} | {len(g)} | {(g['r20'] > 0).mean() * 100:.0f} % | {g['r20'].mean() * 100:+.2f} % | {g['r20'].median() * 100:+.2f} % | "
                         f"{(g['r60'] > 0).mean() * 100:.0f} % | {g['r60'].mean() * 100:+.2f} % | {g['r60'].median() * 100:+.2f} % |")
    lines += ["", f"Reading rule applied as declared: {n_c} candidate(s) of {len(ARMS)}.", "",
              "Limits: 3 years of data (2023-09 →) on 46 names; 20-day windows (a signal only every 20 days per name); the API's labels are",
              "Stockbit's own definitions; net by investor class uses the API's broker classification; close-to-close execution as in menus 1–3."]
    text = "\n".join(lines); print(text)
    out = os.path.join(HERE, f"IDX_BANDAR_{date.today().isoformat()}.md")
    open(out, "w", encoding="utf-8").write(text + "\n"); print("wrote", out)
    from blackheart_ingest.idx import research_store as rs
    with psycopg.connect(dsn) as conn:
        sid = rs.record_study(conn, "bandar", adj.index[-1].date(), params={"trials": ARMS, "n_trials_cumulative": n_trials, "windows": n_win},
                              summary={"results": res, "random": refs, "verdicts": verd, "candidates": n_c}, names=[], report_path=out,
                              note=f"{n_c} candidates of {len(ARMS)}")
        print("study", sid)


if __name__ == "__main__":
    main()
