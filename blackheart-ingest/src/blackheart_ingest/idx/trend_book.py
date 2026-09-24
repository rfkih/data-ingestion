"""Trend book - breakout entries, trailing-stop exits (research menus 6-7, 2026-09-17: research/IDX_TREND_FOLLOW_2026-09-17.md,
IDX_TREND_ROBUST_2026-09-17.md). A book is a trend book when its note starts with ``trend:`` followed by the variant
(``trend:small`` - liquid names that are not blue chips, the +29.9 %/yr cut; ``trend:all`` - every liquid name, the +18.9 %/yr lead).

The rule, exactly as backtested (nothing tuned here):
  universe  Utama/Pengembangan, 60-day median value >= Rp 5 bn, close >= Rp 100; ``small`` additionally value < Rp 20 bn OR close < Rp 1,000
  entry     close = highest close of the last 60 bars AND close > 200-day average AND volume >= 1.5x the 20-day median volume;
            free slots are filled by volume ratio, K = 10 slots, one slot = NAV / K
  exit      close <= 90 % of the highest close since entry (trailing stop), or the name stops trading
  timing    signals at the close of day t (after the daily chain); the ticket is worked at the next open - the paper book by the
            scheduler's paper fill, a live book by the operator (two-key), each line a limit one tick through the close
Every ticket carries mode ``trend``; the guardrails (validate, halt, two-key) apply unchanged; the turnover cap is not applied to
trend tickets by construction (it is an annual-book rule), the weight and sector caps are - set them per book.

Money rule stays the money rule: the research verdict was "paper track earned, not a candidate for money" (Sharpe 0.9-1.3 with a
30-36 % drawdown). A live trend book is the operator's decision, staged after >= 60 closed paper trades reproduce the profile.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pandas as pd
import psycopg

from . import book as bk
from . import overlay, runlog, ticket
from .card import _rows

logger = logging.getLogger(__name__)
K = 10
HI_N, MA_N, VOL_N, VOL_X, TRAIL = 60, 200, 20, Decimal("1.5"), Decimal("0.10")
LIQ_MIN, PRICE_MIN, BLUE_LIQ, BLUE_PRICE = Decimal(5_000_000_000), Decimal(100), Decimal(20_000_000_000), Decimal(1000)
VARIANTS = ("small", "all")


def variant_of(b: dict[str, Any]) -> str | None:
    """The trend variant of a book row: the ``rule``/``trend_variant`` columns, or the older ``trend:<variant>`` note."""
    if b.get("rule") == "trend":
        v = (b.get("trend_variant") or "small").lower()
        return v if v in VARIANTS else "small"
    note = (b.get("note") or "").strip()
    if not note.startswith("trend:"):
        return None
    v = note[6:].split()[0].strip().lower()
    return v if v in VARIANTS else "small"


def trend_books(conn: psycopg.Connection) -> list[str]:
    """Every open trend book on the desk (any owner) - what the nightly chain runs."""
    return [r["book"] for r in _rows(conn, "SELECT book FROM idx.book WHERE rule = 'trend' AND archived_at IS NULL AND book NOT LIKE 'test%%' ORDER BY book",
                                     (), ["book"])]


# ---------------------------------------------------------------------------------------------------------------- data
def universe(conn: psycopg.Connection, d: date, variant: str) -> dict[str, dict[str, Any]]:
    rows = _rows(conn, """
        SELECT b.code, b.close, b.volume, f.value_60d_median AS v60 FROM idx.bar b JOIN idx.feature_daily f USING (code, trade_date)
          JOIN idx.listing l USING (code)
         WHERE b.trade_date = %s AND b.source = 'idx' AND l.board IN ('Utama', 'Pengembangan') AND l.status = 'ACTIVE'
           AND f.value_60d_median >= %s AND b.close >= %s AND b.volume > 0""", (d, LIQ_MIN, PRICE_MIN), ["code", "close", "volume", "v60"])
    if variant == "small":
        rows = [r for r in rows if Decimal(r["v60"]) < BLUE_LIQ or Decimal(r["close"]) < BLUE_PRICE]
    return {r["code"]: r for r in rows}


def history(conn: psycopg.Connection, codes: list[str], d: date, bars: int = MA_N + 5) -> pd.DataFrame:
    """Adjusted closes and volumes for ``codes`` over the last ~bars trading days ending at d (long format)."""
    if not codes:
        return pd.DataFrame(columns=["code", "trade_date", "adj", "volume"])
    # Built from tuples on purpose: pandas' read_sql on a dict_row connection (the API's and scheduler's) yields a frame of
    # column names, i.e. no bars and no signals at all (found 2026-09-17: the nightly trend run saw an empty market).
    cols = ["code", "trade_date", "adj", "volume"]
    with conn.cursor() as cur:
        cur.execute("""SELECT code, trade_date, close * adj_factor AS adj, volume FROM idx.bar
                        WHERE code = ANY(%s) AND source = 'idx' AND trade_date <= %s AND trade_date >= %s ORDER BY code, trade_date""",
                    (codes, d, d - timedelta(days=int(bars * 1.6))))
        rows = [tuple(r.values()) if isinstance(r, dict) else tuple(r) for r in cur.fetchall()]
    df = pd.DataFrame(rows, columns=cols)
    df["adj"] = pd.to_numeric(df["adj"], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
    return df


# ---------------------------------------------------------------------------------------------------------------- pure
def hold_back(entries: list[dict[str, Any]], regime_on: bool) -> tuple[list[dict[str, Any]], list[str]]:
    """The regime gate (book option ``regime_filter`` on a trend book; menus 22-25, studies #62-#66): while the COMPOSITE closes under
    its 200-day average no NEW entry is taken and the signals are recorded as held back. Held names are untouched (their trailing
    stop still runs). Validated as a drawdown rule: mDD -30 % -> -18 % on `small` 2020-26, -27 % -> -19 % on 2005-19, return unchanged."""
    if regime_on:
        return entries, []
    return [], [e["code"] for e in entries]


def entry_signals(hist: pd.DataFrame, d: date) -> list[dict[str, Any]]:
    """Pure. Names whose bar on d is a 60-day high, above the 200-day average, on >= 1.5x median volume; ranked by volume ratio."""
    out = []
    for code, g in hist.groupby("code"):
        g = g.sort_values("trade_date")
        if len(g) < MA_N or g["trade_date"].iloc[-1] != d:
            continue
        adj, vol = g["adj"].to_numpy(float), g["volume"].to_numpy(float)
        last, hi60, ma200 = adj[-1], adj[-HI_N:].max(), adj[-MA_N:].mean()
        vmed = float(pd.Series(vol[-VOL_N:]).median())
        if not (vmed > 0 and last > 0):
            continue
        vr = vol[-1] / vmed
        if last >= hi60 and last > ma200 and vr >= float(VOL_X):
            out.append({"code": code, "vol_ratio": round(vr, 2), "ma200": ma200, "hi60": hi60})
    out.sort(key=lambda x: -x["vol_ratio"])
    return out


def exit_signals(positions: list[dict[str, Any]], closes_today: dict[str, Decimal], peaks: dict[str, Decimal]) -> list[dict[str, Any]]:
    """Pure. Held names to sell: trailing stop hit (close <= 90 % of the peak since entry) or no bar today."""
    out = []
    for p in positions:
        c = p["code"]
        px = closes_today.get(c)
        if px is None:
            out.append({"code": c, "lots": Decimal(p["lots"]), "reason": "no bar today: stopped trading", "close": None})
            continue
        peak = max(peaks.get(c, px), px)
        if px <= (1 - TRAIL) * peak:
            out.append({"code": c, "lots": Decimal(p["lots"]), "reason": f"trailing stop: close {px:,.0f} <= 90 % of peak {peak:,.0f}", "close": px})
    return out


def plan(entries: list[dict[str, Any]], exits: list[dict[str, Any]], positions: list[dict[str, Any]], closes: dict[str, Decimal], cash: Decimal,
         b: dict[str, Any], k: int = K) -> dict[str, Any]:
    """Pure. Sell lines for exits, buy lines for free slots sized at NAV / k, limits one tick through the close, cash-limited."""
    fee_buy, fee_sell = Decimal(b["fee_buy_pct"]) / 100, Decimal(b["fee_sell_pct"]) / 100
    held_value = sum(Decimal(p["lots"]) * ticket.LOT * closes.get(p["code"], Decimal(p["avg_price"])) for p in positions)
    nav = cash + held_value
    slot = nav / k if nav > 0 else Decimal(0)
    min_trade = slot / 4                                              # as backtested: 1/K of capital per name; refuse only dust (< a quarter slot)
    lines: list[dict[str, Any]] = []
    cash_after = cash
    exiting = {x["code"] for x in exits}
    for x in exits:
        px = x["close"] if x["close"] is not None else Decimal(next(p["avg_price"] for p in positions if p["code"] == x["code"]))
        lp = ticket.limit_price(px, "sell")
        notional = x["lots"] * ticket.LOT * lp
        cash_after += notional * (1 - fee_sell)
        lines.append({"code": x["code"], "side": "sell", "lots": x["lots"], "limit_price": lp, "ref_close": px, "notional": notional,
                      "weight_now": (x["lots"] * ticket.LOT * px / nav) if nav else None, "weight_target": Decimal(0), "reason": x["reason"], "flags": ["trend:exit"]})
    held_after = [p["code"] for p in positions if p["code"] not in exiting]
    free = max(k - len(held_after), 0)
    for e in entries:
        if free <= 0:
            break
        c = e["code"]
        if c in held_after or c in exiting:
            continue
        px = closes.get(c)
        if px is None:
            continue
        lp = ticket.limit_price(px, "buy")
        per_lot = lp * ticket.LOT * (1 + fee_buy)
        budget = min(slot, cash_after)
        lots = Decimal(int(budget // per_lot)) if per_lot > 0 else Decimal(0)
        if lots <= 0 or lots * ticket.LOT * lp < min_trade:
            continue
        notional = lots * ticket.LOT * lp
        cash_after -= notional * (1 + fee_buy)
        free -= 1
        lines.append({"code": c, "side": "buy", "lots": lots, "limit_price": lp, "ref_close": px, "notional": notional, "weight_now": Decimal(0),
                      "weight_target": (notional / nav) if nav else None, "reason": f"breakout: 60-day high above MA200 on {e['vol_ratio']}x volume",
                      "flags": ["trend:entry", f"vol:{e['vol_ratio']}x"]})
    return {"lines": lines, "nav": nav, "cash": cash, "cash_after": cash_after, "n_targets": len(held_after) + sum(1 for ln in lines if ln["side"] == "buy"),
            "targets": [ln["code"] for ln in lines if ln["side"] == "buy"] + held_after, "min_trade": min_trade}


# ---------------------------------------------------------------------------------------------------------------- shell
def build(conn: psycopg.Connection, book: str, d: date | None = None) -> dict[str, Any]:
    b = bk.get_book(conn, book)
    variant = variant_of(b)
    if variant is None:
        raise ValueError(f"{book} is not a trend book (note must start with 'trend:')")
    if bk.is_halted(b):
        raise ValueError(f"book {book} is halted ({b.get('halt_reason') or 'no reason given'})")
    if d is None:
        d = _rows(conn, "SELECT max(trade_date) AS d FROM idx.bar WHERE source = 'idx'", (), ["d"])[0]["d"]
    s = bk.snapshot(conn, book)
    positions = [{"code": p["code"], "lots": p["lots"], "avg_price": p["avg_price"], "opened_at": p["opened_at"]} for p in s["positions"]]
    uni = universe(conn, d, variant)
    held_codes = [p["code"] for p in positions]
    open_lines = {ln["code"] for t in _open_tickets(conn, book) for ln in t["lines"] if ln["status"] in ("open", "partial")}
    hist = history(conn, sorted(set(uni) | set(held_codes)), d)
    closes = {c: Decimal(str(v)) for c, v in hist[hist["trade_date"] == d].set_index("code")["adj"].items()}
    # raw closes for limits/ticks (adj == raw on the current basis except across a split: use raw where available)
    raw = {r["code"]: Decimal(r["close"]) for r in _rows(conn, "SELECT code, close FROM idx.bar WHERE trade_date = %s AND source = 'idx' AND code = ANY(%s)",
                                                        (d, sorted(set(uni) | set(held_codes))), ["code", "close"])}
    closes_raw = {c: raw.get(c, closes.get(c)) for c in set(closes) | set(raw)}
    peaks = {}
    for p in positions:
        g = hist[(hist["code"] == p["code"]) & (hist["trade_date"] >= p["opened_at"])]
        if len(g):
            peaks[p["code"]] = Decimal(str(g["adj"].max()))
    entries = [e for e in entry_signals(hist[hist["code"].isin(uni)], d) if e["code"] not in held_codes and e["code"] not in open_lines]
    regime, held_back = None, []
    if b.get("regime_filter"):                                        # regime gate: no new entry while the COMPOSITE is under its MA200
        r = overlay.index_regime(conn, d)
        regime = {"index": r["index_code"], "date": str(r["check_date"]), "close": str(r["close"]), "sma": (str(r["sma"]) if r.get("sma") is not None else None),
                  "on": bool(r["on"])}
        entries, held_back = hold_back(entries, regime["on"])
    exits = exit_signals(positions, closes_raw, peaks)
    exits = [x for x in exits if x["code"] not in open_lines]
    res = plan(entries, exits, positions, closes_raw, Decimal(b["cash"]), b)
    res.update({"book": book, "mode": "trend", "run_date": d, "ticket_date": d, "held": {p["code"]: p for p in positions}, "prices": closes_raw,
                "strategy": f"trend:{variant}", "size": K, "weights": {}, "held_back": held_back, "regime_filter": bool(b.get("regime_filter")),
                "entry_gate": False, "regime": regime, "signals": len(entries), "exits": len(exits), "entry_rows": entries, "exit_rows": exits, "universe": len(uni), "variant": variant})
    return res


def _open_tickets(conn: psycopg.Connection, book: str) -> list[dict[str, Any]]:
    ids = [r["id"] for r in _rows(conn, "SELECT id FROM idx.ticket WHERE book = %s AND status IN ('draft', 'issued') ORDER BY id", (book,), ["id"])]
    return [ticket.load(conn, i) for i in ids]


def run(conn: psycopg.Connection, book: str, actor: str = "scheduler", d: date | None = None) -> dict[str, Any]:
    """Tonight's ticket for a trend book: stored as draft; a paper book's ticket is issued at once (the scheduler fills it at the next
    open), a live book's is left as a draft for the operator (two-key) and pushed to Telegram. -> summary."""
    res = build(conn, book, d)
    out = {"book": book, "date": str(res["run_date"]), "universe": res["universe"], "signals": res["signals"], "exits": res["exits"],
           "held_back": len(res["held_back"]), "regime_on": (res["regime"]["on"] if res.get("regime") else None),
           "lines": len(res["lines"]), "ticket": None, "status": None, "cancelled": []}
    for old in _open_tickets(conn, book):                              # a breakout is for one open only: yesterday's unissued draft is stale
        if old.get("mode") == "trend" and old["status"] == "draft" and old["ticket_date"] < res["run_date"]:
            ticket.set_status(conn, old["id"], "cancelled", actor=actor, rationale="stale trend draft: signals are for the next open only")
            out["cancelled"].append(old["id"])
    if out["cancelled"]:                                               # the freed names may signal again today: rebuild once
        res = build(conn, book, d)
        out.update({"signals": res["signals"], "exits": res["exits"], "lines": len(res["lines"])})
    _record_signals(conn, book, res)
    if not res["lines"]:
        return out
    held = f", {len(res['held_back'])} held back (COMPOSITE under MA200)" if res["held_back"] else ""
    tid = ticket.store(conn, res, notes=f"trend {res['variant']}: {res['signals']} signals, {res['exits']} exits{held}", actor=actor)
    out["ticket"] = tid
    t = ticket.load(conn, tid)
    checks = ticket.validate(conn, tid)
    out["checks_ok"] = checks["ok"]
    if not checks["ok"]:
        out["status"] = "draft"
        runlog.alert(conn, "warning", f"ticket:{book}", f"trend ticket #{tid} not issued - " + ticket.breaches_text(checks),
                     kind="ticket", strategy="trend_small", book=book,
                     payload={"ticket": tid, "breaches": checks.get("breaches")}, dedupe_key=f"ticket:{tid}:not_issued")
        return out
    if ticket.is_live(book):
        out["status"] = "draft"
        try:
            from . import notify
            notify.send(f"[trend] {bk.get_book(conn, book).get('label') or book}: ticket #{tid} drafted by {actor}\n" + notify.format_ticket(t, checks),
                        data=notify.ticket_data(t), book=book)
        except Exception:                                                  # never fail the chain on a notification
            logger.exception("trend notify failed")
    else:
        ticket.set_status(conn, tid, "issued", actor=actor, rationale="trend book: paper ticket auto-issued for the next open")
        out["status"] = "issued"
    return out


def _record_signals(conn: psycopg.Connection, book: str, res: dict[str, Any]) -> None:
    """Tonight's reading of the trend rule, ticket or no ticket: what it would buy, what it would sell, and what the
    regime gate held back. Never fails the run - a missing record is a gap on a page, not a reason to lose the ticket."""
    try:
        from . import signals
        held_back = set(res.get("held_back") or [])
        px = res.get("prices") or {}
        rows = [{"code": e["code"], "action": "buy", "ref_price": px.get(e["code"]),
                 "reason": {"vol_ratio": e.get("vol_ratio"), "hi60": str(e["hi60"]) if e.get("hi60") is not None else None,
                            "ma200": str(e["ma200"]) if e.get("ma200") is not None else None}}
                for e in res.get("entry_rows") or [] if e["code"] not in held_back]
        rows += [{"code": c, "action": "hold_back", "ref_price": px.get(c),
                  "reason": {"why": "COMPOSITE under its 200-day average"}} for c in held_back]
        rows += [{"code": x["code"], "action": "sell", "ref_price": x.get("close"),
                  "reason": {"why": x.get("reason")}} for x in res.get("exit_rows") or []]
        if not rows:
            return
        gate = "" if res.get("regime") is None else (" · gate open" if res["regime"]["on"] else " · gate shut")
        signals.record(conn, "trend_small", res["run_date"], rows, book=book,
                       summary=f"{len(rows)} name(s) on the trend rule{gate}")
    except Exception:
        logger.exception("trend_book: the signal record failed (the ticket is unaffected)")


def render(res: dict[str, Any]) -> str:
    o = [f"# trend {res['variant']} - {res['book']} - {res['run_date']} | universe {res['universe']} | signals {res['signals']} | exits {res['exits']} | "
         f"NAV Rp {float(res['nav']):,.0f} | cash Rp {float(res['cash']):,.0f} -> after Rp {float(res['cash_after']):,.0f}"]
    if res.get("regime"):
        r = res["regime"]
        state = "on" if r["on"] else f"OFF -> {len(res['held_back'])} signal(s) held back: {', '.join(res['held_back']) or '-'}"
        o.append(f"  regime gate: {r['index']} {float(r['close']):,.0f} vs MA200 {float(r['sma']):,.0f} on {r['date']} -> {state}" if r.get("sma")
                 else f"  regime gate: {r['index']} has no 200-day history yet -> on")
    for ln in res["lines"]:
        o.append(f"  {ln['side']:4s} {ln['code']:<6} {int(ln['lots']):>6} lot @ {float(ln['limit_price']):>9,.0f}  {ln['reason']}")
    if not res["lines"]:
        o.append("  (no lines)")
    return "\n".join(o)


def is_trend_ticket(t: dict[str, Any]) -> bool:
    return t.get("mode") == "trend"

