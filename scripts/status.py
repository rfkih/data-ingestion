#!/usr/bin/env python3
"""
Blackridge desk status in one command.

    python scripts/status.py            # the whole digest, one screen
    python scripts/status.py books      # only that block (books|strategies|health|feed|chain|tickets)
    python scripts/status.py --json     # the same facts as JSON, for a script

Written for cheap answers: one run, one screen, no JSON to wade through and no guessing at endpoint
shapes. If you are an agent being asked "what is running / is the desk healthy / which strategies
are active", run this FIRST rather than curling the worker.

Reads only. Never writes, never trades. Stdlib only - no install, no venv.
"""

from __future__ import annotations

import json
import socket
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

INGEST = "http://127.0.0.1:8001"

# The Windows console is cp1252 by default and turns every "." separator into a replacement mark.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass
WIB = timezone(timedelta(hours=7))

# Ports that actually matter locally. Postgres is the `blackheart-postgres-local` container, which
# publishes 5432 on 5433 - probing 5432 reports a false DOWN while the worker is plainly reading it.
PORTS = [
    ("ingest", 8001),
    ("web", 3010),
    ("proxy", 3012),
    ("postgres", 5433),
    ("trading-jvm", 8080),
]

# ANSI is off when the output is piped, so a log file stays readable.
_TTY = sys.stdout.isatty()


def c(s: str, code: str) -> str:
    return f"\033[{code}m{s}\033[0m" if _TTY else s


def dim(s: str) -> str:
    return c(s, "2")


def bold(s: str) -> str:
    return c(s, "1")


def red(s: str) -> str:
    return c(s, "31")


def green(s: str) -> str:
    return c(s, "32")


def amber(s: str) -> str:
    return c(s, "33")


def get(path: str, timeout: float = 6.0):
    """GET a worker endpoint. Returns None rather than raising: a dead worker is a finding."""
    try:
        with urllib.request.urlopen(f"{INGEST}{path}", timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, socket.timeout, ValueError, OSError):
        return None


def port_up(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket() as s:
        s.settimeout(0.6)
        return s.connect_ex((host, port)) == 0


def rp(v, digits: int = 1) -> str:
    """Rupiah, short. Accepts the worker's decimal strings."""
    try:
        n = float(v)
    except (TypeError, ValueError):
        return "-"
    a = abs(n)
    sign = "-" if n < 0 else ""
    if a >= 1e12:
        return f"{sign}Rp {a / 1e12:.2f}T"
    if a >= 1e9:
        return f"{sign}Rp {a / 1e9:.1f}bn"
    if a >= 1e6:
        return f"{sign}Rp {a / 1e6:.{digits}f}M"
    if a >= 1e3:
        return f"{sign}Rp {a / 1e3:.0f}K"
    return f"{sign}Rp {a:.0f}"


def pc(v) -> str:
    try:
        n = float(v) * 100
    except (TypeError, ValueError):
        return ""
    return f"{'+' if n > 0 else ''}{n:.1f}%"


def day(iso) -> str:
    if not iso:
        return "-"
    return str(iso)[:10]


def collect() -> dict:
    """Every fact this tool prints, gathered in one pass."""
    books = get("/idx/books") or []
    live = [b for b in books if b.get("kind") == "live"]
    paper = [b for b in books if b.get("kind") != "live"]

    detail = {}
    for b in live:
        d = get(f"/idx/book/{b['book']}")
        if d:
            detail[b["book"]] = d

    cat = get("/idx/strategies") or {}
    strategies = cat.get("strategies", cat if isinstance(cat, list) else [])

    ops = get("/idx/ops") or {}
    overlay = get("/idx/overlay") or {}
    idx_series = get("/idx/index?codes=COMPOSITE")
    feed = get("/idx/feed/status") or {}

    composite = None
    rows = idx_series if isinstance(idx_series, list) else None
    if isinstance(idx_series, dict):
        rows = idx_series.get("series") or idx_series.get("rows")
        if isinstance(rows, dict):
            rows = next(iter(rows.values()), None)
    if rows:
        composite = rows[-1]

    tickets = {}
    for b in live:
        t = get(f"/idx/ticket?book={b['book']}")
        if t and t.get("id"):
            tickets[b["book"]] = t

    return {
        "at": datetime.now(WIB).strftime("%Y-%m-%d %H:%M WIB"),
        "ports": {name: port_up(p) for name, p in PORTS},
        "live": live,
        "paper": paper,
        "detail": detail,
        "strategies": strategies,
        "ops": ops,
        "overlay": overlay,
        "composite": composite,
        "feed": feed,
        "tickets": tickets,
    }


def block_health(s: dict) -> list[str]:
    out = [bold("HEALTH")]
    parts = []
    for name, up in s["ports"].items():
        parts.append(f"{name} {green('up') if up else red('DOWN')}")
    out.append("  " + " · ".join(parts))
    ops = s["ops"]
    if not ops:
        out.append("  " + red("the ingest worker did not answer - start it with scripts/idx.sh"))
        return out
    alerts = ops.get("open_alerts") or ops.get("openAlerts") or []
    crit = sum(1 for a in alerts if a.get("severity") == "critical")
    warn = sum(1 for a in alerts if a.get("severity") == "warning")
    tone = red if crit else (amber if warn else green)
    out.append(
        f"  last close {day(ops.get('last_bar_date') or ops.get('lastBarDate'))}"
        + (
            f" · COMPOSITE {float(s['composite']['close']):,.0f} ({day(s['composite']['trade_date'])})"
            if s["composite"]
            else ""
        )
    )
    out.append(f"  alerts {tone(str(len(alerts)))} open ({crit} critical, {warn} warning)")
    for a in alerts[:3]:
        out.append(dim(f"    - {str(a.get('message'))[:96]}"))
    if len(alerts) > 3:
        out.append(dim(f"    … {len(alerts) - 3} more"))
    return out


def block_chain(s: dict) -> list[str]:
    ops = s["ops"]
    runs = (ops or {}).get("runs") or []
    out = [bold("CHAIN") + dim("  last runs")]
    if not runs:
        out.append("  " + amber("no run in the last two days - is the scheduler task running?"))
        return out
    seen = set()
    for r in runs:
        job = r.get("job")
        if job in seen:
            continue
        seen.add(job)
        st = r.get("status", "?")
        tone = green if st == "ok" else (amber if st in ("partial", "running") else red)
        when = str(r.get("started_at") or r.get("startedAt") or "")[:16].replace("T", " ")
        out.append(f"  {str(job):<16} {tone(st):<20} {dim(when)}")
        if len(seen) >= 8:
            break
    return out


def block_books(s: dict) -> list[str]:
    out = [bold("BOOKS") + dim(f"  {len(s['live'])} real, {len(s['paper'])} paper (hidden in the app)")]
    ops = s["ops"] or {}
    last_close = day(ops.get("last_bar_date") or ops.get("lastBarDate"))
    if not s["live"]:
        out.append("  " + amber("no live book on this worker"))
    for b in s["live"]:
        d = s["detail"].get(b["book"], {})
        bk = d.get("book", {})
        flags = [k for k in ("regime_filter", "entry_gate", "trend_exit") if bk.get(k)]
        rule = b.get("rule", "?")
        if b.get("trend_variant"):
            rule = f"{rule}:{b['trend_variant']}"
        out.append(
            f"  {bold(b['book']):<28} {str(b.get('label')):<18} {rule:<12} "
            f"{rp(b.get('nav_now')):>10}  {b.get('positions', 0)} pos  "
            f"cash {rp(bk.get('cash') or b.get('cash'))}"
            + (f"  {green('overlay:' + ','.join(flags))}" if flags else "")
            + (f"  {red('HALTED')}" if b.get("halted") else "")
        )
        # A mark behind the last close, or a held name with no price in it, means the figures above
        # are stale - this is exactly how an unmarked IRSX made a book read -10 % when it was +1.5 %.
        nav = d.get("nav") or []
        marked = day(nav[-1].get("trade_date") or nav[-1].get("tradeDate")) if nav else None
        unpriced = [p["code"] for p in (d.get("positions") or []) if p.get("close") is None]
        if marked and last_close != "-" and marked < last_close:
            out.append(
                "      "
                + amber(f"STALE: last marked {marked}, last close {last_close}")
                + dim("  -> idx book mark --book " + b["book"])
            )
        if unpriced:
            out.append(
                "      "
                + amber(f"no price in the mark: {', '.join(unpriced)}")
                + dim("  -> the value, weight and P&L above exclude them")
            )
        # The last NAV row should equal the live NAV. When a fill lands after a mark has run, the
        # mark only moves forward and the older rows keep the pre-fill cash, so the series and the
        # live figure drift apart - a rebuild is the only thing that fixes the older rows.
        try:
            live_nav = float(d.get("nav_now") or d.get("navNow") or b.get("nav_now"))
            row_nav = float(nav[-1]["nav"]) if nav else None
        except (TypeError, ValueError, KeyError):
            live_nav = row_nav = None
        if live_nav and row_nav and abs(live_nav - row_nav) > max(1000.0, live_nav * 0.001):
            out.append(
                "      "
                + amber(f"series disagrees with live NAV: last row {rp(row_nav)} vs {rp(live_nav)}")
                + dim("  -> idx book mark --book " + b["book"] + " --rebuild")
            )
        for p in d.get("positions", []) or []:
            last = p.get("close")
            pnl = pc(p.get("pnl_pct"))
            tone = green if pnl.startswith("+") else (red if pnl.startswith("-") else dim)
            out.append(
                dim(f"      {p['code']:<6} {float(p['lots']):.0f} lots @ {float(p['avg_price']):,.0f}  ")
                + (f"last {float(last):,.0f} {tone(pnl)}" if last is not None else amber("no mark yet"))
            )
    if s["paper"]:
        out.append(
            dim(
                "  paper (research only): "
                + ", ".join(f"{b['book']} {rp(b.get('nav_now'))}" for b in s["paper"])
            )
        )
    return out


def block_strategies(s: dict) -> list[str]:
    out = [bold("STRATEGIES")]
    by = {}
    for x in s["strategies"]:
        by.setdefault(x.get("status", "?"), []).append(x)
    # what the books actually follow, which is the question people mean by "active"
    following = {}
    for b in s["live"]:
        key = b.get("strategy")
        if key:
            following.setdefault(key, []).append(b["book"])
    for st in ("deployed", "baseline", "candidate", "option", "experimental", "tested", "superseded", "reference"):
        rows = by.get(st)
        if not rows:
            continue
        tone = green if st == "deployed" else (amber if st == "experimental" else dim)
        names = []
        for x in rows:
            k = x["key"]
            names.append(f"{k}{green('*') if k in following else ''}")
        out.append(f"  {tone(st):<22} " + ", ".join(names))
    if following:
        out.append(
            dim("  * = a live book follows it: ")
            + ", ".join(f"{k} <- {', '.join(v)}" for k, v in following.items())
        )
    ov = s["overlay"]
    if ov:
        n = len(ov.get("history") or [])
        if n == 0:
            out.append(
                dim("  overlay: ")
                + amber("no monthly regime check recorded")
                + dim(" (the trend gate still computes live from the COMPOSITE series)")
            )
        else:
            latest = ov.get("latest") or {}
            out.append(
                dim(f"  overlay: last check {day(latest.get('check_date'))} - ")
                + (green("invested") if latest.get("on") else amber("in cash"))
            )
    return out


def block_tickets(s: dict) -> list[str]:
    out = [bold("TICKETS")]
    if not s["tickets"]:
        out.append("  " + dim("none open"))
        return out
    for book, t in s["tickets"].items():
        lines = t.get("lines") or []
        done = sum(1 for x in lines if x.get("status") in ("filled", "skipped"))
        st = t.get("status")
        tone = amber if st in ("draft", "issued") else dim
        out.append(f"  {book:<18} #{t.get('id')} {t.get('mode')} {tone(str(st))}  {done}/{len(lines)} lines done")
        for x in lines:
            if x.get("status") in ("open", "partial"):
                out.append(dim(f"      {x['side']:<4} {x['code']:<6} {float(x['lots']):.0f} lots @ {float(x['limit_price']):,.0f}"))
    return out


def block_feed(s: dict) -> list[str]:
    f = s["feed"] or {}
    col = f.get("collector") or {}
    tok = f.get("token") or {}
    ref = f.get("refresh") or {}
    out = [bold("FEED") + dim("  the Stockbit tick session")]
    if not f:
        out.append("  " + dim("no feed endpoint answered"))
        return out
    state = col.get("state", "?")
    stale = col.get("stale_s")
    out.append(
        f"  collector {green(state) if state == 'live' else amber(state)}"
        + (f" · last frame {int(stale)}s ago" if stale is not None else "")
        + f" · {f.get('symbols_enabled', '?')} names"
        + f" · {(f.get('today') or {}).get('trades', '?')} prints today"
    )
    hrs = tok.get("minutes_left")
    days = ref.get("days_left")
    out.append(
        "  session token "
        + (green(f"{int(hrs) // 60}h left") if tok.get("valid") and hrs else red("expired"))
        + " · refresh "
        + (
            (green if (days or 0) >= 2 else amber)(f"{int(days)}d left")
            if ref.get("present") and days is not None
            else red("absent - paste the cookie again")
        )
    )
    return out


BLOCKS = {
    "health": block_health,
    "chain": block_chain,
    "books": block_books,
    "strategies": block_strategies,
    "tickets": block_tickets,
    "feed": block_feed,
}


def main() -> int:
    args = [a for a in sys.argv[1:]]
    as_json = "--json" in args
    wanted = [a for a in args if not a.startswith("-")]

    s = collect()
    if as_json:
        print(json.dumps(s, indent=1, default=str))
        return 0

    print(bold(f"BLACKRIDGE  {s['at']}"))
    for name, fn in BLOCKS.items():
        if wanted and name not in wanted:
            continue
        print()
        for line in fn(s):
            print(line)
    if not s["ops"] and not s["live"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
