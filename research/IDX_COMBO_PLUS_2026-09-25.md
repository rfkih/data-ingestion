# IDX menu 35 - price book + value book + financial statements: combining what the desk knows - 2026-09-25 - 6 trials, cumulative N = 863

Engine #168/#177 (Rp 20 M, 20 slots, lots, offer/bid, fees), deployed 10/5/5 + cash30, 2022-01-03 -> 2026-09-16. Value book vs combined book: daily return correlation +0.33, monthly +0.32.

| arm | CAGR | Sharpe | mDD | Sharpe H1 | Sharpe H2 | Sharpe ex-2025 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| REF | +36.2% | 1.95 | -15% | 1.88 | 2.12 | 1.31 | +19% | +20% | +9% | +101% | +32% |
| VALUE | +16.6% | 0.99 | -23% | 0.79 | 1.25 | 0.93 | +31% | -8% | +9% | +20% | +24% |
| BLEND80 | +32.4% | 1.98 | -13% | 1.87 | 2.17 | 1.39 | +21% | +14% | +9% | +82% | +31% |
| BLEND70 | +30.5% | 1.96 | -12% | 1.80 | 2.17 | 1.40 | +23% | +11% | +9% | +73% | +30% |
| BLEND60 | +28.6% | 1.90 | -13% | 1.68 | 2.14 | 1.39 | +24% | +8% | +9% | +65% | +29% |
| BLEND50 | +26.6% | 1.80 | -15% | 1.54 | 2.07 | 1.35 | +25% | +5% | +9% | +56% | +29% |
| BLEND_WF | +30.3% | 1.84 | -13% | 1.47 | 2.17 | 1.22 | +21% | +5% | +9% | +82% | +31% |
| QV_LOSS | +30.7% | 1.76 | -18% | 2.05 | 1.69 | 1.26 | +18% | +22% | +12% | +73% | +19% |
| QV_WORSE | +28.6% | 1.90 | -13% | 1.76 | 2.10 | 1.29 | +13% | +13% | +13% | +76% | +24% |

Walk-forward blend weights (combined-book share by year): {2022: 0.8, 2023: 0.5, 2024: 0.8, 2025: 0.8, 2026: 0.8}

## Fundamental veto: coverage and what it removed

| arm | sleeve | trades | with a report | vetoed |
|---|---|---|---|---|
| QV_LOSS | ML | 195 | 176 | 40 |
| QV_LOSS | trend | 266 | 265 | 29 |
| QV_LOSS | gap | 233 | 232 | 31 |
| QV_WORSE | ML | 195 | 176 | 70 |
| QV_WORSE | trend | 266 | 265 | 92 |
| QV_WORSE | gap | 233 | 232 | 90 |

Trend + ML trades, price return entry -> exit (informative):

| arm | group | n | mean | median | win |
|---|---|---|---|---|---|
| QV_LOSS | kept | 392 | +6.6% | -1.2% | 46% |
| QV_LOSS | vetoed | 69 | +5.1% | +2.0% | 54% |
| QV_WORSE | kept | 299 | +7.8% | -1.1% | 47% |
| QV_WORSE | vetoed | 162 | +3.8% | -0.7% | 47% |

## Verdict (pre-registered)

- **BLEND80**: full no, halves no, ex2025 yes, walk_forward no
- **BLEND70**: full no, halves no, ex2025 yes, walk_forward no
- **BLEND60**: full no, halves no, ex2025 yes, walk_forward no
- **BLEND50**: full no, halves no, ex2025 yes, walk_forward no
- **QV_LOSS**: full no, halves no, ex2025 no
- **QV_WORSE**: full no, halves no, ex2025 no

Deflated Sharpe at N = 863: {'REF': 0.8741785348281044}

## Reading (written after the run)

**0 of 6 BETTER.** The combined book is already close to the best this information set can do.

1. **The value sleeve is a damper, not an edge.** Correlation with the combined book +0.33 - less diversifying than hoped
   (both are long small/mid IDX equities). BLEND80: Sharpe 1.98 vs 1.95, mDD -13 vs -15 %, CAGR 32.4 vs 36.2 %; it helps
   only outside 2025 (ex-2025 Sharpe 1.39 vs 1.31) and loses in H1. The walk-forward weight (0.8 most years, 0.5 in 2023)
   gives Sharpe 1.84 - worse than not blending. Same shape as menu 31's gold: smaller drawdown, less return, no Sharpe gain
   that survives the halves.
2. **The financial-statement veto HURTS.** Trend/ML entries in loss-making companies did as well or better than the rest
   (vetoed: median +2.0 %, win 54 % vs kept -1.2 %, 46 %). The price signal already carries what the last report says; a
   breakout in a loss-maker is often the turnaround the market is pricing. QV_LOSS cuts Sharpe to 1.76 and deepens the
   drawdown to -18 %; QV_WORSE removes a third of the trades for a lower CAGR. Do not add a fundamental veto to the
   price sleeves.
3. **The reference itself holds up**: deflated Sharpe 0.87 at N = 863, positive every year 2022-2026, Sharpe >= 1.88 in
   both halves. But ex-2025 its Sharpe is 1.31 and 2025 alone is +101 % - the backtest's level is flattered by one year;
   expect something nearer the ex-2025 profile live.
