# IDX menu FF-1 - fundamental forecast, PRELIMINARY - 2026-09-25 - 4 trials, cumulative N = 853

Prediction made on the target period's end date (report not yet out); per-cut AUC = ordering names inside one reporting
season. PRELIMINARY: the 12.8k-workbook backlog is still downloading; 2021-2023 folds are thin and tilted to the old
value/quality pool. Only the re-run on the full data is the verdict.

## Coverage

| year | reports | names | P(profit up) | P(worse) |
|---|---|---|---|---|
| 2021 | 793 | 364 | 72% | 36% |
| 2022 | 877 | 398 | 68% | 42% |
| 2023 | 959 | 436 | 54% | 46% |
| 2024 | 1579 | 480 | 54% | 42% |
| 2025 | 1771 | 495 | 52% | 43% |
| 2026 | 871 | 450 | 63% | 41% |

## T1 - net profit up YoY

| year | n | model AUC | naive AUC | lift | Q1 med 20d | Q5 med 20d | Q5-Q1 |
|---|---|---|---|---|---|---|---|
| 2022 | 877 | 0.752 | 0.728 | +0.024 | -0.9% | +0.0% | +0.9% |
| 2023 | 959 | 0.795 | 0.734 | +0.062 | -2.8% | -3.9% | -1.0% |
| 2024 | 1579 | 0.753 | 0.719 | +0.034 | -2.0% | -2.3% | -0.4% |
| 2025 | 1771 | 0.805 | 0.763 | +0.042 | +4.0% | +3.7% | -0.3% |
| 2026 | 871 | 0.709 | 0.634 | +0.075 | +0.0% | -0.8% | -0.8% |

Pooled per-cut AUC: model 0.769, naive 0.725. Years with lift >= 0.02: 5/5. Rank IC with realised growth: +0.495. **PASSES** the pre-registered bar (preliminary).

Top features (gain share): L_np_g 18%, L_same_year 7%, ret250 6%, LY_np_g 5%, L_up 4%, LY_margin_chg 3%, L_rev_g 3%, ret120 3%, px_hi 3%, L_age 3%

## T3 - deterioration

| year | n | model AUC | naive AUC | lift | Q1 med 20d | Q5 med 20d | Q5-Q1 |
|---|---|---|---|---|---|---|---|
| 2022 | 877 | 0.717 | 0.757 | -0.041 | -0.2% | +0.0% | +0.2% |
| 2023 | 959 | 0.805 | 0.718 | +0.087 | -3.2% | +0.0% | +3.2% |
| 2024 | 1579 | 0.812 | 0.739 | +0.073 | -2.3% | +0.0% | +2.3% |
| 2025 | 1771 | 0.827 | 0.774 | +0.053 | +3.1% | +0.0% | -3.1% |
| 2026 | 871 | 0.776 | 0.657 | +0.119 | -2.5% | +0.0% | +2.5% |

Pooled per-cut AUC: model 0.789, naive 0.737. Years with lift >= 0.02: 4/5. **PASSES** the pre-registered bar (preliminary).

Top features (gain share): L_worse 19%, L_roa 6%, L_margin_chg 6%, L_same_year 5%, px_hi 4%, LY_margin_chg 3%, L_margin 3%, ret250 3%, L_log_ta_idr 3%, log_adv 3%

## Post-run diagnostic (written AFTER the run; does not change the pre-registered reading, but changes how to read it)

**The YTD label leaks what is already public.** IDX reports are year-to-date. When the latest published report is from the
same fiscal year (predicting the 6-, 9- or 12-month figure with the 3-, 6- or 9-month one already out), most of the answer
is already known: persistence alone scores per-cut AUC 0.860 on T1 and the model 0.853 - no skill added. The skill sits in
the COLD case (the latest report is from the previous fiscal year, i.e. forecasting Q1, or the full year before Q3 is out):

| subset | n | T1 model | T1 naive | T3 model | T3 naive |
|---|---|---|---|---|---|
| latest report same fiscal year | 3,756 | 0.853 | 0.860 | 0.848 | 0.830 |
| latest report previous year (cold) | 2,301 | **0.621** | 0.516 | **0.702** | 0.621 |

So the honest preliminary skill is T1 ~0.62 (+0.10 over naive) and T3 ~0.70 (+0.08), not the pooled 0.77/0.79.

**Price reaction: no money signal in the medians.** The Q5 medians of exactly +0.0 % are gocap: in T3's top quintile 22.5 %
of names trade at <= Rp 50 and 10.8 % had zero return. Means are driven by those lottery tails (T3 Q5 mean +10.7 % vs Q1
+5.3 %). T1 Q5-Q1 median spread is ~0 in every year - the market prices what this model knows.

**For the full-data run (to be pre-registered as FF-1b before it runs):** forecast the DISCRETE quarter (YTD minus the
previous YTD of the same year, vs the same quarter last year) so the known part is removed from the label; report the
cold subset separately; exclude names at <= Rp 50 from the reaction test. Discrete quarters need both years' reports of a
name, which is exactly what the backlog download supplies.
