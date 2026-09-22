#!/usr/bin/env python3
"""IDX menu 28 — preliminary microstructure study on the desk's own tick feed (operator, 2026-09-22: "untuk preliminary research
kamu bisa nggak bikin research atau prediction harga bergerak dari data yang kita punya sekarang").

What we have: the Stockbit websocket collector (idx.feed_trade / feed_book, real time: recv - ts ~ -0.3 s) has ONE full session,
2026-09-22 (09-21 = 15 min after the close). 136 names (108 liquid + 19 gocap-event + 8 watch + IHSG), 10-level order book
sampled every second when it changes, aggregated to 1-minute bars (idx.feed_bar_1m: OHLC, buy/sell volume) and 1-minute book
states (idx.feed_book_1m: last book of the minute, totals). One day is enough for a POOLED short-horizon test (~30k name-minutes)
and for nothing longer; every number below is a one-day read and is labelled as such.

QUESTION. Does the state of the book / the tape at minute t say anything about where the MID price is h minutes later?
Two different uses, two different bars:
  (a) standalone signal  - would a trade on it pay after crossing the spread and Stockbit fees (0.30 % round trip)?  Almost certainly
      not at 1-15 min; we measure it anyway so the answer is a number, not an opinion.
  (b) execution timing   - the desk already has to buy (trend entry at the next open) and sell (trail10): if the book says the mid
      is about to move, wait or go now. This needs no edge over the spread, only a reliable sign.

PRE-REGISTERED (declared before the run; nothing tuned afterwards). 7 trials (cumulative 503 + 7 = 510).
  Data      2026-09-22, continuous phases only (09:00-11:59 and 13:30-15:49 WIB); names with >= 150 valid minutes; a minute is valid
            when the last book of the minute has bid > 0, offer > bid; the book state is carried forward inside a session (the
            book persists between updates), never across the lunch break. Targets never cross the break.
  Features at minute t (all from data <= t):
    OBI1   (bid_vol[1] - off_vol[1]) / (bid_vol[1] + off_vol[1])          top-of-book imbalance
    OBI5   same on the 5 best levels each side
    OBIT   (bid_total - off_total) / (bid_total + off_total)              whole-queue imbalance
    TFI5   sum_{t-4..t}(buy_volume - sell_volume) / sum(buy + sell)      trade-flow imbalance (aggressor side from the tape)
    RET5   mid_t / mid_{t-5} - 1                                          5-minute momentum (negative IC = reversal)
    SPRD   (off - bid) / mid                                              conditioning only; reported, not a trial
  Targets   forward MID change over h = 1, 5, 15 min, in ticks (IDX tick of the mid's price band) and in bps. h = 5 is the trial;
            1 and 15 are descriptive.
  Reads (per feature, h = 5)
    IC       Spearman per name, then mean across names and t = mean / (sd / sqrt(n_names)); pooled Spearman as a check.
    halves   morning (09:00-11:59) = discovery, afternoon (13:30-15:49) = holdout, computed separately.
    placebo  the feature shuffled within each name, 50 draws -> percentile of the real mean IC.
    deciles  within-name percentile of the feature -> pooled deciles; mean forward move of D10 and D1 (ticks, bps) and the cost a
             taker pays at t: half-spread x 2 + 30 bps fees (buy at the offer, sell at the bid, Stockbit 0.10 + 0.20 %).
  Bars
    LEAD          h = 5: |t| >= 3 in BOTH halves with the same sign, and placebo percentile >= 99.
    TRADEABLE     h = 5 or 15: mean forward bps of D10 >= mean cost bps of D10 (a taker long would net > 0). Expected: none.
    EXEC-TIMING   h = 5: mean forward ticks of D10 minus D1 >= 0.25 tick with the same sign in both halves (worth waiting for /
                  acting on when a trade is planned anyway).
  Trial 7   LightGBM (sign of the 5-min mid move, zero moves dropped) on OBI1, OBI5, OBIT, TFI5, RET5, SPRD, minute-of-day; train
            morning, test afternoon; read = AUC (>= 0.55 = informative) and the realised bps of the top 10 % predicted-up minutes vs
            their cost.
  Nothing here can be adopted from one day; a LEAD earns a re-run after 20 sessions (menu 28b), not a book.

READ-ONLY. INGEST_DB_DSN=... PYTHONIOENCODING=utf-8 blackheart-ingest/.venv/Scripts/python research/idx_microstructure_prelim.py
  [--day 2026-09-22] [--no-store] [--out research/IDX_MICROSTRUCTURE_PRELIM_<day>.md]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import psycopg
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "blackheart-ingest", "src"))

WIB = ZoneInfo("Asia/Jakarta")
N_TRIALS_BEFORE = 503
TRIALS = ["OBI1", "OBI5", "OBIT", "TFI5", "RET5", "LGBM"]           # 6 feature trials (RET5 counts) + LGBM = 7 with SPRD descriptive
FEATURES = ["OBI1", "OBI5", "OBIT", "TFI5", "RET5"]
HORIZONS = (1, 5, 15)
FEE_BPS = 30.0                                                     # Stockbit 0.10 % buy + 0.20 % sell
MIN_MINUTES = 150
PLACEBO_DRAWS = 50
SEED = 20260922
SESSIONS = (("09:00", "11:59"), ("13:30", "15:49"))                # Tuesday; Friday would be 09:00-11:29 / 14:00-15:49
TICKS = ((200, 1), (500, 2), (2000, 5), (5000, 10), (float("inf"), 25))


def tick_size(px: np.ndarray) -> np.ndarray:
    out = np.full(px.shape, 25.0)
    for lim, t in reversed(TICKS[:-1]):
        out[px < lim] = t
    return out


# ------------------------------------------------------------------------------------------------------------------ data
def load(dsn: str, day: date) -> tuple[pd.DataFrame, pd.DataFrame]:
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("""SELECT minute AT TIME ZONE 'Asia/Jakarta' AS minute, code, bid_px[1] AS bid1, off_px[1] AS off1,
                              bid_vol[1] AS bv1, off_vol[1] AS ov1,
                              (SELECT sum(x) FROM unnest(bid_vol[1:5]) x) AS bv5, (SELECT sum(x) FROM unnest(off_vol[1:5]) x) AS ov5,
                              bid_total, off_total
                       FROM idx.feed_book_1m WHERE (minute AT TIME ZONE 'Asia/Jakarta')::date = %s AND code <> 'IHSG'""", (day,))
        book = pd.DataFrame(cur.fetchall(), columns=["minute", "code", "bid1", "off1", "bv1", "ov1", "bv5", "ov5", "bid_total", "off_total"])
        cur.execute("""SELECT minute AT TIME ZONE 'Asia/Jakarta' AS minute, code, close, volume, buy_volume, sell_volume, n_trades
                       FROM idx.feed_bar_1m WHERE (minute AT TIME ZONE 'Asia/Jakarta')::date = %s AND code <> 'IHSG'""", (day,))
        bars = pd.DataFrame(cur.fetchall(), columns=["minute", "code", "close", "volume", "buy_volume", "sell_volume", "n_trades"])
    for df in (book, bars):
        df["minute"] = pd.to_datetime(df["minute"])
        for c in df.columns:
            if c not in ("minute", "code"):
                df[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
    return book, bars


def session_index(day: date) -> list[pd.DatetimeIndex]:
    out = []
    for a, b in SESSIONS:
        out.append(pd.date_range(datetime.combine(day, datetime.strptime(a, "%H:%M").time()),
                                 datetime.combine(day, datetime.strptime(b, "%H:%M").time()), freq="1min"))
    return out


def build_panel(book: pd.DataFrame, bars: pd.DataFrame, day: date) -> pd.DataFrame:
    """One row per (code, minute) inside the continuous phases: features at t, forward mid moves, cost at t."""
    rows = []
    sessions = session_index(day)
    for code, b in book.groupby("code"):
        b = b.set_index("minute").sort_index()
        r = bars[bars["code"] == code].set_index("minute").sort_index()
        parts = []
        for si, idx in enumerate(sessions):
            s = b.reindex(idx).ffill()                                         # the book persists between updates (inside a session)
            s["session"] = si
            t = r.reindex(idx)[["buy_volume", "sell_volume", "volume", "n_trades"]].fillna(0.0)
            s = s.join(t)
            parts.append(s)
        s = pd.concat(parts)
        s["code"] = code
        ok = (s["bid1"] > 0) & (s["off1"] > s["bid1"])
        s.loc[~ok, ["bid1", "off1"]] = np.nan
        s["mid"] = (s["bid1"] + s["off1"]) / 2
        s["tick"] = tick_size(s["mid"].to_numpy(dtype=float))
        s["SPRD"] = (s["off1"] - s["bid1"]) / s["mid"]
        s["OBI1"] = (s["bv1"] - s["ov1"]) / (s["bv1"] + s["ov1"])
        s["OBI5"] = (s["bv5"] - s["ov5"]) / (s["bv5"] + s["ov5"])
        s["OBIT"] = (s["bid_total"] - s["off_total"]) / (s["bid_total"] + s["off_total"])
        g = s.groupby("session", group_keys=False)
        bs = g["buy_volume"].rolling(5, min_periods=1).sum().reset_index(level=0, drop=True)
        ss = g["sell_volume"].rolling(5, min_periods=1).sum().reset_index(level=0, drop=True)
        s["TFI5"] = (bs - ss) / (bs + ss)
        s["RET5"] = g["mid"].shift(0) / g["mid"].shift(5) - 1
        for h in HORIZONS:
            fwd = g["mid"].shift(-h)
            s[f"fwd{h}_ticks"] = (fwd - s["mid"]) / s["tick"]
            s[f"fwd{h}_bps"] = (fwd / s["mid"] - 1) * 1e4
        s["cost_bps"] = s["SPRD"] * 1e4 + FEE_BPS                             # taker round trip: cross the spread once each way + fees
        s["minute_of_day"] = s.index.hour * 60 + s.index.minute
        rows.append(s.reset_index().rename(columns={"index": "minute"}))
    P = pd.concat(rows, ignore_index=True)
    P = P.dropna(subset=["mid", "OBI1", "OBIT"])
    n = P.groupby("code")["mid"].transform("size")
    return P[n >= MIN_MINUTES].copy()


# --------------------------------------------------------------------------------------------------------------- reads
def per_name_ic(P: pd.DataFrame, feat: str, target: str) -> pd.Series:
    out = {}
    for code, g in P.groupby("code"):
        g = g[[feat, target]].dropna()
        if len(g) >= 30 and g[feat].nunique() > 5 and g[target].nunique() > 3:
            out[code] = stats.spearmanr(g[feat], g[target]).statistic
    return pd.Series(out, dtype=float)


def ic_read(P: pd.DataFrame, feat: str, target: str) -> dict:
    ics = per_name_ic(P, feat, target).dropna()
    n = len(ics)
    t = float(ics.mean() / (ics.std(ddof=1) / np.sqrt(n))) if n > 2 and ics.std(ddof=1) > 0 else float("nan")
    g = P[[feat, target]].dropna()
    pooled = float(stats.spearmanr(g[feat], g[target]).statistic) if len(g) > 50 else float("nan")
    return {"n_names": n, "mean_ic": float(ics.mean()) if n else float("nan"), "t": t, "pos_share": float((ics > 0).mean()) if n else float("nan"),
            "pooled_ic": pooled, "n_obs": len(g)}


def placebo(P: pd.DataFrame, feat: str, target: str, real_mean_ic: float, draws: int, rng: np.random.Generator) -> float:
    """Percentile of the real mean per-name IC among within-name shuffles of the feature (sign-aware: |IC|)."""
    Q = P[["code", feat, target]].dropna().copy()
    vals = []
    for _ in range(draws):
        Q["shuf"] = Q.groupby("code")[feat].transform(lambda x: rng.permutation(x.to_numpy()))
        vals.append(abs(per_name_ic(Q, "shuf", target).mean()))
    vals = np.array(vals)
    return float((vals < abs(real_mean_ic)).mean() * 100)


def decile_read(P: pd.DataFrame, feat: str, h: int) -> dict:
    Q = P[[feat, "code", f"fwd{h}_ticks", f"fwd{h}_bps", "cost_bps"]].dropna().copy()
    Q["pct"] = Q.groupby("code")[feat].rank(pct=True)
    Q["dec"] = np.minimum((Q["pct"] * 10).astype(int) + 1, 10)
    d = Q.groupby("dec").agg(ticks=(f"fwd{h}_ticks", "mean"), bps=(f"fwd{h}_bps", "mean"), cost=("cost_bps", "mean"), n=("pct", "size"))
    top, bot = d.loc[10], d.loc[1]
    return {"d10_ticks": float(top["ticks"]), "d1_ticks": float(bot["ticks"]), "gap_ticks": float(top["ticks"] - bot["ticks"]),
            "d10_bps": float(top["bps"]), "d1_bps": float(bot["bps"]), "d10_cost_bps": float(top["cost"]), "d10_net_bps": float(top["bps"] - top["cost"]),
            "n_d10": int(top["n"]), "up_share_d10": float((Q.loc[Q["dec"] == 10, f"fwd{h}_ticks"] > 0).mean()),
            "down_share_d1": float((Q.loc[Q["dec"] == 1, f"fwd{h}_ticks"] < 0).mean())}


def auc_score(y: np.ndarray, p: np.ndarray) -> float:
    """Mann-Whitney AUC without sklearn."""
    r = stats.rankdata(p)
    n1 = int(y.sum())
    n0 = len(y) - n1
    if n1 == 0 or n0 == 0:
        return float("nan")
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def lgbm_read(P: pd.DataFrame) -> dict:
    import lightgbm as lgb
    cols = [*FEATURES, "SPRD", "minute_of_day"]
    Q = P[[*cols, "session", "fwd5_ticks", "fwd5_bps", "cost_bps"]].dropna()
    Q = Q[Q["fwd5_ticks"] != 0]
    y = (Q["fwd5_ticks"] > 0).astype(int).to_numpy()
    tr, te = (Q["session"] == 0).to_numpy(), (Q["session"] == 1).to_numpy()
    if tr.sum() < 500 or te.sum() < 500:
        return {"skipped": "too few rows", "n_train": int(tr.sum()), "n_test": int(te.sum())}
    params = {"objective": "binary", "learning_rate": 0.03, "num_leaves": 15, "min_data_in_leaf": 100, "bagging_fraction": 0.8,
              "bagging_freq": 1, "feature_fraction": 0.8, "lambda_l2": 5.0, "seed": SEED, "verbose": -1}
    m = lgb.train(params, lgb.Dataset(Q.loc[tr, cols].to_numpy(), label=y[tr], feature_name=cols), num_boost_round=300)
    p = np.asarray(m.predict(Q.loc[te, cols].to_numpy()))
    auc = auc_score(y[te], p)
    te_df = Q.loc[te].assign(p=p)
    top = te_df[te_df["p"] >= np.quantile(p, 0.9)]
    gain = np.asarray(m.feature_importance(importance_type="gain"), dtype=float)
    imp = dict(zip(cols, (gain / gain.sum()).round(3).tolist(), strict=True))
    return {"n_train": int(tr.sum()), "n_test": int(te.sum()), "auc": auc, "base_up_rate": float(y[te].mean()),
            "top10_up_share": float((top["fwd5_ticks"] > 0).mean()), "top10_bps": float(top["fwd5_bps"].mean()),
            "top10_cost_bps": float(top["cost_bps"].mean()), "top10_net_bps": float((top["fwd5_bps"] - top["cost_bps"]).mean()),
            "importance": imp}


# -------------------------------------------------------------------------------------------------------------- report
def fmt(x, d=3):
    return "-" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.{d}f}"


def run(dsn: str, day: date, out_path: str, store: bool, study_name: str) -> dict:
    rng = np.random.default_rng(SEED)
    book, bars = load(dsn, day)
    P = build_panel(book, bars, day)
    halves = {"all": P, "morning": P[P["session"] == 0], "afternoon": P[P["session"] == 1]}
    desc = {"day": day.isoformat(), "names": int(P["code"].nunique()), "name_minutes": len(P),
            "book_rows": len(book), "bar_rows": len(bars),
            "median_spread_bps": float(P["SPRD"].median() * 1e4), "median_cost_bps": float(P["cost_bps"].median()),
            "share_fwd5_zero": float((P["fwd5_ticks"] == 0).mean()), "mean_abs_fwd5_ticks": float(P["fwd5_ticks"].abs().mean())}
    res: dict = {"desc": desc, "ic": {}, "placebo": {}, "deciles": {}, "verdict": {}}
    for f in [*FEATURES, "SPRD"]:
        res["ic"][f] = {h: {k: ic_read(v, f, f"fwd{h}_ticks") for k, v in halves.items()} for h in HORIZONS}
        res["deciles"][f] = {h: {k: decile_read(v, f, h) for k, v in halves.items()} for h in (5, 15)}
        res["placebo"][f] = placebo(P, f, "fwd5_ticks", res["ic"][f][5]["all"]["mean_ic"], PLACEBO_DRAWS, rng) if f in FEATURES else None
    for f in FEATURES:
        m, a = res["ic"][f][5]["morning"], res["ic"][f][5]["afternoon"]
        lead = abs(m["t"]) >= 3 and abs(a["t"]) >= 3 and np.sign(m["t"]) == np.sign(a["t"]) and res["placebo"][f] >= 99
        d5, d15 = res["deciles"][f][5]["all"], res["deciles"][f][15]["all"]
        tradeable = d5["d10_net_bps"] > 0 or d15["d10_net_bps"] > 0
        gm, ga = res["deciles"][f][5]["morning"]["gap_ticks"], res["deciles"][f][5]["afternoon"]["gap_ticks"]
        exec_ok = abs(d5["gap_ticks"]) >= 0.25 and np.sign(gm) == np.sign(ga) and np.sign(gm) == np.sign(d5["gap_ticks"])
        res["verdict"][f] = {"LEAD": bool(lead), "TRADEABLE": bool(tradeable), "EXEC_TIMING": bool(exec_ok)}
    res["lgbm"] = lgbm_read(P)
    res["verdict"]["LGBM"] = {"informative": bool(res["lgbm"].get("auc", 0) >= 0.55), "TRADEABLE": bool(res["lgbm"].get("top10_net_bps", -1) > 0)}
    write_report(res, out_path)
    if store:
        from blackheart_ingest.idx import research_store as rs
        with psycopg.connect(dsn) as conn:
            sid = rs.record_study(conn, study_name, day, params={"trials": TRIALS, "n_trials_cumulative": N_TRIALS_BEFORE + len(TRIALS) + 1,
                                                                 "horizons": HORIZONS, "placebo_draws": PLACEBO_DRAWS, "seed": SEED, "fee_bps": FEE_BPS},
                                 summary=json.loads(json.dumps(res, default=str)), names=[], report_path=out_path,
                                 note="; ".join(f"{f}: " + ",".join(k for k, v in vd.items() if v) for f, vd in res["verdict"].items()) or "no bar cleared")
            res["study_id"] = sid
    return res


def write_report(res: dict, path: str) -> None:
    d = res["desc"]
    L = [f"# IDX menu 28 — microstructure, preliminary (one session: {d['day']})", "",
         "Question: does the order book / the tape at minute t predict the MID price h minutes later? Two bars: standalone (net of spread + fees) and",
         "execution timing (sign only, for trades the desk makes anyway). Pre-registered in `research/idx_microstructure_prelim.py`; 7 trials (cumulative 510).",
         "", "## Data", "",
         f"- {d['names']} names, {d['name_minutes']:,} name-minutes inside the continuous phases; {d['book_rows']:,} book-minutes, {d['bar_rows']:,} bar-minutes",
         f"- median quoted spread {d['median_spread_bps']:.1f} bps; median taker round-trip cost (spread + 30 bps fees) {d['median_cost_bps']:.1f} bps",
         f"- 5-minute mid move: exactly zero in {d['share_fwd5_zero']*100:.0f} % of minutes; mean |move| {d['mean_abs_fwd5_ticks']:.2f} ticks",
         "", "## Information coefficients (Spearman per name, then mean and t across names; target = forward mid move in ticks)", "",
         "| feature | h | all: mean IC / t / n | pooled IC | morning t | afternoon t | placebo pct |", "|---|---|---|---|---|---|---|"]
    for f in [*FEATURES, "SPRD"]:
        for h in HORIZONS:
            a, m, p = res["ic"][f][h]["all"], res["ic"][f][h]["morning"], res["ic"][f][h]["afternoon"]
            pl = res["placebo"][f] if h == 5 and res["placebo"][f] is not None else None
            L.append(f"| {f} | {h} | {fmt(a['mean_ic'])} / {fmt(a['t'],1)} / {a['n_names']} | {fmt(a['pooled_ic'])} | {fmt(m['t'],1)} | {fmt(p['t'],1)} | "
                     f"{fmt(pl,0) if pl is not None else '-'} |")
    L += ["", "## Deciles (within-name percentile of the feature; D10 = top, D1 = bottom; forward mid move)", "",
          "| feature | h | D10 ticks | D1 ticks | gap | D10 up-share | D1 down-share | D10 bps | D10 cost bps | D10 net bps |", "|---|---|---|---|---|---|---|---|---|---|"]
    for f in [*FEATURES, "SPRD"]:
        for h in (5, 15):
            q = res["deciles"][f][h]["all"]
            L.append(f"| {f} | {h} | {fmt(q['d10_ticks'],2)} | {fmt(q['d1_ticks'],2)} | {fmt(q['gap_ticks'],2)} | {fmt(q['up_share_d10'],2)} | {fmt(q['down_share_d1'],2)} | "
                     f"{fmt(q['d10_bps'],1)} | {fmt(q['d10_cost_bps'],1)} | {fmt(q['d10_net_bps'],1)} |")
    g = res["lgbm"]
    L += ["", "## Trial 7 — LightGBM, sign of the 5-minute mid move, train morning -> test afternoon", ""]
    if "skipped" in g:
        L.append(f"- skipped: {g['skipped']}")
    else:
        L += [f"- train {g['n_train']:,} / test {g['n_test']:,} minutes (zero moves dropped); base up-rate {g['base_up_rate']:.3f}",
              f"- **AUC {g['auc']:.3f}**; top-10 % predicted-up minutes: up-share {g['top10_up_share']:.3f}, realised {g['top10_bps']:+.1f} bps vs cost {g['top10_cost_bps']:.1f} bps -> net {g['top10_net_bps']:+.1f} bps",
              f"- importance: {g['importance']}"]
    L += ["", "## Verdicts (pre-registered bars)", "", "| trial | LEAD (both halves |t|>=3, placebo>=99) | TRADEABLE (D10 net > 0) | EXEC-TIMING (gap >= 0.25 tick, same sign) |", "|---|---|---|---|"]
    for f in FEATURES:
        v = res["verdict"][f]
        L.append(f"| {f} | {'YES' if v['LEAD'] else 'no'} | {'YES' if v['TRADEABLE'] else 'no'} | {'YES' if v['EXEC_TIMING'] else 'no'} |")
    v = res["verdict"]["LGBM"]
    L.append(f"| LGBM | informative: {'YES' if v['informative'] else 'no'} | {'YES' if v['TRADEABLE'] else 'no'} | - |")
    L += ["", "## Reading", "",
          "- One session. Nothing here is adoptable; a LEAD here only earns menu 28b (the same reads over >= 20 sessions, halves replaced by a day split).",
          "- TRADEABLE compares the mean forward move of the top decile with the taker's own cost at those minutes; a positive net would mean a",
          "  standalone microstructure trade pays after the spread and fees. A negative net with a strong IC = information that is real but priced",
          "  inside the spread — usable only for timing trades the desk makes anyway (EXEC-TIMING).",
          "- The mid is used throughout so bid-ask bounce cannot manufacture reversal.",
          ""]
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(L))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default="2026-09-22")
    ap.add_argument("--no-store", action="store_true")
    ap.add_argument("--out", default="")
    ap.add_argument("--study-name", default="microstructure_prelim")
    a = ap.parse_args()
    day = date.fromisoformat(a.day)
    out = a.out or os.path.join(HERE, f"IDX_MICROSTRUCTURE_PRELIM_{day.isoformat()}.md")
    res = run(os.environ["INGEST_DB_DSN"], day, out, not a.no_store, a.study_name)
    print(json.dumps({"desc": res["desc"], "verdict": res["verdict"], "lgbm_auc": res["lgbm"].get("auc"), "study_id": res.get("study_id"), "report": out},
                     indent=1, default=str))


if __name__ == "__main__":
    main()
