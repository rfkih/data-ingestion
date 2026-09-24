# IDX - konsolidasi -> breakout volume: lanjut atau false breakout - 2026-09-24 - descriptive, 0 new trials (cumulative N = 711)

Panel idx.bar 2020-01-02 -> 2026-09-23, 760 names, 1618 trading days. Base = 60 closes ending t-1 inside a <= 25 % channel, |net move| <= 15 %, efficiency ratio <= 0.30; base top = the highest of those 60 closes; breakout = close above it, one event per name per 20 days; volume breakout = volume >= 2 x its 20-day median. 'Back in' = a close back below the base top. All returns from the breakout close on adjusted prices unless marked net.

## 1. Headline - base60, volume >= 2x, by liquidity tier

| cut | events | back in <=3 d | <=5 d | <=20 d | above top @20 d | up @20 d | median 20 d | avg 20 d | ran +10 % | clean run |
|---|---|---|---|---|---|---|---|---|---|---|
| BLUE | 223 | 39 % | 48 % | 65 % | 57 % | 50 % | -0.4 % | +0.4 % | 35 % | 26 % |
| LIQ | 501 | 38 % | 45 % | 65 % | 59 % | 50 % | +0.2 % | +2.5 % | 39 % | 29 % |
| small | 283 | 37 % | 42 % | 65 % | 61 % | 51 % | +0.2 % | +4.1 % | 42 % | 31 % |
| THIN | 1096 | 35 % | 43 % | 64 % | 59 % | 46 % | -0.8 % | +2.4 % | 42 % | 33 % |

| tier | events | net +20 d, next-close fill w/ costs | up after costs | median MFE 20 d | median MAE 20 d | fell >=10 % | median winner | median loser |
|---|---|---|---|---|---|---|---|---|
| BLUE | 223 | -0.2 % | 45 % | +6.5 % | -5.9 % | 31 % | +5.9 % | -8.0 % |
| LIQ | 501 | +1.5 % | 46 % | +7.8 % | -6.5 % | 33 % | +7.1 % | -7.9 % |
| small | 283 | +2.8 % | 46 % | +8.3 % | -6.8 % | 34 % | +7.2 % | -7.5 % |
| THIN | 1096 | +1.3 % | 43 % | +8.2 % | -6.9 % | 33 % | +7.1 % | -6.0 % |

### Survival of the break - share of events whose close is still above the base top on day k

| tier | d1 | d3 | d5 | d10 | d20 | 95 % band on 'back inside <=5 d' | 95 % band on 'up at 20 d' |
|---|---|---|---|---|---|---|---|
| BLUE | 77 % | 69 % | 68 % | 63 % | 57 % | 42 % - 55 % | 43 % - 56 % |
| LIQ | 81 % | 70 % | 69 % | 64 % | 59 % | 40 % - 49 % | 46 % - 54 % |
| small | 84 % | 72 % | 70 % | 65 % | 61 % | 37 % - 48 % | 45 % - 56 % |
| THIN | 82 % | 73 % | 71 % | 65 % | 59 % | 40 % - 46 % | 43 % - 49 % |

## 2. Does the count depend on how a base is defined? (LIQ, volume >= 2x)

| cut | events | back in <=3 d | <=5 d | <=20 d | above top @20 d | up @20 d | median 20 d | avg 20 d | ran +10 % | clean run |
|---|---|---|---|---|---|---|---|---|---|---|
| base60 | 501 | 38 % | 45 % | 65 % | 59 % | 50 % | +0.2 % | +2.5 % | 39 % | 29 % |
| base120 | 150 | 41 % | 48 % | 65 % | 59 % | 51 % | +0.3 % | +0.3 % | 35 % | 27 % |
| base20 | 1089 | 35 % | 44 % | 68 % | 57 % | 44 % | -1.0 % | +1.4 % | 38 % | 28 % |
| tight60 | 207 | 35 % | 42 % | 64 % | 61 % | 53 % | +0.7 % | +3.1 % | 30 % | 22 % |
| loose60 | 683 | 39 % | 45 % | 65 % | 59 % | 49 % | +0.0 % | +3.3 % | 43 % | 32 % |

## 3. How much volume? (base60, every break of the base sliced by volume ratio)

**LIQ**

| cut | events | back in <=3 d | <=5 d | <=20 d | above top @20 d | up @20 d | median 20 d | avg 20 d | ran +10 % | clean run |
|---|---|---|---|---|---|---|---|---|---|---|
| vr<1 | 87 | 62 % | 69 % | 89 % | 37 % | 32 % | -3.8 % | -3.1 % | 18 % | 11 % |
| 1-1.5 | 135 | 44 % | 53 % | 70 % | 59 % | 53 % | +0.6 % | +3.5 % | 39 % | 27 % |
| 1.5-2 | 120 | 48 % | 59 % | 82 % | 54 % | 47 % | -0.7 % | +1.3 % | 28 % | 15 % |
| 2-3 | 169 | 46 % | 54 % | 70 % | 60 % | 51 % | +0.3 % | +2.5 % | 32 % | 20 % |
| 3-5 | 158 | 36 % | 43 % | 66 % | 59 % | 49 % | -0.2 % | +0.7 % | 35 % | 27 % |
| 5+ | 174 | 32 % | 37 % | 59 % | 59 % | 50 % | +0.3 % | +4.2 % | 49 % | 40 % |

**small**

| cut | events | back in <=3 d | <=5 d | <=20 d | above top @20 d | up @20 d | median 20 d | avg 20 d | ran +10 % | clean run |
|---|---|---|---|---|---|---|---|---|---|---|
| vr<1 | 52 | 56 % | 63 % | 83 % | 40 % | 35 % | -4.2 % | -2.2 % | 25 % | 19 % |
| 1-1.5 | 77 | 39 % | 49 % | 65 % | 60 % | 52 % | +0.6 % | +5.7 % | 44 % | 30 % |
| 1.5-2 | 69 | 46 % | 54 % | 80 % | 58 % | 49 % | +0.0 % | +2.7 % | 36 % | 17 % |
| 2-3 | 80 | 48 % | 52 % | 70 % | 64 % | 54 % | +1.2 % | +5.3 % | 39 % | 22 % |
| 3-5 | 72 | 35 % | 43 % | 71 % | 56 % | 44 % | -1.2 % | -0.2 % | 29 % | 24 % |
| 5+ | 131 | 32 % | 36 % | 58 % | 62 % | 52 % | +0.7 % | +5.8 % | 51 % | 40 % |

**THIN**

| cut | events | back in <=3 d | <=5 d | <=20 d | above top @20 d | up @20 d | median 20 d | avg 20 d | ran +10 % | clean run |
|---|---|---|---|---|---|---|---|---|---|---|
| vr<1 | 145 | 54 % | 61 % | 79 % | 48 % | 41 % | -1.5 % | +2.1 % | 26 % | 18 % |
| 1-1.5 | 242 | 43 % | 52 % | 73 % | 60 % | 50 % | +0.2 % | +2.8 % | 34 % | 21 % |
| 1.5-2 | 198 | 42 % | 55 % | 75 % | 56 % | 47 % | -0.6 % | +1.2 % | 26 % | 15 % |
| 2-3 | 267 | 42 % | 48 % | 67 % | 58 % | 49 % | +0.0 % | +3.7 % | 35 % | 25 % |
| 3-5 | 317 | 36 % | 44 % | 66 % | 61 % | 50 % | +0.0 % | +2.2 % | 38 % | 29 % |
| 5+ | 512 | 31 % | 39 % | 62 % | 59 % | 42 % | -1.9 % | +2.0 % | 48 % | 39 % |

## 4. How big was the breakout day itself? (LIQ, volume >= 2x)

| cut | events | back in <=3 d | <=5 d | <=20 d | above top @20 d | up @20 d | median 20 d | avg 20 d | ran +10 % | clean run |
|---|---|---|---|---|---|---|---|---|---|---|
| <2 % | 53 | 47 % | 49 % | 68 % | 68 % | 62 % | +1.6 % | +2.2 % | 34 % | 17 % |
| 2-5 % | 200 | 44 % | 50 % | 67 % | 60 % | 52 % | +0.4 % | +0.6 % | 33 % | 24 % |
| 5-10 % | 176 | 34 % | 42 % | 66 % | 56 % | 47 % | -0.8 % | +2.5 % | 39 % | 30 % |
| 10-20 % | 57 | 32 % | 37 % | 56 % | 54 % | 39 % | -5.0 % | +7.8 % | 53 % | 44 % |
| 20 %+ | 15 | 7 % | 13 % | 40 % | 67 % | 60 % | +3.7 % | +9.3 % | 80 % | 73 % |

## 5. Index regime and year (LIQ, volume >= 2x)

| cut | events | back in <=3 d | <=5 d | <=20 d | above top @20 d | up @20 d | median 20 d | avg 20 d | ran +10 % | clean run |
|---|---|---|---|---|---|---|---|---|---|---|
| COMPOSITE >= MA200 | 387 | 39 % | 45 % | 65 % | 58 % | 48 % | -0.4 % | +2.2 % | 40 % | 29 % |
| COMPOSITE < MA200 | 114 | 34 % | 43 % | 63 % | 62 % | 57 % | +0.8 % | +3.4 % | 34 % | 28 % |
| 2020 | 44 | 32 % | 32 % | 50 % | 80 % | 73 % | +5.9 % | +14.7 % | 55 % | 39 % |
| 2021 | 68 | 40 % | 41 % | 56 % | 63 % | 50 % | +0.1 % | +6.8 % | 54 % | 43 % |
| 2022 | 93 | 25 % | 39 % | 65 % | 57 % | 49 % | -0.7 % | -0.9 % | 31 % | 27 % |
| 2023 | 80 | 40 % | 46 % | 71 % | 50 % | 41 % | -1.6 % | -0.4 % | 32 % | 28 % |
| 2024 | 94 | 47 % | 50 % | 66 % | 65 % | 54 % | +1.4 % | +1.1 % | 36 % | 21 % |
| 2025 | 79 | 35 % | 46 % | 67 % | 57 % | 47 % | -1.1 % | +3.6 % | 41 % | 28 % |
| 2026 | 43 | 53 % | 60 % | 74 % | 44 % | 42 % | -3.7 % | -2.7 % | 30 % | 21 % |

## 6. Controls (LIQ, same days)

The two sampled controls have no base top to fall back through, so the level columns read n/a; compare them on the return and run columns.

| cut | events | back in <=3 d | <=5 d | <=20 d | above top @20 d | up @20 d | median 20 d | avg 20 d | ran +10 % | clean run |
|---|---|---|---|---|---|---|---|---|---|---|
| volume break (vr>=2) | 501 | 38 % | 45 % | 65 % | 59 % | 50 % | +0.2 % | +2.5 % | 39 % | 29 % |
| no volume (vr<1) | 87 | 62 % | 69 % | 89 % | 37 % | 32 % | -3.8 % | -3.1 % | 18 % | 11 % |
| inside base, no break | 2358 | n/a | n/a | n/a | n/a | 45 % | -0.7 % | +1.1 % | 26 % | n/a |
| random LIQ name | 2358 | n/a | n/a | n/a | n/a | 46 % | -0.8 % | +1.1 % | 39 % | n/a |

## 7. The last 15 volume breakouts in LIQ

| date | code | vol x | day return | 20-day return | back below top on day | MFE 20 d |
|---|---|---|---|---|---|---|
| 2026-09-09 | BDMN | 4.2 | +2.9 % | - | 1 | +0.7 % |
| 2026-09-09 | ANTM | 2.2 | +3.9 % | - | 8 | +4.7 % |
| 2026-09-03 | PTBA | 10.6 | +6.2 % | - | not yet | +10.7 % |
| 2026-09-01 | SMGR | 8.4 | +16.9 % | - | 10 | +6.4 % |
| 2026-08-31 | NCKL | 2.1 | +1.6 % | - | 1 | +4.6 % |
| 2026-08-31 | CMRY | 4.4 | +3.0 % | - | 2 | +0.2 % |
| 2026-08-24 | SSIA | 5.3 | +7.0 % | -15.8 % | 1 | +4.2 % |
| 2026-08-24 | ADRO | 2.3 | +3.1 % | +0.4 % | not yet | +8.7 % |
| 2026-08-21 | BBRI | 2.0 | +2.9 % | +2.8 % | 2 | +6.5 % |
| 2026-08-18 | DMAS | 14.9 | +8.1 % | +16.8 % | not yet | +32.9 % |
| 2026-08-03 | MAPA | 6.1 | +3.8 % | +3.0 % | 6 | +8.1 % |
| 2026-08-03 | ICBP | 2.7 | +3.2 % | +2.4 % | not yet | +11.1 % |
| 2026-06-19 | MYOR | 3.8 | +14.0 % | -12.1 % | 1 | -2.0 % |
| 2026-05-12 | MARK | 3.1 | +2.9 % | +0.6 % | 2 | +4.0 % |
| 2026-04-29 | ULTJ | 6.8 | +5.0 % | -15.9 % | 2 | +1.8 % |

## Reading (written after the run)

**The short answer, on 501 liquid (>= Rp 5 bn/day) breaks of a 60-day base on at least twice the normal volume, 2020-2026:**

| what happened within 20 trading days | share |
|---|---|
| closed back inside the base within 3 days (the textbook false breakout) | 38 % |
| closed back inside the base within 5 days | 45 % |
| closed back inside the base at some point within 20 days | 65 % |
| never went back inside at all | 35 % |
| still above the base top after 20 days | 59 % |
| higher than the breakout close after 20 days | 50 % |
| its high reached +10 % within 20 days | 39 % |
| reached +10 % BEFORE ever closing back inside | 29 % |

1. **False breakout is the majority outcome, not the exception.** Nearly half (45 %, 95 % band 40-49 %) close back inside
   the base within a week and two thirds do within a month. One break in three never goes back in. The survival curve
   falls fastest on the first three days (81 % -> 70 %) and then flattens: whatever is going to fail mostly fails
   immediately.

2. **"Continues to rise" is a coin flip, with a positive tail.** 50 % are higher 20 days after the breakout close
   (band 46-54 %), median +0.2 %, mean +2.5 %. The typical winner and the typical loser are the same size (median
   winner +7.1 %, median loser -7.9 %), so the positive mean comes entirely from a thin tail of large runners.
   39 % touch +10 % at some point; only 29 % do it without first falling back into the base.

3. **Volume is a filter against the worst, not a predictor of the best.** On the same bases, a break on BELOW-median
   volume (vr < 1, n = 87) fails 62 % within 3 days and 89 % within 20, is up 32 % of the time and runs +10 % only
   18 %. At vr >= 5 (n = 173) failure falls to 32 % / 58 % and the run rate doubles to 50 %. But between vr 1.5 and 3
   there is no gradient at all (the 1.5-2 bucket is the worst of the lot, 59 % back inside in 5 days) - the signal is
   "conviction volume or nothing", not a smooth dial.

4. **The breakout does not beat the market, only the other consolidating names.** Matched on the same days: a random
   liquid name runs +10 % within 20 days 39 % of the time - exactly the breakout rate - and has the same +1.1 % mean
   20-day return. A consolidating name that did NOT break that day runs +10 % only 26 % of the time. So the volume
   break tells you which sleepy name has woken up; it does not tell you that you have found something better than an
   average liquid stock.

5. **After costs and a realistic fill, it is close to nothing.** Buying the NEXT close at the offer and selling 20 days
   later at the bid (the desk cost model, 0.10 / 0.20 % fees): +1.5 % average, 46 % of trades positive on LIQ, -0.2 %
   on BLUE, +2.8 % on the small tier. This matches what the trading version of the rule earned when it was tested as
   a book: menu 27 study #69, base_break +7.9 %/yr Sharpe 0.71 on LIQ and +9.4 % / 0.89 on small, against the deployed
   60-day-high trend rule's +19 % / +29.5 %.

6. **The counts are stable in every direction except time.** Five different definitions of a base (20 / 60 / 120 days,
   tight 15 % channel, loose 35 %) all give 42-48 % back inside within 5 days and 27-31 % clean runs; the four
   liquidity tiers agree to within 5 points. What does move is the year: 2020-21 were kind (73 % / 50 % up at 20 d,
   mean +14.7 % / +6.8 %), 2022-25 flat (-0.9 to +3.6 %), and 2026 so far is the worst year in the panel - 61 % back
   inside within 5 days, median -3.7 %. The index regime barely matters (48 % up above MA200, 57 % below, n = 112).

7. **The size of the breakout day cuts both ways.** Breaks that jump 10-20 % fail least often (37 % back inside in 5
   days) and run most often (53 %), but their median 20-day return is -5.0 % - you pay for the gap. The 15 breaks that
   moved 20 %+ on the day almost never came back (13 %) and 80 % ran +10 %, but 15 events is a curiosity, not a fact.

**What this means for the desk.** Nothing here reopens the family: the statistic is consistent with menu 26/27 having
closed it. It does put numbers on the shape of the trade the deployed trend books already take - roughly half the
entries are wrong within a week, so the 10 % trail and the -10 % broker safety net are sized about right, and any plan
to "buy the breakout and wait for confirmation" is buying the 65 % that come back. The one cut with a real gradient
(conviction volume >= 5x) is worth remembering as a filter on the existing trend signal, not as a new book.

**Limits.** Descriptive counts, 2020-2026 only (the desk panel starts 2020); no new money-rule trials, so nothing here
is a tested rule. Events in the last 20 sessions are excluded from every count (no complete forward window) but are
shown in section 8. Returns use adjusted closes; the intraday high/low columns use IDX bars, so an ARA-locked day
counts as a touch even when nobody could buy it.

## 8. Live screen on 2026-09-23

**Broke out of a 60-day base on >= 2x volume in the last 15 sessions (8 names)**

| date | code | tier | sector | vol x | day return | since the break | back inside on day | still above the top |
|---|---|---|---|---|---|---|---|---|
| 2026-09-22 | DFAM | THIN | None | 21.3 | +19.6 % | -14.5 % | - | yes |
| 2026-09-16 | VISI | THIN | C. Industrials | 10.9 | +24.9 % | +4.0 % | - | yes |
| 2026-09-14 | ULTJ | THIN | D. Consumer Non-Cyclicals | 7.9 | +13.6 % | +10.8 % | - | yes |
| 2026-09-11 | MBSS | THIN | A. Energy | 2.1 | +0.3 % | +0.3 % | - | yes |
| 2026-09-09 | ANTM | LIQ | B. Basic Materials | 2.2 | +3.9 % | +0.7 % | 8 | yes |
| 2026-09-09 | BDMN | LIQ | G. Financials | 4.2 | +2.9 % | -1.3 % | 1 | no |
| 2026-09-07 | BTPS | THIN | G. Financials | 4.9 | +4.4 % | -3.4 % | 4 | no |
| 2026-09-03 | PTBA | LIQ | A. Energy | 10.6 | +6.2 % | +7.2 % | - | yes |

**Inside a 60-day base right now: 38 LIQ names (45 more THIN) - the 25 closest to their base top**

| code | tier | sector | close | base top | to the top | channel width | days in base | Rp bn/day | volume today x |
|---|---|---|---|---|---|---|---|---|---|
| MBSS | THIN | A. Energy | 2,900 | 2,910 | +0.3 % | 16 % | 10 | 2.5 | 0.3 |
| JRPT | THIN | None | 1,150 | 1,155 | +0.4 % | 5 % | 127 | 0.6 | 2.3 |
| LPPF | THIN | E. Consumer Cyclicals | 1,560 | 1,580 | +1.3 % | 14 % | 39 | 1.8 | 1.4 |
| BDMN | LIQ | G. Financials | 4,440 | 4,499 | +1.3 % | 22 % | 9 | 6.8 | 0.8 |
| MGRO | THIN | D. Consumer Non-Cyclicals | 700 | 710 | +1.4 % | 9 % | 305 | 2.7 | 1.0 |
| BJBR | THIN | G. Financials | 765 | 779 | +1.8 % | 9 % | 31 | 1.4 | 1.3 |
| MSTI | THIN | I. Technology | 1,385 | 1,411 | +1.8 % | 18 % | 9 | 1.3 | 1.2 |
| CLEO | THIN | D. Consumer Non-Cyclicals | 416 | 424 | +1.9 % | 18 % | 2 | 3.0 | 0.9 |
| BJTM | THIN | G. Financials | 520 | 530 | +1.9 % | 5 % | 72 | 2.7 | 1.0 |
| BNGA | THIN | G. Financials | 1,760 | 1,796 | +2.0 % | 17 % | 2 | 3.4 | 1.4 |
| JTPE | THIN | C. Industrials | 595 | 609 | +2.4 % | 7 % | 96 | 0.6 | 0.8 |
| RALS | THIN | E. Consumer Cyclicals | 384 | 394 | +2.6 % | 8 % | 22 | 0.9 | 0.4 |
| PNBN | THIN | G. Financials | 865 | 888 | +2.7 % | 8 % | 30 | 1.9 | 1.1 |
| NISP | THIN | G. Financials | 1,265 | 1,300 | +2.8 % | 12 % | 40 | 3.0 | 0.3 |
| MPMX | THIN | E. Consumer Cyclicals | 1,025 | 1,055 | +2.9 % | 12 % | 9 | 2.6 | 0.5 |
| MTDL | THIN | I. Technology | 500 | 516 | +3.1 % | 5 % | 40 | 0.9 | 0.3 |
| ASRI | THIN | H. Properties & Real Estate | 126 | 130 | +3.1 % | 25 % | 8 | 1.0 | 0.9 |
| MKPI | THIN | H. Properties & Real Estate | 21,475 | 22,175 | +3.3 % | 8 % | 350 | 0.9 | 1.0 |
| ACES | LIQ | E. Consumer Cyclicals | 348 | 360 | +3.4 % | 12 % | 31 | 5.3 | 0.7 |
| DRMA | THIN | E. Consumer Cyclicals | 970 | 1,004 | +3.5 % | 23 % | 38 | 0.5 | 0.4 |
| BSML | LIQ | A. Energy | 540 | 560 | +3.7 % | 15 % | 2 | 7.0 | 0.3 |
| CFIN | THIN | G. Financials | 364 | 378 | +3.8 % | 20 % | 9 | 0.7 | 0.2 |
| BIRD | THIN | K. Transportation & Logistic | 1,595 | 1,660 | +4.1 % | 12 % | 13 | 1.1 | 0.3 |
| BTPS | THIN | G. Financials | 970 | 1,013 | +4.4 % | 12 % | 11 | 2.2 | 1.6 |
| BMRI | LIQ | G. Financials | 4,190 | 4,387 | +4.7 % | 18 % | 13 | 545.3 | 0.7 |
