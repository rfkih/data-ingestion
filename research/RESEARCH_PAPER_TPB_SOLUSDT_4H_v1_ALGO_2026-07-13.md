# Research Paper: TPB — SOLUSDT × 4h (with ETHUSDT/BTCUSDT/BNBUSDT/XRPUSDT transfer study)

**Author:** quant-researcher
**Date:** 2026-07-13
**Strategy:** `TPB` (TrendPullbackEngine, archetype=trend_pullback)
**Surface:** `SOLUSDT` × `4h` (primary); ETHUSDT/BTCUSDT/BNBUSDT/XRPUSDT × 4h + SOLUSDT × 1h (secondary)
**Type:** ALGO
**Surface attempt:** v1 — ALGO (first TPB campaign on the operator-seeded trend-pullback surfaces; the two-sidedness test after ATR_MOM's structural bull-only falsification)
**Prior papers on this surface:** none (first TPB paper)
**Filename:** `RESEARCH_PAPER_TPB_SOLUSDT_4H_v1_ALGO_2026-07-13.md`
**Terminal:** ARCHETYPE_EXHAUSTION
**Goal status:** NOT HIT (0/32 SIGNIFICANT_EDGE — n is the binding gate on every runnable surface)
**Hypothesis:** `4e941275-cd35-40a2-94fa-4b3b1542313c`
**Queue(s):** `7bd7c3a0` (SOL r1), `95008622` (ETH r1), `2bf9d542` (SOL r2), `78ad0585` (ETH r2, 2018 window), `6dffdfd7` (SOL r3 exit), `317ed1d5` (BTC), `254fa6af` (BNB), `6b512ca3` (XRP)

---

## TL;DR

TPB trend-pullback was tested as the structurally two-sided directional archetype after ATR_MOM's
bull-only falsification. The central question — does the SHORT side fire and profit in bear
regimes — is answered YES: on SOLUSDT@4h the bear-regime bucket fired in 18/18 sweep cells
(n 10–24 per cell) and was profitable in 18/18; on XRPUSDT@4h it was profitable in 4/4; the
edge is in fact BEAR-CARRIED. The let-winners-run exit (tp1R 3.0 + phase-3 trail 3.0×ATR)
roughly doubles economics — best SOL cell PF 2.40, ann90 +11.2%/yr — and the SAME exit corner
independently wins on XRPUSDT (PF 1.74), a genuine cross-coin confirmation. The strategy is
nonetheless UNCERTIFIABLE per-surface under V11: qualifying pullbacks occur ~4–6×/yr/coin at
4h (n ≤ 38 everywhere over 5.5 years), the 1h interval is dead (null-screen NO_EDGE, median
PF 0.90), ETHUSDT fails cross-window (2018 bear reverses the 2021-window plateau), and BNBUSDT's
bear side is negative. The only n ≥ 100 path is a fixed-config pooled book (SOL+XRP+BTC+BNB
= 109 trades at the pre-registered (3.0, 3.0) config) via a DCB_POOL-style orchestrator-side
pooled certification — an operator decision.

---

## 1. Background

Session start state: prior run (2026-07-12) terminated on ARCHETYPE_EXHAUSTION after falsifying
MRO/MMR band-fade (inverted on BTC/ETH/SOL) and ATR_MOM continuation (structural BULL-ONLY defect:
its long-confirm gate produced ≈0 BEAR trades even across SOLUSDT's −96% 2022). Its #1
data-wishlist item — TPB trend_pullback account_strategy rows — was provisioned by the operator
on 2026-07-13 (research account 99999999-…-0002, ETHUSDT@4h + SOLUSDT@4h, disabled+simulated,
allow_long=TRUE, allow_short=TRUE). DCB_POOL is certified and shipped (closed). TPB was selected
because it is the only runnable archetype with a structurally MIRRORED short path: bear bias gate
= EMA50<EMA200 AND close<EMA200 on the bias timeframe, mirrored RSI (40–62) and CLV bands —
exactly the axis ATR_MOM could not traverse.

## 2. Hypothesis

**Mechanism:** TrendPullbackEngine enters WITH the prevailing EMA50/200 trend after a
counter-trend pullback touches EMA20 (within pullbackTouchAtr×ATR), confirmed by candle quality
(body/range ratio, close-location-value band, relative volume), ADX bands (entry min/max + bias
min/max) and DI spread; exit = TP1 at tp1R×risk plus a break-even-shifted, phase-staged ATR
runner trail. Long and short paths are structural mirrors.

**Pre-registration:** hypothesis `4e941275-cd35-40a2-94fa-4b3b1542313c` registered
2026-07-13T~02:39 (server 2026-07-12T19:39), before the first sweep iteration (~02:58; gap ≈ 19
min, null-screens in between). Falsifiers stated up front: (a) SHORT side ≈0 trades with
loosened gates → structural one-sidedness; (b) shorts fire but PF ≤ 1.0 after ~9bps taker cost;
(c) n < 40 even at the loosest credible config → power-dead at 4h.

**Type:** ALGO.

## 3. Methodology

### 3.1 Statistical Gates (V11 + V60)

n ≥ 100, PF 95% bootstrap CI lower > 1.0, DSR ≥ 0.90 (operator methodology decision 2026-06-15),
SIGNIFICANT_EDGE, mission GOAL bar ann90 ≥ 10%/yr + walk-forward ROBUST. All fixed; none loosened.

### 3.2 Sweep Design

- **Type:** GRID (confirmatory), null-screen (K=8 random draws) before every NEW surface.
- **Backtest windows:** 2021-01-01 → 2026-07-11 (SOL/BTC/BNB/XRP; spans 2021 bull, 2022 bear,
  2023 chop, 2024-26); 2018-01-01 → now (ETH round 2, adds the independent 2018 bear);
  null-screens run the pinned default 2024-01-01 → now window.
- **Dimensions traversed (6):** entry trend-strength (adxEntryMin 18/20/22/25), entry ADX
  ceilings (adxEntryMax 45/60, biasAdxMax 40/60), pullback depth (pullbackTouchAtr 0.5/0.8),
  candle-quality floors (rvolMin, bodyRatioMin), exit (tp1R 2.0/2.5/3.0 × runnerAtrPhase3
  1.8/3.0), window (2021 vs 2018), interval (4h vs 1h screen), cross-coin (5 symbols).
- **Total cells:** 32 sweep iterations (iters 47–96) + 5 null-screens (40 exploratory draws,
  all recorded in hypothesis_audit as NULL_SCREEN_DRAW — DSR multiplicity preserved).

## 4. Parameter Space Explored

| Axis | Values Tested |
|---|---|
| `adxEntryMin` | 18, 20, 22, 25 |
| `adxEntryMax` | 45 (default), 60 |
| `biasAdxMin` | 18 |
| `biasAdxMax` | 40 (default), 60 |
| `pullbackTouchAtr` | 0.40 (default), 0.5, 0.8 |
| `rvolMin` | 0.85, 0.9 |
| `bodyRatioMin` | 0.30, 0.35 |
| `minSignalScore` | 0.50 |
| `maxEntryRiskPct` | 0.06 |
| `tp1R` | 2.0, 2.5, 3.0 |
| `runnerAtrPhase3` | 1.8, 3.0 |
| window | 2021→now, 2018→now (ETH) |
| interval | 4h (sweeps), 1h (null-screen only) |
| symbol | SOL, ETH, BTC, BNB, XRP |

**Total iterations:** 32 (all V11-audited; plus 40 null-screen draws in the trial counter).

**Edge verdict distribution:**

| Verdict | Count |
|---|---|
| SIGNIFICANT_EDGE | 0 |
| INSUFFICIENT_EVIDENCE | 32 |
| NO_EDGE_DETECTED (DISCARD) | 0 |

## 5. Results

### 5.1 Edge summary

The two-sidedness question is settled: TPB's trade flow at 4h is BEAR-DOMINANT (most entries
occur in entry_trend_regime=BEAR) and the bear bucket is profitable on SOLUSDT in 18/18 cells
(round-1 PnL +69..+395, round-2 +185..+474, round-3 up to +634) and on XRPUSDT in 4/4 cells
(+100..+332). This is the exact opposite of the ATR_MOM failure mode — the trend_pullback
archetype's mirrored bias gate genuinely confirms crypto downtrends. Findings by axis:
(1) `adxEntryMin` — 18 is too loose on ETHUSDT (bear bucket net-negative at −127..−272); the
adx 20–22 region is a PLATEAU profitable on both SOL and ETH-2021w (10/10 cells PF > 1.1), not
a spike. (2) ADX ceilings — widening `biasAdxMax` 40→60 admits the strongest-trend entries and
lifts SOL PF 1.22→1.87 at unchanged n; count is unchanged (~5 entries/yr/coin — frequency is
entry-structure-bound, not gate-bound). (3) Exit — the DCB let-winners-run lesson transfers:
(tp1R 3.0, runnerAtrPhase3 3.0) is the best corner on BOTH SOL (PF 2.40, ann90 11.24) and XRP
(PF 1.74, ann90 7.18); on BTC that corner fails (PF 0.85) while (3.0, 1.8) wins (PF 1.45) —
exit surfaces are coin-dependent, so pooled designs must pre-register ONE fixed config.
(4) Window — ETHUSDT's 2021-window plateau (PF 1.12–1.50) REVERSES on 2018→now (7/8 cells
PF 0.48–0.90): the ETH bear edge was window-specific; an explicit regime-of-one caveat for SOL
(its only in-window bear is 2022). (5) Interval — SOLUSDT@1h null-screen NO_EDGE_DETECTED
(median PF 0.898, P95 1.155, 0/8 draws ≥ 1.2): frequency does NOT scale down-interval because
the 4h bias gate still throttles entries while 1h noise/cost destroys per-trade edge.
**Binding constraint everywhere: frequency starvation (n ≤ 38 per surface over 5.5 years).**

### 5.2 Best cell (SOLUSDT@4h, round 3 — anchors future comparisons)

| Param | Value |
|---|---|
| `adxEntryMin` / `adxEntryMax` | 20 / 60 |
| `biasAdxMin` / `biasAdxMax` | 18 / 60 |
| `pullbackTouchAtr` | 0.40 (engine default) |
| `rvolMin` / `bodyRatioMin` | 0.85 / 0.30 |
| `minSignalScore` / `maxEntryRiskPct` | 0.50 / 0.06 |
| `tp1R` / `runnerAtrPhase3` | 3.0 / 3.0 |

| Metric | Value |
|---|---|
| iteration | #84 (queue 6dffdfd7, 2026-07-13) |
| n_trades | 22 |
| PF (point) | 2.397 |
| PF 95% CI | not computed at this n (below CI reliability floor) |
| DSR | not computable at n=22 |
| ag90 (%/yr) | +11.24 |
| BEAR bucket | n=17, PnL +634 |
| Statistical verdict | INSUFFICIENT_EVIDENCE |

Caveat: best-at-grid-corner on a 2×2 exit grid at n=22 — a direction check consistent with the
independent XRP result, not a fitted optimum.

### 5.3 Cross-coin transfer map @4h (fixed plateau entry, exit grid 2×2, 2021→now)

| Symbol | Null-screen | Sweep result | Bear bucket | Disposition |
|---|---|---|---|---|
| SOLUSDT | INCONCLUSIVE | PF 1.15–2.40 across 18 cells | positive 18/18 | CORE |
| XRPUSDT | EDGE_PRESENT (med 1.46) | PF 0.92–1.74; best = same corner as SOL | positive 4/4 | CONFIRMS |
| BTCUSDT | EDGE_PRESENT (med 1.55) | PF 0.85–1.45; best at different exit | positive 3/4 | PARTIAL |
| ETHUSDT | EDGE_PRESENT (med 1.44) | 2021w plateau OK; 2018w 7/8 cells PF<1 | negative at loose gates | FALSIFIED (cross-window) |
| BNBUSDT | INCONCLUSIVE (med 0.0) | PF 0.61–1.25 | NEGATIVE 4/4 | DEAD |

Pooled arithmetic at the pre-registered fixed config (3.0, 3.0): SOL 22 + XRP 30 + BTC 36 +
BNB 21 = **109 trades** (including the drag coins — the honest pooled test); the SOL+XRP core
alone = 52 trades at PF 2.40 / 1.74. This is the only visible n ≥ 100 route.

## 9. Infrastructure Notes

Two load-bearing discoveries about the research plumbing (no code changed):
(1) `repo/queue_write.find_account_strategy_id` and `services/tick._resolve_account_strategy`
match on `(strategy_code, account_id)` ONLY — neither interval nor symbol binds. The two seeded
TPB rows therefore support queues on any research-universe symbol/interval; this is what made
the 1h screen and the BTC/BNB/XRP transfer sweeps runnable without new seeds.
(2) `/null-screen` runs the pinned default 2024-01-01 window (no override support), while sweeps
honor `sweep_config.backtest_window.start_time` — screens are edge-sniffs, and window-sensitive
conclusions (like ETH's) require sweep-level windows.

## 10. Methodology Compliance Audit

| Rule | Compliant? | Notes |
|---|---|---|
| 5-coin research universe (hard rule #1) | YES | BTC/ETH/SOL/BNB/XRP only |
| Intervals in {5m,15m,1h,4h,1d} (hard rule #2) | YES | 4h sweeps, 1h screen |
| Live untouched (hard rule #3) | YES | research account rows only, disabled+simulated |
| Research-mode only (hard rule #4) | YES | no promotion calls |
| 10%/yr bar honored (hard rule #5) | YES | no sub-bar candidate advanced |
| V11 + V60 gates honored (hard rule #6) | YES | 32/32 scored INSUFFICIENT_EVIDENCE honestly |
| ≥ 3 dimensions traversed (hard rule #7) | YES | 6 dimensions |
| Pre-registration before testing | YES | hypothesis 19 min before first sweep; null-screens gated every new surface |
| Append-only durable evidence | YES | no row mutated or deleted |
| Reviewer verdict authoritative (hard rule #12) | YES | 3 plan reviews, all APPROVED before /queue |
| No trading JVM calls (hard rule #13) | YES | orchestrator only |

## 11. Conclusions

1. **Two-sidedness confirmed:** the trend_pullback archetype's mirrored bias gate fires and
   profits in bear regimes (SOL 18/18 cells, XRP 4/4) — the ATR_MOM structural defect does not
   recur; the hypothesis's primary prediction is MET.
2. **The edge is bear-carried:** most 4h pullback entries occur in BEAR regimes and that bucket
   contributes the bulk of PnL on the surfaces that work.
3. **Exit is a first-order lever:** letting winners run (TP1 3R + wide phase-3 trail) roughly
   doubles PF/ag90 on SOL and independently wins on XRP — the DCB trailing-exit lesson
   generalizes to pullback entries.
4. **Frequency is structural at 4h:** ~4–6 qualifying pullbacks/yr/coin caps n ≤ 38 per surface;
   loosening entry gates (adx 18) degrades PF instead of buying n; 1h is noise-dead; the ETH 2018
   window falsifies rather than extends.
5. **Certification is pooled-or-nothing:** the only V11 n ≥ 100 route is a fixed-config pooled
   book (109 trades incl. drag coins) via a DCB_POOL-style orchestrator-side pooled pathway —
   an operator decision (pathway approval + drag-coin inclusion rule), not further solo research.
6. **Implication for the loop:** the runnable directional space on the 5-coin universe is now
   fully traversed (this campaign closed the last open archetype's runnable axes); the loop's
   next unlock is operator provisioning, hence the ARCHETYPE_EXHAUSTION terminal with the pooled
   ask as data-wishlist item #1.
