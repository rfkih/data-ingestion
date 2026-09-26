"""jobs/bar_open: the rule that decides when a Yahoo open may stand in for the one IDX left out."""
from __future__ import annotations

from datetime import date, timedelta

from blackheart_ingest.idx.jobs import bar_open as bo

D0 = date(2025, 1, 6)


def _days(n: int, close: float = 1000.0):
    return [bo.IdxDay(D0 + timedelta(days=i), None, close + 20, close - 20, close) for i in range(n)]


def _yahoo(days, factor: float = 1.0, open_at=None):
    """Yahoo on a basis `factor` times ours (a split since then), with the open at `open_at` (our basis)."""
    return {x.d: bo.YDay(x.d, (open_at if open_at is not None else x.close - 5) / factor, x.close / factor) for x in days}


def test_tick_table():
    assert [bo.tick(p) for p in (50, 199, 200, 499, 500, 1999, 2000, 4999, 5000)] == [1, 1, 2, 2, 5, 5, 10, 10, 25]


def test_accepts_an_aligned_open_on_the_grid_even_on_a_split_basis():
    days = _days(15)
    got = bo.derive(days, _yahoo(days, factor=2.0, open_at=995.0))           # Yahoo halved by a later 2:1 split
    assert got[days[7].d] == (995.0, "ok")


def test_snaps_to_the_grid_within_a_quarter_tick():
    days = _days(15)
    y = _yahoo(days, open_at=995.0)
    y[days[7].d] = bo.YDay(days[7].d, 995.9, y[days[7].d].close)             # 0.9 off a 5-rupiah grid: snaps to 995
    assert bo.derive(days, y)[days[7].d] == (995.0, "ok")
    y[days[7].d] = bo.YDay(days[7].d, 997.5, y[days[7].d].close)             # half a tick off: not an IDX price
    assert bo.derive(days, y)[days[7].d] == (None, "off_grid")


def test_rejects_a_misaligned_day_and_an_open_outside_the_range():
    days = _days(15)
    y = _yahoo(days, open_at=995.0)
    y[days[7].d] = bo.YDay(days[7].d, 995.0, 1010.0)                         # Yahoo's close disagrees: another day's row
    assert bo.derive(days, y)[days[7].d] == (None, "misaligned")
    y = _yahoo(days, open_at=1050.0)                                         # above IDX's high of 1020
    assert bo.derive(days, y)[days[7].d] == (None, "outside_range")


def test_missing_on_yahoo_and_too_few_neighbours():
    days = _days(15)
    y = _yahoo(days)
    del y[days[3].d]
    assert bo.derive(days, y)[days[3].d] == (None, "not_on_yahoo")
    short = _days(3)
    assert bo.derive(short, _yahoo(short))[short[0].d] == (None, "too_few_neighbours")


def test_validate_scores_only_known_opens_and_counts_the_fillable():
    days = _days(15)
    known = [bo.IdxDay(x.d, 995.0 if i % 2 else None, x.high, x.low, x.close) for i, x in enumerate(days)]
    rep = bo.validate({"AAAA": known}, {"AAAA": _yahoo(days, open_at=995.0)})
    assert rep["total"]["accepted"] == 7 and rep["accuracy"] == 1.0
    assert rep["fillable_missing"] == 8


def test_a_date_where_yahoo_disagrees_with_idx_for_many_names_is_not_used():
    names = {}
    yahoo = {}
    for k in range(25):
        days = _days(15)
        # every name has IDX's open on day 7 (995), except the last, which has none there and is the one to fill
        names[f"N{k:02d}"] = [bo.IdxDay(x.d, 995.0 if (i == 7 and k < 24) else None, x.high, x.low, x.close) for i, x in enumerate(days)]
        y = _yahoo(days, open_at=995.0)
        if k < 3:                                            # 3 of 24 known names disagree on day 7: 12.5 % > 5 %
            y[days[7].d] = bo.YDay(days[7].d, 990.0, y[days[7].d].close)
        yahoo[f"N{k:02d}"] = y
    rep = bo.validate(names, yahoo)
    assert rep["bad_dates"] == [names["N00"][7].d.isoformat()]
    assert rep["total"]["accepted"] == 0                     # nothing scored on a bad date


def test_every_stored_open_has_a_source_lies_in_the_range_and_on_the_grid():
    """The invariant the fill must keep on the live table: no open without a source, none outside the day's low-high,
    none off IDX's tick grid."""
    import os

    import psycopg
    import pytest
    dsn = os.environ.get("INGEST_DB_DSN")
    if not dsn:
        pytest.skip("INGEST_DB_DSN not set")
    try:
        c = psycopg.connect(dsn, connect_timeout=5)
    except Exception as e:
        pytest.skip(f"db unreachable: {e}")
    with c, c.cursor() as cur:
        cur.execute("""SELECT count(*) FILTER (WHERE open_src IS NULL),
                              count(*) FILTER (WHERE open < low OR open > high),
                              count(*) FILTER (WHERE mod(open, CASE WHEN open < 200 THEN 1 WHEN open < 500 THEN 2 WHEN open < 2000 THEN 5
                                                                    WHEN open < 5000 THEN 10 ELSE 25 END) <> 0)
                         FROM idx.bar WHERE open IS NOT NULL AND source = 'idx' AND trade_date >= '2020-01-01'""")
        no_src, out_of_range, off_grid = cur.fetchone()
    assert (no_src, out_of_range, off_grid) == (0, 0, 0)


def test_windows_group_nearby_days_and_stay_within_a_year():
    ws = bo.windows([date(2021, 1, 10), date(2021, 1, 25), date(2021, 6, 1)])
    assert ws == [(date(2020, 12, 11), date(2021, 2, 24)), (date(2021, 5, 2), date(2021, 7, 1))]
    long = bo.windows([date(2021, 1, 1) + timedelta(days=20 * k) for k in range(30)])    # a run over 1.6 years
    assert all((b - a).days <= 360 for a, b in long) and len(long) >= 2


def test_fetch_stockbit_pages_parses_and_stops_on_auth():
    import json

    import pytest
    pages = {1: [{"date": (date(2021, 1, 1) + timedelta(days=d)).isoformat(), "open": 100 + d, "close": 101 + d} for d in range(50)],
             2: [{"date": "2021-03-01", "open": 90, "close": 91}]}
    calls = []

    def get(url, h):
        calls.append(url)
        page = int(url.rsplit("page=", 1)[1])
        return 200, json.dumps({"data": {"result": pages.get(page, [])}}).encode()

    got = bo.fetch_stockbit("AAAA", date(2021, 1, 1), date(2021, 2, 1), {}, None, get)
    assert len(got) == 51 and len(calls) == 2 and got[date(2021, 3, 1)].open == 90
    with pytest.raises(bo.StockbitStop):
        bo.fetch_stockbit("AAAA", date(2021, 1, 1), date(2021, 2, 1), {}, None, lambda u, h: (429, b""))


def test_supersede_links_runs_of_one_study_and_the_view_follows_the_chain():
    import os

    import psycopg
    import pytest

    from blackheart_ingest.idx import research_store as rs
    dsn = os.environ.get("INGEST_DB_DSN")
    if not dsn:
        pytest.skip("INGEST_DB_DSN not set")
    try:
        c = psycopg.connect(dsn, connect_timeout=5)
    except Exception as e:
        pytest.skip(f"db unreachable: {e}")
    ids = []
    try:
        for _ in range(3):
            ids.append(rs.record_study(c, "test_supersede", date(2026, 1, 1), params={}, summary={}, names=[]))
        other = rs.record_study(c, "test_supersede_other", date(2026, 1, 1), params={}, summary={}, names=[])
        ids.append(other)
        rs.supersede(c, ids[0], ids[1], "t")
        rs.supersede(c, ids[1], ids[2], "t")
        with c.cursor() as cur:
            cur.execute("SELECT id, current_id FROM idx.study_current WHERE id = ANY(%s) ORDER BY id", (ids[:3],))
            assert [r[1] for r in cur.fetchall()] == [ids[2], ids[2], ids[2]]
        with pytest.raises(ValueError):
            rs.supersede(c, ids[2], other, "t")                 # not the same study
    finally:
        c.rollback()
        with c.cursor() as cur:
            cur.execute("UPDATE idx.study SET superseded_by = NULL WHERE id = ANY(%s)", (ids,))
            cur.execute("DELETE FROM idx.study WHERE id = ANY(%s)", (ids,))
        c.commit()
        c.close()
