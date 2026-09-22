# IDX menu 21 — beyond the two engines: sizing, combination, sector rotation, allocation — 2026-09-22 — 18 trials, cumulative N = 428

Incumbents: value = strict composite, May, rev. 3 (18-22 %/yr, mDD 22-25 %); trend = hi60 / > MA200 / vol >= 1.5x / trail10, K = 10, `small` (+29.9 %/yr, Sharpe 1.34, mDD -30 % to 2026-09-16). Everything below is measured with the same engines, costs and reading rules as menus 6-20.

## A3. Follow-up declared after the operator's question (4 trials, cumulative N = 433): no trading under the 200-day average

regime_gate = no new entry while COMPOSITE < MA200, held names run to their trailing stop; regime_flat = sell everything at the first close under MA200 (next close, at the bid) and stay out until COMPOSITE is back above. Exit and re-entry costs are inside the engine.

| arm | trades | hold d | hit | avg net | payoff | t | CAGR | Sharpe | mDD | years | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| equal 1/K | small | 496 | 24 | 42 % | +4.10 % | 2.38 | 3.4 | +29.5 % | 1.31 | -30 % | 20:+24 21:+65 22:+29 23:-5 24:+1 25:+131 26:-8 | reference |
| regime_gate | small | 381 | 26 | 44 % | +6.30 % | 2.74 | 3.9 | +32.1 % | 1.54 | -18 % | 20:+23 21:+65 22:+24 23:-3 24:+5 25:+147 26:-5 | BETTER / CANDIDATE (rnd Sharpe 0.73) |
| regime_flat | small | 445 | 18 | 41 % | +4.95 % | 2.88 | 3.7 | +28.5 % | 1.42 | -23 % | 20:+19 21:+58 22:+17 23:-4 24:+7 25:+135 26:-5 | no: sharpe<ref+0.15 / CANDIDATE (rnd Sharpe 0.41) |
| equal 1/K | LIQ | 480 | 27 | 38 % | +3.10 % | 2.51 | 2.5 | +19.1 % | 0.92 | -36 % | 20:+32 21:+83 22:-4 23:-12 24:+12 25:+76 26:-22 | reference |
| regime_gate | LIQ | 385 | 28 | 39 % | +3.75 % | 2.56 | 2.7 | +17.4 % | 0.93 | -28 % | 20:+16 21:+90 22:-14 23:-2 24:+5 25:+72 26:-16 | no: sharpe<ref+0.15 / tested: sharpe<1,mdd>25%,years<5 (rnd Sharpe 0.37) |
| regime_flat | LIQ | 484 | 18 | 41 % | +2.68 % | 2.23 | 2.7 | +16.6 % | 0.90 | -30 % | 20:+15 21:+92 22:-20 23:-1 24:+8 25:+70 26:-16 | no: sharpe<ref+0.15 / tested: sharpe<1,mdd>25%,years<5 (rnd Sharpe -0.08) |

2005-2019 (`small`, Yahoo survivors file):

| arm | trades | hold d | hit | avg net | payoff | t | CAGR | Sharpe | mDD | years | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| equal 1/K | 612 | 37 | 41 % | +3.64 % | 2.48 | 4.2 | +13.3 % | 0.89 | -27 % | 05:+5 06:+41 07:+30 08:-10 09:+26 10:+20 11:+8 12:+20 13:+24 14:+7 15:-15 16:+36 17:+19 18:-4 19:+2 | reference |
| regime_gate | 554 | 38 | 43 % | +4.12 % | 2.50 | 4.5 | +14.2 % | 0.96 | -19 % | 05:+3 06:+41 07:+30 08:-3 09:+14 10:+20 11:+8 12:+13 13:+22 14:+10 15:-6 16:+41 17:+19 18:+7 19:+0 | no: sharpe<ref+0.15 (rnd Sharpe 0.85) |
| regime_flat | 599 | 31 | 43 % | +3.37 % | 2.33 | 4.2 | +12.4 % | 0.87 | -23 % | 05:-9 06:+41 07:+29 08:-3 09:+14 10:+27 11:+9 12:+14 13:+19 14:+7 15:-6 16:+44 17:+17 18:-3 19:-4 | no: sharpe<ref+0.15 (rnd Sharpe 0.76) |

