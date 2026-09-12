# Research Paper: CARRY_ML — 13-coin funding panel × 8h

**Author:** Claude (main session, local study — operator-directed "research the ML model, local PC only")
**Date:** 2026-07-10
**Strategy:** `CARRY_ML` (coin-selection overlay for the delta-neutral funding-carry book)
**Surface:** 13 USDT perps (BTC/ETH/SOL/BNB/XRP/ADA/AVAX/DOGE/LINK/NEAR/XLM/FET/ZEC) × 8h funding periods
**Type:** ML (LightGBM funding forecaster / coin ranker)
**Surface attempt:** v1 — ML (first ML attempt on the carry book; follows the 2026-07-04 rule-based conditioning study)
**Prior papers on this surface:** none (rule-based conditioning study 2026-07-04 lives in memory `project_carry_conditioning_validated_2026-07-04`)
**Terminal:** LOCAL_STUDY_COMPLETE
**Goal status:** NOT HIT — **NULL for deployment**, with a quantified opportunity ceiling
**Hypothesis:** local pre-registration in `.rtmp/carry_ml.py` header (written before first run; no orchestrator hypothesis row — study ran entirely on the local PC per operator constraint)
**Queue(s):** none (local; no research-JVM backtests consumed)

---

## TL;DR

Tested whether a pooled LightGBM model forecasting each coin's next-K-period funding (K = 24h/72h/168h)
can pick carry-book coins better than the trailing-mean heuristics the live carry engine already uses.
The model **has real forecast skill** — pooled rank-IC beats the 30-day trailing mean (MA90) in 12/14
walk-forward folds at the primary 72h horizon — but the skill is **economically worthless**: under a
cost-aware switching rule, an ORACLE with *perfect* foresight of realized future funding beats MA90 by
only **+0.4%/yr unlevered** at live taker costs, and only **+2.1%/yr at zero cost**. ML captures none of
it (−0.1%/yr vs MA90 at 12bp; positive only at exactly 0 cost). The carry coin-selection problem has
structurally no forecastable headroom: funding is so persistent that a trailing mean already extracts
nearly all of it, and the fast residual cannot pay the ~24bp swap cost. This independently confirms, from
a completely different angle, the 2026-07-04 finding that the live carry engine is near-optimal —
the constraint is capital, not signal.

---

## 1. Background

Session start state (memory-driven):
- DCB meta-labeling **thoroughly closed** 2026-07-04 (every feature set × label = no transferable signal).
- Hourly BTC/ETH direction/vol ML **closed** 2026-06-27 (no target/feature passes transferability; OOS coin-flip).
- Per-symbol microstructure features **data-gated**: re-verified this session — `liq_*` features have only
  16 days of history (2026-06-24 → 2026-07-10, ~382 hourly points × 5 symbols), `taker_*`/OI ~3 months
  (since 2026-04-14). The ~Aug-2026 revisit gate stands.
- The one designated remaining ML lever (2026-07-04 memo): *point the harness at a strategy that HAS edge —
  the carry book*. This study executes exactly that.

Operator constraint: run entirely on the local PC (no VPS compute). Honored: local `blackheart-train/.venv`
(LightGBM 4.6), CSVs previously exported 2026-07-04 (`.rtmp/mldata/funding.csv`, `fs_prices.csv`; 6 days
stale vs a 6.5-year panel — immaterial). Only VPS touch: one read-only `psql` count for the microstructure
gate check.

---

## 2. Hypothesis

**Mechanism:** The live carry engine selects coins by trailing funding (≈30d mean, `FUNDING_ENTER_THRESHOLD`
~3.3%/yr) with auto-exit. If per-coin funding over the next K periods is forecastable beyond a trailing mean
(mean-reversion at extremes, decay after spikes, cross-sectional rotation), an ML ranker could (a) pick
higher-carry coins and (b) avoid soon-to-flip coins, lifting net book yield.

**Pre-registration (in `.rtmp/carry_ml.py` docstring, written before the first run):**
- PRIMARY: K=9 (72h funding sum), pooled LGBM vs MA90 baseline.
- PASS BAR: ML beats MA90 on BOTH pooled rank-IC AND net top-3 Sharpe in a majority of folds.
- ROBUSTNESS: K=3, K=21; adversarial AUC per fold.

**Type:** ML (LightGBM regressor, pooled across 13 coins, no symbol identity feature).

---

## 3. Methodology

### 3.1 Data
- `funding.csv`: 86,348 rows, 8h funding rates, 13 coins, 2020-01-01 → 2026-07-04 (panel 7,206 × 13).
- `fs_prices.csv`: hourly closes, 8 coins, 2021-06 → 2026-07 (price features NaN-safe where absent).

### 3.2 Features (all causal at decision time t)
Funding: `f_now`, lags 1–3, trailing means (1d/3d/7d/30d), z-score-90, vol-90, percentile-180, sign-streak,
momentum (ma9−ma90). Price: 30d realized vol, 7d/30d momentum. Cross-sectional (stationarity fix from the
07-04 study): XS percentile ranks of `f_now`/`ma9`/`ma90`/`rv90` across coins per timestamp. 22 features.

### 3.3 Target & leak safety
y = sum of funding over t+1..t+K. Walk-forward: expanding train (starts 2020), 120-day test windows,
14 folds 2022-01 → 2026-07; embargo = K periods + 7 days between train end and test start; train rows
require fully realized targets.

### 3.4 Economic simulation (the part that decides)
Top-3 slot book (mirrors live max-pairs behavior), decisions each 8h, position earns next period's realized
funding. Costs: 12bp per enter and per exit (both legs, taker) = 24bp per swap — same model as the 07-04
conditioning study. Two decision rules:
1. **Naive top-3 + hysteresis (round 1):** rebalance toward top-ranked, keep held coins while rank ≤ 5.
2. **Cost-aware (round 2):** act only when predicted funding gain over the horizon clears the switch cost
   (enter if pred×K > cost; swap if Δpred×K > 2×cost; exit if pred×K < −cost). Applied IDENTICALLY to every
   predictor.
Predictors compared: ML, PERSIST (current funding), MA9 (3d mean), MA90 (30d mean ≈ live signal),
ORACLE (realized y — perfect foresight = upper bound of ANY forecaster's value).

---

## 4. Parameter Space Explored

| Axis | Values |
|---|---|
| Horizon K | 3 (24h), **9 (72h, primary)**, 21 (168h) |
| Model | LGBM (fixed params, 500 trees, lr .05, leaves 31) vs 3 heuristic baselines vs ORACLE |
| Decision rule | naive top-3+hysteresis; cost-aware hurdle |
| Cost (sensitivity) | 12 / 6 / 3 / 1 / 0 bp per toggle |

**Total model trials:** 3 (one LGBM per horizon; params never tuned — no mining tax beyond 3 trials).

---

## 5. Results

### 5.1 Forecast quality (walk-forward, 14 folds)

| K | pooled rank-IC: ML / PERSIST / MA9 / MA90 | ML > MA90 (IC) | XS-IC ML / MA90 |
|---|---|---|---|
| 3 | .694 / .652 / .659 / .456 | **14/14** | .532 / .420 |
| 9 (primary) | .637 / .601 / .660 / .492 | **12/14** | .503 / .484 |
| 21 | .543 / .548 / .640 / .502 | 7/14 | .436 / .526 |

ML forecast skill is real at short horizons. Note MA9 — a one-line 3-day mean — is the best K=9/K=21
forecaster; ML's edge over simple trailing means is marginal and shrinks with horizon. Feature importance:
funding vol/means/streak dominate; price features minor. Adversarial AUC ≈ 1.0 every fold (funding regime
is era-distinct — expected, info-only) yet IC transfers, because ranking survives level drift.

### 5.2 Round 1 — naive top-3 selection: even ORACLE loses

| picker (K=9) | net ann% | Sharpe | togg/8h |
|---|---|---|---|
| ML | −23.1% | −15.3 | 0.72 |
| PERSIST | −68.0% | −32.1 | 1.76 |
| MA90 | **+6.0%** | **+11.0** | 0.05 |
| ORACLE | −5.9% | −5.1 | 0.38 |

Perfect foresight of the next 72h of funding LOSES money under naive rebalancing: churn cost (24bp/swap)
exceeds the funding edge per period (~1–3bp). The binding constraint is the decision rule, not the forecast.

### 5.3 Round 2 — cost-aware switching (fair rule, identical for all)

| picker (K=9) | net ann% | gross% | Sharpe | maxDD% | togg/8h |
|---|---|---|---|---|---|
| ML | +4.9% | +5.8% | 10.7 | −3.9 | 0.020 |
| PERSIST | +3.7% | +5.2% | 9.0 | −0.4 | 0.033 |
| MA9 | +5.2% | +5.4% | 14.1 | −0.3 | 0.006 |
| MA90 (≈live) | +5.0% | +5.1% | 12.7 | −0.7 | 0.001 |
| **ORACLE** | **+5.4%** | +5.7% | 14.7 | −0.2 | 0.006 |

**ORACLE − MA90 = +0.4%/yr unlevered = the maximum value ANY forecaster could add** at the realistic
horizon under live costs. ML − MA90 = −0.1%/yr; ML beats MA90 net Sharpe in 6/11 folds (< majority bar
counted with the pre-registered criterion → **FAIL**). K=21: gap +0.7%/yr, ML 0/14. K=3: nominal gap
+3.8%/yr is a hurdle-scaling artifact (the same rule cripples MA90 at short K); vs the best baseline
(PERSIST) the gap is +0.3%/yr and ML trails PERSIST too.

### 5.4 Cost sensitivity (K=9) — would cheaper execution unlock it?

| cost bp/toggle | ML−MA90 | ORACLE−MA90 |
|---|---|---|
| 12 (live taker) | −0.1% | +0.4% |
| 6 | −1.3% | +1.3% |
| 3 | −1.5% | +1.5% |
| 1 | −1.5% | +1.8% |
| 0 | +0.2% | +2.1% |

**No.** Even free execution caps perfect foresight at +2.1%/yr over the trailing mean, and ML only stops
being negative at exactly zero cost. (ML−MA90 worsens at intermediate costs because lower hurdles let the
model churn on forecasts whose edge is smaller than its own noise.)

---

## 6–8. Graduation / Specialist / Walk-Forward

No graduation candidate — NULL result. (Walk-forward was inherent to the design: 14 folds, §5.)

---

## 9. Infrastructure Notes

- Round-1 naive-rule sim initially looked like an ML failure; the ORACLE row exposed it as a decision-rule
  failure — keep an oracle row in every future selection-overlay study (cheap and diagnostic).
- Microstructure gate re-verified on VPS (read-only): `liq_*` 2026-06-24→07-10 only; `btc_taker_*`/OI
  2026-04-14→now. LIQ_FADE meta-label re-run stays gated ~Aug-2026+.
- Artifacts: `.rtmp/carry_ml.py` (harness), `.rtmp/carry_ml_econ2.py` (cost-aware sim),
  `.rtmp/carry_ml_cost_sens.py` (sensitivity), `.rtmp/mldata/oos_K{3,9,21}.csv` (stitched OOS predictions).

---

## 10. Methodology Compliance Audit

| Rule | Compliant? | Notes |
|---|---|---|
| Research-mode only — no live promotion | YES | read-only study; no prod change |
| Pre-registration before testing | YES | pass bar in script header before first run |
| Append-only durable evidence | YES | this paper + scripts + OOS CSVs |
| V11/V60 gates | N/A | no graduation candidate produced |
| Protected/live strategies untouched | YES | — |
| Local-PC-only compute (operator constraint) | YES | one read-only psql count on VPS only |
| Multi-testing honesty | YES | 3 model trials, fixed params, no grid |

---

## 11. Conclusions

1. **Funding is forecastable but the forecast is worthless for coin selection:** ML rank-IC beats the 30d
   trailing mean in 12/14 folds at 72h, yet adds −0.1%/yr net at live costs.
2. **The opportunity ceiling is measured, not guessed:** perfect foresight adds +0.4%/yr (live costs) to
   +2.1%/yr (zero cost) unlevered over the trailing mean — there is structurally almost nothing to win.
3. **The live carry engine's trailing-mean + threshold logic is confirmed near-optimal** from a second,
   independent angle (the 2026-07-04 rule-based study reached the same verdict via conditioning grids).
4. **Cheaper execution does not change the answer** — the ceiling stays ≤2.1%/yr even free.
5. **Implication for the research loop:** ML-on-carry is CLOSED alongside DCB meta-labeling and hourly
   direction/vol ML. The remaining ML lever is unchanged: per-symbol microstructure features, data-gated
   ~Aug-2026. The carry book's binding constraint remains capital (operator-side), not signal.

---

## 12. Data Wishlist

| Priority | Item | Blocker type |
|---|---|---|
| 1 | LIQ_FADE / taker / OI history accrual (auto; recheck ~Aug-2026, needs a big BTC-down day for n≥100 liq events) | time |
| 2 | None — no execution-cost improvement can unlock this surface (§5.4) | — |

---

## 13. Appendix — Audit Trail

| Item | ID |
|---|---|
| Hypothesis | `.rtmp/carry_ml.py` docstring (local pre-registration, 2026-07-10) |
| Harness / sims | `.rtmp/carry_ml.py`, `.rtmp/carry_ml_econ2.py`, `.rtmp/carry_ml_cost_sens.py` |
| OOS predictions | `.rtmp/mldata/oos_K3.csv`, `oos_K9.csv`, `oos_K21.csv` |
| Prior related studies | memory `project_carry_conditioning_validated_2026-07-04`, `project_pooled_meta_label_orthogonal_2026-07-04`, `project_btc_ml_model_research_2026-06-27` |
| DB registration | none (local study; no orchestrator run) |

---
*Local study — no orchestrator queue consumed; VPS untouched except one read-only count query.*
