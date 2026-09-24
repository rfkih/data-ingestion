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
  20:05 Mon-Fri   ara_watch           next session's likely ARA touches (model on today's bars, ML-3) + every held name's ARA price
  every 2 min     ara_touch           in-session: held/watched names at the ARA limit - locked / sellers queued / faded (study #101)
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
from .client import BudgetExceeded, CircuitOpen, IdxClient, IdxFetchError
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
    # alert_once, not alert: the daily chain retries every 15 minutes, and on a Cloudflare day 2026-09-23 that turned
    # ONE unreachable endpoint into 17 identical critical rows. The retry cadence belongs in ingest_run, not the alerts.
    if r.status == "failed":
        runlog.alert_once(conn, "critical", r.job, f"{r.job} {r.run_key}: {r.error}")


def run_universe() -> None:
    with get_connection() as conn, IdxClient() as cl:
        r = job_universe.run(conn, cl, today_wib())
        _fail_alert(conn, r)
        if r.status == "ok":
            runlog.resolve(conn, "universe")          # the listing is a snapshot, so a fresh one settles every past failure
        logger.info("idx universe %s %s rows=%s", r.run_key, r.status, r.rows_out)


def run_daily_chain(yahoo_dir: Path | None = None) -> None:
    """Called every 15 min in the publish window; no-op once today's bar is in."""
    d = today_wib()
    if d.weekday() >= 5:
        return
    with get_connection() as conn:
        if job_daily.latest_bar_date(conn) == d:
            runlog.resolve(conn, "daily", like=f"%{d}%")                    # the bar landed: close today's no-bar/403 alerts
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
                # stop / take-profit / index levels the operator set on this book (idx.price_level). Until 2026-09-23 this
                # call sat inside the trend loop's `except`, so it only ran on a night a trend ticket FAILED - the levels on
                # the IPOT book were unarmed on every normal night since 09-17. Every book, every night, after its mark.
                _fail_alert(conn, levels.check(conn, bk))
        for bk in trend_book.trend_books(conn):                          # tonight's breakout/trailing-stop ticket per trend book
            try:
                rep = trend_book.run(conn, bk)
                logger.info("idx trend %s: %s", bk, rep)
            except Exception as e:
                runlog.alert(conn, "warning", f"ticket:{bk}", f"trend ticket failed: {type(e).__name__}: {e}")
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
            runlog.resolve(conn, "announce", like=f"%{day}%")   # this run covers the last 3 days: it heals its own gaps
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
    """Daily broker-distribution capture: every rolling window the free endpoint serves, whole market (research feed).

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
        # 2026-09-24: widened from the 1-day snapshot of the liquid names to the full capture for the WHOLE market - first
        # the four rolling windows (1D / 1M / 3M / 1Y) with the buyer->seller matrix for every name, so the irreplaceable
        # daily rows land early, then the 48-view detail matrix (investor split, all boards, lots) for every name (the
        # operator's call, "data ID itu emas": ~36k requests, ~10 h at one request per second, done before the open).
        # Resumable per (name, window, view, day); stops cleanly on pushback and picks up where it left off next run.
        last = job_daily.latest_bar_date(conn)
        try:
            cfg = broker.config_fresh(conn=conn)
            codes = broker.all_codes(conn)
            res = broker.capture(conn, codes, broker.MATRIX_CORE, cfg, expected_date=last, log=logger.debug)
            logger.info("idx broker capture core %s ok=%s failed=%s skipped=%s rows=%s edges=%s", res.get("date"), res["ok"], res["failed"],
                        res["skipped"], res["rows"], res["edges"])
            if not res["stopped"]:
                cfg = broker.config_fresh(conn=conn)
                res2 = broker.capture(conn, codes, broker.MATRIX_DETAIL, cfg, expected_date=last, log=logger.debug)
                logger.info("idx broker capture detail %s ok=%s failed=%s skipped=%s rows=%s edges=%s", res2.get("date"), res2["ok"], res2["failed"],
                            res2["skipped"], res2["rows"], res2["edges"])
                res = res2 if res2["stopped"] else res
        except broker.BrokerFetchError as e:
            runlog.alert(conn, "warning", "broker", f"broker capture: {e}")
            logger.warning("idx broker capture: %s", e)
            return
        if res["stopped"]:
            runlog.alert(conn, "warning", "broker", f"broker capture stopped: {res['stopped']}")


def run_feed_watch() -> None:
    """During the session: one warning when the datafeed collector's heartbeat is stale or it is not live (token expired,
    reconnecting for too long, task dead). Dedup is runlog's (same job+message stays one open alert)."""
    from .feed.collector import in_session
    from .providers import registry
    from .providers.base import ProviderError
    if not in_session():
        return
    with get_connection() as conn:
        pinned = registry.pin(conn, "feed")                                 # the provider the toggle names, once
        try:
            h = registry.feed_of(pinned).health(conn)
        except ProviderError as e:                                          # the toggle names a provider with no feed adapter
            runlog.alert_once(conn, "critical", "feed", f"feed toggle is broken: {e} - fix it in Blackridge > More > Brokers")
            return
        if h.ok:
            runlog.resolve(conn, "feed", like="%: DOWN -%")                 # back up: close the incident, do not wait for a human
        else:
            runlog.alert_once(conn, "warning", "feed", f"{h.summary} - check the 'Blackheart IDX feed' task or Blackridge > More > Brokers")
        problem = registry.provenance_problem(registry.streaming_provider(conn), pinned)
        if problem:                                                         # the tables are being filled by the OTHER provider
            runlog.alert_once(conn, "critical", "feed", problem)             # every 5 min: once per incident, not per check


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
    from . import notify
    from .providers import registry
    from .providers.base import PROVIDERS, NotSupported, ProviderError
    now = datetime.now(WIB)
    d = now.date()
    trading = d.weekday() < 5 and now.time() <= SESSION_END
    need_until = session_end_wib(d) + timedelta(minutes=TOKEN_MARGIN_MIN) if trading else None
    nagging = d.weekday() < 5 and NAG_FROM <= now.time() <= NAG_TO
    with get_connection() as conn:
        active_feed = registry.active(conn, "feed")
        for provider in PROVIDERS:                                          # every provider guards its OWN session (review #2)
            tokens = registry.tokens_of(provider)
            critical = provider == active_feed                              # only the streaming provider blinds the desk
            before = tokens.token_state(conn)
            if not before.present and not critical:
                continue                                                    # a standby with nothing stored is not a fault
            failed = None
            try:
                tokens.renew(conn, need_until=need_until)
            except NotSupported as e:                                       # no refresh flow (Ajaib today): only a fault if it matters
                failed = str(e)
            except ProviderError as e:
                failed = str(e)
            st = tokens.token_state(conn)
            left = st.minutes_left
            covers = bool(st.valid and (need_until is None or (left is not None and left >= (need_until - now).total_seconds() / 60)))
            hint = ("Log in to stockbit.com and paste the credentialStorage cookie in Blackridge > More (or /idx/feed/relay)"
                    if provider == "stockbit" else "paste a fresh session in Blackridge > More > Brokers")
            if not covers and nagging and critical:                         # the loud path: repeated, not deduped
                when = st.expires_at or "never (no token)"
                msg = (f"{provider} session will NOT last today's close: expires {when}"
                       + (f" ({left:.0f} min left)" if left is not None else "")
                       + (f"; renewal failed: {failed}" if failed else "")
                       + f". {hint} - without it the tick feed stops and the gap-fade jobs are blind.")
                if not runlog.alert_once(conn, "critical", "feed", msg):   # the first one raises the alert (and pushes);
                    notify.send(msg, title="IDX token", data={"route": "/m/more", "kind": "token"})   # after that, a push every 10 min
                logger.warning("idx token guard: %s", msg)
            elif not covers and nagging:                                    # a standby's dead session: one warning, no nagging
                runlog.alert_once(conn, "warning", "feed", f"{provider} (standby) session is not valid - {hint}")
            elif failed and trading and critical and "no refresh flow" not in failed:   # a real renewal failure, session still covers today
                runlog.alert_once(conn, "warning", "feed", f"{provider} token renewal failed ({failed}) - the stored session still covers today")
            if st.refresh_present and st.refresh_days_left is not None and st.refresh_days_left < REFRESH_WARN_DAYS:
                runlog.alert_once(conn, "warning", "feed", f"{provider} REFRESH token expires {st.refresh_expires_at:%Y-%m-%d %H:%M} UTC "
                                                      f"({st.refresh_days_left:.1f} days): {hint} before then")


def run_ara_watch() -> None:
    """20:05 WIB: the ARA watch list for the next session - model P(touch) on today's bars (research ML-3), the top-10 plus
    every name a book holds, each with its ARA price. Information for a holder or a watcher; never a ticket (menu 16)."""
    from . import ara
    d = today_wib()
    if d.weekday() >= 5:
        return
    with get_connection() as conn:
        try:
            rep = ara.watch(conn)
            logger.info("idx ara watch: bar %s, %d rows", rep["bar_date"], len(rep["rows"]))
        except Exception as e:
            runlog.alert(conn, "warning", "ara", f"ARA watch failed: {type(e).__name__}: {e}")
            logger.exception("ara watch failed")


def run_ara_touch() -> None:
    """Every 2 min in the session: held and watched names at the ARA limit, and whether the touch is locked, queued or
    fading (menu 34: locked -> +431 bps the next day vs the ARA price; faded -> -661 bps). One alert per state change."""
    from . import ara
    now = datetime.now(WIB)
    if not ara.in_session(now):
        return
    with get_connection() as conn:
        try:
            rep = ara.touch_check(conn, now)
            if rep.get("touches"):
                logger.info("idx ara touch: %s", rep["new"] or "no new state")
        except Exception as e:
            runlog.alert_once(conn, "warning", "ara", f"ARA touch check failed: {type(e).__name__}: {e}")
            logger.exception("ara touch failed")


def run_ticket_nudge() -> None:
    """Chase an issued ticket that still needs the operator: lines not worked yet, or every line done but the ticket left
    open (which blocks the next draft). Runs mid-session and before the close so a morning ticket can still be worked.

    Dedupe (2026-09-23 review): one open alert per ticket, keyed on ``stale_state``'s stable ``key`` through
    ``runlog.alert_once``, auto-acknowledged once the ticket is worked or closed. The phone is pushed at once when a
    ticket FIRST turns up, and afterwards only on the morning run - a lingering ticket is a once-a-day reminder, never
    the twice-a-day-forever it was before."""
    from . import notify, runlog, ticket
    d = today_wib()
    if d.weekday() >= 5:
        return
    with get_connection() as conn:
        stale = ticket.stale_tickets(conn, d)
        keys = [s["key"] for s in stale]
        with conn.cursor() as cur:                      # tickets that have since been worked or closed: clear their alert
            cur.execute("UPDATE idx.alert SET acknowledged_at = now() WHERE job = 'ticket' AND acknowledged_at IS NULL "
                        "AND NOT (message = ANY(%s))", (keys,))
        conn.commit()
        if not stale:
            return
        new = [s for s in stale if runlog.alert_once(conn, "warning", "ticket", s["key"])]
        morning = datetime.now(WIB).hour < 12
        logger.info("idx ticket nudge: %d open, %d new, %d stale", len(stale), len(new),
                    sum(1 for s in stale if s["stale"]))
        if not new and not morning:
            return                                      # already reminded this morning; do not nag again this afternoon
        text = "\n".join(["Tiket menunggu Anda:"] + [f"- {s['why']}" for s in stale])
        notify.send(text, title="Tiket terbuka" if new else "Tiket masih terbuka", data={"screen": "ticket"})


def run_track_report() -> None:
    """The evening "is it proven yet?" scorecard for every book that has a research profile (trend, gapfade).

    The operator's staging rule is to add capital only once a strategy reproduces its backtested profile; this pushes the
    progress towards that bar once a day so the decision is made on a number, not on the memory of the last few trades.
    Read-only, and silent when nothing has a profile yet."""
    from . import book as bk
    from . import notify
    from . import track as tk
    d = today_wib()
    if d.weekday() >= 5:
        return
    with get_connection() as conn:
        books = [b for b in bk.list_books(conn)
                 if (bk.get_book(conn, b).get("rule") or "").lower() in tk.PROFILES]
        if not books:
            return
        blocks = [tk.render(tk.scorecard(conn, b)) for b in books]
    text = "\n\n".join(blocks)
    logger.info("idx track: %d book(s)", len(blocks))
    notify.send(text, title=f"Track record {d:%d %b}")


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
            # Every book, exactly as the normal chain does above - not the ("live", "paper") pair this
            # used to hardcode. On a Cloudflare day the IDX `daily` job 403s and this fallback is the
            # only thing that marks, so the pair meant trend_live, paper_trend and paper_turnaround
            # went unmarked all day: on 2026-09-23 that left an IRSX position bought the evening
            # before with no price, and the desk read the book as -10 % when it was up 1.5 %.
            for bk in [x["book"] for x in _all_books(conn)]:
                rm = book.mark(conn, bk)
                _fail_alert(conn, rm)
                if rm.status == "ok":
                    _fail_alert(conn, levels.check(conn, bk))


_GAPS_SQL = """
WITH d AS (SELECT generate_series(%s::date, %s::date, '1 day')::date AS trade_date)
SELECT d.trade_date
  FROM d
  LEFT JOIN LATERAL (SELECT count(*) AS n FROM idx.bar b
                      WHERE b.trade_date = d.trade_date AND b.source = 'idx') bars ON true
  LEFT JOIN LATERAL (SELECT status FROM idx.ingest_run r
                      WHERE r.job = 'daily' AND r.run_key = d.trade_date::text
                      ORDER BY r.started_at DESC LIMIT 1) last_run ON true
 WHERE extract(isodow FROM d.trade_date) < 6
   AND bars.n = 0
   AND (last_run.status IS NULL OR last_run.status = 'failed')
 ORDER BY d.trade_date
"""


def bar_gaps(conn, days: int = 10) -> list[date]:
    """Recent weekdays with no IDX bar that the daily job never managed to fetch. A public holiday is NOT a gap: IDX
    answers for it with an empty payload, so its run is 'ok' with zero rows and the status filter drops it - only a day
    that failed (or was never attempted at all) comes back, which keeps this from re-asking about Idul Fitri forever."""
    from psycopg.rows import tuple_row

    # An explicit row factory: get_connection hands out dict rows, a bare psycopg.connect() (the tests) hands out tuples.
    end = today_wib() - timedelta(days=1)
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(_GAPS_SQL, (end - timedelta(days=days), end))
        return [r[0] for r in cur.fetchall()]


def run_bar_backfill(days: int = 10) -> None:
    """Re-fetch the IDX days the chain never got. The chain only ever chases TODAY (it returns the moment today's bar is
    in), so a day IDX refuses leaves a hole nothing closes: on 2026-09-23 a Cloudflare challenge ran from 16:29 into the
    next morning and left 09-23 with 205 Yahoo closes against the usual 963 - the ~760 names outside the universe simply
    had no bar, and the only cure was a human noticing and running `idx backfill` by hand. Twice a day, so a challenge
    that lifts overnight heals itself; one query and no network when there is nothing to heal. Features are not recomputed
    here - the next daily chain rebuilds them with its 45-day lookback, which covers anything this fills."""
    with get_connection() as conn:
        gaps = bar_gaps(conn, days)
        if not gaps:
            return
        logger.info("idx bar backfill: %d gap day(s) %s", len(gaps), [str(g) for g in gaps])
        healed, still = [], []
        with IdxClient() as cl:
            for d in gaps:
                try:
                    r = job_daily.run(conn, cl, d)
                except (CircuitOpen, BudgetExceeded) as e:                  # the client says stop asking; try again tonight
                    logger.warning("idx bar backfill stopped at %s: %s", d, e)
                    break
                if r.status != "ok":
                    still.append(d)
                    continue
                job_index.run(conn, cl, d)                                  # the index of a healed day, same as the chain
                healed.append(d)
                runlog.resolve(conn, "daily", like=f"%{d}%")
        if healed:
            # Finish the chain for the days we filled. Healing only the bars moves the newest summary date forward while
            # features stay behind, and the screen anchors on the last FINISHED day - so a bars-only heal would leave the
            # desk looking at an older day than the data it now holds (and, before the anchor was fixed, at nothing).
            rp = publish.publish(conn, since=min(healed), yahoo_dir=None)
            _fail_alert(conn, rp)
            rf = features.run(conn, since=min(healed) - timedelta(days=45))
            _fail_alert(conn, rf)
            if rf.status == "ok":
                rc, _ = candidates.run(conn)
                _fail_alert(conn, rc)
                for d in healed:
                    try:                                                 # the public scores of the healed day, as the chain does
                        scores.build(conn, d)
                    except Exception as e:
                        runlog.alert_once(conn, "warning", "scores", f"scores failed for {d}: {type(e).__name__}: {e}")
            logger.info("idx bar backfill: chain rebuilt publish=%s features=%s", rp.rows_out, rf.rows_out)
            runlog.alert(conn, "info", "daily",
                         f"backfilled the IDX bars of {', '.join(str(d) for d in healed)} (they had failed at the time)")
        logger.info("idx bar backfill: healed=%s still missing=%s", [str(d) for d in healed], [str(d) for d in still])


def run_registry_refresh() -> None:
    """Keep the strategies page's numbers in step with research: re-import every record from the newest ROI scorecard
    study into idx.strategy_state. Cheap and idempotent; a page shows `refreshed_at` so a stale import is visible."""
    from . import registry
    with get_connection() as conn:
        res = registry.refresh_scorecard(conn)
    logger.info("idx registry refresh: study=%s written=%s with_record=%s", res.get("study"), res.get("written"), res.get("with_record"))


def run_alert_sweep(days: int = 3) -> None:
    """Keep the ops screen readable: old informational alerts are acknowledged for you (runlog.sweep_info)."""
    with get_connection() as conn:
        runlog.sweep_info(conn, days)


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
    s.add_job(run_bar_backfill, CronTrigger(hour="7,21", minute=30, timezone=WIB), id="bar_backfill")
    s.add_job(run_alert_sweep, CronTrigger(hour=6, minute=0, timezone=WIB), id="alert_sweep")
    s.add_job(run_announce_recent, CronTrigger(day_of_week="mon-fri", hour=20, minute=30, timezone=WIB), id="announce_recent")
    s.add_job(run_broker_snapshot, CronTrigger(day_of_week="mon-fri", hour=20, minute=20, timezone=WIB), id="broker_snapshot")
    s.add_job(run_registry_refresh, CronTrigger(hour=20, minute=5, timezone=WIB), id="registry_refresh")
    s.add_job(run_macro, CronTrigger(day_of_week="mon-sat", hour=7, minute=30, timezone=WIB), id="macro")
    s.add_job(run_feed_watch, IntervalTrigger(minutes=5), id="feed_watch")
    s.add_job(run_token_guard, IntervalTrigger(minutes=10), id="token_guard")
    s.add_job(run_gapfade_entry, CronTrigger(day_of_week="mon-fri", hour=9, minute="0,5", timezone=WIB), id="gapfade_entry")
    s.add_job(run_gapfade_exit, CronTrigger(day_of_week="mon-fri", hour=15, minute=50, timezone=WIB), id="gapfade_exit")
    s.add_job(run_ara_watch, CronTrigger(day_of_week="mon-fri", hour=20, minute=5, timezone=WIB), id="ara_watch")
    s.add_job(run_ara_touch, IntervalTrigger(minutes=2), id="ara_touch")
    s.add_job(run_feed_audit, CronTrigger(day_of_week="mon-fri", hour=20, minute=10, timezone=WIB), id="feed_audit")
    # after the daily chain has marked the books, before the 20:45 nightly agent run
    s.add_job(run_track_report, CronTrigger(day_of_week="mon-fri", hour=20, minute=20, timezone=WIB), id="track_report")
    # mid-session and before the close: a ticket drafted this morning can still be worked today
    s.add_job(run_ticket_nudge, CronTrigger(day_of_week="mon-fri", hour="10,14", minute=30, timezone=WIB), id="ticket_nudge")
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
