# IDX Platform — build plan

**Status:** ready to execute. Implements spec `docs/superpowers/specs/2026-09-12-idx-data-platform-design.md`
(v2, §12 architecture: bronze → silver → gold; operator-in-the-loop execution). Written 2026-09-12.

Each task lists the repo, the files it creates or touches, how it is verified, and an estimate.
Tasks inside a phase are ordered; phases 1b, 2, 3 can overlap once phase 1 has a passer.
Total ≈ 5 working weeks to a paper-trading loop; ≈ 1 week to the go/no-go verdict. No Claude API spend — nightly analysis is manual in Claude chat (phase 3).

## Operator inputs (needed once, not blocking phase 0)

| Item | Needed by | Why |
|---|---|---|
| Current positions (code, lots, avg price), cash, broker + fee % | phase 4 | seed the position book (`research/idx_book.py set …`) |
| ~15 min each trading night in Claude chat | phase 3 | manual analysis of the nightly pack (no API spend) |
| ~30 GB free disk | phase 0 | dump restore ≈ 20 GB + bronze |
| Go/no-go decision after the phase-1 report | phase 1b+ | everything after the screen is conditional |

---

## Phase 0 — Data plane (2–3 days) — **DONE 2026-09-12**

> Delivered: `trading_db` restored locally (serial pg_restore, Timescale 2.27.0); schema `idx` (23 tables, own migration
> history); bronze archive (3,495 responses); day-dump backfill 2020-01-02→2026-09-11 = 1,610 days, 1,360,091 rows, 989 codes
> incl. 27 delisted/unlisted; 216 corporate actions (BBCA 1:5 exact); `idx.bar` on the IDX reference-price basis;
> `market_data` 1,502,779 `.JK` rows from 2001 (43 Yahoo-spliced names) — all 43 splices continuous; scheduler as Windows task
> "Blackheart IDX scheduler"; `/equities/ops` page + `/idx/*` routes; forced-failure alert and replay determinism verified.
> Found: IDX opens before 2025 exist only for LQ45 (see spec §12d).

**Done when:** `idx_daily` runs on its own schedule, `idx_bar` holds 2020+ for every stock that ever
traded (delisted included), `market_data` has `<CODE>.JK` rows on a split-only basis 2001–today, an
alert row appears (and shows in the app) if no bar has landed by 18:00 WIB, and `idx replay` rebuilds
silver from bronze.

### 0.1 Restore `trading_db` locally
- Repo: workspace (`C:/Project`). Files: `docker-compose.override.yml` (already exists — postgres uses
  `pgdata_local`, no host port; add host port `5433:5432` with `!reset` on the base `ports`, per the local-stack memo).
- Steps: `docker compose up -d postgres` (image `timescale/timescaledb-ha:pg16`, PGDATA
  `/home/postgres/pgdata/data`) → `pg_restore -j 4 --no-owner -d trading_db C:\blackheart-backups\trading_db_2026-08-10_200002Z.dump`
  (keep the Timescale image: the dump contains hypertables; *no new* hypertables are created for `idx`).
- Verify: `SELECT count(*) FROM market_data WHERE interval='1d'`; `SELECT version FROM flyway_schema_history ORDER BY installed_rank DESC LIMIT 1` = 213;
  `portfolio_book` has EQ7/EQ6 rows.
- Estimate: 0.5 day (restore time dominates).

### 0.2 `idx` schema + migrations (owned by the ingest worker)
- Repo: `blackheart-ingest`. Files: `src/blackheart_ingest/idx/migrations/0001_schema.sql … 000N`,
  `src/blackheart_ingest/idx/migrate.py` (applies files in order, records in `idx.schema_history(version, sha256, applied_at)`, refuses on checksum drift).
- Tables (all in schema `idx`): `bronze_index`, `listing`, `listing_snapshot`, `daily_summary`, `bar`,
  `corporate_action`, `dividend`, `announcement`, `event`, `news_article`, `financial_report`,
  `financial_fact`, `fundamental`, `valuation_daily`, `sentiment_score`, `sentiment_daily`,
  `company_alias`, `ingest_run`. Keys/columns per spec §4 + §12 (`bar` carries `source`, `basis='split_only'`, `open_missing`).
  Indexes: `(code, trade_date)` btree everywhere; `bronze_index(endpoint, key, fetched_at)`.
- Roles: `GRANT USAGE ON SCHEMA idx TO blackheart_research, blackheart_equity; GRANT SELECT ON ALL TABLES …` (research JVM and equity service read only).
- Verify: `python -m blackheart_ingest.idx.cli migrate` twice → second run is a no-op; `pytest tests/idx/test_migrate.py`.
- Estimate: 0.5 day.

### 0.3 `IdxClient` + bronze archive
- Files: `idx/client.py` (cookie jar, browser headers, backoff 5→80 s, circuit breaker after 5 consecutive 403/5xx → pause 15 min,
  daily request budget, response-field fingerprint per endpoint stored in `bronze_index.fingerprint`, drift → warning),
  `idx/bronze.py` (write `data/idx/bronze/<endpoint>/<key>/<fetched_at>.json.gz`, sha256, index row; `read_latest(endpoint, key)`).
  Port the fetch logic from `research/idx_primary_loader.py`.
- Settings: `INGEST_IDX_BRONZE_DIR`, `INGEST_IDX_RPS=1.0`, `INGEST_IDX_DAILY_BUDGET=3000`.
- Verify: `pytest tests/idx/test_client.py` with recorded fixtures (403 page, 200 JSON, schema-drift sample); manual: fetch one day-dump, confirm the gz + index row.
- Estimate: 0.5 day.

### 0.4 Jobs: `universe`, `daily`, `index` (+ ETL from bronze)
- Files: `idx/jobs/universe.py` (Daftar Saham → `listing` upsert + `listing_snapshot`; diff → listings/delistings/board moves),
  `idx/jobs/daily.py` (`GetStockSummary?date=` → `daily_summary`; weekend/phantom/chain filters and `Previous`-reset detection
  ported from the loader → `corporate_action`; `bar` upsert with split factors back-applied; `open_missing` flag),
  `idx/jobs/index.py` (`GetIndexSummary` → `bar` rows for `^JKSE`, `^JKLQ45`, IDX30, sector indices — verify field names on first run),
  `idx/etl.py` (pure functions bronze-row → silver-rows; every job = fetch→bronze→etl→upsert).
- Cross-check: weekly `GetTradingInfoSS` per code vs `bar`; close disagreement > 0.5 % → `ingest_run.warnings`.
- Verify: unit tests on the ETL with the known defects (2021-05-22 Saturday, COVID open=0, BBCA split 2021-10-13 → factor 0.200137, ANTM placeholders);
  run `daily --date 2026-09-11` and compare 963 rows against `research-scratch/idx-primary/*.csv` (must match exactly).
- Estimate: 1 day.

### 0.5 Backfill 2020-01-02 → today via day-dumps (delisted names included)
- Command: `idx backfill --from 2020-01-02 --to today` (1,610 calls at 1 rps ≈ 30 min; resumable by date; holidays return 0 rows and are recorded).
- Verify: `SELECT count(DISTINCT code) FROM idx.daily_summary` > 962 (delisted names appear); every 2026-09-11 row equals the per-code pull; no `HISTORY_GAP` > 20 days for any code between its first and last trade.
- Estimate: 0.5 day incl. checks.

### 0.6 Yahoo cache on the split-only basis + `market_data` publish
- Files: `research/idx_ohlc_loader.py` — use Yahoo `close` (split-only) instead of `adjclose/close` scaling; keep cleaning rules; write `basis=split_only` in the manifest.
  `idx/publish.py` — `publish_market_data()`: for each code, 2001→2019 rows from the Yahoo cache re-based so the last Yahoo close before 2020-01-02 equals the IDX split-only close on that day (ratio applied to the whole Yahoo segment), 2020+ rows from `bar`; open NULL → close (flag stays in `bar`); upsert `(symbol='<CODE>.JK', interval='1d')` ON CONFLICT DO UPDATE. `publish_feature_values()` stub for phase 1b.
- Verify: splice check — `close(2019-12-30 Yahoo re-based) / close(2020-01-02 IDX)` within the day's real return for every code (no jump > ARA band); BBCA 2021-10-12 → 10-13 continuity.
- Estimate: 0.5 day.

### 0.7 Scheduler, run log, alerts (in-app)
- Files: `idx/scheduler.py` (APScheduler; `universe` 16:15, `daily` 16:30 with retries every 15 min to 20:00, `index` 16:35, `publish` after `daily` success, weekly cross-check Sun 10:00),
  `idx/alerts.py` (writes `idx.alert(id, ts, severity, job, message, acknowledged_at)`: job failure, circuit breaker open, "no bar by 18:00 WIB", fingerprint drift), `ingest_run` rows for every job,
  `idx/cli.py` (`migrate | universe | daily | index | backfill | publish | replay | run-scheduler`), `pyproject.toml` extra `idx = ["apscheduler>=3.10", "openpyxl", "feedparser", "pypdf"]`.
- Routes on the served ingest app (`workers/server.py`): `GET /idx/ops` (last bar date, today's runs, open alerts), `POST /idx/alerts/{id}/ack`.
- Deploy locally: `pythonw -m blackheart_ingest.idx.cli run-scheduler` as a Windows scheduled task (or NSSM service); log to `logs/idx/`.
- Verify: force a failure (bad date) → alert row + visible in `GET /idx/ops`; `idx replay --from-bronze --job daily --date 2026-09-11` reproduces identical silver rows.
- Estimate: 0.5 day.

### 0.8 Minimal ops page in the app
- Repo: `blackridge-frontend` (branch `feat/equities-section`). Files: `src/app/equities/ops/page.tsx`, `src/lib/api/idxOps.ts`, Next rewrite `/idx/:path*` → `INTERNAL_INGEST_URL/idx/:path*` (same pattern as the existing `/equity` rewrite), hook `useIdxOps` (poll 60 s).
- Shows: last bar date vs today, today's job runs with status, open alerts with acknowledge; browser notification (Web Notifications API, opt-in) when a new alert appears. IBM Plex + theme tokens, no hardcoded hex (project rule).
- Verify: `tsc` + vitest for the hook; page renders the forced-failure alert from 0.7.
- Estimate: 0.5 day.

---

## Phase 1 — Alpha screen, go/no-go (2–3 days)

**Done when:** `research/IDX_SCREEN_<date>.md` states, per symbol and for the universe, Sharpe/PF/maxDD/DSR at honest N with next-open fills and 50 bps, and a one-line verdict: passers (if any) or "no edge".

### 1.1 `idx_screen.py`
- Files: `research/idx_screen.py` — reads `idx.bar` (one query for the universe) and the Yahoo split-only cache for pre-2020; **next-open fill** variant of `sleeve()` (entry/exit at the next bar's open; ⚠ IDX records opens before 2025 only for LQ45 — gap-fill from Yahoo opens where available, else next-close, and report the fill basis per result); cost 50 bps round-trip; Donchian grid as `equity_screen.py`; DSR with the true trial count; 5-fold WF; corr vs the existing book (BTC/XAUUSD/ZC=F/JPY=X via the existing `db_ohlc`/`yf_ohlc`).
- Universe: `listing.board IN ('Utama','Pengembangan')`, median 60-day `value` ≥ Rp 5 bn, **delisted names included** for the window they traded (from `daily_summary`), Pemantauan Khusus and Akselerasi excluded.
- Verify: reproduce `equity_screen.py` numbers on SPY/AAPL when run with close fills and 5 bps (regression); run on IDX; report generated.
- Estimate: 1.5 days.

### 1.2 `idx_dividend` (total-return sanity)
- Files: `idx/jobs/announce.py` (shared with 1b.1) + `idx/etl_dividend.py` — parse cash-dividend titles ("Pembagian Dividen Tunai …", "Jadwal Pembagian Dividen …") for ex-date, record date, amount/share → `dividend`. Metadata-only, no PDF parsing.
- Use: report the price-return vs total-return gap for the top-10 yield names in the screen report; if a verdict flips, say so.
- Estimate: 0.5 day.

### 1.3 Screen report + verdict
- Files: `research/IDX_SCREEN_<date>.md` (same shape as `EQUITY_SCREEN_2026-07-18.md`: per-symbol table, best cells, honest-N DSR, survivorship note, dividend gap, WF folds).
- Gate: only a passer at DSR ≥ 0.90 (honest N) with 5/5 WF folds justifies phases 2–4 *as trading work*; otherwise phases 2–3 continue only as thesis-support tooling if the operator wants them.
- Estimate: 0.5 day.

---

## Phase 1b — Cheap overlays (3–4 days) — **DONE 2026-09-12** (run despite no certified passer, as different hypotheses)

> Delivered: `announce` job (152,350 disclosures 2023-07+, 30-kind title classifier, `--reclassify`), `idx.event` (55,113),
> `idx.feature_daily` (1.36 M rows; PIT-tested), `feature_values` mirror path, `research/idx_overlays.py`,
> report `research/IDX_OVERLAYS_2026-09-12.md`. Verdict: no certifiable overlay; foreign flow works only in large caps and
> only as a low-turnover entry filter on the trend rule (WF OOS 0.61 vs 0.37; DSR@96 0.10); events carry nothing;
> dividend "drift" = un-adjusted ex-date drop. Archive depth: disclosures 2023-07-03 onward only.

### 1b.1 Announcement metadata backfill 2020+ and `event` table
- Files: `idx/jobs/announce.py` (`GetAnnouncement` by month window per code — bronze, `announcement` upsert; rule table `Form_Id`/title → `event.kind` ∈ {dividend, rights, buyback, insider_tx, ownership_5pct, uma, suspension, public_expose, material_info, other}); no text extraction yet.
- Verify: sample 50 announcements by hand; kind precision ≥ 0.9 on the sample.
- Estimate: 1 day.

### 1b.2 Daily overlay features → `feature_values`
- Files: `idx/features.py` — PIT features per (trade_date, code): `foreign_net_20d`, `foreign_net_5d`, `value_60d_median`, `mcap_bucket`, `event_insider_buy_30d`, `event_uma_10d`, `event_dividend_ann_30d`; registered in `feature_registry`; `publish_feature_values()` writes them.
- Verify: no feature uses data with `published_at` > trade-date 15:49 WIB (unit test with a document published at 16:10).
- Estimate: 1 day.

### 1b.3 Overlay test
- Files: `research/idx_overlays.py` — take the phase-1 sleeve, apply each overlay as a filter/scaler, WF, DSR/PSR ≥ 0.90; report `research/IDX_OVERLAYS_<date>.md`.
- Estimate: 1–1.5 days.

---

## Phase 2 — Fundamentals + value/quality test — **DONE 2026-09-12**

> Delivered: `fin discover/download/parse` (20,383 reports catalogued; 2,311 audited + 1,961 quarterlies parsed, 0 failures;
> USD filers converted; both IDX header styles), `idx.financial_fact`/`idx.fundamental` PIT, `dividends` (Yahoo, validated vs
> primary cash flow), `idx card`, `research/idx_value_quality.py`, report `research/IDX_VALUE_QUALITY_2026-09-12.md`.
> Result (rev. 2, after the FY2023 scaling + USD-rate parser fixes): composite value within a loose quality gate +122 % (CAGR 16 %,
> 6/6 years positive, DSR@12 0.62, PSR 0.98) vs EW universe −28 %; strict gate trails (+55–60 %) → evidence-supported discretion, not certification.

### 2.1 Report discovery via bulk listing
- Files: `idx/jobs/fin.py` — probe `GetFinancialReport?year=&periode=&kodeEmiten=` with empty `kodeEmiten` + `indexFrom/pageSize` paging; if unsupported, fall back to per-code but only for the liquid ~150; `financial_report` rows with `published_at = File_Modified`, attachments JSON; download `FinancialStatement-*.xlsx` + `instance.zip` to bronze.
- Estimate: 1 day.

### 2.2 Workbook parser + taxonomy map
- Files: `idx/fin_parse.py` (openpyxl; sheets by taxonomy code → `financial_fact` long rows: concept, context, period, value, unit), `idx/taxonomy_map.csv` (industry × concept → metric), `idx/fin_derive.sql` (views → `fundamental`: revenue, gross/operating/net profit, assets, liabilities, equity, cash, debt, shares_out, EPS, BVPS, ROE, ROA, DER, margins, YoY; **as-reported, PIT = first-published value per (code, period)**).
- Verify: 10 companies (incl. 2 banks) checked against their PDFs; XBRL instance cross-check on 3.
- Estimate: 2.5 days.

### 2.3 `valuation_daily`
- Files: `idx/fin_valuation.sql` — market cap (listed_shares × close), PE ttm, PB, dividend yield ttm (from `dividend`), only using fundamentals with `published_at ≤ trade_date`.
- Estimate: 0.5 day.

### 2.4 Thesis card (CLI first, frontend later)
- Files: `idx/cli.py card <CODE>` — 8-quarter trend, valuation vs its own history, last 10 events, foreign-flow 20d, insider tx. Frontend page in `blackridge-frontend` deferred until the equity section is merged.
- Estimate: 1 day.

---

## Re-scope after phase 2 (2026-09-12): the book is an **annual value/quality portfolio**, not a daily trend ticket

The phase-2 verdict changes what phases 3–4 must deliver. The operating rule is: loose gate (audited profit > 0, ROE ≥ 5 %)
→ composite rank (E/P, B/P, DY) → top fifth, equal weight, min 10 names else cash, rebalance each May, ≥ Rp 5 bn/day; the
operator applies strict-quality judgment per name on the thesis card. So the machine's job is the **candidate list + monitoring**,
and the operator's ritual is weekly (nightly only around rebalance). Steps, in order:

| # | Step | Status |
|---|---|---|
| 1 | **Candidate list, systematic** — `idx candidates [--as-of D]` → `idx.candidate` (rank, selected, E/P, E/P ttm, P/B, DY, ROE, D/E, strict-gate fails, TTM warnings, foreign flow) + markdown; `GET /idx/candidates`; scheduler jobs to keep it current (daily chain → features → candidates; `announce_recent` 20:30; `fundamentals` 21:00 Mon–Fri / Sat full; `dividends` monthly). `idx/metrics.py` is the shared PIT evaluator (card, candidates, pack). | **DONE 2026-09-12** — reproduces the research May-2026 list (24 names) |
| 2 | **Quarterlies + TTM** — 2024–2026 TW1–TW3 workbooks for the universe (1,328 more downloaded, 3,288 quarterlies parsed); TTM = FY + YTD − prior YTD (from the report's own comparative); card shows the trailing-12m P/E and the 8-quarter table; thesis-break warnings (`ttm_loss`, `latest_quarter_ytd_loss`, `ytd_profit_down_>50%`). | **DONE 2026-09-12** |
| 3 | **Weekly/nightly pack for manual Claude chat** — `idx pack`: pinned prompt + market + candidate table + compact section per name (selected + next 10 + watchlist) with disclosures since the previous pack → `idx.nightly_pack` + `research-scratch/idx-pack/<date>/pack.md`; `idx pack-import` validates the JSON answer and records it (`idx.sentiment_score`, `answer_json`); routes for the app. 3.1/3.2 (news, disclosure text) become enrichments of the pack later. Found and fixed two workbook-scaling bugs on the way (FY2023 vintage full-amount values; USD filers without a rate) → full re-parse, phase-2 numbers re-checked. | **DONE 2026-09-12** |
| 4 | **Position book + monitoring** — `idx.book/fill/position/book_mark/book_nav` (migration 0007), `idx book fill|show|mark|check|paper-seed|import`, average cost with fees, net dividends on ex-date, splits as fills, NAV series; holding alerts (`job='book:<name>'`, deduplicated) for disclosures / rule break / drawdown ≥ 25 % / liquidity; marked + checked daily after candidates; routes for the app. Paper book seeded from the corrected May-2026 list (24 names, Rp 1 bn, next-open fills): +5.3 % to 2026-09-11 (EW check +5.65 % before fees/lot rounding). | **DONE 2026-09-12** |
| 5 | **Rebalance ticket (phase 4, re-scoped)** — `idx/ticket.py` + migration 0008: `rebalance` (selected list equal-weight vs held → sells/trims/adds/new entrants, whole lots, tick-snapped limits inside the auto-rejection band, cash-capped) and `exits` (rule break on the newest report / pack says sell); lines flagged with rank, strict fails, warnings, pack stance/veto; fill capture per line → `idx.fill` + re-mark, partial/skip with reason; May 1–10 reminder alert; routes for the app. Dry run on the paper book: 10 sells / 12 buys to move from the May list to today's (cancelled — the paper book rebalances in May). Trading JVM not involved. | **DONE 2026-09-12** |
| 6 | **App pages** (`blackridge-frontend`, branch `feat/equities-section`, uncommitted) — `/equities/candidates`, `/equities/card/[code]` (markdown card via `MarkdownLite`), `/equities/book` (live/paper, NAV chart, positions, holding alerts, fill + settings forms), `/equities/ticket` (build rebalance/exits, per-line fill/skip, issue/close), `/equities/pack` (copy pack, import answer, watchlist, answer ledger); `lib/api/idxDesk.ts` + `hooks/useIdxDesk.ts` + types; `GET /idx/card/{code}` added to the worker. tsc/eslint clean, mapper tests, every page and proxy route answered 200 on a dev server. | **DONE 2026-09-12** |
| 7 | **Paper track from now** — the May-2026 list is the seventh observation. | running as book `paper` since 2026-05-05 |

Operator inputs still owed: broker + fee %, whether the book is top-fifth (~15–25 names) or a fixed 10–12, positions/cash.

## Phase 3 — Nightly analysis loop, manual Claude chat (≈ 4 days; no API spend) — see re-scope above

### 3.1 News accumulation (no scoring)
- Files: `idx/jobs/news.py` (feedparser over Kontan, Bisnis.com, CNBC Indonesia, Investor.id, Kompas Money, Detik Finance, Antara, Google News RSS per alias; dedupe by URL + text hash; alias resolution via `company_alias`), `idx/aliases_seed.csv` (top 100 by hand).
- Estimate: 1 day. Starts the clock on the news window.

### 3.2 Disclosure text (lazy)
- Files: `idx/text_extract.py` — pypdf on material `event.kind` only; empty result → mark `needs_ocr`; OCR (Tesseract) only for the top-150 liquid names.
- Estimate: 1 day.

### 3.3 Nightly pack + answer import (replaces batch scoring)
- Files: `idx/nightly.py` (`idx nightly-pack --date D` → `idx.nightly_pack(date, pack_md, pack_json)` + file copy under `research-scratch/idx-nightly/D/`: per ticket/watchlist name — last 20 bars with value + foreign net, corporate actions, disclosures since last pack with kind + link, news headlines since last pack, fundamentals snapshot when available, position + ticket line; ≈ 2–3k tokens per name), `idx/prompts/nightly_v1.md` (pinned chat prompt: document-only, no outcome speculation, answer only in the JSON block), `idx/score_import.py` (validates the answer against the schema, writes `sentiment_score` with `model='claude-chat-manual'`, `prompt_version`, `scored_at=now`; `veto` → calls `blackheart-equity` `POST /api/equity/orders/{id}/skip` with the rationale so the equity service stays the only writer of `equity_*`).
- Routes (ingest app): `GET /idx/nightly/{date}` (pack md + json + pinned prompt), `POST /idx/nightly/{date}/answer` (import), `GET/PUT /idx/watchlist`.
- App page `/equities/nightly` (`blackridge-frontend`): "Copy pack" button (prompt + pack in one clipboard write), answer textarea → import → shows the stored scores and vetoes; watchlist editor.
- Watchlist: `idx.watchlist` (edited in the app) ∪ names on today's ticket ∪ current positions.
- PIT: scores exist only from `scored_at`; `sentiment_daily` (decay 0.85/day) is derived from them; nothing is back-dated.
- Verify: round-trip test — generate a pack for 2026-09-11, hand-write an answer, import, confirm rows and a veto on one line.
- Estimate: 1.5 days.

### 3.4 Veto ledger and review
- Files: `research/idx_veto_review.py` — monthly: ticket-as-issued vs as-executed P&L; tells the operator whether the nightly vetoes added or cost money. Sentiment is not a backtestable overlay without a funded backfill; this review is the honest substitute.
- Estimate: 0.5 day.

---

## Phase 4 — Execution v1, operator-in-the-loop (≈ 1 week)

### 4.1 `blackheart-equity` venue + routing
- Files: `venue/Venues.java` (`IDX`: IDR, non-fractional, lot 100, side-aware fee 0.15/0.25 %, tick table Rp 1/2/5/10/25, ARA/ARB table — values verified against IDX Peraturan II-A at build time), `venue/VenueProfile.java` (fee model takes side; `snapTick(price)`, `clampBand(prev, price)`), `gateway/BookAuthorityGateway.java` (add `"IDX"`), new `client/BrokerRouter.java` (exchange → `BrokerClient`), `config/EquityBookProperties` → per-venue book code, currency, min-notional, cron.
- Flyway (own history): `V3__idx_manual_execution.sql` — `equity_order.currency`, status `PENDING_MANUAL`, `equity_fill.source` (`manual|import`).
- Tests: `VenueProfileTest` (lot/tick/band), `ReconciliationServiceTest` (IDR, lots), gateway filter.
- Estimate: 1.5 days.

### 4.2 `ManualTicketBroker` + daily ticket (in-app)
- Files: `client/manual/ManualTicketBroker.java` (`getPositions()` from `equity_position`; `submitOrder()` writes `PENDING_MANUAL`, returns a ticket id; never calls a broker), `service/TicketService.java` (builds the day's ticket: code, side, lots, limit price = next-open estimate snapped to tick and clamped inside ARA/ARB, reason), `controller/EquityTicketController.java` (`GET /api/equity/ticket/{date}`, `POST /api/equity/orders/{id}/skip` with reason → `SKIPPED_BY_OPERATOR`).
- App page `/equities/ticket` (`blackridge-frontend`): today's lines with reason, per-line fill form (lots, price, fee), skip/reduce with reason, trade-confirmation upload; browser notification when a new ticket is published.
- Scheduler: reconcile is triggered by an `ingest_run(job='publish', status='ok')` row for today (poll every 5 min 16:30–20:00) — not a fixed time.
- Holiday guard: skip when `max(trade_date) FROM idx.bar` ≠ today.
- Estimate: 1.5 days.

### 4.3 Fill capture
- Files: `controller/EquityFillController.java` (`POST /api/equity/fills` — code, side, lots, price, date, fee; `POST /api/equity/fills/import` multipart), `service/FillImportService.java` (parser for the operator's broker trade-confirmation export — format decided once the broker is named), `research/idx_book.py import` (one-shot: seed `equity_fill`/`equity_position` from the CSV ledger). UI lives on the ticket page (4.2) and the existing `/equities/positions`.
- Rules: unfilled `PENDING_MANUAL` orders expire at the next reconcile and are re-issued as a new `(book, date, symbol)` row; partial fills reduce the delta.
- Estimate: 1.5 days.

### 4.4 Paper track
- Book Authority: seed an `IDX_*` book (CANDIDATE → PAPER) from the phase-1 sleeve; `blackheart-equity` `paper` profile with hypothetical fills at next open (+ 50 bps) recorded as `equity_fill.source='paper'`; ≥ 60 trading days before any LIVE flip.
- Estimate: 0.5 day setup, then calendar time.

---

## Phase 5 — Execution v2 (gated)
Only after a broker API/DMA agreement: `client/idx/<Broker>Client.java` implementing `BrokerClient`; everything else unchanged.

## Order of work (critical path)
0.1 → 0.2 → 0.3 → 0.4 → 0.5 → 0.6 → 0.7 → 1.1 → 1.2 → 1.3 → **verdict** → {1b, 2, 3 in parallel} → 4.1 → 4.2 → 4.3 → 4.4.

## Risks tracked during the build
- Cloudflare tightening (mitigation: bronze replay, circuit breaker, Yahoo cross-check; last resort `curl_cffi` impersonation).
- `GetIndexSummary` / bulk financial listing shapes unverified — first task of 0.4 and 2.1 is to record a sample into bronze and adjust.
- Dump restore on the Timescale image (PGDATA path) — follow the local-stack memo exactly.
- Scanned PDFs share unknown — 3.2 measures it before any OCR spend.
