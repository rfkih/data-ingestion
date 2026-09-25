"""stock_state: each state from a synthetic price path, the priority between states, and the streak."""
from __future__ import annotations

import numpy as np
import pandas as pd

from blackheart_ingest.idx import stock_state as ss

N = 320


def _frame(path: np.ndarray, vol: np.ndarray | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    idx = pd.bdate_range("2025-01-01", periods=len(path))
    v = vol if vol is not None else np.full(len(path), 1_000_000.0)
    return pd.DataFrame({"X": path}, index=idx), pd.DataFrame({"X": v}, index=idx)


def _last(path, vol=None) -> str:
    st, _ = ss.classify_panel(*_frame(np.asarray(path, float), vol))
    return st["X"].iloc[-1]


def test_uptrend_and_downtrend():
    assert _last(100 * 1.003 ** np.arange(N)) == "uptrend"
    assert _last(100 * 0.997 ** np.arange(N)) == "downtrend"


def test_sideways_is_a_flat_noisy_base():
    rng = np.random.default_rng(1)
    path = 100 + rng.normal(0, 1.5, N)                     # ~+-5 % around 100, no drift: width < 25 %, ER small
    assert _last(path) == "sideways"


def test_breakout_needs_the_high_the_average_and_the_volume():
    rng = np.random.default_rng(2)
    path = np.concatenate([100 * 1.001 ** np.arange(N - 1), [0.0]])
    path[:-1] += rng.normal(0, 0.3, N - 1)
    path[-1] = path[:-1].max() * 1.05
    vol = np.full(N, 1_000_000.0)
    assert _last(path, vol) != "breakout"                  # a new high on normal volume is not the rule's breakout
    vol[-1] = 3_000_000.0
    assert _last(path, vol) == "breakout"


def test_breakout_out_of_a_base_is_flagged_and_wins_over_sideways():
    rng = np.random.default_rng(3)
    path = np.concatenate([100 * 1.002 ** np.arange(200), 150 + rng.normal(0, 0.8, N - 201), [0.0]])
    path[-1] = path[:-1][-60:].max() * 1.04
    vol = np.full(N, 1_000_000.0)
    vol[-1] = 4_000_000.0
    st, m = ss.classify_panel(*_frame(path, vol))
    assert st["X"].iloc[-1] == "breakout"
    assert bool(m["from_base"]["X"].iloc[-1])


def test_short_history_is_transition():
    assert _last(100 * 1.003 ** np.arange(120)) == "transition"


def test_streak_counts_the_tail():
    assert ss.streak(pd.Series(["a", "b", "b", "b"])) == 3
    assert ss.streak(pd.Series(["a", None, "a"])) == 2
    assert ss.streak(pd.Series([], dtype=object)) == 0
