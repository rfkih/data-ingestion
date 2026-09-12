# Research Paper: DCB — ETHUSDT × 1H

**Author:** quant-researcher
**Date:** 2026-06-20
**Strategy:** `DCB`
**Surface:** `ETHUSDT` × `1H`
**Type:** ALGO
**Surface attempt:** v10 — ALGO (operator-directed anti-stop-hunt + ride-the-wave exit grid, RUN to completion after the v9 INFRA block was cleared by restoring the research JVM heap to 3 GB / -Xmx2560m)
**Prior papers on this surface:** `v1`–`v8` (HYBRID/ML, 2026-05-30 → 2026-06-13); `v9_CHAR_2026-06-20` (INFRA_HARD_FAIL — JVM heap-starved before any iteration produced)
**Filename:** `RESEARCH_PAPER_DCB_ETHUSDT_1H_v10_ALGO_2026-06-20.md`
**Terminal:** STRATEGY_OUTCOME (exit/stop dimension exhausted — no graduation candidate; STOP for operator direction)
**Goal status:** NOT HIT (all 4 cells INSUFFICIENT_EVIDENCE; best DSR 0.188 << 0.90 gate)
**Hypothesis:** `ba62ffee-1732-4a69-b1c7-36b33c5acb08`
**Queue(s):** `6c7e85b3-7faf-4c3c-8a84-22f37137d380` (PARKED, grid exhausted); supersedes parked `48858835-...` (v9 INFRA cancel)

---

## TL;DR

The operator's specific anti-stop-hunt thesis was tested empirically and to completion: a wide stop placed beyond retail/liquidation clusters (`stopAtrMult` 5.0) and a ride-the-wave ATR trail (`trailAtrMult` 3.5), versus the live fixed-TP baseline, on DCB-ETHUSDT-1h over the genuine full 2017-08-17 → 2026-06 history (~3,227 days, ~19k bars). All four grid cells returned **INSUFFICIENT_EVIDENCE**. The edge is unmistakably real — every cell is profitable (PF 1.26–1.63, ag90 10.8–37.5%/yr) and three of four pass both the PF-CI and the 10%/yr economic gate — but the **trial-tax-deflated DSR tops out at 0.188**, 4.7× below the 0.90 gate. This is fully consistent with the previously-measured ~0.34 oracle-exit (perfect-foresight) ceiling that structurally bounds *any* stop/trail rule on the current 1h DonchianBreakout entries below the gate. The operator's combined intuition has genuine economic merit (the 5.0+3.5 combo is the best cell: PF 1.63, the lowest drawdown of the grid at −0.41), but no exit/stop tweak can graduate this surface. **The exit dimension is exhausted.** The one untested mechanism — a true multi-timeframe engine with a real `bias_interval` gate — is surfaced as a HYPOTHESIS for operator direction (operator-only deploy; not built this session).

| Cell (stop × trail) | n_trades | PF | PF 95% CI lower | ag90 (%/yr) | DSR | Verdict |
|---|---|---|---|---|---|---|
| 3.0 × 0.0 (live baseline) | 626 | 1.40 | 1.10 ✅ | 37.5 ✅ | **0.189** ❌ | INSUFFICIENT |
| 3.0 × 3.5 (trail only) | 839 | 1.26 | 1.03 ✅ | 25.6 ✅ | **0.085** ❌ | INSUFFICIENT |
| 5.0 × 0.0 (wide anti-hunt) | 202 | 1.35 | 0.89 ❌ | 10.8 ✅ | **0.013** ❌ | INSUFFICIENT |
| 5.0 × 3.5 (combo — best) | 304 | 1.63 | 1.17 ✅ | 20.2 ✅ | **0.188** ❌ | INSUFFICIENT |

Gates: n ≥ 100, PF CI lower > 1.0, DSR ≥ 0.90, ag90 ≥ 10%/yr, then walk-forward ROBUST. No cell cleared DSR; no walk-forward run.

---

## 1. Background

DCB-ETHUSDT-1h is the platform's only live-ROBUST DonchianBreakout surface (live config: fixed-TP, stop ≈ 3.0 ATR). Across v1–v8 the entry/regime/ML dimensions were exhausted: the ML regime gate (`regime_eth_v2`, a 1d-bias analog) reached the highest DSR any DCB-ETH lever has achieved at **0.55**, still short of the gate; the funding/OFI HYBRID families were all falsified on covariate-shift / adversarial-AUC grounds. The durable conclusion entering this session: DCB-ETH-1h has a **real but irreducibly thin** edge whose **oracle-exit ceiling is ~0.34 DSR** — even a perfect-foresight exit on the current entry set cannot clear 0.90, because the multiplicity (trial-tax) deflation on this over-mined surface (`dsr_n_trials` ≈ 186–189) is too large.

The operator directed a *specific* new test of the **exit/stop dimension**: place the stop beyond where retail and liquidation clusters sit (a "wide anti-stop-hunt" stop, never tested above 3.0 on DCB), combined with a pure ATR trail to ride trends. The prior session (v9) queued this sweep but the research JVM was heap-starved (1.5 GB container / -Xmx1400m, a regression after a container recreation lost the 2026-06-18 3 GB bump), so the full-history backtest GC-thrashed and the drain timed out at 0% → INFRA_HARD_FAIL. The operator restored the heap to 3 GB / -Xmx2560m and recreated the container (health 200 confirmed); this session resumed the same research run (marker `status=ACTIVE`) and ran the sweep to completion.

---

## 2. Hypothesis

**Mechanism:** DCB enters on a Donchian-channel breakout confirmed by ADX (`adxEntryMin` 21) and relative volume (`rvolMin` 1.3). Position management was the experimental surface: `stopAtrMult` sets the initial stop distance in ATR multiples; `trailAtrMult` activates a Chandelier-style ATR trailing stop (0.0 = off, i.e. fixed-TP at `tpR`=5.0R). The operator's thesis: a **wide** initial stop (5.0 ATR) sits beyond the retail/liquidation stop clusters that market-makers hunt, so it avoids being shaken out of valid trends; a **ride-the-wave** ATR trail (3.5, the LeBeau Chandelier literature optimum of 2.5–3.5) then captures the full extent of trends instead of capping at a fixed take-profit.

**Pre-registration:** Hypothesis `ba62ffee-1732-4a69-b1c7-36b33c5acb08` (DCB), ACTIVE, registered 2026-06-19 (prior session), before any iteration in this sweep (earliest iteration 2026-06-19 18:48 UTC). Falsification criterion stated in the hypothesis: the sweep either beats the live fixed-TP baseline and clears the gate, **or** confirms the exit dimension is saturated (oracle ceiling ~0.34) and no stop/trail tweak clears the 0.90 DSR gate.

**Type:** ALGO (parametric exit/stop sweep on the deployed DCB engine; no ML).

---

## 3. Methodology

### 3.1 Statistical Gates (V11 + V60)

| Gate | Threshold | Binding? |
|---|---|---|
| n_trades | ≥ 100 | YES |
| PF 95% bootstrap CI lower | > 1.0 | YES |
| DSR (Bailey–LdP, n_trials from hypothesis_audit) | ≥ 0.90 | YES (operator decision 2026-06-15; was 0.95) |
| Statistical verdict | SIGNIFICANT_EDGE | YES |
| ann. geometric return at alloc-90 (ag90) | ≥ 10%/yr | YES |

The retired +20bps slippage net gate was NOT enforced. The DSR gate is the binding constraint here.

### 3.2 Sweep Design

- **Type:** GRID
- **Backtest window:** `2017-08-17T00:00:00` → ~2026-06 (~3,227 days ≈ 8.8 years, ~35 quarters; full ETH history). Window set **explicitly** to avoid the `tick.py:302` 2024-01-01 default.
- **Dimensions swept (2 axes, 4 cells):**
  - `stopAtrMult` ∈ {3.0 (live baseline), 5.0 (wide anti-stop-hunt)}
  - `trailAtrMult` ∈ {0.0 (fixed-TP baseline), 3.5 (ride-the-wave)}
- **Held fixed at live values:** `tpR`=5.0, `adxEntryMin`=21, `rvolMin`=1.3, `breakEvenR`=1.0, `maxBarsHeld`=120, `trailActivateR`=0.0 (pure trail when trail is on).
- **Total cells:** 4 planned, **4 executed** (no gaps). `dsr_n_trials` on the surface = 186–189 cumulative (the DCB-ETH trial-tax).

### 3.3 Walk-Forward Protocol

Not run — no cell reached SIGNIFICANT_EDGE, so there was no graduation candidate to validate.

---

## 4. Results

### 4.1 Per-cell detail

**Cell 1 — live baseline (stop 3.0, trail 0.0), iter `07ff1d5c`:** n=626, PF 1.40, PF CI [1.099, 1.727], ag90 **37.5%**, Sharpe(ann) 0.89, maxDD −0.94, **DSR 0.189**. Verdict: "PF CI favorable but DSR < 0.9 — selection-bias deflation rejects after multiplicity correction." This reproduces the live config and is the strongest *raw* return cell (37.5%/yr), yet DSR is 0.189.

**Cell 2 — trail only (stop 3.0, trail 3.5), iter `09cc0117`:** n=839, PF 1.26, PF CI [1.029, 1.518], ag90 25.6%, Sharpe(ann) 0.74, maxDD −0.88, **DSR 0.085**. Adding the trail at the baseline stop *increases* turnover (626→839 trades) but *lowers* PF and risk-adjusted quality — DSR drops to 0.085. The trail alone is a net negative for the statistical case.

**Cell 3 — wide anti-stop-hunt (stop 5.0, trail 0.0), iter `967d8e98`:** n=202, PF 1.35, PF CI **[0.887, 1.920] (spans 1.0)**, ag90 10.8%, Sharpe(ann) 0.48, maxDD −1.08, **DSR 0.013**. The wide stop is the operator's headline lever. It cuts trade count sharply (626→202: fewer trades stopped out, longer holds) — but with far fewer, higher-variance trades the **PF-CI now spans 1.0** (fails the PF-CI gate outright) and DSR collapses to near-zero (0.013). The wide stop alone makes the statistical case *weaker*, not stronger.

**Cell 4 — combo (stop 5.0, trail 3.5), iter `7a3d9231`:** n=304, PF **1.63** (best of grid), PF CI [1.165, 2.174] (lower > 1.0, passes PF-CI), ag90 20.2%, Sharpe(ann) 0.92 (best), maxDD **−0.41** (lowest of grid), **DSR 0.188**. The full operator combo is the best *economic* cell: highest PF, lowest drawdown, best Sharpe. The wide stop avoids whipsaw shake-outs and the trail captures trend extent — exactly the operator's intuition, and it has genuine merit on the trade structure. But the trial-tax-deflated DSR is 0.188, still 4.7× below the gate.

### 4.2 Cross-cell synthesis

The best DSR across the entire operator-specified grid is **0.188** (cell 4). The grid spans the full economic spectrum the operator asked about — baseline, trail-only, wide-stop-only, and the full combo — and every cell lands far below 0.90. This is exactly what the pre-registered falsification criterion predicted: it is consistent with the ~0.34 oracle-exit ceiling. A perfect-foresight exit on these entries cannot clear the gate, so no *achievable* stop/trail rule can either. The exit/stop dimension is exhausted on DCB-ETH-1h.

---

## 5. Interpretation & Failure Mode

The failure mode is **not** "no edge." DCB-ETH-1h has a real, persistent, profitable edge (PF 1.26–1.63 across 8.8 years of out-of-sample-spanning history, three cells clearing 10%/yr). The failure mode is **multiplicity deflation against an irreducibly thin edge**: the surface has been mined ~186–189 times, and the Bailey–López-de-Prado deflated Sharpe correctly penalizes that selection. The edge's raw Sharpe (~0.5–0.9 annualized) is simply not large enough to survive a 189-trial haircut.

Crucially, every cell varies only the **exit/stop/sizing** dimension on a **fixed 1h DonchianBreakout entry set**. The ~0.34 oracle-exit ceiling is computed on *those entries*. It therefore does **not** bound an approach that changes the entries — which is why the next recommendation is an entry-side mechanism, not another exit tweak.

The operator's specific concern — that the live fixed-TP stop is being hunted and a wider anti-hunt stop would help — is answered directly: the wide stop (cell 3) does cut stop-outs, but it does not produce a graduate-able edge; the combo (cell 4) improves PF and drawdown materially but still cannot clear the deflation. **No exit/stop configuration graduates this surface.**

---

## 6. Recommended Next Mechanism (operator-deploy decision — NOT built this session)

The single untested lever is a **true multi-timeframe engine with a real `bias_interval` gate**: take the 1-day trend/regime (e.g. above/below an EMA band, 1d ADX, or a regime label) as a directional/risk filter, and only fire 1h (or 15m) breakout/pullback entries that align with it. This **changes the entry set**, so it escapes the ~0.34 oracle-exit ceiling that bounds every 1h-only exit tweak — a structurally different, plausibly higher, DSR surface.

Verified constraints (why this is operator-only and not a sweep):
- **No existing engine exposes a `bias_interval` knob.** DonchianBreakoutEngine and AtrMomentumEngine Tuning records carry no such field. It cannot be swept — it must be **built and deployed** (operator-only, hard rule 8).
- The closest available **proxy** — the ML regime gate (`regime_eth_v2` as a 1d-bias analog) — topped out at **DSR 0.55** (iter 339), still below 0.90 but the **highest DSR any DCB-ETH lever has reached**. That is positive directional evidence: a slower-timeframe bias is the right axis.
- **Do not re-test the falsified neighbours:** standalone intraday trend FALSIFIED; DCB-BTC-1h loses every config; DCB-ETH-4h frequency-starved/FALSIFIED; DCB-XRP-1h loses; DCB-BNB-1h NO_EDGE; DCB-ETH-1h exit dimension now EXHAUSTED.

**Recommendation:** STOP for operator direction. Either (1) authorize building a parametric MTF engine with a real `bias_interval` gate (the only un-tested mechanism on this surface), or (2) redirect research to the 4-way-confirmed binding constraint = data breadth / orthogonal NON-PRICE data. Registered as HYPOTHESIS `baf9f2f8-3884-47cf-917c-a5bc77fbd5b1`.

---

## 7. Provenance

- **Hypothesis:** `ba62ffee-1732-4a69-b1c7-36b33c5acb08` (anti-stop-hunt thesis, pre-registered 2026-06-19).
- **Queue:** `6c7e85b3-7faf-4c3c-8a84-22f37137d380` (PARKED, grid exhausted 2026-06-19/20). Supersedes `48858835-042c-4970-8a43-749d0c92aa0e` (v9 INFRA cancel).
- **Iterations:** `07ff1d5c` (cell 1), `09cc0117` (cell 2), `967d8e98` (cell 3), `7a3d9231` (cell 4). Iteration numbers 374–377.
- **STRATEGY_OUTCOME:** `7c7d94b3-8c2b-482b-a08a-1fbf5e0830b4` (exit-dimension exhausted).
- **Next-mechanism HYPOTHESIS:** `baf9f2f8-3884-47cf-917c-a5bc77fbd5b1` (MTF `bias_interval`, operator-deploy decision).
- **Infra fix:** research JVM (blackheart-research, :8081) heap restored 1.5 GB/-Xmx1400m → 3 GB/-Xmx2560m, container recreated, health 200. Full-history backtests run again.
- **Plan:** `research/RESEARCH_PLAN_2026-06-20.md`.
