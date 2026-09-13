# IDX — Trend overlays for entry and exit (2026-09-13, final numbers)

**The operator's question.** Fundamentals pick the names; can a technical layer time the entry (buy only when the trend is
up, no falling knives) and the exit, so that a 2008- or 2020-sized crash does not take the book? Backtest from 2008. Then:
is a 100-day average better than 200?

**Verdict, in one paragraph.** One overlay does what was asked: the **index regime filter** (all to cash while the IHSG
is under its 200-day average, checked monthly, back in when above). Over 2008–2026 on a 100-name liquid basket it turned
a 51 % maximum drawdown into 25 % (2008: 0 instead of −36 %; 2020: −13 % instead of −47 %) and, with cash earning a
deposit rate, ended well ahead (+794 % against +497 %, Sharpe 0.86 against 0.50). Its price is paid in calm years: on the
real strict book over 2021–2026 it gave up 0 % to 49 % of the return depending on the calendar, and it did not shorten the
book's own 2022 drawdowns, because the IHSG never fell under its average that year. By the criterion written before the
run it is *not* adopted automatically; the decision is the operator's, with those numbers side by side. Per-name trend
rules protect the book's own drawdowns somewhat better on the real data but cost a third to two thirds of the return; the
trailing stop protects least. The **entry gate** (buy a listed name only above its 200-day average) lowers drawdowns a
little and costs return in three of four calendars: a mild damper, not a free improvement (an earlier draft of this
report said otherwise; see the note on the allocation fix). The **200-day window stays**: 100 days looks best only on the
survivor basket and halves the return on the real book; 200 and 250 behave alike.

## What was tested (pre-registered; 12 trials + 1 post-hoc + 16 window arms; cumulative 100)

**Part A, 2008–2026, price only.** Yahoo adjusted closes cached in `research-scratch/idx` (the 450 names alive today, plus
^JKSE). Survivorship: only names alive in 2026 exist in that cache, so the basket's own drawdowns are flattered; every
overlay is measured against the same basket, so the comparison is fair even if the level is not; per-name signals are
the ones most flattered, since among survivors every dip resolved upward by construction. Price returns, no dividends.
Basket: each May, the 100 most traded names (60-day median value) with a year of history, equal weight, drift mode.
Overlays checked on the first trading day of each month, trades at that close. Cash earns 4 %/yr.

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
reference line is that same capped-drift strict, so the arms compare like with like.

**Adoption criterion, declared before the run.** An overlay goes on the book only if (i) in Part A it cuts the basket's
2008 and 2020 episode drawdowns by at least 10 points each, and (ii) in Part B its total return is within 20 % (relative)
of plain strict in at least 3 of 4 calendars and its worst-calendar drawdown is not deeper.

Scripts `research/idx_trend_overlay.py`, `research/idx_sma_window.py`; outputs `research-scratch/idx-screen/trend_overlay_out.txt`,
`trend_overlay_results.json`, `sma_window_out.txt`, `sma_window_results.json`. Simulator additions: `cap` (a number or a
function of the date) and `cash_rate`.

**Note on the allocation fix.** The first two runs of this study allocated the capped-drift purchases in the iteration
order of a Python set, so each entrant's share came out of what the entrants before it had left; totals wandered a few
points between runs and the baseline was under-invested. Fixed (shares of the pool at the start of the trade, order
independent, tested). Every number below is from the fixed runs; the earlier outputs are kept as
`trend_overlay_out_run1_cash0.txt` and `trend_overlay_out_run2_orderdep.txt`. Two readings changed with the fix: the entry
gate no longer adds return, and the index filter's drawdown protection on the 2021–2026 book is smaller than first shown.

## Part A: 2008–2026 (basket of 100; total · CAGR · Sharpe · max drawdown; then the drawdown inside each episode)

| Arm | Total | CAGR | Sharpe | mDD | 2008 | 2011 | 2013 | 2015 | 2018 | 2020 | 2022 | 2025 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| basket, no overlay | +497 % | 10.2 % | 0.50 | 51 % | −36 | −23 | −34 | −35 | −20 | −47 | −18 | −22 |
| index regime | +794 % | 12.7 % | 0.86 | 25 % | 0 | −22 | −20 | −8 | −9 | −13 | −18 | 0 |
| index regime, band | +399 % | 9.2 % | 0.60 | 35 % | 0 | −22 | −32 | −16 | −14 | −11 | −18 | 0 |
| name trend | +912 % | 13.4 % | 0.94 | 27 % | −7 | −18 | −25 | −10 | −15 | −5 | −14 | −12 |
| name momentum | +515 % | 10.4 % | 0.70 | 35 % | −16 | −21 | −35 | −17 | −15 | −15 | −18 | −13 |
| trailing stop 20 % | +623 % | 11.4 % | 0.71 | 41 % | −8 | −18 | −22 | −13 | −18 | −36 | −16 | −16 |
| IHSG, buy and hold | +174 % | 5.7 % | 0.29 | 56 % | −56 | −22 | −24 | −25 | −16 | −38 | −9 | −18 |
| IHSG with the index regime | +295 % | 7.8 % | 0.60 | 23 % | 0 | −21 | −16 | −8 | −12 | −7 | −9 | 0 |

The band version re-enters late and loses the rebounds. The per-name trend line is the highest, and the arm survivorship
flatters most. The trailing stop at monthly checks is too slow for a crash (−36 % in 2020).

## Part B: the strict book, 2021–2026 (total · Sharpe · max drawdown; 2025 Jan–Apr drawdown in brackets)

| Arm | May | Feb | Aug | Nov |
|---|---|---|---|---|
| strict, capped drift | +142 % · 1.00 · 22 % (−12) | +234 % · 1.41 · 21 % (−15) | +120 % · 0.95 · 19 % (−14) | +81 % · 0.81 · 22 % (−15) |
| index regime | +100 % · 0.94 · 22 % (0) | +120 % · 1.17 · 18 % (0) | +120 % · 1.14 · 15 % (0) | +73 % · 0.93 · 20 % (0) |
| index regime, band | +100 % · 0.94 · 18 % (0) | +137 % · 1.24 · 15 % (0) | +119 % · 1.09 · 15 % (0) | +74 % · 0.91 · 20 % (0) |
| name trend | +95 % · 1.11 · 11 % (−4) | +95 % · 1.06 · 17 % (−8) | +70 % · 0.88 · 16 % (−3) | +41 % · 0.68 · 14 % (−4) |
| trailing stop 20 % | +91 % · 1.02 · 13 % (−6) | +108 % · 1.13 · 18 % (−9) | +61 % · 0.76 · 18 % (−6) | +54 % · 0.80 · 16 % (−7) |
| entry only | +130 % · 1.14 · 15 % (−11) | +154 % · 1.29 · 18 % (−11) | +111 % · 1.02 · 20 % (−15) | +85 % · 0.99 · 16 % (−10) |

The book's 2022 drawdowns (−10 to −15 %) happened while the IHSG stayed above its average: the index filter cannot see a
book falling on its own, only a market falling. The 2025 April dip it avoided entirely.

## Criterion, mechanically, and the reading

| Overlay | (i) 2008 / 2020 cut | (ii) within 20 % | Result | Reading |
|---|---|---|---|---|
| index regime | +36 / +34 pts | 2 of 4 | not adopted | the only real crash insurance; costs 0–49 % in the calm window; blind to book-specific drawdowns |
| index regime, band | +36 / +36 pts | 2 of 4 | not adopted | no better than the plain filter |
| name trend | +29 / +42 pts | 0 of 4 | not adopted | lower book drawdowns in two calendars, but a third to two thirds of the return gone; survivor-flattered in Part A |
| name momentum | +20 / +32 pts | no B arm | not adopted | weakest protection |
| trailing stop | +28 / +11 pts | 0 of 4 | not adopted | −36 % in 2020; not a crash defence |
| entry only | no A arm; post hoc, no protection | 3 of 4 | offered as an option | drawdown a little lower (worst 20 % vs 22 %), return lower in three of four calendars |

## The window (research/idx_sma_window.py; 50, 100, 150, 200, 250 days)

Reading rule, declared before the run: 200 stays unless another window beats it in both parts on both counts.

| Window | Basket 2008–2026: total · mDD | Strict book, index filter: May / Feb / Aug / Nov total | worst mDD |
|---|---|---|---|
| 50 | +718 % · 37 % | +66 / +96 / +67 / +57 % | 31 % |
| 100 | +999 % · 29 % | +42 / +70 / +56 / +35 % | 29 % |
| 150 | +853 % · 34 % | +43 / +66 / +60 / +33 % | 26 % |
| **200** | **+794 % · 25 %** | **+100 / +120 / +120 / +73 %** | **22 %** |
| 250 | +507 % · 34 % | +99 / +119 / +124 / +69 % | 22 % |

100 days is the best line on the survivor basket and the worst on the real book, where the shorter windows whipsaw through
the sideways years and halve the return with deeper drawdowns. 200 and 250 behave alike in both parts; the rule is smooth
there. For the entry gate the window barely matters (May +110 to +137 %, Feb +154 to +179 %). **200 stays.**

## What this means for the book

1. **If the fear is a 2008 or 2020, the tool is the index regime filter**, 200-day, checked monthly, no band, idle cash in
   a deposit or SBN. Over eighteen years it halved the pain and ended far ahead. Over the last five it would have cost up
   to half the return in two calendars and nothing in a third. Both are true; the operator chooses which risk to carry.
2. **Per-name trend and stops are not the crash defence.** They trade every month per name, and on the real book they
   cost more than the index filter for protection that is only sometimes better.
3. **The entry gate is a mild damper, not a free lunch.** Expect slightly shallower drawdowns and somewhat less return.
4. Both are book-level options in the app (crash filter, entry gate), off by default; the paper book runs both from
   2026-09-13 so the mechanics are exercised. The catalog shows each option's record next to the choice.
