"""Rights / warrants ingest (idx/jobs/deriv.py): code parsing, series windows, bar filtering, Stockbit paging - offline."""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from blackheart_ingest.idx.jobs import deriv as dv


def test_codes_and_ratio() -> None:
    assert dv.right_expiry("COCO-R20260721") == date(2026, 7, 21) and dv.right_expiry("COCO-W") is None
    assert dv.exchange_code("COCO-R20260721") == "COCO-R" and dv.exchange_code("coco-w2") == "COCO-W2"
    assert dv.parse_ratio("100 : 111") == (Decimal(100), Decimal(111))
    assert dv.parse_ratio("1:1") == (Decimal(1), Decimal(1))
    assert dv.parse_ratio("-") is None and dv.parse_ratio(None) is None


def test_series_rights_by_expiry_warrants_by_unbroken_run() -> None:
    rows = [("right", "COCO-R20260721", date(2026, 7, 1)),
            ("right", "BNBR-R20260105", date(2025, 12, 1)), ("right", "BNBR-R20260105", date(2026, 1, 1)),
            ("warrant", "ABCD-W", date(2025, 1, 1)), ("warrant", "ABCD-W", date(2025, 2, 1)), ("warrant", "ABCD-W", date(2025, 3, 1)),
            ("warrant", "ABCD-W", date(2026, 5, 1))]
    s = {x["series"]: x for x in dv.series(rows)}
    assert s["COCO-R20260721"]["code"] == "COCO-R" and s["COCO-R20260721"]["end"] == date(2026, 7, 21)
    assert s["BNBR-R20260105"]["start"] == date(2025, 12, 1)
    assert s["ABCD-W@2025-01"]["end"] == date(2025, 3, 31) and s["ABCD-W@2026-05"]["start"] == date(2026, 5, 1)
    assert len(s) == 4
    old = {x["series"]: x for x in dv.series([("right", "AGRS-R", date(2020, 4, 1)), ("right", "AGRS-R", date(2021, 6, 1)),
                                              ("right", "AGRS-R", date(2021, 7, 1))])}
    assert set(old) == {"AGRS-R@2020-04", "AGRS-R@2021-06"} and old["AGRS-R@2021-06"]["end"] == date(2021, 7, 31)
    assert old["AGRS-R@2020-04"]["code"] == "AGRS-R"


def test_keep_bars_drops_padding_and_out_of_window() -> None:
    rows = [{"date": "2026-07-14", "close": 5, "volume": 100}, {"date": "2026-07-30", "close": 5, "volume": 0},
            {"date": "2026-06-30", "close": 7, "volume": 10}, {"date": "2026-07-15", "close": None, "volume": 5}]
    got = dv.keep_bars(rows, date(2026, 7, 1), date(2026, 7, 31))
    assert [x["date"] for x in got] == [date(2026, 7, 14)]


def test_spans_and_paging() -> None:
    assert dv.spans(date(2020, 1, 1), date(2021, 6, 30))[0] == (date(2020, 1, 1), date(2020, 12, 16))
    calls = []

    def get(url: str, h: dict[str, str]) -> tuple[int, bytes]:
        calls.append(url)
        page = int(url.rsplit("page=", 1)[1])
        n = 50 if page == 1 else 3
        return 200, json.dumps({"data": {"result": [{"date": f"2026-07-{i % 28 + 1:02d}", "close": 1, "volume": 1} for i in range(n)]}}).encode()
    rows = dv.fetch_stockbit_rows("COCO-R", date(2026, 7, 1), date(2026, 7, 31), {}, get)
    assert len(rows) == 53 and len(calls) == 2 and "COCO-R" in calls[0]
