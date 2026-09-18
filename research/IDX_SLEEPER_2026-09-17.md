# IDX menu 8 — sleeping small caps under continuous accumulation — 2026-09-17 — 5 trials, cumulative N = 292

## Event study (gross, every signal, equal weight): what happens after a sideways name has been accumulated

| arm | n | P(up 20d) | med 20d | P(up 60d) | med 60d | avg 60d | med 120d | med MFE120 / P(>= +20 % within 120d) |
|---|---|---|---|---|---|---|---|---|
| **fflow** (sideways small cap + accumulation) | 955 | 37 % | -2.1 % | 37 % | -4.0 % | -0.6 % | -1.6 % | +11.1 % / 39 % |
| control (sideways small cap, no fflow) | 5058 | 46 % | -0.4 % | 46 % | -0.9 % | +4.0 % | -1.5 % | +15.8 % / 45 % |
| **obv** (sideways small cap + accumulation) | 2787 | 43 % | -0.8 % | 45 % | -1.3 % | +3.5 % | -1.3 % | +21.2 % / 51 % |
| control (sideways small cap, no obv) | 3226 | 45 % | -0.6 % | 44 % | -1.5 % | +3.0 % | -1.9 % | +10.6 % / 38 % |
| **broker2** (sideways small cap + accumulation) | 0 | - | - | - | - | - | - | - |
| control (sideways small cap, no broker2) | 4 | 25 % | -8.9 % | 75 % | +5.3 % | +8.2 % | +43.9 % | +52.8 % / 75 % |
| **broker5** (sideways small cap + accumulation) | 0 | - | - | - | - | - | - | - |
| control (sideways small cap, no broker5) | 0 | - | - | - | - | - | - | - |
| **fflow_obv** (sideways small cap + accumulation) | 562 | 35 % | -2.5 % | 31 % | -5.9 % | -3.9 % | -1.9 % | +11.9 % / 40 % |
| control (sideways small cap, no fflow_obv) | 5451 | 45 % | -0.5 % | 46 % | -0.9 % | +4.0 % | -1.5 % | +15.4 % / 44 % |
| reference: fflow on ALL liquid caps | 8162 | 42 % | -1.2 % | 40 % | -3.0 % | -0.8 % | -3.6 % | +10.1 % / 30 % |

| arm | n | median 60d gap vs control | informative? |
|---|---|---|---|
| fflow | 955 | -3.2 pp | no |
| obv | 2787 | +0.1 pp | no |
| broker2 | 0 | +nan pp | no |
| broker5 | 0 | +nan pp | no |
| fflow_obv | 562 | -5.0 pp | no |

## Trade read (book of 10 slots, entry close t+1 @offer, exit trailing 10 % or 120 days @bid, Stockbit fees)

| arm | trades | hold d | hit | avg net | payoff | t | total | CAGR | Sharpe | mDD | years | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| random entries + same exit | 687 | 22 | 32 % | +0.49 % | 2.23 | 0.5 | -17 % | -2.9 % | 0.03 | -81 % | 20:+69 21:+14 22:-34 23:-19 24:-51 25:+82 26:-12 | reference |
| sideways only (no accumulation test) | 268 | 39 | 34 % | +1.81 % | 2.47 | 1.3 | +47 % | +6.2 % | 0.50 | -32 % | 20:+34 21:+3 22:-8 23:+6 24:-16 25:+18 26:+11 | reference |
| fflow | 102 | 39 | 26 % | -1.11 % | 2.35 | -0.6 | -11 % | -1.8 % | -0.22 | -32 % | 20:+5 21:+10 22:-1 23:-2 24:-18 25:+0 26:-4 | tested: n<150,t<2.5,sharpe<1,mdd>25%,years<5/7,vs random |
| obv | 218 | 38 | 35 % | +1.79 % | 2.36 | 1.1 | +36 % | +4.8 % | 0.44 | -31 % | 20:+30 21:+11 22:-9 23:+3 24:-12 25:+4 26:+8 | tested: t<2.5,sharpe<1,mdd>25%,vs random |
| broker2 | 0 | 0 | 0 % | +0.00 % | 0.00 | 0.0 | +0 % | +0.0 % | 0.00 | 0 % | 20:+0 21:+0 22:+0 23:+0 24:+0 25:+0 26:+0 | tested: n<150,t<2.5,sharpe<1,years<5/7,vs random |
| broker5 | 0 | 0 | 0 % | +0.00 % | 0.00 | 0.0 | +0 % | +0.0 % | 0.00 | 0 % | 20:+0 21:+0 22:+0 23:+0 24:+0 25:+0 26:+0 | tested: n<150,t<2.5,sharpe<1,years<5/7,vs random |
| fflow_obv | 72 | 40 | 29 % | -0.61 % | 2.22 | -0.3 | -5 % | -0.7 % | -0.10 | -26 % | 20:+5 21:+9 22:-0 23:-0 24:-11 25:-5 26:-2 | tested: n<150,t<2.5,sharpe<1,mdd>25%,years<5/7,vs random |

Reading rules applied as declared: informative 0 of 5; candidates for money 0 of 5.

Limits: current listing board (not PIT); broker arms cover 46 names (20-day windows since 2023-09, 5-day windows since 2025-09);
signals one day late (close-to-close); costs = quoted closing spread + fees; dividends ignored.

## Reading (written after the run; rules fixed before it)

The operator's question was "how much does a sleeping, accumulated small cap rise afterwards?" The data's answer: no more than a
sleeping small cap that is not being accumulated. Sixty days after the signal the median small cap that went sideways while
foreigners kept net-buying is DOWN 4.0 % (up 37 % of the time); the sideways control without that buying is down 0.9 % (up 46 %).
Volume-based accumulation (OBV rising while the price is flat) is no better on the median (−1.3 % vs −1.5 %) — what it does
change is the size of the swing: the best point within 120 days is +21 % at the median against +11 % for the control, and half of
the names touch +20 % at some point against 38 %. They then give it back: by day 60 and 120 the medians are the same as the control.
That is the whole "akumulasi lalu terbang" story in numbers — the flight happens about as often as not, and it does not stay up.
Run through the book with a trailing stop, which is built to catch exactly such excursions, the OBV arm returns +4.8 %/yr against
+6.2 %/yr for sideways small caps with no accumulation test at all. The broker feed cannot speak here: its 46 names are the
market's largest, so it has no sideways small caps.

**Verdict: 0 informative, 0 candidates. Sideways + accumulation (foreign or volume flow) does not predict a rise in small caps;
it predicts larger swings that revert. Together with menus 3–5 this closes the accumulation family on every measure the desk
holds: foreign flow, broker concentration, broker labels, order-book imbalance, OBV. Cumulative 292 trials; the trend-following
lead of menus 6–7 remains the only thing that survived, and it did so in the names accumulation rules avoid — the ones already
moving.**
