"""Gap-fade book (menu 29b): the pure selection/sizing/exit rules, the scan guards, and one round trip on a test book -
entry at the open, exit ticket, settle at the close, and the sweep that guarantees nothing is ever held overnight."""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from decimal import Decimal

import psycopg
import pytest

from blackheart_ingest.idx import book as bk
from blackheart_ingest.idx import gapfade, ticket

WIB = "Asia/Jakarta"


# ---- pure ------------------------------------------------------------------------------------------------------------
def test_gap_and_pick() -> None:
    assert gapfade.gap_of(Decimal(930), Decimal(1000)) == Decimal("-0.07")
    cands = [{"code": "AAA", "gap": Decimal("-0.08"), "v60": 1e10}, {"code": "BBB", "gap": Decimal("-0.20"), "v60": 6e9},
             {"code": "CCC", "gap": Decimal("-0.09"), "v60": 9e9}, {"code": "DDD", "gap": Decimal("-0.09"), "v60": 2e10}]
    assert [c["code"] for c in gapfade.pick(cands, 3)] == ["BBB", "DDD", "CCC"]      # deepest first, ties by liquidity
    assert [c["code"] for c in gapfade.pick(cands, 3, held={"BBB"})] == ["DDD", "CCC", "AAA"]
    assert gapfade.pick(cands, 0) == []


def test_plan_entries_sizes_slots_and_respects_cash() -> None:
    picked = [{"code": "AAA", "open": Decimal(1000), "prev_close": Decimal(1100), "gap": Decimal("-0.09")},
              {"code": "BBB", "open": Decimal(500), "prev_close": Decimal(560), "gap": Decimal("-0.11")}]
    lines = gapfade.plan_entries(picked, nav=Decimal(100_000_000), cash=Decimal(100_000_000), k=5,
                                 fee_buy=Decimal("0.001"), min_trade=Decimal(5_000_000))
    assert [ln["code"] for ln in lines] == ["AAA", "BBB"]
    assert lines[0]["limit_price"] == Decimal(1005)                                   # open + one tick (Rp 5 band)
    assert lines[0]["notional"] <= Decimal(20_000_000) and lines[0]["lots"] == Decimal(198)   # slot 20 M / (1,005 x 100 lots) after the fee
    assert all(ln["side"] == "buy" and "gapfade:entry" in ln["flags"] for ln in lines)
    tight = gapfade.plan_entries(picked, nav=Decimal(100_000_000), cash=Decimal(6_000_000), k=5,
                                 fee_buy=Decimal("0.001"), min_trade=Decimal(5_000_000))
    assert [ln["code"] for ln in tight] == ["AAA"]                                    # the cash pays for one line only
    assert gapfade.plan_entries(picked, nav=Decimal(1_000_000), cash=Decimal(1_000_000), k=5,
                                fee_buy=Decimal("0.001"), min_trade=Decimal(5_000_000)) == []   # slot under the floor


def test_plan_exits_sells_everything_priced() -> None:
    pos = [{"code": "AAA", "lots": Decimal(19)}, {"code": "BBB", "lots": Decimal(5)}, {"code": "ZZZ", "lots": Decimal(3)}]
    lines = gapfade.plan_exits(pos, {"AAA": Decimal(1100), "BBB": Decimal(480)})
    assert [ln["code"] for ln in lines] == ["AAA", "BBB"]                             # ZZZ has no price: kept, not sold blind
    assert lines[0]["side"] == "sell" and lines[0]["limit_price"] == Decimal(1095)     # close - one tick
    assert all("gapfade:exit" in ln["flags"] for ln in lines)


# ---- database round trip ----------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def conn():
    dsn = os.environ.get("INGEST_DB_DSN")
    if not dsn:
        pytest.skip("INGEST_DB_DSN not set")
    with psycopg.connect(dsn) as c:
        yield c


BOOK = "test_gapfade"
D = date(2024, 5, 14)                       # a Tuesday well before any real feed data
PREV = date(2024, 5, 13)


def _clean(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM idx.ticket_line WHERE ticket_id IN (SELECT id FROM idx.ticket WHERE book = %s)", (BOOK,))
        for sql in ("DELETE FROM idx.ticket WHERE book = %s", "DELETE FROM idx.fill WHERE book = %s", "DELETE FROM idx.position WHERE book = %s",
                    "DELETE FROM idx.book_mark WHERE book = %s", "DELETE FROM idx.book_nav WHERE book = %s", "DELETE FROM idx.decision WHERE book = %s",
                    "DELETE FROM idx.alert WHERE job = 'gapfade:' || %s",     # the guards raise real alerts; a test leaves none
                    "DELETE FROM idx.book WHERE book = %s"):
            cur.execute(sql, (BOOK,))
        for code in ("TSTA", "TSTB"):
            cur.execute("DELETE FROM idx.feed_trade WHERE code = %s", (code,))
            cur.execute("DELETE FROM idx.feed_book WHERE code = %s", (code,))
            cur.execute("DELETE FROM idx.bar WHERE code = %s", (code,))
            cur.execute("DELETE FROM idx.feature_daily WHERE code = %s", (code,))
            cur.execute("DELETE FROM idx.listing WHERE code = %s", (code,))
    conn.commit()


def _seed(conn, *, opens: dict[str, int], closes: dict[str, int], prev: dict[str, int], with_offer=("TSTA", "TSTB"), n_filler: int = 60) -> None:
    """Two test names with a previous close, an opening print, a book with an offer, and today's close; plus enough filler
    opening prints (real codes are untouched - the filler is the market's own feed) to pass the coverage guard."""
    with conn.cursor() as cur:
        for code in opens:
            cur.execute("""INSERT INTO idx.listing (code, name, board, status, listing_date, first_seen, last_seen)
                           VALUES (%s, %s, 'Utama', 'ACTIVE', %s, %s, %s) ON CONFLICT (code) DO UPDATE SET board = 'Utama', status = 'ACTIVE'""",
                        (code, f"Test {code}", PREV, PREV, D))
            cur.execute("""INSERT INTO idx.bar (code, trade_date, source, open, high, low, close, volume, value)
                           VALUES (%s, %s, 'idx', %s, %s, %s, %s, 1000000, 1000000000) ON CONFLICT (code, trade_date) DO UPDATE SET close = EXCLUDED.close""",
                        (code, PREV, prev[code], prev[code], prev[code], prev[code]))
            cur.execute("""INSERT INTO idx.feature_daily (code, trade_date, value_60d_median) VALUES (%s, %s, %s)
                           ON CONFLICT (code, trade_date) DO UPDATE SET value_60d_median = EXCLUDED.value_60d_median""", (code, PREV, 10_000_000_000))
            ts = datetime(D.year, D.month, D.day, 8, 58, 3)
            cur.execute("""INSERT INTO idx.feed_trade (ts, code, seq, price, qty, verb, board, recv_at)
                           VALUES (%s AT TIME ZONE %s, %s, 1, %s, 10000, 'B', 'RG', now()) ON CONFLICT DO NOTHING""",
                        (ts, WIB, code, opens[code]))
            if code in with_offer:
                cur.execute("""INSERT INTO idx.feed_book (ts, code, seq, bid_px, bid_vol, bid_n, off_px, off_vol, off_n, bid_total, off_total, bid_levels, off_levels, n_updates)
                               VALUES (%s AT TIME ZONE %s, %s, 1, %s, %s, %s, %s, %s, %s, 100000, 100000, 1, 1, 1) ON CONFLICT DO NOTHING""",
                            (ts, WIB, code, [opens[code] - 5], [100000], [1], [opens[code]], [100000], [1]))
            if code in closes:
                cur.execute("""INSERT INTO idx.bar (code, trade_date, source, open, high, low, close, volume, value)
                               VALUES (%s, %s, 'idx', %s, %s, %s, %s, 1000000, 1000000000) ON CONFLICT (code, trade_date) DO UPDATE SET close = EXCLUDED.close""",
                            (code, D, opens[code], max(opens[code], closes[code]), min(opens[code], closes[code]), closes[code]))
        for i in range(n_filler):                                           # coverage guard: enough names opened that morning
            cur.execute("""INSERT INTO idx.feed_trade (ts, code, seq, price, qty, verb, board, recv_at)
                           VALUES (%s AT TIME ZONE %s, %s, 1, 1000, 100, 'B', 'RG', now()) ON CONFLICT DO NOTHING""",
                        (datetime(D.year, D.month, D.day, 8, 58, 5), WIB, f"F{i:03d}"))
    conn.commit()


def _clean_filler(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM idx.feed_trade WHERE code LIKE 'F___' AND (ts AT TIME ZONE 'Asia/Jakarta')::date = %s", (D,))
    conn.commit()


def test_round_trip(conn) -> None:
    _clean(conn)
    # TSTA gaps -10 % and recovers to 960 by the close; TSTB gaps -3 % (not deep enough)
    _seed(conn, prev={"TSTA": 1000, "TSTB": 1000}, opens={"TSTA": 900, "TSTB": 970}, closes={"TSTA": 960, "TSTB": 975})
    bk.ensure_book(conn, BOOK, rule="gapfade", cash="100000000", max_names=5, fee_buy_pct="0.10", fee_sell_pct="0.20",
                   min_v60=str(int(gapfade.LIQ_MIN)), max_weight_pct="25", max_sector_pct="100", label="Test gapfade")
    try:
        s = gapfade.scan(conn, D)
        assert s["ok"] and [c["code"] for c in s["candidates"]] == ["TSTA"]           # TSTB is above the threshold
        assert s["skipped"]["not_deep"] >= 1
        assert "gapfade scan" in gapfade.render_scan(s)

        rep = gapfade.run_entry(conn, BOOK, actor="operator", d=D)
        assert rep["ticket"] and rep["status"] == "filled" and len(rep["filled"]) == 1
        assert rep["filled"][0]["code"] == "TSTA" and rep["filled"][0]["price"] == Decimal(900)
        pos = {p["code"]: p for p in bk.snapshot(conn, BOOK)["positions"]}
        assert Decimal(pos["TSTA"]["lots"]) > 0

        again = gapfade.run_entry(conn, BOOK, actor="operator", d=D)                   # idempotent: one entry a day
        assert again["ticket"] is None and "already exists" in again["why"]

        ex = gapfade.run_exit(conn, BOOK, actor="operator", d=D)
        assert ex["ticket"] and ex["status"] == "issued" and ex["positions"] == 1
        assert gapfade.run_exit(conn, BOOK, actor="operator", d=D)["ticket"] is None   # idempotent too

        st = gapfade.settle(conn, BOOK, actor="operator", d=D)
        assert len(st["filled"]) == 1 and st["filled"][0]["side"] == "sell"
        assert st["filled"][0]["price"] == Decimal(955)                                # close 960 less one tick
        assert not [p for p in bk.snapshot(conn, BOOK)["positions"] if Decimal(p["lots"]) > 0]
        t = ticket.load(conn, ex["ticket"])
        assert t["status"] == "closed"
        rows = gapfade.status(conn, BOOK, D)
        assert rows["entry"] and rows["exit"] and rows["positions"] == []
    finally:
        _clean(conn)
        _clean_filler(conn)


def test_guards(conn) -> None:
    _clean(conn)
    try:
        # no feed at all -> not ok, and no trading
        s = gapfade.scan(conn, date(2019, 1, 3))
        assert not s["ok"] and "opening prints" in s["why"]
        # a name without an offer (locked at auto-rejection down) is skipped
        _seed(conn, prev={"TSTA": 1000}, opens={"TSTA": 900}, closes={"TSTA": 950}, with_offer=())
        s = gapfade.scan(conn, D)
        assert s["ok"] and s["candidates"] == [] and s["skipped"]["no_offer"] == 1
        # a halted book trades nothing
        bk.ensure_book(conn, BOOK, rule="gapfade", cash="100000000", max_names=5, min_v60=str(int(gapfade.LIQ_MIN)),
                       max_weight_pct="25", max_sector_pct="100")
        bk.halt(conn, BOOK, "test")
        rep = gapfade.run_entry(conn, BOOK, actor="operator", d=D)
        assert rep["ticket"] is None and "halted" in rep["why"]
        bk.resume(conn, BOOK)
        with pytest.raises(ValueError, match="not a gap-fade book"):
            gapfade.run_entry(conn, "paper", actor="operator", d=D)
    finally:
        _clean(conn)
        _clean_filler(conn)


def test_leftover_position_is_swept_at_the_open(conn) -> None:
    """A position that survived a session must be sold at the next open before anything new is bought."""
    _clean(conn)
    _seed(conn, prev={"TSTA": 1000, "TSTB": 1000}, opens={"TSTA": 900, "TSTB": 980}, closes={"TSTA": 960, "TSTB": 985})
    bk.ensure_book(conn, BOOK, rule="gapfade", cash="100000000", max_names=5, fee_buy_pct="0.10", fee_sell_pct="0.20",
                   min_v60=str(int(gapfade.LIQ_MIN)), max_weight_pct="25", max_sector_pct="100")
    try:
        bk.add_fill(conn, BOOK, PREV, "TSTB", "buy", Decimal(10), Decimal(1000))       # yesterday's leftover
        assert any(p["code"] == "TSTB" for p in bk.snapshot(conn, BOOK)["positions"])
        rep = gapfade.run_entry(conn, BOOK, actor="operator", d=D)
        assert [f["code"] for f in rep["swept"]] == ["TSTB"]
        held = {p["code"]: Decimal(p["lots"]) for p in bk.snapshot(conn, BOOK)["positions"]}
        assert held.get("TSTB", Decimal(0)) == 0 and held.get("TSTA", Decimal(0)) > 0   # swept, and today's entry still ran
    finally:
        _clean(conn)
        _clean_filler(conn)


def test_settle_without_a_bar_keeps_the_position(conn) -> None:
    """No close published yet -> the exit ticket stays open and the position survives to be swept, never a guessed price."""
    _clean(conn)
    _seed(conn, prev={"TSTA": 1000}, opens={"TSTA": 900}, closes={})
    bk.ensure_book(conn, BOOK, rule="gapfade", cash="100000000", max_names=5, fee_buy_pct="0.10", fee_sell_pct="0.20",
                   min_v60=str(int(gapfade.LIQ_MIN)), max_weight_pct="25", max_sector_pct="100")
    try:
        gapfade.run_entry(conn, BOOK, actor="operator", d=D)
        gapfade.run_exit(conn, BOOK, actor="operator", d=D)
        st = gapfade.settle(conn, BOOK, actor="operator", d=D)
        assert st["filled"] == [] and "not been published" in st["why"]
        assert any(Decimal(p["lots"]) > 0 for p in bk.snapshot(conn, BOOK)["positions"])
    finally:
        _clean(conn)
        _clean_filler(conn)


def test_prev_session_and_stale_bars(conn) -> None:
    assert gapfade.prev_session(conn, date(2019, 1, 3)) is None or gapfade.prev_session(conn, date(2019, 1, 3)) < date(2019, 1, 3)
    d = date.today() + timedelta(days=400)                                              # far future: the last bar is stale
    s = gapfade.scan(conn, d)
    assert not s["ok"]
