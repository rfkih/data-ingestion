# IDX menu 7 — robustness of the trend lead + fundamental gate — 2026-09-26 — 10 trials, cumulative N = 287

| arm | trades | hold d | hit | avg net | payoff | t | total | CAGR | Sharpe | mDD | years | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| lead 60/10/1.5 (LIQ) | 494 | 26 | 37 % | +2.89 % | 2.45 | 2.4 | +190 % | +18.0 % | 0.88 | -35 % | 20:+32 21:+77 22:-7 23:-13 24:+14 25:+74 26:-22 | reference (menu 6) |
| random + trail10 (LIQ) | 471 | 32 | 35 % | +1.96 % | 2.46 | 1.5 | +69 % | +8.5 % | 0.48 | -48 % | 20:+36 21:+33 22:-18 23:-9 24:+2 25:+15 26:+5 | reference |
| trail8 (60, 0.08, 1.5) | 656 | 19 | 38 % | +1.18 % | 2.00 | 1.5 | +81 % | +9.6 % | 0.56 | -32 % | 20:+21 21:+60 22:-13 23:-15 24:+15 25:+28 26:-15 | tested: t<2.5,sharpe<1,mdd>25%,years<5/7,vs random |
| trail12 (60, 0.12, 1.5) | 382 | 34 | 35 % | +2.30 % | 2.50 | 1.6 | +89 % | +10.4 % | 0.57 | -38 % | 20:+32 21:+31 22:-2 23:-12 24:+3 25:+52 26:-19 | tested: t<2.5,sharpe<1,mdd>25%,years<5/7,vs random |
| trail15 (60, 0.15, 1.5) | 257 | 52 | 39 % | +3.86 % | 2.37 | 2.1 | +172 % | +16.8 % | 0.84 | -37 % | 20:+32 21:+36 22:+25 23:-9 24:-7 25:+37 26:+6 | tested: t<2.5,sharpe<1,mdd>25%,vs random |
| hi40 (40, 0.1, 1.5) | 518 | 25 | 37 % | +1.80 % | 2.17 | 1.7 | +106 % | +11.9 % | 0.62 | -44 % | 20:+30 21:+63 22:+9 23:-25 24:-3 25:+30 26:-6 | tested: t<2.5,sharpe<1,mdd>25%,years<5/7,vs random |
| hi90 (90, 0.1, 1.5) | 489 | 26 | 39 % | +2.27 % | 2.13 | 2.0 | +130 % | +13.8 % | 0.72 | -31 % | 20:+32 21:+63 22:-13 23:-12 24:+4 25:+54 26:-13 | tested: t<2.5,sharpe<1,mdd>25%,years<5/7,vs random |
| vol1 (60, 0.1, 1.0) | 512 | 26 | 34 % | +1.32 % | 2.32 | 1.2 | +51 % | +6.6 % | 0.41 | -42 % | 20:+31 21:+43 22:-12 23:-24 24:+4 25:+50 26:-22 | tested: t<2.5,sharpe<1,mdd>25%,years<5/7,vs random |
| vol2 (60, 0.1, 2.0) | 485 | 26 | 37 % | +1.79 % | 2.16 | 1.7 | +96 % | +11.0 % | 0.59 | -34 % | 20:+29 21:+40 22:+4 23:-16 24:+6 25:+51 26:-22 | tested: t<2.5,sharpe<1,mdd>25%,vs random |
| loose | 402 | 31 | 36 % | +0.76 % | 2.00 | 0.8 | +39 % | +5.3 % | 0.37 | -43 % | 20:+23 21:+33 22:-2 23:-22 24:+1 25:+36 26:-19 | tested: t<2.5,sharpe<1,mdd>25%,years<5/7,vs random | not steadier |
| strict | 319 | 35 | 38 % | +1.47 % | 2.09 | 1.1 | +39 % | +5.2 % | 0.40 | -44 % | 20:+15 21:+10 22:-4 23:-14 24:-9 25:+52 26:-3 | tested: t<2.5,sharpe<1,mdd>25%,years<5/7,vs random | not steadier |
| small | 518 | 23 | 42 % | +3.65 % | 2.23 | 3.2 | +385 % | +27.7 % | 1.21 | -30 % | 20:+24 21:+64 22:+7 23:-6 24:+6 25:+148 26:-9 | tested: mdd>25% |

Candidates by the menu-6 rule: 0 of 10.
Robustness read: 2 of 7 neighbours have CAGR >= 10 % with t >= 2.0 -> the lead is **FRAGILE** (recorded as luck).
Gated arms: loose not steadier (mDD -43 % vs -35 %, CAGR +5.3 % vs +18.0 %); strict not steadier (mDD -44 %, CAGR +5.2 %).

Limits: as menu 6; the fundamental gate is point-in-time by publication date, evaluated monthly.
