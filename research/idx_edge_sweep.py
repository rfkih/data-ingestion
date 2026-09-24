#!/usr/bin/env python3
"""IDX menu 33 PRELIM — an edge sweep on the tick feed that AVOIDS the two things that killed menus 28-32: the taker spread and the
day's drift (operator, 2026-09-23: "dengan data yang kita punya apakah kamu bisa mencari celahnya, jangan pesimis, gunakan keahlian
statistika").

Where can a retail account trade WITHOUT crossing a spread? In the auctions: the opening call (08:58 print) and the closing call
(16:00 print) clear at ONE price. Where can a signal be read WITHOUT the day's drift? Cross-sectionally: rank names against each
other at the same instant. Where does a small book edge turn into money with no new trade? In the timing of fills the desk makes
anyway. Six pre-registered reads, real fees (Ajaib / Stockbit: 15 bps buy + 25 bps sell = 40 bps round trip).

DATA  feed_trade auction prints (verb NULL): opening call ~08:58, closing call 16:00 (post-close 16:02-16:14 excluded);
      10-s grid + features from research/idx_lob_ml.build_day (continuous phases only). Sessions 2026-09-22, 09-23; closing call
      also 09-21. Names present in both.

READS (pre-registered)
  S1 CLOSING-CALL PREMIUM   close_call / mid_15:49 − 1 (bps) per name-day. Is the call systematically above/below the last continuous
                            mid (mean, t, per day)? Is it predicted by the last 15 min's OFI / TFI (cross-sectional Spearman, per day)?
  S2 CLOSE → NEXT OPEN      dislocation d = S1 on day k; y = open_call(k+1) / close_call(k) − 1 (bps). Cross-sectional IC (Spearman) and
                            the bottom-quintile-d long: buy at the closing call, sell at the next opening call, fees 40 bps (TRIAL 1; one
                            overnight exists, 09-22 → 09-23, so n ≈ 24: a direction read).
  S3 OPEN-CALL → INTRADAY   gap g = open_call / prev close_call − 1; jump j = mid_09:00:10 / open_call − 1. IC of g and j vs the return
                            open_call → mid 09:15 and → mid 15:49, ranked within day. Descriptive: names with g >= +3 % → intraday return
                            (the held-inventory 'sell the gap-up at the open' from menu 29f, on the tick feed).
  S4 MARKET OFI → MARKET    time series: MKT_OFI5 at t vs the EW market mid return over the next 5 / 15 min (Spearman, t, per day, 2
                            days x ~1,900 steps). Magnitude of the top-decile move in bps vs the 1-tick spread of BBCA/BBRI (~30 bps).
  S5 CROSS-SECTIONAL ALPHA  at every step, rank names by OFI5 (and by the menu-31 LightGBM score if present: not used here); top-decile
                            minus bottom-decile forward 5 / 15-min mid return (bps), liquid band only (spread <= 30 bps at t): the pure
                            alpha a long-only book could capture by CHOOSING WHICH liquid name to buy now (TRIALS 2-3: h5m, h15m;
                            bar = mean spread >= +15 bps with t >= 3 on both days).
  S6 EXECUTION TIMING       a taker BUY that must be done within 15 min: 'now' = hit the offer at t; 'wait' = hit the offer at the first
                            step in (t, t+90] where OBI1 >= 0.3 and micro > mid, else at the deadline. Paired improvement in bps over
                            all name-steps with a valid deadline; same for a SELL (OBI1 <= −0.3 and micro < mid). (TRIALS 4-5;
                            bar = mean improvement >= +5 bps, paired t >= 3, positive on both days.)
  Trials    5 (cumulative 694 → 699). Placebo for S5 / S6: signal shuffled within name-day, 20 draws.
  Bar       stated per read above. Two sessions: a direction read, never an adoption.

READ-ONLY. INGEST_DB_DSN=... PYTHONIOENCODING=utf-8 blackheart-ingest/.venv/Scripts/python research/idx_edge_sweep.py
  [--days 2026-09-22,2026-09-23] [--no-store] [--out research/IDX_EDGE_SWEEP_<day>.md]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
from datetime import date, timedelta

import numpy as np
import pandas as pd
import psycopg
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "blackheart-ingest", "src"))
_spec = importlib.util.spec_from_file_location("idx_lob_ml", os.path.join(HERE, "idx_lob_ml.py"))
lob = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lob)

FEE_BUY, FEE_SELL = 15.0, 25.0
SEED = 20260923
N_PLACEBO = 20
N_TRIALS_BEFORE = 694
LIQ_SPRD = 30.0
H5, H15 = 30, 90


def load_calls(conn: psycopg.Connection, days: list[date]) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute("""SELECT (ts AT TIME ZONE 'Asia/Jakarta')::date, code,
                              CASE WHEN (ts AT TIME ZONE 'Asia/Jakarta')::time < '09:00' THEN 'open' ELSE 'close' END AS call,
                              (array_agg(price ORDER BY ts DESC))[1], sum(qty)
                       FROM idx.feed_trade
                       WHERE verb IS NULL AND ((ts AT TIME ZONE 'Asia/Jakarta')::time < '09:00' OR (ts AT TIME ZONE 'Asia/Jakarta')::time BETWEEN '15:50' AND '16:01')
                         AND (ts AT TIME ZONE 'Asia/Jakarta')::date BETWEEN %s AND %s
                       GROUP BY 1, 2, 3""", (min(days) - timedelta(days=3), max(days)))
        C = pd.DataFrame(cur.fetchall(), columns=["day", "code", "call", "px", "qty"])
    C["px"] = C["px"].astype(float)
    return C


def rs(x, y) -> tuple[float, float, int]:
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 8:
        return np.nan, np.nan, int(ok.sum())
    r = stats.spearmanr(x[ok], y[ok]).statistic
    n = int(ok.sum())
    t = r * np.sqrt((n - 2) / max(1e-9, 1 - r * r))
    return float(r), float(t), n


def tstat(a) -> dict:
    a = np.asarray(a, float)
    a = a[np.isfinite(a)]
    return {"n": int(len(a)), "mean": float(a.mean()) if len(a) else np.nan, "median": float(np.median(a)) if len(a) else np.nan,
            "t": float(a.mean() / a.std(ddof=1) * np.sqrt(len(a))) if len(a) > 2 and a.std(ddof=1) > 0 else np.nan,
            "p_pos": float((a > 0).mean()) if len(a) else np.nan}


# ------------------------------------------------------------------------------------------------------------- S1-S3
def auction_reads(data: dict[date, dict[str, dict]], C: pd.DataFrame, days: list[date]) -> dict:
    out = {"S1": {}, "S2": {}, "S3": {}}
    rows = []
    for d in days:
        for code, x in data[d].items():
            F = x["F"]
            mid, t = x["mid"], pd.DatetimeIndex(x["t"])
            last = np.flatnonzero(t <= pd.Timestamp(f"{d} 15:49:59"))
            first = np.flatnonzero(t >= pd.Timestamp(f"{d} 09:00:00"))
            i915 = np.flatnonzero(t >= pd.Timestamp(f"{d} 09:15:00"))
            cc = C[(C["day"] == d) & (C["code"] == code) & (C["call"] == "close")]["px"]
            oc = C[(C["day"] == d) & (C["code"] == code) & (C["call"] == "open")]["px"]
            pc = C[(C["day"] < d) & (C["code"] == code) & (C["call"] == "close")].sort_values("day")["px"]
            nxt = C[(C["day"] > d) & (C["code"] == code) & (C["call"] == "open")].sort_values("day")["px"]
            r = {"day": d, "code": code,
                 "mid_last": mid[last[-1]] if len(last) else np.nan, "mid_first": mid[first[0]] if len(first) else np.nan,
                 "mid_915": mid[i915[0]] if len(i915) else np.nan,
                 "close_call": float(cc.iloc[0]) if len(cc) else np.nan, "open_call": float(oc.iloc[0]) if len(oc) else np.nan,
                 "prev_close": float(pc.iloc[-1]) if len(pc) else np.nan, "next_open": float(nxt.iloc[0]) if len(nxt) else np.nan,
                 "ofi_last15": float(F["OFI5"].iloc[last[-1]] + F["OFI5"].iloc[max(last[-1] - 30, 0)] + F["OFI5"].iloc[max(last[-1] - 60, 0)]) if len(last) else np.nan,
                 "tfi_last15": float(np.nanmean(F["TFI5"].iloc[max(last[-1] - 90, 0):last[-1] + 1])) if len(last) else np.nan}
            rows.append(r)
    A = pd.DataFrame(rows)
    A["prem"] = (A["close_call"] / A["mid_last"] - 1) * 1e4
    A["next_ret"] = (A["next_open"] / A["close_call"] - 1) * 1e4
    A["gap"] = (A["open_call"] / A["prev_close"] - 1) * 1e4
    A["jump"] = (A["mid_first"] / A["open_call"] - 1) * 1e4
    A["ret_915"] = (A["mid_915"] / A["open_call"] - 1) * 1e4
    A["ret_close"] = (A["mid_last"] / A["open_call"] - 1) * 1e4
    for d, g in A.groupby("day"):
        s1 = tstat(g["prem"])
        s1["ic_ofi"] = rs(g["ofi_last15"], g["prem"])
        s1["ic_tfi"] = rs(g["tfi_last15"], g["prem"])
        s1["p_at_mid"] = float((g["prem"].abs() < 1).mean()) if g["prem"].notna().any() else np.nan
        out["S1"][str(d)] = s1
        g2 = g.dropna(subset=["prem", "next_ret"])
        if len(g2) >= 20:
            q = g2["prem"].quantile([0.2, 0.8])
            lo, hi = g2[g2["prem"] <= q.iloc[0]], g2[g2["prem"] >= q.iloc[1]]
            out["S2"][str(d)] = {"ic": rs(g2["prem"], g2["next_ret"]), "n": len(g2), "all_overnight": tstat(g2["next_ret"]),
                                 "bottom_q_long_net": tstat(lo["next_ret"] - FEE_BUY - FEE_SELL), "top_q_overnight": tstat(hi["next_ret"]),
                                 "bottom_q_prem_mean": float(lo["prem"].mean()), "top_q_prem_mean": float(hi["prem"].mean())}
        g3 = g.dropna(subset=["gap", "jump"])
        out["S3"][str(d)] = {"n": len(g3), "ic_gap_915": rs(g3["gap"], g3["ret_915"]), "ic_gap_close": rs(g3["gap"], g3["ret_close"]),
                             "ic_jump_915": rs(g3["jump"], g3["ret_915"]), "ic_jump_close": rs(g3["jump"], g3["ret_close"]),
                             "jump": tstat(g3["jump"]), "gap_up3_intraday": tstat(g3[g3["gap"] >= 300]["ret_close"]),
                             "gap_dn3_intraday": tstat(g3[g3["gap"] <= -300]["ret_close"])}
    return out, A


# --------------------------------------------------------------------------------------------------------------- S4
def market_read(P: pd.DataFrame) -> dict:
    out = {}
    for d, g in P.groupby("day"):
        M = g.groupby("i").agg(mkt_ofi=("MKT_OFI5", "first"), mid=("pos_day", "mean")).sort_index()
        for h, k in ((H5, "h5m"), (H15, "h15m")):
            fwd = M["mid"].shift(-h) - M["mid"]
            r, t, n = rs(M["mkt_ofi"], fwd)
            top = M["mkt_ofi"] >= M["mkt_ofi"].quantile(0.9)
            out[f"{d}/{k}"] = {"ic": r, "t": t, "n": n, "top_decile_fwd_bps": float(fwd[top].mean()), "bottom_decile_fwd_bps": float(fwd[M['mkt_ofi'] <= M['mkt_ofi'].quantile(0.1)].mean())}
    return out


# --------------------------------------------------------------------------------------------------------------- S5
def cross_sectional(P: pd.DataFrame, rng: np.random.Generator) -> dict:
    out = {}
    L = P[P["sprd_bps"] <= LIQ_SPRD].copy()
    for h, k in ((H5, "h5m"), (H15, "h15m")):
        L[f"fwd{k}"] = L.groupby(["day", "code"])["mid"].shift(-h) / L["mid"] - 1
        res = {}
        for d, g in L.dropna(subset=["OFI5", f"fwd{k}"]).groupby("day"):
            g = g[g.groupby("i")["code"].transform("size") >= 20]
            rk = g.groupby("i")["OFI5"].rank(pct=True)
            top, bot = g[rk >= 0.9], g[rk <= 0.1]
            spread = (top.groupby("i")[f"fwd{k}"].mean() - bot.groupby("i")[f"fwd{k}"].mean()) * 1e4
            # placebo: shuffle OFI5 within (day, i)
            pl = []
            for _ in range(N_PLACEBO):
                sh = g.groupby("i")["OFI5"].transform(lambda x: rng.permutation(x.to_numpy()))
                rk2 = sh.groupby(g["i"]).rank(pct=True)
                pl.append(float(((g[rk2 >= 0.9].groupby("i")[f"fwd{k}"].mean() - g[rk2 <= 0.1].groupby("i")[f"fwd{k}"].mean()) * 1e4).mean()))
            s = tstat(spread)
            s["ticks_top"] = float((top[f"fwd{k}"] * top["mid"] / top["tick"]).mean())
            s["placebo_mean"] = float(np.mean(pl))
            s["placebo_pct"] = float((np.asarray(pl) < s["mean"]).mean() * 100)
            res[str(d)] = s
        pooled = tstat(pd.concat([pd.Series([v["mean"]] * v["n"]) for v in res.values()]))
        out[k] = {"by_day": res, "CANDIDATE": bool(all(v["mean"] >= 15 and v["t"] >= 3 for v in res.values()))}
    return out


# --------------------------------------------------------------------------------------------------------------- S6
def exec_timing(data: dict[date, dict[str, dict]], rng: np.random.Generator) -> dict:
    out = {}
    for side in ("buy", "sell"):
        by_day, pl_day = {}, {}
        for d, names in data.items():
            imp, imp_pl = [], []
            for code, x in names.items():
                F = x["F"]
                obi, micro, sess = F["OBI1"].to_numpy(float), F["micro"].to_numpy(float), x["session"]
                px = x["off1"] if side == "buy" else x["bid1"]
                good = (obi >= 0.3) & (micro > 0) if side == "buy" else (obi <= -0.3) & (micro < 0)
                good = np.where(np.isfinite(obi) & np.isfinite(micro), good, False)
                n = len(px)
                for s_i in np.unique(sess):
                    ix = np.flatnonzero(sess == s_i)
                    if len(ix) <= H15 + 1:
                        continue
                    stride = 6                                                        # one decision per minute
                    for t in ix[:-H15:stride]:
                        if not np.isfinite(px[t]) or px[t] <= 0:
                            continue
                        w = np.flatnonzero(good[t + 1:t + H15 + 1])
                        j = t + 1 + int(w[0]) if len(w) else t + H15
                        if not np.isfinite(px[j]):
                            continue
                        imp.append((px[t] / px[j] - 1) * 1e4 if side == "buy" else (px[j] / px[t] - 1) * 1e4)
                        jr = t + 1 + int(rng.integers(0, H15))                          # placebo: wait a random time
                        if np.isfinite(px[jr]):
                            imp_pl.append((px[t] / px[jr] - 1) * 1e4 if side == "buy" else (px[jr] / px[t] - 1) * 1e4)
            by_day[str(d)] = tstat(imp)
            pl_day[str(d)] = tstat(imp_pl)
        out[side] = {"by_day": by_day, "placebo_by_day": pl_day,
                     "CANDIDATE": bool(all(v["mean"] >= 5 and v["t"] >= 3 for v in by_day.values()) and all(by_day[k]["mean"] > pl_day[k]["mean"] for k in by_day))}
    return out


# ---------------------------------------------------------------------------------------------------------------- run
def run(dsn: str, days: list[date], out_path: str, store: bool, study_name: str) -> dict:
    t0 = time.time()
    data: dict[date, dict[str, dict]] = {}
    with psycopg.connect(dsn) as conn:
        C = load_calls(conn, days)
        for d in days:
            data[d] = lob.build_day(conn, d)
    common = sorted(set.intersection(*(set(v) for v in data.values())))
    data = {d: {c: data[d][c] for c in common} for d in days}
    P = pd.concat([lob.panel(data[d]).assign(day=d) for d in days], ignore_index=True)
    rng = np.random.default_rng(SEED)
    res: dict = {"desc": {"days": [d.isoformat() for d in days], "names": len(common), "calls": {k: int(v) for k, v in C.groupby("call").size().items()}}}
    ar, A = auction_reads(data, C, days)
    res.update(ar)
    res["S4"] = market_read(P)
    res["S5"] = cross_sectional(P, rng)
    res["S6"] = exec_timing(data, rng)
    res["log"] = [f"{time.time() - t0:.0f} s"]
    cands = [f"S2 bottom-quintile long ({d})" for d, v in res["S2"].items() if v["bottom_q_long_net"]["n"] >= 100 and v["bottom_q_long_net"]["mean"] >= 20 and v["bottom_q_long_net"]["t"] >= 2] \
        + [f"S5/{k}" for k, v in res["S5"].items() if v["CANDIDATE"]] + [f"S6/{k}" for k, v in res["S6"].items() if v["CANDIDATE"]]
    res["verdict"] = {"candidates": cands, "n_trials": 5}
    write_report(res, out_path)
    if store:
        from blackheart_ingest.idx import research_store as rs_
        with psycopg.connect(dsn) as conn:
            sid = rs_.record_study(conn, study_name, days[-1], params={"trials": ["S2 bottom-q long", "S5 h5m", "S5 h15m", "S6 buy", "S6 sell"],
                                                                       "n_trials_cumulative": N_TRIALS_BEFORE + 5, "fees": [FEE_BUY, FEE_SELL], "seed": SEED, "days": res["desc"]["days"]},
                                  summary=json.loads(json.dumps(res, default=str)), names=[], report_path=out_path,
                                  note=f"candidates {cands or 'none'}")
            res["study_id"] = sid
    return res


def fmt(x, f="%+.1f"):
    return (f % x) if x is not None and isinstance(x, (int, float)) and np.isfinite(x) else "-"


def write_report(res: dict, path: str) -> None:
    d = res["desc"]
    L = [f"# IDX menu 33 PRELIM — edge sweep without the taker spread and without the day's drift — {', '.join(d['days'])}", "",
         f"{d['names']} names; auction prints: {d['calls']}. Fees Ajaib/Stockbit 15 + 25 bps. Pre-registered in `research/idx_edge_sweep.py`; 5 trials (cumulative {N_TRIALS_BEFORE + 5}).",
         "**Two sessions (one overnight): a direction read, not an adoption.**", "",
         "## S1 — closing-call premium: close_call / mid_15:49 − 1 (bps)", "", "| day | n | mean | median | t | P(>0) | P(|prem| < 1 bp) | IC OFI last-15 (r, t) | IC TFI last-15 (r, t) |", "|---|---|---|---|---|---|---|---|---|"]
    for k, v in res["S1"].items():
        L.append(f"| {k} | {v['n']} | {fmt(v['mean'])} | {fmt(v['median'])} | {fmt(v['t'], '%.2f')} | {fmt(v['p_pos'] * 100, '%.0f')} % | {fmt(v['p_at_mid'] * 100, '%.0f')} % | "
                 f"{fmt(v['ic_ofi'][0], '%+.2f')} ({fmt(v['ic_ofi'][1], '%.1f')}) | {fmt(v['ic_tfi'][0], '%+.2f')} ({fmt(v['ic_tfi'][1], '%.1f')}) |")
    L += ["", "## S2 — closing-call dislocation → next opening call (bps)", "", "| close day | n | IC (r, t) | overnight all (mean, t) | bottom-quintile prem | its overnight NET of 40 bps (n, mean, median, t, P>0) | top-quintile prem | its overnight (mean) | verdict |", "|---|---|---|---|---|---|---|---|---|"]
    for k, v in res["S2"].items():
        b, a, tq = v["bottom_q_long_net"], v["all_overnight"], v["top_q_overnight"]
        ok = b["n"] >= 100 and b["mean"] >= 20 and b["t"] >= 2
        L.append(f"| {k} | {v['n']} | {fmt(v['ic'][0], '%+.2f')} ({fmt(v['ic'][1], '%.1f')}) | {fmt(a['mean'])} ({fmt(a['t'], '%.1f')}) | {fmt(v['bottom_q_prem_mean'])} | "
                 f"{b['n']}, {fmt(b['mean'])}, {fmt(b['median'])}, {fmt(b['t'], '%.2f')}, {fmt(b['p_pos'] * 100, '%.0f')} % | {fmt(v['top_q_prem_mean'])} | {fmt(tq['mean'])} | {'CANDIDATE' if ok else 'no (n < 100)' if b['mean'] >= 20 and b['t'] >= 2 else 'no'} |")
    L += ["", "## S3 — opening call → intraday (bps)", "", "| day | n | jump 09:00:10 vs call (mean, t) | IC gap→09:15 | IC gap→close | IC jump→09:15 | IC jump→close | gap ≥ +3 % intraday (n, mean) | gap ≤ −3 % intraday (n, mean) |", "|---|---|---|---|---|---|---|---|---|"]
    for k, v in res["S3"].items():
        j, gu, gd = v["jump"], v["gap_up3_intraday"], v["gap_dn3_intraday"]
        L.append(f"| {k} | {v['n']} | {fmt(j['mean'])} ({fmt(j['t'], '%.1f')}) | {fmt(v['ic_gap_915'][0], '%+.2f')} ({fmt(v['ic_gap_915'][1], '%.1f')}) | {fmt(v['ic_gap_close'][0], '%+.2f')} ({fmt(v['ic_gap_close'][1], '%.1f')}) | "
                 f"{fmt(v['ic_jump_915'][0], '%+.2f')} ({fmt(v['ic_jump_915'][1], '%.1f')}) | {fmt(v['ic_jump_close'][0], '%+.2f')} ({fmt(v['ic_jump_close'][1], '%.1f')}) | {gu['n']}, {fmt(gu['mean'])} | {gd['n']}, {fmt(gd['mean'])} |")
    L += ["", "## S4 — market-wide order flow (MKT_OFI5) → EW market mid move (bps)", "", "| day / horizon | n | IC (r, t) | top-decile fwd | bottom-decile fwd |", "|---|---|---|---|---|"]
    for k, v in res["S4"].items():
        L.append(f"| {k} | {v['n']} | {fmt(v['ic'], '%+.2f')} ({fmt(v['t'], '%.1f')}) | {fmt(v['top_decile_fwd_bps'])} | {fmt(v['bottom_decile_fwd_bps'])} |")
    L += ["", f"## S5 — cross-sectional: top-decile OFI5 minus bottom-decile forward mid return, liquid names (spread ≤ {LIQ_SPRD:.0f} bps)", "",
          "| horizon | day | steps | spread bps (mean) | median | t | P(>0) | top-decile move (ticks) | placebo mean | placebo pct | verdict |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for k, v in res["S5"].items():
        for dd, s in v["by_day"].items():
            L.append(f"| {k} | {dd} | {s['n']:,} | {fmt(s['mean'])} | {fmt(s['median'])} | {fmt(s['t'], '%.2f')} | {fmt(s['p_pos'] * 100, '%.0f')} % | {fmt(s['ticks_top'], '%+.2f')} | {fmt(s['placebo_mean'])} | {fmt(s['placebo_pct'], '%.0f')} | {'CANDIDATE' if v['CANDIDATE'] else 'no'} |")
    L += ["", "## S6 — execution timing: hit the offer/bid now vs wait for the book (OBI1 ≥ 0.3 & microprice > mid; ≤ 15 min), bps improvement", "",
          "| side | day | decisions | improvement mean | median | t | P(>0) | placebo (wait a random time) | verdict |", "|---|---|---|---|---|---|---|---|---|"]
    for k, v in res["S6"].items():
        for dd, s in v["by_day"].items():
            p = v["placebo_by_day"][dd]
            L.append(f"| {k} | {dd} | {s['n']:,} | {fmt(s['mean'])} | {fmt(s['median'])} | {fmt(s['t'], '%.2f')} | {fmt(s['p_pos'] * 100, '%.0f')} % | {fmt(p['mean'])} | {'CANDIDATE' if v['CANDIDATE'] else 'no'} |")
    L += ["", "## Reading", "", f"- Candidates: {', '.join(res['verdict']['candidates']) or 'none'}.",
          "- S1/S2/S3 trade at ONE price (the call): no spread, only fees. S5 is market-neutral by construction. S6 is money on trades the desk",
          "  makes anyway. Everything else in menus 28-32 paid the spread and rode the day's drift; this sweep is the complement.", "- Re-run at >= 20 sessions.", ""]
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(L))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", default="2026-09-22,2026-09-23")
    ap.add_argument("--no-store", action="store_true")
    ap.add_argument("--out", default="")
    ap.add_argument("--study-name", default="edge_sweep")
    a = ap.parse_args()
    days = sorted(date.fromisoformat(x) for x in a.days.split(","))
    out = a.out or os.path.join(HERE, f"IDX_EDGE_SWEEP_{days[-1].isoformat()}.md")
    res = run(os.environ["INGEST_DB_DSN"], days, out, not a.no_store, a.study_name)
    print(json.dumps({"desc": res["desc"], "verdict": res["verdict"], "study_id": res.get("study_id"), "report": out}, indent=1, default=str))


if __name__ == "__main__":
    main()
