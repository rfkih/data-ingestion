"""One stock for the app's Stock screen, and the search box behind it.

``search`` answers "code or company name" from the active listings with the last close and the day's change; ``profile``
is the structured cousin of the thesis card (``card.build``): the same point-in-time valuation (latest audited report at
today's price and listed shares), the day's facts, 52-week range, liquidity, the reported periods, dividends, foreign flow
and press. Nothing is invented: what the data plane does not hold (a company profile text, the shareholder register) comes
back null / empty so the screen can say so.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import psycopg

from .card import _rows
from .metrics import evaluate

LIQ_VALUE, LIQ_PRICE = Decimal(5_000_000_000), Decimal(100)


def _f(v: Any) -> float | None:
    return None if v is None else float(v)


def _chg(close: Any, prev: Any) -> float | None:
    if close is None or not prev:
        return None
    return float((Decimal(close) - Decimal(prev)) / Decimal(prev) * 100)


def search(conn: psycopg.Connection, q: str = "", codes: list[str] | None = None, limit: int = 8) -> list[dict[str, Any]]:
    """Active listings whose code starts with ``q`` (first) or whose name contains it, with the last close and change. With an
    empty ``q``, the given ``codes`` in that order (the app's recent list); with neither, nothing."""
    q = (q or "").strip()
    codes = [c.upper().strip() for c in (codes or []) if c and c.strip()]
    if not q and not codes:
        return []
    limit = max(1, min(int(limit), 50))
    where = "l.status = 'ACTIVE' AND (l.code ILIKE %s OR l.name ILIKE %s)" if q else "l.code = ANY(%s)"
    params: tuple = (f"{q}%", f"%{q}%", f"{q}%", limit) if q else (codes, limit)
    rows = _rows(conn, f"""
        WITH last2 AS (
            SELECT code, close, row_number() OVER (PARTITION BY code ORDER BY trade_date DESC) AS rn
              FROM idx.bar WHERE source = 'idx' AND trade_date >= current_date - 21)
        SELECT l.code, l.name, l.sector, a.close, b.close AS prev
          FROM idx.listing l LEFT JOIN last2 a ON a.code = l.code AND a.rn = 1 LEFT JOIN last2 b ON b.code = l.code AND b.rn = 2
         WHERE {where}
         ORDER BY {"(l.code ILIKE %s) DESC, " if q else ""}l.code LIMIT %s""", params, ["code", "name", "sector", "close", "prev"])
    out = [{"code": r["code"], "name": r["name"], "sector": r["sector"], "close": _f(r["close"]), "chg_pct": _chg(r["close"], r["prev"])} for r in rows]
    if codes:
        order = {c: i for i, c in enumerate(codes)}
        out.sort(key=lambda r: order.get(r["code"], 99))
    return out


def _period(f: dict[str, Any]) -> str:
    y = f["period_end"].year
    return f"FY{y}" if f["label"] == "TAHUNAN" else f"{f['label']} {y}"


def _fin(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[date] = set()
    out = []
    for f in rows:                                     # newest publication first per period_end
        if f["period_end"] in seen:
            continue
        seen.add(f["period_end"])
        out.append({"period": _period(f), "period_end": f["period_end"], "months": f["months"], "published_at": f["pub"],
                    "revenue": _f(f["revenue"]), "net_profit": _f(f["net_profit"]), "eps": _f(f["eps"]), "margin": _f(f["margin"]),
                    "revenue_yoy": _f(f["rev_yoy"]), "net_profit_yoy": _f(f["np_yoy"])})
    return out


def profile(conn: psycopg.Connection, code: str) -> dict[str, Any] | None:
    """The Stock screen's whole payload as of the last bar; None when the code has no listing and no price."""
    code = code.upper().strip()
    listing = _rows(conn, "SELECT name, board, sector, subsector, listing_date, status, listed_shares FROM idx.listing WHERE code = %s", (code,),
                    ["name", "board", "sector", "subsector", "listing_date", "status", "listed_shares"])
    L = listing[0] if listing else {}
    bars = _rows(conn, """
        SELECT b.trade_date, b.open, b.high, b.low, b.close, b.volume, b.value
          FROM idx.bar b WHERE b.code = %s AND b.source = 'idx' ORDER BY b.trade_date DESC LIMIT 2""", (code,),
        ["d", "open", "high", "low", "close", "volume", "value"])
    if not bars and not listing:
        return None
    out: dict[str, Any] = {"code": code, "name": L.get("name") or code, "sector": L.get("sector"), "subsector": L.get("subsector"),
                           "board": L.get("board"), "listed": L.get("listing_date"), "status": L.get("status"), "as_of": None,
                           "close": None, "prev": None, "open": None, "high": None, "low": None, "volume": None, "value": None, "trades": None,
                           "chg_pct": None, "mcap": None, "shares": _f(L.get("listed_shares")), "pe": None, "pbv": None, "dy": None, "eps": None,
                           "bvps": None, "hi52": None, "lo52": None, "v60": None, "liquid": None, "pe_ttm": None, "ttm_basis": None,
                           "quarterly": [], "annual": [], "dividends": [], "profile": None, "holders": [], "news": [], "foreign": []}
    if not bars:
        return out
    b = bars[0]
    D: date = b["d"]
    price = Decimal(b["close"])
    summ = _rows(conn, """
        SELECT previous, open, high, low, volume, value, frequency, listed_shares FROM idx.daily_summary WHERE code = %s AND trade_date = %s""",
        (code, D), ["previous", "open", "high", "low", "volume", "value", "frequency", "shares"])
    s = summ[0] if summ else {}
    prev = s.get("previous") if s.get("previous") else (bars[1]["close"] if len(bars) > 1 else None)
    shares = Decimal(s.get("shares") or L.get("listed_shares") or 0)
    mcap = price * shares
    feat = _rows(conn, "SELECT value_60d_median FROM idx.feature_daily WHERE code = %s AND trade_date <= %s ORDER BY trade_date DESC LIMIT 1",
                 (code, D), ["v60"])
    v60 = Decimal(feat[0]["v60"]) if feat and feat[0]["v60"] is not None else None
    rng = _rows(conn, """
        SELECT max(coalesce(high, close)) AS hi, min(coalesce(low, close)) AS lo FROM idx.bar
         WHERE code = %s AND source = 'idx' AND trade_date > %s AND trade_date <= %s""", (code, D - timedelta(days=365), D), ["hi", "lo"])
    fund = _rows(conn, """
        SELECT period_end, period_label, published_at, months, revenue, net_profit, total_equity, total_assets, total_debt, cash, cfo,
               capex, dividends_paid, eps, bvps, roe, roa, der, net_margin, revenue_yoy, net_profit_yoy, currency, sector
          FROM idx.fundamental WHERE code = %s AND published_at <= %s ORDER BY period_end DESC, published_at DESC
        """, (code, D + timedelta(days=1)),
        ["period_end", "label", "pub", "months", "revenue", "net_profit", "equity", "assets", "debt", "cash", "cfo", "capex",
         "div_paid", "eps", "bvps", "roe", "roa", "der", "margin", "rev_yoy", "np_yoy", "currency", "sector"])
    annual = [f for f in fund if f["label"] == "TAHUNAN"]
    latest_annual = annual[0] if annual else None
    latest_quarter = next((f for f in fund if f["label"] != "TAHUNAN"), None)
    m = evaluate(code, latest_annual, latest_quarter)
    divs = _rows(conn, """
        SELECT d.ex_date, d.payment_date, d.amount_per_share, d.kind,
               (SELECT close FROM idx.bar b WHERE b.code = d.code AND b.source = 'idx' AND b.trade_date <= d.ex_date ORDER BY b.trade_date DESC LIMIT 1) AS px
          FROM idx.dividend d WHERE d.code = %s ORDER BY d.ex_date DESC LIMIT 8""", (code,), ["ex_date", "pay_date", "dps", "kind", "px"])
    ttm_div = sum((Decimal(x["dps"]) for x in divs if x["ex_date"] <= D and x["ex_date"] > D - timedelta(days=365)), Decimal(0))
    flow = _rows(conn, """
        SELECT trade_date, foreign_buy, foreign_sell, close FROM idx.daily_summary WHERE code = %s AND trade_date <= %s
         ORDER BY trade_date DESC LIMIT 5""", (code, D), ["d", "fb", "fs", "close"])
    news = _rows(conn, """SELECT source, url, published_at, title FROM idx.news_article WHERE %s = ANY(codes)
                          ORDER BY published_at DESC NULLS LAST LIMIT 10""", (code,), ["source", "url", "at", "title"])

    pe = pb = None
    if latest_annual and latest_annual["net_profit"] and mcap > 0:
        np_ = Decimal(latest_annual["net_profit"])
        pe = mcap / np_ if np_ > 0 else None
    if latest_annual and latest_annual["equity"] and mcap > 0:
        pb = mcap / Decimal(latest_annual["equity"])
    pe_ttm = (mcap / m["net_profit_ttm"]) if (m.get("net_profit_ttm") and m["net_profit_ttm"] > 0 and mcap > 0) else None
    out.update({
        "as_of": D, "close": float(price), "prev": _f(prev), "open": _f(s.get("open") or b["open"]), "high": _f(s.get("high") or b["high"]),
        "low": _f(s.get("low") or b["low"]), "volume": _f(s.get("volume") if s else b["volume"]), "value": _f(s.get("value") if s else b["value"]),
        "trades": s.get("frequency"), "chg_pct": _chg(price, prev), "mcap": float(mcap) if shares else None, "shares": float(shares) if shares else None,
        "pe": _f(pe), "pbv": _f(pb), "dy": float(ttm_div / price * 100) if price > 0 else None,
        "eps": _f(latest_annual["eps"]) if latest_annual else None, "bvps": _f(latest_annual["bvps"]) if latest_annual else None,
        "hi52": _f(rng[0]["hi"]) if rng else None, "lo52": _f(rng[0]["lo"]) if rng else None, "v60": _f(v60),
        "liquid": (v60 >= LIQ_VALUE and price >= LIQ_PRICE) if v60 is not None else None,
        "pe_ttm": _f(pe_ttm), "ttm_basis": m.get("ttm_basis"),
        "quarterly": _fin([f for f in fund if f["label"] != "TAHUNAN"])[:8], "annual": _fin(annual)[:5],
        "dividends": [{"ex_date": x["ex_date"], "pay_date": x["pay_date"], "amount": _f(x["dps"]), "kind": x["kind"],
                       "yield_pct": float(Decimal(x["dps"]) / Decimal(x["px"]) * 100) if x["px"] else None} for x in divs],
        "news": [{"at": n["at"], "title": n["title"], "source": n["source"], "url": n["url"]} for n in news],
        "foreign": [{"date": r["d"], "net_shares": _f((r["fb"] or 0) - (r["fs"] or 0)) if (r["fb"] is not None or r["fs"] is not None) else None,
                     "net_value": _f(((r["fb"] or 0) - (r["fs"] or 0)) * (r["close"] or 0)) if (r["fb"] is not None or r["fs"] is not None) else None}
                    for r in reversed(flow)],
    })
    return out
