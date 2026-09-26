# ruff: noqa: RUF001, RUF002  - the page's copy uses the typographic minus and en dash
"""strategy_page / strategy_options: round trips, equity stats, option adapters and validation, the content's integrity, and
the versioned write path against a throwaway book."""
from __future__ import annotations

import json
import os
import re
from datetime import date

import psycopg
import pytest

from blackheart_ingest.idx import registry as reg
from blackheart_ingest.idx import strategy_options as so
from blackheart_ingest.idx import strategy_page as sp
from blackheart_ingest.idx import study_figures as sf
from blackheart_ingest.idx.strategy_page_content import PAGES

VERDICTS = {"Adopted", "Rejected", "Inconclusive", "Running"}


# ---- content -------------------------------------------------------------------------------------------------------------
def test_every_page_is_a_registry_entry_with_a_valid_family_and_verdicts():
    for key, p in PAGES.items():
        assert key in reg.BY_KEY, f"{key} has page content but no registry entry"
        assert p["family"] in sp.FAMILY_LABEL
        assert p.get("one") and p.get("what"), key
        for r in p.get("research", []):
            assert r["verdict"] in VERDICTS, (key, r["title"])
            assert r.get("study") or r.get("date"), (key, r["title"])
        titles = {r["title"] for r in p.get("research", [])}
        for opt, title in p.get("findings", {}).items():
            assert title in titles, f"{key}.findings[{opt}] names no study on the page"
    assert sp.page_keys()[0] in PAGES


# Result-shaped numbers typed into prose: an "N of M" count, a figure named Sharpe / AUC / t / lift / hit rate / drawdown, bps,
# %/yr, points, or a return "a year" / "a trade". Rule settings ("a 10 % trail", "1.5 times its volume", "the 0.5 % round trip")
# and years stay allowed - they are the rule, not its result.
_TYPED_RESULT = re.compile(
    r"\d+ of \d+|(Sharpe|AUC|IC|t-statistic|lift|hit rate|win rate|max DD|drawdown)\s+(of\s+)?[+−-]?\d|\d\s*bps|\d\s*%/yr|\d\s*pts"
    r"|[+−-]?\d+(\.\d+)?\s*%\s*(a year|a trade)")


def _outside(text: str) -> str:
    return re.sub(r"\{[^}]*\}", "", text or "")


def test_result_figures_are_read_from_studies_not_typed():
    for key, p in PAGES.items():
        for r in p.get("research", []):
            figs = r.get("figs") or {}
            for field in ("found", "n"):
                assert not _TYPED_RESULT.search(_outside(r.get(field))), (key, r["title"], field, r.get(field))
                for name in sf.placeholders(r.get(field) or ""):
                    assert name in figs, f"{key} / {r['title']}: {{{name}}} has no spec"
            if not r.get("study"):
                assert not figs and not sf.placeholders(r["found"]), f"{key} / {r['title']}: figures need a stored study"
        page_figs = p.get("figs") or {}
        texts = [p.get("what") or ""] + [v for _, v in p.get("how", [])] + [v for _, v in p.get("detail", [])]
        for t in texts:
            assert not _TYPED_RESULT.search(_outside(t)), (key, t)
            for name in sf.placeholders(t):
                assert name in page_figs and page_figs[name][0] in ("study", "live"), f"{key}: {{{name}}} needs S(...) or LIVE(...)"
        for spec in page_figs.values():
            if spec[0] == "live":
                assert spec[1] in sp.LIVE_FIGS, spec


def test_study_figure_specs():
    s = {"arms": {"a": {"verdict": "no: x", "cagr": 0.291, "t": 2.97}, "b": {"verdict": "BETTER", "cagr": 0.20},
                  "c|d": {"mdd": -0.214}}, "years": [2015, 2026], "k/1": {"v": 3}, "verdict": "ROBUST"}
    assert sf.evaluate(sf.PCT("arms/a/cagr", 1, sign=True), s) == "+29.1"
    assert sf.evaluate(sf.PCT("arms/c|d/mdd", 0), s) == "−21"
    assert sf.evaluate(sf.PCT("arms/c|d/mdd", 0, absval=True), s) == "21"
    assert sf.evaluate(sf.V("arms/a/t", 2), s) == "2.97"
    assert sf.evaluate(sf.YEAR("years/-1"), s) == "2026"
    assert sf.evaluate(sf.LEN("arms"), s) == "3"
    assert sf.evaluate(sf.COUNT("arms", ("prefix", "no"), "verdict"), s) == "1"
    assert sf.evaluate(sf.COUNT("arms", ("not_prefix", "no"), "verdict"), s) == "1"     # an arm with no verdict is not counted
    assert sf.evaluate(sf.DIFF("arms/a/cagr", "arms/b/cagr", 1, 100), s) == "9.1"
    assert sf.evaluate(sf.V(("k/1", "v"), 0), s) == "3"                                 # a key holding "/" via a tuple path
    assert sf.evaluate(sf.TEXT("verdict"), s) == "Robust"
    assert sf.evaluate(sf.V("arms/zz/cagr"), s) is None
    text, missing = sf.render("{a} %/yr, {b}", {"a": sf.PCT("arms/a/cagr"), "b": sf.V("nope")}, s)
    assert text == "29.1 %/yr, –" and missing == ["b"]
    assert sf.render("{a}", {"a": sf.V("x")}, None) == ("–", ["a"])                     # the study row is gone


# ---- round trips and stats -----------------------------------------------------------------------------------------------
def test_fifo_pairs_lots_and_spreads_fees():
    fills = [{"code": "AAA", "side": "buy", "lots": 10, "price": 100, "fee": 10, "d": date(2026, 9, 1)},
             {"code": "AAA", "side": "buy", "lots": 10, "price": 120, "fee": 10, "d": date(2026, 9, 2)},
             {"code": "AAA", "side": "sell", "lots": 15, "price": 130, "fee": 30, "d": date(2026, 9, 5), "reason": "trail"}]
    t = sp._fifo(fills)
    assert [x["entry"] for x in t] == [100, 120] and [x["exit"] for x in t] == [130, 130]
    assert round(t[0]["cost"], 2) == 10 * 100 * 100 + 10 and round(t[0]["pnl"], 2) == 10 * 100 * 130 - 20 - (100000 + 10)
    assert round(t[1]["cost"], 2) == 5 * 100 * 120 + 5 and t[1]["reason"] == "trail"


def test_equity_stats_drawdown_and_the_one_year_rule():
    eq = [100, 110, 99, 105, 120]
    st = sp._equity_stats(["d"] * 5, eq)
    assert round(st["total"], 6) == 20 and round(st["mdd"], 6) == round((99 / 110 - 1) * 100, 6) and st["mdd_long"] == 2
    assert st["cagr"] is None and st["sharpe"] is None                  # fewer than a year of sessions: not annualised


# ---- options -------------------------------------------------------------------------------------------------------------
COMBO = {"rule": "combo", "regime_filter": True, "params": {"sleeves": {"trend": 0.05, "ml": 0.05, "gap": 0.10}, "cash_floor": 0.3}}


def test_options_per_rule_and_the_two_regime_meanings():
    assert [o.key for o in so.options_for("trend_small", COMBO)] == ["on", "size", "regime_gate"]
    assert "confirm" in [o.key for o in so.options_for("ml_rank", COMBO)]
    assert [o.key for o in so.options_for("trend_small", {"rule": "trend", "regime_filter": True})] == ["regime_gate"]
    value = [o.key for o in so.options_for("value_strict", {"rule": "annual"})]
    assert "regime_exit" in value and "regime_gate" not in value         # same column, different rule, different option
    assert so.options_for("gapfade", {"rule": "gapfade"}) == []


def test_option_reads_and_patches_go_through_the_combined_books_validation():
    size = next(o for o in so.options_for("ml_rank", COMBO) if o.key == "size")
    assert size.read(COMBO) == 5.0
    assert size.patch(COMBO, 7.5)["params"]["sleeves"]["ml"] == 0.075
    with pytest.raises(ValueError):
        so.coerce(size, 80)                                               # above the 50 % bound
    on = next(o for o in so.options_for("gapfade", COMBO) if o.key == "on")
    assert on.patch(COMBO, False)["params"]["off"] == ["gap"] and on.read({**COMBO, **on.patch(COMBO, False)}) is False
    floor = so.options_for("cash_floor", COMBO)[0]
    assert floor.read(COMBO) == 30.0 and floor.scope == "portfolio"
    assert so.fmt(floor, 30.0) == "30%" and so.coerce(floor, "25") == 25.0
    tp = next(o for o in so.options_for("value_strict", {"rule": "annual"}) if o.key == "take_profit")
    assert so.coerce(tp, "") is None and so.fmt(tp, None) == "Off"
    stop = next(o for o in so.options_for("ml_rank", COMBO) if o.key == "stop")          # ML-9 (#281): off unless set
    assert stop.read(COMBO) is None and so.fmt(stop, None) == "Off"
    on5 = stop.patch(COMBO, 5)
    assert on5["params"]["ml"]["stop"] == 0.05 and stop.read({**COMBO, **on5}) == 5.0
    assert stop.patch({**COMBO, **on5}, "")["params"]["ml"]["stop"] is None
    with pytest.raises(ValueError):
        so.coerce(stop, 80)


# ---- the write path ------------------------------------------------------------------------------------------------------
@pytest.fixture()
def conn():
    dsn = os.environ.get("INGEST_DB_DSN")
    if not dsn:
        pytest.skip("INGEST_DB_DSN not set")
    try:
        c = psycopg.connect(dsn, connect_timeout=5)
    except Exception as e:
        pytest.skip(f"db unreachable: {e}")
    yield c
    c.close()


def test_every_quoted_figure_resolves_against_the_stored_studies(conn):
    """A study re-run with a different summary shape would print "–"; this names the figure instead of letting it slip."""
    for key in PAGES:
        for r in sp.research(conn, key):
            assert not r["missing"], f"{key} / {r['title']}: not in the stored summary: {r['missing']}"
        page = PAGES[key]
        vals = sp._page_vals(conn, page, sp._studies(conn, sp._page_study_ids(page)))
        assert all(v is not None for v in vals.values()), (key, vals)


BOOK = "test_strategy_page"


def _clean(c):
    with c.cursor() as cur:
        cur.execute("DELETE FROM idx.strategy_config_version WHERE book = %s", (BOOK,))
        cur.execute("DELETE FROM idx.book WHERE book = %s", (BOOK,))
    c.commit()


def test_set_options_versions_and_refuses_a_stale_version(conn):
    _clean(conn)
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO idx.book (book, rule, strategy, regime_filter, params) VALUES (%s, 'combo', 'rule', true, %s)",
                        (BOOK, json.dumps({"sleeves": {"trend": 0.05, "ml": 0.05, "gap": 0.10}})))
        conn.commit()
        assert sp.current_version(conn, BOOK, "ml_rank") == 1
        with pytest.raises(ValueError, match="reason"):
            sp.set_options(conn, "ml_rank", BOOK, [{"option": "size", "value": 7.5, "reason": " "}], 1, "operator")
        conn.rollback()
        out = sp.set_options(conn, "ml_rank", BOOK, [{"option": "size", "value": 7.5, "reason": "test"}], 1, "operator")
        assert out["version"] == 2 and out["changes"][0]["from"] == "5%" and out["changes"][0]["to"] == "7.5%"
        with conn.cursor() as cur:
            cur.execute("SELECT params FROM idx.book WHERE book = %s", (BOOK,))
            assert cur.fetchone()[0]["sleeves"]["ml"] == 0.075
        with pytest.raises(LookupError):
            sp.set_options(conn, "ml_rank", BOOK, [{"option": "size", "value": 5, "reason": "again"}], 1, "operator")
        conn.rollback()
        with pytest.raises(ValueError, match="nothing changed"):
            sp.set_options(conn, "ml_rank", BOOK, [{"option": "size", "value": 7.5, "reason": "same"}], 2, "operator")
        conn.rollback()
    finally:
        conn.rollback()
        _clean(conn)
