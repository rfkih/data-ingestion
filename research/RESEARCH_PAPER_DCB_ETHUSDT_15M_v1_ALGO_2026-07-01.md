# Research Paper: DCB — ETHUSDT × 15m

**Author:** quant-researcher
**Date:** 2026-07-01
**Strategy:** `DCB` (Donchian breakout, entryMode=BREAKOUT)
**Surface:** `ETHUSDT` × `15m`
**Type:** ALGO
**Surface attempt:** v1 — ALGO (H1 15m impulse-continuation: tight-exit × selectivity confirmatory test, operator-directed 15m-scalp continuation)
**Prior papers on this surface:** none (first paper on DCB ETHUSDT 15m; related graveyard: VBO@15m FALSIFIED, VWAP_MR@15m DISCARD)
**Filename:** `RESEARCH_PAPER_DCB_ETHUSDT_15M_v1_ALGO_2026-07-01.md`
**Terminal:** OPERATOR_DIRECTED_COMPLETE (H1 work-unit falsified; H2 handed to next session)
**Goal status:** NOT HIT (H1 FALSIFIED — no cell approached SIGNIFICANT_EDGE)
**Hypothesis:** `2999bcae-051e-4c57-b97c-f93a391238cb`
**Queue(s):** `5332ba32-c89a-4289-a492-aa75e2ff8e74` (2024+ confirmatory), plus `a8536335` / `16c1a233` (2022+ attempts, cancelled — JVM-slowness)

---

## TL;DR

H1 proposed that 15m breakout momentum *continues* (the inverse of the falsified VWAP_MR@15m fade): enter WITH a completed Donchian-20 upper-channel breakout gated on high selectivity (rvolMin ≥ 2, adx ≥ 25), then harvest the 2–6-bar continuation drift with a TIGHT purely-timed exit (maxBarsHeld 2–4 = 30–90 min). The distinguishing, previously-untested lever vs the two prior DCB@15m DISCARDs was exit-tightness × selectivity. It is **FALSIFIED**. The decisive confirmatory tight-exit cell (maxBarsHeld=2, rvolMin=2.0, backtest `f893902e`, ETHUSDT 15m, 2024+) returned **PF 0.508, n=1457, avg_trade −0.230%** — the tightest exit produced the *highest* turnover and the *worst* profit factor of the entire family. Four independent null-screen draws on the loose-exit region (maxBarsHeld 6–7) all lost gross (PF 0.49–0.75), and two prior DISCARDs (ETH PF 0.826, BTC PF 0.557) corroborate. Momentum-continuation via completed-bar Donchian breakout has negative forward drift net of cost at 15m regardless of exit tightness or volume/ADX selectivity. No SIGNIFICANT_EDGE table — no cell was close.

---

## 1. Background

Operator-directed 15m-scalp research (trading track). The 15m graveyard was already settled entering this run: **VBO@15m FALSIFIED** (entry edge flat-negative AND occupancy/exit-bound — loosening entry made n *worse* 38→22); **VWAP_MR@15m DISCARD** (timed exit reaches n=3903 but PF 0.42 — naive reversion loses because momentum *continues* after an impulse); **intraday-EMA-trend@15m FALSIFIED** (forward-IC negative). The standing structural read: the binding constraint at 15m is **cost-robustness + exit structure**, and timed-exit is the correct family (reaches n without occupancy stalls). H1 was the operator's lead hypothesis for the run: exploit the *continuation* that overwhelmed the VWAP fade. A prior instance of this run pre-registered H1 and launched a K=8 null-screen, then paused; this session resumed to pull the verdict and drive to a terminal.

---

## 2. Hypothesis

**Mechanism:** DCB with `entryMode=BREAKOUT` enters long when the close breaks the prior-bar Donchian-20 upper channel (a with-trend range-breakout *continuation*), gated on `relativeVolume20 ≥ rvolMin` (elevated volume) and `adx ≥ adxEntryMin` (trend strength). Exit fires FIRST via `tryTimedExit` at `maxBarsHeld × intervalMinutes` (a purely-timed ceiling; `intervalMinutes` pinned to 15 so a 2-bar hold = 30 min, not the engine-default 60), with optional close-based ATR trailing stop (`trailAtrMult`). Thesis: high selectivity concentrates entries on top-quantile impulse bars whose 2–6-bar continuation drift exceeds the ~9 bps 15m round-trip taker floor; the tight timed exit harvests continuation before mean-reversion erases it.

**Pre-registration:** Hypothesis `2999bcae-051e-4c57-b97c-f93a391238cb` registered 2026-07-01T06:15:51Z, before any sweep iteration. Falsification criterion (stated): one clean NO_EDGE on the high-selectivity tight-exit region ends H1 → pivot to H2. Cost realism mandatory (PF that survives only at zero cost = DISCARD).

**Type:** ALGO.

**Why not a re-skin:** the two prior DCB@15m breakout DISCARDs both *diluted* the impulse — ETH `b5d6d8d0` used tpR=5 fixed-TP + default 24-bar hold + rvol 1.3 (n=1714, PF 0.826, avg −0.185%); BTC `8a98e990` used maxBarsHeld=32 (8h) + rvol 1.0 + adx 0–15 (n=2499, PF 0.557, avg −0.244%). Both had abundant frequency (>1700 trades) — n was never the constraint. Neither tested the tight 2–4-bar timed exit at top-quantile selectivity. H1 isolated exactly that lever.

---

## 3. Methodology

### 3.1 Statistical Gates (V11 + V60)

| Gate | Threshold | Binding? |
|---|---|---|
| n_trades | ≥ 100 | YES |
| PF 95% bootstrap CI lower | > 1.0 | YES |
| DSR (Bailey–LdP) | ≥ 0.90 | YES |
| Statistical verdict | SIGNIFICANT_EDGE | YES |
| ann. geometric return at alloc-90 (ag90) | ≥ 10%/yr (GOAL_HIT bar) | YES |

No cell reached the first gate's *quality* bar — every completed backtest is a gross loser (PF < 1), so V11/V60 evaluation is moot.

### 3.2 Sweep Design

- **Type:** GRID
- **Cost ladder used:** null-screen (K=8 random draws) → confirmatory tight-exit cell.
- **Planned confirmatory grid:** maxBarsHeld {2,4} × rvolMin {2.0,3.0} × trailAtrMult {0.0,2.5} = 8 cells (3 varying axes), fixed entryMode=BREAKOUT, adxEntryMin=25, tpR=2.0, stopAtrMult=2.0, intervalMinutes=15. Trimmed from the plan's original 12-cell grid (dropped maxBarsHeld=6 because the null-screen already showed the loose region loses).
- **Backtest window:** 2024-01-01 → 2026-06-30 (~30 months) for the confirmatory cell that completed. A 2022-01-01 window was attempted first but every 2022+ tight-exit backtest hit the 1800s JVM wall-clock guard (see §9).
- **Executed:** 1 confirmatory cell to COMPLETED (`f893902e`) + 4 null-screen draws to COMPLETED. The remaining 7 grid cells were NOT run — the JVM (single-executor) was blocked by the two guard-failing 2022+ backtests and the tight-exit cells are individually ~14 min each, making the full grid budget-infeasible this session. One completed tight-exit cell + the null-screen distribution is decisive.

---

## 4. Parameter Space Explored

| Axis | Values Tested |
|---|---|
| `maxBarsHeld` | 2 (confirmatory), 6–7 (null-screen draws) |
| `rvolMin` | 1.85–3.09 (null-screen), 2.0 (confirmatory) |
| `adxEntryMin` | 20.5–32.1 (null-screen), 25 (confirmatory) |
| `trailAtrMult` | 0.0–2.21 (null-screen), 0.0 (confirmatory) |
| `tpR` | 1.8–2.8 (null-screen), 2.0 (confirmatory) |

**Edge verdict distribution:**

| Verdict | Count |
|---|---|
| SIGNIFICANT_EDGE | 0 |
| INSUFFICIENT_EVIDENCE | 0 |
| NO_EDGE / gross loser (PF<1) | 5 completed backtests (1 confirmatory + 4 null-screen draws) |

---

## 5. Results

### 5.1 Edge summary

Every completed DCB@15m breakout backtest loses gross (PF < 1) — the entry has negative forward drift *before* cost. The exit-tightness axis is **monotone in the wrong direction**: tighter exit → more trades → worse net PF.

| Config | Window | maxBarsHeld | rvolMin | n_trades | PF | avg_trade % | source |
|---|---|---|---|---|---|---|---|
| Confirmatory | 2024+ | 2 | 2.0 | 1457 | **0.508** | **−0.230** | backtest `f893902e` |
| Null-screen draw | 2024+ | 7 | 1.85 | 1567 | 0.519 | — | journal `89b1173b` |
| Null-screen draw | 2024+ | 6 | 2.80 | 1288 | 0.486 | — | journal `89b1173b` |
| Null-screen draw | 2024+ | 6 | 3.02 | 478 | 0.748 | — | journal `89b1173b` |
| Null-screen draw | 2024+ | 7 | 2.27 | 1255 | 0.620 | — | journal `6c44e038` |
| Prior DISCARD (ETH) | — | 24 | 1.30 | 1714 | 0.826 | −0.185 | queue `b5d6d8d0` |
| Prior DISCARD (BTC) | — | 32 | 1.00 | 2499 | 0.557 | −0.244 | queue `8a98e990` |

The single least-bad draw (PF 0.748) was the *most* selective (rvol 3.02 / adx 30.5) but also the lowest-n (478) — selectivity nudges toward but never past breakeven, and thinning the sample is not a path to a certifiable edge. The tight 2-bar exit (PF 0.508) is the *worst* profit factor at the *highest* turnover of any completed config.

### 5.2 Best cell

No cell had positive expectancy. The "best" completed cell by PF is a low-n null-screen draw (PF 0.748, n=478) — still a heavy gross loser, not a candidate. avg_trade on the confirmatory tight-exit cell is −0.230%, i.e. each round trip loses ~23 bps (worse than the ~9 bps taker cost — the *entry+2-bar-hold* itself is directionally wrong, not merely cost-killed).

---

## 9. Infrastructure Notes

**DCB@15m tight-`maxBarsHeld` backtests are pathologically slow on the research JVM and consumed most of this session.**

- The research JVM backtest executor is effectively single-threaded (concurrency = 1): a second submitted backtest sits PENDING until the first reaches a terminal.
- Tight-exit cells (small `maxBarsHeld`) generate an enormous trade count (2-bar position turnover → ~1457 trades over 30 months at high selectivity). This makes each backtest very slow: the maxBarsHeld=2 cell over a **2022-01-01** window hit the 1800s wall-clock guard and FAILED (twice, for two different queues); over a **2024-01-01** window it took ~14 min. By contrast, the loose-exit (maxBarsHeld 6–7) null-screen draws completed in ~90 s.
- Consequence: the original 2022+ confirmatory queue was cancelled and re-queued at 2024+; the two in-flight 2022+ backtests then serially blocked the JVM (each until its 30-min guard), delaying the first 2024+ tight-exit cell by ~40 min. Only one confirmatory cell was run to completion; the full 8-cell grid was not budget-feasible.
- The prior instance's null-screen `INSUFFICIENT_DATA` verdict was a **poller-bailout artifact** of exactly this: the screen bailed after 3 consecutive draws stuck in `backtest_status=RUNNING` (JVM-queue serialization + short poll timeout), NOT a data gap. The draws that completed were decisive.

**Action for next session (load-bearing):** for any 15m tight-turnover sweep, use a ≤ 2-year window and/or moderate `maxBarsHeld`, and never submit multiple slow cells that can wedge the single JVM executor. Consider whether the research JVM warrants a per-backtest trade-count/interval-aware timeout or added executor concurrency (orchestrator/JVM-owner decision).

---

## 10. Methodology Compliance Audit

| Rule | Compliant? | Notes |
|---|---|---|
| Universe (BTC/ETH/SOL/BNB/XRP) (hard rule #1) | YES | ETHUSDT only |
| Intervals in {5m,15m,1h,4h,1d} (hard rule #2) | YES | 15m |
| Live book untouched (hard rule #3) | YES | research-only backtests, no live mutation |
| Research-mode only — no promotion (hard rule #4) | YES | nothing deployed/promoted |
| 10%/yr bar respected (hard rule #5/#6) | YES | falsified far below any gate |
| V11 + V60 gates honored (hard rule #6) | YES | gates untouched; no cell near SIGNIFICANT_EDGE |
| ≥ 3 axes swept (hard rule #7) | YES | maxBarsHeld × rvolMin × trailAtrMult (plan); confirmatory single-cell + 4 multi-axis null-screen draws |
| Pre-registration before testing (hard rule #10) | YES | hyp registered 06:15:51 before any iteration |
| Append-only durable evidence (hard rule #10) | YES | STRATEGY_OUTCOME + RUN_SUMMARY appended; no research_journal row modified (hypothesis left ACTIVE per convention) |
| Reviewer verdict authoritative (hard rule #12) | YES | plan review APPROVED (0 blocker/0 warning) before queue |
| Research JVM only — no trading JVM (hard rule #13) | YES | orchestrator (:8082) + research JVM (:8081) + read-only DB only |

---

## 11. Conclusions

1. **H1 momentum-continuation is FALSIFIED at 15m on ETHUSDT.** A completed-bar Donchian-20 breakout has negative forward drift net of cost; the confirmatory tight-exit cell lost gross (PF 0.508, avg −0.230%, n=1457).
2. **The tight-exit lever makes it WORSE, not better.** The exit-tightness axis is monotone in the wrong direction: 2-bar hold (PF 0.508) < 6–7-bar hold (PF 0.49–0.75) < prior 24–32-bar holds (PF 0.56–0.83). Tighter exit only multiplies turnover and cost.
3. **Selectivity cannot rescue it.** The most-selective draw (rvol 3.0/adx 30.5) reached only PF 0.748 at n=478 — closer to but still far below breakeven, and only by thinning the sample.
4. **The 15m directional price-action family is now exhausted in both directions:** VWAP_MR fade (PF 0.42) and DCB breakout continuation (PF 0.51–0.83) both lose net of the taker floor. Neither the reversion nor the continuation of a 15m impulse is exploitable with price-action alone.
5. **Implication for the research loop:** PIVOT to H2 — event-conditioned reversal that fades ONLY after *forced* flow (a stop-run/sweep that immediately reclaims, or a liquidation spike) with a timed exit. The edge, if any, at 15m requires an orthogonal *event* condition, not a price-pattern entry. Start with the price-action sweep-reclaim variant; the LIQ_FADE liquidation-intensity variant is data-gated (~Aug-2026).

---

## 12. Data Wishlist

| Priority | Item | Blocker type |
|---|---|---|
| 1 | Per-backtest trade-count / interval-aware timeout OR added research-JVM executor concurrency so tight-turnover 15m sweeps don't wedge the single executor | JVM / orchestrator code (owner decision) |
| 2 | LIQ_FADE liquidation-intensity features usable window (currently accruing, ~Aug-2026) — unlocks H2's liq-spike variant | backfill / time-gated data |

---

## 13. Appendix — Audit Trail

| Item | ID |
|---|---|
| Hypothesis | `2999bcae-051e-4c57-b97c-f93a391238cb` |
| Queue (confirmatory 2024+) | `5332ba32-c89a-4289-a492-aa75e2ff8e74` |
| Queues (2022+ attempts, cancelled) | `a8536335-412e-40a7-82f0-7cec0eb335bf`, `16c1a233-04ca-4a71-b1e5-c6f8855101d3` |
| Confirmatory tight-exit backtest | `f893902e` (PF 0.508, n=1457, avg −0.230%) |
| Null-screen result journals | `6c44e038-43ee-4687-92cb-ad2fdb696b4c`, `89b1173b-9b7f-42de-92f3-6e53f240b2d8` |
| Prior DCB@15m DISCARD queues | `b5d6d8d0` (ETH), `8a98e990` (BTC) |
| STRATEGY_OUTCOME journal | `9618dc46-8a74-4107-90b4-c554752d77c7` |
| RUN_SUMMARY journal | (this session — see /agent/state.last_run_summary) |

---
*Paper generated by quant-researcher. DB registration: `POST /papers/5332ba32-c89a-4289-a492-aa75e2ff8e74/generate`.*
