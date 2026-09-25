#!/usr/bin/env python3
"""IDX - "banyak strategi mencari akumulasi sebelum kenaikan tinggi" - apakah korelasinya nyata, atau ukuran akumulasi
desk yang salah? (operator, 2026-09-24, after studies #130/#131 found nothing in six accumulation proxies.)

The question has a direction problem. "Big risers show accumulation beforehand" is P(accumulation | big rise); a strategy
needs P(big rise | accumulation). Both are measured here, on the same panel, with a richer, textbook (Wyckoff-style)
definition of accumulation than #131 used, so that "your measure was too crude" is tested rather than assumed.

DESCRIPTIVE - no money-rule trials (cumulative stays 711). Panel idx.bar 2020-01 -> last bar, boards Utama + Pengembangan.

PRE-REGISTERED (declared before the run).
  Snapshots: every 10th trading day (to limit overlap), every name in the tier that day. Tiers LIQ (>= Rp 5 bn/day, px >= 100)
    and THIN (>= Rp 0.5 bn). Features use the 60 days ENDING t; outcomes use days t+1 .. t+60.
  BIG RISE (the target the folk strategy wants): close_{t+60} / close_t - 1 >= +50 % (held), and `touch50` = the highest close
    in the next 60 days >= 1.5 x close_t. Also +30 % held, and CRASH = close_{t+60} <= -30 % (the mirror).
  ACCUMULATION FEATURES at t (all from the tape, available for every name):
    flat     |close_t / close_{t-60} - 1| <= 15 %                      (price has gone nowhere)
    obv60    sum(sign(daily return) x volume) / sum(volume) over 60 d  (OBV slope, normalised)
    upvol    share of 60-day volume printed on up days
    voltrend mean volume last 20 d / mean volume days 21-60          (volume waking up)
    squeeze  20-day close range / 60-day close range                  (range contraction, LOW = tight)
    higherlow min close last 20 d > min close days 21-60              (a rising floor)
    quiet    days in the 60 with volume >= 2x median and |return| <= 1 %
    fgn60    foreign net value / (60 x median traded value)           (foreign accumulation)
    WYCKOFF  flat AND obv60 in the top tercile AND voltrend >= 1.2 AND squeeze <= 0.5 AND higherlow   (the textbook picture)
    ACC_SCORE  mean of the within-snapshot percentile ranks of obv60, upvol, voltrend, -squeeze, quiet, fgn60 (a soft composite)
  READ: for each feature, (a) P(big rise | top decile) vs base rate = the strategy's number; (b) P(top decile | big rise) vs 10 %
    = the hindsight number; (c) the same for CRASH, because accumulation-looking tape that precedes crashes as often as rises
    is not accumulation. Lift is INTERESTING if P(rise | signal) >= 1.5 x base with >= 200 signal snapshots AND the crash lift
    is not also >= 1.5 x. A permutation band (2000 draws of the target within snapshot date) is given for the WYCKOFF cell.
READ-ONLY. INGEST_DB_DSN=... PYTHONIOENCODING=utf-8 blackheart-ingest/.venv/Scripts/python research/idx_accum_reverse.py [--no-store]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date

import numpy as np
import pandas as pd
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blackheart-ingest", "src"))
import idx_beyond as B  # noqa: E402
import idx_breakout_stats as BS  # noqa: E402

SEED = 20260924
N_TRIALS = 711
STEP = 10
L = 60
H = 60
FEATS = ("obv60", "upvol", "voltrend", "squeeze_low", "quiet", "fgn60", "acc_score")
DRAWS = 2000


def pct_rank_within_day(x: np.ndarray, day: np.ndarray) -> np.ndarray:
    out = np.full(len(x), np.nan)
    df = pd.DataFrame({"x": x, "d": day})
    ok = np.isfinite(x)
    out[ok] = df[ok].groupby("d")["x"].rank(pct=True).to_numpy()
    return out


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
    tiers = BS.tiers_of(P, unis)
    rng = np.random.default_rng(SEED)

    r1 = adj.pct_change()
    vsum = vol.rolling(L, min_periods=L).sum().replace(0, np.nan)
    F = {
        "flat": (adj / adj.shift(L) - 1).abs() <= 0.15,
        "obv60": (np.sign(r1).fillna(0) * vol).rolling(L, min_periods=L).sum() / vsum,
        "upvol": vol.where(r1 > 0, 0.0).rolling(L, min_periods=L).sum() / vsum,
        "voltrend": vol.rolling(20, min_periods=20).mean() / vol.shift(20).rolling(40, min_periods=40).mean().replace(0, np.nan),
        "squeeze": (adj.rolling(20, min_periods=20).max() - adj.rolling(20, min_periods=20).min())
        / (adj.rolling(L, min_periods=L).max() - adj.rolling(L, min_periods=L).min()).replace(0, np.nan),
        "higherlow": adj.rolling(20, min_periods=20).min() > adj.shift(20).rolling(40, min_periods=40).min(),
        "quiet": ((vol / vol.rolling(20, min_periods=20).median().shift(1).replace(0, np.nan) >= 2) & (r1.abs() <= 0.01)).astype(float).rolling(L, min_periods=L).sum(),
        "fgn60": P["fnet"].rolling(L, min_periods=L).sum() / (L * P["v60"].replace(0, np.nan)),
    }
    fwd60 = adj.shift(-H) / adj - 1
    touch50 = adj[::-1].rolling(H, min_periods=H).max()[::-1].shift(-1) / adj - 1 >= 0.5
    snap_idx = np.arange(L, len(dates) - H, STEP)
    out = {"panel": {"start": str(dates[0].date()), "end": str(dates[-1].date()), "snapshots": int(len(snap_idx))}, "tiers": {}}

    for tname in ("LIQ", "THIN"):
        tier = tiers[tname].to_numpy(bool)
        rows = []
        for t in snap_idx:
            js = np.flatnonzero(tier[t] & np.isfinite(fwd60.to_numpy(float)[t]))
            if len(js) == 0:
                continue
            d = {"day": np.full(len(js), t), "j": js, "r60": fwd60.to_numpy(float)[t, js], "touch50": touch50.to_numpy(bool)[t, js]}
            for k, v in F.items():
                d[k] = v.to_numpy(float)[t, js]
            rows.append(pd.DataFrame(d))
        df = pd.concat(rows, ignore_index=True)
        df["squeeze_low"] = -df["squeeze"]
        df["rise50"] = df["r60"] >= 0.5
        df["rise30"] = df["r60"] >= 0.3
        df["crash30"] = df["r60"] <= -0.3
        ranks = {k: pct_rank_within_day(df[k].to_numpy(float), df["day"].to_numpy()) for k in ("obv60", "upvol", "voltrend", "squeeze_low", "quiet", "fgn60")}
        df["acc_score"] = np.nanmean(np.column_stack(list(ranks.values())), axis=1)
        ranks["acc_score"] = pct_rank_within_day(df["acc_score"].to_numpy(float), df["day"].to_numpy())
        obv_ter = pct_rank_within_day(df["obv60"].to_numpy(float), df["day"].to_numpy()) >= 2 / 3
        df["wyckoff"] = (df["flat"] > 0) & obv_ter & (df["voltrend"] >= 1.2) & (df["squeeze"] <= 0.5) & (df["higherlow"] > 0)
        n = len(df)
        base = {k: float(df[k].mean()) for k in ("rise50", "touch50", "rise30", "crash30")}
        res = {"n": n, "names_per_snapshot": float(n / len(snap_idx)), "base": base, "features": {}, "wyckoff": {},
               "r60_all": {"mean": float(df["r60"].mean()), "median": float(df["r60"].median())}}
        print(f"{tname}: {n} name-snapshots, base P(+50% held in 60d) {base['rise50'] * 100:.2f} %, touch {base['touch50'] * 100:.2f} %, crash {base['crash30'] * 100:.2f} %", flush=True)

        def cell(mask, label):
            m = mask & np.isfinite(df["r60"].to_numpy(float))
            k = int(m.sum())
            if k == 0:
                return {"label": label, "n": 0}
            sub = df[m]
            c = {"label": label, "n": k}
            for tgt in ("rise50", "touch50", "rise30", "crash30"):
                p = float(sub[tgt].mean())
                c[f"p_{tgt}"] = p
                c[f"lift_{tgt}"] = p / base[tgt] if base[tgt] > 0 else float("nan")
                # the hindsight direction: of every big rise, how many carried this signal? vs the signal's own frequency
                tot = int(df[tgt].sum())
                c[f"share_of_{tgt}"] = float(sub[tgt].sum() / tot) if tot else float("nan")
            c["signal_freq"] = k / n
            c["r60_mean"], c["r60_median"] = float(sub["r60"].mean()), float(sub["r60"].median())
            return c

        for k in FEATS:
            rk = ranks[k]
            res["features"][k] = {"top10": cell(rk >= 0.9, f"{k} top decile"), "bottom10": cell(rk <= 0.1, f"{k} bottom decile"),
                                  "top10_flat": cell((rk >= 0.9) & (df["flat"].to_numpy(float) > 0), f"{k} top decile & flat")}
        w = df["wyckoff"].to_numpy(bool)
        res["wyckoff"]["all"] = cell(w, "WYCKOFF")
        res["wyckoff"]["flat_only"] = cell(df["flat"].to_numpy(float) > 0, "flat only (control)")
        # permutation band on P(rise50 | wyckoff): shuffle the target within snapshot day
        if w.sum() >= 30:
            obs = res["wyckoff"]["all"]["p_rise50"]
            days = df["day"].to_numpy()
            y = df["rise50"].to_numpy(bool)
            hits = 0
            order = np.argsort(days, kind="stable")
            days_sorted = days[order]
            bounds = np.flatnonzero(np.diff(days_sorted)) + 1
            groups = np.split(order, bounds)
            for _ in range(DRAWS):
                ys = y.copy()
                for g in groups:
                    ys[g] = y[rng.permutation(g)]
                if ys[w].mean() >= obs:
                    hits += 1
            res["wyckoff"]["perm_p"] = (hits + 1) / (DRAWS + 1)
        out["tiers"][tname] = res
        wa = res["wyckoff"]["all"]
        print(f"  WYCKOFF n={wa.get('n')} P(rise50)={wa.get('p_rise50', float('nan')) * 100:.2f} % lift {wa.get('lift_rise50', float('nan')):.2f} "
              f"crash lift {wa.get('lift_crash30', float('nan')):.2f} share of rises {wa.get('share_of_rise50', float('nan')) * 100:.1f} % perm p {res['wyckoff'].get('perm_p')}", flush=True)

    # ------------------------------------------------------------------------------------------------- markdown
    def f(x, sign=False, dec=1):
        if x is None or not np.isfinite(x):
            return "-"
        return f"{x * 100:+.{dec}f} %" if sign else f"{x * 100:.{dec}f} %"

    Lns = [f"# IDX - akumulasi sebelum kenaikan tinggi: dua arah kondisional - {date.today()} - descriptive, 0 new trials (cumulative N = {N_TRIALS})", "",
           f"Panel {out['panel']['start']} -> {out['panel']['end']}, a snapshot every {STEP} trading days ({out['panel']['snapshots']} snapshots), features over the 60 days "
           f"ending the snapshot, outcome = the close 60 trading days later. 'Big rise' = +50 % held at day 60; 'touch' = the highest close in the 60 days >= +50 %; "
           f"'crash' = -30 % at day 60. Deciles are within-snapshot ranks.", ""]
    for tname, res in out["tiers"].items():
        b = res["base"]
        Lns += [f"## {tname} - {res['n']:,} name-snapshots ({res['names_per_snapshot']:.0f} names per snapshot)", "",
                f"Base rates: **P(+50 % held) = {f(b['rise50'], dec=2)}**, P(touch +50 %) = {f(b['touch50'], dec=2)}, P(+30 % held) = {f(b['rise30'], dec=2)}, "
                f"P(-30 %) = {f(b['crash30'], dec=2)}; mean 60-day return {f(res['r60_all']['mean'], True)}, median {f(res['r60_all']['median'], True)}.", "",
                "### Arah strategi: P(kenaikan | sinyal) - dan cerminnya, P(crash | sinyal)", "",
                "| signal | snapshots | P(+50 % held) | lift | P(touch +50 %) | lift | P(+30 %) | lift | P(-30 % crash) | lift | mean 60 d | median 60 d |",
                "|---|---|---|---|---|---|---|---|---|---|---|---|"]

        def row(c):
            if c.get("n", 0) == 0:
                return f"| {c['label']} | 0 | | | | | | | | | | |"
            return (f"| {c['label']} | {c['n']:,} | {f(c['p_rise50'], dec=2)} | {c['lift_rise50']:.2f} | {f(c['p_touch50'], dec=2)} | {c['lift_touch50']:.2f} | "
                    f"{f(c['p_rise30'], dec=2)} | {c['lift_rise30']:.2f} | {f(c['p_crash30'], dec=2)} | {c['lift_crash30']:.2f} | {f(c['r60_mean'], True)} | {f(c['r60_median'], True)} |")
        Lns.append(row(res["wyckoff"]["all"]))
        Lns.append(row(res["wyckoff"]["flat_only"]))
        for k in FEATS:
            Lns.append(row(res["features"][k]["top10"]))
            Lns.append(row(res["features"][k]["top10_flat"]))
        for k in FEATS:
            Lns.append(row(res["features"][k]["bottom10"]))
        pp = res["wyckoff"].get("perm_p")
        Lns += ["", f"WYCKOFF permutation p (target shuffled within snapshot day, {DRAWS} draws): {pp if pp is not None else 'n/a'}", "",
                "### Arah hindsight: dari semua kenaikan +50 %, berapa yang sebelumnya membawa sinyal ini? (vs seberapa sering sinyalnya muncul)", "",
                "| signal | signal frequency | share of +50 % risers carrying it | share of touch-+50 % | share of -30 % crashers | hindsight lift (risers / frequency) |",
                "|---|---|---|---|---|---|"]

        def hrow(c):
            if c.get("n", 0) == 0:
                return f"| {c['label']} | | | | | |"
            return (f"| {c['label']} | {f(c['signal_freq'])} | {f(c['share_of_rise50'])} | {f(c['share_of_touch50'])} | {f(c['share_of_crash30'])} | "
                    f"{c['share_of_rise50'] / c['signal_freq'] if c['signal_freq'] else float('nan'):.2f} |")
        Lns.append(hrow(res["wyckoff"]["all"]))
        for k in FEATS:
            Lns.append(hrow(res["features"][k]["top10"]))
        Lns.append("")
    path = os.path.join(HERE, f"IDX_ACCUM_REVERSE_{date.today().isoformat()}.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(Lns) + "\n")
    print("\n".join(Lns))
    print("wrote", path)
    if not args.no_store:
        from blackheart_ingest.idx import research_store as rs
        with psycopg.connect(dsn) as conn:
            liq = out["tiers"]["LIQ"]
            sid = rs.record_study(conn, "accum_reverse", dates[-1].date(),
                                  params={"trials": [], "n_trials_cumulative": N_TRIALS, "step": STEP, "L": L, "H": H, "features": list(FEATS), "seed": SEED, "descriptive": True},
                                  summary=json.loads(json.dumps(out, default=str)), names=[], report_path=path,
                                  note=f"LIQ base P(+50%)={liq['base']['rise50'] * 100:.2f}%, WYCKOFF n={liq['wyckoff']['all'].get('n')} lift {liq['wyckoff']['all'].get('lift_rise50', float('nan')):.2f}")
            print(f"study #{sid} stored")


if __name__ == "__main__":
    main()
