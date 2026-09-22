#!/usr/bin/env python3
"""IDX menu 26 — range trading in sideways names ("arbitrage di saham sideways", operator, 2026-09-22: SPTO, MTEL, PNIN as examples; use ML/DL
if it helps; find the universe of sideways names rather than naming them by hand).

What this is and is not. Buying the bottom of a range and selling the middle or the top is mean reversion inside a channel, not arbitrage: there is no
hedge, and the loss comes when the channel breaks. The desk has tested the neighbours of this idea and they died: support/resistance on the whole
universe (menu 20, 0 of 4), 2-5 day swing (46 trials, 0), sleepers (0), the per-name RSI entry on the value list (fragile, menu 25). What has NOT
been tested: a universe screened POINT-IN-TIME as sideways (the operator's examples are chosen with hindsight; SPTO and PNIN trade Rp 0.1-0.3 bn a
day and PNIN's yearly range was 37-219 %), channel levels from percentiles, targets at the channel mid / top instead of +1 %, and a model that
picks which touches of the floor bounce.

PRE-REGISTERED (15 trials; cumulative 479 + 15 = 494). Declared before the run; nothing tuned afterwards.
  Sideways screen at the signal close t, lookback L = 120 trading days, all of: |close_t / close_{t-L} - 1| <= 10 %; channel width (max/min - 1)
    between 8 % and 35 %; efficiency ratio |close_t - close_{t-L}| / sum |daily change| <= 0.25 (a choppy path, not a trend). Channel levels =
    10th / 50th / 90th percentiles of the L closes (lo / mid / hi), frozen at entry.
  Liquidity tiers: BLUE (>= Rp 20 bn/day, >= Rp 1,000), LIQ (>= Rp 5 bn, >= Rp 100), THIN (>= Rp 0.5 bn, >= Rp 100 - where SPTO / PNIN live).
    Costs = the quoted closing offer / bid + Stockbit fees 0.10 / 0.20 %, so a thin name pays its real spread.
  Entries (signal at close t, buy close t+1 at the offer; no signal on a name within 10 days of its last one):
    touch   close <= 1.02 x lo AND the day closed up (a bounce at the floor); ranked by 60-day traded value
    bb2     close <= 20-day mean - 2 sd; ranked by depth
    rsi30   RSI14 <= 30; ranked by depth
  Exits (signal at close, sell close t+1 at the bid): target close >= mid (`_mid`) or >= hi (`_hi`); stop close < 0.95 x lo (channel broken);
    time stop 60 trading days. Book K = 10 slots of NAV/10, one position per name.
  Rule trials (12): touch_mid, touch_hi, bb2_mid, rsi30_mid x {BLUE, LIQ, THIN}.
  ML trials (2): LightGBM (huber on the trade's net return) over every `touch` event (taken or not) on LIQ and THIN; walk-forward by year 2022-2026
    (train on events exited before the test year); filter = keep events above the training 67th percentile; book = touch_mid on the kept events.
    Features at the signal close: channel position / width / efficiency ratio, 5- and 20-day return, RSI14, 20-day vol, volume ratio, distance to
    MA50 / MA200, log value, log price, closing spread, foreign flow 5 / 20 d, touches of the floor in the last L days, the share of the name's
    earlier touches that reached the mid before the stop (only those already exited), COMPOSITE vs MA200 and its 20-day return, sector.
  DL trial (1): a GRU over the last 60 days of [log return, log volume ratio, channel position, close/MA20 - 1] per `touch` event on LIQ, same
    walk-forward and filter; run only if PyTorch is available in the venv (recorded as skipped otherwise).
  References (not trials): random entries in the same sideways universe with the same exit (seeded); the plain rule under the ML/DL comparison.
READING RULES (declared): money rule as menu 6 (>= 150 trades; avg net > 0 with t >= 2.5; Sharpe >= 1.0; mDD <= 25 %; >= 5 of 7 calendar years
  positive; Sharpe >= random + same exit + 0.5). A model is USEFUL only if Spearman IC > 0 in >= 3 of 5 test years AND its filtered book beats
  the plain rule by >= 0.15 Sharpe with a drawdown not deeper. Descriptive: SPTO / MTEL / PNIN - share of days inside the screen, touches, outcomes.
READ-ONLY. INGEST_DB_DSN=... PYTHONIOENCODING=utf-8 blackheart-ingest/.venv/Scripts/python research/idx_range.py [--no-dl] [--no-store]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import date

import numpy as np
import pandas as pd
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blackheart-ingest", "src"))
import idx_beyond as B  # noqa: E402
import idx_exit as E  # noqa: E402
import idx_swing2 as S  # noqa: E402
import idx_trend as T  # noqa: E402

N_BEFORE = 479
K = B.K
SEED = 20260923
L = 120
MAX_HOLD = 60
STOP = 0.95
ENTRIES = ["touch", "bb2", "rsi30"]
RULE_ARMS = ["touch_mid", "touch_hi", "bb2_mid", "rsi30_mid"]
TIERS = ["BLUE", "LIQ", "THIN"]
ARMS = [f"{a}|{u}" for u in TIERS for a in RULE_ARMS] + ["ml_touch_mid|LIQ", "ml_touch_mid|THIN", "dl_touch_mid|LIQ"]
assert len(ARMS) == 15
N_TRIALS = N_BEFORE + len(ARMS)
TEST_YEARS = [2022, 2023, 2024, 2025, 2026]
EXAMPLES = ["SPTO", "MTEL", "PNIN"]
PARAMS = {"objective": "huber", "num_leaves": 8, "learning_rate": 0.03, "min_child_samples": 40, "feature_fraction": 0.8, "bagging_fraction": 0.8,
          "bagging_freq": 1, "lambda_l2": 1.0, "seed": SEED, "verbose": -1, "num_threads": 4}
ROUNDS = 400
FEATURES = ["chan_pos", "width", "er", "r5", "r20", "rsi", "vol20", "vr", "dist_ma50", "dist_ma200", "log_v60", "log_price", "spread", "f5", "f20",
            "n_touch", "prev_success", "prev_n", "comp_ma200", "comp_ret20", "sector"]


def rsi_panel(adj: pd.DataFrame, n=14) -> pd.DataFrame:
    d = adj.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def build(P, unis, comp):
    adj, close, vol = P["adj"], P["close"], P["volume"]
    v60 = P["v60"]
    liq_thin = (v60 >= 0.5e9) & (close >= S.MIN_PRICE) & (vol > 0) & adj.notna()
    tiers = {"BLUE": unis["BLUE"], "LIQ": unis["LIQ"], "THIN": liq_thin}
    lo = adj.rolling(L, min_periods=L).quantile(0.10)
    mid = adj.rolling(L, min_periods=L).quantile(0.50)
    hi = adj.rolling(L, min_periods=L).quantile(0.90)
    width = adj.rolling(L, min_periods=L).max() / adj.rolling(L, min_periods=L).min() - 1
    net_move = (adj / adj.shift(L) - 1)
    er = (adj - adj.shift(L)).abs() / adj.diff().abs().rolling(L, min_periods=L).sum()
    sideways = (net_move.abs() <= 0.10) & (width >= 0.08) & (width <= 0.35) & (er <= 0.25)
    ma20, sd20 = adj.rolling(20, min_periods=20).mean(), adj.rolling(20, min_periods=20).std()
    ma50, ma200 = adj.rolling(50, min_periods=50).mean(), adj.rolling(200, min_periods=200).mean()
    rsi = rsi_panel(adj)
    up_day = adj > adj.shift(1)
    raw = {"touch": ((adj <= 1.02 * lo) & up_day, v60), "bb2": (adj <= ma20 - 2 * sd20, (ma20 - adj) / sd20), "rsi30": (rsi <= 30, 30 - rsi)}
    entries = {}
    for k, (m, sc) in raw.items():
        m = m & sideways
        prior = m.astype(float).rolling(10, min_periods=1).sum().shift(1).fillna(0)
        entries[k] = ((m & (prior == 0)).to_numpy(bool), sc.to_numpy(float))
    vr = vol / vol.rolling(20, min_periods=20).median()
    feats = {"chan_pos": (adj - lo) / (hi - lo).replace(0, np.nan), "width": width, "er": er, "r5": adj / adj.shift(5) - 1, "r20": adj / adj.shift(20) - 1,
             "rsi": rsi, "vol20": adj.pct_change().rolling(20, min_periods=20).std(), "vr": vr, "dist_ma50": adj / ma50 - 1, "dist_ma200": adj / ma200 - 1,
             "log_v60": np.log(v60.clip(lower=1)), "log_price": np.log(close.clip(lower=1)), "spread": (P["offer"] / P["bid"] - 1).where(P["bid"] > 0),
             "f5": P["f5"], "f20": P["f20"]}
    touch_all = (adj <= 1.02 * lo) & up_day
    feats["n_touch"] = touch_all.astype(float).rolling(L, min_periods=1).sum().shift(1)
    cm = comp.reindex(adj.index).ffill()
    comp_feats = {"comp_ma200": cm / cm.rolling(200, min_periods=200).mean() - 1, "comp_ret20": cm / cm.shift(20) - 1}
    levels = {"lo": lo.to_numpy(float), "mid": mid.to_numpy(float), "hi": hi.to_numpy(float)}
    return tiers, sideways, entries, levels, feats, comp_feats


def make_exit(A, LO, TG, max_hold=MAX_HOLD):
    def rule(t, j, p):
        st = p["state"]
        if "lo" not in st:
            s = max(p["e"] - 1, 0)
            st["lo"] = LO[s, j] if np.isfinite(LO[s, j]) else 0.9 * p["a0"]
            st["tg"] = TG[s, j] if np.isfinite(TG[s, j]) else 1.1 * p["a0"]
        a = A[t, j]
        return 1.0 if (a >= st["tg"] or a < STOP * st["lo"] or (t - p["e"]) >= max_hold) else 0
    return rule


def single_trade(A, c_in, c_out, LO, TG, t, j):
    """The engine's timing for one event: signal close t, entry close t+1 @offer, exit signal on a close, exit at the next close @bid."""
    Tn = A.shape[0]
    e = t + 1
    if e >= Tn or not np.isfinite(A[e, j]) or not np.isfinite(c_in[e, j]):
        return None
    lo = LO[t, j] if np.isfinite(LO[t, j]) else 0.9 * A[e, j]
    tg = TG[t, j] if np.isfinite(TG[t, j]) else 1.1 * A[e, j]
    last, x = e, None
    for d in range(e, min(e + MAX_HOLD + 1, Tn - 1)):
        a = A[d, j]
        if not np.isfinite(a):
            x = last
            break
        last = d
        if a >= tg or a < STOP * lo or (d - e) >= MAX_HOLD:
            x = d + 1 if (d + 1 < Tn and np.isfinite(A[d + 1, j]) and np.isfinite(c_out[d + 1, j])) else d
            break
    if x is None:
        x = last
    if x <= e:
        return None
    gross = A[x, j] / A[e, j] - 1
    co = c_out[x, j] if np.isfinite(c_out[x, j]) else 0.006
    return gross - c_in[e, j] - co, gross, x, x - e, bool(A[x, j] >= tg)


def events_table(A, c_in, c_out, entry_mask, uni, LO, TG, feats, comp_feats, dates, cols, sector):
    sec_codes = {s: i for i, s in enumerate(sorted({v for v in sector.values() if isinstance(v, str)}))}
    F = {k: v.to_numpy(float) for k, v in feats.items()}
    C = {k: v.to_numpy(float) for k, v in comp_feats.items()}
    ts, js = np.nonzero(entry_mask & uni)
    rows = []
    hist: dict[int, list[tuple[int, bool]]] = {}
    for t, j in zip(ts, js, strict=True):
        out = single_trade(A, c_in, c_out, LO, TG, t, j)
        if out is None:
            continue
        net, gross, x, hold, hit_target = out
        past = [h for (xi, h) in hist.get(j, []) if xi < t]
        r = {"t": int(t), "j": int(j), "code": cols[j], "date": dates[t], "exit_date": dates[x], "year": dates[t].year, "net": net, "gross": gross, "hold": hold,
             "hit_target": hit_target, "prev_n": len(past), "prev_success": (float(np.mean(past)) if past else 0.5),
             "sector": sec_codes.get(sector.get(cols[j]), -1)}
        for k, arr in F.items():
            r[k] = arr[t, j]
        for k, arr in C.items():
            r[k] = arr[t]
        rows.append(r)
        hist.setdefault(j, []).append((x, hit_target))
    df = pd.DataFrame(rows)
    return df


def walk_forward_lgb(df):
    import lightgbm as lgb
    preds = pd.Series(np.nan, index=df.index)
    thr, per_year = {}, {}
    for y in TEST_YEARS:
        start = pd.Timestamp(y, 1, 1)
        train, test = df[df["exit_date"] < start], df[df["year"] == y]
        if len(train) < 200 or len(test) < 20:
            continue
        m = lgb.train(PARAMS, lgb.Dataset(train[FEATURES], label=train["net"].clip(-0.5, 1.0), categorical_feature=["sector"]), num_boost_round=ROUNDS)
        p_tr, p_te = m.predict(train[FEATURES]), m.predict(test[FEATURES])
        thr[y] = float(np.percentile(p_tr, 200 / 3))
        preds.loc[test.index] = p_te
        per_year[y] = _fold_read(test, p_te, thr[y], len(train))
    imp = None
    return preds, thr, per_year, imp


def _fold_read(test, p_te, thr, n_train):
    q = pd.qcut(pd.Series(p_te, index=test.index).rank(method="first"), 3, labels=["bottom", "mid", "top"])
    ic = pd.Series(p_te, index=test.index).corr(test["net"], method="spearman")
    kept = p_te >= thr
    return {"n_train": int(n_train), "n_test": int(len(test)), "ic": float(ic), "top_net": float(test.loc[q == "top", "net"].mean()),
            "bottom_net": float(test.loc[q == "bottom", "net"].mean()), "top_hit": float((test.loc[q == "top", "net"] > 0).mean()),
            "bottom_hit": float((test.loc[q == "bottom", "net"] > 0).mean()), "kept_share": float(kept.mean()),
            "kept_net": float(test.loc[kept, "net"].mean()) if kept.any() else float("nan"), "dropped_net": float(test.loc[~kept, "net"].mean()) if (~kept).any() else float("nan")}


def walk_forward_gru(df, A, VRL, CP, MA20R, seq=60):
    """A small GRU on the last `seq` days of four series per event. Returns (preds, thr, per_year) or None when torch is missing."""
    try:
        import torch
        from torch import nn
    except Exception:
        return None
    torch.manual_seed(SEED)
    Tn = A.shape[0]
    logret = np.zeros_like(A)
    logret[1:] = np.log(np.where(np.isfinite(A[1:] / A[:-1]), A[1:] / A[:-1], 1.0))
    series = np.stack([np.nan_to_num(logret), np.nan_to_num(np.log(np.clip(VRL, 0.05, 20))), np.nan_to_num(CP, nan=0.5), np.nan_to_num(MA20R)], axis=-1)

    def seqs(sub):
        X = np.zeros((len(sub), seq, 4), np.float32)
        for i, (t, j) in enumerate(zip(sub["t"].to_numpy(), sub["j"].to_numpy(), strict=True)):
            a = max(0, t - seq + 1)
            X[i, seq - (t + 1 - a):] = series[a:t + 1, j]
        return X

    class Net(nn.Module):
        def __init__(self):
            super().__init__()
            self.gru = nn.GRU(4, 32, batch_first=True)
            self.head = nn.Sequential(nn.Linear(32, 16), nn.ReLU(), nn.Linear(16, 1))

        def forward(self, x):
            _, h = self.gru(x)
            return self.head(h[-1]).squeeze(-1)
    preds = pd.Series(np.nan, index=df.index)
    thr, per_year = {}, {}
    for y in TEST_YEARS:
        start = pd.Timestamp(y, 1, 1)
        train, test = df[df["exit_date"] < start], df[df["year"] == y]
        if len(train) < 300 or len(test) < 20:
            continue
        train = train.sort_values("date")
        n_val = max(50, len(train) // 6)
        tr, va = train.iloc[:-n_val], train.iloc[-n_val:]
        Xtr, Xva, Xte = seqs(tr), seqs(va), seqs(test)
        mu, sd = Xtr.reshape(-1, 4).mean(0), Xtr.reshape(-1, 4).std(0) + 1e-6
        Xtr, Xva, Xte = (Xtr - mu) / sd, (Xva - mu) / sd, (Xte - mu) / sd
        ytr = torch.tensor(tr["net"].clip(-0.5, 1.0).to_numpy(np.float32))
        yva = torch.tensor(va["net"].clip(-0.5, 1.0).to_numpy(np.float32))
        net = Net()
        opt = torch.optim.Adam(net.parameters(), lr=1e-3, weight_decay=1e-4)
        loss_fn = nn.SmoothL1Loss()
        Xtr_t, Xva_t, Xte_t = torch.tensor(Xtr), torch.tensor(Xva), torch.tensor(Xte)
        best, best_state = 1e9, None
        for epoch in range(25):
            net.train()
            perm = torch.randperm(len(Xtr_t))
            for i in range(0, len(perm), 256):
                idx = perm[i:i + 256]
                opt.zero_grad()
                loss = loss_fn(net(Xtr_t[idx]), ytr[idx])
                loss.backward()
                opt.step()
            net.eval()
            with torch.no_grad():
                v = float(loss_fn(net(Xva_t), yva))
            if v < best:
                best, best_state = v, {k: t.clone() for k, t in net.state_dict().items()}
        net.load_state_dict(best_state)
        net.eval()
        with torch.no_grad():
            p_tr = net(torch.tensor(np.concatenate([Xtr, Xva]))).numpy()
            p_te = net(Xte_t).numpy()
        thr[y] = float(np.percentile(p_tr, 200 / 3))
        preds.loc[test.index] = p_te
        per_year[y] = _fold_read(test, p_te, thr[y], len(train))
        print(f"DL fold {y}: n_train {len(train)} n_test {len(test)} IC {per_year[y]['ic']:+.3f} top {per_year[y]['top_net'] * 100:+.2f}% bottom {per_year[y]['bottom_net'] * 100:+.2f}%", flush=True)
    return preds, thr, per_year


def filtered_mask(entry_mask, df, preds, thr):
    m = np.zeros_like(entry_mask)
    for (t, j, y), p in zip(df[["t", "j", "year"]].itertuples(index=False, name=None), preds.to_numpy(), strict=True):
        if y in thr and np.isfinite(p) and p >= thr[y]:
            m[t, j] = True
    return m


def model_read(per_year, s_model, s_plain):
    ic_pos = sum(1 for v in per_year.values() if v["ic"] > 0)
    why = []
    if ic_pos < 3:
        why.append(f"IC>0 in {ic_pos}/5")
    if s_model["sharpe"] < s_plain["sharpe"] + 0.15:
        why.append("sharpe<plain+0.15")
    if s_model["mdd"] < s_plain["mdd"]:
        why.append("mdd deeper")
    return ("USEFUL" if not why else "not useful: " + ", ".join(why)), ic_pos


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-dl", action="store_true")
    ap.add_argument("--no-store", action="store_true")
    args = ap.parse_args()
    dsn = os.environ["INGEST_DB_DSN"]
    P, unis, comp, Hp, Lp, sectors, brent = B.load_all(dsn, os.environ.get("IDX_BEYOND_CACHE"))
    c_in, c_out = S.costs(P)
    adj = P["adj"]
    dates, cols = adj.index, adj.columns
    A, H = adj.to_numpy(float), Hp.to_numpy(float)
    tiers, sideways, entries, levels, feats, comp_feats = build(P, unis, comp)
    sector = dict(zip(sectors["code"], sectors["sector"]))
    LO, MID, HI = levels["lo"], levels["mid"], levels["hi"]
    exits = {"mid": make_exit(A, LO, MID), "hi": make_exit(A, LO, HI)}
    side = sideways.to_numpy(bool)
    universes = {u: (tiers[u].to_numpy(bool) & side) for u in TIERS}
    out = {"universe": {}, "rules": {}, "random": {}, "money": {}, "examples": {}, "ml": {}, "dl": {}}
    for u in TIERS:
        n_day = universes[u].sum(axis=1)
        out["universe"][u] = {"names_per_day_median": float(np.median(n_day[n_day > 0])) if (n_day > 0).any() else 0.0, "days_nonempty": int((n_day > 0).sum()),
                              "touch_signals": int((entries["touch"][0] & universes[u]).sum())}
        print(f"universe {u}: sideways names/day median {out['universe'][u]['names_per_day_median']:.0f}, touch signals {out['universe'][u]['touch_signals']}", flush=True)
    # examples
    for code in EXAMPLES:
        if code not in cols:
            out["examples"][code] = "not in panel"
            continue
        j = cols.get_loc(code)
        ins = side[:, j]
        ev = [single_trade(A, c_in, c_out, LO, MID, t, j) for t in np.flatnonzero(entries["touch"][0][:, j])]
        ev = [e for e in ev if e is not None]
        nets = np.array([e[0] for e in ev])
        out["examples"][code] = {"days_sideways_pct": float(ins.mean() * 100), "touch_signals": int(len(ev)), "avg_net": float(nets.mean()) if len(ev) else None,
                                 "hit": float((nets > 0).mean()) if len(ev) else None, "v60_last": float(P["v60"][code].iloc[-1]) if np.isfinite(P["v60"][code].iloc[-1]) else None,
                                 "in_LIQ": bool(tiers["LIQ"][code].iloc[-1]), "in_THIN": bool(tiers["THIN"][code].iloc[-1])}
        print(f"example {code}: {out['examples'][code]}", flush=True)
    # rule arms
    for u in TIERS:
        uni = universes[u]
        for i, arm in enumerate(RULE_ARMS):
            ent, ex = arm.split("_")
            mask, score = entries[ent]
            R, tr, open_ = B.run_book_sized(A, H, c_in, c_out, mask, score, exits[ex], uni, lambda t, j: 1.0 / K)
            s = E.stats(R.copy(), tr, dates, N_TRIALS)
            s["open"] = len(open_)
            Rq, trq, _ = B.run_book_sized(A, H, c_in, c_out, None, None, exits[ex], uni, lambda t, j: 1.0 / K, rng=np.random.default_rng(SEED + i + 10 * TIERS.index(u)))
            rn = E.stats(Rq.copy(), trq, dates, N_TRIALS)
            key = f"{arm}|{u}"
            out["rules"][key], out["random"][key] = s, rn
            out["money"][key] = B.money_read(s, rn)
            print(f"{key:16s} n={s['n']:4d} hold={s['hold']:3.0f} hit={s['hit'] * 100:3.0f}% net={s['avg_net'] * 100:+5.2f}% t={s['tstat']:4.1f} cagr={s['cagr'] * 100:+6.1f}% "
                  f"sharpe={s['sharpe']:5.2f} mdd={s['mdd'] * 100:4.0f}% | rnd sharpe {rn['sharpe']:5.2f} | {out['money'][key]}", flush=True)
    # ML on touch events
    for u in ("LIQ", "THIN"):
        df = events_table(A, c_in, c_out, entries["touch"][0], universes[u], LO, MID, feats, comp_feats, dates, cols, sector)
        print(f"ML {u}: {len(df)} touch events, label mean net {df['net'].mean() * 100:+.2f}%, hit {(df['net'] > 0).mean() * 100:.0f}%, target hit {df['hit_target'].mean() * 100:.0f}%", flush=True)
        preds, thr, per_year, _ = walk_forward_lgb(df)
        fm = filtered_mask(entries["touch"][0], df, preds, thr)
        lo_i = dates.searchsorted(pd.Timestamp("2022-01-01"))
        plain_R, plain_tr, _ = B.run_book_sized(A, H, c_in, c_out, entries["touch"][0], entries["touch"][1], exits["mid"], universes[u], lambda t, j: 1.0 / K)
        ml_R, ml_tr, _ = B.run_book_sized(A, H, c_in, c_out, fm, entries["touch"][1], exits["mid"], universes[u], lambda t, j: 1.0 / K)

        def cut(R, tr):
            return E.stats(R.iloc[lo_i:].reset_index(drop=True), [x for x in tr if x[0] >= lo_i], dates[lo_i:], N_TRIALS)
        s_plain, s_ml = cut(plain_R, plain_tr), cut(ml_R, ml_tr)
        read, ic_pos = model_read(per_year, s_ml, s_plain)
        out["ml"][u] = {"events": int(len(df)), "label_mean": float(df["net"].mean()), "per_year": per_year, "plain": s_plain, "model": s_ml, "read": read, "ic_pos": ic_pos}
        print(f"ML {u}: plain 2022-26 cagr={s_plain['cagr'] * 100:+.1f}% sharpe={s_plain['sharpe']:.2f} mdd={s_plain['mdd'] * 100:.0f}% | model cagr={s_ml['cagr'] * 100:+.1f}% "
              f"sharpe={s_ml['sharpe']:.2f} mdd={s_ml['mdd'] * 100:.0f}% | IC>0 {ic_pos}/5 -> {read}", flush=True)
        if u == "LIQ" and not args.no_dl:
            VRL = feats["vr"].to_numpy(float)
            CP = feats["chan_pos"].to_numpy(float)
            MA20R = (adj / adj.rolling(20, min_periods=20).mean() - 1).to_numpy(float)
            res = walk_forward_gru(df, A, VRL, CP, MA20R)
            if res is None:
                out["dl"]["LIQ"] = {"skipped": "torch unavailable"}
                print("DL skipped: torch unavailable", flush=True)
            else:
                dpreds, dthr, dper = res
                dm = filtered_mask(entries["touch"][0], df, dpreds, dthr)
                dl_R, dl_tr, _ = B.run_book_sized(A, H, c_in, c_out, dm, entries["touch"][1], exits["mid"], universes[u], lambda t, j: 1.0 / K)
                s_dl = cut(dl_R, dl_tr)
                dread, dic = model_read(dper, s_dl, s_plain)
                out["dl"]["LIQ"] = {"per_year": dper, "plain": s_plain, "model": s_dl, "read": dread, "ic_pos": dic}
                print(f"DL LIQ: model cagr={s_dl['cagr'] * 100:+.1f}% sharpe={s_dl['sharpe']:.2f} mdd={s_dl['mdd'] * 100:.0f}% | IC>0 {dic}/5 -> {dread}", flush=True)
    # report
    def yrs(d):
        return " ".join(f"{y % 100:02d}:{v * 100:+.0f}" for y, v in sorted(d.items()))

    def row(label, s, extra):
        return (f"| {label} | {s['n']} | {s['hold']:.0f} | {s['hit'] * 100:.0f} % | {s['avg_net'] * 100:+.2f} % | {s['payoff']:.2f} | {s['tstat']:.1f} | {s['cagr'] * 100:+.1f} % | "
                f"{s['sharpe']:.2f} | {s['mdd'] * 100:.0f} % | {yrs(s['years'])} | {extra} |")
    hdr = ["| arm | trades | hold d | hit | avg net | payoff | t | CAGR | Sharpe | mDD | years | read |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    n_c = sum(1 for v in out["money"].values() if v == "CANDIDATE")
    Lns = [f"# IDX menu 26 — range trading in sideways names — {date.today()} — {len(ARMS)} trials, cumulative N = {N_TRIALS}", "",
           f"Sideways screen (L = {L}): |{L}-day move| <= 10 %, channel width 8-35 %, efficiency ratio <= 0.25; levels = 10th / 50th / 90th percentile of the {L} closes. "
           f"Entry close t+1 @offer, exit close t+1 @bid (target mid or hi, stop {STOP:.2f} x lo, time stop {MAX_HOLD} d), fees 0.10/0.20 %, K = {K}. {dates[0].date()} -> {dates[-1].date()}.", "",
           "## Universe", "", "| tier | sideways names per day (median) | days with a non-empty universe | touch signals |", "|---|---|---|---|"]
    for u in TIERS:
        v = out["universe"][u]
        Lns.append(f"| {u} | {v['names_per_day_median']:.0f} | {v['days_nonempty']} | {v['touch_signals']} |")
    Lns += ["", "## The operator's examples", "", "| name | days inside the screen | touch signals | avg net / trade | hit | 60-day value (Rp bn) | in LIQ / THIN |", "|---|---|---|---|---|---|---|"]
    for code, v in out["examples"].items():
        if isinstance(v, str):
            Lns.append(f"| {code} | {v} | | | | | |")
        else:
            Lns.append(f"| {code} | {v['days_sideways_pct']:.0f} % | {v['touch_signals']} | {(v['avg_net'] * 100 if v['avg_net'] is not None else float('nan')):+.2f} % | "
                       f"{(v['hit'] * 100 if v['hit'] is not None else float('nan')):.0f} % | {(v['v60_last'] or 0) / 1e9:.1f} | {'yes' if v['in_LIQ'] else 'no'} / {'yes' if v['in_THIN'] else 'no'} |")
    Lns += ["", "## Rule arms (12 trials)", "", *hdr]
    for u in TIERS:
        for arm in RULE_ARMS:
            key = f"{arm}|{u}"
            Lns.append(row(key, out["rules"][key], f"{out['money'][key]} (rnd Sharpe {out['random'][key]['sharpe']:.2f})"))
        Lns.append(row(f"random | mid | {u}", out["random"][f"touch_mid|{u}"], "reference"))
    Lns += ["", f"Money rule as declared: {n_c} candidate(s) of 12.", ""]
    for kind, key in (("ML (LightGBM)", "ml"), ("DL (GRU)", "dl")):
        for u, v in out[key].items():
            if "skipped" in v:
                Lns += [f"## {kind} on touch events, {u}: skipped ({v['skipped']})", ""]
                continue
            Lns += [f"## {kind} on `touch` events, {u}" + (f" — {v['events']} events, label mean net {v['label_mean'] * 100:+.2f} %" if "events" in v else ""), "",
                    "| test year | train | test | IC | top third net | bottom third net | top hit | kept share | kept net | dropped net |", "|---|---|---|---|---|---|---|---|---|---|"]
            for y, r in v["per_year"].items():
                Lns.append(f"| {y} | {r['n_train']} | {r['n_test']} | {r['ic']:+.3f} | {r['top_net'] * 100:+.2f} % | {r['bottom_net'] * 100:+.2f} % | {r['top_hit'] * 100:.0f} % | "
                           f"{r['kept_share'] * 100:.0f} % | {r['kept_net'] * 100:+.2f} % | {r['dropped_net'] * 100:+.2f} % |")
            Lns += ["", *hdr, row("plain touch_mid 2022-26", v["plain"], "reference"), row(f"{key} filtered 2022-26", v["model"], v["read"]), ""]
    path = os.path.join(HERE, f"IDX_RANGE_{date.today().isoformat()}.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(Lns) + "\n")
    print("\n".join(Lns))
    print("wrote", path)
    if not args.no_store:
        from blackheart_ingest.idx import research_store as rs
        with psycopg.connect(dsn) as conn:
            sid = rs.record_study(conn, "range_sideways", dates[-1].date(), params={"trials": ARMS, "n_trials_cumulative": N_TRIALS, "L": L, "max_hold": MAX_HOLD, "stop": STOP, "seed": SEED},
                                  summary=json.loads(json.dumps(out, default=str)), names=[], report_path=path,
                                  note=f"{n_c} candidates of 12 rules; ML {[v.get('read') for v in out['ml'].values()]}; DL {[v.get('read', v.get('skipped')) for v in out['dl'].values()]}")
            print(f"study #{sid} stored")


if __name__ == "__main__":
    main()
