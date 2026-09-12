"""Store parsed workbooks: ``idx.financial_fact`` (every fact, as reported) + one ``idx.fundamental`` row per
report (current-period metrics, prior-period comparatives as reported → YoY, ratios). Point-in-time key =
``published_at`` (IDX File_Modified). Shares outstanding come from the last Ringkasan Saham row at or before
publication; the close on that day is the yardstick for the EPS scale check (``_eps_reconcile``)."""
from __future__ import annotations

import logging
import math
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Any

import psycopg

from . import runlog
from .bronze import bronze_dir
from .fin_parse import extract_metrics, parse_workbook

logger = logging.getLogger(__name__)
JOB = "fin:parse"
POWERS = (1_000_000_000, 1_000_000, 1000)
EPS_LO, EPS_HI = Decimal("0.4"), Decimal("2.5")     # EPS x listed shares vs attributable profit: weighted vs listed shares, treasury stock
EP_MIN, EP_MAX = Decimal("0.0001"), Decimal(3)      # an earnings yield outside P/E 0.33..10,000 is a scale error, not a company


def _months(start: date | None, end: date | None) -> int | None:
    if not start or not end:
        return None
    return (end.year - start.year) * 12 + (end.month - start.month) + 1


def _market_at(conn: psycopg.Connection, code: str, when: date) -> tuple[int | None, Decimal | None]:
    """Listed shares and close from the last day-dump row at or before ``when``."""
    with conn.cursor() as cur:
        cur.execute("SELECT listed_shares, close FROM idx.daily_summary WHERE code = %s AND trade_date <= %s AND listed_shares > 0 "
                    "ORDER BY trade_date DESC LIMIT 1", (code, when))
        row = cur.fetchone()
    if row is None:
        return None, None
    shares, close = (row[0], row[1]) if isinstance(row, tuple) else (row["listed_shares"], row["close"])
    return (int(shares) if shares else None), (Decimal(close) if close else None)


def _div(a: Decimal | None, b: Decimal | None) -> Decimal | None:
    if a is None or b is None or b == 0:
        return None
    return a / b


def _yoy(cur: Decimal | None, pri: Decimal | None) -> Decimal | None:
    if cur is None or pri is None or pri == 0:
        return None
    return (cur - pri) / abs(pri)


def fx_table(conn: psycopg.Connection) -> Callable[[date], Decimal | None]:
    """Reporting-date IDR rates as the filers themselves reported them: median info-sheet rate per period end (primary
    source, no external FX feed). Falls back to the nearest period end within 45 days."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT period_end, percentile_cont(0.5) WITHIN GROUP (ORDER BY fx_rate) FROM idx.fundamental
             WHERE currency <> 'IDR' AND fx_rate > 1000 GROUP BY period_end""")
        rows = [list(r.values()) if isinstance(r, dict) else r for r in cur.fetchall()]
    table = {r[0]: Decimal(r[1]) for r in rows}
    table.update({k: v for k, v in FX_SEED.items() if k not in table})

    def lookup(d: date) -> Decimal | None:
        if d in table:
            return table[d]
        near = min(table, key=lambda k: abs((k - d).days), default=None)
        return table[near] if near is not None and abs((near - d).days) <= 45 else None

    return lookup


# Quarter-end BI rates as reported on IDX info sheets (median across USD filers), so a fresh database converts too.
FX_SEED = {date(y, m, dd): Decimal(v) for (y, m, dd), v in {
    (2020, 12, 31): 14105, (2021, 12, 31): 14269, (2022, 12, 31): 15731, (2023, 9, 30): 15526, (2023, 12, 31): 15416,
    (2024, 3, 31): 15853, (2024, 6, 30): 16421, (2024, 9, 30): 15138, (2024, 12, 31): 16162,
    (2025, 3, 31): 16588, (2025, 6, 30): 16233, (2025, 9, 30): 16680, (2025, 12, 31): 16782,
    (2026, 3, 31): 16993, (2026, 6, 30): 17856,
}.items()}


def _neighbour_assets(conn: psycopg.Connection, code: str, period_end: date) -> Decimal | None:
    """Yardstick for scale: the median total assets of the company's three closest other reports (earlier ones preferred),
    so one mis-scaled neighbour cannot drag the next report the wrong way."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT total_assets FROM idx.fundamental WHERE code = %s AND period_end <> %s AND total_assets > 0
             ORDER BY (period_end > %s), abs(period_end - %s) LIMIT 3""", (code, period_end, period_end, period_end))
        rows = cur.fetchall()
    vals = sorted(Decimal(next(iter(r.values())) if isinstance(r, dict) else r[0]) for r in rows)
    return vals[len(vals) // 2] if vals else None


LO, HI = Decimal("0.2"), Decimal("5")       # a real balance sheet does not move 200x-5000x between neighbouring reports


def _scale_fix(ta: Decimal | None, neighbour: Decimal | None, rounding_eff: int) -> int | None:
    """If total assets sit a clean power of 1000 away from the neighbouring report, the label lied: return the corrected
    rounding (None = leave as parsed). Real jumps (a reverse takeover at 97x) are not powers of 1000 and are left alone."""
    if not ta or not neighbour or ta <= 0 or neighbour <= 0:
        return None
    ratio = ta / neighbour
    for f in (1000, 1_000_000, 1_000_000_000):
        if LO < ratio / f < HI and rounding_eff % f == 0 and rounding_eff >= f:
            return rounding_eff // f                       # values were already scaled: undo the label
        if LO < (1 / ratio) / f < HI:
            return rounding_eff * f                        # values are in thousands/millions under a "full amount" label
    return None


def _pow1000(ratio: Decimal) -> Decimal | None:
    """The power of 1000 (1e-9 .. 1e9) a ratio sits at, within EPS_LO..EPS_HI of it; None if it sits nowhere clean."""
    if ratio is None or ratio <= 0:
        return None
    for f in (*POWERS, 1, *[Decimal(1) / p for p in POWERS]):
        if EPS_LO < ratio / Decimal(f) < EPS_HI:
            return Decimal(f)
    return None


def _plaus(ep: Decimal | None) -> float | None:
    """How far an earnings yield is from a typical 10 %, in decades: 0 at 10 %, 1 at 1 % or 100 %, 3 at 0.01 %."""
    if ep is None or ep == 0:
        return None
    return abs(math.log10(abs(float(ep))) + 1)


def _eps_reconcile(net: Decimal | None, eps: Decimal | None, shares: int | None, price: Decimal | None,
                   rounding_eff: int) -> tuple[int | None, Decimal | None, list[str]]:
    """EPS is per share and therefore never scaled by the workbook's rounding label, so ``net_profit ~ eps x shares`` is a
    scale check that needs no neighbouring report — it catches a company whose every report is off (PGEO) and a filer who
    scaled the per-share row too (BBNI FY2024). When the two sit a clean power of 1000 apart, the day's price says which
    side is wrong: the earnings yield that could belong to a company (P/E between 0.33 and 10,000) wins over the one that
    cannot; when both could, the one nearer 10 % wins if it is clearly nearer. Returns (rounding override to re-parse the
    whole report, corrected EPS, flags)."""
    if net is None or eps is None or not eps or not shares or net == 0:
        return None, eps, []
    ratio = abs(net / (eps * Decimal(shares)))
    f = _pow1000(ratio)
    if f is None:
        return None, eps, ["eps_mismatch"]
    if f == 1:
        return None, eps, []
    if not price or price <= 0:
        return None, eps, ["scale_mismatch"]
    ep_net, ep_eps = abs(net / (price * Decimal(shares))), abs(eps / price)
    ok_net, ok_eps = EP_MIN <= ep_net <= EP_MAX, EP_MIN <= ep_eps <= EP_MAX
    if ok_net == ok_eps:                                    # both possible (or neither): the one nearer 10 % wins, if clearly
        pn, pe = _plaus(ep_net), _plaus(ep_eps)
        if not ok_net or pn is None or pe is None or abs(pn - pe) < 1.5:
            return None, eps, ["scale_mismatch"]
        ok_net = pn < pe
    if ok_net:                                              # the EPS is off by f
        return None, eps * f, ["eps_rescaled"]
    if f > 1:                                               # the report is f x too big: only undoable when a label was applied
        if rounding_eff % int(f) == 0 and rounding_eff >= int(f):
            return rounding_eff // int(f), eps, ["report_rescaled"]
        return None, eps, ["scale_mismatch"]
    return rounding_eff * int(1 / f), eps, ["report_rescaled"]


def store_report(conn: psycopg.Connection, report: dict[str, Any], fx_fallback: Callable[[date], Decimal | None] | None = None) -> dict[str, Any]:
    """Parse + store one report (dict with id, code, fiscal_year, period, published_at, bronze path)."""
    path = bronze_dir().parent / report["path"]
    p = parse_workbook(path, fx_fallback)
    m = extract_metrics(p)
    pe = p.info.get("period_end")
    fix = _scale_fix(m["current"].get("total_assets"), _neighbour_assets(conn, report["code"], pe) if pe else None, p.rounding_eff)
    if fix is not None:
        p = parse_workbook(path, fx_fallback, rounding_override=fix)
        m = extract_metrics(p)
    pub_date = report["published_at"].date()
    shares, price = _market_at(conn, report["code"], pub_date)
    override, eps, flags = _eps_reconcile(m["current"].get("net_profit"), m["current"].get("eps"), shares, price, p.rounding_eff)
    if override is not None and override != p.rounding_eff:
        p = parse_workbook(path, fx_fallback, rounding_override=override)
        m = extract_metrics(p)
        eps = m["current"].get("eps")
    cur, pri = m["current"], m["prior"]
    info = p.info
    period_end = info.get("period_end") or date(report["fiscal_year"], {"TW1": 3, "TW2": 6, "TW3": 9, "TAHUNAN": 12}[report["period"]], 30)
    period_start = info.get("period_start") or date(report["fiscal_year"], 1, 1)
    months = _months(period_start, period_end) or {"TW1": 3, "TW2": 6, "TW3": 9, "TAHUNAN": 12}[report["period"]]
    ann = Decimal(12) / Decimal(months)
    net = cur.get("net_profit")
    eq = cur.get("equity_parent") or cur.get("total_equity")
    rev = cur.get("revenue")
    row = {
        "code": report["code"], "period_end": period_end, "published_at": report["published_at"], "report_id": report["id"],
        "period_start": period_start, "months": months, "period_label": report["period"],
        "revenue": rev, "gross_profit": cur.get("gross_profit"), "operating_profit": None, "pretax_profit": cur.get("pretax_profit"),
        "net_profit": net, "total_assets": cur.get("total_assets"), "total_liabilities": cur.get("total_liabilities"),
        "total_equity": eq, "cash": cur.get("cash"), "total_debt": cur.get("total_debt"),
        "current_assets": cur.get("current_assets"), "current_liabilities": cur.get("current_liabilities"),
        "cfo": cur.get("cfo"), "capex": cur.get("capex"), "dividends_paid": cur.get("dividends_paid"),
        "shares_out": shares, "eps": eps,
        "bvps": _div(eq, Decimal(shares)) if shares else None,
        "roe": _div(net * ann if net is not None else None, eq),
        "roa": _div(net * ann if net is not None else None, cur.get("total_assets")),
        "der": _div(cur.get("total_debt"), eq),
        "net_margin": _div(net, rev),
        "revenue_yoy": _yoy(rev, pri.get("revenue")), "net_profit_yoy": _yoy(net, pri.get("net_profit")),
        "net_profit_prior": pri.get("net_profit"), "revenue_prior": pri.get("revenue"), "cfo_prior": pri.get("cfo"),
        "sector": info.get("sector"), "subsector": info.get("subsector"), "rounding": p.rounding_eff, "facts_n": len(p.facts),
        "currency": p.currency or "IDR", "fx_rate": p.fx_rate if (p.currency and p.currency != "IDR") else None,
        "flags": flags,
    }
    facts = [{"report_id": report["id"], "concept": f.concept[:200], "context_ref": f"{f.context}|{f.sheet}|r{f.row}",
              "period_start": period_start if "Duration" in f.context else None,
              "period_end": period_end if f.context.startswith("Current") else info.get("prior_period_end"),
              "value": f.value, "unit": "IDR" if "per share" not in f.concept.lower() else "IDR/share",
              "decimals": len(str(p.rounding_eff)) - 1} for f in p.facts]
    with conn.cursor() as cur_:
        cur_.execute("DELETE FROM idx.financial_fact WHERE report_id = %s", (report["id"],))
        for i in range(0, len(facts), 2000):
            cur_.executemany(
                """
                INSERT INTO idx.financial_fact (report_id, concept, context_ref, period_start, period_end, value, unit, decimals)
                VALUES (%(report_id)s, %(concept)s, %(context_ref)s, %(period_start)s, %(period_end)s, %(value)s, %(unit)s, %(decimals)s)
                ON CONFLICT (report_id, concept, context_ref) DO UPDATE SET value = EXCLUDED.value
                """, facts[i:i + 2000])
        cur_.execute(
            """
            INSERT INTO idx.fundamental (code, period_end, published_at, report_id, period_start, months, period_label, revenue,
                gross_profit, operating_profit, pretax_profit, net_profit, total_assets, total_liabilities, total_equity, cash,
                total_debt, current_assets, current_liabilities, cfo, capex, dividends_paid, shares_out, eps, bvps, roe, roa, der,
                net_margin, revenue_yoy, net_profit_yoy, net_profit_prior, revenue_prior, cfo_prior, sector, subsector, rounding,
                facts_n, currency, fx_rate, flags)
            VALUES (%(code)s, %(period_end)s, %(published_at)s, %(report_id)s, %(period_start)s, %(months)s, %(period_label)s,
                %(revenue)s, %(gross_profit)s, %(operating_profit)s, %(pretax_profit)s, %(net_profit)s, %(total_assets)s,
                %(total_liabilities)s, %(total_equity)s, %(cash)s, %(total_debt)s, %(current_assets)s, %(current_liabilities)s,
                %(cfo)s, %(capex)s, %(dividends_paid)s, %(shares_out)s, %(eps)s, %(bvps)s, %(roe)s, %(roa)s, %(der)s,
                %(net_margin)s, %(revenue_yoy)s, %(net_profit_yoy)s, %(net_profit_prior)s, %(revenue_prior)s, %(cfo_prior)s,
                %(sector)s, %(subsector)s, %(rounding)s, %(facts_n)s, %(currency)s, %(fx_rate)s, %(flags)s)
            ON CONFLICT (code, period_end, published_at) DO UPDATE SET
                report_id = EXCLUDED.report_id, period_start = EXCLUDED.period_start, months = EXCLUDED.months,
                period_label = EXCLUDED.period_label, revenue = EXCLUDED.revenue, gross_profit = EXCLUDED.gross_profit,
                pretax_profit = EXCLUDED.pretax_profit, net_profit = EXCLUDED.net_profit, total_assets = EXCLUDED.total_assets,
                total_liabilities = EXCLUDED.total_liabilities, total_equity = EXCLUDED.total_equity, cash = EXCLUDED.cash,
                total_debt = EXCLUDED.total_debt, current_assets = EXCLUDED.current_assets,
                current_liabilities = EXCLUDED.current_liabilities, cfo = EXCLUDED.cfo, capex = EXCLUDED.capex,
                dividends_paid = EXCLUDED.dividends_paid, shares_out = EXCLUDED.shares_out, eps = EXCLUDED.eps, bvps = EXCLUDED.bvps,
                roe = EXCLUDED.roe, roa = EXCLUDED.roa, der = EXCLUDED.der, net_margin = EXCLUDED.net_margin,
                revenue_yoy = EXCLUDED.revenue_yoy, net_profit_yoy = EXCLUDED.net_profit_yoy,
                net_profit_prior = EXCLUDED.net_profit_prior, revenue_prior = EXCLUDED.revenue_prior, cfo_prior = EXCLUDED.cfo_prior,
                sector = EXCLUDED.sector, subsector = EXCLUDED.subsector, rounding = EXCLUDED.rounding, facts_n = EXCLUDED.facts_n,
                currency = EXCLUDED.currency, fx_rate = EXCLUDED.fx_rate, flags = EXCLUDED.flags
            """, row)
        cur_.execute("UPDATE idx.financial_report SET parse_status = 'parsed', parsed_at = now() WHERE id = %s", (report["id"],))
        if info.get("sector"):
            cur_.execute("UPDATE idx.listing SET sector = COALESCE(sector, %s), subsector = COALESCE(subsector, %s) WHERE code = %s",
                         (info.get("sector"), info.get("subsector"), report["code"]))
    conn.commit()
    return {"facts": len(p.facts), "net_profit": net, "revenue": rev, "period_end": period_end, "warnings": p.warnings,
            "rounding_eff": p.rounding_eff, "fx_source": p.fx_source, "flags": flags}


def run(conn: psycopg.Connection, *, codes: list[str] | None = None, limit: int | None = None,
        reparse: bool = False) -> runlog.RunResult:
    r = runlog.RunResult(JOB, "all" if not codes else ",".join(codes[:3]))
    run_id = runlog.start(conn, JOB, r.run_key)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT fr.id, fr.code, fr.fiscal_year, fr.period, fr.published_at, b.path
              FROM idx.financial_report fr JOIN idx.bronze_index b ON b.id = fr.bronze_id
             WHERE fr.parse_status = ANY(%s) AND (%s::text[] IS NULL OR fr.code = ANY(%s))
             ORDER BY fr.published_at
            """, (["downloaded", "parsed"] if reparse else ["downloaded"], codes, codes))
        rows = cur.fetchall()
    cols = ["id", "code", "fiscal_year", "period", "published_at", "path"]
    todo = [x if isinstance(x, dict) else dict(zip(cols, x, strict=True)) for x in rows]
    if limit:
        todo = todo[:limit]
    r.rows_in = len(todo)
    ok = bad = 0
    fx = fx_table(conn)
    overrides: dict[str, int] = {}
    flag_counts: dict[str, int] = {}
    for rep in todo:
        try:
            res = store_report(conn, rep, fx)
            ok += 1
            for w in res.get("warnings") or []:
                key = w.split(":")[0]
                overrides[key] = overrides.get(key, 0) + 1
            for fl in res.get("flags") or []:
                flag_counts[fl] = flag_counts.get(fl, 0) + 1
        except Exception as e:
            conn.rollback()
            bad += 1
            with conn.cursor() as cur:
                cur.execute("UPDATE idx.financial_report SET parse_status = 'failed' WHERE id = %s", (rep["id"],))
            conn.commit()
            if bad <= 20:
                r.warn(f"{rep['code']} {rep['fiscal_year']} {rep['period']}: {type(e).__name__}: {str(e)[:120]}")
        if (ok + bad) % 200 == 0:
            logger.info("idx fin parse %d/%d ok=%d bad=%d", ok + bad, len(todo), ok, bad)
    r.rows_out = ok
    r.detail["failed"] = bad
    if overrides:
        r.detail["parser_warnings"] = overrides
    if flag_counts:
        r.detail["flags"] = flag_counts
    if bad and not ok:
        r.status = "failed"
    elif bad:
        r.status = "partial"
    runlog.finish(conn, run_id, r)
    return r
