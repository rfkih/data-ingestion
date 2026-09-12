# Research Paper: XS_MOM — 12-coin universe × 1h

**Author:** quant-researcher
**Date:** 2026-06-18
**Strategy:** `XS_MOM` (cross_sectional_rank engine, V144/V145)
**Surface:** 12-coin crypto universe (anchor `BTCUSDT`) × `1h`
**Type:** ALGO
**Surface attempt:** v3 — ALGO (first RUNNABLE broad-universe test, after operator fixed the JVM OOM blocker; v2 was infra-blocked, never produced a verdict)
**Prior papers on this surface:** `RESEARCH_PAPER_XS_MOM_BTCUSDT_1H_v1_ALGO_2026-06-02.md` (5-name universe, all INSUFFICIENT); `RESEARCH_PAPER_XS_MOM_13COIN_1H_v2_ALGO_2026-06-18.md` (INFRA_HARD_FAIL, thesis untested)
**Filename:** `RESEARCH_PAPER_XS_MOM_13COIN_1H_v3_ALGO_2026-06-18.md`
**Terminal:** (session continued past this PIVOT — see RUN_SUMMARY for the session terminal)
**Goal status:** NOT HIT — breadth thesis FALSIFIED (PIVOT, final_verdict=DISCARD)
**Hypothesis:** `f449de21-c9d8-4d3b-a8d5-3f1821245f48`
**Queue(s):** `7b024083-b392-4f1d-b531-ea784ab89eb0`

---

## TL;DR

After the operator fixed the research-JVM OOM blocker (mem_limit 1.5GB→3GB, `-Xmx` 1400m→2560m) that killed the v2 attempt at 0%, the 12-coin cross-sectional momentum sweep RAN cleanly to completion — confirming the infra fix and finally putting the BREADTH thesis to a real test. The thesis is **falsified.** Across all four momentum cells, profit factor sits marginally above 1.0 (1.001–1.073) but **every PF 95% bootstrap CI lower bound straddles below 1.0** (best = 0.955); the reversion direction is actively losing (PF 0.91, CI-low 0.83 → NO_EDGE/DISCARD). Each cell traded ≈5,358 round-trip legs, so the V11 `n≥100` gate is decisively NOT the binding constraint — the cross-sectional long-short quartile legs simply net to ~zero after taker costs regardless of lookback (7d/14d), rebalance cadence (1d/2d), or direction. Post-hoc regime stratification confirms no rescue: `is_promising=false`, best regime BEAR_HIGH_VOL reaches only PF 1.02, and every other regime is sub-1.0. The operator-logged binding constraint from the 2026-06-03 and 2026-06-14 archetype-exhaustion rows — "breadth (more names)" — is now directly disproven for the cross-sectional PRICE-momentum/reversion family.

*(No SIGNIFICANT_EDGE table — no cell cleared the gate.)*

---

## 1. Background

The prior two research runs both terminated `ARCHETYPE_EXHAUSTION` (2026-06-03, 2026-06-14) with the binding constraint explicitly logged as **breadth** on the old 5/8-coin universe. The operator then backfilled a 13-coin universe with deep 1h history (BTC ETH SOL BNB XRP ADA DOGE AVAX FET LINK NEAR XLM ZEC) spanning the 2021 bull / 2022 bear regimes. The `CrossSectionalRankEngine` (V144/V145) already existed but had only ever run on 5 names, where a 0.25 quantile = ~1 name/leg (a single-name bet, not a dispersion portfolio). At 12–13 names the quartiles hold ~3 names each — the first genuine attack on the breadth constraint.

The v2 attempt (same session lineage) was blocked twice at the infra layer: a multi-coin submit `ReadTimeout` and a hard mid-run JVM `OutOfMemoryError` on the new coins. The operator root-caused the OOM to a 1.5GB heap cap pegged at 99.97% under the 12-coin load, raised it to 3GB / `-Xmx2560m`, recreated the container (now ~30% mem), and verified `jvm_ok=true`. This v3 paper documents the first run that actually completed.

---

## 2. Hypothesis

**Mechanism:** XS_MOM ranks the universe each rebalance by trailing relative-strength return over `lookbackBars`. It goes long the top `topQuantile` (0.25) and short the bottom `bottomQuantile` (0.25), rebalancing every `rebalanceBars`. The `direction` axis flips the sign (momentum = long winners/short losers; reversion = long losers/short winners). `minSymbols=8` requires at least 8 ranked names before a leg is taken.

**Pre-registration:** Hypothesis `f449de21-c9d8-4d3b-a8d5-3f1821245f48` registered 2026-06-17T17:39:13Z, before the earliest sweep iteration (2026-06-17T22:58:54Z) — gap ≈ 5h (the gap spans the v2 infra failure + operator fix). Falsification criterion: "PF 95% CI-lower > 1.0, n ≥ 100, ag90 ≥ 10% on the broad universe vs INSUFFICIENT on 5-name." All cells failed the PF-CI clause.

**Type:** ALGO. No ML involvement.

---

## 3. Methodology

### 3.1 Statistical Gates (V11 + V60)

| Gate | Threshold | Binding? |
|---|---|---|
| n_trades | ≥ 100 | NO — every cell ≈5,358 |
| PF 95% bootstrap CI lower | > 1.0 | **YES — the failing gate** |
| DSR (Bailey–LdP) | ≥ 0.90 | not reached (PF-CI failed first) |
| Statistical verdict | SIGNIFICANT_EDGE | NO |
| ann. geometric return at alloc-90 (ag90) | ≥ 10%/yr | not reached |

### 3.2 Sweep Design

- **Type:** GRID
- **Backtest window:** default floor `2024-01-01T00:00:00` → ~yesterday UTC (operator-directed smoke-test window; ~17 months)
- **Dimensions swept (≥3-axis rule satisfied):**
  - `direction`: momentum, reversion
  - `lookbackBars`: 168 (7d), 336 (14d)
  - `rebalanceBars`: 24 (1d), 48 (2d)
  - fixed: `topQuantile=0.25`, `bottomQuantile=0.25`, `minSymbols=8`
- **Total cells:** 8 planned, **5 executed** — `early_stop_on_no_edge=true` halted the grid after the first NO_EDGE/DISCARD cell (reversion/168/24).
- **Universe:** 12 coins — BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT, ADAUSDT, DOGEUSDT, AVAXUSDT, FETUSDT, LINKUSDT, NEARUSDT, XLMUSDT. ZEC dropped from the 13-coin hypothesis because the orchestrator `EnqueueRequest.universe` field is capped at `max_length=12` (Pydantic 422 above 12). ZEC was the lowest-liquidity/thinnest new coin (first-listed ALT_CAP_FADE INSUFFICIENT), so dropping it preserves the breadth attack.

### 3.3 Walk-Forward Protocol

Not run — no cell reached SIGNIFICANT_EDGE.

---

## 4. Parameter Space Explored

| Axis | Values Tested |
|---|---|
| `direction` | momentum, reversion |
| `lookbackBars` | 168, 336 |
| `rebalanceBars` | 24, 48 |
| `topQuantile` / `bottomQuantile` | 0.25 (fixed) |
| `minSymbols` | 8 (fixed) |

**Total iterations:** 5 (early-stopped from 8).

**Edge verdict distribution:**

| Verdict | Count |
|---|---|
| SIGNIFICANT_EDGE | 0 |
| INSUFFICIENT_EVIDENCE | 4 |
| NO_EDGE_DETECTED (DISCARD) | 1 |

---

## 5. Results

### 5.1 Edge summary

PF clustered tightly just above 1.0 for momentum and just below for reversion. The full cell ledger:

| direction | lookback | rebalance | PF (point) | PF 95% CI-low | n | verdict |
|---|---|---|---|---|---|---|
| momentum | 168 | 24 | 1.0006 | 0.921 | 5358 | INSUFFICIENT |
| momentum | 168 | 48 | 1.0255 | 0.918 | 5358 | INSUFFICIENT |
| momentum | 336 | 24 | 1.0285 | 0.947 | 5358 | INSUFFICIENT |
| momentum | 336 | 48 | 1.0731 | 0.955 | 5358 | INSUFFICIENT |
| reversion | 168 | 24 | 0.9079 | 0.829 | 5358 | NO_EDGE (DISCARD) |

The binding constraint is the **edge itself**, not statistical power: with ~5,358 trades the bootstrap CI is narrow, and it still straddles 1.0. Longer lookback (336/14d) is monotonically better than shorter (168/7d), and longer rebalance (48/2d) slightly beats 24/1d — both consistent with a faint, cost-eroded momentum tilt that is real in sign but too small to clear costs. Reversion is the wrong sign.

### 5.2 Best cell

| Param | Value |
|---|---|
| `direction` | momentum |
| `lookbackBars` | 336 |
| `rebalanceBars` | 48 |
| `topQuantile`/`bottomQuantile` | 0.25 |
| `minSymbols` | 8 |

| Metric | Value |
|---|---|
| iteration_id | (momentum/336/48 cell, 2026-06-17T23:01:00) |
| n_trades | 5358 |
| PF (point) | 1.0731 |
| PF 95% CI lower | 0.955 |
| PF 95% CI upper | (CI straddles 1.0) |
| Win rate | ~49% |
| Statistical verdict | INSUFFICIENT_EVIDENCE |

Smoke-test anchor cell (momentum/168/24, iteration `c66edafd-fe6b-4d48-920e-bf16873a43e8`): PF 1.0006, CI [0.921, 1.088], win-rate 49.2%, maxDD 41.8%.

---

## 8. Regime Breakdown (post-hoc, best cell)

Queue `7b024083` regime analysis (`market_data_sma200_atr` source, n_classified=5358):

| Regime | n | PF | mean_return_pct |
|---|---|---|---|
| BEAR_LOW_VOL | 880 | 0.956 | 0.0 |
| BULL_LOW_VOL | 978 | 0.751 | 0.0 |
| BEAR_HIGH_VOL | 1678 | **1.020** | 0.0 |
| BULL_HIGH_VOL | 1822 | 0.882 | 0.0 |

`is_promising=false`, `best_pf=1.0199`. The strongest regime (BEAR_HIGH_VOL) reaches only PF 1.02 — far below the 1.15 promising threshold that would justify a regime-gated retry. No regime rescues the signal, so the step-8.5 NOT_PROMISING branch fired (pivot, not regime-gated retry).

---

## 9. Infrastructure Notes

The v2 OOM blocker is **confirmed fixed.** The operator raised the research-JVM `mem_limit` 1.5GB→3GB and `-Xmx` 1400m→2560m; the 12-coin smoke-test iteration (`c66edafd`) and the full 5-cell drain all completed with no OOM and no submit `ReadTimeout`. `ORCH_JVM_REQUEST_TIMEOUT_S` was already 180s (the v2 "30s timeout" diagnosis was a red herring; the true cause was the in-JVM heap OOM killing the worker thread at 0%).

Two minor tooling observations (not blockers): (1) `scripts/orch.sh POST` requires `--body`, so the body-less `POST /regime-analysis/{queue_id}` must be called via raw curl; (2) the orchestrator's single-worker model serialized concurrent regime-analysis curls — an early client-side 120s timeout still committed the analysis server-side (read it back from the queue row's `regime_analysis` field rather than re-submitting).

---

## 10. Methodology Compliance Audit

| Rule | Compliant? | Notes |
|---|---|---|
| Research universe (hard rule #1) | YES | All 12 coins are backfilled, in-scope; no off-universe names |
| Intervals in {5m,15m,1h,4h,1d} (hard rule #2) | YES | 1h |
| Live trading untouched (hard rule #3) | YES | Research-mode backtest copies only |
| Research-mode only — no promotion (hard rule #4) | YES | No promote/deploy calls |
| 10%/yr economic bar enforced (hard rule #5) | YES | Not reached; not iterated past PIVOT |
| V11 + V60 gates honored (hard rule #6) | YES | PF-CI gate enforced as written; no loosening |
| ≥ 3 axes swept (hard rule #7) | YES | direction × lookbackBars × rebalanceBars |
| Pre-registration before testing (hard rule #10) | YES | Hypothesis 5h before first iter |
| Append-only durable evidence (hard rule #10) | YES | New STRATEGY_OUTCOME row; no edits/deletes |
| Reviewer verdict authoritative (hard rule #12) | YES | Plan APPROVED (hash 56cb3087) before queue |
| Research JVM only — no trading JVM calls (hard rule #13) | YES | All via orchestrator :8082 |

---

## 11. Conclusions

1. **The OOM infra blocker is fixed.** The 12-coin XS backtest now completes cleanly; the operator's 3GB heap bump resolved the v2 worker death.
2. **The breadth thesis is falsified for cross-sectional PRICE momentum.** With 12 names and ~5,358 trades of statistical power, every momentum cell's PF 95% CI-lower straddles below 1.0 (best 0.955) — the long-short legs net to ~zero after taker costs.
3. **Reversion is the wrong sign.** The reversion direction is actively losing (PF 0.91, CI-low 0.83).
4. **No regime rescues it.** Best regime bucket reaches only PF 1.02; `is_promising=false`.
5. **Implication for the research loop:** "breadth" was the operator-logged binding constraint from two prior exhaustion rows; this run disproves it as the constraint for the XS price-momentum family. The constraint is the absence of a tradeable cross-sectional price signal on this universe, not the number of names. The re-discovery gate now blocks re-running this axis-set. The next lever must be an ORTHOGONAL signal (not price momentum) or a single-name trend/MR mechanism on the freshly-backfilled coins, not more breadth on price.

---

## 12. Data Wishlist

| Priority | Item | Blocker type |
|---|---|---|
| 1 | Raise orchestrator `EnqueueRequest.universe` cap from 12 to 13+ if the full declared universe is ever needed (currently forces dropping 1 coin) | orchestrator code (minor; not gating — 12 is sufficient for breadth) |
| 2 | Orthogonal cross-sectional signal (funding-z, basis, or carry rank) as the XS input instead of trailing price return — price momentum is now falsified XS-wide | JVM engine + feature plumbing |

---

## 13. Appendix — Audit Trail

| Item | ID |
|---|---|
| Hypothesis | `f449de21-c9d8-4d3b-a8d5-3f1821245f48` |
| Queue | `7b024083-b392-4f1d-b531-ea784ab89eb0` |
| Smoke-test iteration | `c66edafd-fe6b-4d48-920e-bf16873a43e8` |
| Last (DISCARD) iteration | `ecd31854-57cc-451f-82a1-e47256b2e688` |
| Walk-forward run | none (no SIGNIFICANT_EDGE) |
| STRATEGY_OUTCOME journal | `befa6478-25e3-4d04-bac2-3d09f7a79e26` |
| Prior paper this continues | `RESEARCH_PAPER_XS_MOM_13COIN_1H_v2_ALGO_2026-06-18.md` (infra-blocked v2) |

---
*Paper generated by quant-researcher. DB registration: `POST /papers/7b024083.../generate`.*
