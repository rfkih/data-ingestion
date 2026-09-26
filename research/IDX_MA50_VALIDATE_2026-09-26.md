# IDX menu 24 — validating os_ma50 — 2026-09-26 — 12 trials, cumulative N = 462

Candidate: deployed trend rule + no new entry while COMPOSITE < MA200 unless COMPOSITE >= MA50 (signal close). `small`, 2020-01-02 -> 2026-09-21.

## The candidate against the deployed rule

| arm | trades | hit | avg net | t | CAGR | Sharpe | mDD | years | read |
|---|---|---|---|---|---|---|---|---|---|
| deployed (equal 1/K, no gate) | 518 | 42 % | +3.65 % | 3.2 | +27.7 % | 1.21 | -30 % | 20:+24 21:+64 22:+7 23:-6 24:+6 25:+148 26:-9 | reference |
| regime_gate (menu 22) | 407 | 44 % | +5.47 % | 3.7 | +29.2 % | 1.38 | -17 % | 20:+29 21:+71 22:+1 23:+4 24:+0 25:+135 26:-4 | reference |
| os_ma50 | 445 | 44 % | +4.53 % | 3.6 | +29.7 % | 1.35 | -18 % | 20:+29 21:+70 22:+1 23:+5 24:+2 25:+120 26:+4 | candidate |

## V1. Regime neighbours (6 trials) — FRAGILE (2/6 pass: Sharpe >= ungated + 0.10 and shallower mDD)

| arm | trades | hit | avg net | t | CAGR | Sharpe | mDD | years | read |
|---|---|---|---|---|---|---|---|---|---|
| short30 (off 26 % of days) | 459 | 44 % | +4.74 % | 3.6 | +31.8 % | 1.41 | -20 % | 20:+24 21:+59 22:+1 23:+11 24:+6 25:+155 26:-1 | PASS / CANDIDATE |
| short75 (off 31 % of days) | 451 | 43 % | +4.30 % | 3.5 | +27.9 % | 1.28 | -20 % | 20:+24 21:+59 22:+1 23:+4 24:+2 25:+130 26:+2 | fail: sharpe / CANDIDATE |
| short100 (off 33 % of days) | 434 | 44 % | +4.14 % | 3.5 | +27.0 % | 1.26 | -21 % | 20:+24 21:+64 22:-5 23:+14 24:+2 25:+102 26:+3 | fail: sharpe / CANDIDATE |
| long150 (off 31 % of days) | 439 | 43 % | +3.86 % | 3.3 | +25.4 % | 1.21 | -17 % | 20:+24 21:+32 22:+7 23:+5 24:+2 25:+123 26:+4 | fail: sharpe / CANDIDATE |
| long250 (off 27 % of days) | 448 | 44 % | +4.66 % | 3.8 | +31.0 % | 1.39 | -24 % | 20:+29 21:+76 22:+6 23:+5 24:+1 25:+120 26:+3 | PASS / CANDIDATE |
| lq45_50_200 (off 39 % of days) | 377 | 42 % | +5.22 % | 3.4 | +27.0 % | 1.31 | -18 % | 20:+30 21:+29 22:-0 23:+8 24:+4 25:+140 26:+3 | fail: sharpe / tested: vs random |

## V2. Entry-rule neighbours, ungated vs gated (5 trials) — ADDITIVE (5/5)

| arm | trades | hit | avg net | t | CAGR | Sharpe | mDD | years | read |
|---|---|---|---|---|---|---|---|---|---|
| trail12 ungated | 401 | 35 % | +2.71 % | 1.9 | +14.0 % | 0.73 | -36 % | 20:+24 21:+37 22:+3 23:-3 24:+4 25:+59 26:-16 | twin |
| trail12 gated | 355 | 38 % | +4.19 % | 2.7 | +20.1 % | 1.01 | -25 % | 20:+28 21:+44 22:+1 23:+6 24:-6 25:+72 26:+2 | PASS / tested: mdd>25%,vs random |
| trail15 ungated | 285 | 38 % | +4.66 % | 2.3 | +18.2 % | 0.90 | -40 % | 20:+24 21:+29 22:+45 23:+1 24:-8 25:+63 26:-16 | twin |
| trail15 gated | 256 | 41 % | +5.57 % | 2.6 | +19.9 % | 1.02 | -30 % | 20:+28 21:+34 22:+36 23:+10 24:-7 25:+56 26:-13 | PASS / tested: mdd>25% |
| hi40 ungated | 527 | 41 % | +3.85 % | 3.3 | +28.8 % | 1.26 | -33 % | 20:+28 21:+111 22:+9 23:-10 24:+8 25:+109 26:-13 | twin |
| hi40 gated | 442 | 44 % | +5.56 % | 4.2 | +37.2 % | 1.61 | -24 % | 20:+27 21:+122 22:-2 23:+2 24:+1 25:+142 26:+13 | PASS / CANDIDATE |
| hi90 ungated | 489 | 42 % | +3.35 % | 2.8 | +22.8 % | 1.10 | -32 % | 20:+24 21:+72 22:+13 23:-4 24:-2 25:+99 26:-16 | twin |
| hi90 gated | 424 | 44 % | +4.39 % | 3.2 | +27.2 % | 1.31 | -22 % | 20:+29 21:+79 22:+10 23:+10 24:+1 25:+69 26:-0 | PASS / CANDIDATE |
| vol2 ungated | 490 | 42 % | +5.45 % | 4.0 | +36.2 % | 1.51 | -33 % | 20:+27 21:+71 22:+32 23:+11 24:+9 25:+165 26:-20 | twin |
| vol2 gated | 420 | 46 % | +6.73 % | 4.4 | +41.5 % | 1.77 | -17 % | 20:+29 21:+74 22:+28 23:+29 24:+1 25:+152 26:+0 | PASS / CANDIDATE |

## V7. Large caps (BLUE, 1 trial)

| arm | trades | hit | avg net | t | CAGR | Sharpe | mDD | years | read |
|---|---|---|---|---|---|---|---|---|---|
| BLUE ungated | 335 | 36 % | +0.59 % | 0.5 | +1.9 % | 0.20 | -35 % | 20:+14 21:+16 22:-11 23:-13 24:-3 25:+18 26:-3 | twin |
| BLUE gated | 314 | 34 % | +0.18 % | 0.2 | -0.3 % | 0.06 | -42 % | 20:+14 21:+16 22:-12 23:-21 24:-4 25:+18 26:-5 | fail: sharpe,mdd / tested: t<2.5,sharpe<1,mdd>25%,years<5,vs random |

## V3. Time blocks (descriptive) — gate Sharpe >= ungated in 5 of 5 blocks

| block | ungated CAGR | ungated Sharpe | ungated mDD | gated CAGR | gated Sharpe | gated mDD |
|---|---|---|---|---|---|---|
| 2020-22 | +30.1 % | 1.37 | -15 % | +31.0 % | 1.38 | -15 % |
| 2023-26 | +25.8 % | 1.10 | -30 % | +28.7 % | 1.33 | -18 % |
| 2005-09 | +17.5 % | 1.09 | -18 % | +18.7 % | 1.16 | -18 % |
| 2010-14 | +16.2 % | 1.03 | -19 % | +16.1 % | 1.04 | -19 % |
| 2015-19 | +6.5 % | 0.51 | -25 % | +9.3 % | 0.70 | -25 % |

Rolling 500-day windows (idx, step 20): 56 windows; gated Sharpe >= ungated in 55 %; gated mDD shallower in 82 %; median Sharpe difference +0.02.

Rolling 500-day windows (yahoo, step 20): 158 windows; gated Sharpe >= ungated in 82 %; gated mDD shallower in 85 %; median Sharpe difference +0.07.

## V4. Placebo — 200 circular shifts of the real regime series (same structure, wrong dates)

Real gate: Sharpe 1.35 (percentile 92 of the placebo; placebo median 1.09, 95th 1.46); CAGR +29.7 % (percentile 93; placebo median +21.6 %); mDD -18 % (placebo median -30 %, 5th percentile -36 %; shallower than 100 % of placebos). Sharpe test: FAIL; drawdown test: FAIL.

Lagged regime: 10 days late Sharpe 1.27 mDD -23 %; 20 days late Sharpe 1.46 mDD -20 %.

## V5. Execution (descriptive)

| arm | trades | hit | avg net | t | CAGR | Sharpe | mDD | years | read |
|---|---|---|---|---|---|---|---|---|---|
| deployed, entries 1 day late | 506 | 40 % | +2.68 % | 2.1 | +18.3 % | 0.90 | -34 % | 20:+21 21:+70 22:-7 23:+3 24:-5 25:+87 26:-16 | twin |
| gate, entries 1 day late | 432 | 41 % | +2.49 % | 2.5 | +17.6 % | 0.93 | -26 % | 20:+21 21:+73 22:-14 23:+9 24:-8 25:+63 26:-3 |  |
| deployed, costs x 1.5 | 518 | 41 % | +3.21 % | 2.9 | +23.3 % | 1.05 | -32 % | 20:+24 21:+56 22:+3 23:-8 24:+3 25:+134 26:-11 | twin |
| gate, costs x 1.5 | 445 | 43 % | +4.10 % | 3.3 | +25.9 % | 1.21 | -20 % | 20:+28 21:+62 22:-3 23:+2 24:-1 25:+112 26:+2 |  |

## V6. Attribution in the ungated book (descriptive)

| entries made while the regime was | n | hit | avg net | median | t |
|---|---|---|---|---|---|
| on | 418 | 44 % | +4.51 % | -3.62 % | 3.5 |
| off | 100 | 35 % | +0.05 % | -6.19 % | 0.0 |

Deepest drawdown 2026-01-22 -> 2026-06-08: 34 trades entered inside it; 67 % of their losses came from entries made with the regime off (regime off on 29 % of all days).

## Verdict: **FRAGILE**

Checks: V1 robust = NO; V2 additive = yes; placebo sharpe = NO; blocks >= 4/5 = yes; off-entries worse = yes.
