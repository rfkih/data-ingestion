# IDX menu 22 — validating regime_gate — 2026-09-26 — 12 trials, cumulative N = 445

Candidate: deployed trend rule + no new entry while COMPOSITE < MA200 (signal close). `small`, 2020-01-02 -> 2026-09-21.

## The candidate against the deployed rule

| arm | trades | hit | avg net | t | CAGR | Sharpe | mDD | years | read |
|---|---|---|---|---|---|---|---|---|---|
| deployed (equal 1/K, no gate) | 518 | 42 % | +3.65 % | 3.2 | +27.7 % | 1.21 | -30 % | 20:+24 21:+64 22:+7 23:-6 24:+6 25:+148 26:-9 | reference |
| regime_gate | 407 | 44 % | +5.47 % | 3.7 | +29.2 % | 1.38 | -17 % | 20:+29 21:+71 22:+1 23:+4 24:+0 25:+135 26:-4 | candidate |

## V1. Regime neighbours (6 trials) — FRAGILE (1/6 pass: Sharpe >= ungated + 0.10 and shallower mDD)

| arm | trades | hit | avg net | t | CAGR | Sharpe | mDD | years | read |
|---|---|---|---|---|---|---|---|---|---|
| ma100 (off 37 % of days) | 375 | 43 % | +3.93 % | 3.1 | +21.7 % | 1.13 | -21 % | 20:+24 21:+19 22:+3 23:+16 24:-5 25:+104 26:+4 | fail: sharpe / CANDIDATE |
| ma150 (off 33 % of days) | 390 | 43 % | +4.18 % | 3.3 | +22.6 % | 1.16 | -17 % | 20:+24 21:+15 22:+7 23:+5 24:+1 25:+143 26:-5 | fail: sharpe / CANDIDATE |
| ma250 (off 28 % of days) | 404 | 45 % | +4.65 % | 3.6 | +26.2 % | 1.29 | -23 % | 20:+24 21:+64 22:+6 23:+3 24:+1 25:+118 26:-7 | fail: sharpe / CANDIDATE |
| ma200_buf (off 30 % of days) | 385 | 44 % | +4.98 % | 3.4 | +25.2 % | 1.26 | -21 % | 20:+24 21:+64 22:+8 23:-9 24:+2 25:+120 26:-6 | fail: sharpe / tested: vs random |
| lq45_ma200 (off 46 % of days) | 303 | 40 % | +5.12 % | 3.1 | +20.0 % | 1.11 | -14 % | 20:+24 21:+25 22:+8 23:+7 24:+2 25:+84 26:-4 | fail: sharpe / CANDIDATE |
| breadth50 (off 56 % of days) | 338 | 43 % | +6.37 % | 3.6 | +27.2 % | 1.37 | -29 % | 20:+24 21:+38 22:+23 23:+8 24:+2 25:+155 26:-20 | PASS / tested: mdd>25% |

## V2. Entry-rule neighbours, ungated vs gated (5 trials) — NOT ADDITIVE (2/5)

| arm | trades | hit | avg net | t | CAGR | Sharpe | mDD | years | read |
|---|---|---|---|---|---|---|---|---|---|
| trail12 ungated | 401 | 35 % | +2.71 % | 1.9 | +14.0 % | 0.73 | -36 % | 20:+24 21:+37 22:+3 23:-3 24:+4 25:+59 26:-16 | twin |
| trail12 gated | 328 | 35 % | +3.54 % | 2.1 | +12.5 % | 0.72 | -32 % | 20:+28 21:+44 22:+1 23:-7 24:-5 25:+46 26:-12 | fail: sharpe / tested: t<2.5,sharpe<1,mdd>25%,years<5 |
| trail15 ungated | 285 | 38 % | +4.66 % | 2.3 | +18.2 % | 0.90 | -40 % | 20:+24 21:+29 22:+45 23:+1 24:-8 25:+63 26:-16 | twin |
| trail15 gated | 245 | 40 % | +5.09 % | 2.4 | +14.9 % | 0.83 | -27 % | 20:+28 21:+31 22:+36 23:-4 24:-7 25:+46 26:-18 | fail: sharpe / tested: t<2.5,sharpe<1,mdd>25%,years<5,vs random |
| hi40 ungated | 527 | 41 % | +3.85 % | 3.3 | +28.8 % | 1.26 | -33 % | 20:+28 21:+111 22:+9 23:-10 24:+8 25:+109 26:-13 | twin |
| hi40 gated | 415 | 42 % | +5.98 % | 3.9 | +32.7 % | 1.50 | -24 % | 20:+28 21:+132 22:-2 23:+2 24:+1 25:+118 26:-5 | PASS / CANDIDATE |
| hi90 ungated | 489 | 42 % | +3.35 % | 2.8 | +22.8 % | 1.10 | -32 % | 20:+24 21:+72 22:+13 23:-4 24:-2 25:+99 26:-16 | twin |
| hi90 gated | 391 | 42 % | +4.80 % | 3.3 | +24.1 % | 1.22 | -23 % | 20:+29 21:+80 22:+10 23:+10 24:+1 25:+62 26:-12 | PASS / CANDIDATE |
| vol2 ungated | 490 | 42 % | +5.45 % | 4.0 | +36.2 % | 1.51 | -33 % | 20:+27 21:+71 22:+32 23:+11 24:+9 25:+165 26:-20 | twin |
| vol2 gated | 393 | 45 % | +6.22 % | 4.0 | +33.7 % | 1.54 | -16 % | 20:+27 21:+60 22:+28 23:+7 24:+1 25:+149 26:-6 | fail: sharpe / CANDIDATE |

## V7. Large caps (BLUE, 1 trial)

| arm | trades | hit | avg net | t | CAGR | Sharpe | mDD | years | read |
|---|---|---|---|---|---|---|---|---|---|
| BLUE ungated | 335 | 36 % | +0.59 % | 0.5 | +1.9 % | 0.20 | -35 % | 20:+14 21:+16 22:-11 23:-13 24:-3 25:+18 26:-3 | twin |
| BLUE gated | 288 | 35 % | +0.76 % | 0.6 | +1.5 % | 0.18 | -30 % | 20:+13 21:+16 22:-12 23:-5 24:-3 25:+12 26:-6 | fail: sharpe / tested: t<2.5,sharpe<1,mdd>25%,years<5 |

## V3. Time blocks (descriptive) — gate Sharpe >= ungated in 3 of 5 blocks

| block | ungated CAGR | ungated Sharpe | ungated mDD | gated CAGR | gated Sharpe | gated mDD |
|---|---|---|---|---|---|---|
| 2020-22 | +30.1 % | 1.37 | -15 % | +31.2 % | 1.38 | -15 % |
| 2023-26 | +25.8 % | 1.10 | -30 % | +27.6 % | 1.38 | -17 % |
| 2005-09 | +17.5 % | 1.09 | -18 % | +16.4 % | 1.05 | -18 % |
| 2010-14 | +16.2 % | 1.03 | -19 % | +14.9 % | 0.98 | -19 % |
| 2015-19 | +6.5 % | 0.51 | -25 % | +11.4 % | 0.86 | -18 % |

Rolling 500-day windows (idx, step 20): 56 windows; gated Sharpe >= ungated in 66 %; gated mDD shallower in 82 %; median Sharpe difference +0.06.

Rolling 500-day windows (yahoo, step 20): 158 windows; gated Sharpe >= ungated in 54 %; gated mDD shallower in 87 %; median Sharpe difference +0.00.

## V4. Placebo — 200 circular shifts of the real regime series (same structure, wrong dates)

Real gate: Sharpe 1.38 (percentile 95 of the placebo; placebo median 1.01, 95th 1.37); CAGR +29.2 % (percentile 98; placebo median +17.5 %); mDD -17 % (placebo median -30 %, 5th percentile -36 %; shallower than 100 % of placebos). Sharpe test: PASS; drawdown test: FAIL.

Lagged regime: 10 days late Sharpe 1.07 mDD -22 %; 20 days late Sharpe 1.22 mDD -20 %.

## V5. Execution (descriptive)

| arm | trades | hit | avg net | t | CAGR | Sharpe | mDD | years | read |
|---|---|---|---|---|---|---|---|---|---|
| deployed, entries 1 day late | 506 | 40 % | +2.68 % | 2.1 | +18.3 % | 0.90 | -34 % | 20:+21 21:+70 22:-7 23:+3 24:-5 25:+87 26:-16 | twin |
| gate, entries 1 day late | 399 | 41 % | +2.94 % | 2.6 | +16.4 % | 0.89 | -22 % | 20:+19 21:+89 22:-14 23:+10 24:-7 25:+56 26:-14 |  |
| deployed, costs x 1.5 | 518 | 41 % | +3.21 % | 2.9 | +23.3 % | 1.05 | -32 % | 20:+24 21:+56 22:+3 23:-8 24:+3 25:+134 26:-11 | twin |
| gate, costs x 1.5 | 407 | 43 % | +5.05 % | 3.4 | +25.8 % | 1.24 | -19 % | 20:+28 21:+63 22:-3 23:+3 24:-2 25:+128 26:-5 |  |

## V6. Attribution in the ungated book (descriptive)

| entries made while the regime was | n | hit | avg net | median | t |
|---|---|---|---|---|---|
| on | 371 | 43 % | +4.37 % | -4.40 % | 3.1 |
| off | 147 | 39 % | +1.81 % | -3.08 % | 1.0 |

Deepest drawdown 2026-01-22 -> 2026-06-08: 34 trades entered inside it; 67 % of their losses came from entries made with the regime off (regime off on 41 % of all days).

## Verdict: **PARTIAL: V1 robust, V2 additive, blocks >= 4/5**

Checks: V1 robust = NO; V2 additive = NO; placebo sharpe = yes; blocks >= 4/5 = NO; off-entries worse = yes.
