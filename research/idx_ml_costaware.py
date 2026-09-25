#!/usr/bin/env python3
"""IDX menu ML-6 — cost-aware use of the prediction desk's scores (operator, 2026-09-25: "menurutku kamu salah dalam menggunakan
ML modelnya ... cari tau cara terbaik untuk memanfaatkan seluruh data dan arsitektur yang kita punya").

What ML-4/4b/5 did with the scores was naive: fixed-horizon cohorts that rotate every 5 or 20 days no matter what the score
says, and a rank-hysteresis that churned because a 5-day rank is noise. This menu uses the score the way a cost-aware desk
would: as an EXPECTED RETURN IN BASIS POINTS compared with the round-trip cost of the trade it would cause.

PRE-REGISTERED (10 trials; cumulative 741 + 10 = 751). Scores = the ML-4 walk-forward OOS 5d and 20d predictions (log return);
  e5 = the name's 5d prediction minus that day's LIQ median (expected 5-day excess), e20 likewise; optionally EMA-smoothed
  over 3 days. Costs as ML-4 (closing offer/bid + fees; LIQ round trip ~91 bps). Book from 2022-01, LIQ, K slots, equal weight.
  Position book rule (signals at close t, trades at close t+1):
    BUY into an empty slot the best-ranked name with e > margin x its own round-trip cost
    SELL a holding when its e < 0 (expected below the universe median) AND the best candidate beats it by > margin x cost,
         or after max_hold days, or when the price disappears; otherwise HOLD - the score has to pay for the trade it causes
  Arms (score | margin | ema | K):   e5|1|1|10   e5|2|1|10   e5|1|3|10   e5|2|3|10   e5|2|3|5   e20|1|3|10   e20|2|3|10
    rank5|2|3|10   = the same book on a model retrained walk-forward on the CROSS-SECTIONAL PERCENTILE of the 5d return
                     (a ranking target instead of a return target); e = predicted percentile - 0.5, scaled to bps by the
                     year's realised decile spread (known from the training years)
    blend|2|3|10   = rank-mean of e5 and e20 percentiles, thresholds on e5
    e5_gate|2|3|10 = e5|2|3|10 with the regime gate on new entries
  References: random with the same trade frequency (placebo below), ML-4's fixed cohorts, COMPOSITE.
READING RULE: as ML-4 (Sharpe >= 1.2; mDD >= -25 %; >= 4/5 years positive; placebo pct >= 95 on the best arm (scores
  shuffled within day, 20 runs)). A CANDIDATE beats the desk only above the gated combined book's 1.54 (2020-26) - on this
  2022+ window the trend book's own Sharpe is 1.24, quoted for scale.
READ-ONLY; one idx.study row. Needs IDX_ML_CACHE from ML-4.
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
import idx_ml_strategy as M  # noqa: E402
from blackheart_ingest.idx import research_store as rs  # noqa: E402
from blackheart_ingest.idx.ml import common, daily  # noqa: E402

N_BEFORE = 741
STUDY = "ml_costaware"
ARMS = ["e5|1|1|10", "e5|2|1|10", "e5|1|3|10", "e5|2|3|10", "e5|2|3|5", "e20|1|3|10", "e20|2|3|10", "rank5|2|3|10", "blend|2|3|10", "e5_gate|2|3|10"]
MAX_HOLD = 60
FROM = date(2022, 1, 1)


def book(A, mask, e, k, c_in, c_out, margin, gate=None, t_start=0, max_hold=MAX_HOLD):
    """Cost-aware position book. e = expected excess log return per name-day (NaN = no view). -> R, trades, mean hold."""
    T, N = A.shape
    ret = np.nan_to_num(np.vstack([np.full((1, N), np.nan), A[1:] / A[:-1] - 1]))
    R = np.zeros(T)
    w = 1.0 / k
    held: dict[int, int] = {}
    pend_sell: list[int] = []
    pend_buy: list[int] = []
    trades, holds = 0, []
    rt = c_in + c_out                                   # round-trip cost by name-day
    for t in range(t_start, T - 1):
        for j in pend_sell:
            if j in held:
                R[t] += w * ret[t, j] - w * c_out[t, j]
                holds.append(t - held.pop(j))
        for j in pend_buy:
            if j not in held and len(held) < k and not np.isnan(A[t, j]):
                held[j] = t
                R[t] -= w * c_in[t, j]
                trades += 1
        for j in held:
            if j not in pend_sell:
                R[t] += w * ret[t, j]
        pend_sell, pend_buy = [], []
        ok = mask[t] & np.isfinite(e[t]) & ~np.isnan(A[t]) & ~np.isnan(A[t + 1])
        if gate is not None and not gate[t]:
            ok_new = np.zeros(N, dtype=bool)
        else:
            ok_new = ok
        cand = np.flatnonzero(ok_new)
        order = cand[np.argsort(-e[t, cand], kind="stable")] if len(cand) else cand
        best = float(e[t, order[0]]) if len(order) else -np.inf
        for j, t_in in held.items():
            stale = (t - t_in) >= max_hold or np.isnan(A[t + 1, j]) or not np.isfinite(e[t, j])
            worse = np.isfinite(e[t, j]) and e[t, j] < 0 and best - e[t, j] > margin * rt[t, j]
            if stale or worse:
                pend_sell.append(j)
        free = k - (len(held) - len(pend_sell))
        for j in order:
            if free <= 0:
                break
            if j in held or j in pend_sell:
                continue
            if e[t, j] > margin * rt[t, j]:
                pend_buy.append(int(j))
                free -= 1
    return R, trades, (float(np.mean(holds)) if holds else float("nan"))


def ema(X: np.ndarray, span: int) -> np.ndarray:
    if span <= 1:
        return X
    return pd.DataFrame(X).ewm(span=span, min_periods=1).mean().to_numpy()


def rank_target_scores(P: pd.DataFrame) -> pd.DataFrame:
    """Walk-forward as ML-4, target = the day's percentile of the 5d return within LIQ; returns (percentile prediction, the
    training years' realised top-minus-bottom decile spread used to express it in log-return units)."""
    feats = daily.FEATURES
    P = P.sort_values(["code", "d"]).reset_index(drop=True)
    cal = np.sort(pd.unique(P["d"]))
    year = P["d"].dt.year.to_numpy()
    liq = P["liq"].to_numpy()
    y_pct = P.groupby("d")["fwd_5d"].rank(pct=True).to_numpy(float)
    X = common.to_matrix(P, feats)
    P["r5"] = np.nan
    P["r5_scale"] = np.nan
    for Y in M.TEST_YEARS:
        cut = common.purge_cut(cal, np.datetime64(date(Y, 1, 1)), 5)
        fit_m = (P["d"].to_numpy() < cut) & np.isfinite(y_pct) & liq
        test_m = year == Y
        if fit_m.sum() < 20000:
            continue
        params = dict(common.BASE_PARAMS["ret"], objective="regression")
        bst = common.fit(X[fit_m], y_pct[fit_m], "ret", params, feats, seed=M.SEED + Y)
        P.loc[test_m, "r5"] = np.asarray(bst.predict(X[test_m]), dtype=float)
        F = P[fit_m]
        q = F.groupby("d")["fwd_5d"].transform(lambda s: s.rank(pct=True))
        spread = F.loc[q >= 0.9, "fwd_5d"].mean() - F.loc[q <= 0.1, "fwd_5d"].mean()
        P.loc[test_m, "r5_scale"] = float(spread)
        M.log(f"rank target {Y}: fit {int(fit_m.sum()):,}, training decile spread {spread * 1e4:+.0f} bps")
    return P


def main() -> int:
    dsn = os.environ["INGEST_DB_DSN"]
    P = pickle.load(open(os.environ["IDX_ML_CACHE"], "rb"))
    if "r5" not in P:
        P = rank_target_scores(P)
        pickle.dump(P, open(os.environ["IDX_ML_CACHE"], "wb"))
    P = P[P["d"] >= "2021-06-01"].copy()
    dates = M.wide(P, "close").index
    codes = M.wide(P, "close").columns
    g = lambda c: M.wide(P, c).reindex(index=dates, columns=codes)  # noqa: E731
    A = g("ac").to_numpy(float)
    c_in, c_out = M.costs(g("close").to_numpy(float), g("offer").to_numpy(float), g("bid").to_numpy(float))
    liq = g("liq").fillna(False).astype(bool).to_numpy()
    comp = g("comp_dma200").max(axis=1).ffill().to_numpy(float)
    gate = comp > 0
    t0 = int(np.searchsorted(dates, np.datetime64(FROM)))

    def excess(col: str) -> np.ndarray:
        S = g(col).to_numpy(float)
        Sl = np.where(liq, S, np.nan)
        med = np.nanmedian(Sl, axis=1, keepdims=True)
        return S - med

    e5, e20 = excess("s5"), excess("s20")
    r5 = g("r5").to_numpy(float)
    scale = g("r5_scale").max(axis=1).ffill().to_numpy(float)[:, None]
    rank5 = (r5 - np.nanmedian(np.where(liq, r5, np.nan), axis=1, keepdims=True)) * scale      # percentile gap -> log-return units
    p5 = pd.DataFrame(np.where(liq, e5, np.nan)).rank(axis=1, pct=True).to_numpy()
    p20 = pd.DataFrame(np.where(liq, e20, np.nan)).rank(axis=1, pct=True).to_numpy()
    blend_pct = np.nanmean(np.stack([p5, p20]), axis=0)
    blend = np.where(np.isfinite(blend_pct), e5, np.nan)                 # thresholds on e5, order by the blend (see below)
    res: dict[str, dict] = {}
    for arm in ARMS:
        name, margin, span, k = arm.split("|")
        margin, span, k = float(margin), int(span), int(k)
        src = {"e5": e5, "e20": e20, "rank5": rank5, "blend": blend, "e5_gate": e5}[name]
        e = ema(src, span)
        if name == "blend":
            # order by the blended percentile but keep e5's bps for the cost test: encode as e5 + tiny tie-break by percentile
            e = e + 1e-6 * np.nan_to_num(ema(blend_pct, span))
        R, n, hold = book(A, liq, e, k, c_in, c_out, margin, gate=gate if name == "e5_gate" else None, t_start=t0)
        st = M.stats(R, dates, t0)
        res[arm] = {**st, "trades": n, "hold_days": hold, "turnover_per_year": n / st["years"] / k}
        M.log(f"{arm:<15} CAGR {st['cagr'] * 100:6.1f} %  Sharpe {st['sharpe']:5.2f}  mDD {st['mdd'] * 100:6.1f} %  trades {n:,} hold {hold:.0f} d  "
              f"years+ {st['years_pos']}/{st['n_years']}  " + " ".join(f"{str(y)[2:]}:{v * 100:+.0f}" for y, v in st["by_year"].items()))
    best = max(ARMS, key=lambda a: res[a]["sharpe"])
    name, margin, span, k = best.split("|")
    src = {"e5": e5, "e20": e20, "rank5": rank5, "blend": e5, "e5_gate": e5}[name]
    rng = np.random.default_rng(M.SEED)
    pl = []
    for _ in range(M.N_PLACEBO):
        sh = src.copy()
        for t in range(t0, len(dates)):
            idx = np.flatnonzero(liq[t] & np.isfinite(sh[t]))
            if len(idx) > 1:
                sh[t, idx] = sh[t, rng.permutation(idx)]
        R, _, _ = book(A, liq, ema(sh, int(span)), int(k), c_in, c_out, float(margin), gate=gate if name == "e5_gate" else None, t_start=t0)
        pl.append(M.stats(R, dates, t0)["sharpe"])
    res[best]["placebo"] = {"n": M.N_PLACEBO, "pct": float((np.array(pl) < res[best]["sharpe"]).mean() * 100), "mean": float(np.mean(pl)), "max": float(np.max(pl))}
    M.log(f"placebo {best}: real {res[best]['sharpe']:.2f} vs shuffled mean {np.mean(pl):.2f} max {np.max(pl):.2f} -> pct {res[best]['placebo']['pct']:.0f}")
    for arm in ARMS:
        r = res[arm]
        fails = []
        if r["sharpe"] < 1.2:
            fails.append(f"sharpe {r['sharpe']:.2f} < 1.2")
        if r["mdd"] < -0.25:
            fails.append(f"mdd {r['mdd'] * 100:.0f} % < -25 %")
        if r["years_pos"] < min(4, r["n_years"]):
            fails.append(f"{r['years_pos']}/{r['n_years']} years positive")
        if "placebo" in r and r["placebo"]["pct"] < 95:
            fails.append(f"placebo pct {r['placebo']['pct']:.0f}")
        r["verdict"] = "CANDIDATE" if not fails else "not a candidate: " + "; ".join(fails)
    n_trials = N_BEFORE + len(ARMS)
    L = [f"# IDX menu ML-6 — cost-aware use of the prediction desk's scores — {date.today()} — {len(ARMS)} trials, cumulative N = {n_trials}", "",
         "Position book on LIQ from 2022-01: buy when the expected 5d/20d excess (bps) exceeds margin x the name's round-trip cost, hold until the "
         "score turns negative AND a better name pays for the swap (or 60 days). Same OOS scores and costs as ML-4.", "",
         "| arm (score, margin, ema, K) | trades | hold d | turns/yr/slot | CAGR | Sharpe | mDD | years + | by year | verdict |", "|---|---|---|---|---|---|---|---|---|---|"]
    for arm in ARMS:
        r = res[arm]
        by = " ".join(f"{str(y)[2:]}:{v * 100:+.0f}" for y, v in r["by_year"].items())
        pl_s = f" (placebo pct {r['placebo']['pct']:.0f})" if "placebo" in r else ""
        L.append(f"| {arm} | {r['trades']:,} | {r['hold_days']:.0f} | {r['turnover_per_year']:.1f} | {r['cagr'] * 100:+.1f} % | {r['sharpe']:.2f} | {r['mdd'] * 100:.0f} % | "
                 f"{r['years_pos']}/{r['n_years']} | {by} | {r['verdict']}{pl_s} |")
    L += ["", "For scale on the same window: ML-4 fixed cohorts s5/H5 net -20.5 %/yr (gross +26.4 %, Sharpe 0.86); the deployed trend book (small, gate) "
          "+20.1 %/yr Sharpe 1.24 mDD -18 %; COMPOSITE ~+5 %/yr.", "", "## Verdict (menu ML-6, study stored)", "",
          f"Best arm: **{best}** ({res[best]['cagr'] * 100:+.1f} %/yr, Sharpe {res[best]['sharpe']:.2f}, mDD {res[best]['mdd'] * 100:.0f} %, hold {res[best]['hold_days']:.0f} d) - {res[best]['verdict']}.",
          f"Candidates: {', '.join(a for a in ARMS if res[a]['verdict'] == 'CANDIDATE') or 'none'}."]
    text = "\n".join(L)
    out = os.path.join(HERE, f"IDX_ML_COSTAWARE_{date.today()}.md")
    open(out, "w", encoding="utf-8").write(text + "\n")
    print(text)
    with psycopg.connect(dsn) as conn:
        sid = rs.record_study(conn, STUDY, date.today(), params={"trials": ARMS, "n_trials_cumulative": n_trials, "max_hold": MAX_HOLD, "from": str(FROM)},
                              summary={"arms": common.plain(res), "best": best}, names=[], report_path=out)
        conn.commit()
    M.log(f"study #{sid} stored; report {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
