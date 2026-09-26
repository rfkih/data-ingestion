# IDX menu 34 - the allocation frontier of the combined Rp 20 M book - 2026-09-26 - 10 trials, cumulative N = 843

Engine, trades and costs of #168 (gap-fade scan, trend K-10 trades, ML cost-aware + live +5 %/10 d confirmation), 2022-01 -> 2026-09-16. Deployed sizing 10/5/5 (% of NAV per trade, gap/trend/ML): CAGR 41.7 %, Sharpe 1.89, mDD -20 %, 2022: +4 % 2023: +12 % 2024: +20 % 2025: +184 % 2026: +20 %.

## Sizing grid: the frontier

| cap | in-sample best sizing | CAGR | Sharpe | mDD | walk-forward picks (chosen on prior years) | WF CAGR | WF Sharpe | WF mDD | WF by year | improves deployed (WF) |
|---|---|---|---|---|---|---|---|---|---|---|
| -10 % | none (no sizing holds the cap) | nan % | nan | nan % | 2023: 2.5/2.5/2.5, 2024: 2.5/2.5/2.5, 2025: 10/2.5/2.5, 2026: 10/2.5/2.5 | 30.8 % | 2.10 | -11 % | 23:+4 24:+5 25:+93 26:+27 | no |
| -15 % | 10/5/2.5 | 33.2 % | 1.90 | -15 % | 2023: 5/5/2.5, 2024: 2.5/5/2.5, 2025: 10/2.5/5, 2026: 10/5/2.5 | 36.2 % | 2.00 | -15 % | 23:+6 24:+8 25:+123 26:+23 | YES |
| -20 % | 10/7.5/2.5 | 41.6 % | 1.86 | -18 % | 2023: 2.5/10/2.5, 2024: 2.5/7.5/10, 2025: 2.5/7.5/10, 2026: 10/7.5/5 | 58.5 % | 1.94 | -21 % | 23:+0 24:+32 25:+241 26:+22 | no |
| -25 % | 10/10/5 | 52.3 % | 1.88 | -22 % | 2023: 2.5/10/2.5, 2024: 5/7.5/10, 2025: 10/5/10, 2026: 10/7.5/10 | 53.8 % | 1.70 | -34 % | 23:+0 24:+31 25:+222 26:+17 | no |

Top sizings by CAGR (in-sample, for scale):

| sizing gap/trend/ML | CAGR | Sharpe | mDD | invested-year worst |
|---|---|---|---|---|
| 10/7.5/10 | 59.9 % | 1.82 | -34 % | -34 % |
| 7.5/7.5/10 | 57.1 % | 1.78 | -35 % | -35 % |
| 10/10/7.5 | 54.9 % | 1.78 | -27 % | -27 % |
| 10/5/10 | 53.9 % | 1.73 | -36 % | -36 % |
| 5/7.5/10 | 53.6 % | 1.73 | -40 % | -40 % |
| 10/7.5/7.5 | 53.4 % | 1.83 | -27 % | -27 % |
| 10/10/5 | 52.3 % | 1.88 | -22 % | -22 % |
| 7.5/10/7.5 | 51.7 % | 1.74 | -27 % | -27 % |

## Overlays on the deployed sizing

| overlay | CAGR | Sharpe | mDD | mean exposure | 2022 | 2023 | 2024 | 2025 | 2026 | improves deployed |
|---|---|---|---|---|---|---|---|---|---|---|
| none (deployed) | 41.7 % | 1.89 | -20 % | 100 % | +4 % | +12 % | +20 % | +184 % | +20 % | reference |
| cash30 | 37.3 % | 1.84 | -20 % | 100 % | +4 % | +15 % | +20 % | +147 % | +16 % | no |
| vt10 | 24.3 % | 1.79 | -14 % | 82 % | +0 % | +11 % | +16 % | +93 % | +7 % | no |
| vt15 | 30.9 % | 1.86 | -17 % | 91 % | +2 % | +14 % | +18 % | +124 % | +9 % | no |
| gate50 | 34.5 % | 1.86 | -20 % | 80 % | +6 % | +11 % | +17 % | +142 % | +14 % | no |
| brake10 | 36.8 % | 2.01 | -17 % | 87 % | +7 % | +4 % | +16 % | +183 % | +12 % | no |
| gate+brake | 32.9 % | 1.98 | -17 % | 76 % | +7 % | +7 % | +17 % | +141 % | +12 % | no |

## Verdict (menu 34, study stored)

Overlays that improve the deployed book (mDD shallower by >= 5 pp, CAGR >= 80 %): none. Frontier caps whose walk-forward sizing improves it: cap-15. Changing the live book's sizing or adding an overlay is the operator's call.
