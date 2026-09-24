# IDX menu 29d — how far back can the gap-fade be measured? — written 2026-09-23

The operator asked for a backtest from 2008. It cannot be done, and the reason is in the data, not the rule.

## Can a Yahoo 'open' stand in for the IDX open?

- **After 2015, yes.** On the 153,449 name-days of 2025-2026 where both exist, the Yahoo open rebased onto the IDX
  close equals the IDX open on **99.7 %** of them (mean difference 0 bps), and the rule returns +227 bps on Yahoo
  opens against +228 bps on IDX opens over the same events. *This corrects menu 29, which blamed a Yahoo artefact:*
  *the Yahoo-filled rows there were a different era and population, not a different measurement.*
- **Before 2013, no.** The share of traded days where `open == close`:

| year | open == close |
|---|---|
| 2015 | 16 % |
| 2016 | 16 % |
| 2017 | 18 % |
| 2018 | 14 % |
| 2019 | 15 % |
| 2020 | 13 % |
| 2021 | 13 % |
| 2022 | 14 % |
| 2023 | 17 % |
| 2024 | 18 % |
| 2025 | 16 % |
| 2026 | 13 % |

  65-99 % in 2007-2012 means the column holds the close, not an opening price; 40 % in 2013, and the normal
  14-18 % only from 2015. A 2008 backtest of a rule that buys the open would be reading a field that does not
  contain an open. Admitted years: 2015-2026.

## The rule where the data allows it (Yahoo cache, survivors only)

| window | events | names | days | hit | mean | median | daily t | sleeve | max DD | Sharpe | years + |
|---|---|---|---|---|---|---|---|---|---|---|---|
| all 2015-2026 | 642 | 217 | 385 | 60 % | **+364** | +246 | 8.6 | +6757 % | -12 % | 6.47 | 10/12 |
| 2015-2019 (out of sample) | 48 | 38 | 31 | 40 % | **+135** | -81 | 1.1 | +15 % | -8 % | 2.85 | 4/5 |
| 2020-2022 | 105 | 62 | 74 | 36 % | **+56** | -139 | 1.7 | +17 % | -12 % | 1.84 | 2/3 |
| 2023-2026 | 489 | 153 | 280 | 67 % | **+453** | +373 | 8.9 | +5006 % | -9 % | 7.87 | 4/4 |
| gap <= -5 % | 1696 | 318 | 884 | 54 % | **+225** | +86 | 10.3 | +104586 % | -16 % | 5.40 | 10/12 |
| gap <= -10 % | 367 | 176 | 233 | 60 % | **+498** | +274 | 7.6 | +2194 % | -8 % | 7.23 | 9/12 |

## By year (sleeve return, 5 slots)

- 2015: +0 %, 2016: +9 %, 2017: -1 %, 2018: +1 %, 2019: +5 %, 2020: +4 %, 2021: +19 %, 2022: -6 %, 2023: +263 %, 2024: +369 %, 2025: +87 %, 2026: +61 %

## Verdict

- The 2015-2019 era, which the modern test never saw: **inconclusive**.
- Survivorship is not fixable from this cache: it holds the 450 names that exist today, so every delisted name
  is missing and every figure here is flattered. Treat the pre-2020 numbers as direction, not level.
- To go back further the desk would need a source with true opening-auction prices before 2013; the IDX bronze
  archive starts in 2020 and Yahoo's older opens are not opens.

## Where the edge actually lives (read after the run)

| year | events | mean bps | median bps | hit |
|---|---|---|---|---|
| 2015 | 9 | +15 | -30 | 44 % |
| 2016 | 12 | +358 | -5 | 50 % |
| 2017 | 5 | -59 | -160 | 20 % |
| 2018 | 15 | -10 | -131 | 27 % |
| 2019 | 7 | +358 | +15 | 57 % |
| 2020 | 50 | -4 | -176 | 30 % |
| 2021 | 26 | +345 | +304 | 62 % |
| 2022 | 29 | -101 | -168 | 24 % |
| **2023** | 104 | **+634** | +542 | 77 % |
| **2024** | 122 | **+652** | +640 | 82 % |
| 2025 | 85 | +406 | +176 | 60 % |
| 2026 | 178 | +234 | +53 | 53 % |

Split at the day IDX replaced the 7 % lower auto-rejection limit with the symmetric 20-35 % bands (2023-09-04):

| era | events | years | mean | median | hit | daily t |
|---|---|---|---|---|---|---|
| before, to 2023-09-03 | 210 | 9 | +205 bps | **-30** | 47 % | 4.0 |
| after, from 2023-09-04 | 432 | 4 | **+442 bps** | **+361** | 66 % | 7.8 |

**This is the most important number in the study, and it is not comforting.** Under the old 7 % ARB regime a name could
barely gap 7 % down without locking, so the rule had almost nothing to trade - 210 events in nine years, a negative
median, and a hit rate of 47 %; its positive mean comes from a handful of outliers. Everything the rule is made of
appears after the bands widened: 432 events in four years, median +361 bps, hit 66 %.

Two readings, and the data does not choose between them. Either the wider bands *created* the opportunity (a name can now
fall 12 % at the open and still trade, so the overreaction is visible and fadeable where it used to be a locked market),
which means the edge is real and current; or 2023-2024 was simply an extraordinary two years (mean +634 and +652 bps,
hit 77-82 %, against +234 and 53 % in 2026 as the market normalised), and the rule is decaying in front of us. The 2026
column is the one to watch: it is the weakest post-band year and it is also the year with the most events.

## What this does to menu 29b's verdict

29b called the rule BOUNDARY on 266 IDX-open events from 2023-2026 - which is now visible as *exactly the favourable
regime*. The honest restatement: **the gap-fade is a post-September-2023 phenomenon with three good years and no support
before that**, measured on a survivor-only cache. It stays a paper book, and the paper record now has a second job
besides measuring fills: watching whether 2026's +234 bps keeps sliding.

## The regime story, tested properly — and it does not hold

The section above read the -7 % threshold alone and concluded the edge was born with the wider bands. That reading was
wrong, and the test that shows it is simple: under the old 7 % lower limit a gap of -3 to -6 % was perfectly legal, so if
the fade is real it should be visible there too, in the nine years before the change.

| gap | era | events | years | mean | median | hit | daily t | years + |
|---|---|---|---|---|---|---|---|---|
| -3 % | before | 2,124 | 9 | +95 | -30 | 49 % | **6.0** | **9/9** |
| -3 % | after | 1,207 | 4 | +151 | +97 | 57 % | 4.9 | 3/4 |
| -4 % | before | 1,394 | 9 | +147 | +5 | 50 % | **7.0** | 7/9 |
| -4 % | after | 922 | 4 | +233 | +196 | 61 % | 7.0 | 4/4 |
| -5 % | before | 989 | 9 | +166 | -30 | 48 % | **6.6** | 7/9 |
| -5 % | after | 707 | 4 | +308 | +287 | 63 % | 8.0 | 4/4 |
| -6 % | before | 668 | 9 | +188 | -61 | 47 % | **6.1** | 8/9 |
| -6 % | after | 543 | 4 | +393 | +342 | 65 % | 8.1 | 4/4 |
| -7 % | before | 210 | 9 | +205 | -30 | 47 % | 4.0 | 6/9 |
| -7 % | after | 432 | 4 | +442 | +361 | 66 % | 7.8 | 4/4 |

**The fade worked before September 2023 at every threshold the old regime allowed** - 2,124 events and nine straight
positive years at -3 %, daily t of 6-7 across the board - and it is monotone in the depth of the gap in both eras. What
the band change did was make the -7 % event *possible*: 210 events in nine years became 432 in four. The magnitude
roughly doubled after the change, which is consistent both with the wider bands letting the overreaction show and with
2023-2024 being extraordinary; the level is uncertain, the existence is not.

So the corrected statement is the opposite of the one above: **the gap-fade has twelve years and 3,300+ events of
support across two auto-rejection regimes, not three good years.** The -7 % threshold in particular has a short history,
but it is the tail of a relationship that holds all the way down to -3 %.

A live question this opens, not answered here: the book trades -7 % because menu 29b measured per-trade returns. Over
twelve years -5 % has 1,696 events against 642, at +225 bps against +364 - fewer basis points per trade but far more of
them, which for a five-slot sleeve may be the better rule. That is a threshold study (menu 29e), pre-registered on its
own, not a switch to make by eye.

