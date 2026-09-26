# Independent replication of the gap-fade sleeve - 2026-09-26

Operator item 4 of "1 - 6" (independent validation). A separate agent re-implemented the deployed gap-fade sleeve from a
written specification only - it was not allowed to read `research/`, `gapfade.py` or `combo_book.py` - and compared its trade
list with the stored backtest (#348, `idx.strategy_backtest_trade` strategy `gapfade`, 231 trades). Its code and trade CSVs:
`research-scratch/replication/replicate_gapfade.py`. The discrepancies were then checked against the research code here.

## Result: PARTLY reproduced

The mechanics reproduce exactly: on the 224 matched trades, entry and exit prices agree 100 %. The trade LIST did not.

| set | trades | matched with stored | only replication | only stored | mean / trade | median | hit |
|---|---|---|---|---|---|---|---|
| A: spec as written, most liquid first | 260 | 224 | 36 | 7 | +1.93 % | -0.86 % | 42 % |
| B: spec, deepest gap first (the live rule) | 260 | 176 | 84 | 55 | +2.16 % | -0.82 % | 43 % |
| stored #348 | 231 | - | - | - | +2.62 % | -0.03 % | 49 % |

(The replication used 0.15 / 0.25 % fees from the specification it was given; see below.)

## The causes, verified in the research code

1. **Look-ahead: locked days dropped.** `research/idx_daytrade.py` `eligible()` removed names with open = high = low - known only
   at the close. At the open such a name fills and loses (34 of the replication's 36 extra trades, mean -1.69 %). About +0.5
   pt/trade of inflation. **Fixed** 2026-09-26 (`IDX_LEGACY_ELIG=1` reproduces the old studies).
2. **Look-ahead: board read on the day itself**, not the previous day (FILM, FUTR, PADI, RMKE; FILM alone +28 %). **Fixed** in the
   same change (`P["main"].shift(1)`).
3. **Fees: NOT a flaw.** The replication reproduced the stored returns with 0.30 % round-trip fees; the research uses 0.10 / 0.20 %.
   The operator's REAL Stockbit fills (`idx.fill`, trend_live) are charged exactly 0.10 % on buys and 0.20 % on sells, so the
   research is right and the specification given to the agent (0.15 / 0.25 %) was wrong. Side finding: the combo books'
   `fee_buy_pct` / `fee_sell_pct` parameters are 0.15 / 0.25 %, above what Stockbit charges (the operator's call; allowed under
   the freeze).
4. **Cash sizing** skipped a few names whose one lot cost more than the slot (DSSA, ITMG) - legitimate for a Rp 20 M book.
5. **Selection order differs between backtest and live.** The backtest takes the most liquid names first; the live runner
   (`gapfade.py:122`) takes the deepest gaps first. The order only matters on days with more than 5 candidates: 14 days, where
   deepest-first did better (+2.58 % vs +1.72 %/trade, 8 of 14 days) - too few to be evidence, but the live rule is not the one
   that was backtested.
6. **Specification flaw (mine):** a raw previous close makes split days look like gaps (19 trades, e.g. AKRA -80 %); the stored
   backtest correctly uses adjusted prices.

## Consequence

#348 re-run with fixes 1-2 = **study #386** (combined 48.7 %/yr, Sharpe 2.15, mDD -18.0 % vs 50.6 / 2.21 / -17.1; gap sleeve
+2.07 %/trade, win 43 %, 11.0 %/yr vs +2.62 %, 49 %, 12.8 %). #348 is marked superseded; the kill rules, the scorecard yardstick
and the Strategies pages now read #386.
