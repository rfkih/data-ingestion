# IDX menu ML-1 — LightGBM loser-filter for the trend entry — 2026-09-22 — 2 trials, cumulative N = 403

Walk-forward by year (train on trades exited before the test year); filter = skip signals below the 33rd percentile of the training predictions; book = deployed K=10 trail-10, closing offer/bid + fees. Features: price/volume, foreign flow, market, PIT fundamentals, disclosures since 2023-07 (NaN before), sector. News / pack sentiment / consensus excluded: history starts Sep 2026.

## Universe `small` — 1199 fresh signals 2020-2026, label mean net +4.42 %, hit 38 %, hold 27 d

| test year | train n | test n | IC (Spearman) | top third net | bottom third net | top hit | bottom hit | skipped share | skipped net | kept net |
|---|---|---|---|---|---|---|---|---|---|---|
| 2022 | 228 | 171 | -0.088 | +1.01 % | +4.48 % | 32 % | 37 % | 50 % | +3.11 % | +2.00 % |
| 2023 | 409 | 173 | -0.020 | +0.92 % | +2.30 % | 38 % | 43 % | 34 % | +2.30 % | -0.41 % |
| 2024 | 570 | 197 | -0.065 | -1.64 % | -0.59 % | 29 % | 33 % | 37 % | +0.45 % | -0.98 % |
| 2025 | 773 | 273 | +0.150 | +21.44 % | +6.97 % | 53 % | 40 % | 17 % | +2.50 % | +13.75 % |
| 2026 | 1028 | 138 | -0.022 | -3.58 % | -2.65 % | 35 % | 33 % | 21 % | -2.21 % | -4.13 % |

| book 2022-01 -> 2026-09 | trades | hold | hit | avg net | payoff | t | CAGR | Sharpe | mDD | years |
|---|---|---|---|---|---|---|---|---|---|---|
| plain rule (deployed) | 386 | 24 | 40 % | +3.24 % | 2.30 | 2.5 | +26.5 % | 1.17 | -30 % | 22:+43 23:-5 24:+1 25:+131 26:-8 |
| rule + ML filter | 367 | 24 | 40 % | +3.17 % | 2.27 | 2.4 | +24.5 % | 1.12 | -34 % | 22:+51 23:-1 24:-3 25:+119 26:-15 |
| random + trail10 | 354 | 30 | 33 % | -0.15 % | 2.01 | -0.1 | -2.1 % | 0.00 | -39 % | 22:-1 23:-5 24:+14 25:+2 26:-17 |

**Verdict `small`: not adopted: sharpe<plain+0.15, mdd deeper, tercile spread 1/5**

Top features by gain (last model): comp_ma50 7 %, np_yoy 6 %, net_margin 6 %, breadth 5 %, rev_yoy 5 %, mom120 5 %, dist_ma200 4 %, mom60 4 %, sector 4 %, f60 4 %, roe 4 %, mom20 3 %

## Universe `LIQ` — 1960 fresh signals 2020-2026, label mean net +2.53 %, hit 36 %, hold 29 d

| test year | train n | test n | IC (Spearman) | top third net | bottom third net | top hit | bottom hit | skipped share | skipped net | kept net |
|---|---|---|---|---|---|---|---|---|---|---|
| 2022 | 385 | 325 | -0.027 | +0.55 % | -2.23 % | 31 % | 28 % | 39 % | -2.29 % | +0.03 % |
| 2023 | 713 | 256 | -0.041 | +0.04 % | +2.51 % | 37 % | 35 % | 10 % | -0.98 % | +0.14 % |
| 2024 | 966 | 334 | +0.074 | +2.40 % | -3.34 % | 35 % | 25 % | 37 % | -3.85 % | -0.09 % |
| 2025 | 1309 | 409 | +0.074 | +15.64 % | +1.45 % | 46 % | 35 % | 27 % | +2.89 % | +9.99 % |
| 2026 | 1680 | 211 | -0.062 | -4.61 % | -4.24 % | 31 % | 23 % | 27 % | -5.01 % | -3.03 % |

| book 2022-01 -> 2026-09 | trades | hold | hit | avg net | payoff | t | CAGR | Sharpe | mDD | years |
|---|---|---|---|---|---|---|---|---|---|---|
| plain rule (deployed) | 377 | 27 | 34 % | +0.62 % | 2.11 | 0.6 | +4.9 % | 0.33 | -36 % | 22:-8 23:-12 24:+12 25:+76 26:-22 |
| rule + ML filter | 389 | 26 | 34 % | +0.24 % | 1.97 | 0.2 | +1.1 % | 0.16 | -37 % | 22:+12 23:-24 24:+10 25:+45 26:-22 |
| random + trail10 | 331 | 33 | 33 % | -2.26 % | 1.37 | -2.5 | -12.0 % | -0.52 | -55 % | 22:-23 23:-1 24:-0 25:-1 26:-24 |

**Verdict `LIQ`: not adopted: sharpe<plain+0.15, cagr<80%plain, mdd deeper, tercile spread 3/5**

Top features by gain (last model): mom120 6 %, np_yoy 6 %, comp_ret20 5 %, net_margin 5 %, comp_ma50 5 %, rev_yoy 4 %, mom60 4 %, dist_ma200 4 %, der 4 %, breadth 4 %, f60 4 %, mom20 3 %


## Verdict (menu ML-1, study stored)

0 of 2. A LightGBM over everything the desk knows at the close of the signal day — price, volume, foreign flow, market regime,
point-in-time fundamentals, disclosures, sector — cannot tell which breakouts will be stopped out:

- Out-of-sample rank correlation between the model's score and the trade's net return is ~0 (−0.09 … +0.15); the top third beats
  the bottom third in 1 of 5 years on `small` and 3 of 5 on LIQ. The one year with a positive IC (2025) is the mania year, where
  "anything cheap with growing profits" ran — a regime, not a model.
- The signals the filter would have SKIPPED earned more than the ones it kept in 3 of 5 years on `small`: the model removes
  winners as readily as losers. The filtered book is worse on both universes (Sharpe 1.12 vs 1.17, drawdown −34 % vs −30 %).
- Feature importances are flat (no feature above 7 % of gain): there is no dominant, stable predictor — the same picture the
  desk found with hand rules in menus 6-7 and 13-14.

Why this differs from menus 10-11 (where PIT fundamentals do separate losers): that horizon is a year and the unit is the
name; here the horizon is a 24-day trade whose outcome is dominated by path noise around a 10 % stop. Fundamentals say who
survives; they do not say who breaks out and keeps going next month.

Not adopted. The trend book stays as it is. ML remains in the desk where it has shown lift — the doublers ranker at a 24-month
horizon (study 2026-09-17) — and its costed book test (ML-2) is the next ML menu. News, pack sentiment and consensus features
start their history in September 2026 and can be tried once they cover two test years.
