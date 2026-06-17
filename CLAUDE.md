# Blackheart — Workspace Map (start here)

This directory (`C:/Project`) is **both** a git repo **and** the umbrella workspace for the
Blackheart algorithmic-trading platform. An agent landing here should read this file first,
then jump to the specific repo's `CLAUDE.md`.

> **Two things share this folder.** `C:/Project` the *git repo* (the "data-plane" repo) versions
> `blackheart-inference/`, `blackheart-ingest/`, the workspace config (`.claude/`,
> `docker-compose.yml`, `monitoring/`, `scripts/`), and CI for those services. The sibling
> service repos below each have their **own `.git`** and are gitignored here — edits to them are
> committed/pushed in *their* repo, not this one.

## Repo map

| Directory | Own git repo? | Role | Stack | Port | Its CLAUDE.md |
|---|---|---|---|---|---|
| `blackheart-trading-engine/` | yes | Live trading JVM — Binance, orders, owns Postgres schema + Flyway | Java 21 / Spring Boot | 8080 | ✅ + `docs/agent-context/` (20 files) |
| `blackheart-trading-engine/` (research profile) | — | Research/backtest JVM (same codebase, `research` profile) | Java | 8081 | (same repo) |
| `blackheart-research-orchestrator/` | yes | Agent-facing research API (tick loop, gates, queue) | Python / FastAPI | 8082 | ✅ |
| `blackridge-frontend/` | yes | Operator dashboard | Next.js 14 / TS | 3000 | ✅ + `docs/agent-context/` (5 files) |
| `blackheart-ingest/` | no (this repo) | Macro/sentiment + market-data ingest, feature compute | Python | — | ✅ |
| `blackheart-inference/` | no (this repo) | ML inference sidecar (reads model_registry, writes signal_history) | Python / FastAPI | 8000 | ✅ |
| `blackheart-train/` | yes | ML training worker (feature_values → LightGBM artifacts) | Python | — | ✅ |
| `blackheart-exchange-gateway/` | yes | Binance/exchange connectivity gateway (`blackheartjs`) | Node / TS | 8088 | ✅ |
| `superpowers/` | yes | Claude Code skills/plugins (external OSS, not platform code) | — | — | ✅ |

Infra (local `docker-compose.yml`, 22 services): Postgres/TimescaleDB `5432` (+ standby `5434`),
Redis `6379`, VictoriaMetrics `8428`, Grafana, postgres-exporter `9187`.

`research-orchestrator/` (no "blackheart-" prefix) is an **abandoned stub** — the real service is
`blackheart-research-orchestrator/`. Do not edit the stub.

## Service topology & data flow

```
Binance REST/WS
   │
   ├─► blackheart-exchange-gateway (:8088) ──► trading JVM
   │
   ▼
[ingest] ──► Postgres/Timescale (:5432) ◄── [train] writes model artifacts
   │            ▲   │
   │            │   ├─► trading JVM (:8080)  ── live orders, owns schema/Flyway
   │            │   ├─► research JVM (:8081)  ── backtests
   │            │   └─► inference (:8000)     ── reads features → writes signal_history
   ▼            │
[features] ─────┘
                 research-orchestrator (:8082) ── drives the research tick loop (agent front door)
                 frontend (:3000) ── reads trading JVM (8080) + research JVM (8081) via proxy
```

## Deploy model

- **Prod = VPS `202.74.75.3`** (Tailscale `100.112.13.126`, user `starsky`). All services run as
  Docker Compose on the VPS. Env lives in `/etc/blackheart/*.env`.
- **Every prod deploy = push to that repo's `master`** → GitHub Actions builds → GHCR → VPS pull,
  with auto-rollback. `manage.ps1` is local-dev only. **Pushing THIS repo's master triggers the
  `blackheart-inference` + `blackheart-ingest` CI/deploy workflows** (`.github/workflows/`).
- **Local full stack:** `docker compose up` (+ `docker-compose.override.yml`). See each repo's
  `docs/agent-context/COMMANDS.md` for build/test/run.

## Git workflow (all repos)

- Work on `dev` or a feature branch; merge to `master` only after tests pass; deploy follows the
  master push.
- A behind-origin branch is a chore, not a blocker — rebase onto `origin/master`.
- **Apply every prod change to `dev` too** (keep `dev` from drifting).
- Commit/push only when the operator asks.

## Where to start

1. **Persistent memory** is the source of truth for project state, decisions, and gotchas:
   `C:/Users/rifki/.claude/projects/C--Project/memory/MEMORY.md` (read-first index).
2. **Per-repo entry points:** open the target repo's `CLAUDE.md`; the deep detail lives in its
   `docs/agent-context/` (architecture, migrations, commands, strategies, schema, conventions).
3. **Research lifecycle** is driven through `blackheart-research-orchestrator` (port 8082) — see
   its `CLAUDE.md` for the agent contract; the `.claude/agents/quant-*` defs implement the loop.

## Workspace hygiene rules

- **Secrets never commit:** `*.env`, `sshkey*.pem`, `*.dump`, `*.sql` backups are gitignored —
  keep it that way. Real env lives on the VPS in `/etc/blackheart/`.
- **Scratch stays out of git:** agent/research working files go under `research-scratch/`, `.rtmp/`,
  `tmp/`, or the `.research_run_state*`/`tmp_*` patterns — all gitignored. Don't commit them.
- **`.claude/` config that should be shared** (agents, commands, workflows, hooks, `settings.json`)
  is force-tracked; `settings.local.json` (machine paths) stays local.
- New service repo? Give it a lean `CLAUDE.md` + `docs/agent-context/COMMANDS.md` and add a row above.
