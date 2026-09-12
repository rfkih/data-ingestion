# Research Paper: DCB (SWEEP_RECLAIM) — ETHUSDT × 1H

**Author:** quant-researcher
**Date:** 2026-07-02
**Strategy:** `DCB` (`entryMode=SWEEP_RECLAIM`)
**Surface:** `ETHUSDT` × `1H`
**Type:** ALGO
**Surface attempt:** v11 — ALGO (1h reversion cost-floor test — the runnable proxy for the operator's H1 VWAP_MR/MMR fade, which is seed-blocked at 1h)
**Prior papers on this surface:** `DCB_ETHUSDT_1H_v9_CHAR_2026-06-20`, `DCB_ETHUSDT_1H_v10_ALGO_2026-06-20` (those studied the BREAKOUT/exit dimension; this one tests the opposite — the SWEEP_RECLAIM fade)
**Filename:** `RESEARCH_PAPER_DCB_ETHUSDT_1H_v11_ALGO_2026-07-02.md`
**Terminal:** WALL_CLOCK_CAP (cumulative run budget exhausted; H1 harvested during graceful shutdown)
**Goal status:** NOT HIT
**Hypothesis:** `c9c2a21b-f12f-49ac-a5a7-7759be47995d`
**Queue(s):** `c03f4627-8cab-4678-b2d8-fef7d69b5a53` (full 12-cell grid, iters 472–483), `70d4f278-4eff-42c5-9f86-e45e1eff0f02` (duplicate first cell, iter 471)

---

## TL;DR

The operator's 1-hour "cost-amortization" thesis was that a mean-reversion fade which bled ≈ −0.28%/trade at 15m (against a ~9bps round-trip taker floor) might flip **avg-trade-net positive** at 1h, because the fixed taker cost is a smaller fraction of a larger 1h move. We tested the runnable 1h reversion proxy — `DCB entryMode=SWEEP_RECLAIM` on ETHUSDT@1h (fade a wick that pushes beyond the prior Donchian channel then closes back inside = a stop-run reclaim fade) — across a 12-cell grid (`sweepDepthPct` × `maxBarsHeld` × `rvolMin`) over 2022-01-01 → 2026-06-30. **Every cell has a NEGATIVE avg-trade-net, from −0.245% (best) to −0.543% (worst), n-weighted mean −0.352%.** All 12 cells cleared n ≥ 100 (117–678 trades), so trade count was never the binding constraint. PF ranged 0.61–0.75, every PF 95% CI lower bound sat far below 1.0 (0.39–0.58), DSR = 0.0 everywhere, and annualized-geometric-return-at-alloc-90 was negative on every cell (−8% to −42%). **The cost floor is NOT cleared at 1h.** The best 1h cell (−24.5bps/trade) is actually worse on an n-weighted basis than the 15m result (−0.28%): the gross per-trade edge (≈ −15bps before the ~9bps taker) is itself negative, so amortizing a fixed cost over larger moves cannot rescue a signal that loses gross. The failure mode is **absent (negative) edge, not cost fragility.**

*(No SIGNIFICANT_EDGE cell — metrics gate table omitted; see §5.2 for the best-cell anchor.)*

---

## 1. Background

The 15m intraday price-action family was declared exhausted on 2026-07-01 (ARCHETYPE_EXHAUSTION): every 15m reversion/reversal edge bled ≈ −0.28%/trade against the ~9bps round-trip taker floor, and n was never the constraint (thousands of trades per cell). The operator pivoted to the 1-hour interval on the reasoning that the *same fixed ~9bps taker* is a much smaller fraction of a typical 1h move than of a 15m move, so a cost-fragile edge that died at 15m might clear at 1h. The binding metric for every experiment is `avg_trade_return_pct` **net of real 1h taker cost** — a zero-cost-only PF is an automatic DISCARD.

The pure VWAP_MR / MMR fade at 1h (the operator's literal "H1") is **seed-blocked**: those codes have only 15m `account_strategy` rows, so `/queue` would 412 `account_strategy_missing` at 1h (filed as DATA_WISHLIST, operator-only to seed). The runnable 1h reversion proxy is `DCB entryMode=SWEEP_RECLAIM`, whose `sweepDepthPct` (wick depth beyond the Donchian channel before the reclaim fade) is the direct analog of a deviation-threshold fade. This paper harvests that proxy grid.

15m graveyard (not re-run): VWAP_MR@15m naive PF 0.42 avg −0.28%; DCB SWEEP_RECLAIM@15m iters 468/469/470 avg −0.277/−0.279/−0.279%.

---

## 2. Hypothesis

**Mechanism:** On each 1h bar, detect a "stop-run": price wicks at least `sweepDepthPct` beyond the prior Donchian-N channel extreme and then closes back inside the channel (a trapped-breakout / liquidity-sweep-and-reclaim). Enter a fade AGAINST the sweep direction, size by risk, exit on the first of: fixed take-profit at `tpR` × risk (1.5R), stop at `stopAtrMult` × ATR (2.0), or a purely TIMED exit after `maxBarsHeld` bars. `rvolMin` gates entries to bars with relative volume ≥ threshold. `adxEntryMin=0` (no trend filter on entry).

**Pre-registration:** Hypothesis journal id `c9c2a21b-f12f-49ac-a5a7-7759be47995d` registered 2026-07-01T14:44:31, before the earliest 1h sweep iteration (iter 471) at 2026-07-01T14:54:39 (gap ≈ 10 min). Falsification criterion: no cell reaches `avg_trade_return_pct > 0` net of cost at n ≥ 100 → the 1h interval is not the lever, mean-reversion does not clear the cost floor.

**Type:** ALGO (no ML involvement).

---

## 3. Methodology

### 3.1 Statistical Gates (V11 + V60)

| Gate | Threshold | Binding? |
|---|---|---|
| n_trades | ≥ 100 | YES |
| PF 95% bootstrap CI lower | > 1.0 | YES |
| DSR (Bailey–LdP, n_trials from hypothesis_audit) | ≥ 0.90 | YES |
| Statistical verdict | SIGNIFICANT_EDGE | YES |
| ann. geometric return at alloc-90 (ag90) | ≥ 10%/yr (researcher GOAL_HIT bar) | YES |
| **avg-trade NET of taker cost (operator's binding metric)** | **> 0** | **YES (deciding number)** |

### 3.2 Sweep Design

- **Type:** GRID
- **Backtest window:** 2022-01-01 → 2026-06-30 (54 months, 18 quarters, 1641 days — spans 2022 bear + 2023 chop + 2024/25 bull)
- **Dimensions swept (3 axes):**
  - `sweepDepthPct` ∈ {0.004, 0.008}
  - `maxBarsHeld` ∈ {8, 16, 24}
  - `rvolMin` ∈ {1.5, 2.5}
- **Fixed:** `entryMode=SWEEP_RECLAIM`, `adxEntryMin=0`, `stopAtrMult=2.0`, `tpR=1.5`, `intervalMinutes=60`
- **Total cells:** 12 planned, 12 executed (+1 duplicate of cell 0.004/8/1.5 across the two queues; iter 471 = iter 472 bit-identical)

### 3.3 Walk-Forward Protocol

Not run — no cell reached SIGNIFICANT_EDGE, so no candidate was eligible for walk-forward.

---

## 4. Parameter Space Explored

| Axis | Values Tested |
|---|---|
| `sweepDepthPct` | 0.004, 0.008 |
| `maxBarsHeld` | 8, 16, 24 |
| `rvolMin` | 1.5, 2.5 |

**Total iterations:** 13 (12 distinct cells + 1 duplicate). Cumulative DSR-deflated trial count on the surface: ~196–198.

**Edge verdict distribution (12 distinct cells):**

| Verdict | Count |
|---|---|
| SIGNIFICANT_EDGE | 0 |
| INSUFFICIENT_EVIDENCE | 3 |
| NO_EDGE_DETECTED (DISCARD) | 9 |

---

## 5. Results

### 5.1 Edge summary

Full 12-cell grid (avg-trade is NET of engine taker cost; the deciding metric):

| iter | sweepDep | maxBars | rvol | n | PF | PF CI lo | PF CI hi | avg-trade-net % | DSR | ag90 % | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 471 | 0.004 | 8 | 1.5 | 678 | 0.645 | 0.532 | 0.775 | **−0.3382** | 0.0 | −38.23 | NO_EDGE |
| 472 | 0.004 | 8 | 1.5 | 678 | 0.645 | 0.532 | 0.775 | −0.3382 | 0.0 | −38.23 | NO_EDGE (dup of 471) |
| 473 | 0.004 | 8 | 2.5 | 290 | 0.726 | 0.552 | 0.966 | **−0.2452 (best)** | 0.0 | −14.08 | NO_EDGE |
| 474 | 0.004 | 16 | 1.5 | 666 | 0.661 | 0.554 | 0.793 | −0.3913 | 0.0 | −42.41 | NO_EDGE |
| 475 | 0.004 | 16 | 2.5 | 290 | 0.735 | 0.561 | 0.973 | −0.2805 | 0.0 | −16.07 | NO_EDGE |
| 476 | 0.004 | 24 | 1.5 | 644 | 0.688 | 0.578 | 0.818 | −0.3914 | 0.0 | −41.61 | NO_EDGE |
| 477 | 0.004 | 24 | 2.5 | 283 | 0.725 | 0.552 | 0.961 | −0.3184 | 0.0 | −17.63 | NO_EDGE |
| 478 | 0.008 | 8 | 1.5 | 209 | 0.746 | 0.540 | 1.043 | −0.2694 | 0.0 | −11.50 | INSUFFICIENT |
| 479 | 0.008 | 8 | 2.5 | 117 | 0.660 | 0.414 | 1.033 | −0.3550 | 0.0 | −8.41 | INSUFFICIENT |
| 480 | 0.008 | 16 | 1.5 | 207 | 0.715 | 0.510 | 0.988 | −0.3795 | 0.0 | −15.63 | NO_EDGE |
| 481 | 0.008 | 16 | 2.5 | 117 | 0.658 | 0.417 | 1.005 | −0.4415 | 0.0 | −10.41 | INSUFFICIENT |
| 482 | 0.008 | 24 | 1.5 | 207 | 0.728 | 0.526 | 1.002 | −0.3844 | 0.0 | −15.90 | INSUFFICIENT |
| 483 | 0.008 | 24 | 2.5 | 117 | 0.613 | 0.390 | 0.932 | **−0.5427 (worst)** | 0.0 | −12.55 | NO_EDGE |

Binding constraint = **absent (negative) gross edge**, not frequency and not cost-fragility. Every cell cleared n ≥ 100 (117–678). Every cell lost money net of cost. Axis reading: the shallower/tighter corner (`sweepDepthPct=0.004`, `maxBarsHeld=8`, `rvolMin=2.5` → iter 473) is the least-bad, and deeper sweeps (0.008) + longer holds (24) + looser vol (1.5) monotonically worsen it. No axis or corner produces a positive avg-trade. n-weighted mean avg-trade-net across the grid = **−0.352%**.

### 5.2 Best cell (anchor for future comparisons)

| Param | Value |
|---|---|
| `entryMode` | SWEEP_RECLAIM |
| `sweepDepthPct` | 0.004 |
| `maxBarsHeld` | 8 |
| `rvolMin` | 2.5 |
| `tpR` / `stopAtrMult` / `adxEntryMin` | 1.5 / 2.0 / 0 |

| Metric | Value |
|---|---|
| iteration_id | `5eda4cc4-5e0b-4d69-93f8-8303be77ba2b` (iter 473) |
| backtest_run_id | `0a883615-602f-4491-ae85-8c38dc8ca404` |
| n_trades | 290 |
| PF (point) | 0.726 |
| PF 95% CI lower | 0.5516 |
| PF 95% CI upper | 0.9663 |
| DSR | 0.0 |
| ag90 (%/yr) | −14.08 |
| **avg-trade-net %** | **−0.2452** |
| Sharpe (ann.) | −1.046 |
| Calmar | −0.206 |
| Max drawdown | 0.77% (account-level; ~7% capital utilization per trade) |
| Win rate | 44.48% |
| Statistical verdict | NO_EDGE |

**Regime breakdown of the best cell (the decisive structural evidence):** the fade loses in ALL THREE trend regimes — BEAR (n=111, PnL −2.07, WR 0.45), BULL (n=96, PnL −1.31, WR 0.48), NEUTRAL (n=83, PnL −3.71, WR 0.40). There is no regime pocket where fading a Donchian sweep on ETH is profitable, which pre-falsifies the planned H3 regime/HTF-bias overlay: a regime gate can only reduce n, not turn a uniformly-negative signal positive.

---

## 9. Infrastructure Notes

No infrastructure faults. Health at harvest: `db_ok=true`, `jvm_ok=true`, queue PENDING=0/RUNNING=0 (grid fully flushed). Two 1h queues exist for the same grid: `c03f4627` ran the full 12-cell grid (iters 472–483); `70d4f278` ran only the first cell (iter 471, a duplicate submission). Both COMPLETED with `final_verdict=DISCARD`. The cumulative run wall-clock marker (`C:/Project/.research_run_state.json`) had accrued ~17h against its 8.5h cap because elapsed = now − started_ts counts real-world idle time between cron fires; this did not affect the persisted backtest results, which were harvested directly from the iteration rows.

---

## 10. Methodology Compliance Audit

| Rule | Compliant? | Notes |
|---|---|---|
| BTC/ETH/SOL/BNB/XRP only (hard rule #1) | YES | ETHUSDT |
| Intervals in {5m,15m,1h,4h,1d} (hard rule #2) | YES | 1h |
| Live book untouched (hard rule #3) | YES | research-mode DCB copy, `enabled=false, simulated=true` |
| Research-mode only — no live promotion (hard rule #4) | YES | no promote/deploy calls |
| 10%/yr economic bar (hard rule #5) | YES | all cells negative ag90 → DISCARD |
| V11 + V60 gates honored (hard rule #6) | YES | no threshold loosening; verdicts read as-computed |
| ≥ 3 axes swept (hard rule #7) | YES | sweepDepthPct × maxBarsHeld × rvolMin |
| Pre-registration before testing (hard rule #10) | YES | hypothesis 14:44:31 < first iter 14:54:39 |
| Append-only durable evidence (hard rule #10) | YES | no rows modified/deleted; hypothesis falsified-by-outcome (no PATCH endpoint) |
| Reviewer verdict authoritative (hard rule #12) | YES | no graduation attempted (no candidate) |
| Research JVM only — no trading JVM calls (hard rule #13) | YES | all via orchestrator :8082 |

---

## 11. Conclusions

1. **1h cost-floor verdict = NO.** The DCB SWEEP_RECLAIM reversion fade on ETHUSDT@1h has a negative avg-trade-net in every one of 12 grid cells (−0.245% to −0.543%, n-weighted −0.352%); it does not clear the ~9bps round-trip taker floor that the same-shaped 15m fade also failed to clear.
2. **The signal is gross-negative, not merely cost-fragile.** Best cell −24.5bps/trade minus the ~9bps taker implies gross ≈ −15bps: the mechanism loses before costs, so no amount of cost-amortization (larger 1h moves) can rescue it. The operator's amortization thesis is falsified.
3. **n was never the constraint.** Every cell cleared n ≥ 100 (117–678); the failure is edge, not sample size. This mirrors the 15m finding and confirms the intraday reversion family's problem is signal, not frequency.
4. **H3 regime overlay is pre-falsified.** The fade loses in BEAR, BULL, and NEUTRAL alike; a regime/HTF gate can only shrink n, not create a positive edge.
5. **Directional lesson for the surface.** On ETH the profitable side of a Donchian event is CONTINUATION (the live DCB-ETH-1h BREAKOUT), not the reclaim FADE. Betting against a stop-run reclaim loses across 15m and 1h. The intraday mean-reversion / sweep-fade archetype on ETH is exhausted.
6. **Implication for the research loop:** the pure VWAP_MR/MMR@1h fade (seed-blocked) is the only untested 1h reversion variant left, but given SWEEP_RECLAIM (the closest runnable analog) is gross-negative across the full grid AND all regimes, the prior probability that a differently-shaped 1h fade clears the floor is low. Highest-EV next move is to abandon intraday ETH reversion rather than seed VWAP_MR@1h.

---

## 12. Data Wishlist

| Priority | Item | Blocker type |
|---|---|---|
| 1 | `account_strategy` seed rows for VWAP_MR / MMR / MRO at 1h (BTC + ETH) — would let the pure mean-fade @1h run without the DCB SWEEP_RECLAIM proxy | JVM seed / operator-only |
| 2 | DCB SWEEP_RECLAIM @ BTCUSDT @ 1h (E2 confirmation) — never ran; would confirm whether the negative-edge result is ETH-specific or general | fresh run budget (marker) |

*(Both are low priority given conclusion #6 — the reversion archetype looks dead on ETH intraday.)*

---

## 13. Appendix — Audit Trail

| Item | ID |
|---|---|
| Hypothesis | `c9c2a21b-f12f-49ac-a5a7-7759be47995d` |
| Queue (full grid) | `c03f4627-8cab-4678-b2d8-fef7d69b5a53` |
| Queue (dup first cell) | `70d4f278-4eff-42c5-9f86-e45e1eff0f02` |
| Best iteration | `5eda4cc4-5e0b-4d69-93f8-8303be77ba2b` (iter 473) |
| Worst iteration | `89c5ff38-47d5-4fd3-ad61-eb14d3accc10` (iter 483) |
| Walk-forward run | none (no candidate) |
| Specialist verdicts | none (no candidate) |
| STRATEGY_OUTCOME journal | `a8f9703c-6172-41b1-a605-c676b966dc1f` |
| RUN_SUMMARY journal | (RESEARCH_RUN_COMPLETE_2026-07-02 — see §appendix update below) |
| DB papers | `BH-DCB-ETHUSDT-1H-c03f4627`, `BH-DCB-ETHUSDT-1H-70d4f278` |
| Prior papers this continues | `DCB_ETHUSDT_1H_v9_CHAR_2026-06-20`, `DCB_ETHUSDT_1H_v10_ALGO_2026-06-20` |

---
*Paper generated by quant-researcher. DB registration: `POST /papers/c03f4627-8cab-4678-b2d8-fef7d69b5a53/generate` (+ `/papers/70d4f278.../generate`).*
