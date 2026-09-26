"""Study snapshots - the exact inputs of a research run, content-addressed, so a result can be re-derived after the data moves.

Why (operator 2026-09-26, item 3): the desk's baseline moved several times under it (the adj_factor repair, the Yahoo opens) and
old studies could no longer be reproduced to the digit. A snapshot pins three kinds of input:

  files        a cache the study read (tmp/ml_strategy_cache.pkl ...) - copied once into the blob store, named by its sha256
  queries      a SELECT the study ran - its result written as parquet into the blob store (rows must be ORDER BY'ed)
  fingerprints a whole table or slice, too big to copy: row count + an order-independent sum of row hashes; cheap to recompute,
               so ``drift`` can say "idx.bar changed since study #380" without keeping a copy of it

Blob store: data/snapshots/blobs/<sha[:2]>/<sha> under the workspace root (gitignored /data/), or $IDX_SNAPSHOT_ROOT. A blob is
written once and shared by every study that uses the same bytes. Manifests go to idx.study_snapshot (migration 0055).

    python -m blackheart_ingest.idx.snapshot verify <study_id>     every blob present and its hash intact
    python -m blackheart_ingest.idx.snapshot drift <study_id>      which fingerprints / queries differ from the database today
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg

ROOT = Path(__file__).resolve().parents[4]                      # C:/Project
CHUNK = 1 << 20


def store_root() -> Path:
    return Path(os.environ.get("IDX_SNAPSHOT_ROOT") or ROOT / "data" / "snapshots")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while b := f.read(CHUNK):
            h.update(b)
    return h.hexdigest()


def blob_path(sha: str) -> Path:
    return store_root() / "blobs" / sha[:2] / sha


def put_file(path: str | Path) -> dict[str, Any]:
    """Copy a file into the blob store (once). -> {sha256, bytes, source}."""
    p = Path(path)
    sha = sha256_file(p)
    dst = blob_path(sha)
    if not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_suffix(".part")
        shutil.copyfile(p, tmp)
        os.replace(tmp, dst)
    return {"kind": "file", "sha256": sha, "bytes": p.stat().st_size, "source": str(p.resolve())}


def put_query(conn: psycopg.Connection, sql: str, params: tuple | dict | None = None) -> dict[str, Any]:
    """Run a SELECT and store its result as parquet. The SQL must ORDER BY so the bytes are stable."""
    import pandas as pd
    if "order by" not in sql.lower():
        raise ValueError("a snapshot query must ORDER BY (stable bytes)")
    with conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [c.name for c in cur.description]
        rows = cur.fetchall()
    rows = [tuple(r.values()) if isinstance(r, dict) else tuple(r) for r in rows]
    df = pd.DataFrame(rows, columns=cols)
    for c in df.columns:                                         # Decimal / mixed objects -> strings: parquet-safe and lossless
        if df[c].dtype == object:
            df[c] = df[c].map(lambda v: None if v is None else str(v))
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "q.parquet"
        df.to_parquet(f, index=False, engine="pyarrow")
        out = put_file(f)
    return {**out, "kind": "query", "sql": sql, "params": _jsonable(params), "rows": len(df), "source": None}


def fingerprint(conn: psycopg.Connection, table: str, where: str | None = None, params: tuple | None = None) -> dict[str, Any]:
    """Row count + order-independent hash sum of a table (slice). Detects any changed, added or removed row."""
    if not all(ch.isalnum() or ch in "._" for ch in table):
        raise ValueError(f"bad table name {table!r}")
    sql = f"SELECT count(*) AS n, COALESCE(sum(hashtextextended(t::text, 0)::numeric), 0)::text AS h FROM {table} t" + (f" WHERE {where}" if where else "")
    with conn.cursor() as cur:
        cur.execute(sql, params)
        r = cur.fetchone()
    n, h = (r["n"], r["h"]) if isinstance(r, dict) else r
    return {"kind": "fingerprint", "table": table, "where": where, "params": _jsonable(params), "rows": int(n), "hash": str(h)}


def git_commit() -> str | None:
    try:
        return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def snapshot(conn: psycopg.Connection, study_id: int | None, *, files: dict[str, str] | None = None,
             queries: dict[str, tuple[str, Any]] | None = None, fingerprints: dict[str, tuple[str, str | None]] | None = None,
             script: str | None = None, note: str | None = None) -> dict[str, Any]:
    """Pin a study's inputs. files: {name: path}; queries: {name: (sql, params)}; fingerprints: {name: (table, where)}.
    ``script`` = the research script path (its bytes are pinned too). Stored on idx.study_snapshot when ``study_id``."""
    items: dict[str, Any] = {}
    for k, p in (files or {}).items():
        items[k] = put_file(p)
    if script:
        items["_script"] = {**put_file(script), "kind": "script"}
    for k, (sql, params) in (queries or {}).items():
        items[k] = put_query(conn, sql, params)
    for k, (table, where) in (fingerprints or {}).items():
        items[k] = fingerprint(conn, table, where)
    man = {"created": datetime.now(UTC).isoformat(), "git_commit": git_commit(), "store": str(store_root()), "note": note, "items": items}
    if study_id is not None:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO idx.study_snapshot (study_id, git_commit, manifest) VALUES (%s, %s, %s::jsonb)",
                        (study_id, man["git_commit"], json.dumps(man)))
        conn.commit()
    return man


def manifest_of(conn: psycopg.Connection, study_id: int) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute("SELECT manifest FROM idx.study_snapshot WHERE study_id = %s ORDER BY created_at DESC LIMIT 1", (study_id,))
        r = cur.fetchone()
    if not r:
        return None
    m = r["manifest"] if isinstance(r, dict) else r[0]
    return json.loads(m) if isinstance(m, str) else m


def verify(man: dict[str, Any]) -> list[str]:
    """Every blob present with its hash intact. -> problems ([] = good)."""
    bad = []
    for k, it in man["items"].items():
        if "sha256" not in it:
            continue
        p = blob_path(it["sha256"])
        if not p.exists():
            bad.append(f"{k}: blob missing ({it['sha256'][:12]})")
        elif sha256_file(p) != it["sha256"]:
            bad.append(f"{k}: blob corrupted ({it['sha256'][:12]})")
    return bad


def drift(conn: psycopg.Connection, man: dict[str, Any]) -> list[str]:
    """Inputs that differ from the database / disk today. -> lines ([] = nothing moved)."""
    out = []
    for k, it in man["items"].items():
        if it["kind"] == "fingerprint":
            now = fingerprint(conn, it["table"], it.get("where"), tuple(it["params"]) if it.get("params") else None)
            if (now["rows"], now["hash"]) != (it["rows"], it["hash"]):
                out.append(f"{k}: {it['table']} changed ({it['rows']:,} -> {now['rows']:,} rows)")
        elif it["kind"] == "query":
            now = put_query(conn, it["sql"], tuple(it["params"]) if isinstance(it.get("params"), list) else it.get("params"))
            if now["sha256"] != it["sha256"]:
                out.append(f"{k}: query result changed ({it['rows']:,} -> {now['rows']:,} rows)")
        elif it["kind"] in ("file", "script") and it.get("source"):
            p = Path(it["source"])
            p = p if p.is_absolute() else ROOT / p                     # manifests written before 2026-09-26 21:xx kept relative paths
            if not p.exists():
                out.append(f"{k}: {p} no longer exists (the blob still does)")
            elif sha256_file(p) != it["sha256"]:
                out.append(f"{k}: {p} changed on disk since the study (the pinned copy is {it['sha256'][:12]})")
    return out


def load_query(man: dict[str, Any], name: str):
    """A pinned query result back as a DataFrame (values as the database printed them)."""
    import pandas as pd
    return pd.read_parquet(blob_path(man["items"][name]["sha256"]))


def _jsonable(v: Any) -> Any:
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    if v is None or isinstance(v, (int, float, str, bool)):
        return v
    return str(v)


def main(argv: list[str] | None = None) -> int:
    from ..shared.db import get_connection
    ap = argparse.ArgumentParser(prog="idx snapshot")
    ap.add_argument("cmd", choices=["verify", "drift", "show"])
    ap.add_argument("study_id", type=int)
    a = ap.parse_args(argv)
    with get_connection() as conn:
        man = manifest_of(conn, a.study_id)
        if man is None:
            print(f"study #{a.study_id} has no snapshot")
            return 2
        if a.cmd == "show":
            print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "sql"} for k, v in man["items"].items()}, indent=1))
            return 0
        res = verify(man) if a.cmd == "verify" else drift(conn, man)
        print(f"study #{a.study_id} {a.cmd}: " + ("OK" if not res else f"{len(res)} issue(s)"))
        for line in res:
            print("  " + line)
        return 0 if not res else 1


if __name__ == "__main__":
    sys.exit(main())
