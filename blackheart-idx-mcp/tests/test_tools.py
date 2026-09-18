"""Tools against a fake ingest API (httpx.MockTransport): request shapes, response trimming, guard wiring, error text."""
from __future__ import annotations

import json

import anyio
import httpx
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from idx_mcp import server as srv
from idx_mcp.client import IdxApi, IdxApiError

TICKETS = {7: {"id": 7, "book": "live", "status": "draft", "lines": [{"id": 70, "code": "GJTL"}]},
           8: {"id": 8, "book": "paper", "status": "draft", "lines": [{"id": 80, "code": "CTRA"}]}}


def handler(req: httpx.Request) -> httpx.Response:
    p, q = req.url.path, dict(req.url.params)
    seen.append((req.method, p, q, json.loads(req.content) if req.content else None, req.headers.get("x-ingest-token"),
                 req.headers.get("x-idx-actor")))
    if p == "/idx/ops":
        return httpx.Response(200, json={"last_bar_date": "2026-09-16", "open_alerts": [], "runs": [{"id": i} for i in range(40)]})
    if p == "/idx/pack/latest":
        pj = {"codes": ["GJTL", "CTRA"], "names": [1, 2]}
        body = {"pack_date": "2026-09-16", "pack_md": "# pack", "pack_json": pj, "answer_json": None, "imported_at": None}
        return httpx.Response(200, json=body)
    if p == "/idx/pack/2026-09-16/answer":
        if q.get("model") != "claude-code":
            return httpx.Response(500, json={"detail": "model attribution missing"})
        return httpx.Response(200, json={"names": []})
    if p == "/idx/pack/1999-01-01/answer":
        return httpx.Response(422, json={"detail": "GJTL: not in the pack; CTRA: conviction must be an integer 1..5"})
    if p == "/idx/ticket/7/validate":
        return httpx.Response(200, json={"ok": False, "breaches": [{"kind": "max_weight", "code": "GJTL"}]})
    if p.startswith("/idx/ticket/") and req.method == "GET":
        return httpx.Response(200, json=TICKETS[int(p.rsplit("/", 1)[1])])
    if p.endswith("/status") or p.endswith("/fill"):
        return httpx.Response(200, json={"ok": True})
    if p == "/idx/quote":
        return httpx.Response(200, json=[{"code": c, "close": 1000} for c in q["codes"].split(",")])
    if p == "/idx/notify":
        return httpx.Response(200, json={"sent": False, "configured": False})
    if p == "/idx/book/paper/reconcile":
        return httpx.Response(200, json={"ok": True, "matched": ["GJTL"]})
    if p == "/idx/report":
        return httpx.Response(200, json={"book": q["book"], "period": q["period"], "ret_pct": "1.2", "text": "paper mtd: ..."})
    if p == "/idx/decision":
        return httpx.Response(200, json=[{"id": 1, "actor": "agent", "action": "note"}] if req.method == "GET" else {"id": 9})
    if p == "/idx/card/GJTL":
        return httpx.Response(200, json={"code": "GJTL", "md": "## GJTL"})
    return httpx.Response(404, json={"detail": f"unmapped {p}"})


seen: list = []


@pytest.fixture(autouse=True)
def fake_api(monkeypatch):
    monkeypatch.setenv("INGEST_AUTH_TOKEN", "tok")
    seen.clear()
    srv.set_api(IdxApi(base_url="http://fake", transport=httpx.MockTransport(handler)))
    yield
    srv.set_api(None)


def test_ops_trims_runs_and_sends_token_and_actor():
    d = srv.ops(runs_limit=3)
    assert d["last_bar_date"] == "2026-09-16" and len(d["runs"]) == 3
    assert seen[0][4] == "tok" and seen[0][5] == "agent"


def test_pack_exposes_codes_and_hides_json_by_default():
    d = srv.pack()
    assert d["codes"] == ["GJTL", "CTRA"] and "pack_json" not in d and d["pack_md"] == "# pack"
    assert "pack_md" not in srv.pack(include_md=False) and srv.pack(include_json=True)["pack_json"]["names"] == [1, 2]


def test_pack_answer_is_attributed_to_claude_code():
    srv.pack_answer("2026-09-16", {"pack_date": "2026-09-16", "names": []})
    m, p, q, body, *_ = seen[-1]
    assert (m, p, q["model"]) == ("POST", "/idx/pack/2026-09-16/answer", "claude-code") and body["names"] == []


def test_api_errors_carry_the_server_detail():
    with pytest.raises(IdxApiError, match="not in the pack; CTRA: conviction"):
        srv.pack_answer("1999-01-01", {})


def test_card_returns_markdown():
    assert srv.card("gjtl") == "## GJTL" and seen[-1][1] == "/idx/card/GJTL"


def test_two_key_on_live_ticket():
    srv.ticket_set_status(8, "issued", rationale="paper switch")          # paper: fine
    assert seen[-1][1] == "/idx/ticket/8/status" and seen[-1][3] == {"status": "issued", "rationale": "paper switch"}
    srv.ticket_set_status(7, "cancelled")                                # live draft may be cancelled
    with pytest.raises(Exception, match="two-key"):
        srv.ticket_set_status(7, "issued")
    assert not any(p == "/idx/ticket/7/status" and b.get("status") == "issued" for _, p, _, b, *_ in seen if b)


def test_live_fills_are_never_the_agents():
    with pytest.raises(Exception, match="live fills"):
        srv.ticket_line_fill(7, 70, lots=10, price=1000)
    with pytest.raises(Exception, match="live fills"):
        srv.book_fill("live", "2026-09-17", "GJTL", "buy", 10, 1000)
    srv.ticket_line_fill(8, 80, lots=10, price=1000, fee=1500, trade_date="2026-09-17")
    assert seen[-1][1] == "/idx/ticket/lines/80/fill"
    assert seen[-1][3] == {"lots": 10, "price": 1000, "fee": 1500, "trade_date": "2026-09-17"}
    with pytest.raises(ToolError, match="not on ticket"):
        srv.ticket_line_fill(8, 70, lots=1, price=1)


def test_validate_decisions_and_journal():
    assert srv.ticket_validate(7)["breaches"][0]["kind"] == "max_weight"
    assert srv.decisions(book="paper", limit=5)[0]["actor"] == "agent" and seen[-1][2] == {"book": "paper", "limit": "5"}
    assert srv.journal("left BTPS alone: liquidity alert is a known small-cap", book="paper", code="BTPS") == {"id": 9}
    assert seen[-1][3] == {"rationale": "left BTPS alone: liquidity alert is a known small-cap", "book": "paper", "code": "BTPS",
                           "action": "note"}


def test_errors_surface_as_tool_errors_through_mcp():
    async def go():
        with pytest.raises(ToolError, match="two-key"):
            await srv.server.call_tool("ticket_set_status", {"ticket_id": 7, "status": "issued"})
        res = await srv.server.call_tool("ops", {"runs_limit": 1})
        return res
    res = anyio.run(go)
    assert res is not None


def test_unreachable_api_explains_how_to_start_it():
    def down(req):
        raise httpx.ConnectError("refused")
    srv.set_api(IdxApi(base_url="http://fake", transport=httpx.MockTransport(down)))
    with pytest.raises(IdxApiError, match="unreachable .* uvicorn"):
        srv.ops()


def test_quote_notify_reconcile():
    assert [r["code"] for r in srv.quote([" gjtl", "BBCA "])] == ["GJTL", "BBCA"] and seen[-1][2] == {"codes": "GJTL,BBCA"}
    assert srv.notify("live draft #9 ready") == {"sent": False, "configured": False} and seen[-1][3] == {"text": "live draft #9 ready"}
    csv = "Symbol;Lot\nGJTL;10\n"
    assert srv.reconcile("paper", csv_text=csv, source="x.csv")["ok"] and seen[-1][3] == {"csv": csv, "source": "x.csv"}


def test_report():
    r = srv.report("paper", "mtd")
    assert r["text"].startswith("paper mtd") and seen[-1][2] == {"book": "paper", "period": "mtd"}
