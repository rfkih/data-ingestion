#!/usr/bin/env python3
"""IDX menu ML-6d — why does the cost-aware ML book draw down, and can a filter fix it? (operator, 2026-09-25: "cari tau
kenapa drawdown nya tinggi, bisa ditambah filter nggak").

Part 1 (descriptive, no trials): the ML-6 book (e5 | margin 2 | ema 3 | K 10, LIQ, 2022-01 ->) with a trade log; the
drawdown episodes; what the losing trades look like at ENTRY (price band, liquidity, 20-day volatility, prior 20/60-day
return, spread, market regime, sector) against the winners - on 2022 ONLY, the drawdown year.
Part 2 (pre-registered from the 2022 evidence, tested on 2023-2026 which was not used to pick them): entry filters.
  A filter is READ on 2023-26 vs the unfiltered book on 2023-26: Sharpe >= base + 0.15, mDD not deeper, CAGR >= 0.8 base;
  and REPORTED on 2022 (in-sample) for the record. Trials counted = the filters declared in FILTERS (cumulative 760 + n).
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

N_BEFORE = 760
STUDY = "ml_drawdown"
MARGIN, SPAN, K = 2.0, 3, 10
FROM = date(2022, 1, 1)
OOS_FROM = date(2023, 1, 1)


def book_log(A, mask, e, k, c_in, c_out, margin, t_start=0, max_hold=C.MAX_HOLD):
    """ML-6's book, returning the daily returns AND a trade log (entry/exit day index, name index, net return, reason)."""
    T, N = A.shape
    ret = np.nan_to_num(np.vstack([np.full((1, N), np.nan), A[1:] / A[:-1] - 1]))
    R = np.zeros(T)
    w = 1.0 / k
    held: dict[int, int] = {}
    pend_sell: list[tuple[int, str]] = []
    pend_buy: list[int] = []
    log = []
    rt = c_in + c_out
    for t in range(t_start, T - 1):
        for j, why in pend_sell:
            if j in held:
                R[t] += w * ret[t, j] - w * c_out[t, j]
                t_in = held.pop(j)
                gross = A[t, j] / A[t_in, j] - 1
                log.append({"t_in": t_in, "t_out": t, "j": j, "gross": gross, "net": (1 + gross) * (1 - c_out[t, j]) / (1 + c_in[t_in, j]) - 1, "why": why})
        for j in pend_buy:
            if j not in held and len(held) < k and not np.isnan(A[t, j]):
                held[j] = t
                R[t] -= w * c_in[t, j]
        for j in held:
            if all(j != s for s, _ in pend_sell):
                R[t] += w * ret[t, j]
        pend_sell, pend_buy = [], []
        ok = mask[t] & np.isfinite(e[t]) & ~np.isnan(A[t]) & ~np.isnan(A[t + 1])
        cand = np.flatnonzero(ok)
        order = cand[np.argsort(-e[t, cand], kind="stable")] if len(cand) else cand
        best = float(e[t, order[0]]) if len(order) else -np.inf
        for j, t_in in held.items():
            if (t - t_in) >= max_hold:
                pend_sell.append((j, "max_hold"))
            elif np.isnan(A[t + 1, j]) or not np.isfinite(e[t, j]):
                pend_sell.append((j, "gone"))
            elif e[t, j] < 0 and best - e[t, j] > margin * rt[t, j]:
                pend_sell.append((j, "swap"))
        free = k - (len(held) - len(pend_sell))
        for j in order:
            if free <= 0:
                break
            if j in held or any(j == s for s, _ in pend_sell):
                continue
            if e[t, j] > margin * rt[t, j]:
                pend_buy.append(int(j))
                free -= 1
    return R, pd.DataFrame(log)


def drawdowns(R: np.ndarray, dates, top: int = 3) -> list[dict]:
    eq = np.cumprod(1 + R)
    peak = np.maximum.accumulate(eq)
    dd = eq / peak - 1
    out = []
    i = 0
    while i < len(dd):
        if dd[i] < 0:
            j = i
            while j < len(dd) and dd[j] < 0:
                j += 1
            k = i + int(np.argmin(dd[i:j]))
            out.append({"from": str(dates[i - 1].date()) if i else str(dates[0].date()), "trough": str(dates[k].date()), "to": str(dates[min(j, len(dd) - 1)].date()),
                        "depth": float(dd[k]), "days": j - i})
            i = j
        else:
            i += 1
    return sorted(out, key=lambda x: x["depth"])[:top]


def main() -> int:
    dsn = os.environ["INGEST_DB_DSN"]
    P = pickle.load(open(os.environ["IDX_ML_CACHE"], "rb"))
    P = P[P["d"] >= "2021-06-01"].copy()
    dates = M.wide(P, "close").index
    codes = M.wide(P, "close").columns
    g = lambda c: M.wide(P, c).reindex(index=dates, columns=codes)  # noqa: E731
    A = g("ac").to_numpy(float)
    close = g("close").to_numpy(float)
    c_in, c_out = M.costs(close, g("offer").to_numpy(float), g("bid").to_numpy(float))
    liq = g("liq").fillna(False).astype(bool).to_numpy()
    S = g("s5").to_numpy(float)
    e5 = C.ema(S - np.nanmedian(np.where(liq, S, np.nan), axis=1, keepdims=True), SPAN)
    t0 = int(np.searchsorted(dates, np.datetime64(FROM)))
    t1 = int(np.searchsorted(dates, np.datetime64(OOS_FROM)))
    feats = {k: g(k).to_numpy(float) for k in ("vol20", "ret20", "ret60", "spread_bps", "lvalue60", "comp_dma200", "comp_r20", "sector", "gap", "volr1",
                                                "dist_hi252", "up_days", "breadth", "lmcap", "free_float", "atr_pct", "pos20")}
    feats["value60"] = np.expm1(feats["lvalue60"])
    R, log = book_log(A, liq, e5, K, c_in, c_out, MARGIN, t_start=t0)
    base_all = M.stats(R, dates, t0)
    M.log(f"base book: CAGR {base_all['cagr'] * 100:.1f} % Sharpe {base_all['sharpe']:.2f} mDD {base_all['mdd'] * 100:.0f} %, {len(log)} closed trades")
    dds = drawdowns(R[t0:], dates[t0:])
    for d in dds:
        M.log(f"drawdown {d['depth'] * 100:.0f} % from {d['from']} trough {d['trough']} to {d['to']} ({d['days']} days)")
    log["d_in"], log["d_out"] = dates[log["t_in"]], dates[log["t_out"]]
    log["code"] = codes[log["j"]]
    for k, W in feats.items():
        log[k] = W[log["t_in"].to_numpy(), log["j"].to_numpy()]
    log["price"] = close[log["t_in"].to_numpy(), log["j"].to_numpy()]
    log["year"] = log["d_in"].dt.year
    log["hold"] = log["t_out"] - log["t_in"]
    log["e_in"] = e5[log["t_in"].to_numpy(), log["j"].to_numpy()]
    L22 = log[log["year"] == 2022].copy()
    L22["loser"] = L22["net"] < -0.10
    M.log(f"2022: {len(L22)} trades, net mean {L22['net'].mean() * 100:+.1f} %, hit {(L22['net'] > 0).mean() * 100:.0f} %, "
          f"losers (< -10 %) {int(L22['loser'].sum())} contribute {L22.loc[L22['loser'], 'net'].sum() * 100:+.0f} pp of sum {L22['net'].sum() * 100:+.0f} pp; "
          f"by reason: " + ", ".join(f"{k}: n {v['n']} mean {v['m'] * 100:+.1f} %" for k, v in
                                     {w: {"n": len(x), "m": x["net"].mean()} for w, x in L22.groupby("why")}.items()))
    M.log("worst 12 trades of 2022: " + "; ".join(f"{r.code} {r.d_in.date()} {r.net * 100:+.0f} % ({r.why}, hold {r.hold} d, px {r.price:.0f}, vol20 {r.vol20 * 100:.1f} %, ret20 {r.ret20 * 100:+.0f} %)"
                                                  for r in L22.nsmallest(12, "net").itertuples()))
    profile = {}
    for k in ("price", "value60", "vol20", "ret20", "ret60", "spread_bps", "gap", "volr1", "dist_hi252", "atr_pct", "pos20", "free_float", "lmcap", "e_in", "comp_dma200", "breadth"):
        a, b = L22.loc[L22["loser"], k], L22.loc[~L22["loser"], k]
        profile[k] = {"loser_median": float(np.nanmedian(a)), "other_median": float(np.nanmedian(b))}
        M.log(f"  {k:<12} losers median {np.nanmedian(a):10.4g}   others median {np.nanmedian(b):10.4g}")
    by_band = L22.groupby(pd.cut(L22["price"], [0, 200, 500, 2000, 5000, 1e9]), observed=True)["net"].agg(["size", "mean", lambda x: (x < -0.10).mean()])
    M.log("2022 by price band (n, mean net, share < -10 %):\n" + by_band.to_string())
    by_vol = L22.groupby(pd.qcut(L22["vol20"], 4, duplicates="drop"), observed=True)["net"].agg(["size", "mean", lambda x: (x < -0.10).mean()])
    M.log("2022 by vol20 quartile:\n" + by_vol.to_string())
    by_r20 = L22.groupby(pd.qcut(L22["ret20"], 4, duplicates="drop"), observed=True)["net"].agg(["size", "mean", lambda x: (x < -0.10).mean()])
    M.log("2022 by prior 20-day return quartile:\n" + by_r20.to_string())
    by_reg = L22.groupby(L22["comp_dma200"] > 0)["net"].agg(["size", "mean", lambda x: (x < -0.10).mean()])
    M.log("2022 by regime (COMPOSITE > MA200 at entry):\n" + by_reg.to_string())
    # ---- Part 2: filters declared from the 2022 profile (see the report), tested on 2023-26
    q_vol = float(np.nanquantile(feats["vol20"][t0:t1][liq[t0:t1]], 0.75))
    q_r20 = float(np.nanquantile(feats["ret20"][t0:t1][liq[t0:t1]], 0.75))
    FILTERS = {
        "no_vol_top": liq & ~(feats["vol20"] > q_vol),                      # drop the most volatile quarter (threshold from 2022 LIQ)
        "no_runup": liq & ~(feats["ret20"] > q_r20),                        # drop names already up in the top quarter over 20 days
        "price_ge_200": liq & (close >= 200),                               # drop the Rp 1-tick band (35 % ARA/ARB names)
        "no_vol_no_runup": liq & ~(feats["vol20"] > q_vol) & ~(feats["ret20"] > q_r20),
        "regime_on": liq & (feats["comp_dma200"] > 0),                      # new entries only while COMPOSITE > MA200 (entries only; the book keeps selling on score)
    }
    res = {}
    base_oos = M.stats(R, dates, t1)
    base_is = M.stats(R[:t1], dates[:t1], t0)
    res["base"] = {"oos": base_oos, "is2022": base_is, "trades": len(log)}
    M.log(f"base 2023-26: CAGR {base_oos['cagr'] * 100:.1f} % Sharpe {base_oos['sharpe']:.2f} mDD {base_oos['mdd'] * 100:.0f} % | 2022: {base_is['cagr'] * 100:+.1f} % mDD {base_is['mdd'] * 100:.0f} %")
    for name, mask in FILTERS.items():
        Rf, lf = book_log(A, mask, e5, K, c_in, c_out, MARGIN, t_start=t0)
        oos, is22 = M.stats(Rf, dates, t1), M.stats(Rf[:t1], dates[:t1], t0)
        why = []
        if oos["sharpe"] < base_oos["sharpe"] + 0.15:
            why.append(f"sharpe {oos['sharpe']:.2f} < base {base_oos['sharpe']:.2f} + 0.15")
        if oos["mdd"] < base_oos["mdd"]:
            why.append("mdd deeper")
        if oos["cagr"] < 0.8 * base_oos["cagr"]:
            why.append("cagr < 80 % base")
        verdict = "BETTER (OOS 2023-26)" if not why else "no: " + "; ".join(why)
        res[name] = {"oos": oos, "is2022": is22, "trades": len(lf), "verdict": verdict}
        M.log(f"{name:<16} 2023-26: CAGR {oos['cagr'] * 100:6.1f} % Sharpe {oos['sharpe']:5.2f} mDD {oos['mdd'] * 100:6.1f} % | 2022: {is22['cagr'] * 100:+6.1f} % mDD {is22['mdd'] * 100:.0f} % | "
              f"trades {len(lf)} -> {verdict}")
    n_trials = N_BEFORE + len(FILTERS)
    L = [f"# IDX menu ML-6d — the cost-aware ML book's drawdown: anatomy and filters — {date.today()} — {len(FILTERS)} trials, cumulative N = {n_trials}", "",
         f"Base book (e5 | margin 2 | ema 3 | K 10, LIQ, 2022-01 ->): CAGR {base_all['cagr'] * 100:+.1f} %, Sharpe {base_all['sharpe']:.2f}, mDD {base_all['mdd'] * 100:.0f} %, {len(log)} closed trades.", "",
         "## Drawdown episodes", "", "| from | trough | to | depth | days |", "|---|---|---|---|---|"]
    for d in dds:
        L.append(f"| {d['from']} | {d['trough']} | {d['to']} | {d['depth'] * 100:.0f} % | {d['days']} |")
    L += ["", "## 2022 trades: losers (< -10 %) vs the rest, medians at entry", "", "| feature | losers | others |", "|---|---|---|"]
    for k, v in profile.items():
        L.append(f"| {k} | {v['loser_median']:.4g} | {v['other_median']:.4g} |")
    L += ["", "2022 by price band (n, mean net, share < -10 %):", "", "```", by_band.to_string(), "```", "", "2022 by vol20 quartile:", "", "```", by_vol.to_string(), "```",
          "", "2022 by prior 20-day return quartile:", "", "```", by_r20.to_string(), "```", "", "2022 by regime at entry:", "", "```", by_reg.to_string(), "```", "",
          "Worst 12 trades of 2022: " + "; ".join(f"{r.code} {r.d_in.date()} {r.net * 100:+.0f} % ({r.why}, {r.hold} d)" for r in L22.nsmallest(12, "net").itertuples()), "",
          "## Filters (declared from the 2022 profile, read on 2023-26)", "",
          "| filter | trades | 2023-26 CAGR | Sharpe | mDD | 2022 CAGR | 2022 mDD | verdict |", "|---|---|---|---|---|---|---|---|"]
    for name, r in res.items():
        L.append(f"| {name} | {r['trades']} | {r['oos']['cagr'] * 100:+.1f} % | {r['oos']['sharpe']:.2f} | {r['oos']['mdd'] * 100:.0f} % | {r['is2022']['cagr'] * 100:+.1f} % | "
                 f"{r['is2022']['mdd'] * 100:.0f} % | {r.get('verdict', 'reference')} |")
    L += ["", "## Verdict (menu ML-6d, study stored)", "", f"Filters BETTER out of sample: {', '.join(n for n, r in res.items() if str(r.get('verdict', '')).startswith('BETTER')) or 'none'}."]
    text = "\n".join(L)
    out = os.path.join(HERE, f"IDX_ML_DRAWDOWN_{date.today()}.md")
    open(out, "w", encoding="utf-8").write(text + "\n")
    print(text)
    with psycopg.connect(dsn) as conn:
        sid = rs.record_study(conn, STUDY, date.today(), params={"trials": list(FILTERS), "n_trials_cumulative": n_trials, "thresholds": {"vol20_q75_2022": q_vol, "ret20_q75_2022": q_r20},
                                                                   "base": "e5|2|3|10", "oos_from": str(OOS_FROM)},
                              summary=common.plain({"base": base_all, "drawdowns": dds, "profile_2022": profile, "filters": res}), names=[], report_path=out)
        conn.commit()
    M.log(f"study #{sid} stored; report {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
