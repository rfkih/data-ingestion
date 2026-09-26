#!/usr/bin/env python3
"""WHY would the gap-fade pay? A mechanism test on an independent sample (operator 2026-09-26: "okay coba lakukan 1 - 6", item 2).

Theory: short-term reversal profits are compensation for PROVIDING LIQUIDITY to impatient / forced sellers, and that
compensation rises when market-wide liquidity dries up (Nagel 2012, "Evaporating Liquidity", RFS; Campbell-Grossman-Wang 1993;
on limit-hit markets, forced selling under price limits). #382 found the gap-fade's money in capitulating names; #385 found it
in the high-volatility regime (+63 %/yr vs +6 % calm). Both come from the gap-fade's own 2025-26 trades. This test uses a
DIFFERENT event (a close-to-close loss, no opening print needed) so it reaches 2020-2024, which the gap-fade cannot.

PRE-REGISTERED 2026-09-26 before any result of this script was seen (3 hypotheses = 3 trials; cumulative 1019 + 3 = 1022):
  EVENT    a liquid name (main/development board on d-1, 60-day median value >= Rp 5 bn up to d-1, close d-1 >= 50) whose
           ADJUSTED close-to-close return on d is <= -7 % (split days cannot fake it). Buy at d's close + 1 tick, sell at d+1's
           close - 1 tick, Stockbit fees 0.10 / 0.20 % (the operator's real fills). Buying at a limit-down close fills (the
           queue is sellers).
  STATE    the filtered P(high-vol) of a 2-state HMM on COMPOSITE daily returns (#385's model, refitted here, forward pass
           only - known at d's close).
  H1 (Nagel)        mean return after HIGH-vol closes (P >= 0.5) > after calm closes: difference > 0 with Welch t >= 2.
  H2 (forced sale)  mean return when d is the 2nd+ consecutive <= -7 % day of that name > when it is the first: t >= 2.
  H3 (independence) H1's difference has the same sign in 2020-2024 alone (the years the gap-fade cannot test).
  Unit: the DAY (equal-weight mean of that day's events), so a crash day with 60 losers is one observation, not 60.
  READ     H1 + H3 = the mechanism behind the gap-fade holds on an independent sample -> the sleeve is a volatility-regime
           liquidity business (expect little in calm years; size it as such). Not a new strategy; nothing here is deployed.
READ-ONLY; one idx.study row (liquidity_mechanism).
"""
from __future__ import annotations

import os
import sys
from datetime import date

import numpy as np
import pandas as pd
import psycopg
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blackheart-ingest", "src"))
import idx_alloc_frontier as AF  # noqa: E402
import idx_risk_models as RM  # noqa: E402
from blackheart_ingest.idx import research_store as rs  # noqa: E402
from blackheart_ingest.idx.ml import common  # noqa: E402

STUDY = "liquidity_mechanism"
N_BEFORE = 1019
THR = -0.07
FEE_BUY, FEE_SELL = 0.0010, 0.0020
LIQ, MIN_PX = 5e9, 50
SPLIT = pd.Timestamp("2025-01-01")


def tick(p: np.ndarray) -> np.ndarray:
    return np.select([p < 200, p < 500, p < 2000, p < 5000], [1, 2, 5, 10], 25).astype(float)


def welch(a: np.ndarray, b: np.ndarray) -> dict:
    if len(a) < 2 or len(b) < 2:
        return {"diff": None, "t": None, "n_a": int(len(a)), "n_b": int(len(b))}
    t = stats.ttest_ind(a, b, equal_var=False)
    return {"diff": float(a.mean() - b.mean()), "t": float(t.statistic), "n_a": int(len(a)), "n_b": int(len(b)),
            "mean_a": float(a.mean()), "mean_b": float(b.mean())}


def main() -> int:
    store = "--no-store" not in sys.argv
    dsn = AF.dsn()
    with psycopg.connect(dsn) as conn:
        # v60 computed here from daily_summary.value: idx.feature_daily.value_60d_median only starts ~2023 (found on the first run,
        # which therefore had 4 event days in 2020-22 - a data gap, not a result; the definition is unchanged)
        bars = pd.read_sql("""SELECT b.code, b.trade_date, b.close, b.close * b.adj_factor AS ac, s.remarks, s.value
                                FROM idx.bar b JOIN idx.daily_summary s USING (code, trade_date)
                               WHERE b.source = 'idx' AND b.trade_date >= '2019-06-01'""", conn)
        comp = pd.read_sql("SELECT trade_date, close FROM idx.index_daily WHERE index_code = 'COMPOSITE' ORDER BY 1", conn)
    for c in ("close", "ac", "value"):
        bars[c] = pd.to_numeric(bars[c], errors="coerce")
    bars = bars.sort_values(["code", "trade_date"])
    bars["v60"] = bars.groupby("code")["value"].transform(lambda v: v.rolling(60, min_periods=40).median())
    bars["main"] = bars["remarks"].fillna("").str[4:5].isin(["1", "2"])
    P = {c: bars.pivot(index="trade_date", columns="code", values=c).sort_index() for c in ("close", "ac", "v60", "main")}
    P["main"] = P["main"].fillna(False).astype(bool)
    idx = pd.to_datetime(P["close"].index)
    for k in P:
        P[k].index = idx
    ret = P["ac"] / P["ac"].shift(1) - 1
    elig = P["main"].shift(1).fillna(False).astype(bool) & (P["v60"].shift(1) >= LIQ) & (P["close"].shift(1) >= MIN_PX)
    ev = elig & (ret <= THR)
    prev_ev = (ret.shift(1) <= THR)
    c0, c1 = P["close"], P["close"].shift(-1)
    buy = (c0 + tick(c0.to_numpy())) * (1 + FEE_BUY)
    sell = (c1 - tick(np.nan_to_num(c1.to_numpy(), nan=1.0))) * (1 - FEE_SELL)
    adj_next = (P["ac"].shift(-1) / P["ac"]) / (P["close"].shift(-1) / P["close"])     # a split between d and d+1 rescales the exit
    r = (sell * adj_next / buy - 1).where(ev & c1.notna())
    comp["trade_date"] = pd.to_datetime(comp["trade_date"])
    cr = comp.set_index("trade_date")["close"].astype(float).pct_change().dropna()
    h = RM.hmm_fit(cr.to_numpy())
    p_hi = pd.Series(h["filtered"], index=cr.index).reindex(idx)
    rows = []
    for d in idx:
        if d < pd.Timestamp("2020-01-02"):
            continue
        x = r.loc[d].dropna()
        if x.empty:
            continue
        streak = prev_ev.loc[d].reindex(x.index).fillna(False)
        rows.append({"d": d, "mean": float(x.mean()), "n": int(len(x)), "p_hi": float(p_hi.get(d, np.nan)),
                     "streak_mean": float(x[streak].mean()) if streak.any() else np.nan,
                     "first_mean": float(x[~streak].mean()) if (~streak).any() else np.nan})
    D = pd.DataFrame(rows).set_index("d")
    hi = D["p_hi"] >= 0.5
    h1 = welch(D.loc[hi, "mean"].to_numpy(), D.loc[~hi, "mean"].to_numpy())
    h2 = welch(D["streak_mean"].dropna().to_numpy(), D["first_mean"].dropna().to_numpy())
    E = D[D.index < SPLIT]
    hiE = E["p_hi"] >= 0.5
    h3 = welch(E.loc[hiE, "mean"].to_numpy(), E.loc[~hiE, "mean"].to_numpy())
    L_ = D[D.index >= SPLIT]
    hiL = L_["p_hi"] >= 0.5
    late = welch(L_.loc[hiL, "mean"].to_numpy(), L_.loc[~hiL, "mean"].to_numpy())
    passed = {"H1": bool(h1["diff"] is not None and h1["diff"] > 0 and h1["t"] >= 2), "H2": bool(h2["diff"] is not None and h2["diff"] > 0 and h2["t"] >= 2),
              "H3": (bool(h3["diff"] > 0) if h3["diff"] is not None and min(h3["n_a"], h3["n_b"]) >= 20 else None)}
    by_year = {int(y): {"days": int(len(g)), "mean": float(g["mean"].mean()), "hi_days": int((g["p_hi"] >= 0.5).sum()),
                        "hi_mean": float(g.loc[g["p_hi"] >= 0.5, "mean"].mean()) if (g["p_hi"] >= 0.5).any() else None,
                        "calm_mean": float(g.loc[g["p_hi"] < 0.5, "mean"].mean()) if (g["p_hi"] < 0.5).any() else None}
               for y, g in D.groupby(D.index.year)}
    n_trials = N_BEFORE + 3
    res = {"events": int(D["n"].sum()), "days": int(len(D)), "all_mean": float(D["mean"].mean()), "H1": h1, "H2": h2, "H3_2020_24": h3,
           "late_2025_26": late, "passed": passed, "by_year": by_year}
    f = lambda v: "-" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{v * 100:+.2f} %"  # noqa: E731
    L = [f"# Liquidity-provision mechanism behind the gap-fade - {date.today()} - 3 trials, cumulative N = {n_trials}", "",
         f"Event: liquid name, adjusted close-to-close <= {THR * 100:.0f} %; buy that close + 1 tick, sell next close - 1 tick, fees 0.10 / 0.20 %.",
         f"{res['events']:,} events on {res['days']:,} days, 2020-01 -> 2026-09. Unit = the day (equal-weight mean of its events). "
         f"All days: {f(res['all_mean'])} per day.", "",
         "| hypothesis | group A | mean A | n A | group B | mean B | n B | difference | Welch t | pass |", "|---|---|---|---|---|---|---|---|---|---|"]
    for name, v, a, b in (("H1 Nagel", h1, "high-vol close", "calm close"), ("H2 forced sale", h2, "2nd+ loss day", "first loss day"),
                          ("H3 2020-24 only", h3, "high-vol close", "calm close"), ("(context) 2025-26", late, "high-vol close", "calm close")):
        key = name.split()[0]
        L.append(f"| {name} | {a} | {f(v.get('mean_a'))} | {v['n_a']} | {b} | {f(v.get('mean_b'))} | {v['n_b']} | {f(v['diff'])} | "
                 f"{'-' if v['t'] is None else f'{v['t']:.2f}'} | {passed.get(key, '') if key in passed else ''} |")
    L += ["", "| year | days | mean per day | high-vol days | mean high-vol | mean calm |", "|---|---|---|---|---|---|"]
    for y, v in by_year.items():
        L.append(f"| {y} | {v['days']} | {f(v['mean'])} | {v['hi_days']} | {f(v['hi_mean'])} | {f(v['calm_mean'])} |")
    verdict = ("MECHANISM SUPPORTED" if passed["H1"] and passed["H3"] else "MECHANISM NOT SUPPORTED" if not passed["H1"] else "SUPPORTED ONLY IN 2025-26")
    if passed["H3"] is None:
        verdict += "; H3 UNTESTABLE (too few high-vol days in 2020-24)"
    L += ["", f"**Verdict: {verdict}** (H1 {passed['H1']}, H2 {passed['H2']}, H3 {passed['H3']}).", "",
          "## The finding this test surfaced: the event depends on the exchange's price-limit regime", "",
          "The worst daily decline of any name priced above Rp 200, by month (idx.daily_summary close / previous): about -7 % from",
          "2020-04 to 2023-05 (the COVID-era lower auto-rejection limit), -15 % from 2023-06, -25 % from 2023-09, -15 % again from",
          "2025-04. Under the -7 % regime a close <= -7 % - and the gap-fade's open <= -7 % - is mechanically almost impossible:",
          "that, not only the late density of IDX opening prints, is why the gap-fade has almost no trades before 2023-06. The",
          "sleeve exists only while the lower limit is wide. If the exchange narrows it in a future crisis (as in 2020-03), the",
          "gap-fade will not trigger at all.", "",
          "Reading of H1/H2: a close-to-close loser CONTINUES the next day (all days -2.7 %; a 2nd consecutive loss day -4.1 %,",
          "t -2.25 the wrong way): limit-down cascades run on through the next open. The gap-fade's gain (#382: +6 % in names that",
          "were already crashing) comes AFTER the cascade has gapped the open - an intraday bounce - not from providing liquidity",
          "at the close. The generic liquidity-provision (Nagel) story does not explain it on this market.", "",
          "Limits: a close-to-close loser is a cousin of the gap-down, not the same event (the gap-fade buys the OPEN); the HMM state",
          "is estimated on 2020-26 parameters (the filter is forward-only, the parameters are not); buying a limit-down close assumes",
          "a fill at the queue, which the desk's size can get."]
    text = "\n".join(L)
    print(text)
    out = os.path.join(HERE, f"IDX_LIQUIDITY_MECHANISM_{date.today()}.md")
    if store:
        open(out, "w", encoding="utf-8").write(text + "\n")
        with psycopg.connect(dsn) as conn:
            sid = rs.record_study(conn, STUDY, date.today(), params={"trials": ["H1", "H2", "H3"], "n_trials_cumulative": n_trials, "thr": THR,
                                                                     "fees": [FEE_BUY, FEE_SELL], "sources": [382, 385]},
                                  summary=common.plain({**res, "verdict": verdict}), names=[], report_path=out, note=f"liquidity-provision mechanism: {verdict}")
            conn.commit()
        print(f"study #{sid} stored")
    return 0


if __name__ == "__main__":
    sys.exit(main())
