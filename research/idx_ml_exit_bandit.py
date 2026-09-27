#!/usr/bin/env python3
"""A learned exit policy for the ML sleeve - contextual bandit, walk-forward (operator 2026-09-27: "okay do 1").

The ML sleeve exits by a fixed rule: a same-close stop at -5 % from the fill (#281/#288), else the score swap or the 60-session
limit. Question: does choosing the exit PER TRADE from what is known at entry beat that fixed stop on trades the learner has not
seen? This is the reinforcement-learning question the desk can answer with its data: one decision per trade, a clear reward,
~1,000 trades. The full RL trader was not built (RL-1 #196/#197 lost to equal weight; too little data - see the chat of 09-27).

PRE-REGISTERED 2026-09-27 before any result of this script was seen (2 trials; cumulative 1025 + 2 = 1027):
  TRADES   the ML sleeve's entries as deployed (ens4: four confirmation rules, the #386 engine, 2022-01 -> 2026-09), each with its
           NATURAL exit from the same book run without a stop (score swap, 60-session limit, no score). Trade level: a slot freed
           by an early exit is not re-used (a limit, the same for every arm).
  ARMS     5 exits, each capped by the natural exit, each sold at the close that triggers it (bid side + fee, as the book):
           none | stop -5 % from the fill (DEPLOYED, the benchmark) | stop -10 % | trail 10 % from the highest close | trail 20 %
           net = A_exit / A_entry x (1 - c_out) / (1 + c_in) - 1. Every trade's outcome under every arm is known (full feedback).
  CONTEXT  known at the entry close: ML score (EMA excess), 20-day return, 20-day volatility, ATR %, distance to the 50-day
           average, COMPOSITE vs its 200-day average, log 20-day traded value, log price.
  POLICIES P1 contextual: one small LightGBM regressor per arm (7 leaves, 100 rounds, learning rate 0.05, min 50 rows per leaf; native API)
              predicting that arm's net from the context; choose the argmax.
           P2 non-contextual: the arm with the best mean net over the training trades.
  WALK-FORWARD refit on the first session of each month on every trade whose natural exit is before that day; score the trades
           ENTERED that month. Evaluation starts in the first month with >= 200 closed training trades.
  PASS (per policy, all of): mean net per trade > the deployed stop -5 % on the same out-of-sample trades with paired t >= 2.0;
           better in both halves of the out-of-sample period; its 1st-percentile trade no worse than the stop's.
  READ     a policy that passes goes to a PAPER test only (the live book is frozen to 2027-03-26). None passes -> learned exits are
           closed on this data.
READ-ONLY; one idx.study row (ml_exit_bandit).
Run: IDX_ML_CACHE=tmp/ml_strategy_cache.pkl python research/idx_ml_exit_bandit.py [--no-store]
"""
from __future__ import annotations

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
import idx_alloc_frontier as AF  # noqa: E402
import idx_combo_rupiah as CR  # noqa: E402
import idx_ml_costaware as C  # noqa: E402
import idx_ml_ens4_exits as X  # noqa: E402
import idx_ml_stop_sameclose as SC  # noqa: E402
import idx_ml_strategy as M  # noqa: E402
from blackheart_ingest.idx import research_store as rs  # noqa: E402
from blackheart_ingest.idx.ml import common  # noqa: E402

STUDY = "ml_exit_bandit"
N_BEFORE = 1025
ARMS = ["none", "stop5", "stop10", "trail10", "trail20"]
BENCH = "stop5"
FEATS = ["e5", "ret20", "vol20", "atr_pct", "dist_ma50", "comp_dma200", "lvalue20", "logpx"]
MIN_TRAIN = 200
LGB = {"objective": "regression", "num_leaves": 7, "learning_rate": 0.05, "min_data_in_leaf": 50, "verbose": -1, "seed": 20260927}
ROUNDS = 100


def arm_outcomes(A: np.ndarray, c_in: np.ndarray, c_out: np.ndarray, j: int, t_in: int, t_nat: int) -> dict[str, float]:
    """Pure. Net return of one trade under each exit arm (each capped by the natural exit, sold at the triggering close)."""
    path = A[t_in:t_nat + 1, j]
    entry = A[t_in, j]
    out = {}
    for arm in ARMS:
        ex = t_nat
        if arm != "none":
            peak = entry
            for k in range(1, len(path)):
                p = path[k]
                if np.isnan(p):
                    continue
                if arm.startswith("stop"):
                    hit = p <= (1 - int(arm[4:]) / 100) * entry
                else:
                    hit = p <= (1 - int(arm[5:]) / 100) * peak
                peak = max(peak, p)
                if hit:
                    ex = t_in + k
                    break
        a_ex = A[ex, j]
        if np.isnan(a_ex):
            a_ex = pd.Series(path).ffill().iloc[-1]
        co = c_out[ex, j] if np.isfinite(c_out[ex, j]) else c_out[t_nat, j]
        out[arm] = float(a_ex / entry * (1 - co) / (1 + c_in[t_in, j]) - 1)
    return out


def main() -> int:
    store = "--no-store" not in sys.argv
    P = pickle.load(open(os.environ["IDX_ML_CACHE"], "rb"))
    P = P[(P["d"] >= "2021-06-01") & (P["d"] <= CR.END)].copy()
    dates = M.wide(P, "close").index
    codes = M.wide(P, "close").columns
    g = lambda c: M.wide(P, c).reindex(index=dates, columns=codes)  # noqa: E731
    A, raw = g("ac").to_numpy(float), g("close").to_numpy(float)
    offer, bid = np.nan_to_num(g("offer").to_numpy(float)), np.nan_to_num(g("bid").to_numpy(float))
    liq = g("liq").fillna(False).astype(bool).to_numpy()
    c_in, c_out = M.costs(raw, offer, bid)
    S_ = g("s5").to_numpy(float)
    e5 = C.ema(S_ - np.nanmedian(np.where(liq, S_, np.nan), axis=1, keepdims=True), X.SPAN)
    ctx = {f: g(f).to_numpy(float) for f in ("ret20", "vol20", "atr_pct", "dist_ma50", "comp_dma200", "lvalue20")}
    t0 = int(np.searchsorted(dates, np.datetime64(CR.START)))
    rows = []
    for i, rule in enumerate(X.ENS4, start=1):
        _, log = SC.book_same(A, liq, e5, X.K, c_in, c_out, X.MARGIN, wait=rule, stop=1.0, t_start=t0)   # stop 1.0 = no stop
        for r in log.itertuples():
            j, ti, tn = int(r.j), int(r.t_in), int(r.t_out)
            o = arm_outcomes(A, c_in, c_out, j, ti, tn)
            feat = {"e5": e5[ti, j], "logpx": np.log(raw[ti, j]) if raw[ti, j] > 0 else np.nan, **{f: ctx[f][ti, j] for f in ctx}}
            rows.append({"leg": i, "code": codes[j], "t_in": ti, "t_nat": tn, "d_in": dates[ti], "d_nat": dates[tn], "why": r.why, **feat,
                         **{f"r_{a}": o[a] for a in ARMS}})
    T = pd.DataFrame(rows).sort_values("d_in").reset_index(drop=True)
    M.log(f"trades {len(T)}; arm means (all): " + ", ".join(f"{a} {T[f'r_{a}'].mean() * 100:+.2f} %" for a in ARMS))
    import lightgbm as lgb
    months = pd.period_range(T["d_in"].min(), T["d_in"].max(), freq="M")
    pick1, pick2 = pd.Series(index=T.index, dtype=object), pd.Series(index=T.index, dtype=object)
    for m in months:
        start = m.start_time
        train = T[T["d_nat"] < start]
        test = T[(T["d_in"] >= start) & (T["d_in"] <= m.end_time)]
        if len(train) < MIN_TRAIN or test.empty:
            continue
        pick2.loc[test.index] = max(ARMS, key=lambda a: train[f"r_{a}"].mean())
        preds = {}
        for a in ARMS:
            mdl = lgb.train(LGB, lgb.Dataset(train[FEATS].to_numpy(float), train[f"r_{a}"].to_numpy(float)), num_boost_round=ROUNDS)
            preds[a] = mdl.predict(test[FEATS].to_numpy(float))
        pick1.loc[test.index] = np.array(ARMS)[np.argmax(np.column_stack([preds[a] for a in ARMS]), axis=1)]
    OS = T[pick1.notna()].copy()
    OS["p1"] = [OS.loc[i, f"r_{pick1[i]}"] for i in OS.index]
    OS["p2"] = [OS.loc[i, f"r_{pick2[i]}"] for i in OS.index]
    OS["bench"] = OS[f"r_{BENCH}"]
    mid = OS["d_in"].iloc[len(OS) // 2]
    res: dict = {"trades_all": int(len(T)), "oos_trades": int(len(OS)), "oos_from": str(OS["d_in"].min().date()), "oos_to": str(OS["d_in"].max().date()),
                 "arm_means_oos": {a: float(OS[f"r_{a}"].mean()) for a in ARMS}, "policies": {}}
    for p, lab in (("p1", "P1 contextual (LightGBM per arm)"), ("p2", "P2 best arm so far")):
        d = OS[p] - OS["bench"]
        t = float(d.mean() / (d.std(ddof=1) / np.sqrt(len(d)))) if d.std(ddof=1) > 0 else 0.0
        h1, h2 = d[OS["d_in"] < mid].mean(), d[OS["d_in"] >= mid].mean()
        tail_ok = bool(np.percentile(OS[p], 1) >= np.percentile(OS["bench"], 1))
        passed = bool(d.mean() > 0 and t >= 2.0 and h1 > 0 and h2 > 0 and tail_ok)
        picks = (pick1 if p == "p1" else pick2)[OS.index].value_counts(normalize=True).to_dict()
        res["policies"][p] = {"label": lab, "mean": float(OS[p].mean()), "bench_mean": float(OS["bench"].mean()), "diff": float(d.mean()), "t": t,
                              "h1_diff": float(h1), "h2_diff": float(h2), "p01": float(np.percentile(OS[p], 1)), "bench_p01": float(np.percentile(OS["bench"], 1)),
                              "tail_ok": tail_ok, "passed": passed, "arm_share": {k: float(v) for k, v in picks.items()}}
    wins = [p for p, v in res["policies"].items() if v["passed"]]
    verdict = ("PASSES: " + ", ".join(res["policies"][p]["label"] for p in wins) + " -> paper test only") if wins else "CLOSED: no learned exit beats the fixed stop -5 % out of sample"
    n_trials = N_BEFORE + 2
    f = lambda v: f"{v * 100:+.2f} %"  # noqa: E731
    L = [f"# ML sleeve: a learned exit policy (contextual bandit, walk-forward) - {date.today()} - 2 trials, cumulative N = {n_trials}", "",
         f"{len(T)} ML rule-trades (ens4, #386 engine) with their natural exit; out of sample {res['oos_from']} -> {res['oos_to']}: {len(OS)} trades,",
         "each scored by a policy trained only on trades that had already closed (monthly refit). Benchmark = the deployed same-close stop -5 %.", "",
         "Out-of-sample mean net per trade by arm (every trade under every exit):", "",
         "| " + " | ".join(ARMS) + " |", "|" + "---|" * len(ARMS), "| " + " | ".join(f(res["arm_means_oos"][a]) for a in ARMS) + " |", "",
         "| policy | mean net | stop -5 % | difference | paired t | 1st half | 2nd half | 1st pct vs stop | arms chosen | pass |", "|---|---|---|---|---|---|---|---|---|---|"]
    for p, v in res["policies"].items():
        share = ", ".join(f"{k} {s * 100:.0f} %" for k, s in sorted(v["arm_share"].items(), key=lambda x: -x[1]))
        L.append(f"| {v['label']} | {f(v['mean'])} | {f(v['bench_mean'])} | {f(v['diff'])} | {v['t']:.2f} | {f(v['h1_diff'])} | {f(v['h2_diff'])} | "
                 f"{f(v['p01'])} vs {f(v['bench_p01'])} | {share} | {'yes' if v['passed'] else 'no'} |")
    L += ["", f"**Verdict: {verdict}**", "",
          "Limits: trade level (a slot freed early is not re-used, which understates every early exit a little and the same way for all",
          "arms); the natural exit comes from the no-stop book; same-close execution for every arm (the deployed stop runs 15:40-15:50);",
          "2022-26 only, the same regime caveats as every IDX study."]
    text = "\n".join(L)
    print(text)
    out = os.path.join(HERE, f"IDX_ML_EXIT_BANDIT_{date.today()}.md")
    if store:
        open(out, "w", encoding="utf-8").write(text + "\n")
        with psycopg.connect(AF.dsn()) as conn:
            sid = rs.record_study(conn, STUDY, date.today(), params={"trials": ["P1_contextual", "P2_best_arm"], "n_trials_cumulative": n_trials,
                                                                     "arms": ARMS, "bench": BENCH, "features": FEATS, "lgb": LGB, "min_train": MIN_TRAIN},
                                  summary=common.plain({**res, "verdict": verdict}), names=[], report_path=out, note=verdict)
            conn.commit()
        M.log(f"study #{sid} stored")
    return 0


if __name__ == "__main__":
    sys.exit(main())
