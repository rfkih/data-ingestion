"""Book-level overlays on top of the strategy (research/IDX_TREND_OVERLAY_2026-09-13.md), both off by default:

  regime_filter  the book sits in cash while the COMPOSITE is under its 200-day average. Checked on the first trading
                 day of each month after the close: when the regime turns off a "cash" ticket sells everything; when it
                 turns on a "rebalance" ticket buys the book's list back. An annual rebalance while the regime is off
                 becomes a cash ticket.
  entry_gate     at a rebalance, a listed name under its own 200-day average is not bought (held back, its slot stays in
                 cash) unless it is oversold (14-day RSI at or under 30); at each monthly check the held-back names that
                 have crossed above, or are oversold, are bought, one slot each, with an "entry" ticket.
  trend_exit     at each monthly check, a held name that was above its 200-day average at the previous check and is
                 below it now (a trend break) is sold with an "exits" ticket. With entry_gate this is the asymmetric rule
                 of research/IDX_ASYMMETRIC_2026-09-13.md: sell the break, buy the oversold.
  cash buffer    cash_floor_pct of NAV stays in cash at every rebalance; stress_cash_pct replaces it while the stress
                 detector (stress_rule 'ma' or 'any2') is on. The monthly check records the four stress signals and, when
                 the book's cash target moves by more than 5 points, issues a rebalance ticket at the new target
                 (research/IDX_CASH_BUFFER_2026-09-14.md).

The rules themselves are pure (``regime_from_closes``, ``gate``); the rest reads the tables and builds tickets, which the
operator (live) or the paper fill (paper) then works. Every check is recorded in idx.regime_check.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from itertools import pairwise
from typing import Any

import psycopg
import psycopg.types.json

from . import book as bk
from . import runlog

SMA_DAYS = 200
INDEX = "COMPOSITE"
RSI_N = 14
RSI_MAX = Decimal(30)
VOL_N, VOL_WINDOW, VOL_MIN, VOL_Q = 20, 750, 250, 0.8      # realised-vol spike: 20-day vol above its trailing 3-year 80th percentile
DD_LIMIT = -0.10                                             # index more than 10 % under its 252-day high
BREADTH_MIN = 0.40                                           # fewer than 40 % of names above their own 200-day average
STRESS_RULES = ("ma", "any2")
CASH_MOVE_MIN = Decimal("0.05")                              # re-issue a ticket only when the cash target moves 5+ points


def _rows(conn: psycopg.Connection, sql: str, params: tuple, cols: list[str]) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        out = cur.fetchall()
    return [r if isinstance(r, dict) else dict(zip(cols, r, strict=True)) for r in out]


# ---------------------------------------------------------------------------
# pure rules
# ---------------------------------------------------------------------------
def regime_from_closes(closes: list[Any], days: int = SMA_DAYS) -> dict[str, Any]:
    """Oldest-first closes -> {close, sma, on}. Without ``days`` closes there is no average and the regime is on (no
    history is not a reason to sit out)."""
    if not closes:
        raise ValueError("no closes")
    last = Decimal(str(closes[-1]))
    if len(closes) < days:
        return {"close": last, "sma": None, "on": True, "n": len(closes)}
    window = [Decimal(str(c)) for c in closes[-days:]]
    sma = sum(window, Decimal(0)) / len(window)
    return {"close": last, "sma": sma, "on": last > sma, "n": len(closes)}


def take_profit_hits(positions: list[dict[str, Any]], prices: dict[str, Any], pct: Any) -> dict[str, str]:
    """Pure. Held names whose last close is at least ``pct`` % above their average purchase price -> {code: reason}."""
    if pct is None:
        return {}
    bar = Decimal(str(pct)) / 100
    out = {}
    for p in positions:
        c, avg = p["code"], p.get("avg_price")
        px = prices.get(c)
        if avg is None or px is None or Decimal(str(avg)) <= 0:
            continue
        gain = Decimal(str(px)) / Decimal(str(avg)) - 1
        if gain >= bar:
            out[c] = f"take profit: +{100 * gain:.0f} % over the purchase price (rule +{Decimal(str(pct)):.0f} %)"
    return out


def rsi_from_closes(closes: list[Any], n: int = RSI_N) -> Decimal | None:
    """Pure. Wilder's RSI over the last ``n`` changes of an oldest-first close series; None without enough history."""
    xs = [Decimal(str(c)) for c in closes]
    if len(xs) < n + 1:
        return None
    gains, losses = [], []
    for a, b in pairwise(xs):
        d = b - a
        gains.append(d if d > 0 else Decimal(0))
        losses.append(-d if d < 0 else Decimal(0))
    up = sum(gains[:n], Decimal(0)) / n
    dn = sum(losses[:n], Decimal(0)) / n
    for g, lo in zip(gains[n:], losses[n:], strict=True):                 # Wilder smoothing
        up = (up * (n - 1) + g) / n
        dn = (dn * (n - 1) + lo) / n
    if dn == 0:
        return Decimal(100)
    rs = up / dn
    return Decimal(100) - Decimal(100) / (1 + rs)


def gate(targets: dict[str, Any], trend: dict[str, dict[str, Any]], held: set[str], rsi: dict[str, Any] | None = None) -> list[str]:
    """Pure. The names to hold back at a rebalance: listed, not already held, under their 200-day average, and not
    oversold (RSI over 30, or no RSI). A name without an average (young listing) is bought."""
    out = []
    for c in targets:
        if c in held:
            continue
        t = trend.get(c)
        if t is None or t["sma"] is None or t["on"]:
            continue
        r = (rsi or {}).get(c)
        if r is not None and Decimal(str(r)) <= RSI_MAX:
            continue                                                     # oversold: buy it, do not hold it back
        out.append(c)
    return out


def trend_breaks(prev: dict[str, dict[str, Any]], now: dict[str, dict[str, Any]], held: set[str]) -> dict[str, str]:
    """Pure. Held names that were above their average at the previous check and are below it now -> {code: reason}."""
    out = {}
    for c in sorted(held):
        p, q = prev.get(c), now.get(c)
        if p and q and p["sma"] is not None and q["sma"] is not None and p["on"] and not q["on"]:
            out[c] = f"trend break: crossed under its 200-day average ({q['close']:.0f} vs {q['sma']:.0f})"
    return out


# ---------------------------------------------------------------------------
# signals from the tables
# ---------------------------------------------------------------------------
def stress_from_series(closes: list[Any], breadth: float | None) -> dict[str, Any]:
    """Pure. Oldest-first index closes (up to ~1000 bars) and today's breadth -> the four stress signals and their inputs."""
    import math
    xs = [float(c) for c in closes]
    n = len(xs)
    close = xs[-1] if n else float("nan")
    sma = sum(xs[-SMA_DAYS:]) / SMA_DAYS if n >= SMA_DAYS else None
    vol20 = vol_p80 = None
    if n >= VOL_N + 1:
        rets = [math.log(b / a) for a, b in pairwise(xs) if a > 0 and b > 0]
        vols = []
        for i in range(VOL_N, len(rets) + 1):
            w = rets[i - VOL_N:i]
            m = sum(w) / VOL_N
            vols.append(math.sqrt(sum((x - m) ** 2 for x in w) / (VOL_N - 1)) * math.sqrt(252))
        vol20 = vols[-1]
        hist = vols[-VOL_WINDOW:]
        if len(hist) >= VOL_MIN:
            vol_p80 = sorted(hist)[min(len(hist) - 1, round(VOL_Q * (len(hist) - 1)))]
    hi = max(xs[-252:]) if n >= 120 else None
    dd = close / hi - 1 if hi else None
    s = {"ma": bool(sma is not None and close < sma), "vol": bool(vol20 is not None and vol_p80 is not None and vol20 > vol_p80),
         "dd": bool(dd is not None and dd < DD_LIMIT), "breadth": bool(breadth is not None and breadth < BREADTH_MIN)}
    return {"close": close, "sma": sma, "vol20": vol20, "vol_p80": vol_p80, "dd": dd, "breadth": breadth, "signals": s, "n_on": sum(s.values())}


def stress_on(sig: dict[str, Any], rule: str) -> bool:
    """Pure. Whether the detector fires under the book's rule."""
    if rule == "any2":
        return int(sig.get("n_on", 0)) >= 2
    return bool(sig["signals"]["ma"])


def cash_target(book: dict[str, Any], stressed: bool) -> Decimal:
    """Pure. The fraction of NAV the book keeps in cash: the stress level while the detector is on, else the floor."""
    floor = Decimal(str(book.get("cash_floor_pct") or 0)) / 100
    stress = Decimal(str(book.get("stress_cash_pct") or 0)) / 100
    return max(floor, stress) if stressed and stress > 0 else floor


def uses_cash_buffer(book: dict[str, Any]) -> bool:
    return bool(Decimal(str(book.get("cash_floor_pct") or 0)) > 0 or Decimal(str(book.get("stress_cash_pct") or 0)) > 0)


def breadth_asof(conn: psycopg.Connection, D: date) -> float | None:
    """Share of names with a full 200-bar history whose last adjusted close is above their own 200-day average."""
    rows = _rows(conn, """
        WITH last AS (
            SELECT code, close * adj_factor AS c, row_number() OVER (PARTITION BY code ORDER BY trade_date DESC) AS rn
              FROM idx.bar WHERE source IN ('idx', 'yahoo') AND trade_date <= %s AND close IS NOT NULL AND close > 0),
        agg AS (SELECT code, count(*) AS n, avg(c) AS sma, max(CASE WHEN rn = 1 THEN c END) AS last_c FROM last WHERE rn <= %s GROUP BY code)
        SELECT count(*) FILTER (WHERE n = %s) AS n_valid, count(*) FILTER (WHERE n = %s AND last_c > sma) AS n_above FROM agg""",
                 (D, SMA_DAYS, SMA_DAYS, SMA_DAYS), ["n_valid", "n_above"])
    if not rows or not rows[0]["n_valid"]:
        return None
    return float(rows[0]["n_above"]) / float(rows[0]["n_valid"])


def stress_signals(conn: psycopg.Connection, D: date) -> dict[str, Any]:
    rows = _rows(conn, "SELECT trade_date AS d, close FROM idx.index_daily WHERE index_code = %s AND trade_date <= %s ORDER BY trade_date DESC LIMIT %s",
                 (INDEX, D, VOL_WINDOW + VOL_N + 260), ["d", "close"])
    if not rows:
        raise ValueError(f"no {INDEX} history on or before {D}")
    rows.reverse()
    sig = stress_from_series([r["close"] for r in rows], breadth_asof(conn, D))
    sig.update({"check_date": rows[-1]["d"], "index_code": INDEX})
    return sig


STRESS_COLS = ["check_date", "index_code", "close", "sma", "vol20", "vol_p80", "dd_pct", "breadth_pct", "s_ma", "s_vol", "s_dd", "s_breadth", "n_on", "created_at"]


def record_stress(conn: psycopg.Connection, s: dict[str, Any]) -> None:
    g = s["signals"]
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO idx.stress_check (check_date, index_code, close, sma, vol20, vol_p80, dd_pct, breadth_pct, s_ma, s_vol, s_dd, s_breadth, n_on)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (check_date) DO UPDATE SET close = EXCLUDED.close, sma = EXCLUDED.sma, vol20 = EXCLUDED.vol20, vol_p80 = EXCLUDED.vol_p80,
                           dd_pct = EXCLUDED.dd_pct, breadth_pct = EXCLUDED.breadth_pct, s_ma = EXCLUDED.s_ma, s_vol = EXCLUDED.s_vol, s_dd = EXCLUDED.s_dd,
                           s_breadth = EXCLUDED.s_breadth, n_on = EXCLUDED.n_on""",
                    (s["check_date"], s["index_code"], s["close"], s["sma"], s["vol20"], s["vol_p80"], s["dd"], s["breadth"],
                     g["ma"], g["vol"], g["dd"], g["breadth"], s["n_on"]))
    conn.commit()


def _to_stress(row: dict[str, Any]) -> dict[str, Any]:
    f = lambda v: None if v is None else float(v)  # noqa: E731
    return {"check_date": row["check_date"], "index_code": row["index_code"], "close": f(row["close"]), "sma": f(row["sma"]), "vol20": f(row["vol20"]),
            "vol_p80": f(row["vol_p80"]), "dd": f(row["dd_pct"]), "breadth": f(row["breadth_pct"]),
            "signals": {"ma": bool(row["s_ma"]), "vol": bool(row["s_vol"]), "dd": bool(row["s_dd"]), "breadth": bool(row["s_breadth"])}, "n_on": int(row["n_on"])}


def latest_stress(conn: psycopg.Connection) -> dict[str, Any] | None:
    rows = _rows(conn, f"SELECT {', '.join(STRESS_COLS)} FROM idx.stress_check ORDER BY check_date DESC LIMIT 1", (), STRESS_COLS)
    return _to_stress(rows[0]) if rows else None


def stress_history(conn: psycopg.Connection, limit: int = 24) -> list[dict[str, Any]]:
    rows = _rows(conn, f"SELECT {', '.join(STRESS_COLS)} FROM idx.stress_check ORDER BY check_date DESC LIMIT %s", (limit,), STRESS_COLS)
    return [_to_stress(r) for r in rows]


def index_regime(conn: psycopg.Connection, D: date) -> dict[str, Any]:
    rows = _rows(conn, "SELECT trade_date AS d, close FROM idx.index_daily WHERE index_code = %s AND trade_date <= %s ORDER BY trade_date DESC LIMIT %s",
                 (INDEX, D, SMA_DAYS), ["d", "close"])
    if not rows:
        raise ValueError(f"no {INDEX} history on or before {D}")
    rows.reverse()
    r = regime_from_closes([x["close"] for x in rows])
    r.update({"check_date": rows[-1]["d"], "index_code": INDEX})
    return r


def name_trend(conn: psycopg.Connection, D: date, codes: list[str]) -> dict[str, dict[str, Any]]:
    """Per code: {close, sma, on} on the adjusted close series, as of D."""
    if not codes:
        return {}
    rows = _rows(conn, """
        SELECT code, trade_date AS d, c FROM (
            SELECT code, trade_date, close * adj_factor AS c, row_number() OVER (PARTITION BY code ORDER BY trade_date DESC) AS rn
              FROM idx.bar WHERE source IN ('idx', 'yahoo') AND code = ANY(%s) AND trade_date <= %s AND close IS NOT NULL) t
         WHERE rn <= %s ORDER BY code, trade_date""", (list(codes), D, SMA_DAYS), ["code", "d", "c"])
    by: dict[str, list[Any]] = {}
    for r in rows:
        by.setdefault(r["code"], []).append(r["c"])
    return {c: regime_from_closes(v) for c, v in by.items() if v}


def rsi14(conn: psycopg.Connection, D: date, codes: list[str]) -> dict[str, Decimal]:
    """Per code, the 14-day RSI on the adjusted close as of D (last 60 bars are plenty)."""
    if not codes:
        return {}
    rows = _rows(conn, """
        SELECT code, trade_date AS d, c FROM (
            SELECT code, trade_date, close * adj_factor AS c, row_number() OVER (PARTITION BY code ORDER BY trade_date DESC) AS rn
              FROM idx.bar WHERE source IN ('idx', 'yahoo') AND code = ANY(%s) AND trade_date <= %s AND close IS NOT NULL) t
         WHERE rn <= 60 ORDER BY code, trade_date""", (list(codes), D), ["code", "d", "c"])
    by: dict[str, list[Any]] = {}
    for r in rows:
        by.setdefault(r["code"], []).append(r["c"])
    out = {}
    for c, v in by.items():
        r = rsi_from_closes(v)
        if r is not None:
            out[c] = r
    return out


def previous_check_date(conn: psycopg.Connection, D: date) -> date | None:
    """The first trading day of the month before D's month (the previous monthly check)."""
    first = D.replace(day=1)
    prev_month_last = first - timedelta(days=1)
    rows = _rows(conn, "SELECT min(trade_date) AS d FROM idx.bar WHERE source IN ('idx', 'yahoo') AND trade_date >= %s AND trade_date < %s",
                 (prev_month_last.replace(day=1), first), ["d"])
    return rows[0]["d"] if rows and rows[0]["d"] else None


def first_trading_day_of_month(conn: psycopg.Connection, D: date) -> bool:
    rows = _rows(conn, "SELECT min(trade_date) AS d FROM idx.bar WHERE source IN ('idx', 'yahoo') AND trade_date >= %s AND trade_date <= %s",
                 (D.replace(day=1), D), ["d"])
    return bool(rows and rows[0]["d"] == D)


# ---------------------------------------------------------------------------
# the record of checks
# ---------------------------------------------------------------------------
COLS = ["check_date", "index_code", "close", "sma", "regime_on", "detail", "created_at"]


def record(conn: psycopg.Connection, r: dict[str, Any]) -> None:
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO idx.regime_check (check_date, index_code, close, sma, regime_on, detail)
                       VALUES (%s, %s, %s, %s, %s, %s)
                       ON CONFLICT (check_date) DO UPDATE SET close = EXCLUDED.close, sma = EXCLUDED.sma, regime_on = EXCLUDED.regime_on,
                           detail = EXCLUDED.detail""",
                    (r["check_date"], r["index_code"], r["close"], r["sma"], r["on"], psycopg.types.json.Jsonb({"n": r.get("n")})))
    conn.commit()


def _to_regime(row: dict[str, Any]) -> dict[str, Any]:
    return {"check_date": row["check_date"], "index_code": row["index_code"], "close": row["close"], "sma": row["sma"], "on": bool(row["regime_on"])}


def latest(conn: psycopg.Connection, before: date | None = None) -> dict[str, Any] | None:
    rows = _rows(conn, "SELECT check_date, index_code, close, sma, regime_on, detail, created_at FROM idx.regime_check "
                       "WHERE (%s::date IS NULL OR check_date < %s) ORDER BY check_date DESC LIMIT 1", (before, before), COLS)
    return _to_regime(rows[0]) if rows else None


def history(conn: psycopg.Connection, limit: int = 24) -> list[dict[str, Any]]:
    rows = _rows(conn, "SELECT check_date, index_code, close, sma, regime_on, detail, created_at FROM idx.regime_check ORDER BY check_date DESC LIMIT %s",
                 (limit,), COLS)
    return [_to_regime(r) for r in rows]


def current_list(conn: psycopg.Connection, book: str) -> dict[str, Any] | None:
    """The book's list: the latest rebalance ticket that was not cancelled (its weights and what was held back)."""
    rows = _rows(conn, "SELECT id, run_date, params FROM idx.ticket WHERE book = %s AND mode = 'rebalance' AND status <> 'cancelled' ORDER BY id DESC LIMIT 1",
                 (book,), ["id", "run_date", "params"])
    if not rows:
        return None
    p = rows[0]["params"] or {}
    return {"ticket_id": rows[0]["id"], "run_date": rows[0]["run_date"], "weights": p.get("weights") or {}, "targets": p.get("targets") or [],
            "held_back": p.get("held_back") or []}


# ---------------------------------------------------------------------------
# the monthly check
# ---------------------------------------------------------------------------
def monthly_check(conn: psycopg.Connection, D: date, build: bool = True) -> dict[str, Any]:
    """Record the regime as of D and, for every book with an overlay on, build the ticket it calls for. ``build=False``
    only reports. One report per book: action in {None, 'cash', 're-entry', 'entry'}."""
    from . import ticket as tk

    r = index_regime(conn, D)
    prev = latest(conn, r["check_date"])
    if build:
        record(conn, r)
    report: dict[str, Any] = {"regime": r, "previous_on": prev["on"] if prev else None, "books": [], "stress": None}
    books = [row["book"] for row in _rows(conn, "SELECT book FROM idx.book ORDER BY book", (), ["book"])]
    metas = {b: bk.get_book(conn, b) for b in books}
    stress = None
    if any(uses_cash_buffer(m) for m in metas.values()):
        stress = stress_signals(conn, D)
        report["stress"] = stress
        if build:
            record_stress(conn, stress)
    for b in books:
        meta = metas[b]
        if not (meta.get("regime_filter") or meta.get("entry_gate") or meta.get("take_profit_pct") or meta.get("trend_exit") or uses_cash_buffer(meta)):
            continue
        snap = bk.snapshot(conn, b)
        positions = snap["positions"]
        held = {p["code"] for p in positions}
        entry: dict[str, Any] = {"book": b, "action": None, "ticket": None, "names": []}
        report["books"].append(entry)
        if stress is not None and uses_cash_buffer(meta):
            want = cash_target(meta, stress_on(stress, meta.get("stress_rule") or "ma"))
            nav = Decimal(str(snap.get("nav") or 0))
            have = (Decimal(str(meta["cash"])) / nav) if nav > 0 else None
            entry["cash_target"] = str(want)
            if have is not None and abs(have - want) > CASH_MOVE_MIN:
                entry["action"] = f"cash {round(100 * float(have))}% -> {round(100 * float(want))}%"
                if build:
                    res = tk.build(conn, b, mode="rebalance", run_date=D)
                    tid = tk.store(conn, res, notes=f"cash target {round(100 * float(want))} % on {stress['check_date']} "
                                                    f"({'stress on' if stress_on(stress, meta.get('stress_rule') or 'ma') else 'stress off'}, {stress['n_on']} of 4 signals)")
                    entry["ticket"] = tid
                    runlog.alert(conn, "warning" if want > have else "info", f"ticket:{b}",
                                 f"cash target {round(100 * float(want))} % of NAV ({stress['n_on']} of 4 stress signals on, rule {meta.get('stress_rule') or 'ma'}): "
                                 f"ticket #{tid} moves the {b} book from {round(100 * float(have))} % cash. Work it at the next open.")
        if meta.get("regime_filter"):
            if not r["on"] and held:
                entry["action"] = "cash"
                if build:
                    res = tk.build(conn, b, mode="cash", run_date=D)
                    entry["ticket"] = tk.store(conn, res, notes=f"regime off on {r['check_date']}: to cash")
                    runlog.alert(conn, "warning", f"ticket:{b}", f"regime OFF ({INDEX} {r['close']:.0f} under its 200-day average "
                                 f"{r['sma']:.0f}): ticket #{entry['ticket']} sells the {b} book to cash")
            elif r["on"] and not held and prev is not None and not prev["on"]:
                entry["action"] = "re-entry"
                if build:
                    res = tk.build(conn, b, mode="rebalance", run_date=D)
                    entry["ticket"] = tk.store(conn, res, notes=f"regime on again on {r['check_date']}: back into the list")
                    runlog.alert(conn, "info", f"ticket:{b}", f"regime ON ({INDEX} {r['close']:.0f} above its 200-day average "
                                 f"{r['sma']:.0f}): ticket #{entry['ticket']} buys the {b} book back")
            if not r["on"]:
                continue
        if meta.get("take_profit_pct") and held:
            px = {r["code"]: r["close"] for r in _rows(conn, """SELECT DISTINCT ON (code) code, close FROM idx.bar
                       WHERE code = ANY(%s) AND source IN ('idx', 'yahoo') AND trade_date <= %s ORDER BY code, trade_date DESC""", (sorted(held), D), ["code", "close"])}
            hits = take_profit_hits(positions, px, meta["take_profit_pct"])
            if hits:
                entry["action"] = (entry["action"] + "+" if entry["action"] else "") + "take-profit"
                entry["names"] = entry["names"] + sorted(hits)
                if build:
                    res = tk.build(conn, b, mode="exits", run_date=D, exits=hits)
                    tid = tk.store(conn, res, notes=f"take profit on {r['check_date']}: {', '.join(sorted(hits))}")
                    entry["ticket"] = tid if entry["ticket"] is None else entry["ticket"]
                    runlog.alert(conn, "info", f"ticket:{b}", f"take profit: {', '.join(sorted(hits))} at least {meta['take_profit_pct']:.0f} % over "
                                 f"their purchase price; ticket #{tid} sells them from the {b} book")
        if meta.get("trend_exit") and held:
            prev_d = previous_check_date(conn, D)
            if prev_d is not None:
                breaks = trend_breaks(name_trend(conn, prev_d, sorted(held)), name_trend(conn, D, sorted(held)), held)
                if breaks:
                    entry["action"] = (entry["action"] + "+" if entry["action"] else "") + "trend-exit"
                    entry["names"] = entry["names"] + sorted(breaks)
                    if build:
                        res = tk.build(conn, b, mode="exits", run_date=D, exits=breaks)
                        tid = tk.store(conn, res, notes=f"trend exit on {r['check_date']}: {', '.join(sorted(breaks))} crossed under their 200-day average")
                        entry["ticket"] = tid if entry["ticket"] is None else entry["ticket"]
                        runlog.alert(conn, "warning", f"ticket:{b}", f"trend exit: {', '.join(sorted(breaks))} crossed under their 200-day "
                                     f"average; ticket #{tid} sells them from the {b} book. Work it at the next open: the signal is the {r['check_date']} close.")
                    held = held - set(breaks)
        if meta.get("entry_gate"):
            cur = current_list(conn, b)
            back = [c for c in (cur or {}).get("held_back", []) if c not in held]
            if back:
                trend = name_trend(conn, D, back)
                rsi = rsi14(conn, D, back)
                ready = [c for c in back if (c in trend and trend[c]["on"]) or (c in rsi and rsi[c] <= RSI_MAX)]
                if ready:
                    entry["action"], entry["names"] = "entry", ready
                    if build:
                        res = tk.build(conn, b, mode="entry", run_date=D, entrants=ready)
                        entry["ticket"] = tk.store(conn, res, notes=f"entry gate on {r['check_date']}: {', '.join(ready)} crossed above their 200-day average")
                        runlog.alert(conn, "info", f"ticket:{b}", f"entry gate: {', '.join(ready)} crossed above their 200-day average or are "
                                     f"oversold; ticket #{entry['ticket']} buys them into the {b} book. Work it at the next open.")
    return report


def render(report: dict[str, Any]) -> str:
    r = report["regime"]
    sma = f"{r['sma']:,.0f}" if r["sma"] is not None else "n/a"
    o = [f"# regime check {r['check_date']}: {INDEX} {r['close']:,.0f} vs 200-day average {sma} -> {'ON (invested)' if r['on'] else 'OFF (cash)'}"
         + (f"  (previous check: {'on' if report['previous_on'] else 'off'})" if report["previous_on"] is not None else "")]
    for b in report["books"]:
        what = b["action"] or "nothing to do"
        if b["names"]:
            what += ": " + ", ".join(b["names"])
        if b["ticket"]:
            what += f" -> ticket #{b['ticket']}"
        o.append(f"  {b['book']:6s} {what}")
    if not report["books"]:
        o.append("  (no book has an overlay on)")
    return "\n".join(o)
