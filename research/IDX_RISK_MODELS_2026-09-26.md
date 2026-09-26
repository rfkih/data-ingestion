# Risk models beyond replay - 2026-09-26

Audit, no trial. Book = the deployed combined configuration (#348 NAVs and trade list).

## (a) Regimes: 2-state HMM on COMPOSITE daily returns 2020-01 -> 2026-09 (filtered, no look-ahead)

Calm state: +16 %/yr, vol 12 %. High-vol state: -72 %/yr, vol 36 %. Persistence: calm 0.989, high 0.941 (a high-vol spell lasts ~17 sessions). High-vol share: 2020-26 14 %, backtest window 13 %.

| series | regime (previous close) | days | mean /yr | vol /yr | Sharpe | 1-day VaR 99 % |
|---|---|---|---|---|---|---|
| combined | calm | 980 | +41.8 % | 18.8 % | 2.23 | 2.57 % |
| combined | high_vol | 143 | +69.5 % | 30.0 % | 2.32 | 3.92 % |
| gap_only | calm | 980 | +5.9 % | 6.0 % | 0.99 | 0.68 % |
| gap_only | high_vol | 143 | +63.0 % | 21.3 % | 2.95 | 1.60 % |
| trend_only | calm | 980 | +16.8 % | 11.4 % | 1.47 | 1.80 % |
| trend_only | high_vol | 143 | -11.3 % | 7.9 % | -1.43 | 2.61 % |
| ml_only | calm | 980 | +28.5 % | 15.1 % | 1.89 | 1.99 % |
| ml_only | high_vol | 143 | +29.6 % | 19.7 % | 1.51 | 2.97 % |
| COMPOSITE | calm | 980 | +3.0 % | 13.7 % | 0.22 | 2.35 % |
| COMPOSITE | high_vol | 143 | -15.5 % | 31.9 % | -0.49 | 4.75 % |

## (b) Lower-tail dependence (days both series moved)

| pair | n | Spearman | lambda 5 % | Gaussian 5 % | lambda 10 % | Gaussian 10 % |
|---|---|---|---|---|---|---|
| gap_only~trend_only | 90 | +0.20 | 0.22 | 0.11 | 0.33 | 0.17 |
| gap_only~ml_only | 130 | +0.33 | 0.31 | 0.16 | 0.31 | 0.24 |
| trend_only~ml_only | 874 | +0.24 | 0.25 | 0.12 | 0.25 | 0.20 |
| combined~COMPOSITE | 1121 | +0.35 | 0.36 | 0.17 | 0.35 | 0.25 |
| combined~IDXSMC-LIQ | 1120 | +0.41 | 0.34 | 0.20 | 0.39 | 0.28 |
| trend_only~IDXSMC-LIQ | 966 | +0.38 | 0.33 | 0.18 | 0.33 | 0.26 |
| ml_only~IDXSMC-LIQ | 1027 | +0.35 | 0.31 | 0.17 | 0.32 | 0.25 |
| gap_only~COMPOSITE | 135 | +0.29 | 0.30 | 0.14 | 0.30 | 0.22 |

Independence would give lambda = q (0.05 / 0.10). Empirical well above the Gaussian column = crashes arrive together
more often than the correlation implies.

## (c) Designed two-factor scenarios on the deployed overnight holdings (loss % of that day's NAV)

Betas 2022-26 (median over held names): COMPOSITE 1.09, small-cap spread 0.48.

| scenario | F COMPOSITE | F small-cap spread | median day | 95th pct day | worst | worst date |
|---|---|---|---|---|---|---|
| S1_foreign_exodus | -15 % | -10 % | -10.2 % | -17.3 % | -21.7 % | 2026-07-23 |
| S2_smallcap_unwind | -5 % | -25 % | -8.7 % | -15.7 % | -19.6 % | 2025-07-21 |
| S3_2020x1.25 | -47 % | -10 % | -25.9 % | -45.2 % | -54.5 % | 2025-10-08 |

Limits: #348 NAVs predate the 2026-09-26 look-ahead fix of the gap-fade eligibility (the gap sleeve is intraday and
flat overnight, so (c) is unaffected; (a)/(b) gap rows slightly flatter the sleeve); one HMM on six years with one crash;
linear betas understate a crash's convexity; no exits during a scenario.
