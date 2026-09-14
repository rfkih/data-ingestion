"""Thesis card for one IDX stock — the operator's reading material (CLI now, app page later, nightly pack input).

Everything on the card is point-in-time as of ``as_of`` (default: last bar): fundamentals only from reports
published by then, valuation on that day's close and listed shares, flow from the daily summary, disclosures
from the archive. Markdown out; ASCII only so it renders in any console.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import psycopg

from .metrics import evaluate

MIN_ROE, MAX_DER = Decimal("0.10"), Decimal("1.5")
FIN = ("Financials", "Keuangan")


def _rows(conn: psycopg.Connection, sql: str, params: tuple, cols: list[str]) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    return [dict(zip(cols, (list(r.values()) if isinstance(r, dict) else r), strict=True)) for r in rows]


def _t(v: Decimal | float | None, unit: float = 1e12, d: int = 2) -> str:
    return "-" if v is None else f"{float(v) / unit:,.{d}f}"


def _pct(v: Decimal | float | None, d: int = 1) -> str:
    return "-" if v is None else f"{100 * float(v):+.{d}f}%"


def _x(v: Decimal | float | None, d: int = 2) -> str:
    return "-" if v is None else f"{float(v):.{d}f}x"


def build(conn: psycopg.Connection, code: str, as_of: date | None = None) -> str:
    code = code.upper()
    bar = _rows(conn, """
        SELECT b.trade_date, b.close, s.listed_shares, s.foreign_buy, s.foreign_sell, s.volume, s.value, f.value_60d_median,
               f.foreign_net_share_5d, f.foreign_net_share_20d, f.mcap_quintile
          FROM idx.bar b JOIN idx.daily_summary s USING (trade_date, code) LEFT JOIN idx.feature_daily f USING (trade_date, code)
         WHERE b.code = %s AND b.source IN ('idx', 'yahoo') AND (%s::date IS NULL OR b.trade_date <= %s) ORDER BY b.trade_date DESC LIMIT 1
        """, (code, as_of, as_of), ["d", "close", "shares", "fb", "fs", "vol", "value", "v60", "f5", "f20", "mcap_q"])
    if not bar:
        return f"# {code}\n\nno price data."
    b = bar[0]
    D = b["d"]
    listing = _rows(conn, "SELECT name, board, sector, subsector, listing_date, status FROM idx.listing WHERE code = %s", (code,),
                    ["name", "board", "sector", "subsector", "listing_date", "status"])
    L = listing[0] if listing else {}
    price = Decimal(b["close"])
    shares = Decimal(b["shares"] or 0)
    mcap = price * shares
    fund = _rows(conn, """
        SELECT period_end, period_label, published_at, months, revenue, net_profit, total_equity, total_assets, total_debt, cash, cfo,
               capex, dividends_paid, eps, bvps, roe, roa, der, net_margin, revenue_yoy, net_profit_yoy, currency, sector
          FROM idx.fundamental WHERE code = %s AND published_at <= %s ORDER BY period_end DESC, published_at DESC
        """, (code, D + timedelta(days=1)),
        ["period_end", "label", "pub", "months", "revenue", "net_profit", "equity", "assets", "debt", "cash", "cfo", "capex",
         "div_paid", "eps", "bvps", "roe", "roa", "der", "margin", "rev_yoy", "np_yoy", "currency", "sector"])
    annual = [f for f in fund if f["label"] == "TAHUNAN"]
    latest_annual = annual[0] if annual else None
    # trailing 12m dividends
    divs = _rows(conn, "SELECT ex_date, amount_per_share, source FROM idx.dividend WHERE code = %s AND ex_date <= %s ORDER BY ex_date DESC",
                 (code, D), ["ex_date", "dps", "source"])
    ttm_div = sum(Decimal(x["dps"]) for x in divs if x["ex_date"] > D - timedelta(days=365))
    events = _rows(conn, """
        SELECT published_at, kind, title FROM idx.announcement WHERE code = %s AND published_at <= %s
           AND kind NOT IN ('registry','ad_proof','other','ipo_proceeds','exploration','listing_change','prospectus')
         ORDER BY published_at DESC LIMIT 10""", (code, D + timedelta(days=1)), ["pub", "kind", "title"])
    actions = _rows(conn, "SELECT ex_date, kind, factor FROM idx.corporate_action WHERE code = %s ORDER BY ex_date DESC LIMIT 5",
                    (code,), ["ex_date", "kind", "factor"])
    flow = _rows(conn, """
        SELECT trade_date, foreign_buy - foreign_sell AS net, volume, close FROM idx.daily_summary
         WHERE code = %s AND trade_date <= %s ORDER BY trade_date DESC LIMIT 20""", (code, D), ["d", "net", "vol", "close"])

    latest_quarter = next((f for f in fund if f["label"] != "TAHUNAN"), None)
    m = evaluate(code, latest_annual, latest_quarter)
    cand = _rows(conn, """
        SELECT run_date, rank, selected, score FROM idx.candidate WHERE code = %s AND run_date <= %s ORDER BY run_date DESC LIMIT 1
        """, (code, D), ["run_date", "rank", "selected", "score"])
    pool_n = _rows(conn, "SELECT count(*) FROM idx.candidate WHERE run_date = %s", (cand[0]["run_date"],), ["n"])[0]["n"] if cand else 0
    # valuation
    pe = pb = None
    pe_ttm = (mcap / m["net_profit_ttm"]) if (m.get("net_profit_ttm") and m["net_profit_ttm"] > 0 and mcap > 0) else None
    if latest_annual and latest_annual["net_profit"] and mcap > 0:
        np_ = Decimal(latest_annual["net_profit"])
        pe = mcap / np_ if np_ > 0 else None
    if latest_annual and latest_annual["equity"] and mcap > 0:
        pb = mcap / Decimal(latest_annual["equity"])
    dy = ttm_div / price if price > 0 else None
    # quality gate on the latest audited report
    gate = []
    if latest_annual:
        fa = latest_annual
        is_fin = any(k in (fa["sector"] or L.get("sector") or "") for k in FIN)
        roe = Decimal(fa["roe"]) if fa["roe"] is not None else None
        np_ = Decimal(fa["net_profit"]) if fa["net_profit"] is not None else None
        prior_pos = (np_ is not None and fa["np_yoy"] is not None and (np_ / (1 + Decimal(fa["np_yoy"]))) > 0)
        cfo = Decimal(fa["cfo"]) if fa["cfo"] is not None else None
        der = Decimal(fa["der"]) if fa["der"] is not None else None
        gate = [("ROE >= 10%", roe is not None and roe >= MIN_ROE, _pct(roe)),
                ("net profit > 0", np_ is not None and np_ > 0, _t(np_)),
                ("prior-year profit > 0", prior_pos, _pct(fa["np_yoy"]) + " yoy"),
                ("operating cash flow > 0", cfo is not None and cfo > 0, _t(cfo)),
                ("debt/equity <= 1.5 (financials exempt)", is_fin or der is None or der <= MAX_DER, "financial" if is_fin else _x(der))]
    passed = bool(gate) and all(g[1] for g in gate)

    o = []
    o.append(f"# {code} - {L.get('name') or ''}")
    o.append(f"{L.get('sector') or '?'} / {L.get('subsector') or '?'} | board {L.get('board') or '?'} | listed {L.get('listing_date') or '?'} | as of {D}")
    o.append("")
    o.append("## Price & liquidity")
    o.append(f"- close Rp {float(price):,.0f} | market cap Rp {_t(mcap)} T | listed shares {float(shares)/1e9:,.2f} bn | mcap quintile {b['mcap_q'] or '-'}")
    o.append(f"- 60-day median traded value Rp {_t(b['v60'], 1e9, 1)} bn/day ({'liquid' if (b['v60'] or 0) >= 5e9 else 'ILLIQUID < 5 bn'})")
    o.append("")
    o.append("## Valuation (latest audited report, today's price)")
    o.append(f"- P/E {_x(pe, 1)} | P/B {_x(pb)} | dividend yield (trailing 12m, {len([x for x in divs if x['ex_date'] > D - timedelta(days=365)])} events) {_pct(dy)}")
    if latest_annual:
        o.append(f"- based on FY{latest_annual['period_end'].year} published {latest_annual['pub'].date()} ({latest_annual['currency']}{', converted' if latest_annual['currency'] != 'IDR' else ''})")
    if m.get("ttm_basis"):
        o.append(f"- trailing 12m ({m['ttm_basis']}): P/E {_x(pe_ttm, 1)} | net profit {_t(m.get('net_profit_ttm'), 1e12, 3)} T | revenue {_t(m.get('revenue_ttm'))} T")
    if cand:
        c = cand[0]
        o.append(f"- candidate list {c['run_date']}: rank {c['rank']} of {pool_n} in the loose-gate pool, {'SELECTED (top fifth)' if c['selected'] else 'not selected'}")
    elif m["gate_loose"]:
        o.append("- not in the latest candidate pool (illiquid, or E/P <= 0 on the audited year)")
    o.append("")
    o.append(f"## Book rule (loose gate: profit > 0, ROE >= 5%): {'PASS' if m['gate_loose'] else 'FAIL'}"
             + (f" | warnings: {', '.join(m['warnings'])}" if m["warnings"] else ""))
    o.append(f"## Strict quality gate: {'PASS' if passed else 'FAIL' if gate else 'no audited report yet'}")
    for name, ok, val in gate:
        o.append(f"- [{'x' if ok else ' '}] {name}: {val}")
    o.append("")
    o.append("## Fundamentals (Rp trillion; per share in Rp)")
    o.append("| period | published | revenue | yoy | net profit | yoy | ROE | margin | D/E | CFO | capex | div paid | EPS | BVPS |")
    o.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for f in fund[:10]:
        tag = f"FY{f['period_end'].year}" if f["label"] == "TAHUNAN" else f"{f['label']} {f['period_end'].year}"
        o.append(f"| {tag} | {f['pub'].date()} | {_t(f['revenue'])} | {_pct(f['rev_yoy'])} | {_t(f['net_profit'], 1e12, 3)} | {_pct(f['np_yoy'])} | "
                 f"{_pct(f['roe'])} | {_pct(f['margin'])} | {_x(f['der'])} | {_t(f['cfo'])} | {_t(f['capex'])} | {_t(f['div_paid'])} | "
                 f"{_t(f['eps'], 1, 1)} | {_t(f['bvps'], 1, 0)} |")
    o.append("")
    o.append("## Foreign flow (shares; share of volume)")
    net20 = sum(int(x["net"] or 0) for x in flow)
    vol20 = sum(int(x["vol"] or 0) for x in flow)
    o.append(f"- 5-day net share {_pct(b['f5'])} | 20-day net share {_pct(b['f20'])} | 20-day net {net20/1e6:+,.1f} M shares on {vol20/1e6:,.0f} M volume")
    o.append("- last 10 days: " + " ".join(f"{str(x['d'])[5:]}:{int(x['net'] or 0)/1e6:+.1f}M" for x in flow[:10]))
    o.append("")
    o.append("## Disclosures (last 10, classified)")
    for e in events:
        o.append(f"- {e['pub'].date()} [{e['kind']}] {e['title'][:90]}")
    if actions or divs:
        o.append("")
        o.append("## Corporate actions & dividends")
        for a in actions:
            o.append(f"- {a['ex_date']} {a['kind']} factor {float(a['factor']):.4f}")
        for x in divs[:5]:
            o.append(f"- {x['ex_date']} cash dividend Rp {float(x['dps']):,.1f}/share ({x['source']})")
    from . import annual
    plan = annual.render(conn, code)
    if plan:
        o += ["", plan]
    return "\n".join(o)
