#!/usr/bin/env python3
"""Phase-1 GO/NO-GO: is gold orthogonal to BTC/ETH? (2026-07-15)

Computes daily log-return Pearson correlation of gold (Yahoo GC=F) vs BTC & ETH
(DB market_data 1d), full-sample + per-year. Asset-level correlation is the
first-order driver of sleeve orthogonality — if gold returns are ~uncorrelated
with BTC, a gold trend sleeve is a genuine risk-parity diversifier vs the
BTC-beta-synchronized crypto book (the DSR-0.27 corr-sync wall). Runs on the VPS
(Yahoo + DB). No numpy dependency (manual Pearson)."""
import json, math, subprocess, urllib.request, urllib.parse
from datetime import datetime, timezone

YF = ("https://query1.finance.yahoo.com/v8/finance/chart/"
      + urllib.parse.quote("GC=F") + "?interval=1d&range=25y")
PSQL = ["docker", "exec", "blackheart-postgres", "psql", "-U", "postgres",
        "-d", "trading_db", "-t", "-A", "-F", "|"]


def gold_closes():
    req = urllib.request.Request(YF, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=40) as r:
        d = json.load(r)
    res = d["chart"]["result"][0]
    out = {}
    for i, epoch in enumerate(res["timestamp"]):
        c = res["indicators"]["quote"][0]["close"][i]
        if c is None:
            continue
        out[datetime.fromtimestamp(epoch, tz=timezone.utc).date().isoformat()] = c
    return out


def db_closes(sym):
    sql = ("SELECT start_time::date, close_price FROM market_data "
           "WHERE symbol='%s' AND interval='1d' ORDER BY start_time" % sym)
    out = subprocess.run(PSQL + ["-c", sql], capture_output=True, text=True)
    res = {}
    for line in out.stdout.strip().splitlines():
        if "|" in line:
            dt, px = line.split("|")
            res[dt] = float(px)
    return res


def logrets(closes, dates):
    r = {}
    for i in range(1, len(dates)):
        p0, p1 = closes[dates[i - 1]], closes[dates[i]]
        if p0 > 0 and p1 > 0:
            r[dates[i]] = math.log(p1 / p0)
    return r


def pearson(xs, ys):
    n = len(xs)
    if n < 20:
        return None, n
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0 or vy <= 0:
        return None, n
    return cov / math.sqrt(vx * vy), n


def corr(a_ret, b_ret, year=None):
    common = sorted(set(a_ret) & set(b_ret))
    if year:
        common = [d for d in common if d.startswith(str(year))]
    xs = [a_ret[d] for d in common]
    ys = [b_ret[d] for d in common]
    return pearson(xs, ys)


gold = gold_closes()
btc = db_closes("BTCUSDT")
eth = db_closes("ETHUSDT")
gd = sorted(gold)
gr = logrets(gold, gd)
br = logrets(btc, sorted(btc))
er = logrets(eth, sorted(eth))

print("gold days=%d (%s..%s)  btc days=%d  eth days=%d"
      % (len(gold), gd[0], gd[-1], len(btc), len(eth)))
print("\n=== daily log-return correlation (full sample, overlapping days) ===")
for name, r in [("GOLD~BTC", corr(gr, br)), ("GOLD~ETH", corr(gr, er)),
                ("BTC~ETH (crypto-internal ref)", corr(br, er))]:
    c, n = r
    print("  %-30s corr=%s  n=%d" % (name, ("%.3f" % c) if c is not None else "NA", n))

print("\n=== GOLD~BTC by year (regime check) ===")
for y in range(2018, 2027):
    c, n = corr(gr, br, y)
    if c is not None:
        print("  %d  corr=%.3f  n=%d" % (y, c, n))
