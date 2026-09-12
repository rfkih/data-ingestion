"""PIT rules for phase-1b features: a disclosure after the 16:00 WIB cut belongs to the next trading day."""
from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pandas as pd

from blackheart_ingest.idx import features as F
from blackheart_ingest.idx.jobs.announce import classify

WIB = ZoneInfo("Asia/Jakarta")
DAYS = pd.DatetimeIndex(pd.to_datetime(["2026-09-08", "2026-09-09", "2026-09-10", "2026-09-11", "2026-09-14"]))


def wib(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=WIB).astimezone(UTC)


def test_after_cut_moves_to_next_trading_day() -> None:
    assert F.event_effective_date(wib(2026, 9, 10, 16, 10), DAYS).isoformat() == "2026-09-11"
    assert F.event_effective_date(wib(2026, 9, 10, 15, 59), DAYS).isoformat() == "2026-09-10"
    assert F.event_effective_date(wib(2026, 9, 10, 16, 0), DAYS).isoformat() == "2026-09-10"


def test_weekend_publication_lands_on_monday() -> None:
    assert F.event_effective_date(wib(2026, 9, 12, 9, 0), DAYS).isoformat() == "2026-09-14"   # Saturday
    assert F.event_effective_date(wib(2026, 9, 11, 18, 30), DAYS).isoformat() == "2026-09-14"  # Friday after cut


def test_beyond_last_trading_day_is_none() -> None:
    assert F.event_effective_date(wib(2026, 9, 14, 17, 0), DAYS) is None


def test_cut_utc_is_0900z() -> None:
    from datetime import date
    assert F.cut_utc(date(2026, 9, 11)).isoformat() == "2026-09-11T09:00:00+00:00"


def test_title_rules_on_known_forms() -> None:
    cases = {
        "Penjelasan atas Permintaan Penjelasan Bursa": "exchange_query",
        "Penjelasan atas Volatilitas Transaksi": "exchange_query",
        "Pengumuman Bursa Pencatatan Awal Obligasi dan Sukuk": "debt",      # 'UMA' must not match inside 'Pengumuman'
        "Jadwal Dividen Tunai Interim Tahun Buku 2025": "dividend",
        "Keterbukaan Informasi terkait Aksi Korporasi - Dividen Tunai": "dividend",
        "Laporan Kepemilikan atau Setiap Perubahan Kepemilikan Saham Perusahaan Terbuka": "ownership_change",
        "Rencana Pembelian Kembali Saham": "buyback",
        "Laporan Bulanan Registrasi Pemegang Efek": "registry",
        "Penyampaian Bukti Iklan Jadwal Dividen": "ad_proof",
        "Ringkasan Risalah Rapat Umum Para Pemegang Saham Tahunan": "rups",
        "Penyampaian Laporan Keuangan Interim": "financial_report",
        "Perkara hukum terhadap Emiten": "legal",
    }
    for title, kind in cases.items():
        assert classify(title) == kind, (title, classify(title))
