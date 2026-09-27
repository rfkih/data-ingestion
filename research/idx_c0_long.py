#!/usr/bin/env python3
"""IDX menu RB-3 - C0 radar (wide) as deployed, tested back to 2010 (operator 2026-09-27: "bisa nggak di test dari 2010").

The C0 rule and its liquidity cap were designed on 2021-26 IDX data (#403-#408), so 2010-2019 is out of sample for them.
Data before 2020 is the Yahoo .JK cache (research-scratch/idx/*.JK.csv, 450 names that are listed TODAY = survivors only;
closes and volumes are reliable, opens are not and are not used). No quotes and no board history before 2020, so:
  - costs: fees 0.10 % + 0.20 % and a spread proxy of one tick each side at the fill price (floor 0.25 % a side);
  - no board filter; no lot sizes (a percent book: 1.25 % of NAV per name, <= 40 names, idle cash earns 0);
  - band realism kept: no fill on a day up >= 18 %, no sale on a day down >= 6.5 % (the sale slides, up to 10 sessions).
Rule (as deployed, combo_book.c0w_signals / c0w_exits): close >= 1.3 x close 60 sessions ago, close = 250-session high
(>= 200 bars), day return < 18 %, volume > 0, 20-day mean of close x volume in [Rp 1 bn, Rp 50 bn), close >= Rp 50; buy the next
close, strongest attention (20-day / 250-day value) first; sell the close after a close <= 85 % of the entry close or <= 75 %
of the peak close since.
SURVIVORSHIP is MEASURED, not assumed: the same simulator on 2020-01..2026-09 on (a) the Yahoo survivors and (b) idx.bar with the
delisted names; the gap (a - b) is the bias estimate, reported next to the 2010-19 result.

PRE-REGISTERED (1 trial; cumulative 1106 + 1 = 1107). OOS window 2010-01-04 .. 2019-12-30, Yahoo panel.
PASS only if ALL: book CAGR > IHSG's CAGR over the window; book Sharpe >= 0.5; positive in >= 6 of the 10 years; and the
CAGR still above IHSG after subtracting the MEASURED survivorship gap. Reported: by year vs IHSG, per-trade stats, cut-loss share.
READ-ONLY on the DB except one idx.study row (--no-store to skip).
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
YAHOO = os.path.join(ROOT, "research-scratch", "idx")
STUDY, N_BEFORE = "c0_long", 1106
FEE_B, FEE_S, PCT, MAXPOS = 0.0010, 0.0020, 0.0125, 40


def dsn() -> str:
    return os.environ.get("INGEST_DB_DSN") or [ln.split("=", 1)[1].strip() for ln in open(os.path.join(ROOT, "blackheart-ingest", "idx-local.env"))
                                                if ln.startswith("INGEST_DB_DSN=")][0]


def tick(p):
    return np.where(p < 200, 1, np.where(p < 500, 2, np.where(p < 2000, 5, np.where(p < 5000, 10, 25))))


def panel_yahoo():
    jk = pd.read_csv(os.path.join(YAHOO, "_JKSE.csv"), parse_dates=["date"]).set_index("date")["close"].astype(float).sort_index()
    jk = jk[~jk.index.duplicated(keep="last")]
    jk = jk[jk.index >= "2008-01-01"]
    C, V = {}, {}
    for f in sorted(glob.glob(os.path.join(YAHOO, "*.JK.csv"))):
        code = os.path.basename(f).split(".")[0]
        df = pd.read_csv(f, parse_dates=["date"]).set_index("date").sort_index()
        df = df[~df.index.duplicated(keep="last")]
        c, v = pd.to_numeric(df["close"], errors="coerce"), pd.to_numeric(df["volume"], errors="coerce")
        ok = (c > 0) & c.notna()
        C[code], V[code] = c[ok], v[ok].fillna(0)
    C = pd.DataFrame(C).reindex(jk.index)
    V = pd.DataFrame(V).reindex(jk.index)
    return C, C, V, jk                                               # adjusted = raw proxy (Yahoo closes are split-adjusted)


def panel_idx(conn):
    df = pd.DataFrame(conn.execute("""SELECT code, trade_date, close * coalesce(adj_factor, 1), close, volume FROM idx.bar
                                      WHERE source = 'idx' AND close > 0""").fetchall(), columns=["code", "d", "ac", "c", "v"])
    for k in ("ac", "c", "v"):
        df[k] = df[k].astype(float)
    df["d"] = pd.to_datetime(df.d)
    A = df.pivot(index="d", columns="code", values="ac").sort_index()
    R = df.pivot(index="d", columns="code", values="c").sort_index()
    V = df.pivot(index="d", columns="code", values="v").sort_index().fillna(0)
    ix = pd.DataFrame(conn.execute("SELECT trade_date, close FROM idx.index_daily WHERE index_code = 'COMPOSITE'").fetchall(), columns=["d", "c"])
    ix["d"] = pd.to_datetime(ix.d)
    jk = ix.set_index("d").c.astype(float).sort_index().reindex(A.index).ffill()
    return A, R, V, jk


def trades(A, R, V, start):
    """Every C0 flag (as deployed), one position per name; returns (e, j, x, attention, stopped)."""
    value = R * V
    v20 = value.rolling(20, min_periods=15).mean()
    v250 = value.rolling(250, min_periods=200).mean()
    r1 = A / A.shift(1) - 1
    flag = ((A >= 1.3 * A.shift(60)) & (A >= A.rolling(250, min_periods=200).max()) & (r1 < 0.18) & (V > 0)
            & (v20 >= 1e9) & (v20 < 50e9) & (R >= 50)).to_numpy(bool)
    attn = (v20 / v250).to_numpy(float)
    a, raw = A.to_numpy(float), R.to_numpy(float)
    T, N = a.shape
    t0 = int(np.searchsorted(A.index, np.datetime64(pd.Timestamp(start)))) - 1
    out = []
    for j in range(N):
        i = t0
        while i < T - 2:
            if not flag[i, j]:
                i += 1
                continue
            e = i + 1
            while e < min(i + 6, T - 1) and (np.isnan(a[e, j]) or (a[e - 1, j] > 0 and a[e, j] / a[e - 1, j] - 1 >= 0.18)):
                e += 1
            if np.isnan(a[e, j]) or a[e, j] / a[e - 1, j] - 1 >= 0.18:
                i += 1
                continue
            peak, x, stopped = a[e, j], None, False
            for k in range(e + 1, T):
                if np.isnan(a[k, j]):
                    continue
                peak = max(peak, a[k, j])
                if a[k, j] <= 0.85 * a[e, j] or a[k, j] <= 0.75 * peak:
                    stopped = a[k, j] <= 0.85 * a[e, j]
                    x = k + 1
                    while x < T - 1 and (np.isnan(a[x, j]) or (x < k + 11 and a[x - 1, j] > 0 and a[x, j] / a[x - 1, j] - 1 <= -0.065)):
                        x += 1
                    break
            if x is None or x >= T:
                x = T - 1
            while x > e and np.isnan(a[x, j]):
                x -= 1
            out.append((e, j, x, float(attn[i, j]) if np.isfinite(attn[i, j]) else 0.0, stopped))
            i = x + 1
    return out


def book(tr, A, R, start, end=None):
    a, raw = A.to_numpy(float), R.to_numpy(float)
    idx = A.index
    t0 = int(np.searchsorted(idx, np.datetime64(pd.Timestamp(start))))
    t1 = len(idx) - 1 if end is None else int(np.searchsorted(idx, np.datetime64(pd.Timestamp(end)), side="right")) - 1
    half = lambda p: max(float(tick(np.array([p]))[0]) / p, 0.0025)  # noqa: E731
    entries = {}
    for e, j, x, s, st in tr:
        if t0 <= e <= t1:
            entries.setdefault(e, []).append((j, x, s, st))
    nav, cash, held, navs, rets = 1.0, 1.0, {}, [], []
    for t in range(t0, t1 + 1):
        for j in [j for j, p in held.items() if p["x"] <= t]:
            p = held.pop(j)
            px = a[t, j] if np.isfinite(a[t, j]) else p["last"]
            cash += p["sh"] * px * (1 - half(raw[t, j] if np.isfinite(raw[t, j]) else p["raw"]) - FEE_S)
            rets.append((p["sh"] * px * (1 - FEE_S) / p["cost"] - 1, p["st"], idx[p["t"]].year))
        mv = 0.0
        for j, p in held.items():
            if np.isfinite(a[t, j]):
                p["last"] = a[t, j]
            mv += p["sh"] * p["last"]
        nav = cash + mv
        for j, x, s, st in sorted(entries.get(t, []), key=lambda z: -z[2]):
            if j in held or len(held) >= MAXPOS or not np.isfinite(a[t, j]):
                continue
            amt = min(PCT * nav, cash)
            if amt <= 0:
                continue
            px = a[t, j] * (1 + half(raw[t, j]) + FEE_B)
            held[j] = {"sh": amt / px, "last": a[t, j], "x": x, "cost": amt, "st": st, "t": t, "raw": raw[t, j]}
            cash -= amt
        mv = sum(p["sh"] * p["last"] for p in held.values())
        navs.append(cash + mv)
    s = pd.Series(navs, index=idx[t0:t1 + 1])
    r = s.pct_change().fillna(0)
    yrs = len(s) / 244
    by = s.groupby(s.index.year).last()
    prev, years = 1.0, {}
    for y, v in by.items():
        years[int(y)] = float(v / prev - 1)
        prev = float(v)
    tr_df = pd.DataFrame(rets, columns=["ret", "stop", "year"])
    return {"cagr": float(s.iloc[-1] ** (1 / yrs) - 1), "sharpe": float(r.mean() / r.std() * np.sqrt(244)) if r.std() > 0 else 0.0,
            "mdd": float((s / s.cummax() - 1).min()), "by_year": years, "trades": len(tr_df),
            "win": float((tr_df.ret > 0).mean()) if len(tr_df) else None, "avg": float(tr_df.ret.mean()) if len(tr_df) else None,
            "median": float(tr_df.ret.median()) if len(tr_df) else None, "stop_share": float(tr_df.stop.mean()) if len(tr_df) else None,
            "per_year_trades": {int(y): {"n": len(g), "avg": float(g.ret.mean()), "win": float((g.ret > 0).mean()), "stop": float(g.stop.mean())}
                                for y, g in tr_df.groupby("year")}}


def bench(jk, start, end):
    s = jk[(jk.index >= pd.Timestamp(start)) & (jk.index <= pd.Timestamp(end))].dropna()
    by = s.groupby(s.index.year).last()
    prev, years = float(s.iloc[0]), {}
    for y, v in by.items():
        years[int(y)] = float(v / prev - 1)
        prev = float(v)
    return {"cagr": float((s.iloc[-1] / s.iloc[0]) ** (244 / len(s)) - 1), "by_year": years}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-store", action="store_true")
    a = ap.parse_args()
    AY, RY, VY, jkY = panel_yahoo()
    with psycopg.connect(dsn()) as conn:
        AX, RX, VX, jkX = panel_idx(conn)
    res = {}
    trY = trades(AY, RY, VY, "2010-01-04")
    res["Y_2010_2019"] = book(trY, AY, RY, "2010-01-04", "2019-12-30")
    res["Y_2020_2026"] = book(trY, AY, RY, "2020-01-02", None)
    trX = trades(AX, RX, VX, "2020-01-02")
    res["X_2020_2026"] = book(trX, AX, RX, "2020-01-02", None)
    res["X_2022_2026"] = book(trX, AX, RX, "2022-01-03", None)
    res["ihsg_2010_2019"] = bench(jkY, "2010-01-04", "2019-12-30")
    res["ihsg_2020_2026"] = bench(jkX, "2020-01-02", "2026-09-25")
    gap = res["Y_2020_2026"]["cagr"] - res["X_2020_2026"]["cagr"]
    r, ih = res["Y_2010_2019"], res["ihsg_2010_2019"]
    pos = sum(v > 0 for v in r["by_year"].values())
    checks = {"beats_ihsg": r["cagr"] > ih["cagr"], "sharpe": r["sharpe"] >= 0.5, "years": pos >= 6, "after_survivorship": r["cagr"] - gap > ih["cagr"]}
    res["survivorship_gap"] = gap
    res["verdict"] = {"checks": checks, "pass": all(checks.values()), "positive_years": pos}
    for k in ("Y_2010_2019", "Y_2020_2026", "X_2020_2026", "X_2022_2026"):
        v = res[k]
        print(f"{k:12s} CAGR {v['cagr'] * 100:6.1f} % Sharpe {v['sharpe']:.2f} mDD {v['mdd'] * 100:5.1f} % trades {v['trades']} win {v['win'] * 100:.0f} % "
              f"avg {v['avg'] * 100:+.1f} % stop {v['stop_share'] * 100:.0f} %")
    print("IHSG 2010-19 CAGR", round(ih["cagr"] * 100, 1), "| 2020-26", round(res["ihsg_2020_2026"]["cagr"] * 100, 1))
    print("survivorship gap (Yahoo - IDX, 2020-26):", round(gap * 100, 1), "pp/yr")
    print("by year 2010-19 (C0 / IHSG / trades avg / stop):")
    for y in sorted(r["by_year"]):
        pt = r["per_year_trades"].get(y, {})
        print(f"  {y}: {r['by_year'][y] * 100:+6.1f} % / {ih['by_year'].get(y, float('nan')) * 100:+6.1f} % | n {pt.get('n', 0):3d} avg {pt.get('avg', 0) * 100:+6.1f} % "
              f"win {pt.get('win', 0) * 100:3.0f} % stop {pt.get('stop', 0) * 100:3.0f} %")
    print("verdict", json.dumps(res["verdict"]))
    json.dump(res, open(os.path.join(HERE, "IDX_C0_LONG_2026-09-27.json"), "w"), indent=1, default=str)
    if not a.no_store:
        from blackheart_ingest.idx import research_store as rs
        with psycopg.connect(dsn()) as conn:
            sid = rs.record_study(conn, STUDY, date.today(), params={"trials": ["C0_2010_2019"], "n_trials_cumulative": N_BEFORE + 1},
                                  summary=json.loads(json.dumps(res, default=str)), names=[], report_path="research/IDX_C0_LONG_2026-09-27.md")
            print("study id", sid)


if __name__ == "__main__":
    main()
