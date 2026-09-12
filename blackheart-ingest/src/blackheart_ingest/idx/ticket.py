"""Rebalance ticket — the trade list the operator works at the broker, built from the candidate list and the book.

``rebalance``: hold the selected candidates equal-weight; sell what is no longer selected, trim/add beyond the band,
buy new entrants, sized in round lots at a tick-snapped limit inside IDX's auto-rejection band, buys capped by cash plus
expected sale proceeds. ``exits``: only sells, for held names whose newest report breaks the book rule or whose latest pack
answer says sell — the mid-year thesis-break check. Each line carries the reasons and every flag the operator should see
(strict-gate fails, TTM warnings, the pack's stance/veto). Fills are captured back into ``idx.fill`` line by line.

IDX market rules encoded here (verify against Peraturan II-A when they change): round lot 100 shares; price fractions
Rp 1 / 2 / 5 / 10 / 25 for < 200 / < 500 / < 2,000 / < 5,000 / ≥ 5,000; symmetric auto-rejection 35 % / 25 % / 20 % for
Rp 50-200 / 200-5,000 / > 5,000.
"""
from __future__ import annotations

import json
import logging
import math
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import psycopg
import psycopg.types.json

from . import book as bk
from .card import _pct, _rows
from .metrics import fundamentals_asof

logger = logging.getLogger(__name__)
LOT = 100
BAND = Decimal("0.01")              # ignore weight differences inside ±1 % of NAV
MIN_TRADE = Decimal(5_000_000)      # and trades below Rp 5 M
CASH_RESERVE = Decimal("0.01")      # keep 1 % of NAV in cash for fees/rounding
TICKS = ((200, 1), (500, 2), (2000, 5), (5000, 10), (10**12, 25))
BANDS = ((200, Decimal("0.35")), (5000, Decimal("0.25")), (10**12, Decimal("0.20")))


# ---------------------------------------------------------------------------
# pure: market rules and the plan
# ---------------------------------------------------------------------------
def tick_size(price: Decimal) -> int:
    return next(t for lim, t in TICKS if price < lim)


def snap(price: Decimal, side: str) -> Decimal:
    """Snap to the fraction: buys round up (to get filled), sells round down."""
    t = tick_size(price)
    q = (price / t)
    n = math.ceil(q) if side == "buy" else math.floor(q)
    return Decimal(n * t)


def reject_band(prev_close: Decimal) -> tuple[Decimal, Decimal]:
    pct = next(p for lim, p in BANDS if prev_close <= lim)
    lo = max(Decimal(50), (prev_close * (1 - pct)).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    hi = (prev_close * (1 + pct)).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return snap(lo, "buy"), snap(hi, "sell")


def limit_price(ref_close: Decimal, side: str, ticks_through: int = 1) -> Decimal:
    """Reference close ± a tick, snapped, clamped inside the auto-rejection band around that close."""
    t = tick_size(ref_close)
    raw = ref_close + t * ticks_through if side == "buy" else ref_close - t * ticks_through
    lo, hi = reject_band(ref_close)
    return min(max(snap(raw, side), lo), hi)


def plan(targets: list[str], held: dict[str, dict[str, Any]], prices: dict[str, Decimal], cash: Decimal, *, book: dict[str, Any],
         band: Decimal = BAND, min_trade: Decimal = MIN_TRADE, reserve: Decimal = CASH_RESERVE, mode: str = "rebalance",
         exits: dict[str, str] | None = None) -> dict[str, Any]:
    """Pure. held = {code: {lots, avg_price}}; prices = last close per code. Returns lines + sizing context."""
    fee_buy, fee_sell = Decimal(book["fee_buy_pct"]) / 100, Decimal(book["fee_sell_pct"]) / 100
    value = {c: Decimal(h["lots"]) * LOT * prices[c] for c, h in held.items() if c in prices}
    nav = cash + sum(value.values(), Decimal(0))
    lines: list[dict[str, Any]] = []
    if mode == "exits":
        for c, why in (exits or {}).items():
            if c in held and c in prices:
                lp = limit_price(prices[c], "sell")
                lines.append({"code": c, "side": "sell", "lots": Decimal(held[c]["lots"]), "limit_price": lp, "ref_close": prices[c],
                              "notional": Decimal(held[c]["lots"]) * LOT * lp, "weight_now": value[c] / nav if nav else None,
                              "weight_target": Decimal(0), "reason": why, "flags": []})
        return {"nav": nav, "cash": cash, "n_targets": len(held) - len(lines), "lines": lines, "cash_after": cash + sum(
            ln["notional"] * (1 - fee_sell) for ln in lines)}
    n = len(targets)
    target_value = ((nav * (1 - reserve)) / n) if n else Decimal(0)
    w_target = (target_value / nav) if nav else Decimal(0)
    # sells: no longer a target -> exit; overweight beyond the band -> trim
    for c, h in held.items():
        if c not in prices:
            continue
        v, lots = value[c], Decimal(h["lots"])
        if c not in targets:
            lp = limit_price(prices[c], "sell")
            lines.append({"code": c, "side": "sell", "lots": lots, "limit_price": lp, "ref_close": prices[c], "notional": lots * LOT * lp,
                          "weight_now": v / nav, "weight_target": Decimal(0), "reason": "no longer selected", "flags": []})
        elif v - target_value > band * nav and v - target_value >= min_trade:
            lp = limit_price(prices[c], "sell")
            trim = Decimal(math.ceil((v - target_value) / (lp * LOT)))
            if 0 < trim < lots:
                lines.append({"code": c, "side": "sell", "lots": trim, "limit_price": lp, "ref_close": prices[c], "notional": trim * LOT * lp,
                              "weight_now": v / nav, "weight_target": w_target, "reason": f"trim {_pct(v / nav)} -> {_pct(w_target)}", "flags": []})
    proceeds = sum(ln["notional"] * (1 - fee_sell) for ln in lines)
    budget = cash + proceeds - nav * reserve
    # buys: new entrants and underweights
    buys: list[dict[str, Any]] = []
    for c in targets:
        if c not in prices:
            buys.append({"code": c, "side": "buy", "lots": Decimal(0), "limit_price": Decimal(0), "ref_close": None, "notional": Decimal(0),
                         "weight_now": Decimal(0), "weight_target": w_target, "reason": "no price", "flags": ["no_price"]})
            continue
        v = value.get(c, Decimal(0))
        gap = target_value - v
        if gap <= band * nav or gap < min_trade:
            continue
        lp = limit_price(prices[c], "buy")
        lots = Decimal(int((gap / (1 + fee_buy)) // (lp * LOT)))
        if lots <= 0:
            continue
        buys.append({"code": c, "side": "buy", "lots": lots, "limit_price": lp, "ref_close": prices[c], "notional": lots * LOT * lp,
                     "weight_now": v / nav if nav else Decimal(0), "weight_target": w_target,
                     "reason": "new entrant" if c not in held else f"add {_pct(v / nav)} -> {_pct(w_target)}", "flags": []})
    need = sum(b["notional"] * (1 + fee_buy) for b in buys)
    if need > budget > 0:
        scale = budget / need
        for b in buys:
            b["lots"] = Decimal(int(b["lots"] * scale))
            b["notional"] = b["lots"] * LOT * b["limit_price"]
            b["flags"].append("cash-limited")
        buys = [b for b in buys if b["lots"] > 0 or "no_price" in b["flags"]]
    lines += buys
    cash_after = cash + proceeds - sum(b["notional"] * (1 + fee_buy) for b in buys)
    return {"nav": nav, "cash": cash, "n_targets": n, "target_value": target_value, "lines": lines, "cash_after": cash_after}


# ---------------------------------------------------------------------------
# build from the database
# ---------------------------------------------------------------------------
def build(conn: psycopg.Connection, book: str, *, mode: str = "rebalance", run_date: date | None = None, max_names: int | None = None,
          band: Decimal = BAND, min_trade: Decimal = MIN_TRADE) -> dict[str, Any]:
    b = bk.get_book(conn, book)
    s = bk.snapshot(conn, book)
    held = {p["code"]: {"lots": p["lots"], "avg_price": p["avg_price"]} for p in s["positions"]}
    D = _rows(conn, "SELECT max(run_date) FROM idx.candidate WHERE (%s::date IS NULL OR run_date <= %s)", (run_date, run_date), ["d"])[0]["d"]
    if D is None:
        raise ValueError("no candidate run; run `idx candidates` first")
    cands = _rows(conn, "SELECT code, rank, selected, gate_strict, strict_fails, warnings FROM idx.candidate WHERE run_date = %s ORDER BY rank", (D,),
                  ["code", "rank", "selected", "gate_strict", "strict_fails", "warnings"])
    cmap = {c["code"]: c for c in cands}
    targets = [c["code"] for c in cands if c["selected"]]
    if max_names:
        targets = targets[:max_names]
    codes = sorted(set(targets) | set(held))
    px = {p["code"]: Decimal(p["close"]) for p in _rows(conn, """
        SELECT DISTINCT ON (code) code, close FROM idx.bar WHERE code = ANY(%s) AND source = 'idx' AND trade_date <= %s
         ORDER BY code, trade_date DESC""", (codes, D), ["code", "close"])}
    answers = {a["code"]: a for a in _rows(conn, """
        SELECT DISTINCT ON (code) code, doc_id AS pack_date, event_type AS stance, veto, rationale FROM idx.sentiment_score
         WHERE doc_type = 'pack' AND code = ANY(%s) ORDER BY code, scored_at DESC""", (codes,), ["code", "pack_date", "stance", "veto", "rationale"])}
    exits: dict[str, str] = {}
    if mode == "exits" and held:
        fund = fundamentals_asof(conn, D, list(held))
        for c in held:
            m = fund.get(c)
            a = answers.get(c)
            if m and not m["gate_loose"]:
                exits[c] = "newest report breaks the book rule: " + ", ".join(m["strict_fails"])
            elif a and a["stance"] == "sell":
                exits[c] = f"pack {a['pack_date']}: sell - {(a['rationale'] or '')[:100]}"
    res = plan(targets, held, px, Decimal(b["cash"]), book=b, band=band, min_trade=min_trade, mode=mode, exits=exits)
    for line in res["lines"]:
        c = cmap.get(line["code"])
        a = answers.get(line["code"])
        if c:
            line["reason"] += f" (rank {c['rank']})"
            if line["side"] == "buy":
                if not c["gate_strict"]:
                    line["flags"] += [f"strict:{f}" for f in (c["strict_fails"] or [])]
                line["flags"] += [f"warn:{w}" for w in (c["warnings"] or [])]
        if a and a["stance"]:
            line["flags"].append(f"pack:{a['stance']}" + (" VETO" if a["veto"] else ""))
    res.update({"book": book, "mode": mode, "run_date": D, "ticket_date": D, "targets": targets, "held": held, "prices": px})
    return res


def store(conn: psycopg.Connection, res: dict[str, Any], notes: str | None = None) -> int:
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO idx.ticket (book, ticket_date, run_date, mode, nav, cash, n_targets, params, notes)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                    (res["book"], res["ticket_date"], res["run_date"], res["mode"], res["nav"], res["cash"], res["n_targets"],
                     psycopg.types.json.Jsonb({"targets": res["targets"], "cash_after": str(res["cash_after"])}), notes))
        row = cur.fetchone()
        tid = int(next(iter(row.values())) if isinstance(row, dict) else row[0])
        for i, line in enumerate(res["lines"], 1):
            cur.execute("""INSERT INTO idx.ticket_line (ticket_id, seq, code, side, lots, limit_price, ref_close, notional, weight_now, weight_target, reason, flags)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                        (tid, i, line["code"], line["side"], line["lots"], line["limit_price"], line["ref_close"], line["notional"],
                         line["weight_now"], line["weight_target"], line["reason"], line["flags"]))
    conn.commit()
    return tid


def load(conn: psycopg.Connection, ticket_id: int | None = None, book: str | None = None) -> dict[str, Any] | None:
    t = _rows(conn, """SELECT id, book, ticket_date, run_date, mode, status, nav, cash, n_targets, params, notes, created_at FROM idx.ticket
                       WHERE (%s::bigint IS NULL OR id = %s) AND (%s::text IS NULL OR book = %s) ORDER BY id DESC LIMIT 1""",
              (ticket_id, ticket_id, book, book), ["id", "book", "ticket_date", "run_date", "mode", "status", "nav", "cash", "n_targets", "params", "notes", "created_at"])
    if not t:
        return None
    t = t[0]
    t["lines"] = _rows(conn, """SELECT l.id, l.seq, l.code, li.name, l.side, l.lots, l.limit_price, l.ref_close, l.notional, l.weight_now, l.weight_target,
                                       l.reason, l.flags, l.status, l.filled_lots, l.fill_id, l.skip_reason
                                  FROM idx.ticket_line l LEFT JOIN idx.listing li USING (code) WHERE l.ticket_id = %s ORDER BY l.seq""", (t["id"],),
                       ["id", "seq", "code", "name", "side", "lots", "limit_price", "ref_close", "notional", "weight_now", "weight_target", "reason",
                        "flags", "status", "filled_lots", "fill_id", "skip_reason"])
    return t


def set_status(conn: psycopg.Connection, ticket_id: int, status: str) -> None:
    with conn.cursor() as cur:
        cur.execute("UPDATE idx.ticket SET status = %s, updated_at = now() WHERE id = %s", (status, ticket_id))
    conn.commit()


def fill_line(conn: psycopg.Connection, line_id: int, lots: Decimal, price: Decimal, fee: Decimal | None = None, trade_date: date | None = None,
              note: str | None = None) -> dict[str, Any]:
    """Record the broker fill for a line: a book fill + line status (filled | partial)."""
    ln = _rows(conn, "SELECT l.id, l.ticket_id, l.code, l.side, l.lots, l.filled_lots, t.book, t.ticket_date FROM idx.ticket_line l JOIN idx.ticket t ON t.id = l.ticket_id WHERE l.id = %s",
              (line_id,), ["id", "ticket_id", "code", "side", "lots", "filled_lots", "book", "ticket_date"])
    if not ln:
        raise ValueError(f"no ticket line {line_id}")
    ln = ln[0]
    d = trade_date or date.today()
    fid = bk.add_fill(conn, ln["book"], d, ln["code"], ln["side"], Decimal(lots), Decimal(price), fee, source="manual",
                      note=note or f"ticket {ln['ticket_id']} line {line_id}")
    done = Decimal(ln["filled_lots"]) + Decimal(lots)
    status = "filled" if done >= Decimal(ln["lots"]) else "partial"
    with conn.cursor() as cur:
        cur.execute("UPDATE idx.ticket_line SET status = %s, filled_lots = %s, fill_id = %s, updated_at = now() WHERE id = %s", (status, done, fid, line_id))
    conn.commit()
    bk.mark(conn, ln["book"])
    return {"fill_id": fid, "status": status, "filled_lots": done}


def skip_line(conn: psycopg.Connection, line_id: int, reason: str) -> None:
    with conn.cursor() as cur:
        cur.execute("UPDATE idx.ticket_line SET status = 'skipped', skip_reason = %s, updated_at = now() WHERE id = %s", (reason, line_id))
    conn.commit()


def render(t: dict[str, Any]) -> str:
    o = [f"# Ticket #{t['id']}  {t['book']}  {t['mode']}  {t['status']}  |  prices as of {t['ticket_date']} close, candidates {t['run_date']}",
         f"NAV Rp {float(t['nav'] or 0):,.0f} | cash Rp {float(t['cash'] or 0):,.0f} | targets {t['n_targets']} | cash after (est.) Rp {float(Decimal(str((t['params'] or {}).get('cash_after', 0)))):,.0f}",
         "", "| line | side | code | lots | limit | ref close | notional | now -> target | reason | flags | status |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for line in t["lines"]:
        st = line["status"] + (f" {float(line['filled_lots']):g}" if line["status"] == "partial" else "") + (f": {line['skip_reason']}" if line["skip_reason"] else "")
        o.append(f"| {line['id']} | {line['side'].upper()} | {line['code']} | {float(line['lots']):g} | {float(line['limit_price']):,.0f} | "
                 f"{float(line['ref_close']) if line['ref_close'] is not None else '-':,} | {float(line['notional']):,.0f} | "
                 f"{_pct(line['weight_now'])} -> {_pct(line['weight_target'])} | {line['reason']} | {', '.join(line['flags']) or '-'} | {st} |")
    o += ["", "Work SELL lines first, then BUY. Limits are one tick through the reference close, inside the auto-rejection band. "
          "Record each fill: `idx ticket fill LINE --lots N --price P [--fee F]`; skip with a reason: `idx ticket skip LINE --reason ...`."]
    return "\n".join(o)


def to_json(t: dict[str, Any]) -> str:
    return json.dumps(t, default=str, indent=1)
