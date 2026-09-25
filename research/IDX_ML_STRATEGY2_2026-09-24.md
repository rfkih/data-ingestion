# IDX menu ML-4b — cost-aware strategies on the prediction desk's scores — 2026-09-24 — 8 trials, cumulative N = 731

Same OOS scores and costs as ML-4 (#151). Round trip: LIQ 91 bps, BLUE 70 bps. Hysteresis books hold while the name stays in the top 30 % of the day's ranking, max 60 days. Book 2022-01 -> 2026-09-24.

| arm | hold | K | trades | CAGR | Sharpe | mDD | years + | by year | verdict |
|---|---|---|---|---|---|---|---|---|---|
| blue5 | 5 | 5 | 5,620 | -26.7 % | -0.65 | -80 % | 0/5 | 22:-28 23:-5 24:-17 25:-5 26:-57 | not a candidate: sharpe -0.65 < 1.2; mdd -80 % < -25 %; 0/5 years positive |
| blue20 | 20 | 5 | 5,545 | -21.3 % | -0.47 | -76 % | 2/5 | 22:-45 23:-20 24:+15 25:+31 26:-51 | not a candidate: sharpe -0.47 < 1.2; mdd -76 % < -25 %; 2/5 years positive |
| liq5_top3 | 5 | 3 | 3,372 | -3.7 % | 0.16 | -71 % | 2/5 | 22:-38 23:-16 24:+54 25:+49 26:-30 | not a candidate: sharpe 0.16 < 1.2; mdd -71 % < -25 %; 2/5 years positive |
| hyst5_liq | hyst(2 d) | 10 | 5,544 | -3.1 % | 0.22 | -76 % | 1/5 | 22:-27 23:-31 24:-3 25:+211 26:-44 | not a candidate: sharpe 0.22 < 1.2; mdd -76 % < -25 %; 1/5 years positive (placebo pct 100) |
| hyst5_blue | hyst(2 d) | 5 | 2,534 | -17.1 % | -0.06 | -77 % | 1/5 | 22:-18 23:-8 24:-43 25:+146 26:-61 | not a candidate: sharpe -0.06 < 1.2; mdd -77 % < -25 %; 1/5 years positive |
| hyst20_liq | hyst(3 d) | 10 | 3,265 | -23.9 % | -0.36 | -84 % | 1/5 | 22:-34 23:-48 24:-25 25:+50 26:-29 | not a candidate: sharpe -0.36 < 1.2; mdd -84 % < -25 %; 1/5 years positive |
| blend_hyst | hyst(3 d) | 10 | 4,349 | -14.7 % | -0.07 | -86 % | 1/5 | 22:-44 23:-37 24:-32 25:+141 26:-19 | not a candidate: sharpe -0.07 < 1.2; mdd -86 % < -25 %; 1/5 years positive |
| avoid250 | 250 | all-30% | 106,727 | -0.0 % | 0.01 | -11 % | 2/5 | 22:-4 23:-2 24:+0 25:+8 26:-2 | loser filter INFORMATIVE: excess +1.1 %/yr over the unfiltered LIQ book, positive 4/5 years |

| reference | CAGR | Sharpe | mDD |
|---|---|---|---|
| random_blue_H5 | -33.9 % | -1.79 | -87 % |
| random_blue_H20 | -13.0 % | -0.58 | -60 % |
| liq_all_H250 | -1.1 % | -0.19 | -20 % |

avoid250 excess by year vs the unfiltered LIQ book: 2022:+2.5 2023:+4.1 2024:+1.0 2025:-4.5 2026:+1.2

## Verdict (menu ML-4b, study stored)

Best arm by Sharpe: **hyst5_liq** (-3.1 %/yr, Sharpe 0.22, mDD -76 %) - not a candidate: sharpe 0.22 < 1.2; mdd -76 % < -25 %; 1/5 years positive.
Candidates: none. loser filter INFORMATIVE: excess +1.1 %/yr over the unfiltered LIQ book, positive 4/5 years.
