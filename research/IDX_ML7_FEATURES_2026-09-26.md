# IDX menu ML-7 — feature construction for the daily prediction desk (2026-09-26)

Trials 6 (cumulative 821); learner unchanged (LightGBM, BASE_PARAMS['ret']); labels = the desk's (excess vs COMPOSITE for 20d+); harness A = 3 x 40-day purged blocks; harness B = yearly walk-forward 2022..2026; LIQ = value60 >= Rp 5 bn & close >= 100. 

## Harness A (the registry's blocks): pooled IC | daily IC on LIQ | top-bottom decile spread

### 5d (champion 2026-09-24 pooled IC 0.232); blocks 2026-03-16..2026-05-21, 2026-05-22..2026-07-22, 2026-07-23..2026-09-18

| arm | pooled IC (mean, min) | per block | daily IC LIQ | spread bps |
|---|---|---|---|---|
| base | 0.184 (0.102) | 0.163 / 0.286 / 0.102 | 0.115 | 363 |
| xs | 0.148 (0.029) | 0.154 / 0.261 / 0.029 | 0.145 | 442 |
| wt | 0.160 (0.076) | 0.076 / 0.284 / 0.120 | 0.094 | 316 |
| ens3 | 0.181 (0.125) | 0.150 / 0.270 / 0.125 | 0.129 | 382 |
| all | 0.164 (0.063) | 0.063 / 0.296 / 0.132 | 0.121 | 346 |
| rank | 0.109 (0.096) | 0.123 / 0.109 / 0.096 | 0.131 | 304 |

Placebo (10 within-day shuffles, newest block, arm `ens3`): real 0.125, shuffles 0.039 ± 0.027, pct 100.

### 20d (champion 2026-09-24 pooled IC 0.142); blocks 2026-02-23..2026-04-27, 2026-04-28..2026-07-01, 2026-07-02..2026-08-28

| arm | pooled IC (mean, min) | per block | daily IC LIQ | spread bps |
|---|---|---|---|---|
| base | 0.139 (0.088) | 0.159 / 0.170 / 0.088 | 0.118 | 802 |
| xs | 0.119 (0.056) | 0.182 / 0.118 / 0.056 | 0.093 | 748 |
| wt | 0.104 (0.054) | 0.137 / 0.121 / 0.054 | 0.087 | 524 |
| ens3 | 0.139 (0.081) | 0.173 / 0.162 / 0.081 | 0.119 | 830 |
| all | 0.099 (0.047) | 0.159 / 0.090 / 0.047 | 0.072 | 506 |
| rank | 0.054 (0.025) | 0.105 / 0.032 / 0.025 | 0.071 | 215 |

Placebo (10 within-day shuffles, newest block, arm `ens3`): real 0.081, shuffles -0.026 ± 0.005, pct 100.

### 250d (champion 2026-09-24 pooled IC 0.215); blocks 2025-03-03..2025-05-08, 2025-05-09..2025-07-14, 2025-07-15..2025-09-10

| arm | pooled IC (mean, min) | per block | daily IC LIQ | spread bps |
|---|---|---|---|---|
| base | 0.195 (0.170) | 0.170 / 0.196 / 0.220 | 0.189 | 3398 |
| xs | 0.174 (0.152) | 0.152 / 0.161 / 0.208 | 0.166 | 2850 |
| wt | 0.175 (0.165) | 0.173 / 0.165 / 0.186 | 0.156 | 2614 |
| ens3 | 0.200 (0.186) | 0.188 / 0.186 / 0.227 | 0.190 | 3264 |
| all | 0.167 (0.130) | 0.147 / 0.130 / 0.224 | 0.165 | 3079 |
| rank | 0.158 (0.131) | 0.131 / 0.147 / 0.196 | 0.155 | 2533 |

## Harness B (yearly walk-forward): daily IC on LIQ (t) | spread bps | churn (day-to-day rank corr)

### 5d

| arm | 2022 | 2023 | 2024 | 2025 | 2026 | mean IC | years >= base |
|---|---|---|---|---|---|---|---|
| base | 0.111 (18.4) 376 c0.66 | 0.100 (14.1) 463 c0.70 | 0.065 (8.5) 245 c0.77 | 0.051 (6.4) 259 c0.73 | 0.115 (10.9) 456 c0.63 | 0.088 | 5/5 |
| all | 0.112 (18.0) 337 c0.68 | 0.106 (14.8) 447 c0.79 | 0.065 (9.3) 270 c0.70 | 0.063 (7.1) 237 c0.68 | 0.079 (6.3) 400 c0.64 | 0.085 | 3/5 |
| rank | 0.121 (21.9) 355 c0.45 | 0.127 (19.4) 419 c0.72 | 0.095 (14.3) 221 c0.56 | 0.109 (16.5) 279 c0.54 | 0.122 (14.7) 359 c0.53 | 0.115 | 5/5 |
| ema | 0.109 (17.2) 303 c0.90 | 0.104 (14.2) 434 c0.94 | 0.056 (7.9) 256 c0.91 | 0.050 (5.7) 175 c0.91 | 0.076 (5.6) 352 c0.89 | 0.079 | 1/5 |

### 20d

| arm | 2022 | 2023 | 2024 | 2025 | 2026 | mean IC | years >= base |
|---|---|---|---|---|---|---|---|
| base | 0.109 (18.1) 664 c0.89 | 0.126 (21.1) 1121 c0.92 | 0.106 (16.0) 961 c0.89 | 0.083 (10.4) 834 c0.85 | 0.100 (11.5) 533 c0.86 | 0.105 | 5/5 |
| all | 0.108 (17.6) 852 c0.93 | 0.131 (20.5) 1183 c0.95 | 0.105 (16.2) 1078 c0.91 | 0.054 (6.4) 541 c0.90 | 0.085 (9.3) 638 c0.88 | 0.096 | 1/5 |
| rank | 0.082 (15.2) 873 c0.95 | 0.139 (19.0) 1094 c0.98 | 0.081 (9.7) 489 c0.96 | 0.116 (17.9) 765 c0.94 | -0.002 (-0.1) -151 c0.96 | 0.083 | 2/5 |
| ema | 0.106 (17.2) 879 c0.98 | 0.132 (20.7) 1185 c0.99 | 0.104 (16.0) 1060 c0.97 | 0.051 (6.0) 487 c0.97 | 0.079 (8.7) 602 c0.97 | 0.095 | 1/5 |

### 250d

| arm | 2022 | 2023 | 2024 | 2025 | 2026 | mean IC | years >= base |
|---|---|---|---|---|---|---|---|
| base | 0.082 (30.3) 1247 c0.99 | 0.215 (62.3) 3602 c0.99 | 0.014 (3.7) 1369 c0.99 | 0.169 (37.3) 3702 c0.98 | — | 0.120 | 4/4 |
| all | 0.088 (15.0) 2291 c0.98 | 0.168 (49.9) 3700 c0.98 | 0.050 (10.2) 1101 c0.98 | 0.153 (37.7) 2830 c0.98 | — | 0.115 | 2/4 |
| rank | -0.089 (-12.4) -1858 c0.99 | 0.112 (22.7) 3240 c0.99 | 0.049 (8.5) 1350 c0.99 | 0.135 (24.9) 3113 c0.99 | — | 0.052 | 1/4 |
| ema | 0.090 (15.4) 2305 c0.99 | 0.168 (49.9) 3746 c1.00 | 0.051 (10.3) 1058 c0.99 | 0.152 (37.0) 2797 c0.99 | — | 0.115 | 2/4 |

## Verdict (pre-registered bar: pooled IC >= base + 0.02 on 5d AND 20d, >= 2/3 blocks, placebo >= 95, >= 4/5 years)

- `xs`: informative — 5d: gain -0.0356, blocks_won 0, placebo_pct None, years_won 0, n_years 0, pass False; 20d: gain -0.0202, blocks_won 1, placebo_pct None, years_won 0, n_years 0, pass False
- `wt`: informative — 5d: gain -0.0234, blocks_won 1, placebo_pct None, years_won 0, n_years 0, pass False; 20d: gain -0.0348, blocks_won 0, placebo_pct None, years_won 0, n_years 0, pass False
- `ens3`: informative — 5d: gain -0.0023, blocks_won 1, placebo_pct 100.0, years_won 0, n_years 0, pass False; 20d: gain -0.0002, blocks_won 1, placebo_pct 100.0, years_won 0, n_years 0, pass False
- `all`: informative — 5d: gain -0.0198, blocks_won 2, placebo_pct None, years_won 3, n_years 5, pass False; 20d: gain -0.0402, blocks_won 1, placebo_pct None, years_won 1, n_years 5, pass False
- `rank`: informative — 5d: gain -0.0745, blocks_won 0, placebo_pct None, years_won 5, n_years 5, pass False; 20d: gain -0.085, blocks_won 0, placebo_pct None, years_won 2, n_years 5, pass False
- `ema`: informative — 5d: years_won 1, n_years 5, pass False, note harness B only; 20d: years_won 1, n_years 5, pass False, note harness B only