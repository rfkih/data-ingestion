"""The combined book: one cash pool, three sleeves, a plan every night and before the open, execution measured against the plan
(operator, 2026-09-25: "aku mau live 20 juta ... 3 aktif strategi top 1,2,3 ... 5 %, 5 %, 10 % untuk gap fade ... aku perlu
menguji late execution kalau lewat stockbit, fees, slip ... push notification dan trading plan tiap malam atau sebelum market buka").

Backtest (studies #166-#168, `research/idx_combo_rupiah.py`): Rp 20 M, 2022-01 -> 2026-09, trend 5 % / ML 5 % / gap-fade 10 % of
NAV per trade, 20 slots = Rp 96.5 M, CAGR 39.8 %, Sharpe 1.86, mDD -21.5 %; median calendar year +20 %, worst +12 %. The book
exists to measure the gap between that and Stockbit reality, per trade: fill vs the plan's reference price, minutes late,
tickets never executed.

Sleeves (book.params, defaults in DEFAULTS; a book with rule 'combo'):
  gap     the deployed gap-fade rule (idx/gapfade.py: open <= -7 %, main board, v60 >= Rp 5 bn, up to 5 a day, deepest first),
          bought at the open + tick, sold into the close - tick; sized gap_pct x NAV; intraday only
  trend   the deployed trend rule (idx/trend_book.py: 60-day high, > MA200, volume >= 1.5x median, `small` universe, trail-10
          exit, regime gate); sized trend_pct x NAV; entry at the next close, one day only
  ml      the prediction desk's 5-day score (idx/ml, idx.ml_prediction horizon 5d) used cost-aware: a name is SIGNALLED at the
          close when its expected 5-day excess (EMA-3 of pred_ret minus the liquid median) exceeds margin x its own round trip
          (closing offer/bid + fees); it is BOUGHT only when the price confirms at >= level = signal close x (1 + confirm) within
          confirm_days; SOLD when the score turns negative and a better name pays the swap, or after max_hold days; sized
          ml_pct x NAV
The ticket modes: 'combo' (the nightly plan: sells for tomorrow, trend buys for tomorrow; and the intraday ML confirmations, one
line each), 'gapfade' / 'gapfade_exit' (the same-day gap sleeve, so the app's same-day handling applies). Every line carries
`sleeve:<name>` in its flags - that is how positions are attributed to sleeves (sleeve_positions), nothing else is stored.

Live book: every ticket is a draft the operator issues (two-key) and works at Stockbit; the fill is recorded with the one-tap
screen; lines not executed on their day are marked `missed` at 20:30 (expire) so backtest-vs-live never mixes in trades that
never happened. Paper twin: filled by the desk's paper conventions (next open for the nightly plan, the trigger price for an
ML confirmation, the open / close for gap-fade) - the yardstick the live fills are read against.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import psycopg

from . import book as bk
from . import gapfade, journal, overlay, runlog, ticket, trend_book
from .card import _rows

logger = logging.getLogger(__name__)
WIB = ZoneInfo("Asia/Jakarta")
MODE = "combo"
SLEEVES = ("gap", "trend", "ml")
DEFAULTS: dict[str, Any] = {
    "sleeves": {"trend": 0.05, "ml": 0.05, "gap": 0.10},
    "slots": 20,
    "gap_max_per_day": 5,
    "cash_floor": 0.0,          # share of NAV kept in cash: no NEW trade that would take the invested share above 1 - floor (menu 34: 0.30)
    "ml": {"margin": 2.0, "ema": 3, "confirm": 0.05, "confirm_days": 10, "max_hold": 60, "min_v60": 5e9, "min_price": 100.0,
           # confirmation rules [threshold, trading days]; None = the single rule (confirm, confirm_days). ML-8 (#175) ens4 =
           # [[0.05, 10], [0.08, 10], [0.10, 10], [0.08, 5]]: each rule watches its own level with an equal share of the ML slot.
           "confirm_rules": None,
           # only names on the main boards (Utama/Pengembangan) on the day: 22 of 672 backtest ML trades were on a watch-list
           # board (Akselerasi / Pemantauan Khusus), which the desk's other sleeves never buy (operator 2026-09-26)
           "main_board_only": True,
           # fixed stop from the fill. Sold the SAME day: idx/intents.py arms one stop intent per ML holding and the session tick
           # issues the sell from 15:40 WIB for that day's closing session (#288: 35.0 %/yr, worst trade -22 % vs -34.6 %).
           # compose() below keeps the next-session stop as the fallback for a close that ends under the level after 15:40.
           # None = no stop. ML-9 (#281, ens4, pre-registered + robustness): -5 % 34.4 %/yr Sharpe 1.96 mDD -20 %; -10 % 31.2 %
           # / 1.74 / -25 %; none 27.9 % / 1.30 / -35 %. Off until the operator sets it (live settings are operator-only).
           "stop": None},
    # participation cap: a new buy may not exceed this share of the name's 20-day mean traded value (FE-2 #198: square-root impact
    # makes the trend sleeve lose 25 % of its return near Rp 10 B without it). None = uncapped (ML: a cap cost more in skipped
    # signals than it saved). The gap sleeve keeps its own, tighter cap: 1 % of the 60-day median value (gapfade.PARTICIPATION).
    "adv_cap": {"trend": 0.05, "ml": None},
}
ADV_DAYS = 20
MAIN_BOARDS = "12"                    # daily_summary.remarks board digit: 1 Utama, 2 Pengembangan
# the strategy catalog the app shows (name, one-liner, rhythm line) - the same three sleeves the runner knows
CATALOG: dict[str, dict[str, str]] = {
    "gap": {"name": "Gap fade", "one": "Buys main-board names that open 7 % or more under the previous close and sells into the same close.",
            "line": "Morning 09:00 · max 5 tickets/day · holds 1 day"},
    "trend": {"name": "Trend", "one": "Buys a close at the 60-day high above the 200-day average on 1.5x volume; trails 10 % from the peak; no new entry while the index is under its MA200.",
              "line": "Nightly plan · entry at the next close · holds ~25 days"},
    "ml": {"name": "ML ranking", "one": "The 5-day score, cost-aware: signalled when the expected excess pays twice the round trip, bought only after the price confirms (one or several +x % within n days rules, each with a share of the slot).",
           "line": "Nightly plan + intraday confirmation · holds ~25 days"},
}
# what the backtest says each sleeve does (the scorecard's yardstick; studies #160/#162 ML, #157 trend, #166 gap)
BACKTEST = {"ml": {"win": 0.54, "avg_net": 0.075, "hold_days": 24, "cagr": 0.362},
            "trend": {"win": 0.38, "avg_net": 0.052, "hold_days": 24, "cagr": 0.285},
            "gap": {"win": 0.49, "avg_net": 0.0304, "hold_days": 0, "cagr": None}}
SESSION_FROM, SESSION_TO = time(8, 58), time(15, 50)


# ---------------------------------------------------------------------------------------------------------------- books
def combo_books(conn: psycopg.Connection) -> list[str]:
    return [r["book"] for r in _rows(conn, "SELECT book FROM idx.book WHERE rule = 'combo' AND archived_at IS NULL AND book NOT LIKE 'test%%' ORDER BY book",
                                     (), ["book"])]


def rule_name(thr: float, days: int) -> str:
    return f"+{thr * 100:g}/{days}"


def invested_ok(nav: Decimal, cash_after: Decimal, notional: Decimal, floor: float) -> bool:
    """The cash floor: a new buy of ``notional`` (fees included) is allowed when the invested share stays at or below 1 - floor."""
    if floor <= 0 or nav <= 0:
        return True
    return (nav - cash_after + notional) / nav <= Decimal(str(1 - floor)) + Decimal("0.000001")


def settings(b: dict[str, Any]) -> dict[str, Any]:
    """DEFAULTS overlaid with the book's params (one level deep for the dicts). Pure."""
    p = b.get("params") or {}
    if isinstance(p, str):
        import json
        p = json.loads(p) if p.strip() else {}
    off = [str(x) for x in (p.get("off") or [])]
    sizes = {**DEFAULTS["sleeves"], **(p.get("sleeves") or {})}
    out = {"sleeves": dict(sizes), "sizes": dict(sizes), "off": off, "slots": int(p.get("slots") or DEFAULTS["slots"]),
           "gap_max_per_day": int(p.get("gap_max_per_day") or DEFAULTS["gap_max_per_day"]), "ml": {**DEFAULTS["ml"], **(p.get("ml") or {})},
           "cash_floor": float(p.get("cash_floor") if p.get("cash_floor") is not None else DEFAULTS["cash_floor"])}
    if not 0 <= out["cash_floor"] <= 0.9:
        raise ValueError(f"cash_floor {out['cash_floor']} must be within [0, 0.9]")
    out["adv_cap"] = {**DEFAULTS["adv_cap"], **(p.get("adv_cap") or {})}
    for k, v in out["adv_cap"].items():
        if v is not None and not 0 < float(v) <= 1:
            raise ValueError(f"adv_cap {k}={v} must be None or within (0, 1]")
    m = out["ml"]
    rules = m.get("confirm_rules") or [[m["confirm"], m["confirm_days"]]]
    rules = [(float(thr), int(days)) for thr, days in rules]
    if not rules or any(not (0 < thr <= 0.5) or not (1 <= days <= 60) for thr, days in rules) or len({r for r in rules}) != len(rules):
        raise ValueError(f"confirm_rules {rules} must be distinct [threshold in (0, 0.5], days in 1..60]")
    if m.get("stop") is not None and not 0 < float(m["stop"]) <= 0.5:
        raise ValueError(f"ml stop {m['stop']} must be None or within (0, 0.5]")
    m["rules"] = rules
    m["rule_names"] = [rule_name(thr, days) for thr, days in rules]
    m["size_frac"] = 1.0 / len(rules)
    for k, v in out["sleeves"].items():
        v = float(v)
        if not 0 <= v <= 0.5:
            raise ValueError(f"sleeve size {k}={v} must be within [0, 0.5]")
        out["sizes"][k] = v
        out["sleeves"][k] = 0.0 if k in off else v                     # an OFF sleeve keeps its size but takes no new position
    return out


def strategies_view(conn: psycopg.Connection, book: str) -> dict[str, Any]:
    """What the app's Strategies panel and catalog need for one book: each sleeve with size, on/off, open positions."""
    b = bk.get_book(conn, book)
    S = settings(b)
    pos = sleeve_positions(conn, book)
    sleeves = []
    for k in SLEEVES:
        if k not in S["sizes"] or (k not in (b.get("params") or {}).get("sleeves", {}) and b.get("rule") != "combo"):
            continue
        sleeves.append({"k": k, **CATALOG.get(k, {"name": k, "one": "", "line": ""}), "size": S["sizes"][k], "on": k not in S["off"],
                        "open": sorted(pos.get(k, {})), "backtest": BACKTEST.get(k)})
    return {"book": book, "rule": b.get("rule"), "slots": S["slots"], "params": b.get("params") or {}, "sleeves": sleeves,
            "catalog": [{"k": k, **v, "backtest": BACKTEST.get(k), "default_size": DEFAULTS["sleeves"].get(k, 0.05)} for k, v in CATALOG.items()],
            "positions": len(held_codes(pos))}


def positions_view(conn: psycopg.Connection, book: str) -> list[dict[str, Any]]:
    """Open positions with their sleeve, average, last close and P&L - the Portfolio screen's table."""
    pos = sleeve_positions(conn, book)
    codes = sorted(held_codes(pos))
    closes = {r["code"]: (Decimal(r["close"]), r["trade_date"]) for r in _rows(conn, """SELECT DISTINCT ON (code) code, close, trade_date FROM idx.bar
                        WHERE source = 'idx' AND code = ANY(%s) ORDER BY code, trade_date DESC""", (codes or [""],), ["code", "close", "trade_date"])}
    out = []
    for s, d in pos.items():
        for c, p in d.items():
            last = closes.get(c, (None, None))
            avg = p.get("entry_price")
            pnl = (p["lots"] * ticket.LOT * (last[0] - avg)) if (last[0] is not None and avg is not None) else None
            out.append({"code": c, "sleeve": s, "lots": int(p["lots"]), "avg": float(avg) if avg is not None else None, "last": float(last[0]) if last[0] is not None else None,
                        "last_date": str(last[1]) if last[1] else None, "pnl": float(pnl) if pnl is not None else None, "entry_date": str(p["entry_date"]) if p.get("entry_date") else None})
    return sorted(out, key=lambda r: r["code"])


def create(conn: psycopg.Connection, owner_id: str | None, kind: str, label: str, cash: Decimal | float, *, broker: str | None = None,
           sleeves: dict[str, float] | None = None, slots: int | None = None, fee_buy_pct: float = 0.15, fee_sell_pct: float = 0.25) -> str:
    """A combo book: rule 'combo', the sleeve sizes in params. Paper books use the desk's paper fills; live books are two-key."""
    params = {"sleeves": {**DEFAULTS["sleeves"], **(sleeves or {})}, "slots": int(slots or DEFAULTS["slots"]), "ml": dict(DEFAULTS["ml"]),
              "gap_max_per_day": DEFAULTS["gap_max_per_day"]}
    settings({"params": params})
    return bk.create_book(conn, owner_id, kind, label, rule="combo", cash=Decimal(str(cash)), broker=broker, params=params,
                          fee_buy_pct=fee_buy_pct, fee_sell_pct=fee_sell_pct, regime_filter=True, strategy="rule")


# ---------------------------------------------------------------------------------------------------------------- sleeves
def sleeve_of(flags: list[str] | None) -> str:
    for f in flags or []:
        if f.startswith("sleeve:"):
            return f[7:]
    return "manual"


def attribute(fills: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    """Pure. Filled ticket lines in time order -> open lots per (sleeve, code) with the entry day and average price of the
    current holding. A sell reduces the sleeve's lots; a buy onto a flat position starts a new holding."""
    pos: dict[str, dict[str, dict[str, Any]]] = {s: {} for s in (*SLEEVES, "manual")}
    for f in fills:
        s, c = sleeve_of(f.get("flags")), f["code"]
        p = pos.setdefault(s, {}).get(c)
        lots, px = Decimal(f["lots"]), Decimal(f["price"])
        if f["side"] == "buy":
            if p is None or p["lots"] <= 0:
                pos[s][c] = {"lots": lots, "entry_date": f["trade_date"], "entry_price": px, "cost": lots * px}
            else:
                p["cost"] += lots * px
                p["lots"] += lots
                p["entry_price"] = p["cost"] / p["lots"]
        else:
            if p is not None:
                p["lots"] -= lots
                p["cost"] = p["entry_price"] * p["lots"]
    return {s: {c: p for c, p in d.items() if p["lots"] > 0} for s, d in pos.items()}


def sleeve_positions(conn: psycopg.Connection, book: str) -> dict[str, dict[str, dict[str, Any]]]:
    """Positions by sleeve, from the filled lines of this book's tickets. Lots the book holds beyond what the tickets
    explain (a fill entered by hand outside a ticket) are reported under 'manual'."""
    fills = _rows(conn, """
        SELECT l.code, l.side, l.flags, f.trade_date, l.filled_lots AS lots, f.price
          FROM idx.ticket_line l JOIN idx.ticket t ON t.id = l.ticket_id JOIN idx.fill f ON f.id = l.fill_id
         WHERE t.book = %s AND l.fill_id IS NOT NULL AND l.filled_lots > 0 ORDER BY f.trade_date, f.id""", (book,),
        ["code", "side", "flags", "trade_date", "lots", "price"])
    pos = attribute(fills)
    held = {r["code"]: Decimal(r["lots"]) for r in _rows(conn, "SELECT code, lots FROM idx.position WHERE book = %s AND lots > 0", (book,), ["code", "lots"])}
    for c, lots in held.items():
        explained = sum((p[c]["lots"] for p in pos.values() if c in p), Decimal(0))
        if lots > explained:
            pos["manual"][c] = {"lots": lots - explained, "entry_date": None, "entry_price": None, "cost": None}
    return pos


def held_codes(pos: dict[str, dict[str, dict[str, Any]]]) -> set[str]:
    return {c for d in pos.values() for c in d}


# ---------------------------------------------------------------------------------------------------------------- ML score
def ml_scores(conn: psycopg.Connection, b: dict[str, Any], d: date, S: dict[str, Any]) -> pd.DataFrame:
    """The 5-day score at the close of d, cost-aware: one row per liquid name with e (expected 5-day excess, EMA over the last
    `ema` cuts), rt (its round trip: closing offer/bid + the book's fees), the raw close. Empty when the desk has not scored d."""
    m = S["ml"]
    t_hi = datetime(d.year, d.month, d.day, 23, 59, tzinfo=WIB)
    t_lo = t_hi - timedelta(days=int(m["ema"]) * 3 + 4)
    rows = _rows(conn, """
        SELECT p.code, (p.made_at AT TIME ZONE 'Asia/Jakarta')::date AS d, p.pred_ret, p.ref_price, f.value_60d_median AS v60,
               s.bid, s.offer, b.close, s.remarks
          FROM idx.ml_prediction p
          JOIN idx.feature_daily f ON f.code = p.code AND f.trade_date = (p.made_at AT TIME ZONE 'Asia/Jakarta')::date
          LEFT JOIN idx.daily_summary s ON s.code = p.code AND s.trade_date = f.trade_date
          LEFT JOIN idx.bar b ON b.code = p.code AND b.trade_date = f.trade_date AND b.source = 'idx'
         WHERE p.horizon = '5d' AND p.made_at > %s AND p.made_at <= %s AND p.pred_ret IS NOT NULL""", (t_lo, t_hi),
        ["code", "d", "pred_ret", "ref_price", "v60", "bid", "offer", "close", "remarks"])
    if not rows:
        return pd.DataFrame(columns=["code", "e", "rt", "close", "v60"])
    P = pd.DataFrame(rows)
    for c in ("pred_ret", "ref_price", "v60", "bid", "offer", "close"):
        P[c] = pd.to_numeric(P[c], errors="coerce")
    P["close"] = P["close"].fillna(P["ref_price"])
    liq = (P["v60"] >= float(m["min_v60"])) & (P["close"] >= float(m["min_price"]))
    P = P[liq].copy()
    if P.empty or P["d"].max() != d:
        return pd.DataFrame(columns=["code", "e", "rt", "close", "v60"])
    P["ex"] = P["pred_ret"] - P.groupby("d")["pred_ret"].transform("median")
    P = P.sort_values(["code", "d"])
    P["e"] = P.groupby("code")["ex"].transform(lambda s: s.ewm(span=int(m["ema"]), min_periods=1).mean())
    L = P[P["d"] == d].copy()
    if m.get("main_board_only"):                                        # board digit = 5th char of the remarks notation
        L = L[L["remarks"].fillna("").str[4:5].isin(list(MAIN_BOARDS))]
    fee_b, fee_s = float(b["fee_buy_pct"]) / 100, float(b["fee_sell_pct"]) / 100
    tk = L["close"].map(lambda p: float(ticket.tick_size(Decimal(str(p)))))
    c_in = np.where((L["offer"] > 0) & (L["offer"] >= L["close"]), L["offer"] / L["close"] - 1, tk / L["close"]) + fee_b
    c_out = np.where((L["bid"] > 0) & (L["bid"] <= L["close"]), 1 - L["bid"] / L["close"], tk / L["close"]) + fee_s
    L["rt"] = c_in + c_out
    return L[["code", "e", "rt", "close", "v60"]].reset_index(drop=True)


def trading_days_between(conn: psycopg.Connection, a: date, b_: date) -> int:
    r = _rows(conn, "SELECT count(*) AS n FROM idx.index_daily WHERE index_code = 'COMPOSITE' AND trade_date > %s AND trade_date <= %s", (a, b_), ["n"])
    return int(r[0]["n"]) if r else 0


# ---------------------------------------------------------------------------------------------------------------- the plan (pure core)
def adv_capped(budget: Decimal, adv: Decimal | None, cap: float | None) -> Decimal:
    """Pure. The budget, or cap x ADV20 when that is smaller. No ADV (a name with no traded value yet) leaves it alone."""
    if cap is None or adv is None or adv <= 0:
        return budget
    return min(budget, Decimal(str(cap)) * adv)


def adv20(conn: psycopg.Connection, codes: list[str], upto: date) -> dict[str, Decimal]:
    """Mean traded value (Rp) of each name's last ADV_DAYS sessions up to and including ``upto``."""
    if not codes:
        return {}
    rows = _rows(conn, """SELECT code, avg(value) AS adv FROM (
                            SELECT code, value, row_number() OVER (PARTITION BY code ORDER BY trade_date DESC) AS k
                              FROM idx.daily_summary WHERE code = ANY(%s) AND trade_date <= %s AND trade_date > %s::date - 60) x
                          WHERE k <= %s GROUP BY code""", (sorted(codes), upto, upto, ADV_DAYS), ["code", "adv"])
    return {r["code"]: Decimal(str(r["adv"])) for r in rows if r["adv"] is not None}


def size_line(code: str, side: str, ref: Decimal, lots: Decimal | None, slot: Decimal, cash_left: Decimal, fee: Decimal, nav: Decimal,
              reason: str, flags: list[str]) -> dict[str, Any] | None:
    lp = ticket.limit_price(ref, side)
    if side == "sell":
        notional = lots * ticket.LOT * lp
        return {"code": code, "side": "sell", "lots": lots, "limit_price": lp, "ref_close": ref, "notional": notional,
                "weight_now": (lots * ticket.LOT * ref / nav) if nav else None, "weight_target": Decimal(0), "reason": reason, "flags": flags}
    per_lot = lp * ticket.LOT * (1 + fee)
    budget = min(slot, cash_left)
    n = Decimal(int(budget // per_lot)) if per_lot > 0 else Decimal(0)
    if n <= 0 or n * ticket.LOT * lp < slot / 4:                          # refuse dust (< a quarter slot), as the trend book does
        return None
    notional = n * ticket.LOT * lp
    return {"code": code, "side": "buy", "lots": n, "limit_price": lp, "ref_close": ref, "notional": notional, "weight_now": Decimal(0),
            "weight_target": (notional / nav) if nav else None, "reason": reason, "flags": flags}


def compose(b: dict[str, Any], S: dict[str, Any], nav: Decimal, cash: Decimal, pos: dict[str, dict[str, dict[str, Any]]], closes_raw: dict[str, Decimal],
            trend_entries: list[dict[str, Any]], trend_exits: list[dict[str, Any]], ml: pd.DataFrame, ml_age: dict[str, int], open_codes: set[str],
            pending_watch: set[str], d: date, adv: dict[str, Decimal] | None = None) -> dict[str, Any]:
    """Pure. Tomorrow's lines and tonight's new ML watches from what the sleeves say.
    Sells: trend exits (trail-10 / no bar) and ML exits (swap / expiry / no score). Buys: trend entries at trend_pct x NAV,
    never above adv_cap['trend'] x the name's ADV20 (``adv``).
    Watches: ML candidates (e > margin x rt) up to the free slots, to be bought on confirmation."""
    fee_b, fee_s = Decimal(b["fee_buy_pct"]) / 100, Decimal(b["fee_sell_pct"]) / 100
    m = S["ml"]
    lines: list[dict[str, Any]] = []
    cash_after = cash
    held = held_codes(pos)
    e_map = dict(zip(ml["code"], ml["e"], strict=True)) if len(ml) else {}
    rt_map = dict(zip(ml["code"], ml["rt"], strict=True)) if len(ml) else {}
    px_map = {c: Decimal(str(p)) for c, p in zip(ml["code"], ml["close"], strict=True)} if len(ml) else {}
    # ---- sells
    exiting: set[str] = set()
    for x in trend_exits:
        if x["code"] in open_codes:
            continue
        ref = x["close"] if x.get("close") is not None else Decimal(pos["trend"][x["code"]]["entry_price"])
        ln = size_line(x["code"], "sell", Decimal(ref), Decimal(x["lots"]), Decimal(0), cash_after, fee_s, nav, x["reason"], ["sleeve:trend", "trend:exit"])
        lines.append(ln)
        cash_after += ln["notional"] * (1 - fee_s)
        exiting.add(x["code"])
    cands = ml[(ml["e"] > float(m["margin"]) * ml["rt"])].sort_values("e", ascending=False) if len(ml) else ml
    best = float(cands["e"].iloc[0]) if len(cands) else float("-inf")
    for c, p in pos["ml"].items():
        if c in open_codes:
            continue
        ref = closes_raw.get(c, px_map.get(c))
        why = None
        stopped = False
        entry = p.get("entry_price")
        # the order of the checks is the backtest's (research/idx_ml_ens4_exits.book): expiry, no score, stop, swap
        if ml_age.get(c, 0) >= int(m["max_hold"]):
            why = f"ML expiry: {ml_age[c]} hari, skor tidak pernah minta tukar"
        elif c not in e_map:
            why = "ML: tidak ada skor / bar hari ini"
        elif m.get("stop") and ref is not None and entry and Decimal(ref) <= (1 - Decimal(str(m["stop"]))) * Decimal(entry):
            stopped = True
            why = (f"ML stop {float(m['stop']) * 100:g} %: close {Decimal(ref):,.0f} <= {(1 - float(m['stop'])) * 100:g} % dari harga masuk "
                   f"{Decimal(entry):,.0f} - jual di sesi penutupan besok, limit di batas bawah ARB supaya tetap terisi")
        elif e_map[c] < 0 and best - e_map[c] > float(m["margin"]) * rt_map.get(c, 0.01):
            why = f"ML swap: skor {e_map[c] * 1e4:+.0f} bps, kandidat terbaik {best * 1e4:+.0f} bps"
        if why and ref is not None:
            ln = size_line(c, "sell", Decimal(ref), Decimal(p["lots"]), Decimal(0), cash_after, fee_s, nav, why,
                           ["sleeve:ml", "ml:exit"] + (["ml:stop", "exit:must"] if stopped else []))
            if stopped:
                # a stop must fill even when the name keeps falling: the limit sits at the day's lower auto-rejection bound
                # (the backtest sells at the next close whatever the price)
                ln["limit_price"] = ticket.snap(ticket.reject_band(Decimal(ref))[0], "sell")
                ln["notional"] = Decimal(p["lots"]) * ticket.LOT * ln["limit_price"]
            lines.append(ln)
            cash_after += ln["notional"] * (1 - fee_s)
            exiting.add(c)
    # ---- slots
    n_held_after = len(held - exiting)
    free = max(S["slots"] - n_held_after - len(pending_watch), 0)
    # ---- trend buys
    floor_held: list[str] = []
    slot_t = Decimal(str(S["sleeves"]["trend"])) * nav
    for e in trend_entries:
        if free <= 0 or slot_t <= 0:
            break
        c = e["code"]
        if c in held or c in exiting or c in open_codes or c in pending_watch or c not in closes_raw:
            continue
        budget = adv_capped(slot_t, (adv or {}).get(c), S["adv_cap"].get("trend"))
        ln = size_line(c, "buy", closes_raw[c], None, budget, cash_after, fee_b, nav,
                       f"trend: 60-day high di atas MA200, volume {e['vol_ratio']}x",
                       ["sleeve:trend", "trend:entry", f"vol:{e['vol_ratio']}x"] + (["capped:adv20"] if budget < slot_t else []))
        if ln is None:
            continue
        if not invested_ok(nav, cash_after, ln["notional"] * (1 + fee_b), S["cash_floor"]):
            floor_held.append(c)
            continue
        lines.append(ln)
        cash_after -= ln["notional"] * (1 + fee_b)
        free -= 1
    # ---- ML watches (no line tonight: the buy waits for the price to confirm)
    watches = []
    slot_m = Decimal(str(S["sleeves"]["ml"])) * nav
    for r in cands.itertuples():
        if free <= 0 or slot_m <= 0:
            break
        c = r.code
        if c in held or c in exiting or c in open_codes or c in pending_watch or any(w["code"] == c for w in watches):
            continue
        ref = Decimal(str(r.close))
        for (thr, days), rname in zip(m["rules"], m["rule_names"], strict=True):
            level = ticket.snap(ref * (1 + Decimal(str(thr))), "buy")
            watches.append({"code": c, "signal_date": d, "ref_price": ref, "level_price": level, "until_date": d + timedelta(days=days * 7 // 5 + 2),
                            "e_bps": float(r.e) * 1e4, "cost_bps": float(r.rt) * 1e4, "rule": rname, "size_frac": m["size_frac"]})
        free -= 1
    targets = [ln["code"] for ln in lines if ln["side"] == "buy"] + sorted(held - exiting)
    return {"lines": lines, "watches": watches, "nav": nav, "cash": cash, "cash_after": cash_after, "n_targets": len(targets), "targets": targets,
            "free_slots": free, "ml_candidates": len(cands), "best_e_bps": (best * 1e4 if np.isfinite(best) else None), "floor_held": floor_held}


# ---------------------------------------------------------------------------------------------------------------- the plan (shell)
def _open_lines(conn: psycopg.Connection, book: str) -> set[str]:
    return {r["code"] for r in _rows(conn, """SELECT l.code FROM idx.ticket_line l JOIN idx.ticket t ON t.id = l.ticket_id
                                               WHERE t.book = %s AND t.status IN ('draft', 'issued') AND l.status IN ('open', 'partial')""", (book,), ["code"])}


WATCH_COLS = ["id", "code", "signal_date", "ref_price", "level_price", "until_date", "e_bps", "cost_bps", "rule", "size_frac"]
FIRED = ("triggered", "ticket_issued", "filled", "carried")          # an ml_confirm intent in one of these has taken its share


def pending_watches(conn: psycopg.Connection, book: str, d: date | None = None) -> list[dict[str, Any]]:
    """The ML sleeve's armed confirmation watches - ml_confirm intents of the session rule engine (idx/intents.py), in the shape
    idx.combo_watch had (that table keeps the history before 2026-09-26)."""
    return _rows(conn, """SELECT id, code, (ref->>'signal_date')::date AS signal_date, (ref->>'ref_price')::numeric AS ref_price,
                                 (ref->>'level_price')::numeric AS level_price, expires_on AS until_date, (ref->>'e_bps')::numeric AS e_bps,
                                 (ref->>'cost_bps')::numeric AS cost_bps, COALESCE(ref->>'rule', '+5/10') AS rule,
                                 COALESCE((ref->>'size_frac')::numeric, 1) AS size_frac
                            FROM idx.order_intent
                           WHERE book = %s AND kind = 'ml_confirm' AND status = 'armed' AND (%s::date IS NULL OR expires_on >= %s)
                           ORDER BY (ref->>'e_bps')::numeric DESC NULLS LAST, (ref->>'level_price')::numeric""", (book, d, d), WATCH_COLS)


def triggered_share(conn: psycopg.Connection, book: str, code: str, signal_date: date, exclude: int | None = None) -> float:
    """The share of the ML slot already triggered for (code, signal) - the rules that fired before this one (intents, plus the
    combo_watch history for signals from before the move)."""
    r = _rows(conn, """SELECT (SELECT COALESCE(sum(COALESCE((ref->>'size_frac')::numeric, 1)), 0) FROM idx.order_intent
                                WHERE book = %s AND kind = 'ml_confirm' AND code = %s AND ref->>'signal_date' = %s AND status = ANY(%s)
                                  AND id <> COALESCE(%s, -1))
                            + (SELECT COALESCE(sum(size_frac), 0) FROM idx.combo_watch
                                WHERE book = %s AND code = %s AND signal_date = %s AND status = 'triggered') AS s""",
              (book, code, str(signal_date), list(FIRED), exclude, book, code, signal_date), ["s"])
    return float(r[0]["s"]) if r else 0.0


def build(conn: psycopg.Connection, book: str, d: date | None = None) -> dict[str, Any]:
    b = bk.get_book(conn, book)
    if b.get("rule") != "combo":
        raise ValueError(f"{book} is not a combo book")
    if bk.is_halted(b):
        raise ValueError(f"book {book} is halted ({b.get('halt_reason') or 'no reason given'})")
    S = settings(b)
    if d is None:
        d = _rows(conn, "SELECT max(trade_date) AS d FROM idx.bar WHERE source = 'idx'", (), ["d"])[0]["d"]
    snap = bk.snapshot(conn, book)
    nav, cash = Decimal(snap["nav_now"]), Decimal(b["cash"])
    pos = sleeve_positions(conn, book)
    held = held_codes(pos)
    open_codes = _open_lines(conn, book)
    watching = {w["code"] for w in pending_watches(conn, book, d)}
    # trend sleeve: the deployed universe/signals; exits from its trail on the trend positions
    uni = trend_book.universe(conn, d, "small")
    hist = trend_book.history(conn, sorted(set(uni) | held), d)
    raw = {r["code"]: Decimal(r["close"]) for r in _rows(conn, "SELECT code, close FROM idx.bar WHERE trade_date = %s AND source = 'idx' AND code = ANY(%s)",
                                                        (d, sorted(set(uni) | held)), ["code", "close"])}
    entries = trend_book.entry_signals(hist[hist["code"].isin(uni)], d)
    regime = overlay.index_regime(conn, d)
    entries, held_back = trend_book.hold_back(entries, bool(regime["on"]))
    tpos = [{"code": c, "lots": p["lots"], "avg_price": p["entry_price"], "opened_at": p["entry_date"]} for c, p in pos["trend"].items()]
    peaks = {}
    for p in tpos:
        g = hist[(hist["code"] == p["code"]) & (hist["trade_date"] >= p["opened_at"])]
        if len(g):
            peaks[p["code"]] = Decimal(str(g["adj"].max()))
    trend_exits = trend_book.exit_signals(tpos, raw, peaks)
    # ML sleeve
    ml = ml_scores(conn, b, d, S)
    ml_age = {c: trading_days_between(conn, p["entry_date"], d) for c, p in pos["ml"].items() if p.get("entry_date")}
    adv = adv20(conn, [e["code"] for e in entries], d) if S["adv_cap"].get("trend") is not None else None
    res = compose(b, S, nav, cash, pos, raw, entries, trend_exits, ml, ml_age, open_codes, watching, d, adv)
    res.update({"book": book, "mode": MODE, "run_date": d, "ticket_date": d, "strategy": "combo", "size": S["slots"], "weights": {},
                "held_back": held_back, "regime": {"index": regime["index_code"], "on": bool(regime["on"]), "close": str(regime["close"]),
                                                   "sma": str(regime["sma"]) if regime.get("sma") is not None else None},
                "regime_filter": True, "entry_gate": False, "ml_scored": bool(len(ml)), "ml_universe": len(ml), "trend_signals": len(entries),
                "positions": {s: sorted(p) for s, p in pos.items() if p}, "settings": S})
    return res


def render_plan(res: dict[str, Any], watches: list[dict[str, Any]] | None = None, label: str | None = None) -> str:
    """The evening push: what to do tomorrow and what to watch, in the operator's language."""
    d = res["run_date"]
    o = [f"[combo] {label or res['book']}: rencana {d:%d %b} -> NAV Rp {float(res['nav']) / 1e6:,.1f} jt, kas Rp {float(res['cash']) / 1e6:,.1f} jt, "
         f"slot bebas {res.get('free_slots', '?')}"]
    sells = [ln for ln in res["lines"] if ln["side"] == "sell"]
    buys = [ln for ln in res["lines"] if ln["side"] == "buy"]
    if sells:
        o.append("JUAL besok di pembukaan:")
        o += [f"  {ln['code']} {int(ln['lots'])} lot, limit >= {float(ln['limit_price']):,.0f} - {ln['reason']}" for ln in sells]
    if buys:
        o.append("BELI besok (trend, satu hari saja):")
        o += [f"  {ln['code']} {int(ln['lots'])} lot, limit <= {float(ln['limit_price']):,.0f} (Rp {float(ln['notional']) / 1e6:,.2f} jt) - {ln['reason']}" for ln in buys]
    if watches:
        o.append("AWASI (ML): beli hanya kalau harga menyentuh level")
        o += [f"  {w['code']} level >= {float(w['level_price']):,.0f} (tutup {float(w['ref_price']):,.0f}, sampai {w['until_date']:%d %b}, "
              f"ekspektasi {float(w['e_bps']):+.0f} bps vs biaya {float(w['cost_bps']):.0f})" for w in watches]
    if not (sells or buys or watches):
        o.append("Tidak ada aksi besok.")
    r = res.get("regime") or {}
    if r:
        o.append(f"Gate rezim: {'terbuka' if r.get('on') else 'TUTUP (tidak ada entry trend baru)'}; sinyal trend {res.get('trend_signals', 0)}"
                 + (f", ditahan {len(res.get('held_back') or [])}" if res.get("held_back") else ""))
    if not res.get("ml_scored"):
        o.append("Skor ML untuk hari ini belum ada: sleeve ML tidak menambah awasan malam ini.")
    return "\n".join(o)


def _notify(conn: psycopg.Connection, book: str, text: str, data: dict[str, Any] | None = None) -> None:
    try:
        from . import notify
        notify.send(text, data=data or {"route": f"/m/ticket?book={book}", "kind": "ticket", "book": book}, book=book)
    except Exception:                                                      # a notification never fails the trading job
        logger.exception("combo notify failed")


def plan(conn: psycopg.Connection, book: str, actor: str = "scheduler", d: date | None = None) -> dict[str, Any]:
    """Tonight's plan: the ticket for tomorrow (sells + trend buys) and the ML watches. Idempotent per (book, day): a second run
    the same night replaces the draft only if it has not been issued. Live: draft + push. Paper: issued (fills at the next open)."""
    res = build(conn, book, d)
    d = res["run_date"]
    b = bk.get_book(conn, book)
    out: dict[str, Any] = {"book": book, "date": str(d), "lines": len(res["lines"]), "watches": len(res["watches"]), "ticket": None, "status": None,
                           "cancelled": [], "ml_scored": res["ml_scored"], "trend_signals": res["trend_signals"]}
    with ticket._book_lock(conn, f"combo:{book}"):
        for old in _rows(conn, "SELECT id, ticket_date, status FROM idx.ticket WHERE book = %s AND mode = %s AND status IN ('draft', 'issued') ORDER BY id",
                         (book, MODE), ["id", "ticket_date", "status"]):
            if old["status"] == "draft" and old["ticket_date"] <= d:        # last night's unissued draft, or an earlier run tonight
                ticket.set_status(conn, old["id"], "cancelled", actor=actor, rationale="combo: superseded by tonight's plan")
                out["cancelled"].append(old["id"])
            elif old["ticket_date"] == d and old["status"] == "issued":
                out["status"] = "issued"
                out["why"] = "tonight's plan is already issued"
                return out
        # watches: new ones tonight arm ml_confirm intents; the armed ones stay until they expire (one live per name and rule)
        from . import intents
        for w in res["watches"]:
            intents.create(conn, book, intents.ml_confirm_spec(w), actor, if_absent=True)
        conn.commit()
        watches = pending_watches(conn, book, d)
        text = render_plan(res, watches, b.get("label"))
        out["text"] = text
        if res["lines"]:
            tid = ticket.store(conn, res, notes=f"combo plan {d}: {sum(1 for x in res['lines'] if x['side'] == 'sell')} jual, "
                                                f"{sum(1 for x in res['lines'] if x['side'] == 'buy')} beli, {len(watches)} awasan", actor=actor)
            out["ticket"] = tid
            checks = ticket.validate(conn, tid)
            out["checks_ok"] = checks["ok"]
            if not checks["ok"]:
                out["status"] = "draft"
                runlog.alert(conn, "warning", f"ticket:{book}", f"combo ticket #{tid} not issued - " + ticket.breaches_text(checks), kind="ticket",
                             strategy="combo", book=book, payload={"ticket": tid, "breaches": checks.get("breaches")}, dedupe_key=f"ticket:{tid}:not_issued")
            elif ticket.is_live(book):
                out["status"] = "draft"
            else:
                ticket.set_status(conn, tid, "issued", actor=actor, rationale="combo: paper ticket auto-issued for the next open")
                out["status"] = "issued"
        journal.record(conn, book, actor, "note", ticket_id=out["ticket"], rationale=f"combo plan {d}: {out['lines']} line(s), {len(watches)} watch(es)",
                       refs={"watches": [w["code"] for w in watches], "regime": res.get("regime"), "ml_scored": res["ml_scored"]})
        # push only when there is something to execute tomorrow on a real book (operator 2026-09-26): an ML watch is not an
        # action yet - its KONFIRMASI push comes when the price confirms; a paper book needs nobody
        if res["lines"] and ticket.is_live(book):
            _notify(conn, book, text)
    return out


# ---------------------------------------------------------------------------------------------------------------- ML confirmation (intraday)
def in_session(now: datetime) -> bool:
    t = now.astimezone(WIB)
    return t.weekday() < 5 and SESSION_FROM <= t.time() <= SESSION_TO


def confirm(conn: psycopg.Connection, book: str, actor: str = "scheduler", now: datetime | None = None) -> dict[str, Any]:
    """The ML confirmations run in the session rule engine now (ml_confirm intents, idx/intents.py): this is one tick of it for
    the book, kept for the CLI."""
    from . import intents
    return intents.tick_book(conn, book, now or datetime.now(WIB), actor)


# ---------------------------------------------------------------------------------------------------------------- gap-fade sleeve
def gap_entry(conn: psycopg.Connection, book: str, actor: str = "scheduler", d: date | None = None) -> dict[str, Any]:
    """09:00 / 09:05: the gap-fade sleeve on the combo book - the deployed scan, up to gap_max_per_day names, gap_pct x NAV each."""
    d = d or datetime.now(WIB).date()
    b = bk.get_book(conn, book)
    S = settings(b)
    out: dict[str, Any] = {"book": book, "date": str(d), "candidates": 0, "lines": 0, "ticket": None, "status": None, "filled": [], "why": None}
    if bk.is_halted(b) or S["sleeves"]["gap"] <= 0:
        out["why"] = "halted or gap sleeve off"
        return out
    with ticket._book_lock(conn, f"combo:{book}"):
        if gapfade._tickets_today(conn, book, d, gapfade.MODE_IN):
            out["why"] = "an entry ticket for today already exists"
            return out
        s = gapfade.scan(conn, d, Decimal(str(DEFAULTS.get("gap_max", -0.07))))
        out.update({"candidates": len(s["candidates"]), "seen": s["seen"]})
        if not s["ok"]:
            out["why"] = s["why"]
            return out
        snap = bk.snapshot(conn, book)
        nav, cash = Decimal(snap["nav_now"]), Decimal(b["cash"])
        pos = sleeve_positions(conn, book)
        n_open = len(held_codes(pos)) + len(_open_lines(conn, book))
        room = max(min(S["gap_max_per_day"], S["slots"] - n_open), 0)
        picked = gapfade.pick(s["candidates"], room, held_codes(pos) | _open_lines(conn, book))
        k_size = max(int(round(1 / S["sleeves"]["gap"])), 1)              # plan_entries sizes a slot as NAV / k
        lines = gapfade.plan_entries(picked, nav, cash, k_size, Decimal(b["fee_buy_pct"]) / 100, ticket.min_trade_for(nav))
        if S["cash_floor"] > 0:                                             # the floor: keep the lines that fit under 1 - floor, in order
            kept, cash_after = [], cash
            fee_b = Decimal(b["fee_buy_pct"]) / 100
            for ln in lines:
                if invested_ok(nav, cash_after, ln["notional"] * (1 + fee_b), S["cash_floor"]):
                    kept.append(ln)
                    cash_after -= ln["notional"] * (1 + fee_b)
            out["floor_held"] = [ln["code"] for ln in lines if ln not in kept]
            lines = kept
        for ln in lines:
            ln["flags"] = ["sleeve:gap", *ln["flags"]]
        out["lines"] = len(lines)
        if not lines:
            return out
        res = gapfade._ticket_res(book, d, gapfade.MODE_IN, lines, b, conn, targets=[ln["code"] for ln in lines] + sorted(held_codes(pos)))
        res["strategy"] = "combo"
        tid = ticket.store(conn, res, notes=f"combo gap-fade: {len(lines)} gap(s)", actor=actor)
        out["ticket"] = tid
        checks = ticket.validate(conn, tid)
        if not checks["ok"]:
            out["status"] = "draft"
            runlog.alert(conn, "warning", f"ticket:{book}", f"combo gap ticket #{tid} not issued - " + ticket.breaches_text(checks), kind="ticket",
                         strategy="combo", book=book, dedupe_key=f"ticket:{tid}:not_issued")
            return out
        if ticket.is_live(book):
            out["status"] = "draft"
            _notify(conn, book, f"[combo] GAP-FADE {b.get('label') or book}: beli di pembukaan, jual ke penutupan, ticket #{tid}\n"
                                + "\n".join(f"  {ln['code']} {int(ln['lots'])} lot, limit <= {float(ln['limit_price']):,.0f} ({ln['reason']})" for ln in lines),
                    data={"route": f"/m/ticket?book={book}", "kind": "ticket", "book": book, "ticket": tid})
            return out
        ticket.set_status(conn, tid, "issued", actor=actor, rationale="combo: paper gap ticket issued for the opening fill")
        out["filled"] = gapfade._fill(conn, ticket.load(conn, tid), {c["code"]: c["open"] for c in s["candidates"]}, d, actor, "combo gap paper fill at the open")
        ticket.set_status(conn, tid, "closed", actor=actor, rationale="combo: gap sleeve filled at the open")
        out["status"] = "filled"
    return out


def gap_exit(conn: psycopg.Connection, book: str, actor: str = "scheduler", d: date | None = None) -> dict[str, Any]:
    """Sell every gap-sleeve position into the close (the same-day rule); other sleeves are untouched. The session rule engine
    does this from 15:50 through its gap_exit intents (idx/intents.py); this entry point is kept for the CLI."""
    d = d or datetime.now(WIB).date()
    b = bk.get_book(conn, book)
    with ticket._book_lock(conn, f"combo:{book}"):
        return gap_exit_unlocked(conn, b, actor, d)


def gap_exit_unlocked(conn: psycopg.Connection, b: dict[str, Any], actor: str, d: date) -> dict[str, Any]:
    """gap_exit's body, for a caller that already holds the book lock. Idempotent per day: a second call finds today's exit
    ticket and returns it (ticket, codes) with why = 'an exit ticket for today already exists'."""
    book = b["book"]
    out: dict[str, Any] = {"book": book, "date": str(d), "positions": 0, "ticket": None, "status": None, "why": None, "codes": []}
    today = gapfade._tickets_today(conn, book, d, gapfade.MODE_OUT)
    if today:
        out.update({"why": "an exit ticket for today already exists", "ticket": today[-1]["id"], "status": today[-1]["status"],
                    "codes": sorted({ln["code"] for t in today for ln in t["lines"]})})
        return out
    pos = sleeve_positions(conn, book)["gap"]
    out["positions"] = len(pos)
    if not pos:
        return out
    plist = [{"code": c, "lots": p["lots"], "avg_price": p["entry_price"]} for c, p in pos.items()]
    px = gapfade.last_feed_prices(conn, d, [p["code"] for p in plist])
    lines = gapfade.plan_exits(plist, px)
    for ln in lines:
        ln["flags"] = ["sleeve:gap", *ln.get("flags", [])]
    missing = [p["code"] for p in plist if p["code"] not in px]
    if missing:
        runlog.alert(conn, "warning", f"combo:{book}", f"no price today for {', '.join(missing)} - gap position not in the exit ticket")
    if not lines:
        out["why"] = "no price for any position"
        return out
    res = gapfade._ticket_res(book, d, gapfade.MODE_OUT, lines, b, conn)
    res["strategy"] = "combo"
    tid = ticket.store(conn, res, notes="combo gap-fade: sell into the closing auction", actor=actor)
    out.update({"ticket": tid, "codes": sorted(ln["code"] for ln in lines)})
    ticket.set_status(conn, tid, "issued", actor=actor, rationale="combo: gap exit ticket for the closing auction")
    out["status"] = "issued"
    if ticket.is_live(book):
        _notify(conn, book, f"[combo] JUAL gap-fade ke penutupan, ticket #{tid}\n" + "\n".join(f"  {ln['code']} {int(ln['lots'])} lot @ ~{float(ln['limit_price']):,.0f}" for ln in lines),
                data={"route": f"/m/ticket?book={book}", "kind": "ticket", "book": book, "ticket": tid})
    return out


# ---------------------------------------------------------------------------------------------------------------- pre-open, expiry, nudge
def preopen_text(conn: psycopg.Connection, book: str, d: date | None = None) -> str:
    d = d or datetime.now(WIB).date()
    b = bk.get_book(conn, book)
    t = _rows(conn, "SELECT id, status, ticket_date FROM idx.ticket WHERE book = %s AND mode = %s AND status IN ('draft', 'issued') ORDER BY id DESC LIMIT 1",
              (book, MODE), ["id", "status", "ticket_date"])
    o = [f"[combo] {b.get('label') or book}: pra-market {d:%d %b}"]
    if t:
        tk = ticket.load(conn, t[0]["id"])
        lines = [ln for ln in tk["lines"] if ln["status"] in ("open", "partial")]
        if lines:
            o.append(f"Ticket #{tk['id']} ({tk['status']}): " + "; ".join(f"{ln['side'].upper()} {ln['code']} {int(ln['lots'])} lot @ {float(ln['limit_price']):,.0f}" for ln in lines))
            if tk["status"] == "draft":
                o.append("Ticket masih DRAFT: terbitkan (kunci kedua) sebelum dikerjakan.")
    ws = pending_watches(conn, book, d)
    if ws:
        o.append("Awasan ML hari ini: " + "; ".join(f"{w['code']} >= {float(w['level_price']):,.0f}" for w in ws))
    gp = sleeve_positions(conn, book)["gap"]
    if gp:
        o.append("Sisa posisi gap-fade (harus dijual di pembukaan): " + ", ".join(gp))
    if len(o) == 1:
        o.append("Tidak ada aksi terjadwal; gap-fade dicek 09:00.")
    return "\n".join(o)


def preopen(conn: psycopg.Connection, book: str, d: date | None = None) -> str:
    text = preopen_text(conn, book, d)
    # the 08:30 reminder buzzes only when a line must be worked at the open (an open ticket line, a gap-fade leftover to
    # sell) on a real book - "nothing scheduled" and a list of ML watches are not actions (operator 2026-09-26)
    if ticket.is_live(book) and ("Ticket #" in text or "Sisa posisi gap-fade" in text):
        _notify(conn, book, text)
    return text


def expire(conn: psycopg.Connection, book: str, actor: str = "scheduler", d: date | None = None) -> dict[str, Any]:
    """20:30: a line that was for today and was not executed is a MISS - skipped with the reason, the ticket closed - so the
    scorecard counts it and tomorrow's plan does not see it as pending. Paper tickets are left to the paper fill."""
    d = d or datetime.now(WIB).date()
    out: dict[str, Any] = {"book": book, "missed": [], "closed": []}
    if not ticket.is_live(book):
        return out
    for t in _rows(conn, "SELECT id, mode, ticket_date, status FROM idx.ticket WHERE book = %s AND status IN ('draft', 'issued') AND ticket_date < %s ORDER BY id",
                   (book, d if datetime.now(WIB).time() < time(16, 0) else d + timedelta(days=1)), ["id", "mode", "ticket_date", "status"]):
        tk = ticket.load(conn, t["id"])
        for ln in tk["lines"]:
            if ln["status"] in ("open", "partial"):
                ticket.skip_line(conn, ln["id"], "missed: not executed on its day")
                out["missed"].append((t["id"], ln["code"], ln["side"]))
        ticket.set_status(conn, t["id"], "closed" if t["status"] == "issued" else "cancelled", actor=actor, rationale="combo: day over, unexecuted lines marked missed")
        out["closed"].append(t["id"])
    if out["missed"]:
        journal.record(conn, book, actor, "note", rationale=f"combo {d}: {len(out['missed'])} line(s) missed", refs={"missed": [f"{c} {s} #{t}" for t, c, s in out["missed"]]})
    return out


def nudge(conn: psycopg.Connection, book: str) -> str | None:
    """Late afternoon: remind the operator of lines still open on today's live tickets."""
    if not ticket.is_live(book):
        return None
    d = datetime.now(WIB).date()
    open_ = _rows(conn, """SELECT t.id, t.mode, l.code, l.side, l.lots, l.limit_price FROM idx.ticket t JOIN idx.ticket_line l ON l.ticket_id = t.id
                            WHERE t.book = %s AND t.status IN ('draft', 'issued') AND t.ticket_date >= %s AND l.status IN ('open', 'partial') ORDER BY t.id, l.seq""",
                  (book, d - timedelta(days=1)), ["id", "mode", "code", "side", "lots", "limit_price"])
    if not open_:
        return None
    text = "[combo] belum ditandai: " + "; ".join(f"#{r['id']} {r['side']} {r['code']} {int(r['lots'])} lot" for r in open_) + "\nCatat fill atau lewati sebelum 20:30."
    _notify(conn, book, text)
    return text


# ---------------------------------------------------------------------------------------------------------------- scorecard
def scorecard(conn: psycopg.Connection, book: str, d: date | None = None, store: bool = True) -> dict[str, Any]:
    """Per sleeve since the book started: lines issued / filled / missed, slippage vs the plan's reference (bps, buys pay more =
    positive), hours from ticket to fill record, realised and open P&L; the book's NAV path; the backtest yardstick."""
    d = d or datetime.now(WIB).date()
    b = bk.get_book(conn, book)
    rows = _rows(conn, """
        SELECT t.id AS ticket, t.mode, t.ticket_date, t.created_at AS issued_at, l.code, l.side, l.lots, l.limit_price, l.ref_close, l.status, l.skip_reason, l.flags,
               l.filled_lots, f.price AS fill_price, f.fee, f.created_at AS filled_at, f.trade_date AS fill_date
          FROM idx.ticket t JOIN idx.ticket_line l ON l.ticket_id = t.id LEFT JOIN idx.fill f ON f.id = l.fill_id
         WHERE t.book = %s AND t.status <> 'cancelled' ORDER BY t.id, l.seq""", (book,),
        ["ticket", "mode", "ticket_date", "issued_at", "code", "side", "lots", "limit_price", "ref_close", "status", "skip_reason", "flags", "filled_lots",
         "fill_price", "fee", "filled_at", "fill_date"])
    per: dict[str, dict[str, Any]] = {}
    for r in rows:
        s = sleeve_of(r["flags"])
        p = per.setdefault(s, {"lines": 0, "filled": 0, "missed": 0, "skipped": 0, "slip_bps": [], "delay_h": [], "buy_rp": Decimal(0), "sell_rp": Decimal(0), "fees_rp": Decimal(0)})
        p["lines"] += 1
        if r["status"] in ("filled", "partial") and r["fill_price"]:
            p["filled"] += 1
            ref = Decimal(r["ref_close"])
            fp = Decimal(r["fill_price"])
            slip = (fp / ref - 1) if r["side"] == "buy" else (1 - fp / ref)
            p["slip_bps"].append(float(slip) * 1e4)
            if r["filled_at"] and r["issued_at"]:
                p["delay_h"].append((r["filled_at"] - r["issued_at"]).total_seconds() / 3600)
            gross = Decimal(r["filled_lots"]) * ticket.LOT * fp
            fee = Decimal(r["fee"] or 0)
            p["fees_rp"] += fee
            if r["side"] == "buy":
                p["buy_rp"] += gross + fee
            else:
                p["sell_rp"] += gross - fee
        elif r["status"] == "skipped":
            if (r["skip_reason"] or "").startswith("missed"):
                p["missed"] += 1
            else:
                p["skipped"] += 1
    pos = sleeve_positions(conn, book)
    closes = {r["code"]: Decimal(r["close"]) for r in _rows(conn, "SELECT DISTINCT ON (code) code, close FROM idx.bar WHERE source = 'idx' AND code = ANY(%s) ORDER BY code, trade_date DESC",
                                                            (sorted(held_codes(pos)) or [""],), ["code", "close"])}
    out_s = {}
    for s, p in per.items():
        open_value = sum((q["lots"] * ticket.LOT * closes.get(c, q["entry_price"] or Decimal(0)) for c, q in pos.get(s, {}).items()), Decimal(0))
        pnl = p["sell_rp"] + open_value - p["buy_rp"]
        out_s[s] = {"lines": p["lines"], "filled": p["filled"], "missed": p["missed"], "skipped": p["skipped"],
                    "fill_rate": (p["filled"] / p["lines"]) if p["lines"] else None,
                    "slip_bps_mean": float(np.mean(p["slip_bps"])) if p["slip_bps"] else None, "slip_bps_median": float(np.median(p["slip_bps"])) if p["slip_bps"] else None,
                    "delay_h_median": float(np.median(p["delay_h"])) if p["delay_h"] else None, "bought_rp": float(p["buy_rp"]), "sold_rp": float(p["sell_rp"]),
                    "open_rp": float(open_value), "pnl_rp": float(pnl), "fees_rp": float(p["fees_rp"]), "open_names": sorted(pos.get(s, {})), "backtest": BACKTEST.get(s)}
    nav = _rows(conn, "SELECT trade_date, nav, cash FROM idx.book_nav WHERE book = %s ORDER BY trade_date", (book,), ["trade_date", "nav", "cash"])
    navs = [float(r["nav"]) for r in nav]
    peak = 0.0
    mdd = 0.0
    for v in navs:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1 if peak else 0.0)
    out = {"book": book, "date": str(d), "label": b.get("label"), "kind": "live" if ticket.is_live(book) else "paper", "sleeves": out_s,
           "nav": {"first": navs[0] if navs else None, "last": navs[-1] if navs else None, "days": len(navs), "mdd": mdd,
                   "return": (navs[-1] / navs[0] - 1) if len(navs) > 1 and navs[0] else None},
           "watches": watch_counts(conn, book),
           "settings": settings(b)}
    if store:
        import json
        with conn.cursor() as cur:
            cur.execute("INSERT INTO idx.combo_scorecard (book, d, payload) VALUES (%s, %s, %s::jsonb) ON CONFLICT (book, d) DO UPDATE SET payload = EXCLUDED.payload, computed_at = now()",
                        (book, d, json.dumps(out, default=str)))
        conn.commit()
    return out


def watch_counts(conn: psycopg.Connection, book: str) -> dict[str, int]:
    """pending / triggered / expired / cancelled, as the web reads them: ml_confirm intents (armed = pending, fired = triggered)
    plus the combo_watch history (without the rows that moved to intents)."""
    rows = _rows(conn, """SELECT st, sum(n)::int AS n FROM (
                            SELECT CASE WHEN status = 'armed' THEN 'pending' WHEN status = ANY(%s) THEN 'triggered' ELSE status END AS st, count(*) AS n
                              FROM idx.order_intent WHERE book = %s AND kind = 'ml_confirm' GROUP BY 1
                            UNION ALL
                            SELECT status, count(*) FROM idx.combo_watch WHERE book = %s AND COALESCE(note, '') NOT LIKE 'moved to order_intent%%' GROUP BY 1) x
                          GROUP BY st""", (list(FIRED), book, book), ["st", "n"])
    return {r["st"]: r["n"] for r in rows}


def render_scorecard(sc: dict[str, Any]) -> str:
    o = [f"# combo {sc['label'] or sc['book']} ({sc['kind']}) scorecard {sc['date']}"]
    n = sc["nav"]
    if n["first"]:
        o.append(f"NAV Rp {n['first'] / 1e6:,.2f} jt -> Rp {(n['last'] or 0) / 1e6:,.2f} jt ({(n['return'] or 0) * 100:+.1f} %), {n['days']} hari, mDD {n['mdd'] * 100:.1f} %")
    o.append(f"{'sleeve':<7}{'lines':>6}{'filled':>7}{'missed':>7}{'slip bps':>10}{'delay h':>9}{'P&L Rp':>14}{'fees Rp':>10}  backtest")
    for s, p in sc["sleeves"].items():
        bt = p.get("backtest") or {}
        o.append(f"{s:<7}{p['lines']:>6}{p['filled']:>7}{p['missed']:>7}{('%+.0f' % p['slip_bps_mean']) if p['slip_bps_mean'] is not None else '-':>10}"
                 f"{('%.1f' % p['delay_h_median']) if p['delay_h_median'] is not None else '-':>9}{p['pnl_rp']:>14,.0f}{p['fees_rp']:>10,.0f}  "
                 + (f"win {bt.get('win', 0) * 100:.0f} % avg {bt.get('avg_net', 0) * 100:+.1f} %" if bt else ""))
    if sc.get("watches"):
        o.append("watches: " + ", ".join(f"{k} {v}" for k, v in sc["watches"].items()))
    return "\n".join(o)
