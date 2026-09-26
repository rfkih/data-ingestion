# IDX menu ML-4b — cost-aware strategies on the prediction desk's scores — 2026-09-26 — 8 trials, cumulative N = 731

Same OOS scores and costs as ML-4 (#151). Round trip: LIQ 91 bps, BLUE 70 bps. Hysteresis books hold while the name stays in the top 30 % of the day's ranking, max 60 days. Book 2022-01 -> 2026-09-25.

| arm | hold | K | trades | CAGR | Sharpe | mDD | years + | by year | verdict |
|---|---|---|---|---|---|---|---|---|---|
| blue5 | 5 | 5 | 5,625 | -29.6 % | -0.78 | -83 % | 0/5 | 22:-29 23:-14 24:-21 25:-6 26:-58 | not a candidate: sharpe -0.78 < 1.2; mdd -83 % < -25 %; 0/5 years positive |
| blue20 | 20 | 5 | 5,550 | -11.8 % | -0.19 | -62 % | 2/5 | 22:-24 23:-13 24:+3 25:+45 26:-45 | not a candidate: sharpe -0.19 < 1.2; mdd -62 % < -25 %; 2/5 years positive |
| liq5_top3 | 5 | 3 | 3,375 | -17.2 % | -0.17 | -78 % | 1/5 | 22:-60 23:-22 24:-2 25:+140 26:-44 | not a candidate: sharpe -0.17 < 1.2; mdd -78 % < -25 %; 1/5 years positive |
| hyst5_liq | hyst(2 d) | 10 | 5,347 | -7.9 % | 0.10 | -76 % | 1/5 | 22:-34 23:-35 24:-20 25:+201 26:-33 | not a candidate: sharpe 0.10 < 1.2; mdd -76 % < -25 %; 1/5 years positive (placebo pct 100) |
| hyst5_blue | hyst(2 d) | 5 | 2,495 | -34.2 % | -0.51 | -90 % | 1/5 | 22:-32 23:-35 24:-38 25:+67 26:-70 | not a candidate: sharpe -0.51 < 1.2; mdd -90 % < -25 %; 1/5 years positive |
| hyst20_liq | hyst(3 d) | 10 | 3,247 | -29.5 % | -0.55 | -85 % | 1/5 | 22:-54 23:-42 24:-24 25:+94 26:-51 | not a candidate: sharpe -0.55 < 1.2; mdd -85 % < -25 %; 1/5 years positive |
| blend_hyst | hyst(3 d) | 10 | 4,327 | -19.1 % | -0.22 | -79 % | 1/5 | 22:-33 23:-52 24:-23 25:+188 26:-49 | not a candidate: sharpe -0.22 < 1.2; mdd -79 % < -25 %; 1/5 years positive |
| avoid250 | 250 | all-30% | 106,871 | +0.1 % | 0.04 | -10 % | 2/5 | 22:-4 23:-2 24:+1 25:+8 26:-2 | loser filter INFORMATIVE: excess +1.2 %/yr over the unfiltered LIQ book, positive 4/5 years |

| reference | CAGR | Sharpe | mDD |
|---|---|---|---|
| random_blue_H5 | -34.1 % | -1.81 | -87 % |
| random_blue_H20 | -13.2 % | -0.59 | -60 % |
| liq_all_H250 | -1.2 % | -0.19 | -20 % |

avoid250 excess by year vs the unfiltered LIQ book: 2022:+2.8 2023:+4.5 2024:+1.2 2025:-4.7 2026:+1.3

## Verdict (menu ML-4b, study stored)

Best arm by Sharpe: **hyst5_liq** (-7.9 %/yr, Sharpe 0.10, mDD -76 %) - not a candidate: sharpe 0.10 < 1.2; mdd -76 % < -25 %; 1/5 years positive.
Candidates: none. loser filter INFORMATIVE: excess +1.2 %/yr over the unfiltered LIQ book, positive 4/5 years.
