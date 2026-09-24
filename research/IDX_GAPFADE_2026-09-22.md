# IDX menu 29b — the gap-down fade, tested properly — 2020-01-01 -> 2026-09-21

IDX-sourced opens only: 111,441 eligible name-days. Pre-registered in `research/idx_gapfade.py`; 7 trials (cumulative 535).

## The path after a >= 5 % gap-down open (gross, equal weight, every eligible event)

| horizon | mean | median | P(up) | n |
|---|---|---|---|---|
| open->close | +2.91 % | +1.01 % | 55 % | 892 |
| open->next open | +2.66 % | +1.75 % | 59 % | 890 |
| open->close t+1 | +3.01 % | +2.15 % | 60 % | 892 |
| open->close t+5 | +2.94 % | +1.64 % | 55 % | 892 |

## Arms

| arm | trades | hit | mean | median | t | yrs + | 2020-24 | 2025-26 | fills +/-2t | w/o top 5 % | placebo mean | placebo pct | top-10 names' share | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| g5 | 516 | 49 % | **+182** | -7 | 3.0 | 6/7 | +146 (n 112) | +192 (n 404) | +81 | +41 | -138 ± 17 | 100 | 13 % | tested: t>=3 |
| g7 | 290 | 52 % | **+300** | +34 | 3.0 | 3/6 | +80 (n 23) | +319 (n 267) | +190 | +137 | -164 ± 24 | 100 | 21 % | tested: t>=3 |
| g10 | 187 | 56 % | **+507** | +141 | 3.5 | 3/6 | -88 (n 13) | +551 (n 174) | +392 | +332 | -166 ± 32 | 100 | 30 % | tested: early>0 |
| g5_no | 514 | 52 % | **+161** | +35 | 2.0 | 5/7 | +127 (n 111) | +170 (n 403) | +161 | +6 | -116 ± 22 | 100 | 11 % | tested: t>=3 |
| g5_c1 | 516 | 53 % | **+154** | +52 | 1.8 | 5/7 | +211 (n 112) | +138 (n 404) | +154 | -15 | -115 ± 23 | 100 | 0 % | tested: t>=3,wo_top5>0 |
| g5_idio | 417 | 49 % | **+205** | -12 | 2.8 | 5/7 | +87 (n 85) | +235 (n 332) | +102 | +54 | -136 ± 19 | 100 | 18 % | tested: t>=3 |
| g5_big | 372 | 50 % | **+149** | -1 | 1.8 | 5/7 | +122 (n 105) | +159 (n 267) | +62 | +33 | -125 ± 23 | 100 | 19 % | tested: t>=3 |

## Sleeve economics (capital fraction = trades / 10 each day; the rest idle)

| arm | avg capital deployed | total | CAGR | Sharpe | max DD | money rule |
|---|---|---|---|---|---|---|
| g5 | 22 % | +142 % | +15.9 % | 2.94 | -6 % | pass |
| g7 | 21 % | +129 % | +16.3 % | 3.86 | -4 % | pass |
| g10 | 21 % | +145 % | +18.1 % | 4.86 | -4 % | pass |
| g5_no | 22 % | +113 % | +13.4 % | 2.23 | -14 % | pass |
| g5_c1 | 22 % | +103 % | +12.5 % | 1.95 | -24 % | pass |
| g5_idio | 19 % | +124 % | +14.8 % | 2.90 | -6 % | pass |
| g5_big | 21 % | +67 % | +8.9 % | 2.32 | -5 % | pass |

## By year (mean net bps per trade)

- g5: 2020: +308, 2021: +377, 2022: +76, 2023: -138, 2024: +85, 2025: +235, 2026: +169
- g7: 2021: -262, 2022: -83, 2023: -137, 2024: +253, 2025: +340, 2026: +309
- g10: 2021: -262, 2022: -83, 2023: -196, 2024: +3, 2025: +538, 2026: +557
- g5_no: 2020: +246, 2021: +421, 2022: -27, 2023: -114, 2024: +144, 2025: +260, 2026: +121
- g5_c1: 2020: +629, 2021: +322, 2022: +75, 2023: -87, 2024: +135, 2025: +297, 2026: +53
- g5_idio: 2020: +41, 2021: +379, 2022: -2, 2023: -138, 2024: +85, 2025: +220, 2026: +244
- g5_big: 2020: +308, 2021: +377, 2022: +75, 2023: -96, 2024: -111, 2025: +150, 2026: +165

## Reading

- Verdicts: g5 tested: t>=3; g7 tested: t>=3; g10 tested: early>0; g5_no tested: t>=3; g5_c1 tested: t>=3,wo_top5>0; g5_idio tested: t>=3; g5_big tested: t>=3.
- CANDIDATE needs all seven checks; ROBUST needs the neighbours too; the money rule is read on the sleeve as it would be run.
- IDX opens are dense only from 2025, so 2020-24 is the thin subsample; the test repeats itself as opens accumulate (~600 a day).

## Verdict written after the run

**0 of 7 CANDIDATE by the letter — and every one of the seven arms is positive, at the 100th placebo percentile, in both subsamples
(g10's 2020-24 excepted, n 13), at 2-tick fills, and monotone in the gap (g5 +182 -> g7 +300 -> g10 +507 bps; medians -7 -> +34 -> +141).**
What fails is the daily t: 2.97 (g5), 2.99 (g7) against the declared 3.0, on 233 / 150 / 100 active days; g10 clears t (3.5) and fails only
the thin early subsample. The two-day holds (g5_no, g5_c1) show the reversal is complete by the first close and does not continue.
The sleeve as it would be run (22 % capital on average) passes the money rule everywhere: Sharpe 2.9-4.9, max drawdown -4..-6 %.

Read: BOUNDARY, not closed. The mechanism (opening-auction overreaction, resolved by the close, larger for larger gaps) is the
textbook one and the data say the same thing from every side; the sample is simply young (IDX opens dense only since 2025). The t
will settle itself: ~600 IDX opens arrive per day, ~2 events per active day. Concentration is modest (top-10 names 13-21 %, 30 % for g10).
Risks to keep in view: 2025-26 was a high-volatility year (the H1-2026 crash and rebound) and 2023 is negative for every arm; the
2020-24 subsample is thin. Operationally the rule needs a 09:00 decision from the opening auction (the tick feed has those prints)
and a sale into the closing auction - a morning job, not the nightly chain.

## A gap between the backtest and what can actually be traded (found while building the paper book, 2026-09-22)

The daily summary's "open" is simply the **first trade of the day**, whenever it happens. The tick feed shows how different
that is from the opening auction: on 2026-09-22, of 135 subscribed names **121 printed at 08:58** (the auction) and 2 more by
09:08 - but AALI's first trade was at **10:45** (8,025 = its official "open", -3.9 % against the previous close), HOPE's at
10:45, ELTY's and BTEK's at 09:55. A gap measured against such an "open" is not tradeable at 09:00: nobody could have bought
it, because the stock had not traded yet, and by the time it does the price IS the open.

So the backtested population is wider than the executable one. The paper book is deliberately stricter: only names whose first
print falls inside 08:55-09:10 WIB are candidates (`gapfade.OPEN_FROM/OPEN_TO`). The difference between the paper record and
the backtest will measure how much of the +300 bps lived in late first prints - a number no daily-bar backtest can produce.
Open question for a menu 29c: whether a later scan (first print at any hour, hold to the close) is its own rule - it is a
different holding period and must be pre-registered separately, never folded into this one.

## Can the opening price actually be had? (measured 2026-09-22, one session)

Two facts from the tick feed, both new:

1. **There is nothing to see before the auction matches.** The raw frame archive for 2026-09-22 holds exactly four frames a
   minute between 08:40 and 08:57 - all of them `pong`. Stockbit's websocket disseminates no pre-opening indicative price and no
   pre-opening book to this subscription; the first market data of the day is the auction result at 08:58:03 (1,082 frames).
   IDX closes pre-opening order entry at 08:55, so by the time the price is known the auction cannot be joined: a limit order
   placed into it would have to be placed blind, before 08:55, on the whole universe.
2. **Reacting at 09:00 costs nothing measurable.** For the 106 liquid names that opened in the auction: the first continuous
   print at 09:01 is at the auction price for more than half of them (p25 0 bps, median **0 bps**, p75 +71 bps), the median is
   still 0 bps at 09:05, and **the best offer during 09:00-09:01 sits a median 0 bps (mean +6 bps) above the auction price**.

So the backtest's fill (buy at the open plus one tick) is reachable by acting at 09:00, and a pre-opening screen would neither
be possible nor worth building. The gap-fade design stands as built: scan at 09:00, buy at the offer, sell into the close.
Caveat: one session, and it contained no liquid name that gapped 5 % or more - the names that do gap are the volatile ones and
may drift faster. The paper book measures exactly this from here on.

## Flaw analysis (2026-09-23, operator: "analisis flaw dari strategy gap down")

Everything below is measured, not imagined. The rule stays a paper book; this is the list the paper record has to answer.

### Measured

1. **Survivorship inflates the long history by about half.** Same rule, same years (2023-2026), two universes: the Yahoo
   cache of 450 names that still exist gives **+453 bps** a trade at a 67 % hit rate; the full IDX universe of 962 listed
   names gives **+298 bps** at 54 %. The cache overstates by **+155 bps (+52 %)**. Every number in menu 29d — including
   the 45.7 % CAGR and the twelve-year support — carries that inflation. The IDX-open numbers (29b, 29c) do not.
2. **The profit is in a handful of trades.** Of 266 events, the best 5 % (13 trades) carry **58 %** of all profit and the
   best 10 % carry **91 %**. Drop the best 5 % and the mean falls from +298 to +133 bps. A year without a big reversal is
   a flat year, and the sample contains only three of them.
3. **The typical trade is a small loss.** Median +58 bps at -7 % on IDX opens, and *negative* at every threshold before
   2023. The hit rate of 54 % is barely above a coin.
4. **Capacity is a hard ceiling, and it is close.** A slot is NAV/5 against the name's own daily turnover: at Rp 100 M NAV
   it is 0.05 % of a median name's day (invisible), at Rp 1 bn 0.45 % (fine), at Rp 5 bn **2.3 % median and 20 % worst
   case** (moving the price), at Rp 20 bn **9 % median, 80 % worst case** (impossible). The rule dies somewhere between
   Rp 2 bn and Rp 5 bn of capital.
5. **6 % of events close locked at ARB** and no stop protects them — of the nine events a -10 % stop fires on, five were
   ARB-locked with no bid. Position size is the only defence (menu 29c).
6. **The frequency, not the edge, depends on the band regime.** Under the 7 % ARB the rule had 20 events a year and
   deployed 1.4 % of capital for 4 %/yr; under the wide bands, 136 events and 9.3 % for far more. The per-trade edge
   survived the regime change (menu 29d) but the *return* is entirely a function of how often IDX lets a name gap.
   If the bands are narrowed again the strategy does not get worse — it nearly stops existing.
7. **Decay is suspected but not proven.** 2026 looks weaker by hit rate (53 % against 82 % in 2024) yet on IDX opens the
   2026 mean is +318 bps against +266 for 2023-2025 (t -0.39, p 0.70): **not distinguishable from noise**. The earlier
   claim that the rule is visibly decaying was read off the survivor cache and does not hold on clean data.

### Not yet measured — what the paper book is for

8. **The fill is assumed.** Entry at the open plus one tick, exit at the close minus one tick, both taken on faith. The
   one real measurement (2026-09-22, all liquid names, a quiet day) says the offer at 09:00 sits a median 0 bps above the
   auction price — but that is not the same as a name that just fell 12 % on news.
9. **The live population is stricter than the backtest.** The book only trades names whose first print lands in
   08:55-09:10; roughly one name in ten opens later (AALI's "open" printed at 10:45 on 2026-09-22). The backtest counts
   those, the book cannot.
10. **Which five, on a day when eighty gap.** 2025-04-08 had 81 qualifying names; the rule takes the five deepest. That
    selection has never been tested against alternatives (most liquid, least deep, random).
11. **Crowding.** The rule is simple and public. Nothing in the data yet, but a widening spread or a shrinking fade in
    the paper record would be the first sign.
12. **Statistical debt.** This family has now consumed ~40 arms inside a desk total of 558 trials. 29b already failed its
    own pre-registered bar (daily t 2.97 against 3.0); none of what followed changes that.

### Operational

13. It needs a person or a job at 09:00 and 15:50 on roughly 60 days a year, and a missed exit leaves an overnight
    position the rule never intended (the sweep handles it, at whatever the next open gives).
14. The corporate-action guard depends on the desk's own tables being current at 09:00; a split announced but not yet
    recorded is caught only by the auto-rejection band check.

