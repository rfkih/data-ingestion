#!/usr/bin/env python3
"""IDX menu 14 — set-and-forget exits (operator, 2026-09-18: "kalau pake stop loss? soalnya kamu harus update stop loss-nya tiap hari
kalau pakai trail10"). Menu 13 (research/idx_exit.py) found no textbook exit beating the 10 % trailing stop by the declared bar; the
one exit moving every number the right way was the fixed bracket `tp3r` (stop entry - 2 x ATR20, take profit entry + 3R) — which
happens to be a set-once exit. This menu asks the operator's question directly: what does a stop-loss placed once at entry do, with
and without a fixed target, and how much does a trailing stop lose when it is only re-set weekly or monthly? It also runs the
declared tp3r neighbourhood from menu 13.

PRE-REGISTERED MENU (32 trials = 16 exits x 2 universes; cumulative 343 + 32 = 375). Declared before the run; nothing tuned afterwards.
  Entry, book, costs, execution, universes (small, LIQ): exactly as menu 13. Only the exit changes. R0 = ATR20 (Wilder) at entry.
  A. Stop-loss only (the literal question; a name is otherwise held until it leaves the universe)
      sl10          stop at entry - 10 %
      sl2atr        stop at entry - 2 x ATR20
  B. Percentage brackets, both legs fixed at entry
      b10_20, b10_30, b10_50      stop -10 %, take profit +20 / +30 / +50 %
  C. ATR brackets — the tp3r neighbourhood (stop k x ATR, take profit m x that stop distance); (2,3) = tp3r, re-run as reference
      a1.5x2, a1.5x3, a1.5x4, a2x2, a2x4, a2.5x2, a2.5x3, a2.5x4
  D. Trailing stop re-set less often (stop = 90 % of the peak close, but the level is only refreshed every n trading days)
      trail10_w     every 5 days (weekly)
      trail10_m     every 21 days (monthly)
  E. Stop-loss set once, trailing only for a big winner
      run3r         stop at entry - 2 x ATR20; once the close reaches entry + 3R (R = 2 x ATR20) switch to a 10 % trailing stop
  References (not trials): trail10 (deployed) and tp3r on each universe; random entries + the same exit for every arm (seed per arm).
READING RULES (declared before the run):
  BETTER than trail10 (same universe), ADOPTION (both universes), and the money rule: as menu 13.
  tp3r robustness (decides whether tp3r deserves to replace trail10 in the PAPER book — the live book is the operator's call): a
    neighbour HOLDS if, on the same universe, CAGR >= trail10's and max drawdown not deeper than trail10's by more than 5 pp.
    tp3r is ROBUST if >= 5 of its 8 neighbours hold on small AND >= 5 of 8 hold on LIQ; FRAGILE otherwise.
  Practical read (descriptive): trail10_w / trail10_m against trail10 = the cost of not checking daily.
READ-ONLY. INGEST_DB_DSN=... PYTHONIOENCODING=utf-8 blackheart-ingest/.venv/Scripts/python research/idx_exit2.py
"""
from __future__ import annotations

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
import idx_exit as X  # noqa: E402
import idx_swing2 as S  # noqa: E402

N_BEFORE = 343
K = X.K
LEAD = X.LEAD
UNIS = ["small", "LIQ"]
ATR_GRID = {"a1.5x2": (1.5, 2), "a1.5x3": (1.5, 3), "a1.5x4": (1.5, 4), "a2x2": (2, 2), "a2x4": (2, 4), "a2.5x2": (2.5, 2), "a2.5x3": (2.5, 3), "a2.5x4": (2.5, 4)}
EXITS = ["sl10", "sl2atr", "b10_20", "b10_30", "b10_50", *ATR_GRID, "trail10_w", "trail10_m", "run3r"]
ARMS = [f"{x}|{u}" for u in UNIS for x in EXITS]
assert len(ARMS) == 32
SEED = 20260918


def make_rules(A, ATR, base):
    def atr0(j, p):
        a = p["state"].get("atr0")
        if a is None:
            a = ATR[p["e"], j]
            a = 0.10 * p["a0"] if (np.isnan(a) or a <= 0) else a
            p["state"]["atr0"] = a
        return a

    def sl(x):
        return lambda t, j, p: 1.0 if A[t, j] <= (1 - x) * p["a0"] else 0

    def slatr(k):
        return lambda t, j, p: 1.0 if A[t, j] <= p["a0"] - k * atr0(j, p) else 0

    def bracket_pct(x, y):
        return lambda t, j, p: 1.0 if (A[t, j] <= (1 - x) * p["a0"] or A[t, j] >= (1 + y) * p["a0"]) else 0

    def bracket_atr(k, m):
        def f(t, j, p):
            r = k * atr0(j, p)
            return 1.0 if (A[t, j] <= p["a0"] - r or A[t, j] >= p["a0"] + m * r) else 0
        return f

    def trail_every(n):
        def f(t, j, p):
            st = p["state"]
            if "stop" not in st or (t - p["e"]) % n == 0:
                st["stop"] = 0.90 * p["peak"]
            return 1.0 if A[t, j] <= st["stop"] else 0
        return f

    def run3r(t, j, p):
        r = 2 * atr0(j, p)
        st = p["state"]
        if A[t, j] >= p["a0"] + 3 * r:
            st["armed"] = True
        if st.get("armed") and A[t, j] <= 0.90 * p["peak"]:
            return 1.0
        return 1.0 if A[t, j] <= p["a0"] - r else 0

    rules = {"sl10": sl(0.10), "sl2atr": slatr(2), "b10_20": bracket_pct(0.10, 0.20), "b10_30": bracket_pct(0.10, 0.30), "b10_50": bracket_pct(0.10, 0.50),
             "trail10_w": trail_every(5), "trail10_m": trail_every(21), "run3r": run3r}
    for name, (k, m) in ATR_GRID.items():
        rules[name] = bracket_atr(k, m)
    rules["trail10"], rules["tp3r"] = base["trail10"], base["tp3r"]
    return rules


def main():
    dsn = os.environ["INGEST_DB_DSN"]
    P, unis, comp, Hp, Lp = X.load_all(dsn, os.environ.get("IDX_EXIT_CACHE"))
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
    base = X.make_rules(A, H, L, ATR, ma20.to_numpy(float), ma50.to_numpy(float), RSI, LO10, LO20)
    rules = make_rules(A, ATR, base)
    universes = {"small": (unis["LIQ"] & ~unis["BLUE"]).to_numpy(bool), "LIQ": unis["LIQ"].to_numpy(bool)}
    n_trials = N_BEFORE + len(ARMS)
    res, rnd, refs = {}, {}, {}
    for u in UNIS:
        uni = universes[u]
        for ref in ("trail10", "tp3r"):
            R, trs, _ = X.run_book(A, H, L, c_in, c_out, entry, score, rules[ref], uni)
            refs[f"{ref}|{u}"] = X.stats(R, trs, dates, n_trials)
        for i, x in enumerate(EXITS):
            arm = f"{x}|{u}"
            R, trs, open_ = X.run_book(A, H, L, c_in, c_out, entry, score, rules[x], uni)
            s = X.stats(R, trs, dates, n_trials); s["open"] = len(open_)
            res[arm] = s
            R, trs, _ = X.run_book(A, H, L, c_in, c_out, None, None, rules[x], uni, rng=np.random.default_rng(SEED + 100 + i))
            rnd[arm] = X.stats(R, trs, dates, n_trials)
            print(f"{arm:16s} n={s['n']:4d} hold={s['hold']:4.0f} hit={s['hit'] * 100:3.0f}% net={s['avg_net'] * 100:+5.2f}% t={s['tstat']:4.1f} "
                  f"cagr={s['cagr'] * 100:+5.1f}% sharpe={s['sharpe']:4.2f} mdd={s['mdd'] * 100:4.0f}% capture={s['capture']:.2f} open={s['open']} | rnd sharpe {rnd[arm]['sharpe']:.2f}", flush=True)
    better, money = {}, {}
    for arm in ARMS:
        x, u = arm.split("|")
        s, ref, rn = res[arm], refs[f"trail10|{u}"], rnd[arm]
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
    holds = {u: [g for g in ATR_GRID if res[f"{g}|{u}"]["cagr"] >= refs[f"trail10|{u}"]["cagr"] and res[f"{g}|{u}"]["mdd"] >= refs[f"trail10|{u}"]["mdd"] - 0.05] for u in UNIS}
    robust = all(len(holds[u]) >= 5 for u in UNIS)

    def yrs(d):
        return " ".join(f"{y % 100:02d}:{v * 100:+.0f}" for y, v in sorted(d.items()))

    def row(label, s, extra):
        return (f"| {label} | {s['n']} | {s['hold']:.0f} | {s['hit'] * 100:.0f} % | {s['avg_net'] * 100:+.2f} % | {s['payoff']:.2f} | {s['tstat']:.1f} | "
                f"{s['cagr'] * 100:+.1f} % | {s['sharpe']:.2f} | {s['mdd'] * 100:.0f} % | {s['mfe'] * 100:.1f} % | {s['capture']:.2f} | {yrs(s['years'])} | {extra} |")
    lines = [f"# IDX menu 14 — set-and-forget exits + the tp3r neighbourhood — {date.today()} — {len(ARMS)} trials, cumulative N = {n_trials}", "",
             f"Entry fixed at the menu-6 lead; book K = {K}, entry close t+1 @offer, exit close t+1 @bid, fees {S.FEE_BUY * 100:.2f}/{S.FEE_SELL * 100:.2f} %; "
             f"{dates[0].date()} -> {dates[-1].date()}. Only the exit changes. Names still open at the last bar: `open` (marked, not counted).", ""]
    for u in UNIS:
        lines += [f"## Universe `{u}`" + (" (the deployed rule: paper_trend + trend_live)" if u == "small" else " (the declared paper rule)"), "",
                  "| exit | trades | hold d | hit | avg net | payoff | t | CAGR | Sharpe | mDD | MFE | capture | years | vs trail10 / money rule |",
                  "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
                  row("**trail10** (deployed)", refs[f"trail10|{u}"], "reference"), row("tp3r (menu 13)", refs[f"tp3r|{u}"], "reference")]
        for x in EXITS:
            arm = f"{x}|{u}"
            lines.append(row(x, res[arm], f"{better[arm]} / {money[arm]} (open {res[arm]['open']}, rnd Sharpe {rnd[arm]['sharpe']:.2f})"))
        lines.append("")
    n_money = sum(1 for v in money.values() if v == "CANDIDATE")
    lines += [f"Candidates for money by the menu-6 rule: {n_money} of {len(ARMS)}.",
              f"BETTER than trail10 on both universes (adoption rule): {', '.join(adopt) if adopt else 'none'}.",
              f"BETTER on one universe only (informative, not adopted): {', '.join(informative) if informative else 'none'}.",
              f"tp3r neighbourhood: small {len(holds['small'])}/8 hold ({', '.join(holds['small']) or '-'}); LIQ {len(holds['LIQ'])}/8 hold ({', '.join(holds['LIQ']) or '-'}) "
              f"-> tp3r is **{'ROBUST' if robust else 'FRAGILE'}**.", "",
              "Limits: as menu 13; stop-loss-only arms hold a name until it leaves the universe, so their open positions at the last bar are marked, not",
              "counted, and their trade counts understate turnover of the equity curve."]
    text = "\n".join(lines); print(text)
    out = os.path.join(HERE, f"IDX_EXIT2_{date.today().isoformat()}.md")
    open(out, "w", encoding="utf-8").write(text + "\n"); print("wrote", out)
    from blackheart_ingest.idx import research_store as rs
    with psycopg.connect(dsn) as conn:
        sid = rs.record_study(conn, "trend_exit2", dates[-1].date(), params={"trials": ARMS, "exits": EXITS, "atr_grid": ATR_GRID, "universes": UNIS, "lead": LEAD, "K": K,
                                                                           "n_trials_cumulative": n_trials, "seed": SEED},
                              summary={"results": res, "random": rnd, "refs": refs, "better": better, "money": money, "adopt": adopt, "informative": informative,
                                       "holds": holds, "robust": robust},
                              names=[], report_path=out, note=f"money {n_money}/{len(ARMS)}; adopt {adopt or 'none'}; tp3r {'ROBUST' if robust else 'FRAGILE'}")
        print("study", sid)


if __name__ == "__main__":
    main()
