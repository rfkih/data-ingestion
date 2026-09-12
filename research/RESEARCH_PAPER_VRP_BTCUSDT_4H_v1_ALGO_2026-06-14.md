# Research Paper: VRP (VRP_BTC / VRP_ETH) — BTCUSDT & ETHUSDT × 4H & 1H Interval Study

**Author:** quant-researcher
**Date:** 2026-06-14
**Strategy:** `VRP_BTC`, `VRP_ETH`
**Surface:** `BTCUSDT` × `4H`/`1H` and `ETHUSDT` × `4H`/`1H` (consolidated interval study)
**Type:** ALGO
**Surface attempt:** v1 — ALGO (first VRP run at any interval other than 1d)
**Prior papers on this surface:** none (first attempt)
**Filename:** `RESEARCH_PAPER_VRP_BTCUSDT_4H_v1_ALGO_2026-06-14.md`
**Terminal:** OPERATOR_DIRECTED_COMPLETE (bounded task; not one of the seven autonomous-loop terminals)
**Goal status:** NOT HIT (all 8 cells INSUFFICIENT_EVIDENCE; no graduation candidate)
**Hypothesis:** `a577411e-c250-4149-bdcc-cbbd3c1dda9a`
**Queue(s):** `3f61fb46` (BTC 4h), `aa737bfb` (BTC 1h), `13cc1fc6` (ETH 4h), `fd9626b7` (ETH 1h)

---

## TL;DR

Operator-directed bounded re-validation of whether VRP's Deflated Sharpe can be lifted toward the 0.95 gate via a longer span, other coins, or a finer interval. Span and coins are data-impossible (DVOL exists only for BTC/ETH and only back to 2021-03-24). The untested lever — interval — was tested here at 4h and 1h for both coins over the full DVOL span. **Result: it makes things WORSE.** As the interval gets finer, raw trade count rises monotonically (BTC 119→312→534) but honest DSR FALLS monotonically (BTC 0.053→0.012→0.0054); on ETH the strong 1d edge (DSR 0.174) flips outright NEGATIVE at higher frequency (PF 0.78–0.95). This is the textbook signature of re-sampling a slow, autocorrelated vol-regime signal: more "trades" carry no new independent information, the bootstrap PF CI stays wide and spans 1.0, and the multiplicity-deflated DSR collapses. No lever lifts VRP toward the gate; VRP's edge is genuinely weak and data-bound.

*(No metrics table — no cell reached SIGNIFICANT_EDGE.)*

---

## 1. Background

VRP (variance-risk-premium long/flat) is live on real capital (VRP_BTC on BTCUSDT). The 2026-06-12 walk-forward re-score, after the low-frequency DSR-annualization fix, put VRP's honest DSR below the 0.95 gate; the operator's decision was keep-live-for-now and ask whether DSR can be improved. All prior COMPLETED VRP runs are 1d. Established hard constraints (from the prod DB, not re-discovered this session): DVOL (Deribit implied vol) exists for BTCUSDT + ETHUSDT only; DVOL history floor is 2021-03-24 (so the full usable span ~2021-05 is already in use and cannot be extended); a longer span and other coins are therefore data-impossible. The only untested lever was the interval axis — no VRP had ever run at 4h or 1h.

---

## 2. Hypothesis

**Mechanism:** `VarianceRiskPremiumStrategyEngine` is a long/flat regime switch. It goes 100% long when the 30-day z-score of Deribit implied vol exceeds a threshold (`dvol_zscore_30d > thetaZ`, ZSCORE signal form) and holds until the z-score drops back below threshold; flat otherwise. There are no stops/TPs (`exitsOnCloseOnly`). The signal is a slow vol-regime indicator: the 30-day implied-vol z-score changes slowly, so a position spans many consecutive bars.

**Pre-registration:** Hypothesis `a577411e-c250-4149-bdcc-cbbd3c1dda9a` registered 2026-06-14, before the earliest sweep iteration. Falsification criterion: EITHER honest DSR rises materially at finer intervals (more independent vol-cycle observations) OR DSR stays flat/falls because intraday VRP trades are autocorrelated near-duplicates of the same slow vol regime (effective sample ≪ n).

**Type:** ALGO (existing VRP engine, parametric sweep on interval × thetaZ).

---

## 3. Methodology

### 3.1 Statistical Gates (V11 + V60) — NOT loosened

| Gate | Threshold | Binding? |
|---|---|---|
| n_trades | ≥ 100 | YES |
| PF 95% bootstrap CI lower | > 1.0 | YES |
| DSR (Bailey–LdP, n_trials from hypothesis_audit) | ≥ 0.95 | YES |
| Statistical verdict | SIGNIFICANT_EDGE | YES |
| ann. geometric return at alloc-90 (ag90) | ≥ 10%/yr | YES |

### 3.2 Sweep Design

- **Type:** GRID
- **Backtest window:** 2021-05-01 → 2026-06-13 (~1,869 days, ~20 quarters) — full DVOL span. Window override (`backtest_window.start_time`) was set explicitly to avoid the default 2024-01-01 floor.
- **Dimensions swept:** `interval_name` ∈ {4h, 1h} (× the 1d baseline already on file), `thetaZ` ∈ {0.0, 0.5}, `signalForm` = ZSCORE. Across the study: symbol × interval × thetaZ (≥3 dimensions).
- **Total cells:** 8 executed (BTC/ETH × 4h/1h × thetaZ{0,0.5}), 8 completed.

### 3.3 Walk-Forward Protocol

**Not run on any cell — and this is the methodologically correct choice, not a gap.** Walk-forward tests the OUT-OF-SAMPLE stability of an IN-SAMPLE edge. Every cell here has DSR ≤ 0.012 (≪ 0.95) and a PF 95% CI that spans or sits below 1.0 in-sample — there is no edge to stabilize. The graduation-review gate carries a BLOCKER on `dsr_threshold ≥ 0.95` that would REJECT every cell; `override_review_gate=true` was deliberately NOT used (no operator justification, and no edge to validate). The WF verdict is gate-determined for all 8 cells: non-ROBUST / not-reachable.

---

## 4. Parameter Space Explored

| Axis | Values Tested |
|---|---|
| `interval_name` | 4h, 1h (vs 1d baseline) |
| `thetaZ` | 0.0, 0.5 |
| `signalForm` | ZSCORE |

**Total iterations:** 8 (DSR-deflated cumulative trial count per cell: 152–192)

**Edge verdict distribution:**

| Verdict | Count |
|---|---|
| SIGNIFICANT_EDGE | 0 |
| INSUFFICIENT_EVIDENCE | 8 |
| NO_EDGE_DETECTED (DISCARD) | 0 |

---

## 5. Results

### 5.1 Edge summary — the autocorrelation diagnostic

The binding finding is the monotone divergence between trade count and DSR as the interval gets finer. More trades, lower DSR, wider PF CI — the unmistakable signature of non-independent (autocorrelated) observations re-sampling one slow signal.

**Comparison table (1d baseline = existing rows; 4h/1h = this study). DSR values are honest (post-2026-06-12 annualization fix) and directly comparable across all rows. 1d ag90 carries the legacy low-frequency-annualization-inflation caveat; 4h/1h ag90 is honest.**

| Symbol | Interval | best thetaZ | Trades | Honest DSR | PF (point) | PF 95% CI | CAGR@90 (ag90) | Sharpe(ann) | WF verdict |
|---|---|---|---|---|---|---|---|---|---|
| BTCUSDT | 1d (baseline) | 0.0 | 119 | **0.053** | 1.62 | [0.89, 3.04] | 41.3%* | 0.73 | sub-gate (DSR≪0.95) |
| BTCUSDT | 4h | 0.0 | 312 | 0.0124 | 1.33 | [0.85, 2.07] | 26.0% | 0.54 | not-reachable (DSR≪0.95) |
| BTCUSDT | 1h | 0.0 | 534 | 0.0054 | 1.19 | [0.81, 1.76] | 15.9% | 0.39 | not-reachable (DSR≪0.95) |
| ETHUSDT | 1d (baseline) | 0.0 | 97 | **0.174** | 1.22 | [0.70, 2.34] | 16.2%* | 0.30 | sub-gate (DSR≪0.95) |
| ETHUSDT | 4h | 0.0 | 294 | 0.0001 | 0.95 | [0.62, 1.48] | −4.7% | −0.11 | not-reachable (negative edge) |
| ETHUSDT | 1h | 0.0 | 503 | 0.0 | 0.85 | [0.58, 1.28] | −15.1% | −0.35 | not-reachable (negative edge) |

\* 1d ag90 is annualization-inflated (low-frequency artifact, flagged by the operator); DSR is honest.

thetaZ=0.5 cells are uniformly weaker than thetaZ=0.0 at every interval (BTC 4h: DSR 0.0014, ag90 8.1%; BTC 1h: DSR 0.0005, ag90 2.6%; ETH 4h: PF 0.87, ag90 −10%; ETH 1h: PF 0.78, ag90 −19%).

**The pattern is exact:**
- BTC: n 119 → 312 → 534 (rising); DSR 0.053 → 0.012 → 0.0054 (falling); Sharpe 0.73 → 0.54 → 0.39 (falling).
- ETH: n 97 → 294 → 503 (rising); DSR 0.174 → 0.0001 → 0.0 (collapsing); PF 1.22 → 0.95 → 0.85 (going negative).

### 5.2 Best higher-frequency cell (anchors future comparison)

| Param | Value |
|---|---|
| symbol/interval | BTCUSDT / 4h |
| `signalForm` | ZSCORE |
| `thetaZ` | 0.0 |

| Metric | Value |
|---|---|
| iteration_id | `cc1df163-794d-4742-a532-6303f14b6463` |
| n_trades | 312 |
| PF (point) | 1.33 |
| PF 95% CI | [0.846, 2.074] (spans 1.0 → fails) |
| DSR | 0.0124 |
| ag90 (%/yr) | 25.97 |
| Sharpe (ann) | 0.54 |
| Calmar | 0.54 |
| Max drawdown | 51.5% |
| Win rate | 51.3% |
| Statistical verdict | INSUFFICIENT_EVIDENCE (CI spans 1.0) |

Note: this is the single higher-frequency cell with positive ag90 AND positive Sharpe. Even so, its DSR (0.012) is ~4× WORSE than the 1d baseline's (0.053) and ~80× below the gate. The 26% ag90 is real but uninvestable — the wide PF CI [0.85, 2.07] says the edge is not statistically distinguishable from zero, and the 51% max drawdown makes the Calmar (0.54) poor.

---

## 10. Methodology Compliance Audit

| Rule | Compliant? | Notes |
|---|---|---|
| BTC/ETH/SOL only (hard rule #1) | YES | VRP is DVOL-bound to BTC/ETH; no off-universe symbols. |
| Intervals in {5m,15m,1h,4h,1d} (hard rule #2) | YES | 4h, 1h tested; 1d baseline. |
| Protected strategies untouched (hard rule #3) | YES | Ran on research-mode `enabled=false, simulated=true` VRP seeds; live book untouched. |
| Research-mode only — no live promotion (hard rule #4) | YES | No promotion; no graduation reached. |
| 10%/yr economic bar enforced (hard rule #5) | YES | ag90 reported; no cell shelved as a "pass" below bar. |
| V11 + V60 gates honored (hard rule #6) | YES | DSR≥0.95 / PF-CI / n≥100 enforced; NOT loosened; +20bps slippage gate NOT enforced (retired). |
| ≥3 axes swept (hard rule #7) | YES | symbol × interval × thetaZ. |
| Pre-registration before testing (hard rule #10) | YES | Hypothesis registered before all 8 iterations. |
| Append-only durable evidence (hard rule #10) | YES | No durable rows mutated; hypothesis left ACTIVE, falsification recorded via STRATEGY_OUTCOME. |
| Reviewer verdict authoritative (hard rule #12) | YES | Plan reviews APPROVED for VRP_BTC + VRP_ETH before queue; no override used. |
| Research JVM only — no trading JVM calls (hard rule #13) | YES | All work via orchestrator :8082. |

---

## 11. Conclusions

1. **Interval makes VRP DSR worse, not better.** Finer intervals raise trade count but lower honest DSR monotonically (BTC 0.053→0.012→0.0054; ETH 0.174→0.0001→0.0) — the diagnostic for re-sampling a slow autocorrelated signal.
2. **The PF 95% CI stays wide and spans 1.0 at every higher-frequency cell**, confirming the extra trades add no independent information; the bootstrap correctly refuses to credit them.
3. **ETH VRP's edge is purely low-frequency.** The best 1d performer (DSR 0.174, PF 1.22) flips outright negative at 4h/1h (PF 0.78–0.95, negative ag90 and Sharpe) — chopping the slow signal finer introduces cost/noise that destroys it.
4. **No lever lifts VRP toward the gate.** Span: data-impossible (DVOL floor 2021-03-24). Coins: data-impossible (DVOL is BTC/ETH only). Interval: tested, makes it worse. VRP's true information content is ~a few dozen independent vol cycles over 5 years; it cannot reach n≥100 AND DSR≥0.95 at any interval.
5. **Implication for the research loop:** VRP is a slow, low-Sharpe regime tilt whose honest DSR (0.053 BTC / 0.174 ETH at 1d) is its ceiling. It is genuinely weak and data-bound. Unlocking VRP requires a NEW orthogonal IV data source (more coins) or a structurally different vol signal — not more parameter or interval search on the existing DVOL feed. Walk-forward on any current cell is gate-determined non-ROBUST and was correctly not run.

---

## 12. Data Wishlist

| Priority | Item | Blocker type |
|---|---|---|
| 1 | Implied-vol (DVOL-equivalent) feed for SOL/BNB/XRP/ADA/DOGE/AVAX | new data source — would be the ONLY way to extend VRP beyond BTC/ETH (cross-sectional vol-risk-premium needs breadth) |
| 2 | Pre-2021 implied-vol history for BTC/ETH | new data source — would extend the VRP span below the 2021-03-24 DVOL floor and add independent vol cycles, the only thing that could raise effective-sample DSR |

---

## 13. Appendix — Audit Trail

| Item | ID |
|---|---|
| Hypothesis | `a577411e-c250-4149-bdcc-cbbd3c1dda9a` |
| Plan review (VRP_BTC) | `plan:VRP_BTC:038ff6a6...:a577411e...` (APPROVED) |
| Plan review (VRP_ETH) | `plan:VRP_ETH:038ff6a6...:a577411e...` (APPROVED) |
| Queue BTC 4h / 1h | `3f61fb46-a815-4ba8-ae46-933f06470ecc` / `aa737bfb-1d76-44cd-9453-399732a1c282` |
| Queue ETH 4h / 1h | `13cc1fc6-65de-472c-b2ad-223656404b5c` / `fd9626b7-ee4f-4f70-8bc0-2b470f5104aa` |
| BTC 4h iters (thetaZ 0 / 0.5) | `cc1df163-794d-4742-a532-6303f14b6463` / `5ec821d0-e34d-401f-9696-453046513be5` |
| BTC 1h iters (thetaZ 0 / 0.5) | `4db71d5c-a454-4b13-8a24-3c0425b63172` / `d5201ebf-cd35-4a05-910b-2cfcd9f72dc6` |
| ETH 4h iters (thetaZ 0 / 0.5) | `84aed883-285f-4a6c-a10d-9151aa2e3b11` / `5a6d3c0c-73fd-4e84-8aa5-52732772cf02` |
| ETH 1h iters (thetaZ 0 / 0.5) | `118a1591-0dd9-42ce-9a3d-9477a40b0b9c` / `f4afc8ff-0228-4df8-90ae-816d8591c3b1` |
| Walk-forward run | none (gate-determined non-ROBUST; not run) |
| STRATEGY_OUTCOME journal | `6dc9d06d-930b-4a5b-b2b6-a818dc48d968` |
| RUN_SUMMARY journal | (written at session terminal — see journal) |

---
*Paper generated by quant-researcher. DB registration: `POST /papers/<queue_id>/generate` (all 4 queues registered, WORKING_PAPER status).*
