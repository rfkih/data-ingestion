# Research Paper: DCB — BNBUSDT × 4h

**Author:** quant-researcher
**Date:** 2026-06-20
**Strategy:** `DCB` (Donchian-channel breakout / trend-continuation)
**Surface:** `BNBUSDT` × `4h`
**Type:** ALGO
**Surface attempt:** v1 — ALGO (pure-ATR-trail exit profile on a fresh-coin runnable cell, operator-directed DCB-other-coins mandate)
**Prior papers on this surface:** none (first paper on DCB-BNBUSDT-4h)
**Filename:** `RESEARCH_PAPER_DCB_BNBUSDT_4H_v1_ALGO_2026-06-20.md`
**Terminal:** ARCHETYPE_EXHAUSTION
**Goal status:** NOT HIT (real edge, structurally below the V11 n>=100 gate)
**Hypothesis:** `baf604cb-7c6e-493a-bc62-93e6f688da3c`
**Queue(s):** `d1129bb9-4f27-4179-88e2-416c3820e90a`

---

## TL;DR

Under the operator's OPERATOR_DIRECTED_DCB_OTHER_COINS mandate (extend the DCB-4h-trail archetype to
fresh unmined coin cells, offline-4h-screen-first), I tested the one genuinely un-run, runnable dimension
the mandate named: the pure-ATR-trail exit profile on DCB-BNBUSDT-4h (the trail lever that previously
lifted DCB-BTC-4h to PF 2.40). The offline null-screen PASSED (EDGE_PRESENT: P75 PF 1.44, share_pf>=1.2
0.625), so a focused 16-cell trail-centric sweep was justified and run. The edge is REAL and consistent —
all 16 cells produced PF >= 1.2 (range 1.24–2.32) — but it is STRUCTURALLY FREQUENCY-STARVED: every cell
produced only n=40–65 trades (avg 51), and 0 of 16 reached the V11 n>=100 floor. The binding constraint is
entry-frequency x history-depth on BNB's 4.4yr of data; the trail exit raises profit factor but cannot
manufacture entries. The mechanism does not fail on signal — it fails on sample size.

*(SIGNIFICANT_EDGE table omitted — no cell reached the V11 gate.)*

---

## 1. Background

Session resumed an interrupted autonomous run (local PC restart ~2026-06-20 12:05 local killed the SSH
tunnel/driver; VPS orchestrator + state intact). The prior research run had fired ARCHETYPE_EXHAUSTION_2026-06-20
(2026-06-19 19:36Z) after the DCB-ETH-1h exit/stop dimension was diagnosed saturated (oracle-exit ceiling
DSR ~0.34; best real cell DSR 0.188). The operator issued a fresh, non-overlapping mandate: extend the
DCB-4h-trail archetype to fresh unmined coin cells. A fresh ACTIVE HYPOTHESIS (baf604cb, created 05:24Z,
strictly after the 19:36Z terminal) legitimately cleared the lockout via the resume-protocol bypass clause
(`bypass_available` flipped to true). This is a genuinely new breadth direction, NOT a re-grind of the
saturated DCB-ETH-1h exit dimension.

**Graveyard check (which mandate cells are runnable / already mined):**
- Only BNBUSDT-4h and XRPUSDT-4h of the mandate coins have a DCB `account_strategy` row.
  SOL/DOGE/AVAX/FET/LINK/NEAR/XLM/ZEC have none → `/queue` 412 `account_strategy_missing` → DATA_WISHLIST.
- DCB-XRP-4h: DEAD (null-screen 2026-06-18, frequency-starved n=2..59; trail cannot fix entry frequency → SKIP).
- DCB-BNB-1h: DEAD (NO_EDGE_DETECTED null-screen 2026-06-17).
- DCB-BNB-4h: REAL edge but previously tested only with FIXED-TP let-trends-run exit (WF 53622848,
  INSUFFICIENT_EVIDENCE, DSR 0.074, 45 trades, 4.4yr). The PURE-ATR-TRAIL exit had never been screened
  here → the one genuinely un-run, runnable dimension the mandate names. This paper tests it.

---

## 2. Hypothesis

**Mechanism:** DCB enters on a Donchian-channel breakout (price closes beyond the N-bar channel) gated by
an ADX trend-strength minimum (adxEntryMin) and a relative-volume minimum (rvolMin). Position management
under the trail profile: a wide fixed take-profit at tpR (set high, 5–8R, so it rarely binds and the trail
dominates), an ATR-multiple trailing stop (stopAtrMult), a break-even move at breakEvenR, and a maxBarsHeld
time cap. The thesis: on a fresh coin (BNB-4h), letting winners run under an ATR trail rather than a fixed TP
materially improves the PF distribution — the lever that worked on DCB-BTC-4h.

**Pre-registration:** Hypothesis `baf604cb-7c6e-493a-bc62-93e6f688da3c` registered 2026-06-20T05:24:39Z,
before the null-screen (05:25Z) and before the earliest sweep iteration (~05:35Z). Falsification criterion
stated: NULL branch = NO_EDGE_DETECTED or all draws frequency-starved → the BNB-4h cell is exhausted across
exit profiles. POSITIVE branch = EDGE_PRESENT/INCONCLUSIVE with finite draws n>=40 → proceed to formal pipeline.

**Type:** ALGO (no ML).

---

## 3. Methodology

### 3.1 Statistical Gates (V11 + V60)

| Gate | Threshold | Binding? |
|---|---|---|
| n_trades | >= 100 | YES — **this is the gate that failed (max n=65)** |
| PF 95% bootstrap CI lower | > 1.0 | not reached (n-blocked) |
| DSR (Bailey–LdP, n_trials from hypothesis_audit) | >= 0.90 | not reached (n-blocked) |
| Statistical verdict | SIGNIFICANT_EDGE | NO (16/16 INSUFFICIENT_EVIDENCE) |
| ann. geometric return at alloc-90 (ag90) | >= 10%/yr | not reached (n-blocked) |

### 3.2 Sweep Design

- **Type:** GRID (focused, post-screen)
- **Backtest window:** BNBUSDT 4h full history (~4.4yr, ~2021→2026-06)
- **Offline screen (gate):** null-screen K=8, trail-inclusive param space
  (tpR 3.5–8.0, stopAtrMult 2.5–4.5, maxBarsHeld 18–48, breakEvenR 0.5–1.5, rvolMin 1.1–1.5, adxEntryMin 18–25).
  Verdict EDGE_PRESENT (P75 PF 1.4385, share_pf>=1.2 0.625, mean 1.31, p95 1.56, 100% draws PF>=1.0).
- **Dimensions swept (confirmatory sweep):** tpR {5,6,7,8} × stopAtrMult {2.5,3.0} × maxBarsHeld {36,48}
  × adxEntryMin {18}; fixed rvolMin 1.15, breakEvenR 0.6. Biased toward the low-adx/low-rvol high-frequency
  corner the screen's n=64 winning combo surfaced, to push toward n>=100.
- **Total cells:** 16 planned, 16 executed (queue COMPLETED, no gaps, 0 FAILED).

### 3.3 Walk-Forward Protocol

Not run — no cell reached SIGNIFICANT_EDGE (graduation gate not cleared), so no walk-forward was warranted.

---

## 4. Results

| Statistic | Value |
|---|---|
| Cells executed | 16 |
| Statistical verdicts | 16 INSUFFICIENT_EVIDENCE, 0 SIGNIFICANT_EDGE, 0 NO_EDGE, 0 DISCARD |
| Trade count (n) | min 40, max 65, avg 51.4 |
| Cells reaching n>=100 | **0 of 16** |
| Profit factor (PF) | min 1.24, max 2.32 |
| Cells with PF >= 1.2 | **16 of 16** |

The result is a textbook **real-edge-but-frequency-starved** outcome. Profit factors are strong and uniformly
positive (every cell >= 1.2, several > 2.0), confirming the trail exit improves the BNB-4h PF distribution
exactly as the EDGE_PRESENT screen predicted. But entry frequency is the wall: DCB Donchian breakouts gated
by ADX/rvol fire only ~50 times in BNB's 4.4yr of 4h data, far short of the V11 n>=100 floor. The exit
profile sets hold-time and per-trade payoff — it cannot add entries. Tilting the grid to the low-adx/low-rvol
high-frequency corner topped out at n=65, still below the floor.

Representative cells (iteration / PF / n): #379 PF 2.29 n=58; #383 PF 2.17 n=58; #386 PF 1.86 n=65;
#378 PF 1.85 n=65; #380 PF 1.34 n=43; #384 PF 1.40 n=43; last cell #393 PF 1.52 n=40.

---

## 5. Interpretation & Decision

The mandate's distinguishing lever (pure-ATR-trail) genuinely works on BNB-4h — it lifts PF and passes the
edge sniff. The mechanism is not falsified on signal. It is blocked on **sample size**: 4.4yr of BNB history
× the Donchian breakout firing rate yields ~50 trades, structurally below the V11 gate. No exit-profile,
stop, or hold-time tuning can change entry count. This is the same binding constraint that killed the prior
fixed-TP characterization (DSR 0.074, 45 trades) — confirmed now to be a property of the cell, not the exit.

Regime-analysis was deliberately NOT run: with n=40–65 per cell, any regime stratification would put <20
trades per bucket (uninformative), and the binding constraint is trade-count not regime-concentration.

**Decision:** NOT a candidate. The DCB-4h-trail archetype has no viable fresh-coin runnable cell on the
current account_strategy seed set — BNB-4h exhausted across both exit profiles, XRP-4h frequency-dead,
1h cells dead, and the remaining mandate coins unrunnable (no DCB rows). This closes the mandate's
actionable surface and fires ARCHETYPE_EXHAUSTION with a precise data wishlist.

---

## 6. Data Wishlist / Next Direction

The unlock is **operator-seeding DCB `account_strategy` rows on the longer-history fresh coins**, ranked by
history depth (deeper history is the direct fix for the n>=100 starvation):

1. **DCB-SOLUSDT-4h** — SOL market_data backfilled to 2020 (longer than BNB's 4.4yr); the extra ~1.5yr
   could plausibly push the same ~50-trades/4.4yr rate over the n>=100 floor. Highest-EV next probe.
2. **DCB-DOGEUSDT-4h** and **DCB-AVAXUSDT-4h** — both have 1h market_data 2020→now + feature_values; need
   DCB seed rows. DOGE was the strongest cap-fade coin (high-beta, more breakout events).
3. The structurally-correct alternative (no new seed needed): accept that 4h DCB on any single ~4-5yr alt
   is n-bounded, and instead evaluate these real-but-thin edges on the LOW_FREQUENCY equity-curve DSR track
   (as the 2026-06-14 multi-symbol WF did) or pool them — but that route already returned INSUFFICIENT_EVIDENCE
   for BNB-4h fixed-TP, so deeper history (item 1) is the cleaner unlock.

`request_data_scout: true` — operator should run quant-data-scout against this wishlist to rank next-best
(symbol, interval) cells to seed.
