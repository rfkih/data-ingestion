#!/usr/bin/env python3
"""IDX phase 2 — value + quality, one-year holds, point-in-time. Revision 3 (2026-09-12).

What changed from rev. 2 (see research/IDX_REVIEW_2026-09-12.md):
  * point-in-time universe: every name on Utama/Pengembangan ON THE REBALANCE DAY (board from the IDX notation string in
    the day-dump), traded that day, 60d median value >= Rp 5 bn — names later moved to Pemantauan Khusus or delisted are
    judged as they were, not excluded by where they are today (their reports were downloaded for this revision);
  * selection = blackheart_ingest.idx.candidates.build()/rank_pool() — the production rule (average ranks, data-error guard,
    16:00 WIB information cutoff, pool >= 20 else cash). There is no second implementation of the rule any more;
  * a real portfolio path: units bought at the close, buy-and-hold to the next rebalance, dividends net of the 10 % final tax
    to cash on the ex-date, 25 bps per side + half the tick as spread, a name with no trade on the rebalance day cannot be
    sold (carried), a delisted name is worth zero after its last bar;
  * benchmarks: COMPOSITE, LQ45, IDX Value 30, IDX High Dividend 20 (price indices); the bench portfolio is the same
    simulation over every eligible liquid name;
  * one pre-registered variant, composite_qloose_seccap: the same rule with at most one third of the selection per IDX-IC
    sector (rank walk, skipping full sectors). Declared in the review before this revision was run; one trial in the DSR count;
  * --months runs the identical rule on other rebalance months (calendar sensitivity); month 5 is the reported one.

Portfolios (all long-only, equal weight at each rebalance, held to the next):
  bench                    every eligible liquid name
  quality                  strict gate: ROE >= 10 %, profit this and prior year, CFO > 0, D/E <= 1.5 (financials exempt)
  value_naive              cheapest fifth by E/P among all eligible names            <- the value-trap control
  value_q / composite_q    E/P / composite rank(E/P, B/P, DY) within the strict gate
  value_qloose / composite_qloose   the same within the loose gate (profit > 0, ROE >= 5 %)   <- composite_qloose = the rule
  composite_qloose_seccap  the rule with the sector cap (pre-registered)
  composite_qf             composite_q minus the bottom quintile of 20-day foreign flow
  ep_q1..ep_q5             E/P quintiles within the strict gate (monotonicity check)

READ-ONLY on the DB. INGEST_DB_DSN=... blackheart-ingest/.venv/Scripts/python research/idx_value_quality.py [--months 5,2,8,11]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import UTC, date, datetime

import numpy as np
import pandas as pd
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blackheart-ingest", "src"))
import equity_screen as ES  # noqa: E402

from blackheart_ingest.idx import candidates as cand  # noqa: E402

OUTDIR = os.path.join(ROOT, "research-scratch", "idx-screen")
COST_SIDE = 25.0 / 10000
DIV_TAX = 0.10
REBAL_DAY = 2
FIRST_YEAR = 2021
TICKS = ((200, 1), (500, 2), (2000, 5), (5000, 10), (10**12, 25))
INDICES = ("COMPOSITE", "LQ45", "IDXV30", "IDXHIDIV20")
VARIANTS = {                                  # name -> rank_pool arguments; each one is a trial in the DSR count
    "value_naive": dict(gate=None, keys=("ep",)),
    "value_q": dict(gate="strict", keys=("ep",)),
    "composite_q": dict(gate="strict", keys=cand.KEYS),
    "value_qloose": dict(gate="loose", keys=("ep",)),
    "composite_qloose": dict(gate="loose", keys=cand.KEYS),
    "composite_qloose_seccap": dict(gate="loose", keys=cand.KEYS, sector_cap=1 / 3),
}
NAMES = ["bench", "quality", *VARIANTS, "composite_qf", *[f"ep_q{q}" for q in range(1, 6)]]


def connect():
    dsn = os.environ.get("INGEST_DB_DSN")
    if not dsn:
        sys.exit("set INGEST_DB_DSN")
    conn = psycopg.connect(dsn)
    conn.execute("SET max_parallel_workers_per_gather = 0")
    return conn


def frame(conn, sql, params, cols):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return pd.DataFrame(cur.fetchall(), columns=cols)


def load(conn):
    bars = frame(conn, "SELECT trade_date, code, close * adj_factor, volume FROM idx.bar WHERE source = 'idx' AND trade_date >= '2020-01-01'",
                 (), ["d", "code", "close", "vol"])
    bars["d"] = pd.to_datetime(bars["d"])
    bars["close"] = pd.to_numeric(bars["close"], errors="coerce")
    bars["vol"] = pd.to_numeric(bars["vol"], errors="coerce")
    close = bars.pivot(index="d", columns="code", values="close").astype(float)
    vol = bars.pivot(index="d", columns="code", values="vol").astype(float)
    last = close.apply(lambda s: s.last_valid_index())
    delisted = {c: d for c, d in last.items() if d is not None and d < close.index[-1] - pd.Timedelta(days=30)}
    div = frame(conn, "SELECT code, ex_date, amount_per_share FROM idx.dividend WHERE amount_per_share > 0", (), ["code", "ex", "dps"])
    div["ex"] = pd.to_datetime(div["ex"])
    div["dps"] = pd.to_numeric(div["dps"], errors="coerce")
    ix = frame(conn, "SELECT trade_date, index_code, close FROM idx.index_daily WHERE index_code = ANY(%s)", (list(INDICES),), ["d", "ix", "close"])
    ix["d"] = pd.to_datetime(ix["d"])
    ix["close"] = pd.to_numeric(ix["close"], errors="coerce")
    ix = ix.pivot(index="d", columns="ix", values="close").astype(float)
    return close, vol, delisted, div, ix


def rebalance_dates(index: pd.DatetimeIndex, month: int, day: int = REBAL_DAY) -> list[pd.Timestamp]:
    out = []
    for y in range(FIRST_YEAR, index[-1].year + 1):
        pos = index.searchsorted(pd.Timestamp(date(y, month, day)))
        if pos < len(index):
            out.append(index[pos])
    return out


def select(conn, D: pd.Timestamp) -> tuple[dict[str, set[str]], dict]:
    """Every portfolio's membership at D, all through the production rule."""
    res = cand.build(conn, D.date())
    rows = res["all_rows"]
    sel: dict[str, set[str]] = {"bench": {r["code"] for r in rows if r["tradable"]},
                                "quality": {r["code"] for r in rows if r["tradable"] and r["gate_strict"]}}
    for name, kw in VARIANTS.items():
        pool = cand.rank_pool([dict(r) for r in rows], **kw)
        sel[name] = {r["code"] for r in pool if r["selected"]}
    strict = cand.rank_pool([dict(r) for r in rows], gate="strict", keys=("ep",), min_names=0, min_pool=0)
    f20 = sorted(float(r["f20"]) for r in strict if r["f20"] is not None)
    cut = f20[max(0, len(f20) // 5 - 1)] if len(f20) >= 10 else None
    veto = {r["code"] for r in strict if cut is not None and r["f20"] is not None and float(r["f20"]) <= cut}
    sel["composite_qf"] = sel["composite_q"] - veto
    n = len(strict)
    for q in range(1, 6):
        sel[f"ep_q{q}"] = {r["code"] for i, r in enumerate(strict) if n >= 10 and math.ceil((i + 1) * 5 / n) == q}
    guarded = sorted(r["code"] for r in rows if "data_error_ratio" in r["warnings"])
    log = {"date": str(D.date()), "liquid": res["liquid"], "with_fund": res["with_fundamentals"], "pool_loose": res["pool"],
           "pool_strict": n, "data_error": guarded, **{k: len(v) for k, v in sel.items() if k != "bench"}}
    return sel, log


def cost_side(p: float, spread: bool) -> float:
    return COST_SIDE + (0.5 * next(t for lim, t in TICKS if p < lim) / p if spread else 0.0)


def simulate(sel_by_date: dict[pd.Timestamp, set[str]], close: pd.DataFrame, vol: pd.DataFrame, delisted: dict, div: pd.DataFrame,
             start: pd.Timestamp, end: pd.Timestamp, spread: bool = True) -> pd.Series:
    """NAV of one portfolio: buy at the rebalance close, hold, dividends (net) to cash, real costs, stuck and delisted names."""
    days = close.index[(close.index >= start) & (close.index <= end)]
    div_days: dict[pd.Timestamp, list[tuple[str, float]]] = {}
    for code, ex, dps in div.itertuples(index=False):
        if code not in close.columns or not dps > 0:
            continue
        pos = close.index.searchsorted(ex)
        if pos < len(close.index):
            div_days.setdefault(close.index[pos], []).append((code, float(dps)))
    units: dict[str, float] = {}
    last_px: dict[str, float] = {}
    cash = 1.0
    nav = []
    for d in days:
        row = close.loc[d]

        def px(c, row=row, d=d):
            v = row.get(c, np.nan)
            if not np.isnan(v):
                last_px[c] = v
                return v
            if c in delisted and d > delisted[c]:
                return 0.0
            return last_px.get(c, np.nan)

        for c, dps in div_days.get(d, ()):
            if c in units:
                cash += units[c] * dps * (1 - DIV_TAX)
        if d in sel_by_date:
            vrow = vol.loc[d]
            target = {c for c in sel_by_date[d] if c in row.index and not np.isnan(row[c]) and row[c] > 0 and vrow.get(c, 0) > 0}
            for c in list(units):
                if c in target:
                    continue
                p = px(c)
                if not np.isnan(p) and p > 0 and vrow.get(c, 0) > 0:      # sellable at today's close
                    cash += units[c] * p * (1 - cost_side(p, spread))
                    del units[c]
                elif p == 0.0:                                          # delisted: gone
                    del units[c]
                # else: no trade today (suspended) -> carried, outside the new equal weights
            investable = cash + sum(units[c] * row[c] for c in units if c in target)
            if target:
                w = investable / len(target)
                for c in target:
                    p = row[c]
                    tgt = w / p
                    delta = tgt - units.get(c, 0.0)
                    cash -= delta * p + abs(delta) * p * cost_side(p, spread)
                    units[c] = tgt
        nav.append(cash + sum(u * (0.0 if np.isnan(px(c)) else px(c)) for c, u in units.items()))
    return pd.Series(nav, index=days)


def stats(nav: pd.Series, rebals: list[pd.Timestamp]) -> dict:
    r = np.log(nav / nav.shift(1)).fillna(0.0)
    nz = r[r != 0.0]
    if len(nz):
        r = r[r.index >= nz.index[0]]                                    # from the first invested day
    yrs = max((r.index[-1] - r.index[0]).days / 365.25, 0.25)
    yearly = r.groupby(r.index.year).sum().apply(lambda x: round(100 * (math.exp(x) - 1), 1)).to_dict()
    periods = {str(a.date()): round(100 * (nav.loc[b] / nav.loc[a] - 1), 1) for a, b in zip(rebals, [*rebals[1:], nav.index[-1]], strict=True)}
    return {"total_pct": round(100 * (nav.iloc[-1] / nav.iloc[0] - 1), 1), "cagr_pct": round(100 * (math.exp(r.sum() / yrs) - 1), 1),
            "sharpe": round(ES.sharpe(list(r), 252), 3), "mdd_pct": round(ES.maxdd(list(r)), 1), "yearly": yearly,
            "periods": periods, "from": str(r.index[0].date()), "_r": r}


def contributions(names: set[str], close: pd.DataFrame, div: pd.DataFrame, D: pd.Timestamp, end: pd.Timestamp) -> list[tuple[str, float]]:
    """Each name's share of the period's equal-weight arithmetic return, in % of NAV (price + gross dividends), best first —
    the concentration ledger: how much of a year a handful of names carried."""
    out = []
    n = len(names)
    for c in names:
        if c not in close.columns:
            continue
        s = close[c].loc[D:end].dropna()
        p0 = close.at[D, c] if D in close.index else np.nan
        if s.empty or np.isnan(p0) or p0 <= 0:
            continue
        dv = div[(div["code"] == c) & (div["ex"] > D) & (div["ex"] <= end)]["dps"].sum()
        out.append((c, round(100 * (s.iloc[-1] / p0 - 1 + dv / p0) / n, 1)))
    return sorted(out, key=lambda x: -x[1])


def run_month(conn, month: int, close, vol, delisted, div, spread: bool) -> dict:
    rebals = rebalance_dates(close.index, month)
    sels, logs = {}, []
    for D in rebals:
        s, log = select(conn, D)
        sels[D] = s
        logs.append(log)
    end = close.index[-1]
    ends = [*rebals[1:], end]
    out = {}
    for n in NAMES:
        nav = simulate({D: sels[D][n] for D in rebals}, close, vol, delisted, div, rebals[0], end, spread)
        out[n] = stats(nav, rebals)
        out[n]["holdings"] = []
        for D, e in zip(rebals, ends, strict=True):
            h = {"date": str(D.date()), "n": len(sels[D][n]), "names": sorted(sels[D][n]) if n != "bench" else []}
            if n != "bench" and sels[D][n]:
                contrib = contributions(sels[D][n], close, div, D, e)
                h["top"], h["bottom"] = contrib[:3], contrib[-3:]
                h["top3_pct_of_nav"] = round(sum(x[1] for x in contrib[:3]), 1)
            out[n]["holdings"].append(h)
    n_var = len(NAMES) - 1                                               # every ranked portfolio but the bench
    for n in NAMES:
        s = list(out[n]["_r"])
        out[n]["dsr"] = round(ES.deflated_sharpe(s, n_var), 3)
        out[n]["psr"] = round(ES.deflated_sharpe(s, 1), 3)
        del out[n]["_r"]
    return {"rebalances": [str(r.date()) for r in rebals], "n_trials": n_var, "summary": out, "log": logs}


def index_stats(ix: pd.DataFrame, rebals: list[str], end: pd.Timestamp) -> dict:
    out = {}
    start = pd.Timestamp(rebals[0])
    for name in ix.columns:
        s = ix[name].dropna()
        s = s[(s.index >= start) & (s.index <= end)]
        if len(s) < 2:
            continue
        r = np.log(s / s.shift(1)).fillna(0.0)
        yrs = (s.index[-1] - s.index[0]).days / 365.25
        out[name] = {"total_pct": round(100 * (s.iloc[-1] / s.iloc[0] - 1), 1), "cagr_pct": round(100 * ((s.iloc[-1] / s.iloc[0]) ** (1 / yrs) - 1), 1),
                     "sharpe": round(ES.sharpe(list(r), 252), 3), "mdd_pct": round(ES.maxdd(list(r)), 1),
                     "yearly": r.groupby(r.index.year).sum().apply(lambda x: round(100 * (math.exp(x) - 1), 1)).to_dict()}
    return out


def _line(name, v):
    years = " ".join(f"{y}:{r:+.0f}" for y, r in v["yearly"].items())
    return (f"{name:<24} {v['total_pct']:7.1f} {v['cagr_pct']:7.1f} {v['sharpe']:7.3f} {v['mdd_pct']:7.1f}  "
            f"{v.get('dsr', 0):5.2f} {v.get('psr', 0):5.2f} | {years}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", default="5,2,8,11", help="rebalance months; the first is the reported one")
    ap.add_argument("--no-spread", action="store_true", help="commission only (25 bps/side), no half-tick spread")
    ap.add_argument("--out", default=os.path.join(OUTDIR, "value_quality_results.json"))
    a = ap.parse_args()
    months = [int(m) for m in a.months.split(",")]
    conn = connect()
    close, vol, delisted, div, ix = load(conn)
    print(f"loaded: {close.shape[1]} codes, {len(close)} days ({close.index[0].date()}..{close.index[-1].date()}), "
          f"{len(delisted)} delisted-in-sample, {len(div)} dividend events")
    results = {"generated": datetime.now(UTC).isoformat(), "params": {"cost_side_bps": 25, "spread": not a.no_spread, "div_tax": DIV_TAX,
               "rebal_day": REBAL_DAY, "months": months, "variants": {k: {kk: (str(vv) if kk == "keys" else vv) for kk, vv in v.items()} for k, v in VARIANTS.items()}},
               "months": {}}
    for m in months:
        res = run_month(conn, m, close, vol, delisted, div, not a.no_spread)
        results["months"][str(m)] = res
        print(f"\n=== rebalance month {m}: {res['rebalances']}   (DSR at N = {res['n_trials']})")
        for x in res["log"]:
            print("  ", {k: v for k, v in x.items() if k not in ("data_error",)}, "data_error:", x["data_error"])
        print(f"\n{'portfolio':<24} {'total%':>7} {'CAGR%':>7} {'Sharpe':>7} {'mDD%':>7}  {'DSR':>5} {'PSR':>5} | calendar years %")
        for n in NAMES:
            print(_line(n, res["summary"][n]))
        print("  rebalance-period returns %:")
        for n in ("bench", "composite_qloose", "composite_qloose_seccap", "value_qloose", "composite_q"):
            print(f"   {n:<24} " + " ".join(f"{d[:4]}:{r:+.0f}" for d, r in res["summary"][n]["periods"].items()))
        print("  composite_qloose: period return | top-3 names' share of NAV (name: % of NAV) | worst")
        for h, (d, r) in zip(res["summary"]["composite_qloose"]["holdings"], res["summary"]["composite_qloose"]["periods"].items(), strict=True):
            top = ", ".join(f"{c} {v:+.1f}" for c, v in h.get("top", []))
            bot = ", ".join(f"{c} {v:+.1f}" for c, v in h.get("bottom", []))
            print(f"   {d}: {r:+.0f}% | top3 {h.get('top3_pct_of_nav', 0):+.1f} ({top}) | {bot}")
        sys.stdout.flush()
    first = results["months"][str(months[0])]
    results["benchmarks"] = index_stats(ix, first["rebalances"], close.index[-1])
    print(f"\nbenchmark indices (price), {first['rebalances'][0]} -> {close.index[-1].date()}:")
    for n, v in results["benchmarks"].items():
        print(_line(n, v))
    if len(months) > 1:
        print("\ncalendar sensitivity (composite_qloose | seccap | value_qloose | composite_q | bench): total% / CAGR% / Sharpe / mDD%")
        for m in months:
            s = results["months"][str(m)]["summary"]
            cells = [f"{n} {s[n]['total_pct']:+.0f}/{s[n]['cagr_pct']:+.1f}/{s[n]['sharpe']:.2f}/{s[n]['mdd_pct']:.0f}"
                     for n in ("composite_qloose", "composite_qloose_seccap", "value_qloose", "composite_q", "bench")]
            print(f"  month {m:2d}: " + " | ".join(cells))
    with open(a.out, "w") as f:
        json.dump(results, f, indent=1, default=str)
    print("\nresults ->", a.out)


if __name__ == "__main__":
    main()
