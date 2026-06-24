"""Feature-drift (PSI) monitoring endpoint — scorecard #12 decay monitoring.

Compares each feature's recent LIVE window against an older BASELINE window
(both from ``feature_values``) and returns per-feature PSI, an overall verdict,
and a retrain recommendation. Read-only — it never affects inference. When drift
crosses the retrain threshold it also emits a structured-log warning so it
alerts through the same log pipeline as the rest of the sidecar.

Baseline source: an older feature_values window (no stored training-distribution
snapshot exists yet — see repo map). When a per-model baseline table lands, swap
the baseline query without touching the detector or endpoint shape.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import asyncpg
from fastapi import APIRouter, Depends, Query

from ..logging import get_logger
from ..repo.drift import fetch_feature_window
from ..services.drift_detector import build_drift_report
from .deps import get_db_conn

log = get_logger(__name__)

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


def _parse_features(spec: str) -> list[tuple[str, int]]:
    """Parse ``name:version`` comma list, e.g. ``rsi_14:1,ema_50:1``. Version
    defaults to 1 when omitted."""
    out: list[tuple[str, int]] = []
    for item in spec.split(","):
        item = item.strip()
        if not item:
            continue
        name, _, ver = item.partition(":")
        name = name.strip()
        if not name:
            continue
        out.append((name, int(ver) if ver.strip() else 1))
    return out


@router.get("/drift")
async def feature_drift(
    symbol: str = Query("", description="symbol; empty string for global/macro features"),
    interval: str = Query("", description="bar interval, e.g. 1h; empty for global"),
    features: str = Query(..., description="comma-separated feature_name:version"),
    live_days: int = Query(7, ge=1, le=90),
    baseline_days: int = Query(90, ge=7, le=730),
    conn: asyncpg.Connection = Depends(get_db_conn),
) -> dict:
    now = datetime.now(timezone.utc)
    live_start = now - timedelta(days=live_days)
    baseline_end = live_start
    baseline_start = baseline_end - timedelta(days=baseline_days)

    per_feature: dict[str, tuple[list[float], list[float]]] = {}
    for name, version in _parse_features(features):
        baseline = await fetch_feature_window(
            conn, name, version, symbol, interval, baseline_start, baseline_end
        )
        live = await fetch_feature_window(
            conn, name, version, symbol, interval, live_start, now
        )
        per_feature[name] = (baseline, live)

    report = build_drift_report(per_feature)

    if report.retrain_recommended:
        log.warning(
            "inference.feature_drift_detected",
            symbol=symbol,
            interval=interval,
            max_psi=round(report.max_psi, 4),
            drift_count=report.drift_count,
            warn_count=report.warn_count,
        )

    return {
        "symbol": symbol,
        "interval": interval,
        "live_window_days": live_days,
        "baseline_window_days": baseline_days,
        "max_psi": round(report.max_psi, 6),
        "drift_count": report.drift_count,
        "warn_count": report.warn_count,
        "retrain_recommended": report.retrain_recommended,
        "note": report.note,
        "features": [
            {
                "feature": f.feature,
                "psi": round(f.psi, 6),
                "verdict": f.verdict.value,
                "baseline_n": f.baseline_n,
                "live_n": f.live_n,
            }
            for f in report.features
        ],
    }
