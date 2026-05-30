# GitHub Actions CI/CD Setup — Event-Driven ML Pipeline

## Overview

Two automated CI/CD workflows for building and deploying Blackheart's event-driven ML inference services:
- **Ingest Service** (port 8001): Feature computation streaming to Kafka
- **Inference Service** (port 8000): ML predictions consuming features

Both workflows:
1. ✅ Test code on push to `master`
2. ✅ Build Docker images and push to GHCR
3. ✅ Deploy to VPS via SSH with `docker run` (NOT docker-compose)
4. ✅ Validate with healthcheck
5. ✅ Auto-rollback on failure

---

## Workflow Files

### `.github/workflows/blackheart-ingest-ci.yml`
- **Trigger**: Push/PR to `master` or `main` that modifies `blackheart-ingest/**`
- **Jobs**:
  1. `test` — Run pytest on ingest code
  2. `build-image` — Build + push to `ghcr.io/rfkih/blackheart-ingest`
  3. `deploy-ingest` — SSH deploy to VPS, healthcheck on `/health`, auto-rollback

### `.github/workflows/blackheart-inference-ci.yml`
- **Trigger**: Push/PR to `master` or `main` that modifies `blackheart-inference/**`
- **Jobs**:
  1. `test` — Run pytest on inference code (optional, doesn't block)
  2. `build-image` — Build + push to `ghcr.io/rfkih/blackheart-inference`
  3. `deploy-inference` — SSH deploy to VPS, healthcheck on `/readyz`, auto-rollback

---

## Deployment Method: Docker Run (Not docker-compose)

**Key Point**: The VPS does NOT have a working `docker-compose.yml`. Workflows use direct `docker run` commands.

### Ingest Deployment Command
```bash
docker rm -f blackheart-ingest 2>/dev/null || true
docker pull ghcr.io/rfkih/blackheart-ingest:${NEW_TAG}
docker run -d --name blackheart-ingest --restart unless-stopped \
  -p 8001:8001 \
  -e INGEST_PROFILE=prod \
  -e INGEST_SERVER_HOST=0.0.0.0 \
  -e INGEST_SERVER_PORT=8001 \
  -e INGEST_DB_DSN=postgresql://blackheart_research:${BLACKHEART_RESEARCH_PASSWORD}@postgres:5432/trading_db \
  -e KAFKA_BOOTSTRAP_SERVERS=blackheart-kafka:9092 \
  ghcr.io/rfkih/blackheart-ingest:${NEW_TAG}
```

### Inference Deployment Command
```bash
docker rm -f blackheart-inference 2>/dev/null || true
docker pull ghcr.io/rfkih/blackheart-inference:${NEW_TAG}
docker run -d --name blackheart-inference --restart unless-stopped \
  --network blackheart_default \
  -p 8000:8000 \
  -v /home/starsky/blackheart-train/artifacts:/artifacts:ro \
  -e INFERENCE_PROFILE=prod \
  -e INFERENCE_HOST=0.0.0.0 \
  -e INFERENCE_PORT=8000 \
  -e INFERENCE_AUTH_TOKEN=prod-inference-token \
  -e INFERENCE_DB_DSN=postgresql://blackheart_research:${BLACKHEART_RESEARCH_PASSWORD}@postgres:5432/trading_db \
  -e INFERENCE_ARTIFACT_DIR=/artifacts \
  -e INFERENCE_STREAMING_ENABLED=true \
  ghcr.io/rfkih/blackheart-inference:${NEW_TAG}
```

**Note**: 
- Inference uses `--network blackheart_default` to reach postgres container
- Both use `${BLACKHEART_RESEARCH_PASSWORD}` from VPS `.env` file
- Healthchecks: Ingest → `/health`, Inference → `/readyz`

---

## Environment Variables & Secrets

### Repository Variables (Settings → Variables)
| Variable | Value | Used By |
|----------|-------|---------|
| `DEPLOY_ENABLED` | `true` | Both workflows (gates deploy job) |
| `VPS_HOST` | `202.74.75.3` | Both workflows |
| `VPS_USER` | `starsky` | Both workflows |

### Environment Variables (Settings → Environments → production-vps)
Create or update the `production-vps` environment with:
| Variable | Value | Used By |
|----------|-------|---------|
| `DEPLOY_ENABLED` | `true` | Both workflows |
| `VPS_HOST` | `202.74.75.3` | Both workflows |
| `VPS_USER` | `starsky` | Both workflows |

### Secrets (Settings → Secrets and Variables → Actions)
| Secret | Value | Used By |
|--------|-------|---------|
| `VPS_SSH_KEY` | SSH private key (contents of `C:\Project\sshkey.pem`) | Both workflows (SSH access) |

---

## Workflow Triggers

### Automatic Triggers
- Push to `master`/`main` that modifies:
  - `blackheart-ingest/**` → Ingest workflow runs
  - `blackheart-inference/**` → Inference workflow runs
  - `.github/workflows/*.yml` → Corresponding workflow runs

### Manual Trigger
- GitHub UI → Actions → Select workflow → "Run workflow" → Branch: master

---

## Healthcheck Endpoints

### Ingest (`http://127.0.0.1:8001/health`)
- Method: GET
- Returns: `{"status": "healthy"}`
- Interval: 30s, Timeout: 10s, Retries: 3

### Inference (`http://127.0.0.1:8000/readyz`)
- Method: GET
- Requires: `X-Inference-Token: prod-inference-token` header
- Interval: 30s, Timeout: 10s, Retries: 3

---

## Rollback Behavior

If healthcheck fails after deploy:
1. Workflow captures the previous tag/image SHA
2. Kills new container
3. Starts previous image with same docker run command
4. Re-validates healthcheck
5. If all passes, deploy is marked successful

**Rollback image tag**: Stored in VPS `/home/starsky/blackheart/.env` as `INGEST_TAG` or `INFERENCE_TAG`

---

## Troubleshooting

### Workflow not triggering
- ✓ Confirm change is in `blackheart-ingest/**` or `blackheart-inference/**`
- ✓ Confirm branch is `master` (not `main` or feature branch)
- ✓ Check workflow file syntax (`.github/workflows/*.yml`)

### Deploy job skipped
- ✓ Check `DEPLOY_ENABLED=true` in repo/environment variables
- ✓ Or use manual trigger: workflow_dispatch

### Healthcheck fails
- ✓ SSH into VPS: `ssh -i sshkey.pem starsky@202.74.75.3`
- ✓ Check container: `docker logs blackheart-ingest` or `docker logs blackheart-inference`
- ✓ Test endpoint: `curl http://127.0.0.1:8001/health`

### SSH authentication fails
- ✓ Verify `VPS_SSH_KEY` secret contains full private key (including BEGIN/END lines)
- ✓ Verify `VPS_HOST` and `VPS_USER` are correct

### Docker image not found
- ✓ Check GHCR: `https://github.com/rfkih/data-ingestion/pkgs/container/blackheart-ingest`
- ✓ Verify GitHub token has `packages:write` permission

---

## Recent Fixes (Latest Commits)

| Commit | Change |
|--------|--------|
| `53b158a` | Added clarifying comments to workflows |
| `b763841` | Use BLACKHEART_RESEARCH_PASSWORD from VPS .env + add network |
| `35b7988` | Remove non-existent network reference |
| `8e8d9ab` | Add /health endpoint + fix env vars |
| `3600661` | Use docker run instead of docker-compose |

---

## Current Live Status

**Ingest Service**: ✅ Running on port 8001
- Image: `ghcr.io/rfkih/blackheart-ingest:latest`
- Health: Healthy
- Status: Streaming features to Kafka

**Inference Service**: ✅ Running on port 8000
- Image: `ghcr.io/rfkih/blackheart-inference:latest`
- Network: `blackheart_default`
- Status: Consuming features, publishing signals
