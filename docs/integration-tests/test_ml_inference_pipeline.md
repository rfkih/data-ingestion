# End-to-End ML Inference Pipeline Integration Test

**Purpose:** Verify the complete push-based ML inference pipeline works correctly from feature compute completion through inference trigger, prediction writing, and health monitoring.

**Duration:** ~5–10 minutes

**Prerequisite:** All services running locally or on VPS with network access. See [Local Run Setup](../operations/local_run.md) or [VPS Topology](../operations/vps_topology.md).

---

## Test Overview

This guide walks through the 6-step verification sequence:

1. **Service Startup** — Verify all 3 services are running
2. **Feature Compute Trigger** — POST to `/compute/refresh` to seed features
3. **Inference Webhook Verification** — Confirm inference service received the batch-predict request
4. **Signal Health Check** — Query `/ml/monitor` for fresh signal metadata
5. **Database Verification** — Check `signal_history` for written predictions
6. **End-to-End Timing** — Document latencies at each step

---

## Prerequisites

- **Services running:** blackheart-ingest (Python), blackheart-inference (FastAPI), blackheart-research-orchestrator (FastAPI)
- **Database:** TimescaleDB with `feature_values`, `signals`, `signal_history` tables
- **Environment variables set:**
  - `INGEST_BASE_URL` (default: `http://127.0.0.1:8001`)
  - `INFERENCE_BASE_URL` (default: `http://127.0.0.1:8000`)
  - `ORCHESTRATOR_BASE_URL` (default: `http://127.0.0.1:8082`)
  - `INFERENCE_AUTH_TOKEN` (default: `dev-token`)
- **Tools:** curl, psql/DBeaver, JSON formatter (e.g., jq)

---

## Step 1: Verify Service Startup

### 1.1 Check Ingest Service Health

```bash
curl -s http://127.0.0.1:8001/health | jq .
```

**Expected Response:**
```json
{
  "status": "ok",
  "version": "0.1.0",
  "database": "connected"
}
```

**If fails:** Check ingest logs for connection errors. Verify `DATABASE_URL` points to accessible TimescaleDB.

---

### 1.2 Check Inference Service Health

```bash
curl -s http://127.0.0.1:8000/health | jq .
```

**Expected Response:**
```json
{
  "status": "ok",
  "models_loaded": 3,
  "inference_ready": true
}
```

**If fails:** Check inference logs for LightGBM model loading errors. Verify artifact directory is readable.

---

### 1.3 Check Orchestrator Service Health

```bash
curl -s http://127.0.0.1:8082/health | jq .
```

**Expected Response:**
```json
{
  "status": "ok",
  "database": "connected",
  "scheduler": "running"
}
```

**If fails:** Check orchestrator logs for DB or scheduler init errors.

**Checkpoint:** All 3 services respond with `"status": "ok"`. ✓ Proceed to Step 2.

---

## Step 2: Trigger Feature Compute

### 2.1 POST to /compute/refresh

This endpoint triggers a fresh compute run across active signals.

```bash
curl -X POST http://127.0.0.1:8001/compute/refresh \
  -H "Content-Type: application/json" \
  -H "X-Ingest-Token: dev-token" \
  -d '{
    "symbols": ["BTCUSDT", "ETHUSDT"],
    "look_back_hours": 168
  }' \
  -s | jq .
```

**Expected Response (immediate, ~200ms):**
```json
{
  "compute_run_id": "8f7e6d5c-4b3a-2f1e-0d9c-8b7a6f5e4d3c",
  "status": "queued",
  "symbols": ["BTCUSDT", "ETHUSDT"],
  "estimated_duration_seconds": 45
}
```

**Record:**
- `compute_run_id`: You'll need this for verification
- Response time (should be < 500ms)

**If fails:**
- `401 Unauthorized` → Check `X-Ingest-Token` header value
- `400 Bad Request` → Check JSON payload format
- `500 Internal Server Error` → Check ingest logs for DB write errors

---

### 2.2 Monitor Compute Progress

Poll the status endpoint until compute finishes:

```bash
COMPUTE_RUN_ID="8f7e6d5c-4b3a-2f1e-0d9c-8b7a6f5e4d3c"  # From Step 2.1
curl -s "http://127.0.0.1:8001/compute/runs/${COMPUTE_RUN_ID}" | jq .
```

**Expected Response (while running):**
```json
{
  "run_id": "8f7e6d5c-4b3a-2f1e-0d9c-8b7a6f5e4d3c",
  "status": "running",
  "symbols": ["BTCUSDT", "ETHUSDT"],
  "total_features": 12,
  "rows_written": 0,
  "started_at": "2026-05-30T14:23:10Z",
  "estimated_remaining_seconds": 30
}
```

**Expected Response (when finished):**
```json
{
  "run_id": "8f7e6d5c-4b3a-2f1e-0d9c-8b7a6f5e4d3c",
  "status": "finished",
  "symbols": ["BTCUSDT", "ETHUSDT"],
  "total_features": 12,
  "rows_written": 284,
  "started_at": "2026-05-30T14:23:10Z",
  "finished_at": "2026-05-30T14:23:48Z",
  "duration_seconds": 38,
  "webhook_sent": true,
  "webhook_status": "delivered"
}
```

**Record:**
- `duration_seconds`: Compute time
- `rows_written`: Feature count (should be > 0)
- `webhook_sent`: Should be `true` — this triggers Step 3

**Timing expectation:** 30–90 seconds (depending on symbols and interval)

**If webhook_sent is false:**
- Check ingest logs for webhook call errors
- Verify `INFERENCE_BASE_URL` and `INFERENCE_AUTH_TOKEN` are set correctly
- Proceed to Step 4 and manually trigger inference (see Step 4.1 alt)

---

## Step 3: Verify Inference Batch-Predict Webhook

### 3.1 Check Inference Service Logs

Once compute finishes and webhook is sent, the inference service should have received the batch-predict request. Check logs:

```bash
# Tail inference service logs (command depends on your setup)
# If running locally with direct output:
# tail -n 50 inference.log | grep batch-predict

# Or via Docker:
docker logs blackheart-inference | grep -A2 "batch-predict"
```

**Expected log entries:**
```
[2026-05-30 14:23:50] INFO inference.batch: batch-predict triggered, compute_run_id=8f7e6d5c-4b3a-2f1e-0d9c-8b7a6f5e4d3c
[2026-05-30 14:23:50] INFO inference.batch: querying active signals (status=active or status=shadow)
[2026-05-30 14:23:51] INFO inference.batch: loaded 8 signals, 3 models
[2026-05-30 14:23:54] INFO inference.batch: batch-predict completed, predictions_written=24
```

**If no logs appear:**
- Check if inference service is actually running (`curl http://127.0.0.1:8000/health`)
- Check if ingest service tried to call webhook (ingest logs for `compute.inference_triggered` or `compute.inference_webhook_failed`)
- If webhook call failed, see Step 4.1 alternative to manually trigger

---

### 3.2 Query Inference Batch Status (Optional)

If inference service exposes a batch status endpoint:

```bash
curl -s http://127.0.0.1:8000/inference/batch-status?compute_run_id=8f7e6d5c-4b3a-2f1e-0d9c-8b7a6f5e4d3c \
  -H "X-Inference-Token: dev-token" | jq .
```

**Expected Response:**
```json
{
  "compute_run_id": "8f7e6d5c-4b3a-2f1e-0d9c-8b7a6f5e4d3c",
  "status": "completed",
  "predictions_written": 24,
  "signals_processed": 8,
  "duration_ms": 4200,
  "started_at": "2026-05-30T14:23:50Z",
  "finished_at": "2026-05-30T14:23:54Z"
}
```

**Record:**
- `duration_ms`: Inference latency
- `predictions_written`: Count of signal_history rows written

**Checkpoint:** Inference service received webhook and executed batch-predict. ✓ Proceed to Step 4.

---

## Step 4: Check ML Monitor Health

### 4.1 Query /ml/monitor for Signal Freshness

```bash
curl -s http://127.0.0.1:8000/ml/monitor \
  -H "X-Inference-Token: dev-token" | jq .
```

**Expected Response (snippet):**
```json
{
  "signals": [
    {
      "signal_id": "regime_btc_v3",
      "symbol": "BTCUSDT",
      "interval": "1h",
      "status": "active",
      "last_feature_ts": "2026-05-30T14:00:00Z",
      "last_prediction_ts": "2026-05-30T14:23:54Z",
      "freshness_score": 0.98,
      "feature_age_minutes": 23,
      "inference_latency_ms": 4200,
      "warning": null
    },
    {
      "signal_id": "flow_btc_v2",
      "symbol": "BTCUSDT",
      "interval": "4h",
      "status": "shadow",
      "last_feature_ts": "2026-05-30T12:00:00Z",
      "last_prediction_ts": "2026-05-30T14:23:54Z",
      "freshness_score": 0.85,
      "feature_age_minutes": 143,
      "inference_latency_ms": 4200,
      "warning": "age_warning"
    }
  ],
  "overall_health": "healthy",
  "check_timestamp": "2026-05-30T14:24:00Z"
}
```

**Verify:**
- `last_prediction_ts` is recent (within last 2 minutes) → ✓ Inference ran
- `freshness_score` is high (>0.80) → ✓ Features are fresh
- `inference_latency_ms` is reasonable (<10000) → ✓ Inference is fast
- `warning` is `null` for active signals → ✓ No staleness issues
- `overall_health` is `"healthy"` → ✓ Pipeline is good

**If warnings appear:**
- `age_warning` → Features are older than freshness threshold
  - Check that compute run wrote rows to `feature_values`
  - Verify next compute run (scheduled or manual)
- `inference_latency_warning` → Inference took too long
  - Check inference service CPU/memory usage
  - Look for slow model inference in logs
- `inference_timeout` → Inference service did not respond
  - Restart inference service
  - Check network connectivity

**Record:**
- Overall health status
- Freshness scores for each signal

**Checkpoint:** ML monitor shows fresh signals with recent predictions. ✓ Proceed to Step 5.

---

## Step 5: Verify Predictions in Database

### 5.1 Query signal_history Table

Connect to TimescaleDB and run:

```sql
-- Check latest predictions for active signals
SELECT
  signal_id,
  symbol,
  interval,
  prediction_ts,
  prediction_value,
  confidence_score,
  created_at
FROM signal_history
WHERE created_at > NOW() - INTERVAL '5 minutes'
ORDER BY created_at DESC
LIMIT 20;
```

**Expected Output:**
```
 signal_id        | symbol  | interval | prediction_ts       | prediction_value | confidence_score | created_at
------------------+---------+----------+---------------------+------------------+------------------+--------------------
 regime_btc_v3    | BTCUSDT | 1h       | 2026-05-30 14:00:00 |              1.0 |             0.92 | 2026-05-30 14:23:54
 regime_btc_v3    | BTCUSDT | 1h       | 2026-05-30 13:00:00 |              1.0 |             0.91 | 2026-05-30 14:23:54
 flow_btc_v2      | BTCUSDT | 4h       | 2026-05-30 12:00:00 |             -0.3 |             0.78 | 2026-05-30 14:23:54
 ...
```

**Verify:**
- Rows exist with recent `created_at` (within last 2 minutes)
- `prediction_value` is numeric and reasonable (typically -1.0 to 1.0 or 0.0 to 1.0 depending on model)
- `confidence_score` is present (0.0–1.0 range)
- `prediction_ts` aligns with feature age from Step 4

---

### 5.2 Count Predictions by Signal

```sql
-- Summary of predictions written in this test
SELECT
  signal_id,
  symbol,
  COUNT(*) as prediction_count,
  MAX(created_at) as most_recent
FROM signal_history
WHERE created_at > NOW() - INTERVAL '5 minutes'
GROUP BY signal_id, symbol
ORDER BY signal_id;
```

**Expected Output:**
```
 signal_id        | symbol  | prediction_count | most_recent
------------------+---------+------------------+--------------------
 flow_btc_v2      | BTCUSDT |                2 | 2026-05-30 14:23:54
 regime_btc_v3    | BTCUSDT |                2 | 2026-05-30 14:23:54
 (2 rows)
```

**Record:**
- Total predictions written (should be > 0)
- Which signals were updated

**Checkpoint:** Predictions are persisted in signal_history with correct timestamps and values. ✓ Proceed to Step 6.

---

## Step 6: End-to-End Timing Analysis

### 6.1 Collect Latency Metrics

Compile the times from previous steps into a timeline:

| Stage | Timestamp | Duration | Notes |
|-------|-----------|----------|-------|
| Compute Start | 14:23:10 | — | POST /compute/refresh |
| Compute Finish | 14:23:48 | 38s | `status=finished` |
| Webhook Sent | 14:23:48 | 0s | Immediate after compute |
| Inference Start | 14:23:50 | 2s | Log entry from ingest |
| Inference Finish | 14:23:54 | 4s | Log entry from inference |
| DB Write | 14:23:54 | 0s | Atomic with inference |
| ML Monitor Update | 14:24:00 | 6s | Next /ml/monitor check |
| **Total E2E** | — | **50 seconds** | From POST to DB verification |

**Expected timing:**
- **Compute:** 30–90 seconds (depends on lookback window)
- **Webhook:** < 1 second (local network)
- **Inference:** 2–10 seconds (batch size 3–10 signals)
- **ML Monitor sync:** < 10 seconds (cache refresh)
- **Total E2E:** < 120 seconds (with network latency)

### 6.2 Verify Event Order Constraints

Confirm the pipeline executed in the correct order:

1. ✓ **Compute runs** → features written to `feature_values`
2. ✓ **Webhook fires** → inference service receives batch-predict request
3. ✓ **Inference runs** → predictions computed and written to `signal_history`
4. ✓ **ML Monitor syncs** → freshness checks pass, health status updated
5. ✓ **Database consistency** → all rows consistent, no orphans

### 6.3 Check for Any Errors or Warnings

Review logs for any issues during the test:

**Ingest logs:**
```bash
grep -i "error\|warning" ingest.log | tail -20
```

**Inference logs:**
```bash
grep -i "error\|warning" inference.log | tail -20
```

**Orchestrator logs:**
```bash
grep -i "error\|warning" orchestrator.log | tail -20
```

**Expected:** No critical errors. Warnings about old features or slow inference are acceptable if < 5 total.

---

## Test Completion Checklist

Use this checklist to confirm the test passed:

- [ ] **Step 1:** All 3 services respond to `/health` with `status: ok`
- [ ] **Step 2:** Feature compute finishes with `status: finished` and `rows_written > 0`
- [ ] **Step 2:** `webhook_sent: true` in compute status response
- [ ] **Step 3:** Inference logs show `batch-predict` and `predictions_written > 0`
- [ ] **Step 4:** `/ml/monitor` shows recent `last_prediction_ts` for all signals
- [ ] **Step 4:** `overall_health` is `"healthy"`
- [ ] **Step 5:** `signal_history` table has rows with `created_at` in last 5 minutes
- [ ] **Step 5:** Prediction counts match inference service output
- [ ] **Step 6:** End-to-end latency is < 120 seconds
- [ ] **Step 6:** No critical errors in any service logs

**If any check fails:** See **Troubleshooting** section below.

---

## Troubleshooting

### Service Not Responding

**Problem:** `/health` returns connection refused or timeout

**Solution:**
1. Verify service is running: `ps aux | grep [service-name]`
2. Check logs for startup errors
3. Verify database connection string (`DATABASE_URL`)
4. Ensure port is not in use: `lsof -i :8000` (replace 8000 with service port)
5. Try restarting: `pkill -f [service-name] && sleep 2 && python -m [service-name]`

---

### Webhook Call Fails

**Problem:** Compute finishes but `webhook_sent: false`

**Solution:**
1. Check ingest logs for `compute.inference_webhook_failed`
2. Verify `INFERENCE_BASE_URL` is reachable: `curl http://127.0.0.1:8000/health`
3. Verify `INFERENCE_AUTH_TOKEN` matches token in inference service
4. Manually trigger inference (see Step 4.1 alternative):

```bash
curl -X POST http://127.0.0.1:8000/inference/batch-predict \
  -H "Content-Type: application/json" \
  -H "X-Inference-Token: dev-token" \
  -d '{
    "compute_run_id": "8f7e6d5c-4b3a-2f1e-0d9c-8b7a6f5e4d3c"
  }' \
  -s | jq .
```

---

### Inference Service Doesn't Trigger

**Problem:** No log entries from inference service after webhook call

**Solution:**
1. Verify inference service is running: `curl http://127.0.0.1:8000/health`
2. Check if webhook request reached inference:
   - Enable request logging in FastAPI: `log_level="debug"` in startup
   - Tail logs: `tail -n 100 inference.log | grep "POST /inference/batch-predict"`
3. Check if models are loaded: Look for `models_loaded` in `/health` response
4. Manually trigger inference with curl (see Webhook Call Fails section)

---

### Predictions Not Written to Database

**Problem:** Inference runs but `signal_history` is empty

**Solution:**
1. Verify inference logs show `predictions_written > 0`
2. Check database connection in inference service: `ORCHESTRATOR_DB_DSN`
3. Verify `signal_history` table exists and is writable:

```sql
SELECT COUNT(*) FROM signal_history;
SELECT table_schema, table_name FROM information_schema.tables WHERE table_name = 'signal_history';
```

4. Check for insert errors in inference logs: `grep -i "insert\|write" inference.log`
5. Manually verify table is not full or locked: `SELECT * FROM signal_history LIMIT 1;`

---

### Freshness Score Is Low

**Problem:** `/ml/monitor` shows `freshness_score < 0.80`

**Solution:**
1. Check `last_feature_ts`: If old, features are stale
   - Run another compute: `curl -X POST http://127.0.0.1:8001/compute/refresh ...`
   - Wait for it to finish and check `/ml/monitor` again
2. Check `last_prediction_ts`: If recent, inference is working
   - Low score may just indicate old training features (normal during backtest windows)
3. Adjust freshness threshold in `/ml/monitor` if score should be higher (see service config)

---

### End-to-End Latency Is Too High

**Problem:** Total pipeline time > 120 seconds

**Solution:**
1. **Identify slow stage:**
   - Compute slow? Check ingest logs for feature query time
   - Inference slow? Check inference logs for model prediction time
   - DB write slow? Check TimescaleDB query logs
2. **For compute slowness:**
   - Reduce `look_back_hours` in POST /compute/refresh
   - Check if database indexes are in place: `SELECT indexname FROM pg_indexes WHERE tablename='feature_values';`
3. **For inference slowness:**
   - Check if models are loaded in memory: `free -h` (Linux) or Task Manager (Windows)
   - Profile inference: Add timing logs in `predictor.py`
4. **For database slowness:**
   - Run `ANALYZE` on tables: `ANALYZE feature_values; ANALYZE signal_history;`
   - Check slow query log: `SELECT * FROM pg_stat_statements ORDER BY total_time DESC LIMIT 10;`

---

## Cleanup

After testing, you may want to clean up test data:

```sql
-- Delete predictions from this test (keep last 7 days)
DELETE FROM signal_history
WHERE created_at < NOW() - INTERVAL '7 days';

-- Verify cleanup
SELECT COUNT(*) as remaining_rows FROM signal_history;
```

---

## Additional Resources

- **Architecture:** See [Push-Based ML Inference Pipeline](../architecture/ml_inference_pipeline.md)
- **Feature Compute API:** See `blackheart-ingest/docs/compute_api.md`
- **Inference API:** See `blackheart-inference/docs/batch_predict.md`
- **ML Monitor Design:** See `blackheart-inference/docs/ml_monitor.md`
- **Service Configuration:** See [Service Ports](../reference/blackheart_ports.md)

---

## Sign-Off

Test completed on: ________________  
Tester name: ________________  
Overall result: [ ] PASS [ ] FAIL [ ] PARTIAL  
Notes: ________________________________________________________________  
________________________________________________________________  

---

**Document version:** 1.0  
**Last updated:** 2026-05-30  
**Maintainer:** Quantitative Research Team
