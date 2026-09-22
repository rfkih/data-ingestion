#!/usr/bin/env python3
"""IDX menu 29b — the gap-down fade, tested properly (operator, 2026-09-22: "coba uji secara menyeluruh").

Menu 29 (study #76) found one thing worth a second look: names that open >= 5 % below the previous close, bought at that open and
sold at the close, made +182 bps a trade on IDX-sourced opens (n 516, median -7, placebo -145). It was a post-hoc neighbour of a
failed pre-registered arm (2 %), so it counts for nothing until it survives its own declared test. This is that test.

PRE-REGISTERED (declared before the run; nothing tuned afterwards). 7 trials (cumulative 528 + 7 = 535).
  Data       2020-01 -> 2026-09-21, IDX-sourced opens ONLY (Yahoo opens are contaminated: menu 29). Universe as menu 29: main board,
             v60 >= Rp 5 bn (PIT), close >= 50, not locked at the open. Fills: buy open + 1 tick, sell at the exit bid (- 1 tick);
             fees 0.10 / 0.20 %. Up to K = 10 names a day, the most liquid first, equal weight.
  Arms
    g5        gap <= -5 %, sell at the close                       (the finding)
    g7        gap <= -7 %, sell at the close                       neighbour
    g10       gap <= -10 %, sell at the close                      neighbour
    g5_no     gap <= -5 %, sell at the NEXT open                   does the reversal continue overnight?
    g5_c1     gap <= -5 %, sell at the close of t+1                two-day hold
    g5_idio   gap <= -5 % AND the market gap that morning > -1 %    idiosyncratic gap (market gap = median gap of the eligible names, known at the open)
    g5_big    gap <= -5 % AND v60 >= Rp 20 bn                      the liquid half
    random    K random eligible names on the same days as g5       reference (100 draws for the placebo)
  Reads      trades, hit, mean / median net (bps), daily t (equal-weight day series), years positive, subsamples 2020-24 and 2025-26,
             fills at +2 / -2 ticks, without the top 5 % of trades, placebo percentile (100 draws of random names on the same days,
             same counts), concentration (share of net P&L from the 10 most frequent names), sleeve economics (capital fraction =
             trades / K each day: total, Sharpe, max drawdown, CAGR).
  Bar        CANDIDATE: mean net >= +50 bps, daily t >= 3, placebo pct >= 99, net > 0 in BOTH subsamples, net > 0 at +2/-2 tick fills,
             net > 0 without the top 5 % of trades.  ROBUST: candidate AND both neighbours (g7, g10) >= +50 bps.
             Money rule (sleeve): Sharpe >= 1.0 and max drawdown not deeper than -25 %.
  Facts      the reversal path after a >= 5 % gap-down open (gross, equal weight): open -> close, -> next open, -> close t+1, -> close t+5.

READ-ONLY. INGEST_DB_DSN=... PYTHONIOENCODING=utf-8 blackheart-ingest/.venv/Scripts/python research/idx_gapfade.py [--no-store]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date

import numpy as np
import pandas as pd
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "blackheart-ingest", "src"))
import idx_daytrade as D  # noqa: E402

K = 10
SEED = 20260922
PLACEBO_DRAWS = 100
ARMS = ["g5", "g7", "g10", "g5_no", "g5_c1", "g5_idio", "g5_big"]
N_TRIALS_BEFORE = 528


def build(dsn: str) -> dict:
    with psycopg.connect(dsn) as conn:
        bars = D.load(conn)
    P = D.panels(bars)
    src = bars.pivot(index="trade_date", columns="code", values="open_src").sort_index()
    o, c, v60 = P["open"], P["close"], P["v60"]
    elig = D.eligible(P) & (src == "idx")
    pc = c.shift(1)
    gap = o / pc - 1
    mkt_gap = gap.where(elig).median(axis=1)                                       # known at the open
    tk_o, tk_c = D.tick(o.to_numpy()), D.tick(c.to_numpy())
    buy1 = (o + tk_o) * (1 + D.FEE_BUY)
    buy2 = (o + 2 * tk_o) * (1 + D.FEE_BUY)
    sell_close1 = (c - tk_c) * (1 - D.FEE_SELL)
    sell_close2 = (c - 2 * tk_c) * (1 - D.FEE_SELL)
    o_next = o.shift(-1)
    sell_next_open = (o_next - D.tick(o_next.to_numpy())) * (1 - D.FEE_SELL)
    c1 = c.shift(-1)
    sell_close_t1 = (c1 - D.tick(c1.to_numpy())) * (1 - D.FEE_SELL)
    R = {"close": sell_close1 / buy1 - 1, "close_2t": sell_close2 / buy2 - 1, "next_open": sell_next_open / buy1 - 1, "close_t1": sell_close_t1 / buy1 - 1}
    masks = {"g5": gap <= -0.05, "g7": gap <= -0.07, "g10": gap <= -0.10}
    masks["g5_no"], masks["g5_c1"] = masks["g5"], masks["g5"]
    idio = pd.DataFrame(np.repeat((mkt_gap > -0.01).to_numpy()[:, None], gap.shape[1], axis=1), index=gap.index, columns=gap.columns)
    masks["g5_idio"] = masks["g5"] & idio
    masks["g5_big"] = masks["g5"] & (v60.shift(1) >= 20e9)
    exits = {"g5": "close", "g7": "close", "g10": "close", "g5_no": "next_open", "g5_c1": "close_t1", "g5_idio": "close", "g5_big": "close"}
    path = {"open->close": (c / o - 1), "open->next open": (o_next / o - 1), "open->close t+1": (c1 / o - 1), "open->close t+5": (c.shift(-5) / o - 1)}
    return {"P": P, "elig": elig, "gap": gap, "mkt_gap": mkt_gap, "R": R, "masks": masks, "exits": exits, "v60": v60, "path": path,
            "n_idx_opens": int(elig.sum().sum())}


def pick_trades(B: dict, mask: pd.DataFrame, R: pd.DataFrame) -> pd.DataFrame:
    rows = []
    elig, v60 = B["elig"], B["v60"]
    for d in R.index:
        q = elig.loc[d] & mask.loc[d].fillna(False)
        if not q.any():
            continue
        pick = v60.loc[d].where(q).dropna().sort_values(ascending=False).index[:K]
        r = R.loc[d, pick].dropna()
        for code, x in r.items():
            rows.append((d, code, float(x)))
    return pd.DataFrame(rows, columns=["d", "code", "net"])


def stats(T: pd.DataFrame) -> dict:
    if len(T) < 30:
        return {"trades": len(T), "verdict": "too few"}
    s = T.groupby("d")["net"].mean()
    s.index = pd.to_datetime(s.index)
    t = float(s.mean() / (s.std(ddof=1) / np.sqrt(len(s)))) if s.std(ddof=1) > 0 else float("nan")
    yrs = s.groupby(s.index.year).sum()
    srt = T["net"].sort_values()
    yr = pd.to_datetime(T["d"]).dt.year
    early, late = T[yr <= 2024]["net"], T[yr >= 2025]["net"]
    conc = T.groupby("code")["net"].agg(["size", "sum"]).sort_values("size", ascending=False)
    top10_share = float(conc["sum"].iloc[:10].sum() / T["net"].sum()) if T["net"].sum() != 0 else float("nan")
    n_day = T.groupby("d").size()
    sleeve = (s * (n_day / K)).sort_index()
    eq = (1 + sleeve).cumprod()
    days_span = max(1, (sleeve.index[-1] - sleeve.index[0]).days)
    return {"trades": len(T), "days": len(s), "hit": float((T["net"] > 0).mean()), "mean_bps": float(T["net"].mean() * 1e4),
            "median_bps": float(T["net"].median() * 1e4), "t": t, "years_pos": int((yrs > 0).sum()), "years_n": len(yrs),
            "by_year": {int(y): round(float(T[yr == y]["net"].mean() * 1e4)) for y in sorted(yr.unique())},
            "early_bps": float(early.mean() * 1e4) if len(early) else float("nan"), "early_n": len(early),
            "late_bps": float(late.mean() * 1e4) if len(late) else float("nan"), "late_n": len(late),
            "wo_top5_bps": float(srt.iloc[:-max(1, len(srt) // 20)].mean() * 1e4), "top10_names_share": top10_share,
            "sleeve": {"total_pct": float((eq.iloc[-1] - 1) * 100), "cagr_pct": float(((eq.iloc[-1]) ** (365 / days_span) - 1) * 100),
                       "sharpe": float(sleeve.mean() / sleeve.std(ddof=1) * np.sqrt(252)) if sleeve.std(ddof=1) > 0 else float("nan"),
                       "mdd_pct": float((eq / eq.cummax() - 1).min() * 100), "avg_capital_pct": float((n_day / K).mean() * 100)}}


def placebo(B: dict, T: pd.DataFrame, R: pd.DataFrame, real_mean: float, rng: np.random.Generator) -> dict:
    counts = T.groupby("d").size()
    elig = B["elig"]
    means = []
    for _ in range(PLACEBO_DRAWS):
        vals = []
        for d, n in counts.items():
            cand = elig.loc[d]
            cand = cand[cand].index.to_numpy()
            pk = rng.choice(cand, size=min(n, len(cand)), replace=False)
            vals.extend(R.loc[d, pk].dropna().tolist())
        means.append(float(np.mean(vals)))
    means = np.array(means)
    return {"placebo_mean_bps": float(means.mean() * 1e4), "placebo_sd_bps": float(means.std() * 1e4), "pct": float((means < real_mean).mean() * 100)}


def run(dsn: str, out_path: str, store: bool, study_name: str) -> dict:
    B = build(dsn)
    rng = np.random.default_rng(SEED)
    res: dict = {"desc": {"idx_open_name_days": B["n_idx_opens"], "start": D.START.isoformat(), "end": D.END.isoformat()}, "arms": {}, "path": {}}
    g5 = B["masks"]["g5"]
    for k, v in B["path"].items():
        x = v.where(g5 & B["elig"]).stack()
        res["path"][k] = {"mean_pct": float(x.mean() * 100), "median_pct": float(x.median() * 100), "n": len(x), "p_up": float((x > 0).mean())}
    for a in ARMS:
        R = B["R"][B["exits"][a]]
        T = pick_trades(B, B["masks"][a], R)
        st = stats(T)
        if "mean_bps" in st:
            st.update(placebo(B, T, R, T["net"].mean(), rng))
            T2 = pick_trades(B, B["masks"][a], B["R"]["close_2t"]) if B["exits"][a] == "close" else T
            st["fills_2t_bps"] = float(T2["net"].mean() * 1e4) if len(T2) else float("nan")
        res["arms"][a] = st
    for a in ARMS:
        st = res["arms"][a]
        if "mean_bps" not in st:
            continue
        checks = {"mean>=50": st["mean_bps"] >= 50, "t>=3": st["t"] >= 3, "placebo>=99": st["pct"] >= 99,
                  "early>0": st["early_bps"] > 0, "late>0": st["late_bps"] > 0, "2tick>0": st["fills_2t_bps"] > 0, "wo_top5>0": st["wo_top5_bps"] > 0}
        st["checks"] = checks
        st["verdict"] = "CANDIDATE" if all(checks.values()) else "tested: " + ",".join(k for k, v in checks.items() if not v)
        st["money_rule"] = bool(st["sleeve"]["sharpe"] >= 1.0 and st["sleeve"]["mdd_pct"] >= -25)
    if res["arms"]["g5"].get("verdict") == "CANDIDATE" and all(res["arms"][n].get("mean_bps", -1) >= 50 for n in ("g7", "g10")):
        res["arms"]["g5"]["verdict"] = "ROBUST"
    res["verdict"] = {a: res["arms"][a].get("verdict") for a in ARMS}
    write_report(res, out_path)
    if store:
        from blackheart_ingest.idx import research_store as rs
        with psycopg.connect(dsn) as conn:
            sid = rs.record_study(conn, study_name, D.END, params={"trials": ARMS, "n_trials_cumulative": N_TRIALS_BEFORE + len(ARMS), "K": K, "placebo_draws": PLACEBO_DRAWS, "seed": SEED},
                                 summary=json.loads(json.dumps(res, default=str)), names=[], report_path=out_path,
                                 note="; ".join(f"{a}: {v}" for a, v in res["verdict"].items()))
            res["study_id"] = sid
    return res


def f(x, d=0):
    return "-" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:+.{d}f}" if d == 0 else f"{x:.{d}f}"


def write_report(res: dict, path: str) -> None:
    d = res["desc"]
    L = [f"# IDX menu 29b — the gap-down fade, tested properly — {d['start']} -> {d['end']}", "",
         f"IDX-sourced opens only: {d['idx_open_name_days']:,} eligible name-days. Pre-registered in `research/idx_gapfade.py`; 7 trials (cumulative 535).", "",
         "## The path after a >= 5 % gap-down open (gross, equal weight, every eligible event)", "",
         "| horizon | mean | median | P(up) | n |", "|---|---|---|---|---|"]
    for k, v in res["path"].items():
        L.append(f"| {k} | {v['mean_pct']:+.2f} % | {v['median_pct']:+.2f} % | {v['p_up']*100:.0f} % | {v['n']:,} |")
    L += ["", "## Arms", "",
          "| arm | trades | hit | mean | median | t | yrs + | 2020-24 | 2025-26 | fills +/-2t | w/o top 5 % | placebo mean | placebo pct | top-10 names' share | verdict |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for a in ARMS:
        s = res["arms"][a]
        if "mean_bps" not in s:
            L.append(f"| {a} | {s['trades']} | | | | | | | | | | | | | {s['verdict']} |")
            continue
        L.append(f"| {a} | {s['trades']} | {s['hit']*100:.0f} % | **{s['mean_bps']:+.0f}** | {s['median_bps']:+.0f} | {s['t']:.1f} | {s['years_pos']}/{s['years_n']} | "
                 f"{s['early_bps']:+.0f} (n {s['early_n']}) | {s['late_bps']:+.0f} (n {s['late_n']}) | {f(s['fills_2t_bps'])} | {s['wo_top5_bps']:+.0f} | "
                 f"{s['placebo_mean_bps']:+.0f} ± {s['placebo_sd_bps']:.0f} | {s['pct']:.0f} | {s['top10_names_share']*100:.0f} % | {s['verdict']} |")
    L += ["", "## Sleeve economics (capital fraction = trades / 10 each day; the rest idle)", "",
          "| arm | avg capital deployed | total | CAGR | Sharpe | max DD | money rule |", "|---|---|---|---|---|---|---|"]
    for a in ARMS:
        s = res["arms"][a]
        if "sleeve" not in s:
            continue
        sl = s["sleeve"]
        L.append(f"| {a} | {sl['avg_capital_pct']:.0f} % | {sl['total_pct']:+.0f} % | {sl['cagr_pct']:+.1f} % | {sl['sharpe']:.2f} | {sl['mdd_pct']:.0f} % | {'pass' if s['money_rule'] else 'fail'} |")
    L += ["", "## By year (mean net bps per trade)", ""]
    for a in ARMS:
        s = res["arms"][a]
        if "by_year" in s:
            L.append(f"- {a}: " + ", ".join(f"{y}: {v:+.0f}" for y, v in s["by_year"].items()))
    L += ["", "## Reading", "", "- Verdicts: " + "; ".join(f"{a} {v}" for a, v in res["verdict"].items()) + ".",
          "- CANDIDATE needs all seven checks; ROBUST needs the neighbours too; the money rule is read on the sleeve as it would be run.",
          "- IDX opens are dense only from 2025, so 2020-24 is the thin subsample; the test repeats itself as opens accumulate (~600 a day).", ""]
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(L))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-store", action="store_true")
    ap.add_argument("--out", default="")
    ap.add_argument("--study-name", default="gapfade")
    a = ap.parse_args()
    out = a.out or os.path.join(HERE, f"IDX_GAPFADE_{date.today().isoformat()}.md")
    res = run(os.environ["INGEST_DB_DSN"], out, not a.no_store, a.study_name)
    print(json.dumps({"verdict": res["verdict"], "arms": {a: {k: v.get(k) for k in ("trades", "mean_bps", "median_bps", "t", "pct", "early_bps", "late_bps", "wo_top5_bps", "fills_2t_bps")}
                                                          for a, v in res["arms"].items()}, "path": res["path"], "study_id": res.get("study_id"), "report": out}, indent=1, default=str))


if __name__ == "__main__":
    main()
