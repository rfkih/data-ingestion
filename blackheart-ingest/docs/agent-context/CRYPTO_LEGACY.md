# Crypto-era ingest (the non-`idx/` part of the package)

Read when you touch `sources/`, `features/`, `inference/`, `workers/compute_features.py`, `workers/inference_backfill.py`, the
Kafka pipeline, `/pull` or `/compute`, or `feature_values` / `macro_raw` / `signal_history`. Map: [../../CLAUDE.md](../../CLAUDE.md).
Package layout of these modules: [ARCHITECTURE.md](ARCHITECTURE.md). Deploy (CI, VPS `docker run`): [OPS.md](OPS.md).

The original one-line description of this repo, which is this half:
Python/FastAPI service that pulls macro, options, and market data from free external sources into Postgres and computes macro
`feature_values`; called over HTTP by the Trading JVM's `BackfillMl*` handlers and scheduled by `MlIngestScheduleRefresher`.

## What it does
- **Sources in** (all free, mostly no-auth): FRED + ALFRED vintages, Deribit DVOL + Deribit option-surface skew
  (`deribit_options`), Binance spot (`binance_spot`), Binance futures macro (funding / OI / L-S / taker), Binance forceOrder
  liquidation stream, Binance orderbook, CoinMetrics, DefiLlama, CoinGecko, alternative.me Fear&Greed, ForexFactory.
- **Tables out:** raw rows → `macro_raw` (+ source-health rows); computed macro features → `feature_values` (keyed to
  `feature_registry`). PIT-rejected rows are counted, not silently dropped.
- **Consumers:** the Trading/Research JVMs read `feature_values`; the inference sidecar (`inference/`, separate worker) reads
  features and writes `signal_history`.

## Optional extras
`kafka` (aiokafka + python-snappy, used in the Docker image), `html-scrape` (bs4 + lxml, ForexFactory HTML fallback, currently
unused). CI installs ".[dev,kafka]".

## Gotchas
- **Liquidations are not backfillable** — the `binance_liquidation` lifespan worker is the only source of those rows; don't
  interrupt it carelessly. Default OFF (`INGEST_LIQUIDATION_STREAM_ENABLED`).
- **`deribit_options` has no free history** — each hourly snapshot is the only copy ever captured (plant-and-accumulate).
  Default OFF (`INGEST_DERIBIT_OPTIONS_ENABLED`).
- **PIT discipline** (`shared/pit_guards.py`): every row is validated before insert — future event_time, inverted publisher
  timestamp, and out-of-window backfill are rejected and counted as `rows_rejected_pit`. FRED uses lag-aware windows so monthly
  series keep streaming. Feature compute refuses to carry a forward-filled value older than `max_ffill_age_hours`.
- **Mutation routes are unauthenticated** unless `INGEST_AUTH_TOKEN` is set, and **`api/` is dead**: see
  [ARCHITECTURE.md](ARCHITECTURE.md).
