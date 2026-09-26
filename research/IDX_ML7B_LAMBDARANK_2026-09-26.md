# IDX menu ML-7b — lambdarank 5d through the cost-aware book — 2026-09-26 — 5 trials, cumulative N = 826

Same universe (LIQ), costs, panel, walk-forward years and position book as ML-6 (`idx_ml_costaware.book`); the score is the 3-seed lambdarank 5d percentile gap scaled by the training years' decile spread. References e5|... are ML-6's arms recomputed here.

## Ranking accuracy on this universe: daily rank IC on LIQ vs the 5d return (t) | churn = day-to-day rank corr

| year | lr5 | s5 (deployed regression) |
|---|---|---|
| 2022 | 0.137 (24.8) c0.62 | 0.074 (11.9) c0.73 |
| 2023 | 0.127 (20.8) c0.75 | 0.099 (15.9) c0.77 |
| 2024 | 0.091 (14.2) c0.60 | 0.064 (8.7) c0.73 |
| 2025 | 0.111 (15.9) c0.62 | 0.047 (6.1) c0.76 |
| 2026 | 0.098 (10.1) c0.67 | 0.061 (4.5) c0.76 |

## The book

| arm (score, margin, ema, K) | trades | hold d | turns/yr/slot | CAGR | Sharpe | mDD | years + | by year | verdict |
|---|---|---|---|---|---|---|---|---|---|
| e5|2|3|10 | 439 | 25 | 9.3 | +27.4 % | 0.89 | -54 % | 4/5 | 22:-25 23:+26 24:+21 25:+173 26:+1 | reference |
| e5|2|3|5 | 219 | 25 | 9.3 | +31.4 % | 0.89 | -53 % | 3/5 | 22:-39 23:+20 24:+90 25:+180 26:-8 | reference |
| lr5|2|3|10 | 368 | 31 | 7.8 | +24.2 % | 0.89 | -49 % | 2/5 | 22:-16 23:-3 24:+25 25:+204 26:-9 | not a candidate: sharpe 0.89 < 1.2; mdd -49 % < -25 %; 2/5 years positive | not better than ML-6 ref |
| lr5|2|3|5 | 174 | 33 | 7.4 | -2.5 % | 0.09 | -48 % | 2/5 | 22:-8 23:-5 24:+22 25:+18 26:-30 | not a candidate: sharpe 0.09 < 1.2; mdd -48 % < -25 %; 2/5 years positive | not better than ML-6 ref |
| lr5|1|3|10 | 363 | 32 | 7.7 | +26.9 % | 0.96 | -49 % | 2/5 | 22:-16 23:-2 24:+36 25:+204 26:-9 | not a candidate: sharpe 0.96 < 1.2; mdd -49 % < -25 %; 2/5 years positive | not better than ML-6 ref |
| lr5|2|1|10 | 882 | 13 | 18.7 | +43.8 % | 1.28 | -47 % | 4/5 | 22:+10 23:-0 24:+23 25:+280 26:+8 | not a candidate: mdd -47 % < -25 % | BETTER than ML-6 ref (placebo pct 100) |
| lrblend|2|3|10 | 363 | 31 | 7.7 | +39.3 % | 1.22 | -42 % | 5/5 | 22:+6 23:+2 24:+19 25:+204 26:+22 | not a candidate: mdd -42 % < -25 % | BETTER than ML-6 ref |

## Verdict (menu ML-7b, study stored)

Best arm: **lr5|2|1|10** (+43.8 %/yr, Sharpe 1.28, mDD -47 %, hold 13 d) - not a candidate: mdd -47 % < -25 % | BETTER than ML-6 ref.
CANDIDATES (ML-6 bar): none. BETTER than the ML-6 reference with the same K: lr5|2|1|10, lrblend|2|3|10.
