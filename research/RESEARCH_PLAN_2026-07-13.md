# RESEARCH PLAN 2026-07-13 (v2, TPB run) — trend-pullback two-sided test (ETHUSDT + SOLUSDT @ 4h)

> Supersedes the earlier 2026-07-13 ATR_MOM plan on this same date (that run
> terminated on ARCHETYPE_EXHAUSTION_2026-07-13; its findings are preserved in
> the journal: MRO STRATEGY_OUTCOME 164d275d, ATR_MOM falsification + papers).
> This plan executes the operator-provisioned unlock: TPB account_strategy rows
> seeded on the research account per the prior run's #1 data_wishlist item.

## Premise

- Prior run FALSIFIED two directional families on the 5-coin universe:
  MRO/MMR band-fade (inverted, high-power NO_EDGE on BTC/ETH/SOL) and ATR_MOM
  continuation (structural BULL-ONLY defect — its long-confirm gate never fires
  in crypto downtrends; BEAR ≈ 0 trades even across SOL's −96% 2022).
- TPB (`TrendPullbackEngine`, archetype=trend_pullback) is the structurally
  distinct TWO-SIDED archetype: mirrored long/short bias gates
  (long: ema50>ema200 & close>ema200; short: ema50<ema200 & close<ema200 on the
  bias TF), pullback-to-EMA20 entry, candle-quality gates (bodyRatio, CLV band,
  rvol), ADX bands + DI spread, TP1 + break-even-shifted ATR-runner exit.
- Standing HYPOTHESIS: `4e941275-cd35-40a2-94fa-4b3b1542313c` (ALGO) — the SHORT
  side fires ≥15 BEAR-regime trades with PF>1 pre-cost, pooled two-sided n≥100,
  where ATR_MOM was structurally one-sided. Falsifiers: shorts ≈0 trades OR
  short PF ≤ 1.0 after ~9bps taker cost OR n<40 at loosest credible config.
- Leaderboard state: DCB_POOL certified + shipped (closed). Nothing else near gate.
- Marker: fresh 8.5h run started 2026-07-13, iter=0, no warm leads inherited
  (prior run's warm_leads = []).

## Constraints reaffirmed

- Universe: BTC/ETH/SOL/BNB/XRP only; TPB is seeded ONLY on ETHUSDT@4h + SOLUSDT@4h.
- Intervals 5m/15m/1h/4h/1d; TPB rows exist at 4h only.
- Research-mode only (enabled=false, simulated=true); no live mutation; no promotion.
- V11+V60 gates FIXED: n≥100, PF 95%CI-low>1.0, DSR≥0.90, WF ROBUST for graduation.
  Mission GOAL_HIT bar: I additionally require ann_geom@alloc90 ≥ 10%/yr at step 11
  (stricter than the orchestrator's post-2026-06-19 economic axis). Loosening = fraud.
- Graveyard NOT re-pursued: MRO/MMR, ATR_MOM, funding, VBO, XS-dispersion,
  OI-quadrant, macro-event, ML-on-carry, DCB_POOLED_BOOK (shipped), Tardis skew-gate.

## Discovery ladder position

1. ~~IC screen~~ — not applicable (TPB is a strategy archetype over already-plumbed
   OHLCV/feature-store gates, not a new signal family; null-screen is the correct rung).
2. **Null-screen (IN FLIGHT)** — K=8 random draws per surface, loose-to-default
   gate ranges (biasAdxMin 15–25, adxEntryMin 15–25, diSpreadMin 0–3,
   pullbackTouchAtr 0.4–1.2, rvolMin 0.8–1.2, bodyRatioMin 0.25–0.45,
   clvMin 0.5–0.7, minSignalScore 0.40–0.60, tp1R 1.5–3.0, maxEntryRiskPct
   0.04–0.08). ETHUSDT@4h first (ik `nullscreen-tpb-ethusdt-4h-2026-07-13`),
   SOLUSDT@4h second (sequential — avoids JVM poll contention).
   **ETH@4h RESULT: EDGE_PRESENT** — 8/8 finite, median PF 1.44, P75 1.58,
   P95 2.55, share(PF≥1.2)=0.75. Per-draw n thin (3–21) on the 2024 window →
   n-power is the binding risk, signal is present. Full 12-cell grid justified.
   **SOL@4h RESULT: INCONCLUSIVE** — median PF 0.57, P75 0.91, P95 1.63,
   share(PF≥1.2)=0.25, n 2–13. Per branch rule: SOL grid shrunk to 6 cells
   (tp1R pinned 2.0; adxEntryMin×pullbackTouchAtr = 3×2), iter_budget 6.
   Same 9 axis NAMES on both queues → one plan review covers both.
   NOTE:
   null-screen runs the DEFAULT 2024→now window (no override support) — it is
   an edge-sniff only; the two-sidedness question is answered by the
   confirmatory sweep on the 2021→now window.
3. Confirmatory sweep (E1/E2 below).
4. Walk-forward only on SIGNIFICANT_EDGE + APPROVED graduation + specialist checkpoint.

## Experiments

### E1 — TPB SOLUSDT@4h confirmatory sweep (primary two-sidedness surface)

- Window: `backtest_window.start_time = 2021-01-01T00:00:00` (spans 2021 bull,
  2022 −96% bear, 2023 chop, 2024-26). ~12k bars at 4h — well under caps.
- Grid (12 cells, 3 dimensions traversed):
  - `adxEntryMin`: 18 / 22 / 25 (entry trend-strength)
  - `pullbackTouchAtr`: 0.5 / 0.8 (entry pullback-depth tolerance)
  - `tp1R`: 2.0 / 2.5 (exit)
  - Fixed loosenings (single-value axes): `biasAdxMin=18`, `diSpreadMin=1.0`,
    `rvolMin=0.9`, `bodyRatioMin=0.35`, `minSignalScore=0.50`, `maxEntryRiskPct=0.06`.
- iter_budget: 12.
- Success: any cell SIGNIFICANT_EDGE (V11+V60). Diagnostic (checked on FIRST
  completed iterations, not post-hoc): `by_trend_regime` split — BEAR bucket
  trade count and PF. This answers the archetype question regardless of verdict.
- Branches:
  - BEAR trades ≥15 with PF>1 → two-sided confirmed; refine along whichever
    axis the near-miss indicates (WARM lead protocol).
  - BEAR trades ≈ 0 → check whether biasAdxMax=40 / adxEntryMax=45 cap out
    high-ADX bear legs BEFORE declaring structural one-sidedness; one targeted
    retry with a widened ADX-max axis if so. If still ≈0 → ATR_MOM failure mode
    confirmed on the archetype → falsify.
  - n < 40 everywhere → power-dead at 4h; TPB@1h would need operator seeding
    (journal DATA_WISHLIST; per doctrine this does NOT count as a dead archetype).

### E2 — TPB ETHUSDT@4h confirmatory sweep (transfer + depth surface)

- Same grid shape as E1 (clean cross-surface comparison), same 2021-01-01 window.
  ETH extension to 2018 (second independent bear) reserved as the window-dimension
  follow-up if shorts are real but n-thin.
- iter_budget: 12.
- Success/branches: same as E1.

### Execution order

1. Null-screen ETH@4h (in flight) → read verdict.
2. Null-screen SOL@4h → read verdict.
3. Branch per surface:
   - NO_EDGE_DETECTED → drop that surface's sweep; if BOTH NO_EDGE → falsify
     honestly (grade DEAD ×2 via warmth helper), diagnose exhaustion.
   - EDGE_PRESENT → full 12-cell grid.
   - INCONCLUSIVE → shrink grid to ≤8 cells (drop tp1R axis → 3×2 = 6 cells).
   - INSUFFICIENT_DATA → inspect draw n_trades; if gate-starvation, ONE retry
     with loosened floors; else DATA_WISHLIST (does not count toward exhaustion).
4. Plan review → queue → drain (max_wall_clock_s ≤ 1500 per call) →
   regime-split read on first iterations → verdict → warmth grade → journal.

## Round 2 (added after round-1 results, 2026-07-13) — anchored continuation of the SOL WARM lead

Round-1 result (18/18 INSUF, STRATEGY_OUTCOME 52c65ff7): two-sidedness CONFIRMED
(BEAR fires + profits, SOL regime-analysis is_promising=TRUE best_regime=BEAR);
adxEntryMin=22 plateau profitable 6/6 cells across both coins; binding gate = n
(max 36). This is the popped WARM lead (pursuit 1/3): the un-swept ADX CEILINGS
(adxEntryMax default 45, biasAdxMax default 40) currently EXCLUDE the
strongest-trend pullbacks — precisely the high-ADX 2022 bear legs the edge
lives in. Widening them is the one runnable n-lever that does not degrade
entry quality (unlike adxEntryMin=18, which provably did).

### E3/E4 — TPB SOL + ETH round-2 grid (8 cells each)

- Swept: `adxEntryMin` 20/22 × `adxEntryMax` 45/60 × `biasAdxMax` 40/60.
- Fixed: `biasAdxMin=18`, `pullbackTouchAtr=0.5`, `tp1R=2.0`, `rvolMin=0.85`,
  `bodyRatioMin=0.30`, `minSignalScore=0.50`, `maxEntryRiskPct=0.06`.
  (`diSpreadMin` reverts to engine default 2.0 — dropped to fit the 10-name
  review cap; mild tightening accepted.)
- Windows: SOL 2021-01-01 (unchanged); ETH extended to 2018-01-01 (adds the
  2018 bear — an independent bear regime + ~55% more bars).
- New axis-name set → fresh plan review required (same hypothesis 4e941275).
- Success: any cell SIGNIFICANT_EDGE; realistic aim: n materially up at
  PF-plateau quality → tighter CI → upgrade lead to WARM-with-CI or HOT.
- Branches: n stays < 50 everywhere → 4h power ceiling structurally confirmed →
  DATA_WISHLIST (TPB@1h + more 4h coins) and close the run's TPB work honestly.

## Round 3 (added 2026-07-13) — exit-dimension study, SOL-4h best cell

Context: ETH-4h FALSIFIED cross-window (round 2); TPB@SOLUSDT@1h null-screen
NO_EDGE_DETECTED (median PF 0.90, P95 1.16 — interval unlock falsified;
STRATEGY_OUTCOME e24a4f90). SOL-4h stands WARM (PF 1.87, ann90 8.66, n 25,
BEAR-carried) but n≥100 is unreachable on any runnable surface — remaining
unlocks are operator-gated (TPB@4h seeds on BTCUSDT/BNBUSDT/XRPUSDT for a
pooled book; ~4-5 coins × ~25 trades ≈ n 100+).

### E5 — TPB SOL-4h exit study (4 cells)

- Swept: `tp1R` 2.0/3.0 × `runnerAtrPhase3` 1.8/3.0 at the round-2 best entry
  cell (adxEntryMin 20 / adxEntryMax 60 / biasAdxMax 60 / biasAdxMin 18 /
  rvolMin 0.85 / bodyRatioMin 0.30 / minSignalScore 0.50 / maxEntryRiskPct 0.06).
  `pullbackTouchAtr` reverts to engine default 0.40 (10-name review cap).
- Purpose: does the DCB-trailing-stop lesson transfer — do BEAR tail legs
  (2022 crash) reward a bigger TP1 / wider runner trail, lifting ann90 past 10
  at unchanged n? This completes the full-alpha-surface traversal
  (entry+regime+window+interval+EXIT) and fixes the config the operator would
  pool across 4-5 coins.
- This CANNOT clear V11 alone (n~25 << 100) — it is the handoff-quality
  measurement, not a graduation attempt.

## Decision criteria for next session

- HOT (SIGNIFICANT_EDGE): graduation ladder (steps 9–11), Path-C specialist checkpoint.
- WARM (one gate short, e.g. PF-CI-low>1 at n<100): push warm_lead with next_axis
  (window extension to 2018 on ETH / TPB@1h seeding request / regime gate).
- COLD_POWER (n<100 binding, point PF>1): lead with next_axis = window extension.
- DEAD both surfaces + no leads: TPB was the last runnable structurally-distinct
  directional archetype on the 5-coin universe → ARCHETYPE_EXHAUSTION diagnosis
  with updated data_wishlist (per-symbol microstructure LIQ_FADE ~Aug, new
  archetype seeds on high-beta alts, Tardis options purchase — operator call).
