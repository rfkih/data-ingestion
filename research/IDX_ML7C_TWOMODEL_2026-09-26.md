# IDX menu ML-7c - two models, one book: lambdarank order + regression gate - 2026-09-26 - 3 trials, cumulative N = 833

Cost-aware book on LIQ from 2022-01 (margin 2, EMA-3); the regression's bps decide who may enter and when a swap pays, the lambdarank percentile decides the order. References = the same book ordered by the regression itself.

| arm | trades | win | avg net | CAGR | Sharpe | mDD | years + | by year | verdict |
|---|---|---|---|---|---|---|---|---|---|
| e5|10 | 429 | 42 % | +4.17 % | +27.6 % | 0.89 | -54 % | 4/5 | 22:-25 23:+27 24:+21 25:+173 26:+1 | reference |
| e5|5 | 214 | 43 % | +4.79 % | +31.4 % | 0.89 | -53 % | 3/5 | 22:-39 23:+20 24:+90 25:+180 26:-8 | reference |
| e5+c5/10|10 | 208 | 44 % | +6.71 % | +30.0 % | 1.23 | -41 % | 3/5 | 22:-12 23:+24 24:+41 25:+127 26:-1 | reference |
| lrorder|10 | 392 | 46 % | +4.44 % | +34.6 % | 1.11 | -43 % | 5/5 | 22:+9 23:+18 24:+17 25:+161 26:+4 | BETTER than ref | not a candidate: sharpe 1.11 < 1.2; mdd -43 % < -25 % |
| lrorder|5 | 197 | 49 % | +6.67 % | +56.1 % | 1.39 | -48 % | 4/5 | 22:+42 23:+53 24:+44 25:+180 26:-6 | BETTER than ref | not a candidate: mdd -48 % < -25 % |
| lrorder+c5/10|10 | 173 | 55 % | +7.69 % | +31.0 % | 1.46 | -27 % | 5/5 | 22:+10 23:+6 24:+28 25:+105 26:+17 | BETTER than ref | not a candidate: mdd -27 % < -25 %; placebo pct 85 (placebo pct 85) |

## Verdict (menu ML-7c, study stored)

BETTER than the reference: lrorder|10, lrorder|5, lrorder+c5/10|10. Money-rule candidates: none. Best: lrorder+c5/10|10 (+31.0 %/yr, Sharpe 1.46, mDD -27 %).
