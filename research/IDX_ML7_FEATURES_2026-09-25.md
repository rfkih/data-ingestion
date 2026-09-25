# IDX menu ML-7 — feature construction for the daily prediction desk (2026-09-25)

Trials 6 (cumulative 821); learner unchanged (LightGBM, BASE_PARAMS['ret']); labels = the desk's (excess vs COMPOSITE for 20d+); harness A = 3 x 40-day purged blocks; harness B = yearly walk-forward 2022..2026; LIQ = value60 >= Rp 5 bn & close >= 100. 

## Harness A (the registry's blocks): pooled IC | daily IC on LIQ | top-bottom decile spread

### 5d (champion 2026-09-24 pooled IC 0.232); blocks 2026-03-13..2026-05-20, 2026-05-21..2026-07-21, 2026-07-22..2026-09-17

| arm | pooled IC (mean, min) | per block | daily IC LIQ | spread bps |
|---|---|---|---|---|
| base | 0.182 (0.085) | 0.137 / 0.323 / 0.085 | 0.116 | 386 |
| xs | 0.179 (0.119) | 0.159 / 0.259 / 0.119 | 0.136 | 431 |
| wt | 0.159 (0.083) | 0.092 / 0.303 / 0.083 | 0.103 | 331 |
| ens3 | 0.193 (0.092) | 0.165 / 0.322 / 0.092 | 0.122 | 424 |
| all | 0.163 (0.060) | 0.060 / 0.293 / 0.136 | 0.120 | 347 |
| rank | 0.108 (0.088) | 0.126 / 0.088 / 0.109 | 0.135 | 327 |

Placebo (10 within-day shuffles, newest block, arm `ens3`): real 0.092, shuffles -0.005 ± 0.018, pct 100.

### 20d (champion 2026-09-24 pooled IC 0.142); blocks 2026-02-20..2026-04-24, 2026-04-27..2026-06-30, 2026-07-01..2026-08-27

| arm | pooled IC (mean, min) | per block | daily IC LIQ | spread bps |
|---|---|---|---|---|
| base | 0.121 (0.075) | 0.161 / 0.127 / 0.075 | 0.123 | 753 |
| xs | 0.100 (0.047) | 0.170 / 0.081 / 0.047 | 0.082 | 625 |
| wt | 0.093 (0.047) | 0.144 / 0.089 / 0.047 | 0.081 | 537 |
| ens3 | 0.121 (0.072) | 0.170 / 0.122 / 0.072 | 0.121 | 764 |
| all | 0.081 (0.037) | 0.134 / 0.071 / 0.037 | 0.071 | 585 |
| rank | 0.032 (0.008) | 0.051 / 0.008 / 0.038 | 0.090 | 405 |

Placebo (10 within-day shuffles, newest block, arm `ens3`): real 0.072, shuffles -0.003 ± 0.006, pct 100.

### 250d (champion 2026-09-24 pooled IC 0.215); blocks 2025-02-28..2025-05-07, 2025-05-08..2025-07-11, 2025-07-14..2025-09-09

| arm | pooled IC (mean, min) | per block | daily IC LIQ | spread bps |
|---|---|---|---|---|
| base | 0.206 (0.181) | 0.225 / 0.181 / 0.213 | 0.166 | 3681 |
| xs | 0.189 (0.168) | 0.202 / 0.168 / 0.197 | 0.137 | 3286 |
| wt | 0.209 (0.194) | 0.194 / 0.195 / 0.237 | 0.156 | 3025 |
| ens3 | 0.219 (0.195) | 0.240 / 0.195 / 0.221 | 0.164 | 3781 |
| all | 0.181 (0.161) | 0.182 / 0.161 / 0.201 | 0.119 | 3453 |
| rank | 0.172 (0.158) | 0.164 / 0.158 / 0.193 | 0.159 | 3380 |

## Harness B (yearly walk-forward): daily IC on LIQ (t) | spread bps | churn (day-to-day rank corr)

### 5d

| arm | 2022 | 2023 | 2024 | 2025 | 2026 | mean IC | years >= base |
|---|---|---|---|---|---|---|---|
| base | 0.096 (14.5) 393 c0.67 | 0.104 (14.2) 443 c0.71 | 0.076 (10.9) 259 c0.73 | 0.050 (6.3) 313 c0.74 | 0.098 (7.6) 477 c0.68 | 0.085 | 5/5 |
| all | 0.119 (19.9) 372 c0.67 | 0.098 (14.2) 417 c0.80 | 0.062 (8.8) 281 c0.73 | 0.058 (6.1) 172 c0.71 | 0.108 (9.1) 438 c0.64 | 0.089 | 3/5 |
| rank | 0.106 (18.3) 319 c0.48 | 0.126 (18.8) 423 c0.74 | 0.096 (14.2) 197 c0.55 | 0.101 (15.8) 262 c0.55 | 0.120 (14.3) 370 c0.55 | 0.110 | 5/5 |
| ema | 0.115 (18.5) 348 c0.90 | 0.095 (13.6) 411 c0.94 | 0.055 (7.6) 279 c0.92 | 0.044 (4.6) 143 c0.92 | 0.104 (8.5) 422 c0.89 | 0.082 | 2/5 |

### 20d

| arm | 2022 | 2023 | 2024 | 2025 | 2026 | mean IC | years >= base |
|---|---|---|---|---|---|---|---|
| base | 0.059 (9.9) 589 c0.90 | 0.128 (22.2) 1256 c0.92 | 0.074 (10.3) 903 c0.88 | 0.099 (15.7) 890 c0.86 | 0.073 (7.9) 523 c0.87 | 0.087 | 5/5 |
| all | 0.103 (17.7) 751 c0.93 | 0.125 (19.4) 1227 c0.95 | 0.092 (13.9) 946 c0.91 | 0.082 (10.3) 659 c0.89 | 0.044 (3.9) 512 c0.89 | 0.089 | 2/5 |
| rank | 0.085 (16.5) 708 c0.95 | 0.134 (20.3) 967 c0.98 | 0.083 (10.3) 374 c0.95 | 0.131 (22.1) 702 c0.93 | 0.017 (1.1) 16 c0.96 | 0.090 | 4/5 |
| ema | 0.101 (17.3) 726 c0.98 | 0.126 (19.5) 1248 c0.99 | 0.091 (14.0) 948 c0.97 | 0.081 (10.2) 669 c0.97 | 0.034 (2.9) 478 c0.97 | 0.087 | 2/5 |

### 250d

| arm | 2022 | 2023 | 2024 | 2025 | 2026 | mean IC | years >= base |
|---|---|---|---|---|---|---|---|
| base | 0.055 (17.4) 1126 c0.99 | 0.178 (56.1) 3247 c0.99 | 0.019 (5.4) 968 c0.98 | 0.149 (28.5) 3717 c0.97 | — | 0.100 | 4/4 |
| all | 0.012 (2.0) 1319 c0.98 | 0.149 (48.4) 3454 c0.99 | 0.033 (6.3) 567 c0.98 | 0.122 (33.9) 3563 c0.98 | — | 0.079 | 1/4 |
| rank | -0.171 (-27.7) -2482 c0.99 | 0.085 (19.9) 1989 c0.99 | 0.021 (3.4) 45 c0.99 | 0.166 (31.7) 4167 c0.98 | — | 0.025 | 2/4 |
| ema | 0.013 (2.1) 1311 c1.00 | 0.150 (48.4) 3445 c1.00 | 0.033 (6.2) 565 c0.99 | 0.122 (35.0) 3635 c0.99 | — | 0.080 | 1/4 |

## Verdict (pre-registered bar: pooled IC >= base + 0.02 on 5d AND 20d, >= 2/3 blocks, placebo >= 95, >= 4/5 years)

- `xs`: informative — 5d: gain -0.003, blocks_won 2, placebo_pct None, years_won 0, n_years 0, pass False; 20d: gain -0.0215, blocks_won 1, placebo_pct None, years_won 0, n_years 0, pass False
- `wt`: informative — 5d: gain -0.0228, blocks_won 0, placebo_pct None, years_won 0, n_years 0, pass False; 20d: gain -0.0278, blocks_won 0, placebo_pct None, years_won 0, n_years 0, pass False
- `ens3`: informative — 5d: gain 0.011, blocks_won 2, placebo_pct 100.0, years_won 0, n_years 0, pass False; 20d: gain -0.0001, blocks_won 1, placebo_pct 100.0, years_won 0, n_years 0, pass False
- `all`: informative — 5d: gain -0.0186, blocks_won 1, placebo_pct None, years_won 3, n_years 5, pass False; 20d: gain -0.0403, blocks_won 0, placebo_pct None, years_won 2, n_years 5, pass False
- `rank`: informative — 5d: gain -0.074, blocks_won 1, placebo_pct None, years_won 5, n_years 5, pass False; 20d: gain -0.0888, blocks_won 0, placebo_pct None, years_won 4, n_years 5, pass False
- `ema`: informative — 5d: years_won 2, n_years 5, pass False, note harness B only; 20d: years_won 2, n_years 5, pass False, note harness B only