#!/usr/bin/env python3
"""IDX menu ML-10 - the top-3 strategies on one Rp 20 M book, 5 % of NAV per trade (operator, 2026-09-25: "20 juta itu buat 5
persen alokasiin per trade tapi ada 3 aktif strategi yang top 1,2,3").

One cash pool, one position cap (20), lots of 100, every trade sized at 5 % of the NAV at the moment it is placed:
  gap-fade   the deployed rule (open <= -7 % vs the prior close, main board, 60-day value >= Rp 5 bn, up to 5 a day, deepest
             liquidity first): bought at the open + 1 tick, sold at the close - 1 tick the same day, fees 0.10 / 0.20 %
  trend      the deployed trend book (small universe, 60-day high / > MA200 / volume >= 1.5x, trail-10 exit, regime gate): its
             own K-10 simulator decides the trades; here they are replayed at 5 % of NAV each, entry at the closing offer, exit
             at the closing bid
  ML         the cost-aware 5d score with the +5 % confirmation (K-10 simulator decides the trades; replayed the same way)
Morning gap-fade trades take slots first (they are placed at the open), then at the close exits, then trend entries, then ML
entries; a trade that finds no cash or no free slot is skipped. Window 2022-01 -> 2026-09-16 (the trend cache's end).
Recorded: the combined book and each strategy alone on the same engine and sizing (cumulative 806 + 4 = 810).
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
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blackheart-ingest", "src"))
import idx_beyond as BY  # noqa: E402
import idx_exit as E  # noqa: E402
import idx_gapfade as G  # noqa: E402
import idx_ml_confirm as F  # noqa: E402
import idx_ml_costaware as C  # noqa: E402
import idx_ml_strategy as M  # noqa: E402
import idx_swing2 as S  # noqa: E402
from blackheart_ingest.idx import research_store as rs  # noqa: E402
from blackheart_ingest.idx.ml import common  # noqa: E402

N_BEFORE = 806
STUDY = "combo_rupiah"
CAPITAL, PCT, MAX_POS, LOT = 20_000_000.0, 0.05, 20, 100
FEE_BUY, FEE_SELL = 0.0010, 0.0020
GAP_K = 5
START, END = pd.Timestamp("2022-01-01"), pd.Timestamp("2026-09-16")


def ml_trades(P, dates, codes, A, raw, offer, bid, liq):
    c_in, c_out = M.costs(raw, offer, bid)
    S_ = M.wide(P, "s5").reindex(index=dates, columns=codes).to_numpy(float)
    e5 = C.ema(S_ - np.nanmedian(np.where(liq, S_, np.nan), axis=1, keepdims=True), 3)
    t0 = int(np.searchsorted(dates, np.datetime64(START)))
    _, log = F.book(A, liq, e5, 10, c_in, c_out, 2.0, t_start=t0, wait=(0.05, 10))
    return [{"strat": "ML", "code": codes[r.j], "t_in": int(r.t_in), "t_out": int(r.t_out)} for r in log.itertuples()]


def trend_trades(dsn, dates, *, cache=None, board=None, legacy_shift=False):
    """The deployed trend book's own K-10 trades mapped onto `dates`. cache defaults to IDX_EXIT_CACHE; board -> E.load_all.
    legacy_shift=True reproduces the pre-2026-09-25 mapping (every trade one session late) for old reports only."""
    P, unis, comp, Hp, Lp = E.load_all(dsn, cache if cache is not None else os.environ.get("IDX_EXIT_CACHE"), board=board)
    c_in, c_out = S.costs(P)
    adj, vol = P["adj"], P["volume"]
    d_tr = adj.index
    A, H, L = adj.to_numpy(float), Hp.to_numpy(float), Lp.to_numpy(float)
    ma200 = adj.rolling(200, min_periods=200).mean()
    vr = vol / vol.rolling(20, min_periods=20).median()
    hi = adj.rolling(60, min_periods=60).max()
    entry = ((adj >= hi) & (adj > ma200) & (vr >= 1.5)).to_numpy(bool) & np.asarray(d_tr >= START)[:, None] & ~BY.regime_off_mask(comp, d_tr)[:, None]
    prev = adj.shift(1)
    tr = pd.concat([Hp - Lp, (Hp - prev).abs(), (Lp - prev).abs()], axis=1, keys=["a", "b", "c"]).T.groupby(level=1).max().T.reindex(columns=adj.columns)
    ATR = tr.ewm(alpha=1 / 20, adjust=False, min_periods=20).mean().to_numpy(float)
    ma20, ma50 = (adj.rolling(n, min_periods=n).mean().to_numpy(float) for n in (20, 50))
    d = adj.diff()
    up = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    RSI = (100 - 100 / (1 + up / dn.replace(0, np.nan))).to_numpy(float)
    LO10 = Lp.shift(1).rolling(10, min_periods=10).min().to_numpy(float)
    LO20 = Lp.shift(1).rolling(20, min_periods=20).min().to_numpy(float)
    rule = E.make_rules(A, H, L, ATR, ma20, ma50, RSI, LO10, LO20)["trail10"]
    small = (unis["LIQ"] & ~unis["BLUE"]).to_numpy(bool)
    _, trs, open_ = E.run_book(A, H, L, c_in, c_out, entry, vr.to_numpy(float), rule, small)
    pos = {d: i for i, d in enumerate(dates)}
    out = []
    lag = 1 if legacy_shift else 0
    for tup in trs:
        e, j, hold = tup[0], tup[1], tup[4]
        # E.run_book's tuple: e = the FILL day (signal at close e-1, bought at close e), hold = exit fill day - e.
        # (Before 2026-09-25 this read d_tr[e + 1], d_tr[e + 1 + hold] - every trend trade replayed one session late.)
        if e + lag + hold >= len(d_tr):
            continue
        d_in, d_out = d_tr[e + lag], d_tr[e + lag + hold]
        if d_in in pos and d_out in pos:
            out.append({"strat": "trend", "code": adj.columns[j], "t_in": pos[d_in], "t_out": pos[d_out]})
    return out


def gap_events(dsn, dates):
    B = G.build(dsn)
    g7, elig, v60 = B["masks"]["g7"], B["elig"], B["v60"]
    R = B["R"]["close"]
    o = B["P"]["open"]
    c = B["P"].get("close") if hasattr(B["P"], "get") else None       # the exit price, for trade lists only
    pos = {d: i for i, d in enumerate(dates)}
    out = []
    for d in R.index:
        dd = pd.Timestamp(d)
        if dd < START or dd not in pos:
            continue
        q = elig.loc[d] & g7.loc[d].fillna(False)
        if not q.any():
            continue
        pick = v60.loc[d].where(q).dropna().sort_values(ascending=False).index[:GAP_K]
        for code in pick:
            r, op = R.loc[d, code], o.loc[d, code]
            if np.isfinite(r) and np.isfinite(op) and op > 0:
                cl = float(c.loc[d, code]) if c is not None and code in c.columns and np.isfinite(c.loc[d, code]) else None
                out.append({"strat": "gap", "code": code, "t": pos[dd], "net": float(r), "open": float(op), "close": cl})
    return out


def engine(dates, codes, A, raw, offer, bid, ml, tr, gap, use: set[str], pct_gap: float = PCT):
    idx = {c: i for i, c in enumerate(codes)}
    T = len(dates)
    t0 = int(np.searchsorted(dates, np.datetime64(START)))
    entries: dict[int, list] = {}
    exits: dict[int, list] = {}
    for x in (ml if "ML" in use else []) + (tr if "trend" in use else []):
        entries.setdefault(x["t_in"], []).append(x)
        exits.setdefault(x["t_out"], []).append(x)
    gaps: dict[int, list] = {}
    for x in (gap if "gap" in use else []):
        gaps.setdefault(x["t"], []).append(x)
    cash = CAPITAL
    held: dict[tuple[str, str], dict] = {}
    nav = np.full(T, np.nan)
    trades = []
    invested = []
    for t in range(t0, T):
        nav_prev = nav[t - 1] if t > t0 else CAPITAL
        # morning: gap-fade, settled at the close
        day_gap = 0.0
        for x in sorted(gaps.get(t, []), key=lambda z: -z["net"] * 0):        # keep the deepest-liquidity order
            if len(held) >= MAX_POS:
                break
            px = (x["open"] + common.tick(x["open"])) * (1 + FEE_BUY)
            lots = int((pct_gap * nav_prev) // (px * LOT))
            cost = lots * LOT * px
            if lots < 1 or cost > cash:
                continue
            cash -= cost
            held[("gap", x["code"])] = {"cost": cost}
            proceeds = cost * (1 + x["net"])
            day_gap += proceeds
            trades.append({"strat": "gap", "code": x["code"], "t_in": t, "t_out": t, "cost": cost, "proceeds": proceeds, "pnl": proceeds - cost})
        # close: gap positions settle, then exits
        for key in [k for k in held if k[0] == "gap"]:
            held.pop(key)
        cash += day_gap
        for x in exits.get(t, []):
            key = (x["strat"], x["code"])
            if key not in held:
                continue
            p = held.pop(key)
            j = idx[x["code"]]
            px = bid[t, j] if bid[t, j] > 0 and bid[t, j] <= raw[t, j] else raw[t, j] - common.tick(raw[t, j])
            value = p["units"] * (A[t, j] / p["a_in"]) * (px / raw[t, j]) if not np.isnan(A[t, j]) else p["units"]
            proceeds = value * (1 - FEE_SELL)
            cash += proceeds
            trades.append({"strat": x["strat"], "code": x["code"], "t_in": p["t"], "t_out": t, "cost": p["cost"], "proceeds": proceeds, "pnl": proceeds - p["cost"]})
        mv = sum(p["units"] * (A[t, idx[k[1]]] / p["a_in"]) for k, p in held.items() if k[0] != "gap" and not np.isnan(A[t, idx[k[1]]]))
        nav_now = cash + mv
        for x in sorted(entries.get(t, []), key=lambda z: 0 if z["strat"] == "trend" else 1):
            key = (x["strat"], x["code"])
            j = idx[x["code"]]
            if key in held or len(held) >= MAX_POS or np.isnan(A[t, j]) or raw[t, j] <= 0:
                continue
            px = offer[t, j] if offer[t, j] > 0 and offer[t, j] >= raw[t, j] else raw[t, j] + common.tick(raw[t, j])
            lots = int((PCT * nav_now) // (px * LOT))
            cost = lots * LOT * px * (1 + FEE_BUY)
            if lots < 1 or cost > cash:
                continue
            cash -= cost
            held[key] = {"t": t, "a_in": A[t, j], "units": lots * LOT * raw[t, j], "cost": cost}
        mv = sum(p["units"] * (A[t, idx[k[1]]] / p["a_in"]) for k, p in held.items() if not np.isnan(A[t, idx[k[1]]]))
        nav[t] = cash + mv
        invested.append(mv / nav[t] if nav[t] > 0 else 0.0)
    navs = pd.Series(nav[t0:], index=dates[t0:])
    return navs, pd.DataFrame(trades), float(np.mean(invested))


def stats(nav: pd.Series) -> dict:
    r = nav.pct_change().fillna(0.0)
    yrs = (nav.index[-1] - nav.index[0]).days / 365.25
    eq = nav / nav.iloc[0]
    dd = eq / eq.cummax() - 1
    by = nav.groupby(nav.index.year).agg(["first", "last"])
    return {"final": float(nav.iloc[-1]), "total": float(eq.iloc[-1] - 1), "cagr": float(eq.iloc[-1] ** (1 / yrs) - 1),
            "sharpe": float(r.mean() / r.std() * np.sqrt(252)) if r.std() > 0 else float("nan"), "mdd": float(dd.min()), "mdd_rp": float((nav - nav.cummax()).min()),
            "by_year": {int(y): float(v["last"] / v["first"] - 1) for y, v in by.iterrows()}, "nav_year_end": {int(y): float(v["last"]) for y, v in by.iterrows()}}


def main() -> int:
    dsn = os.environ["INGEST_DB_DSN"]
    P = pickle.load(open(os.environ["IDX_ML_CACHE"], "rb"))
    P = P[(P["d"] >= "2021-06-01") & (P["d"] <= END)].copy()
    dates = M.wide(P, "close").index
    codes = M.wide(P, "close").columns
    g = lambda c: M.wide(P, c).reindex(index=dates, columns=codes)  # noqa: E731
    A, raw = g("ac").to_numpy(float), g("close").to_numpy(float)
    offer, bid = np.nan_to_num(g("offer").to_numpy(float)), np.nan_to_num(g("bid").to_numpy(float))
    liq = g("liq").fillna(False).astype(bool).to_numpy()
    ml = ml_trades(P, dates, codes, A, raw, offer, bid, liq)
    tr = trend_trades(dsn, dates)
    gap = gap_events(dsn, dates)
    M.log(f"events: ML {len(ml)} trades, trend {len(tr)} trades, gap-fade {len(gap)} day-events")
    res = {}
    for name, use in {"combined": {"gap", "trend", "ML"}, "gap_only": {"gap"}, "trend_only": {"trend"}, "ml_only": {"ML"}}.items():
        nav, T_, inv = engine(dates, codes, A, raw, offer, bid, ml, tr, gap, use)
        st = stats(nav)
        per = {}
        for s_, X in T_.groupby("strat"):
            per[s_] = {"n": len(X), "win": float((X["pnl"] > 0).mean()), "pnl": float(X["pnl"].sum()), "avg": float(X["pnl"].mean()), "best": float(X["pnl"].max()), "worst": float(X["pnl"].min())}
        st.update({"trades": len(T_), "invested_share": inv, "per_strategy": per, "fees": float((T_["cost"] * FEE_BUY / (1 + FEE_BUY) + T_["proceeds"] * FEE_SELL / (1 - FEE_SELL)).sum())})
        res[name] = st
        T_.assign(d_in=dates[T_["t_in"]], d_out=dates[T_["t_out"]]).to_csv(os.path.join(ROOT, "research-scratch", f"combo_rupiah_{name}.csv"), index=False)
        M.log(f"{name:<10} final Rp {st['final']:,.0f} ({st['total'] * 100:+.0f} %) CAGR {st['cagr'] * 100:.1f} % Sharpe {st['sharpe']:.2f} mDD {st['mdd'] * 100:.0f} % (Rp {st['mdd_rp']:,.0f}) "
              f"invested {inv * 100:.0f} % trades {len(T_)} | " + " ".join(f"{y}: Rp {v:,.0f} ({st['by_year'][y] * 100:+.0f} %)" for y, v in st["nav_year_end"].items()) + " | "
              + ", ".join(f"{k}: n {v['n']} win {v['win'] * 100:.0f} % P&L Rp {v['pnl']:,.0f}" for k, v in per.items()))
    n_trials = N_BEFORE + len(res)
    L = [f"# IDX menu ML-10 - top-3 strategies on one Rp 20 M book, 5 % of NAV per trade - {date.today()} - cumulative N = {n_trials}", "",
         "Gap-fade (deployed rule, K 5/day, intraday) + trend small + gate (trail-10) + ML cost-aware with +5 % confirmation, one cash pool, 20 slots, lots of 100, "
         "closing offer/bid + Stockbit fees (gap-fade: open + tick / close - tick). 2022-01 -> 2026-09-16.", "",
         "| book | final NAV | total | CAGR | Sharpe | mDD | mDD Rp | invested | trades | fees |", "|---|---|---|---|---|---|---|---|---|---|"]
    for name, st in res.items():
        L.append(f"| {name} | Rp {st['final']:,.0f} | {st['total'] * 100:+.0f} % | {st['cagr'] * 100:.1f} % | {st['sharpe']:.2f} | {st['mdd'] * 100:.0f} % | Rp {st['mdd_rp']:,.0f} | "
                 f"{st['invested_share'] * 100:.0f} % | {st['trades']} | Rp {st['fees']:,.0f} |")
    L += ["", "| book | " + " | ".join(str(y) for y in res["combined"]["nav_year_end"]) + " |", "|---|" + "---|" * len(res["combined"]["nav_year_end"])]
    for name, st in res.items():
        L.append(f"| {name} | " + " | ".join(f"Rp {v:,.0f} ({st['by_year'][y] * 100:+.0f} %)" for y, v in st["nav_year_end"].items()) + " |")
    L += ["", "## Combined book, per strategy", "", "| strategy | trades | win | total P&L | avg P&L | best | worst |", "|---|---|---|---|---|---|---|"]
    for k, v in res["combined"]["per_strategy"].items():
        L.append(f"| {k} | {v['n']} | {v['win'] * 100:.0f} % | Rp {v['pnl']:,.0f} | Rp {v['avg']:,.0f} | Rp {v['best']:,.0f} | Rp {v['worst']:,.0f} |")
    text = "\n".join(L)
    out = os.path.join(HERE, f"IDX_COMBO_RUPIAH_{date.today()}.md")
    open(out, "w", encoding="utf-8").write(text + "\n")
    print(text)
    with psycopg.connect(dsn) as conn:
        sid = rs.record_study(conn, STUDY, date.today(), params={"trials": list(res), "n_trials_cumulative": n_trials, "capital": CAPITAL, "pct": PCT, "max_pos": MAX_POS},
                              summary=common.plain(res), names=[], report_path=out)
        conn.commit()
    M.log(f"study #{sid} stored")
    return 0


if __name__ == "__main__":
    sys.exit(main())
