# Blackheart Platform — Deep Code Review

**Date:** 2026-06-03
**Scope:** All 6 services (~1,400 source files): trading-engine (Java), research-orchestrator / ingest / inference / train (Python), blackridge-frontend (TS/React).
**Method:** 18 parallel review units (correctness + redundancy + best-practice), then every *correctness* finding was adversarially re-verified against source by an independent agent.

## Headline numbers

| | count |
|---|---|
| Total findings | 176 |
| Critical | 4 (3 confirmed, 1 false-positive) |
| High | 29 |
| Medium | 65 |
| Low | 78 |
| Correctness findings verified **confirmed/likely** | 54 |
| Correctness findings caught as **false-positive** by the verifier | 22 |

The verifier earned its keep: it rejected 22 plausible-but-wrong correctness claims, including one that was originally rated **critical** (VBO "shadow-mode gate" — see *False positives* below). Treat everything in this report as verified-real unless noted.

> ⚠️ **Coverage gap:** the `frontend/lib-state` review unit under-delivered (returned a stub summary and a single finding). `src/lib`, `src/hooks`, `src/store`, `src/types` (~141 files) are effectively **un-reviewed** apart from one finding. Re-run that section before trusting it.

---

## Fix-first queue (the 3 confirmed criticals + load-bearing highs)

These are the ones I'd land before anything else — each is verified against source and each either breaks a live feature today or silently disables a money/safety gate.

1. **🔴 Approval gate never checks `minInitialCapitalUsd`** — `ApprovalGateService.java:42-67`. The per-symbol capital floor (a `nullable=false` column, V102-seeded at $1k) is *never compared* to `run.getInitialCapital()`. A backtest on $50 of notional passes the gate that authorizes real-capital deployment. The same field *is* used cosmetically in `isStale()`, proving it was meant to gate. **Add the `FailedCheck` + a regression test.**

2. **🔴 `rankings.py` reads analyzer metrics at the wrong JSONB path** — `repo/rankings.py:34-53`. `tick.py:715` writes `metrics_snapshot = {**run_metrics, "analysis": analysis}`, so `annualized_geometric_return_pct_at_alloc_90`, `dsr`, `psr`, `pf_point_estimate`, etc. live under `->'analysis'`. `rankings.py` reads them top-level and *filters* `WHERE ...->>'annualized...' IS NOT NULL`, so the rankings endpoint returns **zero rows**. Dig through `->'analysis'->>` and add a tick-shaped fixture test.

3. **🔴 `/compute/refresh` selects a non-existent column + dict_row `row[0]` bug** — `ingest/api/compute.py:61-76`. `_get_max_ts_for_feature` does `WHERE name = …` (the column is `feature_name`) **and** then `row[0]` on a `dict_row` (raises `KeyError(0)`). Two stacked bugs make every incremental refresh silently degrade to `status='partial'`, 0 rows. This is the exact `KeyError(0)` class your own `persistence.py` says it fixed. Fix both lines + add an integration test that runs against the real schema.

**Load-bearing highs (verified):**
- **Allocation-cap is a read-then-create race** — `LeaderboardService.java:453-471`. Two concurrent `deploy()` calls each read the same sum, both pass `existing+new ≤ 100%`, both insert → account over-allocated (e.g. 140% live). `@Transactional` under READ COMMITTED does not prevent it. Needs `SELECT … FOR UPDATE` on the account row or a DB constraint.
- **Paired-review gate is fail-open — an agent can self-approve** — `orchestrator/api/reviews.py:175-205`. `POST /reviews` writes `reviewer = <self-asserted X-Agent-Name>` with no `requester != reviewer` check; `/queue` accepts any passing verdict. The playbook advertises "researcher cannot self-approve" but nothing enforces it. Reject when `requested_by == agent`.
- **Login/register rate-limit keys on spoofable `X-Forwarded-For`** — `AuthRateLimitFilter.java:138-146`. Attacker sends a unique XFF per request → fresh token bucket each time → brute-force protection nullified. Only honor XFF from a trusted-proxy CIDR; combine with a per-username bucket.
- **`POST /metrics/reset` is unauthenticated** — `inference/auth.py:22`. A state-mutating POST sits in `_PUBLIC_PATHS`; anyone on the network can wipe SLO/latency evidence. Remove it from the public set.

---

## Cross-cutting themes

These patterns recur across services — fixing the pattern is higher-leverage than fixing each instance.

- **Fail-open gates with no observability.** ML-regime gate (`RiskGuardService.evaluateMlRegime:354`), correlation guard on zero-variance series, capacity guard on missing ADV, VCB/LSR null-regime gate, FCARRY null-EMA bypass, ML down-scale on null size. Most are *intentionally* fail-open, but several fire **silently** — an operator who "turns the gate on" can get no gate with only a WARN log. Add cooldowned metrics/alerts on every "enabled-but-unenforced" path.
- **JSONB key-path drift between writer and readers.** `metrics_snapshot` is written nested-under-`analysis` but read top-level in `rankings.py`, `iterations.py` (`trade_count` vs `total_trades`), and `agent_state.py`. One writer, three readers, all silently NULL. Centralize the snapshot schema and add fixture tests.
- **Write-then-cache idempotency.** `enqueue`/`reviews`/`specialist_reviews`/`tick` insert the row *before* `cache_response`. A crash in between double-inserts (no unique key on `(agent, key)`). Claim-key-first or add a DB unique constraint.
- **Copy-paste duplication of pure helpers.** `baseBuilder/resolveSize/resolveAtr/resolveRegimeScore` across 6 engines + 3 legacy strategies; PSR/erf/normal-CDF in 3 places; `_INTERVAL_SECONDS` in 3 inference modules; submit-payload builders in 3 orchestrator drivers; 5 near-identical triple-barrier label transformers; interval→minutes maps. The `decisionTime` bug below has to be fixed in 6 files *because* of this. Extract the pure ones.
- **`pickle.loads` before integrity check.** `inference/artifact_loader.py:60` and `train/artifacts.py:131` both unpickle, *then* compare `content_sha`. Arbitrary code runs before the check. Hash raw bytes first; the filename already IS the sha.
- **Client-side aggregation of paginated list data** (frontend). P&L page, Trades hero stats, strategy LiveTab all compute money-facing totals/win-rate/PF from one page or a 200-row window — directly against your CLAUDE.md "always server-side" rule. These show *wrong dollar figures as authoritative*.
- **`decisionTime = LocalDateTime.now()` inside the bar loop** (every engine). Records wall-clock of the replay, not `md.getEndTime()` → non-reproducible backtest timestamps. Stamp from the bar clock.

---

## Per-section findings

Severity-ordered. `[verified: …]` is the adversarial verifier's verdict on correctness items. Items with no tag are redundancy/best-practice (not separately verified).

### trading-engine/engine
*Generally clean; look-ahead correctly avoided. Issues cluster on VBO divergence and wall-clock timestamps.*

- **medium** `decisionTime` uses `LocalDateTime.now()` in the bar loop — non-deterministic in backtest. All engines. `DonchianBreakoutEngine.java:173,223,261,283,311,318`. *[verified: confirmed]*
- **medium** Live ML gate fails open on missing/stale point-in-time signal with no fail-closed option — `EngineContextHelpers.java:63-67`. *[verified: likely]*
- **medium** VBO hardcodes `strategyCode="VBO"`, ignoring `spec.getStrategyCode()` — mislabels fills/trade_history/leaderboard joins if driven under another code. `VolatilityBreakoutEngine.java:52-54,324-329`. *[verified: likely]*
- **low** Cross-sectional overlap clamp silently drops the median symbol / hides bad quantile config — `CrossSectionalRankEngine.java:84-90`.
- **low** MMR `readEma` returns null for any name ≠ ema20/50/200 → strategy silently inert — `MomentumMeanReversionEngine.java:316-324`.
- **low** `StrategySpec.paramBoolean` coerces unparseable strings (`"1"`, `"yes"`) to **false**, ignoring fallback → can silently disable `_ml_gate_enabled`. `StrategySpec.java:89-95`.
- **low** `EngineMetrics` "error-rate kill switch" trips on absolute count, not rate — `EngineMetrics.java:85-97`.
- **low (redundancy)** `baseBuilder/hold/veto/resolveSize` copy-pasted across 6 engines — `AtrMomentumEngine.java:289-320` + mirrors.
- **low** `EngineKillSwitchService` no-arg ctor leaves deps null → swallowed NPE no-ops a kill-switch trip — `:47-51`.

### trading-engine/backtest
*Fill-at-next-open is correct; impact model is the weak spot.*

- **high** Market-impact participation measured only against a single 5m bar's quote volume (capped at 1.0) — understates multi-bar/capacity execution cost, undermining the #14 capacity goal. `BacktestTradeExecutorService.java:212-217`. *[verified: confirmed]*
- **medium** Round-trip impact charged 2× at entry using only entry-side notional/liquidity; partial exits (TP1/TP2/runner) mis-allocated. `:206-217`. *[verified: likely]*
- **medium** Legacy flat-rate funding accrues continuously (fractional 8h) instead of at discrete settlements — `BacktestFundingCostService.java:63-72`. *[verified: confirmed]*
- **medium** Uncalibrated-symbol impact coeff is a hardcoded 0.001 guess applied to SOL/BNB/XRP capacity sweeps, no WARN — `BacktestService.java:48-60,225-234`. *[verified: likely]*
- **medium** Short MTM floors contribution at 0 → hides >100% adverse blow-ups, understates max drawdown — `BacktestStateService.java:87-89`. *[verified: likely]*
- **low** Data-coverage validator only counts rows, not the NULL-density it warns about (the "all entries fire every bar" trap) — `BacktestDataValidatorService.java:16-21,53-77`.
- **low** `computePerEvent` returns ZERO funding on missing history — indistinguishable from "genuinely zero" — `:90-91`.
- **low** FAILED-run save on Kafka-produce failure runs outside a tx boundary — `BacktestService.java:203-214`.
- **low (redundancy)** Duplicated interval→minutes & per-side P/L helpers — `BacktestTradeExecutorService.java:985-1024`.

### trading-engine/strategy
*Careful point-in-time discipline; fail-open regime gates are the theme.*

- **medium** VCB/LSR entry trend-regime gate is **fail-open on null regime** → takes long AND short irrespective of regime when `trend_regime` is null (a known failure mode here). `VcbStrategyService.java:174-178,318-322`. *[verified: confirmed]*
- **medium** VCB break-even moves stop to exact entry (no fee buffer), unlike LSR's `beFeeBufferR` → systematic small post-fee drag. `:456-459,544-546`. *[verified: likely]*
- **medium** TPR clone-failure fallback mutates the **shared singleton** Params (`p = base` then in-place setters) → cross-cell parameter bleed under parallel sweeps. `TrendPullbackStrategyService.java:80-95`. *[verified: likely]*
- **medium** TPR research params are a single JVM-global mutable `AtomicReference` — a params PUT/reset racing an in-flight sweep shifts the baseline mid-run (breaks `effective_params_snapshot` reproducibility). `ResearchParamService.java:46-70`. *[verified: likely]*
- **low** FCARRY `confidenceScore` is a verbatim copy of `signalScore` (computed twice) — `:168-169,226-227`.
- **low** `StrategyExecutorFactory.get(null)` throws NPE (vs clean IAE) when parametric enabled — `:71-78`.
- **low** FCARRY `requireTrendAlignment` silently bypassed when EMA50 null — `:141-145,201-205`.
- **low** LSR `inferSetupType` maps null/short roles to `SETUP_LONG_SWEEP` (latent foot-gun) — `:872-880`.
- **low** Active-preset cache unchecked `Map` cast → CCE deep in merge on hot path — `StrategyParamService.java:86-91`.
- **low (redundancy)** `resolveAtr/regimeScore/jumpRisk/riskMultiplier/isMarketVetoed` re-implemented in 3 legacy strategies — should delegate to `EngineContextHelpers`.

### trading-engine/risk-trade
*The gate stack is well-built; the serious issues are fee-blind PnL and a couple of unguarded write paths.*

- **high** Realized PnL is computed **gross of fees** but consumed as net by the 30-day DD kill-switch and vol-targeting → kill-switch trips later than intended. `TradeCloseService.java:605-619`. *[verified: likely — note: Kelly part overstated, DD/vol part real]*
- **high** Open idempotency key is **second-resolution** but documented millisecond → two distinct same-second opens dedup, silently dropping a legitimate entry (24h TTL). `OrderIdempotencyService.java:107-118`. *[verified: likely]*
- **medium** Drawdown returns hardcoded **100%** on any pure-loss window (peak ≤ 0) → force-trips kill-switch regardless of magnitude. `RiskGuardService.java:762-768`. *[verified: confirmed]*
- **medium** ML regime gate fails open (full size) when enabled-but-misconfigured (empty signal name), no metric/alert — `:354-363`. *[verified: likely]*
- **medium** Kelly returns `MIN_KELLY` (5%) floor for negative-expectancy runs instead of skipping → sizes into statistically-losing edges. `KellySizingService.java:228-232`. *[verified: likely]*
- **medium** Correlation guard only blocks high **positive** correlation, is strictly pairwise (3 just-under-threshold legs aggregate), and treats zero-variance series as r=0/allow. `CorrelationGuardService.java:162`. *[verified: likely]*
- **medium (redundancy)** `BookVolTargetingService` is **dead code** (no caller) and overlaps 3 live concentration controls — `:88-137`.
- **low** Shadow-log alert uses a never-reset Micrometer counter → alerts forever after 5 lifetime failures — `RiskGuardService.java:542-557`.
- **low** Capacity guard caps single-order only (stateless across same-minute orders), fully fails open on ADV gap — `CapacityGuardService.java:59-83`.
- **low** TWAP executor blocks the caller thread with `Thread.sleep` across the full duration — unsafe if wired live — `TwapExecutionService.java:97-111`.

### trading-engine/ml-gate
*Well-structured fail-open gate. (This unit returned only its summary + 1 high finding folded into the risk-trade gate analysis above — light coverage; consider a focused re-pass on `service/inference` + `mlsignal`.)*

### trading-engine/quant-math
*Math matches Bailey-LdP; the hole is the approval gate.*

- **🔴 critical** Approval gate never enforces `minInitialCapitalUsd` — fail-open money gate. `ApprovalGateService.java:42-67`. *[verified: confirmed]* — **see Fix-first #1.**
- **high** Allocation-cap is a read-then-create race → two deploys exceed 100%. `LeaderboardService.java:453-471`. *[verified: confirmed]* — **see Fix-first.**
- **medium (redundancy)** Three drifting copies of PSR/erf/normal-CDF — `LeaderboardRankingService.java:205-313` vs `SharpeStatistics`/`StandardNormal`.
- **medium** `avgTradeReturnPct` keeps summing after the geometric ruin latch trips → headline metrics describe two different trade universes. `GeometricReturnCalculator.java:70-86`. *[verified: confirmed]*
- **medium** `decayMultiplier` forced `decayActive=true` for the stored shadow factor — bakes un-calibrated haircut into the displayed live factor. `LeaderboardLiveMetricsService.java:108`. *[verified: likely]*
- **low** Monte Carlo persists null `randomSeed` while results depend on generated `effectiveSeed`; nanoTime is a weak seed — `MonteCarloService.java:58-60`.
- **low** `calcVersion` string-munged `-p0`→`-p1` breaks on next version bump — `LeaderboardSnapshotService.java:198-200`.
- **low** `StandardNormal.inverseCdf` is bare Acklam (no Halley) — tail error exceeds the doc's 1e-7 exactly where DSR's SR\* uses it — `:22-77`.
- **low** USDT reserve floor uses `findFirst()` with no uniqueness guarantee on target rows — `AssetAllocationService.java:269-281`.
- **low** Robustness treats missing fold data as neutral 1.0 → unvalidated rows out-rank weakly-validated ones — `LeaderboardRankingService.java:141-150`.

### trading-engine/api
*Ownership/authz are consistently delegated; issues are at the edges.*

- **high** Login/register rate limiter keys on attacker-controlled `X-Forwarded-For`. `AuthRateLimitFilter.java:138-146`. *[verified: confirmed]* — **see Fix-first.**
- **medium** Blanket `IllegalStateException → 400` masks server faults (e.g. "Authenticated user not found", "SHA-256 unavailable") as client errors. `GlobalExceptionHandler.java:72-76`. *[verified: likely]*
- **medium** 60s `UserDetails`/authorities cache lets a revoked admin keep `ROLE_ADMIN` for up to a minute on money-moving endpoints. `JwtAuthenticationFilter.java:79-90`. *[verified: likely]*
- **medium (redundancy)** Dead `MarketOrderRequest` DTO exposes `apiKey/apiSecret` with no READ_ONLY/ToString.Exclude (credential-injection footgun if ever wired) — `:14-21`.
- **medium** Limit/TWAP probe accepts unvalidated bodies and can fire real mainnet orders (no `@Valid`, no testnet guard) — `LimitOrderProbeController.java:100-167`.
- **low** Internal-orch portfolio read is cross-tenant by a single shared secret, no audit log — `OrchestratorInternalController.java:66-84`.
- **low** `extractRootCause` echoes up to 200 chars of internal message to the client (info disclosure) — `GlobalExceptionHandler.java:49-64`.
- **low** Pending-approval `valueOf(status)` couples request parsing to enum — `PendingApprovalController.java:71-78`.

### trading-engine/persistence
*Solid: parameterized native queries, immutable composite keys, JSONB via JdbcTypeCode.*

- **medium (redundancy)** `JsonMapConverter` is dead code and contradicts the no-AttributeConverter-for-JSONB rule (swallows errors → empty map) — `:22-55`.
- **medium** Credential converter fails open to **plaintext** for non-`enc-v1`-prefixed values → masks unencrypted secrets — `EncryptedStringConverter.java:94-96`.
- **medium** Case-sensitive native email lookup + inconsistent normalization across flows → duplicate-account / login-hole vector; `LIMIT 1` hides dupes. `UserRepository.java:16-22`. *[verified: confirmed]*
- **low** `deleteExpired` `@Modifying` lacks `@Transactional` (throws on direct call) — `IdempotencyRecordRepository.java:47-49`.
- **low (redundancy)** `findActivePreset`/`findActivePresets` identical SQL, Optional vs List — drift risk — `AccountStrategyRepository.java:166-206`.
- **low** `sumNotionalInRange` has no numeric-scale contract → ADV denominator may be mis-scaled — `TradeHistoryRepository.java:70-82`.
- **low (redundancy)** Open-status set hardcoded across ~8 native queries gating live entry/account-delete — `TradesRepository.java:92-316`.
- **low** `findLatest` trusts caller to pass a single-row Pageable — `SignalHistoryRepository.java:63-73`.
- **low** `findLatestBySymbol` returns nullable entity, not Optional (NPE seam on new-symbol data plane) — `MarketDataRepository.java:142-153`.

### trading-engine/data-live
*Mature, defensive (PK-race handling, poison-pill defense, watchdog reconnect).*

- **high** ML regime down-scale silently skipped when the size field is null → order executes at **full fallback size** precisely when the model says trade smaller. `LiveTradingDecisionExecutorService.java:151-167`. *[verified: confirmed]*
- **low** Invalid (price/qty ≤ 0) trade events dropped before idempotent persistence, WARN-only, no gap detection on `trade_history` — `TradeBatchWriter.java:192-198`.
- **low** Active-account map rebuilt from a full table scan on every closed bar; symbol filter applied in Java after a cross-symbol fetch (cross-fire hazard) — `BinanceWebSocketClient.java:461-486`.
- **low** `BarEventPublisher` serializes OHLCV via `.doubleValue()` → precision loss before the event leaves the JVM — `:52-56`.
- **low (redundancy)** `RedisSubscriber` only logs — pub/sub pair is dead plumbing paying a serialization cost — `:19-27`.
- **low (redundancy)** Reconnect/watchdog lifecycle duplicated across the two WS clients **and already drifted** (30s vs 60s stale, different reconnect paths) — `BinanceTradeStreamClient.java:159-300`.
- **low** Funding backfill `truncated` result omits the resume cursor → caller can't resume precisely — `FundingRateBackfillService.java:72-90`.
- **low** Dynamic NULL-count SQL interpolates reflected column names unquoted (reserved-word/mixed-case fragility) — `MarketDataIntegrityService.java:206-219`.
- **low** Orchestrator re-queries DB after each strategy to detect a new trade — assumes synchronous persist; potential double-entry if async — `LiveOrchestratorCoordinatorService.java:108-122`.

### orchestrator/api
*Consistent envelopes, idempotency helpers, constant-time token compare. The review gate is the weak point.*

- **high** Paired-review gate is fail-open — an agent can self-approve its own plan/graduation. `reviews.py:175-205`. *[verified: confirmed]* — **see Fix-first.**
- **medium** Queue cancel silently ignored for a RUNNING row a tick completes (`_decide_next_state` not fenced on `started_at`) → the documented "cancel doesn't stop /tick" trap; `{cancelled:true}` is misleading. `queue.py:472-496`. *[verified: confirmed]*
- **medium** Cache-after-write idempotency double-inserts on a crash between DB write and cache put (no unique key on `(agent,key)`). `queue.py:422-468`. *[verified: confirmed]*
- **low** `/ml/readyz` leaks the lightgbm probe subprocess on timeout (no `proc.kill()`) — public path — `health.py:80-90`.
- **low** Idempotency key not bound to request body → same key + different payload returns stale response, drops new work — `idempotency.py:138-170`.
- **low** `/reviews` and `/specialist-review/complete` don't validate that a matching open request exists before recording a verdict — `reviews.py:175-205`, `specialist_reviews.py:208-287`.

### orchestrator/services
*Methodology-aware (DSR bootstrap, signed-corr gate, ML-sentinel splitting). Walk-forward stability is the risk.*

- **high** Walk-forward can return **ROBUST off a single completed fold** (`pstdev`→0, no min-fold gate; `n` is total-trades-across-folds, not fold count). This is the gate that flips toward real capital. `walk_forward.py:113-128`. *[verified: confirmed]*
- **medium** Capacity base scale is `valid[0]`, not the smallest tested scale → edge-decay measured against an already-impacted baseline if the smallest tier failed. `capacity.py:85-109`. *[verified: likely]*
- **medium** SIGNIFICANT_EDGE + budget-exhausted persisted as `final_verdict='INSUFFICIENT_EVIDENCE'` → corrupts audit trail / re-discovery gate. `tick.py:939-956`. *[verified: likely]*
- **medium** Tick-time portfolio gate correlates the candidate against a baseline set that still includes its **own** strategy_code (self-correlation demotes a legit edge). `portfolio.py:384-455`. *[verified: confirmed]*
- **low** `calmar` truthiness guard treats a legit 0 return as missing; undocumented drawdown sign convention — `analyze.py:583-585`.
- **low** `ml_gate_shadow_analysis` greedy nearest-trade matching is order-dependent → can mis-attribute counterfactual PnL feeding the shadow-mode flip decision — `analyze.py:731-779`.
- **low** Long-poll drivers (walk_forward/capacity/cpcv/cross_window/null_screen) ignore `settings.poll_timeout_s`, hardcoded 3600s → the false-FAIL trap reintroduced for multi-run drivers — `tick.py:215-236`.
- **low** `_paired_bootstrap_ci` can produce a degenerate CI for tiny `n_reps` (no floor) → binding ML-graduation verdict off near-zero resampling — `paired_delta.py:330-355`.
- **low** Reviewer `cost_realism`/tick logging still reference the **retired** +20bps gate; can contribute a false warning-fail — `review.py:322-326`.
- **low (redundancy)** Per-fold/per-scale submit-payload builders ~90% duplicated across tick/walk_forward/capacity, already diverging on `marketImpactEnabled` — `walk_forward.py:131-179`.

### orchestrator/repo-clients
*Careful DB layer (keyset pagination, advisory-lock numbering, SKIP-LOCKED claim). The JSONB key drift is the killer.*

- **🔴 critical** `rankings.py` reads analyzer metrics at `metrics_snapshot` top level; they live under `->'analysis'` → primary filter key always NULL → rankings returns nothing. `rankings.py:34-53`. *[verified: confirmed]* — **see Fix-first #2.**
- **high** `iterations.leaderboard`/list helpers read `metrics_snapshot->>'trade_count'` but the column is `total_trades` → always NULL; sort-by-trade_count is no-op. Same bug in `agent_state._last_iterations`. `iterations.py:29,197`. *[verified: confirmed]*
- **high** `JvmClient` dev_bypass mints a JWT for an arbitrary first user when `ORCH_JVM_DEV_LOGIN_EMAIL` is unset → research writes can land on the wrong (admin live) account. `jvm.py:82-93`.
- **medium** Persistent 401 mapped to synthetic `TransportError` → exhausted auth surfaces as opaque transport error, burns 3 round-trips — `jvm.py:194-201`.
- **medium** Queue claim orders by `(priority, created_time)` but `list_queue` orders by `created_time` only — the "what's next" view disagrees with what `/tick` claims, contradicting the module's own docstring. `queue.py:59-65`. *[verified: likely]*
- **medium** `hourly_feature_refresh` sleeps **before** its first run → a freshly redeployed orchestrator leaves features unrefreshed for a full hour (flips inference to catchup_scan / MlSignalStale). `feature_refresh.py:36-53`. *[verified: likely]*
- **low** `ErrorReporter.report` spawns an unbounded daemon thread per error → thread/socket leak under a burst of unique fingerprints — `error_reporter.py:108-111`.
- **low** `count_sessions` uses `COUNT(DISTINCT session_id)` (drops NULLs) while `list_sessions` groups+returns them → off-by-N pagination — `activity.py:94-131`.
- **low** Hot JSONB discriminator reads use `->>'…' =` (can't use the GIN index) → seq-scan latency cliff on the resume/digest path — `reviews.py:215-229`.
- **low** `fetch_trades ORDER BY entry_time ASC` only → tie/NULL ordering makes sequential-PnL/drawdown analysis non-deterministic — `trades.py:20-36`.
- **low** `TradingJvmClient` reuses the inbound `ORCH_AUTH_TOKEN` as the outbound secret across two trust edges — `trading_jvm.py:164-168`.

### ingest
*Well-engineered shared PIT-guard + naive-UTC + ON-CONFLICT contract. The incremental refresh path is broken.*

- **🔴 critical** `/compute/refresh` selects non-existent column `name` (should be `feature_name`) → every incremental refresh degrades to partial/0-rows. `api/compute.py:61-69`. *[verified: confirmed]* — **see Fix-first #3.**
- **high** `dict_row` `row[0]` `KeyError(0)` in the same function — second stacked bug on the incremental path. `compute.py:71-76`. *[verified: confirmed]*
- **high** Kafka bar-event consumer uses `auto_offset_reset='latest'` + implicit auto-commit → bars dropped on restart/downtime and offsets committed for failed handlers (silent feature lag). `bar_event_consumer.py:256-277`. *[verified: confirmed]*
- **medium** `write_macro_raw_rows` mutates caller dicts in place via `setdefault` → breaks source statelessness; deribit relies on this hidden mutation — `shared/db.py:104-107`.
- **medium** Compute engine `_validate_pit` is a **no-op** despite the docstring claiming a third PIT layer that "checks the transformer's claim" — called with `None` for the data it would need. `features/compute.py:265-289`. *[verified: likely]*
- **medium** Source error paths open a second DB connection for `update_source_health` after the first failed → can replace/mask the real DB error and double connection pressure — `sources/deribit.py:193-206` (+ fred/coinmetrics/binance_macro/coingecko/alternative_me).
- **low** Lifespan binds `get_settings()` at import via `partial` → lifespan tasks freeze import-time settings while handlers see fresh ones — `workers/server.py:246-251`.
- **low** stdlib logging called with structlog-style event keys + reserved `extra` fields → latent `LogRecord` KeyError / silently-lost fields — `webhooks.py:34-43`.
- **low** `_resolve_window` end+days branch reconstructs start via wall-clock arithmetic (works by sub-second luck) — `workers/compute_features.py:107-110`.
- **low** coinmetrics date-only API params vs datetime client-side filter → boundary-day inclusion/exclusion depends on operator's time component — `sources/coinmetrics.py:195-197`.

### inference
*Clear fail-closed-on-missing-features semantics. Several real security/perf gaps.*

- **high** `POST /metrics/reset` is unauthenticated (in `_PUBLIC_PATHS`) → anyone can wipe SLO tracking. `auth.py:22`. *[verified: confirmed]* — **see Fix-first.**
- **high** No artifact/booster cache despite docstrings claiming one → every prediction re-reads + unpickles the `.pkl`; batch-predict re-reads per signal per webhook. `artifact_loader.py:49-69`.
- **high** Streaming worker keys on `mr.interval` but batch-predict uses `serving_interval` → worker infers/backfills at the **wrong interval**. `streaming.py:100-114`. *[verified: likely]*
- **medium** Auth token compared with `!=` (non-constant-time) — `auth.py:44`.
- **medium** `pickle.loads` before the sha integrity check → arbitrary code runs before tampering is detected. `artifact_loader.py:60-62`.
- **medium (redundancy)** batch-predict and `/inference/run` disagree on refused statuses / retired-signal checks and duplicate artifact resolution — extract one "servable model" helper. `batch.py:127`.
- **medium** batch-predict reads features per-signal outside any snapshot, writes in a late transaction → read/write skew drops signals on a partial-bar race. `batch.py:119-226`. *[verified: likely]*
- **low (redundancy)** batch-predict unpacks `confidence` then hardcodes `confidence=None` on write (latent divergence from `/inference/run`) — `batch.py:179-221`.
- **low (redundancy)** `_INTERVAL_SECONDS` duplicated across 3 modules — `streaming.py:52`.
- **low** Latency tracker never populated by any write path → `/metrics/latency` reports empty; SLO surface is decorative — `metrics.py:39-44`.

### train
*Unusually careful PIT discipline (label-aware embargo, automated leakage detection). A few real holes.*

- **high** 80/20 holdout split has **no embargo** → forward labels leak train→val; `holdout_80_20` metrics flow to the gauntlet. `train.py:83-99,987-1008`. *[verified: likely — leak is real; verifier flagged the "passes gate" consequence as weaker than stated]*
- **high** Hardcoded 8-day market-data buffer truncates the 90-day `pctrank` trailing window (and any >8d backward feature) → label percentile computed over a different, shorter sample across the window. `derived_features.py:793-812,163-198`. *[verified: confirmed]*
- **medium** Directional gauntlet gate-4 **binds** multiclass at 0.15 despite docs/aggregation logic written for it to SKIP → a multiclass model can now FAIL (Tier A) where the contract said CONDITIONAL_PASS. `gauntlet_directional.py:117-119,284-355`. *[verified: confirmed]*
- **medium** Orchestrator auth token defaults to `dev-sentinel-not-for-prod`, shipped silently; registration failure swallowed to a warning — `settings.py:37-41`, `cli.py:341-357`.
- **medium** `read_artifact` unpickles before sha check (same class as inference) — `artifacts.py:131-143`.
- **medium** Label-leakage screen (|Pearson|/MI ≥ 0.95) can be evaded by a one-bar-shifted label on autocorrelated series, yet gate-2 treats PASS as "labels PIT-safe" — `integrity.py:411-552`. *[verified: likely]*
- **medium (redundancy)** Five+ near-identical triple-barrier label transformers (~40 lines each) — one missed edit → wrong label. `derived_features.py:221-585`.
- **low** `train_serve_filter_active` reported True for single-element `training_intervals` where no filtering occurs — misleading audit metadata — `walk_forward.py:427`.
- **low** Registration failure swallowed; run still reports `status='ok'` / exit 0 — `cli.py:341-357`.
- **low** `conditional_invariance` evaluates gate-4 over only bins with test support; `n_pairs_evaluated` never thresholded → a fold that can't be assessed can pass transferability — `conditional_invariance.py:222-273`.
- **low** `run_integrity_or_raise` hardcodes the 1000-row floor with no per-spec override — `train.py:728-740`.

### frontend/components
*Display layer is well-guarded (NaN/null em-dash, dialogs on risky mutations). No money-correctness bug; chart edge cases + client-side list ops.*

- **medium (best-practice)** `RecentActivityFeed` sorts+slices trades client-side (fetches 12, re-sorts) → can drop a genuinely recent exit — `RecentActivityFeed.tsx:71`.
- **medium** `PaperTradePanel` slices to 100 client-side and assumes `rows[0]` is newest — `:108,191`.
- **medium** `BacktestTradeTable` does all sort/filter client-side over the full set (perf cliff, anti-pattern) — `:188-217`.
- **medium** `ParamField`/`SliderWithNumber` let typed values exceed min/max (only steppers clamp) → out-of-range financial params reach the payload. `ParamField.tsx:306-312`. *[verified: likely]*
- **low** `EquityCurve` Y-axis mis-formats negative equity (`$-1500`); `MonteCarloChart` does it right — `:104-105`.
- **low** `DrawdownChart`/`EquityCurve` hardcode raw hex instead of theme tokens — `:71-107`.
- **low** Monthly-returns first-cell baseline can overstate a mid-month start — `BacktestMonthlyReturns.tsx:227-243`.
- **low** Max-Drawdown `valueColor` falsy check renders `−—%` for null field — `BacktestMetricsGrid.tsx:263`.
- **low** Duplicate single-letter month labels (3×"J") — clarity on a financial heatmap — `BacktestMonthlyReturns.tsx:76`.
- **low** `PnlCell` flash effect can leak a stale flash direction on rapid oscillation — `:32-45`.
- **low** `PaperTradePanel` fmtNum uses magnitude-based decimals, not per-symbol Binance precision — `:299-306`.
- **low** `CommandPalette` Enter resolves `filtered[activeIndex]` while highlight uses `flatItems` → highlighted row ≠ opened row on reorder — `:88-90,112`.

### frontend/app-routes
*Correct server/client boundaries, no env-var leakage. The cluster of client-side aggregation bugs presents wrong money numbers as authoritative.*

- **high** P&L page **Symbol filter is a literal no-op** — `filterBySymbol` returns full `data` in both branches; every dollar figure stays account-wide while the UI looks filtered. `pnl/page.tsx:491-496`. *[verified: confirmed]*
- **high** Trades journal hero stats (Cumulative P&L / Win Rate / Profit Factor) computed from **one page only**, labeled as totals. `trades/page.tsx:337,627-707`. *[verified: confirmed]*
- **high** Strategy `LiveTab` realized P&L/win-rate computed over a client-truncated 200-trade window not scoped to the account_strategy row → incomplete totals shown as authoritative. `strategies/[accountStrategyId]/page.tsx:1129-1146`. *[verified: confirmed]*
- **medium** Auth middleware gates on cookie **presence** only (fail-open to any non-empty value) — by design (real auth is httpOnly JWT) but document it — `middleware.ts:37-40`.
- **medium** Route/global error boundaries render raw `error.message` to users in prod (against the CLAUDE.md Do-Not) — `error.tsx:42-44`.
- **low** Inconsistent stablecoin sets between allocation donut (6) and risk Cash-buffer (3) → cards disagree about the same wallet — `portfolio/page.tsx:47,424`.
- **low** verify-email effect can fire the one-shot token request twice (StrictMode/re-render) → consumes the token — `verify-email/page.tsx:22-51`.

### frontend/lib-state ⚠️ under-reviewed
*This unit returned only a stub. Re-run before trusting it.*

- **high** `researchClient` is a literal alias of `apiClient` (both built from `env.apiUrl`); `env.researchUrl` is dead → all research/backtest/montecarlo/historical calls hit the trading JVM. Works only because prod is a single JVM; a split deploy misroutes. `lib/api/client.ts:36-38`. *[verified: confirmed]*

---

## False positives the verifier caught (don't act on these)

Surfacing these so you know what was *rejected* — and why the 22 false-positives don't appear above:

- **VBO "ML shadow-mode gate ignores shadow, blocks trades that should be logged"** — originally rated **critical**. Verifier refuted: the sibling spec-driven engines (`EngineContextHelpers.checkMLGate`, used by MMR/CDC) have *no* shadow-mode parameter either and block on deny identically, so VBO is **consistent** with them, not divergent. `_ml_shadow_mode` is a harmless dead spec field, not a parity-breaking contract violation. (Still worth deleting the dead field, but it's not a money bug.)
- **VBO ATR fallback of 1.0 → "garbage stops, enormous position"** — refuted: VBO anchors its stop to the breakout candle's low/high, not entry, so `riskPerUnit` stays at candle-range scale; a 1.0 ATR makes the stop marginally *tighter*, not near-entry. No sizing blow-up.

(20 more lower-severity correctness claims were similarly rejected as guarded-elsewhere / misread / intended-behavior.)

---

## Suggested order of attack

1. **Today:** the 3 confirmed criticals (each is a small, surgical fix with a clear test) + the 4 load-bearing highs in Fix-first.
2. **This week:** the fail-open-without-observability cluster (add metrics/alerts), the JSONB key-drift readers, write-then-cache idempotency, the frontend client-aggregation trio.
3. **Backlog / hygiene:** the redundancy extractions (engine helpers, PSR math, payload builders, triple-barrier core), pickle-before-verify hardening, and the low-severity polish.
4. **Re-run:** a focused review pass on `frontend/lib-state` (under-covered) and `trading-engine/service/inference`+`mlsignal` (light coverage).
