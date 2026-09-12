"""Candidate list — the systematic half of the value/quality book, point-in-time as of a date.

Rule (research/IDX_VALUE_QUALITY_2026-09-12.md, "composite_qloose"): names on the Utama/Pengembangan boards *on that
day* (board read from the IDX notation string in the day-dump, so a name later moved to Pemantauan Khusus or delisted
is judged as it was) that traded that day, 60-day median traded value >= Rp 5 bn -> loose gate (latest audited profit > 0
and ROE >= 5 %) -> composite average-rank of earnings yield, book yield and trailing dividend yield -> top fifth, at
least MIN_NAMES, provided the pool has at least MIN_POOL names (else nothing: a padded selection from a tiny pool is the
gate, not the rank). Every candidate also carries the strict-gate flags, TTM figures and thesis-break warnings so the
operator can apply judgment per name. Rows are stored in ``idx.candidate`` per run date for the app and the pack.

``rank_pool`` is the one implementation of the rule; the research backtest calls it too (research/idx_value_quality.py),
so the live list and the tested list cannot drift.
"""
from __future__ import annotations

import json
import logging
import math
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import psycopg

from . import runlog
from .metrics import LIQ, fundamentals_asof

logger = logging.getLogger(__name__)
JOB = "candidates"
TOP_FRACTION, MIN_NAMES, MIN_POOL = 5, 10, 20
CONV_CAP = Decimal(3)                                                 # CFO / profit above 3 is noise, not virtue
KEYS = ("ep", "bp", "dy")
MAX_RATIO = Decimal(50)                 # E/P, B/P, DY or TTM E/P above 5000 % is a data error
BOARD_DIGIT = {"1": "Utama", "2": "Pengembangan", "3": "Akselerasi", "4": "Pemantauan Khusus", "5": "Ekonomi Baru"}
ELIGIBLE_BOARDS = ("Utama", "Pengembangan")


def _rows(conn, sql, params, cols):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    return [dict(zip(cols, (list(r.values()) if isinstance(r, dict) else r), strict=True)) for r in rows]


def board_from_remarks(remarks: str | None) -> str | None:
    """Board on the day, from the IDX notation string carried by every day-dump row (``Remarks``): the fifth character is
    the board digit (1 Utama, 2 Pengembangan, 3 Akselerasi, 4 Pemantauan Khusus, 5 Ekonomi Baru); a trailing ``X`` is the
    special-monitoring notation. Verified against ``idx.listing.board`` on 2026-09-11 (269/488/42/158/1 rows agree)."""
    if not remarks or len(remarks) < 5:
        return None
    return BOARD_DIGIT.get(remarks[4])


def build(conn: psycopg.Connection, as_of: date | None = None) -> dict[str, Any]:
    last = _rows(conn, "SELECT max(trade_date) FROM idx.bar WHERE source='idx' AND (%s::date IS NULL OR trade_date <= %s)",
                 (as_of, as_of), ["d"])[0]["d"]
    D: date = last
    # raw close x listed shares of the day = market cap on the day's own basis (the adjusted close is on today's split basis,
    # the day's share count on its own: mixing them made a name that later split look up to 10x cheaper in past runs)
    px = _rows(conn, """
        SELECT b.code, COALESCE(l.name, s.name), s.remarks, l.board, l.status, b.close, b.close * b.adj_factor AS adj_close, b.volume,
               s.listed_shares, f.value_60d_median, f.foreign_net_share_20d, f.foreign_net_share_5d, l.sector
          FROM idx.bar b JOIN idx.daily_summary s USING (trade_date, code) LEFT JOIN idx.listing l USING (code)
          LEFT JOIN idx.feature_daily f USING (trade_date, code)
         WHERE b.trade_date = %s AND b.source = 'idx'
        """, (D,), ["code", "name", "remarks", "board_now", "status_now", "close", "adj_close", "volume", "shares", "v60", "f20", "f5", "sector"])
    for p in px:
        p["board"] = board_from_remarks(p["remarks"]) or p["board_now"]
    liquid = [p for p in px if p["board"] in ELIGIBLE_BOARDS and p["v60"] is not None and Decimal(p["v60"]) >= LIQ
              and p["shares"] and Decimal(p["shares"]) > 0 and p["close"]]
    codes = [p["code"] for p in liquid]
    mom = momentum_at(conn, D, codes)
    fund = fundamentals_asof(conn, D, codes)
    divs = _rows(conn, "SELECT code, sum(amount_per_share) AS dps FROM idx.dividend WHERE ex_date > %s AND ex_date <= %s AND code = ANY(%s) GROUP BY code",
                 (D - timedelta(days=365), D, codes), ["code", "dps"])
    dps = {d["code"]: Decimal(d["dps"]) for d in divs}
    rows = []
    for p in liquid:
        m = fund.get(p["code"])
        price, adj_close, shares = Decimal(p["close"]), Decimal(p["adj_close"]), Decimal(p["shares"])
        mcap = price * shares                                        # both on the day's basis
        r: dict[str, Any] = {"code": p["code"], "name": p["name"], "board": p["board"], "price": price, "mcap": mcap,
                             "v60": Decimal(p["v60"]), "tradable": bool(p["volume"] and int(p["volume"]) > 0),
                             "f20": _dec(p["f20"]), "f5": _dec(p["f5"]), "mom": mom.get(p["code"]),
                             # Yahoo dividend amounts are on today's split basis, so the yield uses the adjusted close
                             "dy": (dps.get(p["code"], Decimal(0)) / adj_close) if adj_close > 0 else None, "sector": p["sector"]}
        if m and m.get("net_profit") is not None:
            r.update({"ep": m["net_profit"] / mcap if mcap > 0 else None, "bp": (m["equity"] / mcap) if (m["equity"] is not None and mcap > 0) else None,
                      "ep_ttm": (m["net_profit_ttm"] / mcap) if (m.get("net_profit_ttm") is not None and mcap > 0) else None,
                      "roe": m["roe"], "der": m["der"], "cfo": m["cfo"], "np_yoy": m["np_yoy"], "rev_yoy": m["rev_yoy"],
                      "gate_loose": m["gate_loose"], "gate_strict": m["gate_strict"], "strict_fails": m["strict_fails"],
                      "warnings": m["warnings"], "annual_period": m["annual_period"], "ttm_basis": m.get("ttm_basis"),
                      "sector": m.get("sector") or p["sector"], "is_financial": m.get("is_financial"),
                      # cash conversion: operating cash flow per rupiah of audited profit, capped (rank input of strict_cash)
                      "conv": (min(m["cfo"] / m["net_profit"], CONV_CAP) if (m["cfo"] is not None and m["net_profit"] > 0) else None)})
        else:
            r.update({"ep": None, "bp": None, "ep_ttm": None, "roe": None, "der": None, "cfo": None, "np_yoy": None, "rev_yoy": None, "conv": None,
                      "gate_loose": False, "gate_strict": False, "strict_fails": ["no_audited_report"], "warnings": [],
                      "annual_period": None, "ttm_basis": None, "is_financial": False})
        # a ratio beyond any real valuation means a mis-scaled report, not a bargain: drop the name and say why
        if any(r[k] is not None and abs(r[k]) > MAX_RATIO for k in ("ep", "bp", "ep_ttm", "dy")):
            r.update({"ep": None, "bp": None, "ep_ttm": None, "dy": None, "gate_loose": False, "gate_strict": False,
                      "warnings": [*r["warnings"], "data_error_ratio"]})
        if not r["tradable"]:
            r["warnings"] = [*r["warnings"], "no_trade_on_date"]
        rows.append(r)
    pool = rank_pool([dict(r) for r in rows])
    return {"as_of": D, "liquid": len(rows), "with_fundamentals": sum(1 for r in rows if r["ep"] is not None), "pool": len(pool),
            "selected_n": sum(1 for r in pool if r["selected"]), "pool_rows": pool, "all_rows": rows}


def momentum_at(conn: psycopg.Connection, D: date, codes: list[str], long: int = 252, skip: int = 21) -> dict[str, Decimal]:
    """12-1 month price momentum on the day: close ``skip`` bars before D over close ``long`` bars before D, minus one
    (the same definition as research/idx_top10.py). Empty when the calendar is too short."""
    dates = [r["d"] for r in _rows(conn, """
        SELECT trade_date FROM (SELECT DISTINCT trade_date FROM idx.bar WHERE source = 'idx' AND trade_date <= %s
                                 ORDER BY trade_date DESC LIMIT %s) t ORDER BY trade_date""", (D, long + 1), ["d"])]
    if len(dates) < long + 1 or not codes:
        return {}
    far_d, near_d = dates[0], dates[-1 - skip]
    q = "SELECT code, close * adj_factor AS c FROM idx.bar WHERE source = 'idx' AND trade_date = %s AND code = ANY(%s)"
    far = {r["code"]: Decimal(r["c"]) for r in _rows(conn, q, (far_d, codes), ["code", "c"]) if r["c"]}
    near = {r["code"]: Decimal(r["c"]) for r in _rows(conn, q, (near_d, codes), ["code", "c"]) if r["c"]}
    return {c: near[c] / far[c] - 1 for c in codes if c in near and c in far and far[c] > 0}


def _avg_ranks(pool: list[dict[str, Any]], key: str) -> None:
    """Average rank (ties share the mean of their positions; missing values rank lowest) -> ``rank_<key>``."""
    order = sorted(pool, key=lambda r: (r.get(key) is not None, r.get(key) if r.get(key) is not None else Decimal(0), r["code"]))
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and order[j + 1].get(key) == order[i].get(key):
            j += 1
        avg = Decimal(i + 1 + j + 1) / 2
        for r in order[i:j + 1]:
            r[f"rank_{key}"] = avg
        i = j + 1


def rank_pool(rows: list[dict[str, Any]], *, gate: str | None = "loose", keys: tuple[str, ...] = KEYS,
              top_fraction: int = TOP_FRACTION, min_names: int = MIN_NAMES, min_pool: int = MIN_POOL,
              sector_cap: float | None = None) -> list[dict[str, Any]]:
    """Pure, and the one implementation of the rule. ``gate`` loose | strict | None -> tradable names with E/P > 0 ->
    composite of average ranks over ``keys`` (higher = cheaper) -> top ``1/top_fraction``, at least ``min_names``, only
    when the pool holds at least ``min_pool`` names. ``sector_cap`` (a fraction of the selection, e.g. 1/3) walks down the
    ranking skipping names whose sector is already full — the pre-registered concentration variant. Rows are annotated
    in place: ``rank_<key>``, ``score``, ``rank`` (position), ``selected``; the sorted pool is returned."""
    gate_key = {"loose": "gate_loose", "strict": "gate_strict", None: None}[gate]
    pool = [r for r in rows if (gate_key is None or r.get(gate_key)) and r.get("ep") is not None and r["ep"] > 0
            and r.get("tradable", True)]
    n = len(pool)
    for key in keys:
        _avg_ranks(pool, key)
    for r in pool:
        r["score"] = sum(r[f"rank_{k}"] for k in keys)
    pool.sort(key=lambda r: (-r["score"], r["code"]))
    k = max(min_names, n // top_fraction) if n >= max(min_pool, 1) else 0
    cap = max(1, math.ceil(sector_cap * k)) if (sector_cap and k) else None
    taken: dict[str, int] = {}
    chosen = 0
    for i, r in enumerate(pool, 1):
        r["rank"] = i
        ok = chosen < k
        if ok and cap is not None:
            s = r.get("sector") or "?"
            ok = taken.get(s, 0) < cap
            if ok:
                taken[s] = taken.get(s, 0) + 1
        r["selected"] = ok
        chosen += ok
    return pool


def _dec(v):
    return None if v is None else Decimal(v)


def store(conn: psycopg.Connection, res: dict[str, Any]) -> int:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM idx.candidate WHERE run_date = %s", (res["as_of"],))
        cur.executemany(
            """
            INSERT INTO idx.candidate (run_date, code, rank, selected, score, price, mcap, ep, bp, dy, ep_ttm, roe, der, np_yoy,
                                       gate_loose, gate_strict, strict_fails, warnings, f20, v60, annual_period, ttm_basis, sector, mom, conv)
            VALUES (%(run_date)s, %(code)s, %(rank)s, %(selected)s, %(score)s, %(price)s, %(mcap)s, %(ep)s, %(bp)s, %(dy)s, %(ep_ttm)s,
                    %(roe)s, %(der)s, %(np_yoy)s, %(gate_loose)s, %(gate_strict)s, %(strict_fails)s, %(warnings)s, %(f20)s, %(v60)s,
                    %(annual_period)s, %(ttm_basis)s, %(sector)s, %(mom)s, %(conv)s)
            """,
            [{"run_date": res["as_of"], **{k: r.get(k) for k in ("code", "rank", "selected", "score", "price", "mcap", "ep", "bp", "dy",
              "ep_ttm", "roe", "der", "np_yoy", "gate_loose", "gate_strict", "f20", "v60", "annual_period", "ttm_basis", "sector", "mom", "conv")},
              "strict_fails": r.get("strict_fails") or [], "warnings": r.get("warnings") or []} for r in res["pool_rows"]])
    conn.commit()
    return len(res["pool_rows"])


def render(res: dict[str, Any], top: int | None = None) -> str:
    o = [f"# IDX candidates as of {res['as_of']}",
         f"liquid {res['liquid']} | with audited fundamentals {res['with_fundamentals']} | pass loose gate & E/P>0 {res['pool']} | selected top fifth (min {MIN_NAMES}): **{res['selected_n']}**",
         "", "| # | code | price | mcap T | E/P | E/P ttm | P/E | P/B | DY | ROE | D/E | NP yoy | flow20 | strict gate | warnings | basis |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    rows = res["pool_rows"][: (top or res["selected_n"] + 10)]
    for r in rows:
        pe = (1 / r["ep"]) if r["ep"] else None
        cells = [f"{r['rank']}{'*' if r['selected'] else ''}", r["code"], f"{float(r['price']):,.0f}", f"{float(r['mcap']) / 1e12:.2f}",
                 _p(r["ep"]), _p(r["ep_ttm"]), _x(pe, 1), _x(1 / r["bp"] if r["bp"] else None), _p(r["dy"]), _p(r["roe"]), _x(r["der"]),
                 _p(r["np_yoy"], 0), _p(r["f20"]), "PASS" if r["gate_strict"] else "fail: " + ",".join(r["strict_fails"]),
                 ",".join(r["warnings"]) or "-", r["ttm_basis"] or "-"]
        o.append("| " + " | ".join(cells) + " |")
    o.append("")
    o.append("* = selected. Rule: board Utama/Pengembangan on the day, traded, liquid -> loose gate (profit>0, ROE>=5%) -> composite average "
             f"rank(E/P, B/P, DY) -> top fifth, min {MIN_NAMES} (pool >= {MIN_POOL}), EW, annual rebalance. "
             "Strict-gate fails and TTM warnings are for the operator's judgment, not automatic exclusion.")
    return "\n".join(o)


def _p(v, d=1):
    return "-" if v is None else f"{100 * float(v):+.{d}f}%"


def _x(v, d=2):
    return "-" if v is None else f"{float(v):.{d}f}x"


def run(conn: psycopg.Connection, as_of: date | None = None) -> tuple[runlog.RunResult, dict[str, Any]]:
    r = runlog.RunResult(JOB, as_of.isoformat() if as_of else "latest")
    run_id = runlog.start(conn, JOB, r.run_key)
    res = {}
    try:
        res = build(conn, as_of)
        r.rows_in = res["liquid"]
        r.rows_out = store(conn, res)
        r.detail = {"as_of": str(res["as_of"]), "pool": res["pool"], "selected": res["selected_n"]}
    except Exception as e:
        conn.rollback()
        r.status = "failed"
        r.error = f"{type(e).__name__}: {e}"[:500]
        logger.exception("idx candidates failed")
    runlog.finish(conn, run_id, r)
    return r, res


def to_json(res: dict[str, Any]) -> str:
    return json.dumps({k: v for k, v in res.items() if k != "all_rows"}, default=str, indent=1)
