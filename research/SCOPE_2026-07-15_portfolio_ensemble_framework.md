# Portfolio / Risk-Parity Ensemble Framework — Scope (2026-07-15)

## Goal
Run DCB-1d + carry (+ future uncorrelated sleeves) as ONE combined risk-parity book whose **combined**
DSR clears the gate where no single sleeve does. **The ensemble becomes the graduation unit, not the
individual strategy** — this is the structural shift the whole hunt pointed to.

## Validated basis (why this is worth building)
DCB (directional trend) ⊥ carry (delta-neutral yield): correlation **+0.03, holds OOS** (H1 +0.06 / H2 −0.02).
Combined risk-parity **Sharpe 2.0 / DSR 0.97** full-sample (√N thesis: two uncorrelated Sharpe-1.4 sleeves
→ ~2.0). Each additional genuinely-uncorrelated sleeve raises Sharpe ~×√(N/(N−1)) and adds regime-robustness.
⚠️ Current 2-sleeve edge is **thin post-2022** (recent-regime Sharpe ~1.0–1.4) → design for ACCUMULATION,
not for the DCB+carry pair alone.

## Existing platform pieces (REUSE — do not rebuild)
- **`portfolio_weight` (V109)** — per-strategy weight multiplier, applied before vol-target in the sizing stack.
- **Signal Pool / House Book (V147, `POST /pool/evaluate`)** — the pool-candidate track for combining
  near-miss signals into a book; the closest existing home for an ensemble.
- **Vol-target overlay** (deployed-dormant) — per-strategy vol-targeting = the risk-parity primitive.
- **`account_strategy` allocation** — per-sleeve capital allocation.

## Design
1. **Each sleeve = its own live strategy** (DCB-1d, carry) with its own `account_strategy` row + allocation.
2. **Risk-parity weighting:** vol-target each sleeve to a common target, then weight by inverse realized vol
   (equal risk contribution). weight_i ∝ 1/vol_i over a trailing window, normalized.
3. **Correlation-aware aggregate risk:** uncorrelated sleeves ⇒ aggregate vol < sum ⇒ the book can carry more
   total risk for the same drawdown. Monitor pairwise correlations LIVE; if a pair's correlation rises
   (diversification breaking, e.g. in a crash), down-weight / de-risk.
4. **Rebalance cadence:** periodic (weekly/monthly) re-weighting as vols + correlations drift.
5. **Portfolio-level controls:** aggregate drawdown limit, per-sleeve kill-switch, correlation-breach alert.

## ★ The governance change this requires (the real unlock, operator-owned)
Today V11/V60 gate INDIVIDUAL strategies at DSR≥0.90. The ensemble insight says the COMBINED book is the
graduation unit. So add a **portfolio-admission gate** (NOT a loosening of the single-strategy gate — a
DIFFERENT gate for a different unit):

> A sleeve is admissible to the live book iff: (a) it has a real standalone edge (PF-CI-low>1 net-of-cost,
> even if its solo DSR < 0.90); (b) it is genuinely uncorrelated with the existing book (|corr| < ~0.3,
> verified OOS); AND (c) adding it RAISES the combined-book DSR. The combined book must clear DSR≥0.90.

This keeps the anti-overfit rigor (nothing gets in without real edge + real diversification + a combined-DSR
improvement) while unlocking the portfolio model. It is the honest way to deploy real-but-sub-DSR sleeves.

## Implementation path (incremental)
- **Phase 0 (decision):** operator adopts the ensemble-as-graduation-unit + the portfolio-admission gate above.
- **Phase 1:** deploy **DCB-1d as the 2nd live sleeve** beside carry (research→live), admitted under the
  portfolio gate (real edge + corr 0.03 with carry + raises combined DSR). Risk-parity weight via
  `portfolio_weight` + vol-target, set/rebalanced (manually at first).
- **Phase 2:** a `PortfolioAllocationService` that computes risk-parity weights across active sleeves and
  writes `portfolio_weight`, rebalanced on a schedule; live correlation monitoring + aggregate risk controls.
- **Phase 3:** a sleeve-accumulation pipeline — each new candidate validated for orthogonality + combined-DSR
  lift before admission. **This is the real lever: more uncorrelated sleeves = higher + more robust Sharpe.**

## Honest caveats
- **Current edge is modest post-2022** — the framework's value is the accumulation path, not DCB+carry alone
  (see the parallel recent-regime-decay diagnosis).
- **Correlations rise in tail events** — everything correlates in a crash; the diversification is not
  guaranteed when it's most needed. Portfolio drawdown controls + correlation monitoring are mandatory, not
  optional.
- **Capital-gated** — risk-parity across N sleeves needs enough capital to allocate to each meaningfully; at
  ~$191 it's structural-but-symbolic. Scales directly with capital.
- **Carry Sharpe is construction-sensitive** — the honest ~2.0 (not the funding-only 4.7) is what the book
  rides on.

## Bottom line
The ensemble is the first path this session that breaks the single-book Sharpe ceiling and plausibly clears
the gate. The build is: (1) a portfolio-admission governance decision, (2) DCB-1d live as sleeve #2, (3) a
risk-parity allocation service, (4) an ongoing hunt for uncorrelated sleeve #3+. The near-term payoff is
modest (thin recent edge); the strategic payoff is a genuine quant-firm portfolio model that gets stronger
with every sleeve added — which is exactly the endgame in the strategic-direction memo.
