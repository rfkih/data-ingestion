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
