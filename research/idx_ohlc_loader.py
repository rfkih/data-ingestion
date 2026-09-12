#!/usr/bin/env python3
"""IDX (Bursa Efek Indonesia) daily OHLC loader — phase-6 screen universe.

Same pipeline as research/equity_ohlc_loader.py (US/SGX/Bursa precedent): 25y of
daily bars from the Yahoo v8 chart API — on the SPLIT-ONLY basis (Yahoo's ``close``
field, ``adjust=False``; 2026-09-12 review §12 #2) so it splices onto the IDX primary
feed, which is split-adjusted only. NOT dividend-adjusted, unlike the SGX/Bursa cache.
one CSV per symbol + manifest.json, and (with --commit) INSERT ... ON CONFLICT
DO NOTHING into market_data (interval='1d', symbol = Yahoo ticker unchanged,
e.g. 'BBCA.JK'). Index tickers (^JKSE, ^JKLQ45) are cached for screening only.

Reuses yf_fetch/insert_symbol from equity_ohlc_loader so the CSV + DB format is
byte-identical to the SGX/Bursa backfill. Dry-run by default.

    python research/idx_ohlc_loader.py                 # fetch + cache only
    python research/idx_ohlc_loader.py --commit        # + insert (needs blackheart-postgres)
    python research/idx_ohlc_loader.py --outdir /tmp/equity/idx   # VPS layout

IDX conventions: prices in IDR, board lot 100, T+2, sessions 09:00-15:49 WIB.
Ticker caveats: ADRO.JK = Alamtri (ex-Adaro Energy; AADI spun off 2024);
EXCL.JK = XLSmart (ex-XL Axiata, merged Smartfren 2025); GOTO.JK listed 2022
(short history — flagged by the <2000-bar note, excluded if <750).
"""
import argparse
import json
import os
import sys
import time
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from equity_ohlc_loader import yf_fetch, insert_symbol  # noqa: E402

DEFAULT_OUTDIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "research-scratch", "idx")

# ~LQ45 liquid large/mid caps with long history, sector-spread (banks, telco,
# consumer, autos, mining/materials, energy, infra, property, retail, health).
IDX = ("BBCA.JK BBRI.JK BMRI.JK BBNI.JK BRIS.JK "
       "TLKM.JK ISAT.JK EXCL.JK TOWR.JK TBIG.JK JSMR.JK "
       "UNVR.JK ICBP.JK INDF.JK KLBF.JK GGRM.JK HMSP.JK AMRT.JK CPIN.JK MYOR.JK SIDO.JK "
       "ASII.JK UNTR.JK "
       "ANTM.JK PTBA.JK ADRO.JK INCO.JK MDKA.JK ITMG.JK INTP.JK SMGR.JK TPIA.JK BRPT.JK "
       "PGAS.JK MEDC.JK AKRA.JK "
       "BSDE.JK CTRA.JK PWON.JK "
       "MAPI.JK ACES.JK MIKA.JK GOTO.JK").split()
SCREEN_ONLY = ["^JKSE", "^JKLQ45"]

UNIVERSE = [(t, "IDX", True) for t in IDX] + [(t, "IDX", False) for t in SCREEN_ONLY]

# Yahoo IDX history carries two defect classes the US/SGX/Bursa pull did not:
# (1) single-bar bad prints (v=0 placeholder or x10/÷10 decimal slips) that
#     revert next bar — impossible as real moves under IDX auto-reject bands
#     (±20-35%), so a close >50% off the ±5-bar local median is dropped;
# (2) leading stale segments (placeholder bars o=h=l=c with v=0 for months
#     before real trading, e.g. TPIA pre-relisting 2008-05, ITMG pre-2008-06)
#     — trimmed while >50% of the next 60 bars are placeholders. Distinct-close
#     tests are wrong here: IDX's coarse ticks make few distinct closes normal.
# (3) mid-series placeholder bars at a WRONG level (ITMG Mar-Jun 2008 at the
#     IPO price, ANTM 8-bar run Sep 2012) — a stale quote must equal the last
#     real close; a flat v=0 bar >1% off it is dropped.
# (4) per-symbol history floors where the head is unusable: pre-IPO back-fill
#     from another series (ICBP starts 2001, IPO 2010-10-07), pre-relisting
#     (TPIA), vendor-splice level shifts (KLBF x2.06 2004-02, x1.43 2005-09),
#     or a chronically illiquid head (PWON 2006-09 flat 70-85% of bars).
SPIKE_RATIO = 1.5
SPIKE_WIN = 5
STALE_WIN, STALE_MAX_FLAT = 60, 0.5
PLACEHOLDER_TOL = 0.01
HISTORY_FLOOR = {"ICBP.JK": ("2010-10-07", "pre_ipo"),
                 "TPIA.JK": ("2008-05-28", "pre_relisting"),
                 "KLBF.JK": ("2005-09-30", "vendor_splice_shifts"),
                 "PWON.JK": ("2009-08-07", "illiquid_head"),
                 "ANTM.JK": ("2013-01-02", "yahoo_gap_2010_2012")}   # 595 junk bars, 0 real in 2011
MAX_GAP_DAYS = 20   # calendar days between consecutive bars; longer = flagged hole
VENDOR_SPLICE = "2005-09-29"   # many IDX tickers start here; pre-splice levels can be off


def _median(xs):
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def _placeholder(r):
    return r[1] == r[2] == r[3] == r[4] and r[5] == 0


def clean_rows(tk, rows):
    """Returns (rows, notes). Listing floor, leading stale head, spike bars."""
    notes = []
    if tk in HISTORY_FLOOR:
        floor, why = HISTORY_FLOOR[tk]
        n0 = len(rows)
        rows = [r for r in rows if r[0] >= floor]
        notes.append("%s_dropped=%d(floor=%s)" % (why, n0 - len(rows), floor))
    start = 0
    for i in range(len(rows)):
        win = rows[i:i + STALE_WIN]
        if sum(1 for r in win if _placeholder(r)) <= STALE_MAX_FLAT * len(win):
            start = i
            break
    if start:
        notes.append("leading_stale_trimmed=%d(start->%s)" % (start, rows[start][0]))
        rows = rows[start:]
    # (3) placeholder bars off the last real close
    real, bad_ph, last = [], [], None
    for r in rows:
        if _placeholder(r) and last is not None and abs(r[4] / last - 1) > PLACEHOLDER_TOL:
            bad_ph.append(r[0])
            continue
        real.append(r)
        last = r[4]
    if bad_ph:
        notes.append("placeholder_bars_dropped=%d(%s)" % (len(bad_ph), ",".join(bad_ph[:4])))
    rows = real
    closes = [r[4] for r in rows]
    keep, dropped = [], []
    for i, r in enumerate(rows):
        nb = closes[max(0, i - SPIKE_WIN):i] + closes[i + 1:i + 1 + SPIKE_WIN]
        if len(nb) >= 3:
            ratio = r[4] / _median(nb)
            if ratio > SPIKE_RATIO or ratio < 1 / SPIKE_RATIO:
                dropped.append(r[0])
                continue
        keep.append(r)
    if dropped:
        notes.append("spike_bars_dropped=%d(%s)" % (len(dropped), ",".join(dropped[:6])))
    if keep and keep[0][0] < VENDOR_SPLICE:
        notes.append("pre_%s_vendor_splice" % VENDOR_SPLICE)
    gap, gap_at = 0, ""
    for a, b in zip(keep, keep[1:]):
        d = (date.fromisoformat(b[0]) - date.fromisoformat(a[0])).days
        if d > gap:
            gap, gap_at = d, b[0]
    if gap > MAX_GAP_DAYS:
        notes.append("HISTORY_GAP=%dd(before %s)" % (gap, gap_at))
    return keep, notes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true",
                    help="insert into market_data (default = dry-run)")
    ap.add_argument("--outdir", default=DEFAULT_OUTDIR)
    ap.add_argument("--codes", help="comma list of IDX codes (no .JK) or @file with one per line; "
                                    "default = the built-in universe. Existing CSVs are skipped unless --refresh.")
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    universe = UNIVERSE
    if a.codes:
        raw = open(a.codes[1:]).read().split() if a.codes.startswith("@") else a.codes.split(",")
        universe = [(c.strip().upper() + ".JK", "IDX", True) for c in raw if c.strip()]
    if not a.refresh:
        universe = [u for u in universe
                    if not os.path.exists(os.path.join(a.outdir, u[0].replace("^", "_") + ".csv"))]
    if a.codes and os.path.exists(os.path.join(a.outdir, "manifest.json")):
        prev = json.load(open(os.path.join(a.outdir, "manifest.json")))
        prev.pop("_meta", None)
    else:
        prev = {}
    os.makedirs(a.outdir, exist_ok=True)
    manifest = dict(prev)
    for tk, market, do_insert in universe:
        rows = None
        err = ""
        for attempt in range(3):
            try:
                rows, n_null, n_bad, n_adj = yf_fetch(tk, adjust=False)
                break
            except Exception as e:
                err = str(e)[:120]
                time.sleep(5)
        time.sleep(2)
        if rows is None:
            manifest[tk] = {"market": market, "bars": 0, "inserted": 0,
                            "screen_only": not do_insert,
                            "notes": ["FETCH_FAILED: " + err]}
            print("%-9s %-4s FETCH FAILED after 3 tries: %s" % (tk, market, err), flush=True)
            continue
        rows, notes = clean_rows(tk, rows)
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
        fn = os.path.join(a.outdir, tk.replace("^", "_") + ".csv")
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
        print("%-9s %-4s bars=%5d %s..%s inserted=%5d %s"
              % (tk, market, bars, rows[0][0], rows[-1][0], ins,
                 ";".join(notes) or tag), flush=True)
    manifest["_meta"] = {"basis": "split_only", "source": "yahoo_v8_chart_close_field",
                         "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    with open(os.path.join(a.outdir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1)
    ss = [v for k, v in manifest.items() if not k.startswith("_") and not v["screen_only"]]
    ok = sum(1 for s in ss if s["bars"] >= 750)
    print("SUMMARY IDX: %d/%d symbols ok, rows_inserted=%d, outdir=%s"
          % (ok, len(ss), sum(s["inserted"] for s in ss), a.outdir))


if __name__ == "__main__":
    main()
