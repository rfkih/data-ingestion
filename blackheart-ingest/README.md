# blackheart-ingest

Python service that pulls macro / sentiment / on-chain data from free external
sources into the Blackheart Postgres `*_raw` tables. Called by the Trading
JVM's `BackfillMl*` handlers via HTTP; also runs as a scheduled live-ingest
worker.

Part of Phase 1 / M2 of the ML/sentiment integration. See
`../C--Project/memory/project_ml_blueprint.md` for the full architecture.

## Sources

| Source | Status | Auth | Notes |
|---|---|---|---|
| `alternative_me` | ✅ live | None | Fear & Greed Index. Simplest source. |
| `fred` | ✅ live | Free API key | FRED + ALFRED vintage for revision-prone series |
| `coingecko` | ✅ live | None | Free tier: BTC/ETH dominance + total mcap + per-coin price/mc/vol history |
| `defillama` | ✅ live | None | Per-stablecoin (USDT/USDC/…) circulating USD + per-chain TVL |
| `coinmetrics` | ✅ live | None | Community tier daily on-chain metrics (FlowOutNative, AdrActCnt, etc.) |
| `binance_macro` | ✅ live | None | Public futures macro: funding rate + open interest + L/S ratio + taker buy/sell |
| `deribit` | ✅ live | None | DVOL 30d option-implied vol index (BTC/ETH); deep free history via `get_volatility_index_data` |
| `deribit_options` | ✅ live (forward-accumulating) | None | Option-surface SKEW + term structure (BTC/ETH): 25Δ risk reversal, ATM IV near/30d, term spread. **No free historical backfill** — plant-and-accumulate hourly snapshot. Behind `INGEST_DERIBIT_OPTIONS_ENABLED` (default OFF). |
| `forexfactory` | ✅ live (MVP) | None | faireconomy.media current-week JSON mirror; historical lookups deferred |

Stub sources have Java handlers that simulate progress but don't call this
service yet. The migration path is: implement the Python source module,
update the matching Java handler to delegate via HTTP, drop the stub
simulation. Same `historical_backfill_job` row, same UI.

## Setup

```powershell
# From repo root:
cd C:\Project\blackheart-ingest

# Create venv
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install (editable)
pip install -e ".[dev]"

# Copy env template + fill in FRED_API_KEY
copy .env.example .env
notepad .env

# Run the HTTP server
.\.venv\Scripts\blackheart-ingest-server.exe
# OR
python -m blackheart_ingest.workers.server
```

The HTTP server listens on `127.0.0.1:8001` by default (loopback only;
the Docker image overrides host to `0.0.0.0` INSIDE the container and the
deploy publishes it on loopback + Tailscale only — the mutation routes
carry no auth unless `INGEST_AUTH_TOKEN` is set, so never publish them
to a public interface). The
Trading JVM `BackfillMl*` handlers POST to it.

## Endpoints

```
GET  /healthz                        # liveness probe
GET  /sources                        # which source modules are registered
POST /pull/{source}                  # one-shot pull, blocks until complete
  body: {"start": "YYYY-MM-DDTHH:MM:SS", "end": "...", "symbol": "BTCUSDT|null", "config": {...}}
  returns: {"source": "...", "rows_inserted": N, "rows_rejected_pit": M, ...}
```

## Liquidation stream (always-on worker)

`sources/binance_liquidation.py` accrues Binance USDT-M futures force
liquidations from `wss://fstream.binance.com/market/ws/!forceOrder@arr` into
`macro_raw` (source=`binance_liquidation`, series
`binance_liquidation_<symbol_lower>`, value = notional USDT, ALL symbols).
Liquidations are **not backfillable**, so the worker runs as an asyncio task
inside the server lifespan with auto-reconnect (exponential backoff +
jitter); every disconnect window is logged at WARN as permanently lost.

Default **OFF** — deploying is inert until the operator sets:

```
INGEST_LIQUIDATION_STREAM_ENABLED=true      # master switch
INGEST_LIQUIDATION_WS_URL=...               # optional override
INGEST_LIQUIDATION_FLUSH_MAX_ROWS=200       # batch insert size trigger
INGEST_LIQUIDATION_FLUSH_SECONDS=5          # batch insert time trigger
```

Health: `GET /liquidation/status` returns connected / last_event_at /
events_written / reconnect_count etc. It is NOT a `/pull/{source}` source
(no `fetch`), so it does not appear in `GET /sources`.

## Deribit options skew (forward-accumulating snapshot)

`sources/deribit_options.py` snapshots the live Deribit option surface each
hour and writes its *shape* into `macro_raw` (source=`deribit_options`). Unlike
the DVOL index (source=`deribit`, deep free history), **per-strike option IV has
no free historical backfill** — each hourly snapshot is the only copy we will
ever have, so this is a plant-and-accumulate feed: research history starts
building the moment it is enabled. DVOL's behaviour is untouched.

Series written per currency (BTC, ETH), `symbol=NULL`, hourly cadence:

```
deribit_rr25_<cur>_30d     25Δ risk reversal (put-wing IV − call-wing IV), ~30d expiry. >0 = downside fear
deribit_atm_iv_<cur>_near  ATM mark_iv, nearest expiry >= ~1 day out
deribit_atm_iv_<cur>_30d   ATM mark_iv, expiry nearest 30 days
deribit_term_spread_<cur>  atm_iv_30d − atm_iv_near (vol term-structure slope)
```

It is a normal `/pull/{source}` source (appears in `GET /sources`), so it is
**scheduled exactly like DVOL** — an hourly `ml_ingest_schedule` row for
`source=deribit_options` driven by the trading JVM's `MlIngestScheduleRefresher`
calls `POST /pull/deribit_options`. The `[start, end]` window is ignored (a live
snapshot always captures "now", floored to the hour).

Default **OFF** — deploying the code is inert until the operator sets:

```
INGEST_DERIBIT_OPTIONS_ENABLED=true     # master switch; until set, /pull writes nothing
```

The 25Δ strikes are approximated geometrically (`F·exp(±0.6745·σ_atm·√T)`) and
snapped to the nearest listed strike per wing — `get_book_summary_by_currency`
returns no per-instrument greeks. If a wing is too thin or an expiry illiquid,
that series is skipped for the run (nothing written) rather than zeroed. See the
module docstring for the full derivation and Deribit's single-IV-per-strike
quirk.

## Development

```powershell
# Lint
ruff check src

# Tests
pytest

# Type-check
mypy src
```
