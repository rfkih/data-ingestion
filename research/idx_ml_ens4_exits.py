#!/usr/bin/env python3
"""IDX menu ML-9 - exits on the LIVE ML sleeve (ens4) (operator, 2026-09-26: "how it take profit or stop loss?" ... "yes please").

The live ML sleeve (book live-fae554, combo_book ml.confirm_rules = ens4) has no stop and no take-profit: a holding is sold only
when its score turns negative and a better name pays the swap, after 60 sessions, or when it has no score/bar. The re-run of
#162 on corrected data (#254) found fixed and trailing stops that pass the bar - on the SINGLE +5 %/10 d confirmation rule, not on
ens4, and with a mixed pattern (-5 and -20 % pass, -10 and -30 % do not). Take-profits were never tested on ML.

PRE-REGISTERED 2026-09-26 before any result of this script was seen (10 trials; cumulative 975 + 10 = 985):
  Base = ens4 exactly as study #261 (ML-8 re-run): e5|2|3|10 on LIQ from 2022-01, four confirmation rule-books
         (+5 %/10 d, +8 %/10 d, +10 %/10 d, +8 %/5 d), each with a quarter of the capital; K 10, margin 2 x cost, EMA 3,
         max hold 60, closing offer/bid + fees. SANITY GATE: the base here must reproduce #261's ens4 (CAGR, Sharpe, mDD) to 1e-9,
         else the script stops.
  Arms - one exit rule applied identically inside all four rule-books, signal at the close, sold at the next close:
    stop5 stop10 stop15 stop20     close <= (1 - x) x fill close
    trail10 trail15 trail20        close <= (1 - x) x highest close since the fill
    tp20 tp30 tp50                 close >= (1 + x) x fill close (take-profit)
READING RULE:
  BETTER      Sharpe >= base + 0.15, mDD not deeper, CAGR >= 0.8 x base (as #162/#254)
  and, for a BETTER arm, every robustness check:
    neighbours  the same exit at 0.7x and 1.3x the level (rounded to 0.5 pt) both keep Sharpe > base and mDD not deeper
    halves      Sharpe >= base in 2022-01..2024-04 AND in 2024-05..end
    ex-2025     Sharpe with 2025 removed >= the base's with 2025 removed
    placebo     the arm on 20 books with scores shuffled within the day: real Sharpe above the 95th percentile
  RECOMMENDED = BETTER and all four. Anything else is reported and kept off.
READ-ONLY on the book; one idx.study row (name ml_ens4_exits). Needs IDX_ML_CACHE (the final re-run cache).
"""
from __future__ import annotations

import os
import pickle
import sys
from datetime import date

import numpy as np
import pandas as pd
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blackheart-ingest", "src"))
import idx_ml_costaware as C  # noqa: E402
import idx_ml_strategy as M  # noqa: E402
from blackheart_ingest.idx import research_store as rs  # noqa: E402
from blackheart_ingest.idx.ml import common  # noqa: E402

N_BEFORE = 975
STUDY = "ml_ens4_exits"
ENS4 = [(0.05, 10), (0.08, 10), (0.10, 10), (0.08, 5)]
K, MARGIN, SPAN = 10, 2.0, 3
REF_STUDY = 261                                     # ens4 on the final re-run data: the sanity gate
ARMS = {"stop5": dict(stop=0.05), "stop10": dict(stop=0.10), "stop15": dict(stop=0.15), "stop20": dict(stop=0.20),
        "trail10": dict(trail=0.10), "trail15": dict(trail=0.15), "trail20": dict(trail=0.20),
        "tp20": dict(tp=0.20), "tp30": dict(tp=0.30), "tp50": dict(tp=0.50)}
HALF_SPLIT = date(2024, 5, 1)


def book(A, mask, e, k, c_in, c_out, margin, *, wait, stop=None, trail=None, tp=None, t_start=0, max_hold=C.MAX_HOLD):
    """idx_ml_confirm_stops.book with a take-profit added; identical otherwise (so the base reproduces the confirmation book)."""
    T, N = A.shape
    ret = np.nan_to_num(np.vstack([np.full((1, N), np.nan), A[1:] / A[:-1] - 1]))
    R = np.zeros(T)
    w = 1.0 / k
    held: dict[int, dict] = {}
    watch: dict[int, dict] = {}
    pend_sell: list[tuple[int, str]] = []
    pend_buy: list[int] = []
    log = []
    rt = c_in + c_out
    watch_sig: dict[int, int] = {}
    for t in range(t_start, T - 1):
        for j, why in pend_sell:
            if j in held:
                p = held.pop(j)
                R[t] += w * (ret[t, j] - c_out[t, j])
                log.append({"j": j, "t_in": p["t"], "t_out": t, "why": why,
                            "net": (A[t, j] / A[p["t"], j]) * (1 - c_out[t, j]) / (1 + c_in[p["t"], j]) - 1, "hold": t - p["t"]})
        for j in pend_buy:
            if j not in held and len(held) < k and not np.isnan(A[t, j]):
                held[j] = {"t": t, "t_sig": watch_sig.get(j, t), "peak": A[t, j]}
                R[t] -= w * c_in[t, j]
        for j, p in held.items():
            if all(j != s for s, _ in pend_sell):
                R[t] += w * ret[t, j]
            if not np.isnan(A[t, j]):
                p["peak"] = max(p["peak"], A[t, j])
        pend_sell, pend_buy = [], []
        watch_sig = {j: v["t"] for j, v in watch.items()}
        ok = mask[t] & np.isfinite(e[t]) & ~np.isnan(A[t]) & ~np.isnan(A[t + 1])
        cand = np.flatnonzero(ok)
        order = cand[np.argsort(-e[t, cand], kind="stable")] if len(cand) else cand
        best = float(e[t, order[0]]) if len(order) else -np.inf
        for j, p in held.items():
            px = A[t, j]
            if (t - p["t"]) >= max_hold:
                pend_sell.append((j, "max_hold"))
            elif np.isnan(A[t + 1, j]) or not np.isfinite(e[t, j]):
                pend_sell.append((j, "gone"))
            elif stop is not None and not np.isnan(px) and px <= (1 - stop) * A[p["t"], j]:
                pend_sell.append((j, "stop"))
            elif trail is not None and not np.isnan(px) and px <= (1 - trail) * p["peak"]:
                pend_sell.append((j, "trail"))
            elif tp is not None and not np.isnan(px) and px >= (1 + tp) * A[p["t"], j]:
                pend_sell.append((j, "tp"))
            elif e[t, j] < 0 and best - e[t, j] > margin * rt[t, j]:
                pend_sell.append((j, "swap"))
        for j in list(watch):
            v = watch[j]
            if t > v["until"] or j in held:
                watch.pop(j)
                continue
            if ok[j] and e[t, j] > margin * rt[t, j] and A[t, j] >= (1 + wait[0]) * v["ref"]:
                pend_buy.append(j)
                watch_sig[j] = v["t"]
                watch.pop(j)
        free = k - (len(held) - len(pend_sell)) - len(pend_buy) - len(watch)
        for j in order:
            if free <= 0:
                break
            if j in held or any(j == s for s, _ in pend_sell) or j in watch or j in pend_buy:
                continue
            if e[t, j] > margin * rt[t, j]:
                watch[j] = {"t": t, "ref": A[t, j], "until": t + wait[1]}
                free -= 1
    return R, pd.DataFrame(log)


def sharpe(r: np.ndarray) -> float:
    return float(r.mean() / r.std() * np.sqrt(252)) if len(r) > 1 and r.std() > 0 else float("nan")


def main() -> int:
    dsn = os.environ["INGEST_DB_DSN"]
    P = pickle.load(open(os.environ["IDX_ML_CACHE"], "rb"))
    P = P[P["d"] >= "2021-06-01"].copy()
    dates = M.wide(P, "close").index
    codes = M.wide(P, "close").columns
    g = lambda c: M.wide(P, c).reindex(index=dates, columns=codes)  # noqa: E731
    A = g("ac").to_numpy(float)
    c_in, c_out = M.costs(g("close").to_numpy(float), g("offer").to_numpy(float), g("bid").to_numpy(float))
    liq = g("liq").fillna(False).astype(bool).to_numpy()
    S = g("s5").to_numpy(float)
    e5_raw = S - np.nanmedian(np.where(liq, S, np.nan), axis=1, keepdims=True)
    e5 = C.ema(e5_raw, SPAN)
    t0 = int(np.searchsorted(dates, np.datetime64(date(2022, 1, 1))))
    th = int(np.searchsorted(dates, np.datetime64(HALF_SPLIT)))
    not25 = np.asarray(dates.year != 2025)

    def ens(e, **kw):
        runs = [book(A, liq, e, K, c_in, c_out, MARGIN, wait=r, t_start=t0, **kw) for r in ENS4]
        return np.mean([x[0] for x in runs], axis=0), pd.concat([x[1] for x in runs], ignore_index=True)

    def describe(R, log):
        st = M.stats(R, dates, t0)
        st["sharpe_h1"], st["sharpe_h2"] = sharpe(R[t0:th]), sharpe(R[th:])
        st["sharpe_ex2025"] = sharpe(R[t0:][not25[t0:]])
        st["trades"] = len(log)
        st["win"] = float((log["net"] > 0).mean()) if len(log) else float("nan")
        st["avg"] = float(log["net"].mean()) if len(log) else float("nan")
        st["exits"] = {k: {"n": int(v["size"]), "avg": float(v["mean"])} for k, v in log.groupby("why")["net"].agg(["size", "mean"]).iterrows()} if len(log) else {}
        return st

    R0, L0 = ens(e5)
    base = describe(R0, L0)
    with psycopg.connect(dsn) as conn:
        ref = conn.execute("SELECT summary->'arms'->'ens4' FROM idx.study WHERE id = %s", (REF_STUDY,)).fetchone()[0]
    gate = {k: (base[k], float(ref[k])) for k in ("cagr", "sharpe", "mdd")}
    if any(abs(a - b) > 1e-9 for a, b in gate.values()):
        M.log(f"SANITY GATE FAILED: base {gate} does not reproduce #{REF_STUDY} ens4")
        return 2
    M.log(f"sanity gate ok: base reproduces #{REF_STUDY} ens4 ({base['cagr'] * 100:.2f} % / {base['sharpe']:.3f} / {base['mdd'] * 100:.2f} %)")

    res: dict[str, dict] = {}
    for arm, kw in ARMS.items():
        R, L = ens(e5, **kw)
        r = describe(R, L)
        why = []
        if r["sharpe"] < base["sharpe"] + 0.15:
            why.append(f"sharpe {r['sharpe']:.2f} < base {base['sharpe']:.2f} + 0.15")
        if r["mdd"] < base["mdd"]:
            why.append("mdd deeper")
        if r["cagr"] < 0.8 * base["cagr"]:
            why.append("cagr < 80 % base")
        r["better"] = not why
        r["verdict"] = "BETTER" if not why else "no: " + "; ".join(why)
        res[arm] = r
        M.log(f"{arm:<8} CAGR {r['cagr'] * 100:6.1f} % Sharpe {r['sharpe']:5.2f} mDD {r['mdd'] * 100:6.1f} % h1/h2 {r['sharpe_h1']:.2f}/{r['sharpe_h2']:.2f} "
              f"ex25 {r['sharpe_ex2025']:.2f} trades {r['trades']} | {r['verdict']}")

    # robustness, only for BETTER arms
    rng = np.random.default_rng(M.SEED)
    shuffled = []
    for arm, r in res.items():
        if not r["better"]:
            continue
        (key, x), = ARMS[arm].items()
        nb = {}
        for f in (0.7, 1.3):
            lvl = round(x * f * 200) / 200
            Rn, Ln = ens(e5, **{key: lvl})
            sn = describe(Rn, Ln)
            nb[f"{key}{lvl * 100:g}"] = {"cagr": sn["cagr"], "sharpe": sn["sharpe"], "mdd": sn["mdd"],
                                        "ok": bool(sn["sharpe"] > base["sharpe"] and sn["mdd"] >= base["mdd"])}
        r["neighbours"] = nb
        r["neighbours_ok"] = all(v["ok"] for v in nb.values())
        r["halves_ok"] = bool(r["sharpe_h1"] >= base["sharpe_h1"] and r["sharpe_h2"] >= base["sharpe_h2"])
        r["ex2025_ok"] = bool(r["sharpe_ex2025"] >= base["sharpe_ex2025"])
        if not shuffled:                                       # the same 20 shuffles for every arm
            for _ in range(M.N_PLACEBO):
                shf = e5_raw.copy()
                for t in range(t0, len(dates)):
                    idx = np.flatnonzero(liq[t] & np.isfinite(shf[t]))
                    if len(idx) > 1:
                        shf[t, idx] = shf[t, rng.permutation(idx)]
                shuffled.append(C.ema(shf, SPAN))
        pl = [sharpe(ens(es, **ARMS[arm])[0][t0:]) for es in shuffled]
        r["placebo"] = {"n": len(pl), "pct": float((np.array(pl) < r["sharpe"]).mean() * 100), "mean": float(np.mean(pl)), "max": float(np.max(pl))}
        r["placebo_ok"] = r["placebo"]["pct"] >= 95.0
        r["recommended"] = bool(r["neighbours_ok"] and r["halves_ok"] and r["ex2025_ok"] and r["placebo_ok"])
        M.log(f"{arm}: neighbours {nb} ok={r['neighbours_ok']} | halves ok={r['halves_ok']} | ex-2025 ok={r['ex2025_ok']} | "
              f"placebo pct {r['placebo']['pct']:.0f} | RECOMMENDED={r['recommended']}")
    for r in res.values():
        r.setdefault("recommended", False)

    n_trials = N_BEFORE + len(ARMS)
    yrs = list(base["by_year"])
    L = [f"# IDX menu ML-9 - exits on the live ML sleeve (ens4) - {date.today()} - {len(ARMS)} trials, cumulative N = {n_trials}", "",
         f"Base = ens4 as study #{REF_STUDY} (reproduced exactly: {base['cagr'] * 100:.2f} % / {base['sharpe']:.3f} / {base['mdd'] * 100:.2f} %). "
         "Pre-registered rule and robustness checks in the script's docstring.", "",
         "| arm | CAGR | Sharpe | mDD | Sharpe H1 / H2 | Sharpe ex-2025 | trades | win | avg net | " + " | ".join(str(y) for y in yrs) + " | verdict | recommended |",
         "|---|---|---|---|---|---|---|---|---|" + "---|" * len(yrs) + "---|---|"]
    for arm, r in {"base": base, **res}.items():
        L.append(f"| {arm} | {r['cagr'] * 100:+.1f} % | {r['sharpe']:.2f} | {r['mdd'] * 100:.0f} % | {r['sharpe_h1']:.2f} / {r['sharpe_h2']:.2f} | {r['sharpe_ex2025']:.2f} | "
                 f"{r['trades']} | {r['win'] * 100:.0f} % | {r['avg'] * 100:+.2f} % | " + " | ".join(f"{r['by_year'][y] * 100:+.0f} %" for y in yrs)
                 + f" | {r.get('verdict', 'reference')} | {'YES' if r.get('recommended') else ('-' if arm == 'base' else 'no')} |")
    L += ["", "## Robustness of the BETTER arms", "", "| arm | neighbours | halves | ex-2025 | placebo pct | recommended |", "|---|---|---|---|---|---|"]
    for arm, r in res.items():
        if r["better"]:
            nbs = ", ".join(f"{k}: {v['sharpe']:.2f}/{v['mdd'] * 100:.0f} % {'ok' if v['ok'] else 'FAIL'}" for k, v in r["neighbours"].items())
            L.append(f"| {arm} | {nbs} | {'ok' if r['halves_ok'] else 'FAIL'} | {'ok' if r['ex2025_ok'] else 'FAIL'} | {r['placebo']['pct']:.0f} | {'YES' if r['recommended'] else 'no'} |")
    L += ["", "## Exit anatomy", "", "| arm | " + " | ".join(["swap", "max_hold", "gone", "stop", "trail", "tp"]) + " |", "|---|---|---|---|---|---|---|"]
    for arm, r in {"base": base, **res}.items():
        L.append(f"| {arm} | " + " | ".join(f"{r['exits'][k]['n']} ({r['exits'][k]['avg'] * 100:+.1f} %)" if k in r["exits"] else "-" for k in ["swap", "max_hold", "gone", "stop", "trail", "tp"]) + " |")
    rec = [a for a, r in res.items() if r["recommended"]]
    L += ["", "## Verdict", "", f"BETTER: {', '.join(a for a, r in res.items() if r['better']) or 'none'}; RECOMMENDED: {', '.join(rec) or 'none'}."]
    text = "\n".join(L)
    out = os.path.join(HERE, f"IDX_ML_ENS4_EXITS_{date.today()}.md")
    open(out, "w", encoding="utf-8").write(text + "\n")
    print(text)
    with psycopg.connect(dsn) as conn:
        sid = rs.record_study(conn, STUDY, date.today(),
                              params={"trials": list(ARMS), "n_trials_cumulative": n_trials, "base": f"ens4 as #{REF_STUDY}", "rules": ENS4,
                                      "reading_rule": "BETTER + neighbours + halves + ex-2025 + placebo95"},
                              summary=common.plain({"base": base, "arms": res, "recommended": rec}), names=[], report_path=out,
                              note=f"ML-9 exits on ens4: BETTER {[a for a, r in res.items() if r['better']]}, RECOMMENDED {rec}")
        conn.commit()
    M.log(f"study #{sid} stored")
    return 0


if __name__ == "__main__":
    sys.exit(main())
