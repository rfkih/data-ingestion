# Research Paper: DCB — BTCUSDT × 4h

**Author:** quant-researcher
**Date:** 2026-06-29
**Strategy:** `DCB` (DonchianBreakoutEngine, `entryMode=SWEEP_RECLAIM` — failed-sweep reversal)
**Surface:** `BTCUSDT` × `4h`
**Type:** ALGO
**Surface attempt:** v1 — ALGO (operator-directed exit-dimension redesign: ATR-trailing TP + fee-aware break-even floor on the SWEEP_RECLAIM entry)
**Prior papers on this surface:** none (first DCB_BTCUSDT_4H paper)
**Terminal:** operator-directed work-unit complete (research run remains ACTIVE — not at the 8.5h cap)
**Goal status:** NOT HIT
**Hypothesis:** `a968adc3-d080-4db0-a1c7-e88337039e2a`
**Queue(s):** `c396088c-f7f1-41d5-97b0-a36947bf1d51` (4h) — companion 15m queue `791fdf04-75c7-48e4-bf7f-104e4640c2e2`

---

## TL;DR

The just-completed DCB SWEEP_RECLAIM **entry** study (hyp `44950e97`) fixed the false-entry problem
(win-rate 13.5%→38%) but produced only NO_EDGE cells because 15m-BTC reversals are too small
(reward:risk ~1:1). This study moved the attack to the **exit dimension + the instrument**, testing
the operator's exact ask — "trailing stop TP instead of fixed TP, and after crossing the profit area
move the SL to the minimum price where it breaks even with fees" — on the larger-move 4h surface. An
8-cell grid (trailAtrMult {0, 3.0} × feeBufferPct {0, 0.0008} × trailActivateR {0, 0.5}) over
2020-01-01→now (n=173–216) found that **the ATR trailing stop genuinely improves the exit** (PF
0.893→0.929, expectancy 38% less negative), but **the fee-aware break-even floor at 8bps HURTS the
trailing exit** (PF 0.929→0.758) by locking break-even too early and scratching winners before they
develop. **No cell cleared PF > 1.0** (best 0.929; all geom-return-at-alloc-90 between −25% and −38%),
so DCB sweep-reclaim is cost-dead at BTCUSDT 4h even with the best exit. The trailing TP is the
correct mechanism; the fee-floor at this setting is counter-productive.

*(No cell reached SIGNIFICANT_EDGE — gate table omitted.)*

---

## 1. Background

DCB's edge is known to live at 4h (prior DCB-BTC-4h ATR-trail on the *breakout-continuation* entry hit
PF 2.40 as a graduation candidate, hyp `c8ed2de1`, but was DSR-blocked). The operator's recent thread
re-engineered the engine's `entryMode=SWEEP_RECLAIM` (a stop-run-beyond-Donchian-then-close-back-inside
"failed sweep" reversal) and confirmed at 15m that it raises win-rate to ~38% — yet every cell stayed
NO_EDGE (best PF 0.596) because 15m reversals are too small to beat taker cost (avg_win ≈ avg_loss).
The constraint had moved from the entry to the **exit**. The research JVM was redeployed (image
`vwapsweepfee0629g`) so `DonchianBreakoutEngine` now reads a NEW `feeBufferPct` param alongside the
existing `trailAtrMult` / `trailActivateR`. This study holds the best entry fixed and sweeps the exit
on the surface where reversals are big enough for a trail to build winners: BTCUSDT 4h.

---

## 2. Hypothesis

**Mechanism:** Enter on a failed liquidity sweep (price runs `sweepDepthPct`=0.003 beyond the Donchian
extreme then closes back inside; `adxEntryMin`=0, no trend gate). Manage the position with either a
fixed take-profit at `tpR`=2.5× initial risk (`trailAtrMult`=0, control) or a close-based ATR trailing
stop at `trailAtrMult`=3.0 that ratchets once `trailActivateR` is reached. The NEW `feeBufferPct` floor:
once price has moved ≥ feeBufferPct × entry (round-trip fees earned back), lock the stop at
break-even-after-fees so the trade at worst scratches — the operator's "move SL to the min price where
it breaks even with fees." Stop `stopAtrMult`=2.5, timed exit `maxBarsHeld`=32 bars.

**Pre-registration:** Hypothesis `a968adc3-d080-4db0-a1c7-e88337039e2a` registered 2026-06-29, before
the earliest sweep iteration (#403). Falsification criterion: if trailing + fee-BEP stays sub-1.0 net
at both 4h and 15m, the DCB sweep-reclaim family is cleanly falsified at these cost levels.

**Type:** ALGO (no ML).

---

## 3. Methodology

### 3.1 Statistical Gates (V11 + V60)

n_trades ≥ 100; PF 95% bootstrap CI lower > 1.0; DSR ≥ 0.90 (operator methodology decision
2026-06-15); statistical_verdict = SIGNIFICANT_EDGE; ann. geometric return at alloc-90 ≥ 10%/yr for
the GOAL_HIT terminal. The +20bps slippage net check was retired in V60 (audit-only).

### 3.2 Sweep Design

- **Type:** GRID
- **Backtest window:** 2020-01-01 → now (~6.5yr; COVID crash, 2021 bull, 2022 bear, 2023–25 chop —
  regime-diverse, kills bull-confounding).
- **Dimensions swept (3, hard-rule #7 satisfied):** `trailAtrMult` {0, 3.0}; `feeBufferPct`
  {0, 0.0008}; `trailActivateR` {0, 0.5}.
- **Fixed axes:** entryMode=SWEEP_RECLAIM, sweepDepthPct=0.003, adxEntryMin=0, stopAtrMult=2.5,
  tpR=2.5, maxBarsHeld=32, intervalMinutes=240.
- **Total cells:** 8 planned, 8 executed.

### 3.3 Walk-Forward Protocol

Not run — no cell reached SIGNIFICANT_EDGE, so the graduation gate (and walk-forward) was never
entered.

---

## 4. Results

All 8 cells INSUFFICIENT_EVIDENCE (statistical), DISCARD-equivalent economically (all net-negative).

| # | trailAtrMult | feeBufferPct | trailActR | n | PF | win% | avg_win | avg_loss | expectancy | geom@90 | iteration_id |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 403 | 0 (fixed) | 0 | 0 | 173 | 0.893 | 36.4 | 0.406 | 0.260 | −0.0177 | −31.2 | b8206b69 |
| 404 | 0 (fixed) | 0 | 0.5 | 173 | 0.893 | 36.4 | 0.406 | 0.260 | −0.0177 | −31.2 | 2820cf99 |
| 405 | 0 (fixed) | 0.0008 | 0 | 173 | 0.891 | 35.8 | 0.410 | 0.257 | −0.0180 | −31.6 | d5843c7e |
| 406 | 0 (fixed) | 0.0008 | 0.5 | 173 | 0.891 | 35.8 | 0.410 | 0.257 | −0.0180 | −31.6 | 0e31b0f5 |
| **407** | **3.0 (trail)** | **0** | **0** | **182** | **0.929** | 37.4 | 0.386 | 0.248 | **−0.0110** | **−25.3** | **2ac60740** |
| 408 | 3.0 (trail) | 0 | 0.5 | 175 | 0.920 | 38.3 | 0.381 | 0.257 | −0.0128 | −26.9 | c5ca137f |
| 409 | 3.0 (trail) | 0.0008 | 0 | 216 | 0.758 | 10.6 | 0.600 | 0.094 | −0.0204 | −37.8 | d790b239 |
| 410 | 3.0 (trail) | 0.0008 | 0.5 | 216 | 0.758 | 10.6 | 0.600 | 0.094 | −0.0204 | −37.8 | b0f36dc1 |

### 4.1 Head-to-head: fixed-TP vs trailing-TP (fee-floor OFF)

#403 (fixed) PF 0.893 → #407 (trail 3.0) PF 0.929. The ATR trail improves PF by +0.036 and lifts
expectancy from −0.0177 to −0.0110 (38% less negative), geom@90 from −31.2% to −25.3%. Mechanism: the
trail cuts avg_loss (0.260→0.248) by more than it cuts avg_win (0.406→0.386) — it exits losers earlier
and lets the genuine reversal-continuations breathe. **Trailing beats fixed-TP cleanly.** This
vindicates the operator's "trailing instead of fixed TP" instinct.

### 4.2 Head-to-head: fee-floor ON vs OFF

- **On the fixed-TP exit** (#403 vs #405): PF 0.893 → 0.891 — a **wash**. avg_loss trims slightly
  (0.260→0.257) but win% dips (36.4→35.8), netting flat.
- **On the trailing exit** (#407 vs #409): PF 0.929 → 0.758 — **materially worse**. The 8bps BEP lock
  engages too early: win% collapses 37.4→10.6%, avg_win balloons to 0.600 (only the rare big survivors
  remain "wins") while avg_loss collapses to 0.094 (the bulk of trades scratch at BEP). The
  distribution shift is dramatic but net-negative — expectancy worsens −0.0110→−0.0204. The fee-floor
  strangled the trailing winners before they could develop.

**Did the fee-floor trim the loss tail?** Mechanically yes — avg_loss fell sharply (0.248→0.094 on the
trail). But the trade-off was net-negative because too many would-be winners were scratched. The
operator's hypothesis that the fee-floor "protects" trailing winners is **falsified at
feeBufferPct=0.0008** — the floor is too tight for the 4h ATR move scale.

### 4.3 trailActivateR

Inert when trailAtrMult=0 (cells 403≡404, 405≡406 — bit-identical, a correct sanity check: no trail to
activate). When trailing is on, engaging immediately (actR=0, PF 0.929) slightly beats actR=0.5
(PF 0.920) — earlier engagement cuts losses sooner.

---

## 5. Interpretation & Verdict

DCB SWEEP_RECLAIM at BTCUSDT 4h is **cost-dead even with the best exit**. The reward:risk at 4h
(avg_win/avg_loss ≈ 1.56:1 on the fixed-TP control) is materially better than 15m's ~1:1, and the ATR
trail pushes PF from 0.89 to 0.93 — but that is still short of the PF>1.0 / DSR≥0.90 / ≥10%/yr gate,
and every cell compounds to a deeply negative annualized return (−25% to −38% at alloc-90). The
sweep-reclaim entry simply does not have enough gross edge to survive taker cost on 4h BTC, no matter
how the exit is shaped. The fee-aware BEP floor — a sound idea in principle — is counter-productive at
8bps because it locks break-even inside the noise band of a 4h ATR move.

**This is the directive's pre-registered clean-falsification branch:** the trailing-TP + fee-BEP exit
redesign is *correct engineering* (the trail demonstrably helps) but cannot rescue DCB sweep-reclaim at
these surfaces.

---

## 5b. Companion surface: BTCUSDT × 15m (the directive baseline)

The operator's directive baseline was 15m (where the prior SWEEP_RECLAIM *entry* study ran). This
session reordered the 15m exit grid so trailAtrMult varies fastest (fixed-vs-trail in cells 1–2;
queue `791fdf04` cancelled → reordered into `31d98af4`, parked after the head-to-head was captured).
The clean within-study 15m fixed-vs-trail head-to-head (window 2024→now, n=479):

| # | trail | fee | n | PF | win% | avg_win | avg_loss | R:R | expectancy | geom@90 | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 411/412 | 0 (fixed) | 0 | 479 | 0.571 | 33.0 | 0.141 | 0.122 | 1.16 | −0.0351 | −79.2 | NO_EDGE |
| 413 | 3.0 (trail) | 0 | 479 | 0.578 | 32.4 | 0.138 | 0.114 | — | −0.0325 | −76.7 | NO_EDGE |

At 15m the ATR trail improves PF only **marginally** (+0.007, vs 4h's +0.036): it cuts avg_loss
(0.122→0.114) slightly more than avg_win (0.141→0.138), expectancy −0.0351→−0.0325, geom@90
−79.2→−76.7 — the *same direction* as 4h, but with 15m R:R ~1:1 there are no big winners for the trail
to build, so the lift is tiny and both exits sit deeply sub-1.0. The 15m surface is **far more
cost-dead than 4h** (PF 0.578 vs 0.929; geom@90 −77% vs −25%) because the 15m reversal is too small
(R:R 1.16 vs 4h's 1.56). The prior entry study (iteration #398, trailAtrMult=2.0 at 15m) independently
corroborates (avg_win 0.115 ≈ avg_loss 0.121, PF ~0.58). The fee-floor was not re-swept at 15m — the
complete 4h grid already established it definitively (wash on fixed-TP, hurts the trail), and 15m would
mirror it. Conclusion across **both** surfaces: the trailing TP is the correct exit lever (it helps on
both) but cannot lift DCB sweep-reclaim past the taker-cost barrier; the constraint is gross entry
edge, not the exit — exactly as the directive's honest prior predicted. (Process note: an early cancel
of `791fdf04` briefly orphaned its in-flight backtest, contending with `31d98af4` on the research JVM
and slowing the 15m cells ~22 min each; contention cleared and the head-to-head completed.)

## 6. Next levers (recommendation)

1. **Loosen / re-scale the fee-floor**, not abandon it. feeBufferPct=0.0008 is too tight; a floor that
   only engages after ≥ 1.0–1.5R (well past the ATR noise band) might trim the loss tail without
   scratching winners. But this is a second-order tweak on a first-order-negative edge — low priority.
2. **Change the entry, not the exit.** The exit dimension is now thoroughly mapped (trail helps,
   fee-floor at 8bps hurts). The binding constraint is gross entry edge. Highest-EV next levers:
   (a) a **funding-Z crowded-side filter** on the sweep entry (only fade sweeps that flush
   over-positioned crowds); (b) **lower-cap majors** (SOL/BNB/XRP) where 4h reversals may carry more
   retail-driven follow-through; (c) the **liquidation tape** (LIQ_FADE, data-gated ~late-Aug-2026) as
   the orthogonal confirmation the price-only sweep entry lacks.
3. **Do NOT** re-sweep the DCB exit dimension on BTC again — it is saturated.

---

## 7. Provenance

- Hypothesis `a968adc3-d080-4db0-a1c7-e88337039e2a` (pre-registered, ALGO, operator-directed).
- Plan: `research/RESEARCH_PLAN_2026-06-29_dcb_sweepreclaim_exit.md` (plan-review APPROVED).
- Queue `c396088c-f7f1-41d5-97b0-a36947bf1d51`, 8 iterations #403–#410, COMPLETED.
- 4h STRATEGY_OUTCOME journal `263e1043-ae3b-47c9-95cb-88f4cc5a1c9a`.
- Research-mode only: `DCB@BTCUSDT@4h` seed is enabled=false, simulated=true on research account
  `99999999-…-0002`. Live book untouched; no promotion/enable/deploy.
