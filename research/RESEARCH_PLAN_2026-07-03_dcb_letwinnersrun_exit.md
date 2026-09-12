# RESEARCH PLAN 2026-07-03 — DCB "let winners run" EXIT study

**Hypothesis:** `a3940807-6864-4346-9421-edbaf030d35f` (ALGO)
**Operator question:** Can "letting winners run" beat the incumbent fixed-TP exit on DCB / ETHUSDT / 1h? At 4h? With numbers.

## Premise
The live DCB-ETH-1h position caps every winner at a fixed TP and never trails. Operator intent: "just let the winners win." This is EXIT-dimension research — hold the live BREAKOUT entry fixed, sweep ONLY the exit family.

**True live baseline (verified in prod DB `strategy_definition` Preset 1, account_strategy `7edb997c`):**
`{tpR:2.0, rvolMin:1.3, breakEvenR:1.0, adxEntryMin:20, maxBarsHeld:24, stopAtrMult:3.0, intervalMinutes:240}`, `entryMode=BREAKOUT` (default), `trailAtrMult` ABSENT → **trail OFF**.
- Config quirk: `intervalMinutes:240` on a 1h row → the "24-bar" timed exit fires at `24×240=5760 min = 96h (4 days)`, not 24h. Reproduced in the sweep as `intervalMinutes=60, maxBarsHeld=96`.
- The current OPEN position's TP (1979.48 vs entry 1716.87, stop 1656.97 → tpR≈4.4) is a **stale artifact** from the mid-June WF-ROBUST tpR≈5 swap era; the current live spec is tpR=2.0.

**Engine mechanics (`DonchianBreakoutEngine.java`):**
- `trailAtrMult>0` → NULLS `takeProfitPrice1`, replaces fixed TP with a close-based ATR ratchet engaging at `trailActivateR` (0 = trail from entry; >0 = let it run first, then trail). Monotonic up-only.
- Fixed-TP mode (`trailAtrMult=0`) → fixed TP at `tpR` + one-shot break-even shift at `breakEvenR`.
- **Partial/scale-out RUNNER leg is NOT supported** (every entry emits `exitStructure=SINGLE`, `targetPositionRole=ALL`). Operator item #4 cannot be tested on this engine — reported, not faked.

**Mining-tax reality:** DSR `n_trials` is scoped per (symbol, interval) across ALL archetypes = **206 at ETH-1h, 156 at ETH-4h**. Certification (DSR≥0.90) is structurally near-impossible on both ETH surfaces regardless of exit config. PRIMARY deliverable = honest ECONOMIC comparison (PF / geo90-CAGR / avg-trade) + OOS regime/quarter stratification; certification reported pass/fail-by-axis.

## Constraints reaffirmed
- Universe BTC/ETH/SOL/BNB/XRP; ETHUSDT in scope. Intervals 1h/4h. RESEARCH-MODE ONLY — no promote, no deploy, no live-row edit.
- Gates fixed: V11 (n≥100, PF-CI-lo>1.0, DSR/PSR≥0.90), V102 live (CAGR≥10%/30tr/365d). Goal = geo90≥10% AND WF ROBUST. No loosening.
- Isolation: entry held FIXED (BREAKOUT, rvolMin=1.3, adxEntryMin=20); `maxEntryRiskPct=0.12` uniform so wide-stop (stop=5) cells aren't silently rejected by the 4% risk cap; `intervalMinutes=60`.

## Experiments (execution order)

### Exp 1 — DCB / ETHUSDT / 1h — FIXED-TP arm (trail OFF). 12 cells.
Axes: `tpR ∈ {2.0, 5.0, 10.0}` × `stopAtrMult ∈ {3.0, 5.0}` × `maxBarsHeld ∈ {96, 168}`. Fixed: `trailAtrMult=0, intervalMinutes=60, maxEntryRiskPct=0.12`.
Tests operator items #2 (widen/remove fixed TP; tpR=10 ≈ near-no-cap), #3 (wide stop), #5 (longer maxBarsHeld). Baseline anchor = (tpR=2, stop=3, mbh=96).

### Exp 2 — DCB / ETHUSDT / 1h — TRAIL arm (TP removed). 8 cells.
Axes: `trailAtrMult ∈ {2.0, 3.0}` × `trailActivateR ∈ {0, 1.0}` × `stopAtrMult ∈ {3.0, 5.0}`. Fixed: `maxBarsHeld=96, intervalMinutes=60, maxEntryRiskPct=0.12`.
Tests operator item #1 (ATR trail × activation) and #3 (wide stop + trail = memory's best-economics corner).

### Exp 3 — DCB / ETHUSDT / 4h — COMPARISON (fixed-TP + trail combined, compressed). ~8–10 cells.
Same exit surface at 4h (`intervalMinutes=240`, maxBarsHeld in bars). Answers "does letting winners run pay more where the underlying edge is stronger?" Honest thin-n caveat (ETH-4h ~30 trades historically → n<100 likely fails V11).

Window: 2022-01-01 → yesterday (avoids 2021-bull annualization inflation; multi-regime bear/chop/trend). `early_stop_on_no_edge=false` (need the full comparison table). `override_discard_gate=true` if the axis-set collides with a prior DISCARD — documented reason: fresh post-annualization-fix re-test on the live BREAKOUT entry at operator direction.

## Success criteria (V11)
A cell is a candidate only if n≥100, PF-CI-lo>1.0, DSR≥0.90, PSR≥0.90, geo90≥10, WF ROBUST. Given the mining tax, the realistic outcomes are: (a) trail/wide-TP improves economics but fails DSR → report which axis fails and by how much; or (b) fresh numbers confirm fixed-TP is the local optimum.

## Decision criteria for next step
- If any trail/wide-TP cell BOTH improves economics AND clears DSR → graduation review → walk-forward → GOAL check.
- Else → decisive verdict: economics comparison table (best-economics vs incumbent), regime/quarter OOS read, certification-fail axis, and a concrete operator recommendation (keep fixed-TP / test a specific trail config live as an experiment / pursue 4h/BTC-4h / dead-end).
