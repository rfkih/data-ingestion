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
from .exchange_calendar import is_trading_day

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


# ---- prediction vs actual ----------------------------------------------------------------------------------------------
# Operator 2026-09-27: "aku mau pencatatan lengkap dari prediksi dan aktualnya". Measurement only (the ARA freeze): every
# stored score gets what the next session did, with the model's own labels, and every run gets one scorecard row.
SETTLE_COMPLETE = 0.8          # the next session's summary counts as in once it has >= 80 % of the run day's rows
TOP_KS = (5, 10, 20)
_NO_ROW = {"next_ara_px": None, "touched": None, "locked": None, "ret_close": None, "ret_high": None, "outcome": "no_bar"}


def outcome_of(prev: float | None, high: float | None, close: float | None, volume: float | None) -> dict[str, Any]:
    """What the next session did for one name. The labels are the model's (ara_model.Panel._labels): the limit comes from
    IDX's previous for that session, TOUCH = high at or above it, LOCK = close at or above it. Pure, for the tests."""
    if prev is None or close is None or not prev > 0 or not close > 0:
        return {**_NO_ROW, "outcome": "no_trade"}
    lim = ara_price(prev)
    touched = high is not None and high >= lim - 1e-6
    locked = close >= lim - 1e-6
    outcome = "lock" if locked else "touch" if touched else "no_trade" if not volume else "none"
    return {"next_ara_px": lim, "touched": bool(touched), "locked": bool(locked), "ret_close": close / prev - 1,
            "ret_high": (high / prev - 1) if high else None, "outcome": outcome}


def score_run(rows: list[dict[str, Any]], universe: int | None, universe_locks: int | None,
              universe_touches: int | None) -> dict[str, Any]:
    """One run's grade from its settled rows (rank, listed, p_lock, score, buyable, locked, touched). Precision@k counts
    the top-k by rank; AUC and Brier only when the run kept the whole ranking (a list-only run has no negatives to rank
    against). Pure, for the tests."""
    settled = [r for r in rows if r.get("locked") is not None]
    ranked = sorted((r for r in settled if r.get("rank") is not None), key=lambda r: r["rank"])
    out: dict[str, Any] = {"universe": universe, "universe_locks": universe_locks, "universe_touches": universe_touches,
                           "base_rate": (universe_locks / universe) if universe and universe_locks is not None else None}
    for k in TOP_KS:
        top = [r for r in ranked if r["rank"] <= k]
        out[f"top{k}_locks"] = sum(bool(r["locked"]) for r in top)
        out[f"top{k}_touches"] = sum(bool(r["touched"]) for r in top)
        out[f"top{k}_n"] = len(top)
        out[f"prec{k}"] = out[f"top{k}_locks"] / len(top) if top else None
    out["recall20"] = out["top20_locks"] / universe_locks if universe_locks else None
    listed = [r for r in settled if r.get("listed")]
    out["listed_locks"] = sum(bool(r["locked"]) for r in listed)
    out["listed_buyable"] = sum(bool(r.get("buyable")) for r in listed)
    out["listed_buyable_locks"] = sum(bool(r.get("buyable")) and bool(r["locked"]) for r in listed)
    p10 = [float(r["p_lock"]) for r in ranked if r["rank"] <= 10 and r.get("p_lock") is not None]
    out["mean_p_top10"] = float(np.mean(p10)) if p10 else None
    out["whole_ranking"] = any(not r.get("listed", True) for r in rows)
    out["auc_lock"] = out["auc_touch"] = out["brier_lock"] = None
    if out["whole_ranking"] and settled:
        s = np.array([float(r["score"] if r.get("score") is not None else r["p_lock"]) for r in settled])
        y_lock = np.array([float(r["locked"]) for r in settled])
        y_touch = np.array([float(bool(r["touched"])) for r in settled])
        if 0 < y_lock.sum() < len(y_lock):
            out["auc_lock"] = float(ara_model.auc(y_lock, s))
        if 0 < y_touch.sum() < len(y_touch):
            out["auc_touch"] = float(ara_model.auc(y_touch, s))
        if all(r.get("p_lock") is not None for r in settled):
            p = np.array([float(r["p_lock"]) for r in settled])
            out["brier_lock"] = float(np.mean((p - y_lock) ** 2))
    return out


def _next_session(conn: psycopg.Connection, bar_date: date) -> tuple[date | None, str | None]:
    """The session after ``bar_date`` if its official summary is in, else (None, why)."""
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute("SELECT min(trade_date) FROM idx.daily_summary WHERE trade_date > %s", (bar_date,))
        nd = cur.fetchone()[0]
        if nd is None:
            return None, "next session not in yet"
        cur.execute("""SELECT count(*) FILTER (WHERE trade_date = %s), count(*) FILTER (WHERE trade_date = %s)
                         FROM idx.daily_summary WHERE trade_date IN (%s, %s)""", (bar_date, nd, bar_date, nd))
        n_bar, n_next = cur.fetchone()
    if n_next < SETTLE_COMPLETE * n_bar:
        return None, f"next session {nd} only partly in ({n_next} of ~{n_bar} rows)"
    return nd, None


_SC_COLS = ["run_date", "bar_date", "next_date", "model", "whole_ranking", "n_stored", "n_listed", "universe", "universe_locks",
            "universe_touches", "base_rate", "top5_locks", "top10_locks", "top20_locks", "top5_touches", "top10_touches", "top20_touches",
            "top5_n", "top10_n", "top20_n", "prec5", "prec10", "prec20", "recall20", "listed_locks", "listed_buyable", "listed_buyable_locks", "mean_p_top10",
            "auc_lock", "auc_touch", "brier_lock"]


def settle(conn: psycopg.Connection, run_date: date | None = None, force: bool = False) -> list[dict[str, Any]]:
    """Fill the next session's actuals on every unsettled run (or one run; ``force`` redoes settled ones) and write its
    scorecard. Idempotent; a run whose next session is not in yet stays pending and is picked up the next evening."""
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute("""SELECT run_date, max(bar_date) FROM idx.ara_watch
                        WHERE (%s::date IS NULL OR run_date = %s) AND (%s OR settled_at IS NULL)
                        GROUP BY run_date ORDER BY run_date""", (run_date, run_date, force))
        runs = cur.fetchall()
    out: list[dict[str, Any]] = []
    for rd, bd in runs:
        bd = bd or rd
        nd, why = _next_session(conn, bd)
        if nd is None:
            out.append({"run_date": rd, "bar_date": bd, "pending": why})
            continue
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""SELECT s.code, s.previous::float8 AS prev, COALESCE(b.open, s.open)::float8 AS open, s.high::float8 AS high,
                                  s.low::float8 AS low, s.close::float8 AS close, s.volume::float8 AS volume, s.offer_volume::float8 AS offer_volume
                             FROM idx.daily_summary s LEFT JOIN idx.bar b ON b.code = s.code AND b.trade_date = s.trade_date AND b.source = 'idx'
                            WHERE s.trade_date = %s""", (nd,))
            nxt = {r["code"]: r for r in cur.fetchall()}
            cur.execute("""SELECT code, rank, listed, held, COALESCE(p_lock, p)::float8 AS p_lock, score::float8 AS score, buyable, model
                             FROM idx.ara_watch WHERE run_date = %s""", (rd,))
            rows = [dict(r) for r in cur.fetchall()]
            # the names the model could score that evening (Panel.last_day, mirrored in coverage()): the recall denominator
            cur.execute("""SELECT code FROM idx.daily_summary WHERE trade_date = %s AND substr(remarks, 5, 1) IN ('1', '2')
                             AND close > 0 AND previous >= %s""", (bd, ara_model.MIN_PREV))
            uni = [r["code"] for r in cur.fetchall()]
        upd = []
        for r in rows:
            n = nxt.get(r["code"]) or {}
            o = outcome_of(n["prev"], n["high"], n["close"], n["volume"]) if n else dict(_NO_ROW)
            r.update(o)
            upd.append((nd if n else None, n.get("prev"), o["next_ara_px"], n.get("open"), n.get("high"), n.get("low"), n.get("close"),
                        n.get("volume"), n.get("offer_volume"), o["touched"], o["locked"],
                        None if o["ret_close"] is None else round(o["ret_close"], 6), None if o["ret_high"] is None else round(o["ret_high"], 6),
                        o["outcome"], rd, r["code"]))
        u_out = [outcome_of(nxt[c]["prev"], nxt[c]["high"], nxt[c]["close"], nxt[c]["volume"]) for c in uni if c in nxt]
        sc = score_run(rows, len(uni), sum(bool(o["locked"]) for o in u_out), sum(bool(o["touched"]) for o in u_out))
        vals = {**sc, "run_date": rd, "bar_date": bd, "next_date": nd, "model": next((r["model"] for r in rows if r.get("model")), None),
                "n_stored": len(rows), "n_listed": sum(bool(r.get("listed")) for r in rows)}
        with conn.cursor() as cur:
            cur.executemany("""UPDATE idx.ara_watch SET next_date = %s, next_prev = %s, next_ara_px = %s, next_open = %s, next_high = %s, next_low = %s,
                                      next_close = %s, next_volume = %s, next_offer_volume = %s, touched = %s, locked = %s, ret_close = %s,
                                      ret_high = %s, outcome = %s, settled_at = now()
                                WHERE run_date = %s AND code = %s""", upd)
            cur.execute(f"""INSERT INTO idx.ara_scorecard ({", ".join(_SC_COLS)}, settled_at) VALUES ({", ".join(["%s"] * len(_SC_COLS))}, now())
                            ON CONFLICT (run_date) DO UPDATE SET {", ".join(f"{c} = EXCLUDED.{c}" for c in _SC_COLS[1:])}, settled_at = now()""",
                        [vals[c] for c in _SC_COLS])
        conn.commit()
        out.append({"run_date": rd, "bar_date": bd, "next_date": nd, "rows": len(rows), **sc})
        logger.info("idx ara settle %s -> %s: %d rows, top10 locks %s, universe locks %s", rd, nd, len(rows), sc["top10_locks"], sc["universe_locks"])
    return out


_RECORD_COLS = """run_date, bar_date, code, rank, listed, held, COALESCE(p_lock, p) AS p_lock, p_touch, score, confidence, model, prev_close,
                  ara_px, locked_today, buyable, next_date, next_prev, next_ara_px, next_open, next_high, next_low, next_close, next_volume,
                  next_offer_volume, touched, locked, ret_close, ret_high, outcome, settled_at"""


def record(conn: psycopg.Connection, run_date: date | None = None, code: str | None = None, listed_only: bool = True,
           limit: int = 500) -> dict[str, Any]:
    """Prediction next to what happened. With ``code``: that name across runs, newest first. Otherwise one run (the
    newest settled one by default), in rank order; ``listed_only`` keeps the evening list, False gives every stored score."""
    with conn.cursor(row_factory=dict_row) as cur:
        if code:
            cur.execute(f"SELECT {_RECORD_COLS} FROM idx.ara_watch WHERE code = %s ORDER BY run_date DESC LIMIT %s", (code.upper(), limit))
            return {"code": code.upper(), "rows": [dict(r) for r in cur.fetchall()]}
        if run_date is None:
            cur.execute("SELECT max(run_date) AS d FROM idx.ara_watch WHERE settled_at IS NOT NULL")
            run_date = cur.fetchone()["d"]
            if run_date is None:
                return {"run_date": None, "rows": [], "scorecard": None}
        cur.execute(f"""SELECT {_RECORD_COLS} FROM idx.ara_watch WHERE run_date = %s AND (NOT %s OR listed OR held)
                        ORDER BY rank NULLS LAST, COALESCE(p_lock, p) DESC LIMIT %s""", (run_date, listed_only, limit))
        rows = [dict(r) for r in cur.fetchall()]
        cur.execute("SELECT * FROM idx.ara_scorecard WHERE run_date = %s", (run_date,))
        sc = cur.fetchone()
    return {"run_date": run_date, "rows": rows, "scorecard": dict(sc) if sc else None}


def scorecards(conn: psycopg.Connection, days: int = 60) -> dict[str, Any]:
    """The per-run grades, newest first, and the pooled figures over the model's runs next to study #146's range."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT * FROM idx.ara_scorecard ORDER BY run_date DESC LIMIT %s", (days,))
        rows = [dict(r) for r in cur.fetchall()]
        cur.execute("SELECT count(DISTINCT run_date) AS n FROM idx.ara_watch WHERE settled_at IS NULL")
        pending = cur.fetchone()["n"]
    model_rows = [r for r in rows if r.get("model")]           # the list before the study-#146 model (model NULL) is graded, not pooled
    pooled: dict[str, Any] = {"runs": len(model_rows)}
    for k in TOP_KS:
        n_top = sum(int(r[f"top{k}_n"] or 0) for r in model_rows)
        pooled[f"top{k}_locks"] = sum(int(r[f"top{k}_locks"] or 0) for r in model_rows)
        pooled[f"prec{k}"] = pooled[f"top{k}_locks"] / n_top if n_top else None
    locks = sum(int(r["universe_locks"] or 0) for r in model_rows)
    pooled["universe_locks"] = locks
    pooled["recall20"] = pooled["top20_locks"] / locks if locks else None
    uni = sum(int(r["universe"] or 0) for r in model_rows)
    pooled["base_rate"] = locks / uni if uni else None
    return {"rows": rows, "pooled": pooled, "pending_runs": int(pending or 0),
            "study": {"prec5": "8-20 %", "base_rate": "0.3-0.9 %", "recall20": "48-76 %", "auc": "0.88-0.93", "source": "study #146, 2022-2026 walk-forward"}}


def _pct(v: Any, signed: bool = False) -> str:
    if v is None:
        return "-"
    return f"{float(v) * 100:+.1f}%" if signed else f"{float(v) * 100:.1f}%"


def _num(v: Any, fmt: str) -> str:
    return "-" if v is None else format(float(v), fmt)


def render_record(rec: dict[str, Any]) -> str:
    if rec.get("code"):
        L = [f"{rec['code']}: prediksi ARA vs aktual ({len(rec['rows'])} malam)"]
        for r in rec["rows"]:
            L.append(f"  {r['run_date']} rank {r['rank'] or '-':>4} P(lock) {_pct(r['p_lock']):>6} -> sesi {r['next_date'] or 'belum'} "
                     f"{r['outcome'] or 'belum':<8} close {_pct(r['ret_close'], True):>7} high {_pct(r['ret_high'], True):>7}")
        return "\n".join(L)
    if not rec.get("run_date"):
        return "belum ada run ARA yang sudah diselesaikan"
    sc = rec.get("scorecard") or {}
    L = [f"ARA {rec['run_date']} (bar {sc.get('bar_date')}) -> sesi {sc.get('next_date')}, model {sc.get('model') or 'lama'}: "
         f"top5 {sc.get('top5_locks')} lock, top10 {sc.get('top10_locks')}, top20 {sc.get('top20_locks')}; "
         f"lock di pasar {sc.get('universe_locks')} dari {sc.get('universe')} nama; AUC {_num(sc.get('auc_lock'), '.3f')}",
         " rank kode    P(lock) P(touch)  beli -> hasil       close     high   harga_ARA  close_px"]
    for r in rec["rows"]:
        L.append(f" {r['rank'] or '-':>4} {r['code']:<6} {_pct(r['p_lock']):>7} {_pct(r['p_touch']):>8} {'ya' if r['buyable'] else 'tdk':>5} -> "
                 f"{r['outcome'] or 'belum':<9} {_pct(r['ret_close'], True):>7} {_pct(r['ret_high'], True):>8} {_num(r['next_ara_px'], ',.0f'):>11} "
                 f"{_num(r['next_close'], ',.0f'):>9}")
    return "\n".join(L)


def render_scorecards(s: dict[str, Any]) -> str:
    L = ["run        -> sesi        model  top5 top10 top20  lock_pasar/universe   prec5 recall20    AUC   Brier"]
    for r in s["rows"]:
        L.append(f"{r['run_date']} -> {r['next_date']}  {r['model'] or 'lama':<5} {r['top5_locks']:>4} {r['top10_locks']:>5} {r['top20_locks']:>5} "
                 f"{r['universe_locks'] if r['universe_locks'] is not None else '-':>10}/{r['universe'] or '-':<9} {_pct(r['prec5']):>6} "
                 f"{_pct(r['recall20']):>8} {_num(r['auc_lock'], '.3f'):>6} {_num(r['brier_lock'], '.4f'):>7}")
    p, st = s["pooled"], s["study"]
    L.append(f"gabungan {p['runs']} run model: prec5 {_pct(p['prec5'])} prec10 {_pct(p['prec10'])} prec20 {_pct(p['prec20'])} "
             f"recall20 {_pct(p['recall20'])} base rate {_pct(p['base_rate'])} | studi #146: prec5 {st['prec5']}, base {st['base_rate']}, "
             f"recall20 {st['recall20']}, AUC {st['auc']}")
    if s.get("pending_runs"):
        L.append(f"menunggu sesi berikutnya: {s['pending_runs']} run")
    return "\n".join(L)


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
    return is_trading_day(now) and SESSION_FROM <= now.time() <= SESSION_TO


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
