"""The self-learning prediction desk (idx/ml): metrics, tick prices, the promotion rule, the session grid, the minute and
daily feature builders on synthetic tapes, and a read-only smoke against the desk's tables when a database is around."""
from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import psycopg
import pytest

from blackheart_ingest.idx.ml import common, daily, intraday, loop
from blackheart_ingest.idx.ml.spec import DAILY, HORIZONS, INTRADAY, of_kind

WIB = ZoneInfo("Asia/Jakarta")


# ---- spec --------------------------------------------------------------------------------------------------------------
def test_horizons_cover_one_minute_to_one_year() -> None:
    assert [h.key for h in INTRADAY] == ["1m", "10m", "30m", "60m"]
    assert [h.key for h in DAILY] == ["1d", "5d", "20d", "60d", "120d", "250d"]
    assert HORIZONS["20d"].label.startswith("1 bulan") and HORIZONS["250d"].label.startswith("1 tahun")
    assert len(of_kind("all")) == 10


# ---- metrics -------------------------------------------------------------------------------------------------------------
def test_auc_is_rank_based_and_handles_one_class() -> None:
    y = np.array([0, 0, 1, 1, 1, 0])
    assert common.auc(y, np.array([0.1, 0.2, 0.8, 0.9, 0.7, 0.3])) == 1.0
    assert common.auc(y, np.array([0.9, 0.8, 0.1, 0.2, 0.3, 0.7])) == 0.0
    assert abs(common.auc(y, np.array([0.5, 0.5, 0.5, 0.5, 0.5, 0.5])) - 0.5) < 1e-9
    assert np.isnan(common.auc(np.ones(5), np.arange(5)))


def test_hit_rate_ignores_zero_moves_and_reports_the_majority_base() -> None:
    hit, base, n = common.hit_rate(np.array([True, True, False, True]), np.array([0.01, -0.01, -0.02, 0.0]))
    assert n == 3 and abs(hit - 2 / 3) < 1e-9 and abs(base - 2 / 3) < 1e-9


def test_metrics_for_each_task_has_a_primary() -> None:
    y = np.array([1, 0, 1, 0, 1, 1, 0, 0, 1, 0, 1, 0], dtype=float)
    p = np.array([0.9, 0.2, 0.8, 0.3, 0.7, 0.6, 0.4, 0.1, 0.55, 0.45, 0.65, 0.35])
    m = common.metrics_for("dir", y, p)
    assert m["primary"] == m["auc"] == 1.0 and m["hit"] == 1.0
    r = np.linspace(-0.05, 0.05, 12)
    m = common.metrics_for("ret", r, r * 0.5 + 0.001)
    assert m["primary"] == m["ic"] and m["ic"] > 0.99 and m["mae_bps"] < m["naive_mae_bps"]


# ---- prices --------------------------------------------------------------------------------------------------------------
def test_price_from_lands_on_the_tick() -> None:
    assert common.price_from(1000.0, 0.0123) == 1010.0          # Rp 5 tick under 2,000
    assert common.price_from(6250.0, -0.02) == 6125.0           # Rp 25 tick above 5,000
    assert common.price_from(150.0, 0.03) == 155.0              # Rp 1 tick under 200
    assert np.isnan(common.price_from(float("nan"), 0.01))


# ---- the promotion rule -----------------------------------------------------------------------------------------------------
def _c(name: str, p: float, days_old: int = 0, mid: int | None = None) -> common.Contender:
    return common.Contender(name, p, date(2026, 9, 24) - timedelta(days=days_old), mid)


def test_choose_first_champion_is_the_best_challenger() -> None:
    chosen, why = common.choose([_c("refresh", 0.61, mid=1), _c("tune", 0.63, mid=2)], date(2026, 9, 24))
    assert chosen.name == "tune" and "first champion" in why


def test_choose_clear_winner_beats_champion() -> None:
    chosen, _ = common.choose([_c("champion", 0.60, 10), _c("refresh", 0.605, mid=1), _c("tune", 0.62, mid=2)], date(2026, 9, 24))
    assert chosen.name == "tune"


def test_choose_refresh_wins_ties_because_it_saw_more_data() -> None:
    chosen, why = common.choose([_c("champion", 0.600, 10), _c("refresh", 0.598, mid=1), _c("tune", 0.590, mid=2)], date(2026, 9, 24))
    assert chosen.name == "refresh" and "newer data" in why


def test_choose_keeps_a_champion_that_is_clearly_better() -> None:
    chosen, why = common.choose([_c("champion", 0.650, 10), _c("refresh", 0.630, mid=1), _c("tune", 0.640, mid=2)], date(2026, 9, 24))
    assert chosen.name == "champion" and "kept" in why


def test_choose_replaces_a_stale_champion_unless_the_challenger_is_much_worse() -> None:
    chosen, why = common.choose([_c("champion", 0.650, 60), _c("refresh", 0.630, mid=1)], date(2026, 9, 24))
    assert chosen.name == "refresh" and "d old" in why
    chosen, _ = common.choose([_c("champion", 0.650, 60), _c("refresh", 0.600, mid=1)], date(2026, 9, 24))
    assert chosen.name == "champion"


def test_choose_ignores_challengers_without_a_metric() -> None:
    chosen, _ = common.choose([_c("champion", 0.60, 1), _c("refresh", float("nan"), mid=1)], date(2026, 9, 24))
    assert chosen.name == "champion"


def test_perturb_moves_two_knobs_one_notch_within_the_grid() -> None:
    rng = np.random.default_rng(1)
    base = common.BASE_PARAMS["dir"]
    for _ in range(20):
        p = common.perturb(base, rng)
        changed = [k for k in common.TUNE_SPACE if p.get(k) != base.get(k)]
        assert 1 <= len(changed) <= 2
        for k in changed:
            grid = common.TUNE_SPACE[k]
            assert p[k] in grid and abs(grid.index(p[k]) - grid.index(base[k])) == 1


def test_window_bounds_take_the_last_n_days() -> None:
    days = pd.Series(pd.to_datetime(["2026-01-05"] * 3 + ["2026-01-06"] * 2 + ["2026-01-07", "2026-01-08", "2026-01-09", "2026-01-12", "2026-01-13"]))
    lo, hi = common.window_bounds(days, 2, min_fit_days=3)
    assert pd.Timestamp(lo) == pd.Timestamp("2026-01-12") and pd.Timestamp(hi) == pd.Timestamp("2026-01-13")
    with pytest.raises(RuntimeError):
        common.window_bounds(days, 5, min_fit_days=5)


# ---- the session grid ---------------------------------------------------------------------------------------------------------
def test_session_grid_has_the_two_sessions_and_a_short_friday() -> None:
    g = intraday.session_grid(date(2026, 9, 23))            # Wednesday
    assert len(g) == 180 + 150 and g[0].time() == time(9, 0) and g[179].time() == time(11, 59) and g[180].time() == time(13, 30)
    f = intraday.session_grid(date(2026, 9, 25))            # Friday
    assert len(f) == 150 + 120 and f[149].time() == time(11, 29) and f[150].time() == time(14, 0)
    assert len(intraday.session_grid(date(2026, 9, 26))) == 0


def test_grid_position_is_none_in_the_break_and_after_the_close() -> None:
    d = date(2026, 9, 23)
    assert intraday.grid_position(datetime.combine(d, time(10, 15, 30), tzinfo=WIB))[0] == 75
    assert intraday.grid_position(datetime.combine(d, time(12, 30), tzinfo=WIB)) is None
    assert intraday.grid_position(datetime.combine(d, time(13, 30, 5), tzinfo=WIB))[0] == 180
    assert intraday.grid_position(datetime.combine(d, time(16, 5), tzinfo=WIB)) is None
    assert intraday.grid_position(datetime.combine(d, time(8, 59), tzinfo=WIB)) is None


def _minute_tape(d: date, code: str = "BBCA", n: int = 200, drift: float = 0.0002) -> pd.DataFrame:
    g = intraday.session_grid(d)[:n]
    px = 6000 * np.exp(np.cumsum(np.full(n, drift)))
    px = np.round(px / 25) * 25
    return pd.DataFrame({"minute": g, "code": code, "open": px, "high": px + 25, "low": px - 25, "close": px, "volume": 1000.0,
                         "value": px * 1000, "n_trades": 10.0, "buy_vol": 600.0, "sell_vol": 400.0, "bid_px": px - 25, "bid_vol": 5000.0,
                         "off_px": px + 25, "off_vol": 3000.0, "bid_total": 90000.0, "off_total": 60000.0, "n_updates": 4.0,
                         "bid_vol3": 12000.0, "off_vol3": 8000.0})


def test_minute_features_use_the_mid_and_label_never_crosses_the_close() -> None:
    d = date(2026, 9, 23)
    P = intraday._one_day(_minute_tape(d), d)
    assert len(P) == 200 and set(intraday.FEATURES) - {"mom20", "vol20", "lvalue20", "dist_ma200", "day_ret", "gap", "day_pos", "day_range"} <= set(P.columns)
    row = P.iloc[100]
    assert row["close"] == (row["last"] - 25 + row["last"] + 25) / 2          # the mid of a symmetric book is the last trade here
    assert abs(row["obi1"] - 0.25) < 1e-9 and abs(row["obi3"] - 0.2) < 1e-9 and abs(row["obi"] - 0.2) < 1e-9
    assert row["spread_t"] == 2.0 and abs(row["imb5"] - 0.2) < 1e-9
    assert P["fwd_1m"].notna().sum() == 199 and P["fwd_60m"].notna().sum() == 140    # 60 rows at the end have no label
    assert P["fwd_60m"].dropna().gt(0).mean() > 0.9                                   # the tape drifts up (1-minute moves round to zero on the Rp 25 tick)


def test_minute_panel_attaches_the_previous_bar_context_not_the_same_day() -> None:
    d = date(2026, 9, 23)
    P = intraday._one_day(_minute_tape(d), d)
    P["d"] = d
    ctx = pd.DataFrame({"code": ["BBCA", "BBCA"], "d": [date(2026, 9, 22), date(2026, 9, 23)], "prev_close": [5900.0, 9999.0],
                        "mom20": [0.05, 0.99], "vol20": [0.01, 0.99], "lvalue20": [25.0, 99.0], "dist_ma200": [0.1, 0.99]})
    Q = intraday._attach_context(P, ctx)
    assert (Q["prev_close"] == 5900.0).all() and (Q["mom20"] == 0.05).all()          # the 09-23 bar is not known during 09-23
    assert abs(Q["gap"].iloc[0] - (Q["first_close"].iloc[0] / 5900 - 1)) < 1e-9


# ---- daily features ----------------------------------------------------------------------------------------------------------
def _bar_tape(n: int = 320) -> pd.DataFrame:
    days = pd.bdate_range("2025-06-02", periods=n)
    rows = []
    rng = np.random.default_rng(7)
    for code, start in (("AAAA", 1000.0), ("BBBB", 500.0)):
        px = start * np.exp(np.cumsum(rng.normal(0.0005, 0.02, n)))
        for i, d in enumerate(days):
            c = round(px[i] / 5) * 5
            rows.append({"code": code, "d": d, "open": c * 0.99, "high": c * 1.02, "low": c * 0.98, "close": c, "volume": 1e6, "value": c * 1e6,
                         "adj": 1.0, "frequency": 500.0, "bid": c - 5, "bid_vol": 1e5, "offer": c + 5, "offer_vol": 8e4, "fbuy": 1e4, "fsell": 5e3,
                         "listed": 1e9, "tradeable": 5e8, "weight": 0.01, "nonreg_value": 0.0})
    return pd.DataFrame(rows)


def test_daily_price_features_and_labels_are_shift_consistent() -> None:
    B = daily.price_features(_bar_tape())
    B["sector"] = 1.0
    B = daily.cross_section(B)
    B = daily.labels(B)
    a = B[B["code"] == "AAAA"].reset_index(drop=True)
    i = 300
    assert abs(a.loc[i, "ret20"] - np.log(a.loc[i, "close"] / a.loc[i - 20, "close"])) < 1e-9
    assert abs(a.loc[i, "fwd_5d"] - np.log(a.loc[i + 5, "close"] / a.loc[i, "close"])) < 1e-9
    assert a["fwd_250d"].notna().sum() == len(a) - 250 and a["fwd_1d"].isna().sum() == 1
    assert abs(a.loc[i, "spread_bps"] - 10 / a.loc[i, "close"] * 1e4) < 1e-9
    assert abs(a.loc[i, "bo_imb"] - (1e5 - 8e4) / 1.8e5) < 1e-9
    assert 0 <= a.loc[i, "xs_r20"] <= 1 and a.loc[i, "breadth"] in (0.0, 0.5, 1.0)
    assert a.loc[i, "lmcap"] == pytest.approx(np.log(a.loc[i, "close"] * 1e9))


def test_daily_labels_and_fit_rows_respect_the_liquidity_floor() -> None:
    B = daily.price_features(_bar_tape())
    B["sector"] = 1.0
    B = daily.labels(daily.cross_section(B))
    for c in daily.FEATURES:
        if c not in B:
            B[c] = np.nan
    assert len(daily.fit_rows(B)) > 0
    B2 = B.copy()
    B2["value20"] = 1e6
    assert len(daily.fit_rows(B2)) == 0


# ---- the loop's pure parts ---------------------------------------------------------------------------------------------------
def test_label_for_dir_drops_zero_moves_and_ret_is_clipped() -> None:
    P = pd.DataFrame({"fwd_1d": [0.0, 0.01, -0.02, np.nan, 3.0]})
    R, y = loop._label(P, HORIZONS["1d"], "dir", "daily")
    assert len(R) == 3 and y.tolist() == [1.0, 0.0, 1.0]
    R, y = loop._label(P, HORIZONS["1d"], "ret", "daily")
    assert len(R) == 4 and y.max() == 1.0


def test_render_scorecard_handles_missing_numbers() -> None:
    txt = loop.render_scorecard([{"horizon": "1d", "window_days": 20, "n": 100, "hit_rate": 0.52, "base_hit": 0.51, "auc": None,
                                  "ic": float("nan"), "mae_bps": 120.0, "naive_mae_bps": 118.0}])
    assert "52.0" in txt and "51.0" in txt and "120.0" in txt and "-" in txt


# ---- second pass: blocks, purge, excess labels, calibration ------------------------------------------------------------------
def test_blocks_are_consecutive_and_shrink_when_history_is_short() -> None:
    days = pd.Series(pd.to_datetime([f"2026-01-{d:02d}" for d in range(1, 21)]))     # 20 distinct days
    b = common.blocks(days, n_val=4, k=3, min_fit_days=5)
    assert [(pd.Timestamp(a).day, pd.Timestamp(z).day) for a, z in b] == [(9, 12), (13, 16), (17, 20)]
    b = common.blocks(days, n_val=4, k=3, min_fit_days=14)                             # room for one block only
    assert len(b) == 1 and pd.Timestamp(b[0][0]).day == 17
    with pytest.raises(RuntimeError):
        common.blocks(days, n_val=10, k=1, min_fit_days=15)


def test_purge_cut_moves_the_fit_boundary_back_by_the_horizon() -> None:
    cal = np.array(pd.to_datetime([f"2026-01-{d:02d}" for d in range(1, 31)]).values)
    assert pd.Timestamp(common.purge_cut(cal, cal[20], 5)) == pd.Timestamp(cal[15])
    assert pd.Timestamp(common.purge_cut(cal, cal[20], 0)) == pd.Timestamp(cal[20])
    assert pd.Timestamp(common.purge_cut(cal, cal[2], 10)) == pd.Timestamp(cal[0])       # never before the calendar


def test_block_plan_fit_rows_never_overlap_the_block_outcomes() -> None:
    days = pd.to_datetime([f"2026-0{m}-{d:02d}" for m in (1, 3, 5) for d in range(1, 31)])       # 90 distinct days
    R = pd.DataFrame({"d": np.repeat(days, 3), "fwd_5d": 0.01})
    cal = np.sort(pd.unique(R["d"]))
    plan = loop._block_plan(R, cal, HORIZONS["5d"], "daily")
    assert len(plan) == 2                                                                # 90 days: 2 blocks of 40 + 10 fit days
    for b in plan:
        i_cut = int(np.searchsorted(cal, np.datetime64(b["cut"])))
        i_from = int(np.searchsorted(cal, np.datetime64(b["from"])))
        assert i_from - i_cut == 5                                                       # embargo = the horizon
        assert R["d"][b["fit"]].max() < pd.Timestamp(b["cut"]) and not (b["fit"] & b["val"]).any()


def test_excess_labels_subtract_the_market_for_20d_and_above() -> None:
    B = daily.price_features(_bar_tape())
    B["sector"] = 1.0
    B = daily.cross_section(B)
    d = B["d"].drop_duplicates().sort_values()
    comp = pd.DataFrame({"d": d, "comp_fwd_20d": 0.03, "comp_fwd_60d": 0.05})
    B = B.merge(comp, on="d", how="left")
    B = daily.labels(B)
    a = B[B["code"] == "AAAA"].reset_index(drop=True)
    i = 100
    raw20 = np.log(a.loc[i + 20, "close"] / a.loc[i, "close"])
    assert abs(a.loc[i, "fwd_20d"] - (raw20 - 0.03)) < 1e-9
    assert abs(a.loc[i, "fwd_5d"] - np.log(a.loc[i + 5, "close"] / a.loc[i, "close"])) < 1e-9       # 5d stays absolute
    assert HORIZONS["20d"].basis == "excess" and HORIZONS["5d"].basis == "abs"


def test_isotonic_curve_is_monotone_and_fixes_a_biased_probability() -> None:
    rng = np.random.default_rng(3)
    p = rng.uniform(0.3, 0.9, 5000)                       # a model that says "up" too often
    y = (rng.uniform(size=5000) < (p - 0.25)).astype(float)
    kp, ky = common.isotonic(p, y)
    assert np.all(np.diff(ky) >= -1e-12) and len(kp) >= 2
    cal = common.calibrate(p, kp, ky)
    raw_hit = ((p > 0.5) == (y > 0.5)).mean()
    cal_hit = ((cal > 0.5) == (y > 0.5)).mean()
    assert cal_hit > raw_hit + 0.05
    assert abs(common.calibrate(np.array([0.75]), kp, ky)[0] - 0.5) < 0.08
    assert common.calibrate(np.array([0.2, 0.99]), kp, ky).tolist() == [ky[0], ky[-1]]


def test_placebo_percentile_is_high_for_a_real_signal_and_low_for_noise() -> None:
    rng = np.random.default_rng(5)
    n_days, per_day = 30, 60
    days = np.repeat(np.array(pd.date_range("2026-01-01", periods=n_days).values), per_day)
    X = rng.normal(size=(len(days), 3)).astype(np.float32)
    y = (X[:, 0] + 0.3 * rng.normal(size=len(days)) > 0).astype(float)
    R = pd.DataFrame({"d": days})
    block = {"fit": days < days[-per_day * 5], "val": days >= days[-per_day * 5]}
    params = dict(common.BASE_PARAMS["dir"], rounds=60, min_data_in_leaf=20, num_threads=4)
    bst = common.fit(X[block["fit"]], y[block["fit"]], "dir", params, ["a", "b", "c"])
    real = common.metrics_for("dir", y[block["val"]], np.asarray(bst.predict(X[block["val"]])))["primary"]
    pl = loop._placebo(X, y, R, block, "dir", params, ["a", "b", "c"], 4, rng, real)
    assert pl["pct"] == 100.0 and pl["mean"] < 0.6 < real


# ---- macro by release date -------------------------------------------------------------------------------------------------------
def test_macro_release_dates_follow_the_publisher_not_the_period() -> None:
    ts = pd.Timestamp
    assert daily.release_date("bi_rate", ts("2026-09-23")) == ts("2026-09-23")                 # RDG decision, same day
    assert daily.release_date("us10y", ts("2026-09-22")) == ts("2026-09-23")                   # US close lands after the WIB cut
    assert daily.release_date("cpo", ts("2026-09-25")) == ts("2026-09-26")                     # Bursa Malaysia closes 17:00 WIB
    assert daily.release_date("fedfunds", ts("2026-08-01")) == ts("2026-09-01")                # August average: 1 Sep (Tue)
    assert daily.release_date("id_cpi", ts("2026-07-01")) == ts("2026-08-03")                  # 1 Aug 2026 is a Saturday -> Mon 3 Aug
    assert daily.release_date("id_gdp_qoq", ts("2026-04-01")) == ts("2026-08-06")              # Q2: quarter start +3 m +5 d = Thu 6 Aug
    assert daily.release_date("id_gdp_qoq", ts("2026-01-01")) == ts("2026-05-06")


def test_macro_features_are_the_release_dated_ones() -> None:
    assert "id_cpi" not in daily.FEATURES and "id_cpi_yoy" in daily.FEATURES and "id_gdp_qoq" in daily.FEATURES
    assert set(daily.MACRO_RELEASE) >= set(daily.MACRO_SERIES)


# ---- read-only against the desk's tables (skipped without a database) ----------------------------------------------------------
def _conn():
    dsn = os.environ.get("INGEST_DB_DSN")
    if not dsn:
        pytest.skip("INGEST_DB_DSN not set")
    return psycopg.connect(dsn)


def test_db_daily_panel_recent_cut_is_pit_and_scoreable() -> None:
    with _conn() as c:
        P = daily.build_panel(c, since=date.today() - timedelta(days=420))
    assert not P.empty
    L = daily.latest_rows(P)
    assert len(L) > 50 and set(daily.FEATURES) <= set(L.columns)
    assert (L["stale_days"].dropna() >= 0).all()                         # no report published after the bar
    assert L["fwd_1d"].isna().all()                                       # the last bar has no label yet


def test_db_registry_and_status_read() -> None:
    with _conn() as c:
        s = loop.status(c)
        ids = common.champion_ids(c)
    assert isinstance(s["champions"], list) and isinstance(ids, dict)
