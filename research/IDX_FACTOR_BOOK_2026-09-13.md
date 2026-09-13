# IDX — A factor book from the literature, against the strategy we have (2026-09-13)

**The operator's ask.** Build a strategy from quantitative theory rather than from menus of ideas, and compare it with
the deployed strict composite.

**Verdict.** The textbook stack loses to the strategy we have in every calendar. A four-factor composite (value,
momentum, quality, low volatility, equal factor weights) inside the strict gate earns 6 to 17 % a year against the strict
composite's 14 to 24 %, with the same or deeper drawdowns; inverse-volatility weights, volatility targeting and
time-series momentum each lower the return further while lowering the drawdown, and only the full stack buys a materially
smaller drawdown (14 % against 22–25 %) at half the return. The reason is the one this session keeps finding: in this
market and window the premium is *cheapness inside a quality gate*; adding momentum and low-volatility ranks dilutes the
value tilt (the factor list shares only 45–56 % of its names with the strict list) and swaps cheap, volatile re-raters for
expensive, calm names. Quality adds nothing beyond the gate because the gate *is* the quality screen.

## The bricks (all documented premia and rules)

| Brick | Source | Implementation here |
|---|---|---|
| value | Fama-French | average rank of E/P, B/P, DY (the desk's composite) |
| momentum | Jegadeesh-Titman; Asness-Moskowitz-Pedersen | rank of the 12-1 month return |
| quality | Asness-Frazzini-Pedersen (QMJ) | average rank of ROE, cash conversion, −D/E; the strict gate as the screen |
| low volatility | Frazzini-Pedersen (BAB) | rank of −60-day realised volatility |
| volatility targeting | Moreira-Muir | exposure = min(1, 15 % / realised basket vol), monthly |
| time-series momentum | Moskowitz-Ooi-Pedersen | cash while the COMPOSITE's 12-month return ≤ 0, monthly |

Pre-registered (4 trials; cumulative 130): strict pool, composite = mean of the four factor ranks, top fifth (≥ 10),
annual rebalance in four calendars, monthly exposure checks, real costs, dividends net of tax, cash 4 %/yr. Reading rule:
a candidate only if Sharpe beats strict in ≥ 3 of 4 calendars with CAGR ≥ 90 % of strict's there and no deeper worst
drawdown. Script `research/idx_factor_book.py`; outputs `research-scratch/idx-screen/factor_book_out.txt`,
`factor_book_results.json`. The simulator gained fractional `exposure` (tested).

## Results (CAGR · Sharpe · max drawdown; average exposure; share of names in common with strict)

| Arm | May | Feb | Aug | Nov | Exposure | Overlap |
|---|---|---|---|---|---|---|
| **strict composite (deployed)** | **18.5 · 0.99 · 22 %** | **24.4 · 1.35 · 22 %** | **17.6 · 0.94 · 25 %** | **13.7 · 0.80 · 24 %** | 1.00 | — |
| F1 four factors, equal weight | 16.8 · 0.99 · 25 % | 6.4 · 0.48 · 23 % | 11.6 · 0.68 · 27 % | 11.1 · 0.69 · 24 % | 1.00 | 0.45–0.56 |
| F2 + inverse-vol weights | 14.0 · 0.89 · 24 % | 6.7 · 0.52 · 21 % | 9.3 · 0.61 · 26 % | 9.4 · 0.65 · 22 % | 1.00 | |
| F3 + volatility targeting 15 % | 12.5 · 0.87 · 19 % | 5.0 · 0.40 · 23 % | 8.1 · 0.58 · 24 % | 6.5 · 0.48 · 18 % | 0.92–0.96 | |
| F4 + time-series momentum | 11.1 · 0.89 · 14 % | 3.4 · 0.33 · 14 % | 6.2 · 0.53 · 14 % | 5.1 · 0.46 · 14 % | 0.68–0.72 | |

Reading rule: F1 wins 1 of 4, the others 0 of 4. **All four recorded as tested.**

## Brick by brick

1. **Adding momentum and low vol to value costs return everywhere and most in February** (24.4 % → 6.4 %): the factor
   list skips the cheap, volatile names that re-rated (PTRO, ENRG, TOBA, DSNG) because their volatility rank is poor and
   their momentum was not yet there at the rebalance. Half the strict list never makes the factor list.
2. **Inverse-volatility weights** move money from the names that ran to the names that did not: −2 to −3 points.
3. **Volatility targeting** trims exposure to 0.92–0.96 on average and cuts the drawdown by 0–6 points for 1.5–3 points
   of return; on a book that already sits at 18 % vol, a 15 % target barely binds and mostly adds trades.
4. **Time-series momentum on the index** is the regime filter by another name: exposure 0.7, drawdown 14 % in every
   calendar, return roughly halved. Same trade as the MA200 filter, same reading: insurance, not alpha.

## Why theory did not beat the house rule here

The literature's premia are averages over many markets and decades; which one dominates in a given market and window is
an empirical question. In IDX 2021–2026 the value premium was large and momentum's contribution was calendar-dependent
(the momentum families earlier: +144 % at May, +65 % at November), so an equal-weighted blend dilutes the strong factor
with the weak ones. Quality belongs in the screen, where it already is, not in the rank, where it pushes toward expensive
names. The strict composite is, in factor language, "value with a quality screen, equal weight, annual", and every
attempt to make it more textbook made it worse.

## What stays

- The strict composite remains the book. The factor book is recorded, not adopted.
- The two risk bricks (vol targeting, TSMOM) do what the overlay study already showed: less drawdown for less return.
  If the operator wants that trade, the MA200 regime filter is the simpler, already-built form of it.
- Trials counted this session: 130.
