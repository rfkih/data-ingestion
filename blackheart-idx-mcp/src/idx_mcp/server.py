"""The ``idx-desk`` MCP server: the Blackheart IDX (IHSG) value desk as agent tools.

Every tool is a thin call to the ingest API (``client.IdxApi``) plus, on the writes that matter, a pure guard
(``guard``). Tool docstrings are what the agent reads — they state the contract (arguments, shapes, rules); the
implementation stays one or two lines so the contract cannot drift from the code.

Read tools carry ``readOnlyHint``; writes do not. Errors from the API or a guard surface as ``ToolError`` with the
server's own message, so a 422 from ``pack_answer`` lists every validation problem verbatim.
"""
from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from .client import IdxApi, IdxApiError
from .guard import GuardError, check_fill, check_status_change

AGENT_MODEL = "claude-code"          # attribution of pack answers written through these tools (idx.sentiment_score.model)

INSTRUCTIONS = """\
Tools for the Blackheart IDX (IHSG) value/quality desk. State lives in blackheart-ingest (Postgres schema `idx`);
these tools wrap its `/idx/*` API (local :8001).

Books: `paper` — yours: build, issue, fill and close tickets (paper tickets fill at the next open by the scheduler).
`live` — two-key: you may draft a ticket and record evidence; only the operator issues/closes it in the Blackridge app and enters
the broker fills. Never invent a fill. The server enforces this and more (book halted = nothing builds or issues;
issue requires `ticket_validate` to pass: weight/sector caps, liquidity floor, candidates only, cash, and — for your
rebalances outside May 1-10 — the turnover cap). Book settings and limits are the operator's; you may set a book's note.
Everything you do is journaled (`decisions`); add your own reasoning with `journal`.

The strategy is fixed (composite value/quality rule, strict gate, annual May rebalance, thesis-break exits). Your job is
the second read: answer the nightly pack per name (value-trap hunting, using only what the pack contains), triage
alerts, draft tickets when due, keep the evidence ledger, report. Never pick a name outside the candidates/watchlist.

Start every session with `ops` (is today's bar in? `last_bar_date`) and `alerts`.
"""

server = MCPServer("idx-desk", instructions=INSTRUCTIONS, version="0.1.0")

_api: IdxApi | None = None


def api() -> IdxApi:
    global _api
    if _api is None:
        _api = IdxApi()
    return _api


def set_api(a: IdxApi | None) -> None:
    """Swap the client (tests inject an ``httpx.MockTransport``-backed one)."""
    global _api
    _api = a


def _tool(*, ro: bool) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Register ``fn`` as an MCP tool, mapping API/guard failures to ``ToolError``; returns the raw function so tests
    can call it directly."""
    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        def inner(*a: Any, **k: Any) -> Any:
            try:
                return fn(*a, **k)
            except (IdxApiError, GuardError) as e:
                raise ToolError(str(e)) from None
        server.tool(annotations=ToolAnnotations(readOnlyHint=ro, destructiveHint=False, openWorldHint=False))(inner)
        return fn
    return deco


# ---------------------------------------------------------------------------------------------------------------- read
@_tool(ro=True)
def ops(runs_limit: int = 10) -> dict[str, Any]:
    """Desk status: `last_bar_date` (the newest IDX trading day loaded — if it is not today after ~16:30 WIB the daily
    chain has not landed yet; do not answer a pack or build a ticket on stale data), open alerts, the last ingest runs
    (`runs_limit` newest), active listing count."""
    d = api().get("/ops")
    d["runs"] = (d.get("runs") or [])[: max(runs_limit, 0)]
    return d


@_tool(ro=True)
def alerts(limit: int = 50) -> list[dict[str, Any]]:
    """Open (unacknowledged) alerts, newest first: `{id, ts, severity, job, message}`. `job` is `book:<book>` for holding
    alerts (thesis break on a new report, disclosure kinds that matter, unrealized <= -25 %, liquidity halved), or the
    ingest job that raised it. Acknowledge with `alert_ack` once handled."""
    return api().get("/alerts", limit=limit)


@_tool(ro=True)
def runs(job: str | None = None, limit: int = 30) -> list[dict[str, Any]]:
    """Ingest run log (`idx.ingest_run`), newest first; filter by `job` (e.g. `daily_chain`, `candidates`, `fundamentals`)."""
    return api().get("/runs", job=job, limit=limit)


@_tool(ro=True)
def candidates(as_of: str | None = None, all: bool = False, strategy: str | None = None, size: int | None = None) -> dict[str, Any]:
    """The candidate list of the deployed strategy (or `strategy` key, `size` 10|15|None) from the latest run on/before
    `as_of` (YYYY-MM-DD). `all=true` also returns the rest of the ranked pool. Rows: code, name, rank, selected, price,
    mcap, ep/bp/dy, ep_ttm, roe, der, np_yoy, gate_loose/gate_strict + strict_fails, warnings, v60 (Rp/day), sector."""
    return api().get("/candidates", as_of=as_of, all=all, strategy=strategy, size=size)


@_tool(ro=True)
def card(code: str, as_of: str | None = None) -> str:
    """One name's fundamental card as markdown (valuation, TTM, both gates with reasons, 4Q + 3FY table, flow, corporate
    actions, disclosures, pack answers so far). Point-in-time when `as_of` is given."""
    return api().get(f"/card/{code.upper()}", as_of=as_of)["md"]


@_tool(ro=True)
def name(code: str) -> dict[str, Any]:
    """One name's research picture: the studies that flag it, evidence by kind, plan sections, pack answers, consensus."""
    return api().get(f"/name/{code.upper()}")


@_tool(ro=True)
def book(book: str = "paper", fills_limit: int = 20) -> dict[str, Any]:
    """A book's snapshot: settings (cash, fees, strategy, overlays, `status` active|halted + halt_reason, risk limits
    max_weight_pct/max_sector_pct/max_turnover_pct/min_v60), positions (lots, avg cost, mark, unrealized, dividends),
    closed positions, NAV series, `nav_now`, the newest `fills_limit` fills, open holding alerts."""
    d = api().get(f"/book/{book}")
    d["fills"] = (d.get("fills") or [])[: max(fills_limit, 0)]
    return d


@_tool(ro=True)
def pack(pack_date: str | None = None, include_md: bool = True, include_json: bool = False) -> dict[str, Any]:
    """The nightly analysis pack (latest, or the one for `pack_date`): `pack_md` (the pinned instructions + market +
    candidate table + one section per name; ~12k tokens for ~30 names), `codes` (the names an answer must cover),
    `answer_json`/`imported_at` (an answer already stored, or null). `include_json` adds the per-name numeric block."""
    d = api().get("/pack/latest" if pack_date is None else f"/pack/{pack_date}")
    pj = d.pop("pack_json", None) or {}
    d["codes"] = list(pj.get("codes") or [])
    if include_json:
        d["pack_json"] = pj
    if not include_md:
        d.pop("pack_md", None)
    return d


@_tool(ro=True)
def answers(code: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """Stored pack answers (all models), newest first: `{pack_date, code, stance, conviction, veto, rationale, scored_at}`."""
    return api().get("/answers", code=code, limit=limit)


@_tool(ro=True)
def answers_score() -> dict[str, Any]:
    """Forward returns after each stored answer per stance/veto vs the COMPOSITE — whether the second reader adds value."""
    return api().get("/answers/score")


@_tool(ro=True)
def watchlist() -> list[dict[str, Any]]:
    """The watchlist (`{code, note, added_at}`): names outside the candidate list that the pack also covers."""
    return api().get("/watchlist")


@_tool(ro=True)
def news(code: str | None = None, limit: int = 30) -> list[dict[str, Any]]:
    """Recent Indonesian financial-press items (RSS titles, tagged codes), newest first; `code` filters to one name."""
    return api().get("/news", code=code, limit=limit)


@_tool(ro=True)
def quote(codes: list[str]) -> list[dict[str, Any]]:
    """Latest close per code (end of day - the data plane has no intraday quotes): `{code, name, trade_date, close, open,
    volume, prev_close, chg_pct, v60 (Rp/day 60-day median value), tick, band_lo, band_hi}`; a name without a bar comes
    back with `error`. Use it to sanity-check a ticket's limit prices or a holding's move."""
    return api().get("/quote", codes=",".join(c.strip().upper() for c in codes if c.strip()))


@_tool(ro=True)
def report(book: str = "paper", period: str = "since", as_of: str | None = None) -> dict[str, Any]:
    """Performance over `period` (since | mtd | ytd | 1m | 3m | 6m | 1y | YYYY-MM-DD:YYYY-MM-DD): NAV return vs COMPOSITE /
    LQ45 / IDXV30 / IDX30, max drawdown, fees, dividends, hit rate, and every name's P&L contribution (`names`, sorted).
    `text` is the rendered summary - paste it into the nightly report / `notify` as is. `cash_unmarked` != 0 means the
    operator changed the book's cash outside fills; say the return is not clean over that period."""
    return api().get("/report", book=book, period=period, as_of=as_of)


@_tool(ro=True)
def macro() -> dict[str, Any]:
    """Macro board: every series (BI rate, rupiah, growth, inflation, global rates, commodities) with latest value,
    1/3/12-month change and a 24-month history."""
    return api().get("/macro")


@_tool(ro=True)
def overlay() -> dict[str, Any]:
    """Regime overlay record (index vs SMA, latest check + history, stress state) and which books have overlays on."""
    return api().get("/overlay")


@_tool(ro=True)
def strategies() -> dict[str, Any]:
    """The strategy catalog with the research record per (size, rebalance month): what each choice earned."""
    return api().get("/strategies")


@_tool(ro=True)
def strategy(key: str, size: int | None = None) -> dict[str, Any]:
    """One strategy's metadata and research history (optionally for one `size`)."""
    return api().get(f"/strategies/{key}", size=size)


@_tool(ro=True)
def studies(name: str | None = None) -> dict[str, Any]:
    """Research studies stored in the DB (newest first), optionally only those named `name` (e.g. `doublers`)."""
    return api().get("/study", name=name)


@_tool(ro=True)
def study(study_id: int | None = None, name: str | None = None) -> dict[str, Any]:
    """One study run: by `study_id`, or the latest run of `name`."""
    if study_id is None and not name:
        raise ToolError("give study_id or name")
    return api().get(f"/study/{study_id}") if study_id is not None else api().get("/study/latest", name=name)


@_tool(ro=True)
def ticket(book: str = "paper", ticket_id: int | None = None) -> dict[str, Any]:
    """A rebalance/exits ticket with its lines — by `ticket_id`, else the newest ticket of `book`. Line: `{id, seq, code,
    name, side, lots, limit_price, ref_close, notional, weight_now, weight_target, reason, flags, status, filled_lots}`.
    Ticket status: draft | issued | closed | cancelled. `params.actor` says who built it."""
    return api().get(f"/ticket/{ticket_id}") if ticket_id is not None else api().get("/ticket/latest", book=book)


@_tool(ro=True)
def ticket_validate(ticket_id: int) -> dict[str, Any]:
    """The guardrails a ticket faces at issue, against the book's current positions and limits: `{ok, breaches: [{kind,
    code, detail, value, limit}], nav, cash_after, turnover, weights, sectors, book_status}`. Kinds: halted, lot, band,
    not_in_candidates, liquidity, liquidity_unknown, max_weight, max_sector, cash_negative, turnover (agent rebalance
    outside May 1-10 only). Fix a breach by `ticket_line_skip` on the offending line or by asking the operator to change
    the book's limits — never by working around it."""
    return api().get(f"/ticket/{ticket_id}/validate")


@_tool(ro=True)
def decisions(book: str | None = None, code: str | None = None, action: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """The decision journal, newest first: `{ts, book, actor agent|operator|scheduler, action, code, ticket_id, line_id,
    rationale, refs}`. Actions: pack_answer, ticket_build, ticket_status, ticket_fill, ticket_skip, fill, halt, resume,
    settings, note. Read it at the start of a session to see what happened since the last one."""
    return api().get("/decision", book=book, code=code, action=action, limit=limit)


# --------------------------------------------------------------------------------------------------------------- write
@_tool(ro=False)
def alert_ack(alert_id: int) -> dict[str, Any]:
    """Acknowledge one alert after handling it (say what you did in the evidence ledger or the pack notes)."""
    return api().post(f"/alerts/{alert_id}/ack")


@_tool(ro=False)
def pack_build(as_of: str | None = None, next_n: int = 10) -> dict[str, Any]:
    """Build and store tonight's pack (selected candidates + `next_n` runners-up + watchlist) for `as_of` (default: the
    latest bar). Returns `{pack_date, names, chars}`; then read it with `pack`."""
    return api().post("/pack/build", as_of=as_of, next_n=next_n)


@_tool(ro=False)
def pack_answer(pack_date: str, answer: dict[str, Any]) -> dict[str, Any]:
    """Store your second read of the pack dated `pack_date` (attributed to model `claude-code`). `answer` must be exactly:
    `{"pack_date": "<same date>", "prompt_version": "pack_v1", "names": [{"code": "XXXX", "stance": "buy|hold|avoid|sell",
    "conviction": 1-5 (int), "thesis": "one or two sentences naming the figure/disclosure", "risks": "the specific value-trap
    risk", "veto": false, "veto_reason": null}, ...], "notes": "whole-list remarks"}`. Every code must be in the pack's
    `codes`; no duplicates; a veto needs a reason. Rejected answers return the full list of problems."""
    return api().post(f"/pack/{pack_date}/answer", json=answer, model=AGENT_MODEL)


@_tool(ro=False)
def evidence_add(code: str, kind: str, title: str, summary: str | None = None, source: str | None = None,
                 url: str | None = None, tags: list[str] | None = None, study_id: int | None = None) -> dict[str, Any]:
    """Append to a name's evidence ledger. `kind` must be one of news | announcement | annual | web | analyst | note — use
    `note` for your own reasoning (thesis, risk, decision) and say which in `tags` (e.g. ["risk"]); the others are for
    facts with a source/url. Use it for anything you acted on so the reasoning survives the session."""
    body = {"kind": kind, "title": title, "summary": summary, "source": source, "url": url, "tags": tags, "study_id": study_id}
    return api().post(f"/name/{code.upper()}/evidence", json={k: v for k, v in body.items() if v is not None})


@_tool(ro=False)
def watchlist_set(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Replace the whole watchlist with `items` = `[{"code": "XXXX", "note": "..."}, ...]` (read `watchlist` first and
    resend it with your change — names left out are removed)."""
    return api().put("/watchlist", json=items)


@_tool(ro=False)
def book_fill(book: str, trade_date: str, code: str, side: str, lots: int, price: float, fee: float | None = None,
              note: str | None = None) -> dict[str, Any]:
    """Record an executed fill on a paper/test `book` (`side` buy|sell, `lots` of 100 shares, `price` per share, `fee` in
    Rp or null for the book's default %), then rebuild positions and mark. Live fills are the operator's (Blackridge app)."""
    check_fill(book)
    body = {"trade_date": trade_date, "code": code.upper(), "side": side, "lots": lots, "price": price, "fee": fee, "note": note}
    return api().post(f"/book/{book}/fills", json={k: v for k, v in body.items() if v is not None})


@_tool(ro=False)
def book_settings(book: str, settings: dict[str, Any]) -> dict[str, Any]:
    """Update a book's `note` (the only field the agent may set — cash, fees, strategy, size, overlays and risk limits are the
    operator's; the server answers 403 otherwise). Returns the book."""
    return api().put(f"/book/{book}", json=settings)


@_tool(ro=False)
def ticket_build(book: str = "paper", mode: str = "rebalance", as_of: str | None = None, max_names: int | None = None,
                 strategy: str | None = None) -> dict[str, Any]:
    """Draft a ticket for `book`: `mode` rebalance (to the strategy's target list) or exits (held names whose thesis broke:
    loose gate failed on the newest report, or pack stance sell). Limit prices are tick-snapped inside the ARA/ARB band;
    lots of 100; fees and a cash reserve included. Returns the stored ticket (status draft). Live: leave it draft and tell
    the operator; paper: `ticket_set_status(issued)` and the scheduler fills it at the next open."""
    return api().post("/ticket/build", book=book, mode=mode, as_of=as_of, max_names=max_names, strategy=strategy)


@_tool(ro=False)
def ticket_set_status(ticket_id: int, status: str, rationale: str | None = None) -> dict[str, Any]:
    """Move a ticket to draft | issued | closed | cancelled, with a `rationale` for the journal. Two-key: on the live book
    the agent may only set `cancelled` (on a draft it made) — issuing and closing live tickets is the operator's, in
    the Blackridge app. `issued` runs `ticket_validate` server-side and is refused with the breach list when it fails."""
    t = api().get(f"/ticket/{ticket_id}")
    check_status_change(t["book"], status)
    return api().post(f"/ticket/{ticket_id}/status", json={"status": status, "rationale": rationale})


@_tool(ro=False)
def ticket_line_fill(ticket_id: int, line_id: int, lots: int, price: float, fee: float | None = None, trade_date: str | None = None,
                     note: str | None = None) -> dict[str, Any]:
    """Record a fill for one line of a paper/test ticket (creates the book fill, marks the line filled|partial). Live
    lines are the operator's (Blackridge app)."""
    t = api().get(f"/ticket/{ticket_id}")
    if not any(ln["id"] == line_id for ln in t.get("lines") or []):
        raise ToolError(f"line {line_id} is not on ticket {ticket_id}")
    check_fill(t["book"])
    body = {"lots": lots, "price": price, "fee": fee, "trade_date": trade_date, "note": note}
    return api().post(f"/ticket/lines/{line_id}/fill", json={k: v for k, v in body.items() if v is not None})


@_tool(ro=False)
def ticket_line_skip(line_id: int, reason: str) -> dict[str, Any]:
    """Skip one ticket line with a reason (e.g. the pack veto, liquidity, the operator's call)."""
    return api().post(f"/ticket/lines/{line_id}/skip", json={"reason": reason})


@_tool(ro=False)
def journal(rationale: str, book: str | None = None, code: str | None = None, ticket_id: int | None = None, line_id: int | None = None,
            action: str = "note", refs: dict[str, Any] | None = None) -> dict[str, Any]:
    """Write a free entry to the decision journal (actor `agent`): what you concluded and why — a triaged alert, a name
    you decided to leave alone, the reasoning behind a ticket. Short, specific, one entry per decision."""
    body = {"rationale": rationale, "book": book, "code": code, "ticket_id": ticket_id, "line_id": line_id, "action": action, "refs": refs}
    return api().post("/decision", json={k: v for k, v in body.items() if v is not None})


@_tool(ro=False)
def notify(text: str, title: str | None = None, route: str | None = None) -> dict[str, Any]:
    """Send a push notification to the operator's phone (the Blackridge app; prefixed `[agent]`). Use it for what needs a human
    now: a live draft to issue, a thesis break, a data problem. `title` (default: the first line) and `route` (the app screen
    a tap opens, e.g. `/m/ticket?book=trend_live`; default `/m`). Returns `{sent, configured, channels}` - `configured=false`
    means no phone channel is set up on the server; say so in your report instead of retrying."""
    body = {"text": text, "title": title, "route": route}
    return api().post("/notify", json={k: v for k, v in body.items() if v is not None})


@_tool(ro=False)
def reconcile(book: str, csv_text: str | None = None, rows: list[dict[str, Any]] | None = None,
              source: str | None = None) -> dict[str, Any]:
    """Compare a book with the broker's portfolio export - `csv_text` (the export file's text: Stockbit/IPOT/Ajaib shapes,
    `;` or `,`, Indonesian numbers) or `rows` `[{code, lots|shares, avg?}]`. Read-only; journaled. Returns `{ok, matched,
    only_book, only_broker, lots_mismatch, avg_mismatch}`. Differences are the operator's to fix (a fill or a correction
    in the Blackridge app) - report them, never "fix" the book yourself."""
    body = {"csv": csv_text, "rows": rows, "source": source}
    return api().post(f"/book/{book}/reconcile", json={k: v for k, v in body.items() if v is not None})


@_tool(ro=False)
def overlay_check(as_of: str | None = None, dry_run: bool = True) -> dict[str, Any]:
    """Run the monthly regime/stress check now. `dry_run=true` reports only; `false` records it and builds the overlay
    tickets it calls for."""
    body = {"as_of": as_of, "dry_run": dry_run}
    return api().post("/overlay/check", json={k: v for k, v in body.items() if v is not None})
