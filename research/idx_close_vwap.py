#!/usr/bin/env python3
"""IDX menu NS-1 - the close against the day's VWAP: does a close dumped below where the day actually traded come back?
(operator, 2026-09-25: "anggap saja combo tidak ada ... bikin strategi baru").

A NEW family: no study before this one used the day's VWAP (value / volume from idx.bar) - grep of research/ on 2026-09-25.
The IDX-specific reason to look: the closing price is set in a pre-closing auction and is widely believed to be marked -
up for window dressing, down when size is dumped into the auction. VWAP is what the day's volume actually paid. A close far
BELOW VWAP says the last minutes (or the auction) were a seller's; if that pressure is liquidity rather than information, it
reverses. The long side is the only one a retail IDX account can trade, and it can be traded without the spread: an order
in the pre-closing auction fills AT the close, an order in the pre-opening auction AT the open.

PANEL: idx.bar (source idx) 2020-01-02 -> last bar; adjusted by adj_factor for the forward returns. dev = close / VWAP - 1,
VWAP = value / volume (verified inside [low, high] on every bar). UNIVERSE on day t: 60-day average traded value >= Rp 5 bn
(point in time, ending t), close >= Rp 100, the day's value >= Rp 1 bn, a bar on t+1.

PRE-REGISTERED (2 trials; cumulative 863 + 2 = 865).
  VW_O   each day buy the K = 5 names with the most negative dev (dev <= -3 %) at the close auction, sell at the next open
         auction; 1/K of the book each (unfilled slots stay in cash). Costs: fees 0.10 % buy + 0.20 % sell (auction fills,
         no spread) + 0.10 % assumed impact each side = 0.50 % round trip.
  VW_C   the same, sold at the next CLOSE auction.
  Controls (not trials): REV_O / REV_C - the same book ranked by the day's intraday return (close / open - 1 <= -3 %), the
  textbook short-term reversal; RAND - K random names of the universe each day.
  Neighbours (robustness, not trials): K in {3, 10}, threshold in {-2 %, -5 %}; costs x1.5.
READING RULE: an arm is a STRATEGY CANDIDATE if ALL of: Sharpe >= 1.0 and t >= 3 on daily net returns; positive in >= 5 of
the 7 calendar years; positive in both halves (split 2023-05-01); at costs x1.5 Sharpe >= 0.7; Sharpe above its REV control
(the VWAP must add to plain reversal) and above RAND; and 3 of the 4 neighbours positive. Informative: deciles of dev against
next-open / next-close / 5-day returns; the split of events at the lower auto-rejection band; median traded value (capacity).
READ-ONLY; one idx.study row. INGEST_DB_DSN (or idx-local.env).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date

import numpy as np
import pandas as pd
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "blackheart-ingest", "src"))
from blackheart_ingest.idx import research_store as rs  # noqa: E402
from blackheart_ingest.idx.ml import common  # noqa: E402

N_BEFORE = 863
STUDY = "close_vwap"
K, THR = 5, -0.03
FEE_B, FEE_S, IMPACT = 0.0010, 0.0020, 0.0010
V60_MIN, PX_MIN, VAL_MIN = 5e9, 100.0, 1e9
HALF = pd.Timestamp("2023-05-01")
SEED = 20260925


def log(m: str) -> None:
    print(f"[ns1] {m}", flush=True)


def dsn() -> str:
    if os.environ.get("INGEST_DB_DSN"):
        return os.environ["INGEST_DB_DSN"]
    for line in open(os.path.join(ROOT, "blackheart-ingest", "idx-local.env"), encoding="utf-8"):
        if line.startswith("INGEST_DB_DSN="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("INGEST_DB_DSN not set")


def load(d: str) -> dict[str, pd.DataFrame]:
    with psycopg.connect(d) as conn, conn.cursor() as cur:
        cur.execute("""SELECT code, trade_date, open, high, low, close, volume, value, adj_factor FROM idx.bar
                        WHERE source = 'idx' AND trade_date >= '2019-09-01'""")
        df = pd.DataFrame(cur.fetchall(), columns=["code", "d", "open", "high", "low", "close", "volume", "value", "af"])
    for c in ("open", "high", "low", "close", "volume", "value", "af"):
        df[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
    df["d"] = pd.to_datetime(df["d"])
    W = {c: df.pivot(index="d", columns="code", values=c).sort_index() for c in ("open", "high", "low", "close", "volume", "value", "af")}
    log(f"bars {len(df):,}, {W['close'].shape[1]} names, {W['close'].index[0].date()} -> {W['close'].index[-1].date()}")
    return W


def book(sig: np.ndarray, score: np.ndarray, ret: np.ndarray, k: int, cost: float, rng=None, uni=None) -> np.ndarray:
    """Daily book: on day t pick up to k names where sig (lowest score first; random if rng), earn ret[t] (the forward return
    booked on the entry day), weight 1/k each. Returns the daily net return series (length T)."""
    T = sig.shape[0]
    out = np.zeros(T)
    for t in range(T):
        if rng is not None:
            cand = np.flatnonzero(uni[t] & np.isfinite(ret[t]))
            if len(cand) == 0:
                continue
            pick = rng.choice(cand, size=min(k, len(cand)), replace=False)
        else:
            cand = np.flatnonzero(sig[t] & np.isfinite(ret[t]))
            if len(cand) == 0:
                continue
            pick = cand[np.argsort(score[t, cand], kind="stable")[:k]]
        out[t] = float(np.sum(ret[t, pick] - cost)) / k
    return out


def stats(r: pd.Series, n_trials: int) -> dict:
    r = r.fillna(0.0)
    eq = (1 + r).cumprod()
    yrs = len(r) / 250
    sd = r.std()
    active = r[r != 0]
    by = r.groupby(r.index.year).apply(lambda s: (1 + s).prod() - 1)
    h1, h2 = r[r.index < HALF], r[r.index >= HALF]
    return {"cagr": float(eq.iloc[-1] ** (1 / yrs) - 1) if yrs > 0 else 0.0, "sharpe": float(r.mean() / sd * np.sqrt(250)) if sd > 0 else 0.0,
            "t": float(r.mean() / sd * np.sqrt(len(r))) if sd > 0 else 0.0, "mdd": float((eq / eq.cummax() - 1).min()),
            "days_active": int(len(active)), "avg_active": float(active.mean()) if len(active) else 0.0,
            "win_active": float((active > 0).mean()) if len(active) else 0.0,
            "h1": float((1 + h1).prod() - 1), "h2": float((1 + h2).prod() - 1), "years": {int(y): float(v) for y, v in by.items()}}


def main() -> int:
    d = dsn()
    W = load(d)
    o, h, lo, c, v, val, af = (W[k] for k in ("open", "high", "low", "close", "volume", "value", "af"))
    dates = c.index
    vwap = (val / v.where(v > 0)).where(lambda x: (x >= lo * 0.999) & (x <= h * 1.001))
    dev = c / vwap - 1
    intra = c / o.where(o > 0) - 1
    clv = ((c - lo) / (h - lo).where(h > lo))
    v60 = val.rolling(60, min_periods=40).mean()
    ac, ao = c * af, o * af
    r_o = (ao.shift(-1) / ac - 1)                    # close t -> open t+1
    r_c = (ac.shift(-1) / ac - 1)                    # close t -> close t+1
    r_5 = (ac.shift(-5) / ac - 1)
    prev = c.shift(1)
    day_ret = c / prev - 1
    arb = (c <= lo * 1.0001) & (day_ret <= -0.065)   # closed on its low after a >= 6.5 % fall: at or near the lower band
    uni = (v60 >= V60_MIN) & (c >= PX_MIN) & (val >= VAL_MIN) & c.shift(-1).notna() & dev.notna()
    start = np.searchsorted(dates, pd.Timestamp("2020-01-02"))
    sl = slice(start, len(dates) - 1)
    D = dates[sl]
    U = uni.to_numpy(bool)[sl]
    DEV, INTRA = dev.to_numpy(float)[sl], intra.to_numpy(float)[sl]
    RO, RC = r_o.to_numpy(float)[sl], r_c.to_numpy(float)[sl]
    log(f"universe name-days {int(U.sum()):,}; dev <= -3 %: {int((U & (DEV <= THR)).sum()):,}")
    cost = FEE_B + FEE_S + 2 * IMPACT
    n_trials = N_BEFORE + 2

    # ---- deciles (informative)
    ev = pd.DataFrame({"dev": dev.stack(), "ro": r_o.stack(), "rc": r_c.stack(), "r5": r_5.stack(), "u": uni.stack(), "arb": arb.stack(),
                       "val": val.stack()})
    ev = ev[ev["u"].astype(bool) & ev["dev"].notna() & ev["rc"].notna()]
    ev = ev[ev.index.get_level_values(0) >= pd.Timestamp("2020-01-02")]
    ev["dec"] = pd.qcut(ev["dev"], 10, labels=False, duplicates="drop")
    dec = ev.groupby("dec").agg(n=("dev", "size"), dev=("dev", "mean"), ro=("ro", "mean"), rc=("rc", "mean"), r5=("r5", "mean"))
    ic = {k: float(stats_ic(ev["dev"], ev[k])) for k in ("ro", "rc", "r5")}
    deep = ev[ev["dev"] <= THR]
    arb_split = {g: {"n": int(len(s)), "ro": float(s["ro"].mean()), "rc": float(s["rc"].mean())} for g, s in deep.groupby(deep["arb"].map({True: "at_lower_band", False: "not"}))}
    log(f"IC dev vs next open {ic['ro']:+.3f}, next close {ic['rc']:+.3f}, 5 days {ic['r5']:+.3f}")

    # ---- books
    res = {}
    rng = np.random.default_rng(SEED)
    runs = {
        "VW_O": (U & (DEV <= THR), DEV, RO, K, cost), "VW_C": (U & (DEV <= THR), DEV, RC, K, cost),
        "REV_O": (U & (INTRA <= THR), INTRA, RO, K, cost), "REV_C": (U & (INTRA <= THR), INTRA, RC, K, cost),
        "VW_O_cost1.5": (U & (DEV <= THR), DEV, RO, K, cost * 1.5), "VW_C_cost1.5": (U & (DEV <= THR), DEV, RC, K, cost * 1.5),
        "VW_O_K3": (U & (DEV <= THR), DEV, RO, 3, cost), "VW_O_K10": (U & (DEV <= THR), DEV, RO, 10, cost),
        "VW_O_thr2": (U & (DEV <= -0.02), DEV, RO, K, cost), "VW_O_thr5": (U & (DEV <= -0.05), DEV, RO, K, cost),
        "VW_C_K3": (U & (DEV <= THR), DEV, RC, 3, cost), "VW_C_K10": (U & (DEV <= THR), DEV, RC, 10, cost),
        "VW_C_thr2": (U & (DEV <= -0.02), DEV, RC, K, cost), "VW_C_thr5": (U & (DEV <= -0.05), DEV, RC, K, cost),
    }
    for name, (sig, score, ret, k, cst) in runs.items():
        res[name] = stats(pd.Series(book(sig, score, ret, k, cst), index=D), n_trials)
    for name, ret in (("RAND_O", RO), ("RAND_C", RC)):
        res[name] = stats(pd.Series(book(U, DEV, ret, K, cost, rng=rng, uni=U), index=D), n_trials)
    for name, s in res.items():
        log(f"{name:14s} CAGR {s['cagr']:+7.1%} Sharpe {s['sharpe']:5.2f} t {s['t']:5.1f} mDD {s['mdd']:5.0%} active {s['days_active']:4d} "
            f"avg {s['avg_active']:+.2%} win {s['win_active']:.0%} | " + " ".join(f"{y}:{x:+.0%}" for y, x in s["years"].items()))

    def verdict(arm: str) -> dict:
        s, x = res[arm], arm.split("_")[1]
        rev, rnd, c15 = res[f"REV_{x}"], res[f"RAND_{x}"], res[f"{arm}_cost1.5"]
        nb = [res[f"{arm}_{n}"] for n in ("K3", "K10", "thr2", "thr5")]
        chk = {"sharpe_t": s["sharpe"] >= 1.0 and s["t"] >= 3, "years": sum(1 for y in s["years"].values() if y > 0) >= 5,
               "halves": s["h1"] > 0 and s["h2"] > 0, "cost1.5": c15["sharpe"] >= 0.7, "beats_rev": s["sharpe"] > rev["sharpe"],
               "beats_rand": s["sharpe"] > rnd["sharpe"], "neighbours": sum(1 for n in nb if n["cagr"] > 0) >= 3}
        chk["CANDIDATE"] = all(chk.values())
        return chk
    ver = {a: verdict(a) for a in ("VW_O", "VW_C")}
    dsr = {}
    for a in ("VW_O", "VW_C"):
        try:
            sys.path.insert(0, HERE)
            import equity_screen as ES
            r = pd.Series(book(U & (DEV <= THR), DEV, RO if a == "VW_O" else RC, K, cost), index=D)
            dsr[a] = float(ES.deflated_sharpe(list(r[r != 0].values), n_trials))
        except Exception as e:  # noqa: BLE001 - context only
            dsr[a] = f"n/a ({type(e).__name__})"
    cap = {"median_value_of_picks": float(deep["val"].median()), "p10_value": float(deep["val"].quantile(0.1))}

    # ---- report
    years = sorted(res["VW_O"]["years"])
    L = [f"# IDX menu NS-1 - close vs VWAP: buy the close dumped below the day's VWAP - {date.today()} - 2 trials, cumulative N = {n_trials}", "",
         f"Universe: 60-day value >= Rp {V60_MIN / 1e9:.0f} bn, close >= Rp {PX_MIN:.0f}, day value >= Rp {VAL_MIN / 1e9:.0f} bn; {D[0].date()} -> {D[-1].date()}. "
         f"K = {K}, dev <= {THR:.0%}, round-trip cost {cost:.2%} (auction fills, no spread; 0.10 % impact each side).", "",
         "## Deciles of close / VWAP - 1 (universe name-days)", "", "| decile | n | mean dev | next open | next close | 5 days |", "|---|---|---|---|---|---|"]
    for i, r in dec.iterrows():
        L.append(f"| {int(i) + 1} | {int(r['n']):,} | {r['dev']:+.2%} | {r['ro']:+.2%} | {r['rc']:+.2%} | {r['r5']:+.2%} |")
    L += ["", f"Rank IC of dev with next-open {ic['ro']:+.3f}, next-close {ic['rc']:+.3f}, 5-day {ic['r5']:+.3f} (negative = reversal).",
          f"Events with dev <= {THR:.0%} at/near the lower auto-rejection band vs not: {json.dumps({k: {kk: round(vv, 4) for kk, vv in x.items()} for k, x in arb_split.items()})}", "",
          "## Books (net of costs)", "", "| arm | CAGR | Sharpe | t | mDD | days active | avg / active day | win | H1 | H2 | " + " | ".join(str(y) for y in years) + " |",
          "|---|---|---|---|---|---|---|---|---|---|" + "---|" * len(years)]
    for name, s in res.items():
        L.append(f"| {name} | {s['cagr']:+.1%} | {s['sharpe']:.2f} | {s['t']:.1f} | {s['mdd']:.0%} | {s['days_active']} | {s['avg_active']:+.2%} | {s['win_active']:.0%} | "
                 f"{s['h1']:+.0%} | {s['h2']:+.0%} | " + " | ".join(f"{s['years'].get(y, 0):+.0%}" for y in years) + " |")
    L += ["", "## Verdict (pre-registered)", ""]
    for a, chk in ver.items():
        L.append(f"- **{a}**: " + ", ".join(f"{k} {'yes' if x else 'no'}" for k, x in chk.items() if k != "CANDIDATE")
                 + f" -> **{'STRATEGY CANDIDATE' if chk['CANDIDATE'] else 'not a candidate'}**")
    L += ["", f"Deflated Sharpe at N = {n_trials}: {dsr}. Capacity: median day value of the picks Rp {cap['median_value_of_picks'] / 1e9:.1f} bn "
          f"(10th pct Rp {cap['p10_value'] / 1e9:.1f} bn)."]
    text = "\n".join(L)
    out = os.path.join(HERE, f"IDX_CLOSE_VWAP_{date.today()}.md")
    open(out, "w", encoding="utf-8").write(text + "\n")
    json.dump(common.plain({"res": res, "verdict": ver, "ic": ic, "deciles": dec.reset_index().to_dict("records"), "arb": arb_split, "dsr": dsr, "capacity": cap}),
              open(out.replace(".md", ".json"), "w"), indent=1, default=str)
    print(text)
    with psycopg.connect(d) as conn:
        sid = rs.record_study(conn, STUDY, date.today(), params={"trials": ["VW_O", "VW_C"], "n_trials_cumulative": n_trials, "k": K, "thr": THR,
                                                                 "cost_round_trip": cost, "v60_min": V60_MIN},
                              summary=common.plain({"verdict": ver, "ic": ic, "VW_O": res["VW_O"], "VW_C": res["VW_C"], "REV_O": res["REV_O"], "REV_C": res["REV_C"]}),
                              names=[], report_path=out, note="menu NS-1: buy the close dumped below VWAP, sell next open/close")
        conn.commit()
    log(f"study #{sid} stored; report {out}")
    return 0


def stats_ic(x: pd.Series, y: pd.Series) -> float:
    m = x.notna() & y.notna()
    return pd.Series(x[m].values).rank().corr(pd.Series(y[m].values).rank())


if __name__ == "__main__":
    sys.exit(main())
