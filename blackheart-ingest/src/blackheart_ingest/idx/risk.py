"""Book risk report - VaR / ES, beta, concentration, Euler risk budget, liquidity and stress for one ``idx.book``.

    python -m blackheart_ingest.idx.risk --book trend_live [--as-of 2026-09-25] [--json]

Read-only. Standard risk-management arithmetic, no strategy logic. Everything below ``load_inputs`` is a pure function of
DataFrames so the tests run offline; ``load_inputs`` is the only code that touches Postgres.

Conventions (all documented defaults, change them here, not at call sites):
  * Returns: simple daily returns of the adjusted close (``idx.bar.close * adj_factor``) on the COMPOSITE trading calendar.
    A suspended day carries the last close forward (0 return) - that is what the mark does too.
  * Window: the last ``WINDOW`` = 250 sessions up to the as-of date, applied to the CURRENT holdings at CURRENT weights
    (weights = market value / NAV, cash earns 0). Risk numbers are fractions of NAV and rupiah.
  * Short history: a name with fewer than ``MIN_OBS`` = 60 own returns in the window is replaced by its sector index
    (IDX-IC letter -> IDXENERGY ... IDXTRANS) or COMPOSITE when there is no usable sector series, and FLAGGED. A name with
    60..249 returns keeps its own returns and has the days before its first bar filled from the same proxy (flagged
    ``partial``). A proxy carries index volatility, so it understates a small cap's own risk - read the flag.
  * Historical VaR/ES: empirical quantile of the portfolio's 250 one-day returns; 10-day from the overlapping compounded
    10-day returns of the same holdings (241 windows, overlapping - fewer independent tails than it looks).
  * Parametric VaR/ES: normal, zero mean, Ledoit-Wolf (2004) shrunk covariance toward a scaled identity; 10-day = sqrt(10).
  * Euler risk contributions on the parametric sigma: RC_i = w_i (S w)_i / sigma_p, they sum to sigma_p exactly. Effective
    number of positions = 1 / sum(pc_i^2) with pc_i = RC_i / sigma_p.
  * Liquidity: ADV = mean traded value (Rp) of the last 20 sessions (``idx.daily_summary.value``). Days to exit = value /
    (participation x ADV) at 10 % and 20 %. Liquidation cost = half the quoted spread (last bid/offer; one IDX tick when the
    book is one-sided) + square-root impact Y * sigma_daily * sqrt(Q / ADV) with Y = 0.7 (Almgren et al. 2005 / Toth et al.
    2011 order of magnitude; not calibrated on IDX fills).
  * Stress: replay each name's actual adjusted return over (a) the 2020 COVID drawdown (COMPOSITE peak -> trough, trough in
    2020-01..2020-04), (b) the 2025 drawdown (trough in 2025), (c) the worst 5-session COMPOSITE move in the data; a name not
    listed at the window start is proxied by beta x COMPOSITE (flagged). Plus a -10 % COMPOSITE shock through each beta.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import NormalDist
from typing import Any

import numpy as np
import pandas as pd

WINDOW = 250
MIN_OBS = 60
H_LONG = 10
ALPHAS = (0.95, 0.99)
ADV_DAYS = 20
PARTICIPATION = (0.10, 0.20)
IMPACT_Y = 0.7
COMPOSITE = "COMPOSITE"
SHOCK = -0.10
LOT = 100
# IDX-IC sector letter (idx.listing.sector "E. Consumer Cyclicals") -> sector index code in idx.index_daily
SECTOR_INDEX = {"A": "IDXENERGY", "B": "IDXBASIC", "C": "IDXINDUST", "D": "IDXNONCYC", "E": "IDXCYCLIC", "F": "IDXHEALTH",
                "G": "IDXFINANCE", "H": "IDXPROPERT", "I": "IDXTECHNO", "J": "IDXINFRA", "K": "IDXTRANS"}
# Breach limits (`breaches`): what status.py and a future nightly alert flag. Fractions of NAV unless noted.
LIMITS = {"var99_1d": 0.04,        # 1-day historical VaR 99 %
          "max_name": 0.20,        # largest single name
          "max_sector": 0.40,      # largest sector
          "eff_n_min": 3.0,        # effective positions on risk, checked only when the book holds >= 3 names
          "dte_10_max": 3.0,       # days to exit at 10 % of ADV20, any name (sessions)
          "shock10": -0.08}        # P&L of the -10 % COMPOSITE shock through beta


@dataclass
class Inputs:
    """Everything the report needs, as plain frames.

    positions: code, shares, close (raw, on as_of), sector (may be None)
    bars:      code, trade_date, adj_close          (long; history up to as_of)
    index:     trade_date, index_code, close        (COMPOSITE + sector indices)
    liquidity: code, adv20 (Rp), bid, offer, close  (as of the last session <= as_of)
    """
    book: str
    as_of: date
    cash: float
    positions: pd.DataFrame
    bars: pd.DataFrame
    index: pd.DataFrame
    liquidity: pd.DataFrame
    meta: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# pure: statistics
# ---------------------------------------------------------------------------
def ledoit_wolf(x: np.ndarray) -> tuple[np.ndarray, float]:
    """Ledoit-Wolf (2004) shrinkage toward mu*I (same estimator as sklearn.covariance.LedoitWolf). x: T x N returns."""
    x = np.asarray(x, dtype=float)
    t, n = x.shape
    x = x - x.mean(axis=0)
    if n == 1:
        return np.array([[float((x ** 2).mean())]]), 0.0
    s = x.T @ x / t
    mu = np.trace(s) / n
    x2 = x ** 2
    beta_ = float((x2.T @ x2).sum())
    delta_ = float(((x.T @ x) ** 2).sum()) / t ** 2
    delta = (delta_ - 2.0 * mu * np.trace(s) + n * mu ** 2) / n
    beta = min((beta_ / t - delta_) / (n * t), delta)
    shrink = 0.0 if delta <= 0 else float(beta / delta)
    return (1.0 - shrink) * s + shrink * mu * np.eye(n), shrink


def hist_var_es(r: np.ndarray | pd.Series, alpha: float) -> tuple[float, float]:
    """Historical VaR and ES as positive loss fractions. VaR = -q_{1-alpha} (linear interpolation), ES = -mean(r | r <= -VaR)."""
    r = np.asarray(pd.Series(r).dropna(), dtype=float)
    if r.size == 0:
        return float("nan"), float("nan")
    var = -float(np.quantile(r, 1.0 - alpha))
    tail = r[r <= -var]
    es = -float(tail.mean()) if tail.size else var
    return var, es


def parametric_var_es(w: np.ndarray, cov: np.ndarray, alpha: float, horizon: int = 1) -> tuple[float, float, float]:
    """Normal zero-mean VaR / ES of w'r with covariance ``cov`` over ``horizon`` days (sqrt-time). Returns (var, es, sigma_1d)."""
    w = np.asarray(w, dtype=float)
    sigma = math.sqrt(max(float(w @ cov @ w), 0.0))
    z = NormalDist().inv_cdf(alpha)
    s_h = sigma * math.sqrt(horizon)
    return z * s_h, s_h * NormalDist().pdf(z) / (1.0 - alpha), sigma


def euler_contributions(w: np.ndarray, cov: np.ndarray) -> np.ndarray:
    """RC_i = w_i (cov w)_i / sigma_p; sum(RC) == sigma_p (Euler, sigma is 1-homogeneous in w)."""
    w = np.asarray(w, dtype=float)
    sigma = math.sqrt(max(float(w @ cov @ w), 0.0))
    if sigma == 0:
        return np.zeros_like(w)
    return w * (cov @ w) / sigma


def effective_n(contrib: np.ndarray) -> float:
    """1 / sum(p_i^2) with p = contributions normalised to sum 1 (Herfindahl inverse)."""
    c = np.asarray(contrib, dtype=float)
    tot = c.sum()
    if tot == 0:
        return 0.0
    p = c / tot
    return float(1.0 / (p ** 2).sum())


def beta_of(y: pd.Series, x: pd.Series) -> float:
    df = pd.concat([y, x], axis=1).dropna()
    if len(df) < 2 or df.iloc[:, 1].var() == 0:
        return float("nan")
    return float(df.iloc[:, 0].cov(df.iloc[:, 1]) / df.iloc[:, 1].var())


def idx_tick(price: float) -> float:
    """IDX price fraction: 1 / 2 / 5 / 10 / 25 below 200 / 500 / 2,000 / 5,000 / above."""
    for cap, tick in ((200, 1), (500, 2), (2000, 5), (5000, 10)):
        if price < cap:
            return float(tick)
    return 25.0


def days_to_exit(value: float, adv: float, participation: float) -> float:
    if adv is None or not adv or adv <= 0 or (isinstance(adv, float) and math.isnan(adv)):
        return float("inf")
    return float(value) / (participation * float(adv))


def liquidation_cost(value: float, adv: float, sigma_d: float, half_spread: float, y: float = IMPACT_Y) -> float:
    """Rupiah cost of selling ``value``: value * (half_spread + y * sigma_d * sqrt(value / adv))."""
    if adv is None or adv <= 0 or math.isnan(adv):
        return float("nan")
    return float(value) * (half_spread + y * sigma_d * math.sqrt(float(value) / float(adv)))


# ---------------------------------------------------------------------------
# pure: panels and windows
# ---------------------------------------------------------------------------
def _wide(bars: pd.DataFrame, calendar: pd.DatetimeIndex) -> pd.DataFrame:
    """Adjusted close, date x code, on ``calendar``; carried forward after the first bar only (no pre-listing fill)."""
    if bars.empty:
        return pd.DataFrame(index=calendar)
    b = bars.assign(trade_date=pd.to_datetime(bars["trade_date"]), adj_close=bars["adj_close"].astype(float))
    w = b.pivot_table(index="trade_date", columns="code", values="adj_close", aggfunc="last")
    w = w.reindex(calendar.union(w.index)).sort_index().ffill().reindex(calendar)
    first = b.groupby("code")["trade_date"].min()
    for c in w.columns:
        w.loc[w.index < first[c], c] = np.nan
    return w


def _index_wide(index: pd.DataFrame) -> pd.DataFrame:
    i = index.assign(trade_date=pd.to_datetime(index["trade_date"]), close=index["close"].astype(float))
    return i.pivot_table(index="trade_date", columns="index_code", values="close", aggfunc="last").sort_index()


def sector_proxy(sector: str | None, idx_ret: pd.DataFrame, need: int) -> str:
    """Sector index for an IDX-IC sector string when it has ``need`` returns in the window, else COMPOSITE."""
    if sector:
        code = SECTOR_INDEX.get(str(sector).strip()[:1].upper())
        if code and code in idx_ret.columns and idx_ret[code].notna().sum() >= need:
            return code
    return COMPOSITE


def build_panel(codes: list[str], sectors: dict[str, str | None], px: pd.DataFrame, idx_px: pd.DataFrame,
                window: int = WINDOW, min_obs: int = MIN_OBS) -> tuple[pd.DataFrame, pd.Series, dict[str, dict[str, Any]]]:
    """Return (R, market, info): R = window x names daily returns (proxied/filled where needed), market = COMPOSITE returns
    on the same dates, info[code] = {n_obs, proxy, flag}."""
    idx_ret = idx_px.pct_change(fill_method=None).iloc[-window:]
    px_ret = px.reindex(columns=codes).pct_change(fill_method=None).iloc[-window:]
    mkt = idx_ret[COMPOSITE]
    out, info = {}, {}
    for c in codes:
        own = px_ret[c] if c in px_ret.columns else pd.Series(np.nan, index=idx_ret.index)
        n = int(own.notna().sum())
        proxy = sector_proxy(sectors.get(c), idx_ret, min(window, len(idx_ret)) - 5)
        prox = idx_ret[proxy].fillna(mkt).fillna(0.0)
        if n < min_obs:
            out[c], flag = prox, f"proxy {proxy} ({n} obs < {min_obs})"
        elif n < len(own):
            out[c], flag = own.fillna(prox), f"partial: {len(own) - n} days from {proxy}"
        else:
            out[c], flag = own, None
        info[c] = {"n_obs": n, "proxy": proxy if flag else None, "flag": flag}
    return pd.DataFrame(out, index=idx_ret.index), mkt.fillna(0.0), info


def drawdown_episode(comp: pd.Series, trough_from: date, trough_to: date) -> dict[str, Any] | None:
    """COMPOSITE peak -> trough whose trough (lowest close) lies in [trough_from, trough_to]; the peak is the highest close
    in the data before the trough (the running high the fall started from)."""
    comp = comp.dropna()
    seg = comp[(comp.index >= pd.Timestamp(trough_from)) & (comp.index <= pd.Timestamp(trough_to))]
    if seg.empty:
        return None
    t = seg.idxmin()
    before = comp[comp.index <= t]
    p = before.idxmax()
    return {"start": p.date(), "end": t.date(), "composite": float(comp[t] / comp[p] - 1.0)}


def worst_move(comp: pd.Series, days: int = 5) -> dict[str, Any] | None:
    comp = comp.dropna()
    r = comp / comp.shift(days) - 1.0
    if r.dropna().empty:
        return None
    t = r.idxmin()
    s = comp.index[comp.index.get_loc(t) - days]
    return {"start": s.date(), "end": t.date(), "composite": float(r[t])}


def replay(values: pd.Series, px: pd.DataFrame, win: dict[str, Any], betas: pd.Series) -> dict[str, Any]:
    """Book P&L (Rp) holding today's values through a historical window; names without a price at the window start
    move by beta x COMPOSITE (flagged)."""
    s, e = pd.Timestamp(win["start"]), pd.Timestamp(win["end"])
    pnl, proxied, per = 0.0, [], {}
    for c, v in values.items():
        r = None
        if c in px.columns:
            a, b = px[c].asof(s) if s >= px.index[0] else np.nan, px[c].asof(e) if e >= px.index[0] else np.nan
            if pd.notna(a) and pd.notna(b) and a > 0:
                r = float(b / a - 1.0)
        if r is None:
            bt = betas.get(c, 1.0)
            r = float((1.0 if pd.isna(bt) else bt) * win["composite"])
            proxied.append(c)
        per[c] = r
        pnl += float(v) * r
    return {**win, "pnl": pnl, "proxied": proxied, "by_name": per}


# ---------------------------------------------------------------------------
# pure: the report
# ---------------------------------------------------------------------------
def compute_report(inp: Inputs) -> dict[str, Any]:
    pos = inp.positions.copy()
    pos = pos[pos["shares"].astype(float) > 0] if not pos.empty else pos
    cash = float(inp.cash)
    base: dict[str, Any] = {"book": inp.book, "as_of": inp.as_of.isoformat(), "cash": cash, **inp.meta}
    if pos.empty:
        return {**base, "status": "flat", "nav": cash, "gross": 0.0, "gross_pct": 0.0, "n_positions": 0,
                "var": {}, "beta": 0.0, "positions": [], "sectors": [], "stress": [], "liquidity": {"cost": 0.0, "cost_pct": 0.0},
                "flags": []}

    pos["value"] = pos["shares"].astype(float) * pos["close"].astype(float)
    nav = cash + float(pos["value"].sum())
    pos["weight"] = pos["value"] / nav
    codes = list(pos["code"])
    sectors = dict(zip(pos["code"], pos["sector"], strict=True))

    idx_px = _index_wide(inp.index)
    idx_px = idx_px[idx_px.index <= pd.Timestamp(inp.as_of)]
    cal = idx_px.index
    px = _wide(inp.bars, cal)
    R, mkt, info = build_panel(codes, sectors, px, idx_px)
    w = pos.set_index("code")["weight"].reindex(codes).to_numpy()

    # historical
    port = R.to_numpy() @ w
    port_s = pd.Series(port, index=R.index)
    r10 = ((1.0 + R).rolling(H_LONG).apply(np.prod, raw=True) - 1.0).dropna().to_numpy() @ w
    cov, shrink = ledoit_wolf(R.to_numpy())
    var: dict[str, Any] = {"window": len(R), "shrinkage": shrink}
    for a in ALPHAS:
        k = f"{int(a * 100)}"
        h1, e1 = hist_var_es(port, a)
        h10, e10 = hist_var_es(r10, a)
        p1, pe1, sig = parametric_var_es(w, cov, a, 1)
        p10, pe10, _ = parametric_var_es(w, cov, a, H_LONG)
        var[k] = {"hist_1d": h1, "hist_es_1d": e1, "hist_10d": h10, "hist_es_10d": e10,
                  "param_1d": p1, "param_es_1d": pe1, "param_10d": p10, "param_es_10d": pe10}
        var["sigma_1d"] = sig
    var["vol_ann"] = var["sigma_1d"] * math.sqrt(252)

    rc = euler_contributions(w, cov)
    betas = pd.Series({c: beta_of(R[c], mkt) for c in codes})
    beta_nav = float(np.nansum(w * betas.reindex(codes).to_numpy()))
    beta_hist = beta_of(port_s, mkt)

    # liquidity
    liq = inp.liquidity.set_index("code") if not inp.liquidity.empty else pd.DataFrame()
    rows, cost_tot, flags = [], 0.0, []
    sig_d = R.std(ddof=1)
    for i, p in enumerate(pos.itertuples(index=False)):
        c = p.code
        L = liq.loc[c] if c in liq.index else None
        adv = float(L["adv20"]) if L is not None and pd.notna(L["adv20"]) else float("nan")
        bid = float(L["bid"]) if L is not None and pd.notna(L["bid"]) else 0.0
        offer = float(L["offer"]) if L is not None and pd.notna(L["offer"]) else 0.0
        close = float(p.close)
        if bid > 0 and offer > bid:
            half, spread_src = (offer - bid) / (offer + bid), "quote"
        else:
            half, spread_src = idx_tick(close) / close / 2.0, "tick"
        cost = liquidation_cost(p.value, adv, float(sig_d[c]), half)
        cost_tot += 0.0 if math.isnan(cost) else cost
        fl = [f for f in (info[c]["flag"], None if spread_src == "quote" else "one-sided book: spread = 1 tick") if f]
        if math.isnan(adv):
            fl.append("no ADV")
        rows.append({"code": c, "sector": sectors.get(c), "shares": float(p.shares), "close": close, "value": float(p.value),
                     "weight": float(p.weight), "beta": float(betas[c]), "vol_ann": float(sig_d[c]) * math.sqrt(252),
                     "rc": float(rc[i]), "rc_pct": float(rc[i] / var["sigma_1d"]) if var["sigma_1d"] else 0.0,
                     "adv20": adv, "dte_10": days_to_exit(p.value, adv, PARTICIPATION[0]),
                     "dte_20": days_to_exit(p.value, adv, PARTICIPATION[1]), "half_spread": half, "liq_cost": cost,
                     "n_obs": info[c]["n_obs"], "flags": fl})
        flags += [f"{c}: {f}" for f in fl]

    sec = pos.assign(sector=pos["sector"].fillna("unknown")).groupby("sector")["weight"].sum().sort_values(ascending=False)
    top = max(rows, key=lambda r: r["weight"])

    # stress
    comp = idx_px[COMPOSITE]
    values = pos.set_index("code")["value"]
    stress = []
    for name, win in (("COVID 2020", drawdown_episode(comp, date(2020, 1, 1), date(2020, 4, 30))),
                      ("2025 drawdown", drawdown_episode(comp, date(2025, 1, 1), date(2025, 12, 31))),
                      ("worst 5-day", worst_move(comp, 5))):
        if win:
            st = replay(values, px, win, betas)
            stress.append({"name": name, **{k: v for k, v in st.items() if k != "by_name"}, "pnl_pct": st["pnl"] / nav,
                           "start": str(st["start"]), "end": str(st["end"])})
    shock = float(sum(values[c] * (0 if pd.isna(betas[c]) else betas[c]) * SHOCK for c in codes))
    stress.append({"name": f"COMPOSITE {SHOCK:+.0%} via beta", "composite": SHOCK, "pnl": shock, "pnl_pct": shock / nav, "proxied": []})

    gross = float(pos["value"].sum())
    return {**base, "status": "ok", "nav": nav, "gross": gross, "gross_pct": gross / nav, "n_positions": len(rows),
            "var": var, "euler_sum_rc": float(rc.sum()),
            "beta": beta_nav, "beta_hist": beta_hist, "beta_equity": beta_nav / (gross / nav) if gross else 0.0,
            "max_name": {"code": top["code"], "weight": top["weight"]},
            "max_sector": {"sector": sec.index[0], "weight": float(sec.iloc[0])},
            "sectors": [{"sector": k, "weight": float(v)} for k, v in sec.items()],
            "eff_n_risk": effective_n(rc), "eff_n_weight": effective_n(w),
            "liquidity": {"cost": cost_tot, "cost_pct": cost_tot / nav, "impact_y": IMPACT_Y,
                          "max_dte_10": max(r["dte_10"] for r in rows), "max_dte_20": max(r["dte_20"] for r in rows)},
            "positions": sorted(rows, key=lambda r: -r["value"]), "stress": stress, "flags": flags}


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------
def _rp(v: float) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "-"
    a = abs(v)
    if a < 500:
        return "Rp 0"
    s = f"{a / 1e9:.2f}B" if a >= 1e9 else f"{a / 1e6:.1f}M" if a >= 1e6 else f"{a / 1e3:.0f}k"
    return f"{'-' if v < 0 else ''}Rp {s}"


def _p(v: float, d: int = 1, sign: bool = False) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "-"
    return f"{100 * v:+.{d}f}%" if sign else f"{100 * v:.{d}f}%"


def _d(v: float) -> str:
    if math.isinf(v):
        return "inf"
    return f"{v:.0f}d" if v >= 10 else f"{v:.1f}d" if v >= 1 else f"{v:.2f}d" if v >= 0.01 else "<0.01d"


def render(r: dict[str, Any]) -> str:
    L = [f"RISK  {r['book']}  as of {r['as_of']}" + (f"  ({r['label']})" if r.get("label") else "")
         + ("  [ARCHIVED]" if r.get("archived") else "")]
    L.append(f"  NAV {_rp(r['nav'])}  cash {_rp(r['cash'])}  gross {_rp(r['gross'])} ({_p(r['gross_pct'], 0)})  "
             f"{r['n_positions']} pos")
    if r["status"] == "flat":
        L.append("  flat - no positions, nothing at risk")
        return "\n".join(L)
    v = r["var"]
    L += ["", f"VAR / ES  % of NAV (Rp)   window {v['window']}d  LW shrink {v['shrinkage']:.2f}  vol {_p(v['vol_ann'])}/yr",
          f"  {'':14}{'1d VaR':>16}{'1d ES':>16}{'10d VaR':>16}{'10d ES':>16}"]
    for a in ("95", "99"):
        x = v[a]
        for kind, keys in (("hist", ("hist_1d", "hist_es_1d", "hist_10d", "hist_es_10d")),
                           ("param", ("param_1d", "param_es_1d", "param_10d", "param_es_10d"))):
            cells = "".join(f"{_p(x[k], 2) + ' ' + _rp(x[k] * r['nav']).replace('Rp ', ''):>16}" for k in keys)
            L.append(f"  {a}% {kind:<10}{cells}")
    L += ["", f"EXPOSURE  beta(NAV) {r['beta']:.2f}  beta(hist) {r['beta_hist']:.2f}  beta(equity) {r['beta_equity']:.2f}  "
              f"eff.N risk {r['eff_n_risk']:.1f} / weight {r['eff_n_weight']:.1f}",
          f"  largest name {r['max_name']['code']} {_p(r['max_name']['weight'])}   largest sector {r['max_sector']['sector']} "
          f"{_p(r['max_sector']['weight'])}"]
    L += ["", f"POSITIONS  {'value':>9} {'wt':>6} {'beta':>5} {'vol':>5} {'risk%':>6} {'ADV20':>9} {'exit@10%':>8} {'@20%':>6} {'cost':>8}"]
    for p in r["positions"]:
        L.append(f"  {p['code']:<6}{_rp(p['value']).replace('Rp ', ''):>11} {_p(p['weight']):>6} {p['beta']:>5.2f} "
                 f"{_p(p['vol_ann'], 0):>5} {_p(p['rc_pct']):>6} {_rp(p['adv20']).replace('Rp ', ''):>9} {_d(p['dte_10']):>8} "
                 f"{_d(p['dte_20']):>6} {_rp(p['liq_cost']).replace('Rp ', ''):>8}")
    q = r["liquidity"]
    L.append(f"  liquidation cost {_rp(q['cost'])} ({_p(q['cost_pct'], 2)} NAV; spread/2 + {q['impact_y']} sigma sqrt(Q/ADV))  "
             f"slowest exit {_d(q['max_dte_10'])} @10% ADV")
    L += ["", "STRESS  (today's book through the window)"]
    for s in r["stress"]:
        span = f"{s['start']}..{s['end']}" if s.get("start") else ""
        px = f"  proxied: {','.join(s['proxied'])}" if s.get("proxied") else ""
        L.append(f"  {s['name']:<26}{span:<23} COMP {_p(s['composite'], 1, True):>7}  book {_rp(s['pnl']):>12} "
                 f"({_p(s['pnl_pct'], 1, True)}){px}")
    if r["flags"]:
        L += ["", "FLAGS"] + [f"  {f}" for f in r["flags"]]
    return "\n".join(L)


def _jsonable(o: Any) -> Any:
    if isinstance(o, dict):
        return {k: _jsonable(v) for k, v in o.items()}
    if isinstance(o, list | tuple):
        return [_jsonable(v) for v in o]
    if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
        return None
    if isinstance(o, np.floating | np.integer):
        return _jsonable(o.item())
    return o


# ---------------------------------------------------------------------------
# thin DB loader (read-only)
# ---------------------------------------------------------------------------
def _q(conn: Any, sql: str, params: tuple) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
        cols = [d.name for d in cur.description]
    return pd.DataFrame([list(r.values()) if isinstance(r, dict) else list(r) for r in rows], columns=cols)


def load_inputs(conn: Any, book: str, as_of: date | None = None) -> Inputs:
    b = _q(conn, "SELECT book, cash, label, archived_at, status FROM idx.book WHERE book = %s", (book,))
    if b.empty:
        raise ValueError(f"no book {book!r}")
    last = _q(conn, "SELECT max(trade_date) AS d FROM idx.index_daily WHERE index_code = %s AND trade_date <= %s",
              (COMPOSITE, as_of or date.today()))["d"].iloc[0]
    as_of = last
    nav_last = _q(conn, "SELECT max(trade_date) AS d FROM idx.book_nav WHERE book = %s", (book,))["d"].iloc[0]
    if nav_last is None or as_of >= nav_last:           # today: the live position table and the live cash
        pos = _q(conn, "SELECT code, lots FROM idx.position WHERE book = %s AND lots > 0", (book,))
        cash = float(b["cash"].iloc[0])
    else:                                               # a past date: replay the fills, cash from that day's NAV row
        from .book import positions_asof
        held = positions_asof(conn, book, as_of)
        pos = pd.DataFrame([{"code": c, "lots": p["lots"]} for c, p in held.items() if p and float(p["lots"]) > 0],
                           columns=["code", "lots"])
        c = _q(conn, "SELECT cash FROM idx.book_nav WHERE book = %s AND trade_date <= %s ORDER BY trade_date DESC LIMIT 1", (book, as_of))
        cash = float(c["cash"].iloc[0]) if not c.empty else float(b["cash"].iloc[0])
    codes = list(pos["code"])
    if codes:
        marks = _q(conn, """SELECT DISTINCT ON (code) code, close FROM idx.bar WHERE code = ANY(%s) AND trade_date <= %s
                            ORDER BY code, trade_date DESC""", (codes, as_of))
        sec = _q(conn, "SELECT code, sector FROM idx.listing WHERE code = ANY(%s)", (codes,))
        pos = (pos.merge(marks, on="code", how="left").merge(sec, on="code", how="left")
               .assign(shares=lambda d: d["lots"].astype(float) * LOT, close=lambda d: d["close"].astype(float)))
        bars = _q(conn, """SELECT code, trade_date, close * adj_factor AS adj_close FROM idx.bar
                           WHERE code = ANY(%s) AND trade_date <= %s ORDER BY code, trade_date""", (codes, as_of))
        liq = _q(conn, """
            WITH s AS (SELECT code, trade_date, value, bid, offer, close,
                              row_number() OVER (PARTITION BY code ORDER BY trade_date DESC) AS rn
                         FROM idx.daily_summary WHERE code = ANY(%s) AND trade_date <= %s AND trade_date > %s)
            SELECT code, avg(value) FILTER (WHERE rn <= %s) AS adv20, max(bid) FILTER (WHERE rn = 1) AS bid,
                   max(offer) FILTER (WHERE rn = 1) AS offer, max(close) FILTER (WHERE rn = 1) AS close
              FROM s GROUP BY code""", (codes, as_of, as_of - timedelta(days=60), ADV_DAYS))
        for col in ("adv20", "bid", "offer", "close"):
            liq[col] = liq[col].astype(float)
    else:
        pos = pd.DataFrame(columns=["code", "shares", "close", "sector"])
        bars = pd.DataFrame(columns=["code", "trade_date", "adj_close"])
        liq = pd.DataFrame(columns=["code", "adv20", "bid", "offer", "close"])
    index = _q(conn, """SELECT trade_date, index_code, close FROM idx.index_daily
                        WHERE (index_code = %s OR index_code = ANY(%s)) AND trade_date <= %s ORDER BY trade_date""",
               (COMPOSITE, list(SECTOR_INDEX.values()), as_of))
    return Inputs(book=book, as_of=as_of, cash=cash, positions=pos[["code", "shares", "close", "sector"]] if codes else pos,
                  bars=bars, index=index, liquidity=liq,
                  meta={"label": b["label"].iloc[0], "archived": b["archived_at"].iloc[0] is not None})


def active_books(conn: Any) -> list[str]:
    """Books not archived, real ones first - what `idx risk` with no --book and the API's list report on."""
    b = _q(conn, "SELECT book, status FROM idx.book WHERE archived_at IS NULL ORDER BY (status = 'paper'), book", ())
    return b["book"].tolist()


def breaches(r: dict[str, Any], limits: dict[str, float] = LIMITS) -> list[str]:
    """Plain-language list of LIMITS a report breaks (empty = within limits). A flat book breaks nothing; a proxied name
    is listed because its risk is understated."""
    if r.get("status") == "flat":
        return []
    out = []
    v99 = ((r.get("var") or {}).get("99") or {}).get("hist_1d")
    if v99 is not None and v99 > limits["var99_1d"]:
        out.append(f"1-day VaR99 {v99:.1%} > {limits['var99_1d']:.0%}")
    mn, ms = r.get("max_name") or {}, r.get("max_sector") or {}
    if (mn.get("weight") or 0) > limits["max_name"]:
        out.append(f"{mn.get('code')} is {mn['weight']:.0%} of NAV > {limits['max_name']:.0%}")
    if (ms.get("weight") or 0) > limits["max_sector"]:
        out.append(f"sector {ms.get('sector')} is {ms['weight']:.0%} of NAV > {limits['max_sector']:.0%}")
    if (r.get("n_positions") or 0) >= 3 and (r.get("eff_n_risk") or 99) < limits["eff_n_min"]:
        out.append(f"effective positions {r['eff_n_risk']:.1f} < {limits['eff_n_min']:.0f}")
    slow = [p["code"] for p in r.get("positions") or [] if (p.get("dte_10") or 0) > limits["dte_10_max"]]
    if slow:
        out.append(f"slow to exit (> {limits['dte_10_max']:.0f} sessions at 10 % ADV): {', '.join(slow)}")
    shock = next((s.get("pnl_pct") for s in r.get("stress") or [] if str(s.get("name", "")).startswith("COMPOSITE")), None)
    if shock is not None and shock < limits["shock10"]:
        out.append(f"COMPOSITE -10 % shock costs {shock:.1%} < {limits['shock10']:.0%}")
    proxied = [p["code"] for p in r.get("positions") or [] if p.get("flags")]
    if proxied:
        out.append(f"risk understated, history proxied: {', '.join(proxied)}")
    return out


def report(conn: Any, book: str, as_of: date | None = None) -> dict[str, Any]:
    """One book's report as plain JSON-able data with its `breaches` (the API and the CLI call this)."""
    r = _jsonable(compute_report(load_inputs(conn, book, as_of)))
    r["breaches"] = breaches(r)
    return r


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m blackheart_ingest.idx.risk", description="Book risk report (read-only).")
    ap.add_argument("--book", required=True)
    ap.add_argument("--as-of", type=date.fromisoformat, default=None)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass
    from ..shared.db import get_connection
    with get_connection() as conn:
        conn.read_only = True   # takes effect on the next transaction: this report never writes
        rep = compute_report(load_inputs(conn, a.book, a.as_of))
        conn.rollback()
    print(json.dumps(_jsonable(rep), indent=1, default=str) if a.json else render(rep))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
