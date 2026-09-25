#!/usr/bin/env python3
"""IDX menu 45 - buy the model's single most convincing ARA-tomorrow name at the next OPEN, sell at +20 % / ARA / close
(operator, 2026-09-26: research only - no book, no app change; the ARA freeze of 2026-09-23 stays for everything else).

The model is study #146 / idx/ara_model.py as deployed (LightGBM on BAR+MICRO, Platt-calibrated p_lock; GRU for the ENS
rank). Every score used here is OUT OF SAMPLE: walk-forward by test year 2022..2026, trained on the rows whose label was
realised before the test year began (the last day of Y-1 is purged: its label is Y's first session), calibrated the way
the deployed module does it (tree fitted on the training rows minus their last 250 sessions, Platt on those 250, then the
tree refitted on all training rows). No pooled/in-sample calibration is used anywhere (#146's report calibrated on the
pooled OOF - that would leak for the 10 % gate).

PRE-REGISTERED (7 counted trials; cumulative N_BEFORE 975 -> 982). Declared before any trade result was seen.
  Universe (evening of day t, as in #146): main boards (notation digit 1/2), close > 0, previous >= Rp 50, value >= Rp 1 bn,
    >= 20 sessions of history, and ONE LOT affordable at the operator's size: close_t x 100 <= Rp 2 M (10 % of Rp 20 M).
    Names locked at ARA today (no offer at the close) ARE candidates; they only trade if buyable at tomorrow's open.
  IDX limits: ARA = the highest tick <= previous x (1 + band); band 35 % (prev <= 200) / 25 % (<= 5,000) / 20 % on the main
    boards - unchanged 2020-2026 (the 2020 and 2025 changes were to the ARB side only); 10 % on the Akselerasi and
    Pemantauan Khusus boards, applied if the name sits there on the entry day. Tick table 1/2/5/10/25 at 200/500/2k/5k
    (in force for the whole 2020+ history - jobs/bar_open.py checked every print sits on it). The script audits the
    formula against the data (highs above the computed ARA, by year) and prints the audit.
  MAIN ARM (trial 1): each evening the single name with the highest calibrated p_lock. Next session (e = t+1):
    - not traded on e (suspended) / no open known -> no trade (counted); open >= ARA_e (locked at the open, no offer)
      -> no trade, counted as 'locked at open'; NO fall-back to pick #2.
    - entry E = open + 1 tick (capped at ARA_e), buy fee 0.15 %; lots of 100; 10 % of the sleeve NAV per trade.
    - take-profit TP = min(E x 1.20 rounded UP to the tick, ARA_e); if the day's high >= TP the limit sell fills at TP,
      else sell at the day's close; sell fee 0.25 % (incl. tax) - the fee fields of the Rp 20 M books.
    - daily bars only: we know high and low, not their order. The rule has NO stop, so only the take-profit matters and
      the path question does not arise (said in the report).
  NEIGHBOURS (trials 2-7):
    fallback   top-1, and if it cannot be bought at the open (locked / suspended / no open) the #2 name instead
    top3       the three highest p_lock names, 10 % of NAV split equally (3.33 % each), each with the same exit rule
    tp10       take-profit +10 % instead of +20 % (still capped at ARA)
    nextopen   if the take-profit is not hit, hold overnight and sell at the next session's open
    gate10     trade only when the top name's calibrated p_lock >= 10 % (the page's 'high' confidence band)
    ens        the top-1 by the page's own order (ENS = mean within-day rank of tree p_lock and GRU p_dl)
  Opens: idx.bar.open - IDX's own print (open_src 'idx', broad from Dec 2024) or the validated Yahoo fill ('yahoo';
    'stockbit' rare). PRIMARY window = entries from 2025-01-01 whose entry-day open is IDX's; reported separately:
    2025+ entries on Yahoo opens, and 2022-2024 (mostly Yahoo opens) as SECONDARY, labelled.
  Battery (not counted): placebo = one random name per traded day from the same universe that WAS buyable at that open,
    same exit and costs, 500 draws, the rule's mean must beat the 95th percentile; per-year consistency; costs x 1.5
    (fees x 1.5 and 1.5 ticks); entry open / open + 1 tick / open + 2 ticks (a 1-day delay is not applicable: the whole
    trade lives inside one session - a later entry is a different, intraday rule, and there is no 09:05 / first-trade
    history, so the entry-slippage ladder stands in for it); DSR of the per-trade series at N = 982.
  Sleeve: Rp 20 M, compounding, 10 % per trade -> CAGR / Sharpe (245) / mDD by year. Combo effect: the #192 corrected
    combo NAV (tmp/fe_drawdown_nav.pkl, built by research/idx_fe_drawdown.py, no study row) + this sleeve as an overlay of
    10 % of NAV per trade on the same days (assumes the 10 % is free cash), Sharpe and mDD vs the combo alone.
  READING RULE (main arm, all opens 2022-01 -> 2026-09): PASSES if mean net per trade > 0 with t >= 2.5 by trade AND
    t >= 2.5 clustered by month, positive in >= 60 % of years with trades, placebo >= 95th percentile, the combo's Sharpe
    rises AND its mDD is not deeper with the sleeve, AND the primary (IDX-open) window has >= 30 trades with mean > 0.
    Otherwise CLOSED; UNTESTABLE instead of PASS if the primary window has < 30 trades. Neighbours are reported with the
    same statistics; one passing where the main arm fails is a hypothesis for a future menu, not a result.
READ-ONLY. One idx.study row ('ara_open_tp'). INGEST_DB_DSN (idx-local.env).
  blackheart-ingest/.venv/Scripts/python research/idx_ara_open_tp.py [--end 2026-09-25] [--no-store] [--refit]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import pickle
import re
import sys
import time
from datetime import date, datetime

import numpy as np
import pandas as pd
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blackheart-ingest", "src"))
from blackheart_ingest.idx import ara_model as AM  # noqa: E402

STUDY = "ara_open_tp"
N_BEFORE, N_TRIALS = 975, 7
TEST_YEARS = [2022, 2023, 2024, 2025, 2026]
PRIMARY_FROM = pd.Timestamp("2025-01-01")
CAPITAL, SLOT = 20_000_000.0, 0.10
FEE_B, FEE_S = 0.0015, 0.0025
TP = 0.20
N_PLACEBO = 500
SEED = 20260926
HOLDOUT = 250
BAR = {"t": 2.5, "years": 0.60, "placebo": 95.0, "min_primary": 30}
OOF_CACHE = os.path.join(ROOT, "tmp", "ara_open_tp_oof.pkl")
NAV_PKL = os.path.join(ROOT, "tmp", "fe_drawdown_nav.pkl")
SRC = {"idx": 1, "yahoo": 2, "stockbit": 3}


def dsn() -> str:
    if os.environ.get("INGEST_DB_DSN"):
        return os.environ["INGEST_DB_DSN"]
    env = dict(re.findall(r"^([A-Z_]+)=(.*)$", open(os.path.join(ROOT, "blackheart-ingest", "idx-local.env")).read(), re.M))
    return env["INGEST_DB_DSN"].strip().strip('"')


def load(conn, end: date) -> pd.DataFrame:
    """ara_model.load_summary + the open's source."""
    cols = ["code", "d", "prev", "open", "high", "low", "close", "vol", "val", "freq", "bid", "bv", "off", "ov", "fb", "fs", "nreg", "tsh", "bd", "adj", "osrc"]
    with conn.cursor() as cur:
        cur.execute("""SELECT s.code, s.trade_date, s.previous::float8, COALESCE(b.open, s.open)::float8, s.high::float8, s.low::float8, s.close::float8,
                              s.volume::float8, s.value::float8, s.frequency::float8, s.bid::float8, s.bid_volume::float8, s.offer::float8,
                              s.offer_volume::float8, s.foreign_buy::float8, s.foreign_sell::float8, s.nonreg_volume::float8,
                              s.tradeable_shares::float8, substr(s.remarks, 5, 1), b.adj_factor::float8,
                              CASE WHEN b.open IS NOT NULL THEN b.open_src WHEN s.open IS NOT NULL THEN 'idx' END
                       FROM idx.daily_summary s LEFT JOIN idx.bar b ON b.code = s.code AND b.trade_date = s.trade_date AND b.source = 'idx'
                       WHERE s.trade_date BETWEEN %s AND %s AND s.close > 0""", (AM.START, end))
        df = pd.DataFrame(cur.fetchall(), columns=cols)
    df["d"] = pd.to_datetime(df["d"])
    return df


def tick(px):
    return AM.tick_of(np.asarray(px, float))


def ara_band(prev, band):
    raw = prev * (1 + band)
    t = tick(raw)
    return np.floor(raw / t + 1e-9) * t


def snap_up(x):
    t = tick(x)
    return np.ceil(x / t - 1e-9) * t


# ------------------------------------------------------------------------------------------------ out-of-sample scores
def oof_scores(P: AM.Panel, log=print) -> pd.DataFrame:
    S = P.training()
    m = P.main & P.ok & (P.prev >= AM.MIN_PREV) & (np.nan_to_num(P.val) >= AM.MIN_VALUE)
    m[: AM.L_SEQ - 1] = False
    C = P.frame(m)
    C["year"] = C["d"].dt.year
    out = []
    for yr in TEST_YEARS:
        t_first = int(np.searchsorted(P.dates, np.datetime64(f"{yr}-01-01")))
        tr = S[S["ti"] < t_first - 1]                                    # purge the last day of Y-1 (label = Y's first session)
        te = C[C["year"] == yr].copy()
        days = np.sort(tr["d"].unique())
        cut = days[-HOLDOUT]
        a, ho = tr[tr["d"] < cut], tr[tr["d"] >= cut]
        m0 = AM.fit_tree(a, "LOCK1")
        ab = AM.platt_fit(AM.predict_tree(m0, ho), ho["LOCK1"]) if ho["LOCK1"].sum() >= AM.MIN_CALIB_POS else None
        if ab is None:
            raise RuntimeError(f"{yr}: too few holdout locks to calibrate out of sample")
        mt = AM.fit_tree(tr, "LOCK1")
        te["p_raw"] = AM.predict_tree(mt, te)
        te["p_lock"] = AM.platt_apply(te["p_raw"], ab)
        g = AM.GRUModel(P, threads=8)
        g.fit(tr, "LOCK1")
        te["p_dl"] = g.predict(te)
        te["s_ens"] = 0.5 * (te.groupby("d")["p_lock"].rank(pct=True) + te.groupby("d")["p_dl"].rank(pct=True))
        log(f"  {yr}: train {len(tr):,} ({int(tr['LOCK1'].sum())} locks) calib a={ab[0]:.2f} b={ab[1]:.2f}; test {len(te):,} rows, "
            f"AUC tree {AM.auc(te['LOCK1'].dropna().to_numpy(), te.loc[te['LOCK1'].notna(), 'p_lock'].to_numpy()):.3f}")
        out.append(te[["ti", "ni", "d", "code", "close", "lock", "buyable", "LOCK1", "p_lock", "p_dl", "s_ens"]].assign(calib_a=ab[0], calib_b=ab[1]))
    return pd.concat(out, ignore_index=True)


# ----------------------------------------------------------------------------------------------------------- simulator
class Market:
    def __init__(self, P: AM.Panel, df: pd.DataFrame):
        self.P, self.T = P, P.T
        ti = np.searchsorted(P.dates.values, df["d"].to_numpy())
        ni = np.searchsorted(P.codes, df["code"].to_numpy())
        self.bd = np.zeros((P.T, P.N), dtype=np.int8)
        self.bd[ti, ni] = pd.to_numeric(df["bd"], errors="coerce").fillna(0).astype(int).to_numpy()
        self.src = np.zeros((P.T, P.N), dtype=np.int8)
        self.src[ti, ni] = df["osrc"].map(SRC).fillna(0).astype(int).to_numpy()
        band = np.where(np.isin(self.bd, [3, 4]), 0.10, AM.band_of(P.prev))
        self.ara = ara_band(P.prev, band)                               # the limit that applied on each day, on its own board

    def fill(self, t: int, n: int):
        """Can the name be bought at the open of t+1? -> (e, reason)."""
        e = t + 1
        P = self.P
        if e >= self.T:
            return e, "no_next"
        if not np.isfinite(P.close[e, n]):
            return e, "suspended"
        o = P.open[e, n]
        if not np.isfinite(o) or o <= 0:
            return e, "no_open"
        if o >= self.ara[e, n] - 1e-6:
            return e, "locked_open"
        return e, "ok"

    def trade(self, e: int, n: int, *, tp: float = TP, slip: float = 1.0, fee_mult: float = 1.0, exit_: str = "close") -> dict:
        P = self.P
        o, ara = P.open[e, n], self.ara[e, n]
        E = float(min(o + slip * tick(o), ara))
        lvl_pct = float(snap_up(E * (1 + tp)))
        TPx = min(lvl_pct, ara)
        hit = P.high[e, n] >= TPx - 1e-6
        x_day = e
        if hit:
            X, how = TPx, ("ara" if ara <= lvl_pct else "tp")
        elif exit_ == "close":
            X, how = float(P.close[e, n]), "close"
        else:
            k = e + 1
            while k < self.T and not np.isfinite(P.close[k, n]):
                k += 1
            if k >= self.T:
                X, how = float(P.close[e, n]), "close"
            else:
                X = float(P.open[k, n]) if np.isfinite(P.open[k, n]) and P.open[k, n] > 0 else float(P.prev[k, n])
                how, x_day = "next_open", k
        fb, fs = FEE_B * fee_mult, FEE_S * fee_mult
        net = X * (1 - fs) / (E * (1 + fb)) - 1
        return {"e": e, "x": x_day, "E": E, "X": X, "tp": TPx, "ara": float(ara), "how": how, "net": float(net),
                "src": int(self.src[e, n]), "gross_open_close": float(P.close[e, n] / o - 1), "ara_below_tp": bool(ara <= lvl_pct)}


def picks_of(C: pd.DataFrame, score: str) -> dict[int, list]:
    """Per evening t: the universe names sorted by score (desc) -> list of (ni, p_lock, code)."""
    C = C.sort_values(["ti", score], ascending=[True, False])
    return {int(t): list(zip(g["ni"].to_numpy(), g["p_lock"].to_numpy(), g["code"].to_numpy(), g["lock"].to_numpy()))
            for t, g in C.groupby("ti", sort=False)}


def run_arm(M: Market, picks: dict, arm: str, **kw) -> tuple[pd.DataFrame, dict]:
    rows, reasons = [], {"ok": 0, "locked_open": 0, "suspended": 0, "no_open": 0, "no_next": 0, "gated": 0}
    for t, lst in picks.items():
        if not lst:
            continue
        if arm == "gate10" and lst[0][1] < 0.10:
            reasons["gated"] += 1
            continue
        chosen = []
        if arm == "top3":
            for ni, p, code, lk in lst[:3]:
                e, why = M.fill(t, ni)
                reasons[why] += 1
                if why == "ok":
                    chosen.append((ni, p, code, lk, 1 / 3, 1))
        else:
            cand = lst[:2] if arm == "fallback" else lst[:1]
            for r, (ni, p, code, lk) in enumerate(cand):
                e, why = M.fill(t, ni)
                if r == 0:
                    reasons[why] += 1
                if why == "ok":
                    chosen.append((ni, p, code, lk, 1.0, r + 1))
                    break
        for ni, p, code, lk, w, rank in chosen:
            tr = M.trade(t + 1, ni, **kw)
            tr.update({"t": t, "ni": int(ni), "code": code, "p_lock": float(p), "locked_eve": bool(lk > 0), "w": w, "rank": rank,
                       "d": M.P.dates[t + 1]})
            rows.append(tr)
    df = pd.DataFrame(rows)
    if len(df):
        df["year"] = df["d"].dt.year
        df["month"] = df["d"].dt.to_period("M")
    return df, reasons


# -------------------------------------------------------------------------------------------------------------- stats
def tstats(x: np.ndarray, groups=None) -> tuple[float, float]:
    x = np.asarray(x, float)
    n = len(x)
    if n < 3:
        return float("nan"), float("nan")
    m = x.mean()
    t = m / (x.std(ddof=1) / math.sqrt(n))
    tc = float("nan")
    if groups is not None:
        e = pd.Series(x - m).groupby(np.asarray(groups)).sum().to_numpy()
        G = len(e)
        if G > 2:
            v = G / (G - 1) * (e ** 2).sum() / n ** 2
            tc = m / math.sqrt(v)
    return float(t), float(tc)


def summarize(df: pd.DataFrame) -> dict:
    if len(df) == 0:
        return {"n": 0}
    t, tc = tstats(df["net"].to_numpy(), df["month"].astype(str).to_numpy())
    return {"n": int(len(df)), "mean": float(df["net"].mean()), "median": float(df["net"].median()), "t": t, "t_month": tc,
            "hit": float(df["how"].isin(["tp", "ara"]).mean()), "hit_ara": float((df["how"] == "ara").mean()),
            "win": float((df["net"] > 0).mean()), "worst": float(df["net"].min()), "best": float(df["net"].max())}


def sleeve(df: pd.DataFrame, dates: pd.DatetimeIndex, start="2022-01-01") -> pd.Series:
    """Rp 20 M, 10 % of NAV per trade (x its weight), lots of 100, P&L booked on the exit day."""
    t0 = int(np.searchsorted(dates.values, np.datetime64(start)))
    nav = CAPITAL
    out = np.full(len(dates), np.nan)
    by_e = {k: g for k, g in df.groupby("e")} if len(df) else {}
    pend: dict[int, float] = {}
    for t in range(t0, len(dates)):
        navp = nav
        for r in by_e.get(t, pd.DataFrame()).itertuples():
            lots = math.floor(SLOT * r.w * navp / (r.E * 100 * (1 + FEE_B)))
            if lots <= 0:
                continue
            pnl = lots * 100 * (r.E * (1 + FEE_B)) * r.net
            pend[r.x] = pend.get(r.x, 0.0) + pnl
        nav += pend.pop(t, 0.0)
        out[t] = nav
    return pd.Series(out[t0:], index=dates[t0:])


def nav_stats(nav: pd.Series) -> dict:
    r = nav.pct_change().dropna()
    yrs = len(r) / 245
    cagr = (nav.iloc[-1] / nav.iloc[0]) ** (1 / yrs) - 1 if yrs > 0 else float("nan")
    sh = float(r.mean() / r.std() * math.sqrt(245)) if r.std() > 0 else 0.0
    mdd = float((nav / nav.cummax() - 1).min())
    return {"cagr": float(cagr), "sharpe": sh, "mdd": mdd, "ret": float(nav.iloc[-1] / nav.iloc[0] - 1)}


def by_year_nav(nav: pd.Series) -> dict:
    out = {}
    for y, s in nav.groupby(nav.index.year):
        prev = nav[nav.index < s.index[0]]
        s2 = pd.concat([prev.iloc[-1:], s]) if len(prev) else s
        out[int(y)] = nav_stats(s2)
    return out


def placebo(M: Market, C: pd.DataFrame, days_t: np.ndarray, real_mean: float, rng) -> dict:
    """One random buyable universe name per traded evening, same exit/costs, N_PLACEBO draws."""
    pools = []
    Cg = {int(t): g["ni"].to_numpy() for t, g in C.groupby("ti")}
    for t in days_t:
        nets = []
        for ni in Cg.get(int(t), []):
            e, why = M.fill(int(t), ni)
            if why == "ok":
                nets.append(M.trade(e, ni)["net"])
        pools.append(np.asarray(nets) if nets else np.asarray([0.0]))
    means = np.empty(N_PLACEBO)
    for i in range(N_PLACEBO):
        means[i] = np.mean([p[rng.integers(len(p))] for p in pools])
    return {"pct": float(100 * np.mean(means < real_mean)), "p95": float(np.percentile(means, 95)), "median": float(np.median(means)),
            "pool_mean": float(np.mean([p.mean() for p in pools]))}


def audit_ara(P: AM.Panel, M: Market) -> dict:
    ok = np.isfinite(P.high) & np.isfinite(P.prev) & (P.prev > 0)
    out = {}
    for y in range(2020, int(P.dates[-1].year) + 1):
        rows = (P.dates.year == y)
        mm = ok[rows] & np.isin(M.bd[rows], [1, 2])
        hi, ara = P.high[rows], M.ara[rows]
        above = mm & (hi > ara + 1e-6)
        at = mm & (np.abs(hi - ara) < 1e-6)
        ab = ok[rows] & np.isin(M.bd[rows], [3, 4])
        out[y] = {"main_rows": int(mm.sum()), "high_above_ara": int(above.sum()), "high_at_ara": int(at.sum()),
                  "acc_rows": int(ab.sum()), "acc_above": int((ab & (hi > M.ara[rows] + 1e-6)).sum())}
    return out


# --------------------------------------------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--end", default="2026-09-25")
    ap.add_argument("--no-store", action="store_true")
    ap.add_argument("--refit", action="store_true")
    a = ap.parse_args()
    end = date.fromisoformat(a.end)
    t0 = time.time()
    log = lambda s: print(s, flush=True)  # noqa: E731
    conn = psycopg.connect(dsn())
    df = load(conn, end)
    log(f"loaded {len(df):,} rows in {time.time() - t0:.0f}s")
    P = AM.Panel(df.drop(columns=["osrc"]))
    M = Market(P, df)
    if os.path.exists(OOF_CACHE) and not a.refit:
        C = pickle.load(open(OOF_CACHE, "rb"))
        log(f"OOF scores from cache {OOF_CACHE}")
    else:
        C = oof_scores(P, log)
        pickle.dump(C, open(OOF_CACHE, "wb"))
    C = C[C["close"] * 100 <= SLOT * CAPITAL].copy()                    # one lot fits the Rp 2 M slot
    res = {"end": str(end), "audit": audit_ara(P, M), "arms": {}}
    pk_lock, pk_ens = picks_of(C, "p_lock"), picks_of(C, "s_ens")
    res["evenings"] = len(pk_lock)
    res["top_locked_eve"] = float(np.mean([l[0][3] > 0 for l in pk_lock.values()]))
    arms = {"main": (pk_lock, "main", {}), "fallback": (pk_lock, "fallback", {}), "top3": (pk_lock, "top3", {}),
            "tp10": (pk_lock, "main", {"tp": 0.10}), "nextopen": (pk_lock, "main", {"exit_": "next_open"}),
            "gate10": (pk_lock, "gate10", {}), "ens": (pk_ens, "main", {})}
    trades = {}
    for name, (pk, arm, kw) in arms.items():
        tr, reasons = run_arm(M, pk, arm, **kw)
        trades[name] = tr
        nav = sleeve(tr, P.dates)
        A = {"reasons": reasons, "all": summarize(tr), "nav": nav_stats(nav), "nav_by_year": by_year_nav(nav),
             "by_year": {int(y): summarize(g) for y, g in tr.groupby("year")} if len(tr) else {},
             "primary": summarize(tr[(tr["d"] >= PRIMARY_FROM) & (tr["src"] == 1)]) if len(tr) else {"n": 0},
             "y25_yahoo": summarize(tr[(tr["d"] >= PRIMARY_FROM) & (tr["src"] != 1)]) if len(tr) else {"n": 0},
             "secondary": summarize(tr[tr["d"] < PRIMARY_FROM]) if len(tr) else {"n": 0}}
        res["arms"][name] = A
        log(f"{name:9s} n {A['all'].get('n', 0)} mean {A['all'].get('mean', float('nan')) * 1e4:+.0f} bps t {A['all'].get('t', float('nan')):.2f} "
            f"hit {A['all'].get('hit', float('nan')):.0%} | primary n {A['primary'].get('n', 0)} | {reasons}")
    main_tr = trades["main"]
    # ---- battery on the main arm
    bat = {}
    for lab, kw in (("open+0", {"slip": 0.0}), ("open+1", {"slip": 1.0}), ("open+2", {"slip": 2.0}), ("costs x1.5", {"slip": 1.5, "fee_mult": 1.5})):
        tr, _ = run_arm(M, pk_lock, "main", **kw)
        bat[lab] = summarize(tr)
    res["battery"] = bat
    rng = np.random.default_rng(SEED)
    res["placebo"] = placebo(M, C, main_tr["t"].to_numpy(), float(main_tr["net"].mean()), rng)
    import equity_screen as ES
    res["dsr"] = float(ES.deflated_sharpe(list(main_tr["net"].to_numpy()), N_BEFORE + N_TRIALS))
    # hit decomposition / context
    res["main_extra"] = {"ara_below_tp_share": float(main_tr["ara_below_tp"].mean()), "how": main_tr["how"].value_counts().to_dict(),
                         "locked_eve_share_traded": float(main_tr["locked_eve"].mean()), "gross_open_close": float(main_tr["gross_open_close"].mean()),
                         "src": main_tr["src"].map({1: "idx", 2: "yahoo", 3: "stockbit"}).value_counts().to_dict(),
                         "p_lock_mean": float(main_tr["p_lock"].mean()),
                         "by_plock": {k: summarize(g) for k, g in main_tr.groupby(pd.cut(main_tr["p_lock"], [0, 0.03, 0.10, 1.0]).astype(str))}}
    # ---- combo effect
    combo = pickle.load(open(NAV_PKL, "rb"))
    rc = combo.pct_change().fillna(0.0)
    comb = {}
    for name in ("main", "gate10", "fallback", "top3"):
        tr = trades[name]
        add = pd.Series(0.0, index=combo.index)
        for r in tr.itertuples():
            dx = P.dates[r.x]
            if dx in add.index:
                add[dx] += SLOT * r.w * r.net
        nav2 = (1 + rc + add).cumprod() * combo.iloc[0]
        s0, s1 = nav_stats(combo), nav_stats(nav2)
        comb[name] = {"combo": s0, "with": s1, "sharpe_up": s1["sharpe"] > s0["sharpe"], "mdd_ok": s1["mdd"] >= s0["mdd"] - 1e-9,
                      "trades_in_window": int(sum(1 for r in tr.itertuples() if P.dates[r.x] in add.index))}
    res["combo"] = comb
    # ---- verdict
    A = res["arms"]["main"]
    yrs = A["by_year"]
    pos_years = sum(1 for v in yrs.values() if v.get("n", 0) and v["mean"] > 0) / max(sum(1 for v in yrs.values() if v.get("n", 0)), 1)
    checks = {"mean>0": A["all"]["mean"] > 0, "t_trade": A["all"]["t"] >= BAR["t"], "t_month": A["all"]["t_month"] >= BAR["t"],
              "years": pos_years >= BAR["years"], "placebo": res["placebo"]["pct"] >= BAR["placebo"],
              "combo": comb["main"]["sharpe_up"] and comb["main"]["mdd_ok"],
              "primary": A["primary"].get("n", 0) >= BAR["min_primary"] and A["primary"].get("mean", -1) > 0}
    verdict = "PASS" if all(checks.values()) else "CLOSED"
    if verdict == "PASS" and A["primary"].get("n", 0) < BAR["min_primary"]:
        verdict = "UNTESTABLE"
    res["verdict"] = {"verdict": verdict, "checks": checks, "pos_years": pos_years}
    res["seconds"] = time.time() - t0
    out = os.path.join(HERE, "IDX_ARA_OPEN_TP_2026-09-26.md")
    json.dump(res, open(out.replace(".md", ".json"), "w"), indent=1, default=str)
    pickle.dump(trades, open(os.path.join(ROOT, "tmp", "ara_open_tp_trades.pkl"), "wb"))
    log(json.dumps({k: res[k] for k in ("verdict", "placebo", "dsr", "battery", "main_extra", "top_locked_eve")}, indent=1, default=str))
    log(json.dumps(res["combo"], indent=1, default=str))
    if not a.no_store:
        from blackheart_ingest.idx import research_store as rs
        summ = {"n_trials": N_TRIALS, "trials_cumulative": N_BEFORE + N_TRIALS, "verdict": res["verdict"], "placebo": res["placebo"], "dsr": res["dsr"],
                "arms": {k: {"all": v["all"], "primary": v["primary"], "reasons": v["reasons"], "nav": v["nav"]} for k, v in res["arms"].items()},
                "battery": bat, "combo": {k: {"sharpe": [v["combo"]["sharpe"], v["with"]["sharpe"]], "mdd": [v["combo"]["mdd"], v["with"]["mdd"]]} for k, v in comb.items()}}
        sid = rs.record_study(conn, STUDY, end, params={"tp": TP, "slot": SLOT, "fees": [FEE_B, FEE_S], "slip_ticks": 1, "test_years": TEST_YEARS,
                                                         "primary_from": str(PRIMARY_FROM.date()), "model": "ara_model (#146) walk-forward OOS, holdout Platt"},
                              summary=summ, names=[], report_path="research/IDX_ARA_OPEN_TP_2026-09-26.md",
                              note=f"menu 45: ARA top-1 open->+20%/ARA/close: {verdict}")
        log(f"stored study #{sid}")
        res["study_id"] = sid
        json.dump(res, open(out.replace(".md", ".json"), "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
