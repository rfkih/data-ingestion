# IDX menu ML-6e - stop-loss rules on the cost-aware ML book - 2026-09-25 - 9 trials, cumulative N = 774

| arm | trades | win | avg net | hold d | CAGR | Sharpe | mDD | by year | verdict |
|---|---|---|---|---|---|---|---|---|---|
| base | 437 | 47 % | +2.80 % | 25 | +29.1 % | 0.91 | -51 % | 22:-24 23:+37 24:+29 25:+83 26:+36 | reference |
| stop5 | 909 | 30 % | -0.28 % | 12 | -0.9 % | 0.18 | -72 % | 22:-24 23:+22 24:+22 25:+42 26:-40 | no: sharpe 0.18 < base 0.91 + 0.15; mdd deeper; cagr < 80 % base |
| stop10 | 693 | 38 % | +0.60 % | 16 | +11.6 % | 0.49 | -64 % | 22:-19 23:+44 24:+18 25:+51 26:-19 | no: sharpe 0.49 < base 0.91 + 0.15; mdd deeper; cagr < 80 % base |
| stop20 | 527 | 43 % | +1.49 % | 21 | +15.3 % | 0.59 | -57 % | 22:-31 23:+53 24:+14 25:+94 26:-15 | no: sharpe 0.59 < base 0.91 + 0.15; mdd deeper; cagr < 80 % base |
| stop25 | 481 | 45 % | +2.41 % | 23 | +23.6 % | 0.79 | -58 % | 22:-21 23:+39 24:+22 25:+104 26:-0 | no: sharpe 0.79 < base 0.91 + 0.15; mdd deeper |
| stop30 | 466 | 47 % | +2.07 % | 24 | +17.8 % | 0.65 | -58 % | 22:-16 23:+35 24:+25 25:+59 26:-5 | no: sharpe 0.65 < base 0.91 + 0.15; mdd deeper; cagr < 80 % base |
| time20 | 619 | 39 % | +1.59 % | 18 | +19.9 % | 0.68 | -49 % | 22:-23 23:+31 24:+19 25:+68 26:+18 | no: sharpe 0.68 < base 0.91 + 0.15; cagr < 80 % base |
| nomfe10 | 585 | 38 % | +1.53 % | 18 | +21.1 % | 0.72 | -59 % | 22:-33 23:+37 24:+29 25:+112 26:-2 | no: sharpe 0.72 < base 0.91 + 0.15; mdd deeper; cagr < 80 % base |
| time20_stop20 | 653 | 40 % | +1.67 % | 16 | +21.8 % | 0.73 | -54 % | 22:-26 23:+32 24:+19 25:+114 26:+2 | no: sharpe 0.73 < base 0.91 + 0.15; mdd deeper; cagr < 80 % base |
| nomfe10_stop20 | 652 | 37 % | +1.39 % | 17 | +13.7 % | 0.54 | -62 % | 22:-38 23:+33 24:+19 25:+132 26:-19 | no: sharpe 0.54 < base 0.91 + 0.15; mdd deeper; cagr < 80 % base |

## Verdict

BETTER: none; money rule: none.
