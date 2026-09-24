# IDX menu 32 PRELIM — when does an intraday run's buying power die? — train 2026-09-22 -> test 2026-09-23

118 names; runs (>= 3 ticks off the low, ended at −2 ticks from the high): train 264 (21,214 steps) / test 324 (44,598 steps). Label CONTINUE = +1 tick more before the −2-tick fall, within 15 min.
Pre-registered in `research/idx_run_exhaust.py`; 5 trials (cumulative 670). **One train day, one test day: a direction read.**

## Model — P(continue) from the book, the tape and the run's own shape

- per-name AUC median **0.604** (placebo 0.427, pct 100); pooled AUC 0.633
- per-name IC of P(continue) vs ticks still to come: median +0.195, positive in 71 % of 82 names
- base P(continue) on the test day 0.451; rounds 69; verdict **LEAD**
- importance (gain share): MKT_BREADTH 0.103, MKT_RET 0.074, conc_o 0.068, age 0.066, rvol15 0.061, sprd_bps 0.06, OBI5 0.055, hi_t 0.054, MKT_OFI5 0.051, vol_per_tick 0.047

| run age | P(continue) | n |
|---|---|---|
| <=3min | 0.543 | 5,388 |
| 3-10min | 0.453 | 8,092 |
| >10min | 0.434 | 31,118 |

| gain so far | P(continue) | n |
|---|---|---|
| 3-4t | 0.424 | 32,347 |
| 5-7t | 0.506 | 9,984 |
| >=8t | 0.598 | 2,264 |

| score decile | P(continue) | ticks still to come | n |
|---|---|---|---|
| 1 | 0.168 | +0.24 | 4,460 |
| 2 | 0.314 | +0.54 | 4,460 |
| 3 | 0.397 | +0.71 | 4,460 |
| 4 | 0.415 | +0.76 | 4,459 |
| 5 | 0.492 | +0.94 | 4,460 |
| 6 | 0.494 | +0.92 | 4,460 |
| 7 | 0.540 | +1.02 | 4,460 |
| 8 | 0.560 | +1.10 | 4,459 |
| 9 | 0.566 | +1.21 | 4,460 |
| 10 | 0.564 | +1.41 | 4,460 |

## Exit timing — we hold from the run start; sell at the bid

| policy | runs | ticks kept (mean) | median | ticks left vs the run high | vs base_trail | paired t | verdict |
|---|---|---|---|---|---|---|---|
| base_trail | 324 | +0.02 | -0.50 | 2.46 | +0.00 | - | comparator |
| base_5m | 324 | -0.17 | -0.50 | 2.66 | -0.19 | -1.94 | comparator |
| exit_p30 | 324 | -0.16 | -0.50 | 2.65 | -0.18 | -2.18 | no |
| exit_p50 | 324 | -0.30 | -0.50 | 2.79 | -0.32 | -2.65 | no |

## Entry — taker buy at the offer when P(continue) is high; sell at the bid when it drops below p30, at the run end, or after 15 min; fees 30 bps

| policy | trades | mean net bps | median | P(win) | ticks (bid out − offer in) | t | verdict |
|---|---|---|---|---|---|---|---|
| entry_p80 | 41 | -33.2 | -30.0 | 15 % | -0.17 | -3.30 | no |
| entry_p90 | 7 | -67.1 | -71.8 | 0 % | -1.71 | -5.92 | no |

## Log

- 118 names; runs train 275 (23,633 steps) / test 333 (48,250 steps) in 25 s
- model: per-name AUC 0.604 (placebo 0.427) IC share 0.71 (30 s)

## Reading

- Model lead by the bar (per-name AUC >= 0.58, IC > 0 in >= 70 % of names, placebo >= 95): yes.
- Policy candidates: none.
- The exit table is the monetisable read: a holder sells anyway, so a better sell point is pure gain (no second spread).
- Re-run when >= 20 sessions exist; then walk-forward by day and neutralise the day's market drift.
