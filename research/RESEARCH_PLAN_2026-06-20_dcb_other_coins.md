# Research Plan — 2026-06-20 (operator-directed: DCB other-coins / 4h-trail on fresh cells)

**Run marker:** OPERATOR_DIRECTED_DCB_OTHER_COINS (resumed after 2026-06-20 ~12:05 local PC restart; cumulative 8.5h clock under the existing marker, started_ts 2026-06-20 04:55Z).
**Hypothesis:** `baf604cb-7c6e-493a-bc62-93e6f688da3c` (DCB / BNBUSDT / 4h, kind=ALGO, exit_profile=pure_atr_trail).
**Lockout:** prior run fired ARCHETYPE_EXHAUSTION_2026-06-20 (19:36Z, DCB-ETH-1h exit/stop saturated). The fresh hypothesis above (created 05:24Z, after the terminal) legitimately clears the bypass clause — `bypass_available=true` confirmed. This is a genuinely NEW direction (fresh-coin breadth), not a re-grind of the saturated DCB-ETH-1h exit dimension.

## Premise (5 lines)
Operator mandate: extend the DCB-4h-trail archetype to fresh unmined coin cells (SOL/BNB/XRP/DOGE/AVAX
+ short-history FET/LINK/NEAR/XLM/ZEC). Offline-4h-screen-first; formal pipeline only on screen-passers.
Goal unchanged: ag90 >= 10%/yr + walk-forward ROBUST. The lever that distinguishes this from prior work
is the PURE-ATR-TRAIL exit (the one that lifted DCB-BTC-4h to PF 2.40 / ag90 19.3% before DSR-tax killed it).

## Graveyard check (which mandate cells are runnable / already mined)
- **Runnable DCB cells** (have account_strategy rows): only BNBUSDT-4h and XRPUSDT-4h of the mandate coins.
  SOL/DOGE/AVAX/FET/LINK/NEAR/XLM/ZEC have NO DCB row -> /queue 412 account_strategy_missing -> DATA_WISHLIST
  (operator seed needed), NOT a dead archetype, NOT counted toward exhaustion.
- **DCB-XRP-4h: DEAD** (null-screen 2026-06-18, frequency-starved n=2..59, structurally < n>=100). A trail exit
  changes hold-time, NOT entry frequency -> cannot rescue. SKIP (would be a "blind DSR burn").
- **DCB-BNB-1h: DEAD** (NO_EDGE_DETECTED null-screen 2026-06-17).
- **DCB-BNB-4h: REAL edge, bounded.** WF 2026-06-14 (wf 53622848) with FIXED-TP let-trends-run exit:
  INSUFFICIENT_EVIDENCE — DSR 0.074, 45 trades, 100% folds positive, oos_sharpe 0.90, 4.4yr history.
  The PURE-ATR-TRAIL exit has NEVER been screened on this cell. **This is the one genuinely un-run,
  runnable dimension the mandate names.**

## Constraints reaffirmed
- Universe: BNBUSDT (this plan). Intervals: 4h. Research-mode only (enabled=false, simulated=true). Prod untouched.
- 10%/yr ag90 + ROBUST WF bar. V11/V60 gates frozen. No promote/deploy.

## Experiment (conditional on screen verdict)
**Step A (offline-4h-screen-first GATE):** null-screen DCB-BNBUSDT-4h, K=8, trail-inclusive param space
(tpR 3.5-8.0, stopAtrMult 2.5-4.5, maxBarsHeld 18-48, breakEvenR 0.5-1.5, rvolMin 1.1-1.5, adxEntryMin 18-25).
High tpR makes the fixed-TP rarely bind -> the ATR trail effectively manages the exit.

**Branch on screen verdict:**
- **NO_EDGE_DETECTED** -> pivot, do NOT sweep. Journal STRATEGY_OUTCOME. The DCB-4h-trail archetype has
  no viable fresh-coin runnable cell (BNB-4h dead across exit profiles, XRP-4h frequency-dead, others unseed).
  Likely the 2nd no-credible-next-archetype diagnosis in 7d -> ARCHETYPE_EXHAUSTION terminal with a
  DATA_WISHLIST (seed DCB account_strategy rows on SOL/DOGE/AVAX so the mandate's other coins become runnable).
- **EDGE_PRESENT / INCONCLUSIVE (with finite draws n>=40)** -> proceed to formal pipeline:
  Step B. Plan-review -> /queue a FOCUSED 3-dimension sweep (tpR x stopAtrMult x maxBarsHeld, trail-centric)
  with iter_budget ~12. Step C. /tick/drain. On SIGNIFICANT_EDGE -> graduation review -> Path C specialists.
  On PIVOT (>=5 iters) -> regime-analysis -> STRATEGY_OUTCOME.
- **INSUFFICIENT_DATA** -> DATA_WISHLIST (BNB-4h history gap), does NOT count toward exhaustion.

## Realistic expectation (test intelligently, do NOT blindly burn DSR)
BNB-4h's binding constraint is 4.4yr history + ~45 trades -> a low DSR-trial ceiling that NO exit profile
fully fixes. The screen is the cheap honest test of whether the trail lever materially changes the PF
distribution. If the screen passes AND a sweep produces SIGNIFICANT_EDGE, the WF is the real arbiter; if
DSR still caps it, that is an honest INSUFFICIENT_EVIDENCE, not a failure of the loop.

## Decision criteria for next session
- If screen ran and PASSED but session ended mid-sweep: resume protocol queue-pending branch picks up /tick/drain.
- If screen NO_EDGE: hypothesis baf604cb marked outcome; next direction = operator-seed DATA_WISHLIST for SOL/DOGE/AVAX DCB rows.
