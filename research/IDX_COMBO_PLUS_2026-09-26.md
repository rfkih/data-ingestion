# IDX menu 35 - price book + value book + financial statements: combining what the desk knows - 2026-09-26 - 6 trials, cumulative N = 863

Engine #168/#177 (Rp 20 M, 20 slots, lots, offer/bid, fees), deployed 10/5/5 + cash30, 2022-01-03 -> 2026-09-16. Value book vs combined book: daily return correlation +0.33, monthly +0.28.

| arm | CAGR | Sharpe | mDD | Sharpe H1 | Sharpe H2 | Sharpe ex-2025 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| REF | +37.3% | 1.84 | -20% | 1.15 | 2.35 | 0.96 | +4% | +15% | +20% | +147% | +16% |
| VALUE | +16.6% | 0.99 | -23% | 0.79 | 1.25 | 0.93 | +31% | -8% | +9% | +20% | +24% |
| BLEND80 | +33.4% | 1.88 | -18% | 1.23 | 2.38 | 1.06 | +9% | +11% | +18% | +115% | +17% |
| BLEND70 | +31.4% | 1.87 | -17% | 1.24 | 2.37 | 1.11 | +12% | +8% | +17% | +101% | +18% |
| BLEND60 | +29.3% | 1.83 | -17% | 1.23 | 2.33 | 1.13 | +15% | +6% | +16% | +87% | +19% |
| BLEND50 | +27.2% | 1.76 | -18% | 1.18 | 2.25 | 1.14 | +17% | +3% | +15% | +74% | +20% |
| BLEND_WF | +29.3% | 1.70 | -18% | 0.93 | 2.28 | 0.93 | +9% | +3% | +17% | +101% | +17% |
| QV_LOSS | +33.2% | 1.77 | -17% | 1.10 | 2.26 | 1.01 | +4% | +14% | +16% | +115% | +20% |
| QV_WORSE | +30.3% | 1.91 | -12% | 1.01 | 2.55 | 1.01 | +9% | +6% | +12% | +115% | +19% |

Walk-forward blend weights (combined-book share by year): {2022: 0.8, 2023: 0.5, 2024: 0.7, 2025: 0.7, 2026: 0.8}

## Fundamental veto: coverage and what it removed

| arm | sleeve | trades | with a report | vetoed |
|---|---|---|---|---|
| QV_LOSS | ML | 208 | 197 | 28 |
| QV_LOSS | trend | 282 | 281 | 34 |
| QV_LOSS | gap | 233 | 233 | 31 |
| QV_WORSE | ML | 208 | 197 | 64 |
| QV_WORSE | trend | 282 | 281 | 100 |
| QV_WORSE | gap | 233 | 233 | 92 |

Trend + ML trades, price return entry -> exit (informative):

| arm | group | n | mean | median | win |
|---|---|---|---|---|---|
| QV_LOSS | kept | 428 | +6.6% | -2.8% | 44% |
| QV_LOSS | vetoed | 62 | +4.9% | -2.0% | 47% |
| QV_WORSE | kept | 326 | +7.7% | -2.7% | 44% |
| QV_WORSE | vetoed | 164 | +4.0% | -3.2% | 45% |

## Verdict (pre-registered)

- **BLEND80**: full no, halves yes, ex2025 yes, walk_forward no
- **BLEND70**: full no, halves yes, ex2025 yes, walk_forward no
- **BLEND60**: full no, halves no, ex2025 yes, walk_forward no
- **BLEND50**: full no, halves no, ex2025 yes, walk_forward no
- **QV_LOSS**: full no, halves no, ex2025 yes
- **QV_WORSE**: full no, halves no, ex2025 yes

Deflated Sharpe at N = 863: {'REF': 0.8015539099263209}
