"""Annual reports (laporan tahunan): what management says it will do, next to what the numbers say it did.

IDX lists them under the same endpoint as the financial statements with ``reportType=ar`` (from FY2019). This module
discovers them per fiscal year into ``idx.financial_report`` (report_type 'ar'), downloads the main PDF for chosen
codes (the attachment with the most pages; the others are cover letters and the sustainability report), extracts the
pages that carry the plan (business prospects, next-year projection/targets, strategy, work plan / capex, risks,
dividend policy) into ``idx.annual_excerpt``, and renders them as a section of the thesis card, so the web card, the
phone card and the analysis pack all carry the company's own words.

Pure parts: ``find_sections`` (page texts -> section pages), ``clean_page``, ``render_excerpts``. Shell: the IDX
calls, PDF handling (pypdf), storage.
"""
from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg

from . import runlog
from .client import IdxClient, IdxFetchError
from .jobs.fin import PERIOD_LABEL, _ts, fin_dir

logger = logging.getLogger(__name__)
JOB = "idx.annual"
PAGE = 100
MAX_CHARS = 6000

# section key -> (label, heading patterns). A heading is a SHORT line (see HEADING_MAX) that starts with one of these,
# matched case-insensitively: reports title these sections in upper case, title case or English, and the same words in
# running text sit on long lines, which do not count.
SECTIONS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("proyeksi", "Proyeksi dan target tahun depan",
     (r"proyeksi (kinerja|perusahaan|usaha|tahun|20\d\d)", r"target(,)? realisasi dan proyeksi", r"target (tahun )?20\d\d", r"rkap 20\d\d",
      r"(company )?(performance )?projection(s)? (for )?20\d\d", r"20\d\d (targets?|projection)", r"pandangan 20\d\d", r"20\d\d outlook", r"outlook 20\d\d")),
    ("prospek", "Prospek usaha",
     (r"prospek (usaha|bisnis|perusahaan|perseroan|industri|ke depan|20\d\d)", r"business (prospects?|outlook)", r"prospek dan (strategi|tantangan)",
      r"prospects? (for|in) 20\d\d", r"tinjauan prospek")),
    ("strategi", "Strategi",
     (r"strategi (perusahaan|usaha|bisnis|korporat|perseroan|pengembangan|tahun 20\d\d|20\d\d|dan kebijakan|ke depan)", r"fokus strategi",
      r"(business|corporate|company) strateg(y|ies)", r"arah(an)? (strategis|masa depan|ke depan)", r"inisiatif strategis", r"strategic (initiatives|direction|priorities)")),
    ("rencana", "Rencana kerja dan belanja modal",
     (r"rencana (kerja|bisnis|strategis|pengembangan|investasi|usaha|20\d\d|tahun 20\d\d)", r"belanja modal", r"capital expenditures?",
      r"(work|business) plan (for )?20\d\d", r"rencana dan (target|strategi)")),
    ("risiko", "Risiko usaha",
     (r"faktor risiko", r"risiko (usaha|utama|bisnis|yang dihadapi)", r"risk factors", r"(business|key|principal) risks", r"peluang dan risiko", r"opportunities and risks")),
    ("dividen", "Kebijakan dividen",
     (r"kebijakan dividen", r"dividend policy")),
)
HEADING_MAX = 60
SMALL_WORDS = {"dan", "and", "of", "for", "the", "atas", "untuk", "di", "ke", "&", "-", "serta", "tahun", "year", "in", "on", "to", "at", "yang", "dengan"}


def looks_like_heading(s: str) -> bool:
    """Pure. Upper case, or title case with the usual small words in lower case; a wrapped sentence fragment is neither."""
    words = [w for w in re.split(r"[\s,;:()\[\]\"'“”/|]+", s) if w and any(ch.isalpha() for ch in w)]
    if not words:
        return False
    if all(w.upper() == w for w in words):
        return True
    return all(w[0].isupper() or w.lower() in SMALL_WORDS for w in words)
ORDER = [s[0] for s in SECTIONS]
LABELS = {s[0]: s[1] for s in SECTIONS}
_HEADER_LINE = re.compile(r"^\s*(\d{1,4}|20\d\d Annual Report|Laporan Tahunan 20\d\d|PT [A-Za-z .]+Tbk\.?|[A-Za-z ]{0,40}Tbk)\s*$")


def annual_dir() -> Path:
    return fin_dir().parent / "annual"


# ---------------------------------------------------------------------------
# pure
# ---------------------------------------------------------------------------


def clean_page(text: str) -> str:
    """Collapse whitespace and drop the running headers, folios and single-glyph lines a PDF page carries."""
    out = []
    for line in text.splitlines():
        s = re.sub(r"[ \t]+", " ", line).strip()
        if not s or len(s) <= 2 or _HEADER_LINE.match(s):
            continue
        out.append(s)
    return re.sub(r"\n{2,}", "\n", "\n".join(out))


def heading_lines(text: str) -> list[tuple[str, int]]:
    """Pure. (section, line index) for every heading on a page: a short line, in heading case, beginning with one of
    the section's patterns."""
    found: list[tuple[str, int]] = []
    seen: set[str] = set()
    compiled = [(key, [re.compile(p, re.IGNORECASE) for p in pats]) for key, _, pats in SECTIONS]
    for i, line in enumerate(text.splitlines()):
        s = re.sub(r"[ \t]+", " ", line).strip(" :.-\u2013\u2014|")
        if not 4 <= len(s) <= HEADING_MAX or not looks_like_heading(s):
            continue
        for key, pats in compiled:
            if key in seen:
                continue
            if any((m := p.search(s)) and m.start() <= 3 for p in pats):
                found.append((key, i))
                seen.add(key)
    return found


def heading_sections(text: str) -> list[str]:
    return [k for k, _ in heading_lines(text)]


def find_sections(pages: list[str], max_pages: int = 2) -> dict[str, tuple[int, str]]:
    """Pure. Page texts (1-based order) -> {section: (first page number, cleaned text of that page and the next)}.
    The first fifth of the report (contents, highlights, profile) and pages that look like a table of contents (four
    or more different section headings) are skipped; the first later page carrying a heading wins."""
    n = len(pages)
    start = max(1, n // 5)
    hits: dict[str, tuple[int, str]] = {}
    for i in range(start, n):
        matched = heading_lines(pages[i] or "")
        if len(matched) >= 4:
            continue                                                      # a contents page
        for key, line_no in matched:
            if key in hits:
                continue
            first = "\n".join((pages[i] or "").splitlines()[line_no:])       # from the heading, not the top of the page
            text = "\n".join(clean_page(t) for t in [first, *[(pages[j] or "") for j in range(i + 1, min(n, i + max_pages))]])
            if len(text) < 300:
                continue                                                  # a mention, not a section
            hits[key] = (i + 1, text[:MAX_CHARS])
    return hits


def render_excerpts(code: str, fiscal_year: int, excerpts: dict[str, tuple[int, str]], per_section: int = 1500) -> str:
    """Pure. The card section: the company's plan in its own words, trimmed, with page references."""
    if not excerpts:
        return ""
    o = [f"## Rencana perusahaan — Laporan Tahunan {fiscal_year}", "",
         "Kutipan bagian yang membahas rencana, dari laporan tahunan yang diterbitkan emiten di IDX (bilingual, dipotong). "
         "Kata-kata manajemen, bukan penilaian desk.", ""]
    for key in ORDER:
        if key not in excerpts:
            continue
        page, text = excerpts[key]
        body = text[:per_section].rstrip()
        if len(text) > per_section:
            body += " …"
        o += [f"**{LABELS[key]}** (hal. {page})", "", body, ""]
    return "\n".join(o)


# ---------------------------------------------------------------------------
# shell
# ---------------------------------------------------------------------------


def discover(conn: psycopg.Connection, client: IdxClient, year: int) -> runlog.RunResult:
    """Bulk listing of annual reports for one fiscal year -> idx.financial_report (report_type 'ar', period TAHUNAN)."""
    r = runlog.RunResult(JOB + ":discover", f"{year}")
    run_id = runlog.start(conn, JOB + ":discover", r.run_key)
    try:
        page_no, total, rows = 1, None, []
        while True:
            res = client.financial_report(year, "audit", "", index_from=page_no, page_size=PAGE, report_type="ar")
            payload = res.payload if isinstance(res.payload, dict) else {}
            total = payload.get("ResultCount") if total is None else total
            page = payload.get("Results") or []
            rows.extend(page)
            page_no += 1
            if not page or len(rows) >= (total or 0):
                break
        r.rows_in = len(rows)
        with conn.cursor() as cur:
            for x in rows:
                atts = [{"name": a.get("File_Name"), "path": a.get("File_Path"), "type": a.get("File_Type"), "modified": a.get("File_Modified")}
                        for a in (x.get("Attachments") or []) if (a.get("File_Name") or "").lower().endswith(".pdf")]
                if not atts:
                    continue
                pub = _ts(max((a["modified"] for a in atts if a.get("modified")), default=None)) or datetime.now(UTC)
                cur.execute("""INSERT INTO idx.financial_report (code, fiscal_year, period, report_type, published_at, attachments, parse_status)
                               VALUES (%s, %s, %s, 'ar', %s, %s, 'pending')
                               ON CONFLICT (code, fiscal_year, period, report_type) DO UPDATE SET attachments = EXCLUDED.attachments,
                                   published_at = LEAST(idx.financial_report.published_at, EXCLUDED.published_at)""",
                            (x.get("KodeEmiten"), int(x.get("Report_Year") or year), PERIOD_LABEL["audit"], pub, psycopg.types.json.Jsonb(atts)))
                r.rows_out += 1
        conn.commit()
    except Exception as e:
        conn.rollback()
        r.status, r.error = "failed", f"{type(e).__name__}: {e}"[:500]
        logger.exception("idx annual discover %s failed", year)
    runlog.finish(conn, run_id, r)
    return r


def _pending(conn: psycopg.Connection, codes: list[str] | None, years: list[int] | None, statuses: tuple[str, ...]) -> list[dict[str, Any]]:
    q = "SELECT id, code, fiscal_year, attachments, parse_status FROM idx.financial_report WHERE report_type = 'ar' AND parse_status = ANY(%s)"
    params: list[Any] = [list(statuses)]
    if codes:
        q += " AND code = ANY(%s)"
        params.append([c.upper() for c in codes])
    if years:
        q += " AND fiscal_year = ANY(%s)"
        params.append(years)
    q += " ORDER BY fiscal_year DESC, code"
    with conn.cursor() as cur:
        cur.execute(q, params)
        rows = cur.fetchall()
    cols = ["id", "code", "fiscal_year", "attachments", "parse_status"]
    return [r if isinstance(r, dict) else dict(zip(cols, r, strict=True)) for r in rows]


def _set_status(conn: psycopg.Connection, report_id: int, status: str) -> None:
    with conn.cursor() as cur:
        cur.execute("UPDATE idx.financial_report SET parse_status = %s, parsed_at = now() WHERE id = %s", (status, report_id))
    conn.commit()


def pdf_path(code: str, year: int) -> Path:
    return annual_dir() / code.upper() / f"{code.upper()}_{year}.pdf"


def _page_count(path: Path) -> int:
    from pypdf import PdfReader
    try:
        return len(PdfReader(str(path)).pages)
    except Exception:
        return 0


def download(conn: psycopg.Connection, client: IdxClient, *, codes: list[str] | None = None, years: list[int] | None = None,
             limit: int | None = None) -> runlog.RunResult:
    """Fetch the annual-report PDFs of pending listings; keep the one with the most pages as the report."""
    r = runlog.RunResult(JOB + ":download", ",".join((codes or [])[:3]) or "all")
    run_id = runlog.start(conn, JOB + ":download", r.run_key)
    todo = _pending(conn, codes, years, ("pending",))
    if limit:
        todo = todo[:limit]
    r.rows_in = len(todo)
    for rep in todo:
        cands = [a for a in (rep["attachments"] or []) if "annualreport" in (a.get("name") or "").lower().replace(" ", "") or "laporantahunan" in (a.get("name") or "").lower().replace(" ", "")]
        if not cands:
            cands = [a for a in (rep["attachments"] or []) if (a.get("name") or "").lower().endswith(".pdf")]
        if not cands:
            _set_status(conn, rep["id"], "no_workbook")
            continue
        dst = pdf_path(rep["code"], rep["fiscal_year"])
        dst.parent.mkdir(parents=True, exist_ok=True)
        best, best_pages = None, -1
        for a in cands:
            try:
                body = client.download(a["path"])
            except IdxFetchError as e:
                r.warn(f"{rep['code']} {rep['fiscal_year']} {a.get('name')}: {e}")
                continue
            tmp = dst.with_suffix(f".{abs(hash(a['path'])) % 10**6}.part")
            tmp.write_bytes(body)
            pages = _page_count(tmp)
            if pages > best_pages:
                if best is not None:
                    best.unlink(missing_ok=True)
                best, best_pages = tmp, pages
            else:
                tmp.unlink(missing_ok=True)
        if best is None or best_pages < 20:
            if best is not None:
                best.unlink(missing_ok=True)
            _set_status(conn, rep["id"], "download_failed")
            continue
        best.replace(dst)
        _set_status(conn, rep["id"], "downloaded")
        r.rows_out += 1
        logger.info("idx annual %s %s: %d pages", rep["code"], rep["fiscal_year"], best_pages)
    if r.warnings and not r.rows_out:
        r.status = "failed" if todo else "ok"
    elif r.warnings:
        r.status = "partial"
    runlog.finish(conn, run_id, r)
    return r


def extract(conn: psycopg.Connection, *, codes: list[str] | None = None, years: list[int] | None = None, reparse: bool = False) -> runlog.RunResult:
    """Downloaded PDFs -> idx.annual_excerpt (one row per section found)."""
    from pypdf import PdfReader
    r = runlog.RunResult(JOB + ":extract", ",".join((codes or [])[:3]) or "all")
    run_id = runlog.start(conn, JOB + ":extract", r.run_key)
    todo = _pending(conn, codes, years, ("downloaded", "parsed") if reparse else ("downloaded",))
    r.rows_in = len(todo)
    for rep in todo:
        path = pdf_path(rep["code"], rep["fiscal_year"])
        if not path.exists():
            _set_status(conn, rep["id"], "pending")
            continue
        try:
            reader = PdfReader(str(path))
            pages = []
            for p in reader.pages:
                try:
                    pages.append(p.extract_text() or "")
                except Exception:
                    pages.append("")
            found = find_sections(pages)
        except Exception as e:
            r.warn(f"{rep['code']} {rep['fiscal_year']}: {type(e).__name__}: {str(e)[:100]}")
            _set_status(conn, rep["id"], "failed")
            continue
        with conn.cursor() as cur:
            cur.execute("DELETE FROM idx.annual_excerpt WHERE report_id = %s", (rep["id"],))
            for key, (page, text) in found.items():
                cur.execute("INSERT INTO idx.annual_excerpt (report_id, code, fiscal_year, section, page, text) VALUES (%s, %s, %s, %s, %s, %s)",
                            (rep["id"], rep["code"], rep["fiscal_year"], key, page, text))
        conn.commit()
        _set_status(conn, rep["id"], "parsed")
        r.rows_out += len(found)
        r.detail[f"{rep['code']}:{rep['fiscal_year']}"] = sorted(found)
    if r.warnings:
        r.status = "partial"
    runlog.finish(conn, run_id, r)
    return r


def latest_excerpts(conn: psycopg.Connection, code: str) -> tuple[int | None, dict[str, tuple[int, str]]]:
    with conn.cursor() as cur:
        cur.execute("""SELECT fiscal_year, section, page, text FROM idx.annual_excerpt WHERE code = %s
                       AND fiscal_year = (SELECT max(fiscal_year) FROM idx.annual_excerpt WHERE code = %s) ORDER BY section""", (code.upper(), code.upper()))
        rows = cur.fetchall()
    if not rows:
        return None, {}
    out = {}
    year = None
    for row in rows:
        d = row if isinstance(row, dict) else dict(zip(["fiscal_year", "section", "page", "text"], row, strict=True))
        year = d["fiscal_year"]
        out[d["section"]] = (d["page"], d["text"])
    return year, out


def render(conn: psycopg.Connection, code: str) -> str:
    year, ex = latest_excerpts(conn, code)
    return render_excerpts(code, year, ex) if year else ""


def status(conn: psycopg.Connection) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute("""SELECT fiscal_year, parse_status, count(*) AS n FROM idx.financial_report WHERE report_type = 'ar'
                       GROUP BY 1, 2 ORDER BY 1 DESC, 2""")
        rows = cur.fetchall()
    return [r if isinstance(r, dict) else dict(zip(["fiscal_year", "parse_status", "n"], r, strict=True)) for r in rows]
