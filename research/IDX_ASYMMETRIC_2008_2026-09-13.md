# IDX — The asymmetric rule from 2008 (2026-09-13)

Companion to `IDX_ASYMMETRIC_2026-09-13.md`. Fundamentals exist only from 2020, so the rule is tested here as a price
overlay on the 100-name liquid basket used for the regime filter's long test (Yahoo cache, survivors only, so per-name
rules are flattered a little; every arm is measured on the same basket). Monthly checks, drift with a 1/100 cap, real
costs, price returns, cash 4 %/yr, 2008-05 to 2026-09. Three trials; cumulative 137. Script
`research/idx_asymmetric_2008.py`; outputs `research-scratch/idx-screen/asymmetric_2008_out.txt`, `asymmetric_2008_results.json`.

## Results

| Arm | Total | CAGR | Sharpe | mDD | 2008 | 2011 | 2013 | 2015 | 2018 | 2020 | 2022 | 2025 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| basket, no rule | +497 % | 10.2 % | 0.50 | 51 % | −36 | −23 | −34 | −35 | −20 | −47 | −18 | −22 |
| entry gate only | +552 % | 10.8 % | 0.52 | 53 % | −18 | −23 | −35 | −33 | −21 | −47 | −19 | −24 |
| symmetric (hold only above MA200) | +912 % | 13.4 % | 0.94 | 27 % | −7 | −18 | −25 | −10 | −15 | −5 | −14 | −12 |
| regime filter only | +794 % | 12.7 % | 0.86 | 25 % | 0 | −22 | −20 | −8 | −9 | −13 | −18 | 0 |
| **asymmetric, RSI entry** | +833 % | 12.9 % | 0.76 | 42 % | −17 | −21 | −26 | −21 | −22 | **−39** | −16 | −16 |
| asymmetric, Bollinger entry | +755 % | 12.4 % | 0.75 | 44 % | −18 | −19 | −26 | −17 | −24 | −39 | −16 | −15 |
| **asymmetric + regime filter** | +669 % | 11.8 % | **0.93** | **21 %** | **0** | −20 | −19 | −6 | −9 | **−2** | −16 | **0** |

Reading rule (drawdown at least 5 points shallower than the basket's with CAGR within 2 points): all three confirmed.

## Reading

1. **The asymmetric rule is a per-name damper and a small return adder over eighteen years** (+2.7 points of CAGR,
   drawdown 51 % → 42 %), consistent with the 2021–2026 book result. Mean-reversion entries plus trend-break exits pay.
2. **It is not crash insurance.** 2020: −39 % against −47 % without it. In a market crash every name crosses under its
   average in the same month and the exits fire after most of the damage; the oversold entries then buy the first
   bounce, which in March 2020 was a real one, but the drawdown is already taken.
3. **The two halves together are the smoothest path in the whole session**: drawdown 21 %, 2008 flat, 2020 −2 %,
   April 2025 flat, Sharpe 0.93, at 11.8 % a year against the basket's 10.2 %. The regime filter handles the market;
   the asymmetric rule handles the names; neither does the other's job.
4. The symmetric rule's higher total (+912 %) is the arm survivorship flatters most (every re-entry above the average
   "worked" because the name is alive today) and it cost a third of the return on the real book; it is not the choice.

## What this settles

- The operator's rule is real, on both windows: a damper with a positive expected cost, not a crash shield.
- The recommended stack for a book that wants both return and sleep: **strict composite + regime filter (MA200 on the
  IHSG) + asymmetric per-name rule (exit on a cross under MA200, enter when RSI-14 ≤ 30 or above MA200)**. On 2021–2026
  that is CAGR 10–15 % with 11–15 % drawdowns; on 2008–2026 it is the 21 % line above.
