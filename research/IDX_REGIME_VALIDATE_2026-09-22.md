# IDX menu 22 — validating regime_gate — 2026-09-22 — 12 trials, cumulative N = 445

Candidate: deployed trend rule + no new entry while COMPOSITE < MA200 (signal close). `small`, 2020-01-02 -> 2026-09-21.

## The candidate against the deployed rule

| arm | trades | hit | avg net | t | CAGR | Sharpe | mDD | years | read |
|---|---|---|---|---|---|---|---|---|---|
| deployed (equal 1/K, no gate) | 496 | 42 % | +4.10 % | 3.4 | +29.5 % | 1.31 | -30 % | 20:+24 21:+65 22:+29 23:-5 24:+1 25:+131 26:-8 | reference |
| regime_gate | 381 | 44 % | +6.30 % | 3.9 | +32.1 % | 1.54 | -18 % | 20:+23 21:+65 22:+24 23:-3 24:+5 25:+147 26:-5 | candidate |

## V1. Regime neighbours (6 trials) — FRAGILE (3/6 pass: Sharpe >= ungated + 0.10 and shallower mDD)

| arm | trades | hit | avg net | t | CAGR | Sharpe | mDD | years | read |
|---|---|---|---|---|---|---|---|---|---|
| ma100 (off 37 % of days) | 366 | 43 % | +4.76 % | 3.5 | +25.3 % | 1.30 | -20 % | 20:+24 21:+22 22:+17 23:+14 24:-1 25:+105 26:+5 | fail: sharpe / CANDIDATE |
| ma150 (off 33 % of days) | 367 | 45 % | +5.31 % | 3.9 | +28.0 % | 1.41 | -19 % | 20:+24 21:+41 22:+25 23:-2 24:+6 25:+129 26:-5 | fail: sharpe / tested: vs random |
| ma250 (off 28 % of days) | 384 | 44 % | +5.36 % | 3.8 | +28.4 % | 1.42 | -21 % | 20:+24 21:+65 22:+27 23:-1 24:+1 25:+106 26:-7 | PASS / CANDIDATE |
| ma200_buf (off 30 % of days) | 367 | 44 % | +5.91 % | 3.7 | +28.6 % | 1.42 | -24 % | 20:+24 21:+65 22:+31 23:-12 24:+4 25:+121 26:-6 | PASS / CANDIDATE |
| lq45_ma200 (off 46 % of days) | 292 | 41 % | +5.94 % | 3.4 | +22.7 % | 1.26 | -14 % | 20:+19 21:+31 22:+34 23:+0 24:+2 25:+81 26:-4 | fail: sharpe / CANDIDATE |
| breadth50 (off 55 % of days) | 329 | 44 % | +7.10 % | 3.9 | +30.6 % | 1.51 | -29 % | 20:+24 21:+60 22:+41 23:+7 24:-3 25:+145 26:-20 | PASS / tested: mdd>25% |

## V2. Entry-rule neighbours, ungated vs gated (5 trials) — NOT ADDITIVE (1/5)

| arm | trades | hit | avg net | t | CAGR | Sharpe | mDD | years | read |
|---|---|---|---|---|---|---|---|---|---|
| trail12 ungated | 390 | 35 % | +3.41 % | 2.3 | +18.1 % | 0.90 | -33 % | 20:+24 21:+38 22:+4 23:+4 24:+5 25:+77 26:-15 | twin |
| trail12 gated | 317 | 35 % | +4.45 % | 2.6 | +16.1 % | 0.91 | -26 % | 20:+23 21:+47 22:+8 23:-5 24:-0 25:+48 26:-4 | fail: sharpe / tested: sharpe<1,mdd>25%,years<5 |
| trail15 ungated | 275 | 40 % | +6.30 % | 2.8 | +24.1 % | 1.13 | -38 % | 20:+24 21:+82 22:+44 23:-1 24:-6 25:+52 26:-13 | twin |
| trail15 gated | 235 | 41 % | +6.32 % | 2.7 | +17.8 % | 0.98 | -28 % | 20:+23 21:+82 22:+35 23:-7 24:-5 25:+32 26:-18 | fail: sharpe / tested: sharpe<1,mdd>25%,years<5 |
| hi40 ungated | 516 | 40 % | +3.60 % | 3.1 | +25.7 % | 1.16 | -32 % | 20:+28 21:+92 22:+26 23:-10 24:+1 25:+68 26:-7 | twin |
| hi40 gated | 399 | 43 % | +6.08 % | 3.9 | +31.9 % | 1.50 | -19 % | 20:+28 21:+109 22:+14 23:-2 24:+0 25:+108 26:-4 | PASS / CANDIDATE |
| hi90 ungated | 470 | 42 % | +3.90 % | 3.0 | +25.2 % | 1.21 | -32 % | 20:+24 21:+85 22:+22 23:-3 24:-6 25:+99 26:-17 | twin |
| hi90 gated | 377 | 43 % | +4.85 % | 3.2 | +23.1 % | 1.21 | -21 % | 20:+24 21:+84 22:+15 23:+4 24:-1 25:+61 26:-12 | fail: sharpe / tested: vs random |
| vol2 ungated | 470 | 42 % | +5.85 % | 4.0 | +37.2 % | 1.57 | -33 % | 20:+27 21:+85 22:+45 23:+4 24:+3 25:+165 26:-20 | twin |
| vol2 gated | 373 | 46 % | +6.84 % | 4.2 | +35.6 % | 1.65 | -16 % | 20:+18 21:+68 22:+44 23:+3 24:+4 25:+149 26:-6 | fail: sharpe / CANDIDATE |

## V7. Large caps (BLUE, 1 trial)

| arm | trades | hit | avg net | t | CAGR | Sharpe | mDD | years | read |
|---|---|---|---|---|---|---|---|---|---|
| BLUE ungated | 333 | 36 % | +0.68 % | 0.6 | +2.5 % | 0.24 | -35 % | 20:+14 21:+18 22:-11 23:-13 24:-3 25:+18 26:-2 | twin |
| BLUE gated | 287 | 35 % | +0.84 % | 0.7 | +1.9 % | 0.20 | -30 % | 20:+13 21:+18 22:-12 23:-5 24:-3 25:+12 26:-6 | fail: sharpe / tested: t<2.5,sharpe<1,mdd>25%,years<5,vs random |

## V3. Time blocks (descriptive) — gate Sharpe >= ungated in 2 of 5 blocks

| block | ungated CAGR | ungated Sharpe | ungated mDD | gated CAGR | gated Sharpe | gated mDD |
|---|---|---|---|---|---|---|
| 2020-22 | +39.0 % | 1.76 | -13 % | +36.7 % | 1.65 | -13 % |
| 2023-26 | +22.1 % | 0.99 | -30 % | +28.3 % | 1.44 | -17 % |
| 2005-09 | +17.5 % | 1.09 | -18 % | +16.4 % | 1.05 | -18 % |
| 2010-14 | +16.2 % | 1.03 | -19 % | +14.9 % | 0.98 | -19 % |
| 2015-19 | +6.5 % | 0.51 | -25 % | +11.4 % | 0.86 | -18 % |

Rolling 500-day windows (idx, step 20): 56 windows; gated Sharpe >= ungated in 48 %; gated mDD shallower in 84 %; median Sharpe difference -0.01.

Rolling 500-day windows (yahoo, step 20): 158 windows; gated Sharpe >= ungated in 54 %; gated mDD shallower in 87 %; median Sharpe difference +0.00.

## V4. Placebo — 200 circular shifts of the real regime series (same structure, wrong dates)

Real gate: Sharpe 1.54 (percentile 99 of the placebo; placebo median 1.14, 95th 1.46); CAGR +32.1 % (percentile 100; placebo median +22.3 %); mDD -18 % (placebo median -30 %, 5th percentile -35 %; shallower than 99 % of placebos). Sharpe test: PASS; drawdown test: FAIL.

Lagged regime: 10 days late Sharpe 1.33 mDD -23 %; 20 days late Sharpe 1.42 mDD -21 %.

## V5. Execution (descriptive)

| arm | trades | hit | avg net | t | CAGR | Sharpe | mDD | years | read |
|---|---|---|---|---|---|---|---|---|---|
| deployed, entries 1 day late | 498 | 40 % | +2.83 % | 2.2 | +18.3 % | 0.91 | -34 % | 20:+21 21:+71 22:-5 23:+6 24:-4 25:+74 26:-15 | twin |
| gate, entries 1 day late | 393 | 40 % | +2.55 % | 2.2 | +13.2 % | 0.76 | -22 % | 20:+16 21:+79 22:-12 23:+9 24:-7 25:+39 26:-14 |  |
| deployed, costs x 1.5 | 496 | 41 % | +3.67 % | 3.1 | +25.3 % | 1.16 | -32 % | 20:+24 21:+59 22:+24 23:-8 24:-2 25:+119 26:-11 | twin |
| gate, costs x 1.5 | 381 | 44 % | +5.87 % | 3.7 | +28.8 % | 1.41 | -20 % | 20:+23 21:+58 22:+19 23:-4 24:+2 25:+140 26:-6 |  |

## V6. Attribution in the ungated book (descriptive)

| entries made while the regime was | n | hit | avg net | median | t |
|---|---|---|---|---|---|
| on | 352 | 43 % | +5.10 % | -4.02 % | 3.4 |
| off | 144 | 38 % | +1.65 % | -3.19 % | 0.9 |

Deepest drawdown 2026-01-22 -> 2026-06-08: 34 trades entered inside it; 67 % of their losses came from entries made with the regime off (regime off on 29 % of all days).

## Verdict: **PARTIAL: V1 robust, V2 additive, blocks >= 4/5**

Checks: V1 robust = NO; V2 additive = NO; placebo sharpe = yes; blocks >= 4/5 = NO; off-entries worse = yes.

## Reading (written after the run)

1. **What is validated: the gate is a drawdown reducer, and the timing is real.** Every regime definition (MA100/150/250, buffered MA200,
   LQ45, breadth) cuts the worst drawdown from −30 % to −14…−24 % (breadth −29 %); in rolling two-year windows the gated book's drawdown is
   shallower in 84 % (IDX) and 87 % (2005-19) of windows; no time block is deeper. Against 200 placebo regimes with the same on/off structure
   on the wrong dates, the real gate's Sharpe (1.54) sits at the 99th percentile (placebo median 1.14, 95th 1.46) and its drawdown (−18 %) is
   shallower than every placebo's median (−30 %) — the MA200 dates carry information; "trading less" alone does not do this. The mechanism is
   visible in the ungated book: entries made with the regime off earn +1.6 % net (hit 38 %, t 0.9), entries with it on +5.1 % (hit 43 %,
   t 3.4), and 67 % of the losses inside the 2026 drawdown came from regime-off entries.
2. **What is not validated: the return and Sharpe gain.** The gated Sharpe beats the ungated in only 48 % (IDX) / 54 % (2005-19) of rolling
   windows, median difference 0.00; in the five time blocks it is ahead in the two bear-heavy ones (2023-26: 0.99 → 1.44; 2015-19: 0.51 → 0.86)
   and behind in the three bull ones (2020-22, 2005-09, 2010-14, by 0.04-0.11). Only 3 of 6 regime neighbours and 1 of 5 entry neighbours clear
   the +0.10 Sharpe bar; with a wider trailing stop (12/15 %) the gate lowers Sharpe, which says its return effect is specific to the 10 % trail:
   under a tight trail the regime-off breakouts get whipsawed, under a wide one they survive. The +32 %/yr headline is the bear-heavy 2023-26
   window flattering the gate; over a full cycle the fair expectation is the same return as the ungated rule, a little less in bull years and
   more in bear years, with the worst drawdown around −18…−24 % instead of −30 %.
3. **Execution matters more than the gate.** Entries one day later (close t+2 instead of t+1) take the ungated rule from Sharpe 1.31 to 0.91
   and the gated one from 1.54 to 0.76 (CAGR 32 → 13 %): the first session after a breakout carries much of the trade. The desk's practice —
   ticket at night, fill at the next open — is earlier than the backtest's close t+1, so it is on the safe side, but a ticket left for a day
   is not. Costs × 1.5 leave the gate intact (Sharpe 1.41, CAGR 28.8 %).
4. **Large caps: nothing to gate** (BLUE breakouts Sharpe 0.24 ungated, 0.20 gated) — the LIQ result of menu 21 is BLUE diluting `small`.

**Verdict: PARTIAL.** Adopt it, if at all, as a risk rule (the drawdown clause of the money rule, which the deployed sleeve fails), not as a
return improvement. Reasonable book option: `regime_gate` on `paper_trend` now; `trend_live` at the operator's discretion, two-key.
