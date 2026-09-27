"""Tamper-evident signal ledger (evidence plan item 3, operator 2026-09-26: "okay do all").

A track record convinces an outsider only if the signals provably existed BEFORE the prices that judged them. Every combo
plan (21:10/21:40: tomorrow's lines and ML watch levels) and every morning gap scan (09:00: the lines bought at the open) is
sealed here the moment it is made:

  payload_sha = sha256(canonical JSON of the signal)
  entry_sha   = sha256(prev entry_sha | sealed_at | book | event | payload_sha)   - a hash chain: editing or deleting any past
                                                                                   entry breaks every later hash (``verify``)
Each entry is also appended to data/signal-ledger/ledger.jsonl and committed in that folder's own git repository. The chain
proves ORDER and INTEGRITY on this machine; the external TIME proof is a push of that repository to a remote the operator
chooses (``git -C data/signal-ledger remote add origin <url>``) - once a remote exists, every seal pushes. Never raises into
the trading job that calls it.
"""
from __future__ import annotations

import hashlib
import json
import logging
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[4]
REPO = ROOT / "data" / "signal-ledger"
GENESIS = "0" * 64


def canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True)


def sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def entry_hash(prev: str, sealed_at: str, book: str, event: str, payload_sha: str) -> str:
    return sha("|".join((prev, sealed_at, book, event, payload_sha)))


def _last(conn: psycopg.Connection) -> str:
    with conn.cursor() as cur:
        cur.execute("SELECT entry_sha FROM idx.signal_ledger ORDER BY seq DESC LIMIT 1")
        r = cur.fetchone()
    if not r:
        return GENESIS
    return r["entry_sha"] if isinstance(r, dict) else r[0]


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True, timeout=60)


def ensure_repo() -> None:
    if (REPO / ".git").exists():
        return
    REPO.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(REPO)], capture_output=True, text=True, timeout=60)
    (REPO / "README.md").write_text("Blackheart IDX signal ledger: one sealed line per combo plan / gap scan (idx/signal_ledger.py).\n"
                                    "Verify: python -m blackheart_ingest.idx.signal_ledger verify\n", encoding="utf-8")
    _git("add", "README.md")
    _git("-c", "user.name=blackheart-ledger", "-c", "user.email=ledger@localhost", "commit", "-q", "-m", "ledger genesis")


def seal(conn: psycopg.Connection, book: str, event: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    """Seal one signal set. -> the entry, or None when sealing failed (logged, never raised)."""
    try:
        sealed_at = datetime.now(UTC).isoformat(timespec="microseconds")
        body = canonical(payload)
        p_sha = sha(body)
        with conn.cursor() as cur:
            cur.execute("LOCK TABLE idx.signal_ledger IN EXCLUSIVE MODE")
            prev = _last(conn)
            e_sha = entry_hash(prev, sealed_at, book, event, p_sha)
            cur.execute("""INSERT INTO idx.signal_ledger (sealed_at, book, event, payload, payload_sha, prev_sha, entry_sha)
                           VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s)""", (sealed_at, book, event, body, p_sha, prev, e_sha))
        conn.commit()
        entry = {"sealed_at": sealed_at, "book": book, "event": event, "payload_sha": p_sha, "prev_sha": prev, "entry_sha": e_sha, "payload": payload}
        try:
            ensure_repo()
            with open(REPO / "ledger.jsonl", "a", encoding="utf-8") as f:
                f.write(canonical(entry) + "\n")
            _git("add", "ledger.jsonl")
            _git("-c", "user.name=blackheart-ledger", "-c", "user.email=ledger@localhost", "commit", "-q", "-m", f"{event} {book} {e_sha[:12]}")
            if _git("remote").stdout.strip():                          # an external anchor exists only once the operator adds one
                _git("push", "-q", "origin", "HEAD")
        except Exception:
            logger.exception("signal ledger: git mirror failed (the database entry stands)")
        return entry
    except Exception:
        conn.rollback()
        logger.exception("signal ledger: seal failed for %s %s", book, event)
        return None


def verify_rows(rows: list[dict[str, Any]]) -> list[str]:
    """Pure. Rows in seq order -> problems ([] = the chain is intact)."""
    bad, prev = [], GENESIS
    for r in rows:
        body = canonical(r["payload"])
        if sha(body) != r["payload_sha"]:
            bad.append(f"#{r['seq']}: payload changed after sealing")
        if r["prev_sha"] != prev:
            bad.append(f"#{r['seq']}: chain broken (an entry before it was removed or reordered)")
        sealed = r["sealed_at"] if isinstance(r["sealed_at"], str) else r["sealed_at"].astimezone(UTC).isoformat(timespec="microseconds")
        if entry_hash(r["prev_sha"], sealed, r["book"], r["event"], r["payload_sha"]) != r["entry_sha"]:
            bad.append(f"#{r['seq']}: entry hash does not match its fields")
        prev = r["entry_sha"]
    return bad


def verify(conn: psycopg.Connection) -> list[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT seq, sealed_at, book, event, payload, payload_sha, prev_sha, entry_sha FROM idx.signal_ledger ORDER BY seq")
        cols = [c.name for c in cur.description]
        rows = [r if isinstance(r, dict) else dict(zip(cols, r, strict=True)) for r in cur.fetchall()]
    return verify_rows(rows)


def main() -> int:
    import sys

    from ..shared.db import get_connection
    with get_connection() as conn:
        bad = verify(conn)
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS n FROM idx.signal_ledger")
            r = cur.fetchone()
    n = r["n"] if isinstance(r, dict) else r[0]
    print(f"signal ledger: {n} entries, " + ("chain intact" if not bad else f"{len(bad)} problem(s)"))
    for b in bad:
        print("  " + b)
    sys.exit(0 if not bad else 1)


if __name__ == "__main__":
    main()
