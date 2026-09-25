# IDX menu ML-6b — risk overlays on the cost-aware ML book — 2026-09-25 — 6 trials, cumulative N = 757

Base = ML-6's e5 | margin 2 | ema 3 | K 10 on LIQ from 2022-01 (study #154). Each overlay alone, then the combination.

| arm | trades | hold d | CAGR | Sharpe | mDD | years + | by year | verdict |
|---|---|---|---|---|---|---|---|---|
| base | 447 | 25 | +29.1 % | 0.91 | -51 % | 4/5 | 22:-24 23:+37 24:+29 25:+83 26:+36 | reference |
| trail10 | 901 | 12 | +2.0 % | 0.25 | -67 % | 3/5 | 22:-22 23:+18 24:+13 25:+47 26:-29 | not a candidate: sharpe 0.25 < 1.2; mdd -67 % < -25 %; 3/5 years positive |
| stop15 | 589 | 19 | +15.9 % | 0.60 | -58 % | 4/5 | 22:-29 23:+24 24:+23 25:+83 26:+2 | not a candidate: sharpe 0.60 < 1.2; mdd -58 % < -25 % |
| half_off | 447 | 25 | +16.2 % | 0.68 | -45 % | 4/5 | 22:-24 23:+26 24:+18 25:+56 26:+15 | not a candidate: sharpe 0.68 < 1.2; mdd -45 % < -25 % |
| voltgt | 447 | 25 | +17.2 % | 0.89 | -39 % | 4/5 | 22:-25 23:+20 24:+24 25:+50 26:+28 | not a candidate: sharpe 0.89 < 1.2; mdd -39 % < -25 % (placebo pct 100) |
| liq10 | 411 | 27 | +8.7 % | 0.43 | -54 % | 4/5 | 22:-41 23:+4 24:+6 25:+124 26:+1 | not a candidate: sharpe 0.43 < 1.2; mdd -54 % < -25 % |
| combo | 824 | 13 | -6.0 % | -0.08 | -52 % | 3/5 | 22:-36 23:+2 24:+6 25:+47 26:-27 | not a candidate: sharpe -0.08 < 1.2; mdd -52 % < -25 %; 3/5 years positive |

Deployed trend book on the same window: +20.1 % / 1.24 / -18 %.

## Verdict (menu ML-6b, study stored)

Best arm: **voltgt** (+17.2 %/yr, Sharpe 0.89, mDD -39 %) - not a candidate: sharpe 0.89 < 1.2; mdd -39 % < -25 %.
Candidates: none.
