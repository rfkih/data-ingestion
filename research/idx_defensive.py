#!/usr/bin/env python3
"""IDX menu 44 - DEFENSIVE CARRY SLEEVE (low volatility + dividend carry) as its OWN book, for BREADTH (2026-09-26).

Operator: one more strategy with a DIFFERENT return driver than the four sleeves (gap-fade, trend, ML 5-day rank, annual value -
all price momentum / reversal / value bets). Low volatility (Frazzini-Pedersen BAB, Blitz-van Vliet; strong in EM) combined with
dividend carry. Its job is to lower the combined book's drawdown per unit of return, not to have the highest CAGR.
Not a repeat of #130 (IDX_FACTOR_BOOK): there low vol was a RANK INSIDE the value book (and diluted it); here it is a separate book.

PRE-REGISTERED (written before any result; 8 counted trials, cumulative N_BEFORE = 967 -> 975; trial ids 968..975)
Data (read fresh from the DB; no price caches): idx.bar source 'idx' 2020-01-02 -> latest, CLOSES ONLY (idx.bar.open holds Yahoo
  opens), adjusted close A = close x adj_factor (split-adjusted only, repaired 2026-09-26); idx.daily_summary closing bid/offer,
  remarks (board), listed_shares; idx.dividend cash amount_per_share (Yahoo secondary source, split-adjusted to the current share
  basis - checked on BBCA 2020: 91 = 455 / 5) credited on the ex-date (next trading day if not one), 10 % final tax;
  idx.fundamental point in time by published_at (the ML features' join: latest report with months > 0 published on/before the
  signal day); idx.index_daily COMPOSITE / LQ45 / IDXHIDIV20 (price indices).
Universe on signal day s (the close BEFORE the rebalance day): 60-day median traded value (idx.bar value, min 40 obs) >= Rp 5 bn,
  close >= Rp 100, traded on s, board ON THE DAY Utama/Pengembangan (daily_summary.remarks digit 1/2, idx_swing2.pit_board_mask),
  realised vol available (>= 200 of 252 / >= 100 of 126 daily log returns of A).
Rebalance: first trading day of Feb / May / Aug / Nov (quarterly; offset from the value book's May-only annual date is kept only
  partly - May coincides; reason: the operator's stated calendar, and a quarterly book cannot avoid May without breaking the
  3-month spacing). Signal at close s, trade at the close of the rebalance day t = s + 1: sells at the closing BID (close - 1 tick
  if none), buys at the closing OFFER (close + 1 tick if none), Stockbit fees 0.10 % buy / 0.20 % sell, lots of 100 (rounded to
  the NEAREST lot, cash permitting). Equal weight: target NAV / N; leavers sold; continuing names re-sized only if off target by
  > 25 %; a name with no trade on t is carried and sold on its next traded day; suspended names marked at their last close.
  Cash earns 0. First rebalance 2021-02-01 (252-day vol needs a year of idx.bar), end = latest bar.
Arms (N = 20 names):
  968 D1 low-vol      : the 20 lowest 252-day realised vol.
  969 D2 low-vol+carry: the lowest-vol HALF of the universe, then the 20 highest trailing-12-month dividend yield
                        (sum of amount_per_share with ex_date in (s - 365 d, s] / A_s); if < 20 names have a yield > 0 the rest
                        are filled by lowest vol.
  970 D3 D2 + quality : D2's low-vol half minus names whose latest point-in-time report (published <= s, <= 400 days old) shows
                        net profit <= 0 ('profitable' = 0) or CFO <= 0 ('cfo_pos' = 0; financials exempt from the CFO test - bank
                        CFO swings with loans); names without such a report are KEPT (share reported); then top 20 by yield.
  Neighbours, all on D3 (the full specification; declared as the host before the run):
  971 D3 with 126-day vol    972 D3 with 10 names    973 D3 with 30 names    974 D3 monthly (first trading day of every month)
  975 D1 long history 2010-02 -> 2019-12 on the Yahoo cache research-scratch/idx/*.JK.csv (450 names THAT STILL EXIST TODAY =
      SURVIVORSHIP-BIASED, label it), price only (no dividend history), flat 0.30 % half-spread + fees, fractional shares, liquidity
      from close x volume, no board filter; run through 2020-12 for the 2020-03 crash read. D2/D3 cannot be run before 2020
      (idx.dividend starts 2016-17, fundamentals 2020).
Capital: standalone at Rp 20 M (primary) and Rp 200 M (reported). Benchmarks on the sleeve window: COMPOSITE total-return PROXY
  (price + cap-weighted cash dividends from idx.dividend x listed_shares / market cap, untaxed; understates if Yahoo misses events),
  COMPOSITE / LQ45 / IDXHIDIV20 price.
Combo: the deployed book (#192 variant d, 33.8 % / 1.83 / -17.9 %, 2022-01 -> 2026-09-16), NAV recreated exactly as
  research/idx_fe_drawdown.py does (idx_engine_fix.engine_attr on tmp/ml_strategy_cache.pkl + tmp/exit_cache_pit.pkl, no study row).
  Blend = fixed capital share w in {20 %, 33 %} of a Rp 20 M total in the sleeve (sleeve simulated AT ITS OWN CAPITAL w x Rp 20 M,
  so lots bind), rest in the combo scaled down; shares reset to w at every sleeve rebalance day (drift in between; transfer cost
  ignored). Reported too: the blend with the sleeve at w x Rp 200 M (lots barely bind).
READING RULE (breadth). An arm QUALIFIES if ALL hold:
  (a) standalone (Rp 20 M) net CAGR > COMPOSITE TR-proxy CAGR on the same window, and Sharpe >= COMPOSITE TR Sharpe + 0.2 in BOTH
      halves of the sleeve window (split at its calendar midpoint);
  (b) daily-return correlation with the combo (2022-01 -> 2026-09-16) < 0.5;
  (c) at w = 20 % AND w = 33 %: blend Sharpe >= combo Sharpe AND blend mDD shallower by >= 2 pp, in BOTH halves of the combo window
      (calendar midpoint, as idx_construction.halves), AND the planning-drawdown bootstrap 3-year 1-in-10 drawdown is shallower than
      the combo's. Bootstrap = idx_fe_drawdown's (stationary 20-day blocks, 4,000 paths, seed 7, demeaned daily log returns re-drifted),
      the SAME block draws for combo and blend; combo drift = its backtest drift x 0.5646 (FE-3 planning ratio), sleeve drift = its
      backtest CAGR on the combo window x 0.5 (FE-3's 33-53 % haircut, rounded), blend drift = the capital-weighted mix;
  plus placebo: arm Sharpe >= 95th pct of 200 random 20-name books from the same liquid universe at the same rebalance dates (same
      engine, Rp 20 M); neighbours: >= 3/4 D3 neighbours agree (agree = (a) on the full window [CAGR > COMP TR, Sharpe >= COMP + 0.2],
      (b), and the 20 % blend's full-window Sharpe >= combo with mDD shallower by >= 2 pp) - D1/D2 have no neighbours run, so
      they can at most be PARTIAL; costs x 1.5 (spread and fees) keep (a)-full and the 20 % blend full-window test;
      long history (975): D1 2010-2019 Sharpe >= JKSE price Sharpe + 0.2 and mDD shallower than JKSE's - a fail downgrades any
      QUALIFIES to PARTIAL (the low-vol leg is shared by every arm). DSR at cumulative N 975 reported, not gating.
  PARTIAL: (a), (b) and (c) hold on the full window but one half or one robustness item fails. CLOSED otherwise.
Also reported: crash behaviour (2020-03 from 975; 2024-09-19 -> 2025-04-08 drawdown; 2026-01-27 -> 02-02), turnover, overlap with
the value book's (#66 strict composite, May) holdings, dividend coverage check (idx.fundamental dividends_paid vs idx.dividend).
READ-ONLY on the DB except ONE idx.study row ('defensive_carry'). Run:
  set -a; . blackheart-ingest/idx-local.env; set +a; blackheart-ingest/.venv/Scripts/python research/idx_defensive.py
Env: DEF_NOSTORE=1 skips the study row; DEF_PLACEBO (200).
"""
from __future__ import annotations

import glob
import json
import os
import pickle
import sys
from datetime import date

import numpy as np
import pandas as pd
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blackheart-ingest", "src"))
import idx_swing2 as S  # noqa: E402
from blackheart_ingest.idx import research_store as rs  # noqa: E402
from blackheart_ingest.idx.ml import common  # noqa: E402

STUDY = "defensive_carry"
N_BEFORE = 967
TRIALS = {968: "D1", 969: "D2", 970: "D3", 971: "D3_vol126", 972: "D3_n10", 973: "D3_n30", 974: "D3_monthly", 975: "D1_long_2010_2019"}
N_AFTER = max(TRIALS)
FEE_BUY, FEE_SELL, TAX, LOT = 0.0010, 0.0020, 0.10, 100
LIQ, MIN_PRICE = 5e9, 100
FIRST_REB = pd.Timestamp("2021-02-01")
N_PLACEBO = int(os.environ.get("DEF_PLACEBO", "200"))
SEED = 44
PLAN_RATIO = (8.6 + 6.0 + 5.4) / (12.8 + 12.7 + 9.8)          # FE-3 deployed-size posterior/raw ratio (idx_fe_drawdown)
SLEEVE_HAIRCUT = 0.5
COMBO_PKL = os.path.join(ROOT, "tmp", "defensive_combo_nav.pkl")
FE_NAV_PKL = os.path.join(ROOT, "tmp", "fe_drawdown_nav.pkl")
YAHOO = os.path.join(ROOT, "research-scratch", "idx")
OUT = os.path.join(HERE, "IDX_DEFENSIVE_2026-09-26.md")
FIN_SECTORS = {"G. Financials", "8. Finance"}
CRASHES = {"2020-03 covid": ("2020-02-19", "2020-03-24"), "2024-09 -> 2025-04 drawdown": ("2024-09-19", "2025-04-08"),
           "2026-01-27 -> 02-02": ("2026-01-26", "2026-02-02")}


def log(*a):
    print(*a, flush=True)


def dsn() -> str:
    return os.environ["INGEST_DB_DSN"]


def stats(nav: pd.Series) -> dict:
    nav = nav.dropna()
    r = nav.pct_change().fillna(0.0)
    yrs = max((nav.index[-1] - nav.index[0]).days / 365.25, 1e-9)
    eq = nav / nav.iloc[0]
    by = nav.groupby(nav.index.year).agg(["first", "last"])
    prev = None
    byy = {}
    for y, v in by.iterrows():
        base = prev if prev is not None else v["first"]
        byy[int(y)] = float(v["last"] / base - 1)
        prev = v["last"]
    return {"cagr": float(eq.iloc[-1] ** (1 / yrs) - 1), "sharpe": float(r.mean() / r.std() * np.sqrt(252)) if r.std() > 0 else 0.0,
            "mdd": float((eq / eq.cummax() - 1).min()), "vol": float(r.std() * np.sqrt(252)), "by_year": byy, "final": float(nav.iloc[-1])}


def halves(nav: pd.Series, lo=None, hi=None):
    nav = nav.dropna()
    mid = nav.index[0] + (nav.index[-1] - nav.index[0]) / 2
    return [stats(nav[nav.index <= mid]), stats(nav[nav.index > mid])], mid


def deflated_sharpe(r, n_trials):
    import idx_foreign_gate as FG
    return FG.deflated_sharpe(np.asarray(r, float), n_trials)


# ------------------------------------------------------------------ data --------------------------------------------------------
def load():
    with psycopg.connect(dsn()) as conn:
        q = lambda sql, p=(): pd.read_sql(sql, conn, params=p)  # noqa: E731
        bars = q("""SELECT b.code, b.trade_date, b.close::float8 close, b.adj_factor::float8 adj_factor, b.volume::float8 volume, b.value::float8 value,
                           s.bid::float8 bid, s.offer::float8 offer, s.remarks, s.listed_shares::float8 ls
                      FROM idx.bar b LEFT JOIN idx.daily_summary s USING (code, trade_date)
                     WHERE b.source = 'idx' AND b.trade_date >= '2020-01-01'""")
        div = q("SELECT code, ex_date, amount_per_share::float8 amt FROM idx.dividend WHERE kind = 'cash' AND amount_per_share > 0")
        fund = q("""SELECT code, published_at::date pub, period_end, months, net_profit::float8 np, cfo::float8 cfo, dividends_paid::float8 dp
                      FROM idx.fundamental WHERE published_at IS NOT NULL AND months > 0 ORDER BY code, published_at""")
        listing = q("SELECT code, sector FROM idx.listing")
        ix = q("SELECT index_code, trade_date, close::float8 close FROM idx.index_daily WHERE index_code IN ('COMPOSITE','LQ45','IDXHIDIV20') AND trade_date >= '2020-01-01'")
    bars["trade_date"] = pd.to_datetime(bars["trade_date"])
    return bars, div, fund, listing, ix


def build_panel(bars, div):
    pv = lambda c: bars.pivot(index="trade_date", columns="code", values=c).sort_index()  # noqa: E731
    C = pv("close")
    dates, codes = C.index, C.columns
    AF = pv("adj_factor").reindex(index=dates, columns=codes)
    A = C * AF.fillna(1.0)
    VOL = pv("volume").reindex(index=dates, columns=codes)
    VAL = pv("value").reindex(index=dates, columns=codes)
    BID = pv("bid").reindex(index=dates, columns=codes)
    OFF = pv("offer").reindex(index=dates, columns=codes)
    LS = pv("ls").reindex(index=dates, columns=codes)
    board = S.pit_board_mask(bars, dates, codes)
    traded = (VOL > 0) & C.notna()
    v60 = VAL.where(traded).rolling(60, min_periods=40).median()
    liq = (v60 >= LIQ) & (C >= MIN_PRICE) & traded & board
    lr = np.log(A.ffill()).diff()
    lr = lr.where(traded & traded.shift(1, fill_value=False))            # only returns between two traded days
    vol252 = lr.rolling(252, min_periods=200).std() * np.sqrt(252)
    vol126 = lr.rolling(126, min_periods=100).std() * np.sqrt(252)
    # dividends on the ex-date (next trading day if the ex-date is not one), per current share
    D = pd.DataFrame(0.0, index=dates, columns=codes)
    dv = div[div["code"].isin(set(codes))].copy()
    dv["ex_date"] = pd.to_datetime(dv["ex_date"])
    pos = dates.searchsorted(dv["ex_date"])
    keep = (pos < len(dates)) & (dv["ex_date"] >= dates[0]).to_numpy()      # pre-panel ex-dates must not land on day 0
    dvp, pos = dv[keep], pos[keep]
    for (code, amt), p in zip(dvp[["code", "amt"]].itertuples(index=False, name=None), pos):
        D.iat[p, codes.get_loc(code)] += amt
    # trailing 12-month dividend per current share at the close of each day: ex_date in (d - 365 d, d]
    ttm = pd.DataFrame(0.0, index=dates, columns=codes)
    for code, g in dv.groupby("code"):
        ex = g["ex_date"].to_numpy("datetime64[D]")
        amt = g["amt"].to_numpy(float)
        dd = dates.to_numpy("datetime64[D]")
        cs = np.concatenate([[0.0], np.cumsum(amt[np.argsort(ex)])])
        exs = np.sort(ex)
        hi = np.searchsorted(exs, dd, side="right")
        lo = np.searchsorted(exs, dd - np.timedelta64(365, "D"), side="right")
        ttm[code] = cs[hi] - cs[lo]
    dy = ttm / A
    return {"dates": dates, "codes": codes, "C": C, "AF": AF, "A": A, "VOL": VOL, "BID": BID, "OFF": OFF, "LS": LS, "traded": traded,
            "liq": liq, "vol252": vol252, "vol126": vol126, "D": D, "dy": dy, "v60": v60}


def gate_fail(fund, listing, codes, s):
    """Codes whose latest point-in-time report (published <= s, <= 400 d old) shows net profit <= 0 or CFO <= 0 (financials exempt
    from CFO). Returns (fail set, number of codes with a usable report)."""
    F = fund[(pd.to_datetime(fund["pub"]) <= s) & (pd.to_datetime(fund["pub"]) > s - pd.Timedelta(days=400))]
    last = F.sort_values("pub").groupby("code").tail(1).set_index("code")
    fin = set(listing.loc[listing["sector"].isin(FIN_SECTORS), "code"])
    fail = set()
    for code in codes:
        if code not in last.index:
            continue
        r = last.loc[code]
        if pd.notna(r["np"]) and r["np"] <= 0:
            fail.add(code)
        elif code not in fin and pd.notna(r["cfo"]) and r["cfo"] <= 0:
            fail.add(code)
    return fail, sum(c in last.index for c in codes)


def reb_days(dates, monthly=False, start=FIRST_REB, months=(2, 5, 8, 11)):
    out = []
    s = pd.Series(dates, index=dates)
    for (y, m), g in s.groupby([dates.year, dates.month]):
        if (monthly or m in months) and g.iloc[0] >= start:
            out.append(g.iloc[0])
    return out


def select(P, fund, listing, arm, s, n=20, volwin=252, diag=None):
    liq = P["liq"].loc[s]
    vol = (P["vol252"] if volwin == 252 else P["vol126"]).loc[s]
    u = vol[liq & vol.notna()].sort_values()
    if arm == "D1":
        return list(u.index[:n])
    half = u.iloc[: max(len(u) // 2, n)]
    if arm == "D3":
        fail, have = gate_fail(fund, listing, half.index, s)
        if diag is not None:
            diag.append({"s": str(s.date()), "half": len(half), "have_report": have, "failed": len(fail)})
        half = half[~half.index.isin(fail)]
    dy = P["dy"].loc[s].reindex(half.index).fillna(0.0)
    pos = dy[dy > 0].sort_values(ascending=False)
    pick = list(pos.index[:n])
    if len(pick) < n:
        pick += [c for c in half.index if c not in pick][: n - len(pick)]
    return pick


# ------------------------------------------------------------------ engine ------------------------------------------------------
def simulate(P, targets: dict, capital: float, cost_mult: float = 1.0, end=None):
    """targets: {rebalance day t: [codes]} chosen at the close of t-1. Returns NAV series (from the first rebalance day), trade log,
    holdings after each rebalance."""
    dates, codes = P["dates"], P["codes"]
    cidx = {c: i for i, c in enumerate(codes)}
    C = P["C"].to_numpy(float)
    AF = P["AF"].ffill().to_numpy(float)
    A = P["A"].ffill().to_numpy(float)
    TRD = P["traded"].to_numpy(bool)
    BID, OFF = P["BID"].to_numpy(float), P["OFF"].to_numpy(float)
    D = P["D"].to_numpy(float)
    tick = S.tick
    fb, fs = FEE_BUY * cost_mult, FEE_SELL * cost_mult
    t_of = {d: i for i, d in enumerate(dates)}
    reb = {t_of[d]: v for d, v in targets.items() if d in t_of}
    t0 = min(reb)
    t1 = len(dates) if end is None else int(dates.searchsorted(pd.Timestamp(end), side="right"))
    cash = capital
    q: dict[int, float] = {}          # current-basis shares
    pending: set[int] = set()
    nav = np.full(len(dates), np.nan)
    trades, holds = [], {}

    def px_out(t, j):
        c = C[t, j]
        b = BID[t, j] if (BID[t, j] > 0 and BID[t, j] <= c) else c - tick(c)
        return c - cost_mult * (c - b)

    def px_in(t, j):
        c = C[t, j]
        o = OFF[t, j] if (OFF[t, j] > 0 and OFF[t, j] >= c) else c + tick(c)
        return c + cost_mult * (o - c)

    def sell(t, j, frac=1.0, lots=None):
        nonlocal cash
        raw_held = q[j] * AF[t, j]
        sh = raw_held if lots is None else min(raw_held, lots * LOT)
        proceeds = sh * px_out(t, j) * (1 - fs)
        cash += proceeds
        q[j] -= sh / AF[t, j]
        trades.append((t, codes[j], -sh * C[t, j]))
        if q[j] <= 1e-9 or lots is None:
            q.pop(j, None)

    def buy(t, j, value):
        nonlocal cash
        p = px_in(t, j) * (1 + fb)
        lots = int(round(value / (p * LOT)))
        while lots > 0 and lots * LOT * p > cash:
            lots -= 1
        if lots < 1:
            return
        cash -= lots * LOT * p
        q[j] = q.get(j, 0.0) + lots * LOT / AF[t, j]
        trades.append((t, codes[j], lots * LOT * C[t, j]))

    for t in range(t0, t1):
        for j in list(q):                                      # dividends (ex-date), after tax
            if D[t, j] > 0:
                cash += q[j] * D[t, j] * (1 - TAX)
        for j in list(pending):                                # leavers that could not trade on their rebalance day
            if j not in q:
                pending.discard(j)
            elif TRD[t, j]:
                sell(t, j)
                pending.discard(j)
        if t in reb:
            want = [cidx[c] for c in reb[t] if c in cidx]
            ws = set(want)
            for j in list(q):
                if j not in ws:
                    if TRD[t, j]:
                        sell(t, j)
                    else:
                        pending.add(j)
            navn = cash + sum(q[j] * A[t, j] for j in q)
            tgt = navn / max(len(want), 1)
            for j in want:                                     # trims first (raise cash), then buys
                if j in q and TRD[t, j]:
                    v = q[j] * A[t, j]
                    if v > 1.25 * tgt:
                        sell(t, j, lots=int(round((v - tgt) / (C[t, j] * LOT))))
            for j in want:
                if not TRD[t, j] or C[t, j] <= 0:
                    continue
                v = q[j] * A[t, j] if j in q else 0.0
                if j not in q:
                    buy(t, j, tgt)
                elif v < 0.75 * tgt:
                    buy(t, j, tgt - v)
            holds[dates[t]] = sorted(codes[j] for j in q)
        nav[t] = cash + sum(q[j] * A[t, j] for j in q if np.isfinite(A[t, j]))
    s = pd.Series(nav[t0:t1], index=dates[t0:t1])
    return s, trades, holds


def turnover(nav, trades, dates):
    if not trades:
        return 0.0
    tv = pd.Series([abs(x[2]) for x in trades], index=[dates[x[0]] for x in trades])
    yrs = (nav.index[-1] - nav.index[0]).days / 365.25
    return float(tv.sum() / 2 / nav.mean() / yrs)


# ------------------------------------------------------------------ combo -------------------------------------------------------
def combo_nav():
    """#192 variant (d) NAV exactly as research/idx_fe_drawdown.py step 1 (no study row)."""
    if os.path.exists(COMBO_PKL) and os.environ.get("DEF_REUSE_COMBO"):
        return pickle.load(open(COMBO_PKL, "rb"))
    os.environ["IDX_BOARD_MODE"] = "pit"
    import idx_engine_fix as F
    from idx_engine_fix import CR, FG, K, M
    d = FG.dsn()
    Pm = pickle.load(open(F.ML_CACHE, "rb"))
    Pm = Pm[(Pm["d"] >= "2021-06-01") & (Pm["d"] <= CR.END)].copy()
    dates = M.wide(Pm, "close").index
    codes = M.wide(Pm, "close").columns
    g = lambda c: M.wide(Pm, c).reindex(index=dates, columns=codes)  # noqa: E731
    A, raw = g("ac").to_numpy(float), g("close").to_numpy(float)
    offer, bid = np.nan_to_num(g("offer").to_numpy(float)), np.nan_to_num(g("bid").to_numpy(float))
    liq = g("liq").fillna(False).astype(bool).to_numpy()
    ml = K.ml_ens_trades(Pm, dates, codes, A, raw, offer, bid, liq)
    del Pm
    gap, _ = K.gap_events(d, dates)
    cache, board, legacy = F.VARIANTS["d_fixed"]
    cs = set(codes)
    tr = [dict(y, tag="p", frac=1.0) for y in CR.trend_trades(d, dates, cache=cache, board=board, legacy_shift=legacy) if y["code"] in cs]
    nav, _, _ = F.engine_attr(dates, codes, A, raw, offer, bid, ml + tr, gap)
    pickle.dump(nav, open(COMBO_PKL, "wb"))
    return nav


def blend(combo: pd.Series, sleeve: pd.Series, w: float, resets) -> pd.Series:
    idx = combo.index.intersection(sleeve.index)
    rc = combo.reindex(idx).pct_change().fillna(0.0).to_numpy()
    rs_ = sleeve.reindex(idx).ffill().pct_change().fillna(0.0).to_numpy()
    rset = set(pd.DatetimeIndex(resets))
    vc, vs = 1 - w, w
    out = np.empty(len(idx))
    for i, d in enumerate(idx):
        if i > 0:
            vc *= 1 + rc[i]
            vs *= 1 + rs_[i]
        if d in rset:
            tot = vc + vs
            vc, vs = (1 - w) * tot, w * tot
        out[i] = vc + vs
    return pd.Series(out, index=idx)


def mdd_path(x):
    c = np.cumsum(x)
    peak = np.maximum.accumulate(np.concatenate([[0], c]))[1:]
    return np.min(np.exp(c - peak) - 1)


def boot_draws(n_obs, years=3, n=4000, block=20, seed=7, T=245):
    rng = np.random.default_rng(seed)
    L = years * T
    out = []
    for _ in range(n):
        idx = []
        while len(idx) < L:
            s = rng.integers(0, n_obs)
            idx.extend(range(s, min(s + block, n_obs)))
        out.append(np.array(idx[:L]))
    return out


def plan_dd(nav: pd.Series, cagr_plan: float, draws, T=245):
    r = np.log(nav).diff().dropna().to_numpy()
    x = r - r.mean() + np.log(1 + cagr_plan) / T
    d = np.array([mdd_path(x[ix]) for ix in draws])
    return {"median": float(np.median(d)), "p25": float(np.percentile(d, 25)), "p10": float(np.percentile(d, 10)), "p5": float(np.percentile(d, 5))}


# ------------------------------------------------------------------ benchmarks ----------------------------------------------------
def benchmarks(P, bars, ix):
    I = ix.pivot(index="trade_date", columns="index_code", values="close")
    I.index = pd.to_datetime(I.index)
    I = I.reindex(P["dates"]).ffill()
    # cap-weighted cash dividends: per raw share = amount (current basis) / adj_factor
    mcap = (P["C"] * P["LS"]).sum(axis=1)
    divcash = (P["D"] / P["AF"].ffill() * P["LS"].ffill()).sum(axis=1)
    r = I["COMPOSITE"].pct_change() + divcash / mcap.shift(1)
    tr = (1 + r.fillna(0.0)).cumprod() * I["COMPOSITE"].iloc[0]
    yld = divcash.groupby(divcash.index.year).sum() / mcap.groupby(mcap.index.year).mean()
    return {"COMPOSITE_TR": tr, "COMPOSITE": I["COMPOSITE"], "LQ45": I["LQ45"], "IDXHIDIV20": I["IDXHIDIV20"]}, {int(k): float(v) for k, v in yld.items()}


def dividend_coverage(fund, div, P):
    """FY reports (months = 12) with dividends paid != 0 in the CFO statement vs a Yahoo event within 15 months of period end,
    restricted to names that were liquid at any time."""
    liq_names = set(P["codes"][P["liq"].any(axis=0).to_numpy()])
    F = fund[(fund["months"] == 12) & fund["dp"].notna() & (fund["dp"] != 0) & fund["code"].isin(liq_names)].drop_duplicates(["code", "period_end"])
    dv = div.copy()
    dv["ex_date"] = pd.to_datetime(dv["ex_date"])
    have = 0
    for r in F.itertuples():
        pe = pd.Timestamp(r.period_end)
        g = dv[(dv["code"] == r.code) & (dv["ex_date"] > pe) & (dv["ex_date"] <= pe + pd.DateOffset(months=15))]
        have += len(g) > 0
    F2 = fund[(fund["months"] == 12) & fund["dp"].notna() & (fund["dp"] == 0) & fund["code"].isin(liq_names)].drop_duplicates(["code", "period_end"])
    return {"fy_paid": len(F), "fy_paid_with_yahoo_event": have, "share": have / max(len(F), 1), "fy_zero_paid": len(F2),
            "years": sorted({pd.Timestamp(x).year for x in F["period_end"]})}


# ------------------------------------------------------------------ long history (Yahoo survivors) ------------------------------
def long_history(n=20, n_placebo=N_PLACEBO):
    jk = pd.read_csv(os.path.join(YAHOO, "_JKSE.csv"), parse_dates=["date"]).set_index("date")["close"].astype(float).sort_index()
    jk = jk[~jk.index.duplicated(keep="last")]
    dates = jk.index[(jk.index >= "2008-06-01") & (jk.index <= "2020-12-31")]
    cols = {"close": {}, "volume": {}}
    for f in sorted(glob.glob(os.path.join(YAHOO, "*.JK.csv"))):
        code = os.path.basename(f).split(".")[0]
        df = pd.read_csv(f, parse_dates=["date"]).set_index("date").sort_index()
        df = df[~df.index.duplicated(keep="last")]
        for c in cols:
            cols[c][code] = pd.to_numeric(df[c], errors="coerce")
    Cc = pd.DataFrame(cols["close"]).reindex(dates)
    V = pd.DataFrame(cols["volume"]).reindex(dates)
    traded = (V > 0) & Cc.notna()
    v60 = (Cc * V).where(traded).rolling(60, min_periods=40).median()
    liq = (v60 >= LIQ) & (Cc >= MIN_PRICE) & traded
    lr = np.log(Cc.ffill()).diff().where(traded & traded.shift(1, fill_value=False))
    vol = lr.rolling(252, min_periods=200).std()
    rebs = reb_days(dates, start=pd.Timestamp("2010-02-01"))
    A = Cc.ffill().to_numpy(float)
    codes = Cc.columns
    half, fee_b, fee_s = 0.003, FEE_BUY, FEE_SELL

    t_of = {d: i for i, d in enumerate(dates)}
    rset = {t_of[d] for d in rebs}
    t_start = t_of[rebs[0]]

    def run(pick_fn):
        """Fractional equal-weight book, rebalanced to equal weight at each rebalance close; cash (1 - sum w) earns 0."""
        w = np.zeros(len(codes))
        nav, out = 1.0, []
        for t in range(t_start, len(dates)):
            if t > t_start:
                ret = np.nan_to_num(A[t] / A[t - 1] - 1)
                g = float((w * ret).sum())
                nav *= 1 + g
                w = w * (1 + ret) / (1 + g)
            if t in rset:
                pick = pick_fn(dates[t - 1])
                new = np.zeros(len(codes))
                for c in pick:
                    new[codes.get_loc(c)] = 1 / len(pick)
                cost = (np.clip(w - new, 0, None) * (half + fee_s)).sum() + (np.clip(new - w, 0, None) * (half + fee_b)).sum()
                nav *= 1 - cost
                w = new
            out.append(nav)
        return pd.Series(out, index=dates[t_start:])

    def d1(s):
        u = vol.loc[s][liq.loc[s] & vol.loc[s].notna()].sort_values()
        return list(u.index[:n])

    nav = run(d1)
    rng = np.random.default_rng(SEED + 1)

    def rnd(s):
        u = list(vol.loc[s][liq.loc[s] & vol.loc[s].notna()].index)
        return list(rng.choice(u, size=min(n, len(u)), replace=False))

    pl = []
    for i in range(n_placebo):
        pl.append(stats(run(rnd)[:"2019-12-31"])["sharpe"])
    jkn = jk.reindex(dates).ffill()
    res = {"d1": stats(nav[:"2019-12-31"]), "jkse": stats(jkn[nav.index[0]:"2019-12-31"]), "placebo_p95": float(np.percentile(pl, 95)),
           "placebo_med": float(np.median(pl)), "n_names_2010": int(Cc.loc["2010-02-01":"2010-03-01"].notna().any().sum()),
           "n_names_2019": int(Cc.loc["2019-02-01":"2019-03-01"].notna().any().sum())}
    res["placebo_pct"] = float((np.array(pl) < res["d1"]["sharpe"]).mean() * 100)
    res["crash_2020"] = {"d1": float(nav["2020-03-24"] / nav["2020-02-19"] - 1), "jkse": float(jkn["2020-03-24"] / jkn["2020-02-19"] - 1),
                         "d1_2020": float(nav.iloc[-1] / nav[:"2019-12-31"].iloc[-1] - 1), "jkse_2020": float(jkn.iloc[-1] / jkn[:"2019-12-31"].iloc[-1] - 1)}
    res["pass"] = bool(res["d1"]["sharpe"] >= res["jkse"]["sharpe"] + 0.2 and res["d1"]["mdd"] > res["jkse"]["mdd"])
    return res


# ------------------------------------------------------------------ main --------------------------------------------------------
def main() -> int:
    log("loading DB ...")
    bars, div, fund, listing, ix = load()
    P = build_panel(bars, div)
    dates = P["dates"]
    log(f"panel {len(dates)} days x {len(P['codes'])} codes, {dates[0].date()} -> {dates[-1].date()}")
    bench, mkt_yield = benchmarks(P, bars, ix)
    cov = dividend_coverage(fund, div, P)
    log(f"dividend coverage {cov}; market TR-proxy yield by year {mkt_yield}")
    del bars

    Q = reb_days(dates)
    MON = reb_days(dates, monthly=True)
    prev = lambda d: dates[dates.get_loc(d) - 1]  # noqa: E731
    specs = {"D1": ("D1", 20, 252, Q), "D2": ("D2", 20, 252, Q), "D3": ("D3", 20, 252, Q),
             "D3_vol126": ("D3", 20, 126, Q), "D3_n10": ("D3", 10, 252, Q), "D3_n30": ("D3", 30, 252, Q), "D3_monthly": ("D3", 20, 252, MON)}
    TG, diag = {}, {}
    for name, (arm, n, vw, rb) in specs.items():
        dg = []
        TG[name] = {d: select(P, fund, listing, arm, prev(d), n=n, volwin=vw, diag=dg) for d in rb}
        diag[name] = dg
    univ_n = [int((P["liq"].loc[prev(d)] & P["vol252"].loc[prev(d)].notna()).sum()) for d in Q]
    log(f"universe size at rebalances: min {min(univ_n)} median {int(np.median(univ_n))} max {max(univ_n)}")

    log("combo NAV ...")
    combo = combo_nav()
    cst = stats(combo)
    log(f"combo {cst['cagr']:.3f} {cst['sharpe']:.2f} {cst['mdd']:.3f}")
    if os.path.exists(FE_NAV_PKL):
        fe = pickle.load(open(FE_NAV_PKL, "rb"))
        log(f"combo vs fe_drawdown_nav.pkl max abs diff {float((fe - combo).abs().max()):.4f}")
    ch, cmid = halves(combo)
    draws = boot_draws(len(combo) - 1)
    r_c = np.log(combo).diff().dropna()
    combo_plan = (np.exp(r_c.mean() * 245) - 1) * PLAN_RATIO
    combo_pd = plan_dd(combo, combo_plan, draws)
    log(f"combo planning CAGR {combo_plan:.3f} -> 3y dd {combo_pd}")

    # benchmark stats on the sleeve window
    w0 = Q[0]
    bst = {k: stats(v[w0:]) for k, v in bench.items()}
    bh = {k: halves(v[w0:])[0] for k, v in bench.items()}

    res = {}

    def evaluate(name, cost_mult=1.0, full=True):
        tg = TG[name]
        nav20, trades, holds = simulate(P, tg, 20e6, cost_mult)
        st = stats(nav20)
        h, smid = halves(nav20)
        r = {"standalone": st, "halves": h, "split": str(smid.date()), "turnover": turnover(nav20, trades, dates),
             "n_trades": len(trades), "holds": {str(k.date()): v for k, v in holds.items()}}
        cmp_ = bst["COMPOSITE_TR"]
        r["a_full"] = bool(st["cagr"] > cmp_["cagr"] and st["sharpe"] >= cmp_["sharpe"] + 0.2)
        r["a_halves"] = [bool(h[i]["sharpe"] >= bh["COMPOSITE_TR"][i]["sharpe"] + 0.2) for i in range(2)]
        r["a"] = bool(st["cagr"] > cmp_["cagr"] and all(r["a_halves"]))
        rr = pd.concat([nav20.pct_change(), combo.pct_change()], axis=1, keys=["s", "c"]).dropna()
        r["corr"] = float(rr["s"].corr(rr["c"]))
        r["b"] = r["corr"] < 0.5
        resets = [d for d in tg if d >= combo.index[0]]
        r["blend"] = {}
        for w in (0.20, 0.33):
            navw, _, _ = simulate(P, tg, w * 20e6, cost_mult, end=combo.index[-1])
            bl = blend(combo, navw, w, resets)
            bs = stats(bl)
            bhs = [stats(bl[bl.index <= cmid]), stats(bl[bl.index > cmid])]
            ok_h = [bool(bhs[i]["sharpe"] >= ch[i]["sharpe"] and (bhs[i]["mdd"] - ch[i]["mdd"]) * 100 >= 2.0) for i in range(2)]
            ok_full = bool(bs["sharpe"] >= cst["sharpe"] and (bs["mdd"] - cst["mdd"]) * 100 >= 2.0)
            e = {"full": bs, "halves": bhs, "ok_halves": ok_h, "ok_full": ok_full}
            if full:
                sl_cagr = stats(navw[combo.index[0]:])["cagr"]
                plan = (1 - w) * combo_plan + w * sl_cagr * SLEEVE_HAIRCUT
                e["plan_cagr"] = plan
                e["plan_dd"] = plan_dd(bl, plan, draws)
                e["plan_ok"] = bool(e["plan_dd"]["p10"] > combo_pd["p10"])
                # Rp 200 M total (sleeve lots barely bind) - reported
                n200, _, _ = simulate(P, tg, w * 200e6, cost_mult, end=combo.index[-1])
                b200 = blend(combo, n200, w, resets)
                e["rp200"] = {"full": stats(b200), "halves": [stats(b200[b200.index <= cmid]), stats(b200[b200.index > cmid])]}
                e["crash"] = {k: float(bl[b:e_].iloc[-1] / bl[b:e_].iloc[0] - 1) for k, (b, e_) in CRASHES.items() if len(bl[b:e_]) > 1}
                e["cash_share_mean"] = None
            r["blend"][w] = e
        r["c"] = all(all(r["blend"][w]["ok_halves"]) and r["blend"][w].get("plan_ok", True) for w in (0.20, 0.33))
        r["agree"] = bool(r["a_full"] and r["b"] and r["blend"][0.20]["ok_full"])
        if full:
            nav200, _, _ = simulate(P, tg, 200e6, cost_mult)
            r["rp200"] = stats(nav200)
            rd = nav20.pct_change().dropna().to_numpy()
            r["dsr"] = deflated_sharpe(rd[rd != 0], N_AFTER)
            r["crash"] = {k: {"sleeve": float(nav20[b:e_].iloc[-1] / nav20[b:e_].iloc[0] - 1) if len(nav20[b:e_]) > 1 else None,
                              "combo": float(combo[b:e_].iloc[-1] / combo[b:e_].iloc[0] - 1) if len(combo[b:e_]) > 1 else None,
                              "COMPOSITE": float(bench["COMPOSITE"][b:e_].iloc[-1] / bench["COMPOSITE"][b:e_].iloc[0] - 1),
                              "IDXHIDIV20": float(bench["IDXHIDIV20"][b:e_].iloc[-1] / bench["IDXHIDIV20"][b:e_].iloc[0] - 1)}
                          for k, (b, e_) in CRASHES.items()}
            # invested share
            r["names_held_mean"] = float(np.mean([len(v) for v in holds.values()]))
            r["_nav"] = nav20
        return r

    for name in specs:
        log(f"arm {name} ...")
        res[name] = evaluate(name, full=name in ("D1", "D2", "D3"))
        s = res[name]["standalone"]
        log(f"  {name}: {s['cagr']:.3f} / {s['sharpe']:.2f} / {s['mdd']:.3f}  corr {res[name]['corr']:.2f}  a {res[name]['a']} b {res[name]['b']} "
            f"blend20 {res[name]['blend'][0.2]['full']['sharpe']:.2f}/{res[name]['blend'][0.2]['full']['mdd']:.3f}")

    # costs x 1.5 on the three arms
    for name in ("D1", "D2", "D3"):
        rc = evaluate(name, cost_mult=1.5, full=False)
        res[name]["cost15"] = {"standalone": rc["standalone"], "a_full": rc["a_full"], "blend20_full": rc["blend"][0.2]["full"],
                               "blend20_ok": rc["blend"][0.2]["ok_full"], "hold": bool(rc["a_full"] and rc["blend"][0.2]["ok_full"])}

    # placebo: random 20-name liquid books, same quarterly dates, Rp 20 M
    log("placebo ...")
    rng = np.random.default_rng(SEED)
    pl = []
    for i in range(N_PLACEBO):
        tg = {}
        for d in Q:
            s_ = prev(d)
            u = list(P["liq"].columns[(P["liq"].loc[s_] & P["vol252"].loc[s_].notna()).to_numpy()])
            tg[d] = list(rng.choice(u, size=20, replace=False))
        nv, _, _ = simulate(P, tg, 20e6)
        pl.append(stats(nv)["sharpe"])
    pl = np.array(pl)
    for name in ("D1", "D2", "D3"):
        res[name]["placebo_pct"] = float((pl < res[name]["standalone"]["sharpe"]).mean() * 100)
    placebo = {"median": float(np.median(pl)), "p95": float(np.percentile(pl, 95))}
    log(f"placebo {placebo}")

    log("long history (Yahoo survivors) ...")
    LH = long_history()
    log(f"long {LH}")

    # value book overlap (#66 strict composite, May holdings)
    vq = json.load(open(os.path.join(ROOT, "research-scratch", "idx-screen", "value_quality_results.json")))
    vh = {h["date"]: set(h["names"]) for h in vq["months"]["5"]["summary"]["composite_q"]["holdings"]}
    for name in ("D1", "D2", "D3"):
        hd = res[name]["holds"]
        ov = {}
        for vd, names in vh.items():
            ks = [k for k in hd if k <= vd]
            if ks:
                cur = set(hd[max(ks)])
                ov[vd] = {"overlap": len(cur & names), "value_n": len(names), "sleeve_n": len(cur), "names": sorted(cur & names)}
        res[name]["value_overlap"] = ov

    nb = ["D3_vol126", "D3_n10", "D3_n30", "D3_monthly"]
    nb_agree = sum(res[k]["agree"] for k in nb)
    verdict = {}
    for name in ("D1", "D2", "D3"):
        r = res[name]
        core_full = r["a_full"] and r["b"] and all(r["blend"][w]["ok_full"] for w in (0.20, 0.33))
        rob = {"placebo": r["placebo_pct"] >= 95, "costs": r["cost15"]["hold"], "long": LH["pass"],
               "neighbours": (nb_agree >= 3) if name == "D3" else None}
        strict = r["a"] and r["b"] and r["c"]
        if strict and rob["placebo"] and rob["costs"] and rob["neighbours"] is True and rob["long"]:
            v = "QUALIFIES"
        elif core_full and (strict or sum(x is False for x in rob.values()) <= 1):
            v = "PARTIAL"
        else:
            v = "CLOSED"
        r["robust"] = rob
        verdict[name] = v
    write_report(res, specs, bst, bh, cst, ch, cmid, combo_plan, combo_pd, placebo, LH, cov, mkt_yield, diag, univ_n, nb_agree, verdict, Q)

    if os.environ.get("DEF_NOSTORE"):
        return 0
    summ = {k: {kk: vv for kk, vv in v.items() if not kk.startswith("_") and kk != "holds"} for k, v in res.items()}
    for k in summ:
        summ[k]["blend"] = {str(w): x for w, x in summ[k]["blend"].items()}
    with psycopg.connect(dsn()) as conn:
        sid = rs.record_study(conn, STUDY, date(2026, 9, 26),
                              params={"n_trials_cumulative": N_AFTER, "n_trials_before": N_BEFORE, "trials_added": len(TRIALS), "trials": {str(k): v for k, v in TRIALS.items()},
                                      "menu": 44, "names": 20, "rebalance": "first trading day Feb/May/Aug/Nov", "universe": "v60>=5bn, close>=100, pit board 1/2",
                                      "capital": [20e6, 200e6], "blend_shares": [0.2, 0.33], "combo": "#192 variant d via idx_fe_drawdown recreation",
                                      "plan_ratio": PLAN_RATIO, "sleeve_haircut": SLEEVE_HAIRCUT, "n_placebo": N_PLACEBO},
                              summary=common.plain({"arms": summ, "verdict": verdict, "combo": cst, "combo_halves": ch, "combo_plan_dd": combo_pd,
                                                    "bench": bst, "placebo": placebo, "long_history": LH, "dividend_coverage": cov, "neighbours_agree": nb_agree}),
                              names=[], report_path=OUT, note="menu 44 defensive carry sleeve (low vol + dividend carry) for breadth")
    log(f"study #{sid} stored")
    return 0


def f3(s):
    return f"{s['cagr'] * 100:.1f} % / {s['sharpe']:.2f} / {s['mdd'] * 100:.1f} %"


def write_report(res, specs, bst, bh, cst, ch, cmid, combo_plan, combo_pd, placebo, LH, cov, mkt_yield, diag, univ_n, nb_agree, verdict, Q):
    L = [f"# IDX menu 44 - defensive carry sleeve (low vol + dividend carry) for breadth - 2026-09-26 - 8 trials (968..975), cumulative N = {N_AFTER}", "",
         "Script `research/idx_defensive.py` (pre-registration in its docstring). Rp 20 M standalone unless stated; quarterly (first trading day of "
         f"Feb/May/Aug/Nov), 20 names, liquid main-board universe (point-in-time board), closing bid/offer + Stockbit fees, lots of 100, dividends "
         f"on the ex-date net of 10 % tax. Sleeve window {Q[0].date()} -> {res['D1']['_nav'].index[-1].date()}. Universe at rebalances: "
         f"{min(univ_n)}..{max(univ_n)} names (median {int(np.median(univ_n))}). Cells CAGR / Sharpe / mDD.", "",
         "## Standalone vs benchmarks (same window)", "",
         "| book | full | half 1 Sharpe | half 2 Sharpe | Rp 200 M | turnover/yr | DSR@975 | placebo pct |", "|---|---|---|---|---|---|---|---|"]
    for k, v in res.items():
        L.append(f"| {k} | {f3(v['standalone'])} | {v['halves'][0]['sharpe']:.2f} | {v['halves'][1]['sharpe']:.2f} | "
                 f"{f3(v['rp200']) if 'rp200' in v else '-'} | {v['turnover'] * 100:.0f} % | {v.get('dsr', float('nan')):.2f} | {v.get('placebo_pct', float('nan')):.0f} |")
    for k in ("COMPOSITE_TR", "COMPOSITE", "LQ45", "IDXHIDIV20"):
        L.append(f"| {k}{' (proxy)' if k == 'COMPOSITE_TR' else ' (price)'} | {f3(bst[k])} | {bh[k][0]['sharpe']:.2f} | {bh[k][1]['sharpe']:.2f} | - | - | - | - |")
    L += ["", f"By year (Rp 20 M): " + "; ".join(f"{k} " + " ".join(f"{str(y)[2:]}:{r * 100:+.0f}" for y, r in v["standalone"]["by_year"].items()) for k, v in res.items() if k in ("D1", "D2", "D3"))
          + "; COMPOSITE_TR " + " ".join(f"{str(y)[2:]}:{r * 100:+.0f}" for y, r in bst["COMPOSITE_TR"]["by_year"].items()) + ".", "",
          f"Placebo (200 random 20-name liquid books, same dates, Rp 20 M): Sharpe median {placebo['median']:.2f}, p95 {placebo['p95']:.2f}.", "",
          "## Added to the deployed combo (Rp 20 M total; sleeve simulated at its own capital; same run)", "",
          f"Combo (#192 d, recreated): {f3(cst)}; halves (split {cmid.date()}): {f3(ch[0])} | {f3(ch[1])}. Planning CAGR {combo_plan * 100:.1f} %, "
          f"3-year planning drawdown median {combo_pd['median'] * 100:.1f} %, 1-in-10 {combo_pd['p10'] * 100:.1f} %.", "",
          "| arm | corr w/ combo | share | blend full | blend H1 | blend H2 | halves pass | plan 3y 1-in-10 | Rp 200 M total full |", "|---|---|---|---|---|---|---|---|---|"]
    for k, v in res.items():
        for w, e in v["blend"].items():
            L.append(f"| {k} | {v['corr']:.2f} | {w * 100:.0f} % | {f3(e['full'])} | {f3(e['halves'][0])} | {f3(e['halves'][1])} | {sum(e['ok_halves'])}/2 | "
                     f"{e['plan_dd']['p10'] * 100:.1f} % |" if "plan_dd" in e else
                     f"| {k} | {v['corr']:.2f} | {w * 100:.0f} % | {f3(e['full'])} | {f3(e['halves'][0])} | {f3(e['halves'][1])} | {sum(e['ok_halves'])}/2 | - |")
            if "rp200" in e:
                L[-1] += f" {f3(e['rp200']['full'])} |"
            else:
                L[-1] += " - |"
    L += ["", "## Reading rule per arm", "", "| arm | (a) CAGR>COMP TR & Sharpe+0.2 both halves | (b) corr<0.5 | (c) blends 20/33 % both halves + plan dd | placebo>=95 | costs x1.5 | neighbours | long 2010-19 | verdict |",
          "|---|---|---|---|---|---|---|---|---|"]
    for k in ("D1", "D2", "D3"):
        v = res[k]
        L.append(f"| {k} | {'yes' if v['a'] else 'no'} (full {'yes' if v['a_full'] else 'no'}, halves {v['a_halves']}) | {'yes' if v['b'] else 'no'} ({v['corr']:.2f}) | "
                 f"{'yes' if v['c'] else 'no'} | {v['placebo_pct']:.0f} | {'hold' if v['cost15']['hold'] else 'fail'} ({f3(v['cost15']['standalone'])}) | "
                 f"{(str(nb_agree) + '/4') if k == 'D3' else 'n/a'} | {'pass' if LH['pass'] else 'fail'} | **{verdict[k]}** |")
    L += ["", "Neighbours (on D3; agree = (a) full, (b), 20 % blend full-window Sharpe >= combo and mDD >= 2 pp shallower): "
          + "; ".join(f"{k} {f3(res[k]['standalone'])}, corr {res[k]['corr']:.2f}, blend20 {f3(res[k]['blend'][0.2]['full'])} -> {'agree' if res[k]['agree'] else 'no'}"
                      for k in ("D3_vol126", "D3_n10", "D3_n30", "D3_monthly")) + f". {nb_agree}/4 agree.", "",
          "## Crash behaviour (period return)", "", "| window | D1 | D2 | D3 | combo | D3 blend 20 % | COMPOSITE | IDXHIDIV20 |", "|---|---|---|---|---|---|---|---|"]
    for cn in CRASHES:
        c = {k: res[k]["crash"][cn] for k in ("D1", "D2", "D3")}
        fmt = lambda x: "-" if x is None else f"{x * 100:+.1f} %"  # noqa: E731
        bl = res["D3"]["blend"][0.2]["crash"].get(cn)
        L.append(f"| {cn} | {fmt(c['D1']['sleeve'])} | {fmt(c['D2']['sleeve'])} | {fmt(c['D3']['sleeve'])} | {fmt(c['D3']['combo'])} | {fmt(bl)} | "
                 f"{fmt(c['D3']['COMPOSITE'])} | {fmt(c['D3']['IDXHIDIV20'])} |")
    L += [f"| 2020-02-19 -> 03-24 (975, Yahoo survivors, D1 price only) | {LH['crash_2020']['d1'] * 100:+.1f} % | n/a | n/a | n/a | n/a | JKSE {LH['crash_2020']['jkse'] * 100:+.1f} % | n/a |", "",
          "## Long history (trial 975): D1 on the Yahoo cache 2010-02 -> 2019-12 - SURVIVORSHIP-BIASED (450 names that still exist), price only", "",
          f"D1 {f3(LH['d1'])} vs JKSE (price) {f3(LH['jkse'])}; random 20-name survivor books Sharpe median {LH['placebo_med']:.2f}, p95 {LH['placebo_p95']:.2f} "
          f"(D1 at pct {LH['placebo_pct']:.0f}). Names in the cache: {LH['n_names_2010']} (2010) -> {LH['n_names_2019']} (2019). 2020 full year D1 "
          f"{LH['crash_2020']['d1_2020'] * 100:+.1f} % vs JKSE {LH['crash_2020']['jkse_2020'] * 100:+.1f} %. Read: {'PASS' if LH['pass'] else 'FAIL'} "
          "(Sharpe >= JKSE + 0.2 and mDD shallower). Missing dividends understate D1 by roughly its yield; survivors overstate it.", "",
          "## Data checks", "",
          f"- Dividend coverage: of {cov['fy_paid']} FY reports of ever-liquid names with dividends paid in the cash-flow statement, {cov['fy_paid_with_yahoo_event']} "
          f"({cov['share'] * 100:.0f} %) have a Yahoo event in idx.dividend within 15 months. Market TR-proxy dividend yield by year: "
          + ", ".join(f"{y} {v * 100:.1f} %" for y, v in mkt_yield.items()) + ".",
          "- D3 gate diagnostics (low-vol half size / with a usable report / failed): " + "; ".join(f"{x['s']} {x['half']}/{x['have_report']}/{x['failed']}" for x in diag["D3"]) + ".",
          "", "## Overlap with the value book (#66 strict composite, May holdings)", ""]
    for k in ("D1", "D2", "D3"):
        L.append(f"- {k}: " + "; ".join(f"{d} {o['overlap']}/{o['value_n']} ({', '.join(o['names'])})" for d, o in res[k]["value_overlap"].items()))
    L += ["", "## Holdings (last three rebalances)", ""]
    for k in ("D1", "D2", "D3"):
        hk = list(res[k]["holds"].items())[-3:]
        L.append(f"- {k}: " + " | ".join(f"{d}: {' '.join(v)}" for d, v in hk))
    open(OUT, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    sys.exit(main())
