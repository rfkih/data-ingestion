# Ready-to-run research configs unlocked 2026-07-15 (items 1 & 2)

Two research surfaces are now unblocked on the prod research JVM. Both are queue-time configs — no
new seeds/migrations needed at run time.

## 1. DCB-1d donchian-55 + opposite-channel Turtle exit (item 4 deployed)
The `donchian_breakout` engine (research JVM image `a2d7a3b`, deployed 2026-07-15) now supports two
opt-in spec params, and `donchian_upper/lower_55` are populated for **BTC/ETH/SOL/XRP @1d**.

Sweep the pooled DCB-1d book with:
```
params (spec_jsonb.params):
  entryChannelPeriod: 55        # System-2 Turtle entry channel (reads donchian_*_55)
  turtleExitPeriod:   20        # opposite-channel exit (long closes on a fresh 20-bar low)
  maxBarsHeld:        360        # LARGE so the timed exit doesn't pre-empt the channel ride
  stopAtrMult:        3.0        # protective ATR stop (Turtle 2N-ish); sweep 2.0–4.0
  rvolMin / adxEntryMin: sweep as usual (adxEntryMin 0 to disable the ADX gate)
universe/symbols: BTC/ETH/SOL/XRP at interval=1d (pooled, per the DCB_POOL-1d warm lead)
```
Target: does the 55-entry + opposite-channel exit lift the pooled book DSR past the 0.271 ceiling
(offline PF 1.76 vs live 20-bar+fixed-TP 1.50)? This is the only remaining research-mode lever for
the certified-but-sub-DSR pooled DCB-1d book. If other coins/intervals are needed, run a
`RECOMPUTE_RANGE` for them first to populate donchian_55 (only BTC/ETH/SOL/XRP 1d done so far).

## 2. 8-coin cross-sectional momentum @1d (item 2 unblocked)
The scout's "data-gated" premise was WRONG — all candidate coins already have 1d market_data +
feature_store (ADA topped up 2026-07-15; the rest current). XS_MOM is registered (V145) with its
research-account anchor, and the universe is a queue-time param (`POST /queue` `universe:[...]`,
max 12). So queue directly — NO new account_strategy seeds (an XS strategy uses ONE anchor, not
per-symbol rows):
```
strategy_code: XS_MOM
universe: [BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT, ADAUSDT, DOGEUSDT, AVAXUSDT, LINKUSDT]
interval: 1d
params: lookbackBars 20 (sweep 14–30), topQuantile/bottomQuantile 0.20 (sweep 0.15–0.25),
        rebalanceBars 5 (weekly-ish; daily was cost-killed), minSymbols 6
```
Rationale: on the 5-coin universe topQ 0.20 ≈ 1 name/leg (too thin); 8–9 coins gives a real 2×2
long-short book. Honest prior: XS-mom failed the real-JVM turnover cost at 5 coins (DSR 0.003); the
wider universe is the ONLY lift path, but it's still BTC-beta so treat as a longshot, not a lock.
```
```
