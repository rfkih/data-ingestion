"""Public, read-only API for the signals app (open-research plan phase 2; spec §02-§06). No auth, no books, no tickets,
no user data: factor scores, the screener with editable templates, the historical statistics behind each criteria, and
the research archive. Everything here is the same for every caller and computed by formulas the pages show.

Mounted at ``/pub`` next to ``/idx`` (which stays token-guarded). The signals app proxies only ``/pub/*``.
"""
from __future__ import annotations

import time
from collections import deque
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query, Request, Response

from ..shared.db import get_connection
from . import quality, scores, signal_stats
from .card import _rows

OPS = {"eq", "ne", "gte", "lte", "gt", "lt", "in", "contains"}
RATE_PER_MINUTE = 120
_hits: dict[str, deque[float]] = {}
RESEARCH_DIR = Path(__file__).resolve().parents[4] / "research"
_BODY = Body(...)
_DATE = Query(default=None, alias="date")


def _limit(request: Request) -> None:
    ip = request.client.host if request.client else "?"
    now = time.monotonic()
    q = _hits.setdefault(ip, deque())
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= RATE_PER_MINUTE:
        raise HTTPException(status_code=429, detail="too many requests; try again in a minute")
    q.append(now)


def _cache(response: Response, seconds: int = 900) -> None:
    response.headers["Cache-Control"] = f"public, max-age={seconds}"


def field_value(row: dict[str, Any], field: str) -> Any:
    kind = scores.FIELDS.get(field)
    if kind is None:
        raise HTTPException(status_code=400, detail=f"unknown field {field!r}")
    return row.get(field) if kind[0] == "score" else (row.get("inputs") or {}).get(field)


def matches(row: dict[str, Any], criteria: list[dict[str, Any]]) -> bool:
    for c in criteria:
        v, op, want = field_value(row, c["field"]), c["op"], c.get("value")
        if op not in OPS:
            raise HTTPException(status_code=400, detail=f"unknown op {op!r}")
        if v is None:
            return False
        try:
            if op == "eq" and not (v == want):
                return False
            if op == "ne" and not (v != want):
                return False
            if op == "gte" and not (float(v) >= float(want)):
                return False
            if op == "lte" and not (float(v) <= float(want)):
                return False
            if op == "gt" and not (float(v) > float(want)):
                return False
            if op == "lt" and not (float(v) < float(want)):
                return False
            if op == "in" and v not in (want or []):
                return False
            if op == "contains" and str(want).lower() not in str(v).lower():
                return False
        except (TypeError, ValueError) as e:
            raise HTTPException(status_code=400, detail=f"bad value for {c['field']}: {e}") from None
    return True


def criteria_text(criteria: list[dict[str, Any]]) -> list[str]:
    """The criteria in words - one sentence per clause, from the field catalogue (the single source the UI shows)."""
    words = {"eq": "=", "ne": "≠", "gte": "≥", "lte": "≤", "gt": ">", "lt": "<", "in": "salah satu dari", "contains": "mengandung"}
    out = []
    for c in criteria:
        f = scores.FIELDS.get(c["field"])
        label = f[2] if f else c["field"]
        if f and f[1] == "bool":
            out.append(label if c.get("value") in (True, "true", 1) else f"bukan: {label}")
        else:
            v = c.get("value")
            if c["field"] in ("mom_12_1", "ep", "ep_ttm", "bp", "dy", "roe") and isinstance(v, (int, float)):
                v = f"{float(v) * 100:+.0f} %" if c["field"] == "mom_12_1" else f"{float(v) * 100:.1f} %"
            out.append(f"{label} {words.get(c['op'], c['op'])} {v}")
    return out


def _templates(conn) -> list[dict[str, Any]]:
    rows = _rows(conn, "SELECT key, label, description, criteria, stats_criteria, stats_bucket, sort, position FROM idx.template ORDER BY position, key", (),
                 ["key", "label", "description", "criteria", "stats_criteria", "stats_bucket", "sort", "position"])
    for r in rows:
        r["criteria_text"] = criteria_text(r["criteria"])
    return rows


def _stats_block(conn, criteria: str | None, bucket: str = "all") -> dict[str, Any]:
    """The header statistics for a template: the rows for its criteria, the named bucket first."""
    if not criteria:
        return {"criteria": None, "rows": [], "note": "belum ada statistik historis untuk kriteria ini"}
    rows = signal_stats.rows(conn, criteria)
    rows.sort(key=lambda r: (not r["bucket"].startswith(bucket), r["horizon_days"], r["bucket"]))
    return {"criteria": criteria, "rows": rows, "note": None if rows else "belum ada statistik historis untuk kriteria ini"}


def _cards_for(conn, row: dict[str, Any], templates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Which templates this name meets today, each with its statistics (bucket-matched where the row has one)."""
    cards = []
    for t in templates:
        if matches(row, t["criteria"]):
            block = _stats_block(conn, t["stats_criteria"], t["stats_bucket"])
            own = [r for r in block["rows"] if row.get("bucket") and r["bucket"].startswith(row["bucket"])]
            cards.append({"template": t["key"], "label": t["label"], "criteria_text": t["criteria_text"], "stats": block, "bucket_rows": own})
    return cards


def make_router() -> APIRouter:
    router = APIRouter(prefix="/pub", tags=["pub"])

    @router.get("/scores")
    def get_scores(request: Request, response: Response, date_: date | None = _DATE, codes: str | None = None):
        _limit(request)
        with get_connection() as conn:
            rows = scores.rows_for(conn, date_, [c.strip().upper() for c in codes.split(",")] if codes else None)
        _cache(response)
        return {"as_of": rows[0]["trade_date"] if rows else None, "n": len(rows), "rows": rows}

    @router.get("/scores/{code}")
    def get_score(code: str, request: Request, response: Response):
        _limit(request)
        with get_connection() as conn:
            rows = scores.rows_for(conn, None, [code.upper()])
            if not rows:
                raise HTTPException(status_code=404, detail=f"no score for {code.upper()} (not in the liquid universe on the latest date)")
            row = rows[0]
            hist = scores.history(conn, code)
            templates = _templates(conn)
            cards = _cards_for(conn, row, templates)
        inputs = row.get("inputs") or {}
        gate_res = {"gates": inputs.get("quality_gates"), "metrics": inputs.get("quality_metrics"), "is_financial": inputs.get("quality_is_financial")}
        _cache(response)
        return {"row": row, "history": hist, "gates": quality.gate_table(gate_res) if inputs.get("quality_gates") else [], "cards": cards,
                "disclaimer": "Skor dan statistik dihitung dari data publik dengan rumus terbuka, sama untuk semua orang, dan menggambarkan masa lalu "
                              "kelompok saham - bukan perkiraan, bukan rekomendasi jual atau beli."}

    @router.get("/templates")
    def get_templates(request: Request, response: Response):
        _limit(request)
        with get_connection() as conn:
            rows = _templates(conn)
        _cache(response, 3600)
        return rows

    @router.get("/screener/fields")
    def get_fields(request: Request, response: Response):
        _limit(request)
        _cache(response, 3600)
        return [{"field": k, "kind": v[0], "type": v[1], "label": v[2]} for k, v in scores.FIELDS.items()]

    @router.post("/screener")
    def post_screener(request: Request, response: Response, body: dict[str, Any] = _BODY):
        _limit(request)
        criteria = body.get("criteria") or []
        if not isinstance(criteria, list) or len(criteria) > 12:
            raise HTTPException(status_code=400, detail="criteria: a list of at most 12 clauses")
        for c in criteria:
            if not isinstance(c, dict) or "field" not in c or "op" not in c:
                raise HTTPException(status_code=400, detail="each clause needs field, op, value")
            field_value({"inputs": {}}, c["field"])                          # validates the field name
        sort = body.get("sort") or "value"
        if sort not in scores.FIELDS:
            raise HTTPException(status_code=400, detail=f"unknown sort field {sort!r}")
        limit = max(1, min(int(body.get("limit") or 200), 500))
        weights = body.get("weights") or {}
        template_key = body.get("template")
        with get_connection() as conn:
            rows = scores.rows_for(conn, body.get("date"))
            templates = _templates(conn)
            t = next((x for x in templates if x["key"] == template_key), None) if template_key else None
            stats = _stats_block(conn, t["stats_criteria"], t["stats_bucket"]) if t else {"criteria": None, "rows": [], "note": None}
        out = [r for r in rows if matches(r, criteria)]
        if weights:
            ws = {k: float(v) for k, v in weights.items() if k in ("value", "quality", "trend") and v is not None}
            tot = sum(ws.values()) or 1.0
            for r in out:
                parts = [(r[k] or 0) * w for k, w in ws.items() if r.get(k) is not None]
                r["composite"] = round(sum(parts) / tot, 1) if parts else None
        key = (lambda r: (r.get("composite") is None, -(r.get("composite") or 0))) if weights else (lambda r: (field_value(r, sort) is None, -float(field_value(r, sort) or 0) if scores.FIELDS[sort][1] == "number" else 0))
        out.sort(key=key)
        _cache(response, 300)
        return {"as_of": rows[0]["trade_date"] if rows else None, "universe": len(rows), "n": len(out), "criteria_text": criteria_text(criteria),
                "stats": stats, "rows": out[:limit]}

    @router.get("/signal_stats")
    def get_signal_stats(request: Request, response: Response, criteria: str | None = None, bucket: str | None = None):
        _limit(request)
        with get_connection() as conn:
            rows = signal_stats.rows(conn, criteria, bucket)
        _cache(response, 3600)
        return rows

    @router.get("/research")
    def get_research(request: Request, response: Response, limit: int = 100):
        _limit(request)
        with get_connection() as conn:
            rows = _rows(conn, """SELECT id, name, as_of, run_at, note, report_path, (params->>'n_trials_cumulative')::int AS trials
                                    FROM idx.study WHERE report_path IS NOT NULL ORDER BY id DESC LIMIT %s""", (limit,),
                         ["id", "name", "as_of", "run_at", "note", "report_path", "trials"])
        for r in rows:
            r["report"] = Path(r["report_path"]).name if r["report_path"] else None
            r["available"] = bool(r["report"] and (RESEARCH_DIR / r["report"]).exists())
            r.pop("report_path", None)
        _cache(response, 3600)
        return rows

    @router.get("/research/{study_id}")
    def get_research_one(study_id: int, request: Request, response: Response):
        _limit(request)
        with get_connection() as conn:
            rows = _rows(conn, "SELECT id, name, as_of, note, report_path FROM idx.study WHERE id = %s", (study_id,), ["id", "name", "as_of", "note", "report_path"])
        if not rows or not rows[0]["report_path"]:
            raise HTTPException(status_code=404, detail="no report for this study")
        f = RESEARCH_DIR / Path(rows[0]["report_path"]).name
        if not f.exists():
            raise HTTPException(status_code=404, detail="report file not on this host")
        _cache(response, 3600)
        return {"id": rows[0]["id"], "name": rows[0]["name"], "as_of": rows[0]["as_of"], "note": rows[0]["note"], "report": f.name,
                "markdown": f.read_text(encoding="utf-8")}

    return router
