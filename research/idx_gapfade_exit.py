#!/usr/bin/env python3
"""IDX menu 29c — does the gap-fade need a take-profit, or is the close enough? (operator, 2026-09-22: "ada ini nggak
target harga tp atau tunggu akhir hari saja?").

Menu 29b settled the entry (gap <= -7 % at the open, IDX opens only) and exits at the same day's CLOSE. It never tested an
intraday target or stop, because the fade was measured open-to-close. This does, from the daily bar's own high and low.

What a daily bar can and cannot answer. It knows whether a price was touched, not WHEN: a day whose high reaches the target
and whose low reaches the stop is ambiguous. Every bracket arm is therefore reported twice - pessimistic (assume the stop
came first) and optimistic (assume the target did) - and only the pessimistic reading is allowed to pass. A target-only or
stop-only arm has no ambiguity.

PRE-REGISTERED (declared before the run; nothing tuned afterwards). 9 trials (cumulative 535 + 9 = 544).
  Population   exactly menu 29b's g7: IDX-sourced opens, main board, v60 >= Rp 5 bn, previous close >= Rp 50, not locked,
               no corporate action or dividend ex-date that day, gap <= -7 %, up to K = 10 names a day by liquidity.
  Entry        the open + one tick, fee 0.10 % - unchanged.
  Exits        close      sell at the close - one tick (the deployed rule, the reference)
               tp2/3/5    a limit sell at the open x (1 + x) snapped to the tick, filled when the day's HIGH reaches it,
                          else the close; x = 2 %, 3 %, 5 %
               sl3/sl5    a stop at the open x (1 - y), filled one tick THROUGH it when the day's LOW reaches it (a stop
                          becomes a market order), else the close; y = 3 %, 5 %
               tp3_sl3, tp5_sl5   both, ambiguous days read pessimistically and optimistically
               trail_half sell at the close, but if the high reached +3 % take half the position there and half at the close
  Reads        trades, hit rate, mean and median net bps, the PAIRED difference against `close` on the same trades
               (mean, t), and the share of days where the target was reached at all.
  Bar          BETTER: paired mean >= +50 bps over the close exit AND t >= 2.0 on the paired difference. A bracket must
               clear it on the pessimistic reading.

READ-ONLY. INGEST_DB_DSN=... PYTHONIOENCODING=utf-8 blackheart-ingest/.venv/Scripts/python research/idx_gapfade_exit.py
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
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "blackheart-ingest", "src"))
import idx_daytrade as D  # noqa: E402

K = 10
GAP = -0.07
N_TRIALS_BEFORE = 535
ARMS = ["tp2", "tp3", "tp5", "sl3", "sl5", "tp3_sl3", "tp5_sl5", "trail_half"]


def tick_of(px: np.ndarray) -> np.ndarray:
    return D.tick(px)


def snap_up(px: np.ndarray) -> np.ndarray:
    t = tick_of(px)
    return np.ceil(px / t) * t


def snap_dn(px: np.ndarray) -> np.ndarray:
    t = tick_of(px)
    return np.floor(px / t) * t


def events(dsn: str) -> pd.DataFrame:
    """Menu 29b's g7 population, one row per event, with the day's open/high/low/close on the IDX basis."""
    with psycopg.connect(dsn) as conn:
        bars = D.load(conn)
        with conn.cursor() as cur:
            cur.execute("SELECT code, ex_date FROM idx.corporate_action")
            ca = {(r["code"], r["ex_date"]) if isinstance(r, dict) else (r[0], r[1]) for r in cur.fetchall()}
            cur.execute("SELECT code, ex_date FROM idx.dividend")
            dv = {(r["code"], r["ex_date"]) if isinstance(r, dict) else (r[0], r[1]) for r in cur.fetchall()}
    b = bars[(bars["open_src"] == "idx") & bars["open"].notna() & bars["close"].notna()].copy()
    b = b[b["main"] & (b["close"] >= 50)]
    b = b.sort_values(["code", "trade_date"])
    b["prev"] = b.groupby("code")["close"].shift(1)
    b["v60_prev"] = b.groupby("code")["v60"].shift(1)
    b["gap"] = b["open"] / b["prev"] - 1
    locked = (b["open"] == b["high"]) & (b["high"] == b["low"])
    ev = b[(b["gap"] <= GAP) & (b["v60_prev"] >= 5e9) & ~locked].copy()
    keep = np.array([(c, d) not in ca and (c, d) not in dv for c, d in zip(ev["code"], ev["trade_date"], strict=True)])
    ev = ev[keep]
    ev = ev.sort_values(["trade_date", "v60_prev"], ascending=[True, False]).groupby("trade_date").head(K)
    return ev.reset_index(drop=True)


def price_paths(ev: pd.DataFrame) -> dict[str, np.ndarray]:
    o, h, lo, c = (ev[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))
    buy = (o + tick_of(o)) * (1 + D.FEE_BUY)
    sell_close = (c - tick_of(c)) * (1 - D.FEE_SELL)
    return {"o": o, "h": h, "lo": lo, "c": c, "buy": buy, "sell_close": sell_close}


def arm_returns(p: dict[str, np.ndarray], arm: str, pessimistic: bool = True) -> np.ndarray:
    o, h, lo, buy, sell_close = p["o"], p["h"], p["lo"], p["buy"], p["sell_close"]
    out = sell_close.copy()
    if arm == "close":
        return out / buy - 1
    tp = {"tp2": 0.02, "tp3": 0.03, "tp5": 0.05, "tp3_sl3": 0.03, "tp5_sl5": 0.05, "trail_half": 0.03}.get(arm)
    sl = {"sl3": 0.03, "sl5": 0.05, "tp3_sl3": 0.03, "tp5_sl5": 0.05}.get(arm)
    tp_px = snap_up(o * (1 + tp)) if tp else None
    sl_px = snap_dn(o * (1 - sl)) if sl else None
    hit_tp = (h >= tp_px) if tp is not None else np.zeros_like(o, dtype=bool)
    hit_sl = (lo <= sl_px) if sl is not None else np.zeros_like(o, dtype=bool)
    if arm == "trail_half":                                                # half at the target, half at the close
        half = np.where(hit_tp, (tp_px - tick_of(tp_px)) * (1 - D.FEE_SELL), sell_close)
        return (0.5 * half + 0.5 * sell_close) / buy - 1
    sell = sell_close.copy()
    only_tp = hit_tp & ~hit_sl
    only_sl = hit_sl & ~hit_tp
    both = hit_tp & hit_sl
    if tp is not None:
        sell = np.where(only_tp, (tp_px - tick_of(tp_px)) * (1 - D.FEE_SELL), sell)
    if sl is not None:
        sell = np.where(only_sl, (sl_px - tick_of(sl_px)) * (1 - D.FEE_SELL), sell)   # a stop fills through the level
    if tp is not None and sl is not None:
        first = (sl_px - tick_of(sl_px)) if pessimistic else (tp_px - tick_of(tp_px))
        sell = np.where(both, first * (1 - D.FEE_SELL), sell)
    return sell / buy - 1


def read(ev: pd.DataFrame, base: np.ndarray, r: np.ndarray, extra: dict | None = None) -> dict:
    d = r - base
    t = float(d.mean() / (d.std(ddof=1) / np.sqrt(len(d)))) if len(d) > 2 and d.std(ddof=1) > 0 else float("nan")
    s = pd.Series(r, index=pd.to_datetime(ev["trade_date"]))
    day = s.groupby(s.index).mean()
    return {"trades": len(r), "hit": float((r > 0).mean()), "mean_bps": float(r.mean() * 1e4),
            "median_bps": float(np.median(r) * 1e4), "vs_close_bps": float(d.mean() * 1e4), "t_paired": t,
            "daily_t": float(day.mean() / (day.std(ddof=1) / np.sqrt(len(day)))) if len(day) > 2 and day.std(ddof=1) > 0 else float("nan"),
            **(extra or {})}


def run(dsn: str, out_path: str, store: bool, study_name: str) -> dict:
    ev = events(dsn)
    p = price_paths(ev)
    base = arm_returns(p, "close")
    o, h, lo = p["o"], p["h"], p["lo"]
    res: dict = {"desc": {"events": len(ev), "names": int(ev["code"].nunique()), "days": int(ev["trade_date"].nunique()),
                          "start": str(ev["trade_date"].min()), "end": str(ev["trade_date"].max()),
                          "reach_2pct": float((h >= o * 1.02).mean()), "reach_3pct": float((h >= o * 1.03).mean()),
                          "reach_5pct": float((h >= o * 1.05).mean()), "touch_-3pct": float((lo <= o * 0.97).mean()),
                          "touch_-5pct": float((lo <= o * 0.95).mean()),
                          "mean_high_bps": float((h / o - 1).mean() * 1e4), "mean_low_bps": float((lo / o - 1).mean() * 1e4)},
                 "arms": {"close": read(ev, base, base)}}
    for a in ARMS:
        if a in ("tp3_sl3", "tp5_sl5"):
            pess = arm_returns(p, a, pessimistic=True)
            opt = arm_returns(p, a, pessimistic=False)
            both = float(((h >= snap_up(o * (1 + (0.03 if a == "tp3_sl3" else 0.05)))) &
                          (lo <= snap_dn(o * (1 - (0.03 if a == "tp3_sl3" else 0.05))))).mean())
            res["arms"][a] = read(ev, base, pess, {"ambiguous_share": both,
                                                   "optimistic_bps": float(opt.mean() * 1e4),
                                                   "optimistic_vs_close_bps": float((opt - base).mean() * 1e4)})
        else:
            res["arms"][a] = read(ev, base, arm_returns(p, a))
    for a in ARMS:
        r = res["arms"][a]
        r["verdict"] = "BETTER" if (r["vs_close_bps"] >= 50 and r["t_paired"] >= 2.0) else "no"
    res["verdict"] = [a for a in ARMS if res["arms"][a]["verdict"] == "BETTER"]
    write(res, out_path)
    if store:
        from blackheart_ingest.idx import research_store as rs
        with psycopg.connect(dsn) as conn:
            sid = rs.record_study(conn, study_name, date.fromisoformat(res["desc"]["end"]),
                                  params={"trials": ARMS, "n_trials_cumulative": N_TRIALS_BEFORE + len(ARMS), "gap": GAP, "K": K},
                                  summary=json.loads(json.dumps(res, default=str)), names=[], report_path=out_path,
                                  note=f"{len(res['verdict'])} of {len(ARMS)} beat selling at the close: {res['verdict'] or 'none'}")
            res["study_id"] = sid
    return res


def write(res: dict, path: str) -> None:
    d = res["desc"]
    L = [f"# IDX menu 29c — a take-profit on the gap-fade, or just the close? — {d['start']} -> {d['end']}", "",
         f"{d['events']} events, {d['names']} names, {d['days']} days (menu 29b's g7 population: IDX opens, gap <= -7 %, liquid, "
         "no corporate action). Entry unchanged: the open plus a tick. Pre-registered in `research/idx_gapfade_exit.py`; 9 trials (cumulative 544).", "",
         "## What the day does after the open", "",
         f"- the high reaches +2 % on {d['reach_2pct']*100:.0f} % of days, +3 % on {d['reach_3pct']*100:.0f} %, +5 % on {d['reach_5pct']*100:.0f} %",
         f"- the low reaches -3 % on {d['touch_-3pct']*100:.0f} % of days, -5 % on {d['touch_-5pct']*100:.0f} %",
         f"- mean high {d['mean_high_bps']:+.0f} bps above the open, mean low {d['mean_low_bps']:+.0f} bps below it", "",
         "## Exits", "",
         "| exit | trades | hit | mean | median | vs close | t (paired) | verdict |", "|---|---|---|---|---|---|---|---|"]
    for a, r in res["arms"].items():
        v = r.get("verdict", "reference")
        L.append(f"| {a} | {r['trades']} | {r['hit']*100:.0f} % | **{r['mean_bps']:+.0f}** | {r['median_bps']:+.0f} | "
                 f"{r['vs_close_bps']:+.0f} | {r['t_paired']:.1f} | {v} |" if a != "close" else
                 f"| close (deployed) | {r['trades']} | {r['hit']*100:.0f} % | **{r['mean_bps']:+.0f}** | {r['median_bps']:+.0f} | — | — | reference |")
    amb = [a for a in ARMS if "ambiguous_share" in res["arms"][a]]
    if amb:
        L += ["", "## The brackets, read both ways (the bar uses the pessimistic one)", "",
              "| bracket | ambiguous days | pessimistic vs close | optimistic vs close |", "|---|---|---|---|"]
        for a in amb:
            r = res["arms"][a]
            L.append(f"| {a} | {r['ambiguous_share']*100:.0f} % | {r['vs_close_bps']:+.0f} bps | {r['optimistic_vs_close_bps']:+.0f} bps |")
    L += ["", "## Reading", "", f"- Beat the close: {', '.join(res['verdict']) or 'none'}.",
          "- A target caps the right tail, which is where this rule's money is; a stop turns the deepest intraday dip into a",
          "  realised loss on a day that often closes higher. The table says which of those costs more.", ""]
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(L))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-store", action="store_true")
    ap.add_argument("--out", default="")
    ap.add_argument("--study-name", default="gapfade_exit")
    a = ap.parse_args()
    out = a.out or os.path.join(HERE, f"IDX_GAPFADE_EXIT_{date.today().isoformat()}.md")
    res = run(os.environ["INGEST_DB_DSN"], out, not a.no_store, a.study_name)
    print(json.dumps({"desc": res["desc"], "arms": {k: {x: v.get(x) for x in ("trades", "mean_bps", "vs_close_bps", "t_paired", "verdict")}
                                                    for k, v in res["arms"].items()}, "study_id": res.get("study_id"), "report": out}, indent=1, default=str))


if __name__ == "__main__":
    main()
