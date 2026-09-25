# IDX menu ML-3b — ARA besok dari bar + microstructure penutupan, LightGBM vs GRU — 2026-09-24 — 6 trials, cumulative N = 717

409,722 name-days (880 names) on the main boards, previous >= Rp 50, value >= Rp 1 bn, 2020-01 -> 2026-09-24; walk-forward by test year. Base rate LOCK1 (closes at ARA tomorrow) 0.55 %, TOUCH1 (touches it) 0.84 %. Pre-registered in `research/idx_ara_micro.py`.

## Accuracy of the ranked list, per test year (label LOCK1)

| model | year | rows | base | AUC | AP | precision@5 | precision@10 | precision@20 | recall@20 | lift@5 | buyable share of top-10 | precision@10 among buyable | next-day ret top-10 | ret buyable top-10 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BAR | 2022 | 71,283 | 0.33 % | 0.874 | 0.150 | **7.5 %** | **4.7 %** | 2.7 % | 56 % | 22.7x | 86 % | 1.7 % | 1.13 % | 0.13 % |
| BAR | 2023 | 63,310 | 0.29 % | 0.886 | 0.167 | **7.1 %** | **4.4 %** | 2.5 % | 65 % | 24.2x | 86 % | 1.7 % | 0.62 % | -0.13 % |
| BAR | 2024 | 58,901 | 0.30 % | 0.904 | 0.210 | **8.0 %** | **4.4 %** | 2.6 % | 69 % | 26.8x | 84 % | 1.4 % | 0.21 % | -0.64 % |
| BAR | 2025 | 70,490 | 0.89 % | 0.886 | 0.193 | **17.0 %** | **11.8 %** | 7.0 % | 53 % | 19.2x | 61 % | 3.1 % | 1.69 % | -0.67 % |
| BAR | 2026 | 57,675 | 0.71 % | 0.869 | 0.101 | **12.3 %** | **8.4 %** | 5.4 % | 45 % | 17.2x | 66 % | 3.0 % | 0.59 % | -1.01 % |
| MICRO | 2022 | 71,283 | 0.33 % | 0.849 | 0.109 | **7.2 %** | **4.1 %** | 2.6 % | 54 % | 21.7x | 81 % | 1.0 % | 1.35 % | 0.23 % |
| MICRO | 2023 | 63,310 | 0.29 % | 0.837 | 0.103 | **6.4 %** | **3.6 %** | 2.0 % | 52 % | 21.6x | 85 % | 0.8 % | 0.85 % | 0.09 % |
| MICRO | 2024 | 58,901 | 0.30 % | 0.888 | 0.167 | **7.6 %** | **4.3 %** | 2.6 % | 69 % | 25.4x | 84 % | 1.3 % | 0.57 % | -0.20 % |
| MICRO | 2025 | 70,490 | 0.89 % | 0.857 | 0.186 | **18.1 %** | **11.6 %** | 7.0 % | 53 % | 20.5x | 59 % | 2.4 % | 2.04 % | -0.15 % |
| MICRO | 2026 | 57,675 | 0.71 % | 0.794 | 0.090 | **11.8 %** | **7.1 %** | 4.6 % | 39 % | 16.6x | 65 % | 1.2 % | 1.10 % | -0.26 % |
| BAR+MICRO | 2022 | 71,283 | 0.33 % | 0.882 | 0.171 | **7.9 %** | **4.8 %** | 2.7 % | 57 % | 23.9x | 84 % | 1.8 % | 1.63 % | 0.66 % |
| BAR+MICRO | 2023 | 63,310 | 0.29 % | 0.886 | 0.161 | **7.1 %** | **4.3 %** | 2.6 % | 67 % | 24.2x | 86 % | 1.6 % | 1.11 % | 0.44 % |
| BAR+MICRO | 2024 | 58,901 | 0.30 % | 0.919 | 0.203 | **7.9 %** | **4.6 %** | 2.7 % | 74 % | 26.5x | 84 % | 1.6 % | 0.89 % | 0.19 % |
| BAR+MICRO | 2025 | 70,490 | 0.89 % | 0.879 | 0.205 | **17.6 %** | **11.9 %** | 7.2 % | 54 % | 19.9x | 60 % | 3.2 % | 2.15 % | 0.10 % |
| BAR+MICRO | 2026 | 57,675 | 0.71 % | 0.871 | 0.117 | **12.4 %** | **8.2 %** | 5.4 % | 45 % | 17.4x | 66 % | 2.8 % | 0.85 % | -0.65 % |
| DL | 2022 | 71,283 | 0.33 % | 0.900 | 0.093 | **7.9 %** | **4.8 %** | 3.0 % | 64 % | 23.9x | 82 % | 1.9 % | 1.19 % | 0.06 % |
| DL | 2023 | 63,310 | 0.29 % | 0.913 | 0.167 | **7.5 %** | **4.5 %** | 2.7 % | 70 % | 25.6x | 85 % | 1.8 % | 0.52 % | -0.31 % |
| DL | 2024 | 58,901 | 0.30 % | 0.930 | 0.127 | **8.4 %** | **4.8 %** | 2.9 % | 77 % | 28.0x | 84 % | 1.8 % | 0.13 % | -0.73 % |
| DL | 2025 | 70,490 | 0.89 % | 0.898 | 0.232 | **20.2 %** | **12.8 %** | 7.6 % | 57 % | 22.8x | 59 % | 4.4 % | 2.09 % | -0.13 % |
| DL | 2026 | 57,675 | 0.71 % | 0.881 | 0.119 | **13.1 %** | **8.9 %** | 5.9 % | 49 % | 18.4x | 65 % | 3.7 % | 1.09 % | -0.36 % |
| ENS | 2022 | 71,283 | 0.33 % | 0.898 | 0.125 | **8.0 %** | **4.8 %** | 2.9 % | 62 % | 24.2x | 83 % | 2.0 % | 1.53 % | 0.50 % |
| ENS | 2023 | 63,310 | 0.29 % | 0.906 | 0.141 | **7.6 %** | **4.6 %** | 2.7 % | 70 % | 25.9x | 85 % | 1.9 % | 0.79 % | 0.04 % |
| ENS | 2024 | 58,901 | 0.30 % | 0.933 | 0.125 | **8.4 %** | **4.9 %** | 2.8 % | 76 % | 28.2x | 84 % | 2.0 % | 0.38 % | -0.43 % |
| ENS | 2025 | 70,490 | 0.89 % | 0.890 | 0.165 | **19.6 %** | **12.4 %** | 7.5 % | 57 % | 22.1x | 59 % | 3.7 % | 2.13 % | -0.02 % |
| ENS | 2026 | 57,675 | 0.71 % | 0.877 | 0.107 | **13.3 %** | **8.8 %** | 5.7 % | 48 % | 18.7x | 65 % | 3.6 % | 0.85 % | -0.69 % |

Reading: precision@K = of the K names the model ranks highest each day, the share that closes at ARA the next day (mean over days). recall@20 = the share of the year's ARA locks that were inside the daily top-20. lift = precision@5 / base rate. 'Buyable' = the pick still had an offer at today's close (not locked today).

## Does the closing-book microstructure add to the bars? (BAR+MICRO minus BAR)

| year | ΔAUC | Δprecision@10 | Δrecall@20 | Δbuyable precision@10 | MICRO alone AUC | MICRO alone precision@10 |
|---|---|---|---|---|---|---|
| 2022 | +0.007 | +0.1 pp | +0.9 pp | +0.1 pp | 0.849 | 4.1 % |
| 2023 | -0.000 | -0.0 pp | +2.7 pp | -0.0 pp | 0.837 | 3.6 % |
| 2024 | +0.014 | +0.2 pp | +5.1 pp | +0.2 pp | 0.888 | 4.3 % |
| 2025 | -0.006 | +0.2 pp | +1.0 pp | +0.1 pp | 0.857 | 11.6 % |
| 2026 | +0.002 | -0.1 pp | +0.0 pp | -0.2 pp | 0.794 | 7.1 % |

**Rule (>= +0.01 AUC and >= +1 pp precision@10 in >= 4/5 years): 0/5 years -> micro does NOT add.**
**DL (GRU) within 0.005 AUC of the tree in 5/5 years -> USEFUL; ENS beats the tree on precision@10 in 5/5 -> ADOPTED.**
**Rank model: ENS.**

Secondary label TOUCH1 (touches ARA tomorrow, BAR+MICRO): 2022: AUC 0.898, p@5 11.8 %, p@10 7.2 %; 2023: AUC 0.914, p@5 11.8 %, p@10 7.2 %; 2024: AUC 0.935, p@5 12.6 %, p@10 7.6 %; 2025: AUC 0.886, p@5 28.0 %, p@10 17.1 %; 2026: AUC 0.877, p@5 21.9 %, p@10 14.0 %.

## 'Akurasi' at one operating point — flag the top 1 % of scores (threshold fixed on the training years)

| model | year | flagged | TP | FP | FN | precision | recall | F1 | balanced acc | plain accuracy | always-'no' accuracy |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BAR+MICRO | 2022 | 197 | 62 | 135 | 173 | **31.5 %** | **26.4 %** | 0.287 | 63.1 % | 99.57 % | 99.67 % |
| BAR+MICRO | 2023 | 253 | 55 | 198 | 131 | **21.7 %** | **29.6 %** | 0.251 | 64.6 % | 99.48 % | 99.71 % |
| BAR+MICRO | 2024 | 510 | 79 | 431 | 97 | **15.5 %** | **44.9 %** | 0.230 | 72.1 % | 99.10 % | 99.70 % |
| BAR+MICRO | 2025 | 931 | 227 | 704 | 397 | **24.4 %** | **36.4 %** | 0.292 | 67.7 % | 98.44 % | 99.11 % |
| BAR+MICRO | 2026 | 563 | 112 | 451 | 299 | **19.9 %** | **27.3 %** | 0.230 | 63.2 % | 98.70 % | 99.29 % |
| DL | 2022 | 260 | 48 | 212 | 187 | **18.5 %** | **20.4 %** | 0.194 | 60.1 % | 99.44 % | 99.67 % |
| DL | 2023 | 361 | 71 | 290 | 115 | **19.7 %** | **38.2 %** | 0.260 | 68.9 % | 99.36 % | 99.71 % |
| DL | 2024 | 463 | 84 | 379 | 92 | **18.1 %** | **47.7 %** | 0.263 | 73.5 % | 99.20 % | 99.70 % |
| DL | 2025 | 1,161 | 256 | 905 | 368 | **22.0 %** | **41.0 %** | 0.287 | 69.9 % | 98.19 % | 99.11 % |
| DL | 2026 | 751 | 120 | 631 | 291 | **16.0 %** | **29.2 %** | 0.207 | 64.0 % | 98.40 % | 99.29 % |

Plain accuracy is not the number to quote: saying 'no ARA' for every name is already right 99.4-99.7 % of the time. Precision (how often a flagged name locks) and recall (how many of the locks were flagged) are the accuracy of this model.

## Calibration by score decile, 2026 (BAR+MICRO)

| decile | raw model P | calibrated P | observed P(LOCK1) | next-day return | n |
|---|---|---|---|---|---|
| 1 | 0.08 % | 0.02 % | 0.00 % | -0.13 % | 5,768 |
| 2 | 0.24 % | 0.04 % | 0.00 % | -0.17 % | 5,767 |
| 3 | 0.55 % | 0.07 % | 0.07 % | -0.13 % | 5,768 |
| 4 | 1.19 % | 0.12 % | 0.09 % | -0.11 % | 5,767 |
| 5 | 2.50 % | 0.19 % | 0.16 % | -0.10 % | 5,768 |
| 6 | 5.65 % | 0.32 % | 0.36 % | -0.13 % | 5,767 |
| 7 | 13.06 % | 0.58 % | 0.42 % | -0.23 % | 5,767 |
| 8 | 26.03 % | 1.00 % | 0.66 % | -0.26 % | 5,768 |
| 9 | 44.25 % | 1.69 % | 1.09 % | -0.24 % | 5,767 |
| 10 | 73.01 % | 4.98 % | 4.28 % | 0.28 % | 5,768 |

The raw score is inflated by scale_pos_weight (decile 10 says 73 %, reality 4.3 %); every probability printed below is Platt-recalibrated on the pooled out-of-fold scores (tree a=0.64 b=-3.92, GRU a=0.92 b=-3.72). Ranks, AUC and precision@K do not change under a monotone map.

## What the model looks at (gain share, final fit) and the placebo

- BAR+MICRO: vol20 50.1 %, hl_range 14.2 %, near 8.0 %, days_since_ara 5.6 %, ret5 2.2 %, vr5 1.7 %, ret60 1.3 %, ret1 1.0 %, vr 0.9 %, log_value 0.9 %, dist_hi60 0.9 %, log_price 0.7 %
- MICRO alone: qimb 41.0 %, turnover 19.7 %, fpart 8.8 %, atr_ratio 6.7 %, log_avg_trade 6.1 %, freq_ratio 3.0 %, gap_open 2.3 %, log_ov_vol 2.1 %, qimb_yday 2.0 %, fnet5 1.8 %, qimb5 1.2 %, fnet 1.2 %
- placebo (LOCK1 shuffled in the training set, 3 draws): AUC 0.382, 0.366, 0.330 vs real 0.871 -> percentile 100.
- GRU 2026 fold: best validation AUC 0.888 after 6 epochs; final fit val AUC 0.884.

## Tick-level microstructure (Stockbit feed) — why it is not in the model yet

The feed holds 4 sessions, 513 name-days over ~136 liquid names, and **0 ARA touches**. A classifier cannot be trained on zero positives; ARA is a small-cap event and the feed covers the liquid tail. Pre-registered for when the feed reaches >= 20 sessions and >= 30 touches: intraday re-rank of the nightly list at 09:15 / 10:00 from OBI1/5, OFI 5-min, TFI, spread, distance to ARA in ticks, market OFI (the menu-31 feature set), label = touches ARA later that day; bar = AUC >= 0.70 and precision@5 >= 2x the nightly list's.

## Ranked list for the session after 2026-09-24 (model ENS, fit on every labelled day)

| rank | code | P(lock at ARA), calibrated | P(touch), calibrated | P(GRU), calibrated | close | ARA price | locked today | buyable (offer at close) | ret1 | vol ratio | queue imbalance | freq ratio | foreign net | days since ARA |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **UNSP** | **15.8 %** | 36.0 % | 16.3 % | 320 | 400 | yes | NO | 25.0 % | n/a | +1.00 | n/a | -1.5 % | 0 |
| 2 | **WAPO** | **18.8 %** | 28.0 % | 13.8 % | 352 | 440 | yes | NO | 24.8 % | 12.8x | +1.00 | 13.6x | 9.2 % | 0 |
| 3 | **BIPP** | **11.7 %** | 19.2 % | 14.2 % | 87 | 117 | yes | NO | 33.8 % | 36.7x | +1.00 | 26.6x | 0.2 % | 0 |
| 4 | **AGAR** | **4.3 %** | 8.7 % | 6.2 % | 2,370 | 2,960 | - | yes | -0.4 % | 3.1x | +0.99 | 8.8x | -1.3 % | 3 |
| 5 | **SAFE** | **5.5 %** | 6.7 % | 3.6 % | 730 | 910 | - | yes | -14.6 % | 17.8x | -1.00 | 37.5x | -6.6 % | 17 |
| 6 | **TEBE** | **4.6 %** | 5.0 % | 2.8 % | 2,370 | 2,960 | - | yes | 15.6 % | 4.3x | -0.03 | 3.3x | -0.1 % | 26 |
| 7 | **SMLE** | **3.8 %** | 11.1 % | 5.0 % | 282 | 352 | - | yes | 6.0 % | 1.4x | +0.99 | 1.3x | 23.5 % | 60 |
| 8 | **SMMT** | **3.9 %** | 7.8 % | 3.2 % | 3,170 | 3,960 | - | yes | 7.8 % | 1.4x | +0.72 | 1.6x | 1.6 % | 14 |
| 9 | **CSMI** | **3.7 %** | 7.4 % | 4.0 % | 236 | 294 | - | yes | 0.9 % | 2.7x | +0.24 | 6.3x | -0.8 % | 3 |
| 10 | **SAPX** | **4.0 %** | 5.2 % | 2.7 % | 392 | 490 | - | yes | -8.0 % | 1.3x | +0.99 | 1.8x | 5.7 % | 2 |
| 11 | **MGNA** | **3.9 %** | 4.4 % | 2.6 % | 210 | 262 | - | yes | 4.0 % | 3.7x | +0.56 | 2.5x | -4.2 % | 6 |
| 12 | **AKSI** | **3.8 %** | 6.9 % | 2.2 % | 424 | 530 | - | yes | 6.0 % | 4.9x | +0.17 | 3.2x | -1.0 % | 14 |
| 13 | **ASLI** | **3.0 %** | 3.8 % | 2.7 % | 486 | 605 | - | yes | 17.4 % | 7.7x | -0.90 | 8.9x | 5.5 % | 18 |
| 14 | **UANG** | **3.1 %** | 3.4 % | 2.5 % | 3,980 | 4,970 | - | yes | -1.0 % | 0.4x | +0.90 | 0.3x | -9.6 % | 6 |
| 15 | **BAPA** | **2.4 %** | 4.7 % | 2.2 % | 126 | 170 | - | yes | 6.8 % | 12.3x | +1.00 | 8.5x | -3.3 % | 60 |
| 16 | **BAIK** | **1.5 %** | 2.7 % | 3.7 % | 276 | 344 | - | yes | 0.7 % | 2.3x | +1.00 | 1.3x | 10.4 % | 60 |
| 17 | **BAJA** | **2.3 %** | 2.7 % | 1.4 % | 388 | 484 | - | yes | -11.0 % | 1.9x | -0.18 | 2.2x | -22.6 % | 3 |
| 18 | **MPXL** | **2.3 %** | 3.7 % | 1.3 % | 199 | 268 | - | yes | -9.5 % | 59.0x | +0.56 | 23.8x | 0.4 % | 1 |
| 19 | **HELI** | **2.0 %** | 2.0 % | 1.5 % | 250 | 312 | - | yes | 2.5 % | 4.6x | -0.03 | 3.8x | 0.1 % | 60 |
| 20 | **KICI** | **2.3 %** | 4.8 % | 1.2 % | 298 | 372 | - | yes | 0.7 % | 0.4x | +0.98 | 0.4x | -1.7 % | 4 |

Not a ticket. Menu ML-3 / menu 16: the names most likely to lock are mostly locked already (no offer to buy); the buyable picks lose on average. Use: a holder sells INTO a lock; a watcher knows which names to look at. ARA scope stays frozen (operator, 2026-09-23) - this is a study, not a screen.

_Run 2026-09-24 21:14, 3.9 min._