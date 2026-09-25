#!/usr/bin/env python3
"""IDX menu ML-9 - the ML book in rupiah: Rp 20 M, Rp 1 M per trade (operator, 2026-09-25: "backtest dari 2020 strategi trading kita
dengan ml kita total modal 20 juta 1 trade alokasi 1 juta").

Strategy = the cost-aware ML book with the up-confirmation entry (studies #154, #160): the desk's walk-forward 5d score, a name is
signalled when its expected 5-day excess pays 2x its round-trip cost, bought only after its close is >= 105 % of the signal close
within 10 days, sold when the score turns negative and a better name pays the swap, or after 61 days. Universe LIQ.
Money: Rp 20,000,000 start; every trade buys as many LOTS (100 shares) as Rp 1,000,000 affords at the closing offer (names dearer
than Rp 10,000 cannot be bought with one lot and are skipped); at most 20 open positions; fees 0.10 % / 0.20 %; cash earns 0.
The alternative sizing 5 % of NAV per trade is reported next to it (compounding).
Window: 2021-01 -> end. 2020 cannot be scored: the IDX data starts 2020-01 and the 2021 model is fitted on 2020 alone (purged).
Descriptive: the sizing changes nothing about the signal; 2 sizing variants are recorded as trials (cumulative 804 + 2 = 806).
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
from blackheart_ingest.idx.ml import common, daily  # noqa: E402

N_BEFORE = 804
STUDY = "ml_rupiah"
START = date(2021, 1, 1)
CAPITAL, PER_TRADE, MAX_POS = 20_000_000.0, 1_000_000.0, 20
FEE_BUY, FEE_SELL = 0.0010, 0.0020
LOT = 100
WAIT = (0.05, 10)
MARGIN, SPAN, MAX_HOLD = 2.0, 3, 60


def add_2021_scores(P: pd.DataFrame) -> pd.DataFrame:
    if P.loc[P["d"].dt.year == 2021, "s5"].notna().any():
        return P
    P = P.sort_values(["code", "d"]).reset_index(drop=True)
    cal = np.sort(pd.unique(P["d"]))
    cut = common.purge_cut(cal, np.datetime64(date(2021, 1, 1)), 5)
    y = np.clip(P["fwd_5d"].to_numpy(float), -1.0, 1.0)
    fit_m = (P["d"].to_numpy() < cut) & np.isfinite(y) & P["liq"].to_numpy()
    X = common.to_matrix(P, daily.FEATURES)
    bst = common.fit(X[fit_m], y[fit_m], "ret", common.BASE_PARAMS["ret"], daily.FEATURES, seed=M.SEED + 2021)
    test_m = (P["d"].dt.year == 2021).to_numpy()
    P.loc[test_m, "s5"] = np.asarray(bst.predict(X[test_m]), dtype=float)
    M.log(f"2021 scored from {int(fit_m.sum()):,} rows of 2020 (cut {pd.Timestamp(cut).date()})")
    return P


def simulate(A, raw, offer, bid, mask, e, dates, t0, per_trade=None, pct_nav=None):
    """Rupiah book with lots. A = adjusted close (signals, returns), raw/offer/bid = nominal prices for lot sizing and fills.
    Position value follows the adjusted return (splits handled), cash in rupiah."""
    T, N = A.shape
    cash = CAPITAL
    held: dict[int, dict] = {}
    watch: dict[int, dict] = {}
    pend_sell: list[tuple[int, str]] = []
    pend_buy: list[int] = []
    nav = np.zeros(T)
    trades = []
    skipped_price = 0
    rt = (np.where((offer > 0) & (offer >= raw), offer / raw - 1, 0.005) + FEE_BUY) + (np.where((bid > 0) & (bid <= raw), 1 - bid / raw, 0.005) + FEE_SELL)
    for t in range(t0, T - 1):
        for j, why in pend_sell:
            if j in held:
                p = held.pop(j)
                px = bid[t, j] if bid[t, j] > 0 and bid[t, j] <= raw[t, j] else raw[t, j] - common.tick(raw[t, j])
                value = p["units"] * (A[t, j] / p["a_in"]) * (px / raw[t, j])           # units in adjusted terms x nominal price ratio
                proceeds = value * (1 - FEE_SELL)
                cash += proceeds
                trades.append({"code": j, "t_in": p["t"], "t_out": t, "why": why, "cost_rp": p["cost"], "proceeds_rp": proceeds, "pnl_rp": proceeds - p["cost"],
                               "net": proceeds / p["cost"] - 1, "hold": t - p["t"]})
        for j in pend_buy:
            if j in held or len(held) >= MAX_POS or np.isnan(A[t, j]):
                continue
            budget = per_trade if per_trade else pct_nav * nav[t - 1] if t > 0 else per_trade
            px = offer[t, j] if offer[t, j] > 0 and offer[t, j] >= raw[t, j] else raw[t, j] + common.tick(raw[t, j])
            lots = int(budget // (px * LOT))
            if lots < 1:
                skipped_price += 1
                continue
            cost = lots * LOT * px * (1 + FEE_BUY)
            if cost > cash:
                continue
            cash -= cost
            held[j] = {"t": t, "a_in": A[t, j], "units": lots * LOT * raw[t, j], "cost": cost, "peak": A[t, j]}    # units = nominal value at fill close
        pend_sell, pend_buy = [], []
        mv = sum(p["units"] * (A[t, j] / p["a_in"]) for j, p in held.items() if not np.isnan(A[t, j]))
        nav[t] = cash + mv
        ok = mask[t] & np.isfinite(e[t]) & ~np.isnan(A[t]) & ~np.isnan(A[t + 1])
        cand = np.flatnonzero(ok)
        order = cand[np.argsort(-e[t, cand], kind="stable")] if len(cand) else cand
        best = float(e[t, order[0]]) if len(order) else -np.inf
        for j, p in held.items():
            if (t - p["t"]) >= MAX_HOLD:
                pend_sell.append((j, "max_hold"))
            elif np.isnan(A[t + 1, j]) or not np.isfinite(e[t, j]):
                pend_sell.append((j, "gone"))
            elif e[t, j] < 0 and best - e[t, j] > MARGIN * rt[t, j]:
                pend_sell.append((j, "swap"))
        for j in list(watch):
            v = watch[j]
            if t > v["until"] or j in held:
                watch.pop(j)
                continue
            if ok[j] and e[t, j] > MARGIN * rt[t, j] and A[t, j] >= (1 + WAIT[0]) * v["ref"]:
                pend_buy.append(j)
                watch.pop(j)
        free = MAX_POS - (len(held) - len(pend_sell)) - len(pend_buy) - len(watch)
        for j in order:
            if free <= 0:
                break
            if j in held or any(j == s for s, _ in pend_sell) or j in watch or j in pend_buy:
                continue
            if e[t, j] > MARGIN * rt[t, j] and raw[t, j] * LOT <= (per_trade or CAPITAL * pct_nav):
                watch[j] = {"t": t, "ref": A[t, j], "until": t + WAIT[1]}
                free -= 1
    nav[T - 1] = nav[T - 2]
    return pd.Series(nav[t0:], index=dates[t0:]), pd.DataFrame(trades), skipped_price


def stats(nav: pd.Series) -> dict:
    r = nav.pct_change().fillna(0.0)
    yrs = (nav.index[-1] - nav.index[0]).days / 365.25
    eq = nav / nav.iloc[0]
    dd = eq / eq.cummax() - 1
    by = nav.groupby(nav.index.year).agg(["first", "last"])
    return {"final": float(nav.iloc[-1]), "total": float(eq.iloc[-1] - 1), "cagr": float(eq.iloc[-1] ** (1 / yrs) - 1), "sharpe": float(r.mean() / r.std() * np.sqrt(252)) if r.std() > 0 else float("nan"),
            "mdd": float(dd.min()), "mdd_rp": float((nav - nav.cummax()).min()), "by_year": {int(y): float(v["last"] / v["first"] - 1) for y, v in by.iterrows()},
            "nav_year_end": {int(y): float(v["last"]) for y, v in by.iterrows()}}


def main() -> int:
    dsn = os.environ["INGEST_DB_DSN"]
    P = pickle.load(open(os.environ["IDX_ML_CACHE"], "rb"))
    P = add_2021_scores(P)
    pickle.dump(P, open(os.environ["IDX_ML_CACHE"], "wb"))
    P = P[P["d"] >= "2020-06-01"].copy()
    dates = M.wide(P, "close").index
    codes = M.wide(P, "close").columns
    g = lambda c: M.wide(P, c).reindex(index=dates, columns=codes)  # noqa: E731
    A, raw = g("ac").to_numpy(float), g("close").to_numpy(float)
    offer, bid = np.nan_to_num(g("offer").to_numpy(float)), np.nan_to_num(g("bid").to_numpy(float))
    liq = g("liq").fillna(False).astype(bool).to_numpy()
    S = g("s5").to_numpy(float)
    e5 = C.ema(S - np.nanmedian(np.where(liq, S, np.nan), axis=1, keepdims=True), SPAN)
    t0 = int(np.searchsorted(dates, np.datetime64(START)))
    res = {}
    for name, kw in {"rp1m_fixed": dict(per_trade=PER_TRADE), "pct5_nav": dict(pct_nav=0.05)}.items():
        nav, tr, skipped = simulate(A, raw, offer, bid, liq, e5, dates, t0, **kw)
        st = stats(nav)
        w = tr[tr["pnl_rp"] > 0]
        util = float(1 - (nav.to_numpy() * 0 + 1).mean()) if False else None
        st.update({"trades": len(tr), "win": float((tr["pnl_rp"] > 0).mean()), "avg_pnl_rp": float(tr["pnl_rp"].mean()), "avg_net": float(tr["net"].mean()),
                   "best_rp": float(tr["pnl_rp"].max()), "worst_rp": float(tr["pnl_rp"].min()), "sum_win_rp": float(w["pnl_rp"].sum()), "sum_loss_rp": float(tr.loc[tr["pnl_rp"] <= 0, "pnl_rp"].sum()),
                   "fees_rp": float((tr["cost_rp"] * FEE_BUY / (1 + FEE_BUY) + tr["proceeds_rp"] * FEE_SELL / (1 - FEE_SELL)).sum()), "skipped_price": skipped,
                   "hold": float(tr["hold"].mean()), "by_reason": {k: {"n": int(v["size"]), "avg_rp": float(v["mean"])} for k, v in tr.groupby("why")["pnl_rp"].agg(["size", "mean"]).iterrows()},
                   "trades_by_year": {int(y): int(n) for y, n in tr.assign(y=dates[tr["t_in"]].year).groupby("y").size().items()}})
        res[name] = st
        tr.assign(code=codes[tr["code"]], d_in=dates[tr["t_in"]], d_out=dates[tr["t_out"]]).to_csv(os.path.join(os.path.dirname(HERE), "research-scratch", f"ml_rupiah_{name}.csv"), index=False)
        M.log(f"{name}: final Rp {st['final']:,.0f} total {st['total'] * 100:+.0f} % CAGR {st['cagr'] * 100:.1f} % Sharpe {st['sharpe']:.2f} mDD {st['mdd'] * 100:.0f} % (Rp {st['mdd_rp']:,.0f}) | "
              f"trades {len(tr)} win {st['win'] * 100:.0f} % avg Rp {st['avg_pnl_rp']:,.0f} best Rp {st['best_rp']:,.0f} worst Rp {st['worst_rp']:,.0f} fees Rp {st['fees_rp']:,.0f} skipped(price) {skipped} | "
              + " ".join(f"{y}: Rp {v:,.0f} ({st['by_year'][y] * 100:+.0f} %)" for y, v in st["nav_year_end"].items()))
    n_trials = N_BEFORE + 2
    L = [f"# IDX menu ML-9 - the ML book in rupiah, Rp 20 M with Rp 1 M per trade - {date.today()} - cumulative N = {n_trials}", "",
         "Strategy: cost-aware 5d score + up-confirmation (+5 % in 10 d), LIQ, max 20 positions, lots of 100, closing offer/bid + Stockbit fees, cash earns 0. "
         "From 2021-01 (2020 has no trainable history; the 2021 model is fitted on 2020 alone).", "",
         "| sizing | final NAV | total | CAGR | Sharpe | mDD | mDD Rp | trades | win | avg P&L/trade | best | worst | fees | skipped (price > budget) |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, st in res.items():
        L.append(f"| {name} | Rp {st['final']:,.0f} | {st['total'] * 100:+.0f} % | {st['cagr'] * 100:.1f} % | {st['sharpe']:.2f} | {st['mdd'] * 100:.0f} % | Rp {st['mdd_rp']:,.0f} | {st['trades']} | "
                 f"{st['win'] * 100:.0f} % | Rp {st['avg_pnl_rp']:,.0f} | Rp {st['best_rp']:,.0f} | Rp {st['worst_rp']:,.0f} | Rp {st['fees_rp']:,.0f} | {st['skipped_price']} |")
    L += ["", "| sizing | " + " | ".join(str(y) for y in res["rp1m_fixed"]["nav_year_end"]) + " |", "|---|" + "---|" * len(res["rp1m_fixed"]["nav_year_end"])]
    for name, st in res.items():
        L.append(f"| {name} NAV year end | " + " | ".join(f"Rp {v:,.0f} ({st['by_year'][y] * 100:+.0f} %)" for y, v in st["nav_year_end"].items()) + " |")
    text = "\n".join(L)
    out = os.path.join(HERE, f"IDX_ML_RUPIAH_{date.today()}.md")
    open(out, "w", encoding="utf-8").write(text + "\n")
    print(text)
    with psycopg.connect(dsn) as conn:
        sid = rs.record_study(conn, STUDY, date.today(), params={"trials": list(res), "n_trials_cumulative": n_trials, "capital": CAPITAL, "per_trade": PER_TRADE, "max_pos": MAX_POS, "start": str(START)},
                              summary=common.plain(res), names=[], report_path=out)
        conn.commit()
    M.log(f"study #{sid} stored")
    return 0


if __name__ == "__main__":
    sys.exit(main())
