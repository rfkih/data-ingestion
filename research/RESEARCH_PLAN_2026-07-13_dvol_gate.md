# RESEARCH PLAN 2026-07-13 (afternoon session) — DVOL implied-vol regime gate ($0 run)

Hypothesis: `594c722b-96aa-4090-8436-49ef48117c4a` (operator-directed; substitutes data-blocked
skew stress-gate `470ca035`). Marker: fresh 8.5h run started 2026-07-13 ~07:06 UTC.

## Premise (5 lines)
1. Morning run ended ARCHETYPE_EXHAUSTION (TPB_POOL cert falsified at max power; zero warm leads);
   operator provided a fresh $0 direction → lockout bypassed per protocol.
2. DCB/TPB directional edges are REAL but sub-gate (DSR 0.2–0.36 at n 180–488); residue shows the
   drag concentrates in quiet chop (ETH-4h NEUTRAL PF 0.95 vs BULL 1.50 / BEAR 1.88).
3. Deribit DVOL (30d implied-vol index) has full free history 2021-03→now, already ingested hourly
   (`feature_values`: btc_/eth_dvol_level, *_zscore_30d). Real-time index → PIT-clean IF lagged.
4. PIT trap found + fixed: Deribit candles are OPEN-stamped (verified empirically on VPS) → the
   close at ts is knowable only at ts+1h → all joins use `feature ts <= entry_time − 1h`.
5. Graveyard clean: DVOL_VOV (5abc7e7f) was 2nd-moment standalone directional (different); XS_IVRV
   was cross-sectional. A DVOL level/z CONDITIONING GATE has never been tested here.

## Constraints reaffirmed
Universe BTC/ETH/SOL/BNB/XRP (+operator-seeded ADA/AVAX/DOGE evidence read-only); intervals
5m/15m/1h/4h/1d; live book untouched; V11+V60 gates fixed; 10%/yr bar; $0 budget — no Tardis,
no certifying on 1-month skew; no re-mine of MRO/ATR_MOM/DCB-plain families or DCB_POOL.

## Experiment: Stage-0 offline A/B (read-only, no queue)
Join existing `backtest_trade` entries of pinned substrates to the PIT-lagged DVOL state at entry;
split per-trade returns into gate-ON vs gate-OFF; compare.

- **Substrates** (rule = max-n PF>1.0 cell per surface, pinned pre-analysis):
  - S1 DCB-SOLUSDT-4h — iter a216e2b0, run f1491927, n=220, PF 1.373, DSR 0.230 (gate: btc_dvol)
  - S2 DCB-ETHUSDT-1h — iter 1c9fdc7a, run 22d9ebdc, n=488, PF 1.405, DSR 0.331 (gate: eth_dvol)
  - S3 TPB_POOL 2021+ book — sleeves 590f3a2c/3dc2786d/8e0b06bf/8875fe76, n=92 (gate: btc_dvol;
    measurement-only, n<100)
- **Gates** (fixed pre-analysis; availability lag 1h; trailing-only transforms):
  - G3 PRIMARY: dvol_level ≥ trailing-365d rolling median (min 90d warmup)
  - G1: dvol_zscore_30d ≥ +0.5 · G2 sign-control: z ≤ −0.5 · G4: level > trailing-365d P25
- **Success**: per substrate PF(ON) > PF(OFF) AND one-sided MWU p<0.05 (per-trade return pct).
  Family REAL iff ≥2/3 substrates pass in the predicted direction, no sign-flip on the third.
- **Falsifier**: 0–1 pass, sign-flip, or only G2 passes → FALSIFIED at Stage-0, honest terminal.
- Declared trials: 12. Entries < 2021-04-03 excluded (z warmup) from both arms.

## Branches
- REAL + (S1 or S2 gate-ON n ≥ 100): design confirmatory path. Engine has no DVOL gate param →
  confirmatory in-engine sweep requires an operator-owed JVM patch (as 470ca035 planned). Journal
  the measured gated-book stats (honest DSR w/ cumulative trial tax) as the evidence package;
  the gate itself cannot be certified this run without the engine patch → operator-owed handoff.
- DEAD: STRATEGY_OUTCOME, mark 594c722b FALSIFIED, classify warmth, honest ARCHETYPE_EXHAUSTION
  terminal (no other $0 angle: skew time-gated, price/volume families exhausted per morning run).
- WARM (direction right, power short): journal lead with next_axis, then terminal per scheduler.

## Execution order
1. PIT checkpoint journal (done in-session) → 2. extraction+join script → 3. per-substrate A/B →
4. checkpoint journal with full table → 5. verdict branch → 6. paper (DB gen only if a queue ran;
filesystem paper per template regardless) → 7. terminal + RUN_SUMMARY with warm_leads.

## Decision criteria for next session
Gate REAL → operator decides engine patch; gate DEAD → unlock is TIME (free skew accrual ~months)
or MONEY (Tardis) — both operator-only.
