#!/usr/bin/env python3
"""IDX menu 41 (Track C) - CONSTRUCTION changes to the deployed combo book, 2026-09-25.

Deployed book (the reference, re-run inside this script = the ONLY baseline quoted): one Rp 20 M cash pool, 20 slots, lots of
100, gap-fade 10 % / trend small+gate 5 % / ML cost-aware 5 % of NAV per trade, cash floor 30 % (the #177 `cash30`: no new
trade that would take the overnight invested share above 70 %), ML sleeve = confirmation ensemble ens4 (+5/10, +8/10,
+10/10, +8/5; each rule-book gets 1/4 of the 5 %, a name confirmed by several rules holds several quarter-pieces, slots
count distinct names). Engine, trades and costs are those of `idx_combo_rupiah` (#168) / `idx_alloc_frontier` (#177):
gap events from `CR.gap_events`, trend trades from `CR.trend_trades`, ML from `idx_ml_confirm.book` per rule; closing
offer/bid, Stockbit fees; window 2022-01 -> 2026-09-16.

CANDIDATES SKIPPED (no trial spent):
  2. gap-fade partial take-profit: menu 29c (IDX_GAPFADE_EXIT_2026-09-23, 9 trials) already tested +2/+3/+5 % targets on
     daily highs: every target LOSES to the close (-139 .. -273 bps/trade). A partial TP (fraction f at the target, rest at
     the close) is per trade exactly f x TP + (1-f) x close, so it is dominated for every f > 0. The intraday tape
     (idx.feed_bar_1m) holds 5 sessions (2026-09-21 .. 09-25) = UNTESTABLE for anything finer than 29c.
  (cash floor 30 %, vol target, gate/brake overlays, sizing grid: #177. ML stops/trails: #161. ML rule ensemble: #175.)

PRE-REGISTERED ARMS (12 trials; cumulative N_BEFORE 903 -> 915, ids 903..914):
  #1 trend timing / confirmation (candidate trend signals = the deployed trend simulator's own trades: signal day s = the
     day before its fill; every replay re-applies the trail-10 exit from the replay's own fill, exit filled at the next close)
     t1 trend_d0      replay, fill at close s+1 (on time - what the live runner does: plan after the close, buy next day)
     t2 trend_d1      replay, fill at close s+2 (one day late)
     t3 trend_ens     confirmation ensemble ens4t: rules +3/5, +3/10, +5/5, +5/10 (close >= (1+x) x close_s within w days
                      after s; fill at the next close), 1/4 of the 5 % per rule; + leave-one-rule-out books (neighbours)
     t4 trend_ens_d1  the same, every fill one more day late
     t5 trend_stagger entry split in thirds at closes s+1, s+2, s+3 (a time ensemble, no price condition)
     FRAGILITY read: the CAGR/Sharpe loss d0 -> d1 of the full book and of the trend-only book, ens vs plain.
  #3 sleeve-level risk budget (not in #177; #177 only tested book-level overlays)
     t6 cap6          at most 6 overnight names per sleeve (trend, ML)
     t7 cap4          at most 4 (neighbour of cap6)
     t8 sector3       at most 3 overnight names per sector across the book (sector from the ML panel)
     t9 sector2       at most 2 (neighbour)
     t10 gap_exempt   the intraday gap-fade sleeve ignores the floor (it never holds overnight; floor on overnight only)
  #4 recycling / opportunity cost (when a new trade is blocked by the floor, the slots or cash)
     t11 recycle5     sell the weakest overnight position (lowest return since entry, must be < 0, held >= 5 days) and
                      take the new trade; gap-fade blocks sell at the open (open - 1 tick), close entries at the closing bid
     t12 recycle10    the same with held >= 10 days (neighbour)
READING RULE (fixed before the run). An arm IMPROVES the deployed book if
     (mDD shallower by >= 3 pp AND CAGR >= 0.9 x deployed) OR (CAGR up >= 3 pp AND mDD not deeper by > 1 pp)
  holds on the full window AND in both halves (split at the window's middle date, each half's NAV re-based, compared with
  the deployed book's same half), AND its pre-registered neighbour passes the full-window test (cap6<->cap4,
  sector3<->sector2, recycle5<->recycle10, trend_ens <-> all four leave-one-rule-out books). Arms without a neighbour
  (gap_exempt, trend_stagger) can at most be CANDIDATE. t1/t2 are measurements (the fragility yardstick), not proposals.
  #1 answers its question separately: the ensemble is LESS FRAGILE if its d0->d1 CAGR loss is <= half the plain replay's,
  on the full book and on the trend-only book.
Any change to the live book's params is the operator's call. READ-ONLY on the DB except one idx.study row.
Env: INGEST_DB_DSN (or blackheart-ingest/idx-local.env), IDX_ML_CACHE, IDX_EXIT_CACHE.
"""
from __future__ import annotations

import json
import os
import pickle
import re
import sys
from datetime import date

import numpy as np
import pandas as pd
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blackheart-ingest", "src"))
os.environ.setdefault("IDX_ML_CACHE", os.path.join(ROOT, "tmp", "ml_strategy_cache.pkl"))
os.environ.setdefault("IDX_EXIT_CACHE", os.path.join(ROOT, "tmp", "exit_cache.pkl"))
import idx_beyond as BY  # noqa: E402
import idx_combo_rupiah as CR  # noqa: E402
import idx_exit as E  # noqa: E402
import idx_gapfade as G  # noqa: E402
import idx_ml_confirm as F  # noqa: E402
import idx_ml_costaware as C  # noqa: E402
import idx_ml_strategy as M  # noqa: E402
import idx_swing2 as S  # noqa: E402
from blackheart_ingest.idx import research_store as rs  # noqa: E402
from blackheart_ingest.idx.ml import common  # noqa: E402

N_BEFORE = 903
STUDY = "construction"
PCT = {"gap": 0.10, "trend": 0.05, "ML": 0.05}
FLOOR = 0.30
ENS4_ML = [(0.05, 10), (0.08, 10), (0.10, 10), (0.08, 5)]
ENS4_TREND = [(0.03, 5), (0.03, 10), (0.05, 5), (0.05, 10)]
TRIALS = ["trend_d0", "trend_d1", "trend_ens", "trend_ens_d1", "trend_stagger", "cap6", "cap4", "sector3", "sector2", "gap_exempt",
          "recycle5", "recycle10"]
NEIGH = {"cap6": ["cap4"], "cap4": ["cap6"], "sector3": ["sector2"], "sector2": ["sector3"], "recycle5": ["recycle10"], "recycle10": ["recycle5"]}
NO_NEIGH = {"gap_exempt", "trend_stagger"}
MEASURE = {"trend_d0", "trend_d1", "trend_ens_d1"}


def dsn() -> str:
    if os.environ.get("INGEST_DB_DSN"):
        return os.environ["INGEST_DB_DSN"]
    env = dict(re.findall(r"^([A-Z_]+)=(.*)$", open(os.path.join(ROOT, "blackheart-ingest", "idx-local.env")).read(), re.M))
    v = env["INGEST_DB_DSN"].strip().strip('"')
    os.environ["INGEST_DB_DSN"] = v
    return v


# ---- trade sources -------------------------------------------------------------------------------------------------------
def ml_ens_trades(P, dates, codes, A, raw, offer, bid, liq):
    c_in, c_out = M.costs(raw, offer, bid)
    S_ = M.wide(P, "s5").reindex(index=dates, columns=codes).to_numpy(float)
    e5 = C.ema(S_ - np.nanmedian(np.where(liq, S_, np.nan), axis=1, keepdims=True), 3)
    t0 = int(np.searchsorted(dates, np.datetime64(CR.START)))
    out = []
    for rule in ENS4_ML:
        _, log = F.book(A, liq, e5, 10, c_in, c_out, 2.0, t_start=t0, wait=rule)
        tag = f"+{rule[0] * 100:.0f}/{rule[1]}"
        out += [{"strat": "ML", "tag": tag, "frac": 1 / len(ENS4_ML), "code": codes[r.j], "t_in": int(r.t_in), "t_out": int(r.t_out)} for r in log.itertuples()]
    return out


def trend_signals(d: str):
    """The deployed trend simulator's trades (same code as CR.trend_trades) -> (signal day s, column j) on its own index."""
    P, unis, comp, Hp, Lp = E.load_all(d, os.environ.get("IDX_EXIT_CACHE"))
    c_in, c_out = S.costs(P)
    adj, vol = P["adj"], P["volume"]
    d_tr = adj.index
    A, H, L = adj.to_numpy(float), Hp.to_numpy(float), Lp.to_numpy(float)
    ma200 = adj.rolling(200, min_periods=200).mean()
    vr = vol / vol.rolling(20, min_periods=20).median()
    hi = adj.rolling(60, min_periods=60).max()
    entry = ((adj >= hi) & (adj > ma200) & (vr >= 1.5)).to_numpy(bool) & np.asarray(d_tr >= CR.START)[:, None] & ~BY.regime_off_mask(comp, d_tr)[:, None]
    prev = adj.shift(1)
    tr = pd.concat([Hp - Lp, (Hp - prev).abs(), (Lp - prev).abs()], axis=1, keys=["a", "b", "c"]).T.groupby(level=1).max().T.reindex(columns=adj.columns)
    ATR = tr.ewm(alpha=1 / 20, adjust=False, min_periods=20).mean().to_numpy(float)
    ma20, ma50 = (adj.rolling(n, min_periods=n).mean().to_numpy(float) for n in (20, 50))
    dd = adj.diff()
    up = dd.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    dn = (-dd.clip(upper=0)).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    RSI = (100 - 100 / (1 + up / dn.replace(0, np.nan))).to_numpy(float)
    LO10 = Lp.shift(1).rolling(10, min_periods=10).min().to_numpy(float)
    LO20 = Lp.shift(1).rolling(20, min_periods=20).min().to_numpy(float)
    rule = E.make_rules(A, H, L, ATR, ma20, ma50, RSI, LO10, LO20)["trail10"]
    small = (unis["LIQ"] & ~unis["BLUE"]).to_numpy(bool)
    _, trs, open_ = E.run_book(A, H, L, c_in, c_out, entry, vr.to_numpy(float), rule, small)
    sig = [(int(tp[0]) - 1, int(tp[1])) for tp in trs]
    sig += [(int(p["e"]) - 1, int(j)) for j, p in (open_.items() if isinstance(open_, dict) else [])]
    on_mask = float(np.mean([entry[s, j] for s, j in sig])) if sig else float("nan")
    on_mask_next = float(np.mean([entry[s + 1, j] for s, j in sig if s + 1 < len(d_tr)])) if sig else float("nan")
    return {"A": A, "d_tr": d_tr, "cols": list(adj.columns), "sig": sig, "diag": {"signal_on_day_before_fill": on_mask, "signal_on_fill_day": on_mask_next,
                                                                                  "n_closed": len(trs), "n_open": len(sig) - len(trs)}}


def trail_exit(A, j, f):
    """trail-10 from the fill at close f: exit signalled at close t when A <= 0.9 x peak, filled at close t+1."""
    T = A.shape[0]
    peak = A[f, j]
    for t in range(f, T):
        a = A[t, j]
        if np.isnan(a):
            return t
        peak = max(peak, a)
        if a <= 0.9 * peak:
            return t + 1 if t + 1 < T else None
    return None


def trend_replay(TS, dates, mode: str, delay: int = 0, rules=None):
    A, d_tr, cols = TS["A"], TS["d_tr"], TS["cols"]
    pos = {d: i for i, d in enumerate(dates)}
    T = A.shape[0]
    out = []

    def add(s, j, f, tag, frac):
        if f >= T or np.isnan(A[f, j]) or d_tr[f] not in pos:
            return
        x = trail_exit(A, j, f)
        t_out = pos.get(d_tr[x], 10 ** 9) if x is not None and x < T else 10 ** 9
        if t_out <= pos[d_tr[f]]:
            return
        out.append({"strat": "trend", "tag": tag, "frac": frac, "code": cols[j], "t_in": pos[d_tr[f]], "t_out": t_out})

    for s, j in TS["sig"]:
        if mode == "plain":
            add(s, j, s + 1 + delay, "p", 1.0)
        elif mode == "stagger":
            for k in range(3):
                add(s, j, s + 1 + k, f"st{k}", 1 / 3)
        elif mode == "ens":
            ref = A[s, j]
            for thr, win in rules:
                for t in range(s + 1, min(s + win, T - 1) + 1):
                    if A[t, j] >= (1 + thr) * ref:
                        add(s, j, t + 1 + delay, f"+{thr * 100:.0f}/{win}", 1 / len(rules))
                        break
    return out


def gap_events(d: str, dates):
    """CR.gap_events plus the open panel (needed to sell a recycled position at the open)."""
    B = G.build(d)
    g7, elig, v60 = B["masks"]["g7"], B["elig"], B["v60"]
    R = B["R"]["close"]
    o = B["P"]["open"]
    pos = {dd: i for i, dd in enumerate(dates)}
    out = []
    for dd in R.index:
        ts = pd.Timestamp(dd)
        if ts < CR.START or ts not in pos:
            continue
        q = elig.loc[dd] & g7.loc[dd].fillna(False)
        if not q.any():
            continue
        pick = v60.loc[dd].where(q).dropna().sort_values(ascending=False).index[:CR.GAP_K]
        for code in pick:
            r, op = R.loc[dd, code], o.loc[dd, code]
            if np.isfinite(r) and np.isfinite(op) and op > 0:
                out.append({"strat": "gap", "code": code, "t": pos[ts], "net": float(r), "open": float(op)})
    o.index = pd.DatetimeIndex(o.index)
    return out, o


# ---- engine ------------------------------------------------------------------------------------------------------------------
def engine(dates, codes, A, raw, offer, bid, OPEN, SECT, entries_src, gap, *, use=("gap", "trend", "ML"), floor=FLOOR, sleeve_cap=None,
           sector_cap=None, gap_exempt=False, recycle=None):
    idx = {c: i for i, c in enumerate(codes)}
    T = len(dates)
    t0 = int(np.searchsorted(dates, np.datetime64(CR.START)))
    tick = common.tick
    entries: dict[int, list] = {}
    exits: dict[int, list] = {}
    for n, x in enumerate(e for e in entries_src if e["strat"] in use):
        x = dict(x, id=n)
        entries.setdefault(x["t_in"], []).append(x)
        exits.setdefault(x["t_out"], []).append(x)
    gaps: dict[int, list] = {}
    for x in (gap if "gap" in use else []):
        gaps.setdefault(x["t"], []).append(x)
    cash = CR.CAPITAL
    held: dict[tuple, dict] = {}                       # (strat, tag, code) -> position (overnight only)
    nav = np.full(T, np.nan)
    n_rec = n_block = 0

    def mval(t):
        return sum(p["units"] * (A[t, idx[k[2]]] / p["a_in"]) for k, p in held.items() if not np.isnan(A[t, idx[k[2]]]))

    def names():
        return {(k[0], k[2]) for k in held}

    def sell_close(t, k):
        p = held.pop(k)
        j = idx[k[2]]
        px = bid[t, j] if 0 < bid[t, j] <= raw[t, j] else raw[t, j] - tick(raw[t, j])
        value = p["units"] * (A[t, j] / p["a_in"]) * (px / raw[t, j]) if not np.isnan(A[t, j]) else p["units"]
        return value * (1 - CR.FEE_SELL)

    def weakest(t, at_open):
        best, bk = None, None
        for k, p in held.items():
            j = idx[k[2]]
            if t - p["t"] < recycle or np.isnan(A[t - 1 if at_open else t, j]):
                continue
            if at_open:
                o = OPEN[t, j]
                if not (o > 0) or not (raw[t - 1, j] > 0):
                    continue
                r = (A[t - 1, j] / p["a_in"]) * (o / raw[t - 1, j]) - 1
            else:
                r = A[t, j] / p["a_in"] - 1
            if r < 0 and (best is None or r < best):
                best, bk = r, k
        return bk

    def sell_open(t, k):
        p = held.pop(k)
        j = idx[k[2]]
        o = OPEN[t, j]
        value = p["units"] * (A[t - 1, j] / p["a_in"]) * ((o - tick(o)) / raw[t - 1, j])
        return value * (1 - CR.FEE_SELL)

    for t in range(t0, T):
        nav_prev = nav[t - 1] if t > t0 else CR.CAPITAL
        # morning: gap-fade (bought at the open, sold at the close)
        day_gap, n_gap = 0.0, 0
        mv_open = None
        for x in gaps.get(t, []):
            tries = 2 if recycle is not None else 1
            for attempt in range(tries):
                px = (x["open"] + tick(x["open"])) * (1 + CR.FEE_BUY)
                lots = int((PCT["gap"] * nav_prev) // (px * CR.LOT))
                cost = lots * CR.LOT * px
                if lots < 1:
                    break
                if mv_open is None:
                    mv_open = mval(t)                       # as #177: the overnight book marked at today's close
                blocked = len(names()) + n_gap >= CR.MAX_POS or cost > cash or (floor > 0 and not gap_exempt and (mv_open + cost) / nav_prev > 1 - floor)
                if not blocked:
                    cash -= cost
                    n_gap += 1
                    day_gap += cost * (1 + x["net"])
                    break
                n_block += attempt == 0
                if attempt == 0 and recycle is not None:
                    k = weakest(t, True)
                    if k is None:
                        break
                    j = idx[k[2]]
                    mv_open -= held[k]["units"] * (np.nan_to_num(A[t, j], nan=A[t - 1, j]) / held[k]["a_in"])
                    cash += sell_open(t, k)
                    n_rec += 1
        cash += day_gap
        # close: exits, then entries (trend before ML)
        for x in exits.get(t, []):
            k = (x["strat"], x["tag"], x["code"])
            if k in held and held[k]["id"] == x["id"]:
                cash += sell_close(t, k)
        mv = mval(t)
        nav_now = cash + mv
        for x in sorted(entries.get(t, []), key=lambda z: 0 if z["strat"] == "trend" else 1):
            k = (x["strat"], x["tag"], x["code"])
            j = idx[x["code"]]
            if k in held or np.isnan(A[t, j]) or raw[t, j] <= 0:
                continue
            nm = names()
            new_name = (x["strat"], x["code"]) not in nm
            if sleeve_cap and new_name and x["strat"] in sleeve_cap and len({c for s_, c in nm if s_ == x["strat"]}) >= sleeve_cap[x["strat"]]:
                continue
            if sector_cap and new_name:
                sec = SECT[t, j]
                if sec is not None and sum(1 for c in {c for _, c in nm} if SECT[t, idx[c]] == sec and c != x["code"]) >= sector_cap:
                    continue
            px = offer[t, j] if offer[t, j] > 0 and offer[t, j] >= raw[t, j] else raw[t, j] + tick(raw[t, j])
            for attempt in range(2 if recycle is not None else 1):
                lots = int((PCT[x["strat"]] * x["frac"] * nav_now) // (px * CR.LOT))
                cost = lots * CR.LOT * px * (1 + CR.FEE_BUY)
                if lots < 1:
                    break
                blocked = (new_name and len(names()) >= CR.MAX_POS) or cost > cash or (floor > 0 and (mv + cost) / nav_now > 1 - floor)
                if not blocked:
                    cash -= cost
                    mv += cost / (1 + CR.FEE_BUY)
                    held[k] = {"t": t, "a_in": A[t, j], "units": lots * CR.LOT * raw[t, j], "cost": cost, "id": x["id"]}
                    break
                n_block += attempt == 0
                if attempt == 0 and recycle is not None:
                    wk = weakest(t, False)
                    if wk is None:
                        break
                    jj = idx[wk[2]]
                    mv -= held[wk]["units"] * (A[t, jj] / held[wk]["a_in"])
                    proceeds = sell_close(t, wk)
                    cash += proceeds
                    nav_now = cash + mv
                    n_rec += 1
        nav[t] = cash + mval(t)
    return pd.Series(nav[t0:], index=dates[t0:]), {"recycled": n_rec, "blocked": n_block}


# ---- reading -------------------------------------------------------------------------------------------------------------------
def halves(nav: pd.Series):
    mid = nav.index[0] + (nav.index[-1] - nav.index[0]) / 2
    return [CR.stats(nav[nav.index <= mid]), CR.stats(nav[nav.index > mid])]


def passes(a: dict, d: dict) -> bool:
    dd = (a["mdd"] - d["mdd"]) * 100
    dc = (a["cagr"] - d["cagr"]) * 100
    return bool((dd >= 3 and a["cagr"] >= 0.9 * d["cagr"]) or (dc >= 3 and dd >= -1))


def main() -> int:
    d = dsn()
    P = pickle.load(open(os.environ["IDX_ML_CACHE"], "rb"))
    P = P[(P["d"] >= "2021-06-01") & (P["d"] <= CR.END)].copy()
    dates = M.wide(P, "close").index
    codes = M.wide(P, "close").columns
    g = lambda c: M.wide(P, c).reindex(index=dates, columns=codes)  # noqa: E731
    A, raw = g("ac").to_numpy(float), g("close").to_numpy(float)
    offer, bid = np.nan_to_num(g("offer").to_numpy(float)), np.nan_to_num(g("bid").to_numpy(float))
    liq = g("liq").fillna(False).astype(bool).to_numpy()
    SECT = g("sector").ffill().to_numpy(object)
    SECT = np.where(pd.isna(SECT), None, SECT)
    ml = ml_ens_trades(P, dates, codes, A, raw, offer, bid, liq)
    tr_dep = [dict(x, tag="p", frac=1.0) for x in CR.trend_trades(d, dates)]
    gap, o = gap_events(d, dates)
    OPEN = o.reindex(index=dates, columns=codes).to_numpy(float)
    TS = trend_signals(d)
    M.log(f"events: ML ens4 {len(ml)} rule-trades, trend (deployed replay) {len(tr_dep)}, trend signals {len(TS['sig'])}, gap {len(gap)}; diag {TS['diag']}")
    trend_src = {"trend_d0": trend_replay(TS, dates, "plain", 0), "trend_d1": trend_replay(TS, dates, "plain", 1),
                 "trend_ens": trend_replay(TS, dates, "ens", 0, ENS4_TREND), "trend_ens_d1": trend_replay(TS, dates, "ens", 1, ENS4_TREND),
                 "trend_stagger": trend_replay(TS, dates, "stagger")}
    for i, r in enumerate(ENS4_TREND):
        trend_src[f"trend_ens_loo{i}"] = trend_replay(TS, dates, "ens", 0, [x for x in ENS4_TREND if x != r])
    common_args = (dates, codes, A, raw, offer, bid, OPEN, SECT)

    def run(name, trend=None, **kw):
        src = ml + (tr_dep if trend is None else trend)
        nav, info = engine(*common_args, src, gap, **kw)
        st = CR.stats(nav)
        h = halves(nav)
        res[name] = {**{k: v for k, v in st.items()}, "h1": h[0], "h2": h[1], **info}
        M.log(f"{name:<16} CAGR {st['cagr'] * 100:6.1f} % Sharpe {st['sharpe']:5.2f} mDD {st['mdd'] * 100:6.1f} % | H1 {h[0]['cagr'] * 100:5.1f}/{h[0]['mdd'] * 100:5.1f} "
              f"H2 {h[1]['cagr'] * 100:5.1f}/{h[1]['mdd'] * 100:5.1f} | rec {info['recycled']} blocked {info['blocked']} | "
              + " ".join(f"{str(y)[2:]}:{v * 100:+.0f}" for y, v in st["by_year"].items()))
        return nav

    res: dict[str, dict] = {}
    run("deployed")
    for k in ["trend_d0", "trend_d1", "trend_ens", "trend_ens_d1", "trend_stagger"] + [f"trend_ens_loo{i}" for i in range(4)]:
        run(k, trend=trend_src[k])
    # trend-only books (the sleeve alone on the same engine and floor) for the fragility read
    for k in ["deployed", "trend_d0", "trend_d1", "trend_ens", "trend_ens_d1", "trend_stagger"]:
        run(f"{k}|trend_only", trend=None if k == "deployed" else trend_src[k], use=("trend",))
    run("cap6", sleeve_cap={"trend": 6, "ML": 6})
    run("cap4", sleeve_cap={"trend": 4, "ML": 4})
    run("sector3", sector_cap=3)
    run("sector2", sector_cap=2)
    run("gap_exempt", gap_exempt=True)
    run("recycle5", recycle=5)
    run("recycle10", recycle=10)

    dep = res["deployed"]
    for name in TRIALS + [f"trend_ens_loo{i}" for i in range(4)]:
        r = res[name]
        r["pass_full"] = passes(r, dep)
        r["pass_h1"] = passes(r["h1"], dep["h1"])
        r["pass_h2"] = passes(r["h2"], dep["h2"])
    for name in TRIALS:
        r = res[name]
        core = r["pass_full"] and r["pass_h1"] and r["pass_h2"]
        nb = [f"trend_ens_loo{i}" for i in range(4)] if name == "trend_ens" else NEIGH.get(name, [])
        nb_ok = bool(nb) and all(res[n]["pass_full"] for n in nb)
        if name in MEASURE:
            r["verdict"] = "measurement" + (" (would pass)" if core else "")
        elif core and nb_ok:
            r["verdict"] = "IMPROVES"
        elif core and name in NO_NEIGH:
            r["verdict"] = "CANDIDATE (no neighbour)"
        elif core:
            r["verdict"] = "no: neighbour fails"
        else:
            r["verdict"] = "no"

    def loss(a, b, key="cagr"):
        return (res[a][key] - res[b][key]) * 100

    frag = {"book_plain_cagr_loss_pp": loss("trend_d0", "trend_d1"), "book_ens_cagr_loss_pp": loss("trend_ens", "trend_ens_d1"),
            "trendonly_plain_cagr_loss_pp": loss("trend_d0|trend_only", "trend_d1|trend_only"),
            "trendonly_ens_cagr_loss_pp": loss("trend_ens|trend_only", "trend_ens_d1|trend_only"),
            "trendonly_plain_sharpe": [res["trend_d0|trend_only"]["sharpe"], res["trend_d1|trend_only"]["sharpe"]],
            "trendonly_ens_sharpe": [res["trend_ens|trend_only"]["sharpe"], res["trend_ens_d1|trend_only"]["sharpe"]]}
    plain_l, ens_l = frag["trendonly_plain_cagr_loss_pp"], frag["trendonly_ens_cagr_loss_pp"]
    frag["less_fragile"] = bool(plain_l > 0 and ens_l <= plain_l / 2 and frag["book_ens_cagr_loss_pp"] <= max(frag["book_plain_cagr_loss_pp"], 0) / 2)
    M.log(f"fragility {frag}")

    n_trials = N_BEFORE + len(TRIALS)
    f = lambda v: f"{v * 100:.1f} %"  # noqa: E731
    yrs = sorted(dep["by_year"])
    L = [f"# IDX menu 41 - construction changes to the deployed combo book - {date.today()} - 12 trials (903..914), cumulative N = {n_trials}", "",
         f"Deployed = gap 10 % / trend 5 % / ML ens4 5 % of NAV per trade, 20 slots, cash floor 30 %, Rp 20 M, {CR.START.date()} -> {CR.END.date()}, "
         "engine/trades/costs of #168/#177; re-run in this script (same-run pairs only). Halves split at the window's middle date. "
         "Rule (pre-registered in `research/idx_construction.py`): IMPROVES if (mDD >= 3 pp shallower and CAGR >= 0.9x) or (CAGR >= +3 pp and mDD <= 1 pp deeper), "
         "full window AND both halves, neighbour passing on the full window.", "",
         "Skipped: #2 gap-fade partial take-profit - menu 29c already has every target losing to the close (-139..-273 bps/trade); a partial TP is a "
         "linear mix of a losing target and the close, so it is dominated; idx.feed_bar_1m has 5 sessions (2026-09-21..25) = UNTESTABLE finer than 29c. "
         "Book-level overlays and sizing were #177; ML stops #161; ML rule ensemble #175.", "",
         "| arm | CAGR | Sharpe | mDD | H1 CAGR/mDD | H2 CAGR/mDD | full | H1 | H2 | " + " | ".join(str(y) for y in yrs) + " | verdict |",
         "|---|---|---|---|---|---|---|---|---|" + "---|" * len(yrs) + "---|"]
    for name in ["deployed"] + TRIALS + [f"trend_ens_loo{i}" for i in range(4)]:
        r = res[name]
        yes = lambda b: "pass" if b else "-"  # noqa: E731
        L.append(f"| {name} | {f(r['cagr'])} | {r['sharpe']:.2f} | {f(r['mdd'])} | {f(r['h1']['cagr'])} / {f(r['h1']['mdd'])} | {f(r['h2']['cagr'])} / {f(r['h2']['mdd'])} | "
                 + (" | ".join(yes(r[k]) for k in ("pass_full", "pass_h1", "pass_h2")) if name != "deployed" else "ref | ref | ref") + " | "
                 + " | ".join(f"{r['by_year'].get(y, float('nan')) * 100:+.0f} %" for y in yrs) + f" | {r.get('verdict', 'reference')} |")
    L += ["", "## #1 trend timing: is a confirmation ensemble less fragile to a late fill?", "",
          "| trend sleeve alone (same engine, floor) | CAGR | Sharpe | mDD |", "|---|---|---|---|"]
    for k in ["deployed", "trend_d0", "trend_d1", "trend_ens", "trend_ens_d1", "trend_stagger"]:
        r = res[f"{k}|trend_only"]
        L.append(f"| {k} | {f(r['cagr'])} | {r['sharpe']:.2f} | {f(r['mdd'])} |")
    L += ["", f"CAGR lost to a one-day-late fill: plain {plain_l:+.1f} pp (trend alone) / {frag['book_plain_cagr_loss_pp']:+.1f} pp (whole book); "
          f"ensemble {ens_l:+.1f} pp / {frag['book_ens_cagr_loss_pp']:+.1f} pp. Less fragile by the pre-registered test: {'YES' if frag['less_fragile'] else 'no'}.",
          "", f"Trend replay diagnostic: of the deployed trend simulator's trades, the entry signal is on the day BEFORE the simulator's fill in "
          f"{TS['diag']['signal_on_day_before_fill'] * 100:.0f} % of trades; `idx_combo_rupiah.trend_trades` places the combo's trend entry at simulator-fill + 1 day "
          "(its comment reads the tuple's first field as the signal day), i.e. the deployed baseline replays trend one session late; `trend_d0` is the on-time replay."]
    imp = [n for n in TRIALS if res[n].get("verdict") == "IMPROVES"]
    cand = [n for n in TRIALS if str(res[n].get("verdict", "")).startswith("CANDIDATE")]
    L += ["", "## Verdict (menu 41, study stored)", "", f"IMPROVES: {', '.join(imp) or 'none'}. CANDIDATE: {', '.join(cand) or 'none'}. "
          "Any change to the live book's params is the operator's call."]
    text = "\n".join(L)
    out = os.path.join(HERE, f"IDX_CONSTRUCTION_{date.today()}.md")
    open(out, "w", encoding="utf-8").write(text + "\n")
    json.dump({"res": res, "fragility": frag, "diag": TS["diag"]}, open(os.path.join(ROOT, "research-scratch", f"construction_{date.today()}.json"), "w"), indent=1, default=str)
    print(text)
    if os.environ.get("IDX_NO_RECORD"):
        return 0
    with psycopg.connect(d) as conn:
        sid = rs.record_study(conn, STUDY, date.today(), params={"trials": TRIALS, "n_before": N_BEFORE, "n_trials_cumulative": n_trials, "pct": PCT, "floor": FLOOR,
                                                                 "ml_rules": ENS4_ML, "trend_rules": ENS4_TREND, "skipped": {"gapfade_partial_tp": "dominated by menu 29c; 1m tape 5 sessions"}},
                              summary=common.plain({"res": {k: {kk: vv for kk, vv in v.items() if kk not in ("nav_year_end",)} for k, v in res.items()},
                                                    "fragility": frag, "diag": TS["diag"], "improves": imp, "candidates": cand}),
                              names=[], report_path=out, note="menu 41: construction changes to the deployed combo book (trend confirmation, sleeve/sector caps, gap exempt, recycling)")
        conn.commit()
    M.log(f"study #{sid} stored; report {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
