#!/usr/bin/env python3
"""IDX — a portfolio on Buffett's principles, screened today (operator, 2026-09-18: "bikinkan portfolio berdasarkan Warren Buffett
principles"). Not a backtest and not a trial: a point-in-time screen of the audited record, written up as a candidate book.

The principles, made measurable (Berkshire-era Buffett, the replicable part — see the 2026-09-12 quality study for the backtest of
this style on IDX: it earns, but less than the strict value composite):
  1. Consistent earnings   >= 5 audited years, net profit > 0 in every one, latest FY = FY2024 or FY2025
  2. Durable high ROE      ROE >= 12 % in every year and >= 15 % on average (his favourite single number)
  3. Growing per share     EPS (split-adjusted) latest FY >= first FY of the window
  4. Little debt           non-financials: net debt <= 3 x net profit, or debt/equity <= 0.5
  5. Real cash earnings    non-financials: CFO / net profit >= 0.8 on average; free cash flow (CFO - capex) > 0 in >= 4 of 5 years
  6. Owner-friendly        no dilution (split-adjusted shares +10 % at most over the window); a cash dividend in the last 24 months
  7. Still earning         TTM profit >= 70 % of the latest FY (no collapse in the latest quarters)
  8. Fair price            P/E (TTM) <= 15 and owner-earnings yield >= 6 % (3-year mean free cash flow / market value;
                           banks: TTM profit / market value)
  Liquidity: 60-day median value >= Rp 5 bn, close >= Rp 100 (so the operator can actually buy and sell).
  Rank among the survivors by owner-earnings yield (the cheapest of the wonderful), top 10, weights proportional to a score
  (owner-earnings yield rank + mean ROE rank), capped at 20 %, floored at 5 %.
READ-ONLY (writes one idx.study row). INGEST_DB_DSN=... PYTHONIOENCODING=utf-8 blackheart-ingest/.venv/Scripts/python research/idx_buffett.py
"""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "blackheart-ingest", "src"))
from blackheart_ingest.idx import metrics, research_store  # noqa: E402

TOP, CAP, FLOOR = 10, 0.20, 0.05
FIN = ("Financial", "Finance")


def f(v):
    return None if v is None else float(v)


def main():
    today = date.today()
    with psycopg.connect(os.environ["INGEST_DB_DSN"]) as conn:
        cur = conn.cursor()
        cur.execute("""SELECT f.code, f.trade_date, f.value_60d_median, b.close FROM idx.feature_daily f JOIN idx.bar b USING (code, trade_date)
                        WHERE f.trade_date = (SELECT max(trade_date) FROM idx.feature_daily) AND b.source = 'idx'""")
        last = pd.DataFrame(cur.fetchall(), columns=["code", "trade_date", "v60", "close"])
        as_of = last["trade_date"].iloc[0]
        uni = last[(last["v60"].astype(float) >= 5e9) & (last["close"].astype(float) >= 100)].set_index("code")
        cur.execute("""SELECT code, period_end, published_at, net_profit, revenue, total_equity, total_debt, cash, cfo, capex, dividends_paid,
                              shares_out, roe, der, sector FROM idx.fundamental
                        WHERE months = 12 AND period_label = 'TAHUNAN' AND published_at <= now() AND period_end >= '2019-12-31' AND code = ANY(%s)
                        ORDER BY code, period_end, published_at DESC""", (list(uni.index),))
        fa = pd.DataFrame(cur.fetchall(), columns=["code", "fy", "pub", "np", "rev", "eq", "debt", "cash", "cfo", "capex", "div", "sh", "roe", "der", "sector"])
        fa = fa.drop_duplicates(["code", "fy"], keep="first")
        cur.execute("SELECT code, ex_date, kind, factor FROM idx.corporate_action WHERE kind IN ('split', 'reverse_split') AND factor > 0")
        splits = pd.DataFrame(cur.fetchall(), columns=["code", "ex", "kind", "factor"])
        cur.execute("SELECT code, max(ex_date) FROM idx.dividend WHERE kind = 'cash' AND ex_date >= %s GROUP BY code", (today - timedelta(days=730),))
        last_div = {r[0]: r[1] for r in cur.fetchall()}
        cur.execute("SELECT code, sector FROM idx.listing")
        lsector = {r[0]: r[1] for r in cur.fetchall()}
        ttm = metrics.fundamentals_asof(conn, today, list(uni.index))
    for c in ("np", "rev", "eq", "debt", "cash", "cfo", "capex", "div", "sh", "roe", "der"):
        fa[c] = pd.to_numeric(fa[c], errors="coerce")
    rows, near = [], []
    for code, g in fa.groupby("code"):
        g = g.sort_values("fy")
        if len(g) < 5 or g["fy"].iloc[-1].year < 2024:
            continue
        g = g.iloc[-5:]
        sp = splits[splits["code"] == code]
        adj = []
        for _, r in g.iterrows():
            k = 1.0
            for _, s in sp.iterrows():
                if s["ex"] > r["fy"]:
                    k /= float(s["factor"])
            adj.append(r["sh"] * k if pd.notna(r["sh"]) else None)
        g = g.assign(sh_adj=adj)
        sector = lsector.get(code) or g["sector"].iloc[-1] or ""
        is_fin = any(k in sector for k in FIN)
        t = ttm.get(code, {})
        np_ttm = f(t.get("net_profit_ttm"))
        eq_latest = f(t.get("equity_latest")) or float(g["eq"].iloc[-1])
        close = float(uni.loc[code, "close"])
        sh_now = g["sh_adj"].iloc[-1]
        if not sh_now or not eq_latest or eq_latest <= 0:
            continue
        mcap = close * sh_now
        eps_first = g["np"].iloc[0] / g["sh_adj"].iloc[0] if g["sh_adj"].iloc[0] else None
        eps_last = g["np"].iloc[-1] / sh_now
        roe = g["roe"].astype(float)
        cc = (g["cfo"] / g["np"]).replace([float("inf"), -float("inf")], float("nan"))
        fcf = g["cfo"] - g["capex"].fillna(0)
        net_debt = float(g["debt"].fillna(0).iloc[-1] - g["cash"].fillna(0).iloc[-1])
        oe = (fcf.iloc[-3:].mean() / mcap) if not is_fin else ((np_ttm or 0) / mcap)
        pe = mcap / np_ttm if np_ttm and np_ttm > 0 else None
        pb = mcap / eq_latest
        dil = (sh_now / g["sh_adj"].iloc[0] - 1) if g["sh_adj"].iloc[0] else None
        gates = {
            "1 laba 5 th": bool((g["np"] > 0).all()),
            "2 ROE >=12 tiap th, >=15 rata": bool((roe >= 0.12).all() and roe.mean() >= 0.15),
            "3 EPS tumbuh": bool(eps_first is not None and eps_last >= eps_first),
            "4 utang kecil": bool(is_fin or net_debt <= 3 * float(g["np"].iloc[-1]) or (pd.notna(g["der"].iloc[-1]) and g["der"].iloc[-1] <= 0.5)),
            "5 kas nyata": bool(is_fin or (cc.mean() >= 0.8 and (fcf > 0).sum() >= 4)),
            "6 tanpa dilusi + dividen": bool(dil is not None and dil <= 0.10 and code in last_div),
            "7 TTM utuh": bool(np_ttm is not None and np_ttm >= 0.7 * float(g["np"].iloc[-1])),
            "8 harga wajar": bool(pe is not None and pe <= 15 and oe >= 0.06),
        }
        rec = {"code": code, "sector": sector.split(". ")[-1] if ". " in sector else sector, "fin": is_fin, "close": close, "mcap_t": mcap / 1e12,
               "roe_mean": roe.mean(), "roe_min": roe.min(), "eps_cagr": ((eps_last / eps_first) ** 0.25 - 1) if eps_first and eps_first > 0 and eps_last > 0 else None,
               "net_debt_np": net_debt / float(g["np"].iloc[-1]) if g["np"].iloc[-1] else None, "cc": cc.mean(), "fcf_pos": int((fcf > 0).sum()),
               "dil": dil, "div_yield": (float(g["div"].iloc[-1]) / mcap) if pd.notna(g["div"].iloc[-1]) else None, "pe": pe, "pb": pb, "oe": oe,
               "ttm_basis": t.get("ttm_basis"), "fy": g["fy"].iloc[-1].year, "gates": gates, "fails": [k for k, v in gates.items() if not v]}
        (rows if not rec["fails"] else near).append(rec)
    df = pd.DataFrame(rows).sort_values("oe", ascending=False).head(TOP).reset_index(drop=True) if rows else pd.DataFrame()
    if len(df):
        score = df["oe"].rank() + df["roe_mean"].rank()
        w = score / score.sum()
        for _ in range(5):
            w = w.clip(FLOOR, CAP); w = w / w.sum()
        df["w"] = w
    nm = pd.DataFrame(near)
    nm["n_fail"] = nm["fails"].str.len()
    near1 = nm[nm["n_fail"] == 1].sort_values("oe", ascending=False)

    def pct(v, d=0):
        return "—" if v is None or pd.isna(v) else f"{v * 100:.{d}f} %"

    lines = [f"# Portofolio prinsip Buffett — IDX — screen {as_of} (harga penutupan terakhir)", "",
             f"Universe: {len(uni)} nama likuid (nilai 60 hari ≥ Rp 5 M, harga ≥ Rp 100); {len(rows) + len(near)} punya ≥ 5 laporan audit; "
             f"**{len(rows)} lolos semua 8 gate**; {len(near1)} gagal tepat satu gate.", "",
             "## Buku (10 nama teratas, peringkat owner-earnings yield)", "",
             "| # | Kode | Sektor | Harga | Mcap (T) | ROE rata 5 th | ROE min | EPS CAGR 4 th | Net debt / laba | CFO/laba | FCF+ (5 th) | Dilusi | Div yield | P/E TTM | P/B | OE yield | Bobot |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, r in df.iterrows():
        lines.append(f"| {i + 1} | **{r['code']}** | {r['sector']} | {r['close']:,.0f} | {r['mcap_t']:.1f} | {pct(r['roe_mean'])} | {pct(r['roe_min'])} | {pct(r['eps_cagr'])} | "
                     f"{'bank' if r['fin'] else f'{r['net_debt_np']:.1f}×'} | {'bank' if r['fin'] else f'{r['cc']:.2f}'} | {'bank' if r['fin'] else f'{r['fcf_pos']}/5'} | {pct(r['dil'])} | {pct(r['div_yield'], 1)} | "
                     f"{r['pe']:.1f} | {r['pb']:.1f} | {pct(r['oe'], 1)} | **{r['w'] * 100:.0f} %** |")
    lines += ["", "## Hampir lolos (gagal satu gate) — bahan pertimbangan, bukan buku", "",
              "| Kode | Sektor | ROE rata | P/E | OE yield | Gate yang gagal |", "|---|---|---|---|---|---|"]
    for _, r in near1.head(20).iterrows():
        lines.append(f"| {r['code']} | {r['sector']} | {pct(r['roe_mean'])} | {'—' if r['pe'] is None else f'{r['pe']:.1f}'} | {pct(r['oe'], 1)} | {r['fails'][0]} |")
    fail_counts = nm["fails"].explode().value_counts()
    lines += ["", "## Gate mana yang paling sering menggugurkan", "", "| Gate | Gagal |", "|---|---|"] + [f"| {k} | {v} |" for k, v in fail_counts.items()]
    text = "\n".join(lines); print(text)
    out = os.path.join(HERE, f"IDX_BUFFETT_PORTFOLIO_{today.isoformat()}.md")
    open(out, "w", encoding="utf-8").write(text + "\n"); print("wrote", out)
    with psycopg.connect(os.environ["INGEST_DB_DSN"]) as conn:
        names = [{"code": r["code"], "screens": ["buffett"], "score": float(r["oe"]), "rank": int(i + 1),
                  "features": {k: (None if v is None or (isinstance(v, float) and pd.isna(v)) else v) for k, v in r.items() if k not in ("gates", "fails", "code")},
                  "context": {"weight": float(r["w"])}} for i, r in df.iterrows()]
        sid = research_store.record_study(conn, "buffett_portfolio", as_of, params={"top": TOP, "cap": CAP, "floor": FLOOR, "gates": list(rows[0]["gates"]) if rows else []},
                                          summary={"universe": int(len(uni)), "passed": len(rows), "near": int(len(near1)), "fail_counts": fail_counts.to_dict()},
                                          names=names, report_path=out, note=f"{len(rows)} pass all 8 gates; book = top {len(df)}")
        print("study", sid)


if __name__ == "__main__":
    main()
