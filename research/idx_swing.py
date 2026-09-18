#!/usr/bin/env python3
"""IDX — can a 2–5 day swing rule survive real costs? (operator question 2026-09-17: "trading 2–3 hari atau mingguan").

PRE-REGISTERED MENU (22 trials; cumulative 196 + 22 = 218). Declared before the run; nothing tuned afterwards.
  Universe each day: board Utama/Pengembangan (current listing board — not point-in-time, a known limit), 60-day median
  traded value >= Rp 5 bn, raw close >= Rp 100, volume > 0. Signals at the close of day t; ENTRY at the CLOSE of t+1 (the
  operator works the order the next day; opens exist for the whole universe only from 2025, so close-to-close is the
  honest model over 2020–2026); EXIT at the close of t+1+H. No stops, no re-entry while held. Up to K = 5 names per day,
  equal slots, capital split in H tranches (a name held H days uses 1/(K·H) of the book).
  Costs per trade: Stockbit fee 0.10 % buy + 0.20 % sell, plus one IDX price fraction (tick) against on each side
  (Rp 1/2/5/10/25 by price band) — the price of a limit that actually fills. Dividends ignored (holding days are few).
  Arms (H in {2, 3, 5} unless stated):
    mr3_5 / mr3_7 / mr3_10   3-day return <= -5 / -7 / -10 %, ranked by most negative                       (9 trials)
    fflow_10 / fflow_20      5-day foreign net share >= 10 % / 20 % of volume and 5-day return > 0, ranked by share (6)
    brk20                    close = 20-day high and volume >= 2x 20-day median volume, ranked by volume ratio    (3)
    exdiv_runup              buy at the close 3 trading days before the ex-date, sell at the cum-date close (H=2)  (1)
    exdiv_after              buy at the ex-date close, sell 5 days later                                        (1)
    pead_5 / pead_10         quarterly net profit up >= 30 % y/y, entry the close after publication, H = 5 / 10 (2)
  References (not trials): random_K — five random universe names each day with the same H and costs (the cost drag);
    composite — buy and hold the COMPOSITE index.
READING RULE (declared before the run): an arm is a candidate only if ALL hold after costs: >= 300 trades; the mean net
  return per basket-day > 0 with t-stat >= 2.5 on the daily basket series (names on one day are one observation); net
  portfolio return positive in at least 5 of the 7 calendar years 2020–2026; annualised Sharpe >= 1.0; max drawdown
  <= 25 %; Sharpe at least 0.5 above random_K at the same H. A candidate then goes to a paper book for >= 60 trades
  before any real money. Anything else is recorded as tested — no edge after costs.
READ-ONLY. INGEST_DB_DSN=... blackheart-ingest/.venv/Scripts/python research/idx_swing.py [--out research/IDX_SWING_<date>.md]
"""
from __future__ import annotations

import argparse
import math
import os
import sys
from datetime import date

import numpy as np
import pandas as pd
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blackheart-ingest", "src"))
import equity_screen as ES  # noqa: E402

START, END = date(2020, 1, 1), date(2026, 9, 16)
FEE_BUY, FEE_SELL = 0.0010, 0.0020                 # Stockbit
K = 5
HOLDS = (2, 3, 5)
LIQ, MIN_PRICE = 5e9, 100
N_TRIALS_BEFORE = 196
TRIALS = ([f"mr3_{x}|{h}" for x in (5, 7, 10) for h in HOLDS] + [f"fflow_{x}|{h}" for x in (10, 20) for h in HOLDS]
          + [f"brk20|{h}" for h in HOLDS] + ["exdiv_runup|2", "exdiv_after|5", "pead|5", "pead|10"])
assert len(TRIALS) == 22
SEED = 20260917


def tick(p: np.ndarray) -> np.ndarray:
    return np.select([p < 200, p < 500, p < 2000, p < 5000], [1, 2, 5, 10], 25).astype(float)


def load(conn):
    bars = pd.read_sql("""SELECT b.code, b.trade_date, b.close, b.adj_factor, b.volume, f.foreign_net_share_5d AS f5, f.value_60d_median AS v60
                            FROM idx.bar b LEFT JOIN idx.feature_daily f USING (code, trade_date)
                           WHERE b.source = 'idx' AND b.trade_date BETWEEN %s AND %s""", conn, params=(START, END))
    listing = pd.read_sql("SELECT code, board, sector FROM idx.listing", conn)
    idx = pd.read_sql("SELECT trade_date, close FROM idx.index_daily WHERE index_code = 'COMPOSITE' AND trade_date BETWEEN %s AND %s ORDER BY 1",
                      conn, params=(START, END))
    divs = pd.read_sql("SELECT code, ex_date FROM idx.dividend WHERE kind = 'cash' AND ex_date BETWEEN %s AND %s", conn, params=(START, END))
    pead = pd.read_sql("""
        WITH f AS (SELECT code, period_end, net_profit, published_at::date AS pub FROM idx.fundamental WHERE published_at IS NOT NULL)
        SELECT a.code, a.pub, a.net_profit, b.net_profit AS prior
          FROM f a JOIN f b ON b.code = a.code AND b.period_end = a.period_end - interval '1 year'
         WHERE a.pub BETWEEN %s AND %s""", conn, params=(START, END))
    return bars, listing, idx, divs, pead


def panels(bars: pd.DataFrame, listing: pd.DataFrame):
    bars = bars.copy()
    for c in ("close", "adj_factor", "volume", "f5", "v60"):
        bars[c] = pd.to_numeric(bars[c], errors="coerce")
    bars["adj"] = bars["close"] * bars["adj_factor"].fillna(1.0)
    ok_board = set(listing.loc[listing["board"].isin(["Utama", "Pengembangan"]), "code"])
    bars = bars[bars["code"].isin(ok_board)]
    P = {c: bars.pivot(index="trade_date", columns="code", values=c) for c in ("adj", "close", "volume", "f5", "v60")}
    return P


def signals(P: dict[str, pd.DataFrame], divs: pd.DataFrame, pead: pd.DataFrame) -> dict[str, tuple[pd.DataFrame, pd.DataFrame]]:
    """name -> (mask, rank_score) both dates x codes; higher score = picked first."""
    adj, close, vol = P["adj"], P["close"], P["volume"]
    dates = adj.index
    uni = (P["v60"] >= LIQ) & (close >= MIN_PRICE) & (vol > 0) & adj.notna()
    r3 = adj / adj.shift(3) - 1
    r5 = adj / adj.shift(5) - 1
    out = {}
    for x in (5, 7, 10):
        m = uni & (r3 <= -x / 100)
        out[f"mr3_{x}"] = (m, -r3)
    for x in (10, 20):
        m = uni & (P["f5"] >= x / 100) & (r5 > 0)
        out[f"fflow_{x}"] = (m, P["f5"])
    hi20 = adj.rolling(20, min_periods=20).max()
    vmed = vol.rolling(20, min_periods=20).median()
    vr = vol / vmed
    out["brk20"] = (uni & (adj >= hi20) & (vr >= 2), vr)
    # dividends: ex-date -> trading-day positions
    pos = {d: i for i, d in enumerate(dates)}
    runup = pd.DataFrame(False, index=dates, columns=adj.columns)
    after = pd.DataFrame(False, index=dates, columns=adj.columns)
    for code, ex in divs.itertuples(index=False):
        if code not in adj.columns:
            continue
        i = dates.searchsorted(pd.Timestamp(ex))
        if i >= len(dates):
            continue
        if dates[i].date() != ex:                      # ex-date not a bar day in our data: skip
            continue
        if i - 4 >= 0:
            runup.iat[i - 4, runup.columns.get_loc(code)] = True   # signal t = ex-4 -> entry close t+1 = ex-3, exit H=2 -> ex-1 (cum date)
        after.iat[i - 1, after.columns.get_loc(code)] = True        # signal t = ex-1 -> entry at the ex-date close
    out["exdiv_runup"] = (uni & runup, close * 0 + 1)
    out["exdiv_after"] = (uni & after, close * 0 + 1)
    pm = pd.DataFrame(False, index=dates, columns=adj.columns)
    pead = pead.copy()
    pead["net_profit"] = pd.to_numeric(pead["net_profit"], errors="coerce")
    pead["prior"] = pd.to_numeric(pead["prior"], errors="coerce")
    grow = pead[(pead["prior"] > 0) & (pead["net_profit"] >= 1.3 * pead["prior"])]
    for code, pub in grow[["code", "pub"]].itertuples(index=False):
        if code not in adj.columns:
            continue
        i = dates.searchsorted(pd.Timestamp(pub))
        if i < len(dates):
            pm.iat[i, pm.columns.get_loc(code)] = True              # signal on the publication day (or next bar) -> entry next close
    out["pead"] = (uni & pm, close * 0 + 1)
    return out, uni


def simulate(adj: pd.DataFrame, close: pd.DataFrame, mask: pd.DataFrame, score: pd.DataFrame, H: int, k: int = K,
             rng: np.random.Generator | None = None, uni: pd.DataFrame | None = None):
    """Overlapping-tranche portfolio: on each signal day t pick up to k names (by score, or at random from uni when rng is
    given), enter at close t+1, exit at close t+1+H, weight 1/(k*H) each. Returns daily portfolio returns and trade stats."""
    A = adj.to_numpy(dtype=float)
    C = close.to_numpy(dtype=float)
    M = mask.to_numpy(dtype=bool)
    S = score.to_numpy(dtype=float)
    T, N = A.shape
    W = np.zeros((T, N))                                       # weight during day d (return d-1 -> d)
    cost_day = np.zeros(T)                                     # costs charged on day d (fractions of the book)
    ret = np.full((T, N), np.nan)
    ret[1:] = A[1:] / A[:-1] - 1
    slot = 1.0 / (k * H)
    trades = []                                                # (entry_date_idx, code_idx, net_return)
    U = uni.to_numpy(dtype=bool) if uni is not None else None
    for t in range(T - H - 1):
        e, x = t + 1, t + 1 + H                                # entry close, exit close
        if rng is not None:
            cand = np.flatnonzero(U[t] & ~np.isnan(A[e]) & ~np.isnan(A[x]))
            if len(cand) == 0:
                continue
            pick = rng.choice(cand, size=min(k, len(cand)), replace=False)
        else:
            cand = np.flatnonzero(M[t] & ~np.isnan(A[e]) & ~np.isnan(A[x]))
            if len(cand) == 0:
                continue
            pick = cand[np.argsort(-S[t, cand], kind="stable")[:k]]
        for j in pick:
            pe, px = C[e, j], C[x, j]
            if not (pe > 0 and px > 0):
                continue
            c_in = FEE_BUY + tick(np.array([pe]))[0] / pe
            c_out = FEE_SELL + tick(np.array([px]))[0] / px
            W[e + 1:x + 1, j] += slot
            cost_day[e] += slot * c_in
            cost_day[x] += slot * c_out
            gross = A[x, j] / A[e, j] - 1
            trades.append((e, j, gross - c_in - c_out))
    R = np.nansum(W * np.nan_to_num(ret), axis=1) - cost_day
    return pd.Series(R, index=adj.index), trades, W.sum(axis=1)


def stats(R: pd.Series, trades: list, exposure: np.ndarray, n_trials: int, idx_close: pd.Series | None = None):
    eq = (1 + R).cumprod()
    years = R.groupby(R.index.year).apply(lambda s: (1 + s).prod() - 1)
    ann = R.mean() * 250
    vol = R.std() * math.sqrt(250)
    sharpe = ann / vol if vol > 0 else 0.0
    dd = (eq / eq.cummax() - 1).min()
    n = len(trades)
    nets = np.array([tr[2] for tr in trades]) if n else np.array([])
    # daily basket series: mean net return of the names entered on the same day
    by_day: dict[int, list[float]] = {}
    for e, _, r in trades:
        by_day.setdefault(e, []).append(r)
    bd = np.array([np.mean(v) for v in by_day.values()]) if by_day else np.array([])
    tstat = (bd.mean() / bd.std(ddof=1) * math.sqrt(len(bd))) if len(bd) > 2 and bd.std(ddof=1) > 0 else 0.0
    dsr = ES.deflated_sharpe(list(R[R != 0].values), n_trials) if (R != 0).sum() > 10 else 0.0
    return {"n_trades": n, "n_days": len(bd), "hit": float((nets > 0).mean()) if n else 0.0, "avg_net": float(nets.mean()) if n else 0.0,
            "med_net": float(np.median(nets)) if n else 0.0, "tstat": float(tstat), "total": float(eq.iloc[-1] - 1), "cagr": float(eq.iloc[-1] ** (250 / len(R)) - 1),
            "sharpe": float(sharpe), "mdd": float(dd), "dsr": float(dsr), "exposure": float(exposure.mean()),
            "years": {int(y): float(v) for y, v in years.items()}}


def passes(s: dict, rnd: dict) -> tuple[bool, list[str]]:
    why = []
    if s["n_trades"] < 300:
        why.append("n<300")
    if not (s["avg_net"] > 0 and s["tstat"] >= 2.5):
        why.append("t<2.5")
    if sum(1 for v in s["years"].values() if v > 0) < 5:
        why.append("years<5/7")
    if s["sharpe"] < 1.0:
        why.append("sharpe<1")
    if s["mdd"] < -0.25:
        why.append("mdd>25%")
    if s["sharpe"] < rnd["sharpe"] + 0.5:
        why.append("not>random+0.5")
    return not why, why


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, f"IDX_SWING_{date.today().isoformat()}.md"))
    ap.add_argument("--no-store", action="store_true")
    a = ap.parse_args()
    dsn = os.environ["INGEST_DB_DSN"]
    with psycopg.connect(dsn) as conn:
        bars, listing, idx, divs, pead = load(conn)
    P = panels(bars, listing)
    P = {k: v.sort_index() for k, v in P.items()}
    for k in P:
        P[k].index = pd.to_datetime(P[k].index)
    sig, uni = signals(P, divs, pead)
    adj, close = P["adj"], P["close"]
    n_trials = N_TRIALS_BEFORE + len(TRIALS)
    rng = np.random.default_rng(SEED)
    results: dict[str, dict] = {}
    random_ref: dict[int, dict] = {}
    for H in sorted(set(int(t.split("|")[1]) for t in TRIALS)):
        R, tr, ex = simulate(adj, close, uni, close * 0, H, rng=rng, uni=uni)
        random_ref[H] = stats(R, tr, ex, n_trials)
    for t in TRIALS:
        name, H = t.split("|")
        H = int(H)
        m, s = sig[name]
        R, tr, ex = simulate(adj, close, m, s, H)
        results[t] = stats(R, tr, ex, n_trials)
    idx["trade_date"] = pd.to_datetime(idx["trade_date"])
    ic = idx.set_index("trade_date")["close"].astype(float)
    ic = ic[(ic.index >= adj.index[0]) & (ic.index <= adj.index[-1])]
    comp_years = ic.groupby(ic.index.year).apply(lambda s: s.iloc[-1] / s.iloc[0] - 1)
    comp_total = ic.iloc[-1] / ic.iloc[0] - 1

    def yrs(d):
        return " ".join(f"{y % 100:02d}:{v * 100:+.0f}" for y, v in sorted(d.items()))
    lines = [f"# IDX swing menu — {date.today()} — {len(TRIALS)} trials, cumulative N = {n_trials}", "",
             f"Universe: Utama/Pengembangan, v60 >= Rp {LIQ / 1e9:.0f} bn, close >= Rp {MIN_PRICE}; entry close t+1, exit close t+1+H; K = {K}; "
             f"costs Stockbit {FEE_BUY * 100:.2f} % / {FEE_SELL * 100:.2f} % + 1 tick each side. {adj.index[0].date()} -> {adj.index[-1].date()}, "
             f"{adj.shape[1]} names, {len(adj)} days.", "",
             f"COMPOSITE buy-and-hold: {comp_total * 100:+.1f} % | {yrs(comp_years.to_dict())}", "",
             "| arm | H | trades | days | hit | avg net/trade | median | t(basket) | total | CAGR | Sharpe | mDD | DSR | expo | years | verdict |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    verdicts = {}
    for H, s in random_ref.items():
        lines.append(f"| random_K | {H} | {s['n_trades']} | {s['n_days']} | {s['hit'] * 100:.0f} % | {s['avg_net'] * 100:+.2f} % | {s['med_net'] * 100:+.2f} % | "
                     f"{s['tstat']:.1f} | {s['total'] * 100:+.0f} % | {s['cagr'] * 100:+.1f} % | {s['sharpe']:.2f} | {s['mdd'] * 100:.0f} % | - | "
                     f"{s['exposure'] * 100:.0f} % | {yrs(s['years'])} | reference |")
    for t in TRIALS:
        name, H = t.split("|")
        s = results[t]
        ok, why = passes(s, random_ref[int(H)])
        verdicts[t] = "CANDIDATE" if ok else "tested: " + ",".join(why)
        lines.append(f"| {name} | {H} | {s['n_trades']} | {s['n_days']} | {s['hit'] * 100:.0f} % | {s['avg_net'] * 100:+.2f} % | {s['med_net'] * 100:+.2f} % | "
                     f"{s['tstat']:.1f} | {s['total'] * 100:+.0f} % | {s['cagr'] * 100:+.1f} % | {s['sharpe']:.2f} | {s['mdd'] * 100:.0f} % | {s['dsr']:.2f} | "
                     f"{s['exposure'] * 100:.0f} % | {yrs(s['years'])} | {verdicts[t]} |")
    n_cand = sum(1 for v in verdicts.values() if v == "CANDIDATE")
    lines += ["", f"Reading rule applied as declared: {n_cand} candidate(s) of {len(TRIALS)}.", "",
              "Limits: current listing board (not PIT); close-to-close execution (one day late vs the signal; opens only from 2025);",
              "no quality gate on the universe beyond liquidity; dividends ignored inside a holding; costs are the minimum a filled",
              "limit pays (fee + one tick each side), no extra slippage. A CANDIDATE here is a paper-book candidate, not a rule."]
    text = "\n".join(lines)
    print(text)
    with open(a.out, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    print(f"\nwrote {a.out}")
    if not a.no_store:
        from blackheart_ingest.idx import research_store as rs
        with psycopg.connect(dsn) as conn:
            best = max(TRIALS, key=lambda t: results[t]["sharpe"])
            sid = rs.record_study(conn, "swing", adj.index[-1].date(),
                                  params={"trials": TRIALS, "n_trials_cumulative": n_trials, "fees": [FEE_BUY, FEE_SELL], "K": K, "liq": LIQ,
                                          "min_price": MIN_PRICE, "execution": "close t+1 -> close t+1+H", "reading_rule": "see script docstring"},
                                  summary={"results": results, "random": random_ref, "verdicts": verdicts, "composite_total": float(comp_total),
                                           "best_by_sharpe": best, "candidates": n_cand},
                                  names=[], report_path=a.out, note=f"{n_cand} candidates of {len(TRIALS)}; best by Sharpe {best}")
            print(f"study #{sid} stored")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
