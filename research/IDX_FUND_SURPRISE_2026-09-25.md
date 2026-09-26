# IDX menu 38 (B3) - fundamental earnings surprise / post-earnings drift - 2026-09-26 - 10 trials, cumulative N = 883 - PRELIM

Reported numbers from idx.fundamental (parsed by 2026-09-25 16:00 UTC; drain still running), discrete quarters, signal day = published_at (WIB), entry at the close of the first session after publication (closing offer), exit at the closing bid H sessions later, fees 0.10/0.20 %. Universe: 60-day median value >= Rp 5 bn, close >= Rp 100. Excess = net minus the same-window gross return of the universe's same-market-cap quintile. Entries 2021-01 -> 2026-09-25. Not the price-reaction PEAD of IDX_SWING (0/22).

## Coverage (parsed share of IDX quarterly/annual workbooks, by fiscal year and liquidity at publication)

| fiscal year | <1bn | 1-5bn | 5-50bn | >=50bn |
|---|---|---|---|---|
| 2019 | 479/479 (100 %) | 37/37 (100 %) | 38/38 (100 %) | 7/7 (100 %) |
| 2020 | 2001/2001 (100 %) | 243/243 (100 %) | 301/301 (100 %) | 124/124 (100 %) |
| 2021 | 1808/1808 (100 %) | 419/419 (100 %) | 447/447 (100 %) | 152/152 (100 %) |
| 2022 | 1961/1961 (100 %) | 457/457 (100 %) | 449/449 (100 %) | 153/153 (100 %) |
| 2023 | 2242/2246 (100 %) | 428/429 (100 %) | 451/452 (100 %) | 106/106 (100 %) |
| 2024 | 2292/2380 (96 %) | 345/360 (96 %) | 386/403 (96 %) | 102/106 (96 %) |
| 2025 | 2209/2263 (98 %) | 549/554 (99 %) | 487/493 (99 %) | 178/181 (98 %) |
| 2026 | 1077/1078 (100 %) | 277/278 (100 %) | 254/254 (100 %) | 92/92 (100 %) |

Liquid names (>= Rp 5 bn) parsed share by period: 2019: TAHUNAN 100 %; 2020: TAHUNAN 100 %, TW1 100 %, TW2 100 %, TW3 100 %; 2021: TAHUNAN 100 %, TW1 100 %, TW2 100 %, TW3 100 %; 2022: TAHUNAN 100 %, TW1 100 %, TW2 100 %, TW3 100 %; 2023: TAHUNAN 99 %, TW1 100 %, TW2 100 %, TW3 100 %; 2024: TAHUNAN 95 %, TW1 100 %, TW2 91 %, TW3 98 %; 2025: TAHUNAN 100 %, TW1 94 %, TW2 99 %, TW3 100 %; 2026: TW1 100 %, TW2 100 %

Usable events (discrete quarter computable, published <= 150 d after period end, universe, entry >= 2021): 2653 - by entry year 2021: 381, 2022: 427, 2023: 440, 2024: 397, 2025: 494, 2026: 514. The 2021-23 liquid set is 75-87 % parsed and the discrete quarter needs the previous report of the year as well, so 2021-23 is thinner than 2024-26; the tilt is towards names the value/quality pipeline fetched first (larger, profitable). Hence PRELIM.

## Pre-registered bar

CANDIDATE = (a) mean net excess > 0 with month-clustered t >= 2.5; (b) excess > 0 in >= 4/6 entry years; (c) standalone Rp 20 M book (5 % NAV/trade, 20 slots, lots of 100) Sharpe >= 0.8 and mDD >= -25 %. ROBUST additionally needs placebo pct >= 95, >= 3/4 neighbours with t >= 2, costs x1.5 still positive, 1-day delay positive with t >= 2.

## Results - primary arms

| arm | signal | bucket | H | trades | net/trade | median net | hit | excess/trade | median exc | t (month) | years exc>0 | book CAGR | Sharpe | mDD | by year (excess) | pass |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| T1 | E_mc | top 20 % | 20 | 552 | +0.17 % | -1.45 % | 46 % | +0.45 % | -1.69 % | 1.56 | 3/6 | 0.0 % | 0.06 | -25 % | 21:-2.0(105) 22:+1.9(85) 23:-1.2(61) 24:-0.6(85) 25:+3.8(90) 26:+0.7(126) | no |
| T2 | E_mc | top 20 % | 40 | 530 | -1.46 % | -5.01 % | 39 % | +0.23 % | -2.61 % | 0.75 | 3/6 | 1.7 % | 0.20 | -24 % | 21:-2.3(105) 22:+2.7(85) 23:-2.6(61) 24:+1.5(85) 25:+2.4(90) 26:-0.5(104) | no |
| T3 | E_mc | top 20 % | 60 | 526 | -0.23 % | -6.09 % | 39 % | +0.38 % | -2.88 % | 0.10 | 4/6 | 1.9 % | 0.20 | -40 % | 21:-3.1(105) 22:+3.1(85) 23:-2.7(61) 24:+1.9(85) 25:+2.9(90) 26:+0.1(100) | no |
| T4 | E_sue | top 20 % | 40 | 435 | -0.80 % | -3.68 % | 41 % | +0.87 % | -1.22 % | 1.66 | 4/6 | 1.0 % | 0.15 | -24 % | 21:-2.2(37) 22:+2.3(65) 23:-1.1(68) 24:+1.2(61) 25:+2.9(95) 26:+0.3(109) | no |
| T5 | R | top 20 % | 40 | 535 | -0.12 % | -4.66 % | 39 % | +0.48 % | -3.63 % | 0.56 | 3/6 | 3.0 % | 0.28 | -45 % | 21:+2.7(138) 22:-3.4(90) 23:-6.0(53) 24:+5.3(72) 25:+3.5(106) 26:-3.3(76) | no |
| T6 | E_mc +accruals | top 20 % | 40 | 357 | -0.17 % | -3.85 % | 41 % | +1.29 % | -1.88 % | 1.57 | 3/6 | 3.6 % | 0.39 | -22 % | 21:-0.8(77) 22:+6.6(47) 23:-2.3(45) 24:+3.8(61) 25:+1.8(61) 26:-0.4(66) | no |

Reference (not trials): every universe event, no signal: H20: n 2631, net -1.40 %, excess -0.72 %, t -0.93; H40: n 2536, net -1.52 %, excess -0.42 %, t -0.13; H60: n 2514, net -0.65 %, excess -0.04 %, t 0.14

E_mc quintiles at H = 40 (diagnostic, monotonicity): Q1: n 477, net -0.24 %, excess +0.35 %; Q2: n 490, net -4.92 %, excess -3.71 %; Q3: n 497, net +0.14 %, excess +1.60 %; Q4: n 536, net -1.16 %, excess -0.53 %; Q5: n 530, net -1.46 %, excess +0.23 %

## Battery on the best H = 40 arm (T4: E_sue)

| check | trades | net/trade | excess/trade | t | years exc>0 |
|---|---|---|---|---|---|
| top_decile | 218 | -2.18 % | +0.37 % | 0.23 | 3/6 |
| top_tercile | 717 | -1.01 % | +0.17 % | 1.37 | 4/6 |
| H20 | 456 | +0.59 % | +0.24 % | 1.72 | 3/6 |
| H60 | 429 | -0.66 % | +1.27 % | 1.54 | 5/6 |
| cost1.5 | 435 | -1.23 % | +0.44 % | 1.41 | 3/6 |
| delay1 | 432 | -1.74 % | -0.13 % | 1.05 | 3/6 |

Placebo (same names, 200 random entry dates): real mean excess +0.87 %, placebo median +1.38 %, 95th +3.21 %, real at percentile 30.

Next-open entry, 2025-26 events (opens stored): n 201, net/trade -1.25 % at the open vs -0.98 % at the close.

Standalone book of T4: CAGR 1.0 %, Sharpe 0.15, mDD -24 %, 2021: -1 % 2022: -1 % 2023: -6 % 2024: -4 % 2025: +39 % 2026: -14 %; DSR 0.00 at N = 883.

## Verdict: **CLOSED (PRELIM)**

