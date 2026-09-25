"""Macro series: the BI-Rate page parser, the change table, and the BPS web-API parsing (all pure / stubbed)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import numpy as np
import pandas as pd

from blackheart_ingest.idx import macro as M
from blackheart_ingest.idx.ml import daily as D

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
    assert {s.source for s in M.CATALOG} <= {"fred", "yahoo", "bi", "worldbank", "bps"}


# ---- BPS web API -------------------------------------------------------------------------------------------------------------
# One year of variable 2263 as the API returns it: datacontent keys are vervar + var + turvar + th + turtahun, and the national
# row is vervar 9999 (the rest are provinces). turtahun 13 = "Tahunan" (the calendar-year figure), which is not a month.
BPS_TH = {"status": "OK", "data": [{"pages": 1}, [{"th_id": 125, "th": "2025"}, {"th_id": 124, "th": "2024"}]]}
BPS_DATA = {
    "status": "OK",
    "var": [{"val": 2263, "label": "Inflasi Tahunan (Y-on-Y) 38 Provinsi (2022=100)", "unit": "Persen"}],
    "turvar": [{"val": "0", "label": "Tidak ada"}],
    "vervar": [{"val": 1100, "label": "PROV ACEH"}, {"val": 9999, "label": "INDONESIA"}],
    "tahun": [{"val": 125, "label": "2025"}],
    "turtahun": [{"val": 1, "label": "Januari"}, {"val": 2, "label": "Februari"}, {"val": 13, "label": "Tahunan"}],
    "datacontent": {"9999226301251": 0.76, "9999226301252": -0.09, "9999226301251 3": 9.99,      # a malformed key is ignored
                    "9999226301252 ": 9.99, "1100226301251": 4.20, "999922630125" + "13": 1.57},
}


def test_fetch_bps_reads_the_national_monthly_rows_only(monkeypatch) -> None:
    calls = []

    def fake_get(params):
        calls.append(params["model"])
        return BPS_TH if params["model"] == "th" else BPS_DATA

    monkeypatch.setattr(M, "_bps_get", fake_get)
    pts = M.fetch_bps("2263", date(2025, 1, 1))
    assert pts == [(date(2025, 1, 31), Decimal("0.76")), (date(2025, 2, 28), Decimal("-0.09"))]   # months only, end of month
    assert calls[0] == "th" and "data" in calls                                                   # 2024 is filtered out by `since`
    assert M.fetch_bps("2263", date(2025, 2, 1)) == [(date(2025, 2, 28), Decimal("-0.09"))]


def test_fetch_bps_refuses_an_unconfigured_variable() -> None:
    try:
        M.fetch_bps("0", date(2025, 1, 1))
    except RuntimeError as e:
        assert "not configured" in str(e)
    else:
        raise AssertionError("expected a RuntimeError")


def test_load_macro_prefers_the_bps_inflation_over_the_oecd_index(monkeypatch) -> None:
    """Both series cover 2025-03; the BPS reading (pct) wins and becomes the same log y/y feature the OECD index produced."""
    rows = [("id_cpi", date(2024, 3, 1), 100.0), ("id_cpi", date(2025, 3, 1), 105.0), ("id_inflation_yoy", date(2025, 3, 31), 3.0),
            ("id_inflation_yoy", date(2025, 4, 30), 2.0)]
    rows += [("id_cpi", date(2024, m, 1), 100.0) for m in range(4, 13)] + [("id_cpi", date(2025, m, 1), 105.0) for m in (1, 2)]
    monkeypatch.setattr(D, "_frame", lambda conn, sql, params, cols: pd.DataFrame(rows, columns=cols))
    out = D.load_macro(None)
    s = out[["d", "id_cpi_yoy"]].dropna().set_index("d")["id_cpi_yoy"]
    # the BPS March reading is known from 1 April (month_next_bday) and the April one from 1 May
    assert abs(float(s.loc[pd.Timestamp("2025-04-01")]) - float(np.log1p(0.03))) < 1e-9
    assert abs(float(s.loc[pd.Timestamp("2025-05-01")]) - float(np.log1p(0.02))) < 1e-9
    assert "id_inflation_yoy" not in out.columns                                  # folded into id_cpi_yoy, not a second feature
