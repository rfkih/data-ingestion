# IDX menu 37 (Track B2) - calendar effects, long-only - 2026-09-26 - 12 trials (ids 861..872), cumulative N = 872

Question: does holding only inside a calendar window beat HOLDING the same exposure, net of IDX costs - as a sleeve, or as a timing overlay for the books? Per episode: excess = window return - (days x the same year's mean daily return). JKSE (Yahoo ^JKSE) 2006-01 -> 2026-09 is the primary series; COMPOSITE (idx.index_daily), LIQ and SMALL equal-weight baskets (idx.bar, membership at the prior close) 2020-26 are the tradeable checks. Round trip: index 80 bps; baskets measured at closing offer/bid + fees (mean LIQ 87 bps, SMALL 97 bps per day-pair).

## Pre-registered bar (from the script docstring, written before the run)

- OVERLAY: gross t >= 2 (sign as hypothesised), mean excess of that sign in all 3 blocks (2006-12, 2013-19, 2020-26) and >= 60 % of years, placebo (500 circular shifts of the window) percentile >= 95, every +/-1-day neighbour keeps the sign and >= half the excess, same sign on COMP, LIQ, SMALL.
- SLEEVE (sign + only): the overlay bar AND net excess > 0 with t_net >= 2, neighbours net > 0, costs x1.5 net > 0, LIQ or SMALL net > 0.
- ROBUST = overlay bar; PARTIAL = t and placebo pass, one of blocks / neighbours / tradeable fails; FRAGILE = placebo fails or two fail; CLOSED = |t| < 2 or wrong sign.

## JKSE 2006-26 (primary)

| window | sign | episodes | days % | gross excess bps/ep | t | net bps (80) | t net | net x1.5 | 2006-12 | 2013-19 | 2020-26 | years ok | placebo pct | DSR sleeve | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| tom13 | + | 248 | 20 % | +19.8 | +1.11 | -60.2 | -3.38 | -100.2 | +51 | +1 | +4 | 48 % | 90 | 0.00 | **CLOSED** |
| tom33 | + | 248 | 30 % | +40.5 | +1.85 | -39.5 | -1.80 | -79.5 | +96 | +30 | -14 | 71 % | 99 | 0.00 | **CLOSED** |
| preleb5 | + | 21 | 2 % | +49.8 | +1.15 | -30.2 | -0.69 | -70.2 | +123 | +79 | -52 | 57 % | 78 | 0.00 | **CLOSED** |
| ramadan20 | + | 21 | 8 % | -6.1 | -0.05 | -86.1 | -0.76 | -126.1 | +3 | +76 | -97 | 62 % | 55 | 0.00 | **CLOSED** |
| postleb5 | - | 21 | 2 % | -139.9 | -1.45 | -219.9 | -2.28 | -259.9 | -177 | -85 | -157 | 71 % | 98 | 0.00 | **CLOSED** |
| declast10 | + | 20 | 4 % | +74.1 | +1.26 | -5.9 | -0.10 | -45.9 | +39 | +222 | -58 | 60 % | 77 | 0.00 | **CLOSED** |
| janfirst10 | + | 20 | 4 % | +30.4 | +0.43 | -49.6 | -0.70 | -89.6 | -126 | +63 | +131 | 45 % | 61 | 0.00 | **CLOSED** |
| preholiday | + | 235 | 5 % | +0.8 | +0.10 | -79.2 | -9.70 | -119.2 | -14 | +17 | +4 | 62 % | 52 | 0.00 | **CLOSED** |
| monday | - | 1005 | 20 % | -13.1 | -2.94 | -93.1 | -20.95 | -133.1 | -16 | -12 | -11 | 76 % | 100 | 0.00 | **PARTIAL** |
| friday | + | 975 | 19 % | +1.4 | +0.41 | -78.6 | -22.07 | -118.6 | +7 | +1 | -3 | 48 % | 68 | 0.00 | **CLOSED** |

## Tradeable checks 2020-26 (gross / net excess, bps per episode; t gross)

| window | COMP gross | COMP net | LIQ gross | LIQ net | LIQ t | SMALL gross | SMALL net | SMALL t | SMALL sleeve CAGR / Sharpe / mDD |
|---|---|---|---|---|---|---|---|---|---|
| tom13 | +8 | -72 | +8 | -78 | +0.29 | +10 | -86 | +0.30 | -8.9 % / -0.71 / -60 % |
| tom33 | -5 | -85 | -13 | -100 | -0.34 | -17 | -114 | -0.39 | -11.5 % / -0.79 / -68 % |
| preleb5 | -51 | -131 | -89 | -179 | -1.38 | -118 | -219 | -1.82 | -2.2 % / -0.61 / -14 % |
| ramadan20 | -93 | -173 | -329 | -418 | -1.21 | -468 | -567 | -1.52 | -5.4 % / -0.70 / -31 % |
| postleb5 | -156 | -236 | -77 | -166 | -0.55 | -78 | -178 | -0.67 | -1.8 % / -0.27 / -23 % |
| declast10 | -58 | -138 | -179 | -277 | -2.20 | -229 | -342 | -2.70 | -2.5 % / -0.65 / -23 % |
| janfirst10 | +159 | +79 | +209 | +129 | +0.91 | +191 | +103 | +0.81 | +0.7 % / 0.23 / -12 % |
| preholiday | +4 | -76 | -12 | -100 | -1.06 | -20 | -118 | -1.56 | -13.2 % / -2.58 / -61 % |
| monday | -11 | -91 | +2 | -84 | +0.26 | +4 | -92 | +0.49 | -35.3 % / -3.41 / -94 % |
| friday | -2 | -82 | -7 | -95 | -1.01 | -11 | -110 | -1.55 | -39.4 % / -4.61 / -96 % |

## Neighbours (JKSE, window +/- 1 day) and battery

| window | neighbours: gross / net bps (t) | T | B | P | N | X | overlay bar | sleeve bar |
|---|---|---|---|---|---|---|---|---|
| tom13 | ('tom', 2, 3): +32 / -48 (+1.6); ('tom', 0, 3): +9 / -71 (+0.6); ('tom', 1, 2): +27 / -53 (+1.8); ('tom', 1, 4): +30 / -50 (+1.7) | fail | fail | fail | fail | pass | fail | fail |
| tom33 | ('tom', 4, 3): +34 / -46 (+1.5); ('tom', 2, 3): +32 / -48 (+1.6); ('tom', 3, 2): +48 / -32 (+2.4); ('tom', 3, 4): +50 / -30 (+2.3) | fail | fail | pass | pass | fail | fail | fail |
| preleb5 | ('preleb', 4, 0): +73 / -7 (+1.9); ('preleb', 6, 0): +82 / +2 (+1.5); ('preleb', 5, 1): +37 / -43 (+0.9) | fail | fail | fail | pass | fail | fail | fail |
| ramadan20 | ('preleb', 19, 0): +12 / -68 (+0.1); ('preleb', 21, 0): -13 / -93 (-0.1); ('preleb', 20, 1): -20 / -100 (-0.2) | fail | fail | fail | fail | fail | fail | fail |
| postleb5 | ('postleb', 4, 0): -162 / -242 (-1.4); ('postleb', 6, 0): -170 / -250 (-1.6); ('postleb', 5, 1): -82 / -162 (-1.3) | fail | pass | pass | pass | pass | fail | - |
| declast10 | ('declast', 9, 0): +94 / +14 (+1.5); ('declast', 11, 0): +64 / -16 (+1.1) | fail | fail | fail | pass | fail | fail | fail |
| janfirst10 | ('janfirst', 9, 0): -18 / -98 (-0.2); ('janfirst', 11, 0): +18 / -62 (+0.2) | fail | fail | fail | fail | pass | fail | fail |
| preholiday | ('prehol', 2, 0): +21 / -59 (+1.6); ('prehol', 2, 1): +19 / -61 (+2.3) | fail | fail | fail | pass | fail | fail | fail |
| monday | ('dow_nohol', 0, 0): -15 / -95 (-3.4); ('postweekend', 0, 0): -8 / -88 (-1.7) | pass | pass | pass | pass | fail | fail | - |
| friday | ('dow_nohol', 4, 0): +1 / -79 (+0.4); ('preweekend', 0, 0): +1 / -79 (+0.4) | fail | fail | fail | pass | fail | fail | fail |

## Per year, JKSE gross excess (bps per episode)

| window | 06 | 07 | 08 | 09 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 | 18 | 19 | 20 | 21 | 22 | 23 | 24 | 25 | 26 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| tom13 | +119 | +76 | -58 | +142 | -7 | +28 | +57 | -67 | -19 | +122 | +37 | -4 | -24 | -40 | +106 | +55 | -26 | +1 | -31 | -21 | -56 |
| tom33 | +172 | +71 | +168 | +113 | +30 | +72 | +43 | +30 | -6 | +104 | +143 | +4 | -51 | -17 | +129 | +8 | -27 | +20 | -73 | +5 | -157 |
| preleb5 | -91 | +577 | -108 | +50 | +402 | -14 | +44 | -41 | -40 | +20 | +252 | +53 | +20 | +288 | -14 | -64 | -75 | +2 | +1 | +156 | -372 |
| ramadan20 | +29 | +1506 | -943 | +5 | +155 | -781 | +51 | +73 | +270 | -59 | +119 | +17 | +390 | -278 | -48 | -67 | +210 | +336 | +70 | -146 | -1037 |
| postleb5 | +159 | -411 | -1438 | -93 | +334 | +396 | -188 | -158 | -112 | -295 | +248 | -65 | -277 | +62 | +668 | -300 | -883 | -27 | -288 | -264 | -5 |
| declast10 | +104 | -341 | +561 | -213 | -39 | +302 | -101 | +142 | +42 | +547 | +19 | +419 | +135 | +251 | -47 | -63 | +37 | +252 | -417 | -108 |  |
| janfirst10 |  | -597 | -85 | -211 | +282 | -386 | +243 | +190 | +237 | -26 | -212 | -128 | +47 | +337 | -17 | +617 | +150 | -332 | -59 | -93 | +650 |
| preholiday | +22 | -44 | -71 | -44 | +22 | +14 | +2 | +30 | +64 | -42 | -5 | -8 | +29 | +50 | +10 | +5 | +18 | +4 | -14 | -3 | +6 |
| monday | -34 | +14 | -24 | -4 | +4 | -37 | -32 | -29 | -6 | -33 | -5 | -0 | +8 | -19 | -40 | +3 | -25 | -2 | -2 | +8 | -20 |
| friday | +25 | -13 | +23 | +17 | -12 | -3 | +8 | -1 | -3 | +10 | -18 | -2 | +11 | +7 | +13 | -7 | +6 | +5 | -8 | -20 | -12 |

January, SMALL minus LIQ over the first 10 trading days (bps): 2021: -101, 2022: -175, 2023: -39, 2024: +54, 2025: +57, 2026: +76

Lebaran closures used (last trading day -> reopen): 2006-10-24: 2006-10-20 -> 2006-10-30; 2007-10-13: 2007-10-11 -> 2007-10-17; 2008-10-01: 2008-09-26 -> 2008-10-06; 2009-09-20: 2009-09-17 -> 2009-09-24; 2010-09-10: 2010-09-07 -> 2010-09-15; 2011-08-31: 2011-08-26 -> 2011-09-05; 2012-08-19: 2012-08-16 -> 2012-08-23; 2013-08-08: 2013-08-02 -> 2013-08-12; 2014-07-28: 2014-07-25 -> 2014-08-04; 2015-07-17: 2015-07-15 -> 2015-07-22; 2016-07-06: 2016-07-01 -> 2016-07-11; 2017-06-25: 2017-06-22 -> 2017-07-03; 2018-06-15: 2018-06-08 -> 2018-06-20; 2019-06-05: 2019-05-31 -> 2019-06-10; 2020-05-24: 2020-05-20 -> 2020-05-26; 2021-05-13: 2021-05-11 -> 2021-05-17; 2022-05-02: 2022-04-28 -> 2022-05-09; 2023-04-22: 2023-04-18 -> 2023-04-26; 2024-04-10: 2024-04-05 -> 2024-04-16; 2025-03-31: 2025-03-27 -> 2025-04-08; 2026-03-20: 2026-03-17 -> 2026-03-25

## Survivor on the combined book (monday; trials 11-12)

Correlation of the SMALL sleeve's daily net returns with: combined +0.24, gap +0.15, trend +0.14, ML +0.21

The survivor's sign is negative, so trial 11 (a long-only sleeve INSIDE the window) is by construction a long-Mondays sleeve - shown for completeness, not a candidate. Trial 12 (the overlay) is the real test.

| book | CAGR | Sharpe | mDD |
|---|---|---|---|
| combined | 34.4 % | 1.78 | -22 % |
| blend_80_20 | 15.4 % | 1.05 | -24 % |
| sleeve_alone | -38.4 % | -4.12 | -90 % |
| overlay: defer entries past window (80 trades) | 33.2 % | 1.73 | -22 % |

## Reading (written after the run)

1. **No calendar sleeve exists on IDX.** Not one window clears its own round trip: the best gross excess over holding is
   +74 bps per episode (last 10 days of December) against an 80 bps round trip, and every window is net NEGATIVE on JKSE
   and on the tradeable LIQ / SMALL baskets 2020-26 (measured round trip 86 / 97 bps). The only window net-positive anywhere
   is the first 10 days of January on the 2020-26 baskets (+146..+159 bps, t ~1.0, 6 Januaries) - on 20 years of JKSE it is
   +30 bps gross, 45 % of years, placebo pct 61: noise.
2. **Turn-of-month was real in 2006-12 and is gone.** tom33 (last 3 + first 3): +96 bps/episode in 2006-12, +30 in 2013-19,
   -14 in 2020-26; placebo pct 99 over the full span but t 1.85, and the desk's own 2020-26 series are flat (COMP -5, LIQ -8,
   SMALL -11). The classic -1..+3 window is weaker still (t 1.1). A decayed anomaly: holding trend/value entries "through the
   turn of the month" is worth nothing measurable today.
3. **Ramadan / Lebaran.** The Ramadan run-up (20 days) is a myth on this data (-6 bps, t -0.05; 2020-26 -97). Pre-Lebaran
   5 days +50 bps, t 1.15, negative in 2020-26. **Post-Lebaran is the one consistent pattern**: -140 bps vs holding over the
   first 5 days after the holiday, negative in 3/3 blocks and 71 % of years, placebo pct 98, all neighbours and COMP / LIQ /
   SMALL negative - but 21 episodes, t -1.45, so CLOSED by the letter. It cannot be a sleeve (long-only, negative sign); as an
   overlay it says at most "no need to hurry new buys in the first week after Lebaran" - a free, low-evidence preference, not
   a rule. Worth a re-test when it has more episodes.
4. **Year-end.** December window dressing +74 bps, t 1.26, 2020-26 block negative (-58; baskets -169..-214): no evidence for
   "delay buys to after window dressing", and none for a small-cap January effect (SMALL minus LIQ over the first 10 days of
   January: 3 of 6 years negative).
5. **Pre-holiday and Friday: nothing** (+0.8 and +1.4 bps/day, t 0.1 / 0.4).
6. **Monday is the only effect that passes the statistics - and it lives in the index, not in what the desk trades.** JKSE
   Monday -13 bps vs the same year's mean day, t -2.9, 3/3 blocks (-16 / -12 / -11), 76 % of years, placebo pct 100, neighbours
   hold (Mondays not after a holiday -15, t -3.4); COMPOSITE 2020-26 agrees (-11). But the equal-weight LIQ and SMALL baskets are
   +3 / +5 on Mondays in 2020-26: the weakness sits in the cap-weighted large names. Verdict PARTIAL (tradeable check fails). As
   an overlay on the combined book (defer trend/ML entries that land on a Monday to Tuesday, 80 trades moved) CAGR 32.7 -> 32.3 %,
   Sharpe 1.75 -> 1.74, mDD unchanged: nothing to adopt. Day-of-week can never be a sleeve (50+ round trips a year at ~80 bps).
7. **Verdict for menu 37: CLOSED as a family** (9 CLOSED, 1 PARTIAL with no economic use). Calendar timing adds nothing to the
   trend / value / gap-fade / ML books; the DSR of every calendar sleeve at N = 872 is 0.00. Nothing to deploy.

