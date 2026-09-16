#!/usr/bin/env python3
"""IDX — which financial profile preceded a 2x within 24 months? (2026-09-17, pre-registered before the first run)

Question (operator): "cari yang punya probabilitas paling tinggi untuk naik 100 persen dalam 2 tahun" — from the financial
statements. Now answerable point-in-time: the 2020-2026 quarterlies for the whole liquid universe are parsed.

Design
  snapshots   last trading day of Feb / May / Aug / Nov, 2020-05 .. 2024-08 (the 24-month window must end by 2026-09-16);
              the four months sit right after the audit / Q1 / H1 / Q3 filing deadlines, so each snapshot carries fresh reports
  universe    point-in-time: Utama/Pengembangan on the day, traded, 60d median value >= Rp 5 bn, with an audited report
              (candidates.build(); the production PIT logic, 16:00 WIB cutoff)
  targets     touched2x_24m  max adjusted close within the next 24 months >= 2 x the snapshot close   <- PRIMARY
              end2x_24m      adjusted close 24 months later >= 2 x                                     <- secondary (the honest one)
              touched2x_12m / end2x_12m the same at 12 months (snapshots through 2025-08)
              a name delisted inside the window counts as 0 (no double, -100 % end return)
  features    (all as of the snapshot, from the reports published by then)
              value:     ep_ttm (TTM E/P), bp (B/P), dy (trailing yield)
              quality:   roe (audited), conv (CFO / audited profit, capped 3), der
              growth:    q_np_yoy (latest YTD profit vs prior-year YTD), q_rev_yoy, accel (q_np_yoy minus the previous quarter's),
                         margin_chg (YTD net margin minus prior-year YTD margin), turnaround (prior-year loss -> TTM profit)
              balance:   netcash_mcap ((cash - debt) / mcap)
              price:     mom (12-1 momentum), dist_high (close / 252d high - 1), mcap (log size), v60 (liquidity)
              gates:     gate_strict, gate_loose (as flags)
  analysis    per feature: within-date quintiles (Q1 low .. Q5 high) -> hit rate of the targets, median 24m end return, N;
              lift = hit(extreme quintile) / base rate of the same dates; consistency = number of snapshot years (2020..2024)
              in which the extreme quintile beat that year's base rate. A feature "passes" when lift >= 1.5 on the primary
              target AND consistency >= 4 of 5 years AND N >= 100.
  composites  pre-registered screens (a name is in the screen when every clause holds):
              A cheap_growth   ep_ttm in the top half AND q_np_yoy >= +0.30 AND gate_loose
              B beaten_value   dist_high in the bottom quintile AND ep_ttm in the top half AND gate_loose
              C small_quality  mcap in the bottom half AND gate_strict AND ep_ttm in the top quintile
              D turnaround     turnaround AND q_rev_yoy > 0 AND v60 >= Rp 5 bn
              E accel_cheap    accel in the top quintile AND ep_ttm in the top half AND gate_loose
              reported: hit rates (both targets), median / mean 24m end return, share of names losing > 50 %, names per date
  today       every screen applied to the latest snapshot (2026-09-16) with the numbers; the ranking of today's names by the
              passing features' average within-date percentile ("doubler score"), stated as a screen, not a forecast
  trials      16 features + 5 screens = 21 -> cumulative N_trials 173 + 21 = 194. Nothing here is a certified rule.
Output: research-scratch/idx-screen/doublers_2026-09-17.{md,json}; the paper is research/IDX_DOUBLERS_2026-09-17.md.
READ-ONLY on the DB. INGEST_DB_DSN=... blackheart-ingest/.venv/Scripts/python research/idx_doublers.py
"""
from __future__ import annotations

import json
import math
import os
import sys
from datetime import date, datetime
from decimal import Decimal

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blackheart-ingest", "src"))
import idx_value_quality as VQ  # noqa: E402

from blackheart_ingest.idx import candidates as cand  # noqa: E402
from blackheart_ingest.idx import metrics as MET  # noqa: E402

OUT_MD = os.path.join(VQ.OUTDIR, "doublers_2026-09-17.md")
OUT_JSON = os.path.join(VQ.OUTDIR, "doublers_2026-09-17.json")
SNAP_MONTHS = (2, 5, 8, 11)
FIRST, LAST_24, LAST_12 = pd.Timestamp("2020-05-01"), pd.Timestamp("2024-09-16"), pd.Timestamp("2025-09-16")
H24, H12 = pd.DateOffset(months=24), pd.DateOffset(months=12)
FEATURES = ["ep_ttm", "bp", "dy", "roe", "conv", "der", "q_np_yoy", "q_rev_yoy", "accel", "margin_chg", "turnaround",
            "netcash_mcap", "mom", "dist_high", "log_mcap", "v60"]
QUINT_FEATURES = [f for f in FEATURES if f != "turnaround"]
TARGETS = ["touched2x_24m", "end2x_24m", "touched2x_12m", "end2x_12m"]
LIQ = float(MET.LIQ)


def f(v) -> float | None:
    if v is None:
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) or math.isinf(x) else x


def snapshot_dates(index: pd.DatetimeIndex) -> list[pd.Timestamp]:
    out = []
    for y in range(2020, 2027):
        for m in SNAP_MONTHS:
            end = pd.Timestamp(date(y, m, 1)) + pd.offsets.MonthEnd(0)
            pos = index.searchsorted(end, side="right") - 1
            if 0 <= pos < len(index) and index[pos].month == m and FIRST <= index[pos] <= index[-1]:
                out.append(index[pos])
    return sorted(set(out))


def load_fundamentals(conn) -> pd.DataFrame:
    df = VQ.frame(conn, """SELECT code, period_end, period_label, published_at, months, revenue, net_profit, total_equity, total_debt, cash,
                                  cfo, net_profit_prior, revenue_prior, net_profit_yoy, revenue_yoy
                             FROM idx.fundamental""", (),
                  ["code", "pe", "label", "pub", "months", "rev", "np", "eq", "debt", "cash", "cfo", "np_prior", "rev_prior", "np_yoy", "rev_yoy"])
    df["pe"] = pd.to_datetime(df["pe"])
    df["pub"] = pd.to_datetime(df["pub"], utc=True).dt.tz_convert("Asia/Jakarta").dt.tz_localize(None)
    for c in ("rev", "np", "eq", "debt", "cash", "cfo", "np_prior", "rev_prior", "np_yoy", "rev_yoy"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    # the comparative: stored, else the YoY inversion where unambiguous (metrics.prior_from_yoy)
    for k, pk, yk in (("np", "np_prior", "np_yoy"), ("rev", "rev_prior", "rev_yoy")):
        miss = df[pk].isna()
        inv = [f(MET.prior_from_yoy(None if pd.isna(a) else Decimal(str(a)), None if pd.isna(b) else Decimal(str(b))))
               for a, b in zip(df.loc[miss, k], df.loc[miss, yk], strict=True)]
        df.loc[miss, pk] = [np.nan if v is None else v for v in inv]
    return df.sort_values(["code", "pe", "pub"])


def quarter_features(fund: pd.DataFrame, D: pd.Timestamp, codes: list[str]) -> dict[str, dict]:
    """Per code: latest quarterly YTD row and the previous quarterly row published by the D close; the latest audited row."""
    cutoff = pd.Timestamp(D.date()) + pd.Timedelta(hours=16)
    sub = fund[(fund["pub"] <= cutoff) & (fund["pe"] >= D - pd.Timedelta(days=MET.MAX_AGE_DAYS)) & fund["code"].isin(codes)]
    out: dict[str, dict] = {}
    for code, g in sub.groupby("code"):
        g = g.sort_values(["pe", "pub"])
        q = g[g["label"] != "TAHUNAN"]
        a = g[g["label"] == "TAHUNAN"]
        r: dict = {}
        latest = None
        if len(q):
            latest = q.iloc[-1]
            r["q_np_yoy"] = f((latest["np"] - latest["np_prior"]) / abs(latest["np_prior"])) if pd.notna(latest["np_prior"]) and latest["np_prior"] != 0 else None
            r["q_rev_yoy"] = f((latest["rev"] - latest["rev_prior"]) / abs(latest["rev_prior"])) if pd.notna(latest["rev_prior"]) and latest["rev_prior"] != 0 else None
            if pd.notna(latest["rev"]) and latest["rev"] > 0 and pd.notna(latest["rev_prior"]) and latest["rev_prior"] > 0 and pd.notna(latest["np_prior"]):
                r["margin_chg"] = f(latest["np"] / latest["rev"] - latest["np_prior"] / latest["rev_prior"])
            prev = q[q["pe"] < latest["pe"]]
            if len(prev) and r.get("q_np_yoy") is not None:
                p = prev.iloc[-1]
                if pd.notna(p["np_prior"]) and p["np_prior"] != 0:
                    r["accel"] = f(r["q_np_yoy"] - (p["np"] - p["np_prior"]) / abs(p["np_prior"]))
            r["ytd_turn"] = bool(pd.notna(latest["np_prior"]) and latest["np_prior"] <= 0 and latest["np"] > 0)
        if len(a):
            la = a.iloc[-1]
            r["a_prior_loss"] = bool(pd.notna(la["np_prior"]) and la["np_prior"] <= 0)
            r["a_np"] = f(la["np"])
        row = latest if latest is not None else (a.iloc[-1] if len(a) else None)
        if row is not None:
            r["cash"], r["debt"] = f(row["cash"]), f(row["debt"])
        out[code] = r
    return out


def features_at(conn, fund: pd.DataFrame, D: pd.Timestamp, close: pd.DataFrame) -> pd.DataFrame:
    res = cand.build(conn, D.date())
    rows = [r for r in res["all_rows"] if r["tradable"] and r["ep"] is not None]
    codes = [r["code"] for r in rows]
    qf = quarter_features(fund, D, codes)
    hist = close.loc[:D].tail(252)
    recs = []
    for r in rows:
        q = qf.get(r["code"], {})
        px = f(close.at[D, r["code"]]) if r["code"] in close.columns else None
        hi = f(hist[r["code"]].max()) if r["code"] in hist.columns else None
        mcap = f(r["mcap"])
        ttm = f(r["ep_ttm"])
        turnaround = bool(q.get("a_prior_loss") and ttm is not None and ttm > 0) or bool(q.get("ytd_turn"))
        recs.append({"D": D, "code": r["code"], "sector": r["sector"], "price": px, "mcap": mcap, "log_mcap": math.log(mcap) if mcap else None,
                     "v60": f(r["v60"]), "mom": f(r["mom"]), "dist_high": (px / hi - 1) if (px and hi) else None,
                     "ep_ttm": ttm if ttm is not None else f(r["ep"]), "bp": f(r["bp"]), "dy": f(r["dy"]), "roe": f(r["roe"]), "conv": f(r["conv"]),
                     "der": f(r["der"]), "q_np_yoy": q.get("q_np_yoy"), "q_rev_yoy": q.get("q_rev_yoy"), "accel": q.get("accel"),
                     "margin_chg": q.get("margin_chg"), "turnaround": turnaround,
                     "netcash_mcap": ((q["cash"] - q["debt"]) / mcap) if (mcap and q.get("cash") is not None and q.get("debt") is not None) else None,
                     "gate_strict": bool(r["gate_strict"]), "gate_loose": bool(r["gate_loose"])})
    return pd.DataFrame(recs)


def forward(close: pd.DataFrame, delisted: dict, D: pd.Timestamp, code: str) -> dict:
    s = close[code].loc[D:] if code in close.columns else pd.Series(dtype=float)
    p0 = f(s.iloc[0]) if len(s) else None
    out = {}
    for tag, off, last in (("24m", H24, LAST_24), ("12m", H12, LAST_12)):
        if p0 is None or D > last:
            out[f"touched2x_{tag}"] = out[f"end2x_{tag}"] = out[f"ret_{tag}"] = None
            continue
        end = D + off
        w = s.loc[D + pd.Timedelta(days=1):end].dropna()
        dead = code in delisted and delisted[code] < end
        mx = f(w.max()) if len(w) else None
        pe = 0.0 if dead else (f(w.iloc[-1]) if len(w) else None)
        out[f"touched2x_{tag}"] = None if mx is None else bool(mx >= 2 * p0)
        out[f"end2x_{tag}"] = None if pe is None else bool(pe >= 2 * p0)
        out[f"ret_{tag}"] = None if pe is None else pe / p0 - 1
    return out


def add_quintiles(df: pd.DataFrame) -> pd.DataFrame:
    for feat in QUINT_FEATURES:
        df[f"{feat}_q"] = df.groupby("D")[feat].transform(
            lambda s: pd.qcut(s.rank(method="first"), 5, labels=[1, 2, 3, 4, 5]) if s.notna().sum() >= 25 else pd.Series(np.nan, index=s.index))
        df[f"{feat}_pct"] = df.groupby("D")[feat].rank(pct=True)
    return df


def base_rates(df: pd.DataFrame) -> dict:
    out = {}
    for t in TARGETS:
        v = df[t].dropna()
        out[t] = {"n": len(v), "rate": float(v.mean()) if len(v) else None,
                  "by_year": {int(y): {"n": len(g), "rate": float(g.mean())} for y, g in v.groupby(df.loc[v.index, "D"].dt.year)}}
    return out


def feature_table(df: pd.DataFrame, base: dict) -> list[dict]:
    rows = []
    for feat in QUINT_FEATURES:
        qcol = f"{feat}_q"
        rec = {"feature": feat}
        for t in ("touched2x_24m", "end2x_24m", "touched2x_12m"):
            sub = df[df[t].notna() & df[qcol].notna()]
            if len(sub) < 100:
                continue
            per_q = sub.groupby(qcol, observed=True)[t].agg(["mean", "size"])
            med = sub.groupby(qcol, observed=True)["ret_24m" if "24m" in t else "ret_12m"].median()
            rec[t] = {int(q): {"hit": float(per_q.loc[q, "mean"]), "n": int(per_q.loc[q, "size"]), "med_ret": f(med.loc[q])} for q in per_q.index}
            base_t = float(sub[t].mean())
            for side, q in (("high", 5), ("low", 1)):
                if q not in per_q.index:
                    continue
                lift = per_q.loc[q, "mean"] / base_t if base_t else None
                years = 0
                tot = 0
                for _y, g in sub.groupby(sub["D"].dt.year):
                    gq = g[g[qcol] == q]
                    if len(gq) >= 10:
                        tot += 1
                        years += int(gq[t].mean() > g[t].mean())
                rec[f"{t}:{side}"] = {"lift": f(lift), "consistency": f"{years}/{tot}", "n": int(per_q.loc[q, "size"]),
                                      "passes": bool(lift is not None and lift >= 1.5 and tot >= 4 and years >= 4 and per_q.loc[q, "size"] >= 100)}
        rows.append(rec)
    # the boolean feature
    for feat in ("turnaround", "gate_strict", "gate_loose"):
        rec = {"feature": feat}
        for t in ("touched2x_24m", "end2x_24m", "touched2x_12m"):
            sub = df[df[t].notna()]
            if len(sub) < 100:
                continue
            g = sub.groupby(feat)[t].agg(["mean", "size"])
            base_t = float(sub[t].mean())
            rec[t] = {str(k): {"hit": float(g.loc[k, "mean"]), "n": int(g.loc[k, "size"])} for k in g.index}
            if True in g.index:
                years = tot = 0
                for _y, gg in sub.groupby(sub["D"].dt.year):
                    gq = gg[gg[feat]]
                    if len(gq) >= 10:
                        tot += 1
                        years += int(gq[t].mean() > gg[t].mean())
                lift = g.loc[True, "mean"] / base_t if base_t else None
                rec[f"{t}:true"] = {"lift": f(lift), "consistency": f"{years}/{tot}", "n": int(g.loc[True, "size"]),
                                    "passes": bool(lift is not None and lift >= 1.5 and tot >= 4 and years >= 4 and g.loc[True, "size"] >= 100)}
        rows.append(rec)
    return rows


def screens(df: pd.DataFrame) -> dict[str, pd.Series]:
    ok = lambda s: s.fillna(False).astype(bool)  # noqa: E731
    return {
        "A_cheap_growth": ok((df["ep_ttm_pct"] >= 0.5) & (df["q_np_yoy"] >= 0.30) & df["gate_loose"]),
        "B_beaten_value": ok((df["dist_high_q"] == 1) & (df["ep_ttm_pct"] >= 0.5) & df["gate_loose"]),
        "C_small_quality": ok((df["log_mcap_pct"] <= 0.5) & df["gate_strict"] & (df["ep_ttm_q"] == 5)),
        "D_turnaround": ok(df["turnaround"] & (df["q_rev_yoy"] > 0) & (df["v60"] >= LIQ)),
        "E_accel_cheap": ok((df["accel_q"] == 5) & (df["ep_ttm_pct"] >= 0.5) & df["gate_loose"]),
    }


def screen_table(df: pd.DataFrame) -> list[dict]:
    out = []
    masks = screens(df)
    for name, m in masks.items():
        rec = {"screen": name}
        for t in ("touched2x_24m", "end2x_24m", "touched2x_12m", "end2x_12m"):
            sub = df[df[t].notna()]
            inn = sub[m.loc[sub.index]]
            if not len(inn):
                continue
            base_t = float(sub[t].mean())
            ret = "ret_24m" if "24m" in t else "ret_12m"
            years = tot = 0
            for _y, g in sub.groupby(sub["D"].dt.year):
                gi = g[m.loc[g.index]]
                if len(gi) >= 10:
                    tot += 1
                    years += int(gi[t].mean() > g[t].mean())
            rec[t] = {"hit": float(inn[t].mean()), "base": base_t, "lift": f(inn[t].mean() / base_t) if base_t else None, "n": len(inn),
                      "per_date": f(inn.groupby("D").size().mean()), "med_ret": f(inn[ret].median()), "mean_ret": f(inn[ret].mean()),
                      "loss_gt50": float((inn[ret] <= -0.5).mean()), "consistency": f"{years}/{tot}"}
        out.append(rec)
    return out


def today_tables(df_today: pd.DataFrame, passing: list[tuple[str, str]], screen_names: list[str]) -> dict:
    masks = screens(df_today)
    res = {"as_of": str(df_today["D"].iloc[0].date()), "screens": {}, "score": []}
    cols = ["code", "sector", "price", "mcap", "ep_ttm", "bp", "dy", "roe", "q_np_yoy", "q_rev_yoy", "accel", "dist_high", "mom", "netcash_mcap", "gate_strict"]
    for name in screen_names:
        sub = df_today[masks[name]]
        res["screens"][name] = [{c: (f(r[c]) if c not in ("code", "sector", "gate_strict") else r[c]) for c in cols} for _, r in sub.iterrows()]
    if passing:
        sc = pd.Series(0.0, index=df_today.index)
        for feat, side in passing:
            p = df_today[f"{feat}_pct"] if feat in QUINT_FEATURES else df_today[feat].astype(float)
            sc = sc + (p if side in ("high", "true") else 1 - p).fillna(0.5)
        df_today = df_today.assign(score=sc / len(passing)).sort_values("score", ascending=False)
        res["score"] = [{**{c: (f(r[c]) if c not in ("code", "sector", "gate_strict") else r[c]) for c in cols}, "score": f(r["score"])}
                        for _, r in df_today.head(25).iterrows()]
    return res


def pct(v, d=0):
    return "-" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{100 * v:.{d}f}%"


def render(base: dict, feats: list[dict], scr: list[dict], today: dict, passing: list[tuple[str, str]], n_obs: int, dates: list) -> str:
    L = [f"# IDX doublers — which financial profile preceded a 2x? ({n_obs} name-snapshots, {len(dates)} quarterly snapshots {dates[0].date()} .. {dates[-1].date()})", ""]
    L.append("## Base rates (a liquid, audited name picked at random)")
    for t in TARGETS:
        b = base[t]
        if b["rate"] is None:
            continue
        L.append(f"- **{t}**: {pct(b['rate'], 1)} of {b['n']}  |  by snapshot year: " + ", ".join(f"{y} {pct(v['rate'])} (n={v['n']})" for y, v in b["by_year"].items()))
    L += ["", "## Single features — within-date quintiles, primary target touched2x_24m (Q1 = lowest fifth, Q5 = highest)", "",
          "| feature | Q1 hit | Q2 | Q3 | Q4 | Q5 hit | Q5 med ret | Q1 med ret | lift high | cons. | lift low | cons. | end2x Q5/Q1 | pass |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in feats:
        if r["feature"] in ("turnaround", "gate_strict", "gate_loose"):
            continue
        t = r.get("touched2x_24m")
        if not t:
            continue
        hi, lo = r.get("touched2x_24m:high", {}), r.get("touched2x_24m:low", {})
        e = r.get("end2x_24m", {})
        p = "HIGH" if hi.get("passes") else ("LOW" if lo.get("passes") else "")
        L.append(f"| {r['feature']} | {pct(t.get(1, {}).get('hit'))} | {pct(t.get(2, {}).get('hit'))} | {pct(t.get(3, {}).get('hit'))} | {pct(t.get(4, {}).get('hit'))} | "
                 f"{pct(t.get(5, {}).get('hit'))} | {pct(t.get(5, {}).get('med_ret'))} | {pct(t.get(1, {}).get('med_ret'))} | "
                 f"{hi.get('lift', 0) or 0:.2f} | {hi.get('consistency', '-')} | {lo.get('lift', 0) or 0:.2f} | {lo.get('consistency', '-')} | "
                 f"{pct(e.get(5, {}).get('hit'))}/{pct(e.get(1, {}).get('hit'))} | {p} |")
    L += ["", "| flag | hit when true | n | hit when false | lift | cons. | end2x true | pass |", "|---|---|---|---|---|---|---|---|"]
    for r in feats:
        if r["feature"] not in ("turnaround", "gate_strict", "gate_loose"):
            continue
        t, tt, e = r.get("touched2x_24m", {}), r.get("touched2x_24m:true", {}), r.get("end2x_24m", {})
        L.append(f"| {r['feature']} | {pct(t.get('True', {}).get('hit'))} | {t.get('True', {}).get('n', 0)} | {pct(t.get('False', {}).get('hit'))} | "
                 f"{tt.get('lift', 0) or 0:.2f} | {tt.get('consistency', '-')} | {pct(e.get('True', {}).get('hit'))} | {'YES' if tt.get('passes') else ''} |")
    L += ["", f"Passing features (lift >= 1.5, >= 4/5 years, n >= 100): {', '.join(f'{a} ({b})' for a, b in passing) or 'NONE'}", ""]
    L += ["## Pre-registered screens", "", "| screen | names/date | touched2x 24m | base | lift | cons. | end2x 24m | med 24m ret | mean | loss>50% | touched2x 12m |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in scr:
        a, e, b = r.get("touched2x_24m", {}), r.get("end2x_24m", {}), r.get("touched2x_12m", {})
        if not a:
            continue
        L.append(f"| {r['screen']} | {a['per_date']:.1f} | {pct(a['hit'])} | {pct(a['base'])} | {a['lift']:.2f} | {a['consistency']} | {pct(e.get('hit'))} | "
                 f"{pct(a['med_ret'])} | {pct(a['mean_ret'])} | {pct(a['loss_gt50'])} | {pct(b.get('hit'))} |")
    L += ["", f"## Today ({today['as_of']}) — the screens applied to the latest snapshot", ""]
    for name, rows in today["screens"].items():
        L.append(f"### {name} ({len(rows)} names)")
        if rows:
            L += ["", "| code | sector | price | mcap (T) | E/P ttm | B/P | DY | ROE | YTD np yoy | YTD rev yoy | accel | from 52w high | mom 12-1 | net cash/mcap | strict |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
            for r in rows:
                L.append(f"| {r['code']} | {(r['sector'] or '')[:18]} | {r['price']:,.0f} | {r['mcap'] / 1e12:.2f} | {pct(r['ep_ttm'], 1)} | {r['bp'] or 0:.2f} | {pct(r['dy'], 1)} | {pct(r['roe'])} | "
                         f"{pct(r['q_np_yoy'])} | {pct(r['q_rev_yoy'])} | {pct(r['accel'])} | {pct(r['dist_high'])} | {pct(r['mom'])} | {pct(r['netcash_mcap'])} | {'Y' if r['gate_strict'] else ''} |")
        L.append("")
    if today["score"]:
        L += ["### Doubler score — average within-date percentile of the passing features (top 25)", "",
              "| # | code | sector | score | price | E/P ttm | YTD np yoy | accel | from 52w high | mcap (T) | strict |", "|---|---|---|---|---|---|---|---|---|---|---|"]
        for i, r in enumerate(today["score"], 1):
            L.append(f"| {i} | {r['code']} | {(r['sector'] or '')[:18]} | {r['score']:.2f} | {r['price']:,.0f} | {pct(r['ep_ttm'], 1)} | {pct(r['q_np_yoy'])} | {pct(r['accel'])} | {pct(r['dist_high'])} | {r['mcap'] / 1e12:.2f} | {'Y' if r['gate_strict'] else ''} |")
    return "\n".join(L) + "\n"


def main():
    conn = VQ.connect()
    close, _vol, delisted, _div, _ix = VQ.load(conn)
    fund = load_fundamentals(conn)
    dates = snapshot_dates(close.index)
    hist_dates = [d for d in dates if d <= LAST_12]
    frames = []
    for D in hist_dates:
        df = features_at(conn, fund, D, close)
        fw = [forward(close, delisted, D, c) for c in df["code"]]
        df = pd.concat([df.reset_index(drop=True), pd.DataFrame(fw)], axis=1)
        frames.append(df)
        print(f"{D.date()}: {len(df)} names, touched2x_24m={pct(df['touched2x_24m'].mean()) if df['touched2x_24m'].notna().any() else '-'}", flush=True)
    hist = add_quintiles(pd.concat(frames, ignore_index=True))
    base = base_rates(hist)
    feats = feature_table(hist, base)
    passing = []
    for r in feats:
        for side in ("high", "low", "true"):
            k = f"touched2x_24m:{side}"
            if r.get(k, {}).get("passes"):
                passing.append((r["feature"], side))
    scr = screen_table(hist)
    # today
    today_D = close.index[-1]
    df_t = add_quintiles(features_at(conn, fund, today_D, close))
    today = today_tables(df_t, passing, list(screens(df_t).keys()))
    md = render(base, feats, scr, today, passing, len(hist), hist_dates)
    os.makedirs(VQ.OUTDIR, exist_ok=True)
    open(OUT_MD, "w", encoding="utf-8").write(md)
    json.dump({"generated": datetime.now().isoformat(timespec="seconds"), "snapshots": [str(d.date()) for d in hist_dates], "n_obs": len(hist),
               "base": base, "features": feats, "passing": passing, "screens": scr, "today": today}, open(OUT_JSON, "w", encoding="utf-8"), indent=1, default=str)
    hist.to_csv(os.path.join(VQ.OUTDIR, "doublers_panel_2026-09-17.csv"), index=False)
    print(md)
    print("->", OUT_MD)
    if "--store" in sys.argv:
        print("stored study #", store(conn, today_D, base, feats, scr, today, passing, df_t))


def store(conn, today_D, base, feats, scr, today, passing, df_t) -> int:
    """The run as rows (migration 0020): every name in a screen today or in the score top 25, with its figures and the
    historical hit rate of the screens it sits in."""
    from blackheart_ingest.idx import research_store as rs
    ctx = {r["screen"]: r for r in scr}
    masks = screens(df_t)
    names: dict[str, dict] = {}
    for name, m in masks.items():
        for _, r in df_t[m].iterrows():
            n = names.setdefault(r["code"], {"code": r["code"], "screens": [], "features": {}, "context": {}})
            n["screens"].append(name)
            n["context"][name] = {k: ctx[name].get(k) for k in ("touched2x_24m", "end2x_24m") if ctx[name].get(k)}
    for i, r in enumerate(today["score"], 1):
        n = names.setdefault(r["code"], {"code": r["code"], "screens": [], "features": {}, "context": {}})
        n["score"], n["rank"] = r["score"], i
    keep = ["sector", "price", "mcap", "v60", "mom", "dist_high", "ep_ttm", "bp", "dy", "roe", "conv", "der", "q_np_yoy", "q_rev_yoy",
            "accel", "margin_chg", "turnaround", "netcash_mcap", "gate_strict", "gate_loose"]
    rows = df_t.set_index("code")
    for code, n in names.items():
        n["features"] = {k: (None if pd.isna(rows.at[code, k]) else rows.at[code, k]) for k in keep if k in rows.columns}
    params = {"snapshots": SNAP_MONTHS, "first": str(FIRST.date()), "targets": TARGETS, "features": FEATURES,
              "screens": list(masks.keys()), "trials": 21, "n_trials_cumulative": 194, "passing": passing}
    summary = {"base": base, "features": feats, "screens": scr}
    return rs.record_study(conn, "doublers", today_D.date(), params=params, summary=summary, names=list(names.values()),
                           report_path="research/IDX_DOUBLERS_2026-09-17.md",
                           note="which financial profile preceded a 2x within 24 months; screens are pre-registered, D_turnaround is the one that passes")


if __name__ == "__main__":
    main()
