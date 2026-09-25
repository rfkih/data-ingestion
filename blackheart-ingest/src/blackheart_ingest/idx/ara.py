"""ARA watch: which names are likely to lock at the upper auto-rejection price next session, how sure the model is, and
what a holder's name is doing when it gets there today (operator, 2026-09-23: "kasih alert supaya kita finding saham
potensial untuk ARA" and "menyentuh ARA jadi kita jual di harga paling atas"; 2026-09-24: "terapkan di page ARA untuk
prediksi dan keyakinannya").

What the research settled (research/IDX_ARA_2026-09-21.md, IDX_ML_ARA_2026-09-22.md, IDX_ARA_SELL_2026-09-23.md,
IDX_ARA_MICRO_2026-09-24.md = study #146):
  * tomorrow's lock is predictable from today's bar + closing book: walk-forward 2022-26 AUC 0.88-0.93, the top-5 names a
    day lock 8-20 % of the time against a 0.3-0.9 % base rate (~20x); 48-76 % of a year's locks sit in the daily top-20.
    The evening list here is that model (ara_model.py: LightGBM + GRU, Platt-calibrated, ENS rank).
  * it is NOT a trade: the names that keep going open locked (no offer), the ones that can be bought lose (menu 16;
    ML-3; #146 buyable precision 2-4 %). Nothing here writes a ticket.
  * for a HOLDER the fact that matters is whether the touch holds to the close: a LOCKED close is followed by +431 bps the
    next day against the ARA price (liquid names, n 440, t 8); a FADED touch closes 661 bps under it (n 231, t 15). The
    intraday check reads that state off the tick feed and tells the phone, with those numbers, nothing more.

Two entry points, both scheduled (scheduler.py): ``watch`` in the evening after the bar lands (run in a subprocess: the
model holds ~1 GB while it fits), ``touch_check`` every two minutes during the session. Read-only on the market tables;
writes idx.ara_watch / idx.ara_touch / idx.alert.
"""
from __future__ import annotations

import logging
import math
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import psycopg
from psycopg.rows import dict_row, tuple_row

from . import ara_model, runlog

logger = logging.getLogger(__name__)
WIB = ZoneInfo("Asia/Jakarta")
SESSION_FROM, SESSION_TO = time(8, 58), time(16, 1)
TOP_N = 10
FEATS = ara_model.FEATS
CONF_WORD = {"high": "keyakinan tinggi", "medium": "keyakinan sedang", "low": "keyakinan rendah"}
# the two numbers a holder gets, from menu 34 (study #101), liquid names 2020-2026
FACT_LOCKED = "kunci yang bertahan sampai tutup: hari berikutnya rata-rata +431 bps vs harga ARA (likuid, n 440, studi #101)"
FACT_FADED = "sentuhan yang memudar: tutup hari itu rata-rata -661 bps vs harga ARA (likuid, n 231, studi #101)"
FACT_AT_ARA = "harga di ARA dengan penjual masih antre: belum terkunci; 59 % sentuhan bertahan sampai tutup (studi #101)"
FACT_MODEL = ("model studi #146: dari 5 nama teratas per hari, 8-20 % tutup di ARA besoknya (dasar 0,3-0,9 %, AUC 0,88-0,93, "
              "2022-2026); P sudah dikalibrasi")


# ---- the limit -------------------------------------------------------------------------------------------------------
def tick(px: float) -> float:
    return 1.0 if px < 200 else 2.0 if px < 500 else 5.0 if px < 2000 else 10.0 if px < 5000 else 25.0


def limit_of(prev: float) -> float:
    """Upper auto-rejection band by the previous close: 35 % to Rp 200, 25 % to Rp 5,000, 20 % above (rule II-A)."""
    return 0.35 if prev <= 200 else 0.25 if prev <= 5000 else 0.20


def ara_price(prev: float) -> float:
    """The highest tick at or below prev * (1 + band), on the tick of the price it lands on."""
    raw = prev * (1 + limit_of(prev))
    t = tick(raw)
    return math.floor(raw / t + 1e-9) * t


# ---- the evening model -----------------------------------------------------------------------------------------------
def train_and_score(conn: psycopg.Connection, use_dl: bool | None = None) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Fit study #146's model on every labelled day in idx.daily_summary and score the last bar of every main-board name.
    Returns rows sorted by the ENS score with calibrated p_lock / p_touch / p_dl, flags and the features."""
    P = ara_model.Panel(ara_model.load_summary(conn))
    fitted = ara_model.train(P, use_dl=use_dl)
    scored = ara_model.score_last(P, fitted)
    if scored.empty:
        raise RuntimeError("ara: nothing to score on the last bar")
    info = {"bar_date": P.dates[-1].date(), "scored": len(scored), "model": "ens" if fitted.gru is not None else "tree", **fitted.info}
    return scored, info


# ---- the nightly list ------------------------------------------------------------------------------------------------
def held_names(conn: psycopg.Connection) -> dict[str, list[str]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""SELECT p.code, array_agg(p.book ORDER BY p.book) AS books FROM idx.position p JOIN idx.book b USING (book)
                       WHERE p.lots > 0 AND b.archived_at IS NULL AND p.book NOT LIKE 'test%%' GROUP BY p.code""")
        return {r["code"]: list(r["books"]) for r in cur.fetchall()}


def _f(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if np.isfinite(x) else None


def _row(r: Any, rank: int | None, held: dict[str, list[str]], listed: bool = True) -> dict[str, Any]:
    p_lock = float(r.p_lock)
    return {"code": r.code, "rank": rank, "listed": listed, "p": p_lock, "p_lock": p_lock, "p_touch": _f(getattr(r, "p_touch", None)), "p_dl": _f(getattr(r, "p_dl", None)),
            "score": _f(getattr(r, "score", p_lock)), "prev_close": float(r.close), "ara_px": float(r.ara_px_next),
            "locked_today": bool(getattr(r, "locked_today", False)), "buyable": bool(getattr(r, "buyable", True)),
            "confidence": ara_model.confidence(p_lock), "held": r.code in held, "books": held.get(r.code, []),
            "features": {k: _f(getattr(r, k, None)) for k in FEATS}}


def select_rows(scored: pd.DataFrame, held: dict[str, list[str]], top: int = TOP_N) -> list[dict[str, Any]]:
    """Every scored name in ranking order, with ``listed`` true for the top-N and for anything a book holds. The list,
    the push and the screens read the listed part; the rest is kept so a person can ask about any name. Pure, for the
    tests. ``scored`` needs code, close, ara_px_next, p_lock and is read in its given order (score_last sorts by ENS)."""
    out = []
    for rank, r in enumerate(scored.itertuples(), start=1):
        out.append(_row(r, rank, held, listed=rank <= top or r.code in held))
    return out


def render_watch(rows: list[dict[str, Any]], bar_date: date, base_rate: float) -> str:
    listed = [r for r in rows if r.get("listed", True)]
    top = [r for r in listed if r["rank"] and not r["held"]]
    hold = [r for r in listed if r["held"]]

    def line(r: dict[str, Any]) -> str:
        touch = f", sentuh {r['p_touch'] * 100:.0f} %" if r.get("p_touch") is not None else ""
        state = " · sudah terkunci hari ini" if r.get("locked_today") else ""
        who = " · dipegang " + ",".join(r["books"]) if r["held"] else ""
        return f"- {r['code']} P kunci {r['p'] * 100:.0f} %{touch} ({CONF_WORD[r.get('confidence', 'low')]}), ARA Rp {r['ara_px']:,.0f} (tutup {r['prev_close']:,.0f}){state}{who}"

    L = [f"ARA watch untuk sesi setelah {bar_date:%d %b}: P kunci = peluang tutup di ARA besok, dari bar + book penutupan hari ini "
         f"(dasar {base_rate * 100:.1f} %). {FACT_MODEL}.",
         "Bukan tiket: yang benar-benar lanjut membuka terkunci, yang bisa dibeli rugi (menu 16).", "Daftar:"]
    L += [line(r) for r in top]
    if hold:
        L.append("Nama yang dipegang:")
        L += [f"- {r['code']} P kunci {r['p'] * 100:.1f} % ({CONF_WORD[r.get('confidence', 'low')]}), ARA Rp {r['ara_px']:,.0f} ({','.join(r['books'])})" for r in hold]
    L.append(f"Kalau menyentuh: {FACT_LOCKED}; {FACT_FADED}.")
    return "\n".join(L)


def watch(conn: psycopg.Connection, top: int = TOP_N, notify: bool = True, run_date: date | None = None, use_dl: bool | None = None) -> dict[str, Any]:
    run_date = run_date or datetime.now(WIB).date()
    scored, info = train_and_score(conn, use_dl=use_dl)
    held = held_names(conn)
    rows = select_rows(scored, held, top)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM idx.ara_watch WHERE run_date = %s", (run_date,))
        for r in rows:
            cur.execute("""INSERT INTO idx.ara_watch (run_date, bar_date, code, rank, listed, p, p_lock, p_touch, p_dl, score, prev_close, ara_px, held, books,
                                                      locked_today, buyable, confidence, model, features)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)""",
                        (run_date, info["bar_date"], r["code"], r["rank"], r.get("listed", True), round(r["p"], 5), round(r["p_lock"], 5),
                         None if r["p_touch"] is None else round(r["p_touch"], 5), None if r["p_dl"] is None else round(r["p_dl"], 5),
                         None if r["score"] is None else round(r["score"], 6), r["prev_close"], r["ara_px"], r["held"], r["books"],
                         r["locked_today"], r["buyable"], r["confidence"], info["model"], pd.Series(r["features"], dtype=object).to_json()))
    conn.commit()
    text = render_watch(rows, info["bar_date"], info.get("base_rate", 0.0055))
    if notify:
        runlog.alert_once(conn, "info", "ara", f"ARA watch {run_date}: "
                          + ", ".join(f"{r['code']} {r['p'] * 100:.0f} %" for r in rows if r.get("listed", True) and r["rank"] and not r["held"]))
        try:
            from . import notify as nf
            nf.send(text, title=f"ARA watch {run_date:%d %b}", data={"route": "/m/ara", "kind": "ara"})
        except Exception:                                                  # a notification never fails the job
            logger.exception("ara watch notify failed")
    logger.info("idx ara watch %s: %s", run_date, {k: v for k, v in info.items() if k != "rows"})
    return {"run_date": run_date, **info, "rows": rows, "text": text}


def coverage(conn: psycopg.Connection, run_date: date) -> dict[str, int | None]:
    """How many names the model gave a number to that session, and how many it could have. The scoring mask is
    ``Panel.last_day``: a main-board name that traded, priced at or above ``MIN_PREV`` - there is deliberately no
    liquidity floor at scoring time, so a thin name a person holds still gets a probability. Mirrored here in SQL so a
    reader of the list can see what the top 30 was chosen out of."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""SELECT count(*) FILTER (WHERE substr(remarks, 5, 1) IN ('1', '2')) AS main_board,
                              count(*) FILTER (WHERE substr(remarks, 5, 1) IN ('1', '2') AND close > 0 AND previous >= %s) AS scored
                         FROM idx.daily_summary WHERE trade_date = %s""", (ara_model.MIN_PREV, run_date))
        r = cur.fetchone()
    return {"main_board": int(r["main_board"]) if r else None, "scored": int(r["scored"]) if r else None}


def latest_watch(conn: psycopg.Connection) -> dict[str, Any]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT max(run_date) AS d FROM idx.ara_watch")
        d = cur.fetchone()["d"]
        if d is None:
            return {"run_date": None, "rows": [], "facts": ara_model.FACTS}
        cur.execute("""SELECT run_date, bar_date, code, rank, p, p_lock, p_touch, p_dl, score, prev_close, ara_px, held, books, locked_today, buyable,
                              confidence, model, features FROM idx.ara_watch WHERE run_date = %s AND (listed OR held)
                        ORDER BY rank NULLS LAST, score DESC NULLS LAST, p DESC""", (d,))
        rows = [dict(r) for r in cur.fetchall()]
    for r in rows:                                                          # rows written before 0036 carry only p
        if r.get("p_lock") is None:
            r["p_lock"] = r["p"]
        if r.get("confidence") is None:
            r["confidence"] = ara_model.confidence(float(r["p_lock"]))
    cov = coverage(conn, rows[0]["bar_date"] if rows and rows[0].get("bar_date") else d)
    # Whether the run kept the WHOLE ranking (0040, from the 2026-09-25 evening on) or only its list (every run before): a
    # name missing from a whole-ranking run was not scored at all; missing from a list-only run says nothing about it.
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT count(*) AS n, bool_or(NOT listed) AS whole FROM idx.ara_watch WHERE run_date = %s", (d,))
        st = cur.fetchone()
    return {"run_date": d, "rows": rows, "facts": ara_model.FACTS,
            "coverage": {**cov, "shown": len(rows), "stored": int(st["n"]) if st else len(rows), "whole_ranking": bool(st and st["whole"]),
                         "min_prev": ara_model.MIN_PREV}}


def name_watch(conn: psycopg.Connection, code: str) -> dict[str, Any] | None:
    """The newest ARA score for one name, listed or not: what the model thought of it and where it sat in the ranking."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""SELECT run_date, bar_date, code, rank, listed, p, p_lock, p_touch, p_dl, score, prev_close, ara_px, held, books,
                              locked_today, buyable, confidence, model, features
                         FROM idx.ara_watch WHERE code = %s ORDER BY run_date DESC LIMIT 1""", (code.upper(),))
        r = cur.fetchone()
    if not r:
        return None
    row = dict(r)
    if row.get("p_lock") is None:
        row["p_lock"] = row["p"]
    if row.get("confidence") is None:
        row["confidence"] = ara_model.confidence(float(row["p_lock"]))
    with conn.cursor(row_factory=dict_row) as cur:                          # how many names it was ranked against
        cur.execute("SELECT count(*) AS n FROM idx.ara_watch WHERE run_date = %s", (row["run_date"],))
        n = cur.fetchone()
    row["of"] = int(n["n"]) if n else None
    return row


# ---- the intraday state ----------------------------------------------------------------------------------------------
def classify(high: float | None, last: float | None, ara: float, offer_px: float | None, offer_vol: float | None) -> str | None:
    """None = not touched today; 'locked' = at/above the limit with NO offer (nothing to buy, the classic lock);
    'at_ara' = at the limit but sellers are still queued there; 'faded' = touched, now trading under it."""
    if high is None or not np.isfinite(high) or high < ara - 1e-9:
        return None
    if last is not None and np.isfinite(last) and last >= ara - 1e-9:
        no_offer = offer_px is None or not np.isfinite(offer_px) or offer_px <= 0 or not offer_vol or offer_vol <= 0 or offer_px > ara + 1e-9
        return "locked" if no_offer else "at_ara"
    return "faded"


def _feed_today(conn: psycopg.Connection, d: date, codes: list[str]) -> dict[str, dict[str, Any]]:
    if not codes:
        return {}
    out: dict[str, dict[str, Any]] = {}
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""SELECT code, max(price) AS high FROM idx.feed_trade
                       WHERE (ts AT TIME ZONE 'Asia/Jakarta')::date = %s AND code = ANY(%s) GROUP BY code""", (d, codes))
        for r in cur.fetchall():
            out[r["code"]] = {"high": float(r["high"]) if r["high"] is not None else None}
        cur.execute("""SELECT DISTINCT ON (code) code, price, ts FROM idx.feed_trade
                       WHERE (ts AT TIME ZONE 'Asia/Jakarta')::date = %s AND code = ANY(%s) ORDER BY code, ts DESC""", (d, codes))
        for r in cur.fetchall():
            out.setdefault(r["code"], {})["last"] = float(r["price"]) if r["price"] is not None else None
            out[r["code"]]["last_ts"] = r["ts"]
        cur.execute("""SELECT DISTINCT ON (code) code, off_px[1] AS off, off_vol[1] AS ov, ts FROM idx.feed_book
                       WHERE (ts AT TIME ZONE 'Asia/Jakarta')::date = %s AND code = ANY(%s) ORDER BY code, ts DESC""", (d, codes))
        for r in cur.fetchall():
            out.setdefault(r["code"], {})["offer_px"] = float(r["off"]) if r["off"] is not None else None
            out[r["code"]]["offer_vol"] = float(r["ov"]) if r["ov"] is not None else None
    return out


def _first_touch_ts(conn: psycopg.Connection, d: date, code: str, ara: float) -> datetime | None:
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute("""SELECT min(ts) FROM idx.feed_trade WHERE (ts AT TIME ZONE 'Asia/Jakarta')::date = %s AND code = %s AND price >= %s""",
                    (d, code, ara))
        r = cur.fetchone()
        return r[0] if r else None


def prev_closes(conn: psycopg.Connection, d: date, codes: list[str]) -> dict[str, float]:
    if not codes:
        return {}
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""SELECT DISTINCT ON (code) code, close FROM idx.bar WHERE source IN ('idx', 'yahoo') AND trade_date < %s AND code = ANY(%s)
                       ORDER BY code, trade_date DESC""", (d, codes))
        return {r["code"]: float(r["close"]) for r in cur.fetchall() if r["close"]}


def watched_codes(conn: psycopg.Connection) -> tuple[list[str], dict[str, list[str]]]:
    """Held names plus the latest watch list, restricted to what the feed collects."""
    from .feed import store as fs
    held = held_names(conn)
    lw = latest_watch(conn)
    listed = {r["code"] for r in lw["rows"]}
    in_feed = {c for codes in fs.symbols(conn).values() for c in codes}
    return sorted((set(held) | listed) & in_feed), held


def in_session(now: datetime) -> bool:
    return now.weekday() < 5 and SESSION_FROM <= now.time() <= SESSION_TO


def touch_check(conn: psycopg.Connection, now: datetime | None = None, force: bool = False) -> dict[str, Any]:
    """Every couple of minutes in the session: for every held or watched name in the feed, has today's high reached the
    limit, and is it locked, queued, or fading now? A new state raises one alert (which pushes the owner's phone via
    ``runlog.alert``) carrying the study-#101 number for that state. Idempotent: a state already alerted is silent."""
    now = now or datetime.now(WIB)
    d = now.date()
    if not force and not in_session(now):
        return {"date": str(d), "skipped": "outside the session", "touches": []}
    codes, held = watched_codes(conn)
    prev = prev_closes(conn, d, codes)
    feed = _feed_today(conn, d, codes)
    touches, new = [], []
    for code in codes:
        pc = prev.get(code)
        f = feed.get(code)
        if not pc or not f:
            continue
        ara = ara_price(pc)
        state = classify(f.get("high"), f.get("last"), ara, f.get("offer_px"), f.get("offer_vol"))
        if state is None:
            continue
        row = {"code": code, "state": state, "ara_px": ara, "prev_close": pc, "high": f.get("high"), "last": f.get("last"),
               "offer_px": f.get("offer_px"), "offer_vol": f.get("offer_vol"), "held": held.get(code, [])}
        touches.append(row)
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT state, first_ts FROM idx.ara_touch WHERE trade_date = %s AND code = %s", (d, code))
            old = cur.fetchone()
            first_ts = old["first_ts"] if old and old["first_ts"] else _first_touch_ts(conn, d, code, ara)
            cur.execute("""INSERT INTO idx.ara_touch (trade_date, code, ara_px, prev_close, state, first_ts, last_ts, high, last_price, offer_px, offer_vol)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                           ON CONFLICT (trade_date, code) DO UPDATE SET state = EXCLUDED.state, last_ts = EXCLUDED.last_ts, high = EXCLUDED.high,
                               last_price = EXCLUDED.last_price, offer_px = EXCLUDED.offer_px, offer_vol = EXCLUDED.offer_vol, updated_at = now()""",
                        (d, code, ara, pc, state, first_ts, f.get("last_ts"), f.get("high"), f.get("last"), f.get("offer_px"), f.get("offer_vol")))
        conn.commit()
        changed = not old or old["state"] != state
        if changed:
            fact = {"locked": FACT_LOCKED, "faded": FACT_FADED, "at_ara": FACT_AT_ARA}[state]
            word = {"locked": "terkunci di ARA", "faded": "memudar dari ARA", "at_ara": "di ARA, penjual masih antre"}[state]
            who = f" · dipegang {','.join(held[code])}" if code in held else ""
            msg = f"{code} {word} Rp {ara:,.0f} ({d}){who}: terakhir Rp {f.get('last') or 0:,.0f}. {fact}"
            job = f"book:{held[code][0]}" if code in held else "ara"          # a held name's alert goes to that book's owner
            if runlog.alert_once(conn, "warning", job, msg, kind="ara", strategy="ara_sell", code=code,
                                 book=(held[code][0] if code in held else None),
                                 payload={"state": state, "ara": str(ara), "last": str(f.get("last") or ""), "date": str(d)},
                                 dedupe_key=f"ara:{code}:{d}"):
                new.append(row)
    logger.info("idx ara touch %s: %d touched, %d new", d, len(touches), len(new))
    return {"date": str(d), "checked": len(codes), "touches": touches, "new": [r["code"] for r in new]}


def touches_today(conn: psycopg.Connection, d: date | None = None) -> list[dict[str, Any]]:
    d = d or datetime.now(WIB).date()
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""SELECT trade_date, code, ara_px, prev_close, state, first_ts, last_ts, high, last_price, offer_px, offer_vol, updated_at
                       FROM idx.ara_touch WHERE trade_date = %s ORDER BY first_ts NULLS LAST, code""", (d,))
        return [dict(r) for r in cur.fetchall()]


def render_touches(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "Belum ada sentuhan ARA hari ini di nama yang dipantau."
    word = {"locked": "terkunci", "faded": "memudar", "at_ara": "di ARA, penjual antre"}
    L = []
    for r in rows:
        first = f" · pertama {r['first_ts'].astimezone(WIB):%H:%M}" if r.get("first_ts") else ""
        L.append(f"{r['code']}: {word[r['state']]} · ARA Rp {Decimal(r['ara_px']):,.0f} · terakhir Rp {Decimal(r['last_price'] or 0):,.0f}{first}")
    return "\n".join(L)
