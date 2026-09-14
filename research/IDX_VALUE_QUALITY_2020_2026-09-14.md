# IDX — The strict list from 2020: one more year, the post-crash one (2026-09-14)

**Question.** The operator asked for the backtest from 2020. IDX serves nothing before 2020-01-02 (prices) and FY2019
(financial reports), so 2020 is as far back as point-in-time data can go. The FY2019 audited workbooks were downloaded
and parsed today (299 for the desk's universe; 190 of them published before the May 2020 rebalance, the rest visible
from their publication dates), and `research/idx_value_quality.py` gained `--first-year`.

**Verdict.** Adding the May 2020 rebalance (six weeks after the COVID low) lifts the strict composite's CAGR by about
three points in each calendar and leaves its drawdown where it was (22–25 %). The extra year is a rebound year in
which the strict list made +22 % to +44 % and the liquid basket +28 % to +58 %: value with a quality gate lagged the
rebound in two calendars of three, because the sharpest bounce was in the names the gate excludes. The rule is
unchanged; the number to quote for the strict list is now 18–22 % a year over 2020–2026, still 22–25 % worst drawdown.

What this does not test: the crash itself. The first rebalance is after the low; how the list behaves *through* a crash
is known only from the 2008–2026 price-basket studies (regime filter: IDX_TREND_OVERLAY, IDX_ASYMMETRIC_2008).

## Set-up

`research/idx_value_quality.py --months 5,8,11 --first-year 2020`, everything else as rev. 3 (PIT universe, production
rank pool, real costs, dividends net of tax). February cannot start in 2020: on 2020-02-02 no FY2019 audit had been
published and FY2018 does not exist on IDX, so that calendar keeps its 2021 start. Output
`research-scratch/idx-screen/value_quality_2020_results.json`, `value_quality_2020_out.txt`.

The 2020 rebalances are thin: 70–102 liquid names (the 60-day value filter had only four months of bars), 60–89 with
fundamentals, strict pools of 29–36, lists of ten.

## Strict composite, 2020 start against 2021 start (CAGR · Sharpe · max drawdown)

| Calendar | 2021–2026 (catalog record) | 2020–2026 | Extra year (first rebalance → next) | Liquid basket, same year |
|---|---|---|---|---|
| May | 18.3 · 0.98 · 22 % | **22.1 · 1.07 · 22 %** | +44 % | +58 % |
| Aug | 17.5 · 0.94 · 25 % | **18.2 · 0.90 · 25 %** | +22 % | +28 % |
| Nov | 13.5 · 0.79 · 24 % | **18.1 · 0.97 · 24 %** | +43 % | +33 % |
| average of the three | 16.4 | **19.5** | | |

References 2020-05 → 2026-09: liquid basket 14.2 % (mDD 44 %), IHSG 5.7 % (mDD 42 %), LQ45 −0.9 %.

The May 2020 list: ASII, BBRI, BMRI, DMAS, GGRM, ITMG, LPPF, MNCN, PTBA, UNTR. Best contributors ITMG (+8.5 % of NAV),
DMAS (+7.9), ASII (+5.8); worst GGRM (−1.8).

## Reading

1. **Same rule, same shape, three more points.** The drawdowns are identical because they happen later (2022–2023 and
   the 2025 dip), and the extra year is uniformly positive. Sharpe moves little.
2. **In a rebound the gate costs return.** May 2020 → May 2021: strict +44 %, the whole liquid basket +58 %. The names
   that doubled off the low were the ones with a loss in 2019 or too much debt, which the strict gate refuses. That is the
   price of the gate, paid in the one year in six when it matters, and it is why the same gate has the shallower
   drawdowns in every other year.
3. **The loose-gate pure-value line (`value_qloose`, 36 % at May) is not a discovery.** It is the catalog's `value`
   family, already marked fragile: its 2025 calendar year is +154 % on a handful of names, its August calendar is 12.8 %,
   and in rev. 3 it held Sritex to zero. The same pattern as every concentrated winner in this project.
4. **What to quote.** For the strict list: 18–22 % a year, 22–25 % worst drawdown, over six rebalance years including
   one post-crash rebound. The 2021 start remains the pre-registered record; this is context, not a new decision.

## What changed

- FY2019 audits in the database (299 parsed, PIT publication dates); `--first-year` on the value backtest; the strict
  catalog note carries the 2020 numbers. No book changes; trial count unchanged (a longer window of the same rule).
