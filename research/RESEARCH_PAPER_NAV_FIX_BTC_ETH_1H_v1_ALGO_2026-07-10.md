# Research Paper: NAV_FIX — BTCUSDT + ETHUSDT × 1h

**Author:** Claude (main session, local $0 pre-test — alpha-discovery handoff)
**Date:** 2026-07-10
**Strategy:** `NAV_FIX` (never built — pre-build gate)
**Surface:** BTCUSDT + ETHUSDT × 1h, post-ETF window (BTC 2024-01-11+, ETH 2024-07-23+)
**Type:** ALGO
**Surface attempt:** v1 — ALGO (first and terminal)
**Terminal:** PRE_TEST_FALSIFIED (engine build cancelled at $0)
**Goal status:** NOT HIT
**Hypothesis:** journal `c1a270c5-14b8-495f-9717-7049f095dbf3` (pre-registered 2026-07-10 05:26 UTC, before any test ran)
**Verdict row:** journal `11567b7a-a3be-4846-a999-5ff74746a59a` (ANTI_PATTERN, linked)
**Queue(s):** none — never queued (engine_exists=false; handoff protocol honored)

---

## TL;DR

Alpha-discovery (run `wf_40c49dab-c44`) proposed ETF NAV-fix flow pressure: authorized participants
must execute creation/redemption baskets into the 4pm-ET NAV, so fade the fix-bar move (reversion)
and ride the pre-fix session move (drift). The mandatory $0 offline pre-test on 1,164 fix events
formally PASSED the registered gate on one cell (fade, hold-3, pooled: +6.7bp/trade, NW-t +2.31) —
but a placebo anchor control killed the mechanism: the identical fade rule at 14:00 NY (no fix there)
is *stronger* (+8.1bp, t +2.43) and 17:00 (right after the fix) shows nothing. The effect is generic
US-afternoon 1h mean-reversion, not fix flow — and it sits below the ~9bp taker cost floor anyway.
The drift cell had the wrong sign everywhere. Engine build cancelled; the surviving lesson is a loop
rule: **deterministic-clock hypotheses must carry a placebo-anchor control.**

---

## 1. Background

Produced by the alpha-discovery workflow as survivor 2/2 of its adversarial gate (16 mechanisms
considered, 3 killed pre-registration). Pre-registered per the confirmatory handoff BEFORE any data
was touched. `engine_exists=false` (no hour-of-day logic in any JVM engine), so per protocol it was
never queued; the hypothesis carried a mandatory pre-build gate copied from the MACRO_EVENT_WINDOW
lesson: prove the conditional effect offline for $0 before spending ~1 operator-day on an engine.

## 2. Hypothesis (pre-registered)

Mechanism: mandate-driven, price-insensitive AP/tracker flow concentrates in the 1h bar closing
16:00 America/New_York on weekdays (Kaiko: >6.7% of daily BTC volume). Grossman–Miller pressure →
pre-fix drift + post-fix reversion (FX 4pm-London-fix analog: Evans 2018; Melvin & Prins 2015).
Falsification: if neither pressure nor decay appears, mechanism dead. Build gate: predicted sign
with |NW-t| ≥ 2 on the pooled 2024+ sample.

## 3. Methodology

1h OHLC exported read-only from prod `market_data` (44,218 rows, 2024-01→2026-07-09). Fix bar
selected by DST-correct tz conversion; events require hourly-contiguous bars fix−7..fix+3.
BTC 651 / ETH 513 events. POST_FIX_REVERT: fade sign(r_fix), enter next-bar open, exit close of
fix+H, H ∈ {1,3}, θ ∈ {0, 25bp}. PRE_FIX_DRIFT: sign of the 6-bar move at 15:00 NY close, held
through the fix bar. Newey–West t (lag 5). Placebo: identical fade rule anchored at
10/12/14/15/17/20:00 NY. All compute local (operator constraint); scripts `.rtmp/navfix_pretest.py`,
`.rtmp/navfix_placebo.py`.

## 4. Results

### 4.1 POST_FIX_REVERT (predicted +)

| cell | n | mean bp | NW-t | gate |
|---|---|---|---|---|
| θ=0, H=1, pooled | 1164 | +1.5 | +0.87 | fail |
| **θ=0, H=3, pooled** | 1164 | **+6.7** | **+2.31** | **PASS (letter)** |
| θ=0, H=3, BTC | 651 | +9.0 | +2.68 | pass |
| θ=0, H=3, ETH | 513 | +3.9 | +0.77 | fail |
| θ=25bp, H=3, pooled | 685 | +7.3 | +1.69 | fail |
| θ=25bp, H=3, BTC | 347 | +12.9 | +2.60 | pass (single-asset) |

### 4.2 PRE_FIX_DRIFT (predicted +) — FALSIFIED

All cells negative (pooled −1.1 to −1.5bp, t −0.6 to −0.8). No pre-fix pressure is visible.

### 4.3 Placebo anchor control — the kill

Fade rule, H=3, θ=0, pooled, by NY anchor hour:

| anchor | mean bp | NW-t |
|---|---|---|
| 10:00 | −6.3 | −1.48 |
| 12:00 | −3.4 | −0.88 |
| **14:00 (no fix)** | **+8.1** | **+2.43** |
| 15:00 | +3.8 | +1.35 |
| **16:00 (THE FIX)** | +6.7 | +2.31 |
| 17:00 (post-fix) | +0.8 | +0.30 |
| 20:00 | +3.4 | +1.16 |

The fix hour is not distinguishable from adjacent afternoon anchors; 14:00 beats it. Attribution to
NAV flow fails — this is generic US-afternoon hourly mean-reversion.

### 4.4 Economics

Taker round-trip ≈ 9bp. Every pooled cell mean < 9bp → net-negative. Best net cell (BTC θ=25 H=3):
+12.9 − 9 ≈ +4bp/trade, cost-adjusted t ≈ 0.8 — far below any certification bar.

## 5. Conclusions

1. The registered primary cell passes the gate's letter (pooled t=2.31) but fails mechanism
   attribution: a non-fix placebo anchor reproduces and exceeds it.
2. The mutually-falsifying drift cell has the wrong sign everywhere — no visible pre-fix pressure.
3. After the ~9bp cost floor nothing survives; the best net cell is statistically indistinguishable
   from zero.
4. Engine build cancelled at $0 — second consecutive validation of the pre-build-gate discipline
   (MACRO_EVENT_WINDOW precedent).
5. **Loop rule (journaled as ANTI_PATTERN `11567b7a`):** any deterministic-clock/event-anchored
   hypothesis must pre-register a placebo-anchor control; an event-hour t-stat alone is
   uninterpretable.

## 6. Methodology Compliance Audit

| Rule | Compliant? |
|---|---|
| Pre-registration before testing (gap: registered 05:26, first test ran after) | YES |
| engine_exists=false → never queued | YES |
| Append-only evidence (hypothesis + linked ANTI_PATTERN verdict) | YES |
| Local-PC compute; VPS read-only export only | YES |
| No V11/V60 gate involvement (never reached a sweep) | N/A |

## 7. Appendix — Audit Trail

| Item | ID |
|---|---|
| Hypothesis | `c1a270c5-14b8-495f-9717-7049f095dbf3` |
| Verdict (ANTI_PATTERN) | `11567b7a-a3be-4846-a999-5ff74746a59a` |
| Producer run | alpha-discovery `wf_40c49dab-c44` |
| Sibling survivor (still ACTIVE, data-blocked) | skew-gate `470ca035-03d8-4ea2-a2d3-d19a3cc1616f` + wishlist `b820fc10-975a-4bfd-a5b3-a48c816a264b` |
| Scripts / data | `.rtmp/navfix_pretest.py`, `.rtmp/navfix_placebo.py`, `.rtmp/mldata/ohlc_1h_btc_eth_2024.csv` |
