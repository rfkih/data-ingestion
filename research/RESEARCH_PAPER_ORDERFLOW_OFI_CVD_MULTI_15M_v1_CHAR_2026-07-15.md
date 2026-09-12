# Research Paper: ORDER-FLOW / OFI-CVD candle-proxy — BTC/ETH/SOL/BNB/XRP × 15m — fast-bar scalping edge

**Author:** quant-researcher (local analysis, ANALYSIS-mode — no git/deploy/live writes)
**Date:** 2026-07-15
**Signal family:** candle-derived order-flow proxies — `ofi_ratio` (taker_buy/volume), `ofi_zscore_24h`, `ofi_momentum_8h`, `cvd_proxy_zscore_24h`, `cvd_proxy_pctrank_90d` (+ recomputed true per-bar OFI from raw `taker_buy_base_volume`)
**Surface:** BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT × `15m` (fast-bar), H ∈ {1,2,4} bars = 15/30/60 min
**Type:** CHAR (signal characterization / cost-viability, no engine artifact)
**Terminal:** NULL — real reversion IC, but per-trade edge is an order of magnitude below the cheapest realistic cost. Closes the **candle-proxy** order-flow box (NOT the true L2 order-book version).
**Goal status:** NOT HIT (no certifiable edge). Expected NULL, confirmed cleanly.
**Data:** one controlled VPS read → all-local. `orderflow_15m.csv` (4.51M feature rows), `md_15m.csv` (1.01M OHLCV+taker rows). Panel = 903,012 exactly-ts-matched 15m bars, BTC/ETH from 2020-06, SOL/BNB/XRP from 2022-01, through 2026-07-14.

---

## TL;DR

Candle-proxy order-flow at 15m carries a **real, stationary, highly-significant REVERSION signal** — but the edge is **~0.2–1.5 bps per trade gross**, roughly **10× smaller than the cheapest realistic round-trip cost** (≈4 bps maker / 15 bps taker). It does not clear costs in any of 54 backtest cells, in either the taker or the (favorable-fill) maker model, under either a contemporaneous or a PIT-clean +1-bar-lagged join. NULL — as the priors predicted. This is the classic microstructure result: taker-buy imbalance predicts exactly the bid-ask bounce / temporary impact you can only monetize by *being* the maker who supplied that liquidity, which candle bars cannot represent.

**Archetype: REVERSION** (unanimous). High taker-buy aggression → next-bar price reverts DOWN. Every one of 45 IC cells (5 signals × 3 H × pooled+5 coins) is negative, CI excludes zero, IC magnitude ~10× the shuffle noise floor.

---

## 1. Background & look-ahead guard

This is the last untested scalping angle: order-flow / microstructure at fast bars. Priors were adverse — OFI/CVD at **1h** was already found DEAD clean (`project_cvd_momentum_lead_2026-06-14`), and the full ML direction sweep on price/volume-class features was coin-flip. Candle-proxy OFI/CVD is the same information class (taker buy/sell split baked into the bar), so the base rate for an edge was low; the test exists to *close the box*.

**Critical trap avoided.** The 2026-06-14 CVD "lead" (+148%/yr) was falsified as an **interval-mixing look-ahead** — features from one interval joined to another interval's bars leaked the future. This run **strictly used `interval='15m'` features joined ONLY to 15m bars via an EXACT-timestamp inner join** (`feature_values.ts == market_data.start_time`, both bar-open on the same 15-min grid), never `merge_asof`, never a cross-interval join. Cross-check: the stored `ofi_ratio` reproduces recomputed `taker_buy_base_volume/volume` to **corr = 1.0000, mean|diff| = 0.00000**, confirming the join is bar-aligned and the feature semantics are exactly as documented.

**Additional PIT nail — the +1-bar lag.** A feature stamped at bar `t` describes `[t, t+15m)` and is fully known only at that bar's close. Forward return is measured from the *same* close forward (`log C[t+H] − log C[t]`), so the contemporaneous join is already PIT-legal. To be conservative I re-ran everything with the feature lagged one full bar (known strictly before the return window opens). **The IC survives the lag** (pooled CVD-pctrank H1: −0.0306 → −0.0256), so the signal is NOT a stamp-timing artifact. The reversion is real.

---

## 2. Methodology (honest stack, reused from `dir_predict_local.py` / `vol_forecast_stationary.py`)

- **Signal→forward-return IC:** Spearman, per (coin, signal, H) and pooled. **Block bootstrap** CI (1-day/96-bar blocks to respect autocorr) and a **shuffle-label noise floor** (95th pct of |IC| under permuted labels). Signal counts only if |IC| > shuffle95 AND the bootstrap CI excludes 0. (Vectorized on ranks; base IC validated identical to `scipy.spearmanr`.)
- **LightGBM direction:** OFI/CVD feature set → sign(fwd ret), **purged + embargoed walk-forward** (train 365d, embargo 3d+H, test 90d, roll), per-fold **adversarial_auc** (train-vs-test separability; >0.72 = era-detector), and a **shuffle-label control** model per fold.
- **Archetype:** sign of the pooled IC. Negative ⇒ REVERSION (a passive maker limit is *favorably* filled — model no adverse haircut). Positive would be momentum/continuation ⇒ maker adversely selected.
- **Bounded scalp backtest:** enter on the decile extreme of the signal (top/bottom 10%), direction set by archetype, hold H bars, exit at close, **non-overlapping** entries (≥H apart) so trades are ~independent. Cost models in log-return space: **taker 7.5 bps/side (15 bps round-trip)**; **maker 2 bps/side (4 bps round-trip)** plus an archetype haircut (0 for reversion since fills are favorable; +4 bps had it been momentum). PF + **block-bootstrapped PF 5%-CI-low** per cell. Bar to clear: **net-of-cost PF-CI-low > 1**.

---

## 3. Results

### 3.1 IC — real, stationary, unanimous reversion (CONTEMP join, pooled)

| Signal | H1 IC | H2 IC | H4 IC | shuffle95 | archetype |
|---|---|---|---|---|---|
| cvd_proxy_pctrank_90d (stationary) | −0.0306 | −0.0338 | −0.0282 | ~0.0020 | **rev** |
| ofi_ratio_true (raw taker frac) | −0.0277 | −0.0305 | −0.0247 | ~0.0020 | **rev** |
| ofi_zscore_24h | −0.0253 | −0.0279 | −0.0219 | ~0.0021 | **rev** |
| ofi_momentum_8h | −0.0196 | −0.0202 | −0.0156 | ~0.0021 | **rev** |

All 45 IC cells (incl. per-coin) negative; every CI excludes 0; every |IC| ~10× the shuffle floor. Per-coin H2 CVD-pctrank ranges −0.031 (BNB) to −0.038 (BTC). Under **LAG+1** the pooled IC attenuates ~15–20% (H1 −0.0306→−0.0256) but stays significant everywhere. The stationary 90-day-pct-rank variant (built specifically to kill the adv_auc≈1.0 problem) behaves identically to the raw ratio → the signal is not an epoch artifact.

### 3.2 LightGBM WF direction — barely-there, adv_auc borderline

Pooled OOS-AUC ≈ **0.507–0.513**, shuffle ≈ 0.500–0.502, delta **+0.006 to +0.013**; only ~5–15% of folds beat 0.52; **mean adv_auc 0.62, max 0.94** (BTC z-scores drift). Consistent with the linear IC (a ~0.03 IC ≈ ~0.51 AUC) — there is *some* real directional information, but it is tiny and partly non-stationary. Under LAG+1 the delta shrinks further (+0.003 to +0.012). This is not tradeable AUC; it merely corroborates the IC.

### 3.3 Cost-net scalp backtest — the killer (both join modes, all 54 cells)

| Cost model | cells with PF-CI-low > 1 (of 54) | best cell PF-CI-low |
|---|---|---|
| **Gross (zero cost)** | 29–31 / 54 | ~1.05 (BTC ofi_ratio_true H2) |
| **Net-MAKER (4 bps RT, favorable fills)** | **0 / 54** | 0.891 (SOL cvd-pctrank H2/H4, PF 0.92) |
| **Net-TAKER (15 bps RT)** | **0 / 54** | 0.666–0.682 (SOL cvd-pctrank H4) |

Mean gross return per trade is **~0.2–1.5 bps**. Gross PF barely exceeds 1.0 (~1.01–1.08) on ~half the cells and is *itself* inside the noise band on many. Applying even the cheapest maker round-trip (4 bps) pushes **every** cell's net-maker PF to 0.6–0.93 with CI-low ≤ 0.89 — below break-even. Taker costs bury it 3–5× over. Identical picture under CONTEMP and PIT-clean LAG+1. No coin, no horizon, no signal, no cost model clears the bar.

---

## 4. Interpretation

The signal is genuine and economically interpretable: a burst of taker-buy aggression on a 15m bar is precisely a bout of **temporary price impact / spread crossing**, which mechanically reverts a few bps on the next bars. That reversion IS the liquidity-provision premium — it accrues to the **maker who supplied the fill**, not to a taker (who pays the impact) nor to a maker-scalper working candle bars (who cannot know *where in the book* the pressure hit, cannot queue-position, and whose modeled "favorable fill" still can't be paid by a 0.5-bps gross edge against a 2-bps/side fee). This is textbook: candle-derived order-flow captures the *shadow* of the microstructure premium but none of the *mechanism* needed to harvest it.

**Falsifiers pre-registered and hit:** (a) IC must beat shuffle + be stationary — PASSED (so we can't dismiss it as noise); (b) net-of-cost PF-CI-low > 1 — **FAILED in all 54 cells under the friendliest (maker, favorable-fill) model.** The signal is real; the *edge* is not.

---

## 5. Verdict & scope

**NULL.** Candle-proxy order-flow (OFI/CVD) gives **no fast-bar scalping edge that clears costs** — taker or maker — on any of BTC/ETH/SOL/BNB/XRP at 15/30/60-min horizons. It joins the 1h CVD/OFI result and the price/volume direction sweep in the graveyard. This **closes the candle-proxy order-flow box** — the last untested scalping angle in that information class.

**Explicit scope boundary:** this does **NOT** close the **true L2 order-book** version of the hypothesis (real bid/ask depth, queue position, book imbalance, resting-order dynamics). That is a *different information class* the candle proxy cannot represent, is data-thin today (`ob_*` snapshot features maturing ~Aug), and remains the only live path for a genuine microstructure edge. The reversion sign found here (buy-pressure → mean-revert) is the *encouraging* prior for that L2 work: it says the liquidity-provision premium exists at 15m — the open question is whether an L2 maker strategy can queue into it, which candle bars structurally cannot test.

**Recommended next action:** none on candle proxies. Re-open microstructure only when L2 book history matures; use this reversion IC as the pre-registered mechanism to validate against.

---

## Appendix — artifacts (local, `.rtmp`, gitignored)

- Analysis: `C:/Project/.rtmp/orderflow_scalp.py`
- Log (full 45-cell IC grid + 18 ML cells + 54 backtest cells × 2 join modes): `C:/Project/.rtmp/orderflow_scalp.log`
- Results JSON: `C:/Project/.rtmp/orderflow_scalp_results_CONTEMP.json`, `..._LAG+1.json`
- Data: `C:/Project/.rtmp/mldata/orderflow_15m.csv`, `C:/Project/.rtmp/mldata/md_15m.csv`
