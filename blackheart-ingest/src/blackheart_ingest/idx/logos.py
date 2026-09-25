"""Company logos for every listed name (operator, 2026-09-25: "buat semua saham memiliki logo nya masing2 bisa di fetch dari
web nya stockbit saja").

Source: Stockbit's public CDN, ``https://assets.stockbit.com/logos/companies/{CODE}.png`` (no login; ~5-7 KB a PNG). Each is
downloaded ONCE into ``<data>/idx/logos/{CODE}.png`` and served by the app from there (``GET /idx/logo/{code}``), so a page
never waits on, or depends on, a third party. A name the CDN has no logo for is remembered as ``{CODE}.missing`` and not
asked again until a refresh. Gentle: two requests a second, stop on the first 403/429.
"""
from __future__ import annotations

import logging
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import tuple_row

from .bronze import bronze_dir

logger = logging.getLogger(__name__)

LOGO_URL = "https://assets.stockbit.com/logos/companies/{code}.png"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) blackheart-idx logos"
CODE_RE = re.compile(r"^[A-Z0-9]{1,8}$")
PNG = b"\x89PNG"
MAX_DENIED = 5                                   # this many 403s in a row = the CDN refusing us, not missing logos


def logo_dir() -> Path:
    return bronze_dir().parent / "logos"


def path_for(code: str) -> Path | None:
    """The stored PNG for a code, or None (never fetched, or the CDN has none)."""
    code = code.upper()
    if not CODE_RE.match(code):
        return None
    p = logo_dir() / f"{code}.png"
    return p if p.exists() else None


def listed_codes(conn: psycopg.Connection) -> list[str]:
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute("SELECT code FROM idx.listing WHERE status = 'ACTIVE' ORDER BY code")
        return [r[0] for r in cur.fetchall() if CODE_RE.match(str(r[0]))]


def _get(url: str, timeout: float = 20.0) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "image/png,image/*;q=0.8"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""


def fetch(codes: list[str], *, refresh: bool = False, rps: float = 2.0, getter=_get, sleep=time.sleep) -> dict[str, Any]:
    """Download the logos not yet on disk (all of them with ``refresh``). -> counts and the codes the CDN lacks."""
    d = logo_dir()
    d.mkdir(parents=True, exist_ok=True)
    out: dict[str, Any] = {"asked": 0, "saved": 0, "have": 0, "missing": [], "stopped": None}
    denied = 0                                   # consecutive 403s: the CDN answers 403 (not 404) for a logo it does not have,
    for code in codes:                           # so ONE 403 is a missing logo and a run of them is the CDN refusing us
        code = code.upper()
        png, miss = d / f"{code}.png", d / f"{code}.missing"
        if not refresh and (png.exists() or miss.exists()):
            out["have"] += 1
            continue
        status, body = getter(LOGO_URL.format(code=code))
        out["asked"] += 1
        if status == 429 or (status == 403 and denied >= MAX_DENIED - 1):
            out["stopped"] = f"HTTP {status} at {code} after {denied} refusals in a row - the CDN is pushing back; resume later"
            for c in out["missing"][-denied:] if status == 403 else []:     # those were probably refusals too: ask again next run
                (d / f"{c}.missing").unlink(missing_ok=True)
            break
        denied = denied + 1 if status == 403 else 0
        if status == 200 and body.startswith(PNG):
            png.write_bytes(body)
            miss.unlink(missing_ok=True)
            out["saved"] += 1
        else:
            miss.write_text(f"HTTP {status}\n", encoding="utf-8")
            out["missing"].append(code)
        sleep(1.0 / rps)
    logger.info("idx logos: asked %s saved %s have %s missing %s%s", out["asked"], out["saved"], out["have"], len(out["missing"]),
                f" STOPPED {out['stopped']}" if out["stopped"] else "")
    return out
