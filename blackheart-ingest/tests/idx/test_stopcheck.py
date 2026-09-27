"""Broker stop vs trail10 (idx/stopcheck.py): the pure trail level, the four statuses, and the alert text."""
from __future__ import annotations

from decimal import Decimal

from blackheart_ingest.idx import stopcheck


def test_trail_rounds_down_to_tick() -> None:
    assert stopcheck.trail_level(Decimal(1000)) == Decimal(900)
    assert stopcheck.trail_level(Decimal(233)) == Decimal(208)          # 209.7, tick 2 in the 200-500 band -> 208
    assert stopcheck.trail_level(Decimal(626)) == Decimal(560)          # 563.4 -> tick 5 -> 560


def test_classify_the_0924_case_is_tight() -> None:
    # DEWI 2026-09-24: a 4 % broker stop under a ~226 price (~217) while trail10 of the peak 226 was ~203
    trail = stopcheck.trail_level(Decimal(226))
    assert trail == Decimal(202)                                        # 203.4, tick 2 -> 202
    assert stopcheck.classify(trail, Decimal(217)) == "tight"
    assert stopcheck.classify(trail, Decimal(205)) == "tight"
    assert stopcheck.classify(trail, Decimal(204)) == "ok"              # one tick over is tolerated
    assert stopcheck.classify(trail, Decimal(202)) == "ok"
    assert stopcheck.classify(trail, Decimal(197)) == "ok"              # within LOOSE (3 %)
    assert stopcheck.classify(trail, Decimal(195)) == "loose"
    assert stopcheck.classify(trail, None) == "missing"


def test_message_gives_a_parseable_command() -> None:
    m = stopcheck.message("trend_live", "ABCD", "tight", Decimal(1350), Decimal(1500), Decimal(1480))
    assert "lebih ketat" in m and "--stop 1350`" in m and "--book trend_live" in m
    m = stopcheck.message("trend_live", "ABCD", "missing", Decimal(1350), None, None)
    assert "belum ada stop" in m and "--stop 1350`" in m
