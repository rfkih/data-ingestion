"""Pre-registered kill rules for the combined book - the conditions under which a sleeve is judged broken, written down
BEFORE the live results exist (Phase 0, operator 2026-09-26: "okay fase 0").

Why: every change to the live book so far was chosen on the same 2022-26 data it is judged on. From 2026-09-26 the book is
frozen (combo_book.FREEZE) and the only way a sleeve comes off is one of the rules below firing. A rule never trades and
never switches a sleeve off by itself - live settings are the operator's; a breach raises one actionable alert a day that
names the rule and the pre-registered action.

Rules (declared 2026-09-26, reference = study #386: the book as deployed, #348 re-run after the gap-fade eligibility
look-ahead fix found by the independent replication the same evening - no live trade existed yet):
  edge:<sleeve>   the mean return of the sleeve's CLOSED live trades sits below the 5th percentile of the mean of the same
                  number of trades drawn from #386's trades for that sleeve (bootstrap). "The live trades are not what the
                  backtest produces" - it cannot tell "no edge" from "unlucky" on a few trades, and it is not meant to.
                  Needs EDGE_MIN_N closed trades. Action: switch the sleeve off.
  fills:<sleeve>  share of the sleeve's live lines actually filled < 80 % after 10 lines (the backtest fills 100 %; the
                  return lives in a few large trades, so misses are not neutral). Action: fix execution before anything else.
  slip:<sleeve>   mean live fill vs the paper twin's fill on the same name, side and day > +50 bps (buys paying more =
                  positive) after 10 matched fills. Action: the sleeve is not executable at this broker as backtested.
  ic:ml           the 5-day model's weekly rank IC (predictions vs realised) negative in more than 60 % of the last 12
                  weeks (needs 8). Action: switch the ML sleeve off.
  dd:book         NAV drawdown from peak: warning past -25 %, breach past -30 % (FE planning numbers: -20..-25 % is a
                  normal 3-5 year drawdown, a zero-edge book's 3-year median is -29 %). Action: review the whole book.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import psycopg

from .card import _rows

WIB = ZoneInfo("Asia/Jakarta")
DECLARED = "2026-09-26"
REFERENCE_STUDY = 386          # #348 re-run 2026-09-26 after the gap-fade look-ahead fix (#348 superseded)
BACKTEST_STRATEGY = {"gap": "gapfade", "trend": "trend_small", "ml": "ml_rank"}      # idx.strategy_backtest_trade names
EDGE_MIN_N = {"gap": 20, "trend": 15, "ml": 20}
EDGE_PCT = 5.0
FILL_MIN_LINES, FILL_RATE_MIN = 10, 0.80
SLIP_MIN_N, SLIP_MAX_BPS = 10, 50.0
IC_WEEKS, IC_MIN_WEEKS, IC_NEG_MAX = 12, 8, 0.60
DD_WARN, DD_BREACH = -0.25, -0.30
BOOT = 4000
LOT = 100
ACTION = {"edge": "switch the sleeve off", "fills": "fix execution (fill every line) before judging the sleeve",
          "slip": "the sleeve is not executable as backtested - size it down or off", "ic": "switch the ML sleeve off",
          "dd": "review the whole book (pre-registered review trigger)"}


# ---------------------------------------------------------------------------------------------------------------- pure
def closed_trades(fills: list[dict[str, Any]], sleeve_of) -> list[dict[str, Any]]:
    """Pure. Filled lines in time order -> closed round trips per (sleeve, code), average cost with fees in, a partial sell
    closes its share of the cost. ret = proceeds after fees / cost with fees - 1."""
    held: dict[tuple[str, str], dict[str, Any]] = {}
    out: list[dict[str, Any]] = []
    for f in fills:
        key = (sleeve_of(f.get("flags")), f["code"])
        lots, px, fee = Decimal(f["lots"]), Decimal(f["price"]), Decimal(f.get("fee") or 0)
        p = held.get(key)
        if f["side"] == "buy":
            if p is None or p["lots"] <= 0:
                held[key] = p = {"lots": Decimal(0), "cost": Decimal(0), "d_in": f["trade_date"]}
            p["lots"] += lots
            p["cost"] += lots * LOT * px + fee
        elif p is not None and p["lots"] > 0:
            sold = min(lots, p["lots"])
            part = p["cost"] * sold / p["lots"]
            proceeds = sold * LOT * px - fee * (sold / lots)
            out.append({"sleeve": key[0], "code": key[1], "d_in": p["d_in"], "d_out": f["trade_date"],
                        "ret": float(proceeds / part - 1) if part else 0.0})
            p["lots"] -= sold
            p["cost"] -= part
    return out


def mean_band(ref: np.ndarray, n: int, pct: float = EDGE_PCT, boot: int = BOOT, seed: int = 0) -> float:
    """Pure. The ``pct`` percentile of the mean of ``n`` trades resampled from ``ref`` (fixed seed: the band is part of the rule)."""
    rng = np.random.default_rng(seed)
    return float(np.percentile(rng.choice(ref, (boot, n)).mean(axis=1), pct))


def percentile_of(ref: np.ndarray, n: int, value: float, boot: int = BOOT, seed: int = 0) -> float:
    rng = np.random.default_rng(seed)
    return float((rng.choice(ref, (boot, n)).mean(axis=1) < value).mean() * 100)


def edge_check(sleeve: str, live: list[float], ref: np.ndarray) -> dict[str, Any]:
    n, need = len(live), EDGE_MIN_N[sleeve]
    c = {"rule": f"edge:{sleeve}", "n": n, "need": need, "live_mean": float(np.mean(live)) if live else None,
         "ref_mean": float(ref.mean()) if len(ref) else None}
    if len(ref) == 0:
        return {**c, "status": "no_reference"}
    if n < need:
        return {**c, "status": "insufficient", "band": mean_band(ref, need)}
    band = mean_band(ref, n)
    return {**c, "band": band, "pct": percentile_of(ref, n, c["live_mean"]), "status": "breach" if c["live_mean"] < band else "ok"}


def fill_check(sleeve: str, lines: int, filled: int) -> dict[str, Any]:
    rate = filled / lines if lines else None
    c = {"rule": f"fills:{sleeve}", "n": lines, "need": FILL_MIN_LINES, "fill_rate": rate}
    if lines < FILL_MIN_LINES:
        return {**c, "status": "insufficient"}
    return {**c, "status": "breach" if rate < FILL_RATE_MIN else "ok"}


def slip_check(sleeve: str, vs_twin_bps: list[float]) -> dict[str, Any]:
    n = len(vs_twin_bps)
    c = {"rule": f"slip:{sleeve}", "n": n, "need": SLIP_MIN_N, "mean_bps": float(np.mean(vs_twin_bps)) if n else None}
    if n < SLIP_MIN_N:
        return {**c, "status": "insufficient"}
    return {**c, "status": "breach" if c["mean_bps"] > SLIP_MAX_BPS else "ok"}


def ic_check(weekly_ic: list[float]) -> dict[str, Any]:
    w = weekly_ic[-IC_WEEKS:]
    neg = sum(1 for x in w if x < 0) / len(w) if w else None
    c = {"rule": "ic:ml", "n": len(w), "need": IC_MIN_WEEKS, "neg_share": neg, "mean_ic": float(np.mean(w)) if w else None}
    if len(w) < IC_MIN_WEEKS:
        return {**c, "status": "insufficient"}
    return {**c, "status": "breach" if neg > IC_NEG_MAX else "ok"}


def dd_check(navs: list[float]) -> dict[str, Any]:
    peak, mdd, cur = 0.0, 0.0, 0.0
    for v in navs:
        peak = max(peak, v)
        cur = v / peak - 1 if peak else 0.0
        mdd = min(mdd, cur)
    st = "breach" if cur <= DD_BREACH else "warning" if cur <= DD_WARN else "ok"
    return {"rule": "dd:book", "n": len(navs), "need": 1, "dd_now": cur, "mdd": mdd, "status": st if navs else "insufficient"}


# ---------------------------------------------------------------------------------------------------------------- data
def reference_returns(conn: psycopg.Connection, sleeve: str, study: int = REFERENCE_STUDY) -> np.ndarray:
    rows = _rows(conn, "SELECT pnl / NULLIF(cost, 0) AS r FROM idx.strategy_backtest_trade WHERE study_id = %s AND strategy = %s",
                 (study, BACKTEST_STRATEGY[sleeve]), ["r"])
    return np.array([float(r["r"]) for r in rows if r["r"] is not None])


def book_fills(conn: psycopg.Connection, book: str) -> list[dict[str, Any]]:
    return _rows(conn, """
        SELECT l.code, l.side, l.flags, f.trade_date, l.filled_lots AS lots, f.price, f.fee
          FROM idx.ticket_line l JOIN idx.ticket t ON t.id = l.ticket_id JOIN idx.fill f ON f.id = l.fill_id
         WHERE t.book = %s AND l.fill_id IS NOT NULL AND l.filled_lots > 0 ORDER BY f.trade_date, f.id""", (book,),
                 ["code", "side", "flags", "trade_date", "lots", "price", "fee"])


def weekly_ic(conn: psycopg.Connection, horizon: str = "5d", weeks: int = IC_WEEKS) -> list[float]:
    """Mean over each ISO week of the daily cross-sectional rank IC of the model's realised predictions (oldest first)."""
    rows = _rows(conn, """
        SELECT date_trunc('week', d)::date AS w, avg(ic) AS ic FROM (
            SELECT (made_at AT TIME ZONE 'Asia/Jakarta')::date AS d,
                   corr(pr, rr) AS ic
              FROM (SELECT made_at, percent_rank() OVER (PARTITION BY made_at ORDER BY pred_ret) AS pr,
                           percent_rank() OVER (PARTITION BY made_at ORDER BY realized_ret) AS rr
                      FROM idx.ml_prediction
                     WHERE horizon = %s AND realized_ret IS NOT NULL AND pred_ret IS NOT NULL
                       AND made_at >= now() - make_interval(weeks => %s)) x
             GROUP BY 1 HAVING count(*) >= 20) y
         WHERE ic IS NOT NULL GROUP BY 1 ORDER BY 1""", (horizon, weeks + 2), ["w", "ic"])
    return [float(r["ic"]) for r in rows][-weeks:]


def evaluate(conn: psycopg.Connection, book: str, sc: dict[str, Any] | None = None) -> dict[str, Any]:
    """Every rule for one combo book -> {checks: [...], breaches: [...]}. ``sc`` = a scorecard already computed (fill
    counts and twin slippage come from it)."""
    from . import combo_book as cb
    sc = sc or cb.scorecard(conn, book, store=False)
    trades = closed_trades(book_fills(conn, book), cb.sleeve_of)
    checks: list[dict[str, Any]] = []
    for s in cb.SLEEVES:
        p = sc["sleeves"].get(s) or {}
        checks.append(edge_check(s, [t["ret"] for t in trades if t["sleeve"] == s], reference_returns(conn, s)))
        checks.append(fill_check(s, int(p.get("lines") or 0), int(p.get("filled") or 0)))
        checks.append(slip_check(s, list(p.get("vs_twin_bps") or [])))
    checks.append(ic_check(weekly_ic(conn)))
    navs = [float(r["nav"]) for r in _rows(conn, "SELECT nav FROM idx.book_nav WHERE book = %s ORDER BY trade_date", (book,), ["nav"])]
    checks.append(dd_check(navs))
    for c in checks:
        c["action"] = ACTION[c["rule"].split(":")[0]]
    return {"book": book, "declared": DECLARED, "reference_study": REFERENCE_STUDY, "checks": checks,
            "breaches": [c for c in checks if c["status"] == "breach"], "warnings": [c for c in checks if c["status"] == "warning"]}


def describe(c: dict[str, Any]) -> str:
    r, st = c["rule"], c["status"]
    if r.startswith("edge"):
        body = (f"mean {c['live_mean'] * 100:+.2f} % over {c['n']} trades vs band {c['band'] * 100:+.2f} % (pct {c['pct']:.0f})"
                if st in ("ok", "breach") else f"{c['n']}/{c['need']} closed trades")
    elif r.startswith("fills"):
        body = f"filled {c['fill_rate'] * 100:.0f} % of {c['n']} lines" if c["fill_rate"] is not None else "no lines"
    elif r.startswith("slip"):
        body = f"{c['mean_bps']:+.0f} bps vs twin over {c['n']} fills" if c["mean_bps"] is not None else "no matched fills"
    elif r.startswith("ic"):
        body = f"{c['neg_share'] * 100:.0f} % weeks negative, mean IC {c['mean_ic']:+.3f} ({c['n']} wk)" if c["n"] else "no realised weeks"
    else:
        body = f"drawdown now {c['dd_now'] * 100:.1f} %, worst {c['mdd'] * 100:.1f} %" if c["n"] else "no NAV"
    return f"{r:<13}{st:<13}{body}"


def render(ev: dict[str, Any]) -> str:
    o = [f"# kill rules {ev['book']} (declared {ev['declared']}, reference #{ev['reference_study']})"]
    o += [describe(c) for c in ev["checks"]]
    for c in ev["breaches"] + ev["warnings"]:
        o.append(f"-> {c['rule']}: {c['action']}")
    return "\n".join(o)


def alert(conn: psycopg.Connection, book: str, ev: dict[str, Any], d: date | None = None) -> int:
    """One actionable warning a day per book while any rule is breached (or the drawdown warning is on). -> rows raised."""
    from . import runlog
    hits = ev["breaches"] + ev["warnings"]
    if not hits:
        return 0
    d = d or datetime.now(WIB).date()
    msg = f"{book} kill rule {d}: " + "; ".join(f"{c['rule']} {c['status']} -> {c['action']}" for c in hits)
    runlog.alert(conn, "warning", f"risk:{book}", msg[:400], kind="risk", book=book,
                 payload={"date": str(d), "checks": hits}, dedupe_key=f"kill:{book}:{d}")
    return 1
