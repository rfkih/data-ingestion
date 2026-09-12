# Research Paper: TPB_POOL — SOLUSDT+XRPUSDT pooled book × 4h

**Author:** quant-researcher
**Date:** 2026-07-13
**Strategy:** `TPB_POOL` (book) / `TPB` (sleeves, archetype `trend_pullback`)
**Surface:** `SOLUSDT+XRPUSDT` (pooled) × `4h`
**Type:** ALGO
**Surface attempt:** v1 — ALGO (first pooled-book certification attempt for the TPB family; operator-provisioned unlock after terminal ef7238ba)
**Prior papers on this surface:** none (pooled surface is new; per-coin context in `RESEARCH_PAPER_TPB_SOLUSDT_4H_v1_ALGO_2026-07-13.md`)
**Filename:** `RESEARCH_PAPER_TPB_POOLEDBOOK_4H_v1_ALGO_2026-07-13.md`
**Terminal:** ARCHETYPE_EXHAUSTION
**Goal status:** NOT HIT
**Hypothesis:** `4e941275-cd35-40a2-94fa-4b3b1542313c`
**Queue(s):** none (pooled analyze is queue-less by design — iteration `42e5d72c-67bd-4e6f-9bad-8ba085d31f08` on the book code)

---

## TL;DR

The TPB_POOL book — the two-sided trend-pullback edge pooled across its two genuine-edge surfaces (SOLUSDT-4h, XRPUSDT-4h) at one frozen config — was measured through the DCB_POOL-style orchestrator-side pooled-certification pathway after a full point-in-time cleanliness audit returned PIT_CLEAN. The pooled book confirms a real edge at the book level: PF 2.056 with a bootstrap 95% CI lower bound of 1.049 (> 1.0), bear-carried exactly as hypothesized (41 of 52 trades and 68% of PnL in BEAR regime). It is nonetheless NOT certifiable: n=52 is half the V11 floor, DSR is 0.044 at an honest 209-trial tax, and the equal-slice book annualizes at 9.29%/yr — below the 10% bar. The only route to n≥100 was including BTCUSDT (PF 0.87 at the frozen config) and BNBUSDT (bear-bucket −159.7 PnL) — both fail the pre-registered drag-coin inclusion rule, and padding was declined per the operator's anti-gaming mandate. Verdict: real-but-sub-100; certification honestly refused; family shelved pending operator-gated breadth.

*(No cell reached SIGNIFICANT_EDGE — gate table shown in §5.2.)*

---

## 1. Background

The 2026-07-12/13 TPB run (terminal `ef7238ba`, ARCHETYPE_EXHAUSTION) closed with two-sidedness CONFIRMED — the mirrored short path of the trend-pullback archetype fires and profits in bear regimes, the exact axis where ATR_MOM was structurally bull-only — but all 32 sweep iterations were INSUFFICIENT_EVIDENCE because 4h pullback frequency caps n at ≤ 38 per surface. The per-coin transfer map: SOL-4h core (18 cells PF 1.15–2.40, plateau), XRP-4h confirms at the same exit corner, BTC-4h partial (best at a different exit corner), ETH-4h falsified cross-window (2018 bear reverses the 2021 plateau), BNB-4h dead (bear-negative 4/4), TPB@1h falsified by null-screen. The single remaining V11 path was a fixed-config pooled book via the orchestrator-side pooled certification (built and operator-approved 2026-07-10 for DCB_POOL) — operator-gated, and provisioned as this session's directive. The DCB_POOL precedent carries a hard lesson: its cert was VOIDED by a look-ahead ML gate, so this session was mandated to prove PIT-cleanliness before any compute.

## 2. Hypothesis

**Mechanism:** TPB (`TrendPullbackEngine`, archetype `trend_pullback`) enters on a pullback to EMA20 inside a confirmed trend. Bias gate (4h): EMA50 vs EMA200 stack plus close vs EMA200, mirrored long/short, with a bias-ADX band. Entry gates: ADX band (adxEntryMin/Max), DI spread, RSI band, pullback-touch tolerance in ATR units, candle quality (body/range ratio, close-location value band, relative volume ≥ rvolMin), composite signal score ≥ minSignalScore, risk bracket ≤ maxEntryRiskPct. Exit: TP1 leg at tp1R with break-even shift at 1R, runner leg phase-trails by ATR (phase-3 trail = runnerAtrPhase3 after 3.5R) — the "let winners run" corner that doubled SOL economics.

**Pre-registration:** Hypothesis `4e941275` (ALGO) registered 2026-07-12T19:39, before every TPB sweep iteration. This session added two further pre-registrations BEFORE the pooled compute: the PIT audit verdict (journal `9395948a`) and the drag-coin inclusion rule + book composition + expected outcome (journal `46bfd099`, written 2026-07-13 before the analyze call). Falsification criterion for the cert: n < 100 on the rule-compliant book → report real-but-sub-100 and do not certify.

**Type:** ALGO. No ML model, no `_ml_*` sentinels anywhere in the book — the DCB_POOL void channel (future-vintage ML gate) is structurally absent.

## 3. Methodology

### 3.1 Statistical Gates (V11 + V60)

| Gate | Threshold | Binding? |
|---|---|---|
| n_trades | ≥ 100 | YES — the binding failure |
| PF 95% bootstrap CI lower | > 1.0 | YES |
| DSR (Bailey–LdP, n_trials from hypothesis_audit + external) | ≥ 0.90 | YES |
| Statistical verdict | SIGNIFICANT_EDGE | YES |
| ann. geometric return at alloc-90 (mission bar) | ≥ 10%/yr | YES |

### 3.2 Certification design (not a sweep)

- **Type:** frozen-config confirmatory measurement — ONE config, zero cells searched this session.
- **Frozen config** (byte-exact from reference iterations `f697e708`/`6c87f5fd`): adxEntryMin 20, adxEntryMax 60, biasAdxMin 18, biasAdxMax 60, minSignalScore 0.50, rvolMin 0.85, bodyRatioMin 0.30, maxEntryRiskPct 0.06, tp1R 3.0, runnerAtrPhase3 3.0; all else engine defaults (pullbackTouchAtr 0.40, diSpreadMin 2.0). One config across all sleeves — per-coin exit selection was pre-registered as mining in `deb7f222` and stays forbidden.
- **Windows:** both sleeves 2021-01-01 → 2026-07-12 (identical to the supporting sweep evidence; spans 2021 bull, 2022 bear, 2023 chop, 2024–26).
- **Drag-coin inclusion rule (pre-registered, journal `46bfd099`):** a coin enters the book iff at the frozen config on its full transfer window (i) point PF > 1.0, AND (ii) BEAR-bucket PnL > 0 (the two-sided hypothesis is the thing being certified), AND (iii) the surface was not previously falsified. Application to the pre-existing transfer evidence: BTC fails (i)+(ii) (PF 0.87, BEAR −56.7); BNB fails (ii) (BEAR −159.7, bear win-rate 15%); ETH excluded by prior cross-window falsification; SOL and XRP pass. **Book = SOL+XRP only.**
- **Multiplicity:** server-side per-surface trials (SOL-4h: 88, XRP-4h: 30) + declared external_trials=90 (ETH-4h round-1/2 cells, BTC/BNB transfer cells, 6 null-screens × 8 draws, pool-variant selection, margin) + 1 = **n_trials 209**.

### 3.3 Walk-Forward Protocol

Not run — pre-declared: no graduation review and no walk-forward on a book that fails the n-gate. (The pooled WF design was audited anyway: per-fold fresh single-symbol runs of the frozen config on disjoint test windows; nothing is fitted per fold, so PIT-cleanliness reduces to the feature/bias legs verified in §9.)

## 4. Parameter Space Explored

No new parameter search this session. The frozen config inherits from the prior run's pre-registered ladder (32 sweep iterations + 6 null-screens, all journaled). This session added exactly ONE trial (the pooled analyze itself), declared in the 209-trial DSR tax.

**Edge verdict distribution (this session):**

| Verdict | Count |
|---|---|
| SIGNIFICANT_EDGE | 0 |
| INSUFFICIENT_EVIDENCE | 1 (the pooled book iteration) |
| NO_EDGE_DETECTED (DISCARD) | 0 |

## 5. Results

### 5.1 Edge summary

Replication was exact: the pooled pathway re-ran both sleeves through the standard verified coordinator and reproduced the reference sweep cells byte-level (SOL n=22 PF 2.3966 vs reference 22/2.397; XRP n=30 PF 1.7414 vs reference 30/1.741). The pooled trade series clears the PF-CI gate at book level — lower bound 1.049 — which no single TPB surface achieved alone; pooling genuinely tightened the CI (SOL alone: CI-low 0.86; XRP alone: 0.62). The binding constraint is power, and only power: 4h trend-pullbacks fire ~5/yr/coin, and only two coins carry the two-sided edge. DSR at n=52 with a 209-trial tax is 0.044 — the sample cannot overcome the honest mining tax. The equal-slice book annualizes at 9.29%/yr (SOL sleeve alone 11.24%/yr; the slice model pays XRP's lower per-year PnL density — an honest, conservative book model that claims no cross-sleeve cash reuse).

### 5.2 Best (only) cell — the pooled book

| Param | Value |
|---|---|
| Sleeves | TPB @ SOLUSDT-4h, TPB @ XRPUSDT-4h |
| Config | frozen (§3.2), identical across sleeves |
| Windows | 2021-01-01 → 2026-07-12 |

| Metric | Value | Gate | Pass? |
|---|---|---|---|
| iteration_id | `42e5d72c-67bd-4e6f-9bad-8ba085d31f08` | — | — |
| n_trades | 52 | ≥ 100 | **FAIL** |
| PF (point) | 2.056 | — | — |
| PF 95% CI lower | 1.049 | > 1.0 | PASS |
| PF 95% CI upper | 3.924 | — | — |
| DSR | 0.044 (n_trials=209) | ≥ 0.90 | **FAIL** |
| PSR | 0.350 | — | — |
| ag90 (%/yr, equal-slice book) | 9.29 | ≥ 10 | **FAIL** (marginal) |
| Sharpe (annualized) | 0.844 | — | — |
| Sortino (annualized) | 2.255 | — | — |
| Calmar | 0.587 | — | — |
| Max drawdown (book) | 17.4% | — | — |
| Statistical verdict | INSUFFICIENT_EVIDENCE | SIGNIFICANT_EDGE | **FAIL** |

Regime breakdown (pooled): BEAR 41 trades, +966.3 PnL, WR 0.439; BULL 11 trades, +461.3 PnL, WR 0.364. The edge is bear-carried, consistent with the two-sided hypothesis and opposite to ATR_MOM's structural bull-only defect. Quarterly: 13 of 19 active quarters positive; worst run 2022Q2–Q3 (−309.8 across 8 trades) recovered by 2022Q4 (+284.6).

Contention diagnostics: max 2 concurrent positions; ≥2-concurrent 11.0% of open time; same-symbol overlap 0% (different symbols by construction).

## 9. Infrastructure Notes — PIT-cleanliness audit (the mandate)

The DCB_POOL cert was voided by a look-ahead ML gate; this cert was gated on a source-level PIT audit (journal `9395948a`, verdict **PIT_CLEAN**):

1. **Bias-bar resolution cannot reach a future bar.** `BacktestCoordinatorService.resolveLatestCompletedBiasCandle` filters `candle.endTime <= monitorCandle.endTime` and takes the max — future bias bars are excluded by predicate. The bias FeatureStore lookup is an exact-key `get(resolvedBiasMarket.getStartTime())`: although the preloaded map spans the whole run window, the key is always the identity of an already-completed bar, so a future feature row is unreachable. For 4h sleeves, bias interval == strategy interval, so the bias bar is the just-closed decision bar (decision + fill at bar close = live-parity semantics).
2. **Entry features are causal.** The current bar's FeatureStore is an exact-key `get(strategyCandle.getStartTime())`, and the strategy candle only resolves when a strategy-interval bar closes at the monitor bar's endTime; `previousFeatureStore` is strictly `isBefore`. The engine reads only FeatureStore + MarketData fields of these bars — no `feature_values`, no `signal_history`, no macro tables.
3. **feature_store precompute is causal in both write paths.** Live path: `findLast300BySymbolAndIntervalAndTime` (`start_time <= :startTime LIMIT 300`) with indicators evaluated at the series end index. Bulk path: `buildFeatureRowFromPrecomputed(idx, data.subList(0, idx+1))` — TA4j indicators evaluated at idx (backward-recursive), window helpers fed data through idx only, candle-quality features from bar idx itself.
4. **No model/signal vintage risk.** TPB has no ML gate and the sleeves declare no `_ml_*` sentinels — the exact DCB_POOL void channel is structurally absent.
5. **Exit path.** Stop/TP listener evaluates the current bar; the trailing stop ratchets AFTER the bar survives, taking effect the NEXT bar. The 2026-06-06 intrabar exit-optimism fixes are in place; this is the same verified engine used by all 32 TPB sweep iterations.
6. **Pooled WF design** (not executed): per-fold fresh runs of a frozen config on disjoint windows — nothing fitted per fold; PIT-cleanliness reduces to legs 1–3.

## 10. Methodology Compliance Audit

| Rule | Compliant? | Notes |
|---|---|---|
| Research universe BTC/ETH/SOL/BNB/XRP (hard rule #1) | YES | SOL + XRP sleeves; BTC/BNB evaluated and excluded |
| Intervals in {5m, 15m, 1h, 4h, 1d} (hard rule #2) | YES | 4h only |
| Research never mutates live trading (hard rule #3) | YES | backtest copies only; sleeves resolve research-account rows |
| Research-mode only — no live promotion (hard rule #4) | YES | no promotion call; book stays research-only |
| 10%/yr economic bar enforced (hard rule #5) | YES | 9.29%/yr noted as FAIL, not waved through |
| V11 + V60 gates honored (hard rule #6) | YES | certification REFUSED on n/DSR despite PF-CI pass |
| ≥ 3 dimensions traversed (hard rule #7) | YES | inherited: entry, exit, interval, window, regime, pooling |
| Pre-registration before testing (hard rule #10) | YES | hypothesis 4e941275; PIT audit 9395948a and drag rule 46bfd099 journaled BEFORE compute |
| Append-only durable evidence (hard rule #10) | YES | journal/iteration rows only added |
| Reviewer verdict authoritative (hard rule #12) | YES | no graduation review requested (pre-declared: nothing to review at n=52) |
| Research JVM only — no trading JVM calls (hard rule #13) | YES | all compute via orchestrator :8082 |

## 11. Conclusions

1. **The pooled two-sided trend-pullback edge is real:** PF 2.056 with 95% CI lower 1.049 on 52 pooled trades, bear-carried (41/52 trades, 68% of PnL in BEAR) — the first TPB result whose PF CI clears 1.0.
2. **It is not certifiable on the current universe:** n=52 is half the V11 floor, DSR 0.044 at the honest 209-trial tax, and the equal-slice book yields 9.29%/yr — three gates fail, and no runnable axis raises n without violating a pre-registered constraint.
3. **The padding route was correctly closed by pre-registration:** BTC (PF 0.87 at the frozen config) and BNB (bear-bucket −159.7) fail the drag-coin rule; including them would have crossed n≥100 only by injecting edge-less trades — a padded pass is worse than an honest fail.
4. **The pooled pathway itself is PIT-clean for ALGO books** (six-leg source audit), so this negative is a power conclusion, not a methodology artifact — and the pathway remains reusable for any future book.
5. **Implication for the research loop:** TPB is shelved real-but-thin; the WARM lead (inherited cross-run) prices the unlock at roughly +50 genuine-edge trades — i.e. 2–3 additional coins carrying the two-sided edge at 4h, an operator-gated breadth decision, not a research-runnable axis.

## 12. Data Wishlist

| Priority | Item | Blocker type |
|---|---|---|
| 1 | TPB@4h seeds + market_data/feature_store backfill for ADA/DOGE/AVAX (ADA/DOGE have 1h market_data only; 4h feature_store and account_strategy seeds missing) — each genuine-edge coin adds ~20–30 trades toward n≥100 | backfill + seed rows (operator) |
| 2 | XRPUSDT 4h history depth check: if market_data/feature_store predate 2021, a pre-registrable window extension (2018 bear included) adds ~13 trades — insufficient alone, useful combined with #1 | backfill verification (operator) |
| 3 | LIQ_FADE per-symbol microstructure gate re-check (~Aug 2026, accrual-gated) — the standing non-TPB lead | data accrual (time-gated) |

## 13. Appendix — Audit Trail

| Item | ID |
|---|---|
| Hypothesis | `4e941275-cd35-40a2-94fa-4b3b1542313c` |
| PIT audit verdict journal | `9395948a-673d-406f-b5ae-ee8c23eb6931` (PIT_CLEAN) |
| Pre-registration journal (drag rule + book) | `46bfd099-6f21-4712-b658-a7a71d895a72` |
| Pooled iteration (book) | `42e5d72c-67bd-4e6f-9bad-8ba085d31f08` |
| Sleeve runs | SOL `004e7fc7-b0f8-4295-9f1b-749f00137bb8`, XRP `f8e182e5-4a75-4a3b-b587-c33d4a5cae42` |
| Reference sweep iterations (frozen config) | SOL `f697e708`, XRP `6c87f5fd`, BTC `dba6fe59` (excluded), BNB `e41e865a` (excluded) |
| Walk-forward run | not run (pre-declared: n-gate fail) |
| Specialist verdicts | not requested (no graduation candidate) |
| STRATEGY_OUTCOME journal | `ba6811c1-9f8d-41b3-b155-909293b72e1f` |
| RUN_SUMMARY journal | see ARCHETYPE_EXHAUSTION_2026-07-13 (this session's terminal row) |
| Prior paper(s) this continues | `RESEARCH_PAPER_TPB_SOLUSDT_4H_v1_ALGO_2026-07-13.md` |

---
*Paper generated by quant-researcher. DB registration: not applicable (queue-less pooled iteration; prior run's 8 DB papers cover the underlying sweeps).*
