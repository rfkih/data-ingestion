# IDX menu 6 — trend following with trailing exits — 2026-09-26 — 10 trials, cumulative N = 277

Book of K = 10 slots, entry close t+1 @offer, exit close t+1 @bid, fees 0.10/0.20 %; 2020-01-02 -> 2026-09-16. COMPOSITE buy-and-hold +2.4 % | 20:-5 21:+8 22:+3 23:+6 24:-3 25:+21 26:-26

| arm (entry|exit|universe) | trades | avg hold d | hit | avg net | median | payoff | t | total | CAGR | Sharpe | mDD | years | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| random entries | ma20 | BLUE | 3672 | 4 | 33 % | -0.59 % | -1.05 % | 1.49 | -4.5 | -90 % | -30.5 % | -1.37 | -93 % | 20:+3 21:-10 22:-43 23:-49 24:-29 25:-3 26:-48 | reference |
| random entries | trail10 | BLUE | 427 | 35 | 36 % | +1.34 % | -4.95 % | 2.18 | 1.5 | +68 % | +8.3 % | 0.48 | -40 % | 20:+63 21:+3 22:-13 23:-2 24:+8 25:+40 26:-23 | reference |
| hi60 | ma20 | BLUE | 571 | 15 | 35 % | -0.07 % | -2.78 % | 1.85 | -0.1 | -6 % | -1.0 % | 0.03 | -50 % | 20:+9 21:+24 22:-24 23:-16 24:-13 25:+33 26:-6 | tested: t<2.5,sharpe<1,mdd>25%,years<5/7 |
| hi60 | ma50 | BLUE | 324 | 34 | 34 % | -0.05 % | -3.78 % | 1.90 | -0.0 | +2 % | +0.2 % | 0.11 | -42 % | 20:+12 21:+6 22:-10 23:-16 24:+1 25:+17 26:-6 | tested: t<2.5,sharpe<1,mdd>25%,years<5/7 |
| hi60 | trail10 | BLUE | 333 | 32 | 36 % | +0.64 % | -4.87 % | 1.99 | 0.6 | +14 % | +2.1 % | 0.21 | -35 % | 20:+14 21:+16 22:-11 23:-13 24:-3 25:+18 26:-2 | tested: t<2.5,sharpe<1,mdd>25%,years<5/7,vs random |
| cross | ma20 | BLUE | 392 | 11 | 30 % | -1.11 % | -2.16 % | 1.64 | -2.1 | -33 % | -6.1 % | -0.52 | -40 % | 20:+1 21:-2 22:-8 23:-12 24:-9 25:-9 26:-0 | tested: t<2.5,sharpe<1,mdd>25%,years<5/7 |
| cross | ma50 | BLUE | 335 | 24 | 29 % | +0.01 % | -2.91 % | 2.49 | 0.0 | -0 % | -0.1 % | 0.08 | -33 % | 20:+5 21:+13 22:-10 23:-16 24:+2 25:-0 26:+8 | tested: t<2.5,sharpe<1,mdd>25%,years<5/7 |
| cross | trail10 | BLUE | 267 | 38 | 30 % | -2.42 % | -5.93 % | 1.48 | -3.0 | -40 % | -7.5 % | -0.49 | -54 % | 20:+5 21:+2 22:-13 23:-17 24:-16 25:-14 26:+9 | tested: t<2.5,sharpe<1,mdd>25%,years<5/7,vs random |
| momq | ma20 | BLUE | 1069 | 10 | 29 % | -0.10 % | -2.30 % | 2.43 | -0.2 | -37 % | -6.9 % | -0.23 | -59 % | 20:+9 21:+16 22:-34 23:-9 24:-10 25:+43 26:-35 | tested: t<2.5,sharpe<1,mdd>25%,years<5/7 |
| momq | ma50 | BLUE | 451 | 29 | 34 % | +1.78 % | -3.28 % | 2.54 | 1.4 | +75 % | +9.0 % | 0.48 | -45 % | 20:+22 21:+51 22:-13 23:-3 24:-9 25:+73 26:-28 | tested: t<2.5,sharpe<1,mdd>25%,years<5/7 |
| momq | trail10 | BLUE | 529 | 25 | 34 % | +0.69 % | -5.39 % | 2.18 | 0.6 | -7 % | -1.1 % | 0.06 | -49 % | 20:+30 21:+19 22:-21 23:-4 24:-5 25:+40 26:-40 | tested: t<2.5,sharpe<1,mdd>25%,years<5/7,vs random |
| hi60 | trail10 | LIQ | 494 | 26 | 37 % | +2.89 % | -5.78 % | 2.45 | 2.4 | +190 % | +18.0 % | 0.88 | -35 % | 20:+32 21:+77 22:-7 23:-13 24:+14 25:+74 26:-22 | tested: t<2.5,sharpe<1,mdd>25%,years<5/7,vs random |

Reading rule applied as declared: 0 candidate(s) of 10.

Limits: current listing board (not PIT); signals and exits one day late (close-to-close); no quality gate beyond liquidity; dividends
ignored; costs = quoted closing spread + fees, no extra slippage; positions still open at the last bar are marked, not counted as trades.
