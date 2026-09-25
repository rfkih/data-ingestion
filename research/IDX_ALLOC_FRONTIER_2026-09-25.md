# IDX menu 34 - the allocation frontier of the combined Rp 20 M book - 2026-09-25 - 10 trials, cumulative N = 843

Engine, trades and costs of #168 (gap-fade scan, trend K-10 trades, ML cost-aware + live +5 %/10 d confirmation), 2022-01 -> 2026-09-16. Deployed sizing 10/5/5 (% of NAV per trade, gap/trend/ML): CAGR 39.8 %, Sharpe 1.86, mDD -21 %, 2022: +18 % 2023: +21 % 2024: +14 % 2025: +126 % 2026: +25 %.

## Sizing grid: the frontier

| cap | in-sample best sizing | CAGR | Sharpe | mDD | walk-forward picks (chosen on prior years) | WF CAGR | WF Sharpe | WF mDD | WF by year | improves deployed (WF) |
|---|---|---|---|---|---|---|---|---|---|---|
| -10 % | none (no sizing holds the cap) | nan % | nan | nan % | 2023: 2.5/5/5, 2024: 2.5/2.5/10, 2025: 10/2.5/10, 2026: 10/2.5/5 | 52.9 % | 2.09 | -21 % | 23:+21 24:+33 25:+132 26:+29 | no |
| -15 % | 10/2.5/2.5 | 24.4 % | 1.85 | -13 % | 2023: 10/10/5, 2024: 7.5/7.5/10, 2025: 7.5/5/10, 2026: 10/5/7.5 | 56.3 % | 1.92 | -22 % | 23:+23 24:+26 25:+161 26:+29 | no |
| -20 % | 7.5/7.5/7.5 | 50.7 % | 1.98 | -20 % | 2023: 10/10/5, 2024: 7.5/7.5/10, 2025: 7.5/5/10, 2026: 10/7.5/7.5 | 56.0 % | 1.94 | -21 % | 23:+23 24:+26 25:+161 26:+28 | no |
| -25 % | 10/5/10 | 61.7 % | 2.01 | -24 % | 2023: 10/10/5, 2024: 7.5/7.5/10, 2025: 7.5/5/10, 2026: 10/10/10 | 57.8 % | 1.87 | -24 % | 23:+23 24:+26 25:+161 26:+33 | no |

Top sizings by CAGR (in-sample, for scale):

| sizing gap/trend/ML | CAGR | Sharpe | mDD | invested-year worst |
|---|---|---|---|---|
| 10/5/10 | 61.7 % | 2.01 | -24 % | -24 % |
| 10/10/10 | 59.5 % | 1.88 | -24 % | -24 % |
| 7.5/5/10 | 56.9 % | 1.94 | -24 % | -24 % |
| 10/7.5/10 | 55.9 % | 1.86 | -23 % | -23 % |
| 7.5/7.5/10 | 55.3 % | 1.90 | -22 % | -22 % |
| 5/7.5/10 | 53.4 % | 1.89 | -22 % | -22 % |
| 10/2.5/10 | 53.1 % | 1.83 | -24 % | -24 % |
| 10/7.5/7.5 | 52.6 % | 1.97 | -21 % | -21 % |

## Overlays on the deployed sizing

| overlay | CAGR | Sharpe | mDD | mean exposure | 2022 | 2023 | 2024 | 2025 | 2026 | improves deployed |
|---|---|---|---|---|---|---|---|---|---|---|
| none (deployed) | 39.8 % | 1.86 | -21 % | 100 % | +18 % | +21 % | +14 % | +126 % | +25 % | reference |
| cash30 | 36.2 % | 1.95 | -15 % | 100 % | +19 % | +20 % | +9 % | +101 % | +32 % | YES |
| vt10 | 25.8 % | 1.94 | -12 % | 85 % | +13 % | +19 % | +12 % | +72 % | +10 % | no |
| vt15 | 31.4 % | 1.97 | -14 % | 93 % | +16 % | +21 % | +13 % | +94 % | +13 % | no |
| gate50 | 30.6 % | 1.74 | -21 % | 80 % | +19 % | +12 % | +15 % | +95 % | +13 % | no |
| brake10 | 32.5 % | 1.89 | -19 % | 96 % | +18 % | +16 % | +13 % | +122 % | +5 % | no |
| gate+brake | 29.1 % | 1.89 | -19 % | 79 % | +19 % | +12 % | +15 % | +94 % | +8 % | no |

## Verdict (menu 34, study stored)

Overlays that improve the deployed book (mDD shallower by >= 5 pp, CAGR >= 80 %): cash30. Frontier caps whose walk-forward sizing improves it: none. Changing the live book's sizing or adding an overlay is the operator's call.
