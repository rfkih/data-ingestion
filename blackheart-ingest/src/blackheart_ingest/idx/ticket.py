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


def min_trade_for(nav: Decimal, floor: Decimal = MIN_TRADE) -> Decimal:
    """Pure. The smallest line worth placing for a book of this size: one twentieth of NAV, never above the Rp 5M floor
    used for big books and never under Rp 1M (a Rp 50M book gets Rp 2.5M; a Rp 1B book keeps Rp 5M)."""
    return max(Decimal(1_000_000), min(floor, Decimal(nav) / 20))


def _target_weights(targets: list[str] | dict[str, Any]) -> dict[str, Decimal]:
    """Targets as {code: weight} summing to 1: a list means equal weight, a dict carries the strategy's own weights."""
    if isinstance(targets, dict):
        ws = {c: Decimal(str(w)) for c, w in targets.items()}
        tot = sum((w for w in ws.values() if w > 0), Decimal(0))
        return {c: w / tot for c, w in ws.items() if w > 0} if tot > 0 else {}
    return {c: Decimal(1) / len(targets) for c in targets} if targets else {}


def plan(targets: list[str] | dict[str, Any], held: dict[str, dict[str, Any]], prices: dict[str, Decimal], cash: Decimal, *,
         book: dict[str, Any], band: Decimal = BAND, min_trade: Decimal = MIN_TRADE, reserve: Decimal = CASH_RESERVE,
         mode: str = "rebalance", exits: dict[str, str] | None = None, hold_back: set[str] | None = None,
         buys_only: bool = False) -> dict[str, Any]:
    """Pure. targets = codes (equal weight) or {code: weight}; held = {code: {lots, avg_price}}; prices = last close per
    code. Returns lines + sizing context. ``hold_back``: target names not to buy this time (their slot stays in cash);
    ``buys_only``: no sells or trims (an entry ticket)."""
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
    tw = _target_weights(targets)
    n = len(tw)
    target_value = {c: nav * (1 - reserve) * w for c, w in tw.items()}
    w_target = {c: (target_value[c] / nav if nav else Decimal(0)) for c in tw}
    hold_back = hold_back or set()
    # sells: no longer a target -> exit; overweight beyond the band -> trim
    for c, h in held.items():
        if c not in prices or buys_only:
            continue
        v, lots = value[c], Decimal(h["lots"])
        if c not in tw:
            lp = limit_price(prices[c], "sell")
            lines.append({"code": c, "side": "sell", "lots": lots, "limit_price": lp, "ref_close": prices[c], "notional": lots * LOT * lp,
                          "weight_now": v / nav, "weight_target": Decimal(0), "reason": "no longer selected", "flags": []})
        elif v - target_value[c] > band * nav and v - target_value[c] >= min_trade:
            lp = limit_price(prices[c], "sell")
            trim = Decimal(math.ceil((v - target_value[c]) / (lp * LOT)))
            if 0 < trim < lots:
                lines.append({"code": c, "side": "sell", "lots": trim, "limit_price": lp, "ref_close": prices[c], "notional": trim * LOT * lp,
                              "weight_now": v / nav, "weight_target": w_target[c], "reason": f"trim {_pct(v / nav)} -> {_pct(w_target[c])}",
                              "flags": []})
    proceeds = sum(ln["notional"] * (1 - fee_sell) for ln in lines)
    budget = cash + proceeds - nav * reserve
    # buys: new entrants and underweights, in the strategy's order
    buys: list[dict[str, Any]] = []
    for c in tw:
        if c in hold_back:
            continue
        if c not in prices:
            buys.append({"code": c, "side": "buy", "lots": Decimal(0), "limit_price": Decimal(0), "ref_close": None, "notional": Decimal(0),
                         "weight_now": Decimal(0), "weight_target": w_target[c], "reason": "no price", "flags": ["no_price"]})
            continue
        v = value.get(c, Decimal(0))
        gap = target_value[c] - v
        if gap <= band * nav or gap < min_trade:
            continue
        lp = limit_price(prices[c], "buy")
        lots = Decimal(int((gap / (1 + fee_buy)) // (lp * LOT)))
        if lots <= 0:
            continue
        buys.append({"code": c, "side": "buy", "lots": lots, "limit_price": lp, "ref_close": prices[c], "notional": lots * LOT * lp,
                     "weight_now": v / nav if nav else Decimal(0), "weight_target": w_target[c],
                     "reason": "new entrant" if c not in held else f"add {_pct(v / nav)} -> {_pct(w_target[c])}", "flags": []})
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
    return {"nav": nav, "cash": cash, "n_targets": n, "target_value": target_value, "weights": tw, "lines": lines, "cash_after": cash_after,
            "held_back": sorted(c for c in tw if c in hold_back)}


# ---------------------------------------------------------------------------
# build from the database
# ---------------------------------------------------------------------------
def build(conn: psycopg.Connection, book: str, *, mode: str = "rebalance", run_date: date | None = None, max_names: int | None = None,
          strategy: str | None = None, band: Decimal = BAND, min_trade: Decimal | None = None, entrants: list[str] | None = None,
          exits: dict[str, str] | None = None) -> dict[str, Any]:
    """Targets come from the book's strategy and size (idx.book.strategy / max_names) unless overridden per call.
    Modes: rebalance | exits (names whose newest report breaks the rule, or a pack sell) | cash (sell everything: the
    regime filter turned off) | entry (buy ``entrants``, one slot each: held-back names that crossed above their average).
    With the book's regime_filter on, a rebalance while the regime is off becomes a cash ticket; with entry_gate on, listed
    names under their 200-day average are held back (no buy line, slot kept in cash)."""
    from . import overlay, strategies
    b = bk.get_book(conn, book)
    if mode not in ("rebalance", "exits", "cash", "entry"):
        raise ValueError(f"unknown ticket mode {mode!r}")
    strategy = strategy or b.get("strategy") or "rule"
    size = max_names if max_names is not None else b.get("max_names")
    s = bk.snapshot(conn, book)
    held = {p["code"]: {"lots": p["lots"], "avg_price": p["avg_price"]} for p in s["positions"]}
    D = _rows(conn, "SELECT max(run_date) FROM idx.candidate WHERE (%s::date IS NULL OR run_date <= %s)", (run_date, run_date), ["d"])[0]["d"]
    if D is None:
        raise ValueError("no candidate run; run `idx candidates` first")
    cands = _rows(conn, """SELECT code, rank, selected, ep, bp, dy, np_yoy, mom, gate_loose, gate_strict, strict_fails, warnings, sector
                             FROM idx.candidate WHERE run_date = %s ORDER BY rank""", (D,),
                  ["code", "rank", "selected", "ep", "bp", "dy", "np_yoy", "mom", "gate_loose", "gate_strict", "strict_fails", "warnings", "sector"])
    picked = strategies.pick(strategy, cands, size=size or None)
    cmap = {c["code"]: c for c in picked}
    regime = None
    if mode == "rebalance" and b.get("regime_filter"):
        regime = overlay.latest(conn) or overlay.index_regime(conn, D)
        if not regime["on"]:
            mode = "cash"
    if mode == "cash":
        targets = {}
    elif mode == "entry":
        cur = overlay.current_list(conn, book) or {}
        slot = Decimal(1) / max(len(cur.get("weights") or {}), 1)
        targets = {c: slot for c in (entrants or []) if c not in held}
    else:
        targets = {c["code"]: c["weight"] for c in picked if c["selected"]}
    held_back: list[str] = []
    if mode == "rebalance" and b.get("entry_gate") and targets:
        new = [c for c in targets if c not in held]
        held_back = overlay.gate(targets, overlay.name_trend(conn, D, new), set(held), overlay.rsi14(conn, D, new))
    codes = sorted(set(targets) | set(held))
    px = {p["code"]: Decimal(p["close"]) for p in _rows(conn, """
        SELECT DISTINCT ON (code) code, close FROM idx.bar WHERE code = ANY(%s) AND source = 'idx' AND trade_date <= %s
         ORDER BY code, trade_date DESC""", (codes, D), ["code", "close"])}
    answers = {a["code"]: a for a in _rows(conn, """
        SELECT DISTINCT ON (code) code, doc_id AS pack_date, event_type AS stance, veto, rationale FROM idx.sentiment_score
         WHERE doc_type = 'pack' AND code = ANY(%s) ORDER BY code, scored_at DESC""", (codes,), ["code", "pack_date", "stance", "veto", "rationale"])}
    exits = dict(exits or {})                                              # explicit exits (take profit) come from the caller
    if mode == "cash":
        why = "regime off: to cash" if regime else "to cash"
        exits = {c: why for c in held}
    if mode == "exits" and held and not exits:
        fund = fundamentals_asof(conn, D, list(held))
        for c in held:
            m = fund.get(c)
            a = answers.get(c)
            if m and not m["gate_loose"]:
                exits[c] = "newest report breaks the book rule: " + ", ".join(m["strict_fails"])
            elif a and a["stance"] == "sell":
                exits[c] = f"pack {a['pack_date']}: sell - {(a['rationale'] or '')[:100]}"
    nav_now = Decimal(b["cash"]) + sum(Decimal(h["lots"]) * LOT * px[c] for c, h in held.items() if c in px)
    min_trade = min_trade_for(nav_now) if min_trade is None else min_trade
    res = plan(targets, held, px, Decimal(b["cash"]), book=b, band=band, min_trade=min_trade, mode="exits" if mode == "cash" else mode,
               exits=exits, hold_back=set(held_back), buys_only=(mode == "entry"))
    res["min_trade"] = min_trade
    for line in res["lines"]:
        c = cmap.get(line["code"])
        a = answers.get(line["code"])
        if c:
            line["reason"] += f" (rank {c['strategy_rank']})"
            if line["side"] == "buy":
                if not c["gate_strict"]:
                    line["flags"] += [f"strict:{f}" for f in (c["strict_fails"] or [])]
                line["flags"] += [f"warn:{w}" for w in (c["warnings"] or [])]
        if a and a["stance"]:
            line["flags"].append(f"pack:{a['stance']}" + (" VETO" if a["veto"] else ""))
    res.update({"book": book, "mode": mode, "run_date": D, "ticket_date": D, "targets": list(targets), "held": held, "prices": px,
                "strategy": strategy, "size": size or None, "weights": {c: str(w) for c, w in (res.get("weights") or {}).items()},
                "held_back": held_back, "regime_filter": bool(b.get("regime_filter")), "entry_gate": bool(b.get("entry_gate")),
                "regime": None if regime is None else {"check_date": str(regime["check_date"]), "close": str(regime["close"]),
                                                       "sma": None if regime["sma"] is None else str(regime["sma"]), "on": bool(regime["on"])}})
    return res


def store(conn: psycopg.Connection, res: dict[str, Any], notes: str | None = None) -> int:
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO idx.ticket (book, ticket_date, run_date, mode, nav, cash, n_targets, params, notes)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                    (res["book"], res["ticket_date"], res["run_date"], res["mode"], res["nav"], res["cash"], res["n_targets"],
                     psycopg.types.json.Jsonb({"targets": res["targets"], "cash_after": str(res["cash_after"]), "strategy": res.get("strategy"),
                                               "size": res.get("size"), "weights": res.get("weights"), "held_back": res.get("held_back") or [],
                                               "regime": res.get("regime"), "regime_filter": res.get("regime_filter"),
                                               "entry_gate": res.get("entry_gate")}), notes))
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
              note: str | None = None, source: str = "manual") -> dict[str, Any]:
    """Record the broker fill for a line: a book fill + line status (filled | partial)."""
    ln = _rows(conn, "SELECT l.id, l.ticket_id, l.code, l.side, l.lots, l.filled_lots, t.book, t.ticket_date FROM idx.ticket_line l JOIN idx.ticket t ON t.id = l.ticket_id WHERE l.id = %s",
              (line_id,), ["id", "ticket_id", "code", "side", "lots", "filled_lots", "book", "ticket_date"])
    if not ln:
        raise ValueError(f"no ticket line {line_id}")
    ln = ln[0]
    d = trade_date or date.today()
    fid = bk.add_fill(conn, ln["book"], d, ln["code"], ln["side"], Decimal(lots), Decimal(price), fee, source=source,
                      note=note or f"ticket {ln['ticket_id']} line {line_id}")
    done = Decimal(ln["filled_lots"]) + Decimal(lots)
    status = "filled" if done >= Decimal(ln["lots"]) else "partial"
    with conn.cursor() as cur:
        cur.execute("UPDATE idx.ticket_line SET status = %s, filled_lots = %s, fill_id = %s, updated_at = now() WHERE id = %s", (status, done, fid, line_id))
    conn.commit()
    bk.mark(conn, ln["book"])
    return {"fill_id": fid, "status": status, "filled_lots": done}


def paper_fill_plan(lines: list[dict[str, Any]], prices: dict[str, Any], cash: Any, book_meta: dict[str, Any]) -> tuple[list[dict[str, Any]], Decimal]:
    """Pure. The open lines of a paper ticket and the fill day's prices -> what fills at those prices: sells first (they fund
    the buys), then buys in ticket order, each trimmed to whole lots the remaining cash can pay for including the book's
    buy fee. A line without a price that day, or with no cash left, comes back with ``lots`` 0 and a ``why``."""
    cash = Decimal(cash)
    fee_buy = Decimal(book_meta["fee_buy_pct"]) / 100
    fee_sell = Decimal(book_meta["fee_sell_pct"]) / 100
    out: list[dict[str, Any]] = []
    for ln in sorted(lines, key=lambda x: (x["side"] != "sell", x["seq"])):
        if ln["status"] not in ("open", "partial"):
            continue
        want = Decimal(ln["lots"]) - Decimal(ln.get("filled_lots") or 0)
        p = prices.get(ln["code"])
        f = {"line_id": ln["id"], "code": ln["code"], "side": ln["side"], "lots": Decimal(0), "price": None, "why": None}
        if not p or want <= 0:
            f["why"] = "no bar on the fill day" if not p else "nothing left to fill"
            out.append(f)
            continue
        p = Decimal(p)
        if ln["side"] == "buy":
            per_lot = p * bk.LOT * (1 + fee_buy)
            lots = min(want, Decimal(int(cash // per_lot)) if per_lot > 0 else Decimal(0))
            if lots <= 0:
                f["why"] = "cash exhausted"
                out.append(f)
                continue
            cash -= lots * per_lot
        else:
            lots = want
            cash += lots * p * bk.LOT * (1 - fee_sell)
        f.update({"lots": lots, "price": p})
        out.append(f)
    return out, cash


def paper_fill(conn: psycopg.Connection, book: str = "paper", dry_run: bool = False) -> list[dict[str, Any]]:
    """The paper book's convention (as ``book.paper_seed``): open tickets fill at the open of the first trading day after the
    ticket date, sells first, buys trimmed to the cash; lines that cannot fill are skipped with the reason; the ticket closes.
    Refuses any other book: real fills are captured by hand. Returns one report per ticket touched."""
    if book != "paper":
        raise ValueError("paper_fill is for the paper book only")
    reports = []
    for t_id in [r["id"] for r in _rows(conn, "SELECT id FROM idx.ticket WHERE book = %s AND status IN ('draft', 'issued') ORDER BY id", (book,), ["id"])]:
        t = load(conn, t_id)
        d = _rows(conn, "SELECT min(trade_date) AS d FROM idx.bar WHERE source = 'idx' AND trade_date > %s", (t["ticket_date"],), ["d"])[0]["d"]
        rep = {"ticket": t_id, "ticket_date": t["ticket_date"], "fill_date": d, "fills": [], "cash_after": None, "dry_run": dry_run}
        if d is None:
            rep["why"] = "no bar after the ticket date yet"
            reports.append(rep)
            continue
        codes = [ln["code"] for ln in t["lines"] if ln["status"] in ("open", "partial")]
        px = {r["code"]: (r["open"] or r["close"]) for r in _rows(conn, "SELECT code, open, close FROM idx.bar WHERE trade_date = %s AND source = 'idx' AND code = ANY(%s)",
                                                                    (d, codes), ["code", "open", "close"])}
        b = bk.get_book(conn, book)
        fills, cash_after = paper_fill_plan(t["lines"], px, b["cash"], b)
        rep.update({"fills": fills, "cash_after": cash_after})
        if not dry_run:
            for f in fills:
                if f["lots"] > 0:
                    fill_line(conn, f["line_id"], f["lots"], f["price"], None, d, note=f"paper fill at the {d} open (ticket {t_id})", source="paper")
                else:
                    skip_line(conn, f["line_id"], f"paper: {f['why']}")
            set_status(conn, t_id, "closed")
        reports.append(rep)
    return reports


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
