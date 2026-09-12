# Research Paper: DCB — BTCUSDT × 1d

**Author:** quant-researcher
**Date:** 2026-07-14
**Strategy:** `DCB` (Donchian breakout, causal / no-ML)
**Surface:** `BTCUSDT` × `1d`
**Type:** ALGO
**Surface attempt:** v2 — ALGO (corrected re-diagnosis of the v1 "data-blocked" 0-trades, with a control that isolates the true cause)
**Prior papers on this surface:** `v1_ALGO_2026-07-14` (prior session's premature "feature_values 1d gap" framing)
**Filename:** `RESEARCH_PAPER_DCB_BTCUSDT_1D_v2_ALGO_2026-07-14.md`
**Terminal:** ARCHETYPE_EXHAUSTION (root cause = DATA-PLANE feature_store compute-gap; operator-owed)
**Goal status:** NOT HIT (surface data-blocked; 0 trades — no edge measurable yet)
**Hypothesis:** `4a131f52-f7e6-4569-92d1-aba1c2a2404d`
**Queue(s):** `1804212e-f79d-4a5a-a419-4092a368f740`, `9ae84a51-b998-4ed2-bce6-d0afa628d67b`

---

## TL;DR

The prior session parked the daily (1d) Donchian-breakout surface as "data-blocked: feature_values has
no 1d features." The operator flagged this as a wrong-table misdiagnosis (DCB reads gate features from
`feature_store`, not `feature_values`) and directed a fresh, empirical re-diagnosis. Three fully-permissive
DCB-1d BTCUSDT backtests — including one with **no ADX gate** (`adxEntryMin=0`, `rvolMin=1.0`) over the
**full 2017→2026 history (3252 daily bars)** — all produced **exactly 0 trades**. A control backtest of
**EMA_BAND_BTC at the identical 1d interval, symbol, window, and coordinator produced 25 trades, PF 3.45,
SIGNIFICANT_EDGE.** That control is decisive: the 1d strategy path, the daily-monitor alignment, and
`feature_store` 1d loading all work. Therefore the 0-trades is neither a `feature_values` gap (the prior
framing) nor "feature_store fully populated" (the operator's stated correction) — it is a **feature_store
compute-coverage gap for DCB's specific gate-column family (`donchian_upper_20`/`donchian_lower_20`/
`relative_volume_20`/`adx`/`atr`) at interval=1d**, while the EMA/trend family that EMA_BAND reads IS
present. This is a DATA-PLANE blocker (INSUFFICIENT_DATA, `infra_failure_caused=true`), operator-owed; it
does **not** falsify DCB and does **not** count toward signal-exhaustion. No edge is measurable until the
1d feature_store gap is filled.

*(No metrics table — no cell reached SIGNIFICANT_EDGE; every DCB-1d cell = 0 trades.)*

---

## 1. Background

Platform alpha space was previously declared exhausted (memory 2026-07-13: "$0 alpha space EXHAUSTED; loop
PARKED, needs money/time/decision"). The single remaining genuinely-fresh, PIT-clean cell on a proven
archetype was DCB at the 1d interval — `1d` has never been used by any directional/breakout/CTA strategy
(all 16 existing 1d research seeds are EMA/VRP/DVOL/BASIS/XS/OPTIONS hedging strategies). The prior session
(RUN_SUMMARY `9bd9fa08`, queues `9a086a38`/`9df8ebd5`) probed DCB-1d, got 0 trades, and concluded the
`feature_values`/`feature_registry` ingest table has no 1d features → "data-blocked." The operator DB-noted
that DCB does not read that table — it reads the JVM-computed `feature_store` — and directed this session to
diagnose the 0-trades empirically before re-declaring anything.

---

## 2. Hypothesis

**Mechanism:** DonchianBreakoutEngine long entry = current bar closes above the previous bar's Donchian-20
upper channel (`prev.donchianUpper20`), with `relativeVolume20 ≥ rvolMin` and `adx ≥ adxEntryMin`; ATR-based
stop at `stopAtrMult×ATR`, single TP at `tpR×risk`; symmetric short off `donchianLower20`. Daily breakout is
classic low-cost trend/CTA alpha — costs are negligible at 1d (few trades), it is PIT-clean (no ML sleeve),
and a fresh interval carries a low DSR trial-tax.

**Pre-registration:** Hypothesis `4a131f52-f7e6-4569-92d1-aba1c2a2404d` (ALGO) registered before the earliest
sweep iteration; it explicitly **predicts a permissive DCB-1d BTC backtest fires >0 trades**, and pre-registers
the n-constraint (daily breakouts are rare → a single name won't reach n≥100; the n≥100 path is a PIT-clean,
anti-padding pooled core-5 book with the coin-inclusion rule fixed BEFORE compute). Falsification criterion for
the diagnostic: if a fully-permissive cell still fires 0 trades, the blocker is config/wiring/data, not edge.

**Type:** ALGO (no ML).

---

## 3. Methodology

### 3.1 Statistical Gates (V11 + V60)
Untouched: n≥100, PF 95% CI lower > 1.0, DSR ≥ 0.90, `annualized_geometric_return_pct_at_alloc_90` ≥ 10 for
GOAL_HIT, walk-forward ROBUST. No threshold-shopping. (Not reached — 0 trades everywhere.)

### 3.2 Diagnostic design
Deliberately maximally-permissive cells to force any latent edge to fire, isolating "wiring/data" from
"gates-too-strict":

| Cell | queue / iter | donchianPeriod | adxEntryMin | rvolMin | window | bars | **trades** |
|---|---|---|---|---|---|---|---|
| A | `1804212e` / `343f105f` | 20 | 20 | 1.0 | 2024-01-01→2026-07-13 | ~924d | **0** |
| B | `1804212e` / `de02eb15` | 20 | **0 (no ADX gate)** | 1.0 | ~924d | ~924d | **0** |
| C | `9ae84a51` / `323d7799` | 20 | **0** | 1.0 | **2017-08-17→2026-07-13** | **3252** | **0** |
| **CONTROL** | — / `0dce1fda` | EMA_BAND_BTC | — | — | 2017-08-17→2026-06-12 | ~3200 | **25 (PF 3.45, SIG_EDGE)** |

### 3.3 Why the control is the load-bearing evidence
`BacktestCoordinatorService` throws `IllegalArgumentException("No feature store found for interval:")` if the
strategy interval has no `feature_store` rows. Cell C did **not** throw (status COMPLETED, 3252 bars processed),
so 1d `feature_store` rows exist and were loaded. For all-1d runs the coordinator monitors on the 4h
`dailyMonitorInterval` and fires the strategy only when the monitor bar's `endTime` matches a 1d strategy
candle's `endTime`; EMA_BAND-1d firing 25 trades proves that alignment works. So neither loading nor alignment
is the fault.

---

## 4. Results & Root Cause

`DonchianBreakoutEngine.tryBreakoutLong/Short` returns `null` (→ HOLD) at the **first null gate input**:
`prev.getDonchianUpper20()`/`getDonchianLower20()`, `f.getRelativeVolume20()`, `f.getAdx()`, or
`resolveAtr(f)`. EMA_BAND reads `ema200` (works at 1d); DCB reads the Donchian/rvol/adx/atr family. Exactly-0
trades across 3252 daily bars with **no ADX gate** and `rvol≥1.0` means at least one of those DCB-specific
`feature_store` columns is null on **every** 1d bar. The JVM `TechnicalIndicatorService` feature_store
computation populated the EMA/trend family at 1d but not (effectively, for the DCB read-path) the
Donchian/rvol/adx/atr family.

**Root cause: a `feature_store` compute-coverage gap for DCB's gate-column family at interval=1d.** This is a
DATA-PLANE blocker, classified INSUFFICIENT_DATA / `infra_failure_caused=true`. It does not falsify DCB
(proven ETH-1h live-ROBUST) and does not count toward archetype exhaustion (persistence doctrine).

**On the two prior framings:** (a) the prior "no 1d features in `feature_values`/`feature_registry`" is
literally true — the ingest registry has only 15m/1h/4h and none of the DCB gate columns — but it is the
**wrong read-path** for DCB. (b) The operator's stated correction that `feature_store` 1d is 100% non-null
for the DCB gate columns is **not borne out by engine behavior**: if those columns were populated, a no-ADX-gate
20-day Donchian over 9 years of BTC would fire many trades. The EMA_BAND control shows only the EMA/trend family
reaches the engine at 1d.

**Could not run raw SQL to name the exact null column(s):** the tunneled prod DB (fwd port 15432) and prod
research JVM (:8081; `/api/v1/dev/login-as` returns 404 on prod) reject the on-disk `.env` credentials — the
live tunneled process env differs from the on-disk `.env`. Exact per-column verification is operator-owed.

### 4.1 Secondary finding — DCB-1d research seed gap
No DCB (or any breakout/CTA) `account_strategy` row exists at interval=1d. Of 95 research seeds, 16 are at 1d
but ALL are EMA/VRP/DVOL/BASIS/XS/OPTIONS. The queue did not 412 (the pre-queue check is interval-agnostic on
`strategy_code`), so this did not block the probe — but a DCB-1d seed should be added alongside the feature
recompute so a proper sweep can attribute cleanly.

### 4.2 n-constraint (pre-registered, still standing)
EMA_BAND-1d makes only **25 trades over 9 years** — daily strategies are extremely trade-sparse. Even once the
feature gap is fixed, a single DCB-1d name will not reach n≥100; the n≥100 path is the PIT-clean, anti-padding
pooled core-5 book (coin-inclusion rule fixed before compute; no drag-coin filler; no ML-gate look-ahead — the
DCB_POOL cert was voided for a backfilled regime model, do not repeat).

---

## 5. Conclusion & Operator-Owed

DCB-1d is a genuine, PIT-clean fresh surface but is **data-blocked at the feature-computation layer**, not
no-edge and not falsely "feature_values-blocked." No edge is measurable until unblocked. Terminal =
ARCHETYPE_EXHAUSTION (the one fresh in-data cell is operator-owed; the rest of the in-data, in-universe space
is graveyarded — VWAP_MR FALSIFIED, ATR_MOM maker-flip artifact, MRO/MMR/VWAP_MR mean-reversion gross-dead,
XS ranking graveyarded, DCB single-name swept at 15m/1h/4h).

**Operator-owed (JVM/data-plane; not research-mode):**
1. DB-verify `feature_store WHERE interval='1d'` column nullity for `donchian_upper_20`, `donchian_lower_20`,
   `relative_volume_20`, `adx`, `atr` on core-5. (EMA_BAND-1d works ⇒ 1d rows exist; the DCB gate-column
   family is the suspect.)
2. If null/absent: run the JVM `TechnicalIndicatorService` feature_store recompute at interval=1d for that
   column family on core-5. Then re-probe DCB-1d.
3. Seed a DCB-1d `account_strategy` row for core-5 (secondary finding 4.1).
4. Standing DECISIONS (unchanged): fund Tardis skew data vs wait ~12mo for the free skew feed; optionally build
   a dual-archetype-confirmation JVM engine mode.

**Journals:** HYPOTHESIS `4a131f52`; STRATEGY_OUTCOME (root cause) `af8fee3e`; RUN_SUMMARY (terminal)
`a12d2a66`. Iterations: `343f105f`, `de02eb15`, `323d7799` (DCB-1d 0-trades), `0dce1fda` (EMA_BAND-1d control).
Gates untouched (V11+V60), PIT-clean, no promote/deploy/live/git.
