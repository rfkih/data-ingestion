# IDX menu ML-6b — risk overlays on the cost-aware ML book — 2026-09-26 — 6 trials, cumulative N = 757

Base = ML-6's e5 | margin 2 | ema 3 | K 10 on LIQ from 2022-01 (study #154). Each overlay alone, then the combination.

| arm | trades | hold d | CAGR | Sharpe | mDD | years + | by year | verdict |
|---|---|---|---|---|---|---|---|---|
| base | 442 | 25 | +28.4 % | 0.91 | -54 % | 4/5 | 22:-22 23:+26 24:+21 25:+173 26:+1 | reference |
| trail10 | 838 | 13 | +13.0 % | 0.52 | -54 % | 3/5 | 22:-31 23:+9 24:+21 25:+140 26:-19 | not a candidate: sharpe 0.52 < 1.2; mdd -54 % < -25 %; 3/5 years positive |
| stop15 | 559 | 20 | +16.4 % | 0.63 | -55 % | 3/5 | 22:-18 23:+8 24:+26 25:+104 26:-10 | not a candidate: sharpe 0.63 < 1.2; mdd -55 % < -25 %; 3/5 years positive |
| half_off | 442 | 25 | +17.1 % | 0.72 | -47 % | 3/5 | 22:-23 23:+13 24:+24 25:+103 26:-4 | not a candidate: sharpe 0.72 < 1.2; mdd -47 % < -25 %; 3/5 years positive |
| voltgt | 442 | 25 | +17.8 % | 0.91 | -34 % | 4/5 | 22:-19 23:+20 24:+17 25:+84 26:+3 | not a candidate: sharpe 0.91 < 1.2; mdd -34 % < -25 % (placebo pct 100) |
| liq10 | 385 | 29 | +19.9 % | 0.73 | -48 % | 3/5 | 22:-13 23:+19 24:+5 25:+164 26:-17 | not a candidate: sharpe 0.73 < 1.2; mdd -48 % < -25 %; 3/5 years positive |
| combo | 786 | 14 | -2.4 % | 0.04 | -52 % | 1/5 | 22:-43 23:-3 24:-2 25:+106 26:-20 | not a candidate: sharpe 0.04 < 1.2; mdd -52 % < -25 %; 1/5 years positive |

Deployed trend book on the same window: +20.1 % / 1.24 / -18 %.

## Verdict (menu ML-6b, study stored)

Best arm: **voltgt** (+17.8 %/yr, Sharpe 0.91, mDD -34 %) - not a candidate: sharpe 0.91 < 1.2; mdd -34 % < -25 %.
Candidates: none.
