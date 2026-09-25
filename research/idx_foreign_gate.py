#!/usr/bin/env python3
"""IDX Track B5 / menu 40 - foreign net flow as a GATE on the deployed combo book's existing entries (not its own strategy).

Foreign flow as a standalone signal is closed (#14/#16 swing fflow_10/20: net -0.9 %/trade; OVERLAYS 09-12 B: the Q5-Q1 spread
lives only in large caps, on the sell side, and is not tradeable long-only; BANDAR 09-17: 'asing' class 0/2). What was never
tested is the one use OVERLAYS 09-12 A called promising - a cheap VETO on entries - on the books that are actually deployed:
trend `small` (+ IHSG<MA200 gate), the ML cost-aware sleeve with the +5 %/10 d confirmation, and gap-fade.

Same engine, trades and costs as the deployed combo (idx_combo_rupiah trade lists; idx_alloc_frontier.engine with the deployed
sizing gap 10 % / trend 5 % / ML 5 % of NAV per trade and the 30 % cash floor), 2022-01 -> 2026-09-16.

Signals (idx.daily_summary; foreign_buy/foreign_sell are SHARES -> Rp = shares x close). Information for an entry on day t is
taken from the summary of day t-1 or earlier (trend/ML enter at the close of t, gap-fade at the open of t):
  f_n      per-name net foreign value over n days / traded value over n days (flow share)
  fl_n     per-name net foreign shares over n days / listed shares (float scaling; tradeable_shares == listed_shares here)
  q(.)     cross-sectional percentile of the signal on that day, among names with foreign activity in the window
  mkt_n    market-wide net foreign value over n days / market value over n days (regime)

PRE-REGISTERED ARMS (10 trials; cumulative 893 + 10 = 903 -> range 893..902):
  T1 trend_veto_q20     skip trend entries whose q(f_20) <= 0.20 (heavy foreign selling)
  T2 trend_pos20        take trend entries only when f_20 > 0 (the OVERLAYS 09-12 A rule)
  M1 ml_veto_q20        skip ML entries whose q(f_20) <= 0.20
  M2 ml_pos20           take ML entries only when f_20 > 0
  G1 gap_veto_f5q20     skip gap-down events whose q(f_5) <= 0.20 (foreigners dumping into the gap)
  G2 gap_veto_fl20q20   skip gap-down events whose q(fl_20) <= 0.20 (float-scaled)
  R1 trend_mkt_instead  trend book re-simulated with 'mkt_20 < 0 -> no new entry' INSTEAD of IHSG<MA200
  R2 trend_mkt_along    trend book re-simulated with both gates (off if either is off)
  R3 ml_mkt             skip ML entries while mkt_20 < 0
  R4 gap_mkt            skip gap-fade events while mkt_20 < 0
Per-name gates filter the sleeve's existing trade list (the replayed trades); R1/R2 re-run the trend K-10 simulator because the
deployed regime gate lives inside it.

READING RULE (pre-registered): a gate IMPROVES its sleeve (sleeve alone on the engine, deployed sizing + cash floor) if
Sharpe up AND mDD not deeper AND CAGR >= 0.9 x ungated in 2 of 2 halves (split at the median entry date of the sleeve's
ungated trades), AND the full-window Sharpe sits at >= 95th pct of 200 placebos (per-name: drop the same NUMBER of trades at
random; regime: the same mask circularly shifted by a random offset). Also reported: 4 neighbours (window x0.5 / x2, threshold
looser / tighter), fees x1.5 (+0.5 x round-trip ticks on gap-fade), DSR at cumulative N = 903, the effect on the combined book.
READ-ONLY; one idx.study row ('foreign_gate').
"""
from __future__ import annotations

import math
import os
import pickle
import re
import sys
from datetime import date
from statistics import NormalDist

import numpy as np
import pandas as pd
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blackheart-ingest", "src"))
os.environ.setdefault("IDX_ML_CACHE", os.path.join(ROOT, "tmp", "ml_strategy_cache.pkl"))
os.environ.setdefault("IDX_EXIT_CACHE", os.path.join(ROOT, "tmp", "exit_cache.pkl"))
import idx_alloc_frontier as AF  # noqa: E402
import idx_beyond as BY  # noqa: E402
import idx_combo_rupiah as CR  # noqa: E402
import idx_exit as E  # noqa: E402
import idx_ml_strategy as M  # noqa: E402
import idx_swing2 as S  # noqa: E402
from blackheart_ingest.idx import research_store as rs  # noqa: E402
from blackheart_ingest.idx.ml import common  # noqa: E402

N_BEFORE = 893
STUDY = "foreign_gate"
DEPLOYED = {"gap": 0.10, "trend": 0.05, "ML": 0.05}
CASH_FLOOR = 0.30
N_PLACEBO = int(os.environ.get("FG_PLACEBO", "200"))
SEED = 40
INPUTS = os.path.join(ROOT, "research-scratch", "foreign_gate_inputs.pkl")
SLEEVE = {"T1": "trend", "T2": "trend", "M1": "ML", "M2": "ML", "G1": "gap", "G2": "gap", "R1": "trend", "R2": "trend", "R3": "ML", "R4": "gap"}
NAMES = {"T1": "trend_veto_q20", "T2": "trend_pos20", "M1": "ml_veto_q20", "M2": "ml_pos20", "G1": "gap_veto_f5q20", "G2": "gap_veto_fl20q20",
         "R1": "trend_mkt_instead", "R2": "trend_mkt_along", "R3": "ml_mkt", "R4": "gap_mkt"}
# arm spec: (kind, window, threshold); kind q = veto when pct rank <= thr; pos = keep when f > thr; fl = float q veto; mkt = off when mkt < thr
SPEC = {"T1": ("q", 20, 0.20), "T2": ("pos", 20, 0.0), "M1": ("q", 20, 0.20), "M2": ("pos", 20, 0.0), "G1": ("q", 5, 0.20), "G2": ("fl", 20, 0.20),
        "R1": ("mkt_instead", 20, 0.0), "R2": ("mkt_along", 20, 0.0), "R3": ("mkt", 20, 0.0), "R4": ("mkt", 20, 0.0)}


def neighbours(spec):
    kind, w, thr = spec
    ws = [max(2, w // 2), w * 2]
    if kind in ("q", "fl"):
        ts = [0.10, 0.33]
    elif kind == "pos":
        ts = [-0.05, 0.05]
    else:
        ts = [-0.02, 0.02]
    return [(kind, ws[0], thr), (kind, ws[1], thr), (kind, w, ts[0]), (kind, w, ts[1])]


def dsn() -> str:
    if os.environ.get("INGEST_DB_DSN"):
        return os.environ["INGEST_DB_DSN"]
    env = dict(re.findall(r"^([A-Z_]+)=(.*)$", open(os.path.join(ROOT, "blackheart-ingest", "idx-local.env")).read(), re.M))
    os.environ["INGEST_DB_DSN"] = env["INGEST_DB_DSN"].strip().strip('"')
    return os.environ["INGEST_DB_DSN"]


def deflated_sharpe(r: np.ndarray, n_trials: int) -> float:
    r = np.asarray(r, float)
    n = len(r)
    sd = r.std()
    if n < 10 or sd == 0:
        return 0.0
    sr = r.mean() / sd
    sk = ((r - r.mean()) ** 3).mean() / sd ** 3
    ku = ((r - r.mean()) ** 4).mean() / sd ** 4
    Z, e = NormalDist(), 0.5772156649015329
    v = (1 - sk * sr + (ku - 1) / 4.0 * sr ** 2) / (n - 1)
    if v <= 0:
        return 0.0
    emax = Z.inv_cdf(1 - 1.0 / n_trials) * (1 - e) + Z.inv_cdf(1 - 1.0 / (n_trials * math.e)) * e
    return Z.cdf((sr - math.sqrt(v) * emax) / math.sqrt(v))


# ---- foreign-flow panels ------------------------------------------------------------------------------------------------------
def flow_panels(d: str) -> dict:
    with psycopg.connect(d) as conn:
        df = pd.DataFrame(conn.execute("""SELECT trade_date, code, close::float8, value::float8, foreign_buy::float8 fb, foreign_sell::float8 fs,
                                                 listed_shares::float8 ls FROM idx.daily_summary WHERE trade_date >= '2020-01-01'""").fetchall(),
                          columns=["d", "code", "close", "value", "fb", "fs", "ls"])
    df["d"] = pd.to_datetime(df["d"])
    df["net_sh"] = df["fb"] - df["fs"]
    df["net_val"] = df["net_sh"] * df["close"]
    df["fvol"] = (df["fb"] + df["fs"]) * df["close"]
    w = lambda c: df.pivot(index="d", columns="code", values=c).sort_index()  # noqa: E731
    return {"net_val": w("net_val").fillna(0.0), "value": w("value").fillna(0.0), "net_sh": w("net_sh").fillna(0.0), "ls": w("ls").ffill(),
            "fvol": w("fvol").fillna(0.0)}


def signal(FP: dict, kind: str, win: int) -> pd.DataFrame | pd.Series:
    """Value on day d = information through the close of d (the caller looks it up at t-1 for an entry on t)."""
    nv = FP["net_val"].rolling(win, min_periods=win).sum()
    if kind in ("mkt", "mkt_instead", "mkt_along"):
        return nv.sum(axis=1) / FP["value"].rolling(win, min_periods=win).sum().sum(axis=1)
    active = FP["fvol"].rolling(win, min_periods=win).sum() > 0
    if kind == "fl":
        f = FP["net_sh"].rolling(win, min_periods=win).sum() / FP["ls"].replace(0, np.nan)
    else:
        f = nv / FP["value"].rolling(win, min_periods=win).sum().replace(0, np.nan)
    f = f.where(active)
    if kind in ("q", "fl"):
        return f.rank(axis=1, pct=True)
    return f


def lookup_prev(sig: pd.DataFrame | pd.Series, dates: pd.DatetimeIndex) -> np.ndarray | pd.DataFrame:
    """sig re-indexed so that row t holds the value known at the close of the trading day before dates[t]."""
    s = sig.reindex(sig.index.union(dates)).ffill()
    prev = pd.Series(dates).shift(1).to_numpy()
    out = s.reindex(prev)
    out.index = dates
    return out


def keep_fn(spec, FP, dates):
    kind, w, thr = spec
    sig = lookup_prev(signal(FP, kind, w), dates)
    if kind in ("mkt", "mkt_instead", "mkt_along"):
        off = (sig.to_numpy(float) < thr)                                   # NaN (warm-up) -> not off
        return lambda x, off=off: not off[x.get("t_in", x.get("t"))]
    colpos = {c: i for i, c in enumerate(sig.columns)}
    V = sig.to_numpy(float)

    def keep(x):
        t = x.get("t_in", x.get("t"))
        j = colpos.get(x["code"])
        v = V[t, j] if j is not None else np.nan
        if not np.isfinite(v):
            return True                                                      # no foreign activity / no data -> no veto
        return v > thr
    return keep


# ---- trend re-simulation with an extra / replacement gate (copy of idx_combo_rupiah.trend_trades, gate parameterised) ----------
class TrendSim:
    def __init__(self, d: str, dates):
        P, unis, comp, Hp, Lp = E.load_all(d, os.environ.get("IDX_EXIT_CACHE"))
        self.c_in, self.c_out = S.costs(P)
        adj, vol = P["adj"], P["volume"]
        self.d_tr = adj.index
        self.cols = adj.columns
        self.A, self.H, self.L = adj.to_numpy(float), Hp.to_numpy(float), Lp.to_numpy(float)
        ma200 = adj.rolling(200, min_periods=200).mean()
        self.vr = vol / vol.rolling(20, min_periods=20).median()
        hi = adj.rolling(60, min_periods=60).max()
        self.raw_entry = ((adj >= hi) & (adj > ma200) & (self.vr >= 1.5)).to_numpy(bool) & np.asarray(self.d_tr >= CR.START)[:, None]
        self.ihsg_off = BY.regime_off_mask(comp, self.d_tr)
        prev = adj.shift(1)
        tr = pd.concat([Hp - Lp, (Hp - prev).abs(), (Lp - prev).abs()], axis=1, keys=["a", "b", "c"]).T.groupby(level=1).max().T.reindex(columns=adj.columns)
        ATR = tr.ewm(alpha=1 / 20, adjust=False, min_periods=20).mean().to_numpy(float)
        ma20, ma50 = (adj.rolling(n, min_periods=n).mean().to_numpy(float) for n in (20, 50))
        dd = adj.diff()
        up = dd.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
        dn = (-dd.clip(upper=0)).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
        RSI = (100 - 100 / (1 + up / dn.replace(0, np.nan))).to_numpy(float)
        LO10 = Lp.shift(1).rolling(10, min_periods=10).min().to_numpy(float)
        LO20 = Lp.shift(1).rolling(20, min_periods=20).min().to_numpy(float)
        self.rule = E.make_rules(self.A, self.H, self.L, ATR, ma20, ma50, RSI, LO10, LO20)["trail10"]
        self.small = (unis["LIQ"] & ~unis["BLUE"]).to_numpy(bool)
        self.pos = {x: i for i, x in enumerate(dates)}

    def trades(self, off: np.ndarray) -> list[dict]:
        """off: bool per d_tr day (signal-close information) -> no new entry signalled that day."""
        entry = self.raw_entry & ~off[:, None]
        _, trs, _ = E.run_book(self.A, self.H, self.L, self.c_in, self.c_out, entry, self.vr.to_numpy(float), self.rule, self.small)
        out = []
        for tup in trs:
            e, j, hold = tup[0], tup[1], tup[4]
            if e + 1 + hold >= len(self.d_tr):
                continue
            d_in, d_out = self.d_tr[e + 1], self.d_tr[e + 1 + hold]
            if d_in in self.pos and d_out in self.pos:
                out.append({"strat": "trend", "code": self.cols[j], "t_in": self.pos[d_in], "t_out": self.pos[d_out]})
        return out

    def mkt_off(self, FP, win, thr) -> np.ndarray:
        m = signal(FP, "mkt", win)
        m = m.reindex(m.index.union(self.d_tr)).ffill().reindex(self.d_tr).to_numpy(float)
        return m < thr                                                       # info through the signal close e; entry at close e+1


# ---- evaluation ---------------------------------------------------------------------------------------------------------------
def run(X, lists: dict, pct=DEPLOYED, fee_mult: float = 1.0):
    fb, fs = CR.FEE_BUY, CR.FEE_SELL
    CR.FEE_BUY, CR.FEE_SELL = fb * fee_mult, fs * fee_mult
    try:
        nav, _ = AF.engine(X["dates"], X["codes"], X["A"], X["raw"], X["offer"], X["bid"], lists.get("ML", []), lists.get("trend", []),
                           lists.get("gap", []), pct, cash_floor=CASH_FLOOR)
    finally:
        CR.FEE_BUY, CR.FEE_SELL = fb, fs
    return nav


def st(nav: pd.Series) -> dict:
    r = nav.pct_change().fillna(0.0)
    yrs = max((nav.index[-1] - nav.index[0]).days / 365.25, 1e-9)
    eq = nav / nav.iloc[0]
    return {"cagr": float(eq.iloc[-1] ** (1 / yrs) - 1), "sharpe": float(r.mean() / r.std() * np.sqrt(252)) if r.std() > 0 else 0.0,
            "mdd": float((eq / eq.cummax() - 1).min())}


def halves(nav: pd.Series, split: pd.Timestamp) -> list[dict]:
    return [st(nav[nav.index < split]), st(nav[nav.index >= split])]


def better(g: dict, u: dict) -> bool:
    return g["sharpe"] > u["sharpe"] and g["mdd"] >= u["mdd"] - 1e-9 and g["cagr"] >= 0.9 * u["cagr"] if u["cagr"] > 0 else \
        g["sharpe"] > u["sharpe"] and g["mdd"] >= u["mdd"] - 1e-9 and g["cagr"] >= u["cagr"]


def gap_costlier(gap: list[dict]) -> list[dict]:
    out = []
    for x in gap:
        tk = common.tick(x["open"]) / x["open"]
        out.append({**x, "net": x["net"] - 0.5 * (CR.FEE_BUY + CR.FEE_SELL + 2 * tk)})
    return out


def build_inputs(d: str) -> dict:
    if os.path.exists(INPUTS):
        return pickle.load(open(INPUTS, "rb"))
    P = pickle.load(open(os.environ["IDX_ML_CACHE"], "rb"))
    P = P[(P["d"] >= "2021-06-01") & (P["d"] <= CR.END)].copy()
    dates = M.wide(P, "close").index
    codes = M.wide(P, "close").columns
    g = lambda c: M.wide(P, c).reindex(index=dates, columns=codes)  # noqa: E731
    A, raw = g("ac").to_numpy(float), g("close").to_numpy(float)
    offer, bid = np.nan_to_num(g("offer").to_numpy(float)), np.nan_to_num(g("bid").to_numpy(float))
    liq = g("liq").fillna(False).astype(bool).to_numpy()
    ml = CR.ml_trades(P, dates, codes, A, raw, offer, bid, liq)
    del P
    tr = CR.trend_trades(d, dates)
    gap = CR.gap_events(d, dates)
    X = {"dates": dates, "codes": codes, "A": A, "raw": raw, "offer": offer, "bid": bid, "ml": ml, "tr": tr, "gap": gap}
    os.makedirs(os.path.dirname(INPUTS), exist_ok=True)
    pickle.dump(X, open(INPUTS, "wb"))
    return X


def main() -> int:
    d = dsn()
    X = build_inputs(d)
    dates = X["dates"]
    base = {"ML": X["ml"], "trend": X["tr"], "gap": X["gap"]}
    M.log(f"events: ML {len(X['ml'])}, trend {len(X['tr'])}, gap {len(X['gap'])}")
    FP = flow_panels(d)
    M.log(f"flow panels {FP['net_val'].shape}")
    TS = TrendSim(d, dates)
    tr_check = TS.trades(TS.ihsg_off)
    M.log(f"trend re-sim check: {len(tr_check)} trades vs combo {len(X['tr'])}")
    assert len(tr_check) == len(X["tr"])
    rng = np.random.default_rng(SEED)
    T = len(dates)

    def gated(arm, spec, lists=base):
        sl = SLEEVE[arm]
        kind, w, thr = spec
        if kind == "mkt_instead":
            return TS.trades(TS.mkt_off(FP, w, thr))
        if kind == "mkt_along":
            return TS.trades(TS.ihsg_off | TS.mkt_off(FP, w, thr))
        k = keep_fn(spec, FP, dates)
        return [x for x in lists[sl] if k(x)]

    # ungated sleeves + combined
    ung = {sl: run(X, {sl: base[sl]}) for sl in ("trend", "ML", "gap")}
    ung_cost = {sl: run(X, {sl: gap_costlier(base[sl]) if sl == "gap" else base[sl]}, fee_mult=1.5) for sl in ("trend", "ML", "gap")}
    comb = run(X, base)
    split = {sl: dates[int(np.median([x.get("t_in", x.get("t")) for x in base[sl]]))] for sl in ("trend", "ML", "gap")}
    for sl in ung:
        M.log(f"ungated {sl}: {st(ung[sl])} split {split[sl].date()}")
    M.log(f"combined ungated: {st(comb)}")

    res = {}
    for arm, spec in SPEC.items():
        sl = SLEEVE[arm]
        L_ = gated(arm, spec)
        nav = run(X, {sl: L_})
        g_full, u_full = st(nav), st(ung[sl])
        gh, uh = halves(nav, split[sl]), halves(ung[sl], split[sl])
        halves_ok = [better(a, b) for a, b in zip(gh, uh)]
        skip = 1 - len(L_) / len(base[sl]) if spec[0] not in ("mkt_instead", "mkt_along") else float("nan")
        # placebo
        pl = []
        if spec[0] in ("mkt", "mkt_instead", "mkt_along"):
            kind, w, thr = spec
            if kind == "mkt":
                off = lookup_prev(signal(FP, "mkt", w), dates).to_numpy(float) < thr
            else:
                off = TS.mkt_off(FP, w, thr)
            for _ in range(N_PLACEBO):
                sh = int(rng.integers(60, len(off) - 60))
                o2 = np.roll(off, sh)
                if kind == "mkt":
                    Lp_ = [x for x in base[sl] if not o2[x.get("t_in", x.get("t"))]]
                elif kind == "mkt_instead":
                    Lp_ = TS.trades(o2)
                else:
                    Lp_ = TS.trades(TS.ihsg_off | o2)
                pl.append(st(run(X, {sl: Lp_}))["sharpe"])
            if kind == "mkt":
                skip = 1 - len(L_) / len(base[sl])
        else:
            n_drop = len(base[sl]) - len(L_)
            for _ in range(N_PLACEBO):
                drop = set(rng.choice(len(base[sl]), n_drop, replace=False).tolist()) if n_drop else set()
                pl.append(st(run(X, {sl: [x for i, x in enumerate(base[sl]) if i not in drop]}))["sharpe"])
        pl = np.array(pl)
        pct_ = float((pl < g_full["sharpe"]).mean() * 100)
        # neighbours (full window, same rule)
        nb = []
        for sp in neighbours(spec):
            n_nav = run(X, {sl: gated(arm, sp)})
            s_ = st(n_nav)
            nb.append({"spec": list(sp), **s_, "pass": better(s_, u_full)})
        # costs x1.5
        Lc = gap_costlier(L_) if sl == "gap" else L_
        c_nav = run(X, {sl: Lc}, fee_mult=1.5)
        c_g, c_u = st(c_nav), st(ung_cost[sl])
        # combined book with this gate on its sleeve
        cl = dict(base)
        cl[sl] = L_
        c_comb = st(run(X, cl))
        r = nav.pct_change().fillna(0.0).to_numpy()
        dsr = deflated_sharpe(r[r != 0], N_BEFORE + len(SPEC))
        improves = all(halves_ok) and pct_ >= 95
        res[arm] = {"name": NAMES[arm], "sleeve": sl, "spec": list(spec), "n": len(L_), "n_ungated": len(base[sl]), "skip": skip, "gated": g_full, "ungated": u_full,
                    "halves_gated": gh, "halves_ungated": uh, "halves_ok": halves_ok, "full_ok": better(g_full, u_full), "placebo_pct": pct_,
                    "placebo_med": float(np.median(pl)), "placebo_p95": float(np.percentile(pl, 95)), "neighbours": nb, "nb_pass": sum(n_["pass"] for n_ in nb),
                    "cost15_gated": c_g, "cost15_ungated": c_u, "cost15_ok": better(c_g, c_u), "combined": c_comb, "dsr": dsr, "improves": improves}
        M.log(f"{arm} {NAMES[arm]:<18} n {len(L_)}/{len(base[sl])} | gated {g_full['cagr'] * 100:.1f}%/{g_full['sharpe']:.2f}/{g_full['mdd'] * 100:.1f}% vs "
              f"{u_full['cagr'] * 100:.1f}%/{u_full['sharpe']:.2f}/{u_full['mdd'] * 100:.1f}% | halves {halves_ok} | placebo pct {pct_:.0f} | nb {res[arm]['nb_pass']}/4 | "
              f"cost {res[arm]['cost15_ok']} | comb {c_comb['cagr'] * 100:.1f}%/{c_comb['sharpe']:.2f}/{c_comb['mdd'] * 100:.1f}% | DSR {dsr:.2f} | {'IMPROVES' if improves else 'no'}")

    write_report(res, ung, comb, split, d)
    return 0


def f3(s: dict) -> str:
    return f"{s['cagr'] * 100:.1f} % / {s['sharpe']:.2f} / {s['mdd'] * 100:.1f} %"


def write_report(res, ung, comb, split, d):
    n_trials = N_BEFORE + len(SPEC)
    L = [f"# IDX Track B5 / menu 40 - foreign net flow as a gate on the deployed combo entries - {date.today()} - 10 trials, cumulative N = {n_trials}", "",
         "Same engine, trade lists and costs as the deployed combo (#168 lists, menu-34 engine, gap 10 % / trend 5 % / ML 5 % of NAV per trade, 30 % cash "
         f"floor), 2022-01 -> {CR.END.date()}. Each sleeve is run alone on the engine, gated vs ungated in the SAME run. Flow for an entry on t is read "
         "from idx.daily_summary of t-1 or earlier. Cells: CAGR / Sharpe / mDD.", "",
         "Ungated references: " + "; ".join(f"{sl} {f3(st(ung[sl]))} (halves split {split[sl].date()})" for sl in ung) + f"; combined book {f3(st(comb))}.", "",
         "## Arms vs ungated (same run)", "",
         "| arm | gate | sleeve | trades kept | gated | ungated | half 1 gated vs ungated | half 2 gated vs ungated | halves | placebo pct (median / p95 Sharpe) | neighbours | fees x1.5 gated vs ungated | combined book | DSR @N | verdict |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for arm, r in res.items():
        L.append(f"| {arm} | {r['name']} | {r['sleeve']} | {r['n']}/{r['n_ungated']} | {f3(r['gated'])} | {f3(r['ungated'])} | {f3(r['halves_gated'][0])} vs {f3(r['halves_ungated'][0])} | "
                 f"{f3(r['halves_gated'][1])} vs {f3(r['halves_ungated'][1])} | {sum(r['halves_ok'])}/2 | {r['placebo_pct']:.0f} ({r['placebo_med']:.2f} / {r['placebo_p95']:.2f}) | "
                 f"{r['nb_pass']}/4 | {f3(r['cost15_gated'])} vs {f3(r['cost15_ungated'])} | {f3(r['combined'])} | {r['dsr']:.2f} | {'IMPROVES' if r['improves'] else 'no'} |")
    L += ["", "## Neighbours (full window, same reading rule vs ungated)", "", "| arm | neighbour (kind, window, threshold) | CAGR / Sharpe / mDD | pass |", "|---|---|---|---|"]
    for arm, r in res.items():
        for n_ in r["neighbours"]:
            L.append(f"| {arm} | {tuple(n_['spec'])} | {f3(n_)} | {'yes' if n_['pass'] else 'no'} |")
    imp = [a for a, r in res.items() if r["improves"]]
    L += ["", "## Verdict", ""]
    for sl in ("trend", "ML", "gap"):
        arms = [a for a in res if res[a]["sleeve"] == sl]
        ok = [a for a in arms if res[a]["improves"]]
        detail = ", ".join("%s halves %d/2, placebo %.0f" % (a, sum(res[a]["halves_ok"]), res[a]["placebo_pct"]) for a in arms)
        head = (", ".join(ok) + " IMPROVES") if ok else "no foreign-flow gate improves it"
        L.append(f"- **{sl}**: {head} ({detail}).")
    text = "\n".join(L)
    out = os.path.join(HERE, "IDX_FOREIGN_GATE_2026-09-25.md")
    if os.path.exists(out):
        prev = open(out, encoding="utf-8").read()
        if "## Reading" in prev:
            text += "\n\n" + prev[prev.index("## Reading"):]
    open(out, "w", encoding="utf-8").write(text + "\n")
    print(text)
    if os.environ.get("FG_RECORD") == "1":
        with psycopg.connect(d) as conn:
            sid = rs.record_study(conn, STUDY, date.today(), params={"trials": {a: NAMES[a] for a in SPEC}, "spec": SPEC, "n_trials_cumulative": n_trials,
                                                                     "deployed": DEPLOYED, "cash_floor": CASH_FLOOR, "n_placebo": N_PLACEBO,
                                                                     "reading_rule": "Sharpe up, mDD not deeper, CAGR>=0.9x in 2/2 halves + placebo>=95 pct"},
                                  summary=common.plain({"arms": res, "improving": imp}), names=[], report_path=out,
                                  note="menu 40 / B5: foreign net flow as a gate on trend, ML and gap-fade entries + market-flow regime gate")
            conn.commit()
        M.log(f"study #{sid} stored")


if __name__ == "__main__":
    sys.exit(main())
