#!/usr/bin/env python3
"""IDX menu SX-1 - an algorithm for "sentiment" multibaggers (operator 2026-09-27: "cari algoritma untuk menangkap saham2
sentimen" ... "coba backtest dari 2008").

CONTEXT. Case study of ANTM, BRIS, PANI, AMMN, HRTA (same day, research-scratch/idx/daytrade2/multibagger_legs.csv): every big
leg was set off by a structural event (merger, change of control, IPO with a small float, commodity cycle), foreign flow was ~0,
most of the rise came AFTER a +30 % confirmation, and every peak was followed by a -49..-78 % fall. So the algorithm reacts
(attention + price confirmation) and exits on a trailing stop; it does not try to forecast the event.
Constraints: the ARA scope is frozen (no ARA entry rules) -> a signal day that rose >= 18 % is never an entry day; the price
breakout alone is the deployed trend sleeve -> the CONTROL below is the same rule WITHOUT the attention condition.

PART A - price/volume sentiment, 2008-01 .. 2026-09.
  Panel Y = the Yahoo .JK cache (research-scratch/idx/*.JK.csv, 450 names, SURVIVORS ONLY -> flattering before 2020; reported
  separately); panel X = idx.bar 2020-01 .. 2026-09 (989 names incl. delisted, adj_factor) as the check.
  Signal at the close of t: attention = 20-day mean traded value / 250-day mean >= K; price = close >= 1.3 x close 60 sessions
  ago AND close = 250-day high; the day's return < 18 %; 20-day mean value >= Rp 1 bn; close >= Rp 50.
  Entry at the close of t+1; exit at the close after the first close below (1 - TRAIL) x the highest close since entry, or after
  500 sessions. One position per name. Costs 0.15 % + 0.25 % fees and 0.25 % impact each side (~0.9 % round trip).
  Book: 5 % of NAV per new position, at most 20 open, strongest attention first; idle cash earns 0.
PART B - structural events from IDX announcements, 2023-07 .. 2026-09 (panel X).
  CONTROL events: title ~ pengambilalihan | pengendali | tender wajib, or kind control_change.
  RESTRUCTURE events: title ~ penggabungan usaha | merger | peleburan | perubahan kegiatan usaha | transaksi material.
  Entry: within 120 sessions after the event, the first close >= 1.2 x the close before the event that is also a 60-day high
  (day return < 18 %, 20-day value >= Rp 1 bn); exit trailing 25 %. One event per name per 120 sessions.

REV.2 (2026-09-27, after the first run and BEFORE any verdict was reported; applied to every arm alike): no entry fill on a
day that closes up >= 18 % (upper band - the entry slides to the next day, up to 5), no sale on a day that closes down >= 6.5 %
(lower band - the sale slides, up to 10); placebo for E1/E2 = the same codes with random event dates (40 draws) - reported, and
E1/E2 need placebo pct >= 90 on the book Sharpe. The first run (no lock realism) printed C0 IDX 2020-26 61 %/2.27, E1 2.49, E2 2.27.

PRE-REGISTERED (6 trials; cumulative 1067 + 6 = 1073).
  S1  K = 3, TRAIL 25 %         S2  K = 5, TRAIL 25 %         S3  K = 3, TRAIL 35 %
  S5  IPO momentum (panel X only, listed on/after 2020-02): 5..250 sessions after listing, close >= 1.3 x the first close and
      at its high since listing, same filters, TRAIL 25 %
  E1  CONTROL events + confirmation      E2  RESTRUCTURE events + confirmation
  Control (not a trial): C0 = S1 without the attention condition (plain momentum breakout, same exit).
READING RULE - a trial is a CANDIDATE only if ALL, on each panel it is run on:
  >= 100 trades (E1/E2: >= 30); mean net per trade > 0 with t >= 2; mean still > 0 without its 5 best trades; the book's
  Sharpe >= 0.8 and above C0's on the same panel and window; book positive in >= 60 % of calendar years; book mDD <= 35 %.
  Part A must pass on BOTH Y 2008-2019 and X 2020-2026. READ-ONLY on the DB except one idx.study row (--no-store to skip).
"""
from __future__ import annotations

import argparse
import glob
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
YAHOO = os.path.join(ROOT, "research-scratch", "idx")
STUDY, N_BEFORE = "sentiment_sx1", 1067
TRIALS = ["S1", "S2", "S3", "S5", "E1", "E2"]
FB, FS, IMP = 0.0015, 0.0025, 0.0025
SLOT, MAX_OPEN, MAX_HOLD, DAYCAP, MIN_V, MIN_PX = 0.05, 20, 500, 0.18, 1e9, 50
LOCKDN = -0.065
RNG = np.random.default_rng(20260927)


def dsn() -> str:
    return os.environ.get("INGEST_DB_DSN") or [ln.split("=", 1)[1].strip() for ln in open(os.path.join(ROOT, "blackheart-ingest", "idx-local.env"))
                                                if ln.startswith("INGEST_DB_DSN=")][0]


# ---- panels -----------------------------------------------------------------------------------------------------------

def panel_yahoo():
    jk = pd.read_csv(os.path.join(YAHOO, "_JKSE.csv"), parse_dates=["date"]).set_index("date")["close"].astype(float).sort_index()
    jk = jk[~jk.index.duplicated(keep="last")]
    jk = jk[jk.index >= "2007-01-01"]
    C, V = {}, {}
    for f in sorted(glob.glob(os.path.join(YAHOO, "*.JK.csv"))):
        code = os.path.basename(f).split(".")[0]
        df = pd.read_csv(f, parse_dates=["date"]).set_index("date").sort_index()
        df = df[~df.index.duplicated(keep="last")]
        c = pd.to_numeric(df["close"], errors="coerce")
        v = pd.to_numeric(df["volume"], errors="coerce")
        ok = (c > 0) & c.notna()
        C[code], V[code] = c[ok], (c * v)[ok]
    C = pd.DataFrame(C).reindex(jk.index)
    V = pd.DataFrame(V).reindex(jk.index)
    return C, V, jk


def panel_idx(conn):
    df = pd.DataFrame(conn.execute("""SELECT code, trade_date, close * coalesce(adj_factor, 1), close, value FROM idx.bar
                                      WHERE source = 'idx' AND close > 0""").fetchall(), columns=["code", "d", "ac", "c", "v"])
    for k in ("ac", "c", "v"):
        df[k] = df[k].astype(float)
    df["d"] = pd.to_datetime(df.d)
    C = df.pivot(index="d", columns="code", values="ac").sort_index()
    RAW = df.pivot(index="d", columns="code", values="c").sort_index()
    V = df.pivot(index="d", columns="code", values="v").sort_index()
    ix = pd.DataFrame(conn.execute("SELECT trade_date, close FROM idx.index_daily WHERE index_code = 'COMPOSITE'").fetchall(), columns=["d", "c"])
    ix["d"] = pd.to_datetime(ix.d)
    jk = ix.set_index("d").c.astype(float).sort_index().reindex(C.index).ffill()
    return C, V, RAW, jk


# ---- signals ----------------------------------------------------------------------------------------------------------

def base_filters(C, V, RAW=None):
    px = RAW if RAW is not None else C
    ret1 = C / C.shift(1) - 1
    v20 = V.rolling(20, min_periods=15).mean()
    return (ret1 < DAYCAP) & (v20 >= MIN_V) & (px >= MIN_PX), v20


def sig_attention(C, V, K, RAW=None, attention=True):
    ok, v20 = base_filters(C, V, RAW)
    v250 = V.rolling(250, min_periods=200).mean()
    hi = C.rolling(250, min_periods=200).max()
    s = ok & (C >= 1.3 * C.shift(60)) & (C >= hi)
    if attention:
        s &= (v20 / v250 >= K)
    return s, (v20 / v250)


def sig_ipo(C, V, RAW, first_ok):
    ok, v20 = base_filters(C, V, RAW)
    age = C.notna().cumsum()
    first = C.apply(lambda s: s.dropna().iloc[0] if s.notna().any() else np.nan)
    s = ok & (age >= 5) & (age <= 250) & (C >= 1.3 * first) & (C >= C.cummax())
    s = s.loc[:, [c for c in s.columns if c in first_ok]]
    return s, v20


def sig_event(C, V, RAW, events):
    """events: {code: [dates]} -> first confirmation within 120 sessions."""
    ok, v20 = base_filters(C, V, RAW)
    hi60 = C.rolling(60, min_periods=40).max()
    S = pd.DataFrame(False, index=C.index, columns=C.columns)
    idx = C.index
    n_ev = 0
    for code, ds in events.items():
        if code not in C.columns:
            continue
        last = None
        for d in sorted(ds):
            i = idx.searchsorted(pd.Timestamp(d))
            if i < 1 or i >= len(idx) or (last is not None and i - last < 120):
                continue
            last, n_ev = i, n_ev + 1
            ref = C[code].iloc[:i].dropna()
            if ref.empty:
                continue
            ref = ref.iloc[-1]
            w = slice(i, min(i + 120, len(idx)))
            cond = (C[code].iloc[w] >= 1.2 * ref) & (C[code].iloc[w] >= hi60[code].iloc[w]) & ok[code].iloc[w]
            hit = cond[cond].index
            if len(hit):
                S.loc[hit[0], code] = True
    return S, v20, n_ev


# ---- trades and book ----------------------------------------------------------------------------------------------------

def trades_from(S, C, strength, trail, start, end):
    idx = C.index
    lo, hi = idx.searchsorted(pd.Timestamp(start)), idx.searchsorted(pd.Timestamp(end), side="right")
    out = []
    for code in S.columns:
        sc = S[code].to_numpy()
        c = C[code].to_numpy(float)
        i = lo
        while i < hi - 1:
            if not sc[i]:
                i += 1
                continue
            e = i + 1
            while e < min(i + 6, len(c) - 1) and (not np.isfinite(c[e]) or (np.isfinite(c[e - 1]) and c[e] / c[e - 1] - 1 >= DAYCAP)):
                e += 1                                                   # rev.2: no fill on a day that closes up >= 18 % (upper band)
            if not np.isfinite(c[e]) or (e > i + 1 and c[e] / c[e - 1] - 1 >= DAYCAP):
                i += 1
                continue
            peak, x = c[e], None
            for k in range(e + 1, min(e + MAX_HOLD, len(c) - 1) + 1):
                if not np.isfinite(c[k]):
                    continue
                peak = max(peak, c[k])
                if c[k] < (1 - trail) * peak:
                    x = k + 1
                    while x < len(c) - 1 and (not np.isfinite(c[x]) or (x < k + 11 and np.isfinite(c[x - 1]) and c[x] / c[x - 1] - 1 <= LOCKDN)):
                        x += 1                                           # rev.2: no sale on a day that closes down >= 6.5 % (lower band)
                    break
            if x is None:
                x = min(e + MAX_HOLD, len(c) - 1)
                while x > e and not np.isfinite(c[x]):
                    x -= 1
            if x >= hi:                                                   # still open at the window's end: mark at the last close
                x = hi - 1
                while x > e and not np.isfinite(c[x]):
                    x -= 1
            buy, sell = c[e] * (1 + FB + IMP), c[x] * (1 - FS - IMP)
            st = strength[code].iloc[i] if strength is not None else 0.0
            out.append(dict(code=code, sig=idx[i], e=e, x=x, entry=idx[e], exit=idx[x], ret=sell / buy - 1, gross=c[x] / c[e] - 1,
                            hold=x - e, strength=float(st) if np.isfinite(st) else 0.0))
            i = x + 1
    return out


def book(trades, C, start, end):
    idx = C.index
    lo, hi = idx.searchsorted(pd.Timestamp(start)), idx.searchsorted(pd.Timestamp(end), side="right")
    by_entry = {}
    for t in trades:
        by_entry.setdefault(t["e"], []).append(t)
    nav, cash, pos, navs, taken = 1.0, 1.0, {}, [], 0
    Cv = C.to_numpy(float)
    col = {c: j for j, c in enumerate(C.columns)}
    last_px = {}
    for i in range(lo, hi):
        # exits
        for key in [k for k, p in pos.items() if p["x"] == i]:
            p = pos.pop(key)
            px = Cv[i, col[p["code"]]]
            px = px if np.isfinite(px) else last_px.get(p["code"], p["px"])
            cash += p["sh"] * px * (1 - FS - IMP)
        # mark
        val = 0.0
        for p in pos.values():
            px = Cv[i, col[p["code"]]]
            if np.isfinite(px):
                last_px[p["code"]] = px
            val += p["sh"] * last_px.get(p["code"], p["px"])
        nav = cash + val
        # entries
        for t in sorted(by_entry.get(i, []), key=lambda t: -t["strength"]):
            if len(pos) >= MAX_OPEN or t["code"] in {p["code"] for p in pos.values()}:
                continue
            amt = min(SLOT * nav, cash)
            px = Cv[i, col[t["code"]]]
            if amt <= 0 or not np.isfinite(px):
                continue
            sh = amt / (px * (1 + FB + IMP))
            cash -= amt
            pos[(t["code"], i)] = dict(code=t["code"], sh=sh, px=px, x=t["x"])
            last_px[t["code"]] = px
            taken += 1
        navs.append(nav)
    s = pd.Series(navs, index=idx[lo:hi])
    r = s.pct_change().fillna(0)
    yrs = len(s) / 244
    by_year = s.groupby(s.index.year).apply(lambda x: x.iloc[-1] / x.iloc[0] - 1)
    return dict(cagr=float(s.iloc[-1] ** (1 / yrs) - 1), sharpe=float(r.mean() / r.std() * np.sqrt(244)) if r.std() > 0 else 0.0,
                mdd=float((s / s.cummax() - 1).min()), years_pos=float((by_year > 0).mean()), taken=taken,
                by_year={int(k): round(float(v) * 100, 1) for k, v in by_year.items()})


def trade_stats(trades):
    if not trades:
        return dict(n=0)
    r = np.array([t["ret"] for t in trades])
    srt = np.sort(r)
    no5 = srt[:-5].mean() if len(r) > 5 else np.nan
    top = sorted(trades, key=lambda t: -t["ret"])[:5]
    return dict(n=len(r), mean=float(r.mean()), median=float(np.median(r)), hit=float((r > 0).mean()),
                t=float(r.mean() / r.std(ddof=1) * np.sqrt(len(r))) if len(r) > 2 else np.nan, mean_ex_top5=float(no5),
                hold=float(np.median([t["hold"] for t in trades])), p_loss_gt30=float((r < -0.3).mean()),
                top5=[f"{t['code']} {t['entry'].date()} {t['ret'] * 100:+.0f}%" for t in top])


def bench(jk, start, end):
    s = jk[(jk.index >= pd.Timestamp(start)) & (jk.index <= pd.Timestamp(end))].dropna()
    r = s.pct_change().fillna(0)
    return dict(cagr=float((s.iloc[-1] / s.iloc[0]) ** (244 / len(s)) - 1), sharpe=float(r.mean() / r.std() * np.sqrt(244)),
                mdd=float((s / s.cummax() - 1).min()))


def verdict(ts, bk, c0bk, min_n):
    checks = dict(n=ts.get("n", 0) >= min_n, mean_t=ts.get("n", 0) > 2 and ts["mean"] > 0 and ts["t"] >= 2,
                  ex_top5=ts.get("n", 0) > 5 and ts["mean_ex_top5"] > 0, sharpe=bk["sharpe"] >= 0.8,
                  beats_c0=c0bk is None or bk["sharpe"] > c0bk["sharpe"], years=bk["years_pos"] >= 0.6, mdd=bk["mdd"] >= -0.35)
    return checks, all(checks.values())


def events_from_db(conn):
    rows = conn.execute("""SELECT code, published_at::date, kind, title FROM idx.announcement WHERE code IS NOT NULL AND (
            kind = 'control_change' OR title ~* '(pengambilalihan|pengendali|tender wajib|penggabungan usaha|merger|peleburan|perubahan kegiatan usaha|transaksi material)')""").fetchall()
    ctl, rst = {}, {}
    for code, d, kind, title in rows:
        t = (title or "").lower()
        if "persidangan" in t or "pkpu" in t:                           # court cases about a controller are not a change of control
            continue
        if kind == "control_change" or any(w in t for w in ("pengambilalihan", "pengendali", "tender wajib")):
            ctl.setdefault(code, []).append(d)
        if any(w in t for w in ("penggabungan usaha", "merger", "peleburan", "perubahan kegiatan usaha", "transaksi material")):
            rst.setdefault(code, []).append(d)
    return ctl, rst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-store", action="store_true")
    a = ap.parse_args()
    res = {}
    CY, VY, jkY = panel_yahoo()
    with psycopg.connect(dsn()) as conn:
        CX, VX, RX, jkX = panel_idx(conn)
        ctl, rst = events_from_db(conn)
    windows = {"Y 2008-2019": (CY, VY, None, jkY, "2008-01-01", "2019-12-31"),
               "X 2020-2026": (CX, VX, RX, jkX, "2020-01-02", "2026-09-25"),
               "Y 2020-2026 (survivors)": (CY, VY, None, jkY, "2020-01-02", "2026-09-25")}
    arms = {"C0": dict(K=None, trail=0.25), "S1": dict(K=3, trail=0.25), "S2": dict(K=5, trail=0.25), "S3": dict(K=3, trail=0.35)}
    for wname, (C, V, RAW, jk, s0, s1) in windows.items():
        res[wname] = {"benchmark_ihsg": bench(jk, s0, s1)}
        for arm, p in arms.items():
            S, strength = sig_attention(C, V, p["K"] or 0, RAW, attention=p["K"] is not None)
            tr = trades_from(S, C, strength, p["trail"], s0, s1)
            res[wname][arm] = dict(trades=trade_stats(tr), book=book(tr, C, s0, s1))
            print(wname, arm, json.dumps({k: res[wname][arm]["trades"].get(k) for k in ("n", "mean", "t", "mean_ex_top5")}, default=str),
                  json.dumps({k: res[wname][arm]["book"][k] for k in ("cagr", "sharpe", "mdd")}), flush=True)
    # S5 IPO (panel X, listed after 2020-01-31)
    firsts = CX.apply(lambda s: s.first_valid_index())
    ipo = {c for c, d in firsts.items() if d is not None and d > pd.Timestamp("2020-01-31")}
    S, strength = sig_ipo(CX, VX, RX, ipo)
    tr = trades_from(S, CX, strength, 0.25, "2020-01-02", "2026-09-25")
    res["X 2020-2026"]["S5"] = dict(trades=trade_stats(tr), book=book(tr, CX, "2020-01-02", "2026-09-25"), n_ipo_names=len(ipo))
    print("S5", res["X 2020-2026"]["S5"]["trades"].get("n"), res["X 2020-2026"]["S5"]["book"]["sharpe"], flush=True)
    # Part B events (panel X, 2023-07 onward); C0 on the same window as the reference
    res["X 2023-07-2026"] = {"benchmark_ihsg": bench(jkX, "2023-07-03", "2026-09-25")}
    S, strength = sig_attention(CX, VX, 0, RX, attention=False)
    tr = trades_from(S, CX, strength, 0.25, "2023-07-03", "2026-09-25")
    res["X 2023-07-2026"]["C0"] = dict(trades=trade_stats(tr), book=book(tr, CX, "2023-07-03", "2026-09-25"))
    for arm, ev in (("E1", ctl), ("E2", rst)):
        S, v20, n_ev = sig_event(CX, VX, RX, ev)
        tr = trades_from(S, CX, v20, 0.25, "2023-07-03", "2026-09-25")
        res["X 2023-07-2026"][arm] = dict(trades=trade_stats(tr), book=book(tr, CX, "2023-07-03", "2026-09-25"), events=n_ev)
        print(arm, n_ev, res["X 2023-07-2026"][arm]["trades"].get("n"), res["X 2023-07-2026"][arm]["book"]["sharpe"], flush=True)
    # rev.2 placebo for E1/E2: the same codes, the same number of events, dates drawn at random inside the window
    days = CX.index[(CX.index >= "2023-07-03") & (CX.index <= "2026-06-30")]
    for arm, ev in (("E1", ctl), ("E2", rst)):
        pm, ps = [], []
        for _ in range(40):
            fake = {c: list(RNG.choice(days, size=len(ds))) for c, ds in ev.items()}
            S, v20, _n = sig_event(CX, VX, RX, fake)
            tr = trades_from(S, CX, v20, 0.25, "2023-07-03", "2026-09-25")
            if tr:
                pm.append(np.mean([t["ret"] for t in tr]))
                ps.append(book(tr, CX, "2023-07-03", "2026-09-25")["sharpe"])
        real = res["X 2023-07-2026"][arm]
        res["X 2023-07-2026"][arm]["placebo"] = dict(mean=float(np.mean(pm)), sharpe=float(np.mean(ps)),
                                                    pct_mean=float((np.array(pm) < real["trades"]["mean"]).mean() * 100),
                                                    pct_sharpe=float((np.array(ps) < real["book"]["sharpe"]).mean() * 100))
        print(arm, "placebo", res["X 2023-07-2026"][arm]["placebo"], flush=True)
    # verdicts
    out_v = {}
    for arm in ("S1", "S2", "S3"):
        vs = {w: verdict(res[w][arm]["trades"], res[w][arm]["book"], res[w]["C0"]["book"], 100) for w in ("Y 2008-2019", "X 2020-2026")}
        out_v[arm] = dict(checks={w: v[0] for w, v in vs.items()}, candidate=all(v[1] for v in vs.values()))
    v = verdict(res["X 2020-2026"]["S5"]["trades"], res["X 2020-2026"]["S5"]["book"], res["X 2020-2026"]["C0"]["book"], 100)
    out_v["S5"] = dict(checks=v[0], candidate=v[1])
    for arm in ("E1", "E2"):
        v = verdict(res["X 2023-07-2026"][arm]["trades"], res["X 2023-07-2026"][arm]["book"], res["X 2023-07-2026"]["C0"]["book"], 30)
        pl = res["X 2023-07-2026"][arm]["placebo"]["pct_sharpe"] >= 90
        out_v[arm] = dict(checks={**v[0], "placebo": pl}, candidate=v[1] and pl)
    res["verdicts"] = out_v
    print(json.dumps(out_v, indent=1, default=str))
    json.dump(res, open(os.path.join(HERE, "IDX_SENTIMENT_2026-09-27.json"), "w"), indent=1, default=str)
    if not a.no_store:
        from blackheart_ingest.idx import research_store as rs
        with psycopg.connect(dsn()) as conn:
            sid = rs.record_study(conn, STUDY, date.today(), params={"trials": TRIALS, "n_trials_cumulative": N_BEFORE + len(TRIALS)},
                                  summary={"verdicts": out_v}, names=[], report_path="research/IDX_SENTIMENT_2026-09-27.md")
            print("study id", sid)


if __name__ == "__main__":
    main()
