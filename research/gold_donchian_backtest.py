#!/usr/bin/env python3
"""Phase-1 standalone-edge check: donchian-55 breakout + 20-bar opposite-channel
(Turtle) exit on gold daily — the SAME strategy family as the crypto DCB-1d sleeve,
so the two are comparable for the risk-parity book. Offline, honest 252-day
annualization (never touches the frozen V11 gate math). Runs on the VPS (reads
market_data XAUUSD 1d). Long+short, one position at a time, 8bps/side cost."""
import subprocess, math

SYM = "XAUUSD"
ENTRY_N = 55
EXIT_N = 20
COST_BPS = 8.0            # per side; gold futures are liquid
ANN = 252                 # gold trading days/yr (NOT 365)
PSQL = ["docker", "exec", "blackheart-postgres", "psql", "-U", "postgres",
        "-d", "trading_db", "-t", "-A", "-F", "|"]


def bars():
    sql = ("SELECT start_time::date, high_price, low_price, close_price "
           "FROM market_data WHERE symbol='%s' AND interval='1d' ORDER BY start_time" % SYM)
    out = subprocess.run(PSQL + ["-c", sql], capture_output=True, text=True)
    rows = []
    for ln in out.stdout.strip().splitlines():
        if ln.count("|") == 3:
            d, h, l, c = ln.split("|")
            rows.append((d, float(h), float(l), float(c)))
    return rows


def run(entry_n, exit_n, long_only):
    b = bars()
    highs = [x[1] for x in b]
    lows = [x[2] for x in b]
    closes = [x[3] for x in b]
    n = len(b)
    pos = 0
    entry = 0.0
    trades = []
    daily = []
    cost = COST_BPS / 10000.0
    prev_px = None
    for i in range(entry_n + 1, n):
        upE = max(highs[i - entry_n:i]); loE = min(lows[i - entry_n:i])
        upX = max(highs[i - exit_n:i]); loX = min(lows[i - exit_n:i])
        c = closes[i]
        if pos != 0 and prev_px is not None and prev_px > 0:
            daily.append(pos * math.log(c / prev_px))
        prev_px = c
        if pos == 1 and c <= loX:
            trades.append((c - entry) / entry - 2 * cost); pos = 0
        elif pos == -1 and c >= upX:
            trades.append((entry - c) / entry - 2 * cost); pos = 0
        if pos == 0:
            if c > upE:
                pos = 1; entry = c
            elif c < loE and not long_only:
                pos = -1; entry = c
    wins = [t for t in trades if t > 0]
    gw = sum(t for t in trades if t > 0); gl = -sum(t for t in trades if t < 0)
    pf = gw / gl if gl > 0 else float("inf")
    tot = 1.0
    for t in trades:
        tot *= (1 + t)
    years = (int(b[-1][0][:4]) - int(b[entry_n + 1][0][:4])) or 1
    cagr = (tot ** (1.0 / years) - 1) * 100
    mu = sum(daily) / len(daily) if daily else 0
    sd = math.sqrt(sum((x - mu) ** 2 for x in daily) / len(daily)) if len(daily) > 1 else 0
    sharpe = (mu / sd * math.sqrt(ANN)) if sd > 0 else 0
    side = "long-only " if long_only else "long+short"
    print("  d-%2d/%2d %s trades=%3d win%%=%.1f PF=%.2f Sharpe252=%+.2f CAGR=%+.1f%% grow=%.2fx"
          % (entry_n, exit_n, side, len(trades),
             100.0*len(wins)/len(trades) if trades else 0, pf, sharpe, cagr, tot))


print("GOLD (XAUUSD 1d, %.0fbps/side) donchian breakout + opposite-channel exit:" % COST_BPS)
for ln in (True, False):
    for en, xn in [(55, 20), (20, 10), (40, 20), (100, 40)]:
        run(en, xn, ln)
