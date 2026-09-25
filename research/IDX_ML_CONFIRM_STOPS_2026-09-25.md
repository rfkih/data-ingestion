# IDX menu ML-6h - stops on the up-confirmation entry - 2026-09-25 - 7 trials, cumulative N = 799

| arm | trades | win | avg net | hold d | CAGR | Sharpe | mDD | by year | exits | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| base | 193 | 54 % | +7.49 % | 24 | +36.2 % | 1.38 | -27 % | 22:-10 23:+47 24:+39 25:+91 26:+23 | max_hold n 32 avg +1.7 %, swap n 161 avg +8.6 % | reference |
| stop5 | 294 | 34 % | +2.89 % | 11 | +18.0 % | 0.98 | -33 % | 22:-16 23:+25 24:+31 25:+47 26:+9 | max_hold n 8 avg +56.3 %, stop n 173 avg -8.6 %, swap n 113 avg +16.6 % | no: sharpe 0.98 < base 1.38 + 0.15; mdd deeper; cagr < 80 % base |
| stop10 | 234 | 47 % | +5.48 % | 17 | +31.9 % | 1.49 | -29 % | 22:+0 23:+36 24:+33 25:+66 26:+22 | max_hold n 14 avg +23.0 %, stop n 85 avg -13.1 %, swap n 135 avg +15.4 % | no: sharpe 1.49 < base 1.38 + 0.15; mdd deeper |
| stop15 | 237 | 47 % | +5.00 % | 19 | +23.5 % | 1.08 | -41 % | 22:-8 23:+42 24:+34 25:+58 26:-2 | max_hold n 22 avg +21.4 %, stop n 61 avg -17.6 %, swap n 154 avg +11.6 % | no: sharpe 1.08 < base 1.38 + 0.15; mdd deeper; cagr < 80 % base |
| stop20 | 218 | 52 % | +6.22 % | 20 | +30.3 % | 1.37 | -38 % | 22:+1 23:+43 24:+34 25:+58 26:+15 | max_hold n 24 avg +18.5 %, stop n 37 avg -23.8 %, swap n 157 avg +11.4 % | no: sharpe 1.37 < base 1.38 + 0.15; mdd deeper |
| trail10 | 277 | 42 % | +3.66 % | 12 | +20.2 % | 1.20 | -23 % | 22:-16 23:+37 24:+26 25:+51 26:+9 | max_hold n 3 avg +20.4 %, swap n 97 avg +13.1 %, trail n 177 avg -1.8 % | no: sharpe 1.20 < base 1.38 + 0.15; cagr < 80 % base |
| trail15 | 247 | 45 % | +3.92 % | 16 | +20.9 % | 1.08 | -26 % | 22:-10 23:+33 24:+30 25:+48 26:+7 | max_hold n 11 avg +25.7 %, swap n 128 avg +8.3 %, trail n 108 avg -3.5 % | no: sharpe 1.08 < base 1.38 + 0.15; cagr < 80 % base |
| trail20 | 232 | 51 % | +5.33 % | 19 | +31.5 % | 1.38 | -36 % | 22:-10 23:+38 24:+38 25:+94 26:+9 | max_hold n 18 avg +23.9 %, swap n 152 avg +8.1 %, trail n 62 avg -7.0 % | no: sharpe 1.38 < base 1.38 + 0.15; mdd deeper |

## Base (wait_up5) trade anatomy

| stat | value |
|---|---|
| n | 193 |
| win | 0.5389 |
| avg_win | 0.2584 |
| med_win | 0.1613 |
| avg_loss | -0.1395 |
| med_loss | -0.1255 |
| mfe_win_med | 0.2558 |
| mfe_win_mean | 0.3544 |
| mae_win_med | -0.0171 |
| mfe_loss_med | 0.0226 |
| mae_loss_med | -0.151 |
| mae_all_med | -0.0769 |
| giveback_win_med | 0.0285 |
| sig_to_fill_mean | 4.2487 |
| hold_win | 22.7404 |
| hold_loss | 26.4494 |
| pct_net | {'p10': -0.2081530058703074, 'p25': -0.1130111268042302, 'p50': 0.011557785280413402, 'p75': 0.17424242424242453, 'p90': 0.44200100646043333} |
| share_mae_gt_5 | 0.4093 |
| share_win_mae_gt_5 | 0.6538 |
| share_mae_lt_10 | 0.4093 |
| recover_after_10 | 0.2278 |

## Verdict

BETTER: none; money rule: trail10.
