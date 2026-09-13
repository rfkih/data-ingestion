# IDX — Trend overlays for entry and exit (2026-09-13)

**The operator's question.** Fundamentals pick the names; can a technical layer time the entry (buy only when the trend is
up, no falling knives) and the exit, so that a 2008- or 2020-sized crash does not take the book? Backtest from 2008.

**Verdict, in one paragraph.** One overlay does what was asked: the **index regime filter** (all to cash while the IHSG
is under its 200-day average, checked monthly, back in when above). Over 2008–2026 on a 100-name liquid basket it turned
a 51 % maximum drawdown into 21 % (2008: 0 instead of −31 %; 2020: −8 % instead of −46 %) and, with cash earning a
deposit rate, ended *higher* (+588 % against +464 %, Sharpe 0.94 against 0.50). Its price is paid in calm years: on the
real strict book over 2021–2026 it gave up 8 % to 49 % of the return depending on the calendar, because that window has
no crash to be saved from. By the criterion written before the run it is therefore *not* adopted automatically; the
decision is the operator's, with those two numbers side by side. Per-name trend rules, absolute momentum and a monthly
trailing stop all protect less and cost as much or more. The operator's entry idea, **buy a listed name only when it is
above its 200-day average**, is not insurance (it changes nothing in a crash) but it *added* return in three of four
calendars on the real book and cost nothing in the fourth; it is worth offering as the book's entry rule.

## What was tested (pre-registered; 12 trials, cumulative 83, plus one post-hoc arm counted as 84)

**Part A, 2008–2026, price only.** Yahoo adjusted closes cached in `research-scratch/idx` (the 450 names alive today, plus
^JKSE). Survivorship: only names alive in 2026 exist in that cache, so the basket's own drawdowns are flattered; every
overlay is measured against the same basket, so the comparison is fair even if the level is not. Price returns, no
dividends. Basket: each May, the 100 most traded names (60-day median value) with a year of history, equal weight, drift
mode. Overlays checked on the first trading day of each month, trades at that close. Cash earns 4 %/yr (run 1 paid 0;
kept in `trend_overlay_out_run1_cash0.txt`).

| Arm | Rule |
|---|---|
| index | all to cash while JKSE < SMA200; back in when above |
| index, band | exit below 0.97 × SMA200, re-enter above 1.03 × SMA200 |
| name trend | hold a name only while above its own SMA200; re-entrants capped at one slot |
| name momentum | hold a name only while its 12-1 month return is positive |
| stop | sell a name 20 % under its highest close since entry; re-enter when back above SMA200 |
| entry only (post hoc) | buy a listed name only when above its SMA200; never sell on trend |

**Part B, 2021–2026, the real book.** The strict composite (point-in-time lists, real costs, dividends net of tax) with the
same overlays, four rebalance calendars. Drift mode with entrants capped at one equal-weight slot; cash 4 %/yr. The
reference line here is that capped-drift strict, not the rev. 3 reset figure, so the arms compare like with like.

**Adoption criterion, declared before the run.** An overlay goes on the book only if (i) in Part A it cuts the basket's
2008 and 2020 episode drawdowns by at least 10 points each, and (ii) in Part B its total return is within 20 % (relative)
of plain strict in at least 3 of 4 calendars and its worst-calendar drawdown is not deeper.

Script `research/idx_trend_overlay.py`; outputs `research-scratch/idx-screen/trend_overlay_out.txt`,
`trend_overlay_results.json`. Simulator additions: `cap` (a number or a function of the date) and `cash_rate`.

## Part A: 2008–2026 (basket of 100; total · CAGR · Sharpe · max drawdown; then the drawdown inside each episode)

| Arm | Total | CAGR | Sharpe | mDD | 2008 | 2011 | 2013 | 2015 | 2018 | 2020 | 2022 | 2025 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| basket, no overlay | +464 % | 9.9 % | 0.50 | 51 % | −31 | −21 | −33 | −33 | −21 | −46 | −17 | −20 |
| index regime | +588 % | 11.1 % | 0.94 | 21 % | 0 | −21 | −16 | −6 | −8 | −8 | −15 | 0 |
| index regime, band | +352 % | 8.6 % | 0.70 | 27 % | 0 | −21 | −26 | −11 | −12 | −8 | −15 | 0 |
| name trend | +882 % | 13.3 % | 0.95 | 27 % | −7 | −17 | −25 | −10 | −14 | −5 | −14 | −12 |
| name momentum | +484 % | 10.1 % | 0.69 | 34 % | −16 | −20 | −34 | −16 | −15 | −14 | −17 | −13 |
| trailing stop 20 % | +607 % | 11.2 % | 0.73 | 39 % | −8 | −17 | −21 | −13 | −18 | −35 | −15 | −15 |
| entry only (post hoc, own baseline +471 %) | +493 % | 10.2 % | 0.52 | 49 % | −18 | −23 | −33 | −32 | −19 | −46 | −15 | −23 |
| IHSG, buy and hold | +174 % | 5.7 % | 0.29 | 56 % | −56 | −22 | −24 | −25 | −16 | −38 | −9 | −18 |
| IHSG with the index regime | +295 % | 7.8 % | 0.60 | 23 % | 0 | −21 | −16 | −8 | −12 | −7 | −9 | 0 |

With cash at 0 (run 1) the index regime ended level with the basket (+386 % against +383 %) at less than half the
drawdown; about 30 % of days were spent in cash. The band version re-enters late and loses the rebounds. The per-name
trend line looks best of all, but it is the arm survivorship flatters most: every name in the cache that fell under its
average later came back, by construction. The trailing stop at monthly checks is too slow for a crash (−35 % in 2020).

## Part B: the strict book, 2021–2026 (total · Sharpe · max drawdown; 2025 Jan–Apr drawdown in brackets)

| Arm | May | Feb | Aug | Nov |
|---|---|---|---|---|
| strict, capped drift | +107 % · 1.11 · 18 % (−9) | +158 % · 1.43 · 17 % (−12) | +74 % · 0.88 · 17 % (−12) | +62 % · 0.85 · 18 % (−13) |
| index regime | +66 % · 1.03 · 14 % (0) | +80 % · 1.26 · 11 % (0) | +68 % · 1.09 · 10 % (0) | +45 % · 0.97 · 11 % (0) |
| index regime, band | +70 % · 1.06 · 9 % (0) | +94 % · 1.31 · 10 % (0) | +71 % · 1.06 · 12 % (0) | +46 % · 0.92 · 12 % (0) |
| name trend | +95 % · 1.12 · 11 % (−4) | +95 % · 1.08 · 17 % (−8) | +70 % · 0.88 · 16 % (−3) | +42 % · 0.69 · 14 % (−4) |
| trailing stop 20 % | +94 % · 1.06 · 12 % (−6) | +107 % · 1.13 · 18 % (−9) | +63 % · 0.78 · 17 % (−6) | +54 % · 0.82 · 16 % (−6) |
| entry only | +131 % · 1.18 · 15 % (−11) | +156 % · 1.32 · 18 % (−11) | +111 % · 1.02 · 20 % (−15) | +84 % · 1.00 · 16 % (−10) |

## Criterion, mechanically, and the reading

| Overlay | (i) 2008 / 2020 cut | (ii) within 20 % | Result | Reading |
|---|---|---|---|---|
| index regime | +31 / +38 pts | 1 of 4 | not adopted | the only real crash insurance; fails the calm-window clause because 2021–2026 has no crash |
| index regime, band | +31 / +38 pts | 1 of 4 | not adopted | worse than the plain filter everywhere |
| name trend | +24 / +41 pts | 2 of 4 | not adopted | survivorship-flattered in Part A; costs 10–40 % in Part B |
| name momentum | +15 / +32 pts | no B arm | not adopted | weakest protection |
| trailing stop | +23 / +12 pts | 3 of 4 | passes the letter | still −35 % in 2020 and a 39 % drawdown over 18 years: passes the 10-point bar, fails the purpose. Not put on the book. The bar should have been a level (say, 2020 ≤ −15 %), not a cut. |
| entry only | no A arm; post hoc +22 pts, no protection | 4 of 4, ahead in 3 | offer as entry rule | not insurance; a cheap improvement to how the list is bought |

## What this means for the book

1. **If the fear is a 2008 or 2020, the tool is the index regime filter**, checked monthly, no band, with the idle cash in
   a deposit or SBN. Over eighteen years it halved the pain and ended ahead. Over the last five it would have cost a
   third of the return. Both are true; the operator chooses which risk to carry.
2. **Do not use per-name stops or per-name trend as the crash defence.** They trade often, protect less, and the
   long-run case for them rests on survivors.
3. **The entry gate is worth having regardless**: at each rebalance buy only the listed names above their 200-day
   average, and buy the rest at the first monthly check where they cross. It does not protect in a crash; it buys later
   in a falling name and earlier in a rising one, and on this book that was worth +8 to +37 points over five years.
4. Neither goes on the book without the operator's word. Both are book-level options to build: a monthly check job, an
   "exits to cash" ticket when the regime turns off, a "re-entry" ticket when it turns on, and an entry gate in the
   ticket builder. The catalog would show each option's record next to the choice, as it does for strategies.
