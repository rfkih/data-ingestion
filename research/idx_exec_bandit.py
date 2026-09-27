#!/usr/bin/env python3
"""Execution learning: a contextual bandit that chooses HOW to place a buy, on the recorded order book (operator 2026-09-27:
"you can try for the order execution, or both order execution and exit and compare").

Why execution and not exits: in the #386 trades the spread and ticks paid per round trip are 1.11 % for the gap-fade (54 % of
its +2.07 % edge), 0.65 % for ML (10 %), 0.56 % for trend (12 %); the learned exit (#396) found +0.10 %/trade at t 0.14. What a
better order placement can recover is bounded by that spread - and menus 28b-0/28b-1 (#75, #100) showed passive orders get
filled mostly when the price falls through them (adverse selection).

DATA  idx.feed_book / idx.feed_trade (the tick feed from 2026-09-21; 10-second grid of menu 31, research/idx_lob_ml.py).
EVENTS a small buy (it never moves the book) in every recorded name at the first grid step at or after 09:05, 10:00, 11:00, 14:00
       and 15:00 of each session.
POLICIES  CROSS   buy at the best offer now (what the desk does today; the benchmark)
          JOIN5   post at the best bid; filled at the bid when printed volume at <= that price after posting exceeds the queue
                  ahead (bid size at posting, menu 28b-1's queue rule); not filled in 5 min -> buy at the offer then
          JOIN15  the same with 15 min
          TIGHT5  buy at the offer at the first step within 5 min where the spread is one tick; else at 5 min
COST   bps paid over the MID at the decision: (fill / mid_t - 1) x 1e4 - the spread paid plus the drift while waiting (adverse
       selection shows up here). Fees are the same for every policy and left out.
LEARNERS (walk-forward by session: trained on earlier sessions only, scored on the next)
          P_ctx  one small LightGBM regressor per policy (7 leaves, 100 rounds, min 50 rows) predicting its cost from the book at the
                 decision (spread in ticks, OBI1, OBI5, RET5, 15-min realised volatility, distance from the day high, market return,
                 hour); choose the cheapest prediction
          P_best the policy with the lowest mean cost on the earlier sessions
          ORACLE the cheapest policy per event in hindsight - the ceiling, not a strategy
PRE-REGISTERED 2026-09-27: JUDGED ONLY ONCE >= 20 SESSIONS ARE RECORDED (about 2026-10-19; 2 trials then: P_ctx, P_best).
       PASS: mean cost below CROSS by >= 5 bps with t >= 2.0 over the test SESSIONS (session means as the unit), lower in both
       halves of the test sessions. Before 20 sessions this script runs as a SMOKE (--smoke): numbers are shown, never read.
READ-ONLY; stores an idx.study row only when judged (>= 20 sessions and not --smoke).
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime, time

import numpy as np
import pandas as pd
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blackheart-ingest", "src"))
import idx_alloc_frontier as AF  # noqa: E402
import idx_lob_ml as LB  # noqa: E402
import idx_maker_cancel as MC  # noqa: E402
from blackheart_ingest.idx import research_store as rs  # noqa: E402
from blackheart_ingest.idx.ml import common  # noqa: E402

STUDY = "exec_bandit"
N_BEFORE = 1027
MIN_SESSIONS = 20
DECIDE = [time(9, 5), time(10, 0), time(11, 0), time(14, 0), time(15, 0)]
POLICIES = ["CROSS", "JOIN5", "JOIN15", "TIGHT5"]
STEPS = {"JOIN5": 30, "JOIN15": 90, "TIGHT5": 30}
FEATS = ["sprd_t", "OBI1", "OBI5", "RET5", "rvol15", "dist_hi", "MKT_RET", "hour"]
LGB = {"objective": "regression", "num_leaves": 7, "learning_rate": 0.05, "min_data_in_leaf": 50, "verbose": -1, "seed": 20260927}
ROUNDS = 100


def sessions(conn: psycopg.Connection) -> list[date]:
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT (ts AT TIME ZONE 'Asia/Jakarta')::date FROM idx.feed_book ORDER BY 1")
        return [r[0] if not isinstance(r, dict) else list(r.values())[0] for r in cur.fetchall()]


def events_for(x: dict, prints: tuple | None, day: date) -> list[dict]:
    """Pure-ish. One name-day grid -> the decision events with the cost of each policy."""
    t = pd.to_datetime(x["t"])
    sess, mid, bid, off, tick = x["session"], x["mid"], x["bid1"], x["off1"], x["tick"]
    ahead_all = x["raw"][:, 1]
    F = x["F"]
    tgrid = t.astype("int64").to_numpy()
    out = []
    for tt in DECIDE:
        at = pd.Timestamp(datetime.combine(day, tt))
        j = int(np.searchsorted(t, at))
        if j >= len(t) or (t[j] - at) > pd.Timedelta(minutes=2):
            continue
        s_ix = np.flatnonzero(sess == sess[j])
        last = int(s_ix[-1])
        m0 = mid[j]
        ev = {"t": t[j], "hour": tt.hour + tt.minute / 60, **{f: float(F.iloc[j][f]) if f in F.columns else np.nan for f in FEATS if f != "hour"}}
        ev["c_CROSS"] = (off[j] / m0 - 1) * 1e4
        for p in ("JOIN5", "JOIN15"):
            jn = min(j + STEPS[p], last)
            L = bid[j]
            filled = False
            if prints is not None and jn > j:
                vol = MC.per_step_le(prints, tgrid, L, j + 1, jn)
                filled = bool(vol.cumsum()[-1] >= ahead_all[j]) if len(vol) else False
            ev[f"c_{p}"] = ((L if filled else off[jn]) / m0 - 1) * 1e4
            ev[f"fill_{p}"] = filled
        jn = min(j + STEPS["TIGHT5"], last)
        k = next((i for i in range(j, jn + 1) if off[i] - bid[i] <= tick[i] * 1.01), jn)
        ev["c_TIGHT5"] = (off[k] / m0 - 1) * 1e4
        out.append(ev)
    return out


def main() -> int:
    smoke = "--smoke" in sys.argv
    store = "--no-store" not in sys.argv and not smoke
    dsn = AF.dsn()
    rows = []
    with psycopg.connect(dsn) as conn:
        days = sessions(conn)
        for day in days:
            built = LB.build_day(conn, day)
            prints = MC.load_prints(conn, day)
            for code, x in built.items():
                for ev in events_for(x, prints.get(code), day):
                    rows.append({"day": day, "code": code, **ev})
            print(f"{day}: {len(built)} names, {sum(1 for r in rows if r['day'] == day)} events", flush=True)
    E = pd.DataFrame(rows)
    n_sess = E["day"].nunique()
    judged = n_sess >= MIN_SESSIONS and not smoke
    import lightgbm as lgb
    E["P_ctx"], E["P_best"] = None, None
    for d in sorted(E["day"].unique())[1:]:
        tr, te = E[E["day"] < d], E["day"] == d
        E.loc[te, "P_best"] = min(POLICIES, key=lambda p: tr[f"c_{p}"].mean())
        pred = {}
        for p in POLICIES:
            ok = tr[f"c_{p}"].notna()
            mdl = lgb.train(LGB, lgb.Dataset(tr.loc[ok, FEATS].to_numpy(float), tr.loc[ok, f"c_{p}"].to_numpy(float)), num_boost_round=ROUNDS)
            pred[p] = mdl.predict(E.loc[te, FEATS].to_numpy(float))
        E.loc[te, "P_ctx"] = np.array(POLICIES)[np.argmin(np.column_stack([pred[p] for p in POLICIES]), axis=1)]
    T = E[E["P_ctx"].notna()].copy()
    for lab in ("P_ctx", "P_best"):
        T[f"c_{lab}"] = [T.loc[i, f"c_{T.loc[i, lab]}"] for i in T.index]
    T["c_ORACLE"] = T[[f"c_{p}" for p in POLICIES]].min(axis=1)
    per_day = T.groupby("day")[[f"c_{p}" for p in (*POLICIES, "P_ctx", "P_best", "ORACLE")]].mean()
    res: dict = {"sessions": int(n_sess), "test_sessions": int(per_day.shape[0]), "events": int(len(E)), "test_events": int(len(T)),
                 "mean_cost_bps": {k[2:]: float(T[k].mean()) for k in per_day.columns},
                 "fill_rate": {p: float(E[f"fill_{p}"].mean()) for p in ("JOIN5", "JOIN15")}, "judged": judged, "learners": {}}
    for lab in ("P_ctx", "P_best"):
        d = per_day["c_CROSS"] - per_day[f"c_{lab}"]                      # positive = cheaper than CROSS
        t = float(d.mean() / (d.std(ddof=1) / np.sqrt(len(d)))) if len(d) > 1 and d.std(ddof=1) > 0 else None
        half = len(d) // 2
        res["learners"][lab] = {"saving_bps": float(d.mean()), "t": t, "h1": float(d.iloc[:half].mean()) if half else None,
                                "h2": float(d.iloc[half:].mean()),
                                "passed": bool(judged and d.mean() >= 5 and (t or 0) >= 2 and half and d.iloc[:half].mean() > 0 and d.iloc[half:].mean() > 0),
                                "choice": T[lab].value_counts(normalize=True).round(3).to_dict()}
    banner = (f"**SMOKE - NOT EVIDENCE.** {n_sess} recorded sessions; the pre-registered read needs {MIN_SESSIONS}." if not judged else
              f"Judged on {n_sess} sessions ({N_BEFORE} + 2 trials = {N_BEFORE + 2}).")
    L = [f"# Execution learning on the recorded order book - {date.today()}", "", banner, "",
         f"{len(E):,} small-buy decisions in {E['code'].nunique()} names; {len(T):,} scored out of sample (walk-forward by session). Cost = bps over the",
         "mid at the decision, spread and waiting drift included, fees excluded (the same for every policy).", "",
         "| policy | mean cost (bps) |", "|---|---|"]
    for k, v in res["mean_cost_bps"].items():
        L.append(f"| {k} | {v:+.1f} |")
    L += ["", f"Passive fill rates: JOIN5 {res['fill_rate']['JOIN5'] * 100:.0f} %, JOIN15 {res['fill_rate']['JOIN15'] * 100:.0f} %.", "",
          "| learner | saving vs CROSS (bps) | t (sessions) | 1st half | 2nd half | choices | pass |", "|---|---|---|---|---|---|---|"]
    for lab, v in res["learners"].items():
        ch = ", ".join(f"{k} {s * 100:.0f} %" for k, s in sorted(v["choice"].items(), key=lambda z: -z[1]))
        L.append(f"| {lab} | {v['saving_bps']:+.1f} | {'-' if v['t'] is None else f'{v['t']:.2f}'} | {v['h1'] if v['h1'] is None else f'{v['h1']:+.1f}'} | "
                 f"{v['h2']:+.1f} | {ch} | {'yes' if v['passed'] else ('-' if not judged else 'no')} |")
    L += ["", "Compare: the learned EXIT policy (#396) added +0.10 %/trade (10 bps, t 0.14) - closed. ORACLE is the hindsight ceiling of this",
          "decision alone. Limits: small orders only (no own impact); queue position = the back of the best bid; the 10-second grid; buys",
          "only (sells are the mirror); the opening and closing auctions (where the gap-fade trades) are not in this grid."]
    text = "\n".join(L)
    print(text)
    out = os.path.join(HERE, f"IDX_EXEC_BANDIT_{'SMOKE_' if not judged else ''}{date.today()}.md")
    open(out, "w", encoding="utf-8").write(text + "\n")
    if store and judged:
        with psycopg.connect(dsn) as conn:
            sid = rs.record_study(conn, STUDY, date.today(), params={"trials": ["P_ctx", "P_best"], "n_trials_cumulative": N_BEFORE + 2,
                                                                     "policies": POLICIES, "decide": [str(x) for x in DECIDE], "features": FEATS},
                                  summary=common.plain(res), names=[], report_path=out, note="execution bandit judged")
            conn.commit()
        print(f"study #{sid} stored")
    return 0


if __name__ == "__main__":
    sys.exit(main())
