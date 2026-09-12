# Research Paper: 4-SLEEVE RISK-PARITY BOOK — LOCKED-IN PORTFOLIO-ADMISSION CANDIDATE (crypto DCB pool + GOLD + CORN + USDJPY) × 1d

**Author:** quant-researcher (lock-in authored by main session on operator decision)
**Date:** 2026-07-17
**Strategy:** `DCB_POOL` (crypto DCB-1d pool BTC/ETH/SOL/XRPUSDT, d-20/10 two-sided) + `DCB` long-only sleeves: `XAUUSD` d-40/20, `CORN (ZC=F)` d-55/20, `USDJPY (JPY=X)` d-55/20 — combined as one vol-parity book
**Surface:** multi-asset daily trend book (the portfolio-admission unit)
**Type:** CHAR (breadth extension of the v2 OOS walk-forward; lock-in record)
**Surface attempt:** v3 — CHAR (adds sleeves 3–5 to the v2 two-sleeve walk-forward; documents the operator lock-in decision)
**Prior papers on this surface:** v1 (in-sample thesis validation), v2 (2-sleeve OOS walk-forward, ADMIT-CANDIDATE at DSR 0.51)
**Filename:** `RESEARCH_PAPER_DCB_POOL_RISKPARITY_1D_v3_CHAR_2026-07-17.md`
**Terminal:** OPERATOR_DECISION — option (a): lock in the 4-sleeve book as the documented portfolio-admission candidate (chosen 2026-07-17 over pivoting to higher-Sharpe per-sleeve search)
**Goal status:** LOCKED AS ADMIT-CANDIDATE — Sharpe +1.18 / maxDD 7% / DSR@20 0.76; gate (d) DSR ≥ 0.90 NOT cleared (structural plateau, documented below)
**Hypotheses:** `674cd8aa` (gold sleeve); breadth extension pre-registered in v2 §6
**Queue(s):** none (offline analysis; certified crypto anchor = iteration `bab42423`)
**Journals:** v2 outcome `98e5bb78`; walk-forward deliverable `5e5e290d`; in-sample deliverable `a4986473`; **lock-in decision `2765ba66-cbd9-4e1b-9844-f8a7d483091d`** (CROSS_STRATEGY_FINDING, PARKED, 2026-07-17)

---

## TL;DR

The operator selected **option (a)** on 2026-07-17: **lock in the 4-sleeve risk-parity book — crypto DCB-1d pool + gold + corn + USDJPY — as the platform's documented portfolio-admission candidate**, rather than pivoting the next research push to higher-Sharpe per-sleeve signals. This paper is the lock-in record: the definitive statement of what the book is, what it measures, why it does not graduate at current breadth, and what would change that.

The book's honest OOS walk-forward (vol-parity weights fit in-sample, applied OOS, 5 expanding folds, 8 bps/side, verified by a clean re-run on 2026-07-17): **OOS Sharpe +1.176 (252-ann), DSR 0.762 (N_TRIALS=20), maxDD 7%, max pairwise |corr| 0.176**. Adding a 5th sleeve (oil) adds nothing (+1.166 / 0.761) — the naive-donchian breadth curve **plateaus at 4 sleeves**. Versus the solo crypto book (Sharpe ~0.59, maxDD 52%, DSR 0.24), the 4-sleeve book adds ~+0.6 Sharpe and cuts drawdown by ~7×. The diversification mechanism is real, OOS-robust, and compounds — but individually-weak (~0.3–0.7 Sharpe) trend sleeves cannot stack to a 0.90 DSR. **The book is a strong ADMIT-CANDIDATE and the platform's default portfolio unit going forward; graduation requires a different lever (a materially higher-Sharpe orthogonal sleeve or substantially longer history), not more weak sleeves.**

*(No V11 gate table — this is a portfolio unit, not a single-strategy certification.)*

---

## 1. Background — why this book exists

The 1d crypto single-strategy frontier is exhausted (ARCHETYPE_EXHAUSTION, 2026-07-15): every crypto signal is ~0.8-correlated BTC-beta, capping the pooled DCB-1d book at DSR ~0.27 regardless of edge quality. The falsified alternatives are catalogued in v2 and the 2026-07-15/16 run records: donchian-55/Turtle as a DSR lever (DSR 0.271→0.041), 8/9-coin XS momentum (DSR 0.002), MR at 1d (bull-only artifact), wider DCB exits (pure multiplicity).

The only structural fix is **orthogonal, non-crypto return streams**. v1 validated the mechanism in-sample (gold corr 0.098 vs BTC); v2 proved it OOS for 2 sleeves (combined DSR 0.51 > best solo 0.35, maxDD halved, 5/5 folds positive) and pre-registered breadth as the next lever. This paper measures sleeves 3–5 and records the lock-in.

## 2. Sleeve selection — two-stage screen (no test-fold contamination)

Twelve free-daily-OHLC non-crypto instruments (Yahoo Finance, `gold_ohlc_loader.py` pattern) were screened in two stages, both on data independent of the walk-forward test folds:

**Stage 1 — orthogonality filter (|corr| < 0.30 vs BOTH crypto pool and gold):**
- KEPT: bonds (ZN), oil (CL), EURUSD, USDJPY, corn (ZC), natgas (NG)
- DROPPED: silver (0.78 vs gold), copper (0.33), DXY (−0.40), SP500 (0.30 vs crypto)

**Stage 2 — standalone donchian trend edge (same breakout + opposite-channel-exit family, long-only and long+short, 8 bps/side, grid d-20/10, 40/20, 55/20, 100/40):**
- KEPT: **CORN d-55/20 L (Sharpe 0.72)**, **USDJPY d-55/20 L (0.57)**, OIL d-40/20 L (0.30)
- DROPPED: bonds (best Sharpe −0.28 — no trend edge this history), natgas (dead), EURUSD (weak)

A sleeve must carry BOTH real edge AND orthogonality; orthogonality alone (bonds) does not admit.

Scripts: `research/multi_sleeve_orthogonality.py`, `research/multi_sleeve_edge.py`.

## 3. Methodology (identical to v2, generalized to N sleeves)

- Each sleeve = donchian breakout + opposite-channel exit daily P&L (the deployed `DonchianBreakoutEngine` rule family), 8 bps/side debited on exit.
- Crypto pool = equal-weight across coins active each day (BTC/ETH/SOL/XRP d-20/10, two-sided); non-crypto sleeves long-only (shorting fights secular uptrends; validated per-sleeve).
- **OOS walk-forward:** expanding window, warmup = first 1/3 of common days, then 5 sequential OOS test blocks. **Vol-parity weights (w ∝ 1/realized-vol) estimated on train data only, applied to the OOS block.** OOS returns concatenated; all statistics computed on the concatenated OOS series.
- **DSR:** Bailey & López de Prado deflated Sharpe, N_TRIALS = 20 primary (the gold+crypto program's trial count), 50 and 100 reported as multiplicity sensitivity.
- Common-day intersection shrinks as sleeves are added (USDJPY's Yahoo history is the binding constraint at N=4: 2222 → 1964 days).

Script: `research/multi_sleeve_walkforward.py` (self-contained; runs on the VPS — DB for crypto/gold, Yahoo for corn/JPY/oil).

## 4. Results — breadth curve (verified re-run 2026-07-17)

| N | sleeves | common days | OOS Sharpe (252) | DSR@20 | DSR@50 | DSR@100 | maxDD | avg corr | max \|corr\| |
|---|---|---|---|---|---|---|---|---|---|
| 2 | CRYPTO+GOLD | 2225 | +0.824 | 0.510 | 0.363 | 0.272 | 14% | −0.031 | 0.031 |
| 3 | +CORN | 2222 | +1.089 | 0.751 | 0.618 | 0.519 | 13% | +0.057 | 0.171 |
| **4** | **+USDJPY (the book)** | **1964** | **+1.176** | **0.762** | **0.632** | **0.533** | **7%** | **−0.009** | **0.176** |
| 5 | +OIL | 1963 | +1.166 | 0.761 | 0.631 | 0.532 | 7% | +0.044 | 0.254 |

- **Breadth genuinely lifts the book**: Sharpe +0.82 → +1.18, maxDD 14% → 7% from sleeve 2 to 4. Orthogonality holds OOS at every step (max pairwise |corr| 0.18 for the book).
- **The curve plateaus at 4 sleeves.** Oil (the weakest edge, Sharpe 0.30) adds nothing and lifts the max correlation — it is excluded from the locked book.
- **DSR plateaus at ~0.76** (N=20), degrading to 0.63/0.53 under harsher multiplicity assumptions. The v2 §6 projection ("4–5 sleeves → 0.85–0.90+") was optimistic: √k Sharpe-stacking assumed ~0.6-Sharpe sleeves throughout, but corn/JPY/oil are 0.3–0.7 and the common-history shortening (1964 days) also costs DSR.

## 5. Verdict & the lock-in decision

**Portfolio-admission gate (per `SCOPE_2026-07-15_portfolio_ensemble_framework.md`):**

| gate | criterion | result |
|---|---|---|
| (a) | real standalone edge per sleeve | **PASS** (crypto PF 1.50 JVM-certified; gold 0.65, corn 0.72, JPY 0.57 offline) |
| (b) | pairwise orthogonality OOS (\|corr\| < 0.30) | **PASS** (max 0.176) |
| (c) | each sleeve raises combined-book DSR | **PASS** (0.510 → 0.751 → 0.762) |
| (d) | combined book DSR ≥ 0.90 / ROBUST | **FAIL** (0.762 @ N=20; plateau) |

**Operator decision (2026-07-17), option (a): the 4-sleeve book is LOCKED IN as the documented portfolio-admission candidate.** Rationale: the durable outcome of this arc is the *machine* — a validated orthogonality-screen → edge-screen → OOS-vol-parity-walk-forward admission pipeline plus a concrete 4-sleeve book with a 7%-drawdown, Sharpe-1.18 OOS record. That asset compounds: every future sleeve candidate (options-skew alpha post-Tardis, microstructure post-data-maturity, carry, a higher-Sharpe crypto signal) is admitted through the same gate and lifts the same book. Choosing (b) (an open-ended hunt for a ~1.2-Sharpe sleeve now) would discard none of this and can proceed later against the locked benchmark.

### Adversarial read (carried forward from v2, still true)

1. **The book is dominated by non-crypto sleeves by vol-parity weight** (crypto daily vol ~3× the others). Crypto's contribution is diversification and the 2020-21 fold-carry, not steady return.
2. **All non-crypto numbers are offline-honest but production-unconfirmed.** No live execution path exists (Binance-only stack); gold's JVM certification is additionally infra-blocked (DCB needs a 4h intra-bar monitor feed; XAUUSD has 1d bars only). Corn/JPY are Yahoo-continuous-futures/FX series — real deployment would face roll costs and venue spreads not modeled beyond the 8 bps.
3. **DSR 0.76 is not 0.90.** The lock-in is an admission-candidate record and benchmark, not a graduation. Nothing in this paper feeds the frozen V11/V60 gates.
4. **Free-data survivorship**: the sleeve screen used instruments with long free Yahoo histories; the edge screen grid (4 channel configs × 2 sides) is small but nonzero multiplicity — hence the N=50/100 DSR sensitivities.

## 6. What would clear gate (d) — the standing to-do for any future run

1. **A materially higher-Sharpe orthogonal sleeve (~1.0+)** — the primary lever. Candidates in priority order: options-surface skew alpha (Tardis purchase, hypothesis `470ca035` pre-registered, loader built), microstructure ob_* reversion (data matures ~Sept–Oct 2026, plan pre-registered), a genuinely new crypto signal family. Admit through this book's gate; re-run `multi_sleeve_walkforward.py` extended.
2. **Longer history** — DSR rises with n; the USDJPY-shortened 1964-day window is part of the shortfall. A longer-history 4th sleeve replacing JPY could recover some DSR at equal Sharpe.
3. **NOT a fix (falsified):** more weak trend sleeves (oil, N=5 row), re-weighting, re-tuning existing channels, more crypto breadth (55/Turtle, XS-8coin).
4. **Fold in live carry** at low weight as a free diversifier — untested in this walk-forward (the carry stream's daily series was not reconstructed); worth measuring in the next book revision.

## 7. Reproducibility

- `research/multi_sleeve_orthogonality.py` — stage-1 screen
- `research/multi_sleeve_edge.py` — stage-2 edge screen
- `research/multi_sleeve_walkforward.py` — the N-sleeve OOS walk-forward (this paper's table = its verbatim output, re-run 2026-07-17 on the VPS)
- `research/risk_parity_walkforward.py`, `research/risk_parity_combine.py` — v2/v1 predecessors
- `research/gold_{ohlc_loader,orthogonality,donchian_backtest}.py` — gold sleeve + the loader pattern for any new daily instrument
- Data: crypto + XAUUSD from prod `market_data` (1d); ZC=F / JPY=X / CL=F from Yahoo Finance v8 chart API, 25y daily

## 8. Platform state at lock-in (operator-owed items unchanged)

- Research JVM `ghcr.io/rfkih/blackheart-research:a2d7a3b` (donchian_55/Turtle, V211) and orchestrator `ghcr.io/rfkih/blackheart-orchestrator:bc67e1b` (non-crypto enablement) — both live on prod, **branches `feat/donchian55-turtle-v211` + `feat/noncrypto-research-enablement` NOT pushed** (operator push owed to formalize; rollback tags `86a5ff14` / `923e0758`).
- Gold XAUUSD 1d in prod `market_data` (6273 bars) + `feature_store` (5011); corn/JPY/oil NOT ingested (Yahoo-fetched at analysis time — ingest is a future decision if the book moves toward execution).
- Lock-in decision journaled to `research_journal`: **`2765ba66-cbd9-4e1b-9844-f8a7d483091d`** (CROSS_STRATEGY_FINDING, status PARKED, created_by operator, 2026-07-17).
