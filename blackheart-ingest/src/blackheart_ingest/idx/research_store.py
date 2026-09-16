"""Research results as rows (migration 0020): a study run (``idx.study``), the names it surfaced with their figures
(``idx.study_name``), and the evidence gathered per name (``idx.evidence``: news, disclosures, annual-report plans, web
references, notes). One read — ``name_view`` — assembles a name's whole picture: the studies that flagged it, the evidence,
the latest annual-report plan sections, pack answers and analyst consensus. The research scripts call ``record_study``
at the end of a run instead of leaving the answer in a markdown file only.
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import psycopg

logger = logging.getLogger(__name__)
EVIDENCE_KINDS = ("news", "announcement", "annual", "web", "analyst", "note")


def _jsonable(v: Any) -> Any:
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if hasattr(v, "item") and not isinstance(v, (str, bytes)):           # numpy scalars (bool_, int64, float64)
        v = v.item()
    if isinstance(v, float) and (v != v or v in (float("inf"), float("-inf"))):
        return None
    return v


def _rows(cur) -> list[dict[str, Any]]:
    cols = [d.name for d in cur.description]
    return [r if isinstance(r, dict) else dict(zip(cols, r, strict=True)) for r in cur.fetchall()]


# -- studies -----------------------------------------------------------------------------------------------------------

def record_study(conn: psycopg.Connection, name: str, as_of: date, *, params: dict[str, Any], summary: dict[str, Any],
                 names: list[dict[str, Any]], report_path: str | None = None, note: str | None = None) -> int:
    """Store one run. ``names``: dicts with code, screens (list), score, rank, features (dict), context (dict)."""
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO idx.study (name, as_of, params, summary, report_path, note) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
                    (name, as_of, json.dumps(_jsonable(params)), json.dumps(_jsonable(summary)), report_path, note))
        sid = _rows(cur)[0]["id"]
        cur.executemany("""INSERT INTO idx.study_name (study_id, code, screens, score, rank, features, context)
                           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                        [(sid, n["code"].upper(), list(n.get("screens") or []), n.get("score"), n.get("rank"),
                          json.dumps(_jsonable(n.get("features") or {})), json.dumps(_jsonable(n.get("context") or {}))) for n in names])
    conn.commit()
    logger.info("idx study %s #%s as of %s: %d names", name, sid, as_of, len(names))
    return sid


def studies(conn: psycopg.Connection, name: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute("""SELECT s.id, s.name, s.as_of, s.run_at, s.report_path, s.note, count(n.code) AS names
                         FROM idx.study s LEFT JOIN idx.study_name n ON n.study_id = s.id
                        WHERE (%s::text IS NULL OR s.name = %s) GROUP BY s.id ORDER BY s.run_at DESC LIMIT %s""", (name, name, limit))
        return _rows(cur)


def study(conn: psycopg.Connection, study_id: int | None = None, name: str | None = None) -> dict[str, Any] | None:
    """One study with its names: by id, else the latest run of ``name``."""
    with conn.cursor() as cur:
        if study_id is None:
            cur.execute("SELECT id FROM idx.study WHERE name = %s ORDER BY run_at DESC LIMIT 1", (name,))
            r = _rows(cur)
            if not r:
                return None
            study_id = r[0]["id"]
        cur.execute("SELECT id, name, as_of, run_at, params, summary, report_path, note FROM idx.study WHERE id = %s", (study_id,))
        s = _rows(cur)
        if not s:
            return None
        cur.execute("""SELECT code, screens, score, rank, features, context FROM idx.study_name WHERE study_id = %s
                       ORDER BY rank NULLS LAST, score DESC NULLS LAST, code""", (study_id,))
        out = s[0]
        out["names"] = _rows(cur)
        return out


# -- evidence ----------------------------------------------------------------------------------------------------------

def add_evidence(conn: psycopg.Connection, code: str, kind: str, title: str, *, ts: datetime | None = None, source: str | None = None,
                 url: str | None = None, summary: str | None = None, tags: list[str] | None = None, study_id: int | None = None) -> bool:
    """Insert one item; False when the same (code, kind, url, title) is already there."""
    if kind not in EVIDENCE_KINDS:
        raise ValueError(f"kind must be one of {EVIDENCE_KINDS}")
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO idx.evidence (code, kind, ts, source, title, url, summary, tags, study_id)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (dedup) DO NOTHING RETURNING id""",
                    (code.upper(), kind, ts, source, title.strip(), url, summary, list(tags or []), study_id))
        new = bool(cur.fetchone())
    conn.commit()
    return new


def collect_evidence(conn: psycopg.Connection, code: str, *, days: int = 365, study_id: int | None = None) -> dict[str, int]:
    """Pull what the data plane already holds for a name into idx.evidence: material disclosures (idx.announcement,
    event kinds only — registry/routine filings are noise), press items (idx.news_article) and the annual-report plan
    sections (idx.annual_excerpt). Idempotent."""
    from .jobs.announce import EVENT_KINDS
    code = code.upper()
    counts = {"announcement": 0, "news": 0, "annual": 0}
    with conn.cursor() as cur:
        cur.execute("""SELECT published_at, title, kind, id2 FROM idx.announcement
                        WHERE code = %s AND published_at >= now() - make_interval(days => %s) AND kind = ANY(%s)
                        ORDER BY published_at DESC LIMIT 60""", (code, days, list(EVENT_KINDS)))
        ann = _rows(cur)
        cur.execute("""SELECT source, url, published_at, title, body FROM idx.news_article
                        WHERE %s = ANY(codes) ORDER BY published_at DESC NULLS LAST LIMIT 60""", (code,))
        news = _rows(cur)
        cur.execute("""SELECT fiscal_year, section, page, text FROM idx.annual_excerpt WHERE code = %s
                          AND fiscal_year = (SELECT max(fiscal_year) FROM idx.annual_excerpt WHERE code = %s)""", (code, code))
        ann_ex = _rows(cur)
    for a in ann:
        counts["announcement"] += add_evidence(conn, code, "announcement", a["title"], ts=a["published_at"], source="idx.co.id",
                                               url=f"https://www.idx.co.id/id/perusahaan-tercatat/keterbukaan-informasi/?id={a['id2']}",
                                               tags=[a["kind"]], study_id=study_id)
    for n in news:
        counts["news"] += add_evidence(conn, code, "news", n["title"], ts=n["published_at"], source=n["source"], url=n["url"],
                                       summary=(n["body"] or "")[:600] or None, tags=["press"], study_id=study_id)
    for e in ann_ex:
        counts["annual"] += add_evidence(conn, code, "annual", f"Laporan tahunan FY{e['fiscal_year']} — {e['section']} (p.{e['page']})",
                                         ts=datetime(e["fiscal_year"] + 1, 4, 30, tzinfo=UTC), source="annual report",
                                         summary=(e["text"] or "")[:1200], tags=["plan", e["section"]], study_id=study_id)
    return counts


def evidence(conn: psycopg.Connection, code: str, kinds: list[str] | None = None, limit: int = 100) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute("""SELECT id, kind, ts, source, title, url, summary, tags, study_id, created_at FROM idx.evidence
                        WHERE code = %s AND (%s::text[] IS NULL OR kind = ANY(%s)) ORDER BY ts DESC NULLS LAST, id DESC LIMIT %s""",
                    (code.upper(), kinds, kinds, limit))
        return _rows(cur)


# -- the assembled view --------------------------------------------------------------------------------------------------

def name_view(conn: psycopg.Connection, code: str) -> dict[str, Any]:
    """Everything the desk knows about one name, in one read: the latest run of every study that lists it, the evidence
    by kind, the annual-report plan sections, pack answers, analyst consensus and the latest candidate row."""
    from . import consensus, pack
    code = code.upper()
    with conn.cursor() as cur:
        cur.execute("""SELECT DISTINCT ON (s.name) s.name, s.id AS study_id, s.as_of, s.run_at, n.screens, n.score, n.rank, n.features, n.context
                         FROM idx.study_name n JOIN idx.study s ON s.id = n.study_id
                        WHERE n.code = %s ORDER BY s.name, s.run_at DESC""", (code,))
        flagged = _rows(cur)
        cur.execute("SELECT name, board, sector, subsector, status FROM idx.listing WHERE code = %s", (code,))
        listing = (_rows(cur) or [None])[0]
        cur.execute("""SELECT run_date, rank, selected, price, mcap, ep, bp, dy, roe, der, gate_loose, gate_strict, strict_fails, warnings
                         FROM idx.candidate WHERE code = %s ORDER BY run_date DESC LIMIT 1""", (code,))
        cand = (_rows(cur) or [None])[0]
    ev = evidence(conn, code)
    by_kind: dict[str, list[dict[str, Any]]] = {}
    for e in ev:
        by_kind.setdefault(e["kind"], []).append(e)
    return {"code": code, "listing": listing, "candidate": cand, "studies": flagged, "evidence": by_kind,
            "pack_answers": pack.answers(conn, code, limit=10), "consensus": (consensus.latest(conn, [code]) or [None])[0]}


def render_name(view: dict[str, Any]) -> str:
    """Plain-text rendering of name_view for the CLI."""
    L = [f"== {view['code']}  {(view['listing'] or {}).get('name') or ''}  [{(view['listing'] or {}).get('sector') or '-'}]"]
    c = view["candidate"]
    if c:
        L.append(f"candidate {c['run_date']}: rank {c['rank']} {'SELECTED' if c['selected'] else ''} price {c['price']} E/P {c['ep']} B/P {c['bp']} DY {c['dy']} "
                 f"ROE {c['roe']} strict={'Y' if c['gate_strict'] else 'n'} {c['strict_fails'] or ''}")
    for s in view["studies"]:
        L.append(f"study {s['name']} #{s['study_id']} as of {s['as_of']}: screens={list(s['screens'])} score={s['score']} rank={s['rank']}")
        L.append("   " + json.dumps(_jsonable(s["features"]), default=str)[:400])
    for kind, items in view["evidence"].items():
        L.append(f"-- {kind} ({len(items)})")
        for e in items[:12]:
            ts = str(e["ts"])[:10] if e["ts"] else "          "
            L.append(f"   {ts} {e['title'][:110]}" + (f"  [{', '.join(e['tags'])}]" if e["tags"] else "") + (f"\n      {e['url']}" if e["url"] and kind == "web" else ""))
            if e["summary"] and kind in ("web", "note"):
                L.append(f"      {e['summary'][:300]}")
    if view["consensus"]:
        k = view["consensus"]
        L.append(f"-- consensus {k['snapshot_date']}: target {k['target_mean']} ({k['target_low']}-{k['target_high']}), n={k['n_analysts']}, upside {k['upside_pct']}%")
    if view["pack_answers"]:
        L.append("-- pack answers: " + "; ".join(f"{a.get('pack_date', a.get('doc_id', ''))} {a.get('stance', '')}" for a in view["pack_answers"][:5]))
    return "\n".join(L)
