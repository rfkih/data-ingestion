"""Benchmarks for the Strategies page's equity chart (operator, 2026-09-26: "compare dengan IHSG / reksadana saham tertentu").

  index  the exchange's own indices in idx.index_daily (IHSG = COMPOSITE, LQ45, IDX SMC Liquid, ...): PRICE indices, so
         dividends are not in them - a strategy's backtest counts its dividends only through adjusted prices
  fund   a mutual fund's NAV per unit in idx.fund_nav (reksadana): total return by construction (dividends reinvested, the
         manager's fee taken). The desk has no feed for them; the operator imports a NAV history (CLI `fund-import`)

A benchmark key is "<kind>:<code>" (index:COMPOSITE, fund:<code>). The page asks for the series over a strategy's own
period and does the comparison itself (lib/strategyStats).
"""
from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path
from typing import Any

import psycopg

# the indices offered first, in this order, with the names people use; every other index is offered after them
FEATURED = {
    "COMPOSITE": "IHSG",
    "LQ45": "LQ45",
    "IDX30": "IDX30",
    "IDX80": "IDX80",
    "KOMPAS100": "Kompas100",
    "IDXSMC-LIQ": "IDX SMC Liquid (small and mid caps)",
    "IDXSMC-COM": "IDX SMC Composite",
    "JII": "Jakarta Islamic Index",
    "IDXHIDIV20": "IDX High Dividend 20",
    "IDXQ30": "IDX Quality 30",
    "IDXV30": "IDX Value 30",
    "IDXG30": "IDX Growth 30",
}


def _rows(conn: psycopg.Connection, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [c.name for c in cur.description]
        return [r if isinstance(r, dict) else dict(zip(cols, r, strict=True)) for r in cur.fetchall()]


def catalog(conn: psycopg.Connection) -> list[dict[str, Any]]:
    """Every benchmark the page can draw: featured indices, the other indices, then the imported funds."""
    idx = {r["index_code"]: r for r in _rows(conn, """SELECT index_code, min(trade_date) AS d0, max(trade_date) AS d1, count(*) AS n
                                                           FROM idx.index_daily WHERE close > 0 GROUP BY index_code""")}
    out = [{"key": f"index:{c}", "code": c, "label": lbl, "kind": "index", "featured": True, "from": str(idx[c]["d0"]), "to": str(idx[c]["d1"])}
           for c, lbl in FEATURED.items() if c in idx]
    out += [{"key": f"index:{c}", "code": c, "label": c, "kind": "index", "featured": False, "from": str(r["d0"]), "to": str(r["d1"])}
            for c, r in sorted(idx.items()) if c not in FEATURED and r["n"] >= 250]
    out += [{"key": f"fund:{r['fund_code']}", "code": r["fund_code"], "label": r["name"], "kind": "fund", "featured": True,
             "from": str(r["d0"]), "to": str(r["d1"]), "source": r["source"]}
            for r in _rows(conn, """SELECT fund_code, max(name) AS name, max(source) AS source, min(nav_date) AS d0, max(nav_date) AS d1
                                      FROM idx.fund_nav GROUP BY fund_code ORDER BY max(name)""")]
    return out


def series(conn: psycopg.Connection, key: str, d0: date | None = None, d1: date | None = None) -> dict[str, Any]:
    """{key, label, kind, points: [[date, value]]} over [d0, d1]; KeyError for an unknown benchmark."""
    kind, _, code = key.partition(":")
    if kind == "index":
        pts = _rows(conn, """SELECT trade_date AS d, close AS v FROM idx.index_daily
                              WHERE index_code = %s AND close > 0 AND (%s::date IS NULL OR trade_date >= %s) AND (%s::date IS NULL OR trade_date <= %s)
                              ORDER BY trade_date""", (code, d0, d0, d1, d1))
        label = FEATURED.get(code, code)
    elif kind == "fund":
        pts = _rows(conn, """SELECT nav_date AS d, nav AS v FROM idx.fund_nav
                              WHERE fund_code = %s AND nav > 0 AND (%s::date IS NULL OR nav_date >= %s) AND (%s::date IS NULL OR nav_date <= %s)
                              ORDER BY nav_date""", (code, d0, d0, d1, d1))
        nm = _rows(conn, "SELECT max(name) AS name FROM idx.fund_nav WHERE fund_code = %s", (code,))
        label = (nm[0]["name"] if nm else None) or code
    else:
        raise KeyError(key)
    if not pts:
        raise KeyError(key)
    return {"key": key, "label": label, "kind": kind, "points": [[str(p["d"]), float(p["v"])] for p in pts]}


def _parse_date(s: str) -> date:
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unreadable date {s!r}")


def _parse_num(s: str) -> float:
    s = s.strip().replace("Rp", "").replace(" ", "")
    if s.count(",") and s.count("."):                      # 1.234,56 (id) or 1,234.56 (en): the last separator is the decimal
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif s.count(",") == 1 and len(s.split(",")[1]) != 3:
        s = s.replace(",", ".")
    else:
        s = s.replace(",", "")
    return float(s)


def import_fund_csv(conn: psycopg.Connection, code: str, name: str, path: str, source: str = "csv") -> int:
    """A fund's NAV history from a CSV with a date column and a NAV column (header names containing 'date'/'tanggal' and
    'nav'/'nab'/'price'/'harga'; else the first two columns). Replaces what was stored for the fund on those dates."""
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    if not rows:
        return 0
    head = [h.strip().lower() for h in rows[0]]
    di = next((i for i, h in enumerate(head) if "date" in h or "tanggal" in h), None)
    vi = next((i for i, h in enumerate(head) if any(k in h for k in ("nav", "nab", "price", "harga", "close"))), None)
    body = rows[1:] if di is not None or vi is not None else rows
    di, vi = di if di is not None else 0, vi if vi is not None else 1
    pts = {}
    for r in body:
        if len(r) <= max(di, vi) or not r[di].strip() or not r[vi].strip():
            continue
        pts[_parse_date(r[di])] = _parse_num(r[vi])
    with conn.cursor() as cur:
        cur.executemany("""INSERT INTO idx.fund_nav (fund_code, name, nav_date, nav, source) VALUES (%s, %s, %s, %s, %s)
                           ON CONFLICT (fund_code, nav_date) DO UPDATE SET nav = EXCLUDED.nav, name = EXCLUDED.name, source = EXCLUDED.source,
                               imported_at = now()""",
                        [(code, name, d, v, source) for d, v in sorted(pts.items()) if v > 0])
    conn.commit()
    return len(pts)
