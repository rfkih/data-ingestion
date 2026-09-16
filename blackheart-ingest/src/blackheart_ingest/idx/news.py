"""News collection: Indonesian financial press RSS feeds into ``idx.news_article`` (which existed empty), tagged with the
listed companies each item mentions (ticker in the text, or the company's short name from ``idx.company_alias`` /
``idx.listing``). Collection only: no scoring here. The point is to start the clock on a history the desk never had, so
"bad news" can be measured one day instead of assumed.

Feeds are public RSS/Atom endpoints of the outlets; one fetch each, a few times a day; titles and summaries only (no
article scraping).
"""
from __future__ import annotations

import hashlib
import logging
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import psycopg

from . import runlog

logger = logging.getLogger(__name__)
JOB = "idx.news"
FEEDS: tuple[tuple[str, str], ...] = (
    ("kontan-investasi", "https://investasi.kontan.co.id/rss"),
    ("kontan-keuangan", "https://keuangan.kontan.co.id/rss"),
    ("bisnis-market", "https://www.bisnis.com/rss/market"),
    ("bisnis-finansial", "https://www.bisnis.com/rss/finansial"),
    ("cnbc-market", "https://www.cnbcindonesia.com/market/rss"),
    ("antara-ekonomi", "https://www.antaranews.com/rss/ekonomi.xml"),
    ("idxchannel-market", "https://www.idxchannel.com/rss/market"),
)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) blackheart-desk/1.0 (+news collection, titles only)"
TICKER = re.compile(r"\b([A-Z]{4})\b")


def parse_feed(xml_bytes: bytes) -> list[dict[str, Any]]:
    """Pure. RSS 2.0 or Atom -> [{url, title, summary, published_at}]."""
    out: list[dict[str, Any]] = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return out
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    items = root.findall(".//item")
    if items:
        for it in items:
            link = (it.findtext("link") or "").strip()
            title = (it.findtext("title") or "").strip()
            desc = re.sub(r"<[^>]+>", " ", it.findtext("description") or "").strip()
            pub = it.findtext("pubDate")
            try:
                when = parsedate_to_datetime(pub) if pub else None
            except (TypeError, ValueError):
                when = None
            if link and title:
                out.append({"url": link, "title": title, "summary": desc[:2000], "published_at": when})
        return out
    for e in root.findall(".//atom:entry", ns):
        link_el = e.find("atom:link", ns)
        link = (link_el.get("href") if link_el is not None else "") or ""
        title = (e.findtext("atom:title", default="", namespaces=ns) or "").strip()
        desc = re.sub(r"<[^>]+>", " ", e.findtext("atom:summary", default="", namespaces=ns) or "").strip()
        pub = e.findtext("atom:published", default="", namespaces=ns) or e.findtext("atom:updated", default="", namespaces=ns)
        try:
            when = datetime.fromisoformat(pub.replace("Z", "+00:00")) if pub else None
        except ValueError:
            when = None
        if link and title:
            out.append({"url": link, "title": title, "summary": desc[:2000], "published_at": when})
    return out


def tag_codes(text: str, aliases: dict[str, str], tickers: set[str]) -> list[str]:
    """Pure. Tickers written in the text (BBRI) or company short names (Bank Rakyat Indonesia) -> sorted codes."""
    found = {m for m in TICKER.findall(text) if m in tickers}
    low = text.lower()
    for name, code in aliases.items():
        if len(name) >= 5 and name in low:
            found.add(code)
    return sorted(found)


def load_aliases(conn: psycopg.Connection) -> tuple[dict[str, str], set[str]]:
    aliases: dict[str, str] = {}
    tickers: set[str] = set()
    with conn.cursor() as cur:
        cur.execute("SELECT code, name FROM idx.listing WHERE status = 'ACTIVE'")
        for row in cur.fetchall():
            code, name = (row["code"], row["name"]) if isinstance(row, dict) else row
            tickers.add(code)
            if name:
                short = re.sub(r"\b(pt|tbk|persero|\(persero\)|tbk\.)\b", " ", name.lower())
                short = re.sub(r"[^a-z0-9 ]+", " ", short)
                short = re.sub(r"\s+", " ", short).strip()
                if len(short) >= 5:
                    aliases[short] = code
        try:
            cur.execute("SELECT alias, code FROM idx.company_alias")
            for row in cur.fetchall():
                alias, code = (row["alias"], row["code"]) if isinstance(row, dict) else row
                aliases[alias.lower()] = code
        except psycopg.Error:
            conn.rollback()
    return aliases, tickers


def fetch(url: str, timeout: float = 30.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9, */*;q=0.5"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def run(conn: psycopg.Connection) -> runlog.RunResult:
    r = runlog.RunResult(JOB, datetime.now(UTC).strftime("%Y-%m-%dT%H:%M"))
    run_id = runlog.start(conn, JOB, r.run_key)
    aliases, tickers = load_aliases(conn)
    now = datetime.now(UTC)
    new = 0
    failed = []
    for source, url in FEEDS:
        try:
            items = parse_feed(fetch(url))
        except Exception as e:
            failed.append(source)
            r.warn(f"{source}: {type(e).__name__}: {str(e)[:80]}")
            continue
        r.rows_in += len(items)
        with conn.cursor() as cur:
            for it in items:
                text = f"{it['title']} {it['summary']}"
                codes = tag_codes(text, aliases, tickers)
                h = hashlib.sha1(text.encode("utf-8", "ignore")).hexdigest()
                cur.execute("""INSERT INTO idx.news_article (source, url, published_at, fetched_at, title, body, lang, text_hash, codes)
                               VALUES (%s, %s, %s, %s, %s, %s, 'id', %s, %s) ON CONFLICT (url) DO NOTHING""",
                            (source, it["url"], it["published_at"], now, it["title"], it["summary"], h, codes))
                new += cur.rowcount
        conn.commit()
    r.rows_out = new
    r.detail = {"feeds": len(FEEDS), "failed": failed}
    if failed and len(failed) == len(FEEDS):
        r.status, r.error = "failed", "every feed failed"
    elif failed:
        r.status = "partial"
    runlog.finish(conn, run_id, r)
    return r


def recent(conn: psycopg.Connection, code: str | None = None, limit: int = 30) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute("""SELECT source, url, published_at, title, codes FROM idx.news_article
                       WHERE (%s::text IS NULL OR %s = ANY(codes)) ORDER BY published_at DESC NULLS LAST LIMIT %s""", (code, code, limit))
        rows = cur.fetchall()
    cols = ["source", "url", "published_at", "title", "codes"]
    return [r if isinstance(r, dict) else dict(zip(cols, r, strict=True)) for r in rows]
