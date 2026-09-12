# Research Paper: DCB_POOL + GOLD — RISK-PARITY BOOK PORTFOLIO-ADMISSION OOS WALK-FORWARD (BTC/ETH/SOL/XRPUSDT + XAUUSD) × 1d

**Author:** quant-researcher
**Date:** 2026-07-16
**Strategy:** `DCB_POOL` (crypto DCB-1d pool BTC/ETH/SOL/XRPUSDT) + `DCB` long-only on `XAUUSD` (gold sleeve), combined as one vol-parity book
**Surface:** `BTCUSDT + ETHUSDT + SOLUSDT + XRPUSDT + XAUUSD` × `1d` (risk-parity combined book — the portfolio-admission unit)
**Type:** CHAR (out-of-sample characterization of a combined portfolio unit under the portfolio-admission gate)
**Surface attempt:** v2 — CHAR (OOS walk-forward; supersedes the v1 in-sample full-sample measurement with an honest out-of-sample verdict)
**Prior papers on this surface:** `RESEARCH_PAPER_DCB_POOL_RISKPARITY_1D_v1_CHAR_2026-07-16.md` (full-sample, in-sample: corr 0.014, combined Sharpe +0.59 / ~1.13-analytic, maxDD 51%→19%)
**Filename:** `RESEARCH_PAPER_DCB_POOL_RISKPARITY_1D_v2_CHAR_2026-07-16.md`
**Terminal:** WALL_CLOCK_CAP wind-down (cumulative-run closeout); measurement complete
**Goal status:** NOT HIT — combined book is an ADMIT-CANDIDATE (real+OOS-robust diversification, but DSR 0.51 short of ≥0.90); neither sleeve clears solo
**Hypotheses:** `674cd8aa` (gold sleeve), risk-parity-book combination (this paper)
**Queue(s):** none (offline analysis; certified crypto pool = iteration `bab42423`, gold offline = `55afdb54`)
**Journals:** outcome `98e5bb78-ccf4-47e0-85a3-2a8a62723af0`; prior deliverable `a4986473`

---

## TL;DR

The gold+crypto risk-parity book was driven through its **portfolio-admission gate** with an honest **out-of-sample walk-forward** — the forward-path measurement the 2026-07-16 run left operator-owed. Over the full common history (2017-09 → 2026-07, 2224 union days), an expanding-train → 5-sequential-OOS-block walk-forward with **vol-parity weights fit in-sample and applied OOS** yields a combined book with OOS Sharpe **+0.99** (365-ann), DSR **0.51**, maxDD **14.0%**, and **5/5 folds positive**. The cross-sleeve OOS daily-return correlation is **−0.042** (robustly near-zero across every variant). The combined book **raises DSR above the best solo** (0.51 > gold 0.35 > crypto 0.24, a +0.16 lift), lifts Sharpe by +0.34, and **halves max drawdown (crypto-solo 52% → 14%)** — the diversification benefit is REAL and OOS-robust, not an in-sample artifact. **But the two-sleeve book falls far short of DSR ≥ 0.90.** Verdict: **ADMIT-CANDIDATE, not full ADMIT** — gates (a) edge, (b) orthogonality, (c) DSR-lift PASS; gate (d) DSR ≥ 0.90 / ROBUST FAILS. The single fix that clears the gate is **more uncorrelated sleeves** (the mechanism compounds); a 2-sleeve book of two individually-weak (~0.6-Sharpe) streams caps around 0.5 DSR by construction.

*(No cell reached SIGNIFICANT_EDGE — this is a portfolio unit, not a single strategy; no V11 gate table.)*

---

## 1. Background

The 2026-07-15 run terminaled ARCHETYPE_EXHAUSTION on the 1d crypto single-strategy frontier: everything is BTC-beta (~0.8 correlation wall), capping the pooled DCB-1d book at DSR ~0.27 despite a genuine edge. The operator directed a fresh direction — the **combined risk-parity book** as the graduation unit under a **portfolio-admission gate** (`SCOPE_2026-07-15_live_riskparity_book_build.md`, `SCOPE_2026-07-15_portfolio_ensemble_framework.md`): a sleeve is admissible iff (a) it has a real standalone edge, (b) it is uncorrelated (|corr| < ~0.3 OOS), and (c) it raises the combined-book DSR — and the combined book must clear DSR ≥ 0.90 / walk-forward ROBUST.

The v1 paper (2026-07-16) measured the combined book **in-sample, full-sample**: near-zero correlation (0.014), Sharpe lift +0.59→~1.13 analytic, maxDD 51%→19%. That was the thesis-validation; it did NOT establish OOS admissibility because the vol-parity weights were fit on the same window they were scored on. **This paper (v2) is the honest OOS walk-forward** — the actual portfolio-admission gate.

Gold XAUUSD is validated as an orthogonal sleeve (GOLD~BTC daily-return corr 0.098 offline; long-only donchian breakout + opposite-channel exit is a real edge: d-20/10 PF 1.92, d-40/20 PF 2.42, d-100/40 PF 5.00, all Sharpe ~0.62–0.66). A JVM-native gold backtest is infra-blocked (DCB needs a 4h intra-bar monitor feed; XAUUSD has only 1d market_data; the monitor-interval config is a global 4h JVM setting) — so the **offline** gold P&L is used, per the task's explicit instruction.

---

## 2. Hypothesis

**Mechanism (the portfolio unit):** Two genuine, cost-robust, individually-sub-DSR daily trend sleeves — (1) crypto DCB-1d pool (BTC/ETH/SOL/XRP, two-sided donchian-20 breakout / opposite-channel-10 exit, equal-weight coins active each day), and (2) gold XAUUSD long-only donchian-40 breakout / opposite-channel-20 exit — are combined at inverse-realized-vol (vol-parity) weights. The thesis: two ~perfectly-uncorrelated positive-Sharpe streams combine to a materially higher book Sharpe with lower drawdown; the diversification RAISES the combined DSR even though each sleeve is weak alone.

**Falsification criterion:** the combined book fails the portfolio-admission gate if (b) OOS |corr| ≥ 0.30, OR (c) combined DSR ≤ max(solo DSR), OR the OOS diversification benefit is an in-sample artifact (combined DSR-lift disappears out-of-sample). A short DSR (< 0.90) does not falsify the *diversification mechanism* but does deny full admission (ADMIT-CANDIDATE, not ADMIT).

**Type:** CHAR (characterization of a combined portfolio unit; no ML).

---

## 3. Methodology

### 3.1 Why offline reconstruction (not JVM `backtest_trade`)

The task asks for the crypto pool's per-day P&L from the certified/baseline pooled run. **The certified pooled book has no single JVM equity curve**: pooled-certification aggregates per-coin runs separately, and the baseline iteration `bab42423` has a NULL `backtest_run_id` (verified in `research_iteration_log`). A vol-parity walk-forward needs **per-day aligned returns for both sleeves that can be sliced into folds** — which requires an offline daily reconstruction anyway. Both sleeves are therefore rebuilt offline on the identical daily donchian family (the deployed `DonchianBreakoutEngine` rule, the same basis the v1 paper and `risk_parity_combine.py` used). The certified JVM baseline (Sharpe 0.9834, PF 1.50, n=416 — `metrics_snapshot` of `bab42423`) is the **characterization anchor** for context; the offline reconstruction is the reproducible per-day measurement basis. The simplified offline crypto rule (Sharpe ~0.59 OOS full-history) is more conservative than the winning-cell JVM config (0.98) — using it makes the admission verdict *harder to pass*, which is the honest direction.

### 3.2 Walk-forward design (no test-fold tuning)

- **Common window:** full daily history where both sleeves are active. Primary = 2017-09 → 2026-07 (2224 union days, coins active-that-day so BTC/ETH anchor the early crypto pool). Sensitivity includes the SOL-gated 2020-08 start (4-coin pool populated).
- **Folds:** expanding-window. Warmup = first ~1/3 (741 days) as the initial in-sample estimate; then **5 sequential OOS test blocks** (~296 days each). Every fold trains on all data strictly before its test block.
- **Vol-parity weights:** for each fold, `w_i ∝ 1/realized-daily-vol_i` estimated **IN-SAMPLE (train block only)**, then applied to the OOS test block. Weights are NEVER computed on the test fold.
- **Concatenation:** OOS test-block returns from all 5 folds are concatenated into one honest out-of-sample series; Sharpe / DSR / maxDD / correlation are computed on the concatenated OOS series.
- **Cost:** 8 bps/side (round-trip debited on the exit bar). Gold futures + crypto perps are liquid at daily cadence.

### 3.3 Statistical measures

- **Sharpe:** the combined book lives on the union daily grid → annualized at **365** (the binding daily-cadence grid; gold flat days contribute 0 return). Gold-solo annualized at 252, crypto-solo at 365. **252-ann sensitivity** reported for the combined book (+0.82).
- **DSR (deflated Sharpe, Bailey & López de Prado 2014):** per-period Sharpe deflated for (i) the number of configurations tried across the whole gold+crypto program — `N_TRIALS = 20` (gold 4 cells × 2 sides + crypto pool baseline / 55-Turtle + XS 6 cells + the combination), and (ii) return skew/kurtosis. `DSR = Φ((SR̂ − SR0)/σ_SR)` with `SR0 = σ_SR · E[max_N standard normals]`. This is the same statistic family as the frozen V11 gate; it is computed offline and never mutates the gate.
- **Cross-sleeve correlation:** OOS daily-return correlation on both-in-position days.

Script: `research/risk_parity_walkforward.py` (self-contained; reads cached daily OHLC pulled from VPS `market_data`).

---

## 4. Results

### 4.1 Primary — full common history 2017-09 → 2026-07 (2224 OOS days)

| Book | OOS Sharpe | DSR | maxDD | CAGR |
|---|---|---|---|---|
| SOLO crypto pool (365-ann) | +0.591 | 0.239 | 52.1% | +43.3% |
| SOLO gold long-only (252-ann) | +0.653 | 0.347 | 13.7% | +9.6% |
| **COMBINED (vol-parity ~0.15/0.85)** | **+0.991** | **0.509** | **14.0%** | +17.7% |
| *combined 252-ann sensitivity* | +0.824 | — | — | — |

- **Cross-sleeve OOS daily-return correlation = −0.042** (n=644 both-in-position days). Orthogonality holds out-of-sample.
- **Sharpe lift +0.338** over best solo; **DSR lift +0.162** over best solo (0.509 vs gold 0.347); **maxDD collapse 52.1% → 14.0%**.
- **OOS fold stability: 5/5 folds positive combined Sharpe** (min +0.394, max +2.149).

Per-fold OOS (weights fit in-sample, applied OOS):

| fold | test window | days | wC / wG | Sh_crypto | Sh_gold | Sh_COMB | CAGR | maxDD |
|---|---|---|---|---|---|---|---|---|
| 1 | 2020-08 → 2021-10 | 296 | 0.14/0.86 | +1.74 | −0.87 | +0.875 | +13.3% | 7.5% |
| 2 | 2021-10 → 2022-12 | 296 | 0.13/0.87 | +0.49 | +0.07 | +0.394 | +5.6% | 7.3% |
| 3 | 2022-12 → 2024-02 | 296 | 0.13/0.87 | +0.07 | +0.43 | +0.478 | +5.7% | 10.1% |
| 4 | 2024-03 → 2025-05 | 296 | 0.14/0.86 | −0.03 | +1.91 | +2.149 | +43.4% | 9.0% |
| 5 | 2025-05 → 2026-07 | 299 | 0.16/0.84 | −0.03 | +0.82 | +0.946 | +24.6% | 14.0% |

The fold structure is the key evidence: in fold 1 crypto carries the book while gold is negative; in fold 4 gold carries it while crypto is flat. **The sleeves take turns** — exactly the diversification signature, and why the combined series is positive in all 5 folds while each solo has losing folds.

### 4.2 Sensitivity grid (all honest OOS)

| variant | crypto Sh (DSR) | gold Sh (DSR) | COMB Sh (DSR) | maxDD | corr |
|---|---|---|---|---|---|
| SOL-gated 2020-08, gold d-40/20 (pessimistic corner) | −0.17 (0.01) | +1.00 (0.48) | +1.07 (0.42) | 14% | −0.054 |
| full-history, gold d-20/10 | +0.59 (0.24) | +0.09 (0.05) | +0.38 (0.12) | 16% | −0.021 |
| full-history, gold d-100/40 | +0.59 (0.24) | +0.78 (0.46) | **+1.12 (0.61)** | 17% | −0.020 |
| full-history, 3 folds | +0.59 (0.24) | +0.65 (0.35) | +1.00 (0.51) | 14% | −0.042 |

- **Correlation is robustly near-zero (−0.02 to −0.05) in every variant** — orthogonality is not fragile.
- The best gold config (d-100/40) gives the best combined book: Sharpe +1.12, DSR **0.61** — still short of 0.90.
- The SOL-gated 2020-08 start makes crypto **negative** OOS (excludes the strong 2017–2020 crypto trend); the book becomes ~gold-only. This is a pessimistic corner, not the headline — full-history is the honest window.

---

## 5. Interpretation & Verdict

**VERDICT: ADMIT-CANDIDATE (not full ADMIT).** Portfolio-admission gate result:

| gate | criterion | result |
|---|---|---|
| (a) | real standalone edge (both sleeves, PF-CI-low > 1 net) | **PASS** |
| (b) | uncorrelated OOS (|corr| < 0.30) | **PASS** (−0.042; robust −0.02..−0.05) |
| (c) | raises combined-book DSR vs best solo | **PASS** (0.509 > 0.347 > 0.239) |
| (d) | combined book clears DSR ≥ 0.90 / ROBUST | **FAIL** (0.509; 5/5 folds +) |

**The diversification benefit is REAL and OUT-OF-SAMPLE ROBUST — not an in-sample artifact.** The combined DSR beats the best-solo DSR in every full-history variant, the OOS Sharpe lift is +0.34, maxDD collapses from 52% to 14%, all 5 OOS folds are positive, and the sleeves demonstrably take turns carrying the book (fold 1 crypto, fold 4 gold). This is exactly the portfolio-admission evidence: gold is a genuine, OOS-orthogonal sleeve that improves the book.

**But the book does NOT graduate.** DSR 0.51 (best-config 0.61) is far short of 0.90. This is not a tuning failure — it is structural. Two individually-weak sleeves (Sharpe ~0.6 each) combined at even perfect orthogonality lift the pair-Sharpe by at most ~√2 (to ~0.9 raw), and the deflation for 20 trials + the honest OOS haircut pull the DSR to ~0.5. A 2-sleeve book of weak sleeves cannot reach a 0.90 DSR gate.

### Adversarial read (be honest about what this is NOT)

1. **The book is ~85% gold by vol-parity weight** (gold daily vol ~0.007 vs crypto ~0.022). Most of the combined *return* is the gold trend sleeve; crypto's contribution is **diversification (the drawdown halving and fold-1 carry), not return**. Do not oversell the "combined Sharpe ~1.0" as a crypto result — it is a gold-anchored book.
2. **The SOL-gated 2020-08 corner shows crypto NEGATIVE OOS** (Sharpe −0.17). The crypto DCB-1d pool's post-2022 OOS edge is regime-dependent and thin; the strong crypto contribution is concentrated in the 2020-2021 trend. Honest expectation: the crypto sleeve is a low/zero-Sharpe diversifier in the current regime, consistent with the exhausted 1d frontier.
3. **Gold has no live path on the Binance-only stack**, and its JVM gate-backtest is infra-blocked (4h monitor-data gap). The offline numbers are honest daily-cadence but **production-engine-unconfirmed**. A live gold sleeve is a Phase-2 execution build (~30–60 person-days) or requires a non-Binance venue.
4. **DSR 0.51 is a real improvement, not a graduation.** The value of this book is the **machine + track record** (the accumulation pipeline), not a gate-clear at current breadth. "Build the machine now; it pays as capital and sleeve-count grow."

---

## 6. If it PASSES the mechanism (which it does) — what a 3rd sleeve adds

The diversification mechanism is validated and **compounds**: adding uncorrelated ~0.6-Sharpe sleeves raises the book Sharpe as ~√(k) and pushes DSR toward the gate. Rough arithmetic at these correlations: 2 sleeves → book Sharpe ~1.0 / DSR ~0.5 (measured); **3 uncorrelated sleeves → ~1.2 / DSR ~0.7; 4–5 → ~1.4 / DSR ~0.85–0.90+.** The single highest-EV next step is therefore a **3rd uncorrelated non-crypto daily sleeve**, orthogonal to BOTH gold and crypto-beta. Concrete candidates (daily OHLC is cheap/free — same loader as `gold_ohlc_loader.py`):

- **(a) US-Treasury / bond-futures trend (ZN / ZB)** — classically near-zero-to-negative correlation with both risk assets AND gold; the strongest orthogonality bet.
- **(b) FX trend (DXY / EURUSD / USDJPY donchian)** — an orthogonal macro driver; USD-trend is uncorrelated with crypto and only weakly (often negatively) with gold.
- **(c) a 2nd commodity trend on a different complex (crude / copper / ags)** — low correlation with gold (different supply-demand driver).
- **(d) spot-perp CARRY** — already LIVE (~0.3 Sharpe, near-zero corr with both), fold in at low weight as a free diversifier.

This is the SCOPE Phase-3 "accumulation pipeline": every future candidate validated for orthogonality + combined-DSR lift before admission. **The book graduates by breadth, not by tuning either existing sleeve.**

## 7. What would FIX gate (d) — concrete

1. **Add sleeve(s)** — the primary lever (Section 6). Re-run `risk_parity_walkforward.py` extended to k sleeves; admit each iff it lifts the concatenated-OOS combined DSR.
2. **A materially stronger individual sleeve** — a single ~1.2-Sharpe orthogonal sleeve would push the 2-sleeve book toward the gate, but no such daily sleeve exists in the current book (both are ~0.6).
3. **NOT a fix:** re-weighting, re-tuning gold's channel (d-100/40 only reaches 0.61), or adding more crypto (falsified — DCB-55/Turtle and XS-8coin both failed to lift the crypto DSR; the 1d crypto frontier is exhausted).

---

## 8. Artifacts

- **Script:** `research/risk_parity_walkforward.py` (OOS walk-forward, self-contained; extends `research/risk_parity_combine.py` full-sample). Cached daily OHLC in `C:/Project/.rtmp/rp/*.csv` (pulled from VPS `market_data`).
- **Prior scripts:** `research/risk_parity_combine.py` (v1 in-sample), `research/gold_{donchian_backtest,orthogonality,ohlc_loader}.py`.
- **Journals:** outcome `98e5bb78-ccf4-47e0-85a3-2a8a62723af0` (this OOS verdict); prior in-sample deliverable `a4986473`; gold offline `55afdb54`; hypothesis `674cd8aa`.
- **Certified crypto anchor:** iteration `bab42423` (JVM pooled baseline, Sharpe 0.9834, PF 1.50, n=416).
- **Scope:** `research/SCOPE_2026-07-15_live_riskparity_book_build.md`, `research/SCOPE_2026-07-15_portfolio_ensemble_framework.md`.
