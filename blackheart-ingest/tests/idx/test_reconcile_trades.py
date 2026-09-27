"""Trade-level reconciliation against a broker statement (reconcile.parse_trades_csv / diff_trades) - offline."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from blackheart_ingest.idx import reconcile as rc

STATEMENT = """Akun;12345
Tanggal;Kode Saham;Jenis;Lot;Harga;Komisi
24/09/2026;DEWI;Jual;54;222;2.397,60
22/09/2026;IRSX.JK;Beli;21;456;957,60
18/09/2026;DEWI;Beli;30;184;552
18/09/2026;DEWI;Beli;24;184;441,60
18/09/2026;ERAA;Beli;15;625;937,50
"""


def test_parse_indonesian_statement() -> None:
    rows = rc.parse_trades_csv(STATEMENT)
    assert len(rows) == 5
    assert rows[0] == {"date": "2026-09-24", "code": "DEWI", "side": "sell", "lots": Decimal(54), "price": Decimal(222), "fee": Decimal("2397.60")}
    assert rows[1]["code"] == "IRSX" and rows[1]["side"] == "buy"


def test_diff_aggregates_partials_and_flags_differences() -> None:
    broker = rc.parse_trades_csv(STATEMENT)
    book = [{"date": date(2026, 9, 24), "code": "DEWI", "side": "sell", "lots": 54, "price": 222, "fee": Decimal("2397.60")},
            {"date": date(2026, 9, 22), "code": "IRSX", "side": "buy", "lots": 21, "price": 458, "fee": Decimal("957.60")},     # price differs
            {"date": date(2026, 9, 18), "code": "DEWI", "side": "buy", "lots": 54, "price": 184, "fee": Decimal("993.60")},      # 2 partials at the broker
            {"date": date(2026, 9, 18), "code": "BBCA", "side": "buy", "lots": 1, "price": 9000, "fee": 9}]
    d = rc.diff_trades(book, broker)
    assert d["matched"] == 3 and not d["ok"]
    assert [m["code"] for m in d["differences"]] == ["IRSX"]
    assert d["only_book"] == [["2026-09-18", "BBCA", "buy"]] and d["only_broker"] == [["2026-09-18", "ERAA", "buy"]]


def test_shares_column_and_iso_dates() -> None:
    text = "date,symbol,side,shares,price,fee\n2026-10-06 09:00:05,BBRI,B,500,4100,2050\n"
    rows = rc.parse_trades_csv(text)
    assert rows == [{"date": "2026-10-06", "code": "BBRI", "side": "buy", "lots": Decimal(5), "price": Decimal(4100), "fee": Decimal(2050)}]
