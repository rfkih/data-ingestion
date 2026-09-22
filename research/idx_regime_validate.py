#!/usr/bin/env python3
"""IDX menu 22 — validating `regime_gate` (operator, 2026-09-22: "coba validasi strategi ini sebaik mungkin").

The candidate (menu 21 follow-up A3, study #62): the deployed trend rule (60-day high, > MA200, volume >= 1.5x, K = 10, trail 10 %) with ONE added
condition — no NEW entry while the COMPOSITE closes under its 200-day average at the signal close; held names run to their trailing stop.
On `small` 2020-26: +32.1 %/yr, Sharpe 1.54, mDD -18 % against the deployed 29.5 % / 1.31 / -30 %. The aim here is to break it.

PRE-REGISTERED (12 trials; cumulative 433 + 12 = 445; V3-V6 are descriptive, not trials). Declared before the run; nothing tuned afterwards.
  V1 Regime neighbours (6 trials, `small`): ma100, ma150, ma250 (the average's window); ma200_buf (off when COMPOSITE < 0.98 x MA200, on again only
     above 1.02 x MA200 — hysteresis); lq45_ma200 (LQ45 instead of COMPOSITE); breadth50 (off when fewer than 50 % of the LIQ names close above
     their own 200-day average). ROBUST if >= 4 of 6 keep Sharpe >= the ungated rule + 0.10 AND a shallower max drawdown.
  V2 Entry-rule neighbours (5 trials, `small`): the menu-7 neighbours trail12, trail15, hi40, hi90, vol2, each run ungated and gated (MA200 on
     COMPOSITE). ADDITIVE if >= 4 of 5 gated arms beat their ungated twin by >= 0.10 Sharpe with a shallower max drawdown.
  V7 Large caps (1 trial): the gate on BLUE — to explain why LIQ did not improve. Read against its ungated twin.
  V3 Time blocks (descriptive): IDX 2020-01 -> 2022-12 and 2023-01 -> 2026-09; Yahoo survivors file 2005-09, 2010-14, 2015-19; rolling 500-day
     windows: the share of windows where the gated Sharpe >= the ungated one, and the median Sharpe difference.
  V4 Placebo (descriptive, decisive): 200 circular shifts of the real regime series (same on/off structure, wrong dates) -> distribution of the gated
     book's Sharpe, CAGR and mDD. The signal carries information only if the real gate sits at or above the 95th percentile on Sharpe and at or
     below the 5th percentile on drawdown depth. Also a lagged regime (10 and 20 trading days late) to see how much timing matters.
  V5 Execution (descriptive): entries one day later (signal treated as one day old) and costs x 1.5.
  V6 Attribution (descriptive): in the UNGATED book, trades entered with the regime off vs on: n, hit, avg net, median, and their share of the
     losses inside the deepest drawdown.
VALIDATION RULE (declared): regime_gate is VALIDATED if V1 ROBUST, V2 ADDITIVE, the placebo test passes on Sharpe, the gate keeps Sharpe >= the
  ungated rule in >= 4 of the 5 time blocks, and V6 shows regime-off entries with a lower average net than regime-on entries. Anything less is
  recorded as PARTIAL with the failing checks named; a placebo failure alone is FRAGILE.
READ-ONLY. INGEST_DB_DSN=... PYTHONIOENCODING=utf-8 blackheart-ingest/.venv/Scripts/python research/idx_regime_validate.py [--placebo 200] [--no-store]
"""
from __future__ import annotations

import argparse
import json
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
import idx_beyond as B  # noqa: E402
import idx_exit as E  # noqa: E402
import idx_swing2 as S  # noqa: E402

K = B.K
SEED = 20260922
V2 = {"trail12": (60, 0.12, 1.5), "trail15": (60, 0.15, 1.5), "hi40": (40, 0.10, 1.5), "hi90": (90, 0.10, 1.5), "vol2": (60, 0.10, 2.0)}


def off_from(series: pd.Series, dates, n=200, buf=0.0) -> np.ndarray:
    c = series.reindex(dates).ffill()
    ma = c.rolling(n, min_periods=n).mean()
    if buf <= 0:
        return (c < ma).to_numpy()
    lo, hi = (c < (1 - buf) * ma).to_numpy(), (c > (1 + buf) * ma).to_numpy()
    out = np.zeros(len(c), bool)
    state = False
    for i in range(len(c)):
        if lo[i]:
            state = True
        elif hi[i]:
            state = False
        out[i] = state
    return out


def allow_mask(variant: str, series: pd.Series, dates, short=50, long=200) -> np.ndarray:
    """allow[t] = an entry signalled at close t may be taken. gate: close >= MA(long). ma50: close >= MA(long) OR close >= MA(short)."""
    c = series.reindex(dates).ffill()
    on_long = (c >= c.rolling(long, min_periods=long).mean()).to_numpy()
    if variant == "gate":
        return on_long
    return on_long | (c >= c.rolling(short, min_periods=short).mean()).to_numpy()


def neighbours(variant: str, comp: pd.Series, lq45: pd.Series, dates, liq_above_share: np.ndarray) -> dict[str, np.ndarray]:
    """Regime neighbours as OFF masks (entries blocked)."""
    if variant == "gate":
        return {"ma100": off_from(comp, dates, 100), "ma150": off_from(comp, dates, 150), "ma250": off_from(comp, dates, 250),
                "ma200_buf": off_from(comp, dates, 200, 0.02), "lq45_ma200": off_from(lq45, dates, 200), "breadth50": np.nan_to_num(liq_above_share, nan=1.0) < 0.5}
    return {"short30": ~allow_mask("ma50", comp, dates, 30, 200), "short75": ~allow_mask("ma50", comp, dates, 75, 200), "short100": ~allow_mask("ma50", comp, dates, 100, 200),
            "long150": ~allow_mask("ma50", comp, dates, 50, 150), "long250": ~allow_mask("ma50", comp, dates, 50, 250), "lq45_50_200": ~allow_mask("ma50", lq45, dates, 50, 200)}


def entry_and_rule(P, Hp, Lp, lead):
    adj, vol = P["adj"], P["volume"]
    A = adj.to_numpy(float)
    ma200 = adj.rolling(200, min_periods=200).mean()
    vr = vol / vol.rolling(20, min_periods=20).median()
    hi = adj.rolling(lead[0], min_periods=lead[0]).max()
    entry = ((adj >= hi) & (adj > ma200) & (vr >= lead[2])).to_numpy(bool)
    x = lead[1]
    rule = lambda t, j, p: 1.0 if A[t, j] <= (1 - x) * p["peak"] else 0  # noqa: E731
    return entry, vr.to_numpy(float), rule


def gate_size(off):
    return lambda t, j: 0.0 if off[t] else (1.0 / K)


def run(A, H, c_in, c_out, entry, score, rule, uni, size, dates, n_trials, rng=None, lo=None, hi=None):
    R, tr, open_ = B.run_book_sized(A, H, c_in, c_out, None if rng is not None else entry, None if rng is not None else score, rule, uni, size, rng=rng)
    if lo is not None:
        st = E.stats(R.iloc[lo:hi].reset_index(drop=True), [x for x in tr if lo <= x[0] < hi], dates[lo:hi], n_trials)
    else:
        st = E.stats(R.copy(), tr, dates, n_trials)
    st["open"] = len(open_)
    return st, R, tr


def cmp_read(s, ref, dsh=0.10):
    ok = s["sharpe"] >= ref["sharpe"] + dsh and s["mdd"] > ref["mdd"]
    return "PASS" if ok else "fail: " + ",".join(w for w, c in (("sharpe", s["sharpe"] < ref["sharpe"] + dsh), ("mdd", s["mdd"] <= ref["mdd"])) if c)


def yrs(d):
    return " ".join(f"{y % 100:02d}:{v * 100:+.0f}" for y, v in sorted(d.items()))


def row(label, s, extra):
    return (f"| {label} | {s['n']} | {s['hit'] * 100:.0f} % | {s['avg_net'] * 100:+.2f} % | {s['tstat']:.1f} | {s['cagr'] * 100:+.1f} % | {s['sharpe']:.2f} | "
            f"{s['mdd'] * 100:.0f} % | {yrs(s['years'])} | {extra} |")


HDR = ["| arm | trades | hit | avg net | t | CAGR | Sharpe | mDD | years | read |", "|---|---|---|---|---|---|---|---|---|---|"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--placebo", type=int, default=200)
    ap.add_argument("--no-store", action="store_true")
    ap.add_argument("--variant", default="gate", choices=["gate", "ma50"], help="gate = no entry under MA200; ma50 = also allowed when COMPOSITE >= MA50")
    args = ap.parse_args()
    variant = args.variant
    n_before = {"gate": 433, "ma50": 450}[variant]
    N_TRIALS = n_before + 12
    dsn = os.environ["INGEST_DB_DSN"]
    P, unis, comp, Hp, Lp, sectors, brent = B.load_all(dsn, os.environ.get("IDX_BEYOND_CACHE"))
    with psycopg.connect(dsn) as conn:
        lq = pd.read_sql("SELECT trade_date, close FROM idx.index_daily WHERE index_code = 'LQ45' ORDER BY 1", conn)
    lq["trade_date"] = pd.to_datetime(lq["trade_date"])
    lq45 = lq.set_index("trade_date")["close"].astype(float)
    c_in, c_out = S.costs(P)
    adj = P["adj"]
    dates = adj.index
    A, H = adj.to_numpy(float), Hp.to_numpy(float)
    small = (unis["LIQ"] & ~unis["BLUE"]).to_numpy(bool)
    blue = unis["BLUE"].to_numpy(bool)
    liq = unis["LIQ"].to_numpy(bool)
    entry, score, trail10 = entry_and_rule(P, Hp, Lp, (60, 0.10, 1.5))
    off = ~allow_mask(variant, comp, dates)
    out = {"variant": variant}

    # reference and the candidate
    ref, R_ref, tr_ref = run(A, H, c_in, c_out, entry, score, trail10, small, lambda t, j: 1.0 / K, dates, N_TRIALS)
    gate, R_gate, tr_gate = run(A, H, c_in, c_out, entry, score, trail10, small, gate_size(off), dates, N_TRIALS)
    print(f"ref  cagr={ref['cagr'] * 100:+.1f}% sharpe={ref['sharpe']:.2f} mdd={ref['mdd'] * 100:.0f}% | {variant} cagr={gate['cagr'] * 100:+.1f}% sharpe={gate['sharpe']:.2f} mdd={gate['mdd'] * 100:.0f}%", flush=True)
    out["ref"], out["gate"] = ref, gate
    if variant != "gate":
        out["plain_gate"], _, _ = run(A, H, c_in, c_out, entry, score, trail10, small, gate_size(~allow_mask("gate", comp, dates)), dates, N_TRIALS)

    # V1 regime neighbours
    above = (adj > adj.rolling(200, min_periods=200).mean()).to_numpy(bool)
    breadth = np.where(liq.sum(axis=1) > 0, (above & liq).sum(axis=1) / np.maximum(liq.sum(axis=1), 1), np.nan)
    offs = neighbours(variant, comp, lq45, dates, breadth)
    V1 = list(offs)
    v1 = {}
    for i, k in enumerate(V1):
        s, _, _ = run(A, H, c_in, c_out, entry, score, trail10, small, gate_size(offs[k]), dates, N_TRIALS)
        rn, _, _ = run(A, H, c_in, c_out, None, None, trail10, small, gate_size(offs[k]), dates, N_TRIALS, rng=np.random.default_rng(SEED + i))
        s["read"] = cmp_read(s, ref)
        s["money"] = B.money_read(s, rn)
        s["off_share"] = float(offs[k].mean())
        v1[k] = s
        print(f"V1 {k:11s} off={s['off_share'] * 100:3.0f}% n={s['n']:4d} cagr={s['cagr'] * 100:+5.1f}% sharpe={s['sharpe']:.2f} mdd={s['mdd'] * 100:.0f}% {s['read']} / {s['money']}", flush=True)
    v1_pass = sum(1 for s in v1.values() if s["read"] == "PASS")
    out["V1"] = {"res": v1, "pass": v1_pass, "verdict": "ROBUST" if v1_pass >= 4 else "FRAGILE"}

    # V2 entry-rule neighbours, ungated vs gated
    v2 = {}
    for i, (k, lead) in enumerate(V2.items()):
        e2, sc2, rule2 = entry_and_rule(P, Hp, Lp, lead)
        u, _, _ = run(A, H, c_in, c_out, e2, sc2, rule2, small, lambda t, j: 1.0 / K, dates, N_TRIALS)
        g, _, _ = run(A, H, c_in, c_out, e2, sc2, rule2, small, gate_size(off), dates, N_TRIALS)
        rn, _, _ = run(A, H, c_in, c_out, None, None, rule2, small, gate_size(off), dates, N_TRIALS, rng=np.random.default_rng(SEED + 50 + i))
        g["read"] = cmp_read(g, u)
        g["money"] = B.money_read(g, rn)
        v2[k] = {"ungated": u, "gated": g}
        print(f"V2 {k:8s} ungated sharpe={u['sharpe']:.2f} mdd={u['mdd'] * 100:.0f}% cagr={u['cagr'] * 100:+.1f}% | gated sharpe={g['sharpe']:.2f} mdd={g['mdd'] * 100:.0f}% cagr={g['cagr'] * 100:+.1f}% {g['read']} / {g['money']}", flush=True)
    v2_pass = sum(1 for v in v2.values() if v["gated"]["read"] == "PASS")
    out["V2"] = {"res": v2, "pass": v2_pass, "verdict": "ADDITIVE" if v2_pass >= 4 else "NOT ADDITIVE"}

    # V7 large caps
    ub, _, _ = run(A, H, c_in, c_out, entry, score, trail10, blue, lambda t, j: 1.0 / K, dates, N_TRIALS)
    gb, _, _ = run(A, H, c_in, c_out, entry, score, trail10, blue, gate_size(off), dates, N_TRIALS)
    rnb, _, _ = run(A, H, c_in, c_out, None, None, trail10, blue, gate_size(off), dates, N_TRIALS, rng=np.random.default_rng(SEED + 77))
    gb["read"] = cmp_read(gb, ub)
    gb["money"] = B.money_read(gb, rnb)
    out["V7"] = {"ungated": ub, "gated": gb}
    print(f"V7 BLUE ungated sharpe={ub['sharpe']:.2f} mdd={ub['mdd'] * 100:.0f}% cagr={ub['cagr'] * 100:+.1f}% | gated sharpe={gb['sharpe']:.2f} mdd={gb['mdd'] * 100:.0f}% cagr={gb['cagr'] * 100:+.1f}% {gb['read']}", flush=True)

    # V3 time blocks: IDX
    def block(R, tr, a, b):
        lo, hi = dates.searchsorted(pd.Timestamp(a)), dates.searchsorted(pd.Timestamp(b))
        return E.stats(R.iloc[lo:hi].reset_index(drop=True), [x for x in tr if lo <= x[0] < hi], dates[lo:hi], N_TRIALS)
    blocks = {}
    for name, (a, b) in {"2020-22": ("2020-01-01", "2023-01-01"), "2023-26": ("2023-01-01", "2026-12-31")}.items():
        blocks[name] = {"ref": block(R_ref, tr_ref, a, b), "gate": block(R_gate, tr_gate, a, b)}
    # Yahoo file blocks
    import idx_trend_2008 as Y
    Py, jk = Y.load_yahoo()
    ya, yv, yh, yl = Py["close"], Py["volume"], Py["high"], Py["low"]
    yd = ya.index
    YA, YH = ya.to_numpy(float), yh.to_numpy(float)
    yc_in = np.full(YA.shape, Y.HALF_SPREAD + S.FEE_BUY)
    yc_out = np.full(YA.shape, Y.HALF_SPREAD + S.FEE_SELL)
    ye, ys, yrule = entry_and_rule({"adj": ya, "volume": yv}, yh, yl, (60, 0.10, 1.5))
    v60 = (ya * yv).rolling(60, min_periods=60).median()
    yliq = (v60 >= S.LIQ) & (ya >= S.MIN_PRICE) & (yv > 0) & ya.notna()
    yblue = yliq & (v60 >= S.BLUE_LIQ) & (ya >= S.BLUE_PRICE)
    ylo, yhi = yd.searchsorted(pd.Timestamp("2005-01-01")), yd.searchsorted(pd.Timestamp("2020-01-01"))
    win = np.zeros(len(yd), bool)
    win[ylo:yhi] = True
    ysmall = (yliq & ~yblue).to_numpy(bool) & win[:, None]
    yoff = ~allow_mask(variant, jk, yd)
    _, YR_ref, ytr_ref = run(YA, YH, yc_in, yc_out, ye, ys, yrule, ysmall, lambda t, j: 1.0 / K, yd, N_TRIALS)
    _, YR_gate, ytr_gate = run(YA, YH, yc_in, yc_out, ye, ys, yrule, ysmall, gate_size(yoff), yd, N_TRIALS)

    def yblock(R, tr, a, b):
        lo, hi = yd.searchsorted(pd.Timestamp(a)), yd.searchsorted(pd.Timestamp(b))
        return E.stats(R.iloc[lo:hi].reset_index(drop=True), [x for x in tr if lo <= x[0] < hi], yd[lo:hi], N_TRIALS)
    for name, (a, b) in {"2005-09": ("2005-01-01", "2010-01-01"), "2010-14": ("2010-01-01", "2015-01-01"), "2015-19": ("2015-01-01", "2020-01-01")}.items():
        blocks[name] = {"ref": yblock(YR_ref, ytr_ref, a, b), "gate": yblock(YR_gate, ytr_gate, a, b)}
    for k, v in blocks.items():
        print(f"V3 {k}: ref cagr={v['ref']['cagr'] * 100:+.1f}% sharpe={v['ref']['sharpe']:.2f} mdd={v['ref']['mdd'] * 100:.0f}% | gate cagr={v['gate']['cagr'] * 100:+.1f}% sharpe={v['gate']['sharpe']:.2f} mdd={v['gate']['mdd'] * 100:.0f}%", flush=True)
    blocks_pass = sum(1 for v in blocks.values() if v["gate"]["sharpe"] >= v["ref"]["sharpe"])

    def rolling_cmp(Rr, Rg, w=500):
        rr, rg = Rr.to_numpy(float), Rg.to_numpy(float)
        diffs, wins, dds = [], 0, 0
        for s0 in range(0, len(rr) - w, 20):
            a, b = rr[s0:s0 + w], rg[s0:s0 + w]
            sa = a.mean() / a.std() * math.sqrt(250) if a.std() > 0 else 0
            sb = b.mean() / b.std() * math.sqrt(250) if b.std() > 0 else 0
            diffs.append(sb - sa)
            wins += sb >= sa
            ea, eb = np.cumprod(1 + a), np.cumprod(1 + b)
            dds += (eb / np.maximum.accumulate(eb) - 1).min() >= (ea / np.maximum.accumulate(ea) - 1).min()
        n = len(diffs)
        return {"windows": n, "share_sharpe_ge": wins / n if n else 0, "share_mdd_shallower": dds / n if n else 0, "median_dsharpe": float(np.median(diffs)) if n else 0}
    roll = {"idx": rolling_cmp(R_ref, R_gate), "yahoo": rolling_cmp(YR_ref.iloc[ylo:yhi], YR_gate.iloc[ylo:yhi])}
    print(f"V3 rolling IDX: {roll['idx']} | Yahoo: {roll['yahoo']}", flush=True)
    out["V3"] = {"blocks": blocks, "blocks_pass": blocks_pass, "rolling": roll}

    # V4 placebo: circular shifts of the real regime series
    rng = np.random.default_rng(SEED)
    T = len(dates)
    pl = []
    for i in range(args.placebo):
        k = int(rng.integers(250, T - 250))
        s, _, _ = run(A, H, c_in, c_out, entry, score, trail10, small, gate_size(np.roll(off, k)), dates, N_TRIALS)
        pl.append((s["sharpe"], s["cagr"], s["mdd"]))
        if (i + 1) % 25 == 0:
            print(f"V4 placebo {i + 1}/{args.placebo}", flush=True)
    pl = np.array(pl)
    pct = {"sharpe": float((pl[:, 0] < gate["sharpe"]).mean() * 100), "cagr": float((pl[:, 1] < gate["cagr"]).mean() * 100), "mdd": float((pl[:, 2] < gate["mdd"]).mean() * 100)}
    lag = {}
    for d in (10, 20):
        s, _, _ = run(A, H, c_in, c_out, entry, score, trail10, small, gate_size(np.r_[np.zeros(d, bool), off[:-d]]), dates, N_TRIALS)
        lag[d] = s
    out["V4"] = {"n": int(args.placebo), "placebo_median": {"sharpe": float(np.median(pl[:, 0])), "cagr": float(np.median(pl[:, 1])), "mdd": float(np.median(pl[:, 2]))},
                 "placebo_p95": {"sharpe": float(np.percentile(pl[:, 0], 95)), "cagr": float(np.percentile(pl[:, 1], 95))}, "placebo_mdd_p5": float(np.percentile(pl[:, 2], 5)),
                 "percentile_of_real": pct, "pass_sharpe": pct["sharpe"] >= 95, "pass_mdd": float((pl[:, 2] > gate["mdd"]).mean() * 100) >= 95, "lag": lag}
    print(f"V4 real gate sharpe {gate['sharpe']:.2f} at pct {pct['sharpe']:.0f} (placebo median {out['V4']['placebo_median']['sharpe']:.2f}, p95 {out['V4']['placebo_p95']['sharpe']:.2f}); "
          f"mdd {gate['mdd'] * 100:.0f}% (placebo median {out['V4']['placebo_median']['mdd'] * 100:.0f}%, p5 {out['V4']['placebo_mdd_p5'] * 100:.0f}%) | lag10 sharpe {lag[10]['sharpe']:.2f} lag20 {lag[20]['sharpe']:.2f}", flush=True)

    # V5 execution
    e_late = np.zeros_like(entry)
    e_late[1:] = entry[:-1]
    s_late, _, _ = run(A, H, c_in, c_out, e_late, score, trail10, small, gate_size(off), dates, N_TRIALS)
    r_late, _, _ = run(A, H, c_in, c_out, e_late, score, trail10, small, lambda t, j: 1.0 / K, dates, N_TRIALS)
    s_cost, _, _ = run(A, H, c_in * 1.5, c_out * 1.5, entry, score, trail10, small, gate_size(off), dates, N_TRIALS)
    r_cost, _, _ = run(A, H, c_in * 1.5, c_out * 1.5, entry, score, trail10, small, lambda t, j: 1.0 / K, dates, N_TRIALS)
    out["V5"] = {"late": {"ref": r_late, "gate": s_late}, "cost15": {"ref": r_cost, "gate": s_cost}}
    print(f"V5 late: ref sharpe={r_late['sharpe']:.2f} mdd={r_late['mdd'] * 100:.0f}% | gate sharpe={s_late['sharpe']:.2f} mdd={s_late['mdd'] * 100:.0f}% cagr={s_late['cagr'] * 100:+.1f}%; "
          f"cost x1.5: ref sharpe={r_cost['sharpe']:.2f} | gate sharpe={s_cost['sharpe']:.2f} cagr={s_cost['cagr'] * 100:+.1f}%", flush=True)

    # V6 attribution in the ungated book
    nets_on = np.array([x[3] for x in tr_ref if not off[x[0] - 1]])
    nets_off = np.array([x[3] for x in tr_ref if off[x[0] - 1]])
    eq = (1 + R_ref.to_numpy(float)).cumprod()
    dd = eq / np.maximum.accumulate(eq) - 1
    trough = int(np.argmin(dd))
    peak = int(np.argmax(eq[:trough + 1]))
    in_dd = [x for x in tr_ref if peak <= x[0] <= trough]
    loss_dd = sum(min(0.0, x[3]) for x in in_dd)
    loss_dd_off = sum(min(0.0, x[3]) for x in in_dd if off[x[0] - 1])

    def grp(v):
        return {"n": int(len(v)), "hit": float((v > 0).mean()) if len(v) else 0.0, "avg_net": float(v.mean()) if len(v) else 0.0, "median": float(np.median(v)) if len(v) else 0.0,
                "t": float(v.mean() / v.std(ddof=1) * math.sqrt(len(v))) if len(v) > 2 and v.std(ddof=1) > 0 else 0.0}
    out["V6"] = {"on": grp(nets_on), "off": grp(nets_off), "dd_window": [str(dates[peak].date()), str(dates[trough].date())], "dd_trades": len(in_dd),
                 "loss_share_off": float(loss_dd_off / loss_dd) if loss_dd < 0 else 0.0, "off_share_days": float(off.mean())}
    print(f"V6 on: {out['V6']['on']} | off: {out['V6']['off']} | dd {out['V6']['dd_window']} trades {len(in_dd)} loss share from off-entries {out['V6']['loss_share_off'] * 100:.0f}%", flush=True)

    # verdict
    checks = {"V1 robust": out["V1"]["verdict"] == "ROBUST", "V2 additive": out["V2"]["verdict"] == "ADDITIVE", "placebo sharpe": out["V4"]["pass_sharpe"],
              "blocks >= 4/5": blocks_pass >= 4, "off-entries worse": out["V6"]["off"]["avg_net"] < out["V6"]["on"]["avg_net"]}
    failed = [k for k, v in checks.items() if not v]
    verdict = "VALIDATED" if not failed else ("FRAGILE" if "placebo sharpe" in failed else "PARTIAL: " + ", ".join(failed))
    out["checks"], out["verdict"] = checks, verdict
    print("VERDICT", verdict, checks, flush=True)

    # report
    cand_name = "regime_gate" if variant == "gate" else "os_ma50"
    cand_desc = ("no new entry while COMPOSITE < MA200 (signal close)" if variant == "gate"
                 else "no new entry while COMPOSITE < MA200 unless COMPOSITE >= MA50 (signal close)")
    L = [f"# IDX menu {'22' if variant == 'gate' else '24'} — validating {cand_name} — {date.today()} — 12 trials, cumulative N = {N_TRIALS}", "",
         f"Candidate: deployed trend rule + {cand_desc}. `small`, {dates[0].date()} -> {dates[-1].date()}.", "",
         "## The candidate against the deployed rule", "", *HDR, row("deployed (equal 1/K, no gate)", ref, "reference"),
         *([row("regime_gate (menu 22)", out["plain_gate"], "reference")] if "plain_gate" in out else []), row(cand_name, gate, "candidate"), "",
         f"## V1. Regime neighbours (6 trials) — {out['V1']['verdict']} ({v1_pass}/6 pass: Sharpe >= ungated + 0.10 and shallower mDD)", "", *HDR]
    for k in V1:
        L.append(row(f"{k} (off {v1[k]['off_share'] * 100:.0f} % of days)", v1[k], f"{v1[k]['read']} / {v1[k]['money']}"))
    L += ["", f"## V2. Entry-rule neighbours, ungated vs gated (5 trials) — {out['V2']['verdict']} ({v2_pass}/5)", "", *HDR]
    for k in V2:
        L.append(row(f"{k} ungated", v2[k]["ungated"], "twin"))
        L.append(row(f"{k} gated", v2[k]["gated"], f"{v2[k]['gated']['read']} / {v2[k]['gated']['money']}"))
    L += ["", "## V7. Large caps (BLUE, 1 trial)", "", *HDR, row("BLUE ungated", ub, "twin"), row("BLUE gated", gb, f"{gb['read']} / {gb['money']}"), "",
          f"## V3. Time blocks (descriptive) — gate Sharpe >= ungated in {blocks_pass} of 5 blocks", "",
          "| block | ungated CAGR | ungated Sharpe | ungated mDD | gated CAGR | gated Sharpe | gated mDD |", "|---|---|---|---|---|---|---|"]
    for k, v in blocks.items():
        L.append(f"| {k} | {v['ref']['cagr'] * 100:+.1f} % | {v['ref']['sharpe']:.2f} | {v['ref']['mdd'] * 100:.0f} % | {v['gate']['cagr'] * 100:+.1f} % | {v['gate']['sharpe']:.2f} | {v['gate']['mdd'] * 100:.0f} % |")
    for k, v in roll.items():
        L.append(f"\nRolling 500-day windows ({k}, step 20): {v['windows']} windows; gated Sharpe >= ungated in {v['share_sharpe_ge'] * 100:.0f} %; gated mDD shallower in "
                 f"{v['share_mdd_shallower'] * 100:.0f} %; median Sharpe difference {v['median_dsharpe']:+.2f}.")
    v4 = out["V4"]
    L += ["", f"## V4. Placebo — {v4['n']} circular shifts of the real regime series (same structure, wrong dates)", "",
          f"Real gate: Sharpe {gate['sharpe']:.2f} (percentile {v4['percentile_of_real']['sharpe']:.0f} of the placebo; placebo median {v4['placebo_median']['sharpe']:.2f}, 95th {v4['placebo_p95']['sharpe']:.2f}); "
          f"CAGR {gate['cagr'] * 100:+.1f} % (percentile {v4['percentile_of_real']['cagr']:.0f}; placebo median {v4['placebo_median']['cagr'] * 100:+.1f} %); "
          f"mDD {gate['mdd'] * 100:.0f} % (placebo median {v4['placebo_median']['mdd'] * 100:.0f} %, 5th percentile {v4['placebo_mdd_p5'] * 100:.0f} %; shallower than "
          f"{(np.array([p[2] for p in pl]) < gate['mdd']).mean() * 100:.0f} % of placebos). Sharpe test: {'PASS' if v4['pass_sharpe'] else 'FAIL'}; drawdown test: {'PASS' if v4['pass_mdd'] else 'FAIL'}.",
          "", f"Lagged regime: 10 days late Sharpe {lag[10]['sharpe']:.2f} mDD {lag[10]['mdd'] * 100:.0f} %; 20 days late Sharpe {lag[20]['sharpe']:.2f} mDD {lag[20]['mdd'] * 100:.0f} %.", "",
          "## V5. Execution (descriptive)", "", *HDR, row("deployed, entries 1 day late", r_late, "twin"), row("gate, entries 1 day late", s_late, ""),
          row("deployed, costs x 1.5", r_cost, "twin"), row("gate, costs x 1.5", s_cost, ""), "",
          "## V6. Attribution in the ungated book (descriptive)", "", "| entries made while the regime was | n | hit | avg net | median | t |", "|---|---|---|---|---|---|"]
    for k in ("on", "off"):
        g = out["V6"][k]
        L.append(f"| {k} | {g['n']} | {g['hit'] * 100:.0f} % | {g['avg_net'] * 100:+.2f} % | {g['median'] * 100:+.2f} % | {g['t']:.1f} |")
    L += [f"\nDeepest drawdown {out['V6']['dd_window'][0]} -> {out['V6']['dd_window'][1]}: {out['V6']['dd_trades']} trades entered inside it; "
          f"{out['V6']['loss_share_off'] * 100:.0f} % of their losses came from entries made with the regime off (regime off on {out['V6']['off_share_days'] * 100:.0f} % of all days).", "",
          f"## Verdict: **{verdict}**", "", "Checks: " + "; ".join(f"{k} = {'yes' if v else 'NO'}" for k, v in checks.items()) + "."]
    path = os.path.join(HERE, f"IDX_REGIME_VALIDATE_{date.today().isoformat()}.md" if variant == "gate" else f"IDX_MA50_VALIDATE_{date.today().isoformat()}.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    print("\n".join(L))
    print("wrote", path)
    if not args.no_store:
        from blackheart_ingest.idx import research_store as rs
        with psycopg.connect(dsn) as conn:
            sid = rs.record_study(conn, "regime_gate_validation" if variant == "gate" else "os_ma50_validation", dates[-1].date(), params={"variant": variant, "trials": V1 + list(V2) + ["blue_gate"], "n_trials_cumulative": N_TRIALS, "placebo": args.placebo, "seed": SEED},
                                  summary=json.loads(json.dumps(out, default=str)), names=[], report_path=path, note=verdict)
            print(f"study #{sid} stored")


if __name__ == "__main__":
    main()
