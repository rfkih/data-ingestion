# IDX FE-1 - covariance-aware portfolio construction - 2026-09-26 - 11 trials, cumulative N 942 -> 953

Script `research/idx_fe_covariance.py` (pre-registration in its docstring). Deployed combo book (gap 10 / trend 5 / ML ens4 5 % of NAV per trade, 20 slots, lots of 100, Rp 20 M, cash floor 30 %), #192 engine and trades, 2022-01-01 -> 2026-09-16. Covariance: Ledoit-Wolf, 120 sessions, returns through the previous close. Cells CAGR / Sharpe / mDD.

**Sanity gate:** re-run baseline 33.76 % / 1.825 / -17.89 % vs #192 (d) 33.8 % / 1.83 / -17.9 % - reproduced; the hooked engine equals `idx_construction.engine` to 1e-3 rupiah with no arm active. Gap events come through `idx_daytrade.load` (opens with open_src='idx' only).

## Arms (same run, Rp 20 M)

| trial | arm | full | H1 | H2 | N60 | N250 | NSHR | turnover /yr | ex-ante vol | beta | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| - | baseline (deployed) | 33.8 % / 1.83 / -17.9 % | 14.5 % / 1.25 / -10.5 % | 56.4 % / 2.27 / -17.9 % | - | - | - | 10.0x | 11.4 % | 0.36 | reference |
| 943 | A1_mrc | 30.0 % / 1.85 / -15.7 % (x) | 13.5 % / 1.30 / -9.7 % (x) | 49.0 % / 2.28 / -15.7 % (x) | 33.8 % / 1.95 / -17.1 % (x) | 31.8 % / 1.89 / -15.7 % (x) | 33.7 % / 1.90 / -16.9 % (x) | 9.4x | 9.2 % | 0.31 | **no** |
| 944 | A2_erc | 28.7 % / 1.69 / -16.2 % (x) | 14.9 % / 1.41 / -11.0 % | 44.6 % / 1.97 / -16.2 % (x) | 24.9 % / 1.51 / -17.0 % (x) | 30.1 % / 1.76 / -14.6 % (x) | 28.8 % / 1.67 / -16.4 % (x) | 10.1x | 10.4 % | 0.37 | **no** |
| 945 | A3_mvtilt | 34.0 % / 1.82 / -17.7 % (x) | 14.5 % / 1.25 / -10.5 % (x) | 57.0 % / 2.26 / -17.7 % (x) | 35.4 % / 1.88 / -17.9 % (x) | 34.1 % / 1.83 / -17.6 % (x) | 34.0 % / 1.82 / -17.7 % (x) | 10.1x | 11.3 % | 0.36 | **no** |
| 946 | B1_rp | 34.1 % / 1.80 / -18.3 % (x) | 12.6 % / 1.25 / -8.1 % (x) | 59.8 % / 2.24 / -18.3 % (x) | 36.3 % / 1.92 / -18.2 % (x) | 32.1 % / 1.73 / -18.5 % (x) | 34.5 % / 1.83 / -18.0 % (x) | 9.9x | 9.9 % | 0.30 | **no** |
| 947 | B2_mv | 34.3 % / 1.77 / -17.6 % (x) | 12.6 % / 1.23 / -7.5 % (x) | 60.6 % / 2.20 / -17.6 % (x) | 33.5 % / 1.77 / -18.6 % (x) | 31.9 % / 1.70 / -18.4 % (x) | 34.9 % / 1.80 / -19.3 % (x) | 9.8x | 9.6 % | 0.29 | **no** |
| 948 | B3_md | 32.4 % / 1.72 / -18.6 % (x) | 12.6 % / 1.25 / -7.7 % (x) | 56.0 % / 2.11 / -18.6 % (x) | 35.0 % / 1.86 / -18.4 % (x) | 34.7 % / 1.84 / -18.4 % (x) | 33.8 % / 1.79 / -18.5 % (x) | 9.8x | 9.8 % | 0.30 | **no** |
| 949 | C1_beta | 32.8 % / 1.90 / -13.2 % | 15.0 % / 1.33 / -10.0 % (x) | 53.5 % / 2.34 / -13.2 % | 30.6 % / 1.84 / -11.5 % | 33.9 % / 1.95 / -12.9 % | 33.8 % / 1.96 / -12.5 % | 10.5x | 10.5 % | 0.31 | **no (halves fail)** |
| 950 | C2_sector | 34.9 % / 1.89 / -16.6 % (x) | 15.2 % / 1.30 / -10.5 % (x) | 58.3 % / 2.35 / -16.6 % (x) | 34.9 % / 1.89 / -16.6 % (x) | 34.9 % / 1.89 / -16.6 % (x) | 34.9 % / 1.89 / -16.6 % (x) | 10.0x | 11.3 % | 0.36 | **no** |

(x) = fails the reading rule on that cell. Neighbour families 951 N60, 952 N250, 953 NSHR (fixed shrinkage 0.5 / beta 0.5b+0.5).

## Mechanics and costs

| arm | entries shrunk | entries skipped | days rationed | days re-ordered | re-weights | re-weight value | re-weight cost (fees+spread) | skipped: band | skipped: < 1 lot |
|---|---|---|---|---|---|---|---|---|---|
| baseline | 0 | 0 | 27 | 0 | 0 | Rp 0.0 M | Rp 0.00 M | 0 | 0 |
| A1_mrc | 126 | 83 | 17 | 0 | 0 | Rp 0.0 M | Rp 0.00 M | 0 | 0 |
| A2_erc | 0 | 0 | 53 | 0 | 539 | Rp 311.2 M | Rp 1.47 M | 1566 | 59 |
| A3_mvtilt | 0 | 0 | 22 | 119 | 0 | Rp 0.0 M | Rp 0.00 M | 0 | 0 |
| B1_rp | 0 | 0 | 28 | 0 | 0 | Rp 0.0 M | Rp 0.00 M | 0 | 0 |
| B2_mv | 0 | 0 | 25 | 0 | 0 | Rp 0.0 M | Rp 0.00 M | 0 | 0 |
| B3_md | 0 | 0 | 29 | 0 | 0 | Rp 0.0 M | Rp 0.00 M | 0 | 0 |
| C1_beta | 51 | 133 | 1 | 0 | 0 | Rp 0.0 M | Rp 0.00 M | 0 | 0 |
| C2_sector | 3 | 9 | 26 | 0 | 0 | Rp 0.0 M | Rp 0.00 M | 0 | 0 |

Sleeve weights chosen by B (per-trade % of NAV gap/trend/ML, first session of the month; deployed until 120 sessions exist):

- B1_rp: 2022-01 10.0/5.0/5.0, 2022-07 10.0/5.0/5.0, 2023-01 19.3/2.5/3.7, 2023-07 17.7/3.6/2.6, 2024-01 14.9/2.5/5.5, 2024-07 11.1/4.3/5.2, 2025-01 10.4/4.3/5.5, 2025-07 9.0/5.6/4.9, 2026-01 11.1/3.4/6.0, 2026-07 8.7/5.8/4.9
- B2_mv: 2022-01 10.0/5.0/5.0, 2022-07 10.0/5.0/5.0, 2023-01 20.0/2.5/2.5, 2023-07 20.0/2.5/2.5, 2024-01 18.3/2.5/5.2, 2024-07 12.2/3.6/5.3, 2025-01 10.7/3.6/6.0, 2025-07 8.0/6.3/4.7, 2026-01 11.7/2.5/7.1, 2026-07 7.1/6.8/4.6
- B3_md: 2022-01 10.0/5.0/5.0, 2022-07 10.0/5.0/5.0, 2023-01 19.5/2.5/3.7, 2023-07 18.2/3.4/2.5, 2024-01 15.3/2.5/5.3, 2024-07 11.1/4.3/5.1, 2025-01 10.7/4.3/5.4, 2025-07 9.0/5.6/4.9, 2026-01 11.5/3.3/5.9, 2026-07 8.9/6.1/4.5

## Rp 200 M (same trades, liquidity not modelled; lots bind 10x less)

| arm | CAGR / Sharpe / mDD | vs Rp 200 M baseline | turnover | re-weights | skipped < 1 lot | re-weight cost |
|---|---|---|---|---|---|---|
| baseline | 38.4 % / 1.97 / -16.6 % | reference | 10.3x | - | - | - |
| A1_mrc | 32.3 % / 1.84 / -16.2 % | no | 9.8x | 0 | 0 | Rp 0.00 M |
| A2_erc | 30.1 % / 1.71 / -16.0 % | no | 10.6x | 555 | 1 | Rp 16.39 M |
| A3_mvtilt | 40.6 % / 2.05 / -16.8 % | no | 10.5x | 0 | 0 | Rp 0.00 M |
| B1_rp | 39.1 % / 1.93 / -18.9 % | no | 10.5x | 0 | 0 | Rp 0.00 M |
| B2_mv | 38.0 % / 1.84 / -19.8 % | no | 10.2x | 0 | 0 | Rp 0.00 M |
| B3_md | 39.3 % / 1.92 / -19.5 % | no | 10.6x | 0 | 0 | Rp 0.00 M |
| C1_beta | 34.4 % / 1.92 / -13.3 % | no | 10.8x | 0 | 0 | Rp 0.00 M |
| C2_sector | 38.3 % / 1.97 / -16.2 % | no | 10.4x | 0 | 0 | Rp 0.00 M |

## Verdict

Improves the deployed book (rule: (Sharpe +0.15, mDD not deeper by > 1 pp, CAGR >= 0.9x) or (mDD >= 3 pp shallower, CAGR >= 0.9x), full + both halves + all three neighbours): **none**.

- **C1 beta cap 0.50 is the only arm that passes on the full window** (mDD -17.9 -> -13.2 %, Sharpe +0.08, CAGR 0.97x) and all three neighbours pass (N60 -11.5 %, N250 -12.9 %, NSHR -12.5 %). It FAILS half 1 by the letter: slightly better on every metric (15.0 / 1.33 / -10.0 vs 14.5 / 1.25 / -10.5) but not by the bar. The whole mDD gain is 2026: both books' mDD is the same 4-session crash (2026-01-27 -> 02-02), and the deepest drawdown after it goes -14.9 -> -11.8 %. Before 2026 the mDD goes -10.5 -> -10.0 % (N60: -11.4 %, worse). At Rp 200 M: mDD -16.6 -> -13.3 % but CAGR 0.896x (bar 0.9x), so it fails. Verdict **PARTIAL: do not wire**. Re-test after 6 more months of live data; if a second high-beta selloff shows the same cut, it becomes a one-line entry check.
- A1 MRC cap and A2 ERC cut ex-ante vol (11.4 -> 9.2 / 10.4 %) but pay for it in CAGR. ERC's weekly re-weights cost Rp 1.5 M at Rp 20 M (539 trades, 1,566 skipped by the band, 59 below one lot) and Rp 16.4 M at Rp 200 M. Diversifying the holdings does not raise this book's return per unit of risk.
- A3 min-variance tilt changes the order on 119 days, but the floor rations only ~27 days, so it moves nothing (34.0 vs 33.8 %). At Rp 200 M it reads 40.6 / 2.05 vs 38.4 / 1.97, which is still below the bar.
- B (sleeve RP / MV / MD, walk-forward) moves size to gap-fade (up to 20 % per trade in 2023-24) and loses Sharpe. The sleeves are nearly uncorrelated already, so a covariance adds nothing over the deployed 10/5/5.
- C2 sector cap 25 % binds only 12 times. Its neighbours are degenerate (a sector cap has no window or shrinkage), so they repeat the arm.
- Baseline book beta averages 0.36 and ex-ante vol 11.4 %/yr. The book is already a low-beta, diversified book, which is why covariance-aware construction has little left to take.
