"""ARA watch: which names are likely to touch the upper auto-rejection price tomorrow, and what a holder's name is doing
when it gets there today (operator, 2026-09-23: "kasih alert supaya kita finding saham potensial untuk ARA" and "menyentuh
ARA jadi kita jual di harga paling atas").

What the research settled (research/IDX_ARA_2026-09-21.md, IDX_ML_ARA_2026-09-22.md, IDX_ARA_SELL_2026-09-23.md):
  * tomorrow's touch is predictable from today's bars: walk-forward 2022-26, AUC 0.86-0.92, the top-5 names a day touch
    7-18 % of the time against a 0.3-0.9 % base rate (17-27x). The nightly list here is that model, bar-only features.
  * it is NOT a trade: the names that keep going open locked (no offer), the ones that can be bought lose (menu 16, 0/24;
    menu 29f: buying any gap-up loses). Nothing here writes a ticket.
  * for a HOLDER the fact that matters is whether the touch holds to the close: a LOCKED close is followed by +431 bps the
    next day against the ARA price (liquid names, n 440, t 8); a FADED touch closes 661 bps under it (n 231, t 15). The
    intraday check reads that state off the tick feed and tells the phone, with those numbers, nothing more.

Two entry points, both scheduled (scheduler.py): ``watch`` in the evening after the bar lands, ``touch_check`` every two
minutes during the session. Read-only on the market tables; writes idx.ara_watch / idx.ara_touch / idx.alert.
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

from . import runlog

logger = logging.getLogger(__name__)
WIB = ZoneInfo("Asia/Jakarta")
SESSION_FROM, SESSION_TO = time(8, 58), time(16, 1)
TOP_N = 10
MIN_VALUE20 = 1e9                       # Rp 1 bn mean daily value: below this the bars are too thin to score
MIN_PREV = 50.0
ROUNDS = 300
PARAMS = {"objective": "binary", "learning_rate": 0.05, "num_leaves": 31, "min_data_in_leaf": 500, "bagging_fraction": 0.8,
          "bagging_freq": 1, "feature_fraction": 0.8, "lambda_l2": 10.0, "seed": 20260923, "verbose": -1, "num_threads": 8}
FEATS = ["ret1", "ret5", "ret20", "streak", "lock_yday", "touch_yday", "days_since_touch", "vol_ratio", "value20", "band", "clv",
         "hl_range", "up_days", "dist_hi20", "age_days", "dow"]
# the two numbers a holder gets, from menu 34 (study #101), liquid names 2020-2026
FACT_LOCKED = "kunci yang bertahan sampai tutup: hari berikutnya rata-rata +431 bps vs harga ARA (likuid, n 440, studi #101)"
FACT_FADED = "sentuhan yang memudar: tutup hari itu rata-rata -661 bps vs harga ARA (likuid, n 231, studi #101)"
FACT_AT_ARA = "harga di ARA dengan penjual masih antre: belum terkunci; 59 % sentuhan bertahan sampai tutup (studi #101)"


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


# ---- features from daily bars ----------------------------------------------------------------------------------------
def features(B: pd.DataFrame) -> pd.DataFrame:
    """One row per bar, columns FEATS + touch/lock/touch_next, from a frame with code, d, high, close, volume, value sorted
    by (code, d). Pure pandas/numpy so the tests can feed it a synthetic tape."""
    B = B.sort_values(["code", "d"]).reset_index(drop=True).copy()
    g = B.groupby("code", sort=False)
    B["prev"] = g["close"].shift(1)
    prev = B["prev"].to_numpy(float)
    B["ara_px"] = [ara_price(p) if np.isfinite(p) and p > 0 else np.nan for p in prev]
    B["touch"] = (B["high"] >= B["ara_px"] - 1e-9) & (B["prev"] >= MIN_PREV)
    B["lock"] = B["touch"] & (B["close"] >= B["ara_px"] - 1e-9)
    B["ret1"] = B["close"] / B["prev"] - 1
    B["ret5"] = B["close"] / g["close"].shift(5) - 1
    B["ret20"] = B["close"] / g["close"].shift(20) - 1
    B["lock_yday"] = g["lock"].shift(1).astype(float)
    B["touch_yday"] = g["touch"].shift(1).astype(float)
    codes = B["code"].to_numpy()
    lk, tc = B["lock"].to_numpy(), B["touch"].to_numpy()
    up = (B["ret1"] > 0).to_numpy()
    streak, updays, since = np.zeros(len(B)), np.zeros(len(B)), np.full(len(B), 60.0)
    for i in range(len(B)):
        same = i > 0 and codes[i] == codes[i - 1]
        streak[i] = streak[i - 1] + 1 if (same and lk[i]) else float(lk[i])
        updays[i] = updays[i - 1] + 1 if (same and up[i]) else float(up[i])
        since[i] = 0.0 if tc[i] else (min(60.0, since[i - 1] + 1) if same else 60.0)
    B["streak"], B["up_days"], B["days_since_touch"] = streak, updays, since
    v20 = g["volume"].transform(lambda x: x.rolling(20, min_periods=5).mean())
    B["vol_ratio"] = B["volume"] / v20.replace(0, np.nan)
    B["value20_rp"] = g["value"].transform(lambda x: x.rolling(20, min_periods=5).mean())
    B["value20"] = np.log1p(B["value20_rp"])
    B["band"] = np.select([B["close"] <= 200, B["close"] <= 5000], [0, 1], 2)
    rng = (B["high"] - B["low"]).replace(0, np.nan) if "low" in B else pd.Series(np.nan, index=B.index)
    B["clv"] = ((B["close"] - B["low"]) / rng) if "low" in B else 0.5
    B["hl_range"] = ((B["high"] - B["low"]) / B["prev"]) if "low" in B else (B["high"] / B["prev"] - 1)
    B["dist_hi20"] = B["close"] / g["high"].transform(lambda x: x.rolling(20, min_periods=5).max()) - 1
    B["age_days"] = g.cumcount().astype(float)
    B["dow"] = pd.to_datetime(B["d"]).dt.dayofweek.astype(float)
    B["touch_next"] = g["touch"].shift(-1).astype(float)
    return B


def load_bars(conn: psycopg.Connection, since: date | None = None) -> pd.DataFrame:
    with conn.cursor(row_factory=tuple_row) as cur:                      # the desk's connections default to dict rows
        cur.execute("""SELECT code, trade_date, high, low, close, volume, value FROM idx.bar
                       WHERE source IN ('idx', 'yahoo') AND close > 0 AND (%s::date IS NULL OR trade_date >= %s) ORDER BY code, trade_date""", (since, since))
        B = pd.DataFrame(cur.fetchall(), columns=["code", "d", "high", "low", "close", "volume", "value"])
    for c in ("high", "low", "close", "volume", "value"):
        B[c] = pd.to_numeric(B[c], errors="coerce").astype(float)
    B["d"] = pd.to_datetime(B["d"])
    return B


def train_and_score(B: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Fit on every labelled row (label = touch on the next bar), score the last bar of every name."""
    import lightgbm as lgb
    F = features(B)
    F = F[(F["prev"] >= MIN_PREV) & (F["value20_rp"] >= MIN_VALUE20)]
    last_d = F["d"].max()
    tr = F.dropna(subset=[*FEATS, "touch_next"])
    tr = tr[tr["d"] < last_d]
    if len(tr) < 5000 or tr["touch_next"].sum() < 100:
        raise RuntimeError(f"ara: not enough history to fit ({len(tr)} rows, {int(tr['touch_next'].sum())} touches)")
    m = lgb.train(PARAMS, lgb.Dataset(tr[FEATS].to_numpy(float), tr["touch_next"].to_numpy(), feature_name=FEATS), ROUNDS)
    te = F[F["d"] == last_d].dropna(subset=FEATS).copy()
    te["p"] = np.asarray(m.predict(te[FEATS].to_numpy(float)))
    te["ara_next"] = [ara_price(c) for c in te["close"].to_numpy(float)]
    info = {"bar_date": last_d.date(), "rows_fit": len(tr), "touches_fit": int(tr["touch_next"].sum()), "scored": len(te),
            "base_rate": float(tr["touch_next"].mean())}
    return te.sort_values("p", ascending=False), info


# ---- the nightly list ------------------------------------------------------------------------------------------------
def held_names(conn: psycopg.Connection) -> dict[str, list[str]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""SELECT p.code, array_agg(p.book ORDER BY p.book) AS books FROM idx.position p JOIN idx.book b USING (book)
                       WHERE p.lots > 0 AND b.archived_at IS NULL AND p.book NOT LIKE 'test%%' GROUP BY p.code""")
        return {r["code"]: list(r["books"]) for r in cur.fetchall()}


def select_rows(scored: pd.DataFrame, held: dict[str, list[str]], top: int = TOP_N) -> list[dict[str, Any]]:
    """The top-N by score, then every held name not already in it (rank NULL). Pure, for the tests."""
    out, seen = [], set()
    for rank, r in enumerate(scored.head(top).itertuples(), start=1):
        out.append({"code": r.code, "rank": rank, "p": float(r.p), "prev_close": float(r.close), "ara_px": float(r.ara_next),
                    "held": r.code in held, "books": held.get(r.code, []), "features": {k: float(getattr(r, k)) for k in FEATS}})
        seen.add(r.code)
    by_code = {r.code: r for r in scored.itertuples()}
    for code in sorted(held):
        if code in seen or code not in by_code:
            continue
        r = by_code[code]
        out.append({"code": code, "rank": None, "p": float(r.p), "prev_close": float(r.close), "ara_px": float(r.ara_next),
                    "held": True, "books": held[code], "features": {k: float(getattr(r, k)) for k in FEATS}})
    return out


def render_watch(rows: list[dict[str, Any]], bar_date: date, base_rate: float) -> str:
    top = [r for r in rows if r["rank"]]
    hold = [r for r in rows if r["held"]]
    L = [f"ARA watch untuk sesi setelah {bar_date:%d %b}: skor model dari bar harian (studi ML-3: top-5/hari menyentuh ARA 7-18 % vs dasar {base_rate * 100:.1f} %).",
         "Bukan tiket: yang benar-benar lanjut membuka terkunci, yang bisa dibeli rugi (menu 16).", "Daftar:"]
    L += [f"- {r['code']} P {r['p'] * 100:.0f} %, ARA Rp {r['ara_px']:,.0f} (tutup {r['prev_close']:,.0f}){' · dipegang ' + ','.join(r['books']) if r['held'] else ''}" for r in top]
    if hold:
        L.append("Nama yang dipegang:")
        L += [f"- {r['code']} P {r['p'] * 100:.1f} %, ARA Rp {r['ara_px']:,.0f} ({','.join(r['books'])})" for r in hold]
    L.append(f"Kalau menyentuh: {FACT_LOCKED}; {FACT_FADED}.")
    return "\n".join(L)


def watch(conn: psycopg.Connection, top: int = TOP_N, notify: bool = True, run_date: date | None = None) -> dict[str, Any]:
    run_date = run_date or datetime.now(WIB).date()
    scored, info = train_and_score(load_bars(conn))
    held = held_names(conn)
    rows = select_rows(scored, held, top)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM idx.ara_watch WHERE run_date = %s", (run_date,))
        for r in rows:
            cur.execute("""INSERT INTO idx.ara_watch (run_date, bar_date, code, rank, p, prev_close, ara_px, held, books, features)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)""",
                        (run_date, info["bar_date"], r["code"], r["rank"], round(r["p"], 5), r["prev_close"], r["ara_px"], r["held"], r["books"],
                         pd.Series(r["features"]).to_json()))
    conn.commit()
    text = render_watch(rows, info["bar_date"], info["base_rate"])
    if notify:
        runlog.alert_once(conn, "info", "ara", f"ARA watch {run_date}: " + ", ".join(f"{r['code']} {r['p'] * 100:.0f} %" for r in rows if r["rank"]))
        try:
            from . import notify as nf
            nf.send(text, title=f"ARA watch {run_date:%d %b}", data={"route": "/m/more", "kind": "ara"})
        except Exception:                                                  # a notification never fails the job
            logger.exception("ara watch notify failed")
    logger.info("idx ara watch %s: %s", run_date, info)
    return {"run_date": run_date, **info, "rows": rows, "text": text}


def latest_watch(conn: psycopg.Connection) -> dict[str, Any]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT max(run_date) AS d FROM idx.ara_watch")
        d = cur.fetchone()["d"]
        if d is None:
            return {"run_date": None, "rows": []}
        cur.execute("""SELECT run_date, bar_date, code, rank, p, prev_close, ara_px, held, books, features FROM idx.ara_watch
                       WHERE run_date = %s ORDER BY rank NULLS LAST, p DESC""", (d,))
        return {"run_date": d, "rows": [dict(r) for r in cur.fetchall()]}


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
            if runlog.alert_once(conn, "warning", job, msg):
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
