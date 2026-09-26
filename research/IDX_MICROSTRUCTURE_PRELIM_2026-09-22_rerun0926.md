# IDX menu 28 — microstructure, preliminary (one session: 2026-09-22)

Question: does the order book / the tape at minute t predict the MID price h minutes later? Two bars: standalone (net of spread + fees) and
execution timing (sign only, for trades the desk makes anyway). Pre-registered in `research/idx_microstructure_prelim.py`; 7 trials (cumulative 510).

## Data

- 117 names, 36,695 name-minutes inside the continuous phases; 41,951 book-minutes, 35,310 bar-minutes
- median quoted spread 48.7 bps; median taker round-trip cost (spread + 30 bps fees) 78.7 bps
- 5-minute mid move: exactly zero in 60 % of minutes; mean |move| 0.47 ticks

## Information coefficients (Spearman per name, then mean and t across names; target = forward mid move in ticks)

| feature | h | all: mean IC / t / n | pooled IC | morning t | afternoon t | placebo pct |
|---|---|---|---|---|---|---|
| OBI1 | 1 | 0.220 / 35.5 / 111 | 0.202 | 28.9 | 22.4 | - |
| OBI1 | 5 | 0.231 / 21.0 / 112 | 0.204 | 15.7 | 14.2 | 100 |
| OBI1 | 15 | 0.197 / 12.7 / 115 | 0.162 | 8.4 | 10.1 | - |
| OBI5 | 1 | 0.129 / 19.2 / 111 | 0.073 | 17.6 | 14.5 | - |
| OBI5 | 5 | 0.180 / 14.2 / 112 | 0.098 | 13.5 | 8.9 | 100 |
| OBI5 | 15 | 0.211 / 10.8 / 115 | 0.103 | 9.4 | 6.0 | - |
| OBIT | 1 | 0.007 / 1.1 / 111 | 0.019 | -0.7 | -2.3 | - |
| OBIT | 5 | -0.023 / -1.8 / 112 | 0.029 | -3.4 | -5.3 | 100 |
| OBIT | 15 | -0.062 / -2.7 / 115 | 0.060 | -4.7 | -6.3 | - |
| TFI5 | 1 | -0.049 / -9.3 / 110 | -0.046 | -7.5 | -5.2 | - |
| TFI5 | 5 | -0.040 / -3.7 / 112 | -0.044 | -3.7 | -1.5 | 100 |
| TFI5 | 15 | -0.043 / -3.0 / 115 | -0.048 | -1.9 | -2.8 | - |
| RET5 | 1 | -0.087 / -10.7 / 106 | -0.066 | -7.9 | -9.8 | - |
| RET5 | 5 | -0.122 / -10.0 / 109 | -0.095 | -7.0 | -9.5 | 100 |
| RET5 | 15 | -0.084 / -6.9 / 110 | -0.029 | -4.9 | -9.8 | - |
| SPRD | 1 | 0.108 / 16.1 / 99 | 0.022 | 15.8 | 8.1 | - |
| SPRD | 5 | 0.235 / 19.1 / 99 | 0.042 | 21.3 | 12.4 | - |
| SPRD | 15 | 0.378 / 19.0 / 100 | 0.086 | 23.7 | 11.9 | - |

## Deciles (within-name percentile of the feature; D10 = top, D1 = bottom; forward mid move)

| feature | h | D10 ticks | D1 ticks | gap | D10 up-share | D1 down-share | D10 bps | D10 cost bps | D10 net bps |
|---|---|---|---|---|---|---|---|---|---|
| OBI1 | 5 | 0.18 | -0.33 | 0.51 | 0.31 | 0.40 | 10.7 | 91.0 | -80.2 |
| OBI1 | 15 | 0.02 | -0.58 | 0.60 | 0.31 | 0.50 | 7.8 | 90.9 | -83.0 |
| OBI5 | 5 | 0.10 | -0.36 | 0.46 | 0.26 | 0.39 | 7.2 | 91.7 | -84.5 |
| OBI5 | 15 | -0.04 | -0.78 | 0.73 | 0.29 | 0.56 | 2.7 | 91.5 | -88.8 |
| OBIT | 5 | -0.16 | -0.06 | -0.09 | 0.15 | 0.23 | -6.2 | 91.1 | -97.3 |
| OBIT | 15 | -0.50 | -0.13 | -0.37 | 0.16 | 0.33 | -21.9 | 91.1 | -113.1 |
| TFI5 | 5 | -0.20 | -0.05 | -0.15 | 0.12 | 0.21 | -7.8 | 90.9 | -98.7 |
| TFI5 | 15 | -0.43 | -0.23 | -0.20 | 0.17 | 0.31 | -18.9 | 90.9 | -109.8 |
| RET5 | 5 | -0.13 | 0.15 | -0.29 | 0.18 | 0.15 | -7.3 | 87.2 | -94.5 |
| RET5 | 15 | -0.34 | -0.00 | -0.34 | 0.22 | 0.28 | -15.6 | 87.3 | -102.8 |
| SPRD | 5 | 0.16 | -0.49 | 0.65 | 0.39 | 0.45 | 7.5 | 110.5 | -102.9 |
| SPRD | 15 | 0.33 | -1.31 | 1.64 | 0.49 | 0.71 | 16.9 | 110.0 | -93.1 |

## Trial 7 — LightGBM, sign of the 5-minute mid move, train morning -> test afternoon

- train 7,997 / test 4,730 minutes (zero moves dropped); base up-rate 0.464
- **AUC 0.717**; top-10 % predicted-up minutes: up-share 0.799, realised +43.8 bps vs cost 103.0 bps -> net -59.2 bps
- importance: {'OBI1': 0.17, 'OBI5': 0.052, 'OBIT': 0.054, 'TFI5': 0.044, 'RET5': 0.092, 'SPRD': 0.06, 'minute_of_day': 0.528}

## Verdicts (pre-registered bars)

| trial | LEAD (both halves |t|>=3, placebo>=99) | TRADEABLE (D10 net > 0) | EXEC-TIMING (gap >= 0.25 tick, same sign) |
|---|---|---|---|
| OBI1 | YES | no | YES |
| OBI5 | YES | no | YES |
| OBIT | YES | no | no |
| TFI5 | no | no | no |
| RET5 | YES | no | YES |
| LGBM | informative: YES | no | - |

## Reading

- One session. Nothing here is adoptable; a LEAD here only earns menu 28b (the same reads over >= 20 sessions, halves replaced by a day split).
- TRADEABLE compares the mean forward move of the top decile with the taker's own cost at those minutes; a positive net would mean a
  standalone microstructure trade pays after the spread and fees. A negative net with a strong IC = information that is real but priced
  inside the spread — usable only for timing trades the desk makes anyway (EXEC-TIMING).
- The mid is used throughout so bid-ask bounce cannot manufacture reversal.
