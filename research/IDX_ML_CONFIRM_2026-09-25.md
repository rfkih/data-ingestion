# IDX menu ML-6f - two-step (confirmation) entries on the cost-aware ML book - 2026-09-25 - 6 trials, cumulative N = 780

| arm | trades | win | avg net | added or 2nd-step fills | CAGR | Sharpe | mDD | by year | verdict |
|---|---|---|---|---|---|---|---|---|---|
| base | 437 | 47 % | +2.80 % | 0 % | +29.1 % | 0.91 | -51 % | 22:-24 23:+37 24:+29 25:+83 26:+36 | reference |
| wait_dip10 | 119 | 49 % | +3.06 % | 0 % | +9.4 % | 0.50 | -37 % | 22:-4 23:+10 24:+0 25:+52 26:-5 | no: sharpe 0.50 < base 0.91 + 0.15; cagr < 80 % base |
| wait_dip15 | 86 | 59 % | +8.88 % | 0 % | +17.3 % | 0.85 | -30 % | 22:+8 23:+10 24:+5 25:+75 26:-2 | no: sharpe 0.85 < base 0.91 + 0.15; cagr < 80 % base |
| half_add10 | 437 | 48 % | +4.20 % | 23 % | +18.8 % | 0.79 | -40 % | 22:-16 23:+21 24:+13 25:+48 26:+31 | no: sharpe 0.79 < base 0.91 + 0.15; cagr < 80 % base |
| half_add25 | 437 | 48 % | +3.57 % | 6 % | +18.4 % | 0.90 | -32 % | 22:-11 23:+22 24:+16 25:+47 26:+21 | no: sharpe 0.90 < base 0.91 + 0.15; cagr < 80 % base |
| half_add_up5 | 437 | 43 % | +0.33 % | 33 % | +26.8 % | 1.10 | -37 % | 22:-17 23:+30 24:+33 25:+52 26:+41 | BETTER |
| wait_up5 | 193 | 54 % | +7.49 % | 0 % | +36.2 % | 1.38 | -27 % | 22:-10 23:+47 24:+39 25:+91 26:+23 | BETTER |

## Verdict

BETTER: half_add_up5, wait_up5; money rule: none.
