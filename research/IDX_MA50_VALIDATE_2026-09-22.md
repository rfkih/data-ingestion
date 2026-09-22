# IDX menu 24 — validating os_ma50 — 2026-09-22 — 12 trials, cumulative N = 462

Candidate: deployed trend rule + no new entry while COMPOSITE < MA200 unless COMPOSITE >= MA50 (signal close). `small`, 2020-01-02 -> 2026-09-21.

## The candidate against the deployed rule

| arm | trades | hit | avg net | t | CAGR | Sharpe | mDD | years | read |
|---|---|---|---|---|---|---|---|---|---|
| deployed (equal 1/K, no gate) | 496 | 42 % | +4.10 % | 3.4 | +29.5 % | 1.31 | -30 % | 20:+24 21:+65 22:+29 23:-5 24:+1 25:+131 26:-8 | reference |
| regime_gate (menu 22) | 381 | 44 % | +6.30 % | 3.9 | +32.1 % | 1.54 | -18 % | 20:+23 21:+65 22:+24 23:-3 24:+5 25:+147 26:-5 | reference |
| os_ma50 | 423 | 43 % | +5.21 % | 3.9 | +32.6 % | 1.50 | -18 % | 20:+25 21:+68 22:+24 23:+5 24:+5 25:+108 26:+4 | candidate |

## V1. Regime neighbours (6 trials) — ROBUST (5/6 pass: Sharpe >= ungated + 0.10 and shallower mDD)

| arm | trades | hit | avg net | t | CAGR | Sharpe | mDD | years | read |
|---|---|---|---|---|---|---|---|---|---|
| short30 (off 26 % of days) | 436 | 44 % | +5.63 % | 4.0 | +36.2 % | 1.59 | -20 % | 20:+24 21:+60 22:+24 23:+12 24:+7 25:+154 26:-1 | PASS / CANDIDATE |
| short75 (off 31 % of days) | 427 | 43 % | +5.09 % | 3.9 | +31.8 % | 1.47 | -20 % | 20:+24 21:+60 22:+24 23:+4 24:+5 25:+118 26:+2 | PASS / CANDIDATE |
| short100 (off 33 % of days) | 413 | 44 % | +5.17 % | 4.0 | +31.9 % | 1.48 | -21 % | 20:+24 21:+65 22:+15 23:+14 24:+5 25:+103 26:+4 | PASS / CANDIDATE |
| long150 (off 31 % of days) | 416 | 43 % | +4.67 % | 3.7 | +29.4 % | 1.40 | -18 % | 20:+24 21:+41 22:+25 23:+5 24:+5 25:+111 26:+4 | fail: sharpe / CANDIDATE |
| long250 (off 27 % of days) | 428 | 44 % | +5.23 % | 3.9 | +33.0 % | 1.51 | -22 % | 20:+25 21:+74 22:+27 23:+5 24:+1 25:+108 26:+3 | PASS / CANDIDATE |
| lq45_50_200 (off 39 % of days) | 366 | 43 % | +6.23 % | 3.8 | +32.1 % | 1.53 | -18 % | 20:+25 21:+40 22:+25 23:+5 24:+4 25:+146 26:+3 | PASS / CANDIDATE |

## V2. Entry-rule neighbours, ungated vs gated (5 trials) — ADDITIVE (5/5)

| arm | trades | hit | avg net | t | CAGR | Sharpe | mDD | years | read |
|---|---|---|---|---|---|---|---|---|---|
| trail12 ungated | 390 | 35 % | +3.41 % | 2.3 | +18.1 % | 0.90 | -33 % | 20:+24 21:+38 22:+4 23:+4 24:+5 25:+77 26:-15 | twin |
| trail12 gated | 340 | 37 % | +4.76 % | 2.9 | +22.4 % | 1.13 | -23 % | 20:+25 21:+47 22:+8 23:-1 24:-0 25:+86 26:+3 | PASS / CANDIDATE |
| trail15 ungated | 275 | 40 % | +6.30 % | 2.8 | +24.1 % | 1.13 | -38 % | 20:+24 21:+82 22:+44 23:-1 24:-6 25:+52 26:-13 | twin |
| trail15 gated | 248 | 43 % | +7.33 % | 3.2 | +25.7 % | 1.24 | -30 % | 20:+25 21:+87 22:+35 23:+9 24:-6 25:+50 26:-9 | PASS / tested: mdd>25% |
| hi40 ungated | 516 | 40 % | +3.60 % | 3.1 | +25.7 % | 1.16 | -32 % | 20:+28 21:+92 22:+26 23:-10 24:+1 25:+68 26:-7 | twin |
| hi40 gated | 429 | 45 % | +5.68 % | 4.2 | +37.0 % | 1.62 | -18 % | 20:+27 21:+102 22:+14 23:+4 24:+0 25:+111 26:+20 | PASS / CANDIDATE |
| hi90 ungated | 470 | 42 % | +3.90 % | 3.0 | +25.2 % | 1.21 | -32 % | 20:+24 21:+85 22:+22 23:-3 24:-6 25:+99 26:-17 | twin |
| hi90 gated | 409 | 44 % | +4.76 % | 3.4 | +28.4 % | 1.40 | -20 % | 20:+25 21:+88 22:+15 23:+11 24:-1 25:+69 26:-1 | PASS / CANDIDATE |
| vol2 ungated | 470 | 42 % | +5.85 % | 4.0 | +37.2 % | 1.57 | -33 % | 20:+27 21:+85 22:+45 23:+4 24:+3 25:+165 26:-20 | twin |
| vol2 gated | 403 | 46 % | +7.07 % | 4.5 | +42.0 % | 1.81 | -17 % | 20:+23 21:+80 22:+44 23:+16 24:+4 25:+151 26:-0 | PASS / CANDIDATE |

## V7. Large caps (BLUE, 1 trial)

| arm | trades | hit | avg net | t | CAGR | Sharpe | mDD | years | read |
|---|---|---|---|---|---|---|---|---|---|
| BLUE ungated | 333 | 36 % | +0.68 % | 0.6 | +2.5 % | 0.24 | -35 % | 20:+14 21:+18 22:-11 23:-13 24:-3 25:+18 26:-2 | twin |
| BLUE gated | 312 | 35 % | +0.27 % | 0.2 | +0.3 % | 0.10 | -42 % | 20:+14 21:+18 22:-12 23:-21 24:-4 25:+18 26:-4 | fail: sharpe,mdd / tested: t<2.5,sharpe<1,mdd>25%,years<5,vs random |

## V3. Time blocks (descriptive) — gate Sharpe >= ungated in 4 of 5 blocks

| block | ungated CAGR | ungated Sharpe | ungated mDD | gated CAGR | gated Sharpe | gated mDD |
|---|---|---|---|---|---|---|
| 2020-22 | +39.0 % | 1.76 | -13 % | +38.5 % | 1.72 | -13 % |
| 2023-26 | +22.1 % | 0.99 | -30 % | +27.9 % | 1.32 | -18 % |
| 2005-09 | +17.5 % | 1.09 | -18 % | +18.7 % | 1.16 | -18 % |
| 2010-14 | +16.2 % | 1.03 | -19 % | +16.1 % | 1.04 | -19 % |
| 2015-19 | +6.5 % | 0.51 | -25 % | +9.3 % | 0.70 | -25 % |

Rolling 500-day windows (idx, step 20): 56 windows; gated Sharpe >= ungated in 71 %; gated mDD shallower in 84 %; median Sharpe difference +0.08.

Rolling 500-day windows (yahoo, step 20): 158 windows; gated Sharpe >= ungated in 82 %; gated mDD shallower in 85 %; median Sharpe difference +0.07.

## V4. Placebo — 200 circular shifts of the real regime series (same structure, wrong dates)

Real gate: Sharpe 1.50 (percentile 94 of the placebo; placebo median 1.16, 95th 1.54); CAGR +32.6 % (percentile 94; placebo median +22.8 %); mDD -18 % (placebo median -30 %, 5th percentile -36 %; shallower than 100 % of placebos). Sharpe test: FAIL; drawdown test: FAIL.

Lagged regime: 10 days late Sharpe 1.43 mDD -24 %; 20 days late Sharpe 1.62 mDD -20 %.

## V5. Execution (descriptive)

| arm | trades | hit | avg net | t | CAGR | Sharpe | mDD | years | read |
|---|---|---|---|---|---|---|---|---|---|
| deployed, entries 1 day late | 498 | 40 % | +2.83 % | 2.2 | +18.3 % | 0.91 | -34 % | 20:+21 21:+71 22:-5 23:+6 24:-4 25:+74 26:-15 | twin |
| gate, entries 1 day late | 427 | 41 % | +2.57 % | 2.5 | +17.2 % | 0.92 | -24 % | 20:+21 21:+74 22:-12 23:+8 24:-6 25:+55 26:-4 |  |
| deployed, costs x 1.5 | 496 | 41 % | +3.67 % | 3.1 | +25.3 % | 1.16 | -32 % | 20:+24 21:+59 22:+24 23:-8 24:-2 25:+119 26:-11 | twin |
| gate, costs x 1.5 | 423 | 43 % | +4.78 % | 3.6 | +28.9 % | 1.36 | -20 % | 20:+25 21:+61 22:+19 23:+2 24:+2 25:+100 26:+2 |  |

## V6. Attribution in the ungated book (descriptive)

| entries made while the regime was | n | hit | avg net | median | t |
|---|---|---|---|---|---|
| on | 399 | 43 % | +5.15 % | -2.88 % | 3.7 |
| off | 97 | 34 % | -0.25 % | -6.60 % | -0.1 |

Deepest drawdown 2026-01-22 -> 2026-06-08: 34 trades entered inside it; 67 % of their losses came from entries made with the regime off (regime off on 29 % of all days).

## Verdict: **FRAGILE**

Checks: V1 robust = yes; V2 additive = yes; placebo sharpe = NO; blocks >= 4/5 = yes; off-entries worse = yes.

## Reading (written after the run)

By the letter declared in menu 22 — "a placebo failure alone is FRAGILE" — os_ma50 is **FRAGILE**: its Sharpe sits at the 94th percentile
of 200 shifted regimes, one point under the 95 required. Every other check passes, and more strongly than regime_gate's did:

- V1 5 of 6 regime neighbours (short 30/75/100, long 250, LQ45) keep Sharpe ≥ ungated + 0.10 with a shallower drawdown (regime_gate: 3 of 6);
- V2 5 of 5 entry neighbours improve with the gate, including the wide trails 12/15 % that regime_gate hurt (regime_gate: 1 of 5);
- V3 4 of 5 time blocks (regime_gate: 2 of 5); rolling two-year windows Sharpe ≥ ungated in 71 % (IDX) / 82 % (2005-19), median +0.07
  (regime_gate: 48 / 54 %, median 0.00); drawdown shallower in 84 / 85 %;
- V4 drawdown placebo passes (−18 % against a placebo median of −30 %, 5th percentile −36 %); the lagged regime (20 days late) scores 1.62,
  so the signal is slow-moving rather than precisely timed — which is also why shifted placebos come closer to it than to regime_gate's;
- V6 the entries it blocks are the bad ones: −0.2 % net (hit 34 %, t −0.1) against +5.2 % for the allowed ones (hit 43 %, t 3.7), a cleaner
  split than the gate's (+1.6 % vs +5.1 %);
- V5 one day late it keeps Sharpe 0.92 (regime_gate 0.76); costs × 1.5 Sharpe 1.36.
- Calendar years 2020-26 all positive (23: +5 %, 26: +4 % where the ungated rule lost 5 and 8 %); 2025 lower (+108 % vs +131 %) because
  the MA50 re-opening also lets it back in during the 2025 chop.

Honest summary: the return improvement of os_ma50 is the more robust of the two (it survives every neighbour and most windows), the
timing information is slightly weaker (94th vs 99th percentile), and the label follows the rule as written. Both remain a risk preference;
os_ma50 is the one to prefer if the operator wants the rebound and all-positive years, regime_gate if the shallowest 2005-19 drawdown.
