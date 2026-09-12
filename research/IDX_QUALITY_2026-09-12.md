# IDX — The Buffett question, quantified (2026-09-12, late)

**Question (the operator's).** Is a Buffett-style book, durable high-quality businesses bought at a fair price and held while
the quality lasts, better than the value rule?

**Verdict: no, on this data.** Quality alone loses money in every calendar. Quality at a reasonable price (qarp) earns
+76 % to +132 % with 28–39 % drawdowns, roughly the rule and well under the strict composite (+128 % to +224 %, 22–25 %
drawdowns). A strict "compounder" filter passes about ten names and earns +35 % to +74 %. Holding while the quality is
intact is worse than the annual reset for every family. In the forward-return diagnostic the quality inputs have no
predictive power (ROE ρ −0.07, net margin −0.04, lowest ROE −0.02) except cash conversion (+0.16, positive in all six
years), and price still does the work (earnings yield +0.22). The strict composite already contains both of the pieces that
matter here: a positive-cash-flow gate and a cheapness rank.

## Pre-registered menu (12 trials; cumulative this session 68)

Pool as in rev. 3: the light-gate liquid pool on the day. Quality inputs, all point-in-time from the audited reports
published by the rebalance day's close: latest ROE, cash conversion (CFO / net profit, capped at 3), leverage (debt /
equity; financials at the pool median), net margin, and the lowest ROE across the audited years available (up to three,
one in 2021). Quality score = average of the five ranks.

| Family | Names | Hypothesis |
|---|---|---|
| quality | top fifth by quality score, price ignored | great businesses win at any price |
| qarp | top fifth by rank(quality) + rank(earnings yield) | great businesses at a fair price (Greenblatt's shape) |
| compounder | lowest ROE ≥ 15 % every available year, D/E ≤ 1 (financials exempt), CFO > 0, then the cheapest fifth | durable compounding bought cheaply |

Holding: **reset** (the rule's annual re-weighting) and **hold** (sell only when the latest audited ROE falls under 10 %,
the year is a loss, or the name is no longer eligible; keep the rest whatever their rank; entrants bought with the freed
cash). Sizes: natural fifth and ten. Script `research/idx_quality.py`; outputs `research-scratch/idx-screen/quality_out.txt`,
`quality_results.json`.

## Results (total return · Sharpe · max drawdown)

| Portfolio | May | Feb | Aug | Nov |
|---|---|---|---|---|
| quality, reset | −2 % · −0.02 · 39 % | −13 % · −0.18 · 42 % | −1 % · −0.02 · 39 % | +4 % · 0.05 · 32 % |
| quality, hold | −20 % · −0.26 · 45 % | −15 % · −0.23 · 42 % | −13 % · −0.17 · 44 % | −5 % · −0.07 · 38 % |
| quality ten, reset | +16 % · 0.15 · 34 % | −14 % · −0.17 · 48 % | +4 % · 0.04 · 39 % | −2 % · −0.03 · 37 % |
| qarp, reset | +132 % · 0.78 · 30 % | +80 % · 0.67 · 28 % | +76 % · 0.62 · 33 % | +112 % · 0.89 · 31 % |
| qarp, hold | +70 % · 0.52 · 31 % | +39 % · 0.39 · 32 % | +51 % · 0.45 · 35 % | +59 % · 0.59 · 28 % |
| qarp ten, reset | +88 % · 0.59 · 31 % | +98 % · 0.63 · 39 % | +96 % · 0.70 · 33 % | +110 % · 0.82 · 29 % |
| qarp ten, hold | +119 % · 0.60 · 33 % | +48 % · 0.38 · 41 % | +89 % · 0.64 · 30 % | +71 % · 0.67 · 26 % |
| compounder (≈10 names), reset | +74 % · 0.57 · 33 % | +35 % · 0.34 · 44 % | +44 % · 0.39 · 36 % | +52 % · 0.47 · 31 % |
| compounder, hold | +30 % · 0.30 · 34 % | +7 % · 0.09 · 43 % | +29 % · 0.29 · 42 % | +27 % · 0.31 · 31 % |
| *rule, reset (rev. 3)* | +106 % · 0.83 · 22 % | +111 % · 0.93 · 21 % | +114 % · 0.93 · 21 % | +63 % · 0.63 · 23 % |
| *strict, reset (rev. 3)* | +146 % · 0.98 · 22 % | +224 % · 1.44 · 22 % | +128 % · 0.94 · 25 % | +85 % · 0.79 · 24 % |

The compounder filter passes about ten names on every date, so its natural and ten-name sizes coincide. The quality
family holds only 10–24 names because its fifth is taken from the pool that also has a full quality record.

## Diagnostic: does quality on the day predict the next year?

Spearman with the forward one-year return, pooled over 549 (year, name) rows of the light-gate pool at May; per-year values
in brackets.

| Input | ρ | per year 2021…2026 |
|---|---|---|
| earnings yield | +0.22 | +0.01, +0.16, +0.11, +0.26, +0.51, +0.24 |
| cash conversion (CFO / profit) | +0.16 | +0.13, +0.27, +0.11, +0.13, +0.02, +0.21 |
| quality score | −0.06 | −0.03, +0.10, −0.11, −0.16, −0.01, +0.06 |
| ROE | −0.07 | −0.11, +0.04, −0.02, −0.14, +0.05, −0.19 |
| lowest ROE, up to 3 years | −0.02 | −0.11, +0.07, −0.13, −0.20, −0.06, +0.08 |
| net margin | −0.04 | +0.13, −0.05, −0.01, −0.10, −0.02, −0.07 |

Top quality fifth: mean forward return −4 %, median −8 %. Bottom fifth: mean 0 %, median −9 %. The market already prices
the visible quality; what is left is the price paid and whether the profit is real cash.

## Reading

1. **"Great business at any price" is the one thing that reliably loses here.** High ROE names in this pool are the
   expensive names, and 2021–2026 punished them (−1 % to −13 % over five years, drawdowns to 48 %).
2. **Adding a price rank rescues it, but only back to the rule.** qarp beats the rule in two calendars and loses in two;
   its drawdowns are 7–17 points deeper; its best calendar leans on one year (May 2025 +99 %).
3. **Holding while the quality is intact loses to the reset in every family.** The same result as for value: this data
   has no within-list persistence to hold onto.
4. **Cash conversion is the only quality input that predicts.** That is a post-hoc observation, not a result; if the
   operator wants it tested it goes into a new pre-registered menu (e.g. the strict composite with CFO / profit as a
   fourth rank) and is not to be adopted from this table.

## What to take from it

- Keep the strict composite as the planned successor to the rule (decision May 2027, as pre-registered).
- No Buffett-style catalog entry: the quantitative stand-ins for "wonderful business" do not survive contact with IDX
  prices. If the operator wants a judgment book, it runs on paper beside the rule.
- Candidate for the next menu, pre-registered before running: cash conversion as a rank input in the strict composite.
