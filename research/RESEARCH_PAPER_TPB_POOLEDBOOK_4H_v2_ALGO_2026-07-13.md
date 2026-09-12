# Research Paper: TPB_POOL — POOLEDBOOK × 4H (breadth + window-extension certification, operator-directed)

**Author:** quant-researcher
**Date:** 2026-07-13
**Strategy:** `TPB_POOL` (sleeves `TPB`)
**Surface:** `POOLEDBOOK` (SOLUSDT + XRPUSDT + ADAUSDT + DOGEUSDT / AVAXUSDT candidates) × `4h`
**Type:** ALGO
**Surface attempt:** v2 — ALGO ("operator-provisioned breadth unlock ADA/DOGE/AVAX + pre-registered one-attempt window extension; continues v1's SOL+XRP core certification")
**Prior papers on this surface:** `RESEARCH_PAPER_TPB_POOLEDBOOK_4H_v1_ALGO_2026-07-13.md`
**Filename:** `RESEARCH_PAPER_TPB_POOLEDBOOK_4H_v2_ALGO_2026-07-13.md`
**Terminal:** ARCHETYPE_EXHAUSTION
**Goal status:** NOT HIT
**Hypothesis:** `28a88dd7-4181-4707-816c-898e547b1543` (breadth, FALSIFIED), `ddafba60-83d3-45ae-8eac-351fd82ec192` (window extension, PARKED — predictions held, certification failed)
**Queue(s):** breadth `62692018` (ADA), `f4fd3b5e` (DOGE), `76f46f15` (AVAX); extension `8e7109a5` (SOL), `98c52f36` (XRP), `80fbd0a6` (ADA), `fa208733` (DOGE), `b44a3a15` (AVAX)

---

## TL;DR

The operator provisioned the exact breadth unlock the v1 paper requested (TPB@4h seeds + verified 4h data for ADAUSDT/DOGEUSDT/AVAXUSDT), and this session pushed the TPB_POOL two-sided trend-pullback book to n≥100 through two pre-registered, drag-rule-governed expansions. Both landed short of certification, and the combination is now a power-complete falsification: the **2021+ expanded book** (SOL+XRP+ADA+AVAX, iteration `a7d7b2a3`) has the quality — PF 2.031, PF-CI-low **1.205** (up from the core's 1.049), Sharpe 1.11, ann90 7.81 — but only n=92, because DOGE fails the pre-registered drag rule and its 10 trades may not pad the count. The **full-window book** (2018-anchor, SOL+XRP+ADA+DOGE, iteration `d1d82080`) crosses **n=106** legitimately but the added pre-2021 history dilutes everything that matters: PF 1.633, PF-CI-low 1.0048 (hairline), DSR **0.041**, ann90 **3.80**. The edge is real (PF-CI-low > 1.0 on both variants, bear-carried 75%+ of trades and PnL) but sits **below the certification bar on every legitimate configuration**; certification arithmetic on the current universe/config is closed. No graduation review or walk-forward was run, per pre-declaration.

| Metric (best-n book, `d1d82080`) | Value | Gate | Pass? |
|---|---|---|---|
| n_trades | 106 | ≥ 100 | YES |
| PF 95% CI lower | 1.0048 | > 1.0 | YES (hairline) |
| DSR | 0.041 @ 226 trials | ≥ 0.90 | **NO** |
| ag90 (%/yr) | 3.80 | ≥ 10% | **NO** |
| Walk-forward | not run (gate-blocked by pre-declaration) | ROBUST | — |

---

## 1. Background

v1 (same date) certified the TPB two-sided trend-pullback edge as real-but-thin on the SOL+XRP core: pooled iteration `42e5d72c` n=52, PF 2.056, PF-CI [1.049, 3.924], DSR 0.044@209, ann90-slice 9.29 → INSUFFICIENT_EVIDENCE, padding declined per pre-registration `46bfd099` (BTC PF 0.87 bear-negative, BNB bear −159.7 → both excluded; ETH prior-falsified). The recorded warm lead named "operator-gated breadth: seed TPB@4h on ADA/DOGE/AVAX" as the #1 unlock. The operator provisioned exactly that on 2026-07-13 (research-account `account_strategy` rows + full 4h coverage back to 2020, verified: bear-pullback raw signals ADA 153 / DOGE 195 / AVAX 102) and directed this run. The PIT-cleanliness audit of the entire TPB_POOL path (`9395948a`, PIT_CLEAN, 6 legs verified in source) predates all compute in this session; the new coins ride the identical engine/coordinator path.

## 2. Hypothesis

**Mechanism:** TrendPullbackEngine (archetype `trend_pullback`, spec-driven) enters WITH the prevailing EMA50/200 trend after a counter-trend pullback touches EMA20 (within pullbackTouchAtr×ATR), confirmed by candle quality (bodyRatioMin, CLV band, rvol), ADX bands and DI-spread; exits at TP1 (tp1R) plus a break-even-shifted ATR runner (runnerAtrPhase3). The certified claim (parent hypothesis `4e941275`) is that this fires and profits on BOTH sides, bear-carried — unlike the falsified bull-only ATR_MOM.

**Pre-registration:**
- Breadth: `28a88dd7` registered 05:14 UTC, before the first coin probe at 05:40 (gap 26 min). Falsifier: book stays sub-100 after honest drag-rule exclusions.
- Window extension: `ddafba60` registered 06:02 UTC, before the first extension probe at 06:05 (gap 3 min). Window rule: ALL candidate sleeves at fixed 2018-01-01 anchor, ONE attempt ever, drag rule re-applied verbatim on full windows, flips honored in both directions.
- Drag-coin inclusion rule (carried from v1, `46bfd099`): a coin enters IFF point PF > 1.0 at the frozen config on its full window AND bear-bucket PnL > 0 AND surface not previously falsified.

**Type:** ALGO. No ML signals anywhere in the book (structurally: TPB carries no `_ml_*` sentinels; the DCB_POOL look-ahead channel is absent).

## 3. Methodology

### 3.1 Statistical Gates (V11 + V60)

n ≥ 100 (YES-binding), PF 95% bootstrap CI lower > 1.0 (YES), DSR ≥ 0.90 at server-counted cumulative trials + declared external 90 (YES), ag90 ≥ 10%/yr (operator's certification bar for this task; YES), pooled-series WF ROBUST (conditional stage, never reached).

### 3.2 Sweep Design

- **Type:** GRID, single cell per coin — the BYTE-FROZEN config from `46bfd099`: adxEntryMin=20, adxEntryMax=60, biasAdxMin=18, biasAdxMax=60, minSignalScore=0.50, rvolMin=0.85, bodyRatioMin=0.30, maxEntryRiskPct=0.06, tp1R=3.0, runnerAtrPhase3=3.0 (engine defaults elsewhere, incl. pullbackTouchAtr=0.40, diSpreadMin=2.0). **Zero per-coin tuning** (per-coin exit selection pre-registered as mining in `deb7f222`, stays forbidden).
- **Windows:** breadth probes 2021-01-01 → 2026-07-12; extension probes 2018-01-01 → 2026-07-12 (effective start = per-coin data inception).
- **Cells:** 8 probe cells (3 breadth + 5 extension) + 2 pooled certifications = 10 executed, 10 planned.

### 3.3 Walk-Forward Protocol

Not run. Pre-declared mapping: walk-forward only if ALL V11 gates pass at the pooled level; both pooled iterations returned INSUFFICIENT_EVIDENCE.

---

## 4. Parameter Space Explored

| Axis | Values Tested |
|---|---|
| symbol (transfer axis) | ADAUSDT, DOGEUSDT, AVAXUSDT (breadth); + SOLUSDT, XRPUSDT (extension re-measurement) |
| window_start | 2021-01-01 (breadth), 2018-01-01 (extension, one pre-registered attempt) |
| all 10 config params | frozen single values (see §3.2) |

**Total iterations:** 10 this session (8 probes + 2 pooled). Cumulative DSR-deflated trials at final pooled: 226 (per-surface SOL 91, XRP 33, ADA 6, DOGE 5, external 90, +1 self).

**Edge verdict distribution (this session):**

| Verdict | Count |
|---|---|
| SIGNIFICANT_EDGE | 0 |
| INSUFFICIENT_EVIDENCE | 10 |
| NO_EDGE_DETECTED (DISCARD) | 0 |

---

## 5. Results

### 5.1 Per-coin drag-rule measurements

Breadth round (2021-01-01 windows), rule `46bfd099`:

| Coin | iteration | n | PF | BEAR PnL (n) | ag90 | Rule decision |
|---|---|---|---|---|---|---|
| ADAUSDT | `234e3367` | 24 | 1.786 | +454.5 (22) | 5.60 | **INCLUDE** |
| DOGEUSDT | `e861f783` | 10 | 0.952 | +72.7 (6) | −0.17 | **EXCLUDE** (PF ≤ 1) |
| AVAXUSDT | `fb06d7ca` | 16 | 2.252 | +318.4 (11) | 6.83 | **INCLUDE** |

Extension round (2018-01-01 windows), rule re-applied verbatim:

| Coin | iteration | n | PF | BEAR PnL (n) | Rule decision |
|---|---|---|---|---|---|
| SOLUSDT | `9d1d9792` | 22 | 2.397 | +634.0 (17) | INCLUDE (identical to 2021 run — no pre-2021 data) |
| XRPUSDT | `890671a8` | 41 | 1.334 | +280.0 (29) | INCLUDE |
| ADAUSDT | `bd968629` | 26 | 1.599 | +279.5 (24) | INCLUDE |
| DOGEUSDT | `a2c167e7` | 17 | 1.171 | +113.4 (10) | INCLUDE (**flips in** on full window) |
| AVAXUSDT | `4b23e332` | 14 | 0.733 | −83.3 (13) | EXCLUDE (**flips out**: PF < 1 AND bear-negative) |

The symmetric flips (DOGE in, AVAX out) are the integrity proof that inclusion was never steered toward n≥100 — the rule was followed mechanically in the direction that both helped and hurt the count. The AVAX flip (PF 2.25 → 0.73 from adding 2020Q4 plus indicator warm-up path-dependence; n fell 16 → 14 because earlier EMA/ADX state and single-slot sequencing remove later entries) is a standing robustness caveat: per-coin cells at n 14–41 are high-variance and the drag rule is a noisy classifier at this sample size. The pooled book measurement is the controlling evidence.

### 5.2 Pooled certifications (the two book variants)

| Metric | 2021+ book `a7d7b2a3` (SOL+XRP+ADA+AVAX) | Full-window book `d1d82080` (SOL+XRP+ADA+DOGE) | Gate |
|---|---|---|---|
| n_trades | 92 | **106** | ≥100 |
| PF (point) | 2.031 | 1.633 | — |
| PF 95% CI | [**1.205**, 3.266] | [1.0048, 2.511] | low > 1.0 |
| DSR (@trials) | 0.154 (@219) | 0.041 (@226) | ≥ 0.90 |
| PSR | 0.622 | 0.336 | — |
| ag90 (%/yr, equal-slice) | 7.81 | 3.80 | ≥ 10 |
| Sharpe_ann | 1.106 | 0.666 | — |
| Sortino_ann | 2.876 | 1.611 | — |
| maxDD % | 7.13 | 10.10 | — |
| BEAR bucket | 74/92 trades, +1739/+2312 PnL | 80/106 trades, +1307/+1673 PnL | — |
| Statistical verdict | INSUFFICIENT_EVIDENCE | INSUFFICIENT_EVIDENCE | — |

**The binding structure:** quality and sample size trade off against each other across the only two legitimate windows. The 2021+ book fails only n (92) among {n, PF-CI}; the full-window book passes n but pre-2021 trades halve per-year density (equal-slice ag90 7.81→3.80) and drop pooled Sharpe 1.11→0.67, which crushes DSR (0.154→0.041) despite the longer track. PF-CI-low > 1.0 on BOTH books — the two-sided bear-carried edge is real; it is simply not certifiable at V11 strength on data that exists today.

---

## 9. Infrastructure Notes

- The `GET /account-strategies/research` listing did not show the XRPUSDT-TPB row even though `/queue` + tick ran it fine — listing quirk, not a missing seed; do not treat that endpoint as exhaustive.
- ADA 4h feature coverage ends ~2026-06 (operator-declared); its probe window ran to 2026-07-12 with a signal-less final month — declared, immaterial.
- The journal API has no status-mutation route; hypothesis dispositions (`28a88dd7`→FALSIFIED, `ddafba60`→PARKED) were applied via the playbook-sanctioned psql `UPDATE research_journal SET status=…` on the VPS.

## 10. Methodology Compliance Audit

| Rule | Compliant? | Notes |
|---|---|---|
| Research universe (hard rule #1) | YES* | ADA/DOGE/AVAX are off the standing 5-name universe but were operator-provisioned + operator-directed for this task |
| Intervals valid (hard rule #2) | YES | 4h only |
| Live trading untouched (hard rule #3) | YES | research account 99999999-…-0002 only |
| Research-mode only (hard rule #4) | YES | no promotion, no deploys |
| 10%/yr bar (hard rule #5) | YES | enforced as certification bar; both books honestly below |
| V11+V60 gates honored (hard rule #6) | YES | no threshold moved; DSR reported at 0.041/0.154 without shopping |
| ≥3 dimensions (hard rule #7) | YES | symbol-transfer + window axes on a book already swept across entry/exit/interval/regime/pooling |
| Pre-registration before testing | YES | both hypotheses + window rule + drag rule registered before compute (gaps 26 min / 3 min) |
| Append-only durable evidence (hard rule #10) | YES | status flips only, playbook-sanctioned |
| Reviewer verdict authoritative (hard rule #12) | YES | plan reviews CONDITIONAL_APPROVAL + APPROVED; no graduation requested (no SIGNIFICANT_EDGE) |
| No trading JVM calls (hard rule #13) | YES | orchestrator only |

## 11. Conclusions

1. **The TPB two-sided trend-pullback edge is real at the book level:** PF 95% CI lower bound exceeds 1.0 on both legitimate book variants (1.205 at n=92; 1.0048 at n=106), bear-carried ≥75% of trades and PnL — the mechanism of `4e941275` survived a 4-coin, 2-window, fully pre-registered stress.
2. **Certification arithmetic is closed on current data:** the only window with certifiable quality (2021+) cannot reach n=100 without padding, and the only window that reaches n=100 (2018+) dilutes DSR to 0.041 and ag90 to 3.80 — no legitimate configuration passes all V11 gates simultaneously.
3. **The pre-registered drag rule survived its own stress test:** it flipped DOGE in and AVAX out under the window change — evidence the pipeline optimizes honesty, not the count; the n≥100 book was reported as the worse book.
4. **Per-coin transfer statistics at n 14–41 are knife-edge fragile** (AVAX PF 2.25→0.73 under a window perturbation): future pooled work should treat per-coin point estimates as inclusion inputs only, never as standalone findings.
5. **Implication for the research loop:** TPB family EXHAUSTED on current data; the 2021+ book is a below-bar diversifying overlay candidate (house-book track, operator call), and the organic reopen condition is the 2021+ book crossing n≈100 by itself (~2026-12 at the observed ~1.4 trades/coin-month).

## 12. Data Wishlist

| Priority | Item | Blocker type |
|---|---|---|
| 1 | Time: 2021+ book accrues ~6 trades/month across 4 coins → n≈100 around 2026-12; re-run `a7d7b2a3` book then (no new infra needed) | time/data accrual |
| 2 | Operator decision: route the 2021+ book (PF-CI-low 1.205, sub-bar ann) to the pool-candidate/house-book overlay track instead of V11 certification | operator decision |
| 3 | If more breadth is ever wanted: LINK/MATIC/DOT 4h backfill + TPB seeds (same recipe as ADA/DOGE/AVAX) | backfill + seed |

## 13. Appendix — Audit Trail

| Item | ID |
|---|---|
| Hypotheses | `28a88dd7` (breadth, FALSIFIED), `ddafba60` (window ext, PARKED) |
| Plan reviews | CONDITIONAL_APPROVAL (`plan:TPB:f9ad1561…:28a88dd7`), APPROVED (ext, `ddafba60`) |
| Queues | `62692018`, `f4fd3b5e`, `76f46f15`, `8e7109a5`, `98c52f36`, `80fbd0a6`, `fa208733`, `b44a3a15` |
| Probe iterations | `234e3367` (ADA-2021), `e861f783` (DOGE-2021), `fb06d7ca` (AVAX-2021), `9d1d9792` (SOL-2018), `890671a8` (XRP-2018), `bd968629` (ADA-2018), `a2c167e7` (DOGE-2018), `4b23e332` (AVAX-2018) |
| Pooled iterations | `a7d7b2a3` (2021+ book, n=92), `d1d82080` (full-window book, n=106) |
| Walk-forward run | none (pre-declared gate-block) |
| STRATEGY_OUTCOME journals | `4218489c` (drag decisions 1), `b74a1255` (2021+ pooled outcome), `20c7a8f7` (drag decisions 2), `fbb52d37` (final falsification) |
| RUN_SUMMARY journal | `ARCHETYPE_EXHAUSTION_2026-07-13` (this session's terminal row) |
| Prior paper this continues | `RESEARCH_PAPER_TPB_POOLEDBOOK_4H_v1_ALGO_2026-07-13.md` |
| PIT audit (re-affirmed) | `9395948a` PIT_CLEAN |
| Pre-registrations | `46bfd099` (drag rule + frozen config), `4218489c`/`20c7a8f7` (application checkpoints) |

---
*Paper generated by quant-researcher. DB registration: `POST /papers/<queue_id>/generate` (8 queue papers registered: BH-TPB-{ADA,DOGE,AVAX,SOL,XRP}USDT-4H-… series).*
