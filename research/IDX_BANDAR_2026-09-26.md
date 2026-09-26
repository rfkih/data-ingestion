# IDX menu 4 — bandarmologi — 2026-09-26 — 10 trials, cumulative N = 258

Feed: 531 names, 7727 windows of 20 trading days, 2023-09-04 -> 2026-09-25; signals on window ends; entry close t+1 @offer, exit @bid, fees 0.10/0.20 %.

| arm | H | trades | hit | gross/trade | net/trade | t(basket) | total | Sharpe | mDD | expo | years | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| random (signal dates) | 20 | 340 | 46 % | +1.23 % | +0.57 % | 0.6 | +2 % | 0.16 | -7 % | 4 % | 23:-1 24:-0 25:+3 26:+1 | reference |
| random (signal dates) | 60 | 300 | 43 % | -0.19 % | -0.87 % | -0.4 | -0 % | -0.02 | -8 % | 4 % | 23:+0 24:+1 25:+2 26:-4 | reference |
| big_acc | 20 | 97 | 48 % | +1.51 % | +0.84 % | 0.6 | +1 % | 0.20 | -2 % | 1 % | 23:+1 24:+0 25:+1 26:-1 | tested: n,t<2.5,sharpe<1,vs random |
| big_acc | 60 | 90 | 39 % | -3.51 % | -4.17 % | -0.8 | -1 % | -0.30 | -3 % | 1 % | 23:+0 24:+0 25:+0 26:-2 | tested: n,t<2.5,sharpe<1,vs random |
| acc | 20 | 197 | 49 % | +1.22 % | +0.58 % | 0.3 | +1 % | 0.18 | -4 % | 2 % | 23:-0 24:+1 25:+3 26:-2 | tested: t<2.5,years,sharpe<1,vs random |
| acc | 60 | 182 | 47 % | +1.88 % | +1.23 % | 0.3 | +1 % | 0.11 | -4 % | 2 % | 23:+0 24:+1 25:+2 26:-2 | tested: t<2.5,sharpe<1,vs random |
| breadth | 20 | 198 | 46 % | +1.16 % | +0.52 % | 0.6 | +1 % | 0.16 | -4 % | 2 % | 23:-0 24:-1 25:+1 26:+0 | tested: t<2.5,years,sharpe<1,vs random |
| asing | 20 | 199 | 47 % | +0.84 % | +0.19 % | 0.1 | +0 % | 0.04 | -5 % | 2 % | 23:-0 24:+1 25:+2 26:-3 | tested: t<2.5,years,sharpe<1,vs random |
| asing | 60 | 187 | 41 % | -1.19 % | -1.83 % | -1.0 | -1 % | -0.19 | -6 % | 2 % | 23:+0 24:-0 25:+2 26:-4 | tested: t<2.5,years,sharpe<1,vs random |
| lokal_quiet | 20 | 110 | 47 % | -0.41 % | -1.04 % | -0.1 | -1 % | -0.30 | -3 % | 1 % | 23:-0 24:-0 25:+0 26:-1 | tested: n,t<2.5,years,sharpe<1,vs random |
| persist | 20 | 25 | 44 % | +5.65 % | +5.05 % | 1.2 | +1 % | 0.66 | -0 % | 0 % | 23:+0 24:+0 25:+1 26:-0 | tested: n,t<2.5,sharpe<1,vs random |
| persist | 60 | 23 | 61 % | +6.87 % | +6.25 % | 0.9 | +0 % | 0.40 | -0 % | 0 % | 23:+0 24:+0 25:+0 26:-0 | tested: n,t<2.5,sharpe<1,vs random |
| dist | 20 | 218 | 45 % | +0.11 % | -0.55 % | 0.0 | -2 % | -0.19 | -7 % | 3 % | 23:+0 24:+1 25:+0 26:-3 | reference (mirror) |

Gross forward returns by the API's own label (no costs, every fetched name, equal weight):

| label | n | P(up 20d) | avg 20d | median 20d | P(up 60d) | avg 60d | median 60d |
|---|---|---|---|---|---|---|---|
| broker_accdist= | 2395 | 44 % | -0.24 % | -1.28 % | 42 % | +0.32 % | -3.56 % |
| broker_accdist=Acc | 319 | 51 % | +2.59 % | +0.25 % | 49 % | +7.73 % | -0.27 % |
| broker_accdist=Dist | 354 | 47 % | +1.50 % | -1.06 % | 45 % | +5.73 % | -2.27 % |
| top1_label= | 2395 | 44 % | -0.24 % | -1.28 % | 42 % | +0.32 % | -3.56 % |
| top1_label=Big Acc | 105 | 51 % | +2.49 % | +0.24 % | 43 % | +1.95 % | -4.21 % |
| top1_label=Big Dist | 121 | 49 % | +2.93 % | -0.97 % | 48 % | +11.55 % | -1.14 % |
| top1_label=Neutral | 163 | 47 % | +1.36 % | -0.87 % | 46 % | +6.98 % | -2.56 % |
| top1_label=Normal Acc | 68 | 49 % | +0.63 % | -0.55 % | 56 % | +7.65 % | +3.79 % |
| top1_label=Normal Dist | 67 | 49 % | +1.07 % | +0.00 % | 46 % | +5.02 % | -1.06 % |
| top1_label=Small Acc | 63 | 51 % | +3.12 % | +0.74 % | 49 % | +10.17 % | -0.69 % |
| top1_label=Small Dist | 86 | 45 % | +2.43 % | -0.96 % | 42 % | +2.99 % | -3.18 % |

Reading rule applied as declared: 0 candidate(s) of 10.

Limits: 3 years of data (2023-09 →) on 46 names; 20-day windows (a signal only every 20 days per name); the API's labels are
Stockbit's own definitions; net by investor class uses the API's broker classification; close-to-close execution as in menus 1–3.
