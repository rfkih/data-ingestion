#!/usr/bin/env python3
"""IDX menu 35 - combining what the desk already knows: the price-driven combined book, the value book, and the financial
statements (operator, 2026-09-25: "kombinasikan informasi yang kita punya cari edge sebaik mungkin se robust mungkin
berfikirlah seperti quant ... harus bisa mencari edge yang berarti dan lebih baik dari sebelumnya").

The quant's reasoning, written before the run. 857 trials say one thing: on IDX, a more accurate score rarely adds money;
how it is used does. Every robust stream the desk has is PRICE-driven except one - the value strict composite (annual,
fundamentals, the only book with real fills). Two combinations were never tested on the deployed engine:
  (1) the value book as a capital sleeve next to the combined book - a different horizon (a year vs ~25 days vs one day)
      and a different information set, so the diversification should be real, not a relabelled momentum;
  (2) the financial statements as a VETO on the price sleeves' new entries - a trend breakout or an ML signal on a
      company whose latest published report shows a loss is a different bet from the same signal on a profitable one.
      Point in time: the latest report whose publication date is before the entry day; a name with no parsed report is
      NOT vetoed (so the veto can only remove trades, never invent them; coverage is reported).

ENGINE: menu 34's (idx_alloc_frontier.engine = #168: one Rp 20 M cash pool, 20 slots, lots of 100, closing offer/bid,
Stockbit fees; gap-fade at the open) with the deployed sizing gap 10 / trend 5 / ML 5 % of NAV and the deployed 30 % cash
floor. ML sleeve = the single +5 %/10-day confirmation (#177's; the live ens4 switch is not in this engine). Window
2022-01 -> 2026-09-16. Value sleeve = the strict composite annual-May book NAV (idx_beyond.value_nav).

PRE-REGISTERED (6 trials; cumulative 857 + 6 = 863).
  BLEND80 / BLEND70 / BLEND60 / BLEND50   capital X % combined book, (100 - X) % value book, rebalanced to target at each
                                          month end, 0.30 % cost on the amount moved.
  QV_LOSS   the combined book with new entries (all three sleeves) vetoed when the latest published report shows a loss.
  QV_WORSE  vetoed when that report is a loss, OR its net margin fell >= 3 pp on the year, OR its operating cash flow
            turned negative (the T3 definition of study #179).
  Reference = the deployed combined book (10/5/5, cash30).
READING RULE. An arm is BETTER than the reference if ALL of:
  (a) full window: Sharpe >= reference + 0.15, CAGR >= 0.85 x reference, mDD no more than 2 pp deeper;
  (b) each half (2022-01 -> 2024-04, 2024-05 -> 2026-09): Sharpe >= the reference's in that half;
  (c) without 2025 (the gap-fade and trend boom year): Sharpe >= the reference's without 2025;
  (d) BLEND only - the weight chosen WALK-FORWARD (at each year start, the blend weight with the best Sharpe on the years
      before, from the four) must itself satisfy (a).
  The deflated Sharpe at N = 863 is reported for the winner; it is context, not a gate.
READ-ONLY; one idx.study row. INGEST_DB_DSN (or idx-local.env), IDX_ML_CACHE, IDX_EXIT_CACHE.
"""
from __future__ import annotations

import json
import os
import pickle
import sys
from datetime import date

import numpy as np
import pandas as pd
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blackheart-ingest", "src"))
os.environ.setdefault("IDX_ML_CACHE", os.path.join(ROOT, "tmp", "ml_strategy_cache.pkl"))
os.environ.setdefault("IDX_EXIT_CACHE", os.path.join(ROOT, "tmp", "exit_cache.pkl"))
import idx_alloc_frontier as AF  # noqa: E402
import idx_beyond as BY  # noqa: E402
import idx_combo_rupiah as CR  # noqa: E402
import idx_ml_strategy as M  # noqa: E402
from blackheart_ingest.idx import research_store as rs  # noqa: E402
from blackheart_ingest.idx.ml import common  # noqa: E402

N_BEFORE = 857
ARMS = ["BLEND80", "BLEND70", "BLEND60", "BLEND50", "QV_LOSS", "QV_WORSE"]
STUDY = "combo_plus"
DEPLOYED = {"gap": 0.10, "trend": 0.05, "ML": 0.05}
FLOOR = 0.30
BLENDS = {"BLEND80": 0.8, "BLEND70": 0.7, "BLEND60": 0.6, "BLEND50": 0.5}
SWITCH_COST = 0.003
HALF = pd.Timestamp("2024-05-01")
BAR = {"sharpe_up": 0.15, "cagr_keep": 0.85, "mdd_slack": 0.02}


def sharpe(nav: pd.Series) -> float:
    r = nav.pct_change().dropna()
    return float(r.mean() / r.std() * np.sqrt(252)) if len(r) > 10 and r.std() > 0 else float("nan")


def summary(nav: pd.Series) -> dict:
    st = CR.stats(nav)
    h1, h2 = nav[nav.index < HALF], nav[nav.index >= HALF]
    r = nav.pct_change().dropna()
    r_ex = r[r.index.year != 2025]
    return {"cagr": st["cagr"], "sharpe": st["sharpe"], "mdd": st["mdd"], "by_year": st["by_year"], "final": st["final"],
            "sharpe_h1": sharpe(h1), "sharpe_h2": sharpe(h2),
            "sharpe_ex2025": float(r_ex.mean() / r_ex.std() * np.sqrt(252)) if r_ex.std() > 0 else float("nan")}


def blend(a: pd.Series, b: pd.Series, w: float | pd.Series) -> pd.Series:
    """Two sub-books, capital w / 1-w, rebalanced at month ends at SWITCH_COST on the amount moved. ``w`` may vary by year
    (a Series indexed by year) for the walk-forward pick."""
    idx = a.index.intersection(b.index)
    ra, rb = a.reindex(idx).pct_change().fillna(0.0), b.reindex(idx).pct_change().fillna(0.0)
    wt = (lambda d: float(w.get(d.year, w.iloc[0]))) if isinstance(w, pd.Series) else (lambda d: float(w))
    va, vb = wt(idx[0]), 1 - wt(idx[0])
    out = []
    for i, d in enumerate(idx):
        va *= 1 + ra.iloc[i]
        vb *= 1 + rb.iloc[i]
        tot = va + vb
        month_end = i + 1 == len(idx) or idx[i + 1].month != d.month
        if month_end:
            nxt = idx[i + 1] if i + 1 < len(idx) else d
            target = wt(nxt) * tot
            moved = abs(va - target)
            tot -= moved * SWITCH_COST
            va, vb = wt(nxt) * tot, (1 - wt(nxt)) * tot
        out.append(va + vb)
    return pd.Series(out, index=idx) * (a.iloc[0] if len(a) else 1.0)


def fundamentals(dsn: str) -> pd.DataFrame:
    with psycopg.connect(dsn) as conn:
        f = pd.read_sql("""SELECT code, published_at, net_profit, net_profit_prior, revenue, revenue_prior, cfo, cfo_prior
                             FROM idx.fundamental WHERE months IN (3, 6, 9, 12) AND published_at IS NOT NULL""", conn)
    f["pub"] = pd.to_datetime(f["published_at"], utc=True).dt.tz_convert("Asia/Jakarta").dt.tz_localize(None).dt.normalize()
    for c in ("net_profit", "net_profit_prior", "revenue", "revenue_prior", "cfo", "cfo_prior"):
        f[c] = f[c].astype(float)
    rev = f.revenue.where(f.revenue.abs() > 0)
    revp = f.revenue_prior.where(f.revenue_prior.abs() > 0)
    f["loss"] = f.net_profit < 0
    f["worse"] = f["loss"] | ((f.net_profit / rev - f.net_profit_prior / revp) <= -0.03) | ((f.cfo < 0) & (f.cfo_prior >= 0))
    return f.sort_values("pub")[["code", "pub", "loss", "worse"]]


def veto_filter(trades: list[dict], dates, f: pd.DataFrame, col: str, tkey: str) -> tuple[list[dict], dict]:
    """Drop trades whose entry day's latest published report (published strictly before it) has ``col`` True."""
    if not trades:
        return trades, {"n": 0, "covered": 0, "vetoed": 0}
    q = pd.DataFrame({"i": range(len(trades)), "code": [x["code"] for x in trades],
                      "d": [pd.Timestamp(dates[x[tkey]]) - pd.Timedelta(days=1) for x in trades]}).sort_values("d")
    m = pd.merge_asof(q, f.rename(columns={"pub": "d"}), on="d", by="code", direction="backward")
    covered = m[col].notna()
    bad = set(m.loc[covered & m[col].astype("boolean").fillna(False).astype(bool), "i"])
    return [x for k, x in enumerate(trades) if k not in bad], {"n": len(trades), "covered": int(covered.sum()), "vetoed": len(bad)}


def main() -> int:
    d = AF.dsn()
    P = pickle.load(open(os.environ["IDX_ML_CACHE"], "rb"))
    P = P[(P["d"] >= "2021-06-01") & (P["d"] <= CR.END)].copy()
    dates = M.wide(P, "close").index
    codes = M.wide(P, "close").columns
    g = lambda c: M.wide(P, c).reindex(index=dates, columns=codes)  # noqa: E731
    A, raw = g("ac").to_numpy(float), g("close").to_numpy(float)
    offer, bid = np.nan_to_num(g("offer").to_numpy(float)), np.nan_to_num(g("bid").to_numpy(float))
    liq = g("liq").fillna(False).astype(bool).to_numpy()
    ml = CR.ml_trades(P, dates, codes, A, raw, offer, bid, liq)
    tr = CR.trend_trades(d, dates)
    gap = CR.gap_events(d, dates)
    M.log(f"events: ML {len(ml)}, trend {len(tr)}, gap {len(gap)}")

    ref_nav, _ = AF.engine(dates, codes, A, raw, offer, bid, ml, tr, gap, DEPLOYED, cash_floor=FLOOR)
    res = {"REF": summary(ref_nav)}
    navs = {"REF": ref_nav}
    M.log(f"REF combined (10/5/5, cash30): {res['REF']}")

    # ---- the value sleeve
    v = BY.value_nav(d)
    v.index = pd.to_datetime(v.index)
    v = v[(v.index >= ref_nav.index[0]) & (v.index <= ref_nav.index[-1])]
    v = v.reindex(ref_nav.index).ffill().dropna()
    res["VALUE"] = summary(v / v.iloc[0] * CR.CAPITAL)
    corr = float(ref_nav.pct_change().corr(v.pct_change()))
    corr_m = float(ref_nav.resample("ME").last().pct_change().corr(v.resample("ME").last().pct_change()))
    M.log(f"VALUE alone: {res['VALUE']}; daily corr with REF {corr:+.2f}, monthly {corr_m:+.2f}")
    base = ref_nav.reindex(v.index)
    for arm, w in BLENDS.items():
        navs[arm] = blend(base, v / v.iloc[0] * CR.CAPITAL, w)
        res[arm] = summary(navs[arm])
    # walk-forward pick of the blend weight: at each year start, the best Sharpe on the years before (first year: 0.8)
    years = sorted(set(base.index.year))
    pick = {}
    for y in years:
        past = {arm: sharpe(navs[arm][navs[arm].index.year < y]) for arm in BLENDS}
        past = {k: s for k, s in past.items() if np.isfinite(s)}
        pick[y] = BLENDS[max(past, key=past.get)] if past else 0.8
    navs["BLEND_WF"] = blend(base, v / v.iloc[0] * CR.CAPITAL, pd.Series(pick))
    res["BLEND_WF"] = summary(navs["BLEND_WF"])
    res["BLEND_WF"]["weights"] = pick

    # ---- the fundamental veto
    f = fundamentals(d)
    cover = {}
    for arm, col in (("QV_LOSS", "loss"), ("QV_WORSE", "worse")):
        ml_v, c1 = veto_filter(ml, dates, f, col, "t_in")
        tr_v, c2 = veto_filter(tr, dates, f, col, "t_in")
        gap_v, c3 = veto_filter(gap, dates, f, col, "t")
        cover[arm] = {"ML": c1, "trend": c2, "gap": c3}
        navs[arm], _ = AF.engine(dates, codes, A, raw, offer, bid, ml_v, tr_v, gap_v, DEPLOYED, cash_floor=FLOOR)
        res[arm] = summary(navs[arm])
        M.log(f"{arm}: coverage {cover[arm]} -> {res[arm]}")
    # the vetoed trades themselves: were they worse? (informative)
    vet = {}
    for arm, col in (("QV_LOSS", "loss"), ("QV_WORSE", "worse")):
        kept = {id(x) for x in veto_filter(tr + ml, dates, f, col, "t_in")[0]}
        rows = []
        for x in tr + ml:
            j = list(codes).index(x["code"])
            a0, a1 = A[x["t_in"], j], A[x["t_out"], j]
            if np.isfinite(a0) and np.isfinite(a1) and a0 > 0:
                rows.append({"vetoed": id(x) not in kept, "r": a1 / a0 - 1})
        df = pd.DataFrame(rows)
        vet[arm] = {k: {"n": int(len(s)), "mean": round(float(s["r"].mean()), 4), "median": round(float(s["r"].median()), 4),
                        "win": round(float((s["r"] > 0).mean()), 3)} for k, s in df.groupby(df["vetoed"].map({True: "vetoed", False: "kept"}))}

    # ---- verdict
    ref = res["REF"]

    def better(a: dict) -> dict:
        full = (a["sharpe"] >= ref["sharpe"] + BAR["sharpe_up"] and a["cagr"] >= BAR["cagr_keep"] * ref["cagr"]
                and a["mdd"] >= ref["mdd"] - BAR["mdd_slack"])
        halves = a["sharpe_h1"] >= ref["sharpe_h1"] and a["sharpe_h2"] >= ref["sharpe_h2"]
        ex25 = a["sharpe_ex2025"] >= ref["sharpe_ex2025"]
        return {"full": bool(full), "halves": bool(halves), "ex2025": bool(ex25)}
    verdict = {arm: better(res[arm]) for arm in ARMS}
    wf = better(res["BLEND_WF"])
    for arm in BLENDS:
        verdict[arm]["walk_forward"] = wf["full"]
    passed = [a for a, v in verdict.items() if all(v.values())]
    n_trials = N_BEFORE + len(ARMS)
    dsr = {}
    for a in passed or ["REF"]:
        r = navs[a].pct_change().dropna()
        try:
            from idx_trend import ES  # the desk's deflated-Sharpe helper
            dsr[a] = float(ES.deflated_sharpe(list(r.values), n_trials))
        except Exception:  # noqa: BLE001 - context only
            dsr[a] = None

    # ---- report
    def line(k: str, a: dict) -> str:
        return (f"| {k} | {a['cagr']:+.1%} | {a['sharpe']:.2f} | {a['mdd']:.0%} | {a['sharpe_h1']:.2f} | {a['sharpe_h2']:.2f} | {a['sharpe_ex2025']:.2f} | "
                + " | ".join(f"{a['by_year'].get(y, float('nan')):+.0%}" for y in years) + " |")
    L = [f"# IDX menu 35 - price book + value book + financial statements: combining what the desk knows - {date.today()} - "
         f"{len(ARMS)} trials, cumulative N = {n_trials}", "",
         f"Engine #168/#177 (Rp 20 M, 20 slots, lots, offer/bid, fees), deployed 10/5/5 + cash30, {ref_nav.index[0].date()} -> {ref_nav.index[-1].date()}. "
         f"Value book vs combined book: daily return correlation {corr:+.2f}, monthly {corr_m:+.2f}.", "",
         "| arm | CAGR | Sharpe | mDD | Sharpe H1 | Sharpe H2 | Sharpe ex-2025 | " + " | ".join(str(y) for y in years) + " |",
         "|---|---|---|---|---|---|---|" + "---|" * len(years)]
    for k in ["REF", "VALUE", *BLENDS, "BLEND_WF", "QV_LOSS", "QV_WORSE"]:
        L.append(line(k, res[k]))
    L += ["", f"Walk-forward blend weights (combined-book share by year): {pick}", "",
          "## Fundamental veto: coverage and what it removed", "",
          "| arm | sleeve | trades | with a report | vetoed |", "|---|---|---|---|---|"]
    for arm, cv in cover.items():
        for s_, c in cv.items():
            L.append(f"| {arm} | {s_} | {c['n']} | {c['covered']} | {c['vetoed']} |")
    L += ["", "Trend + ML trades, price return entry -> exit (informative):", "", "| arm | group | n | mean | median | win |", "|---|---|---|---|---|---|"]
    for arm, gv in vet.items():
        for grp, s_ in gv.items():
            L.append(f"| {arm} | {grp} | {s_['n']} | {s_['mean']:+.1%} | {s_['median']:+.1%} | {s_['win']:.0%} |")
    L += ["", "## Verdict (pre-registered)", ""]
    for arm, vv in verdict.items():
        L.append(f"- **{arm}**: " + ", ".join(f"{k} {'yes' if x else 'no'}" for k, x in vv.items()) + (" -> **BETTER**" if all(vv.values()) else ""))
    L += ["", f"Deflated Sharpe at N = {n_trials}: {dsr}"]
    text = "\n".join(L)
    out = os.path.join(HERE, f"IDX_COMBO_PLUS_{date.today()}.md")
    open(out, "w", encoding="utf-8").write(text + "\n")
    json.dump(common.plain({"res": res, "verdict": verdict, "cover": cover, "vetoed": vet, "corr": [corr, corr_m], "dsr": dsr}),
              open(out.replace(".md", ".json"), "w"), indent=1, default=str)
    print(text)
    with psycopg.connect(d) as conn:
        sid = rs.record_study(conn, STUDY, date.today(), params={"trials": ARMS, "n_trials_cumulative": n_trials, "deployed": DEPLOYED, "floor": FLOOR,
                                                                 "bar": BAR, "blends": BLENDS, "switch_cost": SWITCH_COST},
                              summary=common.plain({"res": res, "verdict": verdict, "passed": passed, "corr": [corr, corr_m]}), names=[],
                              report_path=out, note="menu 35: combined book x value book blends, and a financial-statement veto on new entries")
        conn.commit()
    M.log(f"study #{sid} stored; report {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
