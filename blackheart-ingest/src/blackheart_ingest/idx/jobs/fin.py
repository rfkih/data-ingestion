"""``fin`` job — IDX financial statements: discovery (bulk listing) + workbook download.

Archive: fiscal 2020 onward (nothing before). Periods ``tw1|tw2|tw3|audit``. Each report row carries
``File_Modified`` = the moment IDX published it — the only point-in-time timestamp that matters.
The parse target is IDX's standardized taxonomy workbook ``FinancialStatement-<year>-<period>-<code>.xlsx``
(binary archived under ``<bronze_dir>/../fin/<code>/`` and indexed in ``idx.bronze_index``).
"""
from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import psycopg

from .. import runlog
from ..bronze import bronze_dir
from ..client import IdxClient, IdxFetchError

logger = logging.getLogger(__name__)
JOB = "fin"
WIB = ZoneInfo("Asia/Jakarta")
PERIODS = ("tw1", "tw2", "tw3", "audit")
PERIOD_LABEL = {"tw1": "TW1", "tw2": "TW2", "tw3": "TW3", "audit": "TAHUNAN"}
PAGE = 100


def _ts(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s[:19]).replace(tzinfo=WIB).astimezone(UTC)


def fin_dir() -> Path:
    return bronze_dir().parent / "fin"


def discover(conn: psycopg.Connection, client: IdxClient, year: int, period: str) -> runlog.RunResult:
    """Bulk listing for one (year, period) across all emiten -> idx.financial_report (attachments as JSON)."""
    r = runlog.RunResult(JOB + ":discover", f"{year}:{period}")
    run_id = runlog.start(conn, JOB + ":discover", r.run_key)
    try:
        page_no, total, rows = 1, None, []                 # indexFrom is a 1-based PAGE number (0 == 1)
        while True:
            res = client.financial_report(year, period, "", index_from=page_no, page_size=PAGE)
            payload = res.payload if isinstance(res.payload, dict) else {}
            total = payload.get("ResultCount") if total is None else total
            page = payload.get("Results") or []
            rows.extend(page)
            page_no += 1
            if len(page) < PAGE or (total is not None and len(rows) >= total) or page_no > 50:
                break
        r.rows_in = len(rows)
        out = []
        for x in rows:
            code = (x.get("KodeEmiten") or "").strip().upper()
            pub = _ts(x.get("File_Modified"))
            if not code or pub is None:
                continue
            atts = [{"name": a.get("File_Name"), "path": a.get("File_Path"), "size": a.get("File_Size"), "type": a.get("File_Type")}
                    for a in (x.get("Attachments") or [])]
            out.append({"code": code, "fiscal_year": int(x.get("Report_Year") or year), "period": PERIOD_LABEL[period],
                        "report_type": "rdf", "published_at": pub, "attachments": psycopg.types.json.Jsonb(atts),
                        "has_xlsx": any((a.get("name") or "").lower().endswith(".xlsx") for a in atts)})
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO idx.financial_report (code, fiscal_year, period, report_type, published_at, attachments, parse_status)
                VALUES (%(code)s, %(fiscal_year)s, %(period)s, %(report_type)s, %(published_at)s, %(attachments)s,
                        CASE WHEN %(has_xlsx)s THEN 'pending' ELSE 'no_workbook' END)
                ON CONFLICT (code, fiscal_year, period, report_type) DO UPDATE SET
                    published_at = LEAST(idx.financial_report.published_at, EXCLUDED.published_at),
                    attachments = EXCLUDED.attachments
                """, out)
        conn.commit()
        r.rows_out = len(out)
        r.detail["with_xlsx"] = sum(1 for o in out if o["has_xlsx"])
    except Exception as e:
        conn.rollback()
        r.status = "failed"
        r.error = f"{type(e).__name__}: {e}"[:500]
        logger.exception("idx fin discover %s %s failed", year, period)
    runlog.finish(conn, run_id, r)
    return r


def _pending(conn: psycopg.Connection, codes: list[str] | None, years: list[int] | None, periods: list[str] | None) -> list[dict[str, Any]]:
    q = """
        SELECT id, code, fiscal_year, period, attachments FROM idx.financial_report
         WHERE parse_status = 'pending' AND report_type = 'rdf'
    """
    params: list[Any] = []
    if codes:
        q += " AND code = ANY(%s)"
        params.append(codes)
    if years:
        q += " AND fiscal_year = ANY(%s)"
        params.append(years)
    if periods:
        q += " AND period = ANY(%s)"
        params.append([PERIOD_LABEL[p] for p in periods])
    q += " ORDER BY published_at DESC"
    with conn.cursor() as cur:
        cur.execute(q, params)
        rows = cur.fetchall()
    cols = ["id", "code", "fiscal_year", "period", "attachments"]
    return [r if isinstance(r, dict) else dict(zip(cols, r, strict=True)) for r in rows]


def download(conn: psycopg.Connection, client: IdxClient, *, codes: list[str] | None = None, years: list[int] | None = None,
             periods: list[str] | None = None, limit: int | None = None) -> runlog.RunResult:
    """Fetch the standardized workbook for pending reports -> fin dir + bronze_index; parse_status -> 'downloaded'."""
    r = runlog.RunResult(JOB + ":download", ",".join(codes[:3]) + ("…" if codes and len(codes) > 3 else "") if codes else "all")
    run_id = runlog.start(conn, JOB + ":download", r.run_key)
    todo = _pending(conn, codes, years, periods)
    if limit:
        todo = todo[:limit]
    r.rows_in = len(todo)
    ok = bad = 0
    try:
        for rep in todo:
            atts = rep["attachments"] or []
            xl = next((a for a in atts if (a.get("name") or "").lower().endswith(".xlsx")), None)
            if not xl or not xl.get("path"):
                _set_status(conn, rep["id"], "no_workbook")
                bad += 1
                continue
            try:
                body = client.download(xl["path"])
            except IdxFetchError as e:
                _set_status(conn, rep["id"], "download_failed", str(e)[:200])
                bad += 1
                if "circuit" in str(e).lower():
                    raise
                continue
            if not body.startswith(b"PK"):                    # not a real xlsx (error page)
                _set_status(conn, rep["id"], "no_workbook", "attachment is not a zip/xlsx")
                bad += 1
                continue
            d = fin_dir() / rep["code"]
            d.mkdir(parents=True, exist_ok=True)
            path = d / f"{rep['fiscal_year']}_{rep['period']}.xlsx"
            path.write_bytes(body)
            sha = hashlib.sha256(body).hexdigest()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO idx.bronze_index (endpoint, key, fetched_at, path, sha256, bytes, http_status, fingerprint)
                    VALUES ('financial_xlsx', %s, %s, %s, %s, %s, 200, NULL) RETURNING id
                    """,
                    (f"{rep['code']}:{rep['fiscal_year']}:{rep['period']}", datetime.now(UTC),
                     str(path.relative_to(bronze_dir().parent)).replace("\\", "/"), sha, len(body)))
                bid = cur.fetchone()
                bid = bid[0] if isinstance(bid, tuple) else bid["id"]
                cur.execute("UPDATE idx.financial_report SET parse_status = 'downloaded', bronze_id = %s, checksum = %s WHERE id = %s",
                            (bid, sha, rep["id"]))
            conn.commit()
            ok += 1
            if (ok + bad) % 100 == 0:
                logger.info("idx fin download %d/%d ok=%d bad=%d", ok + bad, len(todo), ok, bad)
    except Exception as e:
        conn.rollback()
        r.status = "partial" if ok else "failed"
        r.error = f"{type(e).__name__}: {e}"[:500]
        logger.exception("idx fin download stopped")
    r.rows_out = ok
    r.detail["bad"] = bad
    runlog.finish(conn, run_id, r)
    return r


def _set_status(conn: psycopg.Connection, report_id: int, status: str, note: str | None = None) -> None:
    with conn.cursor() as cur:
        cur.execute("UPDATE idx.financial_report SET parse_status = %s WHERE id = %s", (status, report_id))
    conn.commit()
    if note:
        logger.info("idx fin report %s -> %s (%s)", report_id, status, note)
