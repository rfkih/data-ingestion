#!/usr/bin/env python3
"""IDX menu 28b-1 PRELIM — "bet with the probability, and CANCEL the buy when the direction turns" (operator, 2026-09-23: "kamu betting
dengan probability terus misalnya arahnya tidak menguntungkan cancel buy nya").

Menu 28b-0 (#75): a maker bid fills mostly when the price comes down through it (adverse selection, −48..−63 bps/fill). The operator's
fix: post the bid only while P(up) is high and pull it the moment P(up) drops — the adverse fill needs the price to fall, and the
signal should see that first. Tested here with queue-aware fills on the 10-s grid, P(up, 5 min) from menu 31's LightGBM (train 09-22 →
test 09-23), real fees 15 + 25 bps.

DESIGN (pre-registered before the first run)
  Score      p_t = LightGBM P(UP 5 min) from research/idx_lob_ml (30 book/tape features), trained on 09-22, scored on 09-23.
             Thresholds from the TRAIN day's score distribution: p_hi in {q80, q90} (post), p_lo = q50 (cancel / exit).
  Post       at step t with p_t >= p_hi and a valid bid: a buy limit at L = bid1_t, joining the back of the queue: ahead = bv1_t shares.
  Fill       queue-aware: filled at L at the first later step j (same session, <= 90 steps = 15 min) where the printed volume at
             prices <= L since posting reaches `ahead`. No fill by the deadline = expired.
  Cancel     arm 'cancel': the order is pulled at the first step j with p_j < p_lo before a fill. Arm 'hold': never pulled before the deadline.
  Exit       after a fill at j: 't15' = sell at the bid 15 min after the fill (or the session's last step); 'signal' = sell at the bid at the
             first k > j with p_k < p_lo, else at j + 90. (Taker exits; a maker exit would need its own queue and its own adverse selection.)
  Costs      fees 15 bps buy + 25 bps sell. Net bps = (px_out / L − 1) * 1e4 − 40.
  Reads      per arm: signals, orders posted, fills, fill rate, cancelled share, mean / median net per fill, t, P(win), net per signal,
             adverse share (mid 5 min after the fill below L). Placebo: p shuffled within name (posting AND cancelling from the shuffled
             score), 20 draws → percentile of the real net per fill.
  Trials     p_hi {q80, q90} x {cancel, hold} x exit {t15, signal} = 8 (cumulative 699 → 707).
  Bar        CANDIDATE: >= 100 fills, mean net >= +20 bps, t >= 2.0, placebo pct >= 95. One test day → flagged; nothing adoptable.

READ-ONLY. INGEST_DB_DSN=... PYTHONIOENCODING=utf-8 blackheart-ingest/.venv/Scripts/python research/idx_maker_cancel.py
  [--train 2026-09-22 --test 2026-09-23] [--no-store] [--out research/IDX_MAKER_CANCEL_<test>.md]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
from datetime import date

import numpy as np
import pandas as pd
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "blackheart-ingest", "src"))
_spec = importlib.util.spec_from_file_location("idx_lob_ml", os.path.join(HERE, "idx_lob_ml.py"))
lob = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lob)

FEE_BUY, FEE_SELL = 15.0, 25.0
SEED = 20260923
N_PLACEBO = 20
N_TRIALS_BEFORE = 699
H = 90
BAR = {"fills": 100, "net": 20.0, "t": 2.0, "placebo_pct": 95.0}
ARMS = [(hi, c, ex) for hi in ("q80", "q90") for c in ("cancel", "hold") for ex in ("t15", "signal")]


def load_prints(conn: psycopg.Connection, day: date) -> dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]]:
    with conn.cursor() as cur:
        cur.execute("""SELECT code, to_timestamp(floor(extract(epoch FROM ts) / 10) * 10) AT TIME ZONE 'Asia/Jakarta', price, sum(qty)
                       FROM idx.feed_trade WHERE (ts AT TIME ZONE 'Asia/Jakarta')::date = %s AND verb IS NOT NULL GROUP BY 1, 2, 3""", (day,))
        T = pd.DataFrame(cur.fetchall(), columns=["code", "t", "price", "qty"])
    T["t"] = pd.to_datetime(T["t"]).astype("int64")
    T["price"] = T["price"].astype(float)
    T["qty"] = T["qty"].astype(float)
    return {c: (g["t"].to_numpy(), g["price"].to_numpy(), g["qty"].to_numpy()) for c, g in T.groupby("code")}


def per_step_le(prints: tuple, tgrid: np.ndarray, L: float, j0: int, j1: int) -> np.ndarray:
    """Printed volume at price <= L in each grid bucket j0..j1 (inclusive)."""
    ts, px, q = prints
    out = np.zeros(j1 - j0 + 1)
    m = px <= L + 1e-9
    if not m.any():
        return out
    ts, q = ts[m], q[m]
    keys = tgrid[j0:j1 + 1]
    idx = np.searchsorted(keys, ts)
    ok = (idx < len(keys)) & (ts == keys[np.minimum(idx, len(keys) - 1)])
    np.add.at(out, idx[ok], q[ok])
    return out


def simulate(x: dict, prints: tuple | None, p: np.ndarray, p_hi: float, p_lo: float, cancel: bool, exit_rule: str) -> list[dict]:
    bid, off, mid, sess = x["bid1"], x["off1"], x["mid"], x["session"]
    bv1 = x["raw"][:, 1].astype(float)
    tg = pd.DatetimeIndex(x["t"]).asi8
    n = len(bid)
    out = []
    i = 0
    while i < n - 1:
        if not (np.isfinite(p[i]) and p[i] >= p_hi and np.isfinite(bid[i]) and bid[i] > 0 and bv1[i] > 0):
            i += 1
            continue
        L, ahead = bid[i], bv1[i]
        jmax = i
        while jmax + 1 < n and jmax + 1 <= i + H and sess[jmax + 1] == sess[i]:
            jmax += 1
        vol = per_step_le(prints, tg, L, i + 1, jmax) if prints is not None and jmax > i else np.zeros(max(jmax - i, 0))
        fill, cum, cancelled = None, 0.0, False
        for j in range(i + 1, jmax + 1):
            if cancel and np.isfinite(p[j]) and p[j] < p_lo:
                cancelled = True
                break
            cum += vol[j - i - 1]
            if cum >= ahead:
                fill = j
                break
        if fill is None:
            out.append({"posted": 1, "filled": 0, "cancelled": int(cancelled)})
            i = (j if cancelled else jmax) + 1
            continue
        kmax = fill
        while kmax + 1 < n and kmax + 1 <= fill + H and sess[kmax + 1] == sess[fill]:
            kmax += 1
        k = kmax
        if exit_rule == "signal":
            for kk in range(fill + 1, kmax + 1):
                if np.isfinite(p[kk]) and p[kk] < p_lo:
                    k = kk
                    break
        while k > fill and not np.isfinite(bid[k]):
            k -= 1
        px_out = bid[k] if np.isfinite(bid[k]) else L
        m5 = mid[min(fill + 30, kmax)]
        out.append({"posted": 1, "filled": 1, "cancelled": 0, "net": (px_out / L - 1) * 1e4 - FEE_BUY - FEE_SELL,
                    "adverse": int(np.isfinite(m5) and m5 < L), "wait_steps": fill - i, "hold_steps": k - fill})
        i = k + 1
    return out


def summarise(rows: list[dict]) -> dict:
    r = pd.DataFrame(rows)
    if not len(r):
        return {"posted": 0, "fills": 0}
    f = r[r["filled"] == 1]
    a = f["net"].to_numpy(float) if len(f) else np.asarray([])
    return {"posted": int(len(r)), "fills": int(len(f)), "fill_rate": float(len(f) / len(r)), "cancelled": float(r["cancelled"].mean()),
            "mean": float(a.mean()) if len(a) else np.nan, "median": float(np.median(a)) if len(a) else np.nan,
            "t": float(a.mean() / a.std(ddof=1) * np.sqrt(len(a))) if len(a) > 2 and a.std(ddof=1) > 0 else np.nan,
            "p_win": float((a > 0).mean()) if len(a) else np.nan, "net_per_post": float(a.sum() / len(r)) if len(r) else np.nan,
            "adverse": float(f["adverse"].mean()) if len(f) else np.nan,
            "wait_min": float(f["wait_steps"].median() / 6) if len(f) else np.nan, "hold_min": float(f["hold_steps"].median() / 6) if len(f) else np.nan}


def run(dsn: str, d_train: date, d_test: date, out_path: str, store: bool, study_name: str) -> dict:
    t0 = time.time()
    with psycopg.connect(dsn) as conn:
        TR, TE = lob.build_day(conn, d_train), lob.build_day(conn, d_test)
        prints = load_prints(conn, d_test)
    common = sorted(set(TR) & set(TE))
    TR, TE = {c: TR[c] for c in common}, {c: TE[c] for c in common}
    Ptr, Pte = lob.panel(TR), lob.panel(TE)
    tr, te = Ptr.dropna(subset=[*lob.FEATS, "h5m"]), Pte.dropna(subset=lob.FEATS)
    p_te, _, info = lob.lgb_models(tr, te, "h5m")                    # P(up 5 min) on the test day
    p_tr, _, _ = lob.lgb_models(tr, tr, "h5m")                       # same fit (same seed) scored on the train day → thresholds
    q = {k: float(np.quantile(p_tr, v)) for k, v in (("q50", 0.5), ("q80", 0.8), ("q90", 0.9))}
    score = {}
    te_idx = te.assign(p=p_te)
    for code, g in te_idx.groupby("code"):
        s = np.full(TE[code]["n"], np.nan)
        s[g["i"].to_numpy()] = g["p"].to_numpy()
        score[code] = s
    rng = np.random.default_rng(SEED)
    res: dict = {"desc": {"train": d_train.isoformat(), "test": d_test.isoformat(), "names": len(common), "thresholds": q,
                          "auc_test": lob.model_reads(te.dropna(subset=["h5m"]), p_te[te["h5m"].notna().to_numpy()], "h5m")["auc_name_median"]},
                 "arms": {}}
    shuffled = [{c: rng.permutation(score[c]) for c in common} for _ in range(N_PLACEBO)]
    for hi, c, ex in ARMS:
        rows = []
        for code in common:
            rows += simulate(TE[code], prints.get(code), score[code], q[hi], q["q50"], c == "cancel", ex)
        r = summarise(rows)
        pl = []
        for k in range(N_PLACEBO):
            prow = []
            for code in common:
                prow += simulate(TE[code], prints.get(code), shuffled[k][code], q[hi], q["q50"], c == "cancel", ex)
            s = summarise(prow)
            pl.append(s.get("mean", np.nan))
        pl = np.asarray([v for v in pl if np.isfinite(v)])
        r["placebo_mean"] = float(pl.mean()) if len(pl) else np.nan
        r["placebo_pct"] = float((pl < r["mean"]).mean() * 100) if len(pl) and np.isfinite(r["mean"]) else np.nan
        r["CANDIDATE"] = bool(r["fills"] >= BAR["fills"] and np.isfinite(r["mean"]) and r["mean"] >= BAR["net"] and np.isfinite(r["t"]) and r["t"] >= BAR["t"]
                              and np.isfinite(r["placebo_pct"]) and r["placebo_pct"] >= BAR["placebo_pct"])
        res["arms"][f"{hi}/{c}/{ex}"] = r
    res["verdict"] = {"candidates": [k for k, v in res["arms"].items() if v["CANDIDATE"]], "n_trials": len(ARMS)}
    res["log"] = [f"{time.time() - t0:.0f} s"]
    write_report(res, out_path)
    if store:
        from blackheart_ingest.idx import research_store as rs
        with psycopg.connect(dsn) as conn:
            sid = rs.record_study(conn, study_name, d_test, params={"trials": list(res["arms"]), "n_trials_cumulative": N_TRIALS_BEFORE + len(ARMS),
                                                                    "fees": [FEE_BUY, FEE_SELL], "H": H, "bar": BAR, "seed": SEED, "thresholds": q},
                                 summary=json.loads(json.dumps(res, default=str)), names=[], report_path=out_path,
                                 note=f"candidates {res['verdict']['candidates'] or 'none'}")
            res["study_id"] = sid
    return res


def write_report(res: dict, path: str) -> None:
    d = res["desc"]
    f = lambda x, fmt: (fmt % x) if x is not None and np.isfinite(x) else "-"  # noqa: E731
    L = [f"# IDX menu 28b-1 PRELIM — maker bid on P(up), cancelled when the direction turns — train {d['train']} → test {d['test']}", "",
         f"{d['names']} names; P(up 5 min) LightGBM, test-day per-name AUC {d['auc_test']:.3f}; thresholds q50 {d['thresholds']['q50']:.3f}, q80 {d['thresholds']['q80']:.3f}, q90 {d['thresholds']['q90']:.3f}.",
         f"Queue-aware fills (join the back of bv1), fees 15 + 25 bps, 15-min deadline. Pre-registered in `research/idx_maker_cancel.py`; {res['verdict']['n_trials']} trials (cumulative {N_TRIALS_BEFORE + res['verdict']['n_trials']}).",
         "**One test day: a direction read, not an adoption.**", "",
         "| post at | order | exit | posted | fills | fill rate | cancelled | wait (min) | hold (min) | net/fill mean | median | t | P(win) | adverse (mid −5 min < L) | net/post | placebo mean | placebo pct | verdict |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for k, r in res["arms"].items():
        hi, c, ex = k.split("/")
        L.append(f"| {hi} | {c} | {ex} | {r['posted']:,} | {r['fills']:,} | {f(r.get('fill_rate', np.nan) * 100, '%.0f')} % | {f(r.get('cancelled', np.nan) * 100, '%.0f')} % | "
                 f"{f(r.get('wait_min', np.nan), '%.1f')} | {f(r.get('hold_min', np.nan), '%.1f')} | {f(r.get('mean', np.nan), '%+.1f')} | {f(r.get('median', np.nan), '%+.1f')} | {f(r.get('t', np.nan), '%.2f')} | "
                 f"{f(r.get('p_win', np.nan) * 100, '%.0f')} % | {f(r.get('adverse', np.nan) * 100, '%.0f')} % | {f(r.get('net_per_post', np.nan), '%+.2f')} | {f(r.get('placebo_mean', np.nan), '%+.1f')} | "
                 f"{f(r.get('placebo_pct', np.nan), '%.0f')} | {'CANDIDATE (1 test day)' if r['CANDIDATE'] else 'no'} |")
    L += ["", "## Reading", "", f"- Candidates by the bar (>= 100 fills, >= +20 bps/fill, t >= 2, placebo >= 95): {', '.join(res['verdict']['candidates']) or 'none'}.",
          "- 'cancel' pulls the bid the moment P(up) drops below the train-day median; 'hold' leaves it for 15 min. The placebo posts and cancels",
          "  from a shuffled score, so it measures what a maker bid earns at random times with the same mechanics.",
          "- Compare 'adverse': the share of fills after which the mid is below the fill price 5 min later — the adverse selection the cancel is meant to avoid.",
          "- Re-run at >= 20 sessions.", ""]
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(L))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", default="2026-09-22")
    ap.add_argument("--test", default="2026-09-23")
    ap.add_argument("--no-store", action="store_true")
    ap.add_argument("--out", default="")
    ap.add_argument("--study-name", default="maker_cancel")
    a = ap.parse_args()
    out = a.out or os.path.join(HERE, f"IDX_MAKER_CANCEL_{a.test}.md")
    res = run(os.environ["INGEST_DB_DSN"], date.fromisoformat(a.train), date.fromisoformat(a.test), out, not a.no_store, a.study_name)
    print(json.dumps({"desc": res["desc"], "arms": {k: {x: v.get(x) for x in ("posted", "fills", "mean", "t", "adverse", "placebo_pct", "CANDIDATE")} for k, v in res["arms"].items()},
                      "verdict": res["verdict"], "study_id": res.get("study_id"), "report": out}, indent=1, default=str))


if __name__ == "__main__":
    main()
