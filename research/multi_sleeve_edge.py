#!/usr/bin/env python3
"""Standalone donchian trend edge for candidate sleeves (Yahoo OHLC). Same
donchian breakout + opposite-channel exit as the gold/crypto sleeves, 252-day
annualization, 8bps/side. Reports long-only AND long+short across channels so a
sleeve is only added if it carries real edge (not just orthogonality)."""
import json, math, urllib.request, urllib.parse

CANDS = {"GOLD": "GC=F", "BONDS10y": "ZN=F", "OIL": "CL=F", "EURUSD": "EURUSD=X",
         "USDJPY": "JPY=X", "CORN": "ZC=F", "NATGAS": "NG=F"}
COST_BPS = 8.0
ANN = 252
GRID = [(20, 10), (40, 20), (55, 20), (100, 40)]


def yf_ohlc(tk):
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           + urllib.parse.quote(tk) + "?interval=1d&range=25y")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=40) as r:
        d = json.load(r)
    res = d["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    H, L, C = [], [], []
    for i in range(len(res["timestamp"])):
        h, l, c = q["high"][i], q["low"][i], q["close"][i]
        if None not in (h, l, c) and c > 0:
            H.append(h); L.append(l); C.append(c)
    return H, L, C


def bt(H, L, C, en, xn, long_only):
    n = len(C); pos = 0; entry = 0.0; trades = []; daily = []
    cost = COST_BPS/10000.0; prev = None
    for i in range(en+1, n):
        upE = max(H[i-en:i]); loE = min(L[i-en:i])
        upX = max(H[i-xn:i]); loX = min(L[i-xn:i]); c = C[i]
        if pos != 0 and prev and prev > 0:
            daily.append(pos*math.log(c/prev))
        prev = c
        if pos == 1 and c <= loX:
            trades.append((c-entry)/entry - 2*cost); pos = 0
        elif pos == -1 and c >= upX:
            trades.append((entry-c)/entry - 2*cost); pos = 0
        if pos == 0:
            if c > upE:
                pos = 1; entry = c
            elif c < loE and not long_only:
                pos = -1; entry = c
    if not trades or len(daily) < 50:
        return None
    gw = sum(t for t in trades if t > 0); gl = -sum(t for t in trades if t < 0)
    pf = gw/gl if gl > 0 else float("inf")
    mu = sum(daily)/len(daily); sd = math.sqrt(sum((x-mu)**2 for x in daily)/len(daily))
    sharpe = mu/sd*math.sqrt(ANN) if sd > 0 else 0
    tot = 1.0
    for t in trades:
        tot *= (1+t)
    return len(trades), pf, sharpe, (tot-1)*100


for name, tk in CANDS.items():
    try:
        H, L, C = yf_ohlc(tk)
    except Exception as ex:
        print("%-9s FETCH FAIL %s" % (name, ex)); continue
    best = None
    print("%-9s (%s, %d bars)" % (name, tk, len(C)))
    for lo in (True, False):
        for en, xn in GRID:
            r = bt(H, L, C, en, xn, lo)
            if not r:
                continue
            nt, pf, sh, tg = r
            tag = "L " if lo else "LS"
            mark = ""
            if pf > 1.2 and sh > 0.3:
                mark = " *"
            print("   %s d-%3d/%2d  n=%3d PF=%.2f Sharpe=%+.2f tot=%+.0f%%%s"
                  % (tag, en, xn, nt, pf, sh, tg, mark))
