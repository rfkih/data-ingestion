# RESEARCH PLAN 2026-07-01 (H2) — event-conditioned microstructure reversal @ 15m (operator-directed, TRADING track)

## Premise
Continuation of the operator-directed 15m-scalp run. H1 (DCB BREAKOUT ETH 15m impulse-continuation) is
FALSIFIED (SO `9618dc46`, PF 0.508 — pure price-action dead BOTH directions). The whole raw-price-action 15m
family is exhausted: VBO@15m FALSIFIED (entry flat-negative + occupancy-bound), VWAP_MR@15m DISCARD (n=3903
but PF 0.42, cost-killed), intraday-EMA@15m FALSIFIED (fwd-IC negative), H1 breakout PF 0.508. Binding
constraint at 15m = cost-robustness + exit structure; every edge must clear the ~9bps round-trip taker floor.

## The one unexhausted dimension = forced-flow / orthogonal event-conditioning
Operator H2: fade ONLY after a forced-flow event, not on raw price deviation. Two trigger candidates:
- (a) LIQ_FADE liquidation-intensity spike. **NOT VIABLE this run**: no DEPLOYED engine consumes
  liquidation-intensity features (the LIQ_FADE `raw_aggregation` engine mode is on the unpushed
  `feat/liq-fade-features` branch), AND the Binance forceOrder stream only began accruing 2026-06-12 (n
  bull-only, cost-killed at 30bps, data-gated to ~late-Aug-2026 per prior LIQ_FADE research). Cannot be
  expressed in the prod research JVM today.
- (b) sweep/stop-run of a prior swing that immediately reclaims (wick-through beyond level + close-back-
  inside). **VIABLE** — this is exactly the `DonchianBreakoutEngine` `entryMode=SWEEP_RECLAIM` path
  (`trySweepReclaimLong/Short`): price wicks BEYOND the prior donchian-20 level (runs the stop cluster /
  sell-or-buy-side liquidity = the forced flow), then CLOSES back inside (the reclaim). This IS the seeded
  engine whose entry expresses forced-flow-reversal.

MRO was the operator's first-named engine, but its native entry (`tryLongEntry/ShortEntry`) is a raw
Bollinger-band-tag + RSI-exhaustion fade = precisely the UNCONDITIONAL price-deviation fade the operator
ruled out, and MRO has NO liquidation/sweep gate in its code. So per the operator's fallback ("if none maps
cleanly, use MRO with a liquidation/sweep gate"), the correct on-mission vehicle is DCB SWEEP_RECLAIM, which
has the forced-flow-event gate built in.

## Why this is NOT a re-skin of the exhausted family (re-discovery honesty)
- H1 = DCB **BREAKOUT** (continuation, join the move after liquidity taken). H2 = DCB **SWEEP_RECLAIM** (fade
  the FAILED breakout after the stop-run reclaims) — the OPPOSITE mechanism, event-conditioned not
  unconditional. Different axis-name set ⇒ different re-discovery hash.
- Prior SWEEP_RECLAIM runs were BTC-only (journal 44950e97 BTC@15m; BTC@4h) — ETH@15m sweep-reclaim with the
  moderate-timed-exit × vol-expansion × sweep-depth grid is untested.

## Hard constraints reaffirmed
- Universe BTC/ETH/SOL/BNB/XRP; **ETH primary**. Intervals 5m/15m/1h/4h/1d; focus 15m.
- Research never mutates live; seeded rows enabled=false simulated=true; NEVER promote, NEVER deploy.
- Gates FROZEN (V11: n>=100, PF95%CI lower>1.0, DSR/PSR>=0.90, SIGNIFICANT_EDGE; V60 economic axis).
  GOAL_HIT = walk-forward ROBUST AND ann_geom_alloc90>=10. Cost realism: zero-cost-only PF = DISCARD.

## Engine param mapping (DonchianBreakoutEngine, code DCB)
- `entryMode=SWEEP_RECLAIM` — forced-flow trigger (fixed).
- `sweepDepthPct` — min fractional wick BEYOND the level to count as a genuine stop-run (forced-flow-MAGNITUDE
  selectivity). Axis: [0.0, 0.0015].
- `rvolMin` (relativeVolume20 floor) — H3 vol-regime/volume-expansion overlay; a real stop-run shows up as a
  volume spike. Axis: [1.0, 1.8] (modest vs top-quantile). Tighten on vol, never loosen entry.
- `maxBarsHeld` + `intervalMinutes=15` — MODERATE timed exit (`tryTimedExit` fires first in managePosition).
  Axis: maxBarsHeld [8, 16] = 2h/4h hold at 15m (NOT ultra-tight — avoids the trade-count explosion that
  wedged the JVM 1800s guard on prior tight-exit runs). `intervalMinutes` PINNED to 15 (engine default is
  60 → would 4x the hold; the exact bug that ruined the prior ETH DISCARD's "24-bar" hold).
- `adxEntryMin=0` (fixed) — a reversal setup must NOT require a trend; permissive to reach n>=100.
- `stopAtrMult=2.0`, `tpR=1.5` (fixed) — modest positive-R:R structure so the few high-quality reversions can
  clear cost (per operator perf note: moderate exit, not ultra-tight).

## Experiment E1 — DCB SWEEP_RECLAIM @ ETHUSDT @ 15m
GRID (3 varying axes, per the ≥3-dimension rule):
- sweepDepthPct: [0.0, 0.0015]
- rvolMin:       [1.0, 1.8]
- maxBarsHeld:   [8, 16]
Fixed single-value params (passed so the engine uses them): entryMode=SWEEP_RECLAIM, intervalMinutes=15,
adxEntryMin=0, stopAtrMult=2.0, tpR=1.5.
Grid = 2x2x2 = 8 cells. Window 2024-07-01 -> now (<=2yr, 15m; bounded trade count = JVM-guard-safe).
iter_budget = 8.

## Success / falsification criteria (per iteration)
- SIGNIFICANT_EDGE + ann_geom_alloc90>=10 → graduation review → walk-forward → GOAL_HIT path.
- SIGNIFICANT_EDGE but sub-economic → journal near-miss, no GOAL_HIT.
- Any PF that survives only at zero cost, or PF<=1.0 net of 9bps → DISCARD/NO_EDGE.
- Falsification: one clean NO_EDGE/DISCARD on the deeper-sweep + top-quantile-rvol region ends H2 →
  intraday reversal family exhausted for this run → STRATEGY_OUTCOME + terminal digest.

## Execution order
1. Plan review (this file) → auto-checklist. 2. POST /queue (hypothesis_id 3750031b). 3. /tick/drain
(max_wall_clock_s 1500, re-call if MAX_*_REACHED). 4. Branch on terminal. 5. Journal + paper + digest.

## Decision criteria for next session
- If E1 yields SIGNIFICANT_EDGE → graduation review + specialist checkpoint (Path C).
- If E1 NO_EDGE/DISCARD → H2 falsified; the intraday (15m) reversal + continuation surface is exhausted for
  ETH; the honest next unlock is orthogonal NON-price data (LIQ_FADE once data-gated window opens ~late-Aug,
  or a fresh 15m surface on another coin) — NOT another price-action re-grid.
