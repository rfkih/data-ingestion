"""Read ``feature_values`` + ``feature_registry``.

Inference needs:
  * the version of each feature in the model's feature_set — pinned by
    the artifact when available, else the latest ``registered`` version
  * scope + forward-fill metadata so global features resolve correctly
  * the values at the timestamp(s) being inferred

The schema (V70) keys feature_values on
``(feature_name, version, symbol, interval, ts)``. Per-bar features
carry ``symbol``/``interval`` filled; GLOBAL features (macro, DVOL, …)
carry empty strings in both. blackheart-train's loader splits on
``bool(symbols) and bool(intervals)`` from feature_registry and
forward-fills globals onto the bar grid with a per-feature hour cap
(``max_ffill_age_hours``, default 24*7) when ``ffill_policy =
'last_value'``. This module mirrors those semantics exactly so the
serving-time feature vector matches what the model trained on.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import asyncpg

# Mirror of blackheart_train.loader's global-ffill default cap (hours).
_DEFAULT_GLOBAL_FFILL_CAP_HOURS = 24 * 7


@dataclass(frozen=True)
class FeatureMeta:
    """Registry metadata inference needs per model input."""

    name: str
    version: int
    is_global: bool
    ffill_policy: str | None
    max_ffill_age_hours: float | None

    @property
    def ffill_cap_hours(self) -> float:
        return (
            float(self.max_ffill_age_hours)
            if self.max_ffill_age_hours
            else float(_DEFAULT_GLOBAL_FFILL_CAP_HOURS)
        )


async def get_latest_ts(
    conn: asyncpg.Connection,
) -> datetime | None:
    """Get the latest timestamp from feature_values.

    Returns None if no rows exist in feature_values (empty table).
    """
    row = await conn.fetchrow(
        """
        SELECT MAX(ts) as latest_ts
          FROM feature_values
        """
    )
    if row and row["latest_ts"]:
        return row["latest_ts"]
    return None


async def get_latest_ts_for(
    conn: asyncpg.Connection, symbol: str, interval_name: str
) -> datetime | None:
    """Latest feature_values ts for ONE (symbol, interval).

    The global :func:`get_latest_ts` is interval-agnostic — its MAX(ts) is
    almost always a 15m timestamp once any 15m symbol streams, so evaluating
    a 1h signal there finds no feature row and skips it (the row then falls to
    the catchup_scan fallback). Each signal must be inferred at the latest bar
    for ITS OWN interval. Returns None when that surface has no rows.
    """
    row = await conn.fetchrow(
        """
        SELECT MAX(ts) AS latest_ts
          FROM feature_values
         WHERE symbol = $1 AND interval = $2
        """,
        symbol,
        interval_name,
    )
    if row and row["latest_ts"]:
        return row["latest_ts"]
    return None


async def fetch_feature_meta(
    conn: asyncpg.Connection,
    feature_names: list[str],
    pinned_versions: dict[str, int] | None = None,
) -> dict[str, FeatureMeta]:
    """Map feature_name → :class:`FeatureMeta` for registered features.

    Version resolution: the artifact's pinned version wins when present
    (train/serve parity — the model must be fed the versions it trained
    on); otherwise the latest ``registered`` version, which is what
    blackheart-train resolves at training time. Names absent from the
    registry are absent from the result — the caller surfaces that as
    ``feature_not_registered``.

    Returns an empty dict for an empty input — no SQL fired.
    """
    if not feature_names:
        return {}
    pinned = pinned_versions or {}
    rows = await conn.fetch(
        """
        SELECT feature_name, version, symbols, intervals,
               ffill_policy, max_ffill_age_hours
          FROM feature_registry
         WHERE feature_name = ANY($1::text[])
           AND status = 'registered'
        """,
        feature_names,
    )
    # Highest registered version per name; scope/ffill metadata rides
    # along with whichever row wins (scope is name-level in practice).
    best: dict[str, Any] = {}
    for r in rows:
        name = r["feature_name"]
        if name not in best or int(r["version"]) > int(best[name]["version"]):
            best[name] = r
    out: dict[str, FeatureMeta] = {}
    for name, r in best.items():
        symbols = r["symbols"] or []
        intervals = r["intervals"] or []
        is_per_bar = bool(symbols) and bool(intervals)
        out[name] = FeatureMeta(
            name=name,
            version=int(pinned.get(name, r["version"])),
            is_global=not is_per_bar,
            ffill_policy=r["ffill_policy"],
            max_ffill_age_hours=r["max_ffill_age_hours"],
        )
    return out


def _split_metas(
    metas: dict[str, FeatureMeta],
) -> tuple[list[FeatureMeta], list[FeatureMeta], list[FeatureMeta]]:
    """(per_bar, global_ffill, global_exact) in input order."""
    per_bar = [m for m in metas.values() if not m.is_global]
    global_ffill = [
        m for m in metas.values() if m.is_global and m.ffill_policy == "last_value"
    ]
    global_exact = [
        m for m in metas.values() if m.is_global and m.ffill_policy != "last_value"
    ]
    return per_bar, global_ffill, global_exact


async def fetch_per_bar_values_at_ts(
    conn: asyncpg.Connection,
    *,
    metas: dict[str, FeatureMeta],
    symbol: str,
    interval_name: str,
    ts: datetime,
) -> dict[str, float | None]:
    """Return ``{feature_name: value or None}`` at ``ts``.

    Per-bar features match exactly at ``(symbol, interval, ts)`` — no
    forward-fill at the boundary (PIT-correctness; fills across older
    bars are a registry-time concern). Global features match at
    ``(symbol='', interval='')``; when their registry row says
    ``ffill_policy='last_value'`` the most recent value with
    ``ts <= bar ts`` within ``max_ffill_age_hours`` applies — the exact
    backward-asof-with-tolerance blackheart-train trains with. None
    entries surface as the caller's "missing feature" error — inference
    never fabricates a value.
    """
    if not metas:
        return {}
    out: dict[str, float | None] = {name: None for name in metas}

    per_bar, global_ffill, global_exact = _split_metas(metas)

    if per_bar:
        rows = await conn.fetch(
            """
            WITH wanted AS (
              SELECT unnest($1::text[]) AS feature_name,
                     unnest($2::int[])  AS version
            )
            SELECT fv.feature_name, fv.value
              FROM feature_values fv
              JOIN wanted w
                ON w.feature_name = fv.feature_name
               AND w.version      = fv.version
             WHERE fv.symbol   = $3
               AND fv.interval = $4
               AND fv.ts       = $5
            """,
            [m.name for m in per_bar], [m.version for m in per_bar],
            symbol, interval_name, ts,
        )
        for r in rows:
            v = r["value"]
            out[r["feature_name"]] = float(v) if v is not None else None

    if global_exact:
        rows = await conn.fetch(
            """
            WITH wanted AS (
              SELECT unnest($1::text[]) AS feature_name,
                     unnest($2::int[])  AS version
            )
            SELECT fv.feature_name, fv.value
              FROM feature_values fv
              JOIN wanted w
                ON w.feature_name = fv.feature_name
               AND w.version      = fv.version
             WHERE fv.symbol   = ''
               AND fv.interval = ''
               AND fv.ts       = $3
            """,
            [m.name for m in global_exact], [m.version for m in global_exact],
            ts,
        )
        for r in rows:
            v = r["value"]
            out[r["feature_name"]] = float(v) if v is not None else None

    if global_ffill:
        # Latest row per feature with ts <= bar ts, within the feature's
        # own cap. DISTINCT ON keeps one row per feature (newest first).
        rows = await conn.fetch(
            """
            WITH wanted AS (
              SELECT unnest($1::text[])   AS feature_name,
                     unnest($2::int[])    AS version,
                     unnest($3::float8[]) AS cap_hours
            )
            SELECT DISTINCT ON (fv.feature_name)
                   fv.feature_name, fv.value
              FROM feature_values fv
              JOIN wanted w
                ON w.feature_name = fv.feature_name
               AND w.version      = fv.version
             WHERE fv.symbol   = ''
               AND fv.interval = ''
               AND fv.ts       <= $4
               AND fv.ts       >= $4 - (w.cap_hours * interval '1 hour')
             ORDER BY fv.feature_name, fv.ts DESC
            """,
            [m.name for m in global_ffill],
            [m.version for m in global_ffill],
            [m.ffill_cap_hours for m in global_ffill],
            ts,
        )
        for r in rows:
            v = r["value"]
            out[r["feature_name"]] = float(v) if v is not None else None

    return out


def asof_pick(
    series: list[tuple[datetime, float | None]],
    ts: datetime,
    cap_hours: float,
) -> float | None:
    """Backward as-of lookup with a time cap over a ts-ascending series.

    Returns the value of the latest entry with ``entry_ts <= ts`` and
    ``ts - entry_ts <= cap_hours`` — the in-Python mirror of train's
    ``merge_asof(direction='backward', tolerance=cap)``. Exposed at
    module level (not underscored) so the unit suite can pin the
    boundary semantics without a DB.
    """
    if not series:
        return None
    idx = bisect_right(series, ts, key=lambda kv: kv[0]) - 1
    if idx < 0:
        return None
    entry_ts, value = series[idx]
    if ts - entry_ts > timedelta(hours=cap_hours):
        return None
    return value


async def fetch_per_bar_values_range(
    conn: asyncpg.Connection,
    *,
    metas: dict[str, FeatureMeta],
    symbol: str,
    interval_name: str,
    start: datetime,
    end: datetime,
) -> dict[datetime, dict[str, float | None]]:
    """Return ``{ts: {feature_name: value or None}}`` over ``[start, end)``.

    The grid's timestamps come from the PER-BAR rows (the bar grid);
    global features are then resolved onto each grid ts with the same
    exact-or-asof semantics as :func:`fetch_per_bar_values_at_ts`. Cap
    enforcement lives at the API layer (``Settings.max_backfill_rows``)
    — repo trusts inputs.
    """
    if not metas:
        return {}
    all_names = list(metas)
    per_bar, global_ffill, global_exact = _split_metas(metas)

    out: dict[datetime, dict[str, float | None]] = {}
    if per_bar:
        rows = await conn.fetch(
            """
            WITH wanted AS (
              SELECT unnest($1::text[]) AS feature_name,
                     unnest($2::int[])  AS version
            )
            SELECT fv.ts, fv.feature_name, fv.value
              FROM feature_values fv
              JOIN wanted w
                ON w.feature_name = fv.feature_name
               AND w.version      = fv.version
             WHERE fv.symbol   = $3
               AND fv.interval = $4
               AND fv.ts >= $5
               AND fv.ts <  $6
             ORDER BY fv.ts ASC
            """,
            [m.name for m in per_bar], [m.version for m in per_bar],
            symbol, interval_name, start, end,
        )
        for r in rows:
            ts = r["ts"]
            slot = out.setdefault(ts, {name: None for name in all_names})
            v = r["value"]
            slot[r["feature_name"]] = float(v) if v is not None else None

    if not out or not (global_ffill or global_exact):
        return out

    grid_ts = sorted(out.keys())

    # One range read per scope covers every grid ts; ffill features need
    # lookback before ``start`` up to the widest cap.
    global_series: dict[str, list[tuple[datetime, float | None]]] = {}
    ffill_and_exact = global_ffill + global_exact
    max_cap = max((m.ffill_cap_hours for m in global_ffill), default=0.0)
    rows = await conn.fetch(
        """
        WITH wanted AS (
          SELECT unnest($1::text[]) AS feature_name,
                 unnest($2::int[])  AS version
        )
        SELECT fv.ts, fv.feature_name, fv.value
          FROM feature_values fv
          JOIN wanted w
            ON w.feature_name = fv.feature_name
           AND w.version      = fv.version
         WHERE fv.symbol   = ''
           AND fv.interval = ''
           AND fv.ts >= $3
           AND fv.ts <  $4
         ORDER BY fv.ts ASC
        """,
        [m.name for m in ffill_and_exact],
        [m.version for m in ffill_and_exact],
        start - timedelta(hours=max_cap), end,
    )
    for r in rows:
        v = r["value"]
        global_series.setdefault(r["feature_name"], []).append(
            (r["ts"], float(v) if v is not None else None)
        )

    for m in global_exact:
        by_ts = dict(global_series.get(m.name, []))
        for ts in grid_ts:
            if ts in by_ts:
                out[ts][m.name] = by_ts[ts]

    for m in global_ffill:
        series = global_series.get(m.name, [])
        for ts in grid_ts:
            out[ts][m.name] = asof_pick(series, ts, m.ffill_cap_hours)

    return out
