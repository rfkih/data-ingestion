# IDX menu 30 — averaging down on the trend book — 2026-09-23 — 12 trials, cumulative N = 578

Operator's questions: "kalau setelah turun 10 % tambah posisi?" then "kalau turun > 7 % lalu naik, itu trigger tambah?".
Incumbent: trend hi60 / > MA200 / vol ≥ 1.5x / trail10, K = 10 (`small` +29.5 %/yr, Sharpe 1.31, mDD −30 %; LIQ +19.1 %, 0.92, −36 %).
Engine: `idx_beyond.run_book_sized` (adds at the next close, weights do not drift), costs and reading rules as menus 6–22. Script `research/idx_avgdown.py`.

**Pre-registered bar:** an arm is BETTER only if Sharpe ≥ reference + 0.15 AND drawdown no deeper. The fair reference for every add arm is the **half-size control** (start at ½ slot, never add) — a full-size reference would confuse "smaller first tranche" with "averaging down".

## A. Naive add on a fall (6 trials)

| arm (`small`) | trades | hit | avg net | t | CAGR | Sharpe | mDD | verdict |
|---|---|---|---|---|---|---|---|---|
| eq 1/K + trail10 (incumbent) | 496 | 42 % | +4.10 % | 3.4 | +29.5 % | 1.31 | −30 % | reference (full size) |
| **half, no add (control)** | 496 | 42 % | +4.10 % | 3.4 | +14.5 % | **1.31** | **−16 %** | control |
| addfall10 + trail10 | 496 | 42 % | +4.10 % | 3.4 | +14.5 % | 1.31 | −16 % | identical to control: **the add never executes** — at −10 % the trail fires the same bar, and the engine checks exit before add |
| addfall10 + trail15 | 275 | 41 % | +7.90 % | 3.6 | +10.9 % | 0.96 | −22 % | tested |
| addfall10 + trail20 | 163 | 37 % | +9.36 % | 2.5 | +8.7 % | 0.70 | −27 % | tested |
| addfall15 + trail20 | 163 | 37 % | +9.06 % | 2.4 | +10.1 % | 0.86 | −25 % | tested |
| pyramid (add on the way UP, Turtle) | 496 | 31 % | +0.68 % | 0.6 | +20.5 % | 1.15 | −24 % | tested (menu 21 arm, for contrast) |

LIQ: control 0.92 / −19 %; addfall10+t15 0.70 / −25 %; +t20 0.52 / −41 %; addfall15+t20 0.57 / −35 %; pyramid 0.90 / −28 %.

Reading: "add at −10 %" is not a rule on top of the incumbent — it replaces the stop with an entry at the same trigger. Widening the stop to let the add happen cuts Sharpe 1.31 → 0.96 → 0.70 and deepens drawdown −16 → −27 %. The trap: **avg net per trade rises** (+4.10 → +9.36 %) while trades collapse 496 → 163 — capital sits in losers waiting to recover, so per-trade statistics improve *because* the portfolio worsens.

## B. Add after a fall AND a turn back up (6 trials, the operator's refinement)

| arm (`small`) | trades | hit | avg net | t | CAGR | Sharpe | mDD | verdict |
|---|---|---|---|---|---|---|---|---|
| half, no add (control) | 496 | 42 % | +4.10 % | 3.4 | +14.5 % | **1.31** | **−16 %** | control |
| **dip7 from ENTRY, 1 up close, trail10** | 496 | **42 %** | **+4.40 %** | **3.7** | +14.2 % | 1.20 | −18 % | tested — highest t in the menu |
| dip7 from entry, 2 up closes | 496 | 38 % | +2.30 % | 2.2 | +13.2 % | 1.03 | −19 % | tested |
| dip7 from PEAK, 1 up close | 496 | 39 % | +2.31 % | 2.2 | +12.4 % | 0.92 | −23 % | tested |
| dip7 from peak, trail12 | 390 | 31 % | +0.85 % | 0.7 | +8.7 % | 0.63 | −25 % | tested |
| dip5 from peak | 496 | 39 % | +2.09 % | 2.0 | +17.7 % | 1.13 | −24 % | tested |
| dip10 from peak, trail15 | 275 | 35 % | +3.61 % | 1.8 | +15.1 % | 1.06 | −26 % | tested |

LIQ: control 0.92 / −19 %; dip7_entry 0.75 / −21 %; dip7_peak 0.66 / −26 %; dip5 0.82 / −28 %; dip10+t15 0.59 / −34 %.

Reading: confirmation beats a falling knife (Sharpe 1.20 vs 0.70) and this arm CAN execute under trail10 (−7 % sits inside the −10 % stop). It still loses to not adding: the added rupiah has an opportunity cost — exposure is capped at 100 %, so an add to a name going against you is a breakout not bought elsewhere. "From peak" is much worse than "from entry" because a 7 % dip from the peak happens in almost every winner, so it keeps adding late in the run, right before the trail fires.

## Verdict

**0 of 12 BETTER.** trail10 stays; no add rule. One lead survives as a *hypothesis*, not a rule: a name that dips 7 % below entry and turns up carries the highest t-stat in the menu (3.7 > incumbent 3.4) with the hit rate intact — worth one pre-registered trial as an **entry filter**, not as sizing. Not run here.

Limits: 2020–26 IDX quotes only (2005–19 survivors file not run); `small` and LIQ; adds at the next close at entry cost; no placebo/neighbour battery (nothing reached the bar to deserve one).
