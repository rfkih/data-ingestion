# Non-Crypto / Low-Beta Daily Instrument — Implementation Scope (2026-07-15)

**Structural fix for the correlation-synchronization wall.** The daily crypto research book is
capped at solo DSR ~0.27 (see `SCOPE_2026-07-15_live_riskparity_book_build.md`, Sleeve 1) because
every coin is BTC-beta (pairwise corr 0.7-0.9). Same-universe diversification (the XS-momentum-neutral
sleeve, Sleeve 2) hedges *market beta* but is still fed by the same crypto price stream. A **genuinely
non-crypto sleeve** (equity-index proxy, gold, or an FX major) is the only *universe* change that adds
an orthogonal risk driver and lifts portfolio Sharpe by ~√(N/(N−1)) per uncorrelated sleeve. This
feeds the risk-parity endgame (currently DCB-1d + carry, per that scope).

> This is a **scoping/planning document**. No production code is written here. The honest headline is
> up front: **Phase 1 (research-only) is cheap and should be done first; live execution is gated on a
> new non-crypto venue/broker the platform does not have and Binance cannot provide.**

---

## 0. The execution gap — read this first (it reframes everything)

The platform's entire execution path is **Binance spot + USD-M perp, USDT-quoted, `BTCUSDT`-notation,
HMAC-signed** through `blackheart-exchange-gateway`. Concretely:

- `blackheart-exchange-gateway/src/services/binanceService.js` — `placeMarketOrder` posts to
  `/api/v3/order` with `quoteOrderQty` (BUY) / `quantity` (SELL), USDT pairs only.
- `blackheart-trading-engine/.../service/live/LiveTradingDecisionExecutorService.java:779,844` — the
  OPEN path branches `if ("BNC".equalsIgnoreCase(account.getExchange()))` and **rejects everything
  else** ("Unsupported exchange for LONG/SHORT entry").
- `service/exchange/SymbolFilterService.java` — lot/tick/precision are Binance spot values, resolved
  from a hardcoded map + live Binance `exchangeInfo` fallback. Nothing else.

**Binance does not list SPX, gold, DXY, or EURUSD as tradeable USDT perps in any form the operator can
legally/practically trade from Indonesia.** There are crypto *proxies* (tokenized stocks, XAUT
gold-token, forex-perp DEXes) but each is either unavailable to this account, thin/untrustworthy, or a
different execution stack entirely. **Therefore live execution of a real non-crypto instrument requires
a NEW venue (equity/FX/futures broker), which is a larger lift than the "2nd crypto exchange" already
scoped** (`project_second_exchange_scoping_2026-06-20.md`: ~48-66 person-days for the *first*
Binance-family crypto venue, and that reused an HMAC/USDT/`BTCUSDT` contract a stock broker shares
none of).

The good news: **you do not need live execution to break the DSR ceiling in research.** Orthogonality
and edge are measured from a backtest on a daily OHLC series — which the data plane can carry with
modest work. **Validate first, commit venue money only if it pays.**

---

## 1. Instrument candidates (ranked)

Ranked by (a) expected orthogonality to BTC, (b) daily-bar data availability/cost, (c) execution
feasibility on the current stack.

| Rank | Instrument | BTC orthogonality | Daily data (free) | Live execution feasibility |
|---|---|---|---|---|
| **1** | **Gold (XAU/USD, or GLD ETF proxy)** | **Best.** Low/variable corr to BTC (often ~0, occasionally negative in risk-off); a *different* macro driver (real rates, safe-haven, USD). Not a risk-on twin of BTC the way equities have become. | Stooq (`XAUUSD`/`GC=F`), Yahoo (`GLD`, `GC=F`), Alpha Vantage. Free daily, deep history. | **None on Binance.** Needs a metals/futures broker OR the XAUT gold-token (thin, not on this account). Research-only in Phase 1. |
| **2** | **US equity index (SPX via `SP500`/`^GSPC`, or ES future / SPY ETF)** | **Medium.** Crypto is *positively, regime-dependently* correlated with US equities, strengthened post-2020 (documented in `V181` migration comment). Diversifying in calm regimes, converges toward BTC in risk-off crashes — so it lifts average-Sharpe but is weakest in the tail. | **Already ingested.** `SP500` + `NASDAQCOM` daily FRED closes flow into `feature_values` today (V181, `fred.py` `_PUBLICATION_LAG_DAYS` includes both at lag 1d). Also Stooq/Yahoo (`^GSPC`, `SPY`, `ES=F`). | **None on Binance.** Needs an equity/futures broker. Research-only Phase 1. |
| **3** | **FX major (EUR/USD or DXY)** | **Good, but low edge density.** DXY/EURUSD is macro-orthogonal to BTC, but daily FX trend/carry edges are thin, heavily arbitraged, and low-vol — likely the weakest *standalone* edge even if the most orthogonal. `DTWEXBGS` (trade-weighted USD) is already ingested (lag 7d). | Stooq (`EURUSD`), Yahoo (`EURUSD=X`), Alpha Vantage FX, FRED `DEXUSEU`/`DTWEXBGS`. Free daily. | **None on Binance.** Needs an FX broker (or a forex-perp DEX = separate stack). Research-only Phase 1. |

**Recommendation: Gold (candidate 1) as the primary research target, S&P 500 (candidate 2) as the
cheap warm-up** because its data is *already in the platform*. Gold has the best expected orthogonality
(a genuinely different macro driver, not a BTC risk-on twin) and therefore the largest Sharpe lift per
the √(N/(N−1)) argument. S&P is the fastest thing to *test the pipeline* with because `SP500` daily
closes already sit in `feature_values` — but note that S&P closes currently live in `feature_values`
as **context features, not a tradeable `market_data` OHLC series** (see §2), so even the "already
ingested" candidate needs a small data-plane addition to be *backtestable as an instrument*.

---

## 2. Data-plane work (`blackheart-ingest` + schema)

### 2a. What already exists (the stepping stone)
- `blackheart-ingest/src/blackheart_ingest/sources/fred.py` already pulls **`SP500`, `NASDAQCOM`**
  (daily, lag 1d) plus `DTWEXBGS`, `VIXCLS`, rates/credit — all US macro. These land in `macro_raw`
  and are computed into **`feature_values`** as *global macro context* (V181: `sp500_level`,
  `sp500_return_20d/60d`, `sp500_realized_vol_20d`, `nasdaq_*`). This proves the ingest→macro_raw→
  feature_values path for a non-crypto daily series already works and is PIT-disciplined.
- **Critical distinction the V181 migration comment makes explicit:** these are inputs to research
  computed "at join time from these + the BTC return stream," NOT a `market_data` OHLC row a strategy
  engine can open a position on. `feature_values` is a single-table macro-context store; `market_data`
  is the tradeable OHLC bar table the backtest engine iterates.

### 2b. The gap — a tradeable non-crypto OHLC series
To *backtest an instrument* (not just use it as a context feature) you need rows in **`market_data`**
(`V1__baseline.sql:11`):
```
market_data(symbol VARCHAR(10), interval VARCHAR(5), start_time, end_time,
            open_price, close_price, high_price, low_price, volume,
            trade_count, quote_asset_volume, taker_buy_base_volume, taker_buy_quote_volume, ...)
```
Schema fit findings:
- **`symbol VARCHAR(10)` / `interval VARCHAR(5)`** — fits `XAUUSD`, `GLD`, `SPX`, `EURUSD`, `1d`. No
  schema change needed for the identifier. (`feature_store.symbol` is VARCHAR(20) — also fine.)
- **OHLC + volume are all `NOT NULL`.** A daily equity/FX/metal bar has OHLC; **volume/trade_count/
  taker_* are crypto-microstructure columns with no equity/FX analogue.** Options: (a) write `0` for
  the crypto-only columns (they're `NOT NULL` but a strategy that doesn't read them is unaffected — DCB
  uses price/ATR/Donchian, not taker volume), or (b) map an available volume (equity share volume) into
  `volume` and zero the taker split. Recommend (a) for a first pass; it's honest ("no microstructure
  data for this venue") and unblocks the price-only strategies (DCB, momentum, trend) that are exactly
  the ones worth testing for orthogonality.
- **No `exchange`/venue dimension on `market_data`** — it's implicitly Binance. A non-crypto series
  would coexist by `symbol` alone. This is acceptable for research (the symbol namespace is the
  discriminator) but is a latent gotcha if `XAUUSD` ever collided with a crypto symbol (it won't).

### 2c. New ingest source
Add one source module `sources/stooq.py` (or `yahoo.py`) that pulls **daily OHLC** for the chosen
symbols and writes to **`market_data`** (not `macro_raw`) — this is a *new write target* for ingest,
which today only writes `market_data` via the JVM, never via ingest.
- **Source choice:** **Stooq** (free, no API key, direct daily-OHLC CSV, deep history for indices/FX/
  commodities) is the lowest-friction. Yahoo (`yfinance`) is richer but rate-limits/ToS-fragile.
  Alpha Vantage is free-with-key but 25 req/day throttled. For a handful of daily symbols, **Stooq**.
- **PIT discipline:** reuse `shared/pit_guards.py` (the same `partition_by_pit` FRED uses). A daily
  close is knowable only end-of-day → **lag ≥ 1 day** on `event_time`/`start_time`, exactly as
  `fred.py` stamps `SP500` (`_DEFAULT_LAG_DAYS = 1`). Do NOT stamp a bar's close at its own session
  open — that's the same class of look-ahead the DVOL/skew trap flagged in memory.
- **The market-hours / calendar-gap question (the real non-crypto novelty):**
  - Crypto `market_data` is **24/7, contiguous daily bars** (365 bars/yr). Equities trade ~252
    days/yr (weekends + holidays absent); FX ~260 (weekends absent, near-24h weekdays); gold spot
    ~near-24h weekdays. **A non-crypto daily series has legitimate calendar gaps.**
  - **The backtest engine tolerates this.** The engine iterates a `List<MarketData>` **by list index,
    not by wall-clock delta** (`BacktestTradeExecutorService` walks the ordered bar list; it already
    handles price *gaps* explicitly — `gappedThroughStopLoss` fills a gapped stop at the open,
    `BacktestTradeExecutorService.java:239-259`). So a Fri→Mon jump is just "the next bar," same as any
    overnight gap. **No 24/7 assumption is baked into the bar loop itself.**
  - **Where the gap DOES bite:** (i) any **annualization** that assumes 365 bars/yr (DSR, Sharpe,
    CAGR) will be *wrong* for a 252-bar/yr instrument — the return-per-bar → annual scaling must use
    the instrument's real bars/yr, not 365. This is the single most important correctness fix and it
    lives in the metrics layer, not the bar loop. (ii) Any **cross-series join** (BTC daily vs SPX
    daily) must align on date and decide gap-fill policy (ffill SPX across the crypto weekend, or
    restrict the joint sample to equity trading days). `feature_values` already ffills macro across
    gaps with an `max_ffill_age_hours` cap (72h for daily FRED series) — reuse that policy.

### 2d. Feature compute
The macro feature-compute path (`features/compute.py`, `definitions.py`) already computes returns/vol
from a daily series (`_change_pct`, `_rolling_realized_vol` with `annualize_factor=252` — note V181
*already uses 252 for SP500 vol*, confirming the platform can carry a 252-day-year series). For a
*tradeable* series, the JVM's `TechnicalIndicatorService` computes `feature_store` (EMA/ATR/Donchian)
from `market_data` — it is **price-series-generic** (it reads OHLC, computes TA4j indicators) and does
**not** require crypto microstructure, so it works on a non-crypto OHLC series as-is, provided the
`market_data` rows exist. **No engine change needed to compute features on the new series.**

**Data-plane effort: ~3-5 person-days** (one Stooq source module + `market_data` write path in ingest
+ PIT-lag config + a small backfill of daily history for the chosen symbols + verify feature compute).

---

## 3. JVM work (`blackheart-trading-engine`)

### 3a. Instrument abstraction — do you need one?
The platform has **no `instrument`/`contract_spec` abstraction today**; "symbol" is a bare string and
every per-venue fact (lot/tick/precision/fees) is Binance-hardcoded in `SymbolFilterService` +
`DEFAULT_FEE_RATE` (`project_second_exchange_scoping_2026-06-20.md`). **For research-only (Phase 1) you
do NOT need to build one** — the backtest reads `market_data` by symbol/interval, computes features,
and runs the strategy. The pieces that assume crypto and must be checked:

- **Funding / perp:** the DCB/momentum/trend engines are **spot-price strategies with no funding
  term.** Funding only enters carry (`FundingCarryStrategyEngine`) and the funding-Z DCB_SWEEP variant.
  A non-crypto daily instrument simply has **no funding** — do not seed it into any funding-dependent
  engine. `feature_store.funding_rate_*` columns stay NULL for it (they're nullable). **No change
  needed; just don't route it to carry.**
- **Fee/slippage:** backtest uses one global `DEFAULT_FEE_RATE=0.0004` (0.04%, Binance USD-M taker) +
  `DEFAULT_SLIPPAGE_RATE=0.0005` (`BacktestService.java:37-39`). **These are wrong for equities/FX/
  gold** (equity ETF ~1-5bps commission + spread; retail FX ~fractions of a pip; futures ~fixed
  per-contract). For an honest Phase-1 edge test, **pass an explicit `feeRate`/`slippageRate` on the
  backtest request** (both are already request-overridable — `BacktestService.java:127`) sized to the
  target broker's real costs. No code change; a per-run parameter. (The permanent fix is S3 — wire
  `fee_schedule` per venue — but that's a live-path concern, defer to Phase 2/3.)
- **Annualization / bars-per-year:** as noted in §2c, the DSR/Sharpe/CAGR annualization assumes 365
  bars/yr for a daily interval. **This is the one JVM metrics correctness item for Phase 1.** Locate
  where the daily interval maps to periods-per-year in the stat-rigor computation and make it
  instrument/calendar-aware (252 for equities, ~260 FX, ~252-260 gold) — otherwise a 252-bar/yr
  instrument's DSR is mis-scaled and the whole orthogonality verdict is unreliable. **This is the
  highest-value, must-do JVM fix for research.** (Estimate ~1-2 days incl. finding every annualization
  site and adding a calendar/bars-per-year input to the backtest request.)
- **Backtest bar-count cap:** `MAX_BACKTEST_BARS=600,000` is bar-count based and interval-blind — a
  daily non-crypto series is thousands of bars, trivially under the cap. No change.

### 3b. `account_strategy` seed
To run the strategy in the research JVM it needs an `account_strategy` seed row (symbol, interval,
strategy code) on the research account — same as any new crypto symbol (`CLAUDE.md` data-plane notes:
"data-ready but NOT research-ready: no `account_strategy` seed rows yet"). This is a seed migration
(one V-migration), not code. ~0.5 day.

### 3c. Execution path (Phase 2+ only — NOT Phase 1)
For live execution the JVM needs the same work as adding a venue, **plus** an instrument abstraction
the crypto-venue scope did not need:
- The multi-exchange **scaffolding already exists and is dark** (`service/exchange/ExchangeClient`
  interface, `ExchangeRegistry`, `ExchangeMetadataService`, `SymbolNotationTranslator`, V193
  `exchange`/`instrument_spec`/`fee_schedule` tables, `app.exchange-routing.enabled` flag — see
  `docs/MULTI_EXCHANGE_ADD_A_VENUE.md`). A new broker plugs in as a new `ExchangeClient` +
  `instrument_spec` rows + gateway service.
- **BUT** the crypto scaffolding assumes **spot MARKET orders, USDT quote, HMAC signing, `exchangeInfo`
  filters.** An equity/FX/futures broker is a *different execution model*: contract multipliers,
  margin, settlement, session-open-only fills, potentially FIX or a broker-specific REST auth (OAuth,
  not HMAC), and calendar-aware order-hours. This is why live non-crypto is materially bigger than the
  crypto 2nd-venue (~48-66 pd) estimate — **it is that plus a genuine instrument/contract abstraction
  the platform has never had.**

---

## 4. Gateway / venue work (`blackheart-exchange-gateway`)

- Today the gateway fronts **Binance** (`binanceService.js`, `binanceFuturesService.js`) and
  **Tokocrypto** (`tokocryptoService.js`, ~60% template). Both are **crypto, HMAC-query-signed, USDT**.
  The venue-onboarding contract (`MULTI_EXCHANGE_ADD_A_VENUE.md` step 2, and the memory contract:
  "HMAC-SHA256 over query string, `X-MBX-APIKEY`, `BTCUSDT` concat, spot MARKET only, USDT pairs")
  **does not transfer to a stock/FX/futures broker.**
- A non-crypto broker (e.g. Interactive Brokers, Alpaca for US equities, OANDA for FX) needs a **new
  gateway service** with that broker's auth (often OAuth/token, not HMAC), order model (equity shares /
  FX units / futures contracts), and market-hours handling. This is a **new service, not a copy of
  `tokocryptoService.js`** — the copy-template convenience the crypto scope relied on is gone.
- **Data-feed vs trade-venue separation still helps:** as the 2nd-exchange scope established, the data
  plane and trade venue are decoupled (`data exchange ≠ trade exchange`). Phase 1 uses a *free daily
  data feed* (Stooq) and *no trade venue at all* — so the gateway work is **entirely Phase 2**, not a
  Phase 1 blocker.

**Gateway/venue effort: Phase 1 = 0 (no venue). Phase 2 = a new broker gateway service + JVM
`ExchangeClient` + instrument abstraction — the bulk of the cost.**

---

## 5. Phased plan + person-day estimates

### Phase 1 — RESEARCH-ONLY (validate orthogonality + edge). ~1.5-2.5 person-weeks (7-12 pd)
Cheapest possible way to answer "does a non-crypto sleeve actually break the DSR ceiling?" **before**
any venue commitment.
1. **Ingest:** `sources/stooq.py` (or yahoo) → daily OHLC → `market_data` for the chosen symbol(s)
   (Gold `XAUUSD`/`GLD` primary; add `SPX`/`^GSPC` as the fast warm-up). PIT lag ≥1d. Backfill deep
   history (metals/indices have 20+ yr free). **~3-5 pd.**
2. **JVM metrics fix:** make DSR/Sharpe/CAGR annualization **bars-per-year aware** (252/260 vs 365) —
   the one correctness item that decides whether the verdict is trustworthy. **~1-2 pd.**
3. **Seed + backtest:** `account_strategy` seed for a price-only engine (DCB / trend / momentum) on the
   new symbol at `1d`; run backtests with **broker-realistic fee/slippage overrides** on the request.
   Compute the sleeve's standalone edge AND its **correlation with the DCB-1d crypto book** (the whole
   point — verify |corr| is genuinely low, OOS, not just full-sample). **~2-4 pd.**
4. **Verdict:** does adding the non-crypto sleeve **raise combined-book DSR** under the portfolio-
   admission gate (`SCOPE_2026-07-15_portfolio_ensemble_framework.md`)? Write the research paper.
   **~0.5-1 pd.**

**Deliverable:** a defensible yes/no on whether a non-crypto daily sleeve breaks the corr-sync wall,
with a measured combined-DSR lift — for the cost of a data source and a metrics fix. **No venue, no
live money, no instrument abstraction.**

### Phase 2 — LIVE EXECUTION VENUE (only if Phase 1 validates). ~6-12 person-weeks (30-60 pd)
Bigger than the crypto 2nd-venue (~48-66 pd was for a *Binance-family HMAC/USDT* venue that shared our
contract). A non-crypto broker adds a **genuine instrument/contract abstraction** on top:
1. New broker gateway service (broker auth, order model, market-hours). **~2-3 wk.**
2. JVM `ExchangeClient` impl + `instrument_spec`/`fee_schedule` rows + contract-spec abstraction
   (multiplier, settlement, session calendar, no-funding). Wire S2 (live sizing from `instrument_spec`)
   + S3 (fees from `fee_schedule`) which the crypto scope deferred. **~2-4 wk.**
3. Live-order safety: fill/error mapper, market-hours guard (reject orders outside session),
   idempotency, testnet matrix. **~1-2 wk.**

### Phase 3 — RISK-PARITY ADMISSION. ~1-2 pd (mostly reuse)
Admit the live non-crypto sleeve into the `PortfolioAllocationService` risk-parity book from
`SCOPE_2026-07-15_live_riskparity_book_build.md` — its low correlation lets the book run more gross for
the same drawdown. This is the payoff and it reuses the allocation layer already scoped there.

---

## 6. Honest caveats

- **Execution gap is real and is the dominant cost.** Binance cannot execute a real non-crypto
  instrument; live requires a new equity/FX/futures broker + an instrument abstraction the platform has
  never built. **The √(N/(N−1)) Sharpe lift is a *portfolio-theory* fact; capturing it live is a
  multi-week venue project.** Do not conflate "validated in research" with "deployable."
- **Capital-gated, structurally.** Live book is ~$191 (memory: `project_dcb_pooled_book_cert`). A
  risk-parity book across 3+ sleeves at ~$191 is symbolic; a *fourth, non-crypto* sleeve on a *separate
  broker* with its own minimums (equity/futures often need far more than $20/slot) is not fundable now.
  This is a "build the machine, it pays as capital grows" move — same posture as the risk-parity scope.
- **Calendar/market-hours complexity is a genuine non-crypto novelty** — but it is *contained*: the
  backtest bar loop is gap-tolerant already; the real work is (a) bars-per-year-aware annualization and
  (b) cross-series date-alignment/ffill policy. Neither is large; both are must-do for a trustworthy
  verdict.
- **S&P orthogonality is regime-dependent and weakest in the tail** (V181 comment: crypto-equity corr
  strengthened post-2020, converges in risk-off). It lifts *average* Sharpe but "everything correlates
  in a crash" (echoed in the risk-parity scope). **Gold is the better orthogonality bet** precisely
  because its driver (real rates / safe-haven / USD) is not BTC's risk-on driver.
- **Is Phase-1 research validation worth doing before any venue commitment? YES — unambiguously.**
  It is the cheapest experiment that can either (a) justify the multi-week venue investment with a
  measured combined-DSR lift, or (b) kill it early if the "orthogonal" instrument turns out to have no
  standalone edge or converges with BTC OOS. It reuses the FRED/`SP500` stepping stone the platform
  already built, needs no new venue, no live capital, and no instrument abstraction. **Recommend: do
  Phase 1 with Gold (primary) + S&P (warm-up), gate Phase 2 on its verdict.**

---

## Grounding — files read for this scope

- `C:/Project/CLAUDE.md` — workspace map, topology, deploy model.
- `C:/Users/rifki/.claude/projects/C--Project/memory/project_second_exchange_scoping_2026-06-20.md`
  (~48-66 pd first crypto venue; no `instrument_spec` abstraction; multi-exchange scaffolding built+dark).
- `.../memory/project_arbitrage_family_scoping_2026-06-21.md` (breadth via uncorrelated bets = the binding constraint; IR ≈ IC × √breadth).
- `blackheart-ingest/src/blackheart_ingest/sources/fred.py` — `SP500`/`NASDAQCOM` daily already ingested, PIT lag=1d; the non-crypto-daily stepping stone.
- `blackheart-ingest/CLAUDE.md` — sources write to `macro_raw`+`feature_values`; JVM is the sole `market_data` writer.
- `blackheart-trading-engine/src/main/resources/db/flyway/V1__baseline.sql:11` — `market_data` schema (VARCHAR(10) symbol; crypto microstructure cols NOT NULL).
- `.../db/flyway/V181__fred_inflation_liquidity_equity_features.sql` — S&P/NASDAQ feed `feature_values` as CONTEXT not tradeable OHLC; vol uses `annualize_factor=252`.
- `blackheart-trading-engine/.../service/exchange/SymbolFilterService.java` — Binance-only lot/tick/precision, hardcoded map + `exchangeInfo` fallback.
- `.../service/backtest/BacktestService.java:37-39,127` — global `DEFAULT_FEE_RATE=0.0004`/`DEFAULT_SLIPPAGE_RATE=0.0005`, request-overridable; bar-count cap.
- `.../service/backtest/BacktestTradeExecutorService.java:239-259` — bar loop is index-based + already gap-tolerant (`gappedThroughStopLoss`).
- `.../service/live/LiveTradingDecisionExecutorService.java:779,844` — OPEN rejects non-`BNC` exchanges.
- `.../service/exchange/ExchangeClient.java` + `docs/MULTI_EXCHANGE_ADD_A_VENUE.md` — dark multi-exchange SPI (spot/MARKET/USDT/HMAC only; does not transfer to a non-crypto broker).
- `blackheart-exchange-gateway/src/services/{binanceService,tokocryptoService}.js` — HMAC-query-signed USDT spot; no non-crypto broker template.
- `C:/Project/research/SCOPE_2026-07-15_live_riskparity_book_build.md` + `..._portfolio_ensemble_framework.md` — the DCB-1d(DSR 0.27)+carry endgame + portfolio-admission gate this feeds.
