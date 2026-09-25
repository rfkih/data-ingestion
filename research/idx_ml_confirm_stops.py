#!/usr/bin/env python3
"""IDX menu ML-6h - stops on the up-confirmation entry (operator, 2026-09-25: "kalau yang masuk saat naik 5 persen ada stoploss nya
gimana? rata2 tp di angka berapa? apa yang menentukan titik tp/sl nya?").

Base = wait_up5: ML-6 book, a signalled name is bought only after its close is >= 105 % of the signal close within 10 days (study
#160/#161: +36 %/yr, Sharpe 1.38, mDD -27 %). Exits of the base: the score turns negative and a better name pays the swap, or 61 days.
PRE-REGISTERED (7 trials; cumulative 792 + 7 = 799):
  stop5 stop10 stop15 stop20   fixed stop from the fill: close <= (1 - x) x fill close, sold at the next close
  trail10 trail15 trail20      trailing stop from the peak close since the fill
READING RULE: vs the base on the whole window: Sharpe >= base + 0.15, mDD not deeper, CAGR >= 0.8 base -> BETTER; money rule reported.
Also reported (descriptive): the base's trade anatomy - exit reasons, average win/loss, MFE/MAE, how far the winners ran.
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
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "blackheart-ingest", "src"))
import idx_ml_costaware as C  # noqa: E402
import idx_ml_strategy as M  # noqa: E402
from blackheart_ingest.idx import research_store as rs  # noqa: E402
from blackheart_ingest.idx.ml import common  # noqa: E402

N_BEFORE = 792
STUDY = "ml_confirm_stops"
WAIT = (0.05, 10)
ARMS = {"stop5": dict(stop=0.05), "stop10": dict(stop=0.10), "stop15": dict(stop=0.15), "stop20": dict(stop=0.20),
        "trail10": dict(trail=0.10), "trail15": dict(trail=0.15), "trail20": dict(trail=0.20)}


def book(A, mask, e, k, c_in, c_out, margin, *, wait=WAIT, stop=None, trail=None, t_start=0, max_hold=C.MAX_HOLD):
    T, N = A.shape
    ret = np.nan_to_num(np.vstack([np.full((1, N), np.nan), A[1:] / A[:-1] - 1]))
    R = np.zeros(T)
    w = 1.0 / k
    held: dict[int, dict] = {}
    watch: dict[int, dict] = {}
    pend_sell: list[tuple[int, str]] = []
    pend_buy: list[int] = []
    log = []
    rt = c_in + c_out
    watch_sig: dict[int, int] = {}
    for t in range(t_start, T - 1):
        for j, why in pend_sell:
            if j in held:
                p = held.pop(j)
                R[t] += w * (ret[t, j] - c_out[t, j])
                path = A[p["t"]:t + 1, j] / A[p["t"], j] - 1
                log.append({"j": j, "t_in": p["t"], "t_out": t, "why": why, "gross": A[t, j] / A[p["t"], j] - 1,
                            "net": (A[t, j] / A[p["t"], j]) * (1 - c_out[t, j]) / (1 + c_in[p["t"], j]) - 1,
                            "mfe": float(np.nanmax(path)), "mae": float(np.nanmin(path)), "hold": t - p["t"], "sig_to_fill": p["t"] - p["t_sig"]})
        for j in pend_buy:
            if j not in held and len(held) < k and not np.isnan(A[t, j]):
                held[j] = {"t": t, "t_sig": watch_sig.get(j, t), "peak": A[t, j]}
                R[t] -= w * c_in[t, j]
        for j, p in held.items():
            if all(j != s for s, _ in pend_sell):
                R[t] += w * ret[t, j]
            if not np.isnan(A[t, j]):
                p["peak"] = max(p["peak"], A[t, j])
        pend_sell, pend_buy = [], []
        watch_sig = {j: v["t"] for j, v in watch.items()}
        ok = mask[t] & np.isfinite(e[t]) & ~np.isnan(A[t]) & ~np.isnan(A[t + 1])
        cand = np.flatnonzero(ok)
        order = cand[np.argsort(-e[t, cand], kind="stable")] if len(cand) else cand
        best = float(e[t, order[0]]) if len(order) else -np.inf
        for j, p in held.items():
            px = A[t, j]
            if (t - p["t"]) >= max_hold:
                pend_sell.append((j, "max_hold"))
            elif np.isnan(A[t + 1, j]) or not np.isfinite(e[t, j]):
                pend_sell.append((j, "gone"))
            elif stop is not None and not np.isnan(px) and px <= (1 - stop) * A[p["t"], j]:
                pend_sell.append((j, "stop"))
            elif trail is not None and not np.isnan(px) and px <= (1 - trail) * p["peak"]:
                pend_sell.append((j, "trail"))
            elif e[t, j] < 0 and best - e[t, j] > margin * rt[t, j]:
                pend_sell.append((j, "swap"))
        for j in list(watch):
            v = watch[j]
            if t > v["until"] or j in held:
                watch.pop(j)
                continue
            if ok[j] and e[t, j] > margin * rt[t, j] and A[t, j] >= (1 + wait[0]) * v["ref"]:
                pend_buy.append(j)
                watch_sig[j] = v["t"]
                watch.pop(j)
        free = k - (len(held) - len(pend_sell)) - len(pend_buy) - len(watch)
        for j in order:
            if free <= 0:
                break
            if j in held or any(j == s for s, _ in pend_sell) or j in watch or j in pend_buy:
                continue
            if e[t, j] > margin * rt[t, j]:
                watch[j] = {"t": t, "ref": A[t, j], "until": t + wait[1]}
                free -= 1
    return R, pd.DataFrame(log)


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
    res: dict[str, dict] = {}
    logs: dict[str, pd.DataFrame] = {}
    for name, kw in {"base": {}, **ARMS}.items():
        R, log = book(A, liq, e5, 10, c_in, c_out, 2.0, t_start=t0, **kw)
        st = M.stats(R, dates, t0)
        by = log.groupby("why")["net"].agg(["size", "mean"])
        res[name] = {**st, "trades": len(log), "win": float((log["net"] > 0).mean()), "avg": float(log["net"].mean()), "hold": float(log["hold"].mean()),
                     "by_reason": {k: {"n": int(v["size"]), "avg": float(v["mean"])} for k, v in by.iterrows()}}
        logs[name] = log
        M.log(f"{name:<8} CAGR {st['cagr'] * 100:6.1f} % Sharpe {st['sharpe']:5.2f} mDD {st['mdd'] * 100:6.1f} % trades {len(log)} win {res[name]['win'] * 100:.0f} % avg {res[name]['avg'] * 100:+.2f} % "
              f"hold {res[name]['hold']:.0f} d " + " ".join(f"{str(y)[2:]}:{v * 100:+.0f}" for y, v in st["by_year"].items()) + " | "
              + ", ".join(f"{k}: n {v['n']} avg {v['avg'] * 100:+.1f} %" for k, v in res[name]["by_reason"].items()))
    b = res["base"]
    for name in ARMS:
        r = res[name]
        why = []
        if r["sharpe"] < b["sharpe"] + 0.15:
            why.append(f"sharpe {r['sharpe']:.2f} < base {b['sharpe']:.2f} + 0.15")
        if r["mdd"] < b["mdd"]:
            why.append("mdd deeper")
        if r["cagr"] < 0.8 * b["cagr"]:
            why.append("cagr < 80 % base")
        r["verdict"] = "BETTER" if not why else "no: " + "; ".join(why)
        r["money_rule"] = bool(r["mdd"] >= -0.25 and r["sharpe"] >= 1.0)
    # anatomy of the base
    L0 = logs["base"]
    w_, l_ = L0[L0["net"] > 0], L0[L0["net"] <= 0]
    anat = {"n": len(L0), "win": float((L0["net"] > 0).mean()), "avg_win": float(w_["net"].mean()), "med_win": float(w_["net"].median()), "avg_loss": float(l_["net"].mean()),
            "med_loss": float(l_["net"].median()), "mfe_win_med": float(w_["mfe"].median()), "mfe_win_mean": float(w_["mfe"].mean()), "mae_win_med": float(w_["mae"].median()),
            "mfe_loss_med": float(l_["mfe"].median()), "mae_loss_med": float(l_["mae"].median()), "mae_all_med": float(L0["mae"].median()),
            "giveback_win_med": float((w_["mfe"] - w_["gross"]).median()), "sig_to_fill_mean": float(L0["sig_to_fill"].mean()), "hold_win": float(w_["hold"].mean()), "hold_loss": float(l_["hold"].mean()),
            "pct_net": {f"p{int(q * 100)}": float(v) for q, v in L0["net"].quantile([0.1, 0.25, 0.5, 0.75, 0.9]).items()},
            "share_mae_gt_5": float((L0["mae"] > -0.05).mean()), "share_win_mae_gt_5": float((w_["mae"] > -0.05).mean()), "share_mae_lt_10": float((L0["mae"] < -0.10).mean()),
            "recover_after_10": float((L0.loc[L0["mae"] < -0.10, "net"] > 0).mean())}
    M.log("base anatomy: " + ", ".join(f"{k} {v:.3f}" if isinstance(v, float) else f"{k} {v}" for k, v in anat.items()))
    n_trials = N_BEFORE + len(ARMS)
    L = [f"# IDX menu ML-6h - stops on the up-confirmation entry - {date.today()} - {len(ARMS)} trials, cumulative N = {n_trials}", "",
         "| arm | trades | win | avg net | hold d | CAGR | Sharpe | mDD | by year | exits | verdict |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, r in res.items():
        L.append(f"| {name} | {r['trades']} | {r['win'] * 100:.0f} % | {r['avg'] * 100:+.2f} % | {r['hold']:.0f} | {r['cagr'] * 100:+.1f} % | {r['sharpe']:.2f} | {r['mdd'] * 100:.0f} % | "
                 + " ".join(f"{str(y)[2:]}:{v * 100:+.0f}" for y, v in r["by_year"].items()) + " | "
                 + ", ".join(f"{k} n {v['n']} avg {v['avg'] * 100:+.1f} %" for k, v in r["by_reason"].items()) + f" | {r.get('verdict', 'reference')} |")
    L += ["", "## Base (wait_up5) trade anatomy", "", "| stat | value |", "|---|---|"]
    for k, v in anat.items():
        L.append(f"| {k} | {v if not isinstance(v, float) else round(v, 4)} |")
    L += ["", "## Verdict", "", f"BETTER: {', '.join(n for n in ARMS if res[n]['verdict'] == 'BETTER') or 'none'}; money rule: {', '.join(n for n in ARMS if res[n]['money_rule']) or 'none'}."]
    text = "\n".join(L)
    out = os.path.join(HERE, f"IDX_ML_CONFIRM_STOPS_{date.today()}.md")
    open(out, "w", encoding="utf-8").write(text + "\n")
    print(text)
    L0.to_csv(os.path.join(os.path.dirname(HERE), "research-scratch", "ml_waitup5_trades.csv"), index=False)
    with psycopg.connect(dsn) as conn:
        sid = rs.record_study(conn, STUDY, date.today(), params={"trials": list(ARMS), "n_trials_cumulative": n_trials, "base": "wait_up5 on e5|2|3|10"},
                              summary=common.plain({"arms": res, "anatomy": anat}), names=[], report_path=out)
        conn.commit()
    M.log(f"study #{sid} stored")
    return 0


if __name__ == "__main__":
    sys.exit(main())
