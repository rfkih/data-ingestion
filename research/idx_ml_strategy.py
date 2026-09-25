#!/usr/bin/env python3
"""IDX menu ML-4 — trading strategies on the prediction desk's models (operator, 2026-09-24: "bikin strategi menggunakan juga
prediksi dari model ini, dan cari strategi terbaik ... gabungan teknikal dan ml, dan broksum dan apapun itu").

The prediction desk (blackheart-ingest idx/ml) forecasts direction and return at 1d..250d from everything the desk holds.
This menu asks the only question that matters for a book: does ranking names by those forecasts, alone or on top of the
technical rules and the broker-flow feed, make money after costs - and does it beat what the desk already runs?

PRE-REGISTERED (12 trials; cumulative 711 + 12 = 723). Declared before the run; nothing tuned afterwards.
  Scores: walk-forward by test year 2022..2026. For a test year Y and horizon h, a LightGBM (the desk's BASE_PARAMS, 300 rounds)
    is fitted on every liquid row whose label window ends before 1 Jan Y (purged: rows dated within h trading days of Y are
    dropped), then scores every row of Y. Targets: 5d log return (abs), 20d and 250d log return in EXCESS of the COMPOSITE,
    P(5d up). Features = the desk's daily panel (idx/ml/daily.py: price, tape, cross-section, market, macro by release date,
    PIT fundamentals, 1-day broker flow, events, sector). No score is ever computed with data from its own year or later.
  Universe LIQ: 60-day mean value >= Rp 5 bn, close >= Rp 100 (the desk's LIQ). Signals at close t, entry at close t+1 at the
    closing offer, exit at close t+1+H at the closing bid, Stockbit fees 0.10 / 0.20 %; equal-weight cohorts (the desk's
    rolling-cohort book: every day k new names, each held H days, slot 1/(k*H) of NAV).
  Arms (H = holding days, k = names per day):
    ml5        top-10 by the 5d return score, H 5                    ml5_gate    the same, no new entry while COMPOSITE < MA200
    ml5_dir    top-10 by P(5d up), H 5                               ml5_k5      top-5 by the 5d score, H 5
    ml20       top-10 by the 20d excess score, H 20                  ml20_gate   with the regime gate
    ml250      top-10 by the 250d excess score, H 250                ml250_fund  the same among profitable, CFO > 0, D/E < 1.5
    combo20    rank-mean of ml20 + 60-day momentum + 20-day foreign net share, H 20      combo20_gate  with the gate
    trend_ml   the trend entry (close = 60-day high, close > MA200, volume >= 1.5x its 20-day mean) ranked by ml20, H 20
    brok20     rank-mean of ml20 + foreign buy share + 1 - buyer HHI (1-day broker flow; history from 2025-09 only), H 20
  References (not trials): random top-10 at each H (5 seeds, mean), 60-day momentum alone H 20, COMPOSITE buy & hold.
READING RULE (declared before the run): an arm is a CANDIDATE only if ALL hold on 2022-01 -> end: Sharpe >= 1.2; max drawdown
  not deeper than -25 % (the money rule); >= 4 of 5 calendar years positive; Sharpe >= its random reference + 0.5; placebo
  (scores shuffled within each day, 20 runs) percentile >= 95. A candidate BEATS THE DESK only if its Sharpe exceeds the
  deployed comparable: 1.06 for an annual book (value strict), 1.54 for the gated combined book. brok20 is informative only
  (one year of data). ADOPTION: a candidate goes to a PAPER book by the operator's decision; nothing here writes a book.
READ-ONLY on the market tables; writes one row to idx.study. INGEST_DB_DSN=... blackheart-ingest/.venv/Scripts/python research/idx_ml_strategy.py
  (IDX_ML_CACHE=<file.pkl> caches the panel + OOS scores.)
"""
from __future__ import annotations

import os
import pickle
import sys
import time
from datetime import date, datetime

import numpy as np
import pandas as pd
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "blackheart-ingest", "src"))
from blackheart_ingest.idx import research_store as rs  # noqa: E402
from blackheart_ingest.idx.ml import common, daily  # noqa: E402

N_BEFORE = 711
STUDY = "ml_strategy"
TEST_YEARS = [2022, 2023, 2024, 2025, 2026]
LIQ_VALUE, MIN_PRICE = 5e9, 100.0
FEE_BUY, FEE_SELL = 0.0010, 0.0020
K = 10
SEED = 20260924
N_PLACEBO = 20
TARGETS = {"s5": ("fwd_5d", "ret", 5), "s20": ("fwd_20d", "ret", 20), "s250": ("fwd_250d", "ret", 250), "p5": ("fwd_5d", "dir", 5)}
ARMS = ["ml5", "ml5_gate", "ml5_dir", "ml5_k5", "ml20", "ml20_gate", "ml250", "ml250_fund", "combo20", "combo20_gate", "trend_ml", "brok20"]
BAR = {"sharpe": 1.2, "mdd": -0.25, "years_pos": 4, "vs_random": 0.5, "placebo_pct": 95.0}
DEPLOYED = {"annual": 1.06, "combined": 1.54}


def log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


# ---- scores ------------------------------------------------------------------------------------------------------------
def oos_scores(P: pd.DataFrame) -> pd.DataFrame:
    """Walk-forward by year: for each target and test year, fit on purged earlier rows, score the year. -> P with score columns."""
    feats = daily.FEATURES
    P = P.sort_values(["code", "d"]).reset_index(drop=True)
    cal = np.sort(pd.unique(P["d"]))
    year = P["d"].dt.year.to_numpy()
    X = common.to_matrix(P, feats)
    for key, (col, task, h) in TARGETS.items():
        P[key] = np.nan
        for Y in TEST_YEARS:
            start = np.datetime64(date(Y, 1, 1))
            cut = common.purge_cut(cal, start, h)
            fit_m = (P["d"].to_numpy() < cut) & P[col].notna().to_numpy() & (P["liq"].to_numpy())
            if task == "dir":
                fit_m &= (P[col] != 0).to_numpy()
                y = (P[col].to_numpy(float) > 0).astype(float)
            else:
                y = np.clip(P[col].to_numpy(float), -1.0, 1.0)
            test_m = (year == Y)
            if fit_m.sum() < 20000 or test_m.sum() == 0:
                continue
            t0 = time.time()
            bst = common.fit(X[fit_m], y[fit_m], task, common.BASE_PARAMS[task], feats, seed=SEED + Y)
            P.loc[test_m, key] = np.asarray(bst.predict(X[test_m]), dtype=float)
            log(f"score {key} {Y}: fit {int(fit_m.sum()):,} rows (cut {pd.Timestamp(cut).date()}), scored {int(test_m.sum()):,}, {time.time() - t0:.0f} s")
    return P


# ---- the book -------------------------------------------------------------------------------------------------------------
def wide(P: pd.DataFrame, col: str) -> pd.DataFrame:
    return P.pivot(index="d", columns="code", values=col).sort_index()


def costs(close: np.ndarray, offer: np.ndarray, bid: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    tk = np.vectorize(common.tick)(np.nan_to_num(close, nan=1.0))
    c_in = np.where((offer > 0) & (offer >= close), offer / close - 1, tk / close) + FEE_BUY
    c_out = np.where((bid > 0) & (bid <= close), 1 - bid / close, tk / close) + FEE_SELL
    return c_in, c_out


def simulate(A: np.ndarray, mask: np.ndarray, score: np.ndarray, H: int, k: int, c_in: np.ndarray, c_out: np.ndarray,
             gate: np.ndarray | None = None, rng: np.random.Generator | None = None, t_start: int = 0) -> tuple[np.ndarray, int]:
    """Rolling-cohort book: at every close t >= t_start pick k names (top by score, or random within mask), enter at close t+1
    (offer + fee), exit at close t+1+H (bid + fee); slot 1/(k*H) of NAV each. -> daily book returns, number of trades."""
    T, N = A.shape
    ret = np.full((T, N), np.nan)
    ret[1:] = A[1:] / A[:-1] - 1
    ret = np.nan_to_num(ret)
    R = np.zeros(T)
    slot = 1.0 / (k * H)
    n_trades = 0
    for t in range(t_start, T - H - 1):
        if gate is not None and not gate[t]:
            continue
        e, x = t + 1, t + 1 + H
        base = mask[t] & ~np.isnan(A[e]) & ~np.isnan(A[x])
        cand = np.flatnonzero(base)
        if len(cand) == 0:
            continue
        if rng is not None:
            pick = rng.choice(cand, size=min(k, len(cand)), replace=False)
        else:
            sc = np.nan_to_num(score[t, cand], nan=-np.inf)
            ok = np.isfinite(sc) & (sc > -np.inf)
            if ok.sum() == 0:
                continue
            cand, sc = cand[ok], sc[ok]
            pick = cand[np.argsort(-sc, kind="stable")[:k]]
        for j in pick:
            R[e + 1:x + 1] += slot * ret[e + 1:x + 1, j]
            R[e + 1] -= slot * c_in[e, j]
            R[x] -= slot * c_out[x, j]
            n_trades += 1
    return R, n_trades


def stats(R: np.ndarray, dates: pd.DatetimeIndex, t0: int) -> dict:
    r = R[t0:]
    d = dates[t0:]
    eq = np.cumprod(1 + r)
    years = (d[-1] - d[0]).days / 365.25
    cagr = eq[-1] ** (1 / years) - 1 if years > 0 else float("nan")
    sharpe = r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else float("nan")
    dd = eq / np.maximum.accumulate(eq) - 1
    by_year = pd.Series(r, index=d).groupby(d.year).apply(lambda x: float(np.prod(1 + x) - 1))
    return {"cagr": float(cagr), "sharpe": float(sharpe), "mdd": float(dd.min()), "total": float(eq[-1] - 1), "years": years,
            "by_year": {int(y): round(v, 4) for y, v in by_year.items()}, "years_pos": int((by_year > 0).sum()), "n_years": int(len(by_year))}


def rank_mean(*cols: np.ndarray) -> np.ndarray:
    """Cross-sectional percentile rank per day of each column, averaged (NaN-tolerant)."""
    out = np.zeros_like(cols[0], dtype=float)
    cnt = np.zeros_like(cols[0], dtype=float)
    for c in cols:
        r = pd.DataFrame(c).rank(axis=1, pct=True).to_numpy()
        ok = np.isfinite(r)
        out[ok] += r[ok]
        cnt[ok] += 1
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(cnt > 0, out / cnt, np.nan)


# ---- main -----------------------------------------------------------------------------------------------------------------
def main() -> int:
    dsn = os.environ["INGEST_DB_DSN"]
    cache = os.environ.get("IDX_ML_CACHE")
    if cache and os.path.exists(cache):
        P = pickle.load(open(cache, "rb"))
        log(f"panel + scores from cache: {len(P):,} rows")
    else:
        with psycopg.connect(dsn) as conn:
            log("building the daily panel")
            P = daily.build_panel(conn)
        P["value60"] = np.expm1(P["lvalue60"])
        P["liq"] = (P["value60"] >= LIQ_VALUE) & (P["close"] >= MIN_PRICE)
        keep = ["code", "d", "close", "ac", "bid", "offer", "liq", "ret60", "fnet20", "comp_dma200", "profitable", "cfo_pos", "der",
                "volr1", "bf_foreign_buy_share", "bf_hhi_buy", "fwd_5d", "fwd_20d", "fwd_250d"] + daily.FEATURES
        P = P[[c for c in dict.fromkeys(keep) if c in P]].copy()
        log(f"panel {len(P):,} rows, {P['code'].nunique()} names, {P['d'].min().date()} -> {P['d'].max().date()}; scoring walk-forward")
        P = oos_scores(P)
        if cache:
            pickle.dump(P, open(cache, "wb"))
    P = P[P["d"] >= "2021-06-01"].copy()            # a year of run-up for the 250-day arm's first cohorts; the book starts 2022-01
    dates = wide(P, "close").index
    codes = wide(P, "close").columns
    A = wide(P, "ac").reindex(index=dates, columns=codes).to_numpy(float)
    close = wide(P, "close").reindex(index=dates, columns=codes).to_numpy(float)
    offer = wide(P, "offer").reindex(index=dates, columns=codes).to_numpy(float)
    bid = wide(P, "bid").reindex(index=dates, columns=codes).to_numpy(float)
    c_in, c_out = costs(close, offer, bid)
    liq = wide(P, "liq").reindex(index=dates, columns=codes).fillna(False).to_numpy(bool)
    W = {k: wide(P, k).reindex(index=dates, columns=codes).to_numpy(float) for k in ("s5", "s20", "s250", "p5", "ret60", "fnet20", "volr1",
                                                                                     "profitable", "cfo_pos", "der", "bf_foreign_buy_share", "bf_hhi_buy")}
    comp = wide(P, "comp_dma200").reindex(index=dates).max(axis=1).ffill().to_numpy(float)     # one value per day, whichever names have rows
    gate = comp > 0
    hi60 = pd.DataFrame(A).rolling(60, min_periods=40).max().to_numpy()
    ma200 = pd.DataFrame(A).rolling(200, min_periods=120).mean().to_numpy()
    trend = liq & (A >= hi60 - 1e-9) & (A > ma200) & (W["volr1"] >= 1.5)
    fund = liq & (W["profitable"] == 1) & (W["cfo_pos"] == 1) & (W["der"] < 1.5)
    t0 = int(np.searchsorted(dates, np.datetime64(date(2022, 1, 1))))
    t_brok = int(np.searchsorted(dates, np.datetime64(date(2025, 9, 23))))
    combo20 = rank_mean(W["s20"], W["ret60"], W["fnet20"])
    brok20 = rank_mean(W["s20"], W["bf_foreign_buy_share"], 1 - W["bf_hhi_buy"])
    mom = W["ret60"]

    specs = {
        "ml5": (W["s5"], 5, K, liq, None, t0), "ml5_gate": (W["s5"], 5, K, liq, gate, t0), "ml5_dir": (W["p5"], 5, K, liq, None, t0),
        "ml5_k5": (W["s5"], 5, 5, liq, None, t0), "ml20": (W["s20"], 20, K, liq, None, t0), "ml20_gate": (W["s20"], 20, K, liq, gate, t0),
        "ml250": (W["s250"], 250, K, liq, None, t0), "ml250_fund": (W["s250"], 250, K, fund, None, t0),
        "combo20": (combo20, 20, K, liq, None, t0), "combo20_gate": (combo20, 20, K, liq, gate, t0),
        "trend_ml": (W["s20"], 20, K, trend, None, t0), "brok20": (brok20, 20, K, liq, None, t_brok),
    }
    res: dict[str, dict] = {}
    for name, (score, H, k, mask, g, ts) in specs.items():
        R, n = simulate(A, mask, score, H, k, c_in, c_out, gate=g, t_start=ts)
        res[name] = {**stats(R, dates, ts), "H": H, "k": k, "trades": n, "start": str(dates[ts].date())}
        log(f"{name:<13} CAGR {res[name]['cagr'] * 100:6.1f} %  Sharpe {res[name]['sharpe']:5.2f}  mDD {res[name]['mdd'] * 100:6.1f} %  trades {n:,}")
    refs: dict[str, dict] = {}
    for H in (5, 20, 250):
        runs = []
        for s in range(5):
            R, n = simulate(A, liq, None, H, K, c_in, c_out, rng=np.random.default_rng(SEED + s), t_start=t0)
            runs.append(stats(R, dates, t0))
        refs[f"random_H{H}"] = {k: float(np.mean([r[k] for r in runs])) for k in ("cagr", "sharpe", "mdd")}
        log(f"random H{H}: CAGR {refs[f'random_H{H}']['cagr'] * 100:.1f} % Sharpe {refs[f'random_H{H}']['sharpe']:.2f} mDD {refs[f'random_H{H}']['mdd'] * 100:.1f} %")
    R, n = simulate(A, liq, mom, 20, K, c_in, c_out, t_start=t0)
    refs["mom60_H20"] = {**stats(R, dates, t0), "trades": n}
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT trade_date, close FROM idx.index_daily WHERE index_code = 'COMPOSITE' AND trade_date >= '2022-01-01' ORDER BY trade_date")
        ix = pd.DataFrame(cur.fetchall(), columns=["d", "c"])
    ix_r = ix["c"].astype(float).pct_change().fillna(0).to_numpy()
    refs["composite"] = stats(ix_r, pd.DatetimeIndex(pd.to_datetime(ix["d"])), 0)

    # ---- placebo on the best arm by Sharpe (and on the best gated one if different)
    ranked = sorted((a for a in ARMS if a != "brok20"), key=lambda a: -res[a]["sharpe"])
    for name in dict.fromkeys([ranked[0], next((a for a in ranked if a.endswith("_gate")), ranked[0])]):
        score, H, k, mask, g, ts = specs[name]
        rng = np.random.default_rng(SEED)
        pl = []
        for _ in range(N_PLACEBO):
            sh = score.copy()
            for t in range(ts, len(dates)):
                idx = np.flatnonzero(mask[t] & np.isfinite(sh[t]))
                if len(idx) > 1:
                    sh[t, idx] = sh[t, rng.permutation(idx)]
            R, _ = simulate(A, mask, sh, H, k, c_in, c_out, gate=g, t_start=ts)
            pl.append(stats(R, dates, ts)["sharpe"])
        res[name]["placebo"] = {"n": N_PLACEBO, "pct": float((np.array(pl) < res[name]["sharpe"]).mean() * 100), "mean": float(np.mean(pl)),
                                "max": float(np.max(pl))}
        log(f"placebo {name}: real {res[name]['sharpe']:.2f} vs shuffled mean {np.mean(pl):.2f} max {np.max(pl):.2f} -> pct {res[name]['placebo']['pct']:.0f}")

    # ---- verdicts
    for name in ARMS:
        r = res[name]
        rnd = refs[f"random_H{r['H']}"]["sharpe"]
        fails = []
        if not (r["sharpe"] >= BAR["sharpe"]):
            fails.append(f"sharpe {r['sharpe']:.2f} < {BAR['sharpe']}")
        if not (r["mdd"] >= BAR["mdd"]):
            fails.append(f"mdd {r['mdd'] * 100:.0f} % < -25 %")
        if not (r["years_pos"] >= min(BAR["years_pos"], r["n_years"])):
            fails.append(f"{r['years_pos']}/{r['n_years']} years positive")
        if not (r["sharpe"] >= rnd + BAR["vs_random"]):
            fails.append(f"vs random {rnd:.2f} + 0.5")
        if "placebo" in r and r["placebo"]["pct"] < BAR["placebo_pct"]:
            fails.append(f"placebo pct {r['placebo']['pct']:.0f}")
        if name == "brok20":
            r["verdict"] = "informative only (one year of broker flow)" + ("" if not fails else "; " + "; ".join(fails))
        elif fails:
            r["verdict"] = "not a candidate: " + "; ".join(fails)
        else:
            comp_bar = DEPLOYED["annual"] if r["H"] == 250 else DEPLOYED["combined"]
            r["verdict"] = ("CANDIDATE" + (" (placebo pending)" if "placebo" not in r else "") +
                            (f", beats the deployed comparable {comp_bar}" if r["sharpe"] > comp_bar else f", below the deployed comparable {comp_bar}"))
    best = max(ARMS, key=lambda a: res[a]["sharpe"] if a != "brok20" else -9)
    n_trials = N_BEFORE + len(ARMS)

    # ---- report
    L = [f"# IDX menu ML-4 — strategies on the prediction desk's models — {date.today()} — {len(ARMS)} trials, cumulative N = {n_trials}", "",
         "Walk-forward scores by test year (fit on purged earlier rows), LIQ universe (60-day value >= Rp 5 bn, close >= Rp 100), closing "
         "offer/bid + Stockbit fees, rolling cohorts of K names held H days (slot 1/(K*H)). Book 2022-01 -> " + str(dates[-1].date()) + ".", "",
         "| arm | H | K | trades | CAGR | Sharpe | mDD | years + | by year | placebo pct | verdict |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for name in ARMS:
        r = res[name]
        by = " ".join(f"{str(y)[2:]}:{v * 100:+.0f}" for y, v in r["by_year"].items())
        pl = f"{r['placebo']['pct']:.0f}" if "placebo" in r else "-"
        L.append(f"| {name} | {r['H']} | {r['k']} | {r['trades']:,} | {r['cagr'] * 100:+.1f} % | {r['sharpe']:.2f} | {r['mdd'] * 100:.0f} % | "
                 f"{r['years_pos']}/{r['n_years']} | {by} | {pl} | {r['verdict']} |")
    L += ["", "| reference | CAGR | Sharpe | mDD |", "|---|---|---|---|"]
    for name, r in refs.items():
        L.append(f"| {name} | {r['cagr'] * 100:+.1f} % | {r['sharpe']:.2f} | {r['mdd'] * 100:.0f} % |")
    L += ["", f"Deployed comparables (ROI scorecard #{'roi_scorecard'}): value strict annual 21.8 % / 1.06 / -23 %; trend small + gate 32.1 % / 1.54 / -18 %; "
          "value 50 / trend 50 gated 27.7 % / 1.54 / -15 %.", "",
          "## Verdict (menu ML-4, study stored)", "",
          f"Best arm by Sharpe: **{best}** ({res[best]['cagr'] * 100:+.1f} %/yr, Sharpe {res[best]['sharpe']:.2f}, mDD {res[best]['mdd'] * 100:.0f} %) - {res[best]['verdict']}.",
          f"Candidates: {', '.join(a for a in ARMS if res[a]['verdict'].startswith('CANDIDATE')) or 'none'}."]
    text = "\n".join(L)
    out = os.path.join(HERE, f"IDX_ML_STRATEGY_{date.today()}.md")
    open(out, "w", encoding="utf-8").write(text + "\n")
    print(text)
    with psycopg.connect(dsn) as conn:
        sid = rs.record_study(conn, STUDY, dates[-1].date(), params={"trials": ARMS, "n_trials_cumulative": n_trials, "bar": BAR, "targets": TARGETS,
                                                                       "universe": {"value60": LIQ_VALUE, "min_price": MIN_PRICE}, "fees": [FEE_BUY, FEE_SELL],
                                                                       "test_years": TEST_YEARS, "seed": SEED},
                              summary={"arms": common.plain(res), "refs": common.plain(refs), "best": best}, names=[])
        conn.commit()
    log(f"study #{sid} stored; report {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
