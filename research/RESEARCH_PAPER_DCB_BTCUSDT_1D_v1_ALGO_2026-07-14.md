# Research Paper: DCB — BTCUSDT × 1D

**Author:** quant-researcher
**Date:** 2026-07-14
**Strategy:** `DCB`
**Surface:** `BTCUSDT` × `1d`
**Type:** ALGO
**Surface attempt:** v1 — ALGO (first-ever probe of the 1d interval for any archetype on this platform)
**Prior papers on this surface:** none (first attempt)
**Filename:** `RESEARCH_PAPER_DCB_BTCUSDT_1D_v1_ALGO_2026-07-14.md`
**Terminal:** ARCHETYPE_EXHAUSTION
**Goal status:** NOT HIT (region verified DATA_BLOCKED — never actually backtested)
**Hypothesis:** `9d3ac8e7-447d-4a14-b61a-a38e8ef5df2e`
**Queue(s):** `9a086a38-42dd-40dd-a956-00197f9f7ebe` (v1), `9df8ebd5-d932-4f17-a07f-58131d3d040d` (v2, config-fixed)

---

## TL;DR

The one genuinely-fresh region left on a proven archetype — DCB (Donchian-channel breakout) at the **1d** interval — was probed with two bounded, cost-netted sweeps on BTCUSDT. **Both returned exactly zero trades across every cell**, over a valid 923-day window (2024-01-01 → 2026-07-12). The failure mode is not "no edge": it is a data-plane plumbing gap. The `feature_registry` has **zero features computed at the 1d interval** (coverage: 15m=6, 1h=39, 4h=17, 1d=none), and DCB is a spec-driven engine (`EngineContextHelpers`: ATR/rvol/regime resolution) that cannot evaluate entry gates without features at its traded interval. Raw 1d OHLCV *does* exist (the daily-close buy-hold benchmark read it without error), but the strategy path is starved of 1d feature values. Classification: **INSUFFICIENT_DATA** — does not falsify DCB and does not count toward signal-exhaustion. No SIGNIFICANT_EDGE cell, so no metrics table.

---

## 1. Background

Session resumed a paused autonomous loop (cumulative ~4h43m) with an explicit operator mandate: find a *genuinely fresh* region not in the graveyard, prioritising untested (coin, archetype, interval) cells. A full graveyard scan (200 iterations, 120 journal rows, 30 filesystem papers, 16 FALSIFIED hypotheses) established that the proven-archetype × core-5 surface is worked out at every plumbed interval (5m/15m/1h/4h): DCB-ETH-1h is live and walk-forward ROBUST; DCB-ETH-4h is DSR-blocked (confirmatory FALSIFIED — PF 1.94 / n=131 / PF-CI-low 1.263 / ag90 53% but DSR deflated by cumulative_trials=172); DCB-15m gross-dead; TPB sub-DSR / frequency-starved; ATR_MOM bull-only / gate-rejected; MRO/MMR/VWAP_MR mean-reversion gross-dead; cross-sectional ranking (XS_MOM_14D, XS-BASIS, XS_IVRV, funding/LSR) fully FALSIFIED. The single untouched cell on a proven archetype was the **1d interval** — never used for directional research (it was added to `VALID_INTERVAL_NAMES` for the hedging/allocation track).

---

## 2. Hypothesis

**Mechanism:** A Donchian-channel breakout (donchianPeriod ~20/30) at the daily cadence is a slow multi-week trend-follower on the strongest-trending majors — fewer, larger, higher-conviction breaks; far lower turnover → lower cost drag → better net survival than the 4h variant. Same let-trends-run exit profile (tpR 3-5, breakEvenR 1.0, stopAtrMult 3.0) that makes DCB the proven ETH-1h winner. Crucially **no ML sleeve** — cannot inherit the look-ahead that contaminated the wound-down 4h DCB pool (`regime_eth_v2`).

**Pre-registration:** Hypothesis `9d3ac8e7` registered ACTIVE before any sweep. Falsification criterion: a per-coin point PF ≤ 1.0 after cost on BTC (the strongest trender) falsifies the family; PF > 1.0 with n < 100 is COLD_POWER (a power problem, resolved by pooling the core-5 at 1d). Plan reviewed and APPROVED twice (0 blocker fails; the `axis_not_recently_failed` reviewer check explicitly confirmed the axis combo was fresh).

**Type:** ALGO (pure price, PIT-clean).

---

## 3. Methodology

### 3.1 Statistical Gates (V11 + V60)

n ≥ 100, PF 95% bootstrap CI lower > 1.0, DSR ≥ 0.90 (operator methodology decision 2026-06-15), `annualized_geometric_return_pct_at_alloc_90` ≥ 10, walk-forward ROBUST. Gates untouched — no threshold-shopping. The retired +20bps slippage check was not enforced.

### 3.2 Sweep Design

- **Type:** GRID, seed 42.
- **Backtest window:** 2024-01-01 → 2026-07-12 (~30 months; orchestrator default start).
- **Dimensions swept (≥3):** entry (donchianPeriod {20,30}, adxEntryMin {0,20}), exit (tpR {3.0,5.0}, breakEvenR {1.0}, stopAtrMult {3.0}), interval (1d — the fresh axis). Fixed: rvolMin 1.0, maxBarsHeld 60, entryMode BREAKOUT.
- **Total cells:** 8 planned, 5 executed per queue (grid-combo collapse on singleton axes).
- **Two runs:** v1 (`9a086a38`) as designed; v2 (`9df8ebd5`) added `intervalMinutes=1440` after v1 returned 0 trades, to rule out a bar-cadence config gap.

---

## 4. Results

| Queue | Cells run | Trades/cell | Verdict |
|---|---|---|---|
| v1 `9a086a38` | 5 | 0 | INSUFFICIENT_EVIDENCE (n=0) |
| v2 `9df8ebd5` | 5 | 0 | INSUFFICIENT_EVIDENCE (n=0) |

Representative iterations: `793ba27d` (v1, donchianPeriod 30 / tpR 3.0 / adx 0 → n=0), `b84c6028` (v2, donchianPeriod 30 / tpR 3.0 / intervalMinutes=1440 → n=0). Every cell in both runs completed cleanly (`status=COMPLETED`) with `total_trades=0`, `net_profit=0`, over `window_days=923`.

No cell reached SIGNIFICANT_EDGE; the V11/V60 metrics table is intentionally omitted.

---

## 5. Root-cause analysis

Zero trades across a full ~640-bar daily window (2024-2026, a strongly-trending regime) is implausible for a maximally-permissive Donchian(20)/adx=0 breakout if the strategy could see bars. The investigation:

1. **Not an orchestrator interval-mapping bug** — `interval_name` flows to the JVM as a plain string; there is no 1d special-casing in the client.
2. **Raw 1d OHLCV exists** — `services/tick.py:1335` computes a daily-close buy-hold benchmark (`hedging_gate.evaluate(interval='1d')`) for every iteration and raises a retryable `hedging_gate_error` if the 1d series is missing. All 10 iterations completed with no such error ⇒ 1d bars were present and readable. Corroborated by the trading-engine data-plane note (BTC+ETH 1h/4h/1d back to 2017-08).
3. **Not a sweep-config gap** — v2 added `intervalMinutes=1440` (present in the params_snapshot of `b84c6028`) and still produced 0 trades.
4. **Verified cause:** the `feature_registry` has **zero features at 1d** (coverage 15m/1h/4h only). DCB is a spec-driven engine using `EngineContextHelpers` (ATR/rvol/regime). Without features at the traded interval, every bar's entry gate evaluates to no-signal ⇒ 0 entries.

---

## 6. Verdict & disposition

**INSUFFICIENT_DATA (data-plane plumbing gap), not NO_EDGE.** The DCB-1d region is untested, not falsified. It does not count toward DCB-family signal-exhaustion (persistence doctrine): the DCB breakout edge is real and proven live at ETH-1h.

The run terminates on **ARCHETYPE_EXHAUSTION** because, with the one genuinely-fresh cell data-blocked, no other researcher-actionable, in-data (15m/1h/4h), in-universe cell remains that is not a graveyard re-skin (ATR_MOM's untested cells reproduce a known bull-only failure and add DSR trial-tax; dual-archetype confirmation needs operator-only JVM code). This is the 2nd+ ARCHETYPE_EXHAUSTION in the 7-day window (prior fires 2026-07-12/13), so it is a hard terminal. It matches the platform state: the $0-cost alpha space is exhausted; new certifiable alpha is bound by money (Tardis skew) / time (free skew feed ~12mo) / decision.

---

## 7. Operator-owed

1. **DATA-PLANE (ingest repo):** compute 1d `feature_values` (ATR/rvol/regime family) for the core-5 (BTC/ETH/SOL/BNB/XRP). Raw 1d OHLCV already exists — only the 1d feature computation is missing. This unblocks the single untested proven-archetype × interval fresh cell (DCB-1d causal single-name → core-5 pool for n≥100 with a low DSR trial-count), the one clean PIT-safe cert path that is not a graveyard re-skin.
2. **DECISION:** fund Tardis skew data vs wait ~12mo for the free skew feed (new cert alpha is data/time-bound).
3. **DECISION (optional):** whether to build a dual-archetype-confirmation engine mode (JVM code, operator-only) — the only fresh *archetype* angle left in-data at 15m/1h/4h.

---

## Appendix: audit trail

- Hypothesis: `9d3ac8e7-447d-4a14-b61a-a38e8ef5df2e`
- DATA_WISHLIST (initial, later corrected): `8637b80c-ce56-409e-b35f-eae78ef98537`
- Correction (0-trade = config/plumbing, not missing raw data): `e71f8123-babe-41c5-a0d9-88209cc76b72`
- Withdrawn (premature) RUN_SUMMARY: `727130ba-d657-4b4e-b5ee-d8d7d0370c39`
- Final corrected RUN_SUMMARY: `9bd9fa08-3d71-489d-8e7b-923bb20e5bc2`
- DB papers: `BH-DCB-BTCUSDT-1D-9a086a38`, `BH-DCB-BTCUSDT-1D-9df8ebd5`
- Gates untouched; PIT-clean; no promote/deploy/live/git action taken.
