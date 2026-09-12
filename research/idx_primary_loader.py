#!/usr/bin/env python3
"""IDX PRIMARY-SOURCE daily loader — idx.co.id, not Yahoo.

Two endpoints behind the public site (both JSON, Cloudflare-fronted):
  universe : /primary/StockData/GetSecuritiesStock   (Daftar Saham — every listed
             stock: Code, Name, ListingDate, Shares, ListingBoard)
  history  : /primary/ListedCompany/GetTradingInfoSS?code=X&start=0&length=N
             (per-stock daily Ringkasan Saham rows: Previous, Open, High, Low,
             Close, Volume, Value, Frequency, Bid/Offer(+vol), ListedShares,
             TradebleShares, ForeignBuy/Sell, NonRegular*, Remarks)

★ Depth: the site serves 2020-01-02 onward ONLY (every earlier date returns 0
rows) — ~6.7y. Pre-2020 is not published freely by IDX (vendor/paid).
★ Prices are RAW (as traded). Corporate actions are recovered from IDX's own
`Previous` reference price: on an ex-date IDX resets Previous to the theoretical
price, so factor = Previous(t)/Close(t-1) != 1 marks a split/reverse/bonus/
rights event. adj_* columns back-multiply those factors (cash dividends are NOT
adjusted — IDX does not reset Previous for them).

Layout (research-scratch/idx-primary/, gitignored):
  daftar_saham.json / .csv     universe snapshot
  raw/<CODE>.json.gz           verbatim endpoint response (provenance)
  <CODE>.csv                   flat daily rows + adj_* + adj_factor
  manifest.json                per-code rows/first/last/events/gaps/errors

Usage:
  python research/idx_primary_loader.py                  # all listed stocks (resumable)
  python research/idx_primary_loader.py --codes BBCA,BBRI
  python research/idx_primary_loader.py --board Utama
  python research/idx_primary_loader.py --refresh        # re-fetch cached codes too
"""
import argparse
import csv
import gzip
import http.cookiejar
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUTDIR = os.path.join(ROOT, "research-scratch", "idx-primary")
BASE = "https://www.idx.co.id"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
SLEEP = 1.0                     # politeness between requests
BACKOFF = (5, 10, 20, 40, 80)   # Cloudflare 403 / 5xx / non-JSON
ADJ_TOL = 0.005                 # |Previous/prevClose - 1| above this = corporate action
MAX_GAP_DAYS = 20

# Pulled first so the screen universe lands early; the rest of the market follows.
PRIORITY = ("BBCA BBRI BMRI BBNI BRIS TLKM ISAT EXCL TOWR TBIG JSMR UNVR ICBP INDF "
            "KLBF GGRM HMSP AMRT CPIN MYOR SIDO ASII UNTR ANTM PTBA ADRO INCO MDKA "
            "ITMG INTP SMGR TPIA BRPT PGAS MEDC AKRA BSDE CTRA PWON MAPI ACES MIKA "
            "GOTO").split()

FIELDS = [("Date", "date"), ("Previous", "previous"), ("OpenPrice", "open"),
          ("FirstTrade", "first_trade"), ("High", "high"), ("Low", "low"), ("Close", "close"), ("Volume", "volume"),
          ("Value", "value"), ("Frequency", "frequency"), ("Bid", "bid"),
          ("BidVolume", "bid_volume"), ("Offer", "offer"), ("OfferVolume", "offer_volume"),
          ("ListedShares", "listed_shares"), ("TradebleShares", "tradeable_shares"),
          ("ForeignBuy", "foreign_buy"), ("ForeignSell", "foreign_sell"),
          ("NonRegularVolume", "nonreg_volume"), ("NonRegularValue", "nonreg_value"),
          ("NonRegularFrequency", "nonreg_frequency"), ("Remarks", "remarks")]

_jar = http.cookiejar.CookieJar()
_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_jar))


def get_json(path, referer):
    """GET with browser headers; retries Cloudflare challenges with backoff."""
    req = urllib.request.Request(BASE + path, headers={
        "User-Agent": UA, "Referer": referer, "Accept": "application/json, text/plain, */*",
        "Accept-Language": "id-ID,id;q=0.9,en;q=0.8"})
    last = ""
    for i, wait in enumerate((0,) + BACKOFF):
        if wait:
            time.sleep(wait)
        try:
            with _opener.open(req, timeout=60) as r:
                body = r.read()
            return json.loads(body), body
        except urllib.error.HTTPError as e:
            last = "HTTP %d" % e.code
        except Exception as e:                       # non-JSON challenge page, timeouts
            last = type(e).__name__ + ": " + str(e)[:80]
    raise RuntimeError(last)


def fetch_universe(outdir):
    d, body = get_json("/primary/StockData/GetSecuritiesStock?start=0&length=9999"
                       "&code=&sector=&board=&language=id-id",
                       BASE + "/id/data-pasar/data-saham/daftar-saham/")
    rows = d["data"]
    with open(os.path.join(outdir, "daftar_saham.json"), "wb") as f:
        f.write(body)
    with open(os.path.join(outdir, "daftar_saham.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["code", "name", "listing_date", "shares", "board"])
        for r in rows:
            w.writerow([r["Code"], r["Name"], (r.get("ListingDate") or "")[:10],
                        int(r.get("Shares") or 0), r.get("ListingBoard")])
    return rows


def fetch_history(code):
    d, body = get_json("/primary/ListedCompany/GetTradingInfoSS?code=%s&start=0&length=10000"
                       % urllib.parse.quote(code),
                       BASE + "/id/perusahaan-tercatat/profil-perusahaan-tercatat/%s" % code)
    return d.get("replies") or [], body


def to_rows(replies):
    """Ascending, deduped by date, phantom rows removed, split factors from
    IDX's Previous. Also fills OpenPrice from FirstTrade where IDX recorded 0
    (no pre-opening session 2020-03-13..2020-09-04)."""
    notes = []
    seen = {}
    for r in replies:
        seen[r["Date"][:10]] = r
    out = [seen[k] for k in sorted(seen)]
    wk = [r for r in out if date.fromisoformat(r["Date"][:10]).weekday() >= 5]
    if wk:                                   # IDX never trades Sat/Sun: feed artefacts
        notes.append("weekend_rows_dropped=%d(%s)" % (len(wk), ",".join(r["Date"][:10] for r in wk[:3])))
        out = [r for r in out if r not in wk]
    # chain check: Previous(i+1) must equal Close(i) unless a corporate action;
    # a row whose removal RESTORES the chain is a phantom print.
    phantom = []
    i = 1
    while i < len(out) - 1:
        c_prev, c_i, p_next = out[i - 1].get("Close"), out[i].get("Close"), out[i + 1].get("Previous")
        if c_prev and c_i and p_next and p_next != c_i and p_next == c_prev:
            phantom.append(out[i]["Date"][:10])
            del out[i]
            continue
        i += 1
    if phantom:
        notes.append("phantom_rows_dropped=%d(%s)" % (len(phantom), ",".join(phantom[:3])))
    nopen = 0
    for r in out:
        if not r.get("OpenPrice") and r.get("FirstTrade"):
            r["OpenPrice"] = r["FirstTrade"]
            nopen += 1
    if nopen:
        notes.append("open_from_first_trade=%d" % nopen)
    missing = sum(1 for r in out if not r.get("OpenPrice"))
    if missing:                              # IDX recorded no open (2020-03-13..09-04): keep NULL
        notes.append("open_missing=%d" % missing)
    n = len(out)
    factor = [1.0] * n
    events = []
    for i in range(1, n):
        prev_close, ref = out[i - 1].get("Close") or 0, out[i].get("Previous") or 0
        if prev_close > 0 and ref > 0:
            ratio = ref / prev_close
            if abs(ratio - 1) > ADJ_TOL:
                factor[i] = ratio
                events.append({"date": out[i]["Date"][:10], "factor": round(ratio, 6),
                               "listed_shares_before": out[i - 1].get("ListedShares"),
                               "listed_shares_after": out[i].get("ListedShares"),
                               "remarks": out[i].get("Remarks")})
    # back-multiply: bar s is scaled by every factor after it
    cum = [1.0] * n
    acc = 1.0
    for i in range(n - 1, -1, -1):
        cum[i] = acc
        acc *= factor[i]
    return out, cum, events, notes


def write_csv(path, rows, cum):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([c for _, c in FIELDS] + ["adj_open", "adj_high", "adj_low",
                                             "adj_close", "adj_factor"])
        for r, k in zip(rows, cum):
            vals = []
            for src, _ in FIELDS:
                v = r.get(src)
                if src == "Date":
                    v = (v or "")[:10]
                elif src in ("OpenPrice", "FirstTrade") and not v:
                    v = None
                elif isinstance(v, float) and v.is_integer():
                    v = int(v)
                vals.append(v if v is not None else "")
            adj = [("%.6g" % ((r.get(c) or 0) * k)) if r.get(c) else ""
                   for c in ("OpenPrice", "High", "Low", "Close")]
            w.writerow(vals + adj + ["%.8g" % k])


def validate(rows):
    notes = []
    bad = 0
    for r in rows:
        oc = [x for x in (r.get("OpenPrice"), r.get("Close")) if x]
        if oc and ((r.get("High") or 0) < max(oc) or (r.get("Low") or 0) > min(oc)):
            bad += 1
    if bad:
        notes.append("ohlc_inconsistent=%d" % bad)
    zero = sum(1 for r in rows if not r.get("Close"))
    if zero:
        notes.append("zero_close=%d" % zero)
    notrade = sum(1 for r in rows if not r.get("Volume"))
    if notrade:
        notes.append("no_trade_days=%d" % notrade)
    gap, gap_at = 0, ""
    for a, b in zip(rows, rows[1:]):
        dd = (date.fromisoformat(b["Date"][:10]) - date.fromisoformat(a["Date"][:10])).days
        if dd > gap:
            gap, gap_at = dd, b["Date"][:10]
    if gap > MAX_GAP_DAYS:
        notes.append("HISTORY_GAP=%dd(before %s)" % (gap, gap_at))
    return notes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default=DEFAULT_OUTDIR)
    ap.add_argument("--codes", help="comma list; default = every listed stock")
    ap.add_argument("--board", help="filter Daftar Saham by ListingBoard (e.g. Utama)")
    ap.add_argument("--refresh", action="store_true", help="re-fetch codes already cached")
    a = ap.parse_args()
    os.makedirs(os.path.join(a.outdir, "raw"), exist_ok=True)

    universe = fetch_universe(a.outdir)
    info = {r["Code"]: r for r in universe}
    print("universe: %d listed stocks (Daftar Saham)" % len(universe), flush=True)
    if a.codes:
        codes = [c.strip().upper() for c in a.codes.split(",") if c.strip()]
    else:
        codes = [r["Code"] for r in universe
                 if not a.board or r.get("ListingBoard") == a.board]
    codes = [c for c in PRIORITY if c in codes] + [c for c in codes if c not in PRIORITY]

    mpath = os.path.join(a.outdir, "manifest.json")
    manifest = json.load(open(mpath)) if os.path.exists(mpath) else {}
    t0 = time.time()
    for n, code in enumerate(codes, 1):
        csv_path = os.path.join(a.outdir, code + ".csv")
        if not a.refresh and code in manifest and os.path.exists(csv_path) \
                and not manifest[code].get("error"):
            continue
        meta = info.get(code, {})
        try:
            replies, body = fetch_history(code)
        except Exception as e:
            manifest[code] = {"error": str(e)[:160], "board": meta.get("ListingBoard")}
            print("%4d/%d %-6s FETCH FAILED %s" % (n, len(codes), code, str(e)[:80]), flush=True)
            time.sleep(SLEEP)
            continue
        with gzip.open(os.path.join(a.outdir, "raw", code + ".json.gz"), "wb") as f:
            f.write(body)
        rows, cum, events, cnotes = to_rows(replies)
        entry = {"name": meta.get("Name"), "board": meta.get("ListingBoard"),
                 "listing_date": (meta.get("ListingDate") or "")[:10],
                 "rows": len(rows), "first": rows[0]["Date"][:10] if rows else None,
                 "last": rows[-1]["Date"][:10] if rows else None,
                 "adj_events": events,
                 "notes": (cnotes + validate(rows)) if rows else ["EMPTY"]}
        if rows:
            write_csv(csv_path, rows, cum)
        manifest[code] = entry
        print("%4d/%d %-6s rows=%4d %s..%s adj=%d %s" % (
            n, len(codes), code, len(rows), entry["first"], entry["last"],
            len(events), ";".join(entry["notes"])), flush=True)
        if n % 25 == 0:
            with open(mpath, "w") as f:
                json.dump(manifest, f, indent=1)
        time.sleep(SLEEP)
    with open(mpath, "w") as f:
        json.dump(manifest, f, indent=1)
    done = [c for c in codes if c in manifest and not manifest[c].get("error")]
    errs = [c for c in codes if manifest.get(c, {}).get("error")]
    print("SUMMARY IDX-PRIMARY: %d/%d codes ok, %d failed %s, rows=%d, %.0fs, outdir=%s" % (
        len(done), len(codes), len(errs), errs[:10],
        sum(manifest[c]["rows"] for c in done), time.time() - t0, a.outdir), flush=True)


if __name__ == "__main__":
    sys.exit(main())
