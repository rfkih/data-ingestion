#!/usr/bin/env python3
"""The desk's trend rule on markets it has never seen - Thailand, Malaysia, Singapore (evidence plan item 5, operator 2026-09-26).

Every IDX study used IDX data; the only out-of-sample the trend rule had was IDX 2005-19 on surviving names (#46: weak). A rule
that captures a real behaviour (breakouts on volume keep going, trail the winners) should work on OTHER markets with NO change.

PRE-REGISTERED 2026-09-26 before any result of this script was seen (3 trials, one per market; cumulative 1022 + 3 = 1025):
  DATA     Yahoo daily OHLCV (split-adjusted), 2009-01-01 -> 2026-09-16, the 250 largest common stocks listed TODAY per market
           (Yahoo screener: region th/SET, my/KLS, sg/SES; quoteType EQUITY; Thai DRs and foreign-board lines dropped).
           SURVIVORS ONLY - which flatters any long rule. Hence the reading is the rule AGAINST A PLACEBO ON THE SAME DATA.
  RULE     unchanged from IDX (trend_book.py): close = 60-session high AND close > 200-session average AND volume >= 1.5 x the
           20-session median; K = 10 equal slots filled by volume ratio; bought at the next close; exit when the close <= 90 % of
           the highest close since entry, sold at the next close; no new entry while the market index < its 200-session average
           (TDEX.BK = SET50 ETF for Thailand, ^KLSE, ^STI).
  UNIVERSE liquid = the 100 names with the highest 60-session median traded value (close x volume) each day (relative, so no
           currency threshold); price >= the market's 5th percentile price that day.
  COSTS    flat 0.30 % half-spread each side + 0.10 / 0.20 % fees (the IDX assumption; local stamp duties differ).
  WINDOW   2010-01-01 -> 2026-09-16 (indicator warm-up in 2009).
  PLACEBO  the same book, universe, costs and trail-10 exit with RANDOM entries among eligible names: 50 seeds.
  PASS per market: rule Sharpe >= the placebo's 95th percentile AND the rule's mean closed trade t >= 2.0.
  READ     the rule GENERALISES if it passes in >= 2 of 3 markets; else the IDX result is not supported out of universe.
READ-ONLY; one idx.study row (trend_intl).
"""
from __future__ import annotations

import os
import pickle
import re
import sys
import time
from datetime import date

import numpy as np
import pandas as pd
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blackheart-ingest", "src"))
import idx_alloc_frontier as AF  # noqa: E402
import idx_exit as X  # noqa: E402
import idx_swing2 as S  # noqa: E402
from blackheart_ingest.idx import research_store as rs  # noqa: E402
from blackheart_ingest.idx.ml import common  # noqa: E402

STUDY = "trend_intl"
N_BEFORE = 1022
# Thailand's index (^SET.BK) is no longer served by Yahoo; the gate uses TDEX.BK (the ThaiDEX SET50 ETF, from 2009) instead -
# substituted after the first run crashed on the missing index, before any result existed
MARKETS = {"thailand": ("th", "SET", "TDEX.BK"), "malaysia": ("my", "KLS", "^KLSE"), "singapore": ("sg", "SES", "^STI")}
TOP_CAP, TOP_LIQ = 250, 100
HALF_SPREAD = 0.0030
START, END, WARM = pd.Timestamp("2010-01-01"), pd.Timestamp("2026-09-16"), "2009-01-01"
SEEDS = 50
CACHE = os.path.join(ROOT, "research-scratch", "intl")


def tickers(region: str, exch: str) -> list[str]:
    import yfinance as yf
    from yfinance import EquityQuery
    q = EquityQuery("and", [EquityQuery("eq", ["region", region]), EquityQuery("eq", ["exchange", exch])])
    out, off = [], 0
    while len(out) < TOP_CAP and off < 1500:
        r = yf.screen(q, size=250, offset=off, sortField="intradaymarketcap", sortAsc=False)
        qs = r.get("quotes", [])
        if not qs:
            break
        for x in qs:
            sym = x.get("symbol", "")
            if x.get("quoteType") != "EQUITY":
                continue
            if region == "th" and (re.search(r"\d{2}\.BK$", sym) or "-F.BK" in sym or "-R.BK" in sym):
                continue
            out.append(sym)
        off += 250
        time.sleep(1)
    return out[:TOP_CAP]


def load(market: str) -> tuple[dict[str, pd.DataFrame], pd.Series, list[str]]:
    os.makedirs(CACHE, exist_ok=True)
    f = os.path.join(CACHE, f"{market}.pkl")
    if os.path.exists(f):
        return pickle.load(open(f, "rb"))
    import yfinance as yf
    region, exch, index = MARKETS[market]
    syms = tickers(region, exch)
    frames = []
    for i in range(0, len(syms), 50):
        frames.append(yf.download(syms[i:i + 50], start=WARM, end=str(END.date() + pd.Timedelta(days=1)), auto_adjust=True, progress=False,
                                  group_by="column", threads=True))
        time.sleep(2)
    D = pd.concat(frames, axis=1)
    P = {c.lower(): D[c].copy() for c in ("Close", "High", "Low", "Volume")}
    ix = yf.download(index, start=WARM, end=str(END.date() + pd.Timedelta(days=1)), auto_adjust=True, progress=False)["Close"]
    ix = ix.iloc[:, 0] if isinstance(ix, pd.DataFrame) else ix
    out = (P, ix.astype(float), syms)
    pickle.dump(out, open(f, "wb"))
    return out


def run_market(market: str, n_trials: int) -> dict:
    P, ix, syms = load(market)
    dates = ix.dropna().index
    adj = P["close"].reindex(dates)
    vol = P["volume"].reindex(dates)
    H, L = P["high"].reindex(dates), P["low"].reindex(dates)
    v60 = (adj * vol).rolling(60, min_periods=60).median()
    rank = v60.rank(axis=1, ascending=False)
    pmin = adj.quantile(0.05, axis=1)
    uni = (rank <= TOP_LIQ) & adj.ge(pmin, axis=0) & (vol > 0) & adj.notna()
    ma200 = adj.rolling(200, min_periods=200).mean()
    vr = vol / vol.rolling(20, min_periods=20).median()
    hi = adj.rolling(60, min_periods=60).max()
    ixr = ix.reindex(dates).ffill()
    gate_off = (ixr < ixr.rolling(200, min_periods=200).mean()).to_numpy()
    entry = ((adj >= hi) & (adj > ma200) & (vr >= 1.5)).to_numpy(bool) & ~gate_off[:, None]
    m = (dates >= START) & (dates <= END)
    sl = slice(int(np.argmax(m)), int(len(m) - np.argmax(m[::-1])))
    A = adj.to_numpy(float)[sl]
    Hh, Ll = H.to_numpy(float)[sl], L.to_numpy(float)[sl]
    c_in = np.full(A.shape, HALF_SPREAD + S.FEE_BUY)
    c_out = np.full(A.shape, HALF_SPREAD + S.FEE_SELL)
    U = uni.to_numpy(bool)[sl]
    E = entry[sl] & U
    score = vr.to_numpy(float)[sl]
    rule = lambda t, j, p: 1.0 if A[t, j] <= 0.90 * p["peak"] else 0  # noqa: E731
    R, tr, open_ = X.run_book(A, Hh, Ll, c_in, c_out, E, score, rule, U)
    s = X.stats(R.copy(), tr, dates[sl], n_trials)
    rnd = []
    for k in range(SEEDS):
        Rr, trr, _ = X.run_book(A, Hh, Ll, c_in, c_out, None, None, rule, U, rng=np.random.default_rng(20260926 + k))
        rnd.append(X.stats(Rr.copy(), trr, dates[sl], n_trials)["sharpe"])
    rnd = np.array(rnd)
    ixs = ixr.loc[START:END].dropna()
    ix_cagr = float((ixs.iloc[-1] / ixs.iloc[0]) ** (252 / len(ixs)) - 1)
    passed = bool(s["sharpe"] >= np.percentile(rnd, 95) and s["tstat"] >= 2.0)
    return {"names": len(syms), "rule": {k: s[k] for k in ("n", "hit", "avg_net", "tstat", "cagr", "sharpe", "mdd", "years")},
            "placebo_sharpe_median": float(np.median(rnd)), "placebo_sharpe_p95": float(np.percentile(rnd, 95)),
            "placebo_pct": float((rnd < s["sharpe"]).mean() * 100), "index_cagr": ix_cagr, "passed": passed}


def main() -> int:
    store = "--no-store" not in sys.argv
    n_trials = N_BEFORE + len(MARKETS)
    res = {}
    for mk in MARKETS:
        res[mk] = run_market(mk, n_trials)
        r = res[mk]
        print(f"{mk}: names {r['names']}, rule n {r['rule']['n']} t {r['rule']['tstat']:.2f} CAGR {r['rule']['cagr'] * 100:+.1f} % Sharpe {r['rule']['sharpe']:.2f} "
              f"| placebo median {r['placebo_sharpe_median']:.2f} p95 {r['placebo_sharpe_p95']:.2f} (rule at pct {r['placebo_pct']:.0f}) | index {r['index_cagr'] * 100:+.1f} %", flush=True)
    wins = sum(1 for r in res.values() if r["passed"])
    verdict = "GENERALISES" if wins >= 2 else "NOT SUPPORTED out of universe"
    L = [f"# The trend rule out of universe: Thailand, Malaysia, Singapore - {date.today()} - {len(MARKETS)} trials, cumulative N = {n_trials}", "",
         "Unchanged IDX rule (60-day high / MA200 / 1.5x volume, K 10, trail 10 %, index regime gate), 2010-01 -> 2026-09, Yahoo daily, the 250",
         f"largest stocks listed today per market (survivors), liquid = top {TOP_LIQ} by 60-day median value, 0.30 % half-spread + 0.10/0.20 % fees.",
         f"Placebo = random entries, same book and exit, {SEEDS} seeds.", "",
         "| market | names | trades | hit | avg net | t | CAGR | Sharpe | mDD | placebo Sharpe median / p95 | rule pct | index CAGR | pass |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for mk, r in res.items():
        s = r["rule"]
        L.append(f"| {mk} | {r['names']} | {s['n']} | {s['hit'] * 100:.0f} % | {s['avg_net'] * 100:+.2f} % | {s['tstat']:.2f} | {s['cagr'] * 100:+.1f} % | "
                 f"{s['sharpe']:.2f} | {s['mdd'] * 100:.0f} % | {r['placebo_sharpe_median']:.2f} / {r['placebo_sharpe_p95']:.2f} | {r['placebo_pct']:.0f} | "
                 f"{r['index_cagr'] * 100:+.1f} % | {'yes' if r['passed'] else 'no'} |")
    L += ["", f"**Verdict: {verdict}** ({wins} of {len(MARKETS)} markets pass).", "",
          "Limits: survivors only (the placebo on the same names cancels most of it, not all: a trend rule buys winners, which survivors are",
          "rich in); IDX's cost model on other markets; Yahoo data quality varies (Malaysian and Singapore small caps are thin); the",
          "universe is the 250 largest companies today, not a point-in-time list."]
    text = "\n".join(L)
    print(text)
    out = os.path.join(HERE, f"IDX_TREND_INTL_{date.today()}.md")
    if store:
        open(out, "w", encoding="utf-8").write(text + "\n")
        with psycopg.connect(AF.dsn()) as conn:
            sid = rs.record_study(conn, STUDY, date.today(), params={"trials": list(MARKETS), "n_trials_cumulative": n_trials, "top_cap": TOP_CAP,
                                                                     "top_liq": TOP_LIQ, "half_spread": HALF_SPREAD, "seeds": SEEDS,
                                                                     "window": [str(START.date()), str(END.date())]},
                                  summary=common.plain({"markets": res, "wins": wins, "verdict": verdict}), names=[], report_path=out,
                                  note=f"trend rule out of universe: {verdict}")
            conn.commit()
        print(f"study #{sid} stored")
    return 0


if __name__ == "__main__":
    sys.exit(main())
