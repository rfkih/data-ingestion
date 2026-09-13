# IDX — The doublers (2026-09-13)

**The operator's question.** Which names rose more than 100 % within one to two years, why, and can a statistical model
see them coming?

**Verdict.** Doubling is common in this market and almost unpredictable in the way that would make money. Over 2021–2025,
between 5 % and 34 % of the liquid names in any given year reached twice their price within twelve months (148 distinct
names, 429 in the panel). Before the run they look alike: small, volatile, heavily traded, already rising, in energy,
materials or technology, and more often *failing* the quality gate than passing it. Half of the doublings were earnings
explosions (profit ×2.8, P/E falling), half were re-ratings with no earnings behind them (profit ×0.9, P/E ×2.7), plus a
fifth that went from a loss to a profit. A LightGBM model trained walk-forward on point-in-time features gets AUC 0.57
to 0.69 and a top-decile lift of 1.2× to 1.9×, below the 2× bar set before the run; its top ten per month made +75 %
and +91 % in the two rally years and lost in the flat one. The same features that raise the chance of a double raise the
chance of a −50 % just as much: the wildest fifth of names has a mean twelve-month return of +5 % and a median of −27 %.
The doubler profile is a lottery ticket. The value book's doublers (PTRO, ENRG, ELSA, DSNG, TOBA, ADMR, JPFA…) are the
earnings-led and loss-to-profit class bought cheap, which is the only part of this with a decent median.

## Sample and method (pre-registered; trials cumulative 110)

Bars from 2020-01 for 989 names including the delisted, point-in-time fundamentals, one snapshot on the first trading day
of each month 2021-01 to 2025-09 (56 snapshots), universe = the desk's liquid pool that day (8,003 name-months). Labels:
`touch12` (close reaches 2× within 252 bars), `touch24` (within 504), `fwd12` (the plain 252-bar return; a delisted name
stays at its last close). Features at the snapshot close: E/P, B/P, DY, P/E, ROE, D/E, cash conversion, audited profit and
revenue growth, 1/3/6-month returns, 12-1 momentum, 60-day volatility, drawdown from the 252-day high, rise from the
252-day low, log market cap, log 60-day median value, turnover, 20-day foreign net share, sector. Model: LightGBM, fixed
parameters, walk-forward by test year (2023, 2024, 2025) with a 12-month purge; an L2 logistic regression for the signs.
Reading rule declared before the run: a finding worth building on only if top-decile lift > 2× in every test year and the
top ten beat the universe mean in two of three years. Script `research/idx_multibagger.py`; outputs
`research-scratch/idx-screen/multibagger_out.txt`, `multibagger_results.json`, `multibagger_panel.parquet`.

## How often (base rates)

| Snapshot year | Name-months | Reached 2× within 12 months | Within 24 months | Mean 12-month return |
|---|---|---|---|---|
| 2021 | 1,761 | 12.7 % | 17.5 % | +7 % |
| 2022 | 1,922 | 5.2 % | 9.1 % | −15 % |
| 2023 | 1,652 | 5.6 % | 14.5 % | −3 % |
| 2024 | 1,604 | 15.0 % | 28.5 % | +21 % |
| 2025 (Jan–Sep) | 1,064 | 33.7 % | open | +34 % |

## What they looked like before the run (hit rate of a 12-month double, by quintile)

| Feature | Q1 (lowest) | Q2 | Q3 | Q4 | Q5 (highest) |
|---|---|---|---|---|---|
| market cap | **21.0 %** | 16.3 | 9.7 | 9.4 | 6.9 |
| 60-day volatility | 4.1 | 6.0 | 11.5 | 17.2 | **24.5 %** |
| turnover (value / mcap) | 8.4 | 8.1 | 9.3 | 17.2 | **20.2 %** |
| 12-1 momentum | 9.2 | 9.7 | 9.9 | 14.4 | **20.6 %** |
| rise from 252-day low | 8.2 | 8.1 | 11.6 | 15.1 | **20.7 %** |
| 3-month return | 14.0 | 8.9 | 8.8 | 11.8 | **20.0 %** |
| ROE | **20.9 %** | 16.1 | 10.2 | 7.8 | 8.3 |
| audited profit growth | **18.8 %** | 12.3 | 9.1 | 8.8 | 14.3 |
| P/E | 11.7 | 8.1 | 8.4 | 11.0 | **20.6 %** |
| drawdown from 252-day high | 14.6 | 12.7 | 11.3 | 11.3 | 13.9 |
| foreign flow, 20 days | 9.4 | 12.8 | 15.9 | 14.5 | 10.8 |

By sector: technology 41 %, energy 27 %, basic materials 23 %, mining (old classification) 23 %; consumer cyclicals 16 %;
financials 5 %, property 2 %. Strict quality gate: passes 7.9 %, fails 15.3 %.

Reading: the doubler is small, wild, liquid for its size, already moving, in a cyclical or speculative sector, and usually
*not* a quality name on the last audited year. Being deeply drawn down does not help (the turnaround myth); being already
up does. Cheapness on P/E does not help either: the highest-P/E fifth (which includes loss-makers) doubles most often.

## Why they rose (105 doubler-years with an audited profit at both ends of the 12-month window)

| Class | Count | Median price | Median earnings | Median P/E |
|---|---|---|---|---|
| earnings-led | 37 | ×1.88 | ×2.84 | ×0.66 |
| re-rating-led | 38 | ×2.02 | ×0.86 | ×2.72 |
| loss to profit | 21 | ×1.98 | — | — |
| profit to loss | 9 | ×1.60 | — | — |

Half the doublings had the earnings to show for it (the coal and energy cycle of 2021–22, nickel, gold and the plantation
names later), and their P/E actually fell while they rose. The other half rose on nothing but a higher multiple, and nine
rose while their profit collapsed. The value book's own doublers sit in the first and third rows.

## The model

| Test year | Train rows (doublers) | Base rate | AUC gbm / logistic | Top-decile hit (lift) | Top-10 per month, 12-month return vs universe |
|---|---|---|---|---|---|
| 2023 | 1,761 (223) | 5.6 % | 0.571 / 0.526 | 6.7 % (1.2×) | −3.9 % vs −3.7 % |
| 2024 | 3,683 (322) | 15.0 % | 0.649 / 0.619 | 28.1 % (1.9×) | +75.5 % vs +20.4 % |
| 2025 | 5,335 (415) | 33.7 % | 0.689 / 0.679 | 55.7 % (1.6×) | +90.7 % vs +34.4 % |

Reading rule: lift above 2× in every year: no. Top ten beats the universe in two of three: yes. Verdict by the rule: **not
predictive enough to act on.** What the model learned (gain): sector, volatility, profit and revenue growth, size,
liquidity, six-month return, leverage. The logistic signs agree: smaller, wilder, faster-growing revenue, more turnover.

The whole distribution, not the mean (the same top decile):

| | mean | median | P(> +100 %) | P(< −30 %) | P(< −50 %) |
|---|---|---|---|---|---|
| 2023 top decile | −9 % | −17 % | 2 % | 33 % | 14 % |
| 2024 top decile | +83 % | +5 % | 18 % | 16 % | 7 % |
| 2025 top decile | +76 % | +35 % | 33 % | 16 % | 9 % |
| wildest-volatility fifth, pooled | +5 % | −27 % | 9 % | 47 % | 25 % |
| smallest-cap fifth, pooled | +13 % | −21 % | 11 % | 41 % | 22 % |
| strict gate passes, pooled | +4 % | −7 % | 4 % | 19 % | 5 % |
| strict gate fails, pooled | +7 % | −13 % | 8 % | 31 % | 13 % |

The mean is carried by the few doublers; the median holder of a doubler-profile name loses money, and one in four of the
wildest fifth loses more than half. That is the shape of a lottery: positive skew, negative median.

## The statistical model, stated

Over 2021–2025 the probability that a liquid IDX name reaches 2× within twelve months is about 12 % on average and moves
with the year (5 % in a flat market, a third in a rally). Conditional on the name, the odds rise with smaller size, higher
recent volatility, higher turnover, a positive six- to twelve-month trend, revenue growth, and an energy, materials or
technology label, and fall with quality (ROE, profit growth) and with the financial and property sectors. The best
achievable ranking on these inputs separates doublers from the rest with AUC of about 0.6 to 0.7, and the top decile it
picks has a median return near zero or negative outside rally years, with a one-in-ten chance of losing half.

## What to take from it

1. **Do not build a "doubler" strategy on this.** The predictable part is the profile, and the profile is a lottery ticket:
   a fine mean, a poor median, large drawdowns, and everything depends on the year.
2. **The doublings worth having came from earnings, bought cheap.** That is what the strict composite already does, and its
   own list of doublers (PTRO 2023, ENRG 2025, ELSA, DSNG, TOBA, ADMR, JPFA, TKIM) came with a positive median for the
   book as a whole. The value book is the sane way to own this class.
3. If the operator wants exposure to the re-rating class anyway, the only defensible form is a small, fixed sleeve (say
   10 % of the book) of ten or more such names, sized so that losing half of the sleeve does not matter, rebalanced
   yearly, with no story-chasing. That is not a recommendation; it is the shape a quant would accept.
4. Two features are worth adding to the card as context, not as rules: 60-day volatility and turnover, because they say
   which kind of name the operator is looking at.
