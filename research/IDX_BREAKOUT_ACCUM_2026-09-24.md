# IDX - rata-rata kenaikan setelah breakout + filter akumulasi broker - 2026-09-24 - descriptive, 0 new trials (cumulative N = 711)

Follow-up to study #130. Same events: a close above the top of a 60-day base (channel <= 25 %, |net move| <= 15 %, ER <= 0.30) on volume >= 2x the 20-day median, one per name per 20 days, panel 2020-01-02 -> 2026-09-23. Returns from the breakout close on adjusted prices; events without a complete 20-day forward window are excluded.

## A. Berapa rata-rata kenaikan setelah breakout

| slice | horizon | events | mean | median | share up | mean winner | mean loser |
|---|---|---|---|---|---|---|---|
| BLUE | +1 d | 223 | -0.1 % | -0.4 % | 41 % | +2.6 % | -1.9 % |
|  | +3 d | 223 | -0.1 % | -0.3 % | 46 % | +3.4 % | -3.1 % |
|  | +5 d | 223 | +0.4 % | +0.0 % | 48 % | +5.2 % | -3.9 % |
|  | +10 d | 223 | +0.3 % | -0.1 % | 48 % | +6.6 % | -5.6 % |
|  | +20 d | 223 | +0.4 % | -0.4 % | 50 % | +9.2 % | -8.3 % |
|  | +60 d | 219 | +0.9 % | -2.2 % | 44 % | +16.7 % | -11.7 % |
| LIQ | +1 d | 501 | +0.2 % | -0.4 % | 40 % | +3.5 % | -2.1 % |
|  | +3 d | 501 | +0.8 % | +0.0 % | 47 % | +5.4 % | -3.3 % |
|  | +5 d | 501 | +1.3 % | +0.0 % | 48 % | +7.4 % | -4.1 % |
|  | +10 d | 501 | +1.4 % | -0.3 % | 47 % | +9.5 % | -5.6 % |
|  | +20 d | 501 | +2.5 % | +0.2 % | 50 % | +13.3 % | -8.3 % |
|  | +60 d | 495 | +4.4 % | -1.4 % | 46 % | +23.5 % | -11.7 % |
| small | +1 d | 283 | +0.3 % | -0.4 % | 40 % | +4.2 % | -2.2 % |
|  | +3 d | 283 | +1.5 % | +0.0 % | 47 % | +7.0 % | -3.4 % |
|  | +5 d | 283 | +2.0 % | -0.2 % | 47 % | +9.1 % | -4.2 % |
|  | +10 d | 283 | +2.4 % | -0.5 % | 46 % | +11.9 % | -5.6 % |
|  | +20 d | 283 | +4.1 % | +0.2 % | 51 % | +16.2 % | -8.2 % |
|  | +60 d | 281 | +7.1 % | -0.9 % | 47 % | +28.4 % | -11.8 % |
| THIN | +1 d | 1096 | +0.2 % | -0.4 % | 39 % | +4.3 % | -2.3 % |
|  | +3 d | 1096 | +0.7 % | +0.0 % | 46 % | +6.0 % | -3.7 % |
|  | +5 d | 1096 | +1.2 % | -0.3 % | 46 % | +7.9 % | -4.5 % |
|  | +10 d | 1096 | +1.3 % | -0.5 % | 46 % | +10.0 % | -6.1 % |
|  | +20 d | 1096 | +2.4 % | -0.8 % | 46 % | +14.5 % | -7.8 % |
|  | +60 d | 1079 | +6.3 % | -1.8 % | 45 % | +28.7 % | -11.9 % |

| tier | events | mean MFE 20 d | mean MAE 20 d | mean net +20 d (next-close fill, costs) |
|---|---|---|---|---|
| BLUE | 223 | +9.6 % | -7.7 % | -0.2 % |
| LIQ | 501 | +13.2 % | -8.0 % | +1.5 % |
| small | 283 | +15.9 % | -8.2 % | +2.8 % |
| THIN | 1096 | +14.3 % | -8.4 % | +1.3 % |

### The same profile split by the first five days (LIQ)

| slice | horizon | events | mean | median | share up | mean winner | mean loser |
|---|---|---|---|---|---|---|---|
| LIQ survived 5 d | +1 d | 277 | +1.6 % | +0.8 % | 56 % | +4.0 % | -1.5 % |
|  | +3 d | 277 | +4.0 % | +1.8 % | 75 % | +5.9 % | -1.8 % |
|  | +5 d | 277 | +5.1 % | +2.9 % | 72 % | +8.0 % | -2.3 % |
|  | +10 d | 277 | +5.2 % | +1.9 % | 63 % | +10.7 % | -4.2 % |
|  | +20 d | 277 | +7.1 % | +3.2 % | 65 % | +15.2 % | -8.2 % |
|  | +60 d | 273 | +8.5 % | +1.5 % | 52 % | +27.0 % | -11.7 % |
| LIQ failed <=5 d | +1 d | 224 | -1.7 % | -1.5 % | 20 % | +1.7 % | -2.5 % |
|  | +3 d | 224 | -3.2 % | -2.7 % | 11 % | +1.5 % | -3.8 % |
|  | +5 d | 224 | -3.3 % | -3.0 % | 17 % | +4.2 % | -4.9 % |
|  | +10 d | 224 | -3.2 % | -3.5 % | 26 % | +6.1 % | -6.4 % |
|  | +20 d | 224 | -3.2 % | -3.6 % | 31 % | +8.3 % | -8.4 % |
|  | +60 d | 222 | -0.7 % | -3.3 % | 38 % | +17.6 % | -11.8 % |

## B. Akumulasi yang bisa diukur di seluruh panel (proxy)

**LIQ** - Spearman IC of each measure against the 20-day return and against surviving five days (permutation p over 2000 draws)

| measure | coverage | IC vs 20-day return | p | IC vs survives 5 d |
|---|---|---|---|---|
| fgn60 | 100 % | -0.047 | 0.289 | +0.070 |
| fgn20 | 100 % | -0.028 | 0.551 | +0.057 |
| f20 | 100 % | -0.019 | 0.674 | +0.061 |
| obv60 | 100 % | +0.074 | 0.102 | +0.110 |
| upvol | 100 % | +0.044 | 0.304 | +0.070 |
| quiet | 100 % | -0.019 | 0.678 | +0.052 |

**THIN** - Spearman IC of each measure against the 20-day return and against surviving five days (permutation p over 2000 draws)

| measure | coverage | IC vs 20-day return | p | IC vs survives 5 d |
|---|---|---|---|---|
| fgn60 | 100 % | -0.043 | 0.170 | +0.004 |
| fgn20 | 100 % | -0.006 | 0.837 | +0.005 |
| f20 | 100 % | -0.007 | 0.808 | +0.001 |
| obv60 | 100 % | +0.023 | 0.451 | +0.036 |
| upvol | 100 % | +0.015 | 0.615 | +0.022 |
| quiet | 100 % | +0.018 | 0.563 | +0.071 |

**LIQ / fgn60** (Q1 = least accumulation, Q4 = most)

| quartile | events | back inside <=5 d | above top @20 d | up @20 d | mean 20 d | median 20 d | ran +10 % |
|---|---|---|---|---|---|---|---|
| Q1 | 126 | 51 % | 61 % | 55 % | +5.2 % | +1.7 % | 40 % |
| Q2 | 125 | 42 % | 58 % | 50 % | +4.0 % | +0.0 % | 42 % |
| Q3 | 125 | 45 % | 58 % | 48 % | +0.3 % | -0.5 % | 39 % |
| Q4 | 125 | 41 % | 60 % | 48 % | +0.6 % | -0.4 % | 35 % |

**LIQ / fgn20** (Q1 = least accumulation, Q4 = most)

| quartile | events | back inside <=5 d | above top @20 d | up @20 d | mean 20 d | median 20 d | ran +10 % |
|---|---|---|---|---|---|---|---|
| Q1 | 126 | 48 % | 61 % | 55 % | +4.6 % | +1.3 % | 38 % |
| Q2 | 125 | 47 % | 59 % | 47 % | +3.9 % | -0.4 % | 46 % |
| Q3 | 125 | 43 % | 54 % | 47 % | +1.0 % | -1.3 % | 36 % |
| Q4 | 125 | 41 % | 62 % | 51 % | +0.4 % | +0.3 % | 35 % |

**LIQ / f20** (Q1 = least accumulation, Q4 = most)

| quartile | events | back inside <=5 d | above top @20 d | up @20 d | mean 20 d | median 20 d | ran +10 % |
|---|---|---|---|---|---|---|---|
| Q1 | 126 | 48 % | 61 % | 55 % | +4.4 % | +1.3 % | 37 % |
| Q2 | 125 | 47 % | 57 % | 46 % | +3.8 % | -0.4 % | 45 % |
| Q3 | 125 | 43 % | 56 % | 46 % | +1.0 % | -1.3 % | 38 % |
| Q4 | 125 | 41 % | 62 % | 54 % | +0.9 % | +1.4 % | 35 % |

**LIQ / obv60** (Q1 = least accumulation, Q4 = most)

| quartile | events | back inside <=5 d | above top @20 d | up @20 d | mean 20 d | median 20 d | ran +10 % |
|---|---|---|---|---|---|---|---|
| Q1 | 126 | 54 % | 54 % | 44 % | -0.1 % | -1.2 % | 34 % |
| Q2 | 125 | 43 % | 60 % | 52 % | +3.8 % | +0.3 % | 38 % |
| Q3 | 125 | 43 % | 54 % | 47 % | +2.4 % | -0.8 % | 38 % |
| Q4 | 125 | 38 % | 69 % | 58 % | +4.0 % | +1.4 % | 45 % |

**LIQ / upvol** (Q1 = least accumulation, Q4 = most)

| quartile | events | back inside <=5 d | above top @20 d | up @20 d | mean 20 d | median 20 d | ran +10 % |
|---|---|---|---|---|---|---|---|
| Q1 | 126 | 48 % | 54 % | 45 % | +2.4 % | -1.3 % | 30 % |
| Q2 | 125 | 48 % | 60 % | 52 % | +1.6 % | +0.3 % | 41 % |
| Q3 | 125 | 40 % | 60 % | 50 % | +2.1 % | +0.2 % | 38 % |
| Q4 | 125 | 42 % | 62 % | 53 % | +4.0 % | +0.7 % | 46 % |

**LIQ / quiet** (Q1 = least accumulation, Q4 = most)

| quartile | events | back inside <=5 d | above top @20 d | up @20 d | mean 20 d | median 20 d | ran +10 % |
|---|---|---|---|---|---|---|---|
| Q1 | 260 | 50 % | 58 % | 50 % | +3.3 % | +0.3 % | 40 % |
| Q2 | 174 | 35 % | 60 % | 50 % | +1.8 % | +0.1 % | 40 % |
| Q3 | 67 | 48 % | 58 % | 49 % | +1.2 % | -0.5 % | 34 % |

**THIN / fgn60** (Q1 = least accumulation, Q4 = most)

| quartile | events | back inside <=5 d | above top @20 d | up @20 d | mean 20 d | median 20 d | ran +10 % |
|---|---|---|---|---|---|---|---|
| Q1 | 274 | 45 % | 61 % | 50 % | +4.1 % | +0.1 % | 39 % |
| Q2 | 274 | 39 % | 57 % | 44 % | +2.1 % | -1.6 % | 41 % |
| Q3 | 274 | 44 % | 57 % | 42 % | +2.1 % | -1.8 % | 49 % |
| Q4 | 274 | 43 % | 62 % | 48 % | +1.4 % | +0.0 % | 40 % |

**THIN / fgn20** (Q1 = least accumulation, Q4 = most)

| quartile | events | back inside <=5 d | above top @20 d | up @20 d | mean 20 d | median 20 d | ran +10 % |
|---|---|---|---|---|---|---|---|
| Q1 | 274 | 41 % | 60 % | 49 % | +3.2 % | +0.0 % | 39 % |
| Q2 | 274 | 45 % | 57 % | 42 % | +2.4 % | -1.6 % | 45 % |
| Q3 | 274 | 45 % | 57 % | 42 % | +2.5 % | -1.7 % | 44 % |
| Q4 | 274 | 41 % | 63 % | 51 % | +1.6 % | +0.6 % | 41 % |

**THIN / f20** (Q1 = least accumulation, Q4 = most)

| quartile | events | back inside <=5 d | above top @20 d | up @20 d | mean 20 d | median 20 d | ran +10 % |
|---|---|---|---|---|---|---|---|
| Q1 | 274 | 40 % | 60 % | 50 % | +3.1 % | +0.0 % | 38 % |
| Q2 | 274 | 46 % | 56 % | 41 % | +2.6 % | -1.7 % | 47 % |
| Q3 | 274 | 45 % | 57 % | 41 % | +2.2 % | -2.3 % | 46 % |
| Q4 | 274 | 41 % | 63 % | 52 % | +1.9 % | +0.8 % | 39 % |

**THIN / obv60** (Q1 = least accumulation, Q4 = most)

| quartile | events | back inside <=5 d | above top @20 d | up @20 d | mean 20 d | median 20 d | ran +10 % |
|---|---|---|---|---|---|---|---|
| Q1 | 274 | 47 % | 54 % | 41 % | +0.5 % | -1.7 % | 35 % |
| Q2 | 274 | 41 % | 61 % | 49 % | +3.9 % | +0.0 % | 42 % |
| Q3 | 274 | 41 % | 62 % | 47 % | +2.4 % | +0.0 % | 43 % |
| Q4 | 274 | 43 % | 60 % | 46 % | +3.0 % | -0.8 % | 50 % |

**THIN / upvol** (Q1 = least accumulation, Q4 = most)

| quartile | events | back inside <=5 d | above top @20 d | up @20 d | mean 20 d | median 20 d | ran +10 % |
|---|---|---|---|---|---|---|---|
| Q1 | 274 | 46 % | 55 % | 43 % | +2.3 % | -1.6 % | 34 % |
| Q2 | 274 | 42 % | 61 % | 46 % | +1.2 % | -0.7 % | 41 % |
| Q3 | 274 | 41 % | 62 % | 49 % | +2.6 % | +0.0 % | 43 % |
| Q4 | 274 | 43 % | 59 % | 46 % | +3.7 % | -1.0 % | 52 % |

**THIN / quiet** (Q1 = least accumulation, Q4 = most)

| quartile | events | back inside <=5 d | above top @20 d | up @20 d | mean 20 d | median 20 d | ran +10 % |
|---|---|---|---|---|---|---|---|
| Q1 | 425 | 48 % | 58 % | 48 % | +2.2 % | -0.4 % | 43 % |
| Q2 | 212 | 38 % | 57 % | 45 % | +1.1 % | -1.4 % | 43 % |
| Q3 | 251 | 40 % | 62 % | 43 % | +3.6 % | -0.7 % | 42 % |
| Q4 | 208 | 40 % | 61 % | 46 % | +2.9 % | -0.9 % | 39 % |

## C. Akumulasi broker sungguhan (idx.broker_summary)

Coverage: 42 of 1096 volume breakouts have 1 broker window(s) closing in the 180 days before the break (25 distinct names; the table holds 46 codes with multi-day windows, mostly monthly since 2023-09).

| measure | IC vs 20-day return | p | IC vs survives 5 d |
|---|---|---|---|
| acc_persist | -0.278 | 0.069 | +0.076 |
| acc_top | +0.126 | 0.425 | -0.058 |
| acc_conc | +0.072 | 0.647 | -0.102 |
| det_top5 | +0.329 | 0.037 | +0.171 |
| buyers_over_sellers | -0.327 | 0.063 | -0.172 |

**acc_persist** (Q1 = least, Q4 = most)

| quartile | events | back inside <=5 d | above top @20 d | up @20 d | mean 20 d | median 20 d | ran +10 % |
|---|---|---|---|---|---|---|---|
| Q1 | 11 | 55 % | 91 % | 82 % | +10.1 % | +4.7 % | 36 % |
| Q2 | 10 | 30 % | 70 % | 70 % | +7.7 % | +4.5 % | 20 % |
| Q3 | 11 | 45 % | 64 % | 64 % | +0.3 % | +4.5 % | 55 % |
| Q4 | 10 | 30 % | 50 % | 30 % | +0.0 % | -1.8 % | 30 % |

**acc_top** (Q1 = least, Q4 = most)

| quartile | events | back inside <=5 d | above top @20 d | up @20 d | mean 20 d | median 20 d | ran +10 % |
|---|---|---|---|---|---|---|---|
| Q1 | 11 | 36 % | 73 % | 55 % | +3.0 % | +4.5 % | 64 % |
| Q2 | 10 | 40 % | 50 % | 50 % | +2.8 % | +2.2 % | 30 % |
| Q3 | 10 | 40 % | 50 % | 50 % | +6.6 % | -0.8 % | 20 % |
| Q4 | 11 | 45 % | 100 % | 91 % | +5.8 % | +4.4 % | 27 % |

**acc_conc** (Q1 = least, Q4 = most)

| quartile | events | back inside <=5 d | above top @20 d | up @20 d | mean 20 d | median 20 d | ran +10 % |
|---|---|---|---|---|---|---|---|
| Q1 | 11 | 45 % | 64 % | 55 % | +4.1 % | +4.5 % | 55 % |
| Q2 | 10 | 10 % | 50 % | 40 % | +8.4 % | -3.2 % | 60 % |
| Q3 | 10 | 50 % | 60 % | 60 % | +0.1 % | +3.9 % | 10 % |
| Q4 | 11 | 55 % | 100 % | 91 % | +5.5 % | +4.4 % | 18 % |

**det_top5** (Q1 = least, Q4 = most)

| quartile | events | back inside <=5 d | above top @20 d | up @20 d | mean 20 d | median 20 d | ran +10 % |
|---|---|---|---|---|---|---|---|
| Q1 | 11 | 45 % | 45 % | 36 % | -2.4 % | -5.3 % | 27 % |
| Q2 | 14 | 57 % | 64 % | 57 % | +2.5 % | +2.0 % | 36 % |
| Q3 | 6 | 17 % | 67 % | 67 % | +9.0 % | +3.9 % | 33 % |
| Q4 | 11 | 27 % | 100 % | 91 % | +11.6 % | +7.1 % | 45 % |

**The declared split** - accumulated = at least one broker net-positive in all 1 window(s) AND the top accumulator took 8.7 % or more of all buying (the event-set median)

| quartile | events | back inside <=5 d | above top @20 d | up @20 d | mean 20 d | median 20 d | ran +10 % |
|---|---|---|---|---|---|---|---|
| accumulated | 21 | 43 % | 76 % | 71 % | +6.2 % | +3.6 % | 24 % |
| not accumulated | 21 | 38 % | 62 % | 52 % | +2.9 % | +4.5 % | 48 % |

Gap in 'up at 20 days': +19.0 pp, permutation p = 0.348. UNDERPOWERED by the declared rule (a side has fewer than 100 events) - read as a direction, not a finding.

## D. Bisakah broksum HISTORY diambil dari Stockbit? (probed live, 2026-09-24)

Twelve read-only probes against the operator's own Stockbit key, one request per second.

| probe | result |
|---|---|
| legacy per-window feed `marketdetectors/BBCA?from=2026-08-01&to=2026-08-29` | **HTTP 402 `paywall`** - arbitrary historical windows are Pro-only, as the code comment said |
| free feed `order-trade/broker/distribution` with `period=TB_PERIOD_LAST_1_DAY` | HTTP 200, start = end = 2026-09-23 |
| the same with `TB_PERIOD_LAST_1_MONTH` | **HTTP 200, start 2026-08-23 end 2026-09-23** |
| the same with `TB_PERIOD_LAST_3_MONTHS` | **HTTP 200, start 2026-06-23 end 2026-09-23** |
| the same with `TB_PERIOD_LAST_1_YEAR` | **HTTP 200, start 2025-09-23 end 2026-09-23** |
| `LAST_1_WEEK`, `LAST_5_DAY`, `LAST_6_MONTH`, `MTD`, `YTD`, `CUSTOM`, `DATE_RANGE`, … | HTTP 400 "Your request is invalid" |
| `date=2026-06-30`, `end_date=`, `to=`, `start_date=`+`end_date=` with a valid period | HTTP 200 but the window ignores them - always ends on the last trading day |

The aggregation is real, not a label: BBCA's top buy broker over `LAST_1_YEAR` is Rp 40,695 bn against Rp 138 bn over
`LAST_1_DAY`. **So the desk CAN read, for free and for any name, who has been accumulating over the last month, three
months or year - but only as of today.** The window cannot be moved into the past, so the correlation in section C
cannot be backfilled; it can only be accumulated forward (store the aggregate daily) or bought (Stockbit Pro).

This corrects the note in `blackheart_ingest/idx/broker.py` ("There is no history and no multi-day window … only
LAST_1_DAY is valid"), which was true for `date=` but not for `period=`.

### What the live aggregates say about the current names (illustration, n = 18 - not evidence)

| code | group | top net accumulator 1Y (share of all buying) | 1Y top over 3M | over 1M | same broker in all three | brokers net + (1Y) |
|---|---|---|---|---|---|---|
| DFAM | breakout | XL Rp 9 bn (+0.9 %) | XA Rp 3 bn | HP Rp 1 bn | no | 4/12 |
| VISI | breakout | RF Rp 33 bn (+9.9 %) | RF Rp 11 bn | SQ Rp 5 bn | 1Y=3M | 7/14 |
| ULTJ | breakout | KZ Rp 88 bn (+5.8 %) | KZ Rp 49 bn | KZ Rp 47 bn | yes | 6/14 |
| MBSS | breakout | SQ Rp 63 bn (+3.6 %) | HP Rp 14 bn | SA Rp 11 bn | no | 7/13 |
| ANTM | breakout | BB Rp 2,966 bn (+3.3 %) | DX Rp 582 bn | ZP Rp 238 bn | no | 7/13 |
| BDMN | breakout | YU Rp 189 bn (+7.6 %) | CC Rp 28 bn | BB Rp 13 bn | no | 5/13 |
| BTPS | breakout | XL Rp 87 bn (+5.6 %) | BK Rp 45 bn | BK Rp 45 bn | no | 8/14 |
| PTBA | breakout | AK Rp 600 bn (+5.2 %) | AK Rp 423 bn | AK Rp 447 bn | yes | 6/14 |
| PWON | consolidating | SQ Rp 155 bn (+3.7 %) | OD Rp 25 bn | AK Rp 33 bn | no | 7/13 |
| JRPT | consolidating | PD Rp 94 bn (+80.2 %) | PD Rp 45 bn | PD Rp 11 bn | yes | 5/17 |
| LPPF | consolidating | CC Rp 57 bn (+5.8 %) | XL Rp 16 bn | XL Rp 10 bn | no | 7/13 |
| MGRO | consolidating | AZ Rp 23 bn (+4.5 %) | BQ Rp 2 bn | ZP Rp 1 bn | no | 7/13 |
| BJBR | consolidating | GR Rp 40 bn (+6.2 %) | GR Rp 12 bn | GR Rp 11 bn | yes | 7/13 |
| MSTI | consolidating | OD Rp 28 bn (+7.1 %) | OD Rp 21 bn | OD Rp 9 bn | yes | 4/15 |
| BJTM | consolidating | GR Rp 37 bn (+3.8 %) | XL Rp 10 bn | PD Rp 2 bn | no | 5/13 |
| BNGA | consolidating | IN Rp 68 bn (+4.8 %) | IN Rp 50 bn | IN Rp 36 bn | yes | 5/14 |
| ACES | consolidating | NI Rp 101 bn (+4.0 %) | RX Rp 15 bn | PD Rp 6 bn | no | 7/13 |
| BMRI | consolidating | YU Rp 2,813 bn (+2.0 %) | KZ Rp 1,006 bn | KZ Rp 491 bn | no | 8/12 |

Read this as a demonstration that the measure can be computed live, not as a result: 18 names, one date, no forward
outcome yet. JRPT's +80 % is the artefact of a name so thin that one broker is almost the whole book.

## Reading (written after the run)

**A. Rata-rata kenaikan setelah breakout.** On the 501 liquid volume breakouts: **mean +1.3 % at 5 days, +1.4 % at 10,
+2.5 % at 20, +4.4 % at 60**; medians are +0.0 / -0.3 / +0.2 / -1.4 %. The mean rises with the horizon while the median
does not - the whole gain lives in the right tail. The average winner at 20 days is +13.3 % against an average loser of
-8.3 %, and mean MFE over 20 days is +13.2 % against mean MAE -8.0 %: the average breakout offers you a 13 % gift at
some point and asks you to sit through an 8 % drawdown to get it. Smaller names pay more (small tier: +4.1 % at 20 d,
+7.1 % at 60 d, mean MFE +15.9 %), blue chips pay nothing (+0.4 % at 20 d, -0.2 % after costs).

**The first five days decide the trade.** Split by whether the close ever fell back below the base top in week one:
survivors (277 events) average **+5.1 % at 5 days and +7.1 % at 20**, with 65 % up at 20 days; the 224 that failed
average -3.3 % and -3.2 %, 31 % up. There is no third group. A breakout that has not been given back after a week is a
different animal from one that has.

**B. Akumulasi yang bisa diukur di seluruh panel: tidak ada yang lolos.** Six accumulation proxies over the 60 days of
the base, on 501 LIQ and 1,096 THIN events: every |IC| against the 20-day return is below 0.08 and no permutation p is
below 0.10. Foreign buying is the wrong sign (fgn60 IC -0.047 on LIQ, -0.043 on THIN) - foreigners accumulating during
the base is mildly bad for what follows. The only measure pointing anywhere is **obv60** (up-volume minus down-volume
over the base): IC +0.074 against the 20-day return (p = 0.10) and +0.110 against surviving five days, and its
quartiles do line up - Q1 -> Q4: back inside within 5 days 54 % -> 38 %, still above the top at 20 days 54 % -> 69 %,
up at 20 days 44 % -> 58 %, mean 20-day return -0.1 % -> +4.0 %. That is a 15-point spread on the outcome that matters,
but Q2 and Q3 are out of order and the IC misses the declared bar, so it is a direction to test properly, not a finding.

**C. Akumulasi broker sungguhan: belum bisa dijawab.** Only 42 of 1,096 volume breakouts (25 names) have any stored
broker window closing in the 180 days before the break, and requiring three consecutive windows drops that to 35. At
n = 42 the measures disagree with each other and with the hypothesis - acc_persist IC -0.278 (p 0.07), det_top5 +0.329
(p 0.04), buyers_over_sellers -0.327 (p 0.06) - and with five measures tested at that sample size one p below 0.05 is
what chance produces. The declared split gives accumulated 71 % up at 20 days against 52 % (a +19 pp gap) but on 21
against 21 events with a permutation p of 0.35, and the same split has the accumulated side running +10 % LESS often
(24 % vs 48 %). **UNDERPOWERED as declared: no answer, in either direction.**

**What would answer it.** The data, not the method. Section D shows the free Stockbit feed can give, for any name,
who accumulated over the last month / three months / year - but only ending today. Two ways forward: (1) store that
aggregate every trading day from now, which builds a real panel in 6-12 months and costs ~1 request per name per day;
(2) buy back the historical windows (Stockbit Pro) and rerun this section unchanged - the code already handles the
window shape, it is the same table the 2023-2026 rows sit in. Until then, the honest statement is that the desk has
never tested whether broker accumulation predicts breakout continuation, and the 42 events it can see say nothing.
