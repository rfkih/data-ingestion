#!/usr/bin/env python3
"""IDX menu ML-6g - robustness of the up-confirmation entry (follow-up to ML-6f, study #160, 2026-09-25).

ML-6f: entering a signalled name only after its close is >= 105 % of the signal close within 10 days (wait_up5) gave
+36 %/yr, Sharpe 1.38, mDD -27 % vs the base 29 % / 0.91 / -51 %. The up-direction was added as a control after the trade
anatomy (winners rarely dip), i.e. informed by the same data, so it must survive its neighbours and a placebo before it is
read as real.

PRE-REGISTERED (12 trials; cumulative 780 + 12 = 792): thresholds +3 %, +5 %, +8 %, +10 % x windows 5, 10, 20 days.
  ROBUST if: the 3x3 neighbourhood around (5 %, 10 d) (thresholds 3-8 %, windows 5-20 d) has Sharpe >= base + 0.15 in >= 7 of 9;
  placebo (scores shuffled within day, 20 runs, the wait_up5 rule kept) percentile >= 95; wait_up5 positive in >= 4/5 years.
  Also reported: the same rule on the deployed trend universe `small` is NOT tested here (different simulator) - noted for ML-7.
"""
from __future__ import annotations

import os
import pickle
import sys
from datetime import date

import numpy as np
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "blackheart-ingest", "src"))
import idx_ml_confirm as F  # noqa: E402
import idx_ml_costaware as C  # noqa: E402
import idx_ml_strategy as M  # noqa: E402
from blackheart_ingest.idx import research_store as rs  # noqa: E402
from blackheart_ingest.idx.ml import common  # noqa: E402

N_BEFORE = 780
STUDY = "ml_confirm_robust"
THRESH = [0.03, 0.05, 0.08, 0.10]
WINDOWS = [5, 10, 20]


def main() -> int:
    dsn = os.environ["INGEST_DB_DSN"]
    P = pickle.load(open(os.environ["IDX_ML_CACHE"], "rb"))
    P = P[P["d"] >= "2021-06-01"].copy()
    dates = M.wide(P, "close").index
    codes = M.wide(P, "close").columns
    g = lambda c: M.wide(P, c).reindex(index=dates, columns=codes)  # noqa: E731
    A = g("ac").to_numpy(float)
    c_in, c_out = M.costs(g("close").to_numpy(float), g("offer").to_numpy(float), g("bid").to_numpy(float))
    liq = g("liq").fillna(False).astype(bool).to_numpy()
    S = g("s5").to_numpy(float)
    e5 = C.ema(S - np.nanmedian(np.where(liq, S, np.nan), axis=1, keepdims=True), 3)
    t0 = int(np.searchsorted(dates, np.datetime64(date(2022, 1, 1))))
    R0, _ = F.book(A, liq, e5, 10, c_in, c_out, 2.0, t_start=t0)
    base = M.stats(R0, dates, t0)
    bar = base["sharpe"] + 0.15
    grid: dict[str, dict] = {}
    for th in THRESH:
        for wd in WINDOWS:
            R, log = F.book(A, liq, e5, 10, c_in, c_out, 2.0, t_start=t0, wait=(th, wd))
            st = M.stats(R, dates, t0)
            grid[f"up{int(th * 100)}_w{wd}"] = {**st, "trades": len(log), "win": float((log["net"] > 0).mean()), "avg": float(log["net"].mean()), "th": th, "wd": wd}
            M.log(f"up {th * 100:.0f} % w {wd:>2}: CAGR {st['cagr'] * 100:6.1f} % Sharpe {st['sharpe']:5.2f} mDD {st['mdd'] * 100:6.1f} % trades {len(log)} win {grid[f'up{int(th * 100)}_w{wd}']['win'] * 100:.0f} % "
                  + " ".join(f"{str(y)[2:]}:{v * 100:+.0f}" for y, v in st["by_year"].items()))
    neigh = [grid[f"up{t}_w{w}"] for t in (3, 5, 8) for w in (5, 10, 20)]
    n_pass = sum(r["sharpe"] >= bar for r in neigh)
    rng = np.random.default_rng(M.SEED)
    pl = []
    for _ in range(M.N_PLACEBO):
        sh = S.copy()
        for t in range(t0, len(dates)):
            idx = np.flatnonzero(liq[t] & np.isfinite(sh[t]))
            if len(idx) > 1:
                sh[t, idx] = sh[t, rng.permutation(idx)]
        e_sh = C.ema(sh - np.nanmedian(np.where(liq, sh, np.nan), axis=1, keepdims=True), 3)
        R, _ = F.book(A, liq, e_sh, 10, c_in, c_out, 2.0, t_start=t0, wait=(0.05, 10))
        pl.append(M.stats(R, dates, t0)["sharpe"])
    main_arm = grid["up5_w10"]
    pct = float((np.array(pl) < main_arm["sharpe"]).mean() * 100)
    M.log(f"placebo wait_up5: real {main_arm['sharpe']:.2f} vs shuffled mean {np.mean(pl):.2f} max {np.max(pl):.2f} -> pct {pct:.0f}")
    # a plain momentum control: does the +5 % confirmation work WITHOUT the ML score? enter any LIQ name whose close is >= 105 % of its
    # close 1-10 days ago, ranked by that 10-day return (no score) - same book mechanics via a fake score
    mom = np.full_like(S, np.nan)
    Adf = A.copy()
    with np.errstate(invalid="ignore", divide="ignore"):
        r10 = Adf / np.vstack([np.full((10, A.shape[1]), np.nan), Adf[:-10]]) - 1
    mom = np.where(liq, r10, np.nan)
    rt = c_in + c_out
    ctrl_e = np.where(np.isfinite(mom), mom, np.nan) * 0 + np.where(np.isfinite(mom), 3 * np.nan_to_num(rt, nan=0.01), np.nan)   # always "qualifies"
    ctrl_e = np.where(np.isfinite(mom), ctrl_e + 1e-6 * mom, np.nan)
    Rc, logc = F.book(A, liq, ctrl_e, 10, c_in, c_out, 2.0, t_start=t0, wait=(0.05, 10))
    ctrl = M.stats(Rc, dates, t0)
    M.log(f"control (no ML score, +5 % in 10 d on LIQ ranked by 10-day momentum): CAGR {ctrl['cagr'] * 100:.1f} % Sharpe {ctrl['sharpe']:.2f} mDD {ctrl['mdd'] * 100:.0f} % trades {len(logc)}")
    robust = n_pass >= 7 and pct >= 95 and main_arm["years_pos"] >= 4
    verdict = ("ROBUST" if robust else "FRAGILE") + f": neighbours {n_pass}/9 >= base + 0.15, placebo pct {pct:.0f}, years + {main_arm['years_pos']}/5"
    n_trials = N_BEFORE + len(grid)
    L = [f"# IDX menu ML-6g - robustness of the up-confirmation entry - {date.today()} - {len(grid)} trials, cumulative N = {n_trials}", "",
         f"Base (ML-6 e5|2|3|10): {base['cagr'] * 100:+.1f} % / {base['sharpe']:.2f} / {base['mdd'] * 100:.0f} %; bar = Sharpe >= {bar:.2f}.", "",
         "| threshold | window | trades | win | avg net | CAGR | Sharpe | mDD | years + | by year |", "|---|---|---|---|---|---|---|---|---|---|"]
    for k, r in grid.items():
        L.append(f"| +{r['th'] * 100:.0f} % | {r['wd']} d | {r['trades']} | {r['win'] * 100:.0f} % | {r['avg'] * 100:+.2f} % | {r['cagr'] * 100:+.1f} % | {r['sharpe']:.2f} | {r['mdd'] * 100:.0f} % | "
                 f"{r['years_pos']}/{r['n_years']} | " + " ".join(f"{str(y)[2:]}:{v * 100:+.0f}" for y, v in r["by_year"].items()) + " |")
    L += ["", f"Placebo (wait_up5, scores shuffled within day, {M.N_PLACEBO} runs): real Sharpe {main_arm['sharpe']:.2f}, shuffled mean {np.mean(pl):.2f}, max {np.max(pl):.2f} -> pct {pct:.0f}.",
          f"Control without the ML score (any LIQ name up 5 % in 10 d, ranked by 10-day momentum, same book): {ctrl['cagr'] * 100:+.1f} % / {ctrl['sharpe']:.2f} / {ctrl['mdd'] * 100:.0f} %.",
          "", "## Verdict (menu ML-6g, study stored)", "", verdict + "."]
    text = "\n".join(L)
    out = os.path.join(HERE, f"IDX_ML_CONFIRM2_{date.today()}.md")
    open(out, "w", encoding="utf-8").write(text + "\n")
    print(text)
    with psycopg.connect(dsn) as conn:
        sid = rs.record_study(conn, STUDY, date.today(), params={"trials": list(grid), "n_trials_cumulative": n_trials, "base": "e5|2|3|10", "main": "up5_w10"},
                              summary=common.plain({"grid": grid, "base": base, "placebo": {"pct": pct, "mean": float(np.mean(pl)), "max": float(np.max(pl))},
                                                    "control_no_ml": ctrl, "neighbours_pass": n_pass, "verdict": verdict}), names=[], report_path=out)
        conn.commit()
    M.log(f"study #{sid} stored")
    return 0


if __name__ == "__main__":
    sys.exit(main())
