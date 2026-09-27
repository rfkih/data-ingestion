# IDX menu CB-1 — the C0 radar wide sleeve inside the live combined book — 2026-09-27 — study #408

Script `research/idx_combo_c0w.py` (pre-registered); robustness `research-scratch/idx/filterlab/combo_robust.py` (declared after the
verdict, before its numbers). Engine = the deployed combo exactly as #386 (idx_alloc_frontier.engine, Rp 20 m, cash floor 30 %,
gap 10 % / trend 5 % / ML ens4 10 % with the 5 % stop), 2022-01 -> 2026-09-16. C0W = every C0 flag with 20-day value < Rp 50 bn
(FL-2 #407), stop -15 % / trail 25 %, queued after trend and ML entries. **3 trials; cumulative N 1103 -> 1106. K1 and K3 BETTER by
the letter; robustness says the gain is real in direction but smaller than the headline and not statistically significant.**

| book | cap | CAGR | Sharpe | mDD | Sharpe H1 / H2 | ex-2025 CAGR / Sharpe | invested | by year | verdict |
|---|---|---|---|---|---|---|---|---|---|
| REF as deployed (reproduces #386) | 20 | 48.7 % | 2.15 | -18.0 % | 1.53 / 2.62 | 26.1 % / 1.25 | 45 % | 22 +10, 23 +26, 24 +26, 25 +185, 26 +30 | reference |
| REF40 | 40 | 50.3 % | 2.14 | -18.9 % | 1.52 / 2.62 | 26.0 % / 1.22 | 46 % | | reference |
| **K1 ADD C0W 1.25 %** | 40 | **55.7 %** | **2.38** | -21.5 % | 1.80 / 2.85 | **34.0 % / 1.53** | 58 % | 22 +21, 23 +34, 24 +34, 25 +187, 26 +29 | BETTER |
| K2 ADD C0W 0.625 % | 40 | 44.9 % | 2.08 | -19.1 % | 1.55 / 2.50 | 28.1 % / 1.35 | 52 % | | no |
| **K3 REPLACE trend by C0W** | 40 | 49.5 % | 2.26 | -21.4 % | 1.80 / 2.66 | 31.6 % / 1.49 | 49 % | 22 +12, 23 +25, 24 +42, 25 +152, 26 +32 | BETTER |

Per sleeve (K1): ML 538 trades Rp +45.4 m, C0W 400 trades Rp +44.7 m (avg +18.5 %), gap 145 Rp +35.3 m, trend 154 Rp +15.1 m. C0W
crowds out part of ML and trend (753 -> 538 ML trades) through the shared cash floor and position cap.

## Robustness (not trials)

| variant | CAGR | Sharpe | mDD | ex-2025 CAGR / Sharpe |
|---|---|---|---|---|
| K1 1.25 % (as tested) | 55.7 % | 2.38 | -21.5 % | 34.0 % / 1.53 |
| K1 1.00 % | 48.4 % | 2.19 | -21.3 % | 30.8 % / 1.44 |
| K1 1.50 % | 50.3 % | 2.23 | -22.1 % | 32.1 % / 1.49 |
| K1 UNCAPPED C0 (no FL-2 filter) | 50.1 % | 2.21 | -21.7 % | 28.2 % / 1.33 |
| K3 UNCAPPED | 47.1 % | 2.19 | -21.2 % | 28.1 % / 1.38 |

Daily excess K1 - REF: +4.9 %/yr, t 1.08, IR 0.51, positive in 56 % of 57 months, correlation 0.89; by year +9.1 / +6.5 / +5.9 /
+0.5 / -0.1 pp (2022..2026).

## Reading

1. **Direction robust, size not.** Every variant beats REF on Sharpe and - the part that matters - on the years WITHOUT 2025
   (ex-2025 Sharpe 1.33-1.53 vs 1.25; 2022-24 +6..+9 pp a year). 1.25 % is the lucky peak of its neighbours (2.19-2.23): expect
   roughly +0.05..+0.2 Sharpe and a few points of CAGR, not +7 points.
2. **The FL-2 cap was chosen on 2024-26 data inside this window**, so part of K1's edge over the uncapped version (2.38 vs 2.21)
   is in-sample.
3. **The price is drawdown**: -21..-22 % vs -18 %, and more positions (+85 trades a year).
4. The excess is not statistically significant (t 1.08) and a forward test cannot settle it quickly (IR 0.51 -> ~15 years for
   t 2). The case for adding it is diversification in non-mania years, supported by the whole chain SX-1 -> RB-2 -> FL-2 -> CB-1.
Proposal: run K1 (1.0-1.25 %, cap 40) as the PAPER combo next to the live one; judge "consistent with backtest", not "beats REF".
