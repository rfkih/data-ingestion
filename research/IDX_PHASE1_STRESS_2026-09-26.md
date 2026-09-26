# Phase 1 - the combined book under crashes it never saw - 2026-09-26

Deployed configuration (#348 trade list), overnight holdings on each backtest day, each name's own return over the window
(beta x COMPOSITE when it was not listed). Loss as % of that day's NAV. Audit, no trial.

Invested share (overnight): median 48 %, max 72 % (cash floor 30 % caps new buys at 70 %).

| scenario | window | COMPOSITE | median day | 95th pct day | worst day | worst date | days past -25 % | past -30 % |
|---|---|---|---|---|---|---|---|---|
| covid | 2020-01-14 -> 2020-03-24 | -37.7 % | -17.6 % | -30.4 % | -37.6 % | 2023-12-11 | 14 % | 6 % |
| y2025 | 2024-09-19 -> 2025-04-09 | -24.5 % | -8.2 % | -17.4 % | -22.4 % | 2022-04-08 | 0 % | 0 % |
| worst5 | 2020-03-12 -> 2020-03-19 | -16.1 % | -6.6 % | -12.2 % | -14.4 % | 2023-12-11 | 0 % | 0 % |
| shock10 | -10 % x beta | - | -4.1 % | -7.7 % | -9.5 % | 2026-07-23 | 0 % | 0 % |
| arb2 | 2 x -15 % (assumed ARB) | - | -13.4 % | -19.3 % | -19.9 % | 2022-03-24 | 0 % | 0 % |

Limits: holdings are replayed as a block with no exits during the window (the trail-10 and the ML stop would cut part
of a slow fall, nothing of a gap-down); 2020 names that were not listed move by beta x COMPOSITE, which understates a small
cap's own fall; the ARB level is an assumption (15 %/day).
