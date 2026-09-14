# IDX — Three names with the most upside, out of the strict list (2026-09-14)

**The operator's idea.** Keep the strict composite as the universe, hold only the three names with the highest upside,
and keep re-picking toward the highest upside.

**Verdict.** No definition of "upside" passes the pre-registered bar. Momentum (the three strongest 12-month returns) is
the one cut that beats the full list in all four calendars, at an average 29.5 % CAGR against 19.6 %, but it fails the
other two clauses: its worst drawdown is 36 % against 25 %, and each calendar's result is one name (TAPG, PTRO, ENRG,
DSNG); without that name it is ahead in two calendars of four and averages 17.4 %. Re-picking the cheapest three every
month (ep_m) is ahead in three calendars but with a 47 % drawdown and the same single-name dependence. Every other
definition is below the full list. The books stay on the full strict list; `strict_top3_mom` joins the catalog as
*tested* with its record, for a book that wants to run it small and knowingly.

## Pre-registered menu (9 trials; cumulative 146)

Universe: the strict composite's list at each annual rebalance, four calendars (May, Feb, Aug, Nov) 2021–2026, the rev. 3
simulator (reset mode, equal weight, real costs, dividends net of tax). Script `research/idx_top3_upside.py`; outputs
`research-scratch/idx-screen/top3_upside_out.txt`, `top3_upside_results.json`.

| Definition of "upside" | Top 3 by | Cadence |
|---|---|---|
| composite | the strict composite's own rank | annual |
| ep | earnings yield | annual, and monthly re-pick (ep_m) |
| vgap | ROE × B/P (residual-income fair-P/B gap) | annual, and monthly (vgap_m) |
| recovery | deepest drawdown from the 52-week high | annual, and monthly (recovery_m) |
| momentum | highest 12-month return | annual |
| growth | highest audited net-profit growth | annual |

Reading rule, written before the run: a candidate only if (a) CAGR beats the full list in three of four calendars,
(b) worst-calendar drawdown not more than 8 points deeper, (c) with its single best-contributing name excluded from every
pick, (a) still holds.

A note on the menu: `vgap` is algebraically `ep` (ROE × B/P = E/B × B/P = E/P), so its picks are identical to ep's in every
calendar. It is counted as registered, and it is the same trial twice; the honest count of distinct definitions is eight.

## Results (CAGR · Sharpe · max drawdown; then the same with the best-contributing name excluded)

| | May | Feb | Aug | Nov |
|---|---|---|---|---|
| **strict, full list** | 18.3 · 0.98 · 22 % | 29.1 · 1.44 · 22 % | 17.5 · 0.94 · 25 % | 13.5 · 0.79 · 24 % |
| composite top 3 | 13.7 · 0.59 · 35 % | 17.0 · 0.72 · 29 % | 7.4 · 0.32 · 33 % | 12.1 · 0.58 · 22 % |
| ep top 3 (= vgap) | 15.3 · 0.57 · 41 % | 7.8 · 0.32 · 38 % | 11.5 · 0.42 · 32 % | 6.3 · 0.28 · 33 % |
| recovery top 3 | 19.0 · 0.70 · 32 % | 19.3 · 0.65 · 42 % | 4.7 · 0.21 · 32 % | 7.6 · 0.30 · 30 % |
| **momentum top 3** | **31.2 · 1.03 · 30 %** | **49.9 · 1.40 · 30 %** | **21.7 · 0.68 · 32 %** | **15.3 · 0.56 · 36 %** |
| growth top 3 | 18.0 · 0.57 · 38 % | 28.4 · 1.08 · 32 % | 20.8 · 0.68 · 32 % | 20.0 · 0.71 · 33 % |
| ep, monthly re-pick | 21.0 · 0.73 · 47 % | 23.7 · 0.84 · 32 % | 26.7 · 0.83 · 31 % | 14.1 · 0.56 · 27 % |
| recovery, monthly re-pick | 16.0 · 0.58 · 36 % | 18.1 · 0.65 · 39 % | 11.6 · 0.44 · 36 % | 4.6 · 0.18 · 37 % |

Without the best name (re-picked without it):

| | May | Feb | Aug | Nov |
|---|---|---|---|---|
| momentum top 3 | 25.3 (ex TAPG) | 17.2 (ex PTRO) | 17.9 (ex ENRG) | 9.0 (ex DSNG) |
| growth top 3 | 12.6 (ex TAPG) | 26.1 (ex ELSA) | 10.6 (ex ENRG) | 16.0 (ex AKRA) |
| ep, monthly | 10.8 (ex SRTG) | 13.9 (ex PTRO) | 20.4 (ex ENRG) | 15.0 (ex ADRO) |

| Definition | avg CAGR | avg ex-best | wins vs full | wins ex-best | worst mDD | verdict |
|---|---|---|---|---|---|---|
| composite | 12.6 | 9.6 | 0/4 | 0/4 | 35 % | tested |
| ep (= vgap) | 10.2 | 3.8 | 0/4 | 0/4 | 41 % | tested |
| recovery | 12.7 | 7.5 | 1/4 | 0/4 | 42 % | tested |
| momentum | 29.5 | 17.4 | 4/4 | 2/4 | 36 % | tested (fails b, c) |
| growth | 21.8 | 16.3 | 2/4 | 1/4 | 38 % | tested |
| ep, monthly | 21.4 | 15.0 | 3/4 | 2/4 | 47 % | tested (fails b, c) |
| recovery, monthly | 12.6 | 11.8 | 0/4 | 0/4 | 39 % | tested |
| strict, full list | 19.6 | | | | 25 % | the rule |

## Reading

1. **Concentration to three names does not raise the expected return of the value rule; it raises its variance.** The
   cheapest-three cuts (composite, ep, recovery) are all below the full list on average, with drawdowns 10–20 points
   deeper. The full list's return comes from a few re-ratings a year that nobody can name in advance; three names miss
   them more often than they catch them.
2. **Momentum is the one ordering that consistently finds the re-rating in progress**, which is why it wins every calendar.
   But the whole win is one stock per calendar (PTRO's 2024 run alone turns the February calendar from 17 % to 50 %).
   Those runs are real, and unforecastable: whether the next momentum leader in the strict list doubles or halves is not
   something the backtest can say. Sharpe 0.56–1.40 at 30–36 % drawdowns is a lottery with a good ticket price, not an edge.
3. **Monthly re-picking adds cost and drawdown, not return**, once the one-name effect is removed. The picture the
   operator had in mind (rotate toward whatever has the most room) is, in the data, rotating toward whatever fell most,
   which is the worst-performing definition here (recovery).
4. **The one legitimate use.** A small sleeve, sized so that a 36 % drawdown on the sleeve is bearable, running
   `strict_top3_mom` next to the full-list book: it shares the same universe and calendar, so it costs nothing to
   administer. It is in the catalog for that, marked *tested*, with this record attached. It is not a replacement.

## What changed

- `strict_top3_mom` in the catalog (status *tested*, params gate strict / order mom / size 3); a family may now carry its
  own cut in `params.size`; history import understands the top-3 output (source `top3`).
- Trials: 146. The books stay on the full strict list.
