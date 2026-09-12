# Research Paper: DCB — ETHUSDT × 4H

**Author:** quant-researcher
**Date:** 2026-07-10
**Strategy:** `DCB`
**Surface:** `ETHUSDT` × `4h`
**Type:** HYBRID
**Surface attempt:** v1 — HYBRID (standardized fixed-TP box measured ungated, then regime-gated retry per orchestrator regime_retry recommendation)
**Prior papers on this surface:** none (the 2026-06-14 ETH-4h deep-TP study, PF 3.47 n~30, predates the paper rule and used a different box)
**Filename:** `RESEARCH_PAPER_DCB_ETHUSDT_4H_v1_HYBRID_2026-07-10.md`
**Terminal:** WALL_CLOCK_CAP (run continues to cumulative cap; no graduation this session)
**Goal status:** NOT HIT — DSR is the sole failing V11 gate on every candidate cell
**Hypothesis:** `0a0a81a5` (ungated box), `bc91350e` (gated retry)
**Queue(s):** `6762447f` (ungated), `75937702` (gated); siblings `43b70ded` (ETH-1h gated), `7b3710d8` (BNB-4h), `6f7eebc5` (XRP-4h)

---

## TL;DR

This session measured the SOL-validated standardized Donchian-breakout box (fixed TP, no trail) on ETHUSDT-4h, first ungated and then gated by the `regime_eth_v2` ML signal, after the operator restored the research JVM to 3g heap. Ungated, all 8 cells are profitable (PF 1.20–1.41, n 179–248) but none clears PF-CI-low 1.0. Regime analysis showed the edge lives entirely in trending regimes (BULL PF 1.50, BEAR PF 1.88) and dies in chop (NEUTRAL PF 0.95). The gated retry converted the surface: 7/8 cells clear PF-CI-low (best PF 1.94, ciL 1.263, n=131, ag90 53.4%/yr) — but DSR (0.06–0.37 vs 0.90 at ~170 cumulative trials) blocks certification, exactly as pre-registered. Sibling box measurements falsified BNB-4h and XRP-4h (both PF≈1.0, ag90 negative), fixing the box map at SOL strong / ETH gated-strong / BTC+BNB+XRP dead. The certification path for this family is a pooled multi-sleeve book (operator-gated; DATA_WISHLIST journal `896fbbcf`).

| Metric (best gated cell b59a4f15) | Value | Gate |
|---|---|---|
| n_trades | 131 | ≥ 100 PASS |
| PF 95% CI lower | 1.2629 | > 1.0 PASS |
| DSR | 0.273 | ≥ 0.90 **FAIL** |
| ag90 (%/yr) | 53.4 | ≥ 10% PASS |
| Walk-forward | not run (no SIGNIFICANT_EDGE) | ROBUST |

---

## 1. Background

Session start state (run started 2026-07-10, fresh marker seeded from RESEARCH_RUN_COMPLETE_2026-07-09 warm leads): the DCB-4h breakout family had a confirmed-but-DSR-blocked edge on SOLUSDT (24/24 profitable cells, PF 1.37–1.85, DSR max 0.59), BTC-4h was null-screen-killed both directions, and two prerequisite ETH re-queues (`ac7aca2e` box, `762d2d1c` gated 1h grid) had been infra-killed by a 1.5g JVM memory regression. The operator restored mem_limit 3g / -Xmx2560m and the orchestrator→inference DNS alias on 2026-07-10; both re-queues replayed cleanly this session (zero backtest failures across 40 iterations). This paper documents the ETHUSDT-4h surface; the pooled-book context (SOL, BNB, XRP siblings) is included because the ETH-4h measurement exists to serve the pooled certification design.

## 2. Hypothesis

**Mechanism:** DCB enters long on a Donchian-channel BREAKOUT close, sizes at maxEntryRiskPct 0.12, exits at a fixed take-profit of tpR × initial risk (R), a stop at stopAtrMult × ATR, or a time stop at maxBarsHeld bars. No trailing (trailAtrMult=0). In the gated variant, the `regime_eth_v2` LightGBM regime signal (served from signal_history, 25,607 rows backfilled 2022→now) must permit entry via the RiskGuard ML gate (`_ml_gate_enabled=true`, `_ml_shadow_mode=false`).

**Pre-registration:** Hypothesis `0a0a81a5` (prior session, plan review APPROVED, predicted PF-CI-low>1.0 at n 80–130); hypothesis `bc91350e` registered 2026-07-10 ~07:5x UTC, before the earliest gated iteration (~08:1x UTC). Falsification criterion for the gated retry: fewer than 2/8 cells with PF-CI-low > 1.0 at n ≥ 100.

**Type:** HYBRID. The ML signal is `regime_eth_v2` — chosen because (a) the orchestrator's regime analysis on queue `6762447f` returned is_promising=true with a NEUTRAL-regime bleed, and (b) the same gate had just lifted PF-CI-low past 1.0 on ETHUSDT-1h (queue `43b70ded`, journal `02ccfeb5`), giving a cross-surface prior.

## 3. Methodology

### 3.1 Statistical Gates (V11 + V60)

| Gate | Threshold | Binding this session? |
|---|---|---|
| n_trades | ≥ 100 | passed everywhere (131–248) |
| PF 95% bootstrap CI lower | > 1.0 | ungated: binding (0/8); gated: passed 7/8 |
| DSR (Bailey–LdP, n_trials from hypothesis_audit) | ≥ 0.90 | **binding everywhere** (0.06–0.37 at trials 161–172) |
| ann. geometric return at alloc-90 (ag90) | ≥ 10%/yr | passed on all gated cells (28–57%/yr) |

### 3.2 Sweep Design

- **Type:** GRID (8 cells each, seed 42)
- **Backtest window:** 2021-01-01 → now (~5.5 years, 22 quarters)
- **Dimensions swept:** tpR {2.0, 3.0} × stopAtrMult {2.75, 3.25} × maxBarsHeld {48, 72}; fixed entryMode=BREAKOUT, intervalMinutes=240, trailAtrMult=0, maxEntryRiskPct=0.12; gated variant adds `_ml_gate_enabled=[true]`, `_ml_signal_name=[regime_eth_v2]`, `_ml_shadow_mode=[false]`
- **Total cells:** 8 planned / 8 executed (ungated) + 8/8 (gated); zero failures

### 3.4 Paired-Delta Design

Not a paired sweep — the gate is always-on within queue `75937702` (the ungated `6762447f` serves as the between-queue baseline). Formal `/paired-delta` therefore does not apply; the deltas below are cell-matched across the two queues.

## 4. Parameter Space Explored

| Axis | Values Tested |
|---|---|
| `tpR` | 2.0, 3.0 |
| `stopAtrMult` | 2.75, 3.25 |
| `maxBarsHeld` | 48, 72 |
| `_ml_gate_enabled` | (off — queue 6762447f) / true (queue 75937702) |

**Total iterations:** 16 on this surface (cumulative DSR trial count reached ~172)

**Edge verdict distribution (this surface):**

| Verdict | Count |
|---|---|
| SIGNIFICANT_EDGE | 0 |
| INSUFFICIENT_EVIDENCE | 16 |
| NO_EDGE_DETECTED (DISCARD) | 0 |

## 5. Results

### 5.1 Edge summary

Ungated (queue `6762447f`): a genuine plateau — all 8 cells PF 1.20–1.41 with n 179–248; PF-CI-low 0.88–0.984; best ag90 ≈ 30%/yr equivalent. No knife-edge: the whole box is profitable, thin. Binding constraint: PF CI width, then DSR. Regime analysis (`entry_trend_regime`, 179 trades classified): BULL PF 1.5036 (n 74), BEAR PF 1.8819 (n 44), NEUTRAL PF 0.9531 (n 61) — is_promising=true.

Gated (queue `75937702`): the gate removed the NEUTRAL bleed and lifted the whole plateau. 7/8 cells PF-CI-low > 1.0 (1.006–1.273). Cell-matched deltas vs ungated: PF +0.15 to +0.53, n −25% to −35%, ag90 roughly doubles. The one miss (tpR 2.0/stop 2.75/hold 72, ciL 0.9994) is the loosest-stop widest-hold cell. Binding constraint after gating: DSR alone — 0.06–0.37 against 0.90 with cumulative_trials 165–172 on this heavily-mined surface.

### 5.2 Best cell (gated)

| Param | Value |
|---|---|
| `tpR` | 3.0 |
| `stopAtrMult` | 3.25 |
| `maxBarsHeld` | 72 |
| `_ml_signal_name` | regime_eth_v2 |

| Metric | Value |
|---|---|
| iteration_id | b59a4f15-79e6-4b04-b75f-d74c5e732273 |
| n_trades | 131 |
| PF (point) | 1.9380 |
| PF 95% CI lower | 1.2629 |
| DSR | 0.273 |
| ag90 (%/yr) | 53.43 |
| Statistical verdict | INSUFFICIENT_EVIDENCE (DSR) |

Runner-up: `ffac4614` (tpR 2.0/stop 3.25/hold 72): PF 1.8319, ciL 1.2725, n=151, DSR 0.3702, ag90 56.79 — the highest-ciL cell, more trades, nearly the same economics. The plateau (4 cells at ciL ≥ 1.236) is the robustness argument: this is not a spike.

## 9. Infrastructure Notes

1. **Review-gate axis hashing:** `POST /queue` computes the plan-review target hash from the FULL sweep param name list (fixed single-value axes included). A review filed with only the swept axes 409s with `review_required`. Re-file the review with all param names (hit on queue `7b3710d8`, resolved same session).
2. **Journal status updates:** no HTTP endpoint exists to flip a HYPOTHESIS to FALSIFIED (PATCH /journal/{id} → 405). Falsifications for `451eabad` (BNB) and `da1e610a` (XRP) are recorded content-level in journals `ad4d0a82` / `b14b6c64`; operator psql flip requested in `896fbbcf`.
3. **Trial-tax scoping (load-bearing):** `cumulative_trials` in the DSR is per-(symbol, interval): BNB-4h ran at 46–48, XRP-4h at 11–18, ETH-4h at 161–172, ETH-1h at 222. Fresh surfaces carry low tax — but the two fresh surfaces measured this session had no edge to certify.
4. JVM at 3g / inference DNS alias: both fixes held; 40/40 iterations completed with zero backtest failures at ~2.5 min/cell (4h) and ~10 min/cell (1h gated).

## 10. Methodology Compliance Audit

| Rule | Compliant? | Notes |
|---|---|---|
| Universe BTC/ETH/SOL/BNB/XRP (hard rule #1) | YES | ETH, BNB, XRP surfaces this session |
| Intervals in {5m, 15m, 1h, 4h, 1d} (hard rule #2) | YES | 4h and 1h |
| Research never mutates live (hard rule #3) | YES | backtest copies only; live DCB rows untouched |
| Research-mode only — no live promotion (hard rule #4) | YES | no promotion calls |
| 10%/yr economic bar enforced (hard rule #5) | YES | ag90 gate passed but candidates not advanced (DSR) |
| V11 + V60 gates honored (hard rule #6) | YES | no threshold moved; DSR verdicts accepted |
| ≥ 3 dimensions traversed (hard rule #7) | YES | exit (tpR/stop), holding, regime-gate |
| Pre-registration before testing | YES | hypotheses 0a0a81a5, fdb43c4f, 451eabad, da1e610a, bc91350e all pre-dated their sweeps |
| Append-only durable evidence (hard rule #10) | YES | no rows deleted/modified (status flips deferred to operator) |
| Reviewer verdict authoritative (hard rule #12) | YES | every queue behind an APPROVED plan review |
| No Trading JVM calls (hard rule #13) | YES | orchestrator :8082 only |

## 11. Conclusions

1. **The regime gate is the ETH-4h box's missing component:** gated 7/8 cells clear PF-CI-low vs 0/8 ungated, with PF up to 1.94 and ag90 up to 57%/yr (queues 6762447f vs 75937702, cell-matched).
2. **regime_eth_v2 now shows the same lift on two surfaces:** ETH-1h (6/8 ciL>1.0, best 1.167 at n=472) and ETH-4h (7/8, best 1.273) — the gate's value is a cross-surface pattern, not a single-surface artifact.
3. **DSR is a structural blocker on mined surfaces, not an edge-quality verdict:** every other V11 gate passes on the best cells of three surfaces; DSR 0.06–0.59 under per-surface trial taxes of ~170–222 cannot be closed by any honest parametric axis.
4. **The 4h breakout box is not a universal high-beta effect:** BNB-4h and XRP-4h falsified (best PF 1.07, ag90 negative); the box map is SOL strong / ETH gated-strong / BTC+BNB+XRP dead.
5. **Implication for the research loop:** the family's only certification path is a pooled multi-sleeve run (SOL-4h + gated ETH-4h + gated ETH-1h, n ~750+ diversified) — operator-gated on a pooled account_strategy seed (DATA_WISHLIST `896fbbcf`); until seeded, further single-surface DCB sweeps are negative-EV.
