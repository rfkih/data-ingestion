#!/usr/bin/env python3
"""IDX menu ML-5 — the prediction desk's scores as an OVERLAY on the three proven strategies (operator, 2026-09-24: "kalau
digabungkan dengan strategi trading punya kita yang udah proven?").

ML-4/4b (studies #151, #152) settled that the walk-forward scores rank names for real but cannot carry a book of their own
after IDX costs. This menu puts them where the desk already has an edge and turnover is paid for anyway: choosing among the
trend rule's signals, choosing among the value screen's names, choosing among the morning's gaps. Same simulators, same
costs, same windows as the studies that produced the "proven" numbers; the only change is the choice the score makes.

PRE-REGISTERED (10 trials; cumulative 731 + 10 = 741). Scores = the ML-4 walk-forward OOS scores (5d, 20d excess, 250d excess),
  expressed as that day's percentile rank among LIQ names; every book below runs from 2022-01 (the first OOS year) so the
  reference is recomputed on the same window - the deployed figures in the ROI scorecard are NOT the reference here.
  A. Trend book (idx_exit.run_book: menu-6 lead = close at the 60-day high, > MA200, volume >= 1.5x; trail-10 exit; K 10;
     the deployed regime gate = no NEW entry while COMPOSITE < its 200-day mean; universes `small` (deployed) and LIQ):
       trend_rank20|u   when signals exceed free slots, rank by the 20d score instead of the volume ratio
       trend_filt20|u   skip a signal whose 20d score is in the bottom third of that day's LIQ ranking
       trend_filt5|u    skip a signal whose 5d score is in the bottom third (next-week timing)
     Reference: the plain gated rule on the same window. BETTER (idx_exit's bar) = n >= 150, t >= 2, Sharpe >= ref + 0.15,
     CAGR >= 0.8 x ref, drawdown not deeper.
  B. Value book (idx_value_quality: composite_q = composite rank of E/P, B/P, DY inside the strict gate, May rebalance,
     buy-and-hold to the next, dividends net, 25 bps + half tick; rebalances 2022-05 .. 2026-05):
       value_avoid      drop the picks whose 250d score is in the bottom third at the rebalance (no refill)
       value_refill     the same, each dropped name replaced by the next name in the composite pool that is not bottom-third
       value_rerank     pick the same number of names by the rank-mean of the composite position and the 250d score
     Reference: composite_q on the same rebalances. BETTER = CAGR >= ref + 2 pp, drawdown not deeper, more rebalance
     periods won than lost.
  C. Gap-fade (idx_gapfade: open <= -7 % vs the prior close, buy at the open + tick, sell at the close - tick, fees; up to
     K 10 a day, deepest liquidity first):
       gf_filt5         only gaps on names whose PREVIOUS close's 5d score is in the top half
       gf_rank5         the day's gaps ranked by that score instead of liquidity
     Reference: the g7 arm on the same window. BETTER = mean net per event >= ref + 30 bps with >= 100 events and t >= 3.
  ADOPTION: a BETTER overlay on the deployed universe goes to the PAPER book of that strategy by the operator's decision.
READ-ONLY on the market tables; one idx.study row. INGEST_DB_DSN, IDX_ML_CACHE (from ML-4), IDX_EXIT_CACHE (optional).
"""
from __future__ import annotations

import os
import pickle
import sys
from datetime import date

import numpy as np
import pandas as pd
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "blackheart-ingest", "src"))
import idx_beyond as BY  # noqa: E402
import idx_exit as E  # noqa: E402
import idx_gapfade as G  # noqa: E402
import idx_ml_strategy as M  # noqa: E402
import idx_swing2 as S  # noqa: E402
import idx_value_quality as V  # noqa: E402
from blackheart_ingest.idx import candidates as cand  # noqa: E402
from blackheart_ingest.idx import research_store as rs  # noqa: E402
from blackheart_ingest.idx.ml import common  # noqa: E402

N_BEFORE = 731
STUDY = "ml_overlay"
FROM = pd.Timestamp("2022-01-01")
ARMS = ["trend_rank20|small", "trend_filt20|small", "trend_filt5|small", "trend_rank20|LIQ", "trend_filt20|LIQ", "trend_filt5|LIQ",
        "value_avoid", "value_refill", "value_rerank", "gf_filt5", "gf_rank5"]
assert len(ARMS) == 11          # 11 arms, 10 counted trials: trend_filt5|LIQ is the LIQ mirror of a `small` trial (informative)
N_TRIALS = 10
BOTTOM = 1 / 3


def pct_panels() -> dict[str, pd.DataFrame]:
    P = pickle.load(open(os.environ["IDX_ML_CACHE"], "rb"))
    P = P[P["liq"] & (P["d"] >= FROM)]
    out = {}
    for k in ("s5", "s20", "s250"):
        P[f"pct_{k}"] = P.groupby("d")[k].rank(pct=True)
        out[k] = P.pivot(index="d", columns="code", values=f"pct_{k}").sort_index()
    return out


def align(W: pd.DataFrame, index, columns) -> np.ndarray:
    return W.reindex(index=index, columns=columns).to_numpy(float)


# ---- A. trend --------------------------------------------------------------------------------------------------------------
def family_trend(dsn: str, pct: dict[str, pd.DataFrame]) -> tuple[dict, dict]:
    P, unis, comp, Hp, Lp = E.load_all(dsn, os.environ.get("IDX_EXIT_CACHE"))
    c_in, c_out = S.costs(P)
    adj, vol = P["adj"], P["volume"]
    dates = adj.index
    A, H, L = adj.to_numpy(float), Hp.to_numpy(float), Lp.to_numpy(float)
    ma200 = adj.rolling(200, min_periods=200).mean()
    vr = vol / vol.rolling(20, min_periods=20).median()
    hi = adj.rolling(E.LEAD[0], min_periods=E.LEAD[0]).max()
    entry = ((adj >= hi) & (adj > ma200) & (vr >= E.LEAD[2])).to_numpy(bool)
    entry &= np.asarray(dates >= FROM)[:, None]
    off = BY.regime_off_mask(comp, dates)
    entry &= ~off[:, None]                                                   # the deployed gate: no new entry while the index is under MA200
    vr_score = vr.to_numpy(float)
    p20, p5 = align(pct["s20"], dates, adj.columns), align(pct["s5"], dates, adj.columns)
    prev = adj.shift(1)
    tr = pd.concat([Hp - Lp, (Hp - prev).abs(), (Lp - prev).abs()], axis=1, keys=["a", "b", "c"]).T.groupby(level=1).max().T.reindex(columns=adj.columns)
    ATR = tr.ewm(alpha=1 / 20, adjust=False, min_periods=20).mean().to_numpy(float)
    ma20, ma50 = (adj.rolling(n, min_periods=n).mean().to_numpy(float) for n in (20, 50))
    d = adj.diff()
    up = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    RSI = (100 - 100 / (1 + up / dn.replace(0, np.nan))).to_numpy(float)
    LO10 = Lp.shift(1).rolling(10, min_periods=10).min().to_numpy(float)
    LO20 = Lp.shift(1).rolling(20, min_periods=20).min().to_numpy(float)
    rule = E.make_rules(A, H, L, ATR, ma20, ma50, RSI, LO10, LO20)["trail10"]
    universes = {"small": (unis["LIQ"] & ~unis["BLUE"]).to_numpy(bool), "LIQ": unis["LIQ"].to_numpy(bool)}
    n_trials = N_BEFORE + N_TRIALS
    res, refs = {}, {}
    for u, uni in universes.items():
        R, trs, _ = E.run_book(A, H, L, c_in, c_out, entry, vr_score, rule, uni)
        refs[u] = E.stats(R, trs, dates, n_trials)
        M.log(f"trend ref {u}: n {refs[u]['n']} cagr {refs[u]['cagr'] * 100:+.1f} % sharpe {refs[u]['sharpe']:.2f} mdd {refs[u]['mdd'] * 100:.0f} %")
        variants = {"trend_rank20": (entry, np.nan_to_num(p20, nan=-1.0)),
                    "trend_filt20": (entry & (p20 >= BOTTOM), vr_score),
                    "trend_filt5": (entry & (p5 >= BOTTOM), vr_score)}
        for name, (mask, score) in variants.items():
            R, trs, open_ = E.run_book(A, H, L, c_in, c_out, mask, score, rule, uni)
            s = E.stats(R, trs, dates, n_trials)
            s["open"] = len(open_)
            ref = refs[u]
            why = []
            if s["n"] < 150:
                why.append("n<150")
            if s["tstat"] < 2.0:
                why.append("t<2")
            if s["sharpe"] < ref["sharpe"] + 0.15:
                why.append(f"sharpe {s['sharpe']:.2f} < ref {ref['sharpe']:.2f} + 0.15")
            if s["cagr"] < 0.8 * ref["cagr"]:
                why.append("cagr < 80 % ref")
            if s["mdd"] < ref["mdd"]:
                why.append("mdd deeper")
            s["verdict"] = "BETTER" if not why else "no: " + "; ".join(why)
            res[f"{name}|{u}"] = s
            M.log(f"{name}|{u}: n {s['n']} hit {s['hit'] * 100:.0f} % net {s['avg_net'] * 100:+.2f} % t {s['tstat']:.1f} cagr {s['cagr'] * 100:+.1f} % "
                  f"sharpe {s['sharpe']:.2f} mdd {s['mdd'] * 100:.0f} % -> {s['verdict']}")
    return res, refs


# ---- B. value --------------------------------------------------------------------------------------------------------------
def family_value(dsn: str, pct: dict[str, pd.DataFrame]) -> tuple[dict, dict]:
    with psycopg.connect(dsn) as conn:
        close, vol, delisted, div, _ix = V.load(conn)
        rebals = [D for D in V.rebalance_dates(close.index, 5) if D >= FROM]
        p250 = pct["s250"]
        sels: dict[str, dict] = {k: {} for k in ("composite_q", "value_avoid", "value_refill", "value_rerank")}
        logs = []
        for D in rebals:
            res = cand.build(conn, D.date())
            rows = res["all_rows"]
            pool = cand.rank_pool([dict(r) for r in rows], gate="strict", keys=cand.KEYS)
            picks = [r["code"] for r in pool if r["selected"]]
            n = len(picks)
            row = p250.loc[:D].iloc[-1] if (p250.index <= D).any() else pd.Series(dtype=float)
            score = {r["code"]: float(row.get(r["code"], np.nan)) for r in pool}
            bottom = {c for c in picks if np.isfinite(score.get(c, np.nan)) and score[c] < BOTTOM}
            keep = [c for c in picks if c not in bottom]
            refill = list(keep)
            for r in pool:
                if len(refill) >= n:
                    break
                c = r["code"]
                if c in picks or c in refill or not np.isfinite(score.get(c, np.nan)) or score[c] < BOTTOM:
                    continue
                refill.append(c)
            m = len(pool)
            comp_pos = {r["code"]: 1 - i / max(1, m - 1) for i, r in enumerate(pool)}       # 1 = best composite rank
            blend = {c: np.nanmean([comp_pos[c], score[c]]) if np.isfinite(score.get(c, np.nan)) else comp_pos[c] for c in comp_pos}
            rerank = sorted(blend, key=lambda c: -blend[c])[:n]
            sels["composite_q"][D] = set(picks)
            sels["value_avoid"][D] = set(keep)
            sels["value_refill"][D] = set(refill)
            sels["value_rerank"][D] = set(rerank)
            logs.append({"date": str(D.date()), "picks": n, "dropped": sorted(bottom), "refilled": sorted(set(refill) - set(keep)),
                         "rerank_new": sorted(set(rerank) - set(picks)), "pool": m})
            M.log(f"value {D.date()}: {n} picks, bottom-third dropped {sorted(bottom)}, rerank swaps in {sorted(set(rerank) - set(picks))}")
        end = close.index[-1]
        out = {}
        for name, sel in sels.items():
            nav = V.simulate(sel, close, vol, delisted, div, rebals[0], end, True)
            st = V.stats(nav, rebals)
            del st["_r"]
            out[name] = st
        ref = out["composite_q"]
        for name in ("value_avoid", "value_refill", "value_rerank"):
            st = out[name]
            won = sum(st["periods"][k] > ref["periods"][k] for k in st["periods"])
            lost = sum(st["periods"][k] < ref["periods"][k] for k in st["periods"])
            why = []
            if st["cagr_pct"] < ref["cagr_pct"] + 2:
                why.append(f"cagr {st['cagr_pct']:.1f} < ref {ref['cagr_pct']:.1f} + 2")
            if st["mdd_pct"] < ref["mdd_pct"]:
                why.append("mdd deeper")
            if won <= lost:
                why.append(f"periods won {won} <= lost {lost}")
            st["periods_won"], st["periods_lost"] = won, lost
            st["verdict"] = "BETTER" if not why else "no: " + "; ".join(why)
            M.log(f"{name}: cagr {st['cagr_pct']:+.1f} % sharpe {st['sharpe']:.2f} mdd {st['mdd_pct']:.0f} % won {won} lost {lost} -> {st['verdict']}")
        M.log(f"value ref composite_q: cagr {ref['cagr_pct']:+.1f} % sharpe {ref['sharpe']:.2f} mdd {ref['mdd_pct']:.0f} %")
        out["log"] = logs
        return {k: out[k] for k in ("value_avoid", "value_refill", "value_rerank")}, {"composite_q": ref, "log": logs}


# ---- C. gap-fade ------------------------------------------------------------------------------------------------------------
def pick_by(B: dict, mask: pd.DataFrame, R: pd.DataFrame, rank: pd.DataFrame | None) -> pd.DataFrame:
    rows = []
    elig, v60 = B["elig"], B["v60"]
    for d in R.index:
        if pd.Timestamp(d) < FROM:
            continue
        q = elig.loc[d] & mask.loc[d].fillna(False)
        if not q.any():
            continue
        key = (rank.loc[d] if rank is not None else v60.loc[d]).where(q).dropna().sort_values(ascending=False)
        pick = key.index[:G.K]
        r = R.loc[d, pick].dropna()
        for code, x in r.items():
            rows.append((d, code, float(x)))
    return pd.DataFrame(rows, columns=["d", "code", "net"])


def family_gapfade(dsn: str, pct: dict[str, pd.DataFrame]) -> tuple[dict, dict]:
    B = G.build(dsn)
    gap = B["gap"]
    p5_prev = pct["s5"].reindex(index=gap.index, columns=gap.columns).shift(1)      # the previous close's score, known before the open
    R = B["R"]["close"]
    g7 = B["masks"]["g7"]
    ref = G.stats(pick_by(B, g7, R, None))
    M.log(f"gapfade ref g7: n {ref['trades']} mean {ref['mean_bps']:+.0f} bps t {ref['t']:.1f} sleeve sharpe {ref['sleeve']['sharpe']:.2f}")
    res = {"gf_filt5": G.stats(pick_by(B, g7 & (p5_prev >= 0.5), R, None)), "gf_rank5": G.stats(pick_by(B, g7, R, p5_prev))}
    for name, st in res.items():
        if "mean_bps" not in st:
            st["verdict"] = "too few"
            continue
        why = []
        if st["trades"] < 100:
            why.append("n<100")
        if st["mean_bps"] < ref["mean_bps"] + 30:
            why.append(f"mean {st['mean_bps']:+.0f} < ref {ref['mean_bps']:+.0f} + 30")
        if st["t"] < 3:
            why.append("t<3")
        st["verdict"] = "BETTER" if not why else "no: " + "; ".join(why)
        M.log(f"{name}: n {st['trades']} mean {st['mean_bps']:+.0f} bps hit {st['hit'] * 100:.0f} % t {st['t']:.1f} sleeve sharpe {st['sleeve']['sharpe']:.2f} -> {st['verdict']}")
    return res, {"g7": ref}


def main() -> int:
    dsn = os.environ["INGEST_DB_DSN"]
    pct = pct_panels()
    M.log("percentile panels ready")
    res_t, ref_t = family_trend(dsn, pct)
    res_v, ref_v = family_value(dsn, pct)
    res_g, ref_g = family_gapfade(dsn, pct)
    n_trials = N_BEFORE + N_TRIALS
    L = [f"# IDX menu ML-5 — the prediction desk's scores as an overlay on the proven strategies — {date.today()} — {N_TRIALS} trials, cumulative N = {n_trials}", "",
         "Walk-forward OOS scores (ML-4) as that day's percentile among LIQ names; every book from 2022-01 with its reference recomputed on the same window.", "",
         "## A. Trend book (trail-10, K 10, regime gate) — bar: n >= 150, t >= 2, Sharpe >= ref + 0.15, CAGR >= 0.8 ref, mDD not deeper", "",
         "| arm | n | hold | hit | avg net | t | CAGR | Sharpe | mDD | verdict |", "|---|---|---|---|---|---|---|---|---|---|"]
    for u in ("small", "LIQ"):
        r = ref_t[u]
        L.append(f"| plain gated rule ({u}) | {r['n']} | {r['hold']:.0f} | {r['hit'] * 100:.0f} % | {r['avg_net'] * 100:+.2f} % | {r['tstat']:.1f} | {r['cagr'] * 100:+.1f} % | {r['sharpe']:.2f} | {r['mdd'] * 100:.0f} % | reference |")
        for name in ("trend_rank20", "trend_filt20", "trend_filt5"):
            s = res_t[f"{name}|{u}"]
            L.append(f"| {name} ({u}) | {s['n']} | {s['hold']:.0f} | {s['hit'] * 100:.0f} % | {s['avg_net'] * 100:+.2f} % | {s['tstat']:.1f} | {s['cagr'] * 100:+.1f} % | {s['sharpe']:.2f} | {s['mdd'] * 100:.0f} % | {s['verdict']} |")
    L += ["", "## B. Value book (composite_q, May, 2022-05 -> now) — bar: CAGR >= ref + 2 pp, mDD not deeper, periods won > lost", "",
          "| arm | total | CAGR | Sharpe | mDD | periods (from each May) | verdict |", "|---|---|---|---|---|---|---|"]
    r = ref_v["composite_q"]
    per = lambda s: " ".join(f"{k[2:7]}:{v:+.0f}" for k, v in s["periods"].items())  # noqa: E731
    L.append(f"| composite_q (deployed rule) | {r['total_pct']:+.1f} % | {r['cagr_pct']:+.1f} % | {r['sharpe']:.2f} | {r['mdd_pct']:.0f} % | {per(r)} | reference |")
    for name, s in res_v.items():
        L.append(f"| {name} | {s['total_pct']:+.1f} % | {s['cagr_pct']:+.1f} % | {s['sharpe']:.2f} | {s['mdd_pct']:.0f} % | {per(s)} | {s['verdict']} |")
    L += ["", "Rebalance log: " + "; ".join(f"{x['date']}: {x['picks']} picks, dropped {x['dropped']}, rerank in {x['rerank_new']}" for x in ref_v["log"]), "",
          "## C. Gap-fade (open <= -7 %, buy open + tick, sell close - tick) — bar: mean >= ref + 30 bps, n >= 100, t >= 3", "",
          "| arm | events | hit | mean net | t | sleeve CAGR | sleeve Sharpe | sleeve mDD | verdict |", "|---|---|---|---|---|---|---|---|---|"]
    r = ref_g["g7"]
    L.append(f"| g7 (deployed rule) | {r['trades']} | {r['hit'] * 100:.0f} % | {r['mean_bps']:+.0f} bps | {r['t']:.1f} | {r['sleeve']['cagr_pct']:+.1f} % | {r['sleeve']['sharpe']:.2f} | {r['sleeve']['mdd_pct']:.0f} % | reference |")
    for name, s in res_g.items():
        if "mean_bps" in s:
            L.append(f"| {name} | {s['trades']} | {s['hit'] * 100:.0f} % | {s['mean_bps']:+.0f} bps | {s['t']:.1f} | {s['sleeve']['cagr_pct']:+.1f} % | {s['sleeve']['sharpe']:.2f} | {s['sleeve']['mdd_pct']:.0f} % | {s['verdict']} |")
        else:
            L.append(f"| {name} | {s['trades']} | | | | | | | too few |")
    better = [a for a, s in {**res_t, **res_v, **res_g}.items() if s.get("verdict") == "BETTER"]
    L += ["", "## Verdict (menu ML-5, study stored)", "", f"BETTER overlays: {', '.join(better) or 'none'}."]
    text = "\n".join(L)
    out = os.path.join(HERE, f"IDX_ML_OVERLAY_{date.today()}.md")
    open(out, "w", encoding="utf-8").write(text + "\n")
    print(text)
    with psycopg.connect(dsn) as conn:
        sid = rs.record_study(conn, STUDY, date.today(), params={"trials": ARMS, "n_trials_cumulative": n_trials, "from": str(FROM.date()), "bottom": BOTTOM,
                                                                   "source": "ml_strategy #151 scores"},
                              summary=common.plain({"trend": res_t, "trend_ref": ref_t, "value": res_v, "value_ref": ref_v, "gapfade": res_g, "gapfade_ref": ref_g,
                                                    "better": better}), names=[], report_path=out)
        conn.commit()
    M.log(f"study #{sid} stored; report {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
