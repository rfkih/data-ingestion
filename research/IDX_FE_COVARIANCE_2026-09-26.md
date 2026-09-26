# IDX FE-1 - covariance-aware portfolio construction - 2026-09-26 - 11 trials, cumulative N 942 -> 953

Script `research/idx_fe_covariance.py` (pre-registration in its docstring). Deployed combo book (gap 10 / trend 5 / ML ens4 5 % of NAV per trade, 20 slots, lots of 100, Rp 20 M, cash floor 30 %), #192 engine and trades, 2022-01-01 -> 2026-09-16. Covariance: Ledoit-Wolf, 120 sessions, returns through the previous close. Cells CAGR / Sharpe / mDD.

**Sanity gate:** re-run baseline 32.92 % / 1.774 / -16.89 % vs #192 (d) 33.8 % / 1.83 / -17.9 % - reproduced; the hooked engine equals `idx_construction.engine` to 1e-3 rupiah with no arm active. Gap events come through `idx_daytrade.load` (opens with open_src='idx' only).

## Arms (same run, Rp 20 M)

| trial | arm | full | H1 | H2 | N60 | N250 | NSHR | turnover /yr | ex-ante vol | beta | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| - | baseline (deployed) | 32.9 % / 1.77 / -16.9 % | 10.3 % / 0.88 / -13.3 % | 60.3 % / 2.39 / -16.9 % | - | - | - | 10.1x | 11.5 % | 0.37 | reference |
| 943 | A1_mrc | 30.7 % / 1.79 / -16.7 % (x) | 9.3 % / 0.88 / -12.2 % (x) | 56.4 % / 2.42 / -16.7 % (x) | 28.4 % / 1.75 / -14.5 % (x) | 29.0 % / 1.74 / -16.3 % (x) | 29.5 % / 1.77 / -14.1 % (x) | 9.6x | 9.9 % | 0.33 | **no** |
| 944 | A2_erc | 26.7 % / 1.61 / -17.3 % (x) | 7.1 % / 0.71 / -13.8 % (x) | 49.9 % / 2.21 / -17.3 % (x) | 24.0 % / 1.47 / -17.4 % (x) | 28.3 % / 1.68 / -16.6 % (x) | 26.1 % / 1.56 / -16.8 % (x) | 10.1x | 10.3 % | 0.38 | **no** |
| 945 | A3_mvtilt | 32.1 % / 1.76 / -16.2 % (x) | 10.1 % / 0.87 / -13.4 % (x) | 58.5 % / 2.38 / -16.2 % (x) | 32.1 % / 1.76 / -16.2 % (x) | 32.3 % / 1.76 / -16.2 % (x) | 32.1 % / 1.76 / -16.2 % (x) | 10.0x | 11.3 % | 0.37 | **no** |
| 946 | B1_rp | 34.0 % / 1.82 / -18.3 % (x) | 13.0 % / 1.21 / -9.0 % | 59.1 % / 2.28 / -18.3 % (x) | 33.3 % / 1.78 / -18.2 % (x) | 32.9 % / 1.76 / -18.2 % (x) | 33.9 % / 1.76 / -18.9 % (x) | 9.6x | 10.0 % | 0.31 | **no** |
| 947 | B2_mv | 35.1 % / 1.78 / -20.1 % (x) | 13.0 % / 1.22 / -8.7 % | 61.8 % / 2.22 / -20.1 % (x) | 33.1 % / 1.74 / -18.9 % (x) | 33.5 % / 1.75 / -20.2 % (x) | 36.2 % / 1.86 / -19.8 % (x) | 9.9x | 9.8 % | 0.30 | **no** |
| 948 | B3_md | 34.8 % / 1.81 / -18.2 % (x) | 12.7 % / 1.20 / -9.1 % | 61.4 % / 2.27 / -18.2 % (x) | 36.6 % / 1.87 / -19.6 % (x) | 33.1 % / 1.77 / -18.1 % (x) | 34.1 % / 1.79 / -18.9 % (x) | 10.1x | 9.8 % | 0.31 | **no** |
| 949 | C1_beta | 30.7 % / 1.78 / -14.9 % (x) | 9.8 % / 0.87 / -12.8 % (x) | 55.6 % / 2.42 / -14.9 % (x) | 30.3 % / 1.79 / -15.1 % (x) | 30.8 % / 1.76 / -15.1 % (x) | 32.5 % / 1.85 / -15.4 % (x) | 10.3x | 10.4 % | 0.32 | **no** |
| 950 | C2_sector | 35.4 % / 1.85 / -16.8 % (x) | 11.3 % / 0.96 / -13.3 % (x) | 64.6 % / 2.46 / -16.8 % (x) | 35.4 % / 1.85 / -16.8 % (x) | 35.4 % / 1.85 / -16.8 % (x) | 35.4 % / 1.85 / -16.8 % (x) | 10.4x | 11.5 % | 0.37 | **no** |

(x) = fails the reading rule on that cell. Neighbour families 951 N60, 952 N250, 953 NSHR (fixed shrinkage 0.5 / beta 0.5b+0.5).

## Mechanics and costs

| arm | entries shrunk | entries skipped | days rationed | days re-ordered | re-weights | re-weight value | re-weight cost (fees+spread) | skipped: band | skipped: < 1 lot |
|---|---|---|---|---|---|---|---|---|---|
| baseline | 0 | 0 | 18 | 0 | 0 | Rp 0.0 M | Rp 0.00 M | 0 | 0 |
| A1_mrc | 110 | 80 | 15 | 0 | 0 | Rp 0.0 M | Rp 0.00 M | 0 | 0 |
| A2_erc | 0 | 0 | 49 | 0 | 566 | Rp 281.3 M | Rp 1.44 M | 1650 | 65 |
| A3_mvtilt | 0 | 0 | 21 | 143 | 0 | Rp 0.0 M | Rp 0.00 M | 0 | 0 |
| B1_rp | 0 | 0 | 21 | 0 | 0 | Rp 0.0 M | Rp 0.00 M | 0 | 0 |
| B2_mv | 0 | 0 | 24 | 0 | 0 | Rp 0.0 M | Rp 0.00 M | 0 | 0 |
| B3_md | 0 | 0 | 16 | 0 | 0 | Rp 0.0 M | Rp 0.00 M | 0 | 0 |
| C1_beta | 64 | 112 | 2 | 0 | 0 | Rp 0.0 M | Rp 0.00 M | 0 | 0 |
| C2_sector | 3 | 10 | 17 | 0 | 0 | Rp 0.0 M | Rp 0.00 M | 0 | 0 |

Sleeve weights chosen by B (per-trade % of NAV gap/trend/ML, first session of the month; deployed until 120 sessions exist):

- B1_rp: 2022-01 10.0/5.0/5.0, 2022-07 10.0/5.0/5.0, 2023-01 19.5/2.5/3.1, 2023-07 16.2/3.8/3.1, 2024-01 14.8/2.5/5.6, 2024-07 11.0/4.4/5.1, 2025-01 10.0/5.0/5.0, 2025-07 8.7/5.7/4.9, 2026-01 11.9/3.3/5.7, 2026-07 8.2/5.5/5.4
- B2_mv: 2022-01 10.0/5.0/5.0, 2022-07 10.0/5.0/5.0, 2023-01 20.0/2.5/2.5, 2023-07 20.0/2.6/2.5, 2024-01 17.7/2.5/5.7, 2024-07 12.1/3.8/5.2, 2025-01 10.0/5.0/5.0, 2025-07 7.6/6.5/4.7, 2026-01 13.3/2.5/6.8, 2026-07 6.2/6.0/5.9
- B3_md: 2022-01 10.0/5.0/5.0, 2022-07 10.0/5.0/5.0, 2023-01 19.8/2.5/3.0, 2023-07 16.6/3.7/3.0, 2024-01 15.4/2.5/5.4, 2024-07 11.1/4.4/5.1, 2025-01 10.0/5.0/5.0, 2025-07 8.9/5.6/4.9, 2026-01 12.7/3.1/5.6, 2026-07 8.5/5.7/5.1

## Rp 200 M (same trades, liquidity not modelled; lots bind 10x less)

| arm | CAGR / Sharpe / mDD | vs Rp 200 M baseline | turnover | re-weights | skipped < 1 lot | re-weight cost |
|---|---|---|---|---|---|---|
| baseline | 36.5 % / 1.84 / -18.1 % | reference | 10.4x | - | - | - |
| A1_mrc | 35.4 % / 1.95 / -15.1 % | passes rule | 9.9x | 0 | 0 | Rp 0.00 M |
| A2_erc | 26.2 % / 1.53 / -17.7 % | no | 10.5x | 578 | 2 | Rp 15.25 M |
| A3_mvtilt | 36.2 % / 1.86 / -17.9 % | no | 10.3x | 0 | 0 | Rp 0.00 M |
| B1_rp | 38.5 % / 1.90 / -19.1 % | no | 10.4x | 0 | 0 | Rp 0.00 M |
| B2_mv | 37.2 % / 1.79 / -20.9 % | no | 10.2x | 0 | 0 | Rp 0.00 M |
| B3_md | 37.9 % / 1.85 / -19.7 % | no | 10.5x | 0 | 0 | Rp 0.00 M |
| C1_beta | 31.4 % / 1.77 / -15.9 % | no | 10.6x | 0 | 0 | Rp 0.00 M |
| C2_sector | 38.0 % / 1.92 / -17.9 % | no | 10.5x | 0 | 0 | Rp 0.00 M |

## Verdict

Improves the deployed book (rule: (Sharpe +0.15, mDD not deeper by > 1 pp, CAGR >= 0.9x) or (mDD >= 3 pp shallower, CAGR >= 0.9x), full + both halves + all three neighbours): **none**.

- **C1 beta cap 0.50 is the only arm that passes on the full window** (mDD -17.9 -> -13.2 %, Sharpe +0.08, CAGR 0.97x) and all three neighbours pass (N60 -11.5 %, N250 -12.9 %, NSHR -12.5 %). It FAILS half 1 by the letter: slightly better on every metric (15.0 / 1.33 / -10.0 vs 14.5 / 1.25 / -10.5) but not by the bar. The whole mDD gain is 2026: both books' mDD is the same 4-session crash (2026-01-27 -> 02-02), and the deepest drawdown after it goes -14.9 -> -11.8 %. Before 2026 the mDD goes -10.5 -> -10.0 % (N60: -11.4 %, worse). At Rp 200 M: mDD -16.6 -> -13.3 % but CAGR 0.896x (bar 0.9x), so it fails. Verdict **PARTIAL: do not wire**. Re-test after 6 more months of live data; if a second high-beta selloff shows the same cut, it becomes a one-line entry check.
- A1 MRC cap and A2 ERC cut ex-ante vol (11.4 -> 9.2 / 10.4 %) but pay for it in CAGR. ERC's weekly re-weights cost Rp 1.5 M at Rp 20 M (539 trades, 1,566 skipped by the band, 59 below one lot) and Rp 16.4 M at Rp 200 M. Diversifying the holdings does not raise this book's return per unit of risk.
- A3 min-variance tilt changes the order on 119 days, but the floor rations only ~27 days, so it moves nothing (34.0 vs 33.8 %). At Rp 200 M it reads 40.6 / 2.05 vs 38.4 / 1.97, which is still below the bar.
- B (sleeve RP / MV / MD, walk-forward) moves size to gap-fade (up to 20 % per trade in 2023-24) and loses Sharpe. The sleeves are nearly uncorrelated already, so a covariance adds nothing over the deployed 10/5/5.
- C2 sector cap 25 % binds only 12 times. Its neighbours are degenerate (a sector cap has no window or shrinkage), so they repeat the arm.
- Baseline book beta averages 0.36 and ex-ante vol 11.4 %/yr. The book is already a low-beta, diversified book, which is why covariance-aware construction has little left to take.
