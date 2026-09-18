"""Nightly factor scores (open-research plan phase 2; spec §04). Four scores per liquid name per trade date, 0-100 =
percentile within that day's liquid universe, with the raw numbers behind each one kept in ``inputs``:

  value       cheapness - average rank of E/P, B/P and dividend yield among tradable names with positive audited profit
              (the rev.3 rank pool, ``candidates.rank_pool`` with no gate); names with a loss get no Value score
  quality     gates passed out of eight (``quality.evaluate``) -> percentile among names with five audited years
  trend       average percentile of close/60-day high, close/MA200 and volume/20-day median; ``trend_flag`` = the breakout
              rule of the trend book (close = 60d high, > MA200, volume >= 1.5x) evaluated on the same adjusted closes
  turnaround  flag - prior-year loss and TTM profit (annual comparative) or a YTD turn in the latest quarter, with revenue
              growing (the doublers study's screen D without its liquidity clause, which the universe already applies);
              ``bucket`` = market-cap band x 12-1 momentum band, the slices the study reported

Everything is point in time: the reports published by the day's close, the day's own closes. ``build`` writes
``idx.score_daily`` for one date; the scheduler runs it after the marks; ``idx scores build|show`` by hand.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import psycopg
import psycopg.types.json

from . import candidates, quality
from .card import _rows
from .metrics import as_of_close, comparative, fundamentals_asof

logger = logging.getLogger(__name__)
JOB = "scores"
FIELDS = {  # the screener's field catalogue: what a criteria can filter on, where it lives, how the UI words it
    "value": ("score", "number", "skor Value 0-100 (semakin tinggi semakin murah)"),
    "quality": ("score", "number", "skor Quality 0-100 (gate kualitas terpenuhi)"),
    "trend": ("score", "number", "skor Trend 0-100"),
    "gates": ("score", "number", "jumlah gate kualitas terpenuhi, 0-8"),
    "turnaround": ("score", "bool", "laba berbalik positif setelah rugi, pendapatan tumbuh"),
    "trend_flag": ("score", "bool", "memenuhi rule breakout: close = tertinggi 60 hari, > MA200, volume >= 1,5x"),
    "gate_loose": ("input", "bool", "laba audit positif dan ROE >= 5 %"),
    "gate_strict": ("input", "bool", "gate strict: ROE >= 10 %, laba tahun sebelumnya positif, CFO > 0, D/E <= 1,5"),
    "mom_12_1": ("input", "number", "return 12 bulan tanpa bulan terakhir (0,5 = +50 %)"),
    "mcap_t": ("input", "number", "kapitalisasi pasar, Rp triliun"),
    "v60_bn": ("input", "number", "nilai transaksi median 60 hari, Rp miliar"),
    "ep": ("input", "number", "earnings yield audit (laba / nilai pasar)"),
    "ep_ttm": ("input", "number", "earnings yield TTM"),
    "bp": ("input", "number", "book / nilai pasar"),
    "dy": ("input", "number", "dividend yield 12 bulan"),
    "roe": ("input", "number", "ROE audit terakhir"),
    "der": ("input", "number", "utang / ekuitas"),
    "close_hi60": ("input", "number", "close / tertinggi 60 hari"),
    "close_ma200": ("input", "number", "close / rata-rata 200 hari"),
    "vol_ratio": ("input", "number", "volume / median 20 hari"),
    "close": ("input", "number", "harga penutupan"),
    "sector": ("input", "text", "sektor IDX-IC"),
}


def _f(v) -> float | None:
    return None if v is None else float(v)


def _pct(values: dict[str, float | None]) -> dict[str, float | None]:
    """Percentile rank 0-100 (ties share the mean position; None stays None). 100 = highest."""
    ok = [(v, c) for c, v in values.items() if v is not None]
    n = len(ok)
    out: dict[str, float | None] = {c: None for c in values}
    if n == 0:
        return out
    ok.sort(key=lambda t: (t[0], t[1]))
    i = 0
    while i < n:
        j = i
        while j + 1 < n and ok[j + 1][0] == ok[i][0]:
            j += 1
        p = (i + 1 + j + 1) / 2 / n * 100 if n > 1 else 100.0
        for _, c in ok[i:j + 1]:
            out[c] = round(p, 1)
        i = j + 1
    return out


def trend_inputs(conn: psycopg.Connection, d: date, codes: list[str]) -> dict[str, dict[str, float | None]]:
    """close/60d high, close/MA200, volume/median20 on adjusted closes, and the breakout flag, per code as of ``d``."""
    rows = _rows(conn, """SELECT code, trade_date, close * adj_factor AS adj, volume FROM idx.bar
                           WHERE source IN ('idx', 'yahoo') AND trade_date > %s AND trade_date <= %s AND code = ANY(%s) ORDER BY code, trade_date""",
                 (d - timedelta(days=420), d, codes), ["code", "d", "adj", "vol"])
    series: dict[str, list[tuple[float, float]]] = {}
    for r in rows:
        series.setdefault(r["code"], []).append((float(r["adj"]), float(r["vol"] or 0)))
    out: dict[str, dict[str, float | None]] = {}
    for c in codes:
        s = series.get(c) or []
        adj = [a for a, _ in s]
        vol = [v for _, v in s]
        rec: dict[str, float | None] = {"close_hi60": None, "close_ma200": None, "vol_ratio": None, "trend_flag": None}
        if len(adj) >= 200 and s and s[-1] and adj[-1] > 0:
            hi60, ma200 = max(adj[-60:]), sum(adj[-200:]) / 200
            med20 = sorted(vol[-20:])[len(vol[-20:]) // 2] if len(vol) >= 20 else 0
            vr = (vol[-1] / med20) if med20 > 0 else None
            rec.update({"close_hi60": adj[-1] / hi60, "close_ma200": adj[-1] / ma200, "vol_ratio": vr,
                        "trend_flag": bool(adj[-1] >= hi60 and adj[-1] > ma200 and vr is not None and vr >= 1.5)})
        out[c] = rec
    return out


def quarter_turn(conn: psycopg.Connection, d: date, codes: list[str]) -> dict[str, dict[str, Any]]:
    """Latest quarterly YTD row published by the close: YTD turn (prior-year YTD <= 0, YTD > 0) and revenue growth."""
    rows = _rows(conn, """SELECT DISTINCT ON (code) code, net_profit, revenue, net_profit_yoy, revenue_yoy, net_profit_prior, revenue_prior
                            FROM idx.fundamental
                           WHERE published_at <= %s AND period_end >= %s AND period_label <> 'TAHUNAN' AND code = ANY(%s)
                           ORDER BY code, period_end DESC, published_at DESC""",
                 (as_of_close(d), d - timedelta(days=400), codes), ["code", "net_profit", "revenue", "np_yoy", "rev_yoy", "np_prior", "rev_prior"])
    out = {}
    for r in rows:
        npp = comparative(r, "net_profit")
        rp = comparative(r, "revenue")
        np_ = Decimal(r["net_profit"]) if r["net_profit"] is not None else None
        rev = Decimal(r["revenue"]) if r["revenue"] is not None else None
        out[r["code"]] = {"ytd_turn": bool(npp is not None and npp <= 0 and np_ is not None and np_ > 0),
                          "q_rev_yoy": (float((rev - rp) / abs(rp)) if (rev is not None and rp not in (None, 0)) else None)}
    return out


def bucket_of(mcap: float | None, mom: float | None) -> str | None:
    if mcap is None:
        return None
    band = "<3T" if mcap < 3e12 else ("3-20T" if mcap < 20e12 else ">20T")
    m = "mom:?" if mom is None else ("mom:<=150" if mom <= 1.5 else "mom:>150")
    return f"mcap:{band},{m}"


def compute(conn: psycopg.Connection, d: date | None = None) -> dict[str, Any]:
    """Pure-ish: reads the day, returns the rows to store (no writes)."""
    res = candidates.build(conn, d)
    D: date = res["as_of"]
    rows = [r for r in res["all_rows"] if r["tradable"] and r["price"] >= 100]      # the desk universe: liquid, traded, >= Rp 100
    codes = [r["code"] for r in rows]
    by = {r["code"]: r for r in rows}
    # value: the rank pool without a gate, percentile of the composite rank among names with E/P > 0
    pool = candidates.rank_pool([dict(r) for r in rows], gate=None)
    value = _pct({r["code"]: float(r["score"]) for r in pool})
    # trend
    tr = trend_inputs(conn, D, codes)
    p_hi, p_ma, p_vr = (_pct({c: tr[c][k] for c in codes}) for k in ("close_hi60", "close_ma200", "vol_ratio"))
    # quality
    ttm = fundamentals_asof(conn, D, codes)
    closes = {c: float(by[c]["price"]) for c in codes}
    sectors = {c: by[c].get("sector") for c in codes}
    q = quality.evaluate_many(conn, D, codes, ttm, closes, sectors)
    q_pct = _pct({c: (float(q[c]["passed"]) if q[c]["passed"] is not None else None) for c in codes})
    # turnaround
    qt = quarter_turn(conn, D, codes)
    out = []
    for c in codes:
        r, t, m = by[c], tr[c], ttm.get(c) or {}
        mom = _f(r.get("mom"))
        mcap = _f(r.get("mcap"))
        annual_turn = bool(m.get("net_profit_prior") is not None and m["net_profit_prior"] <= 0 and m.get("net_profit_ttm") is not None and m["net_profit_ttm"] > 0)
        qq = qt.get(c) or {}
        turnaround = bool((annual_turn or qq.get("ytd_turn")) and (qq.get("q_rev_yoy") or 0) > 0)
        trend_parts = [p for p in (p_hi[c], p_ma[c], p_vr[c]) if p is not None]
        inputs = {"ep": _f(r.get("ep")), "ep_ttm": _f(r.get("ep_ttm")), "bp": _f(r.get("bp")), "dy": _f(r.get("dy")), "roe": _f(r.get("roe")),
                  "der": _f(r.get("der")), "gate_loose": bool(r.get("gate_loose")), "gate_strict": bool(r.get("gate_strict")),
                  "strict_fails": r.get("strict_fails") or [], "mom_12_1": mom, "mcap_t": (mcap / 1e12) if mcap else None,
                  "v60_bn": (float(r["v60"]) / 1e9) if r.get("v60") is not None else None, "close": _f(r.get("price")), "sector": r.get("sector"),
                  "name": r.get("name"), "close_hi60": t["close_hi60"], "close_ma200": t["close_ma200"], "vol_ratio": t["vol_ratio"],
                  "value_rank": next((int(p["rank"]) for p in pool if p["code"] == c), None), "value_pool": len(pool),
                  "quality_gates": q[c].get("gates"), "quality_metrics": quality.to_decimal_free(q[c].get("metrics") or {}),
                  "quality_years": q[c].get("years"), "quality_is_financial": q[c].get("is_financial"), "annual_turn": annual_turn, "ytd_turn": bool(qq.get("ytd_turn")),
                  "q_rev_yoy": qq.get("q_rev_yoy"), "ttm_basis": m.get("ttm_basis"), "warnings": r.get("warnings") or []}
        out.append({"trade_date": D, "code": c, "value": value.get(c), "quality": q_pct.get(c),
                    "trend": (round(sum(trend_parts) / len(trend_parts), 1) if trend_parts else None),
                    "turnaround": turnaround, "trend_flag": bool(t["trend_flag"]), "gates": q[c].get("passed"),
                    "bucket": bucket_of(mcap, mom), "inputs": inputs})
    return {"as_of": D, "rows": out, "n": len(out), "n_value": sum(1 for r in out if r["value"] is not None),
            "n_quality": sum(1 for r in out if r["gates"] is not None), "n_trend_flag": sum(1 for r in out if r["trend_flag"]),
            "n_turnaround": sum(1 for r in out if r["turnaround"])}


def store(conn: psycopg.Connection, res: dict[str, Any]) -> int:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM idx.score_daily WHERE trade_date = %s", (res["as_of"],))
        cur.executemany("""INSERT INTO idx.score_daily (trade_date, code, value, quality, trend, turnaround, trend_flag, gates, bucket, inputs)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                        [(r["trade_date"], r["code"], r["value"], r["quality"], r["trend"], r["turnaround"], r["trend_flag"], r["gates"], r["bucket"],
                          psycopg.types.json.Jsonb(quality.to_decimal_free(r["inputs"]))) for r in res["rows"]])
    conn.commit()
    return len(res["rows"])


def build(conn: psycopg.Connection, d: date | None = None) -> dict[str, Any]:
    res = compute(conn, d)
    n = store(conn, res)
    logger.info("scores %s: %d names (value %d, quality %d, breakout %d, turnaround %d)", res["as_of"], n, res["n_value"], res["n_quality"],
                res["n_trend_flag"], res["n_turnaround"])
    return {k: v for k, v in res.items() if k != "rows"} | {"stored": n}


def latest_date(conn: psycopg.Connection) -> date | None:
    return _rows(conn, "SELECT max(trade_date) AS d FROM idx.score_daily", (), ["d"])[0]["d"]


def rows_for(conn: psycopg.Connection, d: date | None = None, codes: list[str] | None = None) -> list[dict[str, Any]]:
    d = d or latest_date(conn)
    if d is None:
        return []
    return _rows(conn, """SELECT s.trade_date, s.code, l.name, s.value, s.quality, s.trend, s.turnaround, s.trend_flag, s.gates, s.bucket, s.inputs
                            FROM idx.score_daily s LEFT JOIN idx.listing l USING (code)
                           WHERE s.trade_date = %s AND (%s::text[] IS NULL OR s.code = ANY(%s)) ORDER BY s.code""",
                 (d, codes, codes), ["trade_date", "code", "name", "value", "quality", "trend", "turnaround", "trend_flag", "gates", "bucket", "inputs"])


def history(conn: psycopg.Connection, code: str, days: int = 250) -> list[dict[str, Any]]:
    return _rows(conn, """SELECT trade_date, value, quality, trend, turnaround, trend_flag, gates FROM idx.score_daily
                           WHERE code = %s ORDER BY trade_date DESC LIMIT %s""", (code.upper(), days),
                 ["trade_date", "value", "quality", "trend", "turnaround", "trend_flag", "gates"])[::-1]


def render(res: dict[str, Any], top: int = 15) -> str:
    rows = sorted(res["rows"], key=lambda r: -(r["value"] or 0))
    o = [f"# scores {res['as_of']} | {res['n']} names | value {res['n_value']} | quality {res['n_quality']} | breakout {res['n_trend_flag']} | turnaround {res['n_turnaround']}",
         f"{'code':6s} {'value':>5s} {'qual':>5s} {'trend':>5s} {'gates':>5s} brk turn bucket"]
    for r in rows[:top]:
        o.append(f"{r['code']:6s} {r['value'] or 0:5.0f} {r['quality'] or 0:5.0f} {r['trend'] or 0:5.0f} {r['gates'] if r['gates'] is not None else '-':>5} "
                 f"{'*' if r['trend_flag'] else ' '}   {'*' if r['turnaround'] else ' '}    {r['bucket'] or ''}")
    return "\n".join(o)
