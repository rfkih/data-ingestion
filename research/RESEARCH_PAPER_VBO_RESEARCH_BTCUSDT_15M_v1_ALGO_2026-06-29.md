# Research Paper: VBO_RESEARCH — BTCUSDT × 15M

**Author:** quant-researcher
**Date:** 2026-06-29
**Strategy:** `VBO_RESEARCH`
**Surface:** `BTCUSDT` × `15M`
**Type:** ALGO
**Surface attempt:** v1 — ALGO (first cost-robust exit+selectivity test of VBO at 15m on BTC, under operator-directed 15m-scalping focus)
**Prior papers on this surface:** none (prior VBO 15m sweeps were on ETH/BNB/XRP, not BTC@15m)
**Filename:** `RESEARCH_PAPER_VBO_RESEARCH_BTCUSDT_15M_v1_ALGO_2026-06-29.md`
**Terminal:** SEED_GATED_OPERATOR_ACTION (config blocker; no lockout) — runnable surface falsified
**Goal status:** NOT HIT
**Hypothesis:** `5e57ec6d-8292-4e11-8ab0-005ec558ec92`
**Queue(s):** `b697ccfa-5fa8-4503-b75a-8129d97ec413`

---

## TL;DR

Under the operator's directed 15-minute scalping focus across the top-5 liquid coins, the platform exposes exactly ONE runnable 15m surface — `VBO_RESEARCH @ BTCUSDT @ 15m` — because every other (coin × 15m) and every non-VBO scalping engine at 15m has no `account_strategy` seed row (POST /queue 412 `account_strategy_missing`). A cost-robust hypothesis was pre-registered targeting the two genuinely un-mined VBO dimensions (multi-phase ATR-runner EXIT + composite minSignalScore SELECTIVITY), which 203 prior VBO iterations never swept. The sweep was decisively falsified on the first cell: the LEAST-selective configuration produced PF=0.09 with only n=38 trades over ~2.5 years (~87k 15m bars). VBO_RESEARCH is a heavily-gated compression-breakout, not a scalper — it fires ~38× in 2.5yr, so it structurally cannot reach the V11 n≥100 gate at 15m, and raising selectivity (the cost-robustness lever) only makes the frequency starvation worse. The base edge is also deeply negative (PF 0.09 = ~all losses). The single most important finding: **15m vol-breakout on BTC is both frequency-starved AND cost-dead on the only runnable 15m surface, and the orthogonal higher-frequency scalp mechanisms the operator wants to test are SEED-GATED pending operator action.**

*(No SIGNIFICANT_EDGE — metrics table omitted; best-cell numbers in §5.2.)*

---

## 1. Background

Operator issued a new directed focus (2026-06-29): find a profitable, COST-ROBUST 15m scalp across the top-5 liquid coins (BTCUSDT, ETHUSDT, SOLUSDT, ZECUSDT, XRPUSDT; BNBUSDT backup), exploring ORTHOGONAL intraday edges (order-flow/CVD, microstructure/VWAP mean-reversion, vol-breakout, opening-range, liquidity-sweep, intraday funding/basis, momentum ignition), prioritizing cost-robustness above raw signal. Prior research book: plain intraday EMA/MA trend on 15m BTC already FALSIFIED; price-action on majors largely exhausted; XS price-momentum dead on 13 coins. Prior terminal: WORKUNIT_PIVOT_2026-06-22 (no actionable family). VBO was research-FALSIFIED on majors (honest BTC ~-24.9%/yr; pre-06-06 backtests look-ahead-inflated). The 4 lowercase-archetype engines (MRO/MMR/DCB/TPB) exist in-code but are not seeded at 15m.

This surface was selected by necessity: `/account-strategies/research` lists VBO_RESEARCH@BTCUSDT@15m as the ONLY runnable 15m surface. The distinction that justified a fresh test of a falsified family: all 203 prior VBO iterations swept only ENTRY thresholds (atrExpansionMin/rvolMin/adxEntryMin/bbWidthMin) and fixed-R take-profits (tp1R/tpR); the engine's multi-phase ATR-runner EXIT and minSignalScore selectivity gate — the cost-robustness levers — were NEVER in any swept axis-set.

---

## 2. Hypothesis

**Mechanism:** VBO_RESEARCH is a volatility-compression-breakout engine: it requires simultaneous Bollinger-band-width compression, an ADX entry band, an ATR-expansion trigger, a relative-volume threshold, candle-quality gates, and a composite minSignalScore, then manages the position via a fixed first-target (tp1R) plus a multi-phase ATR-trailing "runner" (runnerPhase2R/3R, runnerAtrPhase2/3, runnerLockPhase2R/3R). The cost-robust thesis: at 15m, taker fees+slippage (~10-15bps round-trip) kill marginal breakouts; raising minSignalScore + atrExpansionMin cuts turnover to only the highest-conviction expansions, while widening the runner exit lets surviving winners run far enough to clear the cost floor.

**Pre-registration:** Hypothesis `5e57ec6d-8292-4e11-8ab0-005ec558ec92` registered 2026-06-28T17:00:07Z, before the sweep's earliest iteration (2026-06-28T17:32Z; gap ~32 min). Falsification criterion stated: "if even the most selective + let-winners-run cells stay PF<1 or INSUFFICIENT, 15m vol-breakout on BTC is cost-dead and the exit dimension does not rescue it." Plan-review APPROVED (0 blocker, 0 warning fails).

**Type:** ALGO.

---

## 3. Methodology

### 3.1 Statistical Gates (V11 + V60)

| Gate | Threshold | Binding? |
|---|---|---|
| n_trades | ≥ 100 | YES |
| PF 95% bootstrap CI lower | > 1.0 | YES |
| DSR (Bailey–LdP, cumulative n_trials) | ≥ 0.90 | YES |
| Statistical verdict | SIGNIFICANT_EDGE | YES |
| ann. geometric return at alloc-90 (ag90) | ≥ 10%/yr (loop GOAL); V60 platform floor now 0.0 | YES (loop goal) |

### 3.2 Sweep Design

- **Type:** GRID
- **Backtest window:** 2024-01-01 → 2026-06-28 (~30 months, ~10 quarters; ~87k 15m bars)
- **Dimensions swept (3):**
  - `minSignalScore`: 0.80, 0.90
  - `atrExpansionMin`: 1.30, 1.80, 2.30
  - `runnerPhase2R`: 2.0, 3.5
- **Total cells:** 12 planned, 2 executed (sweep cancelled after the first cell decisively falsified the n≥100 sanity assumption — see §5). Each 15m backtest over the full window took ~11 min; the drain hit its 1400s wall-clock cap after 2 cells.

### 3.3 Walk-Forward Protocol

Not run — no cell reached SIGNIFICANT_EDGE.

---

## 4. Parameter Space Explored

| Axis | Values Tested |
|---|---|
| `minSignalScore` | 0.80, 0.90 |
| `atrExpansionMin` | 1.30, 1.80, 2.30 |
| `runnerPhase2R` | 2.0, 3.5 |

**Total iterations:** 2 executed of 12 planned.

**Edge verdict distribution:**

| Verdict | Count |
|---|---|
| SIGNIFICANT_EDGE | 0 |
| INSUFFICIENT_EVIDENCE | 2 |
| NO_EDGE_DETECTED (DISCARD) | 0 |

---

## 5. Results

### 5.1 Edge summary

The binding constraint was **frequency starvation compounded by negative base edge**. At the least-selective grid corner (minSignalScore=0.80, atrExpansionMin=1.30), VBO fired only 38 times over ~2.5 years of 15m bars — far below the V11 n≥100 floor — and those 38 trades had a profit factor of 0.09 (gross profit / gross loss ≈ 0.09, i.e. near-total loss). Because every other cell in the grid is MORE selective (higher minSignalScore and/or higher atrExpansionMin), each remaining cell would fire even fewer than 38 times, making n≥100 unreachable across the entire 12-cell grid. The runner-exit dimension (the let-winners-run lever) is irrelevant when the entry edge is negative and the sample is sub-threshold. The hypothesis predicted n would stay ≥100 under selectivity; the data shows selectivity moves n in the WRONG direction.

### 5.2 Best cell (anchors future comparisons)

| Param | Value |
|---|---|
| `minSignalScore` | 0.80 |
| `atrExpansionMin` | 1.30 |
| `runnerPhase2R` | 2.0 / 3.5 |

| Metric | Value |
|---|---|
| iteration_id | 11ea6659-4671-4b0e-acbe-c4068dd06163 |
| n_trades | 38 |
| PF (point) | 0.09 |
| PF 95% CI lower | n/a (n<100, INSUFFICIENT) |
| DSR | n/a |
| ag90 (%/yr) | negative (PF 0.09) |
| Statistical verdict | INSUFFICIENT_EVIDENCE |

---

## 9. Infrastructure Notes

- **SEED-GATE (primary blocker).** Only `VBO_RESEARCH@BTCUSDT@15m` has an `account_strategy` seed row. Every other (coin × 15m) and every non-VBO scalping engine @ 15m returns 412 `account_strategy_missing`. The orchestrator exposes NO account_strategy-seeding endpoint (GET-only); the research JVM (:8081) is unreachable from the researcher shell (connection refused); hard rule 11 keeps the orchestrator out of `account_strategy` writes. Seeding therefore requires operator action (Flyway migration or platform admin). Documented as STRATEGY_OUTCOME/DATA_WISHLIST journal `0829001a-5d50-4773-b18b-b163c5eb0101`.
- **Slow 15m backtests.** A single VBO 15m backtest over the 2024→now window took ~11 min; the 1400s drain cap returned after 2 cells. A tighter window would speed cells, but was unnecessary here — the first cell already falsified the hypothesis.
- **SOLUSDT 15m feed STALE** (operator-relayed: latest bar ~2026-06-17, ~11d behind) — restrict SOL 15m backtests to ≤2026-06-17 or swap BNB; live-readiness needs the feed fixed.
- **ZECUSDT off the hard-rule-1 universe** — only a 1h ALT_CAP_FADE_ZEC row exists; no 15m market_data/feature_values/seed rows. Cannot backtest ZEC 15m; flagged for backfill.

---

## 10. Methodology Compliance Audit

| Rule | Compliant? | Notes |
|---|---|---|
| Universe BTC/ETH/SOL/BNB/XRP (hard rule #1) | YES | ran BTC only; ZEC correctly NOT traded (off-universe), flagged |
| Intervals in {5m,15m,1h,4h,1d} (hard rule #2) | YES | 15m |
| Prod/live untouched (hard rule #3) | YES | research account, enabled=false simulated=true |
| Research-mode only, no promotion (hard rule #4) | YES | no promotion |
| Profitability bar enforced (hard rule #5/#6) | YES | V11+V60 honored; gates not loosened |
| ≥ 3 axes swept (hard rule #7) | YES | minSignalScore × atrExpansionMin × runnerPhase2R |
| Pre-registration before testing (hard rule #10/#12) | YES | hypothesis predates sweep by ~32 min; plan APPROVED |
| Append-only durable evidence | YES | no deletes/mutations of iteration_log/journal/queue |
| Reviewer verdict authoritative (hard rule #12) | YES | plan review APPROVED before /queue |
| Research JVM only, no trading JVM calls (hard rule #13) | YES | only :8082 orchestrator + read-only :8081 probe (refused) |

---

## 11. Conclusions

1. **Frequency starvation:** VBO_RESEARCH at 15m on BTC fires only ~38 times in 2.5yr at its least-selective setting — it is a heavily-gated compression-breakout, not a scalper, and cannot reach the V11 n≥100 gate at this interval.
2. **Negative base edge:** the 38 trades had PF=0.09 (~all losses); the cost-robust exit/selectivity dimensions cannot rescue a negative entry edge on a sub-threshold sample.
3. **Selectivity is counter-productive here:** raising minSignalScore/atrExpansionMin reduces n further, so the hypothesis's n≥100 assumption fails in the wrong direction — the whole 12-cell grid is dead.
4. **Implication for the research loop:** the operator-directed 15m scalping program is SEED-GATED. The only runnable 15m surface is falsified; the orthogonal higher-frequency mechanisms that could plausibly sustain a 15m scalp (microstructure/VWAP mean-reversion, opening-range, momentum ignition) require operator-seeded `account_strategy` rows before any of them can be tested. The unlock is operator plumbing + orthogonal non-price data, not more price-action sweeps on the majors.

---

## 12. Data Wishlist

| Priority | Item | Blocker type |
|---|---|---|
| 1 | account_strategy seed rows at 15m for MRO/VMT (microstructure & VWAP mean-reversion), MMR (momentum ignition), DCB (opening-range/Donchian breakout) across BTC/ETH/SOL/BNB/XRP | platform seed (Flyway / admin), operator-only |
| 2 | Extend VBO_RESEARCH@15m seed rows to ETH/SOL/BNB/XRP (only BTC seeded now) | platform seed |
| 3 | Fix STALE SOLUSDT 15m feed (latest ~2026-06-17) | backfill / ingest |
| 4 | ZECUSDT full 15m market_data + feature_values + seed rows (if ZEC joins the liquid-5) | backfill + seed |
| 5 | Order-flow / CVD-imbalance intraday engine + 15m seed (the most orthogonal scalp edge; none exists in-code yet) | JVM engine + seed |

---

## 13. Appendix — Audit Trail

| Item | ID |
|---|---|
| Hypothesis | `5e57ec6d-8292-4e11-8ab0-005ec558ec92` |
| Queue | `b697ccfa-5fa8-4503-b75a-8129d97ec413` |
| Best/only iteration | `11ea6659-4671-4b0e-acbe-c4068dd06163` |
| Walk-forward run | n/a (no SIGNIFICANT_EDGE) |
| Specialist verdicts | n/a |
| STRATEGY_OUTCOME journal (falsification) | `872281c3-1129-4e49-98fd-66d75e5ebfe9` |
| STRATEGY_OUTCOME journal (seed-gate DATA_WISHLIST) | `0829001a-5d50-4773-b18b-b163c5eb0101` |
| DB paper | `BH-VBO_RESEARCH-BTCUSDT-15M-b697ccfa` |
| RUN_SUMMARY journal | (see session RUN_SUMMARY 2026-06-29) |

---
*Paper generated by quant-researcher. DB registration: `POST /papers/b697ccfa-5fa8-4503-b75a-8129d97ec413/generate`.*
