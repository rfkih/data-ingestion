# RESEARCH PLAN — DCB ETHUSDT 4h FULL-HISTORY re-validation (window-bug correction)

Date: 2026-06-14
Hypothesis: `ce6235ca-5e6c-4286-becc-51d46229fb6e` (ACTIVE)
Supersedes: hypothesis `01f66330` / queue `a0375917` (FALSIFIED on truncated window)
Operator-directed lifecycle-support task.

## Motivation / root cause
The prior Phase-1 confirmatory sweep on DCB ETHUSDT 4h concluded INSUFFICIENT_EVIDENCE
but was REPORTED as "full history 2017-08 -> 2026". The sweep_config carried
`backtest_window=null`, so the orchestrator forwarded the JVM default floor
`startTime=2024-01-01T00:00:00`. VERIFIED:
- `backtest_run 32661e7b` (last run of queue a0375917): `start_time=2024-01-01 00:00:00`,
  `total_trades=9`, ~2.4 yr window.
- ETHUSDT 4h `market_data`: min `start_time=2017-08-17 04:00`, max `2026-06-14 04:00`,
  count `19,323` bars — the genuine ~8.85 yr exists; ~6.4 yr (2017-08 -> 2024-01) was UNUSED.

Orchestrator code path verified (read-only):
- `api/queue.py` `BacktestWindow.start_time` (ISO-8601, required when object present).
- `services/tick.py:712` `window_cfg = sweep_config.get("backtest_window") or {}`;
  line 713 `start_time_override = window_cfg.get("start_time")`;
  `_build_submit_payload` line 302 `start_time = start_time_override or "2024-01-01T00:00:00"`,
  line 308 placed into JVM payload as `"startTime"`.
=> Setting `sweep_config.backtest_window.start_time="2017-08-17T00:00:00"` overrides the floor.

## Hypothesis (falsifiable)
On the GENUINE full window, the let-trends-run DCB 4h grid yields materially more trades
than the truncated 9. If the best cell reaches n>=100 AND PF 95% CI_lo>1.0 AND DSR>=0.95
AND `annualized_geometric_return_pct_at_alloc_90 >= 10`, it is a graduation candidate.
Otherwise the honest verdict (INSUFFICIENT_EVIDENCE with the REAL trade count, or NO_EDGE)
closes the question. Prior expectation is honestly NEGATIVE (DCB-4h 0-for-4 historically).

## Grid (IDENTICAL to prior, 12 cells, >= 3 dimensions)
- `tpR` ∈ {3.0, 4.0, 5.0}
- `adxEntryMin` ∈ {20, 24}
- `breakEvenR` ∈ {0.5, 1.0}
- fixed: `rvolMin=1.3`, `stopAtrMult=3.0`, `maxBarsHeld=24`

## Window override (THE FIX)
`sweep_config.backtest_window.start_time = "2017-08-17T00:00:00"`.
end_time left to tick-time "yesterday UTC midnight" derivation.

## Critical verification step (do NOT skip)
After iter 1 completes, query `backtest_run` for the new run's `start_time`. It MUST be
~2017-08, NOT 2024-01-01. If it still shows 2024, STOP, diagnose, fix before continuing.
No verdict on a 2024-start window will be reported.

## Gates (FROZEN — V11 + V60)
n>=100, PF 95% CI_lo>1.0, DSR>=0.95, `annualized_geometric_return_pct_at_alloc_90>=10`,
walk-forward ROBUST. No loosening, no override flags.

## Decision branches
- SIGNIFICANT_EDGE cell clears all gates -> STOP at graduation-review checkpoint
  (cannot spawn reviewer here); return motivating_iteration_id + honest metrics.
- INSUFFICIENT_EVIDENCE / NO_EDGE / MARGINAL -> report terminal + REAL full-window
  trade count + metrics; if n genuinely < 100 say so explicitly with the actual number.

## Hard guardrails
RESEARCH MODE ONLY. No account_strategy mutation, no deploy, no live touch.
No gate loosening / override. Honest master engine only. Journal everything.
