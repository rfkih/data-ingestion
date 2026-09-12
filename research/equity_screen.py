#!/usr/bin/env python3
"""Equity-expansion Phase 1 screen + book-lift (blueprint 2026-07-18 s8b).

Donchian breakout + opposite-channel exit (identical rule to
research/multi_sleeve_walkforward.py sleeve_daily) over every cached symbol in
/tmp/equity/ (incl. screen-only ^STI/^KLSE), grid
[(20,10),(40,20),(55,20),(100,40)] x {long-only, long+short}. Costs PER SIDE by
venue: US 5bps, SGX 15bps, Bursa 30bps (charged 2x at exit = round trip, same
convention as multi_sleeve_walkforward). Metrics per cell: n_trades, PF,
Sharpe(252), total return pct, maxDD. Orthogonality: Pearson corr of strategy
daily returns vs BTCUSDT / XAUUSD daily log-returns on the candidate
in-position days (min 200 overlapping days).

PASS = best cell (max Sharpe among n>=40 cells): PF>1.2 AND Sharpe>0.35 AND
n>=40 AND abs(corr_btc)<0.30 AND abs(corr_gold)<0.30.

Book-lift (auto if >=1 tradeable passer): base 4-sleeve book (CRYPTO pool
BTC/ETH/SOL/XRP d-20/10 2-sided 8bps + GOLD XAUUSD d-40/20 L + CORN ZC=F
d-55/20 L + USDJPY JPY=X d-55/20 L, all 8bps as in multi_sleeve_walkforward)
vs base+candidate via the same OOS vol-parity walk-forward (5 folds):
OOS Sharpe(252), DSR@20/50/100, maxDD, max pairwise abs corr.

Run ON THE VPS after equity_ohlc_loader.py:
    python3 equity_screen.py > /tmp/equity/screen_out.txt
Writes /tmp/equity/screen_results.json. READ-ONLY vs the DB.
"""
import json
import math
import os
import subprocess
import time
import urllib.parse
import urllib.request
from statistics import NormalDist
from datetime import datetime, timezone

OUTDIR = "/tmp/equity"
COST_BY_MARKET = {"US": 5.0, "SGX": 15.0, "BURSA": 30.0}
GRID = [(20, 10), (40, 20), (55, 20), (100, 40)]
BASE_COST = 8.0                 # base-book sleeves (multi_sleeve_walkforward parity)
DSR_GATE = 0.762                # current 4-sleeve book DSR to beat
PSQL = ["docker", "exec", "blackheart-postgres", "psql", "-U", "postgres",
        "-d", "trading_db", "-t", "-A", "-F", "|"]


def yf_ohlc(tk):
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           + urllib.parse.quote(tk) + "?interval=1d&range=25y")
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=40) as r:
                d = json.load(r)
            break
        except Exception:
            time.sleep(5)
    res = d["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    out = {}
    for i, e in enumerate(res["timestamp"]):
        h, l, c = q["high"][i], q["low"][i], q["close"][i]
        if None not in (h, l, c) and c > 0:
            out[datetime.fromtimestamp(e, tz=timezone.utc).date().isoformat()] = (h, l, c)
    return out


def db_ohlc(sym):
    out = subprocess.run(PSQL + ["-c",
        "SELECT start_time::date, high_price, low_price, close_price FROM market_data "
        "WHERE symbol='%s' AND interval='1d' ORDER BY start_time" % sym],
        capture_output=True, text=True)
    m = {}
    for ln in out.stdout.strip().splitlines():
        if ln.count("|") == 3:
            d, h, l, c = ln.split("|")
            m[d] = (float(h), float(l), float(c))
    return m


def load_csv(tk):
    m = {}
    with open(os.path.join(OUTDIR, tk.replace("^", "_") + ".csv")) as f:
        next(f)
        for ln in f:
            d, o, h, l, c, v = ln.strip().split(",")
            m[d] = (float(h), float(l), float(c))
    return m


def sleeve(ohlc, en, xn, long_only, cost_bps):
    """Donchian breakout / opposite-channel exit. Same daily series as
    multi_sleeve_walkforward.sleeve_daily (2x per-side cost charged at exit);
    additionally returns closed-trade net simple returns."""
    dates = sorted(ohlc)
    H = [ohlc[d][0] for d in dates]
    L = [ohlc[d][1] for d in dates]
    C = [ohlc[d][2] for d in dates]
    n = len(dates)
    pos = 0
    prev = None
    cost = cost_bps / 10000.0
    daily = {}
    trades = []
    cur = 0.0
    for i in range(en + 1, n):
        upE = max(H[i - en:i]); loE = min(L[i - en:i])
        upX = max(H[i - xn:i]); loX = min(L[i - xn:i])
        c = C[i]; r = 0.0
        if pos != 0 and prev and prev > 0:
            r = pos * math.log(c / prev)
            cur += r
        prev = c
        if pos == 1 and c <= loX:
            r -= 2 * cost; cur -= 2 * cost
            trades.append(math.exp(cur) - 1.0); cur = 0.0; pos = 0
        elif pos == -1 and c >= upX:
            r -= 2 * cost; cur -= 2 * cost
            trades.append(math.exp(cur) - 1.0); cur = 0.0; pos = 0
        if pos == 0:
            if c > upE:
                pos = 1; cur = 0.0
            elif c < loE and not long_only:
                pos = -1; cur = 0.0
        daily[dates[i]] = r
    return daily, trades


def sharpe(s, ann):
    if len(s) < 2:
        return 0.0
    mu = sum(s) / len(s)
    sd = math.sqrt(sum((x - mu) ** 2 for x in s) / len(s))
    return mu / sd * math.sqrt(ann) if sd > 0 else 0.0


def maxdd(s):
    eq = 1.0; peak = 1.0; mdd = 0.0
    for r in s:
        eq *= math.exp(r); peak = max(peak, eq); mdd = max(mdd, (peak - eq) / peak)
    return mdd * 100


def deflated_sharpe(s, n_trials):
    n = len(s)
    if n < 3:
        return 0.0
    mu = sum(s) / n
    sd = math.sqrt(sum((x - mu) ** 2 for x in s) / n)
    if sd == 0:
        return 0.0
    sr = mu / sd
    sk = (sum((x - mu) ** 3 for x in s) / n) / sd ** 3
    ku = (sum((x - mu) ** 4 for x in s) / n) / sd ** 4
    Z = NormalDist(); e = 0.5772156649015329
    v = (1 - sk * sr + (ku - 1) / 4.0 * sr ** 2) / (n - 1)
    if v <= 0:
        return 0.0
    se = math.sqrt(v)
    emax = (Z.inv_cdf(1 - 1.0 / n_trials) * (1 - e)
            + Z.inv_cdf(1 - 1.0 / (n_trials * math.e)) * e) if n_trials > 1 else 0.0
    return Z.cdf((sr - se * emax) / se)


def avg_pairwise_corr(vecs):
    cs = []
    for a in range(len(vecs)):
        for b in range(a + 1, len(vecs)):
            pairs = [(x, y) for x, y in zip(vecs[a], vecs[b]) if x != 0 and y != 0]
            if len(pairs) < 30:
                continue
            ax = [p[0] for p in pairs]; bx = [p[1] for p in pairs]
            ma = sum(ax) / len(ax); mb = sum(bx) / len(bx)
            cov = sum((x - ma) * (y - mb) for x, y in pairs) / len(pairs)
            sa = math.sqrt(sum((x - ma) ** 2 for x in ax) / len(ax))
            sb = math.sqrt(sum((y - mb) ** 2 for y in bx) / len(bx))
            if sa > 0 and sb > 0:
                cs.append(cov / (sa * sb))
    return (sum(cs) / len(cs) if cs else float("nan"),
            (max(abs(c) for c in cs) if cs else float("nan")))


def run_wf(sleeve_daily_list, n_folds=5):
    common = sorted(set.intersection(*[set(s) for s in sleeve_daily_list]))
    vecs = [[s.get(d, 0.0) for d in common] for s in sleeve_daily_list]
    N = len(common); warm = N // 3; step = (N - warm) // n_folds
    oos_comb = []
    for k in range(n_folds):
        tr_end = warm + k * step
        te_end = warm + (k + 1) * step if k < n_folds - 1 else N
        if te_end - tr_end < 5:
            continue
        vols = [math.sqrt(sum(v[i] ** 2 for i in range(tr_end)) / tr_end) or 1e-9
                for v in vecs]
        inv = [1.0 / x for x in vols]; tot = sum(inv); w = [x / tot for x in inv]
        for i in range(tr_end, te_end):
            oos_comb.append(sum(w[j] * vecs[j][i] for j in range(len(vecs))))
    return common, vecs, oos_comb, N, warm


def logret(ohlc):
    dates = sorted(ohlc); out = {}
    for i in range(1, len(dates)):
        c0 = ohlc[dates[i - 1]][2]; c1 = ohlc[dates[i]][2]
        if c0 > 0 and c1 > 0:
            out[dates[i]] = math.log(c1 / c0)
    return out


def corr_vs(daily, aret):
    """Pearson corr of strategy daily returns vs asset log-returns on the
    strategy in-position days. None if <200 overlapping days."""
    pairs = [(r, aret[d]) for d, r in daily.items() if r != 0.0 and d in aret]
    if len(pairs) < 200:
        return None
    ax = [p[0] for p in pairs]; bx = [p[1] for p in pairs]
    n = len(pairs)
    ma = sum(ax) / n; mb = sum(bx) / n
    cov = sum((x - ma) * (y - mb) for x, y in pairs) / n
    sa = math.sqrt(sum((x - ma) ** 2 for x in ax) / n)
    sb = math.sqrt(sum((y - mb) ** 2 for y in bx) / n)
    if sa == 0 or sb == 0:
        return None
    return cov / (sa * sb)


def crypto_pool():
    cd = {}
    for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]:
        for d, r in sleeve(db_ohlc(sym), 20, 10, False, BASE_COST)[0].items():
            cd.setdefault(d, []).append(r)
    return {d: sum(v) / len(v) for d, v in cd.items()}


def wf_metrics(lst):
    common, vecs, oos, N, warm = run_wf(lst)
    ac, mc = avg_pairwise_corr(vecs)
    return {"common_days": N, "oos_sharpe": round(sharpe(oos, 252), 3),
            "dsr20": round(deflated_sharpe(oos, 20), 3),
            "dsr50": round(deflated_sharpe(oos, 50), 3),
            "dsr100": round(deflated_sharpe(oos, 100), 3),
            "maxdd": round(maxdd(oos), 1), "max_abs_corr": round(mc, 3)}


def main():
    man = json.load(open(os.path.join(OUTDIR, "manifest.json")))
    btc_r = logret(db_ohlc("BTCUSDT"))
    gold_r = logret(db_ohlc("XAUUSD"))
    print("corr refs: BTCUSDT %d ret-days, XAUUSD %d ret-days"
          % (len(btc_r), len(gold_r)))
    cells = []
    best = {}
    for tk in sorted(man):
        info = man[tk]
        if info["bars"] < 750:
            print("SKIP %s (bars=%d < 750)" % (tk, info["bars"]))
            continue
        ohlc = load_csv(tk)
        cost = COST_BY_MARKET[info["market"]]
        sym_cells = []
        for en, xn in GRID:
            for lo in (True, False):
                daily, trades = sleeve(ohlc, en, xn, lo, cost)
                ser = [daily[d] for d in sorted(daily)]
                wins = sum(t for t in trades if t > 0)
                loss = -sum(t for t in trades if t < 0)
                pf = (wins / loss) if loss > 0 else (999.0 if wins > 0 else 0.0)
                cb = corr_vs(daily, btc_r)
                cg = corr_vs(daily, gold_r)
                cell = {"sym": tk, "market": info["market"],
                        "cfg": "%d/%d" % (en, xn), "side": "L" if lo else "LS",
                        "n": len(trades), "pf": round(pf, 3),
                        "sharpe": round(sharpe(ser, 252), 3),
                        "ret_pct": round((math.exp(sum(ser)) - 1) * 100, 1),
                        "mdd": round(maxdd(ser), 1),
                        "corr_btc": None if cb is None else round(cb, 3),
                        "corr_gold": None if cg is None else round(cg, 3),
                        "screen_only": info.get("screen_only", False)}
                sym_cells.append(cell)
                cells.append(cell)
        elig = [c for c in sym_cells if c["n"] >= 40]
        b = dict(max(elig or sym_cells, key=lambda c: c["sharpe"]))
        cb, cg = b["corr_btc"], b["corr_gold"]
        b["PASS"] = bool(b["pf"] > 1.2 and b["sharpe"] > 0.35 and b["n"] >= 40
                         and cb is not None and abs(cb) < 0.30
                         and cg is not None and abs(cg) < 0.30)
        best[tk] = b

    hdr = "%-8s %-5s %-7s %-3s %4s %7s %7s %7s %6s %8s %9s %s"
    print("")
    print("=== BEST CELL PER SYMBOL (max Sharpe among n>=40 cells) ===")
    print(hdr % ("sym", "mkt", "cfg", "sd", "n", "PF", "Sharpe", "retPct",
                 "mDD", "corrBTC", "corrGOLD", "PASS"))
    for tk in sorted(best, key=lambda k: -best[k]["sharpe"]):
        b = best[tk]
        print(hdr % (tk, b["market"], b["cfg"], b["side"], b["n"],
                     "%.2f" % min(b["pf"], 99), "%.3f" % b["sharpe"],
                     "%.0f" % b["ret_pct"], "%.0f" % b["mdd"],
                     "n/a" if b["corr_btc"] is None else "%+.2f" % b["corr_btc"],
                     "n/a" if b["corr_gold"] is None else "%+.2f" % b["corr_gold"],
                     ("PASS" if b["PASS"] else "-")
                     + (" (screen-only)" if b["screen_only"] else "")))

    print("")
    print("=== TOP 20 CELLS OVERALL (by Sharpe, n>=10) ===")
    top20 = sorted([c for c in cells if c["n"] >= 10],
                   key=lambda c: -c["sharpe"])[:20]
    print(hdr % ("sym", "mkt", "cfg", "sd", "n", "PF", "Sharpe", "retPct",
                 "mDD", "corrBTC", "corrGOLD", ""))
    for c in top20:
        print(hdr % (c["sym"], c["market"], c["cfg"], c["side"], c["n"],
                     "%.2f" % min(c["pf"], 99), "%.3f" % c["sharpe"],
                     "%.0f" % c["ret_pct"], "%.0f" % c["mdd"],
                     "n/a" if c["corr_btc"] is None else "%+.2f" % c["corr_btc"],
                     "n/a" if c["corr_gold"] is None else "%+.2f" % c["corr_gold"],
                     ""))

    passers = [b for b in best.values() if b["PASS"]]
    tradeable = sorted([b for b in passers if not b["screen_only"]],
                       key=lambda b: -b["sharpe"])
    print("")
    print("PASSERS: %d (%d tradeable)" % (len(passers), len(tradeable)))

    book = None
    if tradeable:
        print("")
        print("=== BOOK-LIFT: base 4-sleeve book vs base+candidate ===")
        base = [crypto_pool(),
                sleeve(db_ohlc("XAUUSD"), 40, 20, True, BASE_COST)[0],
                sleeve(yf_ohlc("ZC=F"), 55, 20, True, BASE_COST)[0],
                sleeve(yf_ohlc("JPY=X"), 55, 20, True, BASE_COST)[0]]
        book = {"BASE(CRYPTO+GOLD+CORN+USDJPY)": wf_metrics(base)}
        for b in tradeable[:3]:
            en, xn = b["cfg"].split("/")
            cand, _ = sleeve(load_csv(b["sym"]), int(en), int(xn),
                             b["side"] == "L", COST_BY_MARKET[b["market"]])
            book["BASE+%s(%s,%s)" % (b["sym"], b["cfg"], b["side"])] = \
                wf_metrics(base + [cand])
        khdr = "%-32s %5s %9s %6s %6s %6s %6s %6s"
        print(khdr % ("book", "days", "SharpeOOS", "DSR20", "DSR50", "DSR100",
                      "mDD", "mxCor"))
        for k, v in book.items():
            print(khdr % (k, v["common_days"], "%.3f" % v["oos_sharpe"],
                          "%.3f" % v["dsr20"], "%.3f" % v["dsr50"],
                          "%.3f" % v["dsr100"], "%.1f" % v["maxdd"],
                          "%.3f" % v["max_abs_corr"]))
        print("DSR gate to beat: %.3f" % DSR_GATE)
    else:
        print("No tradeable passers -> book-lift skipped.")

    with open(os.path.join(OUTDIR, "screen_results.json"), "w") as f:
        json.dump({"cells": cells, "best": best,
                   "passers": [b["sym"] for b in passers],
                   "book_lift": book}, f, indent=1)
    print("")
    print("results -> %s/screen_results.json" % OUTDIR)


if __name__ == "__main__":
    main()
