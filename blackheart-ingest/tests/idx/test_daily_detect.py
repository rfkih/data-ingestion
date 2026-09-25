"""Corporate-action detection in jobs/daily against a fake connection (no DB): a day whose prior session is missing
writes no actions and leaves adj_factor alone - the 2026-09-21 artefact (641 false resets vs the 09-17 close)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from blackheart_ingest.idx import runlog
from blackheart_ingest.idx.jobs import daily


class _Cur:
    def __init__(self, conn):
        self.conn, self.rowcount, self._rows = conn, 0, []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.conn.sql.append(sql)
        self.rowcount = 1
        if "DISTINCT ON (code)" in sql:
            self._rows = self.conn.prior
        elif "max(trade_date)" in sql:
            self._rows = [self.conn.last]
        elif "idx.alert" in sql:
            self._rows = []

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else (1,)


class _Conn:
    def __init__(self, prior, last):
        self.prior, self.last, self.sql = prior, last, []

    def cursor(self, **kw):
        return _Cur(self)

    def commit(self):
        pass


def _day(n_moved: int):
    prior = [(f"C{i:03}", date(2026, 9, 17), Decimal("100"), 1000) for i in range(100)]
    today = [{"code": f"C{i:03}", "previous": Decimal("103") if i < n_moved else Decimal("100"), "listed_shares": 1000}
             for i in range(100)]
    return prior, today


def _writes(conn):
    return [s for s in conn.sql if "INSERT INTO idx.corporate_action" in s or "SET adj_factor" in s]


def test_missing_prior_session_writes_no_action(monkeypatch) -> None:
    monkeypatch.setattr(runlog, "alert", lambda *a, **k: 1)
    prior, today = _day(60)
    conn = _Conn(prior, (date(2026, 9, 17), date(2026, 9, 18)))     # 09-18 has fallback bars but no summary
    r = runlog.RunResult("daily", "2026-09-21")
    assert daily._detect_actions(conn, date(2026, 9, 21), today, r) == 0
    assert _writes(conn) == [] and r.warnings
    conn = _Conn(prior, (date(2026, 9, 17), date(2026, 9, 17)))     # no bars either: 60 of 100 reset
    assert daily._detect_actions(conn, date(2026, 9, 21), today, runlog.RunResult("daily", "x")) == 0
    assert _writes(conn) == []


def test_genuine_action_still_detected() -> None:
    prior, today = _day(1)
    conn = _Conn(prior, (date(2026, 9, 18), date(2026, 9, 18)))
    r = runlog.RunResult("daily", "2026-09-21")
    assert daily._detect_actions(conn, date(2026, 9, 21), today, r) == 1
    assert len(_writes(conn)) == 2 and not r.warnings
