# IDX menu SX-1 — an algorithm for "sentiment" multibaggers, 2008-2026 — 2026-09-27

Operator: "cari algoritma untuk menangkap saham2 sentimen" -> "coba backtest dari 2008". Script `research/idx_sentiment.py`
(pre-registered in its docstring, incl. the rev.2 realism fix made before any verdict was reported). **6 trials; cumulative
N 1067 -> 1073. Result: 0 of 6.** One CONTROL result is worth a follow-up (below).

Data: Yahoo .JK cache 2008-2019 (450 names, SURVIVORS ONLY - flattering), idx.bar 2020-2026 (989 names incl. delisted),
IDX announcements 2023-07 onward (the exchange archive starts there). Entry at the close after the signal (no fill on a
day up >= 18 %), exit on a 25 % trailing stop (no sale on a day down >= 6.5 %), ~0.9 % round trip, 5 % of NAV per name, 20 max.

| arm | window | trades | mean / median per trade | mean without top 5 | book CAGR / Sharpe / mDD | verdict |
|---|---|---|---|---|---|---|
| C0 control: momentum (+30 % in 60 d, 1-year high) | Y 2008-19 | 576 | +17.7 % / -8.7 % | +12.5 % | **+20.8 % / 1.24 / -23 %** | control |
| S1 C0 + attention (20d value >= 3x 1-yr) | Y 2008-19 | 294 | +20.0 % / -10.1 % | +12.0 % | +16.7 % / 1.12 / -22 % | no (below C0) |
| S2 attention >= 5x | Y 2008-19 | 166 | +18.8 % / -10.1 % | +8.8 % | +11.8 % / 0.98 / -22 % | no |
| S3 S1 with a 35 % trail | Y 2008-19 | 270 | +27.4 % / -7.3 % | +16.4 % | +10.6 % / 0.72 / -37 % | no |
| C0 control | X 2020-26 | 1,445 | +16.8 % / -11.2 % | +13.2 % | **+45.8 % / 1.92 / -34 %** | control |
| S1 | X 2020-26 | 1,029 | +15.8 % / -13.7 % | +11.0 % | +26.5 % / 1.16 / -39 % | no |
| S2 | X 2020-26 | 665 | +15.7 % / -13.8 % | +8.7 % | +19.7 % / 0.94 / -45 % | no |
| S3 | X 2020-26 | 905 | +20.8 % / -17.6 % | +13.3 % | +37.2 % / 1.47 / -46 % | no |
| S5 IPO momentum | X 2020-26 | 184 | +11.3 % / -12.6 % | +0.9 % | +15.3 % / 0.97 / -24 % | no (t 1.8, below C0) |
| C0 control | X 2023-07..26 | 906 | +15.7 % / -12.3 % | +11.4 % | +37.2 % / 1.51 / -39 % | control |
| E1 change of control + confirmation | X 2023-07..26 | 82 | +30.2 % / +1.9 % | +12.4 % | +40.6 % / 2.17 / -23 % | **no - placebo pct 48** |
| E2 merger / restructuring + confirmation | X 2023-07..26 | 129 | +32.5 % / -3.3 % | +9.2 % | +65.1 % / 2.38 / -19 % | **no - placebo pct 85** |

IHSG over the same windows: 2008-19 7.2 %/yr, 2020-26 -0.1 %/yr.

## Reading

1. **"Sentiment" as a volume surge adds nothing to momentum** - every attention arm is below the plain momentum control in both
   periods. The volume is already in the price.
2. **The events look great until the placebo.** E1/E2 beat C0 on Sharpe and drawdown, but the SAME names with RANDOM event
   dates do as well (E1 placebo Sharpe 2.15 vs 2.17; E2 2.05 vs 2.38, pct 85 < 90). What pays is the TYPE of company that
   undergoes a change of control or a restructuring (small, speculative, conglomerate-linked), not the announcement's timing.
3. **The first run was too rosy:** without the ARA/ARB lock realism C0 printed 61 %/2.27 on 2020-26; with it 45.8 %/1.92.
   Any number quoted from this study is the rev.2 one.
4. **The control is the finding worth following up.** Plain momentum with a LONG trailing exit and a Rp 1 bn floor beat IHSG
   in both periods (20.8 % vs 7.2 %, 45.8 % vs -0.1 %). The deployed trend sleeve is the same family on the LIQ universe
   (>= Rp 5 bn) with its own exit: 12.7 %/1.19 (#192). The gap may be the smaller names and the 25 % trail - a construction
   question. It is NOT a result: C0 was a control, 2008-19 is survivors-only, mDD -34..-39 %, 2026 YTD negative, and the
   rupiah book skips expensive lots (PANI). Next step = a pre-registered test against the deployed trend engine (same
   simulator, PIT board, rupiah lots, cost stress, capacity).
5. **News before 2023:** the exchange archive starts 2023-07-03, so pre-2023 events need a news backfill. Given point 2 (the
   event's timing did not matter even where we have it), that backfill is unlikely to change the verdict.
