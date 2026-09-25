# IDX menu ML-6 — cost-aware use of the prediction desk's scores — 2026-09-25 — 10 trials, cumulative N = 751

Position book on LIQ from 2022-01: buy when the expected 5d/20d excess (bps) exceeds margin x the name's round-trip cost, hold until the score turns negative AND a better name pays for the swap (or 60 days). Same OOS scores and costs as ML-4.

| arm (score, margin, ema, K) | trades | hold d | turns/yr/slot | CAGR | Sharpe | mDD | years + | by year | verdict |
|---|---|---|---|---|---|---|---|---|---|
| e5|1|1|10 | 847 | 13 | 17.9 | +11.1 % | 0.48 | -65 % | 3/5 | 22:-24 23:+6 24:+13 25:+113 26:-16 | not a candidate: sharpe 0.48 < 1.2; mdd -65 % < -25 %; 3/5 years positive |
| e5|2|1|10 | 821 | 14 | 17.4 | +10.3 % | 0.46 | -65 % | 3/5 | 22:-28 23:+1 24:+13 25:+106 26:-6 | not a candidate: sharpe 0.46 < 1.2; mdd -65 % < -25 %; 3/5 years positive |
| e5|1|3|10 | 465 | 24 | 9.8 | +22.7 % | 0.77 | -51 % | 4/5 | 22:-21 23:+45 24:+24 25:+43 26:+29 | not a candidate: sharpe 0.77 < 1.2; mdd -51 % < -25 % |
| e5|2|3|10 | 447 | 25 | 9.5 | +29.1 % | 0.91 | -51 % | 4/5 | 22:-24 23:+37 24:+29 25:+83 26:+36 | not a candidate: sharpe 0.91 < 1.2; mdd -51 % < -25 % |
| e5|2|3|5 | 221 | 26 | 9.4 | +41.6 % | 1.04 | -61 % | 4/5 | 22:-44 23:+116 24:+48 25:+63 26:+79 | not a candidate: sharpe 1.04 < 1.2; mdd -61 % < -25 % (placebo pct 100) |
| e20|1|3|10 | 293 | 39 | 6.2 | +5.6 % | 0.34 | -60 % | 2/5 | 22:-25 23:-1 24:+39 25:+63 26:-24 | not a candidate: sharpe 0.34 < 1.2; mdd -60 % < -25 %; 2/5 years positive |
| e20|2|3|10 | 297 | 39 | 6.3 | +4.8 % | 0.32 | -60 % | 2/5 | 22:-25 23:-1 24:+44 25:+58 26:-26 | not a candidate: sharpe 0.32 < 1.2; mdd -60 % < -25 %; 2/5 years positive |
| rank5|2|3|10 | 339 | 34 | 7.2 | +3.2 % | 0.26 | -58 % | 2/5 | 22:-4 23:+9 24:-3 25:+45 26:-22 | not a candidate: sharpe 0.26 < 1.2; mdd -58 % < -25 %; 2/5 years positive |
| blend|2|3|10 | 404 | 28 | 8.6 | +26.0 % | 0.85 | -47 % | 4/5 | 22:-26 23:+44 24:+19 25:+89 26:+23 | not a candidate: sharpe 0.85 < 1.2; mdd -47 % < -25 % |
| e5_gate|2|3|10 | 311 | 29 | 6.6 | +0.5 % | 0.16 | -46 % | 3/5 | 22:-22 23:+9 24:+4 25:+56 26:-26 | not a candidate: sharpe 0.16 < 1.2; mdd -46 % < -25 %; 3/5 years positive |

For scale on the same window: ML-4 fixed cohorts s5/H5 net -20.5 %/yr (gross +26.4 %, Sharpe 0.86); the deployed trend book (small, gate) +20.1 %/yr Sharpe 1.24 mDD -18 %; COMPOSITE ~+5 %/yr.

## Verdict (menu ML-6, study stored)

Best arm: **e5|2|3|5** (+41.6 %/yr, Sharpe 1.04, mDD -61 %, hold 26 d) - not a candidate: sharpe 1.04 < 1.2; mdd -61 % < -25 %.
Candidates: none.
