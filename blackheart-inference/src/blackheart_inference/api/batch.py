"""``POST /inference/batch-predict`` — atomic batch inference on latest features.

Webhook target for feature compute completion. Queries all active/shadow
signals and runs inference on the latest available timestamp across all
feature_values. Writes all predictions atomically to signal_history.

Workflow:
  1. Get latest timestamp from feature_values.
  2. Fetch all active/shadow signals.
  3. For each signal, resolve model + load artifact.
  4. Batch-fetch features for (signal, symbol, interval, ts).
  5. Batch-predict + UPSERT to signal_history in a transaction.
  6. Return count of signals processed.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
import structlog

from ..errors import InferenceError
from ..repo import features as features_repo
from ..repo import models as models_repo
from ..repo import signals as signals_repo
from ..services.artifact_loader import read_artifact
from ..services.predictor import EmptyModelError, MissingFeatureError, predict_single
from .deps import get_agent_name, get_db_conn

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/inference", tags=["inference"])


class BatchPredictBody(BaseModel):
    """Request body for batch-predict webhook."""

    compute_run_id: str = Field(
        ..., description="Audit trail ID from feature compute run"
    )


class BatchPredictResponse(BaseModel):
    """Response from batch-predict endpoint."""

    status: str = Field(
        ...,
        description='Status: "ok" if all succeeded, "partial" if some failed, "error" if all failed',
    )
    signals_processed: int = Field(
        ..., description="Total number of signals attempted"
    )
    rows_written: int = Field(
        ..., description="Number of predictions successfully written"
    )
    rows_failed: list[str] = Field(
        ...,
        description='List of failures, e.g. ["signal1:no_model", "signal2:timeout"]',
    )
    completed_at: str = Field(
        ..., description="ISO 8601 timestamp of completion"
    )


@router.post("/batch-predict")
async def batch_predict(
    body: BatchPredictBody,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db_conn),
    agent: str = Depends(get_agent_name),
) -> BatchPredictResponse:
    """Trigger atomic batch inference on all active signals at latest ts.

    Called by feature compute webhook after persist succeeds. Fetches
    the latest timestamp from feature_values, loads all active/shadow
    signals, and runs inference for each at that single point in time,
    writing all results in one transaction.

    Returns:
        {
            "status": "ok" | "partial" | "error",
            "signals_processed": <int>,     # Total signals attempted
            "rows_written": <int>,          # Signals with predictions written
            "rows_failed": [<str>, ...],    # e.g. ["signal1:no_model", "signal2:timeout"]
            "completed_at": <ISO string>,   # Timestamp of inference
        }
    """
    # Step 1: Get latest timestamp from feature_values
    latest_ts = await features_repo.get_latest_ts(conn)
    if latest_ts is None:
        raise InferenceError(
            status_code=409,
            error_code="no_features_available",
            message="feature_values is empty — no timestamp to infer at.",
            retryable=True,
        )

    # Step 2: Fetch all active/shadow signals
    signals = await signals_repo.fetch_active_signals(conn)
    if not signals:
        return BatchPredictResponse(
            status="ok",
            signals_processed=0,
            rows_written=0,
            rows_failed=[],
            completed_at=datetime.now(timezone.utc).isoformat(),
        )

    # Step 3–5: For each signal, resolve model → load artifact → predict → write
    artifact_dir = request.app.state.settings.artifact_dir
    to_write: list[tuple[UUID, str, datetime, float, dict[str, Any]]] = []
    rows_failed: list[str] = []

    for signal in signals:
        signal_id: UUID = signal["signal_id"]
        signal_name = signal.get("name", str(signal_id))
        try:
            # Resolve model
            model = await models_repo.fetch_model_registry_row(
                conn, signal["model_id"]
            )
            if model is None or model["status"] in ("retired", "rejected_by_operator"):
                rows_failed.append(f"{signal_name}:no_model")
                continue
            if not model.get("artifact_sha256"):
                rows_failed.append(f"{signal_name}:no_artifact")
                continue

            # Load artifact — cached + content-verified, off the event loop.
            try:
                payload = await asyncio.to_thread(
                    read_artifact,
                    model["artifact_sha256"],
                    artifact_dir,
                    verify_content=request.app.state.settings.artifact_verify_content,
                )
            except (FileNotFoundError, ValueError):
                rows_failed.append(f"{signal_name}:artifact_load_failed")
                continue

            # Feature metadata — artifact-pinned versions when present,
            # else latest registered (pre-pinning artifacts).
            feature_names: list[str] = list(payload["feature_names"])
            metas = await features_repo.fetch_feature_meta(
                conn, feature_names, payload.get("feature_versions") or None
            )
            missing_versions = [n for n in feature_names if n not in metas]
            if missing_versions:
                rows_failed.append(f"{signal_name}:missing_features")
                continue

            # For each symbol + interval combo in the model
            symbol = model.get("symbol", "")
            interval = model.get("serving_interval") or model.get("interval", "")

            if not symbol or not interval:
                rows_failed.append(f"{signal_name}:no_symbol_or_interval")
                continue

            # Resolve the ts for THIS signal's own (symbol, interval) — the
            # global latest_ts is interval-agnostic and is almost always a 15m
            # timestamp once any 15m symbol streams, which has no row for a 1h
            # signal → it would skip and fall to catchup_scan. Per-surface ts
            # lets each signal infer at its own latest bar.
            signal_ts = await features_repo.get_latest_ts_for(conn, symbol, interval)
            if signal_ts is None:
                rows_failed.append(f"{signal_name}:no_features_for_surface")
                continue

            # Fetch feature vector at the signal's own latest ts
            feature_vector = await features_repo.fetch_per_bar_values_at_ts(
                conn,
                metas=metas,
                symbol=symbol,
                interval_name=interval,
                ts=signal_ts,
            )

            # Predict — off the event loop so a slow model can't stall
            # /healthz and the other signals' webhooks.
            predict_started = time.perf_counter()
            try:
                value, confidence = await asyncio.to_thread(
                    predict_single, payload, feature_vector
                )
            except MissingFeatureError:
                rows_failed.append(f"{signal_name}:missing_feature_vector")
                continue
            except EmptyModelError:
                rows_failed.append(f"{signal_name}:empty_model")
                continue
            except NotImplementedError:
                rows_failed.append(f"{signal_name}:ensemble_unsupported")
                continue

            tracker = getattr(request.app.state, "latency_tracker", None)
            if tracker is not None:
                tracker.record_latency(
                    signal_name, (time.perf_counter() - predict_started) * 1000.0
                )

            # Queue for write
            meta = {
                "model_id": str(model["id"]),
                "artifact_sha256": model["artifact_sha256"],
                "spec_name": payload.get("spec", {}).get("name"),
                "objective": payload.get("objective"),
                "model_status_at_inference": model["status"],
                "compute_run_id": body.compute_run_id,
                "feature_versions_source": (
                    "artifact" if payload.get("feature_versions") else "registry_latest"
                ),
            }
            to_write.append((signal_id, symbol, signal_ts, value, meta))

        except Exception as e:
            # If any single signal fails, don't crash the whole batch.
            # Just skip it and continue.
            logger.exception(
                "unexpected error processing signal",
                signal=signal_name,
                error=repr(e),
            )
            rows_failed.append(f"{signal_name}:unexpected_error")
            continue

    # Step 6: Write all predictions atomically
    rows_written = 0
    if to_write:
        # Use a transaction to ensure all-or-nothing
        async with conn.transaction():
            for signal_id, symbol, ts, value, meta in to_write:
                await signals_repo.upsert_signal_value(
                    conn,
                    signal_id=signal_id,
                    symbol=symbol,
                    ts=ts,
                    value=value,
                    confidence=None,  # Model confidence unused for now; could add model uncertainty in future
                    source="stream",
                    meta=meta,
                    created_by=agent,
                )
                rows_written += 1

    # Determine status based on results
    signals_processed = len(signals)
    if signals_processed == 0:
        status = "ok"
    elif rows_failed and rows_written == 0:
        status = "error"
    elif rows_failed:
        status = "partial"
    else:
        status = "ok"

    return BatchPredictResponse(
        status=status,
        signals_processed=signals_processed,
        rows_written=rows_written,
        rows_failed=rows_failed,
        completed_at=datetime.now(timezone.utc).isoformat(),
    )
