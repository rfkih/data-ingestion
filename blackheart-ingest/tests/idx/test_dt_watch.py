"""dt_watch (C1 forward paper watch): the pure choice and the cost arithmetic - no database."""
from datetime import date

import pytest

from blackheart_ingest.idx import dt_watch as W


def test_choose_ranks_by_day_return_and_requires_both_prints_up():
    elig = {"AAA": 1000.0, "BBB": 1000.0, "CCC": 1000.0, "DDD": 1000.0}
    prints = {"AAA": (1010, 1050),     # +5 %, first hour up -> pick 1
              "BBB": (990, 1080),      # first hour down -> out
              "CCC": (1005, 1020),     # +2 % -> pick 2
              "DDD": (1010, 995)}      # day down -> out
    picks, placebo = W.choose(elig, prints, date(2026, 9, 28))
    assert [p["code"] for p in picks] == ["AAA", "CCC"]
    assert [p["rank"] for p in picks] == [1, 2]
    assert len(placebo) == 4 and all(p["kind"] == "placebo" for p in placebo)


def test_choose_skips_names_at_the_upper_band():
    elig = {"LOCK": 1000.0, "FREE": 1000.0}
    prints = {"LOCK": (1100, 1250), "FREE": (1010, 1100)}      # 1,250 = +25 % band at Rp 1,000
    picks, _ = W.choose(elig, prints, date(2026, 9, 28))
    assert [p["code"] for p in picks] == ["FREE"]


def test_choose_caps_at_k_and_placebo_is_reproducible():
    elig = {f"N{i:02d}": 1000.0 for i in range(20)}
    prints = {c: (1001, 1000 + 10 * i + 5) for i, c in enumerate(sorted(elig))}
    p1, q1 = W.choose(elig, prints, date(2026, 9, 28))
    p2, q2 = W.choose(elig, prints, date(2026, 9, 28))
    assert len(p1) == W.K and p1[0]["code"] == "N19"
    assert [q["code"] for q in q1] == [q["code"] for q in q2]


def test_net_costs():
    assert W.net(1000, 1000, W.FEES["retail"]) == pytest.approx(-0.0050, abs=2e-4)
    assert W.net(1000, 1000, W.FEES["low"]) == pytest.approx(-0.0040, abs=2e-4)
    assert W.net(1000, 1051, W.FEES["retail"]) > 0


def test_prints_yahoo_reads_the_0900_and_1500_bars():
    # 2026-09-28 09:00 WIB = 02:00 UTC; 15:00 WIB = 08:00 UTC
    base = 1790546400 + 4 * 3600  # 2026-09-28 02:00 UTC
    payload = {"chart": {"result": [{"timestamp": [base, base + 3600, base + 6 * 3600, base + 7 * 3600],
                                     "indicators": {"quote": [{"close": [1010, 1020, 1040, 1045]}]}}]}}
    out = W.prints_yahoo(date(2026, 9, 28), ["AAA"], fetch=lambda code: payload)
    assert out == {"AAA": (1010.0, 1040.0)}


def test_sprt_accepts_backtest_edge_and_rejects_zero():
    import numpy as np
    rng = np.random.default_rng(0)
    edge = W.sprt(list(rng.normal(W.SPRT_MU, W.SPRT_SD, 500)))
    zero = W.sprt(list(rng.normal(0.0, W.SPRT_SD, 500)))
    assert edge["decision"].startswith("H1") and zero["decision"].startswith("H0")
    assert W.sprt([W.SPRT_MU / 2] * 10)["decision"] == "running"      # exactly halfway: the LLR does not move


def test_sprt_counts_only_the_first_cap_sessions():
    late = [W.SPRT_MU / 2] * 500 + [W.SPRT_MU * 10] * 100         # LLR flat for 500 sessions, then a burst that would cross H1
    r = W.sprt(late)
    assert r["decision"] == "undecided" and r["sessions"] == 500
