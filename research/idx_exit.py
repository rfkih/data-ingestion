#!/usr/bin/env python3
"""IDX menu 13 — which take-profit / exit mechanism serves the trend book best? (operator, 2026-09-18: "mekanisme TP-nya
bisa diresearch lagi? cari metode TP paling proven di dunia, coba beberapa, cari yang paling baik").

The trend book (menus 6-7; `idx/trend_book.py`, books `paper_trend` + `trend_live`, variant `small`) has ONE exit: close <= 90 % of
the highest close since entry. It has never been run against the exits the trend-following literature actually uses. This menu
keeps the entry, the book, the costs and the execution fixed and swaps only the exit.

PRE-REGISTERED MENU (30 trials = 15 exits x 2 universes; cumulative 313 + 30 = 343). Declared before the run; nothing tuned afterwards.
  Entry (fixed): close = 60-day high, close > MA200, volume >= 1.5x its 20-day median, ranked by volume ratio (the menu-6 lead).
  Book (fixed): K = 10 slots of 1/K each, one position per name; entry signal at close t -> buy close t+1 at the closing offer;
    exit signal at close t -> sell close t+1 at the closing bid; Stockbit fees 0.10/0.20 %. A partial exit leaves its slot occupied
    (the freed cash idles) — exactly what the real book would do. Adjusted closes; ATR/lows/highs on adjusted high/low.
  Universes: `small` (LIQ minus BLUE — the deployed rule, both trend books) and `LIQ` (the declared paper rule). Every exit is one
    trial on each universe.
  Exits (all evaluated on the close, the way the nightly chain sees them):
    Trailing family (the reference's kin)
      ratchet     trail 10 % until the peak is +20 %, then 7 %, then 5 % once +40 % (staged profit protection, Tharp)
      chand3      Chandelier (LeBeau): close <= highest high since entry - 3 x ATR20 (Wilder ATR)
      chand2      Chandelier with 2 x ATR20
      sar         Parabolic SAR (Wilder, AF 0.02 step, 0.20 cap; seeded at the 10-day low on entry): close <= SAR
    Channel / moving-average family (trend break)
      turtle10    Turtle S1 (Dennis/Eckhardt): close < lowest low of the prior 10 days, plus the 2N stop (2 x ATR20 at entry)
      turtle20    Turtle S2: prior 20-day low, plus the 2N stop
      ma20        close < 20-day average (menu-6 exit, never run on these universes)
      ma50        close < 50-day average
    Fixed-target family (classic take-profit)
      oneil       O'Neil: stop at -8 % from entry; sell at +20 % — unless +20 % came within 15 days, then hold 40 days and trail 10 %
      tp3r        Van Tharp bracket: R = 2 x ATR20 at entry; stop at entry - R, take profit at entry + 3R, nothing else
    Scale-out family (sell into strength)
      half20      sell half at +20 %, stop on the rest to break-even, trail 10 % on the rest (Minervini / O'Neil)
      thirds      sell a third at +10 %, a third at +20 %, trail 10 % on the rest
    Overlay family (trail 10 % plus one extra sell trigger)
      climax      sell when close - MA20 >= 4 x ATR20 (blow-off / climax top), else trail 10 %
      rsi75       sell when RSI14 >= 75 (overbought), else trail 10 %
      dead20      trail 10 %, and sell a name that is at or below its entry after 20 days (dead money, Minervini)
  References (not trials): trail10 on each universe (the deployed exit); random entries + the SAME exit for every arm (seed per arm).
READING RULES (declared before the run):
  Against the deployed exit (same universe): an exit is BETTER than trail10 only if ALL hold: >= 150 closed trades; t >= 2.0;
    Sharpe >= trail10 + 0.15; CAGR >= 80 % of trail10's; max drawdown not deeper than trail10's.
  ADOPTION: an exit replaces trail10 in the PAPER book only if BETTER on BOTH universes (small and LIQ). The live book changes only by
    the operator's decision (two-key). One universe only = "informative", recorded, not adopted.
  Candidate for money: the menu-6 rule unchanged (>= 150 trades; t >= 2.5; Sharpe >= 1.0; max DD <= 25 %; >= 5 of 7 years positive;
    Sharpe >= random + same exit + 0.5).
  Extra columns, descriptive only: MFE = mean best unrealised gain per trade; capture = mean gross / mean MFE (how much of the
    open profit the exit keeps).
READ-ONLY. INGEST_DB_DSN=... PYTHONIOENCODING=utf-8 blackheart-ingest/.venv/Scripts/python research/idx_exit.py
  (IDX_EXIT_CACHE=<file.pkl> caches the loaded panels for re-runs; the data is identical either way.)
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
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blackheart-ingest", "src"))
import idx_swing2 as S  # noqa: E402
import idx_trend as T  # noqa: E402

N_BEFORE = 313
K = 10
LEAD = (60, 0.10, 1.5)
EXITS = ["ratchet", "chand3", "chand2", "sar", "turtle10", "turtle20", "ma20", "ma50", "oneil", "tp3r", "half20", "thirds", "climax", "rsi75", "dead20"]
UNIS = ["small", "LIQ"]
ARMS = [f"{x}|{u}" for u in UNIS for x in EXITS]
assert len(ARMS) == 30
SEED = 20260918


def load_hl(conn, P):
    """Adjusted high/low panels aligned to P['adj']."""
    hl = pd.read_sql("SELECT code, trade_date, high, low FROM idx.bar WHERE source = 'idx' AND trade_date BETWEEN %s AND %s", conn, params=(S.START, S.END))
    hl["trade_date"] = pd.to_datetime(hl["trade_date"])
    adj = P["adj"]
    out = {}
    for c in ("high", "low"):
        hl[c] = pd.to_numeric(hl[c], errors="coerce")
        out[c] = hl.pivot(index="trade_date", columns="code", values=c).reindex(index=adj.index, columns=adj.columns)
    f = adj / P["close"]
    return out["high"] * f, out["low"] * f


def load_all(dsn, cache=None):
    if cache and os.path.exists(cache):
        with open(cache, "rb") as fh:
            return pickle.load(fh)
    with psycopg.connect(dsn) as conn:
        bars, listing, idx, macro, buyb, splits, pead = S.load(conn)
        P = S.panels(bars, listing)
        _, unis, comp = S.build(P, listing, idx, macro, buyb, splits, pead)
        H, L = load_hl(conn, P)
    data = (P, unis, comp, H, L)
    if cache:
        with open(cache, "wb") as fh:
            pickle.dump(data, fh)
    return data


def run_book(A, H, L, c_in, c_out, entry_mask, entry_score, rule, uni, k=K, rng=None):
    """Event-driven book with partial exits. rule(t, j, pos) -> fraction of the ORIGINAL position to sell (0 = hold, 1 = all);
    signalled at close t, executed at close t+1. A partial keeps the slot; the trade closes when the last piece is sold and is
    recorded once with the capital-weighted gross/net of its legs. Returns daily returns, closed trades, open positions."""
    Tn, N = A.shape
    ret = np.full((Tn, N), np.nan)
    ret[1:] = A[1:] / A[:-1] - 1
    R = np.zeros(Tn)
    held: dict[int, dict] = {}
    pending: dict[int, float] = {}
    pending_entry: list[int] = []
    trades = []
    w = 1.0 / k
    for t in range(1, Tn):
        day = 0.0
        for j, p in held.items():
            r = ret[t, j]
            day += w * p["w"] * (0.0 if np.isnan(r) else r)
        for j, f in list(pending.items()):
            if j in held and not np.isnan(A[t, j]) and np.isfinite(c_out[t, j]):
                p = held[j]
                f = min(f, p["w"])
                gross = A[t, j] / p["a0"] - 1
                p["legs"].append((f, gross, gross - p["ci"] - c_out[t, j]))
                day -= w * f * c_out[t, j]
                p["w"] -= f
                if p["w"] <= 1e-9:
                    held.pop(j)
                    g = sum(fr * gr for fr, gr, _ in p["legs"])
                    n = sum(fr * nt for fr, _, nt in p["legs"])
                    trades.append((p["e"], j, g, n, t - p["e"], p["mfe"]))
        pending = {}
        for j in pending_entry:
            if len(held) >= k or j in held or np.isnan(A[t, j]) or not np.isfinite(c_in[t, j]):
                continue
            h0 = H[t, j] if not np.isnan(H[t, j]) else A[t, j]
            held[j] = {"e": t, "a0": A[t, j], "peak": A[t, j], "hh": h0, "ci": c_in[t, j], "w": 1.0, "legs": [], "mfe": 0.0, "state": {}}
            day -= w * c_in[t, j]
        pending_entry = []
        R[t] = day
        for j, p in held.items():
            if np.isnan(A[t, j]):
                pending[j] = 1.0
                continue
            p["peak"] = max(p["peak"], A[t, j])
            if not np.isnan(H[t, j]):
                p["hh"] = max(p["hh"], H[t, j])
            p["mfe"] = max(p["mfe"], p["peak"] / p["a0"] - 1)
            f = rule(t, j, p)
            if f and f > 0:
                pending[j] = float(f)
        full_exits = sum(1 for j, f in pending.items() if j in held and f >= held[j]["w"] - 1e-9)
        free = k - (len(held) - full_exits)
        if free > 0:
            if rng is not None:
                cand = np.flatnonzero(uni[t] & ~np.isnan(A[t]))
                cand = [j for j in cand if j not in held]
                pick = list(rng.choice(cand, size=min(free, len(cand)), replace=False)) if cand else []
            else:
                cand = np.flatnonzero(entry_mask[t] & uni[t])
                cand = [j for j in cand if j not in held]
                sc = np.nan_to_num(entry_score[t, cand], nan=-np.inf) if cand else np.array([])
                pick = [cand[i] for i in np.argsort(-sc, kind="stable")[:free]] if cand else []
            pending_entry = list(pick)
    return pd.Series(R), trades, held


def make_rules(A, H, L, ATR, M20, M50, RSI, LO10, LO20):
    def trail(t, j, p, x=0.10):
        return A[t, j] <= (1 - x) * p["peak"]

    def atr0(t, j, p):
        a = p["state"].get("atr0")
        if a is None:
            a = ATR[p["e"], j]
            a = 0.10 * p["a0"] if (np.isnan(a) or a <= 0) else a
            p["state"]["atr0"] = a
        return a

    def ratchet(t, j, p):
        g = p["peak"] / p["a0"] - 1
        x = 0.10 if g < 0.20 else (0.07 if g < 0.40 else 0.05)
        return 1.0 if A[t, j] <= (1 - x) * p["peak"] else 0

    def chand(k):
        def f(t, j, p):
            a = ATR[t, j]
            if np.isnan(a):
                return 1.0 if trail(t, j, p) else 0
            return 1.0 if A[t, j] <= p["hh"] - k * a else 0
        return f

    def sar(t, j, p):
        st = p["state"]
        if "sar" not in st:
            lo = L[max(0, p["e"] - 9):p["e"] + 1, j]
            lo = lo[~np.isnan(lo)]
            st["sar"] = lo.min() if len(lo) else 0.9 * p["a0"]
            st["ep"] = p["hh"]
            st["af"] = 0.02
            return 0
        s = st["sar"] + st["af"] * (st["ep"] - st["sar"])
        for back in (1, 2):
            v = L[t - back, j] if t - back >= 0 else np.nan
            if not np.isnan(v):
                s = min(s, v)
        st["sar"] = s
        h = H[t, j]
        if not np.isnan(h) and h > st["ep"]:
            st["ep"] = h
            st["af"] = min(st["af"] + 0.02, 0.20)
        return 1.0 if A[t, j] <= s else 0

    def turtle(LO):
        def f(t, j, p):
            if A[t, j] <= p["a0"] - 2 * atr0(t, j, p):
                return 1.0
            lo = LO[t, j]
            return 1.0 if (not np.isnan(lo) and A[t, j] < lo) else 0
        return f

    def ma(M):
        def f(t, j, p):
            m = M[t, j]
            return 1.0 if (not np.isnan(m) and A[t, j] < m) else 0
        return f

    def oneil(t, j, p):
        d = t - p["e"]
        g = A[t, j] / p["a0"] - 1
        if g <= -0.08:
            return 1.0
        st = p["state"]
        if st.get("fast"):
            return 1.0 if (d >= 40 and trail(t, j, p)) else 0
        if g >= 0.20:
            if d <= 15:
                st["fast"] = True
                return 0
            return 1.0
        return 0

    def tp3r(t, j, p):
        r = 2 * atr0(t, j, p)
        return 1.0 if (A[t, j] <= p["a0"] - r or A[t, j] >= p["a0"] + 3 * r) else 0

    def half20(t, j, p):
        if not p["legs"] and A[t, j] >= 1.20 * p["a0"]:
            return 0.5
        stop = 0.90 * p["peak"]
        if p["legs"]:
            stop = max(stop, p["a0"])
        return 1.0 if A[t, j] <= stop else 0

    def thirds(t, j, p):
        n = len(p["legs"])
        if n == 0 and A[t, j] >= 1.10 * p["a0"]:
            return 1 / 3
        if n == 1 and A[t, j] >= 1.20 * p["a0"]:
            return 1 / 3
        return 1.0 if trail(t, j, p) else 0

    def climax(t, j, p):
        a, m = ATR[t, j], M20[t, j]
        if not (np.isnan(a) or np.isnan(m)) and A[t, j] - m >= 4 * a:
            return 1.0
        return 1.0 if trail(t, j, p) else 0

    def rsi75(t, j, p):
        r = RSI[t, j]
        if not np.isnan(r) and r >= 75:
            return 1.0
        return 1.0 if trail(t, j, p) else 0

    def dead20(t, j, p):
        if trail(t, j, p):
            return 1.0
        return 1.0 if (t - p["e"] >= 20 and A[t, j] <= p["a0"]) else 0

    return {"trail10": lambda t, j, p: 1.0 if trail(t, j, p) else 0, "ratchet": ratchet, "chand3": chand(3), "chand2": chand(2), "sar": sar,
            "turtle10": turtle(LO10), "turtle20": turtle(LO20), "ma20": ma(M20), "ma50": ma(M50), "oneil": oneil, "tp3r": tp3r,
            "half20": half20, "thirds": thirds, "climax": climax, "rsi75": rsi75, "dead20": dead20}


def stats(R, trades, dates, n_trials):
    s = T.stats(R, trades, dates, n_trials)
    if trades:
        g = np.array([t[2] for t in trades]); m = np.array([t[5] for t in trades])
        s["mfe"] = float(m.mean())
        s["capture"] = float(g.mean() / m.mean()) if m.mean() > 0 else 0.0
    else:
        s["mfe"] = s["capture"] = 0.0
    return s


def main():
    dsn = os.environ["INGEST_DB_DSN"]
    P, unis, comp, Hp, Lp = load_all(dsn, os.environ.get("IDX_EXIT_CACHE"))
    c_in, c_out = S.costs(P)
    adj, vol = P["adj"], P["volume"]
    dates = adj.index
    A = adj.to_numpy(float)
    H, L = Hp.to_numpy(float), Lp.to_numpy(float)
    ma20, ma50, ma200 = (adj.rolling(n, min_periods=n).mean() for n in (20, 50, 200))
    vr = vol / vol.rolling(20, min_periods=20).median()
    hi = adj.rolling(LEAD[0], min_periods=LEAD[0]).max()
    entry = ((adj >= hi) & (adj > ma200) & (vr >= LEAD[2])).to_numpy(bool)
    score = vr.to_numpy(float)
    prev = adj.shift(1)
    tr = pd.concat([Hp - Lp, (Hp - prev).abs(), (Lp - prev).abs()], axis=1, keys=["a", "b", "c"]).T.groupby(level=1).max().T.reindex(columns=adj.columns)
    ATR = tr.ewm(alpha=1 / 20, adjust=False, min_periods=20).mean().to_numpy(float)
    d = adj.diff()
    up = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    RSI = (100 - 100 / (1 + up / dn.replace(0, np.nan))).to_numpy(float)
    LO10 = Lp.shift(1).rolling(10, min_periods=10).min().to_numpy(float)
    LO20 = Lp.shift(1).rolling(20, min_periods=20).min().to_numpy(float)
    rules = make_rules(A, H, L, ATR, ma20.to_numpy(float), ma50.to_numpy(float), RSI, LO10, LO20)
    universes = {"small": (unis["LIQ"] & ~unis["BLUE"]).to_numpy(bool), "LIQ": unis["LIQ"].to_numpy(bool)}
    n_trials = N_BEFORE + len(ARMS)
    res, rnd, refs = {}, {}, {}
    for u in UNIS:
        uni = universes[u]
        R, trs, _ = run_book(A, H, L, c_in, c_out, entry, score, rules["trail10"], uni)
        refs[u] = stats(R, trs, dates, n_trials)
        R, trs, _ = run_book(A, H, L, c_in, c_out, None, None, rules["trail10"], uni, rng=np.random.default_rng(SEED))
        refs[u + "_rnd"] = stats(R, trs, dates, n_trials)
        for i, x in enumerate(EXITS):
            arm = f"{x}|{u}"
            R, trs, open_ = run_book(A, H, L, c_in, c_out, entry, score, rules[x], uni)
            s = stats(R, trs, dates, n_trials); s["open"] = len(open_)
            res[arm] = s
            R, trs, _ = run_book(A, H, L, c_in, c_out, None, None, rules[x], uni, rng=np.random.default_rng(SEED + 1 + i))
            rnd[arm] = stats(R, trs, dates, n_trials)
            print(f"{arm:16s} n={s['n']:4d} hold={s['hold']:4.0f} hit={s['hit'] * 100:3.0f}% net={s['avg_net'] * 100:+5.2f}% t={s['tstat']:4.1f} "
                  f"cagr={s['cagr'] * 100:+5.1f}% sharpe={s['sharpe']:4.2f} mdd={s['mdd'] * 100:4.0f}% capture={s['capture']:.2f} | rnd sharpe {rnd[arm]['sharpe']:.2f}", flush=True)
    better, money = {}, {}
    for arm in ARMS:
        x, u = arm.split("|")
        s, ref, rn = res[arm], refs[u], rnd[arm]
        why = []
        if s["n"] < 150:
            why.append("n<150")
        if s["tstat"] < 2.0:
            why.append("t<2")
        if s["sharpe"] < ref["sharpe"] + 0.15:
            why.append("sharpe<ref+0.15")
        if s["cagr"] < 0.8 * ref["cagr"]:
            why.append("cagr<80%ref")
        if s["mdd"] < ref["mdd"]:
            why.append("mdd deeper")
        better[arm] = "BETTER" if not why else "no: " + ",".join(why)
        why = []
        if s["n"] < 150:
            why.append("n<150")
        if not (s["avg_net"] > 0 and s["tstat"] >= 2.5):
            why.append("t<2.5")
        if s["sharpe"] < 1.0:
            why.append("sharpe<1")
        if s["mdd"] < -0.25:
            why.append("mdd>25%")
        if sum(1 for v in s["years"].values() if v > 0) < 5:
            why.append("years<5/7")
        if s["sharpe"] < rn["sharpe"] + 0.5:
            why.append("vs random")
        money[arm] = "CANDIDATE" if not why else "tested: " + ",".join(why)
    adopt = [x for x in EXITS if all(better[f"{x}|{u}"] == "BETTER" for u in UNIS)]
    informative = [x for x in EXITS if x not in adopt and any(better[f"{x}|{u}"] == "BETTER" for u in UNIS)]

    def yrs(d):
        return " ".join(f"{y % 100:02d}:{v * 100:+.0f}" for y, v in sorted(d.items()))

    def row(label, s, extra):
        return (f"| {label} | {s['n']} | {s['hold']:.0f} | {s['hit'] * 100:.0f} % | {s['avg_net'] * 100:+.2f} % | {s['payoff']:.2f} | {s['tstat']:.1f} | "
                f"{s['cagr'] * 100:+.1f} % | {s['sharpe']:.2f} | {s['mdd'] * 100:.0f} % | {s['mfe'] * 100:.1f} % | {s['capture']:.2f} | {yrs(s['years'])} | {extra} |")
    lines = [f"# IDX menu 13 — exit / take-profit mechanics for the trend book — {date.today()} — {len(ARMS)} trials, cumulative N = {n_trials}", "",
             f"Entry fixed at the menu-6 lead (60-day high, > MA200, volume >= 1.5x); book K = {K}, entry close t+1 @offer, exit close t+1 @bid, "
             f"fees {S.FEE_BUY * 100:.2f}/{S.FEE_SELL * 100:.2f} %; {dates[0].date()} -> {dates[-1].date()}. Only the exit changes.", ""]
    for u in UNIS:
        lines += [f"## Universe `{u}`" + (" (the deployed rule: paper_trend + trend_live)" if u == "small" else " (the declared paper rule)"), "",
                  "| exit | trades | hold d | hit | avg net | payoff | t | CAGR | Sharpe | mDD | MFE | capture | years | vs trail10 / money rule |",
                  "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
                  row("**trail10** (deployed)", refs[u], "reference"), row("random + trail10", refs[u + "_rnd"], "reference")]
        for x in EXITS:
            arm = f"{x}|{u}"
            lines.append(row(x, res[arm], f"{better[arm]} / {money[arm]} (rnd Sharpe {rnd[arm]['sharpe']:.2f})"))
        lines.append("")
    n_money = sum(1 for v in money.values() if v == "CANDIDATE")
    lines += [f"Candidates for money by the menu-6 rule: {n_money} of {len(ARMS)}.",
              f"BETTER than trail10 on both universes (adoption rule): {', '.join(adopt) if adopt else 'none'}.",
              f"BETTER on one universe only (informative, not adopted): {', '.join(informative) if informative else 'none'}.", "",
              "Limits: as menus 6-7 (current listing board, close-to-close signals one day late, quoted closing spread + fees, no slippage beyond it,",
              "dividends ignored, open positions at the last bar marked not counted); every exit is evaluated on the close, not intraday — the Turtle,",
              "Chandelier and SAR rules are therefore slightly late versions of their stop-order originals; ATR = Wilder 20-day on adjusted high/low."]
    text = "\n".join(lines); print(text)
    out = os.path.join(HERE, f"IDX_EXIT_{date.today().isoformat()}.md")
    open(out, "w", encoding="utf-8").write(text + "\n"); print("wrote", out)
    from blackheart_ingest.idx import research_store as rs
    with psycopg.connect(dsn) as conn:
        sid = rs.record_study(conn, "trend_exit", dates[-1].date(), params={"trials": ARMS, "exits": EXITS, "universes": UNIS, "lead": LEAD, "K": K,
                                                                          "n_trials_cumulative": n_trials, "seed": SEED},
                              summary={"results": res, "random": rnd, "refs": refs, "better": better, "money": money, "adopt": adopt, "informative": informative},
                              names=[], report_path=out, note=f"money {n_money}/{len(ARMS)}; adopt {adopt or 'none'}; informative {informative or 'none'}")
        print("study", sid)


if __name__ == "__main__":
    main()
