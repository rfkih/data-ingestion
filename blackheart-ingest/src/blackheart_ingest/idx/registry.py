"""The desk registry: every edge the desk runs, what it is, and what it earned.

Phase 0 of the strategies + alert-stream plan (docs/superpowers/plans/2026-09-24-...). The catalog in ``strategies.py``
answers "which names does an annual book buy"; this answers the operator's question instead - *what is the desk running,
how good is the evidence, and where does the number come from*. One entry per edge, covering value, trend, overlays,
event trades, execution and allocation, plus the families research closed (the closed list is part of the honesty).

Two halves, deliberately kept apart:

  STATIC (here)   what the strategy IS: the rule in one paragraph, its falsifier (what would close it), its cadence,
                  which books may follow it, which studies are its evidence, which catalog family / overlay it maps to.
                  Reviewed by a person; changed in a commit.
  IMPORTED (db)   what it EARNED: CAGR, Sharpe, drawdown, window, robustness verdict, ROI rank, live book. Never typed
                  here. ``refresh_scorecard`` reads the newest ``roi_scorecard`` study from ``idx.study`` and writes
                  ``idx.strategy_state``; a page renders what that stored study computed, or nothing at all.

So a strategy with no study cannot show a performance figure - the rule that keeps the page honest as research moves.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

import psycopg

from .card import _rows

logger = logging.getLogger(__name__)

FAMILIES = ("value", "trend", "event", "ml", "overlay", "execution", "filter", "allocation")
STATUSES = ("live", "paper", "overlay", "research", "reference", "closed")
CADENCES = ("annual", "monthly", "daily", "open_window", "session", "event", "none")
SCORECARD_STUDY = "roi_scorecard"

# ---------------------------------------------------------------------------------------------------------- registry
# `roi` names this entry inside the scorecard study: ("ranked", key) for a book-level record, ("overlays", key) for an
# effect on top of one. `books` is a filter over idx.book (rule / trend_variant / flag), resolved live - not a list of
# ids that rots. `evidence` is the reading order for a person, most decisive first.
REGISTRY: list[dict[str, Any]] = [
    {
        "key": "value_strict", "label": "Value strict composite", "family": "value", "status": "live",
        "cadence": "annual", "roi": ("ranked", "value_strict"), "catalog": "strict",
        "rule": "Main and development boards, liquid, through a strict quality gate (ROE at least 10 %, audited profit this "
                "year and last, positive operating cash flow, debt at most 1.5 times equity, financials exempt); inside that "
                "pool rank the composite of earnings yield, book yield and dividend yield and hold the cheapest fifth, equal "
                "weight, rebalanced each May.",
        "falsifier": "A full cycle where the composite rank stops beating an equal-weight draw from its own strict pool, or a "
                     "placebo percentile under 95 on the next scorecard.",
        "books": {"rule": "annual", "strategy": "strict"},
        "runs_in": "candidates.py / scores.py, rebalance ticket each May",
        "evidence": [66, 47],
        "years": {"catalog": True},
        "note": "The only strategy with real fills (IPOT). Its 2020-26 window is one cycle; the 2023-26 half earned +13 % a "
                "year against +31 % in 2020-23 (study #66, re-run 2026-09-26).",
    },
    {
        "key": "trend_small", "label": "Trend: 60-day high on volume, small caps", "family": "trend", "status": "paper",
        "cadence": "daily", "roi": ("ranked", "trend_small_gated"),        # the deployed rule runs with the regime gate
        "rule": "A name in the small tier (liquid but not blue chip) that closes at a 60-day high, above its 200-day average, "
                "on at least 1.5 times its median volume. Ten slots, equal weight, exit on a 10 % trailing stop. Signals are "
                "drafted after the close; the fill belongs to the next open.",
        "falsifier": "Fills one session late - the same rule filled a day late falls from Sharpe 1.21 to 0.90 - or the long-run "
                     "base rate reasserting itself: 2005-19 on survivors earned 13 % a year, not the 28-29 % of 2020-26.",
        "books": {"rule": "trend", "trend_variant": "small"},
        "runs_in": "trend_book.py, nightly draft + scheduler",
        "evidence": [23, 22, 46, 44, 45],
        "years": {"study": 23, "path": ["results", "small", "years"], "unit": "fraction"},
        "note": "2020-26 is the best 6-year block for this rule in 22 years. Thirty exit variants were tested; none beat the "
                "10 % trail.",
    },
    {
        "key": "regime_gate", "label": "Regime gate: no new entry under the 200-day average", "family": "overlay",
        "status": "overlay", "cadence": "daily", "roi": ("overlays", "regime_gate"), "catalog": "overlay:regime",
        "rule": "While the COMPOSITE closes below its own 200-day average, the trend books take no new entry; held names keep "
                "their trailing stop. Set per book (regime filter), deployed on both trend books since 2026-09-22.",
        "falsifier": "A bear market where the gate neither shortens the drawdown nor holds the Sharpe - the return gain was "
                     "never robust, so only the drawdown claim is on trial.",
        # only trend and combined books: on a value (annual) book the same column is the regime EXIT (sell to cash), a
        # different rule with different evidence - that one belongs to regime_damper
        "books": {"flag": "regime_filter", "rules": ["trend", "combo"]},
        "runs_in": "overlay.index_regime + trend_book.hold_back",
        "evidence": [62, 63, 66, 64, 65],
        "note": "Adopted as a RISK rule only: the drawdown cut and the MA200 timing are real (placebo 95th percentile, "
                "exactly on the bar since the 2026-09-26 re-run), the "
                "return gain appears only in bear blocks.",
    },
    {
        "key": "combined_book", "label": "Combined book: value and trend, half each", "family": "value",
        "status": "research", "cadence": "annual", "roi": ("ranked", "combined_50_50_gated"),
        "rule": "Half the capital in the value strict composite, half in the gated trend book. The two sleeves correlate +0.36, "
                "so the pair clears the money rule that neither clears alone on drawdown.",
        "falsifier": "The correlation rising toward 1 in a drawdown, which is when the pairing has to earn its keep.",
        "books": None,
        "runs_in": "not a book yet - the operator's live split is 67 / 33",
        "evidence": [93, 66],
        "note": "All five weightings pass the money rule, but since the 2026-09-26 re-run the 50/50 split leads in only one "
                "of the two halves (PARTIAL).",
    },
    {
        "key": "gapfade", "label": "Gap-down fade at the open", "family": "event", "status": "paper",
        "cadence": "open_window", "roi": ("ranked", "gapfade_deployed"),
        "rule": "A liquid name (at least Rp 5 bn a day) that opens 7 % or more below the previous close is bought at the open; "
                "the five deepest gaps of the day fill five slots; everything is sold at the close the same day.",
        "falsifier": "The t-statistic on new events falling below 3.0, or the shallower -3 % cohort turning negative: the edge "
                     "is a boundary case that was pre-registered to be re-read as events accumulate.",
        "books": {"rule": "gapfade"},
        "runs_in": "gapfade.py, jobs 09:00 / 09:05 entry, 15:50 exit, evening settle",
        "evidence": [77, 87, 89, 86, 88],
        "note": "Twelve years of support across both auto-rejection regimes, but 93 % of the events are 2025-26. The live book "
                "trades a stricter subset than the backtest: the daily open is the first trade, not the auction.",
    },
    {
        "key": "ara_sell", "label": "Sell into the auto-rejection ceiling", "family": "overlay", "status": "overlay",
        "cadence": "session", "roi": ("overlays", "ara_sell"),
        "rule": "A held name that touches its upper auto-rejection limit is sold at that price rather than held through it. "
                "The desk watches for the touch every two minutes during the session and raises an alert.",
        "falsifier": "A year where holding through the ceiling beats selling at it - the claim is 7 of 7 years so far.",
        "books": None,
        "runs_in": "ara.py, jobs ara_watch 20:05 + ara_touch every 2 minutes",
        "evidence": [101],
        "note": "An exit rule, not an entry. Scope frozen by the operator on 2026-09-23: keep the watch and the alert, build "
                "nothing further on it.",
    },
    {
        "key": "exec_timing", "label": "Execution timing: where to place the order", "family": "execution",
        "status": "overlay", "cadence": "open_window", "roi": None,
        "rule": "For a trade already decided, the live order book says whether to rest at the bid or take the offer now: a buy "
                "that waits for the book to lean to the bid (queue imbalance at least 0.3, microprice above the mid) filled "
                "6 to 11 basis points better than hitting immediately.",
        "falsifier": "The lean losing its edge over a random wait on a fresh pair of sessions.",
        "books": None,
        "runs_in": "execwatch.py + /idx/ticket/{id}/exec, shown on both ticket screens",
        "evidence": [99, 74],
        "note": "Not a reason to trade and not a return strategy - it has no ROI rank. It improves the price of trades the "
                "books were taking anyway, which is why it survived costs when every other microstructure signal did not.",
    },
    {
        "key": "pit_growth_filter", "label": "Point-in-time growth as a loser filter", "family": "filter",
        "status": "research", "cadence": "none", "roi": None,
        "rule": "Among small caps resting in a sideways base, keep only those whose last published profit (or revenue) grew at "
                "least 20 % year on year, point in time. Used to drop names, never to pick them.",
        "falsifier": "The costed version already failed: as a standalone rule it produced too few trades and a 50 % drawdown "
                     "(0 of 4). It survives only as a filter on another rule's list.",
        "books": None,
        "runs_in": "quality.py gates; not wired into a book",
        "evidence": [27, 28, 29],
        "note": "The effect is on the left tail: median one-year return +0.7 % against -27 % for the control, crash rate 13 % "
                "against 43 %, robust in 4 of 4 neighbours.",
    },
    {
        "key": "ew3", "label": "Equal weight: IHSG, S&P 500, gold", "family": "allocation", "status": "research",
        "cadence": "monthly", "roi": ("ranked", "ew3_ihsg_sp_gold"),
        "rule": "A third each in the Indonesian index, the US index and gold, rebalanced monthly, in rupiah.",
        "falsifier": "A decade where the three legs correlate - the record leans on gold and the dollar working when the IHSG "
                     "does not.",
        "books": None,
        "runs_in": "research only (no book, no instrument chosen)",
        "evidence": [92],
        "note": "The longest window the desk has: 2006-2026, through 2008. Beta arranged well, not stock alpha.",
    },
    {
        "key": "regime_damper", "label": "Dampers on the value book: index regime and cash buffer", "family": "overlay",
        "status": "overlay", "cadence": "monthly", "roi": None, "catalog": "overlay:cash_buffer",
        "rule": "Two options set per book: sell to cash while the COMPOSITE is under its 200-day average, and hold 30 % of the "
                "book in cash (50 % while the stress detector is on).",
        "falsifier": "Already partly falsified as a return rule: the buffer missed the pre-registered return floor by two "
                     "points. Both stay as drawdown insurance, priced in return.",
        "books": {"flag": "value_damper"},
        "runs_in": "overlay.py, monthly check",
        "evidence": [],
        "note": "2008 flat instead of -36 %, 2020 -13 % instead of -47 %; costs 0 to 49 % of the return in calm years. "
                "Evidence predates the research store: research/IDX_TREND_OVERLAY_2026-09-13.md and IDX_CASH_BUFFER_2026-09-14.md.",
    },
    # ---- added 2026-09-25 with the Strategies page: the combined book's ML sleeve and cash floor, the paper agent,
    # the next-report forecast, and the families research closed since (their studies are the evidence) -------------
    {
        "key": "ml_rank", "label": "ML ranking with price confirmation", "family": "ml", "status": "live",
        "cadence": "daily", "roi": None,
        "rule": "The 5-day model's score, cost-aware: a signal when the smoothed expected excess pays twice the name's round trip, "
                "bought only after the price confirms (ens4: four confirmation levels, a quarter of the slot each), sold on a score "
                "swap or after 60 sessions.",
        "falsifier": "Live slippage per trade 50 bps or more worse than the paper twin, or the realised rank IC negative in most weeks.",
        "books": {"rule": "combo"},
        "runs_in": "combo_book.py (plan 21:10), intents.py session tick every minute (confirmations, the same-day stop), "
                   "ml/daily.py (the 5d model, 20:40)",
        "evidence": [160, 175, 154, 159],
        "note": "The combined book's ML sleeve; it had no registry entry before the Strategies page.",
    },
    {
        "key": "combo_live", "label": "Combined live book: gap-fade, trend and ML", "family": "ml", "status": "live",
        "cadence": "session", "roi": None,
        "rule": "One Rp 20 M cash pool: gap-fade 10 %, trend 5 % and ML 10 % of NAV per trade (ens4, same-day stop -5 %), no buy "
                "past a 70 % invested share.",
        "falsifier": "The live book trailing its paper twin by more than its backtest's noise over three months, or a drawdown "
                     "past the backtest's worst.",
        "books": {"rule": "combo"},
        "runs_in": "combo_book.py (plan 21:10, pre-open 08:30, gap entry 09:00), intents.py session tick every minute, "
                   "combo_expire 20:30",
        "evidence": [348, 282, 288, 166],
        "note": "Allocation 10/5/10 with the stop since 2026-09-26 (operator).",
    },
    {
        "key": "cash_floor", "label": "Cash floor on the combined book", "family": "overlay", "status": "overlay",
        "cadence": "session", "roi": None,
        "rule": "No new buy in the combined book that would take the invested share above 100 % minus the floor.",
        "falsifier": "The floor cutting return without cutting the drawdown in live trading.",
        "books": {"flag": "combo_cash_floor"},
        "runs_in": "combo_book.invested_ok, before every buy",
        "evidence": [177],
        "note": "30 % on both combined books since 2026-09-25 (menu 34).",
    },
    {
        "key": "ml_agent", "label": "Online learning agent (paper)", "family": "ml", "status": "paper",
        "cadence": "session", "roi": None,
        "rule": "Five decisions a session over the tick feed's names: a bracket or nothing, bought only when the pessimistic expected "
                "reward clears +0.3 %; learns nightly from every name's counterfactual outcome.",
        "falsifier": "After 20 sessions and 30 trades: not beating the random agent by 0.5 pp a trade with t >= 2.",
        "books": None,
        "runs_in": "agent.py, jobs agent_decide / agent_settle",
        "evidence": [],
        "note": "Paper only, virtual Rp 20 M.",
    },
    {
        "key": "fund_forecast", "label": "Next-report forecast", "family": "ml", "status": "research",
        "cadence": "none", "roi": None,
        "rule": "Forecast the next quarterly report's profit direction and deterioration on the quarter's end date.",
        "falsifier": "The full-data run (FF-1b) not beating persistence where no same-year report is out.",
        "books": None, "runs_in": "research only", "evidence": [179],
        "note": "Preliminary on 40 % of the filings.",
    },
    {
        "key": "breakout_filter", "label": "Breakout hold-or-fail model", "family": "trend", "status": "closed",
        "cadence": "none", "roi": None, "rule": "A model of whether a trend breakout holds, as a filter on the trend book.",
        "falsifier": None, "books": None, "runs_in": "closed", "evidence": [180, 130],
        "note": "Closed 2026-09-25: the model is the distance above the level in disguise.",
    },
    {
        "key": "close_vwap", "label": "Close below VWAP", "family": "event", "status": "closed",
        "cadence": "none", "roi": None, "rule": "Buy closes dumped below the day's VWAP, sell the next session.",
        "falsifier": None, "books": None, "runs_in": "closed", "evidence": [182],
        "note": "Closed 2026-09-25: the dump carries information; one-day holds cannot pay IDX costs.",
    },
    {
        "key": "sideways", "label": "Sideways ranges", "family": "trend", "status": "closed",
        "cadence": "none", "roi": None, "rule": "Trade the floor, ceiling, break or dividend of names resting in a range.",
        "falsifier": None, "books": None, "runs_in": "closed", "evidence": [69, 68],
        "note": "Closed 2026-09-21.",
    },
    {
        "key": "bandarmologi", "label": "Broker accumulation", "family": "event", "status": "closed",
        "cadence": "none", "roi": None, "rule": "Follow names the broker tape labels as accumulated.",
        "falsifier": None, "books": None, "runs_in": "closed", "evidence": [18, 19, 16, 133],
        "note": "Closed 2026-09-17: accumulation precedes crashes as often as rises.",
    },
    # ---- reference rows: ranked by the scorecard, useful as yardsticks, not run by the desk -----------------------
    {
        "key": "trend_liq", "label": "Trend on the liquid tier", "family": "trend", "status": "reference",
        "cadence": "daily", "roi": ("ranked", "trend_liq"),
        "rule": "The same trend rule on the whole liquid tier instead of the small tier.", "falsifier": None,
        "books": None, "runs_in": "reference", "evidence": [23],
        "note": "Kept as the yardstick that shows where the small-cap cut earns its drawdown.",
    },
    {
        "key": "trend_small_base_rate", "label": "Trend, 2005-2019 survivors", "family": "trend", "status": "reference",
        "cadence": "none", "roi": ("ranked", "trend_small_2005_2019"),
        "rule": "The deployed trend rule run over 2005-2019 on the names Yahoo still carries.", "falsifier": None,
        "books": None, "runs_in": "reference", "evidence": [46],
        "note": "Survivorship-inflated and still the best long-run estimate the desk has: read 13 % a year as the base rate, "
                "not the 28-29 % of the recent block.",
    },
    {
        "key": "book_gold", "label": "Book 70 / gold 30", "family": "allocation", "status": "research",
        "cadence": "monthly", "roi": ("ranked", "book_gold_70_30"),
        "rule": "Seventy per cent in the combined book, thirty in gold, rebalanced monthly.",
        "falsifier": "Gold and the book falling together, which is the one case the 30 % leg is there for; or the Sharpe bar "
                     "clearing only because gold's 2020-26 run repeats, which it need not.",
        "books": None, "runs_in": "research only", "evidence": [92],
        "note": "Parked by the operator, who is running equities only.",
    },
    {
        "key": "gem_idr", "label": "Rupiah dual momentum", "family": "allocation", "status": "research",
        "cadence": "monthly", "roi": ("ranked", "gem_idr"),
        "rule": "Hold whichever of the Indonesian index, the US index or cash has the strongest 12-month return, in rupiah.",
        "falsifier": "A decade of whipsaws - the rule pays a switching cost each time the leader changes and earns nothing when "
                     "the ranking flips every few months.",
        "books": None, "runs_in": "research only", "evidence": [92],
        "note": "Robust over 2006-2026 and beaten by the equal-weight three.",
    },
]
BY_KEY = {e["key"]: e for e in REGISTRY}

# Families research closed, with the count of pre-registered trials that closed them. Shown so the page cannot read as a
# list of everything that works with the failures quietly dropped. Sourced from the scorecard study's `closed` array.
CLOSED_NOTE = ("Eleven families were closed by pre-registered tests rather than abandoned; the scorecard study carries the "
               "list and the trial counts.")


def _book_filter_sql(f: dict[str, Any] | None) -> tuple[str, list[Any]]:
    """-> (SQL predicate, params). None = the entry has no book side at all; {} = a filter that selects nothing (never
    every book - an empty predicate here would quietly claim the whole desk follows this strategy)."""
    if f is None:
        return "", []
    where, params = [], []
    for col in ("rule", "strategy", "trend_variant"):
        if f.get(col):
            where.append(f"b.{col} = %s")
            params.append(f[col])
    if f.get("rules"):
        where.append("b.rule = ANY(%s)")
        params.append(list(f["rules"]))
    flag = f.get("flag")
    if flag == "regime_filter":
        where.append("b.regime_filter")
    elif flag == "cash_floor_pct":
        where.append("b.cash_floor_pct > 0")
    elif flag == "value_damper":                  # a value book with the regime exit or a cash buffer switched on
        where.append("b.rule = 'annual' AND (b.regime_filter OR b.cash_floor_pct > 0)")
    elif flag == "combo_cash_floor":
        where.append("b.rule = 'combo' AND coalesce((b.params->>'cash_floor')::numeric, 0) > 0")
    return (" AND ".join(where) if where else "false"), params


def books_following(conn: psycopg.Connection, key: str) -> list[dict[str, Any]]:
    """Live answer to "who follows this", from idx.book - never a hard-coded list of book ids. Archived books are
    not following anything, so they are left out."""
    e = BY_KEY.get(key)
    if e is None or not e.get("books"):
        return []
    where, params = _book_filter_sql(e["books"])
    cols = ["book", "label", "kind", "rule", "strategy", "trend_variant", "archived"]
    return _rows(conn, f"""
        SELECT b.book, b.label, CASE WHEN b.book LIKE 'paper%%' THEN 'paper' ELSE 'live' END AS kind,
               b.rule, b.strategy, b.trend_variant, false AS archived
          FROM idx.book b WHERE b.archived_at IS NULL AND ({where}) ORDER BY b.book""", params, cols)


# ------------------------------------------------------------------------------------------- scorecard import
def _num(v: Any) -> float | None:
    """A scorecard figure is a number, or a dict of variant -> number (then: the deployed-config one, else the first)."""
    if isinstance(v, int | float):
        return float(v)
    if isinstance(v, dict):
        for k in ("deployed", "89", "full_span_2021_26"):
            if isinstance(v.get(k), int | float):
                return float(v[k])
        for x in v.values():
            if isinstance(x, int | float):
                return float(x)
    return None


def _live_book(v: Any) -> str | None:
    """The scorecard writes `live` as a book row, a book id, or a dash for "no book"."""
    if isinstance(v, dict):
        return v.get("book")
    if isinstance(v, str) and v.strip() not in ("", "-"):
        return v.strip()
    return None


def scorecard_from_study(summary: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any] | None:
    """Pull one registry entry's record out of a roi_scorecard summary. None when the study says nothing about it."""
    roi = entry.get("roi")
    if not roi:
        return None
    block, name = roi
    if block == "ranked":
        row = next((r for r in (summary.get("ranked") or []) if r.get("key") == name), None)
        if row is None:
            return None
        return {"cagr_pct": _num(row.get("cagr_pct")), "sharpe": _num(row.get("sharpe")), "mdd_pct": _num(row.get("mdd_pct")),
                "window": row.get("window"), "verdict": row.get("status"), "roi_rank": row.get("rank"),
                "live": _live_book(row.get("live")), "label": row.get("label"), "caveat": row.get("caveat"),
                "sources": [s for s in (row.get("sources") or []) if isinstance(s, int)]}
    row = (summary.get("overlays") or {}).get(name)
    if row is None:
        return None
    src = row.get("sources") or ([row["source"]] if isinstance(row.get("source"), int) else [])
    return {"effect": row.get("effect"), "verdict": row.get("verdict") or row.get("status"),
            "years_consistent": row.get("years_consistent"), "sources": [s for s in src if isinstance(s, int)]}


def latest_scorecard(conn: psycopg.Connection) -> dict[str, Any] | None:
    rows = _rows(conn, "SELECT id, as_of, summary FROM idx.study WHERE name = %s ORDER BY as_of DESC, id DESC LIMIT 1",
                 (SCORECARD_STUDY,), ["id", "as_of", "summary"])
    return rows[0] if rows else None


def refresh_scorecard(conn: psycopg.Connection) -> dict[str, Any]:
    """Re-import every entry's record from the newest ROI scorecard study into idx.strategy_state. Idempotent."""
    study = latest_scorecard(conn)
    if study is None:
        logger.warning("idx registry: no %s study stored; nothing to import", SCORECARD_STUDY)
        return {"study": None, "written": 0, "with_record": 0}
    summary = study["summary"] or {}
    written = with_record = 0
    with conn.cursor() as cur:
        for e in REGISTRY:
            sc = scorecard_from_study(summary, e)
            evidence = sorted({*(e.get("evidence") or []), *((sc or {}).get("sources") or [])})
            cur.execute("""INSERT INTO idx.strategy_state (key, status, scorecard, evidence, source_study, note, refreshed_at)
                           VALUES (%s, %s, %s, %s, %s, %s, now())
                           ON CONFLICT (key) DO UPDATE SET status = EXCLUDED.status, scorecard = EXCLUDED.scorecard,
                               evidence = EXCLUDED.evidence, source_study = EXCLUDED.source_study, note = EXCLUDED.note,
                               refreshed_at = now()""",
                        (e["key"], e["status"], psycopg.types.json.Jsonb(sc) if sc else None, evidence, study["id"], e.get("note")))
            written += 1
            with_record += 1 if sc else 0
    conn.commit()
    logger.info("idx registry: imported %d entries (%d with a record) from study #%s", written, with_record, study["id"])
    return {"study": study["id"], "as_of": str(study["as_of"]), "written": written, "with_record": with_record}


# ------------------------------------------------------------------------------------- the per-year record
# Each study shapes its own summary, so there is no generic "give me the yearly returns" - an entry names the path into
# its own evidence instead (reviewed once, here), and an entry with no such path simply has no yearly row on the page.

def _dig(doc: Any, path: list[Any]) -> Any:
    for step in path:
        if isinstance(doc, dict):
            doc = doc.get(step)
        elif isinstance(doc, list) and isinstance(step, int) and -len(doc) <= step < len(doc):
            doc = doc[step]
        else:
            return None
        if doc is None:
            return None
    return doc


def years_for(conn: psycopg.Connection, entry: dict[str, Any]) -> dict[str, Any] | None:
    """-> {"source": "study #23" | "research record", "years": {year: percent}} or None when nothing stored has one."""
    spec = entry.get("years")
    if not spec:
        return None
    if spec.get("catalog"):
        from . import strategies
        rows = [r for r in strategies.history(conn, entry["catalog"]) if r.get("size") in (None, 0)]
        row = next((r for r in rows if (r.get("yearly") or {})), None)
        if row is None:
            return None
        years = {str(k): float(v) for k, v in (row["yearly"] or {}).items() if v is not None}
        return {"source": "research record", "years": years} if years else None
    raw = _dig(_study_summary(conn, spec["study"]) or {}, list(spec["path"]))
    if not isinstance(raw, dict) or not raw:
        return None
    mult = 100.0 if spec.get("unit") == "fraction" else 1.0
    return {"source": f"study #{spec['study']}", "years": {str(k): float(v) * mult for k, v in raw.items() if v is not None}}


def _study_summary(conn: psycopg.Connection, study_id: int) -> dict[str, Any] | None:
    rows = _rows(conn, """SELECT s.summary FROM idx.study_current c JOIN idx.study s ON s.id = c.current_id
                          WHERE c.id = %s""", (study_id,), ["summary"])       # a re-run study reads from its latest run
    return rows[0]["summary"] if rows else None


# ------------------------------------------------------------------------------------------------------- read
def _state(conn: psycopg.Connection) -> dict[str, dict[str, Any]]:
    rows = _rows(conn, "SELECT key, status, scorecard, evidence, source_study, refreshed_at FROM idx.strategy_state",
                 (), ["key", "status", "scorecard", "evidence", "source_study", "refreshed_at"])
    return {r["key"]: r for r in rows}


def _iso(v: Any) -> Any:
    return v.isoformat() if isinstance(v, date | datetime) else v


def _entry(e: dict[str, Any], st: dict[str, Any] | None) -> dict[str, Any]:
    out = {k: v for k, v in e.items() if k != "roi"}
    out["scorecard"] = (st or {}).get("scorecard")
    out["evidence"] = (st or {}).get("evidence") or e.get("evidence") or []
    out["refreshed_at"] = _iso((st or {}).get("refreshed_at"))
    out["source_study"] = (st or {}).get("source_study")
    out["has_record"] = bool(out["scorecard"])
    return out


def today_for(conn: psycopg.Connection, key: str) -> dict[str, Any]:
    """What this strategy is saying right now: the signals of its most recent run, and its open rows on the alert bus
    (during the open window that includes the live placement reads). Nothing here is a decision - the signals are what
    the rule saw, the alerts are what the desk was told."""
    from . import runlog, signals
    last = _rows(conn, "SELECT max(as_of) AS d FROM idx.strategy_signal WHERE strategy = %s", (key,), ["d"])
    as_of = last[0]["d"] if last and last[0]["d"] else None
    rows = signals.latest(conn, key, as_of=as_of, limit=500) if as_of else []   # the whole day, not its first forty
    alerts = runlog.open_alerts(conn, 40, strategy=key)
    return {"as_of": _iso(as_of),
            "signals": [{**r, "as_of": _iso(r["as_of"]), "created_at": _iso(r["created_at"]),
                         "ref_price": (str(r["ref_price"]) if r["ref_price"] is not None else None),
                         "size_pct": (str(r["size_pct"]) if r["size_pct"] is not None else None)} for r in rows],
            "alerts": [{**a, "ts": _iso(a["ts"]), "valid_until": _iso(a["valid_until"]),
                        "acknowledged_at": _iso(a.get("acknowledged_at"))} for a in alerts]}


def desk(conn: psycopg.Connection) -> dict[str, Any]:
    """The whole registry with its imported records and the books following each entry."""
    st = _state(conn)
    entries = []
    for e in REGISTRY:
        row = _entry(e, st.get(e["key"]))
        row["books"] = books_following(conn, e["key"])
        entries.append(row)
    study = latest_scorecard(conn)
    closed = ((study or {}).get("summary") or {}).get("closed") or []
    return {"strategies": entries, "families": list(FAMILIES), "statuses": list(STATUSES),
            "closed": {"note": CLOSED_NOTE, "families": closed},
            "scorecard_study": (study or {}).get("id"), "scorecard_as_of": _iso((study or {}).get("as_of"))}


def detail(conn: psycopg.Connection, key: str) -> dict[str, Any] | None:
    """One entry, its books, and the studies behind it (id, name, date, note, report) in reading order."""
    e = BY_KEY.get(key)
    if e is None:
        return None
    st = _state(conn)
    row = _entry(e, st.get(key))
    row["books"] = books_following(conn, key)
    ids = row["evidence"]
    studies = []
    if ids:
        found = {r["id"]: r for r in _rows(conn, """
            SELECT c.id, s.name, s.as_of, s.note, s.report_path, c.current_id FROM idx.study_current c
              JOIN idx.study s ON s.id = c.current_id WHERE c.id = ANY(%s)""", (list(ids),),
            ["id", "name", "as_of", "note", "report_path", "current_id"])}
        studies = [{**found[i], "as_of": _iso(found[i]["as_of"])} for i in ids if i in found]
    row["studies"] = studies
    row["yearly"] = years_for(conn, e)
    row["today"] = today_for(conn, key)
    if e.get("catalog"):                                      # the annual families keep their per-size research record
        from . import strategies
        row["catalog_history"] = [{k: _iso(v) for k, v in r.items()} for r in strategies.history(conn, e["catalog"])]
    return row
