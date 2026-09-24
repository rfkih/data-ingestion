#!/usr/bin/env python3
"""IDX - rata-rata kenaikan setelah breakout, dan apakah AKUMULASI BROKER meramalkan kelanjutannya (operator, 2026-09-24:
"cari berapa rata2 kenaikan setelah breakout, dan tambahkan juga broker accumulation filter, cari broker2 yang sudah
akumulasi saham tsb dalam waktu lama apakah ada korelasi dengan pelanjutan breakout").

Follow-up to study #130 (research/idx_breakout_stats.py, IDX_BREAKOUT_STATS_2026-09-24.md), which counted false breakouts.
DESCRIPTIVE / CORRELATIONAL ONLY - no money-rule trials, cumulative stays 711. Same event set and the same definitions.

PRE-REGISTERED (declared before the run; nothing tuned afterwards).
  A. GAIN PROFILE of every base60 breakout on >= 2x volume, per tier: mean / median / share positive / mean winner /
     mean loser at +1, +3, +5, +10, +20, +60 days from the breakout close, plus mean MFE and MAE over 20 days, and the
     same profile split by whether the break survived its first 5 days (close never back below the base top).
  B. PANEL-WIDE ACCUMULATION PROXIES, measured on the 60 days of the base ENDING t-1 (no look-ahead), ranked into
     quartiles inside the event set:
       fgn60   foreign net value over the base / (60 x 60-day median traded value)      [foreign accumulation]
       fgn20   the same over the last 20 days of the base
       f20     the feed's foreign_net_share_20d at t-1
       obv60   sum(sign(daily return) x volume) over the base / sum(volume)              [classic OBV accumulation]
       upvol   share of the base's volume that printed on up days
       quiet   count of days in the base with volume >= 2x median and |return| <= 1 %    [quiet-accumulation days]
  C. BROKER-LEVEL ACCUMULATION from idx.broker_summary (net value per broker per window, INVESTOR_TYPE_ALL /
     REGULER / NET). For each event only windows with date_to STRICTLY BEFORE the breakout date and no older than
     180 days are used; the latest M = 3 windows (~3 months) form the accumulation history:
       acc_persist  number of brokers net-positive in ALL 3 windows            ("sudah akumulasi lama")
       acc_top      largest cumulative broker net over the 3 windows / total buy value in those windows
       acc_conc     top-3 positive nets / sum of positive nets                 (concentration of the buying)
       det_top5     idx.broker_detector top5_pct on the latest window
     Split "accumulated" = acc_persist >= 1 AND acc_top >= the event-set median, against the rest.
READING RULES (declared): a measure is INTERESTING only if |Spearman IC vs the 20-day return| >= 0.10 with a
  permutation p < 0.05 (2000 draws) AND its top quartile beats its bottom quartile by >= 10 points on "still above the
  base top at 20 days". Section C is declared UNDERPOWERED if either side of the split has < 100 events; an
  underpowered result is reported as a direction, never as a finding. Nothing here becomes a rule without a money study.
READ-ONLY. INGEST_DB_DSN=... PYTHONIOENCODING=utf-8 blackheart-ingest/.venv/Scripts/python research/idx_breakout_accum.py [--no-store]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, timedelta

import numpy as np
import pandas as pd
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blackheart-ingest", "src"))
import idx_beyond as B  # noqa: E402
import idx_breakout_stats as BS  # noqa: E402
import idx_swing2 as S  # noqa: E402

BS.HOR = (1, 3, 5, 10, 20, 60)   # the gain profile needs the short horizons too
SEED = 20260924
N_TRIALS = 711
M_WIN = 3                        # broker windows that make up the accumulation history
MAX_AGE = 180                    # days: a window older than this is not "recent accumulation"
PROXIES = ("fgn60", "fgn20", "f20", "obv60", "upvol", "quiet")
DRAWS = 2000


def spearman(x, y):
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 30:
        return float("nan")
    a, b = pd.Series(x[ok]).rank().to_numpy(), pd.Series(y[ok]).rank().to_numpy()
    a, b = a - a.mean(), b - b.mean()
    d = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / d) if d > 0 else float("nan")


def perm_p(x, y, ic, rng):
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 30 or not np.isfinite(ic):
        return float("nan")
    xa, ya = x[ok], y[ok]
    hits = 0
    for _ in range(DRAWS):
        if abs(spearman(xa, rng.permutation(ya))) >= abs(ic):
            hits += 1
    return (hits + 1) / (DRAWS + 1)


def profile(m, sel):
    """Mean / median / hit at every horizon for one slice of events."""
    sel = sel & m["complete"]
    d = {"n": int(sel.sum()), "h": {}}
    if d["n"] == 0:
        return d
    for h in BS.HOR:
        r = m[f"r{h}"][sel]
        ok = np.isfinite(r)
        if not ok.any():
            continue
        rr = r[ok]
        win, lose = rr[rr > 0], rr[rr <= 0]
        d["h"][h] = {"n": int(ok.sum()), "avg": float(rr.mean()), "med": float(np.median(rr)), "pos": float((rr > 0).mean()),
                     "win_avg": float(win.mean()) if len(win) else float("nan"), "lose_avg": float(lose.mean()) if len(lose) else float("nan"),
                     "sd": float(rr.std(ddof=1)) if len(rr) > 1 else float("nan")}
    d["mfe_avg"] = float(np.nanmean(m["mfe"][sel]))
    d["mae_avg"] = float(np.nanmean(m["mae"][sel]))
    d["net20_avg"] = float(np.nanmean(m["net20"][sel]))
    return d


def cell(v, sign=True):
    return "-" if v is None or not np.isfinite(v) else (f"{v * 100:+.1f} %" if sign else f"{v * 100:.0f} %")


def prof_rows(label, d):
    if d["n"] == 0:
        return [f"| {label} | 0 | | | | | | |"]
    rows = []
    for h in BS.HOR:
        v = d["h"].get(h)
        if v is None:
            continue
        rows.append(f"| {label if h == BS.HOR[0] else ''} | +{h} d | {v['n']} | {cell(v['avg'])} | {cell(v['med'])} | {cell(v['pos'], False)} | "
                    f"{cell(v['win_avg'])} | {cell(v['lose_avg'])} |")
    return rows


PROF_HDR = ["| slice | horizon | events | mean | median | share up | mean winner | mean loser |", "|---|---|---|---|---|---|---|---|"]
Q_HDR = ["| quartile | events | back inside <=5 d | above top @20 d | up @20 d | mean 20 d | median 20 d | ran +10 % |",
         "|---|---|---|---|---|---|---|---|"]


def qrow(label, m, sel):
    d = BS.summarize(m, sel)
    if d["n"] == 0:
        return f"| {label} | 0 | | | | | | |"
    return (f"| {label} | {d['n']} | {cell(d['fail5'], False)} | {cell(d['above20'], False)} | {cell(d['r20_pos'], False)} | "
            f"{cell(d['r20_avg'])} | {cell(d['r20_med'])} | {cell(d['runner'], False)} |")


# ------------------------------------------------------------------------------------------------- broker history

def load_broker(dsn):
    with psycopg.connect(dsn) as conn:
        bs = pd.read_sql("""SELECT code, date_from, date_to, broker, net_value, buy_value FROM idx.broker_summary
                             WHERE investor_type = 'INVESTOR_TYPE_ALL' AND market_board = 'MARKET_BOARD_REGULER'
                               AND transaction_type = 'TRANSACTION_TYPE_NET' AND date_to > date_from""", conn)
        det = pd.read_sql("""SELECT code, date_from, date_to, top5_pct, total_buyer, total_seller FROM idx.broker_detector
                             WHERE investor_type = 'INVESTOR_TYPE_ALL' AND market_board = 'MARKET_BOARD_REGULER'
                               AND transaction_type = 'TRANSACTION_TYPE_NET' AND date_to > date_from""", conn)
    for df in (bs, det):
        df["date_from"] = pd.to_datetime(df["date_from"])
        df["date_to"] = pd.to_datetime(df["date_to"])
    for c in ("net_value", "buy_value"):
        bs[c] = pd.to_numeric(bs[c], errors="coerce")
    for c in ("top5_pct", "total_buyer", "total_seller"):
        det[c] = pd.to_numeric(det[c], errors="coerce")
    hist: dict[str, list] = {}
    for (code, d_from, d_to), g in bs.groupby(["code", "date_from", "date_to"], sort=False):
        hist.setdefault(code, []).append((d_to, d_from, g[["broker", "net_value", "buy_value"]].to_numpy(object)))
    for code in hist:
        hist[code].sort(key=lambda r: r[0])
    dmap = {(r.code, r.date_to): (r.top5_pct, r.total_buyer, r.total_seller) for r in det.itertuples(index=False)}
    return hist, dmap


def broker_features(hist, dmap, code, when, m_win=M_WIN):
    """Accumulation over the last m_win broker windows that closed strictly before `when`."""
    rows = hist.get(code)
    if not rows:
        return None
    cut = pd.Timestamp(when)
    usable = [r for r in rows if r[0] < cut and (cut - r[0]).days <= MAX_AGE]
    if len(usable) < m_win:
        return None
    usable = usable[-m_win:]
    nets: dict[str, list] = {}
    buy_total = 0.0
    for _, _, arr in usable:
        for broker, net, buy in arr:
            nets.setdefault(str(broker), []).append(float(net) if net is not None and np.isfinite(float(net)) else 0.0)
            buy_total += float(buy) if buy is not None and np.isfinite(float(buy)) else 0.0
    persist = sum(1 for v in nets.values() if len(v) == m_win and all(x > 0 for x in v))
    cum = {b: sum(v) for b, v in nets.items()}
    pos = sorted([v for v in cum.values() if v > 0], reverse=True)
    top = max(cum.values()) if cum else 0.0
    last_to = usable[-1][0]
    det = dmap.get((code, last_to), (np.nan, np.nan, np.nan))
    return {"acc_persist": float(persist), "acc_top": float(top / buy_total) if buy_total > 0 else float("nan"),
            "acc_conc": float(sum(pos[:3]) / sum(pos)) if pos else float("nan"),
            "det_top5": float(det[0]) if det[0] is not None and np.isfinite(det[0]) else float("nan"),
            "buyers_over_sellers": float(det[1] / det[2]) if det[1] and det[2] else float("nan"),
            "windows_from": str(usable[0][1].date()), "windows_to": str(last_to.date())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-store", action="store_true")
    args = ap.parse_args()
    dsn = os.environ["INGEST_DB_DSN"]
    with psycopg.connect(dsn) as conn:
        last_bar = pd.read_sql("SELECT max(trade_date) AS d FROM idx.bar WHERE source = 'idx'", conn)["d"].iloc[0]
    B.S.END = last_bar
    cache = os.environ.get("IDX_BEYOND_CACHE")
    if cache:
        cache = f"{cache}.{last_bar}"
    P, unis, comp, Hp, Lp, sectors, brent = B.load_all(dsn, cache)
    adj, vol = P["adj"], P["volume"]
    dates, cols = adj.index, adj.columns
    A, Hh, Ll = adj.to_numpy(float), Hp.to_numpy(float), Lp.to_numpy(float)
    c_in, c_out = S.costs(P)
    tiers = BS.tiers_of(P, unis)
    VR = (vol / vol.rolling(20, min_periods=20).median().shift(1).replace(0, np.nan)).to_numpy(float)
    rng = np.random.default_rng(SEED)
    print(f"panel {dates[0].date()} -> {dates[-1].date()}", flush=True)

    base, HI, _ = BS.base_panels(adj, **BS.BASES["base60"])
    HIn = HI.to_numpy(float)
    # --- accumulation proxies over the 60 days of the base, all shifted to end at t-1
    L = 60
    r1 = adj.pct_change()
    sgn_vol = np.sign(r1).fillna(0) * vol
    obv60 = (sgn_vol.rolling(L, min_periods=L).sum() / vol.rolling(L, min_periods=L).sum().replace(0, np.nan)).shift(1)
    upvol = ((vol.where(r1 > 0, 0.0)).rolling(L, min_periods=L).sum() / vol.rolling(L, min_periods=L).sum().replace(0, np.nan)).shift(1)
    vr_df = vol / vol.rolling(20, min_periods=20).median().shift(1).replace(0, np.nan)
    quiet = (((vr_df >= 2) & (r1.abs() <= 0.01)).astype(float).rolling(L, min_periods=L).sum()).shift(1)
    fnet, v60 = P["fnet"], P["v60"]
    fgn60 = (fnet.rolling(L, min_periods=L).sum() / (L * v60.replace(0, np.nan))).shift(1)
    fgn20 = (fnet.rolling(20, min_periods=20).sum() / (20 * v60.replace(0, np.nan))).shift(1)
    prox = {"fgn60": fgn60.to_numpy(float), "fgn20": fgn20.to_numpy(float), "f20": P["f20"].shift(1).to_numpy(float),
            "obv60": obv60.to_numpy(float), "upvol": upvol.to_numpy(float), "quiet": quiet.to_numpy(float)}

    out = {"panel": {"start": str(dates[0].date()), "end": str(dates[-1].date())}, "profile": {}, "proxies": {}, "broker": {}}
    ev = {}
    for tname in ("BLUE", "LIQ", "small", "THIN"):
        E = BS.events_for(adj, base, HI, tiers[tname])
        ti, tj = np.nonzero(E)
        m = BS.measure(A, Hh, Ll, c_in, c_out, ti, tj, HIn[ti, tj])
        m["vr"], m["ti"], m["tj"] = VR[ti, tj], ti, tj
        for k, arr in prox.items():
            m[k] = arr[ti, tj]
        ev[tname] = m
        print(f"{tname}: {len(ti)} breakouts, {(m['vr'] >= 2).sum()} with volume >= 2x", flush=True)

    # --- A. gain profile
    for tname in ("BLUE", "LIQ", "small", "THIN"):
        m = ev[tname]
        out["profile"][tname] = profile(m, m["vr"] >= 2)
    m = ev["LIQ"]
    volsel = m["vr"] >= 2
    survived = volsel & (m["fail"] > 5)
    out["profile"]["LIQ survived 5 d"] = profile(m, survived)
    out["profile"]["LIQ failed <=5 d"] = profile(m, volsel & (m["fail"] <= 5))

    # --- B. panel proxies, LIQ + THIN
    for tname in ("LIQ", "THIN"):
        mm = ev[tname]
        sel = (mm["vr"] >= 2) & mm["complete"]
        res = {}
        for k in PROXIES:
            x, y = mm[k][sel], mm["r20"][sel]
            ic = spearman(x, y)
            surv = (mm["fail"][sel] > 5).astype(float)
            ic_s = spearman(x, surv)
            qs = {}
            ok = np.isfinite(mm[k]) & sel
            if ok.sum() >= 40:
                qq = pd.qcut(pd.Series(mm[k][ok]), 4, labels=False, duplicates="drop").to_numpy()
                idx = np.flatnonzero(ok)
                for q in range(int(np.nanmax(qq)) + 1):
                    s = np.zeros(len(mm["r20"]), bool)
                    s[idx[qq == q]] = True
                    qs[f"Q{q + 1}"] = BS.summarize(mm, s)
            res[k] = {"ic_r20": ic, "ic_survive": ic_s, "p": perm_p(mm[k][sel], mm["r20"][sel], ic, rng), "quartiles": qs,
                      "coverage": float(np.isfinite(mm[k][sel]).mean())}
            print(f"{tname} {k}: IC vs r20 {ic:+.3f} (p {res[k]['p']:.3f}), IC vs survive {ic_s:+.3f}", flush=True)
        out["proxies"][tname] = res

    # --- C. broker-level accumulation
    hist, dmap = load_broker(dsn)
    print(f"broker history: {len(hist)} codes", flush=True)
    bro = {"coverage": {}, "measures": {}, "split": {}}
    mm = ev["THIN"]                                    # widest universe; the broker names are all liquid anyway
    sel_all = (mm["vr"] >= 2) & mm["complete"]
    feats = {k: np.full(len(mm["r20"]), np.nan) for k in ("acc_persist", "acc_top", "acc_conc", "det_top5", "buyers_over_sellers")}
    covered = np.zeros(len(mm["r20"]), bool)
    sweep = {}
    for w in (1, 2, 3):
        c = 0
        for i in np.flatnonzero(sel_all):
            if broker_features(hist, dmap, cols[mm["tj"][i]], dates[mm["ti"][i]], m_win=w) is not None:
                c += 1
        sweep[w] = c
        print(f"coverage with {w} window(s) before the break: {c} events", flush=True)
    bro["coverage_sweep"] = sweep
    m_use = max((w for w in (3, 2, 1) if sweep[w] >= 40), default=1)   # the longest history that still has 40+ events
    bro["m_win_used"] = m_use
    for i in np.flatnonzero(sel_all):
        f = broker_features(hist, dmap, cols[mm["tj"][i]], dates[mm["ti"][i]], m_win=m_use)
        if f is None:
            continue
        covered[i] = True
        for k in feats:
            feats[k][i] = f[k]
    for k, v in feats.items():
        mm[k] = v
    n_cov = int(covered.sum())
    bro["coverage"] = {"events_with_volume": int(sel_all.sum()), "events_with_broker_history": n_cov,
                       "codes_in_broker_table": len(hist), "codes_covered": int(len({cols[mm['tj'][i]] for i in np.flatnonzero(covered)}))}
    print(f"broker coverage: {n_cov} of {int(sel_all.sum())} volume breakouts", flush=True)
    if n_cov >= 40:
        for k in ("acc_persist", "acc_top", "acc_conc", "det_top5", "buyers_over_sellers"):
            x, y = mm[k][covered], mm["r20"][covered]
            ic = spearman(x, y)
            qs = {}
            ok = covered & np.isfinite(mm[k])
            if ok.sum() >= 40:
                try:
                    qq = pd.qcut(pd.Series(mm[k][ok]), 4, labels=False, duplicates="drop").to_numpy()
                except ValueError:
                    qq = None
                if qq is not None:
                    idx = np.flatnonzero(ok)
                    for q in range(int(np.nanmax(qq)) + 1):
                        s = np.zeros(len(mm["r20"]), bool)
                        s[idx[qq == q]] = True
                        qs[f"Q{q + 1}"] = BS.summarize(mm, s)
            bro["measures"][k] = {"ic_r20": ic, "ic_survive": spearman(x, (mm["fail"][covered] > 5).astype(float)),
                                  "p": perm_p(x, y, ic, rng), "quartiles": qs}
            print(f"broker {k}: IC vs r20 {ic:+.3f} (p {bro['measures'][k]['p']:.3f})", flush=True)
        med_top = float(np.nanmedian(mm["acc_top"][covered]))
        acc = covered & (mm["acc_persist"] >= 1) & (mm["acc_top"] >= med_top)
        non = covered & ~acc
        bro["split"] = {"accumulated": BS.summarize(mm, acc), "not accumulated": BS.summarize(mm, non), "median_acc_top": med_top,
                        "underpowered": bool(int(acc.sum()) < 100 or int(non.sum()) < 100)}
        # permutation on the split: is the gap in "up at 20 d" bigger than chance?
        lab = acc[covered].astype(float)
        yy = (mm["r20"][covered] > 0).astype(float)
        okk = np.isfinite(mm["r20"][covered])
        gap = float(yy[okk & (lab > 0)].mean() - yy[okk & (lab == 0)].mean()) if (okk & (lab > 0)).any() and (okk & (lab == 0)).any() else float("nan")
        hits = 0
        for _ in range(DRAWS):
            sh = rng.permutation(lab)
            a, b = yy[okk & (sh > 0)], yy[okk & (sh == 0)]
            if len(a) and len(b) and abs(a.mean() - b.mean()) >= abs(gap):
                hits += 1
        bro["split"]["gap_up20"] = gap
        bro["split"]["gap_p"] = (hits + 1) / (DRAWS + 1)
        print(f"split: accumulated {bro['split']['accumulated']['n']} vs {bro['split']['not accumulated']['n']}, gap {gap * 100:+.1f} pp, p {bro['split']['gap_p']:.3f}", flush=True)
    out["broker"] = bro

    # ----------------------------------------------------------------------------------------------- markdown
    Lns = [f"# IDX - rata-rata kenaikan setelah breakout + filter akumulasi broker - {date.today()} - descriptive, 0 new trials (cumulative N = {N_TRIALS})", "",
           f"Follow-up to study #130. Same events: a close above the top of a 60-day base (channel <= 25 %, |net move| <= 15 %, ER <= 0.30) on volume "
           f">= 2x the 20-day median, one per name per 20 days, panel {out['panel']['start']} -> {out['panel']['end']}. Returns from the breakout close "
           f"on adjusted prices; events without a complete 20-day forward window are excluded.", "",
           "## A. Berapa rata-rata kenaikan setelah breakout", "", *PROF_HDR]
    for t in ("BLUE", "LIQ", "small", "THIN"):
        Lns += prof_rows(t, out["profile"][t])
    Lns += ["", "| tier | events | mean MFE 20 d | mean MAE 20 d | mean net +20 d (next-close fill, costs) |", "|---|---|---|---|---|"]
    for t in ("BLUE", "LIQ", "small", "THIN"):
        d = out["profile"][t]
        Lns.append(f"| {t} | {d['n']} | {cell(d['mfe_avg'])} | {cell(d['mae_avg'])} | {cell(d['net20_avg'])} |")
    Lns += ["", "### The same profile split by the first five days (LIQ)", "", *PROF_HDR]
    for k in ("LIQ survived 5 d", "LIQ failed <=5 d"):
        Lns += prof_rows(k, out["profile"][k])
    Lns += ["", "## B. Akumulasi yang bisa diukur di seluruh panel (proxy)", ""]
    for tname in ("LIQ", "THIN"):
        Lns += [f"**{tname}** - Spearman IC of each measure against the 20-day return and against surviving five days "
                f"(permutation p over {DRAWS} draws)", "",
                "| measure | coverage | IC vs 20-day return | p | IC vs survives 5 d |", "|---|---|---|---|---|"]
        for k in PROXIES:
            v = out["proxies"][tname][k]
            Lns.append(f"| {k} | {cell(v['coverage'], False)} | {v['ic_r20']:+.3f} | {v['p']:.3f} | {v['ic_survive']:+.3f} |")
        Lns.append("")
    for tname in ("LIQ", "THIN"):
        for k in PROXIES:
            qs = out["proxies"][tname][k]["quartiles"]
            if not qs:
                continue
            Lns += [f"**{tname} / {k}** (Q1 = least accumulation, Q4 = most)", "", *Q_HDR]
            for q, d in qs.items():
                Lns.append(qrow(q, ev[tname], np.zeros(0, bool)) if d["n"] == 0 else
                           f"| {q} | {d['n']} | {cell(d['fail5'], False)} | {cell(d['above20'], False)} | {cell(d['r20_pos'], False)} | "
                           f"{cell(d['r20_avg'])} | {cell(d['r20_med'])} | {cell(d['runner'], False)} |")
            Lns.append("")
    Lns += ["## C. Akumulasi broker sungguhan (idx.broker_summary)", "",
            f"Coverage: {bro['coverage']['events_with_broker_history']} of {bro['coverage']['events_with_volume']} volume breakouts have "
            f"{bro.get('m_win_used', M_WIN)} broker window(s) closing in the {MAX_AGE} days before the break ({bro['coverage']['codes_covered']} distinct names; the table holds "
            f"{bro['coverage']['codes_in_broker_table']} codes with multi-day windows, mostly monthly since 2023-09).", ""]
    if bro.get("measures"):
        Lns += ["| measure | IC vs 20-day return | p | IC vs survives 5 d |", "|---|---|---|---|"]
        for k, v in bro["measures"].items():
            Lns.append(f"| {k} | {v['ic_r20']:+.3f} | {v['p']:.3f} | {v['ic_survive']:+.3f} |")
        for k, v in bro["measures"].items():
            if not v["quartiles"]:
                continue
            Lns += ["", f"**{k}** (Q1 = least, Q4 = most)", "", *Q_HDR]
            for q, d in v["quartiles"].items():
                Lns.append(f"| {q} | {d['n']} | {cell(d['fail5'], False)} | {cell(d['above20'], False)} | {cell(d['r20_pos'], False)} | "
                           f"{cell(d['r20_avg'])} | {cell(d['r20_med'])} | {cell(d['runner'], False)} |")
        sp = bro["split"]
        Lns += ["", f"**The declared split** - accumulated = at least one broker net-positive in all {bro.get('m_win_used', M_WIN)} window(s) AND the top accumulator took "
                f"{sp['median_acc_top'] * 100:.1f} % or more of all buying (the event-set median)", "", *Q_HDR]
        for k in ("accumulated", "not accumulated"):
            d = sp[k]
            Lns.append(f"| {k} | {d['n']} | {cell(d['fail5'], False)} | {cell(d['above20'], False)} | {cell(d['r20_pos'], False)} | "
                       f"{cell(d['r20_avg'])} | {cell(d['r20_med'])} | {cell(d['runner'], False)} |")
        Lns += ["", f"Gap in 'up at 20 days': {sp['gap_up20'] * 100:+.1f} pp, permutation p = {sp['gap_p']:.3f}. "
                f"{'UNDERPOWERED by the declared rule (a side has fewer than 100 events) - read as a direction, not a finding.' if sp['underpowered'] else 'Both sides clear the declared 100-event floor.'}", ""]
    else:
        Lns += ["Too few covered events to measure anything (fewer than 40).", ""]
    path = os.path.join(HERE, f"IDX_BREAKOUT_ACCUM_{date.today().isoformat()}.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(Lns) + "\n")
    print("\n".join(Lns))
    print("wrote", path)
    if not args.no_store:
        from blackheart_ingest.idx import research_store as rs
        with psycopg.connect(dsn) as conn:
            sid = rs.record_study(conn, "breakout_accum", dates[-1].date(),
                                  params={"trials": [], "n_trials_cumulative": N_TRIALS, "proxies": list(PROXIES), "m_win": M_WIN, "max_age": MAX_AGE,
                                          "seed": SEED, "descriptive": True},
                                  summary=json.loads(json.dumps(out, default=str)), names=[], report_path=path,
                                  note=f"gain profile + accumulation; broker coverage {bro['coverage']['events_with_broker_history']}/{bro['coverage']['events_with_volume']}")
            print(f"study #{sid} stored")


if __name__ == "__main__":
    main()
