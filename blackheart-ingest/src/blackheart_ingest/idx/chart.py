"""What one name looks like right now: candles, the live order book, and where the deployed trend rule stands on it.

This is the read side of the desk's own data - nothing here decides anything and nothing here forecasts a price. Three
pieces, each honest about what it is:

* ``daily``    - adjusted candles from ``idx.bar`` (2020 onwards, 963 names) with the trend rule's own lines drawn on
                 them: the 200-day average, the 60-day high, and the 10 % trailing stop measured from the peak.
* ``intraday`` - one-minute candles from ``idx.feed_bar_1m``, which exists only for the ~136 names the tick collector
                 subscribes to and only since the collector first ran (2026-09-21). A name outside that set is not an
                 error; it simply has no intraday panel.
* ``depth``    - the ten levels each side from ``idx.feed_book``, with the queue imbalance. **The imbalance is an
                 execution-timing readout, not a direction signal.** Study #74 measured its lead at IC 0.23 over 1-5
                 minutes and then measured what it is worth: about half a tick, against a 79 bps round trip. Study #99
                 found the thing that does pay - waiting for the right moment to fill an order you have already decided
                 on, +6-11 bps per fill. So the number is shown as "which side is queued deeper", next to the spread it
                 has to beat, and never as an arrow telling anyone where the price is going.

``trend_state`` reports the RULE's state, not a prediction: whether this name would be an entry today under the rule the
`trend_live` book actually follows, how far it sits from each of the rule's three tests, and whether the regime gate is
open. Every threshold comes from :mod:`trend_book` itself (HI_N, MA_N, VOL_N, VOL_X, TRAIL) so the screen can never
drift away from the book - if the rule changes, this moves with it.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

import pandas as pd
import psycopg

from . import trend_book as tb

logger = logging.getLogger(__name__)

MAX_DAILY_BARS = 1500
MAX_INTRADAY_MINUTES = 8 * 60


def _f(v: Any) -> float | None:
    return None if v is None else float(v)


def daily(conn: psycopg.Connection, code: str, bars: int = 260) -> list[dict[str, Any]]:
    """Adjusted daily candles, oldest first. Adjusted, because the rule's lines are drawn on adjusted closes and a raw
    series would put the 200-day average in the wrong place for any name that has split."""
    n = max(2, min(int(bars), MAX_DAILY_BARS))
    with conn.cursor() as cur:
        cur.execute(
            """SELECT trade_date, open * adj_factor AS o, high * adj_factor AS h, low * adj_factor AS l,
                      close * adj_factor AS c, close AS raw_close, volume
                 FROM idx.bar WHERE code = %s AND source IN ('idx', 'yahoo') ORDER BY trade_date DESC LIMIT %s""",
            (code.upper(), n))
        rows = [dict(r) if isinstance(r, dict) else dict(zip(
            ["trade_date", "o", "h", "l", "c", "raw_close", "volume"], r, strict=True)) for r in cur.fetchall()]
    rows.reverse()
    return [{"date": r["trade_date"].isoformat(), "open": _f(r["o"]), "high": _f(r["h"]), "low": _f(r["l"]),
             "close": _f(r["c"]), "raw_close": _f(r["raw_close"]), "volume": int(r["volume"] or 0)} for r in rows]


def intraday(conn: psycopg.Connection, code: str, minutes: int = 240, d: date | None = None) -> list[dict[str, Any]]:
    """One-minute candles for the session of ``d`` (default: the latest session that has any), oldest first. Empty for a
    name the collector does not subscribe to - the caller shows the daily panel alone rather than an error."""
    n = max(2, min(int(minutes), MAX_INTRADAY_MINUTES))
    with conn.cursor() as cur:
        cur.execute(
            """SELECT minute, open, high, low, close, volume, n_trades, buy_volume, sell_volume
                 FROM idx.feed_bar_1m
                WHERE code = %s AND (%s::date IS NULL OR (minute AT TIME ZONE 'Asia/Jakarta')::date = %s)
                ORDER BY minute DESC LIMIT %s""",
            (code.upper(), d, d, n))
        rows = [dict(r) if isinstance(r, dict) else dict(zip(
            ["minute", "open", "high", "low", "close", "volume", "n_trades", "buy_volume", "sell_volume"],
            r, strict=True)) for r in cur.fetchall()]
    rows.reverse()
    return [{"at": r["minute"].isoformat(), "open": _f(r["open"]), "high": _f(r["high"]), "low": _f(r["low"]),
             "close": _f(r["close"]), "volume": int(r["volume"] or 0), "trades": int(r["n_trades"] or 0),
             "buy_volume": int(r["buy_volume"] or 0), "sell_volume": int(r["sell_volume"] or 0)} for r in rows]


def depth(conn: psycopg.Connection, code: str) -> dict[str, Any]:
    """The latest ten levels each side, with cumulative volume per side and the queue imbalance.

    ``imbalance`` is bid_total / (bid_total + off_total) over the ten levels: 0.5 is balanced, above it the bid queue is
    the deeper one. It is reported beside ``spread_bps`` on purpose - the measured lead is worth a fraction of a tick and
    the spread is what any trade on it would have to cross, which is the whole reason the desk uses this for timing a
    fill and not for choosing one."""
    with conn.cursor() as cur:
        cur.execute("""SELECT ts, bid_px, bid_vol, bid_n, off_px, off_vol, off_n, bid_total, off_total
                         FROM idx.feed_book WHERE code = %s ORDER BY ts DESC LIMIT 1""", (code.upper(),))
        row = cur.fetchone()
    if row is None:
        return {"code": code.upper(), "at": None, "levels": [], "bid_total": None, "off_total": None,
                "imbalance": None, "spread": None, "spread_bps": None, "why": "this name is not in the tick feed"}
    r = dict(row) if isinstance(row, dict) else dict(zip(
        ["ts", "bid_px", "bid_vol", "bid_n", "off_px", "off_vol", "off_n", "bid_total", "off_total"], row, strict=True))
    bpx, bvol, bn = r["bid_px"] or [], r["bid_vol"] or [], r["bid_n"] or []
    opx, ovol, on = r["off_px"] or [], r["off_vol"] or [], r["off_n"] or []
    levels = []
    for i in range(max(len(bpx), len(opx))):
        levels.append({
            "i": i,
            "bid": _f(bpx[i]) if i < len(bpx) else None,
            "bid_vol": int(bvol[i]) if i < len(bvol) else None,
            "bid_n": int(bn[i]) if i < len(bn) else None,
            "off": _f(opx[i]) if i < len(opx) else None,
            "off_vol": int(ovol[i]) if i < len(ovol) else None,
            "off_n": int(on[i]) if i < len(on) else None,
        })
    bt, ot = _f(r["bid_total"]), _f(r["off_total"])
    imb = (bt / (bt + ot)) if (bt is not None and ot is not None and (bt + ot) > 0) else None
    best_bid = _f(bpx[0]) if bpx else None
    best_off = _f(opx[0]) if opx else None
    spread = (best_off - best_bid) if (best_bid and best_off) else None
    mid = ((best_off + best_bid) / 2) if (best_bid and best_off) else None
    return {"code": code.upper(), "at": r["ts"].isoformat(), "levels": levels,
            "best_bid": best_bid, "best_off": best_off, "mid": mid, "spread": spread,
            "spread_bps": round(spread / mid * 10_000, 1) if (spread is not None and mid) else None,
            "bid_total": bt, "off_total": ot, "imbalance": round(imb, 3) if imb is not None else None}


def trend_state(conn: psycopg.Connection, code: str, d: date | None = None) -> dict[str, Any]:
    """Where the deployed trend rule stands on this name, as a state and never as a forecast.

    Returns each of the rule's three entry tests with the actual numbers behind it, the trailing-stop level measured from
    the peak of the window, and the regime gate. ``entry_today`` is what the rule would say if it ran now on this name
    alone - the book still applies its own sizing, cash and hold-back on top, so this is the rule's reading, not a
    ticket."""
    from . import overlay
    code = code.upper()
    d = d or _latest_bar_date(conn, code)
    if d is None:
        return {"code": code, "as_of": None, "why": "no bars for this name"}
    hist = tb.history(conn, [code], d, bars=tb.MA_N + 5)
    g = hist[hist["code"] == code].sort_values("trade_date")
    if len(g) < tb.MA_N:
        return {"code": code, "as_of": d.isoformat(),
                "why": f"only {len(g)} bars; the rule needs {tb.MA_N}"}
    adj = g["adj"].to_numpy(float)
    vol = g["volume"].to_numpy(float)
    last = float(adj[-1])
    hi60 = float(adj[-tb.HI_N:].max())
    ma200 = float(adj[-tb.MA_N:].mean())
    vmed = float(pd.Series(vol[-tb.VOL_N:]).median())
    vr = (float(vol[-1]) / vmed) if vmed > 0 else None
    peak = float(adj[-tb.HI_N:].max())
    trail = peak * (1 - float(tb.TRAIL))
    try:
        regime = overlay.index_regime(conn, d)
    except ValueError:                                                   # no index history: report it, do not guess
        regime = {"on": None, "close": None, "sma": None, "index_code": None}
    tests = {
        "at_60d_high": {"ok": last >= hi60, "close": last, "hi60": hi60,
                        "pct_below": round((hi60 - last) / hi60 * 100, 2) if hi60 else None},
        "above_200d_avg": {"ok": last > ma200, "close": last, "ma200": ma200,
                           "pct_above": round((last - ma200) / ma200 * 100, 2) if ma200 else None},
        "volume_surge": {"ok": bool(vr is not None and vr >= float(tb.VOL_X)), "vol_ratio": round(vr, 2) if vr else None,
                         "needs": float(tb.VOL_X), "median_volume": vmed},
    }
    return {
        "code": code, "as_of": d.isoformat(), "close": last,
        "rule": {"name": "trend", "high_window": tb.HI_N, "average_window": tb.MA_N,
                 "volume_window": tb.VOL_N, "volume_multiple": float(tb.VOL_X), "trail_pct": float(tb.TRAIL) * 100},
        "tests": tests,
        "entry_today": all(t["ok"] for t in tests.values()),
        "trail": {"peak_60d": peak, "stop": trail,
                  "pct_above_stop": round((last - trail) / trail * 100, 2) if trail else None},
        "regime": {"on": regime.get("on"), "index": regime.get("index_code"),
                   "close": _f(regime.get("close")), "sma": _f(regime.get("sma"))},
        "means": ("the rule's reading of this name today, not a price forecast: the desk has no model that predicts "
                  "where a price goes next"),
    }


def _latest_bar_date(conn: psycopg.Connection, code: str) -> date | None:
    with conn.cursor() as cur:
        cur.execute("SELECT max(trade_date) AS d FROM idx.bar WHERE code = %s AND source = 'idx'", (code,))
        row = cur.fetchone()
    d = (row.get("d") if isinstance(row, dict) else row[0]) if row else None
    return d


def view(conn: psycopg.Connection, code: str, *, bars: int = 260, minutes: int = 240) -> dict[str, Any]:
    """Everything one screen needs in a single call: name, daily candles, intraday candles, the book, the rule's state."""
    code = code.upper()
    with conn.cursor() as cur:
        cur.execute("SELECT name FROM idx.listing WHERE code = %s", (code,))
        row = cur.fetchone()
    name = (row.get("name") if isinstance(row, dict) else row[0]) if row else None
    dl = daily(conn, code, bars)
    intra = intraday(conn, code, minutes)
    return {
        "code": code, "name": name,
        "daily": dl,
        "intraday": intra,
        "intraday_from": ("the tick feed, which covers the subscribed names only and starts when the collector first ran"
                          if intra else "this name is not in the tick feed"),
        "depth": depth(conn, code),
        "trend": trend_state(conn, code),
        "generated_at": datetime.now().astimezone().isoformat(),
    }


INDEX_CODE = "COMPOSITE"                 # what idx.index_daily calls it
INDEX_FEED_CODE = "IHSG"                 # what the tick feed calls the same thing


def index_daily(conn: psycopg.Connection, bars: int = 260, index_code: str = INDEX_CODE) -> list[dict[str, Any]]:
    """Daily candles for an index, oldest first. No adjustment: an index has no splits."""
    n = max(2, min(int(bars), MAX_DAILY_BARS))
    with conn.cursor() as cur:
        cur.execute("""SELECT trade_date, open, high, low, close, volume FROM idx.index_daily
                        WHERE index_code = %s ORDER BY trade_date DESC LIMIT %s""", (index_code, n))
        rows = [dict(r) if isinstance(r, dict) else dict(zip(
            ["trade_date", "open", "high", "low", "close", "volume"], r, strict=True)) for r in cur.fetchall()]
    rows.reverse()
    # IDX publishes previous/high/low/close for an index and no open. `open` is Yahoo's ^JKSE open bounded by IDX's own
    # high and low (jobs/index_open.py, `open_src` = 'yahoo'); where that job has not filled a day it stays null rather
    # than being filled with the close - a bar drawn from a made-up open is a claim about the day that nobody made.
    return [{"date": r["trade_date"].isoformat(), "open": _f(r["open"]), "high": _f(r["high"]),
             "low": _f(r["low"]), "close": _f(r["close"]), "volume": int(r["volume"] or 0)}
            for r in rows if r["close"] is not None]


def index_view(conn: psycopg.Connection, *, bars: int = 260, minutes: int = 240) -> dict[str, Any]:
    """The market itself: COMPOSITE candles, its 200-day average, and the REGIME GATE that average drives.

    The average is not decoration here. `regime_filter` on a trend book means exactly this line: while the COMPOSITE
    closes under its 200-day average the book takes no new entry (menus 22-25, studies #62-#66 - validated as a
    drawdown rule, mDD -30 % to -18 %, not as a return rule). So the index chart and the gate are one picture.

    The tick feed carries the index as `IHSG`, so an intraday panel exists for it too."""
    from . import overlay
    daily_rows = index_daily(conn, bars)
    d = date.fromisoformat(daily_rows[-1]["date"]) if daily_rows else None
    try:
        regime = overlay.index_regime(conn, d) if d else {}
    except ValueError:
        regime = {}
    return {
        "code": INDEX_CODE, "name": "IHSG",
        "daily": daily_rows,
        "intraday": intraday(conn, INDEX_FEED_CODE, minutes),
        "as_of": daily_rows[-1]["date"] if daily_rows else None,
        "close": daily_rows[-1]["close"] if daily_rows else None,
        "sma": _f(regime.get("sma")),
        "sma_days": overlay.SMA_DAYS,
        "regime_on": regime.get("on"),
        "means": ("the 200-day average is the regime gate: while the index closes under it a trend book with "
                  "regime_filter on takes no new entry"),
        "generated_at": datetime.now().astimezone().isoformat(),
    }


def feed_codes(conn: psycopg.Connection) -> list[str]:
    """The names that have an intraday panel at all - the collector's subscription list."""
    with conn.cursor() as cur:
        cur.execute("SELECT code FROM idx.feed_symbol WHERE enabled ORDER BY code")
        return [(r.get("code") if isinstance(r, dict) else r[0]) for r in cur.fetchall()]


__all__ = ["daily", "depth", "feed_codes", "index_daily", "index_view", "intraday", "trend_state", "view"]
