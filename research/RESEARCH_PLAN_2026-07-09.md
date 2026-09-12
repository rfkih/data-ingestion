# RESEARCH PLAN 2026-07-09 — Regime-gated retry on DCB-ETHUSDT-1h exit-study cells

## Premise

- Fresh 8.5h research run (marker created 2026-07-09). Resume protocol drained the pending
  exit-study fixed-TP queue `c5c9f491` (hypothesis a3940807): 8/12 cells completed, ALL
  INSUFFICIENT_EVIDENCE (PF 0.96–1.07, n 333–719). Queue ended FAILED after the first tpR=10
  cell failed deterministically at the JVM twice (runs 34a027af, 86695f10; infra healthy).
  Hypothesis a3940807 FALSIFIED via STRATEGY_OUTCOME e872313f — on ETH-1h the live fixed-TP
  tpR=2.0 config remains the exit-dimension local optimum.
- Step-8.5 regime analysis on the last cell (iteration 2cc8101b, PF 1.07 n=333) returned
  **is_promising=true**: NEUTRAL trend-regime PF 1.356 (n=102, mean +0.81%/trade) vs BULL 1.03
  / BEAR 0.89. Recommended follow-up: re-queue with ML regime gate `regime_eth_v2`
  (trained lightgbm_modulator, purpose=regime, ETHUSDT@1h — registry ids ba9cd46f / 6b3b12e4).
- Scheduler gate: PURSUE_LEAD (pursuit 1/3 on family DCB_EXIT_ETH1H). Anchored continuation —
  the raw grid missed PF-CI-low>1.0 unconditionally; the regime-gate is the one axis the grid
  never traversed and it targets exactly that missed gate by cutting the BULL/BEAR losers.
- New hypothesis: **fdb43c4f-1017-4770-b35f-e46b3ff4e3ae** (kind=HYBRID, uses existing trained
  model, no training run needed, ML budget untouched).

## Constraints reaffirmed

- Research universe BTC/ETH/SOL/BNB/XRP; ETHUSDT@1h is in-universe. Intervals 5m/15m/1h/4h/1d.
- Research never mutates live trading; this runs on the research track only.
- Bar: n≥100, PF 95% CI low>1.0, DSR≥0.90, ann_geom_90 ≥ 10%/yr, WF ROBUST. Slippage haircut is
  audit-only (V60).
- Max 2 review rounds; reviewer verdict authoritative.

## Experiment: regime-gated exit-study grid (HYBRID)

- **Strategy / surface**: DCB @ ETHUSDT @ 1h, entryMode BREAKOUT (default), window start 2022-01-01.
- **Grid (8 cells, 3 varied dims + pinned ML sentinels)**:
  - tpR ∈ {2.0, 5.0}
  - stopAtrMult ∈ {3.0, 5.0}
  - maxBarsHeld ∈ {96, 168}
  - pinned: trailAtrMult=0, intervalMinutes=60, maxEntryRiskPct=0.12,
    `_ml_gate_enabled=[true]`, `_ml_signal_name=["regime_eth_v2"]`, `_ml_shadow_mode=[false]`
  - The 8 cells mirror EXACTLY the 8 completed ungated twins in queue c5c9f491 → paired-delta
    via iteration_ids after the drain (treatment `_ml_gate_enabled`, metric profit_factor,
    cross-checked with sharpe + return).
  - Deliberately EXCLUDES the tpR=10 arm: its first cell is the deterministic JVM-failure cell
    (2× FAILED) and the 2026-07-04 stop-width recheck already showed the wide arm worse.
- **Iter budget**: 8.
- **Success criteria**: (a) fail-open detector — first gated cell must NOT be bit-identical
  (PF/n to 4dp) to its off-twin; bit-identical → cancel queue, journal data-gap, void lead,
  fall to next direction (SOL plan below). (b) paired-delta POSITIVE on profit_factor;
  (c) best gated cell PF-CI-low > 1.0 with n ≥ 100 → graduation review path.
- **Branches**:
  - GRADUATE → step 9 (graduation review → Path C specialists → exit SPECIALIST_REVIEW_PENDING).
  - Gate fires, delta NEGATIVE/NEUTRAL, no cell clears → family DCB_EXIT_ETH1H closes DEAD
    (Stage-H precedent honored); STRATEGY_OUTCOME; scheduler → CONTINUE_FRESH.
  - Fail-open → void lead (data gap, not evidence); journal; CONTINUE_FRESH.

## Next direction on CONTINUE_FRESH (pre-staged, not part of this review)

DCB BREAKOUT @ SOLUSDT @ 4h let-winners-run (drafted hypothesis in .rtmp/hyp-sol4h.json):
the 4h Donchian trend mechanism is PF≥1.2 in every sibling 4h cell (BTC 2.40, BNB 16/16,
ETH 3.47) and SOL-4h is the one unmined in-universe surface. Null-screen gate first
(K=8, param box drafted in .rtmp/null-screen-sol4h.json); per-draw n is the go/no-go
(BNB n 40–65 and XRP n<60 were power-killed; SOL needs draws reaching n≈100).

## Execution order (this session)

1. Plan review (`/reviews/request` + `/reviews/auto-run-checklist`) for hypothesis fdb43c4f.
2. `POST /queue` (8 cells, iter_budget 8) + `/tick/drain` (capped ≤1500s per call, re-call).
3. Fail-open check after first cell lands; paired-delta after full drain.
4. Warmth-classify, journal, branch per above.

## Resume addendum (session 3, post JVM-restart)

- Research JVM restarted by operator ~17:58 UTC (Kafka poison-message loop cleared, no
  redelivery). Canary = the SOL-4h null-screen's first completing draws (un-gated JVM path).
- NEW PRECONDITION discovered by session 2 (journal 33d9bd4f): regime_eth_v2 signal_history
  starts 2024-12-02 → 70% of the 2022→now gated window would be fail-open. Execute
  POST /inference/backfill (2022-01-01 → 2024-12-03, ~25.6k rows) and verify
  rows_written before re-queueing the gated grid (original queue 2d293da9 cancelled).
- Re-queue reuses the SAME hypothesis fdb43c4f + grid as above; canary POST /tick (1 cell)
  before /tick/drain per the cancel-reason recipe.

## Experiment 2 (session 3): DCB BREAKOUT SOLUSDT@4h confirmatory sweep (ALGO, hyp 458f2124)

- **Null-screen result (this session, IK ...-r2)**: EDGE_PRESENT — 8/8 draws PF>1.0 (mean 1.196,
  p75 1.307, max 1.426); n reaches 106–125 in the low-tpR/hold~70 region, so the n-starvation
  falsifier did NOT fire on the screen window (~2024→now default).
- **Gated-ETH lead status**: infra-blocked (research JVM mem regression 1.5g/-Xmx1400m, journal
  c656782b); lead preserved in marker; operator owns the fix. This SOL sweep is un-gated 4h work,
  which the degraded JVM demonstrably completes.
- **Grid (12 cells, 3 dims)**: tpR ∈ {2.0, 3.0, 4.0} × stopAtrMult ∈ {2.75, 3.25} ×
  maxBarsHeld ∈ {48, 72}; pinned entryMode=BREAKOUT, intervalMinutes=240, trailAtrMult=0,
  maxEntryRiskPct=0.12. Centered on the null-screen's high-PF region (stop 2.7–3.3, hold 57–72).
- **Window**: start 2021-01-01 (full SOL history minus warmup — spans 2021 bull, 2022 bear,
  2023 chop, 2024–26). Longer than the screen window BY DESIGN (regime diversity + n≥100).
  MEMORY-GUARD BRANCH: first tick is a canary; if the full-window run freezes the 1.4G JVM
  (redelivery-guard FAILED), fall back to start 2023-01-01 and journal the window shrink.
- **Iter budget**: 12. Success: V11+V60 gates (n≥100, PF-CI-low>1.0, DSR≥0.90, ann_geom_90≥10).
- **Branches**: GRADUATE → step 9 (graduation review → Path C). All-INSUF with point-PF>1 &
  n<100 → COLD_POWER lead (next_axis: pool with BNB/XRP siblings or extend window). NO_EDGE /
  PF≤1 after cost → DEAD for DCB_BREAKOUT_SOL4H (family gets its first real dead mark).
- **Execution**: serial drain only (max_wall_clock_s ≤1500/call), nothing else on the JVM.

## Experiment 3 (session 3): DCB-SOL-4h entry-quality DSR lift (ALGO, hyp b5e877f0)

- **Anchor**: Experiment 2 confirmed 12/12 cells real edge, DSR sole binding gate (max 0.59 at
  iter 98692470, tpR 2.0 / stop 3.25 / hold 72, n=149, ann 68.5%/yr). Regime analysis PROMISING
  (BULL PF 2.43) but BULL-gating power-traps (n=57) and no SOL regime model exists.
- **Mechanism**: cull low-conviction breakouts (rvol near the 1.3 default floor) to lift
  per-trade Sharpe -> DSR, holding the proven exit config fixed.
- **Grid (12 cells, 3 dims)**: rvolMin ∈ {1.5, 1.7, 2.0} × adxEntryMin ∈ {22, 26} ×
  maxBarsHeld ∈ {48, 72}; pinned entryMode=BREAKOUT, intervalMinutes=240, trailAtrMult=0,
  maxEntryRiskPct=0.12, tpR=2.0, stopAtrMult=3.25. Window 2021-01-01 (same as Exp 2).
- **Success**: any cell n≥100, PF-CI-low>1.0, DSR≥0.90, ann≥10 → GRADUATE path.
- **Falsifiers**: n<100 before DSR clears (power trap); DSR flat at similar n (filter null).
- **Branches**: GRADUATE → step 9 / Path C. Falsified → family parks WARM with operator-gated
  next axes (bias.interval=1d spec variant; pooled multi-symbol 4h book after 3g mem restore).

## Experiment 4 (session 3): cost-ladder screens — BTC-4h transfer + MMR fade probe

- **DCB-BTC-4h BREAKOUT null-screen (SOL box, no retuning): NO_EDGE_DETECTED** — 8/8 draws
  PF 0.78–0.90, share PF≥1.0 = 0.0, n fine (105–120). Fixed-TP breakout does NOT transfer to
  BTC (June's PF 2.40 was the trail-exit profile). Pooled book ⇒ ETH+BNB+SOL sleeves.
  Zero hypothesis_audit trials spent (screen-level kill). Journal 88252c91.
- **MMR-BTC-4h fade null-screen (data-driven inverse):** consistently-losing breakouts at
  channel extremes imply mean-reversion; MMR fades EMA200-distance extremes with RSI
  confirmation. Box: extremeAtrMult 1.5–3.0 × rsi 25–35/65–75 × stopAtrBuffer 0.75–1.5 ×
  minRR 1.2–2.0 × hold 12–48 @ 4h. Branch: EDGE_PRESENT → confirmatory sweep (if wall-clock
  allows) or warm lead for next session; NO_EDGE → wrap.

## Experiment 5 (session 3): ETH-4h standardized-box measurement (ALGO, hyp 0a0a81a5)

- **Purpose**: book-construction, not certification. The pooled ETH+BNB+SOL DCB-4h book test
  (operator-gated) needs each sleeve measured on the SAME window/config; ETH's prior evidence
  (PF 3.47, n~30) is deep-TP on 2022→. This standardizes it.
- **Grid (8 cells)**: tpR {2.0, 3.0} × stopAtrMult {2.75, 3.25} × maxBarsHeld {48, 72};
  pins as Experiment 2; window 2021-01-01 (SOL-identical; 580k monitor bars = JVM-proven size).
- **Success**: PF-CI-low > 1.0 at n ≥ 80 in the plateau region. Falsifiers: CI-low < 1.0 across
  the box (ETH edge was deep-TP-specific → book drops to BNB+SOL); n < 60 (frequency starvation).
- **Branches**: measurement recorded either way → feeds the pooled-book operator memo; DSR is
  NOT the target (established unreachable per-symbol).

## Decision criteria for next session

- If SPECIALIST_REVIEW_PENDING: operator runs /run-pending-specialists; resume protocol
  picks up verdicts.
- If DCB_EXIT_ETH1H closed DEAD: next session starts at the SOL-4h null-screen
  (warm-lead queue will be empty unless regime retry lands COLD_POWER).
- Deribit historical load remains the highest-value data unlock (IDEA_BACKLOG 82245aea).
