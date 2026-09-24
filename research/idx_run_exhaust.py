#!/usr/bin/env python3
"""IDX menu 32 PRELIM — "when does the buying power of an intraday run die?" (operator, 2026-09-23: "akumulasi terus menerus ...
sampai kapan harga akan naik ... suatu saham lagi naik beberapa tick, kapan power naiknya habis" → "okay boleh lakukan research nya").

Conditional question: GIVEN a name is in an upward run, predict whether the run continues or is exhausted, from the book and the tape.
Two sessions of the Stockbit feed: 09-22 train (market −2.8 %), 09-23 test (+1.7 %). A direction read, never an adoption.

DESIGN (pre-registered before the first run)
  Grid       10-s grid per name inside the continuous phases, built by research/idx_lob_ml.build_day (book carried forward inside a
             session, prints per bucket, 30 hand-made book/tape features incl. OFI, dOV1, TFI, dist_hi, market context).
  Run        per name-session: track the running low of the mid; a run STARTS when mid − low >= 3 ticks; it ENDS at the first step
             where mid <= run high − 2 ticks (the run's high is its exhaustion point); the low resets at the end. Steps inside a run
             (from the start step to the end step) are the sample. Run features added: age (steps), gain (ticks from the run low),
             gain relative to the market (gain − EW market move since the run start, bps), cumulative OFI and cumulative TFI since
             the run start, volume per tick gained, bid follow (log bv1 now / mean bv1 in the run), offer refill (dOV1), ticks to the
             day high, ticks to the next round price (multiple of 10 ticks), MKT_OFI5, MKT_RET.
  Label      at step t inside a run, scanning forward <= 90 steps (15 min): CONTINUE = the mid reaches >= mid_t + 1 tick BEFORE the
             mid falls to <= (running high) − 2 ticks; else EXHAUSTED (the fall came first, or nothing happened in 15 min).
             Also kept: ticks_more = max forward mid − mid_t before the run ends (what a holder could still get).
  Model      LightGBM binary P(continue), train day → test day, early stop on the last 20 % of the train day (by position in run order);
             placebo = labels shuffled within name, 10 draws → per-name AUC median percentile.
  Reads      per-name AUC (median) and per-name IC of P(continue) vs ticks_more (share > 0); base P(continue) by run age bucket
             (<= 3 min, 3-10, > 10) and by gain bucket (3-4, 5-7, >= 8 ticks); calibration deciles.
  Policies   on the test day, one evaluation per run:
             EXIT (we already hold; sell at the BID):
               base_trail   sell when the run ends (mid <= high − 2 ticks) — the naive trailing stop, the comparator (not a trial);
               base_5m      sell 5 min after the run start (not a trial);
               exit_p30 / exit_p50  sell at the first step where P(continue) < the train-day 30th / 50th percentile (2 trials);
               metric = (sell bid − mid at run start) / tick, and ticks left on the table vs the run's eventual high.
             ENTRY (taker buy at the OFFER inside the run when P(continue) >= the train-day 80th / 90th percentile; sell at the bid at
               the first P(continue) < p30, or at the run end, or after 15 min; fees 30 bps; one trade per run): entry_p80 / entry_p90
               (2 trials). Net bps.
  Trials     1 model + 4 policies = 5 (cumulative 665 → 670).
  Bar        MODEL LEAD: per-name AUC median >= 0.58, per-name IC > 0 for >= 70 % of names, placebo pct >= 95.
             EXIT CANDIDATE: >= 100 runs, mean ticks vs base_trail >= +0.5 tick, paired t >= 2.0.
             ENTRY CANDIDATE: >= 100 trades, mean net >= +20 bps, t >= 2.0. One test day → flagged; nothing adoptable.

READ-ONLY. INGEST_DB_DSN=... PYTHONIOENCODING=utf-8 blackheart-ingest/.venv/Scripts/python research/idx_run_exhaust.py
  [--train 2026-09-22 --test 2026-09-23] [--no-store] [--out research/IDX_RUN_EXHAUST_<test>.md]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
from datetime import date

import numpy as np
import pandas as pd
import psycopg
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "blackheart-ingest", "src"))
_spec = importlib.util.spec_from_file_location("idx_lob_ml", os.path.join(HERE, "idx_lob_ml.py"))
lob = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lob)
up = lob.up

START_T, END_T, MORE_T, H = 3, 2, 1, 90
FEE_BPS = 30.0
SEED = 20260923
N_PLACEBO = 10
N_TRIALS_BEFORE = 665
RUN_FEATS = ["age", "gain_t", "gain_rel_bps", "cumOFI", "cumTFI", "vol_per_tick", "bid_follow", "round_t", "hi_t"]
BOOK_FEATS = ["OBI1", "OBI5", "OBI10", "OBN1", "micro", "sprd_t", "sprd_bps", "conc_b", "conc_o", "OFI30", "OFI1", "OFI5", "dBV1", "dOV1",
              "TFI1", "TFI5", "RET1", "RET5", "rvol15", "MKT_OFI5", "MKT_RET", "MKT_BREADTH"]
FEATS = RUN_FEATS + BOOK_FEATS
BAR_MODEL = {"auc": 0.58, "ic_share": 0.70, "placebo_pct": 95.0}
BAR_EXIT = {"runs": 100, "ticks": 0.5, "t": 2.0}
BAR_ENTRY = {"trades": 100, "net": 20.0, "t": 2.0}


# ------------------------------------------------------------------------------------------------------------------ runs
def detect_runs(mid: np.ndarray, tick: np.ndarray, sess: np.ndarray) -> list[tuple[int, int, int]]:
    """(start, end, low_idx) per run; end = the step where mid <= high - END_T ticks (or the session's last step)."""
    runs = []
    for si in np.unique(sess):
        ix = np.flatnonzero(sess == si)
        low, low_i, in_run, start, high = mid[ix[0]], ix[0], False, -1, -np.inf
        for k in ix:
            m, t = mid[k], tick[k]
            if not in_run:
                if m < low:
                    low, low_i = m, k
                if m - low >= START_T * t - 1e-9:
                    in_run, start, high = True, k, m
            else:
                high = max(high, m)
                if m <= high - END_T * t + 1e-9:
                    runs.append((start, k, low_i))
                    in_run, low, low_i = False, m, k
        if in_run:
            runs.append((start, ix[-1], low_i))
    return runs


def label_step(mid: np.ndarray, tick: np.ndarray, t: int, high: float, stop: int) -> tuple[float, float]:
    """CONTINUE (1) if mid reaches mid_t + MORE_T ticks before mid <= running high - END_T ticks within H steps; ticks_more."""
    m0, tk = mid[t], tick[t]
    h = high
    best = 0.0
    lab = 0.0
    for j in range(t + 1, min(t + H, stop) + 1):
        m = mid[j]
        h = max(h, m)
        best = max(best, (m - m0) / tk)
        if m >= m0 + MORE_T * tk - 1e-9 and lab == 0.0:
            lab = 1.0
        if m <= h - END_T * tk + 1e-9:
            break
    return lab, best


def run_panel(days: dict[str, dict], day: date) -> pd.DataFrame:
    rows = []
    for code, d in days.items():
        mid, tick, sess, F = d["mid"], d["tick"], d["session"], d["F"]
        bid1, off1 = d["bid1"], d["off1"]
        Fn = {k: F[k].to_numpy(dtype=float) for k in F.columns}
        ofi = Fn["OFI30"] / 3.0                                                 # per-step OFI (OFI30 = 3-step sum)
        for r_i, (s, e, lo) in enumerate(detect_runs(mid, tick, sess)):
            stop = int(np.flatnonzero(sess == sess[s])[-1])
            mkt0 = Fn["MKT_RET"][s]
            bv1_run = []
            cum_ofi = 0.0
            cum_b, cum_s = 0.0, 0.0
            for t in range(s, e + 1):
                cum_ofi += ofi[t] if np.isfinite(ofi[t]) else 0.0
                bv1_run.append(np.log1p(d["raw"][t, 1]))
                lab, more = label_step(mid, tick, t, float(mid[s:t + 1].max()), stop)
                gain_t = (mid[t] - mid[lo]) / tick[t]
                px = mid[t]
                step = 10 * tick[t]
                rows.append({"code": code, "day": day, "run": r_i, "i": t, "start": s, "end": e, "session": sess[t],
                             "mid": mid[t], "bid1": bid1[t], "off1": off1[t], "tick": tick[t], "mid_start": mid[s], "high_run": float(mid[s:e + 1].max()),
                             "age": t - s, "gain_t": gain_t, "gain_rel_bps": (mid[t] / mid[s] - 1) * 1e4 - (Fn["MKT_RET"][t] - mkt0),
                             "cumOFI": cum_ofi, "cumTFI": float(np.nanmean(Fn["TFI1"][s:t + 1])), "vol_per_tick": float(Fn["rvol15"][t] / max(gain_t, 1)),
                             "bid_follow": bv1_run[-1] - float(np.mean(bv1_run)), "round_t": (np.ceil(px / step) * step - px) / tick[t],
                             "hi_t": Fn["dist_hi"][t], "LAB": lab, "ticks_more": more,
                             **{k: Fn[k][t] for k in BOOK_FEATS}})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------------------------------------------- model
def fit(tr: pd.DataFrame, te: pd.DataFrame, seed: int = SEED, rounds: int = 400, early: bool = True) -> tuple[np.ndarray, np.ndarray, dict]:
    import lightgbm as lgb
    params = {"objective": "binary", "learning_rate": 0.05, "num_leaves": 31, "min_data_in_leaf": 200, "bagging_fraction": 0.8,
              "bagging_freq": 1, "feature_fraction": 0.8, "lambda_l2": 5.0, "seed": seed, "verbose": -1, "num_threads": 16}
    X, y = tr[FEATS].to_numpy(dtype=float), tr["LAB"].to_numpy()
    if early:
        cut = int(len(tr) * 0.8)
        m = lgb.train(params, lgb.Dataset(X[:cut], y[:cut], feature_name=FEATS), rounds,
                      valid_sets=[lgb.Dataset(X[cut:], y[cut:], feature_name=FEATS)], callbacks=[lgb.early_stopping(30, verbose=False)])
        best = m.best_iteration
    else:
        m = lgb.train(params, lgb.Dataset(X, y, feature_name=FEATS), rounds)
        best = rounds
    gain = np.asarray(m.feature_importance(importance_type="gain"), dtype=float)
    return (np.asarray(m.predict(tr[FEATS].to_numpy(dtype=float), num_iteration=best)),
            np.asarray(m.predict(te[FEATS].to_numpy(dtype=float), num_iteration=best)),
            {"importance": dict(zip(FEATS, (gain / gain.sum()).round(3).tolist(), strict=True)), "rounds": int(best)})


def per_name(te: pd.DataFrame, p: np.ndarray) -> tuple[list[float], list[float]]:
    aucs, ics = [], []
    for c, g in te.assign(p=p).groupby("code"):
        if len(g) >= 100 and g["p"].std() > 0 and 0 < g["LAB"].mean() < 1:
            aucs.append(up.auc_score(g["LAB"].to_numpy(), g["p"].to_numpy()))
            ics.append(float(stats.spearmanr(g["p"], g["ticks_more"]).statistic))
    return aucs, ics


def bucket_rates(te: pd.DataFrame) -> dict:
    out = {}
    age = pd.cut(te["age"], [-1, 18, 60, 10_000], labels=["<=3min", "3-10min", ">10min"])
    out["by_age"] = te.groupby(age, observed=True)["LAB"].agg(["mean", "size"]).rename(columns={"mean": "p_continue", "size": "n"}).reset_index().to_dict("records")
    gain = pd.cut(te["gain_t"], [-1, 4.5, 7.5, 10_000], labels=["3-4t", "5-7t", ">=8t"])
    out["by_gain"] = te.groupby(gain, observed=True)["LAB"].agg(["mean", "size"]).rename(columns={"mean": "p_continue", "size": "n"}).reset_index().to_dict("records")
    return out


# -------------------------------------------------------------------------------------------------------------- policy
def exit_policies(te: pd.DataFrame, p: np.ndarray, thr: dict[str, float]) -> dict:
    te = te.assign(p=p)
    res = {k: [] for k in ("base_trail", "base_5m", *thr)}
    left = {k: [] for k in res}
    for (code, r), g in te.groupby(["code", "run"], sort=False):
        g = g.sort_values("i")
        bid, tk, m0, hi = g["bid1"].to_numpy(), float(g["tick"].iloc[0]), float(g["mid_start"].iloc[0]), float(g["high_run"].iloc[0])
        if not np.isfinite(bid[-1]):
            continue
        end_ticks = (bid[-1] - m0) / tk
        res["base_trail"].append(end_ticks)
        left["base_trail"].append((hi - bid[-1]) / tk)
        j = min(30, len(g) - 1)
        res["base_5m"].append((bid[j] - m0) / tk)
        left["base_5m"].append((hi - bid[j]) / tk)
        pv = g["p"].to_numpy()
        for k, q in thr.items():
            hit = np.flatnonzero(pv < q)
            j = int(hit[0]) if len(hit) else len(g) - 1
            res[k].append((bid[j] - m0) / tk)
            left[k].append((hi - bid[j]) / tk)
    out = {}
    base = np.asarray(res["base_trail"])
    for k, v in res.items():
        a = np.asarray(v)
        d = a - base
        out[k] = {"runs": int(len(a)), "ticks_mean": float(a.mean()), "ticks_median": float(np.median(a)), "left_mean": float(np.mean(left[k])),
                  "vs_trail": float(d.mean()), "t_paired": float(d.mean() / d.std(ddof=1) * np.sqrt(len(d))) if len(d) > 2 and d.std(ddof=1) > 0 else np.nan}
        out[k]["CANDIDATE"] = bool(k in thr and out[k]["runs"] >= BAR_EXIT["runs"] and out[k]["vs_trail"] >= BAR_EXIT["ticks"] and np.isfinite(out[k]["t_paired"]) and out[k]["t_paired"] >= BAR_EXIT["t"])
    return out


def entry_policies(te: pd.DataFrame, p: np.ndarray, thr_in: dict[str, float], thr_out: float) -> dict:
    te = te.assign(p=p)
    out = {}
    for k, q in thr_in.items():
        nets, ticks = [], []
        for (code, r), g in te.groupby(["code", "run"], sort=False):
            g = g.sort_values("i")
            pv, off, bid, i = g["p"].to_numpy(), g["off1"].to_numpy(), g["bid1"].to_numpy(), g["i"].to_numpy()
            hit = np.flatnonzero(pv >= q)
            if not len(hit):
                continue
            a = int(hit[0])
            if not np.isfinite(off[a]) or off[a] <= 0:
                continue
            later = np.flatnonzero((pv[a + 1:] < thr_out) | (i[a + 1:] - i[a] >= H))
            b = a + 1 + int(later[0]) if len(later) else len(g) - 1
            if not np.isfinite(bid[b]):
                continue
            nets.append((bid[b] / off[a] - 1) * 1e4 - FEE_BPS)
            ticks.append((bid[b] - off[a]) / float(g["tick"].iloc[0]))
        a = np.asarray(nets)
        out[k] = {"trades": int(len(a)), "mean": float(a.mean()) if len(a) else np.nan, "median": float(np.median(a)) if len(a) else np.nan,
                  "p_win": float((a > 0).mean()) if len(a) else np.nan, "ticks_mean": float(np.mean(ticks)) if ticks else np.nan,
                  "t": float(a.mean() / a.std(ddof=1) * np.sqrt(len(a))) if len(a) > 2 and a.std(ddof=1) > 0 else np.nan}
        out[k]["CANDIDATE"] = bool(out[k]["trades"] >= BAR_ENTRY["trades"] and np.isfinite(out[k]["mean"]) and out[k]["mean"] >= BAR_ENTRY["net"] and np.isfinite(out[k]["t"]) and out[k]["t"] >= BAR_ENTRY["t"])
    return out


# ---------------------------------------------------------------------------------------------------------------- run
def run(dsn: str, d_train: date, d_test: date, out_path: str, store: bool, study_name: str) -> dict:
    t0 = time.time()
    with psycopg.connect(dsn) as conn:
        TR = lob.build_day(conn, d_train)
        TE = lob.build_day(conn, d_test)
    common = sorted(set(TR) & set(TE))
    Ptr = run_panel({c: TR[c] for c in common}, d_train)
    Pte = run_panel({c: TE[c] for c in common}, d_test)
    log = [f"{len(common)} names; runs train {Ptr.groupby(['code', 'run']).ngroups:,} ({len(Ptr):,} steps) / test {Pte.groupby(['code', 'run']).ngroups:,} ({len(Pte):,} steps) in {time.time() - t0:.0f} s"]
    tr = Ptr.dropna(subset=FEATS).sort_values(["code", "run", "i"]).reset_index(drop=True)
    te = Pte.dropna(subset=FEATS).sort_values(["code", "run", "i"]).reset_index(drop=True)
    p_tr, p_te, info = fit(tr, te)
    aucs, ics = per_name(te, p_te)
    rng = np.random.default_rng(SEED)
    pl = []
    for k in range(N_PLACEBO):
        trs = tr.copy()
        for c in trs["code"].unique():
            ix = trs.index[trs["code"] == c]
            trs.loc[ix, "LAB"] = rng.permutation(trs.loc[ix, "LAB"].to_numpy())
        _, pp, _ = fit(trs, te, seed=SEED + k, rounds=150, early=False)
        a, _ = per_name(te, pp)
        pl.append(float(np.median(a)))
    dec = pd.qcut(pd.Series(p_te), 10, labels=False, duplicates="drop")
    cal = pd.DataFrame({"d": dec, "y": te["LAB"].to_numpy(), "more": te["ticks_more"].to_numpy()}).groupby("d").agg(p_continue=("y", "mean"), ticks_more=("more", "mean"), n=("y", "size")).reset_index()
    model = {"auc_pooled": up.auc_score(te["LAB"].to_numpy(), p_te), "auc_name_median": float(np.median(aucs)), "ic_name_median": float(np.median(ics)),
             "ic_share_pos": float((np.asarray(ics) > 0).mean()), "n_names": len(aucs), "base_continue": float(te["LAB"].mean()),
             "placebo_auc_name_median": float(np.mean(pl)), "placebo_pct": float((np.asarray(pl) < np.median(aucs)).mean() * 100),
             "calibration": cal.to_dict("records"), **info, **bucket_rates(te)}
    model["LEAD"] = bool(model["auc_name_median"] >= BAR_MODEL["auc"] and model["ic_share_pos"] >= BAR_MODEL["ic_share"] and model["placebo_pct"] >= BAR_MODEL["placebo_pct"])
    q = {k: float(np.quantile(p_tr, v)) for k, v in (("p30", 0.30), ("p50", 0.50), ("p80", 0.80), ("p90", 0.90))}
    exits = exit_policies(te, p_te, {"exit_p30": q["p30"], "exit_p50": q["p50"]})
    entries = entry_policies(te, p_te, {"entry_p80": q["p80"], "entry_p90": q["p90"]}, q["p30"])
    log.append(f"model: per-name AUC {model['auc_name_median']:.3f} (placebo {model['placebo_auc_name_median']:.3f}) IC share {model['ic_share_pos']:.2f} ({time.time() - t0:.0f} s)")
    res = {"desc": {"train": d_train.isoformat(), "test": d_test.isoformat(), "names": len(common), "runs_train": int(tr.groupby(["code", "run"]).ngroups),
                    "runs_test": int(te.groupby(["code", "run"]).ngroups), "steps_train": len(tr), "steps_test": len(te), "thresholds": q},
           "model": model, "exits": exits, "entries": entries, "log": log}
    res["verdict"] = {"lead": model["LEAD"], "candidates": [k for k, v in exits.items() if v.get("CANDIDATE")] + [k for k, v in entries.items() if v["CANDIDATE"]],
                      "n_trials": 1 + 4}
    write_report(res, out_path)
    if store:
        from blackheart_ingest.idx import research_store as rs
        with psycopg.connect(dsn) as conn:
            sid = rs.record_study(conn, study_name, d_test, params={"trials": ["model", "exit_p30", "exit_p50", "entry_p80", "entry_p90"],
                                                                    "n_trials_cumulative": N_TRIALS_BEFORE + 5, "run": {"start_t": START_T, "end_t": END_T, "more_t": MORE_T, "H": H},
                                                                    "feats": FEATS, "bars": {"model": BAR_MODEL, "exit": BAR_EXIT, "entry": BAR_ENTRY}, "seed": SEED},
                                 summary=json.loads(json.dumps(res, default=str)), names=[], report_path=out_path,
                                 note=f"model lead {model['LEAD']}; candidates {res['verdict']['candidates'] or 'none'}")
            res["study_id"] = sid
    return res


def write_report(res: dict, path: str) -> None:
    d, m = res["desc"], res["model"]
    f = lambda x, fmt: (fmt % x) if x is not None and np.isfinite(x) else "-"  # noqa: E731
    L = [f"# IDX menu 32 PRELIM — when does an intraday run's buying power die? — train {d['train']} -> test {d['test']}", "",
         f"{d['names']} names; runs (>= {START_T} ticks off the low, ended at −{END_T} ticks from the high): train {d['runs_train']:,} ({d['steps_train']:,} steps) / "
         f"test {d['runs_test']:,} ({d['steps_test']:,} steps). Label CONTINUE = +{MORE_T} tick more before the −{END_T}-tick fall, within 15 min.",
         f"Pre-registered in `research/idx_run_exhaust.py`; 5 trials (cumulative {N_TRIALS_BEFORE + 5}). **One train day, one test day: a direction read.**", "",
         "## Model — P(continue) from the book, the tape and the run's own shape", "",
         f"- per-name AUC median **{m['auc_name_median']:.3f}** (placebo {m['placebo_auc_name_median']:.3f}, pct {m['placebo_pct']:.0f}); pooled AUC {m['auc_pooled']:.3f}",
         f"- per-name IC of P(continue) vs ticks still to come: median {m['ic_name_median']:+.3f}, positive in {m['ic_share_pos'] * 100:.0f} % of {m['n_names']} names",
         f"- base P(continue) on the test day {m['base_continue']:.3f}; rounds {m['rounds']}; verdict **{'LEAD' if m['LEAD'] else 'no'}**",
         "- importance (gain share): " + ", ".join(f"{a} {b}" for a, b in sorted(m["importance"].items(), key=lambda kv: -kv[1])[:10]), "",
         "| run age | P(continue) | n |", "|---|---|---|"]
    L += [f"| {r['age']} | {r['p_continue']:.3f} | {int(r['n']):,} |" for r in m["by_age"]]
    L += ["", "| gain so far | P(continue) | n |", "|---|---|---|"]
    L += [f"| {r['gain_t']} | {r['p_continue']:.3f} | {int(r['n']):,} |" for r in m["by_gain"]]
    L += ["", "| score decile | P(continue) | ticks still to come | n |", "|---|---|---|---|"]
    L += [f"| {int(c['d']) + 1} | {c['p_continue']:.3f} | {c['ticks_more']:+.2f} | {int(c['n']):,} |" for c in m["calibration"]]
    L += ["", "## Exit timing — we hold from the run start; sell at the bid", "",
          "| policy | runs | ticks kept (mean) | median | ticks left vs the run high | vs base_trail | paired t | verdict |", "|---|---|---|---|---|---|---|---|"]
    for k, v in res["exits"].items():
        L.append(f"| {k} | {v['runs']:,} | {v['ticks_mean']:+.2f} | {v['ticks_median']:+.2f} | {v['left_mean']:.2f} | {v['vs_trail']:+.2f} | {f(v['t_paired'], '%.2f')} | "
                 f"{'CANDIDATE (1 test day)' if v.get('CANDIDATE') else ('comparator' if k.startswith('base') else 'no')} |")
    L += ["", "## Entry — taker buy at the offer when P(continue) is high; sell at the bid when it drops below p30, at the run end, or after 15 min; fees 30 bps", "",
          "| policy | trades | mean net bps | median | P(win) | ticks (bid out − offer in) | t | verdict |", "|---|---|---|---|---|---|---|---|"]
    for k, v in res["entries"].items():
        L.append(f"| {k} | {v['trades']:,} | {f(v['mean'], '%+.1f')} | {f(v['median'], '%+.1f')} | {f(v['p_win'] * 100 if v['trades'] else np.nan, '%.0f')} % | "
                 f"{f(v['ticks_mean'], '%+.2f')} | {f(v['t'], '%.2f')} | {'CANDIDATE (1 test day)' if v['CANDIDATE'] else 'no'} |")
    L += ["", "## Log", "", *[f"- {x}" for x in res["log"]], "", "## Reading", "",
          f"- Model lead by the bar (per-name AUC >= 0.58, IC > 0 in >= 70 % of names, placebo >= 95): {'yes' if res['verdict']['lead'] else 'no'}.",
          f"- Policy candidates: {', '.join(res['verdict']['candidates']) or 'none'}.",
          "- The exit table is the monetisable read: a holder sells anyway, so a better sell point is pure gain (no second spread).",
          "- Re-run when >= 20 sessions exist; then walk-forward by day and neutralise the day's market drift.", ""]
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(L))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", default="2026-09-22")
    ap.add_argument("--test", default="2026-09-23")
    ap.add_argument("--no-store", action="store_true")
    ap.add_argument("--out", default="")
    ap.add_argument("--study-name", default="run_exhaust")
    a = ap.parse_args()
    out = a.out or os.path.join(HERE, f"IDX_RUN_EXHAUST_{a.test}.md")
    res = run(os.environ["INGEST_DB_DSN"], date.fromisoformat(a.train), date.fromisoformat(a.test), out, not a.no_store, a.study_name)
    print(json.dumps({"desc": res["desc"], "model": {k: res["model"][k] for k in ("auc_name_median", "placebo_auc_name_median", "placebo_pct", "ic_name_median", "ic_share_pos", "base_continue", "LEAD")},
                      "exits": res["exits"], "entries": res["entries"], "verdict": res["verdict"], "log": res["log"], "study_id": res.get("study_id"), "report": out}, indent=1, default=str))


if __name__ == "__main__":
    main()
