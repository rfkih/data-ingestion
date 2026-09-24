# IDX menu 29e — threshold, slots, selection and the ARB floor — 2020-09-08 -> 2026-09-21

IDX-sourced opens only, 110673 gap-down name-days before any threshold. Pre-registered in
`research/idx_gapfade_tune.py`; 8 trials (cumulative 566). The deployed rule is the reference row.

| arm | events | capital | mean | median | hit | closed at ARB | total | CAGR | Sharpe | max DD | worst trade | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| deployed: -7 %, K=5, deepest | 202 | 5.6 % | **+329** | +100 | 54 % | 3.0 % | +254 % | +57 % | 5.71 | -8.3 % | -17 % | reference |
| A. room >= 8% above ARB | 189 | 5.2 % | **+323** | +147 | 57 % | 2.1 % | +220 % | +52 % | 5.75 | -8.2 % | -17 % | no |
| B. gap -5 %, K=5 | 364 | 4.6 % | **+231** | +43 | 53 % | 1.9 % | +389 % | +30 % | 4.58 | -14.0 % | -17 % | no |
| B. gap -5 %, K=10 | 450 | 2.9 % | **+255** | +72 | 53 % | 1.6 % | +200 % | +20 % | 4.19 | -7.8 % | -17 % | no |
| B. gap -7 %, K=10 | 255 | 3.5 % | **+357** | +105 | 55 % | 2.4 % | +139 % | +37 % | 5.16 | -4.2 % | -17 % | no |
| B. gap -10 %, K=5 | 128 | 5.5 % | **+437** | +100 | 54 % | 4.7 % | +190 % | +81 % | 6.73 | -7.6 % | -17 % | no |
| B. gap -10 %, K=10 | 163 | 3.5 % | **+472** | +95 | 53 % | 3.7 % | +109 % | +51 % | 5.95 | -3.8 % | -17 % | no |
| C. most liquid first | 202 | 5.6 % | **+286** | +45 | 53 % | 3.0 % | +195 % | +47 % | 4.61 | -8.3 % | -17 % | no |

## Reading

**0 of 8. Nothing is adopted, and the deployed rule is unchanged.**

- **A. The ARB-room filter does not work.** Today's quartile table suggested that events opening close to the floor
  were the dangerous ones; pre-registered, the filter removes 13 of 202 trades and buys nothing for them. The mean
  falls 6 bps (+329 -> +323), the drawdown improves by a tenth of a point (-8.3 -> -8.2 %), the total gives up 34
  points. The share closing locked at ARB does fall, 3.0 % to 2.1 %, but the worst trade is identical at -17 %: the
  filter drops events that were merely near the floor, not the ones that reach it. **The quartile split was noise, and
  this is the value of declaring the test first** - by eye it looked like the best idea of the day.
- **B. The threshold is a straight trade between size and frequency, and neither end wins.** Deeper gaps pay far more
  per trade (-10 % pays +437 bps against +329) but there are 128 of them instead of 202, so the sleeve total falls,
  +254 % -> +190 %. Shallower gaps trade more often for less (-5 %: 364 trades at +231 bps) and the total rises to
  +389 % - but the drawdown goes with it, -8.3 % -> -14.0 %, and the Sharpe drops from 5.71 to 4.58. **The one result
  worth remembering: ten slots instead of five roughly halves the drawdown** (-8.3 % -> -4.2 % at the same threshold)
  at the cost of about 45 % of the total return, because the capital is spread thinner. That is a size decision for
  when the book has capital to spread, not a rule change.
- **C. Deepest-first is the right selection.** Choosing the most liquid of the day's candidates instead loses 43 bps
  a trade (+286 against +329) on exactly the same 202 slots. The deployed choice, made because the backtest was
  written that way, turns out to be the better one.

So the answer to "how much does this improve profit or drawdown" is: **nothing measurable improves it.** The three
mitigations built today - the participation cap, the execution-context record and the morning push - change no return
by construction. What the run does buy is the knowledge that the two tempting changes (filter out the near-ARB events,
move the threshold) are not improvements, and would have cost return had they been adopted by eye.

### A caveat on the population that matters more than any arm

The IDX-open archive supports these thresholds only recently: the -7 % rule has 1 event in 2023, 12 in 2024, 154 in
2025 and 315 in 2026. **189 of the 202 trades in every row above are from 2025-2026.** The twelve-year support for the
fade comes from menu 29d's Yahoo cache at shallower thresholds, not from this table. Treat the levels here as a
comparison between arms measured on the same two years, not as an estimate of what the rule earns.

### The bar, for the record

BETTER needs Sharpe >= deployed + 0.3, no deeper drawdown and no less total return; a risk rule needs a drawdown at
least 3 points shallower for no more than a tenth of the return. Cumulative trials 566.
