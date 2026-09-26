#!/usr/bin/env python3
"""IDX menu 49 - rights (HMETD) exercise arbitrage (Phase 2, operator 2026-09-26: "Tetap IDX saja").

A right trades for a few sessions after the ex-date. Holding one, you may pay the exercise price K and receive a new share a
few sessions later. When right + K is below the stock price, buying the right, exercising, and selling the new share looks
free - but the share is delivered L sessions later, and the stock usually drifts down during the rights period (new supply).
The question is whether the discount survives that drift and the costs.

PRE-REGISTERED 2026-09-26 before any result of this script was seen (6 trials; cumulative 1007 + 6 = 1013):
  DATA     idx.right_offering (terms: ratio, K = ex_price > 0, ex_date) matched to rights series in idx.deriv_bar (Stockbit,
           volume > 0) by code, the ex-date 0..45 days before the series' first traded day;
           the stock from idx.bar (raw close, source idx) and idx.daily_summary (value).
  TRADE    on right trading day d, at d's close: buy the right at close_R + 1 tick (+0.15 % fee), exercise the same day (pay K),
           sell the new share at the close of the L-th stock session after d at close_S - 1 tick (-0.25 % fee).
           r = proceeds / (right cost + K) - 1.
  SIGNAL   discount D = (close_S - K - close_R) / (K + close_R) at d's close >= thr.
  FILTERS  right traded value on d >= Rp 50 M; stock traded value on d >= Rp 1 B (both known at d's close).
  ARMS     A1 thr 5 %, L 2 (MAIN) | A2 thr 2 %, L 2 | A3 thr 10 %, L 2 | A4 thr 5 %, L 1 | A5 thr 5 %, L 3 |
           A6 every day that passes the filters, L 2 (does the discount predict anything at all?)
  UNIT     the ISSUE: a right's days are one event (same stock, same few sessions); each issue's return = mean over its
           signalled days. Tests run on issues, not days.
  PASS (MAIN, all of): issue mean > 0 with t >= 2.0; >= 55 % of issues positive; mean > 0 in both halves (ex_date 2020-2022 /
           2023-2026); mean > 0 with costs x 1.5; mean > 0 without the top 5 % of issues. Neighbours A2..A5 >= 3 of 4 with
           mean > 0 for ROBUST. A6 is context.
  ALSO     share of exits on a limit-down close (stock close <= previous close x (1 - 0.069)): the sale may not fill there.
REV.2 (same day, after the first run was read - so it is recorded as 6 MORE trials, cumulative 1013 + 6 = 1019). The first run
  (MAIN +16.7 %/issue, t 3.9) was mechanically impossible, not a finding:
    - a right bought on the market settles T+2; it can be exercised on stock session d+2 at the earliest, and the new share is
      sellable D sessions after that. The exit is now session d + 2 + D (D = 2 MAIN, neighbours 1 and 3), not d + L.
    - a right bought fewer than 2 sessions before its last trading day cannot settle before exercise closes (exercise assumed
      to end with the right's last trading day): those days are dropped (36 % of the first run's signalled days).
    - an exit close that is locked at the lower limit (close at the day's low and >= 6.5 % under the previous close - the
      tick-rounded ARB, e.g. 120 -> 112 = -6.7 %) cannot be sold there: the exit rolls to the next unlocked close (<= 5).
    - one issue could appear as two series (BEKS-R20210401 and BEKS-R@2021-01): the issue is now (code, ex_date).
  Thresholds, filters, fees, unit and pass rules are unchanged. Arms: A1 thr 5 %, D 2 (MAIN) | A2 thr 2 % | A3 thr 10 % |
  A4 D 1 | A5 D 3 | A6 all days.
READ-ONLY; one idx.study row (rights_arb).
Run: python research/idx_rights_arb.py [--no-store]
"""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta

import numpy as np
import pandas as pd
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blackheart-ingest", "src"))
import idx_alloc_frontier as AF  # noqa: E402
from blackheart_ingest.idx import research_store as rs  # noqa: E402
from blackheart_ingest.idx.ml import common  # noqa: E402
from blackheart_ingest.idx.risk import idx_tick  # noqa: E402

STUDY = "rights_arb"
N_BEFORE = 1013                     # rev.2: the first run (1007 + 6) was read before the execution was corrected
SETTLE = 2                          # a right bought on d is exercisable on stock session d + 2
LOCK_DROP = 0.065                   # a close at the day's low this far under the previous close = locked at the lower limit
MAX_ROLL = 5
FEE_BUY, FEE_SELL = 0.0015, 0.0025
MIN_R_VALUE, MIN_S_VALUE = 50e6, 1e9
ARMS = {"A1_main": (0.05, 2), "A2_thr2": (0.02, 2), "A3_thr10": (0.10, 2), "A4_D1": (0.05, 1), "A5_D3": (0.05, 3), "A6_all": (None, 2)}
SPLIT = date(2023, 1, 1)


def right_tick(p: float) -> float:
    return 1.0 if p < 200 else idx_tick(p)


def trade_return(r_close: float, k: float, s_exit: float, cost_mult: float = 1.0) -> float:
    """Pure. One right bought at the close (+1 tick, fee), exercised at K, the share sold at the exit close (-1 tick, fee)."""
    buy = (r_close + right_tick(r_close)) * (1 + FEE_BUY * cost_mult)
    sell = max(s_exit - idx_tick(s_exit) * cost_mult, 0.0) * (1 - FEE_SELL * cost_mult)
    return sell / (buy + k) - 1


def load(conn) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Terms matched to a rights series by code and time: the issue whose ex-date lies 0..45 days before the series' first
    traded day (the right starts trading a few sessions after the ex-date). Works for both code formats ('COCO-R20260721',
    and the older 'AGRS-R@2022-08' runs)."""
    off = pd.read_sql("SELECT code, ex_date, ex_price, ratio_old, ratio_new FROM idx.right_offering WHERE ex_price > 0", conn)
    bars = pd.read_sql("SELECT series, code AS xcode, trade_date, close, value FROM idx.deriv_bar WHERE code LIKE '%%-R'", conn)
    first = bars.groupby("series").agg(first=("trade_date", "min"), xcode=("xcode", "first")).reset_index()
    first["code"] = first["xcode"].str.replace("-R", "", regex=False)
    m = first.merge(off, on="code")
    m = m[(m["ex_date"] <= m["first"]) & (m["ex_date"] >= m["first"] - timedelta(days=45))]
    m = m.sort_values("ex_date").drop_duplicates("series", keep="last").rename(columns={"series": "idx_code"})
    m["issue"] = m["code"] + ":" + m["ex_date"].astype(str)
    codes = sorted(m["code"].unique())
    stock = pd.read_sql("""SELECT b.code, b.trade_date, b.close, b.low, s.value FROM idx.bar b
                           LEFT JOIN idx.daily_summary s ON s.code = b.code AND s.trade_date = b.trade_date
                           WHERE b.source = 'idx' AND b.code = ANY(%s) AND b.trade_date >= '2019-11-01'""", conn, params=(codes,))
    return m, bars, stock


def exit_at(s: pd.DataFrame, j: int) -> tuple[float | None, int]:
    """The first sellable close from stock session j: a close locked at the lower limit rolls to the next (<= MAX_ROLL).
    -> (price, sessions rolled); None when the data ends first."""
    for k in range(MAX_ROLL + 1):
        t = j + k
        if t >= len(s):
            return None, k
        c, prev = float(s.loc[t, "close"]), float(s.loc[t - 1, "close"])
        lo = float(s.loc[t, "low"]) if pd.notna(s.loc[t, "low"]) else c
        if not (c <= lo and c <= prev * (1 - LOCK_DROP)):
            return c, k
    return None, MAX_ROLL + 1


def events(m: pd.DataFrame, bars: pd.DataFrame, stock: pd.DataFrame) -> pd.DataFrame:
    """Every feasible right trading day (settles before the right's last trading day) with the sellable exit for D = 1..3."""
    rows = []
    st = {c: g.sort_values("trade_date").reset_index(drop=True) for c, g in stock.groupby("code")}
    for x in m.itertuples():
        b = bars[bars["series"] == x.idx_code]
        s = st.get(x.code)
        if b.empty or s is None:
            continue
        dates = list(s["trade_date"])
        last_r = b["trade_date"].max()
        for y in b.itertuples():
            if y.trade_date not in dates:
                continue
            i = dates.index(y.trade_date)
            if i + SETTLE >= len(s) or dates[i + SETTLE] > last_r:
                continue                                                        # cannot settle before exercise closes
            row = {"issue": x.issue, "series": x.idx_code, "code": x.code, "ex_date": x.ex_date, "d": y.trade_date, "k": float(x.ex_price),
                   "r": float(y.close), "r_value": float(y.value or 0), "s": float(s.loc[i, "close"]), "s_value": float(s.loc[i, "value"] or 0)}
            for D in (1, 2, 3):
                px, rolled = exit_at(s, i + SETTLE + D)
                row[f"s{D}"], row[f"ld{D}"] = px, rolled > 0
            rows.append(row)
    E = pd.DataFrame(rows).drop_duplicates(["issue", "d"])
    E["disc"] = (E["s"] - E["k"] - E["r"]) / (E["k"] + E["r"])
    return E


def arm(E: pd.DataFrame, thr: float | None, L: int, cost_mult: float = 1.0) -> pd.DataFrame:
    X = E[(E["r_value"] >= MIN_R_VALUE) & (E["s_value"] >= MIN_S_VALUE) & E[f"s{L}"].notna()].copy()
    if thr is not None:
        X = X[X["disc"] >= thr]
    X["ret"] = [trade_return(a, b, c, cost_mult) for a, b, c in zip(X["r"], X["k"], X[f"s{L}"], strict=True)]
    X["ld"] = X[f"ld{L}"]
    return X


def by_issue(X: pd.DataFrame) -> pd.DataFrame:
    return X.groupby("issue").agg(ret=("ret", "mean"), days=("ret", "size"), ex_date=("ex_date", "first"), ld=("ld", "mean"),
                                  disc=("disc", "mean"), r_value=("r_value", "median")).reset_index()


def describe(iss: pd.DataFrame, X: pd.DataFrame) -> dict:
    n = len(iss)
    if n == 0:
        return {"issues": 0}
    r = iss["ret"].to_numpy()
    t = float(r.mean() / (r.std(ddof=1) / np.sqrt(n))) if n > 1 and r.std(ddof=1) > 0 else None
    drop = max(1, int(np.ceil(n * 0.05)))                   # rev.2 fix: the first version kept every issue when n < 20
    cut = np.sort(r)[: max(1, n - drop)]
    two = np.sort(r)[: max(1, n - 2)]
    h1, h2 = iss[iss["ex_date"] < SPLIT]["ret"], iss[iss["ex_date"] >= SPLIT]["ret"]
    return {"issues": n, "days": int(len(X)), "mean": float(r.mean()), "median": float(np.median(r)), "t": t,
            "pos": float((r > 0).mean()), "mean_wo_top5": float(cut.mean()),
            "mean_wo_top2": float(two.mean()), "t_wo_top2": float(two.mean() / (two.std(ddof=1) / np.sqrt(len(two)))) if len(two) > 2 and two.std(ddof=1) > 0 else None, "h1_n": int(len(h1)), "h1_mean": float(h1.mean()) if len(h1) else None,
            "h2_n": int(len(h2)), "h2_mean": float(h2.mean()) if len(h2) else None, "limit_down_exit": float(X["ld"].mean()) if len(X) else None,
            "disc_median": float(X["disc"].median()), "right_value_median": float(X["r_value"].median())}


def main() -> int:
    store = "--no-store" not in sys.argv
    dsn = AF.dsn()
    with psycopg.connect(dsn) as conn:
        m, bars, stock = load(conn)
    E = events(m, bars, stock)
    print(f"issues matched {m['idx_code'].nunique()}, with bars {E['issue'].nunique()}, right-days {len(E)}")
    res = {}
    for name, (thr, L) in ARMS.items():
        X = arm(E, thr, L)
        res[name] = describe(by_issue(X), X)
    Xc = arm(E, *ARMS["A1_main"], cost_mult=1.5)
    res["A1_costs15"] = describe(by_issue(Xc), Xc)
    a = res["A1_main"]
    checks = {"mean_t2": bool(a.get("issues", 0) > 1 and a["mean"] > 0 and (a["t"] or 0) >= 2.0), "pos55": bool(a.get("pos", 0) >= 0.55),
              "halves": bool((a.get("h1_mean") or -1) > 0 and (a.get("h2_mean") or -1) > 0),
              "costs15": bool((res["A1_costs15"].get("mean") or -1) > 0), "wo_top5": bool(a.get("mean_wo_top5", -1) > 0)}
    nb = sum(1 for k in ("A2_thr2", "A3_thr10", "A4_D1", "A5_D3") if (res[k].get("mean") or -1) > 0)
    letter = ("ROBUST" if all(checks.values()) and nb >= 3 else "CANDIDATE" if all(checks.values()) else "CLOSED")
    # post-read diagnostic (declared as such, not part of the pre-registration): does it survive losing its two best issues?
    fragile = (a.get("t_wo_top2") or 0) < 2.0
    verdict = f"{letter} by the letter, FRAGILE in substance (without its two best issues t {a.get('t_wo_top2') or 0:.2f})" if fragile and letter != "CLOSED" else letter
    n_trials = N_BEFORE + len(ARMS)
    L_ = [f"# IDX menu 49 rev.2 - rights (HMETD) exercise arbitrage - {date.today()} - {len(ARMS)} trials, cumulative N = {n_trials}", "",
          "rev.2: the first run (+16.7 %/issue) ignored T+2 settlement, exercise deadlines and limit-down exits and double counted one",
          "issue; it is superseded, not reported. Exit = stock session d + 2 (settle, exercise) + D, rolled past locked closes.", "",
          f"Issues with terms and bars: {E['issue'].nunique()} ({len(E)} right trading days). Unit = the issue (mean over its signalled days).",
          "Buy the right at the close + 1 tick, exercise, sell the new share D sessions after exercise (d + 2) - 1 tick; fees 0.15 / 0.25 %.", "",
          "| arm | thr | D | issues | days | mean | median | t | positive | w/o top 5 % | 2020-22 n / mean | 2023-26 n / mean | exits rolled past a lock | median discount |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for k, v in res.items():
        thr, L = ARMS.get(k, ARMS["A1_main"])
        if not v.get("issues"):
            L_.append(f"| {k} | {thr} | {L} | 0 | | | | | | | | | | |")
            continue
        f = lambda x: f"{x * 100:+.2f} %" if x is not None else "-"  # noqa: E731
        L_.append(f"| {k} | {'-' if thr is None else f'{thr * 100:g} %'} | {L} | {v['issues']} | {v['days']} | {f(v['mean'])} | {f(v['median'])} | "
                  f"{v['t']:.2f} | {v['pos'] * 100:.0f} % | {f(v['mean_wo_top5'])} | {v['h1_n']} / {f(v['h1_mean'])} | {v['h2_n']} / {f(v['h2_mean'])} | "
                  f"{(v['limit_down_exit'] or 0) * 100:.0f} % | {v['disc_median'] * 100:.1f} % |")
    L_ += ["", f"MAIN checks: {checks}; neighbours with mean > 0: {nb}/4.",
           f"Post-read diagnostic: MAIN without its two best issues = mean {a.get('mean_wo_top2', 0) * 100:+.2f} %, t {a.get('t_wo_top2') or 0:.2f}.",
           f"**Verdict: {verdict}**", "",
           "Reading: the two best issues are PACK 2025-12 (the stock ran limit-up for days - the gain is the rally, not the discount)",
           "and BEKS 2020-12 (the right at Rp 1-2 against K 50 and a stock at 120, sold after a limit-down streak). Qualifying issues",
           "are rare (17 in 2020-26, 3 since 2023) and 28 % of exits hit a locked close. Not a sleeve; at most a forward paper watch.", "",
           "Limits: rights priced at the CLOSE (thin books; the close may not be buyable); settlement T+2 and delivery D are",
           "assumptions (D 1..3); exercise assumed possible until the right's last trading day; exercise fees beyond the broker fee",
           "are ignored; the lock rule is a proxy (no order-book depth); terms come from IDX's yearly table, which lags the current year."]
    text = "\n".join(L_)
    print(text)
    out = os.path.join(HERE, f"IDX_RIGHTS_ARB_{date.today()}.md")
    if store:
        open(out, "w", encoding="utf-8").write(text + "\n")
        with psycopg.connect(dsn) as conn:
            sid = rs.record_study(conn, STUDY, date.today(),
                                  params={"trials": list(ARMS), "n_trials_cumulative": n_trials, "fees": [FEE_BUY, FEE_SELL],
                                          "filters": {"right_value": MIN_R_VALUE, "stock_value": MIN_S_VALUE}, "split": str(SPLIT),
                                          "rev": 2, "settle": SETTLE, "lock_drop": LOCK_DROP, "max_roll": MAX_ROLL},
                                  summary=common.plain({"arms": res, "checks": checks, "neighbours_pos": nb, "verdict": verdict}),
                                  names=[], report_path=out, note=f"menu 49 rev.2 rights exercise arbitrage (execution corrected): {verdict}")
            conn.commit()
        print(f"study #{sid} stored")
    return 0


if __name__ == "__main__":
    sys.exit(main())
