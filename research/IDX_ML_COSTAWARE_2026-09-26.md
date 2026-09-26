# IDX menu ML-6 — cost-aware use of the prediction desk's scores — 2026-09-26 — 10 trials, cumulative N = 751

Position book on LIQ from 2022-01: buy when the expected 5d/20d excess (bps) exceeds margin x the name's round-trip cost, hold until the score turns negative AND a better name pays for the swap (or 60 days). Same OOS scores and costs as ML-4.

| arm (score, margin, ema, K) | trades | hold d | turns/yr/slot | CAGR | Sharpe | mDD | years + | by year | verdict |
|---|---|---|---|---|---|---|---|---|---|
| e5|1|1|10 | 822 | 14 | 17.4 | +23.9 % | 0.78 | -59 % | 3/5 | 22:+7 23:-3 24:+22 25:+142 26:-10 | not a candidate: sharpe 0.78 < 1.2; mdd -59 % < -25 %; 3/5 years positive |
| e5|2|1|10 | 792 | 14 | 16.8 | +22.1 % | 0.75 | -59 % | 3/5 | 22:+3 23:-7 24:+20 25:+161 26:-14 | not a candidate: sharpe 0.75 < 1.2; mdd -59 % < -25 %; 3/5 years positive |
| e5|1|3|10 | 454 | 25 | 9.6 | +22.3 % | 0.77 | -55 % | 3/5 | 22:-25 23:+25 24:+15 25:+164 26:-10 | not a candidate: sharpe 0.77 < 1.2; mdd -55 % < -25 %; 3/5 years positive |
| e5|2|3|10 | 442 | 25 | 9.4 | +28.4 % | 0.91 | -54 % | 4/5 | 22:-22 23:+26 24:+21 25:+173 26:+1 | not a candidate: sharpe 0.91 < 1.2; mdd -54 % < -25 % |
| e5|2|3|5 | 221 | 25 | 9.4 | +36.3 % | 0.98 | -53 % | 3/5 | 22:-27 23:+20 24:+90 25:+180 26:-8 | not a candidate: sharpe 0.98 < 1.2; mdd -53 % < -25 %; 3/5 years positive (placebo pct 100) |
| e20|1|3|10 | 291 | 39 | 6.2 | +2.2 % | 0.24 | -60 % | 3/5 | 22:-33 23:+30 24:+19 25:+86 26:-42 | not a candidate: sharpe 0.24 < 1.2; mdd -60 % < -25 %; 3/5 years positive |
| e20|2|3|10 | 290 | 40 | 6.1 | +2.4 % | 0.25 | -60 % | 3/5 | 22:-33 23:+30 24:+19 25:+88 26:-42 | not a candidate: sharpe 0.25 < 1.2; mdd -60 % < -25 %; 3/5 years positive |
| rank5|2|3|10 | 353 | 32 | 7.5 | +9.2 % | 0.46 | -52 % | 1/5 | 22:-5 23:-11 24:-1 25:+124 26:-19 | not a candidate: sharpe 0.46 < 1.2; mdd -52 % < -25 %; 1/5 years positive |
| blend|2|3|10 | 401 | 28 | 8.5 | +28.5 % | 0.91 | -51 % | 3/5 | 22:-14 23:+16 24:+33 25:+154 26:-3 | not a candidate: sharpe 0.91 < 1.2; mdd -51 % < -25 %; 3/5 years positive |
| e5_gate|2|3|10 | 316 | 28 | 6.7 | +5.4 % | 0.34 | -49 % | 3/5 | 22:-24 23:+7 24:+21 25:+77 26:-27 | not a candidate: sharpe 0.34 < 1.2; mdd -49 % < -25 %; 3/5 years positive |

For scale on the same window: ML-4 fixed cohorts s5/H5 net -20.5 %/yr (gross +26.4 %, Sharpe 0.86); the deployed trend book (small, gate) +20.1 %/yr Sharpe 1.24 mDD -18 %; COMPOSITE ~+5 %/yr.

## Verdict (menu ML-6, study stored)

Best arm: **e5|2|3|5** (+36.3 %/yr, Sharpe 0.98, mDD -53 %, hold 25 d) - not a candidate: sharpe 0.98 < 1.2; mdd -53 % < -25 %; 3/5 years positive.
Candidates: none.
