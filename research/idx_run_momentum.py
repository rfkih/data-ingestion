#!/usr/bin/env python3
"""IDX menu 32b PRELIM — "if it has already risen 8 ticks, predict it goes higher" (operator, 2026-09-23: "kalau misal naik 8 tik
kemungkinan naik lebih tinggi ya kamu bikin prediksi kalau ini bakal naik lebih tinggi").

Menu 32 read P(continue) = 0.60 on steps where the run's gain was >= 8 ticks — but those are steps INSIDE living runs, so the long
runs dominate the sample (a run that has lasted is a run that has kept going). The clean version of the operator's rule is an EVENT
study: the FIRST 10-s step at which a run's gain reaches K ticks is the prediction moment; everything after it is the outcome.

DESIGN (pre-registered before the first run; no model, no fitting → both sessions are evaluation days)
  Grid/run   as menu 32 (research/idx_run_exhaust.detect_runs): run = mid >= 3 ticks off the running low, ends at −2 ticks from its high.
  Event      first step in a run where (mid − run low) / tick >= K, K in {5, 8}. One event per run per K.
  Outcome    ticks_more = max mid over the rest of the run − mid at the event (in ticks); MORE1 = ticks_more >= 1 (the run went on);
             the run's remaining life (minutes); and two TRADES from the event (taker buy at the offer, fees 30 bps, sold at the bid):
               trail   sell when the run ends (−2 ticks from the high) or at the session's last step;
               t15     sell 15 min after the event (or at the run end if earlier).
  Condition  arm 'all' and arm 'mkt_up' = market breadth (share of feed names above their open) >= 0.5 at the event — the market-state
             feature that led menu 32's model.
  Trials     K {5, 8} x condition {all, mkt_up} x exit {trail, t15} = 8 (cumulative 670 → 678).
  Reads      per arm and per day: events, P(MORE1), mean / median ticks_more, mean net bps, t, P(win); placebo = the same number of
             events per name-day placed at random in-run steps (the run's gain at a random step is what the rule 'ignores'), 200 draws.
  Bar        CANDIDATE: >= 100 events pooled, mean net >= +20 bps, t >= 2.0, positive on BOTH days, placebo pct >= 95.
             PREDICTION read (no trade): P(MORE1) >= 0.60 with >= 100 events on both days = the operator's claim holds as a forecast.
             Two sessions: a direction read, not an adoption.

READ-ONLY. INGEST_DB_DSN=... PYTHONIOENCODING=utf-8 blackheart-ingest/.venv/Scripts/python research/idx_run_momentum.py
  [--days 2026-09-22,2026-09-23] [--no-store] [--out research/IDX_RUN_MOMENTUM_<day>.md]
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

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "blackheart-ingest", "src"))
_spec = importlib.util.spec_from_file_location("idx_run_exhaust", os.path.join(HERE, "idx_run_exhaust.py"))
rx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rx)
lob = rx.lob

KS = (5, 8)
FEE_BPS = 30.0
SEED = 20260923
N_PLACEBO = 200
N_TRIALS_BEFORE = 670
H15 = 90
BAR = {"events": 100, "net": 20.0, "t": 2.0, "placebo_pct": 95.0}


def events_for(days: dict[str, dict], day: date) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Events (first step at gain >= K) and the in-run step pool (for the placebo)."""
    ev, pool = [], []
    for code, d in days.items():
        mid, tick, sess, bid, off = d["mid"], d["tick"], d["session"], d["bid1"], d["off1"]
        breadth = d["F"]["MKT_BREADTH"].to_numpy(dtype=float)
        for r_i, (s, e, lo) in enumerate(rx.detect_runs(mid, tick, sess)):
            gain = (mid[s:e + 1] - mid[lo]) / tick[s:e + 1]
            hi_after = np.maximum.accumulate(mid[s:e + 1][::-1])[::-1]         # max of mid from t to the run end
            for t in range(s, e + 1):
                pool.append({"code": code, "day": day, "run": r_i, "i": t})
            for K in KS:
                hit = np.flatnonzero(gain >= K - 1e-9)
                if not len(hit):
                    continue
                t = s + int(hit[0])
                ev.append(outcome(code, day, r_i, K, t, e, mid, tick, bid, off, breadth, hi_after[int(hit[0])]))
    return pd.DataFrame(ev), pd.DataFrame(pool)


def outcome(code, day, r_i, K, t, e, mid, tick, bid, off, breadth, hi_rest) -> dict:
    tk = tick[t]
    j15 = min(t + H15, e)
    o = off[t]
    ok = np.isfinite(o) and o > 0
    return {"code": code, "day": day, "run": r_i, "K": K, "i": t, "end": e, "mkt_up": bool(breadth[t] >= 0.5),
            "ticks_more": (hi_rest - mid[t]) / tk, "MORE1": float((hi_rest - mid[t]) / tk >= 1 - 1e-9), "life_min": (e - t) / 6.0,
            "net_trail": (bid[e] / o - 1) * 1e4 - FEE_BPS if ok and np.isfinite(bid[e]) else np.nan,
            "net_t15": (bid[j15] / o - 1) * 1e4 - FEE_BPS if ok and np.isfinite(bid[j15]) else np.nan}


def summarise(E: pd.DataFrame, col: str) -> dict:
    a = E[col].dropna().to_numpy()
    by_day = {str(d): {"n": int(g[col].notna().sum()), "mean": float(g[col].mean())} for d, g in E.groupby("day")}
    return {"events": int(len(a)), "p_more1": float(E["MORE1"].mean()), "ticks_more_mean": float(E["ticks_more"].mean()),
            "ticks_more_median": float(E["ticks_more"].median()), "life_min": float(E["life_min"].median()),
            "mean": float(a.mean()) if len(a) else np.nan, "median": float(np.median(a)) if len(a) else np.nan,
            "p_win": float((a > 0).mean()) if len(a) else np.nan,
            "t": float(a.mean() / a.std(ddof=1) * np.sqrt(len(a))) if len(a) > 2 and a.std(ddof=1) > 0 else np.nan, "by_day": by_day}


def placebo(days_data: dict[date, dict[str, dict]], E: pd.DataFrame, pool: pd.DataFrame, col: str, rng: np.random.Generator) -> np.ndarray:
    """Same number of events per name-day, at random in-run steps; outcome measured the same way."""
    counts = E.groupby(["day", "code"]).size()
    pools = {k: g["i"].to_numpy() for k, g in pool.groupby(["day", "code"])}
    runs_end = {}
    means = []
    for _ in range(N_PLACEBO):
        vals = []
        for (day, code), n in counts.items():
            p = pools.get((day, code))
            if p is None or not len(p):
                continue
            d = days_data[day][code]
            mid, tick, sess, bid, off = d["mid"], d["tick"], d["session"], d["bid1"], d["off1"]
            key = (day, code)
            if key not in runs_end:
                ends = {}
                for r_i, (s, e, lo) in enumerate(rx.detect_runs(mid, tick, sess)):
                    for t in range(s, e + 1):
                        ends[t] = e
                runs_end[key] = ends
            ends = runs_end[key]
            for t in rng.choice(p, size=min(n, len(p)), replace=False):
                e = ends[int(t)]
                hi_rest = float(mid[t:e + 1].max())
                o = outcome(code, day, -1, 0, int(t), e, mid, tick, bid, off, d["F"]["MKT_BREADTH"].to_numpy(dtype=float), hi_rest)
                if np.isfinite(o[col]):
                    vals.append(o[col])
        means.append(float(np.mean(vals)) if vals else np.nan)
    return np.asarray(means)


def run(dsn: str, days: list[date], out_path: str, store: bool, study_name: str) -> dict:
    t0 = time.time()
    data: dict[date, dict[str, dict]] = {}
    with psycopg.connect(dsn) as conn:
        for d in days:
            data[d] = lob.build_day(conn, d)
    common = sorted(set.intersection(*(set(v) for v in data.values())))
    E_all, P_all = [], []
    for d in days:
        e, p = events_for({c: data[d][c] for c in common}, d)
        E_all.append(e)
        P_all.append(p)
    E, pool = pd.concat(E_all, ignore_index=True), pd.concat(P_all, ignore_index=True)
    rng = np.random.default_rng(SEED)
    res: dict = {"desc": {"days": [d.isoformat() for d in days], "names": len(common), "runs": int(pool.groupby(["day", "code", "run"]).ngroups),
                          "build_s": round(time.time() - t0)}, "arms": {}, "examples": []}
    for K in KS:
        for cond in ("all", "mkt_up"):
            sub = E[(E["K"] == K) & (E["mkt_up"] if cond == "mkt_up" else True)]
            for ex in ("trail", "t15"):
                col = f"net_{ex}"
                r = summarise(sub, col)
                pl = placebo(data, sub, pool, col, rng) if r["events"] >= 20 else np.asarray([])
                pl = pl[np.isfinite(pl)]
                r["placebo_mean"] = float(pl.mean()) if len(pl) else np.nan
                r["placebo_pct"] = float((pl < r["mean"]).mean() * 100) if len(pl) else np.nan
                both = all(v["n"] > 0 and v["mean"] > 0 for v in r["by_day"].values())
                r["CANDIDATE"] = bool(r["events"] >= BAR["events"] and r["mean"] >= BAR["net"] and np.isfinite(r["t"]) and r["t"] >= BAR["t"] and both
                                      and np.isfinite(r["placebo_pct"]) and r["placebo_pct"] >= BAR["placebo_pct"])
                per_day = sub.groupby("day").size()
                r["FORECAST_OK"] = bool(r["p_more1"] >= 0.60 and len(per_day) == len(days) and bool((per_day >= 100).all()))
                res["arms"][f"K{K}/{cond}/{ex}"] = r
    # a few concrete test-day examples of K=8 events: what happened next
    last = max(days)
    ex8 = E[(E["K"] == 8) & (E["day"] == last)].sort_values("i").head(12)
    res["examples"] = [{"code": r.code, "t": str(data[last][r.code]["t"][r.i])[11:16], "ticks_more": round(r.ticks_more, 1), "life_min": round(r.life_min, 1),
                        "net_trail": round(r.net_trail, 0) if np.isfinite(r.net_trail) else None} for r in ex8.itertuples()]
    res["verdict"] = {"candidates": [k for k, v in res["arms"].items() if v["CANDIDATE"]], "forecast_ok": [k for k, v in res["arms"].items() if v["FORECAST_OK"]],
                      "n_trials": len(res["arms"])}
    write_report(res, out_path)
    if store:
        from blackheart_ingest.idx import research_store as rs
        with psycopg.connect(dsn) as conn:
            sid = rs.record_study(conn, study_name, days[-1], params={"trials": list(res["arms"]), "n_trials_cumulative": N_TRIALS_BEFORE + len(res["arms"]),
                                                                      "K": KS, "fee_bps": FEE_BPS, "bar": BAR, "seed": SEED, "days": res["desc"]["days"]},
                                 summary=json.loads(json.dumps(res, default=str)), names=[], report_path=out_path,
                                 note=f"candidates {res['verdict']['candidates'] or 'none'}; forecast-ok {res['verdict']['forecast_ok'] or 'none'}")
            res["study_id"] = sid
    return res


def write_report(res: dict, path: str) -> None:
    d = res["desc"]
    f = lambda x, fmt: (fmt % x) if x is not None and np.isfinite(x) else "-"  # noqa: E731
    L = [f"# IDX menu 32b PRELIM — 'already up K ticks → it goes higher' as an event study — {', '.join(d['days'])}", "",
         f"{d['names']} names, {d['runs']:,} runs over {len(d['days'])} sessions. Event = the first 10-s step at which a run's gain reaches K ticks.",
         f"Pre-registered in `research/idx_run_momentum.py`; {res['verdict']['n_trials']} trials (cumulative {N_TRIALS_BEFORE + res['verdict']['n_trials']}). "
         "**Two sessions: a direction read, not an adoption.**", "",
         "| K | condition | exit | events | P(≥ +1 tick more) | ticks more (mean / median) | run life left (median min) | net bps (mean / median) | t | P(win) | by day | placebo mean | placebo pct | verdict |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for k, r in res["arms"].items():
        K, cond, ex = k.split("/")
        bd = " / ".join(f"{v['mean']:+.0f} (n {v['n']})" for v in r["by_day"].values())
        L.append(f"| {K[1:]} | {cond} | {ex} | {r['events']:,} | {r['p_more1']:.2f} | {r['ticks_more_mean']:+.2f} / {r['ticks_more_median']:+.2f} | {r['life_min']:.1f} | "
                 f"{f(r['mean'], '%+.1f')} / {f(r['median'], '%+.1f')} | {f(r['t'], '%.2f')} | {f(r['p_win'] * 100, '%.0f')} % | {bd} | {f(r['placebo_mean'], '%+.1f')} | "
                 f"{f(r['placebo_pct'], '%.0f')} | {'CANDIDATE' if r['CANDIDATE'] else 'no'}{' · forecast ok' if r['FORECAST_OK'] else ''} |")
    L += ["", f"## Examples — first twelve K=8 events on {d['days'][-1]}", "", "| name | time | ticks more | run life left (min) | net trail bps |", "|---|---|---|---|---|"]
    L += [f"| {e['code']} | {e['t']} | {e['ticks_more']:+.1f} | {e['life_min']} | {e['net_trail'] if e['net_trail'] is not None else '-'} |" for e in res["examples"]]
    L += ["", "## Reading", "",
          f"- Trade candidates by the bar (>= 100 events, >= +20 bps, t >= 2, both days positive, placebo >= 95): {', '.join(res['verdict']['candidates']) or 'none'}.",
          f"- Forecast read (P(≥ +1 tick more) >= 0.60 with >= 100 events on both days): {', '.join(res['verdict']['forecast_ok']) or 'none'}.",
          "- 'ticks more' is what a holder could still get from the event; the net columns are what a taker who BUYS at the event keeps after the",
          "  spread and the −2-tick giveback. The placebo places the same number of entries at random in-run steps of the same names.",
          "- Re-run at >= 20 sessions.", ""]
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(L))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", default="2026-09-22,2026-09-23")
    ap.add_argument("--no-store", action="store_true")
    ap.add_argument("--out", default="")
    ap.add_argument("--study-name", default="run_momentum")
    a = ap.parse_args()
    days = sorted(date.fromisoformat(x) for x in a.days.split(","))
    out = a.out or os.path.join(HERE, f"IDX_RUN_MOMENTUM_{days[-1].isoformat()}.md")
    res = run(os.environ["INGEST_DB_DSN"], days, out, not a.no_store, a.study_name)
    print(json.dumps({"desc": res["desc"], "arms": {k: {x: v[x] for x in ("events", "p_more1", "ticks_more_mean", "mean", "t", "placebo_pct", "CANDIDATE", "FORECAST_OK")} for k, v in res["arms"].items()},
                      "verdict": res["verdict"], "study_id": res.get("study_id"), "report": out}, indent=1, default=str))


if __name__ == "__main__":
    main()
