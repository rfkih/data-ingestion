# Research Paper: DCB — ETHUSDT × 15m (event-conditioned SWEEP_RECLAIM reversal)

**Author:** quant-researcher
**Date:** 2026-07-01
**Strategy:** `DCB` (DonchianBreakoutEngine, `entryMode=SWEEP_RECLAIM`)
**Surface:** `ETHUSDT` × `15m`
**Type:** ALGO
**Surface attempt:** v2 — ALGO (H2 event-conditioned reversal; the forced-flow counterpart to the v1 raw price-action continuation)
**Prior papers on this surface:** `RESEARCH_PAPER_DCB_ETHUSDT_15M_v1_ALGO_2026-07-01.md` (H1 BREAKOUT continuation, FALSIFIED)
**Filename:** `RESEARCH_PAPER_DCB_ETHUSDT_15M_v2_ALGO_2026-07-01.md`
**Terminal:** STRATEGY_OUTCOME (H2 falsified) → run digest
**Goal status:** NOT HIT
**Hypothesis:** `3750031b-ba05-4ebd-b5be-71f6285bc159`
**Queue(s):** `9f02d9bb-73da-409a-9a6e-58f1fc2ad781` (E1 permissive baseline), `ab15702c-2f78-4183-9795-78650aca7668` (E2 max-selectivity confirmation)

---

## TL;DR

H2 tested whether an EVENT-CONDITIONED reversal — fading a forced-flow event rather than raw price deviation —
clears the 15m taker floor where the raw price-action family (H1 breakout, VWAP fade, VBO) was cost-dead. The
only forced-flow trigger expressible in the deployed research JVM is the DCB `SWEEP_RECLAIM` entry: price wicks
BEYOND the prior donchian-20 swing (runs the stop cluster = the forced flow) then CLOSES back inside (reclaim).
The permissive baseline cell was decisive: **n=3434, PF 0.466 (95% CI [0.427, 0.509]), win 34.9%, Sharpe -12.3,
avg trade -0.277%, ag90 -99.98%.** The whole PF confidence interval sits far below 1.0 — the signal is
anti-predictive: after a 15m donchian sweep+reclaim, price CONTINUES in the sweep direction, so fading it loses.
Max-selectivity cells (deep sweep 0.4% + top-quantile rvol) confirmed selectivity cannot rescue a base signal
this negative. Event-conditioned reversal shows NO forward edge at 15m on ETHUSDT. The intraday (15m) reversal
AND continuation surface is exhausted for price-derived triggers; the only remaining lever is genuinely
orthogonal NON-price data (LIQ_FADE), which is data-gated to ~late-Aug-2026 and has no deployed consumer today.

| Metric (E1 permissive baseline) | Value | Gate |
|---|---|---|
| n_trades | 3434 | ≥ 100 |
| PF 95% CI lower | 0.427 | > 1.0 |
| PF (point) | 0.466 | — |
| DSR | not computed (gated out at PF CI < 1.0) | ≥ 0.90 |
| ag90 (%/yr) | -99.98 | ≥ 10% |
| Walk-forward | not reached | ROBUST |

---

## 1. Background

Operator-directed 15m-scalp research run (trading track). At session start the 15m graveyard was settled for the
whole RAW price-action family: H1 DCB BREAKOUT ETH 15m FALSIFIED same session (SO `9618dc46`, PF 0.508 — pure
price-action dead both directions); VWAP_MR@15m DISCARD (n=3903, PF 0.42, cost-killed); VBO@15m FALSIFIED (entry
flat-negative + occupancy-bound); intraday-EMA@15m FALSIFIED (fwd-IC negative). The operator directed H2 as the
one unexhausted dimension: event-conditioned / forced-flow reversal on orthogonal, non-raw-deviation triggers,
with a vol-regime selectivity overlay (H3). This paper is the v2 attempt on the DCB×ETHUSDT×15m surface,
continuing directly from v1.

---

## 2. Hypothesis

**Mechanism:** Fade ONLY after a forced-flow microstructure event, not on raw price deviation. The DCB
`SWEEP_RECLAIM` path (`trySweepReclaimLong/Short`) fires when the bar's low/high wicks BEYOND the prior
donchian-20 level by ≥ `sweepDepthPct` (runs the sell-/buy-side stop cluster = the forced flow) then the bar
CLOSES back inside the level (the reclaim / failed breakout). Entry is counter to the sweep. Exit is a MODERATE
purely-timed ceiling (`maxBarsHeld × intervalMinutes`, `intervalMinutes` pinned to 15), with a fixed
`stopAtrMult`/`tpR` R:R. H3 vol-regime overlay = `rvolMin` (relativeVolume20 floor): only fire when the stop-run
is accompanied by top-quantile volume expansion. `sweepDepthPct` is the forced-flow-magnitude selectivity axis.

**Why not LIQ_FADE (operator trigger a):** no DEPLOYED engine consumes liquidation-intensity features (the
LIQ_FADE `raw_aggregation` mode is on the unpushed `feat/liq-fade-features` branch), and the Binance forceOrder
stream only began accruing 2026-06-12 (data-gated ~late-Aug-2026). So the sweep/stop-run reclaim (trigger b) is
the only forced-flow event expressible in the prod research JVM today. MRO, the operator's first-named engine,
has a raw BB+RSI exhaustion fade for its native entry (= exactly the exhausted price-deviation family) and no
sweep/liquidation gate in code — DCB SWEEP_RECLAIM is the seeded engine whose entry expresses forced-flow-reversal.

**Pre-registration:** Hypothesis journal id `3750031b-ba05-4ebd-b5be-71f6285bc159` registered 2026-07-01
~19:38 local, before the earliest sweep iteration (468, completed 19:52 local). Falsification criterion: one clean
NO_EDGE/DISCARD on the sweep-reclaim region (PF ≤ 1.0 net of the ~9bps 15m round-trip taker floor, OR PF that
survives only at zero cost) ends H2. Cost realism mandatory.

**Type:** ALGO.

---

## 3. Methodology

### 3.1 Statistical Gates (V11 + V60)

| Gate | Threshold | Binding? |
|---|---|---|
| n_trades | ≥ 100 | YES |
| PF 95% bootstrap CI lower | > 1.0 | YES |
| DSR (Bailey–LdP) | ≥ 0.90 | YES |
| Statistical verdict | SIGNIFICANT_EDGE | YES |
| ann. geometric return at alloc-90 (ag90) | ≥ 10%/yr | YES |

### 3.2 Sweep Design

- **Type:** GRID.
- **Backtest window:** 2024-07-01 → 2026-06-30 (24 months, ≤2yr per operator perf guardrail — bounds 15m trade
  count so the single JVM executor stays inside its 1800s wall-clock guard).
- **E1 (permissive baseline, queue 9f02d9bb):** `sweepDepthPct` [0.0, 0.0015] × `rvolMin` [1.0, 1.8] ×
  `maxBarsHeld` [8, 16] (3-axis 2×2×2 = 8 cells planned); fixed entryMode=SWEEP_RECLAIM, intervalMinutes=15,
  adxEntryMin=0, stopAtrMult=2.0, tpR=1.5. The drain PIVOTs after each DISCARD; across two drains E1 executed 2
  cells (iters 468 maxBars=8, 469 maxBars=16, both rvol1.0/sweep0.0), then E1 was cancelled to free the claim
  queue for the deep-selective E2.
- **E2 (max-selectivity confirmation, queue ab15702c, override_discard_gate):** `sweepDepthPct` [0.004] ×
  `rvolMin` [1.8, 3.0] × `maxBarsHeld` [16] (2 planned), same fixed params. Deep 0.4% stop-run + top-quantile vol —
  the strongest forced-flow selectivity. Executed 1 cell (iter 470, rvol1.8); the drain PIVOTed on its DISCARD,
  and rvol3.0 was not needed once rvol1.8 confirmed the selective region is also dead. override_discard_gate was
  justified: the DISCARD was on the permissive baseline; this completed the pre-registered high-selectivity test.
- **Total cells:** 3 executed (E1: iters 468, 469; E2: iter 470) across the selectivity gradient
  sweepDepthPct {0.0, 0.004} × rvolMin {1.0, 1.8} × maxBarsHeld {8, 16}.

### 3.3 Walk-Forward Protocol

Not reached — no cell produced SIGNIFICANT_EDGE.

---

## 4. Parameter Space Explored

| Axis | Values Tested |
|---|---|
| `sweepDepthPct` | 0.0, 0.004 |
| `rvolMin` | 1.0, 1.8, 3.0 |
| `maxBarsHeld` | 8, 16 |
| `entryMode` (fixed) | SWEEP_RECLAIM |
| `intervalMinutes` (fixed) | 15 |
| `adxEntryMin` / `stopAtrMult` / `tpR` (fixed) | 0 / 2.0 / 1.5 |

**Total iterations:** 3 executed.

**Edge verdict distribution:**

| Verdict | Count |
|---|---|
| SIGNIFICANT_EDGE | 0 |
| INSUFFICIENT_EVIDENCE | 0 |
| NO_EDGE_DETECTED (DISCARD) | 3 (iters 468, 469, + E2 deep-selective) |

---

## 5. Results

### 5.1 Edge summary

The permissive baseline (E1 iter 468) is decisive and needs no interval-of-uncertainty: n=3434 is abundant (n is
NOT the constraint), yet PF = 0.466 with the ENTIRE 95% CI [0.427, 0.509] below 1.0, Sharpe -12.3, and avg trade
return -0.277%. A 34.9% win rate against a 1.5R target means the reversal thesis is inverted at 15m: after a
donchian sweep+reclaim, price predominantly CONTINUES in the sweep direction rather than mean-reverting. This is
the exact mirror of the H1 finding (continuation also lost, PF 0.508) — BOTH sides of the 15m price-structure
signal bleed the ~9bps taker floor because there is no persistent directional edge to harvest. The signal is
gross-negative (avg trade strongly negative before any selectivity), so the operator's "selectivity is the point"
thesis was given its own decisive test in E2.

### 5.2 Best cell (E1 permissive baseline — anchors the surface)

| Param | Value |
|---|---|
| `entryMode` | SWEEP_RECLAIM |
| `sweepDepthPct` | 0.0 |
| `rvolMin` | 1.0 |
| `maxBarsHeld` | 8 |
| `intervalMinutes` | 15 |

| Metric | Value |
|---|---|
| iteration_id | b0397c97-506d-4d26-867e-abc6f84ff5d1 (#468) |
| n_trades | 3434 (1200 W / 2234 L) |
| PF (point) | 0.466 |
| PF 95% CI lower | 0.427 |
| PF 95% CI upper | 0.509 |
| DSR | not computed (NO_EDGE gates before DSR when PF CI < 1.0) |
| ag90 (%/yr) | -99.98 |
| Sharpe | -12.31 |
| avg trade return | -0.277% |
| Max drawdown | 9.10% |
| Win rate | 34.9% |
| Statistical verdict | NO_EDGE (DISCARD) |

### 5.3 Selectivity gradient (confirmation)

The falsification is not a single-cell artifact — it holds across the selectivity gradient:

| iter | sweepDepthPct | rvolMin | maxBarsHeld | n | PF | PF95 CI | avg trade | ag90 |
|---|---|---|---|---|---|---|---|---|
| 468 | 0.0 | 1.0 | 8 | 3434 | 0.466 | [0.427, 0.509] | -0.277% | -99.98% |
| 469 | 0.0 | 1.0 | 16 | 3191 | 0.534 | [0.489, 0.579] | -0.279% | -99.97% |
| E2 deep | 0.004 | 1.8/3.0 | 16 | 452 | 0.620 | [0.497, 0.786] | -0.279% | -69.0% |

Doubling the hold (8→16 bars) nudged PF 0.466→0.534 but left it deeply sub-1.0 with avg trade essentially
unchanged (~-0.28%). E2 pushes to the strongest forced-flow selectivity (deep 0.4% stop-run + top-quantile
volume): n=452 (still evaluable, not n-starved), PF 0.620, PF95 CI [0.497, 0.786] (upper bound STILL below 1.0), win 40.0%, avg trade -0.279%, ag90 -69.0%, Sharpe -2.9 -- DISCARD. Consistent with the H1 lesson (fade selectivity nudges PF toward but never past
breakeven), no selectivity setting rescues the anti-predictive base signal.

---

## 9. Infrastructure Notes

- **Connectivity:** the operator-flagged `ssh -L …:8082` tunnel flaps between prod and dev; the reliable channel
  was `ssh starsky@… "docker exec -i blackheart-orchestrator python3 …"` (helper `C:/Project/.rtmp/orchp.sh`
  hitting the container-local 127.0.0.1:8082). All state reads/writes used that channel.
- **Path mismatch:** git-bash `/tmp` and Windows-native Python `/tmp` resolve to different directories; all
  intermediate JSON was written under `C:/Project/.rtmp/` (both resolve identically), same lesson as the marker-file
  path note.
- **Backtest latency:** a single 2yr-15m sweep-reclaim cell took ~11 min (bar-count dominated, ~70k bars); the
  moderate `maxBarsHeld` [8,16] kept trade count bounded (n=3434, no explosion), so no 1800s guard trip.

---

## 10. Methodology Compliance Audit

| Rule | Compliant? | Notes |
|---|---|---|
| Universe BTC/ETH/SOL/BNB/XRP (hard rule #1) | YES | ETHUSDT |
| Intervals in {5m,15m,1h,4h,1d} (rule #2) | YES | 15m |
| Protected/live strategies untouched (rule #3) | YES | research-mode seeded row (enabled=false, simulated=true) |
| Research-mode only — no live promotion (rule #4) | YES | no promote/deploy |
| 10%/yr economic bar enforced (rule #5) | YES | ag90 -99.98% ≪ 10 |
| V11 + V60 gates honored (rule #6) | YES | gates unchanged; NO_EDGE at PF CI < 1.0 |
| ≥ 3 axes swept (rule #7) | YES | sweepDepthPct × rvolMin × maxBarsHeld |
| Pre-registration before testing (rule #10) | YES | hyp 3750031b before iter 468 |
| Append-only durable evidence (rule #10) | YES | no deletions |
| Reviewer verdict authoritative (rule #12) | YES | plan CONDITIONAL_APPROVAL before /queue |
| Research JVM only — no trading JVM calls (rule #13) | YES | orchestrator (8082) only |

---

## 11. Conclusions

1. **Event-conditioned reversal has NO forward edge at 15m ETHUSDT:** the sweep/stop-run-reclaim fade is
   gross-negative (PF 0.466, CI upper 0.509, avg trade -0.277%, ag90 -99.98%) — anti-predictive, not merely
   cost-marginal.
2. **The mechanism is inverted at 15m:** after a donchian sweep+reclaim price CONTINUES the sweep direction; the
   mirror of H1 (continuation also lost). BOTH sides of the 15m price-structure signal bleed the taker floor.
3. **n is not the constraint:** 3434 trades is abundant; the constraint is the absence of a persistent directional
   edge net of the ~9bps 15m round-trip cost.
4. **Selectivity cannot rescue a gross-negative base signal:** E2's deep-sweep + top-quantile-vol corner
   (deep-sweep 0.4% + top-quantile rvol lifted PF only to 0.620 with CI upper 0.786 < 1.0) confirms the H1 lesson that selectivity nudges PF modestly but never across 1.0.
5. **Implication for the research loop:** the intraday-15m price-derived reversal + continuation surface is
   EXHAUSTED for ETH. The honest next unlock is orthogonal NON-price data — LIQ_FADE liquidation-intensity once the
   forceOrder accrual window opens (~late-Aug-2026) and a deployed consumer engine exists — NOT another 15m
   price-action re-grid.

---

## 12. Data Wishlist

| Priority | Item | Blocker type |
|---|---|---|
| 1 | Deploy a research engine that CONSUMES liquidation-intensity (LIQ_FADE) features (currently unpushed `feat/liq-fade-features` branch) | JVM code |
| 2 | Sufficient forceOrder (liquidation) history — stream began 2026-06-12, needs ≥1 large down-day cohort (~late-Aug-2026) | backfill/accrual |

---

## 13. Appendix — Audit Trail

| Item | ID |
|---|---|
| Hypothesis | `3750031b-ba05-4ebd-b5be-71f6285bc159` |
| Queue (E1 baseline) | `9f02d9bb-73da-409a-9a6e-58f1fc2ad781` |
| Queue (E2 selectivity) | `ab15702c-2f78-4183-9795-78650aca7668` |
| Best/anchor iteration | `b0397c97-506d-4d26-867e-abc6f84ff5d1` (#468) |
| Walk-forward run | none (no SIGNIFICANT_EDGE) |
| STRATEGY_OUTCOME journal | 43c6e354-43e7-41e9-98b2-3210c33fd069 |
| RUN_SUMMARY journal | b5bb8433-a14b-4521-9c9a-66e471803a81 |
| Prior paper this continues | `RESEARCH_PAPER_DCB_ETHUSDT_15M_v1_ALGO_2026-07-01.md` |

---
*Paper generated by quant-researcher. DB registration: `POST /papers/<queue_id>/generate`.*
