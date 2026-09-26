# IDX menu ML-4 — strategies on the prediction desk's models — 2026-09-26 — 12 trials, cumulative N = 723

Walk-forward scores by test year (fit on purged earlier rows), LIQ universe (60-day value >= Rp 5 bn, close >= Rp 100), closing offer/bid + Stockbit fees, rolling cohorts of K names held H days (slot 1/(K*H)). Book 2022-01 -> 2026-09-25.

| arm | H | K | trades | CAGR | Sharpe | mDD | years + | by year | placebo pct | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| ml5 | 5 | 10 | 11,250 | -27.0 % | -0.75 | -82 % | 1/5 | 22:-54 23:-26 24:-25 25:+60 26:-44 | - | not a candidate: sharpe -0.75 < 1.2; mdd -82 % < -25 %; 1/5 years positive |
| ml5_gate | 5 | 10 | 6,660 | -21.2 % | -0.99 | -69 % | 1/5 | 22:-55 23:-11 24:-19 25:+28 26:-22 | - | not a candidate: sharpe -0.99 < 1.2; mdd -69 % < -25 %; 1/5 years positive |
| ml5_dir | 5 | 10 | 11,250 | -22.3 % | -0.95 | -78 % | 1/5 | 22:-39 23:-26 24:-34 25:+63 26:-37 | - | not a candidate: sharpe -0.95 < 1.2; mdd -78 % < -25 %; 1/5 years positive |
| ml5_k5 | 5 | 5 | 5,625 | -26.2 % | -0.56 | -84 % | 1/5 | 22:-64 23:-37 24:-9 25:+115 26:-46 | - | not a candidate: sharpe -0.56 < 1.2; mdd -84 % < -25 %; 1/5 years positive |
| ml20 | 20 | 10 | 11,100 | +1.2 % | 0.20 | -59 % | 3/5 | 22:-26 23:+4 24:+21 25:+87 26:-40 | - | not a candidate: sharpe 0.20 < 1.2; mdd -59 % < -25 %; 3/5 years positive |
| ml20_gate | 20 | 10 | 6,660 | -3.0 % | -0.05 | -43 % | 3/5 | 22:-28 23:+3 24:+17 25:+43 26:-30 | - | not a candidate: sharpe -0.05 < 1.2; mdd -43 % < -25 %; 3/5 years positive |
| ml250 | 250 | 10 | 8,800 | -3.9 % | -0.19 | -36 % | 2/5 | 22:-20 23:-9 24:+9 25:+15 26:-9 | - | not a candidate: sharpe -0.19 < 1.2; mdd -36 % < -25 %; 2/5 years positive; vs random -0.13 + 0.5 |
| ml250_fund | 250 | 10 | 8,800 | +0.5 % | 0.11 | -33 % | 2/5 | 22:-10 23:-14 24:+10 25:+21 26:-1 | - | not a candidate: sharpe 0.11 < 1.2; mdd -33 % < -25 %; 2/5 years positive; vs random -0.13 + 0.5 |
| combo20 | 20 | 10 | 11,100 | +5.7 % | 0.36 | -55 % | 2/5 | 22:-18 23:+11 24:-8 25:+118 26:-29 | 100 | not a candidate: sharpe 0.36 < 1.2; mdd -55 % < -25 %; 2/5 years positive |
| combo20_gate | 20 | 10 | 6,660 | +3.0 % | 0.26 | -39 % | 2/5 | 22:-15 23:+1 24:-8 25:+86 26:-21 | 100 | not a candidate: sharpe 0.26 < 1.2; mdd -39 % < -25 %; 2/5 years positive |
| trend_ml | 20 | 10 | 4,411 | +1.7 % | 0.21 | -34 % | 1/5 | 22:-10 23:-0 24:-1 25:+60 26:-23 | - | not a candidate: sharpe 0.21 < 1.2; mdd -34 % < -25 %; 1/5 years positive |
| brok20 | 20 | 10 | 2,210 | -30.1 % | -0.44 | -59 % | 1/2 | 25:+16 26:-40 | - | informative only (one year of broker flow); sharpe -0.44 < 1.2; mdd -59 % < -25 %; 1/2 years positive; vs random -0.80 + 0.5 |

| reference | CAGR | Sharpe | mDD |
|---|---|---|---|
| random_H5 | -41.2 % | -2.37 | -93 % |
| random_H20 | -16.7 % | -0.80 | -68 % |
| random_H250 | -2.5 % | -0.13 | -41 % |
| mom60_H20 | -30.0 % | -0.83 | -87 % |
| composite | -1.4 % | 0.00 | -42 % |

Deployed comparables (ROI scorecard #roi_scorecard): value strict annual 21.8 % / 1.06 / -23 %; trend small + gate 32.1 % / 1.54 / -18 %; value 50 / trend 50 gated 27.7 % / 1.54 / -15 %.

## Verdict (menu ML-4, study stored)

Best arm by Sharpe: **combo20** (+5.7 %/yr, Sharpe 0.36, mDD -55 %) - not a candidate: sharpe 0.36 < 1.2; mdd -55 % < -25 %; 2/5 years positive.
Candidates: none.
