"""FastAPI endpoint for feature compute refresh.

Supports full and incremental (from max(ts) to now) compute modes.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..features.compute import compute, default_window, FeatureComputeError
from ..features.definitions import FEATURES, get_feature
from ..features.persistence import (
    fail_run,
    finish_run,
    start_run,
    write_values,
)
from ..shared.db import get_connection

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/compute", tags=["compute"])


class ComputeRefreshRequest(BaseModel):
    """Request body for POST /compute/refresh."""

    incremental: bool = Field(
        default=False,
        description="If true, compute from max(feature_values.ts) to now. "
        "If false, compute full backfill window (180 days).",
    )
    features: list[str] = Field(
        default_factory=list,
        description="Feature names to compute. Empty = all registered features.",
    )


class ComputeRefreshResponse(BaseModel):
    """Response from POST /compute/refresh."""

    status: str
    computed_rows: int
    persisted_rows: int
    errors: list[str]


def _get_max_ts_for_feature(
    conn: Any,
    feat_name: str,
    symbol: str | None = None,
    interval: str | None = None,
) -> datetime | None:
    """Query max(ts) from feature_values for a given feature.

    Returns None if no rows exist.
    """
    sql = """
        SELECT MAX(ts) as max_ts
        FROM feature_values
        WHERE name = %(name)s
          AND symbol IS NOT DISTINCT FROM %(symbol)s
          AND interval IS NOT DISTINCT FROM %(interval)s
    """
    with conn.cursor() as cur:
        cur.execute(sql, {"name": feat_name, "symbol": symbol, "interval": interval})
        row = cur.fetchone()
    if row and row[0]:
        # Convert to naive UTC datetime if needed
        ts = row[0]
        if hasattr(ts, "tzinfo") and ts.tzinfo is not None:
            ts = ts.replace(tzinfo=None)
        return ts
    return None


@router.post("/refresh", response_model=ComputeRefreshResponse)
async def refresh_features(req: ComputeRefreshRequest) -> ComputeRefreshResponse:
    """POST /compute/refresh — Compute features with optional incremental mode.

    Incremental mode (incremental=true):
    - Queries max(feature_values.ts) for each feature
    - Computes from max_ts + 1 second to now
    - Skips features with no prior rows (treats as full backfill for those)

    Full mode (incremental=false):
    - Computes over 180-day lookback window

    Response includes:
    - status: 'ok' or 'partial' (if some features failed)
    - computed_rows: total rows computed across all features
    - persisted_rows: total rows written to feature_values
    - errors: list of feature names that failed (if any)
    """
    errors: list[str] = []
    overall_computed = 0
    overall_persisted = 0

    # Resolve which features to compute
    if req.features:
        try:
            feats = [get_feature(name) for name in req.features]
        except KeyError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown feature: {e}",
            ) from e
    else:
        feats = list(FEATURES)

    logger.info("compute.refresh.start", extra={
        "incremental": req.incremental,
        "feature_count": len(feats),
    })

    with get_connection() as conn:
        for feat in feats:
            # Determine symbols/intervals to compute
            symbols = list(feat.symbols) if feat.symbols else [None]
            intervals = list(feat.intervals) if feat.intervals else [None]

            for sym in symbols:
                for ivl in intervals:
                    scope_tag = (
                        f" [{sym or '-'}/{ivl or '-'}]" if (sym or ivl) else ""
                    )

                    try:
                        # Resolve compute window
                        if req.incremental:
                            max_ts = _get_max_ts_for_feature(
                                conn, feat.name, symbol=sym, interval=ivl
                            )
                            if max_ts is None:
                                # No prior data; fall back to full backfill
                                start, end = default_window(180)
                                logger.info(
                                    "compute.incremental_no_prior_data",
                                    extra={
                                        "feature": feat.name,
                                        "scope": scope_tag,
                                        "action": "using_full_backfill",
                                    },
                                )
                            else:
                                # Compute from max_ts + 1 second to now
                                start = max_ts + __import__("datetime").timedelta(
                                    seconds=1
                                )
                                end = datetime.utcnow()
                                logger.info(
                                    "compute.incremental_from_max",
                                    extra={
                                        "feature": feat.name,
                                        "scope": scope_tag,
                                        "max_ts": max_ts.isoformat(),
                                    },
                                )
                        else:
                            start, end = default_window(180)

                        # Start a compute run
                        run_id = start_run(
                            feat,
                            range_start=start,
                            range_end=end,
                            symbol=sym,
                            interval=ivl,
                            conn=conn,
                        )

                        # Compute
                        df = compute(
                            feat,
                            start=start,
                            end=end,
                            conn=conn,
                            symbol=sym,
                            interval=ivl,
                        )

                        overall_computed += len(df) if df is not None else 0

                        # Persist
                        if df is not None and not df.empty:
                            written = write_values(
                                feat, df, run_id=run_id, symbol=sym, interval=ivl, conn=conn
                            )
                            overall_persisted += written
                            finish_run(run_id, rows_written=written, conn=conn)
                            logger.info(
                                "compute.refresh_persisted",
                                extra={
                                    "feature": feat.name,
                                    "scope": scope_tag,
                                    "rows": written,
                                    "run_id": run_id,
                                },
                            )
                        else:
                            finish_run(run_id, rows_written=0, conn=conn)
                            logger.info(
                                "compute.refresh_no_output",
                                extra={
                                    "feature": feat.name,
                                    "scope": scope_tag,
                                    "run_id": run_id,
                                },
                            )

                    except FeatureComputeError as e:
                        err_msg = f"{feat.name}{scope_tag}: {e}"
                        errors.append(err_msg)
                        logger.warning("compute.refresh_failed", extra={
                            "feature": feat.name,
                            "scope": scope_tag,
                            "error": str(e),
                        })
                    except Exception as e:  # noqa: BLE001
                        err_msg = f"{feat.name}{scope_tag}: {type(e).__name__}: {e}"
                        errors.append(err_msg)
                        logger.error("compute.refresh_error", extra={
                            "feature": feat.name,
                            "scope": scope_tag,
                            "error": str(e),
                        })

    status = "ok" if not errors else "partial"
    logger.info("compute.refresh.finish", extra={
        "status": status,
        "computed_rows": overall_computed,
        "persisted_rows": overall_persisted,
        "errors": len(errors),
    })

    return ComputeRefreshResponse(
        status=status,
        computed_rows=overall_computed,
        persisted_rows=overall_persisted,
        errors=errors,
    )
