# IDX — Cash conversion as a rank input (2026-09-12, late)

**Question.** The quality menu's diagnostic found one quality input with forward power: operating cash flow per rupiah of
profit (ρ +0.16, positive in all six years). That was post-hoc. This is the pre-registered test: add it as a fourth rank to
the composite (E/P, B/P, DY, cash conversion), under the light gate and under the strict gate, natural size and ten.

**Verdict.** The pre-registered criterion passes for strict+conv (beats the strict composite in 4 of 4 calendars, worst
drawdown 27 % against 25 %) and fails for the other two (drawdown clause). But the pass is one stock: ENRG, chosen by the
cash-conversion rank at the 2025 rebalances, rose about eightfold in the following year. Re-simulated without ENRG, the
two are within eight points in every calendar, strict+conv ahead in one. That is not an edge; it is a lottery ticket that
paid. The books follow the strict composite. strict_cash is in the catalog, marked tested, for a book that wants it.

## Pre-registered menu (3 trials; cumulative this session 71)

| Portfolio | Names | Ranks |
|---|---|---|
| rule+conv | light gate, top fifth | E/P, B/P, DY, cash conversion |
| strict+conv | strict gate, top fifth | same four |
| strict10+conv | strict+conv cut to ten | same four |

Cash conversion = CFO / net profit from the same audited year the yields use, capped at 3; a name without it ranks lowest
on that input (every name in the pool had one on the dates checked: 104 of 104 in 2022, 88 of 88 in 2024, 123 of 123 in
2026). Equal weight, annual rebalance, the rev. 3 simulator and costs.

**Adoption criterion, declared before the run:** a +conv variant replaces its base only if its total return beats the base
in at least three of four calendars and its worst-calendar drawdown is not more than three points deeper.

Script `research/idx_cash_conversion.py`; outputs `research-scratch/idx-screen/cash_conversion_out.txt`,
`cash_conversion_results.json`.

## Results (total return · Sharpe · max drawdown)

| Portfolio | May | Feb | Aug | Nov |
|---|---|---|---|---|
| rule | +106 % · 0.83 · 22 % | +111 % · 0.93 · 21 % | +114 % · 0.93 · 21 % | +63 % · 0.63 · 23 % |
| rule+conv | +356 % · 1.16 · 28 % | +178 % · 1.17 · 26 % | +264 % · 1.24 · 23 % | +103 % · 0.88 · 27 % |
| strict | +146 % · 0.98 · 22 % | +224 % · 1.44 · 22 % | +128 % · 0.94 · 25 % | +85 % · 0.79 · 24 % |
| strict+conv | +263 % · 1.16 · 27 % | +356 % · 1.65 · 24 % | +128 % · 0.96 · 23 % | +116 % · 0.98 · 22 % |
| strict ten | +105 % · 0.78 · 22 % | +132 % · 1.05 · 26 % | +138 % · 0.95 · 25 % | +96 % · 0.85 · 23 % |
| strict10+conv | +274 % · 1.11 · 30 % | +390 % · 1.70 · 23 % | +129 % · 0.91 · 23 % | +142 % · 1.06 · 24 % |

Criterion, mechanically: rule+conv beats the rule 4/4 but worst drawdown 28 vs 23 → keep the rule. strict+conv beats
strict 4/4, worst drawdown 27 vs 25 → adopt. strict10+conv 3/4, worst drawdown 30 vs 26 → keep strict ten.

## Where the gap comes from

The lists differ by two or three names a year. In 2025 the cash-conversion rank brought in ENRG, which then returned
+786 % (May 2025 to May 2026) and +431 % (Feb 2025 to Feb 2026).

| May 2025 → May 2026 | strict | strict+conv |
|---|---|---|
| equal-weight mean of the names | +29 % | +94 % |
| median name | +24 % | +27 % |
| best name | TAPG +109 % | ENRG +786 % |

Diagnostic (not a trial): the same portfolios re-simulated with ENRG removed from every list.

| Calendar | strict, ex-ENRG | strict+conv, ex-ENRG |
|---|---|---|
| May | +136 % · 0.93 · 22 % | +147 % · 0.96 · 22 % |
| Feb | +224 % · 1.44 · 22 % | +216 % · 1.44 · 21 % |
| Aug | +109 % · 0.85 · 25 % | +107 % · 0.86 · 23 % |
| Nov | +85 % · 0.79 · 24 % | +80 % · 0.78 · 22 % |

Without the one name, strict+conv wins one calendar of four. The criterion was written to catch calendar luck and did not
anticipate one name spanning two calendars; that is a lesson for the next criterion (add: not driven by a single name),
not a reason to move the goalposts silently. The record is kept as it is, and the reading above is the reading.

## What changed

- The books follow the **strict composite** from 2026-09-12 by the operator's decision ("sesuaikan dengan yang terbaik"),
  ahead of the pre-registered May 2027 date. The rule is the baseline in the catalog.
- **strict_cash** joins the catalog with status *tested* and its full record (sizes natural and ten) so the app shows it
  next to the others. `idx.candidate.conv` (migration 0011) carries the input from today's build on.
- Trials this session: 71. No further menus planned; the next scheduled decision is the May 2027 rebalance itself.
