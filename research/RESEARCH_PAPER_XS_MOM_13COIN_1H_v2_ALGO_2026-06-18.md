# Research Paper: XS_MOM — 13-coin universe × 1h

**Author:** quant-researcher
**Date:** 2026-06-18
**Strategy:** `XS_MOM` (cross_sectional_rank engine, V144/V145)
**Surface:** 13-coin crypto universe (anchor `BTCUSDT`) × `1h`
**Type:** ALGO
**Surface attempt:** v2 — ALGO (first broad-universe test; v1 was the 5-name universe)
**Prior papers on this surface:** `RESEARCH_PAPER_XS_MOM_BTCUSDT_1H_v1_ALGO_2026-06-02.md` (5-name universe, all INSUFFICIENT)
**Filename:** `RESEARCH_PAPER_XS_MOM_13COIN_1H_v2_ALGO_2026-06-18.md`
**Terminal:** INFRA_HARD_FAIL
**Goal status:** NOT HIT — surface UNRUNNABLE (no iteration completed; thesis untested, NOT falsified)
**Hypothesis:** `f449de21-c9d8-4d3b-a8d5-3f1821245f48`
**Queue(s):** `0b719edc` (no-universe bug), `191bd807` (12-coin FAILED), `c2b61204` (8-coin ReadTimeout), `7488ed61` (8-coin short-window ReadTimeout)

---

## TL;DR

The operator's highest-prior lead this run was a genuine attack on the BREADTH constraint that ended the prior two research runs: run cross-sectional momentum (XS_MOM) on the newly-expanded 13-coin universe (BTC ETH SOL BNB XRP ADA DOGE AVAX FET LINK NEAR XLM ZEC), where top/bottom quartiles become real ~3-name dispersion portfolios instead of the single-name bets the dead 5-name universe produced. The hypothesis was pre-registered, the plan was reviewer-APPROVED, and four backtest attempts were driven across three universe sizes and two windows. **No cell ever produced a verdict.** Two independent infra walls were isolated: (1) the XS submit `POST /api/v1/backtest` blocks longer than the orchestrator's `ORCH_JVM_REQUEST_TIMEOUT_S=30s` for ANY multi-coin universe (confirmed window-independent — the same ReadTimeout fired on both a 2024→now and a 2025→now 8-coin run), and (2) the new coins (FET/LINK/NEAR/XLM) additionally cause a hard mid-run JVM backtest FAILURE. The breadth thesis is **untested-because-unrunnable, not falsified** — the engine works (the 5-name v1 completed 304–368 trades/quarter); it is the larger universe's heavier submit preflight plus new-coin data that break it. Both blockers require operator action.

*(No metrics table — no cell reached a completed iteration.)*

---

## 1. Background

Prior runs terminated ARCHETYPE_EXHAUSTION twice (2026-06-03, 2026-06-14) with the binding constraint explicitly logged as **BREADTH** on the old 5/8-coin universe. The operator then expanded the backtest universe to 13 coins with deep 1h/4h/1d history spanning the 2018 bear / 2021 bull / 2022 bear regimes. The cross-sectional rank engine (V144/V145) exists and had run before, but only on the 5-name universe (paper v1, hypothesis 79e37d06, ~20 iterations, ALL INSUFFICIENT_EVIDENCE) — where a 0.25 quantile selects ~1 name per leg, i.e. a single-name long/short bet whose idiosyncratic noise swamps any relative-strength signal. The 13-coin universe was the first structural attack on exactly the breadth wall, and (per tick.py:770) the universe rides in the queue request with NO JVM change required. This was selected as the lead per the operator's framing and the highest-prior of the available surfaces (all others being graveyard or exhausted-majors).

---

## 2. Hypothesis

**Mechanism:** XS_MOM longs the top quantile and shorts the bottom quantile of the universe ranked by `lookbackBars`-bar simple return (`kbar_return`), rebalancing every `rebalanceBars`. At 13 names, top/bottom quartiles hold ~3 names each, so the legs average out idiosyncratic noise and isolate the cross-sectional relative-strength factor.

**Pre-registration:** Hypothesis `f449de21-c9d8-4d3b-a8d5-3f1821245f48` registered 2026-06-17T17:39:13Z, before any sweep iteration. Falsification criterion: if a focused 8-cell grid across {direction momentum|reversion, lookbackBars, rebalanceBars} shows P95(PF)<1.2 / all cells INSUFFICIENT, the breadth lever is exhausted for price-momentum XS. **This criterion was never reachable — no cell completed.**

**Type:** ALGO. Why not a re-skin of any graveyard family: continuous price-momentum/reversion cross-section across the whole universe, not (a) ALT_CAP_FADE per-coin capitulation event-fade, not (b) positioning/top-trader-LSR fade (no positioning data, OOS-dead 2026-06-16), not (c) XS-IV/VoV/basis/funding dispersion (those rank by a derived feature; this ranks by raw kbar_return). Plan reviewer APPROVED the distinction (mechanism marker found, no prior outcome on the axis combo in 14 days).

---

## 3. Methodology

### 3.2 Sweep Design
- **Type:** GRID. Planned 8 cells: direction {momentum, reversion} × lookbackBars {168, 336} × rebalanceBars {24, 48}; fixed topQuantile=bottomQuantile=0.25, minSymbols=8.
- **Backtest window:** default 2024-01-01 → yesterday (attempts 1–3); 2025-01-01 → yesterday (attempt 4, to shorten per-cell runtime).
- **Total cells executed: 0 completed.** Every cell failed at submit or backtest before producing a verdict.

### 3.6 Execution Log (what actually happened — the substance of this paper)

| # | Queue | Universe | Window | Outcome |
|---|---|---|---|---|
| 1 | 0b719edc | 13 nested in sweep_config | 2024→ | Ran with **empty universe** — JVM run 241295b8 FAILED. Root cause: `universe` is a TOP-LEVEL QueueRequest field (queue.py:312 reads `body.universe`); nesting it in `sweep_config.universe` silently drops it. |
| 2 | 191bd807 | 12 (top-level, dropped ZEC for the max_length=12 cap) | 2024→ | JVM run 656570a6 returned terminal **status=FAILED ~4 min in** — a hard, fast failure introduced by the new coins. |
| 3 | c2b61204 | 8 proven (BTC ETH SOL BNB XRP ADA DOGE AVAX) | 2024→ | httpx **ReadTimeout** at 23 and 25 min — no hard failure, run still computing. |
| 4 | 7488ed61 | 8 proven | 2025→ (shorter) | httpx **ReadTimeout AGAIN** — proving the timeout is window-INDEPENDENT. |

### 3.7 Root-Cause Isolation

**Blocker A — XS submit exceeds the 30s request timeout (primary, window-independent).** The orchestrator's JVM client (`clients/jvm.py:54`) applies `jvm_request_timeout_s` (env `ORCH_JVM_REQUEST_TIMEOUT_S=30`, Pydantic max 300) to the `submit_backtest` POST `/api/v1/backtest`. For a multi-coin XS universe the submit handler does heavy synchronous preflight that exceeds 30s, so the POST raises `ReadTimeout` before returning a `backtestRunId`. `submit_backtest` deliberately does NOT retry ReadTimeout (jvm.py:158-161, to avoid double-dispatching an hour-long backtest), so the tick crashes `tick_uncaught_exception / ReadTimeout`. Confirmed window-independent: attempts 3 and 4 differ only in window length and both ReadTimeout, so the wall is the submit, not the run duration.

**Blocker B — new coins cause a hard mid-run JVM FAILURE.** Attempt 2's 12-coin run got a run_id (so its submit was accepted) but the JVM returned `status=FAILED` ~4 min into the run. `loadUniverse`/`loadFeatures` (CrossSectionalBacktestCoordinatorService) skip missing symbols gracefully, so a simple data absence would not fail the run — this is a mid-run exception on a new-coin bar (probable market_data 1h integrity gap: NULL/zero close, duplicate timestamp, or a feature_store mismatch on a newly-backfilled coin). The exact cause needs the JVM `backtest_run.error_message` column or :8081 logs, both outside researcher reach (no prod DB password locally; only the :8082 orchestrator is tunneled).

---

## 4. Results

No statistical results — no iteration completed. The single durable finding is the **two-blocker infra diagnosis** above, plus a useful API-contract correction: the XS universe must be passed as a **top-level** `universe` field on the queue request (max 12 entries), not nested inside `sweep_config`.

---

## 5. Verdict & Disposition

**Terminal: INFRA_HARD_FAIL.** Four attempts (3 universe sizes × 2 windows) did not recover. The fix is operator-owned, not researcher-retryable. The breadth thesis remains **OPEN** — untested because unrunnable, explicitly NOT falsified. The prior 5-name v1 completed runs, so the engine and the kbar_return signal path work; the wall is the broad-universe execution path's scalability plus new-coin data integrity.

## 6. Next Levers (operator-owned, ranked)

1. **Raise `ORCH_JVM_REQUEST_TIMEOUT_S`** (>30, max 300) for the XS submit path, OR make the XS submit truly async (return the run_id immediately, run the backtest in the Kafka consumer). Without this, NO multi-coin XS cell can be submitted. This is the single highest-leverage unblock.
2. **Inspect `backtest_run` 656570a6** on the VPS: `SELECT error_message, status FROM backtest_run WHERE backtest_run_id='656570a6-5d2a-4295-99e4-e6a076c8fd17'` to pin which new coin breaks the run; then verify market_data 1h integrity (no NULL/zero close, no dup ts) for FET/LINK/NEAR/XLM/ZEC.
3. **Seed non-ALT_CAP_FADE `account_strategy` rows** for FET/LINK/NEAR/XLM/ZEC so single-name DCB/MMR can also exploit the new multi-regime history (an orthogonal breadth play that bypasses the XS submit cost entirely).

**Resume:** with (1)+(2) fixed, re-queue XS_MOM 12-coin via the already-APPROVED plan (hypothesis `f449de21`, plan hash `56cb3087`, 6-axis) — universe TOP-LEVEL, not nested. No re-review needed (the plan approval is reusable on the same axis-set hash).

---

## 7. Reproducibility

- Hypothesis: journal `f449de21-c9d8-4d3b-a8d5-3f1821245f48`
- Blocker STRATEGY_OUTCOME: journal `b46be92d-21de-4492-9d72-e0011362d9aa`
- Terminal RUN_SUMMARY: journal `fcfa95fc-0e12-41cd-b198-babb70ad72b7`
- Approved plan target_id hash: `56cb3087a3de1ff8912d1d6436906d27eefc4ae6d9371cbdce4cdfadba698901`
- Failed JVM runs: `656570a6-5d2a-4295-99e4-e6a076c8fd17`, `241295b8-7ee0-4735-a743-8f9f93ab1ce1`
