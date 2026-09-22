#!/usr/bin/env python3
"""IDX menu 25 — robustness scorecard of every strategy the desk has researched (operator, 2026-09-22: "lakukan pada semua strategi
yang kita research supaya mengetahui strategi-strategi yang robust").

One battery, the same for every strategy that ever produced a positive result, so the verdicts are comparable:
  N  neighbours       the rule with one parameter moved at a time — does the result survive?
  P  placebo          the same book with the signal replaced by a random one of the same shape — does the signal carry information?
  T  time blocks      early half / late half (and 2005-19 where prices exist) — does it work in more than one regime?
  C  costs x 1.5      does it survive a worse fill?
  D  delay            (from the earlier delay studies) does a late execution kill it?
  M  multiplicity     DSR at the cumulative trial count.
Verdict per strategy: ROBUST (N, P, T pass), PARTIAL (one fails), FRAGILE (P fails, or two fail), UNTESTABLE (too few independent episodes
for any battery), CLOSED (falsified in its own menu; listed with the study).

PRE-REGISTERED NEW TRIALS (17; cumulative 462 + 17 = 479). Declared before the run; nothing tuned afterwards.
  S1 value strict composite, annual May 2020-26 (deployed `live`), rev. 3 simulator (reset, real costs, dividends net of tax):
     N: top quarter / sixth / eighth instead of fifth; E/P only; E/P + B/P; loose gate (6 trials). PASS = CAGR >= 75 % of the rule AND Sharpe >= rule - 0.15.
     P: 200 books of the same size drawn at random from the strict-gate pool at each rebalance. PASS = rule Sharpe >= 95th percentile.
     T: May 2020 -> May 2023 and May 2023 -> Sep 2026: the rule beats the equal-weight strict pool in both. C: costs x 1.5 keeps CAGR >= 75 %.
  S5 asymmetric rule on the strict list (RSI14 <= 30 entry, MA200 cross-below exit, monthly checks, drift, IDX_ASYMMETRIC 2026-09-13):
     N: RSI 25, RSI 35, MA150, MA250 (4 trials), each on the four calendars, read with the rule's own bar (Sharpe > none in >= 3/4 calendars
     with CAGR >= 90 % of none's, worst drawdown shallower). P: 100 time shifts of the RSI and MA signals (20-400 trading days), May calendar:
     PASS = the real arm's Sharpe advantage over `none` >= 95th percentile of the shifted arms'. T: the two calendar halves.
  S7 combined book value + trend (menu 21 B): weights 30/70, 40/60, 60/40, 70/30 (4 trials; 50/50 exists). N PASS = >= 4 of 5 weights pass
     the money rule (Sharpe >= 1, mDD <= 25 %). T: 2021-23 / 2024-26.
  S8 allocation layer in rupiah (menu 21 D): gem lookback 6 and 9 months, EW without gold (3 trials). T: 2006-12 / 2013-19 / 2020-26.
  Compiled, no new runs: trend rule (studies #22-23, #45-46, #63 V5), regime_gate (#63), os_ma50 (#65), crash switch / take-profit +100 % /
     index regime filter / cash buffer (2026-09-13/14 reports: episodes n <= 2 -> UNTESTABLE or damper), and the CLOSED families.
READ-ONLY. INGEST_DB_DSN=... PYTHONIOENCODING=utf-8 blackheart-ingest/.venv/Scripts/python research/idx_robustness_scorecard.py [--placebo 200] [--no-store]
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
import equity_screen as ES  # noqa: E402
import idx_asymmetric as AS  # noqa: E402
import idx_beyond as B  # noqa: E402
import idx_exit as E  # noqa: E402
import idx_swing2 as S  # noqa: E402
import idx_trend_overlay as TO  # noqa: E402
import idx_value_quality as VQ  # noqa: E402
from blackheart_ingest.idx import candidates as cand  # noqa: E402
from blackheart_ingest.idx import strategies as ST  # noqa: E402

N_BEFORE = 462
N_TRIALS = N_BEFORE + 17
SEED = 20260923
K = B.K


def stat_nav(nav: pd.Series, rebals) -> dict:
    s = VQ.stats(nav, rebals)
    r = s.pop("_r", None)
    s["dsr"] = round(ES.deflated_sharpe(list(r), N_TRIALS), 3) if r is not None else None
    return s


def fmt(s):
    return f"CAGR {s['cagr_pct']:+.1f} %, Sharpe {s['sharpe']:.2f}, mDD {s['mdd_pct']:.0f} %"


# ------------------------------------------------------------------------------------------------------------- S1 value rule

def s1_value(conn, close, vol, delisted, div, rows_cache, n_placebo):
    VQ.FIRST_YEAR = 2020
    rebals = VQ.rebalance_dates(close.index, 5)
    end = close.index[-1]
    rows = {}
    for D in rebals:
        if D not in rows_cache:
            rows_cache[D] = cand.build(conn, D.date())["all_rows"]
            print(f"S1 rows {D.date()}: {len(rows_cache[D])}", flush=True)
        rows[D] = rows_cache[D]
    rule = {D: {x["code"] for x in ST.pick("strict", rows[D]) if x["selected"]} for D in rebals}
    pool = {D: sorted({x["code"] for x in rows[D] if x["tradable"] and x["gate_strict"]}) for D in rebals}

    def sim(sel, cost=1.0):
        old = VQ.COST_SIDE
        VQ.COST_SIDE = old * cost
        try:
            return VQ.simulate(sel, close, vol, delisted, div, rebals[0], end, True)
        finally:
            VQ.COST_SIDE = old
    nav_rule = sim(rule)
    st_rule = stat_nav(nav_rule, rebals)
    nav_pool = sim({D: set(pool[D]) for D in rebals})
    st_pool = stat_nav(nav_pool, rebals)
    print(f"S1 rule {fmt(st_rule)} | strict pool EW {fmt(st_pool)}", flush=True)
    neigh = {"top_quarter": dict(gate="strict", keys=cand.KEYS, top_fraction=4), "top_sixth": dict(gate="strict", keys=cand.KEYS, top_fraction=6),
             "top_eighth": dict(gate="strict", keys=cand.KEYS, top_fraction=8), "ep_only": dict(gate="strict", keys=("ep",)),
             "ep_bp": dict(gate="strict", keys=("ep", "bp")), "loose_gate": dict(gate="loose", keys=cand.KEYS)}
    nres = {}
    for k, kw in neigh.items():
        sel = {D: {x["code"] for x in cand.rank_pool([dict(x) for x in rows[D]], **kw) if x["selected"]} for D in rebals}
        s = stat_nav(sim(sel), rebals)
        s["read"] = "PASS" if (s["cagr_pct"] >= 0.75 * st_rule["cagr_pct"] and s["sharpe"] >= st_rule["sharpe"] - 0.15) else "fail"
        s["names"] = float(np.mean([len(sel[D]) for D in rebals]))
        nres[k] = s
        print(f"S1 N {k:12s} names {s['names']:.0f} {fmt(s)} {s['read']}", flush=True)
    rng = np.random.default_rng(SEED)
    pl = []
    for i in range(n_placebo):
        sel = {D: set(rng.choice(pool[D], size=min(len(rule[D]), len(pool[D])), replace=False)) for D in rebals}
        s = stat_nav(sim(sel), rebals)
        pl.append((s["sharpe"], s["cagr_pct"], s["mdd_pct"]))
        if (i + 1) % 50 == 0:
            print(f"S1 placebo {i + 1}/{n_placebo}", flush=True)
    pl = np.array(pl)
    pct = {"sharpe": float((pl[:, 0] < st_rule["sharpe"]).mean() * 100), "cagr": float((pl[:, 1] < st_rule["cagr_pct"]).mean() * 100),
           "mdd": float((pl[:, 2] < st_rule["mdd_pct"]).mean() * 100)}
    placebo = {"n": n_placebo, "median": {"sharpe": float(np.median(pl[:, 0])), "cagr": float(np.median(pl[:, 1])), "mdd": float(np.median(pl[:, 2]))},
               "p95_sharpe": float(np.percentile(pl[:, 0], 95)), "p95_cagr": float(np.percentile(pl[:, 1], 95)), "pct": pct, "pass": pct["sharpe"] >= 95}
    print(f"S1 P rule Sharpe {st_rule['sharpe']:.2f} at pct {pct['sharpe']:.0f} (median {placebo['median']['sharpe']:.2f}, p95 {placebo['p95_sharpe']:.2f}); "
          f"CAGR pct {pct['cagr']:.0f}; mDD pct {pct['mdd']:.0f}", flush=True)
    mid = rebals[3]
    blocks = {}
    for name, (a, b, rb) in {"2020-23": (rebals[0], mid, rebals[:4]), "2023-26": (mid, end, rebals[3:])}.items():
        blocks[name] = {"rule": stat_nav(nav_rule.loc[a:b], rb), "pool": stat_nav(nav_pool.loc[a:b], rb),
                        "placebo_median_sharpe": None}
        print(f"S1 T {name}: rule {fmt(blocks[name]['rule'])} | pool {fmt(blocks[name]['pool'])}", flush=True)
    t_pass = sum(1 for v in blocks.values() if v["rule"]["sharpe"] > v["pool"]["sharpe"] and v["rule"]["cagr_pct"] > v["pool"]["cagr_pct"])
    st_cost = stat_nav(sim(rule, 1.5), rebals)
    n_pass = sum(1 for v in nres.values() if v["read"] == "PASS")
    checks = {"N": n_pass >= 4, "P": placebo["pass"], "T": t_pass == 2, "C": st_cost["cagr_pct"] >= 0.75 * st_rule["cagr_pct"]}
    return {"rule": st_rule, "pool": st_pool, "neighbours": nres, "n_pass": n_pass, "placebo": placebo, "blocks": blocks, "t_pass": t_pass, "cost15": st_cost,
            "checks": checks, "verdict": verdict_of(checks), "rebalances": [str(r.date()) for r in rebals], "list_size": float(np.mean([len(rule[D]) for D in rebals]))}


def verdict_of(checks: dict) -> str:
    core = [k for k in ("N", "P", "T") if k in checks]
    failed = [k for k in core if not checks[k]]
    if not failed:
        return "ROBUST"
    if "P" in failed or len(failed) >= 2:
        return "FRAGILE"
    return "PARTIAL: " + ",".join(failed)


# ------------------------------------------------------------------------------------------------------------- S5 asymmetric rule

def asym_calendar(conn, close, vol, delisted, div, jk, rows_cache, month, rsi_max=30.0, sma=200, shift=0):
    AS.RSI_MAX = rsi_max
    TO.SMA = sma
    VQ.FIRST_YEAR = 2021
    rebals = VQ.rebalance_dates(close.index, month)
    end = close.index[-1]
    lists = {}
    for D in rebals:
        if D not in rows_cache:
            rows_cache[D] = cand.build(conn, D.date())["all_rows"]
        lists[D] = {r["code"] for r in ST.pick("strict", rows_cache[D]) if r["selected"]}
    checks = sorted(set(TO.month_starts(close.index, rebals[0], end)) | set(rebals))
    sig = TO.Signals(close, jk, checks)
    rsi_all = AS.rsi(close)
    if shift:
        rsi_all = rsi_all.shift(shift)
        sig.sma = close.rolling(sma, min_periods=sma).mean().shift(shift).reindex(checks, method="ffill")
    rsi_at = rsi_all.reindex(checks, method="ffill")
    dummy = pd.DataFrame(np.nan, index=checks, columns=close.columns)

    def slot(d, lists=lists):
        return 1 / max(1, len(lists[max(a for a in lists if a <= d)]))
    out = {}
    for kind in ("none", "asym_rsi"):
        plan = TO.build_plan(kind, lists, sig) if kind == "none" else AS.build_asym(kind, lists, sig, close, rsi_at, dummy, None)
        nav = VQ.simulate(plan, close, vol, delisted, div, rebals[0], end, True, mode="drift", cap=slot, cash_rate=TO.CASH_RATE)
        out[kind] = {"nav": nav, "stats": stat_nav(nav, rebals), "rebals": rebals}
    return out


def asym_bar(per_month: dict) -> dict:
    wins = sum(1 for m, v in per_month.items() if v["asym_rsi"]["stats"]["sharpe"] > v["none"]["stats"]["sharpe"]
               and v["asym_rsi"]["stats"]["cagr_pct"] >= 0.9 * v["none"]["stats"]["cagr_pct"])
    dd_a = max(v["asym_rsi"]["stats"]["mdd_pct"] for v in per_month.values())      # VQ.stats reports drawdown depth as a positive %
    dd_n = max(v["none"]["stats"]["mdd_pct"] for v in per_month.values())
    return {"wins": wins, "worst_mdd": dd_a, "none_worst_mdd": dd_n, "pass": wins >= 3 and dd_a < dd_n}


def s5_asym(conn, close, vol, delisted, div, ix, rows_cache, n_placebo):
    jk = ix["COMPOSITE"].dropna()
    months = (5, 2, 8, 11)
    base = {m: asym_calendar(conn, close, vol, delisted, div, jk, rows_cache, m) for m in months}
    bar = asym_bar(base)
    for m in months:
        print(f"S5 base month {m}: none {fmt(base[m]['none']['stats'])} | asym {fmt(base[m]['asym_rsi']['stats'])}", flush=True)
    print(f"S5 base bar: wins {bar['wins']}/4 worst mDD {bar['worst_mdd']:.0f} vs none {bar['none_worst_mdd']:.0f} -> {'PASS' if bar['pass'] else 'fail'}", flush=True)
    neigh = {"rsi25": dict(rsi_max=25.0), "rsi35": dict(rsi_max=35.0), "sma150": dict(sma=150), "sma250": dict(sma=250)}
    nres = {}
    for k, kw in neigh.items():
        per = {m: asym_calendar(conn, close, vol, delisted, div, jk, rows_cache, m, **kw) for m in months}
        b = asym_bar(per)
        b["by_month"] = {m: {"none": per[m]["none"]["stats"], "asym": per[m]["asym_rsi"]["stats"]} for m in months}
        b["avg_cagr"] = float(np.mean([per[m]["asym_rsi"]["stats"]["cagr_pct"] for m in months]))
        b["avg_sharpe"] = float(np.mean([per[m]["asym_rsi"]["stats"]["sharpe"] for m in months]))
        nres[k] = b
        print(f"S5 N {k:7s} wins {b['wins']}/4 worst mDD {b['worst_mdd']:.0f} vs {b['none_worst_mdd']:.0f} avg CAGR {b['avg_cagr']:.1f} Sharpe {b['avg_sharpe']:.2f} -> {'PASS' if b['pass'] else 'fail'}", flush=True)
    real_adv = base[5]["asym_rsi"]["stats"]["sharpe"] - base[5]["none"]["stats"]["sharpe"]
    rng = np.random.default_rng(SEED)
    adv = []
    for i in range(n_placebo):
        k = int(rng.integers(20, 400))
        per = asym_calendar(conn, close, vol, delisted, div, jk, rows_cache, 5, shift=k)
        adv.append(per["asym_rsi"]["stats"]["sharpe"] - per["none"]["stats"]["sharpe"])
        if (i + 1) % 25 == 0:
            print(f"S5 placebo {i + 1}/{n_placebo}", flush=True)
    adv = np.array(adv)
    pct = float((adv < real_adv).mean() * 100)
    placebo = {"n": n_placebo, "real_adv": float(real_adv), "median_adv": float(np.median(adv)), "p95_adv": float(np.percentile(adv, 95)), "pct": pct, "pass": pct >= 95}
    print(f"S5 P real Sharpe advantage {real_adv:+.2f} at pct {pct:.0f} (placebo median {placebo['median_adv']:+.2f}, p95 {placebo['p95_adv']:+.2f})", flush=True)
    reb = base[5]["none"]["rebals"]
    mid = reb[len(reb) // 2]
    blocks = {}
    for name, (a, b, rb) in {"early": (reb[0], mid, reb[:len(reb) // 2 + 1]), "late": (mid, close.index[-1], reb[len(reb) // 2:])}.items():
        blocks[name] = {k: stat_nav(base[5][k]["nav"].loc[a:b], rb) for k in ("none", "asym_rsi")}
        print(f"S5 T {name} ({a.date()} -> {b.date()}): none {fmt(blocks[name]['none'])} | asym {fmt(blocks[name]['asym_rsi'])}", flush=True)
    t_pass = sum(1 for v in blocks.values() if v["asym_rsi"]["sharpe"] > v["none"]["sharpe"])
    n_pass = sum(1 for v in nres.values() if v["pass"])
    checks = {"N": n_pass >= 3, "P": placebo["pass"], "T": t_pass == 2}
    return {"base": {m: {"none": base[m]["none"]["stats"], "asym": base[m]["asym_rsi"]["stats"]} for m in months}, "bar": bar, "neighbours": nres, "n_pass": n_pass,
            "placebo": placebo, "blocks": blocks, "t_pass": t_pass, "checks": checks, "verdict": verdict_of(checks)}


# ------------------------------------------------------------------------------------------------------------- S7 combined book

def s7_combo(dsn, P, unis, Hp, Lp):
    c_in, c_out = S.costs(P)
    dates = P["adj"].index
    A, H, L, entry, score, ATR, SIG, trail10, universes = B.prep_panels(P, unis, Hp, Lp)
    R_tr, _, _ = E.run_book(A, H, L, c_in, c_out, entry, score, trail10, universes["small"])
    R_tr.index = dates
    nav_v = B.value_nav(dsn)
    rets = pd.DataFrame({"value": nav_v.pct_change().fillna(0.0), "trend": R_tr}).dropna()
    rets = rets[(rets.index >= B.COMBO_START) & (rets.index <= min(nav_v.index[-1], dates[-1]))]
    res = {}
    for wv in (0.3, 0.4, 0.5, 0.6, 0.7):
        nav = B.combine(rets, lambda d, h, wv=wv: {"value": wv, "trend": 1 - wv})
        s = B.series_stats(nav.pct_change().fillna(0.0))
        s["money"] = s["sharpe"] >= 1.0 and s["mdd"] >= -0.25
        res[f"{int(wv * 100)}/{int((1 - wv) * 100)}"] = s
        print(f"S7 {int(wv * 100)}/{int((1 - wv) * 100)}: cagr {s['cagr'] * 100:+.1f}% sharpe {s['sharpe']:.2f} mdd {s['mdd'] * 100:.0f}% {'money' if s['money'] else 'fail'}", flush=True)
    n_pass = sum(1 for v in res.values() if v["money"])
    nav50 = B.combine(rets, lambda d, h: {"value": 0.5, "trend": 0.5})
    r50 = nav50.pct_change().fillna(0.0)
    blocks = {"2021-23": B.series_stats(r50[r50.index < "2024-01-01"]), "2024-26": B.series_stats(r50[r50.index >= "2024-01-01"])}
    for k, v in blocks.items():
        print(f"S7 T {k}: cagr {v['cagr'] * 100:+.1f}% sharpe {v['sharpe']:.2f} mdd {v['mdd'] * 100:.0f}%", flush=True)
    t_pass = sum(1 for v in blocks.values() if v["sharpe"] >= 1.0 and v["mdd"] >= -0.25)
    checks = {"N": n_pass >= 4, "T": t_pass == 2}
    return {"weights": res, "n_pass": n_pass, "blocks": blocks, "t_pass": t_pass, "checks": checks, "verdict": verdict_of(checks), "corr": float(rets["value"].corr(rets["trend"]))}


# ------------------------------------------------------------------------------------------------------------- S8 allocation layer

def s8_alloc(dsn):
    jk = pd.read_csv(os.path.join(B.YAHOO, "_JKSE.csv"), parse_dates=["date"]).set_index("date")["close"].astype(float).sort_index()
    sp = pd.read_csv(os.path.join(B.SCRATCH, "gspc.csv"), parse_dates=["date"]).set_index("date")["close"].astype(float).sort_index()
    with psycopg.connect(dsn) as conn:
        m = pd.read_sql("SELECT series, obs_date, value FROM idx.macro WHERE series IN ('gold', 'usdidr', 'bi_rate_hist', 'bi_rate') ORDER BY 2", conn)
    m["obs_date"] = pd.to_datetime(m["obs_date"])
    gold = m[m.series == "gold"].set_index("obs_date")["value"].astype(float)
    fx = m[m.series == "usdidr"].set_index("obs_date")["value"].astype(float)
    bi = pd.concat([m[m.series == "bi_rate_hist"].set_index("obs_date")["value"], m[m.series == "bi_rate"].set_index("obs_date")["value"]]).astype(float).sort_index()
    for k, v in B.BI_FILL.items():
        bi.loc[pd.Timestamp(k + "-01")] = v
    bi = bi.sort_index()
    me = lambda s: s.resample("ME").last()  # noqa: E731
    px = pd.DataFrame({"IHSG": me(jk), "SP_IDR": me(sp) * me(fx), "GOLD_IDR": me(gold) * me(fx)}).dropna()
    px = px[px.index >= "2004-12-31"]
    rate = ((bi.resample("ME").last().reindex(px.index, method="ffill") - B.CASH_SPREAD) / 100).ffill().fillna(0.05)
    cash_m = (1 + rate) ** (1 / 12) - 1
    rets = px.pct_change()
    idx = px.index

    def run(choose, lb):
        mom = px / px.shift(lb) - 1
        cash_l = (1 + cash_m).rolling(lb).apply(np.prod, raw=True) - 1
        R, prev = [], None
        for i in range(12, len(idx) - 1):
            a = choose(i, mom, cash_l)
            r = float(cash_m.iloc[i + 1]) if a == "CASH" else float(rets.iloc[i + 1][a])
            if prev is not None and a != prev:
                r -= B.SWITCH_COST
            prev = a
            R.append((idx[i + 1], r))
        return pd.Series([x[1] for x in R], index=[x[0] for x in R])

    def gem(i, mom, cash_l):
        if mom.iloc[i]["IHSG"] > cash_l.iloc[i]:
            return "IHSG" if mom.iloc[i]["IHSG"] >= mom.iloc[i]["SP_IDR"] else "SP_IDR"
        return "CASH"
    series = {f"gem_{lb}m": run(gem, lb) for lb in (6, 9, 12)}
    sub = rets.iloc[13:]
    series["EW3"] = sub[["IHSG", "SP_IDR", "GOLD_IDR"]].mean(axis=1)
    series["EW2_no_gold"] = sub[["IHSG", "SP_IDR"]].mean(axis=1)
    series["IHSG"] = sub["IHSG"]
    res = {k: B.series_stats(v, per_year=12) for k, v in series.items()}
    ih = res["IHSG"]
    for k, s in res.items():
        s["beats_index"] = s["sharpe"] >= ih["sharpe"] + 0.30 and s["mdd"] >= -0.25 and s["cagr"] >= ih["cagr"]
        print(f"S8 {k:12s} cagr {s['cagr'] * 100:+.1f}% sharpe {s['sharpe']:.2f} mdd {s['mdd'] * 100:.0f}% {'beats index' if s['beats_index'] else '-'}", flush=True)
    blocks = {}
    for name, (a, b) in {"2006-12": ("2006-01-01", "2013-01-01"), "2013-19": ("2013-01-01", "2020-01-01"), "2020-26": ("2020-01-01", "2027-01-01")}.items():
        blocks[name] = {k: B.series_stats(v[(v.index >= a) & (v.index < b)], per_year=12) for k, v in series.items() if k in ("gem_12m", "EW3", "IHSG")}
        print(f"S8 T {name}: " + " | ".join(f"{k} {v['cagr'] * 100:+.1f}%/{v['sharpe']:.2f}/{v['mdd'] * 100:.0f}%" for k, v in blocks[name].items()), flush=True)
    n_pass = sum(1 for k in ("gem_6m", "gem_9m", "gem_12m") if res[k]["beats_index"])
    t_gem = sum(1 for v in blocks.values() if v["gem_12m"]["sharpe"] >= v["IHSG"]["sharpe"])
    t_ew = sum(1 for v in blocks.values() if v["EW3"]["sharpe"] >= v["IHSG"]["sharpe"])
    checks_gem = {"N": n_pass >= 2, "T": t_gem == 3}
    checks_ew = {"N": res["EW2_no_gold"]["sharpe"] >= ih["sharpe"] + 0.30, "T": t_ew == 3}
    return {"res": res, "blocks": blocks, "gem": {"n_pass": n_pass, "t_pass": t_gem, "checks": checks_gem, "verdict": verdict_of(checks_gem)},
            "ew3": {"t_pass": t_ew, "checks": checks_ew, "verdict": verdict_of(checks_ew)}}


# ------------------------------------------------------------------------------------------------------------- compiled rows

COMPILED = [
    {"strategy": "Trend hi60/MA200/vol1.5x/trail10, K=10, small (paper_trend, trend_live)", "evidence": "2020-26 IDX quotes (496 trades) + 2005-19 Yahoo survivors (612)",
     "N": "5/7 neighbours (#23); exits 0/30 better (#44-45) = settled", "P": "random entries + trail10: Sharpe 0.70 vs 1.31 (#23); 0.71 vs 0.89 in 2005-19 (#46)",
     "T": "years +5/7 (2020-26), 12/15 (2005-19); base rate 13 %/yr, 2020-26 = best block in 22 yrs (#46)", "C_D": "costs quoted spread; 1-day-late entry: Sharpe 1.31 -> 0.91 (#63 V5)",
     "M": "DSR 0.64 @428", "verdict": "ROBUST (rule) / FRAGILE to execution delay", "note": "money rule fails on mDD -30 % only"},
    {"strategy": "regime_gate: trend + no entry while IHSG < MA200", "evidence": "same as trend; #62, #63 (12 trials + 200 placebos)",
     "N": "3/6 regime, 1/5 entry neighbours", "P": "Sharpe at 99th pct of 200 shifted regimes; mDD -18 vs placebo median -30", "T": "Sharpe >= ungated in 2/5 blocks; rolling 48/54 %; mDD shallower 84/87 %",
     "C_D": "costs x1.5 ok (1.41); 1-day-late 0.76", "M": "DSR 0.82 @433", "verdict": "PARTIAL (drawdown rule validated, return gain not)", "note": "money-rule CANDIDATE on small"},
    {"strategy": "os_ma50: trend + entry allowed when IHSG >= MA200 or >= MA50", "evidence": "same; #64, #65 (12 trials + 200 placebos)",
     "N": "5/6 regime, 5/5 entry neighbours", "P": "Sharpe at 94th pct (bar 95); mDD passes; lag20 1.62", "T": "4/5 blocks; rolling 71/82 %; all 7 calendar years positive",
     "C_D": "costs x1.5 1.36; 1-day-late 0.92", "M": "DSR ~0.8 @450", "verdict": "FRAGILE by the letter (placebo 94) / strongest neighbourhood of any rule", "note": "money-rule CANDIDATE on small"},
    {"strategy": "Crash switch: strict -> cheapest E/P fifth after -20 %, back above MA200", "evidence": "2 episodes (2020, 2025-26), 4 calendars (IDX_CRASH_SWITCH 09-14)",
     "N": "loose gate +1 pt; price-only version fails (47 % mDD)", "P": "not possible (n = 2)", "T": "1.5 episodes", "C_D": "-", "M": "-", "verdict": "UNTESTABLE (n = 2 episodes)", "note": "passed its bar, thinnest evidence in the project"},
    {"strategy": "Take-profit +100 % on the value book", "evidence": "10 doubling events (IDX_SELL_RULES 09-13)", "N": "+50 % fails 3/4", "P": "not possible (n = 10)", "T": "-", "C_D": "-", "M": "-",
     "verdict": "UNTESTABLE (n = 10 events)", "note": "book option, off"},
    {"strategy": "Index regime filter on the value book (all to cash under MA200)", "evidence": "2008-26 basket + 2021-26 book (IDX_TREND_OVERLAY 09-13)",
     "N": "MA100 halves return on the real book; 200/250 alike", "P": "-", "T": "2008: 0 vs -36; 2020: -13 vs -47; costs 0-49 % of return in calm years", "C_D": "5 sessions late ~1 pt",
     "M": "-", "verdict": "ROBUST as a damper, costs return", "note": "operator's call, not adopted"},
    {"strategy": "Cash buffer 30 % / 50 % on stress", "evidence": "2008-26 basket + 2021-26 book (IDX_CASH_BUFFER 09-14)", "N": "4 detectors alike", "P": "-", "T": "2008/2020 -28..-37", "C_D": "-", "M": "-",
     "verdict": "ROBUST as a damper, fails return floor by 2 pts", "note": "book option, off"},
]

CLOSED = [
    ("swing 2-5 days (46 trials)", "#14, #15"), ("foreign-flow / accumulation (6)", "#16"), ("bandarmologi broker flow (19)", "#18, #19"), ("sleepers 5d-2y (8)", "#25, #26"),
    ("small-cap PIT growth rules (4 costed)", "#27-29"), ("doublers / multibagger sleeve", "IDX_DOUBLER_SLEEVE 09-13"), ("ARA hunter (24) + ML ARA (3)", "#56, #59"),
    ("ML loser filter on trend (2)", "#58"), ("support / resistance (4)", "#60"), ("per-name sizing, vol target, pyramid (10); sector rotation (3)", "#61"),
    ("quality / QARP / factor book / top10 / top3 / sector-relative / hold winners / mom+growth", "IDX_QUALITY, IDX_FACTOR_BOOK, IDX_TOP10, IDX_TOP3_UPSIDE, IDX_SECTOR_RELATIVE, IDX_HOLD_WINNERS, IDX_MOM_GROWTH 09-12..14"),
]


# ------------------------------------------------------------------------------------------------------------- report

def report(out: dict, path: str):
    s1, s5, s7, s8 = out.get("S1"), out.get("S5"), out.get("S7"), out.get("S8")
    L = [f"# IDX menu 25 — robustness scorecard of every researched strategy — {date.today()} — 17 new trials, cumulative N = {N_TRIALS}", "",
         "Battery: N neighbours · P placebo · T time blocks · C costs x 1.5 · D delay · M multiplicity (DSR). Verdicts: ROBUST (N, P, T pass), PARTIAL (one fails), "
         "FRAGILE (P fails or two fail), UNTESTABLE (too few episodes), CLOSED (falsified in its own menu).", "", "## Scorecard", "",
         "| strategy | evidence | N neighbours | P placebo | T time | C / D costs, delay | M | verdict |", "|---|---|---|---|---|---|---|---|"]
    if s1:
        L.append(f"| Value strict composite, annual May (live) | 2020-26, 7 rebalances, ~{s1['list_size']:.0f} names | {s1['n_pass']}/6 pass | Sharpe at pct {s1['placebo']['pct']['sharpe']:.0f} of 200 random strict-pool books "
                 f"(median {s1['placebo']['median']['sharpe']:.2f}) | beats strict pool in {s1['t_pass']}/2 halves | x1.5 costs CAGR {s1['cost15']['cagr_pct']:.1f} % (rule {s1['rule']['cagr_pct']:.1f}); delay: none (09-13) | DSR {s1['rule']['dsr']} | **{s1['verdict']}** |")
    if s5:
        L.append(f"| Asymmetric RSI30 entry / MA200-cross exit on the strict list | 2021-26, 4 calendars, monthly | {s5['n_pass']}/4 pass its bar | Sharpe advantage at pct {s5['placebo']['pct']:.0f} of 100 shifted signals | "
                 f"asym > none in {s5['t_pass']}/2 halves | 1 session late -1.3 pt, 5 late -2.7 (09-13) | - | **{s5['verdict']}** |")
    for c in COMPILED:
        L.append(f"| {c['strategy']} | {c['evidence']} | {c['N']} | {c['P']} | {c['T']} | {c['C_D']} | {c['M']} | **{c['verdict']}** |")
    if s7:
        L.append(f"| Combined book value + trend | 2021-26 daily, corr {s7['corr']:+.2f} | {s7['n_pass']}/5 weights pass the money rule | - | 50/50 passes in {s7['t_pass']}/2 halves | inherits sleeves | - | **{s7['verdict']}** |")
    if s8:
        L.append(f"| Allocation: rupiah dual momentum (IHSG / S&P / cash) | 2006-26 monthly | {s8['gem']['n_pass']}/3 lookbacks beat the index | - | gem >= IHSG Sharpe in {s8['gem']['t_pass']}/3 blocks | 0.30 % switch | - | **{s8['gem']['verdict']}** |")
        L.append(f"| Allocation: equal weight IHSG / S&P / gold | 2006-26 monthly | no-gold version {'passes' if s8['ew3']['checks']['N'] else 'fails'} | - | EW3 >= IHSG Sharpe in {s8['ew3']['t_pass']}/3 blocks | - | - | **{s8['ew3']['verdict']}** |")
    L += ["", "CLOSED (falsified in their own menus, no battery needed): " + "; ".join(f"{a} ({b})" for a, b in CLOSED) + ".", ""]
    if s1:
        L += ["## S1. Value strict composite (deployed `live`)", "", f"Rule: {fmt(s1['rule'])}, DSR {s1['rule']['dsr']}. Strict-pool equal weight: {fmt(s1['pool'])}.", "",
              "| neighbour | names | CAGR | Sharpe | mDD | read |", "|---|---|---|---|---|---|"]
        for k, v in s1["neighbours"].items():
            L.append(f"| {k} | {v['names']:.0f} | {v['cagr_pct']:+.1f} % | {v['sharpe']:.2f} | {v['mdd_pct']:.0f} % | {v['read']} |")
        p = s1["placebo"]
        L += ["", f"Placebo: {p['n']} random books of the rule's size from the strict pool at each rebalance — median Sharpe {p['median']['sharpe']:.2f}, CAGR {p['median']['cagr']:+.1f} %, mDD {p['median']['mdd']:.0f} %; "
              f"95th percentile Sharpe {p['p95_sharpe']:.2f}, CAGR {p['p95_cagr']:+.1f} %. The rule sits at percentile {p['pct']['sharpe']:.0f} (Sharpe), {p['pct']['cagr']:.0f} (CAGR); its drawdown is shallower than {100 - p['pct']['mdd']:.0f} % of the random books. "
              f"{'PASS' if p['pass'] else 'FAIL'}.", ""]
        for k, v in s1["blocks"].items():
            L.append(f"- {k}: rule {fmt(v['rule'])}; strict pool {fmt(v['pool'])}.")
        L += [f"- costs x 1.5: {fmt(s1['cost15'])}.", ""]
    if s5:
        L += ["## S5. Asymmetric rule (RSI entry, MA cross exit) on the strict list", "", "| calendar | none | asym_rsi |", "|---|---|---|"]
        for m, v in s5["base"].items():
            L.append(f"| {m} | {fmt(v['none'])} | {fmt(v['asym'])} |")
        b = s5["bar"]
        L += [f"\nIts own bar: Sharpe > none with CAGR >= 90 % in {b['wins']}/4 calendars, worst mDD {b['worst_mdd']:.0f} vs {b['none_worst_mdd']:.0f} -> {'PASS' if b['pass'] else 'fail'}.", "",
              "| neighbour | wins | worst mDD | none worst | avg CAGR | avg Sharpe | read |", "|---|---|---|---|---|---|---|"]
        for k, v in s5["neighbours"].items():
            L.append(f"| {k} | {v['wins']}/4 | {v['worst_mdd']:.0f} % | {v['none_worst_mdd']:.0f} % | {v['avg_cagr']:+.1f} % | {v['avg_sharpe']:.2f} | {'PASS' if v['pass'] else 'fail'} |")
        p = s5["placebo"]
        L += ["", f"Placebo (May calendar): real Sharpe advantage over none {p['real_adv']:+.2f}; {p['n']} shifted signals median {p['median_adv']:+.2f}, 95th {p['p95_adv']:+.2f}; real at percentile {p['pct']:.0f} -> {'PASS' if p['pass'] else 'FAIL'}.", ""]
        for k, v in s5["blocks"].items():
            L.append(f"- {k}: none {fmt(v['none'])}; asym {fmt(v['asym_rsi'])}.")
        L.append("")
    if s7:
        L += ["## S7. Combined book value + trend", "", "| weights value/trend | CAGR | Sharpe | mDD | money rule |", "|---|---|---|---|---|"]
        for k, v in s7["weights"].items():
            L.append(f"| {k} | {v['cagr'] * 100:+.1f} % | {v['sharpe']:.2f} | {v['mdd'] * 100:.0f} % | {'pass' if v['money'] else 'fail'} |")
        for k, v in s7["blocks"].items():
            L.append(f"\n- 50/50 {k}: CAGR {v['cagr'] * 100:+.1f} %, Sharpe {v['sharpe']:.2f}, mDD {v['mdd'] * 100:.0f} %.")
        L.append("")
    if s8:
        L += ["## S8. Allocation layer", "", "| arm | CAGR | Sharpe | mDD | beats index |", "|---|---|---|---|---|"]
        for k, v in s8["res"].items():
            L.append(f"| {k} | {v['cagr'] * 100:+.1f} % | {v['sharpe']:.2f} | {v['mdd'] * 100:.0f} % | {'yes' if v['beats_index'] else '-'} |")
        for k, v in s8["blocks"].items():
            L.append(f"\n- {k}: " + "; ".join(f"{a} CAGR {b['cagr'] * 100:+.1f} % Sharpe {b['sharpe']:.2f} mDD {b['mdd'] * 100:.0f} %" for a, b in v.items()))
        L.append("")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    print("\n".join(L))
    print("wrote", path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--placebo", type=int, default=200)
    ap.add_argument("--asym-placebo", type=int, default=100)
    ap.add_argument("--parts", default="S1,S5,S7,S8")
    ap.add_argument("--no-store", action="store_true")
    args = ap.parse_args()
    parts = [p.strip() for p in args.parts.split(",")]
    dsn = os.environ["INGEST_DB_DSN"]
    out = {}
    rows_cache: dict = {}
    if "S1" in parts or "S5" in parts:
        conn = psycopg.connect(dsn)
        conn.execute("SET max_parallel_workers_per_gather = 0")
        close, vol, delisted, div, ix = VQ.load(conn)
        if "S1" in parts:
            out["S1"] = s1_value(conn, close, vol, delisted, div, rows_cache, args.placebo)
        if "S5" in parts:
            out["S5"] = s5_asym(conn, close, vol, delisted, div, ix, rows_cache, args.asym_placebo)
        conn.close()
    if "S7" in parts:
        P, unis, comp, Hp, Lp, sectors, brent = B.load_all(dsn, os.environ.get("IDX_BEYOND_CACHE"))
        out["S7"] = s7_combo(dsn, P, unis, Hp, Lp)
    if "S8" in parts:
        out["S8"] = s8_alloc(dsn)
    path = os.path.join(HERE, f"IDX_ROBUSTNESS_SCORECARD_{date.today().isoformat()}.md")
    report(out, path)
    if not args.no_store:
        from blackheart_ingest.idx import research_store as rs
        verdicts = {k: (v.get("verdict") if isinstance(v, dict) and "verdict" in v else {kk: vv.get("verdict") for kk, vv in v.items() if isinstance(vv, dict) and "verdict" in vv}) for k, v in out.items()}
        with psycopg.connect(dsn) as conn:
            sid = rs.record_study(conn, "robustness_scorecard", date.today(), params={"parts": parts, "n_trials_cumulative": N_TRIALS, "placebo": args.placebo, "asym_placebo": args.asym_placebo, "seed": SEED},
                                  summary=json.loads(json.dumps({"verdicts": verdicts, **out}, default=str)), names=[], report_path=path, note=json.dumps(verdicts, default=str))
            print(f"study #{sid} stored")


if __name__ == "__main__":
    main()
