# IDX menu BK-1 - breakout holds or fails: a model as a filter on the trend book - 2026-09-25 - 4 trials, cumulative N = 857

Events: the deployed trend signal on LIQ, one per name per 20 days: 1,499 (1,476 with a full 20-day outcome); hold5 base rate 54%, clean +10 % run 36%. Walk-forward 2022-2026.

## Accuracy (informative)

| year | events | P(hold5) | model AUC | volume-ratio AUC | distance-above-level AUC | model AUC on clean10 |
|---|---|---|---|---|---|---|
| 2022 | 259 | 53% | 0.712 | 0.605 | 0.720 | 0.651 |
| 2023 | 199 | 48% | 0.690 | 0.632 | 0.695 | 0.652 |
| 2024 | 225 | 50% | 0.718 | 0.577 | 0.727 | 0.663 |
| 2025 | 315 | 58% | 0.765 | 0.614 | 0.804 | 0.708 |
| 2026 | 152 | 47% | 0.733 | 0.525 | 0.669 | 0.647 |

Pooled: model 0.726, volume ratio 0.598, distance 0.735 -> **NOT informative** (bar: +0.03 over the best single feature). Top 30 % by prediction held 73% vs bottom 30 % 27%; clean +10 % runs 48% vs 18%.

Top features (gain share): gap 26%, r250 6%, squeeze 5%, base_er 4%, comp_r20 4%, base_net 4%, r1 4%, vr 4%, log_px 4%, f20 4%

## The money: trend book (K = 10, trail10, desk costs), stitched walk-forward window

### small (the live book's universe - the verdict)

| arm | trades | hit | net/trade | CAGR | Sharpe | mDD | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| deployed | 391 | 40% | +2.80% | +22.7% | 1.03 | -30% | +26.4 | -5.5 | +0.9 | +130.9 | -9.2 |
| F30 | 377 | 38% | +3.05% | +21.0% | 0.98 | -33% | +15.3 | -2.6 | -1.5 | +157.3 | -16.8 |
| RANK | 387 | 39% | +3.24% | +22.8% | 1.04 | -37% | +8.8 | -6.9 | +13.3 | +143.8 | -9.6 |
| VR3 | 320 | 40% | +5.14% | +30.9% | 1.37 | -41% | +33.7 | +17.1 | +6.9 | +171.9 | -25.8 |

### LIQ (robustness)

| arm | trades | hit | net/trade | CAGR | Sharpe | mDD | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| deployed | 378 | 34% | +0.61% | +4.1% | 0.30 | -36% | -10.0 | -12.5 | +11.6 | +76.1 | -22.5 |
| F30 | 374 | 34% | +0.28% | +1.2% | 0.16 | -38% | -14.8 | -19.1 | +10.7 | +90.0 | -27.3 |
| RANK | 371 | 36% | +1.76% | +11.9% | 0.63 | -36% | -3.3 | -12.4 | +25.4 | +100.1 | -21.6 |
| VR3 | 360 | 34% | +0.58% | +2.7% | 0.23 | -42% | -9.0 | -7.2 | -0.4 | +92.6 | -30.2 |

## Verdict (pre-registered rule)

- **F30**: small does not improve (worse years 3); LIQ does not (worse years 4)
- **RANK**: small does not improve (worse years 3); LIQ improves (worse years 0)
- **VR3**: small IMPROVES (worse years 1); LIQ does not (worse years 2)

## Reading (written after the run; the rule's verdict stands, but it must be read with these)

1. **The model is the geometry again.** Distance above the breakout level alone scores AUC 0.735; the model with 28 features
   0.726. It sorts breakouts well (top 30 % held 73 % vs 27 %; clean +10 % runs 48 % vs 18 %) only because a close far above
   the level needs a larger fall to count as failed - the menu-27 trap in a new label. Used in the book it adds nothing
   (F30 and RANK: no improvement on small, 3 worse years each). The breakout-survival model family is CLOSED.
2. **VR3 passes the rule on small, and the rule had a hole.** Only signals on >= 3x volume: CAGR +30.9 % vs +22.7 %, Sharpe
   1.37 vs 1.03, 1 worse year. But its drawdown is DEEPER, -41 % vs -30 %, and the pre-registered rule did not penalise a
   deeper drawdown (it only rewarded a shallower one) - a gap in the bar, written down here rather than fixed after the fact.
   It fails on LIQ (Sharpe 0.23 vs 0.30), its 2026 is -25.8 % vs -9.2 %, and the whole gap is 2022-2023 plus 2025's +172 %.
   With the operator's standing goal (CAGR with the drawdown as low as possible) VR3 is NOT recommended for the live book;
   a re-test with the regime gate the live book actually runs, and a bar that also caps the drawdown, is the honest next step
   if the operator wants to pursue it.
3. The live trend book runs with the regime gate (overlay:regime_filter), which this engine run does not apply; all arms
   are compared without it, so the comparison is fair but the levels are not the live book's.
