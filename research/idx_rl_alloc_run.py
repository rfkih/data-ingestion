#!/usr/bin/env python3
"""IDX menu RL-1 - a reinforcement-learning capital allocator over the desk's four tested strategies (operator,
2026-09-25: "kalau untung dapet reward, kita kasih modal" -> "oke kalau bikin reinforcement learning gimana?").

Why this shape. ~1,150 trading days are far too few for an agent that picks stocks from 900 names - it would memorise the
past. So the agent does not pick stocks: it is a CAPITAL MANAGER. Its world is four return streams the desk already trusts
plus cash, each produced by the desk's own engine with costs (#168 / #177: lots, closing offer/bid, Stockbit fees):
  gap    the deployed gap-fade alone, 20 % of NAV per event (K <= 5 a day fills the book)
  trend  the deployed trend rule (small, gate, trail10) alone, 10 % per trade (K = 10)
  ML     the cost-aware 5d ML with the +5 %/10-day confirmation alone, 10 % per trade (K = 10)
  value  the strict composite annual-May book (idx_beyond.value_nav)
Every Friday close it chooses one of seven ALLOCATION TEMPLATES for the next week (weights gap/trend/ML/value/cash):
  EQ .25/.25/.25/.25/0   TREND .15/.55/.15/.15/0   ML .15/.15/.55/.15/0   GAP .55/.15/.15/.15/0   VALUE .15/.15/.15/.55/0
  DEF .125 each + .50 cash   OFF .05 each + .80 cash
STATE (all known at the Friday close): per stream the trailing 20- and 60-day return and 20-day volatility; the COMPOSITE's
distance to its 200-day mean and its 20-day change; the allocator's own drawdown; the last action. Standardised with the
TRAINING window's means only.
REWARD per week: log(1 + r_week) - LAMBDA x (increase of the allocator's drawdown that week) - 0.30 % x turnover.
AGENT: a softmax policy (MLP 17 -> 32 -> 7, torch), REINFORCE with a moving-average baseline and an entropy bonus, trained on
random 26-week episodes drawn from the training weeks; 5 seeds.
WALK-FORWARD: test years 2024, 2025, 2026 (to the engine's end); each is traded by a policy trained ONLY on weeks before
Jan 1 of that year; the three test years are stitched. In test the policy acts greedily (argmax).

PRE-REGISTERED (1 trial: the RL policy; cumulative 865 + 1 = 866). Baselines on the same stitched window (not trials):
  FIXED_EQ   EQ every week                 REGIME   EQ when the COMPOSITE >= its MA200 last Friday, else DEF
  WF_BEST    at each test-year start, the template with the best Sharpe on the years before (the non-RL learner)
  RANDOM     a uniformly random template each week (200 draws: the placebo distribution)
READING RULE: the RL allocator is BETTER if its seed-mean stitched Sharpe >= the best of {FIXED_EQ, REGIME, WF_BEST} + 0.15,
its CAGR >= 0.85 x that baseline's, its mDD no more than 2 pp deeper, at least 4 of 5 seeds individually beat that baseline's
Sharpe, and the seed-mean Sharpe sits at or above the 95th percentile of RANDOM. Anything less: the agent is not given capital.
RUN COPY 2026-09-26 (menu FE-3). Deviations from the file above, bookkeeping only - the design, grid, reward, seeds, baselines
and reading rule are untouched: (1) run on the CORRECTED engine (#192: trend replay fix is in idx_combo_rupiah.trend_trades;
IDX_BOARD_MODE=pit, IDX_EXIT_CACHE=tmp/exit_cache_pit.pkl); the gap stream goes through CR.gap_events -> idx_gapfade.build ->
idx_daytrade.load, which already keeps only IDX-sourced opens (elig & open_src == 'idx'), so no open filter was added here;
(2) N_BEFORE 865 -> 960 (the ledger moved on; RL-1 is trial 961 of FE-3's 961..967); (3) the four daily streams are also
dumped to tmp/rl_streams_2026-09-26.pkl so idx_fe_kelly.py uses the identical streams (same-run pairs); (4) the report is
written as IDX_RL_ALLOC_<date>.md as designed.
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
import torch

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

N_BEFORE = 960
STUDY = "rl_alloc"
STREAMS = ["gap", "trend", "ML", "value"]
TEMPLATES = {
    "EQ": [.25, .25, .25, .25, 0], "TREND": [.15, .55, .15, .15, 0], "ML": [.15, .15, .55, .15, 0], "GAP": [.55, .15, .15, .15, 0],
    "VALUE": [.15, .15, .15, .55, 0], "DEF": [.125, .125, .125, .125, .5], "OFF": [.05, .05, .05, .05, .8]}
NAMES = list(TEMPLATES)
W = np.array([TEMPLATES[k] for k in NAMES])
LAMBDA, COST = 2.0, 0.003
TEST_YEARS = [2024, 2025, 2026]
SEEDS = [1, 2, 3, 4, 5]
EPISODES, EP_LEN, LR, ENT = 3000, 26, 3e-3, 0.01
BAR = {"sharpe_up": 0.15, "cagr_keep": 0.85, "mdd_slack": 0.02, "seeds_needed": 4, "random_pct": 95}


def log(m: str) -> None:
    M.log(f"[rl1] {m}")


# ------------------------------------------------------------------------------------------------ the four streams
def streams(d: str) -> tuple[pd.DataFrame, pd.Series]:
    P = pickle.load(open(os.environ["IDX_ML_CACHE"], "rb"))
    P = P[(P["d"] >= "2021-06-01") & (P["d"] <= CR.END)].copy()
    dates = M.wide(P, "close").index
    codes = M.wide(P, "close").columns
    g = lambda c: M.wide(P, c).reindex(index=dates, columns=codes)  # noqa: E731
    A, raw = g("ac").to_numpy(float), g("close").to_numpy(float)
    offer, bid = np.nan_to_num(g("offer").to_numpy(float)), np.nan_to_num(g("bid").to_numpy(float))
    liq = g("liq").fillna(False).astype(bool).to_numpy()
    comp_d = g("comp_dma200").max(axis=1).ffill()
    ml = CR.ml_trades(P, dates, codes, A, raw, offer, bid, liq)
    tr = CR.trend_trades(d, dates)
    gap = CR.gap_events(d, dates)
    navs = {}
    for name, (m_, t_, g_, pct) in {"gap": ([], [], gap, {"gap": 0.20, "trend": 0, "ML": 0}),
                                    "trend": ([], tr, [], {"gap": 0, "trend": 0.10, "ML": 0}),
                                    "ML": (ml, [], [], {"gap": 0, "trend": 0, "ML": 0.10})}.items():
        nav, _ = AF.engine(dates, codes, A, raw, offer, bid, m_, t_, g_, pct)
        navs[name] = nav
    v = BY.value_nav(d)
    v.index = pd.to_datetime(v.index)
    idx = navs["gap"].index
    navs["value"] = v.reindex(idx).ffill()
    R = pd.DataFrame({k: navs[k].pct_change() for k in STREAMS}).iloc[1:].fillna(0.0)
    return R, comp_d.reindex(R.index).ffill()


# ------------------------------------------------------------------------------------------------ weekly world
def weekly(R: pd.DataFrame, comp_d: pd.Series) -> dict:
    """Weekly blocks: the streams' daily returns inside each week (Mon..Fri), the Friday state features."""
    wk = R.index.to_period("W-FRI")
    weeks = sorted(set(wk))
    feats, blocks, ends = [], [], []
    lr = np.log1p(R)
    for w in weeks:
        m = wk == w
        blocks.append(R[m].to_numpy(float))
        ends.append(R.index[m][-1])
    for e in ends:
        h = R[R.index <= e]
        f = []
        for s in STREAMS:
            f += [float(lr[s][lr.index <= e].tail(20).sum()), float(lr[s][lr.index <= e].tail(60).sum()), float(h[s].tail(20).std() * np.sqrt(250))]
        cd = comp_d[comp_d.index <= e]
        f += [float(cd.iloc[-1]) if len(cd) else 0.0, float(cd.iloc[-1] - cd.iloc[-21]) if len(cd) > 21 else 0.0]
        feats.append(f)
    return {"weeks": weeks, "ends": pd.DatetimeIndex(ends), "blocks": blocks, "X": np.nan_to_num(np.array(feats)),
            "comp_up": np.array([f[-2] >= 0 for f in feats])}


def run_policy(world: dict, i0: int, i1: int, choose, start_action: int = 0) -> tuple[np.ndarray, list[int]]:
    """Trade weeks i0..i1-1 with choose(i, dd, last_action) -> template index (decided at the close of week i-1).
    Returns the daily net return series and the actions."""
    out, acts = [], []
    eq, peak, last = 1.0, 1.0, start_action
    for i in range(i0, i1):
        a = choose(i, 1 - eq / peak, last)
        turnover = float(np.abs(W[a] - W[last]).sum()) / 2 if i > i0 else 0.0
        r = world["blocks"][i] @ W[a][:4]
        r = r.copy()
        if len(r):
            r[0] -= COST * turnover
        for x in r:
            eq *= 1 + x
            peak = max(peak, eq)
        out.extend(r.tolist())
        acts.append(a)
        last = a
    return np.array(out), acts


def state(world: dict, i: int, dd: float, last: int, mu: np.ndarray, sd: np.ndarray) -> np.ndarray:
    x = (world["X"][i - 1] - mu) / sd
    oh = np.zeros(len(NAMES))
    oh[last] = 1.0
    return np.concatenate([x, [dd * 5.0], oh]).astype(np.float32)


def train(world: dict, i_end: int, seed: int, mu: np.ndarray, sd: np.ndarray) -> torch.nn.Module:
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    n_in = world["X"].shape[1] + 1 + len(NAMES)
    net = torch.nn.Sequential(torch.nn.Linear(n_in, 32), torch.nn.Tanh(), torch.nn.Linear(32, len(NAMES)))
    opt = torch.optim.Adam(net.parameters(), lr=LR)
    base = 0.0
    lo = 13                                                            # first weeks lack 60-day features
    for ep in range(EPISODES):
        s0 = int(rng.integers(lo, max(lo + 1, i_end - EP_LEN)))
        s1 = min(i_end, s0 + EP_LEN)
        logps, ents = [], []
        eq, peak, last, ret = 1.0, 1.0, 0, 0.0
        for i in range(s0, s1):
            x = torch.from_numpy(state(world, i, 1 - eq / peak, last, mu, sd))
            logits = net(x)
            dist = torch.distributions.Categorical(logits=logits)
            a = int(dist.sample())
            logps.append(dist.log_prob(torch.tensor(a)))
            ents.append(dist.entropy())
            turnover = float(np.abs(W[a] - W[last]).sum()) / 2
            r = world["blocks"][i] @ W[a][:4]
            dd0 = 1 - eq / peak
            wk = 1.0
            for x_ in r:
                eq *= 1 + x_
                peak = max(peak, eq)
                wk *= 1 + x_
            dd1 = 1 - eq / peak
            ret += np.log(max(wk, 1e-6)) - LAMBDA * max(0.0, dd1 - dd0) - COST * turnover
            last = a
        base = 0.95 * base + 0.05 * ret if ep else ret
        loss = -(ret - base) * torch.stack(logps).sum() - ENT * torch.stack(ents).sum()
        opt.zero_grad()
        loss.backward()
        opt.step()
    return net


def stats(r: np.ndarray, idx: pd.DatetimeIndex) -> dict:
    s = pd.Series(r, index=idx)
    eq = (1 + s).cumprod()
    yrs = len(s) / 250
    return {"cagr": float(eq.iloc[-1] ** (1 / yrs) - 1), "sharpe": float(s.mean() / s.std() * np.sqrt(250)) if s.std() > 0 else 0.0,
            "mdd": float((eq / eq.cummax() - 1).min()), "years": {int(y): float((1 + x).prod() - 1) for y, x in s.groupby(s.index.year)}}


def main() -> int:
    d = AF.dsn()
    R, comp_d = streams(d)
    log("streams alone: " + ", ".join(f"{k} Sharpe {R[k].mean() / R[k].std() * np.sqrt(250):.2f}" for k in STREAMS)
        + f"; corr {json.dumps(R.corr().round(2).to_dict())}")
    pickle.dump({"R": R, "comp_d": comp_d}, open(os.path.join(ROOT, "tmp", f"rl_streams_{date.today()}.pkl"), "wb"))
    world = weekly(R, comp_d)
    ends = world["ends"]
    first = {y: int(np.searchsorted(ends, pd.Timestamp(f"{y}-01-01"))) for y in TEST_YEARS}
    last_i = len(world["weeks"])
    spans = [(first[y], first[TEST_YEARS[k + 1]] if k + 1 < len(TEST_YEARS) else last_i) for k, y in enumerate(TEST_YEARS)]
    day_idx = pd.DatetimeIndex([dd for i in range(spans[0][0], last_i) for dd in R.index[R.index.to_period("W-FRI") == world["weeks"][i]]])
    res, acts_log = {}, {}

    # baselines
    eqi, defi = NAMES.index("EQ"), NAMES.index("DEF")
    r_eq = np.concatenate([run_policy(world, a, b, lambda i, dd, l: eqi, eqi)[0] for a, b in spans])
    r_reg = np.concatenate([run_policy(world, a, b, lambda i, dd, l: eqi if world["comp_up"][i - 1] else defi, eqi)[0] for a, b in spans])
    parts, picks = [], {}
    for (a, b), y in zip(spans, TEST_YEARS, strict=True):
        best, best_s = eqi, -9.0
        for k in range(len(NAMES)):
            rr, _ = run_policy(world, 13, a, lambda i, dd, l, k=k: k, k)
            s_ = rr.mean() / rr.std() * np.sqrt(250) if rr.std() > 0 else -9.0
            if s_ > best_s:
                best, best_s = k, s_
        picks[y] = NAMES[best]
        parts.append(run_policy(world, a, b, lambda i, dd, l, k=best: k, best)[0])
    r_wf = np.concatenate(parts)
    res["FIXED_EQ"], res["REGIME"], res["WF_BEST"] = stats(r_eq, day_idx), stats(r_reg, day_idx), stats(r_wf, day_idx)
    res["WF_BEST"]["picks"] = picks
    rng = np.random.default_rng(7)
    rand_sh = []
    for _ in range(200):
        rr = np.concatenate([run_policy(world, a, b, lambda i, dd, l: int(rng.integers(len(NAMES))), eqi)[0] for a, b in spans])
        rand_sh.append(rr.mean() / rr.std() * np.sqrt(250))
    res["RANDOM"] = {"sharpe_median": float(np.median(rand_sh)), "sharpe_p95": float(np.percentile(rand_sh, 95))}
    for k in ("FIXED_EQ", "REGIME", "WF_BEST"):
        log(f"{k}: CAGR {res[k]['cagr']:+.1%} Sharpe {res[k]['sharpe']:.2f} mDD {res[k]['mdd']:.0%} {res[k]['years']}")
    log(f"RANDOM Sharpe median {res['RANDOM']['sharpe_median']:.2f}, p95 {res['RANDOM']['sharpe_p95']:.2f}")

    # the agent, walk-forward, 5 seeds
    per_seed = []
    for seed in SEEDS:
        parts, acts = [], []
        for (a, b), y in zip(spans, TEST_YEARS, strict=True):
            mu, sd = world["X"][13:a].mean(axis=0), world["X"][13:a].std(axis=0) + 1e-9
            net = train(world, a, seed * 100 + y, mu, sd)

            def greedy(i, dd, l, net=net, mu=mu, sd=sd):
                with torch.no_grad():
                    return int(torch.argmax(net(torch.from_numpy(state(world, i, dd, l, mu, sd)))))
            rr, ac = run_policy(world, a, b, greedy, eqi)
            parts.append(rr)
            acts += ac
        st = stats(np.concatenate(parts), day_idx)
        st["actions"] = {NAMES[k]: int(sum(1 for x in acts if x == k)) for k in range(len(NAMES))}
        per_seed.append(st)
        log(f"RL seed {seed}: CAGR {st['cagr']:+.1%} Sharpe {st['sharpe']:.2f} mDD {st['mdd']:.0%} actions {st['actions']}")
    res["RL_seeds"] = per_seed
    rl = {"cagr": float(np.mean([s["cagr"] for s in per_seed])), "sharpe": float(np.mean([s["sharpe"] for s in per_seed])),
          "mdd": float(np.mean([s["mdd"] for s in per_seed])), "sharpe_min": float(min(s["sharpe"] for s in per_seed)),
          "sharpe_max": float(max(s["sharpe"] for s in per_seed))}
    res["RL"] = rl

    # verdict
    best_k = max(("FIXED_EQ", "REGIME", "WF_BEST"), key=lambda k: res[k]["sharpe"])
    bb = res[best_k]
    chk = {"sharpe": rl["sharpe"] >= bb["sharpe"] + BAR["sharpe_up"], "cagr": rl["cagr"] >= BAR["cagr_keep"] * bb["cagr"],
           "mdd": rl["mdd"] >= bb["mdd"] - BAR["mdd_slack"],
           "seeds": sum(1 for s in per_seed if s["sharpe"] > bb["sharpe"]) >= BAR["seeds_needed"],
           "random": rl["sharpe"] >= res["RANDOM"]["sharpe_p95"]}
    better = all(chk.values())
    n_trials = N_BEFORE + 1
    years = TEST_YEARS
    L = [f"# IDX menu RL-1 - a reinforcement-learning capital allocator over the four tested strategies - {date.today()} - 1 trial, cumulative N = {n_trials}", "",
         f"Streams (engine #168, costs): gap / trend / ML alone + value book; weekly allocation among 7 templates; reward = log return - {LAMBDA} x drawdown increase "
         f"- {COST:.1%} x turnover; REINFORCE MLP, {EPISODES} episodes of {EP_LEN} weeks, {len(SEEDS)} seeds; walk-forward test {years[0]}-{years[-1]} stitched "
         f"({day_idx[0].date()} -> {day_idx[-1].date()}).", "",
         "Daily return correlation of the streams: " + json.dumps(R.corr().round(2).to_dict()), "",
         "| allocator | CAGR | Sharpe | mDD | " + " | ".join(str(y) for y in years) + " |", "|---|---|---|---|" + "---|" * len(years)]
    for k in ("FIXED_EQ", "REGIME", "WF_BEST"):
        L.append(f"| {k} | {res[k]['cagr']:+.1%} | {res[k]['sharpe']:.2f} | {res[k]['mdd']:.0%} | " + " | ".join(f"{res[k]['years'].get(y, 0):+.0%}" for y in years) + " |")
    for s_, st in zip(SEEDS, per_seed, strict=True):
        L.append(f"| RL seed {s_} | {st['cagr']:+.1%} | {st['sharpe']:.2f} | {st['mdd']:.0%} | " + " | ".join(f"{st['years'].get(y, 0):+.0%}" for y in years) + " |")
    L += [f"| **RL mean** | {rl['cagr']:+.1%} | {rl['sharpe']:.2f} (range {rl['sharpe_min']:.2f}..{rl['sharpe_max']:.2f}) | {rl['mdd']:.0%} | |", "",
          f"RANDOM placebo (200 draws): Sharpe median {res['RANDOM']['sharpe_median']:.2f}, 95th pct {res['RANDOM']['sharpe_p95']:.2f}. "
          f"WF_BEST picks: {picks}.", "", "Actions taken in test (weeks, per seed): " + "; ".join(json.dumps(s["actions"]) for s in per_seed), "",
          "## Verdict (pre-registered)", "", f"Best baseline: {best_k}. Checks: " + ", ".join(f"{k} {'yes' if v else 'no'}" for k, v in chk.items())
          + f" -> **{'BETTER - candidate for a paper book' if better else 'NOT better - the agent is not given capital'}**"]
    text = "\n".join(L)
    out = os.path.join(HERE, f"IDX_RL_ALLOC_{date.today()}.md")
    open(out, "w", encoding="utf-8").write(text + "\n")
    json.dump(common.plain({"res": res, "verdict": chk, "better": better, "best_baseline": best_k}), open(out.replace(".md", ".json"), "w"), indent=1, default=str)
    print(text)
    with psycopg.connect(d) as conn:
        sid = rs.record_study(conn, STUDY, date.today(), params={"trials": ["RL"], "n_trials_cumulative": n_trials, "templates": TEMPLATES, "lambda": LAMBDA,
                                                                 "cost": COST, "episodes": EPISODES, "ep_len": EP_LEN, "seeds": SEEDS, "bar": BAR},
                              summary=common.plain({"RL": rl, "baselines": {k: res[k] for k in ("FIXED_EQ", "REGIME", "WF_BEST", "RANDOM")},
                                                    "verdict": chk, "better": better}),
                              names=[], report_path=out, note="menu RL-1 (run under FE-3, corrected engine #192): REINFORCE allocator over gap/trend/ML/value + cash, walk-forward")
        conn.commit()
    log(f"study #{sid} stored; report {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
