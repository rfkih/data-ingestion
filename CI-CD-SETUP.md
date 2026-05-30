# CI/CD Configuration for Blackheart Ingest & Inference

## Overview

Two GitHub Actions workflows are now configured for automated building and deployment:

- **`.github/workflows/blackheart-ingest-ci.yml`** — Feature stream processor (port 8001)
- **`.github/workflows/blackheart-inference-ci.yml`** — ML inference sidecar (port 8000)

Both workflows:
1. Run tests on every push to `master`/`main`
2. Build Docker images and push to `ghcr.io`
3. Deploy to VPS (if `DEPLOY_ENABLED=true`)

## Setup Steps

### 1. Enable GitHub Repository Environment (production-vps)

The deploy jobs use an `environment: production-vps` which provides a deployment safety gate. Set it up:

1. Go to GitHub repo → **Settings** → **Environments**
2. Create a new environment named **`production-vps`**
3. (Optional) Require approvals before deploy

### 2. Add GitHub Variables

Repository → **Settings** → **Variables** (not Secrets):

| Variable | Value | Example |
|----------|-------|---------|
| `DEPLOY_ENABLED` | Set to `true` to enable auto-deploy | `true` |
| `VPS_HOST` | VPS IP or hostname | `202.74.75.3` |
| `VPS_USER` | SSH username on VPS | `starsky` |

### 3. Add GitHub Secrets

Repository → **Settings** → **Secrets and variables** → **Actions**:

| Secret | Value |
|--------|-------|
| `VPS_SSH_KEY` | Contents of SSH private key (e.g., `sshkey.pem`) |

**How to get the SSH key:**
```bash
cat C:/Project/sshkey.pem | clip  # Copy to clipboard
```

Then paste into GitHub Secret `VPS_SSH_KEY` (include the `-----BEGIN ...-----` and `-----END ...-----` lines).

## Workflow Triggers

### Ingest Workflow (`blackheart-ingest-ci.yml`)
- **Triggers on:** Changes to `blackheart-ingest/**` or the workflow file itself
- **Test:** All pushes to master/main
- **Build:** Passed tests → Docker image to `ghcr.io/rfkih/blackheart-ingest:latest` + SHA tag
- **Deploy:** Only if `DEPLOY_ENABLED=true` + image pushed successfully

### Inference Workflow (`blackheart-inference-ci.yml`)
- **Triggers on:** Changes to `blackheart-inference/**` or the workflow file itself
- **Test:** All pushes to master/main
- **Build:** Passed tests → Docker image to `ghcr.io/rfkih/blackheart-inference:latest` + SHA tag
- **Deploy:** Only if `DEPLOY_ENABLED=true` + image pushed successfully

## Deployment Process

When deploy is enabled and tests pass:

1. **Build & push** image to GitHub Container Registry (GHCR)
2. **SSH into VPS** (using `VPS_SSH_KEY`)
3. **Pin image tag** in `/home/starsky/blackheart/.env` (e.g., `INGEST_TAG=abc12345`)
4. **Run docker-compose:** `docker compose pull ingest && docker compose up -d ingest`
5. **Healthcheck:** Verify service is healthy on port 8001 (ingest) or 8000 (inference)
6. **Rollback:** If healthcheck fails, revert to previous tag automatically
7. **Cleanup:** Prune stale Docker images from VPS

## Current Status

✅ **Ingest CI/CD configured:**
- Tests: `blackheart-ingest/tests/` (pytest)
- Build: `blackheart-ingest/Dockerfile` → `ghcr.io/rfkih/blackheart-ingest`
- Deploy: `/home/starsky/blackheart/` on VPS

✅ **Inference CI/CD configured:**
- Tests: `blackheart-inference/tests/` (pytest)
- Build: `blackheart-inference/Dockerfile` → `ghcr.io/rfkih/blackheart-inference`
- Deploy: `/home/starsky/blackheart/` on VPS

⏳ **Pending:** GitHub repo configuration (variables/secrets/environment)

## Manual Testing

To manually trigger a workflow without waiting for a code push:

1. Go to **Actions** tab in GitHub
2. Select workflow (e.g., "Ingest CI/CD")
3. Click **Run workflow** → **Branch: master** → **Run**

## Disabling Auto-Deploy

To prevent automatic deployments (e.g., during maintenance):

1. Set `DEPLOY_ENABLED=false` in GitHub Variables
2. Tests will still run, images will still build, but VPS deploy is skipped

## Troubleshooting

### Workflow not triggering
- Check: Did your change touch `blackheart-ingest/**` or `blackheart-inference/**`?
- Check: Are you pushing to `master` branch (not `main` or a feature branch)?
- Check: Did the `.github/workflows/` files get committed?

### Tests failing
- Run locally: `cd blackheart-ingest && pip install ".[dev,kafka]" && pytest -q`
- Fix issues, commit, push to trigger workflow again

### Docker build failing
- Check: Does `blackheart-ingest/Dockerfile` exist?
- Check: Does `blackheart-ingest/pyproject.toml` exist and have correct dependencies?

### Deploy failing (healthcheck)
- VPS ssh access might be down
- Container might be failing to start (check docker logs on VPS)
- Port 8001 (ingest) or 8000 (inference) might be blocked

## Next Steps

1. **Verify** blackheart-ingest Dockerfile builds locally:
   ```bash
   cd C:/Project/blackheart-ingest
   docker build -t blackheart-ingest:test .
   docker run --rm -p 8001:8001 blackheart-ingest:test
   ```

2. **Configure GitHub** (variables, secrets, environment per steps above)

3. **Push a test change** to trigger the workflow:
   ```bash
   git push origin master
   ```

4. **Monitor** via Actions tab → workflow run → logs

5. **Verify** VPS deployment:
   ```bash
   ssh starsky@202.74.75.3
   docker ps | grep ingest
   docker logs blackheart-ingest --tail 20
   ```
