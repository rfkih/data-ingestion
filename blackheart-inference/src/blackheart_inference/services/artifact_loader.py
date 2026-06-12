"""Load a blackheart-train artifact by content_sha256.

Mirrors ``blackheart_train.artifacts.read_artifact`` so this service can
read every artifact ever written without depending on the training
package as an import. We re-implement rather than depend because:

  * blackheart-train ships ``lightgbm`` + ``scikit-learn`` + the heavy
    feature transformer stack. Inference only needs LightGBM and the
    artifact loader.
  * Decoupling the two services means a training-only refactor cannot
    break inference at the symbol level. The artifact format is the
    contract, not the code.

Artifact path layout: ``<artifact_dir>/<sha256[:2]>/<sha256>.pkl``.

Payload shape (identity covered by ``content_sha256``):

  * ``content_sha256``    str — must match filename's sha
  * ``payload_version``   int — 1 or 2 (v2 carries optional ``ensemble``)
  * ``spec``              dict — ModelSpec frozen-dataclass dump
  * ``feature_names``     list[str] — input column order
  * ``feature_versions``  dict[str,int] | absent — registry versions
                          pinned at train time (older artifacts lack it)
  * ``booster``           lgb.Booster or None (None for ensembles)
  * ``ensemble``          dict or None (v2 ensembles)
  * ``objective``         'binary' | 'regression' | 'multiclass'
  * ``label_feature``     str
  * ``label_version``     int

Integrity model — what is and is NOT protected
----------------------------------------------
``content_sha256`` is blackheart-train's hash over the canonical-JSON of
the model-identity fields ``{spec, feature_names, objective,
label_feature, label_version, booster_model_str}`` (see
``blackheart_train.artifacts.compute_content_sha``). For single-booster
artifacts we RECOMPUTE that hash from the unpickled payload and compare
it to the filename — a payload whose booster or feature list was edited
fails loudly. For ensemble payloads (``booster is None``) the signature
spans train-side ensemble internals we don't ship, so only the
filename-vs-embedded-field consistency check applies.

The recompute cannot run before ``pickle.loads`` — pickle executes code
during deserialisation, so a malicious artifact attacks at load time
regardless of any post-hoc hash. Filesystem permissions on
``artifact_dir`` are the actual security boundary; the hash check
protects against accidental corruption and casual edits, not a hostile
writer. Loads are cached (bounded LRU) keyed by sha — content-addressed
files never go stale, so the cache needs no invalidation.

Forward-compat with v1 artifacts (no ``payload_version`` key): we
backfill ``payload_version=1, ensemble=None`` so consumers can branch
on the version uniformly. Cached payloads are shared across requests —
treat them as read-only.
"""

from __future__ import annotations

import hashlib
import json
import logging
import pickle
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Booster payloads run 1-10 MB unpickled; 16 distinct live models is far
# above anything the registry currently serves.
_CACHE_MAX_ARTIFACTS = 16


def artifact_path(content_sha: str, artifact_dir: Path) -> Path:
    """The on-disk location for a given content_sha."""
    return artifact_dir / content_sha[:2] / f"{content_sha}.pkl"


def _recompute_content_sha(payload: dict[str, Any]) -> str | None:
    """Re-derive blackheart-train's content hash from the payload.

    Returns None when the payload carries no single booster (ensemble or
    empty model body) — those signatures need train-side internals.
    Mirrors ``blackheart_train.train``'s content_dict assembly and
    ``compute_content_sha``'s canonicalisation exactly; verified against
    every artifact on disk (38/38 match, 2026-06-12).
    """
    booster = payload.get("booster")
    if booster is None:
        return None
    content = {
        "spec": payload.get("spec"),
        "feature_names": payload.get("feature_names"),
        "objective": payload.get("objective"),
        "label_feature": payload.get("label_feature"),
        "label_version": payload.get("label_version"),
        "booster_model_str": booster.model_to_string(),
    }
    canonical = json.dumps(content, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


@lru_cache(maxsize=_CACHE_MAX_ARTIFACTS)
def _load_and_verify(
    path_str: str, content_sha: str, verify_content: bool
) -> dict[str, Any]:
    """Cached worker for :func:`read_artifact`. Raises are not cached, so
    a failed load retries on the next call (e.g. after an artifact
    re-sync)."""
    path = Path(path_str)
    try:
        payload = pickle.loads(path.read_bytes())
    except Exception as exc:
        # Unpickle failures include payloads that reference train-only
        # classes (ModuleNotFoundError) — this service cannot serve them,
        # and the caller must see artifact_corrupt, not a raw 500.
        raise ValueError(
            f"artifact unpickle failed at {path}: {exc!r}. The payload may "
            "reference blackheart-train-only classes (ensemble artifacts) "
            "or be truncated/corrupt."
        ) from exc

    stored = payload.get("content_sha256")
    if stored != content_sha:
        raise ValueError(
            f"artifact content_sha mismatch at {path}: "
            f"filename says {content_sha}, payload says {stored!r}"
        )

    if verify_content:
        recomputed = _recompute_content_sha(payload)
        if recomputed is not None and recomputed != content_sha:
            raise ValueError(
                f"artifact content verification FAILED at {path}: recomputed "
                f"sha {recomputed} != filename sha {content_sha}. The payload "
                "body does not match its registered identity (edited model, "
                "partial write, or a lightgbm version whose model_to_string "
                "output drifted from the training environment). Re-train or "
                "re-sync the artifact; to serve anyway set "
                "INFERENCE_ARTIFACT_VERIFY_CONTENT=false."
            )

    payload.setdefault("payload_version", 1)
    payload.setdefault("ensemble", None)
    return payload


def read_artifact(
    content_sha: str,
    artifact_dir: Path,
    *,
    verify_content: bool = True,
) -> dict[str, Any]:
    """Load an artifact, verify identity, return the (cached) payload.

    Raises ``FileNotFoundError`` if the path doesn't exist. Raises
    ``ValueError`` when the payload can't be unpickled, when its embedded
    ``content_sha256`` disagrees with the filename, or — for
    single-booster payloads with ``verify_content=True`` — when the
    recomputed content hash doesn't match the filename. See the module
    docstring for what this does and does not protect against.
    """
    path = artifact_path(content_sha, artifact_dir)
    if not path.exists():
        raise FileNotFoundError(f"artifact not found: {path}")
    return _load_and_verify(str(path), content_sha, verify_content)
