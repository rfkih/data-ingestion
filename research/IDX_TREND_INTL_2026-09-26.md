# The trend rule out of universe: Thailand, Malaysia, Singapore - 2026-09-26 - 3 trials, cumulative N = 1025

Unchanged IDX rule (60-day high / MA200 / 1.5x volume, K 10, trail 10 %, index regime gate), 2010-01 -> 2026-09, Yahoo daily, the 250
largest stocks listed today per market (survivors), liquid = top 100 by 60-day median value, 0.30 % half-spread + 0.10/0.20 % fees.
Placebo = random entries, same book and exit, 50 seeds.

| market | names | trades | hit | avg net | t | CAGR | Sharpe | mDD | placebo Sharpe median / p95 | rule pct | index CAGR | pass |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| thailand | 250 | 504 | 43 % | +5.06 % | 4.26 | +16.0 % | 1.16 | -28 % | 0.66 / 0.83 | 100 | +8.2 % | yes |
| malaysia | 250 | 315 | 49 % | +7.44 % | 5.21 | +13.8 % | 1.06 | -20 % | 0.87 / 1.03 | 96 | +1.7 % | yes |
| singapore | 250 | 310 | 42 % | +5.37 % | 3.64 | +8.4 % | 0.88 | -17 % | 0.67 / 0.89 | 94 | +4.1 % | no |

**Verdict: GENERALISES** (2 of 3 markets pass).

Limits: survivors only (the placebo on the same names cancels most of it, not all: a trend rule buys winners, which survivors are
rich in); IDX's cost model on other markets; Yahoo data quality varies (Malaysian and Singapore small caps are thin); the
universe is the 250 largest companies today, not a point-in-time list.
