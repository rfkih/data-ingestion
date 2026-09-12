# Research Plan — 2026-07-15 (resumed run, iter 8+)

## Premise
Resumed the ACTIVE operator-directed run. The XS_MOM JVM-reproduction checkpoint (Sleeve #2 of the
risk-parity book) was COMPLETED by the prior session (2026-07-15 08:59, journal 35434f65): the real JVM
`CrossSectionalRankEngine` does NOT reproduce the offline ~0.9 Sharpe net-of-cost except at a single
knife-edge cell (lb14×weekly: Sharpe 0.957, +13.8%/yr, n=614) which itself fails V11 (PF-CI-low 0.904,
DSR 0.010). Canonical daily-rebalance = Sharpe 0.654, DSR 0.003, ann-ret@90 −15.4% (cost-killed).
Verdict = QUALIFIED NO-GO standalone. This session extended the XS_MOM warm lead (wider-leg axis) and
FALSIFIED it pre-queue: topQ 0.20 → DSR 0.010, topQ 0.25 (already swept 2026-06) → DSR 0.012 (no lift);
the 5-coin universe cannot widen legs enough; the promising 8-coin 2×2 variant is DATA-gated. XS-momentum
sleeve #2 is CLOSED (journal 9d21e98a).

Frontier now: 3 warm leads, all with operator/orch/data-gated *named* next-axes. This session pursues the
one RESEARCH-MODE-REACHABLE axis inside a WARM lead: the DCB-1d **exit dimension**.

## Constraints reaffirmed
- Universe: BTC/ETH/SOL/BNB/XRP only. Intervals 5m/15m/1h/4h/1d. This plan uses 1d.
- Research-mode ONLY: enabled=false simulated=true; no live dispatch, no promotion, no deploy, no git.
- Live DCB (ETHUSDT) UNTOUCHED — this sweeps the DCB-SOLUSDT-1d research seed row.
- 10%/yr + ROBUST bar unchanged; V11/V60 gates NOT loosened.

## Experiment — DCB-1d ride-longer EXIT probe (hypothesis 0f04038c)
- **Strategy / surface:** DCB @ SOLUSDT @ 1d (research seed row exists; strongest E1 single-name PF 2.05).
- **Mechanism:** the pooled DCB-1d book (bab42423) is one DSR-gate short (0.271<0.90). Its winning cell
  uses a FIXED exit (tpR 4.0 / stop 3.5 / maxBarsHeld 60). The lead's "ride trends longer" mechanism was
  only tested via the operator-owed Turtle exit (not in the JVM) and an entry-side ADX filter (FALSIFIED).
  The JVM-reachable exits (tpR, maxBarsHeld, stopAtrMult) were NEVER swept for ride-longer. Daily trends
  persist many bars; a 4R/60-bar exit may clip winners early, capping the Sharpe-driving win/loss asymmetry.
- **Sweep grid (18 cells, grid):**
  - `tpR`: 4.0, 6.0, 8.0  (let winners run to bigger targets)
  - `maxBarsHeld`: 60, 90, 120  (hold longer)
  - `stopAtrMult`: 3.5, 4.5  (wider trailing stop → fewer premature stop-outs)
  - fixed: entryMode=BREAKOUT, allowShort=true, adxEntryMin=0, rvolMin=0, maxEntryRiskPct=0.12,
    window full-history (SOL 2020-08).
- **Iter budget:** 20 (covers the 18-cell grid).
- **Success criteria (probe-level, not graduation):**
  - HOT/WARM if any cell lifts SOL-1d Sharpe materially above the fixed-4R baseline AND point-PF stays ≥ the
    baseline → re-pool the ride-longer exit across core-4 to re-measure book DSR next.
  - DEAD if no cell lifts Sharpe/PF → the exit dimension is exhausted for DCB-1d in research-mode; the only
    remaining lever is the operator-owed Turtle engine feature → DCB_1D lead DEAD, frontier converges.
- **Branches:**
  - SIGNIFICANT_EDGE + ≥10%/yr → graduation review (unlikely at single-name n; would be a bonus).
  - INSUFFICIENT_EVIDENCE but Sharpe-lifted → WARM, next axis = re-pool ride-longer exit book.
  - NO_EDGE / no Sharpe lift → DEAD; classify, converge.

## Execution order
1. Plan review (this plan) → clear gate.
2. Queue DCB SOLUSDT 1d exit-grid.
3. Drain via /tick/drain (max_wall_clock_s ≤ 1500).
4. Classify warmth; if Sharpe-lifted, design the re-pool follow-up; else classify DEAD and re-run scheduler.

## Decision criteria for next session
- If exit-grid DEAD: DCB_1D lead exhausted in research-mode. Remaining leads (DCB_1D operator-owed Turtle,
  MR_1D orch-owed window + can't-form-book) are all outside research-mode authority → CONVERGED →
  ARCHETYPE_EXHAUSTION diagnosis (this would be the 2nd-in-7d given the 2026-07-14 fire → terminal).
- If exit-grid Sharpe-lifted: re-pool ride-longer across core-4, re-measure book DSR (the real gate).

## Experiment 2 (added mid-session) — MRO-BTC-1d full-history window (hypothesis 91c747fa)
- **Surface:** MRO @ BTCUSDT @ 1d (runnable — queue f5dd617e ran COMPLETED on this surface 2026-07-14).
- **Correction:** the MR_1D lead labeled the window-widen "operator/orch-owed" — WRONG. tick.py:748-753
  already reads sweep_config.backtest_window.start_time. No code change needed.
- **Grid:** rsiOversoldMax {35,45} × stopAtrBuffer {0.5} × intervalMinutes {1440} × maxBarsHeld {15},
  backtest_window.start_time = 2017-08-17 (full BTC history vs the prior default 2024-01-01).
- **Success:** certifiable single-name candidate only if n ≥ ~30 AND PF-CI-low > 1.0 AND DSR non-trivial.
  Else COLD_POWER-confirmed (frequency-capped) or bull-only-DEAD (PF collapses over 2018/2022 bears).
- **Branch:** if it clears → graduation review. If n rises but PF collapses → DEAD. If n stays thin → park.
