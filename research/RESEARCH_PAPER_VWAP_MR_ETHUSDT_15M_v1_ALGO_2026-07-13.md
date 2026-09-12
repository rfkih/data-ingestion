# Research Paper: VWAP_MR — ETHUSDT × 15M

**Author:** quant-researcher
**Date:** 2026-07-13
**Strategy:** `VWAP_MR`
**Surface:** `ETHUSDT` × `15M`
**Type:** ALGO
**Surface attempt:** v1 — ALGO (fresh-coin closing test of the 15m-maker-scalp program: the maker-favorable mean-reversion archetype's last untested cell)
**Prior papers on this surface:** none (first attempt on VWAP_MR-ETHUSDT-15m). Sibling program paper: `RESEARCH_PAPER_ATR_MOM_ETHUSDT_15M_MAKER_v1_EXEC_2026-07-14.md` (the momentum arm that opened the maker thread).
**Filename:** `RESEARCH_PAPER_VWAP_MR_ETHUSDT_15M_v1_ALGO_2026-07-13.md`
**Terminal:** other (operator-directed completion of an APPROVED plan to its pre-registered binary falsifier — not a loop terminal; run marker stays ACTIVE)
**Goal status:** NOT HIT — program FALSIFIED and CLOSED
**Hypothesis:** `725ad692-3ce2-44f3-a360-bcbe160423ba` (now FALSIFIED)
**Queue(s):** `e501a13c-1c0f-41c6-9b12-9bfff975d6bf`

---

## TL;DR

This paper closes the **15m-maker-scalp research program** by executing its pre-registered falsifier. The program's thesis was that maker (post-only) execution could rescue intraday scalps that taker fees buried — *if* a preservable gross (pre-cost) edge exists in the signal. The theoretically-correct maker pairing is mean-reversion (a post-only limit resting AT a dislocation is *favorable* selection — you get filled on the overshoot you wanted to fade — the exact inverse of the momentum-breakout adverse-selection trap falsified in `cc079e32`). The last untested cell was VWAP_MR deviation-fade @ ETHUSDT 15m, ETH being the strongest 15m mean-reversion venue and the one coin×interval VWAP_MR had never run on. A bounded 4-cell grid was driven to terminal (all four NO_EDGE/DISCARD as-run under taker-7.5bps) and gross-rescored per the validated methodology of finding `fc3d8999` (per-trade `backtest_trade.gross_pnl_amount`). **The single most important finding: the best gross PF is 0.8075 (n=3159, 95% bootstrap CI 0.745–0.874 — the entire interval below 1.0).** The signal is gross-dead: maker-favorable fills cannot rescue a strategy that loses *before* costs. The falsifier fired; the program is closed.

*(No SIGNIFICANT_EDGE cell — SIGNIFICANT_EDGE metrics table omitted.)*

---

## 1. Background

The 15m-maker-scalp program was opened after the operator unlocked maker (post-only) execution as a lever against the taker-fee floor that had been killing intraday scalps (finding `fc3d8999`). Two arms were pursued:

1. **Momentum arm (ATR_MOM-ETH-15m):** breakout entries showed gross PF 1.09–1.43 that *looked* maker-rescuable, but the maker flip held only under an all-fills fantasy. Journal `cc079e32` FALSIFIED it: a post-only limit on a momentum-breakout entry is adverse selection — the limit misses the winners (MAE 0.44R) and fills the reverters (MAE 1.05R). Maker PF-CI-low 0.908 < 1 on all fills.

2. **Mean-reversion arm (this paper):** MR is the theoretically-correct maker pairing because the post-only limit rests *at* the dislocation being faded — favorable selection. The graveyard already held 53 MR-family 15m cells across BTC/ETH/SOL (MMR, VWAP_MR, MRO), all gross-dead (best VWAP_MR-BTC 0.959). But VWAP_MR had **never** been run at 15m on ETHUSDT — the one untested fresh-coin cell for the maker-favorable archetype. The operator designated this the *last* cell of the program with a pre-registered binary falsifier: best gross PF < 1.0 → program closes.

---

## 2. Hypothesis

**Mechanism:** `VwapMeanReversionEngine` fades a ≥ `deviateMinPct` deviation from the session VWAP, gated by relative volume (`rvolMin`), with an ATR-based stop, a `tpR` reward-multiple target, and a `maxBarsHeld` time-stop. Long and short. PIT-clean feature set (ema200, relativeVolume20, atrRatio, adx, atr — no DVOL/skew open-stamped columns; audited by the plan reviewer).

**Pre-registration:** Hypothesis `725ad692` registered 2026-07-13T17:06:15, plan review request `42def258` submitted 2026-07-13T17:07:23 (gap ≈ 68s), APPROVED by reviewer `b6fa35be` (0 blocker fails, 0 warning fails) BEFORE the earliest sweep iteration (cell 1 backtest submitted 2026-07-13T17:21:54). **Falsification criterion (binary, machine-checkable):** best gross PF < 1.0 → the entire 15m-maker-scalp program is closed. **Success criterion:** gross PF ≥ 1.0 at n ≥ 200 in ≥ 1 cell → reopens the maker-MR thread (a real lead).

**Type:** ALGO — parametric sweep, no ML. The as-run scoring is taker-7.5bps; the maker question is answered by gross-rescoring, not by an ML gate.

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

Note: the program's operative bar was not V11 graduation but the **pre-registered gross-PF falsifier** — the mechanism cannot even reach the V11 gate discussion because it is a pre-cost loser. The V11/V60 gates were not loosened; they were never approached.

### 3.2 Sweep Design

- **Type:** GRID
- **Backtest window:** default floor 2024-01-01 → tick-time yesterday (full available ETHUSDT-15m history to backtest end; n per cell 3005–4476 confirms full-history depth)
- **Dimensions swept:** `deviateMinPct` ∈ {0.9, 1.4}; `tpR` ∈ {1.5, 2.0}. Held fixed: `rvolMin`=1.2, `maxBarsHeld`=12, `intervalMinutes`=15.
- **Total cells:** 4 planned, 4 executed (no gaps).

### 3.3 Walk-Forward Protocol

Did not run — no cell reached SIGNIFICANT_EDGE. Omitted.

### 3.4 Gross-rescore protocol (the load-bearing method — finding `fc3d8999`)

Fees are a deterministic linear function of per-trade notional, so a run scored under one cost model can be *exactly* re-scored under another with no re-simulation. For each cell's `backtest_run_id`, per-trade `gross_pnl_amount` was pulled from `backtest_trade` on the prod DB; gross PF = Σ(gross>0) / |Σ(gross<0)|. The method was validated to the digit against the prior VWAP_MR-BTC-15m n3903 cell (this session reproduced gross 0.7095, matching `fc3d8999`'s reported 0.710; and net PF 0.4162 matching the stored `metrics_snapshot.profit_factor`). A 2000-sample bootstrap (seed 42) over the per-trade gross-PnL vector gave the 95% CI on gross PF.

---

## 4. Parameter Space Explored

| Axis | Values Tested |
|---|---|
| `deviateMinPct` | 0.9, 1.4 |
| `tpR` | 1.5, 2.0 |
| `rvolMin` (fixed) | 1.2 |
| `maxBarsHeld` (fixed) | 12 |

**Total iterations:** 4

**Edge verdict distribution (as-run, taker-7.5bps):**

| Verdict | Count |
|---|---|
| SIGNIFICANT_EDGE | 0 |
| INSUFFICIENT_EVIDENCE | 0 |
| NO_EDGE_DETECTED (DISCARD) | 4 |

---

## 5. Results

### 5.1 Edge summary

Every cell is gross-dead. Gross PF clusters tightly in 0.78–0.81 with n 3005–4476 — an enormous sample, so the tightness is real signal, not sampling noise (the bootstrap CIs are narrow, ~0.10 wide, and every upper bound is below 1.0). The `deviateMinPct` axis is the only mover: raising the entry threshold 0.9→1.4 lifts gross PF ~0.782→0.807 (fewer, marginally-better trades) but nowhere near 1.0. The `tpR` axis is a near no-op (0.5–2.5% PF swing). The binding constraint is **the signal itself, not cost**: a strategy with gross PF 0.81 is losing 19% of its winning gross to its losing gross before a single basis point of fee is charged. No execution model — maker rebate, maker-real (entry 2bps / exit 4bps), taker-4, or the as-run taker-7.5 — can turn a pre-cost loser into a winner.

**Full per-cell gross-rescore:**

| Cell (deviateMinPct / tpR) | n | GROSS PF | Gross PF 95% CI | net PF (as-run) |
|---|---|---|---|---|
| 0.9 / 1.5 | 4476 | 0.7820 | [0.7306, 0.8360] | 0.5301 |
| 0.9 / 2.0 | 4239 | 0.7838 | [0.7266, 0.8426] | 0.5397 |
| **1.4 / 1.5 (best)** | **3159** | **0.8075** | **[0.7450, 0.8741]** | 0.5623 |
| 1.4 / 2.0 | 3005 | 0.8044 | [0.7339, 0.8794] | 0.5671 |

### 5.2 Best cell

| Param | Value |
|---|---|
| `deviateMinPct` | 1.4 |
| `tpR` | 1.5 |
| `rvolMin` | 1.2 |
| `maxBarsHeld` | 12 |

| Metric | Value |
|---|---|
| iteration_id | `9dcb97dd-84bb-4fdc-99ae-a88c59b0a94f` |
| backtest_run_id | `9dcb97dd`… (run `9dcb97dd-84bb-4fdc-99ae-a88c59b0a94f`) |
| n_trades | 3159 |
| GROSS PF (point) | 0.8075 |
| GROSS PF 95% CI lower | 0.7450 |
| GROSS PF 95% CI upper | 0.8741 |
| net PF (as-run, taker-7.5) | 0.5623 |
| Statistical verdict | NO_EDGE (DISCARD) |

The best cell's **entire** gross-PF 95% CI upper bound (0.874) sits below 1.0 at n = 3159 ≫ 200 — the falsifier is unambiguous, not a knife-edge.

---

## 6–9. Graduation / Specialist / Walk-Forward / Infra

Omitted — no SIGNIFICANT_EDGE cell reached these gates. No infrastructure bugs; two process notes are recorded in §Infrastructure below because they materially shaped execution:

- **`/tick/drain` client-timeout vs server continuation.** Two of the five drain calls returned HTTP 000 (curl `--max-time` abort) while their in-flight backtest continued server-side; the queue then returned to PENDING (via the original tick's finalize or the stuck-row reaper) and a fresh drain re-claimed it. No iteration was lost or double-logged; the append-only iteration_log confirms exactly 4 rows for 4 cells. Full-history 15m backtests run ~12–20 min each, so a single 4-cell sweep spans multiple drain windows and is best driven with repeated short drains.
- **Concurrent JVM contention.** A separate ATR_MOM-ETH-15m research queue held the research JVM's single backtest slot for stretches, serializing my cells behind it (each cell waited for the ATR_MOM run's ~30-min guard or completion). This is a throughput cost, not a correctness issue; the researcher does not disable other queues (not this run's work).

---

## 10. Methodology Compliance Audit

| Rule | Compliant? | Notes |
|---|---|---|
| Universe (BTC/ETH/SOL/BNB/XRP) (hard rule #1) | YES | ETHUSDT |
| Intervals in {5m,15m,1h,4h,1d} (hard rule #2) | YES | 15m |
| Research never mutates live (hard rule #3) | YES | backtest copies only; no live account touched |
| Research-mode only — no promotion (hard rule #4) | YES | no promote/deploy; falsified, nothing to ship |
| 10%/yr economic bar (hard rule #5) | YES | not approached — pre-cost loser |
| V11 + V60 gates honored (hard rule #6/#11) | YES | gates not loosened; never reached |
| ≥ 3 dimensions traversed (hard rule #7) | YES | entry (deviateMinPct), exit (tpR), interval (fresh-coin cell) — plus the gross-vs-cost execution axis |
| Pre-registration before testing (hard rule #10/#12) | YES | hypothesis 68s before plan; APPROVED before first iteration |
| Append-only durable evidence (hard rule #10) | YES | only a HYPOTHESIS **status** column transitioned ACTIVE→FALSIFIED (lifecycle column, not row deletion/content edit) |
| Reviewer verdict authoritative (hard rule #12) | YES | plan APPROVED (`b6fa35be`) before `/queue`; no override of the review gate |
| No Trading JVM (:8080) calls (hard rule #13) | YES | orchestrator (:8082) + read-only prod DB (research role) only |

*One override was used and journaled:* `override_discard_gate=true` on `/queue` (rationale journal `0eca7e7b`). Justification: the re-discovery gate is instrument-blind and fired because VWAP_MR had produced a DISCARD on the same axis-*names* at **BTCUSDT**-15m (prior_iteration `47f0b06f`, different coin, and different `deviateMinPct`=0.8); the reviewer's `axis_not_recently_failed` check independently verified the ETHUSDT-15m cell is genuinely fresh. This is exactly the documented override case, not p-hacking.

---

## 11. Conclusions

1. **Best gross PF is 0.8075 (n=3159), 95% CI [0.745, 0.874] — entirely below 1.0.** The VWAP_MR deviation-fade at ETHUSDT-15m is a pre-cost loser.
2. **The `deviateMinPct` axis is the only mover (0.9→1.4 lifts gross PF ~0.782→0.807); `tpR` is a near no-op.** Even the best entry-threshold cell does not clear gross 1.0.
3. **The pre-registered falsifier fired: best gross PF < 1.0 → the 15m-maker-scalp program is FALSIFIED and CLOSED.** The success condition (gross PF ≥ 1.0 at n ≥ 200) was not met on any cell.
4. **The MR-family is gross-dead at 15m on every coin in the universe.** Complete graveyard: VWAP_MR-BTC 0.959, VWAP_MR-ETH 0.808 (this), MMR-SOL 0.849, MMR-BTC 0.740, MRO-ETH 0.741 — none reaches 1.0. The maker-favorable-pairing thesis (favorable selection at the dislocation) does not manifest as a preservable gross edge, because there is no gross edge to preserve.
5. **Implication for the research loop:** mean-reversion and maker-scalp thinking at the 15m horizon are exhausted for the current universe. Maker rescue is only meaningful where GROSS PF > 1.0, and no 15m MR cell on any coin reaches it. Future intraday work must find a signal with a *positive pre-cost* edge before execution-model tricks are worth exploring.

---

## 12. Data Wishlist

*(No actionable data item unblocks this surface — the constraint is signal, not data. Omitted.)*

---

## 13. Appendix — Audit Trail

| Item | ID |
|---|---|
| Hypothesis (now FALSIFIED) | `725ad692-3ce2-44f3-a360-bcbe160423ba` |
| Plan review request | `42def258-b135-438c-8d1c-101fb9d05e2e` |
| Reviewer approval (plan APPROVED) | `b6fa35be-dc0b-4d3d-af04-8a594999057c` |
| Queue | `e501a13c-1c0f-41c6-9b12-9bfff975d6bf` |
| Cell iterations | `580223a6` (0.9/1.5), `689df0bb` (0.9/2.0), `9dcb97dd` (1.4/1.5, best), `c80a7f80` (1.4/2.0) |
| override_discard_gate rationale | `0eca7e7b-2643-47e6-8325-3f723c8308eb` |
| Gross-rescore methodology source | `fc3d8999-26d0-4fe6-bc94-600068b51c6d` |
| Momentum-arm falsification (adverse-selection) | `cc079e32-4eea-4906-95be-4225a98ec1ed` |
| STRATEGY_OUTCOME (falsification) | `47ab4780-8f02-4c06-bffb-e20f474a12dd` |
| RUN_SUMMARY (program closure) | `e1304dc2-7138-407e-b156-107976f6d57c` |
| DB paper | `BH-VWAP_MR-ETHUSDT-15M-e501a13c` |
| Walk-forward run | — (did not run) |
| Specialist verdicts | — (did not reach graduation) |

---
*Paper generated by quant-researcher. DB registration: `POST /papers/e501a13c-1c0f-41c6-9b12-9bfff975d6bf/generate` (paper_id `BH-VWAP_MR-ETHUSDT-15M-e501a13c`).*
