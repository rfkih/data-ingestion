# RESEARCH PLAN 2026-07-13 (v3) — TPB_POOL breadth extension (operator-provisioned ADA/DOGE/AVAX @4h)

> Supersedes RESEARCH_PLAN_2026-07-13.md (v2, TPB core run — terminated
> ARCHETYPE_EXHAUSTION_2026-07-13 with the SOL+XRP core certified real-but-thin).
> This plan executes the operator's breadth unlock: TPB@4h seeds + verified 4h
> feature_store for ADAUSDT/DOGEUSDT/AVAXUSDT — the prior run's #1 warm-lead next_axis.

## Premise

- Prior run (RUN_SUMMARY `a43e1749`) certified the TPB two-sided trend-pullback edge as REAL-but-thin on
  the SOL+XRP core: pooled iteration `42e5d72c` n=52, PF 2.056, PF 95% CI [1.049, 3.924], DSR 0.044@209
  trials, ann90-slice 9.29%/yr → INSUFFICIENT_EVIDENCE; padding to n≥100 explicitly declined.
- The WARM lead's next_axis was "operator-gated breadth: seed TPB@4h on ADA/DOGE/AVAX". Operator provisioned
  EXACTLY that (2026-07-13): TPB@4h `account_strategy` rows on research account 99999999-…-0002 (verified via
  GET /account-strategies/research), full 4h feature_store back to 2020 (bear-pullback raw signals ADA 153 /
  DOGE 195 / AVAX 102; ADA coverage to 2026-06, DOGE/AVAX to 2026-07).
- Standing hypothesis: `28a88dd7-4181-4707-816c-898e547b1543` (ALGO, anchored continuation of `4e941275`).
- PIT status: full TPB_POOL path audited PIT_CLEAN (`9395948a`) — no ML sentinels, causal bias-bar +
  feature_store in live AND bulk paths, exits ratchet next-bar. New coins ride the identical engine path.
- Drag-coin inclusion rule PRE-REGISTERED (`46bfd099`): coin enters the book IFF (i) point PF > 1.0 at the
  frozen config on its full 2021→now window AND (ii) BEAR-regime bucket PnL > 0 AND (iii) surface not
  previously falsified. BTC + BNB already EXCLUDED by this rule; ETH excluded by prior falsification.

## Constraints reaffirmed

- Research-mode only (`enabled=false, simulated=true`); no live mutation, no promotion, no deploys, no git push.
- Interval 4h (valid); windows 2021-01-01 → yesterday UTC (matches core windows).
- Certification bar FIXED: n≥100, PF-CI-low>1.0, DSR≥0.90, ann90≥10%/yr, PIT-clean, WF ROBUST.
- ANTI-PADDING mandate: a coin failing the drag rule is EXCLUDED even if it would cross n=100.
- HONEST DSR: core DSR is 0.044; breadth may not lift it to 0.90 — report actual value, no threshold-shopping.
- Universe note: ADA/DOGE/AVAX are outside the standing 5-name research universe but are OPERATOR-PROVISIONED
  for this specific certification task (seeds + data verified today) — direct operator instruction governs.

## Experiments

### E1 — per-coin frozen-config transfer measurement (3 queues, 1 cell each)

- Strategy TPB @4h on ADAUSDT, DOGEUSDT, AVAXUSDT (separate queues, same hypothesis `28a88dd7`).
- Sweep grid: SINGLE cell at the byte-frozen config from `46bfd099`:
  adxEntryMin=20, adxEntryMax=60, biasAdxMin=18, biasAdxMax=60, minSignalScore=0.50, rvolMin=0.85,
  bodyRatioMin=0.30, maxEntryRiskPct=0.06, tp1R=3.0, runnerAtrPhase3=3.0 (engine defaults elsewhere,
  incl. pullbackTouchAtr=0.40, diSpreadMin=2.0). NO per-coin tuning — per-coin exit selection was
  pre-registered as mining (`deb7f222`) and stays forbidden. Declared: zero per-coin tune.
- `backtest_window.start_time = 2021-01-01T00:00:00` (end auto = yesterday UTC midnight).
- iter_budget: 1 per queue. Expected n per coin: 15–40 confirmed entries.
- Null-screen skip rationale: anchored continuation (PURSUE_LEAD) of a WARM lead with an already-validated
  mechanism on 2 coins — each measurement is ONE ~3-min backtest, cheaper than a null screen; the
  pre-registered drag rule is the inclusion filter.
- Drag-rule inputs read from the iteration's `analysis.regimes.by_trend_regime` (BEAR bucket) + point PF.

### E2 — pooled re-certification on the expanded book

- `POST /pooled-certification/analyze`, book strategy_code=TPB_POOL, sleeves = SOLUSDT-4h + XRPUSDT-4h core
  + drag-rule passers from E1, all sleeves strategy_code=TPB at the frozen config, window_start 2021-01-01.
- external_trials=90 (unchanged from the `46bfd099` declaration; server-side per-surface trial counting adds
  the new coins' iterations automatically — multiplicity only tightens).
- Success: n≥100 AND PF-CI-low>1.0 AND DSR≥0.90 AND ann90≥10 → graduation review → pooled walk-forward.
- Branches:
  - ≥2 coins pass + all pooled gates pass → graduation ladder (E3).
  - n≥100 but any V11 gate fails → honest INSUFFICIENT_EVIDENCE + paper; NO threshold-shopping; warm lead
    recorded if PF-CI-low still >1.0.
  - 0–1 coins pass → book stays sub-100 → honest falsification + paper (padding declined again).

### E3 — (conditional) graduation review + pooled walk-forward

- `POST /reviews/request` target_kind=graduation on the pooled iteration → `/reviews/auto-run-checklist`.
- If APPROVED → `POST /pooled-certification/walk-forward` (18 folds, 12/3/3 months). If ROBUST + ann≥10 →
  specialist checkpoint (step 9d: skeptic-prescreen, portfolio analytics, specialist-review requests) →
  exit SPECIALIST_REVIEW_PENDING.

## Execution order

1. E1 queues (ADA → DOGE → AVAX), drain, apply drag rule, journal checkpoint at each milestone.
2. E2 pooled analyze on core+passers, journal checkpoint.
3. E3 only if E2 legitimately clears every gate.
4. Paper + RUN_SUMMARY at terminal regardless of outcome.

## Decision criteria for next session

- If SPECIALIST_REVIEW_PENDING: resume protocol picks up the verdicts (step 1a branch 2).
- If falsified: TPB@4h breadth exhausted on every seeded coin; remaining lever = XRP pre-2021 window
  extension (~+13 trades, insufficient alone) — family honestly EXHAUSTED at that point.
