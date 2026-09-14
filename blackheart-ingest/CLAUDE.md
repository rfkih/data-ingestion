# blackheart-ingest — Macro / Market-Data Ingest + Feature Compute

Python/FastAPI service that pulls macro, options, and market data from free external sources into Postgres and computes macro `feature_values`; called over HTTP by the Trading JVM's `BackfillMl*` handlers and scheduled by `MlIngestScheduleRefresher`.

> Part of the Blackheart workspace — topology + repo map in C:/Project/CLAUDE.md.

## What it does
- **Sources in** (all free, mostly no-auth): FRED + ALFRED vintages, Deribit DVOL + Deribit option-surface skew (`deribit_options`), Binance spot (`binance_spot`), Binance futures macro (funding / OI / L-S / taker), Binance forceOrder liquidation stream, Binance orderbook, CoinMetrics, DefiLlama, CoinGecko, alternative.me Fear&Greed, ForexFactory.
- **Tables out:** raw rows → `macro_raw` (+ source-health rows); computed macro features → `feature_values` (keyed to `feature_registry`). PIT-rejected rows are counted, not silently dropped.
- **Consumers:** the Trading/Research JVMs read `feature_values`; the inference sidecar (`inference/`, separate worker) reads features and writes `signal_history`.

## Tech stack
Python 3.12, FastAPI + uvicorn, Pydantic v2 / pydantic-settings, httpx + tenacity, structlog, psycopg 3 (sync), pandas + numpy, fredapi, websockets, lightgbm (inference). Optional extras: `kafka` (aiokafka + python-snappy, used in the Docker image), `html-scrape` (bs4 + lxml, ForexFactory HTML fallback, currently unused).

## Layout (`src/blackheart_ingest/`)
- `workers/server.py` — **the SERVED FastAPI app (`workers.server:app`)**; entry point `blackheart-ingest-server`. This is what Docker runs.
- `workers/compute_features.py` — `blackheart-ingest-compute` one-shot/loop feature compute CLI.
- `workers/inference_backfill.py` — `blackheart-ingest-inference` sidecar backfill (loads model artifacts, writes `signal_history`).
- `workers/bar_event_consumer.py`, `feature_stream.py` — Kafka bar-close → feature-compute pipeline.
- `sources/` — one module per source; `server._KNOWN_SOURCES` maps `/pull/{source}` names to modules. `binance_liquidation.py` is a lifespan worker (not a `/pull` source).
- `features/` — `definitions.py` (declarative `FeatureDef`s), `compute.py`, `persistence.py`.
- `inference/` — ML sidecar (registry / artifacts / persist / api).
- `shared/` — `settings.py`, `db.py`, `pit_guards.py`, `binance_http.py`, `logging_setup.py`.
- `schemas/` — Kafka event models. `api/` — **DEAD** (no live modules; the old unused app factory lived here).
- `tests/` — pytest suite incl. `test_server_app.py` (boots the served app with its lifespan).

## Build / test / run
```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"          # CI installs ".[dev,kafka]"
ruff check src                    # lint
mypy src                          # type-check
pytest                            # tests
python -m blackheart_ingest.workers.server   # run server (or: blackheart-ingest-server)
```
Copy `.env.example` → `.env` and set `INGEST_FRED_API_KEY`. Server listens on `127.0.0.1:8001` (loopback) by default; the Docker image forces host `0.0.0.0` + port `8001` internally.
Key routes: `GET /health` (and `/healthz`), `GET /sources`, `GET /features`, `POST /pull/{source}`, `POST /compute/{feature}/v/{version}`, `POST /compute/incremental`, `GET /liquidation/status`.

## Deploy
Has its **own CI** (`C:/Project/.github/workflows/blackheart-ingest-ci.yml`, root workspace — not inside this repo): push to `master` runs pytest + a served-app smoke-boot, builds/pushes the GHCR image, then auto-deploys to the VPS (gated by `vars.DEPLOY_ENABLED`) with a healthcheck + auto-rollback.
**Docker-run-managed on the VPS — NOT compose.** The container is created via `docker rm -f` + `docker run -d --name blackheart-ingest --network blackheart_default --env-file /home/starsky/blackheart/ingest.env -p 127.0.0.1:8001:8001 -p 100.112.13.126:8001:8001` (loopback + Tailscale only). A `docker compose up` would create a conflicting container — recreate by hand with the same `docker run` + env_file if you must touch it live. CI pulls the image BEFORE removing the old container (a pull-then-rm ordering bug once caused a 53-min outage + lost unbackfillable liquidation events).

## IDX data plane (`src/blackheart_ingest/idx/`, phase 0 — 2026-09-12)

Primary-source Indonesian equities (idx.co.id) → schema **`idx`** in the same `trading_db`; self-scheduled,
**independent of the trading JVM**. Spec: `C:/Project/docs/superpowers/specs/2026-09-12-idx-data-platform-design.md`;
build plan: `docs/superpowers/plans/2026-09-12-idx-platform-build-plan.md`.

- **Layers:** bronze = every response archived (`INGEST_IDX_BRONZE_DIR/<endpoint>/<key>/<fetched_at>.json.gz` + `idx.bronze_index`)
  → silver = `idx.*` tables via pure ETL (`idx/etl.py`) → gold = `public.market_data` rows `<CODE>.JK / 1d` (IDX reference-price basis =
  splits + rights/bonus via `Previous` resets, never cash dividends; `idx/publish.py` re-bases the Yahoo pre-2020 segment onto it). Silver/gold are derived; `idx replay` rebuilds them from bronze with no network.
- **CLI:** `python -m blackheart_ingest.idx.cli` — `migrate | status | universe | daily --date | index --date |
  backfill --from --to [--index] | replay | publish [--full] | announce | features [--publish] | fin discover|download|parse |
  dividends | card CODE | candidates [--as-of D] | answers [--score] | crosscheck | run-scheduler`. Local wrapper:
  `C:/Project/scripts/idx.sh` / `idx.ps1` (loads `idx-local.env`, gitignored).
- **Desk accounts (`idx/accounts.py`, migration 0015 `idx.app_user`, 2026-09-13):** the Papan app's users. Anyone can register; scrypt password hashes; 30-day HS256 sessions signed with `IDX_JWT_SECRET` (base64, `idx-local.env`; the app holds the same value as `JWT_SECRET`); failed sign-ins throttled per email. Served at `/api/v1/users/register|login|me|logout` in the trading JVM's user-API shape (ResponseDto envelope, `blackheart-token` cookie), so the app's `INTERNAL_TRADING_URL` points at this worker and would work unchanged against the JVM. These routes are open by design (loopback bind + the app in front); they are not under `/idx` and never need `X-Ingest-Token`.
- **Value/quality book (phase 2 verdict, `research/IDX_VALUE_QUALITY_2026-09-12.md` rev. 3; review
  `research/IDX_REVIEW_2026-09-12.md`):** `idx/metrics.py` is the one PIT evaluator (latest audited + latest quarterly → TTM,
  loose/strict gates, warnings; information cutoff = 16:00 WIB of the as-of day; prior-period comparatives come from the report
  (`net_profit_prior`, migration 0009) — the YoY ratio is only inverted when its sign is certain). `idx/candidates.py` applies
  the rule: board Utama/Pengembangan **on the day** (`board_from_remarks`: 5th char of the day-dump notation string, 1 Utama
  2 Pengembangan 3 Akselerasi 4 Pemantauan Khusus 5 Ekonomi Baru) → traded that day → liquid ≥ Rp 5 bn/day → loose gate →
  composite **average** rank E/P+B/P+DY → top fifth, min 10, only when the pool has ≥ 20 names. `rank_pool(rows, gate=,
  keys=, sector_cap=)` is the single implementation — `research/idx_value_quality.py` calls `candidates.build()`/`rank_pool()`
  per rebalance date, so backtest and live list cannot drift. Rows carry `data_error_ratio` (ratio > 50×), `no_trade_on_date`,
  `scale_mismatch` warnings. `idx/card.py` is the per-name thesis card. `GET /idx/candidates[?all=1&as_of=]`. Gates are
  evaluated on the **audited** year; TTM and quarterly warnings are shown for judgment, never used to exclude automatically.
  `idx answers --score` = forward returns per pack stance / veto vs COMPOSITE (21/63/126/252 trading days).
- **Book overlays (`idx/overlay.py`, migration 0012, `research/IDX_TREND_OVERLAY_2026-09-13.md`):** per-book flags
  `regime_filter` (cash while COMPOSITE < its 200-day average; monthly check on the first trading day of the month inside
  the daily chain -> `cash` ticket when it turns off, `rebalance` ticket when it turns on; an annual rebalance while off
  becomes a cash ticket) and `entry_gate` (listed names under their own SMA200 are held back at a rebalance, bought with an
  `entry` ticket at the monthly check they cross). Checks recorded in `idx.regime_check`; `idx overlay status | check
  [--dry-run]`; `/idx/overlay`, `POST /idx/overlay/check`. Plus `take_profit_pct` (NULL = off): at the monthly check, held names at or above purchase x (1 + pct) go into an exits ticket (`research/IDX_SELL_RULES_2026-09-13.md`). Plus `trend_exit` (migration 0014): at the monthly check, a held name that crossed under its 200-day average since the previous check goes into an exits ticket, and the entry gate also buys a held-back name when its 14-day RSI is at or under 30 (the asymmetric rule, `research/IDX_ASYMMETRIC_2026-09-13.md`). Plus the cash buffer (migration 0016): `cash_floor_pct` of NAV kept in cash, `stress_cash_pct` while the stress detector (`stress_rule` ma | any2; four signals recorded in `idx.stress_check` at the monthly check) is on; the ticket builder uses it as the plan's cash reserve and the monthly check issues a rebalance ticket when the target moves 5+ points (`research/IDX_CASH_BUFFER_2026-09-14.md`). All OFF by default (paper book: the four trend overlays on since 2026-09-13). Signals are computed at the check close; tickets are meant to be worked at the next open (delay cost measured in `research/idx_execution_delay.py`). `ticket.min_trade_for(nav)` scales the minimum line with the book (NAV/20, floor Rp 1M, cap Rp 5M).
- **Strategy catalog (`idx/strategies.py`, migrations 0010 + 0011):** families `rule` (baseline) · `strict` (deployed since
  2026-09-12, the operator's call ahead of the pre-registered May 2027 date) · `strict_cash` (tested: passes its criterion on
  one name, ENRG; not the default) · `value` · `momentum` · `momentum_rank` · `growth`, each `{gate, order, weight[, keys]}`;
  `strategies.deployed()` is the API's default strategy; a choice = family + size (None = natural
  fifth, 10, 15). `strategies.pick(key, rows, size=, weight=)` is the ONE implementation of "which names, what weights"
  (composite families order their gate pool; feature families order the rule's fifth by ep / mom / np_yoy); the research
  scripts call it too (`research/idx_top10.py <10|15>`), so tested == deployed. `candidates.build` now stores `mom` (12-1
  month momentum, `momentum_at`). `idx.book.strategy` + `max_names` say what a book follows; `ticket.build(strategy=,
  max_names=)` defaults to them and `ticket.plan` takes `{code: weight}` targets. `idx.strategy_history (strategy, size,
  month)` holds the research record (`idx strategies import-history <rev3 json> <top10 json> <top15 json>`, `idx strategies
  list`). Routes: `GET /idx/strategies`, `GET /idx/strategies/{key}?size=`, `GET /idx/candidates?strategy=&size=&all=`,
  `PUT /idx/book/{b}` accepts `strategy`/`max_names`, `POST /idx/ticket/build?strategy=`.
- **Analysis pack (manual Claude chat, no API):** `idx pack` → `idx/pack.py` builds one markdown (pinned prompt `pack_v1` +
  market + candidate table + a compact section per name: valuation, gates, 4 quarters + 3 FY, flow, disclosures since the previous
  pack) for selected candidates + next 10 + `idx.watchlist`; stored in `idx.nightly_pack` and written to
  `research-scratch/idx-pack/<date>/pack.md` (~13k tokens for 32 names). The operator pastes it into Claude chat and saves the
  JSON block; `idx pack-import answer.json` validates (codes must be in the pack, stance buy|hold|avoid|sell, conviction 1-5,
  veto needs a reason) and writes `idx.sentiment_score` rows (`doc_type='pack'`, `model='claude-chat-manual'`) +
  `nightly_pack.answer_json`. `idx answers`, `idx watch list|add|rm`. Routes: `GET /idx/pack/latest|{date}`, `POST /idx/pack/build`,
  `POST /idx/pack/{date}/answer`, `GET /idx/answers`, `GET|PUT /idx/watchlist`.
- **Position book (`idx/book.py`, migration 0007):** `idx.book` (live | paper; cash, fee %, dividend tax), `idx.fill` (buy | sell |
  split; average cost, fees in the basis) → `idx.position` rebuilt from fills; `idx book mark` writes `idx.book_mark` + `idx.book_nav`
  per trading day (net dividends credited on the ex-date, splits become `split` fills; cash anchored on the live `book.cash`, so a
  back-dated fill needs `--rebuild`); `idx book check` raises deduplicated `idx.alert` rows (`job='book:<name>'`) for held names:
  material disclosures (last 3 days), a new report breaking the book rule or with TTM warnings, unrealized loss ≥ 25 %, liquidity
  below half the floor. `idx book fill --date --code --side --lots --price [--fee]` is how the operator records broker fills;
  `idx book paper-seed --book paper --as-of <candidate run date> --amount N` buys the selected list at the next open. Both books
  are marked + checked at the end of the daily chain. Routes: `GET /idx/book/{book}`, `POST /idx/book/{book}/fills`, `PUT /idx/book/{book}`.
  `research/idx_book.py` (CSV ledger) is superseded; `idx book import --file fills.csv` reads its format.
- **Rebalance ticket (`idx/ticket.py`, migration 0008):** `idx ticket build --book live [--mode rebalance|exits] [--as-of run_date]
  [--max-names N]` → `idx.ticket` + `idx.ticket_line`. `rebalance` = hold the selected candidates equal-weight: sell what is no
  longer selected, trim/add beyond ±1 % of NAV (min Rp 5 M), buy new entrants, whole lots, limit = one tick through the reference
  close clamped inside the auto-rejection band, buys capped by cash + expected sale proceeds − 1 % reserve (`cash-limited` flag).
  `exits` = sells only, for held names whose newest report breaks the book rule or whose latest pack answer is `sell`. Lines carry
  rank, strict-gate fails, TTM warnings and the pack stance/veto as flags. Paper tickets fill themselves at the next day's open inside the daily chain (`idx ticket paper-fill --dry-run` previews; sells first, buys trimmed to cash, unfillable lines skipped, ticket closed); live fills are captured by hand: `idx ticket fill --line ID --lots --price
  [--fee]` (→ `idx.fill`, book re-marked; partial fills tracked), `idx ticket skip --line ID --reason`, `issue|close|cancel`.
  IDX rules encoded (verify against Peraturan II-A on change): lot 100; fractions 1/2/5/10/25 below 200/500/2,000/5,000/above;
  symmetric auto-rejection 35/25/20 % for 50–200/200–5,000/>5,000. Scheduler: May 1–10 alert if the live book has no rebalance
  ticket yet. Routes: `GET /idx/ticket/latest?book=`, `GET /idx/ticket/{id}`, `POST /idx/ticket/build`, `POST /idx/ticket/{id}/status`,
  `POST /idx/ticket/lines/{id}/fill|skip`.
- **Workbook scaling gotchas (`idx/fin_parse.py`):** (a) the FY2023 vintage (published Jan-Apr 2024) is labelled "in millions"
  but holds full rupiah — `_effective_rounding` overrides the label when total assets would exceed 50,000 T (IDR) / 3 T (USD),
  and scales up when a "full amount" label yields < Rp 1 bn; (b) ~27 % of USD-filer reports carry no conversion rate —
  `fin_store.fx_table` supplies the median reporting-date rate other filers reported for that period end (`FX_SEED` for a fresh
  DB), `Parsed.fx_source` says which; (c) a company whose *every* report is mis-scaled (PGEO, 1000×) is invisible to the
  neighbour cross-check, and some filers scale the EPS row too (BBNI FY2024 EPS 0.0006) — `fin_store._eps_reconcile` compares
  `net_profit` with `eps × listed shares`; a clean power-of-1000 gap is resolved by the publication-day price (the side whose
  earnings yield could belong to a company wins): `report_rescaled` re-parses the whole workbook, `eps_rescaled` fixes EPS only,
  `scale_mismatch` / `eps_mismatch` are stored in `fundamental.flags` (`scale_mismatch` surfaces as a candidate warning).
  All unit-tested; `fin parse --reparse` re-derives everything from the archived files (safe to run in parallel by code chunks).
- **Schema:** own migrations `idx/migrations/NNNN_*.sql` + `idx.schema_history` (sha256-checked, never edit an applied file).
  Not Flyway. JVM/equity roles get SELECT only.
- **Jobs (WIB):** `universe` 16:15 · `daily` every 15 min 16:30–20:00 until today's bar lands → `index` → `publish --since`
  → `features --since -45d` → `candidates` · 18:00 alert if no bar · `announce_recent` 20:30 (all-emiten feed, last 3 days,
  one request per day) · `fundamentals` 21:00 Mon–Fri (discover current FY → download pending workbooks for
  `metrics.universe_codes` → parse) and Sat 09:00 with the previous FY too · `dividends` 1st of month 09:30 (Yahoo) ·
  Sunday `crosscheck`. Alerts are rows in `idx.alert`, shown by the app (`/equities/ops` via `GET /idx/ops` on this server);
  no Telegram/email.
- **Gotchas:** (1) idx.co.id is Cloudflare-fronted and **fingerprints TLS — `httpx`/`requests` get 403, stdlib `urllib` passes**;
  `idx/client.py` uses urllib on purpose. (2) Use `127.0.0.1`, not `localhost`, in the local DSN (IPv6 `::1` hangs on the Docker
  port proxy). (3) idx.co.id serves **2020-01-02 onward only**; pre-2020 comes from the Yahoo split-only cache
  (`research/idx_ohlc_loader.py`, `yf_fetch(adjust=False)`). (4) Backfill uses the whole-market day-dump
  (`GetStockSummary?date=`) so delisted names are included; per-stock `GetTradingInfoSS` is only a cross-check.
  (5) `OpenPrice=FirstTrade=0` (2020-03-13..09-04, no pre-opening) → `open` NULL + `open_missing`, never fabricated.
  (6) Corporate actions come from IDX's `Previous` reset vs prior close; exact split ratios from listed-shares change;
  `idx.bar.adj_factor` is rewritten for earlier rows, raw prices never change. (7) A code in the day-dump but not in Daftar Saham
  (e.g. GOTOM multiple-voting shares) is `listing.status='NOT_IN_DAFTAR'`, not delisted.
  (8) **Opens before 2025 exist only for LQ45** in IDX's own data (`open_missing` on ~80 % of 2020-24 rows is the source, not a bug).

## Gotchas
- **`api/` is dead.** The served app is `workers.server:app`; the old `api/` app factory was unused. CI's `test_server_app.py` exists precisely because the old suite tested the dead app while the served app shipped broken ("CI green, served app broken").
- **Mutation routes are unauthenticated** unless `INGEST_AUTH_TOKEN` is set — never publish `/pull` or `/compute` on a public interface (the loopback+Tailscale bind is the safeguard).
- **Liquidations are not backfillable** — the `binance_liquidation` lifespan worker is the only source of those rows; don't interrupt it carelessly. Default OFF (`INGEST_LIQUIDATION_STREAM_ENABLED`).
- **`deribit_options` has no free history** — each hourly snapshot is the only copy ever captured (plant-and-accumulate). Default OFF (`INGEST_DERIBIT_OPTIONS_ENABLED`).
- **PIT discipline** (`shared/pit_guards.py`): every row is validated before insert — future event_time, inverted publisher timestamp, and out-of-window backfill are rejected and counted as `rows_rejected_pit`. FRED uses lag-aware windows so monthly series keep streaming. Feature compute refuses to carry a forward-filled value older than `max_ffill_age_hours`.
