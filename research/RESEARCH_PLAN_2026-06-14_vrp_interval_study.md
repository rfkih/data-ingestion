# Research Plan — VRP Interval Study (operator-directed, bounded)

Date: 2026-06-14
Hypothesis: `a577411e-c250-4149-bdcc-cbbd3c1dda9a`
Kind: ALGO (existing VRP engine; parametric sweep on interval × thetaZ)
Mode: OPERATOR-DIRECTED, BOUNDED re-validation (NOT open-ended discovery)

## Premise

Operator asks: can VRP's Deflated Sharpe be improved via a longer span or other coins?
Established facts (from prod DB, do NOT rediscover):
- DVOL (Deribit implied-vol) exists for **BTCUSDT + ETHUSDT only**. "Other coins" beyond ETH is data-impossible without a new IV source.
- DVOL floor = 2021-03-24 (all intervals, both coins). With 30d warm-up, usable start ~2021-05. A longer span is data-impossible (BTC price → 2017 but DVOL does not).
- All COMPLETED VRP runs are 1d. Best **honest** DSR: VRP_BTC 1d = 0.053 (n=119, thetaZ=0) / 0.026 (n=100, thetaZ=0.5); VRP_ETH 1d = 0.174 (n=97, thetaZ=0) / 0.096 (n=103, thetaZ=0.5). All ≪ 0.95 gate.
- **UNTESTED lever = interval.** 1h DVOL ~45,753 rows, 4h DVOL ~11,441 rows per coin. No VRP has ever run at 4h or 1h.

## Constraints reaffirmed

- Universe: BTCUSDT, ETHUSDT only (VRP is DVOL-bound).
- Intervals under test: 4h, 1h (1d is the baseline, already run).
- Window: full DVOL span, ~2021-05-01 → latest (match existing 1d full-span 2021-07-01 → 2026-06-09).
- Prod live book untouched — research runs on `enabled=false, simulated=true` seeds (VRP_BTC/VRP_ETH research account_strategy rows confirmed present; interval is a queue-body field, not keyed to the seed row → no 412).
- Profitability bar 10%/yr + walk-forward ROBUST. Fixed V11/V60 gates — NOT loosened.
- The +20bps slippage gate was retired (V60); audit-only.

## Experiments

Four cells (each its own sweep so per-cell DSR is clean):

| # | strategy | symbol | interval | grid | iter budget |
|---|---|---|---|---|---|
| 1 | VRP_BTC | BTCUSDT | 4h | signalForm=ZSCORE × thetaZ{0.0, 0.5} | 2 |
| 2 | VRP_BTC | BTCUSDT | 1h | signalForm=ZSCORE × thetaZ{0.0, 0.5} | 2 |
| 3 | VRP_ETH | ETHUSDT | 4h | signalForm=ZSCORE × thetaZ{0.0, 0.5} | 2 |
| 4 | VRP_ETH | ETHUSDT | 1h | signalForm=ZSCORE × thetaZ{0.0, 0.5} | 2 |

Param schema mirrors the existing 1d runs (`signalForm:"ZSCORE"`, `thetaZ:{0.0,0.5}`) — the mature ZSCORE signal form, same axes already validated on 1d. Each cell crosses ≥2 dimensions when viewed against the 1d baseline (interval × thetaZ), satisfying the ≥3-dimension informativeness rule across the full study (symbol × interval × thetaZ).

Success criteria per cell (V11+V60 SIGNIFICANT_EDGE): n≥100, PF 95% CI lower>1.0, DSR≥0.95, annualized_geometric_return_pct_at_alloc_90≥10, walk-forward ROBUST.

## Honesty guards (the whole point of the task)

- The 1d DSR-annualization bug was corrected 2026-06-12. Verify per-cell `analysis.dsr` is the honest (non-annualization-inflated) value, and that `cumulative_trials` deflation is applied.
- Higher-frequency VRP may simply re-sample a slow vol-regime signal → autocorrelated near-duplicate trades → effective sample ≪ n. If raw n jumps but DSR does NOT improve proportionally, that is the diagnostic for an autocorrelated re-sample, and I report it plainly rather than treating high n as more evidence.
- Do NOT chase a passing number. If no cell clears the gate, the verdict is "VRP edge is genuinely weak and data-bound across span/coins/interval."

## Execution order

1. Plan review (mandatory gate).
2. Queue cell 1 (VRP_BTC 4h), drain. Then cells 2/3/4 similarly (separate queues for clean per-cell DSR).
3. For any cell reaching SIGNIFICANT_EDGE + 10%/yr → graduation path → walk-forward.
4. For cells at INSUFFICIENT_EVIDENCE → record honest DSR/PF/CAGR; no graduation.
5. Walk-forward the BEST cell per (symbol) regardless of gate, to get a WF verdict for the comparison table (operator explicitly asked for WF verdict per cell).

## Decision criteria for next session / terminal

- This is BOUNDED: exit and report once all four cells (BTC/ETH × 4h/1h) have honest DSR + WF verdict, OR on a hard blocker.
- Deliverable: comparison table (symbol | interval | trades | honest DSR | PF | CAGR@90 | WF verdict) with the 1d baseline rows included, plus a one-paragraph honest verdict on whether ANY lever lifts VRP DSR toward the gate.
- Do NOT pivot into unrelated hypotheses or new alpha families.
