"""``bar-open`` job - the opening price IDX leaves out, from Yahoo, accepted only where it can be shown to be right.

IDX's stock summary gives a name's open from the pre-opening auction (OpenPrice), else its FirstTrade; for names outside
the pre-opening session both are 0 and ``idx.bar.open`` is NULL (``open_missing``). That was ~90 % of traded bars in
2020-2024 and 25-35 % since 2025 - a hole in every feature built on the open (the daily model's gap, the ARA model's
gap_open, gap-fade research) and a made-up flat open (open = close) in ``market_data``.

Yahoo's ``.JK`` series has an open for those days. It is used ONLY where each check below holds, else the day keeps NULL:

  1. alignment   Yahoo's prices are split-adjusted, ours are raw: the day's ratio idx_close / yahoo_close must agree
                 within ALIGN_TOL with the median ratio of the surrounding days - a shifted date, a bad Yahoo row or a
                 split Yahoo has mis-dated all fail this.
  2. tick grid   the open, brought to our basis by that ratio, must land within SNAP_TOL of a price on IDX's tick grid
                 (every IDX print since 2020 sits on it, checked) and is then snapped to it.
  3. range       the snapped open must lie inside IDX's own low-high for the day.

  4. the date    on a date where Yahoo's opens disagree with the opens IDX DID publish for more than BAD_DATE_SHARE of
                 the names (2024-03-25/26, 2025-05-23, 2026-07-17, 2026-09-02: Yahoo took another price that day), no
                 Yahoo open is used at all.

Measured 2026-09-25 over 2020-2026 (research-scratch/idx/yahoo_open): on 294,221 days IDX published an open the rule
reproduces it exactly 99.76 % of the time (100 % in 2020-2023); on 2,103 sampled days IDX left out, Stockbit's own
historical open agrees with the filled one 99.43 % of the time - the misses mostly one or two ticks.

``validate`` measures the rule where the answer is known - the days IDX DID publish an open - and ``run`` refuses to write
unless that exact-match rate clears MIN_ACCURACY. Filled rows carry ``open_src = 'yahoo'``; ``open_missing`` keeps saying
that IDX published none.
"""
from __future__ import annotations

import logging
import statistics
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg

from .. import runlog

logger = logging.getLogger(__name__)
JOB = "bar_open"
ALIGN_TOL = 0.004          # the day's basis ratio within 0.4 % of its neighbours' median
ALIGN_WINDOW = 10          # neighbours each side for that median
SNAP_TOL = 0.25            # within a quarter tick of the grid
MIN_ACCURACY = 0.97        # the rule must reproduce IDX's own opens this often before it may fill anything
BAD_DATE_SHARE = 0.05      # a date where Yahoo disagrees with more than 5 % of IDX's published opens is not used
BAD_DATE_MIN = 20          # ... judged only where at least this many names had an IDX open that day


def tick(price: float) -> int:
    """IDX price fraction (in force for the whole 2020+ history; every published print sits on it)."""
    if price < 200:
        return 1
    if price < 500:
        return 2
    if price < 2000:
        return 5
    if price < 5000:
        return 10
    return 25


@dataclass(frozen=True)
class IdxDay:
    d: date
    open: float | None
    high: float
    low: float
    close: float
    src: str | None = None             # where `open` came from (idx.bar.open_src)


@dataclass(frozen=True)
class YDay:
    d: date
    open: float
    close: float


def derive(idx_days: list[IdxDay], ydays: dict[date, YDay]) -> dict[date, tuple[float | None, str]]:
    """For every IDX day: (the open Yahoo implies on our basis, or None) and the reason. Pure."""
    ratios: dict[date, float] = {}
    for x in idx_days:
        y = ydays.get(x.d)
        if y and y.close > 0 and x.close > 0:
            ratios[x.d] = x.close / y.close
    dates = [x.d for x in idx_days]
    out: dict[date, tuple[float | None, str]] = {}
    for i, x in enumerate(idx_days):
        y = ydays.get(x.d)
        if y is None or x.d not in ratios or not (y.open > 0):
            out[x.d] = (None, "not_on_yahoo")
            continue
        near = [ratios[dates[j]] for j in range(max(0, i - ALIGN_WINDOW), min(len(dates), i + ALIGN_WINDOW + 1))
                if j != i and dates[j] in ratios]
        if len(near) < 3:
            out[x.d] = (None, "too_few_neighbours")
            continue
        med = statistics.median(near)
        r = ratios[x.d]
        if abs(r / med - 1) > ALIGN_TOL:
            out[x.d] = (None, "misaligned")
            continue
        raw = y.open * r
        t = tick(raw)
        snapped = round(raw / t) * t
        if abs(raw - snapped) > SNAP_TOL * t:
            out[x.d] = (None, "off_grid")
            continue
        if tick(snapped) != t and snapped % tick(snapped) != 0:          # snapped across a band edge onto a bad price
            out[x.d] = (None, "off_grid")
            continue
        if not (x.low <= snapped <= x.high):
            out[x.d] = (None, "outside_range")
            continue
        out[x.d] = (float(snapped), "ok")
    return out


# ---------------------------------------------------------------------------------------------------------------- data
def load_idx(conn: psycopg.Connection, codes: Iterable[str] | None, since: date) -> dict[str, list[IdxDay]]:
    """Traded bars per code, oldest first (a day with no trade has no open to find)."""
    with conn.cursor() as cur:
        cur.execute("""SELECT code, trade_date, open, high, low, close, open_src FROM idx.bar
                        WHERE trade_date >= %s AND volume > 0 AND (%s::text[] IS NULL OR code = ANY(%s))
                        ORDER BY code, trade_date""", (since, list(codes) if codes else None, list(codes) if codes else None))
        out: dict[str, list[IdxDay]] = {}
        for r in cur.fetchall():
            code, d, o, h, lo, c, src = ((r["code"], r["trade_date"], r["open"], r["high"], r["low"], r["close"], r["open_src"])
                                         if isinstance(r, dict) else r)
            out.setdefault(code, []).append(IdxDay(d, float(o) if o is not None else None, float(h), float(lo), float(c), src))
    return out


def fetch_yahoo(codes: list[str], start: date, end: date, cache: Path | None = None) -> dict[str, dict[date, YDay]]:
    """Daily open/close per code from Yahoo (``<code>.JK``, split-adjusted, not dividend-adjusted), in batches."""
    import pandas as pd
    import yfinance as yf
    out: dict[str, dict[date, YDay]] = {}
    for i in range(0, len(codes), 80):
        batch = codes[i:i + 80]
        part = cache / f"yahoo_{start}_{end}_{i:04d}.pkl" if cache else None
        if part and part.exists():
            df = pd.read_pickle(part)
        else:
            df = yf.download([f"{c}.JK" for c in batch], start=start.isoformat(), end=(end + timedelta(days=1)).isoformat(),
                             progress=False, auto_adjust=False, group_by="ticker", threads=True)
            if part:
                part.parent.mkdir(parents=True, exist_ok=True)
                df.to_pickle(part)
        for c in batch:
            sym = f"{c}.JK"
            if sym not in df.columns.get_level_values(0):
                continue
            sub = df[sym][["Open", "Close"]].dropna()
            out[c] = {ix.date(): YDay(ix.date(), float(o), float(cl)) for ix, (o, cl) in sub.iterrows() if cl > 0}
        logger.info("yahoo opens: %s/%s codes", min(i + 80, len(codes)), len(codes))
    return out


# ---------------------------------------------------------------------------------------------------------------- measure
def bad_dates(idx: dict[str, list[IdxDay]], derived: dict[str, dict[date, tuple[float | None, str]]]) -> set[date]:
    """Dates on which Yahoo's open disagrees with IDX's published one for more than BAD_DATE_SHARE of the names."""
    n: dict[date, int] = {}
    miss: dict[date, int] = {}
    for code, days in idx.items():
        got = derived[code]
        for x in days:
            o = got[x.d][0]
            if x.open is None or o is None:
                continue
            n[x.d] = n.get(x.d, 0) + 1
            miss[x.d] = miss.get(x.d, 0) + (abs(o - x.open) > 1e-9)
    return {d for d, k in n.items() if k >= BAD_DATE_MIN and miss.get(d, 0) / k > BAD_DATE_SHARE}


def validate(idx: dict[str, list[IdxDay]], yahoo: dict[str, dict[date, YDay]]) -> dict[str, Any]:
    """The rule scored where IDX published an open: accepted share, and exact matches among the accepted, by year.
    Scored with the bad dates left out, as `run` fills - and a date is judged bad from its own mismatches, so the
    accuracy on the remaining dates is also shown per year to make that circularity visible."""
    derived = {c: derive(days, yahoo.get(c, {})) for c, days in idx.items()}
    bad = bad_dates(idx, derived)
    by_year: dict[int, dict[str, int]] = {}
    reasons: dict[str, int] = {}
    misses: list[tuple[str, str, float, float]] = []
    fillable = 0
    for code, days in idx.items():
        got = derived[code]
        for x in days:
            o, why = got[x.d]
            if x.d in bad:
                o, why = None, "bad_date"
            if x.open is None:
                fillable += why == "ok"
                continue
            s = by_year.setdefault(x.d.year, {"known": 0, "accepted": 0, "exact": 0})
            s["known"] += 1
            reasons[why] = reasons.get(why, 0) + 1
            if o is None:
                continue
            s["accepted"] += 1
            if abs(o - x.open) < 1e-9:
                s["exact"] += 1
            elif len(misses) < 20:
                misses.append((code, x.d.isoformat(), o, x.open))
    tot = {k: sum(v[k] for v in by_year.values()) for k in ("known", "accepted", "exact")}
    return {"by_year": dict(sorted(by_year.items())), "total": tot,
            "accuracy": tot["exact"] / tot["accepted"] if tot["accepted"] else None,
            "coverage": tot["accepted"] / tot["known"] if tot["known"] else None,
            "reasons_on_known": reasons, "fillable_missing": fillable, "sample_mismatches": misses,
            "bad_dates": sorted(d.isoformat() for d in bad)}


# ---------------------------------------------------------------------------------------------------------------- write
def run(conn: psycopg.Connection, *, since: date, codes: list[str] | None = None, cache: Path | None = None,
        fetch: Callable[..., dict[str, dict[date, YDay]]] = fetch_yahoo, dry_run: bool = False) -> tuple[runlog.RunResult, dict[str, Any]]:
    """Validate the rule on this window, then fill the missing opens it accepts - unless its accuracy is below the bar."""
    r = runlog.RunResult(JOB, since.isoformat())
    run_id = runlog.start(conn, JOB, r.run_key)
    report: dict[str, Any] = {}
    try:
        # the ratio check needs neighbours before the window
        idx = load_idx(conn, codes, since - timedelta(days=40))
        want = [c for c, days in idx.items() if any(x.open is None and x.d >= since for x in days)]
        # validation uses every code's known opens in the window, so it is scored on the same stretch it fills
        yahoo = fetch(sorted(idx), since - timedelta(days=40), date.today(), cache) if idx else {}
        report = validate({c: [x for x in d] for c, d in idx.items()}, yahoo)
        r.rows_in = sum(1 for d in idx.values() for x in d if x.open is None and x.d >= since)
        acc = report["accuracy"]
        r.detail.update({"accuracy": acc, "coverage": report["coverage"], "known_scored": report["total"]["accepted"]})
        if acc is None or acc < MIN_ACCURACY or report["total"]["accepted"] < 200:
            r.status, r.error = "failed", f"rule not trusted on this window: accuracy {acc} on {report['total']['accepted']} known opens"
            runlog.finish(conn, run_id, r)
            return r, report
        bad = {date.fromisoformat(d) for d in report["bad_dates"]}
        rows = []
        for c in want:
            got = derive(idx[c], yahoo.get(c, {}))
            for x in idx[c]:
                if x.open is None and x.d >= since and x.d not in bad:
                    o, _why = got[x.d]
                    if o is not None:
                        rows.append((Decimal(str(o)), c, x.d))
        if not dry_run and rows:
            with conn.cursor() as cur:
                cur.executemany("""UPDATE idx.bar SET open = %s, open_src = 'yahoo', updated_at = now()
                                    WHERE code = %s AND trade_date = %s AND open IS NULL""", rows)
            conn.commit()
        r.rows_out = 0 if dry_run else len(rows)
        r.detail.update({"filled": len(rows), "dry_run": dry_run, "left_missing": r.rows_in - len(rows), "bad_dates": report["bad_dates"]})
        r.status = "ok"
    except Exception as e:  # recorded on the run row; a day without an open keeps its close
        conn.rollback()
        r.status, r.error = "failed", str(e)[:500]
        logger.warning("bar opens failed: %s", e)
    runlog.finish(conn, run_id, r)
    return r, report


# ---------------------------------------------------------------------------------------------------------------- Stockbit
# The second source, for what Yahoo cannot give: names Yahoo dropped (delisted - their missing opens would otherwise tell a
# model which names were going to die), days it misaligns on, and the dates it got wrong. Same four checks, same bar: the
# rule must reproduce the opens already known in the fetched windows (IDX's own, and separately the Yahoo fills) before it
# may write. Stockbit's daily summary answers at most 50 rows and about a year per request.
STOCKBIT_URL = ("https://exodus.stockbit.com/company-price-feed/historical/summary/{code}?period=HS_PERIOD_DAILY"
                "&start_date={start}&end_date={end}&limit=50&page={page}")
STOCKBIT_PACE = 0.7              # seconds between requests
WINDOW_PAD = timedelta(days=30)  # neighbours either side of a missing day, for the alignment check


class StockbitStop(RuntimeError):
    """Auth, paywall or rate limit: stop the whole run (what was fetched is cached; a re-run resumes)."""


def windows(missing: list[date]) -> list[tuple[date, date]]:
    """Missing days grouped into fetch windows padded with neighbours, each within one calendar year (the API's span)."""
    out: list[tuple[date, date]] = []
    for d in sorted(missing):
        lo, hi = d - WINDOW_PAD, d + WINDOW_PAD
        if out and lo <= out[-1][1] and (hi - out[-1][0]).days <= 360:
            out[-1] = (out[-1][0], hi)
        else:
            out.append((lo, hi))
    return out


def fetch_stockbit(code: str, start: date, end: date, headers: dict[str, str], cache: Path | None,
                   get: Callable[[str, dict[str, str]], tuple[int, bytes]] | None = None) -> dict[date, YDay]:
    import json
    import time
    import urllib.error
    import urllib.request

    part = cache / "stockbit" / f"{code}_{start}_{end}.json" if cache else None
    if part and part.exists():
        rows = json.loads(part.read_text())
    else:
        def _get(url: str, h: dict[str, str]) -> tuple[int, bytes]:
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=30) as resp:
                    return resp.status, resp.read()
            except urllib.error.HTTPError as e:
                return e.code, e.read()
        rows = []
        for page in range(1, 20):
            status, body = (get or _get)(STOCKBIT_URL.format(code=code, start=start, end=end, page=page), headers)
            if status in (401, 402, 403, 429):
                raise StockbitStop(f"HTTP {status} on {code}")
            if status != 200:
                break
            got = json.loads(body).get("data", {}).get("result") or []
            rows += [{"date": x["date"], "open": x.get("open"), "close": x.get("close")} for x in got]
            if get is None:
                time.sleep(STOCKBIT_PACE)
            if len(got) < 50:
                break
        if part:
            part.parent.mkdir(parents=True, exist_ok=True)
            part.write_text(json.dumps(rows))
    return {date.fromisoformat(x["date"]): YDay(date.fromisoformat(x["date"]), float(x["open"]), float(x["close"]))
            for x in rows if x.get("open") and x.get("close")}


def _only(idx: dict[str, list[IdxDay]], srcs: set[str]) -> dict[str, list[IdxDay]]:
    """The same bars with the known opens kept only where they came from `srcs` (the rest scored as unknown)."""
    return {c: [x if x.src in srcs else IdxDay(x.d, None, x.high, x.low, x.close, None) for x in days] for c, days in idx.items()}


def run_stockbit(conn: psycopg.Connection, *, since: date, headers: dict[str, str], codes: list[str] | None = None,
                 cache: Path | None = None, dry_run: bool = False,
                 get: Callable[[str, dict[str, str]], tuple[int, bytes]] | None = None) -> tuple[runlog.RunResult, dict[str, Any]]:
    """Fill the opens still missing after the Yahoo pass from Stockbit, under the same rule and the same accuracy bar."""
    r = runlog.RunResult(JOB + ":stockbit", since.isoformat())
    run_id = runlog.start(conn, r.job, r.run_key)
    report: dict[str, Any] = {}
    try:
        idx = load_idx(conn, codes, since - WINDOW_PAD - timedelta(days=10))
        missing = {c: [x.d for x in days if x.open is None and x.d >= since] for c, days in idx.items()}
        missing = {c: v for c, v in missing.items() if v}
        plan = {c: windows(v) for c, v in missing.items()}
        r.rows_in = sum(len(v) for v in missing.values())
        r.detail["windows"] = sum(len(v) for v in plan.values())
        sb: dict[str, dict[date, YDay]] = {}
        stopped = None
        for n, (c, ws) in enumerate(sorted(plan.items())):
            got_c: dict[date, YDay] = {}
            try:
                for a, b in ws:
                    got_c.update(fetch_stockbit(c, a, b, headers, cache, get))
            except StockbitStop as e:
                stopped = str(e)
                break
            sb[c] = got_c
            if n % 50 == 0:
                logger.info("stockbit opens: %s/%s codes", n, len(plan))
        # score where the answer is known, inside the fetched windows only
        fetched = {c: [x for x in idx[c] if x.d in sb[c]] for c in sb}
        vs_idx = validate(_only(fetched, {"idx"}), sb)
        vs_yahoo = validate(_only(fetched, {"yahoo"}), sb)
        allk = validate(_only(fetched, {"idx", "yahoo"}), sb)
        report = {"vs_idx": {k: vs_idx[k] for k in ("total", "accuracy", "sample_mismatches")},
                  "vs_yahoo": {k: vs_yahoo[k] for k in ("total", "accuracy", "sample_mismatches")},
                  "bad_dates": allk["bad_dates"], "stopped": stopped}
        acc = allk["accuracy"]
        r.detail.update({"accuracy_vs_idx": vs_idx["accuracy"], "accuracy_vs_yahoo": vs_yahoo["accuracy"],
                         "scored": allk["total"]["accepted"], "stopped": stopped})
        if acc is None or acc < MIN_ACCURACY or allk["total"]["accepted"] < 200:
            r.status, r.error = "failed", f"rule not trusted on Stockbit: accuracy {acc} on {allk['total']['accepted']} known opens"
            runlog.finish(conn, run_id, r)
            return r, report
        bad = {date.fromisoformat(d) for d in allk["bad_dates"]}
        rows = []
        for c, want in missing.items():
            if c not in sb:
                continue
            got = derive(idx[c], sb[c])
            for d in want:
                o, _why = got[d]
                if o is not None and d not in bad:
                    rows.append((Decimal(str(o)), c, d))
        if not dry_run and rows:
            with conn.cursor() as cur:
                cur.executemany("""UPDATE idx.bar SET open = %s, open_src = 'stockbit', updated_at = now()
                                    WHERE code = %s AND trade_date = %s AND open IS NULL""", rows)
            conn.commit()
        r.rows_out = 0 if dry_run else len(rows)
        r.detail.update({"filled": len(rows), "left_missing": r.rows_in - len(rows), "dry_run": dry_run})
        r.status = "partial" if stopped else "ok"
    except Exception as e:  # recorded on the run row
        conn.rollback()
        r.status, r.error = "failed", str(e)[:500]
        logger.warning("stockbit opens failed: %s", e)
    runlog.finish(conn, run_id, r)
    return r, report
