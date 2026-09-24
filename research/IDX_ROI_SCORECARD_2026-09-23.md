# IDX — ROI scorecard: every researched strategy, one table — 2026-09-23 (no new trials; cumulative N stays 603)

Written so the desk stops re-deriving these numbers in conversation. Every figure below is quoted from the study that
produced it (ledger id in the source column); nothing here is a new backtest. Stored as study `roi_scorecard` with the same
content in `summary`, so `idx study show --name roi_scorecard`, the MCP study tools and the nightly agent read the same thing.

## Ranked by backtest CAGR

| # | strategy | CAGR/yr | Sharpe | mDD | window | evidence | live | source |
|---|---|---|---|---|---|---|---|---|
| 1 | gap-fade, deployed config (-7 %, K=5, deepest, liq >= Rp 5 bn) | **~26 %** full span; **57 %** as #89 reports (recent regime); 16 % equal-weight K=10 (#77) | 5.71 / 3.86 | -8 % / -4 % | 2020-09 -> 2026-09, IDX opens (93 % of events in 2025-26) | BOUNDARY: t 2.99 vs 3.0, placebo pct 100, monotone in gap | `paper_gapfade` Rp 100 M, **0/20 sessions** | #77, #86, #87, #89 |
| 2 | trend `small` + regime gate | 32.1 % | 1.54 | -18 % | 2020-26 | rule ROBUST (fragile to 1-day-late fill); gate PARTIAL (drawdown cut real, return gain not) | `trend_live` Rp 10 M, **0/60 closed** | #62, #63, #66 |
| 3 | trend `small`, no gate | 29.5 % | 1.31 | -30 % | 2020-26 | ROBUST; fails the money rule on drawdown | - | #23, #62 |
| 4 | value 50 / trend 50, gated | 27.7 % | 1.54 | -15 % | 2020-05 -> 2026-09 | ROBUST (menu 21 B: 4/5 weights pass, 50/50 in 2/2 halves) | live split is 67/33: 25.7 % / 1.45 / -15 % | #93 (menu 32) |
| 5 | book 70 / gold 30 | 24.8 % | 1.65 | -16 % | 2020-05 -> 2026-09 | PARTIAL: Sharpe bar cleared, mDD 0.2 pt deeper; 2/2 halves | parked by the operator (equities only) | #92 (menu 31) |
| 6 | value strict composite, annual May | 21.8 % | 1.06 | -23 % | 2020-26, 7 rebalances | ROBUST: placebo pct 100, 6/6 neighbours, DSR 0.33 | **IPOT `live`, 6 names, NAV ~Rp 19 M - the only one with real fills** (book archived by mis-tap 09-18; un-archive pending) | #66 S1 |
| 7 | trend LIQ | 18.9 % | 0.92 | -36 % | 2020-26 | ROBUST; fails the money rule | - | #23 |
| 8 | trend `small`, 2005-2019 survivors | 13.4 % | 0.89 | -27 % | 15 yrs | the long-run base rate | - | #46 |
| 9 | EW3 IHSG / S&P / gold | 12.6 % (14.2 % w/ dividends) | 1.14 (1.27) | -28 % | **2006-2026** | ROBUST, 3/3 blocks, through 2008 | no book | menu 21 D |
| 10 | rupiah dual momentum (gem) | 11.2 % (12.7 %) | 0.93 (1.04) | -19 % | 2006-2026 | ROBUST | no book | menu 21 D |
| - | IHSG buy & hold | 8.4 % (2006-26) / 5.2 % (2020-26) | 0.53 / 0.41 | -55 % / -35 % | - | benchmark | - | - |

## The gap-fade number, reconciled (why 16, 26 and 57 are all in the ledger)

Same edge, same equity formula (daily return = mean event return x events/K, compounded), three differences:

| | #77 (16.3 %) | #89 (57 %) |
|---|---|---|
| weight per event | K = 10 -> 10 % of NAV | K = 5 -> 20 % of NAV (the deployed config) |
| events taken | every event past the threshold, averaged | the 5 deepest per day + liquidity >= Rp 5 bn -> mean +329 vs +300 bps |
| years divided by | first -> last event (~5.5 yrs) | the arm's own span - the reported 57 % implies ~2.8 yrs (unverified without re-running the script) |

Replicating the deployed rule's population: 591 events 2021-03-31 -> 2026-09-14, by year 2 / 4 / 11 / 25 / **186** / **363**.
#89's total +254 % over that full 5.46-yr span is **~26 %/yr**. Planning number: **26 %**. Recent-regime number: 57 %.
Conservative half-weight number: 16 %. Open item: confirm #89's `years` denominator and add a full-span CAGR row to its report.

## Overlays (add to a book; not a return stream)

| overlay | effect | evidence | source |
|---|---|---|---|
| sell at ARA (held name touches ARA) | holding through costs -227 bps (LIQ) .. -485 (all) vs the ARA price; P(hold beats ARA) 1 %; ~ +1..3 pp/yr on a 10-name book (frequency estimate) | t -12 / -42, 7/7 years, verdict SELL AT ARA | #101 |
| regime gate (no new trend entry while IHSG < MA200) | mDD -30 % -> -18 %; return gain not robust | PARTIAL | #62, #63 |
| dividend harvest | ~ +3 pp/yr, 3 names/day | weak | menu 27 |

## Closed (0 pass in their own menus)

ARA hunter (0/24, #56) · ML ARA predict (#59) · swing 2-5 d (46 trials) · bandarmologi (19) · sideways / range (15, #68) · base
breakout (Sharpe 0.7-0.9, #69) · sleepers (0/8) · day trading (-17 bps/day structural, #76) · maker / two-sided (0/10, #75) ·
per-name sizing, vol target, pyramid (10) · sector rotation (3) · averaging down (0/12, #91) · micro TP / LOB ML / run
exhaustion / edge sweep / maker cancel (#94-#100: 2-session prelims, candidates none or untested).

## How to read this table

1. The evidence column outranks the CAGR column. Row 1 has the highest ROI and zero live record; row 6 has a middling ROI and
   the only real fills. Everything but row 6 is a backtest.
2. Windows are not comparable. Rows 1-7 are 2020-26 - the desk's own scorecard calls it the best block in 22 years - and every
   sleeve weakened in 2023-26 (value Sharpe 1.23 -> 0.90). Rows 8-10 are 15-20 years and include 2008.
3. The portfolio to hold is the blend (row 4), not the winner: either sleeve alone loses to any blend in every window. Gap-fade,
   if it survives 20 paper sessions, joins as a third sleeve that never holds overnight - not as a replacement.
