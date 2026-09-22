# IDX menu 28 — microstructure, preliminary (one session: 2026-09-22)

Question: does the order book / the tape at minute t predict the MID price h minutes later? Two bars: standalone (net of spread + fees) and
execution timing (sign only, for trades the desk makes anyway). Pre-registered in `research/idx_microstructure_prelim.py`; 7 trials (cumulative 510).

## Data

- 117 names, 36,695 name-minutes inside the continuous phases; 41,572 book-minutes, 33,859 bar-minutes
- median quoted spread 48.7 bps; median taker round-trip cost (spread + 30 bps fees) 78.7 bps
- 5-minute mid move: exactly zero in 60 % of minutes; mean |move| 0.46 ticks

## Information coefficients (Spearman per name, then mean and t across names; target = forward mid move in ticks)

| feature | h | all: mean IC / t / n | pooled IC | morning t | afternoon t | placebo pct |
|---|---|---|---|---|---|---|
| OBI1 | 1 | 0.218 / 34.6 / 109 | 0.199 | 28.9 | 21.3 | - |
| OBI1 | 5 | 0.229 / 21.0 / 110 | 0.203 | 15.7 | 13.7 | 100 |
| OBI1 | 15 | 0.197 / 12.7 / 115 | 0.162 | 8.4 | 9.6 | - |
| OBI5 | 1 | 0.130 / 19.4 / 109 | 0.073 | 17.6 | 14.2 | - |
| OBI5 | 5 | 0.184 / 14.6 / 110 | 0.098 | 13.5 | 9.1 | 100 |
| OBI5 | 15 | 0.211 / 10.8 / 115 | 0.103 | 9.4 | 6.0 | - |
| OBIT | 1 | 0.007 / 1.2 / 109 | 0.020 | -0.7 | -3.0 | - |
| OBIT | 5 | -0.021 / -1.6 / 110 | 0.030 | -3.4 | -5.2 | 100 |
| OBIT | 15 | -0.062 / -2.7 / 115 | 0.060 | -4.7 | -6.2 | - |
| TFI5 | 1 | -0.049 / -9.0 / 109 | -0.045 | -7.5 | -5.2 | - |
| TFI5 | 5 | -0.040 / -3.6 / 110 | -0.044 | -3.7 | -1.5 | 100 |
| TFI5 | 15 | -0.043 / -3.0 / 115 | -0.048 | -1.9 | -2.7 | - |
| RET5 | 1 | -0.085 / -10.3 / 106 | -0.064 | -7.9 | -8.9 | - |
| RET5 | 5 | -0.120 / -9.7 / 109 | -0.093 | -7.0 | -9.2 | 100 |
| RET5 | 15 | -0.084 / -6.9 / 110 | -0.029 | -4.9 | -9.8 | - |
| SPRD | 1 | 0.108 / 16.2 / 99 | 0.022 | 15.8 | 7.8 | - |
| SPRD | 5 | 0.237 / 19.3 / 99 | 0.041 | 21.3 | 12.0 | - |
| SPRD | 15 | 0.379 / 19.0 / 100 | 0.085 | 23.7 | 11.9 | - |

## Deciles (within-name percentile of the feature; D10 = top, D1 = bottom; forward mid move)

| feature | h | D10 ticks | D1 ticks | gap | D10 up-share | D1 down-share | D10 bps | D10 cost bps | D10 net bps |
|---|---|---|---|---|---|---|---|---|---|
| OBI1 | 5 | 0.18 | -0.33 | 0.51 | 0.31 | 0.39 | 10.8 | 91.0 | -80.2 |
| OBI1 | 15 | 0.02 | -0.58 | 0.59 | 0.31 | 0.50 | 7.7 | 90.9 | -83.2 |
| OBI5 | 5 | 0.10 | -0.36 | 0.46 | 0.26 | 0.39 | 7.2 | 91.7 | -84.4 |
| OBI5 | 15 | -0.05 | -0.78 | 0.73 | 0.29 | 0.56 | 2.5 | 91.5 | -89.0 |
| OBIT | 5 | -0.15 | -0.06 | -0.09 | 0.15 | 0.23 | -6.2 | 91.1 | -97.2 |
| OBIT | 15 | -0.50 | -0.13 | -0.37 | 0.16 | 0.33 | -22.0 | 91.1 | -113.1 |
| TFI5 | 5 | -0.20 | -0.05 | -0.15 | 0.12 | 0.20 | -7.8 | 90.9 | -98.7 |
| TFI5 | 15 | -0.44 | -0.23 | -0.21 | 0.17 | 0.31 | -19.0 | 90.9 | -110.0 |
| RET5 | 5 | -0.13 | 0.15 | -0.28 | 0.18 | 0.15 | -7.1 | 87.2 | -94.3 |
| RET5 | 15 | -0.34 | -0.01 | -0.33 | 0.22 | 0.28 | -15.5 | 87.3 | -102.8 |
| SPRD | 5 | 0.16 | -0.49 | 0.65 | 0.40 | 0.45 | 7.6 | 110.5 | -102.9 |
| SPRD | 15 | 0.32 | -1.32 | 1.64 | 0.49 | 0.71 | 16.8 | 110.0 | -93.2 |

## Trial 7 — LightGBM, sign of the 5-minute mid move, train morning -> test afternoon

- train 7,997 / test 4,706 minutes (zero moves dropped); base up-rate 0.466
- **AUC 0.715**; top-10 % predicted-up minutes: up-share 0.798, realised +43.9 bps vs cost 103.1 bps -> net -59.2 bps
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

## Caveats read after the run (not part of the bars)

- OBIT passes LEAD by the letter (both halves t <= -3.4/-5.2) but its whole-day per-name t is -1.6 and the pooled IC is +0.03: the sign
  flips between reads. Treated as NOT a lead; the bar should have required the whole-day read too (fixed in menu 28b).
- The session was a down day, so every "down-share" and D1 level is inflated by the day's drift; read the D10-D1 GAPS, not the levels.
- LightGBM puts 53 % of its gain on minute_of_day; on one day that is the day's drift curve, not a feature. Dropped in 28b.
- 60 % of 5-minute mid moves are exactly zero (tick-bound); the OBI1 signal is mostly "which side of the book empties first", i.e. the
  textbook queue-imbalance effect, ~0.5 tick over 5 minutes.
- Economic bottom line: the largest conditional move (OBI1 D10 vs D1, 0.5-0.6 tick ~ 10-20 bps) is a fraction of the taker cost (79 bps
  median) -> no standalone trade at 1-15 min. The same 0.5 tick is real money for trades the desk already makes (trend entries at the open,
  trail10 exits): buy when the bid queue dominates, wait when the offer queue dominates. Menu 28b measures that as a fill-improvement study.

