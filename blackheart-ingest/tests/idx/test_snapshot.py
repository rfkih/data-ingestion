"""Study snapshots (idx/snapshot.py): content-addressed blobs, dedupe, verify, file drift - offline (no database)."""
from __future__ import annotations

from pathlib import Path

import pytest

from blackheart_ingest.idx import snapshot as sn


@pytest.fixture()
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("IDX_SNAPSHOT_ROOT", str(tmp_path / "snap"))
    return tmp_path


def test_put_file_dedupes_and_verifies(store: Path) -> None:
    a = store / "a.bin"
    a.write_bytes(b"hello")
    b = store / "b.bin"
    b.write_bytes(b"hello")
    ia, ib = sn.put_file(a), sn.put_file(b)
    assert ia["sha256"] == ib["sha256"] and sn.blob_path(ia["sha256"]).read_bytes() == b"hello"
    man = {"items": {"a": ia}}
    assert sn.verify(man) == []
    sn.blob_path(ia["sha256"]).write_bytes(b"tampered")
    assert "corrupted" in sn.verify(man)[0]
    sn.blob_path(ia["sha256"]).unlink()
    assert "missing" in sn.verify(man)[0]


def test_file_drift_is_reported(store: Path) -> None:
    f = store / "cache.pkl"
    f.write_bytes(b"v1")
    man = {"items": {"cache": sn.put_file(f)}}
    assert sn.drift(None, man) == []                       # no database needed for file items
    f.write_bytes(b"v2")
    assert "changed on disk" in sn.drift(None, man)[0]
    f.unlink()
    assert "no longer exists" in sn.drift(None, man)[0]


def test_query_must_be_ordered() -> None:
    with pytest.raises(ValueError):
        sn.put_query(None, "SELECT 1")


def test_fingerprint_rejects_odd_table_names() -> None:
    with pytest.raises(ValueError):
        sn.fingerprint(None, "idx.bar; drop table x")
