"""Track record of a live book against the profile its backtest promised - the desk's "is it proven yet?" scorecard.

Why this exists: the operator's rule (2026-09-23) is to add capital to a strategy only once it is proven. That rule is
worthless unless "proven" is a number, so this module turns it into one. It answers three questions and nothing else:

  how far along   closed round trips against the bar the research set (trend: >= 60 closed trades before a live book is
                  staged up, ``trend_book`` docstring; gapfade: >= 20 sessions of paper fills, ``gapfade`` docstring)
  same shape      hit rate, payoff and average net against the BACKTESTED profile, not against zero. A live book that
                  wins far MORE often than the backtest is as much a warning as one that wins less: it means the rule is
                  not doing what was measured.
  the one unknown gapfade only - the measured ``slip_bps`` (first-5-minute VWAP against the price the rule assumed).
                  The backtest cannot produce it; this is the number the paper book exists to collect.

Closed trades use the desk's average-cost convention (``book.apply_fill``), not FIFO: a round trip opens when a position
goes from zero lots and closes when it returns to zero. Partial sells stay inside the same round trip.

Honest by construction: it reads ``idx.fill`` and ``idx.decision`` only. It never estimates a missing fill and never
annualises a sample this small - a track record of 3 trades is reported as 3 trades, not as a CAGR.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Any

import psycopg

from . import book as bk
from .card import _rows

# The profile each live book must reproduce. Sources are the research reports, quoted exactly; do not re-tune them here.
PROFILES: dict[str, dict[str, Any]] = {
    # research/IDX_BEYOND_REGIME_2026-09-22.md, regime_gate | small (the deployed config: regime_filter=on)
    "trend": {"bar": 60, "unit": "closed trades", "hit": 0.44, "payoff": 2.74, "avg_net": 0.063, "hold_d": 26,
              "source": "menu 22 study #62, regime_gate|small"},
    # research/IDX_GAPFADE_2026-09-22.md, study #77, arm g7: 290 trades, hit 52 %, +300 bps a trade; paper bar 20 sessions.
    # (0.49 sat here for a day - that was the hit rate of a same-day bucket-A backtest, not #77's. Quote the study.)
    "gapfade": {"bar": 20, "unit": "sessions", "hit": 0.52, "payoff": None, "avg_net": 0.030, "hold_d": 0,
                "source": "menu 29b study #77, arm g7"},
}


def round_trips(fills: list[dict[str, Any]], sessions: Callable[[date, date], int] | None = None) -> list[dict[str, Any]]:
    """Pure. Every completed round trip in a book's fills, oldest first: a position opens when it leaves zero lots and
    closes when it returns to zero. Average-cost, mirroring ``book.apply_fill``; partial sells stay in the same trip, and
    a name bought again after a close starts a new one. ``fills`` must already be ordered by (trade_date, id).

    ``sessions(opened, closed)`` counts trading days between two dates. The research profiles quote hold in BARS
    (trend: 26), so a hold measured in calendar days overstates it by ~40 % (2026-09-23 review, #9); when the caller
    supplies the counter, each trip carries ``hold_sessions`` and the aggregate prefers it."""
    live: dict[str, dict[str, Any]] = {}
    out: list[dict[str, Any]] = []
    for f in fills:
        c = f["code"]
        ep = live.setdefault(c, {"pos": None, "cost": Decimal(0), "proceeds": Decimal(0),
                                 "opened": None, "n_buy": 0, "n_sell": 0})
        gross = Decimal(f["lots"]) * bk.LOT * Decimal(f["price"])
        fee = Decimal(f["fee"] or 0)
        if f["side"] == "buy":
            ep["cost"] += gross + fee
            ep["n_buy"] += 1
            if ep["opened"] is None:
                ep["opened"] = f["trade_date"]
        elif f["side"] == "sell":
            ep["proceeds"] += gross - fee
            ep["n_sell"] += 1
        new = bk.apply_fill(ep["pos"], f)
        ep["pos"] = new
        if new is not None and Decimal(new["lots"]) == 0 and ep["cost"] > 0:
            out.append({"code": c, "opened": ep["opened"], "closed": f["trade_date"],
                        "hold_d": (f["trade_date"] - ep["opened"]).days if ep["opened"] else None,
                        "hold_sessions": sessions(ep["opened"], f["trade_date"]) if (sessions and ep["opened"]) else None,
                        "cost": ep["cost"], "proceeds": ep["proceeds"],
                        "net": ep["proceeds"] - ep["cost"],
                        "net_pct": float(ep["proceeds"] / ep["cost"] - 1),
                        "buys": ep["n_buy"], "sells": ep["n_sell"]})
            live[c] = {"pos": new, "cost": Decimal(0), "proceeds": Decimal(0),
                       "opened": None, "n_buy": 0, "n_sell": 0}
    return out


def closed_trades(conn: psycopg.Connection, book: str) -> list[dict[str, Any]]:
    """Shell: the book's fills, in order, through ``round_trips``, with hold counted in trading days from ``idx.bar``."""
    fills = _rows(conn, """SELECT id, trade_date, code, side, lots, price, fee FROM idx.fill
                            WHERE book = %s ORDER BY trade_date, id""", (book,),
                  ["id", "trade_date", "code", "side", "lots", "price", "fee"])
    # bars strictly after the entry day up to and including the exit day = sessions held, matching the backtest's count
    return round_trips(fills, sessions=lambda a, b: max(0, len(bk._trading_days(conn, a, b)) - 1))


def slip_rows(conn: psycopg.Connection, book: str) -> list[dict[str, Any]]:
    """Measured execution context recorded by the gapfade entry job (``idx.decision.refs->'exec'``)."""
    rows = _rows(conn, """SELECT ts, refs FROM idx.decision
                           WHERE book = %s AND refs ? 'exec' ORDER BY ts""",
                 (book,), ["ts", "refs"])
    out = []
    for r in rows:
        for e in (r["refs"] or {}).get("exec") or []:
            if e.get("slip_bps") is not None:
                out.append({"at": r["ts"], "code": e.get("code"), "slip_bps": float(e["slip_bps"]),
                            "share": e.get("share_of_window"), "prints5": e.get("prints5")})
    return out


def _agg(trades: list[dict[str, Any]]) -> dict[str, Any]:
    if not trades:
        return {"n": 0, "hit": None, "payoff": None, "avg_net": None, "hold_d": None}
    nets = [t["net_pct"] for t in trades]
    wins = [x for x in nets if x > 0]
    losses = [-x for x in nets if x < 0]
    # prefer sessions (what the research profiles quote); calendar days only when no counter was supplied
    sess = [t["hold_sessions"] for t in trades if t.get("hold_sessions") is not None]
    holds = sess or [t["hold_d"] for t in trades if t.get("hold_d") is not None]
    return {"n": len(trades), "hit": len(wins) / len(nets),
            "payoff": (sum(wins) / len(wins)) / (sum(losses) / len(losses)) if wins and losses else None,
            "avg_net": sum(nets) / len(nets),
            "hold_d": sum(holds) / len(holds) if holds else None,
            "hold_unit": "sessions" if sess else "days"}


def scorecard(conn: psycopg.Connection, book: str) -> dict[str, Any]:
    """The book's live record against the profile its research promised."""
    b = bk.get_book(conn, book)
    rule = (b.get("rule") or "annual").lower()
    prof = PROFILES.get(rule)
    trades = closed_trades(conn, book)
    live = _agg(trades)
    # read-only: count what the book holds now, never bk.rebuild_positions (that DELETEs and rewrites idx.position)
    open_n = len(_rows(conn, "SELECT code FROM idx.position WHERE book = %s AND lots > 0", (book,), ["code"]))
    sc: dict[str, Any] = {"book": book, "label": b.get("label"), "rule": rule, "profile": prof, "live": live,
                          "trades": trades, "open_positions": open_n,
                          "halted": bk.is_halted(b), "archived": b.get("archived_at") is not None}
    if rule == "gapfade":
        sessions = sorted({t["closed"] for t in trades})
        sc["sessions"] = len(sessions)
        slips = slip_rows(conn, book)
        sc["slip"] = {"n": len(slips),
                      "mean": sum(s["slip_bps"] for s in slips) / len(slips) if slips else None,
                      "worst": max((s["slip_bps"] for s in slips), default=None)}
        sc["progress"] = (len(sessions), prof["bar"]) if prof else None
    else:
        sc["progress"] = (live["n"], prof["bar"]) if prof else None
    return sc


def _pct(x: float | None, d: int = 0) -> str:
    return "-" if x is None else f"{x * 100:.{d}f}%"


def render(sc: dict[str, Any]) -> str:
    """One short block, readable on a phone push."""
    p, live = sc.get("profile"), sc["live"]
    head = f"{sc['label'] or sc['book']} ({sc['rule']})"
    if sc["halted"]:
        head += " - HALTED"
    if not p:
        return f"{head}\n  {live['n']} closed, avg {_pct(live['avg_net'], 1)} - no research profile for this rule"
    done, bar = sc["progress"]
    lines = [head, f"  bukti: {done}/{bar} {p['unit']}" + ("  [AMBANG TERCAPAI]" if done >= bar else "")]
    if live["n"]:
        extra = f" - payoff {live['payoff']:.2f} (target {p['payoff']:.2f})" if live["payoff"] and p["payoff"] else ""
        lines.append(f"  hit {_pct(live['hit'])} (target {_pct(p['hit'])}){extra}"
                     f" - avg {_pct(live['avg_net'], 1)} (target {_pct(p['avg_net'], 1)})")
    else:
        lines.append("  belum ada trade tertutup")
    if sc["rule"] == "gapfade" and sc.get("slip"):
        s = sc["slip"]
        tail = f" mean {s['mean']:+.0f} bps, terburuk {s['worst']:+.0f} bps" if s["n"] else " (belum ada entry)"
        lines.append(f"  slip terukur: n={s['n']}{tail}")
    lines.append(f"  posisi terbuka: {sc['open_positions']}")
    return "\n".join(lines)
