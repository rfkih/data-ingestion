#!/usr/bin/env python3
"""Risk-parity combined-book measurement (2026-07-16): gold (XAUUSD) long-only
donchian-trend sleeve + crypto DCB-1d pooled trend sleeve (BTC/ETH/SOL/XRP), at
their measured daily-return correlation. Both sleeves use the SAME donchian
breakout + opposite-channel (Turtle) exit family so they are directly comparable,
matching the deployed DonchianBreakoutEngine and the gold offline validation.

The point: each sleeve is sub-DSR SOLO (crypto book-Sharpe ~1.0/DSR 0.27, gold
Sharpe ~0.6), but they are ~uncorrelated (offline GOLD~BTC corr 0.098). Vol-parity
combining two ~uncorrelated positive-Sharpe streams RAISES the book Sharpe and
LOWERS drawdown — the risk-parity thesis and the portfolio-admission-gate evidence.

Honest annualization: gold 252 trading days/yr, crypto 365. The combined book's
Sharpe is computed on the union daily grid; days a sleeve is flat contribute 0.
Runs on the VPS (reads market_data). Offline; never touches the frozen V11 gate.
"""
import subprocess, math

COST_BPS = 8.0
PSQL = ["docker", "exec", "blackheart-postgres", "psql", "-U", "postgres",
        "-d", "trading_db", "-t", "-A", "-F", "|"]

CRYPTO = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
GOLD = "XAUUSD"
# Channel params: crypto uses donchian-20 entry (the book's baseline); gold uses
# donchian-20 entry too so both sleeves are the same rule. Opposite-channel exit
# = 10-bar. long_only gold (shorting fights gold's uptrend); crypto two-sided.
ENTRY_N = 20
EXIT_N = 10


def bars(sym):
    sql = ("SELECT start_time::date, high_price, low_price, close_price "
           "FROM market_data WHERE symbol='%s' AND interval='1d' ORDER BY start_time" % sym)
    out = subprocess.run(PSQL + ["-c", sql], capture_output=True, text=True)
    rows = []
    for ln in out.stdout.strip().splitlines():
        if ln.count("|") == 3:
            d, h, l, c = ln.split("|")
            try:
                rows.append((d, float(h), float(l), float(c)))
            except ValueError:
                pass
    return rows


def sleeve_daily(sym, long_only):
    """Return {date: position_daily_log_return} for a donchian breakout + opp-channel
    exit sleeve on one symbol. Position return on a held day = pos * log(c/prev_c)."""
    b = bars(sym)
    highs = [x[1] for x in b]; lows = [x[2] for x in b]; closes = [x[3] for x in b]
    dates = [x[0] for x in b]
    n = len(b)
    pos = 0; entry = 0.0; prev = None
    cost = COST_BPS / 10000.0
    daily = {}
    for i in range(ENTRY_N + 1, n):
        upE = max(highs[i - ENTRY_N:i]); loE = min(lows[i - ENTRY_N:i])
        upX = max(highs[i - EXIT_N:i]); loX = min(lows[i - EXIT_N:i])
        c = closes[i]
        r = 0.0
        if pos != 0 and prev is not None and prev > 0:
            r = pos * math.log(c / prev)
        prev = c
        # exits (opposite channel); subtract round-trip cost on exit bar
        if pos == 1 and c <= loX:
            r -= 2 * cost; pos = 0
        elif pos == -1 and c >= upX:
            r -= 2 * cost; pos = 0
        # entries
        if pos == 0:
            if c > upE:
                pos = 1; entry = c
            elif c < loE and not long_only:
                pos = -1; entry = c
        daily[dates[i]] = daily.get(dates[i], 0.0) + r
    return daily


def stats(series, ann):
    """series: list of daily returns. Returns (mu, sd, sharpe, cagr, maxDD)."""
    if not series:
        return 0, 0, 0, 0, 0
    mu = sum(series) / len(series)
    sd = math.sqrt(sum((x - mu) ** 2 for x in series) / len(series)) if len(series) > 1 else 0
    sharpe = (mu / sd * math.sqrt(ann)) if sd > 0 else 0
    # equity curve + maxDD
    eq = 1.0; peak = 1.0; maxdd = 0.0
    for r in series:
        eq *= math.exp(r)
        peak = max(peak, eq)
        maxdd = max(maxdd, (peak - eq) / peak)
    years = len(series) / ann
    cagr = (eq ** (1.0 / years) - 1) * 100 if years > 0 else 0
    return mu, sd, sharpe, cagr, maxdd * 100


def main():
    # crypto pooled sleeve: equal-weight the 4 coins' daily returns
    crypto_daily = {}
    for sym in CRYPTO:
        s = sleeve_daily(sym, long_only=False)
        for d, r in s.items():
            crypto_daily.setdefault(d, []).append(r)
    # equal-weight across coins active that day
    crypto = {d: sum(v) / len(v) for d, v in crypto_daily.items()}

    gold = sleeve_daily(GOLD, long_only=True)

    # union date grid; flat day = 0
    all_dates = sorted(set(crypto) | set(gold))
    c_series = [crypto.get(d, 0.0) for d in all_dates]
    g_series = [gold.get(d, 0.0) for d in all_dates]

    # correlation on overlapping days where BOTH are non-zero (both in a position)
    both = [(crypto[d], gold[d]) for d in all_dates
            if d in crypto and d in gold and crypto[d] != 0 and gold[d] != 0]
    if len(both) > 2:
        cx = [x for x, _ in both]; gx = [y for _, y in both]
        mcx = sum(cx) / len(cx); mgx = sum(gx) / len(gx)
        cov = sum((a - mcx) * (b - mgx) for a, b in both) / len(both)
        sdc = math.sqrt(sum((a - mcx) ** 2 for a in cx) / len(cx))
        sdg = math.sqrt(sum((b - mgx) ** 2 for b in gx) / len(gx))
        corr = cov / (sdc * sdg) if sdc > 0 and sdg > 0 else 0
    else:
        corr = float("nan")

    # solo stats (crypto 365, gold 252). For the combined book use 365 (daily grid).
    _, sdc_all, shc, cagrc, ddc = stats([r for r in c_series if True], 365)
    _, sdg_all, shg, cagrg, ddg = stats([r for r in g_series if True], 252)

    # vol-parity weights: inverse-vol on the sleeves' full-series daily vol
    vc = math.sqrt(sum(x * x for x in c_series) / len(c_series)) or 1e-9
    vg = math.sqrt(sum(x * x for x in g_series) / len(g_series)) or 1e-9
    wc = (1 / vc) / (1 / vc + 1 / vg)
    wg = (1 / vg) / (1 / vc + 1 / vg)
    combined = [wc * c_series[i] + wg * g_series[i] for i in range(len(all_dates))]
    _, sdcomb, shcomb, cagrcomb, ddcomb = stats(combined, 365)

    print("=== RISK-PARITY COMBINED BOOK (gold long-only + crypto DCB-1d pool) ===")
    print("cost=%.0fbps/side  entry=donchian-%d  exit=opp-channel-%d" % (COST_BPS, ENTRY_N, EXIT_N))
    print("union daily grid: %d days (%s -> %s)" % (len(all_dates), all_dates[0], all_dates[-1]))
    print("cross-sleeve daily-return corr (both-in-position days, n=%d): %.3f" % (len(both), corr))
    print()
    print("SOLO crypto pool (365-ann):  Sharpe %+.3f  CAGR %+.1f%%  maxDD %.1f%%  dailyVol %.4f" % (shc, cagrc, ddc, sdc_all))
    print("SOLO gold long-only (252-ann): Sharpe %+.3f  CAGR %+.1f%%  maxDD %.1f%%  dailyVol %.4f" % (shg, cagrg, ddg, sdg_all))
    print()
    print("vol-parity weights: crypto %.2f / gold %.2f" % (wc, wg))
    print("COMBINED BOOK (365-ann):     Sharpe %+.3f  CAGR %+.1f%%  maxDD %.1f%%  dailyVol %.4f" % (shcomb, cagrcomb, ddcomb, sdcomb))
    print()
    diversification_ratio = (wc * sdc_all + wg * sdg_all) / sdcomb if sdcomb > 0 else 0
    print("Sharpe lift vs best solo:    %+.3f (combined %.3f vs best-solo %.3f)" % (shcomb - max(shc, shg), shcomb, max(shc, shg)))
    print("diversification ratio (wtd-avg-vol / book-vol): %.3f  (>1 = real diversification)" % diversification_ratio)


if __name__ == "__main__":
    main()
