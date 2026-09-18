#!/usr/bin/env python3
"""IDX menu 15 — the trend rule before 2020 (operator, 2026-09-18: "udah kamu backtest dari tahun 2008?").

Menus 6-7 and 13-14 established the rule 60-day high / > MA200 / volume >= 1.5x / 10 % trailing stop on IDX data 2020-2026 only —
the exchange's API serves nothing earlier. Before 2020 the only prices are the Yahoo cache (research-scratch/idx/*.JK.csv): OHLCV
for 450 names THAT STILL EXIST TODAY (124 with bars in 2008, 285 in 2019). That file flatters any long rule — the names that went to
zero are not in it — so the level is generous; the fair reads are the rule against random entries on the same data (same bias) and
against the index, and the rule's behaviour through the crashes (2008, 2011, 2013, 2015, 2018). No bid/offer before 2020: the cost
model is a flat 0.30 % half-spread each side (the IDX 2020-26 average for these entries: 0.28 % in / 0.32 % out) + Stockbit fees.

PRE-REGISTERED MENU (2 trials; cumulative 375 + 2 = 377). Declared before the run; nothing tuned afterwards.
  Data: Yahoo cache, split-adjusted close/high/low/volume; trading days = the JKSE index dates.
  Universes as deployed, on adjusted prices: LIQ = 60-day median value (close x volume) >= Rp 5 bn and close >= Rp 100;
    BLUE = LIQ and value >= Rp 20 bn and close >= Rp 1,000; small = LIQ minus BLUE. (Adjusted prices sit below the nominal
    prices of the time for names that split later, so `small` is a little wider than it was.)
  Book, entry, exit, execution: exactly as menus 6-7 (K = 10, close t+1, trail 10 % from the peak close).
  Trials: rule on `small` 2005-01-01 -> 2019-12-31; rule on `LIQ` 2005-2019.
  References (not trials): random entries + trail10 on the same universe/period (seeded); JKSE buy-and-hold; the same rule on the
    Yahoo cache 2020-01-01 -> 2026-09-16 next to the IDX-data result (menu 7) = how much the survivorship + cost model flatter.
READING RULE (declared before the run): the rule HOLDS out-of-sample if, on `small` 2005-2019: >= 150 closed trades; t >= 2.0;
  CAGR >= 10 %; Sharpe >= random + 0.5; positive in >= 9 of 15 years. Otherwise it is recorded as a 2020-26 phenomenon.
  Crash read (descriptive): the book's return and drawdown inside each episode against JKSE.
READ-ONLY. INGEST_DB_DSN=... PYTHONIOENCODING=utf-8 blackheart-ingest/.venv/Scripts/python research/idx_trend_2008.py
"""
from __future__ import annotations

import glob
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
import idx_exit as X  # noqa: E402
import idx_swing2 as S  # noqa: E402

N_BEFORE = 375
K = X.K
YAHOO = os.path.join(ROOT, "research-scratch", "idx")
HALF_SPREAD = 0.0030
OOS = (pd.Timestamp("2005-01-01"), pd.Timestamp("2019-12-31"))
CAL = (pd.Timestamp("2020-01-01"), pd.Timestamp("2026-09-16"))
EPISODES = {"2008 GFC": ("2008-01-01", "2009-03-31"), "2011 EU": ("2011-07-01", "2011-10-31"), "2013 taper": ("2013-05-20", "2013-08-31"),
            "2015 EM": ("2015-04-01", "2015-09-30"), "2018 EM": ("2018-01-01", "2018-10-31"), "2020 covid": ("2020-01-01", "2020-03-31"),
            "2025 Q1": ("2025-01-01", "2025-04-30")}
ARMS = ["small|2005-2019", "LIQ|2005-2019"]
SEED = 20260918


def load_yahoo():
    jk = pd.read_csv(os.path.join(YAHOO, "_JKSE.csv"), parse_dates=["date"]).set_index("date")["close"].astype(float).sort_index()
    jk = jk[~jk.index.duplicated(keep="last")]
    dates = jk.index[(jk.index >= "2004-01-01")]
    cols = {c: {} for c in ("close", "high", "low", "volume")}
    for f in sorted(glob.glob(os.path.join(YAHOO, "*.JK.csv"))):
        code = os.path.basename(f).split(".")[0]
        df = pd.read_csv(f, parse_dates=["date"]).set_index("date").sort_index()
        df = df[~df.index.duplicated(keep="last")]
        for c in cols:
            cols[c][code] = pd.to_numeric(df[c], errors="coerce")
    P = {c: pd.DataFrame(cols[c]).reindex(dates) for c in cols}
    return P, jk.reindex(dates)


def run(A, H, L, c_in, c_out, entry, score, uni, dates, lo, hi, n_trials, rng=None):
    """Run the book on [lo, hi] only (indicators are computed on the full panel beforehand)."""
    m = (dates >= lo) & (dates <= hi)
    sl = slice(int(np.argmax(m)), int(len(m) - np.argmax(m[::-1])))
    As = A[sl]
    rule = lambda t, j, p: 1.0 if As[t, j] <= 0.90 * p["peak"] else 0  # noqa: E731
    R, tr, open_ = X.run_book(As, H[sl], L[sl], c_in[sl], c_out[sl], None if rng is not None else entry[sl], None if rng is not None else score[sl], rule, uni[sl], rng=rng)
    s = X.stats(R.copy(), tr, dates[sl], n_trials)
    s["open"] = len(open_)
    return s, R, dates[sl]


def episode_read(R, dts, jk):
    eq = (1 + R.reset_index(drop=True)).cumprod(); eq.index = dts
    out = {}
    for name, (a, b) in EPISODES.items():
        m = (dts >= a) & (dts <= b)
        if m.sum() < 5:
            continue
        e = eq[m]; j = jk[dts[m]].dropna()
        out[name] = {"book": float(e.iloc[-1] / e.iloc[0] - 1), "book_dd": float((e / e.cummax() - 1).min()),
                     "jkse": float(j.iloc[-1] / j.iloc[0] - 1) if len(j) else float("nan"), "jkse_dd": float((j / j.cummax() - 1).min()) if len(j) else float("nan")}
    return out


def main():
    P, jk = load_yahoo()
    adj, vol = P["close"], P["volume"]
    dates = adj.index
    A, H, L = adj.to_numpy(float), P["high"].to_numpy(float), P["low"].to_numpy(float)
    c_in = np.full(A.shape, HALF_SPREAD + S.FEE_BUY); c_out = np.full(A.shape, HALF_SPREAD + S.FEE_SELL)
    ma200 = adj.rolling(200, min_periods=200).mean()
    vr = vol / vol.rolling(20, min_periods=20).median()
    hi = adj.rolling(60, min_periods=60).max()
    entry = ((adj >= hi) & (adj > ma200) & (vr >= 1.5)).to_numpy(bool)
    score = vr.to_numpy(float)
    v60 = (adj * vol).rolling(60, min_periods=60).median()
    liq = (v60 >= S.LIQ) & (adj >= S.MIN_PRICE) & (vol > 0) & adj.notna()
    blue = liq & (v60 >= S.BLUE_LIQ) & (adj >= S.BLUE_PRICE)
    universes = {"small": (liq & ~blue), "LIQ": liq}
    n_trials = N_BEFORE + len(ARMS)
    res, rnd, cal, eps, counts = {}, {}, {}, {}, {}
    for u in ("small", "LIQ"):
        uni = universes[u].to_numpy(bool)
        s, R, dts = run(A, H, L, c_in, c_out, entry, score, uni, dates, *OOS, n_trials)
        res[u] = s; eps[u] = episode_read(R, dts, jk)
        rnd[u], _, _ = run(A, H, L, c_in, c_out, entry, score, uni, dates, *OOS, n_trials, rng=np.random.default_rng(SEED))
        cal[u], Rc, dtc = run(A, H, L, c_in, c_out, entry, score, uni, dates, *CAL, n_trials)
        eps[u + "_cal"] = episode_read(Rc, dtc, jk)
        counts[u] = universes[u].loc[OOS[0]:OOS[1]].sum(axis=1).groupby(universes[u].loc[OOS[0]:OOS[1]].index.year).mean().round().astype(int).to_dict()
        print(f"{u}: OOS n={s['n']} cagr={s['cagr'] * 100:+.1f}% sharpe={s['sharpe']:.2f} mdd={s['mdd'] * 100:.0f}% t={s['tstat']:.1f} | rnd sharpe {rnd[u]['sharpe']:.2f} "
              f"| cal 2020-26 cagr={cal[u]['cagr'] * 100:+.1f}% sharpe={cal[u]['sharpe']:.2f} mdd={cal[u]['mdd'] * 100:.0f}%", flush=True)
    jk_oos = jk.loc[OOS[0]:OOS[1]].dropna()
    jk_years = jk_oos.groupby(jk_oos.index.year).apply(lambda s: s.iloc[-1] / s.iloc[0] - 1)
    jk_cagr = (jk_oos.iloc[-1] / jk_oos.iloc[0]) ** (250 / len(jk_oos)) - 1
    jk_dd = (jk_oos / jk_oos.cummax() - 1).min()
    s = res["small"]
    why = []
    if s["n"] < 150:
        why.append("n<150")
    if s["tstat"] < 2.0:
        why.append("t<2")
    if s["cagr"] < 0.10:
        why.append("cagr<10%")
    if s["sharpe"] < rnd["small"]["sharpe"] + 0.5:
        why.append("vs random")
    if sum(1 for v in s["years"].values() if v > 0) < 9:
        why.append("years<9/15")
    verdict = "HOLDS" if not why else "does not hold: " + ",".join(why)

    def yrs(d):
        return " ".join(f"{y % 100:02d}:{v * 100:+.0f}" for y, v in sorted(d.items()))

    def row(label, s, extra=""):
        return (f"| {label} | {s['n']} | {s['hold']:.0f} | {s['hit'] * 100:.0f} % | {s['avg_net'] * 100:+.2f} % | {s['payoff']:.2f} | {s['tstat']:.1f} | "
                f"{s['cagr'] * 100:+.1f} % | {s['sharpe']:.2f} | {s['mdd'] * 100:.0f} % | {yrs(s['years'])} | {extra} |")
    hdr = ["| arm | trades | hold d | hit | avg net | payoff | t | CAGR | Sharpe | mDD | years | note |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    lines = [f"# IDX menu 15 — the trend rule 2005-2019 on the Yahoo cache — {date.today()} — {len(ARMS)} trials, cumulative N = {n_trials}", "",
             f"Yahoo split-adjusted OHLCV, 450 surviving names; K = {K}, close t+1, flat {HALF_SPREAD * 100:.2f} % half-spread + fees {S.FEE_BUY * 100:.2f}/{S.FEE_SELL * 100:.2f} %. "
             f"JKSE {OOS[0].year}-{OOS[1].year}: CAGR {jk_cagr * 100:+.1f} %, mDD {jk_dd * 100:.0f} %, years {yrs(jk_years.to_dict())}", "",
             f"Names in universe per year (mean): small {counts['small']} | LIQ {counts['LIQ']}", "",
             "## Out of sample 2005-2019", "", *hdr,
             row("rule 60/10/1.5 | small", res["small"], f"**{verdict}**"), row("random + trail10 | small", rnd["small"], "reference"),
             row("rule 60/10/1.5 | LIQ", res["LIQ"]), row("random + trail10 | LIQ", rnd["LIQ"], "reference"), "",
             "## Calibration 2020-2026: same rule on the Yahoo cache vs the IDX data (menu 7)", "", *hdr,
             row("Yahoo | small", cal["small"], "IDX data: +29.9 %, Sharpe 1.34, mDD -30 %, 495 trades"),
             row("Yahoo | LIQ", cal["LIQ"], "IDX data: +18.9 %, Sharpe 0.92, mDD -36 %, 480 trades"), "",
             "## Crash episodes (book vs JKSE, `small`)", "", "| episode | book | book worst DD | JKSE | JKSE worst DD |", "|---|---|---|---|---|"]
    for name in EPISODES:
        e = eps["small"].get(name) or eps["small_cal"].get(name)
        if e:
            lines.append(f"| {name} | {e['book'] * 100:+.0f} % | {e['book_dd'] * 100:.0f} % | {e['jkse'] * 100:+.0f} % | {e['jkse_dd'] * 100:.0f} % |")
    lines += ["", f"Reading rule applied as declared: the rule **{verdict}** out of sample on `small` 2005-2019.", "",
              "Limits: survivorship (only names listed today; delisted losers absent — the level is generous, random-on-the-same-file is the fair",
              "comparison); price thresholds on split-adjusted prices; flat spread instead of quotes; Rp 5 bn/day is a higher real bar in 2005-2012",
              "than today (thinner universe); no dividends; positions open at a period end are marked, not counted."]
    text = "\n".join(lines); print(text)
    out = os.path.join(HERE, f"IDX_TREND_2008_{date.today().isoformat()}.md")
    open(out, "w", encoding="utf-8").write(text + "\n"); print("wrote", out)
    from blackheart_ingest.idx import research_store as rs
    with psycopg.connect(os.environ["INGEST_DB_DSN"]) as conn:
        sid = rs.record_study(conn, "trend_2008", OOS[1].date(), params={"trials": ARMS, "n_trials_cumulative": n_trials, "half_spread": HALF_SPREAD, "K": K, "oos": [str(OOS[0].date()), str(OOS[1].date())]},
                              summary={"results": res, "random": rnd, "calibration": cal, "episodes": eps, "counts": counts, "verdict": verdict,
                                       "jkse": {"cagr": float(jk_cagr), "mdd": float(jk_dd), "years": {int(y): float(v) for y, v in jk_years.items()}}},
                              names=[], report_path=out, note=verdict)
        print("study", sid)


if __name__ == "__main__":
    main()
