# IDX engine fix - trend replay timing + point-in-time board - 2026-09-25

Measurement corrections (0 trials) + one confirmation trial (R1), cumulative N 915 -> 916. Script `research/idx_engine_fix.py`. Deployed book: gap 10 % / trend 5 % / ML ens4 5 % of NAV per trade, 20 slots, Rp 20 M, cash floor 30 %, 2022-01-01 -> 2026-09-16, the #184 engine (= #177 + ens4 pieces). Cells CAGR / Sharpe / mDD.

## The four variants (same run)

| variant | trend trades | CAGR | Sharpe | mDD | final NAV | H1 CAGR / mDD | H2 CAGR / mDD | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| (a) old engine | 266 | 29.4 % | 1.66 | -18.2 % | Rp 67.1 M | 12.7 % / -14.1 % | 48.6 % / -18.2 % | +10 % | +4 % | +15 % | +109 % | +16 % |
| (b) bug 1 fixed only | 266 | 36.0 % | 1.91 | -17.1 % | Rp 84.8 M | 14.8 % / -12.8 % | 61.2 % / -17.1 % | +17 % | +2 % | +19 % | +129 % | +24 % |
| (c) bug 2 fixed only | 282 | 24.9 % | 1.44 | -17.1 % | Rp 56.8 M | 8.3 % / -14.4 % | 44.0 % / -17.1 % | -0 % | +7 % | +12 % | +87 % | +20 % |
| (d) both fixed = new baseline | 282 | 32.9 % | 1.77 | -16.9 % | Rp 76.2 M | 10.3 % / -13.3 % | 60.3 % / -16.9 % | +5 % | +6 % | +16 % | +124 % | +23 % |

(a) reproduces #184's 'deployed' (30.8 % / 1.74 / -17.3 %): 29.4 % / 1.66 / -18.2 %.

## Per sleeve

Realised P&L inside the combined book (Rp M, trades, win rate; open = unrealised at the end) and each sleeve alone on the same engine and floor.

| variant | gap P&L | trend P&L | ML P&L | trend alone | gap alone | ML alone |
|---|---|---|---|---|---|---|
| (a) old engine | +20.4 M (174, 47 %, open +0.0) | +12.9 M (256, 37 %, open +0.0) | +13.8 M (590, 43 %, open +0.0) | 8.7 % / 0.92 / -12.6 % | 12.8 % / 1.39 / -4.3 % | 9.3 % / 1.22 / -14.4 % |
| (b) bug 1 fixed only | +26.7 M (176, 47 %, open +0.0) | +20.9 M (252, 40 %, open +0.0) | +17.2 M (616, 43 %, open +0.0) | 15.7 % / 1.52 / -8.9 % | 12.8 % / 1.39 / -4.3 % | 9.3 % / 1.22 / -14.4 % |
| (c) bug 2 fixed only | +18.9 M (177, 47 %, open +0.0) | +4.1 M (268, 37 %, open +0.0) | +13.8 M (594, 43 %, open +0.0) | 5.4 % / 0.58 / -17.8 % | 12.8 % / 1.39 / -4.3 % | 9.3 % / 1.22 / -14.4 % |
| (d) both fixed = new baseline | +23.1 M (180, 47 %, open +0.0) | +16.7 M (270, 41 %, open +0.0) | +16.3 M (610, 44 %, open +0.0) | 12.7 % / 1.19 / -11.6 % | 12.8 % / 1.39 / -4.3 % | 9.3 % / 1.22 / -14.4 % |

Deltas vs (a), combined book: (b) bug 1 fixed only: CAGR +6.6 pp, Sharpe +0.25, mDD +1.1 pp; sleeve P&L gap +6.3 M, trend +8.0 M, ML +3.4 M; (c) bug 2 fixed only: CAGR -4.5 pp, Sharpe -0.22, mDD +1.1 pp; sleeve P&L gap -1.4 M, trend -8.8 M, ML +0.0 M; (d) both fixed = new baseline: CAGR +3.6 pp, Sharpe +0.11, mDD +1.3 pp; sleeve P&L gap +2.8 M, trend +3.8 M, ML +2.5 M.

Trend P&L by year (Rp M): (a) old engine: 22 +2.0 23 +0.2 24 -0.4 25 +13.1 26 -2.1; (b) bug 1 fixed only: 22 +3.5 23 -0.2 24 +0.4 25 +17.5 26 -0.2; (c) bug 2 fixed only: 22 -0.2 23 +0.7 24 -0.8 25 +6.9 26 -2.5; (d) both fixed = new baseline: 22 +1.0 23 +0.6 24 -0.2 25 +15.2 26 +0.1.

ML sleeve and the board: 33 of 718 ML ens4 rule-trades were entered while the name was NOT on Utama/Pengembangan that day (ARKO, BNBR, BUKA, CUAN, FOLK, KPIG, KSIX, NICL, NSSS, RMKE). The ML universe is board-agnostic in research AND in the live runner (combo_book.ml_scores), so this is not look-ahead and was not changed; restricting ML to the main boards would be a rule change (operator's call).

## R1 confirmation on the corrected engine (1 trial)

R1 = market-wide 20-day net foreign flow < 0 -> no new trend entry, INSTEAD of IHSG < MA200 (#188). Trend sleeve alone on the engine, halves split at the median ungated entry (2024-01-16); 200 circular-shift placebos of the same mask.

| book | trades | full | half 1 | half 2 |
|---|---|---|---|---|
| trend, IHSG gate (baseline d) | 282 | 12.7 % / 1.19 / -11.6 % | 5.5 % / 0.60 / -8.3 % | 18.6 % / 1.62 / -8.9 % |
| trend, R1 gate | 215 | 11.6 % / 1.34 / -8.2 % | 7.1 % / 0.87 / -6.9 % | 15.3 % / 1.67 / -8.2 % |
| combined book, baseline d | - | 32.9 % / 1.77 / -16.9 % | 10.3 % / 0.88 / -13.3 % | 60.3 % / 2.39 / -16.9 % |
| combined book, R1 | - | 34.9 % / 1.93 / -17.4 % | 12.4 % / 1.15 / -11.1 % | 62.2 % / 2.49 / -17.4 % |

Halves 1/2 (rule: Sharpe up, mDD not deeper, CAGR >= 0.9x); placebo pct 99 (median 0.55, p95 1.06); DSR @ N 916 = 0.35. Verdict: **NOT confirmed**.

Neighbours (counted in #188, not here):

| neighbour (kind, window, thr) | trades | trend alone | passes vs baseline | combined book |
|---|---|---|---|---|
| ('mkt_instead', 10, 0.0) | 242 | 7.8 % / 0.85 / -10.1 % | no | 30.4 % / 1.72 / -16.0 % |
| ('mkt_instead', 40, 0.0) | 206 | 8.2 % / 0.97 / -9.9 % | no | 32.8 % / 1.86 / -16.7 % |
| ('mkt_instead', 20, -0.02) | 282 | 15.4 % / 1.35 / -12.2 % | no | 36.2 % / 1.87 / -17.5 % |
| ('mkt_instead', 20, 0.02) | 151 | 7.9 % / 1.21 / -7.0 % | no | 32.4 % / 1.95 / -15.6 % |
