# IDX menu ML-6h - stops on the up-confirmation entry - 2026-09-26 - 7 trials, cumulative N = 799

| arm | trades | win | avg net | hold d | CAGR | Sharpe | mDD | by year | exits | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| base | 209 | 44 % | +6.49 % | 24 | +28.5 % | 1.18 | -41 % | 22:-17 23:+24 24:+41 25:+127 26:-1 | max_hold n 31 avg -2.5 %, swap n 178 avg +8.1 % | reference |
| stop5 | 299 | 33 % | +4.97 % | 11 | +28.7 % | 1.44 | -29 % | 22:-18 23:+19 24:+26 25:+127 26:+18 | max_hold n 9 avg +43.3 %, stop n 179 avg -9.2 %, swap n 111 avg +24.7 % | BETTER |
| stop10 | 265 | 37 % | +5.07 % | 16 | +27.0 % | 1.32 | -35 % | 22:-21 23:+25 24:+38 25:+71 26:+32 | max_hold n 13 avg +31.8 %, stop n 109 avg -14.7 %, swap n 143 avg +17.7 % | no: sharpe 1.32 < base 1.18 + 0.15 |
| stop15 | 248 | 40 % | +6.25 % | 18 | +28.8 % | 1.30 | -31 % | 22:-13 23:+17 24:+37 25:+82 26:+30 | max_hold n 17 avg +24.5 %, stop n 66 avg -18.4 %, swap n 165 avg +14.2 % | no: sharpe 1.30 < base 1.18 + 0.15 |
| stop20 | 227 | 44 % | +6.52 % | 21 | +29.5 % | 1.36 | -30 % | 22:-21 23:+25 24:+39 25:+89 26:+30 | max_hold n 24 avg +12.3 %, stop n 35 avg -23.5 %, swap n 168 avg +12.0 % | BETTER |
| trail10 | 297 | 41 % | +3.08 % | 12 | +18.9 % | 1.05 | -30 % | 22:-27 23:+28 24:+22 25:+75 26:+13 | max_hold n 4 avg +18.0 %, swap n 102 avg +15.9 %, trail n 191 avg -4.1 % | no: sharpe 1.05 < base 1.18 + 0.15; cagr < 80 % base |
| trail15 | 265 | 42 % | +5.58 % | 16 | +28.8 % | 1.37 | -33 % | 22:-22 23:+21 24:+38 25:+69 26:+50 | max_hold n 10 avg +21.4 %, swap n 145 avg +13.3 %, trail n 110 avg -6.0 % | BETTER |
| trail20 | 246 | 42 % | +6.17 % | 19 | +28.9 % | 1.29 | -30 % | 22:-14 23:+19 24:+28 25:+88 26:+35 | max_hold n 16 avg +25.2 %, swap n 163 avg +12.6 %, trail n 67 avg -14.1 % | no: sharpe 1.29 < base 1.18 + 0.15 |

## Base (wait_up5) trade anatomy

| stat | value |
|---|---|
| n | 209 |
| win | 0.4402 |
| avg_win | 0.3167 |
| med_win | 0.2148 |
| avg_loss | -0.1332 |
| med_loss | -0.1222 |
| mfe_win_med | 0.2994 |
| mfe_win_mean | 0.4141 |
| mae_win_med | -0.002 |
| mfe_loss_med | 0.0169 |
| mae_loss_med | -0.15 |
| mae_all_med | -0.0784 |
| giveback_win_med | 0.0446 |
| sig_to_fill_mean | 4.4019 |
| hold_win | 22.8261 |
| hold_loss | 24.4188 |
| pct_net | {'p10': -0.19764677645421497, 'p25': -0.14053188191119215, 'p50': -0.028893184737340483, 'p75': 0.159205873491588, 'p90': 0.4965137755345849} |
| share_mae_gt_5 | 0.3971 |
| share_win_mae_gt_5 | 0.7283 |
| share_mae_lt_10 | 0.445 |
| recover_after_10 | 0.1183 |

## Verdict

BETTER: stop5, stop20, trail15; money rule: none.
