# blackheart-inference

FastAPI ML inference sidecar for Blackheart: loads trained `model_registry` artifacts, reads `feature_values`, runs `Booster.predict()`, and writes `signal_history` rows the trading JVM consumes.

> Part of the Blackheart workspace — topology + repo map in C:/Project/CLAUDE.md. Lives in the root repo (not its own git repo).

## What it does
- Resolves a signal → model → content-addressed `.pkl` artifact → feature vector → prediction, then UPSERTs into `signal_history` (`source` stamped `stream` | `catchup_scan` | `historical_replay`, a V66 CHECK enum).
- Feature fetch mirrors blackheart-train's loader: per-bar features keyed on `(symbol, interval)`; GLOBAL/macro features (empty symbol+interval) are forward-filled onto the bar grid with a per-feature hour cap, so the serving vector matches training (train parity).
- Consumers: the trading JVM's `MLSignalService` + `MLRegimeGateGuard` read `signal_history`. Direct callers are the research orchestrator (`/inference/run`, `/inference/backfill` proxies) and the optional streaming worker — never the researcher directly. Loopback-only.
- Refuses to serve on retired/rejected signal-or-model, NULL artifact sha, unregistered feature, missing feature_values, oversized backfill (413), or artifact sha mismatch on disk (502 `artifact_corrupt`).

## Tech stack
Python 3.12, FastAPI + uvicorn (single worker — model bytes live in-process), asyncpg, pydantic / pydantic-settings, httpx, structlog, LightGBM, NumPy. Tests: pytest + pytest-asyncio + respx.

## Layout
- `src/blackheart_inference/api/` — routers: `health` (`/healthz`, `/readyz`), `inference` (`/inference/run`, `/inference/backfill`), `streaming` (`/streaming/status`), `batch`, `metrics`, `deps`.
- `src/blackheart_inference/services/` — `artifact_loader` (sha round-trip + tamper check), `predictor` (feature-order + predict), `streaming` (asyncio gap-fill worker).
- `src/blackheart_inference/repo/` — DB access: `features`, `models`, `signals`.
- `src/blackheart_inference/infra/db.py` — asyncpg pool + JSONB-as-dict codec + `health_probe`.
- `src/blackheart_inference/monitoring/` — `latency_tracker`.
- `settings.py` — `INFERENCE_*` pydantic settings + `assert_prod_safe()`. `__main__.py` — uvicorn launcher.
- `tests/` — ~10 test modules (auth, artifact loader, predictor, batch, features repo, readyz, streaming, latency, metrics, smoke). Good coverage; DB-touching paths not exercised here.

## Build / test / run
```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"   # editable + dev extras
Copy-Item .env.example .env                              # set INFERENCE_AUTH_TOKEN, INFERENCE_DB_DSN
.\.venv\Scripts\python.exe -m pytest -q                  # tests
.\.venv\Scripts\python.exe -m blackheart_inference       # serve on 127.0.0.1:8000
```
No console_scripts entry point — run via `python -m blackheart_inference`. Key env (`INFERENCE_` prefix): `INFERENCE_PORT` (8000), `INFERENCE_DB_DSN`, `INFERENCE_ARTIFACT_DIR`, `INFERENCE_AUTH_TOKEN`, `INFERENCE_STREAMING_ENABLED`, `INFERENCE_PROFILE` (`prod` enables `assert_prod_safe()`).

## Deploy
- CI/CD is the **root repo's** `.github/workflows/blackheart-inference-ci.yml` (triggers on `blackheart-inference/**`). Job chain: pytest (strict — blocks on failure) → build + push GHCR image `ghcr.io/rfkih/data-ingestion/blackheart-inference` (`<sha8>` + `latest`) → SSH deploy to VPS via `docker run` (gated on `DEPLOY_ENABLED`), with a `/readyz` healthcheck + auto-rollback to the prior image.
- VPS container: published `127.0.0.1:8000:8000`, network `blackheart_default`, artifacts mounted `-v /home/starsky/blackheart-artifacts:/artifacts:ro`, secrets via `--env-file /home/starsky/blackheart/inference.env` (mode 600).
- CRED-ROTATION CAVEAT: an earlier version committed the prod auth token + DB password inline; secrets were moved to the host-side `inference.env`. Treat the old token/DB password (still in git history) as compromised — rotate, do not reuse.

## Gotchas
- `/readyz` is honest: returns **HTTP 503** when DB or `artifact_dir` is unreachable. The CI deploy gate and compose healthcheck branch on the status code, so a degraded body behind a 200 would tag a broken deploy as healthy — never soften the code.
- Streaming worker is an asyncio task started from the lifespan hook, gated by `INFERENCE_STREAMING_ENABLED` (**default OFF**). It finds gaps between `MAX(signal_history.ts)` and latest `feature_values` per active/shadow signal and loops back to its own `/inference/backfill`; per-target exponential backoff, refuses gaps over `streaming_max_gap_hours` (24h). (README's "Not built" entry for this is stale — it exists in `services/streaming.py`.)
- Artifact dir must be **mounted and populated** — empty dir means every backfill 502s (CI fails the deploy if zero `.pkl` files found). VPS path is `/home/starsky/blackheart-artifacts` (the old `blackheart-train/artifacts` path was wrong).
- asyncpg JSONB is registered as dict — pass dicts to `$N` params, do not `json.dumps` first.
