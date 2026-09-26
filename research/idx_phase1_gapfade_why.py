#!/usr/bin/env python3
"""Phase 1, item 4 - WHY does the gap-down fade pay, and is it a 2025 regime? (operator 2026-09-26: "oke jalankan fase 1")

The deployed gap-fade sleeve earned ~all its money in 2025-26 (#167, #348); 2021-23 lost in the g7/g10 arms (menu 29b). A fade
that pays for a structural reason (liquidity provision to forced sellers) should pay wherever forced selling shows up; one that
pays because 2025 was a panic year should live on market-wide panic days only.

Descriptive, declared before any result was seen (2026-09-26). No rule is chosen here and nothing is deployed (no trial).
  EVENTS the gap-fade trades of the deployed book (#348, strategy gapfade: open <= -7 %, main board, v60 >= Rp 5 bn, <= 5/day,
         bought at the open + tick, sold at the close - tick, fees in). Return = pnl / cost.
  SPLITS (each known before the open of the event day):
         market    COMPOSITE's own open gap that morning <= -1 % ("panic open") vs not; and COMPOSITE's previous-day return
                   <= -2 % vs not
         breadth   events on the same morning: 1 | 2-3 | 4+ (clustered = market-wide selling)
         name      previous-day return <= -10 % (already crashing) vs not; foreign net sell the previous day > 20 % of its volume
                   vs not; an exchange announcement for the name in the 3 calendar days before (news gap) vs none
                   (announcements are stored from 2023-07 only; earlier events are 'unknown')
         period    2022-24 vs 2025-26
  READ   mean / median return, hit rate, n per bucket, and each bucket split by period. A bucket with n < 15 is shown, not read.
READ-ONLY; one idx.study row (phase1_gapfade_why, kind audit).
"""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta

import numpy as np
import pandas as pd
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blackheart-ingest", "src"))
import idx_alloc_frontier as AF  # noqa: E402
from blackheart_ingest.idx import research_store as rs  # noqa: E402
from blackheart_ingest.idx.ml import common  # noqa: E402

STUDY = "phase1_gapfade_why"
MIN_N = 15


def main() -> int:
    store = "--no-store" not in sys.argv
    dsn = AF.dsn()
    with psycopg.connect(dsn) as conn:
        E = pd.read_sql("SELECT code, d_in AS d, pnl / cost AS r FROM idx.strategy_backtest_trade WHERE study_id = 348 AND strategy = 'gapfade'", conn)
        E["d"] = pd.to_datetime(E["d"])
        comp = pd.read_sql("SELECT trade_date AS d, previous, open, close FROM idx.index_daily WHERE index_code = 'COMPOSITE' AND trade_date >= '2021-12-01' ORDER BY 1", conn)
        codes = sorted(E["code"].unique())
        ds = pd.read_sql("""SELECT code, trade_date AS d, previous, close, value, volume, foreign_buy, foreign_sell FROM idx.daily_summary
                            WHERE code = ANY(%s) AND trade_date >= '2021-12-01'""", conn, params=(codes,))
        ann = pd.read_sql("SELECT code, (published_at AT TIME ZONE 'Asia/Jakarta')::date AS d FROM idx.announcement WHERE code = ANY(%s)", conn, params=(codes,))
    E["r"] = E["r"].astype(float)
    comp["d"] = pd.to_datetime(comp["d"])
    comp = comp.set_index("d").astype(float)
    comp["open_gap"] = comp["open"] / comp["previous"] - 1
    comp["prev_ret"] = (comp["close"] / comp["previous"] - 1).shift(1)
    ds["d"] = pd.to_datetime(ds["d"])
    for c in ("previous", "close", "value", "volume", "foreign_buy", "foreign_sell"):
        ds[c] = ds[c].astype(float)
    ds = ds.sort_values(["code", "d"])
    ds["ret"] = ds["close"] / ds["previous"] - 1
    ds["fnet"] = (ds["foreign_sell"] - ds["foreign_buy"]) / ds["volume"].where(ds["volume"] > 0)     # foreign_* are shares
    ds["prev_ret"] = ds.groupby("code")["ret"].shift(1)
    ds["prev_fnet"] = ds.groupby("code")["fnet"].shift(1)
    E = E.merge(ds[["code", "d", "prev_ret", "prev_fnet"]], on=["code", "d"], how="left")
    E = E.join(comp[["open_gap", "prev_ret"]].rename(columns={"prev_ret": "mkt_prev"}), on="d")
    E["n_same_day"] = E.groupby("d")["code"].transform("count")
    ann["d"] = pd.to_datetime(ann["d"])
    A = set(zip(ann["code"], ann["d"], strict=True))
    first_ann = ann["d"].min()

    def news(row) -> str:
        if row["d"] < first_ann + pd.Timedelta(days=3):
            return "unknown"
        return "news" if any((row["code"], row["d"] - pd.Timedelta(days=k)) in A for k in range(0, 4)) else "no news"
    E["news"] = E.apply(news, axis=1)
    E["period"] = np.where(E["d"].dt.year >= 2025, "2025-26", "2022-24")
    splits = {
        "panic open (COMPOSITE open <= -1 %)": np.where(E["open_gap"] <= -0.01, "panic open", "normal open"),
        "COMPOSITE previous day <= -2 %": np.where(E["mkt_prev"] <= -0.02, "market fell", "market ok"),
        "events the same morning": pd.cut(E["n_same_day"], [0, 1, 3, 99], labels=["1", "2-3", "4+"]).astype(str),
        "name fell <= -10 % the day before": np.where(E["prev_ret"] <= -0.10, "already crashing", "fresh gap"),
        "foreign net sell > 20 % of volume the day before": np.where(E["prev_fnet"] > 0.20, "foreign dumping", "no"),
        "exchange announcement in the 3 days before": E["news"].to_numpy(),
    }

    def agg(x: pd.Series) -> dict:
        return {"n": int(len(x)), "mean": float(x.mean()), "median": float(x.median()), "hit": float((x > 0).mean())}
    res = {"all": agg(E["r"]), "by_period": {p: agg(g["r"]) for p, g in E.groupby("period")}, "splits": {}}
    L = [f"# Phase 1 - why the gap-down fade pays - {date.today()}", "",
         f"Deployed gap-fade trades of #348 ({len(E)}, {E['d'].min().date()} -> {E['d'].max().date()}), return per trade after fees. Descriptive audit, no trial.",
         f"Buckets with n < {MIN_N} are shown but not read.", "",
         f"All: n {len(E)}, mean {E['r'].mean() * 100:+.2f} %, median {E['r'].median() * 100:+.2f} %, hit {(E['r'] > 0).mean() * 100:.0f} %. "
         + "; ".join(f"{p}: n {v['n']} mean {v['mean'] * 100:+.2f} %" for p, v in res["by_period"].items()), ""]
    for title, lab in splits.items():
        E["_b"] = lab
        L += [f"## {title}", "", "| bucket | n | mean | median | hit | 2022-24 n / mean | 2025-26 n / mean |", "|---|---|---|---|---|---|---|"]
        res["splits"][title] = {}
        for b, g in E.groupby("_b"):
            a = agg(g["r"])
            pp = {p: agg(h["r"]) for p, h in g.groupby("period")}
            res["splits"][title][str(b)] = {**a, "by_period": pp}
            cell = lambda p: f"{pp[p]['n']} / {pp[p]['mean'] * 100:+.2f} %" if p in pp else "0"  # noqa: E731
            flag = "" if a["n"] >= MIN_N else " (thin)"
            L.append(f"| {b}{flag} | {a['n']} | {a['mean'] * 100:+.2f} % | {a['median'] * 100:+.2f} % | {a['hit'] * 100:.0f} % | {cell('2022-24')} | {cell('2025-26')} |")
        L.append("")
    text = "\n".join(L)
    print(text)
    out = os.path.join(HERE, f"IDX_PHASE1_GAPFADE_WHY_{date.today()}.md")
    if store:
        open(out, "w", encoding="utf-8").write(text + "\n")
        with psycopg.connect(dsn) as conn:
            sid = rs.record_study(conn, STUDY, date.today(), params={"trials": [], "kind": "audit", "sources": [348, 166]},
                                  summary=common.plain(res), names=[], report_path=out, note="Phase 1: where the gap-fade return comes from; descriptive, no trial")
            conn.commit()
        print(f"study #{sid} stored")
    return 0


if __name__ == "__main__":
    sys.exit(main())
