#!/usr/bin/env python3
"""IDX engine fix (2026-09-25): two bugs in the SHARED research engine, fixed, then the deployed combo book re-measured.

BUG 1  idx_combo_rupiah.trend_trades mapped E.run_book's trade tuple with d_tr[e + 1], d_tr[e + 1 + hold] under a comment that
       e is the signal day. run_book stores e = the FILL day (signal at close e-1, bought at close e) and hold = exit fill - e,
       so every trend trade was replayed one session late (entry and exit). Fixed: d_tr[e], d_tr[e + hold].
BUG 2  idx_swing2.panels kept codes by their CURRENT idx.listing.board (look-ahead survivorship, #189). Fixed: the board ON THE
       DAY (daily_summary.remarks) as a per-day mask on LIQ in build(); IDX_BOARD_MODE=current reproduces the old filter;
       idx_exit.load_all refuses a cache of the other mode. Only the trend sleeve reads these panels: gap-fade (idx_daytrade)
       already used the board on the day, and the ML sleeve's panel (idx/ml/daily.build_panel) has no board filter at all -
       exactly like the live runner (combo_book.ml_scores) - so the ML cache needs no rebuild.

RE-MEASURE (measurement corrections, 0 trials): deployed book = gap 10 % / trend 5 % / ML ens4 5 % of NAV per trade, 20 slots,
Rp 20 M, cash floor 30 %, 2022-01 -> 2026-09-16 (the #184 `idx_construction.engine`, = #177 engine + ens4 quarter pieces).
  (a) old engine: current-board cache tmp/exit_cache.pkl + the one-day-late mapping   (= #184 'deployed', must reproduce)
  (b) bug 1 fixed only     (c) bug 2 fixed only (tmp/exit_cache_pit.pkl)     (d) both fixed = the new official baseline
ONE CONFIRMATION TRIAL (cumulative +1): R1 of #188 (market-wide 20-day net foreign flow < 0 -> no new trend entry, INSTEAD of
IHSG < MA200) on the corrected engine vs (d), same run; #188's pre-registered reading rule (trend sleeve alone on the engine:
Sharpe up AND mDD not deeper AND CAGR >= 0.9x in 2/2 halves split at the median ungated entry, AND Sharpe >= 95th pct of 200
circular-shift placebos); neighbours (10 d, 40 d, thr -/+2 %) reported, not counted (already in #188).
READ-ONLY on market tables; one idx.study row ('engine_fix').
"""
from __future__ import annotations

import math
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
ML_CACHE = os.path.join(ROOT, "tmp", "ml_strategy_cache.pkl")          # board-agnostic panel: unaffected by bug 2
OLD_CACHE = os.path.join(ROOT, "tmp", "exit_cache.pkl")                # current-board panels (what every report so far used)
PIT_CACHE = os.path.join(ROOT, "tmp", "exit_cache_pit.pkl")            # point-in-time board panels (this fix)
os.environ["IDX_ML_CACHE"] = ML_CACHE
import idx_beyond as BY  # noqa: E402
import idx_combo_rupiah as CR  # noqa: E402
import idx_construction as K  # noqa: E402
import idx_exit as E  # noqa: E402
import idx_foreign_gate as FG  # noqa: E402
import idx_ml_strategy as M  # noqa: E402
import idx_swing2 as S  # noqa: E402
from blackheart_ingest.idx import research_store as rs  # noqa: E402
from blackheart_ingest.idx.ml import common  # noqa: E402

os.environ.pop("IDX_EXIT_CACHE", None)          # the imports above setdefault it to the OLD cache; every call here passes its cache

STUDY = "engine_fix"
N_BEFORE_CALLER = 895                 # what the caller stated
N_BEFORE_LEDGER = 915                 # highest n_trials_cumulative in idx.study before this run (#184 construction)
N_PLACEBO = int(os.environ.get("EF_PLACEBO", "200"))
SEED = 40
OUT = os.path.join(HERE, "IDX_ENGINE_FIX_2026-09-25.md")
VARIANTS = {"a_old": (OLD_CACHE, "current", True), "b_bug1": (OLD_CACHE, "current", False),
            "c_bug2": (PIT_CACHE, "pit", True), "d_fixed": (PIT_CACHE, "pit", False)}
LABEL = {"a_old": "(a) old engine", "b_bug1": "(b) bug 1 fixed only", "c_bug2": "(c) bug 2 fixed only", "d_fixed": "(d) both fixed = new baseline"}
REF_184 = {"cagr": 0.308, "sharpe": 1.74, "mdd": -0.173}


# ---- the #184 engine with per-sleeve P&L attribution (no caps / recycle; asserted equal to K.engine) --------------------------
def engine_attr(dates, codes, A, raw, offer, bid, src, gap, use=("gap", "trend", "ML"), floor=K.FLOOR):
    idx = {c: i for i, c in enumerate(codes)}
    T = len(dates)
    t0 = int(np.searchsorted(dates, np.datetime64(CR.START)))
    tick = common.tick
    entries, exits, gaps = {}, {}, {}
    for n, x in enumerate(e for e in src if e["strat"] in use):
        x = dict(x, id=n)
        entries.setdefault(x["t_in"], []).append(x)
        exits.setdefault(x["t_out"], []).append(x)
    for x in (gap if "gap" in use else []):
        gaps.setdefault(x["t"], []).append(x)
    cash = CR.CAPITAL
    held = {}
    nav = np.full(T, np.nan)
    pnl = {"gap": [], "trend": [], "ML": []}

    def mval(t):
        return sum(p["units"] * (A[t, idx[k[2]]] / p["a_in"]) for k, p in held.items() if not np.isnan(A[t, idx[k[2]]]))

    def names():
        return {(k[0], k[2]) for k in held}

    for t in range(t0, T):
        nav_prev = nav[t - 1] if t > t0 else CR.CAPITAL
        day_gap, n_gap, mv_open = 0.0, 0, None
        for x in gaps.get(t, []):
            px = (x["open"] + tick(x["open"])) * (1 + CR.FEE_BUY)
            lots = int((K.PCT["gap"] * nav_prev) // (px * CR.LOT))
            cost = lots * CR.LOT * px
            if lots < 1:
                continue
            if mv_open is None:
                mv_open = mval(t)
            if len(names()) + n_gap >= CR.MAX_POS or cost > cash or (floor > 0 and (mv_open + cost) / nav_prev > 1 - floor):
                continue
            cash -= cost
            n_gap += 1
            day_gap += cost * (1 + x["net"])
            pnl["gap"].append((t, cost * x["net"]))
        cash += day_gap
        for x in exits.get(t, []):
            k = (x["strat"], x["tag"], x["code"])
            if k in held and held[k]["id"] == x["id"]:
                p = held.pop(k)
                j = idx[k[2]]
                px = bid[t, j] if 0 < bid[t, j] <= raw[t, j] else raw[t, j] - tick(raw[t, j])
                value = p["units"] * (A[t, j] / p["a_in"]) * (px / raw[t, j]) if not np.isnan(A[t, j]) else p["units"]
                proceeds = value * (1 - CR.FEE_SELL)
                cash += proceeds
                pnl[k[0]].append((t, proceeds - p["cost"]))
        mv = mval(t)
        nav_now = cash + mv
        for x in sorted(entries.get(t, []), key=lambda z: 0 if z["strat"] == "trend" else 1):
            k = (x["strat"], x["tag"], x["code"])
            j = idx[x["code"]]
            if k in held or np.isnan(A[t, j]) or raw[t, j] <= 0:
                continue
            new_name = (x["strat"], x["code"]) not in names()
            px = offer[t, j] if offer[t, j] > 0 and offer[t, j] >= raw[t, j] else raw[t, j] + tick(raw[t, j])
            lots = int((K.PCT[x["strat"]] * x["frac"] * nav_now) // (px * CR.LOT))
            cost = lots * CR.LOT * px * (1 + CR.FEE_BUY)
            if lots < 1:
                continue
            if (new_name and len(names()) >= CR.MAX_POS) or cost > cash or (floor > 0 and (mv + cost) / nav_now > 1 - floor):
                continue
            cash -= cost
            mv += cost / (1 + CR.FEE_BUY)
            held[k] = {"t": t, "a_in": A[t, j], "units": lots * CR.LOT * raw[t, j], "cost": cost, "id": x["id"]}
        nav[t] = cash + mval(t)
    open_ = {}
    for k, p in held.items():                                              # unrealised at the end, marked at the last close
        j = idx[k[2]]
        a = A[T - 1, j]
        open_.setdefault(k[0], 0.0)
        open_[k[0]] += (p["units"] * (a / p["a_in"]) if not np.isnan(a) else p["units"]) - p["cost"]
    return pd.Series(nav[t0:], index=dates[t0:]), pnl, open_


def st(nav):
    s = CR.stats(nav)
    return {k: s[k] for k in ("final", "cagr", "sharpe", "mdd", "by_year")}


def halves(nav, split):
    return [FG.st(nav[nav.index < split]), FG.st(nav[nav.index >= split])]


class TrendSimFixed(FG.TrendSim):
    """#188's TrendSim on a chosen cache/board with the CORRECTED tuple mapping (e = fill day)."""

    def __init__(self, d, dates, cache, board):
        os.environ["IDX_EXIT_CACHE"] = cache
        os.environ["IDX_BOARD_MODE"] = board
        try:
            super().__init__(d, dates)
        finally:
            os.environ.pop("IDX_EXIT_CACHE", None)
            os.environ.pop("IDX_BOARD_MODE", None)

    def trades(self, off):
        entry = self.raw_entry & ~off[:, None]
        _, trs, _ = E.run_book(self.A, self.H, self.L, self.c_in, self.c_out, entry, self.vr.to_numpy(float), self.rule, self.small)
        out = []
        for tup in trs:
            e, j, hold = tup[0], tup[1], tup[4]
            if e + hold >= len(self.d_tr):
                continue
            d_in, d_out = self.d_tr[e], self.d_tr[e + hold]
            if d_in in self.pos and d_out in self.pos and self.cols[j] in self.keep:
                out.append({"strat": "trend", "tag": "p", "frac": 1.0, "code": self.cols[j], "t_in": self.pos[d_in], "t_out": self.pos[d_out]})
        return out


def main() -> int:
    d = FG.dsn()
    if not os.path.exists(PIT_CACHE):
        E.load_all(d, PIT_CACHE, board="pit")
    P = pickle.load(open(ML_CACHE, "rb"))
    P = P[(P["d"] >= "2021-06-01") & (P["d"] <= CR.END)].copy()
    dates = M.wide(P, "close").index
    codes = M.wide(P, "close").columns
    g = lambda c: M.wide(P, c).reindex(index=dates, columns=codes)  # noqa: E731
    A, raw = g("ac").to_numpy(float), g("close").to_numpy(float)
    offer, bid = np.nan_to_num(g("offer").to_numpy(float)), np.nan_to_num(g("bid").to_numpy(float))
    liq = g("liq").fillna(False).astype(bool).to_numpy()
    ml = K.ml_ens_trades(P, dates, codes, A, raw, offer, bid, liq)
    del P
    gap, o = K.gap_events(d, dates)
    OPEN = o.reindex(index=dates, columns=codes).to_numpy(float)
    SECT = np.full((len(dates), len(codes)), None, dtype=object)
    cs = set(codes)
    tr = {}
    for v, (cache, board, legacy) in VARIANTS.items():
        x = CR.trend_trades(d, dates, cache=cache, board=board, legacy_shift=legacy)
        miss = [y for y in x if y["code"] not in cs]
        tr[v] = [dict(y, tag="p", frac=1.0) for y in x if y["code"] in cs]
        M.log(f"{v}: trend {len(x)} trades ({len(miss)} codes outside the ML panel)")
    M.log(f"ML ens4 {len(ml)} rule-trades, gap {len(gap)} events")

    # ML sleeve vs the board on the day (informative: the ML universe is board-agnostic in research AND live)
    Pp = pickle.load(open(PIT_CACHE, "rb"))[0]
    bo = Pp["board_ok"].reindex(index=dates, columns=codes)
    bo = bo.astype(float).to_numpy()                                      # 1 on the board, 0 off, NaN unknown
    offl = [x for x in ml if bo[x["t_in"], codes.get_loc(x["code"])] == 0]
    ml_off, ml_off_names = len(offl), sorted({x["code"] for x in offl})
    M.log(f"ML rule-trades entered while the name was NOT on Utama/Pengembangan: {ml_off}/{len(ml)} ({', '.join(ml_off_names[:15])})")
    del Pp, bo

    # ---- 4 variants ----
    res, navs = {}, {}
    for v in VARIANTS:
        nav, pnl, open_ = engine_attr(dates, codes, A, raw, offer, bid, ml + tr[v], gap)
        if v in ("a_old", "d_fixed"):
            nav_k, _ = K.engine(dates, codes, A, raw, offer, bid, OPEN, SECT, ml + tr[v], gap)
            assert np.allclose(nav.to_numpy(), nav_k.to_numpy(), rtol=0, atol=1e-3), "attribution engine != K.engine"
        s = st(nav)
        s["h"] = K.halves(nav)
        s["sleeve_pnl"] = {sl: {"n": len(p), "realised": float(sum(z for _, z in p)), "win": float(np.mean([z > 0 for _, z in p])) if p else float("nan"),
                                "open": float(open_.get(sl, 0.0)),
                                "by_year": {int(y): float(sum(z for t, z in p if dates[t].year == y)) for y in range(2022, 2027)}} for sl, p in pnl.items()}
        s["alone"] = {}
        for sl in ("trend",) + (("gap", "ML") if v == "a_old" else ()):
            n_, _, _ = engine_attr(dates, codes, A, raw, offer, bid, ml + tr[v], gap, use=(sl,))
            s["alone"][sl] = st(n_)
        res[v], navs[v] = s, nav
        M.log(f"{v:<8} CAGR {s['cagr'] * 100:5.1f} % Sharpe {s['sharpe']:.2f} mDD {s['mdd'] * 100:5.1f} % | "
              + " ".join(f"{str(y)[2:]}:{r * 100:+.0f}" for y, r in s["by_year"].items()) + " | pnl "
              + ", ".join(f"{k} {q['realised'] / 1e6:+.1f}M/{q['n']}" for k, q in s["sleeve_pnl"].items())
              + f" | trend alone {s['alone']['trend']['cagr'] * 100:.1f}/{s['alone']['trend']['sharpe']:.2f}/{s['alone']['trend']['mdd'] * 100:.1f}")
    for sl in ("gap", "ML"):
        for v in ("b_bug1", "c_bug2", "d_fixed"):
            res[v]["alone"][sl] = res["a_old"]["alone"][sl]                # these sleeves' trade lists do not change

    # ---- R1 confirmation trial on the corrected engine ----
    TS = TrendSimFixed(d, dates, PIT_CACHE, "pit")
    TS.keep = cs
    chk = TS.trades(TS.ihsg_off)
    assert [(x["code"], x["t_in"], x["t_out"]) for x in chk] == [(x["code"], x["t_in"], x["t_out"]) for x in tr["d_fixed"]], "TrendSimFixed != corrected trend_trades"
    FP = FG.flow_panels(d)

    def trend_alone(lst):
        n_, _, _ = engine_attr(dates, codes, A, raw, offer, bid, lst, [], use=("trend",))
        return n_

    base_tr = tr["d_fixed"]
    split = dates[int(np.median([x["t_in"] for x in base_tr]))]
    u_nav = trend_alone(base_tr)
    u_full, uh = FG.st(u_nav), halves(u_nav, split)
    r1_tr = TS.trades(TS.mkt_off(FP, 20, 0.0))
    g_nav = trend_alone(r1_tr)
    g_full, gh = FG.st(g_nav), halves(g_nav, split)
    halves_ok = [FG.better(a, b) for a, b in zip(gh, uh)]
    off = TS.mkt_off(FP, 20, 0.0)
    rng = np.random.default_rng(SEED)
    pl = []
    for i in range(N_PLACEBO):
        sh = int(rng.integers(60, len(off) - 60))
        pl.append(FG.st(trend_alone(TS.trades(np.roll(off, sh))))["sharpe"])
        if (i + 1) % 25 == 0:
            M.log(f"placebo {i + 1}/{N_PLACEBO}")
    pl = np.array(pl)
    pct = float((pl < g_full["sharpe"]).mean() * 100)
    comb_nav, comb_pnl, _ = engine_attr(dates, codes, A, raw, offer, bid, ml + r1_tr, gap)
    comb = st(comb_nav)
    comb["h"] = K.halves(comb_nav)
    nb = []
    for sp in FG.neighbours(("mkt_instead", 20, 0.0)):
        ntr = TS.trades(TS.mkt_off(FP, sp[1], sp[2]))
        s_ = FG.st(trend_alone(ntr))
        cn, _, _ = engine_attr(dates, codes, A, raw, offer, bid, ml + ntr, gap)
        nb.append({"spec": list(sp), **s_, "pass": FG.better(s_, u_full), "combined": FG.st(cn), "n": len(ntr)})
    r = g_nav.pct_change().fillna(0.0).to_numpy()
    n_after = N_BEFORE_LEDGER + 1
    dsr = FG.deflated_sharpe(r[r != 0], n_after)
    improves = all(halves_ok) and pct >= 95
    r1 = {"n": len(r1_tr), "n_ungated": len(base_tr), "split": str(split.date()), "gated": g_full, "ungated": u_full, "halves_gated": gh, "halves_ungated": uh,
          "halves_ok": halves_ok, "placebo_pct": pct, "placebo_med": float(np.median(pl)), "placebo_p95": float(np.percentile(pl, 95)),
          "combined": comb, "neighbours": nb, "dsr": dsr, "improves": improves}
    M.log(f"R1 trend alone {g_full} vs {u_full} halves {halves_ok} placebo {pct:.0f} | combined {comb['cagr'] * 100:.1f}/{comb['sharpe']:.2f}/{comb['mdd'] * 100:.1f} "
          f"| nb {[(n_['spec'][1], n_['spec'][2], round(n_['sharpe'], 2), n_['pass']) for n_ in nb]} | DSR {dsr:.2f} | {'IMPROVES' if improves else 'no'}")

    write_report(res, r1, ml_off, len(ml), ml_off_names, tr, n_after)
    if os.environ.get("EF_NOSTORE"):
        return 0
    with psycopg.connect(d) as conn:
        sid = rs.record_study(conn, STUDY, date(2026, 9, 25),
                              params={"n_trials_cumulative": n_after, "n_trials_before": N_BEFORE_LEDGER, "n_before_stated_by_caller": N_BEFORE_CALLER,
                                      "trials_added": 1, "trial": "R1 trend_mkt_instead (mkt 20d net foreign flow < 0 replaces IHSG<MA200) on the corrected engine",
                                      "measurements_not_trials": list(VARIANTS), "deployed": K.PCT, "cash_floor": K.FLOOR, "ml": "ens4", "slots": CR.MAX_POS,
                                      "capital": CR.CAPITAL, "window": [str(CR.START.date()), str(CR.END.date())], "caches": {"old": OLD_CACHE, "pit": PIT_CACHE, "ml": ML_CACHE},
                                      "fixes": {"bug1": "idx_combo_rupiah.trend_trades: d_tr[e], d_tr[e+hold] (e = fill day)",
                                                "bug2": "idx_swing2.panels/build: board on the day (IDX_BOARD_MODE=pit default); idx_exit.load_all refuses a cache of the other mode"},
                                      "n_placebo": N_PLACEBO},
                              summary=common.plain({"variants": {v: {k: x for k, x in s.items()} for v, s in res.items()}, "r1": r1,
                                                    "ml_trades_off_board": {"n": ml_off, "of": len(ml), "names": ml_off_names},
                                                    "new_baseline": {k: res["d_fixed"][k] for k in ("cagr", "sharpe", "mdd", "by_year")}}),
                              names=[], report_path=OUT, note="engine fix: trend replay one day late (bug 1) + current-board look-ahead (bug 2); new official baseline (d); R1 confirmation")
    M.log(f"study #{sid} stored; report {OUT}")
    return 0


def f3(s):
    return f"{s['cagr'] * 100:.1f} % / {s['sharpe']:.2f} / {s['mdd'] * 100:.1f} %"


def write_report(res, r1, ml_off, n_ml, ml_off_names, tr, n_after):
    a, dd = res["a_old"], res["d_fixed"]
    yrs = sorted(a["by_year"])
    L = ["# IDX engine fix - trend replay timing + point-in-time board - 2026-09-25", "",
         f"Measurement corrections (0 trials) + one confirmation trial (R1), cumulative N {N_BEFORE_LEDGER} -> {n_after}. "
         "Script `research/idx_engine_fix.py`. Deployed book: gap 10 % / trend 5 % / ML ens4 5 % of NAV per trade, 20 slots, Rp 20 M, "
         f"cash floor 30 %, {CR.START.date()} -> {CR.END.date()}, the #184 engine (= #177 + ens4 pieces). Cells CAGR / Sharpe / mDD.", "",
         "## The four variants (same run)", "",
         "| variant | trend trades | CAGR | Sharpe | mDD | final NAV | H1 CAGR / mDD | H2 CAGR / mDD | " + " | ".join(str(y) for y in yrs) + " |",
         "|---|---|---|---|---|---|---|---|" + "---|" * len(yrs)]
    for v, s in res.items():
        L.append(f"| {LABEL[v]} | {len(tr[v])} | {s['cagr'] * 100:.1f} % | {s['sharpe']:.2f} | {s['mdd'] * 100:.1f} % | Rp {s['final'] / 1e6:.1f} M | "
                 f"{s['h'][0]['cagr'] * 100:.1f} % / {s['h'][0]['mdd'] * 100:.1f} % | {s['h'][1]['cagr'] * 100:.1f} % / {s['h'][1]['mdd'] * 100:.1f} % | "
                 + " | ".join(f"{s['by_year'][y] * 100:+.0f} %" for y in yrs) + " |")
    L += ["", f"(a) reproduces #184's 'deployed' ({REF_184['cagr'] * 100:.1f} % / {REF_184['sharpe']:.2f} / {REF_184['mdd'] * 100:.1f} %): "
          f"{a['cagr'] * 100:.1f} % / {a['sharpe']:.2f} / {a['mdd'] * 100:.1f} %.", "",
          "## Per sleeve", "", "Realised P&L inside the combined book (Rp M, trades, win rate; open = unrealised at the end) and each sleeve alone on the same engine and floor.", "",
          "| variant | gap P&L | trend P&L | ML P&L | trend alone | gap alone | ML alone |", "|---|---|---|---|---|---|---|"]
    for v, s in res.items():
        sp = s["sleeve_pnl"]
        c = lambda k: f"{sp[k]['realised'] / 1e6:+.1f} M ({sp[k]['n']}, {sp[k]['win'] * 100:.0f} %, open {sp[k]['open'] / 1e6:+.1f})"  # noqa: E731
        L.append(f"| {LABEL[v]} | {c('gap')} | {c('trend')} | {c('ML')} | {f3(s['alone']['trend'])} | {f3(s['alone']['gap'])} | {f3(s['alone']['ML'])} |")
    L += ["", "Deltas vs (a), combined book: " + "; ".join(
        f"{LABEL[v]}: CAGR {(res[v]['cagr'] - a['cagr']) * 100:+.1f} pp, Sharpe {res[v]['sharpe'] - a['sharpe']:+.2f}, mDD {(res[v]['mdd'] - a['mdd']) * 100:+.1f} pp; "
        f"sleeve P&L gap {(res[v]['sleeve_pnl']['gap']['realised'] - a['sleeve_pnl']['gap']['realised']) / 1e6:+.1f} M, "
        f"trend {(res[v]['sleeve_pnl']['trend']['realised'] - a['sleeve_pnl']['trend']['realised']) / 1e6:+.1f} M, "
        f"ML {(res[v]['sleeve_pnl']['ML']['realised'] - a['sleeve_pnl']['ML']['realised']) / 1e6:+.1f} M" for v in ("b_bug1", "c_bug2", "d_fixed")) + ".", "",
          "Trend P&L by year (Rp M): " + "; ".join(f"{LABEL[v]}: " + " ".join(f"{str(y)[2:]} {q / 1e6:+.1f}" for y, q in res[v]["sleeve_pnl"]["trend"]["by_year"].items()) for v in res) + ".", "",
          f"ML sleeve and the board: {ml_off} of {n_ml} ML ens4 rule-trades were entered while the name was NOT on Utama/Pengembangan that day "
          f"({', '.join(ml_off_names[:20]) or '-'}). The ML universe is board-agnostic in research AND in the live runner (combo_book.ml_scores), so this "
          "is not look-ahead and was not changed; restricting ML to the main boards would be a rule change (operator's call).", "",
          "## R1 confirmation on the corrected engine (1 trial)", "",
          f"R1 = market-wide 20-day net foreign flow < 0 -> no new trend entry, INSTEAD of IHSG < MA200 (#188). Trend sleeve alone on the engine, "
          f"halves split at the median ungated entry ({r1['split']}); 200 circular-shift placebos of the same mask.", "",
          "| book | trades | full | half 1 | half 2 |", "|---|---|---|---|---|",
          f"| trend, IHSG gate (baseline d) | {r1['n_ungated']} | {f3(r1['ungated'])} | {f3(r1['halves_ungated'][0])} | {f3(r1['halves_ungated'][1])} |",
          f"| trend, R1 gate | {r1['n']} | {f3(r1['gated'])} | {f3(r1['halves_gated'][0])} | {f3(r1['halves_gated'][1])} |",
          f"| combined book, baseline d | - | {f3(dd)} | {f3(dd['h'][0])} | {f3(dd['h'][1])} |",
          f"| combined book, R1 | - | {f3(r1['combined'])} | {f3(r1['combined']['h'][0])} | {f3(r1['combined']['h'][1])} |", "",
          f"Halves {sum(r1['halves_ok'])}/2 (rule: Sharpe up, mDD not deeper, CAGR >= 0.9x); placebo pct {r1['placebo_pct']:.0f} (median {r1['placebo_med']:.2f}, "
          f"p95 {r1['placebo_p95']:.2f}); DSR @ N {n_after} = {r1['dsr']:.2f}. Verdict: **{'IMPROVES (confirmed)' if r1['improves'] else 'NOT confirmed'}**.", "",
          "Neighbours (counted in #188, not here):", "", "| neighbour (kind, window, thr) | trades | trend alone | passes vs baseline | combined book |", "|---|---|---|---|---|"]
    for n_ in r1["neighbours"]:
        L.append(f"| {tuple(n_['spec'])} | {n_['n']} | {f3(n_)} | {'yes' if n_['pass'] else 'no'} | {f3(n_['combined'])} |")
    open(OUT, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    sys.exit(main())
