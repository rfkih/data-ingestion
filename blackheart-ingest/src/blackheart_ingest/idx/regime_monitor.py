"""Market-regime monitor: the exchange's effective lower price limit and the volatility regime (Track A3 + A4, 2026-09-26).

Two facts from the research that the desk must see on the day they change, not in a report:
  ARB    (#387) the gap-fade can only trigger while the exchange's lower auto-rejection limit is WIDE. From 2020-04 to 2023-05
         it was ~7 % and a -7 % opening gap was mechanically almost impossible; it has been -15 % / -25 % since 2023-06. If the
         exchange narrows it again (as in the 2020-03 crisis), the gap sleeve goes silent without any error. Estimated here from
         the data itself: the worst close/previous decline of any traded name priced above Rp 200 over the last 10 sessions.
         A worst decline shallower than -7.5 % over 10 sessions = the limit is narrow -> a warning (an action: the gap sleeve
         cannot trade; treat its silence as expected, not as a fault).
  REGIME (#385) a 2-state Gaussian HMM on COMPOSITE daily returns; the FILTERED probability of the high-volatility state at
         the last close (forward pass only). Information for the risk report - the gap sleeve earned its money in the high-vol
         state, the trend sleeve lost there - not an alert (the operator's rule: a regime change is not an action by itself).
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

import numpy as np
import psycopg

from .card import _rows

logger = logging.getLogger(__name__)
ARB_WINDOW = 10
ARB_NARROW = -0.075
MIN_PRICE = 200


def hmm_filtered(x: np.ndarray, iters: int = 200, tol: float = 1e-7) -> dict[str, Any]:
    """2-state Gaussian HMM by EM (the #385 model). State 1 = higher variance. -> params + filtered P(state 1) per observation."""
    from scipy import stats
    n = len(x)
    mu = np.array([x.mean(), x.mean()])
    sd = np.array([x.std() * 0.6, x.std() * 1.8])
    A = np.array([[0.98, 0.02], [0.05, 0.95]])
    pi = np.array([0.8, 0.2])
    ll_old = -np.inf
    al = np.zeros((n, 2))
    for _ in range(iters):
        B = np.column_stack([stats.norm.pdf(x, mu[k], sd[k]) for k in (0, 1)]) + 1e-300
        c = np.zeros(n)
        al[0] = pi * B[0]
        c[0] = al[0].sum()
        al[0] /= c[0]
        for t in range(1, n):
            al[t] = (al[t - 1] @ A) * B[t]
            c[t] = al[t].sum()
            al[t] /= c[t]
        be = np.ones((n, 2))
        for t in range(n - 2, -1, -1):
            be[t] = (A @ (B[t + 1] * be[t + 1])) / c[t + 1]
        g = al * be
        g /= g.sum(1, keepdims=True)
        xi = np.zeros((2, 2))
        for t in range(n - 1):
            m = (al[t][:, None] * A) * (B[t + 1] * be[t + 1])[None, :] / c[t + 1]
            xi += m / m.sum()
        A = xi / xi.sum(1, keepdims=True)
        pi = g[0]
        mu = (g * x[:, None]).sum(0) / g.sum(0)
        sd = np.sqrt((g * (x[:, None] - mu) ** 2).sum(0) / g.sum(0))
        ll = float(np.log(c).sum())
        if abs(ll - ll_old) < tol:
            break
        ll_old = ll
    if sd[0] > sd[1]:
        mu, sd, A, al = mu[::-1], sd[::-1], A[::-1, ::-1], al[:, ::-1]
    return {"mu": mu, "sd": sd, "A": A, "filtered": al[:, 1].copy()}


def arb_state(worst: float | None, days: int) -> str:
    """Pure. The worst decline seen over the window -> 'wide' / 'narrow' / 'unknown'."""
    if worst is None or days < ARB_WINDOW // 2:
        return "unknown"
    return "narrow" if worst > ARB_NARROW else "wide"


def arb_floor(conn: psycopg.Connection, d: date | None = None, sessions: int = ARB_WINDOW) -> dict[str, Any]:
    rows = _rows(conn, """
        WITH days AS (SELECT DISTINCT trade_date FROM idx.daily_summary WHERE trade_date <= COALESCE(%s, current_date)
                       ORDER BY trade_date DESC LIMIT %s)
        SELECT min(s.close / s.previous - 1) AS worst, count(DISTINCT s.trade_date) AS days, max(s.trade_date) AS last,
               count(*) FILTER (WHERE s.close / s.previous - 1 <= -0.069) AS n_limit
          FROM idx.daily_summary s JOIN days USING (trade_date)
         WHERE s.previous > %s AND s.close > 0 AND s.volume > 0""", (d, sessions, MIN_PRICE), ["worst", "days", "last", "n_limit"])
    r = rows[0] if rows else {}
    worst = float(r["worst"]) if r.get("worst") is not None else None
    days = int(r.get("days") or 0)
    return {"worst_decline": worst, "sessions": days, "through": str(r.get("last")) if r.get("last") else None,
            "names_at_7pct": int(r.get("n_limit") or 0), "state": arb_state(worst, days), "gap_fade_possible": arb_state(worst, days) != "narrow"}


def vol_regime(conn: psycopg.Connection, d: date | None = None) -> dict[str, Any]:
    rows = _rows(conn, """SELECT trade_date, close FROM idx.index_daily WHERE index_code = 'COMPOSITE' AND trade_date <= COALESCE(%s, current_date)
                           ORDER BY trade_date""", (d,), ["d", "close"])
    px = np.array([float(r["close"]) for r in rows])
    if len(px) < 250:
        return {"state": "unknown"}
    x = px[1:] / px[:-1] - 1
    h = hmm_filtered(x)
    p = float(h["filtered"][-1])
    return {"p_high_vol": p, "state": "high_vol" if p >= 0.5 else "calm", "through": str(rows[-1]["d"]),
            "vol_ann": {"calm": float(h["sd"][0] * np.sqrt(252)), "high": float(h["sd"][1] * np.sqrt(252))},
            "note": "gap sleeve earned in high-vol, trend lost there (#385)"}


def snapshot(conn: psycopg.Connection, d: date | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, fn in (("arb", arb_floor), ("regime", vol_regime)):
        try:
            out[k] = fn(conn, d)
        except Exception as e:                                            # the risk report must not fail on its context block
            conn.rollback()
            logger.exception("regime monitor %s failed", k)
            out[k] = {"state": "unknown", "error": str(e)[:200]}
    return out


def run(conn: psycopg.Connection, d: date | None = None) -> dict[str, Any]:
    """Nightly (inside risk_check): the snapshot, and one warning a day while the lower limit looks narrow."""
    from . import runlog
    snap = snapshot(conn, d)
    a = snap.get("arb", {})
    if a.get("state") == "narrow":
        runlog.alert(conn, "warning", "risk:desk",
                     f"price-limit regime NARROW: the worst daily decline of any name over {a['sessions']} sessions is "
                     f"{a['worst_decline'] * 100:.1f} % - the gap-fade sleeve cannot trigger while the lower limit is ~7 % (#387); "
                     "its silence is expected, not a fault", kind="risk", payload=snap, dedupe_key=f"arb:narrow:{a.get('through')}")
    return snap
