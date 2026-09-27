"""Broker stop vs the book's trailing rule (operator 2026-09-28: "cek stop broker vs aturan book"), after DEWI and IRSX were
sold off-rule on 2026-09-24 by a 4 % broker stop the operator had mis-set - the trend rule is trail10 (close <= 90 % of the
highest close since entry) and neither name had reached it.

The brokers (Stockbit, IPOT) have no API, so the desk cannot read the stop order sitting at the broker. What it can know is
the stop the operator RECORDED for the name in ``idx.price_level`` (kind ``stop``, ``idx levels set CODE --stop L``); on a
trend book that row means "the auto-order at the broker". Every evening, after the trend ticket, each held name of each live
trend book is classified:

  tight     recorded stop above the trail by more than one tick -> the broker can sell a name the rule still holds (the
            09-24 case). Actionable: lower the broker stop to the trail.
  missing   no stop recorded -> actionable once per holding: set one at or below the trail (the menu-13 advice: a broker
            auto-order at -10 % as a safety net).
  loose     recorded stop more than LOOSE below the trail -> the net is stale since the trail moved up. Reported, not pushed:
            the rule sells on the close through the ticket anyway.
  ok        within [trail x (1 - LOOSE), trail + one tick]

trail = 90 % of the highest close since entry (``book.snapshot``'s peak), rounded DOWN to the tick. The broker triggers on
the last price intraday while the rule reads the close, so the safe side for a broker stop is at or below the trail, never
above it. Nothing here trades or edits a level: the alert says what to change, and ``idx levels set`` records it once done.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

import psycopg

from . import book as bk
from . import levels as lv
from . import runlog, ticket, trend_book

LOOSE = Decimal("0.03")
JOB = "levels"


def trail_level(peak: Decimal | float) -> Decimal:
    """Pure. The rule's stop tonight: 90 % of the peak close, rounded down to the tick (a sell never rounds up)."""
    return ticket.snap(Decimal(str(peak)) * (1 - trend_book.TRAIL), "sell")


def classify(trail: Decimal, stop: Decimal | None) -> str:
    """Pure. ``tight`` / ``missing`` / ``loose`` / ``ok`` for a recorded broker stop against the rule's trail."""
    if stop is None:
        return "missing"
    if stop > trail + ticket.tick_size(trail):
        return "tight"
    if stop < trail * (1 - LOOSE):
        return "loose"
    return "ok"


def message(book: str, code: str, status: str, trail: Decimal, stop: Decimal | None, close: Decimal | None) -> str:
    """The alert text, in the operator's language (a fact and the change to make, no advice beyond the book's own rule)."""
    c = f", close {close:,.0f}" if close is not None else ""
    if status == "tight":
        return (f"{code}: stop broker {stop:,.0f} lebih ketat dari aturan trail10 {trail:,.0f}{c} - broker bisa menjual di luar "
                f"aturan. Turunkan stop di broker ke {trail:,.0f}, lalu `idx levels set {code} --book {book} --stop {trail:.0f}`")
    if status == "missing":
        return (f"{code}: belum ada stop broker tercatat (trail10 {trail:,.0f}{c}). Pasang auto-order jual di broker <= {trail:,.0f}, "
                f"lalu `idx levels set {code} --book {book} --stop {trail:.0f}`")
    if status == "loose":
        return f"{code}: stop broker {stop:,.0f} jauh di bawah trail10 {trail:,.0f}{c} - jaring pengaman sudah tertinggal"
    return f"{code}: stop broker {stop:,.0f} sesuai trail10 {trail:,.0f}"


def check(conn: psycopg.Connection, book: str) -> list[dict[str, Any]]:
    """One row per held name: code, close, peak, trail, recorded stop, status, message. Reads only."""
    s = bk.snapshot(conn, book)
    stops = {r["code"]: Decimal(r["level"]) for r in lv.levels(conn, book) if r["kind"] == "stop" and r.get("active", True)}
    out = []
    for p in s["positions"]:
        peak = p.get("peak") or p.get("close")
        if peak is None:
            continue
        close = Decimal(p["close"]) if p.get("close") is not None else None
        tr = trail_level(max(Decimal(peak), close) if close is not None else Decimal(peak))
        st = stops.get(p["code"])
        status = classify(tr, st)
        out.append({"code": p["code"], "opened_at": p.get("opened_at"), "close": close, "peak": Decimal(peak), "trail": tr, "stop": st,
                    "status": status, "message": message(book, p["code"], status, tr, st, close)})
    return out


def _raised(conn: psycopg.Connection, key: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM idx.alert WHERE dedupe_key = %s LIMIT 1", (key,))
        return cur.fetchone() is not None


def run(conn: psycopg.Connection, book: str) -> dict[str, Any]:
    """Nightly: alert on tight (every night it stays tight - the open alert is updated in place, not duplicated) and on
    missing (once per holding). A name that is fixed has its open stop alerts acknowledged. Paper books are skipped."""
    if not ticket.is_live(book):
        return {"book": book, "skipped": "paper"}
    rows = check(conn, book)
    job = f"{JOB}:{book}"
    counts = {"tight": 0, "missing": 0, "loose": 0, "ok": 0}
    for r in rows:
        counts[r["status"]] += 1
        code = r["code"]
        if r["status"] == "tight":
            runlog.alert(conn, "warning", job, r["message"], kind="risk", code=code, book=book,
                         dedupe_key=f"stopcheck:{book}:{code}:tight",
                         payload={"trail": str(r["trail"]), "stop": str(r["stop"]), "close": str(r["close"])})
        elif r["status"] == "missing":
            key = f"stopcheck:{book}:{code}:missing:{r['opened_at']}"
            if not _raised(conn, key):
                runlog.alert(conn, "warning", job, r["message"], kind="risk", code=code, book=book, dedupe_key=key,
                             payload={"trail": str(r["trail"]), "close": str(r["close"])})
        if r["status"] in ("ok", "loose"):
            with conn.cursor() as cur:
                cur.execute("""UPDATE idx.alert SET acknowledged_at = now() WHERE acknowledged_at IS NULL
                                AND dedupe_key LIKE %s""", (f"stopcheck:{book}:{code}:%",))
    conn.commit()
    return {"book": book, **counts}


def render(book: str, rows: list[dict[str, Any]]) -> str:
    if not rows:
        return f"{book}: tidak ada posisi."
    o = [f"{book}  stop broker vs trail10", f"  {'code':6} {'close':>8} {'peak':>8} {'trail':>8} {'stop':>8}  status"]
    for r in rows:
        st = f"{r['stop']:,.0f}" if r["stop"] is not None else "-"
        cl = f"{r['close']:,.0f}" if r["close"] is not None else "-"
        o.append(f"  {r['code']:6} {cl:>8} {r['peak']:>8,.0f} {r['trail']:>8,.0f} {st:>8}  {r['status']}")
    return "\n".join(o)
