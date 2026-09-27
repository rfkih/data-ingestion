"""Database backups and a restore test (Track A2, operator 2026-09-26: "okay do track A").

Before this the desk had no backup: a disk failure would have lost every book, fill, ticket, journal line and study. The
database runs in the Docker container ``blackheart-postgres-local`` (env IDX_PG_CONTAINER); pg_dump / pg_restore run INSIDE it
(the host has no Postgres client) and the file is copied out with ``docker cp``.

  nightly  ``idx`` schema, custom format, WITHOUT the TimescaleDB hypertables' data (their rows live in chunk tables, and the
           tick tables feed_trade / feed_book are gigabytes) + idx.ml_prediction as gzipped CSV (the kill rule ic:ml reads it).
           Manifest with the row counts of the tables that cannot be rebuilt from a source.
  weekly   the whole database (``--full``), custom format.
  restore  ``restore_test``: the latest nightly into a scratch database in the same container, row counts compared with its
           manifest, scratch dropped. A backup that has never been restored is a hope, not a backup.
Files: data/backups/ under the workspace root (gitignored); kept: 14 nightly, 6 weekly. They sit on the SAME disk as the
database - copy data/backups off the machine (the operator's call where) to survive a disk failure.
"""
from __future__ import annotations

import gzip
import json
import logging
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import psycopg

logger = logging.getLogger(__name__)
WIB = ZoneInfo("Asia/Jakarta")
ROOT = Path(__file__).resolve().parents[4]
KEEP_NIGHTLY, KEEP_WEEKLY = 14, 6
# the tables a restore must bring back row for row (not rebuildable from IDX / Stockbit)
CRITICAL = ("idx.book", "idx.fill", "idx.position", "idx.ticket", "idx.ticket_line", "idx.decision", "idx.study", "idx.study_name",
            "idx.book_nav", "idx.order_intent", "idx.strategy_config_version", "idx.strategy_backtest_trade", "idx.alert")
SCRATCH_DB = "idx_restore_test"


def container() -> str:
    return os.environ.get("IDX_PG_CONTAINER", "blackheart-postgres-local")


def backup_dir() -> Path:
    p = Path(os.environ.get("IDX_BACKUP_DIR") or ROOT / "data" / "backups")
    p.mkdir(parents=True, exist_ok=True)
    return p


def _db(conn: psycopg.Connection) -> tuple[str, str]:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database() AS d, current_user AS u")
        r = cur.fetchone()
    return (r["d"], r["u"]) if isinstance(r, dict) else (r[0], r[1])


def _run(args: list[str], timeout: int = 7200) -> str:
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(f"{' '.join(args[:4])} ... failed ({p.returncode}): {(p.stderr or p.stdout)[-400:]}")
    return p.stdout


def hypertables(conn: psycopg.Connection, schema: str = "idx") -> list[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT hypertable_name FROM timescaledb_information.hypertables WHERE hypertable_schema = %s ORDER BY 1", (schema,))
        return [f"{schema}.{r['hypertable_name'] if isinstance(r, dict) else r[0]}" for r in cur.fetchall()]


def counts(conn: psycopg.Connection, tables: tuple[str, ...] = CRITICAL) -> dict[str, int]:
    out = {}
    with conn.cursor() as cur:
        for t in tables:
            cur.execute(f"SELECT count(*) AS n FROM {t}")
            r = cur.fetchone()
            out[t] = int(r["n"] if isinstance(r, dict) else r[0])
    return out


def rotate(kind: str, keep: int) -> list[str]:
    files = sorted(backup_dir().glob(f"{kind}_*.dump"))
    gone = []
    for f in files[:-keep] if keep else []:
        for sib in (f, f.with_suffix(".json"), f.with_name(f.stem + "_ml_prediction.csv.gz")):
            if sib.exists():
                sib.unlink()
        gone.append(f.name)
    return gone


def backup(conn: psycopg.Connection, full: bool = False) -> dict[str, Any]:
    db, user = _db(conn)
    kind = "full" if full else "nightly"
    stamp = datetime.now(WIB).strftime("%Y%m%d_%H%M")
    name = f"{kind}_{stamp}.dump"
    inside = f"/tmp/{name}"
    before = counts(conn)
    args = ["docker", "exec", container(), "pg_dump", "-U", user, "-d", db, "-Fc", "-f", inside]
    hts = []
    if not full:
        hts = hypertables(conn)
        args += ["-n", "idx"] + [f"--exclude-table-data={t}" for t in hts]
    _run(args)
    dst = backup_dir() / name
    _run(["docker", "cp", f"{container()}:{inside}", str(dst)])
    _run(["docker", "exec", container(), "rm", "-f", inside])
    ml_rows = None
    if not full:
        ml = dst.with_name(dst.stem + "_ml_prediction.csv.gz")
        with conn.cursor() as cur, gzip.open(ml, "wb") as f:
            with cur.copy("COPY (SELECT * FROM idx.ml_prediction ORDER BY made_at, code, horizon) TO STDOUT WITH CSV HEADER") as cp:
                for block in cp:
                    f.write(block)
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS n FROM idx.ml_prediction")
            r = cur.fetchone()
            ml_rows = int(r["n"] if isinstance(r, dict) else r[0])
    man = {"file": name, "kind": kind, "db": db, "created": datetime.now(WIB).isoformat(), "bytes": dst.stat().st_size,
           "counts": before, "hypertables_data_excluded": hts, "ml_prediction_rows": ml_rows}
    dst.with_suffix(".json").write_text(json.dumps(man, indent=1))
    man["rotated"] = rotate(kind, KEEP_WEEKLY if full else KEEP_NIGHTLY)
    return man


def latest(kind: str = "nightly") -> Path | None:
    files = sorted(backup_dir().glob(f"{kind}_*.dump"))
    return files[-1] if files else None


def restore_test(conn: psycopg.Connection, dump: Path | None = None) -> dict[str, Any]:
    """Restore a nightly dump into a scratch database and compare the critical row counts with its manifest."""
    dump = dump or latest("nightly")
    if dump is None:
        raise FileNotFoundError("no nightly backup to restore")
    man = json.loads(dump.with_suffix(".json").read_text())
    _db_name, user = _db(conn)
    c = container()
    inside = f"/tmp/{dump.name}"
    _run(["docker", "cp", str(dump), f"{c}:{inside}"])
    try:
        _run(["docker", "exec", c, "psql", "-U", user, "-d", "postgres", "-c", f"DROP DATABASE IF EXISTS {SCRATCH_DB}"])
        _run(["docker", "exec", c, "psql", "-U", user, "-d", "postgres", "-c", f"CREATE DATABASE {SCRATCH_DB}"])
        _run(["docker", "exec", c, "psql", "-U", user, "-d", SCRATCH_DB, "-c", "CREATE EXTENSION IF NOT EXISTS timescaledb"])
        # errors on TimescaleDB catalog objects are expected for a schema-only-of-hypertables restore; the counts decide
        subprocess.run(["docker", "exec", c, "pg_restore", "-U", user, "-d", SCRATCH_DB, "--no-owner", inside],
                       capture_output=True, text=True, timeout=7200)
        got = {}
        for t in man["counts"]:
            out = _run(["docker", "exec", c, "psql", "-U", user, "-d", SCRATCH_DB, "-tAc", f"SELECT count(*) FROM {t}"])
            got[t] = int(out.strip() or -1)
    finally:
        subprocess.run(["docker", "exec", c, "psql", "-U", user, "-d", "postgres", "-c", f"DROP DATABASE IF EXISTS {SCRATCH_DB}"],
                       capture_output=True, text=True, timeout=600)
        subprocess.run(["docker", "exec", c, "rm", "-f", inside], capture_output=True, text=True, timeout=60)
    bad = {t: (man["counts"][t], got.get(t)) for t in man["counts"] if got.get(t) != man["counts"][t]}
    return {"dump": dump.name, "ok": not bad, "mismatch": bad, "checked": len(man["counts"])}


def copy_offsite(dest: str) -> int:
    """Mirror data/backups to another folder (an external drive or a synced folder). -> files copied."""
    d = Path(dest)
    d.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in backup_dir().iterdir():
        t = d / f.name
        if not t.exists() or t.stat().st_size != f.stat().st_size:
            shutil.copy2(f, t)
            n += 1
    return n
