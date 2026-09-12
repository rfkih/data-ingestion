"""``announce`` job — Keterbukaan Informasi (per-emiten disclosures) -> ``idx.announcement`` + ``idx.event``.

Metadata only (title, form id, timestamps, attachment links); no PDF text. ``kind`` is a rule
table on the title — IDX titles are formulaic. The archive behind the endpoint starts 2023-07-03.
The exchange's own UMA notice is not in the per-emiten feed; the emiten's mandatory reply
("Penjelasan atas Permintaan Penjelasan Bursa") is, and is classified ``exchange_query``.
"""
from __future__ import annotations

import logging
import re
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import psycopg

from .. import bronze, runlog
from ..client import IdxClient

logger = logging.getLogger(__name__)
JOB = "announce"
WIB = ZoneInfo("Asia/Jakarta")
ARCHIVE_START = date(2023, 7, 1)
PAGE = 1000

# ordered: first match wins. (kind, regex on lower-cased title)
RULES: list[tuple[str, re.Pattern[str]]] = [(k, re.compile(p)) for k, p in [
    ("ad_proof",           r"bukti iklan"),
    ("registry",           r"registrasi pemegang efek"),
    ("exploration",        r"aktivitas eksplorasi"),
    ("ipo_proceeds",       r"penggunaan dana hasil penawaran umum"),
    ("financial_report",   r"laporan keuangan|laporan tahunan|laporan keberlanjutan"),
    ("exchange_query",     r"permintaan penjelasan bursa|volatilitas transaksi|unusual market|\buma\b"),
    ("suspension",         r"penghentian sementara|suspensi|pembukaan kembali"),
    ("dividend",           r"dividen"),
    ("rights",             r"hmetd|rights issue|penambahan modal|pmthmetd"),
    ("buyback",            r"pembelian kembali|buyback|buy back|pengalihan kembali saham"),
    ("ownership_change",   r"kepemilikan atau setiap perubahan kepemilikan|perubahan kepemilikan saham|laporan kepemilikan saham"),
    ("control_change",     r"pengendali"),
    ("listing_change",     r"pencatatan saham|pencatatan efek|pra pencatatan"),
    ("corporate_action",   r"aksi korporasi|stock split|pemecahan|reverse|penggabungan|merger|akuisisi|pengambilalihan|spin[- ]?off|perubahan kegiatan usaha"),
    ("ownership_change",   r"struktur pemegang saham"),
    ("auditor",            r"akuntan publik"),
    ("legal",              r"perkara hukum|gugatan|pkpu|pailit"),
    ("material_info",      r"informasi atau fakta material|keterbukaan informasi material|^informasi perusahaan"),
    ("media_clarification", r"pemberitaan media"),
    ("public_expose",      r"public expose"),
    ("press_release",      r"press release|siaran pers|kinerja"),
    ("rups",               r"rapat umum|rups"),
    ("management",         r"direksi|komisaris|corporate secretary|sekretaris perusahaan|internal audit|komite audit|pengurus"),
    ("affiliated_tx",      r"transaksi afiliasi|benturan kepentingan|transaksi material"),
    ("rating",             r"pemeringkatan|peringkat"),
    ("debt",               r"obligasi|sukuk|mtn|surat utang|pelunasan efek"),
    ("financing",          r"fasilitas kredit|pinjaman|kredit"),
    ("prospectus",         r"prospektus"),
    ("articles",           r"anggaran dasar"),
    ("esg",                r"\besg\b"),
]]


def classify(title: str | None) -> str:
    t = (title or "").lower()
    for kind, rx in RULES:
        if rx.search(t):
            return kind
    return "other"


def _ts(s: str | None) -> datetime | None:
    """IDX timestamps are WIB wall-clock without an offset."""
    if not s:
        return None
    return datetime.fromisoformat(s[:19]).replace(tzinfo=WIB).astimezone(UTC)


def rows_from(payload_rows: list[dict[str, Any]], fetched_at: datetime, bronze_id: int | None) -> list[dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for x in payload_rows:
        p = x.get("pengumuman") or {}
        id2 = p.get("Id2")
        pub = _ts(p.get("TglPengumuman"))
        if not id2 or pub is None:
            continue
        title = (p.get("JudulPengumuman") or "").strip()
        out[id2] = {
            "id2": id2, "code": (p.get("Kode_Emiten") or "").strip().upper() or None,
            "published_at": pub, "title": title, "form_id": (p.get("Form_Id") or "").strip() or None,
            "perihal": (p.get("PerihalPengumuman") or "").strip() or None,
            "jenis": (p.get("JenisPengumuman") or "").strip() or None,
            "kind": classify(title),
            "attachments": psycopg.types.json.Jsonb(x.get("attachments") or []),
            "bronze_id": bronze_id, "fetched_at": fetched_at,
        }
    return list(out.values())


_UPSERT = """
INSERT INTO idx.announcement (id2, code, published_at, title, form_id, perihal, jenis, kind, attachments, bronze_id, fetched_at)
VALUES (%(id2)s, %(code)s, %(published_at)s, %(title)s, %(form_id)s, %(perihal)s, %(jenis)s, %(kind)s, %(attachments)s,
        %(bronze_id)s, %(fetched_at)s)
ON CONFLICT (id2) DO UPDATE SET
    code = EXCLUDED.code, published_at = EXCLUDED.published_at, title = EXCLUDED.title, form_id = EXCLUDED.form_id,
    perihal = EXCLUDED.perihal, jenis = EXCLUDED.jenis, kind = EXCLUDED.kind, attachments = EXCLUDED.attachments,
    bronze_id = EXCLUDED.bronze_id, fetched_at = EXCLUDED.fetched_at
"""
_EVENT = """
INSERT INTO idx.event (code, event_date, published_at, kind, source, ref_id, payload)
VALUES (%(code)s, %(event_date)s, %(published_at)s, %(kind)s, 'announcement', %(id2)s, %(payload)s)
ON CONFLICT (source, ref_id, kind, code) DO NOTHING
"""
EVENT_KINDS = {"dividend", "rights", "buyback", "ownership_change", "control_change", "corporate_action",
               "material_info", "exchange_query", "media_clarification", "public_expose", "management",
               "affiliated_tx", "suspension", "legal", "press_release"}


def reclassify(conn: psycopg.Connection) -> dict[str, int]:
    """Recompute ``kind`` from stored titles and rebuild announcement-sourced events (rule changes, no refetch)."""
    with conn.cursor() as cur:
        cur.execute("SELECT id2, code, title, published_at, form_id FROM idx.announcement")
        rows = cur.fetchall()
        updates, events = [], []
        for r in rows:
            id2, code, title, pub, form_id = (r if isinstance(r, tuple) else (r["id2"], r["code"], r["title"], r["published_at"], r["form_id"]))
            kind = classify(title)
            updates.append({"kind": kind, "id2": id2})
            if code and kind in EVENT_KINDS:
                events.append({"code": code, "event_date": pub.astimezone(WIB).date(), "published_at": pub, "kind": kind,
                               "id2": id2, "payload": psycopg.types.json.Jsonb({"title": title, "form_id": form_id})})
        cur.executemany("UPDATE idx.announcement SET kind = %(kind)s WHERE id2 = %(id2)s AND kind IS DISTINCT FROM %(kind)s", updates)
        cur.execute("DELETE FROM idx.event WHERE source = 'announcement'")
        cur.executemany(_EVENT, events)
    conn.commit()
    counts: dict[str, int] = {}
    for u in updates:
        counts[u["kind"]] = counts.get(u["kind"], 0) + 1
    return counts


def process(conn: psycopg.Connection, rows: list[dict[str, Any]], fetched_at: datetime, bronze_id: int | None,
            r: runlog.RunResult) -> None:
    anns = rows_from(rows, fetched_at, bronze_id)
    r.rows_in = len(rows)
    if not anns:
        r.detail["empty"] = True
        return
    events = []
    for a in anns:
        if a["code"] and a["kind"] in EVENT_KINDS:
            # event_date = the Jakarta calendar day it was published (PIT: usable from published_at)
            events.append({"code": a["code"], "event_date": a["published_at"].astimezone(WIB).date(),
                           "published_at": a["published_at"], "kind": a["kind"], "id2": a["id2"],
                           "payload": psycopg.types.json.Jsonb({"title": a["title"], "form_id": a["form_id"]})})
    with conn.cursor() as cur:
        cur.executemany(_UPSERT, anns)
        if events:
            cur.executemany(_EVENT, events)
    conn.commit()
    r.rows_out = len(anns)
    r.detail["events"] = len(events)
    kinds: dict[str, int] = {}
    for a in anns:
        kinds[a["kind"]] = kinds.get(a["kind"], 0) + 1
    r.detail["kinds"] = kinds


def run(conn: psycopg.Connection, client: IdxClient, code: str, date_from: date, date_to: date) -> runlog.RunResult:
    r = runlog.RunResult(JOB, f"{code}:{date_from}:{date_to}")
    run_id = runlog.start(conn, JOB, r.run_key)
    try:
        res = client.announcement(code, date_from, date_to, index_from=0, page_size=PAGE)
        drift = bronze.drift(conn, res)
        bid = bronze.write(conn, res)
        if drift:
            r.warn(f"payload fingerprint drift: {drift[0]} -> {drift[1]}")
        rows = res.rows()
        total = (res.payload or {}).get("ResultCount") if isinstance(res.payload, dict) else None
        if total and total > len(rows):
            r.warn(f"ResultCount {total} > returned {len(rows)}: window too wide, split the date range")
        process(conn, rows, res.fetched_at, bid, r)
    except Exception as e:
        conn.rollback()
        r.status = "failed"
        r.error = f"{type(e).__name__}: {e}"[:500]
        logger.exception("idx announce %s failed", code)
    runlog.finish(conn, run_id, r)
    return r
