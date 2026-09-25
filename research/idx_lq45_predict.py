#!/usr/bin/env python3
"""IDX menu 42 - PREDICTING LQ45 adds before the announcement (study 'lq45_predict', 2026-09-25).

Menu 36 (#186) found the LQ45-add premium is real (+295 bps over matched controls on the announcement day, t 3.34, 14/16
events) but fully priced at the next open. The only door left: know the adds BEFORE the notice (the LQ45 rule is public) and
hold into it.

MEMBERSHIP (point in time). IDX has no constituent table in the DB, so membership is rebuilt from a seed + every change:
  seed = LQ45 Feb-Jul 2020 (45 names) minus the 2020-01 adds plus its deletions = the Aug 2019 - Jan 2020 list;
  changes = menu 36's 17 evaluations PLUS three changes menu 36 did not list, sourced 2026-09-25 by web search:
    2021-09-22 fast entry BUKA for SMRA (CNBC Indonesia 20210923123350-17-278577, eff. 2021-09-29)
    2022-06-01 fast entry GOTO for WSKT (market.bisnis.com 20220601/7/1538939, eff. 2022-06-08)
    2024-04-24 evaluation AMMN ISAT in, EMTK PTMP out (market.bisnis.com 20240424/7/1760213, eff. 2024-05-02)
  and the 2025-04-24 evaluation with NO LQ45 change (market.bisnis.com 20250425/7/1872002, eff. 2025-05-02).
  Check: applying all changes in order keeps 45 names at every step, every deletion is a member and every add a non-member,
  and the end state equals the Aug-Oct 2026 list (en.wikipedia.org/wiki/LQ45 + NCKL). Fast entries (IPO fast track) are not
  predicted or traded; they only keep the membership right.
REVIEWS PREDICTED / TRADED: every scheduled evaluation whose review window is covered by idx.bar (starts 2020-01-02):
  2020-07 (6-month window only), semi-annual Jan/Jul to 2024-01, quarterly from 2024-04 (IDX methodology change, eff. 2024-05):
  18 reviews (17 with LQ45 changes + 2025-04 with none). 2020-01 is out (no data before its cut-off). Pre-2024 Apr/Oct minor
  windows are not traded (whether LQ45 was reviewed then is not sourced) - recorded as a limit.

RULE SCORE (all inputs known at the review CUT-OFF c = last trading day of the calendar month before the announcement month):
  window = the 12 months to c (2020-07: the 6 months available). idx.daily_summary regular-market value and frequency.
  eligible: first trading day in the data <= c - 3 months; point-in-time board (daily_summary.remarks, 5th char; 2020 8-char
    notation = last char; forward-filled) in Utama/Pengembangan; no special-notation letter in remarks[18:30] at c (letters
    other than '-', 'K' - K is the multiple-voting-share marker GOTO carries while a member); days traded >= 90 % of window
    sessions; free-float ratio (weight_for_index / listed_shares) >= 7.5 % where IDX publishes it (cross-sectional median
    ratio < 0.99; before ~2021-22 weight_for_index = listed shares and full market cap is used).
  score = mean percentile rank (among eligible) of 12-month traded value, 12-month frequency and free-float market cap at c.
  predicted adds = eligible NON-members ordered by score; top-k.
STEP 1 (classification, not a trial): per review, precision@k (k = 3, 5) and recall@k of the top-k non-members vs the actual
  adds, the actual adds' rank among non-members, and the 'in-rank' set (non-members inside the overall top 45 by score).
  If precision@5 < ~30 % the trade dilutes the +3 % jump across non-adds - said up front.

STEP 2 (trade) PRE-REGISTERED, written before any return was computed. 7 trials; cumulative N_BEFORE 896 + 7 = 903.
  Expected dates without look-ahead: E^ = first trading day of the effective month (Feb/May/Aug/Nov; the actual E in all 18),
  A^ = E^ - 5 sessions. Entry = closing offer at A^ - T sessions; exit = closing bid at the close of the first session after
  the ACTUAL announcement A (the jump day; the notice is public by then). Costs, controls, t: exactly menu 36
  (idx_index_rebalance.Mkt.trade: closing offer/bid or +-1 tick, fees 0.10/0.20 %, 70 bps floor; 5 controls matched on log
  market cap and log 60-day median value at ENTRY among non-members not changed and not predicted; excess = net - mean
  control net; t = event-clustered, one mean per review; a review with no trade is skipped).
    P1 MAIN   top-5, T = 5
    P2        top-5, T = 10
    P3        top-3, T = 5
    P4        'in-rank' set (non-members inside the overall top 45 by score, at most 8), T = 5
    P5        top-5, T = 5, exit at R = the rebalance close (last session before E) instead of A+1
    P6        top-5, T = 5, entry one session LATE (1-day delay)
    P7        top-5, T = 5, score = 12-month traded value rank only (liquidity-only rule)
  Stresses on P1 (not trials): costs x 1.5; halves 2020-22 / 2023-26; placebo: each review's top-5 replaced by 5 random
  eligible non-members from ranks 6..25 (the similar rank band), 1000 draws, event-clustered excess; perfect-foresight
  ceiling (the ACTUAL adds, same window) as a fact; DSR of the per-review excess series at N = 903.
BAR (P1): event-clustered mean excess > 0 with t >= 2.0 AND mean net per trade > 0 AND excess > 0 in >= 60 % of reviews AND
  placebo percentile >= 95. Pass -> PARTIAL at best (18 reviews); then daily return series correlation with the combo sleeves
  (idx_combo_rupiah) and the Rp contribution on a Rp 20 M book. Fail -> CLOSED.
READ-ONLY; one idx.study row ('lq45_predict') whose names are the current top-10 predicted adds for the next review.
INGEST_DB_DSN (or blackheart-ingest/idx-local.env).
"""
from __future__ import annotations

import json
import math
import os
import sys
from datetime import date
from statistics import NormalDist

import numpy as np
import pandas as pd
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blackheart-ingest", "src"))
import idx_index_rebalance as IR  # noqa: E402  (read-only import: Mkt pricing/costs/matching, EVENTS)
from blackheart_ingest.idx import research_store as rs  # noqa: E402

N_BEFORE = 896
N_TRIALS = 7
STUDY = "lq45_predict"
SEED = 20260925
N_PLACEBO = 1000
OUT = os.path.join(HERE, "IDX_LQ45_PREDICT_2026-09-25.md")

SEED_FEB2020 = ("ACES ADRO AKRA ANTM ASII BBCA BBNI BBRI BBTN BMRI BRPT BSDE BTPS CPIN CTRA ERAA EXCL GGRM HMSP ICBP INCO INDF "
                "INKP INTP ITMG JPFA JSMR KLBF LPPF MNCN PGAS PTBA PTPP PWON SCMA SMGR SRIL TBIG TKIM TLKM TOWR UNTR UNVR WIKA WSKT")
CURRENT_2026_08 = ("AADI ADMR ADRO AKRA AMMN AMRT ANTM ASII BBCA BBNI BBRI BBTN BMRI BRPT BUMI CPIN CUAN DEWA EMTK ESSA EXCL GOTO HRTA "
                   "ICBP INCO INDF INDY INKP ISAT ITMG JPFA KLBF MAPI MBMA MDKA MEDC NCKL PGAS PGEO PTBA SCMA TLKM UNTR UNVR WIFI")
EXTRA = [  # (A, E, adds, dels, source, kind)
    ("2021-09-22", "2021-09-29", "BUKA", "SMRA", "cnbcindonesia.com/market/20210923123350-17-278577", "fast"),
    ("2022-06-01", "2022-06-08", "GOTO", "WSKT", "market.bisnis.com/read/20220601/7/1538939", "fast"),
    ("2024-04-24", "2024-05-02", "AMMN ISAT", "EMTK PTMP", "market.bisnis.com/read/20240424/7/1760213", "review"),
    ("2025-04-24", "2025-05-02", "", "", "market.bisnis.com/read/20250425/7/1872002 (no LQ45 change)", "review"),
]
TRIALS = {
    "P1_main": dict(k=5, T=5),
    "P2_T10": dict(k=5, T=10),
    "P3_top3": dict(k=3, T=5),
    "P4_inrank": dict(k="inrank", T=5),
    "P5_exit_R": dict(k=5, T=5, exit="R"),
    "P6_delay1": dict(k=5, T=5, delay=1),
    "P7_value_only": dict(k=5, T=5, score="value"),
}
NOTATION_OK = set("-K")


def all_events():
    ev = [(A, E, a, d, s, "review") for A, E, a, d, s in IR.EVENTS] + EXTRA
    return sorted(ev, key=lambda x: x[0])


def membership():
    """-> list of dicts per event with 'before' membership; asserts the chain is consistent."""
    m = set(SEED_FEB2020.split())
    first = IR.EVENTS[0]
    m = (m - set(first[2].split())) | set(first[3].split())
    out = []
    for A, E, a, d, s, kind in all_events():
        a, d = a.split(), d.split()
        assert len(m) == 45 and all(x in m for x in d) and not any(x in m for x in a), (A, a, d)
        out.append({"A": A, "E": E, "adds": a, "dels": d, "src": s, "kind": kind, "before": set(m)})
        m = (m - set(d)) | set(a)
    assert m == set(CURRENT_2026_08.split()), (m ^ set(CURRENT_2026_08.split()))
    return out, m


def load_summary(conn, dates, cols):
    q = """SELECT trade_date, code, value::float v, frequency::float f, listed_shares::float sh, weight_for_index::float w,
                  close::float c, remarks FROM idx.daily_summary WHERE trade_date >= '2020-01-01'"""
    df = pd.DataFrame(conn.execute(q).fetchall(), columns=["d", "code", "v", "f", "sh", "w", "c", "rm"])
    df["d"] = pd.to_datetime(df["d"])
    rm = df["rm"].fillna("")
    d5, old = rm.str[4], rm.str[-1]
    df["b"] = np.where(d5.isin(list("12345")), d5, np.where((rm.str.len() == 8) & old.isin(list("123")), old, None))
    df["nt"] = rm.apply(lambda r: float(any(ch not in NOTATION_OK for ch in r[18:30])) if len(r) >= 30 else 0.0)
    P = {}
    for k in ("v", "f", "sh", "w", "c", "nt"):
        P[k] = df.pivot(index="d", columns="code", values=k).reindex(index=dates, columns=cols)
    B = df.pivot(index="d", columns="code", values="b").reindex(index=dates, columns=cols).ffill()
    P["board_ok"] = B.isin({"1", "2"})
    P["present"] = P["c"].notna()
    return P


def score_at(P, dates, c_pos: int, kind: str = "full"):
    """-> DataFrame per eligible code at cut-off index c_pos with score components."""
    c_day = dates[c_pos]
    start = max(0, int(np.searchsorted(dates, c_day - pd.DateOffset(months=12), side="right")))
    win = slice(start, c_pos + 1)
    nwin = c_pos + 1 - start
    V = P["v"].iloc[win]
    val = V.sum(min_count=1)
    frq = P["f"].iloc[win].sum(min_count=1)
    days = (V.fillna(0) > 0).sum() / nwin
    first = P["present"].idxmax()  # first date present (data starts 2020-01-02)
    age_ok = first <= c_day - pd.DateOffset(months=3)
    sh, w, cl = P["sh"].iloc[c_pos], P["w"].iloc[c_pos], P["c"].iloc[c_pos]
    ratio = w / sh
    ff_pub = float(np.nanmedian(ratio.values)) < 0.99
    ffm = cl * (w if ff_pub else sh)
    elig = (age_ok & P["board_ok"].iloc[c_pos] & (P["nt"].iloc[c_pos].fillna(0) == 0) & (days >= 0.9) & val.gt(0) & cl.gt(0)
            & ffm.gt(0) & P["present"].iloc[c_pos])
    if ff_pub:
        elig &= ratio.fillna(0) >= 0.075
    df = pd.DataFrame({"val": val, "frq": frq, "ffm": ffm, "days": days, "ff": ratio})[elig.fillna(False)]
    if kind == "value":
        df["score"] = df["val"].rank(pct=True)
    else:
        df["score"] = (df["val"].rank(pct=True) + df["frq"].rank(pct=True) + df["ffm"].rank(pct=True)) / 3
    df = df.sort_values("score", ascending=False)
    df["rank_all"] = np.arange(1, len(df) + 1)
    return df, nwin, ff_pub


def cutoff_pos(dates, A: str) -> int:
    a = pd.Timestamp(A)
    first_of_month = a.replace(day=1)
    return int(np.searchsorted(dates, first_of_month, side="left")) - 1


def dsr(r: np.ndarray, n_trials: int) -> float:
    r = r[np.isfinite(r)]
    n = len(r)
    if n < 3 or r.std() == 0:
        return 0.0
    mu, sd = r.mean(), r.std()
    sr = mu / sd
    sk = ((r - mu) ** 3).mean() / sd ** 3
    ku = ((r - mu) ** 4).mean() / sd ** 4
    Z, e = NormalDist(), 0.5772156649015329
    v = (1 - sk * sr + (ku - 1) / 4.0 * sr ** 2) / (n - 1)
    if v <= 0:
        return 0.0
    se = math.sqrt(v)
    emax = Z.inv_cdf(1 - 1.0 / n_trials) * (1 - e) + Z.inv_cdf(1 - 1.0 / (n_trials * math.e)) * e
    return Z.cdf((sr - se * emax) / se)


def summarize(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"n": 0, "n_ev": 0}
    g = df.groupby("ev")["ex"].mean()
    n = len(g)
    t_ev = float(g.mean() / g.std(ddof=1) * np.sqrt(n)) if n > 1 and g.std(ddof=1) > 0 else float("nan")
    return {"n": int(len(df)), "n_ev": int(n), "net": float(df["net"].mean()), "net_med": float(df["net"].median()),
            "win": float((df["net"] > 0).mean()), "ctrl": float(df["ctrl"].mean()), "ex": float(g.mean()), "t_ev": t_ev,
            "ev_pos": float((g > 0).mean()), "hit": float(df["is_add"].mean()), "days": float(df["days"].mean())}


def main() -> int:
    conn = psycopg.connect(IR.dsn())
    evs, _ = membership()
    W = IR.load(conn)
    M = IR.Mkt(W)
    dates = M.dates
    P = load_summary(conn, dates, M.codes)
    reviews = [e for e in evs if e["kind"] == "review" and e["A"] >= "2020-07-01"]

    # ---- step 1: classification --------------------------------------------------------------------------------------------
    cls_rows = []
    for e in reviews:
        cpos = cutoff_pos(dates, e["A"])
        e["cpos"] = cpos
        e["tA"] = M.pos_after(e["A"], 0)
        e["tE"] = M.pos_on_or_after(e["E"])
        first_of_eff = pd.Timestamp(e["E"]).replace(day=1)
        e["tEhat"] = int(np.searchsorted(dates, first_of_eff, side="left"))
        e["tAhat"] = e["tEhat"] - 5
        e["year"] = int(e["A"][:4])
        for kind in ("full", "value"):
            sc, nwin, ffp = score_at(P, dates, cpos, kind)
            nm = sc[~sc.index.isin(e["before"])].copy()
            nm["rank_nm"] = np.arange(1, len(nm) + 1)
            e[f"nm_{kind}"] = nm
            e[f"inrank_{kind}"] = list(nm[nm["rank_all"] <= 45].index[:8])
            if kind == "full":
                e["nwin"], e["ffpub"] = nwin, ffp
                mem_rank = sc[sc.index.isin(e["before"])]["rank_all"]
                e["mem_out45"] = int((mem_rank > 45).sum())
                e["mem_inelig"] = int(len(e["before"]) - len(mem_rank))
        nm = e["nm_full"]
        adds = e["adds"]
        row = {"A": e["A"], "cut": str(dates[cpos].date()), "win": e["nwin"], "n_adds": len(adds),
               "adds_rank": {a: (int(nm.loc[a, "rank_nm"]) if a in nm.index else None) for a in adds}}
        for k in (3, 5, 10):
            top = list(nm.index[:k])
            hit = len(set(top) & set(adds))
            row[f"p{k}"] = hit / k
            row[f"r{k}"] = hit / len(adds) if adds else float("nan")
            row[f"hit{k}"] = hit
            row[f"top{k}"] = top
        ir = e["inrank_full"]
        row["inrank"] = ir
        row["inrank_hit"] = len(set(ir) & set(adds))
        nmv = e["nm_value"]
        row["p5_value"] = len(set(nmv.index[:5]) & set(adds)) / 5
        row["mem_out45"], row["mem_inelig"] = e["mem_out45"], e["mem_inelig"]
        cls_rows.append(row)
    cls = pd.DataFrame(cls_rows)
    tot_adds = int(cls["n_adds"].sum())
    agg = {f"prec{k}": float(cls[f"hit{k}"].sum() / (k * len(cls))) for k in (3, 5, 10)}
    agg.update({f"rec{k}": float(cls[f"hit{k}"].sum() / tot_adds) for k in (3, 5, 10)})
    agg["inrank_prec"] = float(cls["inrank_hit"].sum() / max(1, sum(len(x) for x in cls["inrank"])))
    agg["inrank_rec"] = float(cls["inrank_hit"].sum() / tot_adds)
    agg["inrank_n"] = int(sum(len(x) for x in cls["inrank"]))
    agg["prec5_value"] = float(cls["p5_value"].mean())
    # POST-HOC, descriptive only (added after step 1 was seen, never traded): drop 'snubbed' names - eligible non-members that
    # were in the previous review's top-10 predicted and were not added - then re-measure precision@5.
    hit_s, n_s, prev = 0, 0, None
    for e in reviews:
        nm = e["nm_full"]
        snub = set() if prev is None else {c for c in prev["nm_full"].index[:10] if c not in prev["adds"]}
        top = [c for c in nm.index if c not in snub][:5]
        hit_s += len(set(top) & set(e["adds"]))
        n_s += 5
        prev = e
    agg["prec5_posthoc_snub"] = hit_s / n_s
    ipo_inelig = sum(1 for r in cls_rows for v in r["adds_rank"].values() if v is None)
    agg["adds_ineligible"] = ipo_inelig
    agg["prec5_if_inelig_all_hit"] = float((cls["hit5"].sum() + ipo_inelig) / (5 * len(cls)))
    agg["tot_adds"] = tot_adds
    agg["n_reviews"] = len(cls)
    print("classification", json.dumps(agg, indent=1))

    # ---- step 2: trades ---------------------------------------------------------------------------------------------------
    ctrl_cache: dict = {}

    def controls(i, e, j, t_in, predicted):
        key = (i, j, t_in)
        if key not in ctrl_cache:
            excl = {M.ix[c] for c in list(e["before"]) + e["adds"] + e["dels"] + list(predicted) if c in M.ix}
            excl.discard(j)
            ctrl_cache[key] = [k for k in M.matched(j, t_in, excl, 5) if k != j]
        return ctrl_cache[key]

    def trade_rows(spec, mult=1.0, pick=None):
        rows = []
        for i, e in enumerate(reviews):
            kind = spec.get("score", "full")
            nm = e[f"nm_{kind}"]
            if pick is not None:
                names = pick[i]
            elif spec["k"] == "inrank":
                names = e[f"inrank_{kind}"]
            else:
                names = list(nm.index[:spec["k"]])
            t_in = e["tAhat"] - spec["T"] + spec.get("delay", 0)
            t_out = e["tE"] - 1 if spec.get("exit") == "R" else e["tA"] + 1
            assert t_in <= e["tA"], (e["A"], t_in, e["tA"])
            predicted = list(nm.index[:10])
            for c in names:
                if c not in M.ix:
                    continue
                j = M.ix[c]
                r = M.trade(j, t_in, t_out, "close", mult)
                if not np.isfinite(r):
                    continue
                cr = [M.trade(k, t_in, t_out, "close", mult) for k in controls(i, e, j, t_in, predicted)]
                cr = [x for x in cr if np.isfinite(x)]
                if not cr:
                    continue
                rows.append({"ev": i, "A": e["A"], "year": e["year"], "code": c, "net": r, "ctrl": float(np.mean(cr)),
                             "ex": r - float(np.mean(cr)), "days": t_out - t_in, "is_add": c in e["adds"]})
        return pd.DataFrame(rows)

    res, frames = {}, {}
    for name, spec in TRIALS.items():
        frames[name] = trade_rows(spec)
        res[name] = summarize(frames[name])
    base = TRIALS["P1_main"]
    frames["P1 costs x1.5"] = trade_rows(base, 1.5)
    res["P1 costs x1.5"] = summarize(frames["P1 costs x1.5"])
    frames["fact: perfect foresight (actual adds)"] = trade_rows(base, pick=[e["adds"] for e in reviews])
    res["fact: perfect foresight (actual adds)"] = summarize(frames["fact: perfect foresight (actual adds)"])
    for n in list(res):
        print(n, {k: (round(v, 4) if isinstance(v, float) else v) for k, v in res[n].items()})

    # placebo: 5 random non-members from ranks 6..25 per review
    rng = np.random.default_rng(SEED)
    pools = [list(e["nm_full"].index[5:25]) for e in reviews]
    pool_rows = trade_rows(base, pick=pools)
    by = {(r.ev, r.code): r.ex for r in pool_rows.itertuples()}
    pl = []
    for _ in range(N_PLACEBO):
        means = []
        for i, pool in enumerate(pools):
            draw = rng.choice(len(pool), size=min(5, len(pool)), replace=False)
            xs = [by[(i, pool[d])] for d in draw if (i, pool[d]) in by]
            if xs:
                means.append(np.mean(xs))
        pl.append(float(np.mean(means)))
    pl = np.array(pl)
    real = res["P1_main"]["ex"]
    pct = float((pl < real).mean() * 100)
    placebo = {"median": float(np.median(pl)), "p95": float(np.percentile(pl, 95)), "pct": pct}
    print("placebo", placebo)

    g1 = frames["P1_main"].groupby("ev")["ex"].mean().to_numpy()
    n_cum = N_BEFORE + N_TRIALS
    d = dsr(g1, n_cum)
    halves = {}
    for lab, lo, hi in (("2020-22", 2020, 2022), ("2023-26", 2023, 2026)):
        f = frames["P1_main"]
        halves[lab] = summarize(f[(f["year"] >= lo) & (f["year"] <= hi)])
    s1 = res["P1_main"]
    bar = {"ex>0": s1["ex"] > 0, "t>=2": s1["t_ev"] >= 2.0, "net>0": s1["net"] > 0, "ev_pos>=60%": s1["ev_pos"] >= 0.6,
           "placebo>=95": pct >= 95}
    passed = all(bar.values())
    verdict = "PARTIAL (small n)" if passed else "CLOSED"
    print("bar", bar, verdict, "dsr", d)

    # ---- current prediction (next review, announcement late Oct 2026) --------------------------------------------------------
    _, cur_members = membership()
    sc_now, _, _ = score_at(P, dates, len(dates) - 1, "full")
    nm_now = sc_now[~sc_now.index.isin(cur_members)].head(10)
    mem_weak = sc_now[sc_now.index.isin(cur_members)].tail(5)

    # ---- report -------------------------------------------------------------------------------------------------------------
    def f(x, pctg=False):
        if x is None or (isinstance(x, float) and not np.isfinite(x)):
            return "-"
        return f"{x * 100:.0f} %" if pctg else f"{x * 1e4:+.0f}"

    L = [f"# IDX menu 42 - predicting LQ45 adds before the announcement - 2026-09-25 - {N_TRIALS} trials, cumulative N = {n_cum}", "",
         f"**Verdict: {verdict}.** Pre-registered in `research/idx_lq45_predict.py` (docstring written before any return was computed).", "",
         f"Reviews: {len(reviews)} scheduled LQ45 evaluations 2020-07 -> 2026-07 ({tot_adds} adds; 2025-04 had none). Membership rebuilt point in time "
         "from the Feb-2020 list + menu 36's events + three changes menu 36 missed (2021-09 BUKA<-SMRA fast entry, 2022-06 GOTO<-WSKT fast entry, "
         "2024-04 AMMN ISAT in / EMTK PTMP out); the chain stays at 45 names at every step and ends on the published Aug-2026 list.", "",
         "## Step 1 - can the rule see the adds? (classification, not a trial)", "",
         f"Pooled over {len(cls)} reviews: precision@3 {agg['prec3']*100:.0f} %, precision@5 **{agg['prec5']*100:.0f} %**, precision@10 {agg['prec10']*100:.0f} %; "
         f"recall@3 {agg['rec3']*100:.0f} %, recall@5 **{agg['rec5']*100:.0f} %**, recall@10 {agg['rec10']*100:.0f} %. "
         f"'In-rank' set (non-members inside the overall top 45): {agg['inrank_n']} names, precision {agg['inrank_prec']*100:.0f} %, recall {agg['inrank_rec']*100:.0f} %. "
         f"Liquidity-only score: precision@5 {agg['prec5_value']*100:.0f} %.", "",
         "| A | cut-off | window (sessions) | adds (rank among eligible non-members) | top-5 predicted | hits@5 | in-rank set | members ranked > 45 / ineligible |",
         "|---|---|---|---|---|---|---|---|"]
    for r in cls_rows:
        ar = ", ".join(f"{a} {('#' + str(v)) if v else 'inelig.'}" for a, v in r["adds_rank"].items()) or "(no change)"
        L.append(f"| {r['A']} | {r['cut']} | {r['win']} | {ar} | {' '.join(r['top5'])} | {r['hit5']} | {' '.join(r['inrank']) or '-'} | {r['mem_out45']} / {r['mem_inelig']} |")
    L += ["", "## Step 2 - buy the predicted adds before the notice, sell on the jump day (bps per trade; t over reviews)", "",
          "| arm | trades | reviews | hit rate (true adds) | net mean | net median | win | controls | excess (review mean) | t (reviews) | reviews > 0 | days |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for n, s in res.items():
        if s.get("n", 0) == 0:
            L.append(f"| {n} | 0 | 0 | - | - | - | - | - | - | - | - | - |")
            continue
        L.append(f"| {n} | {s['n']} | {s['n_ev']} | {s['hit']*100:.0f} % | {f(s['net'])} | {f(s['net_med'])} | {s['win']*100:.0f} % | {f(s['ctrl'])} | "
                 f"{f(s['ex'])} | {s['t_ev']:.2f} | {s['ev_pos']*100:.0f} % | {s['days']:.1f} |")
    L += ["", f"Placebo (5 random eligible non-members from ranks 6-25 per review, {N_PLACEBO} draws): real excess {f(real)}, median {f(placebo['median'])}, "
          f"95th pct {f(placebo['p95'])}, real's percentile **{pct:.0f}**.", "",
          f"DSR of the per-review excess series at N = {n_cum}: {d:.3f}.", "",
          "Halves (P1): " + "; ".join(f"{k}: {v.get('n', 0)} trades, excess {f(v.get('ex'))}, t {v.get('t_ev', float('nan')):.2f}" for k, v in halves.items()), "",
          "BAR (P1): excess > 0, t >= 2, net > 0, >= 60 % reviews positive, placebo >= 95th pct -> " + ", ".join(f"{k} {'pass' if v else 'FAIL'}" for k, v in bar.items())
          + f" -> **{verdict}**.", "",
          "## P1 per review (bps)", "", "| A | names: net / excess (* = true add) |", "|---|---|"]
    fr = frames["P1_main"]
    for e_i, e in enumerate(reviews):
        sub = fr[fr["ev"] == e_i]
        L.append(f"| {e['A']} | " + ", ".join(f"{r.code}{'*' if r.is_add else ''} {r.net*1e4:+.0f}/{r.ex*1e4:+.0f}" for r in sub.itertuples()) + " |")
    L += ["", "## Current ranking for the next review (announcement expected late Oct 2026, effective 2026-11-02)", "",
          f"Data through {dates[-1].date()} (the real cut-off is end-Sep). Top-10 eligible non-members: " +
          ", ".join(f"{c} ({r.score:.3f}, overall #{int(r.rank_all)})" for c, r in nm_now.iterrows()) + ".",
          "Weakest current members: " + ", ".join(f"{c} (#{int(r.rank_all)})" for c, r in mem_weak.iterrows()) + ".", ""]
    open(OUT + ".auto", "w", encoding="utf-8").write("\n".join(L))

    summary = {"classification": agg, "arms": res, "placebo": placebo, "dsr": d, "bar": bar, "verdict": verdict, "halves": halves,
               "n_cum": n_cum}
    names = [{"code": c, "screens": ["lq45_predict"], "score": float(r.score), "rank": i + 1,
              "features": {"val12": float(r.val), "frq12": float(r.frq), "ffm": float(r.ffm), "rank_all": int(r.rank_all)}}
             for i, (c, r) in enumerate(nm_now.iterrows())]
    if os.environ.get("RECORD") == "1":
        sid = rs.record_study(conn, STUDY, date(2026, 9, 25), params={"trials": TRIALS, "n_before": N_BEFORE, "n_trials": N_TRIALS},
                              summary=summary, names=names, report_path="research/IDX_LQ45_PREDICT_2026-09-25.md",
                              note=f"menu 42: predict LQ45 adds; P1 excess {real*1e4:+.0f} bps t {s1['t_ev']:.2f}; {verdict}")
        print("study id", sid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
