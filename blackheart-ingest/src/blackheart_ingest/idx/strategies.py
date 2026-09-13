"""The strategy catalog: the rule and its tested variants, ONE implementation of "which names, what weights" (``pick``),
and the historical record each (strategy, size) earned in research (``idx.strategy_history``, imported from the research
JSON outputs so the app can show the record next to the choice).

A choice is a strategy family plus a size: the family says how the names are ordered and weighted, the size says how many
are held (None = the family's natural list, the top fifth; 10 or 15 = cut to that many). Every family was run through
research/idx_value_quality.py (rev. 3, natural size) and research/idx_top10.py (sizes 10 and 15) with the same simulator,
costs and point-in-time universe; ``history`` names the key in those outputs (rev3 / topn, and conv / conv10 for
research/idx_cash_conversion.py). Statuses:
  deployed      what the books follow unless told otherwise (the strict composite since 2026-09-12)
  baseline      the original rule, the yardstick every variant is measured against
  superseded    was the deployed rule; replaced
  candidate     pre-registered switch, decided at a named rebalance
  tested        run, not better (or not distinguishable) on the evidence
  experimental  calendar-dependent; paper first
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
import psycopg.types.json

from .candidates import KEYS, rank_pool

SIZES = (None, 10, 15)
CATALOG: list[dict[str, Any]] = [
    {"key": "rule", "label": "The rule: cheapest fifth, light quality gate", "status": "baseline",
     "rule": "Utama/Pengembangan, liquid, audited profit with ROE of at least 5 %; composite rank of earnings yield, book yield "
             "and dividend yield; the top fifth (at least ten), equal weight, rebalanced each May.",
     "note": "Ten to twenty-four names a year at its natural size. Beat the equal-weight universe, the COMPOSITE and IDX Value "
             "30 in every rebalance calendar tested; the size of the edge varies by calendar. Cut to ten it is more concentrated "
             "(drawdowns 27 to 29 % in three calendars); cut to fifteen it is about the same as the full list. The books "
             "followed it until 2026-09-12, when the operator moved them to the strict composite.",
     "params": {"gate": "loose", "order": "composite", "weight": "eq"},
     "history": {"rev3": "composite_qloose", "topn": "rule/eq"}},
    {"key": "strict", "label": "Strict composite", "status": "deployed",
     "rule": "As the rule, but the gate is strict: ROE of at least 10 %, profit this and the prior year, positive operating "
             "cash flow, debt at most 1.5 times equity (financials exempt). Composite rank within that pool, equal weight.",
     "note": "Led the rule in all four calendars in rev. 3 (10 to 15 names at its natural size). Cut to ten it matched or beat "
             "the rule everywhere with a higher Sharpe. Every later question (ten names, weights, holding rules, quality, cash "
             "conversion) left it the best robust choice, and the books follow it since 2026-09-12 by the operator's decision, "
             "ahead of the pre-registered May 2027 date.",
     "params": {"gate": "strict", "order": "composite", "weight": "eq"},
     "history": {"rev3": "composite_q", "topn": "strict/eq"}},
    {"key": "strict_cash", "label": "Strict composite plus cash conversion", "status": "tested",
     "rule": "As the strict composite, with a fourth rank input: operating cash flow per rupiah of audited profit, capped at "
             "three. Equal weight.",
     "note": "Passed its pre-registered test on paper (+263 %, +356 %, +128 %, +116 % against the strict composite's +146 %, "
             "+224 %, +128 %, +85 %), but one name, ENRG's eightfold run in 2025, is the whole gap: without it the two are within "
             "eight points in every calendar. Offered for a book that wants the extra input; not the default.",
     "params": {"gate": "strict", "order": "composite", "weight": "eq", "keys": ["ep", "bp", "dy", "conv"]},
     "history": {"conv": "strict+conv", "conv10": "strict10+conv"}},
    {"key": "value", "label": "Pure earnings yield", "status": "tested",
     "rule": "The light gate, then the cheapest names by earnings yield alone, equal weight.",
     "note": "The highest total return at May and the most fragile: +55 % at August, holds Sritex to zero, deeper drawdowns. "
             "Cut to ten it is worse than the rule in three of four calendars.",
     "params": {"gate": "loose", "order": "ep", "weight": "eq"},
     "history": {"rev3": "value_qloose", "topn": "value/eq"}},
    {"key": "momentum", "label": "Value plus momentum", "status": "experimental",
     "rule": "From the rule's list, the names with the strongest 12-month price momentum (skipping the last month), equal weight.",
     "note": "Catches the year's winners when the rebalance date is early in their run (+144 % May, +142 % February at ten "
             "names) and is average to poor otherwise (+100 % August, +65 % November). Paper first.",
     "params": {"gate": "loose", "order": "mom", "weight": "eq"},
     "history": {"topn": "momentum/eq"}},
    {"key": "momentum_rank", "label": "Momentum, weighted to the leaders", "status": "experimental",
     "rule": "As value plus momentum, but weights fall linearly from the strongest name to the last (18 % to 2 % at ten names).",
     "note": "The winner-chaser: +204 % at May and +194 % at February, +23 % at November, at ten names. The widest spread of "
             "outcomes in the catalog. Paper first.",
     "params": {"gate": "loose", "order": "mom", "weight": "rank"},
     "history": {"topn": "momentum/rank"}},
    {"key": "growth", "label": "Profit growth", "status": "tested",
     "rule": "From the rule's list, the names with the highest audited profit growth, equal weight.",
     "note": "Worse than the rule in three of four calendars at ten names.",
     "params": {"gate": "loose", "order": "np_yoy", "weight": "eq"},
     "history": {"topn": "growth/eq"}},
]
BY_KEY = {s["key"]: s for s in CATALOG}
OVERLAYS: list[dict[str, Any]] = [
    {"key": "overlay:regime", "label": "Crash filter: cash while the IHSG is under its 200-day average", "status": "option",
     "rule": "Checked on the first trading day of each month, after the close. Off: the book is sold to cash. On again: the book's list is "
             "bought back. An annual rebalance while it is off becomes a cash ticket. Set per book (regime filter).",
     "note": "2008-2026 on a 100-name liquid basket: max drawdown 51 % to 25 %, 2008 flat instead of -36 %, 2020 -13 % instead of -47 %, "
             "total +794 % against +497 % with cash at 4 %. 2021-2026 on the strict book: 0 to 49 % of the return given up depending on the "
             "calendar, and no help with the book's own 2022 dips, which happened while the IHSG stayed above its average. Insurance: it "
             "pays in market crashes and costs in calm years. 200 days, not 100: shorter windows halve the return on the real book.",
     "history": {"overlay": "index"}},
    {"key": "overlay:entry_gate", "label": "Entry gate: buy a listed name only above its 200-day average", "status": "option",
     "rule": "At a rebalance, a listed name under its own 200-day average is held back and its slot stays in cash; at each monthly check "
             "the held-back names that have crossed above are bought, one slot each. Never sells on trend. Set per book (entry gate).",
     "note": "2021-2026 on the strict book: drawdowns a little shallower (worst 20 % against 22 %), return lower in three of four "
             "calendars (-8 to -34 %), higher in the fourth. No protection in a crash: over 2008-2026 the 2020 drawdown is about the "
             "same either way. A mild damper, not a free improvement.",
     "history": {"overlay": "entry_only"}},
    {"key": "overlay:take_profit", "label": "Take profit: sell a name once it has doubled", "status": "option",
     "rule": "At each monthly check, a held name at or above twice its purchase price is sold and its cash waits for the next "
             "rebalance. Set per book (take profit %, 100 tested).",
     "note": "2021-2026 on the strict book: ahead in three of four calendars by 3 to 8 points, behind by 42 in the fourth (PTRO went on "
             "to +185 % after doubling). Ten doubling events in five years: median -5 % after the double, six of ten fell back. Sells the "
             "small reversals, misses the multi-bagger. Selling on valuation instead (no longer cheap vs peers, P/E over 15) lost in every "
             "calendar; the annual rebalance stays the valuation exit.",
     "history": {"sell": "tp100"}},
    {"key": "overlay:none", "label": "Strict book as simulated in the overlay test (drift, one-slot cap, cash 4 %)", "status": "reference",
     "rule": "", "note": "The like-for-like baseline of the two overlay records above.", "history": {"overlay": "none"}},
]
REFERENCE_LABELS = {"bench": "Equal-weight universe (same simulation)", "index:COMPOSITE": "IDX COMPOSITE (price)",
                    "index:IDXV30": "IDX Value 30 (price)", "index:IDXHIDIV20": "IDX High Dividend 20 (price)",
                    "index:LQ45": "LQ45 (price)"}


def deployed() -> str:
    """The family the books follow unless told otherwise: the one catalog entry with status ``deployed``."""
    return next(s["key"] for s in CATALOG if s["status"] == "deployed")


def get(key: str) -> dict[str, Any]:
    if key not in BY_KEY:
        raise ValueError(f"unknown strategy {key!r}; one of {', '.join(BY_KEY)}")
    return BY_KEY[key]


def get_any(key: str) -> dict[str, Any]:
    """A catalog family or an overlay entry (for the record pages); ValueError otherwise."""
    for s in OVERLAYS:
        if s["key"] == key:
            return s
    return get(key)


def weights(codes: list[str], scheme: str) -> dict[str, Decimal]:
    """Weights over the chosen names in their strategy order, summing to 1."""
    n = len(codes)
    if not n:
        return {}
    if scheme == "top5x2":
        raw = {c: (Decimal(2) if i < n / 2 else Decimal(1)) for i, c in enumerate(codes)}
    elif scheme == "rank":
        raw = {c: Decimal(n - i) for i, c in enumerate(codes)}
    else:
        raw = {c: Decimal(1) for c in codes}
    tot = sum(raw.values(), Decimal(0))
    return {c: v / tot for c, v in raw.items()}


def pick(key: str, rows: list[dict[str, Any]], size: int | None = None, weight: str | None = None) -> list[dict[str, Any]]:
    """Pure. Candidate rows (ep, bp, dy, np_yoy, mom, gate_loose, gate_strict, tradable?) -> the strategy's ordering with
    ``strategy_rank``, ``selected`` and ``weight`` on every row; ``rank`` stays the composite rank of the base pool.
    Composite families order their whole gate pool and select the top fifth; feature families (ep / mom / np_yoy) order the
    rule's own fifth. ``size`` cuts the selection to that many names; ``weight`` overrides the family's scheme."""
    p = get(key)["params"]
    base = rank_pool([dict(r) for r in rows], gate=p["gate"], keys=tuple(p.get("keys") or KEYS))
    if p["order"] == "composite":
        ordered = base
        chosen = [r for r in ordered if r["selected"]]
    else:
        fifth = [r for r in base if r["selected"]]
        f = p["order"]
        ordered = sorted(fifth, key=lambda r: (r.get(f) is None, -(Decimal(r[f]) if r.get(f) is not None else 0), r["code"]))
        chosen = [r for r in ordered if r.get(f) is not None]
    if size:
        chosen = chosen[:size]
    w = weights([r["code"] for r in chosen], weight or p["weight"])
    for i, r in enumerate(ordered, 1):
        r["strategy_rank"] = i
        r["selected"] = r["code"] in w
        r["weight"] = w.get(r["code"], Decimal(0))
    return ordered


# ---------------------------------------------------------------------------
# history: research outputs -> idx.strategy_history
# ---------------------------------------------------------------------------
STATS = ("total_pct", "cagr_pct", "sharpe", "mdd_pct", "dsr", "psr", "from")


def _holdings(h: Any) -> list[dict[str, Any]] | None:
    if h is None:
        return None
    if isinstance(h, dict):                                              # top-n: {date: [codes]}
        return [{"date": d, "n": len(codes), "names": list(codes)} for d, codes in h.items()]
    return [dict(x) for x in h]                                          # rev3: [{date, n, names, top, bottom, top3_pct_of_nav}]


def history_rows_from_json(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Pure. A rev. 3 output (`months.<m>.summary`, size = natural), a top-n output (`months.<m>.table`, `size` = n) or the
    cash-conversion output (`months.<m>.table` with a `verdict`, natural and ten-name keys side by side) -> history rows
    keyed (strategy, size, month). Size 0 means the family's natural list."""
    rows: list[dict[str, Any]] = []
    months = doc.get("months") or {}
    first = next(iter(months.values()), {})
    if "verdict" in doc and "months" in doc and any("tp100" in (m.get("table") or {}) for m in doc["months"].values()):
        for m, mdoc in doc["months"].items():                              # research/idx_sell_rules.py
            table = mdoc.get("table") or {}
            for s in OVERLAYS:
                hk = s["history"].get("sell")
                if hk in table:
                    v = table[hk]
                    rows.append({"strategy": s["key"], "size": 0, "month": int(m), "source": f"sell:{hk}", "n_trials": doc.get("n_trials"),
                                 "stats": {k: v.get(k) for k in STATS}, "yearly": v.get("yearly"), "periods": v.get("periods"),
                                 "holdings": None, "generated_at": doc.get("generated")})
        return rows
    if "part_b" in doc:                                                   # research/idx_trend_overlay.py
        for m, mdoc in (doc["part_b"] or {}).items():
            table = mdoc.get("table") or {}
            for s in OVERLAYS:
                hk = s["history"].get("overlay")
                if hk in table:
                    v = table[hk]
                    rows.append({"strategy": s["key"], "size": 0, "month": int(m), "source": f"overlay:{hk}", "n_trials": doc.get("n_trials"),
                                 "stats": {k: v.get(k) for k in STATS}, "yearly": v.get("yearly"), "periods": v.get("periods"),
                                 "holdings": None, "generated_at": doc.get("generated")})
        return rows
    source = "conv" if "verdict" in doc else ("rev3" if "summary" in first else "topn")
    size = 0 if source == "rev3" else int(doc.get("size") or 10)
    slots = (("conv", 0), ("conv10", 10)) if source == "conv" else ((source, size),)
    generated = doc.get("generated")
    for m, mdoc in months.items():
        table = mdoc.get("summary") if source == "rev3" else mdoc.get("table")
        n_trials = mdoc.get("n_trials") if source == "rev3" else doc.get("n_trials")
        for s in CATALOG:
            for hname, hsize in slots:
                hk = s["history"].get(hname)
                if hk and table and hk in table:
                    v = table[hk]
                    rows.append({"strategy": s["key"], "size": hsize, "month": int(m), "source": f"{source}:{hk}", "n_trials": n_trials,
                                 "stats": {k: v.get(k) for k in STATS}, "yearly": v.get("yearly"), "periods": v.get("periods"),
                                 "holdings": _holdings(v.get("holdings")), "generated_at": generated})
        if source == "rev3" and table and "bench" in table:
            v = table["bench"]
            rows.append({"strategy": "bench", "size": 0, "month": int(m), "source": "rev3:bench", "n_trials": None,
                         "stats": {k: v.get(k) for k in STATS}, "yearly": v.get("yearly"), "periods": v.get("periods"),
                         "holdings": None, "generated_at": generated})
    if source == "rev3":
        for name, v in (doc.get("benchmarks") or {}).items():
            rows.append({"strategy": f"index:{name}", "size": 0, "month": 5, "source": "rev3:benchmarks", "n_trials": None,
                         "stats": {k: v.get(k) for k in STATS}, "yearly": v.get("yearly"), "periods": None, "holdings": None,
                         "generated_at": generated})
    return rows


def import_history(conn: psycopg.Connection, path: str | Path) -> int:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = history_rows_from_json(doc)
    with conn.cursor() as cur:
        for r in rows:
            cur.execute(
                """
                INSERT INTO idx.strategy_history (strategy, size, rebalance_month, source, n_trials, stats, yearly, periods, holdings, generated_at, imported_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                ON CONFLICT (strategy, size, rebalance_month) DO UPDATE SET source = EXCLUDED.source, n_trials = EXCLUDED.n_trials,
                    stats = EXCLUDED.stats, yearly = EXCLUDED.yearly, periods = EXCLUDED.periods, holdings = EXCLUDED.holdings,
                    generated_at = EXCLUDED.generated_at, imported_at = now()
                """,
                (r["strategy"], r["size"], r["month"], r["source"], r["n_trials"], psycopg.types.json.Jsonb(r["stats"]),
                 psycopg.types.json.Jsonb(r["yearly"]), psycopg.types.json.Jsonb(r["periods"]), psycopg.types.json.Jsonb(r["holdings"]),
                 datetime.fromisoformat(r["generated_at"]) if r.get("generated_at") else datetime.now(UTC)))
    conn.commit()
    return len(rows)


COLS = ["strategy", "size", "rebalance_month", "source", "n_trials", "stats", "yearly", "periods", "holdings", "generated_at", "imported_at"]


def history(conn: psycopg.Connection, key: str | None = None, size: int | None = None) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute("""SELECT strategy, size, rebalance_month, source, n_trials, stats, yearly, periods, holdings, generated_at, imported_at
                         FROM idx.strategy_history WHERE (%s::text IS NULL OR strategy = %s) AND (%s::int IS NULL OR size = %s)
                        ORDER BY strategy, size, rebalance_month""", (key, key, size, size))
        rows = cur.fetchall()
    return [x if isinstance(x, dict) else dict(zip(COLS, x, strict=True)) for x in rows]


def catalog(conn: psycopg.Connection | None = None) -> list[dict[str, Any]]:
    """The catalog with each (size, month) record attached (stats + yearly, no holdings), plus the reference rows."""
    hist: dict[str, dict[str, dict[str, Any]]] = {}
    if conn is not None:
        for r in history(conn):
            hist.setdefault(r["strategy"], {}).setdefault(str(r["size"]), {})[str(r["rebalance_month"])] = {
                **r["stats"], "n_trials": r["n_trials"], "yearly": r["yearly"], "periods": r["periods"]}
    out = [{**{k: v for k, v in s.items() if k != "history"}, "sizes": [0, 10, 15], "records": hist.get(s["key"], {})} for s in CATALOG]
    for key, label in REFERENCE_LABELS.items():
        if key in hist:
            out.append({"key": key, "label": label, "status": "reference", "rule": "", "note": "", "params": None, "sizes": [0],
                        "records": hist[key]})
    for s in OVERLAYS:
        out.append({**{k: v for k, v in s.items() if k != "history"}, "params": None, "sizes": [0], "records": hist.get(s["key"], {})})
    return out
