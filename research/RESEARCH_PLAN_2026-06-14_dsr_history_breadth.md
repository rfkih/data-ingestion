# RESEARCH PLAN 2026-06-14 — Operator-directed DSR-history-breadth study

## Premise
Operator-directed study: find a strategy whose Deflated Sharpe improves via
EITHER (a) full 2017-->now BTC/ETH history (price-action only; DVOL/options
features do not predate 2021) OR (b) universe breadth / multi-coin pooling.
Researcher owns the hypothesis choice within the operator's envelope.

Standing operator-directed hypothesis (continued, resume branch 5):
  9795b726 ALT_CAP_FADE altcoin capitulation-fade family (6 alts, 1h).
Operator greenlight: aa818d60. Engine: CapitulationFadeStrategyEngine (V177).

## Constraints reaffirmed
- Universe in scope: BTC/ETH/SOL/BNB/XRP + the 4 ALT_CAP_FADE-only alts
  (ADA/AVAX/DOGE/SOL) for the cap-fade codes only.
- Intervals: 5m/15m/1h/4h/1d. Cap-fade is 1h (seeded).
- Research never mutates live; new strategies enabled=false simulated=true.
- 10%/yr bar + DSR>=0.95 + PF CI>1 + walk-forward ROBUST. Do NOT loosen V11/V60.
- Do NOT use override_review_gate (operator: clear reviewer gates via orchestrator).

## Established envelope (verified this session, do not re-discover)
- 6x ALT_CAP_FADE_{ADA,AVAX,BNB,DOGE,SOL,XRP} seeded, 1h, sim, runnable. No plumbing.
- XRP motivating iter da493632: ann_geom@90 17.36%/yr, PF 8.89 (CI low 1.56),
  win 88.9%, maxDD 10.9%, n=9, DSR=null (n too small). BEAR 7/9, NEUTRAL 2/9.
- Orchestrator runs ONE (code,symbol) per queue/walk-forward. No native pooling
  in a single backtest. Multi-coin pooling (operator lever b) is NOT a single
  orchestrator backtest -- each alt validates alone; events are structurally
  sparse (-15%/12h crash is rare). This is the key structural finding.

## Structural reality (the honest blocker)
- The standard graduation review hard-codes n_trades>=100 (BLOCKER) + trade-level
  DSR>=0.95 (BLOCKER). A rare-event cap-fade (n~9-40/coin) CANNOT clear it.
  Verified: XRP graduation review = REJECTED (2 blockers: n_trades_ample,
  dsr_threshold). This is correct, not a bug to game.
- The walk-forward has a LOW-FREQUENCY track (is_low_frequency, rate<52/yr) that
  validates on the OOS daily-equity curve: DSR>=0.95 (autocorr-adjusted n_eff,
  Lo 2002; per-obs Sharpe -- the 2026-06-09 annualization-bug fix is applied),
  fold-positive>=60%, return CV<=2.5, bear-coverage, >=8 trades, >=30 daily obs.
  This is the honest evaluator for a rare-event strategy and does NOT loosen V11.
- Non-override path: pool_candidate=True walk-forward legitimately skips the
  graduation-review gate (Signal Pool / House Book lane has its own gate at
  /pool/evaluate). This is the correct, no-override route for a sub-graduation
  candidate.

## Experiments (execution order)
1. XRP low-frequency walk-forward (pool_candidate, default params, 2022-01 start,
   6 folds). Honest OOS-equity DSR is the real test. RUNNING.
2. If budget: characterization backtests on the deepest/most-volatile alts to
   obtain motivating iterations -- SOL (2022 1h), DOGE (2020-01, most volatile),
   then their low-frequency walk-forwards. Each is a separate single-coin
   candidate (pooling is conceptual across the family, not a single backtest).
3. Lever (a): a full-2017-history BTC/ETH price-action attempt whose DSR benefits
   from regime diversity -- LOW prior (majors price-action is TAPPED) but the
   2017 depth is a genuinely new condition. Only if cap-fade time permits.

## Decision criteria
- Any candidate low-freq walk-forward = ROBUST  -> STOP and report (operator +
  specialist review owns graduation; pool admission is operator decision).
- INSUFFICIENT_EVIDENCE on the equity curve (likely for n~9, sparse OOS folds) =
  honest statistical-power limit; report it; the family is real-but-underpowered
  on the 5-name + alt universe -> the genuine unlock is universe breadth /
  more capitulation events, which needs either looser threshold (dilutes signal)
  or more alts plumbed into a pooled-backtest mechanism (engine/orchestrator work
  = operator-committed; STOP-and-report if needed).

## Deliverable
Table per candidate (strategy | symbol | events | honest DSR | PF CI | CAGR@90 |
WF verdict) + honest verdict on whether 2017-history or breadth lifts DSR toward
0.95, and whether any cap-fade candidate is graduation-ready.
