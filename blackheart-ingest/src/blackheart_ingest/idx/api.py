"""HTTP surface for the app (``/idx/*``), mounted on the served ingest FastAPI app.

Read routes are open (same-origin proxy from the frontend); mutation routes reuse the server's ``require_token`` gate
when INGEST_AUTH_TOKEN is set.

Who is calling (``who.py``): a signed-in account through the app's proxy (``Authorization: Bearer`` session JWT - scoped to
that account's books, journal, watchlist, phones), or a service with the ingest token (the agent, the CLI; unscoped, or
scoped to one account with ``X-Idx-User``). The ``X-Idx-Actor`` header (``agent`` | ``operator`` | ``scheduler``; absent =
``operator``, a human) drives the guardrails: on a live book only the operator issues/closes tickets and records fills;
only the operator changes a book's settings beyond its note, halts or resumes it. Research reads are shared and open on
the loopback port; research writes (pack, evidence, macro, overlay) are the desk's own tools', never an account's.
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Body, Depends, Header, HTTPException

from ..shared.db import get_connection
from . import journal, runlog
from .jobs import daily as job_daily
from .who import Caller, caller_of, need_user, own_book, own_line, own_ticket, service_only

_BODY = Body(...)


def _plain(v: Any) -> Any:
    """JSON-safe: dates to ISO, Decimals to str (the app and the agent both parse them)."""
    if isinstance(v, dict):
        return {k: _plain(x) for k, x in v.items()}
    if isinstance(v, list | tuple):
        return [_plain(x) for x in v]
    if isinstance(v, date | datetime):
        return v.isoformat()
    return v


def actor_of(x_idx_actor: str | None = Header(default=None)) -> str:
    a = (x_idx_actor or "operator").strip().lower()
    if a not in journal.ACTORS:
        raise HTTPException(status_code=400, detail=f"X-Idx-Actor must be one of {journal.ACTORS}")
    return a


def _operator_only(actor: str, what: str) -> None:
    if actor != "operator":
        raise HTTPException(status_code=403, detail=f"{what} is the operator's (two-key); the agent may not do it")


_CALLER = Depends(caller_of)


def _alert_book(a: dict[str, Any]) -> str | None:
    """The book an alert is about (``book:X`` / ``ticket:X`` jobs), None for the desk's own alerts."""
    job = str(a.get("job") or "")
    kind, _, rest = job.partition(":")
    return rest or None if kind in ("book", "ticket") else None


def make_router(require_token) -> APIRouter:
    router = APIRouter(prefix="/idx", tags=["idx"])

    @router.get("/ops")
    def ops(c: Caller = _CALLER) -> dict[str, Any]:
        from . import book as bk
        with get_connection() as conn:
            mine = set(bk.list_books(conn, c.user_id, include_archived=True)) if c.scoped else None
            last_bar = job_daily.latest_bar_date(conn)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, job, run_key, status, started_at, finished_at, rows_in, rows_out, warnings, error
                      FROM idx.ingest_run WHERE started_at >= now() - interval '2 days'
                     ORDER BY started_at DESC LIMIT 40
                    """
                )
                runs = [dict(r) for r in cur.fetchall()]
                cur.execute("SELECT count(*) AS n, max(trade_date) AS last FROM idx.daily_summary")
                ds = dict(cur.fetchone())
                cur.execute("SELECT count(*) AS n FROM idx.listing WHERE status = 'ACTIVE'")
                active = dict(cur.fetchone())["n"]
                cur.execute("SELECT count(*) AS n FROM idx.bronze_index")
                bronze_n = dict(cur.fetchone())["n"]
            alerts = [a for a in runlog.open_alerts(conn) if mine is None or _alert_book(a) is None or _alert_book(a) in mine]
        return {
            "now": datetime.now(UTC).isoformat(),
            "last_bar_date": last_bar.isoformat() if last_bar else None,
            "daily_summary": {"rows": ds["n"], "last": ds["last"].isoformat() if ds["last"] else None},
            "active_listings": active,
            "bronze_objects": bronze_n,
            "open_alerts": alerts,
            "runs": runs,
        }

    @router.post("/alerts/{alert_id}/ack", dependencies=[Depends(require_token)])
    def ack(alert_id: int, c: Caller = _CALLER) -> dict[str, Any]:
        with get_connection() as conn:
            if c.scoped:
                a = next((x for x in runlog.open_alerts(conn, 500) if x["id"] == alert_id), None)
                if a is not None and _alert_book(a) is not None:
                    own_book(conn, _alert_book(a), c)
            ok = runlog.acknowledge(conn, alert_id)
        if not ok:
            raise HTTPException(status_code=404, detail="alert not found or already acknowledged")
        return {"acknowledged": alert_id}

    @router.get("/alerts")
    def alerts(limit: int = 50, c: Caller = _CALLER) -> list[dict[str, Any]]:
        """Open (unacknowledged) alerts, newest first — the desk's own plus the caller's books' (every book for a service)."""
        from . import book as bk
        with get_connection() as conn:
            rows = runlog.open_alerts(conn, min(max(limit, 1), 500))
            if c.scoped:
                mine = set(bk.list_books(conn, c.user_id, include_archived=True))
                rows = [a for a in rows if _alert_book(a) is None or _alert_book(a) in mine]
            return rows

    @router.get("/report")
    def report_get(book: str = "paper", period: str = "since", as_of: str | None = None, c: Caller = _CALLER) -> dict[str, Any]:
        """NAV return vs COMPOSITE/LQ45/IDXV30/IDX30, drawdown, fees, dividends and the P&L contribution of every name over
        `period` (since | mtd | ytd | 1m | 3m | 6m | 1y | YYYY-MM-DD:YYYY-MM-DD). `text` carries the rendered summary."""
        from . import report as rp
        with get_connection() as conn:
            own_book(conn, book, c)
            try:
                rep = rp.build(conn, book, period, date.fromisoformat(as_of) if as_of else None)
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e)) from None
        rep["text"] = rp.render(rep)
        return _plain(rep)

    @router.get("/index")
    def index_series(codes: str = "COMPOSITE,LQ45", start: str | None = None) -> dict[str, Any]:
        """Daily closes for the named indices (idx.index_daily) since `start` — the Portfolio's benchmark overlay.
        -> {series: {CODE: [{trade_date, close}, ...]}}. Unknown codes come back empty."""
        wanted = [c.strip().upper() for c in codes.split(",") if c.strip()][:6]
        d0 = date.fromisoformat(start) if start else None
        out: dict[str, list[dict[str, Any]]] = {}
        with get_connection() as conn, conn.cursor() as cur:
            for code in wanted:
                cur.execute(
                    "SELECT trade_date, close FROM idx.index_daily WHERE index_code = %s AND (%s::date IS NULL OR trade_date >= %s) "
                    "ORDER BY trade_date",
                    (code, d0, d0),
                )
                out[code] = [{"trade_date": r["trade_date"].isoformat(), "close": r["close"]} for r in cur.fetchall()]
        return _plain({"series": out})

    @router.get("/quote")
    def quote(codes: str) -> list[dict[str, Any]]:
        """Latest close per code (comma-separated): {code, name, trade_date, close, open, volume, prev_close, chg_pct, v60, tick,
        band_lo, band_hi} - end of day; names without a bar come back with `error`."""
        from . import quote as q
        with get_connection() as conn:
            rows = q.latest(conn, codes.split(","))
        return [{k: (v.isoformat() if isinstance(v, date | datetime) else v) for k, v in r.items()} for r in rows]

    @router.post("/notify", dependencies=[Depends(require_token)])
    def notify_send(body: dict[str, Any] = _BODY, c: Caller = _CALLER) -> dict[str, Any]:
        """Send {text, title?, route?, book?} to a phone (the Blackridge app; Telegram too when configured): the caller's own
        account, else the owner of `book`, else the ops account. The first line is the title unless given; route = the app
        screen a tap opens (default /m). {sent, configured, channels}."""
        from . import notify
        text = str(body.get("text") or "").strip()
        if not text:
            raise HTTPException(status_code=422, detail="text is required")
        if body.get("book"):
            with get_connection() as conn:
                own_book(conn, str(body["book"]), c)
        prefix = "" if c.actor == "operator" else f"[{c.actor}] "
        data = {"route": str(body.get("route") or "/m"), "kind": "message", "actor": c.actor}
        sent = notify.send(prefix + text, title=(str(body["title"]).strip() or None) if body.get("title") else None, data=data,
                           user_id=c.user_id, book=body.get("book"))
        return {"sent": sent, "configured": notify.configured(), "channels": notify.channels()}

    @router.post("/push/register", dependencies=[Depends(require_token)])
    def push_register(body: dict[str, Any] = _BODY, c: Caller = _CALLER) -> dict[str, Any]:
        """The Blackridge app registers its Firebase device token for the signed-in account: {token, platform?, label?}.
        Idempotent; called on every start."""
        from . import push
        uid = need_user(c, "registering a phone")
        with get_connection() as conn:
            try:
                row = push.register(conn, str(body.get("token") or ""), platform=str(body.get("platform") or "android"),
                                    username=c.email, label=(str(body["label"])[:200] if body.get("label") else None), user_id=uid)
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e)) from None
        return _plain({**row, "configured": push.configured()})

    @router.delete("/push/{token}", dependencies=[Depends(require_token)])
    def push_unregister(token: str, c: Caller = _CALLER) -> dict[str, Any]:
        """Forget a device token (the app calls this on sign-out) - one of the caller's own."""
        from . import push
        with get_connection() as conn:
            if c.scoped and token not in {d["token"] for d in push.devices(conn, include_disabled=True, user_id=c.user_id)}:
                return {"removed": False}
            return {"removed": push.unregister(conn, token)}

    @router.get("/push/devices")
    def push_devices(all: bool = False, c: Caller = _CALLER) -> dict[str, Any]:
        """The caller's registered phones (tokens shortened; every phone for a service) and whether the server can push at all."""
        from . import push
        with get_connection() as conn:
            rows = push.devices(conn, include_disabled=all, user_id=c.user_id)
        return _plain({"configured": push.configured(), "devices": [{**r, "token": r["token"][:10] + "…"} for r in rows]})

    @router.post("/push/test", dependencies=[Depends(require_token)])
    def push_test(body: dict[str, Any] = _BODY, c: Caller = _CALLER) -> dict[str, Any]:
        """Send a test notification to the caller's phones (every phone for a service): {text?}. {sent, failed, gone, devices, configured}."""
        from . import push
        text = str(body.get("text") or "Blackridge: notifikasi aktif").strip()
        with get_connection() as conn:
            return push.send_all(conn, "Blackridge", text, {"route": "/m", "kind": "test"}, user_id=c.user_id)

    @router.post("/book/{book}/reconcile", dependencies=[Depends(require_token)])
    def book_reconcile(book: str, body: dict[str, Any] = _BODY, c: Caller = _CALLER) -> dict[str, Any]:
        """Compare the book with the broker's portfolio export: {csv: "<export text>"} or {rows: [{code, lots|shares, avg?}]}.
        Read-only on the book; the result is journaled. Differences are the operator's to resolve by hand."""
        from . import reconcile as rc
        actor = c.actor
        with get_connection() as conn:
            own_book(conn, book, c)
            try:
                if body.get("csv"):
                    rows = rc.parse_csv(str(body["csv"]))
                else:
                    rows = [{"code": str(r["code"]).upper(), "lots": rc.parse_number(r.get("lots")) if r.get("lots") is not None
                             else (rc.parse_number(r.get("shares")) or 0) / rc.LOT, "avg": rc.parse_number(r.get("avg") or r.get("avg_price"))}
                            for r in body.get("rows") or []]
                    rows = [r for r in rows if r["lots"]]
                if not rows:
                    raise ValueError("no positions found in the export")
                rep = rc.reconcile(conn, book, rows, actor=actor, source=body.get("source"))
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e)) from None
        return rep

    @router.get("/news")
    def news_recent(code: str | None = None, limit: int = 30) -> list[dict[str, Any]]:
        """Recent press items (RSS titles), optionally only those tagged with one code."""
        from . import news
        with get_connection() as conn:
            rows = news.recent(conn, code.upper() if code else None, min(max(limit, 1), 200))
        return [{k: (v.isoformat() if isinstance(v, date | datetime) else v) for k, v in r.items()} for r in rows]

    @router.get("/runs")
    def runs(job: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, job, run_key, status, started_at, finished_at, rows_in, rows_out, warnings, error
                  FROM idx.ingest_run WHERE (%s::text IS NULL OR job = %s)
                 ORDER BY started_at DESC LIMIT %s
                """,
                (job, job, min(max(limit, 1), 500)),
            )
            return [dict(r) for r in cur.fetchall()]

    @router.get("/candidates")
    def candidates(as_of: str | None = None, all: bool = False, strategy: str | None = None, size: int | None = None) -> dict[str, Any]:
        """The candidate list under a strategy and size (latest run, or the latest on/before as_of): the chosen names, and
        the rest of that strategy's pool with all=1. Rows carry the strategy's rank and weight; `rank` stays the composite rank."""
        from . import strategies
        strategy = strategy or strategies.deployed()
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT max(run_date) AS d FROM idx.candidate WHERE (%s::date IS NULL OR run_date <= %s)", (as_of, as_of))
            d = dict(cur.fetchone())["d"]
            if d is None:
                return {"run_date": None, "strategy": strategy, "size": size, "pool": 0, "selected": 0, "rows": []}
            cur.execute(
                """
                SELECT c.run_date, c.code, l.name, c.rank, c.selected, c.score, c.price, c.mcap, c.ep, c.bp, c.dy, c.ep_ttm, c.roe, c.der,
                       c.np_yoy, c.gate_loose, c.gate_strict, c.strict_fails, c.warnings, c.f20, c.v60, c.annual_period, c.ttm_basis,
                       c.sector, c.mom, c.conv
                  FROM idx.candidate c LEFT JOIN idx.listing l USING (code)
                 WHERE c.run_date = %s ORDER BY c.rank
                """, (d,))
            rows = [dict(r) for r in cur.fetchall()]
        try:
            picked = strategies.pick(strategy, rows, size=size or None)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from None
        out = [r for r in picked if all or r["selected"]]
        return {"run_date": d.isoformat(), "strategy": strategy, "size": size or None, "pool": len(picked),
                "selected": sum(1 for r in picked if r["selected"]), "rows": out}

    @router.get("/strategies")
    def strategies_list() -> dict[str, Any]:
        """The catalog with every (size, month) research record attached: what each choice earned, and how it varies by calendar."""
        from . import strategies
        with get_connection() as conn:
            return {"sizes": [0, 10, 15], "strategies": strategies.catalog(conn)}

    @router.get("/strategies/{key}")
    def strategy_detail(key: str, size: int | None = None) -> dict[str, Any]:
        from . import strategies
        meta = strategies.BY_KEY.get(key) or next((s for s in strategies.OVERLAYS if s["key"] == key), None) or (
            {"key": key, "label": strategies.REFERENCE_LABELS[key], "status": "reference"} if key in strategies.REFERENCE_LABELS else None)
        if meta is None:
            raise HTTPException(status_code=404, detail="unknown strategy")
        with get_connection() as conn:
            rows = strategies.history(conn, key, size)
        return {"strategy": {k: v for k, v in meta.items() if k != "history"},
                "history": [{k: (v.isoformat() if isinstance(v, date | datetime) else v) for k, v in r.items()} for r in rows]}

    @router.get("/card/{code}")
    def card_get(code: str, as_of: str | None = None) -> dict[str, Any]:
        from . import card
        with get_connection() as conn:
            md = card.build(conn, code.upper(), date.fromisoformat(as_of) if as_of else None)
        return {"code": code.upper(), "as_of": as_of, "md": md}

    @router.get("/pack/latest")
    def pack_latest() -> dict[str, Any]:
        return _pack(None)

    @router.get("/pack/{pack_date}")
    def pack_by_date(pack_date: str) -> dict[str, Any]:
        return _pack(date.fromisoformat(pack_date))

    def _pack(d: date | None) -> dict[str, Any]:
        from . import pack
        with get_connection() as conn:
            p = pack.load(conn, d)
        if p is None:
            raise HTTPException(status_code=404, detail="no pack")
        return {k: (v.isoformat() if isinstance(v, date | datetime) else v) for k, v in p.items()}

    @router.post("/pack/build", dependencies=[Depends(require_token)])
    def pack_build(as_of: str | None = None, next_n: int = 10, c: Caller = _CALLER) -> dict[str, Any]:
        service_only(c, "/pack/build")
        from . import pack
        with get_connection() as conn:
            p = pack.build(conn, date.fromisoformat(as_of) if as_of else None, next_n=next_n)
            pack.store(conn, p)
        return {"pack_date": p["pack_date"].isoformat(), "names": len(p["codes"]), "chars": len(p["md"])}

    @router.post("/pack/{pack_date}/answer", dependencies=[Depends(require_token)])
    def pack_answer(pack_date: str, body: dict[str, Any] | list[Any] | str = _BODY, model: str = "claude-chat-manual",
                    c: Caller = _CALLER) -> dict[str, Any]:
        """Import an answer; ``model`` names who answered (``claude-chat-manual`` pasted from chat, ``claude-code`` via the MCP tools)."""
        from . import pack
        service_only(c, "answering a pack")
        actor = c.actor
        with get_connection() as conn:
            try:
                a = pack.import_answer(conn, date.fromisoformat(pack_date), body, model=model)
            except pack.AnswerError as e:
                raise HTTPException(status_code=422, detail=str(e)) from None
            stances = {n["stance"]: sum(1 for m in a["names"] if m["stance"] == n["stance"]) for n in a["names"]}
            journal.record(conn, None, actor, "pack_answer", rationale=(a.get("notes") or "")[:500],
                           refs={"pack_date": pack_date, "model": model, "names": len(a["names"]), "stances": stances,
                                 "vetoes": [n["code"] for n in a["names"] if n["veto"]]})
        return a

    @router.get("/answers")
    def pack_answers(code: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        from . import pack
        with get_connection() as conn:
            rows = pack.answers(conn, code.upper() if code else None, min(max(limit, 1), 500))
        return [{k: (v.isoformat() if isinstance(v, date | datetime) else v) for k, v in r.items()} for r in rows]

    @router.get("/answers/score")
    def pack_answers_score() -> dict[str, Any]:
        """Forward returns after each imported answer, per stance and for vetoes, vs the COMPOSITE (same as `idx answers --score`)."""
        from . import pack
        with get_connection() as conn:
            s = pack.score_answers(conn)
        groups = [{"group": g, "horizon": h, "n": v["n"], "avg_ret": v["sum"] / v["n"], "hit_rate": v["hits"] / v["n"],
                   "avg_excess": (v["xs"] / v["xs_n"]) if v["xs_n"] else None}
                  for g, hs in s["groups"].items() for h, v in sorted(hs.items())]
        return {"answers": s["answers"], "scored": s["scored"], "horizons": s["horizons"], "groups": groups, "rows": s["rows"]}

    @router.get("/books")
    def books_list(c: Caller = _CALLER, archived: bool = False) -> list[dict[str, Any]]:
        """The caller's books (every book for a service) with what a list needs: {book, label, kind: live|paper, rule: annual|trend,
        note, broker, strategy, max_names, status, halted, archived, cash, nav_now, positions, open_ticket: {id, status, mode,
        n_lines} | null}. Live first."""
        from . import book as bk
        from . import ticket as tk
        from . import trend_book
        out = []
        with get_connection() as conn:
            names = bk.list_books(conn, c.user_id, include_archived=archived)
            for name in names:
                s = bk.snapshot(conn, name)
                b = s["book"]
                with conn.cursor() as cur:
                    cur.execute("""SELECT t.id, t.status, t.mode, (SELECT count(*) FROM idx.ticket_line l WHERE l.ticket_id = t.id) AS n_lines
                                     FROM idx.ticket t WHERE t.book = %s AND t.status IN ('draft', 'issued') ORDER BY t.id DESC LIMIT 1""", (name,))
                    r = cur.fetchone()
                open_ticket = (r if isinstance(r, dict) else dict(zip(["id", "status", "mode", "n_lines"], r, strict=True))) if r else None
                out.append({"book": name, "label": b.get("label") or name, "kind": "live" if tk.is_live(name) else "paper",
                            "rule": "trend" if trend_book.variant_of(b) else "annual", "trend_variant": b.get("trend_variant"),
                            "note": b.get("note"), "broker": b.get("broker"), "strategy": b.get("strategy"), "max_names": b.get("max_names"),
                            "status": b.get("status"), "halted": bool(b.get("halted_at")), "archived": bool(b.get("archived_at")),
                            "cash": b["cash"], "nav_now": s["nav_now"], "positions": len(s["positions"]), "open_ticket": open_ticket,
                            "created_at": b.get("created_at")})
        out.sort(key=lambda x: (x["kind"] != "live", x["rule"] != "annual", x["label"].lower()))
        return _plain(out)

    @router.post("/books", dependencies=[Depends(require_token)])
    def books_create(body: dict[str, Any] = _BODY, c: Caller = _CALLER) -> dict[str, Any]:
        """A new book for the signed-in account: {label, kind: paper|live, rule: annual|trend, cash, broker?, fee_buy_pct?,
        fee_sell_pct?, strategy? (annual: a catalog key), max_names?, trend_variant? (trend: small|all), overlays/limits as
        in PUT /book/{book}}. Returns the book row; its id is what every other route takes."""
        from . import book as bk
        uid = need_user(c, "creating a book")
        kind = str(body.get("kind") or "paper").lower()
        rule = str(body.get("rule") or "annual").lower()
        fields = {k: v for k, v in body.items() if k in bk.SETTABLE_FIELDS and k not in ("label", "rule")}
        fields["rule"] = rule
        if rule == "trend":
            fields.setdefault("trend_variant", "small")
            fields.setdefault("max_weight_pct", 15)
            fields.setdefault("max_sector_pct", 40)
        with get_connection() as conn:
            if len(bk.list_books(conn, uid)) >= 12:
                raise HTTPException(status_code=422, detail="twelve open books is the limit; archive one first")
            try:
                book = bk.create_book(conn, uid, kind, str(body.get("label") or ""), **fields)
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e)) from None
            journal.record(conn, book, c.actor, "settings", rationale="book created", refs={"kind": kind, **{k: str(v) for k, v in fields.items()}},
                           user_id=uid)
            return _plain(bk.get_book(conn, book))

    @router.delete("/book/{book}", dependencies=[Depends(require_token)])
    def book_archive(book: str, c: Caller = _CALLER) -> dict[str, Any]:
        """Close a book: open tickets are cancelled, it leaves every list and nightly job, its history stays."""
        from . import book as bk
        _operator_only(c.actor, "closing a book")
        with get_connection() as conn:
            own_book(conn, book, c)
            b = bk.archive(conn, book)
            journal.record(conn, book, c.actor, "settings", rationale="book closed", refs={"archived": True})
            return _plain(b)

    @router.get("/book/{book}")
    def book_get(book: str, c: Caller = _CALLER) -> dict[str, Any]:
        from . import book as bk
        with get_connection() as conn:
            own_book(conn, book, c)
            try:
                s = bk.snapshot(conn, book)
            except ValueError as e:
                raise HTTPException(status_code=404, detail=str(e)) from None
            with conn.cursor() as cur:
                cur.execute("SELECT id, trade_date, code, side, lots, price, fee, source, note FROM idx.fill WHERE book = %s ORDER BY trade_date DESC, id DESC LIMIT 200", (book,))
                fills = [dict(r) for r in cur.fetchall()]
            alerts = [a for a in runlog.open_alerts(conn, 100) if a["job"] == f"book:{book}"]
        return {"book": s["book"], "positions": s["positions"], "closed": s["closed"], "nav": s["nav"], "positions_value": s["positions_value"],
                "nav_now": s["nav_now"], "fills": fills, "alerts": alerts}

    @router.post("/book/{book}/fills", dependencies=[Depends(require_token)])
    def book_fill(book: str, body: dict[str, Any] = _BODY, c: Caller = _CALLER) -> dict[str, Any]:
        """{trade_date, code, side, lots, price, fee?, note?} -> records the fill, moves cash, rebuilds positions, marks.
        Live fills are facts from the broker: operator only."""
        from decimal import Decimal

        from . import book as bk
        from . import ticket
        actor = c.actor
        if ticket.is_live(book):
            _operator_only(actor, "recording a fill on the live book")
        with get_connection() as conn:
            own_book(conn, book, c)
            try:
                fid = bk.add_fill(conn, book, date.fromisoformat(body["trade_date"]), body["code"], body["side"], Decimal(str(body["lots"])),
                                  Decimal(str(body["price"])), Decimal(str(body["fee"])) if body.get("fee") is not None else None, note=body.get("note"),
                                  source=actor if actor != "operator" else "manual")
                bk.mark(conn, book)
            except (ValueError, KeyError) as e:
                raise HTTPException(status_code=422, detail=str(e)) from None
            journal.record(conn, book, actor, "fill", code=body.get("code"), rationale=body.get("note"),
                           refs={"fill_id": fid, "side": body.get("side"), "lots": body.get("lots"), "price": body.get("price"), "fee": body.get("fee")})
        return {"fill_id": fid}

    @router.put("/book/{book}", dependencies=[Depends(require_token)])
    def book_put(book: str, body: dict[str, Any] = _BODY, c: Caller = _CALLER) -> dict[str, Any]:
        """Set label / cash / fees / broker / strategy / size / overlays / risk limits: any of bk.SETTABLE_FIELDS. The agent may
        set only ``note`` - everything else is the operator's."""
        from . import book as bk
        actor = c.actor
        fields = {k: v for k, v in body.items() if k in bk.SETTABLE_FIELDS}
        if actor != "operator" and any(k not in bk.AGENT_SETTABLE_FIELDS for k in fields):
            _operator_only(actor, f"changing {sorted(k for k in fields if k not in bk.AGENT_SETTABLE_FIELDS)} on a book")
        with get_connection() as conn:
            own_book(conn, book, c)
            try:
                bk.ensure_book(conn, book, **fields)
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e)) from None
            journal.record(conn, book, actor, "settings", refs={k: v for k, v in fields.items()})
            return bk.get_book(conn, book)

    @router.post("/book/{book}/halt", dependencies=[Depends(require_token)])
    def book_halt(book: str, body: dict[str, Any] = _BODY, c: Caller = _CALLER) -> dict[str, Any]:
        """Kill switch (operator only): {reason}. No ticket builds or issues and no paper fill runs until resume."""
        from . import book as bk
        actor = c.actor
        _operator_only(actor, "halting a book")
        with get_connection() as conn:
            own_book(conn, book, c)
            try:
                b = bk.halt(conn, book, str(body.get("reason") or "operator halt"))
            except ValueError as e:
                raise HTTPException(status_code=404, detail=str(e)) from None
            journal.record(conn, book, actor, "halt", rationale=b.get("halt_reason"))
            return b

    @router.post("/book/{book}/resume", dependencies=[Depends(require_token)])
    def book_resume(book: str, c: Caller = _CALLER) -> dict[str, Any]:
        from . import book as bk
        actor = c.actor
        _operator_only(actor, "resuming a book")
        with get_connection() as conn:
            own_book(conn, book, c)
            try:
                b = bk.resume(conn, book)
            except ValueError as e:
                raise HTTPException(status_code=404, detail=str(e)) from None
            journal.record(conn, book, actor, "resume")
            return b

    @router.get("/macro")
    def macro_board() -> dict[str, Any]:
        """Every macro series with its latest reading, 1/3/12-month change and a 24-month history."""
        from . import macro
        with get_connection() as conn:
            rows = macro.board(conn)
        return {"as_of": datetime.now(UTC).isoformat(), "series": rows}

    @router.post("/macro/pull", dependencies=[Depends(require_token)])
    def macro_pull(body: dict[str, Any] = _BODY, c: Caller = _CALLER) -> dict[str, Any]:
        service_only(c, "/macro/pull")
        from . import macro
        with get_connection() as conn:
            r = macro.pull(conn, keys=body.get("keys"), full=bool(body.get("full")))
        return {"status": r.status, "rows": r.rows_out, "detail": r.detail, "warnings": r.warnings}

    @router.get("/overlay")
    def overlay_get() -> dict[str, Any]:
        """The regime record (latest check + history) and which books have an overlay on."""
        from . import overlay
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT book, regime_filter, entry_gate, take_profit_pct, trend_exit, cash_floor_pct, stress_cash_pct, stress_rule FROM idx.book ORDER BY book")
            books = [dict(r) for r in cur.fetchall()]
            return {"index": overlay.INDEX, "sma_days": overlay.SMA_DAYS, "latest": overlay.latest(conn), "history": overlay.history(conn), "books": books,
                    "stress": overlay.latest_stress(conn), "stress_history": overlay.stress_history(conn)}

    @router.post("/overlay/check", dependencies=[Depends(require_token)])
    def overlay_check(body: dict[str, Any] = _BODY, c: Caller = _CALLER) -> dict[str, Any]:
        """Run the monthly check now: {as_of?, dry_run?}. Dry run reports without recording or building tickets."""
        service_only(c, "/overlay/check")
        from . import overlay
        with get_connection() as conn:
            try:
                d = date.fromisoformat(body["as_of"]) if body.get("as_of") else date.today()
                rep = overlay.monthly_check(conn, d, build=not bool(body.get("dry_run")))
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e)) from None
        return rep

    @router.get("/ticket/latest")
    def ticket_latest(book: str = "live", c: Caller = _CALLER) -> dict[str, Any]:
        from . import ticket
        with get_connection() as conn:
            own_book(conn, book, c)
            t = ticket.load(conn, None, book)
        if t is None:
            raise HTTPException(status_code=404, detail="no ticket")
        return t

    @router.get("/ticket/{ticket_id}")
    def ticket_get(ticket_id: int, c: Caller = _CALLER) -> dict[str, Any]:
        with get_connection() as conn:
            return own_ticket(conn, ticket_id, c)

    @router.post("/ticket/build", dependencies=[Depends(require_token)])
    def ticket_build(book: str = "live", mode: str = "rebalance", as_of: str | None = None, max_names: int | None = None,
                     strategy: str | None = None, c: Caller = _CALLER) -> dict[str, Any]:
        """Build and store a draft. Refused on a halted book. The ticket remembers who built it (params.actor): the turnover
        guardrail applies to agent-built rebalances. The response carries ``checks`` = the validation the ticket would face at issue."""
        from . import ticket
        actor = c.actor
        with get_connection() as conn:
            own_book(conn, book, c)
            try:
                res = ticket.build(conn, book, mode=mode, run_date=date.fromisoformat(as_of) if as_of else None, max_names=max_names,
                                   strategy=strategy)
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e)) from None
            tid = ticket.store(conn, res, actor=actor)
            t = ticket.load(conn, tid)
            t["checks"] = ticket.validate(conn, tid)
            journal.record(conn, book, actor, "ticket_build", ticket_id=tid,
                           refs={"mode": t["mode"], "n_lines": len(t["lines"]), "run_date": t["run_date"], "ok": t["checks"]["ok"],
                                 "breaches": [x["kind"] for x in t["checks"]["breaches"]]})
            if ticket.is_live(book) and t["lines"]:                   # the operator works live tickets by hand: tell them
                from . import notify
                t["notified"] = notify.send(f"drafted by {actor}\n" + notify.format_ticket(t, t["checks"]), data=notify.ticket_data(t), book=book)
            return t

    @router.get("/ticket/{ticket_id}/validate")
    def ticket_validate(ticket_id: int, c: Caller = _CALLER) -> dict[str, Any]:
        """The guardrails a ticket faces at issue, against the book's current positions and limits: {ok, breaches[], nav,
        cash_after, turnover, weights, sectors, book_status}."""
        from . import ticket
        with get_connection() as conn:
            own_ticket(conn, ticket_id, c)
            try:
                return ticket.validate(conn, ticket_id)
            except ValueError as e:
                raise HTTPException(status_code=404, detail=str(e)) from None

    @router.post("/ticket/{ticket_id}/status", dependencies=[Depends(require_token)])
    def ticket_status(ticket_id: int, body: dict[str, Any] = _BODY, c: Caller = _CALLER) -> dict[str, Any]:
        """{status: draft|issued|closed|cancelled, rationale?}. 403 when the two-key rule refuses (live issue/close by the agent);
        422 when the book is halted or the ticket fails validation (the detail lists every breach)."""
        from . import ticket
        actor = c.actor
        status = body.get("status")
        if status not in ticket.STATUSES:
            raise HTTPException(status_code=422, detail="status must be draft|issued|closed|cancelled")
        with get_connection() as conn:
            own_ticket(conn, ticket_id, c)
            try:
                return ticket.set_status(conn, ticket_id, status, actor=actor, rationale=body.get("rationale"))
            except PermissionError as e:
                raise HTTPException(status_code=403, detail=str(e)) from None
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e)) from None

    @router.post("/ticket/lines/{line_id}/fill", dependencies=[Depends(require_token)])
    def ticket_fill(line_id: int, body: dict[str, Any] = _BODY, c: Caller = _CALLER) -> dict[str, Any]:
        """{lots, price, fee?, trade_date?, note?} - the broker's executed numbers for one line. Live lines: operator only."""
        from decimal import Decimal

        from . import ticket
        actor = c.actor
        with get_connection() as conn:
            ln = own_line(conn, line_id, c)
            if ticket.is_live(ln["book"]):
                _operator_only(actor, "recording a fill on a live ticket")
            try:
                r = ticket.fill_line(conn, line_id, Decimal(str(body["lots"])), Decimal(str(body["price"])),
                                     Decimal(str(body["fee"])) if body.get("fee") is not None else None,
                                     date.fromisoformat(body["trade_date"]) if body.get("trade_date") else None, body.get("note"),
                                     source=actor if actor != "operator" else "manual")
            except (ValueError, KeyError) as e:
                raise HTTPException(status_code=422, detail=str(e)) from None
            journal.record(conn, ln["book"], actor, "ticket_fill", code=ln["code"], ticket_id=ln["ticket_id"], line_id=line_id,
                           rationale=body.get("note"), refs={"lots": body.get("lots"), "price": body.get("price"), "fee": body.get("fee"), "status": r["status"]})
            return r

    @router.post("/ticket/lines/{line_id}/skip", dependencies=[Depends(require_token)])
    def ticket_skip(line_id: int, body: dict[str, Any] = _BODY, c: Caller = _CALLER) -> dict[str, Any]:
        from . import ticket
        actor = c.actor
        with get_connection() as conn:
            ln = own_line(conn, line_id, c)
            reason = str(body.get("reason") or f"{actor} skip")
            ticket.skip_line(conn, line_id, reason)
            journal.record(conn, ln["book"], actor, "ticket_skip", code=ln["code"], ticket_id=ln["ticket_id"], line_id=line_id, rationale=reason)
        return {"id": line_id, "status": "skipped"}

    @router.get("/decision")
    def decision_list(book: str | None = None, code: str | None = None, action: str | None = None, limit: int = 50,
                      c: Caller = _CALLER) -> list[dict[str, Any]]:
        """The caller's decision journal (every account's for a service), newest first: who did what on which book/name/ticket and why."""
        with get_connection() as conn:
            if book:
                own_book(conn, book, c)
            rows = journal.recent(conn, book, code, limit, action, user_id=c.user_id)
        return [{k: (v.isoformat() if isinstance(v, date | datetime) else v) for k, v in r.items()} for r in rows]

    @router.post("/decision", dependencies=[Depends(require_token)])
    def decision_add(body: dict[str, Any] = _BODY, c: Caller = _CALLER) -> dict[str, Any]:
        """A free journal entry in the caller's journal: {rationale, book?, code?, ticket_id?, line_id?, action? (default note), refs?}."""
        if not str(body.get("rationale") or "").strip():
            raise HTTPException(status_code=422, detail="rationale is required")
        with get_connection() as conn:
            if body.get("book"):
                own_book(conn, str(body["book"]), c)
            did = journal.record(conn, body.get("book"), c.actor, str(body.get("action") or "note"), code=body.get("code"),
                                 ticket_id=body.get("ticket_id"), line_id=body.get("line_id"), rationale=str(body["rationale"]), refs=body.get("refs"),
                                 user_id=c.user_id)
        return {"id": did}

    @router.get("/watchlist")
    def watchlist(c: Caller = _CALLER) -> list[dict[str, Any]]:
        """The caller's watchlist (empty for an unscoped service)."""
        if not c.scoped:
            return []
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT code, note, added_at FROM idx.watchlist WHERE user_id = %s ORDER BY code", (c.user_id,))
            return [dict(r) for r in cur.fetchall()]

    @router.put("/watchlist", dependencies=[Depends(require_token)])
    def watchlist_put(items: list[dict[str, Any]] = _BODY, c: Caller = _CALLER) -> dict[str, Any]:
        """Replace the caller's watchlist with the given [{code, note}] list."""
        uid = need_user(c, "a watchlist")
        codes = {str(i.get("code") or "").upper().strip(): (i.get("note") or None) for i in items if i.get("code")}
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM idx.watchlist WHERE user_id = %s AND NOT (code = ANY(%s))", (uid, list(codes)))
            for code, n in codes.items():
                cur.execute("INSERT INTO idx.watchlist (user_id, code, note) VALUES (%s, %s, %s) ON CONFLICT (user_id, code) DO UPDATE SET note = EXCLUDED.note",
                            (uid, code, n))
            conn.commit()
        return {"codes": sorted(codes)}

    @router.get("/study")
    def study_list(name: str | None = None) -> dict[str, Any]:
        """Research runs stored in the DB (migration 0020), newest first."""
        from . import research_store as rs
        with get_connection() as conn:
            return {"studies": rs.studies(conn, name)}

    @router.get("/study/latest")
    def study_latest(name: str) -> dict[str, Any]:
        from . import research_store as rs
        with get_connection() as conn:
            st = rs.study(conn, None, name)
        if not st:
            raise HTTPException(status_code=404, detail="no run of that study")
        return st

    @router.get("/study/{study_id}")
    def study_get(study_id: int) -> dict[str, Any]:
        from . import research_store as rs
        with get_connection() as conn:
            st = rs.study(conn, study_id)
        if not st:
            raise HTTPException(status_code=404, detail="study not found")
        return st

    @router.get("/name/{code}")
    def name_get(code: str) -> dict[str, Any]:
        """One name's whole picture: the studies that flag it, evidence by kind, plan sections, pack answers, consensus."""
        from . import research_store as rs
        with get_connection() as conn:
            return rs.name_view(conn, code)

    @router.post("/name/{code}/evidence", dependencies=[Depends(require_token)])
    def name_evidence_add(code: str, body: dict[str, Any] = _BODY, c: Caller = _CALLER) -> dict[str, Any]:
        service_only(c, "adding evidence")
        from . import research_store as rs
        with get_connection() as conn:
            try:
                new = rs.add_evidence(conn, code, body["kind"], body["title"], source=body.get("source"), url=body.get("url"),
                                      summary=body.get("summary"), tags=body.get("tags"), study_id=body.get("study_id"))
            except (ValueError, KeyError) as e:
                raise HTTPException(status_code=422, detail=f"{e}; kinds: {', '.join(rs.EVIDENCE_KINDS)}") from None
        return {"added": new}

    return router
