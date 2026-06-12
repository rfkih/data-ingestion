"""Test artifact_loader against real blackheart-train artifacts when
available, plus a synthesised artifact for the round-trip / tamper cases.

Skipped if blackheart-train's artifact directory isn't on disk — keeps
the suite green on a fresh checkout without the training side mounted.
"""

from __future__ import annotations

import hashlib
import json
import os
import pickle
from pathlib import Path

import pytest

from blackheart_inference.services.artifact_loader import (
    artifact_path,
    read_artifact,
)


_REAL_ARTIFACT_DIR = Path("C:/Project/blackheart-train/artifacts")


def _find_real_artifact_shas() -> list[str]:
    """All real artifact shas on disk. Some payloads pickle train-only
    classes (ensembles) the sidecar can't import — the round-trip test
    iterates until one loads, so a single such artifact doesn't fail
    the suite (read_artifact correctly refuses it with ValueError)."""
    if not _REAL_ARTIFACT_DIR.exists():
        return []
    shas: list[str] = []
    for shard in sorted(os.listdir(_REAL_ARTIFACT_DIR)):
        shard_dir = _REAL_ARTIFACT_DIR / shard
        if not shard_dir.is_dir():
            continue
        for f in sorted(os.listdir(shard_dir)):
            if f.endswith(".pkl"):
                shas.append(f[:-4])
    return shas


@pytest.mark.skipif(
    not _find_real_artifact_shas(),
    reason="No real blackheart-train artifacts on disk; skipping integration check.",
)
def test_read_real_artifact_round_trips_sha() -> None:
    payload = None
    sha = None
    for candidate in _find_real_artifact_shas():
        try:
            payload = read_artifact(candidate, _REAL_ARTIFACT_DIR)
            sha = candidate
            break
        except ValueError:
            continue  # train-only ensemble payload — refusal is correct
    if payload is None:
        pytest.skip("no sidecar-loadable artifact on disk")
    assert payload["content_sha256"] == sha
    # blackheart-train v2 artifacts persist feature_names as a tuple
    # (ds.feature_names is built via tuple() in loader). Inference coerces
    # to list at the predictor boundary; this loader doesn't transform.
    assert isinstance(payload["feature_names"], (list, tuple))
    assert len(payload["feature_names"]) > 0
    assert payload["objective"] in ("binary", "regression", "multiclass")
    # v1 → v2 backfill: keys must be populated even on old artifacts.
    assert "payload_version" in payload
    assert "ensemble" in payload


def test_artifact_not_found_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        read_artifact("0" * 64, tmp_path)


def test_artifact_sha_mismatch_raises(tmp_path: Path) -> None:
    """Tamper detection: if the payload's content_sha256 doesn't match
    the filename, refuse to load."""
    # Synthesise a payload whose self-reported sha disagrees with where
    # we write it. We don't need a real booster — only the loader needs
    # to read enough to check the sha field.
    real_content = {"k": 1}
    real_sha = hashlib.sha256(
        json.dumps(real_content, sort_keys=True).encode()
    ).hexdigest()
    fake_sha = "1" + real_sha[1:]  # one-char tamper
    payload = {
        "content_sha256": real_sha,
        "spec": {"name": "synth"},
        "feature_names": [],
        "booster": None,
        "ensemble": None,
        "objective": "binary",
    }
    # Write at the FAKE sha's path so filename != self-reported sha.
    target = artifact_path(fake_sha, tmp_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(pickle.dumps(payload, protocol=5))
    with pytest.raises(ValueError, match="content_sha mismatch"):
        read_artifact(fake_sha, tmp_path)


def test_artifact_path_uses_two_char_shard(tmp_path: Path) -> None:
    sha = "abcdef" + "0" * 58
    p = artifact_path(sha, tmp_path)
    assert p.parent.name == "ab"
    assert p.name == f"{sha}.pkl"


# ── content verification (recompute, not just embedded-field echo) ─────────


def _train_tiny_booster():
    import lightgbm as lgb
    import numpy as np

    X = np.array([[0.0, 0.0], [0.0, 1.0], [1.0, 0.0], [1.0, 1.0]], dtype=np.float64)
    y = np.array([0, 0, 1, 1], dtype=np.int32)
    return lgb.train(
        {"objective": "binary", "num_leaves": 2, "min_data_in_leaf": 1,
         "min_data_in_bin": 1, "verbose": -1, "seed": 7},
        lgb.Dataset(X, label=y),
        num_boost_round=2,
    )


def _write_train_style_artifact(tmp_path: Path, *, tamper_booster: bool) -> str:
    """Build an artifact exactly the way blackheart-train does: hash the
    content dict {spec, feature_names, objective, label_feature,
    label_version, booster_model_str} via canonical JSON, embed the sha,
    write at the sha's path. With ``tamper_booster=True``, swap in a
    DIFFERENT booster after hashing — the embedded sha still matches the
    filename, so only a real recompute can catch it."""
    booster = _train_tiny_booster()
    content = {
        "spec": {"name": "synth_verify"},
        "feature_names": ["f0", "f1"],
        "objective": "binary",
        "label_feature": "label_x",
        "label_version": 1,
        "booster_model_str": booster.model_to_string(),
    }
    sha = hashlib.sha256(
        json.dumps(content, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    if tamper_booster:
        import lightgbm as lgb
        import numpy as np

        X = np.array([[0.0], [1.0], [0.0], [1.0]], dtype=np.float64)
        y = np.array([1, 0, 1, 0], dtype=np.int32)
        booster = lgb.train(
            {"objective": "binary", "num_leaves": 2, "min_data_in_leaf": 1,
             "min_data_in_bin": 1, "verbose": -1, "seed": 8},
            lgb.Dataset(X, label=y),
            num_boost_round=2,
        )
    payload = {
        "content_sha256": sha,
        "spec": content["spec"],
        "feature_names": content["feature_names"],
        "objective": content["objective"],
        "label_feature": content["label_feature"],
        "label_version": content["label_version"],
        "booster": booster,
        "ensemble": None,
    }
    target = artifact_path(sha, tmp_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(pickle.dumps(payload, protocol=5))
    return sha


def test_content_verification_accepts_untampered_artifact(tmp_path: Path) -> None:
    sha = _write_train_style_artifact(tmp_path, tamper_booster=False)
    payload = read_artifact(sha, tmp_path, verify_content=True)
    assert payload["content_sha256"] == sha


def test_content_verification_rejects_tampered_booster(tmp_path: Path) -> None:
    """The embedded content_sha256 matches the filename, but the booster
    body was swapped — the pre-fix loader accepted this silently."""
    sha = _write_train_style_artifact(tmp_path, tamper_booster=True)
    with pytest.raises(ValueError, match="content verification FAILED"):
        read_artifact(sha, tmp_path, verify_content=True)


def test_content_verification_escape_hatch(tmp_path: Path) -> None:
    """verify_content=False (INFERENCE_ARTIFACT_VERIFY_CONTENT=false)
    falls back to the filename-vs-embedded-field consistency check."""
    sha = _write_train_style_artifact(tmp_path, tamper_booster=True)
    payload = read_artifact(sha, tmp_path, verify_content=False)
    assert payload["content_sha256"] == sha


def test_unpicklable_artifact_raises_value_error(tmp_path: Path) -> None:
    """Truncated/corrupt bytes (or train-only classes) must surface as
    ValueError → 502 artifact_corrupt, not an unhandled 500."""
    sha = "ab" + "1" * 62
    target = artifact_path(sha, tmp_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"\x80\x05 this is not a pickle")
    with pytest.raises(ValueError, match="unpickle failed"):
        read_artifact(sha, tmp_path)
