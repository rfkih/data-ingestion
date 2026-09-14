"""Self-scheduled IDX jobs (APScheduler, Asia/Jakarta). Independent of the trading JVM.

Schedule (WIB):
  16:15 Mon-Fri   universe            Daftar Saham snapshot
  16:30-20:00     daily (every 15 min until today's bar has landed)
                  -> then index -> publish --since today-7 -> features --since today-45 -> candidates
                  -> on the first trading day of the month: regime check (COMPOSITE vs its 200-day average) and the
                     overlay tickets it calls for (cash / re-entry / entry) for books with an overlay on
                  -> paper ticket fill at today's open (paper book only; live fills are captured by hand)
                  -> book mark + check (live, paper): marks, NAV, holding alerts
  18:00 Mon-Fri   alert if today's bar has still not landed (holiday, or IDX late)
  20:30 Mon-Fri   announce_recent     all-emiten disclosures for the last 3 days -> idx.announcement / idx.event
  21:00 Mon-Fri   fundamentals        discover current fiscal year -> download pending workbooks (universe) -> parse
  09:00 Sat       fundamentals_full   same for the previous fiscal year too (late/restated filings)
  09:30 1st/month dividends           Yahoo dividend events for the universe (idx.dividend, source=yahoo)
  16:45 May 1-10  rebalance_due       alert if no rebalance ticket exists for the live book this year
  10:00 Sun       crosscheck          sample of codes: per-stock endpoint vs idx.bar

The universe for fundamentals/dividends is metrics.universe_codes (liquid today + recent candidates + watchlist).

Run: ``idx run-scheduler`` (foreground; Windows scheduled task / NSSM in practice).
Every run writes idx.ingest_run; problems become idx.alert rows for the app.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from ..shared.db import get_connection
from . import book, candidates, features, fin_store, overlay, publish, runlog, ticket
from .client import IdxClient, IdxFetchError
from .jobs import announce as job_announce
from .jobs import crosscheck as job_crosscheck
from .jobs import daily as job_daily
from .jobs import dividends as job_dividends
from .jobs import fin as job_fin
from .jobs import index as job_index
from .jobs import universe as job_universe
from .metrics import universe_codes

logger = logging.getLogger(__name__)
WIB = ZoneInfo("Asia/Jakarta")


def today_wib() -> date:
    return datetime.now(WIB).date()


def _fail_alert(conn, r: runlog.RunResult) -> None:
    if r.status == "failed":
        runlog.alert(conn, "critical", r.job, f"{r.job} {r.run_key}: {r.error}")


def run_universe() -> None:
    with get_connection() as conn, IdxClient() as cl:
        r = job_universe.run(conn, cl, today_wib())
        _fail_alert(conn, r)
        logger.info("idx universe %s %s rows=%s", r.run_key, r.status, r.rows_out)


def run_daily_chain(yahoo_dir: Path | None = None) -> None:
    """Called every 15 min in the publish window; no-op once today's bar is in."""
    d = today_wib()
    if d.weekday() >= 5:
        return
    with get_connection() as conn:
        if job_daily.latest_bar_date(conn) == d:
            return
        with IdxClient() as cl:
            r = job_daily.run(conn, cl, d)
            _fail_alert(conn, r)
            logger.info("idx daily %s %s rows=%s", d, r.status, r.rows_out)
            if r.status != "ok" or r.rows_out == 0:
                return
            ri = job_index.run(conn, cl, d)
            _fail_alert(conn, ri)
        rp = publish.publish(conn, since=publish.default_since(7), yahoo_dir=None)
        _fail_alert(conn, rp)
        logger.info("idx publish %s rows=%s", rp.status, rp.rows_out)
        rf = features.run(conn, since=d - timedelta(days=45))
        _fail_alert(conn, rf)
        logger.info("idx features %s rows=%s", rf.status, rf.rows_out)
        if rf.status == "ok":
            rc, _ = candidates.run(conn)
            _fail_alert(conn, rc)
            logger.info("idx candidates %s pool=%s selected=%s", rc.status, rc.detail.get("pool"), rc.detail.get("selected"))
        try:
            if overlay.first_trading_day_of_month(conn, d):
                rep = overlay.monthly_check(conn, d)
                logger.info("idx overlay check %s regime_on=%s books=%s", d, rep["regime"]["on"], [(x["book"], x["action"]) for x in rep["books"]])
        except Exception as e:                                          # the chain must go on
            runlog.alert(conn, "warning", "overlay", f"monthly check failed: {type(e).__name__}: {e}")
        try:
            for rep in ticket.paper_fill(conn, "paper"):
                logger.info("idx paper fill ticket #%s at %s: %s lines", rep["ticket"], rep["fill_date"], len(rep["fills"]))
        except Exception as e:                                          # the chain must go on to the marks
            runlog.alert(conn, "warning", "ticket:paper", f"paper fill failed: {type(e).__name__}: {e}")
        for bk in ("live", "paper"):
            rm = book.mark(conn, bk)
            _fail_alert(conn, rm)
            if rm.status == "ok":
                _fail_alert(conn, book.check(conn, bk))


def run_announce_recent(days: int = 3) -> None:
    """All-emiten disclosure feed, one request per calendar day (a day is well under the 1000-row page)."""
    d = today_wib()
    with get_connection() as conn, IdxClient() as cl:
        for k in range(days):
            day = d - timedelta(days=k)
            r = job_announce.run(conn, cl, "", day, day)
            _fail_alert(conn, r)
            if r.status == "failed":
                return
            logger.info("idx announce %s rows=%s events=%s", day, r.rows_out, r.detail.get("events"))


def run_fundamentals(previous_year: bool = False) -> None:
    """Discover new filings -> download pending workbooks for the universe -> parse into idx.fundamental."""
    y = today_wib().year
    years = [y - 1, y] if previous_year else [y]
    with get_connection() as conn, IdxClient() as cl:
        for yy in years:
            for p in job_fin.PERIODS:
                r = job_fin.discover(conn, cl, yy, p)
                _fail_alert(conn, r)
                if r.status == "failed":
                    return
        codes = universe_codes(conn)
        try:
            rd = job_fin.download(conn, cl, codes=codes, years=years)
        except IdxFetchError as e:
            runlog.alert(conn, "warning", "fin:download", f"aborted: {e}")
            return
        _fail_alert(conn, rd)
        logger.info("idx fin download %s pending=%s ok=%s", rd.status, rd.rows_in, rd.rows_out)
        rp = fin_store.run(conn, codes=codes)
        _fail_alert(conn, rp)
        logger.info("idx fin parse %s reports=%s", rp.status, rp.rows_out)


def check_rebalance_due() -> None:
    """Early May: remind the operator to build the annual ticket if none exists for this year's run."""
    d = today_wib()
    if not (d.month == 5 and d.day <= 10) or d.weekday() >= 5:
        return
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM idx.ticket WHERE book = 'live' AND mode = 'rebalance' AND ticket_date >= %s", (date(d.year, 4, 25),))
            row = cur.fetchone()
            n = next(iter(row.values())) if isinstance(row, dict) else row[0]
        if not n:
            runlog.alert(conn, "warning", "ticket", f"annual rebalance window ({d.year}): no rebalance ticket built yet - `idx ticket build --book live`")


def run_dividends() -> None:
    with get_connection() as conn:
        codes = universe_codes(conn)
        r = job_dividends.run(conn, codes)
        _fail_alert(conn, r)
        if r.detail.get("failed_codes", 0) > len(codes) // 10:
            runlog.alert(conn, "warning", "dividends", f"{r.detail['failed_codes']} of {len(codes)} codes failed on Yahoo")
        logger.info("idx dividends %s codes=%s rows=%s", r.status, len(codes), r.rows_out)


def run_macro() -> None:
    from . import macro as job_macro
    with get_connection() as conn:
        r = job_macro.pull(conn)
        _fail_alert(conn, r)
        if r.status == "partial":
            runlog.alert(conn, "warning", "macro", f"macro pull: {', '.join(r.detail.get('failed') or [])} failed; the rest refreshed")
        logger.info("idx macro %s rows=%s failed=%s", r.status, r.rows_out, r.detail.get("failed"))


def check_no_bar() -> None:
    d = today_wib()
    if d.weekday() >= 5:
        return
    with get_connection() as conn:
        if job_daily.latest_bar_date(conn) != d:
            runlog.alert(conn, "warning", "daily",
                         f"no bar for {d} by 18:00 WIB - holiday, or IDX has not published yet (retrying to 20:00)")


def run_crosscheck(sample: int = 60) -> None:
    with get_connection() as conn, IdxClient() as cl:
        try:
            r = job_crosscheck.run(conn, cl, sample=sample)
        except IdxFetchError as e:
            runlog.alert(conn, "warning", "crosscheck", f"aborted: {e}")
            return
        _fail_alert(conn, r)
        if r.detail.get("mismatch_codes"):
            runlog.alert(conn, "warning", "crosscheck",
                         f"{r.detail['mismatch_codes']} of {r.rows_in} sampled codes disagree with the per-stock endpoint (> 0.5 %)")


def build() -> BlockingScheduler:  # noqa: F821
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger

    s = BlockingScheduler(timezone=WIB, job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 3600})
    s.add_job(run_universe, CronTrigger(day_of_week="mon-fri", hour=16, minute=15, timezone=WIB), id="universe")
    s.add_job(run_daily_chain, CronTrigger(day_of_week="mon-fri", hour="16-19", minute="30,45,0,15", timezone=WIB),
              id="daily_chain")
    s.add_job(run_daily_chain, CronTrigger(day_of_week="mon-fri", hour=20, minute=0, timezone=WIB), id="daily_last")
    s.add_job(check_no_bar, CronTrigger(day_of_week="mon-fri", hour=18, minute=0, timezone=WIB), id="no_bar_alert")
    s.add_job(run_announce_recent, CronTrigger(day_of_week="mon-fri", hour=20, minute=30, timezone=WIB), id="announce_recent")
    s.add_job(run_macro, CronTrigger(day_of_week="mon-sat", hour=7, minute=30, timezone=WIB), id="macro")
    s.add_job(run_fundamentals, CronTrigger(day_of_week="mon-fri", hour=21, minute=0, timezone=WIB), id="fundamentals")
    s.add_job(run_fundamentals, CronTrigger(day_of_week="sat", hour=9, minute=0, timezone=WIB), id="fundamentals_full",
              kwargs={"previous_year": True})
    s.add_job(run_dividends, CronTrigger(day=1, hour=9, minute=30, timezone=WIB), id="dividends")
    s.add_job(check_rebalance_due, CronTrigger(month=5, day="1-10", hour=16, minute=45, timezone=WIB), id="rebalance_due")
    s.add_job(run_crosscheck, CronTrigger(day_of_week="sun", hour=10, minute=0, timezone=WIB), id="crosscheck")
    return s


def main() -> int:
    s = build()
    logger.info("idx scheduler starting (Asia/Jakarta); jobs: %s", [j.id for j in s.get_jobs()])
    try:
        s.start()
    except (KeyboardInterrupt, SystemExit):
        pass
    return 0
