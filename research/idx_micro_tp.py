#!/usr/bin/env python3
"""IDX menu 30 PRELIM — "exploit an inefficiency with a 1-2 % take-profit, from the desk's own tick feed" (operator, 2026-09-23:
"aku bukan mau trading berdasarkan selisih 1 tick saja, tapi exploitasi market inefficiency, lihat juga macro nya ... target 1-2
percent tp apakah ada strategi nya?" then "coba uji berdasarkan market microstructure yang kita punya 2 hari kebelakang").

Two sessions of the Stockbit feed exist (09-22, 09-23). That is enough for a DIRECTION read, never for adoption: whatever this says
must be re-run when >= 20 sessions exist (menu 28b) before any book is touched.

DESIGN (pre-registered before the first run)
  Panel      one row per (name, minute) in the continuous phases, built by research/idx_updown_prob.build_panel (book carried forward
             inside a session; names with >= 150 valid minutes). Added market context = the "macro" of the day, computed from the same
             names: MKT_RET (equal-weight mean of pos_day across names at minute t), MKT_TFI (mean TFI5 across names), MKT_BREADTH
             (share of names with pos_day > 0).
  Trade      a retail TAKER buy at the offer at minute t (the only fill a retail account can count on), then a bracket:
             TP  = limit sell at entry * (1 + tp), filled when the minute bar's HIGH prints strictly above the target;
             SL  = stop at entry * (1 - sl), triggered when the bar's LOW prints at or below the stop, filled at stop - 1 tick;
             if both trigger in the same bar the stop is assumed first (conservative);
             otherwise sold at the bid of the last continuous minute (15:49) - never held overnight (this is the day-trading question).
             Fees 30 bps round trip. Net bps = (exit / entry - 1) * 1e4 - 30. One open trade per name at a time (a signal while a
             trade is open is skipped) - that makes the trade count honest.
  Brackets   tp in {1 %, 2 %} x sl in {1 %, 2 %, none} = 6.
  Rules      (fixed, no fitting)
             R1 obi1     OBI1 >= 0.5                       bid queue dominates the top of book
             R2 obi5     OBI5 >= 0.3                       bid dominates five levels
             R3 tfi      TFI5 >= 0.5                       aggressive buyers dominated the last 5 min
             R4 dip      RET5 <= -50 bps                   5-min dip (menu 28: RET5 reverses, IC -0.12)
             R5 surge    vol_surge >= 3 and TFI5 > 0       volume burst with buying
             R6 support  dist_lo <= 1 tick and OBI1 >= 0.3  price at the day's low with a heavy bid = support holding
             R7 macro    MKT_RET >= +0.5 % and OBI1 >= 0.3   the market is up on the day and the book leans bid (the operator's
                                                           "look at the macro too")
             R8 ml       LightGBM P(TP-first | features + market context) trained on the first session, applied to the second;
                         signal = top decile of P on the test session (the only fitted arm; test day only)
             Reference (not a trial): every minute = the base rate of the bracket.
  Trials     8 rules x 6 brackets = 48 (cumulative 603 -> 651).
  Reads      per trial: trades, hit rate (TP first), stop rate, close-exit rate, mean and median net bps, t-stat of the trade mean,
             P(net > 0), by day; placebo = the same number of signals per name-day placed at random minutes, 200 draws, percentile of
             the real mean net among the placebo means.
  Bar        CANDIDATE (for a proper study, not for a book): >= 100 trades pooled, mean net >= +20 bps, t >= 2.0, positive on BOTH
             days, placebo percentile >= 95. Anything less = not a lead. With 2 sessions nothing is adoptable whatever the table says.

READ-ONLY. INGEST_DB_DSN=... PYTHONIOENCODING=utf-8 blackheart-ingest/.venv/Scripts/python research/idx_micro_tp.py
  [--days 2026-09-22,2026-09-23] [--no-store] [--out research/IDX_MICRO_TP_<day>.md]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from datetime import date

import numpy as np
import pandas as pd
import psycopg
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "blackheart-ingest", "src"))
_spec = importlib.util.spec_from_file_location("idx_updown_prob", os.path.join(HERE, "idx_updown_prob.py"))
up = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(up)

FEE_BPS = 30.0
SEED = 20260923
N_PLACEBO = 200
N_TRIALS_BEFORE = 603
BRACKETS = [(tp, sl) for tp in (0.01, 0.02) for sl in (0.01, 0.02, None)]
RULES = {
    "obi1": lambda P: P["OBI1"] >= 0.5,
    "obi5": lambda P: P["OBI5"] >= 0.3,
    "tfi": lambda P: P["TFI5"] >= 0.5,
    "dip": lambda P: P["RET5"] <= -0.005,
    "surge": lambda P: (P["vol_surge"] >= 3) & (P["TFI5"] > 0),
    "support": lambda P: (P["dist_lo"] <= 1) & (P["OBI1"] >= 0.3),
    "macro": lambda P: (P["MKT_RET"] >= 0.005) & (P["OBI1"] >= 0.3),
}
FEATS = [*up.FEATS, "MKT_RET", "MKT_TFI", "MKT_BREADTH"]
BAR = {"trades": 100, "net": 20.0, "t": 2.0, "placebo_pct": 95.0}


def bkey(tp: float, sl: float | None) -> str:
    return f"tp{int(tp * 100)}_sl{int(sl * 100) if sl else 'none'}"


# ---------------------------------------------------------------------------------------------------------- outcomes
def market_context(P: pd.DataFrame) -> pd.DataFrame:
    g = P.groupby(["day", "minute"])
    P["MKT_RET"] = g["pos_day"].transform("mean")
    P["MKT_TFI"] = g["TFI5"].transform("mean")
    P["MKT_BREADTH"] = g["pos_day"].transform(lambda x: (x > 0).mean())
    return P


def outcomes_for(P: pd.DataFrame) -> dict[str, dict[tuple, tuple[np.ndarray, np.ndarray, np.ndarray]]]:
    """For every bracket and every (day, name): per-minute arrays (exit_idx, net_bps, kind) of a taker buy at that minute's offer.
    kind: 1 = TP, -1 = stop, 0 = close, nan = no fill (no offer)."""
    out: dict[str, dict] = {bkey(*b): {} for b in BRACKETS}
    for (d, code), s in P.groupby(["day", "code"], sort=False):
        s = s.sort_values("minute")
        off = s["off1"].to_numpy(dtype=float)
        bid = s["bid1"].to_numpy(dtype=float)
        hi = s["high"].to_numpy(dtype=float)
        lo = s["low"].to_numpy(dtype=float)
        tick = s["tick"].to_numpy(dtype=float)
        n = len(s)
        hi = np.where(np.isfinite(hi) & (hi > 0), hi, -np.inf)
        lo = np.where(np.isfinite(lo) & (lo > 0), lo, np.inf)
        last_bid = bid[-1] if np.isfinite(bid[-1]) else np.nan
        for tp, sl in BRACKETS:
            exit_idx = np.full(n, -1, dtype=int)
            net = np.full(n, np.nan)
            kind = np.full(n, np.nan)
            for t in range(n - 1):
                e = off[t]
                if not np.isfinite(e) or e <= 0:
                    continue
                target = e * (1 + tp)
                stop = e * (1 - sl) if sl else -np.inf
                h = hi[t + 1:]
                l = lo[t + 1:]
                i_tp = int(np.argmax(h > target)) if (h > target).any() else -1
                i_sl = int(np.argmax(l <= stop)) if sl and (l <= stop).any() else -1
                if i_sl >= 0 and (i_tp < 0 or i_sl <= i_tp):
                    j = t + 1 + i_sl
                    px = stop - tick[j]
                    k = -1.0
                elif i_tp >= 0:
                    j = t + 1 + i_tp
                    px = target
                    k = 1.0
                else:
                    j = n - 1
                    px = last_bid
                    k = 0.0
                if not np.isfinite(px):
                    continue
                exit_idx[t] = j
                net[t] = (px / e - 1) * 1e4 - FEE_BPS
                kind[t] = k
            out[bkey(tp, sl)][(d, code)] = (exit_idx, net, kind)
    return out


def simulate(sig_idx: np.ndarray, exit_idx: np.ndarray, net: np.ndarray, kind: np.ndarray) -> tuple[list[float], list[float]]:
    """One open trade per name: walk the signal minutes, skip those inside an open trade."""
    nets, kinds = [], []
    busy_until = -1
    for t in sig_idx:
        if t <= busy_until or exit_idx[t] < 0:
            continue
        nets.append(float(net[t]))
        kinds.append(float(kind[t]))
        busy_until = int(exit_idx[t])
    return nets, kinds


def run_rule(P: pd.DataFrame, signal: pd.Series, outs: dict, rng: np.random.Generator, placebo: bool = True) -> dict:
    per_day: dict[str, list[float]] = {}
    nets_all, kinds_all = [], []
    groups = {}
    for (d, code), s in P.groupby(["day", "code"], sort=False):
        order = np.argsort(s["minute"].to_numpy())
        sig = signal.loc[s.index].to_numpy()[order]
        groups[(d, code)] = sig
    res = {}
    for bk, O in outs.items():
        nets_all, kinds_all, per_day = [], [], {}
        for key, sig in groups.items():
            if key not in O:
                continue
            ex, net, kind = O[key]
            n_, k_ = simulate(np.flatnonzero(sig), ex, net, kind)
            nets_all += n_
            kinds_all += k_
            per_day.setdefault(key[0].isoformat(), []).extend(n_)
        a = np.asarray(nets_all)
        k = np.asarray(kinds_all)
        r = {"trades": int(len(a)), "mean": float(a.mean()) if len(a) else np.nan, "median": float(np.median(a)) if len(a) else np.nan,
             "t": float(a.mean() / a.std(ddof=1) * np.sqrt(len(a))) if len(a) > 2 and a.std(ddof=1) > 0 else np.nan,
             "p_win": float((a > 0).mean()) if len(a) else np.nan,
             "tp_rate": float((k == 1).mean()) if len(k) else np.nan, "sl_rate": float((k == -1).mean()) if len(k) else np.nan,
             "close_rate": float((k == 0).mean()) if len(k) else np.nan,
             "by_day": {d: {"trades": len(v), "mean": float(np.mean(v)) if v else np.nan} for d, v in sorted(per_day.items())}}
        if placebo and len(a) >= 20:
            means = []
            for _ in range(N_PLACEBO):
                pl = []
                for key, sig in groups.items():
                    if key not in O:
                        continue
                    ex, net, kind = O[key]
                    m = int(sig.sum())
                    if m == 0:
                        continue
                    valid = np.flatnonzero(ex >= 0)
                    if len(valid) == 0:
                        continue
                    pick = np.sort(rng.choice(valid, size=min(m, len(valid)), replace=False))
                    n_, _ = simulate(pick, ex, net, kind)
                    pl += n_
                means.append(float(np.mean(pl)) if pl else np.nan)
            means = np.asarray(means)
            means = means[np.isfinite(means)]
            r["placebo_mean"] = float(means.mean()) if len(means) else np.nan
            r["placebo_pct"] = float((means < r["mean"]).mean() * 100) if len(means) else np.nan
        else:
            r["placebo_mean"], r["placebo_pct"] = np.nan, np.nan
        traded_days = [v for v in r["by_day"].values() if v["trades"] > 0]          # the ML arm trades the test day only
        days_pos = bool(traded_days) and all(np.isfinite(v["mean"]) and v["mean"] > 0 for v in traded_days)
        r["days_traded"] = len(traded_days)
        r["CANDIDATE"] = bool(r["trades"] >= BAR["trades"] and np.isfinite(r["mean"]) and r["mean"] >= BAR["net"]
                              and np.isfinite(r["t"]) and r["t"] >= BAR["t"] and days_pos
                              and np.isfinite(r["placebo_pct"]) and r["placebo_pct"] >= BAR["placebo_pct"])
        res[bk] = r
    return res


def ml_signal(P: pd.DataFrame, outs: dict, days: list[date]) -> tuple[pd.Series, dict]:
    """Train on the earlier session(s), score the last; label = TP-first under tp1_sl1; signal = top decile on the test day."""
    import lightgbm as lgb
    O = outs["tp1_sl1"]
    lab = pd.Series(np.nan, index=P.index)
    for (d, code), s in P.groupby(["day", "code"], sort=False):
        if (d, code) not in O:
            continue
        order = np.argsort(s["minute"].to_numpy())
        _, _, kind = O[(d, code)]
        lab.loc[s.index[order]] = np.where(np.isfinite(kind), (kind == 1).astype(float), np.nan)
    P = P.assign(LAB=lab)
    test_day = max(days)
    tr = P[(P["day"] < test_day)].dropna(subset=[*FEATS, "LAB"])
    te = P[(P["day"] == test_day)].dropna(subset=[*FEATS, "LAB"])
    params = {"objective": "binary", "learning_rate": 0.03, "num_leaves": 15, "min_data_in_leaf": 200, "bagging_fraction": 0.8,
              "bagging_freq": 1, "feature_fraction": 0.8, "lambda_l2": 5.0, "seed": SEED, "verbose": -1}
    m = lgb.train(params, lgb.Dataset(tr[FEATS].to_numpy(dtype=float), label=tr["LAB"].to_numpy(), feature_name=FEATS), num_boost_round=400)
    p = np.asarray(m.predict(te[FEATS].to_numpy(dtype=float)))
    y = te["LAB"].to_numpy()
    gain = np.asarray(m.feature_importance(importance_type="gain"), dtype=float)
    top = p >= np.quantile(p, 0.9)
    sig = pd.Series(False, index=P.index)
    sig.loc[te.index[top]] = True
    info = {"auc": up.auc_score(y, p), "base": float(y.mean()), "top_decile_rate": float(y[top].mean()), "rows_train": len(tr), "rows_test": len(te),
            "importance": dict(zip(FEATS, (gain / gain.sum()).round(3).tolist(), strict=True))}
    return sig, info


# ---------------------------------------------------------------------------------------------------------------- run
def run(dsn: str, days: list[date], out_path: str, store: bool, study_name: str) -> dict:
    panels = []
    with psycopg.connect(dsn) as conn:
        for d in days:
            book, bars, prints = up.load_day(conn, d)
            if book.empty:
                continue
            panels.append(up.build_panel(book, bars, prints, d))
    P = pd.concat(panels, ignore_index=True)
    P = market_context(P)
    days = sorted(P["day"].unique())
    outs = outcomes_for(P)
    rng = np.random.default_rng(SEED)
    res: dict = {"desc": {"days": [d.isoformat() for d in days], "names": int(P["code"].nunique()), "rows": len(P),
                          "mkt_ret_close": {d.isoformat(): float(P[P["day"] == d].groupby("minute")["pos_day"].mean().iloc[-1]) for d in days}},
                 "reference": run_rule(P, pd.Series(True, index=P.index), outs, rng, placebo=False), "rules": {}, "signals": {}}
    for name, f in RULES.items():
        sig = f(P).fillna(False)
        res["signals"][name] = int(sig.sum())
        res["rules"][name] = run_rule(P, sig, outs, rng)
    if len(days) >= 2:
        sig, info = ml_signal(P, outs, days)
        res["signals"]["ml"] = int(sig.sum())
        res["ml"] = info
        res["rules"]["ml"] = run_rule(P, sig, outs, rng)
    cands = [f"{r}/{b}" for r, bs in res["rules"].items() for b, v in bs.items() if v["CANDIDATE"]]
    res["verdict"] = {"candidates": cands, "n_trials": len(RULES) * len(BRACKETS) + (len(BRACKETS) if "ml" in res["rules"] else 0)}
    write_report(res, out_path)
    if store:
        from blackheart_ingest.idx import research_store as rs
        with psycopg.connect(dsn) as conn:
            sid = rs.record_study(conn, study_name, days[-1], params={"trials": [f"{r}/{bkey(*b)}" for r in [*RULES, "ml"] for b in BRACKETS],
                                                                     "n_trials_cumulative": N_TRIALS_BEFORE + res["verdict"]["n_trials"],
                                                                     "brackets": [bkey(*b) for b in BRACKETS], "fee_bps": FEE_BPS, "seed": SEED,
                                                                     "bar": BAR, "days": res["desc"]["days"]},
                                 summary=json.loads(json.dumps(res, default=str)), names=[], report_path=out_path,
                                 note=f"{res['verdict']['n_trials']} trials on {len(days)} sessions; candidates {cands or 'none'}")
            res["study_id"] = sid
    return res


def _row(name: str, bk: str, r: dict) -> str:
    bd = " / ".join(f"{v['mean']:+.0f}" if np.isfinite(v["mean"]) else "-" for v in r["by_day"].values())
    f = lambda x, fmt: (fmt % x) if np.isfinite(x) else "-"  # noqa: E731
    return (f"| {name} | {bk} | {r['trades']:,} | {f(r['tp_rate'] * 100, '%.0f')} % | {f(r['sl_rate'] * 100, '%.0f')} % | {f(r['close_rate'] * 100, '%.0f')} % | "
            f"{f(r['mean'], '%+.1f')} | {f(r['median'], '%+.1f')} | {f(r['t'], '%.2f')} | {f(r['p_win'] * 100, '%.0f')} % | {bd} | "
            f"{f(r['placebo_mean'], '%+.1f')} | {f(r['placebo_pct'], '%.0f')} | {("CANDIDATE" + (" (1 test day)" if r.get("days_traded", 2) < 2 else "")) if r["CANDIDATE"] else "no"} |")


def write_report(res: dict, path: str) -> None:
    d = res["desc"]
    hdr = ("| rule | bracket | trades | TP | stop | close | mean bps | median | t | P(win) | by day | placebo mean | placebo pct | verdict |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    L = [f"# IDX menu 30 PRELIM — 1-2 % take-profit brackets from the tick feed — {d['days'][-1]}", "",
         f"Sessions {', '.join(d['days'])}; {d['names']} names; {d['rows']:,} name-minutes. Market (EW of feed names) closed "
         + ", ".join(f"{k} {v * 100:+.2f} %" for k, v in d["mkt_ret_close"].items()) + ".",
         f"Taker buy at the offer, TP limit / stop bracket / sold at the 15:49 bid, fees {FEE_BPS:.0f} bps, one open trade per name.",
         f"Pre-registered in `research/idx_micro_tp.py`; {res['verdict']['n_trials']} trials (cumulative {N_TRIALS_BEFORE + res['verdict']['n_trials']}).",
         "**Two sessions = a direction read only. Nothing here is adoptable.**", "",
         "## Reference — every minute is a signal (base rate of the bracket, not a trial)", "", *hdr]
    L += [_row("all", bk, r) for bk, r in res["reference"].items()]
    L += ["", "## Rules", "", "Signals per rule: " + ", ".join(f"{k} {v:,}" for k, v in res["signals"].items()), "", *hdr]
    for name, bs in res["rules"].items():
        L += [_row(name, bk, r) for bk, r in bs.items()]
    if "ml" in res:
        m = res["ml"]
        L += ["", f"## ML arm — LightGBM P(TP first | tp1_sl1), train {m['rows_train']:,} rows (first session) -> test {m['rows_test']:,} (last session)", "",
              f"- AUC {m['auc']:.3f}; base rate {m['base']:.3f}; top-decile realised {m['top_decile_rate']:.3f}",
              "- importance (gain share): " + ", ".join(f"{k} {v}" for k, v in sorted(m["importance"].items(), key=lambda kv: -kv[1])[:8])]
    L += ["", "## Reading", "", f"- Candidates by the declared bar (>= 100 trades, mean >= +20 bps, t >= 2, both days positive, placebo >= 95): "
          f"{', '.join(res['verdict']['candidates']) or 'none'}.",
          "- The reference rows show what the bracket itself does to an unconditional taker entry; a rule only matters if it beats its reference row",
          "  AND its placebo (same number of entries at random minutes in the same names).",
          "- Re-run when >= 20 sessions exist (menu 28b). A two-session table cannot separate a lead from the day's drift.", ""]
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(L))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", default="2026-09-22,2026-09-23")
    ap.add_argument("--no-store", action="store_true")
    ap.add_argument("--out", default="")
    ap.add_argument("--study-name", default="micro_tp")
    a = ap.parse_args()
    days = sorted(date.fromisoformat(x) for x in a.days.split(","))
    out = a.out or os.path.join(HERE, f"IDX_MICRO_TP_{days[-1].isoformat()}.md")
    res = run(os.environ["INGEST_DB_DSN"], days, out, not a.no_store, a.study_name)
    print(json.dumps({"desc": res["desc"], "verdict": res["verdict"], "ml": {k: v for k, v in res.get("ml", {}).items() if k != "importance"},
                      "study_id": res.get("study_id"), "report": out}, indent=1, default=str))


if __name__ == "__main__":
    main()
