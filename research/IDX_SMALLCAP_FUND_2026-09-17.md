# IDX menu 10 — small caps with a fundamental growth filter (point-in-time) — 2026-09-17 — 6 trials, cumulative N = 301

Monthly signals (first trading day), liquid small caps (value >= Rp 5 bn/day, close >= Rp 100, market cap <= Rp 5 T); growth from the latest
report published by the signal date; returns on forward-filled closes; windows must fit inside the data (signals to ~2024-09).

| set | n | P(up) / med 60d | P(up 1y) | med 1y | avg 1y | P(>= +50 % 1y) / P(<= −30 %) | P(up 2y) | med 2y |
|---|---|---|---|---|---|---|---|---|
| all small caps (base rate) | 1592 | 37 % / -5.7 % | 34 % | -18.4 % | +4.3 % | 14 % / 39 % | 38 % | -17.7 % |
| **rev_g** | 337 | 38 % / -5.2 % | 39 % | -14.5 % | +27.5 % | 17 % / 35 % | 54 % | +12.5 % |
| control: fails rev_g | 650 | 34 % / -6.3 % | 29 % | -21.7 % | -3.4 % | 9 % / 41 % | 32 % | -25.7 % |
| **np_g** | 359 | 39 % / -4.9 % | 34 % | -15.9 % | +8.7 % | 10 % / 35 % | 44 % | -5.0 % |
| control: fails np_g | 440 | 35 % / -5.2 % | 32 % | -19.7 % | +8.8 % | 13 % / 38 % | 35 % | -22.3 % |
| **rev_np_g** | 187 | 41 % / -3.4 % | 37 % | -18.3 % | +25.3 % | 13 % / 36 % | 53 % | +8.5 % |
| control: fails rev_np_g | 594 | 36 % / -5.2 % | 32 % | -17.1 % | +4.5 % | 12 % / 37 % | 36 % | -18.6 % |
| **accel** | 333 | 30 % / -6.7 % | 34 % | -17.0 % | +16.9 % | 13 % / 36 % | 38 % | -19.0 % |
| control: fails accel | 347 | 41 % / -3.3 % | 40 % | -9.6 % | +19.5 % | 15 % / 31 % | 53 % | +3.3 % |
| **sleeper_rev** | 54 | 54 % / +2.3 % | 46 % | -13.7 % | +28.3 % | 15 % / 33 % | 50 % | +0.0 % |
| control: fails sleeper_rev | 107 | 38 % / -3.2 % | 32 % | -10.5 % | +3.5 % | 8 % / 33 % | 26 % | -21.3 % |
| **sleeper_np** | 61 | 61 % / +2.6 % | 51 % | +0.7 % | +28.1 % | 8 % / 13 % | 44 % | -1.6 % |
| control: fails sleeper_np | 82 | 34 % / -3.9 % | 30 % | -27.2 % | +9.4 % | 15 % / 43 % | 29 % | -24.5 % |

COMPOSITE over the same windows (median 1y): +6.6 %.

| arm | n | med 1y gap vs control | vs small-cap base | informative? |
|---|---|---|---|---|
| rev_g | 337 | +7.2 pp | +3.8 pp | YES |
| np_g | 359 | +3.9 pp | +2.5 pp | no |
| rev_np_g | 187 | -1.2 pp | +0.0 pp | no |
| accel | 333 | -7.4 pp | +1.4 pp | no |
| sleeper_rev | 54 | -3.3 pp | +4.6 pp | no |
| sleeper_np | 61 | +27.9 pp | +19.0 pp | no |

Reading rule applied as declared: informative 1 of 6.

Limits: current listing board (not PIT); growth uses year-to-date figures vs the same period a year earlier (reports with a prior-year
comparative only); overlapping windows — descriptive, not significance; no costs (event study).

## Reading (written after the run; rule fixed before it)

Two of six filters do something. Revenue growth of +20 % or more (latest published report, year-to-date vs a year earlier)
lifts the median one-year return of a small cap from −22 % (control) to −14 % (+7 pp), roughly doubles the two-year median gap
(+12.5 % vs −25.7 %) and, on the mean, turns +27.5 % against −3.4 % — informative by the rule, though still below the COMPOSITE
(+6.6 %) at one year: growth alone does not make a small cap beat the index at the median. The striking one is
sideways + profit growth (sleeper_np): only 61 signals, but a median one-year return of +0.7 % against −27.2 % for sideways small
caps without profit growth (+28 pp), half of them up after a year (control 30 %), and a crash rate (−30 % or worse) of 13 %
against 43 %. Profit growth on a stock that has not moved yet mostly removes the losers; the right tail stays (mean +28 %).
Acceleration of revenue growth is the opposite (−7 pp): a jump in growth is usually a low base, not a new trajectory.
Menu 11 tests whether these two survive their neighbours before either is believed.
