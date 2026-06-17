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

## Gotchas
- **`api/` is dead.** The served app is `workers.server:app`; the old `api/` app factory was unused. CI's `test_server_app.py` exists precisely because the old suite tested the dead app while the served app shipped broken ("CI green, served app broken").
- **Mutation routes are unauthenticated** unless `INGEST_AUTH_TOKEN` is set — never publish `/pull` or `/compute` on a public interface (the loopback+Tailscale bind is the safeguard).
- **Liquidations are not backfillable** — the `binance_liquidation` lifespan worker is the only source of those rows; don't interrupt it carelessly. Default OFF (`INGEST_LIQUIDATION_STREAM_ENABLED`).
- **`deribit_options` has no free history** — each hourly snapshot is the only copy ever captured (plant-and-accumulate). Default OFF (`INGEST_DERIBIT_OPTIONS_ENABLED`).
- **PIT discipline** (`shared/pit_guards.py`): every row is validated before insert — future event_time, inverted publisher timestamp, and out-of-window backfill are rejected and counted as `rows_rejected_pit`. FRED uses lag-aware windows so monthly series keep streaming. Feature compute refuses to carry a forward-filled value older than `max_ffill_age_hours`.
