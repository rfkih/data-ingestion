# IDX menu 38 (B3) - fundamental earnings surprise / post-earnings drift - 2026-09-25 - 10 trials, cumulative N = 883 - PRELIM

Reported numbers from idx.fundamental (parsed by 2026-09-25 16:00 UTC; drain still running), discrete quarters, signal day = published_at (WIB), entry at the close of the first session after publication (closing offer), exit at the closing bid H sessions later, fees 0.10/0.20 %. Universe: 60-day median value >= Rp 5 bn, close >= Rp 100. Excess = net minus the same-window gross return of the universe's same-market-cap quintile. Entries 2021-01 -> 2026-09-25. Not the price-reaction PEAD of IDX_SWING (0/22).

## Coverage (parsed share of IDX quarterly/annual workbooks, by fiscal year and liquidity at publication)

| fiscal year | <1bn | 1-5bn | 5-50bn | >=50bn |
|---|---|---|---|---|
| 2019 | 198/479 (41 %) | 28/37 (76 %) | 35/38 (92 %) | 7/7 (100 %) |
| 2020 | 599/2001 (30 %) | 164/243 (67 %) | 247/301 (82 %) | 116/124 (94 %) |
| 2021 | 480/1808 (27 %) | 257/419 (61 %) | 333/447 (74 %) | 127/152 (84 %) |
| 2022 | 573/1961 (29 %) | 276/457 (60 %) | 337/449 (75 %) | 136/153 (89 %) |
| 2023 | 698/2246 (31 %) | 266/429 (62 %) | 394/452 (87 %) | 99/106 (93 %) |
| 2024 | 1027/2380 (43 %) | 302/360 (84 %) | 382/403 (95 %) | 102/106 (96 %) |
| 2025 | 875/2263 (39 %) | 474/554 (86 %) | 484/493 (98 %) | 178/181 (98 %) |
| 2026 | 389/1078 (36 %) | 261/278 (94 %) | 254/254 (100 %) | 92/92 (100 %) |

Liquid names (>= Rp 5 bn) parsed share by period: 2019: TAHUNAN 93 %; 2020: TAHUNAN 100 %, TW1 81 %, TW2 78 %, TW3 75 %; 2021: TAHUNAN 100 %, TW1 72 %, TW2 70 %, TW3 66 %; 2022: TAHUNAN 100 %, TW1 73 %, TW2 72 %, TW3 75 %; 2023: TAHUNAN 99 %, TW1 86 %, TW2 86 %, TW3 84 %; 2024: TAHUNAN 95 %, TW1 100 %, TW2 89 %, TW3 97 %; 2025: TAHUNAN 100 %, TW1 93 %, TW2 99 %, TW3 99 %; 2026: TW1 100 %, TW2 100 %

Usable events (discrete quarter computable, published <= 150 d after period end, universe, entry >= 2021): 2653 - by entry year 2021: 381, 2022: 427, 2023: 440, 2024: 397, 2025: 494, 2026: 514. The 2021-23 liquid set is 75-87 % parsed and the discrete quarter needs the previous report of the year as well, so 2021-23 is thinner than 2024-26; the tilt is towards names the value/quality pipeline fetched first (larger, profitable). Hence PRELIM.

## Pre-registered bar

CANDIDATE = (a) mean net excess > 0 with month-clustered t >= 2.5; (b) excess > 0 in >= 4/6 entry years; (c) standalone Rp 20 M book (5 % NAV/trade, 20 slots, lots of 100) Sharpe >= 0.8 and mDD >= -25 %. ROBUST additionally needs placebo pct >= 95, >= 3/4 neighbours with t >= 2, costs x1.5 still positive, 1-day delay positive with t >= 2.

## Results - primary arms

| arm | signal | bucket | H | trades | net/trade | median net | hit | excess/trade | median exc | t (month) | years exc>0 | book CAGR | Sharpe | mDD | by year (excess) | pass |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| T1 | E_mc | top 20 % | 20 | 552 | +0.17 % | -1.45 % | 46 % | +0.45 % | -1.69 % | 1.56 | 3/6 | 0.0 % | 0.06 | -25 % | 21:-2.0(105) 22:+1.9(85) 23:-1.2(61) 24:-0.6(85) 25:+3.8(90) 26:+0.7(126) | no |
| T2 | E_mc | top 20 % | 40 | 530 | -1.46 % | -5.01 % | 39 % | +0.22 % | -2.61 % | 0.74 | 3/6 | 1.8 % | 0.20 | -24 % | 21:-2.3(105) 22:+2.7(85) 23:-2.6(61) 24:+1.5(85) 25:+2.4(90) 26:-0.5(104) | no |
| T3 | E_mc | top 20 % | 60 | 526 | -0.22 % | -6.09 % | 39 % | +0.38 % | -2.88 % | 0.10 | 4/6 | 2.0 % | 0.21 | -40 % | 21:-3.1(105) 22:+3.1(85) 23:-2.7(61) 24:+1.9(85) 25:+2.9(90) 26:+0.1(100) | no |
| T4 | E_sue | top 20 % | 40 | 435 | -0.78 % | -3.68 % | 42 % | +0.87 % | -1.22 % | 1.67 | 4/6 | 1.1 % | 0.16 | -24 % | 21:-2.2(37) 22:+2.3(65) 23:-1.1(68) 24:+1.2(61) 25:+2.9(95) 26:+0.3(109) | no |
| T5 | R | top 20 % | 40 | 535 | -0.12 % | -4.66 % | 39 % | +0.47 % | -3.63 % | 0.55 | 3/6 | 3.1 % | 0.29 | -45 % | 21:+2.7(138) 22:-3.4(90) 23:-6.0(53) 24:+5.3(72) 25:+3.5(106) 26:-3.4(76) | no |
| T6 | E_mc +accruals | top 20 % | 40 | 357 | -0.17 % | -3.85 % | 41 % | +1.29 % | -1.88 % | 1.56 | 3/6 | 3.7 % | 0.40 | -22 % | 21:-0.8(77) 22:+6.6(47) 23:-2.3(45) 24:+3.8(61) 25:+1.8(61) 26:-0.4(66) | no |

Reference (not trials): every universe event, no signal: H20: n 2631, net -1.40 %, excess -0.72 %, t -0.94; H40: n 2536, net -1.52 %, excess -0.42 %, t -0.14; H60: n 2514, net -0.65 %, excess -0.04 %, t 0.17

E_mc quintiles at H = 40 (diagnostic, monotonicity): Q1: n 477, net -0.24 %, excess +0.34 %; Q2: n 490, net -4.92 %, excess -3.72 %; Q3: n 497, net +0.16 %, excess +1.60 %; Q4: n 536, net -1.14 %, excess -0.53 %; Q5: n 530, net -1.46 %, excess +0.22 %

## Battery on the best H = 40 arm (T4: E_sue)

| check | trades | net/trade | excess/trade | t | years exc>0 |
|---|---|---|---|---|---|
| top_decile | 218 | -2.17 % | +0.38 % | 0.25 | 3/6 |
| top_tercile | 717 | -1.00 % | +0.17 % | 1.37 | 4/6 |
| H20 | 456 | +0.58 % | +0.24 % | 1.71 | 3/6 |
| H60 | 429 | -0.68 % | +1.25 % | 1.52 | 5/6 |
| cost1.5 | 435 | -1.21 % | +0.45 % | 1.42 | 3/6 |
| delay1 | 432 | -1.72 % | -0.13 % | 1.06 | 3/6 |

Placebo (same names, 200 random entry dates): real mean excess +0.87 %, placebo median +1.38 %, 95th +3.22 %, real at percentile 32.

Next-open entry, 2025-26 events (opens stored): n 201, net/trade -1.22 % at the open vs -0.95 % at the close.

Standalone book of T4: CAGR 1.1 %, Sharpe 0.16, mDD -24 %, 2021: -1 % 2022: -1 % 2023: -6 % 2024: -4 % 2025: +39 % 2026: -14 %; DSR 0.00 at N = 883.

## Verdict: **CLOSED (PRELIM)**


## Reading (written after the run; the verdict above was fixed by the pre-registered rule)

1. **No arm clears bar (a).** The best month-clustered t is 1.67 (T4, SUE scaled by the name's own volatility of changes);
   every arm's MEDIAN excess is negative (-1.2 .. -3.6 %) and hit rates are 39-46 %. After the closing spread and fees, net
   per trade is negative at 40 and 60 days in all six arms. Excess is positive in 3-4 of 6 years in every arm: 2022, 2024
   and 2025 are up, 2021 and 2023 are down - a regime pattern, not a drift.
2. **The placebo is the decisive check.** The same names at 200 random entry dates beat their size-matched control by a
   median +1.38 % over 40 days - MORE than they do after a top-quintile surprise (+0.87 %, 32nd percentile). The small
   positive excess comes from WHICH names have parsed reports (larger, profitable, the value/quality pipeline's pool), not
   from WHEN the surprise happened. Rank by surprise adds nothing: E_mc quintiles at H = 40 are not monotone
   (Q1 +0.3 %, Q2 -3.7 %, Q3 +1.6 %, Q4 -0.5 %, Q5 +0.2 %).
3. **Not usable as a filter either.** A filter on the ML / trend entries can only help if the surprise ranks
   the next 1-3 months' returns, and it does not (point 2), so the conditional-trade test was not run (the pre-registration
   runs it, and the combo effect, only when a candidate exists). The FF-1 finding still stands: the market prices reported
   earnings by the time the workbook is public; on IDX the report adds no drift after a realistic entry.
4. **Execution detail.** Entry is the close of the first session after publication; for 2025-26, where opens are stored,
   the next-open entry is worse (-1.22 % vs -0.95 % net), so the missing open is not hiding a first-day drift.
5. **PRELIM means:** 2021-23 is 61-87 % parsed among tradeable names and the drain is still running. A re-run on the
   drained data could change the numbers; given a 32nd-percentile placebo and t < 1.7 everywhere, it would take a very
   different missing set to change the verdict. Re-run `python research/idx_fund_surprise.py` after the drain (change
   CUTOFF) as the confirmation, counted as a new trial set.

Trials: 10 (T1-T6, top decile, top tercile, H20 and H60 on T4), cumulative N = 883 (N_BEFORE 873). Study row #187.
