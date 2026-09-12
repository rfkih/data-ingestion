# Research Paper: DVOL_GATE — MULTIBOOK (DCB-SOLUSDT-4h, DCB-ETHUSDT-1h, TPB-2021+ 4h book)

**Author:** quant-researcher
**Date:** 2026-07-13
**Strategy:** `DVOL_GATE` (entry-conditioning overlay on `DCB` / `TPB`)
**Surface:** `SOLUSDT×4h` + `ETHUSDT×1h` + `SOL/XRP/ADA/AVAX×4h book` (gate variable: Deribit DVOL, BTC/ETH)
**Type:** CHAR
**Surface attempt:** v1 — CHAR (offline Stage-0 conditioning study; no sweep queued, no engine change)
**Prior papers on this surface:** none (first DVOL-conditioning attempt; siblings: `RESEARCH_PAPER_DCB_SOLUSDT_4H_v1_ALGO_2026-07-09.md`, `RESEARCH_PAPER_TPB_POOLEDBOOK_4H_v2_ALGO_2026-07-13.md`)
**Filename:** `RESEARCH_PAPER_DVOL_GATE_MULTIBOOK_4H_v1_CHAR_2026-07-13.md`
**Terminal:** ARCHETYPE_EXHAUSTION
**Goal status:** NOT HIT
**Hypothesis:** `594c722b-96aa-4090-8436-49ef48117c4a` (FALSIFIED)
**Queue(s):** none (Stage-0 falsified before any confirmatory queue)

---

## TL;DR

Operator-directed zero-cost test of a Deribit-DVOL implied-vol regime gate on the platform's three
strongest real-but-sub-threshold directional books (DCB-SOLUSDT-4h n=220, DCB-ETHUSDT-1h n=488,
TPB 2021+ 4-coin book n=92). The pre-registered mechanism — "high-IV regimes carry the breakout
edge; low-IV chop is the drag" — is **falsified in the strongest possible way: every pre-registered
gate variant runs in the OPPOSITE direction on effectively every substrate.** These books earn
their PF in LOW-implied-vol regimes. 0 of 12 pre-registered tests pass; the only nominally
significant cell is the sign-control (vol-compression, G2×S3: PF 4.09 vs 0.91, p=0.007, n=38),
which the pre-registration itself declared a falsification signature, and which sign-flips on S1.
No confirmatory sweep was queued; no engine patch is requested. The $0 options-data angle is closed;
the remaining unlocks for the conditioning-gate family are TIME (free per-strike skew accrual,
~months) or MONEY (Tardis backfill for `470ca035`) — both operator-only.

---

## 1. Background

Session start state: the same-morning run (`ARCHETYPE_EXHAUSTION_2026-07-13`, journal `091a8eac`)
had falsified TPB_POOL certification at maximum power and declared all price/volume directional
families (MRO, ATR_MOM, DCB-plain, TPB) exhausted with zero warm leads. A 24h lockout was standing;
the operator provided an explicit fresh direction (this study), clearing the lockout per the
fresh-HYPOTHESIS bypass clause — the same pattern as the morning's operator breadth unlock.

The direction: the pre-registered options-surface stress gate (`470ca035`, RR25 skew-z + IV term
structure on the pooled DCB-4h book) is data-blocked — per-strike skew history requires a paid
Tardis backfill, and the free skew feed has only ~1 month accrued (663 hourly rows since
2026-06-15, untestable). Deribit **DVOL** (30d implied-vol index level) is the one options-surface
signal with full free history (2021-03 → now), already ingested hourly into `feature_values`
(`btc_/eth_dvol_level`, `*_dvol_zscore_30d`, 46,496/46,257 rows). The operator asked whether a
DVOL vol-regime gate — the affordable substitute for the skew stress gate — lifts the
real-but-DSR-blocked DCB/TPB edges.

Graveyard check (pre-registration): the only DVOL priors are `5abc7e7f` (DVOL_VOV — the SECOND
moment, vol-of-vol, used as a standalone 1d directional signal; falsified 2026-06-11) and
`185e9538` (XS_IVRV — cross-sectional IV-RV pair; falsified). A DVOL **level/z-score conditioning
gate** on directional entries had never been tested. Not a re-skin: the conditioning variable is
options-market data orthogonal to the exhausted OHLCV families.

## 2. Hypothesis

**Mechanism (as pre-registered):** DCB breakouts and TPB pullback-continuations are
long-vol-expansion trades. Their residue shows the edge dying in quiet chop (DCB-ETH-4h regime
split: BULL PF 1.50 / BEAR 1.88 / NEUTRAL 0.95). DVOL, the crypto VIX, encodes the vol regime in
real time. Gating entries to high-IV regimes (or away from dead-calm regimes) should excise the
chop drag, lifting PF and DSR while keeping n ≥ 100 on the two large substrates.

**Pre-registration:** hypothesis `594c722b-96aa-4090-8436-49ef48117c4a` registered 2026-07-13
~07:45 UTC, before ANY conditional analysis ran (the A/B script was written and executed strictly
after). Gates, substrates, substrate-selection rule (max-n PF>1.0 cell per surface), success
criteria, falsifier, and 12 declared trials all fixed in the hypothesis row. Falsification
criterion: "0–1 substrates pass, or cross-substrate sign-flip, or only G2 (sign-control) passes →
family FALSIFIED at Stage-0, no re-mining."

**Type:** ALGO (offline conditioning study; no ML model, no training).

## 3. Methodology

### 3.1 Statistical Gates (V11 + V60)

Standard gates (n≥100, PF-CI-low>1.0, DSR≥0.90 per operator decision 2026-06-15, ag90≥10%/yr,
WF ROBUST) were the downstream target; Stage-0 used its own pre-registered screen (below) and
falsified before any V11 evaluation became relevant.

### 3.2 Study Design (offline A/B — no sweep)

- **Data:** 800 existing `backtest_trade` rows from 6 pinned `backtest_run`s; hourly DVOL series
  from `feature_values` (single source; the `feature_store` 1h/4h copies are stale at 2026-06-12).
- **PIT discipline:** Deribit DVOL candles verified **OPEN-stamped** (empirical test from the VPS
  ingest container: hourly candle T close 37.88 == 1-min candle close at T+59min, ≠ value at T
  37.92; in-progress current-hour candle present with running close). The stored close at ts is
  knowable only at ts+1h ⇒ all joins use availability lag 1h (`feature ts ≤ entry_time − 1h`).
  `dvol_zscore_30d` is a trailing pandas `rolling(720, min_periods=240)` — causal. Derived
  365d median/P25 computed trailing-only (window 8760h, min 2160h). Join staleness realized:
  0h at median AND p95 (hourly grid alignment). Trades entering before 2021-04-03 (z warmup)
  excluded from BOTH arms (6 trades: 3 pre-cutoff + 3 null-gate).
- **Gates (fixed pre-analysis):**
  - G3 PRIMARY (regime level): `dvol_level ≥ trailing-365d rolling median`
  - G1 (expansion): `dvol_zscore_30d ≥ +0.5`
  - G2 (sign-control, predicted harmful): `dvol_zscore_30d ≤ −0.5`
  - G4 (mild calm-skip): `dvol_level > trailing-365d P25`
- **Substrates (rule: max-n PF>1.0 cell per surface, pinned before analysis):**
  - S1 DCB-SOLUSDT-4h — iter `a216e2b0`, run `f1491927`, n=220, PF 1.373, DSR 0.230 (gate: BTC DVOL as market-wide IV; SOL has no DVOL index)
  - S2 DCB-ETHUSDT-1h — iter `1c9fdc7a`, run `22d9ebdc`, n=488, PF 1.405, DSR 0.331, window 2022-01→2026-07 (gate: ETH DVOL)
  - S3 TPB_POOL 2021+ book — sleeves `590f3a2c`/`3dc2786d`/`8e0b06bf`/`8875fe76` (SOL/XRP/ADA/AVAX 4h), n=92 (gate: BTC DVOL; measurement-only, n<100)
- **Success criterion (per substrate):** PF(gate-ON) > PF(gate-OFF) AND one-sided Mann-Whitney U
  (per-trade return %, ON>OFF) p<0.05. Family REAL iff ≥2/3 substrates pass in the predicted
  direction with no sign-flip on the third.

## 4. Parameter Space Explored

| Axis | Values Tested |
|---|---|
| gate variant | G3 (level≥med365), G1 (z≥+0.5), G2 (z≤−0.5, control), G4 (level>P25) |
| substrate | S1 DCB-SOL-4h, S2 DCB-ETH-1h, S3 TPB-2021+ book |

**Total tests:** 12 (declared pre-analysis; no additional cells were examined — no threshold
shopping occurred after the first look).

**Verdict distribution:** 0 pass / 12 fail (11 opposite-direction or n.s.; 1 sign-control pass = falsification evidence).

## 5. Results

### 5.1 Edge summary

Baselines (post-cutoff): S1 n=217 PF 1.317 · S2 n=488 PF 1.405 · S3 n=89 PF 2.021.

| Substrate | Gate | n_on | PF_on | n_off | PF_off | MWU p (ON>OFF) | Direction |
|---|---|---|---|---|---|---|---|
| S1 DCB-SOL-4h | G3 PRIMARY | 68 | 1.150 | 149 | **1.416** | 0.799 | OPPOSITE |
| S1 | G1 | 64 | 1.230 | 153 | **1.362** | 0.704 | OPPOSITE |
| S1 | G2 (control) | 96 | 1.226 | 121 | **1.390** | 0.667 | control also negative |
| S1 | G4 | 121 | 1.234 | 96 | **1.429** | 0.667 | OPPOSITE |
| S2 DCB-ETH-1h | G3 PRIMARY | 229 | 1.346 | 259 | **1.476** | 0.916 | OPPOSITE |
| S2 | G1 | 161 | 1.080 | 327 | **1.648** | 0.996 | STRONGLY OPPOSITE |
| S2 | G2 (control) | 204 | **1.519** | 284 | 1.344 | 0.100 | inverted, n.s. |
| S2 | G4 | 298 | **1.455** | 190 | 1.305 | 0.650 | predicted, n.s. |
| S3 TPB book | G3 PRIMARY | 20 | 0.730 | 69 | **2.600** | 0.977 | OPPOSITE |
| S3 | G1 | 18 | 1.710 | 71 | **2.091** | 0.535 | OPPOSITE |
| S3 | G2 (control) | 38 | **4.088** | 51 | 0.912 | **0.007** | inverted — falsifier arm |
| S3 | G4 | 43 | 1.491 | 46 | **2.643** | 0.909 | OPPOSITE |

Binding finding: **the books earn their PF in LOW-implied-vol regimes.** The primary gate degrades
PF on all three substrates; the expansion gate (G1) is the single worst variant (S2: gated PF 1.080
vs ungated-arm 1.648, p 0.996 against). The only nominally significant cell is the sign-control —
the pre-declared falsification signature — and it flips sign on S1 (compression HURTS SOL-4h).

### 5.2 Diagnostic (paper-grade context, not re-mining)

Year-bucket decomposition shows the low-IV-favorable inversion is NOT a single-regime artifact:
G3-OFF (low-vol) out-earns G3-ON in 2021 (PF 5.39 vs 0.14), 2023 (1.01 vs 0.29), 2024 (2.15 vs
0.33), 2026 (10.99 vs 0.60), roughly ties 2025 (3.63 vs 2.92), and flips only in 2022 (2.08 vs
2.64). BTC DVOL year medians fell 89→43 over the sample, but the trailing-365d median gate adapts,
so this is a genuine conditional pattern, not pure calendar drift. A hindsight mechanism exists
(vol-compression squeezes precede breakouts; high-IV marks post-move exhaustion) — but it is
post-hoc on this data and is NOT pursued, per the pre-registered no-re-mining clause and the
multiplicity already burned (the p=0.007 cell has an expected false-positive count of ~0.17
across the 24 signed tests and is n=38).

## 9. Infrastructure Notes

- **PIT trap found and neutralized:** Deribit DVOL candles are OPEN-stamped; the `feature_values`
  row at ts carries information from [ts, ts+1h). Any consumer joining `dvol_*` at-or-before a bar
  time WITHOUT a 1h lag has up to 1h of look-ahead. This applies to the `feature_store`
  `dvol_level`/`dvol_zscore_30d` columns too — **audit any future JVM feature join against this**
  (checkpoint journal `2b46375a`).
- Deribit API is geo-blocked from the local dev PC; empirical verification ran inside the VPS
  ingest container.
- `feature_store` 1h/4h DVOL columns are stale (last 2026-06-12); `feature_values` is fresh to now.

## 10. Methodology Compliance Audit

| Rule | Compliant? | Notes |
|---|---|---|
| Research universe (hard rule #1) | YES | evidence read-only incl. operator-seeded ADA/AVAX sleeves |
| Intervals (hard rule #2) | YES | 4h/1h substrates |
| Live book untouched (hard rule #3) | YES | read-only study |
| Research-mode only (hard rule #4) | YES | no deploy/promotion |
| 10%/yr bar (hard rule #5) | YES | falsified before economics stage |
| V11+V60 unmodified (hard rule #6) | YES | Stage-0 screen only; no gate moved |
| ≥3 dimensions (hard rule #7) | YES | gate-variant × threshold-form × substrate-breadth |
| Pre-registration before test (rule #10) | YES | hypothesis 594c722b + plan written before A/B ran |
| Append-only evidence (hard rule #10) | YES | status flip on hypothesis only (sanctioned) |
| Reviewer authoritative (hard rule #12) | N/A | no /queue, no graduation — review gates not reached |
| No trading-JVM calls (hard rule #13) | YES | DB reads via postgres; orchestrator HTTP only |

## 11. Conclusions

1. **The DVOL high-IV regime gate is falsified at Stage-0:** 0/12 pre-registered tests pass; the
   primary gate degrades PF on all three substrates (Δ PF −0.13 to −1.87).
2. **The true conditional structure is INVERTED:** DCB/TPB directional edges concentrate in
   low-implied-vol regimes, consistently across 5 of 6 years — high-IV entries are the drag.
3. **The inverted compression-gate cannot be claimed from this data:** it is post-hoc, n=38 at its
   only significant cell, sign-flips on S1, and the pre-registration bans re-mining.
4. **PIT dividend:** the open-stamped Deribit candle trap is now documented; any future JVM-side
   DVOL/skew feature consumer must apply a 1-bar (1h) availability lag.
5. **Implication for the loop:** the zero-cost options-surface angle is exhausted. The
   conditioning-gate family's remaining unlocks are the free skew accrual reaching testable depth
   (~months) or the Tardis backfill for `470ca035` (operator budget call) — plus one legitimate
   forward test: pre-register the compression gate on trades accrued strictly after 2026-07-13.

## 12. Data Wishlist

| Priority | Item | Blocker type |
|---|---|---|
| 1 | Tardis options_chain backfill 2022-01→2026-06 → unblocks skew stress-gate `470ca035` (Stage-0 design ready) | money (operator) |
| 2 | Free rr25_skew/term-spread accrual to ~12 months depth (testable ~2027-06; interim read ~2026-10) | time |
| 3 | True-OOS retest of inverted compression gate on post-2026-07-13 accrued trades (needs ~100 gated trades) | time |

## 13. Appendix — Audit Trail

| Item | ID |
|---|---|
| Hypothesis | `594c722b-96aa-4090-8436-49ef48117c4a` (FALSIFIED) |
| Queue(s) | none |
| Substrate iterations | `a216e2b0` (S1), `1c9fdc7a` (S2), `a7d7b2a3` (S3 pooled) |
| Substrate backtest_runs | `f1491927`, `22d9ebdc`, `590f3a2c`, `3dc2786d`, `8e0b06bf`, `8875fe76` |
| PIT checkpoint journal | `2b46375a-165a-4772-a660-223ff58a42b3` |
| STRATEGY_OUTCOME journal | `3dec89a6-6d3c-4f0a-80fb-7145827874ea` |
| RUN_SUMMARY journal | (terminal row, see ARCHETYPE_EXHAUSTION_2026-07-13 afternoon) |
| Plan | `research/RESEARCH_PLAN_2026-07-13_dvol_gate.md` |
| Analysis artifacts | `.rtmp/dvol_ab.py`, `.rtmp/dvol_ab_results.csv`, `.rtmp/dvol_diag.py` (scratch, gitignored) |
| Prior paper(s) | `RESEARCH_PAPER_TPB_POOLEDBOOK_4H_v2_ALGO_2026-07-13.md` (morning terminal context) |

---
*Paper generated by quant-researcher. DB registration: none (no queue reached terminal this session).*
