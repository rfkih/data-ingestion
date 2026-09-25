#!/usr/bin/env python3
"""IDX menu 39 (Track B4) - CORPORATE-ACTION events, long-only: splits, rights (HMETD), buybacks, tender offers, reverse splits.

Question: does a corporate-action disclosure (split plan, buyback plan, tender offer / change of control) carry a
tradeable long drift after IDX costs, and does a rights issue (HMETD) carry a negative drift worth using as an AVOID
filter on the existing books?

DATA (read-only): idx.announcement (2023-07-03 ->, published_at = the point-in-time signal), idx.corporate_action (ex-dates
2020 ->, from IDX 'Previous' resets; kinds split / rights_or_bonus / reverse_split), idx.bar (close x adj_factor = the
split + rights adjusted series; adj_factor is rewritten backwards at every reset, raw prices never change, so a return
across an ex-date is a clean total-price return excluding cash dividends), idx.daily_summary (closing bid / offer).
KNOWN DATA DEFECT (found while building this menu, 2026-09-25): 441 'rights_or_bonus' rows dated 2026-09-21 are artefacts
of the 09-18 Cloudflare backfill (the reset compared 09-21 'Previous' with the 09-17 close, not 09-18) - excluded here.

EVENT DEFINITIONS (fixed before any return was computed):
  entry session e = the first session whose OPEN is after the publication (published_at in WIB; before 09:00 -> that day,
    otherwise the next session). Opens before 2025 exist only for LQ45, so the fill is the CLOSE of e at the closing offer
    (+ tick when the quote is missing/crossed) + 0.10 % fee; exit at the closing bid - 0.20 % fee (research/idx_swing2
    costs, the desk's convention; round trip ~70-130 bps). Signal day t = e - 1. Returns on close x adj_factor.
  Deduplication: the first matching disclosure per code in a 180-day window (buyback: 90 days).
  split_ann   title ~ 'stock split|pemecahan' and not 'reverse|penggabungan nilai'           (announcement, 2023-07 ->)
  split_ex    corporate_action kind split, factor < 0.9, entry = the ex-date session           (ex-date, 2020 ->)
  rights_ann  title ~ 'HMETD|hak memesan efek terlebih dahulu|rights issue|PMHMETD' and not 'tanpa|PMTHMETD|non-HMETD'
  rights_ex   corporate_action rights_or_bonus, factor <= 0.97, ex_date <> 2026-09-21, entry = the ex-date session
  buyback_ann title ~ 'pembelian kembali saham|pembelian saham kembali|buy ?back' and not
              'pengalihan|hasil|laporan|utang|sukuk|obligasi|penghentian|perkembangan|realisasi|treasuri'
  tender_ann  title ~ 'penawaran tender|tender offer' and not 'utang|obligasi|sukuk|notes|surat' OR kind control_change with
              title ~ 'pengendali|pengambilalihan|akuisisi' and not 'persidangan|perkara|pkpu|wanprestasi|tidak menyebabkan'
  reverse     4 corporate_action rows 2020-24 -> UNTESTABLE by construction, no trial spent.
  Universe at t: main-board-agnostic, v60 (60-session mean traded value, missing days = 0) >= Rp 5 bn and close >= Rp 100
  (the desk's LIQ floor). Matched controls: the 5 LIQ names at t with the nearest log v60 and a bar at e and at the exit,
  excluding names with an event of the same family within 60 sessions. Market-adjusted = event gross minus the LIQ
  equal-weight index over the same window.

PRE-REGISTERED (7 trials; cumulative 883 + 7 = 890):
  T1 split_ann_20    long, hold 20 sessions
  T2 split_ann_toex  long, exit at the ex-date close (120 sessions max)
  T3 split_ex_20     long, bought at the ex-date close, hold 20
  T4 buyback_ann_20  long, hold 20
  T5 tender_ann_20   long, hold 20
  T6 rights_ann_20   AVOID filter candidate (20 sessions)
  T7 rights_ex_20    AVOID filter candidate (20 sessions after the ex-date)
BAR - long arm (T1-T5), all on the LIQ universe:
  n >= 30 events, else UNTESTABLE (reported, verdict none).
  PRIMARY (else CLOSED): mean NET return > 0 with t >= 2.5 AND mean matched excess > 0 with t >= 2.0.
  Battery: P placebo - mean market-adjusted return above the 95th pct of 500 same-code random-date draws (same holding);
    T years - net mean > 0 in >= 2/3 of the calendar years with >= 5 events; N neighbours - H 10 and H 40 (T2: H 20/40
    fixed) and the Rp 1 bn floor keep net mean > 0; C costs x 1.5 net > 0; D 1-session delay net > 0; M DSR on the sleeve's
    daily series at N = 890 reported (not a gate).
  ROBUST = primary + P + T + N pass (C, D reported); PARTIAL = one of P/T/N fails; FRAGILE = P fails, or two fail.
BAR - avoid filter (T6, T7): mean matched excess <= -2 % with t <= -2.0, placebo below the 5th pct, negative in >= 2/3 of
  years; if met, the filter "no trend / ML entry in a name inside [announcement or ex-date, +20 sessions]" is replayed on the
  combined Rp 20 M book (idx_combo_rupiah engine) and reported (CAGR / Sharpe / mDD), not deployed.
IF a long arm passes: its sleeve's daily series (5 % of NAV per event, costs in), correlation with the gap / trend / ML
  sleeves of idx_combo_rupiah and the combined book with it added.
Not trials (diagnostics): event counts per type at every floor, pre-event run-up, the 2025+ open-entry version, H profile.
READ-ONLY; one idx.study row ('corp_actions'). INGEST_DB_DSN (or blackheart-ingest/idx-local.env).
"""
from __future__ import annotations

import math
import os
import re
import sys
from datetime import date
from statistics import NormalDist

import numpy as np
import pandas as pd
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blackheart-ingest", "src"))
from blackheart_ingest.idx import research_store as rs  # noqa: E402
from blackheart_ingest.idx.ml import common  # noqa: E402

N_BEFORE = 883
STUDY = "corp_actions"
TRIALS = ["split_ann_20", "split_ann_toex", "split_ex_20", "buyback_ann_20", "tender_ann_20", "rights_ann_20", "rights_ex_20"]
N_AFTER = N_BEFORE + len(TRIALS)
FEE_BUY, FEE_SELL = 0.0010, 0.0020
LIQ_V, LIQ_V_LO, MIN_PX = 5e9, 1e9, 100.0
N_PLACEBO, N_CTRL, SEED = 500, 5, 39
START = "2019-09-01"
rng = np.random.default_rng(SEED)


def dsn() -> str:
    if os.environ.get("INGEST_DB_DSN"):
        return os.environ["INGEST_DB_DSN"]
    env = dict(re.findall(r"^([A-Z_]+)=(.*)$", open(os.path.join(ROOT, "blackheart-ingest", "idx-local.env")).read(), re.M))
    return env["INGEST_DB_DSN"].strip().strip('"')


def log(m: str) -> None:
    print(m, flush=True)


# ---- data -----------------------------------------------------------------------------------------------------------------------
def load(conn):
    b = pd.read_sql(f"""select code, trade_date d, source, close, adj_factor, value from idx.bar
                        where trade_date >= '{START}' and source in ('idx','yahoo') and close > 0""", conn)
    b = b.sort_values("source").drop_duplicates(["code", "d"], keep="first")          # 'idx' before 'yahoo'
    q = pd.read_sql(f"select code, trade_date d, bid, offer from idx.daily_summary where trade_date >= '{START}'", conn)
    b = b.merge(q, on=["code", "d"], how="left")
    b["d"] = pd.to_datetime(b["d"])
    cnt = b.groupby("d").size()
    dates = cnt.index[cnt >= 200].sort_values()
    W = lambda c: b.pivot(index="d", columns="code", values=c).reindex(dates).astype(float)  # noqa: E731
    close, adj, val, bid, off = W("close"), W("adj_factor"), W("value"), W("bid"), W("offer")
    A = (close * adj)
    v60 = val.fillna(0).rolling(60, min_periods=40).mean()
    C = close.to_numpy()
    tk = np.vectorize(common.tick)(np.nan_to_num(C, nan=1.0))
    o, bd = np.nan_to_num(off.to_numpy()), np.nan_to_num(bid.to_numpy())
    c_in = np.where((o > 0) & (o >= C), o / C - 1, tk / C) + FEE_BUY
    c_out = np.where((bd > 0) & (bd <= C), 1 - bd / C, tk / C) + FEE_SELL
    c_in = np.minimum(np.nan_to_num(c_in, nan=0.05), 0.10)
    c_out = np.minimum(np.nan_to_num(c_out, nan=0.05), 0.10)
    return dict(dates=dates, codes=close.columns, A=A.to_numpy(), Af=A.ffill(limit=60).to_numpy(), raw=C, v60=v60.to_numpy(),
                c_in=c_in, c_out=c_out)


def entry_session(dates: pd.DatetimeIndex, pub_wib: pd.Timestamp) -> int:
    d0 = pub_wib.normalize()
    i = int(dates.searchsorted(d0))                                   # first session >= pub date
    if i < len(dates) and dates[i] == d0 and pub_wib.hour < 9:
        return i
    return int(dates.searchsorted(d0, side="right"))


def ann_events(conn, D, fam: str, days: int) -> pd.DataFrame:
    pats = {
        "split_ann": ("title ~* '(stock split|pemecahan)' and title !~* '(reverse|penggabungan nilai)'", None),
        "rights_ann": ("title ~* '(HMETD|hak memesan efek terlebih dahulu|rights issue|PMHMETD)' and title !~* '(tanpa|PMTHMETD|non-HMETD|non HMETD)'", None),
        "buyback_ann": ("title ~* '(pembelian kembali saham|pembelian saham kembali|buy ?back)' and title !~* "
                        "'(pengalihan|hasil|laporan|utang|sukuk|obligasi|penghentian|perkembangan|realisasi|treasuri)'", None),
        "tender_ann": ("(title ~* '(penawaran tender|tender offer)' and title !~* '(utang|obligasi|sukuk|notes|surat)') or "
                       "(kind = 'control_change' and title ~* '(pengendali|pengambilalihan|akuisisi)' and title !~* "
                       "'(persidangan|perkara|pkpu|wanprestasi|tidak menyebabkan)')", None),
    }
    where, _ = pats[fam]
    a = pd.read_sql(f"select code, published_at, title from idx.announcement where code is not null and ({where}) order by code, published_at", conn)
    a["pub"] = pd.to_datetime(a["published_at"], utc=True).dt.tz_convert("Asia/Jakarta").dt.tz_localize(None)
    keep, last = [], {}
    for r in a.itertuples():
        if r.code in last and (r.pub - last[r.code]).days < days:
            continue
        last[r.code] = r.pub
        keep.append(r)
    ev = pd.DataFrame(keep)
    if ev.empty:
        return ev
    ev["e"] = [entry_session(D["dates"], p) for p in ev["pub"]]
    return ev[["code", "pub", "title", "e"]]


def ca_events(conn, D, kind: str) -> pd.DataFrame:
    cond = {"split_ex": "kind='split' and factor < 0.9", "rights_ex": "kind='rights_or_bonus' and factor <= 0.97 and ex_date <> '2026-09-21'",
            "reverse": "kind='reverse_split'"}[kind]
    c = pd.read_sql(f"select code, ex_date, factor from idx.corporate_action where {cond} order by ex_date", conn)
    c["pub"] = pd.to_datetime(c["ex_date"])
    c["e"] = [int(D["dates"].searchsorted(p)) for p in c["pub"]]
    c["title"] = c["factor"].map(lambda f: f"factor {float(f):.3f}")
    return c[["code", "pub", "title", "e"]]


# ---- evaluation --------------------------------------------------------------------------------------------------------------------
def index_series(D, floor):
    A = D["A"]
    r = np.full_like(A, np.nan)
    r[1:] = A[1:] / A[:-1] - 1
    liq_prev = np.zeros_like(A, dtype=bool)
    liq_prev[1:] = (D["v60"][:-1] >= floor) & (D["raw"][:-1] >= MIN_PX)
    r = np.where(liq_prev & np.isfinite(r) & (np.abs(r) < 0.5), r, np.nan)
    m = np.nan_to_num(np.nanmean(np.where(np.isfinite(r), r, np.nan), axis=1))
    return np.cumprod(1 + m)


def prep(ev: pd.DataFrame, D, floor: float, H: int | None, exit_col: str | None = None, delay: int = 0) -> pd.DataFrame:
    """Attach column index, exit session, liquidity at t. H None -> exit column given per event."""
    cidx = {c: i for i, c in enumerate(D["codes"])}
    T = len(D["dates"])
    rows = []
    for r in ev.itertuples():
        j = cidx.get(r.code)
        e = r.e + delay
        if j is None or e < 61 or e >= T - 1:
            continue
        t = e - 1
        if not (D["v60"][t, j] >= floor and D["raw"][t, j] >= MIN_PX) or not np.isfinite(D["A"][e, j]):
            continue
        x = e + H if H is not None else min(getattr(r, exit_col) + delay if getattr(r, exit_col) + delay > e else e + 1, e + 120)
        if x >= T:
            continue                                                  # immature
        rows.append({"code": r.code, "pub": r.pub, "j": j, "t": t, "e": e, "x": x})
    return pd.DataFrame(rows)


def returns(P: pd.DataFrame, D, I, cost_mult=1.0) -> pd.DataFrame:
    if P.empty:
        return P
    A, Af = D["A"], D["Af"]
    j, e, x = P["j"].to_numpy(), P["e"].to_numpy(), P["x"].to_numpy()
    ax = np.where(np.isfinite(A[x, j]), A[x, j], Af[x, j])
    g = ax / A[e, j] - 1
    net = (1 + g) * (1 - cost_mult * D["c_out"][x, j]) / (1 + cost_mult * D["c_in"][e, j]) - 1
    P = P.copy()
    P["gross"], P["net"], P["mkt"] = g, net, g - (I[x] / I[e] - 1)
    return P


def matched_excess(P: pd.DataFrame, D, floor, excl: dict[str, list[int]]) -> np.ndarray:
    A, Af, v60, raw = D["A"], D["Af"], D["v60"], D["raw"]
    codes = D["codes"]
    out = []
    for r in P.itertuples():
        ok = (v60[r.t] >= floor) & (raw[r.t] >= MIN_PX) & np.isfinite(A[r.e]) & (np.isfinite(A[r.x]) | np.isfinite(Af[r.x]))
        ok[r.j] = False
        bad = [k for k, es in excl.items() if any(abs(q - r.e) <= 60 for q in es)]
        if bad:
            ok[np.isin(codes, bad)] = False
        cand = np.flatnonzero(ok)
        if len(cand) < N_CTRL:
            out.append(np.nan)
            continue
        dist = np.abs(np.log(v60[r.t, cand] + 1) - math.log(v60[r.t, r.j] + 1))
        pick = cand[np.argsort(dist)[:N_CTRL]]
        ax = np.where(np.isfinite(A[r.x, pick]), A[r.x, pick], Af[r.x, pick])
        out.append(r.gross - np.nanmean(ax / A[r.e, pick] - 1))
    return np.array(out)


def placebo(P: pd.DataFrame, D, I, floor) -> np.ndarray:
    """500 draws: every event re-dated to a random LIQ session of the same code, same holding length -> mean market-adjusted."""
    A, Af = D["A"], D["Af"]
    T = len(D["dates"])
    liq = (D["v60"] >= floor) & (D["raw"] >= MIN_PX)
    pools = {}
    for j in P["j"].unique():
        pools[j] = np.flatnonzero(liq[:-1, j] & np.isfinite(A[1:, j])) + 1          # candidate e (t = e-1 liquid)
    H = (P["x"] - P["e"]).to_numpy()
    J = P["j"].to_numpy()
    draws = np.zeros(N_PLACEBO)
    for k in range(N_PLACEBO):
        vals = []
        for jj, h in zip(J, H):
            pool = pools[jj]
            pool = pool[pool + h < T]
            if len(pool) == 0:
                continue
            e = pool[rng.integers(len(pool))]
            x = e + h
            ax = A[x, jj] if np.isfinite(A[x, jj]) else Af[x, jj]
            if np.isfinite(ax):
                vals.append(ax / A[e, jj] - 1 - (I[x] / I[e] - 1))
        draws[k] = np.mean(vals)
    return draws


def tstat(x) -> float:
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 and x.std(ddof=1) > 0 else float("nan")


def sleeve_daily(P: pd.DataFrame, D, pct=0.05, max_pos=20) -> pd.Series:
    """Event sleeve on its own: 5 % of NAV per open event (cap 20), cash otherwise; costs on entry / exit day."""
    A, Af = D["A"], D["Af"]
    T = len(D["dates"])
    R = np.zeros(T)
    open_ = {}
    ent = {}
    for r in P.itertuples():
        ent.setdefault(r.e, []).append(r)
    for t in range(T):
        day = 0.0
        for k, r in list(open_.items()):
            a0 = A[t - 1, r.j] if np.isfinite(A[t - 1, r.j]) else Af[t - 1, r.j]
            a1 = A[t, r.j] if np.isfinite(A[t, r.j]) else Af[t, r.j]
            rr = a1 / a0 - 1 if np.isfinite(a0) and np.isfinite(a1) else 0.0
            if t == r.x:
                rr = (1 + rr) * (1 - D["c_out"][t, r.j]) - 1
                del open_[k]
            day += pct * rr
        for r in ent.get(t, []):
            if len(open_) < max_pos:
                open_[(r.code, r.e)] = r
                day -= pct * D["c_in"][t, r.j]
        R[t] = day
    return pd.Series(R, index=D["dates"])


def dsr(r: np.ndarray, n_trials: int) -> float:
    r = r[np.isfinite(r)]
    n = len(r)
    if n < 3 or r.std() == 0:
        return 0.0
    mu, sd = r.mean(), r.std()
    sr = mu / sd
    sk = ((r - mu) ** 3).mean() / sd ** 3
    ku = ((r - mu) ** 4).mean() / sd ** 4
    Z, e = NormalDist(), 0.5772156649015329
    v = (1 - sk * sr + (ku - 1) / 4.0 * sr ** 2) / (n - 1)
    if v <= 0:
        return 0.0
    se = math.sqrt(v)
    emax = Z.inv_cdf(1 - 1.0 / n_trials) * (1 - e) + Z.inv_cdf(1 - 1.0 / (n_trials * math.e)) * e
    return Z.cdf((sr - se * emax) / se)


def sstats(s: pd.Series) -> dict:
    s = s[s.index >= s[s != 0].index.min()] if (s != 0).any() else s
    eq = (1 + s).cumprod()
    yrs = max((s.index[-1] - s.index[0]).days / 365.25, 0.1)
    return {"cagr": float(eq.iloc[-1] ** (1 / yrs) - 1), "sharpe": float(s.mean() / s.std() * math.sqrt(252)) if s.std() > 0 else float("nan"),
            "mdd": float((eq / eq.cummax() - 1).min())}


def evaluate(name, ev, D, I, I_lo, H, kind, excl, exit_col=None, neigh=((10,), (40,))):
    P = returns(prep(ev, D, LIQ_V, H, exit_col), D, I)
    res = {"name": name, "kind": kind, "n_raw": int(len(ev)), "n": int(len(P))}
    P_lo = returns(prep(ev, D, LIQ_V_LO, H, exit_col), D, I_lo)
    res["n_lo"] = int(len(P_lo))
    if len(P) < 3:
        res["verdict"] = "UNTESTABLE"
        return res, P
    P["exc"] = matched_excess(P, D, LIQ_V, excl)
    res.update({"net": float(P["net"].mean()), "net_med": float(P["net"].median()), "t_net": tstat(P["net"]), "gross": float(P["gross"].mean()),
                "hit": float((P["net"] > 0).mean()), "exc": float(np.nanmean(P["exc"])), "t_exc": tstat(P["exc"]), "mkt": float(P["mkt"].mean()),
                "t_mkt": tstat(P["mkt"]), "cost": float((P["gross"] - P["net"]).mean())})
    P["y"] = pd.to_datetime(P["pub"]).dt.year
    by = P.groupby("y").agg(n=("net", "size"), net=("net", "mean"), exc=("exc", "mean"))
    res["years"] = {int(y): {"n": int(v.n), "net": float(v.net), "exc": float(v.exc)} for y, v in by.iterrows()}
    yy = by[by["n"] >= 5]
    res["years_pos"] = f"{int((yy['net'] > 0).sum())}/{len(yy)}"
    res["years_neg_exc"] = f"{int((yy['exc'] < 0).sum())}/{len(yy)}"
    ok_years_long = len(yy) > 0 and (yy["net"] > 0).mean() >= 2 / 3
    ok_years_avoid = len(yy) > 0 and (yy["exc"] < 0).mean() >= 2 / 3
    dr = placebo(P, D, I, LIQ_V)
    res["placebo_pct"] = float((dr < P["mkt"].mean()).mean() * 100)
    res["placebo_med"], res["placebo_p95"], res["placebo_p05"] = float(np.median(dr)), float(np.percentile(dr, 95)), float(np.percentile(dr, 5))
    res["cost15"] = float(returns(prep(ev, D, LIQ_V, H, exit_col), D, I, 1.5)["net"].mean())
    Pd = returns(prep(ev, D, LIQ_V, H, exit_col, delay=1), D, I)
    res["delay1"] = float(Pd["net"].mean()) if len(Pd) else float("nan")
    res["delay1_mkt"] = float(Pd["mkt"].mean()) if len(Pd) else float("nan")
    nb = {}
    for (h,) in neigh:
        Q = returns(prep(ev, D, LIQ_V, h, None), D, I)
        nb[f"H{h}"] = {"n": int(len(Q)), "net": float(Q["net"].mean()) if len(Q) else float("nan"), "mkt": float(Q["mkt"].mean()) if len(Q) else float("nan")}
    nb["floor1bn"] = {"n": int(len(P_lo)), "net": float(P_lo["net"].mean()) if len(P_lo) else float("nan"), "mkt": float(P_lo["mkt"].mean()) if len(P_lo) else float("nan")}
    res["neigh"] = nb
    s = sleeve_daily(P, D)
    res["sleeve"] = sstats(s)
    res["dsr"] = dsr(s[s.index >= s[s != 0].index.min()].to_numpy(), N_AFTER) if (s != 0).any() else 0.0
    # verdict
    if len(P) < 30:
        res["verdict"] = "UNTESTABLE"
    elif kind == "long":
        prim = res["net"] > 0 and res["t_net"] >= 2.5 and res["exc"] > 0 and res["t_exc"] >= 2.0
        if not prim:
            res["verdict"] = "CLOSED"
        else:
            fails = []
            if res["placebo_pct"] < 95:
                fails.append("P")
            if not ok_years_long:
                fails.append("T")
            if not all(v["net"] > 0 for v in nb.values()):
                fails.append("N")
            res["fails"] = fails
            res["verdict"] = "ROBUST" if not fails else ("FRAGILE" if "P" in fails or len(fails) >= 2 else "PARTIAL")
    else:
        prim = res["exc"] <= -0.02 and res["t_exc"] <= -2.0
        if not prim:
            res["verdict"] = "CLOSED (no avoid signal)"
        else:
            fails = []
            if res["placebo_pct"] > 5:
                fails.append("P")
            if not ok_years_avoid:
                fails.append("T")
            res["fails"] = fails
            res["verdict"] = "ROBUST avoid-filter" if not fails else ("FRAGILE" if "P" in fails or len(fails) >= 2 else "PARTIAL avoid-filter")
    return res, P


def diag_profile(P, D, I, hs=(1, 5, 10, 20, 40, 60)):
    """Market-adjusted mean drift from entry close to +h, and the run-up from t-20 to t (not trials)."""
    A, Af = D["A"], D["Af"]
    T = len(D["dates"])
    out = {}
    for h in hs:
        v = []
        for r in P.itertuples():
            x = r.e + h
            if x < T:
                ax = A[x, r.j] if np.isfinite(A[x, r.j]) else Af[x, r.j]
                v.append(ax / A[r.e, r.j] - 1 - (I[x] / I[r.e] - 1))
        out[f"+{h}"] = float(np.nanmean(v)) if v else float("nan")
    v = []
    for r in P.itertuples():
        a0 = A[r.t - 20, r.j] if np.isfinite(A[r.t - 20, r.j]) else Af[r.t - 20, r.j]
        v.append(A[r.e, r.j] / a0 - 1 - (I[r.e] / I[r.t - 20] - 1))
    out["runup_t-20..e"] = float(np.nanmean(v))
    return out


def main() -> int:
    conn = psycopg.connect(dsn())
    D = load(conn)
    log(f"panel {len(D['dates'])} sessions x {len(D['codes'])} codes, {D['dates'][0].date()} -> {D['dates'][-1].date()}")
    I, I_lo = index_series(D, LIQ_V), index_series(D, LIQ_V_LO)
    E = {"split_ann": ann_events(conn, D, "split_ann", 180), "rights_ann": ann_events(conn, D, "rights_ann", 180),
         "buyback_ann": ann_events(conn, D, "buyback_ann", 90), "tender_ann": ann_events(conn, D, "tender_ann", 180),
         "split_ex": ca_events(conn, D, "split_ex"), "rights_ex": ca_events(conn, D, "rights_ex"), "reverse": ca_events(conn, D, "reverse")}
    # T2: attach the split ex-date session to each split announcement (first split ex-date after the announcement, <= 200 days)
    sx = E["split_ex"]
    xs = []
    for r in E["split_ann"].itertuples():
        m = sx[(sx["code"] == r.code) & (sx["pub"] > r.pub) & (sx["pub"] <= r.pub + pd.Timedelta(days=200))]
        xs.append(int(m["e"].iloc[0]) if len(m) else r.e + 120)
    E["split_ann"]["xe"] = xs
    excl = {f: {} for f in E}
    for f, ev in E.items():
        for r in ev.itertuples():
            excl[f].setdefault(r.code, []).append(r.e)
    counts = {f: {"all": int(len(ev)), "by_year": {int(k): int(v) for k, v in pd.to_datetime(ev["pub"]).dt.year.value_counts().sort_index().items()}} for f, ev in E.items()}
    log("events: " + ", ".join(f"{f} {c['all']}" for f, c in counts.items()))
    spec = [("split_ann_20", "split_ann", 20, "long", None), ("split_ann_toex", "split_ann", None, "long", "xe"),
            ("split_ex_20", "split_ex", 20, "long", None), ("buyback_ann_20", "buyback_ann", 20, "long", None),
            ("tender_ann_20", "tender_ann", 20, "long", None), ("rights_ann_20", "rights_ann", 20, "avoid", None),
            ("rights_ex_20", "rights_ex", 20, "avoid", None)]
    R, PP, prof = {}, {}, {}
    for name, fam, H, kind, xc in spec:
        neigh = ((20,), (40,)) if xc else ((10,), (40,))
        res, P = evaluate(name, E[fam], D, I, I_lo, H, kind, excl[fam], xc, neigh)
        R[name], PP[name] = res, P
        if len(P):
            prof[name] = diag_profile(P, D, I)
        log(f"{name}: n {res['n']} (raw {res['n_raw']}, Rp1bn {res['n_lo']}) net {res.get('net', float('nan')) * 100:+.2f} % t {res.get('t_net', float('nan')):.2f} "
            f"exc {res.get('exc', float('nan')) * 100:+.2f} % t {res.get('t_exc', float('nan')):.2f} mkt {res.get('mkt', float('nan')) * 100:+.2f} placebo pct {res.get('placebo_pct', float('nan')):.0f} "
            f"years {res.get('years_pos')} delay {res.get('delay1', float('nan')) * 100:+.2f} cost1.5 {res.get('cost15', float('nan')) * 100:+.2f} -> {res['verdict']}")
    # reverse split: count only
    rv = E["reverse"]
    R["reverse_split"] = {"n_raw": int(len(rv)), "events": [f"{r.code} {r.pub.date()} {r.title}" for r in rv.itertuples()], "verdict": "UNTESTABLE (4 events)"}
    # 2025+ open-entry diagnostic (gross, market-adjusted not needed): open of e vs close of e + H
    # opens back-filled from Yahoo (open_src='yahoo') are chart data, not IDX opening prints: keep them out
    opn = pd.read_sql("select code, trade_date d, CASE WHEN open_src = 'idx' THEN open END AS open from idx.bar where trade_date >= '2025-01-01' and open > 0 and source='idx'", conn)
    opn["d"] = pd.to_datetime(opn["d"])
    ow = opn.pivot(index="d", columns="code", values="open").reindex(index=D["dates"], columns=D["codes"]).to_numpy(float)
    diag_open = {}
    for name, P in PP.items():
        if not len(P):
            continue
        Q = P[pd.to_datetime(P["pub"]) >= "2025-01-01"]
        v, v2 = [], []
        for r in Q.itertuples():
            o = ow[r.e, r.j]
            if np.isfinite(o) and o > 0:
                v.append(D["raw"][r.e, r.j] / o - 1)                   # entry-day open -> close (what the close fill gives up)
                v2.append(r.gross)
        diag_open[name] = {"n": len(v), "open_to_close_e": float(np.mean(v)) if v else float("nan")}
    # avoid-filter / combo replay only if a pre-registered bar passed
    passed = [k for k, v in R.items() if str(v.get("verdict", "")).startswith(("ROBUST", "PARTIAL"))]
    combo = {}
    if passed:
        combo = combo_effect(passed, PP, E, D, R)
    write_report(R, counts, prof, diag_open, combo, PP)
    if os.environ.get("CA_DRY"):
        log("dry run - no study row")
        return 0
    with conn:
        sid = rs.record_study(conn, STUDY, date.today(), params={"trials": TRIALS, "n_before": N_BEFORE, "n_trials_cumulative": N_AFTER, "liq_floor": LIQ_V,
                                                                 "placebo": N_PLACEBO, "controls": N_CTRL, "seed": SEED},
                              summary=common.plain({"results": R, "counts": counts, "profile": prof, "open_diag": diag_open, "combo": combo}), names=[],
                              report_path=os.path.join(HERE, "IDX_CORP_ACTIONS_2026-09-25.md"))
    log(f"study #{sid} stored")
    return 0


def combo_effect(passed, PP, E, D, R):
    """Pre-registered follow-up; only reached when a bar passes."""
    import pickle
    os.environ.setdefault("IDX_ML_CACHE", os.path.join(ROOT, "tmp", "ml_strategy_cache.pkl"))
    os.environ.setdefault("IDX_EXIT_CACHE", os.path.join(ROOT, "tmp", "exit_cache.pkl"))
    os.environ["INGEST_DB_DSN"] = dsn()
    import idx_combo_rupiah as CR
    import idx_ml_strategy as M
    P = pickle.load(open(os.environ["IDX_ML_CACHE"], "rb"))
    P = P[(P["d"] >= "2021-06-01") & (P["d"] <= CR.END)].copy()
    dates = M.wide(P, "close").index
    codes = M.wide(P, "close").columns
    g = lambda c: M.wide(P, c).reindex(index=dates, columns=codes)  # noqa: E731
    A, raw = g("ac").to_numpy(float), g("close").to_numpy(float)
    offer, bid = np.nan_to_num(g("offer").to_numpy(float)), np.nan_to_num(g("bid").to_numpy(float))
    liq = g("liq").fillna(False).astype(bool).to_numpy()
    ml = CR.ml_trades(P, dates, codes, A, raw, offer, bid, liq)
    tr = CR.trend_trades(os.environ["INGEST_DB_DSN"], dates)
    gap = CR.gap_events(os.environ["INGEST_DB_DSN"], dates)
    out = {}
    base_nav, _, _ = CR.engine(dates, codes, A, raw, offer, bid, ml, tr, gap, {"gap", "trend", "ML"})
    out["base"] = CR.stats(base_nav)
    base_r = base_nav.pct_change().fillna(0)
    for name in passed:
        fam = {"split_ann_20": "split_ann", "split_ann_toex": "split_ann", "split_ex_20": "split_ex", "buyback_ann_20": "buyback_ann",
               "tender_ann_20": "tender_ann", "rights_ann_20": "rights_ann", "rights_ex_20": "rights_ex"}[name]
        if R[name]["kind"] == "avoid":
            ev = E[fam]
            dpos = {d: i for i, d in enumerate(dates)}
            block = {}
            for r in ev.itertuples():
                d0 = pd.Timestamp(r.pub).normalize()
                i = int(dates.searchsorted(d0))
                block.setdefault(r.code, []).append((i, i + 20))
            f = lambda xs: [x for x in xs if not any(a <= x["t_in"] <= b for a, b in block.get(x["code"], []))]  # noqa: E731
            nav, _, _ = CR.engine(dates, codes, A, raw, offer, bid, f(ml), f(tr), gap, {"gap", "trend", "ML"})
            out[name] = {"filtered": CR.stats(nav), "removed_ml": len(ml) - len(f(ml)), "removed_trend": len(tr) - len(f(tr))}
        else:
            s = sleeve_daily(PP[name], D).reindex(base_nav.index).fillna(0)
            sl = {}
            for use in ("gap", "trend", "ML"):
                n_, _, _ = CR.engine(dates, codes, A, raw, offer, bid, ml, tr, gap, {use})
                sl[use] = float(np.corrcoef(n_.pct_change().fillna(0), s)[0, 1])
            comb = (1 + base_r + s).cumprod() * CR.CAPITAL
            out[name] = {"corr": sl, "corr_combined": float(np.corrcoef(base_r, s)[0, 1]), "combined_plus": CR.stats(comb), "sleeve_alone": sstats(s)}
    return out


READING = """1. **0 of 7 pass. Nothing here is a sleeve and nothing is an avoid filter.** Five long arms: three are UNTESTABLE at the desk floor
   (split announcement n 10, split to ex-date n 10, split ex-date n 28 - splitters on IDX are mostly small, illiquid names), two are
   CLOSED on the primary bar (buyback n 115: net -0.3 %, matched excess -1.8 %, t -1.2; tender / change of control n 43: net -0.8 %,
   excess +1.4 %, t 0.5). Neither avoid arm reaches -2 % / t -2: rights announcement is POSITIVE vs matched controls (+7.3 %, t 1.4,
   0/4 years negative), rights ex-date is -1.9 % (t -0.5, placebo pct 9, years 2/4).
2. **The information is priced before the disclosure.** Run-up t-20 -> entry (market-adjusted): tender +8.3 %, split +8.7 %, rights
   announcement +6.3 %, rights ex-date +25.7 %. On IDX the mandatory tender offer is disclosed AFTER the controlling stake has changed
   hands; the tender price is the acquisition price the market has already traded to. Post-hoc check (not a trial, not a verdict): a
   strict tender-title-only definition (78 disclosures, target-side wording, no 'hasil/laporan') is worse - net -2.4 % (n 25, LIQ) to
   -5.2 % (n 39, Rp 1 bn) at 20 sessions. The EM "tender offer premium" does not exist in this data after the disclosure.
3. **Buybacks:** the 2025-26 surge (112 + 86 plans, most of them the OJK "kondisi pasar berfluktuasi signifikan" no-RUPS buybacks
   after the 2025 drawdowns) gives +0.6 % gross over 20 sessions against a 0.9 % round trip; H 40 is +2.0 % net but the primary H
   fails and 2026 is -8.1 %. A buyback plan is not a commitment to buy and the market treats it that way.
4. **Rights (HMETD) as an avoid filter: no.** The median rights-ex name does fall (median net -12 %), but the mean is carried by a few
   rebounds and the matched excess is not separable from noise (t -0.5); the announcement itself is followed by a positive, noisy
   excess (right tail: BUVA, PACK, PANI). A rule that skips trend / ML entries around rights would remove winners as often as losers.
   The pre-registered combo replay was therefore not run.
5. **Reverse split: UNTESTABLE** (4 events 2020-24: MITI, BEKS, BBRM, NETV). Split drift: too few liquid events to test; the ten
   liquid split announcements run +8 % market-adjusted by +40 sessions but -2 % at +20 - a lottery, not a rule.
6. **Data notes.** (a) adj_factor handles splits and rights correctly (close x adj_factor is continuous across DSSA 2026-04-09
   1:25 and FORU 2026-09-22); (b) DEFECT: 441 'rights_or_bonus' rows dated 2026-09-21 (factor ~0.98-1.0) are artefacts of the 09-18
   backfill (the reset compared 09-21 'Previous' with 09-17's close) - they also shift adj_factor for rows before 09-18 by ~1-2 %
   on those names; excluded here, worth a fix in the ingest (not touched: read-only menu); (c) announcements exist only from
   2023-07, so every announcement arm is ~3 years; opens before 2025 exist only for LQ45, so fills are at the entry-day close
   (2025+ open->close on the entry day is -2.0 % for tender, +0.5 % buyback: the open fill would not rescue either).
7. **Trials used: 7 (883 -> 890).** Closed family: corporate-action event drift (split, buyback, tender/MTO, rights) - long-only."""


def pc(x, d=2):
    return "-" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x * 100:+.{d}f} %"


def write_report(R, counts, prof, diag_open, combo, PP):
    L = [f"# IDX menu 39 (Track B4) - corporate-action events, long-only - 2026-09-25 - {len(TRIALS)} trials, cumulative N = {N_AFTER}", "",
         "Script `research/idx_corp_actions.py` (pre-registration in its docstring). Signal = the IDX disclosure's publication (announcements "
         "exist from 2023-07-03) or the ex-date (corporate_action, 2020 ->); fill at the close of the first session whose open follows the "
         "publication (closing offer + 0.10 %), exit at the closing bid - 0.20 %; returns on close x adj_factor (split/rights adjusted, "
         "no dividends). LIQ floor at the signal day: 60-session mean value >= Rp 5 bn, close >= Rp 100. Controls = 5 LIQ names nearest in "
         "value; placebo = 500 same-code random-date draws.", "",
         "## Events", "", "| family | all disclosures / ex-dates (deduped) | by year |", "|---|---|---|"]
    for f, c in counts.items():
        L.append(f"| {f} | {c['all']} | " + " ".join(f"{y}:{n}" for y, n in c["by_year"].items()) + " |")
    L += ["", "## Pre-registered trials", "",
          "| trial | n LIQ (Rp 1 bn) | net mean / median | t net | hit | gross | cost | matched excess (t) | mkt-adj (t) | placebo pct (p05/med/p95) | years | cost x1.5 | delay 1 | neighbours | sleeve 5 %/event CAGR / Sharpe / mDD | DSR | verdict |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for k in TRIALS:
        r = R[k]
        if "net" not in r:
            L.append(f"| {k} | {r['n']} ({r['n_lo']}) | - | - | - | - | - | - | - | - | - | - | - | - | - | - | {r['verdict']} |")
            continue
        nb = "; ".join(f"{a} n{v['n']} {pc(v['net'], 1)}" for a, v in r["neigh"].items())
        yrs = r["years_pos"] if r["kind"] == "long" else f"exc<0 {r['years_neg_exc']}"
        L.append(f"| {k} | {r['n']} ({r['n_lo']}) | {pc(r['net'])} / {pc(r['net_med'])} | {r['t_net']:.2f} | {r['hit'] * 100:.0f} % | {pc(r['gross'])} | {pc(r['cost'])} | "
                 f"{pc(r['exc'])} ({r['t_exc']:.2f}) | {pc(r['mkt'])} ({r['t_mkt']:.2f}) | {r['placebo_pct']:.0f} ({pc(r['placebo_p05'], 1)}/{pc(r['placebo_med'], 1)}/{pc(r['placebo_p95'], 1)}) | "
                 f"{yrs} | {pc(r['cost15'])} | {pc(r['delay1'])} | {nb} | {pc(r['sleeve']['cagr'], 1)} / {r['sleeve']['sharpe']:.2f} / {pc(r['sleeve']['mdd'], 0)} | {r['dsr']:.2f} | **{r['verdict']}** |")
    L += ["", f"Reverse split: {R['reverse_split']['n_raw']} events ({'; '.join(R['reverse_split']['events'])}) -> **UNTESTABLE**, no trial spent.", "",
          "## Per year (net mean / matched excess, events)", "", "| trial | " + " | ".join(str(y) for y in range(2020, 2027)) + " |", "|---|" + "---|" * 7]
    for k in TRIALS:
        ys = R[k].get("years", {})
        L.append(f"| {k} | " + " | ".join(f"{pc(ys[y]['net'], 1)} / {pc(ys[y]['exc'], 1)} (n{ys[y]['n']})" if y in ys else "-" for y in range(2020, 2027)) + " |")
    L += ["", "## Diagnostics (not trials)", "", "Market-adjusted drift from the entry close (mean), and the run-up t-20 -> entry close:", "",
          "| trial | run-up | +1 | +5 | +10 | +20 | +40 | +60 | 2025+ entry-day open->close (n) |", "|---|---|---|---|---|---|---|---|---|"]
    for k, p in prof.items():
        o = diag_open.get(k, {})
        L.append(f"| {k} | {pc(p['runup_t-20..e'], 1)} | " + " | ".join(pc(p[f'+{h}'], 1) for h in (1, 5, 10, 20, 40, 60)) + f" | {pc(o.get('open_to_close_e'), 1)} ({o.get('n', 0)}) |")
    if combo:
        L += ["", "## Combo / filter effect (pre-registered follow-up)", "", "```", str(common.plain(combo)), "```"]
    L += ["", "## Reading (written after the dry run; numbers are the same seeded run)", "", READING]
    open(os.path.join(HERE, "IDX_CORP_ACTIONS_2026-09-25.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    for k, P in PP.items():
        if len(P):
            P.to_csv(os.path.join(ROOT, "research-scratch", f"corp_actions_{k}.csv"), index=False)


if __name__ == "__main__":
    sys.exit(main())
