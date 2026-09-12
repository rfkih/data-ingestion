# RESEARCH PLAN — Deribit Options-Skew (RR25) — pre-registration

- **Created:** 2026-06-19  | **Author:** scaffold (operator-directed)  | **Status:** PARKED-PENDING-HISTORY
- **Signal family:** Deribit option-surface skew (25-delta risk reversal) + IV level + vol term-structure
- **Track:** trading | **Readiness:** execution gated on feature history → ~September 2026
- **Why this exists:** the archetype-exhaustion data-scout's #1 unlock — an **orthogonal NON-price** signal,
  after price-action / XS / vol-dispersion were exhausted and the carry book was parked.
  Pre-registered NOW so the research is IC-first and not p-hacked when history matures.

## 1. The signal (shipped 2026-06-19, V187 + blackheart-ingest FeatureDefs)
Source `deribit_options` (live since 2026-06-15, hourly). Promoted to `feature_values`:
| feature | meaning |
|---|---|
| `btc/eth_rr25_skew_30d` | 25Δ risk reversal at ~30d = put-wing IV − call-wing IV. **>0 = market pays up for downside protection (fear/bearish positioning); <0 = call-bid (greed).** |
| `btc/eth_rr25_skew_zscore_30d` | 30d rolling z-score of the above (the regime-normalised signal to test) |
| `btc/eth_atm_iv_30d` | ATM implied vol level (the "crypto VIX") |
| `btc/eth_vol_term_spread` | 30d IV − near IV (forward-vol slope; contango/backwardation) |

**Populating now:** the level features (`rr25_skew_30d`, `atm_iv_30d`, `vol_term_spread`) since 2026-06-16.
**NOT yet:** `rr25_skew_zscore_30d` needs ~240h (~10 days) before it computes at all.

## 2. Pre-registered falsifiable hypotheses (test in this order; do NOT add new ones post-hoc)
RR25 measures *directional positioning demand*, not vol level — distinct from the 3 dead Deribit-vol
families (see §5). Two mutually-exclusive directional claims + secondary structure:

- **H1 (contrarian / capitulation-fade — PRIMARY):** an extreme **positive** `rr25_skew_zscore`
  (crowded downside-hedging) precedes **positive** forward returns (fear overdone → bounce).
  → Falsifiable: forward-return Spearman IC of `rr25_skew_zscore` is significantly **> 0**.
- **H2 (regime / momentum — ALTERNATIVE):** rising skew signals a deteriorating regime →
  **negative** forward returns (risk-off continues). → IC significantly **< 0**.
- **H3 (secondary, only if H1/H2 survive):** does `vol_term_spread` (forward-vol slope) or `atm_iv_30d`
  add orthogonal predictive power beyond RR25 alone?

If the IC is indistinguishable from 0 on every horizon → **signal is DEAD; pivot, do not spend a sweep.**

## 3. Test plan — STRICT cost-ladder order (CLAUDE.md / playbook §1.9)
1. **IC SCREEN FIRST (minutes, REQUIRED):** `POST /signal-screen` — Spearman IC + Newey-West t-stat +
   quantile spread of `btc_rr25_skew_zscore_30d` (then `eth_…`) vs forward returns at **1d and 4h** horizons.
   Journals a `SIGNAL_SCREEN` row for multiplicity. **This is the gate** — no engine, no sweep, until it passes.
2. **If IC promising on a horizon:** pre-register the surviving hypothesis (H1 or H2) formally, then build the
   `OptionsSkewEngine` (archetype `options_skew`; reuse the `VarianceRiskPremiumStrategyEngine` /
   `DvolVovStrategyEngine` pattern that already reads Deribit vol features) — **parameterised**: long/flat
   on `rr25_skew_zscore` crossing a sweepable threshold, with **direction as a swept param** so the sweep,
   not this plan, decides contrarian-vs-momentum. Then `/queue` → `/tick` → walk-forward → graduate (V11/V60).
3. **If IC dead:** journal NO_EDGE, pivot. Do not build the engine.

## 4. Readiness gate (why this is PARKED, not active)
- `rr25_skew_zscore_30d` doesn't compute until ~2026-06-26 (~10d of history).
- A credible IC needs ~60–90 non-overlapping obs at the test horizon. At a **1d** horizon that's
  ~60–90 daily points → **~mid-Aug to mid-Sept 2026**. (4h gives more obs sooner but the 30d-z signal is slow.)
- **Action until then: NONE — let history accrue.** Re-check feature depth ~2026-09-01, then run step-1 IC screen.

## 5. Caveats / priors (weigh honestly)
- **Deribit-vol is 0-for-3 on this platform:** DVOL-level, DVOL vol-of-vol (V171), and XS_IVRV all came back
  DEAD ([[alpha-pack-2026-06-11]]). RR25 skew is a *distinct* construct (directional positioning ≠ vol level),
  so it's a fair fresh test — but the prior is a Bayesian headwind; budget the DSR multiplicity accordingly.
- **No breadth:** options data is BTC/ETH only — a 2-name signal, not a portfolio.
- **Slow signal:** the 30d z-score window makes this low-frequency; expect few independent observations →
  watch effective-sample DSR, not raw n.
- **Engine deliberately NOT pre-built** — building it before the IC screen would repeat the premature-work
  trap (the carry-book lesson, 2026-06-19). It's a fast follow-on once the screen validates.

## 6. Status log
- 2026-06-19: data shipped (V187) + this pre-registration written. Engine deferred to post-IC-screen.
  Re-evaluate ~2026-09-01.
