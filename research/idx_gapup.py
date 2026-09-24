#!/usr/bin/env python3
"""IDX menu 29f — the other side: what happens after a gap UP? (operator, 2026-09-23: "kalau yang gap up gimana?").

The gap-down fade rests on the opening auction overreacting to bad news. If that is what it is, the same overreaction
should follow good news, and the mirror trade - selling a gap up - should pay. Two arms, only one of them executable:

  buy_up   buy the open of a name that gapped UP and sell it into the same close. This is the trade the desk COULD do,
           and menu 29's gap_up arm (+2 %, mixed opens) already lost 301 bps a trade. Tested here on clean data at
           depths that match the fade's.
  fade_up  sell that open and buy it back at the close. This is the mirror of the deployed rule and is NOT executable
           for this account: IDX permits short selling only through a margin facility on an eligible-securities list,
           and the desk has none. It is measured to learn whether the overreaction is symmetric, not to trade it.

PRE-REGISTERED (declared before the run). 8 trials (cumulative 550 + 8 = 558).
  Data      exactly menu 29d's: the Yahoo cache 2015-2026 (years whose `open == close` share is under 30 %), rebased on
            its own close, survivors only, corporate actions and dividend ex-dates removed, gaps deeper than the day's
            auto-rejection band removed.
  Universe  60-day median value >= Rp 5 bn, previous close >= Rp 50, not locked at the open, K = 10 a day.
  Arms      gap >= +3 %, +5 %, +7 %, +10 %, each read both ways (buy_up and fade_up) = 8.
  Costs     buy at open + 1 tick, sell at close - 1 tick, 0.10 / 0.20 %. The short leg is charged the same two ticks and
            the same fees, and NO borrow cost - which flatters it; a real short would pay more.
  Reads     events, hit, mean/median net bps, daily t, and the same split at 2023-09-04 that menu 29d used.
  Bar       an arm is worth a follow-up only if its mean is >= +50 bps with a daily t >= 3 in BOTH eras.

READ-ONLY. INGEST_DB_DSN=... PYTHONIOENCODING=utf-8 blackheart-ingest/.venv/Scripts/python research/idx_gapup.py
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
import idx_gapfade_long as L  # noqa: E402

CUT = date(2023, 9, 4)
GAPS = (0.03, 0.05, 0.07, 0.10)
N_TRIALS_BEFORE = 550


def events_up(d: pd.DataFrame, dsn: str, gap_min: float) -> pd.DataFrame:
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT code, ex_date FROM idx.corporate_action")
        ca = {(r["code"], r["ex_date"]) if isinstance(r, dict) else (r[0], r[1]) for r in cur.fetchall()}
        cur.execute("SELECT code, ex_date FROM idx.dividend")
        ca |= {(r["code"], r["ex_date"]) if isinstance(r, dict) else (r[0], r[1]) for r in cur.fetchall()}
    d = d.copy()
    d["prev"] = d.groupby("code")["close"].shift(1)
    d["value"] = d["close"] * d["volume"]
    d["v60"] = d.groupby("code")["value"].transform(lambda s: s.rolling(60, min_periods=40).median()).groupby(d["code"]).shift(1)
    d["gap"] = d["open"] / d["prev"] - 1
    locked = (d["open"] == d["high"]) & (d["high"] == d["low"])
    ev = d[(d["gap"] >= gap_min) & (d["v60"] >= L.LIQ) & (d["prev"] >= L.PRICE_MIN) & ~locked].copy()
    ev = ev[np.array([(c, t) not in ca for c, t in zip(ev["code"], ev["trade_date"], strict=True)])]
    band = np.select([ev["prev"] <= 200, ev["prev"] <= 5000], [0.35, 0.25], 0.20)
    ev = ev[ev["gap"] <= band]
    return ev.sort_values(["trade_date", "v60"], ascending=[True, False]).groupby("trade_date").head(L.K).reset_index(drop=True)


def both_ways(ev: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    o, c = ev["open"].to_numpy(dtype=float), ev["close"].to_numpy(dtype=float)
    buy_at_open = (o + D.tick(o)) * (1 + D.FEE_BUY)
    sell_at_close = (c - D.tick(c)) * (1 - D.FEE_SELL)
    long_r = sell_at_close / buy_at_open - 1
    sell_at_open = (o - D.tick(o)) * (1 - D.FEE_SELL)           # the short leg, charged the same friction, no borrow
    buy_at_close = (c + D.tick(c)) * (1 + D.FEE_BUY)
    short_r = sell_at_open / buy_at_close - 1
    return long_r, short_r


def read(ev: pd.DataFrame, r: np.ndarray) -> dict:
    if len(r) < 20:
        return {"events": len(r), "verdict": "too few"}
    s = pd.Series(r, index=pd.to_datetime(ev["trade_date"]))
    day = s.groupby(s.index).mean()
    t = float(day.mean() / (day.std(ddof=1) / np.sqrt(len(day)))) if len(day) > 2 and day.std(ddof=1) > 0 else float("nan")
    return {"events": len(r), "hit": float((r > 0).mean()), "mean_bps": float(r.mean() * 1e4),
            "median_bps": float(np.median(r) * 1e4), "daily_t": t}


def run(dsn: str, out: str, store: bool, study_name: str) -> dict:
    d, _ = L.quality_gate(L.load_cache())
    res: dict = {"arms": {}}
    for g in GAPS:
        ev = events_up(d, dsn, g)
        lr, sr = both_ways(ev)
        for side, r in (("buy_up", lr), ("fade_up", sr)):
            key = f"{side} >= +{g*100:.0f} %"
            res["arms"][key] = {"all": read(ev, r),
                                "before": read(ev[ev["trade_date"] < CUT], r[(ev["trade_date"] < CUT).to_numpy()]),
                                "after": read(ev[ev["trade_date"] >= CUT], r[(ev["trade_date"] >= CUT).to_numpy()])}
            a = res["arms"][key]
            ok = all(a[e].get("mean_bps", -1) >= 50 and a[e].get("daily_t", 0) >= 3 for e in ("before", "after"))
            a["verdict"] = "worth a follow-up" if ok else "no"
    # the fade's own numbers, for the mirror
    dn = L.events(d, dsn, -0.07)
    res["reference_gap_down_7"] = read(dn, L.returns(dn))
    res["verdict"] = [k for k, v in res["arms"].items() if v["verdict"] == "worth a follow-up"]
    write(res, out)
    if store:
        from blackheart_ingest.idx import research_store as rs
        with psycopg.connect(dsn) as conn:
            res["study_id"] = rs.record_study(conn, study_name, L.END and date.fromisoformat(L.END),
                                              params={"trials": list(res["arms"]), "n_trials_cumulative": N_TRIALS_BEFORE + 8, "gaps": GAPS},
                                              summary=json.loads(json.dumps(res, default=str)), names=[], report_path=out,
                                              note=f"{len(res['verdict'])} of 8 worth a follow-up: {res['verdict'] or 'none'}")
    return res


def write(res: dict, path: str) -> None:
    ref = res["reference_gap_down_7"]
    L_ = ["# IDX menu 29f — what happens after a gap UP? — written 2026-09-23", "",
          "The fade assumes the opening auction overreacts. If so it should overreact to good news too. Same data as menu 29d",
          "(Yahoo cache 2015-2026, survivors, corporate actions removed); 8 trials, cumulative 558.", "",
          f"Reference — the deployed rule, gap <= -7 % bought at the open: {ref['events']} events, mean **{ref['mean_bps']:+.0f} bps**, "
          f"median {ref['median_bps']:+.0f}, hit {ref['hit']*100:.0f} %, daily t {ref['daily_t']:.1f}.", "",
          "## Buying the gap up, and selling it (the mirror trade)", "",
          "| arm | events | hit | mean | median | daily t | before 2023-09 | after | verdict |", "|---|---|---|---|---|---|---|---|---|"]
    for k, a in res["arms"].items():
        al, b, af = a["all"], a["before"], a["after"]
        if "mean_bps" not in al:
            L_.append(f"| {k} | {al['events']} | | | | | | | too few |")
            continue
        bs = f"{b['mean_bps']:+.0f} (t {b['daily_t']:.1f})" if "mean_bps" in b else "too few"
        as_ = f"{af['mean_bps']:+.0f} (t {af['daily_t']:.1f})" if "mean_bps" in af else "too few"
        L_.append(f"| {k} | {al['events']} | {al['hit']*100:.0f} % | **{al['mean_bps']:+.0f}** | {al['median_bps']:+.0f} | "
                  f"{al['daily_t']:.1f} | {bs} | {as_} | {a['verdict']} |")
    L_ += ["", "## Reading", "",
           f"- Worth a follow-up: {', '.join(res['verdict']) or 'none'}.",
           "- `fade_up` is charged two ticks and both fees but **no borrow cost**, and it is not executable by this account:",
           "  IDX allows short selling only through a margin facility on an eligible list, which the desk does not have. It is",
           "  measured to learn whether the overreaction is symmetric, not because it could be traded.",
           "- If buying gap ups loses and fading them wins by about the same amount, the asymmetry is not an edge one can",
           "  reach; if both lose, the opening auction is not systematically wrong about good news at all.", ""]
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(L_))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-store", action="store_true")
    ap.add_argument("--out", default="")
    ap.add_argument("--study-name", default="gapup")
    a = ap.parse_args()
    out = a.out or os.path.join(HERE, f"IDX_GAPUP_{date.today().isoformat()}.md")
    res = run(os.environ["INGEST_DB_DSN"], out, not a.no_store, a.study_name)
    print(json.dumps({"verdict": res["verdict"], "reference": res["reference_gap_down_7"],
                      "arms": {k: v["all"] for k, v in res["arms"].items()}, "study_id": res.get("study_id"), "report": out},
                     indent=1, default=str))


if __name__ == "__main__":
    main()
