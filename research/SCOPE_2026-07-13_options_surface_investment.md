# Investment Scope — Deribit Options-Surface Data (Tardis backfill)

**Date:** 2026-07-13 · **Author:** operator session · **Decision:** GO (recommended)
**One-liner:** Buy the historical Deribit options-chain from Tardis.dev (~one-time low-hundreds $), run the *already-built* loader, and unlock the only genuinely **orthogonal** alpha source left — options-implied skew/vol — after the price/volume families were exhausted (DCB fake, MRO dead, ATR_MOM bull-only, TPB real-but-sub-DSR).

---

## 1. Why this, and why now

Every family this platform has falsified is **derived from price + volume + funding** — the same information re-sliced. The wall we hit (DSR-bound, trade-scarce) is what you get when you keep mining one information source. Options-implied vol is **new information**: it prices the market's *forward* fear/greed (skew) and vol expectation (term structure), set by a different population (option writers/hedgers) than spot flow. That orthogonality is the whole point of the strategic direction (many *uncorrelated* signals) and is the single most likely place a **certifiable, low-correlation** edge exists.

Documented edge shapes it opens (all real in the literature + crypto):
- **VRP (variance risk premium):** implied (DVOL) systematically > realized vol → short-vol / long-carry timing.
- **Risk-reversal (RR25) skew as a fear gauge:** put-wing IV − call-wing IV; skew spikes mark capitulation/stress → a regime/stress **gate** on directional entries (the exact lever that would have helped DCB/TPB's neutral-chop drag).
- **Vol term-structure slope:** backwardation vs contango as a risk-on/off regime filter.

## 2. The gap is *data only* — the engineering is already built (verified 2026-07-13)

| Component | Status |
|---|---|
| Historical Tardis loader `sources/deribit_options_history.py` (commit `147e14a`) — reads Tardis `options_chain` CSV(.gz), hourly-downsamples, normalizes mark_iv, PIT-safe, idempotent `macro_raw` write | ✅ BUILT + tested + CLI `blackheart-ingest-deribit-history` (has `--no-persist` dry run) |
| Live forward feed `sources/deribit_options.py` (25-Δ RR, ATM IV, term spread) | ✅ BUILT, **gated OFF** behind `INGEST_DERIBIT_OPTIONS_ENABLED` |
| Feature defs `btc/eth_rr25_skew_30d`, `_zscore_30d`, `vol_term_spread` (commit `2e4e6ae`, V187) | ✅ DEFINED (passthrough/zscore of the `deribit_rr25_*` macro_raw series) |
| DVOL vol-*level* feed (`deribit.py`, free, backfills to ~Mar 2021) | ✅ ALREADY FLOWING (`feature_store.dvol_level` = 11,441 rows) |
| **The historical surface *shape* data (skew / term structure)** | ❌ **MISSING — `rr25_skew_30d` / `vol_term_spread` = 0 rows.** Deribit's free tier serves per-strike IV **live only, no historical backfill** (loader docstring) → must be bought from Tardis |

So the loader, the live feed, the features, and the tests all exist. **What's missing is the ~$X of Tardis data to feed the loader once.** This is the cheapest possible "new data source" unlock.

## 3. What to buy (precise spec)

- **Vendor:** Tardis.dev
- **Dataset:** `options_chain` (the format `deribit_options_history.py` reads — CSV.gz)
- **Exchange:** Deribit · **Underlyings:** BTC + ETH (both, per the feature defs)
- **Window:** 2022-01-01 → present. **Rationale:** must span the **2022 bear** (skew's highest-signal regime), 2023–24 recovery, 2025–26 — the same OOS windows the walk-forward folds use. Pre-2022 optional (thin Deribit ETH options liquidity).
- **Resolution:** intraday quotes; the loader **downsamples to hourly** (last quote per instrument per [H,H+1)), so full tick isn't required — the smallest granularity Tardis offers that includes all listed strikes hourly is sufficient.
- **Est. cost:** Tardis is subscription (~low-hundreds $/month for historical API/download access). Strategy: **one month (~$200–400) to download the full 2022→now history, then cancel** → effectively a one-time cost. Ongoing live accrual is **free** (Deribit public API via the existing gated feed). *→ needs a Tardis quote to confirm exact $.*

## 4. Execution plan (effort: ~0.5–1.5 person-days once data is in hand — infra is built)

1. **Buy + download** the Tardis Deribit BTC+ETH `options_chain` history (operator; ~$200–400 one-time).
2. **Dry-run** the loader on the download: `blackheart-ingest-deribit-history --no-persist` → confirms parse + 4 series (`deribit_rr25_btc/eth_30d`, `deribit_atm_iv_*`, `deribit_term_spread_*`) before writing.
3. **Backfill** `macro_raw` (drop `--no-persist`) → populates the hourly skew/term-structure series 2022→now.
4. **Recompute** `feature_store` skew columns for BTC/ETH (the passthrough/zscore features) — a feature-recompute job over the backfilled range.
5. **Turn on the live feed** — `INGEST_DERIBIT_OPTIONS_ENABLED=true` (VPS `/etc/blackheart/*.env`) so skew accrues forward for eventual *live* gating.
6. **Research** (the loop): pre-register + test the families in §5, **PIT-clean** (apply the DCB lesson — the skew series is genuinely PIT here, snapshot-at-bar, no future-vintage model).

## 5. Candidate alpha families unlocked (research backlog)

- **(A) RR25-skew stress-gate** — already pre-registered (hypothesis `470ca035`, wishlist `b820fc10`): gate directional entries on `rr25_skew_zscore_30d >= +0.5 OR vol_term_spread <= 0` to skip neutral-chop; targets the exact drag that kept DCB/TPB below the bar. **Two-sided, causal, no ML** — structurally the anti-DCB.
- **(B) VRP timing** — DVOL (have it) − realized-vol (have it) → a carry/short-vol overlay or a sizing signal.
- **(C) Term-structure regime** — contango/backwardation as a risk-on/off filter on the live book.
- **(D) Skew-zscore mean-reversion / momentum** — skew as its own tradeable series.

## 6. ★ Stage-0 cheap validation FIRST (de-risk before any JVM work — $0)

Before touching the trading JVM, run the **offline A/B** on existing `backtest_trade` rows: join the backfilled skew/term-structure onto historical DCB/TPB/DCB_SWEEP trades and measure whether the §5(A) gate would have lifted PF / cut the neutral-chop losers. This answers "does skew actually predict here?" for **zero incremental cost** and decides whether the ~hours JVM gate-patch is worth it. (This is the discovery-ladder's first rung; do not skip it.)

## 7. Odds, risks, honest caveats

- **Orthogonality is the upside** — but must be *measured*: compute the correlation of the skew-gated P&L vs the existing book before believing the diversification.
- **The 25-Δ construction is a documented geometric approximation** (no per-instrument greeks on the free/summary endpoint; snapped-to-listed-strike). Fine for a research proxy; note it in any cert.
- **Skew may be real-but-weak** (like everything else) — Stage-0 gates this cheaply.
- **Data quality:** verify Tardis Deribit ETH-option coverage/gaps in 2022 (thin early liquidity) before trusting the 2022-bear cells.
- **This is the only unlock with built infra + tiny cost + a truly new information source** — vs. a 2nd exchange (10–15 person-days, helps execution not signal), more coins (same exhausted price families), or a new engine (LIQ_FADE is time-gated to ~Sept; bear-gen is already covered by TPB and sub-DSR).

## 8. Recommendation & first step

**GO.** The cost is small and one-time, the engineering is done and tested, and it's the highest-odds path to a *certifiable, uncorrelated* edge. **First concrete step: get a Tardis.dev quote for the Deribit BTC+ETH `options_chain` 2022→now.** In parallel (free, now) I can dry-run the loader against its synthetic-CSV tests to re-confirm readiness so we're ready to backfill the moment the data lands.

*Cross-refs: pre-registered skew-gate `470ca035` / wishlist `b820fc10` (memory: alpha-discovery 2026-07-10); the exhausted price/volume map (memory: research-run 2026-07-13); the DCB look-ahead lesson — skew here is PIT-clean snapshot-at-bar, no future-vintage model.*
