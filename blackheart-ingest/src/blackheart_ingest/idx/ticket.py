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
from contextlib import contextmanager
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import psycopg
import psycopg.types.json

from . import book as bk
from . import journal
from .card import _pct, _rows
from .metrics import fundamentals_asof

logger = logging.getLogger(__name__)
LOT = 100
BAND = Decimal("0.01")              # ignore weight differences inside ±1 % of NAV
MIN_TRADE = Decimal(5_000_000)      # and trades below Rp 5 M
CASH_RESERVE = Decimal("0.01")      # keep 1 % of NAV in cash for fees/rounding
TICKS = ((200, 1), (500, 2), (2000, 5), (5000, 10), (10**12, 25))
BANDS = ((200, Decimal("0.35")), (5000, Decimal("0.25")), (10**12, Decimal("0.20")))
LIVE_BOOKS = frozenset({"live"})     # kept for callers; the rule itself is is_live(): everything that is not paper/test is live


def is_live(book: str) -> bool:
    """Two-key applies to every book that is not a paper or test book (live, trend_live, ...)."""
    b = (book or "").lower()
    return not (b.startswith("paper") or b.startswith("test"))


def is_paper(book: str) -> bool:
    """``paper``, ``paper_trend``, ``paper-3f9a2c`` (created books carry their kind as the id prefix)."""
    return (book or "").lower().startswith("paper")
REBALANCE_WINDOW = ((5, 1), (5, 10))  # the annual rebalance: turnover is expected in May 1-10
TWO_KEY = ("two-key: tickets on the live book are issued and closed by the operator (the Blackridge app or `idx ticket issue`); "
           "the agent may only draft or cancel its own draft")
STATUSES = ("draft", "issued", "closed", "cancelled")


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
def in_rebalance_window(d: date) -> bool:
    (m1, d1), (m2, d2) = REBALANCE_WINDOW
    return (m1, d1) <= (d.month, d.day) <= (m2, d2)


def validate_lines(lines: list[dict[str, Any]], held: dict[str, dict[str, Any]], prices: dict[str, Decimal], cash: Decimal, *,
                   book: dict[str, Any], sectors: dict[str, str | None], v60: dict[str, Decimal | None], allowed_buys: set[str],
                   ticket_date: date, mode: str, actor: str = "operator") -> dict[str, Any]:
    """Pure. The guardrails a ticket must pass before it is issued (or paper-filled), against the book's limits:
    ``lot`` (whole positive lots left to trade), ``band`` (limit inside the auto-rejection band of its reference close),
    ``not_in_candidates`` (a buy outside the candidate run / targets), ``liquidity`` (a buy under ``min_v60``),
    ``max_weight`` / ``max_sector`` (a buy that leaves one name / one sector above the cap, weights on pre-ticket NAV),
    ``cash_negative`` (buys exceed cash plus sale proceeds after fees), ``turnover`` (an AGENT-built rebalance outside the
    May window trading more than ``max_turnover_pct`` of NAV - the anti-churn rule; operator and scheduler tickets are exempt).
    Only open/partial lines count: filled lines are already in ``held``; skipped lines are not traded."""
    fee_buy, fee_sell = Decimal(book["fee_buy_pct"]) / 100, Decimal(book["fee_sell_pct"]) / 100
    lim_w, lim_s = Decimal(book["max_weight_pct"]) / 100, Decimal(book["max_sector_pct"]) / 100
    lim_t, min_v60 = Decimal(book["max_turnover_pct"]) / 100, Decimal(book["min_v60"])

    def price_of(c: str, ln: dict[str, Any] | None = None) -> Decimal | None:
        if c in prices:
            return Decimal(prices[c])
        if ln is not None and ln.get("ref_close") is not None:
            return Decimal(ln["ref_close"])
        return None

    value_now = {c: Decimal(h["lots"]) * LOT * price_of(c) for c, h in held.items() if price_of(c) is not None}
    nav = Decimal(cash) + sum(value_now.values(), Decimal(0))
    post_lots = {c: Decimal(h["lots"]) for c, h in held.items()}
    breaches: list[dict[str, Any]] = []
    traded = buys = sells = Decimal(0)
    active = [ln for ln in lines if (ln.get("status") or "open") in ("open", "partial")]
    for ln in active:
        c, side = ln["code"], ln["side"]
        left = Decimal(ln["lots"]) - Decimal(ln.get("filled_lots") or 0)
        lp = Decimal(ln["limit_price"])
        if left <= 0 or left != left.to_integral_value():
            breaches.append({"kind": "lot", "code": c, "detail": f"{left} lots left to trade", "value": str(left), "limit": "whole lots > 0"})
            continue
        if ln.get("ref_close") is not None:
            lo, hi = reject_band(Decimal(ln["ref_close"]))
            if not lo <= lp <= hi:
                breaches.append({"kind": "band", "code": c, "detail": f"limit {lp} outside auto-rejection band {lo}-{hi} of close {ln['ref_close']}",
                                 "value": str(lp), "limit": f"{lo}-{hi}"})
        notional = left * LOT * lp
        traded += notional
        if side == "buy":
            buys += notional
            post_lots[c] = post_lots.get(c, Decimal(0)) + left
            if c not in allowed_buys:
                breaches.append({"kind": "not_in_candidates", "code": c, "detail": "buy of a name outside the candidate run and the ticket's targets",
                                 "value": c, "limit": "candidates"})
            liq = v60.get(c)
            if liq is None:
                breaches.append({"kind": "liquidity_unknown", "code": c, "detail": "no 60-day traded-value figure for this name", "value": None,
                                 "limit": str(min_v60)})
            elif Decimal(liq) < min_v60:
                breaches.append({"kind": "liquidity", "code": c, "detail": f"60-day median value Rp {float(liq):,.0f}/day under the floor",
                                 "value": str(liq), "limit": str(min_v60)})
        else:
            sells += notional
            post_lots[c] = max(post_lots.get(c, Decimal(0)) - left, Decimal(0))
    line_by_code = {ln["code"]: ln for ln in active}
    post_value = {c: n * LOT * price_of(c, line_by_code.get(c)) for c, n in post_lots.items() if n > 0 and price_of(c, line_by_code.get(c)) is not None}
    weights = {c: (v / nav if nav > 0 else Decimal(0)) for c, v in post_value.items()}
    bought = {ln["code"] for ln in active if ln["side"] == "buy"}
    for c in sorted(bought):
        if weights.get(c, Decimal(0)) > lim_w:
            breaches.append({"kind": "max_weight", "code": c, "detail": f"{c} would be {float(weights[c]) * 100:.1f} % of NAV after the ticket",
                             "value": str(weights[c]), "limit": str(lim_w)})
    sector_w: dict[str, Decimal] = {}
    for c, w in weights.items():
        sec = sectors.get(c)
        if sec:
            sector_w[sec] = sector_w.get(sec, Decimal(0)) + w
    for sec in sorted({sectors.get(c) for c in bought if sectors.get(c)}):
        if sector_w.get(sec, Decimal(0)) > lim_s:
            breaches.append({"kind": "max_sector", "code": None, "detail": f"sector {sec} would be {float(sector_w[sec]) * 100:.1f} % of NAV after the ticket",
                             "value": str(sector_w[sec]), "limit": str(lim_s), "sector": sec})
    cash_after = Decimal(cash) + sells * (1 - fee_sell) - buys * (1 + fee_buy)
    if cash_after < 0:
        breaches.append({"kind": "cash_negative", "code": None, "detail": f"buys exceed cash plus sale proceeds by Rp {float(-cash_after):,.0f}",
                         "value": str(cash_after), "limit": "0"})
    turnover = (traded / nav) if nav > 0 else Decimal(0)
    if actor == "agent" and mode == "rebalance" and not in_rebalance_window(ticket_date) and turnover > lim_t:
        breaches.append({"kind": "turnover", "code": None, "detail": f"agent rebalance outside May 1-10 trades {float(turnover) * 100:.0f} % of NAV",
                         "value": str(turnover), "limit": str(lim_t)})
    return {"ok": not breaches, "breaches": breaches, "n_lines": len(active), "nav": nav, "cash_after": cash_after, "turnover": turnover,
            "weights": {c: str(w) for c, w in sorted(weights.items())}, "sectors": {k: str(v) for k, v in sorted(sector_w.items())},
            "actor": actor, "in_rebalance_window": in_rebalance_window(ticket_date)}


def validate(conn: psycopg.Connection, ticket_id: int) -> dict[str, Any]:
    """The guardrails against the live state of the book: current positions, latest closes, the candidate run the ticket was
    built from (pool + sectors + liquidity), the book's limits and status. Adds ``halted`` when the book is."""
    t = load(conn, ticket_id)
    if t is None:
        raise ValueError(f"no ticket {ticket_id}")
    b = bk.get_book(conn, t["book"])
    s = bk.snapshot(conn, t["book"])
    held = {p["code"]: {"lots": p["lots"], "avg_price": p["avg_price"]} for p in s["positions"]}
    codes = sorted(set(held) | {ln["code"] for ln in t["lines"]})
    px = {r["code"]: Decimal(r["close"]) for r in _rows(conn, """
        SELECT DISTINCT ON (code) code, close FROM idx.bar WHERE code = ANY(%s) AND source IN ('idx', 'yahoo') ORDER BY code, trade_date DESC""",
        (codes,), ["code", "close"])}
    cands = _rows(conn, "SELECT code, sector, v60 FROM idx.candidate WHERE run_date = %s", (t["run_date"],), ["code", "sector", "v60"]) if t["run_date"] else []
    sectors = {r["code"]: r["sector"] for r in _rows(conn, "SELECT code, sector FROM idx.listing WHERE code = ANY(%s)", (codes,), ["code", "sector"])}
    sectors.update({c["code"]: c["sector"] for c in cands if c["sector"]})
    v60 = {c["code"]: c["v60"] for c in cands}
    for r in _rows(conn, """SELECT DISTINCT ON (code) code, value_60d_median FROM idx.feature_daily
                             WHERE code = ANY(%s) AND value_60d_median IS NOT NULL ORDER BY code, trade_date DESC""",
                   ([c for c in codes if c not in v60],), ["code", "v60"]):
        v60.setdefault(r["code"], r["v60"])
    params = t.get("params") or {}
    allowed = {c["code"] for c in cands} | set(params.get("targets") or [])
    res = validate_lines(t["lines"], held, px, Decimal(b["cash"]), book=b, sectors=sectors, v60=v60, allowed_buys=allowed,
                         ticket_date=t["ticket_date"], mode=t["mode"], actor=str(params.get("actor") or "operator"))
    if bk.is_halted(b):
        res["breaches"].insert(0, {"kind": "halted", "code": None, "detail": f"book {t['book']} is halted: {b.get('halt_reason') or ''}".rstrip(": "),
                                   "value": "halted", "limit": "active"})
        res["ok"] = False
    res.update({"ticket_id": ticket_id, "book": t["book"], "status": t["status"], "book_status": b.get("status")})
    return res


def breaches_text(v: dict[str, Any]) -> str:
    return "; ".join(f"{x['kind']}" + (f" {x['code']}" if x.get("code") else "") + f": {x['detail']}" for x in v["breaches"])


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
    if bk.is_halted(b):
        raise ValueError(f"book {book} is halted ({b.get('halt_reason') or 'no reason given'}); resume it before building a ticket")
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
        SELECT DISTINCT ON (code) code, close FROM idx.bar WHERE code = ANY(%s) AND source IN ('idx', 'yahoo') AND trade_date <= %s
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
    reserve, stress_state = CASH_RESERVE, None
    if overlay.uses_cash_buffer(b):                                        # the standing / stress cash buffer as the plan's reserve
        sig = overlay.latest_stress(conn) or overlay.stress_signals(conn, D)
        stress_state = {"check_date": str(sig["check_date"]), "n_on": sig["n_on"], "on": overlay.stress_on(sig, b.get("stress_rule") or "ma")}
        reserve = max(CASH_RESERVE, overlay.cash_target(b, stress_state["on"]))
    res = plan(targets, held, px, Decimal(b["cash"]), book=b, band=band, min_trade=min_trade, mode="exits" if mode == "cash" else mode,
               exits=exits, hold_back=set(held_back), buys_only=(mode == "entry"), reserve=reserve)
    res["min_trade"] = min_trade
    res["cash_target"] = str(reserve)
    res["stress"] = stress_state
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


def store(conn: psycopg.Connection, res: dict[str, Any], notes: str | None = None, actor: str = "operator") -> int:
    """``actor`` (agent | operator | scheduler) is kept in params: the turnover guardrail applies to agent-built tickets only."""
    if actor not in journal.ACTORS:
        raise ValueError(f"actor must be one of {journal.ACTORS}")
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO idx.ticket (book, ticket_date, run_date, mode, nav, cash, n_targets, params, notes)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                    (res["book"], res["ticket_date"], res["run_date"], res["mode"], res["nav"], res["cash"], res["n_targets"],
                     psycopg.types.json.Jsonb({"targets": res["targets"], "cash_after": str(res["cash_after"]), "strategy": res.get("strategy"),
                                               "size": res.get("size"), "weights": res.get("weights"), "held_back": res.get("held_back") or [],
                                               "regime": res.get("regime"), "regime_filter": res.get("regime_filter"),
                                               "entry_gate": res.get("entry_gate"), "actor": actor}), notes))
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



def list_recent(conn: psycopg.Connection, book: str, since: date, limit: int = 40) -> list[dict[str, Any]]:
    """Every ticket of a book dated on/after ``since`` plus any older one still open (draft/issued), newest first, with lines."""
    ids = [r["id"] for r in _rows(conn, """SELECT id FROM idx.ticket WHERE book = %s AND (ticket_date >= %s OR status IN ('draft', 'issued'))
                                            ORDER BY id DESC LIMIT %s""", (book, since, limit), ["id"])]
    return [t for t in (load(conn, i) for i in ids) if t]


def set_status(conn: psycopg.Connection, ticket_id: int, status: str, actor: str = "operator", rationale: str | None = None) -> dict[str, Any]:
    """Move a ticket between draft | issued | closed | cancelled. Guardrails (all server-side, so no client can skip them):
    two-key - on a live book only the operator issues or closes (``PermissionError``); a halted book issues nothing;
    ``issued`` requires ``validate`` to pass (``ValueError`` listing every breach). Every change is journaled."""
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    t = load(conn, ticket_id)
    if t is None:
        raise ValueError(f"no ticket {ticket_id}")
    if is_live(t["book"]) and status in ("issued", "closed") and actor != "operator":
        raise PermissionError(TWO_KEY)
    checks = None
    if status == "issued":
        checks = validate(conn, ticket_id)
        if not checks["ok"]:
            raise ValueError(f"ticket #{ticket_id} cannot be issued: " + breaches_text(checks))
    with conn.cursor() as cur:
        cur.execute("UPDATE idx.ticket SET status = %s, updated_at = now() WHERE id = %s", (status, ticket_id))
    journal.record(conn, t["book"], actor, "ticket_status", ticket_id=ticket_id, rationale=rationale or f"{t['status']} -> {status}",
                   refs={"from": t["status"], "to": status, "mode": t["mode"], "n_lines": len(t["lines"]),
                         "turnover": str(checks["turnover"]) if checks else None}, commit=False)
    conn.commit()
    return {"id": ticket_id, "status": status, "checks": checks}


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
    if not is_paper(book):
        raise ValueError("paper_fill is for paper books only")
    reports = []
    if bk.is_halted(bk.get_book(conn, book)):
        return reports                                                     # kill switch: nothing fills until resume
    with _book_lock(conn, f"paper_fill:{book}"):                          # two chains can never fill the same ticket twice
        return _paper_fill_locked(conn, book, dry_run, reports)


@contextmanager
def _book_lock(conn: psycopg.Connection, key: str):
    """Session-level advisory lock (survives the commits inside); released on exit even on error."""
    with conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_lock(hashtext(%s))", (key,))
    conn.commit()
    try:
        yield
    finally:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_unlock(hashtext(%s))", (key,))
        conn.commit()


def _paper_fill_locked(conn: psycopg.Connection, book: str, dry_run: bool, reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for t_id in [r["id"] for r in _rows(conn, "SELECT id FROM idx.ticket WHERE book = %s AND status IN ('draft', 'issued') ORDER BY id", (book,), ["id"])]:
        t = load(conn, t_id)
        checks = validate(conn, t_id)
        if not checks["ok"]:
            reports.append({"ticket": t_id, "ticket_date": t["ticket_date"], "fill_date": None, "fills": [], "cash_after": None, "dry_run": dry_run,
                            "why": "guardrails: " + breaches_text(checks)})
            if not dry_run:
                bk._alert_once(conn, "warning", f"ticket:{book}", f"paper ticket #{t_id} not filled - " + breaches_text(checks))
            continue
        d = _rows(conn, "SELECT min(trade_date) AS d FROM idx.bar WHERE source IN ('idx', 'yahoo') AND trade_date > %s", (t["ticket_date"],), ["d"])[0]["d"]
        rep = {"ticket": t_id, "ticket_date": t["ticket_date"], "fill_date": d, "fills": [], "cash_after": None, "dry_run": dry_run}
        if d is None:
            rep["why"] = "no bar after the ticket date yet"
            reports.append(rep)
            continue
        codes = [ln["code"] for ln in t["lines"] if ln["status"] in ("open", "partial")]
        px = {r["code"]: (r["open"] or r["close"]) for r in _rows(conn, "SELECT code, open, close FROM idx.bar WHERE trade_date = %s AND source IN ('idx', 'yahoo') AND code = ANY(%s)",
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
            set_status(conn, t_id, "closed", actor="scheduler", rationale=f"paper fill at the {d} open")
        reports.append(rep)
    return reports


def line_book(conn: psycopg.Connection, line_id: int) -> dict[str, Any] | None:
    """Which ticket and book a line belongs to (the routes gate live lines on it)."""
    rows = _rows(conn, "SELECT l.id, l.ticket_id, l.code, l.side, t.book FROM idx.ticket_line l JOIN idx.ticket t ON t.id = l.ticket_id WHERE l.id = %s",
                 (line_id,), ["id", "ticket_id", "code", "side", "book"])
    return rows[0] if rows else None


def skip_line(conn: psycopg.Connection, line_id: int, reason: str) -> None:
    with conn.cursor() as cur:
        cur.execute("UPDATE idx.ticket_line SET status = 'skipped', skip_reason = %s, updated_at = now() WHERE id = %s", (reason, line_id))
    conn.commit()


SAME_DAY_MODES = frozenset({"gapfade", "gapfade_exit"})   # drafted in the morning for THAT session; everything else is drafted
                                                          # from a close and worked the NEXT session (trend, rebalance, exits)


def stale_state(ticket_id: int, book: str, mode: str, ticket_date: date, lines: list[dict[str, Any]], today: date,
                sessions_passed: int) -> dict[str, Any] | None:
    """Pure. Why an ``issued`` ticket still needs the operator, or None if it does not.

    ``sessions_passed`` = trading days strictly between ``ticket_date`` and ``today`` - the sessions that have fully
    closed since the ticket was dated. The session in progress is never one of them, so a ticket is only "stale" once
    the session it was meant for is over:

      trend / rebalance / exits   dated at a close, worked the NEXT session -> stale when sessions_passed >= 1.
                                  The morning after the draft is sessions_passed == 0: the normal case, not stale.
                                  (Measured in calendar days this flagged EVERY overnight ticket - the bug this fixes.)
      gapfade / gapfade_exit      dated the morning it is for -> stale as soon as today > ticket_date.

    Two ways a ticket drifts, needing opposite actions:
      waiting   lines still ``open``; ``stale`` says whether the prices it was built on are already a session old.
      finish    every line filled or skipped but the ticket never closed, which blocks the next draft
                (ticket #103 sat like this from 2026-09-17).
    ``key`` is stable per ticket - no ages, no counts - so ``runlog.alert_once`` can dedupe on it day after day.
    """
    if not lines:
        return None
    open_n = sum(1 for ln in lines if ln.get("status") == "open")
    filled_n = sum(1 for ln in lines if ln.get("status") == "filled")
    if open_n == 0:
        return {"id": ticket_id, "book": book, "mode": mode, "kind": "finish", "stale": False, "open": 0,
                "filled": filled_n, "sessions_passed": sessions_passed,
                "key": f"#{ticket_id} ({book}) finish",
                "why": f"#{ticket_id} ({book}): {filled_n} lines filled, none open - close the ticket"}
    stale = today > ticket_date if mode in SAME_DAY_MODES else sessions_passed >= 1
    if not stale:
        why = f"#{ticket_id} ({book}): {open_n} line(s) not worked yet - for this session"
    elif mode in SAME_DAY_MODES:
        why = f"#{ticket_id} ({book}): {open_n} line(s) never worked - it was for {ticket_date}, prices are stale"
    else:
        why = (f"#{ticket_id} ({book}): {open_n} line(s) not worked - the session it was drafted for closed "
               f"{sessions_passed} session(s) ago, prices are stale")
    return {"id": ticket_id, "book": book, "mode": mode, "kind": "waiting", "stale": stale, "open": open_n,
            "filled": filled_n, "sessions_passed": sessions_passed,
            "key": f"#{ticket_id} ({book}) waiting", "why": why}


def sessions_between(conn: psycopg.Connection, start: date, end: date) -> int:
    """Trading days strictly between two dates, from the bars the desk has (``idx.bar``)."""
    if end <= start:
        return 0
    return len(bk._trading_days(conn, start + timedelta(days=1), end - timedelta(days=1)))


def stale_tickets(conn: psycopg.Connection, today: date | None = None) -> list[dict[str, Any]]:
    """Shell: every issued ticket that still needs the operator, newest first."""
    today = today or date.today()
    ts = _rows(conn, "SELECT id, book, mode, ticket_date FROM idx.ticket WHERE status = 'issued' ORDER BY id DESC",
               (), ["id", "book", "mode", "ticket_date"])
    out = []
    for t in ts:
        lines = _rows(conn, "SELECT status FROM idx.ticket_line WHERE ticket_id = %s", (t["id"],), ["status"])
        s = stale_state(t["id"], t["book"], t["mode"] or "", t["ticket_date"], lines, today,
                        sessions_between(conn, t["ticket_date"], today))
        if s:
            out.append(s)
    return out


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
