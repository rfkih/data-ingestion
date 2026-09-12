# RESEARCH PLAN 2026-07-10 — DCB_POOLED_BOOK orchestrator-side pooled certification

## Premise

1. Prior run (RUN_SUMMARY `ec35299a`) closed on the operator-decision point of warm lead
   **DCB_POOLED_BOOK**: offline pooled evidence (journal `ef8b3942`) shows the 3-sleeve book
   (SOLUSDT-4h ungated + ETHUSDT-4h regime_eth_v2-gated + ETHUSDT-1h regime_eth_v2-gated)
   at n=772, PF 1.633 CI[1.365, 1.946], Sharpe_ann 2.21, DSR 0.963 at the WORST-CASE
   222-trial tax, 6/6 profitable years, sleeve monthly-PnL correlations 0.18 / 0.12 / −0.27.
2. The JVM pooled coordinator is ENGINE-BLOCKED for stop-based archetypes (journal `eaeb1220`:
   no intra-bar listener, allowShort hardcoded false, single interval, no ML-gate wiring) —
   POOLED_INDEPENDENT runs for DCB remain OUT OF SCOPE (operator confirmed; do not queue).
3. **Operator approval 2026-07-10** (this run's directive): build the orchestrator-side pooled
   certification pathway — coordinated single-symbol per-fold runs through the STANDARD
   verified coordinator, pool the trade series orchestrator-side, apply **UNCHANGED V11
   thresholds**, WF-equivalent ROBUST on the pooled series. Approval covers ADDING the
   pathway in the orchestrator edit zone; gate semantics stay frozen.
4. Hypothesis pre-registered: `099daa20-f364-4740-923e-8c002cd1960e` (kind=ALGO, DCB_POOL).
5. Anchored continuation of the popped warm lead (pursuit 1/3); novelty clause does not apply.

## Constraints reaffirmed

- Research universe BTC/ETH/SOL/BNB/XRP; intervals 5m/15m/1h/4h/1d. Sleeves: SOL-4h, ETH-4h, ETH-1h — in scope.
- Research never mutates live trading; DCB_POOL rows are `enabled=false, simulated=true`.
- V11+V60 gates UNCHANGED: n≥100, PF 95% CI-low>1.0, DSR≥0.90 (cumulative-trial scaled),
  walk-forward stability cutoffs byte-identical to `services/walk_forward.stability_verdict`.
- GOAL bar: annualized_geometric_return_pct_at_alloc_90 ≥ 10 AND pooled WF ROBUST.
- Reviewer gates: plan review before compute; graduation review before pooled walk-forward
  (the new endpoint enforces the same `graduation_review_required` 409 as `/walk-forward`).

## Experiment E1 — build the pathway (orchestrator edit zone)

Two synchronous endpoints (platform style = long synchronous handlers, agent backgrounds the curl):

- **`POST /pooled-certification/analyze`** — body: book strategy_code (`DCB_POOL`), sleeves[]
  (strategy_code, instrument, interval_name, window_start, overrides incl. `_ml_*` sentinels),
  full_end, external_trials, motivating_hypothesis_id. For each sleeve: submit ONE standard
  single-symbol backtest over its full window (same `_build_payload` semantics as
  `services/walk_forward.py` — ML sentinels split via `sweep.split_ml_overrides`), poll to
  COMPLETED, fetch trades. Pool trades across sleeves; score with `services/analyze.py`
  primitives UNCHANGED (bootstrap PF CI seed 42 B=2000, per-obs Sharpe, Bailey-LdP DSR with
  bootstrap fallback, `statistical_verdict`, `decision_verdict`). n_trials = Σ over DISTINCT
  sleeve (instrument, interval) of `hypothesis_audit.count_data_universe_trials` + external
  + 1 (monotone: caller can only RAISE). Writes a `research_iteration_log` row
  (strategy_code=DCB_POOL, backtest_run_id=NULL, params_snapshot=sleeve configs, metrics
  compatible with the graduation checklist: `metrics_snapshot.analysis.*` +
  `confidence_intervals.pf_95`). Returns iteration_id + pooled metrics + contention diagnostics.
- **`POST /pooled-certification/walk-forward`** — body: pooled iteration_id + fold params
  (train12/test3/step3, n_folds≤20). GATES: same `graduation_review_required` 409 as
  `/walk-forward` (APPROVED graduation verdict on the pooled iteration_id required); same
  bear-coverage rejection; same overlapping-folds rejection. Reads sleeve configs from the
  pooled iteration's params_snapshot (single source of truth). Per fold × sleeve: standard
  single-symbol run on the fold TEST window; pool the fold's trades across sleeves; per-fold
  pooled metrics; aggregate with the SAME `aggregate_folds` + `stability_verdict` cutoffs
  (n≥100 total, pf_mean≥1.0, pf_positive≥60%, pf_std≤1.5 → ROBUST). Sleeves whose data starts
  after a fold's test_start simply contribute zero trades to that fold (documented; matches
  E3b convention). Writes ONE `walk_forward_run` row (strategy_code=DCB_POOL,
  interval_name="pooled", instrument="SOLUSDT,ETHUSDT", fold_results carrying per-sleeve
  run_ids per fold + validation summary).

### Economic-return model (shared-equity-contention approximation — reviewer-auditable)

- Pooling merges per-trade `realized_pnl_amount` of INDEPENDENT full-capital runs. Per-trade
  PF / Sharpe / DSR are sizing-scale-invariant → first-order exact for an equal-slice book.
- Book return model: **equal-slice, no-rebalance**. Each of K sleeves owns 1/K of book
  capital and compounds internally at the JVM's own alloc-90 semantics
  (`geometric_return_pct_at_alloc_90` of that sleeve's run, computed by the verified engine).
  Book multiplier M_book = (1/K)·Σ M_i over the COMMON calendar window; a late-start sleeve
  (ETH-1h, 2022+) idles at M=1 for the uncovered prefix — honest drag, no backfill.
  `annualized_geometric_return_pct_at_alloc_90` = `analyze.annualize_geometric_return`
  ((M_book−1)·100, common window days). UNCHANGED gate function; new is only the documented
  book-level sizing model.
- **Bound**: the slice model never over-deploys (Σ slices ≤ 90% of book even with all three
  concurrently open — no margin contention by construction) and claims no cross-sleeve
  cash reuse (when 1 sleeve is active the other slices idle — return is UNDERSTATED vs an
  adaptive shared-cash book). Both directions conservative. Residual unmodeled effect:
  same-symbol ETH-4h+ETH-1h concurrent positions on one live account (platform coordinator
  is first-to-open-wins) — a DEPLOYMENT constraint, not certification math; reported as
  `same_symbol_overlap` diagnostic and flagged for the operator in the graduation package.
- Diagnostics reported: pct of open-time with ≥2 / 3 concurrent positions, max concurrent,
  same-symbol overlap pct, per-sleeve replication check vs reference iterations.

### Multiplicity honesty

- DB-derived floor: Σ count_data_universe_trials over {(SOLUSDT,4h), (ETHUSDT,4h), (ETHUSDT,1h)}.
- `external_trials=8` declared on top: offline pooled-config selection in E3b examined 3 pool
  variants + cell-box scanning not otherwise attributable (margin of safety). DSR moves
  ~0.001 per +10 trials at this n — immaterial but honest.
- Certification re-runs of the FROZEN pre-registered configs are confirmatory, not selection
  → no new hypothesis_audit trial rows (mirrors existing /walk-forward fold-run precedent).

### Tests + practice (contract §Code authority)

- `PYTHONPATH=src pytest -q` green before deploy; new unit tests for: pooled stats parity with
  analyze_run on a synthetic merge; slice-model return math incl. late-start sleeve; fold
  pooling with a sleeve absent from early folds; graduation-gate 409; bear-coverage 409;
  V11-constant pin (thresholds imported from analyze/walk_forward, never redefined).
- `GET /agent/playbook` updated with both endpoints.
- ORCHESTRATOR_CHANGE journal row with rationale + motivating iteration ids.
- Deploy via repo CI (public repo, Actions green, auto-deploy with healthcheck+rollback).

## Experiment E2 — run the certification

1. `POST /pooled-certification/analyze` with the 3 frozen sleeves (windows: SOL-4h 2021-01-01→,
   ETH-4h 2021-01-01→, ETH-1h 2022-01-01→; common end = yesterday UTC).
   - Success: pooled n≥700, PF CI-low>1.0, DSR≥0.90 at server trials, verdict SIGNIFICANT_EDGE,
     slice-model ann≥10%/yr. Replication tolerance vs E3b: PF point within ±0.1, n within ±5%.
   - Branch NOT significant → journal STRATEGY_OUTCOME (family dead-end for this axis), grade
     per warmth taxonomy, back to step 1. Branch replication mismatch (>tolerance) → treat as
     methodology bug, investigate before ANY further claim; do not proceed to review.
2. Graduation review (9a/9b) on the pooled iteration_id; then Path-C specialist checkpoint (9d):
   skeptic-prescreen, portfolio correlations/optimize, specialist-review requests, exit
   SPECIALIST_REVIEW_PENDING. (param_robustness WARNING on empty DCB_POOL sweep history is
   EXPECTED and accepted — book-level neighborhood evidence lives in the underlying DCB sweeps
   + E3b pool variants; if it stacks to 2 WARNING fails → REJECTED, follow OPERATOR_ESCALATION
   conditions if met, else STRATEGY_OUTCOME.)
3. After specialist verdicts (next session, no veto): `POST /pooled-certification/walk-forward`
   (train12/test3/step3, n_folds=18, window 2021-01-01→now — covers the 2021-11→2022-12 bear).
   - ROBUST + ann≥10 → GOAL_HIT protocol (incl. fire-and-forget quant-curator handoff).
   - INCONSISTENT/OVERFIT/NO_EDGE → STRATEGY_OUTCOME, grade DEAD for this axis, next archetype.

## Execution order (this session)

1. ✅ marker + state + lead pop + hypothesis `099daa20`
2. this plan → plan review → APPROVED required before E1 compute runs
3. E1 build + tests + deploy + playbook + ORCHESTRATOR_CHANGE journal
4. E2.1 analyze phase (background curl + marker heartbeat loop)
5. E2.2 graduation review + specialist requests → SPECIALIST_REVIEW_PENDING exit

## Decision criteria for next session

- Specialist verdicts in, no veto → resume protocol jumps to pooled walk-forward (E2.3).
- Any veto → STRATEGY_OUTCOME with the veto reason; DCB_POOLED_BOOK pursuit 2/3 may address a
  CURABLE objection (e.g. portfolio overlap weighting) once; else grade DEAD.
- WF ROBUST + ann≥10 → GOAL_HIT; operator decides promotion (multi-account deployment note:
  ETH sleeves need separate accounts or accepted suppression).
