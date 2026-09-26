"""Session rule engine: actions that wait for a price or time condition are rows (``idx.order_intent``), evaluated by ONE
session tick for every book, instead of one scheduled job per rule (operator, 2026-09-26: "architecture yang bagus, scalable,
jangan kebanyakan job").

  intent        a pending action on one name of one book: side, kind, a TRIGGER (a registered condition + a time window),
                an optional lot count (None = the sleeve's whole position when it fires), where it came from (ref), an expiry
  life cycle    armed -> triggered -> ticket_issued -> filled | expired | cancelled; every change is an order_intent_event
  trigger       a registered pure predicate over (trigger spec, last price, time of day); a new rule is a new entry in
                TRIGGERS, not a new job
  tick          session_tick(): reconcile the intents each book's settings imply, read the live prices once for every armed
                name, evaluate, and turn the fired intents into tickets through the same path as the ML confirmations
                (live: draft + push for the operator to execute; paper: issued and filled at once)

Pure core (TRIGGERS, evaluate, the plan_* reconcilers) / thin shell (session_tick and its helpers), as in combo_book.

Kinds
  ml_stop     (phase 1, study #288) an ML position whose price at or after 15:40 WIB is at or below entry x (1 - ml.stop) is sold
              in the same closing session; the limit sits at the lower auto-rejection bound so it fills in the closing auction
              even on a falling day. The nightly plan's next-session stop (combo_book.compose) stays as the fallback.
  ml_confirm  (phase 2) the ML sleeve's price confirmation: armed by the nightly plan (one per name and ens4 rule), fires when
              the last trade is at or above the level in the session, and buys the rule's share of the ML slot. Replaces the
              combo_confirm job and the pending rows of idx.combo_watch.
  gap_exit    (phase 3) every gap-fade position is sold into the closing auction from 15:50 (trigger at_time); all of a book's
              gap exits go on one ticket, as before. Replaces the combo_gap_exit job.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

import psycopg

from . import book as bk
from . import combo_book as cb
from . import gapfade, ticket

logger = logging.getLogger(__name__)
WIB = cb.WIB
LIVE_STATUSES = ("armed", "triggered", "ticket_issued")
TRANSITIONS = {
    "armed": {"triggered", "expired", "cancelled"},
    "triggered": {"ticket_issued", "carried", "cancelled"},       # carried: its job was done without a ticket of its own
    "ticket_issued": {"filled", "cancelled"},
}
STOP_AFTER, STOP_BEFORE = "15:40", "15:50"          # the ML stop's window: from 15:40 until the pre-closing session opens
CONFIRM_AFTER, CONFIRM_BEFORE = "08:58", "15:50"    # the ML confirmation's window: the continuous session
GAP_AFTER, GAP_BEFORE = "15:50", "15:58"            # the gap exit: the pre-closing session's order entry
ENGINE_FROM, ENGINE_TO = time(8, 58), time(15, 58)  # the tick runs on weekdays inside this span
ML_KINDS = ("ml_stop", "ml_confirm")                # kinds that wait while the name has an open ticket line


def in_window(now: datetime) -> bool:
    t = now.astimezone(WIB)
    return t.weekday() < 5 and ENGINE_FROM <= t.time() <= ENGINE_TO


# ---------------------------------------------------------------------------------------------------------------- pure core
def _in_window(spec: dict[str, Any], now_t: time) -> bool:
    after = time.fromisoformat(spec["after"]) if spec.get("after") else time.min
    before = time.fromisoformat(spec["before"]) if spec.get("before") else time.max
    return after <= now_t <= before


def _price_at_or_below(spec: dict[str, Any], price: Decimal | None, now_t: time) -> bool:
    return price is not None and _in_window(spec, now_t) and price <= Decimal(str(spec["level"]))


def _price_at_or_above(spec: dict[str, Any], price: Decimal | None, now_t: time) -> bool:
    return price is not None and _in_window(spec, now_t) and price >= Decimal(str(spec["level"]))


def _at_time(spec: dict[str, Any], price: Decimal | None, now_t: time) -> bool:
    return _in_window(spec, now_t)


TRIGGERS: dict[str, Callable[[dict[str, Any], Decimal | None, time], bool]] = {
    "price_at_or_below": _price_at_or_below,
    "price_at_or_above": _price_at_or_above,
    "at_time": _at_time,
}


def evaluate(intents: list[dict[str, Any]], prices: dict[str, Decimal], now: datetime) -> list[dict[str, Any]]:
    """The armed intents whose trigger holds now, each with the price that fired it. Pure."""
    now_t = now.astimezone(WIB).time()
    fired = []
    for it in intents:
        if it["status"] != "armed":
            continue
        spec = it["trigger"] if isinstance(it["trigger"], dict) else json.loads(it["trigger"])
        fn = TRIGGERS.get(spec.get("type"))
        if fn is None:
            raise ValueError(f"intent #{it.get('id')}: unknown trigger type {spec.get('type')!r}")
        px = prices.get(it["code"])
        if fn(spec, px, now_t):
            fired.append({**it, "fire_price": px})
    return fired


def stop_level(entry: Decimal, stop: float) -> Decimal:
    return (Decimal(entry) * (1 - Decimal(str(stop)))).quantize(Decimal("0.0001"))


def plan_ml_stops(positions: dict[str, dict[str, Any]], stop: float | None, live: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[tuple[dict[str, Any], str]]]:
    """What the ML stop setting implies against the intents that exist. -> (to create, [(intent, reason) to cancel]). Pure.
    One armed stop per held ML name at entry x (1 - stop); a changed entry (a top-up) or a changed setting re-arms it; a name
    no longer held, or the stop switched off, cancels it. Intents already past 'armed' are left to run their course."""
    armed = {it["code"]: it for it in live if it["kind"] == "ml_stop" and it["status"] == "armed"}
    busy = {it["code"] for it in live if it["kind"] == "ml_stop" and it["status"] != "armed"}
    create, cancel = [], []
    for code, it in armed.items():
        p = positions.get(code)
        if stop is None:
            cancel.append((it, "stop switched off"))
        elif p is None or not p.get("entry_price"):
            cancel.append((it, "no longer held in the ML sleeve"))
        elif Decimal(str(it["trigger"]["level"])) != stop_level(p["entry_price"], stop):
            cancel.append((it, "entry price or stop changed"))
    if stop is None:
        return create, cancel
    kept = {c for c, it in armed.items() if all(it is not x for x, _ in cancel)}
    for code, p in positions.items():
        if code in kept or code in busy or not p.get("entry_price"):
            continue
        create.append({"code": code, "side": "sell", "kind": "ml_stop", "sleeve": "ml",
                       "trigger": {"type": "price_at_or_below", "level": float(stop_level(p["entry_price"], stop)),
                                   "after": STOP_AFTER, "before": STOP_BEFORE},
                       "ref": {"entry_price": float(p["entry_price"]), "stop": float(stop), "entry_date": str(p.get("entry_date")), "study": 288}})
    return create, cancel


def ml_confirm_spec(w: dict[str, Any]) -> dict[str, Any]:
    """The nightly plan's ML watch (combo_book.compose) as an ml_confirm intent: buy when the price reaches the level, until
    the watch's last day."""
    return {"code": w["code"], "side": "buy", "kind": "ml_confirm", "sleeve": "ml", "expires_on": w["until_date"],
            "trigger": {"type": "price_at_or_above", "level": float(w["level_price"]), "after": CONFIRM_AFTER, "before": CONFIRM_BEFORE},
            "ref": {"signal_date": str(w["signal_date"]), "ref_price": float(w["ref_price"]), "level_price": float(w["level_price"]),
                    "e_bps": None if w.get("e_bps") is None else float(w["e_bps"]), "cost_bps": None if w.get("cost_bps") is None else float(w["cost_bps"]),
                    "rule": w.get("rule") or "+5/10", "size_frac": float(w.get("size_frac") or 1)}}


def plan_gap_exits(positions: dict[str, dict[str, Any]], live: list[dict[str, Any]], d: date) -> tuple[list[dict[str, Any]], list[tuple[dict[str, Any], str]]]:
    """One gap_exit intent per gap-fade position for today's pre-closing session; an armed one whose name left the sleeve is
    cancelled. Pure."""
    mine = {it["code"]: it for it in live if it["kind"] == "gap_exit"}
    cancel = [(it, "no longer held in the gap sleeve") for c, it in mine.items() if it["status"] == "armed" and c not in positions]
    create = [{"code": c, "side": "sell", "kind": "gap_exit", "sleeve": "gap", "expires_on": d,
               "trigger": {"type": "at_time", "after": GAP_AFTER, "before": GAP_BEFORE},
               "ref": {"entry_price": float(p["entry_price"]) if p.get("entry_price") else None, "entry_date": str(p.get("entry_date"))}}
              for c, p in positions.items() if c not in mine]
    return create, cancel


# ---------------------------------------------------------------------------------------------------------------- shell
def _rows(conn: psycopg.Connection, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [c.name for c in cur.description]
        return [r if isinstance(r, dict) else dict(zip(cols, r, strict=True)) for r in cur.fetchall()]


def live_intents(conn: psycopg.Connection, book: str | None = None) -> list[dict[str, Any]]:
    return _rows(conn, """SELECT id, book, sleeve, code, side, kind, trigger, lots, ref, status, expires_on, ticket_id FROM idx.order_intent
                           WHERE status = ANY(%s) AND (%s::text IS NULL OR book = %s) ORDER BY id""", (list(LIVE_STATUSES), book, book))


def create(conn: psycopg.Connection, book: str, spec: dict[str, Any], actor: str = "scheduler", *, if_absent: bool = False) -> int | None:
    """Arm an intent. if_absent: a live one for the same name, kind and rule already exists -> nothing, None."""
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO idx.order_intent (book, sleeve, code, side, kind, trigger, lots, ref, expires_on)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""" + (" ON CONFLICT DO NOTHING" if if_absent else "") + " RETURNING id",
                    (book, spec["sleeve"], spec["code"], spec["side"], spec["kind"], json.dumps(spec["trigger"]), spec.get("lots"),
                     json.dumps(spec.get("ref") or {}), spec.get("expires_on")))
        row = cur.fetchone()
        if row is None:
            return None
        iid = int(row[0] if not isinstance(row, dict) else row["id"])
        cur.execute("INSERT INTO idx.order_intent_event (intent_id, from_status, to_status, note, actor) VALUES (%s, NULL, 'armed', %s, %s)",
                    (iid, f"{spec['kind']} {spec['trigger']['type']} {spec['trigger'].get('level')}", actor))
    return iid


def transition(conn: psycopg.Connection, intent: dict[str, Any], to: str, *, price: Decimal | None = None, note: str | None = None,
               ticket_id: int | None = None, actor: str = "scheduler") -> None:
    frm = intent["status"]
    if to not in TRANSITIONS.get(frm, set()):
        raise ValueError(f"intent #{intent['id']}: {frm} -> {to} is not a valid transition")
    with conn.cursor() as cur:
        cur.execute("UPDATE idx.order_intent SET status = %s, ticket_id = COALESCE(%s, ticket_id), updated_at = now() WHERE id = %s AND status = %s",
                    (to, ticket_id, intent["id"], frm))
        if cur.rowcount != 1:
            raise RuntimeError(f"intent #{intent['id']} changed under us (expected {frm})")
        cur.execute("INSERT INTO idx.order_intent_event (intent_id, from_status, to_status, price, note, actor) VALUES (%s, %s, %s, %s, %s, %s)",
                    (intent["id"], frm, to, price, note, actor))
    intent["status"] = to


def _settle_issued(conn: psycopg.Connection, live: list[dict[str, Any]], held: set[str], actor: str) -> None:
    """A ticket_issued intent ends with its ticket line: filled (the line filled, a sell whose name left the sleeve, or the
    ticket closed) or cancelled (the line skipped - a missed order - or the ticket cancelled)."""
    for it in [x for x in live if x["status"] == "ticket_issued" and x.get("ticket_id")]:
        t = ticket.load(conn, int(it["ticket_id"])) or {}
        st = t.get("status")
        ln = next((x for x in t.get("lines") or [] if x.get("code") == it["code"]), None)
        lst = (ln or {}).get("status")
        if lst == "filled" or (it["side"] == "sell" and it["code"] not in held and st not in ("cancelled", "expired")):
            transition(conn, it, "filled", note=f"ticket #{it['ticket_id']} {st}, line {lst}", actor=actor)
        elif lst in ("skipped", "cancelled") or st in ("cancelled", "expired"):
            transition(conn, it, "cancelled", note=f"ticket #{it['ticket_id']} {st}, line {lst}", actor=actor)
        elif st == "closed":
            transition(conn, it, "filled", note=f"ticket #{it['ticket_id']} closed", actor=actor)


def _expire(conn: psycopg.Connection, live: list[dict[str, Any]], d: date, actor: str) -> list[str]:
    """An armed intent past its last day expires (a watch that never confirmed, yesterday's gap exit)."""
    gone = []
    for it in [x for x in live if x["status"] == "armed" and x.get("expires_on") and x["expires_on"] < d]:
        transition(conn, it, "expired", note=f"last day {it['expires_on']}", actor=actor)
        gone.append(it["code"])
    return gone


def _fire_ml_stop(conn: psycopg.Connection, b: dict[str, Any], it: dict[str, Any], pos: dict[str, dict[str, dict[str, Any]]], d: date,
                  actor: str) -> tuple[str, int | None]:
    book, code, last = b["book"], it["code"], Decimal(it["fire_price"])
    p = pos["ml"].get(code)
    if p is None:
        transition(conn, it, "cancelled", price=last, note="not held when the stop fired", actor=actor)
        return "cancelled", None
    transition(conn, it, "triggered", price=last, note=f"last {float(last):,.0f} <= stop {float(it['trigger']['level']):,.0f}", actor=actor)
    snap = bk.snapshot(conn, book)
    nav, cash = Decimal(snap["nav_now"]), Decimal(b["cash"])
    fee_s = Decimal(b["fee_sell_pct"]) / 100
    stop_pct = float(it["ref"].get("stop", 0)) * 100
    ln = cb.size_line(code, "sell", last, Decimal(p["lots"]), Decimal(0), cash, fee_s, nav,
                      f"ML stop {stop_pct:g} % (hari yang sama): harga {float(last):,.0f} <= {100 - stop_pct:g} % dari harga masuk "
                      f"{float(p['entry_price']):,.0f} - jual di sesi penutupan hari ini, limit di batas bawah ARB supaya terisi",
                      ["sleeve:ml", "ml:exit", "ml:stop", "exit:must", "stop:sameday", f"intent:{it['id']}"])
    ln["limit_price"] = ticket.snap(ticket.reject_band(last)[0], "sell")
    ln["notional"] = Decimal(p["lots"]) * ticket.LOT * ln["limit_price"]
    res = gapfade._ticket_res(book, d, cb.MODE, [ln], b, conn, targets=sorted(cb.held_codes(pos) - {code}))
    res["strategy"] = "combo"
    tid = ticket.store(conn, res, notes=f"combo ML same-day stop {code} at {float(last):,.0f} (intent {it['id']})", actor=actor)
    checks = ticket.validate(conn, tid)
    if not checks["ok"]:
        ticket.set_status(conn, tid, "cancelled", actor=actor, rationale="intents: stop ticket failed validation")
        transition(conn, it, "cancelled", price=last, note="validation: " + ticket.breaches_text(checks), actor=actor)
        return "validation", tid
    transition(conn, it, "ticket_issued", price=last, ticket_id=tid, actor=actor)
    t = ticket.load(conn, tid)
    if ticket.is_live(book):
        cb._notify(conn, book, f"[combo] STOP ML {code}: harga {float(last):,.0f} <= stop {float(it['trigger']['level']):,.0f}\n"
                               f"JUAL {int(ln['lots'])} lot di sesi penutupan HARI INI, limit {float(ln['limit_price']):,.0f} (batas bawah), ticket #{tid}",
                   data={"route": f"/m/ticket?book={book}", "kind": "ticket", "book": book, "ticket": tid})
        return "draft", tid
    # paper: the closing session is taken at the price that fired the stop (the 15:40 price stands in for the close)
    ticket.set_status(conn, tid, "issued", actor=actor, rationale="intents: paper stop issued")
    ticket.fill_line(conn, t["lines"][0]["id"], ln["lots"], last, trade_date=d, note=f"paper same-day stop at {float(last):,.0f} (intent {it['id']})",
                     source="paper")
    ticket.set_status(conn, tid, "closed", actor=actor, rationale="intents: paper stop filled")
    transition(conn, it, "filled", price=last, note="paper fill", actor=actor)
    return "filled", tid


def _watch(it: dict[str, Any]) -> dict[str, Any]:
    r = it["ref"]
    return {"id": it["id"], "code": it["code"], "signal_date": date.fromisoformat(str(r["signal_date"])), "level_price": Decimal(str(r["level_price"])),
            "e_bps": r.get("e_bps"), "rule": r.get("rule") or "+5/10", "size_frac": Decimal(str(r.get("size_frac") or 1))}


def _fire_ml_confirms(conn: psycopg.Connection, b: dict[str, Any], S: dict[str, Any], fired: list[dict[str, Any]], pos: dict[str, dict[str, dict[str, Any]]],
                      d: date, actor: str) -> list[tuple[dict[str, Any], str, int | None]]:
    """The confirmed ML watches, best expected edge first: each buys its rule's share of the ML slot (ens4 tops a name up to the
    cumulative share of the rules that fired; a dust share is carried to the next rule). No free slot or the cash floor: the
    intent stays armed and may fire later in the window. Live: draft + push. Paper: issued and filled at the trigger price."""
    book = b["book"]
    fired = sorted(fired, key=lambda x: (-float(x["ref"].get("e_bps") or 0), float(x["trigger"]["level"])))
    snap = bk.snapshot(conn, book)
    nav, cash = Decimal(snap["nav_now"]), Decimal(b["cash"])
    n_open = len(cb.held_codes(pos)) + len(cb._open_lines(conn, book))
    fee_b = Decimal(b["fee_buy_pct"]) / 100
    slot = Decimal(str(S["sleeves"]["ml"])) * nav
    ml_cap = S["adv_cap"].get("ml")
    adv = cb.adv20(conn, [x["code"] for x in fired], d - timedelta(days=1)) if ml_cap is not None else {}
    out = []
    for it in fired:
        w, last = _watch(it), Decimal(it["fire_price"])
        code, frac = w["code"], w["size_frac"]
        why = f"last {float(last):,.0f} >= level {float(w['level_price']):,.0f}"
        try:
            held_ml = pos["ml"].get(code)
            same_signal = held_ml is not None and held_ml.get("entry_date") is not None and held_ml["entry_date"] >= w["signal_date"]
            if code in cb.held_codes(pos) and not (frac < 1 and same_signal):
                transition(conn, it, "cancelled", price=last, note="already held", actor=actor)
                out.append((it, "cancelled: already held", None))
                conn.commit()
                continue
            if code not in cb.held_codes(pos) and n_open >= S["slots"]:
                out.append((it, "waiting: no free slot", None))
                continue
            budget = slot
            if frac < 1:
                done = Decimal(str(cb.triggered_share(conn, book, code, w["signal_date"], exclude=it["id"])))
                bought = (held_ml["lots"] * ticket.LOT * held_ml["entry_price"]) if same_signal else Decimal(0)
                budget = slot * min(done + frac, Decimal(1)) - bought
                if budget <= 0:
                    transition(conn, it, "triggered", price=last, note=why, actor=actor)
                    transition(conn, it, "carried", price=last, note="share already filled by an earlier rule", actor=actor)
                    out.append((it, "carried", None))
                    conn.commit()
                    continue
            budget = cb.adv_capped(budget, adv.get(code), ml_cap)
            ln = cb.size_line(code, "buy", last, None, budget, cash, fee_b, nav,
                              f"ML konfirmasi {w['rule']}: harga {float(last):,.0f} >= level {float(w['level_price']):,.0f} (sinyal {w['signal_date']:%d %b}, "
                              f"ekspektasi {float(w['e_bps'] or 0):+.0f} bps)",
                              ["sleeve:ml", "ml:entry", f"level:{float(w['level_price']):.0f}", f"rule:{w['rule']}", f"intent:{it['id']}"])
            if ln is None and frac < 1 and cash >= budget:
                transition(conn, it, "triggered", price=last, note=why, actor=actor)
                transition(conn, it, "carried", price=last, note="dust: share carried to the next rule", actor=actor)
                out.append((it, "carried: dust", None))
                conn.commit()
                continue
            if ln is None:
                transition(conn, it, "cancelled", price=last, note="no cash for a slot", actor=actor)
                out.append((it, "cancelled: no cash", None))
                conn.commit()
                continue
            if not cb.invested_ok(nav, cash, ln["notional"] * (1 + fee_b), S["cash_floor"]):
                out.append((it, "waiting: cash floor", None))       # stays armed: the floor may free up before the window ends
                continue
            transition(conn, it, "triggered", price=last, note=why, actor=actor)
            res = gapfade._ticket_res(book, d, cb.MODE, [ln], b, conn, targets=[code, *sorted(cb.held_codes(pos))])
            res["strategy"] = "combo"
            tid = ticket.store(conn, res, notes=f"combo ML confirmation {code} at {float(last):,.0f} (intent {it['id']})", actor=actor)
            checks = ticket.validate(conn, tid)
            if not checks["ok"]:
                ticket.set_status(conn, tid, "cancelled", actor=actor, rationale="intents: confirmation ticket failed validation")
                transition(conn, it, "cancelled", price=last, note="validation: " + ticket.breaches_text(checks), actor=actor)
                out.append((it, "validation", tid))
                conn.commit()
                continue
            transition(conn, it, "ticket_issued", price=last, ticket_id=tid, actor=actor)
            t = ticket.load(conn, tid)
            if ticket.is_live(book):
                cb._notify(conn, book, f"[combo] KONFIRMASI ML {code}: harga {float(last):,.0f} >= level {float(w['level_price']):,.0f}\n"
                                       f"BELI {int(ln['lots'])} lot, limit <= {float(ln['limit_price']):,.0f} (Rp {float(ln['notional']) / 1e6:,.2f} jt), ticket #{tid}",
                           data={"route": f"/m/ticket?book={book}", "kind": "ticket", "book": book, "ticket": tid})
                out.append((it, "draft", tid))
            else:
                ticket.set_status(conn, tid, "issued", actor=actor, rationale="intents: paper confirmation issued")
                ticket.fill_line(conn, t["lines"][0]["id"], ln["lots"], ln["limit_price"], trade_date=d, note=f"combo paper fill at the trigger (ticket {tid})",
                                 source="paper")
                ticket.set_status(conn, tid, "closed", actor=actor, rationale="intents: paper confirmation filled at the trigger price")
                transition(conn, it, "filled", price=ln["limit_price"], note="paper fill", actor=actor)
                cash -= ln["notional"] * (1 + fee_b)
                pos["ml"][code] = {"lots": (held_ml["lots"] if same_signal else Decimal(0)) + ln["lots"],
                                   "entry_date": held_ml["entry_date"] if same_signal else w["signal_date"], "entry_price": ln["limit_price"]}
                out.append((it, "filled", tid))
            if code not in cb.held_codes(pos):
                n_open += 1
            conn.commit()
        except Exception as e:  # one intent failing never stops the others; it stays visible in its events
            conn.rollback()
            logger.exception("intent #%s ml_confirm %s failed", it["id"], code)
            out.append((it, f"error: {e}", None))
    return out


def _fire_gap_exits(conn: psycopg.Connection, b: dict[str, Any], fired: list[dict[str, Any]], d: date, actor: str) -> list[tuple[dict[str, Any], str, int | None]]:
    """All of the book's gap exits on one closing-auction ticket (combo_book.gap_exit_unlocked, idempotent per day)."""
    rep = cb.gap_exit_unlocked(conn, b, actor, d)
    codes, tid = set(rep.get("codes") or []), rep.get("ticket")
    out = []
    for it in fired:
        transition(conn, it, "triggered", note=f"pre-closing session {GAP_AFTER}", actor=actor)
        if tid and it["code"] in codes:
            transition(conn, it, "ticket_issued", ticket_id=tid, note=rep.get("why") or "gap exit ticket", actor=actor)
            out.append((it, str(rep.get("status") or "issued"), tid))
        else:
            transition(conn, it, "cancelled", note=rep.get("why") or "no price today - not on the exit ticket", actor=actor)
            out.append((it, "cancelled: " + (rep.get("why") or "no price today"), tid))
    conn.commit()
    return out


def tick_book(conn: psycopg.Connection, book: str, now: datetime, actor: str = "scheduler") -> dict[str, Any]:
    """One book: settle and expire its intents, reconcile them with its settings and positions, then fire what the live prices
    and the clock trigger."""
    d = now.astimezone(WIB).date()
    b = bk.get_book(conn, book)
    out: dict[str, Any] = {"book": book, "armed": 0, "created": 0, "cancelled": 0, "expired": [], "fired": []}
    if bk.is_halted(b):
        return out
    S = cb.settings(b)
    with ticket._book_lock(conn, f"combo:{book}"):
        pos = cb.sleeve_positions(conn, book)
        live = live_intents(conn, book)
        _settle_issued(conn, live, cb.held_codes(pos), actor)
        out["expired"] = _expire(conn, live, d, actor)
        live = [x for x in live if x["status"] in LIVE_STATUSES]
        to_create, to_cancel = plan_ml_stops(pos["ml"], S["ml"].get("stop"), live)
        if S["sleeves"].get("gap", 0) > 0 or pos["gap"]:
            c2, x2 = plan_gap_exits(pos["gap"], live, d)
            to_create, to_cancel = to_create + c2, to_cancel + x2
        for it, why in to_cancel:
            transition(conn, it, "cancelled", note=why, actor=actor)
        for spec in to_create:
            create(conn, book, spec, actor)
        conn.commit()
        out["created"], out["cancelled"] = len(to_create), len(to_cancel)
        armed = [x for x in live_intents(conn, book) if x["status"] == "armed" and not (x.get("expires_on") and x["expires_on"] < d)]
        out["armed"] = len(armed)
        if not armed:
            return out
        busy = cb._open_lines(conn, book)                          # an ML name with an open ticket line is already being traded
        prices = gapfade.last_feed_prices(conn, d, sorted({x["code"] for x in armed if x["trigger"].get("type") != "at_time"}))
        fired = evaluate([x for x in armed if not (x["kind"] in ML_KINDS and x["code"] in busy)], prices, now)
        results: list[tuple[dict[str, Any], str, int | None]] = []
        for it in [x for x in fired if x["kind"] == "ml_stop"]:
            try:
                what, tid = _fire_ml_stop(conn, b, it, pos, d, actor)
                conn.commit()
            except Exception as e:  # one intent failing never stops the others; it stays visible in its events
                conn.rollback()
                logger.exception("intent #%s ml_stop %s failed", it["id"], it["code"])
                what, tid = f"error: {e}", None
            results.append((it, what, tid))
        for kind, fire in (("ml_confirm", lambda xs: _fire_ml_confirms(conn, b, S, xs, pos, d, actor)),
                           ("gap_exit", lambda xs: _fire_gap_exits(conn, b, xs, d, actor))):
            xs = [x for x in fired if x["kind"] == kind]
            if not xs:
                continue
            try:
                results += fire(xs)
            except Exception as e:
                conn.rollback()
                logger.exception("intents: %s batch on %s failed", kind, book)
                results += [(x, f"error: {e}", None) for x in xs]
        for it in [x for x in fired if x["kind"] not in ("ml_stop", "ml_confirm", "gap_exit")]:
            results.append((it, "unknown kind", None))
        out["fired"] = [{"intent": it["id"], "code": it["code"], "kind": it["kind"], "price": None if it.get("fire_price") is None else float(it["fire_price"]),
                         "result": what, "ticket": tid} for it, what, tid in results]
    return out


def session_tick(conn: psycopg.Connection, now: datetime | None = None, actor: str = "scheduler") -> list[dict[str, Any]]:
    """The one job: every book with intents, once. Outside the session (08:58-15:58 WIB, weekdays) it does nothing."""
    now = now or datetime.now(WIB)
    if not in_window(now):
        return []
    out = []
    for book in cb.combo_books(conn):
        try:
            out.append(tick_book(conn, book, now, actor))
        except Exception:  # one book failing never stops the others
            conn.rollback()
            logger.exception("session tick: book %s failed", book)
    return out
