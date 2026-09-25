"""Pure ETL on the feed defects seen in the 2026-09-12 primary pull."""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from blackheart_ingest.idx import etl

NOW = datetime(2026, 9, 12, 10, 0, tzinfo=UTC)


def row(**kw):
    base = {"No": 1, "IDStockSummary": 1, "Date": "2026-09-11T00:00:00", "StockCode": "BBCA",
            "StockName": "Bank Central Asia Tbk.", "Remarks": "XD--", "Previous": 6425.0, "OpenPrice": 6400.0,
            "FirstTrade": 6400.0, "High": 6400.0, "Low": 6250.0, "Close": 6325.0, "Change": -100.0,
            "Volume": 187922700.0, "Value": 1186692840000.0, "Frequency": 39802.0, "IndexIndividual": 18059.0,
            "Offer": 6325.0, "OfferVolume": 1703300.0, "Bid": 6300.0, "BidVolume": 5313800.0,
            "ListedShares": 122042299500.0, "TradebleShares": 122042299500.0, "WeightForIndex": 1.0,
            "ForeignSell": 154534600.0, "ForeignBuy": 71131400.0, "DelistingDate": "",
            "NonRegularVolume": 86020.0, "NonRegularValue": 578372375.0, "NonRegularFrequency": 12.0}
    base.update(kw)
    return base


def test_summary_and_bar_normal_day() -> None:
    s = etl.summary_rows([row()], NOW, 7)[0]
    assert s["code"] == "BBCA" and s["trade_date"].isoformat() == "2026-09-11"
    assert s["close"] == Decimal("6325") and s["foreign_buy"] == 71131400 and s["bronze_id"] == 7
    assert s["delisting_date"] is None and s["listed_shares"] == 122042299500
    b = etl.bar_row(s)
    assert b["open"] == Decimal("6400") and not b["open_missing"] and b["quality_flags"] == []
    assert b["source"] == "idx" and b["basis"] == "split_only"


def test_covid_missing_open_is_null_not_fabricated() -> None:
    s = etl.summary_rows([row(Date="2020-03-16T00:00:00", OpenPrice=0.0, FirstTrade=0.0, Previous=28300.0,
                              High=28300.0, Low=26575.0, Close=27525.0)], NOW, None)[0]
    assert s["open"] is None and s["first_trade"] is None
    b = etl.bar_row(s)
    assert b["open"] is None and b["open_missing"] and "open_missing" in b["quality_flags"]
    assert "ohlc_inconsistent" not in b["quality_flags"]


def test_first_trade_fallback_when_only_openprice_is_zero() -> None:
    s = etl.summary_rows([row(OpenPrice=0.0, FirstTrade=6410.0, High=6450.0)], NOW, None)[0]
    b = etl.bar_row(s)
    assert b["open"] == Decimal("6410") and not b["open_missing"]


def test_no_trade_day_and_zero_close() -> None:
    s = etl.summary_rows([row(Volume=0.0, Value=0.0, Frequency=0.0, High=0.0, Low=0.0, Close=6425.0, OpenPrice=0.0,
                              FirstTrade=0.0)], NOW, None)[0]
    b = etl.bar_row(s)
    assert "no_trade" in b["quality_flags"] and "hl_missing" in b["quality_flags"]
    assert b["high"] == b["low"] == Decimal("6425")
    assert etl.bar_row(etl.summary_rows([row(Close=0.0)], NOW, None)[0]) is None


def test_duplicates_last_wins_and_bad_rows_dropped() -> None:
    rows = [row(Close=1.0), row(Close=2.0), row(StockCode=""), row(Date=None)]
    out = etl.summary_rows(rows, NOW, None)
    assert len(out) == 1 and out[0]["close"] == Decimal("2")


def test_bbca_split_detected_exactly_from_share_ratio() -> None:
    # 2021-10-12 close 36,600 / listed 24,408,459,900 -> 2021-10-13 Previous 7,325 / listed 122,042,299,500
    factor = etl.previous_reset(Decimal("36600"), Decimal("7325"))
    assert factor is not None and abs(factor - Decimal("0.2001366")) < Decimal("0.0001")
    kind, f = etl.classify_action(factor, 24408459900, 122042299500)
    assert kind == "split" and f == Decimal("0.2")


def test_rights_issue_uses_price_factor() -> None:
    # BBRI 2021-09-08: Previous/prior close = 0.974, listed shares unchanged on the ex-date
    factor = etl.previous_reset(Decimal("4000"), Decimal("3896"))
    kind, f = etl.classify_action(factor, 123345810000, 123345810000)
    assert kind == "rights_or_bonus" and f == Decimal("3896") / Decimal("4000")


def test_small_previous_mismatch_is_not_an_action() -> None:
    assert etl.previous_reset(Decimal("1000"), Decimal("1004")) is None
    assert etl.previous_reset(Decimal("1000"), Decimal("1000")) is None
    assert etl.previous_reset(None, Decimal("1000")) is None


def test_listing_and_index_rows() -> None:
    ls = etl.listing_rows([{"Code": "bbca", "Name": "Bank Central Asia Tbk.", "ListingDate": "2000-05-31T00:00:00",
                            "Shares": 122042299500.0, "ListingBoard": "Utama"}, {"Code": ""}])
    assert ls == [{"code": "BBCA", "name": "Bank Central Asia Tbk.", "listing_date": etl.parse_date("2000-05-31"),
                   "board": "Utama", "listed_shares": 122042299500}]
    ix = etl.index_rows([{"IndexCode": "COMPOSITE", "Date": "2026-09-11T00:00:00", "Previous": 6589.338,
                          "Highest": 6552.792, "Lowest": 6462.96, "Close": 6541.377, "Volume": 28617128161.0,
                          "Value": 14712675309883.0}], NOW, 3)
    assert ix[0]["index_code"] == "COMPOSITE" and ix[0]["open"] is None and ix[0]["high"] == Decimal("6552.792")


def test_detection_blocked_when_prior_session_missing() -> None:
    from datetime import date
    # 2026-09-21: 09-18 had only Yahoo fallback bars, the latest summary was 09-17 -> no detection
    assert etl.detection_blocked(date(2026, 9, 17), date(2026, 9, 18), 641, 963) is not None
    assert etl.detection_blocked(date(2026, 9, 17), date(2026, 9, 18), 0, 963) is not None
    # no bars either: the mass reset gives it away
    assert "missing prior session" in etl.detection_blocked(date(2026, 9, 17), date(2026, 9, 17), 641, 963)
    # a normal ex-date day (max seen: 5 names) and a thin early universe still detect
    assert etl.detection_blocked(date(2026, 9, 18), date(2026, 9, 18), 5, 963) is None
    assert etl.detection_blocked(date(2026, 9, 18), date(2026, 9, 18), 19, 100) is None
    assert etl.detection_blocked(None, None, 0, 0) is None
