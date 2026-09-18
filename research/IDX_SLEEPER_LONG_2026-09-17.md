# IDX menu 9 — sleeping small caps + accumulation, 1–2 years ahead — 2026-09-17 — 3 trials, cumulative N = 295

Signals thinned to one per name per 20 trading days; returns on forward-filled closes (a name that stops trading is carried at its last price);
windows must fit inside 2020-01 .. 2026-09, so signals run to about 2024-09.

| set | n | P(up 1y) | med 1y | avg 1y | P(up 2y) | med 2y | P(>= +50 % 2y) / P(<= −30 % 2y) | med best point in 2y | stopped trading |
|---|---|---|---|---|---|---|---|---|---|
| all small caps (base rate) | 1621 | 33 % | -20.2 % | +1.3 % | 36 % | -19.8 % | 19 % / 44 % | +36.1 % | 0 % |
| sideways small caps, any flow | 207 | 35 % | -9.4 % | +6.8 % | 34 % | -15.8 % | 19 % / 39 % | +23.8 % | 0 % |
| **fflow**: sideways + accumulation | 33 | 39 % | -17.7 % | +3.7 % | 45 % | -4.3 % | 30 % / 27 % | +26.8 % | 0 % |
| control: sideways, no fflow | 174 | 34 % | -9.1 % | +7.4 % | 32 % | -18.1 % | 17 % / 41 % | +23.6 % | 0 % |
| **obv**: sideways + accumulation | 85 | 32 % | -19.2 % | +15.9 % | 32 % | -20.8 % | 24 % / 41 % | +23.8 % | 0 % |
| control: sideways, no obv | 122 | 38 % | -7.7 % | +0.5 % | 35 % | -9.6 % | 16 % / 38 % | +23.8 % | 0 % |
| **fflow_obv**: sideways + accumulation | 18 | 33 % | -24.5 % | -11.4 % | 39 % | -9.4 % | 39 % / 33 % | +19.5 % | 0 % |
| control: sideways, no fflow_obv | 189 | 35 % | -9.1 % | +8.5 % | 33 % | -16.1 % | 17 % / 40 % | +24.0 % | 0 % |

COMPOSITE over the same windows (median): 1y +5.6 %, 2y +10.2 %.

| arm | n | med 1y gap vs control | vs small-cap base | informative? |
|---|---|---|---|---|
| fflow | 33 | -8.6 pp | +2.5 pp | no |
| obv | 85 | -11.5 pp | +1.0 pp | no |
| fflow_obv | 18 | -15.4 pp | -4.3 pp | no |

Reading rule applied as declared: informative 0 of 3.

Limits: current listing board (not PIT); market cap from feature_daily on the day; signals thinned; the 2-year read has fewer independent
windows than it has rows (overlapping calendar time), so treat P(up) and medians as descriptive, not as significance.

## Reading (written after the run; rule fixed before it)

At one and two years the picture gets worse, not better. The base rate is the first fact: over 2020–2024 signal dates, the median
liquid small cap is DOWN about 20 % a year and two years later (up only a third of the time), while the COMPOSITE is up 6 % and
10 % over the same windows. Going sideways first helps a little (median −9 % / −16 %); being accumulated on top of that does not:
foreign-accumulated sleepers −18 % at one year (n = 33), OBV-accumulated −19 % (n = 85), both accumulated −25 % (n = 18) — every arm
below its own control at one year. What the accumulation arms do have is a fatter right tail — the OBV arm's MEAN one-year return is
+16 % against a −19 % median, and 24–30 % of the accumulated names are up 50 % or more after two years against 16–19 % for the
controls — while 27–41 % are down 30 % or more. That is a lottery ticket, not a strategy: a few multi-baggers pay for a majority
of losers, and nothing in the data says which is which in advance.

**Verdict: 0 of 3 informative. Over 1–2 years, sleeping small caps under accumulation underperform the index by 20–30 pp at the
median; the idea does not work at any horizon the desk can measure (5 days to 2 years). Where the operator's instinct is right is
the tail — small caps that eventually run do run far — but the only rule that has caught those runs after costs is the trend
follower of menus 6–7, which enters after the move has started, not while the stock sleeps. Cumulative 295 trials.**
