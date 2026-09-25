#!/usr/bin/env python3
"""IDX menu 34 - the allocation frontier of the combined book: how much CAGR is left at each drawdown cap
(operator, 2026-09-25: "maximize CAGR, tapi minimize drawdown se minim mungkin" -> "okay kerjakan ... 2").

Every ML study since #155 says the same thing: filters, stops and tuning do not cut the drawdown, allocation does. The
combined Rp 20 M book (#166-168: gap 10 % / trend 5 % / ML 5 % of NAV per trade, 20 slots) was sized by the operator, not
searched. This menu searches the sizing and the portfolio-level risk overlays on the SAME engine, trades and costs as
#168 (`idx_combo_rupiah`: the deployed gap-fade scan, the trend book's own K-10 trades, the ML cost-aware book with the
live +5 %/10-day confirmation; lots of 100, closing offer/bid, Stockbit fees; 2022-01 -> 2026-09-16).

PRE-REGISTERED (10 trials; cumulative 833 + 10 = 843).
  Sizing grid: % of NAV per trade for gap / trend / ML each in {2.5, 5, 7.5, 10} = 64 books (the deployed 10/5/5 is one).
  Frontier: for each drawdown cap in {-10, -15, -20, -25 %} the book with the highest CAGR whose mDD respects the cap,
    (a) in-sample on the whole window, (b) WALK-FORWARD: the sizing is chosen on the years before Y (by-year returns and
    the worst drawdown inside those years) and applied in Y, 2023..2026, stitched - the honest number.        (4 trials)
  Overlays on the deployed sizing (each reads only information known at the previous close):                  (6 trials)
    cash30     cash floor 30 %: no new trade when it would take invested share above 70 %
    vt10/vt15  volatility target: new trades and open positions scaled to target / (20-day realised vol of the book's NAV,
               annualised), capped at 1; open positions are scaled OUT pro-rata at the closing bid, never scaled back in
    gate50     COMPOSITE below its 200-day mean -> exposure 50 % (the deployed trend gate stops entries; this also halves
               what is held)
    brake10    NAV 10 % below its peak -> exposure 50 % until a new high
    gate+brake both
  Everything reported per year; the same overlays are also run on each cap's walk-forward sizing (informative).
READING RULE: an arm IMPROVES the deployed book if its mDD is shallower by >= 5 pp AND its CAGR >= 0.8 x the deployed
CAGR, in the walk-forward as well as in-sample where both exist; a change to the live book's params is the operator's call.
READ-ONLY; one idx.study row. INGEST_DB_DSN (or idx-local.env), IDX_ML_CACHE, IDX_EXIT_CACHE (tmp/exit_cache.pkl).
"""
from __future__ import annotations

import itertools
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
import idx_combo_rupiah as CR  # noqa: E402
import idx_ml_strategy as M  # noqa: E402
from blackheart_ingest.idx import research_store as rs  # noqa: E402
from blackheart_ingest.idx.ml import common  # noqa: E402

N_BEFORE = 833
STUDY = "alloc_frontier"
GRID = [0.025, 0.05, 0.075, 0.10]
CAPS = [-0.10, -0.15, -0.20, -0.25]
DEPLOYED = {"gap": 0.10, "trend": 0.05, "ML": 0.05}
OVERLAYS = ["cash30", "vt10", "vt15", "gate50", "brake10", "gate+brake"]
YEARS_WF = [2023, 2024, 2025, 2026]
BAR = {"mdd_gain_pp": 5.0, "cagr_keep": 0.8}


def dsn() -> str:
    if os.environ.get("INGEST_DB_DSN"):
        return os.environ["INGEST_DB_DSN"]
    env = dict(re.findall(r"^([A-Z_]+)=(.*)$", open(os.path.join(ROOT, "blackheart-ingest", "idx-local.env")).read(), re.M))
    v = env["INGEST_DB_DSN"].strip().strip('"')
    os.environ["INGEST_DB_DSN"] = v
    return v


# ---- engine: idx_combo_rupiah.engine with per-sleeve sizing, a cash floor and a daily exposure multiplier ----------------------
def engine(dates, codes, A, raw, offer, bid, ml, tr, gap, pct: dict[str, float], *, cash_floor: float = 0.0, overlay: str | None = None,
           comp_below: np.ndarray | None = None):
    idx = {c: i for i, c in enumerate(codes)}
    T = len(dates)
    t0 = int(np.searchsorted(dates, np.datetime64(CR.START)))
    entries: dict[int, list] = {}
    exits: dict[int, list] = {}
    for x in ml + tr:
        entries.setdefault(x["t_in"], []).append(x)
        exits.setdefault(x["t_out"], []).append(x)
    gaps: dict[int, list] = {}
    for x in gap:
        gaps.setdefault(x["t"], []).append(x)
    cash = CR.CAPITAL
    held: dict[tuple[str, str], dict] = {}
    nav = np.full(T, np.nan)
    peak = CR.CAPITAL
    expo_hist = []
    tick = common.tick
    for t in range(t0, T):
        nav_prev = nav[t - 1] if t > t0 else CR.CAPITAL
        # exposure for today from yesterday's information
        expo = 1.0
        if overlay in ("vt10", "vt15"):
            target = 0.10 if overlay == "vt10" else 0.15
            hist = nav[max(t0, t - 21):t]
            if len(hist) >= 15:
                r = np.diff(hist) / hist[:-1]
                vol = float(np.std(r) * np.sqrt(252))
                expo = min(1.0, target / vol) if vol > 0 else 1.0
        if overlay in ("gate50", "gate+brake") and comp_below is not None and t > t0 and comp_below[t - 1]:
            expo = min(expo, 0.5)
        if overlay in ("brake10", "gate+brake") and nav_prev < 0.9 * peak:
            expo = min(expo, 0.5)
        expo_hist.append(expo)
        # scale out open positions when the exposure fell below what they carry
        for key, p in list(held.items()):
            if key[0] == "gap":
                continue
            if expo < p["scale"] - 0.10:
                j = idx[key[1]]
                if np.isnan(A[t, j]) or raw[t, j] <= 0:
                    continue
                frac = 1 - expo / p["scale"]
                px = bid[t, j] if bid[t, j] > 0 and bid[t, j] <= raw[t, j] else raw[t, j] - tick(raw[t, j])
                value = p["units"] * (A[t, j] / p["a_in"]) * (px / raw[t, j]) * frac
                cash += value * (1 - CR.FEE_SELL)
                p["units"] *= (1 - frac)
                p["cost"] *= (1 - frac)
                p["scale"] = expo
        # morning: gap-fade, settled at the close
        day_gap = 0.0
        for x in gaps.get(t, []):
            if len(held) >= CR.MAX_POS:
                break
            px = (x["open"] + tick(x["open"])) * (1 + CR.FEE_BUY)
            lots = int((pct["gap"] * expo * nav_prev) // (px * CR.LOT))
            cost = lots * CR.LOT * px
            if lots < 1 or cost > cash:
                continue
            mv_now = sum(p["units"] * (A[t, idx[k[1]]] / p["a_in"]) for k, p in held.items() if k[0] != "gap" and not np.isnan(A[t, idx[k[1]]]))
            if cash_floor > 0 and (mv_now + cost) / nav_prev > 1 - cash_floor:
                continue
            cash -= cost
            held[("gap", x["code"])] = {"cost": cost}
            proceeds = cost * (1 + x["net"])
            day_gap += proceeds
        for key in [k for k in held if k[0] == "gap"]:
            held.pop(key)
        cash += day_gap
        for x in exits.get(t, []):
            key = (x["strat"], x["code"])
            if key not in held:
                continue
            p = held.pop(key)
            j = idx[x["code"]]
            px = bid[t, j] if bid[t, j] > 0 and bid[t, j] <= raw[t, j] else raw[t, j] - tick(raw[t, j])
            value = p["units"] * (A[t, j] / p["a_in"]) * (px / raw[t, j]) if not np.isnan(A[t, j]) else p["units"]
            cash += value * (1 - CR.FEE_SELL)
        mv = sum(p["units"] * (A[t, idx[k[1]]] / p["a_in"]) for k, p in held.items() if k[0] != "gap" and not np.isnan(A[t, idx[k[1]]]))
        nav_now = cash + mv
        for x in sorted(entries.get(t, []), key=lambda z: 0 if z["strat"] == "trend" else 1):
            key = (x["strat"], x["code"])
            j = idx[x["code"]]
            if key in held or len(held) >= CR.MAX_POS or np.isnan(A[t, j]) or raw[t, j] <= 0:
                continue
            px = offer[t, j] if offer[t, j] > 0 and offer[t, j] >= raw[t, j] else raw[t, j] + tick(raw[t, j])
            lots = int((pct[x["strat"]] * expo * nav_now) // (px * CR.LOT))
            cost = lots * CR.LOT * px * (1 + CR.FEE_BUY)
            if lots < 1 or cost > cash:
                continue
            if cash_floor > 0 and (mv + cost) / nav_now > 1 - cash_floor:
                continue
            cash -= cost
            mv += cost / (1 + CR.FEE_BUY)
            held[key] = {"t": t, "a_in": A[t, j], "units": lots * CR.LOT * raw[t, j], "cost": cost, "scale": expo}
        mv = sum(p["units"] * (A[t, idx[k[1]]] / p["a_in"]) for k, p in held.items() if not np.isnan(A[t, idx[k[1]]]))
        nav[t] = cash + mv
        peak = max(peak, nav[t])
    navs = pd.Series(nav[t0:], index=dates[t0:])
    return navs, float(np.mean(expo_hist))


def year_stats(nav: pd.Series) -> dict[int, dict[str, float]]:
    """Per calendar year: return and the worst drawdown INSIDE the year (peak reset at the year's start)."""
    out = {}
    for y, s in nav.groupby(nav.index.year):
        eq = s / s.iloc[0]
        out[int(y)] = {"ret": float(eq.iloc[-1] - 1), "mdd": float((eq / eq.cummax() - 1).min())}
    return out


def key(p: dict[str, float]) -> str:
    return f"{p['gap'] * 100:g}/{p['trend'] * 100:g}/{p['ML'] * 100:g}"


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
    comp_below = (g("comp_dma200").max(axis=1).ffill().to_numpy(float) < 0)
    ml = CR.ml_trades(P, dates, codes, A, raw, offer, bid, liq)
    tr = CR.trend_trades(d, dates)
    gap = CR.gap_events(d, dates)
    M.log(f"events: ML {len(ml)} trades, trend {len(tr)} trades, gap-fade {len(gap)} day-events; COMPOSITE below MA200 on {int(comp_below.sum())} days")

    # ---- sizing grid ----
    books: dict[str, dict] = {}
    for gp, tp, mp in itertools.product(GRID, GRID, GRID):
        pct = {"gap": gp, "trend": tp, "ML": mp}
        nav, _ = engine(dates, codes, A, raw, offer, bid, ml, tr, gap, pct)
        st = CR.stats(nav)
        books[key(pct)] = {**st, "pct": pct, "years": year_stats(nav), "nav": nav}
    dep = books[key(DEPLOYED)]
    M.log(f"deployed {key(DEPLOYED)}: CAGR {dep['cagr'] * 100:.1f} % Sharpe {dep['sharpe']:.2f} mDD {dep['mdd'] * 100:.0f} %")

    # ---- frontier: in-sample and walk-forward ----
    frontier: dict[str, dict] = {}
    for cap in CAPS:
        ok = [k for k, b in books.items() if b["mdd"] >= cap]
        ins = max(ok, key=lambda k: books[k]["cagr"]) if ok else None
        # walk-forward: pick on the years before Y by (a) worst in-year drawdown within cap, (b) highest mean yearly return
        picks, wf_nav = {}, []
        for Y in YEARS_WF:
            def score(k):
                ys = {y: v for y, v in books[k]["years"].items() if y < Y}
                worst = min(v["mdd"] for v in ys.values())
                mean_ret = float(np.mean([v["ret"] for v in ys.values()]))
                return (worst >= cap, mean_ret)
            cands = [k for k in books if score(k)[0]]
            pick = max(cands, key=lambda k: score(k)[1]) if cands else min(books, key=lambda k: -min(v["mdd"] for y, v in books[k]["years"].items() if y < Y))
            picks[Y] = pick
            nav_y = books[pick]["nav"]
            wf_nav.append(nav_y[nav_y.index.year == Y] / nav_y[nav_y.index.year == Y].iloc[0])
        chain = []
        level = 1.0
        for s in wf_nav:
            chain.append(s * level)
            level = float(chain[-1].iloc[-1])
        wf = pd.concat(chain) * CR.CAPITAL
        wf_st = CR.stats(wf)
        frontier[f"cap{int(cap * 100)}"] = {"cap": cap, "in_sample": ins, "in_sample_stats": {k: v for k, v in books[ins].items() if k not in ("nav", "years")} if ins else None,
                                            "wf_picks": picks, "wf": wf_st, "wf_nav": wf}
        M.log(f"cap {cap * 100:.0f} %: in-sample {ins} ({books[ins]['cagr'] * 100:.1f} %/{books[ins]['sharpe']:.2f}/{books[ins]['mdd'] * 100:.0f} %); "
              f"walk-forward picks {picks} -> {wf_st['cagr'] * 100:.1f} %/{wf_st['sharpe']:.2f}/{wf_st['mdd'] * 100:.0f} %" if ins else f"cap {cap * 100:.0f} %: no book in-sample")

    # ---- overlays on the deployed sizing, and on each cap's walk-forward pick of the last year (informative) ----
    overlays: dict[str, dict] = {}
    for ov in OVERLAYS:
        nav, expo = engine(dates, codes, A, raw, offer, bid, ml, tr, gap, DEPLOYED, cash_floor=0.30 if ov == "cash30" else 0.0,
                           overlay=None if ov == "cash30" else ov, comp_below=comp_below)
        st = CR.stats(nav)
        overlays[ov] = {**st, "expo_mean": expo, "years": year_stats(nav)}
        M.log(f"overlay {ov:<10} CAGR {st['cagr'] * 100:6.1f} % Sharpe {st['sharpe']:5.2f} mDD {st['mdd'] * 100:6.1f} % expo {expo * 100:.0f} % "
              + " ".join(f"{str(y)[2:]}:{v * 100:+.0f}" for y, v in st["by_year"].items()))
    for ov in OVERLAYS:
        r = overlays[ov]
        r["improves"] = bool((r["mdd"] - dep["mdd"]) * 100 >= BAR["mdd_gain_pp"] and r["cagr"] >= BAR["cagr_keep"] * dep["cagr"])
    for cap, f in frontier.items():
        f["improves_wf"] = bool((f["wf"]["mdd"] - dep["mdd"]) * 100 >= BAR["mdd_gain_pp"] and f["wf"]["cagr"] >= BAR["cagr_keep"] * dep["cagr"])

    n_trials = N_BEFORE + len(CAPS) + len(OVERLAYS)
    yrs = sorted(dep["by_year"])
    L = [f"# IDX menu 34 - the allocation frontier of the combined Rp 20 M book - {date.today()} - 10 trials, cumulative N = {n_trials}", "",
         f"Engine, trades and costs of #168 (gap-fade scan, trend K-10 trades, ML cost-aware + live +5 %/10 d confirmation), 2022-01 -> {CR.END.date()}. "
         f"Deployed sizing {key(DEPLOYED)} (% of NAV per trade, gap/trend/ML): CAGR {dep['cagr'] * 100:.1f} %, Sharpe {dep['sharpe']:.2f}, mDD {dep['mdd'] * 100:.0f} %, "
         + " ".join(f"{y}: {dep['by_year'][y] * 100:+.0f} %" for y in yrs) + ".", "",
         "## Sizing grid: the frontier", "", "| cap | in-sample best sizing | CAGR | Sharpe | mDD | walk-forward picks (chosen on prior years) | WF CAGR | WF Sharpe | WF mDD | WF by year | improves deployed (WF) |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for cap, f in frontier.items():
        s = f["in_sample_stats"] or {"cagr": float("nan"), "sharpe": float("nan"), "mdd": float("nan")}
        w = f["wf"]
        L.append(f"| {f['cap'] * 100:.0f} % | {f['in_sample'] or 'none (no sizing holds the cap)'} | {s['cagr'] * 100:.1f} % | {s['sharpe']:.2f} | {s['mdd'] * 100:.0f} % | "
                 + ", ".join(f"{y}: {p}" for y, p in f["wf_picks"].items()) + f" | {w['cagr'] * 100:.1f} % | {w['sharpe']:.2f} | {w['mdd'] * 100:.0f} % | "
                 + " ".join(f"{str(y)[2:]}:{v * 100:+.0f}" for y, v in w["by_year"].items()) + f" | {'YES' if f['improves_wf'] else 'no'} |")
    top = sorted(books.values(), key=lambda b: -b["cagr"])[:8]
    L += ["", "Top sizings by CAGR (in-sample, for scale):", "", "| sizing gap/trend/ML | CAGR | Sharpe | mDD | invested-year worst |", "|---|---|---|---|---|"]
    for b in top:
        L.append(f"| {key(b['pct'])} | {b['cagr'] * 100:.1f} % | {b['sharpe']:.2f} | {b['mdd'] * 100:.0f} % | {min(v['mdd'] for v in b['years'].values()) * 100:.0f} % |")
    L += ["", "## Overlays on the deployed sizing", "", "| overlay | CAGR | Sharpe | mDD | mean exposure | " + " | ".join(str(y) for y in yrs) + " | improves deployed |",
          "|---|---|---|---|---|" + "---|" * len(yrs) + "---|"]
    L.append(f"| none (deployed) | {dep['cagr'] * 100:.1f} % | {dep['sharpe']:.2f} | {dep['mdd'] * 100:.0f} % | 100 % | " + " | ".join(f"{dep['by_year'][y] * 100:+.0f} %" for y in yrs) + " | reference |")
    for ov, r in overlays.items():
        L.append(f"| {ov} | {r['cagr'] * 100:.1f} % | {r['sharpe']:.2f} | {r['mdd'] * 100:.0f} % | {r['expo_mean'] * 100:.0f} % | " + " | ".join(f"{r['by_year'][y] * 100:+.0f} %" for y in yrs)
                 + f" | {'YES' if r['improves'] else 'no'} |")
    imp_ov = [ov for ov in OVERLAYS if overlays[ov]["improves"]]
    imp_fr = [c for c, f in frontier.items() if f["improves_wf"]]
    L += ["", "## Verdict (menu 34, study stored)", "",
          f"Overlays that improve the deployed book (mDD shallower by >= 5 pp, CAGR >= 80 %): {', '.join(imp_ov) or 'none'}. "
          f"Frontier caps whose walk-forward sizing improves it: {', '.join(imp_fr) or 'none'}. Changing the live book's sizing or adding an overlay is the operator's call."]
    text = "\n".join(L)
    out = os.path.join(HERE, f"IDX_ALLOC_FRONTIER_{date.today()}.md")
    open(out, "w", encoding="utf-8").write(text + "\n")
    slim_books = {k: {kk: vv for kk, vv in b.items() if kk != "nav"} for k, b in books.items()}
    slim_front = {k: {kk: vv for kk, vv in f.items() if kk != "wf_nav"} for k, f in frontier.items()}
    json.dump({"deployed": {k: v for k, v in dep.items() if k != "nav"}, "books": slim_books, "frontier": slim_front, "overlays": overlays},
              open(out.replace(".md", ".json"), "w"), indent=1, default=str)
    print(text)
    with psycopg.connect(d) as conn:
        sid = rs.record_study(conn, STUDY, date.today(), params={"trials": OVERLAYS + [f"cap{int(c * 100)}" for c in CAPS], "n_trials_cumulative": n_trials, "grid": GRID,
                                                                 "caps": CAPS, "deployed": DEPLOYED, "bar": BAR},
                              summary={"deployed": {k: v for k, v in dep.items() if k not in ("nav", "years")}, "frontier": common.plain(slim_front),
                                       "overlays": common.plain(overlays), "improving_overlays": imp_ov, "improving_caps": imp_fr},
                              names=[], report_path=out, note="menu 34: sizing frontier + portfolio overlays on the combined book engine")
        conn.commit()
    M.log(f"study #{sid} stored; report {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
