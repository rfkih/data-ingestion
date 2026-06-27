"""Unit tests for the historical Deribit options-surface loader.

Pure-synthetic: a Tardis-format ``options_chain`` CSV is generated in a tmp dir
and run through ``deribit_options_history.build_macro_rows`` (no DB, no network).
The skew / term maths itself is the live feed's -- these tests assert the LOADER
wiring: the 4 series come out, the values match a hand-checked surface, hourly
grouping works, mark_iv unit normalization works, and the historical PIT path
accepts rows the live guard would reject.

NOTE: no real Tardis sample was available, so these exercise the loader on
synthetic data only. The three flagged assumptions (mark_iv units, PIT, hourly
snapshot) must still be sanity-checked against the operator's first real file.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest

from blackheart_ingest.shared.pit_guards import partition_by_pit
from blackheart_ingest.sources import deribit_options as dopt
from blackheart_ingest.sources import deribit_options_history as doh

# Fixed historical clock: a 2024 surface, ingested "now" in 2026.
_NEAR_TOKEN = "17JUN24"
_NEAR_EXP = datetime(2024, 6, 17, 8, 0, 0)
_30D_TOKEN = "13JUL24"
_30D_EXP = datetime(2024, 7, 13, 8, 0, 0)
_UNDER = 63000.0
_ING = datetime(2026, 6, 27, 0, 0, 0)


def _micros(dt: datetime) -> int:
    """Naive-UTC datetime -> epoch microseconds (the Tardis timestamp unit)."""
    return int(dt.replace(tzinfo=UTC).timestamp() * 1_000_000)


def _smile_rows(
    ts_us: int,
    token: str,
    expiry: datetime,
    underlying: float,
    atm_iv: float,
    put_skew: float,
    call_skew: float,
    n: int = 12,
    cur: str = "BTC",
) -> list[dict]:
    """Tardis options_chain rows for one expiry: a vol smile around the forward.

    IV rises ``put_skew`` per step below the forward and ``call_skew`` per step
    above it (put_skew > call_skew => downside-rich => RR25 > 0). Emits both the
    C and the P at each strike sharing one mark_iv (the Deribit quirk). ``atm_iv``
    is given in whatever unit the test wants (fraction or percent)."""
    step = underlying * 0.025
    out: list[dict] = []
    for i in range(-n, n + 1):
        strike = round(underlying + i * step)
        if i < 0:
            iv = atm_iv + abs(i) * put_skew
        elif i > 0:
            iv = atm_iv + i * call_skew
        else:
            iv = atm_iv
        for kind in ("C", "P"):
            out.append(
                {
                    "exchange": "deribit",
                    "symbol": f"{cur}-{token}-{strike}-{kind}",
                    "timestamp": ts_us,
                    "type": "call" if kind == "C" else "put",
                    "strike_price": float(strike),
                    "expiration": _micros(expiry),
                    "underlying_price": underlying,
                    "mark_price": 0.05,
                    "mark_iv": iv,
                    "delta": 0.5 if kind == "C" else -0.5,
                }
            )
    return out


def _write_csv(tmp_path, rows: list[dict], name: str = "opt.csv") -> str:
    p = tmp_path / name
    pd.DataFrame(rows).to_csv(p, index=False)
    return str(p)


def test_single_hour_builds_four_series_and_normalizes_iv(tmp_path):
    # mark_iv supplied as DECIMAL FRACTIONS (0.45 / 0.40) -> loader must scale
    # x100 to PERCENT (45 / 40) before the shared compute consumes it.
    ts = _micros(datetime(2024, 6, 13, 12, 30))
    rows_in = (
        _smile_rows(ts, _NEAR_TOKEN, _NEAR_EXP, _UNDER, 0.45, 0.015, 0.004)
        + _smile_rows(ts, _30D_TOKEN, _30D_EXP, _UNDER, 0.40, 0.015, 0.004)
    )
    csv = _write_csv(tmp_path, rows_in)

    macro, meta = doh.build_macro_rows(
        [csv], currencies=["BTC"], target_days=30, min_strikes_per_wing=3,
        iv_units="auto", ingestion_time=_ING,
    )

    h = datetime(2024, 6, 13, 12, 0, 0)
    by = {r["series_id"]: r for r in macro}
    assert set(by) == {
        "deribit_atm_iv_btc_near",
        "deribit_atm_iv_btc_30d",
        "deribit_rr25_btc_30d",
        "deribit_term_spread_btc",
    }
    # FLAG 1 unit normalization: fraction in -> percent out.
    assert by["deribit_atm_iv_btc_near"]["value"] == pytest.approx(45.0)
    assert by["deribit_atm_iv_btc_30d"]["value"] == pytest.approx(40.0)
    # term spread = atm_30d - atm_near = 40 - 45 = -5 (backwardation).
    assert by["deribit_term_spread_btc"]["value"] == pytest.approx(-5.0)
    # downside-rich smile -> positive risk reversal.
    assert by["deribit_rr25_btc_30d"]["value"] > 0.0

    assert meta["iv_factor"] == 100.0
    assert meta["iv_mode"].startswith("fraction")
    assert meta["n_snapshots"] == 1

    # macro_raw row contract (matches the live feed).
    for r in macro:
        assert r["source"] == "deribit_options"
        assert r["symbol"] is None
        assert r["value_text"] is None
        assert r["content_hash"]
        assert r["event_time"] == h
        assert r["event_time"].tzinfo is None
        assert r["ingestion_time"] == _ING
        assert r["source_uri"].startswith("deribit_options/")
    assert len({r["source_uri"] for r in macro}) == len(macro)


def test_hourly_grouping_yields_one_snapshot_per_hour(tmp_path):
    rows_in: list[dict] = []
    for hh, under in ((12, 63000.0), (13, 64000.0)):
        ts = _micros(datetime(2024, 6, 13, hh, 30))
        rows_in += _smile_rows(ts, _NEAR_TOKEN, _NEAR_EXP, under, 0.45, 0.015, 0.004)
        rows_in += _smile_rows(ts, _30D_TOKEN, _30D_EXP, under, 0.40, 0.015, 0.004)
    csv = _write_csv(tmp_path, rows_in)

    macro, meta = doh.build_macro_rows(
        [csv], currencies=["BTC"], target_days=30, min_strikes_per_wing=3,
        ingestion_time=_ING,
    )

    event_times = {r["event_time"] for r in macro}
    assert event_times == {datetime(2024, 6, 13, 12, 0, 0), datetime(2024, 6, 13, 13, 0, 0)}
    assert meta["n_snapshots"] == 2
    for h in event_times:
        sids = {r["series_id"] for r in macro if r["event_time"] == h}
        assert sids == {
            "deribit_atm_iv_btc_near",
            "deribit_atm_iv_btc_30d",
            "deribit_rr25_btc_30d",
            "deribit_term_spread_btc",
        }


def test_last_quote_within_the_hour_wins(tmp_path):
    # Same instruments quoted twice in hour 12: an early stale surface (atm 0.30)
    # then a later one (atm 0.45). The loader must keep the LATER quote.
    early = _micros(datetime(2024, 6, 13, 12, 5))
    late = _micros(datetime(2024, 6, 13, 12, 55))
    rows_in = (
        _smile_rows(early, _NEAR_TOKEN, _NEAR_EXP, _UNDER, 0.30, 0.015, 0.004)
        + _smile_rows(late, _NEAR_TOKEN, _NEAR_EXP, _UNDER, 0.45, 0.015, 0.004)
        + _smile_rows(late, _30D_TOKEN, _30D_EXP, _UNDER, 0.40, 0.015, 0.004)
    )
    csv = _write_csv(tmp_path, rows_in)

    macro, _ = doh.build_macro_rows(
        [csv], currencies=["BTC"], target_days=30, min_strikes_per_wing=3,
        ingestion_time=_ING,
    )
    h = datetime(2024, 6, 13, 12, 0, 0)
    near = next(
        r for r in macro if r["series_id"] == "deribit_atm_iv_btc_near" and r["event_time"] == h
    )
    assert near["value"] == pytest.approx(45.0)  # late wins, not the stale 30.0


def test_pit_accepts_historical_rows_that_live_guard_would_reject(tmp_path):
    # FLAG 2: event_times are ~2 years before ingestion. The loader's backfill
    # PIT path (request_start = load-window start) must ACCEPT them, while the
    # live feed's wall-clock lag guard would drop every one.
    ts = _micros(datetime(2024, 6, 13, 12, 30))
    rows_in = (
        _smile_rows(ts, _NEAR_TOKEN, _NEAR_EXP, _UNDER, 0.45, 0.015, 0.004)
        + _smile_rows(ts, _30D_TOKEN, _30D_EXP, _UNDER, 0.40, 0.015, 0.004)
    )
    csv = _write_csv(tmp_path, rows_in)

    macro, meta = doh.build_macro_rows([csv], currencies=["BTC"], ingestion_time=_ING)
    assert macro  # rows were produced

    accepted, rejected = doh.partition_history(
        macro, ingestion_time=_ING, request_start=meta["request_start"]
    )
    assert rejected == []                 # nothing dropped
    assert len(accepted) == len(macro)    # all rows kept

    # Contrast: the LIVE feed config (no request_start) rejects them all as
    # "stale backfill" -- which is exactly why the loader needs its own path.
    live_accepted, live_rejected = partition_by_pit(macro, config=dopt._PIT_CONFIG, now=_ING)
    assert live_accepted == []
    assert len(live_rejected) == len(macro)


def test_percent_units_passthrough_and_currency_filter(tmp_path):
    # mark_iv already in PERCENT (45 / 40) + an ETH expiry that must be filtered
    # out when only BTC is requested.
    ts = _micros(datetime(2024, 6, 13, 12, 30))
    rows_in = (
        _smile_rows(ts, _NEAR_TOKEN, _NEAR_EXP, _UNDER, 45.0, 1.5, 0.4)
        + _smile_rows(ts, _30D_TOKEN, _30D_EXP, _UNDER, 40.0, 1.5, 0.4)
        + _smile_rows(ts, _30D_TOKEN, _30D_EXP, 3500.0, 40.0, 1.5, 0.4, cur="ETH")
    )
    csv = _write_csv(tmp_path, rows_in)

    macro, meta = doh.build_macro_rows(
        [csv], currencies=["BTC"], iv_units="percent", ingestion_time=_ING
    )

    by = {r["series_id"]: r for r in macro}
    assert by["deribit_atm_iv_btc_near"]["value"] == pytest.approx(45.0)  # no x100 scaling
    assert meta["iv_factor"] == 1.0
    assert meta["iv_mode"] == "percent"
    assert all("eth" not in r["series_id"] for r in macro)  # ETH filtered out
