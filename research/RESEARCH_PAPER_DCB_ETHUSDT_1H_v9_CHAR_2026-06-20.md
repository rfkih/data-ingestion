# Research Paper: DCB — ETHUSDT × 1H

**Author:** quant-researcher
**Date:** 2026-06-20
**Strategy:** `DCB`
**Surface:** `ETHUSDT` × `1H`
**Type:** CHAR
**Surface attempt:** v9 — CHAR (operator-directed MTF/trailing/anti-stop-hunt thesis test; INFRA-blocked before any iteration completed)
**Prior papers on this surface:** `v1`–`v8` (HYBRID/ML, 2026-05-30 → 2026-06-13)
**Filename:** `RESEARCH_PAPER_DCB_ETHUSDT_1H_v9_CHAR_2026-06-20.md`
**Terminal:** INFRA_HARD_FAIL
**Goal status:** NOT HIT (no iteration produced — research JVM heap-starved)
**Hypothesis:** `ba62ffee-1732-4a69-b1c7-36b33c5acb08`
**Queue(s):** `48858835-042c-4970-8a43-749d0c92aa0e` (PARKED)

---

## TL;DR

Operator directed a fresh multi-timeframe / trailing / anti-stop-hunt research thesis (1d bias + faster
entry, ride-the-wave trailing stop, stops placed away from retail/liquidation clusters). I designed and
queued the single genuinely-untested cell of that thesis — a 4-cell `stopAtrMult{3.0,5.0} ×
trailAtrMult{0.0,3.5}` grid on the LIVE DCB-ETH-1h edge surface over the full 2017-08 history — but the
sweep produced **zero completed iterations**: the prod research JVM is heap-regressed to `-Xmx1400m` /
1.5 GB container (the 2026-06-18 bump to 3 GB was lost on container recreation), so the first
full-history backtest GC-thrash-stalled and the `/tick/drain` timed out after 25 min at 0%. The JVM is
now unresponsive to health probes. **This is an infrastructure blocker, not a research signal**
(`infra_failure_caused=true`; does not count toward archetype exhaustion). The substantive finding,
drawn from durable prior evidence rather than new iterations, is that **the operator's exact thesis is
already comprehensively answered on the reachable DCB substrate** — see §5.

*(No SIGNIFICANT_EDGE table — no cell executed.)*

---

## 1. Background

Session opened with no lockout (`lockout_state=null`), empty queue, no Path-C pending, no ML in flight.
The operator issued a fresh OPERATOR-DIRECTED mandate (bypassing the prior ARCHETYPE_EXHAUSTION terminal):
test a multi-timeframe trend strategy using a 1d bias for direction, a faster interval (1h/15m) for entry
timing, a trailing stop tuned to ride the wave, and stops placed away from where retail clusters
(anti-stop-hunt), on ETHUSDT + BTCUSDT. The operator explicitly warned: *test intelligently, do not blindly
burn DSR*, and listed prior findings not to re-burn (standalone intraday trend FALSIFIED; DCB-BTC-1h loses
every config; DCB-ETH-1h fixed-TP already beat trailing at 1h-standalone; `/signal-screen` unusable
intraday).

DCB-ETH-1h is DCB's only live + walk-forward-ROBUST edge (tpR-5.0, 564 trades). It was the natural
substrate to harden under the operator's thesis.

---

## 2. Hypothesis

**Mechanism:** DCB (Donchian-channel breakout) enters on a channel breakout gated by ADX + relative
volume, manages with an ATR stop, and exits on fixed-TP (tpR) or — in this test — an ATR trailing stop.
The operator's thesis maps onto DCB's reachable knobs: `stopAtrMult` = stop placement (anti-stop-hunt =
WIDE stop, beyond retail/liquidation clusters), `trailAtrMult` = ride-the-wave trailing exit. The 1d-bias
leg has NO engine knob (see §4), so it was approximated by DCB's existing per-bar trend-regime context.

**Pre-registration:** Hypothesis `ba62ffee-1732-4a69-b1c7-36b33c5acb08` registered 2026-06-20T00:53Z,
before any sweep iteration (none executed). Falsification criterion: if the wide anti-hunt stop (5.0) +
ride-the-wave trail (3.5) raises avg_win/expectancy AND DSR vs the live fixed-TP baseline, the thesis is
supported; if metrics move little and DSR stays < 0.90, the exit dimension is saturated.

**Type:** CHAR (the executed artifact characterizes the thesis against prior evidence + records the infra
blocker; the ALGO sweep that was queued produced no data).

---

## 3. Methodology

### 3.1 Statistical Gates (V11 + V60)
n_trades ≥ 100, PF 95% CI lower > 1.0, DSR ≥ 0.90 (operator decision 2026-06-15), ag90 ≥ 10%/yr,
walk-forward ROBUST. (V60 absolute-return floor set to 0.0 platform-wide 2026-06-19; DSR/PSR/WF rigor
unchanged.) None evaluated — no cell completed.

### 3.2 Sweep Design
- **Type:** GRID
- **Backtest window:** `2017-08-17T00:00:00` → ~now (explicit, to defeat the tick.py:302 2024 default)
- **Dimensions swept:** `stopAtrMult ∈ {3.0, 5.0}`, `trailAtrMult ∈ {0.0, 3.5}`; fixed at live params
  `tpR=5.0, adxEntryMin=21, rvolMin=1.3, breakEvenR=1.0, maxBarsHeld=120, trailActivateR=0.0`.
- **Total cells:** 4 planned, **0 executed** (research JVM heap-starved; first cell never produced a
  backtest_run_id).

### 3.3 Pre-justification (anti-fishing)
Wide stop (5.0) = the operator's literal anti-stop-hunt thesis (never tested on DCB; prior max
`stopAtrMult` was 3.0). Trail 3.5 = LeBeau Chandelier literature optimum (2.5–3.5). Two baseline cells
(stop 3.0 / trail 0.0) reproduce the live config for a clean paired comparison. Grid kept to 4 cells to
bound trial-tax damage on the already-mined (DCB, ETHUSDT) bucket (185 cumulative trials).

---

## 4. The multi-timeframe reachability finding

**No engine in the platform exposes a higher-timeframe `bias_interval` knob.** Verified by reading the
`Tuning` records of `DonchianBreakoutEngine` (knobs: rvolMin, adxEntryMin, stopAtrMult, tpR, breakEvenR,
maxEntryRiskPct, maxBarsHeld, intervalMinutes, trailAtrMult, trailActivateR) and `AtrMomentumEngine`
(signedEr20 + ADX are same-interval trend-quality filters, not a higher-TF bias). DCB records
`entry_trend_regime` (BULL/BEAR/NEUTRAL) for analytics but does NOT gate entries on it. Therefore the
operator's literal "1d bias + faster-interval entry" mechanism **cannot be built without a new/modified
engine**, which is operator-only (hard rule 8 — new spec deploys restart the trading JVM). The closest
reachable analog — the regime-ML-gate (`regime_eth_v2`) — was already the best DCB-ETH lever in prior work
(iteration 339: DSR 0.55, still < 0.90).

---

## 5. The substantive finding (durable prior evidence)

The operator's thesis dimensions were the subject of the last ~6 days of research and are already
answered on the DCB substrate:

| Test | Result | Grounding |
|---|---|---|
| DCB-BTC-4h pure-ATR-trail (trail 3.0) | real edge PF 2.40, ag90 19.3%, **DSR 0.14** — trial-tax DEAD | iter 373 (BTCUSDT, trials 193); STRATEGY_OUTCOME 2026-06-19 |
| DCB-ETH-1h regime-gated ("1d-bias" analog) | best lever, **DSR 0.55** < 0.90 | iter 339 (trails 158) |
| DCB-ETH-1h exit dimension ceiling | **oracle-exit DSR ~0.34** — even perfect-foresight exit sub-gate | graduation-gate-solve 2026-06-15 |
| DCB-ETH-4h | FALSIFIED — frequency-starved, all 12 cells n<100 | STRATEGY_OUTCOME 2026-06-14 |
| DCB-XRP-1h conventional grid | loses money — PF<1.03, ag90 −7%…−78% | iters 297–306 |
| DCB-BNB-1h | NO_EDGE_DETECTED (null-screen) | 2026-06-17 |
| DCB-4h multi-symbol robustness | NONE of BTC/ETH/BNB clears walk-forward | STRATEGY_OUTCOME 2026-06-14 |

**Trial-tax map (DCB cumulative `dsr_n_trials`):** ETHUSDT 128–185, BTCUSDT 193, BNBUSDT 29–33,
XRPUSDT ~6–15. Every new ETH/BTC cell raises the DSR bar — re-grinding is the "blind DSR burn" the
operator forbade.

**Interpretation:** the exit-dimension oracle ceiling (0.34) is the load-bearing fact — it measures the
theoretical best ANY trailing/stop/exit tuning can achieve on DCB-ETH-1h, and it is far below the 0.90
gate. The operator's "ride the wave" payoff, even perfectly executed, cannot graduate DCB-ETH-1h. The
binding constraint (4-way confirmed in prior sessions) is data breadth / orthogonal data, not param
search or exit tuning.

---

## 6. What blocked this session (infra)

`/tick/drain` ran 25 min and returned curl(28) timeout with 0 bytes. The queue stayed at iter#=1,
last_run_id=None the entire time. Research JVM (`blackheart-research`) memory pinned 99.97–99.98%, CPU
4–24% (GC-thrash). A prior backtest worker (runId 8accaa02) was marked FAILED after STALE 1025s at 0%
("worker died before ack"). JVM config: `-Xms512m -Xmx1400m`, container mem_limit 1,572,864,000 bytes
(1.5 GB). Memory documents the needed config as ≥3 GB / `-Xmx2560m` for pre-2024 full-history sweeps
(2026-06-18) — that bump was NOT present on the running container (VPS compose is hand-managed/diverged).
JVM is now unresponsive to `/actuator/health` (10s timeout across 3 retry probes). Queue 48858835 was
PARKED with the infra reason so it does not block the next session.

---

## 7. Recommendations to operator

1. **Restore research JVM heap** to ≥3 GB / `-Xmx2560m` AND persist it in the VPS compose (currently
   diverged from git). The JVM likely needs a restart (memory pinned, unresponsive).
2. **Then** either re-queue the parked sweep (48858835) for a real result, OR — more decisively — accept
   the §5 evidence that the operator's exit/stop thesis cannot graduate DCB, and choose between:
   (a) authorizing a **new multi-timeframe engine with a real `bias_interval` gate** (the only un-tested
   mechanism for the thesis), or (b) redirecting research to the 4-way-confirmed binding constraint
   (data breadth / orthogonal non-price data).
3. The liquidation (forceOrder) stream the operator cited for the anti-stop-hunt map is accruing since
   2026-06-12 and is data-gated until ~late-Aug-2026 for the LIQ_FADE lead; not reachable for this thesis
   yet.
