# Phase 1 - how overfit is the choice of the combined book? - 2026-09-26

Audit, not a trial (nothing here can be deployed; the live book is frozen). Grid = every construction choice the desk made on
2022-26: ML confirm x stop x cash floor x gap/trend/ML size = 144 configurations on the #348 engine. Signal rules held fixed,
so every number is an UPPER bound on what the construction layer is worth.

Anchor: deployed `ens4|stop5|floor30|g10/t5/m10` = CAGR 50.6 %, Sharpe 2.21, mDD -17.1 % (#348 50.6 / 2.21 / -17.1) - reproduced. It ranks **34 of 144** by Sharpe.

Grid spread: CAGR 14.2 .. 85.9 %, Sharpe 1.19 .. 2.43.

## 1. Probability of backtest overfitting (CSCV, 16 blocks, 12,870 splits)

| PBO | median logit | IS Sharpe of the pick | its OOS Sharpe | IS->OOS slope | OOS Sharpe < 0 |
|---|---|---|---|---|---|
| **0.33** | +0.43 | 2.60 | 2.08 | -1.02 | 0 % |

## 2. Deflated Sharpe of the deployed configuration

| trials N | Sharpe | expected max Sharpe of N noise trials | DSR |
|---|---|---|---|
| 144 (this grid) | 2.21 | 0.79 | **1.00** |
| 1007 (desk ledger) | 2.21 | 0.96 | **1.00** |

These two rows are NOT reassuring: the 144 configurations are near-copies of one book (Sharpe sd across the grid ~0.2), so the
expected best of N is low. The desk's 1,007 trials were mostly OTHER families with a much wider Sharpe spread. Sensitivity with
a cross-trial Sharpe sd (annual); the ledger's MEASURED spread is 0.78 (6,406 arm Sharpes in 170 stored studies).
Trials are correlated, so the effective N is below 1,007:

| effective N | Sharpe sd | expected max Sharpe of N noise trials | DSR |
|---|---|---|---|
| 100 | 0.5 | 1.27 | **0.98** |
| 300 | 0.5 | 1.45 | **0.95** |
| 1007 | 0.5 | 1.63 | **0.90** |
| 100 | 0.78 | 1.97 | **0.70** |
| 300 | 0.78 | 2.26 | **0.46** |
| 1007 | 0.78 | 2.54 | **0.23** |
| 100 | 1.0 | 2.53 | **0.24** |
| 300 | 1.0 | 2.90 | **0.06** |
| 1007 | 1.0 | 3.26 | **0.01** |

## 3. Nested walk-forward of the selection process (2023-01-01 -> end, half-year folds)

| | CAGR | Sharpe | mDD |
|---|---|---|---|
| selection rule `max_sharpe` (out of sample) | 71.1 % | 2.44 | -17.4 % |
| selection rule `max_cagr_mdd25` (out of sample) | 102.7 % | 2.60 | -20.8 % |
| deployed configuration (chosen with hindsight) | 64.4 % | 2.55 | -17.1 % |
| median configuration of the grid | 54.5 % | 2.38 | -18.6 % |
| equal weight of all 144 (no choice at all) | 57.1 % | 2.54 | -17.4 % |

Without 2025 (same window): deployed 33.5 %/yr, median configuration 28.5 %/yr.

Picks, `max_sharpe`:

| fold | picked | OOS CAGR | OOS rank of 144 |
|---|---|---|---|
| 2023-01-01 | `ens4|stop5|floor30|g20/t5/m5` | +5.9 % | 73 |
| 2023-07-01 | `ens4|stop5|floor30|g10/t5/m10` | +40.2 % | 16 |
| 2024-01-01 | `single|stop10|floor30|g20/t5/m10` | +42.0 % | 78 |
| 2024-07-01 | `ens4|stop5|floor0|g20/t5/m10` | +8.1 % | 87 |
| 2025-01-01 | `single|stop10|floor30|g20/t5/m10` | +109.0 % | 27 |
| 2025-07-01 | `single|stop5|floor30|g20/t2.5/m10` | +407.2 % | 26 |
| 2026-01-01 | `ens4|stop5|floor0|g10/t5/m10` | +69.8 % | 54 |

Picks, `max_cagr_mdd25`:

| fold | picked | OOS CAGR | OOS rank of 144 |
|---|---|---|---|
| 2023-01-01 | `single|stop5|floor30|g20/t5/m10` | +10.5 % | 24 |
| 2023-07-01 | `single|stop5|floor30|g5/t5/m10` | +37.4 % | 29 |
| 2024-01-01 | `single|stop10|floor30|g20/t5/m10` | +42.0 % | 78 |
| 2024-07-01 | `single|stopnone|floor0|g10/t5/m10` | +16.1 % | 41 |
| 2025-01-01 | `single|stopnone|floor0|g10/t5/m10` | +117.9 % | 23 |
| 2025-07-01 | `single|stop5|floor0|g20/t5/m10` | +721.0 % | 2 |
| 2026-01-01 | `single|stop5|floor0|g20/t5/m10` | +161.0 % | 13 |

