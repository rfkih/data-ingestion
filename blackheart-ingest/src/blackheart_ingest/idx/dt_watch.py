"""Forward paper watch of research rule C1 (menu DT-3, study #398, research/IDX_DAYTRADE3_2026-09-27.md).

C1 = at the end of the session, among the tick collector's names that are eligible (20-session average value >= Rp 5 bn,
previous close >= Rp 100), take those whose last print before 15:50 is above the previous close AND whose last print before
10:00 was also above it, skip any within one tick of the upper auto-rejection band, and rank by the day's return; the top
five would be BOUGHT IN THE CLOSING AUCTION and SOLD IN THE NEXT OPENING AUCTION. Five random eligible names (seeded by the
date) are logged the same way as the placebo. Nothing here places an order or pushes a phone - it is a measurement.

Why forward: in the backtest (713 sessions 2023-09..2026-09) C1 earned +51 bps gross, +0 net at 0.15/0.25 % fees, +10 bps at
0.10/0.20 %, and the exchange changes the auto-rejection rules on 2026-09-28. Only data after that date can say whether it
survives, and whether a cheaper broker would make it worth trading.

JUDGEMENT RULE (declared 2026-09-27 before the first row; REVISED the same evening, still before any row existed - do not
change it after seeing data). The first rule (t of net_low >= 2 after 60 sessions) had a 6 % chance of passing a REAL edge of
the backtest's size: C1's daily return sd is ~173 bps against a ~10 bps net edge (research-scratch/idx/daytrade2/c1_power.py).
The revision tests the part that can be measured in months - the SELECTION edge, net of the day's common overnight move:
  d_t = mean gross of the day's picks - the eligible universe's equal-weight gross (row kind 'universe', same auctions).
  Backtest 2023-09..2026-09: d = +26.5 bps/session, sd 126 (t 5.4) over 661 sessions; on the 398 sessions from 2025 (the
  regime with IDX's own opening prints, the one the watch lives in) +27.5 bps, sd 153 - THESE are the parameters (review
  2026-09-27, still before the first row). Wald SPRT on d_t, H0: mean 0 vs H1: mean +27.5 bps, sd fixed at 153 bps,
  alpha 0.05, beta 0.20 -> stop when the log-likelihood ratio crosses +2.773 (accept H1) or -1.558 (accept H0); bootstrap
  of the 2025+ sessions: a true edge is accepted 80 % of the time (median 101 sessions, p10 37, p90 218), a zero edge is
  rejected 97 % (median 84), falsely accepted 2 %. Only the first 500 sessions count; unresolved by then = "undecided".
  The universe is the eligible list FROZEN at pick time (stored on the universe row), never re-derived at settle.
  CANDIDATE only if the SPRT accepts H1 AND the live mean net_low of the picks (fees 0.10 / 0.20 %, 5 bps impact) is > 0.
Even then the next step is a real-money pilot only on the operator's decision - never automatic. The samples predate the
auto-rejection change of 2026-09-28; if the new bands shift the distribution, H1 was set on the old regime and the test says so.

Data: picks from ``idx.feed_bar_1m`` (the bars before 15:50 are final when the job runs at 16:20); names the feed does not
carry (about a third of the liquid set) or a day without feed bars (a dead session token) read the same prints from Yahoo's
hourly .JK series (the backtest's source), which matched the feed on 100 %
of overlapping bars (research-scratch/idx/daytrade2/validate.py). Prices to settle come from ``idx.daily_summary``.
"""
from __future__ import annotations

import json
import logging
import random
import urllib.request
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import psycopg
from psycopg.rows import tuple_row

from . import exchange_calendar as cal

logger = logging.getLogger(__name__)
WIB = ZoneInfo("Asia/Jakarta")
K, MIN_V20, MIN_PREV = 5, 5e9, 100
FEES = {"retail": (0.0015, 0.0025), "low": (0.0010, 0.0020)}
IMPACT = 0.0005
VOID_AFTER = 5                        # trading days without a next opening print -> the row is closed unsettled
SPRT_MU, SPRT_SD, SPRT_CAP = 0.00275, 0.0153, 500
SPRT_A, SPRT_B = float(np.log(0.8 / 0.05)), float(np.log(0.2 / 0.95))


def tick(p: float) -> float:
    return 1 if p < 200 else 2 if p < 500 else 5 if p < 2000 else 10 if p < 5000 else 25


def ara(p: float) -> float:
    """Upper auto-rejection band from 2026-09-28 (Kep-00136/BEI/09-2026): 35 % / 25 % / 20 % by previous price."""
    return 0.35 if p <= 200 else 0.25 if p <= 5000 else 0.20


def net(buy: float, sell: float, fees: tuple[float, float]) -> float:
    fb, fs = fees
    return sell * (1 - IMPACT) * (1 - fs) / (buy * (1 + IMPACT) * (1 + fb)) - 1


def _rows(conn: psycopg.Connection, sql: str, params: tuple = ()) -> list[tuple]:
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def eligible(conn: psycopg.Connection, d: date) -> dict[str, float]:
    """{code: previous official close} for the collector's names eligible on d (information up to d-1 only)."""
    prev = cal.prev_trading_day(d, conn)
    rows = _rows(conn, """
        WITH s AS (SELECT code, trade_date, close, value,
                          row_number() OVER (PARTITION BY code ORDER BY trade_date DESC) AS rn
                     FROM idx.daily_summary WHERE trade_date <= %s AND trade_date > %s - 45)
        SELECT s.code, max(s.close) FILTER (WHERE s.trade_date = %s), avg(s.value) FILTER (WHERE s.rn <= 20), count(*) FILTER (WHERE s.rn <= 20)
          FROM s JOIN idx.feed_symbol f ON f.code = s.code AND f.enabled
         GROUP BY s.code""", (prev, prev, prev))
    return {c: float(pc) for c, pc, v20, n in rows if pc and v20 and n >= 15 and float(v20) >= MIN_V20 and float(pc) >= MIN_PREV}


def prints_feed(conn: psycopg.Connection, d: date, codes: list[str]) -> dict[str, tuple[float, float]]:
    """{code: (last print before 10:00, last print before 15:50)} from the tick feed's minute bars."""
    lo, t10, t1550 = (datetime.combine(d, t, WIB) for t in (time(9, 0), time(10, 0), time(15, 50)))
    rows = _rows(conn, """
        SELECT code,
               (array_agg(close ORDER BY minute DESC) FILTER (WHERE minute < %s))[1],
               (array_agg(close ORDER BY minute DESC) FILTER (WHERE minute < %s))[1]
          FROM idx.feed_bar_1m WHERE minute >= %s AND minute < %s AND code = ANY(%s) AND close > 0
         GROUP BY code""", (t10, t1550, lo, t1550, codes))
    return {c: (float(a), float(b)) for c, a, b in rows if a and b}


def prints_yahoo(d: date, codes: list[str], fetch=None) -> dict[str, tuple[float, float]]:
    """The same two prints from Yahoo's hourly bars: the 09:00 bar's close and the 15:00 bar's close."""
    def _get(code: str) -> dict:
        u = f"https://query1.finance.yahoo.com/v8/finance/chart/{code}.JK?interval=60m&range=5d"
        req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
        return json.load(urllib.request.urlopen(req, timeout=20))
    fetch = fetch or _get
    out = {}
    for code in codes:
        try:
            res = fetch(code)["chart"]["result"][0]
            q = res["indicators"]["quote"][0]
            got = {}
            for ts, c in zip(res["timestamp"], q["close"], strict=False):
                t = datetime.fromtimestamp(ts, WIB)
                if t.date() == d and c is not None and (t.hour, t.minute) in ((9, 0), (15, 0)):
                    got[t.hour] = float(c)
            if 9 in got and 15 in got:
                out[code] = (got[9], got[15])
        except Exception as e:                                           # one name's failure never stops the rest
            logger.debug("dt_watch yahoo %s: %s", code, e)
    return out


def choose(elig: dict[str, float], prints: dict[str, tuple[float, float]], d: date) -> tuple[list[dict], list[dict]]:
    """Pure: (picks, placebo) rows from the eligible set and the two prints per name."""
    cands = []
    for code, pc in elig.items():
        if code not in prints:
            continue
        p10, p1549 = prints[code]
        r_day, r_first = p1549 / pc - 1, p10 / pc - 1
        if r_day <= 0 or r_first <= 0 or p1549 >= pc * (1 + ara(pc)) - tick(p1549):
            continue
        cands.append(dict(code=code, r_day=r_day, r_first=r_first, px_1549=p1549, prev_close=pc))
    cands.sort(key=lambda r: -r["r_day"])
    picks = [dict(r, kind="pick", rank=i + 1) for i, r in enumerate(cands[:K])]
    pool = sorted(c for c in elig if c in prints)
    rnd = random.Random(int(d.strftime("%Y%m%d")))
    placebo = []
    for code in rnd.sample(pool, min(K, len(pool))):
        p10, p1549 = prints[code]
        pc = elig[code]
        placebo.append(dict(code=code, kind="placebo", rank=None, r_day=p1549 / pc - 1, r_first=p10 / pc - 1, px_1549=p1549, prev_close=pc))
    return picks, placebo


def pick(conn: psycopg.Connection, d: date, *, fetch=None) -> dict[str, Any]:
    if not cal.is_trading_day(d, conn):
        return {"date": str(d), "skipped": "not a trading day"}
    elig = eligible(conn, d)
    prints = prints_feed(conn, d, sorted(elig))
    n_feed = len(prints)
    missing = sorted(c for c in elig if c not in prints)            # the feed carries ~2/3 of the liquid names
    prints.update(prints_yahoo(d, missing, fetch) if missing else {})
    src = f"feed {n_feed} + yahoo {len(prints) - n_feed}"
    picks, placebo = choose(elig, prints, d)
    universe = [dict(code="*", kind="universe", rank=len(elig), r_day=None, r_first=None, px_1549=None, prev_close=None)]
    with conn.cursor() as cur:
        # a re-run for the same day REPLACES that day's unsettled rows (never two top-5s for one session)
        cur.execute("DELETE FROM idx.dt_watch WHERE run_date = %s AND settled_at IS NULL", (d,))
        for r in picks + placebo + universe:
            cur.execute("""INSERT INTO idx.dt_watch (run_date, kind, code, rank, r_day, r_first, px_1549, prev_close, universe)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (run_date, kind, code) DO NOTHING""",
                        (d, r["kind"], r["code"], r["rank"], r["r_day"], r["r_first"], r["px_1549"], r["prev_close"],
                         sorted(elig) if r["kind"] == "universe" else None))
    conn.commit()
    return {"date": str(d), "source": src, "eligible": len(elig), "priced": len(prints),
            "picks": [p["code"] for p in picks], "placebo": [p["code"] for p in placebo]}


def universe_gross(conn: psycopg.Connection, d: date, nd: date, codes: list[str] | None = None) -> float | None:
    """Equal-weight closing-auction (d) -> opening-auction (nd) gross return of the names eligible on d - the list stored at pick
    time (``codes``); None until nd's opening prints are in (needs half the names priced)."""
    elig = codes if codes is not None else sorted(eligible(conn, d))
    rows = _rows(conn, """SELECT a.code, a.close, b.open FROM idx.daily_summary a JOIN idx.daily_summary b
                            ON b.code = a.code AND b.trade_date = %s
                           WHERE a.trade_date = %s AND a.code = ANY(%s) AND a.close > 0 AND b.open > 0""", (nd, d, sorted(elig)))
    if not elig or len(rows) < 0.5 * len(elig):
        return None
    return float(np.mean([float(o) / float(c) - 1 for _, c, o in rows]))


def sprt(diffs: list[float], mu: float = SPRT_MU, sd: float = SPRT_SD, a: float = SPRT_A, b: float = SPRT_B,
         cap: int = SPRT_CAP) -> dict[str, Any]:
    """Pure: Wald's sequential test on the session differences (pick - universe), in order; stops at the first crossing."""
    llr = 0.0
    for i, x in enumerate(diffs[:cap], 1):
        llr += mu / sd ** 2 * (x - mu / 2)
        if llr >= a:
            return {"decision": "H1 accepted (selection edge as in the backtest)", "sessions": i, "llr": llr}
        if llr <= b:
            return {"decision": "H0 accepted (no selection edge)", "sessions": i, "llr": llr}
    return {"decision": "undecided" if len(diffs) >= cap else "running", "sessions": min(len(diffs), cap), "llr": llr, "bounds": [b, a]}


def settle(conn: psycopg.Connection, today: date) -> dict[str, Any]:
    """Fill every open row whose next session's opening print is known; close rows that never get one."""
    done = void = 0
    for run_date, kind, code, frozen in _rows(conn, "SELECT run_date, kind, code, universe FROM idx.dt_watch WHERE settled_at IS NULL AND run_date < %s",
                                              (today,)):
        nd = cal.next_trading_day(run_date, conn)
        if kind == "universe":
            g = universe_gross(conn, run_date, nd, list(frozen) if frozen else None)
            if g is not None:
                conn.execute("""UPDATE idx.dt_watch SET next_date = %s, gross = %s, settled_at = now()
                                WHERE run_date = %s AND kind = 'universe'""", (nd, g, run_date))
                done += 1
            elif cal.add_trading_days(run_date, VOID_AFTER, conn) <= today:
                conn.execute("UPDATE idx.dt_watch SET next_date = %s, settled_at = now() WHERE run_date = %s AND kind = 'universe'",
                             (nd, run_date))
                void += 1
            continue
        px = dict(((c_d), (cl, op)) for c_d, cl, op in _rows(conn, """SELECT trade_date, close, open FROM idx.daily_summary
                                                                     WHERE code = %s AND trade_date IN (%s, %s)""", (code, run_date, nd)))
        buy = px.get(run_date, (None, None))[0]
        sell = px.get(nd, (None, None))[1]
        if buy and sell and float(buy) > 0 and float(sell) > 0:
            b, s = float(buy), float(sell)
            conn.execute("""UPDATE idx.dt_watch SET buy_close = %s, next_date = %s, sell_open = %s, gross = %s, net_retail = %s,
                            net_low = %s, settled_at = now() WHERE run_date = %s AND kind = %s AND code = %s""",
                         (b, nd, s, s / b - 1, net(b, s, FEES["retail"]), net(b, s, FEES["low"]), run_date, kind, code))
            done += 1
        elif cal.add_trading_days(run_date, VOID_AFTER, conn) <= today:
            conn.execute("UPDATE idx.dt_watch SET next_date = %s, settled_at = now() WHERE run_date = %s AND kind = %s AND code = %s",
                         (nd, run_date, kind, code))
            void += 1
    conn.commit()
    return {"settled": done, "void": void}


def report(conn: psycopg.Connection) -> dict[str, Any]:
    rows = _rows(conn, """SELECT run_date, kind, gross, net_retail, net_low FROM idx.dt_watch
                          WHERE settled_at IS NOT NULL AND gross IS NOT NULL AND kind <> 'universe' ORDER BY run_date""")
    out: dict[str, Any] = {"rule": "SPRT on pick - universe (module docstring)"}
    for kind in ("pick", "placebo"):
        r = [x for x in rows if x[1] == kind]
        if not r:
            out[kind] = {"n": 0}
            continue
        days = sorted({x[0] for x in r})
        daily = np.array([np.mean([x[4] for x in r if x[0] == d]) for d in days])
        half = len(days) // 2
        out[kind] = {"n": len(r), "sessions": len(days), "first": str(days[0]), "last": str(days[-1]),
                     "gross_bps": float(np.mean([x[2] for x in r]) * 1e4), "net_retail_bps": float(np.mean([x[3] for x in r]) * 1e4),
                     "net_low_bps": float(np.mean([x[4] for x in r]) * 1e4),
                     "t_net_low": float(daily.mean() / daily.std(ddof=1) * np.sqrt(len(daily))) if len(daily) > 2 and daily.std(ddof=1) > 0 else None,
                     "halves_net_low_bps": [float(daily[:half].mean() * 1e4) if half else None, float(daily[half:].mean() * 1e4)]}
    uni = {x[0]: x[2] for x in _rows(conn, """SELECT run_date, kind, gross FROM idx.dt_watch
                                               WHERE kind = 'universe' AND gross IS NOT NULL ORDER BY run_date""")}
    by_day: dict = {}
    for d, kind, g, _nr, _nl in rows:
        if kind == "pick":
            by_day.setdefault(d, []).append(g)
    diffs = [float(np.mean(v)) - uni[d] for d, v in sorted(by_day.items()) if d in uni]
    test = sprt(diffs)
    out["universe_gross_bps"] = float(np.mean(list(uni.values())) * 1e4) if uni else None
    out["selection_diff_bps"] = float(np.mean(diffs) * 1e4) if diffs else None
    out["sprt"] = test
    p = out["pick"]
    if test["decision"].startswith("H1"):
        out["verdict"] = ("CANDIDATE (operator decides on a pilot)" if p.get("n") and p["net_low_bps"] > 0
                          else "selection edge confirmed, but not profitable at 0.10/0.20 % fees")
    elif test["decision"].startswith("H0"):
        out["verdict"] = "no - selection edge not confirmed"
    else:
        out["verdict"] = test["decision"]
    return out


__all__ = ["choose", "eligible", "net", "pick", "prints_feed", "prints_yahoo", "report", "settle", "sprt", "universe_gross"]
