# IDX Track B5 / menu 40 - foreign net flow as a gate on the deployed combo entries - 2026-09-26 - 10 trials, cumulative N = 903

Same engine, trade lists and costs as the deployed combo (#168 lists, menu-34 engine, gap 10 % / trend 5 % / ML 5 % of NAV per trade, 30 % cash floor), 2022-01 -> 2026-09-16. Each sleeve is run alone on the engine, gated vs ungated in the SAME run. Flow for an entry on t is read from idx.daily_summary of t-1 or earlier. Cells: CAGR / Sharpe / mDD.

Ungated references: trend 12.7 % / 1.19 / -11.6 % (halves split 2024-01-16); ML 13.1 % / 1.20 / -22.4 % (halves split 2024-08-30); gap 12.8 % / 1.39 / -4.3 % (halves split 2026-01-29); combined book 37.3 % / 1.84 / -19.9 %.

## Arms vs ungated (same run)

| arm | gate | sleeve | trades kept | gated | ungated | half 1 gated vs ungated | half 2 gated vs ungated | halves | placebo pct (median / p95 Sharpe) | neighbours | fees x1.5 gated vs ungated | combined book | DSR @N | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| T1 | trend_veto_q20 | trend | 241/282 | 12.7 % / 1.31 / -10.4 % | 12.7 % / 1.19 / -11.6 % | 3.8 % / 0.45 / -10.4 % vs 5.5 % / 0.60 / -8.3 % | 20.2 % / 1.92 / -7.6 % vs 18.6 % / 1.62 / -8.9 % | 1/2 | 90 (1.14 / 1.35) | 3/4 | 12.4 % / 1.27 / -10.6 % vs 12.2 % / 1.16 / -12.1 % | 36.5 % / 1.85 / -20.8 % | 0.31 | no |
| T2 | trend_pos20 | trend | 194/282 | 12.0 % / 1.36 / -11.3 % | 12.7 % / 1.19 / -11.6 % | 4.3 % / 0.55 / -11.3 % vs 5.5 % / 0.60 / -8.3 % | 18.4 % / 1.96 / -8.3 % vs 18.6 % / 1.62 / -8.9 % | 1/2 | 96 (1.03 / 1.36) | 1/4 | 11.5 % / 1.31 / -11.6 % vs 12.2 % / 1.16 / -12.1 % | 39.2 % / 1.93 / -20.4 % | 0.35 | no |
| M1 | ml_veto_q20 | ML | 167/208 | 10.9 % / 1.14 / -18.9 % | 13.1 % / 1.20 / -22.4 % | 6.1 % / 0.93 / -12.2 % vs 9.2 % / 1.18 / -10.7 % | 17.7 % / 1.41 / -18.9 % vs 18.8 % / 1.33 / -22.4 % | 1/2 | 49 (1.16 / 1.43) | 1/4 | 10.7 % / 1.12 / -19.0 % vs 12.9 % / 1.19 / -22.5 % | 34.1 % / 1.75 / -19.8 % | 0.21 | no |
| M2 | ml_pos20 | ML | 126/208 | 9.0 % / 1.20 / -13.6 % | 13.1 % / 1.20 / -22.4 % | 4.1 % / 0.88 / -13.6 % vs 9.2 % / 1.18 / -10.7 % | 16.1 % / 1.56 / -12.2 % vs 18.8 % / 1.33 / -22.4 % | 0/2 | 72 (1.07 / 1.51) | 0/4 | 8.8 % / 1.18 / -13.8 % vs 12.9 % / 1.19 / -22.5 % | 33.2 % / 1.84 / -17.2 % | 0.26 | no |
| G1 | gap_veto_f5q20 | gap | 164/233 | 9.9 % / 1.23 / -3.8 % | 12.8 % / 1.39 / -4.3 % | 4.1 % / 0.82 / -3.4 % vs 7.3 % / 1.20 / -4.3 % | 47.8 % / 2.43 / -3.8 % vs 47.8 % / 2.20 / -3.5 % | 0/2 | 46 (1.25 / 1.49) | 1/4 | 7.3 % / 0.94 / -5.3 % vs 9.2 % / 1.05 / -4.7 % | 33.3 % / 1.73 / -17.3 % | 0.55 | no |
| G2 | gap_veto_fl20q20 | gap | 130/233 | 10.1 % / 1.34 / -3.4 % | 12.8 % / 1.39 / -4.3 % | 4.6 % / 1.02 / -2.6 % vs 7.3 % / 1.20 / -4.3 % | 44.8 % / 2.43 / -3.4 % vs 47.8 % / 2.20 / -3.5 % | 1/2 | 88 (1.13 / 1.41) | 0/4 | 8.2 % / 1.13 / -3.8 % vs 9.2 % / 1.05 / -4.7 % | 36.1 % / 1.85 / -17.4 % | 0.76 | no |
| R1 | trend_mkt_instead | trend | 215/282 | 7.9 % / 0.96 / -10.2 % | 12.7 % / 1.19 / -11.6 % | 4.2 % / 0.55 / -8.1 % vs 5.5 % / 0.60 / -8.3 % | 10.9 % / 1.27 / -10.2 % vs 18.6 % / 1.62 / -8.9 % | 0/2 | 100 (0.15 / 0.72) | 0/4 | 7.5 % / 0.91 / -10.4 % vs 12.2 % / 1.16 / -12.1 % | 32.8 % / 1.72 / -19.4 % | 0.11 | no |
| R2 | trend_mkt_along | trend | 199/282 | 8.7 % / 1.02 / -11.3 % | 12.7 % / 1.19 / -11.6 % | 5.8 % / 0.70 / -9.3 % vs 5.5 % / 0.60 / -8.3 % | 11.0 % / 1.28 / -11.3 % vs 18.6 % / 1.62 / -8.9 % | 0/2 | 94 (0.45 / 1.07) | 0/4 | 7.7 % / 0.92 / -10.9 % vs 12.2 % / 1.16 / -12.1 % | 32.3 % / 1.69 / -20.2 % | 0.14 | no |
| R3 | ml_mkt | ML | 98/208 | 3.9 % / 0.66 / -8.2 % | 13.1 % / 1.20 / -22.4 % | 3.8 % / 0.64 / -8.2 % vs 9.2 % / 1.18 / -10.7 % | 4.2 % / 0.73 / -8.1 % vs 18.8 % / 1.33 / -22.4 % | 0/2 | 26 (0.82 / 1.55) | 0/4 | 3.7 % / 0.63 / -8.4 % vs 12.9 % / 1.19 / -22.5 % | 28.9 % / 1.73 / -14.9 % | 0.03 | no |
| R4 | gap_mkt | gap | 39/233 | 0.8 % / 0.34 / -2.6 % | 12.8 % / 1.39 / -4.3 % | 0.9 % / 0.37 / -2.6 % vs 7.3 % / 1.20 / -4.3 % | 0.0 % / 0.00 / 0.0 % vs 47.8 % / 2.20 / -3.5 % | 0/2 | 0 (1.00 / 1.26) | 0/4 | 0.3 % / 0.13 / -3.0 % vs 9.2 % / 1.05 / -4.7 % | 25.4 % / 1.52 / -28.8 % | 0.01 | no |

## Neighbours (full window, same reading rule vs ungated)

| arm | neighbour (kind, window, threshold) | CAGR / Sharpe / mDD | pass |
|---|---|---|---|
| T1 | ('q', 10, 0.2) | 11.9 % / 1.20 / -12.9 % | no |
| T1 | ('q', 40, 0.2) | 13.9 % / 1.38 / -9.1 % | yes |
| T1 | ('q', 20, 0.1) | 13.2 % / 1.26 / -10.7 % | yes |
| T1 | ('q', 20, 0.33) | 13.6 % / 1.43 / -8.7 % | yes |
| T2 | ('pos', 10, 0.0) | 9.4 % / 1.08 / -12.7 % | no |
| T2 | ('pos', 40, 0.0) | 10.2 % / 1.15 / -9.2 % | no |
| T2 | ('pos', 20, -0.05) | 13.3 % / 1.32 / -10.2 % | yes |
| T2 | ('pos', 20, 0.05) | 1.8 % / 0.44 / -6.4 % | no |
| M1 | ('q', 10, 0.2) | 12.1 % / 1.29 / -16.9 % | yes |
| M1 | ('q', 40, 0.2) | 11.2 % / 1.16 / -19.0 % | no |
| M1 | ('q', 20, 0.1) | 12.3 % / 1.20 / -21.4 % | no |
| M1 | ('q', 20, 0.33) | 9.5 % / 1.14 / -16.7 % | no |
| M2 | ('pos', 10, 0.0) | 7.6 % / 1.10 / -12.6 % | no |
| M2 | ('pos', 40, 0.0) | 6.0 % / 1.00 / -12.7 % | no |
| M2 | ('pos', 20, -0.05) | 11.1 % / 1.18 / -20.1 % | no |
| M2 | ('pos', 20, 0.05) | 2.2 % / 0.90 / -4.4 % | no |
| G1 | ('q', 2, 0.2) | 10.5 % / 1.30 / -4.2 % | no |
| G1 | ('q', 10, 0.2) | 11.8 % / 1.39 / -3.6 % | yes |
| G1 | ('q', 5, 0.1) | 12.4 % / 1.43 / -4.4 % | no |
| G1 | ('q', 5, 0.33) | 7.9 % / 1.08 / -3.8 % | no |
| G2 | ('fl', 10, 0.2) | 9.1 % / 1.37 / -2.9 % | no |
| G2 | ('fl', 40, 0.2) | 9.4 % / 1.36 / -4.7 % | no |
| G2 | ('fl', 20, 0.1) | 10.0 % / 1.29 / -3.5 % | no |
| G2 | ('fl', 20, 0.33) | 7.4 % / 1.11 / -3.4 % | no |
| R1 | ('mkt_instead', 10, 0.0) | 4.5 % / 0.53 / -14.8 % | no |
| R1 | ('mkt_instead', 40, 0.0) | 3.1 % / 0.41 / -15.2 % | no |
| R1 | ('mkt_instead', 20, -0.02) | 9.2 % / 0.90 / -14.1 % | no |
| R1 | ('mkt_instead', 20, 0.02) | 5.9 % / 0.94 / -9.3 % | no |
| R2 | ('mkt_along', 10, 0.0) | 4.7 % / 0.55 / -13.5 % | no |
| R2 | ('mkt_along', 40, 0.0) | 3.0 % / 0.39 / -15.1 % | no |
| R2 | ('mkt_along', 20, -0.02) | 10.3 % / 1.02 / -11.7 % | no |
| R2 | ('mkt_along', 20, 0.02) | 4.6 % / 0.78 / -8.1 % | no |
| R3 | ('mkt', 10, 0.0) | 6.6 % / 1.00 / -7.5 % | no |
| R3 | ('mkt', 40, 0.0) | 6.6 % / 1.05 / -7.5 % | no |
| R3 | ('mkt', 20, -0.02) | 6.0 % / 0.86 / -11.2 % | no |
| R3 | ('mkt', 20, 0.02) | 2.8 % / 0.57 / -5.3 % | no |
| R4 | ('mkt', 10, 0.0) | 0.7 % / 0.42 / -1.6 % | no |
| R4 | ('mkt', 40, 0.0) | 2.0 % / 0.83 / -0.9 % | no |
| R4 | ('mkt', 20, -0.02) | 5.8 % / 0.93 / -3.6 % | no |
| R4 | ('mkt', 20, 0.02) | 1.0 % / 0.56 / -0.3 % | no |

## Verdict

- **trend**: no foreign-flow gate improves it (T1 halves 1/2, placebo 90, T2 halves 1/2, placebo 96, R1 halves 0/2, placebo 100, R2 halves 0/2, placebo 94).
- **ML**: no foreign-flow gate improves it (M1 halves 1/2, placebo 49, M2 halves 0/2, placebo 72, R3 halves 0/2, placebo 26).
- **gap**: no foreign-flow gate improves it (G1 halves 0/2, placebo 46, G2 halves 1/2, placebo 88, R4 halves 0/2, placebo 0).

## Reading (written after the run)

1. **Per-name foreign flow as a veto does nothing for any deployed sleeve (T1, T2, M1, M2, G1, G2: 0 of 6 pass).** Vetoing the bottom
   quintile of 20-day flow share costs trend and ML return and buys no drawdown (placebo pct 46 / 57: indistinguishable from dropping
   the same number of trades at random). The OVERLAYS 09-12 A rule (f20 > 0) is the closest: trend Sharpe 0.92 -> 1.06 in both halves,
   but placebo pct 86 (below 95), 0/4 neighbours (f10, f40, +-5 % thresholds all lose), and on the combined book the mDD deepens
   -15.3 -> -17.0 %. As in 09-12 A, the effect lives in large caps, and the trend `small` book excludes BLUE by construction.
   Gap-fade: skipping gap-downs that foreigners are dumping (G1 f5, G2 float-scaled) cuts CAGR 12.8 -> ~10 %; the heavy-selling
   gap-downs are not the bad ones.
2. **The market-wide outflow gate is the only hit, and it is fragile.** R1 (mkt 20-day net flow < 0 -> no new trend entry, INSTEAD of
   IHSG < MA200) passes the pre-registered rule: 11.5 % / 1.33 / -10.7 % vs 8.7 % / 0.92 / -12.6 %, better in both halves, placebo
   pct 100 (circular-shifted masks median Sharpe 0.29), fees x1.5 holds. R2 (both gates) likewise (placebo 98). But the window is a
   knife-edge: the 10- and 40-day versions of the SAME gate lose to ungated (Sharpe 0.76 / 0.79, mDD -14.5 / -15.5 %), only the
   +2 % threshold neighbour passes -> 1/4 neighbours; DSR 0.34 / 0.29 at N = 903. On the combined book it lifts CAGR 36.2 -> 43.4 %
   and Sharpe 1.95 -> 2.23 but deepens mDD -15.3 -> -16.3 %. Verdict: PASS BY THE LETTER / FRAGILE (neighbourhood) - not a change
   to the live trend gate; at most a paper shadow of R1 next to the IHSG gate.
3. **Market-wide outflow is where ML and gap-fade EARN.** R3/R4 keep only 46 % / 17 % of trades and sit at placebo pct 2 / 0 - the
   gate removes the best trades, not random ones. Gap-fade events cluster in foreign-outflow tape (2025-26); an outflow regime gate on
   those sleeves is the wrong sign. Do not add one.
4. Per the construction-not-accuracy rule: no foreign-flow gate is recommended for the live book. Foreign flow stays closed as a
   signal and as a per-name filter on these books; the market-flow trend gate is logged FRAGILE.



