"""Point-in-time fundamental metrics per code as of a date — shared by the candidate list, the thesis card and
the nightly pack. Trailing-twelve-month figures combine the latest audited year with the latest quarterly:
TTM = FY(prev) + YTD(current) - YTD(prior year, same quarter), the prior YTD being the comparative the same
report carries. Since migration 0009 the comparative is stored as reported (``net_profit_prior`` /
``revenue_prior``); rows parsed before that fall back to inverting the YoY ratio, which is only possible when
the sign of the comparative is certain (see ``prior_from_yoy``)."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import psycopg

LOOSE_ROE, STRICT_ROE, MAX_DER = Decimal("0.05"), Decimal("0.10"), Decimal("1.5")
FIN = ("Financials", "Keuangan")
MAX_AGE_DAYS = 16 * 30
LIQ = Decimal(5_000_000_000)
WIB = ZoneInfo("Asia/Jakarta")
CLOSE = time(16, 0)
COLS = ["code", "period_end", "label", "pub", "months", "revenue", "net_profit", "equity", "assets", "debt", "cash", "cfo",
        "capex", "div_paid", "eps", "roe", "der", "np_yoy", "rev_yoy", "sector", "currency", "np_prior", "rev_prior", "flags"]


def _rows(conn: psycopg.Connection, sql: str, params: tuple, cols: list[str]) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    return [dict(zip(cols, (list(r.values()) if isinstance(r, dict) else r), strict=True)) for r in rows]


def _d(v) -> Decimal | None:
    return None if v is None else Decimal(v)


def as_of_close(as_of: date) -> datetime:
    """Information cutoff for a run "as of the ``as_of`` close": a report counts once published by 16:00 WIB that day.
    The same cutoff serves the live desk (whose list is worked the next session) and the backtest (fills at the close)."""
    return datetime.combine(as_of, CLOSE, tzinfo=WIB)


def prior_from_yoy(cur: Decimal | None, yoy: Decimal | None) -> Decimal | None:
    """The comparative implied by a value and its YoY ratio ``(cur - prior) / |prior|`` — only where the inversion is
    unambiguous. A profit with yoy <= 1 had a positive comparative (cur / (1 + yoy)); a loss with -1 <= yoy < 1 had a
    negative one (cur / (1 - yoy)). A profit with yoy > 1 may be strong growth or a turnaround from a loss, and a loss
    with yoy < -1 may follow a profit or a smaller loss: the ratio cannot tell, so the answer is None and the caller
    must use the stored comparative."""
    if cur is None or yoy is None:
        return None
    if cur > 0 and -1 < yoy <= 1:
        return cur / (1 + yoy)
    if cur < 0 and -1 <= yoy < 1:
        return cur / (1 - yoy)
    return None


def comparative(r: dict[str, Any], key: str) -> Decimal | None:
    """Prior-period value for ``net_profit`` or ``revenue``: the stored comparative, else the YoY inversion."""
    stored = r.get("np_prior" if key == "net_profit" else "rev_prior")
    if stored is not None:
        return _d(stored)
    return prior_from_yoy(_d(r.get(key)), _d(r.get("np_yoy" if key == "net_profit" else "rev_yoy")))


def universe_codes(conn: psycopg.Connection, min_value: Decimal = LIQ) -> list[str]:
    """Codes worth keeping fundamentals/dividends current for: liquid at any point in the last 120 days (60d median
    value >= min_value) + anything selected as a candidate in the last 400 days + the watchlist."""
    rows = _rows(conn, """
        SELECT code FROM idx.feature_daily WHERE trade_date >= current_date - 120 AND value_60d_median >= %s
        UNION SELECT code FROM idx.candidate WHERE selected AND run_date >= current_date - 400
        UNION SELECT code FROM idx.watchlist
        """, (min_value,), ["code"])
    return sorted({r["code"] for r in rows})


def fundamentals_asof(conn: psycopg.Connection, as_of: date, codes: list[str] | None = None) -> dict[str, dict[str, Any]]:
    """Per code: latest audited row and latest quarterly row published by the ``as_of`` close -> evaluate()."""
    rows = _rows(conn, """
        SELECT code, period_end, period_label, published_at, months, revenue, net_profit, total_equity, total_assets, total_debt,
               cash, cfo, capex, dividends_paid, eps, roe, der, net_profit_yoy, revenue_yoy, sector, currency,
               net_profit_prior, revenue_prior, flags
          FROM idx.fundamental
         WHERE published_at <= %s AND period_end >= %s AND (%s::text[] IS NULL OR code = ANY(%s))
         ORDER BY code, period_end DESC, published_at DESC
        """, (as_of_close(as_of), as_of - timedelta(days=MAX_AGE_DAYS), codes, codes), COLS)
    latest: dict[str, dict[str, Any]] = {}
    for r in rows:
        o = latest.setdefault(r["code"], {"annual": None, "quarter": None})
        if r["label"] == "TAHUNAN" and o["annual"] is None:
            o["annual"] = r
        elif r["label"] != "TAHUNAN" and o["quarter"] is None:
            o["quarter"] = r
    return {code: evaluate(code, o["annual"], o["quarter"]) for code, o in latest.items()}


def evaluate(code: str, a: dict[str, Any] | None, q: dict[str, Any] | None) -> dict[str, Any]:
    """Pure: latest audited row ``a`` + latest quarterly row ``q`` (COLS keys; either may be None) -> metrics, TTM,
    gates and thesis-break warnings. Gates are evaluated on the audited report (the rule the backtest used)."""
    m: dict[str, Any] = {"code": code, "annual_period": a["period_end"] if a else None, "annual_pub": a["pub"].date() if a else None,
                         "quarter_period": q["period_end"] if q else None, "quarter_pub": q["pub"].date() if q else None,
                         "sector": (a or q)["sector"] if (a or q) else None}
    if a and q and q["period_end"] > a["period_end"]:
        for k in ("net_profit", "revenue"):
            fy, ytd, prior = _d(a[k]), _d(q[k]), comparative(q, k)
            m[f"{k}_ttm"] = (fy + ytd - prior) if (fy is not None and ytd is not None and prior is not None) else None
        m["cfo_ttm"] = _d(a["cfo"])                       # no prior-YTD comparative stored for cash flow
        m["equity_latest"] = _d(q["equity"]) if q["equity"] is not None else _d(a["equity"])
        m["debt_latest"] = _d(q["debt"]) if q["debt"] is not None else _d(a["debt"])
        m["ttm_basis"] = f"FY{a['period_end'].year} + {q['label']} {q['period_end'].year} YTD"
    elif a:
        m["net_profit_ttm"], m["revenue_ttm"], m["cfo_ttm"] = _d(a["net_profit"]), _d(a["revenue"]), _d(a["cfo"])
        m["equity_latest"], m["debt_latest"] = _d(a["equity"]), _d(a["debt"])
        m["ttm_basis"] = f"FY{a['period_end'].year}"
    else:
        m["net_profit_ttm"] = m["revenue_ttm"] = m["cfo_ttm"] = None
        m["equity_latest"] = _d(q["equity"]) if q else None
        m["debt_latest"] = _d(q["debt"]) if q else None
        m["ttm_basis"] = f"{q['label']} {q['period_end'].year} only" if q else None
    if a:
        np_, eq, roe, cfo, der = _d(a["net_profit"]), _d(a["equity"]), _d(a["roe"]), _d(a["cfo"]), _d(a["der"])
        prior = comparative(a, "net_profit")
        is_fin = any(k in (a["sector"] or "") for k in FIN)
        checks = [("roe<10%", roe is not None and roe >= STRICT_ROE), ("loss", np_ is not None and np_ > 0),
                  ("prior_year_unknown" if prior is None else "prior_year_loss", prior is not None and prior > 0),
                  ("cfo<=0", cfo is not None and cfo > 0), ("der>1.5", is_fin or der is None or der <= MAX_DER)]
        m.update({"roe": roe, "der": der, "cfo": cfo, "net_profit": np_, "equity": eq, "np_yoy": _d(a["np_yoy"]),
                  "rev_yoy": _d(a["rev_yoy"]), "net_profit_prior": prior, "is_financial": is_fin,
                  "gate_loose": bool(np_ is not None and np_ > 0 and roe is not None and roe >= LOOSE_ROE),
                  "gate_strict": all(ok for _, ok in checks), "strict_fails": [n for n, ok in checks if not ok]})
    else:
        m.update({"gate_loose": False, "gate_strict": False, "strict_fails": ["no_audited_report"], "is_financial": False,
                  "roe": None, "der": None, "cfo": None, "net_profit": None, "equity": None, "np_yoy": None, "rev_yoy": None,
                  "net_profit_prior": None})
    warn = []
    if m.get("net_profit_ttm") is not None and m["net_profit_ttm"] <= 0:
        warn.append("ttm_loss")
    if q and q["net_profit"] is not None and _d(q["net_profit"]) < 0:
        warn.append("latest_quarter_ytd_loss")
    if q and q["np_yoy"] is not None and _d(q["np_yoy"]) < Decimal("-0.5"):
        warn.append("ytd_profit_down_>50%")
    if any("scale_mismatch" in (r.get("flags") or ()) for r in (a, q) if r):
        warn.append("scale_mismatch")
    m["warnings"] = warn
    return m
