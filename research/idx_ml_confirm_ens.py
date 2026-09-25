#!/usr/bin/env python3
"""IDX menu ML-8 - the ML sleeve as an ENSEMBLE of confirmation rules instead of one (operator, 2026-09-25: "okay kerjakan 1").

ML-6f/6g (studies #160-161) found the +5 %/10-day price confirmation on the cost-aware ML book (36.2 %/yr, Sharpe 1.38,
mDD -27 %) and that it is FRAGILE: of the 12 neighbours (+3/+5/+8/+10 % x 5/10/20 days) only 5 clear "Sharpe >= base + 0.15",
the median neighbour sits near 26 %/1.1/-33 %. The live sleeve runs the best neighbour. This menu asks whether running the
sleeve as several rules at once - each with an equal share of the sleeve's capital - buys robustness: the ensemble's return
is the mean of its rule-books' daily returns, so no single threshold decides the year.

PRE-REGISTERED (4 trials; cumulative 826 + 4 = 830). Base book = ML-6 e5|2|3|10 (LIQ, K 10, margin 2, EMA-3, from 2022-01), the
same `idx_ml_confirm.book(wait=(thr, window))` as #160-161. Rule-books: the 12 neighbours. Arms:
  ens3    mean of  +5/10, +8/10, +10/10          (the live rule and its two nearest thresholds, same window)
  ens4    ens3 + +8/5
  ens6    thresholds 5/8/10 x windows 5/10
  ens12   all twelve
Reported for every arm: CAGR, Sharpe, mDD, years positive, by year, the leave-one-rule-out RANGE of Sharpe and mDD (how much
one rule decides), and the single rules for scale. Placebo (20 within-day shuffles of the score, best ensemble by Sharpe).
READING RULE. An ensemble is RECOMMENDED for the live sleeve if ALL of: Sharpe >= the median single rule (the honest
expectation for the live rule), mDD not deeper than the median single rule's, worst year >= the live rule's worst year,
and its leave-one-out Sharpe range <= half the range of the 12 single rules (the robustness it is bought for). CANDIDATE
(money rule, ML-6 reading) reported separately: Sharpe >= 1.2, mDD >= -25 %, >= 4/5 years, placebo pct >= 95. The switch is the
operator's decision (the live sleeve's confirm rule is a book param).
READ-ONLY; one idx.study row. IDX_ML_CACHE (default tmp/ml_strategy_cache.pkl).
"""
from __future__ import annotations

import json
import os
import pickle
import re
import sys
from datetime import date

import numpy as np
import pandas as pd
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blackheart-ingest", "src"))
import idx_ml_confirm as F  # noqa: E402
import idx_ml_costaware as C  # noqa: E402
import idx_ml_strategy as M  # noqa: E402
from blackheart_ingest.idx import research_store as rs  # noqa: E402
from blackheart_ingest.idx.ml import common  # noqa: E402

N_BEFORE = 826
STUDY = "ml_confirm_ens"
RULES = [(0.03, 5), (0.03, 10), (0.03, 20), (0.05, 5), (0.05, 10), (0.05, 20), (0.08, 5), (0.08, 10), (0.08, 20), (0.10, 5), (0.10, 10), (0.10, 20)]
LIVE = (0.05, 10)
ARMS = {"ens3": [(0.05, 10), (0.08, 10), (0.10, 10)],
        "ens4": [(0.05, 10), (0.08, 10), (0.10, 10), (0.08, 5)],
        "ens6": [(0.05, 5), (0.05, 10), (0.08, 5), (0.08, 10), (0.10, 5), (0.10, 10)],
        "ens12": RULES}
K, MARGIN, SPAN = 10, 2.0, 3
BAR = {"sharpe": 1.2, "mdd": -0.25, "years_pos": 4, "placebo_pct": 95.0}


def dsn() -> str:
    if os.environ.get("INGEST_DB_DSN"):
        return os.environ["INGEST_DB_DSN"]
    env = dict(re.findall(r"^([A-Z_]+)=(.*)$", open(os.path.join(ROOT, "blackheart-ingest", "idx-local.env")).read(), re.M))
    return env["INGEST_DB_DSN"].strip().strip('"')


def name(rule: tuple[float, int]) -> str:
    return f"+{rule[0] * 100:.0f}/{rule[1]}"


def main() -> int:
    cache = os.environ.get("IDX_ML_CACHE", os.path.join(ROOT, "tmp", "ml_strategy_cache.pkl"))
    P = pickle.load(open(cache, "rb"))
    P = P[P["d"] >= "2021-06-01"].copy()
    dates = M.wide(P, "close").index
    codes = M.wide(P, "close").columns
    g = lambda c: M.wide(P, c).reindex(index=dates, columns=codes)  # noqa: E731
    A = g("ac").to_numpy(float)
    c_in, c_out = M.costs(g("close").to_numpy(float), g("offer").to_numpy(float), g("bid").to_numpy(float))
    liq = g("liq").fillna(False).astype(bool).to_numpy()
    S = g("s5").to_numpy(float)
    e5_raw = S - np.nanmedian(np.where(liq, S, np.nan), axis=1, keepdims=True)
    e5 = C.ema(e5_raw, SPAN)
    t0 = int(np.searchsorted(dates, np.datetime64(date(2022, 1, 1))))

    def run_rule(e: np.ndarray, rule: tuple[float, int]) -> np.ndarray:
        R, _ = F.book(A, liq, e, K, c_in, c_out, MARGIN, t_start=t0, wait=rule)
        return R

    single: dict[tuple[float, int], np.ndarray] = {}
    single_stats: dict[str, dict] = {}
    for rule in RULES:
        single[rule] = run_rule(e5, rule)
        st = M.stats(single[rule], dates, t0)
        single_stats[name(rule)] = st
        M.log(f"rule {name(rule):<7} CAGR {st['cagr'] * 100:6.1f} % Sharpe {st['sharpe']:5.2f} mDD {st['mdd'] * 100:6.1f} % years+ {st['years_pos']}/{st['n_years']} "
              + " ".join(f"{str(y)[2:]}:{v * 100:+.0f}" for y, v in st["by_year"].items()))
    sh = np.array([s["sharpe"] for s in single_stats.values()])
    md = np.array([s["mdd"] for s in single_stats.values()])
    single_range = float(sh.max() - sh.min())
    med_sharpe, med_mdd = float(np.median(sh)), float(np.median(md))
    live = single_stats[name(LIVE)]
    live_worst = min(live["by_year"].values())

    res: dict[str, dict] = {}
    for arm, rules in ARMS.items():
        R = np.mean([single[r] for r in rules], axis=0)
        st = M.stats(R, dates, t0)
        loo = [M.stats(np.mean([single[r] for r in rules if r != x], axis=0), dates, t0) for x in rules] if len(rules) > 2 else []
        loo_sh = [s["sharpe"] for s in loo]
        loo_md = [s["mdd"] for s in loo]
        res[arm] = {**st, "rules": [name(r) for r in rules], "loo_sharpe_range": float(max(loo_sh) - min(loo_sh)) if loo else float("nan"),
                    "loo_sharpe_min": float(min(loo_sh)) if loo else float("nan"), "loo_mdd_worst": float(min(loo_md)) if loo else float("nan"),
                    "worst_year": float(min(st["by_year"].values()))}
        M.log(f"{arm:<6} CAGR {st['cagr'] * 100:6.1f} % Sharpe {st['sharpe']:5.2f} mDD {st['mdd'] * 100:6.1f} % years+ {st['years_pos']}/{st['n_years']} "
              f"LOO Sharpe range {res[arm]['loo_sharpe_range']:.2f} (min {res[arm]['loo_sharpe_min']:.2f}) " + " ".join(f"{str(y)[2:]}:{v * 100:+.0f}" for y, v in st["by_year"].items()))
    best = max(ARMS, key=lambda a: res[a]["sharpe"])
    rng = np.random.default_rng(M.SEED)
    pl = []
    for i in range(M.N_PLACEBO):
        shf = e5_raw.copy()
        for t in range(t0, len(dates)):
            idx = np.flatnonzero(liq[t] & np.isfinite(shf[t]))
            if len(idx) > 1:
                shf[t, idx] = shf[t, rng.permutation(idx)]
        e_sh = C.ema(shf, SPAN)
        R = np.mean([run_rule(e_sh, r) for r in ARMS[best]], axis=0)
        pl.append(M.stats(R, dates, t0)["sharpe"])
        M.log(f"placebo {best} {i + 1}/{M.N_PLACEBO}: {pl[-1]:.2f}")
    res[best]["placebo"] = {"n": M.N_PLACEBO, "pct": float((np.array(pl) < res[best]["sharpe"]).mean() * 100), "mean": float(np.mean(pl)), "max": float(np.max(pl))}
    M.log(f"placebo {best}: real {res[best]['sharpe']:.2f} vs shuffled mean {np.mean(pl):.2f} max {np.max(pl):.2f} -> pct {res[best]['placebo']['pct']:.0f}")

    for arm, r in res.items():
        why = []
        if r["sharpe"] < med_sharpe:
            why.append(f"sharpe {r['sharpe']:.2f} < median single {med_sharpe:.2f}")
        if r["mdd"] < med_mdd:
            why.append(f"mdd {r['mdd'] * 100:.0f} % deeper than median single {med_mdd * 100:.0f} %")
        if r["worst_year"] < live_worst:
            why.append(f"worst year {r['worst_year'] * 100:+.0f} % < live rule {live_worst * 100:+.0f} %")
        if not (r["loo_sharpe_range"] <= single_range / 2):
            why.append(f"LOO Sharpe range {r['loo_sharpe_range']:.2f} > half the single-rule range {single_range / 2:.2f}")
        r["recommend"] = not why
        r["why_not"] = why
        fails = []
        if r["sharpe"] < BAR["sharpe"]:
            fails.append(f"sharpe {r['sharpe']:.2f} < 1.2")
        if r["mdd"] < BAR["mdd"]:
            fails.append(f"mdd {r['mdd'] * 100:.0f} % < -25 %")
        if r["years_pos"] < min(BAR["years_pos"], r["n_years"]):
            fails.append(f"{r['years_pos']}/{r['n_years']} years positive")
        if "placebo" in r and r["placebo"]["pct"] < BAR["placebo_pct"]:
            fails.append(f"placebo pct {r['placebo']['pct']:.0f}")
        r["candidate"] = not fails
        r["fails"] = fails

    n_trials = N_BEFORE + len(ARMS)
    yrs = list(live["by_year"])
    L = [f"# IDX menu ML-8 - the ML sleeve as an ensemble of confirmation rules - {date.today()} - {len(ARMS)} trials, cumulative N = {n_trials}", "",
         f"Base = ML-6 e5|2|3|10 on LIQ from 2022-01 with a price-confirmation entry (`idx_ml_confirm.book`); an ensemble splits the sleeve's capital "
         f"equally across its rule-books. Single rules: median Sharpe {med_sharpe:.2f}, median mDD {med_mdd * 100:.0f} %, Sharpe range {single_range:.2f}; "
         f"live rule {name(LIVE)}: Sharpe {live['sharpe']:.2f}, mDD {live['mdd'] * 100:.0f} %, worst year {live_worst * 100:+.0f} %.", "",
         "## Single rules (for scale)", "", "| rule | CAGR | Sharpe | mDD | years + | " + " | ".join(str(y) for y in yrs) + " |", "|---|---|---|---|---|" + "---|" * len(yrs)]
    for rn, st in single_stats.items():
        L.append(f"| {rn}{' (live)' if rn == name(LIVE) else ''} | {st['cagr'] * 100:+.1f} % | {st['sharpe']:.2f} | {st['mdd'] * 100:.0f} % | {st['years_pos']}/{st['n_years']} | "
                 + " | ".join(f"{st['by_year'][y] * 100:+.0f} %" for y in yrs) + " |")
    L += ["", "## Ensembles", "", "| arm | rules | CAGR | Sharpe | mDD | years + | worst year | LOO Sharpe range (min) | LOO worst mDD | " + " | ".join(str(y) for y in yrs) + " | recommend | money rule |",
          "|---|---|---|---|---|---|---|---|---|" + "---|" * len(yrs) + "---|---|"]
    for arm, r in res.items():
        pl_s = f" (placebo pct {r['placebo']['pct']:.0f})" if "placebo" in r else ""
        L.append(f"| {arm} | {', '.join(r['rules'])} | {r['cagr'] * 100:+.1f} % | {r['sharpe']:.2f} | {r['mdd'] * 100:.0f} % | {r['years_pos']}/{r['n_years']} | {r['worst_year'] * 100:+.0f} % | "
                 f"{r['loo_sharpe_range']:.2f} ({r['loo_sharpe_min']:.2f}) | {r['loo_mdd_worst'] * 100:.0f} % | " + " | ".join(f"{r['by_year'][y] * 100:+.0f} %" for y in yrs)
                 + f" | {'YES' if r['recommend'] else 'no: ' + '; '.join(r['why_not'])} | {'CANDIDATE' if r['candidate'] else 'no: ' + '; '.join(r['fails'])}{pl_s} |")
    rec = [a for a in ARMS if res[a]["recommend"]]
    L += ["", "## Verdict (menu ML-8, study stored)", "",
          f"Recommended for the live sleeve: {', '.join(rec) or 'none'}. Money-rule candidates: {', '.join(a for a in ARMS if res[a]['candidate']) or 'none'}. "
          f"Best by Sharpe: {best} ({res[best]['cagr'] * 100:+.1f} %/yr, {res[best]['sharpe']:.2f}, mDD {res[best]['mdd'] * 100:.0f} %)."]
    text = "\n".join(L)
    out = os.path.join(HERE, f"IDX_ML_CONFIRM_ENS_{date.today()}.md")
    open(out, "w", encoding="utf-8").write(text + "\n")
    json.dump({"single": single_stats, "arms": common.plain(res)}, open(out.replace(".md", ".json"), "w"), indent=1, default=str)
    print(text)
    with psycopg.connect(dsn()) as conn:
        sid = rs.record_study(conn, STUDY, date.today(), params={"trials": list(ARMS), "arms": {a: [name(r) for r in rs_] for a, rs_ in ARMS.items()},
                                                                 "n_trials_cumulative": n_trials, "k": K, "margin": MARGIN, "ema": SPAN, "bar": BAR},
                              summary={"single": single_stats, "arms": common.plain(res), "recommended": rec, "best": best,
                                       "median_single": {"sharpe": med_sharpe, "mdd": med_mdd, "sharpe_range": single_range}},
                              names=[], report_path=out, note="ML-8: confirmation-rule ensemble for the live ML sleeve")
        conn.commit()
    M.log(f"study #{sid} stored; report {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
