# Research Plan — 2026-06-20 (operator-directed: MTF / trailing / anti-stop-hunt)

**Hypothesis:** `ba62ffee-1732-4a69-b1c7-36b33c5acb08` (DCB)
**Run marker:** OPERATOR_DIRECTED_MTF_TREND_TRAILING_STOP (fresh 8.5h clock)

## Premise (5 lines)
Operator thesis: multi-timeframe trend (1d bias + faster entry), trailing stop tuned to ride the
wave, stops placed away from where retail clusters (anti-stop-hunt). Goal unchanged: 10%/yr ag90 +
walk-forward ROBUST. The operator explicitly warned: test intelligently, do NOT blindly burn DSR;
listed prior findings to not re-burn (standalone intraday trend FALSIFIED; DCB-BTC-1h loses every
config; DCB-ETH-1h fixed-TP already beat trailing at 1h-standalone; /signal-screen unusable intraday).

## State synthesis (from /agent/state + iterations + journal, 2026-06-20)
- No lockout (`lockout_state=null`); operator mandate bypasses the prior ARCHETYPE_EXHAUSTION anyway.
- Queue empty (PENDING=0, RUNNING=0). No Path-C pending. No ML in flight.
- **The operator's exact dimensions were the subject of the last ~6 days of research and are largely
  falsified on the natural substrates:**
  - DCB-BTC-4h pure-ATR-trail (c8ed2de1, 2026-06-19): real edge PF 2.40 ag90 19.3%, **DSR 0.14** — trial-tax DEAD (193 trials).
  - DCB-ETH best lever was regime-ML-gate (iter 339, the "1d-bias" analog): **DSR 0.55** < 0.90.
  - DCB-ETH-1h: irreducibly thin; **oracle-exit ceiling DSR ~0.34** (perfect-foresight exit still sub-gate) → no stop/trail tweak can rescue it.
  - DCB-ETH-4h FALSIFIED 2026-06-14 (all 12 cells n<100, frequency-starved).
  - DCB-XRP-1h conventional grid loses money (PF<1.03, ag90 −7%..−78%); DCB-XRP-4h null-screen frequency-starved; DCB-BNB-1h NO_EDGE.
  - DCB-4h multi-symbol robustness SETTLED 2026-06-14: NONE of BTC/ETH/BNB clears walk-forward.
- **No engine exposes a `bias_interval` knob** (verified DonchianBreakoutEngine + AtrMomentumEngine
  Tuning records) — a true 1d-bias+faster-entry engine cannot be built without an operator-only deploy (hard rule 8).
- **Trial-tax map (DCB):** ETHUSDT 128–185, BTCUSDT 193, BNBUSDT 29–33, XRPUSDT ~6–15. Every new
  cell on ETH/BTC raises the bar; re-grinding is the "blind DSR burn" the operator forbade.

## Constraints reaffirmed
- Universe: ETHUSDT (this plan). Intervals: 1h. Research-mode only (enabled=false, simulated=true).
- Live book untouched. No promotion. No deploy. 10%/yr + ROBUST bar. DSR ≥ 0.90 (V11/V60, absolute-return floor 0.0 per 2026-06-19 operator decision; rigor unchanged).

## Experiment E1 — the one genuinely-untested cell of the operator's thesis
**Surface:** DCB / ETHUSDT / 1h (DCB's only validated edge; live ROBUST).
**Window:** EXPLICIT full history `2017-08-17 → 2026-06-14` (avoid tick.py:302 2024 default).
**Grid (4 cells, pre-justified — minimizes trial-tax damage):**
- `stopAtrMult` ∈ {3.0 (live baseline), 5.0 (WIDE anti-stop-hunt, beyond retail/liquidation clusters — never tested on DCB; prior max was 3.0)}
- `trailAtrMult` ∈ {0.0 (fixed-TP baseline), 3.5 (ride-the-wave, Chandelier literature-optimal 2.5–3.5)}
- Held fixed at live params: `tpR=5.0, adxEntryMin=21, rvolMin=1.3, breakEvenR=1.0, maxBarsHeld=120, trailActivateR=0.0` (pure-trail when trail on).
**Pre-justification (not fished):** wide stop = the operator's literal anti-hunt thesis; trail 3.5 =
LeBeau Chandelier optimum. Two baseline cells (stop 3.0 / trail 0.0) reproduce the live config for a
clean paired comparison.
**Success criteria (V11/V60):** n≥100, PF 95% CI lower>1.0, DSR≥0.90, ag90≥10%, then walk-forward ROBUST.
**Branches:**
- SIGNIFICANT_EDGE + ag90≥10% → graduation review → Path-C specialist checkpoint → walk-forward.
- INSUFFICIENT_EVIDENCE (expected if oracle ceiling 0.34 holds) → this DEFINITIVELY answers the
  operator's exit-dimension thesis on DCB: even the widest anti-hunt stop + ride-the-wave trail
  cannot clear the trial-tax-deflated gate. Journal STRATEGY_OUTCOME; the DCB archetype is exhausted
  for the operator's thesis; the binding constraint is data breadth / a NON-DCB engine with a real
  bias_interval (operator-deploy) — surface as data/engine wishlist.

## Execution order
1. Plan review (this plan) → APPROVED → queue E1.
2. /tick/drain (explicit full window, iter_budget 6, require_walk_forward false at sweep stage).
3. Branch on terminal_action per above.

## Decision criteria for next session
- If E1 graduates: walk-forward → GOAL_HIT or STRATEGY_OUTCOME.
- If E1 INSUFFICIENT (likely): the operator's trailing/stop/MTF thesis is comprehensively answered on
  the reachable DCB substrate — recommend the operator either (a) authorize a new engine with a real
  multi-timeframe bias_interval gate (the only un-tested mechanism, requires deploy), or (b) redirect
  to the breadth/orthogonal-data constraint (the 4-way-confirmed binding limit).
