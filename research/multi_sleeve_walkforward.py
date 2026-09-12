#!/usr/bin/env python3
"""BREADTH TEST — does adding orthogonal non-crypto trend sleeves lift the combined
risk-parity book DSR toward the 0.90 admission gate? Generalizes
risk_parity_walkforward.py (2 sleeves) to N. Incremental N=2..5, honest OOS
vol-parity walk-forward, Bailey/LdP deflated DSR. Runs on VPS (Yahoo + DB). 8bps/side.

Sleeves (each = donchian breakout + opp-channel exit; config = the robust cell from
the edge screen): CRYPTO pool (BTC/ETH/SOL/XRP d-20/10 2-sided) + GOLD (XAUUSD d-40/20 L)
+ CORN (ZC d-55/20 L, Sharpe 0.72) + USDJPY (JPY d-55/20 L, 0.57) + OIL (CL d-40/20 L, 0.30).
All pairwise |corr|<0.30 vs crypto AND gold (orthogonality screen)."""
import json, math, subprocess, urllib.request, urllib.parse
from statistics import NormalDist
from datetime import datetime, timezone

COST_BPS = 8.0
PSQL = ["docker", "exec", "blackheart-postgres", "psql", "-U", "postgres",
        "-d", "trading_db", "-t", "-A", "-F", "|"]


def yf_ohlc(tk):
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           + urllib.parse.quote(tk) + "?interval=1d&range=25y")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=40) as r:
        d = json.load(r)
    res = d["chart"]["result"][0]; q = res["indicators"]["quote"][0]; out = {}
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
            d, h, l, c = ln.split("|"); m[d] = (float(h), float(l), float(c))
    return m


def sleeve_daily(ohlc, en, xn, long_only):
    dates = sorted(ohlc); H = [ohlc[d][0] for d in dates]
    L = [ohlc[d][1] for d in dates]; C = [ohlc[d][2] for d in dates]
    n = len(dates); pos = 0; prev = None; cost = COST_BPS/10000.0; daily = {}
    for i in range(en+1, n):
        upE = max(H[i-en:i]); loE = min(L[i-en:i])
        upX = max(H[i-xn:i]); loX = min(L[i-xn:i]); c = C[i]; r = 0.0
        if pos != 0 and prev and prev > 0:
            r = pos*math.log(c/prev)
        prev = c
        if pos == 1 and c <= loX:
            r -= 2*cost; pos = 0
        elif pos == -1 and c >= upX:
            r -= 2*cost; pos = 0
        if pos == 0:
            if c > upE:
                pos = 1
            elif c < loE and not long_only:
                pos = -1
        daily[dates[i]] = r
    return daily


def crypto_pool():
    cd = {}
    for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]:
        for d, r in sleeve_daily(db_ohlc(sym), 20, 10, False).items():
            cd.setdefault(d, []).append(r)
    return {d: sum(v)/len(v) for d, v in cd.items()}


def sharpe(s, ann):
    if len(s) < 2:
        return 0.0
    mu = sum(s)/len(s); sd = math.sqrt(sum((x-mu)**2 for x in s)/len(s))
    return mu/sd*math.sqrt(ann) if sd > 0 else 0.0


def maxdd(s):
    eq = 1.0; peak = 1.0; mdd = 0.0
    for r in s:
        eq *= math.exp(r); peak = max(peak, eq); mdd = max(mdd, (peak-eq)/peak)
    return mdd*100


def deflated_sharpe(s, n_trials):
    n = len(s)
    if n < 3:
        return 0.0
    mu = sum(s)/n; sd = math.sqrt(sum((x-mu)**2 for x in s)/n)
    if sd == 0:
        return 0.0
    sr = mu/sd
    sk = (sum((x-mu)**3 for x in s)/n)/sd**3
    ku = (sum((x-mu)**4 for x in s)/n)/sd**4
    Z = NormalDist(); e = 0.5772156649015329
    v = (1 - sk*sr + (ku-1)/4.0*sr**2)/(n-1)
    if v <= 0:
        return 0.0
    se = math.sqrt(v)
    emax = (Z.inv_cdf(1-1.0/n_trials)*(1-e) + Z.inv_cdf(1-1.0/(n_trials*math.e))*e) if n_trials > 1 else 0.0
    return Z.cdf((sr - se*emax)/se)


def avg_pairwise_corr(vecs):
    cs = []
    for a in range(len(vecs)):
        for b in range(a+1, len(vecs)):
            pairs = [(x, y) for x, y in zip(vecs[a], vecs[b]) if x != 0 and y != 0]
            if len(pairs) < 30:
                continue
            ax = [p[0] for p in pairs]; bx = [p[1] for p in pairs]
            ma = sum(ax)/len(ax); mb = sum(bx)/len(bx)
            cov = sum((x-ma)*(y-mb) for x, y in pairs)/len(pairs)
            sa = math.sqrt(sum((x-ma)**2 for x in ax)/len(ax))
            sb = math.sqrt(sum((y-mb)**2 for y in bx)/len(bx))
            if sa > 0 and sb > 0:
                cs.append(cov/(sa*sb))
    return sum(cs)/len(cs) if cs else float("nan"), (max(abs(c) for c in cs) if cs else float("nan"))


def run_wf(sleeve_daily_list, n_folds=5):
    common = sorted(set.intersection(*[set(s) for s in sleeve_daily_list]))
    vecs = [[s.get(d, 0.0) for d in common] for s in sleeve_daily_list]
    N = len(common); warm = N//3; step = (N-warm)//n_folds
    oos_comb = []
    for k in range(n_folds):
        tr_end = warm + k*step
        te_end = warm + (k+1)*step if k < n_folds-1 else N
        if te_end - tr_end < 5:
            continue
        vols = [math.sqrt(sum(v[i]**2 for i in range(tr_end))/tr_end) or 1e-9 for v in vecs]
        inv = [1.0/x for x in vols]; tot = sum(inv); w = [x/tot for x in inv]
        for i in range(tr_end, te_end):
            oos_comb.append(sum(w[j]*vecs[j][i] for j in range(len(vecs))))
    return common, vecs, oos_comb, N, warm


NAMES = ["CRYPTO", "GOLD", "CORN", "USDJPY", "OIL"]
print("building sleeves...")
S = {
    "CRYPTO": crypto_pool(),
    "GOLD": sleeve_daily(db_ohlc("XAUUSD"), 40, 20, True),
    "CORN": sleeve_daily(yf_ohlc("ZC=F"), 55, 20, True),
    "USDJPY": sleeve_daily(yf_ohlc("JPY=X"), 55, 20, True),
    "OIL": sleeve_daily(yf_ohlc("CL=F"), 40, 20, True),
}
print("\n=== BREADTH: incremental sleeves, OOS vol-parity walk-forward (5 folds) ===")
print("N  sleeves                         commonDays  OOS-Sharpe(252)  DSR@20  DSR@50  DSR@100  maxDD%  avgCorr  max|corr|")
for n in range(2, 6):
    names = NAMES[:n]
    lst = [S[x] for x in names]
    common, vecs, oos, Ndays, warm = run_wf(lst)
    sh = sharpe(oos, 252)
    dd = maxdd(oos)
    ac, mc = avg_pairwise_corr(vecs)
    print("%d  %-30s  %6d      %+.3f          %.3f   %.3f   %.3f    %4.0f    %+.3f   %.3f"
          % (n, "+".join(names), Ndays, sh,
             deflated_sharpe(oos, 20), deflated_sharpe(oos, 50), deflated_sharpe(oos, 100),
             dd, ac, mc))
