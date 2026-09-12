# RESEARCH PLAN 2026-06-29 - Cost-robust 15m scalping (operator-directed continuation)

## Premise
Operator REJECTED the prior session's SEED_GATED dead-end. Two directives, both executed this session:
1. Seed the missing 15m surfaces via existing JVM endpoints (no Flyway).
2. Diagnose the VBO 38-trade starvation and LOOSEN (not tighten) the 15m entry filters.
Standing hypothesis: e8f9e726-3602-4fd8-a0a6-9f087df006a5 (VBO 15m loosening, ALGO).

## Hard constraints reaffirmed
- Universe: BTCUSDT/ETHUSDT/SOLUSDT/BNBUSDT/XRPUSDT. ZEC off-universe (no 15m data) - skipped.
- Intervals: 5m/15m/1h/4h/1d; this focus = 15m.
- Research never mutates live; every seeded row enabled=false + simulated=true; no promotion.
- Gates FIXED (V11: n>=100, PF 95% CI lower>1.0, DSR>=0.90, SIGNIFICANT_EDGE; V60 econ floor 0.0).
  Loop GOAL_HIT = walk-forward ROBUST AND annualized_geom_return_alloc90 >= 10. Loosen ENTRY FILTERS only, never gates.

## DIRECTIVE 1 - SEEDING (DONE this session)
- Tunnel to VPS orchestrator (:8082) + research JVM (:8081); minted research-agent JWT (userId ...0001)
  via POST /api/v1/users/login (service_account creds from VPS env).
- Seeded 24 rows via POST /api/v1/account-strategies on research account ...0002. Because simulated(creatorIsAgent)
  is true for the research agent, every row lands simulated=true; enabled omitted=false.
- Seeded @ 15m, enabled=false simulated=true (DB-verified, 0 safety violations):
  VBO_RESEARCH: ETH/SOL/BNB/XRP (BTC pre-existing); DCB, MRO, VWAP_MR, MMR: BTC/ETH/SOL/BNB/XRP.
- Substituted VWAP_MR for operator's "VMT": VMT_BTC is HEDGING-kind/BTC-only (1d trend-hedge), not a 15m scalp;
  VWAP_MR is the genuine VWAP mean-reversion engine. MRO = microstructure reversal.
- SOL 15m feed stale at 2026-06-17 (confirmed) - SOL sweeps must cap end <= 2026-06-17.
- Live rows (DCB-ETH-1h, DCB-BTC-4h, EMA_BAND_BTC-1d, VMT_BTC-1d) UNTOUCHED - none at 15m.

## DIRECTIVE 2 - VBO loosening + frequency-sensitivity
Diagnosis: prior 38-trade run (iters 11ea6659/d7dae06c, PF 0.087, window 2024-01-01->now) had the binding
ADX/BB/CLV gates UNTOUCHED while atrExpansionMin+minSignalScore were moved UP (tighter) - n stayed pinned at 38.

### Experiment E1 - loosening grid (VBO_RESEARCH @ BTCUSDT @ 15m, same 2024-01-01->now window)
3 varying axes (binding gates), ordered so first cells isolate adxEntryMax:
- clvMin: [0.55, 0.70]   (default 0.90)
- minSignalScore: [0.55, 0.70]   (default 0.80)
- adxEntryMax: [30, 40]   (default 22 - widen the 7pt ADX band; operator's single biggest gate)
Fixed-loosened (single-value axes): adxEntryMin=10, compressionBbWidthPctMax=0.12, bodyRatioMin=0.30,
  atrExpansionMin=1.10, rvolMin=1.0.  Grid = 2x2x2 = 8 cells. Window kept = 2024-01-01->now (apples-to-apples).

### Success criteria (V11/V60, FIXED)
SIGNIFICANT_EDGE requires n>=100, PF 95% CI lower>1.0, DSR>=0.90, ag90>=10% -> graduation -> Path-C -> walk-forward.
Diagnostic goal: confirm n breaks past 100, read PF SIGN at high n, learn which gate moves n most.

### Branches
- n>=100 AND PF>1 with edge -> graduation review -> specialists -> walk-forward; ROBUST+>=10%/yr -> GOAL_HIT (operator flag).
- n>=100 AND PF<=1 (flat/negative after 15m cost) -> honest STRATEGY_OUTCOME; PIVOT to seeded VWAP_MR/MRO then DCB.
- n still <100 after heavy loosening -> VBO entry structurally rare at 15m even ungated -> pivot.

## Execution order
Seed (done) -> register hypothesis (done) -> plan review -> queue E1 -> /tick/drain (budget-bounded) -> verdicts -> journal.

## Decision criteria for next session
- E1 cells completed: read n-elasticity + PF sign; graduate (if a cell clears V11) or pivot to VWAP_MR/MRO.
- WIND_DOWN/RUN_COMPLETE mid-drain: queue persists PENDING; next run re-drains, then pivots per branch.
- Orthogonal-engine sweeps (VWAP_MR/MRO/DCB/MMR @ 15m) now UNBLOCKED on all 5 coins (SOL window-capped).
