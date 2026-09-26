# IDX menu ML-6f - two-step (confirmation) entries on the cost-aware ML book - 2026-09-26 - 6 trials, cumulative N = 780

| arm | trades | win | avg net | added or 2nd-step fills | CAGR | Sharpe | mDD | by year | verdict |
|---|---|---|---|---|---|---|---|---|---|
| base | 432 | 43 % | +4.20 % | 0 % | +28.4 % | 0.91 | -54 % | 22:-22 23:+26 24:+21 25:+173 26:+1 | reference |
| wait_dip10 | 128 | 47 % | +6.73 % | 0 % | +15.6 % | 0.78 | -26 % | 22:-20 23:+3 24:+17 25:+79 26:+16 | no: sharpe 0.78 < base 0.91 + 0.15; cagr < 80 % base |
| wait_dip15 | 83 | 54 % | +9.21 % | 0 % | +15.9 % | 0.87 | -17 % | 22:-10 23:+7 24:+14 25:+36 26:+35 | no: sharpe 0.87 < base 0.91 + 0.15; cagr < 80 % base |
| half_add10 | 432 | 46 % | +5.63 % | 23 % | +20.4 % | 0.88 | -40 % | 22:-10 23:+14 24:+16 25:+103 26:-1 | no: sharpe 0.88 < base 0.91 + 0.15; cagr < 80 % base |
| half_add25 | 432 | 44 % | +5.07 % | 6 % | +19.2 % | 0.97 | -34 % | 22:-10 23:+16 24:+11 25:+95 26:+2 | no: sharpe 0.97 < base 0.91 + 0.15; cagr < 80 % base |
| half_add_up5 | 432 | 41 % | +1.44 % | 35 % | +26.8 % | 1.11 | -42 % | 22:-19 23:+21 24:+24 25:+132 26:+8 | BETTER |
| wait_up5 | 209 | 44 % | +6.49 % | 0 % | +28.5 % | 1.18 | -41 % | 22:-17 23:+24 24:+41 25:+127 26:-1 | BETTER |

## Verdict

BETTER: half_add_up5, wait_up5; money rule: none.
