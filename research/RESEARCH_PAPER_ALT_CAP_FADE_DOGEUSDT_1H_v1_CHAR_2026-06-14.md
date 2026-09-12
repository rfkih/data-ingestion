<!-- CHAR study: ALT capitulation-fade family (operator-directed DSR/history/breadth) -->
# Research Paper: ALT_CAP_FADE family - multi-alt x 1H (operator-directed DSR/history/breadth study)

**Author:** quant-researcher
**Date:** 2026-06-14
**Strategy:** `ALT_CAP_FADE_{XRP,DOGE,SOL,...}` (CapitulationFadeStrategyEngine, V177)
**Surface:** XRPUSDT / DOGEUSDT / SOLUSDT x 1H (+ DCB ETHUSDT 4H full-2017 as lever-(a) precedent)
**Type:** CHAR
**Surface attempt:** v1 - CHAR (first orchestrator-run characterization of the V177 cap-fade family)
**Prior papers on this surface:** none
**Filename:** `RESEARCH_PAPER_ALT_CAP_FADE_DOGEUSDT_1H_v1_CHAR_2026-06-14.md`
**Terminal:** ARCHETYPE_EXHAUSTION (operator-directed levers both settled; no credible next experiment in envelope)
**Goal status:** NOT HIT
**Hypothesis:** `9795b726-773d-4fd8-a93b-98dcee061d9c` (operator-directed, ACTIVE)
**Queue(s):** `3720bf72` (DOGE), `7db97e53` (SOL); XRP iter da493632 + WF from prior session

---

## TL;DR

Operator-directed study of two DSR-lift levers within the established envelope: (a) full 2017->now BTC/ETH
price-action history, (b) multi-coin universe breadth via the V177 altcoin capitulation-fade family. BOTH levers
were tested honestly and BOTH fail the same way: they add regime diversity but NOT enough EVENTS to clear a
deflated-Sharpe-significant edge. The deep -15%/12h capitulation is too rare per single coin to validate
out-of-sample (XRP: 2 OOS trades, DSR 0.0002; DOGE, the strongest coin: 10 OOS trades, DSR 0.22; both vs the
0.95 gate). The full-2017 lever was already settled the same day on DCB ETHUSDT 4H (n=35 over 8.85yr, DSR 0.13,
8.1%/yr - all sub-gate). No graduation-grade candidate. Breadth/depth DOES lift the IN-SAMPLE DSR (XRP null at
n=9 -> DOGE 0.793 at n=41) and adds bull/neutral-regime coverage, but the edge does not survive out-of-sample on
any single coin, and the orchestrator has no native cross-coin event-pooling to assemble a real n>=100 sample.

| coin / surface | events (IS / OOS) | honest DSR | PF 95% CI low | CAGR@90 | WF verdict |
|---|---|---|---|---|---|
| ALT_CAP_FADE_XRP  1H  | 9 / 2  | null IS / 0.0002 OOS | 1.56 | 17.4%/yr | INSUFFICIENT_EVIDENCE |
| ALT_CAP_FADE_DOGE 1H  | 41 / 10 | 0.793 IS / 0.22 OOS | 1.30 | 33.5%/yr | INSUFFICIENT_EVIDENCE |
| ALT_CAP_FADE_SOL  1H  | 12 / -  | null | 0.31 (FAIL) | 1.3%/yr | not run (sub-gate IS) |
| DCB ETHUSDT 4H (lever a, prior session) | 35 / - | 0.134 | 1.45 | 8.1%/yr | INSUFFICIENT_EVIDENCE |

---

## 1. Background

The operator established a feasibility envelope and asked whether EITHER full 2017 BTC/ETH history OR multi-coin
breadth could lift a strategy Deflated Sharpe toward the V11 0.95 gate. ALT_CAP_FADE was the operator one
clean survivor (buy alt after deep ~-12/-15%/12h crash, hold ~24h, long/flat spot; +ve all 5yr, ~140 events,
~71% win in earlier price-proxy work). V177 (master 5dde9e8) shipped CapitulationFadeStrategyEngine + six
research-mode per-alt codes. A prior session pre-registered hypothesis 9795b726 and obtained a STRONG XRP
motivating iteration (da493632). This session continued that hypothesis (resume branch 5).

## 2. Hypothesis

**Mechanism:** Long/flat, never short. ENTER LONG when trailing-12h return r12 = price(t)/price(t-12)-1 <
thetaReturn (default -0.15, a deep capitulation); HOLD exactly maxHoldBars (24) bars; exit flat; non-overlapping.
Binary sizing, bar-close-only exits. Three sweep params (thetaReturn / lookbackBars / maxHoldBars). Low
degree-of-freedom by design (good for DSR multiplicity).

**Pre-registration:** hypothesis 9795b726 (ACTIVE, operator-directed), explicitly anticipating that V11 n>=100
cannot evaluate a rare-event strategy and that the LOW-FREQUENCY walk-forward (DSR on OOS daily-equity) is the
correct evaluator. Falsification: equity-curve DSR < 0.95 OR fold-positive < 60% OR OOS-edge collapse.

**Type:** ALGO.

## 3. Methodology

### 3.1 Statistical gates (V11 + V60) - UNCHANGED, NOT loosened
n_trades >= 100; PF 95% bootstrap CI lower > 1.0; DSR (Bailey-LdP, cumulative-trial deflation) >= 0.95;
ag90 >= 10%/yr; walk-forward ROBUST. The retired +20bps slippage check was NOT enforced.

### 3.2 Rare-event evaluation path (no gate loosening)
The standard graduation review hard-codes n>=100 (BLOCKER) + trade-level DSR (BLOCKER) - structurally
inapplicable to a rare-event strategy. The graduation review for XRP was run honestly and REJECTED (2 blockers:
n_trades_ample n=9<100, dsr_threshold null) - documented, not bypassed. The honest evaluator is the walk-forward
LOW-FREQUENCY track (is_low_frequency rate<52/yr): DSR>=0.95 measured on the OOS daily-equity return series with
autocorrelation-adjusted effective N (Lo 2002) and PER-OBSERVATION Sharpe (the 2026-06-09 annualization-bug fix
is applied - so no inflation), fold-positive>=60%, return CV<=2.5, bear-coverage, >=8 trades, >=30 daily obs.
The walk-forwards were run with pool_candidate=True, which LEGITIMATELY skips the graduation-review gate (Signal
Pool / House Book lane has its own gate). override_review_gate was NOT used.

### 3.3 Cost realism
feeRate 0.00075 (7.5bps/side ~ 15bps RT) + JVM default slippage. Cost-irrelevant for this low-turnover family.

## 4. Parameter space
Characterization runs used the seeded defaults (thetaReturn -0.15, lookbackBars 12, maxHoldBars 24). DOGE/SOL
were run with backtest_window.start_time set to their full history (DOGE 2020-01, SOL 2022-01) to avoid the
JVM default 2024-01 truncation that previously produced artifact verdicts.

## 5. Results

### 5.1 XRP (iter da493632; WF 79d9745b)
In-sample: ann_geom@90 17.36%/yr, PF 8.89 (CI [1.56, 12.32]), win 88.9%, maxDD 10.9%, n=9, DSR null. Regime:
BEAR 7/9, NEUTRAL 2/9 - bear-concentrated, ZERO bull trades. Low-freq WF (2022-01, 6 folds): only 2 trades
fired across ALL 6 OOS windows (4 folds zero entries); OOS-equity DSR 0.0002, fold-positive 33.3%.
=> INSUFFICIENT_EVIDENCE.

### 5.2 DOGE (iter 4b49aeba; WF a8f31090) - STRONGEST coin
In-sample (full 2020-01, 2355d): ann_geom@90 33.46%/yr, geom@90 +544%, PF 2.79 (CI [1.30, 7.58]), win 63.4%,
Sharpe_ann 0.98, maxDD 25.4%, n=41, DSR 0.793 (NON-null - clears the >=30-obs floor). Regime: BEAR 22 (72.7%
win), BULL 7 (57.1%), NEUTRAL 12 (50%) - fires across ALL THREE regimes. Low-freq WF (2020-06, 8 folds): only
10 trades across 8 OOS windows (1-3/fold, 2 zero); OOS-equity DSR 0.2213, fold-positive 62.5%, per-obs Sharpe
0.034. The in-sample DSR 0.793 does NOT survive OOS. => INSUFFICIENT_EVIDENCE.

### 5.3 SOL (iter 35d1f6d5) - WEAKEST coin
In-sample (2022-01): PF 1.20 (CI [0.31, 5.37] - FAILS >1.0), ann_geom@90 1.26%/yr (FAILS 10%), win 58.3%, n=12,
DSR null. Regime: BEAR 11, NEUTRAL 1 - bear-only. Sub-gate in-sample; WF not run.

### 5.4 Lever (a) precedent - DCB ETHUSDT 4H full-2017 (prior session, queue 153769aa)
12-cell sweep over genuine 2017-08-17->now (8.85yr). Best cell PF 3.47 (CI [1.45, 9.49]), DSR 0.1343, ag90
8.12%/yr, n=35 - all sub-gate. Root cause: a 4h trend strategy fires ~30 trades over 8.85yr. Same event-count
limit as the cap-fade family.

## 8. Walk-Forward
XRP WF 79d9745b = INSUFFICIENT_EVIDENCE (OOS DSR 0.0002, 2 trades). DOGE WF a8f31090 = INSUFFICIENT_EVIDENCE
(OOS DSR 0.22, 10 trades). Both honest low-frequency tracks; both fail the OOS-equity DSR>=0.95 bar by a wide
margin because the OOS test windows fire too few capitulation events.

## 10. Methodology Compliance Audit
- V11/V60 gates NOT loosened. Graduation review run honestly (XRP REJECTED, documented).
- override_review_gate NOT used. Walk-forwards used the legitimate pool_candidate lane.
- DSR is annualization-correct (per-obs Sharpe + Lo-2002 n_eff; the bug that previously inflated low-freq DSR is
  fixed and the honest numbers here are low BECAUSE the fix is in force).
- Cost realism: feeRate 0.00075 + slippage. Pre-registration: hypothesis 9795b726 predates all iterations.
- No live mutation; all codes enabled=false simulated=true on research account.

## 11. Conclusions
1. Neither operator lever lifts any low-turnover strategy DSR over 0.95. The binding constraint is EVENT COUNT
   (n), not regime diversity - both 2017-history and multi-coin breadth add regimes but not enough independent
   events for a deflated-Sharpe-significant edge.
2. Breadth/depth DOES help directionally: XRP DSR null (n=9) -> DOGE DSR 0.793 (n=41) in-sample, and DOGE adds
   bull/neutral coverage. But the edge collapses OUT-OF-SAMPLE on every single coin (OOS DSR 0.0002 / 0.22).
3. The deep -15%/12h capitulation is genuinely real but structurally rare - even DOGE (deepest history, highest
   vol) fires only ~10 events in 8 OOS test quarters. No single coin is graduation-ready or pool-admissible.
4. The ONLY path to the gate is a genuinely POOLED ~100-150-event sample across the 6 alts. The orchestrator/
   engine cannot produce this today (one (code,symbol) per backtest/walk-forward; the universe field routes to
   the XS long-short coordinator, which is the wrong mechanism for a per-symbol long/flat timed-hold fade). This
   is operator-committed engine work - STOP-AND-REPORT (hard rule). Even pooled, the alts market-wide-flush
   correlation will discount the effective independent-event count below the raw sum.
5. ALT_CAP_FADE family = REAL-BUT-UNDERPOWERED on the current universe/mechanism. Keep the V177 codes seeded;
   do NOT iterate single-coin params further (p-hacking risk on n<50 samples).

## 12. Data / Capability Wishlist
- POOLED capitulation-fade backtest: a CapitulationFade engine/coordinator mode (or orchestrator multi-symbol
  aggregation) that assembles ONE n>=100 event sample across the 6 alts with a shared equity curve, so the
  honest pooled DSR can be measured. This is the precise unlock for operator lever (b).
- Alternatively: plumb more high-beta alts (ADA/AVAX already seeded for cap-fade only) AND a longer SOL 1h
  history (currently 2022+), to grow the per-coin event count.

## 13. Appendix - iteration / run ids
XRP iter da493632 (bt 2309a25c), WF 79d9745b. DOGE iter 4b49aeba (bt ee9f6e92), WF a8f31090.
SOL iter 35d1f6d5. DCB-ETH-4H best cell iter fb46d768 (queue 153769aa, prior session).
Journal: hyp 9795b726; outcomes 7e4488b8 (XRP WF), 58d67c21 (DOGE char), f89ba1ee (SOL char),
54b67402 (DOGE WF). Graduation review target graduation:da493632 = REJECTED.
