# Research Paper: ATR_MOM — ETHUSDT × 4H (with SOLUSDT × 4H two-sidedness confirmation)

**Author:** quant-researcher
**Date:** 2026-07-13
**Strategy:** `ATR_MOM` (ATR-expansion + efficiency-ratio trend-continuation)
**Surface:** `ETHUSDT` × `4h` (primary) + `SOLUSDT` × `4h` (confirmation)
**Type:** CHAR
**Surface attempt:** v1 — CHAR (first ATR_MOM 4h characterization; the archetype had only ever run at 1h before)
**Prior papers on this surface:** none (first attempt)
**Terminal:** ARCHETYPE_EXHAUSTION (2nd in 7d window — the run-ending terminal)
**Goal status:** NOT HIT
**Hypothesis:** `d1b932ea-81d1-4405-9c77-5c67039329da` (ETH) + `407a1a2f-9363-403f-8c48-30860ff4d1b1` (SOL)
**Queue(s):** `31fc1cd9` (ETH conf.), `1418d16e` (ETH fire-rate), `f9d7eab4` (ETH throttle), `ac4575bf` (SOL regime)

---

## TL;DR

ATR_MOM is an ADX + directional-efficiency-ratio-gated ATR-expansion trend-continuation breakout. It had near-missed the V11 gate at 1h on ETH (PF-CI-low 0.98, n132) under a heavy 51-iteration DSR tax, so this session tested it on the fresh 4h interval where the mining tax is near-zero. The signal is genuinely REAL — a null-screen returned EDGE_PRESENT (8/8 draws PF>1.0) and every confirmatory cell was point-profitable. Across three ETH sweeps I successfully drove it across the n=100 power floor AND above PF-CI-low>1.0 AND above the 10%/yr ann90 bar simultaneously (best cell atrExp1.3/er0.18/adx16: n=131, PF-CI-low 1.039, ann90 +16.6%/yr). **But it never reached SIGNIFICANT_EDGE, and the reason is fatal and structural: the edge is a pure BULL-regime artifact.** Across all 8 ETH cells ~85-88% of trades and 100%+ of profit come from BULL; NEUTRAL is uniformly negative; BEAR has ~0 trades across a 5.5-year window that includes the entire 2022 bear. A dedicated SOLUSDT@4h confirmation (highest-beta coin, violent 2022 bear) reproduced the defect exactly — **BEAR = ZERO trades in every cell** — proving the bull-only behavior is structural to the archetype, not ETH-specific. DSR (0.07-0.09) and the regime-concentration gate correctly reject a single-regime signal. ATR_MOM is a bull-trend beta harvester by construction; the unconditional trend-continuation family is exhausted for certification.

*(No cell reached SIGNIFICANT_EDGE — metrics table omitted per template; best-cell metrics in §5.2.)*

---

## 1. Background

The prior research run ended GOAL_HIT (2026-07-12): the DCB_POOL 3-sleeve regime-gated + pooled book was certified (n=772, PF 1.63, DSR 0.944, WF ROBUST 18/18) and is now live. That closed the DCB Donchian-breakout family. This fresh run opened with the DCB family closed and most classic families already falsified (funding-Z, VBO, intraday-EMA, XS-dispersion, OI-quadrant, ALT_CAP_FADE, positioning-XS, CVD/OFI, MACRO_EVENT, NAV-fix, ML-on-carry). The session's first experiment (MRO band-fade @ SOLUSDT@4h) was falsified — completing the cross-coin map that mean-reversion fades invert on all three majors. This paper covers the pivot to a structurally-distinct family: unconditional trend-continuation via ATR_MOM, chosen for its 1h ETH near-miss and its orthogonality to both the shipped DCB book and the just-falsified fade family.

---

## 2. Hypothesis

**Mechanism:** ATR_MOM opens LONG when the ATR-ratio expansion exceeds `atrExpansionMult` AND the signed 20-bar efficiency ratio exceeds `erTrendMin` (positive directional momentum) AND ADX exceeds `adxFloor`; symmetric SHORT for the negative case. Exit is a fixed `tpR` take-profit, an `stopAtrMult`×ATR stop, break-even at 1R, and a timed exit at `maxBarsHeld`×interval. It rides confirmed directional-momentum expansions.

**Pre-registration (ETH):** Hypothesis `d1b932ea` registered before the earliest sweep iteration; null-screen (EDGE_PRESENT) gated the confirmatory sweep. Falsification criterion: all cells PF≤1.0 or PF-CI-low<0.90 at n≥100, OR n-starvation. **Pre-registration (SOL):** Hypothesis `407a1a2f` registered specifically to test the short-side/bear dimension ETH could not exercise. Falsifier: BEAR n<10 (short-side never fires → structural defect).

**Type:** ALGO (both).

---

## 3. Methodology

### 3.1 Statistical Gates (V11 + V60)

| Gate | Threshold | Binding? |
|---|---|---|
| n_trades | ≥ 100 | crossed (best n=131) |
| PF 95% bootstrap CI lower | > 1.0 | crossed (best 1.039) |
| DSR (Bailey–LdP, n_trials from hypothesis_audit) | ≥ 0.90 | **BINDING — failed (0.07-0.09)** |
| Statistical verdict | SIGNIFICANT_EDGE | not reached |
| ann. geometric return at alloc-90 (ag90) | ≥ 10%/yr | crossed (+16.6) |

*Note: the operator lowered the DSR bar to 0.90 (2026-06-15). The mission GOAL_HIT bar (ann90≥10 + WF ROBUST) is stricter than the orchestrator's post-2026-06-19 gate, which dropped the 10%/yr economic floor; I applied ann90≥10 myself regardless.*

### 3.2 Sweep Design

- **Type:** GRID
- **Backtest window:** 2021-01-01 → 2026-07 (~5.5 years, includes full 2022 bear)
- **Dimensions swept (ETH, across 3 sweeps):** adxFloor {14,16,18,20,26}, atrExpansionMult {1.2,1.3,1.4,1.6}, erTrendMin {0.18,0.22,0.25}, tpR {1.5,1.8,2.4} — plus pinned stopAtrMult 1.5, maxBarsHeld 24, maxEntryRiskPct 0.06, intervalMinutes 240
- **Total cells:** 22 executed across 4 queues (8 ETH conf. + 6 ETH fire-rate + 8 ETH throttle + 6 SOL regime)

### 3.3 Walk-Forward Protocol

Did not run — no cell reached SIGNIFICANT_EDGE (DSR gate blocked graduation).

---

## 4. Parameter Space Explored

| Axis | Values Tested |
|---|---|
| `adxFloor` | 14, 16, 18, 20, 26 |
| `atrExpansionMult` | 1.2, 1.3, 1.4, 1.6, 1.7 |
| `erTrendMin` | 0.18, 0.22, 0.25 |
| `tpR` | 1.5, 1.8, 2.4 |
| `instrument` | ETHUSDT, SOLUSDT |

**Total iterations:** 28 (ETH 22 + SOL 6); cumulative DSR-deflated trial count on ETH: 202.

**Edge verdict distribution:**

| Verdict | Count |
|---|---|
| SIGNIFICANT_EDGE | 0 |
| INSUFFICIENT_EVIDENCE | 28 |
| NO_EDGE_DETECTED (DISCARD) | 0 |

---

## 5. Results

### 5.1 Edge summary

The ATR_MOM 4h signal on ETH is real and point-profitable everywhere (null-screen 8/8 PF>1.0). The binding constraint evolved across three ETH sweeps:
1. **Conf. sweep** (adxFloor/atrExp/tpR): best n=80, PF-CI-low 0.971 — n-power short.
2. **Fire-rate sweep** (lower adxFloor + shorter tpR): shortening tpR to 1.5 FLIPPED PF-CI-low>1.0 (3 cells 1.009-1.045) but n stuck at 84-86. Key learning: **adxFloor is NOT the fire-rate throttle** (n flat as adx dropped 20→14).
3. **Throttle sweep** (loosen atrExpansionMult + erTrendMin, the true levers): crossed n=100 — **4 cells cleared n≥100 AND PF-CI-low>1.0 AND ann90>10 simultaneously**.

Yet all 28 stayed INSUFFICIENT_EVIDENCE. The binding gate at the end was **DSR (0.07-0.09, n_trials 202)** — and the root cause of the low DSR is regime concentration: the edge is bull-only (§6.3-equivalent below).

### 5.2 Best cell (ETH throttle sweep — anchors future comparisons)

| Param | Value |
|---|---|
| `atrExpansionMult` | 1.3 |
| `erTrendMin` | 0.18 |
| `adxFloor` | 16 |
| `tpR` | 1.5 |

| Metric | Value |
|---|---|
| iteration_id | (throttle cell, queue f9d7eab4) |
| n_trades | 131 |
| PF (point) | ~1.5 |
| PF 95% CI lower | 1.039 |
| DSR | 0.085 |
| ag90 (%/yr) | +16.64 |
| Statistical verdict | INSUFFICIENT_EVIDENCE |

**Regime breakdown of the best cell (the fatal finding):**

| Regime | n | PnL | WR |
|---|---|---|---|
| BULL | 111 | +591 | 0.57 |
| NEUTRAL | 19 | −86 | ~0.24 |
| BEAR | 1 | −15 | — |

Every ETH cell showed this shape: ~85-88% of trades in BULL, NEUTRAL uniformly negative, BEAR ≈ 0 trades across 5.5 years including all of 2022.

### 5.3 SOLUSDT@4h confirmation (the decisive two-sidedness test)

SOL was chosen as the sharpest possible test of the short-side: highest beta in the universe, −96% 2022 bear with repeated sharp down-legs. Null-screen was EDGE_PRESENT but marginal (share PF≥1.0 = 0.375, median 0.93). The 6-cell confirmatory sweep regime split:

| Cell (adx/atrExp) | n | PF-CI-low | ann90 | BULL | NEUTRAL | BEAR |
|---|---|---|---|---|---|---|
| 20 / 1.7 | 13 | 0.323 | +1.5 | n12/+57 | n1/−14 | **0** |
| 20 / 1.5 | 35 | 0.482 | +0.3 | n31/+35 | n4/−15 | **0** |
| 20 / 1.3 | 78 | 0.589 | −0.2 | n71/+66 | n7/−50 | **0** |
| 16 / 1.7 | 14 | 0.461 | +2.9 | n13/+94 | n1/−14 | **0** |
| 16 / 1.5 | 39 | 0.552 | +1.5 | n34/+83 | n5/−32 | **0** |
| 16 / 1.3 | 87 | 0.598 | −1.8 | n74/+42 | n13/−64 | **0** |

**BEAR = ZERO trades in every single cell**, exactly as on ETH — even on SOL's violent 2022 bear. SOL's bull signal is also strictly weaker than ETH's (PF-CI-low 0.32-0.60 vs ~1.0). The falsifier fired.

---

## 9. Infrastructure Notes

No infrastructure failures. Orchestrator/JVM/DB healthy throughout; all drains completed cleanly (MAX_ITERS_REACHED terminals, queue-exhausted). One minor client-side note: two `/journal` POSTs 422'd on title length > 300 chars and were retried with shortened titles.

---

## 10. Methodology Compliance Audit

| Rule | Compliant? | Notes |
|---|---|---|
| Universe {BTC,ETH,SOL,BNB,XRP} (hard rule #1) | YES | ETHUSDT + SOLUSDT only |
| Intervals in {5m,15m,1h,4h,1d} (hard rule #2) | YES | 4h |
| Live strategies untouched (hard rule #3) | YES | research-mode ATR_MOM (disabled+simulated) |
| Research-mode only — no live promotion (hard rule #4) | YES | no promote call |
| 10%/yr economic bar enforced (mission) | YES | applied ann90≥10 myself despite orchestrator floor removal |
| V11 + V60 gates honored (hard rule #6) | YES | DSR gate correctly blocked; no loosening |
| ≥ 3 axes swept (hard rule #7) | YES | 8 dims total on ATR_MOM |
| Pre-registration before testing (hard rule #10) | YES | both hypotheses pre-null-screen |
| Append-only durable evidence (hard rule #10) | YES | only INSERTs |
| Reviewer verdict authoritative (hard rule #12) | YES | every sweep plan-reviewed APPROVED |
| Research JVM only (hard rule #13) | YES | orchestrator :8082 |

---

## 11. Conclusions

1. **The ATR_MOM 4h trend-continuation signal is genuinely real and profitable** — null-screen EDGE_PRESENT (8/8 PF>1.0), all confirmatory cells point-profitable, and I drove it across n≥100 + PF-CI-low>1.0 + ann90>10 simultaneously (best +16.6%/yr).
2. **It is nonetheless uncertifiable because it is a pure BULL-regime artifact** — ~85-88% of trades and 100%+ of profit from BULL, NEUTRAL uniformly negative, BEAR ≈ 0 trades across 5.5y including all of 2022.
3. **The bull-only defect is STRUCTURAL, not ETH-specific** — SOLUSDT@4h (highest beta, −96% 2022 bear) reproduced BEAR=0 trades in every cell. The mechanism: high-ATR-expansion + high-directional-efficiency bars are overwhelmingly up-moves on crypto (up-legs are sharper/more-efficient; down-legs grind and whipsaw), so the long gate fires and the short gate is starved.
4. **DSR (0.07-0.09) and the regime-concentration gate correctly rejected it** — the gates did their job on a single-regime signal that would fail any bear-containing walk-forward fold.
5. **Key craft learning:** for ATR_MOM the fire-rate throttle is the ATR-expansion + efficiency-ratio gate, NOT the ADX floor (n was flat as adxFloor dropped 20→14; only loosening atrExpansionMult/erTrendMin raised n).
6. **Implication for the research loop:** unconditional single-direction directional archetypes on the 5-coin universe are exhausted — mean-reversion fades invert (MRO/MMR), trend-continuations are structurally bull-only (ATR_MOM), and the only certifiable structure found (DCB) required regime-gating + pooling (shipped/closed). The next credible direction is data/seeding-gated.

---

## 12. Data Wishlist

| Priority | Item | Blocker type |
|---|---|---|
| 1 | Seed `account_strategy` rows (disabled+simulated) for TPR/TPB `trend_pullback` @4h on ETHUSDT+SOLUSDT — the one structurally-distinct untested archetype (pullback-into-confirmed-trend, two-sided by construction; currently 412 `account_strategy_missing`) | JVM/DB seed |
| 2 | Paid Tardis options-surface backfill to unlock the RR25-skew stress-gate on the pooled DCB book (operator purchase decision) | data backfill |
| 3 | Seed ATR_MOM @4h on a high-beta alt with a distinct bear structure (LINK/AVAX/NEAR) if a two-sided variant is ever pursued — though this paper's structural finding suggests low priority | JVM/DB seed |

---

## 13. Appendix — Audit Trail

| Item | ID |
|---|---|
| Hypothesis (ETH) | `d1b932ea-81d1-4405-9c77-5c67039329da` |
| Hypothesis (SOL) | `407a1a2f-9363-403f-8c48-30860ff4d1b1` |
| Queues | `31fc1cd9`, `1418d16e`, `f9d7eab4`, `ac4575bf` |
| Best iteration (ETH throttle) | `e9d4bbd0-3107-4ded-a921-3a97d6f4f27b` (n122 sibling) / best n131 cell in queue f9d7eab4 |
| Best iteration (SOL) | `b2817c9c-a60e-4cb3-8442-99a82303dff1` |
| Null-screen outcomes | `c1222191` (ETH EDGE_PRESENT), `6b31ae12` (SOL EDGE_PRESENT-marginal) |
| STRATEGY_OUTCOME (ETH falsification) | `e0ddb2f9-7cf6-4f8b-8a66-e9854992e5e9` |
| STRATEGY_OUTCOME (SOL structural falsification) | `44e1ce27-e75c-4394-a33d-6577d3c08b1b` |
| RUN_SUMMARY (fire-rate, throttle) | `65914b1d`, `4397839c` |
| Soft ARCHETYPE_EXHAUSTION | `b77de6ae-7faa-4dec-b90d-181f57ba676e` |

---
*Paper generated by quant-researcher. DB registration: `POST /papers/<queue_id>/generate`.*
