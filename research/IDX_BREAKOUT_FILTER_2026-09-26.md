# IDX menu BK-1 - breakout holds or fails: a model as a filter on the trend book - 2026-09-26 - 4 trials, cumulative N = 857

Events: the deployed trend signal on LIQ, one per name per 20 days: 1,531 (1,507 with a full 20-day outcome); hold5 base rate 54%, clean +10 % run 36%. Walk-forward 2022-2026.

## Accuracy (informative)

| year | events | P(hold5) | model AUC | volume-ratio AUC | distance-above-level AUC | model AUC on clean10 |
|---|---|---|---|---|---|---|
| 2022 | 265 | 53% | 0.707 | 0.603 | 0.722 | 0.639 |
| 2023 | 200 | 48% | 0.686 | 0.627 | 0.694 | 0.664 |
| 2024 | 228 | 50% | 0.717 | 0.578 | 0.725 | 0.676 |
| 2025 | 316 | 58% | 0.773 | 0.615 | 0.803 | 0.713 |
| 2026 | 151 | 46% | 0.718 | 0.517 | 0.668 | 0.638 |

Pooled: model 0.727, volume ratio 0.596, distance 0.735 -> **NOT informative** (bar: +0.03 over the best single feature). Top 30 % by prediction held 75% vs bottom 30 % 29%; clean +10 % runs 50% vs 20%.

Top features (gain share): gap 27%, r250 6%, squeeze 5%, base_er 5%, comp_r20 4%, base_net 4%, vr 4%, r1 4%, log_px 3%, f20 3%

## The money: trend book (K = 10, trail10, desk costs), stitched walk-forward window

### small (the live book's universe - the verdict)

| arm | trades | hit | net/trade | CAGR | Sharpe | mDD | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| deployed | 397 | 40% | +2.95% | +25.3% | 1.09 | -30% | +23.5 | -6.0 | +5.6 | +147.7 | -8.8 |
| F30 | 385 | 40% | +3.47% | +26.1% | 1.17 | -36% | +26.6 | +6.3 | +9.4 | +143.9 | -20.6 |
| RANK | 386 | 39% | +2.96% | +21.3% | 0.98 | -35% | +16.5 | -7.7 | +20.1 | +113.2 | -13.0 |
| VR3 | 322 | 40% | +4.47% | +27.0% | 1.23 | -40% | +28.1 | +16.3 | +3.9 | +165.8 | -28.4 |

### LIQ (robustness)

| arm | trades | hit | net/trade | CAGR | Sharpe | mDD | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| deployed | 382 | 35% | +0.50% | +3.5% | 0.27 | -35% | -12.5 | -13.3 | +13.7 | +74.3 | -22.4 |
| F30 | 378 | 34% | +0.60% | +4.7% | 0.32 | -35% | -9.0 | -18.6 | +8.9 | +95.3 | -22.0 |
| RANK | 383 | 35% | +0.72% | +5.7% | 0.36 | -35% | +0.9 | -18.7 | +17.7 | +63.8 | -18.8 |
| VR3 | 357 | 34% | +0.13% | +0.3% | 0.12 | -43% | -6.9 | -12.6 | +5.2 | +73.1 | -31.5 |

## Verdict (pre-registered rule)

- **F30**: small does not improve (worse years 2); LIQ does not (worse years 2)
- **RANK**: small does not improve (worse years 4); LIQ does not (worse years 2)
- **VR3**: small does not improve (worse years 2); LIQ does not (worse years 3)
