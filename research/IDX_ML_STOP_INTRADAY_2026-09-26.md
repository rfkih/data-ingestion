# IDX menu ML-9c - the ML stop run as Stockbit's Auto Order - 2026-09-26 - 2 trials, cumulative N = 989

Pre-registered rule in the script's docstring. Intraday stop from daily bars: trigger = fill x (1 - x), limit 2 ticks under.

| book | CAGR | Sharpe | mDD | Sharpe H1 / H2 | trades | win | avg | median | worst trade | 1st pct | hold d | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| none | +27.9 % | 1.30 | -35 % | 1.20 / 1.48 | 720 | 44 % | +7.31 % | -2.56 % | -53.4 % | -43.1 % | 22.9 | reference |
| close_stop5 | +34.4 % | 1.96 | -20 % | 1.56 / 2.32 | 948 | 36 % | +6.19 % | -5.17 % | -34.6 % | -25.3 % | 11.1 | reference |
| sb_stop5 | +21.3 % | 1.53 | -19 % | 1.09 / 1.87 | 1064 | 23 % | +3.29 % | -6.00 % | -30.9 % | -18.4 % | 7.7 | no: cagr < 80 % none; not better in both halves |
| close_stop10 | +31.2 % | 1.74 | -25 % | 1.42 / 2.03 | 845 | 41 % | +6.54 % | -5.15 % | -34.6 % | -26.4 % | 15.3 | reference |
| sb_stop10 | +23.4 % | 1.40 | -19 % | 0.77 / 1.82 | 906 | 34 % | +4.69 % | -10.65 % | -35.1 % | -19.3 % | 12.8 | no: sharpe 1.40 < none 1.30 + 0.15; not better in both halves |
