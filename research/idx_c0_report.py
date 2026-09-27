#!/usr/bin/env python3
"""IDX C0 radar (wide) - REPORTING run for the Strategies page (operator 2026-09-27: "halaman strategi C0 dulu"). No trial.

Two things, both so the page can read every figure from a stored study instead of typed prose:
  1. adds the numeric holdout table to study #407 (filter_lab), whose stored summary held text only; the numbers are the ones
     the locked holdout agent wrote (research-scratch/idx/filterlab/agents/holdout_run/*.json), not re-run;
  2. stores study 'c0_sleeve': the sleeve AS DEPLOYED on its own (every C0 flag, 20-day value Rp 1-50 bn, one position per
     name, stop -15 % / trail 25 %, Rp 20 m book, 1.25 % of NAV per position, <= 40 open, lots, offer/bid, band realism;
     2022-01 -> cache end) with the book statistics, the four start dates, per-trade statistics of every capped trade
     2021-26 (research-scratch/idx/filterlab), exits by kind, the exit alternatives on the same entries (descriptive), by
     entry year and execution facts; and imports the book's trade list into idx.strategy_backtest_trade for the Results tab.
READ-ONLY on market data; writes one idx.study row, updates #407's summary, and replaces the page's imported trades.
"""
from __future__ import annotations

import csv
import json
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
os.environ.setdefault("IDX_BOARD_MODE", "pit")
import idx_c0_wide as W  # noqa: E402
import idx_combo_live as CL  # noqa: E402
import idx_exit as E  # noqa: E402
import idx_radar_book as RB  # noqa: E402
import idx_swing2 as S  # noqa: E402
import idx_trend_c0 as T  # noqa: E402

FL = os.path.join(ROOT, "research-scratch", "idx", "filterlab")
PAGE_KEY = "c0_radar"
CAP, START = 50e9, "2022-01-03"


def enrich_407(conn):
    hold = os.path.join(FL, "agents", "holdout_run")
    log = [json.loads(ln)["expr"] for ln in open(os.path.join(FL, "holdout", "holdout_log.jsonl"), encoding="utf-8")]
    names = {"": "base", "r250 > r60": "prior_uptrend", "r250 > r60 and r20 < 0.8": "prior_uptrend_not_stretched",
             "value20_bn < 60": "liquidity_cap_60", "value20_bn < 5 * mcap_tn": "low_turnover", "ep_ytd > -0.01": "loss_veto",
             "value20_bn < 50": "liquidity_cap_50"}
    table = {}
    for f in ("base", "c1", "c2", "c3", "c4", "c5", "c6"):
        d = json.load(open(os.path.join(hold, f + ".json"), encoding="utf-8"))
        table[names.get(d.get("expr") or "", f)] = {"expr": d.get("expr"), "kept": d["kept"], "dropped": d["dropped"], "welch_t": d.get("welch_t"),
                                                   "book_filtered": d["book_filtered"], "book_base": d["book_base"]}
    add = {"holdout": table, "holdout_calls": len(log), "train_trades": 622, "holdout_trades": 663, "train_expressions": 1454,
           "candidates": 17, "survivors": 6, "passed": 2}
    with conn.cursor() as cur:
        cur.execute("UPDATE idx.study SET summary = summary || %s::jsonb WHERE id = 407", (json.dumps(add),))
    conn.commit()
    return table


def replay_logged(trades, P, start, capital, pct, maxpos, why):
    """idx_c0_wide.replay with a trade log and the invested share (same fills, same band realism)."""
    adj, raw, off, bid = (P[k].to_numpy(float) for k in ("adj", "close", "offer", "bid"))
    dates, cols = P["adj"].index, P["adj"].columns
    Tn = len(dates)
    t0 = int(np.searchsorted(dates, np.datetime64(pd.Timestamp(start))))
    entries = {}
    for e, j, x, s in trades:
        if e >= t0:
            entries.setdefault(e, []).append((j, x, s))
    cash, held, nav, inv, log = capital, {}, np.full(Tn, np.nan), [], []
    for t in range(t0, Tn):
        for j in [j for j, p in held.items() if p["x"] <= t]:
            p = held[j]
            r = raw[t, j] / raw[t - 1, j] - 1 if raw[t - 1, j] > 0 else 0.0
            if np.isnan(adj[t, j]) or (r <= T.DNLOCK and not (bid[t, j] > 0) and t - p["x"] < 10):
                continue
            px = bid[t, j] if 0 < bid[t, j] <= raw[t, j] else raw[t, j] - T.tick(raw[t, j])
            proceeds = p["units"] * (adj[t, j] / p["a_in"]) * (px / raw[t, j]) * (1 - T.FEE_SELL)
            cash += proceeds
            log.append({"strat": "c0w", "code": cols[j], "d_in": dates[p["t"]].date(), "d_out": dates[t].date(), "cost": p["cost"],
                        "pnl": proceeds - p["cost"], "entry": p["px"], "exit": px, "why": why.get((p["e"], j), "")})
            held.pop(j)
        mv = sum(p["units"] * adj[t, j] / p["a_in"] for j, p in held.items() if not np.isnan(adj[t, j]))
        nav_now = cash + mv
        for j, x, s in sorted(entries.get(t, []), key=lambda z: -z[2]):
            if j in held or len(held) >= maxpos or np.isnan(adj[t, j]) or not raw[t, j] > 0:
                continue
            px = off[t, j] if off[t, j] > 0 and off[t, j] >= raw[t, j] else raw[t, j] + T.tick(raw[t, j])
            lots = int((pct * nav_now) // (px * T.LOT * (1 + T.FEE_BUY)))
            cost = lots * T.LOT * px * (1 + T.FEE_BUY)
            if lots < 1 or cost > cash:
                continue
            cash -= cost
            held[j] = {"a_in": adj[t, j], "units": lots * T.LOT * raw[t, j], "x": x, "t": t, "e": t, "cost": cost, "px": px}
        mv = sum(p["units"] * adj[t, j] / p["a_in"] for j, p in held.items() if not np.isnan(adj[t, j]))
        nav[t] = cash + mv
        inv.append(mv / nav[t] if nav[t] > 0 else 0.0)
    return pd.Series(nav[t0:], index=dates[t0:]).ffill(), inv, log


def trade_side_stats():
    """Per-trade statistics of every capped C0 trade 2021-26 (the filter lab's trade list) and the exit alternatives."""
    df = pd.concat([pd.read_parquet(os.path.join(FL, "trades_train.parquet")), pd.read_parquet(os.path.join(FL, "holdout", "trades_holdout.parquet"))],
                   ignore_index=True)
    df = df[df.value20_bn < 50].reset_index(drop=True)
    arr = dict(np.load(os.path.join(FL, "arrays.npz")))
    A = arr["A"]
    df["gross"] = [A[r.x, r.j] / A[r.e, r.j] - 1 for r in df.itertuples()]
    w, lo = df.net[df.net > 0], df.net[df.net <= 0]
    top = df.net.sort_values(ascending=False)
    k = max(1, round(len(df) * 0.05))
    kind = np.where(df.open_at_end, "open", np.where(df.stop, "stop", "trail"))
    exits = {kk: {"n": int((kind == kk).sum()), "share": float((kind == kk).mean()), "mean": float(df.net[kind == kk].mean()),
                  "median": float(df.net[kind == kk].median()), "hold_median": float(df.hold[kind == kk].median()),
                  "profit_share": float(df.net[kind == kk].sum() / df.net.sum())} for kk in ("stop", "trail", "open")}
    wait = np.array([A[r.e, r.j] / A[r.i, r.j] - 1 for r in df.itertuples()])
    stats = {"n": len(df), "names": int(df.code.nunique()), "first": str(df.d.min().date()), "last": str(df.d.max().date()),
             "win": float((df.net > 0).mean()), "avg_win": float(w.mean()), "avg_loss": float(lo.mean()), "expectancy": float(df.net.mean()),
             "median": float(df.net.median()), "profit_factor": float(w.sum() / abs(lo.sum())), "touch2x": float(df.touch2x.mean()),
             "hold_median": float(df.hold.median()), "hold_win": float(df.hold[df.net > 0].median()), "hold_loss": float(df.hold[df.net <= 0].median()),
             "top5pct_profit_share": float(top.iloc[:k].sum() / df.net.sum()), "over100_n": int((df.net >= 1).sum()),
             "over100_profit_share": float(df.net[df.net >= 1].sum() / df.net.sum()), "mfe_win": float(df.mfe[df.net > 0].mean()),
             "capture_win": float(w.sum() / df.mfe[df.net > 0].sum()), "cost_mean": float((df.gross - df.net).mean()),
             "cost_median": float((df.gross - df.net).median()), "spread_median": float(df.spread_rel.median()),
             "wait_mean": float(wait.mean()), "wait_median": float(np.median(wait)), "wait_up": float((wait > 0).mean()),
             "stop_mean": exits["stop"]["mean"], "stop_p10": float(df.net[kind == "stop"].quantile(0.1)), "worst": float(df.net.min()),
             "value20_median_bn": float(df.value20_bn.median()), "sd": float(df.net.std())}
    by_year = {str(y): {"n": len(g), "mean": float(g.net.mean()), "median": float(g.net.median()), "win": float((g.net > 0).mean()),
                        "touch2x": float(g.touch2x.mean()), "stop": float(g.stop.mean())} for y, g in df.groupby(df.d.dt.year)}
    top10 = [{"code": r.code, "d": str(r.d.date()), "ret": float(r.net), "hold": int(r.hold)} for r in df.nlargest(10, "net").itertuples()]
    return stats, exits, by_year, top10


ALTS = {"deployed": "stop 15 + trail 25", "tp20": "take profit +20 %", "tp30": "take profit +30 %", "tp50": "take profit +50 %",
        "tp100": "take profit +100 %", "half50": "half at +50 %, rest trail 25", "trail15": "trail 15", "trail20": "trail 20",
        "trail30": "trail 30", "trail35": "trail 35", "nostop": "no cut loss", "stop10": "stop 10", "stop20": "stop 20", "t60": "time exit 60"}


def alternatives():
    import importlib.util
    spec = importlib.util.spec_from_file_location("c0d", os.path.join(FL, "c0_detail.py"))
    # c0_detail.py prints as it runs; reuse its sim() by executing it quietly
    import contextlib
    import io
    mod = importlib.util.module_from_spec(spec)
    with contextlib.redirect_stdout(io.StringIO()):
        spec.loader.exec_module(mod)
    runs = {"deployed": mod.sim(), "tp20": mod.sim(trail=None, tp=0.20), "tp30": mod.sim(trail=None, tp=0.30), "tp50": mod.sim(trail=None, tp=0.50),
            "tp100": mod.sim(trail=None, tp=1.00), "half50": mod.sim(half_at=0.50), "trail15": mod.sim(trail=0.15), "trail20": mod.sim(trail=0.20),
            "trail30": mod.sim(trail=0.30), "trail35": mod.sim(trail=0.35), "nostop": mod.sim(stop=None), "stop10": mod.sim(stop=0.10),
            "stop20": mod.sim(stop=0.20), "t60": mod.sim(tmax=60)}
    return {k: {kk: float(vv) for kk, vv in v.items()} | {"label": ALTS[k]} for k, v in runs.items()}


def main() -> int:
    dsn = T.dsn()
    with psycopg.connect(dsn) as conn:
        hold = enrich_407(conn)
    print("#407 enriched:", {k: (v["kept"]["n"], v["welch_t"]) for k, v in hold.items()})
    P, unis, comp, Hp, Lp = E.load_all(dsn, T.CACHE, board="pit")
    c_in, c_out = S.costs(P)
    dates = P["adj"].index
    A, H, L = P["adj"].to_numpy(float), Hp.to_numpy(float), Lp.to_numpy(float)
    raw = P["close"].to_numpy(float)
    arms, vr, c0_entry, u1, tier = RB.masks(P, unis, comp)
    value = P["close"] * P["volume"]
    v20 = value.rolling(20, min_periods=15).mean()
    attn = (v20 / value.rolling(250, min_periods=200).mean()).to_numpy(float)
    t_first = int(np.searchsorted(dates, np.datetime64(pd.Timestamp(START)))) - 1
    tr = W.all_trades(A, raw, c_in, c0_entry & u1 & (v20 < CAP).to_numpy(bool), attn, t0=t_first)
    why = {}
    for e, j, x, s in tr:
        path = A[e:x, j]
        path = path[~np.isnan(path)]
        why[(e, j)] = "cut loss -15 %" if len(path) and path[-1] <= 0.85 * A[e, j] else ("trailing -25 %" if x < len(A) - 1 else "open")
    nav, inv, log = replay_logged(tr, P, START, 20e6, W.PCT_W, W.MAXPOS_W, why)
    book = CL.book_stats(nav, inv)
    Tt = pd.DataFrame(log)
    Tt["hold"] = [(pd.Timestamp(b) - pd.Timestamp(a)).days for a, b in zip(Tt.d_in, Tt.d_out, strict=True)]
    Tt["sleeve"] = "c0w"
    book.update({k: v for k, v in CL.trade_stats(Tt).items() if k != "per_strategy"})
    starts = {}
    for st in W.STARTS:
        w = W.replay(tr, P, st, 20e6, W.PCT_W, W.MAXPOS_W)
        starts[st] = {k: w[k] for k in ("cagr", "sharpe", "mdd")}
    stats, exits, by_year, top10 = trade_side_stats()
    alts = alternatives()
    summary = {"c0_book": book, "starts": starts, "trade_stats": stats, "exits": exits, "by_entry_year": by_year, "top10": top10,
               "alternatives": alts, "config": {"capital": 20e6, "pct": W.PCT_W, "maxpos": W.MAXPOS_W, "cap_v20": CAP, "stop": 0.15, "trail": 0.25,
                                               "from": START}}
    csv_path = os.path.join(ROOT, "research-scratch", "c0_sleeve_trades.csv")
    Tt.to_csv(csv_path, index=False)
    from blackheart_ingest.idx import research_store as rs
    from blackheart_ingest.idx import strategy_page as sp
    with psycopg.connect(dsn) as conn:
        sid = rs.record_study(conn, "c0_sleeve", date.today(), params={"trials": [], "kind": "reporting", "sources": [403, 405, 407, 408]},
                              summary=json.loads(json.dumps(summary, default=str)), names=[], report_path="research/idx_c0_report.py",
                              note="C0 radar (wide) as deployed on its own - reporting, no trial; feeds the Strategies page")
    with psycopg.connect(dsn, row_factory=psycopg.rows.dict_row) as conn:
        n = sp.import_backtest(conn, PAGE_KEY, sid, csv_path)
    print(f"study #{sid} stored; {n} trades imported for '{PAGE_KEY}'")
    print(f"book {START}..: CAGR {book['cagr'] * 100:.1f} % Sharpe {book['sharpe']:.2f} mDD {book['mdd'] * 100:.1f} % trades {book['trades']} "
          f"win {book['win'] * 100:.0f} % ex-2025 {book['cagr_ex2025'] * 100:.1f} %; by year {({y: round(v * 100, 1) for y, v in book['by_year'].items()})}")
    print("starts", {k: (round(v["cagr"] * 100, 1), round(v["sharpe"], 2)) for k, v in starts.items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
