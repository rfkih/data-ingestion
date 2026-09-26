# IDX menu FF-1 - fundamental forecast, PRELIMINARY - 2026-09-26 - 4 trials, cumulative N = 853

Prediction made on the target period's end date (report not yet out); per-cut AUC = ordering names inside one reporting
season. PRELIMINARY: the 12.8k-workbook backlog is still downloading; 2021-2023 folds are thin and tilted to the old
value/quality pool. Only the re-run on the full data is the verdict.

## Coverage

| year | reports | names | P(profit up) | P(worse) |
|---|---|---|---|---|
| 2021 | 2772 | 719 | 69% | 45% |
| 2022 | 2963 | 773 | 64% | 49% |
| 2023 | 3167 | 846 | 53% | 51% |
| 2024 | 3092 | 887 | 51% | 48% |
| 2025 | 3408 | 908 | 52% | 47% |
| 2026 | 1700 | 885 | 59% | 47% |

## T1 - net profit up YoY

| year | n | model AUC | naive AUC | lift | Q1 med 20d | Q5 med 20d | Q5-Q1 |
|---|---|---|---|---|---|---|---|
| 2021 | 2772 | 0.710 | 0.710 | -0.000 | +0.0% | +1.8% | +1.8% |
| 2022 | 2963 | 0.796 | 0.767 | +0.028 | -3.9% | +0.0% | +3.9% |
| 2023 | 3167 | 0.827 | 0.775 | +0.052 | -2.1% | -1.3% | +0.8% |
| 2024 | 3092 | 0.791 | 0.730 | +0.061 | -1.5% | +0.0% | +1.5% |
| 2025 | 3408 | 0.808 | 0.754 | +0.053 | +0.5% | +0.9% | +0.4% |
| 2026 | 1700 | 0.734 | 0.630 | +0.104 | +0.0% | +0.0% | +0.0% |

Pooled per-cut AUC: model 0.781, naive 0.737. Years with lift >= 0.02: 5/6. Rank IC with realised growth: +0.494. **PASSES** the pre-registered bar (preliminary).

Top features (gain share): L_np_g 30%, L_same_year 7%, LY_np_g 7%, L_up 7%, LY_margin_chg 5%, ret250 3%, L_margin_chg 3%, ret120 3%, L_rev_g 3%, L_log_ta_idr 2%

## T3 - deterioration

| year | n | model AUC | naive AUC | lift | Q1 med 20d | Q5 med 20d | Q5-Q1 |
|---|---|---|---|---|---|---|---|
| 2021 | 2772 | 0.831 | 0.785 | +0.045 | +3.1% | +0.0% | -3.1% |
| 2022 | 2963 | 0.822 | 0.774 | +0.048 | -0.4% | +0.0% | +0.4% |
| 2023 | 3167 | 0.835 | 0.763 | +0.072 | -2.0% | +0.0% | +2.0% |
| 2024 | 3092 | 0.851 | 0.769 | +0.083 | -2.0% | +0.0% | +2.0% |
| 2025 | 3408 | 0.848 | 0.776 | +0.071 | +2.1% | +0.0% | -2.1% |
| 2026 | 1700 | 0.793 | 0.684 | +0.109 | -1.0% | +0.0% | +1.0% |

Pooled per-cut AUC: model 0.833, naive 0.765. Years with lift >= 0.02: 6/6. **PASSES** the pre-registered bar (preliminary).

Top features (gain share): L_worse 31%, L_roa 11%, L_margin_chg 6%, L_margin 4%, L_same_year 4%, LY_margin_chg 3%, L_loss 2%, ret120 2%, L_log_ta_idr 2%, LY_np_g 2%
