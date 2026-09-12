# Live Risk-Parity Book — Concrete Build Scope (2026-07-15)

Deploy **DCB-1d + XS-momentum-neutral + carry** as one risk-parity sleeve set. Honest target: a genuinely
uncorrelated ~1.0–1.3 forward Sharpe book (NOT the front-loaded 2.0) — the value is the *machine + track
record*, not a home-run return. Every number here is regime-capped; size small.

## The three sleeves — status & what each needs

### Sleeve 1 — DCB-1d (directional trend) — the durable anchor (~1.4 Sharpe, regime-robust)
- Engine EXISTS + fixed this session (interval-aware risk cap, live on `86a5ff14`). Certified real, sub-DSR
  solo (0.27), durable pre/post-2022.
- NEEDS: a live `account_strategy` seed at interval=1d for the core coins (currently only research seeds
  exist, acct `99999999…002`); admission under the **portfolio gate** (not the solo DSR gate).

### Sleeve 2 — XS-momentum-neutral (dollar-neutral cross-sectional) — the real orthogonal add (~0.9 Sharpe)
- Dollar-neutral: long the strongest / short the weakest of the core-5/8 on ~20d momentum, ~5d rebalance,
  equal gross long = gross short (market-beta hedged → corr +0.01 with DCB, +0.02 with carry).
- ★Platform ALREADY has XS infrastructure (XS_MOM_14D V-seed, XS_BASIS V172, XS_IVRV V170) — this sleeve
  should map to / extend the existing XS engine, not a greenfield build. Verify the XS_MOM engine's
  lookback/rebalance/neutrality matches the validated (c) config; seed if a new variant is needed.
- NEEDS: confirm/seed the XS_MOM engine at the validated params; multi-coin backtest to reproduce the ~0.9
  Sharpe on the JVM (offline was dollar-neutral synthetic — re-validate on the real XS engine).

### Sleeve 3 — Carry (delta-neutral yield) — the free diversifier (~0.3 Sharpe now)
- LIVE. Post-2022 it's a near-zero-Sharpe cash-parker, NOT a return engine — keep it for its orthogonality +
  optionality if funding regimes return; it costs little.
- NEEDS: apply the **maker-OPEN post-only** fee optimization (~1.5%/yr saved — the separate carry-execution
  scope) — the one place carry can still add measurable value.

## The allocation layer — risk-parity (reuse existing primitives)
- **`portfolio_weight` (V109)** carries the per-sleeve weight; **vol-target overlay** (dormant) targets each
  sleeve to a common vol; risk-parity weight_i ∝ 1/vol_i over a trailing window, normalized.
- Build a **`PortfolioAllocationService`**: reads each active sleeve's trailing realized vol + pairwise
  correlations, computes risk-parity weights, writes `portfolio_weight`, rebalances weekly/monthly.
- Correlation-aware: uncorrelated sleeves ⇒ the book can run more gross risk for the same drawdown; monitor
  live pairwise correlation and de-risk on a breach (crash-correlation is the tail risk).

## The governance change (the actual unlock — operator decision)
Adopt the **portfolio-admission gate** (from `SCOPE_2026-07-15_portfolio_ensemble_framework.md`): a sleeve is
admissible iff (a) real standalone edge (PF-CI-low>1 net, even if solo DSR<0.90), (b) |corr|<~0.3 with the
live book (OOS-verified), (c) it RAISES combined-book DSR. This is NOT loosening V11/V60 — it's a *separate*
gate for a *different* unit (the portfolio). Without it, DCB-1d + XS-mom can't deploy (both sub-DSR solo).

## Build phases
- **Phase 0 — decision:** operator adopts the portfolio-admission gate + ensemble-as-graduation-unit.
- **Phase 1 — sleeves live:** seed DCB-1d live; confirm/seed XS_MOM at validated params + JVM-revalidate;
  carry already live (+ maker-OPEN). Admit each under the portfolio gate.
- **Phase 2 — allocation service:** `PortfolioAllocationService` (risk-parity weights → `portfolio_weight`,
  scheduled rebalance) + live correlation monitoring + aggregate drawdown control + per-sleeve kill-switch.
- **Phase 3 — accumulation pipeline:** every future candidate validated for orthogonality + combined-DSR lift
  before admission. This is the ongoing lever.

## Risk controls (mandatory, not optional)
- Aggregate portfolio drawdown limit (kills all sleeves).
- Per-sleeve kill-switch (retire a decayed sleeve — carry is the live example: demote, don't remove).
- Correlation-breach alert (diversification breaking → de-risk). **Everything correlates in a crash** — the
  book's diversification is weakest exactly when it's most needed; size for that.

## Honest caveats
- Forward book ~1.0–1.3 Sharpe, NOT gate-clearing on recent regime — deploy for the machine + track record,
  with modest expectations, at small size.
- **Capital-gated:** risk-parity across 3 sleeves needs enough capital to allocate meaningfully; at ~$191 it's
  structural-but-symbolic. Scales directly with capital — this is a "build the machine now, it pays as capital
  grows" move.
- XS-mom and carry both decay into 2025 — the book leans on DCB; the diversifiers reduce vol more than they
  add return in the current regime.

## Effort estimate
Sleeve seeding + XS re-validation: ~1–2 days. `PortfolioAllocationService` + risk controls: ~3–5 days.
Governance decision: operator. Total ~1 person-week of engineering once the governance call is made.
