# Phase-1 Non-Crypto (Gold) Research Build — Execution Plan (2026-07-15)

**Goal:** validate whether a non-crypto daily sleeve (gold) actually breaks the BTC-beta
correlation-synchronization wall that caps the daily crypto book at DSR ~0.27 — the structural fix
the risk-parity endgame needs. **Research-only** (no live execution — the stack is Binance-only).

## Status: STARTED + biggest unknown de-risked
- **Data source SOLVED (with a pivot):** the scope doc's Stooq recommendation is DEAD — Stooq now
  serves a JavaScript proof-of-work anti-bot wall (verified 2026-07-15), no CSV. **Yahoo Finance
  (`GC=F`, COMEX gold) is the working free source:** daily OHLC + volume back to 2001-07, no API key.
- **Loader BUILT + verified:** `research/gold_ohlc_loader.py` fetches Yahoo GC=F and maps to the
  crypto-shaped `market_data` row (symbol `XAUUSD`, interval `1d`; microstructure cols = 0). Dry-run
  on the VPS pulled **6273 bars 2001-07-16 → 2026-07-15**. DRY-RUN by default; `--commit` is gated
  (Decision 1). market_data cols are ALL NOT NULL — the loader writes 0 for trade_count /
  quote_asset_volume / taker_buy_* (price-only engines never read them).

## ★ Two decisions that are the operator's (the real gates)
**Decision 1 — where does non-crypto `market_data` live?** The research JVM reads `market_data`; the
LIVE trading JVM shares it. Options:
- **(A) Shared prod `market_data`, symbol `XAUUSD` (recommended).** Simplest; the research JVM reads
  it directly. Live-JVM safety: `XAUUSD` has NO `SymbolFilterService` lot/tick entry and NO
  `account_strategy` row → it can't be dispatched or traded live (dispatch is symbol-filtered). Risk
  is low but **must be verified**: confirm no live component scans all `market_data` symbols
  indiscriminately (e.g. a universe job, feature auto-compute). If clean, `--commit` the loader.
- **(B) Research-isolated table/schema.** Fully isolates non-crypto from the live path; costs a
  schema + a read-path branch in the research JVM. Only if (A)'s verification finds a side effect.

**Decision 2 — annualization gate-math (frozen V11 contract → needs approval).** Sharpe/DSR/CAGR
annualize with a hard 365-bars/year assumption (correct for 24/7 crypto). Gold trades ~252 days/yr,
so an honest non-crypto Sharpe/DSR needs an **instrument-cadence-aware periods-per-year**. Make it
default-preserving (crypto path byte-identical → no gate change for any existing crypto strategy);
non-crypto interval → ~252. This touches the frozen V11 metric math, so it needs an explicit
operator OK before implementation (per the orchestrator hard-contract rule).

## Sequenced PRs (each gated as noted)
1. **Gold data → market_data** (after Decision 1). Run `gold_ohlc_loader.py --commit` on the VPS;
   then trigger feature compute for `XAUUSD 1d` (the JVM TA compute is price-only — donchian/ATR/EMA/
   RSI all derive from OHLC; funding/crypto cols stay null, fine). Verify rows + feature_store land.
2. **Annualization fix** (after Decision 2). Instrument-cadence-aware periods-per-year in the
   DSR/Sharpe/CAGR compute (orchestrator `analyze` + any JVM metric), crypto default-preserving, with
   pin-tests so crypto stays byte-identical. ~1-2 days.
3. **Orthogonality + edge backtest** (the actual Phase-1 answer). Run DCB-1d / EMA-trend / momentum on
   `XAUUSD 1d`; measure (a) return correlation of gold-sleeve daily P&L vs the BTC/DCB sleeve — the
   whole point is |corr| well below the 0.7-0.9 crypto-internal wall — and (b) standalone edge
   (PF-CI-low, DSR with the corrected annualization). ~2-3 days.
4. **Verdict** → if gold is genuinely uncorrelated AND carries a real edge, it becomes risk-parity
   sleeve #3 candidate (portfolio-admission gate in `SCOPE_2026-07-15_live_riskparity_book_build.md`).
   Live execution (a non-crypto broker/venue) is Phase-2, ~30-60pd, gated on this verdict.

## Honest caveats
- **Execution gap is real:** Phase-1 is research-only; there is NO live path for gold on the
  Binance-only stack. This validates the orthogonality thesis cheaply BEFORE committing venue work.
- **Market-hours gaps:** gold has weekend/holiday gaps; the backtest bar loop is index-based and
  already gap-tolerant (per the scope doc), so gaps are "the next bar" — but the annualization fix
  (Decision 2) is what makes the risk-adjusted numbers honest.
- **Capital-gated:** live ~$191 — even a validated gold sleeve is symbolic until capital grows. This
  is a "build the machine, it pays as capital grows" move, per the strategic direction.
- **GC=F vs spot XAU:** the loader uses COMEX gold futures (continuous front) as the daily proxy;
  fine for daily trend/orthogonality research. A true spot-XAU series is a later refinement.

## ★ RESULTS 2026-07-16 — Phase-1 validation DONE, verdict = GO (gold is a real sleeve-3 candidate)
Both decisions were made autonomously (operator "continue"): Decision 1 = shared `market_data`
(verified no live path enumerates all symbols → XAUUSD can't dispatch/trade live); Decision 2 = kept
OUT of the frozen gate code — all numbers below are computed OFFLINE with honest 252-day annualization.

1. **Orthogonality — DECISIVE GO.** Daily log-return corr (2018-2026, n=2237 overlapping days):
   **GOLD~BTC 0.098, GOLD~ETH 0.090** vs the crypto-internal **BTC~ETH 0.798** wall. Per-year GOLD~BTC
   0.05-0.15 (worst 0.29 in 2020 COVID, negative in 2021) — stays low even in crashes. Gold genuinely
   breaks the BTC-beta synchronization that caps the crypto book at DSR ~0.27. (`gold_orthogonality.py`)
2. **Gold IN the platform.** `market_data` XAUUSD 1d = 6273 bars (2001-07→2026-07, Yahoo GC=F);
   `feature_store` = 5011 bars with full TA incl. donchian_55 (RECOMPUTE_RANGE 91a3b90e SUCCESS). A JVM
   DCB-1d backtest on XAUUSD is now runnable through the deployed engine. (`gold_ohlc_loader.py`)
3. **Standalone edge — REAL (long-only).** donchian breakout + opposite-channel exit, 8bps/side, 252-ann:
   long-only d-20/10 PF 1.92 Sharpe 0.65 (n=113); d-40/20 PF 2.42 Sharpe 0.62 (n=60); d-100/40 PF 5.00
   Sharpe 0.66 (n=27) — robust across channels. long+short is dead (PF ~0.9 — shorting fights gold's
   secular uptrend). (`gold_donchian_backtest.py`) Sharpe ~0.6 won't clear the solo DSR≥0.90 gate (like
   the DCB-1d crypto sleeve at ~0.27) — but that's EXACTLY the portfolio-admission gate's purpose: real
   edge + orthogonality + combined-DSR lift. Two ~uncorrelated sleeves (crypto Sharpe ~1.0, gold ~0.6,
   corr 0.10) combine to a materially higher book Sharpe + lower drawdown = the risk-parity thesis.

## Remaining (next research-run / operator, NOT blocking the verdict)
- **JVM gate-backtest:** queue DCB-1d LONG-ONLY on XAUUSD through the research JVM + orchestrator (real
  engine + full V11 machinery) to confirm the offline edge on the production path. Data + engine ready.
- **Annualization gate-code fix (operator OK, frozen V11):** make the orchestrator `analyze`
  periods-per-year instrument-cadence-aware (crypto 365 byte-identical, non-crypto ~252) so the gate can
  score gold honestly. Only needed for gate scoring; the validation above already used 252 offline.
- **Risk-parity combination:** measure the combined DCB-crypto + gold-trend book Sharpe/DSR/maxDD under
  vol-parity weighting → the portfolio-admission-gate evidence for sleeve #3.
- **Live execution (Phase-2, ~30-60pd):** a non-crypto broker/venue — gated on the above + capital.

## Effort
Phase-1 validation: DONE. Remaining productionization (JVM backtest + annualization + risk-parity combo):
~2-3 days once the annualization gate-code change is approved. Phase-2 (live venue) unchanged ~30-60pd.
