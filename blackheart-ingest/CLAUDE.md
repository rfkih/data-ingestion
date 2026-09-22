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
- **Annual reports (`idx/annual.py`, migration 0018 `idx.annual_excerpt`, 2026-09-14):** IDX lists laporan tahunan under the same endpoint with `reportType=ar` (client `financial_report(..., report_type='ar')`; rows in `idx.financial_report` with report_type 'ar'). `idx annual discover --years | download --list|--codes|--universe | extract | status | show CODE`: the main PDF (most pages) goes to `data/idx/annual/<code>/<code>_<year>.pdf`, the plan pages (prospek, proyeksi/target, strategi, rencana/capex, risiko, dividen; uppercase headings after the first fifth of the report) are stored as excerpts and appended to the thesis card (web, phone, pack). Scheduler job `annual` on the 6th, 10:00 WIB, for today's lists and holdings, at most 8 reports per run at 0.2 rps (the rest wait for the next run). Needs `pypdf[crypto]` (some issuers, e.g. SRTG, publish AES-encrypted PDFs). Known IDX-side corrupt uploads (2026-09-16): DEWA FY2025 (truncated), GPRA FY2025 (all-zero file) — issuer sites only.
- **Yahoo fallback for the day's closes (2026-09-14):** `jobs/daily.fallback_yahoo` writes `idx.bar` rows with source 'yahoo' and quality_flags {fallback} (never over an 'idx' row; the IDX upsert replaces them later); scheduler `daily_fallback` 19:40 WIB weekdays when the IDX bar is missing, then marks the books. Desk readers (book, candidates, card, overlay, pack, publish, ticket) accept source IN ('idx','yahoo'); `daily.latest_bar_date` and crosscheck stay IDX-only so the chain keeps trying IDX and the no-bar alert still fires. Client: a 403 is retried once (a transient challenge), a second 403 stops the call (`cf-mitigated: challenge` is Cloudflare, not an IP block; retrying feeds it). `INGEST_IDX_PROXY` routes calls through an HTTP CONNECT proxy for recovery only.
- **Many users, each with their own desk (`idx/who.py`, migration 0026, 2026-09-17):** `idx.book.owner_id/label/rule/trend_variant/archived_at`, `idx.decision.user_id`, `idx.watchlist (user_id, code)`, `idx.push_device.user_id`, `idx.app_user.plan/accepted_terms_at`. Every personal `/idx/*` route takes a `Caller` (`who.caller_of`): a signed-in account (the app's proxy forwards the session JWT as `Authorization: Bearer`; verified with `IDX_JWT_SECRET`) is scoped to its own books/tickets/journal/watchlist/phones (`own_book` -> 404 for anyone else's); a service holding the ingest token (CLI, scheduler, agent) is unscoped, or scoped to one account with `X-Idx-User: <email>` (the nightly agent sends `IDX_AGENT_USER`); with no ingest token configured (this box, tests) a credential-less loopback caller counts as an unscoped service. Research reads stay open; research writes (pack build/answer, evidence, macro pull, overlay check) are `service_only` (403 for an account). New: `POST /idx/books {label, kind paper|live, rule annual|trend, cash, broker, fees, strategy, max_names, trend_variant}` -> id `<kind>-<6hex>` (`ticket.is_paper` = id starts with `paper`), `DELETE /idx/book/{book}` archives (open tickets cancelled, out of every list and job), `GET /idx/books` lists the caller's. `book.create_book/list_books/owner_of/archive`. Notifications go to a person: `notify.send(user_id= | book=)` -> the book's owner's phones, alerts `book:X`/`ticket:X` -> X's owner, desk alerts -> `IDX_OPS_NOTIFY_EMAIL`'s phones (unset = dropped); `journal.record(user_id=)` defaults to the book's owner. Existing books (`live`, `paper`, `trend_live`, `paper_trend`) were assigned to the first account (the operator). Test books stay ownerless. Tests: `tests/idx/test_multiuser.py`.
- **Phone push (`idx/push.py`, migration 0025 `idx.push_device`, 2026-09-17):** the operator's notification channel is the Blackridge Android app (`blackheart-idx-web`; renamed from Papan on 2026-09-17 - older notes below say Papan), not Telegram. `notify.send(text, title=, data=)` fans out to every configured channel: the app (`push.broadcast` -> Firebase Cloud Messaging HTTP v1, bearer from a service-account JWT signed with `cryptography`, cached; `IDX_FCM_SERVICE_ACCOUNT` = path of the Firebase service-account JSON placed by the operator, never through chat or git) and Telegram (only if `IDX_TELEGRAM_*` are set). A text's first line is the push title; `data.route` is the app screen a tap opens (`notify.ticket_data(t)` -> `/m/ticket?book=`; alerts -> `/m/more`). Device tokens come from the app (`POST /idx/push/register {token, platform, label}` + `X-Idx-User` from the app's proxy; `DELETE /idx/push/{token}`; `GET /idx/push/devices`; `POST /idx/push/test`); a token FCM reports gone (404 / UNREGISTERED) is disabled until the app registers again. Nothing here raises into the job that notified. CLI `idx push devices | test [--text]`, `idx notify --status` lists the channels. `GET /idx/books` lists every book (kind live|paper, rule annual|trend, nav, open ticket) for the phone's selectors.
- **Price levels (`idx/levels.py`, migration 0024 `idx.price_level`, 2026-09-17):** per book+code+kind (stop | take_profit | warn) a level and a note saying what to do. `levels.check` runs after every mark in the daily chain and the Yahoo-fallback path: stop/warn fire at close <= level, take_profit at close >= level; alert critical (stop, take_profit) / warning (warn) through `runlog.alert` (Telegram when `IDX_TELEGRAM_TOKEN`/`_CHAT` are set, see notify.py), stamped `triggered_at` so it fires once until `idx levels reset CODE`. Index codes (COMPOSITE) read `idx.index_daily`. CLI `idx levels set CODE [--stop L] [--tp L] [--warn L] [--note] | list | clear CODE [--kind] | reset CODE | check`. Live book 2026-09-17: satellite SSIA stop 1,030 / tp 3,440 / warn 1,250, LPKR 35 / 118 / 45; core names warn -25 % and stop -40 % vs avg; COMPOSITE warn 5,800 / stop 5,150.
- **Research store (`idx/research_store.py`, migration 0020 `idx.study` / `idx.study_name` / `idx.evidence`, 2026-09-17):** research results as rows. A study run (`record_study`: name, as_of, params, summary, the names it surfaced with their figures, screens, score, rank and the screens' historical hit rates), and evidence per name (`add_evidence`: kind news | announcement | annual | web | analyst | note, deduplicated on (code, kind, url, title); `collect_evidence` pulls material disclosures, press items and the annual-report plan sections the data plane already holds). `name_view` assembles one name: studies that flag it, evidence by kind, pack answers, consensus, latest candidate row. CLI `idx study list|show [--name N|--id I]|name CODE`, `idx evidence collect CODE[,CODE] [--days N] [--study I] | add CODE --kind K --title T [--url --summary --tags --ts] | show CODE`. API `GET /idx/study?name=`, `/idx/study/latest?name=`, `/idx/study/{id}`, `/idx/name/{code}`, `POST /idx/name/{code}/evidence`. `research/idx_doublers.py --store` writes its run (study `doublers`).
- **News + analyst consensus (`idx/news.py`, `idx/consensus.py`, migration 0019 `idx.consensus`, 2026-09-14/16):** `idx news pull|show [--codes]` collects the public RSS feeds of Kontan, Bisnis, CNBC Indonesia, Antara, IDX Channel into `idx.news_article` (titles + summaries only, deduplicated by text hash, tagged with the codes mentioned via ticker or `idx.company_alias`); collection only, no scoring — the history the desk never had. `idx consensus pull|show [--codes]` snapshots Yahoo's analyst consensus per name (target mean/low/high, n, recommendation, forward/TTM P/E, upside) into `idx.consensus` (code, snapshot_date), so revisions can be tested in a year. Scheduler: `news` 06:10/12:10/18:10/22:10 WIB, `consensus` Sat 11:00 WIB (universe + holdings), `fin_backlog` Tue-Sat 05:30 WIB (2021-2023 quarterly workbooks, 60 a day, skips the day when IDX challenges the client).
- **Macro series (`idx/macro.py`, migration 0017 `idx.macro`, 2026-09-14):** BI-Rate (Bank Indonesia's page via `curl`; Python's TLS is reset by the site; OECD history via FRED to 2023-12), USD/IDR, GDP q/q and annual, CPI (OECD, lags), US 10y, Fed funds, VIX, Brent, gold, CPO. Scheduler job `macro` 07:30 WIB Mon-Sat; CLI `idx macro pull [--full] | show`; API `/idx/macro`. Needs INGEST_FRED_API_KEY (.env). No free source for the ID 10-year yield. Tested as stress-detector inputs and rejected (`research/IDX_MACRO_STRESS_2026-09-14.md`): the board is for reading.
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
  [--dry-run]`; `/idx/overlay`, `POST /idx/overlay/check`. Plus `take_profit_pct` (NULL = off): at the monthly check, held names at or above purchase x (1 + pct) go into an exits ticket (`research/IDX_SELL_RULES_2026-09-13.md`). Plus `trend_exit` (migration 0014): at the monthly check, a held name that crossed under its 200-day average since the previous check goes into an exits ticket, and the entry gate also buys a held-back name when its 14-day RSI is at or under 30 (the asymmetric rule, `research/IDX_ASYMMETRIC_2026-09-13.md`). Plus the cash buffer (migration 0016): `cash_floor_pct` of NAV kept in cash, `stress_cash_pct` while the stress detector (`stress_rule` ma | any2; four signals recorded in `idx.stress_check` at the monthly check) is on; the ticket builder uses it as the plan's cash reserve and the monthly check issues a rebalance ticket when the target moves 5+ points (`research/IDX_CASH_BUFFER_2026-09-14.md`). All OFF by default (paper book: the four trend overlays on since 2026-09-13). On a TREND book `regime_filter` is the regime gate: no NEW entry while the COMPOSITE closes under its 200-day average, held names untouched (`trend_book.hold_back`, `overlay.index_regime`; the ticket carries `regime` + `held_back`; validated in `research/IDX_REGIME_VALIDATE_2026-09-22.md` and `IDX_ROBUSTNESS_SCORECARD_2026-09-22.md`); on `paper_trend` and `trend_live` since 2026-09-22; CLI `idx book set --book X --regime-filter on|off`. Signals are computed at the check close; tickets are meant to be worked at the next open (delay cost measured in `research/idx_execution_delay.py`). `ticket.min_trade_for(nav)` scales the minimum line with the book (NAV/20, floor Rp 1M, cap Rp 5M).
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
  warning/critical ones also go out through `notify` (below).
- **Gotchas:** (1) idx.co.id is Cloudflare-fronted and **fingerprints TLS — `httpx`/`requests` get 403; `urllib` passed until
  2026-09-14 and is challenged since; `curl` (Schannel on Windows) passes**. `idx/client.py` therefore runs through a `curl`
  subprocess when one is installed (`INGEST_IDX_TRANSPORT=auto|curl|urllib`; the first call gets one 403 and the retry with the
  cookie jar passes). A challenge shows `cf-mitigated: challenge` on every path incl. robots.txt and is NOT an IP block —
  a different IP/proxy does not help, a different TLS stack does. (2) Use `127.0.0.1`, not `localhost`, in the local DSN (IPv6 `::1` hangs on the Docker
  port proxy). (3) idx.co.id serves **2020-01-02 onward only**; pre-2020 comes from the Yahoo split-only cache
  (`research/idx_ohlc_loader.py`, `yf_fetch(adjust=False)`). (4) Backfill uses the whole-market day-dump
  (`GetStockSummary?date=`) so delisted names are included; per-stock `GetTradingInfoSS` is only a cross-check.
  (5) `OpenPrice=FirstTrade=0` (2020-03-13..09-04, no pre-opening) → `open` NULL + `open_missing`, never fabricated.
  (6) Corporate actions come from IDX's `Previous` reset vs prior close; exact split ratios from listed-shares change;
  `idx.bar.adj_factor` is rewritten for earlier rows, raw prices never change. (7) A code in the day-dump but not in Daftar Saham
  (e.g. GOTOM multiple-voting shares) is `listing.status='NOT_IN_DAFTAR'`, not delisted.
  (8) **Opens before 2025 exist only for LQ45** in IDX's own data (`open_missing` on ~80 % of 2020-24 rows is the source, not a bug).
- **Datafeed collector (`idx/feed/`, migration 0029, 2026-09-21):** real-time prints + order books from the operator's OWN
  Stockbit session (`wss://wss-jkt.trading.stockbit.com/ws`, subprotocol `web`, protobuf envelope with a plain
  `#O|CODE|BID|price;orders;volume|…` body — `feed/proto.py` documents the message shapes; no protobuf dependency).
  Personal data: **never into `/pub`, never into Blackridge.** History starts the day it first ran. Tables: `idx.feed_trade`
  (every print; hypertable, compressed after 3 days) · `idx.feed_book` (top-10 each side, ≤ 1 sample/s/name, only on change)
  · continuous aggregates `idx.feed_bar_1m`, `idx.feed_book_1m` (refresh every minute) · `feed_symbol` (subscription, re-read
  every 5 min) · `feed_token` (24 h session JWT) · `feed_status` heartbeat · `feed_event` log · `feed_day` coverage audit
  (Σqty vs the official daily volume). Process: `idx feed run` (ONE websocket; asyncio receive loop + writer thread with its
  own connection and a bounded retry queue; idles outside Mon–Fri 08:40–16:20 WIB). Dead-connection detection: transport
  errors, app-level ping after 15 s silence / pong grace 13 s, and a data watchdog in continuous phases (no data 90 s →
  resubscribe, 180 s → reconnect); reconnect = backoff 1…30 s forever, fresh key + auth + re-read symbols; advisory-lock
  singleton; token-expiry warning 45 min ahead. Raw frames archived by default to `logs/idx/feed/<date>.frames.gz` (sync-flushed
  each second, 7 days) — `idx feed replay --file F` re-ingests a day after a DB outage or parser fix. Windows task **"Blackheart
  IDX feed"** (`scripts/idx-feed-task.ps1`; `-Restart` is the only correct restart — Stop-ScheduledTask leaves the python child
  alive holding the lock). **Token:** the operator
  logs in to stockbit.com and pastes the `credentialStorage` cookie at `http://127.0.0.1:8001/idx/feed/relay` (or
  `STOCKBIT_TOKEN=` in `idx-local.env` — re-read live, no restart) — needed once per week now: **headless renewal works**
  (verified 2026-09-22: `POST exodus.stockbit.com/login/refresh`, refresh token as `Authorization: Bearer`, body `{}`;
  access 24 h, refresh 7 d, both rotate). `broker.refresh_and_persist(conn=)` / `idx broker refresh` takes the newest refresh
  token of `idx-local.env` vs the relay row (`idx.feed_token`, by JWT `iat`) and writes the new pair back to both. Three
  places renew: scheduler job `token_renew` every 30 min (`broker.renew_if_needed`, when < 3 h remain), the collector
  itself 45 min before expiry (worker thread, then `load_token`), and the 20:20 broker snapshot (`config_fresh(conn=)`).
  ★ **`token_guard` every 10 min (2026-09-22) is the one that guarantees a session for the trading day**: off-session it keeps
  the 3-hour freshness rule; on a weekday up to 16:30 it demands enough validity to reach the close **16:15 + 30 min**
  (`broker.minutes_needed`, `renew_if_needed(need_until=)`) and renews from the refresh token. When the session cannot be made
  to last that long (no refresh token, or Stockbit refused it) it raises ONE critical alert (`runlog.alert_once`) and then
  **pushes the operator's phone on every run — every 10 minutes — until it is fixed**; without a session the tick feed goes
  dark and the gap-fade jobs are blind. The refresh token's own 7-day horizon is watched too (warning under 2 days), so the
  paste is asked for days ahead, never mid-session. The guard passes its own clock into `token_status` (mixing clocks was a
  real bug in the first cut).
  The relay page shows the token status and has a "Renew now" button (`POST /idx/feed/token/refresh`); pasting a bare
  *refresh* JWT (7-day lifetime) is exchanged for a full pair on the spot, and any paste carrying a refresh token is
  mirrored into `idx-local.env`. A re-login in the browser invalidates older refresh tokens — paste the cookie again if
  renewal answers 401 (alert `feed`: "token renewal failed").
  CLI `idx feed status|symbols [--liquid N|--set A,B|--disable A,B]|token [--paste FILE|-]|audit [--date]`;
  routes `GET /idx/feed/status`, `GET|PUT /idx/feed/symbols`, `POST /idx/feed/token` (service/loopback only). Scheduler:
  `feed_watch` every 5 min in-session (stale heartbeat / expired token → warning alert), `feed_audit` 20:10 (coverage < 95 %).

- **Gap-fade book (`idx/gapfade.py`, research menu 29b, 2026-09-22)** — the desk's first intraday book, PAPER ONLY (`paper_gapfade`,
  Rp 100 M, K=5, `rule='gapfade'`). Rule: a name whose **opening print** is <= -7 % against the previous close is bought at the open
  + 1 tick (deepest gaps first, slot = NAV/K) and sold into the **same** closing auction (close - 1 tick); nothing is ever held
  overnight. Jobs: `gapfade_entry` 09:00 + 09:05 retry (the opening auction prints reach the feed at ~08:58 and are the official
  open for ~90 % of names), `gapfade_exit` 15:50 (sell ticket), and `gapfade.settle` inside the evening daily chain (fills the
  exit at the official close). CLI `idx gapfade scan|entry|exit|settle|books|init`. Guards: feed coverage (>= 50 opening prints,
  else no trading + alert), stale bars, **no offer = skip** (a name locked at auto-rejection down cannot be bought — the mirror of
  the ARA trap), leftover positions swept at the next open with a warning, one entry + one exit ticket per day under the paper
  filler's advisory lock, halt respected, live books drafted not filled (two-key). ★ **The daily summary's "open" is the first
  trade of the day, not the opening auction** — on 2026-09-22 AALI's "open" printed at 10:45 — so the live book trades a stricter
  subset than the backtest (first print inside 08:55-09:10 only); the paper record measures that difference. Tests `tests/idx/test_gapfade.py`.

- **One-tap fill (`idx/fillmatch.py`, 2026-09-22)** — recording fills by hand is the desk's biggest daily chore. For each
  still-open line of an **issued** ticket the tape says what the market actually traded inside that line's limit today
  (`idx.feed_trade`, from 09:00): `propose()` returns lots + price (VWAP snapped the conservative way — a buy rounds up, a sell
  down — and never worse than the limit) with a confidence (high = the flow was >= 10x the line, medium >= 3x, low under that),
  the eligible volume, the print count and the window. It cannot know which prints were the operator's (the feed carries no
  account), so it only ever proposes; the write still goes through `ticket.fill_line` (two-key, journal, book mark). A draft,
  closed or cancelled ticket proposes nothing. Route `GET /idx/ticket/{id}/suggest`, CLI `idx suggest [--ticket N | --book B]`,
  phone: the card under the line being worked on `/m/ticket`. Tests `tests/idx/test_fillmatch.py`.

## Gotchas
- **`api/` is dead.** The served app is `workers.server:app`; the old `api/` app factory was unused. CI's `test_server_app.py` exists precisely because the old suite tested the dead app while the served app shipped broken ("CI green, served app broken").
- **Mutation routes are unauthenticated** unless `INGEST_AUTH_TOKEN` is set — never publish `/pull` or `/compute` on a public interface (the loopback+Tailscale bind is the safeguard).
- **Liquidations are not backfillable** — the `binance_liquidation` lifespan worker is the only source of those rows; don't interrupt it carelessly. Default OFF (`INGEST_LIQUIDATION_STREAM_ENABLED`).
- **`deribit_options` has no free history** — each hourly snapshot is the only copy ever captured (plant-and-accumulate). Default OFF (`INGEST_DERIBIT_OPTIONS_ENABLED`).
- **PIT discipline** (`shared/pit_guards.py`): every row is validated before insert — future event_time, inverted publisher timestamp, and out-of-window backfill are rejected and counted as `rows_rejected_pit`. FRED uses lag-aware windows so monthly series keep streaming. Feature compute refuses to carry a forward-filled value older than `max_ffill_age_hours`.
