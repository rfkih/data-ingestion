# IDX — Hold the winners? (2026-09-12, late)

**Question (the operator's, via Buffett).** Concentrated books are the *result* of holding winners for years, not of
sizing them big on the day of purchase. Rev. 3 and the ten-name menu tested sizing at purchase (rank tilts) and found nothing
robust. This tests what happens after purchase: never trim, and hold until the thesis breaks.

**Verdict.** Not trimming winners changes nothing: "drift" tracks the rule within a point in every calendar, so the
operator may skip the May trims (fewer trades, same result). Holding every name until it breaks the light gate, regardless
of rank, is a different animal: +185 % and +222 % in two calendars, +42 % and +90 % in the other two, Sharpe down to
0.45–0.89, drawdowns 37 %. It turns the book into a bet on whatever the early years happened to buy. And inside the list
there is no year-to-year persistence to exploit: the rank correlation between a name's return in year t and year t+1 is
+0.07 on 30 pairs. The Buffett effect needs Buffett's insight into which businesses endure; a screen does not have it, and
the closest quantitative stand-in, the quality gate, is already the strict composite.

## Pre-registered menu

| Mode | At each May |
|---|---|
| reset (the rule) | sell what left the list; re-weight everything held to equal weight |
| drift | sell what left the list; cash goes to the new entrants equally; nothing already held is touched, winners keep the weight they grew into |
| hold | sell only names that no longer pass the light gate that day (profit ≤ 0 or ROE < 5 %, or no longer eligible); keep the rest whatever their rank; buy the list's new entrants with the freed cash |

Families: the rule (natural size), the strict composite (natural size), the strict composite at ten. Nine portfolios, four
calendars, the same simulator and costs. Trials counted cumulatively: 56. Script `research/idx_hold_winners.py`; outputs
`research-scratch/idx-screen/hold_winners_out.txt`, `hold_winners_results.json`.

## Results (total return; Sharpe; max drawdown)

| Portfolio | May | Feb | Aug | Nov |
|---|---|---|---|---|
| rule, reset | +106 % · 0.83 · 22 % | +111 % · 0.93 · 21 % | +114 % · 0.93 · 21 % | +63 % · 0.63 · 23 % |
| rule, drift | +107 % · 0.83 · 22 % | +113 % · 0.93 · 21 % | +111 % · 0.90 · 20 % | +60 % · 0.60 · 23 % |
| rule, hold | +76 % · 0.62 · 26 % | +67 % · 0.62 · 32 % | +97 % · 0.78 · 23 % | +52 % · 0.52 · 28 % |
| strict, reset | +146 % · 0.98 · 22 % | +224 % · 1.44 · 22 % | +128 % · 0.94 · 25 % | +85 % · 0.79 · 24 % |
| strict, drift | +147 % · 0.97 · 22 % | +240 % · 1.46 · 23 % | +119 % · 0.86 · 26 % | +85 % · 0.78 · 25 % |
| strict, hold | +185 % · 0.76 · 37 % | +90 % · 0.78 · 28 % | +222 % · 0.88 · 37 % | +42 % · 0.45 · 26 % |
| strict ten, reset | +105 % · 0.78 · 22 % | +132 % · 1.05 · 26 % | +138 % · 0.95 · 25 % | +96 % · 0.85 · 23 % |
| strict ten, drift | +102 % · 0.76 · 22 % | +143 % · 1.09 · 26 % | +134 % · 0.92 · 26 % | +94 % · 0.82 · 23 % |
| strict ten, hold | +175 % · 0.73 · 38 % | +61 % · 0.62 · 28 % | +229 % · 0.89 · 36 % | +46 % · 0.49 · 26 % |

Reading:

1. **Trimming is irrelevant.** Drift and reset differ by a point or two everywhere. The list turns over most of its names
   every year, so the May trims are small money; the within-year drift already lets winners run.
2. **"Hold until it breaks" is a coin flip with bigger stakes.** Its two good calendars come from one year each (May 2025
   +118 %, Aug 2024 +41 % and 2025 +38 %) where names bought years earlier and kept regardless of rank happened to run.
   Its two bad calendars are worse than the plain rule. Drawdowns rise to 37 %.
3. **No persistence to lean on.** For names in two consecutive May lists, last year's better half returned +5 % the next
   year, the worse half +1 %; Spearman +0.07. The winners of a year are not the winners of the next.

## What to take from it

- Skip the May trims if you like: same outcome, fewer orders. (The ticket can do this: build in rebalance mode and skip the
  trim lines; a "no-trim" option is a small addition if wanted.)
- Do not replace the ranking with "hold while the thesis is intact". If the operator wants a Buffett-style book, that is a
  judgment book, run on paper next to the rule, not a rule change.
- The strict composite remains the only robust improvement on the rule across every question asked today.
