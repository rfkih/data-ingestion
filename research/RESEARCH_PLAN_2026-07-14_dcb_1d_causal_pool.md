# RESEARCH PLAN 2026-07-14 — DCB causal Donchian-breakout at the 1d interval (fresh region)

**Hypothesis journal_id:** `9d3ac8e7-447d-4a14-b61a-a38e8ef5df2e`
**Archetype/family:** DCB_1D (Donchian-channel breakout, daily cadence)
**Kind:** ALGO (pure price, PIT-clean, NO ML sleeve)
**Goal (fixed):** `annualized_geometric_return_pct_at_alloc_90 >= 10` AND walk-forward `stability_verdict=ROBUST`.

## Why this region is genuinely fresh (post-graveyard scan)

Scanned: `/agent/state`, 200 most-recent iterations, 120 journal rows, FALSIFIED graveyard (16 rows), and the 30 filesystem research papers. Findings:

- The proven-archetype × core-universe × {5m,15m,1h,4h} surface is worked out:
  - DCB-ETH-1h: **live + walk-forward ROBUST** (graduated).
  - DCB-ETH-4h: **FALSIFIED** — the confirmatory let-trends-run run produced PF 1.94, n=131, PF-CI-low 1.263, `annualized_geom_return_pct_at_alloc_90 = 53.4%` (all pass) but ended INSUFFICIENT_EVIDENCE purely on **DSR deflated by cumulative_trials=172** (the ETH-4h surface trial-tax) + walk-forward never cleared.
  - DCB-15m: gross-dead. DCB-BTC/BNB-4h: tried (BTC operator-revoked).
  - TPB: sub-DSR / frequency-starved. ATR_MOM: bull-only, gate-rejected. MRO/MMR/VWAP_MR: mean-reversion gross-dead.
- **The 1d interval has ZERO prior iterations for ANY archetype** (journal + iteration scan confirm). 1d was added to `VALID_INTERVAL_NAMES` for the hedging/allocation track and never used for directional research.
- The pooled DCB book (`DCB_POOL`) only ever ran at **4h**, and its SIGNIFICANT_EDGE cert was **look-ahead-contaminated** (the `s1._ml_signal_name=regime_eth_v2` future-vintage ML gate — wound down per memory 2026-07-13).

## Mechanism

A Donchian-channel breakout (donchianPeriod ~20) at the **daily** cadence is a slow multi-week trend-follower: fewer, larger, higher-conviction breaks; far lower turnover → lower cost drag → better net survival than the 4h variant. Same let-trends-run exit profile (tpR 3-5, breakEvenR 1.0, stopAtrMult ~3.0) that makes DCB the proven ETH-1h winner. NO ML gate — cannot inherit the 4h-pool look-ahead.

## Not a re-skin (novelty clause vs dead-ends + FALSIFIED graveyard)

- vs **DCB-ETH-4h confirmatory FALSIFIED**: different interval → different bar statistics, breakout frequency, and DSR trial-count. The 1d surface has **zero prior trials** → minimal deflation trial-tax, which is the exact axis (cumulative_trials=172) that sank ETH-4h.
- vs **DCB_POOL 4h contaminated cert**: this design carries **no ML sleeve at all**, so it cannot inherit `regime_eth_v2` look-ahead.
- vs **XS_MOM_14D / XS-BASIS / XS_IVRV / funding-LSR FALSIFIED**: those are cross-sectional rank-spreads; this is single-name directional breakout — orthogonal.
- vs the session dead-end `MR_MAKER_SCALP` (VWAP_MR-ETH-15m gross-dead): different family (trend-breakout vs mean-reversion), different interval (1d vs 15m), no maker fill dependence.

## Design — staged, bounded, cost-netted

**STAGE 1 (this iteration): single-name net-of-cost probe, DCB-BTCUSDT-1d.**
BTC has the longest, cleanest daily history — cheapest way to confirm 1d data depth AND measure per-coin gross+net edge before the heavier pool run.

- strategy_code: `DCB`, interval_name: `1d`, instrument: `BTCUSDT`
- Window: full history (JVM default reaches back to ~2017/2021; iteration metrics will report actual span).
- Grid (bounded, ≤ 8 cells → low trial-tax):
  - `donchianPeriod`: {20, 30}
  - `tpR`: {3.0, 5.0}
  - `breakEvenR`: {1.0}
  - `stopAtrMult`: {3.0}
  - `adxEntryMin`: {0, 20}
  - `rvolMin`: {1.0}
  - `maxBarsHeld`: {60}
  - entryMode: BREAKOUT
- `n_trials` = 8 (full grid), `strategy=grid`, `seed=42`.

**Dimensions traversed (≥3):** entry (donchianPeriod, adxEntryMin), exit (tpR, breakEvenR, stopAtrMult), interval (1d — the fresh axis). ✓ hard-rule 7.

### Expected outcome & warmth grading (honest priors)

- Single-name 1d over ~5.5y fires ~30-50 trades → most likely **n < 100 → COLD_POWER** (a power problem, not a signal problem — persistence doctrine). Point PF > 1.0 with n<100 ⇒ push a COLD_POWER lead with `next_axis = pool core-5 at 1d` to reach n≥100.
- If point PF ≤ 1.0 after cost on BTC (the strongest trender) → **DEAD** for the family — daily breakout carries no net edge; journal and pivot.
- If per-coin PF-CI-low > 1.0 already at n<100 → **WARM**, next_axis = pool.

**STAGE 2 (next iteration, gated on Stage-1 point PF>1):** DCB_POOL causal book, sleeves = BTC/ETH/SOL/BNB/XRP all at 1d, per-sleeve `s{N}.` schema, **no `_ml_signal_name`**, low trial-count → pool n≥100 with a clean DSR. This is the certification path.

## Gates (unchanged — no threshold-shopping)

n ≥ 100, PF 95% CI lower > 1.0, DSR ≥ 0.90, `annualized_geom_return_pct_at_alloc_90 ≥ 10`, walk-forward ROBUST. The retired +20bps slippage gate is NOT enforced. Honest cost-netted verdicts only.

## Decision branches

- Stage-1 COLD_POWER (PF>1, n<100) → queue Stage-2 pool at 1d.
- Stage-1 WARM → queue Stage-2 pool (higher priority).
- Stage-1 DEAD (PF≤1 net on BTC) → family DEAD on the entry+exit+interval dims; if pooling also can't help (BTC is the best trender), pivot / diagnose exhaustion honestly.
- Stage-2 GRADUATE → graduation review → Path-C specialist checkpoint → walk-forward → GOAL_HIT if ROBUST & ann≥10.
