#!/usr/bin/env python3
"""IDX menu 28b-0 — "will the price go up, and when should we post the order?": a calibrated probability of an upward mid move
from the desk's own tick feed, plus the only policy that can monetise it for a retail account: a MAKER order posted when (a) the
model says up and (b) the bid queue is thin enough that the order actually fills before the move (operator, 2026-09-22: "bisa nggak
kamu research supaya prediksi harga akan naik atau bikin probabilitas kapan kita harus melakukan itu").

Why this shape. Menu 28 showed the book predicts the mid (OBI1 IC 0.23, t 21) but a taker cannot pay the spread, and a maker who
joins a THICK bid queue fills only when the level breaks (queue-aware net -87 bps, fill 2 %). So the question is not "will it go
up" alone; it is "will it go up AND can my order be near the front". Both are measured here.

DESIGN (pre-registered; re-run nightly as sessions accumulate - one session today, so morning = train, afternoon = test; from the
second session on, train = all earlier sessions, test = the latest one, and the halves split is retired).
  Panel      one row per (name, minute) in the continuous phases; names with >= 150 valid minutes; book carried forward inside a session.
  Features   book: OBI1, OBI5, OBIT, dOBI1 (OBI1_t - OBI1_{t-3}), SPRD (bps), depth ratio bv1 / bv5, ov1 / ov5, n_updates
             tape: TFI5, vol_surge (volume_t+..t-4 / mean 30-min volume), n_trades_5
             price: RET5, RET15, RET30, pos_day (mid / first mid of the day - 1), dist_hi / dist_lo (ticks from the day's running high / low)
             queue: q_thin = bv1 / printed volume at <= bid over the last 5 min (small = the queue can clear)
             (no minute-of-day: on one session it is the drift curve)
  Targets    UP15  = mid_{t+15} - mid_t >= +1 tick           (close-to-close, what a holder earns)
             TOUCH = max(mid_{t+1..t+15}) - mid_t >= +1 tick  (an exit at +1 tick was available)
  Model      LightGBM binary, 400 rounds, lr 0.03, 15 leaves, min 200 rows per leaf, bagging 0.8; probabilities read raw and after
             isotonic-free bin calibration (10 bins of predicted p -> realised rate).
  Reads      AUC on the test half; calibration table (bin, mean p, realised rate, n); lift of the top decile.
  Policy     at minute t with P(UP15) >= p*: post a buy at bid_t; queue-aware fill (join the back: filled when prints at <= bid cumulate past
             bv1 within 5 min); then post the sell at the offer seen at the fill; queue-aware; unsold after 15 min -> sell at the bid.
             Fees 30 bps. Grid p* in {0.5, 0.6, 0.7} x queue filter {any, thin: q_thin <= 2} = 6 policies (the trials).
  Two-sided  (operator, same day) quote bid AND offer together from inventory; both fill -> spread - fees; a lone leg is closed at
             the far side at the deadline ('deadline') or as soon as the mid moves a tick against it ('stop'); conditions 'bal'
             (|OBI1| <= 0.2 and 5-min trades >= the name's median) or 'any' = 4 trials. Total 10 trials (cumulative 520).
  Bar        CANDIDATE: on the test half, >= 100 fills, mean net >= +10 bps, P(net > 0) >= 50 %. Anything less = "not yet"; one session
             never adopts anything - the bar has to hold on >= 20 sessions (menu 28b).

READ-ONLY. INGEST_DB_DSN=... PYTHONIOENCODING=utf-8 blackheart-ingest/.venv/Scripts/python research/idx_updown_prob.py [--days 2026-09-22]
  [--no-store] [--out research/IDX_UPDOWN_PROB_<day>.md]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime

import numpy as np
import pandas as pd
import psycopg
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "blackheart-ingest", "src"))

SESSIONS_MON_THU = (("09:00", "11:59"), ("13:30", "15:49"))
SESSIONS_FRI = (("09:00", "11:29"), ("14:00", "15:49"))
TICKS = ((200, 1), (500, 2), (2000, 5), (5000, 10), (float("inf"), 25))
MIN_MINUTES = 150
FEE_BPS = 30.0
SEED = 20260922
H = 15
FEATS = ["OBI1", "OBI5", "OBIT", "dOBI1", "SPRD", "depth_b", "depth_o", "n_updates", "TFI5", "vol_surge", "n_trades_5",
         "RET5", "RET15", "RET30", "pos_day", "dist_hi", "dist_lo", "q_thin"]
POLICIES = [(p, q) for p in (0.5, 0.6, 0.7) for q in ("any", "thin")]
N_TRIALS_BEFORE = 510
MIN_NS = 60_000_000_000.0


def tick_size(px: np.ndarray) -> np.ndarray:
    out = np.full(px.shape, 25.0)
    for lim, t in reversed(TICKS[:-1]):
        out[px < lim] = t
    return out


def sessions_for(day: date) -> list[pd.DatetimeIndex]:
    spec = SESSIONS_FRI if day.weekday() == 4 else SESSIONS_MON_THU
    return [pd.date_range(datetime.combine(day, datetime.strptime(a, "%H:%M").time()),
                          datetime.combine(day, datetime.strptime(b, "%H:%M").time()), freq="1min") for a, b in spec]


# ------------------------------------------------------------------------------------------------------------------ data
def load_day(conn: psycopg.Connection, day: date) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, np.ndarray]]:
    with conn.cursor() as cur:
        cur.execute("""SELECT minute AT TIME ZONE 'Asia/Jakarta', code, bid_px[1], off_px[1], bid_vol[1], off_vol[1],
                              (SELECT sum(x) FROM unnest(bid_vol[1:5]) x), (SELECT sum(x) FROM unnest(off_vol[1:5]) x), bid_total, off_total, n_updates
                       FROM idx.feed_book_1m WHERE (minute AT TIME ZONE 'Asia/Jakarta')::date = %s AND code <> 'IHSG'""", (day,))
        book = pd.DataFrame(cur.fetchall(), columns=["minute", "code", "bid1", "off1", "bv1", "ov1", "bv5", "ov5", "bid_total", "off_total", "n_updates"])
        cur.execute("""SELECT minute AT TIME ZONE 'Asia/Jakarta', code, high, low, volume, buy_volume, sell_volume, n_trades
                       FROM idx.feed_bar_1m WHERE (minute AT TIME ZONE 'Asia/Jakarta')::date = %s AND code <> 'IHSG'""", (day,))
        bars = pd.DataFrame(cur.fetchall(), columns=["minute", "code", "high", "low", "volume", "buy_volume", "sell_volume", "n_trades"])
        cur.execute("""SELECT date_trunc('minute', ts AT TIME ZONE 'Asia/Jakarta'), code, price, sum(qty) FROM idx.feed_trade
                       WHERE (ts AT TIME ZONE 'Asia/Jakarta')::date = %s GROUP BY 1, 2, 3""", (day,))
        T = pd.DataFrame(cur.fetchall(), columns=["minute", "code", "price", "qty"])
    for df in (book, bars, T):
        df["minute"] = pd.to_datetime(df["minute"])
        for c in df.columns:
            if c not in ("minute", "code"):
                df[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
    T["m"] = T["minute"].astype("int64").astype(float)
    prints = {c: g[["m", "price", "qty"]].to_numpy(dtype=float) for c, g in T.groupby("code")}
    return book, bars, prints


def vol_at(prints: dict[str, np.ndarray], code: str, m0: float, m1: float, cond: str, level: float) -> float:
    a = prints.get(code)
    if a is None:
        return 0.0
    mask = (a[:, 0] > m0) & (a[:, 0] <= m1) & ((a[:, 1] <= level) if cond == "le" else (a[:, 1] >= level))
    return float(a[mask, 2].sum())


def build_panel(book: pd.DataFrame, bars: pd.DataFrame, prints: dict[str, np.ndarray], day: date) -> pd.DataFrame:
    rows = []
    for code, b in book.groupby("code"):
        b = b.set_index("minute").sort_index()
        r = bars[bars["code"] == code].set_index("minute").sort_index()
        parts = []
        for si, idx in enumerate(sessions_for(day)):
            s = b.reindex(idx).ffill()
            s["session"] = si
            s = s.join(r.reindex(idx)[["high", "low", "volume", "buy_volume", "sell_volume", "n_trades"]].fillna(0.0))
            parts.append(s)
        s = pd.concat(parts)
        s["code"] = code
        s["day"] = day
        ok = (s["bid1"] > 0) & (s["off1"] > s["bid1"])
        s.loc[~ok, ["bid1", "off1"]] = np.nan
        s["mid"] = (s["bid1"] + s["off1"]) / 2
        s["tick"] = tick_size(s["mid"].to_numpy(dtype=float))
        s["SPRD"] = (s["off1"] - s["bid1"]) / s["mid"] * 1e4
        s["OBI1"] = (s["bv1"] - s["ov1"]) / (s["bv1"] + s["ov1"])
        s["OBI5"] = (s["bv5"] - s["ov5"]) / (s["bv5"] + s["ov5"])
        s["OBIT"] = (s["bid_total"] - s["off_total"]) / (s["bid_total"] + s["off_total"])
        s["depth_b"] = s["bv1"] / s["bv5"]
        s["depth_o"] = s["ov1"] / s["ov5"]
        g = s.groupby("session", group_keys=False)
        s["dOBI1"] = s["OBI1"] - g["OBI1"].shift(3)
        bs = g["buy_volume"].rolling(5, min_periods=1).sum().reset_index(level=0, drop=True)
        ss = g["sell_volume"].rolling(5, min_periods=1).sum().reset_index(level=0, drop=True)
        s["TFI5"] = (bs - ss) / (bs + ss)
        v5 = g["volume"].rolling(5, min_periods=1).sum().reset_index(level=0, drop=True)
        v30 = g["volume"].rolling(30, min_periods=5).mean().reset_index(level=0, drop=True)
        s["vol_surge"] = (v5 / 5) / v30
        s["n_trades_5"] = g["n_trades"].rolling(5, min_periods=1).sum().reset_index(level=0, drop=True)
        for k in (5, 15, 30):
            s[f"RET{k}"] = s["mid"] / g["mid"].shift(k) - 1
        first = s["mid"].dropna().iloc[0] if s["mid"].notna().any() else np.nan
        s["pos_day"] = s["mid"] / first - 1
        run_hi = s["mid"].cummax()
        run_lo = s["mid"].cummin()
        s["dist_hi"] = (run_hi - s["mid"]) / s["tick"]
        s["dist_lo"] = (s["mid"] - run_lo) / s["tick"]
        mins = s.index.astype("int64").to_numpy(dtype=float)
        bid = s["bid1"].to_numpy()
        flow = np.array([vol_at(prints, code, mins[i] - 5 * MIN_NS, mins[i], "le", bid[i]) if np.isfinite(bid[i]) else np.nan for i in range(len(s))])
        s["flow5_bid"] = flow
        s["q_thin"] = s["bv1"] / np.where(flow > 0, flow, np.nan)
        fwd = g["mid"].shift(-H)
        s["UP15"] = ((fwd - s["mid"]) >= s["tick"] - 1e-9).astype(float)
        s.loc[fwd.isna(), "UP15"] = np.nan
        fmax = g["mid"].transform(lambda x: x[::-1].rolling(H, min_periods=H).max()[::-1].shift(-1))
        s["TOUCH"] = ((fmax - s["mid"]) >= s["tick"] - 1e-9).astype(float)
        s.loc[fmax.isna(), "TOUCH"] = np.nan
        s["fwd15_bps"] = (fwd / s["mid"] - 1) * 1e4
        rows.append(s.reset_index().rename(columns={"index": "minute"}))
    P = pd.concat(rows, ignore_index=True)
    P = P.dropna(subset=["mid", "OBI1"])
    n = P.groupby(["day", "code"])["mid"].transform("size")
    return P[n >= MIN_MINUTES].copy()


# --------------------------------------------------------------------------------------------------------------- model
def auc_score(y: np.ndarray, p: np.ndarray) -> float:
    r = stats.rankdata(p)
    n1 = int(y.sum())
    n0 = len(y) - n1
    return float("nan") if n1 == 0 or n0 == 0 else float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def fit_predict(tr: pd.DataFrame, te: pd.DataFrame, target: str) -> tuple[np.ndarray, dict[str, float]]:
    import lightgbm as lgb
    params = {"objective": "binary", "learning_rate": 0.03, "num_leaves": 15, "min_data_in_leaf": 200, "bagging_fraction": 0.8,
              "bagging_freq": 1, "feature_fraction": 0.8, "lambda_l2": 5.0, "seed": SEED, "verbose": -1}
    m = lgb.train(params, lgb.Dataset(tr[FEATS].to_numpy(dtype=float), label=tr[target].to_numpy(), feature_name=FEATS), num_boost_round=400)
    p = np.asarray(m.predict(te[FEATS].to_numpy(dtype=float)))
    gain = np.asarray(m.feature_importance(importance_type="gain"), dtype=float)
    return p, dict(zip(FEATS, (gain / gain.sum()).round(3).tolist(), strict=True))


def calibration(y: np.ndarray, p: np.ndarray, bins: int = 10) -> list[dict]:
    edges = np.quantile(p, np.linspace(0, 1, bins + 1))
    out = []
    for i in range(bins):
        m = (p >= edges[i]) & (p <= edges[i + 1] if i == bins - 1 else p < edges[i + 1])
        if m.sum():
            out.append({"bin": i + 1, "p_mean": float(p[m].mean()), "realised": float(y[m].mean()), "n": int(m.sum())})
    return out


# -------------------------------------------------------------------------------------------------------------- policy
def maker_policy(te: pd.DataFrame, p: np.ndarray, prints: dict[str, np.ndarray], p_star: float, queue: str, W: int = 5, X: int = 15) -> dict:
    te = te.assign(p=p)
    out = []
    for code, s in te.groupby("code"):
        s = s.sort_values("minute").reset_index(drop=True)
        mins = s["minute"].astype("int64").to_numpy(dtype=float)
        sess, bid, ask = s["session"].to_numpy(), s["bid1"].to_numpy(), s["off1"].to_numpy()
        bv, ov, pp, qt, tick = s["bv1"].to_numpy(), s["ov1"].to_numpy(), s["p"].to_numpy(), s["q_thin"].to_numpy(), s["tick"].to_numpy()
        n, i = len(s), 0
        while i < n - 1:
            go = pp[i] >= p_star and np.isfinite(bid[i]) and bv[i] > 0 and (queue == "any" or (np.isfinite(qt[i]) and qt[i] <= 2.0))
            if not go:
                i += 1
                continue
            fill, cum = None, 0.0
            for j in range(i + 1, min(i + 1 + W, n)):
                if sess[j] != sess[i]:
                    break
                cum += vol_at(prints, code, mins[j - 1], mins[j], "le", bid[i])
                if cum >= bv[i]:
                    fill = j
                    break
            if fill is None:
                out.append({"filled": 0})
                i += 1
                continue
            px_in = bid[i]
            px_ask = ask[fill] if np.isfinite(ask[fill]) else ask[i]
            ahead = ov[fill] if np.isfinite(ov[fill]) else ov[i]
            sold, cum = None, 0.0
            for k in range(fill + 1, min(fill + 1 + X, n)):
                if sess[k] != sess[fill]:
                    break
                cum += vol_at(prints, code, mins[k - 1], mins[k], "ge", px_ask)
                if cum >= ahead:
                    sold = k
                    break
            if sold is not None:
                px_out = px_ask
            else:
                k = min(fill + X, n - 1)
                while k > fill and (sess[k] != sess[fill] or not np.isfinite(bid[k])):
                    k -= 1
                px_out = bid[k] if np.isfinite(bid[k]) else px_in
            gross = (px_out / px_in - 1) * 1e4
            out.append({"filled": 1, "sold_at_ask": int(sold is not None), "net_bps": gross - FEE_BPS, "ticks": (px_out - px_in) / tick[i]})
            i = (sold if sold is not None else min(fill + X, n - 1)) + 1
    r = pd.DataFrame(out)
    f = r[r["filled"] == 1] if len(r) else r
    res = {"p_star": p_star, "queue": queue, "signals": len(r), "fills": len(f),
           "fill_rate": float(len(f) / len(r)) if len(r) else float("nan"),
           "sold_at_ask": float(f["sold_at_ask"].mean()) if len(f) else float("nan"),
           "net_bps": float(f["net_bps"].mean()) if len(f) else float("nan"),
           "p_win": float((f["net_bps"] > 0).mean()) if len(f) else float("nan"),
           "net_per_signal_bps": float(f["net_bps"].sum() / len(r)) if len(r) else float("nan")}
    res["CANDIDATE"] = bool(res["fills"] >= 100 and res["net_bps"] >= 10 and res["p_win"] >= 0.5)
    return res


def two_sided_policy(te: pd.DataFrame, prints: dict[str, np.ndarray], cond: str, exit_rule: str, X: int = 15) -> dict:
    """The operator's idea (2026-09-22): quote BOTH sides at once from inventory - a buy at the bid and a sell at the offer - and
    earn the spread when both fill; if only one leg fills and the other does not come, get out. ``cond``: 'bal' = quote only when
    the book is balanced (|OBI1| <= 0.2) and the name is active (5-min trades >= its median), 'any' = always. ``exit_rule``:
    'deadline' = the lone leg is closed at the far side after X minutes; 'stop' = also closed the minute the mid moves one tick
    against it. Fees 30 bps per round trip (10 buy + 20 sell). Queue-aware fills on both legs."""
    out = []
    for code, s in te.groupby("code"):
        s = s.sort_values("minute").reset_index(drop=True)
        mins = s["minute"].astype("int64").to_numpy(dtype=float)
        sess, bid, ask, mid = s["session"].to_numpy(), s["bid1"].to_numpy(), s["off1"].to_numpy(), s["mid"].to_numpy()
        bv, ov, obi, tick = s["bv1"].to_numpy(), s["ov1"].to_numpy(), s["OBI1"].to_numpy(), s["tick"].to_numpy()
        act = s["n_trades_5"].to_numpy()
        act_med = float(np.nanmedian(act)) if np.isfinite(act).any() else 0.0
        n, i = len(s), 0
        while i < n - 1:
            ok = np.isfinite(bid[i]) and np.isfinite(ask[i]) and bv[i] > 0 and ov[i] > 0
            if cond == "bal":
                ok = ok and abs(obi[i]) <= 0.2 and act[i] >= act_med
            if not ok:
                i += 1
                continue
            pb, pa = bid[i], ask[i]
            cb = ca = 0.0
            fb = fa = None
            end = i
            for j in range(i + 1, min(i + 1 + X, n)):
                if sess[j] != sess[i]:
                    break
                end = j
                if fb is None:
                    cb += vol_at(prints, code, mins[j - 1], mins[j], "le", pb)
                    if cb >= bv[i]:
                        fb = j
                if fa is None:
                    ca += vol_at(prints, code, mins[j - 1], mins[j], "ge", pa)
                    if ca >= ov[i]:
                        fa = j
                if fb is not None and fa is not None:
                    break
                if exit_rule == "stop" and np.isfinite(mid[j]):
                    if fb is not None and fa is None and mid[j] <= pb - tick[i]:       # long leg under water by a tick -> out at the bid
                        break
                    if fa is not None and fb is None and mid[j] >= pa + tick[i]:       # short leg under water by a tick -> out at the offer
                        break
            if fb is None and fa is None:
                out.append({"kind": "none"})
                i = end + 1
                continue
            if fb is not None and fa is not None:
                net = (pa / pb - 1) * 1e4 - FEE_BPS
                out.append({"kind": "both", "net_bps": net})
            elif fb is not None:                                                  # bought, never sold -> sell at the bid now
                px_out = bid[end] if np.isfinite(bid[end]) else pb
                out.append({"kind": "buy_only", "net_bps": (px_out / pb - 1) * 1e4 - FEE_BPS})
            else:                                                                 # sold, never bought back -> buy at the offer now
                px_in = ask[end] if np.isfinite(ask[end]) else pa
                out.append({"kind": "sell_only", "net_bps": (pa / px_in - 1) * 1e4 - FEE_BPS})
            i = end + 1
    r = pd.DataFrame(out)
    f = r[r["kind"] != "none"] if len(r) else r
    kinds = f["kind"].value_counts().to_dict() if len(f) else {}
    res = {"cond": cond, "exit": exit_rule, "quotes": len(r), "fills": len(f), "both": int(kinds.get("both", 0)),
           "buy_only": int(kinds.get("buy_only", 0)), "sell_only": int(kinds.get("sell_only", 0)),
           "net_bps": float(f["net_bps"].mean()) if len(f) else float("nan"),
           "net_both": float(f.loc[f["kind"] == "both", "net_bps"].mean()) if kinds.get("both") else float("nan"),
           "net_lone": float(f.loc[f["kind"] != "both", "net_bps"].mean()) if len(f) and kinds.get("both", 0) < len(f) else float("nan"),
           "p_win": float((f["net_bps"] > 0).mean()) if len(f) else float("nan"),
           "net_per_quote_bps": float(f["net_bps"].sum() / len(r)) if len(r) else float("nan")}
    res["CANDIDATE"] = bool(res["fills"] >= 100 and res["net_bps"] >= 10 and res["p_win"] >= 0.5)
    return res


TWO_SIDED = [(c, e) for c in ("bal", "any") for e in ("deadline", "stop")]


# ----------------------------------------------------------------------------------------------------------------- run
def run(dsn: str, days: list[date], out_path: str, store: bool, study_name: str) -> dict:
    panels, prints_all = [], {}
    with psycopg.connect(dsn) as conn:
        for d in days:
            book, bars, prints = load_day(conn, d)
            if book.empty:
                continue
            panels.append(build_panel(book, bars, prints, d))
            prints_all[d] = prints
    P = pd.concat(panels, ignore_index=True)
    test_day = max(prints_all)
    if len(prints_all) == 1:                                                    # one session: morning -> afternoon
        tr, te = P[P["session"] == 0], P[P["session"] == 1]
        split = "morning -> afternoon (single session)"
    else:
        tr, te = P[P["day"] < test_day], P[P["day"] == test_day]
        split = f"{len(prints_all) - 1} earlier session(s) -> {test_day}"
    res: dict = {"desc": {"days": [d.isoformat() for d in prints_all], "split": split, "names": int(P["code"].nunique()),
                          "rows_train": len(tr), "rows_test": len(te),
                          "base_UP15": float(te["UP15"].mean()), "base_TOUCH": float(te["TOUCH"].mean())}, "models": {}}
    trm = tr.dropna(subset=[*FEATS, "UP15", "TOUCH"])
    tem = te.dropna(subset=[*FEATS, "UP15", "TOUCH"])
    for target in ("UP15", "TOUCH"):
        p, imp = fit_predict(trm, tem, target)
        y = tem[target].to_numpy()
        top = p >= np.quantile(p, 0.9)
        res["models"][target] = {"auc": auc_score(y, p), "calibration": calibration(y, p), "importance": imp,
                                 "top_decile": {"p_mean": float(p[top].mean()), "realised": float(y[top].mean()), "lift": float(y[top].mean() / y.mean()),
                                                "fwd15_bps": float(tem.loc[top, "fwd15_bps"].mean())}}
        if target == "UP15":
            p_up = p
    res["policies"] = [maker_policy(tem, p_up, prints_all[test_day], ps, q) for ps, q in POLICIES]
    res["two_sided"] = [two_sided_policy(tem, prints_all[test_day], c, e) for c, e in TWO_SIDED]
    res["verdict"] = {"candidates": [f"p*={r['p_star']} queue={r['queue']}" for r in res["policies"] if r["CANDIDATE"]]
                      + [f"two-sided {r['cond']}/{r['exit']}" for r in res["two_sided"] if r["CANDIDATE"]]}
    write_report(res, out_path)
    if store:
        from blackheart_ingest.idx import research_store as rs
        with psycopg.connect(dsn) as conn:
            sid = rs.record_study(conn, study_name, test_day, params={"trials": [f"p*={p} queue={q}" for p, q in POLICIES] + [f"two-sided {c}/{e}" for c, e in TWO_SIDED],
                                                                      "n_trials_cumulative": N_TRIALS_BEFORE + len(POLICIES) + len(TWO_SIDED),
                                                                      "features": FEATS, "H": H, "fee_bps": FEE_BPS, "seed": SEED, "days": res["desc"]["days"]},
                                 summary=json.loads(json.dumps(res, default=str)), names=[], report_path=out_path,
                                 note=f"AUC UP15 {res['models']['UP15']['auc']:.3f} TOUCH {res['models']['TOUCH']['auc']:.3f}; candidates {res['verdict']['candidates'] or 'none'}")
            res["study_id"] = sid
    return res


def write_report(res: dict, path: str) -> None:
    d = res["desc"]
    L = [f"# IDX menu 28b-0 — P(up) and when to post the order — {d['days'][-1]}", "",
         f"Sessions {', '.join(d['days'])}; split {d['split']}; {d['names']} names; train {d['rows_train']:,} / test {d['rows_test']:,} name-minutes.",
         f"Base rates on the test half: UP15 (mid +1 tick after 15 min) {d['base_UP15']:.3f}; TOUCH (+1 tick reached within 15 min) {d['base_TOUCH']:.3f}.",
         "Pre-registered in `research/idx_updown_prob.py`; 6 one-sided + 4 two-sided policy trials (cumulative 520).", ""]
    for t, m in res["models"].items():
        L += [f"## Model {t} — AUC {m['auc']:.3f}", "", "| p-bin | mean p | realised | n |", "|---|---|---|---|"]
        L += [f"| {c['bin']} | {c['p_mean']:.3f} | {c['realised']:.3f} | {c['n']:,} |" for c in m["calibration"]]
        td = m["top_decile"]
        L += ["", f"- top decile: mean p {td['p_mean']:.3f}, realised {td['realised']:.3f} (lift {td['lift']:.2f}x), mean 15-min mid move {td['fwd15_bps']:+.1f} bps",
              f"- importance (gain share): {', '.join(f'{k} {v}' for k, v in sorted(m['importance'].items(), key=lambda kv: -kv[1])[:8])}", ""]
    L += ["## Maker policies on the test half (post at the bid when P(UP15) >= p*; queue-aware fills; sell at the offer; 15-min deadline; fee 30 bps)", "",
          "| p* | queue | signals | fills | fill rate | sold@offer | net bps/fill | P(win) | net bps/signal | verdict |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in res["policies"]:
        L.append(f"| {r['p_star']} | {r['queue']} | {r['signals']:,} | {r['fills']} | {r['fill_rate']*100:.0f} % | {r['sold_at_ask']*100 if r['fills'] else 0:.0f} % | "
                 f"{r['net_bps']:+.1f} | {r['p_win']*100 if r['fills'] else 0:.0f} % | {r['net_per_signal_bps']:+.2f} | {'CANDIDATE' if r['CANDIDATE'] else 'not yet'} |")
    L += ["", "## Two-sided quotes from inventory (bid and offer posted together; queue-aware; lone leg closed at the far side; fee 30 bps)", "",
          "| condition | exit | quotes | fills | both legs | buy only | sell only | net bps/fill | net both | net lone | P(win) | net/quote | verdict |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in res["two_sided"]:
        L.append(f"| {r['cond']} | {r['exit']} | {r['quotes']:,} | {r['fills']} | {r['both']} | {r['buy_only']} | {r['sell_only']} | {r['net_bps']:+.1f} | "
                 f"{r['net_both']:+.1f} | {r['net_lone']:+.1f} | {r['p_win']*100 if r['fills'] else 0:.0f} % | {r['net_per_quote_bps']:+.2f} | "
                 f"{'CANDIDATE' if r['CANDIDATE'] else 'not yet'} |")
    L += ["", "## Reading", "",
          f"- Candidates by the declared bar: {', '.join(res['verdict']['candidates']) or 'none'}.",
          "- The probability model answers 'will it go up'; the policy table answers 'can a retail order be there when it does'. A good AUC with",
          "  no candidate policy means the move is visible but the queue in front of a late order eats it (menu 28's finding).",
          "- Re-run nightly; from the second session the split is by day. Nothing is adoptable before 20 sessions.", ""]
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(L))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", default="2026-09-22", help="comma list; the last one is the test session")
    ap.add_argument("--no-store", action="store_true")
    ap.add_argument("--out", default="")
    ap.add_argument("--study-name", default="updown_prob")
    a = ap.parse_args()
    days = sorted(date.fromisoformat(x) for x in a.days.split(","))
    out = a.out or os.path.join(HERE, f"IDX_UPDOWN_PROB_{days[-1].isoformat()}.md")
    res = run(os.environ["INGEST_DB_DSN"], days, out, not a.no_store, a.study_name)
    print(json.dumps({"desc": res["desc"], "auc": {k: v["auc"] for k, v in res["models"].items()}, "verdict": res["verdict"],
                      "policies": [{k: r[k] for k in ("p_star", "queue", "fills", "net_bps", "p_win")} for r in res["policies"]],
                      "two_sided": [{k: r[k] for k in ("cond", "exit", "fills", "both", "net_bps", "p_win")} for r in res["two_sided"]],
                      "study_id": res.get("study_id"), "report": out}, indent=1, default=str))


if __name__ == "__main__":
    main()
