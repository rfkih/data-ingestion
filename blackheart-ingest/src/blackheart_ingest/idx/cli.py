"""``python -m blackheart_ingest.idx.cli <command>`` - operator CLI for the IDX data plane.

Commands (build plan 2026-09-12, phase 0):
  migrate | status                schema ``idx`` migrations
  universe [--date D]             Daftar Saham snapshot -> idx.listing(_snapshot)
  daily --date D                  one day's Ringkasan Saham -> daily_summary, bar, corporate_action
  index --date D                  one day's Ringkasan Indeks -> index_daily
  backfill --from D --to D        every weekday in range (daily [+ --index]); archived days replay from bronze
  replay --job daily|index --date D [--to D]   re-derive silver from bronze, no network
  publish [--since D | --full] [--codes A,B]   idx.bar (+ Yahoo pre-2020 on --full) -> market_data
  crosscheck [--sample N | --codes A,B]        per-stock endpoint vs idx.bar (last 45 days)
  announce [--codes A,B | --all] [--from D] [--to D]   Keterbukaan Informasi metadata -> announcement + event
  features [--since D] [--codes A,B] [--publish]       PIT overlay features -> idx.feature_daily (+ feature_values mirror)
  fin discover [--years 2020-2025] [--periods tw1,audit]   bulk listing -> idx.financial_report
  fin download [--codes A,B | --universe] [--years ..] [--periods ..] [--limit N]   workbooks -> data/idx/fin
  fin parse [--codes A,B] [--limit N] [--reparse]      workbooks -> idx.financial_fact + idx.fundamental (PIT)
  dividends [--codes A,B | --universe]                 Yahoo dividend events -> idx.dividend (source=yahoo)
  card CODE [--as-of D] [--out file.md]                thesis card (PIT): valuation, quality gate, fundamentals, flow, disclosures
  candidates [--as-of D] [--top N] [--out file.md]     value/quality candidate list (PIT) -> idx.candidate + markdown
  pack [--as-of D] [--next N] [--codes A,B] [--out DIR] analysis pack for manual Claude chat -> idx.nightly_pack + files
  pack-import FILE [--date D]                          import the JSON answer -> idx.sentiment_score + nightly_pack.answer_json
  answers [--code C] [--limit N]                       imported answers, newest first
  watch list | add CODE [--note ..] | rm CODE          watchlist (held / followed names included in every pack)
  book show|fills|fill|cash|set|import|mark|check|paper-seed [--book live|paper]   position book (see `book -h`)
  ticket build|show|issue|close|fill|skip [--book] [--mode rebalance|exits]         rebalance ticket + fill capture
  board [--as-of D] [--record]                 what the five best strategies say today (entries only)
  run-scheduler                                foreground APScheduler (Asia/Jakarta), see scheduler.py

DB comes from the INGEST_* settings (INGEST_DB_DSN or INGEST_DB_HOST/...).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from ..shared.db import get_connection
from ..shared.logging_setup import configure
from . import bronze, features, publish, runlog
from . import migrate as mig
from .client import BudgetExceeded, CircuitOpen, IdxClient
from .jobs import announce as job_announce
from .jobs import crosscheck as job_crosscheck
from .jobs import daily as job_daily
from .jobs import dividends as job_dividends
from .jobs import fin as job_fin
from .jobs import index as job_index
from .jobs import universe as job_universe


def _d(s: str) -> date:
    return date.fromisoformat(s)


def _jwt_exp(token: str) -> str | None:
    """The exp claim of a JWT as a UTC string, for a friendly "expires …" line; None if it cannot be read."""
    import base64
    import json as _json
    try:
        p = token.split(".")[1]
        claims = _json.loads(base64.urlsafe_b64decode(p + "=" * (-len(p) % 4)))
        exp = claims.get("exp")
        return datetime.fromtimestamp(exp, UTC).strftime("%Y-%m-%d %H:%M UTC") if exp else None
    except Exception:
        return None


def _today() -> date:
    return datetime.now(UTC).date()


def _report(r) -> None:
    extra = " ".join(f"{k}={v}" for k, v in r.detail.items() if k != "actions")
    warn = f" warnings={len(r.warnings)}" if r.warnings else ""
    err = f" error={r.error}" if r.error else ""
    print(f"{r.job:14} {r.run_key or '':10} {r.status:8} in={r.rows_in:<5} out={r.rows_out:<5} {extra}{warn}{err}")
    for a in r.detail.get("actions", []):
        print(f"    corporate action: {a}")


def cmd_migrate(_: argparse.Namespace) -> int:
    with get_connection() as conn:
        ran = mig.migrate(conn)
    for m in ran:
        print(f"applied {m.version:04d}_{m.name} ({m.sha256[:12]})")
    if not ran:
        print("idx schema up to date")
    return 0


def cmd_status(_: argparse.Namespace) -> int:
    with get_connection() as conn:
        rows = mig.status(conn)
    for v, n, st in rows:
        print(f"{v:04d}_{n:<40} {st}")
    return 1 if any(st == "DRIFT" for _, _, st in rows) else 0


def cmd_universe(a: argparse.Namespace) -> int:
    with get_connection() as conn, IdxClient() as cl:
        r = job_universe.run(conn, cl, _d(a.date) if a.date else _today())
    _report(r)
    return 0 if r.status == "ok" else 1


def cmd_daily(a: argparse.Namespace) -> int:
    with get_connection() as conn, IdxClient() as cl:
        r = job_daily.run(conn, cl, _d(a.date))
    _report(r)
    return 0 if r.status in ("ok", "skipped") else 1


def cmd_index(a: argparse.Namespace) -> int:
    with get_connection() as conn, IdxClient() as cl:
        r = job_index.run(conn, cl, _d(a.date))
    _report(r)
    return 0 if r.status in ("ok", "skipped") else 1


def _weekdays(start: date, end: date):
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


def cmd_backfill(a: argparse.Namespace) -> int:
    start, end = _d(a.from_), _d(a.to) if a.to else _today()
    n_fetch = n_replay = n_empty = n_fail = 0
    with get_connection() as conn, IdxClient() as cl:
        for d in _weekdays(start, end):
            jobs = [("daily", "stock_summary", job_daily)]
            if a.index:
                jobs.append(("index", "index_summary", job_index))
            for _name, endpoint, mod in jobs:
                try:
                    if not a.refresh and bronze.latest(conn, endpoint, d.isoformat()) is not None:
                        r = mod.replay(conn, d)
                        n_replay += 1
                    else:
                        r = mod.run(conn, cl, d)
                        n_fetch += 1
                except (CircuitOpen, BudgetExceeded) as e:
                    print(f"STOP at {d}: {e}")
                    print(f"backfill: fetched={n_fetch} replayed={n_replay} empty={n_empty} failed={n_fail}")
                    return 2
                if r.status == "failed":
                    n_fail += 1
                if r.detail.get("empty"):
                    n_empty += 1
                if a.verbose or r.status == "failed" or r.detail.get("actions"):
                    _report(r)
            if (n_fetch + n_replay) % 50 == 0:
                print(f"... {d} fetched={n_fetch} replayed={n_replay} empty={n_empty} failed={n_fail}", flush=True)
    print(f"backfill done: fetched={n_fetch} replayed={n_replay} empty(holiday/unpublished)={n_empty} failed={n_fail}")
    return 1 if n_fail else 0


def cmd_replay(a: argparse.Namespace) -> int:
    mod = job_daily if a.job == "daily" else job_index
    start, end = _d(a.date), _d(a.to) if a.to else _d(a.date)
    bad = 0
    with get_connection() as conn:
        for d in _weekdays(start, end):
            r = mod.replay(conn, d)
            if r.status == "failed":
                bad += 1
            if a.verbose or r.status == "failed" or r.detail.get("actions"):
                _report(r)
    print(f"replay done ({a.job} {start}..{end}) failed={bad}")
    return 1 if bad else 0


def cmd_publish(a: argparse.Namespace) -> int:
    from pathlib import Path
    yahoo = Path(a.yahoo_dir) if a.full else None
    since = None if a.full else (_d(a.since) if a.since else publish.default_since())
    codes = [c.strip().upper() for c in a.codes.split(",")] if a.codes else None
    with get_connection() as conn:
        r = publish.publish(conn, codes=codes, since=since, yahoo_dir=yahoo)
    _report(r)
    for w in r.warnings:
        print(f"    {w}")
    return 0 if r.status == "ok" else 1


def cmd_announce(a: argparse.Namespace) -> int:
    if a.reclassify:
        with get_connection() as conn:
            counts = job_announce.reclassify(conn)
        for k, n in sorted(counts.items(), key=lambda kv: -kv[1]):
            print(f"{k:<20} {n}")
        return 0
    start = _d(a.from_) if a.from_ else job_announce.ARCHIVE_START
    end = _d(a.to) if a.to else _today()
    with get_connection() as conn, IdxClient() as cl:
        if a.codes:
            codes = [c.strip().upper() for c in a.codes.split(",")]
        else:
            with conn.cursor() as cur:
                cur.execute("SELECT code FROM idx.listing ORDER BY code")
                codes = [x[0] if isinstance(x, tuple) else x["code"] for x in cur.fetchall()]
        if not a.refresh:
            with conn.cursor() as cur:
                cur.execute("SELECT DISTINCT split_part(key, ':', 1) FROM idx.bronze_index WHERE endpoint = 'announcement'")
                done = {x[0] if isinstance(x, tuple) else next(iter(x.values())) for x in cur.fetchall()}
            codes = [c for c in codes if c not in done]
        n_ok = n_fail = n_events = 0
        for i, code in enumerate(codes, 1):
            try:
                r = job_announce.run(conn, cl, code, start, end)
            except (CircuitOpen, BudgetExceeded) as e:
                print(f"STOP at {code}: {e}")
                break
            if r.status == "failed":
                n_fail += 1
                _report(r)
            else:
                n_ok += 1
                n_events += r.detail.get("events", 0)
            if a.verbose or r.warnings:
                _report(r)
            if i % 50 == 0:
                print(f"... {i}/{len(codes)} ok={n_ok} failed={n_fail} events={n_events}", flush=True)
    print(f"announce done: codes={len(codes)} ok={n_ok} failed={n_fail} events={n_events}")
    return 1 if n_fail else 0


def cmd_features(a: argparse.Namespace) -> int:
    codes = [c.strip().upper() for c in a.codes.split(",")] if a.codes else None
    since = _d(a.since) if a.since else None
    with get_connection() as conn:
        r = features.run(conn, codes=codes, since=since)
        _report(r)
        if a.publish and r.status == "ok":
            if codes is None:
                import json as _json
                from pathlib import Path as _P
                uni = _P(__file__).resolve().parents[4] / "research-scratch" / "idx-screen" / "universe.json"
                codes = [u["code"] for u in _json.loads(uni.read_text(encoding="utf-8"))] if uni.exists() else []
            n = features.publish_feature_values(conn, codes=codes, since=since)
            print(f"feature_values mirrored: {n} rows for {len(codes)} codes")
    return 0 if r.status == "ok" else 1


def _years(spec: str | None) -> list[int] | None:
    if not spec:
        return None
    if "-" in spec:
        lo, hi = spec.split("-")
        return list(range(int(lo), int(hi) + 1))
    return [int(x) for x in spec.split(",")]


def cmd_fin(a: argparse.Namespace) -> int:
    years = _years(a.years)
    periods = a.periods.split(",") if a.periods else None
    with get_connection() as conn, IdxClient() as cl:
        if a.sub == "discover":
            bad = 0
            for y in (years or list(range(2020, _today().year + 1))):
                for p in (periods or list(job_fin.PERIODS)):
                    r = job_fin.discover(conn, cl, y, p)
                    _report(r)
                    bad += r.status == "failed"
            return 1 if bad else 0
        codes = None
        if a.sub == "parse":
            from . import fin_store
            codes = [c.strip().upper() for c in a.codes.split(",")] if a.codes else None
            r = fin_store.run(conn, codes=codes, limit=a.limit, reparse=a.reparse)
            _report(r)
            for w in r.warnings:
                print(f"    {w}")
            return 0 if r.status == "ok" else 1
        if a.codes:
            codes = [c.strip().upper() for c in a.codes.split(",")]
        elif a.universe:
            import json as _json

            from .metrics import universe_codes
            uni = Path(__file__).resolve().parents[4] / "research-scratch" / "idx-screen" / "universe.json"
            extra = {u["code"] for u in _json.loads(uni.read_text(encoding="utf-8"))} if uni.exists() else set()
            codes = sorted(set(universe_codes(conn)) | extra)
        r = job_fin.download(conn, cl, codes=codes, years=years, periods=periods, limit=a.limit)
        _report(r)
        return 0 if r.status == "ok" else 1


def cmd_dividends(a: argparse.Namespace) -> int:
    with get_connection() as conn:
        if a.codes:
            codes = [c.strip().upper() for c in a.codes.split(",")]
        else:
            from .metrics import universe_codes
            codes = universe_codes(conn)
        r = job_dividends.run(conn, codes)
    _report(r)
    return 0 if r.status == "ok" else 1


def cmd_card(a: argparse.Namespace) -> int:
    from . import card
    with get_connection() as conn:
        md = card.build(conn, a.code, _d(a.as_of) if a.as_of else None)
    if a.out:
        Path(a.out).write_text(md, encoding="utf-8")
        print(f"wrote {a.out}")
    else:
        print(md)
    return 0


def cmd_annual(a: argparse.Namespace) -> int:
    from . import annual
    from .metrics import universe_codes
    codes = [c.strip().upper() for c in a.codes.split(",")] if a.codes else None
    years = _years(a.years) if a.years else None
    with get_connection() as conn:
        if a.sub == "discover":
            with IdxClient() as cl:
                for y in years or [date.today().year - 1]:
                    r = annual.discover(conn, cl, y)
                    print(f"annual discover {y}: {r.status} listed={r.rows_in} stored={r.rows_out}" + (f" {r.error}" if r.error else ""))
            return 0
        if a.sub == "download":
            if a.list:
                codes = (codes or []) + _list_codes(conn)
            if a.universe:
                codes = (codes or []) + universe_codes(conn)
            with IdxClient() as cl:
                r = annual.download(conn, cl, codes=codes, years=years, limit=a.limit)
            print(f"annual download: {r.status} pending={r.rows_in} downloaded={r.rows_out}")
            for w in r.warnings[:10]:
                print("  !", w)
            return 0
        if a.sub == "extract":
            r = annual.extract(conn, codes=codes, years=years, reparse=a.reparse)
            print(f"annual extract: {r.status} reports={r.rows_in} sections={r.rows_out}")
            for k, v in r.detail.items():
                print(f"  {k}: {', '.join(v)}")
            return 0
        if a.sub == "show":
            print(annual.render(conn, a.codes.upper()) or f"no annual-report excerpts for {a.codes}")
            return 0
        for row in annual.status(conn):
            print(f"  FY{row['fiscal_year']} {row['parse_status']:16s} {row['n']}")
    return 0


def _list_codes(conn) -> list[str]:
    """Today's selected names (the rule) plus the strict list plus every book's holdings."""
    from . import strategies
    cols = ["code", "rank", "selected", "ep", "bp", "dy", "np_yoy", "mom", "gate_loose", "gate_strict", "strict_fails", "warnings", "sector"]
    with conn.cursor() as cur:
        cur.execute("SELECT max(run_date) FROM idx.candidate")
        row = cur.fetchone()
        D = next(iter(row.values())) if isinstance(row, dict) else row[0]
        cur.execute(f"SELECT {', '.join(cols)} FROM idx.candidate WHERE run_date = %s ORDER BY rank", (D,))
        cands = [r if isinstance(r, dict) else dict(zip(cols, r, strict=True)) for r in cur.fetchall()]
        codes = {r["code"] for r in cands if r["selected"]} | {r["code"] for r in strategies.pick("strict", cands) if r["selected"]}
        cur.execute("SELECT DISTINCT code FROM idx.fill")
        codes |= {(r["code"] if isinstance(r, dict) else r[0]) for r in cur.fetchall()}
    return sorted(codes)


def cmd_news(a: argparse.Namespace) -> int:
    from . import news
    with get_connection() as conn:
        if a.sub == "pull":
            r = news.run(conn)
            print(f"news {r.status}: {r.rows_in} items seen, {r.rows_out} new" + (f"; failed feeds: {', '.join(r.detail.get('failed') or [])}" if r.detail.get("failed") else ""))
            return 0
        for it in news.recent(conn, a.codes.upper() if a.codes else None, a.limit or 30):
            print(f"  {str(it['published_at'])[:16]:16s} {','.join(it['codes']) or '-':12s} {it['title'][:90]}  [{it['source']}]")
    return 0


def cmd_consensus(a: argparse.Namespace) -> int:
    from . import consensus
    from .metrics import universe_codes
    with get_connection() as conn:
        if a.sub == "pull":
            codes = [c.strip().upper() for c in a.codes.split(",")] if a.codes else sorted(set(universe_codes(conn)) | set(_list_codes(conn)))
            r = consensus.run(conn, codes)
            print(f"consensus {r.status}: {r.rows_in} names, {r.detail.get('covered')} with coverage")
            return 0
        codes = [c.strip().upper() for c in a.codes.split(",")] if a.codes else None
        print(f"{'code':5s} {'date':>10s} {'price':>8s} {'target':>8s} {'low':>7s} {'high':>7s} {'n':>3s} {'upside':>7s} {'reco':>5s} {'key':10s}")
        for r in consensus.latest(conn, codes):
            f = lambda v, w=8, d=0: "" if v is None else f"{float(v):{w}.{d}f}"  # noqa: E731
            print(f"{r['code']:5s} {r['snapshot_date']!s:>10s} {f(r['price']):>8s} {f(r['target_mean']):>8s} {f(r['target_low'], 7):>7s} {f(r['target_high'], 7):>7s} {r['n_analysts']:3d} {f(r['upside_pct'], 6, 0):>6s}% {f(r['reco_mean'], 5, 1):>5s} {r['reco_key'] or '':10s}")
    return 0


def cmd_levels(a: argparse.Namespace) -> int:
    from . import levels
    with get_connection() as conn:
        if a.sub == "set":
            if a.stop is not None:
                print(levels.set_level(conn, a.book, a.code, "stop", a.stop, a.note))
            if a.tp is not None:
                print(levels.set_level(conn, a.book, a.code, "take_profit", a.tp, a.note))
            if a.warn is not None:
                print(levels.set_level(conn, a.book, a.code, "warn", a.warn, a.note))
        elif a.sub == "clear":
            print("removed", levels.clear(conn, a.book, a.code, a.kind))
        elif a.sub == "reset":
            print("re-armed", levels.reset(conn, a.book, a.code, a.kind))
        elif a.sub == "check":
            r = levels.check(conn, a.book)
            print(f"levels check {r.status}: {r.rows_in} armed, {r.rows_out} fired")
        else:
            rows = levels.levels(conn, a.book if a.book != "all" else None, a.code)
            print(levels.render(rows, levels._closes(conn, sorted({x["code"] for x in rows}))))
    return 0


def cmd_board(a: argparse.Namespace) -> int:
    """The daily board: what each of the five best strategies wants, before any book's cash."""
    from . import signalboard
    from .jobs import daily as job_daily
    with get_connection() as conn:
        d = _d(a.as_of) if a.as_of else job_daily.latest_bar_date(conn)
        if d is None:
            print("the desk has no bars yet")
            return 1
        if a.record:
            res = signalboard.record(conn, d)
            for r in res["recorded"]:
                print(f"  {r['strategy']:<15} rows={r.get('rows', 0)}" + (f" error={r['error']}" if r.get("error") else ""))
            return 0
        print(signalboard.render(signalboard.build(conn, d)))
    return 0


def cmd_study(a: argparse.Namespace) -> int:
    from . import research_store as rs
    with get_connection() as conn:
        if a.sub == "list":
            for s in rs.studies(conn, a.name):
                print(f"  #{s['id']:<4d} {s['name']:16s} as of {s['as_of']}  run {str(s['run_at'])[:16]}  names={s['names']}  {s['report_path'] or ''}")
        elif a.sub == "show":
            st = rs.study(conn, a.id, a.name)
            if not st:
                print("no such study")
                return 1
            print(f"#{st['id']} {st['name']} as of {st['as_of']} (run {str(st['run_at'])[:16]}) {st['report_path'] or ''}")
            for n in st["names"]:
                print(f"  {n['code']:6s} rank={n['rank'] if n['rank'] is not None else '-':>3} score={n['score'] if n['score'] is not None else '-':>7} screens={list(n['screens'])}")
        elif a.sub == "name":
            print(rs.render_name(rs.name_view(conn, a.code)))
    return 0


def cmd_evidence(a: argparse.Namespace) -> int:
    from . import research_store as rs
    with get_connection() as conn:
        if a.sub == "collect":
            for code in [c.strip().upper() for c in a.code.split(",")]:
                print(code, rs.collect_evidence(conn, code, days=a.days or 365, study_id=a.study))
        elif a.sub == "add":
            ts = datetime.fromisoformat(a.ts) if a.ts else None
            new = rs.add_evidence(conn, a.code, a.kind, a.title, ts=ts, source=a.source, url=a.url, summary=a.summary,
                                  tags=[t.strip() for t in (a.tags or "").split(",") if t.strip()], study_id=a.study)
            print("added" if new else "already there")
        elif a.sub == "show":
            for e in rs.evidence(conn, a.code, [a.kind] if a.kind else None, a.limit or 100):
                print(f"  {str(e['ts'])[:10] if e['ts'] else '          '} [{e['kind']}] {e['title'][:110]}  {e['url'] or ''}")
    return 0


def cmd_macro(a: argparse.Namespace) -> int:
    from . import macro
    if a.sub == "bps-find":
        rows = macro.bps_find(a.keys or "inflasi")
        for r in rows:
            print(f"  var {r['var_id']!s:>6}  {r['title']}  [{r.get('unit') or ''}] {r.get('subject') or ''}")
        print(f"{len(rows)} variable(s); put the national monthly y-on-y one into macro.BPS_INFLATION_VAR")
        return 0
    with get_connection() as conn:
        if a.sub == "pull":
            r = macro.pull(conn, keys=a.keys.split(",") if a.keys else None, full=a.full)
            for k, v in r.detail.items():
                if isinstance(v, dict):
                    print(f"  {k:14s} {v['points']:5d} points, last {v['last']}")
            print(f"macro pull {r.status}: {r.rows_out} rows" + (f"; failed: {', '.join(r.detail.get('failed') or [])}" if r.detail.get("failed") else ""))
            for w in r.warnings:
                print("  !", w)
            return 0 if r.status != "failed" else 1
        print(f"{'series':14s} {'last':>10s} {'value':>12s} {'1m':>9s} {'3m':>9s} {'12m':>9s}  label")
        for row in macro.board(conn):
            f = lambda v: "" if v is None else f"{float(v):+.2f}"  # noqa: E731
            val = "" if row["value"] is None else f"{float(row['value']):,.2f}"
            print(f"{row['key']:14s} {row['date'] or ''!s:>10s} {val:>12s} {f(row['chg_1m']):>9s} {f(row['chg_3m']):>9s} {f(row['chg_12m']):>9s}  {row['label']}")
    return 0


def cmd_overlay(a: argparse.Namespace) -> int:
    from . import overlay
    with get_connection() as conn:
        if a.sub == "status":
            r = overlay.latest(conn)
            if r is None:
                print("no regime check recorded yet; run `idx overlay check --dry-run`")
            else:
                sma = f"{r['sma']:,.0f}" if r["sma"] is not None else "n/a"
                print(f"regime {'ON (invested)' if r['on'] else 'OFF (cash)'} since check {r['check_date']}: {r['index_code']} {r['close']:,.0f} vs 200-day average {sma}")
            with conn.cursor() as cur:
                cur.execute("SELECT book, regime_filter, entry_gate, take_profit_pct, trend_exit, cash_floor_pct, stress_cash_pct, stress_rule FROM idx.book ORDER BY book")
                for row in cur.fetchall():
                    row = dict(row) if isinstance(row, dict) else dict(zip(["book", "regime_filter", "entry_gate", "take_profit_pct", "trend_exit",
                                                                            "cash_floor_pct", "stress_cash_pct", "stress_rule"], row, strict=True))
                    tp = f"take profit +{row['take_profit_pct']:.0f} %" if row["take_profit_pct"] is not None else "take profit off"
                    cb = (f"cash buffer {row['cash_floor_pct']:.0f} % -> {row['stress_cash_pct']:.0f} % on stress ({row['stress_rule']})"
                          if (row["cash_floor_pct"] or row["stress_cash_pct"]) else "cash buffer off")
                    print(f"  {row['book']:6s} regime filter {'on' if row['regime_filter'] else 'off'}, entry gate {'on' if row['entry_gate'] else 'off'}, "
                          f"trend exit {'on' if row['trend_exit'] else 'off'}, {tp}, {cb}")
            s = overlay.latest_stress(conn)
            if s is not None:
                g = s["signals"]
                print(f"stress check {s['check_date']}: {s['n_on']} of 4 on  (under MA200 {g['ma']}, vol spike {g['vol']}, >10 % under 52w high {g['dd']}, "
                      f"breadth<40 % {g['breadth']}; breadth {100 * s['breadth']:.0f} %, vol {100 * s['vol20']:.0f} % vs p80 {100 * s['vol_p80']:.0f} %)"
                      if s["vol20"] is not None and s["vol_p80"] is not None and s["breadth"] is not None else
                      f"stress check {s['check_date']}: {s['n_on']} of 4 on")
            for h in overlay.history(conn, 12):
                print(f"  {h['check_date']} {'on ' if h['on'] else 'off'} {h['close']:,.0f} / {h['sma']:,.0f}" if h["sma"] is not None else f"  {h['check_date']} {'on' if h['on'] else 'off'}")
            return 0
        d = _d(a.as_of) if a.as_of else date.today()
        rep = overlay.monthly_check(conn, d, build=not a.dry_run)
        print(overlay.render(rep) + ("   [dry run]" if a.dry_run else ""))
    return 0


def cmd_candidates(a: argparse.Namespace) -> int:
    from . import candidates
    with get_connection() as conn:
        r, res = candidates.run(conn, _d(a.as_of) if a.as_of else None)
    if r.status != "ok":
        _report(r)
        return 1
    md = candidates.render(res, a.top)
    if a.out:
        Path(a.out).write_text(md, encoding="utf-8")
        print(f"wrote {a.out}")
    else:
        print(md)
    return 0


def _pack_dir() -> Path:
    return Path(__file__).resolve().parents[4] / "research-scratch" / "idx-pack"


def cmd_pack(a: argparse.Namespace) -> int:
    from . import pack
    codes = [c.strip().upper() for c in a.codes.split(",")] if a.codes else None
    with get_connection() as conn:
        p = pack.build(conn, _d(a.as_of) if a.as_of else None, next_n=a.next, codes=codes)
        pack.store(conn, p)
    out = Path(a.out) if a.out else _pack_dir() / p["pack_date"].isoformat()
    out.mkdir(parents=True, exist_ok=True)
    (out / "pack.md").write_text(p["md"], encoding="utf-8")
    (out / "pack.json").write_text(json.dumps(p["json"], default=str, indent=1), encoding="utf-8")
    print(f"pack {p['pack_date']}: {len(p['codes'])} names, {len(p['md']):,} chars (~{len(p['md']) // 4:,} tokens) -> {out / 'pack.md'}")
    return 0


def cmd_pack_import(a: argparse.Namespace) -> int:
    from . import pack
    text = Path(a.file).read_text(encoding="utf-8")
    with get_connection() as conn:
        if a.date:
            d = _d(a.date)
        else:
            p = pack.load(conn)
            if p is None:
                print("no pack to import into")
                return 1
            d = p["pack_date"]
        try:
            ans = pack.import_answer(conn, d, text)
        except pack.AnswerError as e:
            print(f"answer rejected: {e}")
            return 1
    vetoes = [n["code"] for n in ans["names"] if n["veto"]]
    print(f"imported {len(ans['names'])} answers for pack {d}" + (f"; missing: {','.join(ans['missing'])}" if ans["missing"] else "")
          + (f"; VETO: {','.join(vetoes)}" if vetoes else ""))
    for n in ans["names"]:
        print(f"  {n['code']:<6} {n['stance']:<5} c{n['conviction']} {'VETO ' if n['veto'] else ''}{n['thesis'][:110]}")
    return 0


def cmd_answers(a: argparse.Namespace) -> int:
    from . import pack
    with get_connection() as conn:
        if a.score:
            print(pack.render_scores(pack.score_answers(conn)))
            return 0
        rows = pack.answers(conn, a.code.upper() if a.code else None, a.limit)
    for r in rows:
        print(f"{r['pack_date']} {r['code']:<6} {r['stance']:<5} c{int(r['conviction'])} {r['veto'] or '-':<4} {(r['rationale'] or '')[:120]}")
    return 0


def cmd_strategies(a: argparse.Namespace) -> int:
    from . import strategies
    with get_connection() as conn:
        if a.sub == "import-history":
            n = sum(strategies.import_history(conn, f) for f in a.files)
            print(f"imported {n} history rows from {len(a.files)} file(s)")
            return 0
        for s in strategies.catalog(conn):
            print(f"{s['key']:14s} {s['status']:12s} {s['label']}")
            for size, months in sorted(s["records"].items(), key=lambda kv: int(kv[0])):
                cells = "  ".join(f"m{m}: {v['total_pct']:+.0f}% Sh {v['sharpe']:.2f} DD {v['mdd_pct']:.0f}%" for m, v in sorted(months.items(), key=lambda kv: int(kv[0])))
                print(f"    size {size if size != '0' else 'all':>3}  {cells}")
    return 0


def cmd_watch(a: argparse.Namespace) -> int:
    with get_connection() as conn, conn.cursor() as cur:
        if a.sub == "add":
            cur.execute("INSERT INTO idx.watchlist (code, note) VALUES (%s, %s) ON CONFLICT (code) DO UPDATE SET note = EXCLUDED.note",
                        (a.code.upper(), a.note))
            conn.commit()
            print(f"watching {a.code.upper()}")
        elif a.sub == "rm":
            cur.execute("DELETE FROM idx.watchlist WHERE code = %s", (a.code.upper(),))
            conn.commit()
            print(f"removed {a.code.upper()} ({cur.rowcount})")
        else:
            cur.execute("SELECT code, note, added_at FROM idx.watchlist ORDER BY code")
            for r in cur.fetchall():
                r = list(r.values()) if isinstance(r, dict) else r
                print(f"{r[0]:<6} {str(r[2])[:10]}  {r[1] or ''}")
    return 0


def cmd_book(a: argparse.Namespace) -> int:
    from decimal import Decimal

    from . import book
    with get_connection() as conn:
        if a.sub == "show":
            print(book.render(book.snapshot(conn, a.book)))
        elif a.sub == "fills":
            with conn.cursor() as cur:
                cur.execute("SELECT id, trade_date, code, side, lots, price, fee, source, note FROM idx.fill WHERE book = %s ORDER BY trade_date DESC, id DESC LIMIT %s",
                            (a.book, a.limit))
                for r in cur.fetchall():
                    r = list(r.values()) if isinstance(r, dict) else list(r)
                    print(f"{r[0]:>5} {r[1]} {r[2]:<6} {r[3]:<5} {float(r[4]):>8g} @ {float(r[5]):>10,.0f} fee {float(r[6]):>10,.0f} {r[7]:<10} {r[8] or ''}")
        elif a.sub == "fill":
            fid = book.add_fill(conn, a.book, _d(a.date), a.code, a.side, Decimal(a.lots), Decimal(a.price),
                                Decimal(a.fee) if a.fee is not None else None, note=a.note)
            print(f"fill #{fid} recorded; cash now Rp {float(book.get_book(conn, a.book)['cash']):,.0f}")
            print(book.render(book.snapshot(conn, a.book)))
        elif a.sub == "cash":
            book.ensure_book(conn, a.book, cash=Decimal(a.amount))
            print(f"{a.book}: cash set to Rp {float(Decimal(a.amount)):,.0f}")
        elif a.sub == "set":
            fields = {k: v for k, v in (("fee_buy_pct", a.fee_buy), ("fee_sell_pct", a.fee_sell), ("div_tax_pct", a.div_tax), ("broker", a.broker),
                                        ("cash_floor_pct", a.cash_floor), ("stress_cash_pct", a.stress_cash), ("stress_rule", a.stress_rule),
                                        ("max_weight_pct", a.max_weight), ("max_sector_pct", a.max_sector), ("max_turnover_pct", a.max_turnover),
                                        ("min_v60", a.min_v60), ("regime_filter", a.regime_filter)) if v is not None}
            book.ensure_book(conn, a.book, **fields)
            print(f"{a.book}: {book.get_book(conn, a.book)}")
        elif a.sub == "import":
            n = book.import_csv(conn, a.book, a.file)
            print(f"imported {n} fills into {a.book}")
            print(book.render(book.snapshot(conn, a.book)))
        elif a.sub == "mark":
            r = book.mark(conn, a.book, _d(a.as_of) if a.as_of else None, rebuild=a.rebuild)
            _report(r)
            if r.status == "ok":
                print(book.render(book.snapshot(conn, a.book)))
        elif a.sub == "check":
            r = book.check(conn, a.book)
            _report(r)
            for al in runlog.open_alerts(conn, 20):
                if al["job"] == f"book:{a.book}":
                    print(f"  [{al['severity']}] {al['message']}")
        elif a.sub == "halt":
            from . import journal
            b = book.halt(conn, a.book, a.reason or "operator halt")
            journal.record(conn, a.book, "operator", "halt", rationale=b["halt_reason"])
            print(f"{a.book}: HALTED ({b['halt_reason']}) - no ticket builds/issues, no paper fills until `idx book resume`")
        elif a.sub == "resume":
            from . import journal
            book.resume(conn, a.book)
            journal.record(conn, a.book, "operator", "resume")
            print(f"{a.book}: active")
        elif a.sub == "journal":
            from . import journal
            for r in journal.recent(conn, a.book, a.code, a.limit):
                print(f"{r['ts']:%Y-%m-%d %H:%M} {r['actor']:<9} {r['action']:<13} {r['code'] or '':<6} #{r['ticket_id'] or '-':<5} {r['rationale'] or ''}")
        elif a.sub == "reconcile":
            from . import reconcile as rc
            rows = rc.parse_csv(Path(a.file).read_text(encoding="utf-8-sig"))
            rep = rc.reconcile(conn, a.book, rows, source=Path(a.file).name)
            print(rc.render(rep))
            return 0 if rep["ok"] else 1
        elif a.sub == "paper-seed":
            fills = book.paper_seed(conn, a.book, _d(a.as_of), Decimal(a.amount), fill=a.fill)
            print(f"{a.book}: {len(fills)} names bought on {fills[0]['date'] if fills else '-'}")
            r = book.mark(conn, a.book)
            _report(r)
            print(book.render(book.snapshot(conn, a.book)))
    return 0


def cmd_ticket(a: argparse.Namespace) -> int:
    from decimal import Decimal

    from . import ticket
    with get_connection() as conn:
        if a.sub == "build":
            res = ticket.build(conn, a.book, mode=a.mode, run_date=_d(a.as_of) if a.as_of else None, max_names=a.max_names,
                               strategy=a.strategy)
            tid = ticket.store(conn, res, notes=a.note)
            t = ticket.load(conn, tid)
            print(ticket.render(t))
            if a.out:
                Path(a.out).write_text(ticket.render(t), encoding="utf-8")
                print(f"wrote {a.out}")
        elif a.sub == "show":
            t = ticket.load(conn, a.id, None if a.id else a.book)
            print(ticket.render(t) if t else "no ticket")
        elif a.sub == "validate":
            t = ticket.load(conn, a.id, None if a.id else a.book)
            if not t:
                print("no ticket")
                return 1
            v = ticket.validate(conn, t["id"])
            print(f"ticket #{t['id']} {t['book']} {t['mode']} {t['status']} built by {v['actor']}: {'OK' if v['ok'] else 'BREACHES'} | "
                  f"turnover {float(v['turnover']) * 100:.0f} % | cash after Rp {float(v['cash_after']):,.0f}")
            for x in v["breaches"]:
                print(f"  - {x['kind']} {x['code'] or ''}: {x['detail']}")
            return 0 if v["ok"] else 1
        elif a.sub in ("issue", "close", "cancel"):
            t = ticket.load(conn, a.id, None if a.id else a.book)
            if not t:
                print("no ticket")
                return 1
            try:
                ticket.set_status(conn, t["id"], {"issue": "issued", "close": "closed", "cancel": "cancelled"}[a.sub], actor="operator", rationale=a.note)
            except ValueError as e:
                print(f"refused: {e}")
                return 1
            print(f"ticket #{t['id']} {'cancelled' if a.sub == 'cancel' else a.sub + 'd'}")
        elif a.sub == "paper-fill":
            for rep in ticket.paper_fill(conn, "paper", dry_run=a.dry_run):
                head = f"ticket #{rep['ticket']} ({rep['ticket_date']}) -> {rep['fill_date'] or rep.get('why')}{' [dry run]' if a.dry_run else ''}"
                print(head)
                for f in rep["fills"]:
                    print(f"  {f['side']:4s} {f['code']:6s} {f['lots']:>6} lots @ {f['price'] if f['price'] is not None else '-':>8}  {f['why'] or ''}")
                if rep["cash_after"] is not None:
                    print(f"  cash after: Rp {rep['cash_after']:,.0f}")
        elif a.sub == "fill":
            r = ticket.fill_line(conn, a.line, Decimal(a.lots), Decimal(a.price), Decimal(a.fee) if a.fee is not None else None,
                                 _d(a.date) if a.date else None, a.note)
            print(f"line {a.line}: {r['status']} ({float(r['filled_lots']):g} lots), fill #{r['fill_id']}")
        elif a.sub == "skip":
            ticket.skip_line(conn, a.line, a.reason or "operator skip")
            print(f"line {a.line}: skipped")
    return 0


def cmd_account(a: argparse.Namespace) -> int:
    """Desk accounts: list | reset-link EMAIL (a one-time password-reset link, 30 minutes, shown once - hand it to the person)."""
    from . import accounts
    with get_connection() as conn:
        if a.sub == "list":
            with conn.cursor() as cur:
                cur.execute("SELECT u.email, u.full_name, u.plan, u.created_at, u.last_login_at, "
                            "(SELECT count(*) FROM idx.book b WHERE b.owner_id = u.id AND b.archived_at IS NULL) AS books "
                            "FROM idx.app_user u ORDER BY u.created_at")
                for r in cur.fetchall():
                    r = dict(r)
                    print(f"{r['email']:<36} {r['full_name'][:24]:<24} {r['plan']:<6} books {r['books']}  joined {r['created_at']:%Y-%m-%d}"
                          f"  last login {r['last_login_at']:%Y-%m-%d %H:%M}" if r["last_login_at"] else
                          f"{r['email']:<36} {r['full_name'][:24]:<24} {r['plan']:<6} books {r['books']}  joined {r['created_at']:%Y-%m-%d}  never signed in")
            return 0
        tok = accounts.make_reset(conn, a.email, minutes=a.minutes)
    if not tok:
        print(f"no account {a.email!r}")
        return 1
    base = (a.base or os.environ.get("IDX_APP_URL") or "https://a8.tailbf9662.ts.net/blackridge").rstrip("/")
    print(f"{base}/reset?token={tok}")
    print(f"(one use, {a.minutes} minutes; older unused links for this account are now void)")
    return 0


def cmd_push(a: argparse.Namespace) -> int:
    from . import push
    with get_connection() as conn:
        if a.sub == "devices":
            print(f"push: {'configured' if push.configured() else 'NOT configured (set ' + push.SA_ENV + ')'}")
            for d in push.devices(conn, include_disabled=True):
                print(f"{d['token'][:12]}…  {d['platform']:<8} {d['username'] or '-':<12} {(d['label'] or '-')[:40]:<40} "
                      f"seen {d['last_seen']:%Y-%m-%d %H:%M}  sent {d['last_sent']:%Y-%m-%d %H:%M}" if d["last_sent"] else
                      f"{d['token'][:12]}…  {d['platform']:<8} {d['username'] or '-':<12} {(d['label'] or '-')[:40]:<40} seen {d['last_seen']:%Y-%m-%d %H:%M}",
                      "DISABLED " + (d["error"] or "") if d["disabled"] else (d["error"] or ""))
            return 0
        rep = push.send_all(conn, "Blackridge", a.text or "Blackridge: notifikasi aktif", {"route": "/m", "kind": "test"})
        print(rep)
        return 0 if rep["sent"] else 1


def cmd_notify(a: argparse.Namespace) -> int:
    from . import notify
    if a.status or not a.text:
        ch = notify.channels()
        print(f"channels: {', '.join(ch) if ch else 'NONE (app: set ' + notify.push.SA_ENV + ' to the Firebase service-account file; telegram: ' + notify.TOKEN_ENV + ' + ' + notify.CHAT_ENV + ')'}")
        return 0
    ok = notify.send(a.text)
    print("sent" if ok else "not sent (see log)")
    return 0 if ok else 1


def cmd_registry(a: argparse.Namespace) -> int:
    """The desk registry: what the desk runs, its record, and where the number came from."""
    from . import registry
    with get_connection() as conn:
        if a.sub == "refresh":
            res = registry.refresh_scorecard(conn)
            print(f"imported {res['written']} entries ({res['with_record']} with a record) from study #{res['study']} ({res.get('as_of')})"
                  if res["study"] else "no roi_scorecard study stored; nothing imported")
            return 0 if res["study"] else 1
        if a.sub == "show":
            e = registry.detail(conn, a.key or "")
            if e is None:
                print(f"unknown strategy {a.key!r}; one of {', '.join(registry.BY_KEY)}")
                return 1
            sc = e["scorecard"] or {}
            print(f"{e['label']}  [{e['status']} · {e['family']} · {e['cadence']}]")
            print(f"  rule       {e['rule']}")
            print(f"  falsifier  {e['falsifier'] or '-'}")
            print(f"  runs in    {e['runs_in']}")
            if sc.get("cagr_pct") is not None:
                print(f"  record     {sc['cagr_pct']:+.1f} %/yr · Sharpe {sc.get('sharpe')} · mDD {sc.get('mdd_pct')} % · {sc.get('window')}")
            if sc.get("effect"):
                print(f"  effect     {sc['effect']}")
            if sc.get("verdict"):
                print(f"  verdict    {sc['verdict']}")
            print(f"  books      {', '.join(b['book'] for b in e['books']) or '-'}")
            print(f"  evidence   {', '.join(f'#{s['id']} {s['name']}' for s in e['studies']) or '-'}")
            print(f"  refreshed  {e['refreshed_at'] or 'never - run: idx registry refresh'}")
            return 0
        d = registry.desk(conn)
        print(f"{len(d['strategies'])} strategies · records from study #{d['scorecard_study']} ({d['scorecard_as_of']})")
        for e in d["strategies"]:
            sc = e["scorecard"] or {}
            rec = (f"{sc['cagr_pct']:+6.1f} %/yr  Sharpe {sc.get('sharpe'):<5} mDD {sc.get('mdd_pct')} %"
                   if sc.get("cagr_pct") is not None else (sc.get("effect") or "no record")[:44])
            print(f"  {e['key']:<22} {e['status']:<10} {e['family']:<11} {rec:<48} {', '.join(b['book'] for b in e['books'])}")
        if d["closed"]["families"]:
            print()
            print(f"closed by research: {'; '.join(d['closed']['families'])}")
        return 0


def cmd_broker(a: argparse.Namespace) -> int:
    import json

    from . import broker
    with get_connection() as conn:
        if a.sub == "refresh":
            try:
                tok = broker.refresh_and_persist(conn=conn)                 # newest of env / relay row; written back to both
            except broker.BrokerFetchError as e:
                print(f"refresh failed: {e}")
                return 1
            exp = _jwt_exp(tok)
            print(f"token refreshed and written to idx-local.env + idx.feed_token (…{tok[-8:]}){f'; expires {exp}' if exp else ''}")
            return 0
        if a.sub == "universe":
            codes = broker.universe_codes(conn)
            print(f"{len(codes)} names: {' '.join(codes)}")
            return 0
        if a.sub == "day":
            codes = [c.strip().upper() for c in a.codes.split(",")] if a.codes else broker.universe_codes(conn)
            try:
                cfg = broker.config_fresh(conn=conn)                         # auto-refresh from the newest refresh token
            except broker.BrokerFetchError as e:
                print(f"config: {e}")
                return 1
            expected = _rows_last_bar(conn)
            try:
                res = broker.snapshot(conn, codes, cfg, rps=a.rps, expected_date=expected, log=print)
            except broker.BrokerFetchError as e:
                print(f"snapshot stopped: {e}")
                return 1
            print(res)
            return 0 if not res["stopped"] else 1
        if a.sub == "capture":
            try:
                cfg = broker.config_fresh(conn=conn)
            except broker.BrokerFetchError as e:
                print(f"config: {e}")
                return 1
            if a.codes:
                codes = [c.strip().upper() for c in a.codes.split(",")]
            elif a.min_v60:
                codes = broker.detail_codes(conn, a.min_v60)
            else:
                codes = broker.all_codes(conn)
            matrix = broker.MATRIX_DETAIL if a.detail else broker.MATRIX_CORE
            print(f"capture: {len(codes)} names x {len(matrix)} views = {len(codes) * len(matrix)} requests at {a.rps}/s (resumable)")
            try:
                res = broker.capture(conn, codes, matrix, cfg, rps=a.rps, expected_date=_rows_last_bar(conn), max_requests=a.max, log=print)
            except broker.BrokerFetchError as e:
                print(f"capture stopped: {e}")
                return 1
            print(res)
            return 0 if not res["stopped"] or res["stopped"].startswith("max requests") else 1
        if a.sub == "show":
            rows = broker.show(conn, a.code)
            if not rows:
                print("no rows")
                return 1
            print(f"{a.code.upper()} {rows[0]['date_from']} -> {rows[0]['date_to']}  (top by net value)")
            for r in rows:
                print(f"  {r['broker']:<4} {(r['broker_name'] or '')[:22]:<22} buy {float(r['buy_value'] or 0) / 1e9:8.2f} bn / {float(r['buy_lot'] or 0):>9,.0f} lot @ {float(r['buy_avg'] or 0):>8,.0f}"
                      f" | sell {float(r['sell_value'] or 0) / 1e9:8.2f} bn / {float(r['sell_lot'] or 0):>9,.0f} lot @ {float(r['sell_avg'] or 0):>8,.0f} | net {float(r['net_value'] or 0) / 1e9:+8.2f} bn")
            return 0
        if a.sub == "reparse":
            n = broker.reparse(conn, a.code or None)
            print(f"reparsed: {n} rows")
            return 0
        cfg = broker.config()
        if a.sub == "probe":
            d_to = _d(a.d_to) if a.d_to else _rows_last_bar(conn)
            d_from = _d(a.d_from) if a.d_from else d_to
            status, payload, err = broker.fetch(a.code, d_from, d_to, cfg)
            rows, diag = broker.parse(payload)
            print(f"HTTP {status} {err or ''} | payload keys: {list(payload)[:8] if isinstance(payload, dict) else type(payload).__name__} | parsed {diag['n']} rows | lists used {diag['lists_used']}")
            print(f"keys seen: {diag['keys_seen']}")
            txt = json.dumps(payload)[:1500] if payload is not None else ""
            print("payload head:", txt)
            if status == 200:
                broker.store(conn, a.code, d_from, d_to, cfg, status, payload, err)
                for r in rows[:8]:
                    print(f"  {r['broker']:<4} net {float(r['net_value']) / 1e9:+8.2f} bn  buy {float(r['buy_value'] or 0) / 1e9:.2f} / sell {float(r['sell_value'] or 0) / 1e9:.2f}")
            return 0 if status == 200 else 1
        codes = [c.strip().upper() for c in a.codes.split(",")] if a.codes else broker.universe_codes(conn)
        end = _d(a.end) if a.end else _rows_last_bar(conn)
        res = broker.backfill(conn, codes, _d(a.start), end, window=a.window, rps=a.rps, cfg=cfg, max_requests=a.max, log=print)
        print(res)
        return 0 if not res["stopped"] or res["stopped"].startswith("max_requests") else 1


def _rows_last_bar(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT max(trade_date) FROM idx.bar WHERE source = 'idx'")
        r = cur.fetchone()
        return next(iter(r.values())) if isinstance(r, dict) else r[0]


def cmd_trend(a: argparse.Namespace) -> int:
    from . import trend_book
    with get_connection() as conn:
        if a.sub == "books":
            for b in trend_book.trend_books(conn):
                print(b)
            return 0
        d = _d(a.as_of) if a.as_of else None
        if a.sub == "build":
            print(trend_book.render(trend_book.build(conn, a.book, d)))
            return 0
        rep = trend_book.run(conn, a.book, actor="operator", d=d)
        print(rep)
        return 0


def cmd_suggest(a: argparse.Namespace) -> int:
    """What the tape supports for the open lines of a ticket (the one-tap fill's proposal, on the terminal)."""
    from . import fillmatch, ticket
    with get_connection() as conn:
        tid = a.ticket
        if tid is None:
            t = ticket.load(conn, book=a.book)
            if t is None:
                print(f"no ticket for {a.book}")
                return 1
            tid = t["id"]
        print(fillmatch.render(fillmatch.suggest(conn, tid, _d(a.as_of) if a.as_of else None)))
        return 0


def cmd_gapfade(a: argparse.Namespace) -> int:
    """The intraday gap-fade book (research menu 29b): morning scan/entry, afternoon exit, evening settle."""
    import json as _json

    from . import gapfade
    with get_connection() as conn:
        d = _d(a.as_of) if a.as_of else None
        if a.sub == "books":
            for b in gapfade.gapfade_books(conn):
                print(b)
            return 0
        if a.sub == "scan":
            print(gapfade.render_scan(gapfade.scan(conn, d)))
            return 0
        if a.sub == "init":
            bk_ = a.book
            from . import book as bkmod
            with conn.cursor() as cur:                                  # the book belongs to a person: alerts and the app's
                cur.execute("""UPDATE idx.book SET owner_id = (SELECT id FROM idx.app_user WHERE email = %s)
                                WHERE book = %s AND owner_id IS NULL""",   # live screen are scoped to its owner
                            (a.owner or os.environ.get("IDX_AGENT_USER") or os.environ.get("IDX_OPS_NOTIFY_EMAIL"), bk_))
                conn.commit()
            bkmod.ensure_book(conn, bk_, rule="gapfade", max_names=a.slots, cash=a.cash, broker=a.broker, label=a.label,
                              fee_buy_pct=a.fee_buy, fee_sell_pct=a.fee_sell, min_v60=str(int(gapfade.LIQ_MIN)),
                              max_weight_pct=str(round(100 / max(1, a.slots) + 5, 2)), max_sector_pct="100",
                              note="gapfade: buy the opening gap-down, sell into the same close (menu 29b, paper track)")
            print(f"{bk_}: {bkmod.get_book(conn, bk_)}")
            return 0
        fn = {"entry": gapfade.run_entry, "exit": gapfade.run_exit, "settle": gapfade.settle}[a.sub]
        print(_json.dumps(fn(conn, a.book, actor="operator", d=d), indent=1, default=str))
        return 0


def cmd_ara(a: argparse.Namespace) -> int:
    """ARA watch (research menus 16 / ML-3 / 34): the evening list of likely touches, and today's touches off the feed."""
    import json as _json

    from . import ara
    with get_connection() as conn:
        if a.sub == "watch":
            rep = ara.watch(conn, top=a.top, notify=not a.no_notify, use_dl=False if a.no_dl else None)
            print(rep["text"])
            print(_json.dumps({k: v for k, v in rep.items() if k not in ("rows", "text")}, default=str))
            return 0
        if a.sub == "show":
            print(_json.dumps(ara.latest_watch(conn), indent=1, default=str))
            return 0
        if a.sub == "touch":
            print(_json.dumps(ara.touch_check(conn, force=a.force), indent=1, default=str))
            return 0
        print(ara.render_touches(ara.touches_today(conn, _d(a.as_of) if a.as_of else None)))
        return 0


def cmd_scores(a: argparse.Namespace) -> int:
    from . import scores
    with get_connection() as conn:
        d = _d(a.as_of) if a.as_of else None
        if a.sub == "build":
            res = scores.compute(conn, d)
            n = scores.store(conn, res)
            print(scores.render(res, top=a.top))
            print(f"stored {n} rows for {res['as_of']}")
        elif a.sub == "show":
            rows = scores.rows_for(conn, d, [a.code.upper()] if a.code else None)
            if a.code and rows:
                r = rows[0]
                print(f"{r['code']} {r['name'] or ''} {r['trade_date']}: value {r['value']} quality {r['quality']} trend {r['trend']} gates {r['gates']} "
                      f"breakout {r['trend_flag']} turnaround {r['turnaround']} bucket {r['bucket']}")
                print(json.dumps(r["inputs"], indent=1, default=str)[:4000])
            else:
                print(scores.render({"as_of": rows[0]["trade_date"] if rows else d, "rows": rows, "n": len(rows),
                                     "n_value": sum(1 for r in rows if r["value"] is not None), "n_quality": sum(1 for r in rows if r["gates"] is not None),
                                     "n_trend_flag": sum(1 for r in rows if r["trend_flag"]), "n_turnaround": sum(1 for r in rows if r["turnaround"])}, top=a.top))
        elif a.sub == "stats":
            from . import signal_stats
            if a.refresh:
                rep = signal_stats.refresh(conn)
                print(json.dumps(rep, indent=1, default=str))
            for r in signal_stats.rows(conn, a.criteria):
                print(f"{r['criteria']:15s} {r['bucket']:24s} h{r['horizon_days']:<4d} n={r['n']:<5d} hit={_pct_or(r['hit'])} med={_pct_or(r['median'])} "
                      f"mean={_pct_or(r['mean'])} loss50={_pct_or(r['p_loss50'])} mdd={_pct_or(r['mdd_book'])} {r['sample_from']}..{r['sample_to']} ({r['source'] or r['study_id']})")
    return 0


def _pct_or(v) -> str:
    return "-" if v is None else f"{float(v) * 100:.1f}%"


def cmd_report(a: argparse.Namespace) -> int:
    from . import report as rp
    with get_connection() as conn:
        rep = rp.build(conn, a.book, a.period, _d(a.as_of) if a.as_of else None)
    text = rp.render(rep, top=a.top)
    print(text)
    if a.notify:
        from . import notify
        print("sent" if notify.send(text) else "not sent")
    return 0


def cmd_track(a: argparse.Namespace) -> int:
    from . import book as bk
    from . import track as tk
    with get_connection() as conn:
        if a.book:
            books = [a.book]
        else:
            books = [b for b in bk.list_books(conn)
                     if (bk.get_book(conn, b).get("rule") or "").lower() in tk.PROFILES] if a.all else ["paper"]
        blocks = []
        for b in books:
            sc = tk.scorecard(conn, b)
            blocks.append(tk.render(sc))
            if a.trades:
                for t in sc["trades"]:
                    blocks.append(f"    {t['closed']} {t['code']:<6} {t['net_pct'] * 100:+6.1f}%  {t['hold_d']}d")
    text = "\n\n".join(blocks)
    print(text)
    if a.notify:
        from . import notify
        print("sent" if notify.send(text, title="Track record") else "not sent")
    return 0


def cmd_quote(a: argparse.Namespace) -> int:
    from . import quote as q
    with get_connection() as conn:
        for r in q.latest(conn, a.codes.split(",")):
            if r.get("error"):
                print(f"{r['code']:<6} {r['error']}")
                continue
            chg = f"{float(r['chg_pct']):+.2f} %" if r["chg_pct"] is not None else "-"
            v60 = f"Rp {float(r['v60']) / 1e9:.1f} bn/d" if r["v60"] is not None else "-"
            print(f"{r['code']:<6} {r['trade_date']} close {float(r['close']):>9,.0f} ({chg})  v60 {v60}  tick {r['tick']}  band {float(r['band_lo']):,.0f}-{float(r['band_hi']):,.0f}  {r['name'] or ''}")
    return 0


def cmd_crosscheck(a: argparse.Namespace) -> int:
    codes = [c.strip().upper() for c in a.codes.split(",")] if a.codes else None
    with get_connection() as conn, IdxClient() as cl:
        r = job_crosscheck.run(conn, cl, sample=a.sample, codes=codes)
    _report(r)
    for w in r.warnings:
        print(f"    {w}")
    return 0 if r.status == "ok" else 1


def cmd_feed(a: argparse.Namespace) -> int:
    """Stockbit datafeed collector: run | status | symbols [--set A,B] [--liquid N] [--disable A,B] | token [--paste FILE] | audit [--date D]"""
    from .feed import store as fs
    if a.action == "run":
        from .feed.collector import main as feed_main
        return feed_main(["--no-raw"] if a.no_raw else [])
    if a.action == "replay":
        from .feed.collector import main as feed_main
        if not a.file:
            print("feed replay --file logs/idx/feed/<date>.frames.gz")
            return 2
        return feed_main(["--replay", a.file])
    with get_connection() as conn:
        if a.action == "status":
            st = fs.status(conn)
            c, t = st["collector"], st["token"]
            print(f"collector: {c.get('state')}  {c.get('detail') or ''}  (pid {c.get('pid')}, heartbeat {c.get('stale_s', '?')} s ago)")
            print(f"  frames {c.get('n_frames', 0):,}  trades {c.get('n_trades', 0):,}  books {c.get('n_books', 0):,}  symbols {c.get('n_symbols', 0)}  reconnects {c.get('reconnects', 0)}  last frame {c.get('last_frame_at') or '-'}")
            print(f"token: {'valid' if t['valid'] else 'MISSING/EXPIRED'}  expires {t.get('expires_at') or '-'}  ({t.get('minutes_left')} min left, source {t.get('source')}, user {t.get('user_id')})")
            td = st["today"]
            print(f"today: {td['trades'] or 0:,} prints on {td['codes'] or 0} names  {td['first_at'] or ''} -> {td['last_at'] or ''}   subscribed {st['symbols_enabled']}")
            for e in st["events"]:
                print(f"  {e['at']:%Y-%m-%d %H:%M:%S} {e['kind']:<10} {e['detail'] or ''}")
            return 0
        if a.action == "symbols":
            if a.liquid:
                n = fs.set_symbols(conn, fs.liquid_codes(conn, a.liquid), reason="liquid", replace=True)
                print(f"seeded {n} liquid/held/watched names")
            if a.set:
                print(f"set {fs.set_symbols(conn, a.set.split(','), reason='manual')}")
            if a.disable:
                print(f"disabled {fs.disable_symbols(conn, a.disable.split(','))}")
            rows = fs.list_symbols(conn)
            on = [r for r in rows if r["enabled"]]
            print(f"{len(on)} enabled of {len(rows)}: " + " ".join(r["code"] for r in on))
            return 0
        if a.action == "token":
            if a.paste:
                raw = open(a.paste, encoding="utf-8").read() if a.paste != "-" else sys.stdin.read()
                row = fs.save_token(conn, fs.parse_relay(raw), source="paste")
                print(f"stored: user {row['user_id']} expires {row['expires_at']}")
            t = fs.token_status(fs.load_token(conn))
            print(f"token {'valid' if t['valid'] else 'MISSING/EXPIRED'}: expires {t.get('expires_at') or '-'} ({t.get('minutes_left')} min left), source {t.get('source')}, user {t.get('user_id')}, received {t.get('received_at') or '-'}")
            return 0 if t["valid"] else 1
        if a.action == "audit":
            d = date.fromisoformat(a.date) if a.date else date.today()
            rows = fs.audit_day(conn, d)
            print(f"{d}: {len(rows)} names")
            for r in sorted(rows, key=lambda r: (r["coverage"] is None, r["coverage"] or 0)):
                cov = f"{float(r['coverage']) * 100:6.1f} %" if r["coverage"] is not None else "   n/a  "
                print(f"  {r['code']:<6} prints {r['n_trades']:>7,}  vol {r['volume']:>14,}  official {r['official_vol'] or 0:>14,}  cov {cov}  gap {r['max_gap_s'] or 0:>5} s  books {r['n_books']:>6}")
            return 0
    print("feed: run | status | symbols | token | audit | replay")
    return 2


def cmd_ml(a: argparse.Namespace) -> int:
    """The self-learning prediction desk (idx/ml): train | predict | eval | scorecard | status | show CODE | board | models."""
    import json as _json

    from .ml import common as mlc
    from .ml import loop as ml
    with get_connection() as conn:
        if a.sub == "train":
            for kind in (["daily", "intraday"] if a.kind == "all" else [a.kind]):
                rep = ml.train(conn, kind, tune=not a.no_tune, horizons=a.horizons.split(",") if a.horizons else None, placebo=a.placebo)
                print(rep["text"])
            return 0
        if a.sub == "calibrate":
            for c in ml.fit_calibration(conn):
                print(f"{c['horizon']:>4}: n {c['n']:,} knots {c['knots']} curve {c['lo']:.2f}..{c['hi']:.2f} hit@0.5 raw {c['raw_hit'] * 100:.1f} % -> cal {c['cal_hit'] * 100:.1f} %")
            return 0
        if a.sub == "predict":
            if a.kind in ("daily", "all"):
                print(_json.dumps(ml.predict_daily(conn), default=str))
            if a.kind in ("intraday", "all"):
                print(_json.dumps(ml.predict_intraday(conn), default=str))
            return 0
        if a.sub == "eval":
            print(_json.dumps(ml.evaluate(conn), default=str))
            return 0
        if a.sub == "scorecard":
            print(ml.render_scorecard(ml.scorecard(conn, _d(a.as_of) if a.as_of else None)))
            return 0
        if a.sub == "status":
            print(ml.render_status(ml.status(conn)))
            return 0
        if a.sub == "show":
            if not a.code:
                print("usage: idx ml show CODE")
                return 2
            for r in ml.latest_for(conn, a.code.upper()):
                px = "-" if r["pred_price"] is None else f"{r['pred_price']:,.0f}"
                pu = "-" if r["p_up"] is None else f"{r['p_up']:.2f}"
                rel = " vs IHSG" if r.get("basis") == "excess" else ""
                line = (f"{r['horizon']:>4} {r['label']:<26} cut {r['made_at']:%Y-%m-%d %H:%M} ref {r['ref_price']:,.0f} -> {px} "
                        f"({(r['pred_ret'] or 0) * 1e4:+.0f} bps{rel}) P(naik{rel}) {pu}")
                if r.get("realized_ret") is not None:
                    line += f" | terjadi {r['realized_price']:,.0f} ({r['realized_ret'] * 1e4:+.0f} bps) hit={r['hit']}"
                t = r.get("track") or {}
                if t.get("hit_rate") is not None:
                    line += f" | rekam 20d: hit {t['hit_rate'] * 100:.1f} % vs base {t['base_hit'] * 100:.1f} %, IC {t['ic'] if t['ic'] is None else '%.3f' % t['ic']}"
                print(line)
            return 0
        if a.sub == "board":
            print(_json.dumps(ml.board(conn, a.horizon, a.top), default=str, indent=1))
            return 0
        for m in mlc.models(conn, a.top):
            v = m["val_metrics"] or {}
            prim = "-" if v.get("primary") is None else f"{v['primary']:.3f}"
            print(f"#{m['model_id']} {m['horizon']:>4} {m['task']} {m['status']:<9} {m['origin']:<7} {m['trained_at']:%m-%d %H:%M} "
                  f"val {m['val_from']}..{m['val_to']} primary {prim} - {m['reason']}")
        return 0


def cmd_combo(a: argparse.Namespace) -> int:
    """The combined book (idx/combo_book.py): create | set | plan | preopen | confirm | gap-entry | gap-exit | expire | nudge | scorecard | status."""
    import json as _json

    from . import combo_book as cb
    with get_connection() as conn:
        if a.sub == "create":
            owner = None
            if a.owner:
                from . import accounts
                u = accounts.get_user(conn, a.owner)
                if not u:
                    print(f"no account {a.owner}")
                    return 2
                owner = str(u["id"])
            sleeves = {k: float(v) for k, v in (("trend", a.trend), ("ml", a.ml), ("gap", a.gap)) if v is not None}
            bid = cb.create(conn, owner, a.kind, a.label or f"combo {a.kind}", a.cash, broker=a.broker, sleeves=sleeves or None, slots=a.slots)
            print(bid)
            return 0
        books = [a.book] if a.book else cb.combo_books(conn)
        if a.sub == "set":
            from . import book as bkm
            for bkid in books:
                b = bkm.get_book(conn, bkid)
                p = dict(b.get("params") or {})
                p.setdefault("sleeves", {})
                for k, v in (("trend", a.trend), ("ml", a.ml), ("gap", a.gap)):
                    if v is not None:
                        p["sleeves"][k] = float(v)
                if a.slots:
                    p["slots"] = int(a.slots)
                if a.cash_floor is not None:
                    p["cash_floor"] = float(a.cash_floor)
                if a.ml_confirm is not None:                                  # "5/10,8/10,10/10,8/5" -> [[0.05, 10], ...]; "single" -> the one rule
                    p.setdefault("ml", {})
                    if a.ml_confirm.strip().lower() in ("single", "none", "off"):
                        p["ml"]["confirm_rules"] = None
                    else:
                        p["ml"]["confirm_rules"] = [[float(x.split("/")[0]) / 100, int(x.split("/")[1])] for x in a.ml_confirm.split(",") if x.strip()]
                cb.settings({"params": p})
                bkm.ensure_book(conn, bkid, params=p)
                print(bkid, _json.dumps(p))
            return 0
        for bkid in books:
            if a.sub == "plan":
                rep = cb.plan(conn, bkid, actor="operator", d=_d(a.as_of) if a.as_of else None)
                print(rep.get("text") or rep)
            elif a.sub == "preopen":
                print(cb.preopen(conn, bkid, _d(a.as_of) if a.as_of else None))
            elif a.sub == "confirm":
                print(_json.dumps(cb.confirm(conn, bkid, actor="operator"), default=str))
            elif a.sub == "gap-entry":
                print(_json.dumps(cb.gap_entry(conn, bkid, actor="operator", d=_d(a.as_of) if a.as_of else None), default=str))
            elif a.sub == "gap-exit":
                print(_json.dumps(cb.gap_exit(conn, bkid, actor="operator", d=_d(a.as_of) if a.as_of else None), default=str))
            elif a.sub == "expire":
                print(_json.dumps(cb.expire(conn, bkid, actor="operator"), default=str))
            elif a.sub == "nudge":
                print(cb.nudge(conn, bkid) or "nothing open")
            elif a.sub == "scorecard":
                print(cb.render_scorecard(cb.scorecard(conn, bkid)))
            else:
                from . import book as bkm
                b = bkm.get_book(conn, bkid)
                pos = cb.sleeve_positions(conn, bkid)
                print(f"{bkid} [{b.get('label')}] rule {b.get('rule')} cash Rp {float(b['cash']):,.0f} settings {_json.dumps(cb.settings(b))}")
                for s_, d in pos.items():
                    if d:
                        print(f"  {s_}: " + ", ".join(f"{c} {int(p['lots'])} lot @ {float(p['entry_price'] or 0):,.0f} since {p['entry_date']}" for c, p in d.items()))
                for w in cb.pending_watches(conn, bkid):
                    print(f"  watch {w['code']} level {float(w['level_price']):,.0f} until {w['until_date']} (e {float(w['e_bps']):+.0f} bps)")
        return 0


def cmd_run_scheduler(_: argparse.Namespace) -> int:
    import os
    from logging.handlers import RotatingFileHandler

    from . import scheduler
    log_dir = os.environ.get("INGEST_IDX_LOG_DIR")
    if log_dir:
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        h = RotatingFileHandler(Path(log_dir) / "scheduler.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logging.getLogger().addHandler(h)
        logging.getLogger().setLevel(logging.INFO)
    return scheduler.main()


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="idx", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate", help="apply pending idx.* migrations").set_defaults(fn=cmd_migrate)
    sub.add_parser("status", help="show migration state").set_defaults(fn=cmd_status)
    p = sub.add_parser("universe", help="Daftar Saham snapshot")
    p.add_argument("--date", help="snapshot date (default: today UTC)")
    p.set_defaults(fn=cmd_universe)
    p = sub.add_parser("daily", help="one day's whole-market summary")
    p.add_argument("--date", required=True)
    p.set_defaults(fn=cmd_daily)
    p = sub.add_parser("index", help="one day's index summary")
    p.add_argument("--date", required=True)
    p.set_defaults(fn=cmd_index)
    p = sub.add_parser("backfill", help="daily (+index) for every weekday in a range; resumable")
    p.add_argument("--from", dest="from_", required=True)
    p.add_argument("--to")
    p.add_argument("--index", action="store_true", help="also pull index summaries")
    p.add_argument("--refresh", action="store_true", help="re-fetch even if bronze has the day")
    p.set_defaults(fn=cmd_backfill)
    p = sub.add_parser("replay", help="re-derive silver from bronze")
    p.add_argument("--job", choices=["daily", "index"], default="daily")
    p.add_argument("--date", required=True)
    p.add_argument("--to")
    p.set_defaults(fn=cmd_replay)
    p = sub.add_parser("publish", help="project idx.bar into market_data (<CODE>.JK, 1d, split-only)")
    p.add_argument("--since", help="only bars on/after this date (default: last 7 days)")
    p.add_argument("--full", action="store_true", help="every bar + the Yahoo pre-2020 segment")
    p.add_argument("--codes", help="comma list; default all codes with idx bars")
    p.add_argument("--yahoo-dir", default=str(Path(__file__).resolve().parents[4] / "research-scratch" / "idx"))
    p.set_defaults(fn=cmd_publish)
    p = sub.add_parser("announce", help="disclosure metadata per code (archive starts 2023-07)")
    p.add_argument("--codes")
    p.add_argument("--from", dest="from_")
    p.add_argument("--to")
    p.add_argument("--refresh", action="store_true", help="re-fetch codes already archived")
    p.add_argument("--reclassify", action="store_true", help="recompute kinds/events from stored titles, no network")
    p.set_defaults(fn=cmd_announce)
    p = sub.add_parser("features", help="PIT overlay features (flow, liquidity, mcap, events)")
    p.add_argument("--since")
    p.add_argument("--codes")
    p.add_argument("--publish", action="store_true", help="also mirror into feature_registry/feature_values (universe codes)")
    p.set_defaults(fn=cmd_features)
    p = sub.add_parser("fin", help="financial statements: discover | download")
    p.add_argument("sub", choices=["discover", "download", "parse"])
    p.add_argument("--reparse", action="store_true", help="parse: also re-parse reports already parsed")
    p.add_argument("--years", help="e.g. 2020-2025 or 2024,2025")
    p.add_argument("--periods", help="comma list of tw1,tw2,tw3,audit")
    p.add_argument("--codes")
    p.add_argument("--universe", action="store_true", help="codes from research-scratch/idx-screen/universe.json")
    p.add_argument("--limit", type=int)
    p.set_defaults(fn=cmd_fin)
    p = sub.add_parser("dividends", help="Yahoo dividend events -> idx.dividend (secondary source, dated)")
    p.add_argument("--codes")
    p.add_argument("--universe", action="store_true")
    p.set_defaults(fn=cmd_dividends)
    p = sub.add_parser("card", help="thesis card for one stock (markdown)")
    p.add_argument("code")
    p.add_argument("--as-of")
    p.add_argument("--out")
    p.set_defaults(fn=cmd_card)
    p = sub.add_parser("candidates", help="value/quality candidate list as of a date")
    p.add_argument("--as-of")
    p.add_argument("--top", type=int)
    p.add_argument("--out")
    p.set_defaults(fn=cmd_candidates)
    p = sub.add_parser("pack", help="analysis pack for manual Claude chat")
    p.add_argument("--as-of")
    p.add_argument("--next", type=int, default=10)
    p.add_argument("--codes")
    p.add_argument("--out")
    p.set_defaults(fn=cmd_pack)
    p = sub.add_parser("pack-import", help="import the JSON answer for a pack")
    p.add_argument("file")
    p.add_argument("--date")
    p.set_defaults(fn=cmd_pack_import)
    p = sub.add_parser("answers", help="imported pack answers")
    p.add_argument("--code")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--score", action="store_true", help="forward returns per stance (21/63/126/252 trading days) and vs COMPOSITE")
    p.set_defaults(fn=cmd_answers)
    p = sub.add_parser("strategies", help="strategy catalog: list | import-history FILE...")
    p.add_argument("sub", choices=["list", "import-history"])
    p.add_argument("files", nargs="*")
    p.set_defaults(fn=cmd_strategies)
    p = sub.add_parser("annual", help="annual reports: discover [--years] | download [--codes|--list|--universe] [--years] [--limit] | extract [--codes] [--years] [--reparse] | status | show CODE")
    p.add_argument("sub", choices=["discover", "download", "extract", "status", "show"])
    p.add_argument("--codes", help="comma list, or the code for `show`")
    p.add_argument("--years", help="e.g. 2024-2025 or 2025")
    p.add_argument("--list", action="store_true", help="download: today's lists and book holdings")
    p.add_argument("--universe", action="store_true", help="download: the whole liquid universe (large)")
    p.add_argument("--limit", type=int)
    p.add_argument("--reparse", action="store_true")
    p.set_defaults(fn=cmd_annual)
    p = sub.add_parser("news", help="news feeds: pull | show [--codes C] [--limit N]")
    p.add_argument("sub", choices=["pull", "show"])
    p.add_argument("--codes")
    p.add_argument("--limit", type=int)
    p.set_defaults(fn=cmd_news)
    p = sub.add_parser("consensus", help="analyst consensus snapshots: pull [--codes A,B] | show [--codes A,B]")
    p.add_argument("sub", choices=["pull", "show"])
    p.add_argument("--codes")
    p.set_defaults(fn=cmd_consensus)
    p = sub.add_parser("levels", help="price alerts per held name: set CODE [--stop L] [--tp L] [--warn L] [--note] | list | clear CODE [--kind] | reset CODE | check")
    p.add_argument("sub", choices=["set", "list", "clear", "reset", "check"])
    p.add_argument("code", nargs="?")
    p.add_argument("--book", default="live")
    p.add_argument("--stop")
    p.add_argument("--tp")
    p.add_argument("--warn")
    p.add_argument("--kind", choices=["stop", "take_profit", "warn"])
    p.add_argument("--note")
    p.set_defaults(fn=cmd_levels)
    p = sub.add_parser("board", help="what the five best strategies say on a day (entries only, no book)")
    p.add_argument("--as-of", help="default: the newest bar date")
    p.add_argument("--record", action="store_true", help="also store the rows in idx.strategy_signal and raise the alerts")
    p.set_defaults(fn=cmd_board)
    p = sub.add_parser("study", help="research results in the DB: list [--name N] | show [--id I | --name N] | name CODE")
    p.add_argument("sub", choices=["list", "show", "name"])
    p.add_argument("--name")
    p.add_argument("--id", type=int)
    p.add_argument("code", nargs="?")
    p.set_defaults(fn=cmd_study)
    p = sub.add_parser("evidence", help="per-name evidence: collect CODE[,CODE] [--days N] | add CODE --kind K --title T [...] | show CODE [--kind K]")
    p.add_argument("sub", choices=["collect", "add", "show"])
    p.add_argument("code")
    p.add_argument("--kind", choices=["news", "announcement", "annual", "web", "analyst", "note"])
    p.add_argument("--title")
    p.add_argument("--url")
    p.add_argument("--source")
    p.add_argument("--summary")
    p.add_argument("--tags", help="comma list, e.g. operational,guidance")
    p.add_argument("--ts", help="ISO timestamp of publication")
    p.add_argument("--days", type=int)
    p.add_argument("--study", type=int, help="study id to attach the evidence to")
    p.add_argument("--limit", type=int)
    p.set_defaults(fn=cmd_evidence)
    p = sub.add_parser("macro", help="macro series: pull [--keys a,b] [--full] | show | bps-find [--keys KEYWORD]")
    p.add_argument("sub", choices=["pull", "show", "bps-find"])
    p.add_argument("--keys", help="comma list of series keys (default all); for bps-find: the keyword (default 'inflasi')")
    p.add_argument("--full", action="store_true", help="reload from 2005")
    p.set_defaults(fn=cmd_macro)
    p = sub.add_parser("overlay", help="book overlays: status | check [--as-of D] [--dry-run] (regime filter, entry gate)")
    p.add_argument("sub", choices=["status", "check"])
    p.add_argument("--as-of")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_overlay)
    p = sub.add_parser("watch", help="watchlist")
    p.add_argument("sub", choices=["list", "add", "rm"])
    p.add_argument("code", nargs="?")
    p.add_argument("--note")
    p.set_defaults(fn=cmd_watch)
    p = sub.add_parser("book", help="position book: live (your fills) and paper (the annual value book)")
    p.add_argument("sub", choices=["show", "fills", "fill", "cash", "set", "import", "mark", "check", "paper-seed", "halt", "resume", "journal",
                                   "reconcile"])
    p.add_argument("--book", default="live")
    p.add_argument("--reason", help="halt: why (recorded on the book and in the journal)")
    p.add_argument("--max-weight", help="set: one name after a ticket, %% of NAV")
    p.add_argument("--max-sector", help="set: one sector after a ticket, %% of NAV")
    p.add_argument("--max-turnover", help="set: agent rebalance outside May 1-10, traded / NAV %%")
    p.add_argument("--min-v60", help="set: liquidity floor for a buy, Rp/day")
    p.add_argument("--regime-filter", choices=["on", "off"], help="set: trend book = no new entry while COMPOSITE < MA200 (regime gate); annual book = all to cash under MA200")
    p.add_argument("--date")
    p.add_argument("--code")
    p.add_argument("--side", choices=["buy", "sell"])
    p.add_argument("--lots")
    p.add_argument("--price")
    p.add_argument("--fee", help="absolute IDR; default = book fee %% of gross")
    p.add_argument("--note")
    p.add_argument("--amount", help="cash amount (cash / paper-seed)")
    p.add_argument("--fee-buy")
    p.add_argument("--fee-sell")
    p.add_argument("--cash-floor", help="set: standing cash buffer, %% of NAV (0 = off)")
    p.add_argument("--stress-cash", help="set: cash while the stress detector is on, %% of NAV (0 = off)")
    p.add_argument("--stress-rule", choices=["ma", "any2"], help="set: the detector (ma = index under MA200; any2 = two of four signals)")
    p.add_argument("--div-tax")
    p.add_argument("--broker")
    p.add_argument("--file")
    p.add_argument("--as-of")
    p.add_argument("--rebuild", action="store_true")
    p.add_argument("--fill", choices=["next_open", "close"], default="next_open")
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(fn=cmd_book)
    p = sub.add_parser("ticket", help="rebalance ticket: target list vs held -> buys/sells in lots; fill capture")
    p.add_argument("sub", choices=["build", "show", "validate", "issue", "close", "cancel", "fill", "skip", "paper-fill"])
    p.add_argument("--book", default="live")
    p.add_argument("--dry-run", action="store_true", help="paper-fill: show what would fill, change nothing")
    p.add_argument("--mode", choices=["rebalance", "exits", "cash"], default="rebalance")
    p.add_argument("--as-of", help="candidate run date to target (default latest)")
    p.add_argument("--max-names", type=int)
    p.add_argument("--strategy", help="catalog key (default: the book's strategy); see `idx strategies list`")
    p.add_argument("--id", type=int)
    p.add_argument("--line", type=int)
    p.add_argument("--lots")
    p.add_argument("--price")
    p.add_argument("--fee")
    p.add_argument("--date")
    p.add_argument("--note")
    p.add_argument("--reason")
    p.add_argument("--out")
    p.set_defaults(fn=cmd_ticket)
    p = sub.add_parser("notify", help="send TEXT to the operator's phone (Blackridge app push; Telegram if configured), or --status")
    p.add_argument("text", nargs="?")
    p.add_argument("--status", action="store_true")
    p.set_defaults(fn=cmd_notify)
    p = sub.add_parser("registry", help="the desk registry: list (every strategy with its imported record) | show KEY | refresh (re-import records from the newest roi_scorecard study)")
    p.add_argument("sub", choices=["list", "show", "refresh"], nargs="?", default="list")
    p.add_argument("key", nargs="?")
    p.set_defaults(fn=cmd_registry)
    p = sub.add_parser("broker", help="broker summary feed (Stockbit data account): capture [--codes] [--detail] (all rolling windows 1D/1M/3M/1Y + the buyer->seller matrix, whole market; --detail = investor split, all boards, lots on the liquid names) | day [--codes|--universe] (today's 1-day snapshot only) | refresh (rotate the token) | probe CODE | backfill [--codes|--universe] (legacy, Pro-only now) | show CODE | reparse [--codes] | universe")
    p.add_argument("sub", choices=["capture", "day", "refresh", "probe", "backfill", "show", "reparse", "universe"])
    p.add_argument("--detail", action="store_true", help="capture: the 48-view matrix (investor ALL/FOREIGN/DOMESTIC x board REGULER/ALL x value/lots) instead of the 4 core views")
    p.add_argument("--min-v60", dest="min_v60", type=float, help="capture: only names with 60d median value >= this (Rp); default = the whole market")
    p.add_argument("code", nargs="?")
    p.add_argument("--codes", help="comma-separated; default for backfill = --universe")
    p.add_argument("--universe", action="store_true", help="liquid names (60d value >= Rp 20 bn, price >= 1,000)")
    p.add_argument("--from", dest="d_from")
    p.add_argument("--to", dest="d_to")
    p.add_argument("--start", default="2023-09-01")
    p.add_argument("--end")
    p.add_argument("--window", type=int, default=20, help="trading days per request window")
    p.add_argument("--rps", type=float, default=1.0)
    p.add_argument("--max", type=int, help="stop after this many requests (a first careful run)")
    p.set_defaults(fn=cmd_broker)
    p = sub.add_parser("account", help="desk accounts: list | reset-link EMAIL [--minutes 30] [--base URL] (one-time password-reset link)")
    p.add_argument("sub", choices=["list", "reset-link"])
    p.add_argument("email", nargs="?")
    p.add_argument("--minutes", type=int, default=30)
    p.add_argument("--base")
    p.set_defaults(fn=cmd_account)
    p = sub.add_parser("push", help="phone push (Blackridge app): devices | test [--text T]")
    p.add_argument("sub", choices=["devices", "test"])
    p.add_argument("--text")
    p.set_defaults(fn=cmd_push)
    p = sub.add_parser("trend", help="trend book (breakout + trailing stop): build [--book B] [--as-of D] (dry: print only) | run (store + issue/draft) | books")
    p.add_argument("sub", choices=["build", "run", "books"])
    p.add_argument("--book", default="paper_trend")
    p.add_argument("--as-of")
    p.set_defaults(fn=cmd_trend)
    p = sub.add_parser("suggest", help="what the tape supports for a ticket's open lines: suggest [--ticket N | --book B] [--as-of D]")
    p.add_argument("--ticket", type=int, default=None)
    p.add_argument("--book", default="trend_live")
    p.add_argument("--as-of")
    p.set_defaults(fn=cmd_suggest)
    p = sub.add_parser("gapfade", help="intraday gap-fade book (menu 29b): scan | entry (08:58) | exit (15:50) | settle (evening) | books | init [--book B --cash N --slots K]")
    p.add_argument("sub", choices=["scan", "entry", "exit", "settle", "books", "init"])
    p.add_argument("--book", default="paper_gapfade")
    p.add_argument("--as-of")
    p.add_argument("--cash", default="100000000")
    p.add_argument("--slots", type=int, default=5)
    p.add_argument("--broker", default="stockbit")
    p.add_argument("--label", default="Gap fade")
    p.add_argument("--fee-buy", dest="fee_buy", default="0.10")
    p.add_argument("--fee-sell", dest="fee_sell", default="0.20")
    p.add_argument("--owner", default=None, help="account e-mail the book belongs to (default IDX_AGENT_USER)")
    p.set_defaults(fn=cmd_gapfade)
    p = sub.add_parser("ara", help="ARA watch: watch (evening list from today's bars) | show (latest list) | touch (check the feed now) | today (today's touches)")
    p.add_argument("sub", choices=["watch", "show", "touch", "today"])
    p.add_argument("--top", type=int, default=10)
    p.add_argument("--no-notify", dest="no_notify", action="store_true")
    p.add_argument("--no-dl", dest="no_dl", action="store_true", help="watch: LightGBM only, skip the GRU (faster, tree rank)")
    p.add_argument("--force", action="store_true", help="touch: run even outside the session")
    p.add_argument("--as-of")
    p.set_defaults(fn=cmd_ara)
    p = sub.add_parser("ml", help="self-learning prediction desk: train [--kind daily|intraday|all] [--no-tune] [--horizons 1d,20d] [--placebo N] | predict [--kind] | eval | calibrate | scorecard [--as-of D] | status | show CODE | board [--horizon H] [--top N] | models [--top N]")
    p.add_argument("sub", choices=["train", "predict", "eval", "calibrate", "scorecard", "status", "show", "board", "models"])
    p.add_argument("--placebo", type=int, default=0, help="train: N label-shuffled refits per (horizon, task) on the newest block (slow)")
    p.add_argument("code", nargs="?")
    p.add_argument("--kind", choices=["daily", "intraday", "all"], default="all")
    p.add_argument("--no-tune", dest="no_tune", action="store_true", help="train: skip the perturbed-params challenger")
    p.add_argument("--horizons", help="train: comma-separated subset, e.g. 1d,20d")
    p.add_argument("--horizon", default="1d")
    p.add_argument("--top", type=int, default=20)
    p.add_argument("--as-of")
    p.set_defaults(fn=cmd_ml)
    p = sub.add_parser("combo", help="combined book: create --kind paper|live --label L --cash RP [--owner EMAIL] [--trend 0.05 --ml 0.05 --gap 0.10 --slots 20] | set [--book B] [--trend|--ml|--gap|--slots] | plan | preopen | confirm | gap-entry | gap-exit | expire | nudge | scorecard | status [--book B] [--as-of D]")
    p.add_argument("sub", choices=["create", "set", "plan", "preopen", "confirm", "gap-entry", "gap-exit", "expire", "nudge", "scorecard", "status"])
    p.add_argument("--book")
    p.add_argument("--kind", choices=["paper", "live"], default="paper")
    p.add_argument("--label")
    p.add_argument("--cash", type=float, default=20_000_000)
    p.add_argument("--owner", help="email of the owning account")
    p.add_argument("--broker")
    p.add_argument("--trend", type=float)
    p.add_argument("--ml", type=float)
    p.add_argument("--gap", type=float)
    p.add_argument("--slots", type=int)
    p.add_argument("--cash-floor", type=float, help="set: share of NAV kept in cash, e.g. 0.30 (menu 34); 0 = off")
    p.add_argument("--ml-confirm", help="set: confirmation rules 'pct/days,...' e.g. '5/10,8/10,10/10,8/5' (ML-8 ens4), or 'single'")
    p.add_argument("--as-of")
    p.set_defaults(fn=cmd_combo)
    p = sub.add_parser("scores", help="public factor scores (spec §04): build [--as-of D] | show [--code X] [--as-of D] | stats [--refresh] [--criteria C]")
    p.add_argument("sub", choices=["build", "show", "stats"])
    p.add_argument("--as-of")
    p.add_argument("--code")
    p.add_argument("--criteria")
    p.add_argument("--refresh", action="store_true", help="stats: re-import signal_stats from the recorded research")
    p.add_argument("--top", type=int, default=20)
    p.set_defaults(fn=cmd_scores)
    p = sub.add_parser("report", help="NAV vs IHSG/LQ45/IDXV30/IDX30 + per-name contribution: --book B --period since|mtd|ytd|1m|3m|6m|1y|A:B")
    p.add_argument("--book", default="paper")
    p.add_argument("--period", default="since")
    p.add_argument("--as-of")
    p.add_argument("--top", type=int, default=5)
    p.add_argument("--notify", action="store_true", help="also send the summary to Telegram")
    p.set_defaults(fn=cmd_report)
    p = sub.add_parser("track", help="is it proven yet? closed round trips vs the profile the research promised: --book B | --all")
    p.add_argument("--book")
    p.add_argument("--all", action="store_true", help="every open book that has a research profile (trend, gapfade)")
    p.add_argument("--trades", action="store_true", help="also list the closed round trips")
    p.add_argument("--notify", action="store_true", help="also push the scorecard to the phone / Telegram")
    p.set_defaults(fn=cmd_track)
    p = sub.add_parser("quote", help="latest close, change, liquidity, tick and band for CODE[,CODE]")
    p.add_argument("codes")
    p.set_defaults(fn=cmd_quote)
    p = sub.add_parser("crosscheck", help="per-stock endpoint vs idx.bar for a sample of codes")
    p.add_argument("--sample", type=int, default=60)
    p.add_argument("--codes")
    p.set_defaults(fn=cmd_crosscheck)
    p = sub.add_parser("feed", help="Stockbit datafeed collector: run [--no-raw] | status | symbols [--liquid N] [--set A,B] [--disable A,B] | token [--paste FILE|-] | audit [--date D] | replay --file F")
    p.add_argument("action", choices=["run", "status", "symbols", "token", "audit", "replay"])
    p.add_argument("--no-raw", action="store_true")
    p.add_argument("--file")
    p.add_argument("--liquid", type=int)
    p.add_argument("--set")
    p.add_argument("--disable")
    p.add_argument("--paste")
    p.add_argument("--date")
    p.set_defaults(fn=cmd_feed)
    sub.add_parser("run-scheduler", help="run the Asia/Jakarta job scheduler in the foreground").set_defaults(fn=cmd_run_scheduler)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure()
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
