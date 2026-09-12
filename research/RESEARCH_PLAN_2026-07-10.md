# Research Plan — 2026-07-10 (run started this session)

## Premise

Prior run (RESEARCH_RUN_COMPLETE_2026-07-09, journal 2408489f) confirmed the DCB-4h
Donchian-breakout edge on SOLUSDT (24/24 profitable cells, PF 1.37–1.85, n up to 220,
ann_geom_90 36–68%/yr) but every cell is blocked on the single V11 gate DSR (max 0.59
vs 0.90). BTC-4h is screen-killed both directions. The certification path is a pooled
ETH+BNB+SOL DCB-4h book — pooling raises n (the DSR binding constraint) while
diversifying. Two prerequisite re-queues were infra-killed by the 1.5g JVM regression;
operator restored 3g/-Xmx2560m and the inference DNS alias 2026-07-10, both verified.

## Constraints reaffirmed

Universe BTC/ETH/SOL/BNB/XRP; intervals 5m/15m/1h/4h/1d; research never mutates live;
V11+V60 gates fixed (n>=100, PF-CI-low>1.0, DSR>=0.90, ann_geom_90>=10, WF ROBUST);
reviewer verdicts authoritative; no promotion.

## Experiments (anchored continuations — pursue in this order)

### E1. Re-queue ETH-4h standardized box (lead DCB_BREAKOUT_ETH4H, pursuit 1/3)
- Hypothesis: 0a0a81a5 (ACTIVE, plan review APPROVED prior run).
- Exact replica of FAILED queue ac7aca2e sweep_config: grid 8 cells —
  entryMode=BREAKOUT, intervalMinutes=240, trailAtrMult=0, maxEntryRiskPct=0.12,
  tpR {2.0,3.0} x stopAtrMult {2.75,3.25} x maxBarsHeld {48,72}, window 2021-01-01→now.
- Purpose: standardized-box MEASUREMENT of ETH-4h sleeve for the pooled book (the
  ETH-4h deep-TP PF 3.47 n~30 from 2026-06-14 was a different box).
- Success: PF-CI-low>1.0 at n 80–130 in the same box shape SOL passed. Any
  SIGNIFICANT_EDGE cell → graduation path as usual.
- Branch: cells profitable → sleeve confirmed, feeds E3 design. Cells dead → pooled
  book falls back to SOL+BNB sleeves (BNB-4h measured prior runs).

### E2. Re-queue gated DCB-ETH-1h grid (lead DCB_EXIT_ETH1H, pursuit TBD)
- Hypothesis: fdb43c4f (ACTIVE, plan review APPROVED prior run).
- Exact replica of FAILED queue 762d2d1c sweep_config: 8 cells —
  intervalMinutes=60, maxEntryRiskPct=0.12, trailAtrMult=0, tpR {2.0,5.0} x
  stopAtrMult {3.0,5.0} x maxBarsHeld {96,168}, ML gate regime_eth_v2 ON (sentinels),
  window 2022-01-01→now. regime_eth_v2 signal_history fully backfilled (25,607 rows).
- Purpose: NEUTRAL-regime pocket (PF 1.356 n=102, iter 2cc8101b) gated to lift a cell
  past PF-CI-low/DSR.
- NOTE: HYBRID-kind — paired-delta gate does not apply here (gate always-on grid, no
  on/off pairing); if a cell graduates, ml-prescreen runs at 9d.
- Branch: gate lifts a cell → graduation path. Gate fails / fail-open (bit-identical
  metrics) → journal, family likely exhausted at 1h.

### E3. Pooled ETH+BNB+SOL DCB-4h book (lead DCB_BREAKOUT_SOL4H)
E1 RESULT (in): ETH-4h box 8/8 profitable, PF 1.20-1.41, n 179-248, PF-CI-low
0.88-0.98 (power-blocked, same as SOL); regime BULL 1.50 / BEAR 1.88 / NEUTRAL 0.95
(is_promising=true). ETH sleeve CONFIRMED for the book.
- E3a. BNB-4h standardized box measurement (hyp 451eabad, fresh ALGO design):
  identical 8-cell box (tpR {2.0,3.0} x stopAtrMult {2.75,3.25} x maxBarsHeld
  {48,72}, BREAKOUT, no trail, 2021->now). Success: >=6/8 cells PF>=1.2, n>=100.
  Surface has prior DCB-4h iterations (funding-sweep pool 2026-06-29) — no
  null-screen required. NOT the falsified rvol/adx axis; box never queued on BNB.
- E3b. Offline pooled analysis: pool backtest_trade series of the best common
  box cell across SOL+ETH+BNB; compute pooled PF, bootstrap CI, DSR estimate.
  Journal as evidence; certifiable pooled run needs an operator-seeded pooled
  account_strategy (DATA_WISHLIST if pooled stats clear the mechanical bar).

### E4. Regime-gated ETH-4h box retry (lead DCB_BREAKOUT_ETH4H pursuit 2, from E1 regime analysis)
- Orchestrator regime_retry recommendation: same 8-cell E1 box + regime_eth_v2
  sentinels (gate out NEUTRAL PF 0.95; BULL/BEAR carry PF 1.5-1.88).
- Direct-graduation candidate: gating NEUTRAL out of best cell (PF 1.41 n=196
  ciL 0.984) plausibly lifts PF to ~1.6 at n ~118 -> PF-CI-low > 1.0.
- Fresh HYPOTHESIS + plan review required (sentinel axes change the axis-set).

## Execution order

E1 queue → drain (max_wall_clock_s 1500 per call) → classify → E2 queue → drain →
classify → E3 design + review → queue → drain. Wall-clock checks between every
blocking call; WIND_DOWN at 8h cumulative stops new queues.

## Decision criteria for next session

- Any GRADUATE → step 9 (graduation review + Path C specialist checkpoint).
- E1/E2 both DEAD → pooled book design proceeds on SOL+BNB only; if that is also
  dead, family-exhaustion diagnosis per scheduler.
- Warm leads carried in marker; RUN_SUMMARY carries them on any run-ending terminal.

### E5. XRP-4h standardized box (added mid-session, same pooled-book pursuit)
E3a RESULT: BNB-4h box DEAD (6/8 PF<1.0, all geo90 negative) -- BNB sleeve OUT.
Box map: BTC dead (null-screen), BNB dead (today), ETH thin-real, SOL strong.
- XRPUSDT-4h is the LAST unmapped major for the box. Same 8 cells, 2021->now.
- Load-bearing finding (today): cumulative_trials is per-(symbol,interval)
  (BNB-4h 46-48 vs ETH-1h 222) -- XRP-4h carries LOW trial tax, so a SOL-grade
  edge there has a genuine DSR-0.90 shot, unlike any mined ETH/SOL surface.
- Success: >=5/8 cells PF>=1.3 at n>=100. SIGNIFICANT_EDGE cell -> graduation
  path as usual. DEAD -> pooled book = ETH+SOL sleeves only; E3b evidence
  journal + DATA_WISHLIST closes the pursuit.
