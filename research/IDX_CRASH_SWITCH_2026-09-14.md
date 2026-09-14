# IDX — Normal: strict with a momentum tilt; after a crash: the cheapest names (2026-09-14)

**The operator's idea.** Hold the strict composite (tilted to momentum) in a normal market; once the market has
crashed, shift to the most undervalued names, which lead the rebound; return when the market has recovered.

**Verdict.** The first switch this session that passes its pre-registered bar, and it passes cleanly: the crash-time
shift to the **cheapest fifth by earnings yield** beats the tilted strict list in every calendar of both windows
(2021 start: 23.9 % a year against 19.6 %; 2020 start: 24.2 % against 20.3 %), keeps beating it in three of four
calendars without its best crash-time name, and costs 4 points of worst drawdown (29 % against 25 %). The loose-gate
version is a point better still (24.4 %, 27 % drawdown). The price-only version (shift to the names that fell
furthest) fails everywhere: 47 % drawdowns; what fell most keeps falling. Cheap, not beaten, is what rebounds.

The caveat that has to sit next to the verdict: the crash rule was on in **two episodes**, July–November 2020 (in the
2020-start window only) and April 2025 to today, where it never turned off: the IHSG has not closed a month above its
200-day average since. So the 2021-start result is one long episode that is still running, and the whole test is
1.5 crashes. The mechanism is sound and the 2020 episode agrees, but this is a small sample, and the rule would be
holding the deep-value list right now.

## Pre-registered menu (3 trials; cumulative 173)

Crash on when the COMPOSITE closes 20 % or more under its 252-day high at a monthly check; off when it closes above
its 200-day average. Normal list: the strict composite with weights linear 2:1 from the highest to the lowest 12-1
momentum. Deep value, built at the check that turns the crash on and at annual rebalances while it stays on, equal
weight: `dv_strict_ep` (strict gate, cheapest fifth by E/P), `dv_loose_ep` (loose gate, cheapest fifth by E/P),
`dv_beaten` (strict gate pool, the fifth furthest under its 252-day high). References: strict (equal weight) and tilt
(no switch). Script `research/idx_crash_switch.py`; outputs `research-scratch/idx-screen/crash_switch_out.txt`,
`crash_switch_results.json`.

Reading rule, written before the run: candidate only if CAGR beats tilt in three of four 2021-start calendars and two
of three 2020-start calendars, worst drawdown not more than 5 points deeper, and with the best crash-time name excluded
still three of four; the price-only version must also beat the 2008 basket with a drawdown no more than 5 points deeper.

## Results (CAGR · Sharpe · max drawdown; the switch arms then without their best crash-time name)

2021 start (crash on 2025-04-08 → 2026-09, ten monthly checks):

| Arm | May | Feb | Aug | Nov | avg |
|---|---|---|---|---|---|
| strict | 18.3 · 0.98 · 22 % | 23.8 · 1.18 · 22 % | 17.5 · 0.94 · 25 % | 13.5 · 0.79 · 24 % | 18.3 |
| tilt (normal list, no switch) | 20.3 · 1.05 · 22 % | 26.4 · 1.26 · 23 % | 18.2 · 0.93 · 25 % | 13.6 · 0.77 · 25 % | 19.6 |
| **switch → strict-gate cheapest** | **23.1 · 1.11 · 28 %** (ex ENRG 20.3) | **30.1 · 1.33 · 28 %** (27.8) | **23.8 · 1.10 · 29 %** (21.4) | **18.6 · 0.95 · 28 %** (16.2) | **23.9** |
| switch → loose-gate cheapest | 22.1 · 1.07 · 27 % (20.1) | 30.9 · 1.37 · 27 % (28.4) | 25.2 · 1.15 · 27 % (22.5) | 19.5 · 0.99 · 27 % (16.8) | 24.4 |
| switch → most beaten | 18.3 · 0.73 · 47 % | 25.0 · 0.93 · 46 % | 17.6 · 0.67 · 46 % | 13.2 · 0.54 · 46 % | 18.5 |

2020 start (crash on 2020-07 → 2020-11 and 2025-04 → 2026-09):

| Arm | May | Aug | Nov | avg |
|---|---|---|---|---|
| strict | 22.1 · 1.07 · 22 % | 18.2 · 0.90 · 25 % | 18.1 · 0.97 · 24 % | 19.5 |
| tilt | 23.9 · 1.13 · 22 % | 18.9 · 0.91 · 25 % | 18.0 · 0.95 · 25 % | 20.3 |
| **switch → strict-gate cheapest** | **26.5 · 1.17 · 28 %** | **23.8 · 1.06 · 29 %** | **22.3 · 1.09 · 28 %** | **24.2** |
| switch → loose-gate cheapest | 27.4 · 1.19 · 27 % | 27.6 · 1.19 · 27 % | 23.0 · 1.12 · 27 % | 26.0 |
| switch → most beaten | 19.7 · 0.76 · 47 % | 17.1 · 0.66 · 46 % | 17.6 · 0.71 · 46 % | 18.1 |

2008–2026 basket, May calendar (price only, 43 crash-on months): basket 11.4 % · mDD 54 %; switch to the most beaten
14.8 % · 55 % (ex BRIS 14.4). It beats the basket on return with the same drawdown, and it is the price-only
definition, which failed on the strict book; not a plan.

| Variant | wins 2021 | wins 2020 | ex-best | worst mDD | verdict |
|---|---|---|---|---|---|
| strict-gate cheapest | 4/4 | 3/3 | 3/4 | 29 % | **candidate** |
| loose-gate cheapest | 4/4 | 3/3 | 3/4 | 27 % | **candidate** |
| most beaten | 0/4 | 0/3 | 0/4 | 47 % | tested |

Control, added after the run to read the result (not a trial): the cheapest strict-gate list held *all the time*
(`value_q`, 2020 start) makes 28.5 / 13.8 / 18.0 % at May / Aug / Nov with 30–32 % drawdowns; the switch makes
26.5 / 23.8 / 22.3 % with 28–29 %. The switch is not "pure value beats the composite"; it is the composite in normal
times and value in the crash, and it beats holding either one throughout.

## Reading

1. **Cheap rebounds; beaten does not.** The same crash, two definitions of undervalued: the cheapest-by-earnings list
   adds 4–6 points a year, the most-fallen list adds nothing and doubles the drawdown. After a crash the names that
   recover are the ones with earnings behind the price, not the ones with the deepest hole.
2. **The gate matters less in a crash.** The loose-gate list (profit and ROE ≥ 5 %, no cash-flow or debt test) does a
   point better than the strict-gate list with a shallower drawdown. In a rebound, the lower-quality cheap names bounce
   hardest. Over a long run the strict gate is the safer choice for the same idea, and the difference is inside the
   noise of two episodes.
3. **The cost is the drawdown while the crash deepens.** The switch happens at −20 %; if the market keeps falling (as in
   2026: −38 % by July) the deep-value list falls with it, and it is 4 points deeper at the trough than the strict list.
   The gain comes on the way up.
4. **Two episodes.** This is the thinnest evidence base of anything adopted in this project. The pre-registered rule
   passed with room to spare, the mechanism is the oldest one in value investing, and 2020 agrees with 2025–2026; but a
   third crash could read differently. It should run with that understood.

## If built

A book option next to the crash filter: `crash_switch` (on/off) with the crash state recorded at the monthly check
(on at −20 % from the 252-day high, off above the 200-day average); while on, the book's effective strategy is
`strict_ep` (strict gate, cheapest fifth by earnings yield alone, new catalog entry) and the monthly check issues a
rebalance ticket when the state flips. The momentum tilt in normal times is a second option (`mom_tilt`, the 2:1
weighting inside the list, IDX_MOM_GROWTH).

## Today (2026-09-11 close)

The crash rule is on (IHSG 28 % under its 52-week high, under its 200-day average). The strict-gate cheapest list:
SRTG, GJTL, DEWA, CTRA, EMTK, SIMP, PWON, BBYB, INDF, ASII, LSIP, JPFA, UNTR (13 names, P/E 3.3–6.6). Against the
strict list in ticket #15 it keeps eight names and swaps the four banks-and-retail names (BBNI, BBRI, BMRI, ACES) and
ELSA for DEWA, EMTK, BBYB, INDF, JPFA.
