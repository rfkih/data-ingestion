# IDX menu FE-3 - capital per strategy: Bayesian shrinkage + fractional Kelly vs RL-1 - 2026-09-26 - 7 trials (RL-1 961, Kelly 962..967), cumulative N = 967

Streams: RL-1's four daily sleeve streams from the same run (corrected engine #192, pit board, IDX-only opens), 2022-01-04 -> 2026-09-16. Walk-forward test 2024-2026 stitched (2024-01-02 -> 2026-09-16, 639 days). Script `research/idx_fe_kelly.py`; RL-1 run copy `research/idx_rl_alloc_run.py` (deviations: corrected engine, N 865 -> 960, streams dumped; design untouched).

## 1. Planning numbers - posterior expected return per sleeve (full stream, quote these instead of the raw backtest)

Prior N(0, tau^2), tau = 15.4% (EB, floor 5%); se inflated by episodes (k_ep), DSR @ N 967 (k_dsr = 1/max(DSR, 0.25)), placebo (k_plc). Stream sizing = RL-1's (gap 20 %/event, trend 10 %, ML 10 %, value full); the haircut is scale-free, so the last column applies it to the deployed-size sleeve-alone CAGR.

| sleeve | raw mean/yr | vol | Sharpe | active days by year | T_eff / T (yrs) | k_ep | DSR | k_dsr | placebo | se_eff | shrink B | **posterior mean/yr** | haircut | grand-mean prior (sens.) | deployed-size raw -> planning |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gap | +26.3% | 19.1% | 1.37 | 3 / 5 / 13 / 57 / 58 | 2.71 / 4.49 | 1.66 | 0.81 | 1.23 | 100 (#86/#89) | 12.9% | 0.41 | **+15.4%** | -41% | +23.4% | 12.8% -> **7.5%** (#192 gap alone) |
| trend | +19.4% | 20.7% | 0.94 | 245 / 231 / 236 / 183 / 73 | 4.51 / 4.49 | 1.00 | 0.10 | 4.00 | 99 (#63) | 19.5% | 0.62 | **+7.4%** | -62% | +23.4% | 12.7% -> **4.9%** (#192 trend alone (d)) |
| ML | +29.3% | 23.6% | 1.24 | 232 / 200 / 213 / 236 / 164 | 4.92 / 4.49 | 1.00 | 0.27 | 3.70 | 100 (ML-6g) | 21.4% | 0.66 | **+10.0%** | -66% | +23.4% | 9.8% -> **3.3%** (#192 ML ens4 alone) |
| value | +17.6% | 17.8% | 0.99 | 245 / 239 / 237 / 236 / 166 | 4.92 / 4.49 | 1.00 | 0.12 | 4.00 | 100 (#66) | 16.8% | 0.54 | **+8.0%** | -54% | +23.4% | 21.8% -> **9.9%** (#66 value strict) |

Sensitivity prior centre (grand mean, DerSimonian-Laird): +23.4%/yr.

## 2. Walk-forward fits (each on weeks before Jan 1 of the test year)

- **2024** (103 training weeks, LW shrinkage 0.17): mu unshrunk {'gap': np.float64(-0.0085), 'trend': np.float64(0.0717), 'ML': np.float64(0.1031), 'value': np.float64(0.1117)}, shrunk {'gap': np.float64(-0.0076), 'trend': np.float64(0.0022), 'ML': np.float64(0.005), 'value': np.float64(0.0044)}, B {'gap': 0.107, 'trend': 0.969, 'ML': 0.951, 'value': 0.961}, T_eff {'gap': 1.88, 'trend': 2.0, 'ML': 1.99, 'value': 2.0}, DSR {'gap': 0.0, 'trend': 0.003, 'ML': 0.011, 'value': 0.01}; full Kelly unshrunk {'gap': np.float64(0.0), 'trend': np.float64(0.66), 'ML': np.float64(3.1), 'value': np.float64(2.902)}, shrunk {'gap': np.float64(0.0), 'trend': np.float64(0.007), 'ML': np.float64(0.163), 'value': np.float64(0.111)}; held weights (cap 70%): full_shrunk {'gap': np.float64(0.0), 'trend': np.float64(0.007), 'ML': np.float64(0.163), 'value': np.float64(0.111)}; half_shrunk {'gap': np.float64(0.0), 'trend': np.float64(0.004), 'ML': np.float64(0.081), 'value': np.float64(0.056)}; quarter_shrunk {'gap': np.float64(0.0), 'trend': np.float64(0.002), 'ML': np.float64(0.041), 'value': np.float64(0.028)}; full_unshrunk {'gap': np.float64(0.0), 'trend': np.float64(0.069), 'ML': np.float64(0.326), 'value': np.float64(0.305)}; half_unshrunk {'gap': np.float64(0.0), 'trend': np.float64(0.069), 'ML': np.float64(0.326), 'value': np.float64(0.305)}; quarter_unshrunk {'gap': np.float64(0.0), 'trend': np.float64(0.069), 'ML': np.float64(0.326), 'value': np.float64(0.305)}
- **2025** (154 training weeks, LW shrinkage 0.13): mu unshrunk {'gap': np.float64(0.0153), 'trend': np.float64(0.0357), 'ML': np.float64(0.1863), 'value': np.float64(0.1156)}, shrunk {'gap': np.float64(0.0034), 'trend': np.float64(0.0018), 'ML': np.float64(0.0124), 'value': np.float64(0.0069)}, B {'gap': 0.776, 'trend': 0.951, 'ML': 0.933, 'value': 0.94}, T_eff {'gap': 2.17, 'trend': 3.0, 'ML': 2.99, 'value': 3.0}, DSR {'gap': 0.003, 'trend': 0.002, 'ML': 0.128, 'value': 0.021}; full Kelly unshrunk {'gap': np.float64(1.594), 'trend': np.float64(0.0), 'ML': np.float64(6.909), 'value': np.float64(3.402)}, shrunk {'gap': np.float64(0.58), 'trend': np.float64(0.0), 'ML': np.float64(0.443), 'value': np.float64(0.204)}; held weights (cap 70%): full_shrunk {'gap': np.float64(0.331), 'trend': np.float64(0.0), 'ML': np.float64(0.253), 'value': np.float64(0.116)}; half_shrunk {'gap': np.float64(0.29), 'trend': np.float64(0.0), 'ML': np.float64(0.221), 'value': np.float64(0.102)}; quarter_shrunk {'gap': np.float64(0.145), 'trend': np.float64(0.0), 'ML': np.float64(0.111), 'value': np.float64(0.051)}; full_unshrunk {'gap': np.float64(0.094), 'trend': np.float64(0.0), 'ML': np.float64(0.406), 'value': np.float64(0.2)}; half_unshrunk {'gap': np.float64(0.094), 'trend': np.float64(0.0), 'ML': np.float64(0.406), 'value': np.float64(0.2)}; quarter_unshrunk {'gap': np.float64(0.094), 'trend': np.float64(0.0), 'ML': np.float64(0.406), 'value': np.float64(0.2)}
- **2026** (205 training weeks, LW shrinkage 0.17): mu unshrunk {'gap': np.float64(0.133), 'trend': np.float64(0.2375), 'ML': np.float64(0.3141), 'value': np.float64(0.1387)}, shrunk {'gap': np.float64(0.0871), 'trend': np.float64(0.0896), 'ML': np.float64(0.1957), 'value': np.float64(0.0661)}, B {'gap': 0.345, 'trend': 0.623, 'ML': 0.377, 'value': 0.524}, T_eff {'gap': 1.76, 'trend': 3.95, 'ML': 3.98, 'value': 4.0}, DSR {'gap': 0.616, 'trend': 0.164, 'ML': 0.592, 'value': 0.055}; full Kelly unshrunk {'gap': np.float64(6.307), 'trend': np.float64(2.778), 'ML': np.float64(7.874), 'value': np.float64(2.779)}, shrunk {'gap': np.float64(4.209), 'trend': np.float64(0.597), 'ML': np.float64(5.267), 'value': np.float64(1.202)}; held weights (cap 70%): full_shrunk {'gap': np.float64(0.261), 'trend': np.float64(0.037), 'ML': np.float64(0.327), 'value': np.float64(0.075)}; half_shrunk {'gap': np.float64(0.261), 'trend': np.float64(0.037), 'ML': np.float64(0.327), 'value': np.float64(0.075)}; quarter_shrunk {'gap': np.float64(0.261), 'trend': np.float64(0.037), 'ML': np.float64(0.327), 'value': np.float64(0.075)}; full_unshrunk {'gap': np.float64(0.224), 'trend': np.float64(0.099), 'ML': np.float64(0.279), 'value': np.float64(0.099)}; half_unshrunk {'gap': np.float64(0.224), 'trend': np.float64(0.099), 'ML': np.float64(0.279), 'value': np.float64(0.099)}; quarter_unshrunk {'gap': np.float64(0.224), 'trend': np.float64(0.099), 'ML': np.float64(0.279), 'value': np.float64(0.099)}

## 3. Head to head (stitched test window, same run)

| allocator | CAGR | Sharpe | mDD | 2024 | 2025 | 2026 | RANDOM pct | verdict |
|---|---|---|---|---|---|---|---|---|
| FIXED_EQ (best baseline) | +41.1% | 2.44 | -13.1% | +13% | +77% | +21% | 100 | - |
| REGIME | +31.6% | 2.36 | -10.3% | +12% | +56% | +15% | 100 | - |
| WF_BEST | +53.1% | 2.41 | -11.9% | +13% | +88% | +40% | 100 | - |
| DEPLOYED (reported, not in the rule) | +61.5% | 2.39 | -16.9% | +16% | +129% | +28% | 100 | - |
| RL-1 (seed mean; range 1.13..1.42) | +16.4% | 1.25 | -15.1% | +6% | +28% | +9% | 14 | NOT better (sharpe n, cagr n, mdd n, seeds n, random n) |
| Kelly full_shrunk | +27.4% | 2.06 | -13.7% | +7% | +46% | +18% | 92 | NOT better (sharpe n, cagr n, mdd y, random n) |
| Kelly half_shrunk | +23.6% | 1.88 | -13.7% | +4% | +40% | +18% | 82 | NOT better (sharpe n, cagr n, mdd y, random n) |
| Kelly quarter_shrunk | +15.6% | 1.42 | -13.7% | +2% | +20% | +18% | 28 | NOT better (sharpe n, cagr n, mdd y, random n) |
| Kelly full_unshrunk | +30.5% | 2.11 | -12.2% | +16% | +47% | +16% | 94 | NOT better (sharpe n, cagr n, mdd y, random n) |
| Kelly half_unshrunk | +30.5% | 2.11 | -12.2% | +16% | +47% | +16% | 94 | NOT better (sharpe n, cagr n, mdd y, random n) |
| Kelly quarter_unshrunk | +30.5% | 2.11 | -12.2% | +16% | +47% | +16% | 94 | NOT better (sharpe n, cagr n, mdd y, random n) |

RANDOM (200 weekly-random templates): Sharpe median 1.58, p95 2.13. WF_BEST picks {2024: 'VALUE', 2025: 'ML', 2026: 'GAP'}. Deployed combo full span on this run: +32.9% / 1.77 / -16.9%.

## Verdict (pre-registered, RL-1's rule)

Best baseline FIXED_EQ (+41.1% / 2.44 / -13.1%); bar Sharpe >= 2.59, CAGR >= +35.0%, mDD >= -15.1%, Sharpe >= RANDOM p95 2.13. Kelly arms BETTER: **0/6**.
