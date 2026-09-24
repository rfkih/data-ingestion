"""An issued ticket that still needs the operator (stage 2 of the live loop; rewritten after the 2026-09-23 review).

The bug this guards against: measured in calendar days, EVERY overnight ticket read as "drafted 1d ago on stale prices"
the morning it was meant to be worked. Staleness is now counted in sessions that have fully closed, per mode."""
from __future__ import annotations

from datetime import date

from blackheart_ingest.idx import ticket

TUE, WED, THU, FRI = date(2026, 9, 22), date(2026, 9, 23), date(2026, 9, 24), date(2026, 9, 25)


def _lines(*st: str) -> list[dict]:
    return [{"status": s} for s in st]


# ---- next-session modes (trend / rebalance / exits): dated at a close, worked the next morning ---------------------
def test_trend_ticket_the_morning_after_is_waiting_not_stale() -> None:
    s = ticket.stale_state(7, "trend_live", "trend", TUE, _lines("open", "open"), WED, sessions_passed=0)
    assert s and s["kind"] == "waiting" and s["stale"] is False
    assert "for this session" in s["why"] and "stale" not in s["why"]


def test_trend_ticket_is_stale_once_its_session_has_closed() -> None:
    s = ticket.stale_state(7, "trend_live", "trend", TUE, _lines("open"), THU, sessions_passed=1)
    assert s["stale"] is True and "1 session(s) ago" in s["why"]
    s2 = ticket.stale_state(7, "trend_live", "trend", TUE, _lines("open"), FRI, sessions_passed=2)
    assert "2 session(s) ago" in s2["why"]


def test_rebalance_and_exits_follow_the_next_session_rule() -> None:
    for mode in ("rebalance", "exits", ""):
        assert ticket.stale_state(1, "live", mode, TUE, _lines("open"), WED, 0)["stale"] is False
        assert ticket.stale_state(1, "live", mode, TUE, _lines("open"), THU, 1)["stale"] is True


# ---- same-day modes (gapfade): dated the morning it is for ----------------------------------------------------------
def test_gapfade_ticket_is_fine_on_its_day_and_stale_the_next() -> None:
    assert ticket.stale_state(9, "paper_gapfade", "gapfade", WED, _lines("open"), WED, 0)["stale"] is False
    s = ticket.stale_state(9, "paper_gapfade", "gapfade", WED, _lines("open"), THU, 0)
    assert s["stale"] is True and "never worked" in s["why"]


# ---- finish, regardless of age -----------------------------------------------------------------------------------
def test_all_lines_filled_but_ticket_open_asks_to_close() -> None:
    s = ticket.stale_state(103, "trend_live", "trend", date(2026, 9, 17), _lines("filled", "filled"), WED, 4)
    assert s["kind"] == "finish" and s["filled"] == 2 and "close the ticket" in s["why"]


def test_skipped_counts_as_done_not_waiting() -> None:
    assert ticket.stale_state(9, "live", "trend", WED, _lines("filled", "skipped"), WED, 0)["kind"] == "finish"


def test_a_ticket_with_no_lines_is_not_chased() -> None:
    assert ticket.stale_state(10, "live", "trend", WED, [], WED, 0) is None


# ---- the dedupe key ----------------------------------------------------------------------------------------------
def test_key_is_stable_across_days_so_alert_once_can_dedupe() -> None:
    k1 = ticket.stale_state(7, "trend_live", "trend", TUE, _lines("open"), WED, 0)["key"]
    k2 = ticket.stale_state(7, "trend_live", "trend", TUE, _lines("open"), FRI, 2)["key"]
    assert k1 == k2 == "#7 (trend_live) waiting"
    assert ticket.stale_state(7, "trend_live", "trend", TUE, _lines("filled"), FRI, 2)["key"] == "#7 (trend_live) finish"
