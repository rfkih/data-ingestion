#!/usr/bin/env python3
"""Equity-expansion Phase 1 loader (blueprint 2026-07-18 s8b).

Fetches 25y of daily OHLC from the Yahoo v8 chart API for the US/SGX/Bursa
screen universe, back-adjusts OHLC by (adjclose/close) per bar (splits +
dividends), caches one CSV per symbol under /tmp/equity/, validates, and
inserts into market_data (interval='1d', symbol = Yahoo ticker unchanged,
ON CONFLICT DO NOTHING -- the ONLY write this script performs). Index tickers
(^STI, ^KLSE) are cached for screening but NEVER inserted.

Run ON THE VPS:  python3 equity_ohlc_loader.py --commit
Dry-run by default (fetch+cache+validate, no DB writes).
Writes /tmp/equity/manifest.json consumed by equity_screen.py.
Column mapping replicates research/gold_ohlc_loader.py (XAUUSD precedent):
crypto microstructure fields written 0 for non-crypto instruments.
"""
import argparse
import json
import os
import subprocess
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

OUTDIR = "/tmp/equity"
INTERVAL = "1d"
PSQL = ["docker", "exec", "-i", "blackheart-postgres",
        "psql", "-U", "postgres", "-d", "trading_db"]

US = ("SPY QQQ IWM DIA XLE XLF XLK XLV XLI XLP XLU XLY XLB XLRE XLC TLT IEF "
      "LQD HYG GLD SLV USO DBA DBC EEM EFA VNQ AAPL MSFT NVDA AMZN GOOGL "
      "JPM XOM").split()
SGX = ("ES3.SI D05.SI O39.SI U11.SI Z74.SI F34.SI S68.SI S63.SI C6L.SI "
       "A17U.SI C38U.SI BN4.SI").split()
BURSA = ("1155.KL 1023.KL 1295.KL 5347.KL 5225.KL 5183.KL 2445.KL 1961.KL "
         "5285.KL 6947.KL 4863.KL 3816.KL 4707.KL").split()
SCREEN_ONLY = [("^STI", "SGX"), ("^KLSE", "BURSA")]

UNIVERSE = ([(t, "US", True) for t in US]
            + [(t, "SGX", True) for t in SGX]
            + [(t, "BURSA", True) for t in BURSA]
            + [(t, m, False) for t, m in SCREEN_ONLY])


def yf_fetch(tk, adjust=True):
    """25y daily bars. adjust=True: OHLC back-adjusted by adjclose/close (splits
    + dividends, the SGX/Bursa precedent). adjust=False: Yahoo's own ``close``
    basis, which is split-adjusted only (verified: BBCA.JK 2021-10-12 close
    7,320 = 36,600/5 while adjclose 6,248 also strips dividends) — the basis
    the IDX primary feed uses, so the two can be spliced. Returns
    (rows, n_null, n_bad, n_adj); rows = [(iso_date, o, h, l, c, v), ...]."""
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           + urllib.parse.quote(tk) + "?interval=1d&range=25y")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=40) as r:
        d = json.load(r)
    res = d["chart"]["result"][0]
    ts = res["timestamp"]
    q = res["indicators"]["quote"][0]
    adj = None
    try:
        adj = res["indicators"]["adjclose"][0]["adjclose"]
    except (KeyError, IndexError, TypeError):
        pass
    seen = {}
    n_null = n_bad = n_adj = 0
    vol = q.get("volume") or [None] * len(ts)
    for i, epoch in enumerate(ts):
        o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        if None in (o, h, l, c):
            n_null += 1
            continue
        if min(o, h, l, c) <= 0:
            n_bad += 1
            continue
        f = 1.0
        if adjust and adj is not None and i < len(adj) and adj[i] is not None and adj[i] > 0:
            f = adj[i] / c
            n_adj += 1
        elif not adjust:
            n_adj += 1
        day = datetime.fromtimestamp(epoch, tz=timezone.utc).date().isoformat()
        seen[day] = (day, o * f, h * f, l * f, c * f, int(vol[i] or 0))
    rows = [seen[k] for k in sorted(seen)]
    return rows, n_null, n_bad, n_adj


def insert_symbol(tk, rows):
    """INSERT ... ON CONFLICT DO NOTHING into market_data. Returns (n, err)."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    cols = ("symbol,interval,start_time,end_time,open_price,close_price,"
            "high_price,low_price,volume,trade_count,quote_asset_volume,"
            "taker_buy_base_volume,taker_buy_quote_volume,created_time")
    vals = ",".join(
        "('%s','%s','%s 00:00:00','%s 23:59:59.999',%.10g,%.10g,%.10g,%.10g,"
        "%d,0,0,0,0,'%s')" % (tk, INTERVAL, d, d, o, c, h, l, v, now)
        for d, o, h, l, c, v in rows)
    sql = ("INSERT INTO market_data (%s) VALUES %s "
           "ON CONFLICT (symbol,interval,start_time) DO NOTHING;" % (cols, vals))
    out = subprocess.run(PSQL, input=sql, capture_output=True, text=True)
    txt = (out.stdout or "") + (out.stderr or "")
    for ln in txt.splitlines():
        if ln.startswith("INSERT"):
            return int(ln.split()[-1]), ""
    return 0, txt.strip()[:200]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true",
                    help="insert into market_data (default = dry-run)")
    a = ap.parse_args()
    os.makedirs(OUTDIR, exist_ok=True)
    manifest = {}
    for tk, market, do_insert in UNIVERSE:
        rows = None
        err = ""
        for attempt in range(3):          # retry each failed symbol twice
            try:
                rows, n_null, n_bad, n_adj = yf_fetch(tk)
                break
            except Exception as e:
                err = str(e)[:120]
                time.sleep(5)
        time.sleep(2)                      # be polite to Yahoo
        if rows is None:
            manifest[tk] = {"market": market, "bars": 0, "inserted": 0,
                            "screen_only": not do_insert,
                            "notes": ["FETCH_FAILED: " + err]}
            print("%-8s %-5s FETCH FAILED after 3 tries: %s" % (tk, market, err))
            continue
        notes = []
        if n_null:
            notes.append("null_ohlc_dropped=%d" % n_null)
        if n_bad:
            notes.append("nonpos_price_dropped=%d" % n_bad)
        if n_adj < len(rows):
            notes.append("adjclose_missing=%d" % (len(rows) - n_adj))
        bars = len(rows)
        if bars < 750:
            notes.append("TOO_SHORT(<750): excluded from insert+screen")
        elif bars < 2000:
            notes.append("short_history(<2000): kept")
        fn = os.path.join(OUTDIR, tk.replace("^", "_") + ".csv")
        with open(fn, "w") as f:
            f.write("date,open,high,low,close,volume\n")
            for d, o, h, l, c, v in rows:
                f.write("%s,%.10g,%.10g,%.10g,%.10g,%d\n" % (d, o, h, l, c, v))
        ins = 0
        if do_insert and a.commit and bars >= 750:
            ins, ierr = insert_symbol(tk, rows)
            if ierr:
                notes.append("INSERT_ERR: " + ierr)
        manifest[tk] = {"market": market, "bars": bars, "first": rows[0][0],
                        "last": rows[-1][0], "inserted": ins,
                        "screen_only": not do_insert, "notes": notes}
        tag = "screen-only" if not do_insert else ("" if a.commit else "dry-run")
        print("%-8s %-5s bars=%5d %s..%s inserted=%5d %s"
              % (tk, market, bars, rows[0][0], rows[-1][0], ins,
                 ";".join(notes) or tag))
    with open(os.path.join(OUTDIR, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1)
    for m in ("US", "SGX", "BURSA"):
        ss = [v for v in manifest.values()
              if v["market"] == m and not v["screen_only"]]
        ok = sum(1 for s in ss if s["bars"] >= 750)
        print("SUMMARY %s: %d/%d symbols ok, rows_inserted=%d"
              % (m, ok, len(ss), sum(s["inserted"] for s in ss)))


if __name__ == "__main__":
    main()
