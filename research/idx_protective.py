#!/usr/bin/env python3
"""IDX menu 48 - two PROTECTIVE construction rules on the deployed combo book (2026-09-26).

Operator: menu 46 (#283) says a young IPO bought in the secondary market lags matched seasoned names by ~15 % over six months
(every cohort 2020-25); menu 47 (#286) says an MSCI Standard DELETION drifts -627 bps excess from notice to rebalance (t -3.3,
16 reviews). Both are AVOID facts. Menu 48 asks whether turning them into construction rules protects the deployed book.

PRE-REGISTERED (written before any arm was run; 8 counted trials, cumulative N_BEFORE = 999 -> 1007; trial ids 1000..1007)
Engine / baseline: the deployed combo exactly as research/idx_fe_drawdown.py rebuilds it (idx_engine_fix variant d_fixed:
  IDX_BOARD_MODE=pit, trend from tmp/exit_cache_pit.pkl with the corrected tuple mapping, ML ens4 from tmp/ml_strategy_cache.pkl,
  gap events from idx_gapfade.build -> idx_daytrade.load (IDX opens only, read fresh from the DB); gap 10 % / trend 5 % / ML 5 %
  of NAV per trade, 20 slots, cash floor 30 %, Rp 20 M, closing offer/bid, Stockbit fees, 2022-01-01 -> 2026-09-16). The engine is
  a COPY of idx_engine_fix.engine_attr with three hooks (per-trade records, forced exits at the bid, entry blocks), asserted equal
  to engine_attr with the hooks off. Adjusted prices: the caches' in-window daily returns were checked against a fresh read of
  idx.bar close x adj_factor after today's repair (641 fake 2026-09-21 actions removed): max difference 3e-9 - the repair only
  touches 2026-09-21, after the window END, so the caches ARE the fresh prices for this window.
  REFERENCE = the LIVE runner's rule set: ML main_board_only (combo_book DEFAULTS ml.main_board_only=True): drop ML rule-trades
  whose name is NOT on Utama/Pengembangan on the entry day (exit_cache_pit board_ok == 0; unknown kept). Caller's numbers: 650 of
  672 kept, 34.6 % / 1.87 / -17.0 %. Also printed (same run): the #192 variant d without it (caller: 33.8 % / 1.83 / -17.9 %).
  Every arm below is applied ON TOP OF the reference and compared with it in the same run.
A. YOUNG-IPO FILTER. sessions(code, day) = number of IDX sessions (idx.index_daily COMPOSITE dates) d with listing_date <= d <
  entry day (idx.listing.listing_date; a name without a listing_date is never young, count reported). A new entry is dropped
  when sessions < L. Implemented as a trade-list drop (the way main_board_only was measured): the combo engine never sees the
  trade; a slot freed in the book is taken by whatever the book would take next. Entry day = fill day t_in (ML, trend) / the
  event day (gap-fade).
    1000 A125_mt  ML + trend, L = 125     1001 A250_mt  L = 250 (primary)     1002 A500_mt  L = 500
    1003 A125_gap gap-fade only, L = 125  1004 A250_gap L = 250                1005 A500_gap L = 500
  Reported per arm: trade-list entries removed (per sleeve), how many of them the REFERENCE book actually took, and the mean net
  return of those taken (in-book realised proceeds / cost - 1; ML ens4 rule pieces of the same name and fill day are merged
  cost-weighted into one position, t = mean / (sd / sqrt(n)) over positions); plus the stand-alone net of every removed entry.
  Informative, not counted: A250_mt implemented at the CANDIDATE level (trend: masked in the trend book's own entry matrix before
  E.run_book; ML: removed from the ML book's eligible set after the median is taken, as combo_book.ml_scores does for the board).
B. MSCI-DELETION EXIT. Standard-index deletions from menu 47's sourced change lists (idx_msci_predict.REVIEWS; announced date is
  US time, J = first IDX session strictly after it, R = the 'as of the close of' date). For each deletion with J inside the window:
  any position the book HOLDS at the close of J-1 in that name (ML / trend; gap-fade is intraday) is sold at the close of J at
  the closing bid (the engine's exit price rule); new entries in that name (all three sleeves) are blocked for J <= t <= R.
    1006 B_J     sell at the J close           1007 B_J1  sell at the J+1 close (neighbour; same block)
  COUNT FIRST: held-position events = distinct positions in the reference book held at the J-1 close in a deleted name. If fewer
  than 5, B is UNTESTABLE on the combo: 1006/1007 are then spent instead on
    1006 B_value  the annual value book (research/idx_beyond.value_nav = strict composite, May rebalance): each deletion held by
         the value book at J (selection of the latest May rebalance <= J, idx_value_quality.select 'composite_q') - effect =
         holding weight x (0 - the name's net return from the J close at the bid to the next rebalance close), i.e. what selling
         to cash would have added (an approximation of the NAV effect; no re-investment of the cash)
    1007 B_proxy  'held names' proxy: every deletion 2022+ whose name was in ANY sleeve's candidate list (trade list entries of
         ML/trend/gap) within the 60 sessions before J: net return from the J close (bid) to the R close and to J+60 (bid), vs 0.
  and the verdict on the combo is UNTESTABLE regardless of those numbers.
READING RULE: an arm IMPROVES if (Sharpe >= reference + 0.05 AND CAGR >= 0.97 x reference AND mDD not deeper [>= reference mDD
  - 0.05 pp]) in BOTH halves (calendar midpoint of the window, idx_construction.halves), OR the removed trades (in-book positions,
  as defined above) have mean net < 0 with t <= -2 AND the full-window CAGR >= 0.97 x reference. Neighbours must agree: A125 <->
  A250 <-> A500 within a sleeve family (an arm needs every adjacent L to pass too); B_J needs B_J1. Placebo for A: drop the same
  NUMBER of randomly chosen trade-list entries from the same sleeves (per-sleeve counts matched), 200 draws (seed 48); the real
  arm's full-window Sharpe must be >= the 95th percentile of the placebo Sharpes. A passes only if rule + neighbours + placebo.
  DSR of the arm's daily returns at cumulative N = 1007 reported, not gating.
READ-ONLY on the DB except ONE idx.study row ('protective_rules'). No live-book / scheduler / src changes. Run:
  set -a; . blackheart-ingest/idx-local.env; set +a; blackheart-ingest/.venv/Scripts/python research/idx_protective.py
Env: PR_NOSTORE=1 skips the study row; PR_PLACEBO (200).
POST-RUN NOTE (added after the first run, pre-registration above unchanged): this engine reproduces #192 d at 32.92 % / 1.774 /
  -16.89 % (718 ML rule-trades), exactly as IDX_ENGINE_FIX / FE-1 / FE-capacity re-runs print it; the '33.8 % / 1.83 / -17.9 %'
  quote is not what the #192 path prints today. main_board_only keeps 685 of 718 rule-trades (426 of 444 positions) ->
  33.86 % / 1.810 / -15.85 %; the caller's 650/672 and 34.6 % / 1.87 / -17.0 % were not reproduced (different ML trade set).
  The same-run 685/718 reference is what every arm is read against.
"""
from __future__ import annotations

import os
import pickle
import sys
from datetime import date

os.environ["IDX_BOARD_MODE"] = "pit"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.environ["IDX_ML_CACHE"] = os.path.join(ROOT, "tmp", "ml_strategy_cache.pkl")
os.environ["IDX_EXIT_CACHE"] = os.path.join(ROOT, "tmp", "exit_cache_pit.pkl")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blackheart-ingest", "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import psycopg  # noqa: E402

import idx_engine_fix as F  # noqa: E402
from idx_engine_fix import CR, E, FG, K, M  # noqa: E402
from blackheart_ingest.idx import research_store as rs  # noqa: E402
from blackheart_ingest.idx.ml import common  # noqa: E402

STUDY = "protective_rules"
N_BEFORE = 999
TRIALS = {1000: "A125_mt", 1001: "A250_mt", 1002: "A500_mt", 1003: "A125_gap", 1004: "A250_gap", 1005: "A500_gap", 1006: "B_J", 1007: "B_J1"}
N_AFTER = max(TRIALS)
N_PLACEBO = int(os.environ.get("PR_PLACEBO", "200"))
SEED = 48
MIN_HELD = 5
OUT = os.path.join(HERE, "IDX_PROTECTIVE_2026-09-26.md")
INP = os.path.join(ROOT, "tmp", "protective_inputs.pkl")
RES = os.path.join(ROOT, "tmp", "protective_results.pkl")
tick = common.tick


def log(*a):
    print(*a, flush=True)


# ---- engine: copy of idx_engine_fix.engine_attr + per-trade records, forced exits, entry blocks --------------------------------
def engine(dates, codes, A, raw, offer, bid, src, gap, *, use=("gap", "trend", "ML"), floor=K.FLOOR, force=None, block=None):
    """force: {t: set(codes)} - positions in these names are sold at the close of t (bid) before that day's entries.
    block: set of (t, code) - no new entry of any sleeve (gap included) in code on day t."""
    force = force or {}
    block = block or set()
    idx = {c: i for i, c in enumerate(codes)}
    T = len(dates)
    t0 = int(np.searchsorted(dates, np.datetime64(CR.START)))
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
    trades = []                     # (strat, code, t_in, t_out, cost, proceeds, forced)

    def mval(t):
        return sum(p["units"] * (A[t, idx[k[2]]] / p["a_in"]) for k, p in held.items() if not np.isnan(A[t, idx[k[2]]]))

    def names():
        return {(k[0], k[2]) for k in held}

    def sell(k, t, forced):
        nonlocal cash
        p = held.pop(k)
        j = idx[k[2]]
        px = bid[t, j] if 0 < bid[t, j] <= raw[t, j] else raw[t, j] - tick(raw[t, j])
        value = p["units"] * (A[t, j] / p["a_in"]) * (px / raw[t, j]) if not np.isnan(A[t, j]) else p["units"]
        proceeds = value * (1 - CR.FEE_SELL)
        cash += proceeds
        trades.append((k[0], k[2], p["t"], t, p["cost"], proceeds, forced))

    for t in range(t0, T):
        nav_prev = nav[t - 1] if t > t0 else CR.CAPITAL
        day_gap, n_gap, mv_open = 0.0, 0, None
        for x in gaps.get(t, []):
            if (t, x["code"]) in block:
                continue
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
            trades.append(("gap", x["code"], t, t, cost, cost * (1 + x["net"]), False))
        cash += day_gap
        for x in exits.get(t, []):
            k = (x["strat"], x["tag"], x["code"])
            if k in held and held[k]["id"] == x["id"]:
                sell(k, t, False)
        fc = force.get(t)
        if fc:
            for k in [k for k in held if k[2] in fc]:
                j = idx[k[2]]
                if np.isnan(A[t, j]) or raw[t, j] <= 0:        # no close today: cannot sell (not expected for Standard names)
                    continue
                sell(k, t, True)
        mv = mval(t)
        nav_now = cash + mv
        for x in sorted(entries.get(t, []), key=lambda z: 0 if z["strat"] == "trend" else 1):
            k = (x["strat"], x["tag"], x["code"])
            j = idx[x["code"]]
            if k in held or np.isnan(A[t, j]) or raw[t, j] <= 0 or (t, x["code"]) in block:
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
    for k, p in list(held.items()):                                     # open at the end: marked at the last close (no exit cost)
        j = idx[k[2]]
        a = A[T - 1, j]
        trades.append((k[0], k[2], p["t"], None, p["cost"], (p["units"] * (a / p["a_in"]) if not np.isnan(a) else p["units"]), False))
    return pd.Series(nav[t0:], index=dates[t0:]), trades


def st(nav):
    s = CR.stats(nav)
    h = K.halves(nav)
    return {"cagr": s["cagr"], "sharpe": s["sharpe"], "mdd": s["mdd"], "final": s["final"], "by_year": s["by_year"],
            "h": [{k: x[k] for k in ("cagr", "sharpe", "mdd")} for x in h]}


def positions(trades, keep=None):
    """In-book trades merged to positions: (strat, code, t_in) -> cost-weighted net. keep: predicate on (strat, code, t_in)."""
    agg = {}
    for s, c, ti, to, cost, proc, _ in trades:
        if keep is not None and not keep(s, c, ti):
            continue
        a = agg.setdefault((s, c, ti), [0.0, 0.0])
        a[0] += cost
        a[1] += proc
    return {k: v[1] / v[0] - 1 for k, v in agg.items() if v[0] > 0}


def tstat(x):
    x = np.asarray(list(x), float)
    if len(x) < 2 or x.std(ddof=1) == 0:
        return {"n": len(x), "mean": float(x.mean()) if len(x) else float("nan"), "t": float("nan")}
    return {"n": len(x), "mean": float(x.mean()), "t": float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))}


def standalone_net(x, A, raw, offer, bid, codes):
    j = codes.get_loc(x["code"])
    ti, to = x["t_in"], x["t_out"]
    pin = offer[ti, j] if offer[ti, j] > 0 and offer[ti, j] >= raw[ti, j] else raw[ti, j] + tick(raw[ti, j])
    pout = bid[to, j] if 0 < bid[to, j] <= raw[to, j] else raw[to, j] - tick(raw[to, j])
    if np.isnan(A[ti, j]) or np.isnan(A[to, j]):
        return np.nan
    return (A[to, j] / A[ti, j]) * (pout / raw[to, j]) / (pin / raw[ti, j]) * (1 - CR.FEE_SELL) / (1 + CR.FEE_BUY) - 1


# ---- inputs ---------------------------------------------------------------------------------------------------------------------
def build_inputs(d):
    P = pickle.load(open(F.ML_CACHE, "rb"))
    P = P[(P["d"] >= "2021-06-01") & (P["d"] <= CR.END)].copy()
    dates = M.wide(P, "close").index
    codes = M.wide(P, "close").columns
    g = lambda c: M.wide(P, c).reindex(index=dates, columns=codes)  # noqa: E731
    A, raw = g("ac").to_numpy(float), g("close").to_numpy(float)
    offer, bid = np.nan_to_num(g("offer").to_numpy(float)), np.nan_to_num(g("bid").to_numpy(float))
    liq = g("liq").fillna(False).astype(bool).to_numpy()
    ml = K.ml_ens_trades(P, dates, codes, A, raw, offer, bid, liq)
    # candidate-level inputs for the informative A250 check (e5 as K.ml_ens_trades builds it)
    S_ = M.wide(P, "s5").reindex(index=dates, columns=codes).to_numpy(float)
    del P
    gap, _ = K.gap_events(d, dates)
    cache, board, legacy = F.VARIANTS["d_fixed"]
    cs = set(codes)
    tr = [dict(y, tag="p", frac=1.0) for y in CR.trend_trades(d, dates, cache=cache, board=board, legacy_shift=legacy) if y["code"] in cs]
    bo = pickle.load(open(F.PIT_CACHE, "rb"))[0]["board_ok"].reindex(index=dates, columns=codes).astype(float).to_numpy()
    with psycopg.connect(d) as conn:
        L = pd.read_sql("SELECT code, listing_date FROM idx.listing", conn)
        cal = pd.read_sql("SELECT trade_date FROM idx.index_daily WHERE index_code = 'COMPOSITE' ORDER BY trade_date", conn)
    return dict(dates=dates, codes=codes, A=A, raw=raw, offer=offer, bid=bid, liq=liq, S=S_, ml=ml, gap=gap, tr=tr, bo=bo, L=L, cal=cal)


def main() -> int:
    d = FG.dsn()
    if os.path.exists(INP) and not os.environ.get("PR_REBUILD"):
        I = pickle.load(open(INP, "rb"))
    else:
        I = build_inputs(d)
        pickle.dump(I, open(INP, "wb"))
    dates, codes, A, raw, offer, bid = I["dates"], I["codes"], I["A"], I["raw"], I["offer"], I["bid"]
    ml, gap, tr, bo = I["ml"], I["gap"], I["tr"], I["bo"]
    run = lambda src, g, **kw: engine(dates, codes, A, raw, offer, bid, src, g, **kw)  # noqa: E731

    # ---- baselines ----
    nav_chk, _, _ = F.engine_attr(dates, codes, A, raw, offer, bid, ml + tr, gap)
    nav_d, trades_d = run(ml + tr, gap)
    assert np.allclose(nav_d.to_numpy(), nav_chk.to_numpy(), rtol=0, atol=1e-3), "engine copy != engine_attr"
    ml_mb = [x for x in ml if bo[x["t_in"], codes.get_loc(x["code"])] != 0]
    ref_src = ml_mb + tr
    nav_ref, trades_ref = run(ref_src, gap)
    base = {"d": st(nav_d), "ref": st(nav_ref), "n_ml": len(ml), "n_ml_mb": len(ml_mb), "n_tr": len(tr), "n_gap": len(gap),
            "n_ml_pos": len({(x["code"], x["t_in"]) for x in ml}), "n_ml_mb_pos": len({(x["code"], x["t_in"]) for x in ml_mb})}
    log(f"baseline d  {base['d']['cagr']:.3%} {base['d']['sharpe']:.3f} {base['d']['mdd']:.3%}  (ML rule-trades {len(ml)}, positions {base['n_ml_pos']})")
    log(f"reference   {base['ref']['cagr']:.3%} {base['ref']['sharpe']:.3f} {base['ref']['mdd']:.3%}  (ML main-board {len(ml_mb)} / {len(ml)}; positions {base['n_ml_mb_pos']})")
    log(f"halves ref {base['ref']['h']}")

    # ---- listing age ----
    cal = pd.DatetimeIndex(pd.to_datetime(I["cal"]["trade_date"]))
    ld = pd.to_datetime(I["L"].set_index("code")["listing_date"]).reindex(codes)
    lpos = np.array([cal.searchsorted(x) if pd.notna(x) else -10**6 for x in ld])     # first session >= listing date
    dpos = cal.searchsorted(dates)                                                      # session index of each panel date
    no_ld = [c for c, x in zip(codes, ld) if pd.isna(x)]
    log(f"listing_date missing for {len(no_ld)} of {len(codes)} panel codes")

    def sessions(t, code):
        return int(dpos[t] - lpos[codes.get_loc(code)])

    def young(x, t, L):
        return sessions(t, x["code"]) < L

    res = {"base": base, "no_listing_date": no_ld, "arms": {}}
    pos_ref = positions(trades_ref)
    rng = np.random.default_rng(SEED)

    def arm_A(name, L, sleeves):
        if sleeves == "mt":
            src = [x for x in ref_src if not young(x, x["t_in"], L)]
            rem = [x for x in ref_src if young(x, x["t_in"], L)]
            g_ = gap
            rem_gap = []
        else:
            src = ref_src
            rem = []
            g_ = [x for x in gap if not young(x, x["t"], L)]
            rem_gap = [x for x in gap if young(x, x["t"], L)]
        nav, trades = run(src, g_)
        s = st(nav)
        key = {(x["strat"], x["code"], x["t_in"]) for x in rem} | {("gap", x["code"], x["t"]) for x in rem_gap}
        taken = {k: v for k, v in pos_ref.items() if k in key}
        by = {}
        for sl in ("ML", "trend", "gap"):
            by[sl] = {"removed_list": sum(1 for x in rem if x["strat"] == sl) + (len(rem_gap) if sl == "gap" else 0),
                      "removed_pos": len({(x["code"], x["t_in"]) for x in rem if x["strat"] == sl}) + (len(rem_gap) if sl == "gap" else 0),
                      "taken": tstat(v for k, v in taken.items() if k[0] == sl)}
        sa = [standalone_net(x, A, raw, offer, bid, codes) for x in rem] + [x["net"] for x in rem_gap]
        s.update({"removed": {"list": len(rem) + len(rem_gap), "by": by, "taken": tstat(taken.values()),
                              "standalone": tstat(v for v in sa if np.isfinite(v)),
                              "names": sorted({x["code"] for x in rem} | {x["code"] for x in rem_gap})},
                  "dsr": FG.deflated_sharpe(nav.pct_change().fillna(0).to_numpy()[1:], N_AFTER)})
        # placebo: same number of random trade-list entries per sleeve
        pl = []
        for i in range(N_PLACEBO):
            if sleeves == "mt":
                drop = set()
                for sl in ("ML", "trend"):
                    ids = [n for n, x in enumerate(ref_src) if x["strat"] == sl]
                    k = sum(1 for x in rem if x["strat"] == sl)
                    drop |= set(rng.choice(ids, size=k, replace=False).tolist()) if k else set()
                nv, _ = run([x for n, x in enumerate(ref_src) if n not in drop], gap)
            else:
                drop = set(rng.choice(len(gap), size=len(rem_gap), replace=False).tolist()) if rem_gap else set()
                nv, _ = run(ref_src, [x for n, x in enumerate(gap) if n not in drop])
            pl.append(FG.st(nv)["sharpe"])
        pl = np.array(pl)
        s["placebo"] = {"pct": float((pl < s["sharpe"]).mean() * 100), "p95": float(np.percentile(pl, 95)), "med": float(np.median(pl))}
        res["arms"][name] = s
        r_ = s["removed"]
        log(f"{name}: {s['cagr']:.2%} {s['sharpe']:.3f} {s['mdd']:.2%} | removed list {r_['list']} taken {r_['taken']['n']} "
            f"mean {r_['taken']['mean']:+.2%} t {r_['taken']['t']:.2f} | standalone {r_['standalone']['mean']:+.2%} t {r_['standalone']['t']:.2f} "
            f"| placebo pct {s['placebo']['pct']:.0f} p95 {s['placebo']['p95']:.3f}")
        pickle.dump(res, open(RES, "wb"))

    for L in (125, 250, 500):
        arm_A(f"A{L}_mt", L, "mt")
    for L in (125, 250, 500):
        arm_A(f"A{L}_gap", L, "gap")

    # ---- informative: A250_mt at the candidate level ----
    res["cand250"] = cand_level(I, d, ref_src, run, sessions, lpos, dpos)

    # ---- B: MSCI deletions ----
    import idx_msci_predict as MP
    ev = []
    for rv, ann, asof, _, dels, _, _ in MP.REVIEWS:
        J = int(dates.searchsorted(pd.Timestamp(ann), side="right"))
        R = int(dates.searchsorted(pd.Timestamp(asof)))
        if J >= len(dates) or dates[J] < CR.START or not dels:
            continue
        for c in dels.split():
            ev.append({"review": rv, "code": c, "J": J, "R": min(R, len(dates) - 1), "Jd": str(dates[J].date()), "Rd": str(dates[min(R, len(dates) - 1)].date())})
    held_ev = []
    for e in ev:
        for s_, c, ti, to, cost, proc, _ in trades_ref:
            if c == e["code"] and s_ != "gap" and ti <= e["J"] - 1 and (to is None or to > e["J"]):
                held_ev.append({**e, "strat": s_, "t_in": str(dates[ti].date()), "t_out": str(dates[to].date()) if to is not None else None})
    held_pos = {(h["review"], h["code"], h["strat"], h["t_in"]) for h in held_ev}
    blocked = [x for x in ref_src if any(x["code"] == e["code"] and e["J"] <= x["t_in"] <= e["R"] for e in ev)]
    blocked_gap = [x for x in gap if any(x["code"] == e["code"] and e["J"] <= x["t"] <= e["R"] for e in ev)]
    res["B"] = {"events": ev, "held": held_ev, "n_held_positions": len(held_pos), "n_held_names": len({(h["review"], h["code"]) for h in held_ev}),
                "blocked_list": len(blocked), "blocked_gap": len(blocked_gap), "in_universe": sorted({e["code"] for e in ev} & set(codes))}
    log(f"B: {len(ev)} deletions in window; held positions at J-1 close: {len(held_pos)} ({res['B']['n_held_names']} name-events); "
        f"blocked entries: {len(blocked)} ML/trend, {len(blocked_gap)} gap")
    block = {(t, e["code"]) for e in ev for t in range(e["J"], e["R"] + 1)}
    for name, off in (("B_J", 0), ("B_J1", 1)):
        force = {}
        for e in ev:
            force.setdefault(min(e["J"] + off, len(dates) - 1), set()).add(e["code"])
        nav, trades = run(ref_src, gap, force=force, block=block)
        s = st(nav)
        s["forced"] = [(tt[0], tt[1], str(dates[tt[2]].date()), str(dates[tt[3]].date()), tt[5] / tt[4] - 1) for tt in trades if tt[6]]
        s["dsr"] = FG.deflated_sharpe(nav.pct_change().fillna(0).to_numpy()[1:], N_AFTER)
        res["arms"][name] = s
        log(f"{name}: {s['cagr']:.2%} {s['sharpe']:.3f} {s['mdd']:.2%} forced {s['forced']}")
    # what the held positions did from the J close to their planned exit (the counterfactual the rule gives up / saves)
    cf = []
    for h in held_ev:
        for s_, c, ti, to, cost, proc, _ in trades_ref:
            if c == h["code"] and s_ == h["strat"] and str(dates[ti].date()) == h["t_in"]:
                j = codes.get_loc(c)
                Jt = h["J"]
                pJ = bid[Jt, j] if 0 < bid[Jt, j] <= raw[Jt, j] else raw[Jt, j] - tick(raw[Jt, j])
                tt = to if to is not None else len(dates) - 1
                pO = bid[tt, j] if 0 < bid[tt, j] <= raw[tt, j] else raw[tt, j] - tick(raw[tt, j])
                cf.append({"code": c, "strat": s_, "review": h["review"], "hold_after_J": float((A[tt, j] / A[Jt, j]) * (pO / raw[tt, j]) / (pJ / raw[Jt, j]) - 1)})
                break
    res["B"]["counterfactual"] = cf
    pickle.dump(res, open(RES, "wb"))
    if len(held_pos) < MIN_HELD:
        res["B"]["fallback"] = fallback_B(d, ev, I, gap, ref_src, dates, codes, A, raw, bid)
        pickle.dump(res, open(RES, "wb"))
    verdicts(res)
    write_report(res)
    if os.environ.get("PR_NOSTORE"):
        return 0
    with psycopg.connect(d) as conn:
        sid = rs.record_study(conn, STUDY, date(2026, 9, 26),
                              params={"n_trials_cumulative": N_AFTER, "n_trials_before": N_BEFORE, "trials": {str(k): v for k, v in TRIALS.items()},
                                      "reference": "combo #192 d + ML main_board_only (live runner)", "deployed": K.PCT, "cash_floor": K.FLOOR,
                                      "window": [str(CR.START.date()), str(CR.END.date())], "n_placebo": N_PLACEBO, "seed": SEED,
                                      "caches": {"ml": F.ML_CACHE, "pit": F.PIT_CACHE}},
                              summary=common.plain(slim(res)), names=[], report_path=OUT,
                              note="menu 48 protective rules: young-IPO entry filter (A) + MSCI Standard deletion exit (B) on the deployed combo")
    log(f"study #{sid} stored; report {OUT}")
    return 0


def slim(res):
    out = {"base": {k: res["base"][k] for k in res["base"]}, "verdicts": res.get("verdicts"), "arms": {}}
    for k, s in res["arms"].items():
        out["arms"][k] = {x: s[x] for x in s if x not in ("by_year",)}
    out["B"] = {k: v for k, v in res["B"].items() if k != "events"}
    out["cand250"] = res.get("cand250")
    return out


# ---- informative candidate-level A250 --------------------------------------------------------------------------------------
def cand_level(I, d, ref_src, run, sessions, lpos, dpos, L=250):
    dates, codes, A, raw, offer, bid, liq = I["dates"], I["codes"], I["A"], I["raw"], I["offer"], I["bid"], I["liq"]
    young = (dpos[:, None] - lpos[None, :]) < L                                    # T x N
    # ML: e5 from the full liquid set (median unchanged), the book's eligible set minus young names
    c_in, c_out = M.costs(raw, offer, bid)
    e5 = K.C.ema(I["S"] - np.nanmedian(np.where(liq, I["S"], np.nan), axis=1, keepdims=True), 3)
    t0 = int(np.searchsorted(dates, np.datetime64(CR.START)))
    ml = []
    for rule in K.ENS4_ML:
        _, lg = K.F.book(A, liq & ~young, e5, 10, c_in, c_out, 2.0, t_start=t0, wait=rule)
        tag = f"+{rule[0] * 100:.0f}/{rule[1]}"
        ml += [{"strat": "ML", "tag": tag, "frac": 1 / len(K.ENS4_ML), "code": codes[r.j], "t_in": int(r.t_in), "t_out": int(r.t_out)} for r in lg.itertuples()]
    bo = I["bo"]
    ml = [x for x in ml if bo[x["t_in"], codes.get_loc(x["code"])] != 0]
    # trend: the trend book's own entry matrix with young names masked (copy of CR.trend_trades, d_fixed mapping)
    tr = trend_masked(d, dates, codes, L)
    nav, _ = run(ml + tr, I["gap"])
    s = st(nav)
    s.update({"n_ml": len(ml), "n_tr": len(tr)})
    log(f"cand250: {s['cagr']:.2%} {s['sharpe']:.3f} {s['mdd']:.2%} ML {len(ml)} trend {len(tr)}")
    return s


def trend_masked(dsn, dates, codes, L):
    P, unis, comp, Hp, Lp = E.load_all(dsn, F.PIT_CACHE, board="pit")
    c_in, c_out = CR.S.costs(P)
    adj, vol = P["adj"], P["volume"]
    d_tr = adj.index
    with psycopg.connect(dsn) as conn:
        Ls = pd.read_sql("SELECT code, listing_date FROM idx.listing", conn)
        cal = pd.DatetimeIndex(pd.to_datetime(pd.read_sql("SELECT trade_date FROM idx.index_daily WHERE index_code = 'COMPOSITE' ORDER BY trade_date", conn)["trade_date"]))
    ld = pd.to_datetime(Ls.set_index("code")["listing_date"]).reindex(adj.columns)
    lpos = np.array([cal.searchsorted(x) if pd.notna(x) else -10**6 for x in ld])
    young = (cal.searchsorted(d_tr)[:, None] - lpos[None, :]) < L
    A, H, Lo = adj.to_numpy(float), Hp.to_numpy(float), Lp.to_numpy(float)
    ma200 = adj.rolling(200, min_periods=200).mean()
    vr = vol / vol.rolling(20, min_periods=20).median()
    hi = adj.rolling(60, min_periods=60).max()
    entry = ((adj >= hi) & (adj > ma200) & (vr >= 1.5)).to_numpy(bool) & np.asarray(d_tr >= CR.START)[:, None] & ~CR.BY.regime_off_mask(comp, d_tr)[:, None]
    # the signal is at close e-1 and the fill at close e; the filter reads the fill day -> mask the signal row one day earlier
    young_fill = np.vstack([young[1:], young[-1:]])
    entry &= ~young_fill
    prev = adj.shift(1)
    trr = pd.concat([Hp - Lp, (Hp - prev).abs(), (Lp - prev).abs()], axis=1, keys=["a", "b", "c"]).T.groupby(level=1).max().T.reindex(columns=adj.columns)
    ATR = trr.ewm(alpha=1 / 20, adjust=False, min_periods=20).mean().to_numpy(float)
    ma20, ma50 = (adj.rolling(n, min_periods=n).mean().to_numpy(float) for n in (20, 50))
    dd = adj.diff()
    up = dd.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    dn = (-dd.clip(upper=0)).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    RSI = (100 - 100 / (1 + up / dn.replace(0, np.nan))).to_numpy(float)
    LO10 = Lp.shift(1).rolling(10, min_periods=10).min().to_numpy(float)
    LO20 = Lp.shift(1).rolling(20, min_periods=20).min().to_numpy(float)
    rule = E.make_rules(A, H, Lo, ATR, ma20, ma50, RSI, LO10, LO20)["trail10"]
    small = (unis["LIQ"] & ~unis["BLUE"]).to_numpy(bool)
    _, trs, _ = E.run_book(A, H, Lo, c_in, c_out, entry, vr.to_numpy(float), rule, small)
    pos = {x: i for i, x in enumerate(dates)}
    cs = set(codes)
    out = []
    for tup in trs:
        e, j, hold = tup[0], tup[1], tup[4]
        if e + hold >= len(d_tr):
            continue
        d_in, d_out = d_tr[e], d_tr[e + hold]
        if d_in in pos and d_out in pos and adj.columns[j] in cs:
            out.append({"strat": "trend", "tag": "p", "frac": 1.0, "code": adj.columns[j], "t_in": pos[d_in], "t_out": pos[d_out]})
    return out


# ---- B fallback (only if < 5 held events on the combo) ---------------------------------------------------------------------
def fallback_B(d, ev, I, gap, ref_src, dates, codes, A, raw, bid):
    import idx_value_quality as VQ
    out = {"value": [], "proxy": []}
    with psycopg.connect(d) as conn:
        close, vol, delisted, div, ix = VQ.load(conn)
        VQ.FIRST_YEAR = 2021
        rebals = VQ.rebalance_dates(close.index, 5)
        sels = {}
        for D in rebals:
            sel, _ = VQ.select(conn, D)
            sels[D] = sel["composite_q"]
    for e in ev:
        Jd = pd.Timestamp(e["Jd"])
        prior = [D for D in rebals if D <= Jd - pd.Timedelta(days=1)]
        if not prior:
            continue
        D0 = prior[-1]
        nxt = [D for D in rebals if D > Jd]
        if e["code"] not in sels[D0]:
            continue
        end = nxt[0] if nxt else close.index[-1]
        c = close[e["code"]]
        pJ = c.loc[:Jd].dropna().iloc[-1]
        pE = c.loc[:end].dropna().iloc[-1]
        cost = VQ.cost_side(pJ, True)
        hold = pE / pJ - 1
        out["value"].append({"review": e["review"], "code": e["code"], "rebalance": str(D0.date()), "n_names": len(sels[D0]),
                             "hold_to_next_rebal": float(hold), "sell_cost": float(cost),
                             "nav_effect": float((-hold - cost) / max(len(sels[D0]), 1))})
    cand = {}
    for x in ref_src:
        cand.setdefault(x["code"], []).append(x["t_in"])
    for x in gap:
        cand.setdefault(x["code"], []).append(x["t"])
    for e in ev:
        ts = cand.get(e["code"], [])
        if not any(e["J"] - 60 <= t < e["J"] for t in ts) or e["code"] not in set(codes):
            continue
        j = codes.get_loc(e["code"])
        Jt, R = e["J"], e["R"]
        J60 = min(Jt + 60, len(dates) - 1)
        b = lambda t: bid[t, j] if 0 < bid[t, j] <= raw[t, j] else raw[t, j] - tick(raw[t, j])  # noqa: E731
        out["proxy"].append({"review": e["review"], "code": e["code"], "J_to_R": float(A[R, j] / A[Jt, j] - 1), "J_to_J60": float(A[J60, j] / A[Jt, j] - 1)})
    return out


# ---- verdicts and report -----------------------------------------------------------------------------------------------------
def passes(a, ref):
    halves_ok = all(x["sharpe"] >= y["sharpe"] + 0.05 and x["cagr"] >= 0.97 * y["cagr"] and x["mdd"] >= y["mdd"] - 0.0005 for x, y in zip(a["h"], ref["h"]))
    rm = a.get("removed", {}).get("taken", {})
    trade_ok = bool(rm and rm.get("n", 0) >= 2 and rm["mean"] < 0 and rm["t"] <= -2 and a["cagr"] >= 0.97 * ref["cagr"])
    return bool(halves_ok), trade_ok


def verdicts(res):
    ref = res["base"]["ref"]
    v = {}
    for fam in ("mt", "gap"):
        names = [f"A{L}_{fam}" for L in (125, 250, 500)]
        rule = {n: passes(res["arms"][n], ref) for n in names}
        for i, n in enumerate(names):
            nb = [names[k] for k in (i - 1, i + 1) if 0 <= k < 3]
            ok = any(rule[n])
            nb_ok = all(any(rule[m]) for m in nb)
            pl = res["arms"][n]["placebo"]["pct"] >= 95
            v[n] = {"halves": rule[n][0], "trades": rule[n][1], "neighbours": nb_ok, "placebo": pl,
                    "verdict": "IMPROVES" if ok and nb_ok and pl else "no"}
    if res["B"]["n_held_positions"] < MIN_HELD:
        for n in ("B_J", "B_J1"):
            v[n] = {"verdict": f"UNTESTABLE ({res['B']['n_held_positions']} held positions < {MIN_HELD})"}
    else:
        r = {n: passes(res["arms"][n], ref) for n in ("B_J", "B_J1")}
        for n, o in (("B_J", "B_J1"), ("B_J1", "B_J")):
            v[n] = {"halves": r[n][0], "neighbours": r[o][0], "verdict": "IMPROVES" if r[n][0] and r[o][0] else "no"}
    res["verdicts"] = v


def f3(s):
    return f"{s['cagr'] * 100:.1f} % / {s['sharpe']:.2f} / {s['mdd'] * 100:.1f} %"


def write_report(res):
    b = res["base"]
    ref = b["ref"]
    L_ = [f"# IDX menu 48 - protective construction rules (young-IPO filter, MSCI-deletion exit) - 2026-09-26 - 8 trials ({min(TRIALS)}..{N_AFTER}), cumulative N = {N_AFTER}", "",
          "Script `research/idx_protective.py` (pre-registration in its docstring, written before any arm was run). Deployed combo, "
          f"{CR.START.date()} -> {CR.END.date()}, Rp 20 M, gap 10 % / trend 5 % / ML ens4 5 %, 20 slots, cash floor 30 %; cells CAGR / Sharpe / mDD; same run throughout.", "",
          "## Baseline reproduced", "",
          f"- #192 variant d (all ML): **{f3(b['d'])}** (target 33.8 % / 1.83 / -17.9 %); ML {b['n_ml']} rule-trades = {b['n_ml_pos']} (name, fill-day) positions.",
          f"- Reference = d + ML main_board_only (the live runner): **{f3(ref)}** (target 34.6 % / 1.87 / -17.0 %); ML kept {b['n_ml_mb']} of {b['n_ml']} rule-trades "
          f"({b['n_ml_mb_pos']} of {b['n_ml_pos']} positions). Halves (calendar midpoint): {f3(ref['h'][0])} | {f3(ref['h'][1])}.",
          "- Adjusted prices: in-window daily returns of the caches equal a fresh idx.bar close x adj_factor read after today's repair to 3e-9 (the 641 removed actions sit on 2026-09-21, after the window).",
          f"- idx.listing.listing_date missing for {len(res['no_listing_date'])} panel codes (never young).", "",
          "## A - young-IPO entry filter", "",
          "| arm | full | H1 | H2 | list entries removed (ML/trend/gap) | taken by ref book | their mean net (t) | stand-alone mean net (t) | placebo pct (p95) | DSR | halves | trades | neighbours | verdict |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
          f"| reference | {f3(ref)} | {f3(ref['h'][0])} | {f3(ref['h'][1])} | - | - | - | - | - | - | - | - | - | - |"]
    V = res["verdicts"]
    for n in ("A125_mt", "A250_mt", "A500_mt", "A125_gap", "A250_gap", "A500_gap"):
        s = res["arms"][n]
        r = s["removed"]
        by = r["by"]
        v = V[n]
        L_.append(f"| {n} | {f3(s)} | {f3(s['h'][0])} | {f3(s['h'][1])} | {by['ML']['removed_list']}/{by['trend']['removed_list']}/{by['gap']['removed_list']} | "
                  f"{r['taken']['n']} | {r['taken']['mean'] * 100:+.2f} % ({r['taken']['t']:.2f}) | {r['standalone']['mean'] * 100:+.2f} % ({r['standalone']['t']:.2f}) | "
                  f"{s['placebo']['pct']:.0f} ({s['placebo']['p95']:.2f}) | {s['dsr']:.2f} | {'yes' if v['halves'] else 'no'} | {'yes' if v['trades'] else 'no'} | "
                  f"{'yes' if v['neighbours'] else 'no'} | **{v['verdict']}** |")
    L_ += ["", "Taken-by-sleeve (positions the reference book held, mean net, t): " + "; ".join(
        f"{n}: " + ", ".join(f"{sl} {x['taken']['n']} {x['taken']['mean'] * 100:+.1f} % ({x['taken']['t']:.1f})" for sl, x in res["arms"][n]["removed"]["by"].items() if x["taken"]["n"])
        for n in ("A125_mt", "A250_mt", "A500_mt", "A125_gap", "A250_gap", "A500_gap")) + ".", ""]
    c = res.get("cand250")
    if c:
        L_ += [f"Informative (not counted): A250_mt at the candidate level (young names removed from the ML book's eligible set and the trend book's entry matrix, "
               f"so freed slots refill): {f3(c)}; H1 {f3(c['h'][0])}, H2 {f3(c['h'][1])}; ML {c['n_ml']} rule-trades, trend {c['n_tr']}.", ""]
    B = res["B"]
    L_ += ["## B - MSCI Standard deletion exit", "",
           f"{len(B['events'])} Standard deletions with J inside the window ({', '.join(e['review'] + ' ' + e['code'] for e in B['events'])}). "
           f"Held by the reference book at the J-1 close and still held after the J close: **{B['n_held_positions']} positions** ({B['n_held_names']} name-events; rule pieces listed): "
           + (", ".join(f"{h['review']} {h['code']} {h['strat']} (in {h['t_in']})" for h in B["held"]) or "none")
           + f". Entries the block would stop: {B['blocked_list']} ML/trend list entries, {B['blocked_gap']} gap events.", ""]
    if B.get("counterfactual"):
        L_ += ["What those held positions did from the J close to their planned exit: " + ", ".join(f"{x['review']} {x['code']} {x['strat']} {x['hold_after_J'] * 100:+.1f} %" for x in B["counterfactual"]) + ".", ""]
    if B["n_held_positions"] < MIN_HELD:
        L_ += [f"Fewer than {MIN_HELD} held positions: B is UNTESTABLE on the combo; trials 1006/1007 are spent on the fallback below. The engine runs of B_J / B_J1 are printed for information only (one review, both events in the May-2026 freeze deletions).", ""]
    L_ += ["| arm | full | H1 | H2 | forced sells (rule pieces) | verdict |", "|---|---|---|---|---|---|"]
    for n in ("B_J", "B_J1"):
        s = res["arms"][n]
        L_.append(f"| {n} | {f3(s)} | {f3(s['h'][0])} | {f3(s['h'][1])} | {len(s['forced'])} | **{V[n]['verdict']}** |")
    fb = B.get("fallback")
    if fb:
        vv = fb["value"]
        L_ += ["", "Fallback (B untestable on the combo):", "",
               f"- Value book (strict composite, May): {len(vv)} deletion(s) held at J: "
               + (", ".join(f"{x['review']} {x['code']} (book of {x['n_names']}, J -> next rebalance {x['hold_to_next_rebal'] * 100:+.1f} %, NAV effect of selling {x['nav_effect'] * 100:+.2f} %)" for x in vv) or "none")
               + (f"; summed NAV effect {sum(x['nav_effect'] for x in vv) * 100:+.2f} % over the window." if vv else "."),
               f"- 'Held names' proxy (deletions whose name was a candidate of any sleeve in the 60 sessions before J): {len(fb['proxy'])} events; "
               + (f"J -> R mean {np.mean([x['J_to_R'] for x in fb['proxy']]) * 100:+.1f} % ({tstat(x['J_to_R'] for x in fb['proxy'])['t']:.2f}), "
                  f"J -> J+60 mean {np.mean([x['J_to_J60'] for x in fb['proxy']]) * 100:+.1f} % ({tstat(x['J_to_J60'] for x in fb['proxy'])['t']:.2f}): "
                  + ", ".join(f"{x['review']} {x['code']} {x['J_to_R'] * 100:+.1f}/{x['J_to_J60'] * 100:+.1f}" for x in fb["proxy"]) if fb["proxy"] else "none") + "."]
    open(OUT, "w", encoding="utf-8").write("\n".join(L_) + "\n")
    print("\n".join(L_))


if __name__ == "__main__":
    sys.exit(main())
