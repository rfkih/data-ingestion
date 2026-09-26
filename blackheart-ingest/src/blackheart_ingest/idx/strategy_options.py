# ruff: noqa: RUF001  - display copy: the design uses the typographic minus, times, en dash and ≥
"""The settings a strategy takes in one portfolio - the Options tab of the Strategies page.

Each option is declared once: what it means, its type and unit, and an ADAPTER to where the runners read it today (a column of
``idx.book`` or a key of ``idx.book.params``). The page never writes its own copy of a setting: a change is turned into the
same ``ensure_book`` call the portfolio screen makes, so the validation (``book.ensure_book``, ``combo_book.settings``) and the
runners stay the single truth, and ``idx.strategy_config_version`` records the change.

The two meanings of ``idx.book.regime_filter`` are two options here, never one: on a trend or combined book it is the
REGIME GATE (no new entry while the COMPOSITE is under its 200-day average; held names keep their stops), on a value (annual)
book it is the REGIME EXIT (the monthly check sells to cash). Same column, different rule - so different labels, descriptions
and evidence.

Scope: 'strategy' options belong to this strategy alone; 'portfolio' options are shared by every strategy in the portfolio
(the combined book's regime gate and cash floor), and the page says so before a change is saved.
"""
from __future__ import annotations

import copy
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from . import combo_book as cb


@dataclass(frozen=True)
class Option:
    key: str
    label: str
    type: str                                   # 'bool' | 'num' | 'enum'
    desc: str
    unit: str = ""
    scope: str = "strategy"                     # 'strategy' | 'portfolio'
    choices: tuple[tuple[str, str], ...] = ()   # enum: (value, label)
    lo: float | None = None
    hi: float | None = None
    blank_off: bool = False                     # num: empty = off
    read: Callable[[dict[str, Any]], Any] = field(default=lambda b: None, repr=False)
    patch: Callable[[dict[str, Any], Any], dict[str, Any]] = field(default=lambda b, v: {}, repr=False)


def _params(b: dict[str, Any]) -> dict[str, Any]:
    p = b.get("params") or {}
    if isinstance(p, str):
        p = json.loads(p) if p.strip() else {}
    return copy.deepcopy(p)


def _with_params(b: dict[str, Any], fn: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    p = _params(b)
    fn(p)
    cb.settings({"params": p})                  # ValueError here = the combined book's own validation refused it
    return {"params": p}


def _num(v: Any) -> float | None:
    if v is None or v == "":
        return None
    if isinstance(v, Decimal):
        return float(v)
    return float(v)


# ---- combined-book sleeve options (gap / trend / ml) --------------------------------------------------------------------
def _sleeve_size(sleeve: str) -> Option:
    def read(b: dict[str, Any]) -> float:
        return round(cb.settings(b)["sizes"][sleeve] * 100, 4)

    def patch(b: dict[str, Any], v: Any) -> dict[str, Any]:
        return _with_params(b, lambda p: p.setdefault("sleeves", {}).__setitem__(sleeve, float(v) / 100))
    return Option("size", "Size per trade", "num", "Share of the portfolio's value put into each new position of this strategy.",
                  unit="% of NAV", lo=0, hi=50, read=read, patch=patch)


def _sleeve_on(sleeve: str) -> Option:
    def read(b: dict[str, Any]) -> bool:
        return sleeve not in cb.settings(b)["off"]

    def patch(b: dict[str, Any], v: Any) -> dict[str, Any]:
        def f(p: dict[str, Any]) -> None:
            off = [x for x in (p.get("off") or []) if x != sleeve]
            if not v:
                off.append(sleeve)
            p["off"] = off
        return _with_params(b, f)
    return Option("on", "Taking new trades", "bool", "Off keeps the strategy's open positions to their own exits but opens nothing new.",
                  read=read, patch=patch)


def _combo_regime_gate() -> Option:
    return Option("regime_gate", "Regime gate", "bool",
                  "No new entry while the IDX Composite closes under its 200-day average; held names keep their own exits.",
                  scope="portfolio", read=lambda b: bool(b.get("regime_filter")), patch=lambda b, v: {"regime_filter": bool(v)})


def _combo_cash_floor() -> Option:
    def read(b: dict[str, Any]) -> float:
        return round(cb.settings(b)["cash_floor"] * 100, 4)

    def patch(b: dict[str, Any], v: Any) -> dict[str, Any]:
        return _with_params(b, lambda p: p.__setitem__("cash_floor", float(v) / 100))
    return Option("cash_floor", "Cash floor", "num",
                  "No new trade that would take the invested share above 100 % minus this. Checked before every buy.",
                  unit="%", scope="portfolio", lo=0, hi=90, read=read, patch=patch)


ENS4 = [[0.05, 10], [0.08, 10], [0.10, 10], [0.08, 5]]


def _ml_confirm() -> Option:
    def read(b: dict[str, Any]) -> str:
        rules = cb.settings(b)["ml"]["rules"]
        return "ens4" if [list(r) for r in rules] == [[float(a), int(c)] for a, c in ENS4] else "single" if len(rules) == 1 else "custom"

    def patch(b: dict[str, Any], v: Any) -> dict[str, Any]:
        if v == "custom":
            raise ValueError("a custom rule set is set from the CLI (idx combo set --ml-confirm), not here")
        return _with_params(b, lambda p: p.setdefault("ml", {}).__setitem__("confirm_rules", copy.deepcopy(ENS4) if v == "ens4" else None))
    return Option("confirm", "Entry confirmation", "enum",
                  "How the price must confirm a signal before the buy: one rule (+5 % within 10 sessions), or four rules that each "
                  "take a quarter of the slot.",
                  choices=(("single", "One rule · +5 % in 10 days"), ("ens4", "Four rules · ens4"), ("custom", "Custom")),
                  read=read, patch=patch)


def _ml_num(key: str, label: str, unit: str, desc: str, lo: float, hi: float, as_int: bool = False) -> Option:
    def read(b: dict[str, Any]) -> float:
        return float(cb.settings(b)["ml"][key])

    def patch(b: dict[str, Any], v: Any) -> dict[str, Any]:
        return _with_params(b, lambda p: p.setdefault("ml", {}).__setitem__(key, int(float(v)) if as_int else float(v)))
    return Option(key, label, "num", desc, unit=unit, lo=lo, hi=hi, read=read, patch=patch)


def _ml_stop() -> Option:
    """ML-9 (#281): a fixed stop from the fill, in percent; empty = no stop (the default)."""
    def read(b: dict[str, Any]) -> float | None:
        v = cb.settings(b)["ml"].get("stop")
        return None if v is None else round(float(v) * 100, 4)

    def patch(b: dict[str, Any], v: Any) -> dict[str, Any]:
        return _with_params(b, lambda p: p.setdefault("ml", {}).__setitem__("stop", None if v in (None, "") else float(v) / 100))
    return Option("stop", "Stop-loss", "num",
                  "Sell when a holding closes this far under its entry price, in the next closing session (the order is priced to fill "
                  "even if the name keeps falling). Empty = no stop.",
                  unit="%", lo=1, hi=50, blank_off=True, read=read, patch=patch)


def _gap_per_day() -> Option:
    def read(b: dict[str, Any]) -> float:
        return float(cb.settings(b)["gap_max_per_day"])

    def patch(b: dict[str, Any], v: Any) -> dict[str, Any]:
        return _with_params(b, lambda p: p.__setitem__("gap_max_per_day", int(float(v))))
    return Option("per_day", "Tickets per day", "num", "At most this many gap-downs are bought in one morning, deepest first.",
                  unit="names", lo=1, hi=20, read=read, patch=patch)


# ---- single-strategy books --------------------------------------------------------------------------------------------
def _trend_regime_gate() -> Option:
    return Option("regime_gate", "Regime gate", "bool",
                  "No new entry while the IDX Composite closes under its 200-day average; held names keep their 10 % trailing stop.",
                  read=lambda b: bool(b.get("regime_filter")), patch=lambda b, v: {"regime_filter": bool(v)})


def _value_opts() -> list[Option]:
    return [
        Option("max_names", "Names held", "num", "How many of the cheapest qualifying names the book holds. Empty = the strategy's own list size.",
               unit="names", lo=1, hi=40, blank_off=True, read=lambda b: b.get("max_names"),
               patch=lambda b, v: {"max_names": None if v in (None, "") else int(float(v))}),
        Option("regime_exit", "Regime exit", "bool",
               "Sell the book to cash while the IDX Composite is under its 200-day average; buy back when it closes above.",
               read=lambda b: bool(b.get("regime_filter")), patch=lambda b, v: {"regime_filter": bool(v)}),
        Option("take_profit", "Take-profit", "num", "Sell a holding once it has gained this much. Empty = off.", unit="%", lo=1, hi=500,
               blank_off=True, read=lambda b: _num(b.get("take_profit_pct")),
               patch=lambda b, v: {"take_profit_pct": None if v in (None, "") else float(v)}),
        Option("cash_buffer", "Cash buffer", "num", "Share of the book held in cash at the monthly check.", unit="%", lo=0, hi=80,
               read=lambda b: _num(b.get("cash_floor_pct")) or 0.0, patch=lambda b, v: {"cash_floor_pct": float(v or 0)}),
    ]


# ---- which options a strategy has in a given book -----------------------------------------------------------------------
SLEEVE_OF = {"gapfade": "gap", "trend_small": "trend", "ml_rank": "ml"}


def options_for(strategy: str, b: dict[str, Any]) -> list[Option]:
    rule = b.get("rule")
    if rule == "combo":
        s = SLEEVE_OF.get(strategy)
        if s:
            out = [_sleeve_on(s), _sleeve_size(s)]
            if s == "trend":
                out.append(_combo_regime_gate())
            if s == "ml":
                out += [_ml_confirm(), _ml_num("margin", "Cost margin", "× round trip",
                                               "A signal must expect at least this many round-trip costs of excess return.", 0.5, 10),
                        _ml_num("max_hold", "Longest hold", "sessions", "A position still held after this many sessions is sold.",
                                5, 250, as_int=True), _ml_stop()]
            if s == "gap":
                out.append(_gap_per_day())
            return out
        if strategy == "regime_gate":
            return [_combo_regime_gate()]
        if strategy == "cash_floor":
            return [_combo_cash_floor()]
        return []
    if rule == "trend" and strategy in ("trend_small", "regime_gate"):
        return [_trend_regime_gate()]
    if rule == "annual" and strategy == "value_strict":
        return _value_opts()
    if rule == "annual" and strategy == "regime_damper":
        return [o for o in _value_opts() if o.key in ("regime_exit", "cash_buffer")]
    return []


# ---- values ---------------------------------------------------------------------------------------------------------------
def coerce(o: Option, v: Any) -> Any:
    """A value from the page -> the option's type, bounds checked. ValueError with a sentence the page can show."""
    if o.type == "bool":
        if isinstance(v, bool):
            return v
        s = str(v).strip().lower()
        if s in ("on", "true", "1", "yes"):
            return True
        if s in ("off", "false", "0", "no"):
            return False
        raise ValueError(f"{o.label}: on or off")
    if o.type == "enum":
        if v not in {c for c, _ in o.choices}:
            raise ValueError(f"{o.label}: one of {', '.join(c for c, _ in o.choices)}")
        return v
    if v is None or (isinstance(v, str) and not v.strip()):
        if o.blank_off:
            return None
        raise ValueError(f"{o.label}: a number is required")
    try:
        x = float(str(v).replace(",", "."))
    except ValueError:
        raise ValueError(f"{o.label}: {v!r} is not a number") from None
    if (o.lo is not None and x < o.lo) or (o.hi is not None and x > o.hi):
        raise ValueError(f"{o.label}: between {o.lo:g} and {o.hi:g} {o.unit}".rstrip())
    return x


def fmt(o: Option, v: Any) -> str:
    if o.type == "bool":
        return "On" if v else "Off"
    if o.type == "enum":
        return dict(o.choices).get(v, str(v))
    if v is None:
        return "Off" if o.blank_off else "–"
    x = float(v)
    s = f"{x:g}"
    if o.unit in ("%", "% of NAV"):
        return f"{s}%"
    return f"{s} {o.unit}".strip()


def schema(o: Option) -> dict[str, Any]:
    return {"key": o.key, "label": o.label, "type": o.type, "desc": o.desc, "unit": o.unit, "scope": o.scope,
            "choices": [{"value": c, "label": lbl} for c, lbl in o.choices if c != "custom"], "lo": o.lo, "hi": o.hi, "blank_off": o.blank_off}
