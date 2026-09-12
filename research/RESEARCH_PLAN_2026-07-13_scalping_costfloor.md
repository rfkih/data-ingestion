# RESEARCH PLAN 2026-07-13 — Operator-directed SCALPING hunt (cost-floor netted)

## Premise

- Operator landed a fresh direction (2026-07-13): hunt scalping alpha at 5m/15m/1h. This clears the
  ARCHETYPE_EXHAUSTION_2026-07-13 lockout via the fresh-HYPOTHESIS bypass (hypothesis `1c523721-bcbe-40e7-b0a3-d34956131d15`,
  created 11:25 > terminal-fire 07:31).
- The 4h directional families are exhausted (TPB/ATR_MOM/MRO/MMR/DCB/NAV_FIX/skew/macro/DVOL, 30d window).
  The intraday region is only PARTIALLY explored and its graveyard is specific: VWAP_MR@15m (n=3903, NET PF 0.42,
  cost-killed), VBO@15m (exit/slot-bound, FALSIFIED), intraday-EMA-trend@15m (fwd-IC negative). All were
  high-frequency and/or tight-target designs.
- **The cost floor is the wall.** Taker fee + slippage ≈ 15–20bps round trip. The only untested corner:
  RARE deep-dislocation entries with reversion targets several ATR away — sacrifice frequency for per-trade margin.
- Data verified ready: feature_store 5m (13 coins, 6.8M rows), 15m (2.9M rows), 1h — current. 15m archetypes
  MRO/MMR/DCB/VWAP_MR/VBO seeded on the research account; 412 gate binds on (strategy_code, account) only.
- Engine PF is fee-netted; `slippage_haircut_pnl` ladder (+5/+10/+20/+50bps) computed per iteration — every verdict
  reported NET, with the +10bps haircut as the margin audit.

## Constraints reaffirmed

- Research universe primary: BTCUSDT/ETHUSDT/SOLUSDT/BNBUSDT/XRPUSDT (deep history); operator opened the 13-coin
  feature_store universe for 5m/15m breadth if needed.
- Intervals: 5m/15m/1h this run (operator scope). Prod untouchable; research-mode only; no promote/deploy/push.
- Gates FIXED (V11+V60): n≥100, PF 95% CI-low>1.0, DSR≥0.90, ann_geom@alloc90 ≥10%/yr, WF ROBUST. No threshold
  shopping. Honest outcome allowed: "scalping is cost-bound on taker-only execution" is a valid terminal conclusion.
- PIT: only prev-bar feature_store columns (rsi/atr/ema/bb). No DVOL/skew (open-stamped) columns.
- /signal-screen NOT used at intraday scale (O(n) bootstrap jams orchestrator). /null-screen (K=8) is the
  surface gate instead.

## Experiments

### E1 (primary) — MMR deep-dislocation fade @ SOLUSDT 15m [family FAST_MR]

- Hypothesis: `1c523721-bcbe-40e7-b0a3-d34956131d15` (pre-registered, ALGO).
- Mechanism: price displaced ≥ extremeAtrMult×ATR from EMA200 + RSI extreme + reversal candle → fade toward EMA50;
  ATR-buffered stop; minRewardRiskRatio doubles as dislocation-depth selectivity; maxBarsHeld time-stop. Two-sided.
- Null-screen gate (new surface): K=8 draws over the pre-registered region, seed 42, IK
  `nullscreen-mmr-solusdt-15m-2026-07-13` (RUNNING at plan-write time).
- Window: 2021-01-01 → now (~192k bars, regime-diverse: 2021 bull / 2022 bear / 2023 chop / 2024-25 bull / 2026).
- Sweep grid (branch A, EDGE_PRESENT): extremeAtrMult [2.0, 2.5, 3.0] × minRewardRiskRatio [1.2, 1.8, 2.4] ×
  maxBarsHeld [12, 24] = 18 cells; RSI thresholds at engine defaults (30/70). 3 dimensions traversed
  (entry-extremity / exit-selectivity / time-stop).
- Branch B (INCONCLUSIVE): bounded 8 cells — extremeAtrMult [2.0, 3.0] × minRR [1.2, 2.0] × maxBarsHeld [12, 24].
- Branch C (NO_EDGE_DETECTED): do NOT sweep. Classify DEAD for the surface, pivot to E2.
- Branch D (INSUFFICIENT_DATA): DATA_WISHLIST journal; does not count toward exhaustion; pivot to E2.
- Success: V11+V60 net + (audit) +10bps haircut positive. Warmth grading per v2 loop on every terminal.

### E2 (second surface / mechanism) — chosen by E1 warmth

- If E1 WARM with n<100 binding (COLD_POWER): same params at 5m (4× bar density) or pooled-adjacent surface
  (MMR@XRPUSDT@15m — highest-beta alt with full 15m depth) along the lead's next_axis.
- If E1 DEAD on signal (not power): MRO@SOLUSDT@15m (BB-band exhaustion — different anchor/target structure)
  with its own null-screen; grid on rsiOversoldMax × minRR × maxBarsHeld.
- If E1 HOT: graduation path (steps 9–11), no E2.

### E3 (third family, only if FAST_MR exhausts) — DCB breakout-scalp @ 15m SOL/XRP

- DCB BREAKOUT entry with TIGHT scalp exit (low tpR 1.0–1.5, tight trail, maxBarsHeld) — differentiated from the
  07-01 ETH-15m DCB work (impulse-continuation + sweep-reclaim on ETH; this is SOL/XRP with scalp-tight exits).
  Requires its own null-screen (new surfaces).

## Execution order

1. Null-screen MMR@SOL@15m (background, ~30–60 min) — heartbeat every few min while waiting.
2. Plan review (`/reviews/request` + `/reviews/auto-run-checklist`) once null verdict lands and branch is chosen.
3. `POST /queue` (hypothesis_id 1c523721...) → `/tick/drain` loop (max_wall_clock_s ≤ 1500/call).
4. Classify warmth per cell-set terminal; journal checkpoint; iterate per branches above.
5. Papers + journals at every terminal per protocol.

## Decision criteria for next session

- Any cell with net PF CI-low > 1.0 at n ≥ 100 and DSR ≥ 0.90 → graduation review → specialists → WF.
- WARM leads (one gate short) → `warm_leads` queue with named next_axis (5m density / coin transfer / exit variant).
- If FAST_MR + BREAKOUT_SCALP both DEAD across ≥3 dims each → the honest "scalping is cost-bound on taker-only
  execution" conclusion, with the per-cell net-vs-gross evidence table in the paper. That is a valid, valuable outcome:
  it prices the maker-rebate/execution-model unlock for the operator.
