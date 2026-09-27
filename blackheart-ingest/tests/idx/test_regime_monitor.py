"""Regime monitor (idx/regime_monitor.py) and the risk report's two-factor scenarios - pure parts."""
from __future__ import annotations

import numpy as np
import pandas as pd

from blackheart_ingest.idx import regime_monitor as rm
from blackheart_ingest.idx import risk


def test_arb_state() -> None:
    assert rm.arb_state(-0.25, 10) == "wide" and rm.arb_state(-0.069, 10) == "narrow" and rm.arb_state(None, 10) == "unknown"
    assert rm.arb_state(-0.07, 3) == "unknown"                                     # too few sessions to judge


def test_hmm_finds_the_volatile_stretch() -> None:
    rng = np.random.default_rng(0)
    x = np.concatenate([rng.normal(0.0005, 0.008, 400), rng.normal(-0.002, 0.03, 60), rng.normal(0.0005, 0.008, 200)])
    h = rm.hmm_filtered(x)
    f = h["filtered"]
    assert h["sd"][1] > h["sd"][0] and f[420:460].mean() > 0.8 and f[:380].mean() < 0.2


def test_two_factor_betas_recover_the_loadings() -> None:
    rng = np.random.default_rng(1)
    n = 300
    mkt = pd.Series(rng.normal(0, 0.01, n))
    spr = pd.Series(rng.normal(0, 0.008, n))
    R = pd.DataFrame({"AAAA": 1.2 * mkt + 0.8 * spr + rng.normal(0, 0.002, n), "BBBB": pd.Series([np.nan] * n)})
    b = risk.two_factor_betas(R, mkt, spr)
    assert abs(b["AAAA"][0] - 1.2) < 0.05 and abs(b["AAAA"][1] - 0.8) < 0.05 and b["BBBB"] == (1.0, 1.0)
