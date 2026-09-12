#!/usr/bin/env python3
"""IDX phase-1b overlays — are foreign flow and disclosures worth anything, and do they help the trend sleeve?

Window: 2020-01-02+ (IDX primary; flow exists) — events only from 2023-07 (archive start).
Universe: research-scratch/idx-screen/universe.json (451 ever-liquid names), liquidity gate on entries.
Cost 50 bps round trip everywhere. All tests count their variants for DSR (honest N).

A. Flow filter on the Donchian sleeve (next-open fills): entry allowed only when foreign_net_share_20d
   satisfies a condition. Pooled equal-weight daily return across names in position, best cell chosen per
   variant -> compare pooled Sharpe / DSR(N = variants x cells).
B. Standalone flow signal: weekly quintile sorts on foreign_net_share_20d (and 5d) — Q5-Q1 spread net of
   cost, t-stat, yearly breakdown; plus a long-only "flow momentum" rule (20d > 0 & 5d > 0).
C. Event studies: abnormal return (vs equal-weight universe) at +1/+5/+10/+20 trading days after the
   effective day; pre-event 5d for exchange_query (UMA reply) to test mean reversion.
D. BRPT 20/10 L with each flow filter (thin: few trades since 2020) — reported, not relied upon.

READ-ONLY. Run: INGEST_DB_DSN=... blackheart-ingest/.venv/Scripts/python research/idx_overlays.py
"""
from __future__ import annotations

import json
import math
import os
import statistics
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import psycopg

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import equity_screen as ES  # noqa: E402
import idx_screen as IS  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTDIR = os.path.join(ROOT, "research-scratch", "idx-screen")
COST = 25.0                      # bps per side
GRID = ES.GRID
FLOW_FILTERS = {                  # name -> predicate on (f20, f5)
    "none": lambda f20, f5: True,
    "f20>0": lambda f20, f5: f20 is not None and f20 > 0,
    "f20>+5%": lambda f20, f5: f20 is not None and f20 > 0.05,
    "f20<0": lambda f20, f5: f20 is not None and f20 < 0,
    "f20<-5%": lambda f20, f5: f20 is not None and f20 < -0.05,
    "f5>0&f20>0": lambda f20, f5: f20 is not None and f5 is not None and f20 > 0 and f5 > 0,
}
EVENT_KINDS = ["exchange_query", "ownership_change", "dividend", "buyback", "material_info", "rights", "control_change"]


def load(conn, codes):
    """Wide frames indexed by date: close (adjusted), open (adjusted, NaN if missing), high, low, value,
    f20, f5, liq (trailing 60d median value >= 5bn)."""
    with conn.cursor() as cur:
        cur.execute("SET max_parallel_workers_per_gather = 0")   # docker /dev/shm is small; avoid parallel DSM spill
        cur.execute(
            """
            SELECT b.trade_date, b.code, b.open * b.adj_factor, b.high * b.adj_factor, b.low * b.adj_factor,
                   b.close * b.adj_factor, b.value, f.foreign_net_share_20d, f.foreign_net_share_5d, f.value_60d_median
              FROM idx.bar b LEFT JOIN idx.feature_daily f USING (trade_date, code)
             WHERE b.source = 'idx' AND b.code = ANY(%s) ORDER BY b.trade_date, b.code
            """, (codes,))
        rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["d", "code", "o", "h", "l", "c", "value", "f20", "f5", "v60"])
    df["d"] = pd.to_datetime(df["d"])
    for col in ("o", "h", "l", "c", "value", "f20", "f5", "v60"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    wide = {col: df.pivot(index="d", columns="code", values=col) for col in ("o", "h", "l", "c", "value", "f20", "f5", "v60")}
    wide["liq"] = (wide["v60"].shift(1) >= 5e9)          # strictly past data, like the screen's mask
    return wide


def sleeve_pooled(wide, codes, en, xn, long_only, flt):
    """Run the next-open sleeve per name with entry mask = liq & flow filter; return the pooled equal-weight
    daily series (mean across names in position that day) and trade count."""
    dates = [d.strftime("%Y-%m-%d") for d in wide["c"].index]
    pooled_sum = np.zeros(len(dates)); pooled_n = np.zeros(len(dates)); n_trades = 0
    idx_of = {d: i for i, d in enumerate(dates)}
    pred = FLOW_FILTERS[flt]
    for code in codes:
        c = wide["c"][code].to_numpy();
        if np.isnan(c).sum() > len(c) * 0.5:
            continue
        # forward-fill gaps (untraded days) for channel math; a name with no bar that day stays flat
        cs = pd.Series(c).ffill().to_numpy()
        o = wide["o"][code].to_numpy(); h = pd.Series(wide["h"][code].to_numpy()).ffill().to_numpy()
        l = pd.Series(wide["l"][code].to_numpy()).ffill().to_numpy()
        f20 = wide["f20"][code].to_numpy(); f5 = wide["f5"][code].to_numpy(); liq = wide["liq"][code].to_numpy()
        valid = ~np.isnan(cs)
        if valid.sum() < 300:
            continue
        mask = [bool(liq[i]) and not np.isnan(cs[i]) and pred(None if np.isnan(f20[i]) else f20[i], None if np.isnan(f5[i]) else f5[i])
                for i in range(len(dates))]
        O = [None if np.isnan(x) else float(x) for x in o]
        daily, trades, _ = IS.sleeve_fill(dates, O, list(map(float, h)), list(map(float, l)), list(map(float, cs)),
                                          en, xn, long_only, COST, mask, "next_open")
        n_trades += len(trades)
        for d, r in daily.items():
            if r != 0.0:
                i = idx_of[d]; pooled_sum[i] += r; pooled_n[i] += 1
    pooled = np.where(pooled_n > 0, pooled_sum / np.maximum(pooled_n, 1), 0.0)
    return pooled, n_trades, int((pooled_n > 0).sum())


def stats(series):
    s = [float(x) for x in series]
    return {"sharpe": round(ES.sharpe(s, 252), 3), "ret_pct": round((math.exp(sum(s)) - 1) * 100, 1),
            "mdd": round(ES.maxdd(s), 1), "days": len(s)}


# ---------------------------------------------------------------------------

def test_A(wide, codes, out):
    print("\n=== A. Flow filter on the Donchian sleeve (pooled equal-weight, next-open, 50 bps, liq gate) ===")
    res = {}
    n_variants = len(FLOW_FILTERS) * len(GRID) * 2
    for flt in FLOW_FILTERS:
        best = None
        for en, xn in GRID:
            for lo in (True, False):
                pooled, n_tr, active = sleeve_pooled(wide, codes, en, xn, lo, flt)
                st = stats(pooled); st.update({"cell": f"{en}/{xn} {'L' if lo else 'LS'}", "trades": n_tr, "active_days": active,
                                               "dsr_N": round(ES.deflated_sharpe(list(pooled), n_variants), 3)})
                if best is None or st["sharpe"] > best["sharpe"]:
                    best = st
        res[flt] = best
        print("  %-12s best %-10s Sharpe %6.3f ret %7.1f%% mDD %5.1f%% trades %5d DSR@%d %.3f"
              % (flt, best["cell"], best["sharpe"], best["ret_pct"], best["mdd"], best["trades"], n_variants, best["dsr_N"]))
    out["A_flow_filter_on_trend"] = {"variants": n_variants, "results": res}


def test_B(wide, codes, out):
    print("\n=== B. Standalone foreign-flow signal (weekly quintile sorts, net of 50 bps on turnover) ===")
    c = wide["c"]; liq = wide["liq"]
    ret = np.log(c / c.shift(1))                                     # daily log return per name
    res = {}
    n_variants = 0
    for fcol in ("f20", "f5"):
        f = wide[fcol]
        weeks = pd.Series(c.index, index=c.index).dt.to_period("W")
        rebal = c.index[weeks != weeks.shift(1)]                      # first trading day of each week
        q_ret = {q: [] for q in range(1, 6)}
        q_dates = []
        prev_sets = {q: set() for q in range(1, 6)}
        held = {q: set() for q in range(1, 6)}
        cost_next = {q: 0.0 for q in range(1, 6)}                     # rebalance cost charged to the next day
        for i, d in enumerate(c.index):
            # 1) realise today's return on what was held from the previous close (PIT: no same-day selection)
            if i > 0:
                for q in range(1, 6):
                    hs = held[q]
                    r = ret.loc[d, list(hs)].dropna() if hs else pd.Series(dtype=float)
                    q_ret[q].append((float(r.mean()) if len(r) else 0.0) - cost_next[q])
                    cost_next[q] = 0.0
                q_dates.append(d)
            # 2) at a rebalance close, select on today's feature; positions take effect from tomorrow,
            #    and the round-trip cost on the changed fraction is charged to tomorrow's return
            if d in rebal:
                row = f.loc[d]; ok = liq.loc[d] & row.notna()
                names = row[ok]
                if len(names) >= 25:
                    ranks = names.rank(method="first")
                    qs = pd.qcut(ranks, 5, labels=[1, 2, 3, 4, 5])
                    new_held = {q: set(qs[qs == q].index) for q in range(1, 6)}
                    for q in range(1, 6):
                        changed = len(new_held[q].symmetric_difference(held[q])) / max(1, len(new_held[q]))
                        cost_next[q] = changed * COST / 10000.0               # 25 bps x changed fraction (~50 bps full turnover)
                    held = new_held
        n_variants += 1
        s5 = np.array(q_ret[5]); s1 = np.array(q_ret[1]); spread = s5 - s1
        yearly = pd.Series(spread, index=pd.DatetimeIndex(q_dates)).groupby(lambda x: x.year).sum()
        t = spread.mean() / (spread.std(ddof=1) / math.sqrt(len(spread))) if len(spread) > 2 and spread.std() > 0 else 0.0
        res[fcol] = {"Q5": stats(s5), "Q1": stats(s1), "spread": stats(spread), "t_stat": round(float(t), 2),
                     "yearly_spread_pct": {str(k): round(100 * (math.exp(v) - 1), 1) for k, v in yearly.items()},
                     "per_quintile_sharpe": {str(q): round(ES.sharpe(q_ret[q], 252), 3) for q in range(1, 6)}}
        print("  %s: Q5 Sharpe %.3f | Q1 Sharpe %.3f | Q5-Q1 spread Sharpe %.3f (t=%.2f) ret %.1f%% | yearly %s | by quintile %s"
              % (fcol, res[fcol]["Q5"]["sharpe"], res[fcol]["Q1"]["sharpe"], res[fcol]["spread"]["sharpe"], res[fcol]["t_stat"],
                 res[fcol]["spread"]["ret_pct"], res[fcol]["yearly_spread_pct"], res[fcol]["per_quintile_sharpe"]))
    # long-only flow momentum rule, pooled
    f20 = wide["f20"]; f5 = wide["f5"]
    pos = ((f20 > 0) & (f5 > 0) & liq).shift(1).fillna(False).astype(bool)   # held from the next day
    r = (ret.where(pos)).mean(axis=1).fillna(0.0)
    turn = (pos.astype(int).diff().abs().sum(axis=1) / pos.sum(axis=1).replace(0, np.nan)).fillna(0.0)
    net = r - turn * COST / 10000.0
    res["long_flow_momentum"] = stats(net.to_numpy()); n_variants += 1
    res["long_flow_momentum"]["avg_names"] = round(float(pos.sum(axis=1).mean()), 1)
    print("  long-only f20>0&f5>0 (daily, pooled, net): Sharpe %.3f ret %.1f%% mDD %.1f%% avg names %.0f"
          % (res["long_flow_momentum"]["sharpe"], res["long_flow_momentum"]["ret_pct"], res["long_flow_momentum"]["mdd"], res["long_flow_momentum"]["avg_names"]))
    # universe equal-weight benchmark
    bench = ret.where(liq).mean(axis=1).fillna(0.0)
    res["benchmark_ew_liquid"] = stats(bench.to_numpy())
    print("  benchmark: equal-weight liquid universe Sharpe %.3f ret %.1f%% mDD %.1f%%" % (res["benchmark_ew_liquid"]["sharpe"], res["benchmark_ew_liquid"]["ret_pct"], res["benchmark_ew_liquid"]["mdd"]))
    for k in ("f20", "f5"):
        res[k]["spread"]["dsr_N"] = round(ES.deflated_sharpe(list(np.array(q_ret[5]) - np.array(q_ret[1])), n_variants), 3) if False else None
    out["B_standalone_flow"] = {"variants": n_variants, "results": res}


def test_C(conn, wide, codes, out):
    print("\n=== C. Event studies (abnormal return vs equal-weight liquid universe; effective day = PIT day) ===")
    c = wide["c"]; liq = wide["liq"]
    ret = np.log(c / c.shift(1))
    bench = ret.where(liq).mean(axis=1)
    ab = ret.sub(bench, axis=0)
    cum = ab.cumsum()
    with conn.cursor() as cur:
        cur.execute("SELECT code, kind, published_at FROM idx.event WHERE code = ANY(%s) AND kind = ANY(%s)", (codes, EVENT_KINDS))
        ev = pd.DataFrame(cur.fetchall(), columns=["code", "kind", "published_at"])
    if ev.empty:
        print("  no events"); return
    ev["published_at"] = pd.to_datetime(ev["published_at"], utc=True)
    from blackheart_ingest.idx.features import event_effective_date
    tdays = c.index
    ev["eff"] = [event_effective_date(t.to_pydatetime(), tdays) for t in ev["published_at"]]
    ev = ev.dropna(subset=["eff"]); ev["eff"] = pd.to_datetime(ev["eff"])
    pos_of = {d: i for i, d in enumerate(tdays)}
    res = {}
    for kind in EVENT_KINDS:
        e = ev[ev["kind"] == kind]
        rows = []
        for code, d in zip(e["code"], e["eff"]):
            if code not in cum.columns or d not in pos_of:
                continue
            i = pos_of[d]
            if i < 6 or i + 21 >= len(tdays):
                continue
            base = cum[code].iloc[i]           # cumulative through the effective day's close
            pre5 = cum[code].iloc[i] - cum[code].iloc[i - 5]
            rows.append({"pre5": pre5, **{f"h{h}": cum[code].iloc[i + h] - base for h in (1, 5, 10, 20)}})
        if len(rows) < 30:
            print("  %-17s n=%d (too few)" % (kind, len(rows))); continue
        df = pd.DataFrame(rows).replace([np.inf, -np.inf], np.nan).dropna()
        st = {}
        for col in ("pre5", "h1", "h5", "h10", "h20"):
            x = df[col]; t = x.mean() / (x.std(ddof=1) / math.sqrt(len(x))) if x.std() > 0 else 0.0
            st[col] = {"mean_pct": round(100 * x.mean(), 2), "t": round(float(t), 2), "hit": round(float((x > 0).mean()), 2)}
        res[kind] = {"n": len(df), **st}
        print("  %-17s n=%4d | pre5 %+.2f%% (t %.1f) | +1d %+.2f%% (t %.1f) | +5d %+.2f%% (t %.1f) | +10d %+.2f%% (t %.1f) | +20d %+.2f%% (t %.1f)"
              % (kind, len(df), st["pre5"]["mean_pct"], st["pre5"]["t"], st["h1"]["mean_pct"], st["h1"]["t"], st["h5"]["mean_pct"], st["h5"]["t"],
                 st["h10"]["mean_pct"], st["h10"]["t"], st["h20"]["mean_pct"], st["h20"]["t"]))
    out["C_event_studies"] = {"kinds_tested": len(EVENT_KINDS), "horizons": 4, "results": res}


def test_D(wide, out):
    print("\n=== D. BRPT 20/10 L (2020+ window) with each flow filter — thin, informational ===")
    res = {}
    for flt in FLOW_FILTERS:
        pooled, n_tr, _ = sleeve_pooled(wide, ["BRPT"], 20, 10, True, flt)
        st = stats(pooled); st["trades"] = n_tr; res[flt] = st
        print("  %-12s Sharpe %6.3f ret %7.1f%% mDD %5.1f%% trades %d" % (flt, st["sharpe"], st["ret_pct"], st["mdd"], n_tr))
    out["D_brpt_filters"] = res


def main():
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument("--limit", type=int, help="first N universe names (smoke test)")
    a = ap.parse_args()
    conn = IS.connect()
    universe = json.load(open(os.path.join(OUTDIR, "universe.json")))
    codes = [u["code"] for u in universe][: a.limit] if a.limit else [u["code"] for u in universe]
    if "BRPT" not in codes:
        codes.append("BRPT")
    wide = load(conn, codes)
    print("loaded: %d dates x %d codes; f20 coverage %.0f%% of bars" % (len(wide["c"]), len(wide["c"].columns),
          100 * wide["f20"].notna().sum().sum() / wide["c"].notna().sum().sum()))
    out = {"generated": datetime.now(timezone.utc).isoformat(), "universe": len(codes), "window": [str(wide["c"].index[0].date()), str(wide["c"].index[-1].date())]}
    test_A(wide, codes, out)
    test_B(wide, codes, out)
    test_C(conn, wide, codes, out)
    test_D(wide, out)
    with open(os.path.join(OUTDIR, "overlays_results.json"), "w") as f:
        json.dump(out, f, indent=1, default=str)
    print("\nresults -> research-scratch/idx-screen/overlays_results.json")


if __name__ == "__main__":
    main()
