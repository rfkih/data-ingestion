# IDX menu 21 — beyond the two engines: sizing, combination, sector rotation, allocation — 2026-09-26 — 18 trials, cumulative N = 428

Incumbents: value = strict composite, May, rev. 3 (18-22 %/yr, mDD 22-25 %); trend = hi60 / > MA200 / vol >= 1.5x / trail10, K = 10, `small` (+29.9 %/yr, Sharpe 1.34, mDD -30 % to 2026-09-16). Everything below is measured with the same engines, costs and reading rules as menus 6-20.

## A3. Follow-up declared after the operator's question (4 trials, cumulative N = 433): no trading under the 200-day average

regime_gate = no new entry while COMPOSITE < MA200, held names run to their trailing stop; regime_flat = sell everything at the first close under MA200 (next close, at the bid) and stay out until COMPOSITE is back above. Exit and re-entry costs are inside the engine.

| arm | trades | hold d | hit | avg net | payoff | t | CAGR | Sharpe | mDD | years | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| equal 1/K | small | 518 | 23 | 42 % | +3.65 % | 2.23 | 3.2 | +27.7 % | 1.21 | -30 % | 20:+24 21:+64 22:+7 23:-6 24:+6 25:+148 26:-9 | reference |
| regime_gate | small | 407 | 24 | 44 % | +5.47 % | 2.52 | 3.7 | +29.2 % | 1.38 | -17 % | 20:+29 21:+71 22:+1 23:+4 24:+0 25:+135 26:-4 | BETTER / CANDIDATE (rnd Sharpe -0.00) |
| regime_flat | small | 464 | 18 | 41 % | +4.42 % | 2.68 | 3.5 | +25.9 % | 1.27 | -24 % | 20:+24 21:+61 22:-3 23:-4 24:+7 25:+136 26:-5 | no: sharpe<ref+0.15 / tested: years<5 (rnd Sharpe 0.26) |
| equal 1/K | LIQ | 494 | 26 | 37 % | +2.89 % | 2.45 | 2.4 | +17.8 % | 0.87 | -35 % | 20:+32 21:+77 22:-7 23:-13 24:+14 25:+74 26:-23 | reference |
| regime_gate | LIQ | 404 | 26 | 39 % | +3.35 % | 2.46 | 2.5 | +16.1 % | 0.86 | -32 % | 20:+16 21:+88 22:-15 23:-6 24:+4 25:+71 26:-15 | no: sharpe<ref+0.15 / tested: sharpe<1,mdd>25%,years<5,vs random (rnd Sharpe 0.37) |
| regime_flat | LIQ | 494 | 18 | 40 % | +2.66 % | 2.26 | 2.7 | +16.6 % | 0.89 | -32 % | 20:+15 21:+91 22:-21 23:-5 24:+10 25:+75 26:-16 | no: sharpe<ref+0.15 / tested: sharpe<1,mdd>25%,years<5 (rnd Sharpe 0.21) |

2005-2019 (`small`, Yahoo survivors file):

| arm | trades | hold d | hit | avg net | payoff | t | CAGR | Sharpe | mDD | years | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| equal 1/K | 612 | 37 | 41 % | +3.64 % | 2.48 | 4.2 | +13.3 % | 0.89 | -27 % | 05:+5 06:+41 07:+30 08:-10 09:+26 10:+20 11:+8 12:+20 13:+24 14:+7 15:-15 16:+36 17:+19 18:-4 19:+2 | reference |
| regime_gate | 554 | 38 | 43 % | +4.12 % | 2.50 | 4.5 | +14.2 % | 0.96 | -19 % | 05:+3 06:+41 07:+30 08:-3 09:+14 10:+20 11:+8 12:+13 13:+22 14:+10 15:-6 16:+41 17:+19 18:+7 19:+0 | no: sharpe<ref+0.15 (rnd Sharpe 0.85) |
| regime_flat | 599 | 31 | 43 % | +3.37 % | 2.33 | 4.2 | +12.4 % | 0.87 | -23 % | 05:-9 06:+41 07:+29 08:-3 09:+14 10:+27 11:+9 12:+14 13:+19 14:+7 15:-6 16:+44 17:+17 18:-3 19:-4 | no: sharpe<ref+0.15 (rnd Sharpe 0.76) |

