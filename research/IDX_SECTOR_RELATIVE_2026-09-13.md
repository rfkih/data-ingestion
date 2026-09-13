# IDX — Cheap and expensive relative to the industry and to growth (2026-09-13)

**The operator's correction.** A P/E of 5 can be a value trap and a P/E of 30 can be fair for a fast grower; "expensive"
should be judged against the sector and the growth (and against the analyst consensus), not against an absolute
multiple.

**Verdict.** The correction is right in principle and the data says the book already handles it the way that works
here: the value-trap defence is the **quality gate** (audited profit two years running, ROE ≥ 10 %, positive operating
cash flow, sane debt), not a relative multiple. Making cheapness *relative to the sector* or *adjusted for growth* made
the book worse in every calendar, and selling a name when it turns expensive against its own sector lost in every
calendar too. Cross-sector cheapness is where the return came from: whole industries were cheap together (coal and
energy in 2021, banks in 2022), and a sector-neutral rank throws that away. Audited growth is a lagging input: the
cheapest names often have falling profits, which is *why* they are cheap; the composite then earns the re-rating. A
consensus-based rule cannot be backtested (no point-in-time consensus exists in any source we have; Yahoo's target
prices need a paid session and have no history) and is left as a judgment input.

## Pre-registered menu (5 trials; cumulative 109)

2021–2026, four calendars, drift mode with a one-slot cap, cash 4 %/yr. Selection arms take the top fifth of the gated
pool, equal weight, once a year.

| Arm | Rule |
|---|---|
| sector_rel, light / strict gate | E/P, B/P, DY each as a percentile within the name's sector (sectors with fewer than 5 gated names fall back to the whole pool); score = mean percentile |
| growth_adj, light / strict gate | composite of ranks E/P, B/P, DY and audited profit growth: cheap and growing |
| sell_sector | strict book; at each monthly check sell a held name whose E/P is under the median E/P of its sector's gated names (expensive against its industry); cash waits for the next rebalance |

Reading rule, declared before the run: adopt over the strict composite only if ahead in at least three of four calendars
with no deeper worst drawdown. Script `research/idx_sector_relative.py`; outputs `research-scratch/idx-screen/sector_relative_out.txt`,
`sector_relative_results.json`.

## Results (total return · Sharpe · max drawdown)

| Arm | May | Feb | Aug | Nov | Ahead of strict |
|---|---|---|---|---|---|
| strict composite (deployed) | +142 % · 1.00 · 22 % | +234 % · 1.41 · 21 % | +120 % · 0.95 · 19 % | +81 % · 0.81 · 22 % | — |
| sector-relative, light gate | +85 % · 0.74 · 27 % | +83 % · 0.70 · 25 % | +82 % · 0.78 · 23 % | +65 % · 0.66 · 26 % | 0 of 4 |
| sector-relative, strict gate | +97 % · 0.79 · 29 % | +99 % · 0.82 · 23 % | +97 % · 0.87 · 21 % | +74 % · 0.76 · 23 % | 0 of 4 |
| growth-adjusted, light gate | +75 % · 0.61 · 26 % | +104 % · 0.79 · 27 % | +78 % · 0.70 · 20 % | +57 % · 0.57 · 23 % | 0 of 4 |
| growth-adjusted, strict gate | +119 % · 0.83 · 27 % | +142 % · 0.95 · 25 % | +88 % · 0.70 · 25 % | +67 % · 0.62 · 27 % | 0 of 4 |
| sell when expensive vs sector | +131 % · 0.99 · 20 % | +113 % · 1.01 · 20 % | +93 % · 0.85 · 20 % | +59 % · 0.70 · 22 % | 0 of 4 |

Every variant loses to the plain strict composite in every calendar, most by a third or more.

## Reading

1. **Value traps are a quality problem, not a multiple problem.** The strict gate is what separates a P/E 5 that earns
   its way out from a P/E 5 that never does; earlier menus showed it beating pure earnings yield in every calendar
   (rev. 3: +146 % against a fragile +323 % that held Sritex to zero).
2. **Sector-relative cheapness removes the signal.** In this market the cheap names cluster by industry and the whole
   cluster re-rates; ranking inside the sector buys the "least bad" name of an expensive sector and skips the cheap
   sector. This is also why the sector cap tested in rev. 3 gave no consistent benefit.
3. **Growth adjustment looks backward.** Audited growth is a year old on the day it is used, and the composite's winners
   are often names whose last audited year was poor. A forward growth estimate would be the right input, and that is the
   consensus data we do not have.
4. **"Expensive against the sector" is not a sell signal here** for the same reason "no longer cheap against the pool"
   was not (IDX_SELL_RULES): the re-rating is the return, and the annual rebalance harvests it.

## What this means for the book

- Nothing changes in the rule. The strict composite stays; the annual rebalance stays the valuation exit.
- Where the operator's judgment enters is the pack: the card carries the sector, growth and the strict-gate flags, and a
  name that is cheap for a reason the numbers cannot see (a fair P/E 30 grower, a P/E 5 trap the gate missed) is a
  pack veto or a pack sell, which the exits ticket already honours.
- If a consensus feed becomes available (a paid terminal, or a broker export), "price above consensus" can be shown on
  the card as a judgment input. It cannot be backtested without a point-in-time history, so it will not become a rule.
