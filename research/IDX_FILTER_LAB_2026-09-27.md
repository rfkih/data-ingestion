# IDX menu FL-2 — filter lab on the C0 radar wide sleeve — 2026-09-27 — study #407

Operator request: *"analisa filter apa yang bisa memfilter saham2 itu, benar2 cari tau supaya meningkatkan profitabilitas"*.
Harness `research/idx_filter_lab.py`; workflow `idx-radar-filter-lab` (9 finder agents, 51 adversarial verifier agents, 1 holdout agent).

**Result: 2 of 6 holdout tests PASS, and both are the same effect: a liquidity (crowding) cap. Skip C0 flags whose 20-day average
traded value is at least Rp 50-60 bn/day.** Everything else failed. That includes the price-path rules that looked best on
train, and they reversed out of sample.
Trials: cumulative N **1,097 -> 1,103** (6 holdout tests). 1,454 train-only expressions were explored with the holdout closed.

| funnel | count |
|---|---|
| feature families searched (train only) | 9 |
| train-only expressions evaluated | 1,454 (plus about 10k internal greedy splits and 858/900-cell permutation grids) |
| candidates proposed | 17 |
| adversarial verdicts (3 lenses x 17) | 51, of which 26 refuted (leakage 0/17, overfit 15/17 incl. 2 fatal, economics 11/17) |
| survivors (at most 1 refutation, none fatal) | 6 |
| holdout tests (run once, no tuning) | 6 + 1 base run; `holdout_log.jsonl` has exactly 7 lines |
| PASS (pre-registered) | **2**: `value20_bn < 50`, `value20_bn < 60`. One finding. |

---

## 1. Design

**Base trades.** Every C0 flag is taken: close >= 1.3 x close 60 sessions ago, at the 250-day high, day return < 18 %. The flag
must be in U1: 20-day value >= Rp 1 bn, close >= Rp 50, board point-in-time on the day. One position per name. Entry at the close
after the flag, with no fill on a >= 18 % day. Exit at the close after the first close <= 85 % of entry (stop) or <= 75 % of the
peak (trail). This is RB-2's wide sleeve (#405). Every feature is read at flag-day index i = e - 1. No ARA lock/touch features
(ARA scope frozen). `board_now`/`sector` are current attributes and were flagged as leakage-prone; no candidate uses them.

**Split, fixed before any search.**

| split | entries | trades | base mean / median net | touch2x / stop | base book Sharpe / CAGR / mDD |
|---|---|---|---|---|---|
| TRAIN | 2021-01-04 .. 2023-12-29 | 622 | +14.3 % / -13.1 % | 25.7 % / 51.1 % | 1.74 / 18.0 % / -10.5 % |
| HOLDOUT | 2024-01-02 .. 2026-09 | 663 | +18.8 % / -10.8 % | 25.0 % / 45.7 % | 1.80 / 20.4 % / -20.2 % |

The holdout parquet sits in a separate folder. `eval --split holdout` requires `FILTERLAB_HOLDOUT=1` and appends every call to
`holdout_log.jsonl`. Finders and verifiers were told never to open it, and the log shows only the 7 locked calls.

**Harness (`eval --split train --expr ...`).** It prints kept/dropped trade stats (mean, median, hit, touch2x, stop), the Welch t
of kept vs dropped mean net, a per-year split, and an **exposure-matched rupiah book**. The book runs on Rp 20 m. The base uses
1.25 % per position and <= 40 open. The filtered book uses 1.25 % x n_base / n_kept (capped at 5 %), with exposure <= 50 %. Lots
of 100, fills at offer/bid, fees 0.10 / 0.20 %, no sale on a <= -6.5 % day without a bid. Matching exposure stops a filter from
looking better only because it trades less. The side effect is that a filter keeping fewer trades gets bigger positions and a
more concentrated book, so its mDD gets worse mechanically (see section 5).

**Discover.** One finder agent per family: price_path, vol_liquidity, size_age, flows, regime_crowding, fundamentals, events,
sector_commodity, multivariate. Each worked on train only, counted every expression, and returned at most 3 simple,
economically motivated rules keeping >= 150 trades, with per-year and neighbour-threshold results.

**Verify.** Three independent skeptics per candidate, instructed to refute when in doubt:
- *leakage / point-in-time*: rebuild the columns from source and check for future data, current attributes, revisions and
  survivorship.
- *overfit / robustness*: re-run the harness at >= 4 neighbouring thresholds, check each train year, and recompute without the
  top-5 kept trades.
- *exposure / economics*: check the gain is not exposure-mechanical, kept mean > 0.143, kept median vs -0.131, no right-tail cut
  (touch2x), and a plausible IDX mechanism.

Survival rule: at most 1 refutation and no fatal verdict.

**Holdout.** One agent ran each survivor exactly once plus the unfiltered base, with no variants. It computed the one-sided p of
Welch t (kept > dropped) from `t.sf(t, df = min(n_kept, n_dropped) - 1)` and Holm-adjusted it across the 6.
**Pre-registered PASS:** `holm_p < 0.05` AND filtered book Sharpe > base Sharpe AND filtered mDD >= base mDD - 5 pp.

**Multiple-testing context.**
- Cumulative desk trials before this study: 1,097. This study adds 6 holdout tests, giving 1,103.
- The 1,454 train-only expressions are not counted as trials because the holdout stayed closed while they ran. They do mean every
  train t-value below is selection-biased. The two price-path candidates that reversed on holdout show that bias.
- Holm over this study's 6 tests is the pre-registered control. Under a much stricter Bonferroni over all 1,103 cumulative trials
  (p < 4.5e-5), neither liquidity cap would clear (one-sided p 1.0e-4 and 4.7e-4). They are confirmed out-of-sample effects on
  about 100-117 dropped trades, not certainties.

---

## 2. Search by family

| family | expr. tried | cand. | survived | holdout PASS | what the family found |
|---|---|---|---|---|---|
| price_path | 116 | 2 | 2 | 0 | Prior 12-1 momentum (`r250 > r60`) looked strong on robust train stats (MW p 0.0004-0.003). Over-extension, `close_loc`, `up20` and streaks were unstable or all-tail. **Reversed on holdout.** |
| vol_liquidity | 80 | 2 | 1 | **1** | One real, stable effect: the liquidity cap `value20_bn < 60`. vol_ratio, tick, spread, book_imb, price, attn, freq_ratio and vol caps were flat, non-monotone or TFAS-driven. |
| size_age | 95 | 3 | 1 | 0 | The harness `age` column is a calendar proxy (sessions since 2020-01-02). mcap and price level are capacity artefacts. Turnover/mcap rules are the liquidity effect rescaled. Listing age depends on 2 rockets. |
| flows | 80 | 3 | 0 | – | Foreign flow only matters crossed with attention, and the best of 858 grid cells sits at the permutation median (search-adjusted p about 0.45). book_imb shows nothing. |
| regime_crowding | 233 | 1 | 0 | – | Market-wide features give only a few dozen regime episodes. The mania-day veto is January 2021. ihsg_r60 < 0.02 improves the median but loses the tail (book Sharpe 0.66-1.01). |
| fundamentals | 39 | 2 | 1 | 0 | Only the sign of YTD profit. Earnings growth, valuation and profit size are null (FL-1 confirmed again). |
| events | 50 | 0 | – | – | **Untestable.** `idx.event` starts on 2023-07-03, so the counters are structural zeros before that. The query+rights veto sits at the 44th-76th percentile of placebo drops. |
| sector_commodity | 245 | 2 | 0 | – | Brent/CPO-downtrend veto: 4-8 episodes, 1-day look-ahead in the harness, gain from 2023 only. Raw `sector` mixes JASICA/IDX-IC codes (survivorship artefact). |
| multivariate | 516 | 2 | 1 | **1** | Out-of-sample Spearman of LightGBM/ridge is 0.07-0.14 (negative in the 2022 leave-one-year-out fold). The distilled first split is `value20_bn < 50`, found independently of vol_liquidity. |
| **total** | **1,454** | **17** | **6** | **2** | |

---

## 3. Every candidate: train numbers

Base: n 622, mean +14.3 %, book Sharpe 1.74, CAGR 18.0 %, mDD -10.5 %. "Book" is the harness exposure-matched book.

| # | family | candidate | expression | kept n | kept mean | dropped mean | Welch t | book Sh | book mDD | per-year consistent | survives |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | price_path | prior_uptrend | `r250 > r60` | 327 | +22.0 % | +5.8 % | 1.92 | 2.21 | -9.3 % | yes | **yes** |
| 2 | price_path | prior_uptrend_not_stretched | `r250 > r60 and r20 < 0.8` | 266 | +25.1 % | +6.3 % | 1.98 | 2.43 | -8.7 % | yes | **yes** |
| 3 | vol_liquidity | liquidity_cap_60bn | `value20_bn < 60` | 531 | +17.9 % | -6.7 % | 4.57 | 1.94 | -12.1 % | yes | **yes** |
| 4 | vol_liquidity | liquidity_cap_plus_vol20_cap | `value20_bn < 60 and vol20 <= 0.10` | 451 | +21.3 % | -4.2 % | 4.14 | 1.83 | -14.8 % | no | no |
| 5 | size_age | low_turnover_5x | `value20_bn < 5 * mcap_tn` | 364 | +20.3 % | +5.9 % | 1.82 | 2.21 | -14.0 % | yes | **yes** |
| 6 | size_age | churn_veto_10x | `value20_bn < 10 * mcap_tn` | 471 | +18.2 % | +2.2 % | 2.39 | 1.95 | -10.1 % | no | no |
| 7 | size_age | young_listing_8y (new column) | `list_age_y < 8` | 227 | +27.2 % | +6.9 % | 1.87 | 2.15 | -19.3 % | yes | no |
| 8 | regime_crowding | mania_day_veto | `flags_today <= 15` | 542 | +16.2 % | +1.2 % | 1.92 | 2.13 | -10.8 % | no | no |
| 9 | flows | A: hot names foreigners sell | `not (attn20 > 3 and fnet20 < -0.005)` | 530 | +16.6 % | +1.0 % | 2.11 | 2.06 | -10.8 % | yes | no |
| 10 | flows | B: quiet names, heavy foreign buying | `not (attn20 < 2.3 and fnet5 > 0.1)` | 578 | +15.9 % | -6.0 % | 3.74 | 1.62 | -11.1 % | yes | no |
| 11 | flows | A+B | both vetoes | 486 | +18.7 % | -1.3 % | 2.99 | 2.15 | -12.9 % | yes | no |
| 12 | sector_commodity | oil_tape_veto | `brent_r60 > -0.02 or brent_r60 != brent_r60` | 493 | +19.0 % | -3.8 % | 3.63 | 2.07 | -9.5 % | yes | no |
| 13 | sector_commodity | commodity_tape_veto_brent_cpo | `(brent_r60 + cpo_r60) > 0 or NaN` | 472 | +19.4 % | -1.8 % | 3.29 | 2.02 | -10.1 % | yes | no |
| 14 | fundamentals | loss-maker veto | `loss == 0` | 472 | +17.4 % | +4.7 % | 1.73 | 1.99 | -14.4 % | yes | no |
| 15 | fundamentals | loss-maker veto, breakeven tol. | `ep_ytd > -0.01` | 509 | +16.3 % | +5.2 % | 1.43 | 2.04 | -11.1 % | yes | **yes** |
| 16 | multivariate | liquidity_cap | `value20_bn < 50` | 516 | +18.3 % | -5.4 % | 4.23 | 2.05 | -12.3 % | yes | **yes** |
| 17 | multivariate | liquidity_cap + profitable | `value20_bn < 50 and loss == 0` | 389 | +21.9 % | +1.7 % | 2.73 | 2.17 | -15.8 % | yes | no |

Neighbour behaviour (from the finders; the verifiers reproduced all numbers exactly):
- **#3/#16:** plateau from 40 to 150 bn, with t 4.1-4.9 and book Sharpe 1.93-2.08. The cliff below about 35 bn is one trade
  (MSIN +673 %, value20 37.7 bn).
- **#1:** book Sharpe 1.81-2.21 for c in 0.9-1.05, but 1.33-1.56 at c >= 1.1 (TFAS sits at ratio 1.06).
- **#5:** trade-level plateau from 3x to 10x, but the book peaks locally at 5x (6x gives 1.75).
- **#8:** book below base at <= 12 and <= 13 (TFAS was on a 14-flag day).
- **#12:** Sharpe 1.86-2.07 over -0.05..0, but mDD is unstable.
- **#15:** Sharpe above base over ep -0.02..+0.01.

---

## 4. Every candidate: the three verdicts

Format: **REFUTED** or ok (severity), followed by a one-line reason.

| # | candidate | leakage / PIT | overfit / robustness | exposure / economics |
|---|---|---|---|---|
| 1 | prior_uptrend | ok (minor). r20/r60/r250 rebuilt exactly from adjusted closes, and the corporate actions pre-date the flags. 58 of 67 NaN-r250 rows are a panel-start artefact (Jan 2021); filling them keeps the effect (t 1.99, Sh 2.25). Must be computed on adjusted prices. | **REFUTED (serious).** The book edge is the NaN/young-listing drop (`r250 == r250` alone gives Sh 2.07) plus TFAS. Without TFAS it sits at the 64th percentile of random subsets. c = 1.1 is already below base, 2022 is null and the response is non-monotone. | ok (minor). Not exposure-driven (avg exposure 0.470 vs 0.453). MW p 0.003, log t 2.65, month-clustered t 3.34. Stage-2 mechanism. Without TFAS the book is 1.49 vs 1.48. |
| 2 | prior_uptrend_not_stretched | ok (minor). Same PIT check; the NaN-filled version keeps 283 trades at Sh 2.36. On raw closes t falls to 1.07 because PANI and MSIN switch sides. | **REFUTED (serious).** The top 5 kept trades are 64 % of kept net; without them the gap is +0.030 (t 0.62) and 2021 flips. Book below base at ratio 1.2 (1.52) and at +0.2 (1.35). The r20 veto adds only MW p 0.068. | ok (minor). MW p 0.0004, log t 2.92, beats every random 266-subset. But the r20 < 0.8 leg is unsupported (regression t 0.83), and the 2.43 headline rests on TFAS getting a slot. |
| 3 | liquidity_cap_60bn | ok (minor). value20 is raw close x raw volume (split-invariant) and was recomputed exactly from `idx.bar`, MSIN included. Delisted names are present. | ok (minor). t 4.2-4.9 for every cap from 40 to 120; without the top 5, t 4.98; the month bootstrap is never <= 0. Right direction in all 3 years. Weak spots: 59 of 91 drops in 2021, medians barely differ, mDD only flat at base sizing. | ok (minor). Capacity-free Rp 5 bn book: Sh 2.40 vs 2.00, above all random subsets. touch2x 29 % vs 6.6 %, and 0 of 91 dropped trades exceed +100 %. Holds within terciles of vol20/mcap/price/r60/attn20. Month-clustered t 4.07. |
| 4 | liquidity_cap_plus_vol20_cap | ok (minor). Both features rebuilt from `daily_summary`; 0 trades reclassified. | **REFUTED (fatal).** The simpler #3 beats it (Sh 1.94 vs 1.83). mDD is -14.8 % and worse than base at every vol20 cut. 2022/2023 reverse after trimming. | **REFUTED (serious).** The vol20 leg drops names that touch 2x more often (33.8 % vs 28.2 %), which is tail-cutting. The problem is the fixed exit, not the entry. |
| 5 | low_turnover_5x | ok (none). mcap_tn is PIT (listed_shares steps exactly on split dates), value20 is raw, no NaN. | ok (serious). The trade-level plateau from 3x to 10x is real, but the book's 2.21 is a local peak (6x gives 1.75). mDD is worse than base from 3.5x to 6.5x. 2022 is null at every threshold. | ok (minor). At truly matched exposure (1.7 %/position): Sh 2.17, mDD -10.3 %. Not tail-cutting: touch2x 25.3 vs 26.4 %, with bigger winners. Lee-Swaminathan turnover life-cycle. |
| 6 | churn_veto_10x | ok (none). Same columns as #5. | **REFUTED (fatal).** The typical trade is identical (median -0.131 vs -0.135, touch2x 0.259 vs 0.252). Capped-net t 1.29. With the top 3 removed from both books it is 0.76 vs 1.05. 2022 is reversed from 7x to 12x. | **REFUTED (serious).** Removing TFAS alone brings the kept mean to the base mean; without the top 5, t 1.32. The book gain is 1.32x upsizing of 2021 rockets. |
| 7 | young_listing_8y | ok (minor). `listing_date` is the fixed IPO date and spot checks are correct. The 3 missing names are genuinely old listings. | **REFUTED (serious).** Without the top 5, the kept mean is 0.082 vs 0.069 (t 0.28). With TFAS and DMMX removed, the book is worse than base (1.26 vs 1.35, mDD -18.7 vs -9.6 %). | **REFUTED (serious).** The typical trade is not better (MW p 0.26). The gain is 2 Jan-2021 rockets held at 2.75x size; a null forced to include them puts it at the 87th percentile. |
| 8 | mania_day_veto | ok (minor). `flags_today` comes from the c0 panel at day i with a PIT board. | **REFUTED (serious).** At <= 12/13 the book is below base (TFAS moves sides). 64 of 80 vetoes fall on 5-18 Jan 2021, and it never fires in 2023. Without the top 5, t 0.97. | **REFUTED (serious).** The vetoed trades made only -Rp 0.07 m in the base book. The gain is a 14 % bigger TFAS position plus freed slots. Clustered t -1.05 to -1.57, and mDD is worse in every variant. |
| 9 | flows A | ok (none). fnet20 rebuilt from `daily_summary` (622/622 match); attn20 is trailing. | **REFUTED (serious).** The cut sits around the 3 biggest winners (TFAS fnet20 -0.0004, MPPA, KAYU); at -0.0001 it reverses (t -0.20, Sh 1.62). Without the top 5, t 1.13. attn20 > 2.2 gives Sh 1.56. | **REFUTED (serious).** t 1.86 without TFAS, month-clustered 1.71, 1.01 excluding 2021H1. Random drops among hot names reach its Sharpe 10-12 % of the time. |
| 10 | flows B | ok (none). fnet5 is lag-0 exact; lags of ±1/±2 match only 7-10 %. | **REFUTED (serious).** The book is worse than base (Sh 1.62, CAGR 17.1 %, mDD -11.1 %). MW p 0.43; all right tail (none of the 44 > +100 %, which random chance gives with p 0.08). | **REFUTED (serious).** Below the random-drop median at Rp 20 m, 200 m and 2 bn. Largely a large-cap size effect. |
| 11 | flows A+B | ok (none). All three columns strictly backward-looking. | **REFUTED (serious).** Max-t permutation over a 900-cell grid gives adjusted p 0.27. Neighbours fall to 1.64-1.72, and mDD is -12.9 %. | **REFUTED (serious).** Leg B has no support of its own (MW p 0.43, lowers the book), and the drawdown goal fails at harness sizing. |
| 12 | oil_tape_veto | ok (minor). Real 1-day look-ahead: FRED Brent settles about 01:30 WIB on D+1. Lag 1-5 rebuilds keep Sh 1.87-2.12, t 2.8-4.0. | **REFUTED (serious).** The expression as written uses look-ahead. With lag 1, the whole book gain comes from 2023 (2021 3.03 -> 3.02, 2022 0.39 -> 0.37). | **REFUTED (serious).** About 4 Brent-downtrend episodes, not 129 independent trades. Within-month t -1.4. The 2023 edge is PANI alone. MW p 0.079. |
| 13 | commodity_tape_veto_brent_cpo | ok (minor). Same look-ahead plus a NaN artefact from pivot -> reindex(ffill); proper release lags keep the effect. | **REFUTED (serious).** Gain in 2023 only (per-year book 0.05 -> 1.63). 2022 falls to 0.37-0.48 in the lagged versions. | **REFUTED (serious).** The t compares years: with year FE, t 1.14 iid and 1.93 clustered. The 2023 edge is PANI. The export-name mechanism does not carry it. |
| 14 | loss-maker veto `loss == 0` | ok (minor). Reports count only if published before 07:00 WIB on the flag day; recompute matches 100 %. | **REFUTED (serious).** The top 5 kept trades are 47.6 of 81.9 kept net; without them t 0.49. The book gain is capacity reshuffling (MSIN and ASSA got slots). The vetoed trades were net positive in the base book. | **REFUTED (serious).** t 1.73; clustered 1.63-1.72; controls + month FE 1.28. The ep buckets contradict the mechanism (ep <= -0.2 is the best bucket, +46 %). mDD -14.4 %. |
| 15 | loss-maker veto `ep_ytd > -0.01` | ok (minor). PIT profit and PIT mcap; the announcement timestamps lead File_Modified (conservative). | **REFUTED (serious).** The top 5 are 57 % of kept net; without them the gap is +0.018 (t 0.29). The book without the top 5 is 0.73 vs 0.67 with worse mDD. 2021 reverses without the outliers. | ok (minor). Book without upsizing: Sh 2.07 / CAGR 21.2 % / mDD -9.5 %. Random-drop p 0.028. Smooth plateau. Drops 2x-touchers only in proportion. |
| 16 | liquidity_cap `value20_bn < 50` | ok (minor). Raw exchange close x volume; no survivorship; the dropped losses are real limit-down strings. | **REFUTED (serious).** The H2 (2022-07..2023-12) hold-up is carried by about 5 trades (without the top 5, t 0.90). Only 2021 survives trimming. mDD is worse than base at every threshold under matched sizing. | ok (minor). Equal-sizing book Sh 2.22 vs 1.74 (p 0.002 vs quarter-matched random drops). A book of only the dropped trades loses money. touch2x 28.7 vs 11.3 %. t 4.1 with controls. |
| 17 | liquidity_cap + profitable | ok (minor). Lagging the earnings information by N days does not decay the edge. | **REFUTED (serious).** The loss leg rests on 5 trades (gap 0.145 -> 0.024 without them) and peaks narrowly at ep = 0. Combined t 2.73 is below the cap alone (4.23). | **REFUTED (serious).** Incremental t 1.24-1.63, bootstrap P 0.93. At equal sizing it is slightly worse than the cap alone (Sh 2.195 vs 2.219). |

Events family: no candidate. The data exists only from 2023-07-03 (69 covered train trades), so it cannot be tested on train.

---

## 5. Holdout (entries 2024-01-02 .. 2026-09, 663 trades; run once)

Base: mean +18.8 %, median -10.8 %, touch2x 25.0 %, stop 45.7 %; book Sharpe 1.80, CAGR 20.4 %, mDD -20.2 %.
PASS = Holm p < 0.05 AND Sharpe > 1.80 AND mDD >= -25.2 %.

| # | filter | expression | kept / dropped n | kept mean | dropped mean | Welch t | one-sided p | Holm p | book Sh | CAGR | mDD | PASS |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 16 | liquidity_cap | `value20_bn < 50` | 546 / 117 | +22.8 % | +0.3 % | **3.84** | 0.0001 | **0.0006** | **2.01** | 25.1 % | -19.4 % | **PASS** |
| 3 | liquidity_cap_60bn | `value20_bn < 60` | 563 / 100 | +22.0 % | +1.0 % | **3.41** | 0.0005 | **0.0023** | **2.09** | 26.3 % | -19.7 % | **PASS** |
| 5 | low_turnover_5x | `value20_bn < 5 * mcap_tn` | 361 / 302 | +23.8 % | +12.9 % | 1.47 | 0.072 | 0.288 | 1.51 | 15.8 % | -20.4 % | fail |
| 15 | loss-maker veto (tol.) | `ep_ytd > -0.01` | 557 / 106 | +19.3 % | +16.1 % | 0.28 | 0.389 | 1.00 | 2.04 | 24.0 % | -19.3 % | fail |
| 2 | prior_uptrend_not_stretched | `r250 > r60 and r20 < 0.8` | 293 / 370 | +16.3 % | +20.8 % | -0.62 | 0.732 | 1.00 | 1.42 | 16.5 % | -23.6 % | fail |
| 1 | prior_uptrend | `r250 > r60` | 356 / 307 | +15.8 % | +22.3 % | -0.83 | 0.797 | 1.00 | 1.11 | 12.2 % | -24.8 % | fail |

Holdout detail on the typical trade and the tail (kept vs dropped):

| filter | median | touch2x | hit | stop | by year, kept vs dropped mean (2024 / 2025 / 2026) |
|---|---|---|---|---|---|
| `value20_bn < 50` | -9.7 / -11.9 % | 26.7 / 17.1 % | 37.5 / 26.5 % | 45.8 / 45.3 % | +22.1 vs -9.9 / +35.5 vs +11.8 / -6.6 vs -11.9 |
| `value20_bn < 60` | -9.9 / -11.7 % | 26.5 / 17.0 % | 37.5 / 25.0 % | 45.8 / 45.0 % | +21.1 vs -8.6 / +34.4 vs +13.4 / -6.9 vs -11.6 |
| `value20_bn < 5 * mcap_tn` | -9.9 / -12.0 % | 23.3 / 27.2 % | – | – | +16.3 vs +21.9 / +43.6 vs +19.0 / -8.5 vs -7.3 |
| `ep_ytd > -0.01` | -10.2 / -12.8 % | 23.9 / **31.1** % | – | – | 2024 reversed (+16.5 vs +27.0) |
| `r250 > r60 and r20 < 0.8` | **-6.8 / -12.8 %** | 23.5 / 26.2 % | 39.9 / 32.2 % | – | reversed overall |
| `r250 > r60` | **-8.9 / -12.4 %** | 21.9 / **28.7** % | – | 43.8 / 47.9 % | reversed overall |

Train -> holdout, side by side:

| filter | Welch t train -> holdout | book Sharpe vs base, train -> holdout | mDD vs base, train -> holdout |
|---|---|---|---|
| `value20_bn < 50` | 4.23 -> 3.84 | 2.05 vs 1.74 -> 2.01 vs 1.80 | -12.3 vs -10.5 -> -19.4 vs -20.2 |
| `value20_bn < 60` | 4.57 -> 3.41 | 1.94 vs 1.74 -> 2.09 vs 1.80 | -12.1 vs -10.5 -> -19.7 vs -20.2 |
| `value20_bn < 5 * mcap_tn` | 1.82 -> 1.47 | 2.21 -> 1.51 | -14.0 -> -20.4 |
| `ep_ytd > -0.01` | 1.43 -> 0.28 | 2.04 -> 2.04 | -11.1 -> -19.3 |
| `r250 > r60 and r20 < 0.8` | 1.98 -> -0.62 | 2.43 -> 1.42 | -8.7 -> -23.6 |
| `r250 > r60` | 1.92 -> -0.83 | 2.21 -> 1.11 | -9.3 -> -24.8 |

The nominal cap bites at about the same rate in both periods: `< 60` drops 14.6 % of train flags and 15.1 % of holdout flags;
`< 50` drops 17.0 % and 17.6 %. The threshold has not yet drifted in real terms.

**PASS: `value20_bn < 50` and `value20_bn < 60`. This is one confirmed effect, not two.**

---

## 6. Honest reading

**What separates winners from losers on IDX C0 momentum flags.** One thing: **how crowded the name already is, measured as
rupiah traded per day.**
- The sleeve earns only from convexity. On train the top 10 trades are 75 % of net and the median trade is -13 %.
- Names already trading >= Rp 50-60 bn/day are either large caps (BBRI, ASII, BBNI, ADRO, ANTM, INCO, MDKA, UNTR...) or
  crowded theme spikes (BUMN-karya in January 2021, digital banks in August 2021, coal). A 250-day-high breakout there is late
  and widely arbitraged, and it almost never re-rates 2x.
  - Train: 0 of 91 dropped trades exceeded +100 %, and touch2x was 6.6 % vs 29 %.
  - Holdout: touch2x 17 % vs 27 %, and the dropped mean was about +0-1 % per trade.
- The cap removes a group with no upside. It does not improve the median much (holdout -9.9 vs -11.7 %), and stop rates are
  equal. It works on the tail, and the tail is where this sleeve's money is.
- It is turnover, not size. Dropping the top 91 by mcap does nothing (t 0.05), and an mcap cap fails (Sh 1.37).
- Scaling turnover by mcap (#5) added nothing and failed the holdout.
- The effect was found independently by two families (the vol_liquidity scan and the multivariate model's first split), with a
  third (size_age turnover) pointing at it. It was the only candidate that no lens refuted (#3), and it held in every holdout
  year.

**What does not separate them (despite looking good on train).**
1. **Price path / prior 12-1 momentum reversed out of sample.**
   - The holdout kept the better median and hit rate (median -8.9 vs -12.4 %, hit 39.9 vs 32.2 % for #2) but moved the rockets
     to the dropped side (touch2x 21.9 vs 28.7 %).
   - On a convex sleeve, a filter that raises the median while losing the tail makes the book worse (Sharpe 1.11 and 1.42 vs 1.80).
   - Lesson: **rank and median tests (MW p 0.0004 on train) are not a proxy for P&L here.** The overfit lens was right that the
     book edge was TFAS plus a data-start artefact. The economics lens was wrong to pass it.
2. **Fundamentals.** The loss-maker veto failed at trade level for the third time: FL-1 t 0.67, here holdout t 0.28, and menu 35 on the trend sleeve
   found the opposite sign. Loss-makers doubled more often in the holdout (31 % vs 24 %). Its better book (2.04) is capacity and
   sizing noise. Earnings growth is null again. This fits FL-1's reading that speculative attention is the fuel.
3. **Foreign flow x attention and closing-book imbalance.** Nothing survives a search-adjusted permutation (p about 0.45 over
   the full grid). Flow only "works" in cells cut around individual winners.
4. **Market regime and crowding days, and the commodity tape.** These are period selectors with 4-8 effective episodes. The
   mania veto is two weeks of January 2021. The Brent/CPO veto is 2023-only once its 1-day look-ahead is removed.
5. **Size, price level, listing age, prior flags, vol caps.** These are either capacity artefacts of the 40-slot/Rp 20 m book or
   one or two rockets (TFAS +1840 %, DMMX +855 %) held at larger size.
6. **Events.** Not testable: `idx.event` starts on 2023-07-03.
7. **ML.** Out-of-sample Spearman is 0.07-0.14 and negative in one fold. The one-line liquidity rule does as well as the model.
   This agrees with the desk's rule that construction, not accuracy, is where the edge is.

**Why most train "wins" were noise.**
- The exposure-matched book swings about ±0.3 Sharpe depending on which of about 10 rockets get a slot.
- Random subsets of the same size score below base on Sharpe: 170 kept gives 1.0 ± 0.5, 375 gives 1.4 ± 0.4, 480 gives
  1.5 ± 0.35.
- Upsizing mechanically worsens mDD for any filter keeping fewer than about 450 trades.
- Welch t on a net distribution with max +1840 % is miscalibrated. Ex-top-k, winsorised, log, clustered and placebo checks were
  what separated real from lucky.

---

## 7. What the desk should do

1. **Adopt one liquidity cap on the C0 wide sleeve: skip a C0 flag when its 20-day average traded value is >= Rp 60 bn**
   (`value20_bn < 60`).
   - Pick one; 50 bn is equally valid and had the stronger holdout t.
   - Why 60: no lens refuted it on train, it has the best holdout book (Sharpe 2.09 vs 1.80, CAGR 26.3 vs 20.4 %, mDD -19.7 vs
     -20.2 %), and it sits in the middle of the 45-120 bn plateau, away from the one-trade cliff below 40 bn.
   - **Implement it as a skip, with no upsizing.** Keep 1.25 % per position and 40 slots. Train showed that skip-only keeps
     drawdown flat (-10.4 vs -10.5 %), while exposure-matched upsizing worsens it.
   - Do not add capital to the sleeve on the back of this. That needs a live track record first.
2. **Expect a smaller live gain than the book shows.** At Rp 20 m and 1.25 % (about Rp 250 k per position), names priced above
   about Rp 2,500 are already unaffordable, and many of the dropped large caps are among them.
3. **The cap does not rescue bad years.** 2026 is a losing year for the sleeve under every filter: base -7.9 %, capped kept
   trades -6.9 %.
4. **Monitor the nominal threshold.** Check each quarter that it still drops about 15 % of flags (14.6 % train, 15.1 % holdout).
   If it drifts outside roughly 10-20 %, a cross-sectional percentile version is the natural fix. That version is a new
   hypothesis and needs its own pre-registered test; do not swap it in untested.
5. **Do not adopt:** prior-uptrend/over-extension, turnover/mcap, the loss-maker veto, flow x attention, the mania veto,
   commodity-tape vetoes, event vetoes, listing age, vol caps.
6. **Harness and data fixes found along the way:**
   - (a) The harness `age` is sessions since 2020-01-02, a calendar proxy. Add `list_age_y` from `idx.listing.listing_date` if
     age matters again.
   - (b) Brent, CPO and gold are read at the flag day's obs_date, which is a 1-day look-ahead. Use the `MACRO_RELEASE`
     next-day lag from `idx/ml/daily.py`. Pivot -> reindex(ffill) also leaves NaNs (27-38 trades).
   - (c) `ev_*` counters are structural zeros before 2023-07-03. **This also contaminates the ML desk**, since `idx/ml/daily.py`
     reads the same columns. Set them to NaN before 2023-07-03 or backfill `idx.event`.
   - (d) `r250` is NaN for flags in January 2021 because the panel starts on 2020-01-02.
7. **Lead, not a result:** several verifiers found that high-vol names touch 2x but get shaken out by the fixed -15 % stop /
   25 % trail. A vol-scaled exit is a separate, untested hypothesis for a future pre-registered menu.

---

## Files

- Harness: `research/idx_filter_lab.py`. Train data: `research-scratch/idx/filterlab/trades_train.parquet`.
- Finder and verifier scripts: `research-scratch/idx/filterlab/agents/` (per-family folders `price_path/`, `vol_liquidity/`,
  `size_age/`, `fund/`, `regime_crowding/`, `sector_commodity/`, `multivariate/`; `flows_*`, `ev_*`, `verify_*`, `verif_*`).
- Holdout runs: `research-scratch/idx/filterlab/agents/holdout_run/` (base.json, c1-c6.json); log
  `research-scratch/idx/filterlab/holdout/holdout_log.jsonl` (7 lines).
- Related: `IDX_C0_WIDE_2026-09-27.md` (#405, the sleeve), `IDX_C0_FILTER_2026-09-27.md` (#406, FL-1).
