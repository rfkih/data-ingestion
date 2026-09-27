#!/usr/bin/env python3
"""IDX menu MK-1 PRELIM - two-sided tick capture as a MAKER on wide-tick names (operator 2026-09-27: "day trading harus bisa"
-> plan step 2 "jadi maker, bukan taker").

WHY. DT-2/DT-3 (#397, #398): intraday signals are real but a taker pays ~37 bps of spread + 40 bps of fees. The literature
(Barber, Lee, Liu, Odean - Taiwan) finds the profitable day traders provide liquidity. On IDX the tick ladder makes ONE tick
large on some prices (Rp 150: tick 1 = 67 bps; Rp 520: tick 5 = 96 bps), larger than the 40 bps round-trip fee. A resting bid
at the best bid, then a resting offer one tick higher, earns that tick when both fill - IF the fills are not adversely
selected (the bid fills because the price is falling). Menu 28b-1 (#?, one day, 1-min books) posted directional bids and lost
~50 bps a fill; this is the two-sided, queue-aware version on the full tick data.

DATA: idx.feed_trade (every print) + idx.feed_book (every book update, 10 levels), sessions 2026-09-22 .. 09-25, ~135 names.

SIMULATION (queue-aware, conservative): decision marks every 5 minutes in 09:05-11:45 and 13:35-15:30 (Friday: session 1 to
11:25, session 2 from 14:05); one position per name. At a mark, if the book is fresh (< 60 s), the spread is exactly one tick
and tick / mid >= theta: post a BUY at the best bid, joining the BACK of the queue (queue ahead = the level's volume; later
cancellations ahead of us are ignored = fewer fills than reality). The bid fills when prints AT the bid after the post exceed
queue ahead + our size, or at once on any print below it. Unfilled after 10 min (or at the session break) -> cancelled.
After a fill: post a SELL at bid + 1 tick behind that level's queue (0 ahead if the offer sits higher); it fills on prints at
that price beyond the queue, or at once on a print above it. Exits otherwise: STOP when the best bid falls 2 ticks below the
entry -> sell to the best bid; 30 minutes without the offer filling -> sell to the best bid; still open at 15:40 -> the closing
auction (daily_summary.close). Size Rp 10 m (whole lots). Fees 0.15 % buy + 0.25 % sell; stress 0.10 / 0.20 % reported too.

PRE-REGISTERED (4 trials; cumulative 1063 + 4 = 1067).
  M1  theta 60 bps, stop 2 ticks            M2  theta 100 bps, stop 2 ticks
  M3  M1 + book tilt: best-bid volume >= 1.5 x best-offer volume at the post (queue imbalance leads the mid, menu 28)
  M4  M1 without the stop (exit at the offer, the 30-min taker exit, or the auction)
READING RULE (4 sessions = a direction read): PRELIM LEAD only if ALL: >= 100 round trips; mean net > 0 at 0.15/0.25 fees;
t across name-days >= 2; positive on >= 3 of the 4 days. A lead goes to a forward re-run at >= 20 sessions, nothing else.
Also reported: fill rate, share of entries exited at the offer, adverse selection (mid 5 min after the bid fill vs the bid).
READ-ONLY on the DB except one idx.study row (--no-store to skip).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "blackheart-ingest", "src"))
WIB = ZoneInfo("Asia/Jakarta")
STUDY, N_BEFORE = "maker_tick", 1063
DAYS = [date(2026, 9, 22), date(2026, 9, 23), date(2026, 9, 24), date(2026, 9, 25)]
SIZE_RP, POST_TTL, EXIT_TTL, FRESH = 10e6, 600, 1800, 60
FEES = {"retail": (0.0015, 0.0025), "low": (0.0010, 0.0020)}
TRIALS = {"M1": dict(theta=0.006, stop=2, tilt=None), "M2": dict(theta=0.010, stop=2, tilt=None),
          "M3": dict(theta=0.006, stop=2, tilt=1.5), "M4": dict(theta=0.006, stop=None, tilt=None)}


def dsn() -> str:
    return os.environ.get("INGEST_DB_DSN") or [ln.split("=", 1)[1].strip() for ln in open(os.path.join(ROOT, "blackheart-ingest", "idx-local.env"))
                                                if ln.startswith("INGEST_DB_DSN=")][0]


def tick(p: float) -> float:
    return 1 if p < 200 else 2 if p < 500 else 5 if p < 2000 else 10 if p < 5000 else 25


def marks(d: date) -> list[datetime]:
    fri = d.weekday() == 4
    s1 = (time(9, 5), time(11, 25) if fri else time(11, 45))
    s2 = (time(14, 5) if fri else time(13, 35), time(15, 30))
    out = []
    for a, b in (s1, s2):
        t = datetime.combine(d, a, WIB)
        while t.time() <= b:
            out.append(t)
            t += timedelta(minutes=5)
    return out


def session_end(t: datetime) -> datetime:
    fri = t.weekday() == 4
    e1 = time(11, 30) if fri else time(12, 0)
    return datetime.combine(t.date(), e1 if t.time() < e1 else time(15, 49, 59), WIB)


def load_day(conn, d: date):
    lo, hi = datetime.combine(d, time(8, 50), WIB), datetime.combine(d, time(15, 50), WIB)
    bk = pd.DataFrame(conn.execute("""SELECT code, ts, bid_px[1], bid_vol[1], off_px[1], off_vol[1], off_px[2], off_vol[2]
                                      FROM idx.feed_book WHERE ts >= %s AND ts < %s ORDER BY code, ts, seq""", (lo, hi)).fetchall(),
                      columns=["code", "ts", "b1", "bv1", "o1", "ov1", "o2", "ov2"])
    tr = pd.DataFrame(conn.execute("""SELECT code, ts, price, qty FROM idx.feed_trade
                                      WHERE ts >= %s AND ts < %s AND board = '1' ORDER BY code, ts, seq""", (lo, hi)).fetchall(),
                      columns=["code", "ts", "px", "qty"])
    close = dict(conn.execute("SELECT code, close FROM idx.daily_summary WHERE trade_date = %s", (d,)).fetchall())
    return bk, tr, close


def sim_name_day(code, d, B, T, close_px, p):
    """All round trips of one name on one day under trial parameters p."""
    bts = B.ts.values.astype("datetime64[ns]").astype(np.int64)
    tts = T.ts.values.astype("datetime64[ns]").astype(np.int64)
    tpx, tq = T.px.to_numpy(float), T.qty.to_numpy(float)
    b1, bv1, o1, ov1 = (B[c].to_numpy(float) for c in ("b1", "bv1", "o1", "ov1"))
    o2, ov2 = B.o2.to_numpy(float), B.ov2.to_numpy(float)

    def book_at(t_ns):
        i = np.searchsorted(bts, t_ns, side="right") - 1
        return i if i >= 0 else None

    out, busy_until = [], 0
    ns = lambda dt: int(pd.Timestamp(dt).value)
    for m in marks(d):
        t0 = ns(m)
        if t0 < busy_until:
            continue
        i = book_at(t0)
        if i is None or t0 - bts[i] > FRESH * 1e9 or not (b1[i] > 0 and o1[i] > 0):
            continue
        L, tk = b1[i], tick(b1[i])
        if o1[i] - L != tk or tk / ((L + o1[i]) / 2) < p["theta"]:
            continue
        if p["tilt"] and not (bv1[i] >= p["tilt"] * ov1[i]):
            continue
        size = max(100, int(SIZE_RP / L / 100) * 100)
        ahead = bv1[i]
        # --- entry: resting bid at L ---
        deadline = min(t0 + POST_TTL * 1e9, ns(session_end(m)))
        j = np.searchsorted(tts, t0, side="right")
        filled_at, used = None, 0.0
        while j < len(tts) and tts[j] <= deadline:
            if tpx[j] < L:
                filled_at, through = tts[j], True
                break
            if tpx[j] == L:
                used += tq[j]
                if used >= ahead + size:
                    filled_at, through = tts[j], False
                    break
            j += 1
        if filled_at is None:
            out.append(dict(code=code, d=d, filled=False))
            continue
        # adverse selection: mid 5 min after the fill
        k = book_at(filled_at + 300e9)
        mid5 = (b1[k] + o1[k]) / 2 if k is not None and b1[k] > 0 and o1[k] > 0 else np.nan
        # --- exit: resting offer at E = L + tick ---
        E = L + tk
        k = book_at(filled_at)
        q = ov1[k] if o1[k] == E else (ov2[k] if o2[k] == E else 0.0) if o1[k] < E else 0.0
        exit_dl = min(filled_at + EXIT_TTL * 1e9, ns(datetime.combine(d, time(15, 40), WIB)))
        jj, used, sell, kind = j + 1, 0.0, None, None
        stop_px = L - p["stop"] * tk if p["stop"] else None
        kb = np.searchsorted(bts, filled_at, side="right")
        while True:
            nt = tts[jj] if jj < len(tts) else np.inf
            nb = bts[kb] if kb < len(bts) else np.inf
            nxt = min(nt, nb)
            if nxt > exit_dl:
                break
            if nb <= nt:                                                 # a book update: the stop reads the best bid
                if stop_px is not None and 0 < b1[kb] <= stop_px:
                    sell, kind = b1[kb], "stop"
                    break
                kb += 1
            else:
                if tpx[jj] > E:
                    sell, kind = E, "offer"
                    break
                if tpx[jj] == E:
                    used += tq[jj]
                    if used >= q + size:
                        sell, kind = E, "offer"
                        break
                jj += 1
        if sell is None:
            if exit_dl >= ns(datetime.combine(d, time(15, 40), WIB)) and close_px:
                sell, kind = float(close_px), "auction"
            else:
                k = book_at(exit_dl)
                sell, kind = (b1[k] if k is not None and b1[k] > 0 else L), "timeout"
        busy_until = int(filled_at + 1)
        out.append(dict(code=code, d=d, filled=True, buy=L, sell=float(sell), kind=kind, tick_bps=tk / L * 1e4, through=through,
                        ahead_rp=ahead * L, wait_s=(filled_at - t0) / 1e9,
                        adverse_bps=(mid5 / L - 1) * 1e4 if np.isfinite(mid5) else np.nan))
    return out


def net(buy, sell, fees, m=1.0):
    fb, fs = fees
    return sell * (1 - m * fs) / (buy * (1 + m * fb)) - 1


def evaluate(rows):
    df = pd.DataFrame(rows)
    posts = len(df)
    f = df[df.filled == True].copy()  # noqa: E712
    if f.empty:
        return dict(posts=posts, n=0, verdict="no trades")
    f["net"] = [net(b, s, FEES["retail"]) for b, s in zip(f.buy, f.sell)]
    f["net_low"] = [net(b, s, FEES["low"]) for b, s in zip(f.buy, f.sell)]
    f["gross"] = f.sell / f.buy - 1
    nd = f.groupby(["code", "d"]).net.mean()
    t = nd.mean() / nd.std(ddof=1) * np.sqrt(len(nd)) if len(nd) > 2 else np.nan
    by_day = f.groupby("d").net.mean()
    r = dict(posts=posts, n=len(f), fill_rate=len(f) / posts, names=int(f.code.nunique()),
             exits={k: round(v, 3) for k, v in f.kind.value_counts(normalize=True).items()},
             tick_bps=f.tick_bps.median(), gross_bps=f.gross.mean() * 1e4, net_bps=f.net.mean() * 1e4,
             net_low_bps=f.net_low.mean() * 1e4, median_bps=f.net.median() * 1e4, hit=float((f.net > 0).mean()),
             t_namedays=float(t), by_day={str(k): round(v * 1e4, 1) for k, v in by_day.items()},
             adverse_bps=float(np.nanmean(f.adverse_bps)))
    checks = dict(n100=r["n"] >= 100, net_pos=r["net_bps"] > 0, t2=r["t_namedays"] >= 2, days=int((by_day > 0).sum()) >= 3)
    r["checks"], r["verdict"] = checks, "PRELIM LEAD" if all(checks.values()) else "no"
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-store", action="store_true")
    a = ap.parse_args()
    rows = {k: [] for k in TRIALS}
    with psycopg.connect(dsn()) as conn:
        for d in DAYS:
            bk, tr, close = load_day(conn, d)
            print(d, "book", len(bk), "trades", len(tr), flush=True)
            tg = dict(tuple(tr.groupby("code")))
            for code, B in bk.groupby("code"):
                T = tg.get(code)
                if T is None or len(T) < 50:
                    continue
                for k, p in TRIALS.items():
                    rows[k] += sim_name_day(code, d, B.reset_index(drop=True), T.reset_index(drop=True), close.get(code), p)
    res = {k: evaluate(v) for k, v in rows.items()}
    for k, r in res.items():
        print(k, json.dumps(r, default=str))
    json.dump(res, open(os.path.join(HERE, "IDX_MAKER_TICK_2026-09-27.json"), "w"), indent=1, default=str)
    pd.DataFrame([r for r in rows["M4"] if r.get("filled")]).to_parquet(os.path.join(ROOT, "research-scratch", "idx", "daytrade2", "maker_m4_fills.parquet"))
    if not a.no_store:
        from blackheart_ingest.idx import research_store as rs
        with psycopg.connect(dsn()) as conn:
            sid = rs.record_study(conn, STUDY, date.today(), params={"trials": list(TRIALS), "n_trials_cumulative": N_BEFORE + len(TRIALS),
                                  "days": [str(d) for d in DAYS], "size_rp": SIZE_RP}, summary=res, names=[],
                                  report_path="research/IDX_MAKER_TICK_2026-09-27.md")
            print("study id", sid)


if __name__ == "__main__":
    main()
