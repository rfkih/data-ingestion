# Research Plan — 2026-07-01 (1-HOUR INTERVAL PIVOT, trading track)

## Premise
The 15m price-action family is EXHAUSTED (ARCHETYPE_EXHAUSTION 2026-07-01): every 15m
reversion/reversal edge bled ~-0.28%/trade against the ~9bps round-trip taker floor; n was
never the constraint. Operator pivoted to 1h because that same fixed ~9bps floor is a much
smaller FRACTION of a typical 1h move — a cost-fragile edge that died at 15m may clear at 1h.
Binding metric for every experiment: **avg_trade_return_pct NET of real 1h taker cost**
(zero-cost-only PF is a DISCARD).

15m graveyard (do NOT re-run): VWAP_MR@15m naive PF0.42 avg -0.28%; VWAP_MR@15m deep-deviation
(deviateMinPct 3.5) avg -0.16%; DCB SWEEP_RECLAIM@15m iters 468/469/470 avg -0.277/-0.279/-0.279%.
1h graveyard (do NOT re-run): DCB-ETH-1h BREAKOUT (live, 24-bar fixed-TP CAPPED); DCB-BTC-1h
BREAKOUT loses every config; XS price-momentum 13-coin @1h NO_EDGE; CVD/OFI @1h look-ahead dead.

## Constraints reaffirmed
- Universe BTC/ETH/SOL/BNB/XRP; ETH primary (deepest clean 1h history), BTC second. Verify SOL
  1h freshness before use (SOL 15m feed stale <=2026-06-17); this session does NOT use SOL.
- Intervals 5m/15m/1h/4h/1d; this session = 1h only.
- Research-mode only (enabled=false, simulated=true); never promote/deploy; never touch live book.
- Profitability bar: annualized_geometric_return_pct_at_alloc_90 >= 10 AND walk-forward ROBUST.
- V11 (n>=100, PF 95% CI lower>1.0, DSR/PSR>=0.90) + V60 as-is. No threshold loosening.

## Seed reality (checked /account-strategies/research)
- DCB has 1h seeds on BTC/ETH/BNB/XRP -> H2 (DCB SWEEP_RECLAIM) is RUNNABLE at 1h.
- VWAP_MR / MMR / MRO have ONLY 15m seeds -> H1's pure VWAP/mean fade at 1h is SEED-BLOCKED
  (would 412 account_strategy_missing). Filed as DATA_WISHLIST (operator-only to seed).
  DCB SWEEP_RECLAIM is the runnable reversion proxy: `sweepDepthPct` (wick depth beyond the
  Donchian channel before the reclaim fade) is the direct analog of H1's deviation-threshold.

## Experiments (execution order)

### E1 (LEAD) — DCB SWEEP_RECLAIM @ ETHUSDT @ 1h   [hypothesis c9c2a21b]
- Mechanism: enter AGAINST a stop-run — price wicks `sweepDepthPct` beyond prior Donchian-N
  channel then closes back inside (trapped-breakout / sweep-exhaustion), fade with a purely
  TIMED exit (maxBarsHeld hours) + fixed TP/SL.
- Grid (3 swept dims, 12 cells): sweepDepthPct {0.004, 0.008} x maxBarsHeld {8, 16, 24} x
  rvolMin {1.5, 2.5}; fixed adxEntryMin=0, stopAtrMult=2.0, tpR=1.5, intervalMinutes=60.
- Window: 2022-01-01 -> now (2022 bear + 2023 chop + 2024/25).
- Success: any n>=100 cell with avg_trade_return_pct > 0 net of cost = cost floor CLEARED at 1h;
  then V11+V60 gauntlet. Partial: avg-trade-net improves materially vs -0.28% but stays <0 ->
  mechanism real, cost still binds -> E3 overlay. Null: still ~-0.28% -> interval not the lever.

### E2 — DCB SWEEP_RECLAIM @ BTCUSDT @ 1h (second symbol, if E1 not-null)
- Same grid, BTCUSDT. Confirms whether any 1h reversion edge is ETH-specific or generalizes.

### E3 (OVERLAY, conditional on E1/E2 partial) — regime / HTF-bias gate
- Fade ONLY in mean-reverting / high-realized-vol conditions, or gate by higher-TF (4h/1d) bias
  so we do not fade a strong trend. Tighten via adxEntryMin (chop filter) or a regime gate;
  NEVER loosen entry gates to chase n. Runs only if E1/E2 show a cost-positive-but-sub-gate or
  regime-concentrated near-miss.

## Decision criteria for next session
- Any cell GRADUATE (SIGNIFICANT_EDGE + >=10%/yr) -> graduation review -> Path C specialists ->
  walk-forward -> GOAL_HIT if ROBUST.
- All PIVOT -> regime-analysis on the sweep -> STRATEGY_OUTCOME with avg-trade-net digest; then
  answer the operator's YES/NO/INCONCLUSIVE cost-floor question and, if budget remains, E3 overlay
  or a second archetype.
- Report per-experiment: engine/symbol/interval, n, PF, avg-trade NET of cost, DSR/PSR, verdict.
