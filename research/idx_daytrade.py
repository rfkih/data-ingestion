#!/usr/bin/env python3
"""IDX menu 29 — day trading (operator, 2026-09-22: "kalau day trading kamu bisa nggak?").

Day trading here = long-only, buy at the open, sell at the close of the same day, decided from information available at or before
the open. The tick feed has one session, so the test uses seven years of daily bars (2020-01 -> 2026-09-21): IDX opens where the
summary has them (5 % of rows before 2025, ~60 % after), else the desk's Yahoo daily cache scaled to the IDX close and accepted only
inside the day's low..high (the menu-16 recipe); rows without a usable open are skipped, never guessed.

PRE-REGISTERED (declared before the run; nothing tuned afterwards). 8 trials (cumulative 520 + 8 = 528); random = reference.
  Universe   main board, 60-day median value >= Rp 5 bn (the desk's tradeable floor, PIT), close >= 50, not locked (open = high = low).
  Execution  buy at open + 1 tick (the offer), sell at close - 1 tick (the bid); fees 0.10 % + 0.20 %. Up to K = 10 names a day per rule,
             the most liquid first; equal weight; one day; no overnight.
  Arms (signal known at the open)
    gap_up        open >= previous close x 1.02                      gap-and-go (continuation)
    gap_down      open <= previous close x 0.98                      gap fade (bounce)
    prev_breakout previous close > the prior 20-day high             breakout continuation
    prev_drop     previous day return <= -3 %                        next-day bounce
    mom5          top 10 by 5-day return to the previous close       short momentum
    rev5          bottom 10 by 5-day return                          short reversal
    trend_set     previous close > MA200 AND = 60-day high AND volume >= 1.5x 20-day average   the desk's trend signal, intraday only
    vol_surge     previous day volume >= 3x its 20-day average AND previous return > 0         attention continuation
    random        10 random eligible names a day                     reference
  Reads      trades, hit rate, mean gross / net per trade (bps), daily portfolio series -> t (mean / se), Sharpe (annualised on
             trading days), total, max drawdown, years positive (of 7), net vs random.
  Bar        CANDIDATE: net/trade > 0, t >= 3, Sharpe >= 1.0, >= 5 of 7 years positive, net/trade >= random + 50 bps.
  Facts first the market's own intraday vs overnight return (EW across the universe, per year): the headwind or tailwind every
             long-only day trade starts with.

READ-ONLY. INGEST_DB_DSN=... PYTHONIOENCODING=utf-8 blackheart-ingest/.venv/Scripts/python research/idx_daytrade.py [--no-store]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import date

import numpy as np
import pandas as pd
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "blackheart-ingest", "src"))

START, END = date(2020, 1, 1), date(2026, 9, 21)
FEE_BUY, FEE_SELL = 0.0010, 0.0020
LIQ = 5e9
K = 10
SEED = 20260922
ARMS = ["gap_up", "gap_down", "prev_breakout", "prev_drop", "mom5", "rev5", "trend_set", "vol_surge"]
N_TRIALS_BEFORE = 520
YAHOO = os.path.join(ROOT, "research-scratch", "idx")


def tick(p):
    p = np.asarray(p, dtype=float)
    return np.select([p < 200, p < 500, p < 2000, p < 5000], [1, 2, 5, 10], 25).astype(float)


# ------------------------------------------------------------------------------------------------------------------ data
def load(conn) -> pd.DataFrame:
    bars = pd.read_sql("""SELECT b.code, b.trade_date, b.open, b.high, b.low, b.close, b.volume, b.value, s.remarks, f.value_60d_median AS v60
                            FROM idx.bar b JOIN idx.daily_summary s USING (code, trade_date) LEFT JOIN idx.feature_daily f USING (code, trade_date)
                           WHERE b.source = 'idx' AND b.trade_date BETWEEN %s AND %s""", conn, params=(START, END))
    for c in ("open", "high", "low", "close", "volume", "value", "v60"):
        bars[c] = pd.to_numeric(bars[c], errors="coerce")
    bars["main"] = bars["remarks"].fillna("").str[4:5].isin(["1", "2"])
    parts = []
    for f in sorted(glob.glob(os.path.join(YAHOO, "*.JK.csv"))):
        code = os.path.basename(f).split(".")[0]
        df = pd.read_csv(f, usecols=["date", "open", "close"])
        df = df[df["date"] >= str(START)]
        df["code"] = code
        parts.append(df)
    y = pd.concat(parts, ignore_index=True)
    y["trade_date"] = pd.to_datetime(y["date"]).dt.date
    y["y_open"] = pd.to_numeric(y["open"], errors="coerce")
    y["y_close"] = pd.to_numeric(y["close"], errors="coerce")
    y = y[(y["y_open"] > 0) & (y["y_close"] > 0)].drop_duplicates(["code", "trade_date"], keep="last")[["code", "trade_date", "y_open", "y_close"]]
    bars = bars.merge(y, on=["code", "trade_date"], how="left")
    fill = bars["y_open"] * (bars["close"] / bars["y_close"])
    ok = bars["open"].isna() & fill.notna() & (bars["volume"] > 0) & (fill >= bars["low"] - 0.5) & (fill <= bars["high"] + 0.5)
    bars["open_src"] = np.where(bars["open"].notna(), "idx", np.where(ok, "yahoo", "none"))
    bars.loc[ok, "open"] = fill[ok]
    bars.loc[bars["open"].notna() & ((bars["open"] < bars["low"] - 0.5) | (bars["open"] > bars["high"] + 0.5)), "open"] = np.nan
    return bars.sort_values(["code", "trade_date"])


def panels(bars: pd.DataFrame) -> dict[str, pd.DataFrame]:
    P = {c: bars.pivot(index="trade_date", columns="code", values=c).sort_index() for c in ("open", "high", "low", "close", "volume", "v60")}
    P["main"] = bars.pivot(index="trade_date", columns="code", values="main").sort_index().fillna(False).astype(bool)
    return P


# ----------------------------------------------------------------------------------------------------------------- arms
def signals(P: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    o, h, lo, c, v = P["open"], P["high"], P["low"], P["close"], P["volume"]
    pc = c.shift(1)
    ret1 = pc / c.shift(2) - 1
    ret5 = pc / c.shift(6) - 1
    hi20 = h.shift(1).rolling(20, min_periods=15).max().shift(1)          # prior 20-day high, excluding the previous day itself
    ma200 = c.shift(1).rolling(200, min_periods=150).mean()
    hi60 = c.shift(1).rolling(60, min_periods=45).max()
    v20 = v.shift(1).rolling(20, min_periods=15).mean()
    pv = v.shift(1)
    S = {"gap_up": (o >= pc * 1.02), "gap_down": (o <= pc * 0.98), "prev_breakout": (pc > hi20), "prev_drop": (ret1 <= -0.03),
         "trend_set": (pc > ma200) & (pc >= hi60) & (pv >= 1.5 * v20), "vol_surge": (pv >= 3 * v20) & (ret1 > 0)}
    S = {k: v_.astype(float).where(v_.notna()) for k, v_ in S.items()}
    S["mom5"] = ret5          # ranked
    S["rev5"] = -ret5         # ranked
    return S


def eligible(P: dict[str, pd.DataFrame]) -> pd.DataFrame:
    o, h, lo, c, v60 = P["open"], P["high"], P["low"], P["close"], P["v60"]
    locked = (o == h) & (h == lo)
    return P["main"] & (v60.shift(1) >= LIQ) & (c.shift(1) >= 50) & o.notna() & c.notna() & ~locked


def net_day_return(P: dict[str, pd.DataFrame]) -> pd.DataFrame:
    o, c = P["open"], P["close"]
    buy = (o + tick(o.to_numpy())) * (1 + FEE_BUY)
    sell = (c - tick(c.to_numpy())) * (1 - FEE_SELL)
    return sell / buy - 1


def run_arm(name: str, sig: pd.DataFrame, elig: pd.DataFrame, R: pd.DataFrame, G: pd.DataFrame, v60: pd.DataFrame, rng: np.random.Generator) -> dict:
    """Pick up to K names a day: ranked arms by signal, threshold arms by liquidity among qualifiers; equal-weight day return."""
    ranked = name in ("mom5", "rev5")
    days, rets, gross, n_tr, hits = [], [], [], 0, 0
    for d in R.index:
        e = elig.loc[d]
        if name == "random":
            cand = e[e].index.to_numpy()
            if len(cand) == 0:
                continue
            pick = rng.choice(cand, size=min(K, len(cand)), replace=False)
        else:
            s = sig.loc[d]
            if ranked:
                s = s.where(e)
                s = s.dropna().sort_values(ascending=False)
                pick = s.index[:K].to_numpy()
            else:
                q = e & (s == 1.0)
                if not q.any():
                    continue
                pick = v60.loc[d].where(q).dropna().sort_values(ascending=False).index[:K].to_numpy()
        if len(pick) == 0:
            continue
        r = R.loc[d, pick].dropna()
        if r.empty:
            continue
        days.append(d)
        rets.append(float(r.mean()))
        gross.append(float(G.loc[d, r.index].mean()))
        n_tr += len(r)
        hits += int((r > 0).sum())
    s = pd.Series(rets, index=pd.to_datetime(days))
    if len(s) < 20:
        return {"arm": name, "trades": n_tr, "days": len(s), "verdict": "too few"}
    t = float(s.mean() / (s.std(ddof=1) / np.sqrt(len(s)))) if s.std(ddof=1) > 0 else float("nan")
    eq = (1 + s).cumprod()
    mdd = float((eq / eq.cummax() - 1).min())
    years = s.groupby(s.index.year).sum()
    return {"arm": name, "trades": n_tr, "days": len(s), "hit": hits / n_tr, "gross_bps": float(np.mean(gross) * 1e4), "net_bps": float(s.mean() * 1e4),
            "t": t, "sharpe": float(s.mean() / s.std(ddof=1) * np.sqrt(252)) if s.std(ddof=1) > 0 else float("nan"),
            "total": float(eq.iloc[-1] - 1), "mdd": mdd, "years_pos": int((years > 0).sum()), "years_n": len(years),
            "by_year": {int(y): round(float(v) * 100, 1) for y, v in years.items()}}


def intraday_vs_overnight(P: dict[str, pd.DataFrame], elig: pd.DataFrame) -> dict:
    o, c = P["open"], P["close"]
    intra = (c / o - 1).where(elig)
    over = (o / c.shift(1) - 1).where(elig)
    ew_i, ew_o = intra.mean(axis=1), over.mean(axis=1)
    out = {}
    for y, g in ew_i.groupby(pd.to_datetime(ew_i.index).year):
        go = ew_o.loc[g.index]
        out[int(y)] = {"intraday_bps_per_day": float(g.mean() * 1e4), "overnight_bps_per_day": float(go.mean() * 1e4),
                       "intraday_total_pct": float(((1 + g).prod() - 1) * 100), "overnight_total_pct": float(((1 + go).prod() - 1) * 100), "days": int(g.notna().sum())}
    out["all"] = {"intraday_bps_per_day": float(ew_i.mean() * 1e4), "overnight_bps_per_day": float(ew_o.mean() * 1e4),
                  "intraday_total_pct": float(((1 + ew_i.dropna()).prod() - 1) * 100), "overnight_total_pct": float(((1 + ew_o.dropna()).prod() - 1) * 100),
                  "days": int(ew_i.notna().sum())}
    return out


# ----------------------------------------------------------------------------------------------------------------- run
def run(dsn: str, out_path: str, store: bool, study_name: str) -> dict:
    with psycopg.connect(dsn) as conn:
        bars = load(conn)
    P = panels(bars)
    elig = eligible(P)
    R, G = net_day_return(P), (P["close"] / P["open"] - 1)
    S = signals(P)
    rng = np.random.default_rng(SEED)
    res: dict = {"desc": {"start": START.isoformat(), "end": END.isoformat(), "open_src": bars["open_src"].value_counts().to_dict(),
                          "eligible_name_days": int(elig.sum().sum()), "names": int(elig.any().sum())},
                 "market": intraday_vs_overnight(P, elig), "arms": {}}
    res["arms"]["random"] = run_arm("random", None, elig, R, G, P["v60"], rng)
    for a in ARMS:
        res["arms"][a] = run_arm(a, S[a], elig, R, G, P["v60"], rng)
    rnd = res["arms"]["random"].get("net_bps", 0.0)
    for a in ARMS:
        r = res["arms"][a]
        if "net_bps" in r:
            ok = r["net_bps"] > 0 and r["t"] >= 3 and r["sharpe"] >= 1.0 and r["years_pos"] >= 5 and r["net_bps"] >= rnd + 50
            fails = [k for k, c in (("net<=0", r["net_bps"] <= 0), ("t<3", r["t"] < 3), ("sharpe<1", r["sharpe"] < 1.0), ("years", r["years_pos"] < 5), ("vs random", r["net_bps"] < rnd + 50)) if c]
            r["verdict"] = "CANDIDATE" if ok else "tested: " + ",".join(fails)
    res["verdict"] = {"candidates": [a for a in ARMS if res["arms"][a].get("verdict") == "CANDIDATE"]}
    write_report(res, out_path)
    if store:
        from blackheart_ingest.idx import research_store as rs
        with psycopg.connect(dsn) as conn:
            sid = rs.record_study(conn, study_name, END, params={"trials": ARMS, "n_trials_cumulative": N_TRIALS_BEFORE + len(ARMS), "K": K, "liq": LIQ, "seed": SEED},
                                 summary=json.loads(json.dumps(res, default=str)), names=[], report_path=out_path,
                                 note=f"{len(res['verdict']['candidates'])} candidates of {len(ARMS)}; market intraday {res['market']['all']['intraday_bps_per_day']:+.1f} bps/day vs overnight {res['market']['all']['overnight_bps_per_day']:+.1f}")
            res["study_id"] = sid
    return res


def f1(x, d=1):
    return "-" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.{d}f}"


def write_report(res: dict, path: str) -> None:
    d, m = res["desc"], res["market"]
    L = [f"# IDX menu 29 — day trading (open -> close, long only) — {d['start']} -> {d['end']}", "",
         f"Universe: main board, v60 >= Rp 5 bn, not locked; {d['names']} names, {d['eligible_name_days']:,} eligible name-days; opens: {d['open_src']}.",
         "Execution: buy open + 1 tick, sell close - 1 tick, fees 0.10 % + 0.20 %, up to 10 names a day, equal weight. Pre-registered in `research/idx_daytrade.py`; 8 trials (cumulative 528).",
         "", "## The market's own intraday vs overnight return (equal-weight across the eligible universe)", "",
         "| year | intraday bps/day | overnight bps/day | intraday total | overnight total | days |", "|---|---|---|---|---|---|"]
    for y, r in m.items():
        L.append(f"| {y} | {r['intraday_bps_per_day']:+.1f} | {r['overnight_bps_per_day']:+.1f} | {r['intraday_total_pct']:+.1f} % | {r['overnight_total_pct']:+.1f} % | {r['days']} |")
    L += ["", "## Arms", "", "| arm | trades | days | hit | gross/trade | net/trade | t | Sharpe | total | mDD | years + | by year (%) | verdict |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for a in ["random", *ARMS]:
        r = res["arms"][a]
        if "net_bps" not in r:
            L.append(f"| {a} | {r['trades']} | {r['days']} | - | - | - | - | - | - | - | - | - | {r['verdict']} |")
            continue
        L.append(f"| {a} | {r['trades']:,} | {r['days']:,} | {r['hit']*100:.0f} % | {r['gross_bps']:+.0f} bps | **{r['net_bps']:+.0f} bps** | {f1(r['t'])} | {f1(r['sharpe'],2)} | "
                 f"{r['total']*100:+.0f} % | {r['mdd']*100:.0f} % | {r['years_pos']}/{r['years_n']} | {' '.join(f'{y%100}:{v:+.0f}' for y, v in r['by_year'].items())} | {r.get('verdict', 'reference')} |")
    L += ["", "## Reading", "", f"- Candidates by the declared bar: {', '.join(res['verdict']['candidates']) or 'none'}.",
          "- Every trade pays ~30 bps of fees plus two ticks (the open offer and the closing bid); a day trade has to beat that every day it is on.",
          "- The intraday-vs-overnight table is the structural fact: it says whether being long during the session, on average, is paid at all.", ""]
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(L))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-store", action="store_true")
    ap.add_argument("--out", default="")
    ap.add_argument("--study-name", default="daytrade")
    a = ap.parse_args()
    out = a.out or os.path.join(HERE, f"IDX_DAYTRADE_{date.today().isoformat()}.md")
    res = run(os.environ["INGEST_DB_DSN"], out, not a.no_store, a.study_name)
    print(json.dumps({"market_all": res["market"]["all"], "arms": {k: {x: v.get(x) for x in ("trades", "net_bps", "t", "sharpe", "years_pos", "verdict")} for k, v in res["arms"].items()},
                      "study_id": res.get("study_id"), "report": out}, indent=1, default=str))


if __name__ == "__main__":
    main()
