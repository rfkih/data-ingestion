# Phase 1 - why the gap-down fade pays - 2026-09-26

Deployed gap-fade trades of #348 (231, 2022-01-12 -> 2026-09-14), return per trade after fees. Descriptive audit, no trial.
Buckets with n < 15 are shown but not read.

All: n 231, mean +2.62 %, median -0.03 %, hit 49 %. 2022-24: n 20 mean +1.20 %; 2025-26: n 211 mean +2.76 %

## panic open (COMPOSITE open <= -1 %)

| bucket | n | mean | median | hit | 2022-24 n / mean | 2025-26 n / mean |
|---|---|---|---|---|---|---|
| normal open | 175 | +3.25 % | +0.06 % | 50 % | 18 / -0.69 % | 157 / +3.70 % |
| panic open | 56 | +0.66 % | -0.30 % | 46 % | 2 / +18.18 % | 54 / +0.01 % |

## COMPOSITE previous day <= -2 %

| bucket | n | mean | median | hit | 2022-24 n / mean | 2025-26 n / mean |
|---|---|---|---|---|---|---|
| market fell | 49 | +6.16 % | +3.33 % | 65 % | 0 | 49 / +6.16 % |
| market ok | 182 | +1.67 % | -0.39 % | 45 % | 20 / +1.20 % | 162 / +1.73 % |

## events the same morning

| bucket | n | mean | median | hit | 2022-24 n / mean | 2025-26 n / mean |
|---|---|---|---|---|---|---|
| 1 | 98 | +2.93 % | -0.30 % | 47 % | 20 / +1.20 % | 78 / +3.37 % |
| 2-3 | 41 | +0.55 % | -0.48 % | 46 % | 0 | 41 / +0.55 % |
| 4+ | 92 | +3.22 % | +0.63 % | 53 % | 0 | 92 / +3.22 % |

## name fell <= -10 % the day before

| bucket | n | mean | median | hit | 2022-24 n / mean | 2025-26 n / mean |
|---|---|---|---|---|---|---|
| already crashing | 89 | +6.06 % | +0.74 % | 52 % | 4 / +14.78 % | 85 / +5.65 % |
| fresh gap | 142 | +0.47 % | -0.30 % | 48 % | 16 / -2.19 % | 126 / +0.81 % |

## foreign net sell > 20 % of volume the day before

| bucket | n | mean | median | hit | 2022-24 n / mean | 2025-26 n / mean |
|---|---|---|---|---|---|---|
| foreign dumping | 39 | +1.38 % | -0.30 % | 49 % | 3 / +11.27 % | 36 / +0.55 % |
| no | 192 | +2.88 % | -0.02 % | 49 % | 17 / -0.58 % | 175 / +3.21 % |

## exchange announcement in the 3 days before

| bucket | n | mean | median | hit | 2022-24 n / mean | 2025-26 n / mean |
|---|---|---|---|---|---|---|
| news | 118 | +2.56 % | +0.63 % | 53 % | 5 / -1.47 % | 113 / +2.74 % |
| no news | 108 | +2.86 % | -0.30 % | 47 % | 10 / +3.63 % | 98 / +2.78 % |
| unknown (thin) | 5 | -0.99 % | -2.19 % | 20 % | 5 / -0.99 % | 0 |

