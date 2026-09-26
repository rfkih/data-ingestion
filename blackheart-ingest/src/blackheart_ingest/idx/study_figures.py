# ruff: noqa: RUF001, RUF002  - display copy: the typographic minus and en dash
"""Figures read out of a stored study (``idx.study.summary``) for the prose on the Strategies page.

The page's sentences are reviewed copy and live in code; the numbers inside them do not. A research line is a template -
``"+{cagr} %/yr, Sharpe {sharpe}"`` - and each placeholder names a spec that says where in the study's stored summary the
number sits and how to print it. A re-run study therefore changes the page by itself, and a figure the summary does not hold
prints as "–" instead of a number somebody typed.

Specs (plain tuples so the content module stays data):
  V(path, dp, scale, sign, absval)   the value at ``path`` ("a/b/0/c"), times ``scale``, ``dp`` decimals
  YEAR(path)                          a year, no thousands separator
  TEXT(path)                          a stored word (a verdict), sentence case
  LEN(path)                           how many entries a dict or list holds
  COUNT(path, test, field)            how many children pass ``test``; ``field`` reads a key of each child first
  DIFF(a, b, dp, scale)               value(a) - value(b)
Tests for COUNT: ("eq", x) | ("prefix", s) | ("not_prefix", s) | ("truthy",) | ("lt", x)
A path is "a/b/c", or a tuple when a key itself holds a "/".
"""
from __future__ import annotations

import re
import string
from typing import Any

DASH = "–"
_MINUS = "−"


def V(path: str, dp: int = 1, scale: float = 1, sign: bool = False, absval: bool = False) -> tuple:
    return ("v", path, dp, scale, sign, absval)


def PCT(path: str, dp: int = 1, sign: bool = False, absval: bool = False) -> tuple:
    """A fraction printed as a percentage number (the template carries the % sign)."""
    return ("v", path, dp, 100, sign, absval)


def YEAR(path: str) -> tuple:
    """A calendar year, printed without a thousands separator."""
    return ("year", path)


def TEXT(path: str) -> tuple:
    """A stored word such as a verdict ("ROBUST"), printed in sentence case."""
    return ("text", path)


def LEN(path: str) -> tuple:
    return ("len", path)


def COUNT(path: str, test: tuple, field: str | None = None) -> tuple:
    return ("count", path, test, field)


def DIFF(a: str, b: str, dp: int = 1, scale: float = 1) -> tuple:
    return ("diff", a, b, dp, scale)


def S(study: int, spec: tuple) -> tuple:
    """A page-level figure (Overview prose) read from study ``study``."""
    return ("study", study, spec)


def LIVE(name: str) -> tuple:
    """A page-level figure counted from the live tables now; the query lives in strategy_page.LIVE_FIGS."""
    return ("live", name)


_MISSING = object()


def node(summary: Any, path: str | tuple) -> Any:
    """The value at ``path`` inside a summary; ``_MISSING`` when any step is absent. Keys may contain spaces or '|'; a key
    that itself holds a '/' is reached with a tuple path."""
    o = summary
    parts = list(path) if isinstance(path, (list, tuple)) else [p for p in path.split("/") if p != ""]
    for part in parts:
        if isinstance(o, dict) and part in o:
            o = o[part]
        elif isinstance(o, list) and part.lstrip("-").isdigit() and -len(o) <= int(part) < len(o):
            o = o[int(part)]
        else:
            return _MISSING
    return o


def _num(x: Any) -> float | None:
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def fmt_num(v: float, dp: int, sign: bool = False) -> str:
    s = f"{abs(v):,.{dp}f}"
    if v < 0 and float(s.replace(",", "")) != 0:
        return _MINUS + s
    return ("+" + s) if sign and v > 0 else s


def _passes(v: Any, test: tuple) -> bool:
    kind = test[0]
    if kind == "eq":
        return v == test[1]
    if kind == "prefix":
        return isinstance(v, str) and v.startswith(test[1])
    if kind == "not_prefix":
        return isinstance(v, str) and not v.startswith(test[1])
    if kind == "truthy":
        return bool(v)
    if kind == "lt":
        return _num(v) is not None and v < test[1]
    raise ValueError(f"unknown test {test!r}")


def evaluate(spec: tuple, summary: Any) -> str | None:
    """The printed figure, or None when the summary does not hold it."""
    kind = spec[0]
    if kind == "v":
        _, path, dp, scale, sign, absval = spec
        v = _num(node(summary, path))
        if v is None:
            return None
        v *= scale
        return fmt_num(abs(v) if absval else v, dp, sign)
    if kind == "year":
        v = _num(node(summary, spec[1]))
        return None if v is None else str(int(v))
    if kind == "text":
        o = node(summary, spec[1])
        return o.capitalize() if isinstance(o, str) and o else None
    if kind == "len":
        o = node(summary, spec[1])
        return f"{len(o):,}" if isinstance(o, (dict, list)) else None
    if kind == "count":
        _, path, test, field = spec
        o = node(summary, path)
        if not isinstance(o, (dict, list)):
            return None
        items = o.values() if isinstance(o, dict) else o
        vals = [(c.get(field) if isinstance(c, dict) else None) if field else c for c in items]
        return f"{sum(1 for v in vals if _passes(v, test)):,}"
    if kind == "diff":
        _, a, b, dp, scale = spec
        va, vb = _num(node(summary, a)), _num(node(summary, b))
        return None if va is None or vb is None else fmt_num((va - vb) * scale, dp)
    raise ValueError(f"unknown spec {spec!r}")


def placeholders(template: str) -> list[str]:
    return [f for _, f, _, _ in string.Formatter().parse(template) if f]


def render(template: str, figs: dict[str, tuple], summary: Any) -> tuple[str, list[str]]:
    """The template with every placeholder filled from the summary, and the names that were not there (printed as "–")."""
    missing: list[str] = []
    vals: dict[str, str] = {}
    for name in placeholders(template):
        spec = figs.get(name)
        got = evaluate(spec, summary) if spec is not None and summary is not None else None
        if got is None:
            missing.append(name)
        vals[name] = got if got is not None else DASH
    return template.format(**vals), missing


_DIGIT = re.compile(r"\d")


def typed_figures(text: str) -> bool:
    """True when copy outside the placeholders carries a digit - used by the tests to keep result figures out of prose."""
    return bool(_DIGIT.search(re.sub(r"\{[^}]*\}", "", text)))
