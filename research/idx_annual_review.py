#!/usr/bin/env python3
"""IDX — what management wrote for 2026, for every name in the quality pool (2026-09-14).

Reads the extracted annual-report sections (idx.annual_excerpt) and the full PDFs, pulls the concrete statements
out of them — 2026 targets (revenue, profit, growth, volumes), the macro assumptions the plan rests on (USD/IDR,
BI rate, GDP), capex and expansion, a change of president director — and lines them up against the first-half 2026
results and today's macro, so "did the plan survive contact with the year" is a column, not an impression.

Two passes per report:
  1. sentences in the plan sections (and any page mentioning "2026") that carry a number next to a plan word
     (target, proyeksi, diperkirakan, menargetkan, ditargetkan, RKAP, capex, belanja modal, ekspansi, asumsi ...)
  2. the macro assumptions: 'Rp1x.xxx' next to USD, 'BI Rate x,xx%', growth 'x,x%'
Output: research-scratch/idx-screen/annual_review_2025.md (one block per company) and .json.

READ-ONLY on the DB. INGEST_DB_DSN=... blackheart-ingest/.venv/Scripts/python research/idx_annual_review.py
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import UTC, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "blackheart-ingest", "src"))
import idx_value_quality as VQ  # noqa: E402
from blackheart_ingest.idx import annual as AN  # noqa: E402

OUT_MD = os.path.join(VQ.OUTDIR, "annual_review_2025.md")
OUT_JSON = os.path.join(VQ.OUTDIR, "annual_review_2025.json")
PLAN_WORDS = r"(target|menargetkan|ditargetkan|proyeksi|diproyeksikan|diperkirakan|memperkirakan|rencana|berencana|akan (membuka|menambah|membangun|meningkatkan|memperluas|mengembangkan)|" \
             r"rkap|capex|belanja modal|ekspansi|expansion|pembukaan|gerai baru|kapasitas|guidance|outlook|expect(s|ed)? to|plan(s|ned)? to|aim(s)? to)"
NUM = r"(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?\s*(?:%|persen|triliun|miliar|juta|ha|hektar|kl|ton|unit|gerai|sumur|mw|bopd|bscfd|x)?)"
YEAR_PAT = re.compile(r"\b2026\b")
MACRO_PATS = {
    "usdidr": re.compile(r"(?:usd/idr|us\$|usd|dolar|kurs|nilai tukar|exchange rate)[^.\n]{0,40}?rp\s?(1[5-9][.,]\d{3})", re.I),
    "bi_rate": re.compile(r"(?:bi[- ]?rate|bi 7[- ]?day|suku bunga acuan|7drr)[^.\n]{0,30}?(\d[,.]\d{1,2})\s?%", re.I),
    "gdp": re.compile(r"(?:pertumbuhan (?:ekonomi|pdb)|gdp growth|economic growth)[^.\n]{0,40}?(\d[,.]\d{1,2})\s?%", re.I),
}
SENTENCE_MAX = 320


def sentences(text: str) -> list[str]:
    t = re.sub(r"\s+", " ", text)
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z\d“\"(])", t) if s.strip()]


def plan_sentences(text: str) -> list[str]:
    out = []
    for s in sentences(text):
        if len(s) > SENTENCE_MAX or not YEAR_PAT.search(s):
            continue
        if re.search(PLAN_WORDS, s, re.I) and re.search(NUM, s):
            out.append(s)
    return out


def macro_assumptions(text: str) -> dict[str, str]:
    t = re.sub(r"\s+", " ", text)
    out = {}
    for k, p in MACRO_PATS.items():
        m = p.search(t)
        if m:
            out[k] = m.group(1)
    return out


def president_change(pages: list[str]) -> str | None:
    pat = re.compile(r"(diangkat|appointed)[^.\n]{0,80}(direktur utama|president director)[^.\n]{0,120}?(20\d\d)", re.I)
    for t in pages:
        m = pat.search(re.sub(r"\s+", " ", t))
        if m and m.group(3) in ("2025", "2026"):
            return m.group(0)[:200]
    return None


def review_one(conn, code: str) -> dict:
    year, ex = AN.latest_excerpts(conn, code)
    rec = {"code": code, "fiscal_year": year, "sections": sorted(ex), "plan": [], "macro": {}, "president_change": None}
    for key in AN.ORDER:
        if key in ex:
            for s in plan_sentences(ex[key][1]):
                if s not in rec["plan"]:
                    rec["plan"].append(s)
            rec["macro"].update({k: v for k, v in macro_assumptions(ex[key][1]).items() if k not in rec["macro"]})
    path = AN.pdf_path(code, year or 2025)
    if path.exists():
        from pypdf import PdfReader
        try:
            pages = []
            for p in PdfReader(str(path)).pages:
                try:
                    pages.append(p.extract_text() or "")
                except Exception:
                    pages.append("")
        except Exception:
            pages = []
        n = len(pages)
        hits = 0
        for i in range(n // 6, n):                                        # the plan lives in the middle of the report
            t = pages[i]
            if "2026" not in t:
                continue
            for s in plan_sentences(t):
                if s not in rec["plan"] and hits < 40:
                    rec["plan"].append(s)
                    hits += 1
            for k, v in macro_assumptions(t).items():
                rec["macro"].setdefault(k, v)
        rec["president_change"] = president_change(pages[: n // 2])
        rec["pages"] = n
    return rec


def h1(conn, code: str) -> dict:
    rows = VQ.frame(conn, """SELECT net_profit_yoy, revenue_yoy, roe, der, cfo, net_profit, period_end, months FROM idx.fundamental
                             WHERE code = %s ORDER BY published_at DESC LIMIT 1""", (code,),
                    ["net_profit_yoy", "revenue_yoy", "roe", "der", "cfo", "net_profit", "period_end", "months"])
    if rows.empty:
        return {}
    r = rows.iloc[0]
    return {"period": str(r["period_end"]), "months": int(r["months"]), "np_yoy": float(r["net_profit_yoy"]) if r["net_profit_yoy"] is not None else None,
            "rev_yoy": float(r["revenue_yoy"]) if r["revenue_yoy"] is not None else None, "roe": float(r["roe"]) if r["roe"] is not None else None}


def main():
    conn = VQ.connect()
    pool = json.load(open(os.path.join(VQ.OUTDIR, "ar_pool.json")))
    macro_now = {r["series"]: float(r["value"]) for r in VQ.frame(conn, """SELECT DISTINCT ON (series) series, value FROM idx.macro
                 WHERE series IN ('usdidr', 'bi_rate', 'id_gdp_annual') ORDER BY series, obs_date DESC""", (), ["series", "value"]).to_dict("records")}
    out = []
    md = [f"# What management wrote for 2026 — {len(pool)} names, FY2025 annual reports (read {datetime.now(UTC).date()})", "",
          f"Today: USD/IDR {macro_now.get('usdidr', 0):,.0f}, BI-Rate {macro_now.get('bi_rate', 0):.2f} %. A plan's assumptions are marked "
          "**broken** when the rupiah is more than 3 % weaker or the BI rate more than 50 bp higher than assumed.", ""]
    for code in pool:
        rec = review_one(conn, code)
        rec["h1"] = h1(conn, code)
        out.append(rec)
        flags = []
        m = rec["macro"]
        if "usdidr" in m:
            v = float(m["usdidr"].replace(".", "").replace(",", "."))
            if macro_now.get("usdidr", 0) > v * 1.03:
                flags.append(f"rupiah assumed {v:,.0f} (now {macro_now['usdidr']:,.0f}) **broken**")
        if "bi_rate" in m:
            v = float(m["bi_rate"].replace(",", "."))
            if macro_now.get("bi_rate", 0) > v + 0.5:
                flags.append(f"BI rate assumed {v:.2f} % (now {macro_now['bi_rate']:.2f} %) **broken**")
        h = rec["h1"]
        md.append(f"## {code} — FY{rec['fiscal_year']} ({rec.get('pages', 0)} pages; sections: {', '.join(rec['sections']) or 'none found'})")
        if h:
            pct = lambda v: "n/a" if v is None else f"{v:+.0%}"  # noqa: E731
            md.append(f"H1 2026: net profit {pct(h.get('np_yoy'))}, revenue {pct(h.get('rev_yoy'))}, ROE {'n/a' if h.get('roe') is None else f'{h['roe']:.1%}'}")
        if m:
            md.append("Assumptions: " + ", ".join(f"{k} {v}" for k, v in m.items()) + ("  →  " + "; ".join(flags) if flags else ""))
        if rec["president_change"]:
            md.append(f"Leadership: {rec['president_change']}")
        if rec["plan"]:
            md.append("Plan statements (2026, with numbers):")
            for s in rec["plan"][:14]:
                md.append(f"- {s}")
        else:
            md.append("No numeric 2026 statement found (report may state the plan without figures, or the text layer is thin).")
        md.append("")
        print(f"{code}: sections {len(rec['sections'])}, plan sentences {len(rec['plan'])}, macro {rec['macro']}, flags {flags}")
        sys.stdout.flush()
    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md))
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, default=str)
    print("->", OUT_MD)


if __name__ == "__main__":
    main()
