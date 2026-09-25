# IDX menu ML-7c - two models, one book: lambdarank order + regression gate - 2026-09-25 - 3 trials, cumulative N = 833

Cost-aware book on LIQ from 2022-01 (margin 2, EMA-3); the regression's bps decide who may enter and when a swap pays, the lambdarank percentile decides the order. References = the same book ordered by the regression itself.

| arm | trades | win | avg net | CAGR | Sharpe | mDD | years + | by year | verdict |
|---|---|---|---|---|---|---|---|---|---|
| e5|10 | 434 | 47 % | +3.10 % | +33.3 % | 1.00 | -51 % | 4/5 | 22:-14 23:+36 24:+32 25:+83 26:+36 | reference |
| e5|5 | 220 | 49 % | +4.30 % | +47.3 % | 1.13 | -59 % | 4/5 | 22:-34 23:+117 24:+48 25:+63 26:+79 | reference |
| e5+c5/10|10 | 195 | 56 % | +8.08 % | +40.5 % | 1.50 | -27 % | 5/5 | 22:+7 23:+43 24:+39 25:+91 26:+23 | reference |
| lrorder|10 | 400 | 44 % | +2.01 % | +11.5 % | 0.50 | -54 % | 3/5 | 22:-16 23:+12 24:+11 25:+116 26:-26 | not better than ref | not a candidate: sharpe 0.50 < 1.2; mdd -54 % < -25 %; 3/5 years positive |
| lrorder|5 | 206 | 45 % | +2.01 % | +15.2 % | 0.56 | -57 % | 2/5 | 22:-12 23:-8 24:+32 25:+85 26:-1 | not better than ref | not a candidate: sharpe 0.56 < 1.2; mdd -57 % < -25 %; 2/5 years positive |
| lrorder+c5/10|10 | 163 | 51 % | +8.88 % | +34.6 % | 1.54 | -28 % | 5/5 | 22:+8 23:+21 24:+36 25:+76 26:+31 | not better than ref | not a candidate: mdd -28 % < -25 % (placebo pct 100) |

## Verdict (menu ML-7c, study stored)

BETTER than the reference: none. Money-rule candidates: none. Best: lrorder+c5/10|10 (+34.6 %/yr, Sharpe 1.54, mDD -28 %).
