# IDX — Momentum and profit growth combined, inside the strict list (2026-09-14)

**Question.** Both orderings had some power to name the strict list's eventual winners (41 % and 38 % of their picks in
the ex-post best three, against 25 % for chance). Combined, as a cut and as a tilt, do they beat the full list?

**Verdict.** Not by the pre-registered bar. Five names by the combined score beat the full list in three calendars of
four (24.1 % against 18.3 %) but lose that in two of four once each calendar's best name is removed, at a deeper
drawdown. The tilts (the whole list held, weights 2:1 from best to worst score) beat the full list in all four
calendars, by 0.2 to 1.5 points, with the same drawdown; that is a real but small ordering effect, worth about a point
a year, not enough to change the rule. The list stays equal weight.

## Pre-registered menu (4 trials; cumulative 155)

Combined score = the average of two ranks inside the list: 12-1 momentum (higher first) and audited net-profit growth
(higher first); a name without growth data ranks last on that input. Arms: mg3 (three best, equal weight), mg5 (five),
mg_tilt (whole list, weights linear from 2 at the best score to 1 at the worst), mom_tilt (the same on momentum alone).
Windows: 2021–2026 on four calendars, and 2020–2026 on May/Aug/Nov as a direction check. Same simulator and costs as
the strict record. Script `research/idx_mom_growth.py`; outputs `research-scratch/idx-screen/mom_growth_out.txt`,
`mom_growth_results.json`.

Reading rule, written before the run: a candidate only if (a) CAGR beats the full list in three of four calendars,
(b) worst drawdown not more than 5 points deeper (tilts) or 8 (cuts), (c) with its best-contributing name excluded (a)
holds, (d) it beats the full list in two of three 2020-start calendars.

## Results (CAGR · Sharpe · max drawdown), 2021 start

| Arm | May | Feb | Aug | Nov | avg | ex-best avg | worst mDD |
|---|---|---|---|---|---|---|---|
| strict, full list | 18.3 · 0.98 · 22 % | 23.8 · 1.18 · 22 % | 17.5 · 0.94 · 25 % | 13.5 · 0.79 · 24 % | 18.3 | | 25 % |
| mg3 | 24.1 · 0.79 · 37 % | 17.1 · 0.64 · 29 % | 16.3 · 0.57 · 32 % | 17.1 · 0.61 · 36 % | 18.6 | 13.9 | 37 % |
| mg5 | 27.5 · 1.09 · 26 % | 33.7 · 1.31 · 25 % | 17.2 · 0.69 · 29 % | 18.1 · 0.81 · 27 % | 24.1 | 17.4 | 29 % |
| mg_tilt | 19.8 · 1.01 · 22 % | 25.1 · 1.22 · 23 % | 17.6 · 0.91 · 25 % | 13.7 · 0.78 · 24 % | 19.1 | 15.5 | 25 % |
| mom_tilt | 20.3 · 1.05 · 22 % | 26.4 · 1.26 · 23 % | 18.2 · 0.93 · 25 % | 13.6 · 0.77 · 25 % | 19.6 | 15.8 | 25 % |

2020 start (May / Aug / Nov): strict 22.1 / 18.2 / 18.1; mg3 29.0 / 17.6 / 18.4; mg5 29.7 / 17.0 / 18.6; mg_tilt
23.3 / 18.1 / 17.8; mom_tilt 23.9 / 18.9 / 18.0.

| Arm | wins | ex-best wins | 2020 wins | worst mDD | verdict |
|---|---|---|---|---|---|
| mg3 | 2/4 | 1/4 | 2/3 | 37 % | tested |
| mg5 | 3/4 | 2/4 | 2/3 | 29 % | tested (clause c) |
| mg_tilt | 4/4 | 0/4 | 1/3 | 25 % | tested (clauses c, d) |
| mom_tilt | 4/4 | 0/4 | 2/3 | 25 % | tested (clause c) |

Clause (c) as written removes the best name from the variant but not from the reference, which is the right test for a
cut (the cut's edge may be that one name) and an unfair one for a tilt (the full list holds the name too). The fair
diagnostic, the name removed from both: mg_tilt +1.2 / +0.3 / −0.4 / +0.6 points against the full list ex the same name,
mom_tilt +1.8 / +0.4 / +0.4 / +0.2. The tilt's edge survives the diagnostic and stays small.

## Reading

1. **Five names is where the combined score looks best and is still one name.** 33.7 % at February is PTRO; without it
   20.0 %. SRTG, ENRG, DSNG carry the other calendars.
2. **The tilt is the honest version of the ordering effect: about a point a year, same drawdown.** Momentum alone tilts
   slightly better than momentum plus growth; growth adds nothing once momentum is in.
3. **Not adopted.** A point a year is inside the noise of six rebalances, and the tilt adds a second parameter (2:1) to
   the rule. If it still shows after the May 2027 pre-registered check, it can be revisited then.
