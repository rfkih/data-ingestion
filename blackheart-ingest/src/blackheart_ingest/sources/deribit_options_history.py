"""Historical Deribit options-surface loader (Tardis.dev options_chain CSV).

The live feed ``sources/deribit_options.py`` snapshots the Deribit option
surface each hour into ``macro_raw`` (series ``deribit_rr25_<cur>_30d``,
``deribit_atm_iv_<cur>_near``, ``deribit_atm_iv_<cur>_30d``,
``deribit_term_spread_<cur>``). Per-strike option IV has *no free historical
backfill*, so this loader ingests purchased Tardis.dev ``options_chain``
history and produces the SAME series for past hours -- REUSING the exact skew /
term-structure computation in ``deribit_options._build_currency_rows`` (no skew
maths is reimplemented here).

What it does
------------
1. Reads one or more Tardis ``options_chain`` CSV(.gz) files (exchange=deribit).
2. Maps each Tardis row to the ``{instrument_name, mark_iv, underlying_price}``
   dict shape ``deribit_options._parse_instruments`` consumes.
3. HOURLY downsample: groups rows by ``floor(timestamp, 1h)`` and, within each
   (currency, hour) bucket, keeps the LAST quote per instrument (the most recent
   surface state seen in that hour). Each bucket becomes one snapshot stamped
   with ``event_time`` = the hour boundary (mirrors the live feed, which floors
   the wall clock to the hour).
4. Computes the 4 series per (currency, hour) via the shared pure compute and
   writes ``macro_raw`` rows (``event_time`` = the historical hour,
   ``ingestion_time`` = now). Re-runs are idempotent: same source / source_uri /
   content_hash as the live feed plus ``ON CONFLICT DO NOTHING``.

THREE assumptions to VERIFY against the operator's first real Tardis sample
(each flagged inline below):

  * mark_iv UNITS -- Tardis ``options_chain`` ``mark_iv`` is commonly a DECIMAL
    fraction (e.g. 0.39), while the compute expects PERCENT (e.g. 39.0). See
    ``_decide_iv_factor`` ("FLAG 1").
  * PIT handling -- historical ``event_time`` is far in the past and the live
    12h PIT guard would reject it; we use a backfill PIT path (pass
    ``request_start`` = load-window start). See ``partition_history`` ("FLAG 2").
  * hourly-snapshot choice -- "last quote per instrument within the [H, H+1)
    hour bucket". See the FLAG 3 comment in ``build_macro_rows``.

CLI::

    python -m blackheart_ingest.sources.deribit_options_history
        --csv deribit_BTC_options_2024-01-01.csv.gz --currencies BTC,ETH --no-persist
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from ..shared.db import get_connection, update_source_health, write_macro_raw_rows
from ..shared.logging_setup import configure as configure_logging
from ..shared.pit_guards import PitConfig, partition_by_pit
from . import deribit_options as dopt

logger = logging.getLogger(__name__)

# Same source identity as the live feed: downstream feature compute does not
# care whether a macro_raw row came from a live snapshot or this backfill, so
# the series line up seamlessly.
SOURCE_NAME = dopt.name  # "deribit_options"

# FLAG 2 (PIT): historical event_times are far in the past, so the live feed's
# 12h lag guard (deribit_options._PIT_CONFIG) would reject every row. The
# canonical fix used by the other historical backfills (deribit DVOL, FRED) is
# to pass request_start = the load-window start to partition_by_pit, which
# switches rule #3 to a "predates the requested window" check instead of the
# "stale vs wall clock" check. The lag below is then only the slop tolerance
# *below* request_start.
_HISTORY_PIT_CONFIG = PitConfig(max_backfill_lag_hours=48)

# FLAG 1 (mark_iv units): if the median positive mark_iv in the file is below
# this, the values look like DECIMAL FRACTIONS (e.g. 0.39) and are scaled x100
# to PERCENT (39.0) -- the units _compute_rr25 expects. Crypto IVs as fractions
# sit ~0.1-3.0; as percent ~10-300; 5.0 is a safe separator. VERIFY against the
# first real Tardis sample and override with --iv-units if it ever guesses wrong.
_IV_FRACTION_MEDIAN_THRESHOLD = 5.0

# Candidate column names for the forward / underlying price, priority order.
_UNDERLYING_COLS = ("underlying_price", "underlying_index", "index_price")
_TIMESTAMP_COL = "timestamp"
_SYMBOL_COL = "symbol"
_MARK_IV_COL = "mark_iv"


def _detect_timestamp_unit(median_ts: float) -> str:
    """Infer the epoch unit of the Tardis ``timestamp`` column from magnitude.

    Tardis ``options_chain`` documents MICROSECONDS, but we guard the ms / s /
    ns cases defensively so a differently-encoded file does not silently shift
    every event_time. The boundaries cleanly separate the four scales for any
    plausible crypto-era date (2015+).
    """
    if median_ts >= 1e17:
        return "ns"
    if median_ts >= 1e14:
        return "us"
    if median_ts >= 1e11:
        return "ms"
    return "s"


def _decide_iv_factor(sample: pd.Series, mode: str) -> tuple[float, str]:
    """Return ``(multiplier_to_percent, resolved_mode)`` for mark_iv.

    FLAG 1. ``mode`` is one of ``auto`` / ``fraction`` / ``percent``. In
    ``auto`` we look at the median positive mark_iv: below the threshold => the
    file is in fractions => multiply by 100 to reach percent.
    """
    if mode == "percent":
        return 1.0, "percent"
    if mode == "fraction":
        return 100.0, "fraction"
    positive = sample[sample > 0]
    if positive.empty:
        return 1.0, "percent (default; no positive mark_iv to sample)"
    median = float(positive.median())
    if median < _IV_FRACTION_MEDIAN_THRESHOLD:
        return 100.0, f"fraction (auto; median mark_iv={median:.4f})"
    return 1.0, f"percent (auto; median mark_iv={median:.4f})"


def _read_csv(path: str | Path) -> pd.DataFrame:
    """Read one Tardis CSV(.gz). ``compression='infer'`` handles .gz vs .csv."""
    return pd.read_csv(path, compression="infer")


def _empty_meta(currencies: list[str], note: str, n_input_rows: int = 0) -> dict[str, Any]:
    return {
        "iv_mode": "n/a",
        "iv_factor": 1.0,
        "n_input_rows": int(n_input_rows),
        "n_snapshots": 0,
        "n_macro_rows": 0,
        "request_start": None,
        "earliest_event_time": None,
        "latest_event_time": None,
        "currencies": sorted(currencies),
        "note": note,
    }


def build_macro_rows(
    csv_paths: list[str | Path],
    *,
    currencies: list[str] | None = None,
    target_days: int | None = None,
    min_strikes_per_wing: int | None = None,
    iv_units: str = "auto",
    ingestion_time: datetime | None = None,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Read Tardis options_chain CSV(s) and build (pre-PIT) ``macro_raw`` rows.

    Pure (no DB): returns ``(rows, meta)``. ``load`` / the CLI apply the PIT
    guard and the DB write. ``ingestion_time`` defaults to now;
    ``window_start`` / ``window_end`` optionally clip the hour range to
    ``[start, end)``.
    """
    currencies = [c.upper() for c in (currencies or dopt._DEFAULT_CURRENCIES)]
    target_days = int(target_days or dopt._DEFAULT_TARGET_DAYS)
    min_strikes_per_wing = int(min_strikes_per_wing or dopt._DEFAULT_MIN_STRIKES_PER_WING)
    ingestion_time = ingestion_time or datetime.utcnow()

    frames = [_read_csv(p) for p in csv_paths]
    df = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]

    underlying_col = next((c for c in _UNDERLYING_COLS if c in df.columns), None)
    missing = [c for c in (_TIMESTAMP_COL, _SYMBOL_COL, _MARK_IV_COL) if c not in df.columns]
    if missing or underlying_col is None:
        need = list(missing)
        if underlying_col is None:
            need.append(f"one of {_UNDERLYING_COLS}")
        raise ValueError(
            f"Tardis CSV missing required column(s): {need}. Got columns: {list(df.columns)}"
        )

    # Keep just what we need; coerce numerics (non-parseable -> NaN -> dropped).
    df = df[[_TIMESTAMP_COL, _SYMBOL_COL, _MARK_IV_COL, underlying_col]].copy()
    df[_TIMESTAMP_COL] = pd.to_numeric(df[_TIMESTAMP_COL], errors="coerce")
    df[_MARK_IV_COL] = pd.to_numeric(df[_MARK_IV_COL], errors="coerce")
    df[underlying_col] = pd.to_numeric(df[underlying_col], errors="coerce")
    df = df.dropna(subset=[_TIMESTAMP_COL, _MARK_IV_COL, underlying_col])
    # Drop illiquid / not-yet-quoted strikes up front so "last quote in the
    # hour" lands on the last VALID quote (mirrors _parse_instruments' guard).
    df = df[(df[_MARK_IV_COL] > 0) & (df[underlying_col] > 0)]

    n_input_rows = len(df)
    if df.empty:
        return [], _empty_meta(currencies, "no usable rows after numeric clean")

    factor, iv_mode = _decide_iv_factor(df[_MARK_IV_COL], iv_units)

    # Currency from the instrument-name prefix (BTC-... / ETH-...); keep only
    # standard coin-margined option symbols (what the live feed surfaces).
    df["currency"] = df[_SYMBOL_COL].astype(str).str.split("-").str[0].str.upper()
    df = df[
        df[_SYMBOL_COL].astype(str).str.match(dopt._INSTRUMENT_RE.pattern)
        & df["currency"].isin(currencies)
    ]
    if df.empty:
        return [], _empty_meta(currencies, "no option rows for requested currencies", n_input_rows)

    unit = _detect_timestamp_unit(float(df[_TIMESTAMP_COL].median()))
    df["dt"] = pd.to_datetime(df[_TIMESTAMP_COL], unit=unit)  # naive UTC
    df["hour"] = df["dt"].dt.floor("1h")

    if window_start is not None:
        df = df[df["hour"] >= pd.Timestamp(window_start)]
    if window_end is not None:
        df = df[df["hour"] < pd.Timestamp(window_end)]
    if df.empty:
        return [], _empty_meta(currencies, "no rows inside [window_start, window_end)", n_input_rows)

    df["mark_iv_pct"] = df[_MARK_IV_COL] * factor
    df["underlying"] = df[underlying_col]

    # FLAG 3 (hourly snapshot choice): within each (currency, hour) bucket keep
    # the LAST quote per instrument (sort by raw timestamp ascending, take the
    # tail). That reconstructs the most-recent surface state observed in the
    # hour; we label it with the hour-floor event_time, matching the live feed
    # which floors the wall clock to the hour. (The alternative -- "state as of
    # the last update <= the hour boundary" -- would reach into the prior hour;
    # we deliberately keep each snapshot self-contained within [H, H+1).)
    df = df.sort_values(_TIMESTAMP_COL)
    latest = df.groupby(["currency", "hour", _SYMBOL_COL], sort=False).tail(1)

    rows: list[dict[str, Any]] = []
    n_snapshots = 0
    for (currency, hour), grp in latest.groupby(["currency", "hour"], sort=True):
        n_snapshots += 1
        result = [
            {"instrument_name": s, "mark_iv": iv, "underlying_price": u}
            for s, iv, u in zip(
                grp[_SYMBOL_COL], grp["mark_iv_pct"], grp["underlying"], strict=False
            )
        ]
        hour_py = pd.Timestamp(hour).to_pydatetime()  # naive UTC python datetime
        rows.extend(
            dopt._build_currency_rows(
                result,
                str(currency),
                hour_py,  # now: point-in-time for expiry selection + year-fraction
                hour_py,  # snapshot_time: event_time stamped on every row
                target_days,
                min_strikes_per_wing,
                ingestion_time=ingestion_time,
            )
        )

    event_times = [r["event_time"] for r in rows]
    meta = {
        "iv_mode": iv_mode,
        "iv_factor": factor,
        "n_input_rows": n_input_rows,
        "n_snapshots": n_snapshots,
        "n_macro_rows": len(rows),
        "request_start": min(event_times) if event_times else None,
        "earliest_event_time": min(event_times) if event_times else None,
        "latest_event_time": max(event_times) if event_times else None,
        "currencies": sorted(currencies),
        "note": None if rows else "no series produced (illiquid / too-thin surface)",
    }
    return rows, meta


def partition_history(
    rows: list[dict[str, Any]],
    *,
    ingestion_time: datetime,
    request_start: datetime | None,
) -> tuple[list[dict[str, Any]], list[tuple[dict[str, Any], str]]]:
    """FLAG 2. Backfill PIT split.

    Pass ``request_start`` = load-window start so historical event_times are
    accepted (rule #3 becomes "predates the requested window"), unlike the live
    feed's wall-clock lag guard which would drop every historical row.
    """
    return partition_by_pit(
        rows, config=_HISTORY_PIT_CONFIG, now=ingestion_time, request_start=request_start
    )


def load(
    csv_paths: list[str | Path],
    *,
    currencies: list[str] | None = None,
    target_days: int | None = None,
    min_strikes_per_wing: int | None = None,
    iv_units: str = "auto",
    window_start: datetime | None = None,
    window_end: datetime | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """End-to-end: read CSV(s) -> build series -> PIT -> (optionally) write DB.

    Returns a summary dict. With ``persist=False`` it computes everything but
    skips the DB write (useful for sanity-checking the first real sample).
    """
    ingestion_time = datetime.utcnow()
    rows, meta = build_macro_rows(
        csv_paths,
        currencies=currencies,
        target_days=target_days,
        min_strikes_per_wing=min_strikes_per_wing,
        iv_units=iv_units,
        ingestion_time=ingestion_time,
        window_start=window_start,
        window_end=window_end,
    )
    request_start = window_start or meta["request_start"]
    accepted, rejected = partition_history(
        rows, ingestion_time=ingestion_time, request_start=request_start
    )

    inserted = 0
    skipped = 0
    if persist and accepted:
        try:
            with get_connection() as conn:
                inserted, skipped = write_macro_raw_rows(accepted, conn=conn)
                update_source_health(
                    SOURCE_NAME,
                    success=True,
                    rows_inserted=inserted,
                    rows_rejected_pit=len(rejected),
                    conn=conn,
                )
        except Exception as e:
            logger.exception("deribit_options_history DB write failed")
            update_source_health(SOURCE_NAME, success=False, error_message=str(e)[:500])
            raise

    summary = {
        **meta,
        "rows_accepted": len(accepted),
        "rows_rejected_pit": len(rejected),
        "rows_inserted": inserted,
        "rows_skipped_duplicate": skipped,
        "persisted": bool(persist and accepted),
    }
    logger.info(
        "deribit_options_history | snapshots=%d macro_rows=%d accepted=%d "
        "rejected_pit=%d inserted=%d iv_mode=%s",
        meta["n_snapshots"], meta["n_macro_rows"], len(accepted),
        len(rejected), inserted, meta["iv_mode"],
    )
    return summary


def _parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s)


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="blackheart-ingest-deribit-history",
        description="Backfill the Deribit options-surface skew/term series from "
        "Tardis.dev options_chain CSV history.",
    )
    p.add_argument(
        "--csv",
        nargs="+",
        required=True,
        help="One or more Tardis options_chain CSV(.gz) paths (exchange=deribit).",
    )
    p.add_argument(
        "--currencies",
        type=str,
        default="BTC,ETH",
        help="Comma-separated currencies to load. Default BTC,ETH.",
    )
    p.add_argument(
        "--target-days",
        type=int,
        default=dopt._DEFAULT_TARGET_DAYS,
        help=f"The '30d' expiry bucket in days. Default {dopt._DEFAULT_TARGET_DAYS}.",
    )
    p.add_argument(
        "--min-strikes-per-wing",
        type=int,
        default=dopt._DEFAULT_MIN_STRIKES_PER_WING,
        help=f"Skip RR25 if a wing is thinner. Default {dopt._DEFAULT_MIN_STRIKES_PER_WING}.",
    )
    p.add_argument(
        "--iv-units",
        choices=["auto", "fraction", "percent"],
        default="auto",
        help="mark_iv units in the CSV (FLAG 1). 'auto' detects fraction vs "
        "percent from the median; override if the first sample proves it wrong.",
    )
    p.add_argument(
        "--start",
        type=_parse_iso,
        default=None,
        help="Optional ISO datetime (UTC, naive) lower bound on the snapshot hour.",
    )
    p.add_argument(
        "--end",
        type=_parse_iso,
        default=None,
        help="Optional ISO datetime (UTC, naive) exclusive upper bound on the hour.",
    )
    p.add_argument(
        "--no-persist",
        action="store_true",
        help="Compute + PIT but skip the DB write (dry-run / sanity check).",
    )
    return p


def main() -> int:
    configure_logging()
    args = _build_arg_parser().parse_args()
    currencies = [c.strip().upper() for c in args.currencies.split(",") if c.strip()]
    summary = load(
        args.csv,
        currencies=currencies,
        target_days=args.target_days,
        min_strikes_per_wing=args.min_strikes_per_wing,
        iv_units=args.iv_units,
        window_start=args.start,
        window_end=args.end,
        persist=not args.no_persist,
    )
    print("deribit_options_history load summary:")
    for k in (
        "iv_mode", "iv_factor", "n_input_rows", "n_snapshots", "n_macro_rows",
        "earliest_event_time", "latest_event_time", "rows_accepted",
        "rows_rejected_pit", "rows_inserted", "rows_skipped_duplicate", "persisted",
    ):
        print(f"  {k}: {summary.get(k)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
