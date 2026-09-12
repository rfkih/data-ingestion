# Research Paper: MACRO_EVENT_WINDOW — POOLED5 (BTC/ETH/SOL/BNB/XRP) × 1h

**Author:** Claude (alpha-discovery + operator-directed pre-test)
**Date:** 2026-07-03
**Strategy:** `MACRO_EVENT_WINDOW` (FOMC/CPI calendar-window: pre-announcement drift + post-release continuation)
**Surface:** `POOLED5` (equal-weight BTC/ETH/SOL/BNB/XRP perp book) × `1h`
**Type:** ALGO
**Surface attempt:** v1 — ALGO (first attempt on any calendar-anchored surface; zero-trial offline pre-test terminal)
**Prior papers on this surface:** none
**Filename:** `RESEARCH_PAPER_MACRO_EVENT_WINDOW_POOLED5_1H_v1_ALGO_2026-07-03.md`
**Terminal:** PRE-TEST PARK (killed before engine build / before any queue trial)
**Goal status:** NOT HIT (mechanism weakly present but power-bound and economically sub-scale)
**Hypothesis:** `a98ea2d0-8293-4845-a688-40a5ae058397` (PARKED)
**Queue(s):** none — zero research-queue trials spent (that is the point of this paper)

---

## TL;DR

The alpha-discovery workflow (2026-07-03, graveyard-aware over 16 dead families) produced one surviving
pre-registered hypothesis: a calendar-time FOMC/CPI event strategy (long risk 24h→2h pre-event, flat through
the print, sign-of-first-post-event-bar continuation held 8/24h) on the pooled 5-symbol perp book — the first
fully NON-PRICE (calendar+clock) anchor tested on this platform. Because no engine can express calendar
windows, the pre-registered plan required a zero-trial offline event-study before the ~1-day engine build.
That pre-test (real Binance perp 1h klines 2019-09→2026-07, V202 calendar verbatim, 9bps RT cost, two
clock-matched placebos n=1833 each) shows: the Lucca-Moench pre-FOMC drift does **not** exist in crypto perps
(FOMC pre-window +14.8bps gross vs +17.3bps placebo baseline); CPI pre-drift and FOMC-H8 continuation are
positive but insignificant (t=0.88 / t=1.13); and the best surviving cell contributes ~+2.3%/yr book-level —
below the V102 10%/yr bar with no path to DSR≥0.90 at 20 events/yr. **Verdict: PARK; engine build cancelled;
zero trials and zero build-days spent.** The one honest residue: post-FOMC 8h continuation flips a
significantly mean-reverting baseline (placebo t=−3.5) to positive continuation (diff-t≈1.7) — a potential
zero-cost conditioning overlay if a live engine ever consumes calendar context, not a standalone strategy.

*(SIGNIFICANT_EDGE table omitted — no cell reached any gate; no backtest ran.)*

---

## 1. Background

Session start state: free-data directional alpha surface systematically exhausted (price-action family,
funding family, positioning/OI, XS momentum/breadth, cointegration/lead-lag all falsified 2026-06); live
book dormant except carry; operator asked for new profitable strategy proposals from the full research
record. The alpha-discovery workflow swept literature + quant forums with the graveyard as a hard
constraint, generated 27 candidate mechanisms, and adversarially killed 4 of 5 finalists pre-registration
(DELEV_FLUSH_FADE, FUNDING_SETTLEMENT_REV, post-expiry gamma-release Donchian, RR25 skew-z — see the
discovery output for post-mortems). MACRO_EVENT_WINDOW survived on orthogonality (non-price anchor),
cost math (1-3% event moves vs 9bps floor), and clean falsifiability (windows fixed a priori).

## 2. Hypothesis

**Mechanism:** Scheduled-macro-event calendar design. LEG A: long-only, position=+1 iff 2 ≤ h(t) ≤ 24
where h(t) = hours from closed 1h bar to next event (FOMC 19:00 UTC / CPI 12:30 UTC, embedded static
schedule identical to ingest V202 constants). BLACKOUT: flat T−2h → close of first full post-event bar b1.
LEG B: enter sign(close(b1)−open(b1)) at close(b1), time-exit after H ∈ {8,24} hours. No stops/TPs/sizing
knobs; unit position; each leg trades exactly twice per event.

**Pre-registration:** Hypothesis `a98ea2d0` registered 2026-07-02T17:30Z, BEFORE the pre-test ran
(2026-07-03) and before any engine existed. Falsification criterion stated: pooled Leg A mean in-window
return not positive AND pooled Leg B continuation not positive after costs across ~70 independent events.
Declared n_trials=60 (10 configs × (5 per-symbol + 1 pooled)).

**Type:** ALGO (no ML).

## 3. Methodology

No JVM backtest ran. Per the pre-registered plan (engine_exists=false → do not queue), the test was a
zero-trial offline event-study executed exactly on the pre-registered rule:

- **Data:** Binance USDT-M perp 1h klines via fapi (BTC 59,735 bars from 2019-09-08; ETH/XRP/BNB/SOL from
  listing → 2026-07-02). Run inside the VPS ingest container (local ISP blocks Binance).
- **Events in perp era:** FOMC n=55, CPI n=82 (V202 calendar verbatim, 2027 approximations excluded by
  data range). Primary unit of observation = equal-weight pooled book return per event (symbols are
  per-event correlated; per-symbol rows are supporting only).
- **Cost:** 9bps round trip per leg (platform taker floor).
- **Controls:** TWO clock-matched placebo sets — pseudo-events at 19:00 UTC (FOMC clock) and 12:30 UTC
  (CPI clock) on every day with no real event within ±2 days (n=1833 each) — isolating the event premium
  from unconditional drift and time-of-day beta.
- **Artifacts:** `research-scratch/mew_pretest/` (script, per-event CSVs, report JSON).

### 3.1 Statistical Gates (V11 + V60) — what they would have required

| Gate | Threshold | Binding? |
|---|---|---|
| n_trades | ≥ 100 | pooled events = 137 (would pass on count, but see DSR) |
| PF 95% CI lower | > 1.0 | unreachable at t≈0.8 |
| DSR (n_trials=60 declared) | ≥ 0.90 | **the killer — needs t≈3+, observed 0.8–1.1** |
| ag90 | (V60 floor removed) | best cell ≈ +2.3%/yr — fails V102 live bar regardless |

## 4. Parameter Space Explored

All pre-declared configs were evaluated offline (no free parameters existed to fish):

| Axis | Values |
|---|---|
| event_set | FOMC+CPI, FOMC-only (CPI-only shown for decomposition) |
| leg_config | pre-only, post-only, composite |
| post_hold H | 8h, 24h |
| pre_window / buffer | 24h / 2h (FIXED, not swept) |

**Total research-queue iterations: 0. Cumulative DSR-deflated trial count spent: 0.**

## 5. Results

### 5.1 Pooled book, net of 9bps RT per leg (bps/event)

| Cell | n | gross | net | t(net) | hit | clock-matched placebo (net) |
|---|---|---|---|---|---|---|
| Leg A — ALL | 137 | +31.2 | +22.2 | 0.80 | 48.9% | — |
| Leg A — FOMC | 55 | +14.8 | +5.8 | 0.14 | 47.3% | +8.3 (**below placebo**) |
| Leg A — CPI | 82 | +42.2 | +33.2 | 0.88 | 50.0% | +3.2 (excess ≈ +30, excess-t ≈ 0.8) |
| Leg B H8 — ALL | 137 | +19.5 | +10.5 | 0.55 | 53.3% | — |
| Leg B H8 — FOMC | 55 | +37.4 | +28.4 | 1.13 | 56.4% | −14.3 (t=−3.47) → **diff-t ≈ 1.7** |
| Leg B H8 — CPI | 82 | +7.5 | −1.6 | −0.06 | 51.2% | −12.2 |
| Leg B H24 — ALL | 137 | −10.9 | −19.9 | −0.55 | 49.6% | −16.5 / −14.0 |

Composite (A + B24) net by year: 2019 −28 / 2020 −43 / 2021 +96 / 2022 −118 / 2023 +27 / 2024 +77 /
2025 +34 / 2026 −95 bps — no regime stability.

### 5.2 Failure-mode analysis

1. **The literature anchor does not transfer.** Pre-FOMC drift (the design's strongest citation) is
   *absent*: FOMC pre-window drift sits below the same-clock unconditional baseline. Crypto perps do not
   pay the equity announcement premium in the pre-window.
2. **The only mechanism signature is FOMC-H8 continuation** — the baseline first-bar direction
   significantly mean-reverts over 8h (placebo t=−3.5 at both clocks, consistent with the known 1h
   mean-reversion/cost-floor grave), and FOMC flips it to continuation (+28.4 net, diff-t≈1.7, p≈0.09).
   Real-ish, but 8 events/yr × 28bps ≈ **+2.3%/yr** — an order of magnitude below a deployable edge.
3. **Power is wall-clock-bound, not breadth-bound.** Symbols are per-event correlated; only TIME adds
   events (+20/yr). Reaching t≈3 at the observed effect/vol ratio needs O(2000) events ≈ decades.
   This is the same event-rarity ceiling that killed LIQ_FADE interim reads and the funding-Z sweeps.

## 9. Infrastructure Notes

- Local ISP DNS-intercepts `fapi.binance.com` (SSL hostname mismatch) — Binance-touching research scripts
  must run on the VPS (ingest container has pandas/numpy/httpx and clean egress).
- The prod journal has no `DATA_WISHLIST` entry_type — the convention is `IDEA_BACKLOG` with a
  `DATA_WISHLIST:` title prefix.
- `research_journal` status flips for PARK are done server-side by services (e.g. reviews.py); did the
  same surgically via psql (`postgres` role, not `blackheart`).

## 10. Methodology Compliance Audit

| Rule | Compliant? | Notes |
|---|---|---|
| Research universe (5 plumbed symbols) | YES | BTC/ETH/SOL/BNB/XRP |
| Intervals in {5m, 15m, 1h, 4h} | YES | 1h |
| Research-mode only — no live promotion | YES | nothing built or deployed |
| V11 + V60 gates honored | YES | no gate loosened; pre-test used them as the yardstick |
| Pre-registration before testing | YES | hypothesis a98ea2d0 registered 2026-07-02, pre-test ran 2026-07-03 |
| No free-parameter fishing after results | YES | windows fixed a priori; no post-hoc variants run (NFP explicitly declined) |
| Append-only durable evidence | YES | HYPOTHESIS + IDEA_BACKLOG + STRATEGY_OUTCOME rows; status flips only |
| Declared n_trials respected | YES | 0 of 60 spent; family closed at zero cost |

## 11. Conclusions

1. **The pre-FOMC announcement drift does not exist in crypto perps** — pre-event drift is at/below the
   same-clock unconditional baseline (FOMC +14.8 gross vs placebo +17.3).
2. **Post-FOMC 8h continuation is the only real signature** (flips a t=−3.5 mean-reverting baseline to
   +28bps net, diff-t≈1.7) but is worth ~2.3%/yr — a conditioning overlay at best, never a strategy.
3. **Calendar-event designs on this platform are power-bound by wall-clock** (20 events/yr, symbols
   correlated per event) — no sweep, interval, or breadth choice can fix n; DSR≥0.90 is unreachable
   for decades.
4. **Implication for the research loop:** the discovery→pre-register→zero-trial-pre-test→build-gate
   pipeline worked exactly as designed — a plausible, literature-backed, adversarially-vetted hypothesis
   was killed for ~$0 in compute, 0 queue trials, and 0 engine days. Use this ladder for every
   engine-absent hypothesis.
5. The last cheap non-price anchor is now spent; remaining unlocks stay what they were: **scale the carry
   book** (proven, deployment-gated) and **paid/accruing data surfaces** (forceOrder tape ~Sept-2026,
   Deribit options accumulation).

## 12. Data Wishlist

| Priority | Item | Blocker type |
|---|---|---|
| 1 | ~~MacroEventWindowEngine~~ — **CANCELLED by this pre-test** (wishlist 931c8501 → STALE) | — |
| 2 | Minute-bar (1m/5m) backtest support around event timestamps would enable a *different* sharper-entry event hypothesis — only worth revisiting if some other driver funds intraday data | backfill + JVM |

## 13. Appendix — Audit Trail

| Item | ID |
|---|---|
| Hypothesis | `a98ea2d0-8293-4845-a688-40a5ae058397` (PARKED) |
| Engine-build wishlist | `931c8501-d980-4d31-9ffe-bea1d5d2fa8f` (STALE — build cancelled) |
| STRATEGY_OUTCOME journal | `cc6d0342-c445-4242-9e56-e591a42f57aa` |
| Queue(s) | none |
| Discovery workflow | `wf_4f038a2b-d9a` (16 agents; 4 siblings killed at gate) |
| Pre-test artifacts | `research-scratch/mew_pretest/{mew_pretest.py, pretest_report.json, pooled_book_event_returns.csv, per_symbol_event_returns.csv}` |

---
*Paper written at the pre-test terminal; no queue row exists, so no `POST /papers/<queue_id>/generate` registration applies.*
