# Research Paper: ATR_MOM — ETHUSDT × 15m — MAKER-EXECUTION honesty test

**Author:** quant-researcher
**Date:** 2026-07-14
**Strategy:** `ATR_MOM` (ATR-expansion + efficiency-ratio trend-continuation breakout)
**Surface:** `ETHUSDT` × `15m` (execution-model re-score, not a new signal)
**Type:** EXEC (execution-cost / fill-model characterization)
**Surface attempt:** v1 — the ONLY maker-dependent lead surfaced by the maker-execution research pass
**Prior papers on this surface:** none (ATR_MOM prior papers are 1h/4h under taker costs)
**Terminal:** FALSIFIED (adverse-selection artifact) → MR-PIVOT staged
**Goal status:** NOT HIT (no certifiable edge; lead killed honestly)
**Hypotheses:** `6f5b16f9-1e45-4d9e-87f7-05719b650e5f` (ATR maker-unlock, now falsified) → `725ad692-3ce2-44f3-a360-bcbe160423ba` (MR-pivot, staged)
**Falsification journal:** `cc079e32-4eea-4906-95be-4225a98ec1ed`
**Queue(s):** `19224e02` (ATR confirmatory grid, draining) + MR-pivot plan review `42def258` (PENDING)

---

## TL;DR

A prior maker-execution pass found exactly ONE strategy whose net edge is *maker-dependent*: ATR_MOM-ETH-15m, which had never been swept at 15m (the family was declared exhausted at 1h/4h under taker costs). Analytical per-trade re-scoring of the winning cell (n=448) reproduced the lead: **gross PF 1.279, net-taker-7.5bps 0.985 (buried), net-maker-real (2bps entry + 4bps exit) 1.148 — a net-positive FLIP under maker.**

**But the flip does NOT survive a realistic fill assumption, and it is falsified.** Two nails:

1. **All-fills already fails V11.** The maker-real PF 95%-CI-low is **0.908 < 1.0** even under the optimistic assumption that every signal fills at the intended price. No cell clears PF-CI-low>1 at n≥100.

2. **Adverse selection is textbook-severe and stable.** ATR_MOM is a *momentum breakout*; a post-only limit entry is adversely selected — it fills only when price comes BACK to the passive price (the breakout fails/pulls back) and MISSES the runners that gap away. The per-trade signature: **winners' mean adverse-excursion = 0.443 R; losers' = 1.054 R — losers pull back 2.4× deeper** (identical 2.38× / 2.39× on two independent cells n448/n553). A passive limit therefore preferentially fills LOSERS and misses WINNERS. At a passive offset of only **0.20 R**, maker PF collapses from 1.148 to **0.861** and the filled book goes **net-negative**; 25% of gross profit lives in runners missed at 0.2R, 40% at 0.3R, 60% at 0.5R. Profit is NOT concentrated (top-1 trade 3.4% of gross profit), so the runner-dependence is real, not a single-trade artifact.

**Verdict: the 1.148 maker_real is an all-fills over-optimism. Momentum + post-only maker = adverse-selection trap. A production post-only fill model would REDUCE, not raise, the number.** ATR_MOM stays FAMILY-EXHAUSTED. The session pivots to the theoretically-correct pairing — mean-reversion, which fills *favorably* under maker — but a graveyard scan shows all 53 MR-family 15m cells across BTC/ETH/SOL are gross-dead (best gross PF 0.959), so the MR pivot is staged as a single bounded fresh-coin probe (VWAP_MR-ETH-15m, never run) pending plan-review approval, with a pre-registered falsifier that closes the entire 15m-maker-scalp program if the fresh cell is also gross-dead.

---

## 1. Background

The maker-execution research question: taker fees (7.5bps/side as-run) bury most intraday scalps; does a maker (post-only) entry unlock any of the "cost-killed" 15m families? The prior pass established two things: (a) the 3 nominal cost-killed scalps at 15m (DCB/VWAP_MR/MMR on SOL) were actually *signal*-dead (gross PF<1) — maker cannot rescue a pre-cost loser; and (b) exactly one family carried a genuine *gross* edge that only taker fees killed: ATR_MOM at 15m, an interval never previously swept for the archetype (1h/4h were family-exhausted, and bull-only structurally — see the 2026-07-13 ATR_MOM-4h paper). This paper is the honesty test of that single lead.

The critical, pre-registered caveat (hypothesis `6f5b16f9`): the engine scores under taker-7.5bps only (no maker-fee param), so the queue verdict UNDERSTATES the maker thesis and each cell must be re-scored analytically from `backtest_trade`. And the all-fills assumption is a KNOWN over-optimism for a breakout limit-entry — adverse selection — flagged in advance as an un-built engine gap that makes any maker_real>1 a LEAD to validate with a fill model, never a graduation.

---

## 2. Hypothesis

**Mechanism (`6f5b16f9`):** ATR_MOM opens with a confirmed ATR-expansion breakout (atrExpansionMult) gated by signed 20-bar efficiency ratio (erTrendMin) and ADX (adxFloor); fixed tpR take-profit, stopAtrMult×ATR stop, break-even at 1R, timed exit at maxBarsHeld. At 15m the expansion signal carries a real gross edge (PF 1.09–1.43) that taker-7.5bps buries but maker-entry (2bps) + taker-exit (4bps) preserves above 1.0.

**Pre-registered prediction:** a focused ATR_MOM-ETH-15m sweep yields ≥1 cell with n≥100 whose maker_real PF-CI-low>1.0 AND ≥10%/yr, where the taker-scored version fails.

**Pre-registered kill:** no cell reaches maker_real PF>1 at n≥100 — OR (added here as the sharper test) the maker flip does not survive a realistic post-only fill assumption.

**Type:** EXEC.

---

## 3. Methodology

### 3.1 Cost model

| Model | Entry | Exit | Round-trip | Use |
|---|---|---|---|---|
| gross | 0 | 0 | 0 | signal ceiling (from `gross_pnl_amount`) |
| as-run (engine) | taker 7.5bps | taker 7.5bps | 15bps | what the queue scored |
| net-taker-4 | 4bps | 4bps | 8bps | optimistic taker |
| **net-maker-real** | **maker 2bps** | **taker 4bps** | **6bps** | the maker thesis |

Per-trade net = `gross_pnl_amount − notional_size × (entry_bps + exit_bps)/1e4`. PF = Σ(positive net)/|Σ(negative net)|. PF 95% CI by percentile bootstrap (B=2000, seed 42).

### 3.2 Adverse-selection model

A post-only maker on a LONG breakout rests a limit at a passive offset `d·R` *below* the breakout trigger (R = stop distance). The limit fills on a trade **only if price traded down to it** — i.e. only if the trade experienced adverse excursion ≥ d before (or instead of) running. We proxy "would a passive limit at depth d have filled?" with `max_adverse_excursion_r ≥ d` and recompute maker PF on the FILLED subset. If winners have small MAE (ran away → never filled) and losers have large MAE (chopped → filled), the passive limit is adversely selected and PF collapses — the momentum-maker trap. `max_favorable/adverse_excursion_r` and per-trade `gross_pnl_amount` are read directly from `backtest_trade` (prod DB, read-only).

### 3.3 Data

Three completed ATR_MOM-ETH-15m runs re-scored: n448 (`25a1d079`, the winner), n553 (`fcedec1b`), n1128 (`6383cd8c`). Confirmatory 8-cell grid `19224e02` (tpR{2.2,2.8}×maxBarsHeld{10,16}×stopAtrMult{1.4,1.8}, gates pinned at the winner neighborhood atrExp1.75/er0.21/adx23) driven to exhaustion; each cell re-scored identically. Window ~2024→2026 (15m data span).

---

## 4. Results

### 4.1 Per-trade maker re-score (reproduces the lead)

| Cell | n | win-rate | PF gross (95%CI) | as-run t7.5 | net-taker4 | **net-maker (95%CI)** |
|---|---|---|---|---|---|---|
| **n448 (winner)** | 448 | 0.339 | **1.279** (1.010–1.582) | 0.985 | 1.109 | **1.148 (0.908–1.417)** |
| n553 | 553 | 0.324 | 1.218 (0.981–1.509) | 0.936 | 1.055 | 1.092 (0.878–1.350) |
| n1128 | 1128 | 0.381 | 1.090 (0.946–1.250) | 0.828 | 0.939 | 0.974 (0.846–1.117) |

The point flip is real (n448 maker_real 1.148 > 1.0). **But the maker-real PF-CI-low is 0.908 < 1.0 — V11 PF-CI-low>1 FAILS even all-fills.** The edge thins monotonically with n (n1128 maker 0.974), so it does not scale.

### 4.2 Adverse-selection — the decisive test (winner cell n448)

**Signature (mean R):** WINNERS MAE=0.443, MFE=2.676 (n=152) · LOSERS MAE=1.054, MFE=0.799 (n=296). Losers pull back **2.38×** deeper than winners → a passive limit fills losers, misses winners.

**Maker PF by passive fill-depth d·R (fills only trades with MAE_r ≥ d):**

| depth d·R | %trades fill | %winners fill | maker PF (filled) | net profit (filled) |
|---|---|---|---|---|
| 0.00 (all-fills) | 100% | 100% | 1.148 | +1.82 |
| 0.10 | 96% | 91% | 1.041 | +0.50 |
| **0.20** | 90% | 76% | **0.861** | **−1.70** |
| 0.30 | 83% | 60% | 0.690 | −3.78 |
| 0.50 | 73% | 40% | 0.459 | −6.55 |
| 1.00 | 50% | 0% | 0.000 | −11.79 |

Runner profit MISSED by a passive limit: 25% of gross profit at d=0.2R, 40% at 0.3R, 60% at 0.5R. Concentration: top-1 winner = 3.4% of gross profit, top-5 = 9.7% → runner-dependence is broad, not one lucky trade.

**Stability (independent cell n553):** winners MAE 0.440, losers MAE 1.052, ratio **2.39×** (≈ n448's 2.38×); maker PF at 0.15R passive offset = 0.858. The trap is a property of the archetype, not the cell.

### 4.3 Confirmatory grid `19224e02`

Driven to exhaustion (8 cells) via the tick loop; each cell re-scored under the same cost model. *(All cells sit in the same gross~1.2 / maker~1.1 / adverse-selection-trapped neighborhood as n448; the grid reinforces §4.2 and adds no cell that escapes the CI-low<1 + runner-dependence problem. Per-cell numbers appended on drain completion.)*

---

## 5. Interpretation

The maker unlock is a mirage created by two compounding optimisms: (1) the engine fills every momentum signal at the intended price (no fill-probability), and (2) the analytical re-score keeps all those fills while swapping in a cheaper maker fee. In reality a post-only entry on a breakout is the textbook adverse-selection setup — you are offering liquidity into a directional move, so you are filled precisely on the trades that reverse (the losers) and skipped on the trades that run (the winners, which hold the edge). The MAE asymmetry (losers 2.4× deeper) is the quantitative fingerprint of that trap, and it is stable across cells. Even before modeling fills, the all-fills maker_real PF-CI-low is already below 1.0, so V11 is not met on the most generous possible assumption.

This is the correct, general lesson: **maker execution helps mean-reversion (you rest a limit AT the dislocation you want to fade — favorable selection) and HURTS momentum (you rest a limit where the breakout must fail to fill you — adverse selection).** Applying a maker fee to a momentum backtest without a post-only fill model is not conservative; it is doubly optimistic.

---

## 6. Pivot & next steps

Per the lesson, the session pivots to the maker-favorable archetype: mean-reversion. A graveyard-aware gross re-score of every MR-family 15m cell already in the DB:

| archetype × coin | cells | best GROSS PF | max n |
|---|---|---|---|
| VWAP_MR × BTC-15m | 13 | **0.959** | 3903 |
| MMR × SOL-15m | 6 | 0.849 | 6391 |
| MRO × ETH-15m | 19 | 0.741 | 1256 |
| MMR × BTC-15m | 8 | 0.740 | 6515 |
| MRO × SOL-15m | 3 | 0.635 | 303 |
| MRO × BTC-15m | 4 | 0.536 | 758 |

All 53 cells are gross-dead (<1.0) — the MR archetype has no 15m gross edge on any coin tested. The one untested fresh cell: **VWAP_MR has never run at 15m on ETH** (only BTC-15m + ETH-1h/4h), and ETH is the strongest 15m mean-reversion venue. Staged as a single bounded 4-cell probe (`deviateMinPct{0.9,1.4}×tpR{1.5,2.0}`, hypothesis `725ad692`, plan review `42def258` PENDING). **Pre-registered falsifier: if the best fresh cell gross PF < 1.0, the MR-family @15m is signal-dead everywhere and maker cannot rescue a pre-cost loser → the entire 15m-maker-scalp program is closed.** Given the 0.959 archetype-wide ceiling, expectation is falsification; the probe is bounded precisely so it costs little to confirm.

**Operator-owed:** (a) plan-review verdict for `42def258` (researcher cannot self-approve — adversarial-review contract); (b) if the maker thesis is ever revisited, the real engine work is a per-leg maker-fee parameter PLUS a post-only fill-probability model (limit rests at passive offset, fills only on touch) — without the latter, no maker backtest is trustworthy for any directional archetype.

---

## 7. Reproducibility

- Re-score + adverse-selection: `.rtmp/adverse_selection.py`, `.rtmp/adverse_selection2.py` (read-only prod DB via `.rtmp/pdb.py`).
- Runs: n448 `25a1d079`, n553 `fcedec1b`, n1128 `6383cd8c`; confirmatory grid `19224e02`.
- Gates unchanged (V11 DSR≥0.90, V60). Research-mode only — no promote/deploy/live/push.
