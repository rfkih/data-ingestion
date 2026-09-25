# IDX menu ML-6d — the cost-aware ML book's drawdown: anatomy and filters — 2026-09-25 — 5 trials, cumulative N = 765

Base book (e5 | margin 2 | ema 3 | K 10, LIQ, 2022-01 ->): CAGR +29.1 %, Sharpe 0.91, mDD -51 %, 437 closed trades.

## Drawdown episodes

| from | trough | to | depth | days |
|---|---|---|---|---|
| 2026-01-20 | 2026-06-08 | 2026-09-24 | -51 % | 160 |
| 2022-06-02 | 2023-01-13 | 2024-01-25 | -42 % | 406 |
| 2025-01-30 | 2025-04-09 | 2025-04-22 | -22 % | 49 |

## 2022 trades: losers (< -10 %) vs the rest, medians at entry

| feature | losers | others |
|---|---|---|
| price | 330 | 362 |
| value60 | 1.209e+10 | 1.033e+10 |
| vol20 | 0.04123 | 0.05069 |
| ret20 | 0.0433 | 0.04327 |
| ret60 | 0.0702 | 0.01639 |
| spread_bps | 59.54 | 60.98 |
| gap | 0 | 0.00495 |
| volr1 | 0.95 | 0.6569 |
| dist_hi252 | -0.4286 | -0.3377 |
| atr_pct | 0.06863 | 0.07459 |
| pos20 | 0.5 | 0.4237 |
| free_float | 1 | 1 |
| lmcap | 27.68 | 28.47 |
| e_in | 0.03551 | 0.03179 |
| comp_dma200 | 0.05281 | 0.05418 |
| breadth | 0.4112 | 0.3961 |

2022 by price band (n, mean net, share < -10 %):

```
                        size      mean  <lambda_0>
price                                             
(0.0, 200.0]              25 -0.058466    0.480000
(200.0, 500.0]            38 -0.067841    0.473684
(500.0, 2000.0]           28 -0.008665    0.321429
(2000.0, 5000.0]           8  0.215289    0.250000
(5000.0, 1000000000.0]     6 -0.150182    0.666667
```

2022 by vol20 quartile:

```
                   size      mean  <lambda_0>
vol20                                        
(0.00674, 0.0309]    27 -0.046943    0.333333
(0.0309, 0.0488]     26 -0.054654    0.576923
(0.0488, 0.0643]     26 -0.047892    0.384615
(0.0643, 0.115]      26  0.018177    0.423077
```

2022 by prior 20-day return quartile:

```
                  size      mean  <lambda_0>
ret20                                       
(-0.542, -0.174]    27 -0.050213    0.370370
(-0.174, 0.0433]    26 -0.068493    0.500000
(0.0433, 0.204]     26 -0.048025    0.423077
(0.204, 1.237]      26  0.035545    0.423077
```

2022 by regime at entry:

```
             size      mean  <lambda_0>
comp_dma200                            
False          10 -0.026495    0.300000
True           95 -0.033643    0.442105
```

Worst 12 trades of 2022: ARTO 2022-11-17 -47 % (swap, 46 d); JAWA 2022-01-04 -35 % (max_hold, 61 d); AYLS 2022-03-29 -31 % (swap, 26 d); ESIP 2022-04-27 -30 % (max_hold, 61 d); KJEN 2022-09-30 -29 % (swap, 22 d); OPMS 2022-10-06 -29 % (swap, 54 d); TECH 2022-10-19 -27 % (swap, 17 d); TOBA 2022-12-01 -24 % (swap, 25 d); MITI 2022-02-16 -24 % (swap, 30 d); PKPK 2022-02-09 -23 % (swap, 57 d); FIRE 2022-12-21 -23 % (swap, 19 d); TRUK 2022-01-04 -22 % (max_hold, 61 d)

## Filters (declared from the 2022 profile, read on 2023-26)

| filter | trades | 2023-26 CAGR | Sharpe | mDD | 2022 CAGR | 2022 mDD | verdict |
|---|---|---|---|---|---|---|---|
| base | 437 | +48.9 % | 1.27 | -51 % | -24.6 % | -33 % | reference |
| no_vol_top | 355 | +14.6 % | 0.62 | -42 % | -19.8 % | -29 % | no: sharpe 0.62 < base 1.27 + 0.15; cagr < 80 % base |
| no_runup | 378 | +15.2 % | 0.60 | -53 % | -21.7 % | -29 % | no: sharpe 0.60 < base 1.27 + 0.15; mdd deeper; cagr < 80 % base |
| price_ge_200 | 435 | +29.1 % | 0.89 | -58 % | -22.0 % | -31 % | no: sharpe 0.89 < base 1.27 + 0.15; mdd deeper; cagr < 80 % base |
| no_vol_no_runup | 345 | +4.1 % | 0.29 | -42 % | -20.8 % | -33 % | no: sharpe 0.29 < base 1.27 + 0.15; cagr < 80 % base |
| regime_on | 311 | +7.5 % | 0.42 | -46 % | -22.1 % | -30 % | no: sharpe 0.42 < base 1.27 + 0.15; cagr < 80 % base |

## Verdict (menu ML-6d, study stored)

Filters BETTER out of sample: none.

## Follow-up (post-hoc, 2 informal trials, not counted; tmp/ml_icgate.py)

Is the drawdown the SCORE failing? No. The daily cross-sectional IC of the 5d score is positive in 53 of 57 months (2022-01 -> 2026-09);
the worst book months (2022-06 -13.5 %, 2022-11/12 -11/-10 %, 2026-03 -28 %, 2026-05 -16 %) mostly had a positive IC. Monthly IC vs
book return correlation 0.32. The book loses when the small-cap universe falls as a whole: a long-only book of volatile names carries
the market, whatever the ranking does. An IC gate on new entries (trailing 40-day IC > 0, lagged 6 d) is off only 5 % of days and
changes nothing (26.6 % / 0.86 / -46 %); halving exposure after a 15 % drawdown until a new high gives 19.7 % / 0.88 / -35 %; both
together 18.3 % / 0.84 / -32 %. Conclusion: no entry filter fixes this book's drawdown; it is exposure, to be handled by allocation
(the sleeve study #157: ML-voltarget 50 / trend 50 = 23.7 % / 1.49 / -24 %) or by a hedge the IDX retail desk does not have.
