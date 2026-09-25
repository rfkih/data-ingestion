# IDX Track B5 / menu 40 - foreign net flow as a gate on the deployed combo entries - 2026-09-25 - 10 trials, cumulative N = 903

Same engine, trade lists and costs as the deployed combo (#168 lists, menu-34 engine, gap 10 % / trend 5 % / ML 5 % of NAV per trade, 30 % cash floor), 2022-01 -> 2026-09-16. Each sleeve is run alone on the engine, gated vs ungated in the SAME run. Flow for an entry on t is read from idx.daily_summary of t-1 or earlier. Cells: CAGR / Sharpe / mDD.

Ungated references: trend 8.7 % / 0.92 / -12.6 % (halves split 2024-01-22); ML 16.7 % / 1.50 / -14.0 % (halves split 2024-05-16); gap 12.8 % / 1.39 / -4.3 % (halves split 2026-01-29); combined book 36.2 % / 1.95 / -15.3 %.

## Arms vs ungated (same run)

| arm | gate | sleeve | trades kept | gated | ungated | half 1 gated vs ungated | half 2 gated vs ungated | halves | placebo pct (median / p95 Sharpe) | neighbours | fees x1.5 gated vs ungated | combined book | DSR @N | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| T1 | trend_veto_q20 | trend | 226/266 | 6.9 % / 0.85 / -14.0 % | 8.7 % / 0.92 / -12.6 % | 4.5 % / 0.60 / -8.9 % vs 6.9 % / 0.79 / -8.0 % | 8.7 % / 1.01 / -9.9 % vs 9.9 % / 0.99 / -12.6 % | 0/2 | 46 (0.87 / 1.12) | 1/4 | 6.6 % / 0.82 / -14.7 % vs 7.9 % / 0.85 / -13.7 % | 34.2 % / 1.83 / -14.8 % | 0.08 | no |
| T2 | trend_pos20 | trend | 187/266 | 8.0 % / 1.06 / -11.9 % | 8.7 % / 0.92 / -12.6 % | 6.5 % / 0.92 / -6.9 % vs 6.9 % / 0.79 / -8.0 % | 9.1 % / 1.15 / -11.9 % vs 9.9 % / 0.99 / -12.6 % | 2/2 | 86 (0.82 / 1.16) | 0/4 | 7.7 % / 1.02 / -11.8 % vs 7.9 % / 0.85 / -13.7 % | 37.8 % / 1.97 / -17.0 % | 0.17 | no |
| M1 | ml_veto_q20 | ML | 163/195 | 14.2 % / 1.46 / -13.3 % | 16.7 % / 1.50 / -14.0 % | 15.8 % / 2.18 / -4.1 % vs 16.2 % / 2.15 / -5.5 % | 12.6 % / 1.10 / -13.3 % vs 17.3 % / 1.26 / -14.0 % | 1/2 | 57 (1.42 / 1.66) | 1/4 | 13.9 % / 1.43 / -13.3 % vs 16.2 % / 1.45 / -14.1 % | 32.9 % / 1.90 / -15.5 % | 0.46 | no |
| M2 | ml_pos20 | ML | 125/195 | 13.8 % / 1.67 / -11.9 % | 16.7 % / 1.50 / -14.0 % | 14.4 % / 2.24 / -3.2 % vs 16.2 % / 2.15 / -5.5 % | 13.3 % / 1.38 / -11.9 % vs 17.3 % / 1.26 / -14.0 % | 0/2 | 91 (1.31 / 1.73) | 0/4 | 13.5 % / 1.65 / -11.9 % vs 16.2 % / 1.45 / -14.1 % | 31.9 % / 1.85 / -14.6 % | 0.65 | no |
| G1 | gap_veto_f5q20 | gap | 164/233 | 9.9 % / 1.23 / -3.8 % | 12.8 % / 1.39 / -4.3 % | 4.1 % / 0.82 / -3.4 % vs 7.3 % / 1.20 / -4.3 % | 47.8 % / 2.43 / -3.8 % vs 47.8 % / 2.20 / -3.5 % | 0/2 | 46 (1.24 / 1.50) | 1/4 | 7.3 % / 0.94 / -5.3 % vs 9.2 % / 1.05 / -4.7 % | 35.7 % / 1.94 / -15.8 % | 0.55 | no |
| G2 | gap_veto_fl20q20 | gap | 130/233 | 10.1 % / 1.34 / -3.4 % | 12.8 % / 1.39 / -4.3 % | 4.6 % / 1.02 / -2.6 % vs 7.3 % / 1.20 / -4.3 % | 44.8 % / 2.43 / -3.4 % vs 47.8 % / 2.20 / -3.5 % | 1/2 | 85 (1.16 / 1.45) | 0/4 | 8.2 % / 1.13 / -3.8 % vs 9.2 % / 1.05 / -4.7 % | 32.7 % / 1.84 / -15.0 % | 0.76 | no |
| R1 | trend_mkt_instead | trend | 209/266 | 11.5 % / 1.33 / -10.7 % | 8.7 % / 0.92 / -12.6 % | 11.1 % / 1.32 / -6.5 % vs 6.9 % / 0.79 / -8.0 % | 11.6 % / 1.32 / -10.7 % vs 9.9 % / 0.99 / -12.6 % | 2/2 | 100 (0.29 / 0.86) | 1/4 | 11.0 % / 1.29 / -10.7 % vs 7.9 % / 0.85 / -13.7 % | 43.4 % / 2.23 / -16.3 % | 0.34 | IMPROVES |
| R2 | trend_mkt_along | trend | 194/266 | 10.5 % / 1.27 / -12.3 % | 8.7 % / 0.92 / -12.6 % | 10.3 % / 1.31 / -6.5 % vs 6.9 % / 0.79 / -8.0 % | 10.5 % / 1.23 / -12.3 % vs 9.9 % / 0.99 / -12.6 % | 2/2 | 98 (0.55 / 1.03) | 1/4 | 10.3 % / 1.25 / -12.2 % vs 7.9 % / 0.85 / -13.7 % | 43.3 % / 2.24 / -16.3 % | 0.29 | IMPROVES |
| R3 | ml_mkt | ML | 90/195 | 3.7 % / 0.60 / -12.8 % | 16.7 % / 1.50 / -14.0 % | 7.0 % / 1.15 / -5.3 % vs 16.2 % / 2.15 / -5.5 % | 0.6 % / 0.12 / -12.8 % vs 17.3 % / 1.26 / -14.0 % | 0/2 | 2 (1.14 / 1.67) | 0/4 | 3.5 % / 0.58 / -12.8 % vs 16.2 % / 1.45 / -14.1 % | 23.7 % / 1.54 / -15.0 % | 0.02 | no |
| R4 | gap_mkt | gap | 39/233 | 0.8 % / 0.34 / -2.6 % | 12.8 % / 1.39 / -4.3 % | 0.9 % / 0.37 / -2.6 % vs 7.3 % / 1.20 / -4.3 % | 0.0 % / 0.00 / 0.0 % vs 47.8 % / 2.20 / -3.5 % | 0/2 | 0 (0.98 / 1.26) | 0/4 | 0.3 % / 0.13 / -3.0 % vs 9.2 % / 1.05 / -4.7 % | 24.2 % / 1.62 / -16.5 % | 0.01 | no |

## Neighbours (full window, same reading rule vs ungated)

| arm | neighbour (kind, window, threshold) | CAGR / Sharpe / mDD | pass |
|---|---|---|---|
| T1 | ('q', 10, 0.2) | 7.8 % / 0.90 / -11.9 % | no |
| T1 | ('q', 40, 0.2) | 7.9 % / 0.93 / -11.9 % | yes |
| T1 | ('q', 20, 0.1) | 8.4 % / 0.91 / -12.3 % | no |
| T1 | ('q', 20, 0.33) | 7.5 % / 0.97 / -11.3 % | no |
| T2 | ('pos', 10, 0.0) | 6.8 % / 0.93 / -12.6 % | no |
| T2 | ('pos', 40, 0.0) | 5.0 % / 0.72 / -11.5 % | no |
| T2 | ('pos', 20, -0.05) | 7.1 % / 0.84 / -14.0 % | no |
| T2 | ('pos', 20, 0.05) | 3.3 % / 0.76 / -6.9 % | no |
| M1 | ('q', 10, 0.2) | 16.6 % / 1.78 / -10.7 % | yes |
| M1 | ('q', 40, 0.2) | 13.3 % / 1.36 / -12.9 % | no |
| M1 | ('q', 20, 0.1) | 15.1 % / 1.46 / -13.1 % | no |
| M1 | ('q', 20, 0.33) | 13.2 % / 1.53 / -11.9 % | no |
| M2 | ('pos', 10, 0.0) | 12.2 % / 1.62 / -10.2 % | no |
| M2 | ('pos', 40, 0.0) | 11.0 % / 1.37 / -12.5 % | no |
| M2 | ('pos', 20, -0.05) | 13.8 % / 1.41 / -13.0 % | no |
| M2 | ('pos', 20, 0.05) | 3.1 % / 0.94 / -4.5 % | no |
| G1 | ('q', 2, 0.2) | 10.5 % / 1.30 / -4.2 % | no |
| G1 | ('q', 10, 0.2) | 11.8 % / 1.39 / -3.6 % | yes |
| G1 | ('q', 5, 0.1) | 12.4 % / 1.43 / -4.4 % | no |
| G1 | ('q', 5, 0.33) | 7.9 % / 1.08 / -3.8 % | no |
| G2 | ('fl', 10, 0.2) | 9.1 % / 1.37 / -2.9 % | no |
| G2 | ('fl', 40, 0.2) | 9.4 % / 1.36 / -4.7 % | no |
| G2 | ('fl', 20, 0.1) | 10.0 % / 1.29 / -3.5 % | no |
| G2 | ('fl', 20, 0.33) | 7.4 % / 1.11 / -3.4 % | no |
| R1 | ('mkt_instead', 10, 0.0) | 6.7 % / 0.76 / -14.5 % | no |
| R1 | ('mkt_instead', 40, 0.0) | 6.4 % / 0.79 / -15.5 % | no |
| R1 | ('mkt_instead', 20, -0.02) | 11.7 % / 1.13 / -16.3 % | no |
| R1 | ('mkt_instead', 20, 0.02) | 8.9 % / 1.30 / -6.0 % | yes |
| R2 | ('mkt_along', 10, 0.0) | 6.4 % / 0.75 / -13.5 % | no |
| R2 | ('mkt_along', 40, 0.0) | 5.7 % / 0.73 / -15.5 % | no |
| R2 | ('mkt_along', 20, -0.02) | 11.8 % / 1.21 / -14.1 % | no |
| R2 | ('mkt_along', 20, 0.02) | 8.0 % / 1.22 / -6.0 % | yes |
| R3 | ('mkt', 10, 0.0) | 8.3 % / 1.20 / -12.8 % | no |
| R3 | ('mkt', 40, 0.0) | 7.6 % / 1.19 / -12.8 % | no |
| R3 | ('mkt', 20, -0.02) | 11.8 % / 1.45 / -12.6 % | no |
| R3 | ('mkt', 20, 0.02) | 3.9 % / 0.91 / -3.3 % | no |
| R4 | ('mkt', 10, 0.0) | 0.7 % / 0.42 / -1.6 % | no |
| R4 | ('mkt', 40, 0.0) | 2.0 % / 0.83 / -0.9 % | no |
| R4 | ('mkt', 20, -0.02) | 5.8 % / 0.93 / -3.6 % | no |
| R4 | ('mkt', 20, 0.02) | 1.0 % / 0.56 / -0.3 % | no |

## Verdict

- **trend**: R1, R2 IMPROVES (T1 halves 0/2, placebo 46, T2 halves 2/2, placebo 86, R1 halves 2/2, placebo 100, R2 halves 2/2, placebo 98).
- **ML**: no foreign-flow gate improves it (M1 halves 1/2, placebo 57, M2 halves 0/2, placebo 91, R3 halves 0/2, placebo 2).
- **gap**: no foreign-flow gate improves it (G1 halves 0/2, placebo 46, G2 halves 1/2, placebo 85, R4 halves 0/2, placebo 0).

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

