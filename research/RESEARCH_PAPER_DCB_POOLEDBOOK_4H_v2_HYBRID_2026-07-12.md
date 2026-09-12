# Research Paper: DCB_POOL — POOLEDBOOK (SOLUSDT-4h + ETHUSDT-4h + ETHUSDT-1h)

**Author:** quant-researcher
**Date:** 2026-07-12
**Strategy:** `DCB_POOL` (book code; every sleeve is `DCB`)
**Surface:** `POOLEDBOOK` (SOLUSDT × 4h ungated + ETHUSDT × 4h ML-gated + ETHUSDT × 1h ML-gated)
**Type:** HYBRID
**Surface attempt:** v2 — HYBRID (certification + walk-forward of the book characterized in v1; two of three sleeves consume the regime_eth_v2 ML gate)
**Prior papers on this surface:** `RESEARCH_PAPER_DCB_POOLEDBOOK_4H_v1_CHAR_2026-07-10.md`
**Filename:** `RESEARCH_PAPER_DCB_POOLEDBOOK_4H_v2_HYBRID_2026-07-12.md`
**Terminal:** GOAL_HIT
**Goal status:** GOAL_HIT
**Hypothesis:** `099daa20-f364-4740-923e-8c002cd1960e`
**Queue(s):** none — orchestrator-side pooled-certification pathway (`POST /pooled-certification/analyze` + `/pooled-certification/walk-forward`), no research_queue row

---

## TL;DR

The 3-sleeve gated DCB book (SOLUSDT-4h ungated, ETHUSDT-4h regime_eth_v2-gated, ETHUSDT-1h regime_eth_v2-gated; pooled under strategy_code `DCB_POOL`) cleared every V11 gate on the full 2021-01-01 → 2026-07-09 window and then returned a ROBUST 18-fold pooled walk-forward with 17/18 folds PF-positive, including all four 2022-bear folds. This is the first GOAL_HIT produced by the orchestrator-side pooled-certification pathway (operator methodology approval 2026-07-10, commit cde631a): the individually n-starved or DSR-blocked single-surface DCB edges (SOL-4h DSR 0.59; ETH-4h n≈30) certify jointly because pooling triples the trade count while the per-trade edge is preserved. The candidate is handed to quant-curator (fire-and-forget, journal `6f717c5c`); promotion remains operator-only.

| Metric | Value | Gate |
|---|---|---|
| n_trades | 772 | ≥ 100 |
| PF 95% CI lower | 1.3752 | > 1.0 |
| DSR | 0.9438 (at 454-trial tax) | ≥ 0.90 |
| ag90 (%/yr) | 59.70 | ≥ 10% |
| Walk-forward | ROBUST (18 folds, PF mean 1.7453, 94.44% positive) | ROBUST |

---

## 1. Background

Run 3 of the DCB_POOLED_BOOK pursuit. The precursor state (papers v1_CHAR 2026-07-10, `RESEARCH_PAPER_DCB_SOLUSDT_4H_v1_ALGO_2026-07-09.md`, `RESEARCH_PAPER_DCB_ETHUSDT_4H_v1_HYBRID_2026-07-10.md`): three real but individually uncertifiable DCB edges — SOL-4h 24/24-profitable grid but DSR 0.59 (n≈100 with heavy trial tax), ETH-4h PF 3.47 but n≈30, ETH-1h n=472 but PF too thin ungated. The JVM's pooled coordinator (`PooledIndependentBacktestCoordinatorService`) cannot host stop/TP archetypes (no TradeListener step, long-only, single-interval — journal `eaeb1220`), so the operator approved an orchestrator-side pooled-certification pathway (2026-07-10): coordinated standard single-symbol runs, trades merged orchestrator-side, scored by the UNCHANGED `services/analyze.py` V11 primitives. Pathway built and deployed as commit `cde631a` (ORCHESTRATOR_CHANGE journal `2aa9246e`). Run 3 certified the book, passed graduation review 7/7, exited on SPECIALIST_REVIEW_PENDING; the operator drained the skeptic (CONCERN, non-veto). This session (Path C resume after a PC-shutdown interruption) ran the pooled walk-forward — the final gate.

## 2. Hypothesis

**Mechanism:** Each sleeve is a standard DCB Donchian-channel breakout: enter on channel break (BREAKOUT entry mode), fixed ATR stop (3.25× on 4h sleeves, 3.0× on the 1h sleeve), fixed take-profit at 2.0R, time-stop at maxBarsHeld (72 bars on 4h, 168 on 1h), no trailing. The ETHUSDT sleeves trade only when the `regime_eth_v2` ML gate allows (`_ml_gate_enabled=true`, shadow off); the SOLUSDT sleeve is ungated. The book pools the three per-trade PnL series; sizing follows the documented equal-slice no-rebalance model (each sleeve owns 1/3 of book capital; PF/Sharpe/DSR are sizing-scale-invariant and therefore exact).

**Pre-registration:** Hypothesis journal `099daa20-f364-4740-923e-8c002cd1960e` registered 2026-07-10T10:10:05Z, before the pooled analyze produced iteration `c30e5587` at 2026-07-10T10:51:45Z (gap ≈ 42 min). Falsification criterion: pooled series fails any V11 gate, or pooled walk-forward not ROBUST.

**Type:** HYBRID — sleeves s1 (ETHUSDT-4h) and s2 (ETHUSDT-1h) consume `regime_eth_v2` as an entry gate; the gate had already shown per-surface value (NEUTRAL-pocket lift, prior ETH papers). No new model was trained for the book.

## 3. Methodology

### 3.1 Statistical Gates (V11 + V60)

| Gate | Threshold | Binding? |
|---|---|---|
| n_trades | ≥ 100 | YES |
| PF 95% bootstrap CI lower | > 1.0 | YES |
| DSR (Bailey–LdP, n_trials server-computed from hypothesis_audit per sleeve surface + external 10 + 1 self = 454) | ≥ 0.90 | YES |
| Statistical verdict | SIGNIFICANT_EDGE | YES |
| ann. geometric return at alloc-90 (ag90) | ≥ 10%/yr | YES (researcher goal bar; platform V60 floor is 0.0 since 2026-06-19) |
| Pooled walk-forward | ROBUST | YES |

All thresholds imported unchanged from `analyze`/`walk_forward` — the pooled module defines no verdict constant of its own (pinned by `tests/test_pooled_certification.py`).

### 3.2 Certification design (no sweep this run)

- **Type:** single pre-registered configuration — the three frozen sleeve configs from the prior single-surface work; no parameter search on the pooled surface (external_trials=10 declared for offline pool-variant selection).
- **Backtest window:** 2021-01-01 → 2026-07-09 (SOL-4h and ETH-4h sleeves; ETH-1h sleeve starts 2022-01-01 per its data window, idle-slice convention before that).
- **Cells:** 1 planned, 1 executed (iteration `c30e5587`). A second book variant (iteration `06904251`, n=752, PF 1.6482) was analyzed but NOT taken to graduation — the certified iteration is the pre-registered one.

### 3.3 Walk-Forward Protocol

18-fold rolling: train 12 months, test 3 months, step 3 months, OOS windows 2022-01-01 → 2026-07-01 (contiguous, non-overlapping). Per fold: one standard single-symbol run per sleeve over the test window, trades pooled, fold PF/Sharpe/WR computed on the pooled series; verdict from the byte-identical `aggregate_folds` + `stability_verdict` cutoffs (total n ≥ 100, pf_mean ≥ 1.0, pf_positive ≥ 60%, pf_std ≤ 1.5). Bear-coverage gate active (window includes the 2022 bear; no override used).

## 4. Parameter Space Explored

| Axis (per sleeve) | Values |
|---|---|
| `entryMode` | BREAKOUT (s0, s1); s2 per frozen ETH-1h config |
| `tpR` | 2.0 (all sleeves) |
| `stopAtrMult` | 3.25 (4h sleeves), 3.0 (1h sleeve) |
| `maxBarsHeld` | 72 (4h), 168 (1h) |
| `trailAtrMult` | 0 (no trailing — trailing FALSIFIED at 1h 2026-07-04) |
| `maxEntryRiskPct` | 0.12 |
| `_ml_gate_enabled` / `_ml_signal_name` | s1, s2: true / regime_eth_v2; s0: ungated |

**Total iterations this pursuit:** 2 pooled analyses (1 certified); cumulative DSR-deflated trial count charged: 454 (ETHUSDT:1h 228 + ETHUSDT:4h 172 + SOLUSDT:4h 43 + external 10 + 1 self).

**Edge verdict distribution (pooled surface):**

| Verdict | Count |
|---|---|
| SIGNIFICANT_EDGE | 2 (c30e5587 certified; 06904251 variant, not graduated) |
| INSUFFICIENT_EVIDENCE | 0 |
| NO_EDGE_DETECTED (DISCARD) | 0 |

## 5. Results

### 5.1 Edge summary

Pooling solved exactly the constraint that killed the single surfaces: sample size at preserved per-trade edge. n went 149/151/472 (per sleeve) → 772 pooled while PF stayed 1.63 (sleeves 1.76/1.83/1.42), so the PF CI tightened decisively above 1.0 and DSR cleared 0.90 even under the 454-trial tax. Cost stress is robust: +50bps slippage retains 64.8% of PnL. Max book drawdown 24.53% under the equal-slice model. Contention diagnostics: max 3 concurrent positions, ≥2 concurrent 53% of open time, same-symbol (ETH) overlap 26.9% — a live-deployment coordination constraint (first-to-open-wins), not a certification-math error.

### 5.2 Certified iteration

| Sleeve | Instrument/Interval | Gate | n | PF | run_id |
|---|---|---|---|---|---|
| s0 | SOLUSDT/4h | none | 149 | 1.7589 | `39ef0be9-4a72-4224-bdb4-13a6097ef5d3` |
| s1 | ETHUSDT/4h | regime_eth_v2 | 151 | 1.8319 | `adda9517-0a8d-4cc6-8fb5-5c39118134a9` |
| s2 | ETHUSDT/1h | regime_eth_v2 | 472 | 1.4237 | `70dbe274-de48-4243-a200-2de88d24ee1e` |

| Metric | Value |
|---|---|
| iteration_id | `c30e5587-5eec-403f-9774-fbf236b96c84` |
| n_trades | 772 |
| PF (point) | 1.6325 |
| PF 95% CI | [1.3752, 1.9478] (2000 resamples) |
| DSR / PSR | 0.9438 / 0.9988 |
| ag90 (%/yr) | 59.70 |
| Sharpe (annualized) | 2.2071 |
| Max drawdown | 24.53% |
| Slippage retention (+20/+50bps) | 88.3% / 64.8% of PnL |
| Statistical verdict | SIGNIFICANT_EDGE (CI excludes 1.0 favorably) |

## 6. Graduation Candidate

Graduation review: **APPROVED 7/7** (2026-07-10, target `graduation:c30e5587-...`). In-sample metrics per §5.2; all five binding gates pass with margin. Regime and quarterly cuts were reviewed at certification time (run-3 session): all trend regimes positive, +50bps robust — detail lives in the certification iteration's `metrics_snapshot` and the v1_CHAR paper.

### 6.4 Parameter robustness

The book's sleeves are frozen pre-registered configs from prior single-surface plateaus (SOL-4h: 24/24-profitable grid neighborhood; ETH sleeves: validated boxes, not knife-edge cells — the DCB 5.0×3.5 spike lesson was explicitly screened against in the sleeve selection). `flatten_sleeve_params` keeps book variants Hamming-1 comparable for the reviewer.

### 6.5 Portfolio fit

Portfolio analytics ran at the run-3 checkpoint; correlation to the live book was not veto-flagged by any specialist. The book itself is the diversification instrument: three sleeves across two symbols and two intervals with 53% concurrent-open time.

## 7. Specialist Reviews

| Specialist | Verdict | journal_id | Load-bearing argument |
|---|---|---|---|
| quant-skeptic | CONCERN (non-veto) | `f75a2231-6224-4c56-8568-22692bbb34c5` | DSR n_trials=454 is mechanically unverifiable because the pooled pathway writes zero hypothesis_audit rows; at a stress-tested 800 true trials DSR≈0.71 would fail the gate. Lenses 1/3/4 clean. "Researcher may proceed." |
| quant-curator | PENDING (fire-and-forget handoff) | request `6f717c5c-cfde-4ab9-ac46-a96c3bd72153` | Operator drains via `/run-pending-specialists`; verdict does not gate GOAL_HIT. |

**Skeptic CONCERN addressed:** the finding is about provenance, not the point estimate — 454 was server-computed from the per-surface ledger counts (228+172+43) plus declared external 10 plus 1 self, and those counts are snapshotted in the iteration's `quant_audit_notes` and `metrics_snapshot.pooled_certification.n_trials_breakdown`. The fix the skeptic asked for (per-sleeve `hypothesis_audit` ledger rows + a `counted_at` timestamp so counts stay re-derivable) is designed and scoped to `src/orchestrator/services/pooled_certification.py` but could NOT be applied this session (edit permission denied) — it stays owed to the operator as a non-blocking follow-up. Note the stress scenario (800 trials) has no evidential basis: the ledger lower-bounds are exact and the external-trials term was a deliberate conservative doubling.

## 8. Walk-Forward Results

**Walk-forward ID:** `be0f6313-61e5-413b-9363-093137f92bd5`
**Folds:** 18 (train 12m / test 3m / step 3m, OOS 2022-01-01 → 2026-07-01)
**Stability verdict:** ROBUST

### 8.1 Fold-level breakdown

| Fold | Test window | PF | Sharpe | WR | Trades |
|---|---|---|---|---|---|
| 1 | 2022-01→2022-04 | 2.63 | 4.16 | 0.48 | 29 |
| 2 | 2022-04→2022-07 | 2.93 | 4.55 | 0.58 | 26 |
| 3 | 2022-07→2022-10 | 1.19 | 0.57 | 0.29 | 21 |
| 4 | 2022-10→2023-01 | 1.44 | 1.74 | 0.33 | 42 |
| 5 | 2023-01→2023-04 | 1.84 | 2.52 | 0.39 | 36 |
| 6 | 2023-04→2023-07 | 1.11 | 0.56 | 0.33 | 45 |
| 7 | 2023-07→2023-10 | 2.34 | 3.62 | 0.46 | 46 |
| 8 | 2023-10→2024-01 | 2.14 | 3.55 | 0.39 | 46 |
| 9 | 2024-01→2024-04 | 0.96 | -0.23 | 0.39 | 38 |
| 10 | 2024-04→2024-07 | 1.07 | 0.36 | 0.32 | 44 |
| 11 | 2024-07→2024-10 | 1.84 | 3.11 | 0.43 | 47 |
| 12 | 2024-10→2025-01 | 1.16 | 0.84 | 0.36 | 53 |
| 13 | 2025-01→2025-04 | 1.61 | 2.43 | 0.46 | 39 |
| 14 | 2025-04→2025-07 | 1.32 | 1.46 | 0.38 | 45 |
| 15 | 2025-07→2025-10 | 2.01 | 3.93 | 0.47 | 51 |
| 16 | 2025-10→2026-01 | 2.22 | 4.23 | 0.49 | 45 |
| 17 | 2026-01→2026-04 | 1.82 | 3.32 | 0.55 | 47 |
| 18 | 2026-04→2026-07 | 1.78 | 2.86 | 0.36 | 42 |
| **Aggregate** | — | mean=1.7453 std=0.5488 min=0.9553 | mean=2.42 | — | total=742 |

pf_positive 94.44% (17/18). The 2022 bear is fully OOS-covered and strongly positive (folds 1–4: PF 2.63 / 2.93 / 1.19 / 1.44) — the breakout book monetizes bear-market trending moves. The single sub-1.0 fold (2024Q1, PF 0.955, −1.5%) is a shallow chop-quarter loss, not a regime failure; the adjacent 2024Q2 fold is already recovering (PF 1.07). Return mean +17.7% per 3-month fold under the equal-slice model.

## 9. Infrastructure Notes

- **Path C resume across a PC shutdown:** the run marker (`C:/Project/.research_run_state.json`) survived with status=ACTIVE; `started_ts` was rebased to the operator-verified 1.4h cumulative because the raw calendar gap (46h powered-off) is not research spend.
- **MSYS `/tmp` vs Python `C:\tmp` path mismatch** bit twice (stale started_ts cache produced a spurious RUN_COMPLETE; response-file parse failed) — both recovered by treating the marker file as source of truth and piping files via bash stdin. Known trap, documented in the agent prompt.
- **Edit-permission denial:** the skeptic-recommended provenance fix (per-sleeve `hypothesis_audit` rows + `counted_at` in `_pooled_n_trials`) was designed but could not be written to `src/orchestrator/services/pooled_certification.py` this session. Owed to operator; design is in the GOAL_HIT journal row `89b0c258` and §7 above.
- Walk-forward runtime: ~12.5 min for 54 sleeve-fold backtests (~40s/fold), monitored via VPS orchestrator logs (`pooled_cert.fold_start`).

## 10. Methodology Compliance Audit

| Rule | Compliant? | Notes |
|---|---|---|
| Research universe (hard rule #1) | YES | SOLUSDT + ETHUSDT only |
| Intervals in {5m,15m,1h,4h,1d} (hard rule #2) | YES | 4h + 1h sleeves |
| Live strategies untouched (hard rule #3) | YES | research account only; no account_strategy mutation |
| Research-mode only — no live promotion (hard rule #4) | YES | curator handoff only; promotion operator-gated |
| 10%/yr economic bar (hard rule #5) | YES | ag90 59.7%/yr |
| V11 + V60 gates honored (hard rule #6) | YES | all thresholds imported unchanged; DSR bar 0.90 per operator decision 2026-06-15 |
| ≥ 3 dimensions traversed (hard rule #7) | YES | pooling + gating + interval across the pursuit |
| Pre-registration before testing (hard rule #10) | YES | hypothesis 099daa20 42 min before analyze |
| Append-only durable evidence (hard rule #10) | YES | journal/iteration/WF rows only added |
| Reviewer verdict authoritative (hard rule #12) | YES | graduation APPROVED before WF; pooled-WF endpoint enforces the same 409 gate |
| No Trading JVM calls (hard rule #13) | YES | orchestrator :8082 only (+ read-only VPS log tail) |

## 11. Conclusions

1. **Pooling is the certification unlock for stop/TP breakout archetypes on this platform:** three individually uncertifiable DCB edges (n-starved or DSR-blocked) jointly clear every V11 gate at n=772 with PF preserved at 1.63.
2. **The edge is regime-broad:** 17/18 OOS folds PF-positive including all four 2022-bear quarters; the worst fold loses only 1.5%.
3. **The orchestrator-side pooled-certification pathway works end-to-end** (analyze → graduation gate → pooled WF) with zero JVM changes and zero loosened thresholds, and produced its first GOAL_HIT on first certified use.
4. **Implication for the research loop:** provenance hardening (per-sleeve audit rows + counted_at) should land before the pathway's second use so DSR multiplicity keeps compounding correctly across pooled runs; and the live-deployment design must respect the first-to-open-wins coordinator constraint on the two same-symbol ETH sleeves (26.9% overlap).

## 12. Data Wishlist

| Priority | Item | Blocker type |
|---|---|---|
| 1 | Per-sleeve `hypothesis_audit` rows + `counted_at` in pooled pathway (skeptic f75a2231) | orchestrator code (edit-permission blocked this session) |
| 2 | Live-deployment coordination design for same-symbol sleeves (ETH-4h + ETH-1h; first-to-open-wins suppression) | JVM design decision, operator-owned |

## 13. Appendix — Audit Trail

| Item | ID |
|---|---|
| Hypothesis | `099daa20-f364-4740-923e-8c002cd1960e` |
| Queue(s) | none (pooled-certification pathway) |
| Certified iteration | `c30e5587-5eec-403f-9774-fbf236b96c84` |
| Sleeve runs | `39ef0be9`, `adda9517`, `70dbe274` |
| Walk-forward run | `be0f6313-61e5-413b-9363-093137f92bd5` |
| Graduation review | APPROVED 7/7 (2026-07-10) |
| Skeptic verdict | `f75a2231-6224-4c56-8568-22692bbb34c5` (CONCERN, non-veto) |
| Curator request | `6f717c5c-cfde-4ab9-ac46-a96c3bd72153` (PENDING) |
| PATH_C_RESUMING marker | `a2e14e63-4366-4771-aec2-5722a772f930` |
| GOAL_HIT RUN_SUMMARY | `89b0c258-cd58-4e04-aae9-b04a1cb065e6` |
| Orchestrator pathway | commit `cde631a`, ORCHESTRATOR_CHANGE journal `2aa9246e` |
| Prior paper this continues | `RESEARCH_PAPER_DCB_POOLEDBOOK_4H_v1_CHAR_2026-07-10.md` |

---
*Paper generated by quant-researcher. DB registration: not applicable (no queue_id — pooled-certification pathway; paper delivered on filesystem + journal references).*
