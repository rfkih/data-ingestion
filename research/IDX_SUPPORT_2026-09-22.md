# IDX menu 20 — buy at support, sell at resistance — 2026-09-22 — 4 trials, cumulative N = 410

Entry: close within 2 % of the 60-day low on an up day, ranked by liquidity; buy close t+1 @offer. res60 = sell at the 60-day high that stood at entry or stop 7 % below entry; trail10 = deployed trailing stop. K = 10, fees 0.10/0.20 % + closing spread, 2020-01 -> 2026-09-21.

| arm | trades | hold d | hit | avg net | payoff | t | CAGR | Sharpe | mDD | years | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| sup60|res60|BLUE | 263 | 51 | 29 % | -1.27 % | 2.04 | -1.3 | -4.1 % | -0.17 | -43 % | 20:+12 21:+0 22:-2 23:-17 24:+1 25:-12 26:-6 | tested: t<2.5,sharpe<1,mdd>25%,years<5/7,vs random |
| random|res60|BLUE | 515 | 29 | 37 % | -0.59 % | 1.51 | -0.8 | -5.6 % | -0.17 | -55 % | 20:+17 21:-5 22:-5 23:-6 24:-19 25:+6 26:-20 | reference |
| sup60|trail10|BLUE | 302 | 45 | 36 % | +0.15 % | 1.85 | 0.2 | +0.2 % | 0.09 | -34 % | 20:+17 21:-4 22:+12 23:-12 24:-4 25:+0 26:-6 | tested: t<2.5,sharpe<1,mdd>25%,years<5/7,vs random |
| random|trail10|BLUE | 433 | 35 | 32 % | -0.18 % | 2.03 | -0.2 | -1.2 % | 0.05 | -43 % | 20:+11 21:-12 22:+2 23:+3 24:-2 25:+22 26:-24 | reference |
| trend hi60|trail10|BLUE | 333 | 32 | 36 % | +0.68 % | 2.01 | 0.6 | +2.5 % | 0.24 | -35 % | 20:+14 21:+18 22:-11 23:-13 24:-3 25:+18 26:-2 | reference (the deployed idea, opposite entry) |
| sup60|res60|LIQ | 292 | 48 | 27 % | -0.70 % | 2.40 | -0.6 | -2.9 % | -0.08 | -45 % | 20:+13 21:+2 22:-20 23:-10 24:+1 25:+3 26:-4 | tested: t<2.5,sharpe<1,mdd>25%,years<5/7,vs random |
| random|res60|LIQ | 473 | 32 | 35 % | -0.47 % | 1.74 | -0.5 | -5.9 % | -0.18 | -68 % | 20:+67 21:-5 22:+1 23:-14 24:-27 25:-2 26:-32 | reference |
| sup60|trail10|LIQ | 320 | 45 | 36 % | +2.84 % | 2.67 | 1.7 | +7.3 % | 0.50 | -42 % | 20:+30 21:+34 22:-7 23:-10 24:+3 25:+26 26:-17 | tested: t<2.5,sharpe<1,mdd>25%,years<5/7,vs random |
| random|trail10|LIQ | 458 | 33 | 34 % | +1.12 % | 2.26 | 1.1 | +3.2 % | 0.25 | -50 % | 20:+65 21:+8 22:-11 23:+4 24:-23 25:+52 26:-36 | reference |
| trend hi60|trail10|LIQ | 480 | 27 | 38 % | +3.10 % | 2.51 | 2.5 | +19.1 % | 0.92 | -36 % | 20:+32 21:+83 22:-4 23:-12 24:+12 25:+76 26:-22 | reference (the deployed idea, opposite entry) |

Reading rule applied as declared: 0 candidate(s) of 4.
