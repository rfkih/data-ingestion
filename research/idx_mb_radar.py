#!/usr/bin/env python3
"""IDX menu MB-1 - a multibagger RADAR, judged as a radar (operator 2026-09-27: "sebenarnya memang untuk mencari saham2 seperti
itu tujuannya" - the goal is FINDING names like ANTM / BRIS / HRTA / PANI, not a book with a Sharpe).

A radar is measured by what happens to the names it flags, against names picked at random ON THE SAME DATES from the same
universe (so the market's own rally is not credited to the flag):
  precision  P(the name touches 2x its flag-day close within 250 sessions)       - "ada berapa yang jadi multibagger"
  end2x      P(still >= 2x at session 250)
  lift       precision / the same-date random precision
  cost       P(the name is ever <= -30 % within 250 sessions) and the median 250-session return
Panel idx.bar (adj_factor) 2020-01 .. 2026-09-25; flags up to 2025-09-19 so every window is complete (events: 2023-07-03 on).
Universe on a flag day: 20-session mean value >= Rp 1 bn, close >= Rp 50. One flag per name per 120 sessions (the first).

PRE-REGISTERED FLAGS (8 trials; cumulative 1079 + 8 = 1087):
  F1 C0        close >= 1.3 x close 60 sessions ago, at its 250-day high, day return < 18 %
  F2 S1        F1 and 20-day value >= 3 x its 250-day mean (attention)
  F3 TREND     the deployed trend entry: 60-day high, > MA200, volume >= 1.5 x its 20-day median
  F4 CONTROL   a change-of-control / tender-offer announcement (event day)
  F5 RESTRUCT  a merger / business-change / material-transaction announcement (event day)
  F6 UMA       the issuer's reply to an exchange query (unusual market activity) - the exchange's own attention flag
  F7 C0+UMA    F1 on a day with an F6 reply in the prior 20 sessions
  F8 C0+EVENT  F1 on a day with an F4 or F5 announcement in the prior 120 sessions
READING RULE: a flag is USEFUL as a radar if lift >= 1.5 with >= 50 flags and the lift is >= 1.2 in each calendar year that has
>= 15 flags; its cost is reported, not judged (a radar that finds rockets also finds duds). The date-matched random precision
is the base. READ-ONLY on the DB except one idx.study row (--no-store to skip).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date

import numpy as np
import pandas as pd
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "blackheart-ingest", "src"))
STUDY, N_BEFORE = "mb_radar", 1079
H, GAP, LAST_FLAG = 250, 120, pd.Timestamp("2025-09-19")
RNG = np.random.default_rng(20260927)


def dsn() -> str:
    return os.environ.get("INGEST_DB_DSN") or [ln.split("=", 1)[1].strip() for ln in open(os.path.join(ROOT, "blackheart-ingest", "idx-local.env"))
                                                if ln.startswith("INGEST_DB_DSN=")][0]


def load(conn):
    df = pd.DataFrame(conn.execute("""SELECT code, trade_date, close * coalesce(adj_factor, 1), close, value, volume FROM idx.bar
                                      WHERE source = 'idx' AND close > 0""").fetchall(), columns=["code", "d", "ac", "c", "v", "vol"])
    for k in ("ac", "c", "v", "vol"):
        df[k] = df[k].astype(float)
    df["d"] = pd.to_datetime(df.d)
    W = {k: df.pivot(index="d", columns="code", values=k).sort_index() for k in ("ac", "c", "v", "vol")}
    ev = pd.DataFrame(conn.execute("""SELECT code, published_at::date, kind, lower(coalesce(title, '')) FROM idx.announcement
                                      WHERE code IS NOT NULL AND (kind IN ('control_change', 'exchange_query') OR title ~*
                                      '(pengambilalihan|pengendali|tender wajib|penggabungan usaha|merger|peleburan|perubahan kegiatan usaha|transaksi material)')""").fetchall(),
                      columns=["code", "d", "kind", "title"])
    ev["d"] = pd.to_datetime(ev.d)
    return W, ev


def event_mask(ev, idx, cols, pred):
    M = pd.DataFrame(False, index=idx, columns=cols)
    for r in ev[ev.apply(pred, axis=1)].itertuples():
        if r.code in M.columns:
            i = idx.searchsorted(r.d)
            if i < len(idx):
                M.iat[i, M.columns.get_loc(r.code)] = True
    return M


def recent(M, n):
    return M.astype(int).rolling(n, min_periods=1).max().astype(bool)


def outcomes(A, i, j):
    p0 = A[i, j]
    seg = A[i + 1:i + 1 + H, j]
    seg = seg[~np.isnan(seg)]
    if not np.isfinite(p0) or len(seg) < 200:
        return None
    return (seg.max() / p0 >= 2.0, seg[-1] / p0 >= 2.0, seg.min() / p0 <= 0.7, seg[-1] / p0 - 1)


def evaluate(F, A, elig, idx, name, event_from=None):
    Fm = F.to_numpy(bool) & elig
    last = {}
    rows, base = [], {}
    lo = idx.searchsorted(pd.Timestamp(event_from)) if event_from else 250
    hi = idx.searchsorted(LAST_FLAG, side="right")
    for i in range(lo, hi):
        for j in np.flatnonzero(Fm[i]):
            if j in last and i - last[j] < GAP:
                continue
            last[j] = i
            o = outcomes(A, i, j)
            if o is None:
                continue
            if i not in base:                                            # date-matched random base: 60 eligible names
                pool = np.flatnonzero(elig[i])
                pick = RNG.choice(pool, size=min(60, len(pool)), replace=False)
                bo = [outcomes(A, i, k) for k in pick]
                bo = [b for b in bo if b is not None]
                base[i] = np.mean([b[0] for b in bo]) if bo else np.nan
            rows.append(dict(d=idx[i], code=F.columns[j], touch2x=o[0], end2x=o[1], dd30=o[2], r250=o[3], base=base[i]))
    df = pd.DataFrame(rows)
    if df.empty:
        return dict(n=0), df
    by_year = {}
    for y, g in df.groupby(df.d.dt.year):
        by_year[int(y)] = dict(n=len(g), precision=float(g.touch2x.mean()), base=float(g.base.mean()),
                               lift=float(g.touch2x.mean() / g.base.mean()) if g.base.mean() > 0 else None)
    res = dict(n=len(df), names=int(df.code.nunique()), precision=float(df.touch2x.mean()), end2x=float(df.end2x.mean()),
               base=float(df.base.mean()), lift=float(df.touch2x.mean() / df.base.mean()), dd30=float(df.dd30.mean()),
               median_r250=float(df.r250.median()), mean_r250=float(df.r250.mean()), by_year=by_year)
    yrs_ok = [v["lift"] is not None and v["lift"] >= 1.2 for v in by_year.values() if v["n"] >= 15]
    res["useful"] = bool(res["n"] >= 50 and res["lift"] >= 1.5 and all(yrs_ok))
    return res, df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-store", action="store_true")
    a = ap.parse_args()
    with psycopg.connect(dsn()) as conn:
        W, ev = load(conn)
    C, RAW, V, VOL = W["ac"], W["c"], W["v"], W["vol"]
    idx, cols = C.index, C.columns
    A = C.to_numpy(float)
    v20 = V.rolling(20, min_periods=15).mean()
    elig = ((v20 >= 1e9) & (RAW >= 50)).to_numpy(bool)
    r1 = C / C.shift(1) - 1
    f1 = (C >= 1.3 * C.shift(60)) & (C >= C.rolling(250, min_periods=200).max()) & (r1 < 0.18)
    f2 = f1 & (v20 / V.rolling(250, min_periods=200).mean() >= 3)
    f3 = (C >= C.rolling(60, min_periods=60).max()) & (C > C.rolling(200, min_periods=200).mean()) & (VOL / VOL.rolling(20, min_periods=20).median() >= 1.5)
    ctl = event_mask(ev, idx, cols, lambda r: r.kind == "control_change" or any(w in r.title for w in ("pengambilalihan", "pengendali", "tender wajib"))
                     and "persidangan" not in r.title and "pkpu" not in r.title)
    rst = event_mask(ev, idx, cols, lambda r: any(w in r.title for w in ("penggabungan usaha", "merger", "peleburan", "perubahan kegiatan usaha", "transaksi material")))
    uma = event_mask(ev, idx, cols, lambda r: r.kind == "exchange_query")
    flags = {"F1_C0": (f1, None), "F2_S1": (f2, None), "F3_TREND": (f3, None), "F4_CONTROL": (ctl, "2023-07-03"),
             "F5_RESTRUCT": (rst, "2023-07-03"), "F6_UMA": (uma, "2023-07-03"),
             "F7_C0_UMA": (f1 & recent(uma, 20), "2023-07-03"), "F8_C0_EVENT": (f1 & recent(ctl | rst, 120), "2023-07-03")}
    res, lists = {}, {}
    for name, (F, frm) in flags.items():
        r, df = evaluate(F.reindex(index=idx, columns=cols).fillna(False), A, elig, idx, name, frm)
        res[name], lists[name] = r, df
        print(name, json.dumps({k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items() if k != "by_year"}), flush=True)
        print("   by year", {y: (v["n"], round(v["precision"], 2), round(v["base"], 2), round(v["lift"], 2) if v["lift"] else None) for y, v in r.get("by_year", {}).items()}, flush=True)
    five = {}
    for name, df in lists.items():
        if len(df):
            hit = df[df.code.isin(["ANTM", "BRIS", "PANI", "AMMN", "HRTA"])]
            five[name] = [f"{r.code} {r.d.date()} {'2x' if r.touch2x else ''} r250 {r.r250 * 100:+.0f}%" for r in hit.itertuples()]
    res["five_names"] = five
    print(json.dumps(five, indent=1))
    json.dump(res, open(os.path.join(HERE, "IDX_MB_RADAR_2026-09-27.json"), "w"), indent=1, default=str)
    if not a.no_store:
        from blackheart_ingest.idx import research_store as rs
        with psycopg.connect(dsn()) as conn:
            sid = rs.record_study(conn, STUDY, date.today(), params={"trials": list(flags), "n_trials_cumulative": N_BEFORE + len(flags), "horizon": H},
                                  summary={k: {kk: vv for kk, vv in v.items() if kk != "by_year"} if isinstance(v, dict) and "n" in v else v for k, v in res.items()},
                                  names=[], report_path="research/IDX_MB_RADAR_2026-09-27.md")
            print("study id", sid)


if __name__ == "__main__":
    main()
