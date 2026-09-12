"""HTTP surface for the app (``/idx/*``), mounted on the served ingest FastAPI app.

Read routes are open (same-origin proxy from the frontend); the acknowledge
route reuses the server's ``require_token`` gate when INGEST_AUTH_TOKEN is set.
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException

from ..shared.db import get_connection
from . import runlog
from .jobs import daily as job_daily

_BODY = Body(...)


def make_router(require_token) -> APIRouter:
    router = APIRouter(prefix="/idx", tags=["idx"])

    @router.get("/ops")
    def ops() -> dict[str, Any]:
        with get_connection() as conn:
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
            alerts = runlog.open_alerts(conn)
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
    def ack(alert_id: int) -> dict[str, Any]:
        with get_connection() as conn:
            ok = runlog.acknowledge(conn, alert_id)
        if not ok:
            raise HTTPException(status_code=404, detail="alert not found or already acknowledged")
        return {"acknowledged": alert_id}

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
    def candidates(as_of: str | None = None, all: bool = False) -> dict[str, Any]:
        """Latest candidate list (or the latest on/before as_of): selected names first, the rest of the pool with all=1."""
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT max(run_date) AS d FROM idx.candidate WHERE (%s::date IS NULL OR run_date <= %s)", (as_of, as_of))
            d = dict(cur.fetchone())["d"]
            if d is None:
                return {"run_date": None, "pool": 0, "selected": 0, "rows": []}
            cur.execute(
                """
                SELECT c.run_date, c.code, l.name, c.rank, c.selected, c.score, c.price, c.mcap, c.ep, c.bp, c.dy, c.ep_ttm, c.roe, c.der,
                       c.np_yoy, c.gate_loose, c.gate_strict, c.strict_fails, c.warnings, c.f20, c.v60, c.annual_period, c.ttm_basis,
                       c.sector
                  FROM idx.candidate c LEFT JOIN idx.listing l USING (code)
                 WHERE c.run_date = %s AND (%s OR c.selected) ORDER BY c.rank
                """, (d, all))
            rows = [dict(r) for r in cur.fetchall()]
            cur.execute("SELECT count(*) AS n, count(*) FILTER (WHERE selected) AS s FROM idx.candidate WHERE run_date = %s", (d,))
            n = dict(cur.fetchone())
        return {"run_date": d.isoformat(), "pool": n["n"], "selected": n["s"], "rows": rows}

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
    def pack_build(as_of: str | None = None, next_n: int = 10) -> dict[str, Any]:
        from . import pack
        with get_connection() as conn:
            p = pack.build(conn, date.fromisoformat(as_of) if as_of else None, next_n=next_n)
            pack.store(conn, p)
        return {"pack_date": p["pack_date"].isoformat(), "names": len(p["codes"]), "chars": len(p["md"])}

    @router.post("/pack/{pack_date}/answer", dependencies=[Depends(require_token)])
    def pack_answer(pack_date: str, body: dict[str, Any] | list[Any] | str = _BODY) -> dict[str, Any]:
        from . import pack
        with get_connection() as conn:
            try:
                return pack.import_answer(conn, date.fromisoformat(pack_date), body)
            except pack.AnswerError as e:
                raise HTTPException(status_code=422, detail=str(e)) from None

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

    @router.get("/book/{book}")
    def book_get(book: str) -> dict[str, Any]:
        from . import book as bk
        with get_connection() as conn:
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
    def book_fill(book: str, body: dict[str, Any] = _BODY) -> dict[str, Any]:
        """{trade_date, code, side, lots, price, fee?, note?} -> records the fill, moves cash, rebuilds positions, marks."""
        from decimal import Decimal

        from . import book as bk
        with get_connection() as conn:
            try:
                fid = bk.add_fill(conn, book, date.fromisoformat(body["trade_date"]), body["code"], body["side"], Decimal(str(body["lots"])),
                                  Decimal(str(body["price"])), Decimal(str(body["fee"])) if body.get("fee") is not None else None, note=body.get("note"))
                bk.mark(conn, book)
            except (ValueError, KeyError) as e:
                raise HTTPException(status_code=422, detail=str(e)) from None
        return {"fill_id": fid}

    @router.put("/book/{book}", dependencies=[Depends(require_token)])
    def book_put(book: str, body: dict[str, Any] = _BODY) -> dict[str, Any]:
        """Set cash / fees / broker: any of {cash, fee_buy_pct, fee_sell_pct, div_tax_pct, broker, note}."""
        from . import book as bk
        with get_connection() as conn:
            bk.ensure_book(conn, book, **{k: v for k, v in body.items() if k in ("cash", "fee_buy_pct", "fee_sell_pct", "div_tax_pct", "broker", "note")})
            return bk.get_book(conn, book)

    @router.get("/ticket/latest")
    def ticket_latest(book: str = "live") -> dict[str, Any]:
        from . import ticket
        with get_connection() as conn:
            t = ticket.load(conn, None, book)
        if t is None:
            raise HTTPException(status_code=404, detail="no ticket")
        return t

    @router.get("/ticket/{ticket_id}")
    def ticket_get(ticket_id: int) -> dict[str, Any]:
        from . import ticket
        with get_connection() as conn:
            t = ticket.load(conn, ticket_id)
        if t is None:
            raise HTTPException(status_code=404, detail="no ticket")
        return t

    @router.post("/ticket/build", dependencies=[Depends(require_token)])
    def ticket_build(book: str = "live", mode: str = "rebalance", as_of: str | None = None, max_names: int | None = None) -> dict[str, Any]:
        from . import ticket
        with get_connection() as conn:
            try:
                res = ticket.build(conn, book, mode=mode, run_date=date.fromisoformat(as_of) if as_of else None, max_names=max_names)
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e)) from None
            tid = ticket.store(conn, res)
            return ticket.load(conn, tid)

    @router.post("/ticket/{ticket_id}/status", dependencies=[Depends(require_token)])
    def ticket_status(ticket_id: int, body: dict[str, Any] = _BODY) -> dict[str, Any]:
        from . import ticket
        status = body.get("status")
        if status not in ("draft", "issued", "closed", "cancelled"):
            raise HTTPException(status_code=422, detail="status must be draft|issued|closed|cancelled")
        with get_connection() as conn:
            ticket.set_status(conn, ticket_id, status)
        return {"id": ticket_id, "status": status}

    @router.post("/ticket/lines/{line_id}/fill", dependencies=[Depends(require_token)])
    def ticket_fill(line_id: int, body: dict[str, Any] = _BODY) -> dict[str, Any]:
        """{lots, price, fee?, trade_date?, note?}"""
        from decimal import Decimal

        from . import ticket
        with get_connection() as conn:
            try:
                return ticket.fill_line(conn, line_id, Decimal(str(body["lots"])), Decimal(str(body["price"])),
                                        Decimal(str(body["fee"])) if body.get("fee") is not None else None,
                                        date.fromisoformat(body["trade_date"]) if body.get("trade_date") else None, body.get("note"))
            except (ValueError, KeyError) as e:
                raise HTTPException(status_code=422, detail=str(e)) from None

    @router.post("/ticket/lines/{line_id}/skip", dependencies=[Depends(require_token)])
    def ticket_skip(line_id: int, body: dict[str, Any] = _BODY) -> dict[str, Any]:
        from . import ticket
        with get_connection() as conn:
            ticket.skip_line(conn, line_id, str(body.get("reason") or "operator skip"))
        return {"id": line_id, "status": "skipped"}

    @router.get("/watchlist")
    def watchlist() -> list[dict[str, Any]]:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT code, note, added_at FROM idx.watchlist ORDER BY code")
            return [dict(r) for r in cur.fetchall()]

    @router.put("/watchlist", dependencies=[Depends(require_token)])
    def watchlist_put(items: list[dict[str, Any]] = _BODY) -> dict[str, Any]:
        """Replace the watchlist with the given [{code, note}] list."""
        codes = {str(i.get("code") or "").upper().strip(): (i.get("note") or None) for i in items if i.get("code")}
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM idx.watchlist WHERE NOT (code = ANY(%s))", (list(codes),))
            for c, n in codes.items():
                cur.execute("INSERT INTO idx.watchlist (code, note) VALUES (%s, %s) ON CONFLICT (code) DO UPDATE SET note = EXCLUDED.note", (c, n))
            conn.commit()
        return {"codes": sorted(codes)}

    return router
