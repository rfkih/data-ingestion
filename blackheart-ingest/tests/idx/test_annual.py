"""Annual reports: the section finder and the card rendering (pure)."""
from __future__ import annotations

from blackheart_ingest.idx import annual as AN


def test_heading_lines_are_short_and_start_with_the_pattern_in_any_case() -> None:
    assert AN.heading_sections("Prospek Usaha\nBusiness Outlook\nteks panjang tentang prospek usaha yang bukan judul karena kalimatnya panjang sekali") == ["prospek"]
    assert AN.heading_sections("2026 OUTLOOK\nKebijakan Dividen\nRencana 2026") == ["proyeksi", "dividen", "rencana"]
    assert AN.heading_sections("Sumber: IMF, World Economic Outlook Database") == []
    assert AN.heading_sections("Outlook 2026\u201d pada tanggal 6 Agustus 2025 dan") == []        # a wrapped sentence, not a heading
    assert AN.looks_like_heading("Target, Realisasi dan Proyeksi") and AN.looks_like_heading("2026 OUTLOOK")
    assert not AN.looks_like_heading("prospek usaha yang dibahas di sini")


def test_find_sections_skips_the_contents_and_the_front_and_takes_uppercase_headings() -> None:
    contents = "DAFTAR ISI\nPROSPEK USAHA 12\nSTRATEGI PERUSAHAAN 20\nFAKTOR RISIKO 30\nKEBIJAKAN DIVIDEN 40\n"
    front = ["cover"] * 10 + [contents]
    body = [""] * 20
    body[3] = "2025 Annual Report\nPT Contoh Tbk\nBagian sebelumnya yang tidak relevan.\nPROSPEK USAHA TAHUN 2026\nPerusahaan memperkirakan permintaan tumbuh 5 %.\n241" + "\nkalimat tambahan tentang pasar domestik yang cukup panjang supaya bagian ini dihitung sebagai bagian." * 3
    body[4] = "Lanjutan prospek: fokus pada distribusi.\n"
    body[9] = "PROYEKSI KINERJA TAHUN 2026\nPendapatan Rp 13.559 miliar\nLaba bersih Rp 586 miliar" + "\nrincian proyeksi per segmen yang cukup panjang untuk dihitung sebagai bagian yang utuh." * 4
    body[15] = "Sebagaimana disampaikan, kebijakan dividen dibahas di sini di dalam kalimat panjang tanpa heading tersendiri."   # running text
    pages = front + body
    found = AN.find_sections(pages)
    assert set(found) == {"prospek", "proyeksi"}
    page, text = found["prospek"]
    assert page == 15 and "permintaan tumbuh 5 %" in text and "fokus pada distribusi" in text
    assert text.startswith("PROSPEK USAHA TAHUN 2026") and "tidak relevan" not in text      # the excerpt starts at the heading
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
