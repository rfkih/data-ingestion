#!/usr/bin/env python3
"""IDX menu FF-1 - can the NEXT financial report be forecast? Fundamental forecast, phase 1 PRELIMINARY
(operator, 2026-09-25: "okay selesaikan kekurangan datanya dan iya boleh jalan fase 1 sebagai preliminary").

PRELIMINARY: runs on the ~8.1k reports parsed today; 12.8k more workbooks are being downloaded (tmp/fin_backlog_drain.py).
Before 2024 the parsed quarterlies cover only ~150 names per quarter, mostly the old value/quality research pool, so the
2021-2023 folds are thin and tilted towards good companies. The SAME script re-runs unchanged once the backlog is in;
only that run is the verdict.

The question, point in time. For every report R (a code's YTD statement ending at period_end, months 3/6/9/12) the
prediction is made ON R's period_end - the quarter is over, the report is not out yet (median 45 days later). Features
use only what was public on that date: the latest report published before it, the same period one year earlier (base
effect), prices up to that close, and IDX announcements in the 90 days before (from 2023-07; missing earlier).
Label sources are the workbook itself: R.net_profit vs R.net_profit_prior (the comparative column), so a label never
needs last year's report to be parsed.

PRE-REGISTERED (4 trials; cumulative 849 + 4 = 853).
  T1 up     R's YTD net profit above the same period last year (net_profit > net_profit_prior).
  T1 size   growth (np - prior) / |prior|, clipped to [-2, 2]  (rank IC; informative for T1, not a separate verdict)
  T3 worse  deterioration: a loss (np < 0), OR net margin down >= 3 pp on the year, OR CFO turned negative (prior >= 0).
  Models    LightGBM, one per target; walk-forward by the target's calendar year Y in 2021..2026: trained on reports
            whose label was PUBLISHED before Jan 1 of Y (so no fold sees its own future), tested on reports ending in Y.
  Naive     T1: the latest published report's YTD YoY growth (persistence); T3: the latest report's own deterioration
            flag plus its margin change (a model has to know more than "what was bad stays bad").
  Metric    per-cut AUC (cut = the target period_end: the question is which NAMES do better inside one reporting season,
            not which season was good for everyone), same as the desk's ML since ML-7.
READING RULE: a target PASSES if model per-cut AUC >= naive + 0.02 in at least 4 of the 6 test years AND the pooled
2021-2026 per-cut AUC >= 0.60. Informative only (no verdict): the price reaction - quintile spread of the adjusted return
from period_end to 20 trading days after publication (no costs), which is phase 2's question.
READ-ONLY on market tables; one idx.study row + report. INGEST_DB_DSN (or blackheart-ingest/idx-local.env).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date

import lightgbm as lgb
import numpy as np
import pandas as pd
import psycopg
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "blackheart-ingest", "src"))
from blackheart_ingest.idx import research_store as rs  # noqa: E402
from blackheart_ingest.idx.ml import common  # noqa: E402

N_BEFORE = 849
N_TRIALS = 4
STUDY = "fund_forecast_prelim"
YEARS = [2021, 2022, 2023, 2024, 2025, 2026]
BAR = {"lift": 0.02, "years_needed": 4, "pooled_min": 0.60}
ANN_KINDS = ["material_info", "ownership_change", "affiliated_tx", "exchange_query", "management", "public_expose",
             "rups", "dividend", "press_release"]
PARAMS = dict(objective="binary", learning_rate=0.03, num_leaves=15, min_data_in_leaf=40, feature_fraction=0.8,
              bagging_fraction=0.8, bagging_freq=1, lambda_l2=5.0, verbose=-1, seed=7)
ROUNDS = 400


def log(msg: str) -> None:
    print(f"[fund] {msg}", flush=True)


def dsn() -> str:
    if os.environ.get("INGEST_DB_DSN"):
        return os.environ["INGEST_DB_DSN"]
    for line in open(os.path.join(ROOT, "blackheart-ingest", "idx-local.env"), encoding="utf-8"):
        if line.startswith("INGEST_DB_DSN="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("INGEST_DB_DSN not set")


# ------------------------------------------------------------------------------------------------------------ load
def load(conn) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    f = pd.read_sql("""
        SELECT code, period_end, published_at, months, revenue, gross_profit, net_profit, net_profit_prior, revenue_prior,
               cfo, cfo_prior, total_assets, total_liabilities, total_equity, cash, total_debt, current_assets,
               current_liabilities, capex, dividends_paid, shares_out, eps, roe, roa, der, sector, currency, flags
          FROM idx.fundamental
         WHERE months IN (3, 6, 9, 12) AND published_at IS NOT NULL
           AND NOT ('scale_mismatch' = ANY(coalesce(flags, '{}')))""", conn)
    f["period_end"] = pd.to_datetime(f["period_end"])
    f["published_at"] = pd.to_datetime(f["published_at"], utc=True).dt.tz_convert("Asia/Jakarta").dt.tz_localize(None).dt.normalize()
    num = [c for c in f.columns if c not in ("code", "period_end", "published_at", "months", "sector", "currency", "flags")]
    f[num] = f[num].astype(float)
    f = f.sort_values(["code", "period_end", "published_at"]).drop_duplicates(["code", "period_end"], keep="last")
    log(f"fundamental rows {len(f):,}, names {f.code.nunique()}")
    b = pd.read_sql("""SELECT code, trade_date, close * adj_factor AS px, value FROM idx.bar
                        WHERE trade_date >= '2018-06-01' AND close > 0""", conn)
    b["trade_date"] = pd.to_datetime(b["trade_date"])
    b = b.sort_values(["code", "trade_date"])
    log(f"bars {len(b):,}")
    a = pd.read_sql("""SELECT code, (published_at AT TIME ZONE 'Asia/Jakarta')::date AS d, kind FROM idx.announcement
                         WHERE kind = ANY(%(k)s) AND code IS NOT NULL""", conn, params={"k": ANN_KINDS})
    a["d"] = pd.to_datetime(a["d"])
    log(f"announcements {len(a):,}")
    return f, b, a


# -------------------------------------------------------------------------------------------------------- features
def report_feats(f: pd.DataFrame) -> pd.DataFrame:
    """Per-report quantities, as ratios so the currency and the scale do not matter."""
    x = pd.DataFrame(index=f.index)
    ta = f.total_assets.where(f.total_assets > 0)
    rev = f.revenue.where(f.revenue.abs() > 0)
    revp = f.revenue_prior.where(f.revenue_prior.abs() > 0)
    x["np_g"] = ((f.net_profit - f.net_profit_prior) / f.net_profit_prior.abs().where(f.net_profit_prior.abs() > 0)).clip(-2, 2)
    x["rev_g"] = ((f.revenue - f.revenue_prior) / revp.abs()).clip(-2, 2)
    x["cfo_g"] = ((f.cfo - f.cfo_prior) / f.cfo_prior.abs().where(f.cfo_prior.abs() > 0)).clip(-2, 2)
    x["margin"] = (f.net_profit / rev).clip(-2, 2)
    x["margin_chg"] = (f.net_profit / rev - f.net_profit_prior / revp).clip(-1, 1)
    x["gross_margin"] = (f.gross_profit / rev).clip(-2, 2)
    ann = 12.0 / f.months
    x["roa"] = (f.net_profit * ann / ta).clip(-1, 1)
    x["roe"] = f.roe.clip(-2, 2)
    x["der"] = f.der.clip(0, 10)
    x["lev"] = (f.total_liabilities / ta).clip(0, 3)
    x["cur_ratio"] = (f.current_assets / f.current_liabilities.where(f.current_liabilities > 0)).clip(0, 10)
    x["cash_ta"] = (f.cash / ta).clip(0, 1)
    x["accruals"] = ((f.net_profit - f.cfo) / ta).clip(-1, 1)
    x["cfo_np"] = (f.cfo / f.net_profit.abs().where(f.net_profit.abs() > 0)).clip(-5, 5)
    x["capex_ta"] = (f.capex.abs() / ta).clip(0, 1)
    x["div_np"] = (f.dividends_paid.abs() / f.net_profit.where(f.net_profit > 0)).clip(0, 3)
    x["loss"] = (f.net_profit < 0).astype(float)
    x["loss_prior"] = (f.net_profit_prior < 0).astype(float)
    x["up"] = (f.net_profit > f.net_profit_prior).astype(float).where(f.net_profit.notna() & f.net_profit_prior.notna())
    x["worse"] = worse_flag(f)
    x["log_ta_idr"] = np.log(ta.where(f.currency.fillna("IDR").eq("IDR")))
    return x


def worse_flag(f: pd.DataFrame) -> pd.Series:
    rev = f.revenue.where(f.revenue.abs() > 0)
    revp = f.revenue_prior.where(f.revenue_prior.abs() > 0)
    mchg = f.net_profit / rev - f.net_profit_prior / revp
    w = (f.net_profit < 0) | (mchg <= -0.03) | ((f.cfo < 0) & (f.cfo_prior >= 0))
    known = f.net_profit.notna() & (f.net_profit_prior.notna() | f.cfo.notna())
    return w.astype(float).where(known)


def price_feats(b: pd.DataFrame, when: pd.DataFrame) -> pd.DataFrame:
    """Price facts at each (code, asof) - the last close on or before it."""
    b = b.copy()
    g = b.groupby("code")["px"]
    for n in (20, 60, 120, 250):
        b[f"ret{n}"] = g.pct_change(n, fill_method=None)
    lr = np.log(b["px"]).groupby(b["code"]).diff()
    b["vol60"] = lr.groupby(b["code"]).transform(lambda s: s.rolling(60, min_periods=40).std())
    b["adv60"] = b.groupby("code")["value"].transform(lambda s: s.rolling(60, min_periods=20).mean())
    b["hi250"] = g.transform(lambda s: s.rolling(250, min_periods=120).max())
    b["px_hi"] = b["px"] / b["hi250"]
    cols = ["code", "trade_date", "px", "ret20", "ret60", "ret120", "ret250", "vol60", "adv60", "px_hi"]
    w = when[["code", "asof"]].reset_index().sort_values("asof")
    m = pd.merge_asof(w, b[cols].sort_values("trade_date"), left_on="asof", right_on="trade_date", by="code",
                      direction="backward", tolerance=pd.Timedelta(days=10))
    m = m.set_index("index").drop(columns=["trade_date"])
    m["log_adv"] = np.log(m.pop("adv60").where(lambda s: s > 0))
    return m


def ann_feats(a: pd.DataFrame, when: pd.DataFrame) -> pd.DataFrame:
    """Announcement counts by kind in the 90 days before asof; NaN before coverage (2023-07-01 + 90 d)."""
    start = a["d"].min() + pd.Timedelta(days=90)
    out = pd.DataFrame(index=when.index)
    for k in ANN_KINDS:
        ak = a[a.kind == k]
        s = ak.groupby("code")["d"].apply(lambda s: np.sort(s.values.astype("datetime64[D]"))).to_dict()
        vals = []
        for code, asof in zip(when["code"], when["asof"], strict=True):
            arr = s.get(code)
            if arr is None or len(arr) == 0:
                vals.append(0.0)
                continue
            t = np.datetime64(asof.date())
            vals.append(float(np.searchsorted(arr, t) - np.searchsorted(arr, t - np.timedelta64(90, "D"))))
        out[f"ann_{k}"] = vals
    out.loc[when["asof"] < start, :] = np.nan
    return out


def build(f: pd.DataFrame, b: pd.DataFrame, a: pd.DataFrame) -> pd.DataFrame:
    f = f.reset_index(drop=True)
    rf = report_feats(f)
    base = pd.concat([f[["code", "period_end", "published_at", "months", "sector"]], rf], axis=1)
    # the target rows: every report with a label; asof = its period_end
    t = base[base["up"].notna() | base["worse"].notna()].copy()
    t = t.rename(columns={"published_at": "label_known"})
    t["asof"] = t["period_end"]
    t["np_g_t"] = rf.loc[t.index, "np_g"]
    t = t[["code", "period_end", "label_known", "asof", "months", "sector", "up", "worse", "np_g_t"]].reset_index(drop=True)
    # the latest report PUBLISHED before asof (strictly), as-of join on published_at
    lat = base.rename(columns={c: f"L_{c}" for c in rf.columns}).rename(columns={"period_end": "L_period_end", "months": "L_months"})
    lat = lat.drop(columns=["sector"]).sort_values("published_at")
    t = t.sort_values("asof")
    t["asof_m1"] = t["asof"] - pd.Timedelta(days=1)
    t = pd.merge_asof(t, lat, left_on="asof_m1", right_on="published_at", by="code", direction="backward",
                      allow_exact_matches=True).drop(columns=["asof_m1"])
    t["L_age"] = (t["asof"] - t["published_at"]).dt.days
    t["L_same_year"] = (t["L_period_end"].dt.year == t["period_end"].dt.year).astype(float)
    t = t.drop(columns=["published_at"])
    # the same period one year earlier (base effect), if it was published by asof
    ly = base[["code", "period_end", "published_at", "np_g", "rev_g", "margin_chg", "up"]].copy()
    ly["period_end"] = ly["period_end"] + pd.DateOffset(years=1)
    ly = ly.rename(columns={"np_g": "LY_np_g", "rev_g": "LY_rev_g", "margin_chg": "LY_margin_chg", "up": "LY_up",
                            "published_at": "LY_pub"})
    t = t.merge(ly, on=["code", "period_end"], how="left")
    late = t["LY_pub"] >= t["asof"]
    t.loc[late, ["LY_np_g", "LY_rev_g", "LY_margin_chg", "LY_up"]] = np.nan
    t = t.drop(columns=["LY_pub"])
    # history: how many of the code's last 4 published reports grew YoY
    hist = base[["code", "published_at", "up"]].dropna().sort_values(["code", "published_at"])
    hist["up4"] = hist.groupby("code")["up"].transform(lambda s: s.rolling(4, min_periods=2).mean())
    t = t.sort_values("asof")
    t["asof_m1"] = t["asof"] - pd.Timedelta(days=1)
    t = pd.merge_asof(t, hist[["code", "published_at", "up4"]].sort_values("published_at"), left_on="asof_m1",
                      right_on="published_at", by="code", direction="backward").drop(columns=["asof_m1", "published_at"])
    t = t.reset_index(drop=True)
    t = pd.concat([t, price_feats(b, t)[price_feats_cols()]], axis=1)
    t = pd.concat([t, ann_feats(a, t)], axis=1)
    t["sector_c"] = t["sector"].astype("category").cat.codes.astype(float)
    t["target_months"] = t["months"].astype(float)
    t = t[t["L_period_end"].notna()].reset_index(drop=True)
    log(f"targets with a prior published report: {len(t):,} ({t.code.nunique()} names)")
    return t


def price_feats_cols() -> list[str]:
    return ["px", "ret20", "ret60", "ret120", "ret250", "vol60", "px_hi", "log_adv"]


def feature_list(t: pd.DataFrame) -> list[str]:
    drop = {"code", "period_end", "label_known", "asof", "months", "sector", "up", "worse", "np_g_t", "L_period_end",
            "px"}
    return [c for c in t.columns if c not in drop]


# ------------------------------------------------------------------------------------------------------ evaluation
def cut_auc(t: pd.DataFrame, score: np.ndarray, y: np.ndarray) -> float:
    m, _, n = common.cut_auc(t["period_end"].dt.strftime("%Y-%m-%d").values, score, y)
    return m if n else float("nan")


def walk_forward(t: pd.DataFrame, target: str, feats: list[str]) -> tuple[pd.Series, dict]:
    pred = pd.Series(np.nan, index=t.index)
    imp: dict[str, float] = {}
    for y in YEARS:
        start = pd.Timestamp(f"{y}-01-01")
        tr = t[(t["label_known"] < start) & t[target].notna()]
        te = t[(t["period_end"].dt.year == y) & t[target].notna()]
        if len(tr) < 500 or len(te) < 100:
            log(f"  {target} {y}: skipped (train {len(tr)}, test {len(te)})")
            continue
        m = lgb.train(PARAMS, lgb.Dataset(tr[feats], tr[target]), ROUNDS)
        pred.loc[te.index] = m.predict(te[feats])
        for k, v in zip(feats, m.feature_importance("gain"), strict=True):
            imp[k] = imp.get(k, 0.0) + float(v)
        log(f"  {target} {y}: train {len(tr):,} test {len(te):,}")
    tot = sum(imp.values()) or 1.0
    return pred, {k: round(v / tot, 4) for k, v in sorted(imp.items(), key=lambda kv: -kv[1])[:15]}


def naive(t: pd.DataFrame, target: str) -> np.ndarray:
    if target == "up":
        return t["L_np_g"].values
    return (t["L_worse"].fillna(0) - t["L_margin_chg"].fillna(0)).values


def reaction(conn_bars: pd.DataFrame, t: pd.DataFrame, score: pd.Series) -> dict:
    """Informative: adjusted return from period_end to 20 trading days after publication, quintiles of the score per cut."""
    b = conn_bars[["code", "trade_date", "px"]]
    s = t.loc[score.notna(), ["code", "period_end", "label_known"]].copy()
    s["score"] = score.dropna()
    p0 = pd.merge_asof(s.sort_values("period_end"), b.sort_values("trade_date"), left_on="period_end", right_on="trade_date",
                       by="code", direction="backward", tolerance=pd.Timedelta(days=10)).rename(columns={"px": "p0"})
    bb = b.copy()
    bb["px20"] = bb.groupby("code")["px"].shift(-20)
    p1 = pd.merge_asof(p0.sort_values("label_known"), bb[["code", "trade_date", "px20"]].sort_values("trade_date").rename(columns={"trade_date": "d1"}),
                       left_on="label_known", right_on="d1", by="code", direction="forward", tolerance=pd.Timedelta(days=10))
    p1["r"] = p1["px20"] / p1["p0"] - 1
    p1 = p1[p1["r"].notna()]
    n = p1.groupby("period_end")["score"].transform("size")
    p1["q"] = np.floor(p1.groupby("period_end")["score"].rank(pct=True, method="first") * 5 - 1e-9).where(n >= 10)
    p1["y"] = p1["period_end"].dt.year
    out = {}
    for y, g in p1.groupby("y"):
        q = g.groupby("q")["r"].median()
        out[int(y)] = {"n": int(len(g)), "q1_med": round(float(q.get(0, np.nan)), 4), "q5_med": round(float(q.get(4, np.nan)), 4),
                       "spread": round(float(q.get(4, np.nan) - q.get(0, np.nan)), 4)}
    return out


def main() -> int:
    d = dsn()
    with psycopg.connect(d) as conn:
        f, b, a = load(conn)
    t = build(f, b, a)
    feats = feature_list(t)
    log(f"{len(feats)} features")
    res: dict = {"coverage": {}, "targets": {}}
    for y in YEARS:
        ty = t[t["period_end"].dt.year == y]
        res["coverage"][y] = {"reports": int(len(ty)), "names": int(ty.code.nunique()), "up_rate": round(float(ty["up"].mean()), 3),
                              "worse_rate": round(float(ty["worse"].mean()), 3)}
    for target in ("up", "worse"):
        pred, imp = walk_forward(t, target, feats)
        nv = naive(t, target)
        rows = {}
        for y in YEARS:
            m = (t["period_end"].dt.year == y) & t[target].notna() & pred.notna()
            if m.sum() < 100:
                continue
            yy = t.loc[m, target].values
            rows[y] = {"n": int(m.sum()), "model": round(cut_auc(t[m], pred[m].values, yy), 4),
                       "naive": round(cut_auc(t[m], nv[m.values], yy), 4)}
            rows[y]["lift"] = round(rows[y]["model"] - rows[y]["naive"], 4)
        m = t[target].notna() & pred.notna()
        pooled = {"model": round(cut_auc(t[m], pred[m].values, t.loc[m, target].values), 4),
                  "naive": round(cut_auc(t[m], nv[m.values], t.loc[m, target].values), 4)}
        wins = sum(1 for r in rows.values() if r["lift"] >= BAR["lift"])
        passed = wins >= BAR["years_needed"] and pooled["model"] >= BAR["pooled_min"]
        extra = {}
        if target == "up":
            ok = m & t["np_g_t"].notna()
            extra["ic_growth_pooled"] = round(float(stats.spearmanr(pred[ok], t.loc[ok, "np_g_t"]).statistic), 4)
        res["targets"][target] = {"years": rows, "pooled": pooled, "wins": wins, "passed": passed, "importance": imp,
                                  "reaction": reaction(b, t, pred), **extra}
        log(f"{target}: wins {wins}/{len(rows)} pooled {pooled} -> {'PASS' if passed else 'fail'}")
    n_trials = N_BEFORE + N_TRIALS
    L = [f"# IDX menu FF-1 - fundamental forecast, PRELIMINARY - {date.today()} - {N_TRIALS} trials, cumulative N = {n_trials}", "",
         "Prediction made on the target period's end date (report not yet out); per-cut AUC = ordering names inside one reporting",
         "season. PRELIMINARY: the 12.8k-workbook backlog is still downloading; 2021-2023 folds are thin and tilted to the old",
         "value/quality pool. Only the re-run on the full data is the verdict.", "", "## Coverage", "",
         "| year | reports | names | P(profit up) | P(worse) |", "|---|---|---|---|---|"]
    for y, c in res["coverage"].items():
        L.append(f"| {y} | {c['reports']} | {c['names']} | {c['up_rate']:.0%} | {c['worse_rate']:.0%} |")
    for target, name in (("up", "T1 - net profit up YoY"), ("worse", "T3 - deterioration")):
        r = res["targets"][target]
        L += ["", f"## {name}", "", "| year | n | model AUC | naive AUC | lift | Q1 med 20d | Q5 med 20d | Q5-Q1 |", "|---|---|---|---|---|---|---|---|"]
        for y, v in r["years"].items():
            rx = r["reaction"].get(y, {})
            L.append(f"| {y} | {v['n']} | {v['model']:.3f} | {v['naive']:.3f} | {v['lift']:+.3f} | {rx.get('q1_med', float('nan')):+.1%} | "
                     f"{rx.get('q5_med', float('nan')):+.1%} | {rx.get('spread', float('nan')):+.1%} |")
        L += ["", f"Pooled per-cut AUC: model {r['pooled']['model']:.3f}, naive {r['pooled']['naive']:.3f}. Years with lift >= "
              f"{BAR['lift']}: {r['wins']}/{len(r['years'])}. " + (f"Rank IC with realised growth: {r['ic_growth_pooled']:+.3f}. " if "ic_growth_pooled" in r else "")
              + f"**{'PASSES' if r['passed'] else 'does not pass'}** the pre-registered bar (preliminary).", "",
              "Top features (gain share): " + ", ".join(f"{k} {v:.0%}" for k, v in list(r["importance"].items())[:10])]
    text = "\n".join(L)
    out = os.path.join(HERE, f"IDX_FUND_FORECAST_PRELIM_{date.today()}.md")
    open(out, "w", encoding="utf-8").write(text + "\n")
    json.dump(res, open(out.replace(".md", ".json"), "w"), indent=1, default=str)
    print(text)
    with psycopg.connect(d) as conn:
        sid = rs.record_study(conn, STUDY, date.today(), params={"trials": ["T1_up", "T1_size", "T3_worse", "naive"], "n_trials_cumulative": n_trials,
                                                                 "years": YEARS, "bar": BAR, "lgb": PARAMS, "rounds": ROUNDS, "preliminary": True},
                              summary=common.plain({k: {kk: vv for kk, vv in v.items() if kk != "importance"} for k, v in res["targets"].items()}),
                              names=[], report_path=out, note="menu FF-1: next-report forecast (profit up / deterioration), preliminary on partial data")
        conn.commit()
    log(f"study #{sid} stored; report {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
