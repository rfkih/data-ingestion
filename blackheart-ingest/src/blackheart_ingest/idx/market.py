"""The market in one read: breadth, foreign flow, sectors, movers, and the world around it.

Everything here comes from `idx.daily_summary` (the official day summary) and `idx.macro`. Nothing is
modelled and nothing is estimated except where it says so in the payload itself:

* ``breadth``  - advancers, decliners and unchanged, counted against each name's own `previous`. Exact.
* ``foreign``  - IDX publishes `foreign_buy` / `foreign_sell` in SHARES, not rupiah. The rupiah figure
                 every screen wants is therefore sum of (buy - sell) x close, an approximation, and the
                 payload carries `value_is_estimated: true` so the screen can say so. The share figure
                 beside it is the exact one.
* ``sectors``  - only about half of the listings carry a sector (473 of 989 are null on 2026-09-24), so
                 the payload reports `covered` and `listed` and the screen says what it is missing
                 rather than implying the whole market.
* ``movers``   - biggest movers among names that actually trade: the liquidity floor keeps a name that
                 printed once from topping the list at +25 %.
* ``world``    - the macro series the desk already watches, with their own last change.
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any

import psycopg

logger = logging.getLogger(__name__)

MOVERS_N = 6
MOVERS_MIN_VALUE = Decimal("1e9")          # Rp 1 bn traded that day - below this a "mover" is one print
FOREIGN_SESSIONS = 10
WORLD_SERIES = ("usdidr", "gold", "brent", "vix", "us10y", "cpo")


def _f(v: Any) -> float | None:
    return None if v is None else float(v)


def _rows(conn: psycopg.Connection, sql: str, params: tuple, cols: list[str]) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        out = []
        for r in cur.fetchall():
            out.append(dict(r) if isinstance(r, dict) else dict(zip(cols, r, strict=True)))
        return out


def latest_day(conn: psycopg.Connection, index_code: str = "COMPOSITE") -> date | None:
    """The last day this read can be built from in full: one that has BOTH a day summary and an index
    close. They do not land together - a `daily` run during the session writes a summary for a day whose
    index has not been published yet (2026-09-24: 963 summary rows, no index row), and anchoring on the
    summary alone put a half-built day on the screen with a blank index above it. Same rule as
    `candidates.build`: show the last day that is actually finished."""
    with conn.cursor() as cur:
        cur.execute("""SELECT max(s.trade_date) AS d FROM idx.daily_summary s
                        WHERE EXISTS (SELECT 1 FROM idx.index_daily i
                                       WHERE i.trade_date = s.trade_date AND i.index_code = %s)""",
                    (index_code,))
        row = cur.fetchone()
    return (row.get("d") if isinstance(row, dict) else row[0]) if row else None


def breadth(conn: psycopg.Connection, d: date) -> dict[str, Any]:
    """Advancers, decliners, unchanged - counted against each name's own previous close, not a market
    average, which is what makes it breadth rather than a second way of saying the index moved."""
    rows = _rows(conn, """
        SELECT count(*) FILTER (WHERE close > previous) AS up,
               count(*) FILTER (WHERE close < previous) AS down,
               count(*) FILTER (WHERE close = previous) AS flat,
               count(*) FILTER (WHERE close IS NULL OR previous IS NULL) AS unknown,
               count(*) AS listed
          FROM idx.daily_summary WHERE trade_date = %s""", (d,), ["up", "down", "flat", "unknown", "listed"])
    r = rows[0] if rows else {}
    return {k: int(r.get(k) or 0) for k in ("up", "down", "flat", "unknown", "listed")}


def foreign(conn: psycopg.Connection, d: date, sessions: int = FOREIGN_SESSIONS) -> dict[str, Any]:
    """Foreign net over the last ``sessions`` days. Shares are exact; the rupiah figure is sum of (buy - sell) x close
    and is flagged as an estimate - IDX publishes the two legs in shares only."""
    rows = _rows(conn, """
        SELECT trade_date,
               sum(foreign_buy) - sum(foreign_sell) AS net_shares,
               sum((foreign_buy - foreign_sell) * close) AS net_value
          FROM idx.daily_summary
         WHERE trade_date <= %s AND foreign_buy IS NOT NULL AND foreign_sell IS NOT NULL
         GROUP BY trade_date ORDER BY trade_date DESC LIMIT %s""",
        (d, max(1, int(sessions))), ["trade_date", "net_shares", "net_value"])
    rows.reverse()
    series = [{"date": r["trade_date"].isoformat(), "net_shares": _f(r["net_shares"]),
               "net_value": _f(r["net_value"])} for r in rows]
    today = series[-1] if series else {"net_shares": None, "net_value": None}
    return {
        "today": today,
        "series": series,
        "window_value": sum(x["net_value"] or 0 for x in series) if series else None,
        "value_is_estimated": True,
        "why": "IDX publishes foreign buy and sell in shares; the rupiah figure is those shares at the day's close",
    }


IDX_IC = r"^[A-Z]\. "                      # "K. Transportation & Logistic" - the current taxonomy, 11 sectors


def sectors(conn: psycopg.Connection, d: date) -> dict[str, Any]:
    """Each sector's move, weighted by the day's traded value so a thin name cannot swing it.

    Only the IDX-IC taxonomy ("K. Transportation & Logistic", 11 sectors) is reported. `idx.listing` also
    holds 48 names still on the old JASICA scheme ("4. Miscellaneous Industry") and 447 with no sector at
    all; putting all three in one list produced a table with two spellings of the market and no total that
    meant anything. The stragglers are counted in `unclassified`, so the screen can say what it is missing
    instead of implying the whole market is here."""
    rows = _rows(conn, """
        SELECT l.sector,
               count(*) AS n,
               sum(s.value) AS value,
               sum((s.close - s.previous) / NULLIF(s.previous, 0) * s.value) / NULLIF(sum(s.value), 0) * 100 AS chg_pct
          FROM idx.daily_summary s JOIN idx.listing l USING (code)
         WHERE s.trade_date = %s AND l.sector ~ %s AND s.previous > 0 AND s.value > 0
         GROUP BY l.sector ORDER BY chg_pct DESC NULLS LAST""", (d, IDX_IC), ["sector", "n", "value", "chg_pct"])
    cov = _rows(conn, """
        SELECT count(*) FILTER (WHERE l.sector ~ %s) AS covered,
               count(*) FILTER (WHERE l.sector IS NOT NULL AND l.sector !~ %s) AS other_scheme,
               count(*) FILTER (WHERE l.sector IS NULL) AS no_sector,
               count(*) AS listed
          FROM idx.daily_summary s LEFT JOIN idx.listing l USING (code) WHERE s.trade_date = %s""",
        (IDX_IC, IDX_IC, d), ["covered", "other_scheme", "no_sector", "listed"])
    c = cov[0] if cov else {}
    return {
        # the leading letter is the taxonomy's own ordering key, not part of the name a reader wants
        "rows": [{"sector": r["sector"].split(". ", 1)[-1], "key": r["sector"][:1], "n": int(r["n"]),
                  "value": _f(r["value"]), "chg_pct": _f(r["chg_pct"])} for r in rows],
        "covered": int(c.get("covered") or 0),
        "listed": int(c.get("listed") or 0),
        "unclassified": int(c.get("other_scheme") or 0) + int(c.get("no_sector") or 0),
    }


def movers(conn: psycopg.Connection, d: date, n: int = MOVERS_N) -> dict[str, Any]:
    """The day's biggest moves among names that actually traded. Without the value floor the list is
    whatever printed once at its upper limit, which tells a reader nothing about the market."""
    sql = """
        SELECT s.code, COALESCE(l.name, s.name) AS name, s.close, s.previous, s.value,
               (s.close - s.previous) / NULLIF(s.previous, 0) * 100 AS chg_pct
          FROM idx.daily_summary s LEFT JOIN idx.listing l USING (code)
         WHERE s.trade_date = %s AND s.previous > 0 AND s.value >= %s
         ORDER BY chg_pct {dir} NULLS LAST LIMIT %s"""
    cols = ["code", "name", "close", "previous", "value", "chg_pct"]
    out = {}
    for key, direction in (("gainers", "DESC"), ("losers", "ASC")):
        rows = _rows(conn, sql.format(dir=direction), (d, MOVERS_MIN_VALUE, max(1, int(n))), cols)
        out[key] = [{"code": r["code"], "name": r["name"], "close": _f(r["close"]),
                     "chg_pct": _f(r["chg_pct"]), "value": _f(r["value"])} for r in rows]
    out["min_value"] = float(MOVERS_MIN_VALUE)
    return out


def world(conn: psycopg.Connection, series: tuple[str, ...] = WORLD_SERIES) -> list[dict[str, Any]]:
    """The macro series next to the market, each with its own last move. `idx.macro` holds these at
    whatever cadence the source publishes, so the change is against that series' previous observation,
    never against a calendar day it may not have."""
    rows = _rows(conn, """
        SELECT series, obs_date, value, prev FROM (
            SELECT series, obs_date, value,
                   lag(value) OVER (PARTITION BY series ORDER BY obs_date) AS prev,
                   row_number() OVER (PARTITION BY series ORDER BY obs_date DESC) AS rn
              FROM idx.macro WHERE series = ANY(%s)) t
         WHERE rn = 1 ORDER BY series""", (list(series),), ["series", "obs_date", "value", "prev"])
    by = {r["series"]: r for r in rows}
    out = []
    for s in series:                                                     # keep the caller's order
        r = by.get(s)
        if not r:
            continue
        v, p = _f(r["value"]), _f(r["prev"])
        out.append({"series": s, "at": r["obs_date"].isoformat(), "value": v,
                    "chg_pct": ((v - p) / p * 100) if (v is not None and p) else None})
    return out


def day_facts(conn: psycopg.Connection, d: date, index_code: str = "COMPOSITE") -> dict[str, Any]:
    """The six figures the design prints under the index chart.

    The design's first fact is the index's OPEN. There is no such number: IDX publishes previous, high,
    low and close for an index and no open (null on all 1,618 COMPOSITE rows). So the first fact is the
    previous close, which the exchange does publish, under its own label - the figure is real or it is
    not shown. Shares, value and trades are the market's own totals from the day summary, which is also
    what breadth is counted from, so the numbers on this screen all come from one table."""
    ix = _rows(conn, """SELECT previous, high, low, close FROM idx.index_daily
                         WHERE index_code = %s AND trade_date = %s""", (index_code, d),
               ["previous", "high", "low", "close"])
    tot = _rows(conn, """SELECT sum(volume) AS shares, sum(value) AS value, sum(frequency) AS trades
                           FROM idx.daily_summary WHERE trade_date = %s""", (d,), ["shares", "value", "trades"])
    i = ix[0] if ix else {}
    t = tot[0] if tot else {}
    return {
        "previous": _f(i.get("previous")), "high": _f(i.get("high")), "low": _f(i.get("low")),
        "close": _f(i.get("close")),
        "shares": _f(t.get("shares")), "value": _f(t.get("value")), "trades": _f(t.get("trades")),
        "no_open": True,
        "why_no_open": "IDX publishes previous, high, low and close for an index - never an open",
    }


def overview(conn: psycopg.Connection, d: date | None = None) -> dict[str, Any]:
    """One call for the top of the desk: the index, breadth, foreign flow, sectors, movers, the world."""
    from . import chart
    d = d or latest_day(conn)
    if d is None:
        return {"as_of": None, "why": "no day summary in this database"}
    return {
        "as_of": d.isoformat(),
        "index": chart.index_view(conn, bars=130, minutes=240),
        "facts": day_facts(conn, d),
        "breadth": breadth(conn, d),
        "foreign": foreign(conn, d),
        "sectors": sectors(conn, d),
        "movers": movers(conn, d),
        "world": world(conn),
    }


__all__ = ["breadth", "day_facts", "foreign", "latest_day", "movers", "overview", "sectors", "world"]
