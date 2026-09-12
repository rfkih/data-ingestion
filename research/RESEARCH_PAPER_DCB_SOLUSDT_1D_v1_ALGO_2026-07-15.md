# Research Paper: DCB — SOLUSDT × 1D (ride-longer exit axis)

**Author:** quant-researcher
**Date:** 2026-07-15
**Strategy:** `DCB` (Donchian breakout)
**Surface:** `SOLUSDT` × `1D` (exit-axis probe for the pooled DCB-1d book)
**Type:** ALGO
**Surface attempt:** v1 — ALGO (ride-longer exit test of the DCB_1D warm lead; sibling surfaces MRO-BTCUSDT-1D + XS_MOM-core5-1D covered in §7)
**Prior papers on this surface:** none (first DCB-SOLUSDT-1D paper); related: `RESEARCH_PAPER_DCB_SOLUSDT_4H_v1_ALGO_2026-07-09.md`, DCB_1D verdict RUN_SUMMARY `DCB_1D_VERDICT_2026-07-14`
**Filename:** `RESEARCH_PAPER_DCB_SOLUSDT_1D_v1_ALGO_2026-07-15.md`
**Terminal:** ARCHETYPE_EXHAUSTION
**Goal status:** NOT HIT
**Hypothesis:** `0f04038c-f490-4173-976b-3751e122cb7c` (DCB exit) + `91c747fa-fd7a-4eb3-96a9-1e22dd6366cd` (MRO window) + `f02e601d-4375-490e-aec1-2118d41191e8` (XS_MOM wider-leg)
**Queue(s):** `604460b3-b7b4-429d-8a7e-2974d8330448` (DCB), `5e789e5b-01fb-46ad-93ae-9a00f3fa5a77` (MRO)

---

## TL;DR

This session resumed the operator-directed run whose XS_MOM JVM-reproduction checkpoint (risk-parity book sleeve #2) had already been answered by the prior session — QUALIFIED NO-GO (the offline ~0.9 Sharpe reproduces on the real JVM only at a single knife-edge lb14×weekly cell, DSR 0.010). The session then drained the three remaining frontier warm leads to honest resolution. All three failed in research-mode: (1) the **XS_MOM wider-leg** lead was falsified pre-queue — leg-widening from topQ 0.20 to 0.25 was already tested (2026-06) and produced no DSR lift (both ~0.01), and the promising 8-coin variant is data-gated; (2) the **DCB-1d ride-longer exit** thesis (this paper's headline experiment) was falsified on the JVM-reachable exits — wider tpR strictly lowers DSR (pure multiplicity, no PF gain because trades never reach the wider target), wider stops destroy the edge, and longer holds raise raw return but not the risk-adjusted book measure; (3) the **MRO-BTC-1d** COLD_POWER lead resolved to DEAD — widening the window to full history raised n as predicted (8-11 → 32-45) but the point-PF collapsed from ~2.0 to ~0.6 (net losing), proving the 2024-25 edge was a bull-regime artifact. The single most important finding: **the daily crypto book-DSR ceiling (~0.27 for the DCB-1d trend book) is a correlation-synchronization wall, not a tunable exit/entry/window parameter — it is archetype-invariant, and every research-mode lever is now exhausted.**

*(No cell reached SIGNIFICANT_EDGE — metrics table omitted.)*

---

## 1. Background

Run frame: build a daily risk-parity book (DCB-1d trend + XS-momentum-neutral + carry) as the graduation unit, since no single daily strategy clears DSR≥0.90 solo (`SCOPE_2026-07-15_live_riskparity_book_build.md`). At session start the frontier carried three warm leads from the prior sessions' `RUN_SUMMARY` `OPERATOR_DIRECTED_XS_MOM_VALIDATION_2026-07-15`: DCB_POOL-1d (WARM, DSR 0.271, one gate short), XS_MOM core-5 1d (WARM, wider-leg axis un-swept), MRO-1d BTCUSDT (COLD_POWER, frequency-starved). The 1d surface had already fired `ARCHETYPE_EXHAUSTION_2026-07-14` (trend + MR both Sharpe-capped by BTC-beta synchronization); the operator's XS_MOM directive was the bypass that re-opened this run.

---

## 2. Hypothesis

**Mechanism (headline DCB experiment):** DCB is a two-sided Donchian-20 breakout: enter long on an upper-channel break (short on lower), stop at `stopAtrMult`×ATR, take profit at `tpR`×R, timed-exit at `maxBarsHeld` bars. The pooled DCB-1d book (BTC/ETH/SOL/XRP) is real (PF 1.50, +16.2%/yr, profitable bull AND bear) but one gate short (book DSR 0.271 < 0.90). The lead's stated mechanism — "ride trends longer may lift Sharpe past DSR" — has an operator-owed named axis (opposite-channel Turtle-27 exit / Donchian-55 channel, which does not exist in the JVM engine). This experiment tested the SAME ride-longer mechanism through the exits the JVM DOES expose: **wider tpR (4→6→8) lets winners run to bigger targets; longer maxBarsHeld (60→90→120) holds through more of the trend; wider stopAtrMult (3.5→4.5) avoids premature stop-outs.** Prediction: these raise per-name Sharpe and lift book DSR toward the gate, because daily crypto trends persist many bars and the fixed 4R/60-bar exit clips winners early.

**Pre-registration:** Hypothesis `0f04038c` registered 2026-07-15 ~10:16 UTC, before the sweep iterations (~10:20+). Falsification criterion: if no cell lifts single-name Sharpe/PF materially above the fixed-4R baseline, the exit dimension is exhausted for DCB-1d in research-mode.

**Type:** ALGO.

---

## 3. Methodology

### 3.1 Statistical Gates (V11 + V60)
n_trades ≥ 100 · PF 95% CI lower > 1.0 · DSR ≥ 0.90 · SIGNIFICANT_EDGE · ag90 ≥ 10%/yr · walk-forward ROBUST. Gates unchanged; not loosened.

### 3.2 Sweep Design (headline DCB experiment)
- **Type:** GRID
- **Surface:** DCB SOLUSDT 1d (strongest E1 single-name, PF 2.05), research seed acct `99999999-…-002`, enabled=false simulated=true.
- **Backtest window:** 2020-08-11 → now (full SOL history; via `sweep_config.backtest_window.start_time` override).
- **Dimensions:** tpR {4.0, 6.0, 8.0} × maxBarsHeld {60, 90, 120} × stopAtrMult {3.5, 4.5}; fixed entryMode=BREAKOUT, allowShort=true, adxEntryMin=0, rvolMin=0, maxEntryRiskPct=0.12.
- **Total cells:** 18 planned, 18 executed.

---

## 4. Results (DCB-SOLUSDT-1d exit grid, all INSUFFICIENT_EVIDENCE at single-name n)

DSR is used as the risk-adjusted-book proxy (the Sharpe field was null; DSR tracks book Sharpe monotonically here).

| tpR | mbh | stop | n | PF | DSR | ag90 % |
|---|---|---|---|---|---|---|
| 4 | 60 | 3.5 | 63 | 2.048 | 0.378 | +36.5 |
| 4 | 90 | 3.5 | 53 | 2.416 | 0.385 | +51.6 |
| 4 | 120 | 3.5 | 49 | 2.655 | 0.367 | +61.5 |
| 6 | 60 | 3.5 | 63 | 2.048 | 0.267 | +36.5 |
| 8 | 60 | 3.5 | 63 | 2.048 | 0.216 | +36.5 |
| 6 | 120 | 3.5 | 49 | 2.551 | 0.257 | +57.2 |
| 8 | 120 | 3.5 | 49 | 2.551 | 0.217 | +57.2 |
| 4 | 60 | 4.5 | 38 | 1.093 | 0.014 | −3.1 |
| 4 | 90 | 4.5 | 32 | 1.561 | 0.030 | +6.5 |
| 4 | 120 | 4.5 | 27 | 1.058 | — | −6.8 |

**Three clean effects:**
1. **Wider tpR strictly LOWERS DSR** at every (mbh, stop): e.g. at mbh60/stop3.5, DSR 0.378 → 0.267 → 0.216 as tpR 4→6→8, with **identical PF 2.048**. Trades rarely reach the wider TP, so widening tpR adds only trial multiplicity (deflating DSR) with zero return benefit. Ride-longer via tpR is refuted.
2. **Wider stop (3.5→4.5) is destructive:** PF 2.05→1.09, DSR 0.38→0.01, ag90 +36%→−3%.
3. **Longer maxBarsHeld (60→90→120) at stop3.5 raises PF (2.05→2.66) and ag90 (+36%→+61%) but DSR stays flat ~0.37-0.385** — raw return up, risk-adjusted book measure unchanged.

Best single-name cell: tpR4/mbh90/stop3.5 (PF 2.42, +51.6%/yr, DSR 0.385) — a marginal per-name improvement, not a book-DSR-mover (a pooled book needs the DSR to climb from 0.271 to 0.90). Regime-analysis `is_promising=true` was a thin-cell artifact (BULL PF 1.19 n=11 on the worst cell; NEUTRAL negative PF 0.46); no SOLUSDT regime ML model exists → step-8.5 Else path (annotate + pivot).

---

## 5. Interpretation

The DCB-1d book-DSR ceiling is **not** an exit-tuning problem. It is the correlation-synchronization wall diagnosed in `ARCHETYPE_EXHAUSTION_2026-07-14`: all daily crypto majors are BTC-beta, so daily trend breakouts fire synchronized across coins → zero diversification → book Sharpe capped ~1.0 (DSR ~0.27) regardless of per-name exit. Per-name exit-tuning can move a single coin's raw return but cannot break the book-level correlation ceiling. With entry (ADX, prior-falsified), exit (this paper), interval, regime, and sizing all traversed, every research-mode DCB-1d lever is exhausted. The only remaining lever is the operator-owed engine feature (donchian_55 channel + opposite-channel Turtle exit).

---

## 6. Threats to validity

- Single-name SOL n is thin (27-63) → INSUFFICIENT_EVIDENCE by construction; the DSR comparison across the grid is internally consistent (same surface, same window) and is the correct read for the *relative* exit effect, which is what the hypothesis tested.
- The regime `is_promising` flag fired on one weak cell; treated as artifact, not signal — consistent with the prior ADX/regime-gate falsification on DCB_1D.

---

## 7. Sibling experiments this session (frontier lead drainage)

**7a. XS_MOM core-5 1d wider-leg (hyp `f02e601d`) — FALSIFIED pre-queue.** The operator-directed JVM reproduction was already complete (QUALIFIED NO-GO, journal `35434f65`): canonical daily-rebalance Sharpe 0.654 / DSR 0.003 / ag90 −15.4%; the offline ~0.9 reproduces only at lb14×weekly (Sharpe 0.957, +13.8%/yr, n=614) which itself fails V11 (PF-CI-low 0.904, DSR 0.010). The remaining lead axis was leg-width. Pre-existing DB evidence killed it: topQ 0.20 → DSR max 0.010; topQ 0.25 (swept 2026-06) → DSR max 0.012 — no lift from widening. On a 5-coin universe topQ 0.30 ≈ topQ 0.25 (top ~1.5 vs ~1.25 names) → cannot move DSR two orders of magnitude. The only promising variant (8-coin 2×2) is DATA-gated: no 1d market_data beyond core-5. Outcome journal `9d21e98a`.

**7b. MRO-BTCUSDT-1d full-history window (hyp `91c747fa`) — DEAD (bull-only artifact).** First corrected a factual error in the lead: the window-widen was labeled "operator/orch-owed" but `tick.py:748-753` already reads `sweep_config.backtest_window.start_time` — always research-mode-reachable. Re-ran the 2026-07-14 positive-PF cells over 2017-08 instead of the 2024-01-01 default. n rose exactly as the frequency-proportionality mechanism predicted (8-11 → 32 and 45 trades) BUT the point-PF collapsed from ~2.0 to **0.59 / 0.64** (net losing), DSR 0.0001, ag90 **−2.9% / −1.7%**. The 2024-25 PF 2.0 was a bull-regime artifact: over the 2018+2022 bears the BB-band reversal-fade catches falling knives (same flaw as gross-dead MMR). Daily crypto mean-reversion is bull-only across both mechanisms. Outcome journal `f400e5b9`, DB paper `BH-MRO-BTCUSDT-1D-5e789e5b`.

---

## 8. Conclusion & next axis

Terminal: **ARCHETYPE_EXHAUSTION** (second+ diagnosis in the trailing-7d window; the first terminal fired 2026-07-14). All three frontier families are research-mode-exhausted on the 1d surface: DCB_1D (correlation-ceiling, only lever operator-owed), MR_1D (bull-only DEAD), XS_MOM (QUALIFIED NO-GO + wider-leg falsified + 8-coin data-gated). The correlation-synchronization ceiling is archetype-invariant at the daily horizon — the fix is a **universe** change (a lower-beta / non-crypto daily instrument uncorrelated to BTC), not a strategy tweak.

**Data wishlist (unblocks the next direction):**
1. Engine feature — `donchian_upper_55/lower_55` column + tunable entry-channel period + opposite-channel Turtle exit in `DonchianBreakoutEngine` (the DCB_1D ride-longer lever; offline-55+Turtle PF 1.76 > JVM-20+ATR 1.50).
2. 1d market_data + feature backfill for ≥3 liquid alts (ADA/DOGE/AVAX/LINK) → enables an 8-coin 2×2 XS-momentum universe (the only path that could lift XS-mom DSR at low turnover).
3. A lower-beta / non-crypto daily instrument uncorrelated to BTC — the structural fix for the daily book-Sharpe ceiling (a UNIVERSE problem, not an archetype problem).
4. Liquidation-reaction (`LIQ_FADE`) data maturing ~Aug — the best fresh intraday direction, cost-insensitive (big dislocations).
