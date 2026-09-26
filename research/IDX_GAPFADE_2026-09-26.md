# IDX menu 29b — the gap-down fade, tested properly — 2020-01-01 -> 2026-09-21

IDX-sourced opens only: 111,441 eligible name-days. Pre-registered in `research/idx_gapfade.py`; 7 trials (cumulative 535).

## The path after a >= 5 % gap-down open (gross, equal weight, every eligible event)

| horizon | mean | median | P(up) | n |
|---|---|---|---|---|
| open->close | +2.91 % | +1.01 % | 55 % | 892 |
| open->next open | +2.66 % | +1.75 % | 59 % | 890 |
| open->close t+1 | +3.01 % | +2.15 % | 60 % | 892 |
| open->close t+5 | +2.94 % | +1.64 % | 55 % | 892 |

## Arms

| arm | trades | hit | mean | median | t | yrs + | 2020-24 | 2025-26 | fills +/-2t | w/o top 5 % | placebo mean | placebo pct | top-10 names' share | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| g5 | 516 | 49 % | **+182** | -7 | 3.0 | 6/7 | +146 (n 112) | +192 (n 404) | +81 | +41 | -138 ± 17 | 100 | 13 % | tested: t>=3 |
| g7 | 290 | 52 % | **+300** | +34 | 3.0 | 3/6 | +80 (n 23) | +319 (n 267) | +190 | +137 | -164 ± 24 | 100 | 21 % | tested: t>=3 |
| g10 | 187 | 56 % | **+507** | +141 | 3.5 | 3/6 | -88 (n 13) | +551 (n 174) | +392 | +332 | -166 ± 32 | 100 | 30 % | tested: early>0 |
| g5_no | 514 | 52 % | **+161** | +35 | 2.0 | 5/7 | +127 (n 111) | +170 (n 403) | +161 | +6 | -116 ± 22 | 100 | 11 % | tested: t>=3 |
| g5_c1 | 516 | 53 % | **+154** | +52 | 1.8 | 5/7 | +211 (n 112) | +138 (n 404) | +154 | -15 | -115 ± 23 | 100 | 0 % | tested: t>=3,wo_top5>0 |
| g5_idio | 417 | 49 % | **+205** | -12 | 2.8 | 5/7 | +87 (n 85) | +235 (n 332) | +102 | +54 | -136 ± 19 | 100 | 18 % | tested: t>=3 |
| g5_big | 372 | 50 % | **+149** | -1 | 1.8 | 5/7 | +122 (n 105) | +159 (n 267) | +62 | +33 | -125 ± 23 | 100 | 19 % | tested: t>=3 |

## Sleeve economics (capital fraction = trades / 10 each day; the rest idle)

| arm | avg capital deployed | total | CAGR | Sharpe | max DD | money rule |
|---|---|---|---|---|---|---|
| g5 | 22 % | +142 % | +15.9 % | 2.94 | -6 % | pass |
| g7 | 21 % | +129 % | +16.3 % | 3.86 | -4 % | pass |
| g10 | 21 % | +145 % | +18.1 % | 4.86 | -4 % | pass |
| g5_no | 22 % | +113 % | +13.4 % | 2.23 | -14 % | pass |
| g5_c1 | 22 % | +103 % | +12.5 % | 1.95 | -24 % | pass |
| g5_idio | 19 % | +124 % | +14.8 % | 2.90 | -6 % | pass |
| g5_big | 21 % | +67 % | +8.9 % | 2.32 | -5 % | pass |

## By year (mean net bps per trade)

- g5: 2020: +308, 2021: +377, 2022: +76, 2023: -138, 2024: +85, 2025: +235, 2026: +169
- g7: 2021: -262, 2022: -83, 2023: -137, 2024: +253, 2025: +340, 2026: +309
- g10: 2021: -262, 2022: -83, 2023: -196, 2024: +3, 2025: +538, 2026: +557
- g5_no: 2020: +246, 2021: +421, 2022: -27, 2023: -114, 2024: +144, 2025: +260, 2026: +121
- g5_c1: 2020: +629, 2021: +322, 2022: +75, 2023: -87, 2024: +135, 2025: +297, 2026: +53
- g5_idio: 2020: +41, 2021: +379, 2022: -2, 2023: -138, 2024: +85, 2025: +220, 2026: +244
- g5_big: 2020: +308, 2021: +377, 2022: +75, 2023: -96, 2024: -111, 2025: +150, 2026: +165

## Reading

- Verdicts: g5 tested: t>=3; g7 tested: t>=3; g10 tested: early>0; g5_no tested: t>=3; g5_c1 tested: t>=3,wo_top5>0; g5_idio tested: t>=3; g5_big tested: t>=3.
- CANDIDATE needs all seven checks; ROBUST needs the neighbours too; the money rule is read on the sleeve as it would be run.
- IDX opens are dense only from 2025, so 2020-24 is the thin subsample; the test repeats itself as opens accumulate (~600 a day).
