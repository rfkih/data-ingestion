"""IdxClient - retries a Cloudflare challenge, rejects non-JSON, opens the circuit, keeps a budget.
Transport is injected (``fetch_fn``) so nothing here touches the network."""
from __future__ import annotations

import json
import sys
from datetime import date

import pytest

from blackheart_ingest.idx import client as c

CHALLENGE = b'<!DOCTYPE html><html lang="en-US"><head><title>Just a moment...</title></head></html>'
SUMMARY = {"draw": 0, "recordsTotal": 1, "recordsFiltered": 1,
           "data": [{"No": 1, "IDStockSummary": 1, "Date": "2026-09-11T00:00:00", "StockCode": "BBCA",
                     "Previous": 6425.0, "OpenPrice": 6400.0, "High": 6400.0, "Low": 6250.0, "Close": 6325.0}]}


class Fake:
    """Scripted transport: each call pops the next (status, body); the last one repeats."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls: list[tuple[str, dict[str, str]]] = []

    def __call__(self, url, headers):
        self.calls.append((url, headers))
        return self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]


def ok(payload) -> tuple[int, bytes]:
    return 200, json.dumps(payload).encode()


def make_client(fake, **kw) -> c.IdxClient:
    sleeps: list[float] = []
    cl = c.IdxClient(rps=0, daily_budget=kw.pop("daily_budget", 100), circuit_threshold=kw.pop("circuit_threshold", 3),
                     circuit_pause_s=1, backoff=kw.pop("backoff", (1, 1, 1)), fetch_fn=fake, sleep=sleeps.append)
    cl._test_sleeps = sleeps  # type: ignore[attr-defined]
    return cl


def test_challenge_then_json_succeeds() -> None:
    fake = Fake((403, CHALLENGE), ok(SUMMARY))
    cl = make_client(fake)
    res = cl.stock_summary(date(2026, 9, 11))
    assert len(fake.calls) == 2
    assert "date=20260911" in fake.calls[0][0] and fake.calls[0][1]["Referer"].endswith("ringkasan-saham/")
    assert res.status == 200 and res.key == "2026-09-11"
    assert res.rows()[0]["StockCode"] == "BBCA"
    assert res.fingerprint == "Close,Date,High,IDStockSummary,Low,No,OpenPrice,Previous,StockCode"
    assert cl._test_sleeps == [1]  # type: ignore[attr-defined]


def test_non_json_body_is_retried_then_fails() -> None:
    cl = make_client(Fake((200, CHALLENGE)), backoff=(1, 1), circuit_threshold=99)
    with pytest.raises(c.IdxFetchError):
        cl.trading_info("bbca")
    assert cl.requests_made == 3


def test_circuit_pauses_once_then_opens() -> None:
    cl = make_client(Fake((503, b"")), backoff=(1,) * 10, circuit_threshold=2)
    with pytest.raises(c.CircuitOpen):
        cl.securities_stock()
    assert cl.requests_made == 4  # 2 failures -> pause -> 2 more -> open


def test_transport_errors_count_as_failures() -> None:
    def boom(url, headers):
        raise OSError("connection reset")

    cl = c.IdxClient(rps=0, daily_budget=10, circuit_threshold=99, circuit_pause_s=1, backoff=(1,), fetch_fn=boom,
                     sleep=lambda s: None)
    with pytest.raises(c.IdxFetchError):
        cl.index_summary(date(2026, 9, 11))
    assert cl.requests_made == 2


def test_daily_budget_is_enforced() -> None:
    cl = make_client(Fake(ok(SUMMARY)), daily_budget=2)
    cl.stock_summary(date(2026, 9, 10))
    cl.stock_summary(date(2026, 9, 11))
    with pytest.raises(c.BudgetExceeded):
        cl.stock_summary(date(2026, 9, 12))


def test_announcement_and_financial_keys() -> None:
    a = make_client(Fake(ok({"ResultCount": 0, "Replies": []}))).announcement("BBCA", date(2026, 8, 1), date(2026, 9, 12))
    assert a.key == "BBCA:2026-08-01:2026-09-12:0" and a.rows() == [] and a.fingerprint is None
    f = make_client(Fake(ok({"ResultCount": 0, "Results": []}))).financial_report(2025, "tw3", "BBCA")
    assert f.key == "2025:tw3:BBCA:0" and "kodeEmiten=BBCA" in f.url and "periode=tw3" in f.url


def test_default_fetcher_honours_transport_env(monkeypatch):
    monkeypatch.setenv("INGEST_IDX_TRANSPORT", "urllib")
    assert c.default_fetcher().__name__ == "fetch" and not hasattr(c.default_fetcher(), "jar")
    monkeypatch.setenv("INGEST_IDX_TRANSPORT", "curl")
    monkeypatch.setattr(c, "find_curl", lambda: None)
    with pytest.raises(RuntimeError):
        c.default_fetcher()
    monkeypatch.setenv("INGEST_IDX_TRANSPORT", "auto")
    assert not hasattr(c.default_fetcher(), "jar")                     # no curl -> urllib, no error


def test_curl_fetcher_parses_status_and_body(monkeypatch, tmp_path):
    """The curl transport is driven through a stand-in executable: body to -o, status code on stdout."""
    import os
    fake = tmp_path / "curl.py"
    fake.write_text("import sys\nargs = sys.argv[1:]\nout = args[args.index('-o') + 1]\n"
                    "open(out, 'wb').write(b'%PDF-x')\nsys.stdout.write('206')\n")
    real_run = c.subprocess.run

    def run(cmd, **kw):
        assert cmd[0] == "CURL" and "-b" in cmd and "-c" in cmd and cmd[-1] == "https://x/y"
        assert "User-Agent: ua" in cmd
        return real_run([sys.executable, str(fake), *cmd[1:]], **kw)

    monkeypatch.setattr(c, "find_curl", lambda: "CURL")
    monkeypatch.setattr(c.subprocess, "run", run)
    fetch = c._curl_fetcher()
    assert fetch("https://x/y", {"User-Agent": "ua"}) == (206, b"%PDF-x")
    cl = c.IdxClient(rps=0, fetch_fn=fetch)
    jar = fetch.jar
    assert os.path.exists(jar)
    cl.close()
    assert not os.path.exists(jar)
