# Research Paper: DCB — ETHUSDT × 1h

**Author:** quant-researcher
**Date:** 2026-07-09
**Strategy:** `DCB`
**Surface:** `ETHUSDT` × `1h`
**Type:** ALGO
**Surface attempt:** v12 — ALGO (close-out of the exit-study fixed-TP widening arm left pending by the 2026-07-03 session; regime-gated HYBRID follow-up queued but infra-blocked)
**Prior papers on this surface:** `v11_ALGO_2026-07-02`, `v10_ALGO_2026-06-20`, `v9_CHAR_2026-06-20`, `v8_HYBRID_2026-06-13`, `v7_ML_2026-06-02`, `v6_HYBRID_2026-06-02`, `v5_HYBRID_2026-05-30`
**Filename:** `RESEARCH_PAPER_DCB_ETHUSDT_1H_v12_ALGO_2026-07-09.md`
**Terminal:** INFRA_HARD_FAIL (research JVM degraded; run marker stays ACTIVE — session terminal, not run terminal)
**Goal status:** NOT HIT
**Hypothesis:** `a3940807-6864-4346-9421-edbaf030d35f` (falsified) → follow-up `fdb43c4f-1017-4770-b35f-e46b3ff4e3ae` (registered, un-executed)
**Queue(s):** `c5c9f491-83b0-4bd3-8531-a7bdd444036d` (FAILED, 8/12 cells scored) → `2d293da9-42c3-4b79-90d4-84438aa9675b` (PENDING, 0/8)

---

## TL;DR

This session completed the fixed-TP widening arm of the DCB-ETHUSDT-1h exit-dimension study left pending on 2026-07-03. All 8 completed cells (tpR {2,5} × stopAtrMult {3,5} × maxBarsHeld {96,168}, trailing off, 2022-01-01 onward) returned INSUFFICIENT_EVIDENCE with point PF 0.96–1.07 at n 333–719: widening or effectively removing the fixed take-profit does NOT beat the live incumbent tpR=2.0 config, and hypothesis a3940807 is falsified. Combined with the 2026-07-04 trailing-stop recheck (trailing falsified; 5.0×3.5 a knife-edge overfit), the exit dimension at ETHUSDT-1h is now closed in both directions. The single live thread is a post-hoc regime cut: step-8.5 regime analysis on the final cell returned is_promising=true — NEUTRAL-regime PF 1.356 (n=102, mean +0.81%/trade) vs BULL 1.03 / BEAR 0.89 — and a regime-gated HYBRID retry (ML gate `regime_eth_v2`, 8 cells mirroring the ungated twins for paired-delta) was pre-registered, plan-approved, and queued, but never executed: the research JVM degraded mid-session (two deterministic backtest FAILs, two ReadTimeouts, one 503 backtest-queue-saturation, then `/readyz` jvm=false on repeated probes) and the session exited INFRA_HARD_FAIL.

---

## 1. Background

Session start state (fresh 8.5h run, marker created 2026-07-09): `last_run_summary` = RESEARCH_RUN_COMPLETE_2026-07-02 (1h SWEEP_RECLAIM reversion falsified), no warm leads inherited (pre-v2 marker), queue PENDING=1. The 15m intraday price-action family is exhausted (soft fire 2026-07-01, now outside the 7d window); 1h ETH reversion falsified 2026-07-02; the DCB trailing-stop arm was falsified by the operator-side 2026-07-04 recheck. The resume protocol's queue-pending branch picked up queue c5c9f491 — the fixed-TP arm of the exit study (hypothesis a3940807), 7/12 cells done, all INSUFFICIENT_EVIDENCE.

Also probed this session: the Deribit options-surface historical load (loader commit 147e14a) was confirmed NEVER RUN — a feature backfill of `btc_rr25_skew_30d` for 2025-01 wrote 0 rows; live accrual only since 2026-06-16. IV-skew family remains data-gated (IDEA_BACKLOG 82245aea).

## 2. Hypothesis

**Mechanism (arm under test):** DCB Donchian-20 breakout entry on ETHUSDT 1h (live BREAKOUT mode), with the exit re-parameterized toward let-winners-run via the FIXED-TP path: tpR widened from the incumbent 2.0 to 5.0/10.0, stops widened (stopAtrMult 3.0/5.0), holds lengthened (maxBarsHeld 96/168), trailing disabled (trailAtrMult=0).

**Pre-registration:** hypothesis a3940807 registered 2026-07-03T09:41 before the queue (09:43). Falsification criterion: no widened-TP cell beats the incumbent on economics with V11 gates in reach.

**Type:** ALGO.

## 3. Methodology

### 3.1 Statistical gates (V11 + V60)

Standard: n≥100, PF 95% CI low > 1.0, DSR ≥ 0.90 (operator-lowered 2026-06-15), SIGNIFICANT_EDGE, ag90 ≥ 10%/yr. Slippage haircut audit-only.

### 3.2 Sweep design

- **Type:** GRID, seed 42
- **Backtest window:** 2022-01-01 → run date (~54 months)
- **Dimensions:** tpR {2.0, 5.0, 10.0} × stopAtrMult {3.0, 5.0} × maxBarsHeld {96, 168}; pinned trailAtrMult=0, intervalMinutes=60, maxEntryRiskPct=0.12
- **Total cells:** 12 planned, 8 executed. Cells 9–12 (the tpR=10.0 arm beyond the first) were not scored: the iter-9 cell failed deterministically at the JVM twice (backtest runs `34a027af`, `86695f10`, terminal FAILED with infra healthy on re-probe), and the 2026-07-04 stop-width recheck independently established the wide arm is worse than the incumbent — the missing cells cannot change the verdict.

## 4. Parameter Space Explored

| Axis | Values Tested |
|---|---|
| `tpR` | 2.0, 5.0 (10.0 arm aborted) |
| `stopAtrMult` | 3.0, 5.0 |
| `maxBarsHeld` | 96, 168 |

**Total iterations:** 8 scored (queue-local 1–8; global iteration numbers include 496, 497)

**Edge verdict distribution:**

| Verdict | Count |
|---|---|
| SIGNIFICANT_EDGE | 0 |
| INSUFFICIENT_EVIDENCE | 8 |
| NO_EDGE_DETECTED (DISCARD) | 0 |

## 5. Results

### 5.1 Edge summary

PF clustered tightly around 1.0 (0.96–1.07) across every cell — the widened-TP surface is flat and edgeless, not frequency-starved (n 333–719 everywhere). The binding constraint is the PF CI spanning 1.0 on every cell; DSR ~0 throughout. Neither wider stops nor longer holds moved the needle: the exit axes are no-ops on top of a marginal unconditional entry. Conclusion matches v10/v11 and the 2026-07-04 recheck: the live fixed-TP tpR=2.0/24-bar configuration is the local optimum of the exit dimension at this surface, and no exit re-parameterization (trailing OR fixed-TP widening) rescues it.

### 5.2 Best cell

| Param | Value |
|---|---|
| `tpR` | 5.0 |
| `stopAtrMult` | 5.0 |
| `maxBarsHeld` | 168 |

| Metric | Value |
|---|---|
| iteration_id | 2cc8101b-c076-497a-b18e-570ec38206a2 |
| n_trades | 333 |
| PF (point) | 1.0734 |
| PF 95% CI | spans 1.0 (INSUFFICIENT_EVIDENCE) |
| DSR | ~0 |
| Statistical verdict | INSUFFICIENT_EVIDENCE |

### 5.3 Regime breakdown of the best cell (the live thread)

| Regime | n | PF | WR | mean ret/trade |
|---|---|---|---|---|
| BULL | 147 | 1.031 | 26.5% | +0.08% |
| NEUTRAL | 102 | 1.356 | 38.2% | +0.81% |
| BEAR | 84 | 0.887 | 27.4% | -0.36% |

`POST /regime-analysis/c5c9f491` returned is_promising=true (best_pf 1.356 ≥ 1.15, n=102 ≥ 10) and recommended the ML regime gate `regime_eth_v2` (trained lightgbm_modulator, purpose=regime, ETHUSDT@1h — registry ba9cd46f/6b3b12e4). Caveat honored in the follow-up design: this is a post-hoc cut on ONE cell; the Stage-H precedent (regime_btc_v3 destroyed DCB value in the only prior paired test) makes the paired-delta gate mandatory before any graduation claim.

## 9. Follow-up in flight (blocked)

Hypothesis `fdb43c4f` (HYBRID, anchored continuation, pursuit 1/3 on family DCB_EXIT_ETH1H): 8 gated cells mirroring the completed ungated twins exactly (tpR {2,5} × stop {3,5} × maxBars {96,168}, `_ml_gate_enabled=true`, `_ml_signal_name=regime_eth_v2`, `_ml_shadow_mode=false`), enabling paired-delta via iteration_ids against the off-twins. Plan approved (`plan:DCB:4239f2ff...:fdb43c4f`), queued as `2d293da9`. Includes a fail-open detector: if the first gated cell is bit-identical to its off-twin, signal_history lacks historical regime_eth_v2 rows and the retry is void as a data gap (not evidence). Execution blocked by JVM degradation; queue stays PENDING for the next session's queue-pending resume branch.

## 10. Infrastructure post-mortem (session terminal)

Ladder observed: iter-9 backtest FAILED ×2 (deterministic, ~12–19 min in, infra probes healthy) → drain ReadTimeout on submit → JVM 503 "Backtest queue is temporarily unavailable" → second ReadTimeout → `/readyz` jvm=false on two probes ≥10 min apart. Interpretation: timed-out submissions left orphaned backtests stacking on the research JVM (3GB heap), saturating its backtest queue and eventually its health probe. Session retry budget burned 6→2 before the INFRA_HARD_FAIL terminal fired. Operator action needed: restart the research JVM service on the VPS (svc key `research`); the pending queue and marker resume automatically afterward.

## 11. Verdict and disposition

- Hypothesis a3940807 **FALSIFIED** (STRATEGY_OUTCOME e872313f). Exit dimension at DCB-ETHUSDT-1h closed in both directions (trailing 2026-07-04, fixed-TP widening this paper).
- Family DCB_EXIT_ETH1H graded **WARM** (regime lead), pursuit 1/3 claimed by follow-up fdb43c4f — the family lead-bans at 3 pursuits without a HOT per the anti-knife-edge cap.
- DB paper: `BH-DCB-ETHUSDT-1H-c5c9f491`.
- Next session: drain queue 2d293da9 (fail-open detector first), else fall to the pre-staged DCB-SOLUSDT-4h BREAKOUT direction (null-screen gate; drafts in `.rtmp/hyp-sol4h.json`, `.rtmp/null-screen-sol4h.json`).
