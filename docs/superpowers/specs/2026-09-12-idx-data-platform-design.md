# IDX Data Platform — design (prices · fundamentals · sentiment · execution)

**Status:** PLAN v2, operator review. Written 2026-09-12; §12 review the same day amends decisions 1, 2, 3 and the phase order. Builds on the equity blueprint
(`2026-07-18-equity-trading-microservice-design.md`) — IDX becomes a venue of `blackheart-equity`,
not a new service. This doc covers the **data plane** that has to exist before any IDX sleeve can be
certified, plus the execution path that IDX's broker reality allows.

## 0. Thesis in one paragraph

Trade IDX with the platform's certified trend engine, where a *primary-source* data plane
(idx.co.id, not Yahoo) feeds three layers: **prices + flow** (daily Ringkasan Saham incl. foreign
buy/sell), **fundamentals** (IDX's standardized quarterly financial statements), and **sentiment**
(IDX disclosures first, Indonesian financial news second, scored by Claude with point-in-time
discipline). Fundamentals and sentiment are *conditioning* inputs to the trend sleeve and *thesis
support* for the operator — they are hypotheses that must clear the same DSR/PSR gates as everything
else, never a second brain. Execution starts operator-in-the-loop (IDX has no retail order API) and
graduates to a broker API/DMA only if one is secured.

## 1. What already exists (verified 2026-09-12)

| Asset | State |
|---|---|
| `research/idx_primary_loader.py` | Pulls Daftar Saham (962 listed stocks) + per-stock daily history from idx.co.id; raw JSON kept; phantom/weekend rows filtered; corporate-action factors from IDX's `Previous`. Full-market pull running to `research-scratch/idx-primary/`. |
| `research/idx_ohlc_loader.py` | Yahoo `.JK` 25y history, 43 names, cleaned (`research-scratch/idx/`). Only free source for pre-2020. |
| IDX endpoints confirmed | `GetSecuritiesStock` (universe), `GetTradingInfoSS` (per-stock daily, **2020-01-02 onward only**), `GetStockSummary?date=` (whole market per day), `GetFinancialReport` (quarterly xlsx + XBRL zip per emiten), `GetAnnouncement` (Keterbukaan Informasi per emiten, PDFs). All Cloudflare-fronted; browser headers + backoff work. |
| Platform | Blackheart stack DOWN on VPS since 2026-08-11 (deliberate). `trading_db` exists as local dump `C:\blackheart-backups\trading_db_2026-08-10_200002Z.dump` (4.8G). `blackheart-equity` service built + deployed inert (US/Alpaca only). `blackheart-ingest` = Python ingest service (`sources/` modules, `/pull/{source}`, PIT guards, writes `macro_raw` + `feature_values`). |

## 2. Decisions (locked unless operator overrides)

1. **One database, the platform's `trading_db`**, restored locally from the 08-10 dump (plain
   Postgres is enough — see §12). IDX bars land in `market_data` (symbol `BBCA.JK`, interval `1d`, same
   convention as the SGX `.SI` / Bursa `.KL` rows) so the certified research pipeline (screen
   scripts, research JVM, DSR gates, Book Authority) works unchanged. Rich primary data lives in a
   new **`idx_*` namespace**. *Rejected:* a standalone `idx_db` — cheaper to start, but forks the
   research plane and re-creates the two-brains trap.
2. ~~Schema owner = trading JVM Flyway (V214)~~ **AMENDED (§12):** a separate Postgres schema
   `idx` in the same database with its **own migration history**, owned by the ingest worker —
   the same pattern `blackheart-equity` uses for `equity_*`. The JVM only reads published rows.
3. **Ingest lives in `blackheart-ingest`** as an `idx/` package reusing its DB/PIT/logging
   helpers — **but self-scheduled** (§12): the existing `/pull` routes are triggered by the trading
   JVM, which must not be a dependency. No new service.
4. **Execution lives in `blackheart-equity`** as `Venues.IDX` + an IDX `BrokerClient`. v1 broker =
   `ManualTicketBroker` (operator executes in the broker app, fills recorded back). *Rejected:*
   browser automation of a broker app (ToS + fragility), unofficial Stockbit APIs.
5. ~~Sentiment scored by Claude via the Batches API~~ **AMENDED 2026-09-12 (operator: no API budget):**
   sentiment/thesis analysis is done **manually in Claude chat each night**. The system produces a
   *nightly pack* (`idx nightly-pack`) the operator pastes in; Claude answers in a fixed JSON contract;
   the operator pastes it back in the app's Nightly page (→ `idx score-import`) → `sentiment_score` rows with
   `model='claude-chat-manual'`, `prompt_version`, `scored_at`. Same schema, same PIT rules, zero API
   cost. Consequence: no historical backfill of scores → sentiment is **thesis support and a recorded
   veto layer**, not a backtestable overlay, unless the operator later funds a backfill.
6. **Every timestamp is point-in-time.** Fundamentals are usable from IDX's `File_Modified`
   (publication time), disclosures from `TglPengumuman`, news from publisher time (fallback: fetch
   time). Features are computed with `published_at <= bar close`. This is what makes the later
   backtests honest.
7. **Universe for research = Utama + Pengembangan boards**, liquidity-filtered (median 60-day daily
   value ≥ Rp 5 bn), **excluding Pemantauan Khusus** (full call auction — different microstructure)
   and Akselerasi. All 962 are still ingested (survivorship-free history; delistings tracked).

## 3. Sources

### 3a. Prices, flow, corporate actions — primary
| Endpoint | Cadence | Notes |
|---|---|---|
| `StockData/GetSecuritiesStock` | daily snapshot | Universe incl. board + listed shares; diffing snapshots yields listings/delistings/board moves. |
| `TradingSummary/GetStockSummary?date=YYYYMMDD` | daily 16:30 WIB | One call = whole market for that day (963 rows). Primary daily job. |
| `ListedCompany/GetTradingInfoSS?code=` | backfill / repair | Per-stock 2020+ history in one call. Already pulled. |
| `TradingSummary/GetIndexSummary?date=` | daily | IHSG, LQ45, IDX30, sector indices (positive-control / beta hedging). *Verify field shape in build.* |

Known feed defects (already handled in the loader, keep in the ingest): phantom weekend rows
(2021-05-22 market-wide), `OpenPrice=FirstTrade=0` for 2020-03-13→2020-09-04 (no pre-opening session
during COVID — store NULL), `Previous` reset = corporate action (BBCA 1:5 on 2021-10-13 → factor
0.2001 with listed shares ×5; BBRI rights 2021-09-08 → 0.974). Cash dividends do **not** reset
`Previous` → adjusted series is split/rights-adjusted only; dividend history comes from disclosures.

### 3b. Fundamentals — primary
`ListedCompany/GetFinancialReport?year=&periode=tw1|tw2|tw3|audit&kodeEmiten=` → attachments per
report: **`FinancialStatement-YYYY-P-CODE.xlsx`** (IDX standardized taxonomy workbook — the parse
target), `instance.zip` (XBRL instance — verification / fallback), inline XBRL, PDFs. Depth: at least
2020+; the endpoint takes a `year` param — probe how far back during build (XBRL mandate ≈ 2015).
Taxonomy differs by industry (general / banks / insurance / securities / financing) — the mapping
table `idx_taxonomy_map` normalizes ~40 concepts onto one metric set.

Secondary (for the pre-2020 gap, later): IDX "Ringkasan Performa Perusahaan Tercatat" PDFs carry
5-year highlights + ratios per company.

### 3c. Sentiment / events — tiered
| Tier | Source | Why | Cadence |
|---|---|---|---|
| 1 | IDX Keterbukaan Informasi (`GetAnnouncement`, per emiten, `Form_Id` typed, PDFs) | Official, timestamped, structured: dividends, corporate actions, material info, public expose, **insider/≥5 % ownership changes** | hourly |
| 1 | IDX exchange notices: UMA (unusual market activity), suspensions, special-monitoring entries | Attention/risk events; UMA is a documented mean-reversion signal to test | hourly |
| 1 | `foreign_buy/foreign_sell` (already in 3a) | Primary flow, daily, every stock | daily |
| 2 | Indonesian financial news RSS: Kontan, Bisnis.com (market), CNBC Indonesia (market), Investor.id, Kompas Money, Detik Finance, Antara Ekonomi + Google News RSS per company name (`hl=id&gl=ID`) | Volume + narrative; Indonesian-language | every 30 min |
| 3 (deferred) | Stockbit stream, X/Twitter | Retail chatter; unofficial/paid APIs, ToS risk | — |

Entity resolution: `idx_company_alias` (code ↔ legal name, short name, common abbreviations:
"BCA"→BBCA, "Bank Mandiri"→BMRI, "Telkom"→TLKM, "Astra"→ASII…), seeded from Daftar Saham names and
curated by hand for the top ~100; unresolved mentions are kept (not dropped) with `code=NULL`.

## 4. Schema — `idx_*` namespace (Flyway V214, trading-engine)

| Table | Key | Purpose |
|---|---|---|
| `idx_listing` | `code` | Current universe row: name, listing_date, board, listed_shares, sector/subsector, status, first_seen, last_seen |
| `idx_listing_snapshot` | `(snapshot_date, code)` | Daily Daftar Saham diff → listings, delistings, board moves (survivorship) |
| `idx_daily_summary` | `(trade_date, code)` · hypertable | Every primary field: previous, open (NULL-able), first_trade, high, low, close, change, volume, value, frequency, bid/offer (+vol), listed/tradeable shares, foreign_buy/sell, non-regular vol/value/freq, remarks, `fetched_at` |
| `idx_corporate_action` | `(code, ex_date, kind)` | factor, listed_shares before/after, source (`previous_reset` / `announcement`), announcement_id |
| `idx_financial_report` | `(code, fiscal_year, period, report_type)` | file list (JSONB), `published_at` = File_Modified, parse_status, checksum |
| `idx_financial_fact` | `(report_id, concept, context_ref)` | Long-format facts from the xlsx/XBRL: value, unit, decimals, period_start/end |
| `idx_fundamental` | `(code, period_end)` | Normalized metrics: revenue, gross/operating/net profit, total assets, liabilities, equity, cash, total debt, shares_out, EPS, BVPS, ROE, ROA, DER, net margin, YoY growth, `published_at` |
| `idx_valuation_daily` | `(trade_date, code)` | Joins prices × latest *published* fundamentals: market cap (listed_shares × close), PE (ttm), PB, dividend yield (ttm from disclosures) |
| `idx_announcement` | `id2` | code, published_at, title, form_id, kind (mapped), attachments JSONB, extracted_text, text_hash |
| `idx_news_article` | `id`, `url` UNIQUE | source, published_at, fetched_at, title, body, lang, resolved codes[] |
| `idx_sentiment_score` | `(doc_type, doc_id, code)` | model, prompt_version, stance (−2..+2), materiality (0..3), event_type, horizon_days, confidence, rationale, scored_at |
| `idx_sentiment_daily` | `(trade_date, code)` | PIT aggregates: n_docs, mean/materiality-weighted stance, exp-decayed score, n_negative_material, last_insider_buy_days… → mirrored into `feature_values` via `feature_registry` |
| `idx_company_alias` | `(code, alias)` | entity resolution |
| `idx_ingest_run` | `id` | job, window, rows_in/out, rejected_pit, error, started/finished |
| `market_data` (existing) | `(symbol, interval, start_time)` | `<CODE>.JK` 1d bars, split-adjusted OHLC (open NULL → carried as close for the 2020 gap, flagged) — the research contract |

Sizing: ~1.55 M daily rows (962 × 1,610) today, +963/day; facts ≈ 5 M over 6 years; news a few
hundred/day. Trivial for Timescale on a PC.

## 5. Jobs (all WIB; `blackheart-ingest` sources unless noted)

| Job | When | Reads → writes |
|---|---|---|
| `idx_universe` | 16:15 daily | Daftar Saham → `idx_listing`, `idx_listing_snapshot` |
| `idx_daily` | 16:30 daily (IDX publishes ~16:00; retry to 20:00) | `GetStockSummary?date=` → `idx_daily_summary`, corporate-action detection → `idx_corporate_action`, `market_data` upsert; cross-check vs per-stock endpoint weekly |
| `idx_index_daily` | 16:30 daily | `GetIndexSummary` → `market_data` (`^JKSE`-style screen-only rows or `idx_index_daily`) |
| `idx_announcements` | hourly | `GetAnnouncement` since cursor → `idx_announcement`; PDF text extraction (pypdf) |
| `idx_news` | every 30 min | RSS → `idx_news_article` (dedupe by URL + text hash; alias resolution) |
| `idx_sentiment` | 20:00 nightly | unscored docs → Claude **Batches** (strict JSON schema, prompt v1) → `idx_sentiment_score` → `idx_sentiment_daily` → `feature_values` |
| `idx_financials` | weekly + daily during filing windows (Apr, Jul–Aug, Oct–Nov, Mar) | `GetFinancialReport` scan → download xlsx/zip → parse → `idx_financial_fact` → `idx_fundamental` → `idx_valuation_daily` |
| backfill (one-off) | now | per-stock 2020+ (done), announcements 2020+ (endpoint has dateFrom/dateTo), financial reports 2020+ (and older if served), news: RSS is recent-only → sentiment history starts at ingest start (honest) |

PIT rules reuse `shared/pit_guards.py`: reject future `published_at`, reject backfill outside window,
never forward-fill fundamentals past the next report's `published_at`.

## 6. Sentiment scoring contract (manual-chat edition — see decision 5)

**Nightly loop (≈ 15 min of operator time):**
1. After the bar lands, `idx nightly-pack --date D` writes `research-scratch/idx-nightly/D/pack.md`
   (and `pack.json`): for each name on the ticket + watchlist — last 20 bars (close, value, foreign
   net), corporate actions, disclosures since the last pack (title, `Form_Id`, kind, link), news
   headlines since the last pack, fundamentals snapshot when phase 2 exists, current position and
   the ticket line. Sized to ≈ 2–3k tokens per name; a digest header for the whole list.
2. Operator pastes `pack.md` into Claude chat with the pinned prompt (`idx/prompts/nightly_v1.md`:
   document-only, no outcome speculation, answer only in the JSON block).
3. Claude returns one JSON block: `[{code, event_type, stance, materiality, horizon_days,
   confidence, rationale, veto: null|"skip"|"reduce"}]`.
4. Operator pastes it into `research-scratch/idx-nightly/D/answer.json`; `idx score-import --date D`
   validates against the schema and writes `sentiment_score` (+ `equity_order.status=SKIPPED_BY_OPERATOR`
   with the rationale when `veto` is set). Vetoes are measured later: ticket-as-issued vs ticket-as-executed.

The same pack works in a Claude Code session (which can read the file and write the import itself);
that is the cheaper path if the operator prefers it. Structured fields below are unchanged.

- Input: one document (announcement text or article) + resolved ticker list + a compact company card
  (name, sector, last close, market cap bucket).
- Output (strict JSON, `output_config.format`): `[{code, event_type ∈ {earnings, dividend,
  corporate_action, insider_transaction, ownership_change, regulatory, uma_or_suspension,
  management, guidance, macro_sector, other}, stance −2..+2, materiality 0..3, horizon_days,
  confidence 0..1, rationale ≤ 30 words}]`.
- Prompt is versioned (`prompt_version`), cached system prefix (company-agnostic instructions
  first, volatile document last), batched nightly. Re-scoring a version = new rows, old kept.
- Cost: **$0 API**. (For reference if a backfill is ever funded: ~50k documents ≈ $300 one-off at
  Opus 5 batch prices.)
- Evaluation before use: a 300-doc hand-labelled set (operator + agent) → agreement ≥ 0.75 on
  stance sign, and the feature must add OOS lift to the trend sleeve (WF, DSR/PSR ≥ 0.90) before it
  conditions any trade. Crypto flow/sentiment factors were falsified OOS on this platform — same
  bar applies.

## 7. Fundamentals contract

- Parse the IDX standardized workbook: sheets by taxonomy code (general info, statement of financial
  position, profit or loss, cash flows). Map per-industry concepts to the metric set via
  `idx_taxonomy_map` (banks: interest income / CASA / NPL instead of revenue / COGS).
- Store every raw fact; derive metrics in SQL views so a mapping fix re-derives without re-parsing.
- `published_at` = `File_Modified` (IDX upload time). A metric is visible to research only from then.
- Thesis-support surface (frontend, later): per-ticker card — 8-quarter trend of revenue/net profit/
  ROE/DER, valuation vs 5-year band, last 10 disclosures with stance, foreign-flow 20-day sum,
  insider transactions.

## 8. Execution path (blackheart-equity)

**Venue mechanics for `Venues.IDX`**: IDR, board lot 100, no fractional, **long-only** (retail short
selling is restricted), T+2, sessions 09:00–11:30 / 13:30–15:49 WIB (Fri 09:00–11:30 / 14:00–15:49),
pre-opening + closing auction, tiered tick sizes (Rp 1 / 2 / 5 / 10 / 25 by price band), auto-reject
bands (ARA/ARB) by price tier — encode as a rule table and **verify current values against IDX
Peraturan II-A at build time**. Fees ≈ 0.15–0.19 % buy / 0.25–0.29 % sell (sell includes 0.1 % final
tax; levy ≈ 0.04 %; VAT on commission) → **50 bps round-trip is the screen cost**.

**Order flow v1 — operator-in-the-loop**
1. Book Authority (trading JVM) emits `target_position` rows with `exchange='IDX'`, notional in IDR.
2. `blackheart-equity` reconciles once the day's `idx_daily` has landed, snaps qty to lots, prices
   at next-day open, writes `equity_order(status=PENDING_MANUAL)` and renders the **daily ticket in
   the app** (`/equities/ticket`): code, side, lots, limit price (tick-snapped, inside ARA/ARB),
   reason (sleeve, target, delta). **No Telegram/email (operator decision 2026-09-12): the web app is
   the only interface** — alerts, ticket, fills, nightly pack/answer all live there; an optional
   browser notification when a new ticket or alert appears.
3. Operator places orders in the broker app next morning; records fills on the ticket page (or
   uploads the broker's trade confirmation export there) → `equity_fill` → `equity_position`.
4. Nightly reconciliation vs the operator-confirmed position; mismatch = loud alert, no auto-fix.

**Order flow v2 — broker API/DMA** (only if secured): same `BrokerClient` interface, `IdxBrokerClient`
adapter. Who to ask: IDX member brokers with algo/DMA programs (IDX permits robot trading via a member
that files an electronic-order plan). Candidates to approach in order of tech track record: Indo
Premier (IPOT), Mirae Asset Sekuritas, Phillip Sekuritas, BNI Sekuritas, Stockbit Sekuritas. No
retail order API is publicly documented today — treat every claim as unverified until a contract
exists. IBKR does not offer IDX.

**Code changes** (from the venue-extension review): `Venues.IDX`; `"IDX"` in
`BookAuthorityGateway.EQUITY_EXCHANGES`; `BrokerRouter` (exchange → `BrokerClient`); per-venue
min-notional/currency; per-venue cron (`0 45 9 * * MON-FRI` UTC) + "latest bar == as_of_date" guard
(Lebaran/holidays); side-aware `VenueProfile.feeModel`; tick-snapping + ARA/ARB clamp for limit
orders; `equity_order.currency`. Roughly a few days once the data plane exists.

## 9. Certification path (unchanged platform rules)

Screen (Donchian grid, 50 bps, universe §2.7, 2020+ primary **and** 25y Yahoo for the long window)
→ if passers: orthogonality vs the existing book (BTC/gold/US sleeves) → conditioning hypotheses
(foreign-flow, insider buys, disclosure stance, valuation percentile) tested as *overlays* on the trend
sleeve, WF with DSR/PSR ≥ 0.90 at honest N → frozen sleeve into a Book Authority book (`IDX_*`) →
**paper via operator-in-the-loop with recorded hypothetical fills** ≥ 60 trading days → live small.
Nothing in this doc lowers a gate.

## 10. Phases

| # | Phase | Deliverable | Effort |
|---|---|---|---|
| 0 | Data plane up | Local TimescaleDB restored from dump; V214 `idx_*` applied; full-market primary cache loaded into `idx_daily_summary` + `market_data`; `idx_daily` job live at 16:30 WIB | 1–2 days |
| 1 | Alpha screen | IDX Donchian screen at 50 bps on primary (2020+) + Yahoo (25y, cleaned); liquidity/board filter; report `research/IDX_SCREEN_<date>.md`. **Go/no-go gate for everything below.** | 2–3 days |
| 2 | Fundamentals | `idx_financials` job, taxonomy map, `idx_fundamental` + `idx_valuation_daily`; backfill 2020+ | ~1 week |
| 3 | Events + sentiment | announcements + UMA + news ingest, alias table, Claude batch scoring, PIT daily feature into `feature_values`, 300-doc eval set | 1–2 weeks |
| 4 | Overlay research | test flow / insider / disclosure / valuation overlays on the certified trend sleeve; paper (report) | 1–2 weeks |
| 5 | Execution v1 | `Venues.IDX` + `ManualTicketBroker` + ticket page + fill capture + reconciliation; paper track | ~1 week |
| 6 | Execution v2 | broker API/DMA adapter — gated on a signed broker path | TBD |

## 11. Open items for the operator

1. **DB host** — local PC now (recommended; VPS is repurposed and RAM-tight). Prod later on a
   separate small VPS.
2. **Sentiment model tier** — default Opus 5 batch (~$40/mo); say the word for Haiku.
3. **Social sources** — recommend skipping Stockbit/X scraping (ToS + noise) until Tier 1/2 prove out.
4. **Broker outreach** — business/KYC conversation only the operator can start; nothing in phases
   0–5 blocks on it.
5. **Pre-2020 depth** — accept Yahoo (cleaned) for the long lookback, or buy vendor history.

## 12. Review v2 (2026-09-12) — weaknesses found, and the hardened architecture

Operator asked for a second pass: find the weak points, make it robust, fast, efficient.

### 12a. Weaknesses (ranked by damage)

| # | Weakness | Damage | Fix |
|---|---|---|---|
| 1 | **Survivorship bias in the primary pull.** The per-stock endpoint was fed from *today's* Daftar Saham → stocks delisted 2020–2026 are absent. | 2020+ backtests on primary data are too optimistic. | Backfill with `GetStockSummary?date=` per trading day (1,610 calls ≈ 30 min) — it returns every stock traded that day, delisted ones included. Per-stock data becomes the cross-check. Track delistings in `idx_listing_snapshot`. |
| 2 | **Adjustment basis mismatch at the splice.** Yahoo series = split+dividend adjusted; IDX = split-only. Joined under one `BBCA.JK` symbol → a level jump on 2020-01-02 → fake Donchian breakouts. `market_data` also has `open_price NOT NULL` and no `source`/`basis` column. | Corrupt research bars. | One basis: **split-only**. Yahoo's `close` field is already split-only (verified: BBCA 2021-10-12 close 7,320 = 36,600/5; `adjclose` 6,248 adds dividends) → rebuild the Yahoo cache from `close`. Keep a silver table `idx_bar(code, trade_date, source, basis, o/h/l/c, volume, value, adj_factor, open_missing)`; `market_data` is a *published projection* of it (open NULL → close, flagged in silver). |
| 3 | **Schema in JVM Flyway.** Every table change needs a Java build + JVM redeploy for a Python-owned plane. | Slow iteration, coupling to a stack that is down. | Separate schema `idx` + own migration history (SQL files, applied by the worker). Flyway/ddl-validate never see it. |
| 4 | **Scheduling depends on the JVM.** `blackheart-ingest` pulls are triggered by `MlIngestScheduleRefresher` in the trading JVM. | JVM down = no data. | The `idx` worker owns its schedule (APScheduler/cron), writes `idx_ingest_run`, alerts via Telegram on failure or on "no bar by 18:00 WIB". |
| 5 | **LLM hindsight leakage.** A 2026 model scoring a 2021 disclosure "knows" what happened to the stock. | Sentiment overlays look predictive in backtests and are not. | Document-only prompt (no price/outcome speculation, no ticker history in the card), evaluate stance only on documents **after the model's training cutoff**, use objective event classification (dividend / rights / insider buy / UMA …) for anything earlier. |
| 6 | **Sentiment build order.** News RSS has no archive → the news overlay cannot be researched for a year, yet 1–2 weeks were budgeted to build it. | Wasted effort before any evidence. | Disclosures first (2020+ archive via `dateFrom/dateTo` → backtestable now). News = accumulate-only (fetch + store, no scoring) until the window is long enough. |
| 7 | **Scanned PDFs.** Many Keterbukaan Informasi attachments are image scans; `pypdf` returns nothing; OCR/vision is slow and costly. | Text pipeline stalls. | `JudulPengumuman` + `Form_Id` are structured → classify from metadata first; extract text lazily and only for material form types. |
| 8 | **No dividend data** → total return understated (IDX banks yield 3–5 %/yr). | Screen biased against high-yield names; wrong go/no-go. | `idx_dividend` from cash-dividend announcements (structured titles: "Pembagian Dividen Tunai …", ex-date / record date / amount) before the screen verdict on high-yield names. |
| 9 | **Fundamentals plan naive**: per-stock listing = 23k calls; restatements and taxonomy versions unhandled. | Days of fetching; PIT errors. | Bulk listing per (year, period) with `kodeEmiten=` empty (verify pagination); store as-reported values keyed by (concept, period, `published_at`), PIT uses the first-published value; start with the ~150 liquid names, scale after the mapping is validated against 10 PDFs. |
| 10 | **Execution timing and fill model.** 16:00 publish → 16:30 pull → 16:45 reconcile is a 15-minute margin over a Cloudflare-fronted feed; the screen assumes close fills while reality is next-open (+ ARA/ARB gaps); manual fill entry is error-prone. | Missed tickets, optimistic backtests, drift. | Reconcile is event-driven (after `idx_daily` succeeds; deadline 18:00 — orders are for next morning anyway). Screen and paper use **next-open fills + 50 bps + gap risk**. Fills come from the broker's daily trade confirmation (import parser); manual entry only as fallback. Unfilled ticket → carried to the next ticket (new `(book, date, symbol)` row, so idempotency holds). |
| 11 | **Single origin, unofficial endpoints, Cloudflare.** No replay, no fallback, no drift detection. | Silent outages / silent schema changes. | **Bronze layer**: every response archived immutably (`bronze/<endpoint>/<key>/<fetched_at>.json.gz` + `idx.bronze_index` with sha256) → silver is a deterministic replay of bronze. Circuit breaker on consecutive 403s. Response-field fingerprint per endpoint → alert on drift. Yahoo `.JK` daily as cross-check and gap-fill with `source` recorded; > 0.5 % close disagreement flagged. |
| 12 | **Scope too front-loaded.** 4–5 weeks of fundamentals + sentiment before any edge is shown. | Sunk cost. | Phase 1b "overlays from data already in hand" (foreign flow, `Form_Id` events, market cap from listed shares × close) before any parser is built. |
| 13 | **TimescaleDB is unnecessary** for 1.5 M daily rows; per-symbol `psql` reads in the screen are slow. | Complexity, slow screens. | Plain Postgres, `(code, trade_date)` btree, materialized `idx_bar`; the screen reads one query per batch. |

### 12b. Hardened architecture

```
bronze  (immutable)   data/idx/bronze/<endpoint>/<key>/<fetched_at>.json.gz  + idx.bronze_index
   │  deterministic, replayable ETL (pure functions of bronze)
silver  (schema idx)  idx_listing(_snapshot) · idx_daily_summary · idx_bar · idx_corporate_action ·
                      idx_dividend · idx_announcement · idx_event · idx_news_article ·
                      idx_financial_report/_fact · idx_fundamental · idx_sentiment_score · idx_ingest_run
   │  PIT projections (published_at ≤ bar close)
gold                  idx_feature_daily → feature_values (feature_registry) ;
                      market_data ← published projection of idx_bar (split-only basis, `<CODE>.JK`)
consumers             Python screen (reads idx_bar) · research JVM (reads market_data / feature_values) ·
                      Book Authority → target_position(exchange='IDX') → blackheart-equity Venues.IDX
```

- **Worker** = `blackheart-ingest` package `idx/` with its own CLI (`idx backfill|daily|announce|news|fin|nightly-pack|score-import`),
  APScheduler, `IdxClient` (cookie jar, backoff, circuit breaker, request budget, fingerprint),
  alerts written to `idx.alert` and shown in the app (no Telegram). Every job idempotent and resumable.
- **Interface = `blackridge-frontend`** (branch `feat/equities-section`): `/equities/ops` (data health,
  alerts, last bar date), `/equities/ticket` (today's ticket, fill entry, confirmation upload, veto),
  `/equities/nightly` (copy the pack, paste the answer, import), plus the existing overview/positions.
  Backends: `blackheart-equity` (`/api/equity/*` — orders, fills, positions, skip) and the ingest worker
  (`/idx/*` — ops, nightly pack/answer, watchlist) via same-origin Next rewrites.
- **Daily cost**: 1 whole-market call + ~5 announcement pages + RSS. Backfill: 1,610 day-dumps (~30 min),
  announcements by month window, financials by bulk listing.
- **Research contract unchanged**: `market_data` + `feature_values` — but both are *derived*, never the
  system of record. Rebuild = `idx replay --from bronze`.
- **Sentiment**: disclosures → event classification (objective) + stance (post-cutoff eval only);
  Claude Batches, `claude-opus-5`, strict JSON, versioned prompt; news accumulate-only.

### 12d. Facts established while building phase 0 (2026-09-12)

- **Basis = IDX reference-price adjusted, not strictly split-only.** IDX's `Previous` reset covers splits
  *and* rights/bonus issues (theoretical ex-rights price); cash dividends never. Yahoo's `close` adjusts for
  splits only, and uses its own rights convention (BBRI: 10/11 vs IDX 0.9744). `publish` therefore re-bases
  the Yahoo pre-2020 segment by the median close ratio on the first overlapping days; all 43 splices are
  continuous (flagged re-bases: BBRI 1.072, INCO 0.985, TPIA 0.908 = exactly the rights factors).
- **Opening prices before 2025 exist only for ~45 stocks (LQ45).** Both IDX endpoints agree; from 2025 the
  open is recorded broadly (≈ 75 % of traded names). `idx.bar.open_missing` is honest about it. Phase-1
  "next-open fills" must either restrict to LQ45 for the long window or gap-fill opens from Yahoo (flagged);
  the screen reports which fill basis each result used.
- **Survivorship:** the day-dump backfill yields 989 codes vs 962 in today's Daftar Saham — 27 delisted or
  non-listed classes are in the history.
- **Cloudflare fingerprints TLS:** `httpx`/`requests` receive 403; stdlib `urllib` passes. The client is urllib.
- **TimescaleDB restore must be serial** (`pg_restore -j` breaks the catalog FK order).

### 12c. Phases, re-ordered

| # | Phase | Deliverable | Effort |
|---|---|---|---|
| 0 | Data plane | DB restored; schema `idx` + migrations; bronze; **day-dump backfill 2020+ (delisted included)**; `idx_bar` (split-only; Yahoo re-based from `close`); `market_data` publish; self-scheduled `idx_daily` + alerts; Yahoo cross-check | 2–3 days |
| 1 | Alpha screen — go/no-go | Donchian at 50 bps, **next-open fills**, liquid Utama/Pengembangan universe incl. delisted names; `idx_dividend` for total-return sanity on high-yield names | 2–3 days |
| 1b | Cheap overlays | Foreign-flow, `Form_Id` event flags (announcement metadata backfill 2020+), market-cap buckets — as overlays on the trend sleeve, WF + DSR/PSR ≥ 0.90 | 3–4 days |
| 2 | Fundamentals | Bulk listing, workbook parser for ~150 liquid names, as-reported PIT facts, valuation daily | ~1 week |
| 3 | Sentiment | Disclosure text (lazy OCR) + stance scoring with post-cutoff evaluation; news accumulate-only from day 1 | ~1 week |
| 4 | Execution v1 | `Venues.IDX`, event-driven reconcile, ticket, confirmation import, paper track | ~1 week |
| 5 | Execution v2 | Broker API/DMA — gated | TBD |
