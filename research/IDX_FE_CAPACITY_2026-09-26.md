# IDX FE-2 - market impact and capacity of the deployed combo book - 2026-09-26

Script `research/idx_fe_capacity.py`. Impact calibration and the capacity curve are MEASUREMENT (0 trials); part 3 spends 5 pre-registered trials, cumulative N 954 -> 959 (ids 955..959; range 955..960 was allocated to this menu by the caller; the ledger max at run time, 967, is fe_kelly_rl / rl_alloc, which start after 960). Deployed book = gap 10 % / trend 5 % / ML ens4 5 % of NAV per trade, 20 slots, cash floor 30 %, 2022-01-01 -> 2026-09-16, the engine of `idx_engine_fix.py` (d) with point-in-time board (IDX_BOARD_MODE=pit, tmp/exit_cache_pit.pkl, tmp/ml_strategy_cache.pkl); gap opens only open_src='idx'.

**Baseline reproduced** (Rp 20 M, zero impact, no cap): 33.8 % / 1.83 / -17.9 % (target 33.8 % / 1.83 / -17.9 %; the capacity engine is asserted equal to `engine_fix.engine_attr` to 1e-3 Rp per day).

## 1. Impact model

cost per fill = spread/2 (already charged: buys at the closing offer, sells at the closing bid) + **Y x sigma20 x (Q / ADV20)^delta**, sigma20 = 20-day stdev of daily log returns, ADV20 = 20-day mean REGULAR-board value (negotiated trades removed), both known at t-1; Q = the order's Rp value. Several pieces in one name/side on one day pay the marginal cost of the aggregate.

| source | proxy | n | Y (free delta) | delta [90 % CI] | R2 (bins) | Y at delta=0.5 [90 % CI] |
|---|---|---|---|---|---|---|
| A all | daily net foreign flow | 428,687 | 1.49 | 0.93 [0.76, 1.10] | 0.91 | 0.64 [0.62, 0.66] |
| A ADV tercile low | daily net foreign flow | 137,640 | 0.52 | 0.88 [0.54, 1.05] | 0.79 | 0.26 [0.24, 0.29] |
| A ADV tercile mid | daily net foreign flow | 142,759 | 1.27 | 0.82 [0.69, 1.02] | 0.94 | 0.68 [0.66, 0.70] |
| A ADV tercile high | daily net foreign flow | 148,288 | 1.33 | 0.75 [0.66, 0.82] | 0.97 | 0.87 [0.85, 0.89] |
| A ADV < Rp 5 bn | daily net foreign flow | 204,201 | 0.97 | 0.95 [0.67, 0.99] | 0.88 | 0.38 [0.35, 0.40] |
| A 2020-02..2023-05 | daily net foreign flow | 175,017 | 1.11 | 0.80 [0.65, 0.97] | 0.93 | 0.60 [0.58, 0.62] |
| A 2023-06..2026-09 | daily net foreign flow | 253,670 | 1.24 | 0.85 [0.79, 1.04] | 0.98 | 0.67 [0.64, 0.69] |
| A, phi >= 0.03 only | local fit on the bins the book trades in | - | 0.83 | 0.65 | - | 0.65 |
| B | top-broker net over ~20-day windows (17 large caps) | 601 | 1.15 | 0.51 [0.10, 1.52] | 0.60 | 1.06 [0.77, 1.51] |
| C | live feed, 30-min signed volume (4 sessions, 119 names) | 4,722 | - | - | - | -0.58 (wrong sign) |

A bins (phi = |net foreign| / ADV20, mean I = sign x market-relative return / sigma20): 0.001: -0.004, 0.002: -0.007, 0.003: +0.006, 0.006: +0.003, 0.009: +0.021, 0.015: +0.040, 0.025: +0.063, 0.041: +0.093, 0.066: +0.152, 0.108: +0.201, 0.176: +0.287, 0.286: +0.382, 0.465: +0.478, 0.755: +0.527.
Next-day continuation of the same-day move (A, market-relative, in sigma): phi 0.01-0.03: same day +0.05, next day +0.03; phi 0.03-0.1: same day +0.13, next day +0.05; phi 0.1-0.3: same day +0.28, next day +0.06; phi 0.3-1.0: same day +0.48, next day +0.06.

D - the visible book (10 levels) at 15:40-15:49 WIB, 4 sessions: cost of sweeping phi x ADV20 over the half-spread:

| phi | share of books deep enough | median excess cost | in sigma | median half-spread |
|---|---|---|---|---|
| 0.001 | 100 % | 0 bps | 0.00 | 24 bps |
| 0.003 | 100 % | 0 bps | 0.00 | 24 bps |
| 0.01 | 100 % | 15 bps | 0.07 | 24 bps |
| 0.03 | 94 % | 52 bps | 0.22 | 24 bps |
| 0.05 | 85 % | 82 bps | 0.33 | 24 bps |
| 0.1 | 57 % | 124 bps | 0.52 | 24 bps |

**Model used: delta = 0.5, Y central = 0.83** (geometric mean of A's local fit 0.65 and B 1.06); bracket Y = 0.5 / 1.0 (literature) and 1.5 (stress: what an immediate sweep of the visible book implies at phi 0.05-0.1). Plus the A local free fit (Y 0.83, delta 0.65) as an exponent check.

## 2. Capacity curve

Main scenario **Y0.83_cap10** (Y 0.83, participation cap 10 % of ADV20 per name/side/day: entry excess skipped, exit excess spills to the next closes). CAGR / Sharpe / mDD; skip = signals with no fill because of the cap; fill = filled / wanted Rp; imp = average impact per Rp traded.

| NAV | total | gap | trend | ML | total skip / fill | round-trip impact bps per Rp entered (gap / trend / ML) | drag pp/yr |
|---|---|---|---|---|---|---|---|
| Rp 20 M | 33.1 / 1.79 / -17 | 12.3 / 1.35 / -4 | 12.6 / 1.19 / -11 | 9.0 / 1.21 / -12 | 0.5 % / 96 % | 13 / 6 / 10 | 1.04 |
| Rp 100 M | 32.0 / 1.72 / -17 | 12.0 / 1.30 / -5 | 13.0 / 1.18 / -10 | 13.0 / 1.39 / -15 | 0.5 % / 99 % | 30 / 14 / 20 | 2.30 |
| Rp 250 M | 33.1 / 1.73 / -19 | 11.5 / 1.25 / -5 | 13.0 / 1.17 / -10 | 13.0 / 1.35 / -16 | 0.5 % / 99 % | 48 / 23 / 32 | 3.84 |
| Rp 500 M | 31.8 / 1.68 / -18 | 10.9 / 1.19 / -5 | 12.8 / 1.15 / -10 | 12.9 / 1.33 / -16 | 0.5 % / 99 % | 67 / 32 / 45 | 5.26 |
| Rp 1.00 B | 30.2 / 1.59 / -19 | 10.0 / 1.10 / -5 | 12.5 / 1.13 / -10 | 12.7 / 1.31 / -16 | 0.7 % / 99 % | 90 / 44 / 63 | 7.15 |
| Rp 2.50 B | 26.8 / 1.45 / -19 | 8.3 / 0.94 / -5 | 11.9 / 1.09 / -11 | 12.2 / 1.26 / -16 | 0.7 % / 98 % | 122 / 64 / 94 | 9.90 |
| Rp 5.00 B | 24.7 / 1.38 / -19 | 6.8 / 0.80 / -6 | 11.4 / 1.04 / -11 | 11.7 / 1.21 / -16 | 1.1 % / 95 % | 151 / 88 / 124 | 11.86 |
| Rp 10.00 B | 22.5 / 1.28 / -19 | 5.6 / 0.70 / -6 | 10.5 / 0.97 / -13 | 10.4 / 1.11 / -16 | 1.9 % / 90 % | 182 / 117 / 160 | 13.93 |
| Rp 25.00 B | 17.0 / 1.06 / -21 | 3.5 / 0.50 / -6 | 8.3 / 0.84 / -18 | 9.0 / 1.03 / -16 | 4.3 % / 82 % | 224 / 161 / 213 | 16.55 |
| Rp 50.00 B | 12.4 / 0.88 / -22 | 1.2 / 0.21 / -6 | 6.2 / 0.74 / -19 | 7.8 / 0.96 / -15 | 9.6 % / 70 % | 246 / 194 / 239 | 15.89 |
| Rp 100.00 B | 8.1 / 0.70 / -20 | -0.7 / -0.08 / -9 | 4.9 / 0.75 / -15 | 4.9 / 0.70 / -14 | 13.9 % / 55 % | 268 / 219 / 258 | 13.55 |

Zero-impact reference at each NAV (lots of 100 only): Rp 20 M 33.8 %, Rp 100 M 38.1 %, Rp 250 M 39.6 %, Rp 500 M 38.3 %, Rp 1.00 B 38.5 %, Rp 2.50 B 38.0 %, Rp 5.00 B 38.8 %, Rp 10.00 B 38.9 %, Rp 25.00 B 37.3 %, Rp 50.00 B 37.3 %, Rp 100.00 B 37.3 %.

Per-sleeve skip share (main scenario, sleeve alone): gap: Rp 20 M 0 %, Rp 100 M 0 %, Rp 250 M 0 %, Rp 500 M 0 %, Rp 1.00 B 0 %, Rp 2.50 B 0 %, Rp 5.00 B 0 %; trend: Rp 20 M 0 %, Rp 100 M 0 %, Rp 250 M 0 %, Rp 500 M 0 %, Rp 1.00 B 0 %, Rp 2.50 B 0 %, Rp 5.00 B 0 %; ML: Rp 20 M 1 %, Rp 100 M 1 %, Rp 250 M 1 %, Rp 500 M 1 %, Rp 1.00 B 1 %, Rp 2.50 B 1 %, Rp 5.00 B 1 %.

### NAV thresholds (sleeve alone; total = the combined book)

SIM = first NAV on the grid (log-interpolated) where the simulated CAGR is <= 75 % / <= 50 % of the zero-impact CAGR at the same NAV (the zero-impact CAGR itself moves with NAV through lot rounding: the ML quarter-pieces are Rp 250 k at Rp 20 M). The combined book is path-dependent (shared cash, floor, slots), so its SIM points are noisy. DRAG = the smooth estimate: realised impact Rp per year / average NAV, fitted as a power of NAV over the grid (slope b ~ 0.5 = square root), solved for drag = 25 % / 50 % of the sleeve's zero-impact CAGR (median over NAV >= 100 M). DRAG is shown only without a cap: under a cap the impact saturates and the cost moves into skipped / unfilled signals, which only SIM sees. **Capacity = DRAG 25 % without a cap (cross-checked by SIM); cap rules are read on SIM.**

| scenario | book | zero-impact CAGR | SIM 25 % | SIM 50 % (CAGR halves) | DRAG 25 % | DRAG 50 % | drag slope b |
|---|---|---|---|---|---|---|---|
| Y0.5_capnone | total | 38.2 % | Rp 4.51 B | Rp 32.83 B | Rp 5.38 B | Rp 26.40 B | 0.44 |
| Y0.5_capnone | gap | 13.3 % | Rp 2.76 B | Rp 12.17 B | Rp 3.00 B | Rp 13.58 B | 0.46 |
| Y0.5_capnone | trend | 13.5 % | Rp 23.82 B | > 100 B | Rp 30.08 B | Rp 133.04 B | 0.47 |
| Y0.5_capnone | ML | 14.7 % | Rp 31.36 B | > 100 B | Rp 36.12 B | Rp 148.15 B | 0.49 |
| Y0.5_cap10 | total | 38.2 % | Rp 6.56 B | Rp 47.82 B | - | - | 0.31 |
| Y0.5_cap10 | gap | 13.3 % | Rp 2.86 B | Rp 25.02 B | - | - | 0.34 |
| Y0.5_cap10 | trend | 13.5 % | Rp 21.92 B | Rp 76.68 B | - | - | 0.40 |
| Y0.5_cap10 | ML | 14.7 % | Rp 13.84 B | Rp 73.01 B | - | - | 0.41 |
| Y0.5_cap5 | total | 38.2 % | Rp 6.51 B | Rp 31.90 B | - | - | 0.24 |
| Y0.5_cap5 | gap | 13.3 % | Rp 4.32 B | Rp 18.29 B | - | - | 0.28 |
| Y0.5_cap5 | trend | 13.5 % | Rp 15.08 B | Rp 48.01 B | - | - | 0.32 |
| Y0.5_cap5 | ML | 14.7 % | Rp 10.86 B | Rp 40.92 B | - | - | 0.34 |
| Y0.5_cap2 | total | 38.2 % | Rp 3.75 B | Rp 15.14 B | - | - | 0.11 |
| Y0.5_cap2 | gap | 13.3 % | Rp 3.78 B | Rp 10.83 B | - | - | 0.17 |
| Y0.5_cap2 | trend | 13.5 % | Rp 7.15 B | Rp 22.74 B | - | - | 0.18 |
| Y0.5_cap2 | ML | 14.7 % | Rp 6.16 B | Rp 18.09 B | - | - | 0.22 |
| Y0.83_capnone | total | 38.2 % | Rp 1.66 B | Rp 11.17 B | Rp 2.14 B | Rp 11.62 B | 0.41 |
| Y0.83_capnone | gap | 13.3 % | Rp 1.02 B | Rp 4.50 B | Rp 1.13 B | Rp 5.53 B | 0.44 |
| Y0.83_capnone | trend | 13.5 % | Rp 8.40 B | Rp 37.76 B | Rp 10.51 B | Rp 47.08 B | 0.46 |
| Y0.83_capnone | ML | 14.7 % | Rp 11.32 B | Rp 51.82 B | Rp 13.49 B | Rp 56.12 B | 0.49 |
| Y0.83_cap10 | total | 38.2 % | Rp 1.51 B | Rp 17.82 B | - | - | 0.31 |
| Y0.83_cap10 | gap | 13.3 % | Rp 1.02 B | Rp 5.47 B | - | - | 0.33 |
| Y0.83_cap10 | trend | 13.5 % | Rp 11.54 B | Rp 41.99 B | - | - | 0.40 |
| Y0.83_cap10 | ML | 14.7 % | Rp 6.96 B | Rp 55.06 B | - | - | 0.41 |
| Y0.83_cap5 | total | 38.2 % | Rp 2.96 B | Rp 16.71 B | - | - | 0.24 |
| Y0.83_cap5 | gap | 13.3 % | Rp 1.00 B | Rp 8.78 B | - | - | 0.27 |
| Y0.83_cap5 | trend | 13.5 % | Rp 10.55 B | Rp 32.86 B | - | - | 0.32 |
| Y0.83_cap5 | ML | 14.7 % | Rp 5.51 B | Rp 34.01 B | - | - | 0.34 |
| Y0.83_cap2 | total | 38.2 % | Rp 2.67 B | Rp 11.25 B | - | - | 0.11 |
| Y0.83_cap2 | gap | 13.3 % | Rp 1.40 B | Rp 7.14 B | - | - | 0.17 |
| Y0.83_cap2 | trend | 13.5 % | Rp 5.62 B | Rp 18.83 B | - | - | 0.18 |
| Y0.83_cap2 | ML | 14.7 % | Rp 4.05 B | Rp 16.21 B | - | - | 0.22 |
| Y1_capnone | total | 38.2 % | Rp 1.10 B | Rp 7.07 B | Rp 1.51 B | Rp 8.72 B | 0.40 |
| Y1_capnone | gap | 13.3 % | Rp 680 M | Rp 3.07 B | Rp 778 M | Rp 3.96 B | 0.43 |
| Y1_capnone | trend | 13.5 % | Rp 5.73 B | Rp 26.31 B | Rp 7.14 B | Rp 32.16 B | 0.46 |
| Y1_capnone | ML | 14.7 % | Rp 7.78 B | Rp 34.96 B | Rp 9.40 B | Rp 39.36 B | 0.48 |
| Y1_cap10 | total | 38.2 % | Rp 946 M | Rp 8.32 B | - | - | 0.31 |
| Y1_cap10 | gap | 13.3 % | Rp 680 M | Rp 3.29 B | - | - | 0.33 |
| Y1_cap10 | trend | 13.5 % | Rp 8.16 B | Rp 32.34 B | - | - | 0.41 |
| Y1_cap10 | ML | 14.7 % | Rp 5.46 B | Rp 42.47 B | - | - | 0.41 |
| Y1_cap5 | total | 38.2 % | Rp 1.17 B | Rp 8.45 B | - | - | 0.24 |
| Y1_cap5 | gap | 13.3 % | Rp 679 M | Rp 5.04 B | - | - | 0.27 |
| Y1_cap5 | trend | 13.5 % | Rp 7.92 B | Rp 25.73 B | - | - | 0.32 |
| Y1_cap5 | ML | 14.7 % | Rp 4.29 B | Rp 30.70 B | - | - | 0.34 |
| Y1_cap2 | total | 38.2 % | Rp 1.93 B | Rp 9.69 B | - | - | 0.12 |
| Y1_cap2 | gap | 13.3 % | Rp 769 M | Rp 5.79 B | - | - | 0.17 |
| Y1_cap2 | trend | 13.5 % | Rp 4.96 B | Rp 16.82 B | - | - | 0.18 |
| Y1_cap2 | ML | 14.7 % | Rp 3.15 B | Rp 15.27 B | - | - | 0.22 |
| Y1.5_capnone | total | 38.2 % | Rp 440 M | Rp 3.31 B | Rp 641 M | Rp 4.28 B | 0.36 |
| Y1.5_capnone | gap | 13.3 % | Rp 300 M | Rp 1.34 B | Rp 330 M | Rp 1.87 B | 0.40 |
| Y1.5_capnone | trend | 13.5 % | Rp 2.52 B | Rp 11.36 B | Rp 3.06 B | Rp 14.01 B | 0.46 |
| Y1.5_capnone | ML | 14.7 % | Rp 3.40 B | Rp 15.18 B | Rp 4.27 B | Rp 18.23 B | 0.48 |
| Y1.5_cap10 | total | 38.2 % | Rp 361 M | Rp 3.09 B | - | - | 0.31 |
| Y1.5_cap10 | gap | 13.3 % | Rp 300 M | Rp 1.36 B | - | - | 0.32 |
| Y1.5_cap10 | trend | 13.5 % | Rp 3.32 B | Rp 15.22 B | - | - | 0.41 |
| Y1.5_cap10 | ML | 14.7 % | Rp 2.29 B | Rp 15.25 B | - | - | 0.41 |
| Y1.5_cap5 | total | 38.2 % | Rp 444 M | Rp 3.75 B | - | - | 0.24 |
| Y1.5_cap5 | gap | 13.3 % | Rp 300 M | Rp 1.42 B | - | - | 0.27 |
| Y1.5_cap5 | trend | 13.5 % | Rp 3.59 B | Rp 15.03 B | - | - | 0.33 |
| Y1.5_cap5 | ML | 14.7 % | Rp 2.53 B | Rp 18.24 B | - | - | 0.34 |
| Y1.5_cap2 | total | 38.2 % | Rp 536 M | Rp 5.18 B | - | - | 0.12 |
| Y1.5_cap2 | gap | 13.3 % | Rp 301 M | Rp 2.46 B | - | - | 0.17 |
| Y1.5_cap2 | trend | 13.5 % | Rp 3.22 B | Rp 11.17 B | - | - | 0.18 |
| Y1.5_cap2 | ML | 14.7 % | Rp 1.84 B | Rp 12.70 B | - | - | 0.22 |
| Alocal_cap10 | total | 38.2 % | Rp 6.61 B | Rp 40.50 B | - | - | 0.41 |
| Alocal_cap10 | gap | 13.3 % | Rp 3.51 B | Rp 22.63 B | - | - | 0.45 |
| Alocal_cap10 | trend | 13.5 % | Rp 21.01 B | Rp 70.09 B | - | - | 0.53 |
| Alocal_cap10 | ML | 14.7 % | Rp 13.55 B | Rp 69.96 B | - | - | 0.52 |
| Y0.5_rule | total | 38.2 % | Rp 5.74 B | Rp 35.91 B | - | - | 0.20 |
| Y0.5_rule | gap | 13.3 % | Rp 3.78 B | Rp 10.83 B | - | - | 0.17 |
| Y0.5_rule | trend | 13.5 % | Rp 15.08 B | Rp 48.01 B | - | - | 0.32 |
| Y0.5_rule | ML | 14.7 % | Rp 13.84 B | Rp 73.01 B | - | - | 0.41 |
| Y0.83_rule | total | 38.2 % | Rp 2.36 B | Rp 14.14 B | - | - | 0.21 |
| Y0.83_rule | gap | 13.3 % | Rp 1.40 B | Rp 7.14 B | - | - | 0.17 |
| Y0.83_rule | trend | 13.5 % | Rp 10.55 B | Rp 32.86 B | - | - | 0.32 |
| Y0.83_rule | ML | 14.7 % | Rp 6.96 B | Rp 55.06 B | - | - | 0.41 |
| Y1_rule | total | 38.2 % | Rp 1.55 B | Rp 10.44 B | - | - | 0.21 |
| Y1_rule | gap | 13.3 % | Rp 769 M | Rp 5.79 B | - | - | 0.17 |
| Y1_rule | trend | 13.5 % | Rp 7.92 B | Rp 25.73 B | - | - | 0.32 |
| Y1_rule | ML | 14.7 % | Rp 5.46 B | Rp 42.47 B | - | - | 0.41 |
| Y1.5_rule | total | 38.2 % | Rp 425 M | Rp 5.09 B | - | - | 0.21 |
| Y1.5_rule | gap | 13.3 % | Rp 301 M | Rp 2.46 B | - | - | 0.17 |
| Y1.5_rule | trend | 13.5 % | Rp 3.59 B | Rp 15.03 B | - | - | 0.33 |
| Y1.5_rule | ML | 14.7 % | Rp 2.29 B | Rp 15.25 B | - | - | 0.41 |

Total book CAGR by scenario and NAV:

| scenario | Rp 20 M | Rp 100 M | Rp 250 M | Rp 500 M | Rp 1.00 B | Rp 2.50 B | Rp 5.00 B | Rp 10.00 B | Rp 25.00 B | Rp 50.00 B | Rp 100.00 B |
|---|---|---|---|---|---|---|---|---|---|---|---|
| zero | 33.8 | 38.1 | 39.6 | 38.3 | 38.5 | 38.0 | 38.8 | 38.9 | 37.3 | 37.3 | 37.3 |
| Y0.5_capnone | 34.9 | 36.5 | 37.5 | 35.1 | 34.1 | 31.0 | 28.7 | 26.4 | 21.3 | 14.6 | 8.5 |
| Y0.5_cap10 | 32.2 | 34.4 | 35.2 | 34.0 | 32.3 | 31.2 | 30.9 | 26.4 | 22.3 | 18.4 | 13.0 |
| Y0.5_cap5 | 32.2 | 32.1 | 35.2 | 32.6 | 32.8 | 33.6 | 30.6 | 26.7 | 20.6 | 15.0 | 9.5 |
| Y0.5_cap2 | 32.2 | 34.5 | 33.9 | 34.4 | 33.8 | 30.3 | 27.8 | 22.8 | 14.8 | 9.2 | 5.5 |
| Y0.83_capnone | 32.2 | 35.4 | 34.1 | 33.3 | 30.5 | 27.2 | 24.4 | 20.5 | 11.5 | 5.2 | -3.6 |
| Y0.83_cap10 | 33.1 | 32.0 | 33.1 | 31.8 | 30.2 | 26.8 | 24.7 | 22.5 | 17.0 | 12.4 | 8.1 |
| Y0.83_cap5 | 33.1 | 33.7 | 33.3 | 31.5 | 30.2 | 29.5 | 25.9 | 22.1 | 16.7 | 11.8 | 7.1 |
| Y0.83_cap2 | 33.1 | 33.7 | 32.0 | 32.7 | 33.2 | 28.9 | 24.9 | 20.3 | 13.0 | 7.8 | 4.6 |
| Y1_capnone | 32.8 | 33.0 | 33.4 | 32.3 | 29.1 | 26.1 | 22.8 | 16.0 | 8.5 | 0.1 | -8.1 |
| Y1_cap10 | 32.6 | 33.3 | 32.5 | 30.9 | 28.7 | 24.9 | 22.4 | 18.4 | 12.5 | 9.7 | 5.7 |
| Y1_cap5 | 32.6 | 31.5 | 31.9 | 30.6 | 29.2 | 27.0 | 24.2 | 17.9 | 14.7 | 9.9 | 5.8 |
| Y1_cap2 | 32.6 | 31.5 | 31.4 | 31.8 | 31.0 | 27.6 | 23.4 | 19.3 | 12.1 | 7.1 | 4.1 |
| Y1.5_capnone | 33.6 | 33.5 | 31.6 | 28.3 | 26.3 | 21.9 | 15.0 | 9.6 | -1.3 | -9.5 | -17.9 |
| Y1.5_cap10 | 31.6 | 31.6 | 31.0 | 27.6 | 25.3 | 20.1 | 16.9 | 12.6 | 6.2 | 2.4 | -1.3 |
| Y1.5_cap5 | 31.6 | 31.7 | 30.9 | 28.5 | 24.7 | 21.7 | 17.5 | 14.8 | 8.8 | 4.8 | 2.1 |
| Y1.5_cap2 | 31.6 | 31.7 | 30.1 | 28.9 | 27.2 | 23.2 | 19.6 | 15.3 | 9.2 | 5.0 | 2.6 |
| Alocal_cap10 | 32.0 | 35.2 | 35.5 | 34.7 | 33.0 | 31.2 | 31.1 | 26.3 | 22.0 | 17.2 | 12.1 |
| Y0.5_rule | 32.2 | 34.4 | 35.1 | 34.6 | 33.2 | 30.9 | 30.5 | 23.6 | 20.6 | 16.9 | 10.9 |
| Y0.83_rule | 33.1 | 32.0 | 33.4 | 32.6 | 31.0 | 28.3 | 25.8 | 20.4 | 17.1 | 14.0 | 9.0 |
| Y1_rule | 32.6 | 33.3 | 32.6 | 31.5 | 29.3 | 28.0 | 23.8 | 19.6 | 15.4 | 12.5 | 7.9 |
| Y1.5_rule | 31.6 | 31.6 | 31.1 | 28.3 | 26.7 | 23.1 | 19.5 | 14.3 | 10.1 | 8.2 | 4.9 |

## 3. Optimal execution - trend sleeve at Rp 11.00 B (Y 0.83, cap 10 % per child)

The first OVERNIGHT sleeve to lose 25 % of its return to impact (pure impact, Y 0.83, no cap) is **trend** (DRAG 25 % at Rp 10.51 B; the trials run at that NAV); the gap sleeve (DRAG 25 % at Rp 1.13 B) is intraday (buy the open, sell the same close), so a multi-session schedule does not apply to it.

| schedule | sleeve CAGR / Sharpe / mDD | H1 | H2 | imp bps | fill | sleeve @Y0.5 | sleeve @Y1.5 | total book | verdict |
|---|---|---|---|---|---|---|---|---|---|
| one | 10.31 / 0.96 / -13.3 | 1.2 / 0.17 | 20.1 / 1.65 | 108 | 98 % | 11.65 | 7.72 | 21.92 / 1.26 | reference |
| split2 | 7.52 / 0.74 / -14.1 | 0.9 / 0.15 | 14.4 / 1.27 | 76 | 99 % | 8.47 | 5.68 | 18.99 / 1.14 | no (full n, halves nn) |
| split3 | 6.10 / 0.62 / -15.2 | 0.7 / 0.12 | 11.7 / 1.06 | 61 | 99 % | 6.85 | 4.61 | 15.94 / 1.02 | no (full n, halves nn) |
| ac_lo | 10.39 / 0.96 / -13.0 | 1.4 / 0.19 | 20.0 / 1.64 | 105 | 99 % | 11.68 | 7.89 | 19.49 / 1.15 | no (full n, halves nn) |
| ac_mid | 10.32 / 0.96 / -13.3 | 1.2 / 0.17 | 20.1 / 1.65 | 108 | 98 % | 11.65 | 7.71 | 21.93 / 1.26 | no (full n, halves nn) |
| ac_hi | 10.31 / 0.96 / -13.3 | 1.2 / 0.17 | 20.1 / 1.65 | 108 | 98 % | 11.65 | 7.72 | 21.92 / 1.26 | no (full n, halves nn) |

AC fractions over 3 closes for a Rp 5 / 25 / 100 / 400 M order in a Rp 20 bn ADV name with sigma 3.5 %: ac_lo (lambda 1e-07): 0.75/0.15/0.10, 0.85/0.10/0.05, 0.90/0.10, 0.95/0.05; ac_mid (lambda 1e-06): 0.95/0.05, 1.00, 1.00, 1.00; ac_hi (lambda 1e-05): 1.00, 1.00, 1.00, 1.00.

Reading rule (pre-registered): CAGR >= +1 pp AND Sharpe not lower AND mDD not deeper by > 1 pp vs (a), full window and both halves. Winner: **none**.

## 4. Recommendation

Max NAV before impact eats > 25 % of the return (DRAG 25 %, sleeve alone at its deployed per-trade size, no cap; Y 1.5 / 1.0 / **0.83** / 0.5):

- **gap-fade (10 %/trade): Rp 1.13 B** (Rp 330 M / Rp 778 M / Rp 1.13 B / Rp 3.00 B). It breaks first by an order of magnitude: 10 % of NAV per trade, both legs pay impact the same day, and its edge per trade (~3 %) is the thinnest. Its open leg also trades into the opening auction, whose depth the desk cannot measure (the feed does not carry auctions), so the lower end of the bracket is the prudent reading.
- **trend (5 %/trade): Rp 10.51 B** (Rp 3.06 B / Rp 7.14 B / Rp 10.51 B / Rp 30.08 B).
- **ML ens4 (5 %/trade in quarter pieces): Rp 13.49 B** (Rp 4.27 B / Rp 9.40 B / Rp 13.49 B / Rp 36.12 B).
- **combined book: Rp 2.14 B** (Rp 641 M / Rp 1.51 B / Rp 2.14 B / Rp 5.38 B); SIM cross-check Rp 1.66 B.
- CAGR halves (DRAG 50 %, central Y): gap Rp 5.53 B, trend Rp 47.08 B, ML Rp 56.12 B, total Rp 11.62 B.

At the operator's next step (Rp 500 M) the central model costs the combined book 5.0 pp CAGR (38.3 -> 33.3 %), at Y 1.5 10.0 pp; at Rp 1 B 8.0 pp. Hundreds of millions are inside capacity; past ~Rp 1 B the gap sleeve is the binding constraint.

Sizing / participation rule for the combo runner when the book grows (model-derived; the per-sleeve rule was run as a capacity scenario, i.e. measurement, NOT a pre-registered trial):

1. Size = min(sleeve % x NAV, phi* x ADV20 value), phi* = (0.125 x edge / (Y x sigma20))^2, i.e. round-trip impact <= 25 % of the sleeve's backtest edge per trade. At sigma 3.5 %, Y 0.83: **gap 2 %, trend 5 %, ML 10 % of ADV20**; scale with 1/sigma^2 per name. Measured: rule vs no cap at central Y, combined SIM 25 % point Rp 2.36 B vs Rp 1.66 B; gap Rp 1.40 B vs Rp 1.02 B; trend Rp 10.55 B vs Rp 8.40 B; ML Rp 6.96 B vs Rp 11.32 B (the ML cap costs more skipped edge than it saves in impact: drop the ML cap; the rule becomes gap 2 %, trend 5 %, ML uncapped).
2. Unfilled remainder is dropped (do not chase the next day); exits are never skipped - spill the excess to the next close.
3. Do not stretch execution over several sessions: every multi-session schedule lost more to signal decay than it saved in impact (part 3; winner: none). Trade at one close; when capacity binds, shrink the size, do not slow the trade.
4. Above ~Rp 1 B cut the gap sleeve's per-trade weight (e.g. 10 % -> 5 %) or its K, before touching trend/ML; re-run this script with the live scorecard's measured slippage to re-fit Y once >= 50 live fills per sleeve exist (the combo scorecard records slippage vs ref_close).
5. At Rp 20 M impact is immaterial (central Y, cap 10 %: 33.1 % vs 33.8 %); nothing changes in the live book now.
