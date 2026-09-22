"""Gap-fade book - buy the opening overreaction, sell it into the same close (research menu 29b, 2026-09-22:
``research/IDX_GAPFADE_2026-09-22.md``, study #77). A book is a gap-fade book when its ``rule`` is ``gapfade``.

The rule, exactly as backtested (nothing tuned here):
  universe  Utama/Pengembangan, ACTIVE, 60-day median value >= Rp 5 bn, previous close >= Rp 50
  entry     the opening price is <= -7 % against the previous close; deepest gaps first, K = 5 slots, one slot = NAV / K,
            bought at the open + one tick
  exit      every position is sold into the SAME day's closing auction (close - one tick). Nothing is ever held overnight.
  timing    the opening auction prints reach the tick feed at ~08:58 WIB and are the official open for ~90 % of names
            (verified 2026-09-22), so the scan runs at 08:58, the exit ticket at 15:50, and the exit fill is recorded in
            the evening at the official close.

Status: PAPER ONLY by decision. Menu 29b is BOUNDARY, not a candidate: every arm positive, placebo 100th percentile, monotone
in the gap (-5 % +182 bps, -7 % +300, -10 % +507), sleeve Sharpe 2.9-4.9 - but the daily t is 2.97 against a declared 3.0 and
the sample is young (IDX opens are dense only from 2025). The paper book exists to measure the ONE number the backtest cannot:
the difference between the opening price we see and the price we can actually buy. A live gap-fade book needs >= 20 sessions
of paper fills plus the operator's decision.

Robustness (why each guard is here, all failures are loud and safe):
  stale feed      the opening prints must be today's and inside 08:55-09:10 WIB; a name whose first print is later did not
                  open then and is skipped. No prints at all, or fewer than MIN_FEED_NAMES names -> no trading, one alert.
  stale bars      the previous close must come from the last trading day within 5 calendar days; otherwise no trading.
  no offer        a name locked at auto-rejection down has no offer to buy (the mirror of the ARA trap, menu 16): the latest
                  book snapshot must show an offer, else the name is skipped.
  not a price     A CORPORATE ACTION IS NOT A GAP. On a split, bonus or rights ex-date the open is quoted on the new basis
                  against yesterday's old-basis close, which reads as a crash that never happened (DSSA 2026-04-09: a 1:25
                  split showed as -96 %; CUAN 2025-07-15, a 1:10 split, as -90 %; 8 of 539 events since 2025). Three
                  filters: the gap may not breach the day's auto-rejection band (a real price move cannot), a name with a
                  corporate action or a dividend ex-date today is skipped, and a breach raises an alert because it means a
                  corporate action the desk has not recorded yet.
  leftovers       a position that survived the previous session (exit job missed, no bar) is sold at today's open BEFORE any
                  new entry, and raises a warning - the book is intraday by construction.
  once a day      one entry ticket and one exit ticket per book per day, under the same advisory lock the paper filler uses,
                  so a second run (manual or scheduler) fills nothing twice.
  halt            a halted book scans, reports and trades nothing.
  live books      never auto-filled: the ticket is drafted and pushed to the phone, the operator holds the second key.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import psycopg

from . import book as bk
from . import journal, runlog, ticket
from .card import _rows

logger = logging.getLogger(__name__)

GAP_MAX = Decimal("-0.07")                  # buy only gaps at or below this
K = 5                                       # slots; one slot = NAV / K
LIQ_MIN = Decimal(5_000_000_000)
PRICE_MIN = Decimal(50)
OPEN_FROM, OPEN_TO = time(8, 55), time(9, 10)
MIN_FEED_NAMES = 50                         # fewer names than this in the opening window = a broken feed, not a quiet market
MAX_BAR_AGE_DAYS = 5
MODE_IN, MODE_OUT = "gapfade", "gapfade_exit"
WIB = ZoneInfo("Asia/Jakarta")


def session_phase(now: datetime) -> str:
    """Where the trading day is, for the live screen: closed | pre-open | open | lunch | closing | after.
    Mon-Thu 09:00-12:00 / 13:30-15:49 continuous, Fri 09:00-11:30 / 14:00-15:49; pre-opening from 08:45."""
    if now.weekday() >= 5:
        return "closed"
    t, fri = now.time(), now.weekday() == 4
    lunch_from, lunch_to = (time(11, 30), time(14, 0)) if fri else (time(12, 0), time(13, 30))
    if t < time(8, 45):
        return "closed"
    if t < time(9, 0):
        return "pre-open"
    if t < lunch_from:
        return "open"
    if t < lunch_to:
        return "lunch"
    if t < time(15, 50):
        return "open"
    if t <= time(16, 15):
        return "closing"
    return "after"


def _auto_fills(book: str) -> bool:
    """Paper (and test) books are filled by the job itself; a live book is never auto-filled - the operator holds the
    second key, exactly as ``ticket.is_live`` defines it everywhere else on the desk."""
    return not ticket.is_live(book)


def gapfade_books(conn: psycopg.Connection) -> list[str]:
    """Every open gap-fade book on the desk (any owner) - what the morning and afternoon jobs run."""
    return [r["book"] for r in _rows(conn, "SELECT book FROM idx.book WHERE rule = 'gapfade' AND archived_at IS NULL AND book NOT LIKE 'test%%' ORDER BY book",
                                     (), ["book"])]


def settings(b: dict[str, Any]) -> tuple[Decimal, int]:
    """(gap threshold, slots) for a book: ``max_names`` overrides K; the threshold is fixed until research moves it."""
    return GAP_MAX, int(b.get("max_names") or K)


# ----------------------------------------------------------------------------------------------------------------- pure
def gap_of(open_px: Decimal, prev_close: Decimal) -> Decimal:
    return (Decimal(open_px) / Decimal(prev_close)) - 1


def pick(cands: list[dict[str, Any]], k: int, held: set[str] | None = None) -> list[dict[str, Any]]:
    """Pure. Eligible candidates -> the k deepest gaps, one line per name, never a name already held."""
    held = held or set()
    out = [c for c in sorted(cands, key=lambda x: (x["gap"], -float(x.get("v60") or 0))) if c["code"] not in held]
    return out[:k]


def plan_entries(picked: list[dict[str, Any]], nav: Decimal, cash: Decimal, k: int, fee_buy: Decimal,
                 min_trade: Decimal) -> list[dict[str, Any]]:
    """Pure. One slot = NAV / k, bought at the open + one tick, trimmed to whole lots the cash can pay for."""
    slot = (Decimal(nav) / k) if k else Decimal(0)
    left = Decimal(cash)
    lines = []
    for c in picked:
        lp = ticket.limit_price(Decimal(c["open"]), "buy")
        per_lot = lp * ticket.LOT * (1 + fee_buy)
        if per_lot <= 0:
            continue
        lots = Decimal(int(min(slot, left) // per_lot))
        notional = lots * ticket.LOT * lp
        if lots <= 0 or notional < min_trade:
            continue
        left -= notional * (1 + fee_buy)
        lines.append({"code": c["code"], "side": "buy", "lots": lots, "limit_price": lp, "ref_close": Decimal(c["open"]), "notional": notional,
                      "weight_now": Decimal(0), "weight_target": (notional / nav) if nav else None,
                      "reason": f"gap {float(c['gap']) * 100:.1f} % at the open ({c['prev_close']} -> {c['open']})",
                      "flags": ["gapfade:entry", f"gap:{float(c['gap']) * 100:.1f}%"]})
    return lines


def plan_exits(positions: list[dict[str, Any]], prices: dict[str, Decimal], reason: str = "gapfade: same-day exit") -> list[dict[str, Any]]:
    """Pure. Sell every position at the reference price less one tick; a position without a price is left out (and the
    caller must keep it, never drop it silently)."""
    lines = []
    for p in sorted(positions, key=lambda x: x["code"]):
        lots = Decimal(p["lots"])
        px = prices.get(p["code"])
        if lots <= 0 or px is None:
            continue
        lp = ticket.limit_price(Decimal(px), "sell")
        notional = lots * ticket.LOT * lp
        lines.append({"code": p["code"], "side": "sell", "lots": lots, "limit_price": lp, "ref_close": Decimal(px), "notional": notional,
                      "weight_now": None, "weight_target": Decimal(0), "reason": reason, "flags": ["gapfade:exit"]})
    return lines


# ----------------------------------------------------------------------------------------------------------------- data
def opening_prices(conn: psycopg.Connection, d: date) -> dict[str, dict[str, Any]]:
    """The first print of the day per name from the tick feed, kept only when it falls in the opening window. That print is
    the opening-auction match: on 2026-09-22 it equalled the official IDX open for 122 of 135 names."""
    rows = _rows(conn, """SELECT DISTINCT ON (code) code, price, ts AT TIME ZONE 'Asia/Jakarta' AS t FROM idx.feed_trade
                           WHERE (ts AT TIME ZONE 'Asia/Jakarta')::date = %s ORDER BY code, ts""", (d,), ["code", "price", "t"])
    out = {}
    for r in rows:
        t = r["t"].time() if isinstance(r["t"], datetime) else None
        if t is None or not (OPEN_FROM <= t <= OPEN_TO) or not r["price"]:
            continue
        out[r["code"]] = {"open": Decimal(str(r["price"])), "at": r["t"]}
    return out


def offers(conn: psycopg.Connection, d: date) -> dict[str, Decimal]:
    """Latest offer per name from the book feed today: no offer = nothing to buy (auto-rejection lock)."""
    rows = _rows(conn, """SELECT DISTINCT ON (code) code, off_px[1] AS off, off_vol[1] AS ov FROM idx.feed_book
                           WHERE (ts AT TIME ZONE 'Asia/Jakarta')::date = %s ORDER BY code, ts DESC""", (d,), ["code", "off", "ov"])
    return {r["code"]: Decimal(str(r["off"])) for r in rows if r["off"] and Decimal(str(r["off"])) > 0 and (r["ov"] or 0) > 0}


def corporate_actions(conn: psycopg.Connection, d: date) -> set[str]:
    """Names whose basis changed today (split, bonus, rights): their open is not comparable with yesterday's close."""
    return {r["code"] for r in _rows(conn, "SELECT code FROM idx.corporate_action WHERE ex_date = %s", (d,), ["code"])}


def ex_dividends(conn: psycopg.Connection, d: date) -> set[str]:
    """Names trading ex-dividend today: the open drops by the dividend, which is not an overreaction to fade."""
    return {r["code"] for r in _rows(conn, "SELECT code FROM idx.dividend WHERE ex_date = %s", (d,), ["code"])}


def prev_session(conn: psycopg.Connection, d: date) -> date | None:
    r = _rows(conn, "SELECT max(trade_date) AS d FROM idx.bar WHERE source = 'idx' AND trade_date < %s", (d,), ["d"])
    return r[0]["d"] if r and r[0]["d"] else None


def scan(conn: psycopg.Connection, d: date | None = None, gap_max: Decimal = GAP_MAX) -> dict[str, Any]:
    """Today's gap-down candidates from the feed, with every guard applied. Never raises on market conditions; the caller
    reads ``ok`` and ``why``."""
    d = d or datetime.now().date()
    res: dict[str, Any] = {"date": d, "ok": False, "why": None, "candidates": [], "seen": 0, "prev_date": None, "skipped": {}}
    px = opening_prices(conn, d)
    res["seen"] = len(px)
    if len(px) < MIN_FEED_NAMES:
        res["why"] = f"only {len(px)} opening prints in the feed (need {MIN_FEED_NAMES}) - the collector is down or the market is closed"
        return res
    pd_ = prev_session(conn, d)
    res["prev_date"] = pd_
    if pd_ is None or (d - pd_).days > MAX_BAR_AGE_DAYS:
        res["why"] = f"last IDX bar is {pd_} - too old to price a gap against"
        return res
    base = {r["code"]: r for r in _rows(conn, """
        SELECT b.code, b.close AS prev_close, f.value_60d_median AS v60, l.board, l.status, l.sector
          FROM idx.bar b JOIN idx.listing l USING (code) LEFT JOIN idx.feature_daily f ON f.code = b.code AND f.trade_date = b.trade_date
         WHERE b.trade_date = %s AND b.source = 'idx'""", (pd_,), ["code", "prev_close", "v60", "board", "status", "sector"])}
    off = offers(conn, d)
    actions = corporate_actions(conn, d)
    divs = ex_dividends(conn, d)
    skipped = {"no_base": 0, "board": 0, "illiquid": 0, "price": 0, "no_offer": 0, "not_deep": 0,
               "corporate_action": 0, "ex_dividend": 0, "impossible": 0}
    impossible: list[str] = []
    cands = []
    for code, o in px.items():
        b = base.get(code)
        if b is None or not b["prev_close"]:
            skipped["no_base"] += 1
            continue
        if b["board"] not in ("Utama", "Pengembangan") or b["status"] != "ACTIVE":
            skipped["board"] += 1
            continue
        if Decimal(b["prev_close"]) < PRICE_MIN:
            skipped["price"] += 1
            continue
        if b["v60"] is None or Decimal(b["v60"]) < LIQ_MIN:
            skipped["illiquid"] += 1
            continue
        g = gap_of(o["open"], b["prev_close"])
        if g > gap_max:
            skipped["not_deep"] += 1
            continue
        if code in actions:                                               # split / bonus / rights: the open is a new basis
            skipped["corporate_action"] += 1
            continue
        if code in divs:                                                  # ex-dividend: the drop is the dividend, not a fall
            skipped["ex_dividend"] += 1
            continue
        if o["open"] < ticket.reject_band(Decimal(b["prev_close"]))[0]:   # deeper than the market allows in a day
            skipped["impossible"] += 1
            impossible.append(code)
            continue
        if code not in off:
            skipped["no_offer"] += 1                                      # locked at ARB: there is nothing to buy
            continue
        cands.append({"code": code, "open": o["open"], "at": o["at"], "prev_close": Decimal(b["prev_close"]), "gap": g,
                      "v60": Decimal(b["v60"]), "sector": b["sector"], "offer": off[code]})
    res.update({"ok": True, "candidates": sorted(cands, key=lambda c: c["gap"]), "skipped": skipped, "impossible": impossible})
    if impossible:                                                        # a corporate action the desk does not know about yet
        runlog.alert_once(conn, "warning", "gapfade", f"{d}: {', '.join(impossible)} opened beyond the auto-rejection band - "
                                                      "an unrecorded split, bonus or rights, not a price move; skipped")
    return res


def close_prices(conn: psycopg.Connection, d: date, codes: list[str]) -> dict[str, Decimal]:
    """Official IDX closes for the exit fill; empty until the daily chain has fetched the day."""
    if not codes:
        return {}
    return {r["code"]: Decimal(r["close"]) for r in _rows(conn, "SELECT code, close FROM idx.bar WHERE trade_date = %s AND source = 'idx' AND code = ANY(%s)",
                                                          (d, codes), ["code", "close"])}


def last_feed_prices(conn: psycopg.Connection, d: date, codes: list[str]) -> dict[str, Decimal]:
    """Latest traded price today per name - what the 15:50 exit ticket prices its limits against."""
    if not codes:
        return {}
    rows = _rows(conn, """SELECT DISTINCT ON (code) code, price FROM idx.feed_trade
                           WHERE (ts AT TIME ZONE 'Asia/Jakarta')::date = %s AND code = ANY(%s) ORDER BY code, ts DESC""",
                 (d, codes), ["code", "price"])
    return {r["code"]: Decimal(str(r["price"])) for r in rows if r["price"]}


def _tickets_today(conn: psycopg.Connection, book: str, d: date, mode: str) -> list[dict[str, Any]]:
    ids = [r["id"] for r in _rows(conn, "SELECT id FROM idx.ticket WHERE book = %s AND ticket_date = %s AND mode = %s ORDER BY id", (book, d, mode), ["id"])]
    return [ticket.load(conn, i) for i in ids]


def _open_positions(conn: psycopg.Connection, book: str) -> list[dict[str, Any]]:
    return [{"code": p["code"], "lots": Decimal(p["lots"]), "avg_price": p["avg_price"]} for p in bk.snapshot(conn, book)["positions"] if Decimal(p["lots"]) > 0]


def _fill(conn: psycopg.Connection, t: dict[str, Any], prices: dict[str, Decimal], d: date, actor: str, note: str) -> list[dict[str, Any]]:
    """Fill the open lines of a paper ticket at ``prices`` (the line's own limit is the reference, the fill is at the price
    given). A line without a price is skipped with its reason so the ticket can close."""
    done = []
    for ln in t["lines"]:
        if ln["status"] not in ("open", "partial"):
            continue
        p = prices.get(ln["code"])
        want = Decimal(ln["lots"]) - Decimal(ln.get("filled_lots") or 0)
        if p is None or want <= 0:
            ticket.skip_line(conn, ln["id"], "no price for the fill" if p is None else "nothing left to fill")
            continue
        ticket.fill_line(conn, ln["id"], want, Decimal(p), trade_date=d, note=note, source="paper")
        done.append({"code": ln["code"], "side": ln["side"], "lots": want, "price": Decimal(p)})
    return done


# ---------------------------------------------------------------------------------------------------------------- shell
def run_entry(conn: psycopg.Connection, book: str, actor: str = "scheduler", d: date | None = None) -> dict[str, Any]:
    """08:58 WIB: scan, sweep any leftover position, build today's entry ticket. A paper book is filled at the opening price
    at once; a live book's ticket is drafted and pushed to the operator (two-key)."""
    d = d or datetime.now().date()
    b = bk.get_book(conn, book)
    out: dict[str, Any] = {"book": book, "date": str(d), "candidates": 0, "lines": 0, "ticket": None, "status": None, "filled": [], "swept": [], "why": None}
    if b.get("rule") != "gapfade":
        raise ValueError(f"{book} is not a gap-fade book (rule must be 'gapfade')")
    if bk.is_halted(b):
        out["why"] = f"book halted: {b.get('halt_reason') or ''}".strip(": ")
        return out
    gap_max, k = settings(b)
    with ticket._book_lock(conn, f"gapfade:{book}"):                      # one entry per book per day, whoever runs it
        if _tickets_today(conn, book, d, MODE_IN):
            out["why"] = "an entry ticket for today already exists"
            return out
        s = scan(conn, d, gap_max)
        out.update({"candidates": len(s["candidates"]), "seen": s["seen"], "skipped": s["skipped"]})
        if not s["ok"]:
            out["why"] = s["why"]
            runlog.alert(conn, "warning", f"gapfade:{book}", f"no gap-fade scan for {d}: {s['why']}")
            return out
        px_open = {c["code"]: c["open"] for c in s["candidates"]}
        left = _open_positions(conn, book)                                 # intraday book: nothing may survive a session
        if left:
            sweep_px = {**last_feed_prices(conn, d, [p["code"] for p in left]), **px_open}
            lines = plan_exits(left, sweep_px, reason="gapfade: leftover from a previous session, sold at the open")
            if lines:
                res = _ticket_res(book, d, MODE_OUT, lines, b, conn)
                tid = ticket.store(conn, res, notes="gapfade sweep: leftover positions", actor=actor)
                if _auto_fills(book):
                    ticket.set_status(conn, tid, "issued", actor=actor, rationale="gapfade sweep")
                    out["swept"] = _fill(conn, ticket.load(conn, tid), {ln["code"]: ln["ref_close"] for ln in lines}, d, actor, "gapfade sweep at the open")
                    ticket.set_status(conn, tid, "closed", actor=actor, rationale="gapfade sweep filled")
            runlog.alert(conn, "warning", f"gapfade:{book}", f"{len(left)} position(s) survived the previous session and were swept at today's open: "
                                                             + ", ".join(p["code"] for p in left))
        snap = bk.snapshot(conn, book)
        nav, cash = Decimal(snap["nav_now"]), Decimal(b["cash"])
        held = {p["code"] for p in _open_positions(conn, book)}
        picked = pick(s["candidates"], k, held)
        lines = plan_entries(picked, nav, cash, k, Decimal(b["fee_buy_pct"]) / 100, ticket.min_trade_for(nav))
        out["lines"] = len(lines)
        if not lines:
            journal.record(conn, book, actor, "note", rationale=f"gapfade {d}: {len(s['candidates'])} candidate(s), no line "
                                                                f"({'no candidate' if not picked else 'slot or cash too small'})",
                           refs={"candidates": [c["code"] for c in s["candidates"]], "seen": s["seen"]})
            return out
        res = _ticket_res(book, d, MODE_IN, lines, b, conn, targets=[ln["code"] for ln in lines])
        tid = ticket.store(conn, res, notes=f"gapfade: {len(lines)} gap(s) at or below {float(gap_max) * 100:.0f} %", actor=actor)
        out["ticket"] = tid
        t = ticket.load(conn, tid)
        checks = ticket.validate(conn, tid)
        out["checks_ok"] = checks["ok"]
        if not checks["ok"]:
            out["status"] = "draft"
            runlog.alert(conn, "warning", f"ticket:{book}", f"gapfade ticket #{tid} not issued - " + ticket.breaches_text(checks))
            return out
        if ticket.is_live(book):
            out["status"] = "draft"
            _notify(conn, book, f"[gapfade] {b.get('label') or book}: ticket #{tid} - buy at the open, sell into the close\n"
                                + "\n".join(f"  {ln['code']} {int(ln['lots'])} lot @ {float(ln['limit_price']):,.0f} ({ln['reason']})" for ln in lines), t)
            return out
        ticket.set_status(conn, tid, "issued", actor=actor, rationale="gapfade: paper ticket issued for the opening fill")
        out["filled"] = _fill(conn, ticket.load(conn, tid), px_open, d, actor, "gapfade paper fill at the open")
        ticket.set_status(conn, tid, "closed", actor=actor, rationale="gapfade: filled at the open")
        out["status"] = "filled"
        journal.record(conn, book, actor, "note", ticket_id=tid,
                       rationale=f"gapfade {d}: bought {len(out['filled'])} name(s) at the open, to be sold into today's close",
                       refs={"fills": [{"code": f["code"], "lots": str(f["lots"]), "price": str(f["price"])} for f in out["filled"]]})
    return out


def run_exit(conn: psycopg.Connection, book: str, actor: str = "scheduler", d: date | None = None) -> dict[str, Any]:
    """15:50 WIB: the sell ticket for everything the book holds, priced against the last trade. A live book's ticket is
    drafted for the closing auction; a paper book's waits for the official close (``settle``)."""
    d = d or datetime.now().date()
    b = bk.get_book(conn, book)
    out: dict[str, Any] = {"book": book, "date": str(d), "positions": 0, "ticket": None, "status": None, "why": None}
    if b.get("rule") != "gapfade":
        raise ValueError(f"{book} is not a gap-fade book")
    with ticket._book_lock(conn, f"gapfade:{book}"):
        if _tickets_today(conn, book, d, MODE_OUT):
            out["why"] = "an exit ticket for today already exists"
            return out
        pos = _open_positions(conn, book)
        out["positions"] = len(pos)
        if not pos:
            return out
        px = last_feed_prices(conn, d, [p["code"] for p in pos])
        lines = plan_exits(pos, px)
        missing = [p["code"] for p in pos if p["code"] not in px]
        if missing:                                                        # never drop a position: it is swept at tomorrow's open
            runlog.alert(conn, "warning", f"gapfade:{book}", f"no price today for {', '.join(missing)} - not in the exit ticket, will be swept at the next open")
        if not lines:
            out["why"] = "no price for any position"
            return out
        res = _ticket_res(book, d, MODE_OUT, lines, b, conn)
        tid = ticket.store(conn, res, notes="gapfade: sell into the closing auction", actor=actor)
        out["ticket"] = tid
        ticket.set_status(conn, tid, "issued", actor=actor, rationale="gapfade: exit ticket for the closing auction")
        out["status"] = "issued"
        if ticket.is_live(book):
            _notify(conn, book, f"[gapfade] {b.get('label') or book}: SELL into today's close, ticket #{tid}\n"
                                + "\n".join(f"  {ln['code']} {int(ln['lots'])} lot @ ~{float(ln['limit_price']):,.0f}" for ln in lines), ticket.load(conn, tid))
    return out


def settle(conn: psycopg.Connection, book: str, actor: str = "scheduler", d: date | None = None) -> dict[str, Any]:
    """Evening, after the daily chain: fill the paper exit ticket at the official close (less one tick, as backtested).
    Without today's bar the ticket stays open and the position is swept at the next open - never a guessed price."""
    d = d or datetime.now().date()
    out: dict[str, Any] = {"book": book, "date": str(d), "filled": [], "ticket": None, "why": None}
    if not _auto_fills(book):
        out["why"] = "live book: fills are captured from the broker"
        return out
    with ticket._book_lock(conn, f"gapfade:{book}"):
        ts = [t for t in _tickets_today(conn, book, d, MODE_OUT) if t["status"] == "issued"]
        if not ts:
            out["why"] = "no issued exit ticket for today"
            return out
        t = ts[-1]
        out["ticket"] = t["id"]
        codes = [ln["code"] for ln in t["lines"] if ln["status"] in ("open", "partial")]
        closes = close_prices(conn, d, codes)
        if not closes:
            out["why"] = "today's bar has not been published yet"
            runlog.alert(conn, "warning", f"gapfade:{book}", f"exit ticket #{t['id']} could not be filled: no bar for {d} yet")
            return out
        px = {c: ticket.limit_price(p, "sell") for c, p in closes.items()}   # the closing auction less one tick, as backtested
        out["filled"] = _fill(conn, t, px, d, actor, "gapfade paper fill at the close")
        ticket.set_status(conn, t["id"], "closed", actor=actor, rationale="gapfade: exit filled at the close")
        journal.record(conn, book, actor, "note", ticket_id=t["id"], rationale=f"gapfade {d}: sold {len(out['filled'])} name(s) into the close",
                       refs={"fills": [{"code": f["code"], "lots": str(f["lots"]), "price": str(f["price"])} for f in out["filled"]]})
    return out


def _ticket_res(book: str, d: date, mode: str, lines: list[dict[str, Any]], b: dict[str, Any], conn: psycopg.Connection,
                targets: list[str] | None = None) -> dict[str, Any]:
    snap = bk.snapshot(conn, book)
    nav, cash = Decimal(snap["nav_now"]), Decimal(b["cash"])
    buys = sum((ln["notional"] for ln in lines if ln["side"] == "buy"), Decimal(0))
    sells = sum((ln["notional"] for ln in lines if ln["side"] == "sell"), Decimal(0))
    cash_after = cash + sells * (1 - Decimal(b["fee_sell_pct"]) / 100) - buys * (1 + Decimal(b["fee_buy_pct"]) / 100)
    held = [p["code"] for p in snap["positions"] if Decimal(p["lots"]) > 0]
    tg = targets if targets is not None else [c for c in held if c not in {ln["code"] for ln in lines}]
    return {"book": book, "mode": mode, "run_date": d, "ticket_date": d, "nav": nav, "cash": cash, "cash_after": cash_after,
            "n_targets": len(tg), "targets": tg, "lines": lines, "strategy": "gapfade", "size": int(b.get("max_names") or K),
            "weights": {}, "held_back": [], "regime": None, "regime_filter": False, "entry_gate": False}


def _notify(conn: psycopg.Connection, book: str, text: str, t: dict[str, Any]) -> None:
    try:
        from . import notify
        notify.send(text, data=notify.ticket_data(t), book=book)
    except Exception:                                                      # a notification never fails the trading job
        logger.exception("gapfade notify failed")


def render_scan(s: dict[str, Any]) -> str:
    if not s["ok"]:
        return f"# gapfade scan {s['date']}: NOT OK - {s['why']} (prints seen {s['seen']})"
    o = [f"# gapfade scan {s['date']} | opening prints {s['seen']} | previous session {s['prev_date']} | candidates {len(s['candidates'])} "
         f"| skipped {s['skipped']}"]
    for c in s["candidates"]:
        o.append(f"  {c['code']:<6} {float(c['prev_close']):>9,.0f} -> {float(c['open']):>9,.0f}  gap {float(c['gap']) * 100:>6.1f} %  "
                 f"v60 Rp {float(c['v60']) / 1e9:>5.1f} bn  offer {float(c['offer']):,.0f}  ({c['at']:%H:%M:%S})")
    if not s["candidates"]:
        o.append("  (no candidate)")
    return "\n".join(o)


def status(conn: psycopg.Connection, book: str, d: date | None = None) -> dict[str, Any]:
    """What the book did today: tickets, fills, open positions - the one call the CLI and a morning check use."""
    d = d or datetime.now().date()
    ent = _tickets_today(conn, book, d, MODE_IN)
    ex = _tickets_today(conn, book, d, MODE_OUT)
    pos = _open_positions(conn, book)
    snap = bk.snapshot(conn, book)
    return {"book": book, "date": str(d), "entry": [{"id": t["id"], "status": t["status"], "lines": len(t["lines"])} for t in ent],
            "exit": [{"id": t["id"], "status": t["status"], "lines": len(t["lines"])} for t in ex],
            "positions": [{"code": p["code"], "lots": str(p["lots"]), "avg_price": str(p["avg_price"])} for p in pos],
            "nav": str(snap["nav_now"]), "cash": str(snap["book"]["cash"])}
