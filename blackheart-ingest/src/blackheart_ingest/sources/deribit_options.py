"""Deribit OPTIONS implied-vol SKEW / term-structure → ``macro_raw``.

A **forward-accumulating** (plant-and-accumulate) snapshot feed that captures
the *shape* of the Deribit options surface each hour, for research history we
cannot buy retroactively.

Why a separate module from ``deribit.py``?
------------------------------------------
``deribit.py`` ships the **DVOL** index — a single 30d forward-vol *level* with
deep free history (``get_volatility_index_data`` backfills to ~Mar 2021). This
module is a pure ADDITION that captures surface *shape* (skew + term structure),
which DVOL collapses away. Per-strike option IV is **only served live** on the
free tier — there is no free historical backfill — so each hourly snapshot is
the only copy we will ever have. DVOL's behaviour is untouched.

Endpoint
--------
``public/get_book_summary_by_currency?currency=<CUR>&kind=option`` returns one
row per live option instrument, each carrying ``mark_iv`` (Deribit's mark
implied vol, in %), ``underlying_price`` (the forward/index price for that
expiry), and an ``instrument_name`` of the form ``BTC-<DDMMMYY>-<STRIKE>-<C|P>``.
No auth, no rate-limit auth headers — same client/base-URL as DVOL.

API quirk (important): Deribit publishes a **single ``mark_iv`` per strike** —
the call and put at the same strike share the identical mark IV (put-call
parity holds at the mark). So a risk-reversal cannot be "put IV − call IV at the
same strike" (that is always 0). The economically-correct construction on a
single-IV-per-strike surface is the **strike skew**: IV at the OTM *put* strike
(below forward) minus IV at the OTM *call* strike (above forward).

Series written (``symbol=NULL``, asset encoded in ``series_id`` — matching the
``macro_raw`` convention used by DVOL / funding / coinmetrics):

    deribit_rr25_<cur>_30d    25-delta risk reversal (put-wing IV − call-wing IV),
                              expiry nearest 30 days. Positive = downside fear.
    deribit_atm_iv_<cur>_near ATM mark_iv, nearest expiry >= ~1 day out.
    deribit_atm_iv_<cur>_30d  ATM mark_iv, expiry nearest 30 days.
    deribit_term_spread_<cur> atm_iv_30d − atm_iv_near (vol term-structure slope).

25-delta approximation
----------------------
``get_book_summary_by_currency`` does NOT return per-instrument greeks (no
``delta`` field — confirmed against the live payload), so we approximate the
25-delta strikes geometrically. Under Black-Scholes the strike whose call delta
is ~0.25 sits at ``F * exp(+z * sigma * sqrt(T))`` and the 25-delta put strike at
``F * exp(-z * sigma * sqrt(T))``, where ``z = N^{-1}(0.75) ≈ 0.6745`` and
``sigma`` is the ATM vol, ``T`` the year-fraction to expiry. We compute those two
*target* strikes from the ATM vol and snap each to the nearest available listed
strike on the correct wing (put strike strictly below F, call strike strictly
above F). This is a documented approximation: it ignores the vol-of-the-wing
(skew) feedback on delta and the drift/rate terms, both second-order for a
research skew proxy. Exact 25-delta would require per-instrument greeks (a
heavier per-strike ``ticker`` fan-out) — deliberately not done here.

Cold-start / partial-data safety: if an expiry has too few strikes on a wing to
form the skew (illiquid / brand-new listing), that *series* is skipped for that
run (nothing written) and logged — never a garbage/zero value. A run that finds
no usable expiry writes nothing and reports healthy-but-empty rather than
failing.

Config:
    currencies: list[str]   default ["BTC", "ETH"]
    target_days: int        default 30 (the "30d" expiry bucket)
    min_strikes_per_wing: int default 3 (skip a skew if a wing is thinner)
"""
from __future__ import annotations

import logging
import math
import re
import time
from datetime import datetime
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ..shared.base import IngestionRequest, IngestionResult
from ..shared.db import content_hash, get_connection, update_source_health, write_macro_raw_rows
from ..shared.pit_guards import PitConfig, partition_by_pit
from ..shared.settings import get_settings

logger = logging.getLogger(__name__)

# ``name`` is the source identifier matching ml_ingest_schedule.source and the
# _KNOWN_SOURCES registry key in workers/server.py. Distinct from "deribit"
# (the DVOL source) so this feed schedules and reports health independently.
name = "deribit_options"
raw_table = "macro_raw"

_BASE_URL = "https://www.deribit.com/api/v2"
_PATH = "/public/get_book_summary_by_currency"

# Live snapshot of a continuously-updated book; 12h PIT slop matches DVOL and
# the other macro sources. event_time is floored to the hour, so the worst-case
# lag vs ingestion clock is < 1h anyway.
_PIT_CONFIG = PitConfig(max_backfill_lag_hours=12)
_DEFAULT_CURRENCIES = ["BTC", "ETH"]
_DEFAULT_TARGET_DAYS = 30
_DEFAULT_MIN_STRIKES_PER_WING = 3

# Skip an expiry as the "near" bucket if it is closer than this — sub-1-day
# options have unstable IVs as they decay into the close.
_MIN_NEAR_DAYS = 1.0

# z = N^{-1}(0.75) ≈ 0.6745 — the standard-normal quantile whose two-sided
# tails leave 25% mass, i.e. the ~25-delta point under a lognormal.
_DELTA25_Z = 0.6744897501960817

# Deribit instrument name: <CUR>-<DDMMMYY>-<STRIKE>-<C|P>, e.g. BTC-26JUN26-65000-C.
_INSTRUMENT_RE = re.compile(r"^[A-Z]+-(\d{1,2}[A-Z]{3}\d{2})-(\d+(?:\.\d+)?)-([CP])$")
_MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}


@retry(
    reraise=True,
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
)
def _http_get(client: httpx.Client, params: dict[str, Any]) -> dict[str, Any]:
    """GET the book summary. Mirrors deribit.py: Deribit returns HTTP 200 with a
    JSON-RPC ``error`` body for rate-limits / bad params, so we raise on that to
    fail loud (and trip the tenacity retry) instead of degrading to "no data"."""
    response = client.get(f"{_BASE_URL}{_PATH}", params=params)
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict) and payload.get("error"):
        raise httpx.HTTPError(f"Deribit API error: {payload['error']}")
    return payload


def _parse_expiry(token: str) -> datetime | None:
    """``26JUN26`` -> naive-UTC datetime at Deribit's 08:00 UTC expiry."""
    m = re.match(r"^(\d{1,2})([A-Z]{3})(\d{2})$", token)
    if not m:
        return None
    day = int(m.group(1))
    month = _MONTHS.get(m.group(2))
    if month is None:
        return None
    year = 2000 + int(m.group(3))
    try:
        # Deribit options expire at 08:00 UTC. The exact intraday time barely
        # matters for a day-count to ~30d, but be precise.
        return datetime(year, month, day, 8, 0, 0)
    except ValueError:
        return None


def _parse_instruments(result: list[dict[str, Any]]) -> dict[datetime, list[dict[str, Any]]]:
    """Group valid option rows by expiry datetime.

    Each kept entry is ``{"strike", "type" ('C'|'P'), "iv", "underlying"}``.
    Rows with a null/zero ``mark_iv`` or missing ``underlying_price`` are
    dropped (illiquid / not-yet-quoted strikes) — never coerced to 0.
    """
    by_expiry: dict[datetime, list[dict[str, Any]]] = {}
    for e in result:
        name_field = e.get("instrument_name") or ""
        m = _INSTRUMENT_RE.match(name_field)
        if not m:
            continue
        expiry = _parse_expiry(m.group(1))
        if expiry is None:
            continue
        iv = e.get("mark_iv")
        underlying = e.get("underlying_price")
        if iv is None or underlying is None:
            continue
        try:
            iv_f = float(iv)
            underlying_f = float(underlying)
            strike_f = float(m.group(2))
        except (TypeError, ValueError):
            continue
        if iv_f <= 0.0 or underlying_f <= 0.0:
            continue
        by_expiry.setdefault(expiry, []).append(
            {"strike": strike_f, "type": m.group(3), "iv": iv_f, "underlying": underlying_f}
        )
    return by_expiry


def _atm_iv(strikes: list[dict[str, Any]], forward: float) -> float | None:
    """ATM mark_iv = the IV of the listed strike nearest the forward.

    On Deribit the call and put at a strike share one mark_iv, so we just take
    whichever instrument sits at the strike closest to ``forward``.
    """
    if not strikes:
        return None
    nearest = min(strikes, key=lambda r: abs(r["strike"] - forward))
    return nearest["iv"]


def _wing_iv(
    strikes: list[dict[str, Any]],
    target_strike: float,
    *,
    side: str,
    forward: float,
) -> float | None:
    """IV at the listed strike nearest ``target_strike`` on the requested wing.

    ``side='put'`` restricts to strikes strictly below the forward (downside
    wing); ``side='call'`` to strikes strictly above. Returns None if that wing
    has no listed strike (so the caller can skip the series rather than reach
    across the forward and contaminate the skew sign).
    """
    if side == "put":
        wing = [r for r in strikes if r["strike"] < forward]
    else:
        wing = [r for r in strikes if r["strike"] > forward]
    if not wing:
        return None
    nearest = min(wing, key=lambda r: abs(r["strike"] - target_strike))
    return nearest["iv"]


def _unique_strikes(strikes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse the C/P pair at each strike to one entry (they share mark_iv).

    Keeps the per-wing counts honest for the ``min_strikes_per_wing`` gate —
    otherwise every strike counts twice.
    """
    seen: dict[float, dict[str, Any]] = {}
    for r in strikes:
        seen.setdefault(r["strike"], r)
    return list(seen.values())


def _compute_rr25(
    strikes: list[dict[str, Any]],
    forward: float,
    year_fraction: float,
    *,
    min_strikes_per_wing: int,
) -> float | None:
    """25-delta risk reversal = IV(25d put wing) − IV(25d call wing).

    Positive => the downside (put) wing is richer than the upside (call) wing
    => the market is paying up for crash protection (downside fear). See the
    module docstring for the geometric 25-delta strike approximation and why a
    *strike* skew (not a same-strike put-minus-call) is the correct construction
    on Deribit's single-IV-per-strike surface.
    """
    uniq = _unique_strikes(strikes)
    puts = [r for r in uniq if r["strike"] < forward]
    calls = [r for r in uniq if r["strike"] > forward]
    if len(puts) < min_strikes_per_wing or len(calls) < min_strikes_per_wing:
        return None

    atm = _atm_iv(uniq, forward)
    if atm is None or atm <= 0.0 or year_fraction <= 0.0:
        return None
    # mark_iv is in PERCENT (e.g. 39.3). Convert to a fraction for the
    # lognormal strike formula, then the move is z * sigma * sqrt(T).
    sigma = atm / 100.0
    move = _DELTA25_Z * sigma * math.sqrt(year_fraction)
    put_target = forward * math.exp(-move)
    call_target = forward * math.exp(+move)

    put_iv = _wing_iv(uniq, put_target, side="put", forward=forward)
    call_iv = _wing_iv(uniq, call_target, side="call", forward=forward)
    if put_iv is None or call_iv is None:
        return None
    return put_iv - call_iv


def _pick_expiries(
    by_expiry: dict[datetime, list[dict[str, Any]]],
    now: datetime,
    target_days: int,
) -> tuple[datetime | None, datetime | None]:
    """Choose (near_expiry, target_expiry).

    near   = the soonest expiry at least ``_MIN_NEAR_DAYS`` out.
    target = the expiry whose day-count is closest to ``target_days``.
    Either may be None if no expiry qualifies. They can coincide (e.g. only one
    listed expiry) — the caller handles that.
    """
    candidates = sorted(by_expiry)
    near: datetime | None = None
    for exp in candidates:
        days = (exp - now).total_seconds() / 86400.0
        if days >= _MIN_NEAR_DAYS:
            near = exp
            break

    target: datetime | None = None
    best_gap = float("inf")
    for exp in candidates:
        days = (exp - now).total_seconds() / 86400.0
        if days < _MIN_NEAR_DAYS:
            continue
        gap = abs(days - target_days)
        if gap < best_gap:
            best_gap = gap
            target = exp
    return near, target


def _build_row(series_id: str, event_time: datetime, value: float, ingestion_time: datetime) -> dict[str, Any]:
    iso_ts = event_time.isoformat()
    return {
        "source": name,
        # source_uri MUST be unique per (series_id, event_time) — the macro_raw
        # UNIQUE(source, source_uri, event_time) constraint would otherwise
        # collapse distinct series sharing a uri (binance_ob_imbalance class).
        # Suffix with series_id + iso_ts, matching DVOL / coingecko / coinmetrics.
        "source_uri": f"deribit_options/{series_id}/{iso_ts}",
        "symbol": None,
        "series_id": series_id,
        "event_time": event_time,
        "ingestion_time": ingestion_time,
        "value": float(value),
        "value_text": None,
        "content_hash": content_hash(series_id, iso_ts, float(value)),
    }


def _snapshot_currency(
    client: httpx.Client,
    currency: str,
    now: datetime,
    snapshot_time: datetime,
    target_days: int,
    min_strikes_per_wing: int,
) -> list[dict[str, Any]]:
    """Fetch the live option book for ``currency`` and build the skew/term rows.

    Returns the (possibly empty) list of macro_raw rows. Any series whose inputs
    are insufficient is skipped with a log line; never writes a garbage value.
    """
    cur = currency.upper()
    lc = cur.lower()
    payload = _http_get(client, {"currency": cur, "kind": "option"})
    result = (payload.get("result") or [])
    if not isinstance(result, list) or not result:
        logger.warning("deribit_options: empty option book for %s — skipping run", cur)
        return []

    by_expiry = _parse_instruments(result)
    if not by_expiry:
        logger.warning("deribit_options: no parseable option instruments for %s — skipping", cur)
        return []

    near_exp, target_exp = _pick_expiries(by_expiry, now, target_days)

    rows: list[dict[str, Any]] = []

    # --- ATM IV at the near expiry ---
    atm_near: float | None = None
    if near_exp is not None:
        strikes = by_expiry[near_exp]
        forward = strikes[0]["underlying"]
        atm_near = _atm_iv(_unique_strikes(strikes), forward)
        if atm_near is not None:
            rows.append(_build_row(f"deribit_atm_iv_{lc}_near", snapshot_time, atm_near, now))
        else:
            logger.warning("deribit_options: %s near expiry %s has no ATM IV — skipping near", cur, near_exp.date())
    else:
        logger.warning("deribit_options: %s has no expiry >= %.0fd out — skipping near series", cur, _MIN_NEAR_DAYS)

    # --- ATM IV + RR25 at the ~30d (target) expiry ---
    atm_target: float | None = None
    if target_exp is not None:
        strikes = by_expiry[target_exp]
        forward = strikes[0]["underlying"]
        year_fraction = max((target_exp - now).total_seconds() / (365.0 * 86400.0), 1e-9)

        atm_target = _atm_iv(_unique_strikes(strikes), forward)
        if atm_target is not None:
            rows.append(_build_row(f"deribit_atm_iv_{lc}_30d", snapshot_time, atm_target, now))
        else:
            logger.warning("deribit_options: %s target expiry %s has no ATM IV — skipping atm_30d", cur, target_exp.date())

        rr25 = _compute_rr25(
            strikes, forward, year_fraction, min_strikes_per_wing=min_strikes_per_wing
        )
        if rr25 is not None:
            rows.append(_build_row(f"deribit_rr25_{lc}_30d", snapshot_time, rr25, now))
        else:
            logger.warning(
                "deribit_options: %s target expiry %s has too few strikes per wing for RR25 — skipping",
                cur, target_exp.date(),
            )
    else:
        logger.warning("deribit_options: %s has no usable target expiry — skipping atm_30d + rr25", cur)

    # --- Term-structure slope: atm_30d − atm_near ---
    # Only when both ATM IVs exist AND the two expiries are actually different
    # (one listed expiry would make this a meaningless 0).
    if (
        atm_near is not None
        and atm_target is not None
        and near_exp is not None
        and target_exp is not None
        and near_exp != target_exp
    ):
        rows.append(
            _build_row(f"deribit_term_spread_{lc}", snapshot_time, atm_target - atm_near, now)
        )
    else:
        logger.info(
            "deribit_options: %s term spread skipped (need two distinct expiries with ATM IV)", cur
        )

    logger.info(
        "deribit_options %s | near=%s target=%s series_built=%d",
        cur,
        near_exp.date() if near_exp else None,
        target_exp.date() if target_exp else None,
        len(rows),
    )
    return rows


def fetch(request: IngestionRequest) -> IngestionResult:
    """Snapshot the live Deribit option surface and write skew/term-structure rows.

    This is a *live snapshot* source: the option surface has no free historical
    backfill, so the requested ``[start, end]`` window is ignored — every call
    captures "now", floored to the hour. The JVM ``ml_ingest_schedule`` row for
    ``deribit_options`` drives the hourly cadence (same mechanism as DVOL).
    """
    started = time.monotonic()

    # Feature flag: default OFF so deploying the code is inert. Even with an
    # ml_ingest_schedule row present, the feed writes nothing until the operator
    # sets INGEST_DERIBIT_OPTIONS_ENABLED=true (mirrors the liquidation stream's
    # "deploy is inert" convention). Returns a clean empty result, NOT an error,
    # so a scheduled tick against a disabled feed reports healthy/empty.
    if not get_settings().deribit_options_enabled:
        logger.info(
            "deribit_options disabled (INGEST_DERIBIT_OPTIONS_ENABLED unset) — skipping snapshot"
        )
        return IngestionResult(
            source=name,
            symbol=None,
            start=request.start,
            end=request.end,
            note="disabled: set INGEST_DERIBIT_OPTIONS_ENABLED=true to start accruing",
        )

    now = datetime.utcnow()  # naive UTC — matches macro_raw / PIT convention
    # Floor to the hour so repeated snapshots within an hour are idempotent at
    # the (series_id, event_time) unique key — a retried/duplicate tick in the
    # same hour collapses to one row instead of accumulating intra-hour noise.
    snapshot_time = now.replace(minute=0, second=0, microsecond=0)

    currencies = request.config.get("currencies") or _DEFAULT_CURRENCIES
    target_days = int(request.config.get("target_days") or _DEFAULT_TARGET_DAYS)
    min_strikes_per_wing = int(
        request.config.get("min_strikes_per_wing") or _DEFAULT_MIN_STRIKES_PER_WING
    )

    all_rows: list[dict[str, Any]] = []
    series_seen: list[str] = []
    try:
        with httpx.Client(timeout=30.0) as client:
            for i, currency in enumerate(currencies):
                if i > 0:
                    time.sleep(0.5)  # be polite to the public endpoint
                logger.info("deribit_options snapshot currency=%s target_days=%d", currency, target_days)
                rows = _snapshot_currency(
                    client, currency, now, snapshot_time, target_days, min_strikes_per_wing
                )
                all_rows.extend(rows)
                series_seen.extend(r["series_id"] for r in rows)
    except Exception as e:  # noqa: BLE001
        logger.exception("deribit_options snapshot failed")
        update_source_health(name, success=False, error_message=str(e)[:500])
        raise

    # request_start is None for this live snapshot (no declared window), so the
    # PIT guard falls back to the lag check — fine, event_time is "now" floored.
    accepted, rejected = partition_by_pit(all_rows, config=_PIT_CONFIG, now=now)

    rows_inserted = 0
    rows_skipped_duplicate = 0
    try:
        with get_connection() as conn:
            rows_inserted, rows_skipped_duplicate = write_macro_raw_rows(accepted, conn=conn)
            update_source_health(
                name,
                success=True,
                rows_inserted=rows_inserted,
                rows_rejected_pit=len(rejected),
                conn=conn,
            )
    except Exception as e:  # noqa: BLE001
        logger.exception("deribit_options DB write failed")
        update_source_health(name, success=False, error_message=str(e)[:500])
        raise

    duration = time.monotonic() - started
    result = IngestionResult(
        source=name,
        symbol=None,
        start=request.start,
        end=request.end,
        rows_fetched=len(all_rows),
        rows_inserted=rows_inserted,
        rows_rejected_pit=len(rejected),
        rows_skipped_duplicate=rows_skipped_duplicate,
        series_seen=sorted(set(series_seen)),
        duration_seconds=duration,
        note=(
            None if all_rows
            else "no usable option surface this run (cold-start / illiquid expiries) — nothing written"
        ),
    )
    logger.info(
        "deribit_options fetch complete | series=%d fetched=%d inserted=%d skipped=%d pit_reject=%d duration=%.2fs",
        len(set(series_seen)), len(all_rows), rows_inserted, rows_skipped_duplicate,
        len(rejected), duration,
    )
    return result
