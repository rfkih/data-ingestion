"""Signal ledger (idx/signal_ledger.py): the hash chain detects an edited payload, a removed entry and a forged hash."""
from __future__ import annotations

import copy

from blackheart_ingest.idx import signal_ledger as sl


def chain(n: int = 3) -> list[dict]:
    rows, prev = [], sl.GENESIS
    for i in range(n):
        payload = {"for_date": f"2026-10-0{i + 1}", "lines": [{"code": "AAAA", "side": "buy", "lots": 10 + i}]}
        p_sha = sl.sha(sl.canonical(payload))
        at = f"2026-10-0{i + 1}T14:10:00.000000+00:00"
        e = sl.entry_hash(prev, at, "live-x", "plan", p_sha)
        rows.append({"seq": i + 1, "sealed_at": at, "book": "live-x", "event": "plan", "payload": payload, "payload_sha": p_sha, "prev_sha": prev, "entry_sha": e})
        prev = e
    return rows


def test_intact_chain_verifies() -> None:
    assert sl.verify_rows(chain()) == []


def test_edited_payload_is_caught() -> None:
    rows = chain()
    rows[1]["payload"]["lines"][0]["lots"] = 999
    assert any("payload changed" in b for b in sl.verify_rows(rows))


def test_removed_entry_breaks_the_chain() -> None:
    rows = chain()
    del rows[1]
    assert any("chain broken" in b for b in sl.verify_rows(rows))


def test_recomputed_payload_hash_still_fails_the_entry_hash() -> None:
    rows = copy.deepcopy(chain())
    rows[0]["payload"]["lines"][0]["lots"] = 1
    rows[0]["payload_sha"] = sl.sha(sl.canonical(rows[0]["payload"]))     # a forger updates the payload hash too
    assert any("entry hash" in b for b in sl.verify_rows(rows))


def test_canonical_is_order_independent() -> None:
    assert sl.canonical({"b": 1, "a": [2, {"d": 1, "c": 2}]}) == sl.canonical({"a": [2, {"c": 2, "d": 1}], "b": 1})
