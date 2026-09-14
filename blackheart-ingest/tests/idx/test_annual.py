"""Annual reports: the section finder and the card rendering (pure)."""
from __future__ import annotations

from blackheart_ingest.idx import annual as AN


def test_find_sections_skips_the_contents_and_the_front_and_takes_uppercase_headings() -> None:
    contents = "DAFTAR ISI\nPROSPEK USAHA 12\nSTRATEGI PERUSAHAAN 20\nFAKTOR RISIKO 30\nKEBIJAKAN DIVIDEN 40\n"
    front = ["cover"] * 10 + [contents]
    body = [""] * 20
    body[3] = "2025 Annual Report\nPT Contoh Tbk\nPROSPEK USAHA TAHUN 2026\nPerusahaan memperkirakan permintaan tumbuh 5 %.\n241"
    body[4] = "Lanjutan prospek: fokus pada distribusi.\n"
    body[9] = "PROYEKSI KINERJA TAHUN 2026\nPendapatan Rp 13.559 miliar\nLaba bersih Rp 586 miliar"
    body[15] = "kebijakan dividen dibahas di sini tanpa heading"           # lower-case running text does not count
    pages = front + body
    found = AN.find_sections(pages)
    assert set(found) == {"prospek", "proyeksi"}
    page, text = found["prospek"]
    assert page == 15 and "permintaan tumbuh 5 %" in text and "fokus pada distribusi" in text
    assert "2025 Annual Report" not in text and "\n241" not in text                     # running header and folio dropped
    assert found["proyeksi"][0] == 21


def test_render_excerpts_trims_and_orders() -> None:
    md = AN.render_excerpts("ELSA", 2025, {"risiko": (300, "risiko " * 10), "proyeksi": (242, "x" * 2000)}, per_section=100)
    assert md.startswith("## Rencana perusahaan — Laporan Tahunan 2025")
    assert md.index("Proyeksi dan target") < md.index("Risiko usaha")
    assert "(hal. 242)" in md and "…" in md
    assert AN.render_excerpts("X", 2025, {}) == ""


def test_clean_page_drops_headers_and_short_lines() -> None:
    t = AN.clean_page("  2025 Annual Report \nPT Elnusa Tbk\n7\nIsi  yang   penting\n ab \nBaris kedua")
    assert t == "Isi yang penting\nBaris kedua"
