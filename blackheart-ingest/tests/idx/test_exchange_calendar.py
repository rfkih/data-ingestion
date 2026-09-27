"""Exchange calendar (idx/exchange_calendar.py): parsing the exchange's holiday PDF text, trading-day arithmetic."""
from __future__ import annotations

import time
from datetime import date

from blackheart_ingest.idx import exchange_calendar as xc

# the layout pypdf gives for the exchange's "Kalender Libur Bursa Tahun 2026" (dates, weekdays and names as separate runs)
TEXT = """www.idx.co.id
Bulan Tanggal Hari Keterangan
Hari
Bursa
Januari 01-01-2026
16-01-2026
Kamis
Jumat
Tahun Baru 2026 Masehi
Isra Mikraj Nabi Muhammad SAW 20
Februari 16-02-2026
17-02-2026
Senin
Selasa
Cuti Bersama Tahun Baru Imlek 2577 Kongzili
Tahun Baru Imlek 2577 Kongzili 18
April 03-04-2026 Jumat Wafat Yesus Kristus 21
Juli  Tidak ada hari libur kecuali Sabtu dan Minggu 23
"""


def test_parse_dates_and_names() -> None:
    got = dict(xc.parse_calendar_text(TEXT))
    assert list(got) == [date(2026, 1, 1), date(2026, 1, 16), date(2026, 2, 16), date(2026, 2, 17), date(2026, 4, 3)]
    assert got[date(2026, 1, 1)] == "Tahun Baru 2026 Masehi"
    assert got[date(2026, 1, 16)] == "Isra Mikraj Nabi Muhammad SAW"                  # the trailing "20" trading-day count removed
    assert got[date(2026, 2, 17)] == "Tahun Baru Imlek 2577 Kongzili"
    assert got[date(2026, 4, 3)] == "Wafat Yesus Kristus"


def test_names_left_empty_when_they_do_not_pair() -> None:
    got = dict(xc.parse_calendar_text("Desember 24-12-2026\n25-12-2026\nKamis\nJumat\nCuti Bersama Natal\n"))
    assert got == {date(2026, 12, 24): None, date(2026, 12, 25): None}


def test_trading_day_arithmetic(monkeypatch) -> None:
    h = {date(2026, 12, 24), date(2026, 12, 25), date(2026, 12, 31), date(2027, 1, 1)}
    monkeypatch.setitem(xc._cache, "days", h)
    monkeypatch.setitem(xc._cache, "at", time.monotonic())
    assert xc.is_trading_day(date(2026, 12, 23)) and not xc.is_trading_day(date(2026, 12, 25)) and not xc.is_trading_day(date(2026, 12, 26))
    assert xc.next_trading_day(date(2026, 12, 23)) == date(2026, 12, 28)
    assert xc.next_trading_day(date(2026, 12, 30)) == date(2027, 1, 4)
    assert xc.prev_trading_day(date(2027, 1, 4)) == date(2026, 12, 30)


def test_add_trading_days_skips_holidays(monkeypatch) -> None:
    monkeypatch.setitem(xc._cache, "days", {date(2027, 3, 9), date(2027, 3, 10), date(2027, 3, 11), date(2027, 3, 12), date(2027, 3, 15)})
    monkeypatch.setitem(xc._cache, "at", time.monotonic())
    assert xc.add_trading_days(date(2027, 3, 5), 1) == date(2027, 3, 8)
    assert xc.add_trading_days(date(2027, 3, 5), 2) == date(2027, 3, 16)             # the Idul Fitri week is not a window


def test_table_ends_before_the_notes_and_the_english_copy() -> None:
    text = ("Desember 24-12-2026\n25-12-2026\n31-12-2026\nKamis\nJumat\nKamis\nCuti Bersama Kelahiran Yesus Kristus\n"
            "Kelahiran Yesus Kristus\nLibur Bursa\n20\nJumlah Hari Bursa 239\nCatatan:\n1. Idul Fitri (21 Maret 2026) ...\n"
            "Month Date Day Remarks Trading\nJanuary 01-01-2026\nNew Year 2026\n")
    assert xc.parse_calendar_text(text) == [(date(2026, 12, 24), "Cuti Bersama Kelahiran Yesus Kristus"),
                                           (date(2026, 12, 25), "Kelahiran Yesus Kristus"), (date(2026, 12, 31), "Libur Bursa")]
