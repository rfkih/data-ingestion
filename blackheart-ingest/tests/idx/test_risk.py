"""Book risk report: the pure arithmetic on offline fixtures (no database)."""
from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd
import pytest

from blackheart_ingest.idx import risk


# ---------------------------------------------------------------------------
# VaR / ES
# ---------------------------------------------------------------------------
def test_parametric_two_asset_var_matches_closed_form() -> None:
    s1, s2, rho = 0.02, 0.03, 0.5
    cov = np.array([[s1 ** 2, rho * s1 * s2], [rho * s1 * s2, s2 ** 2]])
    w = np.array([0.5, 0.5])
    sigma = math.sqrt(0.25 * s1 ** 2 + 0.25 * s2 ** 2 + 2 * 0.25 * rho * s1 * s2)      # 0.0217945
    var, es, sig = risk.parametric_var_es(w, cov, 0.95, 1)
    assert sig == pytest.approx(sigma)
    assert var == pytest.approx(1.6448536 * sigma, rel=1e-6)                         # 3.585 %
    assert es == pytest.approx(sigma * 0.1031356 / 0.05, rel=1e-5)                    # phi(z)/(1-a)
    var10, _, _ = risk.parametric_var_es(w, cov, 0.99, 10)
    assert var10 == pytest.approx(2.3263479 * sigma * math.sqrt(10), rel=1e-6)


def test_historical_two_asset_var_and_es() -> None:
    r = np.arange(-50, 50) / 1000.0                          # 100 equally spaced daily returns
    R = np.column_stack([r, r])                              # two identical assets, 50/50 -> portfolio = r
    port = R @ np.array([0.5, 0.5])
    var, es = risk.hist_var_es(port, 0.95)
    assert var == pytest.approx(0.04505)                     # linear interpolation between the 5th and 6th worst
    assert es == pytest.approx(0.048)                        # mean of -5.0 .. -4.6 %


def test_ledoit_wolf_is_a_valid_shrunk_covariance() -> None:
    rng = np.random.default_rng(1)
    x = rng.normal(0, 0.02, size=(250, 6))
    cov, shrink = risk.ledoit_wolf(x)
    assert 0.0 <= shrink <= 1.0
    assert np.allclose(cov, cov.T)
    assert np.linalg.eigvalsh(cov).min() > 0
    s = np.cov(x, rowvar=False, ddof=0)
    mu = np.trace(s) / 6
    assert np.allclose(cov, (1 - shrink) * s + shrink * mu * np.eye(6))
    try:                                                      # same estimator as sklearn when it is installed
        from sklearn.covariance import LedoitWolf
    except ImportError:
        return
    assert shrink == pytest.approx(LedoitWolf().fit(x).shrinkage_)


# ---------------------------------------------------------------------------
# Euler decomposition, concentration
# ---------------------------------------------------------------------------
def test_euler_contributions_sum_to_portfolio_sigma() -> None:
    rng = np.random.default_rng(7)
    x = rng.normal(0, 0.02, size=(250, 5)) + rng.normal(0, 0.01, size=(250, 1))
    cov, _ = risk.ledoit_wolf(x)
    w = np.array([0.3, 0.2, 0.15, 0.1, 0.05])                 # 80 % invested, 20 % cash
    rc = risk.euler_contributions(w, cov)
    assert rc.sum() == pytest.approx(math.sqrt(w @ cov @ w))
    assert risk.effective_n(np.ones(4)) == pytest.approx(4.0)
    assert risk.effective_n(np.array([1.0, 0, 0])) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# liquidity
# ---------------------------------------------------------------------------
def test_days_to_exit_and_liquidation_cost_arithmetic() -> None:
    assert risk.days_to_exit(1e9, 2e9, 0.10) == pytest.approx(5.0)
    assert risk.days_to_exit(1e9, 2e9, 0.20) == pytest.approx(2.5)
    assert math.isinf(risk.days_to_exit(1e9, 0.0, 0.10))
    # Rp 100 M against Rp 10 B ADV, sigma 2 %, half-spread 0.5 %: 1e8 * (0.005 + 0.7 * 0.02 * sqrt(0.01)) = Rp 640 k
    assert risk.liquidation_cost(1e8, 1e10, 0.02, 0.005) == pytest.approx(640_000)
    assert [risk.idx_tick(p) for p in (150, 300, 1500, 3000, 9000)] == [1, 2, 5, 10, 25]


# ---------------------------------------------------------------------------
# the whole report on a synthetic market
# ---------------------------------------------------------------------------
def _fixture(codes: list[str], shares: list[float], cash: float = 50e6) -> risk.Inputs:
    days = pd.bdate_range("2020-01-01", "2026-09-25")
    rng = np.random.default_rng(3)
    m = rng.normal(0.0003, 0.01, len(days))
    m[(days >= "2020-03-02") & (days <= "2020-03-20")] = -0.03              # the crash
    comp = 6000 * np.cumprod(1 + m)
    index = pd.DataFrame({"trade_date": days.date, "index_code": "COMPOSITE", "close": comp})
    bars = []
    for c in codes:
        start = 0 if c != "NEWB" else len(days) - 30                         # NEWB listed 30 sessions ago
        r = 1.5 * m + (rng.normal(0, 0.01, len(days)) if c != "BETA" else 0)  # BETA = exactly 1.5 x market
        px = 1000 * np.cumprod(1 + r)
        bars.append(pd.DataFrame({"code": c, "trade_date": days.date[start:], "adj_close": px[start:]}))
    bars_df = pd.concat(bars)
    last = bars_df.groupby("code").tail(1).set_index("code")["adj_close"]
    pos = pd.DataFrame({"code": codes, "shares": shares, "close": [last[c] for c in codes],
                        "sector": ["E. Consumer Cyclicals"] * len(codes)})
    liq = pd.DataFrame({"code": codes, "adv20": [5e9] * len(codes), "bid": [last[c] - 5 for c in codes],
                        "offer": [last[c] + 5 for c in codes], "close": [last[c] for c in codes]})
    return risk.Inputs(book="t", as_of=date(2026, 9, 25), cash=cash, positions=pos, bars=bars_df, index=index, liquidity=liq)


def test_report_end_to_end_beta_euler_flags_and_stress() -> None:
    rep = risk.compute_report(_fixture(["BETA", "NOIS", "NEWB"], [20_000, 20_000, 10_000]))
    assert rep["status"] == "ok" and rep["n_positions"] == 3
    by = {p["code"]: p for p in rep["positions"]}
    assert by["BETA"]["beta"] == pytest.approx(1.5, rel=1e-6)
    assert "proxy COMPOSITE" in by["NEWB"]["flags"][0]                        # 29 own returns < 60 -> proxied
    assert rep["euler_sum_rc"] == pytest.approx(rep["var"]["sigma_1d"])
    assert sum(p["rc_pct"] for p in rep["positions"]) == pytest.approx(1.0)
    assert rep["nav"] == pytest.approx(rep["cash"] + rep["gross"])
    assert rep["beta"] == pytest.approx(sum(p["weight"] * p["beta"] for p in rep["positions"]))
    names = [s["name"] for s in rep["stress"]]
    assert names[:3] == ["COVID 2020", "2025 drawdown", "worst 5-day"]
    covid = rep["stress"][0]
    assert covid["composite"] < -0.3 and covid["pnl"] < 0 and covid["proxied"] == ["NEWB"]
    shock = rep["stress"][-1]
    assert shock["pnl"] == pytest.approx(sum(p["value"] * p["beta"] * -0.10 for p in rep["positions"]))
    for a in ("95", "99"):
        v = rep["var"][a]
        assert v["hist_es_1d"] >= v["hist_1d"] > 0 and v["param_es_1d"] >= v["param_1d"] > 0
    assert rep["var"]["99"]["param_1d"] > rep["var"]["95"]["param_1d"]
    assert by["BETA"]["dte_10"] == pytest.approx(by["BETA"]["value"] / (0.1 * 5e9))
    text = risk.render(rep)
    assert "VAR / ES" in text and "STRESS" in text and "NEWB: proxy" in text


def test_flat_book_is_a_clean_report() -> None:
    inp = risk.Inputs(book="flat", as_of=date(2026, 9, 25), cash=20e6,
                      positions=pd.DataFrame(columns=["code", "shares", "close", "sector"]),
                      bars=pd.DataFrame(columns=["code", "trade_date", "adj_close"]),
                      index=pd.DataFrame(columns=["trade_date", "index_code", "close"]),
                      liquidity=pd.DataFrame(columns=["code", "adv20", "bid", "offer", "close"]))
    rep = risk.compute_report(inp)
    assert rep["status"] == "flat" and rep["nav"] == 20e6 and rep["n_positions"] == 0 and rep["gross"] == 0
    assert "flat" in risk.render(rep)


def test_breaches_flag_each_limit_and_ignore_a_flat_book() -> None:
    assert risk.breaches({"status": "flat"}) == []
    ok = {"status": "ok", "n_positions": 5, "eff_n_risk": 4.5, "var": {"99": {"hist_1d": 0.02}},
          "max_name": {"code": "AAAA", "weight": 0.12}, "max_sector": {"sector": "G. Financials", "weight": 0.30},
          "positions": [{"code": "AAAA", "dte_10": 0.1, "flags": []}],
          "stress": [{"name": "COMPOSITE -10% via beta", "pnl_pct": -0.05}]}
    assert risk.breaches(ok) == []
    bad = dict(ok, eff_n_risk=2.0, var={"99": {"hist_1d": 0.05}}, max_name={"code": "AAAA", "weight": 0.25},
               max_sector={"sector": "G. Financials", "weight": 0.45},
               positions=[{"code": "AAAA", "dte_10": 4.0, "flags": ["proxy"]}],
               stress=[{"name": "COMPOSITE -10% via beta", "pnl_pct": -0.09}])
    got = risk.breaches(bad)
    assert len(got) == 7
    assert any("VaR99" in x for x in got) and any("AAAA is 25%" in x for x in got) and any("proxied: AAAA" in x for x in got)
