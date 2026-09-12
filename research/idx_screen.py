#!/usr/bin/env python3
"""IDX phase-1 screen — Donchian breakout on the primary-source IDX data plane (go/no-go).

Same certified rule, grid, stats and PASS gate as research/equity_screen.py (imported, not
re-implemented), with three IDX-specific additions from the 2026-09-12 spec §12:

* fill basis: ``next_open`` (signal on close i, executed at open i+1; gap risk included) next to the
  certified ``close`` fill. IDX records opens before 2025 only for LQ45, so a missing open is
  gap-filled from the Yahoo open (rescaled by the same-day close ratio) when cached, else the
  next close — and every cell reports its fill mix (open / yahoo-open / close-fallback).
* liquidity gate (point-in-time): a new entry is allowed only when the trailing 60-day median
  traded value >= Rp 5 bn (Yahoo segment: close*volume proxy). Exits are always allowed.
* honest multiplicity: DSR at N=8 (cells per symbol) AND at N=8*universe; a per-symbol 5-fold
  expanding walk-forward that picks the cell on the train fold only.

Cost: 50 bps round trip (25 bps/side, charged 2x at exit — the platform convention).
Data: idx.bar (adjusted = raw*adj_factor) for 2020+, Yahoo split-only cache re-based onto the
IDX basis for pre-2020 (same rule as blackheart_ingest.idx.publish). Corr refs + base book from
market_data. READ-ONLY. Run with the ingest venv (psycopg + numpy):

    INGEST_DB_DSN=... python research/idx_screen.py [--fill next_open|close] [--top N]
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import statistics
import sys
import time
from datetime import date, datetime, timezone

import psycopg

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import equity_screen as ES  # noqa: E402  (certified sleeve/stats/WF)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
YAHOO_DIR = os.path.join(ROOT, "research-scratch", "idx")
OUTDIR = os.path.join(ROOT, "research-scratch", "idx-screen")
COST_BPS = 25.0                 # per side; 2x at exit = 50 bps round trip
GRID = ES.GRID                  # [(20,10),(40,20),(55,20),(100,40)]
LIQ_THRESHOLD = 5e9             # Rp, trailing 60d median daily value
LIQ_WIN = 60
MIN_BARS = 750
N_FOLDS = 5


# ---------------------------------------------------------------------------
# data
# ---------------------------------------------------------------------------

def connect():
    dsn = os.environ.get("INGEST_DB_DSN")
    if not dsn:
        sys.exit("set INGEST_DB_DSN (see blackheart-ingest/idx-local.env)")
    return psycopg.connect(dsn)


def db_ohlc(conn, symbol, interval="1d"):
    """{date: (H, L, C)} from market_data — replaces equity_screen.db_ohlc (docker psql)."""
    out = {}
    for d, h, l, c in conn.execute(
        "SELECT start_time::date, high_price, low_price, close_price FROM market_data "
        "WHERE symbol=%s AND interval=%s ORDER BY start_time", (symbol, interval)):
        out[d.isoformat()] = (float(h), float(l), float(c))
    return out


def load_yahoo(code):
    p = os.path.join(YAHOO_DIR, f"{code}.JK.csv")
    if not os.path.exists(p):
        return {}
    out = {}
    with open(p, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out[r["date"]] = (float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]), float(r["volume"]))
    return out


def load_idx(conn, code):
    """Per date: dict(o, h, l, c, value, open_missing) on the IDX reference-price basis."""
    out = {}
    for d, o, h, l, c, v, f, om in conn.execute(
        "SELECT trade_date, open, high, low, close, value, adj_factor, open_missing FROM idx.bar "
        "WHERE code=%s AND source='idx' ORDER BY trade_date", (code,)):
        f = float(f)
        out[d.isoformat()] = {"o": float(o) * f if o is not None else None, "h": float(h) * f, "l": float(l) * f,
                              "c": float(c) * f, "value": float(v or 0), "om": bool(om)}
    return out


def build_series(conn, code):
    """Merge IDX (2020+) with the Yahoo pre-2020 segment (re-based) and gap-fill IDX opens from Yahoo.

    Returns (dates, O, H, L, C, VAL, OSRC) where OSRC[i] in {'idx','yahoo','none'} and O[i] may be None."""
    idx = load_idx(conn, code)
    ya = load_yahoo(code)
    if not idx:
        return None
    first_idx = min(idx)
    # splice ratio on the first 5 overlapping days (same rule as publish.py)
    overlap = [d for d in sorted(ya) if d in idx][:5]
    ratios = [idx[d]["c"] / ya[d][3] for d in overlap if ya[d][3] > 0]
    ratio = statistics.median(ratios) if ratios else 1.0
    yahoo_ok = len(ratios) >= 3 and abs(ratio - 1) <= 0.15     # same rejection rule as idx.publish
    rows = {}
    if yahoo_ok:
        for d, (o, h, l, c, v) in ya.items():
            if d < first_idx:
                rows[d] = (o * ratio, h * ratio, l * ratio, c * ratio, c * v * ratio, "yahoo")
    for d, x in idx.items():
        o, src = x["o"], "idx"
        if o is None:
            y = ya.get(d) if yahoo_ok else None
            if y and y[3] > 0 and y[0] > 0:
                o, src = y[0] * (x["c"] / y[3]), "yahoo"      # same-day basis conversion
            else:
                src = "none"
        rows[d] = (o, x["h"], x["l"], x["c"], x["value"], src)
    dates = sorted(rows)
    O = [rows[d][0] for d in dates]; H = [rows[d][1] for d in dates]; L = [rows[d][2] for d in dates]
    C = [rows[d][3] for d in dates]; VAL = [rows[d][4] for d in dates]; OSRC = [rows[d][5] for d in dates]
    return dates, O, H, L, C, VAL, OSRC, (ratio if yahoo_ok else None), len([d for d in dates if d < first_idx])


def liquidity_mask(VAL):
    """liq[i] = trailing LIQ_WIN-day median of VAL[i-LIQ_WIN:i] >= threshold (strictly past data)."""
    n = len(VAL)
    liq = [False] * n
    window = []
    for i in range(n):
        if len(window) == LIQ_WIN:
            liq[i] = statistics.median(window) >= LIQ_THRESHOLD
        window.append(VAL[i])
        if len(window) > LIQ_WIN:
            window.pop(0)
    return liq


# ---------------------------------------------------------------------------
# sleeve with explicit fills
# ---------------------------------------------------------------------------

def sleeve_fill(dates, O, H, L, C, en, xn, long_only, cost_bps, liq=None, fill="next_open"):
    """Donchian breakout / opposite-channel exit (equity_screen.sleeve rule) with explicit fills.

    fill='signal_close'  -> execute at the signal bar's close (== certified sleeve; regression only)
    fill='next_open'     -> execute at the next bar's open, or its close when the open is None
    Returns (daily {date: log-return}, trades [net simple], fills {'open','close_fallback'})."""
    n = len(dates)
    cost = cost_bps / 10000.0
    pos = 0
    pending = None                     # ('enter', +1/-1) or ('exit',) to execute at bar i
    cur = 0.0
    daily, trades = {}, []
    fills = {"open": 0, "close_fallback": 0}
    prev_c = None
    for i in range(en + 1, n):
        c = C[i]
        r = 0.0
        # 1) execute pending order (next_open mode) at this bar's fill price
        if pending is not None:
            f = O[i]
            if f is None or f <= 0:
                f = c; fills["close_fallback"] += 1
            else:
                fills["open"] += 1
            if pending[0] == "exit":
                leg = pos * math.log(f / prev_c) if prev_c else 0.0
                r += leg; cur += leg
                r -= 2 * cost; cur -= 2 * cost
                trades.append(math.exp(cur) - 1.0); cur = 0.0; pos = 0
                r += 0.0  # flat for the rest of the bar
            else:
                pos = pending[1]; cur = 0.0
                leg = pos * math.log(c / f)
                r += leg; cur += leg
            pending = None
        elif pos != 0 and prev_c and prev_c > 0:
            r = pos * math.log(c / prev_c); cur += r
        # 2) signal on this bar's close (channels from strictly prior bars — certified rule)
        upE = max(H[i - en:i]); loE = min(L[i - en:i])
        upX = max(H[i - xn:i]); loX = min(L[i - xn:i])
        if fill == "signal_close":
            if pos == 1 and c <= loX:
                r -= 2 * cost; cur -= 2 * cost; trades.append(math.exp(cur) - 1.0); cur = 0.0; pos = 0
            elif pos == -1 and c >= upX:
                r -= 2 * cost; cur -= 2 * cost; trades.append(math.exp(cur) - 1.0); cur = 0.0; pos = 0
            if pos == 0:
                if c > upE and (liq is None or liq[i]):
                    pos = 1; cur = 0.0
                elif c < loE and not long_only and (liq is None or liq[i]):
                    pos = -1; cur = 0.0
        else:
            if pos == 1 and c <= loX:
                pending = ("exit",)
            elif pos == -1 and c >= upX:
                pending = ("exit",)
            elif pos == 0:
                if c > upE and (liq is None or liq[i]):
                    pending = ("enter", 1)
                elif c < loE and not long_only and (liq is None or liq[i]):
                    pending = ("enter", -1)
        prev_c = c
        daily[dates[i]] = r
    return daily, trades, fills


def cell_metrics(daily, trades, btc_r, gold_r):
    ser = [daily[d] for d in sorted(daily)]
    wins = sum(t for t in trades if t > 0); loss = -sum(t for t in trades if t < 0)
    pf = (wins / loss) if loss > 0 else (999.0 if wins > 0 else 0.0)
    cb = ES.corr_vs(daily, btc_r); cg = ES.corr_vs(daily, gold_r)
    return {"n": len(trades), "pf": round(pf, 3), "sharpe": round(ES.sharpe(ser, 252), 3),
            "ret_pct": round((math.exp(sum(ser)) - 1) * 100, 1), "mdd": round(ES.maxdd(ser), 1),
            "corr_btc": None if cb is None else round(cb, 3), "corr_gold": None if cg is None else round(cg, 3),
            "in_pos_days": sum(1 for x in ser if x != 0.0), "days": len(ser)}


def per_symbol_wf(cell_dailies, n_folds=N_FOLDS):
    """Expanding-window WF over the 8 cells: pick max-Sharpe cell (n>=10 trades in train) on the train
    fold, apply on the test fold. Returns oos series, fold results, and the picked cells."""
    keys = list(cell_dailies)
    common = sorted(set.intersection(*[set(cell_dailies[k][0]) for k in keys]))
    N = len(common); warm = N // 3; step = (N - warm) // n_folds
    oos = []; folds = []
    for k in range(n_folds):
        tr_end = warm + k * step
        te_end = warm + (k + 1) * step if k < n_folds - 1 else N
        if te_end - tr_end < 5:
            continue
        best_key, best_s = None, -1e9
        for key in keys:
            d, trades_dates = cell_dailies[key]
            tr = [d[x] for x in common[:tr_end]]
            n_tr = sum(1 for td in trades_dates if td < common[tr_end])
            if n_tr < 10:
                continue
            s = ES.sharpe(tr, 252)
            if s > best_s:
                best_key, best_s = key, s
        if best_key is None:
            best_key = max(keys, key=lambda kk: ES.sharpe([cell_dailies[kk][0][x] for x in common[:tr_end]], 252))
        d = cell_dailies[best_key][0]
        te = [d[x] for x in common[tr_end:te_end]]
        oos.extend(te)
        folds.append({"fold": k + 1, "cell": best_key, "train_sharpe": round(best_s, 3),
                      "oos_sharpe": round(ES.sharpe(te, 252), 3), "oos_ret_pct": round((math.exp(sum(te)) - 1) * 100, 1)})
    return oos, folds


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fill", choices=["next_open", "close"], default="next_open")
    ap.add_argument("--universe", default=os.path.join(OUTDIR, "universe.json"))
    ap.add_argument("--codes", help="comma list to restrict (debug)")
    ap.add_argument("--no-liq-gate", action="store_true")
    ap.add_argument("--top", type=int, default=25)
    a = ap.parse_args()
    os.makedirs(OUTDIR, exist_ok=True)
    conn = connect()
    ES.db_ohlc = lambda sym: db_ohlc(conn, sym)        # base book + corr refs via psycopg
    fill_mode = "signal_close" if a.fill == "close" else "next_open"

    universe = json.load(open(a.universe))
    codes = [u["code"] for u in universe]
    if a.codes:
        codes = [c.strip().upper() for c in a.codes.split(",")]
    btc_r = ES.logret(db_ohlc(conn, "BTCUSDT")); gold_r = ES.logret(db_ohlc(conn, "XAUUSD"))
    print("corr refs: BTCUSDT %d ret-days, XAUUSD %d ret-days | fill=%s | liq gate=%s | universe=%d"
          % (len(btc_r), len(gold_r), fill_mode, not a.no_liq_gate, len(codes)), flush=True)

    t0 = time.time()
    cells, best, wf_all, meta = [], {}, {}, {}
    skipped = []
    for k, code in enumerate(codes, 1):
        s = build_series(conn, code)
        if s is None:
            skipped.append((code, "no idx bars")); continue
        dates, O, H, L, C, VAL, OSRC, ratio, n_pre = s
        if len(dates) < MIN_BARS:
            skipped.append((code, "bars=%d<%d" % (len(dates), MIN_BARS))); continue
        liq = None if a.no_liq_gate else liquidity_mask(VAL)
        meta[code] = {"bars": len(dates), "first": dates[0], "last": dates[-1], "pre2020_yahoo_bars": n_pre,
                      "splice_ratio": None if ratio is None else round(ratio, 4), "yahoo_rejected": ratio is None,
                      "open_src": {k2: OSRC.count(k2) for k2 in ("idx", "yahoo", "none")},
                      "liquid_days": sum(1 for x in (liq or []) if x)}
        sym_cells, cell_dailies = [], {}
        for en, xn in GRID:
            for lo in (True, False):
                daily, trades, fills = sleeve_fill(dates, O, H, L, C, en, xn, lo, COST_BPS, liq, fill_mode)
                m = cell_metrics(daily, trades, btc_r, gold_r)
                cell = {"sym": code, "cfg": "%d/%d" % (en, xn), "side": "L" if lo else "LS", **m,
                        "fills_open": fills["open"], "fills_close_fallback": fills["close_fallback"]}
                sym_cells.append(cell); cells.append(cell)
                # trade dates for WF train counting: approximate by exit days (nonzero r after a trade) — use
                # entry signal days: days where daily != 0 first after zero streak
                tdates = []
                prev0 = True
                for d in sorted(daily):
                    nz = daily[d] != 0.0
                    if nz and prev0:
                        tdates.append(d)
                    prev0 = not nz
                cell_dailies["%d/%d %s" % (en, xn, "L" if lo else "LS")] = (daily, tdates)
        elig = [c for c in sym_cells if c["n"] >= 40]
        b = dict(max(elig or sym_cells, key=lambda c: c["sharpe"]))
        cb, cg = b["corr_btc"], b["corr_gold"]
        b["PASS"] = bool(b["pf"] > 1.2 and b["sharpe"] > 0.35 and b["n"] >= 40
                         and cb is not None and abs(cb) < 0.30 and cg is not None and abs(cg) < 0.30)
        # honest multiplicity on the best cell's own series
        bd = cell_dailies["%s %s" % (b["cfg"], b["side"])][0]
        bser = [bd[d] for d in sorted(bd)]
        b["dsr8"] = round(ES.deflated_sharpe(bser, 8), 3)
        b["dsrN"] = round(ES.deflated_sharpe(bser, 8 * len(codes)), 3)
        oos, folds = per_symbol_wf(cell_dailies)
        b["wf_oos_sharpe"] = round(ES.sharpe(oos, 252), 3) if oos else None
        b["wf_folds_pos"] = sum(1 for f in folds if f["oos_ret_pct"] > 0)
        b["wf_folds"] = len(folds)
        b["wf_dsr8"] = round(ES.deflated_sharpe(oos, 8), 3) if oos else None
        wf_all[code] = folds
        best[code] = b
        if k % 50 == 0:
            print("... %d/%d symbols (%.0fs)" % (k, len(codes), time.time() - t0), flush=True)

    hdr = "%-6s %-7s %-3s %4s %6s %7s %7s %5s %7s %8s %6s %6s %7s %5s %s"
    print("\n=== BEST CELL PER SYMBOL (max Sharpe among n>=40 cells) — fill=%s, 50 bps, liq gate ===" % fill_mode)
    print(hdr % ("sym", "cfg", "sd", "n", "PF", "Sharpe", "retPct", "mDD", "corrBTC", "corrGOLD", "DSR8", "DSRn", "WFoos", "folds", "PASS"))
    ranked = sorted(best, key=lambda c: -best[c]["sharpe"])
    for code in ranked[:a.top]:
        b = best[code]
        print(hdr % (code, b["cfg"], b["side"], b["n"], "%.2f" % min(b["pf"], 99), "%.3f" % b["sharpe"],
                     "%.0f" % b["ret_pct"], "%.0f" % b["mdd"],
                     "n/a" if b["corr_btc"] is None else "%+.2f" % b["corr_btc"],
                     "n/a" if b["corr_gold"] is None else "%+.2f" % b["corr_gold"],
                     "%.3f" % b["dsr8"], "%.3f" % b["dsrN"],
                     "n/a" if b["wf_oos_sharpe"] is None else "%.3f" % b["wf_oos_sharpe"],
                     "%d/%d" % (b["wf_folds_pos"], b["wf_folds"]), "PASS" if b["PASS"] else "-"))

    passers = [c for c in ranked if best[c]["PASS"]]
    strong = [c for c in passers if best[c]["dsr8"] >= 0.90 and best[c]["wf_folds_pos"] == best[c]["wf_folds"] and best[c]["wf_folds"] >= 4]
    honest = [c for c in passers if best[c]["dsrN"] >= 0.90]
    print("\nUNIVERSE %d | screened %d | skipped %d | PASSERS (certified gate @50bps): %d | + DSR8>=0.90 & all WF folds +: %d | DSR at honest N=%d >=0.90: %d"
          % (len(codes), len(best), len(skipped), len(passers), len(strong), 8 * len(codes), len(honest)))
    # fill-basis summary
    fo = sum(c["fills_open"] for c in cells); fc = sum(c["fills_close_fallback"] for c in cells)
    print("fills: open=%d close_fallback=%d (%.0f%% at open)" % (fo, fc, 100 * fo / max(1, fo + fc)))
    osrc = {"idx": 0, "yahoo": 0, "none": 0}
    for m in meta.values():
        for k2 in osrc: osrc[k2] += m["open_src"][k2]
    print("open source over all bars: %s" % osrc)

    # book-lift for tradeable passers (top 3 by Sharpe) — certified base book + candidate, vol-parity WF
    book = None
    if strong or passers:
        cand_codes = (strong or passers)[:3]
        print("\n=== BOOK-LIFT: base 4-sleeve book vs base+candidate (equity_screen.wf_metrics) ===")
        try:
            base = [ES.crypto_pool(),
                    ES.sleeve(db_ohlc(conn, "XAUUSD"), 40, 20, True, ES.BASE_COST)[0],
                    ES.sleeve(db_ohlc(conn, "ZC=F"), 55, 20, True, ES.BASE_COST)[0],
                    ES.sleeve(db_ohlc(conn, "JPY=X"), 55, 20, True, ES.BASE_COST)[0]]
            book = {"BASE(CRYPTO+GOLD+CORN+USDJPY)": ES.wf_metrics(base)}
            for code in cand_codes:
                b = best[code]; en, xn = map(int, b["cfg"].split("/"))
                dates, O, H, L, C, VAL, OSRC, _, _ = build_series(conn, code)
                liq = None if a.no_liq_gate else liquidity_mask(VAL)
                cand, _, _ = sleeve_fill(dates, O, H, L, C, en, xn, b["side"] == "L", COST_BPS, liq, fill_mode)
                book["BASE+%s(%s,%s)" % (code, b["cfg"], b["side"])] = ES.wf_metrics(base + [cand])
            khdr = "%-34s %5s %9s %6s %6s %6s %6s %6s"
            print(khdr % ("book", "days", "SharpeOOS", "DSR20", "DSR50", "DSR100", "mDD", "mxCor"))
            for kb, v in book.items():
                print(khdr % (kb, v["common_days"], "%.3f" % v["oos_sharpe"], "%.3f" % v["dsr20"], "%.3f" % v["dsr50"],
                              "%.3f" % v["dsr100"], "%.1f" % v["maxdd"], "%.3f" % v["max_abs_corr"]))
            print("DSR gate to beat: %.3f" % ES.DSR_GATE)
        except Exception as e:  # noqa: BLE001
            print("book-lift failed: %s" % e)

    out = {"generated": datetime.now(timezone.utc).isoformat(), "fill": fill_mode, "cost_bps_round_trip": 2 * COST_BPS,
           "liq_gate": not a.no_liq_gate, "universe": len(codes), "cells": cells, "best": best, "wf": wf_all,
           "meta": meta, "skipped": skipped, "passers": passers, "strong": strong, "honest": honest, "book_lift": book}
    fn = os.path.join(OUTDIR, "screen_results_%s.json" % fill_mode)
    with open(fn, "w") as f:
        json.dump(out, f, indent=1)
    print("\nresults -> %s (%.0fs)" % (fn, time.time() - t0))


if __name__ == "__main__":
    main()
