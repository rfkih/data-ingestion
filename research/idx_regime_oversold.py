#!/usr/bin/env python3
"""IDX menu 23 — re-open the gate on an oversold market (operator, 2026-09-22: "kalau bikin setelah MA turun dari 200 tapi ga harus tunggu di atas 200,
karena pasti ada bottom-nya sebelum naik; ketika sudah jenuh jual di-allow untuk buy").

Menu 22 validated `regime_gate` (no new trend entry while COMPOSITE < MA200) as a drawdown rule and showed where it pays: it waits for the index
to climb back over its average, so it misses the first leg of every rebound (2009: 14 % against 26 % ungated; 2012: 13 % against 20 %). The
operator's fix: while the index is under its average, re-allow entries once the market is oversold — the bottom is usually in before the cross.

PRE-REGISTERED (5 trials; cumulative 445 + 5 = 450). Declared before the run; nothing tuned afterwards. All on `small`, deployed rule otherwise.
Entries are allowed when COMPOSITE >= MA200 at the signal close (as regime_gate) OR when the oversold condition holds, all read on COMPOSITE:
  os_rsi30         RSI14 <= 30 on that day (a narrow window)
  os_rsi30_20d     within 20 trading days after any close with RSI14 <= 30
  os_rsi30_latch   once RSI14 <= 30 has printed since the regime went off, until the next close back above MA200 ("the bottom is in")
  os_bounce5       close >= 1.05 x the 60-day low (a 5 % bounce off the low has happened)
  os_ma50          close >= MA50 (the short trend has turned up under the long one)
References (not trials): ungated rule; regime_gate; random entries + the same allowance mask per arm.
READING RULE (declared): an arm RECOVERS the rebound if ALL hold: CAGR >= regime_gate + 2 points; max drawdown <= 25 %; Sharpe >= regime_gate - 0.05;
  >= 150 trades. Money rule as menu 6. Robustness (descriptive): the same arms on `small` 2005-2019 with the JKSE, and the 2009 calendar year alone.
READ-ONLY. INGEST_DB_DSN=... PYTHONIOENCODING=utf-8 blackheart-ingest/.venv/Scripts/python research/idx_regime_oversold.py [--no-store]
"""
from __future__ import annotations

import argparse
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
import idx_beyond as B  # noqa: E402
import idx_regime_validate as V  # noqa: E402
import idx_swing2 as S  # noqa: E402

N_BEFORE = 445
K = B.K
SEED = 20260923
ARMS = ["os_rsi30", "os_rsi30_20d", "os_rsi30_latch", "os_bounce5", "os_ma50"]
N_TRIALS = N_BEFORE + len(ARMS)


def rsi(s: pd.Series, n=14) -> pd.Series:
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def masks(comp: pd.Series, dates) -> dict[str, np.ndarray]:
    """allow[t] = True when an entry signalled at close t may be taken."""
    c = comp.reindex(dates).ffill()
    ma200 = c.rolling(200, min_periods=200).mean()
    on = (c >= ma200).to_numpy()
    off = ~on
    r = rsi(c).to_numpy(float)
    os_day = np.nan_to_num(r, nan=100) <= 30
    win20 = pd.Series(os_day).rolling(20, min_periods=1).max().to_numpy() > 0
    latch = np.zeros(len(c), bool)
    armed = False
    for i in range(len(c)):
        if on[i]:
            armed = False
        elif os_day[i]:
            armed = True
        latch[i] = armed
    lo60 = c.rolling(60, min_periods=60).min()
    bounce = (c >= 1.05 * lo60).to_numpy()
    ma50 = c.rolling(50, min_periods=50).mean()
    above50 = (c >= ma50).to_numpy()
    return {"gate": on, "os_rsi30": on | (off & os_day), "os_rsi30_20d": on | (off & win20), "os_rsi30_latch": on | (off & latch),
            "os_bounce5": on | (off & bounce), "os_ma50": on | (off & above50)}


def allow_size(allow):
    return lambda t, j: (1.0 / K) if allow[t] else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-store", action="store_true")
    args = ap.parse_args()
    dsn = os.environ["INGEST_DB_DSN"]
    P, unis, comp, Hp, Lp, sectors, brent = B.load_all(dsn, os.environ.get("IDX_BEYOND_CACHE"))
    c_in, c_out = S.costs(P)
    adj = P["adj"]
    dates = adj.index
    A, H = adj.to_numpy(float), Hp.to_numpy(float)
    small = (unis["LIQ"] & ~unis["BLUE"]).to_numpy(bool)
    entry, score, trail10 = V.entry_and_rule(P, Hp, Lp, (60, 0.10, 1.5))
    M = masks(comp, dates)
    res, rnd = {}, {}
    ref, _, _ = V.run(A, H, c_in, c_out, entry, score, trail10, small, lambda t, j: 1.0 / K, dates, N_TRIALS)
    gate, _, _ = V.run(A, H, c_in, c_out, entry, score, trail10, small, allow_size(M["gate"]), dates, N_TRIALS)
    print(f"ref cagr={ref['cagr'] * 100:+.1f}% sharpe={ref['sharpe']:.2f} mdd={ref['mdd'] * 100:.0f}% | gate cagr={gate['cagr'] * 100:+.1f}% sharpe={gate['sharpe']:.2f} mdd={gate['mdd'] * 100:.0f}%", flush=True)
    for i, arm in enumerate(ARMS):
        s, _, _ = V.run(A, H, c_in, c_out, entry, score, trail10, small, allow_size(M[arm]), dates, N_TRIALS)
        rn, _, _ = V.run(A, H, c_in, c_out, None, None, trail10, small, allow_size(M[arm]), dates, N_TRIALS, rng=np.random.default_rng(SEED + i))
        why = []
        if s["cagr"] < gate["cagr"] + 0.02:
            why.append("cagr<gate+2")
        if s["mdd"] < -0.25:
            why.append("mdd>25%")
        if s["sharpe"] < gate["sharpe"] - 0.05:
            why.append("sharpe<gate-0.05")
        if s["n"] < 150:
            why.append("n<150")
        s["read"] = "RECOVERS" if not why else "no: " + ",".join(why)
        s["money"] = B.money_read(s, rn)
        s["allow_share_off"] = float((M[arm] & ~M["gate"]).sum() / max((~M["gate"]).sum(), 1))
        res[arm], rnd[arm] = s, rn
        print(f"{arm:15s} allow-under-MA200={s['allow_share_off'] * 100:3.0f}% n={s['n']:4d} hit={s['hit'] * 100:3.0f}% net={s['avg_net'] * 100:+5.2f}% cagr={s['cagr'] * 100:+5.1f}% "
              f"sharpe={s['sharpe']:.2f} mdd={s['mdd'] * 100:.0f}% {s['read']} / {s['money']} (rnd {rn['sharpe']:.2f})", flush=True)

    # 2005-2019 on the Yahoo survivors file
    import idx_trend_2008 as Y
    Py, jk = Y.load_yahoo()
    ya, yv, yh, yl = Py["close"], Py["volume"], Py["high"], Py["low"]
    yd = ya.index
    YA, YH = ya.to_numpy(float), yh.to_numpy(float)
    yc_in = np.full(YA.shape, Y.HALF_SPREAD + S.FEE_BUY)
    yc_out = np.full(YA.shape, Y.HALF_SPREAD + S.FEE_SELL)
    ye, ys, yrule = V.entry_and_rule({"adj": ya, "volume": yv}, yh, yl, (60, 0.10, 1.5))
    v60 = (ya * yv).rolling(60, min_periods=60).median()
    yliq = (v60 >= S.LIQ) & (ya >= S.MIN_PRICE) & (yv > 0) & ya.notna()
    yblue = yliq & (v60 >= S.BLUE_LIQ) & (ya >= S.BLUE_PRICE)
    lo, hi = yd.searchsorted(pd.Timestamp("2005-01-01")), yd.searchsorted(pd.Timestamp("2020-01-01"))
    win = np.zeros(len(yd), bool)
    win[lo:hi] = True
    ysmall = (yliq & ~yblue).to_numpy(bool) & win[:, None]
    YM = masks(jk, yd)
    yres = {}
    for name in ["ungated", "gate", *ARMS]:
        size = (lambda t, j: 1.0 / K) if name == "ungated" else allow_size(YM[name])
        s, _, _ = V.run(YA, YH, yc_in, yc_out, ye, ys, yrule, ysmall, size, yd, N_TRIALS, lo=lo, hi=hi)
        yres[name] = s
        print(f"2005-19 {name:15s} cagr={s['cagr'] * 100:+5.1f}% sharpe={s['sharpe']:.2f} mdd={s['mdd'] * 100:.0f}% 2009={s['years'].get(2009, 0) * 100:+.0f}% 2012={s['years'].get(2012, 0) * 100:+.0f}%", flush=True)

    n_rec = sum(1 for s in res.values() if s["read"] == "RECOVERS")
    L = [f"# IDX menu 23 — re-open the gate on an oversold market — {date.today()} — {len(ARMS)} trials, cumulative N = {N_TRIALS}", "",
         "Entries allowed when COMPOSITE >= MA200 at the signal close OR the oversold condition holds; `small`, deployed rule otherwise. "
         "allow-under = share of regime-off days on which the arm allows entries.", "",
         "| arm | allow-under | trades | hit | avg net | t | CAGR | Sharpe | mDD | years | read / money |", "|---|---|---|---|---|---|---|---|---|---|---|"]

    def row(label, s, extra, allow=""):
        return (f"| {label} | {allow} | {s['n']} | {s['hit'] * 100:.0f} % | {s['avg_net'] * 100:+.2f} % | {s['tstat']:.1f} | {s['cagr'] * 100:+.1f} % | {s['sharpe']:.2f} | "
                f"{s['mdd'] * 100:.0f} % | {V.yrs(s['years'])} | {extra} |")
    L.append(row("ungated (deployed)", ref, "reference", "100 %"))
    L.append(row("regime_gate", gate, "reference", "0 %"))
    for arm in ARMS:
        L.append(row(arm, res[arm], f"{res[arm]['read']} / {res[arm]['money']} (rnd Sharpe {rnd[arm]['sharpe']:.2f})", f"{res[arm]['allow_share_off'] * 100:.0f} %"))
    L += ["", f"Reading rule applied as declared: {n_rec} of {len(ARMS)} recover the rebound.", "", "## 2005-2019 (`small`, Yahoo survivors file, JKSE regime)", "",
          "| arm | trades | hit | avg net | t | CAGR | Sharpe | mDD | years | 2009 | 2012 |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, s in yres.items():
        L.append(f"| {name} | {s['n']} | {s['hit'] * 100:.0f} % | {s['avg_net'] * 100:+.2f} % | {s['tstat']:.1f} | {s['cagr'] * 100:+.1f} % | {s['sharpe']:.2f} | {s['mdd'] * 100:.0f} % | "
                 f"{V.yrs(s['years'])} | {s['years'].get(2009, 0) * 100:+.0f} % | {s['years'].get(2012, 0) * 100:+.0f} % |")
    path = os.path.join(HERE, f"IDX_REGIME_OVERSOLD_{date.today().isoformat()}.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    print("\n".join(L))
    print("wrote", path)
    if not args.no_store:
        from blackheart_ingest.idx import research_store as rs
        with psycopg.connect(dsn) as conn:
            sid = rs.record_study(conn, "regime_gate_oversold", dates[-1].date(), params={"trials": ARMS, "n_trials_cumulative": N_TRIALS, "seed": SEED},
                                  summary=json.loads(json.dumps({"ref": ref, "gate": gate, "res": res, "random": rnd, "yahoo": yres}, default=str)), names=[],
                                  report_path=path, note=f"{n_rec} of {len(ARMS)} recover the rebound")
            print(f"study #{sid} stored")


if __name__ == "__main__":
    main()
