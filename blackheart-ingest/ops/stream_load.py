"""Load check for the alert stream: N browsers on one worker, M rows, how many arrive and how late.

Not a unit test - a measurement against the running worker, so the numbers are real. Read-only apart from the alerts
it writes and deletes itself (job = 'loadtest').

    INGEST_DB_DSN=... python stream_load.py [clients] [rows]
"""
from __future__ import annotations

import os
import statistics
import sys
import threading
import time
import urllib.request

import psycopg

URL = os.environ.get("IDX_URL", "http://127.0.0.1:8001") + "/idx/stream?kinds=ops"
CLIENTS = int(sys.argv[1]) if len(sys.argv) > 1 else 20
ROWS = int(sys.argv[2]) if len(sys.argv) > 2 else 25
JOB = "loadtest"


def reader(i: int, got: dict[int, list[tuple[int, float]]], ready: threading.Event, stop: threading.Event) -> None:
    try:
        with urllib.request.urlopen(URL, timeout=60) as r:
            got[i] = []
            ready.set()
            for raw in r:
                line = raw.decode("utf-8", "replace").strip()
                if line.startswith("id: "):
                    got[i].append((int(line[4:]), time.monotonic()))
                if stop.is_set():
                    break
    except Exception as e:
        print(f"client {i}: {type(e).__name__}: {e}")


def main() -> None:
    dsn = os.environ["INGEST_DB_DSN"]
    conn = psycopg.connect(dsn, autocommit=True)
    got: dict[int, list[tuple[int, float]]] = {}
    stop = threading.Event()
    threads = []
    t0 = time.monotonic()
    for i in range(CLIENTS):
        ready = threading.Event()
        t = threading.Thread(target=reader, args=(i, got, ready, stop), daemon=True)
        t.start()
        threads.append(t)
        ready.wait(timeout=5)
    connected = len(got)
    print(f"{connected}/{CLIENTS} clients connected in {time.monotonic() - t0:.1f}s")
    time.sleep(1.0)

    sent: list[tuple[int, float]] = []
    for n in range(ROWS):
        with conn.cursor() as cur:
            cur.execute("INSERT INTO idx.alert (severity, job, message, kind) VALUES ('info', %s, %s, 'ops') RETURNING id",
                        (JOB, f"load row {n}"))
            row = cur.fetchone()
        sent.append((int(row[0]), time.monotonic()))
        time.sleep(0.05)
    print(f"wrote {len(sent)} rows")
    time.sleep(2.0)
    stop.set()

    ids_sent = {i for i, _ in sent}
    at = dict(sent)
    delivered = [len([1 for aid, _ in rows if aid in ids_sent]) for rows in got.values()]
    lat = [(ts - at[aid]) * 1000 for rows in got.values() for aid, ts in rows if aid in ids_sent]
    print(f"delivered per client: min {min(delivered)} / median {int(statistics.median(delivered))} / max {max(delivered)}"
          f" of {len(sent)}")
    if lat:
        lat.sort()
        print(f"latency ms: p50 {lat[len(lat)//2]:.0f} · p95 {lat[int(len(lat)*0.95)]:.0f} · max {lat[-1]:.0f}")
    print("complete clients:", sum(1 for d in delivered if d == len(sent)), "of", len(delivered))
    with conn.cursor() as cur:
        cur.execute("DELETE FROM idx.alert WHERE job = %s", (JOB,))
        print("cleaned up", cur.rowcount, "rows")
    try:
        with urllib.request.urlopen(os.environ.get("IDX_URL", "http://127.0.0.1:8001") + "/idx/stream/status", timeout=5) as r:
            print("status after:", r.read().decode())
    except Exception as e:
        print("status:", e)


if __name__ == "__main__":
    main()
