"""The state a name's price is in today - breakout, breakdown, sideways, uptrend, downtrend or neither - as a RULE on its
adjusted closes and volume, never as a forecast (operator, 2026-09-25: "klasifikasi trend sahamnya di sideways atau uptrend
atau breakout volume").

Every threshold is one the desk already uses, so a state here means the same thing as on the other screens:

  breakout    the deployed trend rule's entry test today (idx/trend_book): close = the 60-day high, close above the 200-day
              average, volume >= 1.5x the 20-day median. ``from_base`` marks the ones that left a base60 (below) - study #130
              counted those: 45 % close back inside the base within 5 days.
  breakdown   the mirror: close = the 60-day low, under the 200-day average, volume >= 1.5x.
  sideways    base60 of study #130 on the 60 closes ending today: channel width (max/min - 1) <= 25 %, |net move| <= 15 %,
              efficiency ratio |net| / sum|daily change| <= 0.30.
  uptrend     close > MA50 > MA200 and MA50 higher than 20 days ago.
  downtrend   close < MA50 < MA200 and MA50 lower than 20 days ago.
  transition  none of the above (a name between states, or with too little history - ``why`` says which).
The order above is the priority when two hold (a breakout out of a base is a breakout). ``since`` counts the consecutive
trading days the name has been in today's state. What a state is WORTH is a separate question: studies #69, #130, #132 and
menu BK-1 (research/idx_breakout_filter.py) - the short answer is in ``MEANS``.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd
import psycopg

from . import trend_book as tb

STATES = ("breakout", "breakdown", "sideways", "uptrend", "downtrend", "transition")
BASE_N, BASE_WIDTH, BASE_MOVE, BASE_ER = 60, 0.25, 0.15, 0.30
MA_FAST, SLOPE_N = 50, 20
BARS = int(tb.MA_N) + SLOPE_N + 70                       # enough for MA200, its slope and the 60-day streak
MEANS = ("a reading of the chart by fixed rules, not a forecast. What the states have been worth on IDX 2020-2026: a volume "
         "breakout is a coin flip at 20 days with a fat right tail (45 % fall back into the base within 5 days, study #130); "
         "the trend book makes its money by holding the few that run with a 10 % trailing stop; a sideways name drifts "
         "down unless it pays a dividend (menu 26-27).")


def classify_panel(adj: pd.DataFrame, vol: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """Pure. Wide frames (dates x codes) of adjusted closes and volumes -> (state per cell, the measures behind it)."""
    hi = adj.rolling(tb.HI_N, min_periods=tb.HI_N).max()
    lo = adj.rolling(tb.HI_N, min_periods=tb.HI_N).min()
    ma50 = adj.rolling(MA_FAST, min_periods=MA_FAST).mean()
    ma200 = adj.rolling(tb.MA_N, min_periods=tb.MA_N).mean()
    vr = vol / vol.rolling(tb.VOL_N, min_periods=tb.VOL_N).median().replace(0, np.nan)
    mx = adj.rolling(BASE_N, min_periods=BASE_N).max()
    mn = adj.rolling(BASE_N, min_periods=BASE_N).min()
    width = mx / mn - 1
    net = adj / adj.shift(BASE_N - 1) - 1
    er = (adj - adj.shift(BASE_N - 1)).abs() / adj.diff().abs().rolling(BASE_N - 1, min_periods=BASE_N - 1).sum()
    base = (width <= BASE_WIDTH) & (net.abs() <= BASE_MOVE) & (er <= BASE_ER)
    vx = float(tb.VOL_X)
    breakout = (adj >= hi) & (adj > ma200) & (vr >= vx)
    breakdown = (adj <= lo) & (adj < ma200) & (vr >= vx)
    up = (adj > ma50) & (ma50 > ma200) & (ma50 > ma50.shift(SLOPE_N))
    down = (adj < ma50) & (ma50 < ma200) & (ma50 < ma50.shift(SLOPE_N))
    st = pd.DataFrame("transition", index=adj.index, columns=adj.columns, dtype=object)
    for mask, name in ((down, "downtrend"), (up, "uptrend"), (base, "sideways"), (breakdown, "breakdown"), (breakout, "breakout")):
        st = st.mask(mask.fillna(False), name)                  # later assignments win: the priority is the reverse of this list
    st = st.where(adj.notna())
    measures = {"vr": vr, "hi60": hi, "lo60": lo, "ma50": ma50, "ma200": ma200, "width": width, "net": net, "er": er,
                "from_base": base.shift(1, fill_value=False) & breakout}
    return st, measures


def streak(col: pd.Series) -> int:
    """Consecutive rows at the end of ``col`` equal to its last value."""
    v = col.dropna()
    if v.empty:
        return 0
    last = v.iloc[-1]
    n = 0
    for x in reversed(v.tolist()):
        if x != last:
            break
        n += 1
    return n


def _panel(conn: psycopg.Connection, d: date, codes: list[str] | None) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
    with conn.cursor() as cur:
        cur.execute("""SELECT code, trade_date, close * adj_factor AS adj, volume, value FROM idx.bar
                        WHERE source = 'idx' AND trade_date <= %s AND trade_date >= %s AND (%s::text[] IS NULL OR code = ANY(%s))""",
                    (d, d - timedelta(days=int(BARS * 1.6)), codes, codes))
        rows = [tuple(r.values()) if isinstance(r, dict) else tuple(r) for r in cur.fetchall()]
    df = pd.DataFrame(rows, columns=["code", "trade_date", "adj", "volume", "value"])
    for c in ("adj", "volume", "value"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    adj = df.pivot(index="trade_date", columns="code", values="adj").sort_index()
    vol = df.pivot(index="trade_date", columns="code", values="volume").reindex_like(adj)
    val = df.pivot(index="trade_date", columns="code", values="value").reindex_like(adj)
    v60 = val.tail(60).mean()
    return adj, vol, v60


def _f(x: Any, nd: int = 4) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return round(v, nd) if np.isfinite(v) else None


def _row(code: str, st: pd.DataFrame, m: dict[str, pd.DataFrame], adj: pd.DataFrame, v60: pd.Series) -> dict[str, Any]:
    s = st[code]
    state = s.iloc[-1]
    close = adj[code].iloc[-1]
    n_bars = int(adj[code].notna().sum())
    out = {"code": code, "state": state, "since": streak(s), "close": _f(close, 2), "value_60d": _f(v60.get(code), 0),
           "vol_ratio": _f(m["vr"][code].iloc[-1], 2), "from_base": bool(m["from_base"][code].iloc[-1]),
           "pct_from_60d_high": _f(close / m["hi60"][code].iloc[-1] - 1), "pct_from_ma50": _f(close / m["ma50"][code].iloc[-1] - 1),
           "pct_from_ma200": _f(close / m["ma200"][code].iloc[-1] - 1),
           "base": {"width": _f(m["width"][code].iloc[-1]), "net": _f(m["net"][code].iloc[-1]), "er": _f(m["er"][code].iloc[-1])}}
    if state == "transition" and n_bars < tb.MA_N:
        out["why"] = f"only {n_bars} bars; the 200-day average needs {tb.MA_N}"
    return out


def _last_date(conn: psycopg.Connection) -> date | None:
    with conn.cursor() as cur:
        cur.execute("SELECT max(trade_date) FROM idx.bar WHERE source = 'idx'")
        r = cur.fetchone()
    v = r[0] if isinstance(r, tuple) else (next(iter(r.values())) if r else None)
    return v


def board(conn: psycopg.Connection, d: date | None = None, *, state: str | None = None, min_value: float = 0.0,
          limit: int = 200) -> dict[str, Any]:
    """Every name with a bar on ``d`` (default: the last bar day) -> its state; counts per state; optionally one state only,
    above a 60-day average traded value. Breakouts sort by volume ratio, the rest by traded value."""
    if state and state not in STATES:
        raise ValueError(f"state must be one of {', '.join(STATES)}")
    d = d or _last_date(conn)
    if d is None:
        return {"as_of": None, "counts": {}, "names": [], "means": MEANS}
    adj, vol, v60 = _panel(conn, d, None)
    if adj.empty or adj.index[-1] != d:
        return {"as_of": d.isoformat(), "counts": {}, "names": [], "means": MEANS, "why": "no bars on that day"}
    st, m = classify_panel(adj, vol)
    today = adj.iloc[-1]
    codes = [c for c in adj.columns if pd.notna(today[c]) and (v60.get(c) or 0) >= min_value]
    counts = {s: int(sum(1 for c in codes if st[c].iloc[-1] == s)) for s in STATES}
    pick = [c for c in codes if state is None or st[c].iloc[-1] == state]
    rows = [_row(c, st, m, adj, v60) for c in pick]
    key = (lambda r: -(r["vol_ratio"] or 0)) if state in ("breakout", "breakdown") else (lambda r: -(r["value_60d"] or 0))
    rows.sort(key=key)
    return {"as_of": d.isoformat(), "min_value": min_value, "counts": counts, "state": state, "total": len(pick),
            "names": rows[:limit], "means": MEANS}


def one(conn: psycopg.Connection, code: str, d: date | None = None, history: int = 60) -> dict[str, Any]:
    """One name: today's state with its measures, and the state of each of the last ``history`` trading days."""
    code = code.upper()
    d = d or _last_date(conn)
    adj, vol, v60 = _panel(conn, d, [code]) if d else (pd.DataFrame(), pd.DataFrame(), pd.Series(dtype=float))
    if code not in adj.columns:
        return {"code": code, "as_of": d.isoformat() if d else None, "state": None, "why": "no bars for this name", "means": MEANS}
    st, m = classify_panel(adj, vol)
    out = _row(code, st, m, adj, v60)
    out["as_of"] = adj.index[-1].isoformat() if hasattr(adj.index[-1], "isoformat") else str(adj.index[-1])
    h = st[code].dropna().tail(history)
    out["history"] = [{"date": (i.isoformat() if hasattr(i, "isoformat") else str(i)), "state": v} for i, v in h.items()]
    out["means"] = MEANS
    return out
