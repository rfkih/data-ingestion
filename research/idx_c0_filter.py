#!/usr/bin/env python3
"""IDX menu FL-1 - which radar (C0) names are worth buying: earnings and news filters on the wide sleeve (operator 2026-09-27:
"filter lagi saham mana yang layak dibeli ... perhatikan sentiment/beritanya, berpotensi meningkatkan laba atau hanya noise").

Data limits (checked first): announcement TEXT is not stored (titles / kinds only, 2023-07-03 on); idx.news_article covers one
month. So "news that raises earnings" is measured two ways that exist historically: (1) the REPORTED earnings the market could
see before the entry (financial reports published before the entry day, 2020 on); (2) the KIND of the issuer's recent
disclosures - substantive (material information, affiliated / material transactions, corporate actions, change of control,
public expose) versus attention-only (the reply to an exchange query, a clarification of media reports) - 2023-07 on.
Prior on (1): menu 35 (#181) found a loss-maker veto HURT the trend sleeve (vetoed trades won more) - momentum rockets are often
turnarounds; the doubler study (#2) found turnaround the best doubling profile. The test says which way C0 goes.

BASE: the RB-2 wide sleeve's trades (research/idx_c0_wide.py): every C0 flag in U1, one position per name, stop -15 % / trail 25 %,
entries 2022-01 on; book = its rupiah replay (Rp 20 m, 1.25 % per position, <= 40 open).
PRE-REGISTERED FILTERS (4 trials; cumulative 1093 + 4 = 1097) - each KEEPS a subset of the base trades:
  K1 EARN_UP     the latest profit (attributable to the parent, year-to-date) published before the entry is >= 30 % above the same
                 period a year earlier, or turned from a loss to a profit
  K2 NO_LOSS     drop names whose latest published year-to-date profit is negative
  K3 SUBSTANCE   (2023-07 on) keep names with a substantive disclosure in the 60 sessions before the entry
  K4 NO_NOISE    (2023-07 on) drop names with an exchange-query reply or media clarification in the 20 sessions before the entry and
                 no substantive disclosure in the 60
READING RULE - a filter is USEFUL only if ALL: kept-minus-dropped mean net per trade > 0 with Welch t >= 2; the filtered book's
Sharpe > the unfiltered book's at every start in its window (K1/K2: 2022-01-03, 2022-07-01, 2023-01-02, 2023-07-03; K3/K4:
2023-07-03 and 2024-01-02); the filtered book's mDD no more than 5 points deeper. Reported: kept share, touch-2x share, stop share.
READ-ONLY on the DB except one idx.study row (--no-store to skip).
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
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import idx_c0_wide as W  # noqa: E402
import idx_exit as E  # noqa: E402
import idx_radar_book as RB  # noqa: E402
import idx_swing2 as S  # noqa: E402
import idx_trend_c0 as T  # noqa: E402

STUDY, N_BEFORE = "c0_filter", 1093
SUBSTANCE = ("material_info", "affiliated_tx", "corporate_action", "control_change", "public_expose")
NOISE = ("exchange_query", "media_clarification")


def earnings_table(conn):
    rows = conn.execute("""SELECT r.code, r.published_at, f.period_start, f.period_end, f.value
                             FROM idx.financial_fact f JOIN idx.financial_report r ON r.id = f.report_id
                            WHERE f.concept = 'Profit (loss) attributable to parent entity' AND f.period_start IS NOT NULL
                              AND r.published_at IS NOT NULL""").fetchall()
    df = pd.DataFrame(rows, columns=["code", "pub", "ps", "pe", "v"]).dropna()
    df["v"] = df.v.astype(float)
    df["pub"] = pd.to_datetime(df.pub, utc=True).dt.tz_convert(None)
    df = df.sort_values("pub").drop_duplicates(["code", "ps", "pe"], keep="first")
    key = {(r.code, r.ps, r.pe): r.v for r in df.itertuples()}
    out = {}
    for r in df.itertuples():                                            # each report's own period: its latest (max pe) row
        prev = key.get((r.code, r.ps.replace(year=r.ps.year - 1), r.pe.replace(year=r.pe.year - 1)))
        out.setdefault(r.code, []).append((r.pub, r.pe, r.v, prev))
    return {c: sorted(v, key=lambda x: (x[0], x[1])) for c, v in out.items()}


def state_at(tab, code, when):
    rows = [x for x in tab.get(code, []) if x[0] < when]
    if not rows:
        return None
    pub, pe, v, prev = max(rows, key=lambda x: x[1])
    return dict(v=v, prev=prev, up=(prev is not None and ((prev <= 0 < v) or (prev > 0 and v >= 1.3 * prev))), loss=v < 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-store", action="store_true")
    a = ap.parse_args()
    P, unis, comp, Hp, Lp = E.load_all(T.dsn(), T.CACHE, board="pit")
    c_in, c_out = S.costs(P)
    dates, cols = P["adj"].index, P["adj"].columns
    A, raw = P["adj"].to_numpy(float), P["close"].to_numpy(float)
    arms, vr, c0_entry, u1, tier = RB.masks(P, unis, comp)
    value = P["close"] * P["volume"]
    attn = (value.rolling(20, min_periods=15).mean() / value.rolling(250, min_periods=200).mean()).to_numpy(float)
    t_first = int(np.searchsorted(dates, np.datetime64(pd.Timestamp(W.STARTS[0])))) - 1
    base = W.all_trades(A, raw, c_in, c0_entry & u1, attn, t0=t_first)
    with psycopg.connect(T.dsn()) as conn:
        tab = earnings_table(conn)
        ann = pd.DataFrame(conn.execute("SELECT code, published_at::date, kind FROM idx.announcement WHERE kind = ANY(%s)",
                                        (list(SUBSTANCE + NOISE),)).fetchall(), columns=["code", "d", "kind"])
    ann["d"] = pd.to_datetime(ann.d)
    ann_by = {c: g for c, g in ann.groupby("code")}
    rows = []
    for e, j, x, s in base:
        code, d_in = cols[j], dates[e]
        co = c_out[x, j] if np.isfinite(c_out[x, j]) else 0.004
        net = (A[x, j] / A[e, j]) * (1 - co) / (1 + c_in[e, j]) - 1
        seg = A[e:min(e + 251, len(A)), j]
        seg = seg[~np.isnan(seg)]
        st = state_at(tab, code, d_in)
        g = ann_by.get(code)
        sub60 = noise20 = False
        if g is not None:
            lo60, lo20 = dates[max(0, e - 61)], dates[max(0, e - 21)]
            win = g[(g.d > lo60) & (g.d < d_in)]
            sub60 = bool(win.kind.isin(SUBSTANCE).any())
            noise20 = bool(win[(win.d > lo20)].kind.isin(NOISE).any())
        rows.append(dict(e=e, j=j, x=x, s=s, code=code, d=d_in, net=net, touch2x=bool(len(seg) and seg.max() / A[e, j] >= 2),
                         stop=bool(A[x - 1, j] <= 0.85 * A[e, j]) if x - 1 > e else False,
                         has_fin=st is not None, up=bool(st and st["up"]), loss=bool(st and st["loss"]), sub60=sub60, noise20=noise20))
    df = pd.DataFrame(rows)
    ann_start = pd.Timestamp("2023-07-03")
    filt = {"K1_EARN_UP": (df.up, W.STARTS),
            "K2_NO_LOSS": (~df.loss, W.STARTS),
            "K3_SUBSTANCE": (df.sub60 | (df.d < ann_start), ["2023-07-03", "2024-01-02"]),
            "K4_NO_NOISE": (~(df.noise20 & ~df.sub60) | (df.d < ann_start), ["2023-07-03", "2024-01-02"])}
    print(f"base trades {len(df)}; with a published report {df.has_fin.mean():.0%}; earnings up {df.up.mean():.0%}; loss-making {df.loss.mean():.0%}; "
          f"(2023-07+) substantive 60d {df[df.d >= ann_start].sub60.mean():.0%}, noise 20d {df[df.d >= ann_start].noise20.mean():.0%}", flush=True)
    res = {}
    for name, (keep, starts) in filt.items():
        scope = df.d >= (ann_start if name.startswith(("K3", "K4")) else pd.Timestamp("2022-01-01"))
        k, d = df[keep & scope], df[~keep & scope]
        t = stats.ttest_ind(k.net, d.net, equal_var=False).statistic if len(k) > 2 and len(d) > 2 else np.nan
        books = {}
        for st_ in starts:
            full = W.replay(base, P, st_, 20e6, W.PCT_W, W.MAXPOS_W)
            kept_tr = [(r.e, r.j, r.x, r.s) for r in df[keep].itertuples()]
            fb = W.replay(kept_tr, P, st_, 20e6, W.PCT_W, W.MAXPOS_W)
            books[st_] = dict(filtered=dict(cagr=fb["cagr"], sharpe=fb["sharpe"], mdd=fb["mdd"]), base=dict(cagr=full["cagr"], sharpe=full["sharpe"], mdd=full["mdd"]))
        chk = dict(diff_t=bool(k.net.mean() > d.net.mean() and t >= 2),
                   sharpe=all(v["filtered"]["sharpe"] > v["base"]["sharpe"] for v in books.values()),
                   mdd=all(v["filtered"]["mdd"] >= v["base"]["mdd"] - 0.05 for v in books.values()))
        res[name] = dict(kept=len(k), dropped=len(d), kept_mean=k.net.mean(), dropped_mean=d.net.mean(), t=t,
                         kept_median=k.net.median(), dropped_median=d.net.median(), kept_2x=k.touch2x.mean(), dropped_2x=d.touch2x.mean(),
                         kept_stop=k.stop.mean(), dropped_stop=d.stop.mean(), books=books, checks=chk, useful=all(chk.values()))
        print(f"{name}: kept {len(k)} mean {k.net.mean() * 100:+.1f}% med {k.net.median() * 100:+.1f}% 2x {k.touch2x.mean():.0%} stop {k.stop.mean():.0%} | "
              f"dropped {len(d)} mean {d.net.mean() * 100:+.1f}% med {d.net.median() * 100:+.1f}% 2x {d.touch2x.mean():.0%} stop {d.stop.mean():.0%} | t {t:.2f}", flush=True)
        for st_, v in books.items():
            print(f"    from {st_}: filtered Sh {v['filtered']['sharpe']:.2f} CAGR {v['filtered']['cagr'] * 100:.1f}% mDD {v['filtered']['mdd'] * 100:.0f}% | "
                  f"base Sh {v['base']['sharpe']:.2f} CAGR {v['base']['cagr'] * 100:.1f}% mDD {v['base']['mdd'] * 100:.0f}%", flush=True)
        print("   ", chk, "USEFUL" if all(chk.values()) else "no", flush=True)
    json.dump(res, open(os.path.join(HERE, "IDX_C0_FILTER_2026-09-27.json"), "w"), indent=1, default=str)
    if not a.no_store:
        from blackheart_ingest.idx import research_store as rs
        with psycopg.connect(T.dsn()) as conn:
            sid = rs.record_study(conn, STUDY, date.today(), params={"trials": list(filt), "n_trials_cumulative": N_BEFORE + len(filt)},
                                  summary=res, names=[], report_path="research/IDX_C0_FILTER_2026-09-27.md")
            print("study id", sid)


if __name__ == "__main__":
    main()
