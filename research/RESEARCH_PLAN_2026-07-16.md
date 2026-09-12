# Research Plan 2026-07-16 — three newly-unlocked surfaces (operator-directed)

## Premise
The 1d crypto single-strategy frontier terminaled ARCHETYPE_EXHAUSTION_2026-07-15 (correlation-synchronization wall: everything is BTC-beta, book-DSR capped ~0.27). Operator directs a FRESH DIRECTION on three surfaces unlocked by 2026-07-15/16 engineering that did NOT exist when 1d exhausted. Lockout bypassed via the sanctioned mechanism: a fresh HYPOTHESIS (gold `674cd8aa`, created 2026-07-16) strictly newer than the terminal-fire row → `bypass_available=true`. Standing goal unchanged: a strategy (or portfolio unit) clearing 10%/yr @alloc-90 AND walk-forward ROBUST.

## Constraints reaffirmed
- Research-mode ONLY (enabled=false, simulated=true). No deploy, no promote, no git push. Live book untouched.
- V11/V60/DSR/PSR gates frozen (DSR≥0.90, PF-CI-low>1.0, n≥100). No gate/annualization code change.
- Universe for crypto: BTC/ETH/SOL/XRP/BNB (+ ADA/DOGE/AVAX/LINK 1d verified for XS). XAUUSD is research-only (Binance-only stack has no live gold path — Phase-1 orthogonality validation, not a deploy candidate).
- Intervals: 1d (added for hedging/allocation track). Gold ~252 bars/yr → annualized Sharpe/return OVERSTATED ~1.20× by the 365-bar gate; trade PF/win-rate honest.
- Orchestrator change (journal edaa16b8): sweep_config allow_long/allow_short override, additive + crypto byte-identical, hot-patched onto the prod orchestrator. Enables gold LONG-ONLY.

## Experiments (priority order = operator priority)

### E1 — ★★ GOLD XAUUSD-1d LONG-ONLY donchian (HIGHEST VALUE). Hypothesis `674cd8aa`.
- Strategy anchor: DCB (symbol-agnostic resolution; XAUUSD travels in queue instrument).
- Direction: **allow_short=false** (sweep_config override). Gold long+short is DEAD (PF ~0.9).
- Grid: entryChannelPeriod {20,55} × turtleExitPeriod {0,20} × stopAtrMult {2.5,3.5} × tpR {4.0} × maxBarsHeld {360}. rvolMin=0, adxEntryMin=0. (turtleExitPeriod=0 → fixed-TP classic; >0 → opposite-channel Turtle exit.)
- Window: full history (start ~2004 to get ATR/donchian warmup past the 2001 start). Cost 8bps/side equiv (feeRate 0.00075).
- Success (V11): PF-CI-low > 1.0, n real. WARM if PF-CI-low>1.0 & point-PF>1.5 (offline says yes). DSR ~0.90 NOT expected solo (Sharpe ~0.6) — that's the portfolio unit's job.
- Branches: PF-CI-low>1.0 → confirmed sleeve-3, record P&L stream for the risk-parity combo (E4). point-PF≤1.0 net → offline edge dies on prod path (DEAD), journal + pivot.

### E2 — ★ donchian-55 + Turtle exit on crypto DCB-1d pool (BTC/ETH/SOL/XRP). Lead `bab42423`.
- Does entryChannelPeriod=55 + turtleExitPeriod=20 lift the pooled DCB-1d book DSR past the 0.271 ceiling (offline PF 1.76 > live 1.50)?
- Grid: entryChannelPeriod {20,55} × turtleExitPeriod {0,20} × stopAtrMult {2.5,3.5}, maxBarsHeld≥360, two-sided (crypto anchor default). Pool BTC/ETH/SOL/XRP full history, anti-padding (BNB excluded PF<1).
- Success: pooled DSR > 0.271 (ideally ≥0.90). WARM if DSR lifts materially even if <0.90.

### E3 — 8-coin cross-sectional momentum @1d (longshot). Hypothesis TBD.
- XS_MOM universe [BTC,ETH,SOL,BNB,XRP,ADA,DOGE,AVAX,LINK] interval 1d, lookback {14,20,30}, topQ/bottomQ 0.20, rebalanceBars 5 (weekly-ish; daily was cost-killed DSR 0.003), minSymbols 6.
- Honest prior: still BTC-beta, longshot. Wider universe is the only lift path. Let the gate decide.

### E4 — ★★ Risk-parity combined book (the graduation unit).
- IF E1 (gold) AND the crypto DCB-1d book both carry confirmed edges: measure the combined vol-parity book Sharpe/DSR/maxDD from the two P&L streams (offline is fine). Two ~uncorrelated sleeves (crypto Sharpe ~1.0, gold ~0.6, corr 0.10) combine to materially higher book Sharpe + lower DD. This is the portfolio-admission-gate evidence and the single most valuable output.

## Execution order
E1 (gold) → E2 (donchian-55 crypto pool) → E3 (XS 8-coin) → E4 (combine if E1+E2 both edge-positive). Wall-clock: fresh 8.5h run; wind-down at 8h.

## Decision criteria for next session
- Gold confirmed + crypto-55 pool lifted → E4 combined-book metrics = the deliverable; if combined DSR/return clears, that's the portfolio candidate.
- Gold DEAD on prod path → offline↔JVM divergence, investigate cost/annualization, park gold.
- All three DEAD → not archetype exhaustion (these are fresh families); journal outcomes, hand back the risk-parity residue.
