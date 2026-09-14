"""Macro series: the BI-Rate page parser and the change table (pure)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from blackheart_ingest.idx import macro as M

BI_HTML = """
<tr><td class="text-center">19 Agustus 2026</td><td class="text-center">5.75 %</td></tr>
<tr><td class="text-center">9 Juni 2026</td><td class="text-center">5.50 %</td></tr>
<tr><td class="text-center">22 April 2026</td><td class="text-center">4,75 %</td></tr>
<tr><td>not a date</td><td>1.00 %</td></tr>
"""


def test_bi_rate_page_parses_indonesian_dates_and_both_decimal_marks() -> None:
    rows = M.parse_bi_rate_page(BI_HTML)
    assert rows == [(date(2026, 4, 22), Decimal("4.75")), (date(2026, 6, 9), Decimal("5.50")), (date(2026, 8, 19), Decimal("5.75"))]


def test_changes_look_back_one_three_and_twelve_months() -> None:
    pts = [(date(2025, 9, 1), Decimal(100)), (date(2026, 6, 1), Decimal(110)), (date(2026, 8, 10), Decimal(120)), (date(2026, 9, 10), Decimal(126))]
    c = M.changes(pts)
    assert c["value"] == 126 and c["date"] == date(2026, 9, 10)
    assert c["chg_1m"] == 6 and c["chg_3m"] == 16 and c["chg_12m"] == 26
    assert round(c["chg_12m_pct"], 1) == Decimal("26.0")
    assert M.changes([])["value"] is None
    assert M.changes([(date(2026, 9, 1), Decimal(5))])["chg_1m"] is None          # nothing a month back


def test_catalog_keys_are_unique_and_sources_known() -> None:
    keys = [s.key for s in M.CATALOG]
    assert len(keys) == len(set(keys))
    assert {s.source for s in M.CATALOG} <= {"fred", "yahoo", "bi", "worldbank"}
