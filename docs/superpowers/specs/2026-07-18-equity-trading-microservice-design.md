# Blueprint: Equity-Trading Microservice (`blackheart-equity`)

**Date:** 2026-07-18
**Status:** DESIGN / BLUEPRINT (approved architecture; one open decision — target market/venue)
**Author:** brainstorming session with operator
**Goal:** Trade equities with the existing certified trend-engine approach (donchian/DCB + cross-asset
risk-parity book), as a **standalone Spring Boot microservice** owning the **full live lifecycle incl. broker
execution**, surfaced in the one Blackridge frontend.

---

## 1. Decisions locked (this session)

| # | Decision | Choice |
|---|---|---|
| 1 | Product | **Trade stocks** with the trend engine (extend the risk-parity book to equities, like gold) — not a forecast-only product, not stocks-as-crypto-features. |
| 2 | Form factor | **Standalone microservice**, own repo/container/schema, in the one integrated frontend. |
| 3 | Scope | **Full lifecycle incl. broker execution** (data → decision → orders → fills → PnL). |
| 4 | Engine relationship | **Approach B (tightened):** reuse the shared **certified brain** (research pipeline + DSR/V102 gates); do NOT reimplement strategy logic. |
| 5 | Robustness pattern | **One strategy/cert brain + one book/allocation authority + thin isolated venue executors.** Executors reach a `target_position`; they never decide strategy or size. |
| 6 | Stack | **Spring Boot / Java 21**, mirroring `blackheart-trading-engine` structure/conventions. |
| 7 | Broker | **Alpaca** (US, commission-free, REST/WS, native paper, accepts Indonesia, $1 min). IBKR = later multi-market path. |
| 8 | **Target market** | **RESOLVED (2026-07-18): US (NYSE/Nasdaq)** — see §8. Wins on all 3 operator criteria (fees, API-broker-accessible-from-Indonesia, free-data completeness). |
| 9 | Trading cadence | **Daily/swing only (2026-07-19)** — EOD decisions, multi-day holds. No scalping/day-trading: PDT rule <$25k, SIP data cost, HFT competition, and the platform's own intraday-falsification evidence (cost floor killed all 54 intraday cells in crypto). Intraday = documented tripwire, not scope. |

## 2. Why this shape (rejected alternatives)

- **A — fully standalone, reimplement the engine in Python:** rejected. Max isolation but duplicates the
  *certified* engine + the entire statistical gate suite → two drifting sources of truth, full re-validation.
  The DCB_POOL look-ahead disaster shows how subtle strategy bugs hide.
- **C — extract a shared "quant core" library first:** correct long-term, but a platform-wide refactor of a
  live trading system before any equity value. Too risky as step 1; we evolve *toward* it.
- **B (chosen), tightened:** the equity service is genuinely separate (own repo/container/schema, owns its
  market's mechanics) but reuses the one certified brain and reads allocation from one book authority. Only
  option where the risk-parity book becomes a true **cross-asset** book (crypto + gold + equities), which is
  the "many uncorrelated signals" endgame.

## 3. Components

**① Shared certification brain — exists, generalized.** Research JVM + orchestrator pipeline, market-aware.
Equity OHLCV → shared `market_data`; donchian sweeps run through the **unchanged** DSR≥0.90 / V102 gates →
**certified equity sleeve config**. No strategy logic reimplemented anywhere. *Reuses the `bc67e1b` non-crypto
enablement branch (direction override + audit NULL-denorm) + the `gold_ohlc_loader.py` pattern.*

**② Book / Allocation Authority — new, small; the missing piece.** Single owner of the cross-asset book.
Daily: latest bars → ask the shared brain for each certified sleeve's **desired signal** (donchian fired?
long/flat) → compute **vol-parity target positions** across all sleeves (crypto + gold + equity) → emit targets.
Lives as a **portfolio module in the trading JVM** beside the existing `AssetAllocationController` + nightly
rebalance cron (already Spring/Java); extractable to a standalone `blackheart-portfolio` service later.

**③ `blackheart-equity` — the new Spring Boot microservice.** Dumb executor: consume target equity positions,
diff vs current holdings, work orders to reach target. **No strategy logic** — only equity *mechanics*: trading
calendar/hours, order types, PDT rule, T+1 settlement, fractional shares, corporate actions, halts/LULD. Owns
`equity_*` schema (positions/orders/fills/PnL).

**④ Equity data ingest — new, small.** Equity OHLCV (daily first) → shared `market_data`, split/dividend
adjusted, calendar-aware. Owned by ③ as a scheduled Spring component (service owns its data). Yahoo for research
backfill; live provider per §8.

**⑤ Broker connectivity — folded into ③, multi-venue by design (decision 2026-07-18: NO separate service per
market).** A venue is a parameter, not a domain: SGX/Bursa differ from US in values (calendar, T+2, board lots,
fee model, currency), not in kind — one service, venue as a first-class dimension. Concretely:
- **`BrokerClient` interface** + adapters: `client/alpaca/` (US, phase 1) and `client/ibkr/` (SGX + Bursa +
  later Dubai/Europe — one adapter covers the whole multi-market future). REST + WS fills, mirroring the JVM's
  exchange-client wrapping. No separate Node gateway.
- **`VenueProfile` per exchange:** trading calendar/hours, settlement (T+1 US / T+2 SGX+Bursa), board-lot size
  (100 SGX/Bursa), tick sizes, currency (USD/SGD/MYR, IBKR auto-FX), and a **per-venue fee model** — SGX
  (0.08% min S$2.50 + clearing) and Bursa (brokerage + 0.03% clearing + ~0.15% stamp) are NOT free like US;
  research backtests must charge real per-venue costs, not flat 8 bps.
- **Schema/contract:** `exchange` + `currency` columns in `equity_*`; `target_position` gains a venue field.
The asset-class boundary (equity vs live crypto) is the service split that matters and is already made; markets
within the class share code paths, so per-market services would triplicate scaffold without adding safety.

**⑥ Frontend — new "Equities" section** in Blackridge: cross-asset book allocation, equity positions/orders/
fills/PnL, per-sleeve cert status. Reuses research + portfolio-rebalance components; IBM Plex, token-driven theme.

## 4. The contract that makes it robust

```
target_position { sleeve_id, symbol, side, target_weight, target_notional, as_of_bar }
```
Emitted by ② (the only place that decides *how much*); consumed by the JVM executor (crypto) or ③ (equity).
Executors only *reach* the target. Removes both the two-brains risk and the orphaned-book risk.

## 5. Control flow (end to end)

```
INGEST  equity OHLCV ─► market_data (shared, market-aware)
RESEARCH orchestrator → research JVM → DSR/V102 gates → certified equity sleeve config
ADMIT   operator admits sleeve (portfolio-admission gate: orthogonality + book-DSR lift)
────────────────────────  live, once per session  ────────────────────────
② Book Authority: bars → shared-brain desired signals → vol-parity TARGET POSITIONS
        ├─ crypto targets ─► JVM executor ─► exchange-gateway ─► Binance   (exists)
        └─ equity targets ─► ③ blackheart-equity ─► broker ─► venue        (new)
FILLS  ③ → equity_* schema → ② reconciles book → ⑥ frontend
```

**Isolation:** ③ failing can't touch crypto; stale ② → executors hold last target (no wild orders); live crypto
JVM path untouched except the annualization generalization (parity-preserving, pin-tested at 365).

## 6. Spring Boot structure (mirror `blackheart-trading-engine`)

- **Java 21 / Spring Boot**, own git repo + container + `equity_*` Postgres schema; VPS Compose service.
- **Packages** `id.co.blackheart.equity.*`: `controller/ service/ engine/ client/ model/ repository/ dto/ config/
  converter/ exception/ metrics/ util/`. `engine/` = execution mechanics ONLY (never strategy).
- **Profiles** `paper` (default) / `live`, mirroring the JVM live/research split.
- **Flyway** `src/main/resources/db/flyway/` (live dir; ignore dead `db/migration`), `V1__equity_schema.sql`+.
- **Build/deploy identical:** `build.gradle` + `gradlew`, `Dockerfile` COPY-jar, GH Actions → GHCR →
  VPS `docker compose up -d`, auto-rollback tag.
- **Own `CLAUDE.md` + `docs/agent-context/{COMMANDS,ARCHITECTURE,SCHEMA,STRATEGIES}.md`**; add a row to the root
  workspace map (`C:/Project/CLAUDE.md`).

## 7. Parity-preserving shared edits (guarded)

1. **Bars-per-year annualization (252 vs 365)** keyed off the symbol's market calendar, in the JVM statistics +
   orchestrator DSR — with **pin tests** so every crypto path stays byte-identical at 365.
2. `market_data` equity symbols + crypto-only CHECK relaxation — **partly shipped** via the gold/`bc67e1b` branch.

## 8. Target market / venue — RESOLVED: US (NYSE/Nasdaq) via Alpaca

Operator asked (2026-07-18) to pick the market with **lowest transaction fees + best API-automation broker
accessible from Indonesia + most complete free data**, across US / Singapore / Malaysia / Dubai / Europe.
Web-researched; **US wins on all three axes** (see comparison table below). Decision: **US market, Alpaca broker.**

| Market | Transaction fees | API broker for an Indonesian | Free data |
|---|---|---|---|
| **🇺🇸 US** | **$0 commission** (Alpaca; IBKR Lite $0) | **Alpaca** — 195+ countries incl. Indonesia, REST/WS, native paper, $1 min | **Best** — Alpaca free RT + 7yr history; Yahoo/Stooq/AlphaVantage |
| 🇸🇬 SGX | SGX+clearing fees; broker min ~S$0.99–25 | IBKR / Tiger / moomoo | Mostly delayed; limited free API |
| 🇲🇾 Bursa | brokerage % + 0.03% clearing + 0.1% stamp | IBKR; thin local API for foreigners | Third-party only |
| 🇦🇪 DFM/ADX | ~0.2–0.3% round-trip | IBKR only (added DFM/ADX Dec 2025) | Limited free |
| 🇪🇺 Europe | + stamp duties (UK 0.5%, FR/IT FTT) | IBKR / Saxo | Limited free |

- **Broker = Alpaca** (US): commission-free, REST/WebSocket, native **paper** (fits paper-first rollout), accepts
  Indonesian residents, $1 min → maps directly onto the `client/alpaca/` package. `client/<broker>/` stays swappable.
- **Multi-market later = IBKR** (one account → US + Dubai + Europe + SGX). Its API (gateway process) is more painful
  and its data is paid, so US/Alpaca first; IBKR is the expansion path, not step 1.
- **Caveats (non-blocking):** US hours 21:30–04:00 WIB — fine, daily/EOD strategy runs automatically, operator need
  not be awake. PDT rule if account <$25k (paper-first + daily cadence largely sidesteps it).

⚠️**Honest orthogonality caveat (unchanged):** in our own multi-sleeve screen, **broad SP500 was DROPPED for 0.30
correlation with crypto** (risk-on beta). "Stocks" are NOT automatically orthogonal like gold/corn. Equity sleeves
must pass the SAME per-instrument orthogonality screen — favour US **sectors/factors/single-names or trend-timed
exposure** over the broad risk-on index. A research finding to respect, not a blocker.

**Sources:** [Alpaca International](https://alpaca.markets/international), [Alpaca Data API](https://alpaca.markets/data),
[BrokerChooser – API brokers 2026](https://investingintheweb.com/brokers/best-api-brokers/),
[IBKR commissions](https://www.interactivebrokers.com/en/pricing/commissions-stocks.php),
[IBKR adds UAE DFM/ADX](https://goodmoneyguide.com/uae/interactive-brokers-adds-uae-equities-investing-trading/),
[SingSaver SG brokerage fees 2026](https://www.singsaver.com.sg/investment/blog/singapore-brokerage-account-fees-comparison),
[Bursa Malaysia transaction costs](https://www.bursamalaysia.com/trade/trading_resources/equities/transaction_costs),
[Yahoo Finance API guide](https://publicapis.io/blog/yahoo-finance-api-guide).

## 8b. Data architecture & ingestion (designed 2026-07-18, operator ask)

**Same spine as crypto — proven by gold:** equity 1d bars → shared `market_data`; features (incl. donchian) →
`feature_store`; research JVM/orchestrator/gates consume unchanged; loader = `gold_ohlc_loader.py` pattern.
No schema change needed for the research plane.

**Four real differences vs crypto:**
1. **Ingest rhythm:** one scheduled EOD batch pull (not 24/7 WS streaming) — cron-style job, no stream infra.
2. **Calendar:** weekend/holiday bars don't exist — market-calendar registry; features treat gaps as legitimate.
3. **Corporate actions (the big one):** research uses back-adjusted OHLCV; live uses raw prices + position
   adjustment on split day; `equity_corporate_action` table in the service schema.
4. **Survivorship:** Yahoo = today's listings only → **v1 universe = ETFs** (sectors/factors/bonds/commodities,
   no survivorship problem); single-name screens later need a survivorship-free paid source (Sharadar/Norgate).

**Schema split (clarified 2026-07-18, operator question "own DB or shared?"):** BOTH, by data type —
- **Shared plane (existing `trading_db`):** `market_data` + `feature_store` hold equity bars/features alongside
  crypto/gold. Required, not convenience: the certification brain reads one place, and orthogonality/book
  measurement is cross-asset (needs BTC × gold × equity joinable in one DB).
- **Service-owned:** `equity_*` tables — `equity_instrument` (ticker/exchange/currency/lot registry),
  `equity_corporate_action`, `equity_order`, `equity_fill`, `equity_position`, `equity_pnl_snapshot` — owned
  exclusively by `blackheart-equity`, **own Flyway history** (`flyway_schema_history_equity`, V1 onward, in the
  equity repo; justified deviation from the "trading-engine owns all migrations" rule because the namespace is
  disjoint). No other service writes these; the equity service writes nothing else except `market_data` inserts.
- **Physically ONE Postgres instance** (existing `blackheart-postgres`): a second server doubles ops surface
  (backups/monitoring/standby/disk alerts) for zero benefit at ~300k daily-bar rows. Escape hatch: the cleanly
  owned `equity_*` namespace can lift to its own instance later via dump/restore + connstring change.
Daily volumes tiny → no hypertable.

**One-instance guardrails (BINDING — operator design review 2026-07-19):**
1. **Noisy-neighbor containment:** equity service connects as its OWN DB role with a connection limit and
   `statement_timeout` (pattern: orchestrator's dedicated `blackheart_research` role). It shares the instance
   with the LIVE trading JVM — a runaway query must be killable by policy, not by ops heroics.
2. **No cross-boundary FKs, ever:** `equity_*` never references `trades`/`accounts`/etc. and vice versa.
   Cross-domain reads go through service APIs or the explicitly-shared tables (`market_data`, `feature_store`,
   `target_position`) only. Convenience joins across ownership boundaries are rejected in review.
3. **Split tripwires (any one → move `equity_*` to its own instance):** (a) equity goes intraday
   (minute-bars × hundreds of symbols); (b) equity queries sustain a meaningful share of DB CPU in
   postgres-exporter; (c) a venue/regulatory requirement demands data isolation.
Rationale: database-per-service orthodoxy optimizes for org-scale team decoupling; this platform's binding
constraint is ops burden (one operator + agents). The design keeps the exit cheap instead of paying for it now.

**Flow/microstructure data availability (researched 2026-07-18):**
| Product | US | SGX | Bursa |
|---|---|---|---|
| Broker summary (per-broker) | **Does not exist** (closest: FINRA dark-pool venue volume, 2-wk lag) | No | No true per-broker |
| Foreign/institutional flow | Slow proxies only: 13F (qtrly+45d), short interest (biweekly) | **Weekly** inst/retail by sector | **Weekly** foreign/local-inst/retail; since **2026-04-06 trade-level retail/inst nominee split** |
| Microstructure | Richest, but Alpaca free = **IEX (~2% of volume)**; SIP $99/mo | Delayed/paid | Paid/vendor |

Takeaways: (1) Phase 1 needs NONE of this — trend book = OHLCV only; flow = later research feature surface
(like crypto funding/OI/LSR). (2) ⚠️Crypto positioning-flow factors were FALSIFIED OOS (TOP-TRADER-LSR-FADE) —
flow is a hypothesis, never a given. (3) ★Bursa's new trade-level retail/inst split = differentiated, under-mined
surface the US lacks — register as phase-6 hypothesis; weekly cadence suits a daily/weekly book.

**Phase-1 concrete build (on operator go) — screens ALL THREE markets at once (operator ask 2026-07-18);
execution still built only for what passes:**
(i) v1 universe = ~25-30 liquid US ETFs (sector SPDRs, factors, TLT/IEF, GLD/USO/DBA, EEM/EFA) + few mega-caps,
**PLUS SGX candidates** (`^STI`/`ES3.SI` + ~10-15 liquid large caps: DBS/OCBC/UOB, Singtel, Wilmar, SGX, big
REITs — `.SI` suffix) **PLUS Bursa candidates** (`^KLSE` + ~10-15 large caps: Maybank/CIMB/Public Bank, Tenaga,
IHH, **plantations KLK/IOI/SD-Guthrie** — `.KL` suffix). ★Plantation hypothesis: corn passed the sleeve screen
(Sharpe 0.72, orthogonal) → palm-oil-linked Bursa plantations are the most plausible orthogonal equity
candidates (commodity-driven, not risk-on beta). Indices themselves expected weak (KLCI range-bound, risk-on
beta like SP500).
(ii) `equity_ohlc_loader` backfills ~15-25y adjusted daily → prod `market_data` (Yahoo; validate gaps/ticks —
SGX/Bursa quality a notch below US; large-cap-only = survivorship caveat noted).
(iii) feature RECOMPUTE_RANGE; (iv) offline orthogonality+edge screen (`multi_sleeve_*` pipeline) with
**honest per-venue costs** — US $0 commission (slippage only), SGX ~0.10-0.15%/side, Bursa ~0.2-0.35%/side
(brokerage+0.03% clearing+0.15% stamp) — the cost bar IS the filter; local-currency returns for screening,
SGD/MYR FX overlay flagged for live phase. No new service, no migration, no broker account needed.

## 9. Phased rollout (each phase independently valuable)

1. **Data + research** — equity ingest → `market_data`; certify first equity sleeve through market-aware gates.
   Reuses the gold path; ~days.
2. **Book authority** — `target_position` contract + cross-asset vol-parity allocation; crypto executor reads
   targets (no behavior change).
3. **`blackheart-equity` skeleton** — Spring scaffold, `equity_*` schema, broker **paper** integration,
   reach-target loop; paper-trades the certified sleeve.
4. **Frontend Equities section.**
5. **Go-live gate** — flip `paper → live` only after a certified sleeve + paper track record clear the
   portfolio-admission bar.
6. **SGX / Bursa Malaysia expansion (operator request 2026-07-18)** — certify-before-build discipline:
   (a) research-screen SGX/Bursa sleeves OFFLINE first (Yahoo `.SI`/`.KL` daily data, same orthogonality +
   edge + book-DSR pipeline, per-venue fee model — near-zero cost); (b) ONLY if a sleeve passes, build the
   `client/ibkr/` adapter + SGX/Bursa `VenueProfile`s → paper → admission gate. Broker reality for an
   Indonesian: **IBKR is the only single-account path to both SGX and Bursa** (Bursa added Aug 2024, MYR
   auto-FX; moomoo rejects Indonesian residents; Tiger = SGX only). Honest expectation: STI/KLCI are equity
   risk-on beta (SP500 was dropped at 0.30 crypto-corr) and KLCI is famously range-bound — the trend screen
   may legitimately find nothing; that outcome is cheap and fine.

## 10. Testing

Unit (execution mechanics, calendar/PDT/settlement edge cases), broker contract tests vs paper, a **backtest-
parity test** (equity service's reach-target replay vs the research JVM's certified backtest must match), pin
tests on the annualization generalization.

## 11. Constraints & ties to existing platform state

- Reuses: the gold sleeve precedent, the `bc67e1b` non-crypto research enablement, the 4-sleeve risk-parity book
  (`2765ba66`), `AssetAllocationController` + nightly rebalance cron, the research orchestrator gates.
- Capital/venue are operator-gated (as with carry). Paper-first means capital is not a blocker to build.
- No push/deploy without operator ask (workspace rule).

---

**Next step after the §8 market decision:** finalize the broker/calendar/data-provider specifics into the doc,
user-review, then invoke `writing-plans` to produce the phased implementation plan.
