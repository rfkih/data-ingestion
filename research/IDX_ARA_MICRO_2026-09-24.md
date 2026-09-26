# IDX menu ML-3b — ARA besok dari bar + microstructure penutupan, LightGBM vs GRU — 2026-09-24 — 6 trials, cumulative N = 717

409,722 name-days (880 names) on the main boards, previous >= Rp 50, value >= Rp 1 bn, 2020-01 -> 2026-09-24; walk-forward by test year. Base rate LOCK1 (closes at ARA tomorrow) 0.55 %, TOUCH1 (touches it) 0.84 %. Pre-registered in `research/idx_ara_micro.py`.

## Accuracy of the ranked list, per test year (label LOCK1)

| model | year | rows | base | AUC | AP | precision@5 | precision@10 | precision@20 | recall@20 | lift@5 | buyable share of top-10 | precision@10 among buyable | next-day ret top-10 | ret buyable top-10 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BAR | 2022 | 71,283 | 0.33 % | 0.877 | 0.141 | **7.5 %** | **4.7 %** | 2.7 % | 56 % | 22.7x | 86 % | 1.7 % | 1.17 % | 0.19 % |
| BAR | 2023 | 63,310 | 0.29 % | 0.886 | 0.156 | **7.3 %** | **4.2 %** | 2.5 % | 65 % | 24.8x | 86 % | 1.5 % | 0.55 % | -0.21 % |
| BAR | 2024 | 58,901 | 0.30 % | 0.905 | 0.211 | **8.2 %** | **4.5 %** | 2.6 % | 70 % | 27.4x | 84 % | 1.4 % | 0.33 % | -0.49 % |
| BAR | 2025 | 70,490 | 0.89 % | 0.884 | 0.192 | **17.0 %** | **11.7 %** | 7.1 % | 54 % | 19.2x | 61 % | 3.1 % | 1.70 % | -0.62 % |
| BAR | 2026 | 57,675 | 0.71 % | 0.870 | 0.108 | **12.5 %** | **8.5 %** | 5.5 % | 45 % | 17.6x | 66 % | 3.4 % | 0.52 % | -1.06 % |
| MICRO | 2022 | 71,283 | 0.33 % | 0.841 | 0.096 | **6.9 %** | **4.0 %** | 2.5 % | 51 % | 21.0x | 82 % | 1.0 % | 1.36 % | 0.24 % |
| MICRO | 2023 | 63,310 | 0.29 % | 0.834 | 0.095 | **6.1 %** | **3.6 %** | 2.1 % | 54 % | 20.8x | 85 % | 0.8 % | 0.89 % | 0.13 % |
| MICRO | 2024 | 58,901 | 0.30 % | 0.895 | 0.180 | **7.8 %** | **4.4 %** | 2.7 % | 72 % | 26.3x | 84 % | 1.3 % | 0.57 % | -0.20 % |
| MICRO | 2025 | 70,490 | 0.89 % | 0.853 | 0.175 | **18.2 %** | **11.5 %** | 6.9 % | 52 % | 20.6x | 59 % | 2.5 % | 2.23 % | 0.22 % |
| MICRO | 2026 | 57,675 | 0.71 % | 0.797 | 0.091 | **11.6 %** | **7.3 %** | 4.4 % | 37 % | 16.2x | 65 % | 1.4 % | 1.12 % | -0.27 % |
| BAR+MICRO | 2022 | 71,283 | 0.33 % | 0.882 | 0.170 | **8.0 %** | **4.6 %** | 2.7 % | 56 % | 24.4x | 84 % | 1.6 % | 1.63 % | 0.65 % |
| BAR+MICRO | 2023 | 63,310 | 0.29 % | 0.886 | 0.157 | **7.2 %** | **4.4 %** | 2.5 % | 65 % | 24.5x | 86 % | 1.7 % | 0.90 % | 0.19 % |
| BAR+MICRO | 2024 | 58,901 | 0.30 % | 0.925 | 0.223 | **8.4 %** | **4.8 %** | 2.7 % | 73 % | 28.2x | 84 % | 1.8 % | 0.91 % | 0.20 % |
| BAR+MICRO | 2025 | 70,490 | 0.89 % | 0.880 | 0.200 | **17.6 %** | **12.0 %** | 7.3 % | 55 % | 19.9x | 60 % | 3.4 % | 2.04 % | -0.08 % |
| BAR+MICRO | 2026 | 57,675 | 0.71 % | 0.868 | 0.114 | **12.4 %** | **8.4 %** | 5.5 % | 46 % | 17.4x | 66 % | 3.1 % | 0.79 % | -0.70 % |
| DL | 2022 | 71,283 | 0.33 % | 0.900 | 0.089 | **7.7 %** | **4.6 %** | 3.0 % | 62 % | 23.4x | 83 % | 1.7 % | 1.09 % | -0.02 % |
| DL | 2023 | 63,310 | 0.29 % | 0.913 | 0.190 | **7.7 %** | **4.5 %** | 2.7 % | 70 % | 26.2x | 85 % | 1.8 % | 0.49 % | -0.34 % |
| DL | 2024 | 58,901 | 0.30 % | 0.932 | 0.138 | **8.4 %** | **4.9 %** | 2.9 % | 77 % | 28.2x | 84 % | 1.9 % | 0.12 % | -0.74 % |
| DL | 2025 | 70,490 | 0.89 % | 0.899 | 0.225 | **20.5 %** | **12.7 %** | 7.7 % | 58 % | 23.2x | 59 % | 4.1 % | 1.87 % | -0.47 % |
| DL | 2026 | 57,675 | 0.71 % | 0.877 | 0.118 | **13.7 %** | **8.7 %** | 5.8 % | 49 % | 19.2x | 65 % | 3.5 % | 0.83 % | -0.73 % |
| ENS | 2022 | 71,283 | 0.33 % | 0.897 | 0.126 | **8.0 %** | **4.8 %** | 2.9 % | 61 % | 24.4x | 83 % | 2.0 % | 1.69 % | 0.70 % |
| ENS | 2023 | 63,310 | 0.29 % | 0.905 | 0.141 | **7.6 %** | **4.8 %** | 2.7 % | 70 % | 25.9x | 85 % | 2.2 % | 0.84 % | 0.11 % |
| ENS | 2024 | 58,901 | 0.30 % | 0.937 | 0.143 | **8.7 %** | **5.1 %** | 2.9 % | 78 % | 29.1x | 84 % | 2.2 % | 0.43 % | -0.36 % |
| ENS | 2025 | 70,490 | 0.89 % | 0.890 | 0.160 | **19.5 %** | **12.7 %** | 7.5 % | 56 % | 22.0x | 59 % | 4.2 % | 2.18 % | 0.06 % |
| ENS | 2026 | 57,675 | 0.71 % | 0.874 | 0.108 | **13.5 %** | **8.8 %** | 5.6 % | 47 % | 18.9x | 65 % | 3.7 % | 0.71 % | -0.86 % |

Reading: precision@K = of the K names the model ranks highest each day, the share that closes at ARA the next day (mean over days). recall@20 = the share of the year's ARA locks that were inside the daily top-20. lift = precision@5 / base rate. 'Buyable' = the pick still had an offer at today's close (not locked today).

## Does the closing-book microstructure add to the bars? (BAR+MICRO minus BAR)

| year | ΔAUC | Δprecision@10 | Δrecall@20 | Δbuyable precision@10 | MICRO alone AUC | MICRO alone precision@10 |
|---|---|---|---|---|---|---|
| 2022 | +0.005 | -0.1 pp | +0.0 pp | -0.1 pp | 0.841 | 4.0 % |
| 2023 | +0.000 | +0.1 pp | +0.0 pp | +0.2 pp | 0.834 | 3.6 % |
| 2024 | +0.019 | +0.3 pp | +2.8 pp | +0.4 pp | 0.895 | 4.4 % |
| 2025 | -0.004 | +0.3 pp | +1.1 pp | +0.3 pp | 0.853 | 11.5 % |
| 2026 | -0.002 | -0.1 pp | +0.2 pp | -0.2 pp | 0.797 | 7.3 % |

**Rule (>= +0.01 AUC and >= +1 pp precision@10 in >= 4/5 years): 0/5 years -> micro does NOT add.**
**DL (GRU) within 0.005 AUC of the tree in 5/5 years -> USEFUL; ENS beats the tree on precision@10 in 5/5 -> ADOPTED.**
**Rank model: ENS.**

Secondary label TOUCH1 (touches ARA tomorrow, BAR+MICRO): 2022: AUC 0.899, p@5 11.4 %, p@10 6.8 %; 2023: AUC 0.914, p@5 12.2 %, p@10 7.3 %; 2024: AUC 0.934, p@5 12.3 %, p@10 7.6 %; 2025: AUC 0.885, p@5 27.5 %, p@10 17.7 %; 2026: AUC 0.874, p@5 20.7 %, p@10 13.8 %.

## 'Akurasi' at one operating point — flag the top 1 % of scores (threshold fixed on the training years)

| model | year | flagged | TP | FP | FN | precision | recall | F1 | balanced acc | plain accuracy | always-'no' accuracy |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BAR+MICRO | 2022 | 192 | 61 | 131 | 174 | **31.8 %** | **26.0 %** | 0.286 | 62.9 % | 99.57 % | 99.67 % |
| BAR+MICRO | 2023 | 291 | 61 | 230 | 125 | **21.0 %** | **32.8 %** | 0.256 | 66.2 % | 99.44 % | 99.71 % |
| BAR+MICRO | 2024 | 500 | 82 | 418 | 94 | **16.4 %** | **46.6 %** | 0.243 | 72.9 % | 99.13 % | 99.70 % |
| BAR+MICRO | 2025 | 1,016 | 235 | 781 | 389 | **23.1 %** | **37.7 %** | 0.287 | 68.3 % | 98.34 % | 99.11 % |
| BAR+MICRO | 2026 | 619 | 111 | 508 | 300 | **17.9 %** | **27.0 %** | 0.216 | 63.1 % | 98.60 % | 99.29 % |
| DL | 2022 | 261 | 46 | 215 | 189 | **17.6 %** | **19.6 %** | 0.185 | 59.6 % | 99.43 % | 99.67 % |
| DL | 2023 | 361 | 70 | 291 | 116 | **19.4 %** | **37.6 %** | 0.256 | 68.6 % | 99.36 % | 99.71 % |
| DL | 2024 | 459 | 85 | 374 | 91 | **18.5 %** | **48.3 %** | 0.268 | 73.8 % | 99.21 % | 99.70 % |
| DL | 2025 | 1,221 | 260 | 961 | 364 | **21.3 %** | **41.7 %** | 0.282 | 70.1 % | 98.12 % | 99.11 % |
| DL | 2026 | 738 | 120 | 618 | 291 | **16.3 %** | **29.2 %** | 0.209 | 64.1 % | 98.42 % | 99.29 % |

Plain accuracy is not the number to quote: saying 'no ARA' for every name is already right 99.4-99.7 % of the time. Precision (how often a flagged name locks) and recall (how many of the locks were flagged) are the accuracy of this model.

## Calibration by score decile, 2026 (BAR+MICRO)

| decile | raw model P | calibrated P | observed P(LOCK1) | next-day return | n |
|---|---|---|---|---|---|
| 1 | 0.09 % | 0.02 % | 0.00 % | -0.20 % | 5,768 |
| 2 | 0.28 % | 0.04 % | 0.02 % | -0.17 % | 5,767 |
| 3 | 0.62 % | 0.07 % | 0.09 % | -0.13 % | 5,768 |
| 4 | 1.29 % | 0.12 % | 0.12 % | -0.16 % | 5,767 |
| 5 | 2.70 % | 0.19 % | 0.19 % | -0.04 % | 5,768 |
| 6 | 5.98 % | 0.32 % | 0.29 % | -0.08 % | 5,767 |
| 7 | 13.54 % | 0.57 % | 0.42 % | -0.23 % | 5,767 |
| 8 | 26.99 % | 0.98 % | 0.59 % | -0.25 % | 5,768 |
| 9 | 45.83 % | 1.67 % | 1.09 % | -0.21 % | 5,767 |
| 10 | 74.61 % | 4.97 % | 4.32 % | 0.25 % | 5,768 |

The raw score is inflated by scale_pos_weight (decile 10 says 75 %, reality 4.3 %); every probability printed below is Platt-recalibrated on the pooled out-of-fold scores (tree a=0.64 b=-3.98, GRU a=0.91 b=-3.72). Ranks, AUC and precision@K do not change under a monotone map.

## What the model looks at (gain share, final fit) and the placebo

- BAR+MICRO: vol20 50.0 %, hl_range 14.5 %, near 8.0 %, days_since_ara 5.7 %, ret5 2.3 %, vr5 1.7 %, ret60 1.4 %, ret1 1.0 %, dist_hi60 0.9 %, vr 0.9 %, breadth_near 0.9 %, log_value 0.7 %
- MICRO alone: qimb 40.7 %, turnover 19.6 %, fpart 9.0 %, atr_ratio 7.0 %, log_avg_trade 5.8 %, gap_open 3.5 %, freq_ratio 2.4 %, log_ov_vol 2.2 %, fnet5 2.0 %, fnet20 1.4 %, qimb5 1.2 %, log_bv_vol 1.2 %
- placebo (LOCK1 shuffled in the training set, 3 draws): AUC 0.398, 0.387, 0.315 vs real 0.868 -> percentile 100.
- GRU 2026 fold: best validation AUC 0.886 after 5 epochs; final fit val AUC 0.883.

## Tick-level microstructure (Stockbit feed) — why it is not in the model yet

The feed holds 5 sessions, 647 name-days over ~136 liquid names, and **0 ARA touches**. A classifier cannot be trained on zero positives; ARA is a small-cap event and the feed covers the liquid tail. Pre-registered for when the feed reaches >= 20 sessions and >= 30 touches: intraday re-rank of the nightly list at 09:15 / 10:00 from OBI1/5, OFI 5-min, TFI, spread, distance to ARA in ticks, market OFI (the menu-31 feature set), label = touches ARA later that day; bar = AUC >= 0.70 and precision@5 >= 2x the nightly list's.

## Ranked list for the session after 2026-09-24 (model ENS, fit on every labelled day)

| rank | code | P(lock at ARA), calibrated | P(touch), calibrated | P(GRU), calibrated | close | ARA price | locked today | buyable (offer at close) | ret1 | vol ratio | queue imbalance | freq ratio | foreign net | days since ARA |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **UNSP** | **14.8 %** | 34.8 % | 18.6 % | 320 | 400 | yes | NO | 25.0 % | n/a | +1.00 | n/a | -1.5 % | 0 |
| 2 | **WAPO** | **12.8 %** | 25.5 % | 13.0 % | 352 | 440 | yes | NO | 24.8 % | 12.8x | +1.00 | 13.6x | 9.2 % | 0 |
| 3 | **BIPP** | **11.1 %** | 20.0 % | 18.2 % | 87 | 117 | yes | NO | 33.8 % | 36.7x | +1.00 | 26.6x | 0.2 % | 0 |
| 4 | **SMLE** | **5.8 %** | 9.9 % | 4.5 % | 282 | 352 | - | yes | 6.0 % | 1.4x | +0.99 | 1.3x | 23.5 % | 60 |
| 5 | **SAFE** | **7.0 %** | 7.3 % | 4.0 % | 730 | 910 | - | yes | -14.6 % | 17.8x | -1.00 | 37.5x | -6.6 % | 17 |
| 6 | **AGAR** | **3.9 %** | 6.4 % | 5.9 % | 2,370 | 2,960 | - | yes | -0.4 % | 3.1x | +0.99 | 8.8x | -1.3 % | 3 |
| 7 | **SMMT** | **4.1 %** | 7.6 % | 3.3 % | 3,170 | 3,960 | - | yes | 7.8 % | 1.4x | +0.72 | 1.6x | 1.6 % | 14 |
| 8 | **TEBE** | **4.0 %** | 7.1 % | 3.1 % | 2,370 | 2,960 | - | yes | 15.6 % | 4.3x | -0.03 | 3.3x | -0.1 % | 26 |
| 9 | **CSMI** | **2.8 %** | 8.8 % | 3.4 % | 236 | 294 | - | yes | 0.9 % | 2.7x | +0.24 | 6.3x | -0.8 % | 3 |
| 10 | **MGNA** | **2.7 %** | 5.4 % | 3.2 % | 210 | 262 | - | yes | 4.0 % | 3.7x | +0.56 | 2.5x | -4.2 % | 6 |
| 11 | **SAPX** | **3.0 %** | 5.8 % | 2.5 % | 392 | 490 | - | yes | -8.0 % | 1.3x | +0.99 | 1.8x | 5.7 % | 2 |
| 12 | **ASLI** | **2.7 %** | 4.2 % | 2.7 % | 486 | 605 | - | yes | 17.4 % | 7.7x | -0.90 | 8.9x | 5.5 % | 18 |
| 13 | **AKSI** | **2.4 %** | 6.3 % | 2.3 % | 424 | 530 | - | yes | 6.0 % | 4.9x | +0.17 | 3.2x | -1.0 % | 14 |
| 14 | **MSIN** | **3.7 %** | 2.1 % | 1.5 % | 206 | 256 | - | yes | -14.9 % | 1.7x | -1.00 | 0.9x | -5.3 % | 60 |
| 15 | **BAPA** | **2.3 %** | 2.0 % | 2.1 % | 126 | 170 | - | yes | 6.8 % | 12.3x | +1.00 | 8.5x | -3.3 % | 60 |
| 16 | **BAJA** | **2.3 %** | 4.3 % | 1.7 % | 388 | 484 | - | yes | -11.0 % | 1.9x | -0.18 | 2.2x | -22.6 % | 3 |
| 17 | **UANG** | **1.9 %** | 2.7 % | 2.0 % | 3,980 | 4,970 | - | yes | -1.0 % | 0.4x | +0.90 | 0.3x | -9.6 % | 6 |
| 18 | **MPXL** | **2.2 %** | 4.0 % | 1.3 % | 199 | 268 | - | yes | -9.5 % | 59.0x | +0.56 | 23.8x | 0.4 % | 1 |
| 19 | **SNLK** | **2.1 %** | 3.1 % | 1.0 % | 234 | 292 | - | yes | 6.4 % | 1.7x | +0.81 | 2.4x | 7.4 % | 60 |
| 20 | **PMUI** | **1.9 %** | 2.2 % | 1.3 % | 114 | 153 | - | yes | 9.6 % | 42.7x | +1.00 | 26.8x | -1.4 % | 60 |

Not a ticket. Menu ML-3 / menu 16: the names most likely to lock are mostly locked already (no offer to buy); the buyable picks lose on average. Use: a holder sells INTO a lock; a watcher knows which names to look at. ARA scope stays frozen (operator, 2026-09-23) - this is a study, not a screen.

_Run 2026-09-26 03:04, 3.4 min._