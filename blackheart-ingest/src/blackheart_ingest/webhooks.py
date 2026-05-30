"""HTTP client for post-compute webhooks (feature → inference trigger)."""

from __future__ import annotations

import logging
from typing import Any
import httpx

logger = logging.getLogger(__name__)


async def notify_inference_batch_ready(
    *,
    base_url: str,
    auth_token: str,
    compute_run_id: str,
) -> dict[str, Any]:
    """POST to inference service to trigger batch predict on fresh features.

    Called after feature_compute succeeds. Inference service will query
    all active/shadow signals and batch-predict in a single transaction.

    Args:
        base_url: Inference service base URL (e.g. http://127.0.0.1:8000)
        auth_token: X-Inference-Token value
        compute_run_id: feature_compute_run.run_id for audit trail

    Returns:
        Response JSON with 'status' and 'queued' (count of signals).

    Raises:
        httpx.HTTPError on non-200 status.
    """
    logger.info("webhook.compute_ready", extra={"compute_run_id": compute_run_id})
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{base_url}/inference/batch-predict",
            json={"compute_run_id": compute_run_id},
            headers={"X-Inference-Token": auth_token},
        )
        response.raise_for_status()
        result = response.json()
        logger.info("webhook.success", extra={"compute_run_id": compute_run_id, "result": result})
        return result
