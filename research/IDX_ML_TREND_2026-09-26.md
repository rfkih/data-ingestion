# IDX menu ML-1 — LightGBM loser-filter for the trend entry — 2026-09-26 — 2 trials, cumulative N = 403

Walk-forward by year (train on trades exited before the test year); filter = skip signals below the 33rd percentile of the training predictions; book = deployed K=10 trail-10, closing offer/bid + fees. Features: price/volume, foreign flow, market, PIT fundamentals, disclosures since 2023-07 (NaN before), sector. News / pack sentiment / consensus excluded: history starts Sep 2026.

## Universe `small` — 1245 fresh signals 2020-2026, label mean net +4.53 %, hit 38 %, hold 27 d

| test year | train n | test n | IC (Spearman) | top third net | bottom third net | top hit | bottom hit | skipped share | skipped net | kept net |
|---|---|---|---|---|---|---|---|---|---|---|
| 2022 | 256 | 180 | -0.001 | -1.10 % | -1.01 % | 30 % | 35 % | 53 % | +0.79 % | +3.72 % |
| 2023 | 446 | 178 | -0.051 | +2.61 % | +1.43 % | 38 % | 41 % | 31 % | +1.52 % | +0.89 % |
| 2024 | 612 | 200 | -0.045 | +2.10 % | -0.61 % | 34 % | 39 % | 40 % | -1.64 % | +0.28 % |
| 2025 | 817 | 274 | +0.181 | +20.60 % | +4.14 % | 55 % | 37 % | 18 % | +0.15 % | +14.55 % |
| 2026 | 1074 | 138 | +0.009 | -5.04 % | -3.45 % | 33 % | 28 % | 24 % | -3.13 % | -4.44 % |

| book 2022-01 -> 2026-09 | trades | hold | hit | avg net | payoff | t | CAGR | Sharpe | mDD | years |
|---|---|---|---|---|---|---|---|---|---|---|
| plain rule (deployed) | 396 | 24 | 40 % | +2.94 % | 2.20 | 2.4 | +25.6 % | 1.10 | -30 % | 22:+25 23:-6 24:+6 25:+148 26:-9 |
| rule + ML filter | 375 | 24 | 40 % | +3.53 % | 2.32 | 2.6 | +28.1 % | 1.25 | -33 % | 22:+52 23:+10 24:+6 25:+104 26:-15 |
| random + trail10 | 386 | 28 | 32 % | -0.85 % | 1.84 | -0.8 | -6.5 % | -0.20 | -49 % | 22:-7 23:-16 24:-13 25:+51 26:-28 |

**Verdict `small`: not adopted: sharpe<plain+0.15, mdd deeper, tercile spread 3/5**

Top features by gain (last model): comp_ma50 7 %, np_yoy 6 %, comp_ma200 5 %, dist_ma200 5 %, mom60 5 %, net_margin 5 %, mom20 4 %, mom120 4 %, roe 4 %, breadth 4 %, f60 4 %, sector 4 %

## Universe `LIQ` — 2009 fresh signals 2020-2026, label mean net +2.63 %, hit 36 %, hold 29 d

| test year | train n | test n | IC (Spearman) | top third net | bottom third net | top hit | bottom hit | skipped share | skipped net | kept net |
|---|---|---|---|---|---|---|---|---|---|---|
| 2022 | 416 | 334 | -0.035 | -0.74 % | -1.62 % | 28 % | 32 % | 37 % | -1.94 % | -0.45 % |
| 2023 | 753 | 261 | -0.024 | -0.02 % | -0.70 % | 33 % | 32 % | 17 % | -0.69 % | +0.66 % |
| 2024 | 1011 | 337 | +0.048 | +0.07 % | -2.25 % | 30 % | 23 % | 45 % | -3.43 % | +0.10 % |
| 2025 | 1356 | 410 | +0.049 | +12.37 % | +2.29 % | 44 % | 41 % | 25 % | +2.62 % | +10.03 % |
| 2026 | 1729 | 211 | -0.030 | -3.91 % | -3.25 % | 37 % | 26 % | 26 % | -4.04 % | -3.86 % |

| book 2022-01 -> 2026-09 | trades | hold | hit | avg net | payoff | t | CAGR | Sharpe | mDD | years |
|---|---|---|---|---|---|---|---|---|---|---|
| plain rule (deployed) | 382 | 27 | 35 % | +0.58 % | 2.06 | 0.5 | +4.4 % | 0.31 | -35 % | 22:-9 23:-13 24:+14 25:+74 26:-23 |
| rule + ML filter | 384 | 26 | 34 % | -0.04 % | 1.90 | -0.0 | -0.0 % | 0.10 | -37 % | 22:-4 23:-19 24:+13 25:+49 26:-23 |
| random + trail10 | 366 | 30 | 29 % | +0.65 % | 2.73 | 0.5 | -2.4 % | -0.01 | -48 % | 22:-17 23:-4 24:-11 25:+75 26:-27 |

**Verdict `LIQ`: not adopted: sharpe<plain+0.15, cagr<80%plain, mdd deeper**

Top features by gain (last model): mom120 7 %, np_yoy 6 %, comp_ma200 5 %, breadth 5 %, rev_yoy 5 %, comp_ma50 5 %, mom20 5 %, net_margin 4 %, mom60 4 %, dist_ma200 4 %, der 4 %, comp_ret20 4 %

