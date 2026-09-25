#!/usr/bin/env python3
"""IDX Track B1, menu 36 - the INDEX REBALANCING effect on IDX: do names ADDED to LQ45 rise between the announcement and the
rebalance close (index funds buy them at the close before the effective date)? Deletions: the desk is long-only, so they are
only an avoid-filter or a buy-the-rebound after the effective date.

DATA (sourced 2026-09-25 by web search; idx.announcement holds one evaluation notice, so the history is hand-built from the
press: Kontan, Bisnis, CNBC Indonesia, Liputan6, Antara, IPOT news, Bareksa, Katadata - URLs in SOURCES below). 17 LQ45
evaluations with at least one change, 2020-01 -> 2026-07 (the 2025-04 evaluation changed nothing in LQ45 and is not an event).
A = the IDX announcement date as the press reports it (after the close as a rule - e.g. PTMP 2024-01-25 announced, +25 % on
the 26th); where only the article date is known (2023-07 CNBC 07-26 11:35 WIB, 2026-01 Antara 01-27 12:09 WIB) A is that date,
which can only make the entry LATER than possible (conservative). E = the effective date (first trading day of the period);
R = the rebalance close = the last trading day before E (passive funds trade at that close).
MSCI / FTSE / IDX30 / IDX80 were NOT assembled (time budget): the test is LQ45 only; that is recorded, not hidden.

PRICES: idx.bar (IDX source, adjusted = close x adj_factor), idx.daily_summary closing bid/offer, listed shares (market cap).
IDX-sourced OPENS exist only for ~7 % of name-days before 2025 (menu 29: Yahoo opens are contaminated), so the main entry is
the CLOSING OFFER of the first trading day after A (A+1 close), uniform across all 17 events; the literal next-OPEN entry is
run as a neighbour on the events where IDX opens exist.
COSTS: buy at the closing offer (or close + 1 tick; open + 1 tick for open entries), sell at the closing bid (or close - 1 tick),
Stockbit fees 0.10 % buy / 0.20 % sell, and a FLOOR of 70 bps round trip (the house range 70-91 bps): cost = max(actual, 0.70 %).
Lots of 100 are irrelevant at the per-trade return level used here (every add is liquid by construction).
CONTROLS: for every add at every event, the 5 names nearest in (log market cap, log 60-day median traded value) at A, among
names with close >= 50 that were not added or deleted in that event; same window, same cost model. EXCESS = add net - mean of
its 5 controls' net. Inference is EVENT-CLUSTERED: one number per event (mean excess of its adds), t over events.

PRE-REGISTERED (7 trials; cumulative N_BEFORE 849 + 7 = 856), written before any return was computed:
  T1 MAIN  adds: buy A+1 closing offer, sell R closing bid.
  T2 NEXT-OPEN adds: buy A+1 open + tick (events with IDX opens only), sell R close.
  T3 DELAY adds: buy A+2 closing offer (1 day late), sell R close.
  T4 EXIT-E adds: A+1 close -> E close (the effective day's close).
  T5 HOLD adds: A+1 close -> E+5 close (does the premium survive the effective date?).
  T6 DEL-AVOID deletions: A+1 close -> R close (useful as an avoid-filter if excess < 0 with t <= -2).
  T7 DEL-REBOUND deletions: buy R closing offer, sell R+10 close (bar: mean excess > 0 with t >= 2).
  Stresses on T1 (not trials): costs x1.5, per year, halves 2020-22 / 2023-26, placebo (a) random names: each add replaced by a
  random name from its 40 nearest matched non-changed names, 1000 draws; placebo (b) random dates: the same adds, the whole
  window shifted back by a random 20..250 trading days, 1000 draws. Facts (not trials): the announcement-day reaction
  (A close -> A+1 close) and the pre-announcement run-up (A-20 close -> A close), gross, vs controls.
BAR (T1): event-clustered mean excess > 0 with t >= 2.0 AND mean net per trade > 0 AND excess > 0 in >= 60 % of events.
VERDICT (robustness scorecard): T1 fails -> CLOSED. Else N = T2/T3/T4 mean excess > 0 in >= 2 of 3; P = both placebo
percentiles >= 95; T = excess > 0 in both halves. All pass -> ROBUST; one of N/T fails -> PARTIAL; P fails or two fail -> FRAGILE.
If ROBUST/PARTIAL: daily return series of the sleeve and correlation / combo effect vs gap-fade, trend, ML (idx_combo_rupiah).
READ-ONLY; one idx.study row ('index_rebalance'). INGEST_DB_DSN (or blackheart-ingest/idx-local.env).
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import date

import numpy as np
import pandas as pd
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "blackheart-ingest", "src"))
from blackheart_ingest.idx import research_store as rs  # noqa: E402

N_BEFORE = 849
STUDY = "index_rebalance"
FEE_BUY, FEE_SELL, COST_FLOOR = 0.0010, 0.0020, 0.0070
N_CTRL, N_POOL, N_PLACEBO = 5, 40, 1000
SEED = 20260925

# (announcement A, effective E, adds, deletions, source)
EVENTS = [
    ("2020-01-27", "2020-02-03", "ACES TBIG TOWR", "INDY MEDC TPIA", "cnbcindonesia.com/market/20200127170629-17-133126"),
    ("2020-07-24", "2020-08-03", "MDKA MIKA SMRA", "BRPT LPPF WSKT", "market.bisnis.com/read/20200724/7/1270916"),
    ("2021-01-26", "2021-02-01", "MEDC TPIA", "SCMA SRIL", "liputan6.com/saham/read/4466941; kontan 2021-02-01"),
    ("2021-07-26", "2021-08-02", "BRPT TINS", "BTPS CTRA", "investasi.kontan.co.id ...agustus-2021-januari-2022-1"),
    ("2022-01-25", "2022-02-02", "AMRT BFIN EMTK HRUM WSKT", "ACES AKRA BSDE JSMR PWON", "cnbcindonesia.com/market/20220126113634-17-310544"),
    ("2022-07-25", "2022-08-01", "ARTO BRIS INDY", "GGRM PTPP TKIM", "market.bisnis.com/read/20220726/7/1559173"),
    ("2023-01-25", "2023-02-01", "ACES AKRA ESSA SCMA SIDO SRTG", "BFIN ERAA HMSP MIKA MNCN WIKA", "liputan6.com/saham/read/5189966"),
    ("2023-07-26", "2023-08-01", "GGRM MAPI", "JPFA TINS", "cnbcindonesia.com/market/20230726113525-17-457412 (article date)"),
    ("2024-01-25", "2024-02-01", "MBMA MTEL PGEO PTMP", "INDY SCMA TBIG TPIA", "infobanknews.com; cnbcindonesia.com/research/20240126132147"),
    ("2024-07-25", "2024-08-01", "JSMR", "SRTG", "market.bisnis.com/read/20240725/7/1785475"),
    ("2024-10-25", "2024-11-01", "ADMR SMRA", "GGRM HRUM", "pusatdata.kontan.co.id ...1-november-2024-31-januari-2025"),
    ("2025-01-22", "2025-02-03", "CTRA JPFA MAPA", "BUKA INTP MTEL", "pusatdata.kontan.co.id ...3-februari-30-april-2025"),
    ("2025-07-25", "2025-08-01", "AADI SCMA", "ESSA SIDO", "market.bisnis.com/read/20250725/7/1896508"),
    ("2025-10-27", "2025-11-03", "BUMI DSSA EMTK HEAL NCKL", "ARTO BRIS JSMR MAPA SMRA", "indopremier.com ipotnews 477568"),
    ("2026-01-27", "2026-02-02", "BREN", "ACES", "antaranews.com/berita/5378378 (article date)"),
    ("2026-04-24", "2026-05-04", "CUAN DEWA ESSA HRTA WIFI", "BREN CTRA DSSA HEAL NCKL", "bareksa.com/berita/saham/2026-04-24"),
    ("2026-07-27", "2026-08-03", "INDY NCKL", "SMGR TOWR", "market.bisnis.com/read/20260727/7/1991498"),
]


def dsn() -> str:
    if os.environ.get("INGEST_DB_DSN"):
        return os.environ["INGEST_DB_DSN"]
    env = dict(re.findall(r"^([A-Z_]+)=(.*)$", open(os.path.join(ROOT, "blackheart-ingest", "idx-local.env")).read(), re.M))
    v = env["INGEST_DB_DSN"].strip().strip('"')
    os.environ["INGEST_DB_DSN"] = v
    return v


def tick(px):
    px = np.asarray(px, float)
    return np.where(px < 200, 1.0, np.where(px < 500, 2.0, np.where(px < 2000, 5.0, np.where(px < 5000, 10.0, 25.0))))


def load(conn):
    # opens back-filled from Yahoo (open_src='yahoo') are chart data, not IDX opening prints: keep them out
    q = """SELECT b.trade_date d, b.code, b.close::float c, b.adj_factor::float af, b.value::float v,
                  CASE WHEN b.open_missing OR b.open_src IS DISTINCT FROM 'idx' THEN NULL ELSE b.open::float END o,
                  s.bid::float bid, s.offer::float offer, s.listed_shares::float sh
           FROM idx.bar b LEFT JOIN idx.daily_summary s USING (code, trade_date)
           WHERE b.source = 'idx' AND b.trade_date >= '2019-01-01'"""
    df = pd.DataFrame(conn.execute(q).fetchall(), columns=["d", "code", "c", "af", "v", "o", "bid", "offer", "sh"])
    df["d"] = pd.to_datetime(df["d"])
    W = {k: df.pivot(index="d", columns="code", values=k).sort_index() for k in ["c", "af", "v", "o", "bid", "offer", "sh"]}
    cols = W["c"].columns
    for k in W:
        W[k] = W[k].reindex(columns=cols)
    return W


class Mkt:
    def __init__(self, W):
        self.dates = W["c"].index
        self.codes = list(W["c"].columns)
        self.ix = {c: i for i, c in enumerate(self.codes)}
        g = lambda k: W[k].to_numpy(float)  # noqa: E731
        self.C, self.AF, self.O, self.BID, self.OFF, self.SH = g("c"), g("af"), g("o"), g("bid"), g("offer"), g("sh")
        V = W["v"]
        self.V60 = V.rolling(60, min_periods=20).median().to_numpy(float)
        self.MCAP = self.C * self.SH

    def pos_after(self, d: str, k: int = 1) -> int:
        """index of the k-th trading day strictly after d (k=0: the last trading day <= d)."""
        i = int(np.searchsorted(self.dates, np.datetime64(d), side="right")) - 1
        return i + k

    def pos_on_or_after(self, d: str) -> int:
        return int(np.searchsorted(self.dates, np.datetime64(d), side="left"))

    def trade(self, j: int, t_in: int, t_out: int, entry: str = "close", mult: float = 1.0) -> float:
        """net return: buy at t_in (closing offer or open + tick), sell at t_out closing bid; cost = max(actual, floor) x mult."""
        T = len(self.dates)
        if not (0 <= t_in < T and 0 <= t_out < T) or t_out < t_in or (t_out == t_in and entry != "open"):
            return np.nan
        if entry == "open":
            ref_in = self.O[t_in, j]
            buy = ref_in + tick(ref_in) if np.isfinite(ref_in) else np.nan
        else:
            ref_in = self.C[t_in, j]
            off = self.OFF[t_in, j]
            buy = off if np.isfinite(off) and off >= ref_in else ref_in + tick(ref_in)
        ref_out = self.C[t_out, j]
        bid = self.BID[t_out, j]
        sell = bid if np.isfinite(bid) and 0 < bid <= ref_out else ref_out - tick(ref_out)
        af_in, af_out = self.AF[t_in, j], self.AF[t_out, j]
        if not all(np.isfinite([ref_in, ref_out, af_in, af_out, buy, sell])) or ref_in <= 0 or ref_out <= 0:
            return np.nan
        gross = (ref_out * af_out) / (ref_in * af_in) - 1
        cost = max((buy / ref_in - 1) + (1 - sell / ref_out) + FEE_BUY + FEE_SELL, COST_FLOOR) * mult
        return float(gross - cost)

    def gross(self, j, t0, t1):
        a, b = self.C[t0, j] * self.AF[t0, j], self.C[t1, j] * self.AF[t1, j]
        return float(b / a - 1) if np.isfinite(a) and np.isfinite(b) and a > 0 else np.nan

    def matched(self, j: int, t: int, exclude: set[int], n: int) -> list[int]:
        m, v = self.MCAP[t], self.V60[t]
        ok = np.isfinite(m) & np.isfinite(v) & (m > 0) & (v > 0) & (self.C[t] >= 50)
        ok[list(exclude)] = False
        if not (np.isfinite(m[j]) and np.isfinite(v[j]) and m[j] > 0 and v[j] > 0):
            return []
        lm, lv = np.log(np.where(ok, m, 1)), np.log(np.where(ok, v, 1))
        sm, sv = np.nanstd(lm[ok]), np.nanstd(lv[ok])
        dist = np.where(ok, ((lm - np.log(m[j])) / sm) ** 2 + ((lv - np.log(v[j])) / sv) ** 2, np.inf)
        return [int(k) for k in np.argsort(dist)[:n] if np.isfinite(dist[k])]


def build_events(M: Mkt):
    ev = []
    for A, E, adds, dels, src in EVENTS:
        tA = M.pos_after(A, 0)
        tE = M.pos_on_or_after(E)
        ev.append({"A": A, "E": E, "tA": tA, "tE": tE, "tR": tE - 1, "adds": adds.split(), "dels": dels.split(), "src": src,
                   "year": int(A[:4])})
    return ev


def run_arm(M, ev, side, t_in_f, t_out_f, entry="close", mult=1.0, fake=None, shift=0):
    """-> per-trade rows. side 'adds'|'dels'. fake: {(event_i, code): replacement j} for the names placebo."""
    rows = []
    for i, e in enumerate(ev):
        changed = {M.ix[c] for c in e["adds"] + e["dels"] if c in M.ix}
        for code in e[side]:
            if code not in M.ix:
                continue
            j0 = M.ix[code]
            ctrl = e["ctrl"].get((side, code), [])
            j = fake[(i, code)] if fake is not None else j0
            if j is None:
                continue
            t_in, t_out = t_in_f(e) - shift, t_out_f(e) - shift
            r = M.trade(j, t_in, t_out, entry, mult)
            if not np.isfinite(r):
                continue
            cr = [M.trade(k, t_in, t_out, entry, mult) for k in ctrl if k != j]
            cr = [x for x in cr if np.isfinite(x)]
            if not cr:
                continue
            rows.append({"ev": i, "A": e["A"], "year": e["year"], "code": M.codes[j], "net": r, "ctrl": float(np.mean(cr)), "ex": r - float(np.mean(cr)),
                         "days": t_out - t_in})
    return pd.DataFrame(rows)


def summarize(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"n": 0, "n_ev": 0}
    g = df.groupby("ev")["ex"].mean()
    n = len(g)
    t_ev = float(g.mean() / g.std(ddof=1) * np.sqrt(n)) if n > 1 and g.std(ddof=1) > 0 else float("nan")
    t_tr = float(df["ex"].mean() / df["ex"].std(ddof=1) * np.sqrt(len(df))) if len(df) > 1 else float("nan")
    return {"n": int(len(df)), "n_ev": int(n), "net": float(df["net"].mean()), "net_med": float(df["net"].median()), "win": float((df["net"] > 0).mean()),
            "ctrl": float(df["ctrl"].mean()), "ex": float(g.mean()), "ex_trade": float(df["ex"].mean()), "t_ev": t_ev, "t_trade": t_tr,
            "ev_pos": float((g > 0).mean()), "days": float(df["days"].mean())}


def main() -> int:
    conn = psycopg.connect(dsn())
    W = load(conn)
    M = Mkt(W)
    ev = build_events(M)
    missing = [(e["A"], c) for e in ev for c in e["adds"] + e["dels"] if c not in M.ix]
    rng = np.random.default_rng(SEED)
    for e in ev:
        changed = {M.ix[c] for c in e["adds"] + e["dels"] if c in M.ix}
        e["ctrl"], e["pool"] = {}, {}
        for side in ("adds", "dels"):
            for c in e[side]:
                if c in M.ix:
                    nn = M.matched(M.ix[c], e["tA"], changed, N_POOL)
                    e["ctrl"][(side, c)] = nn[:N_CTRL]
                    e["pool"][(side, c)] = nn
    A1 = lambda e: e["tA"] + 1  # noqa: E731
    R = lambda e: e["tR"]  # noqa: E731
    arms = {
        "T1_main": ("adds", A1, R, "close"),
        "T2_next_open": ("adds", A1, R, "open"),
        "T3_delay1": ("adds", lambda e: e["tA"] + 2, R, "close"),
        "T4_exit_E": ("adds", A1, lambda e: e["tE"], "close"),
        "T5_hold_E5": ("adds", A1, lambda e: e["tE"] + 5, "close"),
        "T6_del_avoid": ("dels", A1, R, "close"),
        "T7_del_rebound": ("dels", R, lambda e: e["tR"] + 10, "close"),
    }
    res, frames = {}, {}
    for k, (side, fi, fo, en) in arms.items():
        df = run_arm(M, ev, side, fi, fo, en)
        frames[k] = df
        res[k] = summarize(df)
    main_df = frames["T1_main"]
    stress = {"costs_x1.5": summarize(run_arm(M, ev, "adds", A1, R, "close", mult=1.5))}
    stress["by_year"] = {int(y): summarize(g) for y, g in main_df.groupby("year")}
    stress["half_2020_22"] = summarize(main_df[main_df["year"] <= 2022])
    stress["half_2023_26"] = summarize(main_df[main_df["year"] >= 2023])
    # facts
    facts = {"day0": summarize(pd.DataFrame([{"ev": i, "year": e["year"], "code": c, "net": M.gross(M.ix[c], e["tA"], e["tA"] + 1),
                                              "ctrl": np.nanmean([M.gross(k, e["tA"], e["tA"] + 1) for k in e["ctrl"][("adds", c)]]), "days": 1}
                                             for i, e in enumerate(ev) for c in e["adds"] if c in M.ix]).assign(ex=lambda d: d["net"] - d["ctrl"]).dropna()),
             "runup_20d": summarize(pd.DataFrame([{"ev": i, "year": e["year"], "code": c, "net": M.gross(M.ix[c], e["tA"] - 20, e["tA"]),
                                                   "ctrl": np.nanmean([M.gross(k, e["tA"] - 20, e["tA"]) for k in e["ctrl"][("adds", c)]]), "days": 20}
                                                  for i, e in enumerate(ev) for c in e["adds"] if c in M.ix]).assign(ex=lambda d: d["net"] - d["ctrl"]).dropna())}
    # placebo (a) random names
    real = res["T1_main"]["ex"]
    pa = []
    for _ in range(N_PLACEBO):
        fake = {}
        for i, e in enumerate(ev):
            for c in e["adds"]:
                if c in M.ix:
                    pool = [k for k in e["pool"][("adds", c)] if k not in e["ctrl"][("adds", c)]] or e["pool"][("adds", c)]
                    fake[(i, c)] = int(rng.choice(pool)) if pool else None
        d = run_arm(M, ev, "adds", A1, R, "close", fake=fake)
        pa.append(d.groupby("ev")["ex"].mean().mean() if not d.empty else np.nan)
    pa = np.array(pa, float)
    # placebo (b) random dates (same names, whole window shifted back 20..250 trading days)
    pb = []
    for _ in range(N_PLACEBO):
        rows = []
        for i, e in enumerate(ev):
            s = int(rng.integers(20, 251))
            d = run_arm(M, [e], "adds", A1, R, "close", shift=s)
            if not d.empty:
                rows.append(d["ex"].mean())
        pb.append(np.mean(rows) if rows else np.nan)
    pb = np.array(pb, float)
    plac = {"names": {"median": float(np.nanmedian(pa)), "p95": float(np.nanpercentile(pa, 95)), "pct": float((pa < real).mean() * 100)},
            "dates": {"median": float(np.nanmedian(pb)), "p95": float(np.nanpercentile(pb, 95)), "pct": float((pb < real).mean() * 100)}}
    # verdict
    m = res["T1_main"]
    bar = bool(m["ex"] > 0 and m["t_ev"] >= 2.0 and m["net"] > 0 and m["ev_pos"] >= 0.6)
    N_ok = sum(res[k].get("ex", -1) > 0 for k in ("T2_next_open", "T3_delay1", "T4_exit_E")) >= 2
    P_ok = plac["names"]["pct"] >= 95 and plac["dates"]["pct"] >= 95
    T_ok = stress["half_2020_22"].get("ex", -1) > 0 and stress["half_2023_26"].get("ex", -1) > 0
    if not bar:
        verdict = "CLOSED"
    elif N_ok and P_ok and T_ok:
        verdict = "ROBUST"
    elif P_ok and (N_ok + T_ok) == 1:
        verdict = "PARTIAL"
    else:
        verdict = "FRAGILE"
    d6, d7 = res["T6_del_avoid"], res["T7_del_rebound"]
    del_avoid = bool(d6.get("ex", 0) < 0 and d6.get("t_ev", 0) <= -2)
    del_rebound = bool(d7.get("ex", 0) > 0 and d7.get("t_ev", 0) >= 2)
    n_trials = N_BEFORE + len(arms)

    # ---- report
    f = lambda x: f"{x * 1e4:+.0f}" if isinstance(x, float) and np.isfinite(x) else "-"  # noqa: E731
    L = [f"# IDX menu 36 (Track B1) - index rebalancing effect (LQ45) - {date.today()} - 7 trials, cumulative N = {n_trials}", "",
         f"**Verdict (adds, long): {verdict}.** Deletions as avoid-filter: {'USEFUL' if del_avoid else 'not significant'}; "
         f"deletion rebound: {'PASSES' if del_rebound else 'fails'}. Pre-registered in `research/idx_index_rebalance.py`.", "",
         f"Events: {len(ev)} LQ45 evaluations 2020-01 -> 2026-07 with changes, {sum(len(e['adds']) for e in ev)} adds / "
         f"{sum(len(e['dels']) for e in ev)} deletions, sourced from the press (the table below). Codes without IDX bars: {missing or 'none'}.",
         "Costs: closing offer/bid (open + tick for T2), fees 0.10/0.20 %, floor 70 bps round trip. Excess = net - mean net of 5 names "
         "matched on market cap and 60-day traded value at A. t = event-clustered (one mean per event).", "",
         "## Arms (bps per trade; t over events)", "",
         "| arm | trades | events | net mean | net median | win | controls | excess (event mean) | t (events) | t (trades) | events > 0 | days |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for k, s in list(res.items()) + [("T1 costs x1.5", stress["costs_x1.5"]), ("fact: day-0 reaction (A close->A+1 close, gross)", facts["day0"]),
                                     ("fact: 20-day pre-announcement run-up (gross)", facts["runup_20d"])]:
        if s.get("n", 0) == 0:
            L.append(f"| {k} | 0 | - | - | - | - | - | - | - | - | - | - |")
            continue
        L.append(f"| {k} | {s['n']} | {s['n_ev']} | {f(s['net'])} | {f(s['net_med'])} | {s['win'] * 100:.0f} % | {f(s['ctrl'])} | {f(s['ex'])} | "
                 f"{s['t_ev']:.2f} | {s['t_trade']:.2f} | {s['ev_pos'] * 100:.0f} % | {s['days']:.1f} |")
    L += ["", f"BAR (T1): excess > 0, t(events) >= 2.0, net > 0, >= 60 % events positive -> **{'PASS' if bar else 'FAIL'}**. "
          f"N (T2/T3/T4 excess > 0, 2 of 3): {'pass' if N_ok else 'fail'}; P (both placebos >= 95th pct): {'pass' if P_ok else 'fail'}; "
          f"T (both halves > 0): {'pass' if T_ok else 'fail'}.", "",
          "## Placebos (T1 excess, bps)", "", "| placebo | real | median | 95th pct | real's percentile |", "|---|---|---|---|---|",
          f"| random matched non-changed names (1000) | {f(real)} | {f(plac['names']['median'])} | {f(plac['names']['p95'])} | {plac['names']['pct']:.0f} |",
          f"| same adds, window shifted back 20-250 days (1000) | {f(real)} | {f(plac['dates']['median'])} | {f(plac['dates']['p95'])} | {plac['dates']['pct']:.0f} |", "",
          "## T1 by year and half", "", "| block | trades | events | net | excess | t (events) |", "|---|---|---|---|---|---|"]
    for k, s in [(str(y), s) for y, s in stress["by_year"].items()] + [("2020-22", stress["half_2020_22"]), ("2023-26", stress["half_2023_26"])]:
        L.append(f"| {k} | {s['n']} | {s['n_ev']} | {f(s['net'])} | {f(s['ex'])} | {s['t_ev']:.2f} |" if s.get("n") else f"| {k} | 0 | | | | |")
    L += ["", "## Per event (T1 adds; T6 deletions same window; bps)", "",
          "| A (announced) | E (effective) | trading days A+1->R | adds: net / excess | dels: net / excess | source |", "|---|---|---|---|---|---|"]
    d6f = frames["T6_del_avoid"]
    for i, e in enumerate(ev):
        a = main_df[main_df["ev"] == i]
        dd = d6f[d6f["ev"] == i]
        sa = ", ".join(f"{r.code} {f(r.net)}/{f(r.ex)}" for r in a.itertuples()) or "-"
        sd = ", ".join(f"{r.code} {f(r.net)}/{f(r.ex)}" for r in dd.itertuples()) or "-"
        L.append(f"| {e['A']} | {e['E']} | {e['tR'] - e['tA'] - 1} | {sa} | {sd} | {e['src']} |")
    text = "\n".join(L)
    out = os.path.join(HERE, "IDX_INDEX_REBALANCE_2026-09-25.md")
    summary = {"verdict": verdict, "bar_pass": bar, "N": N_ok, "P": P_ok, "T": T_ok, "del_avoid": del_avoid, "del_rebound": del_rebound,
               "arms": res, "stress": stress, "facts": facts, "placebo": plac, "n_events": len(ev), "n_trials_cumulative": n_trials}
    json.dump(json.loads(json.dumps(summary, default=float)), open(os.path.join(ROOT, "research-scratch", "index_rebalance_summary.json"), "w"), indent=1)
    main_df.to_csv(os.path.join(ROOT, "research-scratch", "index_rebalance_T1.csv"), index=False)
    open(out, "w", encoding="utf-8").write(text + "\n")
    print(text)
    if "--store" in sys.argv:
        sid = rs.record_study(conn, STUDY, date.today(), params={"events": EVENTS, "trials": list(arms), "n_trials_cumulative": n_trials,
                                                                  "cost_floor": COST_FLOOR, "fees": [FEE_BUY, FEE_SELL], "n_ctrl": N_CTRL},
                              summary=json.loads(json.dumps(summary, default=float)), names=[], report_path=out)
        print(f"study #{sid} stored")
    return 0


if __name__ == "__main__":
    sys.exit(main())
