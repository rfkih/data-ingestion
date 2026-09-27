# blackheart-ingest - IDX desk worker + crypto-era macro ingest

Python/FastAPI worker, one package `src/blackheart_ingest`, two halves. `idx/` is the live IDX (Indonesian equities) desk:
primary-source data plane into schema `idx` of the same `trading_db`, books and tickets, the Stockbit feed, ML, research;
self-scheduled and independent of the trading JVM. The rest is the crypto-era macro/market-data ingest + feature compute:
`/pull` and `/compute`, called over HTTP by the Trading JVM's `BackfillMl*` handlers and scheduled by
`MlIngestScheduleRefresher` (CRYPTO_LEGACY.md). This file: map + always-on rules; detail: table at the end.

> Part of the Blackheart workspace — topology + repo map in C:/Project/CLAUDE.md.

**Stack:** Python 3.12 · FastAPI + uvicorn · Pydantic v2 / pydantic-settings · httpx + tenacity · structlog · psycopg 3 (sync)
· pandas + numpy · fredapi · websockets · lightgbm (inference). Extras `kafka`, `html-scrape`. IDX desk:
`curl_cffi` (idx.co.id transport), `pypdf[crypto]` (annual reports), `cryptography` (FCM JWT).

## Run / test / restart
```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"          # CI installs ".[dev,kafka]"
ruff check src                    # lint
mypy src                          # type-check
pytest                            # tests
python -m blackheart_ingest.workers.server   # run server (or: blackheart-ingest-server)
python -m blackheart_ingest.idx.cli <verb>   # IDX CLI; local wrapper C:/Project/scripts/idx.sh / idx.ps1 (loads idx-local.env)
```
- Copy `.env.example` → `.env` and set `INGEST_FRED_API_KEY`. Listens on `127.0.0.1:8001` by default.
- Feed collector: restart ONLY with `C:/Project/scripts/idx-feed-task.ps1 -Restart`. Scheduler task:
  `C:/Project/scripts/idx-scheduler-task.ps1`. Both tasks: a logon trigger + a 10-minute watchdog (FEED.md).
- Safety net: `idx watchdog`, `idx backup run|restore-test|offsite`, `idx tca`, `idx combo kill`,
  `python -m blackheart_ingest.idx.snapshot verify|drift <study>` (OPS.md).
- Stream check: `GET /idx/stream/status`, `curl -sN 'http://127.0.0.1:8001/idx/stream?kinds=ops'` (ALERTS.md).

## Always-on rules and hazards
**Money, books, strategies**
- Before changing any live parameter or quoting a strategy number, read `docs/MODEL_INVENTORY.md`: binding change control
  (pre-registered study + independent spec-only replication + journal); combo books `live-fae554` / `paper-edbb01` frozen to
  2027-03-26.
- Live books are two-key: a live ticket is a draft; nothing fills one automatically. Live fills are recorded by hand
  (`idx ticket fill`, `idx book fill`); after a back-dated fill re-run `idx book mark --rebuild` (cash is anchored on the live
  `book.cash`). `fillmatch` only proposes; the write goes through `ticket.fill_line`. Paper tickets fill themselves. Respect a
  halted book.
- Paper-only engines stay paper: gap-fade book `paper_gapfade`, the online agent (`idx/agent.py`), the C1 watch
  (`idx/dt_watch.py`, no orders, no pushes). Real money is the operator's call (declared judgement rules), via draft tickets.
- Forecasts, never tickets: no book reads an `idx/ml` daily horizon until it shows a positive realised IC for months; a
  1-minute hit rate above base is worth less than the spread; never build a book on the 1d horizon. The combo `ml` sleeve's 5d
  score is under the change control above.
- The ARA watch is information, never a ticket; ARA prediction-vs-actual is measurement only, inside the operator's ARA freeze
  (no ARA books, entry rules, new screens or research menus: ARA.md). The chart screen gets nothing that forecasts a price.
- Never hand-type a performance number into the registry: a strategy with no study shows no figure.
- Daily board: bookless (never invents a position), entries only; an engine that throws shows `error` - silence and "nothing
  today" must never look the same.
- One implementation, research == live: `candidates.rank_pool`, `strategies.pick`, trend thresholds imported from `trend_book`,
  `idx/metrics.py` (the one PIT evaluator, cutoff 16:00 WIB), `ml/intraday.py` minute features (same path live and settled).
  Never fork them.
- IDX rules in `ticket` (lot 100, tick fractions, `ticket.reject_band`): verify against Peraturan II-A on change. ARB = 15 %
  flat rounded UP to the tick; a same-day/must-fill stop bands on yesterday's close, never the firing price (JATS rejects a
  stop priced under the ARB).
- Open window: no live feed for tomorrow's buy list; the feed appears only at the open (08:55-09:30) for names that already
  have a ticket; `unsubscribe()` removes only `reason='ticket'` rows, never the standing liquid set.
- `line_message` quotes the side of the book the read points at: the wrong side is a number somebody might type in.
- Gap-fade: nothing held overnight; no offer = skip (a name locked at the lower band cannot be bought); < 50 opening prints =
  no trading + alert; one entry + one exit ticket per day under the paper filler's advisory lock.
- The daily summary's "open" is the first trade, not the opening auction (AALI 2026-09-22 printed at 10:45): the live
  gap-fade trades only a first print inside 08:55-09:10.
- `/idx/books` `capital` is reconstructed from cash + every fill; the first NAV point is NOT the capital (no returns from it).

**Database and data**
- Migrations: `idx/migrations/NNNN_*.sql` + `idx.schema_history` (sha256-checked): never edit an applied file, add a new one.
  Not Flyway. JVM/equity roles get SELECT only.
- Local DSN: `127.0.0.1`, never `localhost` (IPv6 `::1` hangs on the Docker port proxy). Postgres port: C:/Project/CLAUDE.md.
- Never fabricate prices: a missing open stays NULL + `open_missing`; an index has no open (never fill it with the close); raw
  prices never change, only `idx.bar.adj_factor`.
- Opens before 2025 exist only for LQ45 (`open_missing` on ~80 % of 2020-24 rows is the source, not a bug); idx.co.id serves
  2020-01-02 onward only (pre-2020 = Yahoo split-only cache); `NOT_IN_DAFTAR` is not delisted.
- Reference-price basis = splits + rights/bonus, never cash dividends. Silver/gold are derived: `idx replay` rebuilds them.
- A partial day must never blank the desk: `candidates.build` and `pack.build` anchor on `max(idx.daily_summary.trade_date)`,
  not `max(idx.bar)`. Yahoo fallback rows (source 'yahoo') never overwrite 'idx' rows; `daily.latest_bar_date` and
  crosscheck stay IDX-only.
- idx.co.id gives `httpx`/`requests` a 403 and the BI-Rate page resets Python's TLS: a new fetcher goes through
  `idx/client.py` (`curl_cffi`) or `curl`, never plain httpx/requests.
- idx.co.id (Cloudflare) fingerprints the connection: a second 403 stops the call - never hammer (retrying feeds it). If a day
  fails: newer `INGEST_IDX_IMPERSONATE` profile -> `INGEST_IDX_PROXY` -> wait for `bar_backfill`.
- Keep Cloudflare quiet: annual reports <= 8 per run at 0.2 rps; `fin_backlog` skips the day when IDX challenges the client.
- The logos CDN answers 403, not 404, for a missing logo; five 403s in a row stop the run as pushback.
- Gates are evaluated on the audited year; TTM/quarterly warnings are for judgment, never an automatic exclusion.
- Macro series were tested as stress-detector inputs and rejected: the macro board is for reading only.
- ML labels and reference price are the book MID, not the last trade (last trade: 84 % 1-minute hit rate vs a real 70 %).
  No sklearn in the venv: metrics are scipy/numpy.
- Survivorship: names delisted 2021-2024 are largely absent from `idx.bar`; discount 120d/250d numbers.
- Accumulate-forward data cannot be bought back: feed history starts the day the collector ran, broker history only grows
  nightly (`broker_snapshot`). Don't break either.
- Broker capture: core views first (they cannot be recovered later), one request/second, stop on 401/402/429. An empty 200
  from the broker-distribution endpoint is throttling: never store empty answers.
- Crypto PIT (`shared/pit_guards.py`): rows validated before insert, rejects counted (`rows_rejected_pit`), not dropped;
  feature compute refuses a forward-filled value older than `max_ffill_age_hours`.

**Feed, tokens, secrets**
- Feed data is the operator's personal data: never into `/pub`, never into Blackridge.
- Stockbit tokens live ONLY in `idx.feed_token`; `idx-local.env` holds no Stockbit token (written only as an emergency copy
  when the DB write fails). Refresh tokens rotate, so a lost pair is a lost session; a browser re-login kills older ones.
- `token_guard` passes its own clock into `token_status` (mixing clocks was a real bug); the refresh token's 7-day horizon
  warns under 2 days.
- Killing the collector blinds the desk (no opening prints: gap-fade refuses, ARA watch sees nothing). `Stop-ScheduledTask`
  leaves the python child holding the advisory lock. A second collector that finds the lock held exits 0 on purpose: a
  non-zero exit would arm restart-on-failure every 2 minutes.
- Firebase service-account JSON (`IDX_FCM_SERVICE_ACCOUNT`): placed by the operator, never through chat or git. `idx-local.env`
  (`IDX_JWT_SECRET`, `INGEST_BPS_API_KEY`, ...) is gitignored.

**Alerts and notifications**
- Producers INSERT into `idx.alert`, never pick a channel. Scheduled checks use `runlog.alert_once` (never `runlog.alert`), a
  message stable for the whole incident, and resolve their own alert (`runlog.resolve`) when it clears.
- The alert sweep never sweeps warnings or criticals. A price level fires once until `idx levels reset CODE`.
- Book alerts reach the book owner's phones; desk alerts `IDX_OPS_NOTIFY_EMAIL`'s (unset = dropped). `kind='exec'` is never
  pushed; mutes and quiet hours apply at the phone channel only. Nothing in push raises into the job that notified.
- The SSE listener stays a thread, not a coroutine (psycopg's async mode refuses Windows' ProactorEventLoop).
  `/idx/stream/status` says `connected` false until the first subscriber: open a stream before calling it DOWN.

**Service, routes, deploy**
- Push to `master` (C:/Project repo) runs CI + auto-deploy to the VPS (gated by `vars.DEPLOY_ENABLED`, false since 2026-09-24:
  the VPS stack is off on purpose, pushes run test + build only; the desk runs on the local PC). The VPS container is
  Docker-run-managed, NOT compose: `docker compose up` creates a conflicting container (OPS.md).
- The CI deploy pulls the image BEFORE removing the old container (pull-then-rm caused a 53-min outage + lost unbackfillable
  liquidation events). To touch the live container, recreate it by hand with the same `docker run` + env_file.
- Mutation routes are unauthenticated unless `INGEST_AUTH_TOKEN` is set: never publish `/pull` or `/compute` on a public
  interface; the loopback+Tailscale bind is the safeguard, so never widen it. Research writes are `service_only`. With no
  ingest token configured (this box, tests) a credential-less loopback caller counts as an unscoped service.
- Every personal `/idx/*` route takes a `Caller` (`who.caller_of`): an account is scoped to its own
  books/tickets/journal/watchlist/phones (`own_book` -> 404). A route without it leaks one user's data to another.
- Test books stay ownerless.
- Desk-account routes `/api/v1/users/*` are open by design and outside `/idx`: they never need `X-Ingest-Token`.
- The served app is `workers.server:app`; `api/` is dead. Keep `test_server_app.py`: the old suite tested the dead app while
  the served app shipped broken.
- Liquidation stream and `deribit_options` snapshots cannot be backfilled: don't interrupt them.
- `/idx/stream` hangs a FastAPI `TestClient` forever: tests call the route coroutine directly.
- PowerShell: quote the comma list (e.g. `idx logos --codes A,B`).

## Module map (`src/blackheart_ingest/`)
- `workers/server.py` served app; `sources/`, `features/`, `inference/`, `schemas/` crypto-era
- `idx/` (`<name>.py`): cli, scheduler (CLI, jobs) · client, etl, publish, jobs/, migrations/ (bronze→silver→
  `market_data`) · fin_parse, fin_store, annual, macro, news, consensus, logos (fundamentals, macro, news) · feed/, broker
  (feed, tokens, broker capture) · book, ticket, fillmatch, levels, openwindow (books, tickets, fills) · combo_book,
  gapfade, trend_book · metrics, candidates, strategies, overlay, registry, signalboard (strategies) · ml/, agent, ara ·
  runlog, stream, notify, push, prefs, signals (alerts, SSE, push) · who, accounts, chart · research_store, pack, card,
  dt_watch, snapshot (research) · killrules, risk, regime_monitor, intents (MODEL_INVENTORY.md)

## Where the detail lives (`docs/agent-context/`)
| file | read it when |
|---|---|
| [ARCHITECTURE.md](docs/agent-context/ARCHITECTURE.md) | layout, routes, IDX CLI, callers/scoping, accounts, chart, v3 web routes |
| [OPS.md](docs/agent-context/OPS.md) | deploy, restarts, env settings, safety net, tests |
| [JOBS.md](docs/agent-context/JOBS.md) | a scheduled job; what runs when (WIB) |
| [DATA.md](docs/agent-context/DATA.md) | idx.co.id client/Cloudflare, backfill, Yahoo fallback, schema, workbooks, annual, macro, news, logos |
| [FEED.md](docs/agent-context/FEED.md) | tick feed, its Windows task, Stockbit tokens, broker capture |
| [ALERTS.md](docs/agent-context/ALERTS.md) | alerts, the SSE stream, phone push |
| [BOOKS_TICKETS.md](docs/agent-context/BOOKS_TICKETS.md) | books, tickets, tick/ARA/ARB rules, levels, fills, open window, combo, gap-fade |
| [STRATEGIES.md](docs/agent-context/STRATEGIES.md) | candidates, overlays + regime gate, strategy catalog, registry, daily board |
| [ML.md](docs/agent-context/ML.md) | prediction desk (`idx/ml/`), online agent |
| [ARA.md](docs/agent-context/ARA.md) | ARA watch, touches, prediction vs actual, the ARA freeze |
| [RESEARCH.md](docs/agent-context/RESEARCH.md) | study store, evidence, pack, C1 watch, study/menu index |
| [CRYPTO_LEGACY.md](docs/agent-context/CRYPTO_LEGACY.md) | crypto-era sources, features, inference, PIT guards |
| [docs/MODEL_INVENTORY.md](docs/MODEL_INVENTORY.md) | before changing a live parameter or quoting a strategy number |
