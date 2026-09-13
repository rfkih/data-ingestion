# IDX — The operator's asymmetric rule: sell on a trend break, buy when oversold (2026-09-13)

> From 2008, as a price overlay on the long basket: `IDX_ASYMMETRIC_2008_2026-09-13.md` (a damper and a small return adder over eighteen years, not crash insurance; with the regime filter the smoothest path of the session).

**The operator's idea.** Sell a name when its price breaks under its 200-day average, but do not wait for the trend to
turn before buying: buy a listed name when it has fallen into an oversold zone, or once an accumulation base has formed.

**Verdict.** The asymmetric rule with an RSI entry is the first per-name rule this session that passes its pre-registered
bar: Sharpe above the plain strict composite in three calendars of four with at least 90 % of its return, worst drawdown
17 % against 22 %, and the April 2025 dip cut from −12…−15 % to −3…−8 %. The asymmetry is what makes it work: the exit
fires only on a cross from above to below the average, so a name bought oversold is not thrown out for being under it,
which is exactly what sank the symmetric "hold only above MA200" rule (a third of the return gone). The Bollinger entry
is a coin flip against RSI (better in May, worse in November), the 20 % stop only costs return, and the accumulation-base
entry waits too long: the base rarely forms while a value name is on the list, so the book sits in cash and earns 4 to 6
points less a year.

## Pre-registered menu (4 trials; cumulative 134)

Strict composite lists, four calendars, monthly checks at the first trading day's close, drift mode with a one-slot cap,
real costs, dividends net of tax, cash 4 %/yr. Script `research/idx_asymmetric.py`; outputs
`research-scratch/idx-screen/asymmetric_out.txt`, `asymmetric_results.json`.

| Element | Rule |
|---|---|
| exit (all arms) | at a check, sell a held name that was above its MA200 at the previous check and is below it now; names that left the list leave at the annual rebalance |
| entry | a listed name not held is bought at a check when it is oversold OR above its MA200 |
| oversold, RSI | 14-day RSI at or under 30 |
| oversold, BB | close under the lower Bollinger band (20-day mean − 2σ) |
| base (the operator's clarification) | under the MA200, 60-day close range ≤ 20 %, 60-day OBV balance > 0, 20-day mean ≥ 60-day mean |
| stop variant | RSI arm plus a sale when a held name is 20 % under its purchase close |

Reading rule, declared before the run: a candidate only if Sharpe beats `none` with CAGR ≥ 90 % of none's in three of
four calendars and the worst drawdown is shallower.

## Results (CAGR · Sharpe · max drawdown; the 2025 Jan–Apr episode drawdown in brackets)

| Arm | May | Feb | Aug | Nov |
|---|---|---|---|---|
| none (hold to the rebalance) | 17.9 · 1.00 · 22 % (−12) | 24.0 · 1.41 · 21 % (−15) | 16.7 · 0.95 · 19 % (−14) | 13.0 · 0.81 · 22 % (−15) |
| entry gate only (reference) | 16.8 · 1.14 · 15 % (−11) | 18.1 · 1.29 · 18 % (−11) | 15.8 · 1.02 · 20 % (−15) | 13.5 · 0.99 · 16 % (−11) |
| symmetric: hold only above MA200 (reference) | 13.3 · 1.11 · 11 % (−4) | 12.6 · 1.06 · 17 % (−8) | 10.9 · 0.88 · 16 % (−3) | 7.4 · 0.68 · 14 % (−4) |
| **asymmetric, RSI entry** | **16.8 · 1.19 · 16 % (−5)** | 17.2 · 1.26 · 17 % (−8) | **15.8 · 1.09 · 16 % (−3)** | **12.7 · 0.99 · 14 % (−5)** |
| asymmetric, Bollinger entry | 16.8 · 1.23 · 11 % (−4) | 17.8 · 1.28 · 18 % (−9) | 15.8 · 1.11 · 15 % (−4) | 11.4 · 0.85 · 17 % (−9) |
| asymmetric, RSI + 20 % stop | 15.2 · 1.09 · 16 % (−5) | 16.6 · 1.24 · 17 % (−8) | 15.4 · 1.08 · 16 % (−3) | 12.6 · 0.99 · 14 % (−5) |
| asymmetric, accumulation-base entry | 12.4 · 0.95 · 16 % (−4) | 13.9 · 1.09 · 18 % (−8) | 10.5 · 0.77 · 15 % (−3) | 8.1 · 0.71 · 16 % (−4) |

| Arm | Sharpe-and-CAGR wins | Worst drawdown | Verdict |
|---|---|---|---|
| asymmetric, RSI | 3 of 4 | 17 % vs 22 % | **candidate** |
| asymmetric, Bollinger | 2 of 4 | 18 % | tested |
| asymmetric, RSI + stop | 2 of 4 | 17 % | tested |
| asymmetric, base | 0 of 4 | 18 % | tested |

## Reading

1. **Where the return goes.** Against the plain rule the RSI arm gives up 1 point of CAGR in May, Aug and Nov and 7 in
   February (the calendar whose 2024 was one name, PTRO, bought before it had any trend). In exchange the drawdown is
   4–8 points shallower in every calendar and the Sharpe higher in three.
2. **Why the exit is cheap here and expensive in the symmetric rule.** A cross from above to below the average happens
   to a value name a few times over its year on the list; the symmetric rule then also refuses to hold it until it climbs
   back, which is where the re-rating happens. The asymmetric rule sells the break but buys the oversold, so the name is
   back in the book quickly, often lower.
3. **Oversold beats "base".** The base definition is strict (four conditions) and a listed value name seldom satisfies it
   while cheap; the arm spent long stretches under-invested. Looser base definitions would drift back toward RSI.
4. **Against the entry gate alone**, which the operator already has: similar return, higher Sharpe in three calendars
   (1.19 vs 1.14, 1.09 vs 1.02, level in Nov), shallower drawdown in Aug and Nov. The difference is the trend-break exit.
5. **Caveats.** Five years, one cycle; the 2025 dip is where most of the drawdown benefit shows; RSI 30 and MA200 are the
   conventional settings, not tuned, and the Bollinger variant behaves alike, which is the right kind of neighbour check.

## If built

A book option next to the entry gate: `trend_exit` (sell at the monthly check a held name that crossed under its MA200
since the last check) and an oversold clause in the entry gate (buy a held-back name when its RSI-14 is at or under 30,
not only when it is above its MA200). The monthly check already exists; the exits ticket already exists; the card would
show RSI and the last cross. Not built until the operator says so.
