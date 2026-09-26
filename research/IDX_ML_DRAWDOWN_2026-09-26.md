# IDX menu ML-6d — the cost-aware ML book's drawdown: anatomy and filters — 2026-09-26 — 5 trials, cumulative N = 765

Base book (e5 | margin 2 | ema 3 | K 10, LIQ, 2022-01 ->): CAGR +28.4 %, Sharpe 0.91, mDD -54 %, 432 closed trades.

## Drawdown episodes

| from | trough | to | depth | days |
|---|---|---|---|---|
| 2026-01-20 | 2026-05-21 | 2026-09-25 | -54 % | 161 |
| 2022-05-19 | 2023-03-20 | 2024-02-05 | -39 % | 421 |
| 2025-01-30 | 2025-04-09 | 2025-04-22 | -27 % | 49 |

## 2022 trades: losers (< -10 %) vs the rest, medians at entry

| feature | losers | others |
|---|---|---|
| price | 528 | 431 |
| value60 | 1.003e+10 | 1.02e+10 |
| vol20 | 0.0619 | 0.05238 |
| ret20 | 0.09869 | 0.04327 |
| ret60 | 0.1363 | 0.1564 |
| spread_bps | 56.18 | 65.15 |
| gap | 0 | 0 |
| volr1 | 0.8352 | 0.6362 |
| dist_hi252 | -0.38 | -0.3294 |
| atr_pct | 0.08802 | 0.07745 |
| pos20 | 0.5717 | 0.4439 |
| free_float | 1 | 1 |
| lmcap | 27.54 | 28.31 |
| e_in | 0.04179 | 0.04023 |
| comp_dma200 | 0.04762 | 0.04846 |
| breadth | 0.3815 | 0.3568 |

2022 by price band (n, mean net, share < -10 %):

```
                        size      mean  <lambda_0>
price                                             
(0.0, 200.0]              19  0.012299    0.315789
(200.0, 500.0]            35 -0.074500    0.457143
(500.0, 2000.0]           35 -0.004809    0.400000
(2000.0, 5000.0]           9  0.035511    0.555556
(5000.0, 1000000000.0]     6 -0.118945    0.500000
```

2022 by vol20 quartile:

```
                   size      mean  <lambda_0>
vol20                                        
(0.00605, 0.0323]    26  0.059218    0.230769
(0.0323, 0.0546]     26 -0.048355    0.461538
(0.0546, 0.0705]     26 -0.045202    0.500000
(0.0705, 0.13]       26 -0.078593    0.500000
```

2022 by prior 20-day return quartile:

```
                  size      mean  <lambda_0>
ret20                                       
(-0.671, -0.152]    26 -0.005185    0.384615
(-0.152, 0.0559]    26 -0.043903    0.384615
(0.0559, 0.356]     26 -0.050273    0.461538
(0.356, 0.989]      26 -0.013570    0.461538
```

2022 by regime at entry:

```
             size      mean  <lambda_0>
comp_dma200                            
False          11 -0.055624    0.545455
True           93 -0.024993    0.408602
```

Worst 12 trades of 2022: TNCA 2022-04-28 -39 % (swap, 22 d); LPIN 2022-01-31 -38 % (swap, 9 d); MITI 2022-02-18 -36 % (swap, 53 d); OBMD 2022-11-08 -35 % (swap, 42 d); JAYA 2022-05-18 -29 % (max_hold, 61 d); INDX 2022-06-21 -28 % (swap, 44 d); KINO 2022-08-26 -27 % (max_hold, 61 d); OPMS 2022-10-07 -25 % (max_hold, 61 d); PICO 2022-11-29 -24 % (swap, 11 d); AYLS 2022-03-30 -23 % (swap, 31 d); BEBS 2022-02-14 -21 % (swap, 4 d); INDR 2022-08-09 -21 % (swap, 60 d)

## Filters (declared from the 2022 profile, read on 2023-26)

| filter | trades | 2023-26 CAGR | Sharpe | mDD | 2022 CAGR | 2022 mDD | verdict |
|---|---|---|---|---|---|---|---|
| base | 432 | +46.9 % | 1.27 | -54 % | -22.5 % | -29 % | reference |
| no_vol_top | 352 | +18.3 % | 0.74 | -43 % | -1.7 % | -17 % | no: sharpe 0.74 < base 1.27 + 0.15; cagr < 80 % base |
| no_runup | 353 | +11.1 % | 0.49 | -54 % | -22.5 % | -28 % | no: sharpe 0.49 < base 1.27 + 0.15; mdd deeper; cagr < 80 % base |
| price_ge_200 | 404 | +28.5 % | 0.90 | -55 % | -24.2 % | -38 % | no: sharpe 0.90 < base 1.27 + 0.15; mdd deeper; cagr < 80 % base |
| no_vol_no_runup | 322 | +8.0 % | 0.43 | -43 % | +2.8 % | -17 % | no: sharpe 0.43 < base 1.27 + 0.15; cagr < 80 % base |
| regime_on | 316 | +14.9 % | 0.67 | -49 % | -24.0 % | -30 % | no: sharpe 0.67 < base 1.27 + 0.15; cagr < 80 % base |

## Verdict (menu ML-6d, study stored)

Filters BETTER out of sample: none.
