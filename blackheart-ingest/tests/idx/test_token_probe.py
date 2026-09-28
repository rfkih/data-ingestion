"""Pre-open live check of the Stockbit session (2026-09-28 incident: Stockbit killed the session overnight while its expiry
still read 8 h; the collector found out at 08:40 and the desk missed the opening auction). Pure: no database, no network."""
from __future__ import annotations

from datetime import time as dtime

import httpx
import pytest

from blackheart_ingest.idx import broker, notify, runlog
from blackheart_ingest.idx import scheduler as sch
from blackheart_ingest.idx.feed import collector as fc
from blackheart_ingest.idx.feed import store as fs


class _Resp:
    def __init__(self, status: int, body: object = None) -> None:
        self.status_code, self._body = status, body

    def json(self) -> object:
        if self._body is None:
            raise ValueError("not json")
        return self._body


def _get(resp: _Resp):
    seen = {}

    def get(url, headers=None):
        seen["url"], seen["headers"] = url, headers
        return resp
    return get, seen


def test_probe_reads_the_key_request_like_the_collector() -> None:
    get, seen = _get(_Resp(200, {"data": {"key": "abc"}}))
    assert fc.probe_session("tok", get=get) == ("ok", "websocket key issued")
    assert seen["url"] == fc.KEY_URL and seen["headers"]["Authorization"] == "Bearer tok"
    assert fc.probe_session("tok", get=_get(_Resp(401, {}))[0])[0] == "rejected"
    assert fc.probe_session("tok", get=_get(_Resp(500, {}))[0]) == ("error", "HTTP 500")
    assert fc.probe_session("tok", get=_get(_Resp(200, {"data": {}}))[0]) == ("error", "no key in the answer")
    assert fc.probe_session("tok", get=_get(_Resp(200, None))[0]) == ("error", "answer is not JSON")

    def down(url, headers=None):
        raise httpx.ConnectError("no route")
    assert fc.probe_session("tok", get=down)[0] == "error"


def test_probe_window_is_before_the_collector_connects() -> None:
    assert not sch.in_probe_window(dtime(6, 59))
    assert sch.in_probe_window(dtime(7, 0)) and sch.in_probe_window(dtime(8, 39))
    assert not sch.in_probe_window(dtime(8, 40))                              # the collector owns the session from 08:40
    assert sch.PROBE_TO == dtime(*fc.SESSION_OPEN)


class _Conn:
    commits = 0

    def commit(self) -> None:
        self.commits += 1


@pytest.fixture()
def desk(monkeypatch):
    """Record what the probe does to the bus and the phone."""
    rec = {"alerts": [], "sends": [], "resolved": [], "refreshed": 0, "open": set(), "answers": [], "token": "old"}

    def alert_once(conn, severity, job, message, **kw):
        if message in rec["open"]:
            return False
        rec["open"].add(message)
        rec["alerts"].append((severity, message))
        return True

    def refresh(conn=None):
        rec["refreshed"] += 1
        if rec.get("refresh_error"):
            raise broker.BrokerAuthError("refresh: HTTP 401")
        rec["token"] = "new"
        return "new"

    monkeypatch.setattr(fs, "load_token", lambda conn, provider="stockbit": {"access_token": rec["token"]})
    monkeypatch.setattr(fc, "probe_session", lambda tok, get=None: rec["answers"].pop(0))
    monkeypatch.setattr(broker, "newest_refresh_token", lambda env=None, conn=None: "rt")
    monkeypatch.setattr(broker, "refresh_and_persist", refresh)
    monkeypatch.setattr(runlog, "alert_once", alert_once)
    monkeypatch.setattr(runlog, "resolve", lambda conn, job, like=None: rec["resolved"].append(like) or 1)
    monkeypatch.setattr(notify, "send", lambda text, **kw: rec["sends"].append(text) or True)
    return rec


class _RConn(_Conn):
    rollbacks = 0

    def rollback(self) -> None:
        self.rollbacks += 1


OPEN = lambda: True   # noqa: E731 - the probe window, pinned open for the tests


def test_an_accepted_session_closes_the_probe_alerts(desk) -> None:
    desk["answers"] = [("ok", "websocket key issued")]
    assert sch.preopen_probe(_RConn(), clock=OPEN) == "ok"
    assert desk["resolved"] == ["Stockbit session %"] and not desk["alerts"] and desk["refreshed"] == 0


def test_a_killed_session_is_revived_from_the_refresh_token_first(desk) -> None:
    desk["answers"] = [("rejected", "HTTP 401"), ("ok", "websocket key issued")]
    assert sch.preopen_probe(_RConn(), clock=OPEN) == "ok"
    assert desk["refreshed"] == 1 and desk["token"] == "new" and not desk["alerts"] and not desk["sends"]


def test_a_dead_pair_raises_one_critical_alert_then_pushes_every_run(desk) -> None:
    desk["refresh_error"] = True
    desk["answers"] = [("rejected", "HTTP 401")]
    assert sch.preopen_probe(_RConn(), clock=OPEN) == "rejected"
    assert desk["alerts"] == [("critical", sch.PROBE_ALERT)] and not desk["sends"]     # the alert itself pushes (policy: feed critical)
    desk["answers"] = [("rejected", "HTTP 401")]
    assert sch.preopen_probe(_RConn(), clock=OPEN) == "rejected"
    assert desk["sends"] == [sch.PROBE_ALERT] and len(desk["alerts"]) == 1                # then a push on every run, no new row
    assert "paste" in sch.PROBE_ALERT and "08:45" in sch.PROBE_ALERT and "Alerts > Data feed" in sch.PROBE_ALERT
    assert "More >" not in sch.PROBE_ALERT                                   # the phone has no More tab since 2026-09-26


def test_a_network_error_warns_once_without_nagging(desk) -> None:
    desk["answers"] = [("error", "ConnectError: no route")]
    assert sch.preopen_probe(_RConn(), clock=OPEN) == "error"
    assert desk["alerts"] == [("warning", sch.PROBE_UNCHECKED)] and not desk["sends"] and desk["refreshed"] == 0


def test_the_critical_probe_alert_reaches_a_phone_under_the_alert_policy() -> None:
    from blackheart_ingest.idx import alert_policy
    row = {"severity": "critical", "job": "feed", "message": sch.PROBE_ALERT}
    assert alert_policy.push_now(row)


def test_no_second_refresh_when_the_guard_already_failed_one(desk) -> None:
    """A refresh token the guard just spent (or found dead) must not be POSTed again: rotation reuse can revoke the family."""
    desk["answers"] = [("rejected", "HTTP 401")]
    assert sch.preopen_probe(_RConn(), may_refresh=False, clock=OPEN) == "rejected"
    assert desk["refreshed"] == 0 and desk["alerts"] == [("critical", sch.PROBE_ALERT)]


def test_a_token_stored_meanwhile_is_judged_instead_of_refreshing(desk, monkeypatch) -> None:
    tokens = iter([{"access_token": "old"}, {"access_token": "pasted"}])
    monkeypatch.setattr(fs, "load_token", lambda conn, provider="stockbit": next(tokens))
    desk["answers"] = [("rejected", "HTTP 401"), ("ok", "websocket key issued")]
    assert sch.preopen_probe(_RConn(), clock=OPEN) == "ok" and desk["refreshed"] == 0


def test_the_probe_never_touches_stockbit_after_the_window(desk) -> None:
    desk["answers"] = [("ok", "should not be asked")]
    assert sch.preopen_probe(_RConn(), clock=lambda: False) == "late" and desk["answers"]   # nothing consumed


def test_a_failed_refresh_rolls_back_before_alerting(desk) -> None:
    desk["refresh_error"] = True
    desk["answers"] = [("rejected", "HTTP 401")]
    c = _RConn()
    assert sch.preopen_probe(c, clock=OPEN) == "rejected" and c.rollbacks == 1


def test_the_unchecked_warning_is_actionable_so_the_operator_sees_it() -> None:
    from blackheart_ingest.idx import alert_policy
    assert alert_policy.actionable({"severity": "warning", "job": "feed", "message": sch.PROBE_UNCHECKED})
