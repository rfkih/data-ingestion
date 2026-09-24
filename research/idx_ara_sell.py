#!/usr/bin/env python3
"""IDX menu 34 — "a name I hold touches ARA today: sell at the ARA price, or hold?" (operator, 2026-09-23: "atau menyentuh ARA jadi
kita jual di harga paling atas"). Complements menu 16 (ARA hunter: buying = fill illusion, 0/24) and ML-3 (P(ARA tomorrow) is
predictable, precision@5 7-18 %, but not buyable). This is the HOLDER's side, which has no fill problem: a resting sell at the ARA
price is free (menu 29c addendum) and fills if the price gets there.

DESIGN (pre-registered before the first run; daily bars idx.bar 2020-01 → 2026-09, main-board names, prev close >= Rp 50)
  ARA price  prev_close * (1 + 35 / 25 / 20 %) rounded down to the tick (band by prev close: <= 200 / <= 5,000 / above).
  Event      TOUCH day t: high >= ARA price. LOCK: close >= ARA price (the touch held to the close). FADED: touched, closed below.
  Question   the holder could have sold at the ARA price on day t. Value of holding instead, in bps relative to the ARA price:
               H0 = close_t / ARA − 1              (sold at the close instead)
               H1 = close_{t+1} / ARA − 1          (held one more day)
               H5 = close_{t+5} / ARA − 1
               H20 = close_{t+20} / ARA − 1
             Negative = selling at ARA was better. Reported for ALL touches, LOCK, FADED, by year, and by liquidity (60-day median
             value >= Rp 5 bn = LIQ) — the desk's books hold LIQ names.
  Also       P(lock | touch); P(touch again t+1 | lock); the 'ride' alternative: hold while the close stays locked, sell at the first
             non-locked close (max 10 days) vs ARA on day t — the best case for holding through an ARA chain.
  Trials     4 horizons x {ALL, LIQ} = 8 reads on ONE question; counted as 4 trials (the horizons; ALL vs LIQ is a split).
             Cumulative 707 → 711.
  Bar        SELL-AT-ARA WINS at a horizon if the mean hold value is <= −100 bps with t <= −3 and negative in >= 5 of 7 years, for
             LIQ names (the ones the desk holds). HOLD WINS if >= +100 bps with t >= 3 and positive in >= 5 of 7 years.

READ-ONLY. INGEST_DB_DSN=... PYTHONIOENCODING=utf-8 blackheart-ingest/.venv/Scripts/python research/idx_ara_sell.py [--no-store]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date

import numpy as np
import pandas as pd
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "blackheart-ingest", "src"))

SEED = 20260923
N_TRIALS_BEFORE = 707
HORIZONS = {"H0": 0, "H1": 1, "H5": 5, "H20": 20}
LIQ_RP = 5e9


def tick(px: np.ndarray) -> np.ndarray:
    return np.select([px < 200, px < 500, px < 2000, px < 5000], [1, 2, 5, 10], 25).astype(float)


def ara_limit(prev: np.ndarray) -> np.ndarray:
    return np.select([prev <= 200, prev <= 5000], [0.35, 0.25], 0.20)


def load(dsn: str) -> pd.DataFrame:
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("""SELECT code, trade_date, high, close, value FROM idx.bar WHERE source = 'idx' AND close > 0 ORDER BY code, trade_date""")
        B = pd.DataFrame(cur.fetchall(), columns=["code", "d", "high", "close", "value"])
    for c in ("high", "close", "value"):
        B[c] = pd.to_numeric(B[c], errors="coerce").astype(float)
    B["d"] = pd.to_datetime(B["d"])
    return B


def build(B: pd.DataFrame) -> pd.DataFrame:
    g = B.groupby("code", sort=False)
    B["prev"] = g["close"].shift(1)
    tk = tick(B["prev"].fillna(1).to_numpy())
    B["ara"] = np.floor(B["prev"] * (1 + ara_limit(B["prev"].to_numpy())) / tk) * tk
    B["touch"] = (B["high"] >= B["ara"] - 1e-9) & (B["prev"] >= 50)
    B["lock"] = B["touch"] & (B["close"] >= B["ara"] - 1e-9)
    B["val60"] = g["value"].transform(lambda x: x.rolling(60, min_periods=20).median())
    B["liq"] = B["val60"] >= LIQ_RP
    B["year"] = B["d"].dt.year
    for k, h in HORIZONS.items():
        B[k] = (g["close"].shift(-h) / B["ara"] - 1) * 1e4
    B["lock_next"] = g["lock"].shift(-1)
    # ride: hold while the close stays locked, sell at the first non-locked close (max 10 days)
    ride = np.full(len(B), np.nan)
    codes, lock, close, ara = B["code"].to_numpy(), B["lock"].to_numpy(), B["close"].to_numpy(), B["ara"].to_numpy()
    touch_idx = np.flatnonzero(B["touch"].to_numpy())
    for i in touch_idx:
        j = i
        while j + 1 < len(B) and codes[j + 1] == codes[i] and lock[j] and j - i < 10:
            j += 1
        if codes[j] == codes[i]:
            ride[i] = (close[j] / ara[i] - 1) * 1e4
    B["ride"] = ride
    return B


def tstat(a) -> dict:
    a = np.asarray(a, float)
    a = a[np.isfinite(a)]
    return {"n": int(len(a)), "mean": float(a.mean()) if len(a) else np.nan, "median": float(np.median(a)) if len(a) else np.nan,
            "t": float(a.mean() / a.std(ddof=1) * np.sqrt(len(a))) if len(a) > 2 and a.std(ddof=1) > 0 else np.nan,
            "p_pos": float((a > 0).mean()) if len(a) else np.nan}


def reads(T: pd.DataFrame) -> dict:
    out = {}
    for col in [*HORIZONS, "ride"]:
        r = tstat(T[col])
        r["by_year"] = {int(y): tstat(g[col]) for y, g in T.groupby("year")}
        yrs = [v for v in r["by_year"].values() if v["n"] >= 20]
        r["SELL_WINS"] = bool(r["mean"] <= -100 and np.isfinite(r["t"]) and r["t"] <= -3 and sum(1 for v in yrs if v["mean"] < 0) >= 5)
        r["HOLD_WINS"] = bool(r["mean"] >= 100 and np.isfinite(r["t"]) and r["t"] >= 3 and sum(1 for v in yrs if v["mean"] > 0) >= 5)
        out[col] = r
    return out


def run(dsn: str, out_path: str, store: bool, study_name: str) -> dict:
    t0 = time.time()
    B = build(load(dsn))
    T = B[B["touch"]]
    res: dict = {"desc": {"rows": len(B), "names": int(B["code"].nunique()), "from": str(B["d"].min().date()), "to": str(B["d"].max().date()),
                          "touches": int(len(T)), "locks": int(T["lock"].sum()), "p_lock": float(T["lock"].mean()),
                          "p_lock_next_given_lock": float(T[T["lock"]]["lock_next"].mean()), "liq_touches": int(T["liq"].sum())}}
    res["reads"] = {"ALL": reads(T), "LIQ": reads(T[T["liq"]]), "LOCK": reads(T[T["lock"]]), "FADED": reads(T[~T["lock"]]),
                    "LIQ_LOCK": reads(T[T["liq"] & T["lock"]]), "LIQ_FADED": reads(T[T["liq"] & ~T["lock"]])}
    res["verdict"] = {k: {h: ("SELL" if v[h]["SELL_WINS"] else "HOLD" if v[h]["HOLD_WINS"] else "-") for h in [*HORIZONS, "ride"]} for k, v in res["reads"].items()}
    res["log"] = [f"{time.time() - t0:.0f} s"]
    write_report(res, out_path)
    if store:
        from blackheart_ingest.idx import research_store as rs
        with psycopg.connect(dsn) as conn:
            sid = rs.record_study(conn, study_name, date.today(), params={"trials": list(HORIZONS), "n_trials_cumulative": N_TRIALS_BEFORE + 4, "liq_rp": LIQ_RP, "seed": SEED},
                                 summary=json.loads(json.dumps(res, default=str)), names=[], report_path=out_path, note=f"LIQ verdict {res['verdict']['LIQ']}")
            res["study_id"] = sid
    return res


def f(x, fmt="%+.0f"):
    return (fmt % x) if x is not None and isinstance(x, (int, float, np.floating)) and np.isfinite(x) else "-"


def write_report(res: dict, path: str) -> None:
    d = res["desc"]
    L = [f"# IDX menu 34 — a held name touches ARA: sell at the ARA price, or hold? — {date.today()}", "",
         f"idx.bar {d['from']} → {d['to']}, {d['names']} names; {d['touches']:,} touch days ({d['liq_touches']:,} in liquid names), {d['locks']:,} locked closes "
         f"(P(lock | touch) {d['p_lock']:.2f}; P(locked again next day | lock) {d['p_lock_next_given_lock']:.2f}).",
         f"Value of HOLDING instead of selling at ARA, in bps vs the ARA price (negative = selling at ARA was better). Pre-registered in `research/idx_ara_sell.py`; 4 trials (cumulative {N_TRIALS_BEFORE + 4}).", ""]
    for k, v in res["reads"].items():
        L += [f"## {k}", "", "| horizon | n | mean bps vs ARA | median | t | P(hold > ARA) | by year (mean) | verdict |", "|---|---|---|---|---|---|---|---|"]
        for h, r in v.items():
            by = "; ".join(f"{y}: {f(w['mean'])}" for y, w in r["by_year"].items())
            L.append(f"| {h} | {r['n']:,} | {f(r['mean'])} | {f(r['median'])} | {f(r['t'], '%.1f')} | {f(r['p_pos'] * 100, '%.0f')} % | {by} | {'SELL AT ARA' if r['SELL_WINS'] else 'HOLD' if r['HOLD_WINS'] else '-'} |")
        L.append("")
    L += ["## Reading", "", "- H0 = sold at that day's close instead; H1/H5/H20 = held n more days; ride = held while the close stayed locked, sold at the first",
          "  unlocked close (max 10 days). LIQ = 60-day median value ≥ Rp 5 bn, the names the desk's books hold.",
          "- Bar: SELL wins at ≤ −100 bps, t ≤ −3, negative in ≥ 5 of 7 years; HOLD wins symmetrically.", ""]
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(L))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-store", action="store_true")
    ap.add_argument("--out", default="")
    ap.add_argument("--study-name", default="ara_sell")
    a = ap.parse_args()
    out = a.out or os.path.join(HERE, f"IDX_ARA_SELL_{date.today().isoformat()}.md")
    res = run(os.environ["INGEST_DB_DSN"], out, not a.no_store, a.study_name)
    print(json.dumps({"desc": res["desc"], "verdict": res["verdict"], "study_id": res.get("study_id"), "report": out}, indent=1, default=str))


if __name__ == "__main__":
    main()
