# IDX menu 25 — robustness scorecard of every researched strategy — 2026-09-22 — 17 new trials, cumulative N = 479

Battery: N neighbours · P placebo · T time blocks · C costs x 1.5 · D delay · M multiplicity (DSR). Verdicts: ROBUST (N, P, T pass), PARTIAL (one fails), FRAGILE (P fails or two fail), UNTESTABLE (too few episodes), CLOSED (falsified in its own menu).

## Scorecard

| strategy | evidence | N neighbours | P placebo | T time | C / D costs, delay | M | verdict |
|---|---|---|---|---|---|---|---|
| Value strict composite, annual May (live) | 2020-26, 7 rebalances, ~12 names | 6/6 pass | Sharpe at pct 100 of 200 random strict-pool books (median 0.40) | beats strict pool in 2/2 halves | x1.5 costs CAGR 21.6 % (rule 21.8); delay: none (09-13) | DSR 0.327 | **ROBUST** |
| Asymmetric RSI30 entry / MA200-cross exit on the strict list | 2021-26, 4 calendars, monthly | 2/4 pass its bar | Sharpe advantage at pct 88 of 100 shifted signals | asym > none in 2/2 halves | 1 session late -1.3 pt, 5 late -2.7 (09-13) | - | **FRAGILE** |
| Trend hi60/MA200/vol1.5x/trail10, K=10, small (paper_trend, trend_live) | 2020-26 IDX quotes (496 trades) + 2005-19 Yahoo survivors (612) | 5/7 neighbours (#23); exits 0/30 better (#44-45) = settled | random entries + trail10: Sharpe 0.70 vs 1.31 (#23); 0.71 vs 0.89 in 2005-19 (#46) | years +5/7 (2020-26), 12/15 (2005-19); base rate 13 %/yr, 2020-26 = best block in 22 yrs (#46) | costs quoted spread; 1-day-late entry: Sharpe 1.31 -> 0.91 (#63 V5) | DSR 0.64 @428 | **ROBUST (rule) / FRAGILE to execution delay** |
| regime_gate: trend + no entry while IHSG < MA200 | same as trend; #62, #63 (12 trials + 200 placebos) | 3/6 regime, 1/5 entry neighbours | Sharpe at 99th pct of 200 shifted regimes; mDD -18 vs placebo median -30 | Sharpe >= ungated in 2/5 blocks; rolling 48/54 %; mDD shallower 84/87 % | costs x1.5 ok (1.41); 1-day-late 0.76 | DSR 0.82 @433 | **PARTIAL (drawdown rule validated, return gain not)** |
| os_ma50: trend + entry allowed when IHSG >= MA200 or >= MA50 | same; #64, #65 (12 trials + 200 placebos) | 5/6 regime, 5/5 entry neighbours | Sharpe at 94th pct (bar 95); mDD passes; lag20 1.62 | 4/5 blocks; rolling 71/82 %; all 7 calendar years positive | costs x1.5 1.36; 1-day-late 0.92 | DSR ~0.8 @450 | **FRAGILE by the letter (placebo 94) / strongest neighbourhood of any rule** |
| Crash switch: strict -> cheapest E/P fifth after -20 %, back above MA200 | 2 episodes (2020, 2025-26), 4 calendars (IDX_CRASH_SWITCH 09-14) | loose gate +1 pt; price-only version fails (47 % mDD) | not possible (n = 2) | 1.5 episodes | - | - | **UNTESTABLE (n = 2 episodes)** |
| Take-profit +100 % on the value book | 10 doubling events (IDX_SELL_RULES 09-13) | +50 % fails 3/4 | not possible (n = 10) | - | - | - | **UNTESTABLE (n = 10 events)** |
| Index regime filter on the value book (all to cash under MA200) | 2008-26 basket + 2021-26 book (IDX_TREND_OVERLAY 09-13) | MA100 halves return on the real book; 200/250 alike | - | 2008: 0 vs -36; 2020: -13 vs -47; costs 0-49 % of return in calm years | 5 sessions late ~1 pt | - | **ROBUST as a damper, costs return** |
| Cash buffer 30 % / 50 % on stress | 2008-26 basket + 2021-26 book (IDX_CASH_BUFFER 09-14) | 4 detectors alike | - | 2008/2020 -28..-37 | - | - | **ROBUST as a damper, fails return floor by 2 pts** |
| Combined book value + trend | 2021-26 daily, corr +0.37 | 4/5 weights pass the money rule | - | 50/50 passes in 2/2 halves | inherits sleeves | - | **ROBUST** |
| Allocation: rupiah dual momentum (IHSG / S&P / cash) | 2006-26 monthly | 3/3 lookbacks beat the index | - | gem >= IHSG Sharpe in 3/3 blocks | 0.30 % switch | - | **ROBUST** |
| Allocation: equal weight IHSG / S&P / gold | 2006-26 monthly | no-gold version passes | - | EW3 >= IHSG Sharpe in 3/3 blocks | - | - | **ROBUST** |

CLOSED (falsified in their own menus, no battery needed): swing 2-5 days (46 trials) (#14, #15); foreign-flow / accumulation (6) (#16); bandarmologi broker flow (19) (#18, #19); sleepers 5d-2y (8) (#25, #26); small-cap PIT growth rules (4 costed) (#27-29); doublers / multibagger sleeve (IDX_DOUBLER_SLEEVE 09-13); ARA hunter (24) + ML ARA (3) (#56, #59); ML loser filter on trend (2) (#58); support / resistance (4) (#60); per-name sizing, vol target, pyramid (10); sector rotation (3) (#61); quality / QARP / factor book / top10 / top3 / sector-relative / hold winners / mom+growth (IDX_QUALITY, IDX_FACTOR_BOOK, IDX_TOP10, IDX_TOP3_UPSIDE, IDX_SECTOR_RELATIVE, IDX_HOLD_WINNERS, IDX_MOM_GROWTH 09-12..14).

## S1. Value strict composite (deployed `live`)

Rule: CAGR +21.8 %, Sharpe 1.06, mDD 23 %, DSR 0.327. Strict-pool equal weight: CAGR +9.8 %, Sharpe 0.56, mDD 34 %.

| neighbour | names | CAGR | Sharpe | mDD | read |
|---|---|---|---|---|---|
| top_quarter | 14 | +27.3 % | 1.20 | 27 % | PASS |
| top_sixth | 10 | +18.8 % | 0.93 | 23 % | PASS |
| top_eighth | 10 | +18.5 % | 0.91 | 22 % | PASS |
| ep_only | 12 | +28.1 % | 1.08 | 32 % | PASS |
| ep_bp | 12 | +26.5 % | 1.06 | 30 % | PASS |
| loose_gate | 17 | +20.5 % | 1.00 | 23 % | PASS |

Placebo: 200 random books of the rule's size from the strict pool at each rebalance — median Sharpe 0.40, CAGR +8.2 %, mDD 40 %; 95th percentile Sharpe 0.79, CAGR +19.5 %. The rule sits at percentile 100 (Sharpe), 99 (CAGR); its drawdown is shallower than 100 % of the random books. PASS.

- 2020-23: rule CAGR +31.3 %, Sharpe 1.38, mDD 18 %; strict pool CAGR +17.5 %, Sharpe 1.03, mDD 15 %.
- 2023-26: rule CAGR +14.0 %, Sharpe 0.75, mDD 23 %; strict pool CAGR +3.5 %, Sharpe 0.20, mDD 34 %.
- costs x 1.5: CAGR +21.6 %, Sharpe 1.05, mDD 23 %.

## S5. Asymmetric rule (RSI entry, MA cross exit) on the strict list

| calendar | none | asym_rsi |
|---|---|---|
| 5 | CAGR +17.6 %, Sharpe 0.98, mDD 23 % | CAGR +16.2 %, Sharpe 1.14, mDD 16 % |
| 2 | CAGR +25.7 %, Sharpe 1.34, mDD 21 % | CAGR +18.2 %, Sharpe 1.20, mDD 17 % |
| 8 | CAGR +16.4 %, Sharpe 0.94, mDD 19 % | CAGR +15.7 %, Sharpe 1.09, mDD 16 % |
| 11 | CAGR +12.7 %, Sharpe 0.80, mDD 22 % | CAGR +12.7 %, Sharpe 0.99, mDD 14 % |

Its own bar: Sharpe > none with CAGR >= 90 % in 3/4 calendars, worst mDD 17 vs 23 -> PASS.

| neighbour | wins | worst mDD | none worst | avg CAGR | avg Sharpe | read |
|---|---|---|---|---|---|---|
| rsi25 | 0/4 | 17 % | 23 % | +12.8 % | 0.98 | fail |
| rsi35 | 3/4 | 19 % | 23 % | +16.1 % | 1.05 | PASS |
| sma150 | 0/4 | 16 % | 23 % | +13.5 % | 0.98 | fail |
| sma250 | 3/4 | 18 % | 23 % | +15.8 % | 1.11 | PASS |

Placebo (May calendar): real Sharpe advantage over none +0.16; 100 shifted signals median -0.04, 95th +0.21; real at percentile 88 -> FAIL.

- early: none CAGR +14.8 %, Sharpe 0.83, mDD 21 %; asym CAGR +16.3 %, Sharpe 1.10, mDD 16 %.
- late: none CAGR +21.3 %, Sharpe 1.18, mDD 23 %; asym CAGR +16.0 %, Sharpe 1.20, mDD 13 %.

## S7. Combined book value + trend

| weights value/trend | CAGR | Sharpe | mDD | money rule |
|---|---|---|---|---|
| 30/70 | +26.2 % | 1.34 | -25 % | fail |
| 40/60 | +24.9 % | 1.35 | -23 % | pass |
| 50/50 | +23.6 % | 1.33 | -22 % | pass |
| 60/40 | +22.2 % | 1.29 | -22 % | pass |
| 70/30 | +20.7 % | 1.23 | -22 % | pass |

- 50/50 2021-23: CAGR +18.2 %, Sharpe 1.11, mDD -18 %.

- 50/50 2024-26: CAGR +30.0 %, Sharpe 1.57, mDD -22 %.

## S8. Allocation layer

| arm | CAGR | Sharpe | mDD | beats index |
|---|---|---|---|---|
| gem_6m | +14.1 % | 1.19 | -16 % | yes |
| gem_9m | +12.8 % | 1.07 | -19 % | yes |
| gem_12m | +11.2 % | 0.93 | -19 % | yes |
| EW3 | +12.6 % | 1.14 | -28 % | - |
| EW2_no_gold | +11.2 % | 0.90 | -44 % | - |
| IHSG | +8.4 % | 0.53 | -55 % | - |

- 2006-12: gem_12m CAGR +17.7 % Sharpe 1.08 mDD -16 %; EW3 CAGR +14.3 % Sharpe 1.12 mDD -28 %; IHSG CAGR +19.9 % Sharpe 0.87 mDD -55 %

- 2013-19: gem_12m CAGR +9.1 % Sharpe 1.20 mDD -12 %; EW3 CAGR +9.9 % Sharpe 0.95 mDD -12 %; IHSG CAGR +5.5 % Sharpe 0.53 mDD -23 %

- 2020-26: gem_12m CAGR +6.9 % Sharpe 0.67 mDD -19 %; EW3 CAGR +13.9 % Sharpe 1.39 mDD -12 %; IHSG CAGR +0.6 % Sharpe 0.12 mDD -35 %


## Reading (written after the run)

1. **Two engines and one portfolio rule are robust; everything else is a damper, a lottery, or closed.**
   - The **value strict composite** survives every check the data allows: all six neighbours (top quarter to top eighth, E/P alone, E/P + B/P,
     loose gate) stay in the same neighbourhood; 200 random books of the same size from the same strict pool have a median Sharpe of 0.40 and a
     95th percentile of 0.79 against the rule's 1.06 — cheapness ranking inside the quality gate is the whole edge, not the gate; it beats the
     pool in both halves; costs × 1.5 take 0.2 points. What the battery cannot do is look before 2020 (no point-in-time fundamentals), so the
     evidence is seven rebalances in one decade; and the DSR at 479 trials is 0.33 — the multiplicity tax of this many menus is now the biggest
     mark against it, and the placebo, not the DSR, is the reason to trust it.
   - The **trend rule** is robust as a rule (neighbours, exits, random reference, two decades) and fragile only to execution: one session late
     halves its Sharpe. Its regime overlays split: `regime_gate` validated as a drawdown rule, `os_ma50` the strongest neighbourhood in the
     project but a hair under the placebo bar. Either one turns the sleeve into a money-rule pass; the choice between them is a risk preference.
   - The **combined book** passes the money rule at four of five weight splits (only 30/70 breaches −25 % by a hair) and in both halves.
2. **The asymmetric rule is FRAGILE.** It still passes its own bar (Sharpe up in 3 of 4 calendars, worst drawdown 17 % vs 23 %) and wins both
   halves, but only two of four neighbours hold (RSI 25 and MA150 kill it: 0 of 4 calendars) and the shifted-signal placebo puts its Sharpe
   advantage at the 88th percentile: a third of the benefit is "being partly in cash at random times", the timing adds the rest at a level the
   data cannot separate from chance. Keep it as a drawdown option, not as an edge.
3. **The allocation layer is robust against the index in every block** — dual momentum at 6, 9 and 12 months, and equal weight IHSG / S&P /
   gold — but note which wins when: momentum led 2006-12 and 2013-19, equal weight led 2020-26 (gold), and the no-gold equal weight has a
   −44 % drawdown. The robust statement is "diversify out of 100 % IHSG", not one specific rule.
4. **Untestable is not the same as false.** The crash switch (2 episodes) and the +100 % take-profit (10 events) passed their bars and cannot
   be validated by any battery; they stay as book options, off.
5. **Closed stays closed.** Eleven families, ~150 trials, were falsified in their own menus; nothing here reopens them.
