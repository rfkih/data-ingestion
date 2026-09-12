#!/usr/bin/env python3
"""
Phase-1 gold daily OHLC loader (non-crypto research sleeve, 2026-07-15).

Fetches COMEX gold (GC=F) daily bars from Yahoo Finance and maps them to the
crypto-shaped `market_data` row (symbol=XAUUSD, interval=1d). Yahoo is the source
because Stooq is now behind a JS proof-of-work anti-bot wall (verified dead
2026-07-15). Gold history goes back to ~2000-08.

DRY-RUN BY DEFAULT — prints coverage + sample rows, writes nothing. Pass --commit
to insert (idempotent, ON CONFLICT DO NOTHING). ⚠ --commit is GATED on the
operator's "where does non-crypto market_data live?" decision (see
research/PHASE1_GOLD_BUILD_PLAN_2026-07-15.md, Decision 1). Do NOT --commit to
prod market_data without that call.

Run ON THE VPS (needs DB access + real python3):
    python3 gold_ohlc_loader.py                 # dry-run
    python3 gold_ohlc_loader.py --commit         # insert (gated)

market_data columns are ALL NOT NULL; the crypto microstructure fields
(trade_count / quote_asset_volume / taker_buy_*) are written 0 for a non-crypto
instrument (price-only engines — DCB/trend/momentum — never read them).
"""
import argparse
import json
import subprocess
import urllib.request
from datetime import datetime, timezone

SYMBOL = "XAUUSD"
YF_TICKER = "GC=F"
INTERVAL = "1d"
YF_URL = ("https://query1.finance.yahoo.com/v8/finance/chart/"
          + urllib.parse.quote(YF_TICKER) + "?interval=1d&range=25y")
PSQL = ["docker", "exec", "-i", "blackheart-postgres",
        "psql", "-U", "postgres", "-d", "trading_db"]


def fetch():
    req = urllib.request.Request(YF_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=40) as r:
        d = json.load(r)
    res = d["chart"]["result"][0]
    ts = res["timestamp"]
    q = res["indicators"]["quote"][0]
    rows = []
    for i, epoch in enumerate(ts):
        o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        v = q.get("volume", [None] * len(ts))[i]
        if None in (o, h, l, c):
            continue  # Yahoo emits null OHLC on non-trading days — skip
        day = datetime.fromtimestamp(epoch, tz=timezone.utc).date()
        rows.append({
            "start": "%s 00:00:00" % day, "end": "%s 23:59:59.999" % day,
            "o": o, "h": h, "l": l, "c": c, "v": v or 0,
        })
    return rows


def to_values_sql(rows):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    parts = []
    for r in rows:
        parts.append(
            "('%s','%s','%s','%s',%f,%f,%f,%f,%f,0,0,0,0,'%s')"
            % (SYMBOL, INTERVAL, r["start"], r["end"],
               r["o"], r["c"], r["h"], r["l"], r["v"], now))
    return ",".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true",
                    help="insert into market_data (GATED — see build plan Decision 1)")
    args = ap.parse_args()

    rows = fetch()
    print("fetched %d gold daily bars: %s -> %s"
          % (len(rows), rows[0]["start"][:10], rows[-1]["start"][:10]))
    print("sample (latest 3):")
    for r in rows[-3:]:
        print("  %s O=%.2f H=%.2f L=%.2f C=%.2f V=%s"
              % (r["start"][:10], r["o"], r["h"], r["l"], r["c"], r["v"]))

    if not args.commit:
        print("\nDRY-RUN — nothing written. Pass --commit to insert (operator-gated).")
        return

    cols = ("symbol,interval,start_time,end_time,open_price,close_price,high_price,"
            "low_price,volume,trade_count,quote_asset_volume,taker_buy_base_volume,"
            "taker_buy_quote_volume,created_time")
    sql = ("INSERT INTO market_data (%s) VALUES %s "
           "ON CONFLICT (symbol,interval,start_time) DO NOTHING;"
           % (cols, to_values_sql(rows)))
    # Pipe the multi-row INSERT via stdin — 6k rows as a -c arg blows past ARG_MAX.
    out = subprocess.run(PSQL, input=sql, capture_output=True, text=True)
    print("COMMIT:", out.stdout.strip() or out.stderr.strip())


if __name__ == "__main__":
    main()
