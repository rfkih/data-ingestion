"""The daily board - what each of the desk's five best strategies says today.

The operator runs more than one engine (value strict at IPOT, trend at Stockbit) and asked for one
screen that shows what each of them wants on a given day, so that choosing which to follow stays
theirs. This module computes each strategy's reading WITHOUT a book: no cash, no lots, no ticket,
only what the rule saw. The book-level version of the same question is the ticket, and it stays
where it is.

Which five, and why. The registry (``idx.strategy_state``) ranks every edge the desk has by ROI.
The board takes the top five that are BOTH equity-only and able to speak on any given day:

  1  gapfade        ROI rank 1   intraday, decided at the 09:00 open
  2  trend_small    ROI rank 3   nightly breakout scan, small-cap cut
  3  combined_book  ROI rank 4   value 50 / trend 50 - what the operator actually runs
  4  value_strict   ROI rank 6   annual, the only strategy with real fills
  5  trend_liq      ROI rank 7   the same trend rule on the liquid universe

Left out on purpose: ``book_gold`` (rank 5), ``ew3`` and ``gem_idr`` price gold and foreign
indices, which the desk does not trade - the operator runs equities only; ``trend_small_base_rate``
is a yardstick, not a rule. The overlays (``regime_gate``, ``ara_sell``, ``exec_timing``,
``regime_damper``, ``pit_growth_filter``) are not entry rules: where one touches a row it is
written into that row's reason, never shown as a sixth strategy.

Entries only. An exit depends on what a book holds and at what price, so it belongs to the ticket
and the book screen - a board that guessed at exits would be inventing positions. Every figure here
is computed from stored bars and the candidate run; nothing on this board is estimated.
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any

import psycopg

logger = logging.getLogger(__name__)

BOARD: list[dict[str, Any]] = [
    {"key": "gapfade", "roi_rank": 1, "label": "Gap-fade", "horizon": "one day",
     "rule": "buy the opening gap-down of -7 % or deeper, sell into the same close",
     "decided_at": "09:00 WIB"},
    {"key": "trend_small", "roi_rank": 3, "label": "Trend small", "horizon": "weeks",
     "rule": "60-day high, above the 200-day average, volume at least 1.5x the 20-day median; small-cap cut",
     "decided_at": "after the close"},
    {"key": "combined_book", "roi_rank": 4, "label": "Combined 50/50", "horizon": "mixed",
     "rule": "half the money on value strict, half on trend small, both under the regime gate",
     "decided_at": "after the close"},
    {"key": "value_strict", "roi_rank": 6, "label": "Value strict", "horizon": "a year",
     "rule": "cheapest fifth of the strict quality gate, equal weight, rebalanced each May",
     "decided_at": "May 1-10"},
    {"key": "trend_liq", "roi_rank": 7, "label": "Trend liquid", "horizon": "weeks",
     "rule": "the same trend rule on the liquid universe, without the small-cap cut",
     "decided_at": "after the close"},
]
BY_KEY = {e["key"]: e for e in BOARD}
KEYS = [e["key"] for e in BOARD]
REBALANCE_MONTH, REBALANCE_LAST_DAY = 5, 10


def _j(v: Any) -> Any:
    """JSON-safe: Decimals and dates become strings, so a reason dict survives ``Jsonb``."""
    if isinstance(v, Decimal | date):
        return str(v)
    if isinstance(v, dict):
        return {k: _j(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_j(x) for x in v]
    return v


def _regime(conn: psycopg.Connection, d: date) -> dict[str, Any] | None:
    """The index regime on ``d``, or None when the index has no history there."""
    from . import overlay
    try:
        r = overlay.index_regime(conn, d)
    except ValueError:
        return None
    return {"index": r["index_code"], "date": str(r["check_date"]), "close": str(r["close"]),
            "sma": (str(r["sma"]) if r.get("sma") is not None else None), "on": bool(r["on"]), "n": r.get("n")}


def trend_rows(conn: psycopg.Connection, d: date, variant: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """What the trend rule wants to buy on ``d``, before any book's cash. Names the gate refuses come
    back as ``hold_back`` rather than disappearing - the operator should see what was refused."""
    from . import trend_book as tb
    uni = tb.universe(conn, d, variant)
    if not uni:
        return [], {"universe": 0, "regime": None, "slots": tb.K,
                    "why": "no name cleared the liquidity floor on this date"}
    hist = tb.history(conn, sorted(uni), d)
    entries = tb.entry_signals(hist, d)
    reg = _regime(conn, d)
    taken, held = tb.hold_back(entries, True if reg is None else reg["on"])
    px = {c: r.get("close") for c, r in uni.items()}
    slot = (Decimal(100) / tb.K).quantize(Decimal("0.01"))
    rows: list[dict[str, Any]] = [
        {"code": e["code"], "action": "buy", "ref_price": px.get(e["code"]), "size_pct": slot,
         "reason": _j({"vol_ratio": e["vol_ratio"], "hi60": e["hi60"], "ma200": e["ma200"]})}
        for e in taken]
    rows += [{"code": c, "action": "hold_back", "ref_price": px.get(c), "size_pct": None,
              "reason": _j({"why": "regime gate: COMPOSITE under its 200-day average"})} for c in held]
    return rows, {"universe": len(uni), "regime": reg, "slots": tb.K,
                  "why": None if rows else "no name made a new 60-day high on volume"}


def gapfade_rows(conn: psycopg.Connection, d: date) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """The opening gap-down scan for ``d``. The scan itself reports whether the morning's prints were
    usable; when they were not, ``why`` says so and the board shows no names rather than a guess."""
    from . import gapfade as gf
    res = gf.scan(conn, d)
    meta: dict[str, Any] = {"ok": bool(res.get("ok")), "why": res.get("why"), "seen": res.get("seen"),
                            "prev_date": str(res["prev_date"]) if res.get("prev_date") else None,
                            "skipped": res.get("skipped"), "slots": gf.K, "gap_max": str(gf.GAP_MAX),
                            "provider": res.get("provider")}
    if not res.get("ok"):
        return [], meta
    picked = gf.pick(res.get("candidates") or [], gf.K)
    slot = (Decimal(100) / gf.K).quantize(Decimal("0.01"))
    rows = [{"code": c["code"], "action": "buy", "ref_price": c.get("offer") or c.get("open"), "size_pct": slot,
             "reason": _j({"gap_pct": (c["gap"] * 100).quantize(Decimal("0.1")), "open": c.get("open"),
                           "prev_close": c.get("prev_close"), "sector": c.get("sector")})}
            for c in picked]
    if not rows:
        meta["why"] = meta.get("why") or "no name opened -7 % or deeper"
    return rows, meta


def _candidate_rows(conn: psycopg.Connection, d: date) -> tuple[list[dict[str, Any]], date | None]:
    """The newest candidate run on or before ``d`` - the same read the ``/candidates`` route makes."""
    with conn.cursor() as cur:
        cur.execute("SELECT max(run_date) AS d FROM idx.candidate WHERE run_date <= %s", (d,))
        row = cur.fetchone()
        run_date = (dict(row) if isinstance(row, dict) else {"d": row[0]})["d"]
        if run_date is None:
            return [], None
        cur.execute(
            """
            SELECT c.run_date, c.code, l.name, c.rank, c.selected, c.score, c.price, c.mcap, c.ep, c.bp, c.dy,
                   c.ep_ttm, c.roe, c.der, c.np_yoy, c.gate_loose, c.gate_strict, c.strict_fails, c.warnings,
                   c.f20, c.v60, c.annual_period, c.ttm_basis, c.sector, c.mom, c.conv
              FROM idx.candidate c LEFT JOIN idx.listing l USING (code)
             WHERE c.run_date = %s ORDER BY c.rank
            """, (run_date,))
        return [dict(r) for r in cur.fetchall()], run_date


def value_rows(conn: psycopg.Connection, d: date, strategy: str = "strict") -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """The annual value list as it stands on ``d``. Outside the May window these are ``hold`` rows: the
    target the strategy would own, not an order for today. Calling them buys would misread the rule."""
    from . import strategies
    raw, run_date = _candidate_rows(conn, d)
    if not raw:
        return [], {"run_date": None, "why": "no candidate run on or before this date"}
    try:
        picked = strategies.pick(strategy, raw, size=None)
    except ValueError as e:
        return [], {"run_date": str(run_date), "why": str(e)}
    sel = [r for r in picked if r.get("selected")]
    in_window = d.month == REBALANCE_MONTH and d.day <= REBALANCE_LAST_DAY
    # The window still to come: this May while it is open or still ahead, next May once it has passed.
    passed = (d.month, d.day) > (REBALANCE_MONTH, REBALANCE_LAST_DAY)
    next_window = f"May {d.year + 1 if passed else d.year}"
    action = "buy" if in_window else "hold"
    rows = [{"code": r["code"], "action": action, "ref_price": r.get("price"),
             "size_pct": (r["weight"] * 100).quantize(Decimal("0.01")) if r.get("weight") is not None else None,
             "reason": _j({"rank": r.get("strategy_rank"), "ep": r.get("ep"), "bp": r.get("bp"),
                           "dy": r.get("dy"), "roe": r.get("roe"), "sector": r.get("sector"),
                           "why": None if in_window else "annual list; it only trades in the May window"})}
            for r in sel]
    return rows, {"run_date": str(run_date), "pool": len(picked), "names": len(sel),
                  "in_window": in_window, "next_window": next_window,
                  "why": None if rows else "the strict gate passed no name in this run"}


def combined_rows(conn: psycopg.Connection, d: date) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Value 50 / trend 50: both sleeves at half weight, each row tagged with the sleeve it came from."""
    v, vm = value_rows(conn, d)
    t, tm = trend_rows(conn, d, "small")
    rows: list[dict[str, Any]] = []
    for src, sleeve in ((v, "value 50 %"), (t, "trend 50 %")):
        for r in src:
            size = r.get("size_pct")
            rows.append({**r, "size_pct": ((size / 2).quantize(Decimal("0.01")) if size is not None else None),
                         "reason": {**(r.get("reason") or {}), "sleeve": sleeve}})
    why = None if rows else "neither sleeve signalled"
    return rows, {"value": vm, "trend": tm, "why": why}


def rows_for(conn: psycopg.Connection, key: str, d: date) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """One strategy's reading on ``d``."""
    if key == "gapfade":
        return gapfade_rows(conn, d)
    if key == "trend_small":
        return trend_rows(conn, d, "small")
    if key == "trend_liq":
        return trend_rows(conn, d, "all")
    if key == "value_strict":
        return value_rows(conn, d)
    if key == "combined_book":
        return combined_rows(conn, d)
    raise ValueError(f"not a board strategy: {key}")


def build(conn: psycopg.Connection, d: date) -> dict[str, Any]:
    """The whole board for one day. A strategy that fails to compute is reported as an error on its own
    card, never as an empty list - silence and "nothing today" must not look the same."""
    from . import registry
    out: list[dict[str, Any]] = []
    for e in BOARD:
        card: dict[str, Any] = {**e, "rows": [], "meta": {}, "error": None,
                                "books": registry.books_following(conn, e["key"])}
        try:
            rows, meta = rows_for(conn, e["key"], d)
            card["rows"], card["meta"] = rows, meta
        except Exception as exc:                                   # one broken engine must not blank the board
            logger.exception("signalboard: %s failed", e["key"])
            card["error"] = str(exc)
        card["by_action"] = _counts(card["rows"])
        out.append(card)
    return {"as_of": str(d), "strategies": out}


def _counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    by: dict[str, int] = {}
    for r in rows:
        by[r["action"]] = by.get(r["action"], 0) + 1
    return by


def record(conn: psycopg.Connection, d: date, *, alert: bool = True) -> dict[str, Any]:
    """Store the board in ``idx.strategy_signal`` under ``book=''`` - the bookless reading, which is
    what the daily screen shows. A book's own rows (written by the trend book) are left alone."""
    from . import signals
    res = build(conn, d)
    done = []
    for card in res["strategies"]:
        if card["error"] or not card["rows"]:
            done.append({"strategy": card["key"], "rows": 0, "error": card["error"]})
            continue
        summary = f"{card['label']}: " + ", ".join(f"{n} to {a.replace('_', ' ')}"
                                                   for a, n in sorted(card["by_action"].items()))
        done.append(signals.record(conn, card["key"], d, card["rows"], book="", summary=summary, alert=alert))
    return {"as_of": str(d), "recorded": done}


def render(res: dict[str, Any]) -> str:
    """The board on a terminal."""
    out = [f"# board {res['as_of']}"]
    for c in res["strategies"]:
        head = f"\n## {c['roi_rank']}. {c['label']} ({c['key']}) - {c['horizon']}, decided {c['decided_at']}"
        if c["books"]:
            head += "  [followed by " + ", ".join(b["book"] for b in c["books"]) + "]"
        out.append(head)
        out.append(f"   {c['rule']}")
        if c["error"]:
            out.append(f"   ERROR: {c['error']}")
            continue
        if not c["rows"]:
            out.append(f"   nothing today: {(c['meta'] or {}).get('why') or 'no signal'}")
            continue
        for r in c["rows"]:
            px = f"{float(r['ref_price']):,.0f}" if r.get("ref_price") is not None else "-"
            sz = f"{float(r['size_pct']):.1f}%" if r.get("size_pct") is not None else "   - "
            why = (r.get("reason") or {}).get("why") or (r.get("reason") or {}).get("sleeve") or ""
            out.append(f"   {r['action']:<9} {r['code']:<6} @ {px:>9}  {sz:>6}  {why}")
    return "\n".join(out)
