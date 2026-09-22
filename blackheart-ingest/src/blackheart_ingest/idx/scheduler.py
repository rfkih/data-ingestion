"""Self-scheduled IDX jobs (APScheduler, Asia/Jakarta). Independent of the trading JVM.

Schedule (WIB):
  16:15 Mon-Fri   universe            Daftar Saham snapshot
  16:30-20:00     daily (every 15 min until today's bar has landed)
                  -> then index -> publish --since today-7 -> features --since today-45 -> candidates
                  -> on the first trading day of the month: regime check (COMPOSITE vs its 200-day average) and the
                     overlay tickets it calls for (cash / re-entry / entry) for books with an overlay on
                  -> paper ticket fill at today's open (paper book only; live fills are captured by hand)
                  -> book mark + check (live, paper): marks, NAV, holding alerts
  09:00, 09:05    gapfade_entry       intraday gap-fade books: the opening auction printed at ~08:58 -> scan, sweep, entry ticket
  15:50 Mon-Fri   gapfade_exit        intraday gap-fade books: sell everything into the closing auction
  every 10 min    token_guard         the Stockbit session must outlive today's close; renews, else nags the phone every run
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
from datetime import UTC, date, datetime, timedelta
from datetime import time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

from ..shared.db import get_connection
from . import (
    book,
    candidates,
    features,
    fin_store,
    levels,
    overlay,
    publish,
    runlog,
    scores,
    ticket,
    trend_book,
)
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
        books = [r["book"] for r in _all_books(conn)]
        for bk in [x for x in books if ticket.is_paper(x)]:
            try:
                for rep in ticket.paper_fill(conn, bk):
                    logger.info("idx paper fill %s ticket #%s at %s: %s lines", bk, rep["ticket"], rep["fill_date"], len(rep["fills"]))
            except Exception as e:                                      # the chain must go on to the marks
                runlog.alert(conn, "warning", f"ticket:{bk}", f"paper fill failed: {type(e).__name__}: {e}")
        from . import gapfade  # the intraday book settles at the official close
        for bk in gapfade.gapfade_books(conn):
            try:
                rep = gapfade.settle(conn, bk)
                logger.info("idx gapfade settle %s: %s", bk, rep)
            except Exception as e:
                runlog.alert(conn, "warning", f"gapfade:{bk}", f"settle failed: {type(e).__name__}: {e}")
        for bk in books:
            rm = book.mark(conn, bk)
            _fail_alert(conn, rm)
            if rm.status == "ok":
                _fail_alert(conn, book.check(conn, bk))
        for bk in trend_book.trend_books(conn):                          # tonight's breakout/trailing-stop ticket per trend book
            try:
                rep = trend_book.run(conn, bk)
                logger.info("idx trend %s: %s", bk, rep)
            except Exception as e:
                runlog.alert(conn, "warning", f"ticket:{bk}", f"trend ticket failed: {type(e).__name__}: {e}")
                _fail_alert(conn, levels.check(conn, bk))                   # stop / take-profit / index levels
        try:                                                                # the public scores for the day (spec §04); fails soft
            rep = scores.build(conn)
            logger.info("idx scores: %s", rep)
        except Exception as e:
            runlog.alert(conn, "warning", "scores", f"scores failed: {type(e).__name__}: {e}")


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


def _all_books(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute("SELECT book FROM idx.book WHERE book NOT LIKE 'test%%' AND archived_at IS NULL ORDER BY book")
        return [r if isinstance(r, dict) else {"book": r[0]} for r in cur.fetchall()]


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


def run_broker_snapshot() -> None:
    """Today's free broker-distribution snapshot for the liquid universe (card context; not a desk dependency).

    Off unless a Stockbit token is known (STOCKBIT_TOKEN / STOCKBIT_REFRESH_TOKEN in idx-local.env, or the relay row
    in idx.feed_token). Auto-refreshes from the newest refresh token first; a paywall/expired key stops the run
    cleanly and raises one warning, not a crash.
    """
    import os as _os

    from . import broker
    d = today_wib()
    if d.weekday() >= 5:
        return
    with get_connection() as conn:
        if not (_os.environ.get(broker.TOKEN_ENV) or broker.newest_refresh_token(conn=conn)):
            return
        try:
            cfg = broker.config_fresh(conn=conn)
            codes = universe_codes(conn)
            res = broker.snapshot(conn, codes, cfg, expected_date=job_daily.latest_bar_date(conn), log=logger.info)
        except broker.BrokerFetchError as e:
            runlog.alert(conn, "warning", "broker", f"broker snapshot: {e}")
            logger.warning("idx broker snapshot: %s", e)
            return
        if res["stopped"]:
            runlog.alert(conn, "warning", "broker", f"broker snapshot stopped: {res['stopped']}")
        logger.info("idx broker snapshot %s ok=%s failed=%s rows=%s", res.get("date"), res["ok"], res["failed"], res["rows"])


def run_feed_watch() -> None:
    """During the session: one warning when the datafeed collector's heartbeat is stale or it is not live (token expired,
    reconnecting for too long, task dead). Dedup is runlog's (same job+message stays one open alert)."""
    from .feed import store as fs
    from .feed.collector import in_session
    if not in_session():
        return
    with get_connection() as conn:
        st = fs.status(conn)
        c = st["collector"]
        state, stale = c.get("state"), c.get("stale_s")
        if state == "off" or stale is None or stale > 180:
            runlog.alert(conn, "warning", "feed", f"datafeed collector not running (state {state}, heartbeat {stale} s ago) - "
                                                  "check the 'Blackheart IDX feed' task")
        elif state == "token_expired":
            runlog.alert(conn, "warning", "feed", "datafeed collector has no valid Stockbit token - log in and paste it at /idx/feed/relay")
        elif state != "live" and stale is not None:
            runlog.alert(conn, "warning", "feed", f"datafeed collector {state}: {c.get('detail') or ''}")


def run_gapfade_entry() -> None:
    """09:00 and 09:05 WIB on a weekday (the second run is a no-op once a ticket exists; it exists for a feed that was
    late at 09:00): the gap-fade morning scan and entry ticket for every gap-fade book (research menu 29b, paper).
    The opening auction has just matched and its prints are in the tick feed; a broken feed trades nothing (gapfade.scan)."""
    from . import gapfade
    d = today_wib()
    if d.weekday() >= 5:
        return
    with get_connection() as conn:
        for bk_ in gapfade.gapfade_books(conn):
            try:
                rep = gapfade.run_entry(conn, bk_)
                logger.info("idx gapfade entry %s: %s", bk_, rep)
            except Exception as e:                                          # one book must never stop the others
                runlog.alert(conn, "warning", f"gapfade:{bk_}", f"entry failed: {type(e).__name__}: {e}")
                logger.exception("gapfade entry failed for %s", bk_)


def run_gapfade_exit() -> None:
    """15:50 WIB: sell everything a gap-fade book holds into the closing auction. Nothing is held overnight by construction."""
    from . import gapfade
    d = today_wib()
    if d.weekday() >= 5:
        return
    with get_connection() as conn:
        for bk_ in gapfade.gapfade_books(conn):
            try:
                rep = gapfade.run_exit(conn, bk_)
                logger.info("idx gapfade exit %s: %s", bk_, rep)
            except Exception as e:
                runlog.alert(conn, "warning", f"gapfade:{bk_}", f"exit failed: {type(e).__name__}: {e}")
                logger.exception("gapfade exit failed for %s", bk_)


SESSION_END = dtime(16, 15)              # post-closing ends 16:15 WIB - the session the token must cover
NAG_FROM, NAG_TO = dtime(7, 0), dtime(16, 30)   # the window in which a dead session is nagged about, every run
TOKEN_MARGIN_MIN = 30                    # the token must outlive the close by this much
REFRESH_WARN_DAYS = 2.0                  # warn this many days before the refresh token itself runs out


def session_end_wib(d: date) -> datetime:
    return datetime.combine(d, SESSION_END, tzinfo=WIB)


def run_token_guard() -> None:
    """Every 10 minutes: the Stockbit session must stay valid until the market closes.

    Off-session it keeps the 3-hour freshness rule (so the next morning starts with a live token). Between 07:00 and 16:30
    on a weekday it demands enough validity to reach 16:15 + 30 min and renews from the refresh token when it does not have
    it. If the session cannot be made to last that long - no refresh token, or Stockbit refused it (a browser re-login
    invalidates the old one) - it pushes the operator a notification ON EVERY RUN, i.e. every 10 minutes, until it is fixed:
    without a session the tick feed goes dark and the gap-fade jobs cannot see the opening auction. The refresh token's own
    7-day horizon is watched too, so the paste is asked for days ahead instead of during a session.
    """
    from . import broker, notify
    from .feed import store as fs
    now = datetime.now(WIB)
    d = now.date()
    trading = d.weekday() < 5 and now.time() <= SESSION_END
    need_until = session_end_wib(d) + timedelta(minutes=TOKEN_MARGIN_MIN) if trading else None
    nagging = d.weekday() < 5 and NAG_FROM <= now.time() <= NAG_TO
    with get_connection() as conn:
        failed = None
        try:
            rep = broker.renew_if_needed(conn, need_until=need_until)
            if rep["renewed"]:
                logger.info("idx stockbit token renewed, %s min left (needed %s)", rep["minutes_left"], rep["needed"])
            elif rep["reason"].startswith("no refresh token"):
                failed = "no refresh token is stored"
        except broker.BrokerFetchError as e:
            failed = f"{type(e).__name__}: {e}"
        st = fs.token_status(fs.load_token(conn), now.astimezone(UTC))   # one clock for the whole decision
        left = st.get("minutes_left")
        covers = bool(st["valid"] and (need_until is None or (left is not None and left >= (need_until - now).total_seconds() / 60)))
        if not covers and nagging:                                         # the loud path: repeated, not deduped
            when = st["expires_at"] or "never (no token)"
            msg = (f"Stockbit session will NOT last today's close: expires {when}"
                   + (f" ({left:.0f} min left)" if left is not None else "")
                   + (f"; renewal failed: {failed}" if failed else "")
                   + ". Log in to stockbit.com and paste the credentialStorage cookie at http://127.0.0.1:8001/idx/feed/relay - "
                     "without it the tick feed stops and the gap-fade jobs are blind.")
            if not runlog.alert_once(conn, "critical", "feed", msg):       # the first one raises the alert (and pushes);
                notify.send(msg, title="IDX token", data={"route": "/m/more", "kind": "token"})   # after that, a push every 10 min
            logger.warning("idx token guard: %s", msg)
        elif failed and trading:
            runlog.alert(conn, "warning", "feed", f"Stockbit token renewal failed ({failed}) - the stored session still covers today")
        rs = broker.refresh_status(conn=conn)
        if rs["present"] and rs["days_left"] is not None and rs["days_left"] < REFRESH_WARN_DAYS:
            runlog.alert(conn, "warning", "feed", f"Stockbit REFRESH token expires {rs['expires_at']:%Y-%m-%d %H:%M} UTC "
                                                  f"({rs['days_left']:.1f} days): paste a fresh cookie at /idx/feed/relay before then")


def run_feed_audit() -> None:
    """Coverage of today's prints against the official day summary (which the daily chain fetched earlier this evening);
    a subscribed name under 95 % is a warning."""
    from .feed import store as fs
    d = today_wib()
    if d.weekday() >= 5:
        return
    with get_connection() as conn:
        rows = fs.audit_day(conn, d)
        if not rows:
            return
        low = [r for r in rows if r["coverage"] is not None and r["coverage"] < 0.95]
        logger.info("idx feed audit %s: %d names, %d under 95 %% coverage", d, len(rows), len(low))
        if low:
            worst = ", ".join(f"{r['code']} {float(r['coverage']) * 100:.0f}%" for r in sorted(low, key=lambda r: r["coverage"])[:8])
            runlog.alert(conn, "warning", "feed", f"datafeed coverage under 95 % on {len(low)} names {d}: {worst}")


def run_macro() -> None:
    from . import macro as job_macro
    with get_connection() as conn:
        r = job_macro.pull(conn)
        _fail_alert(conn, r)
        if r.status == "partial":
            runlog.alert(conn, "warning", "macro", f"macro pull: {', '.join(r.detail.get('failed') or [])} failed; the rest refreshed")
        logger.info("idx macro %s rows=%s failed=%s", r.status, r.rows_out, r.detail.get("failed"))


def run_annual(limit: int = 8) -> None:
    """Annual reports for today's lists and holdings: discover this year and last, download at most ``limit`` reports
    (each one is 20-60 MB and several attachments; the rest wait for the next run), extract the plan pages."""
    from . import annual
    from .cli import _list_codes
    with get_connection() as conn, IdxClient(rps=0.2) as cl:
        y = today_wib().year
        for year in (y - 1, y):
            annual.discover(conn, cl, year)
        r = annual.download(conn, cl, codes=_list_codes(conn), years=[y - 1, y], limit=limit)
        e = annual.extract(conn)
        _fail_alert(conn, r)
        logger.info("idx annual: downloaded=%s extracted sections=%s", r.rows_out, e.rows_out)


def run_daily_fallback() -> None:
    """19:40 WIB on a weekday with no IDX bar yet: take the day's closes from Yahoo so marks, NAV and the ticket see
    today's prices; the chain keeps trying IDX until 20:00 and the watcher/backfill replaces the rows later."""
    from .metrics import universe_codes
    d = today_wib()
    if d.weekday() >= 5:
        return
    with get_connection() as conn:
        if job_daily.latest_bar_date(conn) == d:
            return
        r = job_daily.fallback_yahoo(conn, d, universe_codes(conn))
        _fail_alert(conn, r)
        logger.info("idx daily fallback %s %s rows=%s", d, r.status, r.rows_out)
        if r.status == "ok":
            for bk in ("live", "paper"):
                rm = book.mark(conn, bk)
                _fail_alert(conn, rm)
                if rm.status == "ok":
                    _fail_alert(conn, levels.check(conn, bk))


def run_news() -> None:
    from . import news
    with get_connection() as conn:
        r = news.run(conn)
        if r.status == "failed":
            _fail_alert(conn, r)
        logger.info("idx news %s items=%s new=%s failed=%s", r.status, r.rows_in, r.rows_out, r.detail.get("failed"))


def run_consensus() -> None:
    """Weekly analyst-consensus snapshot for the universe and every book holding (Yahoo, one call per name)."""
    from . import consensus
    from .cli import _list_codes
    from .metrics import universe_codes
    with get_connection() as conn:
        codes = sorted(set(universe_codes(conn)) | set(_list_codes(conn)))
        r = consensus.run(conn, codes)
        _fail_alert(conn, r)
        logger.info("idx consensus %s names=%s covered=%s", r.status, r.rows_in, r.detail.get("covered"))


def run_fin_backlog(limit: int = 60) -> None:
    """Quarterly workbooks 2021-2023 for the universe, a few dozen a day at a gentle pace, so the earnings-acceleration
    signal can be tested on more than two years. Skips the day when the IDX client is being challenged."""
    with get_connection() as conn:
        codes = universe_codes(conn)
        try:
            with IdxClient(rps=0.3) as cl:
                rd = job_fin.download(conn, cl, codes=codes, years=[2021, 2022, 2023], periods=["tw1", "tw2", "tw3"], limit=limit)
        except IdxFetchError as e:
            runlog.alert(conn, "info", "fin:backlog", f"skipped today: {e}")
            return
        logger.info("idx fin backlog %s pending=%s ok=%s", rd.status, rd.rows_in, rd.rows_out)
        if rd.rows_out:
            rp = fin_store.run(conn, codes=codes)
            logger.info("idx fin backlog parse %s reports=%s", rp.status, rp.rows_out)


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
    from apscheduler.triggers.interval import IntervalTrigger

    s = BlockingScheduler(timezone=WIB, job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 3600})
    s.add_job(run_universe, CronTrigger(day_of_week="mon-fri", hour=16, minute=15, timezone=WIB), id="universe")
    s.add_job(run_daily_chain, CronTrigger(day_of_week="mon-fri", hour="16-19", minute="30,45,0,15", timezone=WIB),
              id="daily_chain")
    s.add_job(run_daily_chain, CronTrigger(day_of_week="mon-fri", hour=20, minute=0, timezone=WIB), id="daily_last")
    s.add_job(check_no_bar, CronTrigger(day_of_week="mon-fri", hour=18, minute=0, timezone=WIB), id="no_bar_alert")
    s.add_job(run_daily_fallback, CronTrigger(day_of_week="mon-fri", hour=19, minute=40, timezone=WIB), id="daily_fallback")
    s.add_job(run_announce_recent, CronTrigger(day_of_week="mon-fri", hour=20, minute=30, timezone=WIB), id="announce_recent")
    s.add_job(run_broker_snapshot, CronTrigger(day_of_week="mon-fri", hour=20, minute=20, timezone=WIB), id="broker_snapshot")
    s.add_job(run_macro, CronTrigger(day_of_week="mon-sat", hour=7, minute=30, timezone=WIB), id="macro")
    s.add_job(run_feed_watch, IntervalTrigger(minutes=5), id="feed_watch")
    s.add_job(run_token_guard, IntervalTrigger(minutes=10), id="token_guard")
    s.add_job(run_gapfade_entry, CronTrigger(day_of_week="mon-fri", hour=9, minute="0,5", timezone=WIB), id="gapfade_entry")
    s.add_job(run_gapfade_exit, CronTrigger(day_of_week="mon-fri", hour=15, minute=50, timezone=WIB), id="gapfade_exit")
    s.add_job(run_feed_audit, CronTrigger(day_of_week="mon-fri", hour=20, minute=10, timezone=WIB), id="feed_audit")
    s.add_job(run_news, CronTrigger(hour="6,12,18,22", minute=10, timezone=WIB), id="news")
    s.add_job(run_consensus, CronTrigger(day_of_week="sat", hour=11, minute=0, timezone=WIB), id="consensus")
    s.add_job(run_fin_backlog, CronTrigger(day_of_week="tue-sat", hour=5, minute=30, timezone=WIB), id="fin_backlog")
    s.add_job(run_annual, CronTrigger(day=6, hour=10, minute=0, timezone=WIB), id="annual")
    s.add_job(run_fundamentals, CronTrigger(day_of_week="mon-fri", hour=21, minute=0, timezone=WIB), id="fundamentals")
    s.add_job(run_fundamentals, CronTrigger(day_of_week="sat", hour=9, minute=0, timezone=WIB), id="fundamentals_full",
              kwargs={"previous_year": True})
    s.add_job(run_dividends, CronTrigger(day=1, hour=9, minute=30, timezone=WIB), id="dividends")
    s.add_job(check_rebalance_due, CronTrigger(month=5, day="1-10", hour=16, minute=45, timezone=WIB), id="rebalance_due")
    s.add_job(run_crosscheck, CronTrigger(day_of_week="sun", hour=10, minute=0, timezone=WIB), id="crosscheck")
    return s


LOCK_KEY = "idx-scheduler"


def try_singleton_lock(conn, key: str = LOCK_KEY) -> bool:
    """Session-level Postgres advisory lock shared by every scheduler on every host that uses this database. Held until
    ``conn`` closes, so a second ``run-scheduler`` (a task restart that left the old one alive, a second host) sees
    False and must exit instead of running the daily chain twice."""
    with conn.cursor() as cur:
        cur.execute("SELECT pg_try_advisory_lock(hashtext(%s)) AS got", (key,))
        r = cur.fetchone()
    conn.commit()
    got = r["got"] if isinstance(r, dict) else r[0]
    return bool(got)


def _lock_connection():
    import psycopg
    from psycopg.rows import dict_row

    from ..shared.settings import get_settings
    return psycopg.connect(**get_settings().db_kwargs(), row_factory=dict_row, autocommit=False)


def main() -> int:
    lock = _lock_connection()
    if not try_singleton_lock(lock):
        logger.warning("idx scheduler already running (advisory lock %r held by another session) - exiting", LOCK_KEY)
        lock.close()
        return 0
    s = build()

    def keep_lock() -> None:
        """If the lock connection died (Postgres restart) the lock is gone and another instance may have started:
        stop this one and let the service manager restart it, which re-acquires the lock cleanly."""
        nonlocal lock
        try:
            with lock.cursor() as cur:
                cur.execute("SELECT 1")
            lock.commit()
        except Exception as e:
            logger.critical("idx scheduler lost its lock connection (%s) - shutting down for a clean restart", e)
            s.shutdown(wait=False)

    from apscheduler.triggers.interval import IntervalTrigger
    s.add_job(keep_lock, IntervalTrigger(minutes=5), id="singleton_lock")
    logger.info("idx scheduler starting (Asia/Jakarta); jobs: %s", [j.id for j in s.get_jobs()])
    try:
        s.start()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        lock.close()
    return 0
