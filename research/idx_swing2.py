#!/usr/bin/env python3
"""IDX swing, menu 2 (2026-09-17, Fable): every dataset the desk holds that could carry a days-to-weeks signal, with the
REAL closing bid/offer as the cost. Follows menu 1 (research/idx_swing.py: 22 trials, 0 candidates, cost 1.29 %).

PRE-REGISTERED MENU (24 trials; cumulative 218 + 24 = 242). Declared before the run; nothing tuned afterwards.
  (wave|10, wave|20 added before the run at the operator's question 'ride the uptrend + good sentiment'.)
  Data used: idx.bar (adjusted closes), idx.daily_summary (closing bid/offer and their volumes, trade frequency, foreign
  buy/sell shares), idx.feature_daily (foreign net share, 60-day value), idx.macro (VIX, USD/IDR, US 10y, Brent — daily
  since 2005), idx.index_daily (COMPOSITE), idx.event (buyback disclosures since 2023-07), idx.corporate_action (splits),
  idx.fundamental (quarterly profit with publication dates), idx.listing (sector).
  Universes: LIQ = board Utama/Pengembangan, 60-day median value >= Rp 5 bn, close >= Rp 100, volume > 0.
             BLUE = LIQ and value >= Rp 20 bn and close >= Rp 1,000 (where a tick is <= 0.5 % of price).
             BASKET = the 20 most-traded BLUE names each day, equal weight (market-timing arms trade this).
  Execution: signal at the close of t; ENTRY at the close of t+1 paying the closing OFFER of t+1 (close + one tick when no
  offer is quoted); EXIT at the close of t+1+H receiving the closing BID (close - one tick when none). Stockbit fees
  0.10 % / 0.20 %. Overlapping tranches: a name held H days weighs 1/(K*H). No stops. Dividends ignored.
  Macro dated t is known before Jakarta opens on t+1 (US closes ~04:00 WIB), so a signal at close t may use it.
  A. market timing on BASKET (K = 20):
     vix_drop|3, vix_drop|5   VIX fell >= 10 % over 2 days
     idr_up|5                 USD/IDR fell >= 0.5 % over 3 days (rupiah stronger)
     fflow_mkt|5              market-wide foreign net value > 0 on t, t-1, t-2 and |t| >= 1.5x its 20-day median
     idx_rev|5                COMPOSITE 3-day return <= -3 %
     tom|4                    turn of the month: signal on the second-to-last trading day (entry at the month's last close)
     us10y_drop|5             US 10-year yield fell >= 0.15 pp over 5 days
  B. microstructure, cross-sectional on BLUE (K = 5):
     obi|2, obi|5             closing order-book imbalance bid_vol/(bid_vol+offer_vol) >= 0.70, ranked by imbalance
     accum|5, accum|10        volume >= 2x 20-day median, |1-day return| <= 1 %, 5-day foreign net share > 0 (quiet accumulation)
     freq|3                   trade count >= 3x 20-day median and the day up (attention), ranked by the ratio
  C. events on LIQ (K = 5):
     buyback|10, buyback|20   buyback disclosure (idx.event kind buyback), entry the close after the event date
     split_runup|9            entry 10 trading days before a split ex-date, exit the day before it (the retail run-up)
  D. cross-sectional 10–20 days on BLUE (K = 5):
     mom20|10, mom20|20       top decile of the return from t-22 to t-2 (skip the last two days)
     brk20|10, brk20|20       close = 20-day high with volume >= 2x median (menu-1 arm at the longer horizon, BLUE only)
     pead|20                  quarterly net profit >= +30 % y/y, entry after publication
     wave|10, wave|20         "ride the wave": in the top quarter of 20-day momentum (skip 2 days), above the 20-day high within
                              the last 5 days, 20-day foreign net share > 0 and trade count >= 1.5x its 20-day median (trend +
                              flow + attention: the desk's only sentiment proxies with history), ranked by momentum
  E. commodity -> sector on LIQ energy names (sector A. Energy / 2. Mining, ranked by value; K = 5):
     brent_up|5, brent_up|10  Brent +5 % or more over 5 days
  References (not trials): random on the same universe, K and H for every arm family; COMPOSITE buy and hold.
READING RULE (declared before the run): candidate only if ALL hold after costs: >= 300 trades (event arms >= 150); mean net
  basket-day return > 0 with t >= 2.5; net portfolio return positive in >= 5 of 7 calendar years (event arms: >= 3 of 4,
  2023–2026); annualised Sharpe >= 1.0; max drawdown <= 25 %; Sharpe >= random + 0.5. Candidates go to a paper book for
  >= 60 trades before money. Everything else: tested, no edge after costs.
READ-ONLY. INGEST_DB_DSN=... blackheart-ingest/.venv/Scripts/python research/idx_swing2.py
"""
from __future__ import annotations

import argparse
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

START, END = date(2020, 1, 1), date(2026, 9, 16)
FEE_BUY, FEE_SELL = 0.0010, 0.0020
LIQ, MIN_PRICE = 5e9, 100
BLUE_LIQ, BLUE_PRICE, BASKET_N = 20e9, 1000, 20
N_TRIALS_BEFORE = 218
SEED = 20260917
ARMS = [  # name|H : (family, universe, K)
    ("vix_drop|3", "A"), ("vix_drop|5", "A"), ("idr_up|5", "A"), ("fflow_mkt|5", "A"), ("idx_rev|5", "A"), ("tom|4", "A"), ("us10y_drop|5", "A"),
    ("obi|2", "B"), ("obi|5", "B"), ("accum|5", "B"), ("accum|10", "B"), ("freq|3", "B"),
    ("buyback|10", "C"), ("buyback|20", "C"), ("split_runup|9", "C"),
    ("mom20|10", "D"), ("mom20|20", "D"), ("brk20|10", "D"), ("brk20|20", "D"), ("pead|20", "D"), ("wave|10", "D"), ("wave|20", "D"),
    ("brent_up|5", "E"), ("brent_up|10", "E"),
]
assert len(ARMS) == 24
FAMILY = {"A": ("BASKET", BASKET_N), "B": ("BLUE", 5), "C": ("LIQ", 5), "D": ("BLUE", 5), "E": ("ENERGY", 5)}
EVENT_ARMS = {"buyback", "split_runup"}


def tick(p):
    p = np.asarray(p, dtype=float)
    return np.select([p < 200, p < 500, p < 2000, p < 5000], [1, 2, 5, 10], 25).astype(float)


def load(conn):
    q = lambda sql, params=(): pd.read_sql(sql, conn, params=params)  # noqa: E731
    bars = q("""SELECT b.code, b.trade_date, b.close, b.adj_factor, b.volume, s.bid, s.offer, s.bid_volume AS bv, s.offer_volume AS ov, s.frequency AS freq,
                       s.foreign_buy AS fb, s.foreign_sell AS fs, f.foreign_net_share_5d AS f5, f.foreign_net_share_20d AS f20, f.value_60d_median AS v60
                  FROM idx.bar b LEFT JOIN idx.daily_summary s USING (code, trade_date) LEFT JOIN idx.feature_daily f USING (code, trade_date)
                 WHERE b.source = 'idx' AND b.trade_date BETWEEN %s AND %s""", (START, END))
    listing = q("SELECT code, board, sector FROM idx.listing")
    idx = q("SELECT trade_date, close FROM idx.index_daily WHERE index_code = 'COMPOSITE' AND trade_date BETWEEN %s AND %s ORDER BY 1", (START, END))
    macro = q("SELECT series, obs_date, value FROM idx.macro WHERE series IN ('vix', 'usdidr', 'us10y', 'brent') AND obs_date >= %s ORDER BY 2", (date(2019, 10, 1),))
    buyb = q("SELECT code, event_date FROM idx.event WHERE kind = 'buyback' AND event_date BETWEEN %s AND %s", (START, END))
    splits = q("SELECT code, ex_date FROM idx.corporate_action WHERE kind = 'split' AND ex_date BETWEEN %s AND %s", (START, END))
    pead = q("""WITH f AS (SELECT code, period_end, net_profit, published_at::date AS pub FROM idx.fundamental WHERE published_at IS NOT NULL)
                SELECT a.code, a.pub, a.net_profit, b.net_profit AS prior FROM f a JOIN f b ON b.code = a.code AND b.period_end = a.period_end - interval '1 year'
                 WHERE a.pub BETWEEN %s AND %s""", (START, END))
    return bars, listing, idx, macro, buyb, splits, pead


def panels(bars, listing):
    bars = bars.copy()
    for c in ("close", "adj_factor", "volume", "bid", "offer", "bv", "ov", "freq", "fb", "fs", "f5", "f20", "v60"):
        bars[c] = pd.to_numeric(bars[c], errors="coerce")
    bars["adj"] = bars["close"] * bars["adj_factor"].fillna(1.0)
    bars["fnet"] = (bars["fb"].fillna(0) - bars["fs"].fillna(0)) * bars["close"]
    ok = set(listing.loc[listing["board"].isin(["Utama", "Pengembangan"]), "code"])
    bars = bars[bars["code"].isin(ok)]
    P = {c: bars.pivot(index="trade_date", columns="code", values=c).sort_index() for c in ("adj", "close", "volume", "bid", "offer", "bv", "ov", "freq", "fnet", "f5", "f20", "v60")}
    for k in P:
        P[k].index = pd.to_datetime(P[k].index)
    return P


def event_mask(dates, cols, rows, offset=0):
    """rows: iterable of (code, day) -> mask True at the trading-day index of day (+offset)."""
    m = pd.DataFrame(False, index=dates, columns=cols)
    for code, d in rows:
        if code not in cols or pd.isna(d):
            continue
        i = dates.searchsorted(pd.Timestamp(d)) + offset
        if 0 <= i < len(dates):
            m.iat[i, m.columns.get_loc(code)] = True
    return m


def build(P, listing, idx, macro, buyb, splits, pead):
    adj, close, vol = P["adj"], P["close"], P["volume"]
    dates, cols = adj.index, adj.columns
    liq = (P["v60"] >= LIQ) & (close >= MIN_PRICE) & (vol > 0) & adj.notna()
    blue = liq & (P["v60"] >= BLUE_LIQ) & (close >= BLUE_PRICE)
    rank_v = P["v60"].where(blue).rank(axis=1, ascending=False)
    basket = blue & (rank_v <= BASKET_N)
    sec = listing.set_index("code")["sector"].reindex(cols)
    energy = liq & pd.DataFrame(np.tile(sec.isin(["A. Energy", "2. Mining"]).to_numpy(), (len(dates), 1)), index=dates, columns=cols)
    ones = close * 0 + 1
    # --- macro aligned to trading days (last observation on or before t) ---
    mac = macro.copy()
    mac["obs_date"] = pd.to_datetime(mac["obs_date"])
    mac["value"] = pd.to_numeric(mac["value"], errors="coerce")
    M = mac.pivot(index="obs_date", columns="series", values="value").sort_index().reindex(dates, method="ffill")
    vix, idr, us10, brent = M["vix"], M["usdidr"], M["us10y"], M["brent"]
    idx = idx.copy()
    idx["trade_date"] = pd.to_datetime(idx["trade_date"])
    comp = idx.set_index("trade_date")["close"].astype(float).reindex(dates, method="ffill")
    fnet_mkt = P["fnet"].where(liq).sum(axis=1)
    fabs_med = fnet_mkt.abs().rolling(20, min_periods=20).median()
    mkt = {
        "vix_drop": vix / vix.shift(2) - 1 <= -0.10,
        "idr_up": idr / idr.shift(3) - 1 <= -0.005,
        "fflow_mkt": (fnet_mkt > 0) & (fnet_mkt.shift(1) > 0) & (fnet_mkt.shift(2) > 0) & (fnet_mkt.abs() >= 1.5 * fabs_med),
        "idx_rev": comp / comp.shift(3) - 1 <= -0.03,
        "us10y_drop": us10 - us10.shift(5) <= -0.15,
    }
    ym = pd.Series(dates.year * 100 + dates.month, index=dates)
    last_of_month = ym != ym.shift(-1)
    mkt["tom"] = last_of_month.shift(-1, fill_value=False)          # second-to-last trading day of the month
    arms = {}
    for k, s in mkt.items():
        arms[k] = (basket & pd.DataFrame(np.tile(s.fillna(False).to_numpy()[:, None], (1, len(cols))), index=dates, columns=cols), P["v60"])
    # --- microstructure ---
    obi = P["bv"] / (P["bv"] + P["ov"])
    r1 = adj / adj.shift(1) - 1
    vmed = vol.rolling(20, min_periods=20).median()
    vr = vol / vmed
    fmed = P["freq"].rolling(20, min_periods=20).median()
    fr = P["freq"] / fmed
    arms["obi"] = (blue & (obi >= 0.70) & (P["bid"] >= close - pd.DataFrame(tick(close.to_numpy()), index=dates, columns=cols)), obi)
    arms["accum"] = (blue & (vr >= 2) & (r1.abs() <= 0.01) & (P["f5"] > 0), vr)
    arms["freq"] = (blue & (fr >= 3) & (r1 > 0), fr)
    # --- events ---
    buyb = buyb.copy()
    arms["buyback"] = (liq & event_mask(dates, cols, buyb[["code", "event_date"]].itertuples(index=False)), ones)
    arms["split_runup"] = (liq & event_mask(dates, cols, splits[["code", "ex_date"]].itertuples(index=False), offset=-11), ones)
    # --- cross-sectional 10-20 d ---
    mom = adj.shift(2) / adj.shift(22) - 1
    dec = mom.where(blue).rank(axis=1, ascending=False, pct=True)
    arms["mom20"] = (blue & (dec <= 0.10), mom)
    hi20 = adj.rolling(20, min_periods=20).max()
    arms["brk20"] = (blue & (adj >= hi20) & (vr >= 2), vr)
    pead = pead.copy()
    for c in ("net_profit", "prior"):
        pead[c] = pd.to_numeric(pead[c], errors="coerce")
    grow = pead[(pead["prior"] > 0) & (pead["net_profit"] >= 1.3 * pead["prior"])]
    arms["pead"] = (blue & event_mask(dates, cols, grow[["code", "pub"]].itertuples(index=False)), ones)
    near_high = (adj >= hi20).rolling(5, min_periods=1).max() >= 1
    f20 = P["f20"]
    arms["wave"] = (blue & (dec <= 0.25) & near_high & (f20 > 0) & (fr >= 1.5), mom)
    # --- commodity -> sector ---
    b5 = (brent / brent.shift(5) - 1 >= 0.05).fillna(False)
    arms["brent_up"] = (energy & pd.DataFrame(np.tile(b5.to_numpy()[:, None], (1, len(cols))), index=dates, columns=cols), P["v60"])
    unis = {"LIQ": liq, "BLUE": blue, "BASKET": basket, "ENERGY": energy}
    return arms, unis, comp


def costs(P):
    """Entry cost at the closing offer, exit at the closing bid; a tick when the quote is missing/crossed."""
    C = P["close"].to_numpy(float)
    tk = tick(np.nan_to_num(C, nan=1.0))
    off, bid = P["offer"].to_numpy(float), P["bid"].to_numpy(float)
    c_in = np.where((off > 0) & (off >= C), off / C - 1, tk / C) + FEE_BUY
    c_out = np.where((bid > 0) & (bid <= C), 1 - bid / C, tk / C) + FEE_SELL
    return c_in, c_out


def simulate(adj, mask, score, H, k, c_in, c_out, rng=None, uni=None):
    A = adj.to_numpy(float)
    M = mask.to_numpy(bool)
    S = score.to_numpy(float)
    T, N = A.shape
    W = np.zeros((T, N))
    cost_day = np.zeros(T)
    ret = np.full((T, N), np.nan)
    ret[1:] = A[1:] / A[:-1] - 1
    slot = 1.0 / (k * H)
    trades = []
    U = uni.to_numpy(bool) if uni is not None else None
    for t in range(T - H - 1):
        e, x = t + 1, t + 1 + H
        base = (U[t] if rng is not None else M[t]) & ~np.isnan(A[e]) & ~np.isnan(A[x])
        cand = np.flatnonzero(base)
        if len(cand) == 0:
            continue
        if rng is not None:
            pick = rng.choice(cand, size=min(k, len(cand)), replace=False)
        else:
            sc = np.nan_to_num(S[t, cand], nan=-np.inf)
            pick = cand[np.argsort(-sc, kind="stable")[:k]]
        for j in pick:
            ci, co = c_in[e, j], c_out[x, j]
            if not (np.isfinite(ci) and np.isfinite(co)):
                continue
            W[e + 1:x + 1, j] += slot
            cost_day[e] += slot * ci
            cost_day[x] += slot * co
            gross = A[x, j] / A[e, j] - 1
            trades.append((e, j, gross, gross - ci - co))
    R = np.nansum(W * np.nan_to_num(ret), axis=1) - cost_day
    return pd.Series(R, index=adj.index), trades, W.sum(axis=1)


def stats(R, trades, exposure, n_trials):
    eq = (1 + R).cumprod()
    years = R.groupby(R.index.year).apply(lambda s: (1 + s).prod() - 1)
    vol = R.std() * math.sqrt(250)
    sharpe = (R.mean() * 250 / vol) if vol > 0 else 0.0
    dd = (eq / eq.cummax() - 1).min()
    n = len(trades)
    g = np.array([t[2] for t in trades]) if n else np.array([])
    nets = np.array([t[3] for t in trades]) if n else np.array([])
    by_day = {}
    for e, _, _, r in trades:
        by_day.setdefault(e, []).append(r)
    bd = np.array([np.mean(v) for v in by_day.values()]) if by_day else np.array([])
    tstat = (bd.mean() / bd.std(ddof=1) * math.sqrt(len(bd))) if len(bd) > 2 and bd.std(ddof=1) > 0 else 0.0
    active = R[R != 0]
    dsr = ES.deflated_sharpe(list(active.values), n_trials) if len(active) > 10 else 0.0
    return {"n_trades": n, "n_days": len(bd), "hit": float((nets > 0).mean()) if n else 0.0, "avg_gross": float(g.mean()) if n else 0.0,
            "avg_net": float(nets.mean()) if n else 0.0, "med_net": float(np.median(nets)) if n else 0.0, "tstat": float(tstat),
            "total": float(eq.iloc[-1] - 1), "cagr": float(eq.iloc[-1] ** (250 / len(R)) - 1), "sharpe": float(sharpe), "mdd": float(dd),
            "dsr": float(dsr), "exposure": float(exposure.mean()), "years": {int(y): float(v) for y, v in years.items()}}


def passes(name, s, rnd):
    why = []
    ev = name in EVENT_ARMS
    if s["n_trades"] < (150 if ev else 300):
        why.append("n")
    if not (s["avg_net"] > 0 and s["tstat"] >= 2.5):
        why.append("t<2.5")
    yrs = {y: v for y, v in s["years"].items() if (y >= 2023 if ev else True)}
    if sum(1 for v in yrs.values() if v > 0) < (3 if ev else 5):
        why.append("years")
    if s["sharpe"] < 1.0:
        why.append("sharpe<1")
    if s["mdd"] < -0.25:
        why.append("mdd")
    if s["sharpe"] < rnd["sharpe"] + 0.5:
        why.append("vs random")
    return not why, why


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, f"IDX_SWING2_{date.today().isoformat()}.md"))
    ap.add_argument("--no-store", action="store_true")
    a = ap.parse_args()
    dsn = os.environ["INGEST_DB_DSN"]
    with psycopg.connect(dsn) as conn:
        bars, listing, idx, macro, buyb, splits, pead = load(conn)
    P = panels(bars, listing)
    arms, unis, comp = build(P, listing, idx, macro, buyb, splits, pead)
    c_in, c_out = costs(P)
    adj = P["adj"]
    n_trials = N_TRIALS_BEFORE + len(ARMS)
    rng = np.random.default_rng(SEED)
    refs, results, verdicts = {}, {}, {}
    for arm, fam in ARMS:
        name, H = arm.split("|")
        H = int(H)
        uname, k = FAMILY[fam]
        key = (uname, k, H)
        if key not in refs:
            R, tr, ex = simulate(adj, unis[uname], adj * 0, H, k, c_in, c_out, rng=rng, uni=unis[uname])
            refs[key] = stats(R, tr, ex, n_trials)
        m, s = arms[name]
        R, tr, ex = simulate(adj, m, s, H, k, c_in, c_out)
        results[arm] = stats(R, tr, ex, n_trials)
        ok, why = passes(name, results[arm], refs[key])
        verdicts[arm] = "CANDIDATE" if ok else "tested: " + ",".join(why)
    cc = comp.dropna()
    comp_total = cc.iloc[-1] / cc.iloc[0] - 1

    def yrs(d):
        return " ".join(f"{y % 100:02d}:{v * 100:+.0f}" for y, v in sorted(d.items()))

    def row(label, H, s, verdict, dsr=True):
        return (f"| {label} | {H} | {s['n_trades']} | {s['hit'] * 100:.0f} % | {s['avg_gross'] * 100:+.2f} % | {s['avg_net'] * 100:+.2f} % | {s['tstat']:.1f} | "
                f"{s['total'] * 100:+.0f} % | {s['sharpe']:.2f} | {s['mdd'] * 100:.0f} % | {(f'{s['dsr']:.2f}' if dsr else '-')} | {s['exposure'] * 100:.0f} % | "
                f"{yrs(s['years'])} | {verdict} |")
    # universe cost diagnostics
    diag = []
    for uname, u in unis.items():
        U = u.to_numpy(bool)
        rt = (c_in + c_out)[U]
        diag.append(f"{uname}: avg round trip {np.nanmean(rt) * 100:.2f} % (median {np.nanmedian(rt) * 100:.2f} %), names/day {U.sum(axis=1).mean():.0f}")
    lines = [f"# IDX swing menu 2 — {date.today()} — {len(ARMS)} trials, cumulative N = {n_trials}", "",
             f"Execution: entry close t+1 at the closing offer, exit close t+1+H at the closing bid, fees {FEE_BUY * 100:.2f}/{FEE_SELL * 100:.2f} %. "
             f"{adj.index[0].date()} -> {adj.index[-1].date()}, {adj.shape[1]} names, {len(adj)} days. COMPOSITE buy-and-hold {comp_total * 100:+.1f} %.", "",
             "Universe costs: " + " | ".join(diag), "",
             "| arm | H | trades | hit | gross/trade | net/trade | t(basket) | total | Sharpe | mDD | DSR | expo | years | verdict |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for (uname, k, H), s in sorted(refs.items()):
        lines.append(row(f"random {uname} K={k}", H, s, "reference", dsr=False))
    for arm, fam in ARMS:
        name, H = arm.split("|")
        lines.append(row(f"{name} [{FAMILY[fam][0]}]", H, results[arm], verdicts[arm]))
    n_cand = sum(1 for v in verdicts.values() if v == "CANDIDATE")
    lines += ["", f"Reading rule applied as declared: {n_cand} candidate(s) of {len(ARMS)}.", "",
              "Limits: current listing board/sector (not PIT); close-to-close (one day after the signal); buyback events include bond",
              "buybacks and extensions (title-based kind); split run-up uses the ex-date only (announcement dates not stored); no",
              "quality gate beyond liquidity; dividends ignored inside a holding; costs = quoted closing spread + fees, no extra slippage."]
    text = "\n".join(lines)
    print(text)
    with open(a.out, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    print(f"\nwrote {a.out}")
    if not a.no_store:
        from blackheart_ingest.idx import research_store as rs
        with psycopg.connect(dsn) as conn:
            best = max(results, key=lambda t: results[t]["sharpe"])
            sid = rs.record_study(conn, "swing2", adj.index[-1].date(),
                                  params={"trials": [x for x, _ in ARMS], "n_trials_cumulative": n_trials, "fees": [FEE_BUY, FEE_SELL],
                                          "execution": "close t+1 @offer -> close t+1+H @bid", "universes": {"LIQ": [LIQ, MIN_PRICE], "BLUE": [BLUE_LIQ, BLUE_PRICE], "basket": BASKET_N}},
                                  summary={"results": results, "random": {f"{u}|{k}|{h}": v for (u, k, h), v in refs.items()}, "verdicts": verdicts,
                                           "composite_total": float(comp_total), "best_by_sharpe": best, "candidates": n_cand, "diag": diag},
                                  names=[], report_path=a.out, note=f"{n_cand} candidates of {len(ARMS)}; best by Sharpe {best}")
            print(f"study #{sid} stored")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
