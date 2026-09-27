# Ops - deploy, the safety net, restarts, env settings, tests

Read when you deploy, restart something, set or look up an env setting, or look for the tests of an area.
Map: [../../CLAUDE.md](../../CLAUDE.md) (it carries the everyday build/test/run commands). Alerts and notification policy:
[ALERTS.md](ALERTS.md).

## Deploy
- Has its **own CI** (`C:/Project/.github/workflows/blackheart-ingest-ci.yml`, root workspace — not inside this repo): push to
  `master` runs pytest + a served-app smoke-boot, builds/pushes the GHCR image, then auto-deploys to the VPS (gated by
  `vars.DEPLOY_ENABLED`) with a healthcheck + auto-rollback.
- **Docker-run-managed on the VPS — NOT compose.** The container is created via `docker rm -f` + `docker run -d --name
  blackheart-ingest --network blackheart_default --env-file /home/starsky/blackheart/ingest.env -p 127.0.0.1:8001:8001 -p
  100.112.13.126:8001:8001` (loopback + Tailscale only).
- A `docker compose up` would create a conflicting container — recreate by hand with the same `docker run` + env_file if you
  must touch it live.
- CI pulls the image BEFORE removing the old container (a pull-then-rm ordering bug once caused a 53-min outage + lost
  unbackfillable liquidation events).
- Server bind: `127.0.0.1:8001` (loopback) by default; the Docker image forces host `0.0.0.0` + port `8001` internally.

## Ops safety net (2026-09-26)
- `idx watchdog` (own Windows task, `C:/Project/scripts/idx-watchdog-task.ps1`), `idx backup run|restore-test|offsite`, `idx tca`,
  `idx combo kill`, `python -m blackheart_ingest.idx.snapshot verify|drift <study>`.
- Their schedules and what reaches the operator: the monitoring map in [../MODEL_INVENTORY.md](../MODEL_INVENTORY.md).

## Windows tasks and restarts
- "Blackheart IDX feed" (`C:/Project/scripts/idx-feed-task.ps1`): `-Restart` is the only correct restart; logon + 10-minute watchdog;
  a second collector exits 0 on purpose (a non-zero exit would arm restart-on-failure every 2 minutes). Full story:
  [FEED.md](FEED.md).
- "Blackheart IDX scheduler" (`C:/Project/scripts/idx-scheduler-task.ps1`): same watchdog. Jobs: [JOBS.md](JOBS.md).
- The stream listener and its checks (`/idx/stream/status`, `ops/stream_load.py`): [ALERTS.md](ALERTS.md).

## Env settings named in these docs
Local values live in `idx-local.env` (gitignored; loaded by `C:/Project/scripts/idx.sh` / `idx.ps1`) and `.env`
(from `.env.example`); on the VPS in `/home/starsky/blackheart/ingest.env`.

| setting | meaning | detail |
|---|---|---|
| `INGEST_FRED_API_KEY` | FRED (crypto-era sources and IDX macro) | [DATA.md](DATA.md) |
| `INGEST_BPS_API_KEY` | BPS App ID (`key` parameter) | [DATA.md](DATA.md), [ML.md](ML.md) |
| `INGEST_IDX_BRONZE_DIR` | bronze archive root | [DATA.md](DATA.md) |
| `INGEST_IDX_TRANSPORT`, `INGEST_IDX_IMPERSONATE`, `INGEST_IDX_PROXY` | idx.co.id transport, impersonation profile, recovery proxy | [DATA.md](DATA.md) |
| `INGEST_AUTH_TOKEN` | without it mutation routes are unauthenticated | [ARCHITECTURE.md](ARCHITECTURE.md) |
| `IDX_JWT_SECRET` | session JWT secret shared with the app (`JWT_SECRET`) | [ARCHITECTURE.md](ARCHITECTURE.md) |
| `IDX_AGENT_USER` | account the nightly agent acts for (`X-Idx-User`) | [ARCHITECTURE.md](ARCHITECTURE.md) |
| `IDX_OPS_NOTIFY_EMAIL` | whose phones get desk alerts (unset = dropped) | [ALERTS.md](ALERTS.md) |
| `IDX_FCM_SERVICE_ACCOUNT` | path of the Firebase service-account JSON (placed by the operator, never through chat or git) | [ALERTS.md](ALERTS.md) |
| `IDX_TELEGRAM_*` (`IDX_TELEGRAM_TOKEN`/`_CHAT`) | optional Telegram channel | [ALERTS.md](ALERTS.md) |
| `INGEST_LIQUIDATION_STREAM_ENABLED`, `INGEST_DERIBIT_OPTIONS_ENABLED` | crypto-era plant-and-accumulate workers, default OFF | [CRYPTO_LEGACY.md](CRYPTO_LEGACY.md) |
| Stockbit tokens | NOT env: only in `idx.feed_token` (env = emergency copy) | [FEED.md](FEED.md) |

## Tests by area
- `tests/` pytest suite; `test_server_app.py` boots the served app with its lifespan (why: [ARCHITECTURE.md](ARCHITECTURE.md)).
- `tests/idx/test_multiuser.py` (callers, scoping) · `tests/idx/test_stream.py` (SSE; calls the route coroutine directly, never
  `TestClient`) · `tests/idx/test_openwindow.py` · `tests/idx/test_fillmatch.py` · `tests/idx/test_gapfade.py` ·
  `tests/idx/test_combo_book.py` (11) · `tests/idx/test_signalboard.py` · `tests/idx/test_registry.py` ·
  `tests/idx/test_broker.py` (wide capture section) · `tests/idx/test_ml.py` (32) · `tests/idx/test_ara.py` ·
  `tests/idx/test_dt_watch.py`. Test books stay ownerless.
