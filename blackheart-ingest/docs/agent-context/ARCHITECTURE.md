# Architecture - package layout, the served app, the IDX desk surface, callers and accounts, screens

Read when you need the package layout, where a route or CLI verb lives, how a caller is scoped (account vs service), the desk
accounts, or the chart/stock screens the web app reads. Map: [../../CLAUDE.md](../../CLAUDE.md).

## Package layout (`src/blackheart_ingest/`)
- `workers/server.py` — **the SERVED FastAPI app (`workers.server:app`)**; entry point `blackheart-ingest-server`. This is what
  Docker runs.
- `workers/compute_features.py` — `blackheart-ingest-compute` one-shot/loop feature compute CLI.
- `workers/inference_backfill.py` — `blackheart-ingest-inference` sidecar backfill (loads model artifacts, writes
  `signal_history`).
- `workers/bar_event_consumer.py`, `feature_stream.py` — Kafka bar-close → feature-compute pipeline.
- `sources/` — one module per source; `server._KNOWN_SOURCES` maps `/pull/{source}` names to modules. `binance_liquidation.py`
  is a lifespan worker (not a `/pull` source).
- `features/` — `definitions.py` (declarative `FeatureDef`s), `compute.py`, `persistence.py`.
- `inference/` — ML sidecar (registry / artifacts / persist / api).
- `shared/` — `settings.py`, `db.py`, `pit_guards.py`, `binance_http.py`, `logging_setup.py`.
- `schemas/` — Kafka event models. `api/` — **DEAD** (no live modules; the old unused app factory lived here).
- `tests/` — pytest suite incl. `test_server_app.py` (boots the served app with its lifespan).
- `idx/` — the IDX desk (this file and the other topic files). The crypto-era pieces above (sources, features, inference,
  Kafka): [CRYPTO_LEGACY.md](CRYPTO_LEGACY.md).

**`api/` is dead.** The served app is `workers.server:app`; the old `api/` app factory was unused. CI's `test_server_app.py`
exists precisely because the old suite tested the dead app while the served app shipped broken ("CI green, served app broken").

## Served routes (core)
- Key routes: `GET /health` (and `/healthz`), `GET /sources`, `GET /features`, `POST /pull/{source}`,
  `POST /compute/{feature}/v/{version}`, `POST /compute/incremental`, `GET /liquidation/status`.
- **Mutation routes are unauthenticated** unless `INGEST_AUTH_TOKEN` is set — never publish `/pull` or `/compute` on a public
  interface (the loopback+Tailscale bind is the safeguard).
- The IDX routes (`/idx/*`) are listed in each topic file next to the feature they serve.

## IDX data plane (`src/blackheart_ingest/idx/`, phase 0 — 2026-09-12)
- Primary-source Indonesian equities (idx.co.id) → schema **`idx`** in the same `trading_db`; self-scheduled,
  **independent of the trading JVM**. Spec: `C:/Project/docs/superpowers/specs/2026-09-12-idx-data-platform-design.md`;
  build plan: `docs/superpowers/plans/2026-09-12-idx-platform-build-plan.md`.
- Layers (bronze/silver/gold), schema and migrations: [DATA.md](DATA.md). Scheduler jobs: [JOBS.md](JOBS.md).
- **CLI:** `python -m blackheart_ingest.idx.cli` — `migrate | status | universe | daily --date | index --date |
  backfill --from --to [--index] | replay | publish [--full] | announce | features [--publish] | fin discover|download|parse |
  dividends | card CODE | candidates [--as-of D] | answers [--score] | crosscheck | run-scheduler`. Local wrapper:
  `C:/Project/scripts/idx.sh` / `idx.ps1` (loads `idx-local.env`, gitignored). Later verbs (feed, broker, book, ticket,
  combo, gapfade, ml, agent, ara, ...) are listed in their topic files.

## Many users, each with their own desk (`idx/who.py`, migration 0026, 2026-09-17)
- Columns: `idx.book.owner_id/label/rule/trend_variant/archived_at`, `idx.decision.user_id`, `idx.watchlist (user_id, code)`,
  `idx.push_device.user_id`, `idx.app_user.plan/accepted_terms_at`.
- Every personal `/idx/*` route takes a `Caller` (`who.caller_of`):
  - a signed-in account (the app's proxy forwards the session JWT as `Authorization: Bearer`; verified with `IDX_JWT_SECRET`)
    is scoped to its own books/tickets/journal/watchlist/phones (`own_book` -> 404 for anyone else's);
  - a service holding the ingest token (CLI, scheduler, agent) is unscoped, or scoped to one account with
    `X-Idx-User: <email>` (the nightly agent sends `IDX_AGENT_USER`);
  - with no ingest token configured (this box, tests) a credential-less loopback caller counts as an unscoped service.
- Research reads stay open; research writes (pack build/answer, evidence, macro pull, overlay check) are `service_only` (403 for
  an account).
- Books per person (`POST /idx/books`, archive, list): [BOOKS_TICKETS.md](BOOKS_TICKETS.md). Notifications per person:
  [ALERTS.md](ALERTS.md).
- Existing books (`live`, `paper`, `trend_live`, `paper_trend`) were assigned to the first account (the operator). Test books
  stay ownerless. Tests: `tests/idx/test_multiuser.py`.

## Desk accounts (`idx/accounts.py`, migration 0015 `idx.app_user`, 2026-09-13)
- The Papan app's users (the app is now Blackridge). Anyone can register; scrypt password hashes; 30-day HS256 sessions signed
  with `IDX_JWT_SECRET` (base64, `idx-local.env`; the app holds the same value as `JWT_SECRET`); failed sign-ins throttled per
  email.
- Served at `/api/v1/users/register|login|me|logout` in the trading JVM's user-API shape (ResponseDto envelope,
  `blackheart-token` cookie), so the app's `INTERNAL_TRADING_URL` points at this worker and would work unchanged against the JVM.
- These routes are open by design (loopback bind + the app in front); they are not under `/idx` and never need `X-Ingest-Token`.

## One name on one screen (`idx/chart.py`, 2026-09-24)
- Routes `GET /idx/chart/{code}`, `/chart/{code}/depth`, `/chart/codes`: adjusted daily candles from `idx.bar`, one-minute
  candles from `idx.feed_bar_1m` (subscribed names only, history starts when the collector first ran), the ten levels each side
  from `idx.feed_book`, and `trend_state` - the deployed trend rule's READING of the name.
- Every threshold is imported from `trend_book` (HI_N, MA_N, VOL_N, VOL_X, TRAIL) rather than restated, so the screen cannot
  drift away from the book; a test asserts that.
- Nothing here forecasts a price and nothing should be added that does: the queue imbalance is returned next to `spread_bps`
  because study #74 measured its lead at about half a tick against a ~79 bps round trip, which makes it a fill-timing readout
  and not a signal.
- A name outside the tick feed returns empty intraday and depth with a `why`, never an error.
- `GET /idx/chart/index` is the same for the market itself (COMPOSITE daily + the feed's `IHSG` minute bars + the 200-day average
  and `regime_on`). An index has **no open** in the IDX payload - `open` is NULL on all 1,618 COMPOSITE rows - so it is passed
  through as null and the screen draws a line; filling it with the close would put a candle on the page claiming the market
  opened where it closed.

## Web routes for the v3 screens
- `GET /idx/tickets?book=&days=`, `/idx/combo/{watch,scorecard,positions,strategies}`, `/idx/combo/catalog` (bookless: the
  Add-strategy sheet and the New-portfolio modal), `/idx/search`, `/idx/stock/{code}`.
- `/idx/books` also returns `capital` (what was put in, reconstructed from cash + every fill - the first NAV point is NOT the
  capital), `halted_at`, `halt_reason` and `strategies` (a combined portfolio's live sleeve count).
- Other screens' routes: the daily board and registry ([STRATEGIES.md](STRATEGIES.md)), the alert stream
  ([ALERTS.md](ALERTS.md)), logos ([DATA.md](DATA.md)), ML and ARA ([ML.md](ML.md), [ARA.md](ARA.md)).
