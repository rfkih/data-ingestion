#!/usr/bin/env python3
"""Risk-parity breadth: fetch candidate non-crypto daily sleeves (Yahoo) + BTC (DB),
build the daily-return correlation matrix. Filter = keep instruments uncorrelated
with crypto AND gold AND each other (|corr|<~0.3). Runs on VPS. No numpy."""
import json, math, subprocess, urllib.request, urllib.parse
from datetime import datetime, timezone

# name -> Yahoo ticker
CANDIDATES = {
    "GOLD": "GC=F", "BONDS10y": "ZN=F", "BOND30y": "ZB=F", "OIL": "CL=F",
    "COPPER": "HG=F", "SILVER": "SI=F", "NATGAS": "NG=F",
    "EURUSD": "EURUSD=X", "USDJPY": "JPY=X", "DXY": "DX-Y.NYB",
    "SP500": "ES=F", "CORN": "ZC=F",
}
PSQL = ["docker", "exec", "blackheart-postgres", "psql", "-U", "postgres",
        "-d", "trading_db", "-t", "-A", "-F", "|"]


def yf_closes(ticker):
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           + urllib.parse.quote(ticker) + "?interval=1d&range=25y")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=40) as r:
            d = json.load(r)
        res = d["chart"]["result"][0]
        out = {}
        for i, e in enumerate(res["timestamp"]):
            c = res["indicators"]["quote"][0]["close"][i]
            if c is not None and c > 0:
                out[datetime.fromtimestamp(e, tz=timezone.utc).date().isoformat()] = c
        return out
    except Exception as ex:
        print("  FETCH FAIL %s (%s): %s" % (ticker, ticker, ex))
        return {}


def db_closes(sym):
    out = subprocess.run(PSQL + ["-c",
        "SELECT start_time::date, close_price FROM market_data WHERE symbol='%s' "
        "AND interval='1d' ORDER BY start_time" % sym], capture_output=True, text=True)
    res = {}
    for ln in out.stdout.strip().splitlines():
        if "|" in ln:
            dt, px = ln.split("|"); res[dt] = float(px)
    return res


def rets(closes):
    dts = sorted(closes); r = {}
    for i in range(1, len(dts)):
        p0, p1 = closes[dts[i-1]], closes[dts[i]]
        if p0 > 0 and p1 > 0:
            r[dts[i]] = math.log(p1/p0)
    return r


def pearson(a, b):
    common = sorted(set(a) & set(b))
    if len(common) < 100:
        return None, len(common)
    xs = [a[d] for d in common]; ys = [b[d] for d in common]
    n = len(xs); mx = sum(xs)/n; my = sum(ys)/n
    cov = sum((x-mx)*(y-my) for x, y in zip(xs, ys))
    vx = sum((x-mx)**2 for x in xs); vy = sum((y-my)**2 for y in ys)
    return (cov/math.sqrt(vx*vy) if vx > 0 and vy > 0 else None), n


series = {"CRYPTO(BTC)": rets(db_closes("BTCUSDT"))}
for name, tk in CANDIDATES.items():
    c = yf_closes(tk)
    if c:
        series[name] = rets(c)
        print("  %-11s %-11s bars=%d %s..%s" % (name, tk, len(c), min(c), max(c)))

names = list(series.keys())
print("\n=== daily log-return correlation matrix ===")
print("           " + " ".join("%8.8s" % n for n in names))
for a in names:
    row = []
    for b in names:
        c, n = pearson(series[a], series[b])
        row.append("%8s" % ("%.3f" % c if c is not None else "NA"))
    print("%-11s" % a + " ".join(row))

print("\n=== |corr| vs CRYPTO(BTC) and GOLD (breadth filter, want both < 0.30) ===")
for a in names:
    if a in ("CRYPTO(BTC)", "GOLD"):
        continue
    cc, _ = pearson(series[a], series["CRYPTO(BTC)"])
    cg, _ = pearson(series[a], series.get("GOLD", {}))
    flag = "KEEP" if (cc is not None and cg is not None and abs(cc) < 0.30 and abs(cg) < 0.30) else "drop"
    print("  %-11s vsBTC=%6s vsGOLD=%6s  -> %s"
          % (a, "%.3f" % cc if cc is not None else "NA",
             "%.3f" % cg if cg is not None else "NA", flag))
