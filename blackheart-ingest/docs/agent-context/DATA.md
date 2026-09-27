# IDX data - client, ETL, schema `idx`, migrations, publish, fundamentals, macro, news, logos

Read when you touch how IDX data gets in (idx.co.id client, Cloudflare, backfill, Yahoo fallback), the schema or a
migration, the `public.market_data` publish, the financial-report workbooks, annual reports, macro series, news, consensus
or logos. Map: [../../CLAUDE.md](../../CLAUDE.md). Job times: [JOBS.md](JOBS.md). CLI verbs and spec paths:
[ARCHITECTURE.md](ARCHITECTURE.md).

Primary-source Indonesian equities (idx.co.id) -> schema **`idx`** in the same `trading_db`; self-scheduled,
**independent of the trading JVM** (phase 0 — 2026-09-12).

## Layers: bronze -> silver -> gold
- **bronze** = every response archived (`INGEST_IDX_BRONZE_DIR/<endpoint>/<key>/<fetched_at>.json.gz` + `idx.bronze_index`)
- -> **silver** = `idx.*` tables via pure ETL (`idx/etl.py`)
- -> **gold** = `public.market_data` rows `<CODE>.JK / 1d` (IDX reference-price basis = splits + rights/bonus via `Previous`
  resets, never cash dividends; `idx/publish.py` re-bases the Yahoo pre-2020 segment onto it).
- Silver/gold are derived; `idx replay` rebuilds them from bronze with no network.

## Schema and migrations
- **Schema:** own migrations `idx/migrations/NNNN_*.sql` + `idx.schema_history` (sha256-checked, never edit an applied file).
  Not Flyway. JVM/equity roles get SELECT only.
- Migration index (each is described in the file named):

| migration | what | detail |
|---|---|---|
| 0007 | position book (`idx/book.py`) | [BOOKS_TICKETS.md](BOOKS_TICKETS.md) |
| 0008 | rebalance ticket (`idx/ticket.py`) | [BOOKS_TICKETS.md](BOOKS_TICKETS.md) |
| 0009 | prior-period comparatives `net_profit_prior` | [STRATEGIES.md](STRATEGIES.md) |
| 0010 + 0011 | strategy catalog (`idx/strategies.py`) | [STRATEGIES.md](STRATEGIES.md) |
| 0012 | book overlays (`idx/overlay.py`) | [STRATEGIES.md](STRATEGIES.md) |
| 0014 | `trend_exit` overlay | [STRATEGIES.md](STRATEGIES.md) |
| 0015 | `idx.app_user` (desk accounts) | [ARCHITECTURE.md](ARCHITECTURE.md) |
| 0016 | cash buffer overlay | [STRATEGIES.md](STRATEGIES.md) |
| 0017 | `idx.macro` | this file |
| 0018 | `idx.annual_excerpt` | this file |
| 0019 | `idx.consensus` | this file |
| 0020 | `idx.study` / `idx.study_name` / `idx.evidence` | [RESEARCH.md](RESEARCH.md) |
| 0024 | `idx.price_level` | [BOOKS_TICKETS.md](BOOKS_TICKETS.md) |
| 0025 | `idx.push_device` | [ALERTS.md](ALERTS.md) |
| 0026 | many users (`idx/who.py`) | [ARCHITECTURE.md](ARCHITECTURE.md) |
| 0029 | datafeed collector (`idx/feed/`) | [FEED.md](FEED.md) |
| 0032 | `idx.ara_watch` / `idx.ara_touch` | [ARA.md](ARA.md) |
| 0033 | broker distribution capture, widened | [FEED.md](FEED.md) |
| 0034 | desk registry (`idx/registry.py`) | [STRATEGIES.md](STRATEGIES.md) |
| 0035 | alert bus and stream | [ALERTS.md](ALERTS.md) |
| 0036 | `idx.ml_model` / `idx.ml_prediction` / `idx.ml_scorecard` | [ML.md](ML.md) |
| 0038 | ML second pass (purged blocks) | [ML.md](ML.md) |
| 0039 | combined book (`idx.book.params` / `idx.combo_watch` / `idx.combo_scorecard`) | [BOOKS_TICKETS.md](BOOKS_TICKETS.md) |
| 0041 | `combo_watch` `rule`, `size_frac` | [BOOKS_TICKETS.md](BOOKS_TICKETS.md) |
| 0042 + 0043 | online agent tables + `exit_at` | [ML.md](ML.md) |
| 0059, 0060, 0061 | `idx.dt_watch`, universe row, universe frozen at pick | [RESEARCH.md](RESEARCH.md) |
| 0062 | ARA prediction vs actual | [ARA.md](ARA.md) |
| 0063 | `ml_prediction.realize_status` | [ML.md](ML.md) |

## The idx.co.id client and Cloudflare (`idx/client.py`)
- **Original gotcha (1):** idx.co.id is Cloudflare-fronted and **fingerprints TLS — `httpx`/`requests` get 403; `urllib`
  passed until 2026-09-14 and is challenged since; `curl` (Schannel on Windows) passes**. `idx/client.py` therefore runs
  through a `curl` subprocess when one is installed (`INGEST_IDX_TRANSPORT=auto|curl|urllib`; the first call gets one 403 and
  the retry with the cookie jar passes). A challenge shows `cf-mitigated: challenge` on every path incl. robots.txt and is NOT
  an IP block — a different IP/proxy does not help, a different TLS stack does.
- **403 handling (2026-09-14):** a 403 is retried once (a transient challenge), a second 403 stops the call
  (`cf-mitigated: challenge` is Cloudflare, not an IP block; retrying feeds it). `INGEST_IDX_PROXY` routes calls through an
  HTTP CONNECT proxy for recovery only.
- **Cloudflare (2026-09-24, the third tightening):** the challenge is on the **connection fingerprint**, not the IP and not
  the headers - the whole site answered 403 to both curls on this host while Chrome loaded it. Neither curl had HTTP/2
  compiled in, which no browser can be; `curl_cffi` (libcurl-impersonate) speaks Chrome's TLS **and** HTTP/2 and returned
  all 963 rows over HTTP/3 for the very day plain curl could not fetch. It is now the default transport
  (`INGEST_IDX_TRANSPORT=impersonate|curl|urllib|auto`, `INGEST_IDX_IMPERSONATE` = profile, default `chrome`).
  - **The profile ages**: `chrome` and `safari` passed, the pinned `chrome124` and `edge101` were still challenged - so if
    challenges return, try a newer profile before assuming an IP block.
  - Escalation order when a day cannot be fetched: newer impersonation profile -> `INGEST_IDX_PROXY` (different egress) ->
    wait, because `bar_backfill` retries twice a day on its own and heals the hole without anyone watching.

## Daily bars: fallback, gap healing, the anchor day
- **Yahoo fallback for the day's closes (2026-09-14):** `jobs/daily.fallback_yahoo` writes `idx.bar` rows with source 'yahoo'
  and quality_flags {fallback} (never over an 'idx' row; the IDX upsert replaces them later); scheduler `daily_fallback`
  19:40 WIB weekdays when the IDX bar is missing, then marks the books.
  - Desk readers (book, candidates, card, overlay, pack, publish, ticket) accept source IN ('idx','yahoo');
    `daily.latest_bar_date` and crosscheck stay IDX-only so the chain keeps trying IDX and the no-bar alert still fires.
- **Gap healing (`scheduler.bar_gaps` / `run_bar_backfill`, 2026-09-24):** the chain only ever chases TODAY, so a day IDX
  refuses leaves a permanent hole - a Cloudflare challenge on 2026-09-23 cost 758 of 963 names (the Yahoo fallback covers
  only `universe_codes`) and nothing but a human running `idx backfill` would have filled it.
  - Twice a day the backfill re-fetches recent weekdays that have **no `source='idx'` bar and whose last `daily` run failed or
    never ran**; a public holiday answers empty with status 'ok', so it is never re-asked.
  - Features are left to the next chain (45-day lookback).
- **A partial day must never blank the desk:** `candidates.build` and `pack.build` anchor on `max(idx.daily_summary.trade_date)`,
  the last COMPLETE day - not on `max(idx.bar)`. The Yahoo fallback writes `idx.bar` only, so anchoring on the bar picked a
  day whose inner join to `daily_summary` matched nothing: on 2026-09-23 candidates, scores, the screener and `/pub` all
  returned zero rows until IDX answered again.

## Data gotchas (numbered as in the original list; (1) is the client section above)
- (2) Use `127.0.0.1`, not `localhost`, in the local DSN (IPv6 `::1` hangs on the Docker port proxy).
- (3) idx.co.id serves **2020-01-02 onward only**; pre-2020 comes from the Yahoo split-only cache
  (`research/idx_ohlc_loader.py`, `yf_fetch(adjust=False)`).
- (4) Backfill uses the whole-market day-dump (`GetStockSummary?date=`) so delisted names are included; per-stock
  `GetTradingInfoSS` is only a cross-check.
- (5) `OpenPrice=FirstTrade=0` (2020-03-13..09-04, no pre-opening) → `open` NULL + `open_missing`, never fabricated.
- (6) Corporate actions come from IDX's `Previous` reset vs prior close; exact split ratios from listed-shares change;
  `idx.bar.adj_factor` is rewritten for earlier rows, raw prices never change.
- (7) A code in the day-dump but not in Daftar Saham (e.g. GOTOM multiple-voting shares) is `listing.status='NOT_IN_DAFTAR'`,
  not delisted.
- (8) **Opens before 2025 exist only for LQ45** in IDX's own data (`open_missing` on ~80 % of 2020-24 rows is the source, not
  a bug).
- The index has no open either (NULL on all COMPOSITE rows): see the chart section in [ARCHITECTURE.md](ARCHITECTURE.md).
- Survivorship of `idx.bar` (checked 2026-09-25): see [ML.md](ML.md#survivorship-checked-2026-09-25).

## Financial-report workbooks (`idx/fin_parse.py`, `idx/fin_store.py`)
**Workbook scaling gotchas (`idx/fin_parse.py`):**
- (a) the FY2023 vintage (published Jan-Apr 2024) is labelled "in millions" but holds full rupiah — `_effective_rounding`
  overrides the label when total assets would exceed 50,000 T (IDR) / 3 T (USD), and scales up when a "full amount" label
  yields < Rp 1 bn;
- (b) ~27 % of USD-filer reports carry no conversion rate — `fin_store.fx_table` supplies the median reporting-date rate other
  filers reported for that period end (`FX_SEED` for a fresh DB), `Parsed.fx_source` says which;
- (c) a company whose *every* report is mis-scaled (PGEO, 1000×) is invisible to the neighbour cross-check, and some filers
  scale the EPS row too (BBNI FY2024 EPS 0.0006) — `fin_store._eps_reconcile` compares `net_profit` with
  `eps × listed shares`; a clean power-of-1000 gap is resolved by the publication-day price (the side whose earnings yield
  could belong to a company wins): `report_rescaled` re-parses the whole workbook, `eps_rescaled` fixes EPS only,
  `scale_mismatch` / `eps_mismatch` are stored in `fundamental.flags` (`scale_mismatch` surfaces as a candidate warning).
- All unit-tested; `fin parse --reparse` re-derives everything from the archived files (safe to run in parallel by code chunks).
- Backlog: scheduler `fin_backlog` Tue-Sat 05:30 WIB (2021-2023 quarterly workbooks, 60 a day, skips the day when IDX challenges
  the client). Current workbooks: job `fundamentals` ([JOBS.md](JOBS.md)).
- How the parsed figures are evaluated (PIT, TTM, gates): `idx/metrics.py` in [STRATEGIES.md](STRATEGIES.md).

## Annual reports (`idx/annual.py`, migration 0018 `idx.annual_excerpt`, 2026-09-14)
- IDX lists laporan tahunan under the same endpoint with `reportType=ar` (client `financial_report(..., report_type='ar')`;
  rows in `idx.financial_report` with report_type 'ar').
- `idx annual discover --years | download --list|--codes|--universe | extract | status | show CODE`: the main PDF (most pages)
  goes to `data/idx/annual/<code>/<code>_<year>.pdf`, the plan pages (prospek, proyeksi/target, strategi, rencana/capex,
  risiko, dividen; uppercase headings after the first fifth of the report) are stored as excerpts and appended to the thesis
  card (web, phone, pack).
- Scheduler job `annual` on the 6th, 10:00 WIB, for today's lists and holdings, at most 8 reports per run at 0.2 rps (the rest
  wait for the next run).
- Needs `pypdf[crypto]` (some issuers, e.g. SRTG, publish AES-encrypted PDFs).
- Known IDX-side corrupt uploads (2026-09-16): DEWA FY2025 (truncated), GPRA FY2025 (all-zero file) — issuer sites only.

## News + analyst consensus (`idx/news.py`, `idx/consensus.py`, migration 0019 `idx.consensus`, 2026-09-14/16)
- `idx news pull|show [--codes]` collects the public RSS feeds of Kontan, Bisnis, CNBC Indonesia, Antara, IDX Channel into
  `idx.news_article` (titles + summaries only, deduplicated by text hash, tagged with the codes mentioned via ticker or
  `idx.company_alias`); collection only, no scoring — the history the desk never had.
- `idx consensus pull|show [--codes]` snapshots Yahoo's analyst consensus per name (target mean/low/high, n, recommendation,
  forward/TTM P/E, upside) into `idx.consensus` (code, snapshot_date), so revisions can be tested in a year.
- Scheduler: `news` 06:10/12:10/18:10/22:10 WIB, `consensus` Sat 11:00 WIB (universe + holdings).

## Macro series (`idx/macro.py`, migration 0017 `idx.macro`, 2026-09-14)
- Series: BI-Rate (Bank Indonesia's page via `curl`; Python's TLS is reset by the site; OECD history via FRED to 2023-12),
  USD/IDR, GDP q/q and annual, CPI (OECD, lags), US 10y, Fed funds, VIX, Brent, gold, CPO, **Indonesia inflation y/y from BPS**
  (`id_inflation_yoy`, source `bps`, variable 2263, national row; 2024-01 onward, the live replacement for the OECD CPI index
  that stops 2025-04).
- Scheduler jobs `macro` 07:30 and `macro_pm` 14:00 WIB Mon-Sat - the afternoon run exists because BPS publishes the monthly
  reading around midday on the 1st (measured 2026-09-01 12:26 WIB), so the morning pull would miss it by a day; it also
  retries whatever failed in the morning.
- CLI `idx macro pull [--keys a,b] [--full] | show | bps-find [--keys KEYWORD]`; API `/idx/macro`.
- Needs INGEST_FRED_API_KEY and INGEST_BPS_API_KEY (the BPS App ID is the `key` parameter; idx-local.env).
- No free source for the ID 10-year yield.
- Tested as stress-detector inputs and rejected (`research/IDX_MACRO_STRESS_2026-09-14.md`): the board is for reading.
- The BPS source in detail (variable 2263, API gotchas) and how the ML panel uses macro by release date: [ML.md](ML.md).

## Company logos (`idx/logos.py`, 2026-09-25)
- Operator: "buat semua saham memiliki logo nya masing2 ... dari stockbit".
- Stockbit's public CDN `https://assets.stockbit.com/logos/companies/{CODE}.png` (no login, ~5-7 KB), downloaded ONCE into
  `<data>/idx/logos/{CODE}.png` and served by `GET /idx/logo/{code}` (PNG, `Cache-Control: public, max-age=604800`; 404 = no
  logo -> the web shows a two-letter monogram).
- The CDN answers **403, not 404,** for a logo it lacks: one 403 is recorded as `{CODE}.missing` (not asked again until
  `--refresh`), five in a row stop the run as pushback (and the false misses are forgotten).
- CLI `idx logos [--codes A,B] [--refresh]` (PowerShell: quote the comma list); job `logos` Sunday 10:00 WIB takes new listings.
- The web proxy (`blackheart-idx-web/src/app/idx/[...path]/route.ts`) passes `image/*` through as bytes.
