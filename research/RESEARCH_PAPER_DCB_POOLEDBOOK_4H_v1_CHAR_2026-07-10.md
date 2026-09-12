# Research Paper: DCB — POOLED BOOK (SOLUSDT-4h + ETHUSDT-4h + ETHUSDT-1h) × 4h/1h

**Author:** quant-researcher
**Date:** 2026-07-10
**Strategy:** `DCB`
**Surface:** `SOLUSDT` × `4h` + `ETHUSDT` × `4h` (regime-gated) + `ETHUSDT` × `1h` (regime-gated) — pooled-book characterization
**Type:** CHAR
**Surface attempt:** v1 — CHAR (offline pooled-series certification feasibility study after the pooled-engine block)
**Prior papers on this surface:** `RESEARCH_PAPER_DCB_SOLUSDT_4H_v1_ALGO_2026-07-09.md` (SOL sleeve), `RESEARCH_PAPER_DCB_ETHUSDT_1H_v12_ALGO_2026-07-09.md` (ETH-1h surface history)
**Filename:** `RESEARCH_PAPER_DCB_POOLEDBOOK_4H_v1_CHAR_2026-07-10.md`
**Terminal:** WALL_CLOCK_CAP (RESEARCH_RUN_COMPLETE — run closed after the directive lead reached its operator-decision point)
**Goal status:** NOT HIT (certifiable-on-paper book identified; certification pipeline is operator-gated)
**Hypothesis:** pursuit of warm lead `DCB_POOLED_BOOK` (anchored continuation; no new sweep queued — see §9 for why)
**Queue(s):** none this session (analysis over completed runs `da857a20`, `8f7df1db`, `ec9359d7`, `36742d6a`, `a786df78`, `c28455be`)

---

## TL;DR

The DCB-4h/1h breakout sleeves measured across this run (SOL-4h ungated, ETH-4h and ETH-1h regime_eth_v2-gated) are individually blocked by exactly one V11 gate — DSR — everywhere. This paper tests the standing thesis that pooling them into one trade series clears DSR, using an offline merge of the completed runs' trade series scored with an exact replica of the production analyzer (replication validated bit-for-bit on the SOL-4h cell: PF 1.7589, DSR 0.5904@15 trials). Result: the **three-sleeve gated book is robustly certifiable on paper** — n=772, PF 1.633 (95% CI [1.365, 1.946]), per-trade-annualized Sharpe 2.21, **DSR 0.963 at the most punitive 222-trial mining tax**, 6/6 profitable years — while the engine-feasible ungated pool FAILS (DSR 0.826 best case) and the gated 2-sleeve 4h pool is knife-edge (0.909 only if pooled-surface trials ≤ 30). The binding constraint has moved from statistics to ENGINEERING: `PooledIndependentBacktestCoordinatorService` cannot host stop-based archetypes (no intra-bar listener), blocks shorts, forces one interval, and has no ML-gate wiring — so certification requires an operator build decision (§12).

| Metric (POOL-3G, offline estimate) | Value | Gate |
|---|---|---|
| n_trades | 772 | ≥ 100 ✓ |
| PF 95% CI lower | 1.365 | > 1.0 ✓ |
| DSR @ n_trials=222 (worst case) | 0.963 | ≥ 0.90 ✓ |
| Sharpe (annualized, per-trade) | 2.21 | — |
| Fold profile | 6/6 years profitable, worst-year PF 1.126 | ROBUST-shaped |
| Walk-forward | NOT RUN — engine-blocked | pending build |

*(These are offline pooled estimates, not a certified iteration — see §5.3 caveats. No V11 verdict is claimed.)*

---

## 1. Background

Run context (started 2026-07-10, ~5.6h consumed by two prior sessions that died on plan rate limits): the prior run (RESEARCH_RUN_COMPLETE_2026-07-09) confirmed the DCB-4h breakout edge on SOL (24/24 profitable cells) with DSR the sole blocker; this run mapped the standardized box across the majors — ETH-4h thin-real ungated (8/8 profitable, ciL 0.88–0.98), BNB-4h DEAD, XRP-4h DEAD, BTC-4h screen-killed both directions — and found that the `regime_eth_v2` ML gate lifts ETH-4h to PF 1.86–1.94 (ciL up to 1.27) and ETH-1h to PF 1.29–1.46 (ciL up to 1.17). The prior session filed a DATA_WISHLIST for a pooled DCB account_strategy seed; the operator executed it (strategy_definition `DCB_POOL`, account_strategy on research account …002) and directed this session at the pooled certification run.

Code-reading the pooled coordinator (as the operator instructed) found the run as designed is impossible on the current engine — journal `eaeb1220` (§9). This paper is the substitute the plan itself specified (E3b, RESEARCH_PLAN_2026-07-10): offline pooled-series evidence to quantify whether the engine build is worth making at all.

## 2. Hypothesis

**Mechanism:** DCB (Donchian breakout) enters on channel breakouts (both sides on the honest single-symbol path), manages via ATR stop (`stopAtrMult`), fixed TP (`tpR`), break-even shift, and a `maxBarsHeld` timed exit. The gated ETH sleeves additionally require `regime_eth_v2` (LightGBM regime classifier served from `signal_history`, coverage 2022-01→now) to pass at entry. The pooled-book thesis: the sleeves' per-trade edges are real but individually under-powered against the Bailey–LdP deflation; one merged trade series raises n (149/151/472 → 772) and diversification raises Sharpe (sleeve monthly-PnL correlations 0.180 / 0.120 / −0.271), so DSR clears.

**Pre-registration:** the pooled thesis was pre-registered as warm lead `DCB_POOLED_BOOK` in the run marker and in the prior session's DATA_WISHLIST journal (2026-07-10 05:42) before any pooled analysis ran. Falsification criterion: pooled series fails DSR 0.90 at honest trial counts → pooling is not the certification path.

**Type:** CHAR (characterization over completed runs; no new backtests).

## 3. Methodology

### 3.1 Statistical Gates (V11 + V60)

Standard gates (n ≥ 100, PF 95% CI lower > 1.0, DSR ≥ 0.90 with cumulative trial scaling, ag90 ≥ 10%/yr, WF ROBUST). No gate was moved. This paper produces ESTIMATES against those gates, not verdicts.

### 3.2 Analysis Design

- **Inputs:** per-trade `realized_pnl_amount` series of six COMPLETED single-symbol runs (honest path: intra-bar SL/TP via listener, shorts allowed, ML gates enforced).
- **Scoring:** exact replica of `services/analyze.py` conventions — sample-std Sharpe, population skew/excess-kurtosis, bootstrap PF CI (B=2000, seed 42, sentinel-PF resamples dropped), DSR = Φ((SR−SR\*)·√((n−1)/denom)) with SR\* = Φ⁻¹(1−0.05/n_trials)/√n and denom = 1 − skew·SR + ((kurt+2)/4)·SR².
- **Replication validation:** SOL-4h cell (tpR 2.0 / stopAtrMult 3.25 / maxBarsHeld 72, iteration `98692470`) reproduces the recorded PF 1.7589 exactly and DSR 0.5904 at the recorded n_trials=15 exactly.
- **Trial-count sensitivity:** DSR reported at n_trials ∈ {8, 16, 30, 100, 187, 222} spanning "pool = fresh surface, box-only mining" (8–16) through "inherit the full ETH-1h surface history" (222).

### 3.3 Pool Definitions

| Pool | Sleeves (cell) | Engine requirement |
|---|---|---|
| POOL-U | SOL-4h (2.0/3.25/72) + ETH-4h ungated (2.0/3.25/72) | minimal fix (listener + shorts) |
| POOL-2G | SOL-4h + ETH-4h gated (2.0/3.25/72, run `8f7df1db`) | + per-symbol ML-gate wiring |
| POOL-3G | POOL-2G + ETH-1h gated (2.0/3.0/168, run `ec9359d7`) | + cross-interval pooling |

## 4. Parameter Space Explored

No new cells were executed. The underlying sweeps this analysis pools were pre-registered grids: the 8-cell standardized 4h box (tpR {2.0,3.0} × stopAtrMult {2.75,3.25} × maxBarsHeld {48,72}, BREAKOUT, no trail, 2021→now) run ungated on SOL/ETH/BNB/XRP and gated on ETH; and the 8-cell 1h box (tpR {2.0,5.0} × stopAtrMult {3.0,5.0} × maxBarsHeld {96,168}, 2022→now) run ungated (2026-07-03) and gated (2026-07-10) on ETH.

## 5. Results

### 5.1 Pooled series vs gates

| Pool | n | PF | PF 95% CI | SR_ann | DSR@8 | DSR@16 | DSR@30 | DSR@100 | DSR@187 | DSR@222 | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| POOL-U | 352 | 1.546 | [1.210, 1.965] | 1.45 | 0.826 | 0.755 | 0.685 | — | 0.483@172 | — | **FAILS all counts** |
| POOL-2G | 300 | 1.790 | [1.382, 2.326] | 1.80 | 0.963 | 0.939 | 0.909 | 0.834 | 0.785 | 0.771 | knife-edge (≤30 trials only) |
| POOL-3G | 772 | 1.633 | [1.365, 1.946] | 2.21 | 0.998 | 0.996 | 0.992 | 0.978 | 0.967 | **0.963** | **clears at every count** |

Sleeve monthly-PnL correlations: SOL~gETH-4h **0.180**, gETH-4h~gETH-1h **0.120**, SOL~gETH-1h **−0.271**. The 1h sleeve is the diversification engine as well as the n engine.

Fold stability (POOL-3G, per calendar year): 2021 PF 1.73 (n=31), 2022 1.87 (n=119), 2023 1.90 (n=172), 2024 1.13 (n=182), 2025 1.76 (n=177), 2026 1.82 (n=91) — 6/6 profitable, bear-2022 included.

### 5.2 Gate attribution (is regime_eth_v2 load-bearing?)

Matched-cell gate-on vs gate-off comparisons from the DB (same params, same windows):

| Surface | Cell | Ungated | Gated | Gate effect |
|---|---|---|---|---|
| ETH-4h | 2.0/3.25/72 | PF 1.361, n=203, ciL 0.980 | PF 1.832, n=151, ciL 1.273 | additive (binds, +0.47 PF) |
| ETH-1h | 2.0/3.0/168 | PF 1.016, n=711, ciL 0.850 | PF 1.424, n=472, ciL 1.167 | **load-bearing** (dead → real) |
| ETH-1h | 2.0/3.0/96 | PF 1.019, n=739, ciL 0.859 | PF 1.405, n=488, ciL 1.146 | **load-bearing** |

The n reductions (711→472 etc.) prove the gate binds (signal_history coverage 2022-01→now; 2021 was fail-open on the 4h sweeps and is reported as-is). All 8 matched 1h cells and all 8 matched 4h cells show positive gate deltas — a strong paired-delta contrast to the Stage-H `regime_btc_v3` value-destruction result. **Consequence: there is no ungated shortcut to the book; ML-gate wiring is a hard requirement of any certifiable pool.**

### 5.3 Caveats (honest limits of the offline estimate)

1. **Merged independent runs ≠ shared-cash book.** Per-trade Sharpe/PF/DSR are sizing-scale-invariant, so equal-slice sizing is first-order exact, but shared-cash contention and same-symbol overlap between the two ETH sleeves (monthly corr 0.12) are not modeled.
2. **Post-hoc cell selection** across the 8-cell box is covered by the trial-count sensitivity; POOL-3G clears even at the maximal 222-trial interpretation, so the conclusion is selection-robust. POOL-2G is not (0.909 only at ≤30).
3. **No walk-forward ran** — the fold table is a calendar split of in-sample trades, not the WF protocol. Certification still requires the real pipeline end-to-end.
4. ETH-1h sleeve window is 2022→now vs 2021→now for the 4h sleeves; DSR is per-trade and window-insensitive, PF unaffected.

## 9. Infrastructure Notes

**Pooled-engine block (journal `eaeb1220`).** `PooledIndependentBacktestCoordinatorService` cannot honestly run DCB: (1) its walk loop (`walkGrid`: fillPending → evaluateSymbol → checkIntraBarDrawdown → markEquity) never invokes `TradeListenerService`, so DCB's armed SL/TP levels would silently never fire — javadoc confirms "v1 targets exitsOnCloseOnly archetypes"; (2) `buildContext` hardcodes `allowShort=FALSE`; (3) one `run.getInterval()` for the whole universe — no 4h+1h mix; (4) research pooled path wires no ML gates. A pooled DCB run would therefore certify a different strategy (long-only, stop-less, ungated) than the measured sleeves — not queued, on methodology grounds. This is a config blocker, not alpha evidence (`infra_failure_caused=true`).

**Path-format trap (session ops):** git-bash `curl -o /tmp/x` writes MSYS temp while Windows Python `open('/tmp/x')` reads `C:\tmp\x` — a stale May-24 state file there masqueraded as the live `/agent/state` response early in the session. All scratch IO moved to `C:/Project/.rtmp/`.

**Session also generated the five missing DB papers** for the prior (crashed) session's terminal queues: `BH-DCB-ETHUSDT-4H-6762447f`, `BH-DCB-ETHUSDT-1H-43b70ded`, `BH-DCB-BNBUSDT-4H-7b3710d8`, `BH-DCB-XRPUSDT-4H-6f7eebc5`, `BH-DCB-ETHUSDT-4H-75937702`.

## 10. Methodology Compliance Audit

| Rule | Compliant? | Notes |
|---|---|---|
| Universe BTC/ETH/SOL/BNB/XRP (hard rule #1) | YES | SOL + ETH only |
| Intervals in {5m,15m,1h,4h,1d} (hard rule #2) | YES | 4h + 1h |
| Research never mutates live (hard rule #3) | YES | read-only session; no live contact |
| Research-mode only — no promotion (hard rule #4) | YES | — |
| 10%/yr economic bar (hard rule #5) | YES | pooled ag estimate ≫ 10%/yr; no promotion claimed |
| V11 + V60 gates honored (hard rule #6) | YES | no verdict claimed from offline estimates; gates untouched |
| ≥ 3 dimensions traversed (hard rule #7) | YES | underlying sweeps traversed entry/exit/holding/gating/interval |
| Pre-registration before testing (hard rule #10) | YES | lead + wishlist journaled before analysis |
| Append-only durable evidence (hard rule #10) | YES | journals appended; no rows modified |
| Reviewer verdict authoritative (hard rule #12) | YES | no queue/walk-forward attempted without review — none attempted at all |
| No trading-JVM calls (hard rule #13) | YES | orchestrator HTTP + read-only psql on prod DB |

## 11. Conclusions

1. **Pooling is confirmed as the only certification path** for the DCB breakout family: solo-sleeve DSR cannot reach 0.90 at any achievable n (SOL-4h needs Sharpe ≈1.68 vs 1.25 observed; ETH surfaces carry 170–222-trial taxes).
2. **The three-sleeve gated book clears every V11 statistical estimate robustly** (n=772, ciL 1.365, DSR 0.963 at worst-case trials, 6/6 years) — the alpha case for the book is strong.
3. **The regime_eth_v2 gate is load-bearing**, transforming a dead ETH-1h surface (PF 1.02) into the book's largest and most diversifying sleeve (PF 1.42, corr −0.27 to SOL) — any certifiable pool must carry per-symbol ML gates.
4. **The engine cannot run any certifiable version of this book today**; the minimal listener+shorts fix alone is provably not worth building (POOL-U fails at 0.826).
5. **Implication for the research loop:** the lead is operator-gated — the highest-EV build is NOT the pooled coordinator extension but coordinated single-symbol per-fold runs + orchestrator-side pooled-series certification (zero JVM changes, reuses the fully-honest path), which is a certification-pipeline-semantics extension requiring explicit operator methodology approval before implementation.

## 12. Data Wishlist

| Priority | Item | Blocker type |
|---|---|---|
| 1 | Operator methodology decision: approve pooled-series certification via coordinated single-symbol runs (orchestrator-side pooled analyze + pooled walk-forward over the 3 sleeves), OR commission the full pooled-coordinator build (intra-bar listener + allowShort + per-symbol ML gates + cross-interval) | methodology / JVM code |
| 2 | If option A approved: orchestrator endpoints `POST /pool/backtest-series` + pooled WF protocol spec (researcher can implement in edit zone AFTER approval) | orchestrator code |

## 13. Appendix — Audit Trail

| Item | ID |
|---|---|
| Warm lead pursued | `DCB_POOLED_BOOK` (marker; pursuit 1/3) |
| Engine-block wishlist journal | `eaeb1220-d96a-4b43-b67c-b44ea21a3d91` |
| E3b evidence journal | `ef8b3942-636d-4a4b-8e33-01d8a17e199c` |
| Sleeve runs pooled | SOL-4h `da857a20`, gated ETH-4h `8f7df1db` (iter 557), gated ETH-1h `ec9359d7` (iter 531/`b0d73aab`), ungated ETH-4h `36742d6a` |
| Key iterations referenced | `98692470` (SOL best), `b59a4f15` (gated ETH-4h iter 561), `b0d73aab` (gated ETH-1h best), iters 484–497 (ungated ETH-1h baselines) |
| Walk-forward run | — (engine-blocked) |
| RUN_SUMMARY journal | RESEARCH_RUN_COMPLETE_2026-07-10 (this session) |
| Prior paper this continues | `RESEARCH_PAPER_DCB_SOLUSDT_4H_v1_ALGO_2026-07-09.md` |

---
*Paper generated by quant-researcher. DB registration: pooled analysis has no queue_id; underlying sleeve queues registered as `BH-DCB-*` papers listed in §9.*
