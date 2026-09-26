# ruff: noqa: RUF001, RUF002  - display copy uses the typographic en dash, as the design does
"""The Strategies page (design "Blackridge Strategies.dc.html"): one read model per screen, assembled from what the desk
already stores. Nothing here invents a figure - a tab with no data says so, and the web shows "–".

  catalog()                  the list: every strategy the page shows, its status, family, headline backtest, live since start,
                             and the portfolios it runs in
  detail(key)                Overview, Research, Training, Options (per portfolio, with versions) and Timeline in one read
  performance(key, book)     one run's live curve and drawdown (book NAV, the combined book's sleeve attribution, or the agent)
  results(key)               trade lists per source - the imported backtest round trips and the paper/live round trips
  set_options(...)           the write path: validated through the book's own rules, recorded as a new version

Sources: registry.REGISTRY (what a strategy is) + strategy_page_content.PAGES (its prose), idx.book (where it runs and its
settings), idx.strategy_state / idx.study (headlines and studies), idx.ml_model / idx.agent_model (training), idx.fill +
idx.ticket_line (live trades, attributed by sleeve flags), idx.book_nav, idx.agent_decision, idx.alert,
idx.strategy_config_version, idx.strategy_backtest_trade.
"""
from __future__ import annotations

import csv
import json
import logging
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row, tuple_row

from . import combo_book as cb
from . import registry as reg
from . import strategy_options as so
from . import study_figures as sf
from .strategy_page_content import PAGES
from .ticket import is_live

logger = logging.getLogger(__name__)

FAMILY_LABEL = {"value": "Value", "trend": "Trend", "event": "Event", "ml": "ML", "overlay": "Overlay"}
AGENT_BOOK = "agent"                                  # the online agent's virtual book (idx.agent_decision), not an idx.book row
AGENT_CAPITAL = 20_000_000.0


def _q(conn: psycopg.Connection, sql: str, params: tuple | list = ()) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


def _f(x: Any) -> float | None:
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _iso(d: Any) -> str | None:
    if d is None:
        return None
    if isinstance(d, datetime):
        return d.date().isoformat()
    return d.isoformat() if hasattr(d, "isoformat") else str(d)


def page_keys() -> list[str]:
    """The strategies the page shows: every registry entry that has page content, in registry order."""
    return [e["key"] for e in reg.REGISTRY if e["key"] in PAGES]


# ---------------------------------------------------------------------------------------------------------------- runs
def _books(conn: psycopg.Connection) -> list[dict[str, Any]]:
    return _q(conn, """SELECT book, label, rule, strategy, trend_variant, regime_filter, entry_gate, take_profit_pct, trend_exit,
                              cash_floor_pct, max_names, params, created_at, status
                         FROM idx.book WHERE archived_at IS NULL AND book NOT LIKE 'test%%' ORDER BY created_at""")


def _in_filter(conn: psycopg.Connection, key: str) -> set[str]:
    e = reg.BY_KEY.get(key)
    if not e or not e.get("books"):
        return set()
    where, params = reg._book_filter_sql(e["books"])
    if not where:
        return set()
    return {r["book"] for r in _q(conn, f"SELECT b.book FROM idx.book b WHERE b.archived_at IS NULL AND {where}", params)}


def _sleeve_active(b: dict[str, Any], sleeve: str) -> bool:
    """A combined book runs a sleeve unless it was removed (size 0 AND off - the portfolio screen's 'remove')."""
    try:
        s = cb.settings(b)
    except ValueError:
        return False
    return not (s["sizes"].get(sleeve, 0) == 0 and sleeve in s["off"])


def runs(conn: psycopg.Connection, key: str, books: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Where a strategy runs: one row per portfolio, live before paper, oldest first."""
    page = PAGES.get(key, {})
    books = books if books is not None else _books(conn)
    by = {b["book"]: b for b in books}
    names = set(_in_filter(conn, key))
    sleeve = page.get("sleeve")
    if sleeve:
        names |= {b["book"] for b in books if b["rule"] == "combo" and _sleeve_active(b, sleeve)}
    out = [{"book": n, "label": by[n]["label"] or n, "live": is_live(n), "rule": by[n]["rule"], "since": _iso(by[n]["created_at"])}
           for n in names if n in by]
    if key == "ml_agent":
        first = _q(conn, "SELECT min(fitted_at) AS d FROM idx.agent_model")
        if first and first[0]["d"]:
            out.append({"book": AGENT_BOOK, "label": "Agent paper book", "live": False, "rule": "agent", "since": _iso(first[0]["d"])})
    return sorted(out, key=lambda r: (not r["live"], r["since"] or "", r["book"]))


def status_of(key: str, rs: list[dict[str, Any]]) -> str:
    page = PAGES.get(key, {})
    if page.get("status"):
        return page["status"]
    e = reg.BY_KEY.get(key, {})
    if e.get("status") == "closed":
        return "closed"
    if any(r["live"] for r in rs):
        return "live"
    if rs:
        return "paper"
    return "research"


# ---------------------------------------------------------------------------------------------------------------- headline
def _pct(v: Any) -> float | None:
    """A study stores CAGR/mDD either as a fraction (0.346) or in percent (34.6); the page speaks percent."""
    x = _f(v)
    if x is None:
        return None
    return x * 100 if abs(x) <= 3 else x


def _node(summary: Any, path: list[str]) -> Any:
    for p in path:
        summary = summary.get(p) if isinstance(summary, dict) else None
    return summary


def headline(conn: psycopg.Connection, key: str) -> dict[str, Any] | None:
    """The list's backtest figure: {cagr, mdd} for a strategy that trades, {text, sub} for an overlay's EFFECT (what it did to
    the strategies it sits on), read from where it is stored."""
    h = PAGES.get(key, {}).get("headline")
    if not h:
        return None
    if "state" in h:
        rows = _q(conn, "SELECT scorecard FROM idx.strategy_state WHERE key = %s", (h["state"],))
        sc = rows[0]["scorecard"] if rows and rows[0]["scorecard"] else None
        if not sc:
            return None
        if sc.get("cagr_pct") is not None:
            return {"cagr": _f(sc.get("cagr_pct")), "mdd": _f(sc.get("mdd_pct")), "sharpe": _f(sc.get("sharpe")),
                    "window": sc.get("window"), "study": (sc.get("sources") or [None])[0]}
        if sc.get("effect"):                                           # an overlay: "mDD -30% -> -18%; return gain not robust"
            head, _, rest = str(sc["effect"]).partition(";")
            return {"text": head.strip().replace("mDD", "max DD").replace("->", "→"), "sub": rest.strip() or sc.get("verdict"),
                    "study": (sc.get("sources") or [None])[0]}
        return None
    rows = _q(conn, """SELECT s.summary FROM idx.study_current c JOIN idx.study s ON s.id = c.current_id
                        WHERE c.id = %s""", (h["study"],))
    if not rows:
        return None
    if "arm" in h:                                                     # an overlay measured against the book without it
        base, arm = _node(rows[0]["summary"], h["base"]), _node(rows[0]["summary"], h["arm"])
        if not isinstance(base, dict) or not isinstance(arm, dict):
            return None
        b_c, a_c, b_d, a_d = _pct(base.get("cagr")), _pct(arm.get("cagr")), _pct(base.get("mdd")), _pct(arm.get("mdd"))
        if None in (b_c, a_c, b_d, a_d):
            return None
        return {"text": f"max DD {b_d:.0f}% → {a_d:.0f}%", "sub": f"{a_c - b_c:+.1f} pts /yr", "study": h["study"]}
    node = _node(rows[0]["summary"], h.get("path", []))
    if not isinstance(node, dict):
        return None
    return {"cagr": _pct(node.get(h.get("cagr", "cagr"))), "mdd": _pct(node.get(h.get("mdd", "mdd"))), "sharpe": _f(node.get("sharpe")),
            "study": h["study"], "window": None}


# ---------------------------------------------------------------------------------------------------------------- trades
def _fifo(fills: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Round trips from fills (code, side, lots, price, fee, d, reason), first in first out, fees spread by lots."""
    open_: dict[str, list[dict[str, Any]]] = defaultdict(list)
    out = []
    for f in fills:
        lots, px, fee = float(f["lots"]), float(f["price"]), float(f.get("fee") or 0)
        if lots <= 0:
            continue
        if f["side"] == "buy":
            open_[f["code"]].append({"lots": lots, "px": px, "fee": fee, "d": f["d"]})
            continue
        left, fee_per = lots, fee / lots
        while left > 1e-9 and open_[f["code"]]:
            lot = open_[f["code"]][0]
            take = min(left, lot["lots"])
            buy_fee = lot["fee"] * take / lot["lots"] if lot["lots"] else 0.0
            cost = take * 100 * lot["px"] + buy_fee
            proceeds = take * 100 * px - fee_per * take
            out.append({"code": f["code"], "d_in": _iso(lot["d"]), "d_out": _iso(f["d"]), "entry": lot["px"], "exit": px,
                        "cost": cost, "pnl": proceeds - cost, "ret": (proceeds / cost - 1) * 100 if cost else 0.0, "reason": f.get("reason")})
            lot["fee"] -= buy_fee
            lot["lots"] -= take
            left -= take
            if lot["lots"] <= 1e-9:
                open_[f["code"]].pop(0)
    return out


def _book_fills(conn: psycopg.Connection, book: str, sleeve: str | None) -> list[dict[str, Any]]:
    """A book's fills in order; for a combined book only the ones whose ticket line carries this sleeve's flag."""
    if sleeve:
        return _q(conn, """SELECT f.code, f.side, f.lots, f.price, f.fee, f.trade_date AS d, l.reason
                             FROM idx.fill f JOIN idx.ticket_line l ON l.fill_id = f.id
                            WHERE f.book = %s AND %s = ANY(l.flags) ORDER BY f.trade_date, f.id""", (book, f"sleeve:{sleeve}"))
    return _q(conn, """SELECT f.code, f.side, f.lots, f.price, f.fee, f.trade_date AS d,
                              (SELECT l.reason FROM idx.ticket_line l WHERE l.fill_id = f.id LIMIT 1) AS reason
                         FROM idx.fill f WHERE f.book = %s AND f.source <> 'corporate_action' ORDER BY f.trade_date, f.id""", (book,))


def run_trades(conn: psycopg.Connection, key: str, book: str) -> list[dict[str, Any]]:
    if book == AGENT_BOOK:
        rows = _q(conn, """SELECT code, d, (exit_at AT TIME ZONE 'Asia/Jakarta')::date AS d_out, entry_px, exit_px, lots, pnl, reward, exit_reason
                             FROM idx.agent_decision WHERE agent = 'ts' AND settled_at IS NOT NULL AND exit_reason <> 'no_fill' ORDER BY exit_at""")
        why = {"tp": "Take-profit", "sl": "Stop", "time": "Holding time"}
        return [{"code": r["code"], "d_in": _iso(r["d"]), "d_out": _iso(r["d_out"] or r["d"]), "entry": _f(r["entry_px"]), "exit": _f(r["exit_px"]),
                 "cost": (_f(r["entry_px"]) or 0) * (r["lots"] or 0) * 100, "pnl": _f(r["pnl"]) or 0.0, "ret": (_f(r["reward"]) or 0) * 100,
                 "reason": why.get(r["exit_reason"], r["exit_reason"])} for r in rows]
    b = _q(conn, "SELECT rule FROM idx.book WHERE book = %s", (book,))
    sleeve = PAGES.get(key, {}).get("sleeve") if b and b[0]["rule"] == "combo" else None
    return _fifo(_book_fills(conn, book, sleeve))


# ---------------------------------------------------------------------------------------------------------------- series
def _equity_stats(dates: list[str], eq: list[float]) -> dict[str, Any]:
    """Portfolio figures from a series of values indexed to 100 at the start."""
    if len(eq) < 2:
        return {"total": 0.0, "cagr": None, "mdd": 0.0, "mdd_long": 0, "vol": None, "sharpe": None, "sortino": None}
    peak, mdd, run, longest = eq[0], 0.0, 0, 0
    for v in eq:
        peak = max(peak, v)
        dd = v / peak - 1
        mdd = min(mdd, dd)
        run = run + 1 if dd < -1e-12 else 0
        longest = max(longest, run)
    rets = [eq[i] / eq[i - 1] - 1 for i in range(1, len(eq)) if eq[i - 1]]
    n = len(rets)
    mean = sum(rets) / n if n else 0.0
    sd = (sum((r - mean) ** 2 for r in rets) / max(1, n - 1)) ** 0.5 if n > 1 else 0.0
    down = [r for r in rets if r < 0]
    dsd = (sum(r * r for r in down) / max(1, len(down))) ** 0.5 if down else 0.0
    total = (eq[-1] / eq[0] - 1) * 100
    year = n >= 250
    return {"total": total, "cagr": ((eq[-1] / eq[0]) ** (250 / n) - 1) * 100 if year else None, "mdd": mdd * 100, "mdd_long": longest,
            "vol": sd * (250 ** 0.5) * 100 if n > 1 else None, "sharpe": (mean / sd * 250 ** 0.5) if year and sd else None,
            "sortino": (mean / dsd * 250 ** 0.5) if year and dsd else None}


def _closes(conn: psycopg.Connection, codes: list[str], d0: date) -> dict[str, dict[str, float]]:
    if not codes:
        return {}
    out: dict[str, dict[str, float]] = defaultdict(dict)
    for r in _q(conn, "SELECT code, trade_date, close FROM idx.bar WHERE source = 'idx' AND code = ANY(%s) AND trade_date >= %s",
                (codes, d0)):
        out[r["code"]][r["trade_date"].isoformat()] = float(r["close"])
    return out


def series(conn: psycopg.Connection, key: str, book: str) -> dict[str, Any] | None:
    """One run's daily value, indexed to 100 at its start. Book NAV for a book that is this strategy alone; the sleeve's fills
    marked to the close for a combined book; realised P&L for the agent. None when there is nothing to show yet."""
    if book == AGENT_BOOK:
        rows = _q(conn, """SELECT (exit_at AT TIME ZONE 'Asia/Jakarta')::date AS d, sum(pnl) AS pnl FROM idx.agent_decision
                            WHERE agent = 'ts' AND settled_at IS NOT NULL AND exit_at IS NOT NULL GROUP BY 1 ORDER BY 1""")
        if not rows:
            return None
        acc, dates, eq = 0.0, [], []
        for r in rows:
            acc += float(r["pnl"] or 0)
            dates.append(r["d"].isoformat())
            eq.append(100 * (1 + acc / AGENT_CAPITAL))
        return {"dates": dates, "live": eq, "capital": AGENT_CAPITAL}
    b = _q(conn, "SELECT rule, created_at, cash FROM idx.book WHERE book = %s", (book,))
    if not b:
        return None
    nav = _q(conn, "SELECT trade_date, nav FROM idx.book_nav WHERE book = %s ORDER BY trade_date", (book,))
    if b[0]["rule"] != "combo":
        if len(nav) < 2:
            return None
        n0 = float(nav[0]["nav"]) or 1.0
        return {"dates": [r["trade_date"].isoformat() for r in nav], "live": [100 * float(r["nav"]) / n0 for r in nav], "capital": n0}
    # a combined book: this sleeve's round trips and open lots, marked to each close, as a share of the book's first NAV
    sleeve = PAGES.get(key, {}).get("sleeve")
    if not sleeve or not nav:
        return None
    capital = float(nav[0]["nav"]) or float(b[0]["cash"] or 0) or 1.0
    fills = _book_fills(conn, book, sleeve)
    if not fills:
        return None
    d0 = nav[0]["trade_date"]
    codes = sorted({f["code"] for f in fills})
    px = _closes(conn, codes, d0)
    days = [r["trade_date"].isoformat() for r in nav]
    eq, pos, realized, fi = [], defaultdict(lambda: [0.0, 0.0]), 0.0, 0     # pos[code] = [lots, cost incl. fees]
    fills_sorted = sorted(fills, key=lambda f: f["d"])
    for d in days:
        while fi < len(fills_sorted) and fills_sorted[fi]["d"].isoformat() <= d:
            f = fills_sorted[fi]
            lots, p, fee = float(f["lots"]), float(f["price"]), float(f.get("fee") or 0)
            if f["side"] == "buy":
                pos[f["code"]][0] += lots
                pos[f["code"]][1] += lots * 100 * p + fee
            else:
                held, cost = pos[f["code"]]
                share = min(1.0, lots / held) if held else 0.0
                realized += lots * 100 * p - fee - cost * share
                pos[f["code"]] = [held - lots, cost * (1 - share)]
            fi += 1
        unreal = sum(n * 100 * px.get(c, {}).get(d, 0.0) - cost for c, (n, cost) in pos.items() if n > 0 and px.get(c, {}).get(d))
        eq.append(100 * (1 + (realized + unreal) / capital))
    return {"dates": days, "live": eq, "capital": capital}


# ---------------------------------------------------------------------------------------------------------------- options
def current_version(conn: psycopg.Connection, book: str, key: str) -> int:
    r = _q(conn, "SELECT max(version) AS v FROM idx.strategy_config_version WHERE book = %s AND strategy = %s", (book, key))
    return int(r[0]["v"]) if r and r[0]["v"] else 1


def _book_row(conn: psycopg.Connection, book: str) -> dict[str, Any]:
    from . import book as bk
    return bk.get_book(conn, book)


def options_view(conn: psycopg.Connection, key: str, run: dict[str, Any],
                 rendered: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    if run["book"] == AGENT_BOOK:
        return None
    b = _book_row(conn, run["book"])
    opts = so.options_for(key, b)
    if not opts:
        return None
    find = PAGES.get(key, {}).get("findings", {})
    research_by = {r["title"]: r for r in (rendered if rendered is not None else research(conn, key))}
    items = []
    for o in opts:
        try:
            v = o.read(b)
        except (ValueError, KeyError):
            v = None
        r = research_by.get(find.get(o.key, ""))
        items.append({**so.schema(o), "value": v, "text": so.fmt(o, v),
                      "finding": r["found"] if r else None, "study": r and {"title": r["title"], "id": r.get("study"), "verdict": r["verdict"]}})
    vs = _q(conn, """SELECT version, changes, actor, created_at FROM idx.strategy_config_version
                      WHERE book = %s AND strategy = %s ORDER BY version""", (run["book"], key))
    versions = [{"v": 1, "date": run["since"], "actor": None, "changes": []}] + [
        {"v": r["version"], "date": _iso(r["created_at"]), "actor": r["actor"], "changes": r["changes"]} for r in vs]
    return {"book": run["book"], "label": run["label"], "live": run["live"], "version": versions[-1]["v"], "options": items, "versions": versions}


def set_options(conn: psycopg.Connection, key: str, book: str, changes: list[dict[str, Any]], expected_version: int, actor: str) -> dict[str, Any]:
    """Apply changes as ONE new version. Each change {option, value, reason}; every reason is required. The book's own
    validation runs (ensure_book / combo_book.settings); the version row and the book update commit together."""
    from . import book as bk
    if not changes:
        raise ValueError("no changes")
    now_v = current_version(conn, book, key)
    if int(expected_version) != now_v:
        raise LookupError(f"settings are at v{now_v}, not v{expected_version} - reload and try again")
    b = _book_row(conn, book)
    opts = {o.key: o for o in so.options_for(key, b)}
    work = dict(b)
    fields: dict[str, Any] = {}
    record = []
    for ch in changes:
        o = opts.get(ch.get("option"))
        if o is None:
            raise ValueError(f"{key} has no option {ch.get('option')!r} in {book}")
        reason = str(ch.get("reason") or "").strip()
        if not reason:
            raise ValueError(f"{o.label}: a reason is required")
        new = so.coerce(o, ch.get("value"))
        old = o.read(work)
        if (o.type == "num" and old is not None and new is not None and float(old) == float(new)) or old == new:
            continue
        patch = o.patch(work, new)
        work.update(patch)
        fields.update(patch)
        record.append({"option": o.key, "label": o.label, "from": so.fmt(o, old), "to": so.fmt(o, new), "reason": reason})
    if not record:
        raise ValueError("nothing changed")
    snapshot = {k: (o.read(work) if not isinstance(o.read(work), Decimal) else float(o.read(work))) for k, o in opts.items()}
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO idx.strategy_config_version (book, strategy, version, changes, snapshot, actor)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (book, key, now_v + 1, json.dumps(record), json.dumps(snapshot, default=str), actor))
    bk.ensure_book(conn, book, **fields)                  # validates, updates and COMMITS - the version row with it
    return {"version": now_v + 1, "changes": record}


# ---------------------------------------------------------------------------------------------------------------- research / training
def _studies(conn: psycopg.Connection, ids: list[int | None]) -> dict[int, dict[str, Any]]:
    """cited id -> {summary, date, current} for the studies a page quotes, in one read. A study re-run on corrected data
    (idx.study.superseded_by) is read from its latest run; `current` is that run's id."""
    want = sorted({i for i in ids if i})
    if not want:
        return {}
    return {r["id"]: {"summary": r["summary"], "date": _iso(r["run_at"]), "current": r["current_id"]}
            for r in _q(conn, """SELECT c.id, c.current_id, s.run_at, s.summary FROM idx.study_current c
                                   JOIN idx.study s ON s.id = c.current_id WHERE c.id = ANY(%s)""", (want,))}


# Page-level figures counted from the live tables when the page is read (strategy_page_content: LIVE(name)).
LIVE_FIGS: dict[str, tuple[str, int, float]] = {          # name -> (sql returning one number, decimals, scale)
    "ml_universe": ("""SELECT count(DISTINCT code) FROM idx.ml_prediction WHERE horizon = '5d'
                        AND made_at::date = (SELECT max(made_at)::date FROM idx.ml_prediction WHERE horizon = '5d')""", 0, 1),
    "feed_names": ("SELECT count(*) FROM idx.feed_symbol WHERE enabled", 0, 1),
    "agent_samples_per_session": ("SELECT count(*)::float / NULLIF(count(DISTINCT d), 0) FROM idx.agent_sample", -2, 1),
    "agent_uncond_ret": ("SELECT avg(reward) FROM idx.agent_sample", 1, 100),
}


def _live_fig(conn: psycopg.Connection, name: str) -> str | None:
    sql, dp, scale = LIVE_FIGS[name]
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(sql)
        row = cur.fetchone()
    v = _f(row[0]) if row else None
    if v is None:
        return None
    v *= scale
    if dp < 0:                                             # rounded to hundreds: "about 1,700 outcomes a session"
        return f"{round(v, dp):,.0f}"
    return sf.fmt_num(v, dp)


def _page_vals(conn: psycopg.Connection, page: dict[str, Any], studies: dict[int, dict[str, Any]]) -> dict[str, str | None]:
    vals: dict[str, str | None] = {}
    for name, spec in (page.get("figs") or {}).items():
        if spec[0] == "live":
            vals[name] = _live_fig(conn, spec[1])
        elif spec[0] == "study":
            st = studies.get(spec[1])
            vals[name] = sf.evaluate(spec[2], st["summary"]) if st else None
        else:
            raise ValueError(f"page figure {name!r} must be S(...) or LIVE(...)")
    return vals


def _fill(text: str | None, vals: dict[str, str | None]) -> str | None:
    if text is None:
        return None
    return text.format(**{n: vals.get(n) or sf.DASH for n in sf.placeholders(text)})


def _page_study_ids(page: dict[str, Any]) -> list[int | None]:
    return [r.get("study") for r in page.get("research", [])] + [sp[1] for sp in (page.get("figs") or {}).values() if sp[0] == "study"]


def prose(conn: psycopg.Connection, key: str, studies: dict[int, dict[str, Any]] | None = None) -> dict[str, Any]:
    """The Overview copy with its figures filled from the stored studies and the live tables."""
    page = PAGES[key]
    vals = _page_vals(conn, page, studies if studies is not None else _studies(conn, _page_study_ids(page)))
    return {"what": _fill(page.get("what"), vals),
            "how": [{"k": k, "v": _fill(v, vals)} for k, v in page.get("how", [])],
            "detail": [{"k": k, "v": _fill(v, vals)} for k, v in page.get("detail", [])]}


def research(conn: psycopg.Connection, key: str, studies: dict[int, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """The studies behind a strategy. ``found`` and ``n`` are rendered from each study's stored summary; a figure the summary
    does not hold prints as "–" and is named in ``missing``."""
    items = PAGES.get(key, {}).get("research", [])
    if studies is None:
        studies = _studies(conn, [r.get("study") for r in items])
    out = []
    for r in items:
        st = studies.get(r["study"]) if r.get("study") else None
        summ = st["summary"] if st else None
        figs = r.get("figs") or {}
        found, m1 = sf.render(r["found"], figs, summ)
        n, m2 = sf.render(r.get("n") or sf.DASH, figs, summ)
        out.append({**{k: v for k, v in r.items() if k != "figs"}, "found": found, "n": n, "missing": sorted(set(m1 + m2)),
                    "date": st["date"] if st else r.get("date"),
                    # the run shown: a study re-run on corrected data is cited by its latest run's number
                    "study": st["current"] if st else r.get("study"), "first_run": r.get("study")})
    return sorted(out, key=lambda r: r["date"] or "", reverse=True)


def training(conn: psycopg.Connection, key: str) -> dict[str, Any] | None:
    m = PAGES.get(key, {}).get("model")
    if not m:
        return None
    if m["kind"] == "ml_model":
        rows = _q(conn, """SELECT model_id, trained_at, status, origin, promoted_at, retired_at, val_metrics, features, reason
                             FROM idx.ml_model WHERE horizon = %s AND task = %s ORDER BY trained_at""", (m["horizon"], m["task"]))
        metric = "ic" if m["task"] == "ret" else "auc"
        vers = []
        for r in rows:
            vm = r["val_metrics"] or {}
            blocks = vm.get("blocks") or []
            last = blocks[-1].get(metric) if blocks and isinstance(blocks[-1], dict) else None
            st = ("champion" if r["status"] == "champion" else "former" if r["promoted_at"] else
                  "candidate" if r["status"] == "candidate" else "lost")
            vers.append({"ver": f"#{r['model_id']}", "date": _iso(r["trained_at"]), "val": _f(vm.get(metric)), "hold": _f(last), "status": st,
                         "origin": r["origin"], "note": r["reason"]})
        champ = next((v for v in reversed(vers) if v["status"] == "champion"), None)
        n_feat = len(rows[-1]["features"]) if rows and rows[-1]["features"] else None
        live = _q(conn, """SELECT count(*) AS n, avg((hit)::int) AS hit FROM idx.ml_prediction
                            WHERE horizon = %s AND realized_at > now() - interval '60 days' AND hit IS NOT NULL""", (m["horizon"],))
        facts = [("Model", "LightGBM, champion against challenger"), ("Features", str(n_feat) if n_feat else "–"),
                 ("Scoring", "Nightly, 20:40 WIB"), ("Retraining", "Nightly: a refresh and a tuned challenger"),
                 ("Promotion rule", "A challenger replaces the champion only when it beats it by more than 0.005"),
                 ("Live hit rate · 60 days", f"{float(live[0]['hit']) * 100:.1f}% of {live[0]['n']:,}" if live and live[0]["n"] else "–")]
        return {"metric": "Validation IC" if metric == "ic" else "Validation AUC", "hold_label": "Latest block",
                "facts": [{"k": k, "v": v} for k, v in facts], "versions": vers, "champion": champ and champ["ver"]}
    if m["kind"] == "agent_model":
        rows = _q(conn, "SELECT id, fitted_at, data_to, n, params FROM idx.agent_model ORDER BY id")
        vers = []
        for i, r in enumerate(rows):
            acts = (r["params"] or {}).get("actions", {})
            vers.append({"ver": f"#{r['id']}", "date": _iso(r["fitted_at"]), "val": float(r["n"]), "hold": float(len(acts)),
                         "status": "champion" if i == len(rows) - 1 else "former", "origin": "nightly", "note": f"data to {_iso(r['data_to'])}"})
        facts = [("Model", "Bayesian linear, one per bracket"), ("Decision", "Pessimistic bound ≥ +0.3 %"),
                 ("Retraining", "Nightly, 16:50 WIB"), ("Samples", f"{rows[-1]['n']:,}" if rows else "–")]
        return {"metric": "Samples", "hold_label": "Actions ready", "facts": [{"k": k, "v": v} for k, v in facts],
                "versions": vers, "champion": vers[-1]["ver"] if vers else None}
    return None


# ---------------------------------------------------------------------------------------------------------------- timeline
def timeline(conn: psycopg.Connection, key: str, rs: list[dict[str, Any]], limit: int = 300,
             rendered: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for r in rs:
        items.append({"date": r["since"], "kind": "settings", "book": r["label"],
                      "title": f"{'Went live' if r['live'] else 'Started on paper'} · settings v1", "sub": "Initial settings."})
    for v in _q(conn, "SELECT book, version, changes, created_at FROM idx.strategy_config_version WHERE strategy = %s", (key,)):
        lab = next((r["label"] for r in rs if r["book"] == v["book"]), v["book"])
        items.append({"date": _iso(v["created_at"]), "kind": "settings", "book": lab, "title": f"Settings v{v['version']}",
                      "sub": " ".join(f"{c['label']} {c['from']} → {c['to']}. {c['reason']}" for c in v["changes"])})
    for s in (rendered if rendered is not None else research(conn, key)):
        items.append({"date": s["date"], "kind": "study", "title": f"Study {s['verdict'].lower()}: {s['title']}" if s["verdict"] != "Running"
                      else f"Study started: {s['title']}", "sub": s["found"] if s["verdict"] != "Running" else s["tested"]})
    t = training(conn, key)
    for v in (t or {}).get("versions", []):
        if v["status"] in ("champion", "former"):
            items.append({"date": v["date"], "kind": "model", "title": f"{v['ver']} promoted to champion", "sub": v.get("note") or ""})
    aliases = {key}
    if key == "ml_rank":
        aliases.add("combo")
    for a in _q(conn, """SELECT ts, message, book, severity FROM idx.alert WHERE strategy = ANY(%s) ORDER BY ts DESC LIMIT 60""", (list(aliases),)):
        items.append({"date": _iso(a["ts"]), "kind": "alert", "book": a["book"], "title": (a["message"] or "").split("\n")[0][:140], "sub": ""})
    items = [i for i in items if i["date"]]
    items.sort(key=lambda x: x["date"], reverse=True)
    return items[:limit]


# ---------------------------------------------------------------------------------------------------------------- screens
def catalog(conn: psycopg.Connection) -> dict[str, Any]:
    books = _books(conn)
    out = []
    for key in page_keys():
        page, e = PAGES[key], reg.BY_KEY[key]
        rs = runs(conn, key, books)
        st = status_of(key, rs)
        live = None
        for r in rs if page["family"] != "overlay" else []:             # an overlay trades nothing of its own
            s = series(conn, key, r["book"])
            if s and len(s["live"]) >= 2:
                n = len(run_trades(conn, key, r["book"]))
                live = {"ret": s["live"][-1] - 100, "book": r["label"], "trades": n}
                break
        out.append({"key": key, "name": e["label"], "one": page["one"], "family": page["family"], "status": st,
                    "headline": headline(conn, key), "live": live, "overlay": page["family"] == "overlay",
                    "portfolios": [{"book": r["book"], "label": r["label"], "live": r["live"]} for r in rs]})
    return {"strategies": out, "families": FAMILY_LABEL}


def detail(conn: psycopg.Connection, key: str) -> dict[str, Any]:
    if key not in PAGES or key not in reg.BY_KEY:
        raise KeyError(key)
    page, e = PAGES[key], reg.BY_KEY[key]
    books = _books(conn)
    rs = runs(conn, key, books)
    st = status_of(key, rs)
    positions: dict[str, list[str]] = {}
    for r in rs:
        if r["book"] == AGENT_BOOK:
            positions[r["book"]] = [x["code"] for x in _q(conn, "SELECT code FROM idx.agent_decision WHERE agent = 'ts' AND settled_at IS NULL")]
        elif r["rule"] == "combo" and page.get("sleeve"):
            positions[r["book"]] = sorted(cb.sleeve_positions(conn, r["book"]).get(page["sleeve"], {}).keys())
        elif page["family"] != "overlay":
            positions[r["book"]] = [x["code"] for x in _q(conn, "SELECT code FROM idx.position WHERE book = %s AND lots > 0 ORDER BY code", (r["book"],))]
    studies = _studies(conn, _page_study_ids(page))
    res = research(conn, key, studies)
    copy = prose(conn, key, studies)
    opts = [o for o in (options_view(conn, key, r, res) for r in rs) if o]
    ver = {o["book"]: o["version"] for o in opts}
    return {
        "key": key, "name": e["label"], "family": page["family"], "family_label": FAMILY_LABEL[page["family"]], "status": st,
        "one": page["one"], "what": copy["what"], "rules": page.get("rules", []), "how": copy["how"], "detail": copy["detail"],
        "falsifier": e.get("falsifier"), "closed": page.get("closed"), "model": bool(page.get("model")),
        "runs": [{**r, "version": ver.get(r["book"]), "positions": positions.get(r["book"], []),
                  "has_options": r["book"] in ver} for r in rs],
        "headline": headline(conn, key), "research": res, "training": training(conn, key),
        "options": opts, "timeline": timeline(conn, key, rs, rendered=res), "fills": page.get("fills"),
    }


def performance(conn: psycopg.Connection, key: str, book: str) -> dict[str, Any]:
    rs = {r["book"]: r for r in runs(conn, key)}
    if book not in rs:
        raise KeyError(book)
    s = series(conn, key, book)
    trades = run_trades(conn, key, book)
    if not s:
        return {"book": book, "label": rs[book]["label"], "live": rs[book]["live"], "since": rs[book]["since"], "series": None, "stats": None,
                "trades": len(trades)}
    st = _equity_stats(s["dates"], s["live"])
    wins = sum(1 for t in trades if t["ret"] > 0)
    return {"book": book, "label": rs[book]["label"], "live": rs[book]["live"], "since": rs[book]["since"],
            "series": {"dates": s["dates"], "live": s["live"], "backtest": None},
            "stats": {**st, "trades": len(trades), "win": wins / len(trades) * 100 if trades else None, "sessions": len(s["dates"])}}


def _months(dates: list[str], values: list[float]) -> dict[str, float]:
    """Month -> return in percent, each month against the previous month's last value (the first against the first value)."""
    out: dict[str, float] = {}
    last: dict[str, float] = {}
    for d, v in zip(dates, values, strict=True):
        last[d[:7]] = v
    prev = values[0] if values else None
    for m in sorted(last):
        if prev:
            out[m] = (last[m] / prev - 1) * 100
        prev = last[m]
    return out


def _study_port(node: dict[str, Any]) -> dict[str, Any]:
    """The portfolio figures a backtest study stored for one book (idx_combo_live.py writes all of them; older studies some)."""
    inv = node.get("invested_share")
    tot = _f(node.get("total"))                                        # a fraction here (5.85 = +585 %), not _pct's guess
    return {"total": tot * 100 if tot is not None else None, "cagr": _pct(node.get("cagr")), "mdd": _pct(node.get("mdd")), "mdd_long": node.get("mdd_long"),
            "vol": _pct(node.get("vol")), "sharpe": _f(node.get("sharpe")), "sortino": _f(node.get("sortino")),
            "exposure": _pct(inv) if inv else None, "mdd_rp": _f(node.get("mdd_rp")), "final": _f(node.get("final")),
            "sharpe_h1": _f(node.get("sharpe_h1")), "sharpe_h2": _f(node.get("sharpe_h2")), "cagr_ex2025": _pct(node.get("cagr_ex2025")),
            "sharpe_ex2025": _f(node.get("sharpe_ex2025")), "best_day": _pct(node.get("best_day")), "worst_day": _pct(node.get("worst_day")),
            "pos_months": node.get("pos_months"), "n_months": node.get("n_months")}


def results(conn: psycopg.Connection, key: str) -> dict[str, Any]:
    page = PAGES.get(key, {})
    sources = []
    bt = page.get("backtest")
    if bt:
        # the trades imported from the run that currently stands for the cited study (a re-run imports under its own id)
        cur_bt = _q(conn, "SELECT current_id FROM idx.study_current WHERE id = %s", (bt["study"],))
        bt_id = cur_bt[0]["current_id"] if cur_bt else bt["study"]
        rows = _q(conn, """SELECT code, d_in, d_out, cost, pnl, exit_reason, entry_price, exit_price, leg FROM idx.strategy_backtest_trade
                            WHERE strategy = %s AND study_id = %s ORDER BY d_out, seq""", (key, bt_id))
        if rows:
            summ = _q(conn, "SELECT summary FROM idx.study WHERE id = %s", (bt_id,))
            node = (summ[0]["summary"] or {}).get(bt["file"], {}) if summ else {}
            first, last = rows[0]["d_in"], rows[-1]["d_out"]
            sessions = _q(conn, "SELECT count(DISTINCT trade_date) AS n FROM idx.bar WHERE source = 'idx' AND trade_date BETWEEN %s AND %s", (first, last))
            trades = [{"code": r["code"], "d_in": _iso(r["d_in"]), "d_out": _iso(r["d_out"]), "entry": _f(r["entry_price"]), "exit": _f(r["exit_price"]),
                       "leg": r["leg"],
                       "cost": float(r["cost"]), "pnl": float(r["pnl"]), "ret": float(r["pnl"]) / float(r["cost"]) * 100 if float(r["cost"]) else 0.0,
                       "reason": r["exit_reason"]} for r in rows]
            sources.append({"key": "bt", "label": "Backtest", "from": _iso(first), "to": _iso(last), "sessions": sessions[0]["n"] if sessions else None,
                            "study": bt_id, "size": sum(t["cost"] for t in trades) / len(trades), "trades": trades,
                            "port": _study_port(node),
                            "years": {str(y): _pct(v) for y, v in (node.get("by_year") or {}).items()},
                            "months": {m: _pct(v) for m, v in (node.get("by_month") or {}).items()},
                            "nav": node.get("nav") or None, "config": bt.get("config"),
                            "method": "study"})
    for r in runs(conn, key):
        trades = run_trades(conn, key, r["book"])
        if not trades:
            continue
        s = series(conn, key, r["book"])
        port = _equity_stats(s["dates"], s["live"]) if s else {}
        years: dict[str, float] = {}
        if s:
            by: dict[str, list[float]] = defaultdict(list)
            for d, v in zip(s["dates"], s["live"], strict=True):
                by[d[:4]].append(v)
            prev = 100.0
            for y in sorted(by):
                years[y] = (by[y][-1] / prev - 1) * 100
                prev = by[y][-1]
        size = sum(t["cost"] for t in trades) / len(trades)
        sources.append({"key": f"{'live' if r['live'] else 'paper'}:{r['book']}", "label": f"{'Live' if r['live'] else 'Paper'} · {r['label']}",
                        "from": trades[0]["d_in"], "to": trades[-1]["d_out"], "sessions": len(s["dates"]) if s else None, "study": None,
                        "size": size, "trades": trades, "port": {**port, "exposure": None}, "years": years,
                        "months": _months(s["dates"], s["live"]) if s else {},
                        "nav": [[d, v] for d, v in zip(s["dates"], s["live"], strict=True)] if s else None,
                        "method": "live" if r["live"] else "paper"})
    return {"key": key, "fills": page.get("fills"), "sources": sources}


# ---------------------------------------------------------------------------------------------------------------- import
BACKTEST_EXIT = {"gapfade": "Same-day close", "trend_small": "10 % trailing stop", "ml_rank": None}
# a trade list's own exit reason (the `why` column idx_combo_live.py writes), in the page's words
EXIT_WHY = {"stop_same": "Same-day stop", "swap": "Swapped for a better score", "max_hold": "Longest hold reached", "gone": "No score"}
EXIT_BY_SLEEVE = {"gap": "Same-day close", "trend": "10 % trailing stop"}     # a combined book's trade list: by its sleeve
# the leg a trade list row belongs to: the ML sleeve's ens4 rules (idx_combo_live.py writes ML1..ML4 in ENS4 order)
LEG = {"ML1": "ML +5/10", "ML2": "ML +8/10", "ML3": "ML +10/10", "ML4": "ML +8/5", "gap": "Gap-fade", "trend": "Trend"}


def _price(v: Any) -> float | None:
    x = _f(v) if v not in (None, "") else None
    return round(x, 2) if x is not None and x == x and x > 0 else None


def import_backtest(conn: psycopg.Connection, key: str, study_id: int, path: str) -> int:
    """A study's trade list (strat, code, cost, pnl, d_in, d_out CSV - research/idx_combo_rupiah.py's) into
    idx.strategy_backtest_trade. Replaces what was imported for (key, study) before."""
    rows = list(csv.DictReader(Path(path).open(encoding="utf-8")))
    with conn.cursor() as cur:
        cur.execute("DELETE FROM idx.strategy_backtest_trade WHERE strategy = %s AND study_id = %s", (key, study_id))
        cur.executemany("""INSERT INTO idx.strategy_backtest_trade (strategy, study_id, seq, code, d_in, d_out, cost, pnl, exit_reason,
                                                                  entry_price, exit_price, leg)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                        [(key, study_id, i, r["code"], r["d_in"], r["d_out"], round(float(r["cost"]), 2), round(float(r["pnl"]), 2),
                          EXIT_WHY.get(r.get("why") or "") or EXIT_BY_SLEEVE.get(r.get("strat") or "") or BACKTEST_EXIT.get(key),
                          _price(r.get("entry")), _price(r.get("exit")), LEG.get(r.get("strat") or ""))
                         for i, r in enumerate(rows)])
    conn.commit()
    return len(rows)

