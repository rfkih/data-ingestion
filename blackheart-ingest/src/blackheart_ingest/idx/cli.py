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
  run-scheduler                                foreground APScheduler (Asia/Jakarta), see scheduler.py

DB comes from the INGEST_* settings (INGEST_DB_DSN or INGEST_DB_HOST/...).
"""
from __future__ import annotations

import argparse
import json
import logging
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


def cmd_macro(a: argparse.Namespace) -> int:
    from . import macro
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
                                        ("cash_floor_pct", a.cash_floor), ("stress_cash_pct", a.stress_cash), ("stress_rule", a.stress_rule)) if v is not None}
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
        elif a.sub in ("issue", "close", "cancel"):
            t = ticket.load(conn, a.id, None if a.id else a.book)
            if not t:
                print("no ticket")
                return 1
            ticket.set_status(conn, t["id"], {"issue": "issued", "close": "closed", "cancel": "cancelled"}[a.sub])
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


def cmd_crosscheck(a: argparse.Namespace) -> int:
    codes = [c.strip().upper() for c in a.codes.split(",")] if a.codes else None
    with get_connection() as conn, IdxClient() as cl:
        r = job_crosscheck.run(conn, cl, sample=a.sample, codes=codes)
    _report(r)
    for w in r.warnings:
        print(f"    {w}")
    return 0 if r.status == "ok" else 1


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
    p = sub.add_parser("macro", help="macro series: pull [--keys a,b] [--full] | show")
    p.add_argument("sub", choices=["pull", "show"])
    p.add_argument("--keys", help="comma list of series keys (default all)")
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
    p.add_argument("sub", choices=["show", "fills", "fill", "cash", "set", "import", "mark", "check", "paper-seed"])
    p.add_argument("--book", default="live")
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
    p.add_argument("sub", choices=["build", "show", "issue", "close", "cancel", "fill", "skip", "paper-fill"])
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
    p = sub.add_parser("crosscheck", help="per-stock endpoint vs idx.bar for a sample of codes")
    p.add_argument("--sample", type=int, default=60)
    p.add_argument("--codes")
    p.set_defaults(fn=cmd_crosscheck)
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
