# Research Paper: DCB — SOLUSDT × 4h

**Author:** quant-researcher
**Date:** 2026-07-09
**Strategy:** `DCB`
**Surface:** `SOLUSDT` × `4h`
**Type:** ALGO
**Surface attempt:** v1 — ALGO (first formal mining of the SOLUSDT 4h Donchian-breakout surface; entryMode=BREAKOUT, fixed-TP exits)
**Prior papers on this surface:** none (first attempt)
**Filename:** `RESEARCH_PAPER_DCB_SOLUSDT_4H_v1_ALGO_2026-07-09.md`
**Terminal:** WALL_CLOCK_CAP (session 3 of the run; family parked WARM)
**Goal status:** NOT HIT — real edge on every axis except DSR certification
**Hypothesis:** `458f2124-2bd7-47ef-b5b0-7418fcc54ca1` (transfer) and `b5e877f0-43df-45bf-858f-57d67d6a4834` (entry-quality DSR lift, FALSIFIED)
**Queue(s):** `6e47428e-ca1c-4e38-9eab-27fe9718cdd4` (exit grid), `8c4b0a4a-d99c-41c7-acaf-eed551d2c98a` (quality grid)

---

## TL;DR

The 4h Donchian-breakout mechanism — already shown real-but-underpowered on ETHUSDT (PF 3.47, n≈30), BNBUSDT (walk-forward 100% positive folds, n≈45) and BTCUSDT (trail-exit PF 2.40, DSR-taxed) — transfers to SOLUSDT with the largest sample the mechanism has ever produced. All 24 formal cells across two pre-registered grids are profitable: PF 1.24–1.85, n up to 220, annualized geometric return at 90% allocation 9–68%/yr, PF-95%-CI lower bound above 1.0 in 17 of 24 cells, and positive PnL in BULL, BEAR and NEUTRAL regimes at the anchor config. Every cell fails exactly one V11 gate: DSR (max 0.59 vs the 0.90 bar) — the per-symbol Sharpe (~0.8–1.2) is too low for deflated certainty at n≈150. An entry-quality filter sweep (rvolMin, adxEntryMin) designed to lift DSR was falsified: rvolMin=2.0 lifts point PF to 1.85 but the trade-count loss drops DSR to 0.34, and adxEntryMin≥26 destroys the edge outright. The surface's sweepable axes are exhausted; the remaining certification path is portfolio-level and operator-gated: a pooled multi-symbol DCB-4h book test (requires the research JVM memory limit restored to 3g) and/or a `bias.interval=1d` spec variant.

*(No cell reached SIGNIFICANT_EDGE — gate table omitted per template.)*

---

## 1. Background

Session start (2026-07-09, session 3 of an 8.5h cumulative run): the standing warm lead was a regime-gated DCB-ETH-1h retry (hypothesis `fdb43c4f`), blocked twice by infrastructure. This session cleared its data precondition (25,607-row `regime_eth_v2` signal_history backfill, 2022-01-01→2024-12-03, executed directly against the inference sidecar after diagnosing a Docker-DNS break in the orchestrator proxy path) but the gated backtest then froze the research JVM — root-caused to the container running the pre-2026-06-18 memory config (1.5 GiB / -Xmx1400m; the documented 3g fix was lost in a container recreate). The ETH lead is preserved, operator-gated.

The session pivoted to the pre-staged second direction: DCB BREAKOUT on SOLUSDT@4h. Selection rationale: the 4h Donchian mechanism had shown PF ≥ 1.2 on every sibling 4h surface, and SOL was the one unmined in-universe surface whose higher per-bar volatility plausibly fixes the family's chronic n-starvation (ETH-4h n≈30; BNB-4h n≈45; XRP-4h frequency-dead n<60). Prior SOL-4h DCB rows (2026-06-29, iterations 441–443) were SWEEP_RECLAIM funding-Z cells from the falsified funding family — zero information about BREAKOUT mode.

## 2. Hypothesis

**Mechanism:** DCB (Donchian channel breakout). Entry: close beyond the 20-bar Donchian channel with relative-volume ≥ rvolMin (default 1.30) and ADX ≥ adxEntryMin (default 20); long above the upper channel, short below the lower. Position management: ATR-multiple stop (stopAtrMult), break-even shift at +1R. Exit: fixed take-profit at tpR × risk, timed exit at maxBarsHeld bars, trailing disabled (trailAtrMult=0).

**Pre-registration (hypothesis 1):** `458f2124` registered 2026-07-09T17:36Z, before any SOL BREAKOUT backtest ran (null-screen 18:07Z, first sweep cell 18:27Z). Falsifiers named in advance: null-screen NO_EDGE_DETECTED; n-starvation (best cells stuck n<100).

**Pre-registration (hypothesis 2):** `b5e877f0` registered 2026-07-09T19:41Z, before the quality-sweep queue was created (19:44Z). Success criterion: a cell with n≥100, PF-CI-low>1.0, DSR≥0.90, ag90≥10. Falsifiers named in advance: power trap (n<100 before DSR clears); quality-filter null (DSR flat/down at similar n).

**Type:** ALGO (both hypotheses).

## 3. Methodology

### 3.1 Statistical Gates (V11 + V60)

| Gate | Threshold | Binding this campaign? |
|---|---|---|
| n_trades | ≥ 100 | passed in 20/24 cells |
| PF 95% bootstrap CI lower | > 1.0 | passed in 17/24 cells |
| DSR (n_trials from hypothesis_audit) | ≥ 0.90 | **FAILED in 24/24 cells — the binding gate** |
| Statistical verdict | SIGNIFICANT_EDGE | never reached (DSR) |
| ag90 | ≥ 10%/yr | passed in 22/24 cells |

### 3.2 Sweep Design

- **Type:** GRID (seed 42) both sweeps.
- **Backtest window:** 2021-01-01 → 2026-07-09 (~66 months, 22 quarters; spans 2021 bull, 2022 bear, 2023 chop, 2024–26 bull/corrections).
- **Null-screen first (cost ladder):** 8 random draws over the BREAKOUT box → **EDGE_PRESENT** (8/8 finite, all PF>1.0, mean 1.196, p75 1.307, max 1.426; share PF≥1.2 = 0.375). Two draws reached n≥100 on the screen's shorter default window — the n-starvation falsifier did NOT fire.
- **Sweep 1 (queue `6e47428e`):** tpR {2.0, 3.0, 4.0} × stopAtrMult {2.75, 3.25} × maxBarsHeld {48, 72} = 12 cells; pinned entryMode=BREAKOUT, intervalMinutes=240, trailAtrMult=0, maxEntryRiskPct=0.12. 12/12 executed.
- **Sweep 2 (queue `8c4b0a4a`):** rvolMin {1.5, 1.7, 2.0} × adxEntryMin {22, 26} × maxBarsHeld {48, 72} = 12 cells; exits pinned at the sweep-1 best-DSR cell (tpR=2.0, stopAtrMult=3.25). 12/12 executed.

### 3.3 Walk-Forward Protocol

Omitted — no cell reached SIGNIFICANT_EDGE, so the graduation/walk-forward gate was never unlocked.

## 4. Parameter Space Explored

| Axis | Values Tested |
|---|---|
| `tpR` | 2.0, 3.0, 4.0 (+ null-screen continuum 1.5–5.0) |
| `stopAtrMult` | 2.75, 3.25 (+ screen 2.0–5.0) |
| `maxBarsHeld` | 48, 72 (+ screen 24–96) |
| `rvolMin` | default 1.3, then 1.5, 1.7, 2.0 |
| `adxEntryMin` | default 20, then 22, 26 |

**Total iterations:** 24 formal (iterations 498–521) + 8 null-screen draws (no hypothesis_audit trials). Cumulative DSR trial count on the surface at the anchor cell: 12–16 (rising through the campaign).

**Edge verdict distribution:**

| Verdict | Count |
|---|---|
| SIGNIFICANT_EDGE | 0 |
| INSUFFICIENT_EVIDENCE | 24 |
| NO_EDGE_DETECTED (DISCARD) | 0 |

## 5. Results

### 5.1 Edge summary

Sweep 1 produced a **plateau, not a spike**: every one of the 12 exit-grid cells is profitable (PF 1.37–1.79), PF rises monotonically with stopAtrMult (3.25 > 2.75 in every pairing), is roughly flat in tpR, and n falls smoothly from 220 (tpR 2.0 / stop 2.75 / hold 48) to 129 (tpR 4.0 / stop 3.25 / hold 72). Eleven of twelve cells have PF-CI-low > 1.0; the twelfth is 0.9987. ag90 spans 36.5–68.5%/yr. The binding constraint in every cell is DSR (0.20–0.59): at trade-level Sharpe ≈ 0.8–1.2 and n ≈ 130–220, deflated certainty cannot reach 0.90.

Sweep 2 falsified the entry-quality escape route. rvolMin is a genuine PF lever (2.0/adx22 cells: PF 1.81–1.85, the surface's highest, CI-low ≈ 1.16) but the n cost (220→100) dominates the DSR arithmetic — best filtered DSR 0.34 vs unfiltered anchor 0.59. adxEntryMin tightening (22→26) uniformly destroys the edge (PF 1.24–1.56, all six cells CI-low < 1.0): ADX level at entry is not a conviction signal for 4h SOL breakouts.

Sweep-1 exit grid (full):

| iter | tpR | stop | hold | PF | CI-low | n | DSR | ag90 |
|---|---|---|---|---|---|---|---|---|
| 498 | 2.0 | 2.75 | 48 | 1.37 | 0.999 | 220 | 0.23 | 36.5 |
| 499 | 2.0 | 2.75 | 72 | 1.44 | 1.047 | 211 | 0.30 | 45.8 |
| 500 | 2.0 | 3.25 | 48 | 1.61 | 1.129 | 164 | 0.45 | 52.5 |
| **501** | **2.0** | **3.25** | **72** | **1.76** | **1.226** | **149** | **0.59** | **68.5** |
| 502 | 3.0 | 2.75 | 48 | 1.48 | 1.016 | 189 | 0.21 | 40.8 |
| 503 | 3.0 | 2.75 | 72 | 1.58 | 1.087 | 180 | 0.30 | 54.6 |
| 504 | 3.0 | 3.25 | 48 | 1.79 | 1.191 | 146 | 0.45 | 58.6 |
| 505 | 3.0 | 3.25 | 72 | 1.76 | 1.159 | 131 | 0.35 | 54.4 |
| 506 | 4.0 | 2.75 | 48 | 1.67 | 1.129 | 180 | 0.33 | 59.4 |
| 507 | 4.0 | 2.75 | 72 | 1.58 | 1.045 | 172 | 0.20 | 47.4 |
| 508 | 4.0 | 3.25 | 48 | 1.79 | 1.171 | 144 | 0.36 | 59.0 |
| 509 | 4.0 | 3.25 | 72 | 1.73 | 1.098 | 129 | 0.25 | 50.2 |

Sweep-2 quality grid (exits fixed tpR 2.0 / stop 3.25):

| iter | rvol | adx | hold | PF | CI-low | n | DSR | ag90 |
|---|---|---|---|---|---|---|---|---|
| 510 | 1.5 | 22 | 48 | 1.63 | 1.106 | 135 | 0.30 | 42.1 |
| 511 | 1.5 | 22 | 72 | 1.55 | 1.031 | 129 | 0.21 | 37.6 |
| 512 | 1.5 | 26 | 48 | 1.24 | 0.789 | 114 | 0.02 | 9.1 |
| 513 | 1.5 | 26 | 72 | 1.29 | 0.822 | 110 | 0.04 | 13.3 |
| 514 | 1.7 | 22 | 48 | 1.66 | 1.119 | 124 | 0.28 | 40.8 |
| 515 | 1.7 | 22 | 72 | 1.67 | 1.128 | 115 | 0.27 | 42.3 |
| 516 | 1.7 | 26 | 48 | 1.36 | 0.846 | 100 | 0.05 | 16.1 |
| 517 | 1.7 | 26 | 72 | 1.54 | 0.974 | 95 | 0.12 | 27.8 |
| 518 | 2.0 | 22 | 48 | 1.81 | 1.156 | 106 | 0.32 | 41.9 |
| 519 | 2.0 | 22 | 72 | 1.85 | 1.167 | 100 | 0.34 | 46.4 |
| 520 | 2.0 | 26 | 48 | 1.44 | 0.866 | 90 | 0.05 | 17.8 |
| 521 | 2.0 | 26 | 72 | 1.56 | 0.949 | 87 | 0.10 | 26.0 |

### 5.2 Best cell (anchors future comparisons)

| Param | Value |
|---|---|
| entryMode | BREAKOUT |
| intervalMinutes | 240 |
| tpR | 2.0 |
| stopAtrMult | 3.25 |
| maxBarsHeld | 72 |
| trailAtrMult | 0 |
| rvolMin / adxEntryMin | defaults (1.3 / 20) |

| Metric | Value |
|---|---|
| iteration_id | `98692470-8e8b-4b63-bfd3-0a35f5d067bc` (iteration 501) |
| n_trades | 149 |
| PF (point) | 1.7589 |
| PF 95% CI lower | 1.2263 |
| PF 95% CI upper | 2.5538 |
| DSR | 0.5904 |
| ag90 (%/yr) | 68.47 |
| Statistical verdict | INSUFFICIENT_EVIDENCE (DSR-blocked) |

Regime breakdown (canary cell 498, representative of the unfiltered grid): BULL n=98 PnL +17.1, NEUTRAL n=64 PnL +8.1, BEAR n=58 PnL +3.7 — positive in all three regimes; the edge is NOT a 2021-bull artifact. Post-sweep regime analysis (last cell): BULL PF 2.43 (n=57), NEUTRAL 1.33 (n=43), BEAR 1.11 (n=29), `is_promising=true`, but every strong pocket is n<100 and no SOL regime model exists — the ML-gated retry path is both unavailable and power-trapped.

## 9. Infrastructure Notes

Three findings this session, all documented in the journal with operator fixes:

1. **Orchestrator→inference DNS break (journal `8c4256d4`):** `blackheart-inference` was recreated 2026-06-27 without the `inference` network alias; the orchestrator's `/inference/*` proxy has returned 503 `inference_service_unreachable` ever since (session 2 mis-read this as "sidecar down"). Sidecar itself healthy. Workaround executed: the regime_eth_v2 backfill (25,607 rows) was driven directly against the sidecar on VPS host loopback. Operator fix: re-attach the network alias (or add `--network-alias inference` to the CI deploy).
2. **Research JVM memory regression (journal `c656782b`):** container running 1.5 GiB / -Xmx1400m — the 2026-06-18 bump to 3g / -Xmx2560m was lost in today's restart. A gated 1h backtest froze the whole JVM (HikariPool housekeeper delta 2m31s, all Kafka consumers timed out); the BT-REDELIVERY guard correctly marked the run FAILED instead of poison-looping. Un-gated 4h work (this campaign, 25 backtests) completes under the degraded limit. Operator fix: restore mem_limit 3g + -Xmx2560m on the hand-managed VPS compose (svc `research`).
3. The `bias.interval` higher-timeframe trend gate is a spec-BODY field, not a params field — it cannot be swept via `/queue`; testing it requires an operator spec deploy.

## 10. Methodology Compliance Audit

| Rule | Compliant? | Notes |
|---|---|---|
| Research universe (BTC/ETH/SOL/BNB/XRP) | YES | SOLUSDT |
| Intervals in {5m, 15m, 1h, 4h, 1d} | YES | 4h |
| Live trading untouched | YES | research account only |
| Research-mode only — no live promotion | YES | — |
| 10%/yr economic bar enforced | YES | ag90 reported per cell; no promotion claimed |
| V11 + V60 gates honored | YES | DSR 0.90 respected — no threshold pleading |
| ≥ 3 axes swept | YES | 5 axes across two grids |
| Pre-registration before testing | YES | both hypotheses registered before their sweeps |
| Append-only durable evidence | YES | falsification recorded as new STRATEGY_OUTCOME rows |
| Reviewer verdict authoritative | YES | both plans APPROVED before /queue (0 blockers) |
| No trading JVM calls | YES | orchestrator + read-only SSH diagnostics only |

## 11. Conclusions

1. **The 4h Donchian-breakout edge is real on SOLUSDT and finally adequately sampled:** 24/24 profitable cells, n up to 220 (7× the ETH-4h sample), positive in all three trend regimes, ag90 36–68%/yr in the unfiltered grid.
2. **DSR ≥ 0.90 is unreachable per-symbol on this surface:** with trade-level Sharpe ~0.8–1.2, neither more trades (n=220 cell: DSR 0.23) nor higher per-trade quality (PF 1.85 cell: DSR 0.34) closes the gap — the two levers trade off against each other.
3. **Entry-quality filtering is a PF lever but not a certification lever (hypothesis b5e877f0 FALSIFIED):** rvolMin 2.0 produced the surface's best PF (1.85) at exactly n=100, and adxEntryMin tightening destroys the edge.
4. **The mechanism is now confirmed real-but-underpowered on four of five universe symbols** (ETH n≈30, BNB n≈45, BTC trail-exit DSR-taxed, SOL n≈150–220 DSR 0.59) — the same failure mode everywhere: per-symbol Sharpe below certification at available n.
5. **Implication for the research loop:** the highest-EV certification path is the pooled multi-symbol DCB-4h book test — cross-symbol pooling is the only remaining lever that raises n and diversifies Sharpe simultaneously. It is blocked on the operator restoring the research JVM to 3g (multi-coin backtests OOM at 1.4G), with the `bias.interval=1d` spec variant as the secondary lever. Both are recorded as warm leads in the run marker for the next session.
