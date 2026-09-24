#!/usr/bin/env python3
"""IDX - konsolidasi lalu breakout volume: berapa yang LANJUT naik dan berapa yang FALSE BREAKOUT (operator, 2026-09-24:
"cari saham2 konsolidasi lalu terjadi breakout volume, coba cari statistiknya berapa banyak yang melanjutkan kenaikan
harga atau false breakout").

DESCRIPTIVE ONLY - this is a base-rate count, not a rule search. No new money-rule trials (cumulative stays 711). The
trading version of this family was already tested and closed: menu 27 (study #69) A-arms base_break|LIQ +7.9 %/yr
Sharpe 0.71 and base_break|small +9.4 %/yr Sharpe 0.89 against the deployed 60-day-high trend rule's +19 % / +29.5 %.
What was never reported is the statistic itself: of every consolidation break on volume, how many hold and how many
fall straight back into the base.

PRE-REGISTERED DEFINITIONS (declared before the run; nothing tuned afterwards).
  Panel: idx.bar primary feed, boards Utama + Pengembangan, 2020-01-02 -> 2026-09-16, adjusted closes/highs/lows.
  Tiers (point-in-time, 60-day median traded value): BLUE >= Rp 20 bn & px >= 1000; LIQ >= Rp 5 bn & px >= 100;
    small = LIQ minus BLUE (the trend books' universe); THIN >= Rp 0.5 bn & px >= 100.
  CONSOLIDATION (base) measured on the L closes ending t-1, primary `base60`: L = 60, channel width (max/min - 1)
    <= 25 %, |net move over L| <= 15 %, efficiency ratio |close_t-1 - close_t-1-L| / sum|daily change| <= 0.30.
    Neighbours (for the stability of the statistic, not trials): base120 (L=120, 35 %, 10 %, 0.25 = the menu-26
    screen), base20 (L=20, 12 %, 8 %, 0.35), tight60 (width <= 15 %), loose60 (35 %, 20 %, 0.40).
  BASE TOP hi = max of the L closes ending t-1. BREAKOUT day t: close_t > hi. One event per name per 20 trading days
    (the first break of the base). VOLUME RATIO vr = volume_t / median(volume, 20 d ending t-1) - recorded per event,
    so every volume cut is a slice of one event set. "Volume breakout" = vr >= 2.
  FALSE BREAKOUT (the count asked for) = the first close back BELOW the base top hi within N days, N = 3, 5, 10, 20.
    Soft variant: close < 0.97 x hi. Suspension note: an event whose forward close is missing is counted in `stale`
    and left out of the return means.
  CONTINUATION: return from the breakout close at +5/+10/+20/+60 days; share positive; share still above hi at +20;
    MFE/MAE from the breakout close over the next 20 days on adjusted highs/lows; `runner` = the high reaches
    >= +10 % within 20 days; `clean runner` = it reaches +10 % BEFORE any close falls back below hi.
  TRADEABLE column: buy the close t+1 at the quoted offer + 0.10 % fee, sell the close t+20 at the bid + 0.20 %
    (the desk cost model) - the 1-day-late fill the desk knows the trend rule needs.
  CONTROLS (matched on the same days, seeded): `no volume` = the same base breaks with vr < 1; `inside base` = names
    inside a base that did not break that day; `random` = random names in the same tier on the same days.
  CUTS: tier, volume bucket, breakout-day return bucket, index regime (COMPOSITE >= / < MA200), calendar year.
READ-ONLY. INGEST_DB_DSN=... PYTHONIOENCODING=utf-8 blackheart-ingest/.venv/Scripts/python research/idx_breakout_stats.py [--no-store]
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
import idx_swing2 as S  # noqa: E402

SEED = 20260924
N_TRIALS = 711  # descriptive study: no new money-rule trials
GAP = 20        # one event per name per 20 trading days
HOR = (5, 10, 20, 60)
FAILS = (3, 5, 10, 20)
RUN = 0.10
BASES = {
    "base60":  dict(L=60,  width=0.25, move=0.15, er=0.30),
    "base120": dict(L=120, width=0.35, move=0.10, er=0.25),
    "base20":  dict(L=20,  width=0.12, move=0.08, er=0.35),
    "tight60": dict(L=60,  width=0.15, move=0.15, er=0.30),
    "loose60": dict(L=60,  width=0.35, move=0.20, er=0.40),
}
TIERS = ("BLUE", "LIQ", "small", "THIN")
VOL_BUCKETS = [("vr<1", 0.0, 1.0), ("1-1.5", 1.0, 1.5), ("1.5-2", 1.5, 2.0), ("2-3", 2.0, 3.0), ("3-5", 3.0, 5.0), ("5+", 5.0, 1e9)]
DAY_BUCKETS = [("<2 %", -1.0, 0.02), ("2-5 %", 0.02, 0.05), ("5-10 %", 0.05, 0.10), ("10-20 %", 0.10, 0.20), ("20 %+", 0.20, 9.0)]


# --------------------------------------------------------------------------------------------------------- panels

def base_panels(adj: pd.DataFrame, L: int, width: float, move: float, er: float):
    """Base mask and base-top level at t, both measured on the L closes ending t-1."""
    mx = adj.rolling(L, min_periods=L).max()
    mn = adj.rolling(L, min_periods=L).min()
    w = mx / mn - 1
    nm = (adj / adj.shift(L) - 1).abs()
    e = (adj - adj.shift(L)).abs() / adj.diff().abs().rolling(L, min_periods=L).sum()
    m = (w <= width) & (nm <= move) & (e <= er)
    return m.shift(1).fillna(False), mx.shift(1), w.shift(1)


def tiers_of(P, unis):
    close, vol, adj, v60 = P["close"], P["volume"], P["adj"], P["v60"]
    liq, blue = unis["LIQ"], unis["BLUE"]
    thin = (v60 >= 0.5e9) & (close >= S.MIN_PRICE) & (vol > 0) & adj.notna()
    return {"BLUE": blue, "LIQ": liq, "small": liq & ~blue, "THIN": thin}


def events_for(adj, base, HI, tier):
    raw = base & (adj > HI) & tier & adj.notna() & HI.notna()
    prior = raw.astype(float).rolling(GAP, min_periods=1).sum().shift(1).fillna(0)
    return (raw & (prior == 0)).to_numpy(bool)


# --------------------------------------------------------------------------------------------------- measurement

def measure(A, Hh, Ll, c_in, c_out, ti, tj, lvl):
    """Per-event forward outcomes from the breakout close A[t, j]. lvl = the base top (NaN for controls)."""
    T = A.shape[0]
    n = len(ti)
    out = {f"r{h}": np.full(n, np.nan) for h in HOR}
    out["net20"] = np.full(n, np.nan)
    out["mfe"] = np.full(n, np.nan)
    out["mae"] = np.full(n, np.nan)
    out["fail"] = np.full(n, 999)          # first day the close is back below the base top
    out["fail_soft"] = np.full(n, 999)
    out["first_up"] = np.full(n, 999)      # first day the high reaches +RUN
    out["above20"] = np.full(n, np.nan)
    out["stale"] = np.zeros(n, bool)
    out["complete"] = (np.asarray(ti) + 20) < T   # a full 20-day forward window exists in the panel
    out["alive"] = {k: np.full(n, np.nan) for k in (1, 3, 5, 10, 20)}   # close still >= base top at day k
    out["lvl"] = np.asarray(lvl, float)
    for i in range(n):
        t, j, L0 = ti[i], tj[i], lvl[i]
        p0 = A[t, j]
        if not np.isfinite(p0) or p0 <= 0:
            out["stale"][i] = True
            continue
        for h in HOR:
            if t + h < T:
                v = A[t + h, j]
                if np.isfinite(v):
                    out[f"r{h}"][i] = v / p0 - 1
        if t + 20 < T and np.isfinite(A[t + 1, j]) and np.isfinite(A[t + 20, j]):
            buy = A[t + 1, j] * (1 + c_in[t + 1, j])
            sell = A[t + 20, j] * (1 - c_out[t + 20, j])
            if np.isfinite(buy) and buy > 0 and np.isfinite(sell):
                out["net20"][i] = sell / buy - 1
        hi_run, lo_run = -np.inf, np.inf
        for k in range(1, 21):
            if t + k >= T:
                break
            hv, lv, cv = Hh[t + k, j], Ll[t + k, j], A[t + k, j]
            if np.isfinite(hv):
                hi_run = max(hi_run, hv)
            if np.isfinite(lv):
                lo_run = min(lo_run, lv)
            if np.isfinite(hv) and out["first_up"][i] == 999 and hv >= p0 * (1 + RUN):
                out["first_up"][i] = k
            if np.isfinite(L0) and np.isfinite(cv):
                if out["fail"][i] == 999 and cv < L0:
                    out["fail"][i] = k
                if out["fail_soft"][i] == 999 and cv < 0.97 * L0:
                    out["fail_soft"][i] = k
        if np.isfinite(hi_run):
            out["mfe"][i] = hi_run / p0 - 1
        if np.isfinite(lo_run):
            out["mae"][i] = lo_run / p0 - 1
        for k in out["alive"]:
            if np.isfinite(L0) and t + k < T and np.isfinite(A[t + k, j]):
                out["alive"][k][i] = float(A[t + k, j] >= L0)
        if np.isfinite(L0) and t + 20 < T and np.isfinite(A[t + 20, j]):
            out["above20"][i] = float(A[t + 20, j] >= L0)
        if not np.isfinite(out["r20"][i]):
            out["stale"][i] = True
    return out


def wilson(k, n, z=1.96):
    """95 % Wilson interval for a share - the honest band on a count this size."""
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    c = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((p + z * z / (2 * n) - c) / (1 + z * z / n), (p + z * z / (2 * n) + c) / (1 + z * z / n))


def summarize(m, sel=None):
    if sel is None:
        sel = np.ones(len(m["r20"]), bool)
    sel = sel & m["complete"]          # only events with a full 20-day forward window
    n = int(sel.sum())
    d = {"n": n, "has_level": bool(np.isfinite(m["lvl"][sel]).any())}
    if n == 0:
        return d
    pick = lambda k: m[k][sel]  # noqa: E731

    def f(a):
        return float(np.nanmean(a)) if np.isfinite(a).any() else float("nan")

    def med(a):
        return float(np.nanmedian(a)) if np.isfinite(a).any() else float("nan")

    def share_pos(a):
        ok = np.isfinite(a)
        return float((a[ok] > 0).mean()) if ok.any() else float("nan")

    for N in FAILS:
        d[f"fail{N}"] = float((pick("fail") <= N).mean())
    d["fail_soft5"] = float((pick("fail_soft") <= 5).mean())
    d["above20"] = f(pick("above20"))
    for h in HOR:
        r = pick(f"r{h}")
        d[f"r{h}_med"] = med(r)
        d[f"r{h}_avg"] = f(r)
        d[f"r{h}_pos"] = share_pos(r)
    net = pick("net20")
    d["net20_avg"], d["net20_med"], d["net20_pos"] = f(net), med(net), share_pos(net)
    d["mfe_med"], d["mae_med"] = med(pick("mfe")), med(pick("mae"))
    d["runner"] = float((pick("mfe") >= RUN).mean())
    d["clean"] = float(((pick("first_up") < pick("fail")) & (pick("first_up") < 999)).mean())
    d["big_loss"] = float((pick("mae") <= -0.10).mean())
    r20 = pick("r20")
    win, lose = r20[np.isfinite(r20) & (r20 > 0)], r20[np.isfinite(r20) & (r20 <= 0)]
    d["win_med"] = float(np.median(win)) if len(win) else float("nan")
    d["lose_med"] = float(np.median(lose)) if len(lose) else float("nan")
    d["stale"] = float(pick("stale").mean())
    d["alive"] = {}
    for k in m["alive"]:
        a = m["alive"][k][sel]
        d["alive"][str(k)] = float(np.nanmean(a)) if np.isfinite(a).any() else float("nan")
    d["fail5_ci"] = list(wilson(int((pick("fail") <= 5).sum()), n))
    r20ok = np.isfinite(r20)
    d["r20_pos_ci"] = list(wilson(int((r20[r20ok] > 0).sum()), int(r20ok.sum())))
    d["runner_ci"] = list(wilson(int((pick("mfe") >= RUN).sum()), n))
    return d


# ------------------------------------------------------------------------------------------------------- report

def pct(x, sign=False):
    if x is None or not np.isfinite(x):
        return "-"
    return f"{x * 100:+.1f} %" if sign else f"{x * 100:.0f} %"


def row(label, d):
    if d["n"] == 0:
        return f"| {label} | 0 | | | | | | | | | |"
    lv = d.get("has_level", True)
    cell = lambda v, sign=False: (pct(v, sign) if lv else "n/a")  # noqa: E731
    return (f"| {label} | {d['n']} | {cell(d['fail3'])} | {cell(d['fail5'])} | {cell(d['fail20'])} | {cell(d['above20'])} | "
            f"{pct(d['r20_pos'])} | {pct(d['r20_med'], True)} | {pct(d['r20_avg'], True)} | {pct(d['runner'])} | {cell(d['clean'])} |")


HDR = ["| cut | events | back in <=3 d | <=5 d | <=20 d | above top @20 d | up @20 d | median 20 d | avg 20 d | ran +10 % | clean run |",
       "|---|---|---|---|---|---|---|---|---|---|---|"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-store", action="store_true")
    args = ap.parse_args()
    dsn = os.environ["INGEST_DB_DSN"]
    with psycopg.connect(dsn) as conn:                       # take the panel to the last bar the feed has
        last_bar = pd.read_sql("SELECT max(trade_date) AS d FROM idx.bar WHERE source = 'idx'", conn)["d"].iloc[0]
    B.S.END = last_bar
    cache = os.environ.get("IDX_BEYOND_CACHE")
    if cache:
        cache = f"{cache}.{last_bar}"
    P, unis, comp, Hp, Lp, sectors, brent = B.load_all(dsn, cache)
    adj = P["adj"]
    dates, cols = adj.index, adj.columns
    A, Hh, Ll = adj.to_numpy(float), Hp.to_numpy(float), Lp.to_numpy(float)
    c_in, c_out = S.costs(P)
    tiers = tiers_of(P, unis)
    vmed = P["volume"].rolling(20, min_periods=20).median().shift(1)
    VR = (P["volume"] / vmed.replace(0, np.nan)).to_numpy(float)
    R1 = (adj / adj.shift(1) - 1).to_numpy(float)
    cm = comp.reindex(dates).ffill()
    regime = (cm >= cm.rolling(200, min_periods=200).mean()).to_numpy(bool)
    years = dates.year.to_numpy()
    rng = np.random.default_rng(SEED)
    print(f"panel {dates[0].date()} -> {dates[-1].date()}, {len(cols)} names, {len(dates)} days", flush=True)

    out = {"panel": {"start": str(dates[0].date()), "end": str(dates[-1].date()), "names": int(len(cols)), "days": int(len(dates))},
           "universe": {}, "primary": {}, "bases": {}, "vol": {}, "day": {}, "regime": {}, "year": {}, "controls": {}, "examples": {}}
    ev_cache = {}
    base60 = HI60 = None
    for bname, bp in BASES.items():
        base, HI, W = base_panels(adj, bp["L"], bp["width"], bp["move"], bp["er"])
        if bname == "base60":
            base60, HI60 = base, HI
        HIn = HI.to_numpy(float)
        for tname in TIERS:
            if bname != "base60" and tname != "LIQ":
                continue
            E = events_for(adj, base, HI, tiers[tname])
            ti, tj = np.nonzero(E)
            lvl = HIn[ti, tj]
            m = measure(A, Hh, Ll, c_in, c_out, ti, tj, lvl)
            m["vr"] = VR[ti, tj]
            m["r1"] = R1[ti, tj]
            m["gap"] = A[ti, tj] / lvl - 1
            m["reg"] = regime[ti]
            m["yr"] = years[ti]
            m["ti"], m["tj"] = ti, tj
            ev_cache[(bname, tname)] = m
            in_base = (base & tiers[tname]).to_numpy(bool)
            print(f"{bname}/{tname}: {len(ti)} breakouts, in-base share {in_base.mean() * 100:.1f} %", flush=True)
            if bname == "base60":
                nd = in_base.sum(axis=1)
                out["universe"][tname] = {"names_in_base_median": float(np.median(nd[nd > 0])) if (nd > 0).any() else 0.0,
                                          "breakouts": int(len(ti)), "with_volume": int((m["vr"] >= 2).sum())}

    # 1. headline: base60, vr >= 2, per tier
    for tname in TIERS:
        m = ev_cache[("base60", tname)]
        out["primary"][tname] = summarize(m, m["vr"] >= 2)
    # 2. base definition stability (LIQ, vr >= 2)
    for bname in BASES:
        m = ev_cache[(bname, "LIQ")]
        out["bases"][bname] = summarize(m, m["vr"] >= 2)
    # 3. volume buckets
    for tname in ("LIQ", "small", "THIN"):
        m = ev_cache[("base60", tname)]
        out["vol"][tname] = {lab: summarize(m, (m["vr"] >= a) & (m["vr"] < b)) for lab, a, b in VOL_BUCKETS}
    # 4. breakout-day return buckets, regime, year (LIQ)
    m = ev_cache[("base60", "LIQ")]
    volsel = m["vr"] >= 2
    out["day"] = {lab: summarize(m, volsel & (m["r1"] >= a) & (m["r1"] < b)) for lab, a, b in DAY_BUCKETS}
    out["regime"] = {"COMPOSITE >= MA200": summarize(m, volsel & m["reg"]), "COMPOSITE < MA200": summarize(m, volsel & ~m["reg"])}
    out["year"] = {str(y): summarize(m, volsel & (m["yr"] == y)) for y in sorted(set(years.tolist()))}
    # 5. controls on LIQ, matched on the breakout days
    out["controls"]["volume break (vr>=2)"] = out["primary"]["LIQ"]
    out["controls"]["no volume (vr<1)"] = summarize(m, m["vr"] < 1)
    ev_days = np.unique(m["ti"][volsel])
    liqn = tiers["LIQ"].to_numpy(bool)
    basen = (base60 & tiers["LIQ"]).to_numpy(bool)
    brk = np.zeros_like(basen)
    brk[m["ti"], m["tj"]] = True
    for label, pool in (("inside base, no break", basen & ~brk), ("random LIQ name", liqn & ~brk)):
        ti_c, tj_c = [], []
        want = min(5 * int(volsel.sum()), 40000)
        per = max(1, want // max(1, len(ev_days)))
        for t in ev_days:
            js = np.flatnonzero(pool[t])
            if len(js) == 0:
                continue
            take = rng.choice(js, size=min(per, len(js)), replace=False)
            ti_c += [t] * len(take)
            tj_c += list(take)
        ti_c, tj_c = np.array(ti_c), np.array(tj_c)
        mc = measure(A, Hh, Ll, c_in, c_out, ti_c, tj_c, np.full(len(ti_c), np.nan))
        out["controls"][label] = summarize(mc)
    # 6. the most recent volume breakouts
    recent = np.argsort(m["ti"])[::-1]
    ex = []
    for i in recent:
        if not volsel[i] or len(ex) >= 15:
            continue
        ex.append({"date": str(dates[m["ti"][i]].date()), "code": cols[m["tj"][i]], "vr": float(m["vr"][i]), "day_ret": float(m["r1"][i]),
                   "r20": float(m["r20"][i]) if np.isfinite(m["r20"][i]) else None, "fail": int(m["fail"][i]),
                   "mfe": float(m["mfe"][i]) if np.isfinite(m["mfe"][i]) else None})
    out["examples"] = ex

    # ------------------------------------------------------------------------------------------------- markdown
    P0 = out["primary"]["LIQ"]
    Lns = [f"# IDX - konsolidasi -> breakout volume: lanjut atau false breakout - {date.today()} - descriptive, 0 new trials (cumulative N = {N_TRIALS})", "",
           f"Panel idx.bar {out['panel']['start']} -> {out['panel']['end']}, {out['panel']['names']} names, {out['panel']['days']} trading days. "
           f"Base = 60 closes ending t-1 inside a <= 25 % channel, |net move| <= 15 %, efficiency ratio <= 0.30; base top = the highest of those 60 closes; "
           f"breakout = close above it, one event per name per {GAP} days; volume breakout = volume >= 2 x its 20-day median. "
           f"'Back in' = a close back below the base top. All returns from the breakout close on adjusted prices unless marked net.", "",
           "## 1. Headline - base60, volume >= 2x, by liquidity tier", "", *HDR]
    for t in TIERS:
        Lns.append(row(t, out["primary"][t]))
    Lns += ["", "| tier | events | net +20 d, next-close fill w/ costs | up after costs | median MFE 20 d | median MAE 20 d | fell >=10 % | median winner | median loser |",
            "|---|---|---|---|---|---|---|---|---|"]
    for t in TIERS:
        d = out["primary"][t]
        Lns.append(f"| {t} | {d['n']} | {pct(d.get('net20_avg'), True)} | {pct(d.get('net20_pos'))} | {pct(d.get('mfe_med'), True)} | {pct(d.get('mae_med'), True)} | "
                   f"{pct(d.get('big_loss'))} | {pct(d.get('win_med'), True)} | {pct(d.get('lose_med'), True)} |")
    Lns += ["", "### Survival of the break - share of events whose close is still above the base top on day k", "",
            "| tier | d1 | d3 | d5 | d10 | d20 | 95 % band on 'back inside <=5 d' | 95 % band on 'up at 20 d' |", "|---|---|---|---|---|---|---|---|"]
    for t in TIERS:
        d = out["primary"][t]
        a = d["alive"]
        Lns.append(f"| {t} | {pct(a['1'])} | {pct(a['3'])} | {pct(a['5'])} | {pct(a['10'])} | {pct(a['20'])} | "
                   f"{pct(d['fail5_ci'][0])} - {pct(d['fail5_ci'][1])} | {pct(d['r20_pos_ci'][0])} - {pct(d['r20_pos_ci'][1])} |")
    Lns += ["", "## 2. Does the count depend on how a base is defined? (LIQ, volume >= 2x)", "", *HDR]
    for b in BASES:
        Lns.append(row(b, out["bases"][b]))
    Lns += ["", "## 3. How much volume? (base60, every break of the base sliced by volume ratio)", ""]
    for t in ("LIQ", "small", "THIN"):
        Lns += [f"**{t}**", "", *HDR]
        for lab, _, _ in VOL_BUCKETS:
            Lns.append(row(lab, out["vol"][t][lab]))
        Lns.append("")
    Lns += ["## 4. How big was the breakout day itself? (LIQ, volume >= 2x)", "", *HDR]
    for lab, _, _ in DAY_BUCKETS:
        Lns.append(row(lab, out["day"][lab]))
    Lns += ["", "## 5. Index regime and year (LIQ, volume >= 2x)", "", *HDR]
    for k, d in out["regime"].items():
        Lns.append(row(k, d))
    for k, d in out["year"].items():
        Lns.append(row(k, d))
    Lns += ["", "## 6. Controls (LIQ, same days)", "",
            "The two sampled controls have no base top to fall back through, so the level columns read n/a; compare them on the return and run columns.", "", *HDR]
    for k, d in out["controls"].items():
        Lns.append(row(k, d))
    Lns += ["", "## 7. The last 15 volume breakouts in LIQ", "", "| date | code | vol x | day return | 20-day return | back below top on day | MFE 20 d |", "|---|---|---|---|---|---|---|"]
    for e in out["examples"]:
        Lns.append(f"| {e['date']} | {e['code']} | {e['vr']:.1f} | {pct(e['day_ret'], True)} | {pct(e['r20'], True) if e['r20'] is not None else '-'} | "
                   f"{e['fail'] if e['fail'] < 999 else 'not yet'} | {pct(e['mfe'], True) if e['mfe'] is not None else '-'} |")
    # 8. live screen on the last bar: who is consolidating, and who broke out in the last 15 sessions
    sec = dict(zip(sectors["code"], sectors["sector"]))
    HI60n, base60n = HI60.to_numpy(float), base60.to_numpy(bool)
    v60n = P["v60"].to_numpy(float)
    W60 = (adj.rolling(60, min_periods=60).max() / adj.rolling(60, min_periods=60).min() - 1).shift(1).to_numpy(float)
    tlast = len(dates) - 1
    screen = {"as_of": str(dates[tlast].date()), "consolidating": [], "recent_breakouts": []}
    for tier in ("LIQ", "THIN"):
        tn = tiers[tier].to_numpy(bool)
        for j in np.flatnonzero(base60n[tlast] & tn[tlast] & np.isfinite(A[tlast])):
            if tier == "THIN" and tiers["LIQ"].to_numpy(bool)[tlast, j]:
                continue
            days_in = 0
            while tlast - days_in >= 0 and base60n[tlast - days_in, j]:
                days_in += 1
            screen["consolidating"].append({"code": cols[j], "tier": tier, "sector": sec.get(cols[j], ""), "close": float(P["close"].to_numpy(float)[tlast, j]),
                                            "top": float(HI60n[tlast, j] / (A[tlast, j] / P["close"].to_numpy(float)[tlast, j])), "to_top": float(HI60n[tlast, j] / A[tlast, j] - 1),
                                            "width": float(W60[tlast, j]), "days_in_base": int(days_in), "v60_bn": float(v60n[tlast, j] / 1e9),
                                            "vr": float(VR[tlast, j]) if np.isfinite(VR[tlast, j]) else None})
    screen["consolidating"] = [r for r in screen["consolidating"] if r["to_top"] >= 0]   # still under the top; above it = breaking out today
    screen["consolidating"].sort(key=lambda r: r["to_top"])
    for tier in ("LIQ", "THIN"):
        mm = ev_cache[("base60", "LIQ" if tier == "LIQ" else "THIN")]
        for i in np.flatnonzero((mm["ti"] >= tlast - 15) & (mm["vr"] >= 2)):
            t, j = mm["ti"][i], mm["tj"][i]
            if tier == "THIN" and tiers["LIQ"].to_numpy(bool)[t, j]:
                continue
            still = bool(np.isfinite(A[tlast, j]) and A[tlast, j] >= mm["lvl"][i])
            screen["recent_breakouts"].append({"date": str(dates[t].date()), "code": cols[j], "tier": tier, "sector": sec.get(cols[j], ""), "vr": float(mm["vr"][i]),
                                               "day_ret": float(mm["r1"][i]), "since": float(A[tlast, j] / A[t, j] - 1) if np.isfinite(A[tlast, j]) else None,
                                               "back_inside_day": int(mm["fail"][i]) if mm["fail"][i] < 999 else None, "still_above": still})
    screen["recent_breakouts"].sort(key=lambda r: r["date"], reverse=True)
    out["screen"] = screen
    Lns += ["", f"## 8. Live screen on {screen['as_of']}", "",
            f"**Broke out of a 60-day base on >= 2x volume in the last 15 sessions ({len(screen['recent_breakouts'])} names)**", "",
            "| date | code | tier | sector | vol x | day return | since the break | back inside on day | still above the top |", "|---|---|---|---|---|---|---|---|---|"]
    for r in screen["recent_breakouts"]:
        Lns.append(f"| {r['date']} | {r['code']} | {r['tier']} | {r['sector']} | {r['vr']:.1f} | {pct(r['day_ret'], True)} | {pct(r['since'], True) if r['since'] is not None else '-'} | "
                   f"{r['back_inside_day'] or '-'} | {'yes' if r['still_above'] else 'no'} |")
    liq_cons = [r for r in screen["consolidating"] if r["tier"] == "LIQ"]
    Lns += ["", f"**Inside a 60-day base right now: {len(liq_cons)} LIQ names ({len(screen['consolidating']) - len(liq_cons)} more THIN) - the 25 closest to their base top**", "",
            "| code | tier | sector | close | base top | to the top | channel width | days in base | Rp bn/day | volume today x |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in screen["consolidating"][:25]:
        vrs = f"{r['vr']:.1f}" if r["vr"] is not None and np.isfinite(r["vr"]) else "-"
        Lns.append(f"| {r['code']} | {r['tier']} | {r['sector']} | {r['close']:,.0f} | {r['top']:,.0f} | {pct(r['to_top'], True)} | {pct(r['width'])} | {r['days_in_base']} | "
                   f"{r['v60_bn']:.1f} | {vrs} |")
    path = os.path.join(HERE, f"IDX_BREAKOUT_STATS_{date.today().isoformat()}.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(Lns) + "\n")
    print("\n".join(Lns))
    print("wrote", path)
    if not args.no_store:
        by_code: dict[str, dict] = {}                      # a name can be on both lists (broke out, then fell back into a base)
        for i, r in enumerate(out["screen"]["recent_breakouts"]):
            by_code[r["code"]] = {"code": r["code"], "screens": ["breakout_vol"], "score": r["vr"], "rank": i + 1,
                                  "features": {"day_ret": r["day_ret"], "since": r["since"], "still_above": r["still_above"], "tier": r["tier"]},
                                  "context": {"date": r["date"], "sector": r["sector"]}}
        for i, r in enumerate(out["screen"]["consolidating"]):
            e = by_code.get(r["code"])
            if e is not None:
                e["screens"].append("consolidating")
                e["features"].update({"to_top": r["to_top"], "width": r["width"], "days_in_base": r["days_in_base"], "v60_bn": r["v60_bn"]})
                continue
            by_code[r["code"]] = {"code": r["code"], "screens": ["consolidating"], "score": -r["to_top"], "rank": i + 1,
                                  "features": {"to_top": r["to_top"], "width": r["width"], "days_in_base": r["days_in_base"], "v60_bn": r["v60_bn"], "tier": r["tier"]},
                                  "context": {"as_of": out["screen"]["as_of"], "sector": r["sector"]}}
        store_names = list(by_code.values())
        from blackheart_ingest.idx import research_store as rs
        with psycopg.connect(dsn) as conn:
            sid = rs.record_study(conn, "breakout_stats", dates[-1].date(),
                                  params={"trials": [], "n_trials_cumulative": N_TRIALS, "bases": BASES, "gap": GAP, "seed": SEED, "descriptive": True},
                                  summary=json.loads(json.dumps(out, default=str)), names=store_names, report_path=path,
                                  note=f"LIQ vol-breakouts n={P0['n']}, back inside base <=5 d {P0['fail5'] * 100:.0f} %, up at 20 d {P0['r20_pos'] * 100:.0f} %, median 20 d {P0['r20_med'] * 100:+.1f} %")
            print(f"study #{sid} stored")


if __name__ == "__main__":
    main()
