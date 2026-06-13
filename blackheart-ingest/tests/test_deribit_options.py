"""Unit tests for the Deribit OPTIONS implied-vol skew / term-structure source.

Pure-mock: ``_http_get`` is patched (no real HTTP) and the skew / term-structure
maths is exercised against synthetic book-summary payloads. The two DB-writing
paths in ``fetch`` are not exercised here (mirrors test_deribit.py, which tests
the pure ``_fetch_dvol`` builder, not the DB write). The flag short-circuit IS
tested since it returns before any DB call.
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import httpx
import pytest

from blackheart_ingest.sources import deribit_options as dopt

# ── synthetic book-summary builders ──────────────────────────────────────────

def _instr(cur: str, expiry: str, strike: int, kind: str, iv: float, underlying: float) -> dict:
    """One get_book_summary_by_currency row. Deribit publishes ONE mark_iv per
    strike (call and put share it), and NO delta field — both modelled here."""
    return {
        "instrument_name": f"{cur}-{expiry}-{strike}-{kind}",
        "mark_iv": iv,
        "underlying_price": underlying,
    }


def _smile_book(
    cur: str,
    expiry: str,
    underlying: float,
    *,
    atm_iv: float,
    put_skew: float,
    call_skew: float,
    n: int = 12,
    step: float | None = None,
) -> list[dict]:
    """A synthetic vol smile around ``underlying``.

    IV rises ``put_skew`` per step *below* the forward and ``call_skew`` per step
    *above* it. put_skew > call_skew => the downside wing is richer => RR25 > 0.
    Emits both the C and the P at each strike sharing the same mark_iv (the
    Deribit quirk).
    """
    step = step or underlying * 0.025
    rows: list[dict] = []
    for i in range(-n, n + 1):
        strike = round(underlying + i * step)
        if i < 0:
            iv = atm_iv + abs(i) * put_skew
        elif i > 0:
            iv = atm_iv + i * call_skew
        else:
            iv = atm_iv
        rows.append(_instr(cur, expiry, strike, "C", iv, underlying))
        rows.append(_instr(cur, expiry, strike, "P", iv, underlying))
    return rows


def _page(rows: list[dict]) -> dict:
    return {"result": rows}


# Expiry tokens relative to a fixed "now" of 2026-06-13. ~near is 4 days out,
# ~30d is 30 days out, plus a far one for the target picker to discriminate.
_NOW = datetime(2026, 6, 13, 12, 0, 0)
_NEAR = "17JUN26"   # ~4 days
_30D = "13JUL26"    # ~30 days
_FAR = "26MAR27"    # far — should never be picked as the 30d target


# ── expiry / instrument parsing ──────────────────────────────────────────────

def test_parse_expiry_and_instrument():
    assert dopt._parse_expiry("26JUN26") == datetime(2026, 6, 26, 8, 0, 0)
    assert dopt._parse_expiry("3JUL26") == datetime(2026, 7, 3, 8, 0, 0)
    assert dopt._parse_expiry("bogus") is None
    m = dopt._INSTRUMENT_RE.match("BTC-26JUN26-65000-C")
    assert m and m.group(1) == "26JUN26" and m.group(2) == "65000" and m.group(3) == "C"


def test_parse_instruments_drops_null_iv_and_underlying():
    rows = [
        _instr("BTC", _30D, 60000, "C", 40.0, 63000.0),
        {"instrument_name": "BTC-13JUL26-61000-C", "mark_iv": None, "underlying_price": 63000.0},
        {"instrument_name": "BTC-13JUL26-62000-C", "mark_iv": 40.0, "underlying_price": None},
        {"instrument_name": "BTC-13JUL26-63000-C", "mark_iv": 0.0, "underlying_price": 63000.0},  # iv<=0 dropped
        {"instrument_name": "PERP-NOT-AN-OPTION", "mark_iv": 40.0, "underlying_price": 1.0},
    ]
    by_expiry = dopt._parse_instruments(rows)
    assert list(by_expiry.keys()) == [datetime(2026, 7, 13, 8, 0, 0)]
    # only the single fully-populated, positive-iv row survived
    assert len(by_expiry[datetime(2026, 7, 13, 8, 0, 0)]) == 1


# ── core signal maths ────────────────────────────────────────────────────────

def test_richer_puts_give_positive_rr25():
    # Downside wing steeper than upside => RR25 must be > 0 (downside fear).
    book = _smile_book("BTC", _30D, 63000.0, atm_iv=40.0, put_skew=1.5, call_skew=0.4)
    by_expiry = dopt._parse_instruments(book)
    expiry = datetime(2026, 7, 13, 8, 0, 0)
    strikes = by_expiry[expiry]
    yf = (expiry - _NOW).total_seconds() / (365.0 * 86400.0)
    rr25 = dopt._compute_rr25(strikes, 63000.0, yf, min_strikes_per_wing=3)
    assert rr25 is not None
    assert rr25 > 0.0


def test_richer_calls_give_negative_rr25():
    # Upside wing steeper => RR25 < 0 (upside chase / call skew).
    book = _smile_book("BTC", _30D, 63000.0, atm_iv=40.0, put_skew=0.4, call_skew=1.5)
    by_expiry = dopt._parse_instruments(book)
    expiry = datetime(2026, 7, 13, 8, 0, 0)
    yf = (expiry - _NOW).total_seconds() / (365.0 * 86400.0)
    rr25 = dopt._compute_rr25(by_expiry[expiry], 63000.0, yf, min_strikes_per_wing=3)
    assert rr25 is not None
    assert rr25 < 0.0


def test_symmetric_smile_gives_near_zero_rr25():
    book = _smile_book("BTC", _30D, 63000.0, atm_iv=40.0, put_skew=1.0, call_skew=1.0)
    by_expiry = dopt._parse_instruments(book)
    expiry = datetime(2026, 7, 13, 8, 0, 0)
    yf = (expiry - _NOW).total_seconds() / (365.0 * 86400.0)
    rr25 = dopt._compute_rr25(by_expiry[expiry], 63000.0, yf, min_strikes_per_wing=3)
    assert rr25 is not None
    assert abs(rr25) < 1.0  # symmetric wings → ~0


def test_rr25_skipped_when_wing_too_thin():
    # Only 2 strikes per wing but min is 3 → None (skip, never garbage).
    book = _smile_book("BTC", _30D, 63000.0, atm_iv=40.0, put_skew=1.0, call_skew=1.0, n=2)
    by_expiry = dopt._parse_instruments(book)
    expiry = datetime(2026, 7, 13, 8, 0, 0)
    yf = (expiry - _NOW).total_seconds() / (365.0 * 86400.0)
    rr25 = dopt._compute_rr25(by_expiry[expiry], 63000.0, yf, min_strikes_per_wing=3)
    assert rr25 is None


def test_atm_iv_picks_nearest_strike():
    rows = [
        _instr("BTC", _30D, 60000, "C", 38.0, 63100.0),
        _instr("BTC", _30D, 63000, "C", 40.0, 63100.0),  # nearest to 63100
        _instr("BTC", _30D, 66000, "C", 42.0, 63100.0),
    ]
    by_expiry = dopt._parse_instruments(rows)
    strikes = dopt._unique_strikes(by_expiry[datetime(2026, 7, 13, 8, 0, 0)])
    assert dopt._atm_iv(strikes, 63100.0) == 40.0


def test_pick_expiries_near_and_30d():
    book = (
        _smile_book("BTC", _NEAR, 63000.0, atm_iv=45.0, put_skew=1.0, call_skew=1.0)
        + _smile_book("BTC", _30D, 63000.0, atm_iv=40.0, put_skew=1.0, call_skew=1.0)
        + _smile_book("BTC", _FAR, 63000.0, atm_iv=35.0, put_skew=1.0, call_skew=1.0)
    )
    by_expiry = dopt._parse_instruments(book)
    near, target = dopt._pick_expiries(by_expiry, _NOW, 30)
    assert near == datetime(2026, 6, 17, 8, 0, 0)   # soonest >= 1d
    assert target == datetime(2026, 7, 13, 8, 0, 0)  # closest to 30d, NOT the far one


# ── full snapshot assembly (per-currency) ────────────────────────────────────

def test_snapshot_builds_all_four_series_with_term_sign():
    # near IV (45) > 30d IV (40) → term spread = 40 - 45 < 0 (backwardation).
    # downside-skewed → rr25 > 0.
    book = (
        _smile_book("BTC", _NEAR, 63000.0, atm_iv=45.0, put_skew=1.5, call_skew=0.4)
        + _smile_book("BTC", _30D, 63000.0, atm_iv=40.0, put_skew=1.5, call_skew=0.4)
    )
    snapshot_time = _NOW.replace(minute=0, second=0, microsecond=0)
    client = object()  # _http_get is patched, so the client is never used
    with patch.object(dopt, "_http_get", return_value=_page(book)):
        rows = dopt._snapshot_currency(client, "BTC", _NOW, snapshot_time, 30, 3)

    by_series = {r["series_id"]: r for r in rows}
    assert set(by_series) == {
        "deribit_atm_iv_btc_near",
        "deribit_atm_iv_btc_30d",
        "deribit_rr25_btc_30d",
        "deribit_term_spread_btc",
    }
    # ATM IVs land on the synthetic ATM levels.
    assert by_series["deribit_atm_iv_btc_near"]["value"] == pytest.approx(45.0)
    assert by_series["deribit_atm_iv_btc_30d"]["value"] == pytest.approx(40.0)
    # term spread = atm_30d - atm_near = 40 - 45 = -5 (downward-sloping / backwardation).
    assert by_series["deribit_term_spread_btc"]["value"] == pytest.approx(-5.0)
    # downside skew → positive risk reversal.
    assert by_series["deribit_rr25_btc_30d"]["value"] > 0.0

    # row shape / macro_raw contract
    for r in rows:
        assert r["source"] == "deribit_options"
        assert r["symbol"] is None
        assert r["value_text"] is None
        assert r["content_hash"]
        # event_time MUST be naive UTC and floored to the hour.
        assert r["event_time"].tzinfo is None
        assert r["event_time"] == snapshot_time
        assert r["event_time"].minute == 0 and r["event_time"].second == 0
    # source_uri unique per series → guards the macro_raw UNIQUE collision class.
    assert len({r["source_uri"] for r in rows}) == len(rows)
    assert by_series["deribit_rr25_btc_30d"]["source_uri"] == (
        "deribit_options/deribit_rr25_btc_30d/" + snapshot_time.isoformat()
    )


def test_snapshot_single_expiry_skips_term_spread():
    # Only one listed expiry near 30d: near==target, so term spread (which needs
    # two distinct expiries) is skipped — never written as a meaningless 0.
    book = _smile_book("BTC", _30D, 63000.0, atm_iv=40.0, put_skew=1.5, call_skew=0.4)
    snapshot_time = _NOW.replace(minute=0, second=0, microsecond=0)
    with patch.object(dopt, "_http_get", return_value=_page(book)):
        rows = dopt._snapshot_currency(object(), "BTC", _NOW, snapshot_time, 30, 3)
    series = {r["series_id"] for r in rows}
    assert "deribit_term_spread_btc" not in series
    # the single-expiry one still yields atm_near, atm_30d, rr25 (all on that expiry)
    assert "deribit_rr25_btc_30d" in series
    assert "deribit_atm_iv_btc_30d" in series


def test_snapshot_empty_book_writes_nothing():
    with patch.object(dopt, "_http_get", return_value=_page([])):
        rows = dopt._snapshot_currency(object(), "BTC", _NOW, _NOW, 30, 3)
    assert rows == []


def test_snapshot_thin_wing_skips_rr25_but_keeps_atm():
    # 30d expiry too thin for RR25 (n=2 < min 3) but ATM IV still computable.
    book = (
        _smile_book("BTC", _NEAR, 63000.0, atm_iv=45.0, put_skew=1.0, call_skew=1.0)
        + _smile_book("BTC", _30D, 63000.0, atm_iv=40.0, put_skew=1.0, call_skew=1.0, n=2)
    )
    with patch.object(dopt, "_http_get", return_value=_page(book)):
        rows = dopt._snapshot_currency(object(), "BTC", _NOW, _NOW, 30, 3)
    series = {r["series_id"] for r in rows}
    assert "deribit_rr25_btc_30d" not in series        # skipped, no garbage value
    assert "deribit_atm_iv_btc_30d" in series           # ATM still written
    assert "deribit_atm_iv_btc_near" in series


# ── HTTP error handling (mirrors test_deribit.py) ────────────────────────────

def test_http_get_raises_on_json_error_body():
    from unittest.mock import MagicMock
    client = MagicMock()
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"error": {"code": 10028, "message": "too_many_requests"}}
    client.get.return_value = resp
    with pytest.raises(httpx.HTTPError):
        dopt._http_get(client, {"currency": "BTC", "kind": "option"})


# ── feature flag short-circuit ───────────────────────────────────────────────

def test_fetch_disabled_returns_inert_result():
    from blackheart_ingest.shared.base import IngestionRequest

    req = IngestionRequest(
        start=datetime(2026, 6, 13, 0, 0),
        end=datetime(2026, 6, 13, 23, 0),
        symbol=None,
        config={},
    )

    class _Settings:
        deribit_options_enabled = False

    # Patch where fetch looks it up + guarantee no HTTP / DB is touched.
    with patch.object(dopt, "get_settings", return_value=_Settings()), \
         patch.object(dopt, "_http_get", side_effect=AssertionError("must not call HTTP when disabled")):
        result = dopt.fetch(req)

    assert result.source == "deribit_options"
    assert result.rows_inserted == 0
    assert result.series_seen == []
    assert "disabled" in (result.note or "")
