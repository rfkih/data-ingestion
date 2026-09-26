# IDX menu 29e — threshold, slots, selection and the ARB floor — 2020-09-08 -> 2026-09-21

IDX-sourced opens only, 110816 gap-down name-days before any threshold. Pre-registered in
`research/idx_gapfade_tune.py`; 8 trials (cumulative 566). The deployed rule is the reference row.

| arm | events | capital | mean | median | hit | closed at ARB | total | CAGR | Sharpe | max DD | worst trade | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| deployed: -7 %, K=5, deepest | 202 | 5.6 % | **+329** | +100 | 54 % | 3.0 % | +254 % | +57 % | 5.71 | -8.3 % | -17 % | reference |
| A. room >= 8% above ARB | 189 | 5.2 % | **+323** | +147 | 57 % | 2.1 % | +220 % | +52 % | 5.75 | -8.2 % | -17 % | no |
| B. gap -5 %, K=5 | 364 | 4.6 % | **+231** | +43 | 53 % | 1.9 % | +389 % | +30 % | 4.58 | -14.0 % | -17 % | no |
| B. gap -5 %, K=10 | 450 | 2.9 % | **+255** | +72 | 53 % | 1.6 % | +200 % | +20 % | 4.19 | -7.8 % | -17 % | no |
| B. gap -7 %, K=10 | 255 | 3.5 % | **+357** | +105 | 55 % | 2.4 % | +139 % | +37 % | 5.16 | -4.2 % | -17 % | no |
| B. gap -10 %, K=5 | 128 | 5.5 % | **+437** | +100 | 54 % | 4.7 % | +190 % | +81 % | 6.73 | -7.6 % | -17 % | no |
| B. gap -10 %, K=10 | 163 | 3.5 % | **+472** | +95 | 53 % | 3.7 % | +109 % | +51 % | 5.95 | -3.8 % | -17 % | no |
| C. most liquid first | 202 | 5.6 % | **+286** | +45 | 53 % | 3.0 % | +195 % | +47 % | 4.61 | -8.3 % | -17 % | no |

## Reading

- Passing the bar: none.
- BETTER needs Sharpe >= deployed + 0.3, no deeper drawdown and no less total return; a risk rule needs a
  drawdown at least 3 points shallower for no more than a tenth of the return.
