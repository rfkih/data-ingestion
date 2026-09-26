# IDX menu 39 (Track B4) - corporate-action events, long-only - 2026-09-25 - 7 trials, cumulative N = 890

Script `research/idx_corp_actions.py` (pre-registration in its docstring). Signal = the IDX disclosure's publication (announcements exist from 2023-07-03) or the ex-date (corporate_action, 2020 ->); fill at the close of the first session whose open follows the publication (closing offer + 0.10 %), exit at the closing bid - 0.20 %; returns on close x adj_factor (split/rights adjusted, no dividends). LIQ floor at the signal day: 60-session mean value >= Rp 5 bn, close >= Rp 100. Controls = 5 LIQ names nearest in value; placebo = 500 same-code random-date draws.

## Events

| family | all disclosures / ex-dates (deduped) | by year |
|---|---|---|
| split_ann | 35 | 2023:9 2024:16 2025:4 2026:6 |
| rights_ann | 146 | 2023:28 2024:31 2025:36 2026:51 |
| buyback_ann | 244 | 2023:3 2024:43 2025:112 2026:86 |
| tender_ann | 147 | 2023:16 2024:37 2025:53 2026:41 |
| split_ex | 67 | 2020:5 2021:10 2022:12 2023:13 2024:16 2025:6 2026:5 |
| rights_ex | 125 | 2020:8 2021:33 2022:27 2023:14 2024:15 2025:14 2026:14 |
| reverse | 4 | 2020:2 2022:1 2024:1 |

## Pre-registered trials

| trial | n LIQ (Rp 1 bn) | net mean / median | t net | hit | gross | cost | matched excess (t) | mkt-adj (t) | placebo pct (p05/med/p95) | years | cost x1.5 | delay 1 | neighbours | sleeve 5 %/event CAGR / Sharpe / mDD | DSR | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| split_ann_20 | 10 (12) | -2.50 % / -3.49 % | -0.43 | 40 % | -1.88 % | +0.62 % | +0.12 % (0.02) | +0.65 % (0.12) | 30 (-5.3 %/+4.1 %/+17.2 %) | 0/0 | -2.81 % | -1.23 % | H10 n10 -7.1 %; H40 n10 +3.0 %; floor1bn n12 +0.5 % | -0.3 % / -0.11 / -6 % | 0.00 | **UNTESTABLE** |
| split_ann_toex | 10 (12) | +1.83 % / -5.46 % | 0.20 | 30 % | +2.87 % | +1.04 % | +8.51 % (1.07) | +7.20 % (0.83) | 48 (-5.5 %/+7.7 %/+28.7 %) | 0/0 | +1.31 % | +3.43 % | H20 n10 -2.5 %; H40 n10 +3.0 %; floor1bn n12 +10.6 % | +0.3 % / 0.14 / -6 % | 0.00 | **UNTESTABLE** |
| split_ex_20 | 28 (38) | -2.21 % / -3.26 % | -0.53 | 32 % | -1.50 % | +0.70 % | +0.62 % (0.16) | -1.16 % (-0.28) | 9 (-1.9 %/+2.9 %/+8.7 %) | 2/3 | -2.56 % | -2.36 % | H10 n28 -3.0 %; H40 n28 -3.4 %; floor1bn n38 -0.9 % | -0.9 % / -0.52 / -8 % | 0.00 | **UNTESTABLE** |
| buyback_ann_20 | 115 (150) | -0.34 % / -1.18 % | -0.26 | 44 % | +0.58 % | +0.92 % | -1.77 % (-1.20) | -0.83 % (-0.74) | 12 (-1.6 %/+0.6 %/+2.8 %) | 1/3 | -0.80 % | -0.85 % | H10 n116 +0.7 %; H40 n113 +2.0 %; floor1bn n150 -0.3 % | -0.5 % / -0.01 / -21 % | 0.00 | **CLOSED** |
| tender_ann_20 | 43 (64) | -0.77 % / -0.69 % | -0.26 | 42 % | +0.22 % | +0.99 % | +1.37 % (0.48) | +0.50 % (0.17) | 49 (-4.7 %/+0.6 %/+7.3 %) | 3/4 | -1.25 % | -0.29 % | H10 n44 +0.3 %; H40 n41 +0.3 %; floor1bn n64 +4.7 % | -0.6 % / -0.14 / -13 % | 0.00 | **CLOSED** |
| rights_ann_20 | 41 (58) | +3.37 % / -2.08 % | 0.62 | 46 % | +4.46 % | +1.10 % | +7.27 % (1.39) | +5.03 % (0.98) | 61 (-2.8 %/+3.8 %/+11.6 %) | exc<0 0/4 | +2.83 % | +2.67 % | H10 n42 -0.2 %; H40 n39 -0.7 %; floor1bn n58 +1.4 % | +0.9 % / 0.19 / -12 % | 0.00 | **CLOSED (no avoid signal)** |
| rights_ex_20 | 50 (76) | -3.86 % / -12.05 % | -0.90 | 36 % | -2.83 % | +1.04 % | -1.92 % (-0.46) | -2.56 % (-0.61) | 9 (-3.9 %/+2.0 %/+9.1 %) | exc<0 2/4 | -4.38 % | -3.71 % | H10 n50 -6.1 %; H40 n50 -0.9 %; floor1bn n76 -4.8 % | -2.2 % / -0.51 / -16 % | 0.00 | **CLOSED (no avoid signal)** |

Reverse split: 4 events (MITI 2020-11-19 factor 2.500; BEKS 2020-12-10 factor 10.000; BBRM 2022-02-18 factor 1.500; NETV 2024-10-22 factor 2.000) -> **UNTESTABLE**, no trial spent.

## Per year (net mean / matched excess, events)

| trial | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|
| split_ann_20 | - | - | - | +5.0 % / +12.7 % (n2) | +19.9 % / +18.9 % (n2) | -4.2 % / -0.2 % (n2) | -16.6 % / -15.4 % (n4) |
| split_ann_toex | - | - | - | +3.3 % / +7.3 % (n2) | +27.8 % / +34.2 % (n2) | +11.5 % / +12.3 % (n2) | -16.8 % / -5.6 % (n4) |
| split_ex_20 | -2.8 % / -1.0 % (n1) | +6.6 % / +6.8 % (n6) | -12.0 % / -6.6 % (n6) | +1.7 % / +5.2 % (n6) | +11.5 % / +11.7 % (n2) | +4.8 % / +1.4 % (n3) | -18.6 % / -10.4 % (n4) |
| buyback_ann_20 | - | - | - | +0.1 % / -10.6 % (n1) | -0.4 % / +2.6 % (n15) | +6.4 % / -0.3 % (n53) | -8.1 % / -4.7 % (n46) |
| tender_ann_20 | - | - | - | +2.4 % / +5.9 % (n6) | +1.8 % / +4.5 % (n10) | +1.6 % / -1.0 % (n14) | -6.8 % / -0.5 % (n13) |
| rights_ann_20 | - | - | - | +10.9 % / +9.3 % (n5) | -0.5 % / +6.4 % (n10) | +12.7 % / +12.5 % (n11) | -3.4 % / +3.3 % (n15) |
| rights_ex_20 | -25.7 % / -23.6 % (n1) | +0.4 % / +3.4 % (n18) | -4.3 % / -4.2 % (n11) | -5.5 % / -6.6 % (n4) | -15.6 % / -13.6 % (n3) | +15.1 % / +12.4 % (n7) | -27.4 % / -17.7 % (n6) |

## Diagnostics (not trials)

Market-adjusted drift from the entry close (mean), and the run-up t-20 -> entry close:

| trial | run-up | +1 | +5 | +10 | +20 | +40 | +60 | 2025+ entry-day open->close (n) |
|---|---|---|---|---|---|---|---|---|
| split_ann_20 | +8.7 % | -1.3 % | -1.6 % | -2.2 % | +0.6 % | +8.4 % | +4.1 % | -0.6 % (6) |
| split_ann_toex | +8.7 % | -1.3 % | -1.6 % | -2.2 % | +0.6 % | +8.4 % | +4.1 % | -0.6 % (6) |
| split_ex_20 | +6.1 % | -0.3 % | -0.2 % | -1.5 % | -1.2 % | -2.3 % | -0.7 % | -1.0 % (7) |
| buyback_ann_20 | +1.2 % | +0.7 % | +0.6 % | +0.2 % | -0.8 % | +1.7 % | -0.3 % | +0.5 % (99) |
| tender_ann_20 | +8.3 % | -0.5 % | -0.5 % | +1.9 % | +0.5 % | +0.9 % | +3.0 % | -2.0 % (25) |
| rights_ann_20 | +6.3 % | -0.4 % | -0.7 % | +1.6 % | +5.0 % | +5.6 % | +12.1 % | +0.4 % (19) |
| rights_ex_20 | +25.7 % | +0.8 % | -4.1 % | -5.2 % | -2.6 % | +0.4 % | +3.0 % | +0.4 % (10) |

## Reading (written after the dry run; numbers are the same seeded run)

1. **0 of 7 pass. Nothing here is a sleeve and nothing is an avoid filter.** Five long arms: three are UNTESTABLE at the desk floor
   (split announcement n 10, split to ex-date n 10, split ex-date n 28 - splitters on IDX are mostly small, illiquid names), two are
   CLOSED on the primary bar (buyback n 115: net -0.3 %, matched excess -1.8 %, t -1.2; tender / change of control n 43: net -0.8 %,
   excess +1.4 %, t 0.5). Neither avoid arm reaches -2 % / t -2: rights announcement is POSITIVE vs matched controls (+7.3 %, t 1.4,
   0/4 years negative), rights ex-date is -1.9 % (t -0.5, placebo pct 9, years 2/4).
2. **The information is priced before the disclosure.** Run-up t-20 -> entry (market-adjusted): tender +8.3 %, split +8.7 %, rights
   announcement +6.3 %, rights ex-date +25.7 %. On IDX the mandatory tender offer is disclosed AFTER the controlling stake has changed
   hands; the tender price is the acquisition price the market has already traded to. Post-hoc check (not a trial, not a verdict): a
   strict tender-title-only definition (78 disclosures, target-side wording, no 'hasil/laporan') is worse - net -2.4 % (n 25, LIQ) to
   -5.2 % (n 39, Rp 1 bn) at 20 sessions. The EM "tender offer premium" does not exist in this data after the disclosure.
3. **Buybacks:** the 2025-26 surge (112 + 86 plans, most of them the OJK "kondisi pasar berfluktuasi signifikan" no-RUPS buybacks
   after the 2025 drawdowns) gives +0.6 % gross over 20 sessions against a 0.9 % round trip; H 40 is +2.0 % net but the primary H
   fails and 2026 is -8.1 %. A buyback plan is not a commitment to buy and the market treats it that way.
4. **Rights (HMETD) as an avoid filter: no.** The median rights-ex name does fall (median net -12 %), but the mean is carried by a few
   rebounds and the matched excess is not separable from noise (t -0.5); the announcement itself is followed by a positive, noisy
   excess (right tail: BUVA, PACK, PANI). A rule that skips trend / ML entries around rights would remove winners as often as losers.
   The pre-registered combo replay was therefore not run.
5. **Reverse split: UNTESTABLE** (4 events 2020-24: MITI, BEKS, BBRM, NETV). Split drift: too few liquid events to test; the ten
   liquid split announcements run +8 % market-adjusted by +40 sessions but -2 % at +20 - a lottery, not a rule.
6. **Data notes.** (a) adj_factor handles splits and rights correctly (close x adj_factor is continuous across DSSA 2026-04-09
   1:25 and FORU 2026-09-22); (b) DEFECT: 441 'rights_or_bonus' rows dated 2026-09-21 (factor ~0.98-1.0) are artefacts of the 09-18
   backfill (the reset compared 09-21 'Previous' with 09-17's close) - they also shift adj_factor for rows before 09-18 by ~1-2 %
   on those names; excluded here, worth a fix in the ingest (not touched: read-only menu); (c) announcements exist only from
   2023-07, so every announcement arm is ~3 years; opens before 2025 exist only for LQ45, so fills are at the entry-day close
   (2025+ open->close on the entry day is -2.0 % for tender, +0.5 % buyback: the open fill would not rescue either).
7. **Trials used: 7 (883 -> 890).** Closed family: corporate-action event drift (split, buyback, tender/MTO, rights) - long-only.
