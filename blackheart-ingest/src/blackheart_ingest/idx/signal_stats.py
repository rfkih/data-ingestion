"""Historical statistics behind each screener criteria (open-research plan phase 2; spec §06).

One row per (criteria, bucket, horizon): what happened to the whole group of names that met the criteria in the recorded
research - n, hit rate, median, mean, the tail (share losing more than half, or the book's worst drawdown), per year, and
where the number comes from (``study_id`` or the report path). Rules, in code: nothing is written without a source; a
row without n >= 50 is not written; horizons are the ones the study measured, never extrapolated.

Sources (all point in time, costs included where the study had them):
  trend_breakout   idx.study ``trend_exit`` (#44: 2020-26 per-trade stats of the deployed rule on small / LIQ) and
                   ``trend_2008`` (#46: the same rule 2005-2019 on the Yahoo survivors file)
  turnaround       idx.study ``doublers`` (#2) + its panel csv (research-scratch/idx-screen/doublers_panel_*.csv) for the
                   per-year and per-bucket slices; horizons 12 and 24 months, targets "touched 2x" and "still 2x"
  value_strict     research-scratch/idx-screen/value_quality_2020_results.json (rev.3 strict composite, May calendar)
  quality8         no backtest yet -> no row (the UI says so)
"""
from __future__ import annotations

import csv
import glob
import json
import logging
import os
from datetime import date
from pathlib import Path
from typing import Any

import psycopg
import psycopg.types.json

from .card import _rows

logger = logging.getLogger(__name__)
MIN_N = 50
ROOT = Path(__file__).resolve().parents[4]                  # C:/Project (the umbrella) when run from the checkout
SCRATCH = ROOT / "research-scratch" / "idx-screen"
LIQ = 5e9


def _study(conn: psycopg.Connection, name: str) -> dict[str, Any] | None:
    r = _rows(conn, "SELECT id, summary, report_path FROM idx.study WHERE name = %s ORDER BY id DESC LIMIT 1", (name,), ["id", "summary", "report_path"])
    if not r:
        return None
    s = r[0]["summary"]
    r[0]["summary"] = json.loads(s) if isinstance(s, str) else s
    return r[0]


def _trend_rows(conn: psycopg.Connection) -> list[dict[str, Any]]:
    out = []
    ex = _study(conn, "trend_exit")
    if ex:
        for uni in ("small", "LIQ"):
            s = ex["summary"].get("refs", {}).get(uni)
            if s and s.get("n", 0) >= MIN_N:
                out.append({"criteria": "trend_breakout", "bucket": uni, "horizon_days": 0, "sample_from": date(2020, 1, 2), "sample_to": date(2026, 9, 16),
                            "n": int(s["n"]), "hit": s["hit"], "median": s.get("med_net"), "mean": s.get("avg_net"), "p_loss50": None, "mdd_book": s["mdd"],
                            "extra": {k: s.get(k) for k in ("hold", "payoff", "cagr", "sharpe", "capture", "mfe", "tstat", "total")} | {"exit": "trail 10 % from the peak close", "K": 10},
                            "by_year": {str(k): v for k, v in (s.get("years") or {}).items()}, "study_id": ex["id"], "source": ex["report_path"]})
    old = _study(conn, "trend_2008")
    if old:
        for uni in ("small", "LIQ"):
            s = old["summary"].get("results", {}).get(uni)
            if s and s.get("n", 0) >= MIN_N:
                out.append({"criteria": "trend_breakout", "bucket": f"{uni}:2005-2019", "horizon_days": 0, "sample_from": date(2005, 1, 3), "sample_to": date(2019, 12, 30),
                            "n": int(s["n"]), "hit": s["hit"], "median": s.get("med_net"), "mean": s.get("avg_net"), "p_loss50": None, "mdd_book": s["mdd"],
                            "extra": {k: s.get(k) for k in ("hold", "payoff", "cagr", "sharpe", "capture", "mfe", "tstat", "total")}
                            | {"exit": "trail 10 % from the peak close", "K": 10, "data": "Yahoo survivors file (450 names listed today): level generous"},
                            "by_year": {str(k): v for k, v in (s.get("years") or {}).items()}, "study_id": old["id"], "source": old["report_path"]})
    return out


def _panel_path() -> Path | None:
    files = sorted(glob.glob(str(SCRATCH / "doublers_panel_*.csv")))
    return Path(files[-1]) if files else None


def _f(v: str) -> float | None:
    try:
        return float(v) if v not in ("", "nan", "None") else None
    except ValueError:
        return None


def _turnaround_rows(conn: psycopg.Connection) -> list[dict[str, Any]]:
    st = _study(conn, "doublers")
    if not st:
        return []
    out = []
    base = st["summary"].get("base", {})
    for target, horizon in (("touched2x_24m", 500), ("end2x_24m", 500), ("touched2x_12m", 250), ("end2x_12m", 250)):
        b = base.get(target)
        if b and b.get("n", 0) >= MIN_N:
            out.append({"criteria": "universe", "bucket": target, "horizon_days": horizon, "sample_from": date(2020, 5, 29), "sample_to": date(2025, 8, 29),
                        "n": int(b["n"]), "hit": b["rate"], "median": None, "mean": None, "p_loss50": None, "mdd_book": None,
                        "extra": {"target": target, "what": "base rate of the liquid universe"},
                        "by_year": {y: v["rate"] for y, v in (b.get("by_year") or {}).items()}, "study_id": st["id"], "source": st["report_path"]})
    panel = _panel_path()
    if panel is None:
        d = next((x for x in st["summary"].get("screens", []) if x["screen"].startswith("D")), None)
        if d:
            for target, horizon in (("touched2x_24m", 500), ("end2x_24m", 500), ("touched2x_12m", 250), ("end2x_12m", 250)):
                t = d.get(target)
                if t and t.get("n", 0) >= MIN_N:
                    out.append({"criteria": "turnaround", "bucket": f"all:{target}", "horizon_days": horizon, "sample_from": date(2020, 5, 29), "sample_to": date(2024, 8, 30),
                                "n": int(t["n"]), "hit": t["hit"], "median": t.get("med_ret"), "mean": t.get("mean_ret"), "p_loss50": t.get("loss_gt50"), "mdd_book": None,
                                "extra": {"target": target, "base": t.get("base"), "lift": t.get("lift"), "consistency": t.get("consistency"), "by_year": "panel not on this host"},
                                "by_year": {}, "study_id": st["id"], "source": st["report_path"]})
        return out
    with open(panel, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    members = [r for r in rows if r.get("turnaround") in ("True", "1", "true") and (_f(r.get("q_rev_yoy") or "") or 0) > 0 and (_f(r.get("v60") or "") or 0) >= LIQ]

    def bucket(r: dict[str, str]) -> str:
        mcap, mom = _f(r.get("mcap") or ""), _f(r.get("mom") or "")
        band = "?" if mcap is None else ("<3T" if mcap < 3e12 else ("3-20T" if mcap < 20e12 else ">20T"))
        m = "mom:?" if mom is None else ("mom:<=150" if mom <= 1.5 else "mom:>150")
        return f"mcap:{band},{m}"

    def stats(sub: list[dict[str, str]], target: str, ret: str) -> dict[str, Any] | None:
        have = [r for r in sub if r.get(target) not in ("", None) and r.get(ret) not in ("", None)]
        if len(have) < MIN_N:
            return None
        hits = [r[target] in ("True", "1", "true") for r in have]
        rets = sorted(_f(r[ret]) or 0.0 for r in have)
        by: dict[str, list[bool]] = {}
        for r, h in zip(have, hits, strict=True):
            by.setdefault(r["D"][:4], []).append(h)
        return {"n": len(have), "hit": sum(hits) / len(hits), "median": rets[len(rets) // 2], "mean": sum(rets) / len(rets),
                "p_loss50": sum(1 for x in rets if x <= -0.5) / len(rets), "by_year": {y: sum(v) / len(v) for y, v in sorted(by.items())}}

    groups: dict[str, list[dict[str, str]]] = {"all": members}
    for r in members:
        groups.setdefault(bucket(r), []).append(r)
    for bk, sub in groups.items():
        for target, ret, horizon in (("touched2x_24m", "ret_24m", 500), ("end2x_24m", "ret_24m", 500), ("touched2x_12m", "ret_12m", 250), ("end2x_12m", "ret_12m", 250)):
            s = stats(sub, target, ret)
            if s:
                out.append({"criteria": "turnaround", "bucket": f"{bk}:{target}", "horizon_days": horizon, "sample_from": date(2020, 5, 29),
                            "sample_to": date(2024, 8, 30) if horizon == 500 else date(2025, 8, 29), "n": s["n"], "hit": s["hit"], "median": s["median"], "mean": s["mean"],
                            "p_loss50": s["p_loss50"], "mdd_book": None, "extra": {"target": target, "screen": "D: prior-year loss -> profit, YTD revenue growing, liquid"},
                            "by_year": s["by_year"], "study_id": st["id"], "source": str(panel.relative_to(ROOT)) if panel.is_relative_to(ROOT) else str(panel)})
    return out


def _value_rows(conn: psycopg.Connection) -> list[dict[str, Any]]:
    f = SCRATCH / "value_quality_2020_results.json"
    if not f.exists():
        return []
    d = json.loads(f.read_text(encoding="utf-8"))
    out = []
    for month, label in (("5", "May"), ("8", "Aug"), ("11", "Nov")):
        s = (d.get("months") or {}).get(month, {}).get("summary", {}).get("composite_q")
        reb = (d.get("months") or {}).get(month, {}).get("rebalances") or []
        if not s or not reb:
            continue
        n = 10 * len(reb)                                             # ten names per rebalance
        if n < MIN_N:
            continue
        out.append({"criteria": "value_strict", "bucket": f"all:{label}", "horizon_days": 250, "sample_from": date.fromisoformat(reb[0]), "sample_to": date(2026, 9, 12),
                    "n": n, "hit": None, "median": None, "mean": None, "p_loss50": None, "mdd_book": -abs(s["mdd_pct"]) / 100,
                    "extra": {"cagr": s["cagr_pct"] / 100, "sharpe": s["sharpe"], "total": s["total_pct"] / 100, "calendar": label, "rebalances": reb,
                              "periods": s.get("periods"), "bench_cagr": (d.get("benchmarks") or {}).get("COMPOSITE", {}).get("cagr_pct", 0) / 100,
                              "what": "book of ten names, equal weight, rebalanced yearly; costs and net dividends included"},
                    "by_year": {y: v / 100 for y, v in (s.get("yearly") or {}).items()}, "study_id": None, "source": "research/IDX_VALUE_QUALITY_2020_2026-09-14.md"})
    return out


def collect(conn: psycopg.Connection) -> list[dict[str, Any]]:
    return _trend_rows(conn) + _turnaround_rows(conn) + _value_rows(conn)


def refresh(conn: psycopg.Connection) -> dict[str, Any]:
    rows = collect(conn)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM idx.signal_stats")
        for r in rows:
            cur.execute("""INSERT INTO idx.signal_stats (criteria, bucket, horizon_days, sample_from, sample_to, n, hit, median, mean, p_loss50, mdd_book, extra, by_year, study_id, source)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                        (r["criteria"], r["bucket"], r["horizon_days"], r["sample_from"], r["sample_to"], r["n"], r["hit"], r["median"], r["mean"], r["p_loss50"],
                         r["mdd_book"], psycopg.types.json.Jsonb(r["extra"]), psycopg.types.json.Jsonb(r["by_year"]), r["study_id"], r["source"]))
    conn.commit()
    by = {}
    for r in rows:
        by[r["criteria"]] = by.get(r["criteria"], 0) + 1
    logger.info("signal_stats refreshed: %d rows %s", len(rows), by)
    return {"rows": len(rows), "by_criteria": by, "panel": str(_panel_path() or "-"), "cwd": os.getcwd()}


def rows(conn: psycopg.Connection, criteria: str | None = None, bucket: str | None = None) -> list[dict[str, Any]]:
    return _rows(conn, """SELECT id, criteria, bucket, horizon_days, sample_from, sample_to, n, hit, median, mean, p_loss50, mdd_book, extra, by_year, study_id, source, refreshed_at
                            FROM idx.signal_stats WHERE (%s::text IS NULL OR criteria = %s) AND (%s::text IS NULL OR bucket = %s)
                           ORDER BY criteria, horizon_days, bucket""", (criteria, criteria, bucket, bucket),
                 ["id", "criteria", "bucket", "horizon_days", "sample_from", "sample_to", "n", "hit", "median", "mean", "p_loss50", "mdd_book", "extra", "by_year", "study_id", "source", "refreshed_at"])
