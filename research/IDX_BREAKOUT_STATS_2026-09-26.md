# IDX - konsolidasi -> breakout volume: lanjut atau false breakout - 2026-09-26 - descriptive, 0 new trials (cumulative N = 711)

Panel idx.bar 2020-01-02 -> 2026-09-25, 989 names, 1620 trading days. Base = 60 closes ending t-1 inside a <= 25 % channel, |net move| <= 15 %, efficiency ratio <= 0.30; base top = the highest of those 60 closes; breakout = close above it, one event per name per 20 days; volume breakout = volume >= 2 x its 20-day median. 'Back in' = a close back below the base top. All returns from the breakout close on adjusted prices unless marked net.

## 1. Headline - base60, volume >= 2x, by liquidity tier

| cut | events | back in <=3 d | <=5 d | <=20 d | above top @20 d | up @20 d | median 20 d | avg 20 d | ran +10 % | clean run |
|---|---|---|---|---|---|---|---|---|---|---|
| BLUE | 223 | 39 % | 48 % | 65 % | 57 % | 49 % | -0.4 % | +0.4 % | 35 % | 26 % |
| LIQ | 506 | 38 % | 44 % | 65 % | 59 % | 50 % | +0.0 % | +2.5 % | 39 % | 29 % |
| small | 288 | 36 % | 42 % | 65 % | 61 % | 50 % | +0.2 % | +4.0 % | 43 % | 32 % |
| THIN | 1124 | 35 % | 43 % | 64 % | 59 % | 46 % | -0.8 % | +2.4 % | 43 % | 33 % |

| tier | events | net +20 d, next-close fill w/ costs | up after costs | median MFE 20 d | median MAE 20 d | fell >=10 % | median winner | median loser |
|---|---|---|---|---|---|---|---|---|
| BLUE | 223 | -0.2 % | 45 % | +6.5 % | -5.9 % | 31 % | +6.2 % | -8.0 % |
| LIQ | 506 | +1.4 % | 45 % | +7.8 % | -6.5 % | 32 % | +7.1 % | -7.7 % |
| small | 288 | +2.6 % | 46 % | +8.3 % | -6.8 % | 34 % | +7.2 % | -7.4 % |
| THIN | 1124 | +1.3 % | 42 % | +8.2 % | -6.9 % | 33 % | +7.2 % | -6.0 % |

### Survival of the break - share of events whose close is still above the base top on day k

| tier | d1 | d3 | d5 | d10 | d20 | 95 % band on 'back inside <=5 d' | 95 % band on 'up at 20 d' |
|---|---|---|---|---|---|---|---|
| BLUE | 77 % | 69 % | 68 % | 63 % | 57 % | 42 % - 55 % | 43 % - 56 % |
| LIQ | 81 % | 71 % | 70 % | 64 % | 59 % | 40 % - 49 % | 45 % - 54 % |
| small | 85 % | 72 % | 71 % | 65 % | 61 % | 36 % - 47 % | 45 % - 56 % |
| THIN | 82 % | 73 % | 71 % | 65 % | 59 % | 40 % - 46 % | 43 % - 49 % |

## 2. Does the count depend on how a base is defined? (LIQ, volume >= 2x)

| cut | events | back in <=3 d | <=5 d | <=20 d | above top @20 d | up @20 d | median 20 d | avg 20 d | ran +10 % | clean run |
|---|---|---|---|---|---|---|---|---|---|---|
| base60 | 506 | 38 % | 44 % | 65 % | 59 % | 50 % | +0.0 % | +2.5 % | 39 % | 29 % |
| base120 | 150 | 41 % | 48 % | 65 % | 59 % | 51 % | +0.3 % | +0.3 % | 35 % | 27 % |
| base20 | 1115 | 36 % | 44 % | 68 % | 57 % | 44 % | -1.0 % | +1.4 % | 38 % | 27 % |
| tight60 | 209 | 35 % | 41 % | 65 % | 61 % | 52 % | +0.7 % | +3.1 % | 31 % | 22 % |
| loose60 | 694 | 38 % | 45 % | 65 % | 59 % | 49 % | -0.4 % | +3.3 % | 44 % | 32 % |

## 3. How much volume? (base60, every break of the base sliced by volume ratio)

**LIQ**

| cut | events | back in <=3 d | <=5 d | <=20 d | above top @20 d | up @20 d | median 20 d | avg 20 d | ran +10 % | clean run |
|---|---|---|---|---|---|---|---|---|---|---|
| vr<1 | 88 | 62 % | 69 % | 89 % | 36 % | 32 % | -4.1 % | -3.1 % | 18 % | 11 % |
| 1-1.5 | 138 | 45 % | 54 % | 70 % | 58 % | 52 % | +0.6 % | +3.3 % | 39 % | 26 % |
| 1.5-2 | 121 | 47 % | 59 % | 83 % | 54 % | 46 % | -0.7 % | +1.0 % | 29 % | 16 % |
| 2-3 | 170 | 46 % | 54 % | 70 % | 59 % | 51 % | +0.2 % | +2.4 % | 32 % | 20 % |
| 3-5 | 159 | 36 % | 43 % | 65 % | 59 % | 49 % | +0.0 % | +0.7 % | 35 % | 27 % |
| 5+ | 177 | 32 % | 37 % | 59 % | 59 % | 50 % | +0.0 % | +4.1 % | 50 % | 40 % |

**small**

| cut | events | back in <=3 d | <=5 d | <=20 d | above top @20 d | up @20 d | median 20 d | avg 20 d | ran +10 % | clean run |
|---|---|---|---|---|---|---|---|---|---|---|
| vr<1 | 53 | 57 % | 64 % | 83 % | 40 % | 34 % | -4.5 % | -2.4 % | 25 % | 19 % |
| 1-1.5 | 80 | 40 % | 51 % | 66 % | 59 % | 51 % | +0.5 % | +5.2 % | 42 % | 29 % |
| 1.5-2 | 70 | 46 % | 53 % | 80 % | 57 % | 49 % | -0.3 % | +2.2 % | 37 % | 19 % |
| 2-3 | 81 | 47 % | 52 % | 70 % | 63 % | 53 % | +1.0 % | +5.2 % | 40 % | 23 % |
| 3-5 | 73 | 34 % | 42 % | 70 % | 56 % | 45 % | -1.1 % | -0.2 % | 30 % | 25 % |
| 5+ | 134 | 31 % | 35 % | 58 % | 62 % | 51 % | +0.7 % | +5.6 % | 51 % | 40 % |

**THIN**

| cut | events | back in <=3 d | <=5 d | <=20 d | above top @20 d | up @20 d | median 20 d | avg 20 d | ran +10 % | clean run |
|---|---|---|---|---|---|---|---|---|---|---|
| vr<1 | 149 | 54 % | 62 % | 79 % | 47 % | 40 % | -1.5 % | +2.0 % | 26 % | 18 % |
| 1-1.5 | 250 | 44 % | 53 % | 73 % | 59 % | 50 % | +0.1 % | +2.6 % | 35 % | 21 % |
| 1.5-2 | 209 | 42 % | 54 % | 74 % | 56 % | 48 % | -0.4 % | +1.4 % | 28 % | 17 % |
| 2-3 | 272 | 42 % | 48 % | 67 % | 58 % | 49 % | +0.0 % | +3.8 % | 36 % | 25 % |
| 3-5 | 324 | 36 % | 44 % | 65 % | 60 % | 49 % | +0.0 % | +2.0 % | 39 % | 30 % |
| 5+ | 528 | 31 % | 39 % | 61 % | 59 % | 42 % | -1.9 % | +2.0 % | 48 % | 39 % |

## 4. How big was the breakout day itself? (LIQ, volume >= 2x)

| cut | events | back in <=3 d | <=5 d | <=20 d | above top @20 d | up @20 d | median 20 d | avg 20 d | ran +10 % | clean run |
|---|---|---|---|---|---|---|---|---|---|---|
| <2 % | 52 | 46 % | 48 % | 67 % | 67 % | 62 % | +2.0 % | +2.2 % | 33 % | 17 % |
| 2-5 % | 201 | 44 % | 51 % | 67 % | 60 % | 52 % | +0.5 % | +0.6 % | 33 % | 23 % |
| 5-10 % | 178 | 34 % | 42 % | 66 % | 56 % | 46 % | -0.8 % | +2.4 % | 39 % | 30 % |
| 10-20 % | 59 | 31 % | 36 % | 54 % | 56 % | 41 % | -4.7 % | +8.0 % | 54 % | 46 % |
| 20 %+ | 16 | 6 % | 12 % | 44 % | 62 % | 56 % | +3.2 % | +6.9 % | 81 % | 75 % |

## 5. Index regime and year (LIQ, volume >= 2x)

| cut | events | back in <=3 d | <=5 d | <=20 d | above top @20 d | up @20 d | median 20 d | avg 20 d | ran +10 % | clean run |
|---|---|---|---|---|---|---|---|---|---|---|
| COMPOSITE >= MA200 | 391 | 39 % | 45 % | 65 % | 58 % | 48 % | -0.4 % | +2.3 % | 41 % | 29 % |
| COMPOSITE < MA200 | 115 | 34 % | 43 % | 63 % | 62 % | 56 % | +0.8 % | +3.1 % | 35 % | 29 % |
| 2020 | 46 | 30 % | 30 % | 50 % | 78 % | 72 % | +5.9 % | +14.0 % | 57 % | 41 % |
| 2021 | 70 | 39 % | 40 % | 56 % | 63 % | 50 % | +0.1 % | +6.5 % | 56 % | 44 % |
| 2022 | 94 | 24 % | 38 % | 65 % | 57 % | 49 % | -0.8 % | -0.9 % | 31 % | 27 % |
| 2023 | 80 | 40 % | 46 % | 71 % | 50 % | 41 % | -1.6 % | -0.4 % | 32 % | 28 % |
| 2024 | 94 | 47 % | 50 % | 66 % | 65 % | 54 % | +1.4 % | +1.1 % | 36 % | 21 % |
| 2025 | 79 | 35 % | 46 % | 67 % | 57 % | 47 % | -1.1 % | +3.6 % | 41 % | 28 % |
| 2026 | 43 | 53 % | 60 % | 74 % | 44 % | 40 % | -3.7 % | -2.8 % | 30 % | 21 % |

## 6. Controls (LIQ, same days)

The two sampled controls have no base top to fall back through, so the level columns read n/a; compare them on the return and run columns.

| cut | events | back in <=3 d | <=5 d | <=20 d | above top @20 d | up @20 d | median 20 d | avg 20 d | ran +10 % | clean run |
|---|---|---|---|---|---|---|---|---|---|---|
| volume break (vr>=2) | 506 | 38 % | 44 % | 65 % | 59 % | 50 % | +0.0 % | +2.5 % | 39 % | 29 % |
| no volume (vr<1) | 88 | 62 % | 69 % | 89 % | 36 % | 32 % | -4.1 % | -3.1 % | 18 % | 11 % |
| inside base, no break | 2382 | n/a | n/a | n/a | n/a | 46 % | -0.5 % | +0.8 % | 26 % | n/a |
| random LIQ name | 2382 | n/a | n/a | n/a | n/a | 43 % | -1.4 % | +0.4 % | 37 % | n/a |

## 7. The last 15 volume breakouts in LIQ

| date | code | vol x | day return | 20-day return | back below top on day | MFE 20 d |
|---|---|---|---|---|---|---|
| 2026-09-09 | BDMN | 4.2 | +2.9 % | - | 1 | +0.7 % |
| 2026-09-09 | ANTM | 2.2 | +3.9 % | - | 9 | +5.3 % |
| 2026-09-03 | PTBA | 10.6 | +6.2 % | - | not yet | +10.7 % |
| 2026-09-01 | SMGR | 8.4 | +16.9 % | - | 10 | +6.4 % |
| 2026-08-31 | NCKL | 2.1 | +1.6 % | - | 1 | +4.6 % |
| 2026-08-31 | CMRY | 4.4 | +3.0 % | - | 2 | +0.2 % |
| 2026-08-24 | SSIA | 5.3 | +7.0 % | -15.8 % | 1 | +4.2 % |
| 2026-08-24 | ADRO | 2.3 | +3.1 % | -0.8 % | not yet | +8.7 % |
| 2026-08-21 | BBRI | 2.0 | +2.9 % | +2.2 % | 2 | +6.5 % |
| 2026-08-18 | DMAS | 14.9 | +8.1 % | +16.8 % | not yet | +32.9 % |
| 2026-08-03 | MAPA | 6.1 | +3.8 % | +3.0 % | 6 | +8.1 % |
| 2026-08-03 | ICBP | 2.7 | +3.2 % | +2.4 % | not yet | +11.1 % |
| 2026-06-19 | MYOR | 3.8 | +14.0 % | -12.1 % | 1 | -2.0 % |
| 2026-05-12 | MARK | 3.1 | +2.9 % | +0.6 % | 2 | +4.0 % |
| 2026-04-29 | ULTJ | 6.8 | +5.0 % | -15.9 % | 2 | +1.8 % |

## 8. Live screen on 2026-09-25

**Broke out of a 60-day base on >= 2x volume in the last 15 sessions (7 names)**

| date | code | tier | sector | vol x | day return | since the break | back inside on day | still above the top |
|---|---|---|---|---|---|---|---|---|
| 2026-09-22 | DFAM | THIN | 9. Trade, Services & Investment | 21.3 | +19.6 % | -19.1 % | 1 | no |
| 2026-09-16 | VISI | THIN | C. Industrials | 10.9 | +24.9 % | +8.6 % | - | yes |
| 2026-09-14 | ULTJ | THIN | D. Consumer Non-Cyclicals | 7.9 | +13.6 % | +20.1 % | - | yes |
| 2026-09-11 | MBSS | THIN | A. Energy | 2.1 | +0.3 % | +0.0 % | - | yes |
| 2026-09-09 | ANTM | LIQ | B. Basic Materials | 2.2 | +3.9 % | +0.9 % | 9 | yes |
| 2026-09-09 | BDMN | LIQ | G. Financials | 4.2 | +2.9 % | -3.1 % | 1 | no |
| 2026-09-07 | BTPS | THIN | G. Financials | 4.9 | +4.4 % | -9.4 % | 4 | no |

**Inside a 60-day base right now: 39 LIQ names (45 more THIN) - the 25 closest to their base top**

| code | tier | sector | close | base top | to the top | channel width | days in base | Rp bn/day | volume today x |
|---|---|---|---|---|---|---|---|---|---|
| DAAZ | THIN | B. Basic Materials | 1,790 | 1,790 | +0.0 % | 23 % | 6 | 0.5 | 4.8 |
| BNGA | THIN | G. Financials | 1,740 | 1,765 | +1.4 % | 17 % | 1 | 3.4 | 0.5 |
| MGRO | THIN | D. Consumer Non-Cyclicals | 695 | 710 | +2.2 % | 9 % | 307 | 2.7 | 0.9 |
| BSML | LIQ | A. Energy | 540 | 555 | +2.8 % | 14 % | 4 | 7.0 | 0.4 |
| NISP | THIN | G. Financials | 1,255 | 1,290 | +2.8 % | 12 % | 42 | 3.1 | 1.1 |
| MKPI | THIN | H. Properties & Real Estate | 21,525 | 22,175 | +3.0 % | 8 % | 352 | 0.9 | 1.0 |
| RALS | THIN | E. Consumer Cyclicals | 382 | 394 | +3.1 % | 7 % | 24 | 0.8 | 0.8 |
| MPMX | THIN | E. Consumer Cyclicals | 1,020 | 1,055 | +3.4 % | 10 % | 11 | 2.6 | 0.5 |
| MSTI | THIN | I. Technology | 1,345 | 1,395 | +3.7 % | 18 % | 1 | 1.3 | 0.6 |
| BJTM | THIN | G. Financials | 510 | 530 | +3.9 % | 5 % | 74 | 2.6 | 1.0 |
| TBIG | THIN | J. Infrastructures | 1,465 | 1,530 | +4.4 % | 14 % | 30 | 0.6 | 0.4 |
| LPPF | THIN | E. Consumer Cyclicals | 1,585 | 1,660 | +4.7 % | 13 % | 41 | 1.8 | 0.9 |
| ITMG | LIQ | A. Energy | 25,500 | 26,750 | +4.9 % | 20 % | 3 | 31.8 | 0.3 |
| JTPE | THIN | C. Industrials | 595 | 625 | +5.0 % | 7 % | 98 | 0.6 | 1.8 |
| PWON | LIQ | H. Properties & Real Estate | 266 | 280 | +5.3 % | 17 % | 26 | 9.3 | 0.6 |
| MTDL | THIN | I. Technology | 498 | 525 | +5.4 % | 6 % | 42 | 0.9 | 1.2 |
| CFIN | THIN | G. Financials | 358 | 378 | +5.6 % | 20 % | 11 | 0.6 | 0.3 |
| BIRD | THIN | K. Transportation & Logistic | 1,570 | 1,660 | +5.7 % | 12 % | 15 | 1.1 | 0.6 |
| ACES | LIQ | E. Consumer Cyclicals | 342 | 362 | +5.8 % | 12 % | 33 | 5.1 | 0.4 |
| CLEO | THIN | D. Consumer Non-Cyclicals | 408 | 434 | +6.4 % | 16 % | 13 | 3.1 | 0.8 |
| TBLA | THIN | D. Consumer Non-Cyclicals | 610 | 650 | +6.6 % | 7 % | 15 | 0.8 | 0.9 |
| BJBR | THIN | G. Financials | 755 | 805 | +6.6 % | 7 % | 33 | 1.4 | 1.0 |
| SMSM | THIN | E. Consumer Cyclicals | 1,685 | 1,800 | +6.8 % | 13 % | 399 | 3.2 | 0.5 |
| SNLK | THIN | E. Consumer Cyclicals | 240 | 258 | +7.5 % | 19 % | 45 | 3.2 | 1.0 |
| BDKR | THIN | J. Infrastructures | 159 | 171 | +7.5 % | 22 % | 2 | 1.6 | 1.2 |
