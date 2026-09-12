# RESEARCH PLAN 2026-06-18 — XS_MOM cross-sectional momentum on the 13-coin universe

## Premise
Prior runs terminated ARCHETYPE_EXHAUSTION (2026-06-03, 2026-06-14) with the binding
constraint explicitly logged as **BREADTH** on the old 5/8-coin universe. The operator
expanded the backtest universe to **13 coins with deep 1h/4h/1d history across the
2018 bear / 2021 bull / 2022 bear** regimes:
BTC ETH SOL BNB XRP ADA DOGE AVAX FET LINK NEAR XLM ZEC.

The cross-sectional rank engine (V144/V145, `CrossSectionalRankEngine`) EXISTS and has
run before, but only on the 5-name universe (hypothesis 79e37d06, ~20 iters, ALL
INSUFFICIENT_EVIDENCE — e.g. iter d8d3df6c, quarterly PnL wildly mixed). At 5 names a
0.25 quantile is ~1 name per leg = a single-name bet, not a dispersion portfolio.
At 13 names the top/bottom quartiles hold ~3 names each — the first genuine attack on
the breadth constraint. The universe is passed via `sweep_config.universe`
(tick.py:770), so NO JVM change is needed.

Standing hypothesis (pre-registered): **f449de21-c9d8-4d3b-a8d5-3f1821245f48**.

## Constraints reaffirmed
- Universe: 13 coins all in-scope for 1h backtest (operator-verified market_data today).
- Interval: 1h (matches the rebalance cadence; n is large — ~360 trades/quarter observed).
- Research-mode only; prod untouchable; ROBUST is a gate not a trigger.
- Gates fixed: V11 (n>=100, PF 95%CI-lo>1.0, DSR>=0.90, PSR>=0.90) + V60 (ann_geom_at_alloc_90>=10%/yr).
- Taker-only CLOSE path; must survive >=30bps. XS rebalance turnover is the key cost risk —
  watch slippage_haircut_pnl as a sanity signal (audit-only, not a gate).

## Experiment 1 — XS_MOM 13-coin confirmatory grid (kind=ALGO)
- **Strategy/surface**: XS_MOM, interval 1h, dispatch anchor BTCUSDT, universe = 13 coins.
- **Hypothesis**: breadth (13 vs 5 names) turns the quartile legs into real dispersion
  portfolios; a momentum OR reversion tilt clears PF 95%CI-lo>1.0 + n>=100 + >=10%/yr.
- **Grid (8 cells, 3 axes — satisfies >=3-dimension rule)**:
  - `direction`: ["momentum", "reversion"]
  - `lookbackBars`: ["168", "336"]   (7-day, 14-day relative-strength windows)
  - `rebalanceBars`: ["24", "48"]     (daily, 2-day rotation)
  - fixed: `topQuantile=0.25`, `bottomQuantile=0.25`, `minSymbols=8`
- **Iter budget**: 8 (full grid).
- **Success criteria**: any cell reaching statistical_verdict=SIGNIFICANT_EDGE with the
  V11+V60 gates → graduation review → walk-forward.
- **Branches**:
  - GRADUATE → step 9 (paired-delta N/A for ALGO) → graduation review → Path C specialists.
  - PIVOT (all INSUFFICIENT/NO_EDGE) → regime-analysis (>=5 iters) → STRATEGY_OUTCOME.
    If regime-analysis is_promising with a regime model → regime-gated retry (step 8.5).
    Else pivot to next archetype (see "next session").
  - If the engine excludes too many symbols / universe-too-thin warnings dominate →
    DATA_WISHLIST (market_data gap on a new coin), does NOT count toward exhaustion.

## Execution order
1. Plan review (this plan) → auto-checklist.
2. POST /queue (8-cell grid, universe in sweep_config).
3. POST /tick/drain (max_iters 12, max_wall_clock_s 1500) — repeat until terminal.
4. Branch on terminal_action per above.

## Decision criteria for next session
- If XS_MOM 13-coin GRADUATES → walk-forward; ROBUST + >=10%/yr = GOAL_HIT.
- If XS_MOM 13-coin PIVOTs → the breadth lever is tested for price-momentum XS.
  Next archetype candidates that ALSO exploit the new breadth WITHOUT re-chasing
  graveyard families:
  (a) XS_MOM reversion-only at shorter lookback (mean-reversion cross-section is
      distinct from momentum) if the grid hints reversion > momentum but sub-gate;
  (b) DCB / MMR single-name on the NEW deep-history coins (FET/LINK/NEAR/XLM/ZEC)
      — but those have NO account_strategy seed except via ALT_CAP_FADE_* (graveyard),
      so that path is a DATA_WISHLIST (operator must seed account_strategy rows).
- A second genuine no-credible-archetype diagnosis in the 7d window → ARCHETYPE_EXHAUSTION.
