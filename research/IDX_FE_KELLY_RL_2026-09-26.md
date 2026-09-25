# IDX menu FE-3 - capital per strategy: Bayesian shrinkage + fractional Kelly vs RL-1 - 2026-09-26 - 7 trials (RL-1 961, Kelly 962..967), cumulative N = 967

Streams: RL-1's four daily sleeve streams from the same run (corrected engine #192, pit board, IDX-only opens), 2022-01-04 -> 2026-09-16. Walk-forward test 2024-2026 stitched (2024-01-02 -> 2026-09-16, 639 days). Script `research/idx_fe_kelly.py`; RL-1 run copy `research/idx_rl_alloc_run.py` (deviations: corrected engine, N 865 -> 960, streams dumped; design untouched).

## 1. Planning numbers - posterior expected return per sleeve (full stream, quote these instead of the raw backtest)

Prior N(0, tau^2), tau = 18.5% (EB, floor 5%); se inflated by episodes (k_ep), DSR @ N 967 (k_dsr = 1/max(DSR, 0.25)), placebo (k_plc). Stream sizing = RL-1's (gap 20 %/event, trend 10 %, ML 10 %, value full); the haircut is scale-free, so the last column applies it to the deployed-size sleeve-alone CAGR.

| sleeve | raw mean/yr | vol | Sharpe | active days by year | T_eff / T (yrs) | k_ep | DSR | k_dsr | placebo | se_eff | shrink B | **posterior mean/yr** | haircut | grand-mean prior (sens.) | deployed-size raw -> planning |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gap | +26.3% | 19.1% | 1.37 | 3 / 5 / 13 / 57 / 58 | 2.71 / 4.49 | 1.66 | 0.81 | 1.23 | 100 (#86/#89) | 12.9% | 0.33 | **+17.7%** | -33% | +24.7% | 12.8% -> **8.6%** (#192 gap alone) |
| trend | +19.4% | 20.7% | 0.94 | 245 / 231 / 236 / 183 / 73 | 4.51 / 4.49 | 1.00 | 0.10 | 4.00 | 99 (#63) | 19.5% | 0.53 | **+9.2%** | -53% | +24.7% | 12.7% -> **6.0%** (#192 trend alone (d)) |
| ML | +33.2% | 23.3% | 1.43 | 235 / 235 / 198 / 236 / 164 | 4.91 / 4.49 | 1.00 | 0.43 | 2.35 | 100 (ML-6g) | 16.8% | 0.45 | **+18.2%** | -45% | +24.7% | 9.8% -> **5.4%** (#192 ML ens4 alone) |
| value | +17.6% | 17.8% | 0.99 | 245 / 239 / 237 / 236 / 166 | 4.92 / 4.49 | 1.00 | 0.12 | 4.00 | 100 (#66) | 16.8% | 0.45 | **+9.7%** | -45% | +24.7% | 21.8% -> **11.9%** (#66 value strict) |

Sensitivity prior centre (grand mean, DerSimonian-Laird): +24.7%/yr.

### 1b. Planning drawdown of the deployed combo (added 2026-09-26; measurement, not a trial)

Quote this next to the planning return: the planning drawdown is DEEPER than the backtest, not shallower. Script
`research/idx_fe_drawdown.py` (rebuilds the #192 corrected combo NAV without writing a study row, then bootstraps it).
- Source: #192 variant (d) daily NAV, 2022-01 -> 2026-09-16, reproduced exactly: CAGR 33.8 %, Sharpe 1.83, realised mDD -17.9 %,
  daily-return vol 17.3 %/yr (mean of daily log returns annualises to 34.8 %).
- Planning CAGR of the combo = backtest x (8.6 + 6.0 + 5.4) / (12.8 + 12.7 + 9.8), the deployed-size posterior/raw ratio of the
  three sleeves above = **~19.7 %/yr**.
- Method: stationary block bootstrap (20-day blocks, 4,000 paths, seed 7) of the demeaned daily log returns re-drifted to the
  stated CAGR; the maximum drawdown of each path.

| drift | horizon | median | 1-in-4 | 1-in-10 | 1-in-20 |
|---|---|---|---|---|---|
| backtest (34.8 %) | 1 y | -10.1 % | -15.3 % | -17.9 % | -19.6 % |
| backtest | 3 y | -17.5 % | -18.1 % | -21.0 % | -23.2 % |
| backtest | 5 y | -17.9 % | -19.9 % | -22.8 % | -24.7 % |
| **planning (19.7 %)** | **1 y** | **-12.1 %** | **-17.7 %** | **-19.8 %** | **-22.1 %** |
| **planning** | **3 y** | **-18.2 %** | **-21.9 %** | **-26.0 %** | **-28.9 %** |
| **planning** | **5 y** | **-20.5 %** | **-24.5 %** | **-28.8 %** | **-31.7 %** |
| zero edge | 1 y | -18.2 % | -22.2 % | -27.1 % | -30.4 % |
| zero edge | 3 y | -28.7 % | -35.6 % | -42.4 % | -46.7 % |
| zero edge | 5 y | -35.4 % | -43.7 % | -51.7 % | -56.2 % |

**Planning numbers for the combo: return ~+20 %/yr, normal worst drawdown -20..-25 % over a few years, -30 % possible.**
Reading:
- The survive-one-year rule (never past -25 %) is breached in year 1 in < 5 % of planning paths.
- A drawdown past about -30 % is far more likely with zero edge than with the planning edge. It is the review trigger (stop
  adding capital, re-examine), not a buy-the-dip signal.
- Caveats: the bootstrap only reshuffles 2022-26, which has no 2020-style crash, and it breaks up volatility clustering
  beyond 20 days. FE-4's COVID replay of the invested value book was -43 %; the combo (>= 30 % cash, beta ~0.36-0.4) would
  plausibly lose roughly -20..-30 % in such a crash. That figure is a judgement, not a measurement.

## 2. Walk-forward fits (each on weeks before Jan 1 of the test year)

- **2024** (103 training weeks, LW shrinkage 0.18): mu unshrunk {'gap': -0.0085, 'trend': 0.0717, 'ML': 0.2293, 'value': 0.1117}, shrunk {'gap': -0.0076, 'trend': 0.0022, 'ML': 0.0131, 'value': 0.0044}, B {'gap': 0.107, 'trend': 0.969, 'ML': 0.943, 'value': 0.961}, T_eff {'gap': 1.88, 'trend': 2.0, 'ML': 2.0, 'value': 2.0}, DSR {'gap': 0.0, 'trend': 0.003, 'ML': 0.198, 'value': 0.01}; full Kelly unshrunk {'gap': 0.0, 'trend': 0.437, 'ML': 8.517, 'value': 1.875}, shrunk {'gap': 0.0, 'trend': 0.0, 'ML': 0.504, 'value': 0.045}; held weights (cap 70%): full_shrunk {'gap': 0.0, 'trend': 0.0, 'ML': 0.504, 'value': 0.045}; half_shrunk {'gap': 0.0, 'trend': 0.0, 'ML': 0.252, 'value': 0.023}; quarter_shrunk {'gap': 0.0, 'trend': 0.0, 'ML': 0.126, 'value': 0.011}; full_unshrunk {'gap': 0.0, 'trend': 0.028, 'ML': 0.551, 'value': 0.121}; half_unshrunk {'gap': 0.0, 'trend': 0.028, 'ML': 0.551, 'value': 0.121}; quarter_unshrunk {'gap': 0.0, 'trend': 0.028, 'ML': 0.551, 'value': 0.121}
- **2025** (154 training weeks, LW shrinkage 0.13): mu unshrunk {'gap': 0.0153, 'trend': 0.0357, 'ML': 0.2548, 'value': 0.1156}, shrunk {'gap': 0.0034, 'trend': 0.0018, 'ML': 0.0383, 'value': 0.0069}, B {'gap': 0.776, 'trend': 0.951, 'ML': 0.85, 'value': 0.94}, T_eff {'gap': 2.17, 'trend': 3.0, 'ML': 2.98, 'value': 3.0}, DSR {'gap': 0.003, 'trend': 0.002, 'ML': 0.49, 'value': 0.021}; full Kelly unshrunk {'gap': 0.458, 'trend': 0.0, 'ML': 10.707, 'value': 2.765}, shrunk {'gap': 0.26, 'trend': 0.0, 'ML': 1.654, 'value': 0.043}; held weights (cap 70%): full_shrunk {'gap': 0.093, 'trend': 0.0, 'ML': 0.592, 'value': 0.015}; half_shrunk {'gap': 0.093, 'trend': 0.0, 'ML': 0.592, 'value': 0.015}; quarter_shrunk {'gap': 0.065, 'trend': 0.0, 'ML': 0.414, 'value': 0.011}; full_unshrunk {'gap': 0.023, 'trend': 0.0, 'ML': 0.538, 'value': 0.139}; half_unshrunk {'gap': 0.023, 'trend': 0.0, 'ML': 0.538, 'value': 0.139}; quarter_unshrunk {'gap': 0.023, 'trend': 0.0, 'ML': 0.538, 'value': 0.139}
- **2026** (205 training weeks, LW shrinkage 0.20): mu unshrunk {'gap': 0.133, 'trend': 0.2375, 'ML': 0.3213, 'value': 0.1387}, shrunk {'gap': 0.0908, 'trend': 0.0968, 'ML': 0.2394, 'value': 0.0705}, B {'gap': 0.317, 'trend': 0.592, 'ML': 0.255, 'value': 0.492}, T_eff {'gap': 1.76, 'trend': 3.95, 'ML': 3.98, 'value': 4.0}, DSR {'gap': 0.616, 'trend': 0.164, 'ML': 0.758, 'value': 0.055}; full Kelly unshrunk {'gap': 6.114, 'trend': 3.843, 'ML': 8.496, 'value': 1.663}, shrunk {'gap': 4.146, 'trend': 1.386, 'ML': 6.694, 'value': 0.34}; held weights (cap 70%): full_shrunk {'gap': 0.231, 'trend': 0.077, 'ML': 0.373, 'value': 0.019}; half_shrunk {'gap': 0.231, 'trend': 0.077, 'ML': 0.373, 'value': 0.019}; quarter_shrunk {'gap': 0.231, 'trend': 0.077, 'ML': 0.373, 'value': 0.019}; full_unshrunk {'gap': 0.213, 'trend': 0.134, 'ML': 0.296, 'value': 0.058}; half_unshrunk {'gap': 0.213, 'trend': 0.134, 'ML': 0.296, 'value': 0.058}; quarter_unshrunk {'gap': 0.213, 'trend': 0.134, 'ML': 0.296, 'value': 0.058}

## 3. Head to head (stitched test window, same run)

| allocator | CAGR | Sharpe | mDD | 2024 | 2025 | 2026 | RANDOM pct | verdict |
|---|---|---|---|---|---|---|---|---|
| FIXED_EQ (best baseline) | +40.1% | 2.38 | -11.9% | +12% | +70% | +24% | 100 | - |
| REGIME | +30.1% | 2.22 | -11.9% | +11% | +52% | +16% | 99 | - |
| WF_BEST | +42.5% | 1.97 | -16.8% | +20% | +73% | +19% | 92 | - |
| DEPLOYED (reported, not in the rule) | +58.5% | 2.29 | -17.9% | +15% | +117% | +31% | 100 | - |
| RL-1 (seed mean; range 1.22..1.56) | +18.8% | 1.46 | -12.8% | +7% | +33% | +10% | 44 | NOT better (sharpe n, cagr n, mdd y, seeds n, random n) |
| Kelly full_shrunk | +32.2% | 1.91 | -13.1% | +17% | +46% | +20% | 88 | NOT better (sharpe n, cagr n, mdd y, random n) |
| Kelly half_shrunk | +28.3% | 1.76 | -13.1% | +8% | +46% | +20% | 74 | NOT better (sharpe n, cagr n, mdd y, random n) |
| Kelly quarter_shrunk | +21.5% | 1.55 | -11.7% | +4% | +33% | +20% | 52 | NOT better (sharpe n, cagr n, mdd y, random n) |
| Kelly full_unshrunk | +30.6% | 1.95 | -13.4% | +19% | +40% | +18% | 90 | NOT better (sharpe n, cagr n, mdd y, random n) |
| Kelly half_unshrunk | +30.6% | 1.95 | -13.4% | +19% | +40% | +18% | 90 | NOT better (sharpe n, cagr n, mdd y, random n) |
| Kelly quarter_unshrunk | +30.6% | 1.95 | -13.4% | +19% | +40% | +18% | 90 | NOT better (sharpe n, cagr n, mdd y, random n) |

RANDOM (200 weekly-random templates): Sharpe median 1.52, p95 2.05. WF_BEST picks {2024: 'ML', 2025: 'ML', 2026: 'ML'}. Deployed combo full span on this run: +33.8% / 1.83 / -17.9%.

## Verdict (pre-registered, RL-1's rule)

Best baseline FIXED_EQ (+40.1% / 2.38 / -11.9%); bar Sharpe >= 2.53, CAGR >= +34.1%, mDD >= -13.9%, Sharpe >= RANDOM p95 2.05. Kelly arms BETTER: **0/6**.

## Reading (written after the run)

1. **RL-1 is not given capital** (study #196, trial 961): seed-mean 18.8 % / 1.46 / -12.8 % vs FIXED_EQ 40.1 % / 2.38 / -11.9 %; every seed
   (1.22..1.56) is below the RANDOM median (1.52). The agent learned to sit in OFF/DEF and TREND (the weakest stream at this sizing) - 26 weeks
   x 2-3 training years is too little signal for a policy gradient. Deviations from its pre-registration: corrected engine (#192: trend
   replay fix, pit board via tmp/exit_cache_pit.pkl), N 865 -> 960, streams dumped for FE-3. The gap stream already goes through
   idx_daytrade.load (IDX-sourced opens only, `elig & open_src == 'idx'`), so no filter was added.
2. **Kelly: 0/6 pass.** The 70 % cash-floor cap binds on every unshrunk fit (full Kelly asks for 8-11x in ML), so full/half/quarter
   unshrunk are the same book - Kelly only chose the MIX, and the mix it chose (ML-heavy, 54-55 %) lost to plain equal weights.
   Shrinkage moved the 2024-25 fits to near-cash (B 0.85-0.97 on 2-3 years of data, DSR ~0 at N 967) and cost return in 2025.
   Nothing beats FIXED_EQ, and FIXED_EQ's 2.38 is itself inside the window where every sleeve was strong.
3. **The deployed combo (58.5 % / 2.29 / -17.9 % on the same 2024-26 days) is not beaten by any allocator here**; the question
   "how much per strategy" is answered by keeping the construction as it is. Equal weight across sleeves is the right default
   when the means cannot be told apart, and after shrinkage they cannot: posterior means 9-18 %/yr with se_eff 13-20 %.
4. **Planning numbers** (section 1): quote the posterior column, not the raw backtest. The haircut is 33-53 %. Caveats: the gap
   haircut is the SMALLEST (33 %) despite 93 % of events in 2025-26, because its DSR is high (0.81, a positively skewed sparse
   stream); k_ep captures only its concentration by year (T_eff 2.7 of 4.5 yrs). Value's T_eff counts days, not its 5 annual
   cohorts, so its evidence is overstated here. All four placebo percentiles are >= 99, so the placebo factor did not
   differentiate. The deployed-size column scales #192/#66 sleeve-alone CAGRs by (1 - B); treat it as a planning figure, not a backtest.
