#!/usr/bin/env python3
"""IDX menu 21 — beyond the two engines: sizing, combination, sector rotation, the allocation layer (operator, 2026-09-22:
"cari strategi investment atau trading yang lebih baik dibandingkan strategi yang sudah kita punya").

What the desk has (the incumbents, the bar to beat):
  value   strict composite (rev. 3), annual May rebalance: 18-22 %/yr, Sharpe ~0.9-1.0, worst drawdown 22-25 % (2020/21-2026); book `live`
  trend   hi60 / > MA200 / volume >= 1.5x / trail 10 %, K = 10, universe `small`: +29.9 %/yr, Sharpe 1.34, mDD -30 % (2020-26), fails the
          money rule on drawdown only; books `paper_trend`, `trend_live`
After 410 trials over 20 menus the entry side (swing, accumulation, broker flow, ARA, support, sleepers, ML filters) is mined out and the
exit side (64 trials) is settled on trail10. The levers not yet pulled are the ones a portfolio manager pulls: HOW MUCH to hold (sizing),
how to COMBINE the engines (allocation between sleeves), a THIRD engine on a different axis (sector rotation), and the layer ABOVE the desk
(asset allocation in rupiah).

PRE-REGISTERED MENU (18 trials; cumulative 410 + 18 = 428). Declared before the run; nothing tuned afterwards.
  A. Position sizing on the trend sleeve. Entry, exit (trail10), book (K = 10 slots), costs (closing offer/bid + Stockbit fees) and execution
     (signal at close t, trade at close t+1) exactly as menus 6-7 / 13; ONLY the slot size changes. 5 rules x 2 universes (small, LIQ) = 10 trials.
       invvol       slot = (1/K) x (median 60-day vol of the universe that day / the name's 60-day vol), clipped to 0.5/K..2/K; exposure <= 100 %
       risk1        Turtle unit: slot = 1 % of NAV / (2 x ATR20 / price) at the signal close, clipped to 2.5..15 % (15 % = the books' max_weight)
       voltarget    book level: every slot scaled by m = clip(20 % / realised 20-day vol of the unscaled book, 0.25, 1.0), m from the prior close
       regime_half  slots at half size while COMPOSITE < its 200-day average at the prior close, full size otherwise
       pyramid      enter with half a slot; add the other half at the close after the price first stands >= entry + 1 x ATR20 (Turtle add)
     Reading vs the deployed sizing (equal 1/K), same universe: BETTER only if ALL hold: >= 150 closed trades; t >= 2.0; Sharpe >= ref + 0.15;
       CAGR >= 80 % of ref; max drawdown not deeper than ref. ADOPTION (paper book) needs BETTER on both universes. Money rule as menu 6.
     Robustness (descriptive, not a trial): a BETTER rule is re-run on `small` 2005-2019 (Yahoo survivors file, menu-15 set-up) and is
       CONFIRMED only if it keeps Sharpe >= ref + 0.15 there too.
  B. The combined book — what the operator runs today, measured as ONE book. value = composite_q (strict gate), May calendar from 2020, rev. 3
     simulator (real costs, dividends net of tax); trend = the deployed sleeve (small, trail10, K = 10, equal slots). Window 2021-01-04 ->
     2026-09-21 (both engines live). Sleeve weights re-set on the first trading day of each month, drift inside the month; moving money between
     sleeves is free (it is a slot-size change, not a trade). 3 trials:
       combo_5050   50 / 50
       combo_rp     inverse trailing 60-day vol of each sleeve, monthly, each sleeve clipped to 30..70 %
       combo_3way   40 value / 40 trend / 20 cash at 4 %/yr
     Reading: BETTER than what we have only if ALL hold: Sharpe >= max(value, trend) + 0.15; max drawdown <= 25 %; CAGR >= 18 %; positive in
       >= 5 of the 6 calendar years. Descriptive: daily-return correlation of the sleeves, drawdown overlap.
  C. Sector rotation — a third engine on a different axis. LIQ names with an IDX-IC sector (A..K). Sector return = equal-weight daily return of
     its LIQ members (membership as of the prior day). Monthly at the first trading day's close from 2021-01: rank sectors; hold the 10 most
     liquid LIQ names (60-day value) of each chosen sector, equal weight, full reset; sells at the closing bid, buys at the closing offer,
     Stockbit fees; dividends ignored; idle cash 4 %/yr. 3 trials:
       sec_mom6     top-2 sectors by 6-month (125-day) return
       sec_mom12_1  top-2 sectors by 12-month return skipping the last month (250 days, skip 21)
       sec_cmdty    Energy (A) held while Brent's 3-month (63-day) return > 0, else cash (menu 2 tested this lead at 10 days; this is monthly)
     References: random 2 sectors monthly (seeded); every LIQ name equal weight monthly; COMPOSITE. Money rule as menu 6 with "5 of 6 years"
       (a trade = one name held over consecutive months, net = exit at bid over entry at offer).
  D. The allocation layer — investment, not stock picking. Monthly, 2005-01 -> 2026-09, in rupiah. Assets: IHSG (JKSE price index), S&P 500
     in IDR (^GSPC x USDIDR), gold in IDR (macro gold x USDIDR), cash = BI rate minus 1.5 points (deposito net of tax; the 2024-2025 BI
     gap in idx.macro filled by hand from the published decisions). 0.30 % per switch. 2 trials:
       gem_idr      dual momentum (Antonacci, home = IHSG): if IHSG's 12-month return > cash's, hold the better of IHSG / S&P (IDR) by
                    12-month return; else cash
       dm3_idr      hold the best of {IHSG, S&P (IDR), gold (IDR)} by 12-month return when it beats cash; else cash
     References: IHSG buy-and-hold; 60 / 40 IHSG / cash monthly; equal-weight three assets monthly.
     Reading: BETTER than holding the index only if ALL hold: Sharpe >= IHSG + 0.30; max drawdown <= 25 %; CAGR >= IHSG's; positive in
       >= 2/3 of the calendar years.
READ-ONLY. INGEST_DB_DSN=... PYTHONIOENCODING=utf-8 blackheart-ingest/.venv/Scripts/python research/idx_beyond.py [--family A,B,C,D] [--no-store]
  IDX_BEYOND_CACHE=<file.pkl> caches the loaded panels; IDX_BEYOND_SCRATCH=<dir> holds gspc.csv and the value-book NAV cache.
"""
from __future__ import annotations

import argparse
import glob
import json
import math
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
import idx_exit as E  # noqa: E402
import idx_swing2 as S  # noqa: E402
import idx_trend as T  # noqa: E402

S.END = date(2026, 9, 21)
N_BEFORE = 410
K = E.K
LEAD = E.LEAD
SEED = 20260922
SIZINGS = ["invvol", "risk1", "voltarget", "regime_half", "pyramid"]
UNIS = ["small", "LIQ"]
ARMS_A = [f"{s}|{u}" for u in UNIS for s in SIZINGS]
ARMS_B = ["combo_5050", "combo_rp", "combo_3way"]
ARMS_C = ["sec_mom6", "sec_mom12_1", "sec_cmdty"]
ARMS_D = ["gem_idr", "dm3_idr"]
ALL_ARMS = ARMS_A + ARMS_B + ARMS_C + ARMS_D
assert len(ALL_ARMS) == 18
N_TRIALS = N_BEFORE + len(ALL_ARMS)
CASH_RATE = 0.04
COMBO_START = pd.Timestamp("2021-01-04")
YAHOO = os.path.join(ROOT, "research-scratch", "idx")
SCRATCH = os.environ.get("IDX_BEYOND_SCRATCH", os.path.join(ROOT, "research-scratch", "idx-screen"))
BI_FILL = {"2024-01": 6.00, "2024-04": 6.25, "2024-09": 6.00, "2025-01": 5.75, "2025-05": 5.50, "2025-07": 5.25, "2025-08": 5.00, "2025-09": 4.75}
CASH_SPREAD = 1.5
SWITCH_COST = 0.003


# ----------------------------------------------------------------------------------------------------------------------- shared

def series_stats(R: pd.Series, per_year=250) -> dict:
    """Book-level numbers of a daily (or monthly, per_year=12) simple-return series."""
    R = R.astype(float).fillna(0.0)
    eq = (1 + R).cumprod()
    vol = R.std() * math.sqrt(per_year)
    years = R.groupby(R.index.year).apply(lambda s: (1 + s).prod() - 1)
    n = len(R)
    return {"total": float(eq.iloc[-1] - 1), "cagr": float(eq.iloc[-1] ** (per_year / n) - 1) if n else 0.0,
            "sharpe": float(R.mean() * per_year / vol) if vol > 0 else 0.0, "vol": float(vol),
            "mdd": float((eq / eq.cummax() - 1).min()), "years": {int(y): float(v) for y, v in years.items()}, "n_days": int(n)}


def yrs(d):
    return " ".join(f"{y % 100:02d}:{v * 100:+.0f}" for y, v in sorted(d.items()))


def money_read(s, rn, years_needed=5):
    why = []
    if s["n"] < 150:
        why.append("n<150")
    if not (s["avg_net"] > 0 and s["tstat"] >= 2.5):
        why.append("t<2.5")
    if s["sharpe"] < 1.0:
        why.append("sharpe<1")
    if s["mdd"] < -0.25:
        why.append("mdd>25%")
    if sum(1 for v in s["years"].values() if v > 0) < years_needed:
        why.append(f"years<{years_needed}")
    if rn is not None and s["sharpe"] < rn["sharpe"] + 0.5:
        why.append("vs random")
    return "CANDIDATE" if not why else "tested: " + ",".join(why)


def better_read(s, ref):
    why = []
    if s["n"] < 150:
        why.append("n<150")
    if s["tstat"] < 2.0:
        why.append("t<2")
    if s["sharpe"] < ref["sharpe"] + 0.15:
        why.append("sharpe<ref+0.15")
    if s["cagr"] < 0.8 * ref["cagr"]:
        why.append("cagr<80%ref")
    if s["mdd"] < ref["mdd"]:
        why.append("mdd deeper")
    return "BETTER" if not why else "no: " + ",".join(why)


def load_all(dsn, cache=None):
    if cache and os.path.exists(cache):
        with open(cache, "rb") as fh:
            return pickle.load(fh)
    with psycopg.connect(dsn) as conn:
        bars, listing, idx, macro, buyb, splits, pead = S.load(conn)
        P = S.panels(bars, listing)
        _, unis, comp = S.build(P, listing, idx, macro, buyb, splits, pead)
        H, L = E.load_hl(conn, P)
        sectors = pd.read_sql("SELECT code, sector FROM idx.listing", conn)
        brent = pd.read_sql("SELECT obs_date, value FROM idx.macro WHERE series = 'brent' ORDER BY 1", conn)
    data = (P, unis, comp, H, L, sectors, brent)
    if cache:
        with open(cache, "wb") as fh:
            pickle.dump(data, fh)
    return data


# ----------------------------------------------------------------------------------------------------------------------- family A

def run_book_sized(A, H, c_in, c_out, entry_mask, entry_score, rule, uni, size, add=None, k=K, rng=None):
    """E.run_book with a per-position weight (fraction of NAV) chosen at entry by size(t_signal, j), and optional adds.
    Same convention as the desk's engines: a position contributes w x r each day (weights do not drift with price), so the
    equal-weight case (size = 1/K) reproduces E.run_book to the last digit. An add (pyramid) executes at the next close at the
    entry cost. A slot is one name whatever its weight; total exposure never exceeds 100 %."""
    Tn, N = A.shape
    ret = np.full((Tn, N), np.nan)
    ret[1:] = A[1:] / A[:-1] - 1
    R = np.zeros(Tn)
    held: dict[int, dict] = {}
    pending: dict[int, float] = {}
    pending_add: dict[int, float] = {}
    pending_entry: list[int] = []
    trades = []
    for t in range(1, Tn):
        day = 0.0
        for j, p in held.items():
            r = ret[t, j]
            day += p["w"] * (0.0 if np.isnan(r) else r)
        for j, f in list(pending.items()):
            if j in held and not np.isnan(A[t, j]) and np.isfinite(c_out[t, j]):
                p = held[j]
                w_sell = min(f * p["w0"], p["w"])
                if w_sell <= 0:
                    continue
                tot = sum(wl for wl, _, _ in p["legs_in"])
                g = sum(wl * (A[t, j] / al - 1) for wl, al, _ in p["legs_in"]) / tot
                ci = sum(wl * cl for wl, _, cl in p["legs_in"]) / tot
                p["legs_out"].append((w_sell, g, g - ci - c_out[t, j]))
                p["legs"].append((w_sell / p["w0"], g, g - ci - c_out[t, j]))
                day -= w_sell * c_out[t, j]
                p["w"] -= w_sell
                if p["w"] <= 1e-9:
                    held.pop(j)
                    tw = sum(x[0] for x in p["legs_out"])
                    gg = sum(x[0] * x[1] for x in p["legs_out"]) / tw
                    nn = sum(x[0] * x[2] for x in p["legs_out"]) / tw
                    trades.append((p["e"], j, gg, nn, t - p["e"], p["mfe"]))
        pending = {}
        expo = sum(p["w"] for p in held.values())
        for j, wa in list(pending_add.items()):
            if j in held and not np.isnan(A[t, j]) and np.isfinite(c_in[t, j]) and expo + wa <= 1.0 + 1e-9:
                p = held[j]
                p["legs_in"].append((wa, A[t, j], c_in[t, j]))
                p["w"] += wa
                p["w0"] += wa
                day -= wa * c_in[t, j]
                expo += wa
        pending_add = {}
        for j in pending_entry:
            if len(held) >= k or j in held or np.isnan(A[t, j]) or not np.isfinite(c_in[t, j]):
                continue
            w = min(float(size(t - 1, j)), 1.0 - expo)
            if w < 0.25 / k:
                continue
            h0 = H[t, j] if not np.isnan(H[t, j]) else A[t, j]
            held[j] = {"e": t, "a0": A[t, j], "peak": A[t, j], "hh": h0, "w": w, "w0": w, "legs_in": [(w, A[t, j], c_in[t, j])],
                       "legs_out": [], "legs": [], "mfe": 0.0, "state": {}}
            day -= w * c_in[t, j]
            expo += w
        pending_entry = []
        R[t] = day
        for j, p in held.items():
            if np.isnan(A[t, j]):
                pending[j] = 1.0
                continue
            p["peak"] = max(p["peak"], A[t, j])
            if not np.isnan(H[t, j]):
                p["hh"] = max(p["hh"], H[t, j])
            p["mfe"] = max(p["mfe"], p["peak"] / p["a0"] - 1)
            f = rule(t, j, p)
            if f and f > 0:
                pending[j] = float(f)
            elif add is not None:
                wa = add(t, j, p)
                if wa and wa > 0:
                    pending_add[j] = float(wa)
        full_exits = sum(1 for j, f in pending.items() if j in held and f * held[j]["w0"] >= held[j]["w"] - 1e-9)
        free = k - (len(held) - full_exits)
        if free > 0:
            if rng is not None:
                cand = np.flatnonzero(uni[t] & ~np.isnan(A[t]))
                cand = [j for j in cand if j not in held]
                pick = list(rng.choice(cand, size=min(free, len(cand)), replace=False)) if cand else []
            else:
                cand = np.flatnonzero(entry_mask[t] & uni[t])
                cand = [j for j in cand if j not in held]
                sc = np.nan_to_num(entry_score[t, cand], nan=-np.inf) if cand else np.array([])
                pick = [cand[i] for i in np.argsort(-sc, kind="stable")[:free]] if cand else []
            pending_entry = list(pick)
    return pd.Series(R), trades, held


def make_sizes(A, ATR, SIG, uni_bool, k):
    def eq(t, j):
        return 1.0 / k

    def invvol(t, j):
        s = SIG[t, j]
        row = SIG[t][uni_bool[t]]
        row = row[np.isfinite(row)]
        ref = float(np.median(row)) if len(row) else np.nan
        if not (np.isfinite(s) and s > 0 and np.isfinite(ref) and ref > 0):
            return 1.0 / k
        return (1.0 / k) * float(np.clip(ref / s, 0.5, 2.0))

    def risk1(t, j):
        a, p = ATR[t, j], A[t, j]
        if not (np.isfinite(a) and a > 0 and np.isfinite(p) and p > 0):
            return 1.0 / k
        return float(np.clip(0.01 / (2 * a / p), 0.025, 0.15))

    def half(t, j):
        return 0.5 / k

    return {"eq": eq, "invvol": invvol, "risk1": risk1, "half": half}


def make_add(A, ATR, k):
    def add(t, j, p):
        st = p["state"]
        if st.get("added"):
            return 0
        a0 = ATR[p["e"], j]
        if not (np.isfinite(a0) and a0 > 0):
            a0 = 0.10 * p["a0"]
        if A[t, j] >= p["a0"] + a0:
            st["added"] = True
            return 0.5 / k
        return 0
    return add


def scale_series(R_raw: np.ndarray, m: np.ndarray) -> pd.Series:
    """Book-level multiplier known at the prior close: R_t x m_{t-1}."""
    return pd.Series(R_raw * np.r_[1.0, m[:-1]])


def vt_mult(R_raw, target=0.20, lo=0.25, hi=1.0, win=20):
    s = pd.Series(R_raw).rolling(win, min_periods=win).std() * math.sqrt(250)
    m = (target / s.replace(0, np.nan)).clip(lo, hi).fillna(1.0)
    return m.to_numpy(float)


def regime_mult(comp: pd.Series, dates) -> np.ndarray:
    c = comp.reindex(dates).ffill()
    ma = c.rolling(200, min_periods=200).mean()
    return np.where((c < ma).to_numpy(), 0.5, 1.0)


def prep_panels(P, unis, Hp, Lp):
    adj, vol = P["adj"], P["volume"]
    A = adj.to_numpy(float)
    H, L = Hp.to_numpy(float), Lp.to_numpy(float)
    ma200 = adj.rolling(200, min_periods=200).mean()
    vr = vol / vol.rolling(20, min_periods=20).median()
    hi = adj.rolling(LEAD[0], min_periods=LEAD[0]).max()
    entry = ((adj >= hi) & (adj > ma200) & (vr >= LEAD[2])).to_numpy(bool)
    score = vr.to_numpy(float)
    prev = adj.shift(1)
    tr = pd.concat([Hp - Lp, (Hp - prev).abs(), (Lp - prev).abs()], axis=1, keys=["a", "b", "c"]).T.groupby(level=1).max().T.reindex(columns=adj.columns)
    ATR = tr.ewm(alpha=1 / 20, adjust=False, min_periods=20).mean().to_numpy(float)
    SIG = (adj.pct_change().rolling(60, min_periods=40).std() * math.sqrt(250)).to_numpy(float)
    z = np.zeros_like(A)
    rules = E.make_rules(A, H, L, ATR, z, z, z, z, z)
    universes = {"small": (unis["LIQ"] & ~unis["BLUE"]).to_numpy(bool), "LIQ": unis["LIQ"].to_numpy(bool)}
    return A, H, L, entry, score, ATR, SIG, rules["trail10"], universes


def family_a(P, unis, comp, Hp, Lp):
    c_in, c_out = S.costs(P)
    dates = P["adj"].index
    A, H, L, entry, score, ATR, SIG, trail10, universes = prep_panels(P, unis, Hp, Lp)
    res, refs, rnd, raw_R = {}, {}, {}, {}
    for u in UNIS:
        uni = universes[u]
        sizes = make_sizes(A, ATR, SIG, uni, K)
        add = make_add(A, ATR, K)
        R0, tr0, _ = E.run_book(A, H, L, c_in, c_out, entry, score, trail10, uni)
        R1, tr1, _ = run_book_sized(A, H, c_in, c_out, entry, score, trail10, uni, sizes["eq"])
        assert np.allclose(R0.to_numpy(), R1.to_numpy(), atol=1e-12) and len(tr0) == len(tr1), "sized engine must reproduce the reference"
        refs[u] = E.stats(R1.copy(), tr1, dates, N_TRIALS)
        raw_R[u] = R1.to_numpy(float)
        Rr, trr, _ = E.run_book(A, H, L, c_in, c_out, None, None, trail10, uni, rng=np.random.default_rng(SEED))
        refs[u + "_rnd"] = E.stats(Rr, trr, dates, N_TRIALS)
        rr = Rr.to_numpy(float)
        rng_i = 0
        for s_name in SIZINGS:
            arm = f"{s_name}|{u}"
            if s_name in ("invvol", "risk1"):
                Rs, trs, open_ = run_book_sized(A, H, c_in, c_out, entry, score, trail10, uni, sizes[s_name])
                rng_i += 1
                Rq, trq, _ = run_book_sized(A, H, c_in, c_out, None, None, trail10, uni, sizes[s_name], rng=np.random.default_rng(SEED + rng_i))
            elif s_name == "pyramid":
                Rs, trs, open_ = run_book_sized(A, H, c_in, c_out, entry, score, trail10, uni, sizes["half"], add=add)
                rng_i += 1
                Rq, trq, _ = run_book_sized(A, H, c_in, c_out, None, None, trail10, uni, sizes["half"], add=add, rng=np.random.default_rng(SEED + rng_i))
            else:
                m = vt_mult(raw_R[u]) if s_name == "voltarget" else regime_mult(comp, dates)
                Rs, trs, open_ = scale_series(raw_R[u], m), tr1, {}
                mr = vt_mult(rr) if s_name == "voltarget" else m
                Rq, trq = scale_series(rr, mr), trr
            st = E.stats(Rs, trs, dates, N_TRIALS)
            st["open"] = len(open_)
            st["expo"] = float(np.mean(np.abs(Rs.to_numpy()) > 0))
            res[arm] = st
            rnd[arm] = E.stats(Rq, trq, dates, N_TRIALS)
            print(f"A {arm:18s} n={st['n']:4d} hit={st['hit'] * 100:3.0f}% net={st['avg_net'] * 100:+5.2f}% t={st['tstat']:4.1f} cagr={st['cagr'] * 100:+5.1f}% "
                  f"sharpe={st['sharpe']:4.2f} mdd={st['mdd'] * 100:4.0f}% | ref sharpe {refs[u]['sharpe']:.2f} mdd {refs[u]['mdd'] * 100:.0f}% | rnd {rnd[arm]['sharpe']:.2f}", flush=True)
    better = {arm: better_read(res[arm], refs[arm.split("|")[1]]) for arm in ARMS_A}
    money = {arm: money_read(res[arm], rnd[arm]) for arm in ARMS_A}
    adopt = [s for s in SIZINGS if all(better[f"{s}|{u}"] == "BETTER" for u in UNIS)]
    informative = [s for s in SIZINGS if s not in adopt and any(better[f"{s}|{u}"] == "BETTER" for u in UNIS)]
    return {"res": res, "refs": refs, "rnd": rnd, "better": better, "money": money, "adopt": adopt, "informative": informative}


def regime_off_mask(comp: pd.Series, dates) -> np.ndarray:
    c = comp.reindex(dates).ffill()
    return (c < c.rolling(200, min_periods=200).mean()).to_numpy()


def family_a2(P, unis, comp, Hp, Lp):
    """FOLLOW-UP declared after reading family A (1 trial; cumulative 428 + 1 = 429): the implementable form of regime_half.
    regime_entry: a NEW position takes half a slot (1/2K) when COMPOSITE < its 200-day average at the signal close, a full slot
    otherwise; positions already held are never resized (no trimming trades). Same reading rules as family A; robustness 2005-2019
    with the JKSE. Descriptive: the share of trading days per year with the regime off."""
    c_in, c_out = S.costs(P)
    dates = P["adj"].index
    A, H, L, entry, score, ATR, SIG, trail10, universes = prep_panels(P, unis, Hp, Lp)
    off = regime_off_mask(comp, dates)
    off_share = pd.Series(off, index=dates).groupby(dates.year).mean()
    res, refs, rnd = {}, {}, {}
    for u in UNIS:
        uni = universes[u]
        size = lambda t, j, off=off: (0.5 / K) if off[t] else (1.0 / K)  # noqa: E731
        R0, tr0, _ = E.run_book(A, H, L, c_in, c_out, entry, score, trail10, uni)
        refs[u] = E.stats(R0, tr0, dates, N_TRIALS + 1)
        Rs, trs, open_ = run_book_sized(A, H, c_in, c_out, entry, score, trail10, uni, size)
        st = E.stats(Rs, trs, dates, N_TRIALS + 1)
        st["open"] = len(open_)
        res[u] = st
        Rq, trq, _ = run_book_sized(A, H, c_in, c_out, None, None, trail10, uni, size, rng=np.random.default_rng(SEED + 99))
        rnd[u] = E.stats(Rq, trq, dates, N_TRIALS + 1)
        print(f"A2 regime_entry|{u:5s} n={st['n']:4d} hit={st['hit'] * 100:3.0f}% net={st['avg_net'] * 100:+5.2f}% t={st['tstat']:4.1f} cagr={st['cagr'] * 100:+5.1f}% "
              f"sharpe={st['sharpe']:4.2f} mdd={st['mdd'] * 100:4.0f}% | ref sharpe {refs[u]['sharpe']:.2f} mdd {refs[u]['mdd'] * 100:.0f}% | rnd {rnd[u]['sharpe']:.2f}", flush=True)
    better = {u: better_read(res[u], refs[u]) for u in UNIS}
    money = {u: money_read(res[u], rnd[u]) for u in UNIS}
    return {"res": res, "refs": refs, "rnd": rnd, "better": better, "money": money, "off_share": {int(y): float(v) for y, v in off_share.items()}}


def family_a3(P, unis, comp, Hp, Lp):
    """FOLLOW-UP declared after the operator's question "kalau di bawah MA200 tidak usah trading?" (4 trials; cumulative 429 + 4 = 433).
    regime_gate: no NEW entry while COMPOSITE < MA200 at the signal close; held names run to their trailing stop.
    regime_flat: every held name is sold at the first close with COMPOSITE < MA200 (executed next close at the bid) and no entry is taken
                 until COMPOSITE is back above; trailing stop otherwise. Costs of the exits and re-entries are inside the engine.
    Same reading rules as family A (BETTER vs equal 1/K; money rule); 2005-2019 check on `small` with the JKSE."""
    c_in, c_out = S.costs(P)
    dates = P["adj"].index
    A, H, L, entry, score, ATR, SIG, trail10, universes = prep_panels(P, unis, Hp, Lp)
    off = regime_off_mask(comp, dates)
    return _run_regime_arms(A, H, c_in, c_out, entry, score, trail10, universes, off, dates, N_TRIALS + 5)


def _run_regime_arms(A, H, c_in, c_out, entry, score, trail10, universes, off, dates, n_trials, lo=None, hi=None):
    size_gate = lambda t, j: 0.0 if off[t] else (1.0 / K)  # noqa: E731
    rule_flat = lambda t, j, p: 1.0 if (off[t] or trail10(t, j, p)) else 0  # noqa: E731
    arms = {"regime_gate": (size_gate, trail10), "regime_flat": (size_gate, rule_flat)}
    res, refs, rnd = {}, {}, {}

    def cut(R, trs):
        if lo is None:
            return E.stats(R, trs, dates, n_trials)
        return E.stats(R.iloc[lo:hi].reset_index(drop=True), [x for x in trs if lo <= x[0] < hi], dates[lo:hi], n_trials)
    for u, uni in universes.items():
        R0, tr0, _ = run_book_sized(A, H, c_in, c_out, entry, score, trail10, uni, lambda t, j: 1.0 / K)
        refs[u] = cut(R0, tr0)
        for i, (name, (size, rule)) in enumerate(arms.items()):
            arm = f"{name}|{u}"
            Rs, trs, open_ = run_book_sized(A, H, c_in, c_out, entry, score, rule, uni, size)
            st = cut(Rs, trs)
            st["open"] = len(open_)
            res[arm] = st
            Rq, trq, _ = run_book_sized(A, H, c_in, c_out, None, None, rule, uni, size, rng=np.random.default_rng(SEED + 200 + i))
            rnd[arm] = cut(Rq, trq)
            print(f"A3 {arm:20s} n={st['n']:4d} hit={st['hit'] * 100:3.0f}% net={st['avg_net'] * 100:+5.2f}% t={st['tstat']:4.1f} cagr={st['cagr'] * 100:+5.1f}% "
                  f"sharpe={st['sharpe']:4.2f} mdd={st['mdd'] * 100:4.0f}% | ref sharpe {refs[u]['sharpe']:.2f} mdd {refs[u]['mdd'] * 100:.0f}% | rnd {rnd[arm]['sharpe']:.2f}", flush=True)
    better = {arm: better_read(res[arm], refs[arm.split("|")[1]]) for arm in res}
    money = {arm: money_read(res[arm], rnd[arm]) for arm in res}
    return {"res": res, "refs": refs, "rnd": rnd, "better": better, "money": money}


def family_a3_robust():
    import idx_trend_2008 as Y
    Py, jk = Y.load_yahoo()
    adj, vol, Hp, Lp = Py["close"], Py["volume"], Py["high"], Py["low"]
    dates = adj.index
    A, H, L = adj.to_numpy(float), Hp.to_numpy(float), Lp.to_numpy(float)
    c_in = np.full(A.shape, Y.HALF_SPREAD + S.FEE_BUY)
    c_out = np.full(A.shape, Y.HALF_SPREAD + S.FEE_SELL)
    ma200 = adj.rolling(200, min_periods=200).mean()
    vr = vol / vol.rolling(20, min_periods=20).median()
    hi = adj.rolling(LEAD[0], min_periods=LEAD[0]).max()
    entry = ((adj >= hi) & (adj > ma200) & (vr >= LEAD[2])).to_numpy(bool)
    score = vr.to_numpy(float)
    z = np.zeros_like(A)
    trail10 = E.make_rules(A, H, L, z, z, z, z, z, z)["trail10"]
    v60 = (adj * vol).rolling(60, min_periods=60).median()
    liq = (v60 >= S.LIQ) & (adj >= S.MIN_PRICE) & (vol > 0) & adj.notna()
    blue = liq & (v60 >= S.BLUE_LIQ) & (adj >= S.BLUE_PRICE)
    lo, hi_ = dates.searchsorted(pd.Timestamp("2005-01-01")), dates.searchsorted(pd.Timestamp("2020-01-01"))
    window = np.zeros(len(dates), bool)
    window[lo:hi_] = True
    uni = (liq & ~blue).to_numpy(bool) & window[:, None]
    off = regime_off_mask(jk, dates)
    return _run_regime_arms(A, H, c_in, c_out, entry, score, trail10, {"small": uni}, off, dates, N_TRIALS + 5, lo=lo, hi=hi_)


def family_a2_robust():
    import idx_trend_2008 as Y
    Py, jk = Y.load_yahoo()
    adj, vol, Hp, Lp = Py["close"], Py["volume"], Py["high"], Py["low"]
    dates = adj.index
    A, H, L = adj.to_numpy(float), Hp.to_numpy(float), Lp.to_numpy(float)
    c_in = np.full(A.shape, Y.HALF_SPREAD + S.FEE_BUY)
    c_out = np.full(A.shape, Y.HALF_SPREAD + S.FEE_SELL)
    ma200 = adj.rolling(200, min_periods=200).mean()
    vr = vol / vol.rolling(20, min_periods=20).median()
    hi = adj.rolling(LEAD[0], min_periods=LEAD[0]).max()
    entry = ((adj >= hi) & (adj > ma200) & (vr >= LEAD[2])).to_numpy(bool)
    score = vr.to_numpy(float)
    z = np.zeros_like(A)
    trail10 = E.make_rules(A, H, L, z, z, z, z, z, z)["trail10"]
    v60 = (adj * vol).rolling(60, min_periods=60).median()
    liq = (v60 >= S.LIQ) & (adj >= S.MIN_PRICE) & (vol > 0) & adj.notna()
    blue = liq & (v60 >= S.BLUE_LIQ) & (adj >= S.BLUE_PRICE)
    lo, hi_ = dates.searchsorted(pd.Timestamp("2005-01-01")), dates.searchsorted(pd.Timestamp("2020-01-01"))
    window = np.zeros(len(dates), bool)
    window[lo:hi_] = True
    uni = (liq & ~blue).to_numpy(bool) & window[:, None]
    off = regime_off_mask(jk, dates)
    size = lambda t, j: (0.5 / K) if off[t] else (1.0 / K)  # noqa: E731

    def cut(R, trs):
        return E.stats(R.iloc[lo:hi_].reset_index(drop=True), [x for x in trs if lo <= x[0] < hi_], dates[lo:hi_], N_TRIALS + 1)
    R_ref, tr_ref, _ = run_book_sized(A, H, c_in, c_out, entry, score, trail10, uni, lambda t, j: 1.0 / K)
    R, trs, _ = run_book_sized(A, H, c_in, c_out, entry, score, trail10, uni, size)
    out = {"ref": cut(R_ref, tr_ref), "regime_entry": cut(R, trs)}
    print(f"A2 2005-19 regime_entry cagr={out['regime_entry']['cagr'] * 100:+5.1f}% sharpe={out['regime_entry']['sharpe']:4.2f} mdd={out['regime_entry']['mdd'] * 100:4.0f}% "
          f"| ref {out['ref']['cagr'] * 100:+5.1f}% {out['ref']['sharpe']:4.2f} {out['ref']['mdd'] * 100:4.0f}%", flush=True)
    return out


# ----------------------------------------------------------------------------------------------------------------------- family A robustness (2005-2019)

def family_a_robust(sizings: list[str]):
    """Re-run the reference and the named sizing rules on `small` 2005-2019 from the Yahoo survivors file (menu-15 set-up)."""
    import idx_trend_2008 as Y
    out = {}
    Py, jk = Y.load_yahoo()
    adj, vol, Hp, Lp = Py["close"], Py["volume"], Py["high"], Py["low"]
    dates = adj.index
    A, H, L = adj.to_numpy(float), Hp.to_numpy(float), Lp.to_numpy(float)
    c_in = np.full(A.shape, Y.HALF_SPREAD + S.FEE_BUY)
    c_out = np.full(A.shape, Y.HALF_SPREAD + S.FEE_SELL)
    ma200 = adj.rolling(200, min_periods=200).mean()
    vr = vol / vol.rolling(20, min_periods=20).median()
    hi = adj.rolling(LEAD[0], min_periods=LEAD[0]).max()
    entry = ((adj >= hi) & (adj > ma200) & (vr >= LEAD[2])).to_numpy(bool)
    score = vr.to_numpy(float)
    prev = adj.shift(1)
    tr = pd.concat([Hp - Lp, (Hp - prev).abs(), (Lp - prev).abs()], axis=1, keys=["a", "b", "c"]).T.groupby(level=1).max().T.reindex(columns=adj.columns)
    ATR = tr.ewm(alpha=1 / 20, adjust=False, min_periods=20).mean().to_numpy(float)
    SIG = (adj.pct_change().rolling(60, min_periods=40).std() * math.sqrt(250)).to_numpy(float)
    z = np.zeros_like(A)
    trail10 = E.make_rules(A, H, L, ATR, z, z, z, z, z)["trail10"]
    v60 = (adj * vol).rolling(60, min_periods=60).median()
    liq = (v60 >= S.LIQ) & (adj >= S.MIN_PRICE) & (vol > 0) & adj.notna()
    blue = liq & (v60 >= S.BLUE_LIQ) & (adj >= S.BLUE_PRICE)
    uni = (liq & ~blue).to_numpy(bool)
    lo, hi_ = dates.searchsorted(pd.Timestamp("2005-01-01")), dates.searchsorted(pd.Timestamp("2020-01-01"))
    window = np.zeros(len(dates), bool)
    window[lo:hi_] = True
    uni = uni & window[:, None]
    sizes = make_sizes(A, ATR, SIG, uni, K)
    add = make_add(A, ATR, K)

    def cut(R, trs):
        Rw = R.iloc[lo:hi_].reset_index(drop=True)
        trw = [x for x in trs if lo <= x[0] < hi_]
        return E.stats(Rw, trw, dates[lo:hi_], N_TRIALS)
    R_ref, tr_ref, _ = run_book_sized(A, H, c_in, c_out, entry, score, trail10, uni, sizes["eq"])
    out["ref"] = cut(R_ref, tr_ref)
    raw = R_ref.to_numpy(float)
    for s_name in sizings:
        if s_name in ("invvol", "risk1"):
            R, trs, _ = run_book_sized(A, H, c_in, c_out, entry, score, trail10, uni, sizes[s_name])
        elif s_name == "pyramid":
            R, trs, _ = run_book_sized(A, H, c_in, c_out, entry, score, trail10, uni, sizes["half"], add=add)
        elif s_name == "voltarget":
            R, trs = scale_series(raw, vt_mult(raw)), tr_ref
        else:
            m = np.where((jk.reindex(dates).ffill() < jk.reindex(dates).ffill().rolling(200, min_periods=200).mean()).to_numpy(), 0.5, 1.0)
            R, trs = scale_series(raw, m), tr_ref
        out[s_name] = cut(R, trs)
        print(f"R {s_name:12s} 2005-19 n={out[s_name]['n']:4d} cagr={out[s_name]['cagr'] * 100:+5.1f}% sharpe={out[s_name]['sharpe']:4.2f} mdd={out[s_name]['mdd'] * 100:4.0f}% "
              f"| ref sharpe {out['ref']['sharpe']:.2f} mdd {out['ref']['mdd'] * 100:.0f}%", flush=True)
    return out


# ----------------------------------------------------------------------------------------------------------------------- family B

def value_nav(dsn, first_year=2020, month=5) -> pd.Series:
    cache = os.path.join(SCRATCH, f"beyond_value_nav_{first_year}_{month}.csv")
    if os.path.exists(cache):
        s = pd.read_csv(cache, parse_dates=["date"]).set_index("date")["nav"]
        return s
    import idx_value_quality as VQ
    VQ.FIRST_YEAR = first_year
    with psycopg.connect(dsn) as conn:
        conn.execute("SET max_parallel_workers_per_gather = 0")
        close, vol, delisted, div, ix = VQ.load(conn)
        rebals = VQ.rebalance_dates(close.index, month)
        sels = {}
        for D in rebals:
            sel, log = VQ.select(conn, D)
            sels[D] = sel["composite_q"]
            print(f"B value {D.date()}: {len(sels[D])} names (pool strict {log['pool_strict']})", flush=True)
    nav = VQ.simulate(sels, close, vol, delisted, div, rebals[0], close.index[-1], spread=True)
    os.makedirs(SCRATCH, exist_ok=True)
    nav.rename("nav").rename_axis("date").to_csv(cache)
    return nav


def combine(rets: pd.DataFrame, weight_fn, cash_rate=0.0) -> pd.Series:
    """NAV of a book of sleeves: weights re-set at the close of the first trading day of each month, drift in between."""
    dates = rets.index
    dc = (1 + cash_rate) ** (1 / 252) - 1 if cash_rate else 0.0
    nav = 1.0
    w = weight_fn(dates[0], rets.iloc[:1])
    vals = {k: nav * v for k, v in w.items()}
    cash = nav - sum(vals.values())
    out = [nav]
    for i in range(1, len(dates)):
        d = dates[i]
        cash *= 1 + dc
        for k in vals:
            vals[k] *= 1 + float(rets.iloc[i][k])
        nav = cash + sum(vals.values())
        out.append(nav)
        if d.month != dates[i - 1].month:
            w = weight_fn(d, rets.iloc[:i + 1])
            vals = {k: nav * v for k, v in w.items()}
            cash = nav - sum(vals.values())
    return pd.Series(out, index=dates)


def family_b(dsn, P, unis, Hp, Lp):
    c_in, c_out = S.costs(P)
    dates = P["adj"].index
    A, H, L, entry, score, ATR, SIG, trail10, universes = prep_panels(P, unis, Hp, Lp)
    R_tr, tr_tr, _ = E.run_book(A, H, L, c_in, c_out, entry, score, trail10, universes["small"])
    R_tr.index = dates
    nav_v = value_nav(dsn)
    r_v = nav_v.pct_change().fillna(0.0)
    rets = pd.DataFrame({"value": r_v, "trend": R_tr}).dropna()
    rets = rets[rets.index >= COMBO_START]
    rets = rets[rets.index <= min(nav_v.index[-1], dates[-1])]

    def w_5050(d, hist):
        return {"value": 0.5, "trend": 0.5}

    def w_rp(d, hist):
        h = hist.iloc[-60:]
        sv, st = h["value"].std(), h["trend"].std()
        if not (sv > 0 and st > 0):
            return {"value": 0.5, "trend": 0.5}
        wv = (1 / sv) / (1 / sv + 1 / st)
        wv = float(np.clip(wv, 0.3, 0.7))
        return {"value": wv, "trend": 1 - wv}

    def w_3way(d, hist):
        return {"value": 0.4, "trend": 0.4}

    res = {}
    for arm, fn, cr in (("combo_5050", w_5050, 0.0), ("combo_rp", w_rp, 0.0), ("combo_3way", w_3way, CASH_RATE)):
        nav = combine(rets, fn, cash_rate=cr)
        res[arm] = series_stats(nav.pct_change().fillna(0.0))
    sleeves = {"value": series_stats(rets["value"]), "trend": series_stats(rets["trend"])}
    corr = float(rets["value"].corr(rets["trend"]))
    eq_v, eq_t = (1 + rets["value"]).cumprod(), (1 + rets["trend"]).cumprod()
    dd_v, dd_t = eq_v / eq_v.cummax() - 1, eq_t / eq_t.cummax() - 1
    both = float(((dd_v < -0.10) & (dd_t < -0.10)).mean())
    worst = {"value_at_trend_trough": float(dd_v.loc[dd_t.idxmin()]), "trend_at_value_trough": float(dd_t.loc[dd_v.idxmin()]),
             "value_trough": str(dd_v.idxmin().date()), "trend_trough": str(dd_t.idxmin().date())}
    bar = max(sleeves["value"]["sharpe"], sleeves["trend"]["sharpe"]) + 0.15
    verdict = {}
    for arm in ARMS_B:
        s = res[arm]
        why = []
        if s["sharpe"] < bar:
            why.append(f"sharpe<{bar:.2f}")
        if s["mdd"] < -0.25:
            why.append("mdd>25%")
        if s["cagr"] < 0.18:
            why.append("cagr<18%")
        if sum(1 for v in s["years"].values() if v > 0) < 5:
            why.append("years<5/6")
        verdict[arm] = "BETTER" if not why else "no: " + ",".join(why)
        print(f"B {arm:12s} cagr={s['cagr'] * 100:+5.1f}% sharpe={s['sharpe']:4.2f} mdd={s['mdd'] * 100:4.0f}% {verdict[arm]}", flush=True)
    print(f"B sleeves value cagr={sleeves['value']['cagr'] * 100:+.1f}% sh={sleeves['value']['sharpe']:.2f} mdd={sleeves['value']['mdd'] * 100:.0f}% | "
          f"trend cagr={sleeves['trend']['cagr'] * 100:+.1f}% sh={sleeves['trend']['sharpe']:.2f} mdd={sleeves['trend']['mdd'] * 100:.0f}% | corr {corr:.2f}", flush=True)
    return {"res": res, "sleeves": sleeves, "corr": corr, "both_dd10": both, "worst": worst, "verdict": verdict,
            "window": [str(rets.index[0].date()), str(rets.index[-1].date())]}


# ----------------------------------------------------------------------------------------------------------------------- family C

def sim_monthly(A, c_in, c_out, rebal_idx, targets_fn, cash_rate=CASH_RATE):
    """Monthly full-reset equal-weight book on adjusted closes. targets_fn(t) -> list of column indices (empty = all cash)."""
    Tn, N = A.shape
    dc = (1 + cash_rate) ** (1 / 252) - 1
    units: dict[int, float] = {}
    last: dict[int, float] = {}
    spell: dict[int, tuple[int, float]] = {}
    cash, nav_prev = 1.0, 1.0
    R = np.zeros(Tn)
    trades = []
    rebal = set(rebal_idx)
    for t in range(Tn):
        cash *= 1 + dc
        for j in units:
            if np.isfinite(A[t, j]):
                last[j] = A[t, j]
        nav = cash + sum(u * last.get(j, 0.0) for j, u in units.items())
        R[t] = nav / nav_prev - 1 if t > 0 else 0.0
        nav_prev = nav
        if t in rebal:
            tg = [j for j in targets_fn(t) if np.isfinite(A[t, j]) and np.isfinite(c_in[t, j])]
            tgs = set(tg)
            for j in list(units):
                if j in tgs or not (np.isfinite(A[t, j]) and np.isfinite(c_out[t, j])):
                    continue
                px = A[t, j] * (1 - c_out[t, j])
                cash += units[j] * px
                e, pin = spell.pop(j)
                trades.append((e, j, A[t, j] / pin - 1, px / pin - 1, t - e, 0.0))
                units.pop(j)
            nav = cash + sum(u * last.get(j, 0.0) for j, u in units.items())
            if tg:
                target = nav / len(tg)
                for j in tg:
                    cur = units.get(j, 0.0) * A[t, j]
                    delta = target - cur
                    if delta > 0:
                        units[j] = units.get(j, 0.0) + delta / A[t, j]
                        cash -= delta * (1 + c_in[t, j])
                        if j not in spell:
                            spell[j] = (t, A[t, j] * (1 + c_in[t, j]))
                    elif delta < 0 and np.isfinite(c_out[t, j]):
                        units[j] = units.get(j, 0.0) + delta / A[t, j]
                        cash -= delta * (1 - c_out[t, j])
                    last[j] = A[t, j]
            nav_prev = cash + sum(u * last.get(j, 0.0) for j, u in units.items())
    return pd.Series(R), trades, units


def family_c(P, unis, comp, sectors, brent):
    c_in, c_out = S.costs(P)
    adj = P["adj"]
    dates, cols = adj.index, adj.columns
    A = adj.to_numpy(float)
    ret = np.full(A.shape, np.nan)
    ret[1:] = A[1:] / A[:-1] - 1
    liq = unis["LIQ"].to_numpy(bool)
    sec = dict(zip(sectors["code"], sectors["sector"]))
    letter = np.array([(s[0] if isinstance(s, str) and len(s) > 1 and s[0] in "ABCDEFGHIJK" and s[1] == "." else "") for s in (sec.get(c) for c in cols)], dtype=object)
    names = sorted({x for x in letter if x})
    prev_liq = np.zeros_like(liq)
    prev_liq[1:] = liq[:-1]
    secret = {}
    for s in names:
        M = prev_liq & (letter == s)[None, :] & np.isfinite(ret)
        num = np.where(M, np.nan_to_num(ret), 0.0).sum(axis=1)
        den = M.sum(axis=1)
        secret[s] = np.where(den > 0, num / np.maximum(den, 1), 0.0)
    SR = pd.DataFrame(secret, index=dates)
    cum = (1 + SR).cumprod()
    mom6 = cum / cum.shift(125) - 1
    mom12_1 = cum.shift(21) / cum.shift(250) - 1
    v60 = P["v60"].to_numpy(float)
    b = brent.copy()
    b["obs_date"] = pd.to_datetime(b["obs_date"])
    bs = b.set_index("obs_date")["value"].astype(float).sort_index()
    b3 = (bs / bs.shift(63) - 1).reindex(dates, method="ffill").to_numpy(float)
    rebal_idx = [i for i, d in enumerate(dates) if i > 0 and d.month != dates[i - 1].month and d >= COMBO_START]

    def top_names(t, s, n=10):
        cand = np.flatnonzero(liq[t] & (letter == s))
        if not len(cand):
            return []
        sc = np.nan_to_num(v60[t, cand], nan=-np.inf)
        return [int(cand[i]) for i in np.argsort(-sc, kind="stable")[:n]]

    def by_mom(M):
        def f(t):
            row = M.iloc[t].dropna().sort_values(ascending=False)
            out = []
            for s in row.index[:2]:
                out += top_names(t, s)
            return out
        return f

    def cmdty(t):
        return top_names(t, "A") if (np.isfinite(b3[t]) and b3[t] > 0) else []

    rng = np.random.default_rng(SEED)

    def random2(t):
        pick = rng.choice(names, size=2, replace=False)
        out = []
        for s in pick:
            out += top_names(t, s)
        return out

    def all_liq(t):
        return [int(j) for j in np.flatnonzero(liq[t])]

    arms = {"sec_mom6": by_mom(mom6), "sec_mom12_1": by_mom(mom12_1), "sec_cmdty": cmdty}
    res, refs = {}, {}
    lo = rebal_idx[0]
    for name, fn in [*arms.items(), ("random2", random2), ("all_liq", all_liq)]:
        R, trs, open_ = sim_monthly(A, c_in, c_out, rebal_idx, fn)
        Rw = R.iloc[lo:].reset_index(drop=True)
        st = T.stats(Rw, trs, dates[lo:], N_TRIALS)
        st["open"] = len(open_)
        (res if name in arms else refs)[name] = st
        print(f"C {name:12s} n={st['n']:4d} hit={st['hit'] * 100:3.0f}% net={st['avg_net'] * 100:+5.2f}% t={st['tstat']:4.1f} cagr={st['cagr'] * 100:+5.1f}% "
              f"sharpe={st['sharpe']:4.2f} mdd={st['mdd'] * 100:4.0f}% hold={st['hold']:.0f}", flush=True)
    cc = comp.reindex(dates).ffill().iloc[lo:]
    refs["COMPOSITE"] = series_stats(cc.pct_change().fillna(0.0))
    money = {arm: money_read(res[arm], refs["random2"], years_needed=5) for arm in ARMS_C}
    sector_ranks = {s: float(SR[s].iloc[lo:].add(1).prod() - 1) for s in names}
    return {"res": res, "refs": refs, "money": money, "sectors": names, "sector_total": sector_ranks, "window": [str(dates[lo].date()), str(dates[-1].date())]}


# ----------------------------------------------------------------------------------------------------------------------- family D

def family_d(dsn):
    jk = pd.read_csv(os.path.join(YAHOO, "_JKSE.csv"), parse_dates=["date"]).set_index("date")["close"].astype(float).sort_index()
    sp = pd.read_csv(os.path.join(SCRATCH, "gspc.csv"), parse_dates=["date"]).set_index("date")["close"].astype(float).sort_index()
    with psycopg.connect(dsn) as conn:
        m = pd.read_sql("SELECT series, obs_date, value FROM idx.macro WHERE series IN ('gold', 'usdidr', 'bi_rate_hist', 'bi_rate') ORDER BY 2", conn)
    m["obs_date"] = pd.to_datetime(m["obs_date"])
    gold = m[m.series == "gold"].set_index("obs_date")["value"].astype(float)
    fx = m[m.series == "usdidr"].set_index("obs_date")["value"].astype(float)
    bi = pd.concat([m[m.series == "bi_rate_hist"].set_index("obs_date")["value"], m[m.series == "bi_rate"].set_index("obs_date")["value"]]).astype(float).sort_index()
    for k, v in BI_FILL.items():
        bi.loc[pd.Timestamp(k + "-01")] = v
    bi = bi.sort_index()
    me = lambda s: s.resample("ME").last()  # noqa: E731
    px = pd.DataFrame({"IHSG": me(jk), "SP_IDR": me(sp) * me(fx), "GOLD_IDR": me(gold) * me(fx)}).dropna()
    px = px[px.index >= "2004-12-31"]
    rate = (bi.resample("ME").last().reindex(px.index, method="ffill") - CASH_SPREAD) / 100
    rate = rate.fillna(method="ffill").fillna(5.0 / 100)
    cash_m = (1 + rate) ** (1 / 12) - 1
    rets = px.pct_change()
    mom = px / px.shift(12) - 1
    cash12 = (1 + cash_m).rolling(12).apply(np.prod, raw=True) - 1
    idx = px.index
    out = {}

    def run(choose):
        R, prev = [], None
        for i in range(12, len(idx) - 1):
            a = choose(i)
            r = float(cash_m.iloc[i + 1]) if a == "CASH" else float(rets.iloc[i + 1][a])
            if prev is not None and a != prev and not (a == "CASH" and prev == "CASH"):
                r -= SWITCH_COST
            prev = a
            R.append((idx[i + 1], r, a))
        s = pd.Series([x[1] for x in R], index=[x[0] for x in R])
        st = series_stats(s, per_year=12)
        st["switches"] = int(sum(1 for k in range(1, len(R)) if R[k][2] != R[k - 1][2]))
        st["time_in"] = {a: float(np.mean([x[2] == a for x in R])) for a in ("IHSG", "SP_IDR", "GOLD_IDR", "CASH")}
        return st, s

    def gem(i):
        if mom.iloc[i]["IHSG"] > cash12.iloc[i]:
            return "IHSG" if mom.iloc[i]["IHSG"] >= mom.iloc[i]["SP_IDR"] else "SP_IDR"
        return "CASH"

    def dm3(i):
        row = mom.iloc[i][["IHSG", "SP_IDR", "GOLD_IDR"]]
        best = row.idxmax()
        return best if row[best] > cash12.iloc[i] else "CASH"

    res = {}
    res["gem_idr"], _ = run(gem)
    res["dm3_idr"], _ = run(dm3)
    # sensitivity (descriptive, not a trial): price indices carry no dividends; add a flat 2.5 %/yr to IHSG and 1.8 %/yr to the S&P while held
    div_m = {"IHSG": (1.025) ** (1 / 12) - 1, "SP_IDR": (1.018) ** (1 / 12) - 1, "GOLD_IDR": 0.0}
    rets_nodiv = rets.copy()
    for k, v in div_m.items():
        rets[k] = rets[k] + v
    with_div = {"gem_idr": run(gem)[0], "dm3_idr": run(dm3)[0], "IHSG": run(lambda i: "IHSG")[0],
                "EW3": series_stats(rets.iloc[13:][["IHSG", "SP_IDR", "GOLD_IDR"]].mean(axis=1), per_year=12)}
    rets = rets_nodiv
    refs = {}
    refs["IHSG"], _ = run(lambda i: "IHSG")
    refs["SP_IDR"], _ = run(lambda i: "SP_IDR")
    refs["GOLD_IDR"], _ = run(lambda i: "GOLD_IDR")
    refs["CASH"], _ = run(lambda i: "CASH")
    sub = rets.iloc[13:]
    cm = cash_m.iloc[13:]
    refs["60_40"] = series_stats(0.6 * sub["IHSG"] + 0.4 * cm, per_year=12)
    refs["EW3"] = series_stats(sub[["IHSG", "SP_IDR", "GOLD_IDR"]].mean(axis=1), per_year=12)
    ih = refs["IHSG"]
    verdict = {}
    for arm in ARMS_D:
        s = res[arm]
        why = []
        if s["sharpe"] < ih["sharpe"] + 0.30:
            why.append(f"sharpe<IHSG+0.30")
        if s["mdd"] < -0.25:
            why.append("mdd>25%")
        if s["cagr"] < ih["cagr"]:
            why.append("cagr<IHSG")
        ny = len(s["years"])
        if sum(1 for v in s["years"].values() if v > 0) < math.ceil(2 * ny / 3):
            why.append("years<2/3")
        verdict[arm] = "BETTER" if not why else "no: " + ",".join(why)
        print(f"D {arm:10s} cagr={s['cagr'] * 100:+5.1f}% sharpe={s['sharpe']:4.2f} mdd={s['mdd'] * 100:4.0f}% switches={s['switches']} {verdict[arm]}", flush=True)
    for k, s in refs.items():
        print(f"D ref {k:8s} cagr={s['cagr'] * 100:+5.1f}% sharpe={s['sharpe']:4.2f} mdd={s['mdd'] * 100:4.0f}%", flush=True)
    return {"res": res, "refs": refs, "verdict": verdict, "with_div": with_div, "window": [str(idx[13].date()), str(idx[-1].date())], "bi_fill": BI_FILL}


# ----------------------------------------------------------------------------------------------------------------------- report

def report(out: dict, path: str):
    L = [f"# IDX menu 21 — beyond the two engines: sizing, combination, sector rotation, allocation — {date.today()} — {len(ALL_ARMS)} trials, cumulative N = {N_TRIALS}", "",
         "Incumbents: value = strict composite, May, rev. 3 (18-22 %/yr, mDD 22-25 %); trend = hi60 / > MA200 / vol >= 1.5x / trail10, K = 10, `small` "
         "(+29.9 %/yr, Sharpe 1.34, mDD -30 % to 2026-09-16). Everything below is measured with the same engines, costs and reading rules as menus 6-20.", ""]

    def row_t(label, s, extra):
        return (f"| {label} | {s['n']} | {s['hold']:.0f} | {s['hit'] * 100:.0f} % | {s['avg_net'] * 100:+.2f} % | {s['payoff']:.2f} | {s['tstat']:.1f} | "
                f"{s['cagr'] * 100:+.1f} % | {s['sharpe']:.2f} | {s['mdd'] * 100:.0f} % | {yrs(s['years'])} | {extra} |")
    hdr_t = ["| arm | trades | hold d | hit | avg net | payoff | t | CAGR | Sharpe | mDD | years | verdict |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    if "A" in out:
        a = out["A"]
        L += ["## A. Position sizing on the trend sleeve (10 trials)", "",
              "Only the slot size changes; entry, exit, book, costs, execution as deployed. voltarget / regime_half scale the whole book from the prior close "
              "(trade statistics are then the reference's; the book numbers change). Random = random entries with the same sizing and exit.", ""]
        for u in UNIS:
            L += [f"### Universe `{u}`" + (" (deployed: paper_trend, trend_live)" if u == "small" else ""), "", *hdr_t,
                  row_t("**equal 1/K** (deployed)", a["refs"][u], "reference"), row_t("random + trail10", a["refs"][u + "_rnd"], "reference")]
            for s in SIZINGS:
                arm = f"{s}|{u}"
                L.append(row_t(s, a["res"][arm], f"{a['better'][arm]} / {a['money'][arm]} (rnd Sharpe {a['rnd'][arm]['sharpe']:.2f})"))
            L.append("")
        L += [f"BETTER than equal slots on both universes (adoption rule): {', '.join(a['adopt']) if a['adopt'] else 'none'}.",
              f"BETTER on one universe only (informative): {', '.join(a['informative']) if a['informative'] else 'none'}.",
              f"Candidates for money: {sum(1 for v in a['money'].values() if v == 'CANDIDATE')} of {len(ARMS_A)}.", ""]
        if "R" in out:
            r = out["R"]
            L += ["### Robustness 2005-2019 (`small`, Yahoo survivors file, flat 0.30 % half-spread; descriptive)", "",
                  "| rule | trades | hit | avg net | t | CAGR | Sharpe | mDD | years | read |", "|---|---|---|---|---|---|---|---|---|---|"]
            for k, s in r.items():
                rd = "reference" if k == "ref" else ("CONFIRMED" if s["sharpe"] >= r["ref"]["sharpe"] + 0.15 else "not confirmed")
                L.append(f"| {k} | {s['n']} | {s['hit'] * 100:.0f} % | {s['avg_net'] * 100:+.2f} % | {s['tstat']:.1f} | {s['cagr'] * 100:+.1f} % | {s['sharpe']:.2f} | {s['mdd'] * 100:.0f} % | {yrs(s['years'])} | {rd} |")
            L.append("")
    if "A2" in out:
        a2 = out["A2"]
        L += ["## A2. Follow-up declared after reading A (1 trial, cumulative N = 429): regime-sized ENTRIES, the implementable form", "",
              "A new position takes half a slot when COMPOSITE < its 200-day average at the signal close, a full slot otherwise; held positions are never "
              "resized. Share of trading days with the regime off: " + ", ".join(f"{y}: {v * 100:.0f} %" for y, v in a2["off_share"].items()) + ".", "", *hdr_t]
        for u in UNIS:
            L.append(row_t(f"equal 1/K | {u}", a2["refs"][u], "reference"))
            L.append(row_t(f"regime_entry | {u}", a2["res"][u], f"{a2['better'][u]} / {a2['money'][u]} (rnd Sharpe {a2['rnd'][u]['sharpe']:.2f})"))
        r = a2["robust"]
        L += ["", "2005-2019 (`small`, Yahoo survivors file): " + " | ".join(f"{k}: CAGR {s['cagr'] * 100:+.1f} %, Sharpe {s['sharpe']:.2f}, mDD {s['mdd'] * 100:.0f} %, years {yrs(s['years'])}" for k, s in r.items()), ""]
    if "A3" in out:
        a3 = out["A3"]
        L += ["## A3. Follow-up declared after the operator's question (4 trials, cumulative N = 433): no trading under the 200-day average", "",
              "regime_gate = no new entry while COMPOSITE < MA200, held names run to their trailing stop; regime_flat = sell everything at the first close "
              "under MA200 (next close, at the bid) and stay out until COMPOSITE is back above. Exit and re-entry costs are inside the engine.", "", *hdr_t]
        for u in UNIS:
            L.append(row_t(f"equal 1/K | {u}", a3["refs"][u], "reference"))
            for name in ("regime_gate", "regime_flat"):
                arm = f"{name}|{u}"
                L.append(row_t(f"{name} | {u}", a3["res"][arm], f"{a3['better'][arm]} / {a3['money'][arm]} (rnd Sharpe {a3['rnd'][arm]['sharpe']:.2f})"))
        r = a3["robust"]
        L += ["", "2005-2019 (`small`, Yahoo survivors file):", "", *hdr_t, row_t("equal 1/K", r["refs"]["small"], "reference")]
        for name in ("regime_gate", "regime_flat"):
            arm = f"{name}|small"
            L.append(row_t(name, r["res"][arm], f"{r['better'][arm]} (rnd Sharpe {r['rnd'][arm]['sharpe']:.2f})"))
        L.append("")
    if "B" in out:
        b = out["B"]
        L += [f"## B. The combined book: value + trend as one book (3 trials), {b['window'][0]} -> {b['window'][1]}", "",
              f"Daily-return correlation of the sleeves: {b['corr']:+.2f}. Days with both sleeves > 10 % under water: {b['both_dd10'] * 100:.0f} %. "
              f"Value at the trend trough ({b['worst']['trend_trough']}): {b['worst']['value_at_trend_trough'] * 100:.0f} %; trend at the value trough "
              f"({b['worst']['value_trough']}): {b['worst']['trend_at_value_trough'] * 100:.0f} %.", "",
              "| book | CAGR | vol | Sharpe | mDD | years | verdict |", "|---|---|---|---|---|---|---|"]
        for k in ("value", "trend"):
            s = b["sleeves"][k]
            L.append(f"| {k} alone | {s['cagr'] * 100:+.1f} % | {s['vol'] * 100:.0f} % | {s['sharpe']:.2f} | {s['mdd'] * 100:.0f} % | {yrs(s['years'])} | reference (what runs today, separately) |")
        for arm in ARMS_B:
            s = b["res"][arm]
            L.append(f"| {arm} | {s['cagr'] * 100:+.1f} % | {s['vol'] * 100:.0f} % | {s['sharpe']:.2f} | {s['mdd'] * 100:.0f} % | {yrs(s['years'])} | {b['verdict'][arm]} |")
        L.append("")
    if "C" in out:
        c = out["C"]
        L += [f"## C. Sector rotation (3 trials), {c['window'][0]} -> {c['window'][1]}, sectors {', '.join(c['sectors'])}", "", *hdr_t]
        for arm in ARMS_C:
            L.append(row_t(arm, c["res"][arm], c["money"][arm]))
        for k in ("random2", "all_liq"):
            L.append(row_t(k, c["refs"][k], "reference"))
        s = c["refs"]["COMPOSITE"]
        L += [f"| COMPOSITE | - | - | - | - | - | - | {s['cagr'] * 100:+.1f} % | {s['sharpe']:.2f} | {s['mdd'] * 100:.0f} % | {yrs(s['years'])} | reference |", "",
              "Sector equal-weight LIQ total return over the window: " + ", ".join(f"{k} {v * 100:+.0f} %" for k, v in sorted(c["sector_total"].items(), key=lambda x: -x[1])) + ".", ""]
    if "D" in out:
        d = out["D"]
        L += [f"## D. The allocation layer in rupiah (2 trials), monthly {d['window'][0]} -> {d['window'][1]}", "",
              f"Cash = BI rate - {CASH_SPREAD} points; BI 2024-25 filled by hand: {d['bi_fill']}. Switch cost {SWITCH_COST * 100:.2f} %.", "",
              "| arm | CAGR | vol | Sharpe | mDD | switches | time in IHSG / S&P / gold / cash | years | verdict |", "|---|---|---|---|---|---|---|---|---|"]
        for arm in ARMS_D:
            s = d["res"][arm]
            ti = s["time_in"]
            L.append(f"| {arm} | {s['cagr'] * 100:+.1f} % | {s['vol'] * 100:.0f} % | {s['sharpe']:.2f} | {s['mdd'] * 100:.0f} % | {s['switches']} | "
                     f"{ti['IHSG'] * 100:.0f} / {ti['SP_IDR'] * 100:.0f} / {ti['GOLD_IDR'] * 100:.0f} / {ti['CASH'] * 100:.0f} % | {yrs(s['years'])} | {d['verdict'][arm]} |")
        for k, s in d["refs"].items():
            L.append(f"| {k} | {s['cagr'] * 100:+.1f} % | {s['vol'] * 100:.0f} % | {s['sharpe']:.2f} | {s['mdd'] * 100:.0f} % | - | - | {yrs(s['years'])} | reference |")
        L += ["", "Dividend sensitivity (descriptive): the same arms with a flat 2.5 %/yr added to IHSG and 1.8 %/yr to the S&P while held (price indices carry none):", "",
              "| arm | CAGR | Sharpe | mDD |", "|---|---|---|---|"]
        for k, s in d["with_div"].items():
            L.append(f"| {k} | {s['cagr'] * 100:+.1f} % | {s['sharpe']:.2f} | {s['mdd'] * 100:.0f} % |")
        L.append("")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    print("\n".join(L))
    print("wrote", path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", default="A,B,C,D")
    ap.add_argument("--no-store", action="store_true")
    ap.add_argument("--robust", default="", help="sizing rules to re-run 2005-2019 (default: the BETTER ones)")
    ap.add_argument("--out", default="", help="report path (default research/IDX_BEYOND_<date>.md)")
    ap.add_argument("--study-name", default="beyond_engines")
    args = ap.parse_args()
    fams = [f.strip().upper() for f in args.family.split(",")]
    dsn = os.environ["INGEST_DB_DSN"]
    out = {}
    need_panels = any(f in fams for f in ("A", "A2", "A3", "B", "C"))
    if need_panels:
        P, unis, comp, Hp, Lp, sectors, brent = load_all(dsn, os.environ.get("IDX_BEYOND_CACHE"))
        print(f"panels {P['adj'].index[0].date()} -> {P['adj'].index[-1].date()}, {P['adj'].shape[1]} names", flush=True)
    if "A" in fams:
        out["A"] = family_a(P, unis, comp, Hp, Lp)
        rob = [s for s in args.robust.split(",") if s] or sorted(set(out["A"]["adopt"] + out["A"]["informative"]))
        if rob:
            out["R"] = family_a_robust(rob)
    if "A2" in fams:
        out["A2"] = family_a2(P, unis, comp, Hp, Lp)
        out["A2"]["robust"] = family_a2_robust()
    if "A3" in fams:
        out["A3"] = family_a3(P, unis, comp, Hp, Lp)
        out["A3"]["robust"] = family_a3_robust()
    if "B" in fams:
        out["B"] = family_b(dsn, P, unis, Hp, Lp)
    if "C" in fams:
        out["C"] = family_c(P, unis, comp, sectors, brent)
    if "D" in fams:
        out["D"] = family_d(dsn)
    path = args.out or os.path.join(HERE, f"IDX_BEYOND_{date.today().isoformat()}.md")
    report(out, path)
    if not args.no_store:
        from blackheart_ingest.idx import research_store as rs
        summary = json.loads(json.dumps(out, default=str))
        n_c = sum(1 for k in ("A",) if k in out for v in out[k]["money"].values() if v == "CANDIDATE")
        n_c += sum(1 for k in ("C",) if k in out for v in out[k]["money"].values() if v == "CANDIDATE")
        n_b = sum(1 for k in ("B", "D") if k in out for v in out[k]["verdict"].values() if v == "BETTER")
        note = (f"money candidates {n_c}; BETTER-than-incumbent {n_b}; adopt A {out.get('A', {}).get('adopt', [])}; "
                f"B {out.get('B', {}).get('verdict', {})}; D {out.get('D', {}).get('verdict', {})}")
        with psycopg.connect(dsn) as conn:
            sid = rs.record_study(conn, args.study_name, date(2026, 9, 21), params={"trials": ALL_ARMS, "n_trials_cumulative": N_TRIALS, "K": K, "seed": SEED,
                                                                                    "families": fams}, summary=summary, names=[], report_path=path, note=note)
            print(f"study #{sid} stored")


if __name__ == "__main__":
    main()
