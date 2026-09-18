"""Quality gates - Buffett's principles made measurable on the audited record (research/idx_buffett.py, 2026-09-18; spec §04).

Eight gates on the last five audited years published by ``as_of`` (point in time), plus the TTM figures from
:func:`metrics.fundamentals_asof`; the count of gates passed is the Quality score's input. Every gate carries the number it
was judged on, so a stock page can show the ingredients, not just the verdict.

  1 laba 5 th            net profit > 0 in every one of the five years
  2 ROE                  >= 12 % every year and >= 15 % on average
  3 EPS tumbuh           EPS (split-adjusted shares) latest FY >= first FY of the window
  4 utang kecil          non-financials: net debt <= 3 x net profit, or debt/equity <= 0.5
  5 kas nyata            non-financials: mean CFO/net profit >= 0.8 and free cash flow > 0 in >= 4 of 5 years
  6 tanpa dilusi+dividen shares (split-adjusted) +10 % at most over the window, and a cash dividend within 24 months
  7 TTM utuh             TTM profit >= 70 % of the latest FY
  8 harga wajar          P/E (TTM) <= 15 and owner-earnings yield >= 6 % (3-year mean FCF / market value; banks: TTM E/P)
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import psycopg

from .card import _rows
from .metrics import as_of_close

FIN = ("Financial", "Finance")
GATES = ("laba5", "roe", "eps", "utang", "kas", "dilusi_dividen", "ttm", "harga")
WINDOW = 5


def _f(v) -> float | None:
    return None if v is None else float(v)


def annual_rows(conn: psycopg.Connection, as_of: date, codes: list[str]) -> dict[str, list[dict[str, Any]]]:
    """Per code, the audited FY rows published by the ``as_of`` close, oldest first (one row per FY, latest publication)."""
    rows = _rows(conn, """
        SELECT DISTINCT ON (code, period_end) code, period_end, net_profit, revenue, total_equity, total_debt, cash, cfo, capex,
               dividends_paid, shares_out, roe, der, sector
          FROM idx.fundamental
         WHERE months = 12 AND period_label = 'TAHUNAN' AND published_at <= %s AND period_end >= %s AND code = ANY(%s)
         ORDER BY code, period_end, published_at DESC
        """, (as_of_close(as_of), date(as_of.year - WINDOW - 2, 1, 1), codes),
        ["code", "fy", "np", "rev", "eq", "debt", "cash", "cfo", "capex", "div", "sh", "roe", "der", "sector"])
    out: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        out.setdefault(r["code"], []).append(r)
    return out


def splits(conn: psycopg.Connection, codes: list[str]) -> dict[str, list[tuple[date, float]]]:
    rows = _rows(conn, "SELECT code, ex_date, factor FROM idx.corporate_action WHERE kind IN ('split', 'reverse_split') AND factor > 0 AND code = ANY(%s)",
                 (codes,), ["code", "ex", "factor"])
    out: dict[str, list[tuple[date, float]]] = {}
    for r in rows:
        out.setdefault(r["code"], []).append((r["ex"], float(r["factor"])))
    return out


def last_cash_dividend(conn: psycopg.Connection, as_of: date, codes: list[str]) -> dict[str, date]:
    rows = _rows(conn, "SELECT code, max(ex_date) AS d FROM idx.dividend WHERE kind = 'cash' AND ex_date > %s AND ex_date <= %s AND code = ANY(%s) GROUP BY code",
                 (as_of - timedelta(days=730), as_of, codes), ["code", "d"])
    return {r["code"]: r["d"] for r in rows}


def evaluate(code: str, rows: list[dict[str, Any]], ttm: dict[str, Any] | None, close: float | None, sector: str | None,
             split_list: list[tuple[date, float]] | None = None, dividend_recent: bool = False) -> dict[str, Any]:
    """Pure. Five audited FY rows (oldest first, may be fewer) -> gates, metrics, and the numbers behind them.
    Returns ``gates=None`` when fewer than five years or no shares/equity to price on."""
    out: dict[str, Any] = {"code": code, "years": len(rows), "gates": None, "passed": None, "metrics": {}}
    rows = [r for r in rows if r["np"] is not None][-WINDOW:]
    if len(rows) < WINDOW or not close:
        return out
    is_fin = any(k in (sector or rows[-1].get("sector") or "") for k in FIN)

    def sh_adj(r) -> float | None:
        if r["sh"] is None:
            return None
        k = 1.0
        for ex, fac in (split_list or []):
            if ex > r["fy"]:
                k /= fac
        return float(r["sh"]) * k

    sh_first, sh_now = sh_adj(rows[0]), sh_adj(rows[-1])
    eq_latest = _f((ttm or {}).get("equity_latest")) or _f(rows[-1]["eq"])
    if not sh_now or not eq_latest or eq_latest <= 0:
        return out
    np_ = [float(r["np"]) for r in rows]
    roe = [float(r["roe"]) if r["roe"] is not None else 0.0 for r in rows]
    cfo = [_f(r["cfo"]) for r in rows]
    capex = [float(r["capex"] or 0) for r in rows]
    fcf = [(c - x) if c is not None else None for c, x in zip(cfo, capex, strict=True)]
    cc = [c / n for c, n in zip(cfo, np_, strict=True) if c is not None and n > 0]
    mcap = close * sh_now
    np_ttm = _f((ttm or {}).get("net_profit_ttm"))
    eps_first = np_[0] / sh_first if sh_first else None
    eps_last = np_[-1] / sh_now
    net_debt = float(rows[-1]["debt"] or 0) - float(rows[-1]["cash"] or 0)
    der = _f(rows[-1]["der"])
    fcf3 = [v for v in fcf[-3:] if v is not None]
    oe = (sum(fcf3) / len(fcf3) / mcap) if (not is_fin and fcf3) else ((np_ttm or 0.0) / mcap)
    pe = (mcap / np_ttm) if (np_ttm and np_ttm > 0) else None
    pb = mcap / eq_latest
    dil = (sh_now / sh_first - 1) if sh_first else None
    roe_mean, roe_min = sum(roe) / len(roe), min(roe)
    cc_mean = (sum(cc) / len(cc)) if cc else None
    fcf_pos = sum(1 for v in fcf if v is not None and v > 0)
    gates = {
        "laba5": all(n > 0 for n in np_),
        "roe": roe_min >= 0.12 and roe_mean >= 0.15,
        "eps": eps_first is not None and eps_last >= eps_first,
        "utang": bool(is_fin or (np_[-1] > 0 and net_debt <= 3 * np_[-1]) or (der is not None and der <= 0.5)),
        "kas": bool(is_fin or (cc_mean is not None and cc_mean >= 0.8 and fcf_pos >= 4)),
        "dilusi_dividen": bool(dil is not None and dil <= 0.10 and dividend_recent),
        "ttm": bool(np_ttm is not None and np_ttm >= 0.7 * np_[-1]),
        "harga": bool(pe is not None and pe <= 15 and oe >= 0.06),
    }
    out.update({"gates": gates, "passed": sum(gates.values()), "is_financial": is_fin,
                "metrics": {"roe_mean": roe_mean, "roe_min": roe_min, "loss_years": sum(1 for n in np_ if n <= 0),
                            "eps_cagr": ((eps_last / eps_first) ** (1 / (WINDOW - 1)) - 1) if (eps_first and eps_first > 0 and eps_last > 0) else None,
                            "net_debt_np": (net_debt / np_[-1]) if np_[-1] else None, "cc_mean": cc_mean, "fcf_pos": fcf_pos, "dilution": dil,
                            "div_yield": (float(rows[-1]["div"]) / mcap) if rows[-1]["div"] is not None else None,
                            "pe_ttm": pe, "pb": pb, "oe_yield": oe, "mcap": mcap, "fy_last": rows[-1]["fy"].year}})
    return out


def evaluate_many(conn: psycopg.Connection, as_of: date, codes: list[str], ttm: dict[str, dict[str, Any]], closes: dict[str, float],
                  sectors: dict[str, str | None]) -> dict[str, dict[str, Any]]:
    """Batch: queries once, evaluates every code."""
    rows, sp, divs = annual_rows(conn, as_of, codes), splits(conn, codes), last_cash_dividend(conn, as_of, codes)
    return {c: evaluate(c, rows.get(c, []), ttm.get(c), closes.get(c), sectors.get(c), sp.get(c), c in divs) for c in codes}


def gate_table(res: dict[str, Any]) -> list[dict[str, Any]]:
    """The eight gates with their labels and the number each was judged on, for a card."""
    m, g = res.get("metrics") or {}, res.get("gates") or {}
    fmt = lambda v, p=0: "-" if v is None else f"{v * 100:.{p}f} %"  # noqa: E731
    items = [("laba5", "laba positif 5 tahun", f"{m.get('loss_years', '-')} tahun rugi"),
             ("roe", "ROE >= 12 % tiap tahun, >= 15 % rata-rata", f"rata {fmt(m.get('roe_mean'))}, min {fmt(m.get('roe_min'))}"),
             ("eps", "EPS naik selama 5 tahun", f"CAGR {fmt(m.get('eps_cagr'), 1)}"),
             ("utang", "net debt <= 3x laba atau D/E <= 0,5", "bank" if res.get("is_financial") else (f"{m['net_debt_np']:.1f}x laba" if m.get("net_debt_np") is not None else "-")),
             ("kas", "CFO/laba >= 0,8 dan FCF positif >= 4 dari 5", "bank" if res.get("is_financial") else f"CFO/laba {m.get('cc_mean') and f'{m['cc_mean']:.2f}'}, FCF+ {m.get('fcf_pos')}/5"),
             ("dilusi_dividen", "tanpa dilusi (<= +10 %) dan dividen tunai 24 bulan", f"saham {fmt(m.get('dilution'))}"),
             ("ttm", "laba TTM >= 70 % FY terakhir", "-"),
             ("harga", "P/E <= 15 dan owner-earnings yield >= 6 %", f"P/E {m['pe_ttm']:.1f}, OE {fmt(m.get('oe_yield'), 1)}" if m.get("pe_ttm") else f"OE {fmt(m.get('oe_yield'), 1)}")]
    return [{"key": k, "label": lbl, "value": val, "pass": bool(g.get(k)) if g else None} for k, lbl, val in items]


def to_decimal_free(d: Any) -> Any:
    """JSON-safe copy (Decimal/date -> float/str)."""
    if isinstance(d, dict):
        return {k: to_decimal_free(v) for k, v in d.items()}
    if isinstance(d, list):
        return [to_decimal_free(v) for v in d]
    if isinstance(d, Decimal):
        return float(d)
    if isinstance(d, date):
        return d.isoformat()
    return d
