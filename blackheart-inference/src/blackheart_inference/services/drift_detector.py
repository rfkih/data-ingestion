"""Population Stability Index (PSI) feature-drift detection.

Scorecard #12 (decay monitoring). Pure logic — no DB, no I/O — so it is fully
unit-testable in this repo's "pure-logic only" test discipline. The repo layer
(`repo/drift.py`) supplies the baseline + live value arrays; the API layer
(`api/drift_monitoring.py`) wires it to HTTP and structured-log alerts.

PSI measures how much a feature's live distribution has moved away from a
baseline (training-era) distribution. Industry-standard interpretation:

    PSI < 0.10            no significant shift          -> OK
    0.10 <= PSI < 0.25    moderate shift, watch it      -> WARN
    PSI >= 0.25           significant shift, act         -> DRIFT

A model whose inputs have DRIFTed is a prime retrain candidate — that's the
automated-retrain trigger the platform lacked.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

# Interpretation thresholds (standard credit-risk / ML-monitoring convention).
PSI_OK_BELOW = 0.10
PSI_DRIFT_AT_OR_ABOVE = 0.25
DEFAULT_BINS = 10

# Smoothing floor so an empty bin can't produce log(0) / divide-by-zero.
_EPS = 1e-6

# A feature needs at least this many baseline points to bin meaningfully.
_MIN_BASELINE = 20
_MIN_LIVE = 5


class DriftVerdict(str, Enum):
    OK = "OK"
    WARN = "WARN"
    DRIFT = "DRIFT"
    INSUFFICIENT = "INSUFFICIENT"  # not enough data to judge — surfaced, never silent


@dataclass(frozen=True)
class FeaturePsi:
    feature: str
    psi: float
    verdict: DriftVerdict
    baseline_n: int
    live_n: int


@dataclass(frozen=True)
class DriftReport:
    features: list[FeaturePsi]  # sorted by PSI descending
    max_psi: float
    drift_count: int
    warn_count: int
    retrain_recommended: bool
    note: str


def _verdict(psi: float) -> DriftVerdict:
    if psi < PSI_OK_BELOW:
        return DriftVerdict.OK
    if psi < PSI_DRIFT_AT_OR_ABOVE:
        return DriftVerdict.WARN
    return DriftVerdict.DRIFT


def _quantile_edges(sorted_vals: list[float], bins: int) -> list[float]:
    """Interior bin edges from baseline quantiles. Dedup collapses flat regions
    (a near-constant feature yields few bins, which is correct — there is little
    distribution to drift)."""
    edges: list[float] = []
    n = len(sorted_vals)
    for i in range(1, bins):
        idx = min(n - 1, (i * n) // bins)
        edge = sorted_vals[idx]
        if not edges or edge > edges[-1]:
            edges.append(edge)
    return edges


def _bin_fractions(values: list[float], edges: list[float]) -> list[float]:
    """Fraction of `values` falling in each of len(edges)+1 bins."""
    nbins = len(edges) + 1
    counts = [0] * nbins
    for v in values:
        placed = nbins - 1
        for i, edge in enumerate(edges):
            if v <= edge:
                placed = i
                break
        counts[placed] += 1
    total = len(values)
    if total == 0:
        return [0.0] * nbins
    return [c / total for c in counts]


def compute_feature_psi(
    feature: str,
    baseline: list[float],
    live: list[float],
    bins: int = DEFAULT_BINS,
) -> FeaturePsi:
    """PSI of `live` vs `baseline` for one feature. Bins are defined on the
    baseline so the comparison is "how did live move relative to training"."""
    base = [float(v) for v in baseline if v is not None]
    liv = [float(v) for v in live if v is not None]
    if len(base) < _MIN_BASELINE or len(liv) < _MIN_LIVE:
        return FeaturePsi(feature, 0.0, DriftVerdict.INSUFFICIENT, len(base), len(liv))

    edges = _quantile_edges(sorted(base), bins)
    base_frac = _bin_fractions(base, edges)
    live_frac = _bin_fractions(liv, edges)

    psi = 0.0
    for b, l in zip(base_frac, live_frac):
        b_adj = max(b, _EPS)
        l_adj = max(l, _EPS)
        psi += (l_adj - b_adj) * math.log(l_adj / b_adj)
    psi = abs(psi)  # PSI is non-negative; guard float noise near zero

    return FeaturePsi(feature, psi, _verdict(psi), len(base), len(liv))


def build_drift_report(
    per_feature: dict[str, tuple[list[float], list[float]]],
    *,
    bins: int = DEFAULT_BINS,
    retrain_drift_threshold: int = 1,
) -> DriftReport:
    """Aggregate per-feature PSI into a book-level drift verdict + retrain
    recommendation. `per_feature` maps feature_name -> (baseline_vals, live_vals).
    Retrain is recommended once `retrain_drift_threshold` features hit DRIFT."""
    feats = [
        compute_feature_psi(name, base, live, bins)
        for name, (base, live) in per_feature.items()
    ]
    feats.sort(key=lambda f: f.psi, reverse=True)

    drift_count = sum(1 for f in feats if f.verdict is DriftVerdict.DRIFT)
    warn_count = sum(1 for f in feats if f.verdict is DriftVerdict.WARN)
    insufficient = sum(1 for f in feats if f.verdict is DriftVerdict.INSUFFICIENT)
    max_psi = feats[0].psi if feats else 0.0
    retrain = drift_count >= retrain_drift_threshold

    if drift_count == 0 and warn_count == 0 and insufficient == 0:
        note = "OK"
    else:
        note = f"{drift_count} drift, {warn_count} warn, {insufficient} insufficient-data"

    return DriftReport(feats, max_psi, drift_count, warn_count, retrain, note)
