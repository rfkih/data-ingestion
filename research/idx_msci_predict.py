#!/usr/bin/env python3
"""IDX menu 47 - PREDICTING MSCI INDONESIA (Standard) ADDITIONS before the announcement (study 'msci_predict', 2026-09-26).

Menu 36 (#186): LQ45 adds jump ~+3 % at the open after the notice, nothing left after. Menu 42 (#191): predicting LQ45 adds
fails (precision@5 9 %) because IDX's committee is discretionary; it named MSCI Indonesia (published, mechanical rules) as the
better candidate. This menu tests that.

EVENTS (sourced 2026-09-26). Primary source = MSCI's own public change lists, one PDF per review and segment:
  https://app2.msci.com/eqb/gimi/stdindex/MSCI_<Mon><YY>_STPublicList.pdf   (Standard)
  https://app2.msci.com/eqb/gimi/smallcap/MSCI_<Mon><YY>_SCPublicList.pdf   (Small Cap)
  downloaded for all 27 reviews Feb20..Aug26 (research-scratch/msci/), Indonesia section parsed with pypdf. Each gives the
  announcement date (US, published after the US close = before the Jakarta open of the next day) and the 'as of the close of'
  rebalance date R. Cross-checked in the press: liputan6 4556579 (May21), liputan6 4961857 (May22), katadata 63e6209c895c0
  (Feb23), stockbit snips (May24 TPIA in / TOWR SMGR out), cnbcindonesia research 20250212105511 (Feb25), kompas 2025/08/08 +
  cnbcindonesia market 20250808092042 (Aug25), cnbcindonesia research 20251106063651 (Nov25), investortrust 112681 (Aug26).
  Standard ADDS (10 reviews, 15 names): Nov20 MDKA TOWR | Feb21 ANTM | May21 TBIG | Feb22 ARTO | May22 ADMR AMRT INCO | May23 GOTO |
  Nov23 AMMN | May24 TPIA | Aug25 DSSA CUAN | Nov25 BREN BRMS. Standard deletions in 18 reviews (table below). No Indonesian early
  (IPO) inclusion was found 2020-2026 (news + change lists; absence of evidence).
  2026 FREEZE: MSCI announced 2026-01-27 (free-float consultation result) a freeze on FIF/NOS increases, IMI additions and upward
  migrations for Indonesia; it held at Feb/May/Aug 2026 (deletions only). Those three reviews are known in advance to have no
  adds, so they are NOT traded (recorded, not hidden). Feb 2020 is out (its price cut-off precedes our data, which start 2020-01-02).
  Traded reviews: May 2020 .. Nov 2025 = 23 scheduled reviews, 10 with Standard adds -> few events: PARTIAL at best.
MEMBERSHIP (point in time): chained BACKWARD from the post-Aug-2026 list of 9 (ASII BBCA BBNI BBRI BMRI BRMS BRPT TLKM UNTR,
  Republika / investortrust 2026-08-13) through every change; asserted: every deletion is a member and every add a non-member
  at its step. Gives 28 names before May 2020 (2019 press: 27) and 17 before May 2026 (press: 17 -> 11).

RULE PROXY (inputs known at the PRICE CUT-OFF c = min(last IDX session of the month before the announcement month, the 11th
session before the Jakarta jump session) - MSCI uses a price date among the last 10 business days of the prior month):
  full mcap USD = close x listed_shares / USDIDR (idx.macro 'usdidr'); FF shares = weight_for_index where IDX publishes free float
  (from 2022-04 the cross-sectional median ratio is ~0.21; before, it equals listed shares and FF = full, i.e. no FIF test);
  eligible non-member: first session <= c - 3 months (minimum length of trading); regular board, no special-notation letter at c
  (menu 42's flags; MSCI's criterion 10 excludes FCA/watchlist names); frequency: traded on >= 80 % of sessions in the 12-month
  AND the 3-month window; ATVR: monthly median daily value x 252 / FF mcap at month end, 12-month mean and 3-month mean both
  >= 15 % (EM threshold); FF ratio >= 15 % (FIF floor) where published.
  Cutoff estimate C^ = median full mcap (USD) of the 3 smallest current members; FF floor = 0.5 x C^ x (members' median FF ratio).
  score = full company mcap USD (MSCI sizes on full mcap). 'rule-pass' = eligible non-members with full mcap >= 1.5 C^ (May/Nov
  semi-annual) or 1.8 C^ (Feb/Aug quarterly) and FF mcap >= the FF floor.
STEP 1 (classification, not a trial): precision@k / recall@k (k = 1, 3, 5) of the top-k non-members by score vs actual Standard
  adds, pooled over the 23 traded reviews; rank of each actual add; the rule-pass set's precision/recall.

STEP 2 (trade) PRE-REGISTERED, written before any return was computed. 7 trials; cumulative N_BEFORE 992 + 7 = 999.
  The announcement date is published by MSCI a year ahead, so the jump session J (first IDX session after the US announcement
  date) is known without look-ahead. Entry = closing offer at session J - T; exit (a) = closing bid at J's close (the jump day),
  exit (b) = closing bid at R's close (the last IDX session <= MSCI's 'as of the close of' date; index funds trade there).
  Costs / controls / t exactly menu 36/42 (idx_index_rebalance.Mkt.trade: closing offer/bid or +-1 tick, fees 0.10/0.20 %,
  70 bps round-trip floor; 5 controls matched on log mcap + log 60-day median value at ENTRY among non-members that are not
  changed in the review and not in the predicted top-10; excess = net - mean control net; t = event-clustered over reviews).
    M1        top-3 by score, T = 5,  exit (a)
    M2        top-3,          T = 10, exit (a)
    M3 MAIN   top-3,          T = 5,  exit (b)
    M4        top-3,          T = 10, exit (b)
    M5        top-1,          T = 5,  exit (b)
    M6        rule-pass set (at most 5, by score), T = 5, exit (b)
    M7        top-3 by FF mcap (eligible non-members), T = 5, exit (b)
  Stresses on M3 (not trials): costs x 1.5; halves 2020-22 / 2023-25; placebo: 3 random eligible non-members from score ranks
  4..20 per review, 1000 draws; DSR of the per-review excess series at N = 999. Facts (not trials), ACTUAL adds: perfect foresight
  (same M1/M3 windows); announcement reaction (J-1 close -> J close, gross, vs controls); POST-ANNOUNCEMENT DRIFT: buy the closing
  offer at J's close, sell R's closing bid (tradeable after the notice) - net, excess, t over reviews; and the same for the
  Standard deletions (avoid-filter view).
BAR (M3): event-clustered mean excess > 0 with t >= 2.0 AND mean net per trade > 0 AND excess > 0 in >= 60 % of reviews AND
  placebo percentile >= 95. Pass -> PARTIAL at best (10 add reviews); then correlation with the combo sleeves and Rp on a
  Rp 20 M book. Fail -> CLOSED.
READ-ONLY; one idx.study row ('msci_predict'). INGEST_DB_DSN (or blackheart-ingest/idx-local.env).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date

import numpy as np
import pandas as pd
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blackheart-ingest", "src"))
import idx_index_rebalance as IR  # noqa: E402  (read-only: Mkt pricing/costs/matching)
import idx_lq45_predict as LP  # noqa: E402  (read-only: load_summary board/notation flags, dsr)
from blackheart_ingest.idx import research_store as rs  # noqa: E402

N_BEFORE = 992
N_TRIALS = 7
STUDY = "msci_predict"
SEED = 20260926
N_PLACEBO = 1000
OUT = os.path.join(HERE, "IDX_MSCI_PREDICT_2026-09-26.md")
SRC = "app2.msci.com/eqb/gimi/stdindex/MSCI_{}_STPublicList.pdf"

# (review, US announcement date, 'as of the close of' R, std adds, std dels, small-cap adds count, small-cap dels count)
REVIEWS = [
    ("Feb20", "2020-02-12", "2020-02-28", "", "", 0, 0),
    ("May20", "2020-05-12", "2020-05-29", "", "BBTN PTBA BSDE JSMR TKIM PWON", 10, 14),
    ("Aug20", "2020-08-12", "2020-08-31", "", "", 0, 0),
    ("Nov20", "2020-11-10", "2020-11-30", "MDKA TOWR", "HMSP EXCL", 5, 4),
    ("Feb21", "2021-02-09", "2021-02-26", "ANTM", "ACES", 1, 1),
    ("May21", "2021-05-11", "2021-05-27", "TBIG", "PGAS", 3, 3),
    ("Aug21", "2021-08-11", "2021-08-31", "", "", 0, 0),
    ("Nov21", "2021-11-11", "2021-11-30", "", "", 9, 3),
    ("Feb22", "2022-02-09", "2022-02-28", "ARTO", "", 0, 0),
    ("May22", "2022-05-12", "2022-05-31", "ADMR AMRT INCO", "INTP", 11, 2),
    ("Aug22", "2022-08-11", "2022-08-31", "", "", 0, 0),
    ("Nov22", "2022-11-10", "2022-11-30", "", "ADMR GGRM TBIG", 4, 3),
    ("Feb23", "2023-02-09", "2023-02-28", "", "ARTO", 3, 1),
    ("May23", "2023-05-11", "2023-05-31", "GOTO", "", 0, 2),
    ("Aug23", "2023-08-10", "2023-08-31", "", "", 3, 4),
    ("Nov23", "2023-11-14", "2023-11-30", "AMMN", "INCO", 2, 5),
    ("Feb24", "2024-02-12", "2024-02-29", "", "", 2, 1),
    ("May24", "2024-05-14", "2024-05-31", "TPIA", "TOWR SMGR", 5, 9),
    ("Aug24", "2024-08-12", "2024-08-30", "", "ANTM", 5, 0),
    ("Nov24", "2024-11-06", "2024-11-25", "", "", 1, 2),
    ("Feb25", "2025-02-11", "2025-02-28", "", "INKP MDKA UNVR", 3, 4),
    ("May25", "2025-05-13", "2025-05-30", "", "", 2, 4),
    ("Aug25", "2025-08-07", "2025-08-26", "DSSA CUAN", "ADRO", 6, 2),
    ("Nov25", "2025-11-05", "2025-11-24", "BREN BRMS", "ICBP KLBF", 7, 3),
    ("Feb26", "2026-02-10", "2026-02-27", "", "INDF", 1, 2),
    ("May26", "2026-05-12", "2026-05-29", "", "AMMN BREN TPIA DSSA CUAN AMRT", 1, 13),
    ("Aug26", "2026-08-12", "2026-08-31", "", "CPIN GOTO", 1, 9),
]
FREEZE = {"Feb26", "May26", "Aug26"}
AFTER_AUG26 = "ASII BBCA BBNI BBRI BMRI BRMS BRPT TLKM UNTR"
TRIALS = {
    "M1_T5_jump": dict(k=3, T=5, exit="J"),
    "M2_T10_jump": dict(k=3, T=10, exit="J"),
    "M3_T5_R (main)": dict(k=3, T=5, exit="R"),
    "M4_T10_R": dict(k=3, T=10, exit="R"),
    "M5_top1_T5_R": dict(k=1, T=5, exit="R"),
    "M6_rulepass_T5_R": dict(k="rule", T=5, exit="R"),
    "M7_ffcap_T5_R": dict(k=3, T=5, exit="R", score="ff"),
}
MAIN = "M3_T5_R (main)"


def membership():
    """-> dict review -> member set BEFORE that review (backward chain from the post-Aug-2026 list)."""
    m = set(AFTER_AUG26.split())
    before = {}
    for rv, _, _, a, d, _, _ in reversed(REVIEWS):
        a, d = a.split(), d.split()
        assert all(x in m for x in a) and not any(x in m for x in d), (rv, a, d)
        m = (m - set(a)) | set(d)
        before[rv] = set(m)
    return before


def main() -> int:
    conn = psycopg.connect(IR.dsn())
    before = membership()
    W = IR.load(conn)
    M = IR.Mkt(W)
    dates = M.dates
    P = LP.load_summary(conn, dates, M.codes)
    fx = pd.DataFrame(conn.execute("SELECT obs_date, value::float FROM idx.macro WHERE series='usdidr'").fetchall(), columns=["d", "fx"])
    fx["d"] = pd.to_datetime(fx["d"])
    FX = fx.set_index("d")["fx"].sort_index().reindex(dates, method="ffill")
    first_day = P["present"].idxmax()
    V = P["v"]
    ff_ratio_all = (P["w"] / P["sh"])
    med_ratio = ff_ratio_all.median(axis=1)
    ff_pub = med_ratio < 0.99  # per date: IDX publishes free float (full phase-in ~2022-04)
    months = pd.Series(dates, index=dates).dt.to_period("M")

    def features(cpos: int):
        c_day = dates[cpos]
        fxc = FX.iloc[cpos]
        cl, sh, w = P["c"].iloc[cpos], P["sh"].iloc[cpos], P["w"].iloc[cpos]
        pub = bool(ff_pub.iloc[cpos])
        ffs = w if pub else sh
        full = cl * sh / fxc
        ffm = cl * ffs / fxc
        st12 = int(np.searchsorted(dates, c_day - pd.DateOffset(months=12), side="right"))
        st3 = int(np.searchsorted(dates, c_day - pd.DateOffset(months=3), side="right"))
        Vw = V.iloc[st12:cpos + 1]
        fr12 = (Vw.fillna(0) > 0).mean()
        fr3 = (V.iloc[st3:cpos + 1].fillna(0) > 0).mean()
        # monthly ATVR: median daily value in month x 252 / FF mcap (IDR) at month end
        mo = months.iloc[st12:cpos + 1]
        med = Vw.groupby(mo.values).median()
        last_idx = pd.Series(np.arange(st12, cpos + 1), index=mo.values).groupby(level=0).max()
        ffm_idr_me = pd.DataFrame({p: (P["c"].iloc[i] * (P["w"].iloc[i] if bool(ff_pub.iloc[i]) else P["sh"].iloc[i])) for p, i in last_idx.items()}).T
        atvr = (med * 252) / ffm_idr_me.reindex(med.index)
        atvr12 = atvr.mean(skipna=True)
        atvr3 = atvr.tail(3).mean(skipna=True)
        age_ok = first_day <= c_day - pd.DateOffset(months=3)
        ratio = (w / sh) if pub else pd.Series(1.0, index=sh.index)
        elig = (age_ok & P["board_ok"].iloc[cpos] & (P["nt"].iloc[cpos].fillna(0) == 0) & (fr12 >= 0.8) & (fr3 >= 0.8)
                & (atvr12 >= 0.15) & (atvr3 >= 0.15) & (ratio.fillna(0) >= 0.15) & full.gt(0) & P["present"].iloc[cpos])
        return pd.DataFrame({"full": full, "ffm": ffm, "atvr12": atvr12, "atvr3": atvr3, "fr12": fr12, "ratio": ratio, "elig": elig.fillna(False)}), pub

    # ---- per review setup + step 1 -------------------------------------------------------------------------------------------
    revs = []
    for rv, A, R, a, d, sca, scd in REVIEWS:
        e = {"rv": rv, "A": A, "R": R, "adds": a.split(), "dels": d.split(), "sca": sca, "scd": scd, "before": before[rv],
             "year": int(A[:4]), "freeze": rv in FREEZE}
        e["tJ"] = int(np.searchsorted(dates, pd.Timestamp(A), side="right"))  # first IDX session after the US announcement date
        e["tR"] = int(np.searchsorted(dates, pd.Timestamp(R), side="right")) - 1
        prev_me = int(np.searchsorted(dates, pd.Timestamp(A).replace(day=1), side="left")) - 1
        e["cpos"] = min(prev_me, e["tJ"] - 11)
        e["traded"] = (not e["freeze"]) and e["cpos"] >= 60 and e["tJ"] - 10 >= 0
        revs.append(e)
    trade_revs = [e for e in revs if e["traded"]]
    cls_rows = []
    for e in trade_revs:
        F, pub = features(e["cpos"])
        mem = [c for c in e["before"] if c in F.index]
        memF = F.loc[mem].dropna(subset=["full"])
        chat = float(np.median(np.sort(memF["full"].values)[:3]))
        mratio = float(memF["ratio"].median())
        ff_floor = 0.5 * chat * mratio
        mult = 1.5 if e["rv"][:3] in ("May", "Nov") else 1.8
        nm = F[F["elig"] & ~F.index.isin(e["before"])].sort_values("full", ascending=False).copy()
        nm["rank"] = np.arange(1, len(nm) + 1)
        e["nm"] = nm
        e["nm_ff"] = nm.sort_values("ffm", ascending=False)
        e["rule"] = list(nm[(nm["full"] >= mult * chat) & (nm["ffm"] >= ff_floor)].index[:5])
        e["chat"], e["pub"] = chat, pub
        allF = F.dropna(subset=["full"])
        row = {"rv": e["rv"], "A": e["A"], "cut": str(dates[e["cpos"]].date()), "chat": chat, "n_mem": len(e["before"]), "pub": pub,
               "adds": e["adds"], "add_rank": {}, "top5": list(nm.index[:5]), "rule": e["rule"]}
        for a in e["adds"]:
            if a in nm.index:
                row["add_rank"][a] = f"#{int(nm.loc[a, 'rank'])}"
            elif a in allF.index:
                why = [k for k, ok in (("age", first_day.get(a) <= dates[e['cpos']] - pd.DateOffset(months=3)),
                                        ("freq", allF.loc[a, "fr12"] >= 0.8), ("atvr", allF.loc[a, "atvr12"] >= 0.15 and allF.loc[a, "atvr3"] >= 0.15),
                                        ("ff", allF.loc[a, "ratio"] >= 0.15)) if not ok]
                row["add_rank"][a] = "inelig(" + ",".join(why or ["board/notation"]) + ")"
            else:
                row["add_rank"][a] = "no data"
        for k in (1, 3, 5):
            hit = len(set(nm.index[:k]) & set(e["adds"]))
            row[f"hit{k}"] = hit
        row["rule_hit"] = len(set(e["rule"]) & set(e["adds"]))
        cls_rows.append(row)
    cls = pd.DataFrame(cls_rows)
    tot_adds = int(sum(len(r["adds"]) for r in cls_rows))
    agg = {f"prec{k}": float(cls[f"hit{k}"].sum() / (k * len(cls))) for k in (1, 3, 5)}
    agg.update({f"rec{k}": float(cls[f"hit{k}"].sum() / tot_adds) for k in (1, 3, 5)})
    n_rule = int(sum(len(r["rule"]) for r in cls_rows))
    agg.update({"rule_n": n_rule, "rule_prec": float(cls["rule_hit"].sum() / max(1, n_rule)), "rule_rec": float(cls["rule_hit"].sum() / tot_adds),
                "tot_adds": tot_adds, "n_reviews": len(cls), "n_add_reviews": int(sum(1 for r in cls_rows if r["adds"]))})
    # precision restricted to reviews that had adds (how well does it name them when MSCI adds someone)
    ar = cls[cls["adds"].apply(len) > 0]
    agg["prec3_add_reviews"] = float(ar["hit3"].sum() / (3 * len(ar)))
    print("classification", json.dumps(agg, indent=1))

    # ---- step 2: trades ------------------------------------------------------------------------------------------------------
    ctrl_cache: dict = {}

    def controls(i, e, j, t_in):
        key = (i, j, t_in)
        if key not in ctrl_cache:
            excl = {M.ix[c] for c in list(e["before"]) + e["adds"] + e["dels"] + list(e["nm"].index[:10]) if c in M.ix}
            excl.discard(j)
            ctrl_cache[key] = [k for k in M.matched(j, t_in, excl, 5) if k != j]
        return ctrl_cache[key]

    def trade_rows(spec, mult=1.0, pick=None, entry_off=None, revlist=None):
        rows = []
        for i, e in enumerate(revlist or trade_revs):
            if pick is not None:
                names = pick[i]
            elif spec["k"] == "rule":
                names = e["rule"]
            else:
                src = e["nm_ff"] if spec.get("score") == "ff" else e["nm"]
                names = list(src.index[:spec["k"]])
            t_in = e["tJ"] - spec["T"] if entry_off is None else entry_off(e)
            t_out = e["tJ"] if spec["exit"] == "J" else e["tR"]
            for c in names:
                if c not in M.ix:
                    continue
                j = M.ix[c]
                r = M.trade(j, t_in, t_out, "close", mult)
                if not np.isfinite(r):
                    continue
                cr = [M.trade(k, t_in, t_out, "close", mult) for k in controls(i, e, j, t_in)]
                cr = [x for x in cr if np.isfinite(x)]
                if not cr:
                    continue
                rows.append({"ev": i, "rv": e["rv"], "year": e["year"], "code": c, "net": r, "ctrl": float(np.mean(cr)),
                             "ex": r - float(np.mean(cr)), "days": t_out - t_in, "is_add": c in e["adds"]})
        return pd.DataFrame(rows)

    summarize = LP.summarize
    res, frames = {}, {}
    for name, spec in TRIALS.items():
        frames[name] = trade_rows(spec)
        res[name] = summarize(frames[name])
    base = TRIALS[MAIN]
    frames["M3 costs x1.5"] = trade_rows(base, 1.5)
    res["M3 costs x1.5"] = summarize(frames["M3 costs x1.5"])
    actual = [e["adds"] for e in trade_revs]
    frames["fact: perfect foresight, T5 -> jump"] = trade_rows(TRIALS["M1_T5_jump"], pick=actual)
    frames["fact: perfect foresight, T5 -> R"] = trade_rows(base, pick=actual)
    frames["fact: DRIFT actual adds, J close -> R close"] = trade_rows(dict(k=0, T=0, exit="R"), pick=actual, entry_off=lambda e: e["tJ"])
    all_revs = [e for e in revs if e["cpos"] >= 60]
    for e in all_revs:
        if "nm" not in e:
            e["nm"] = pd.DataFrame(index=[])
    frames["fact: DRIFT deletions (all 18), J close -> R close"] = trade_rows(dict(k=0, T=0, exit="R"), pick=[e["dels"] for e in all_revs],
                                                                            entry_off=lambda e: e["tJ"], revlist=all_revs)
    # descriptive split added AFTER the first run (not a trial): deletions outside the 2026 freeze / HSC reviews
    fdel = frames["fact: DRIFT deletions (all 18), J close -> R close"]
    frames["fact: DRIFT deletions, 2020-2025 only (post-hoc split)"] = fdel[fdel["year"] <= 2025]
    for k in [k for k in frames if k.startswith("fact")] + ["M3 costs x1.5"]:
        res[k] = summarize(frames[k])
    # announcement reaction (gross), actual adds
    rr = []
    for i, e in enumerate(trade_revs):
        for c in e["adds"]:
            if c not in M.ix:
                continue
            j = M.ix[c]
            g = M.gross(j, e["tJ"] - 1, e["tJ"])
            cg = [M.gross(k, e["tJ"] - 1, e["tJ"]) for k in controls(i, e, j, e["tJ"] - 1)]
            cg = [x for x in cg if np.isfinite(x)]
            if np.isfinite(g) and cg:
                rr.append({"ev": i, "rv": e["rv"], "year": e["year"], "code": c, "net": g, "ctrl": float(np.mean(cg)), "ex": g - float(np.mean(cg)),
                           "days": 1, "is_add": True})
    frames["fact: announcement reaction (J-1 -> J close, gross)"] = pd.DataFrame(rr)
    res["fact: announcement reaction (J-1 -> J close, gross)"] = summarize(frames["fact: announcement reaction (J-1 -> J close, gross)"])
    for n in res:
        print(n, {k: (round(v, 4) if isinstance(v, float) else v) for k, v in res[n].items()})

    # placebo
    rng = np.random.default_rng(SEED)
    pools = [list(e["nm"].index[3:20]) for e in trade_revs]
    pool_rows = trade_rows(base, pick=pools)
    by = {(r.ev, r.code): r.ex for r in pool_rows.itertuples()}
    pl = []
    for _ in range(N_PLACEBO):
        means = []
        for i, pool in enumerate(pools):
            if not pool:
                continue
            draw = rng.choice(len(pool), size=min(3, len(pool)), replace=False)
            xs = [by[(i, pool[d])] for d in draw if (i, pool[d]) in by]
            if xs:
                means.append(np.mean(xs))
        pl.append(float(np.mean(means)))
    pl = np.array(pl)
    s1 = res[MAIN]
    real = s1["ex"]
    pct = float((pl < real).mean() * 100)
    placebo = {"median": float(np.median(pl)), "p95": float(np.percentile(pl, 95)), "pct": pct}
    n_cum = N_BEFORE + N_TRIALS
    g1 = frames[MAIN].groupby("ev")["ex"].mean().to_numpy()
    d = LP.dsr(g1, n_cum)
    halves = {}
    for lab, lo, hi in (("2020-22", 2020, 2022), ("2023-25", 2023, 2025)):
        f_ = frames[MAIN]
        halves[lab] = summarize(f_[(f_["year"] >= lo) & (f_["year"] <= hi)])
    bar = {"ex>0": s1["ex"] > 0, "t>=2": s1["t_ev"] >= 2.0, "net>0": s1["net"] > 0, "ev_pos>=60%": s1["ev_pos"] >= 0.6, "placebo>=95": pct >= 95}
    passed = all(bar.values())
    verdict = "PARTIAL (few events)" if passed else "CLOSED"
    print("placebo", placebo, "bar", bar, verdict, "dsr", d)

    # ---- current ranking (next review: Nov 2026; freeze in force) -------------------------------------------------------------
    cur_members = set(AFTER_AUG26.split())
    Fnow, _ = features(len(dates) - 1)
    nm_now = Fnow[Fnow["elig"] & ~Fnow.index.isin(cur_members)].sort_values("full", ascending=False).head(8)

    # ---- report ------------------------------------------------------------------------------------------------------------
    def f(x):
        return "-" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x * 1e4:+.0f}"

    L = [f"# IDX menu 47 - predicting MSCI Indonesia (Standard) additions - 2026-09-26 - {N_TRIALS} trials, cumulative N = {n_cum}", "",
         f"**Verdict: {verdict}.** Pre-registered in `research/idx_msci_predict.py` (docstring written before any return was computed).", "",
         "## Events (MSCI's own change lists)", "",
         f"27 quarterly reviews Feb 2020 -> Aug 2026 sourced from MSCI's public change-list PDFs (`{SRC.format('<Mon><YY>')}`, and the "
         "SCPublicList twin for Small Cap), cross-checked against the press (sources in the docstring). 18 reviews changed the Standard index; "
         f"**10 added names (15 adds)**; 3 (Feb/May/Aug 2026) fell under MSCI's Indonesia freeze (2026-01-27: no IMI additions, no upward "
         "migrations) and are not traded. Membership chained backward from the post-Aug-2026 list of 9 and consistent at every step.", "",
         "| review | announced (US) | J (1st IDX session after) | R (as-of close) | Standard adds | Standard deletions | Small Cap adds / dels | members before |",
         "|---|---|---|---|---|---|---|---|"]
    for e in revs:
        L.append(f"| {e['rv']}{' (freeze)' if e['freeze'] else ''} | {e['A']} | {dates[e['tJ']].date() if e['tJ'] < len(dates) else '-'} | "
                 f"{dates[e['tR']].date()} | {' '.join(e['adds']) or '-'} | {' '.join(e['dels']) or '-'} | {e['sca']} / {e['scd']} | {len(e['before'])} |")
    L += ["", "## Step 1 - can the published rule see the adds? (classification, not a trial)", "",
          f"Pooled over {agg['n_reviews']} traded reviews ({agg['tot_adds']} adds in {agg['n_add_reviews']} reviews): precision@1 {agg['prec1']*100:.0f} %, "
          f"precision@3 **{agg['prec3']*100:.0f} %**, precision@5 {agg['prec5']*100:.0f} %; recall@1 {agg['rec1']*100:.0f} %, recall@3 **{agg['rec3']*100:.0f} %**, "
          f"recall@5 {agg['rec5']*100:.0f} %. Precision@3 on the reviews that had adds only: {agg['prec3_add_reviews']*100:.0f} %. "
          f"Rule-pass set (size >= 1.5/1.8 x C^, FF floor): {agg['rule_n']} names, precision {agg['rule_prec']*100:.0f} %, recall {agg['rule_rec']*100:.0f} %.", "",
          "| review | price cut-off | C^ (USD bn, 3 smallest members) | FF published | adds (rank among eligible non-members) | top-5 predicted | hits@3 | rule-pass |",
          "|---|---|---|---|---|---|---|---|"]
    for r in cls_rows:
        ar_ = ", ".join(f"{a} {v}" for a, v in r["add_rank"].items()) or "-"
        L.append(f"| {r['rv']} | {r['cut']} | {r['chat']/1e9:.2f} | {'yes' if r['pub'] else 'no'} | {ar_} | {' '.join(r['top5'])} | {r['hit3']} | {' '.join(r['rule']) or '-'} |")
    L += ["", "## Step 2 - trades (bps per trade; excess vs 5 matched controls; t over reviews)", "",
          "| arm | trades | reviews | hit rate (true adds) | net mean | net median | win | controls | excess (review mean) | t (reviews) | reviews > 0 | days |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for n, s in res.items():
        if s.get("n", 0) == 0:
            L.append(f"| {n} | 0 | 0 | - | - | - | - | - | - | - | - | - |")
            continue
        L.append(f"| {n} | {s['n']} | {s['n_ev']} | {s['hit']*100:.0f} % | {f(s['net'])} | {f(s['net_med'])} | {s['win']*100:.0f} % | {f(s['ctrl'])} | "
                 f"{f(s['ex'])} | {s['t_ev']:.2f} | {s['ev_pos']*100:.0f} % | {s['days']:.1f} |")
    L += ["", f"Placebo (3 random eligible non-members from score ranks 4-20 per review, {N_PLACEBO} draws): real {f(real)}, median {f(placebo['median'])}, "
          f"95th pct {f(placebo['p95'])}, real's percentile **{pct:.0f}**.", "", f"DSR of the per-review M3 excess at N = {n_cum}: {d:.3f}.", "",
          "Halves (M3): " + "; ".join(f"{k}: {v.get('n', 0)} trades, excess {f(v.get('ex'))}, t {v.get('t_ev', float('nan')):.2f}" for k, v in halves.items()), "",
          "BAR (M3): " + ", ".join(f"{k} {'pass' if v else 'FAIL'}" for k, v in bar.items()) + f" -> **{verdict}**.", "",
          "## Per review (M3 picks; actual-add drift J -> R) (bps, net / excess, * = true add)", "", "| review | M3 picks | actual adds: J close -> R close |", "|---|---|---|"]
    fm, fd = frames[MAIN], frames["fact: DRIFT actual adds, J close -> R close"]
    for i, e in enumerate(trade_revs):
        a = ", ".join(f"{r.code}{'*' if r.is_add else ''} {r.net*1e4:+.0f}/{r.ex*1e4:+.0f}" for r in fm[fm["ev"] == i].itertuples()) or "-"
        b = ", ".join(f"{r.code} {r.net*1e4:+.0f}/{r.ex*1e4:+.0f}" for r in fd[fd["ev"] == i].itertuples()) or "-"
        L.append(f"| {e['rv']} | {a} | {b} |")
    L += ["", "## Current ranking (next review Nov 2026; the freeze is still in force - no adds expected)", "",
          f"Data through {dates[-1].date()}. Largest eligible non-members by full mcap (USD bn): " +
          ", ".join(f"{c} {r.full/1e9:.1f}" for c, r in nm_now.iterrows()) + ".", ""]
    open(OUT + ".auto", "w", encoding="utf-8").write("\n".join(L))
    print("\n".join(L))

    summary = {"classification": agg, "arms": res, "placebo": placebo, "dsr": d, "bar": bar, "verdict": verdict, "halves": halves, "n_cum": n_cum,
               "reviews": [{k: v for k, v in r.items()} for r in cls_rows]}
    names = [{"code": c, "screens": ["msci_predict"], "score": float(r.full) / 1e9, "rank": i + 1,
              "features": {"full_usd": float(r.full), "ff_usd": float(r.ffm), "atvr12": float(r.atvr12)}} for i, (c, r) in enumerate(nm_now.iterrows())]
    if os.environ.get("RECORD") == "1":
        sid = rs.record_study(conn, STUDY, date(2026, 9, 26), params={"trials": TRIALS, "n_before": N_BEFORE, "n_trials": N_TRIALS, "reviews": REVIEWS},
                              summary=json.loads(json.dumps(summary, default=str)), names=names, report_path="research/IDX_MSCI_PREDICT_2026-09-26.md",
                              note=f"menu 47: predict MSCI Indonesia Standard adds; M3 excess {real*1e4:+.0f} bps t {s1['t_ev']:.2f}; {verdict}")
        print("study id", sid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
