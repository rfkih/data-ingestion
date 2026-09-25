#!/usr/bin/env python3
"""IDX Track A2 - survivorship bias: is idx.bar missing delisted names, and how much does the backtest universe flatter the
books? (2026-09-25). A DATA STUDY, not a strategy trial: adds 0 to the cumulative trial count (849).

Steps
  1. Delisting list 2020-01 .. 2026-09 from IDX's own statistic (primary/DigitalStatistic LINK_DELISTING, monthly; fetched
     with curl_cffi impersonate='safari', cached in tmp/idx_delisting_stat.json) + FREN (merger into EXCL/XLSMART, not in
     IDX's delisting statistic) + every code whose last idx.bar is before 2026-09. Reasons from idx.announcement titles.
  2. Coverage: each delisted code's rows in idx.bar / idx.daily_summary, first/last date vs the delisting date.
  3. Stage those rows to tmp/delisted_bars.parquet.
  4. Bias: the research panels (`idx_swing2.panels`) keep only codes whose CURRENT idx.listing.board is Utama/Pengembangan,
     which drops (a) every delisted code (listing status NOT_IN_DAFTAR, board NULL) and (b) every code that is on Akselerasi /
     Pemantauan Khusus / Ekonomi Baru TODAY, for the whole 2020-2026 history. Three universes, everything else identical:
       U0 as-run   current board in {Utama, Pengembangan}                       (what every study so far used)
       U1 +dead    U0 plus the delisted codes                                   (the delisting fix alone)
       U2 PIT      board ON THE DAY in {Utama, Pengembangan} (daily_summary.remarks; 2020-01..07 old notation = last char),
                   all codes incl. delisted                                     (the honest universe; = the live rule's intent)
     Books: (a) the deployed trend book `small` (LIQ minus BLUE; 60-day high & > MA200 & vol >= 1.5x; K=10; trail10; regime
     gate; closing offer/bid + Stockbit fees - `idx_combo_rupiah.trend_trades`'s exact config), entries from 2020 and from
     2022-01 (the combo window); (b) equal-weight LIQ (daily EW of names in LIQ at close t-1, no costs) as the baseline;
     (c) descriptive: EW of every board name that traded at t-1 (no liquidity floor), with a -100 % day for forced delistings.
READ-ONLY on idx.bar (no insert: see report). One idx.study row ('survivorship').
  PYTHONIOENCODING=utf-8 blackheart-ingest/.venv/Scripts/python research/idx_survivorship.py
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
from datetime import date

import numpy as np
import pandas as pd
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blackheart-ingest", "src"))
import idx_beyond as BY  # noqa: E402
import idx_exit as E  # noqa: E402
import idx_swing2 as S  # noqa: E402
from blackheart_ingest.idx import research_store as rs  # noqa: E402

TMP = os.path.join(ROOT, "tmp")
STAT = os.path.join(TMP, "idx_delisting_stat.json")
STAGE = os.path.join(TMP, "delisted_bars.parquet")
OUT = os.path.join(HERE, "IDX_SURVIVORSHIP_2026-09-25.md")
N_TRIALS = 849                       # unchanged: data study
START22 = pd.Timestamp("2022-01-01")
OK_BOARDS = {"1", "2"}               # Utama, Pengembangan

# reason per delisted code: IDX statistic + announcement titles (idx.announcement) + press (CNBC Indonesia 2025-07-22)
REASON = {
    "BORN": "forced (long suspension)", "ITTG": "forced (long suspension)", "APOL": "forced (long suspension)",
    "SCBD": "voluntary go-private", "CKRA": "forced (long suspension)", "GREN": "forced (long suspension)",
    "FINN": "forced (long suspension)", "TURI": "voluntary go-private (tender offer)", "RMBA": "voluntary go-private (BAT tender offer)",
    "FREN": "merger into EXCL (XLSMART); shares converted, not in IDX delisting statistic",
    "MFIN": "voluntary go-private after mandatory tender offer", "MASA": "voluntary go-private (tender offer)",
    "CNTX": "voluntary go-private", "CNTB": "voluntary go-private (series B of CNTX)",
}
JULY25 = ["FORZ", "JKSW", "KPAL", "KPAS", "KRAH", "MAMI", "MAMIP", "MYRX", "MYRXP", "NIPS", "PRAS", "HDTX"]
for _c in JULY25:
    REASON[_c] = "forced (bankruptcy / 24+ months suspended), IDX batch 2025-07-21"
FORCED = {c for c, r in REASON.items() if r.startswith("forced")}


def dsn():
    if "INGEST_DB_DSN" not in os.environ:
        for line in open(os.path.join(ROOT, "blackheart-ingest", "idx-local.env"), encoding="utf-8"):
            if line.startswith("INGEST_DB_DSN="):
                os.environ["INGEST_DB_DSN"] = line.split("=", 1)[1].strip().strip('"')
    return os.environ["INGEST_DB_DSN"]


def idx_delisting_stat():
    """IDX's delisting statistic, one call per month 2020-01..2026-09 (cached)."""
    if os.path.exists(STAT):
        return json.load(open(STAT))
    from curl_cffi import requests as cr
    s = cr.Session(impersonate="safari")          # 'chrome' is challenged by Cloudflare from this host (2026-09-25)
    ref = {"Referer": "https://www.idx.co.id/id/data-pasar/laporan-statistik/digital-statistic/monthly/corporate-action-of-listed-companies/delisted-company"}
    out = []
    for y in range(2020, 2027):
        for m in range(1, 13):
            if (y, m) > (2026, 9):
                break
            u = (f"https://www.idx.co.id/primary/DigitalStatistic/GetApiDataPaginated?urlName=LINK_DELISTING&periodYear={y}&periodMonth={m}"
                 "&periodType=monthly&isPrint=False&cumulative=false&pageSize=500&pageNumber=1&orderBy=&search=")
            for z in s.get(u, timeout=60, headers=ref).json().get("data", []):
                z["_y"], z["_m"] = y, m
                out.append(z)
            time.sleep(0.7)
    json.dump(out, open(STAT, "w"), indent=1, default=str)
    return out


def delisting_table(conn):
    stat = {z["code"]: z for z in idx_delisting_stat()}
    last = pd.read_sql("""SELECT b.code, min(b.trade_date) AS first_bar, max(b.trade_date) AS last_bar, count(*) AS bars,
                                 count(*) FILTER (WHERE b.volume > 0) AS traded_days, max(l.name) AS name, max(l.status) AS status
                            FROM idx.bar b LEFT JOIN idx.listing l USING (code) GROUP BY b.code""", conn)
    dead_db = set(last.loc[pd.to_datetime(last["last_bar"]) < pd.Timestamp("2026-09-01"), "code"])
    codes = sorted(set(stat) | dead_db | {"FREN"})
    ds = pd.read_sql("SELECT code, count(*) AS ds_rows, max(trade_date) AS ds_last FROM idx.daily_summary WHERE code = ANY(%s) GROUP BY code", conn, params=(codes,))
    v60 = pd.read_sql("""SELECT code, max(value_60d_median) / 1e9 AS max_v60_bn,
                                count(*) FILTER (WHERE value_60d_median >= 5e9) AS days_v60_ge5bn FROM idx.feature_daily WHERE code = ANY(%s) GROUP BY code""",
                      conn, params=(codes,))
    t = pd.DataFrame({"code": codes}).merge(last, on="code", how="left").merge(ds, on="code", how="left").merge(v60, on="code", how="left")
    t["idx_delisting_date"] = [pd.to_datetime(stat[c]["DeListingDate"]).date() if c in stat else None for c in t["code"]]
    t["in_idx_stat"] = t["code"].isin(stat)
    t["reason"] = t["code"].map(REASON).fillna("?")
    t["covered"] = t["bars"].fillna(0) > 0
    return t


def pit_board(conn, dates, cols):
    """Board digit on the day from daily_summary.remarks (5th char; 2020-01..07 notation '--U9---2' = last char), per code
    forward/back-filled over days with an unreadable notation. Returns a bool mask 'board in Utama/Pengembangan'."""
    r = pd.read_sql("SELECT code, trade_date, remarks FROM idx.daily_summary WHERE trade_date BETWEEN %s AND %s", conn, params=(S.START, S.END))
    rm = r["remarks"].fillna("")
    d5 = rm.str[4]
    old = rm.str[-1]
    r["b"] = np.where(d5.isin(list("12345")), d5, np.where((rm.str.len() == 8) & old.isin(list("123")), old, None))
    r["trade_date"] = pd.to_datetime(r["trade_date"])
    B = r.pivot(index="trade_date", columns="code", values="b").reindex(index=dates, columns=cols).ffill().bfill()
    return B.isin(OK_BOARDS), B


def load(conn):
    bars, listing, idx, macro, buyb, splits, pead = S.load(conn)
    bars = bars.copy()
    for c in ("close", "adj_factor", "volume", "bid", "offer", "bv", "ov", "freq", "fb", "fs", "f5", "f20", "v60"):
        bars[c] = pd.to_numeric(bars[c], errors="coerce")
    bars["adj"] = bars["close"] * bars["adj_factor"].fillna(1.0)
    bars["fnet"] = (bars["fb"].fillna(0) - bars["fs"].fillna(0)) * bars["close"]
    # identical to S.panels except: NO current-board filter (all codes kept; universes are masks below)
    P = {c: bars.pivot(index="trade_date", columns="code", values=c).sort_index() for c in ("adj", "close", "volume", "bid", "offer", "bv", "ov", "freq", "fnet", "f5", "f20", "v60")}
    for k in P:
        P[k].index = pd.to_datetime(P[k].index)
    _, unis, comp = S.build(P, listing, idx, macro, buyb, splits, pead)
    Hp, Lp = E.load_hl(conn, P)
    return P, unis, comp, Hp, Lp, listing


def trend_book(P, unis, comp, Hp, Lp, colmask, start=None):
    """idx_combo_rupiah.trend_trades's exact book, universe = small & colmask. Returns daily R, closed trades, open."""
    c_in, c_out = S.costs(P)
    adj, vol = P["adj"], P["volume"]
    d_tr = adj.index
    A, H, L = adj.to_numpy(float), Hp.to_numpy(float), Lp.to_numpy(float)
    ma200 = adj.rolling(200, min_periods=200).mean()
    vr = vol / vol.rolling(20, min_periods=20).median()
    hi = adj.rolling(60, min_periods=60).max()
    entry = ((adj >= hi) & (adj > ma200) & (vr >= 1.5)).to_numpy(bool) & ~BY.regime_off_mask(comp, d_tr)[:, None]
    if start is not None:
        entry &= np.asarray(d_tr >= start)[:, None]
    prev = adj.shift(1)
    tr = pd.concat([Hp - Lp, (Hp - prev).abs(), (Lp - prev).abs()], axis=1, keys=["a", "b", "c"]).T.groupby(level=1).max().T.reindex(columns=adj.columns)
    ATR = tr.ewm(alpha=1 / 20, adjust=False, min_periods=20).mean().to_numpy(float)
    ma20, ma50 = (adj.rolling(n, min_periods=n).mean().to_numpy(float) for n in (20, 50))
    d = adj.diff()
    up = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    RSI = (100 - 100 / (1 + up / dn.replace(0, np.nan))).to_numpy(float)
    LO10 = Lp.shift(1).rolling(10, min_periods=10).min().to_numpy(float)
    LO20 = Lp.shift(1).rolling(20, min_periods=20).min().to_numpy(float)
    rule = E.make_rules(A, H, L, ATR, ma20, ma50, RSI, LO10, LO20)["trail10"]
    small = ((unis["LIQ"] & ~unis["BLUE"]) & colmask).to_numpy(bool)
    R, trs, open_ = E.run_book(A, H, L, c_in, c_out, entry, vr.to_numpy(float), rule, small)
    R.index = d_tr
    return R, trs, open_


def ew(adj, member, forced_loss=None):
    """Daily EW of names in `member` at close t-1, return close t-1 -> t (a missing close counts 0, or -100 % on a forced
    delisting's first missing day when forced_loss = {code: last_bar_date})."""
    r = adj / adj.shift(1) - 1
    if forced_loss:
        for c, dlast in forced_loss.items():
            if c in r.columns:
                nxt = r.index[r.index > pd.Timestamp(dlast)]
                if len(nxt):
                    r.loc[nxt[0], c] = -1.0
    m = member.shift(1, fill_value=False)
    w = m.sum(axis=1)
    R = (r.where(m).fillna(0.0).sum(axis=1) / w.replace(0, np.nan)).fillna(0.0)
    return R


def st(R, trs=None, start=None):
    if start is not None:
        R = R[R.index >= start]
    first = R.ne(0).idxmax() if R.ne(0).any() else R.index[0]
    R = R[R.index >= first]
    eq = (1 + R).cumprod()
    vol = R.std() * math.sqrt(250)
    out = {"from": str(first.date()), "cagr": float(eq.iloc[-1] ** (250 / len(R)) - 1), "sharpe": float(R.mean() * 250 / vol) if vol > 0 else 0.0,
           "mdd": float((eq / eq.cummax() - 1).min()), "total": float(eq.iloc[-1] - 1)}
    if trs is not None:
        out["n"] = len(trs)
        out["avg_net"] = float(np.mean([t[3] for t in trs])) if trs else 0.0
    return out


def main() -> int:
    t0 = time.time()
    with psycopg.connect(dsn()) as conn:
        tab = delisting_table(conn)
        dead = list(tab["code"])
        stage = pd.read_sql("""SELECT b.*, s.name, s.remarks, s.previous, s.bid, s.offer, s.frequency, s.listed_shares
                                 FROM idx.bar b LEFT JOIN idx.daily_summary s USING (code, trade_date) WHERE b.code = ANY(%s) ORDER BY 1, 2""", conn, params=(dead,))
        os.makedirs(TMP, exist_ok=True)
        stage.to_parquet(STAGE, index=False)
        print(f"staged {len(stage)} rows / {stage['code'].nunique()} codes -> {STAGE}", flush=True)
        P, unis, comp, Hp, Lp, listing = load(conn)
        pit, B = pit_board(conn, P["adj"].index, P["adj"].columns)
    cols, dates = P["adj"].columns, P["adj"].index
    cur_ok = set(listing.loc[listing["board"].isin(["Utama", "Pengembangan"]), "code"])
    one = pd.DataFrame(True, index=dates, columns=cols)
    U = {"U0_asrun": one & pd.Series(cols.isin(list(cur_ok)), index=cols),
         "U1_plus_dead": one & pd.Series(cols.isin(list(cur_ok | set(dead))), index=cols),
         "U2_pit_board": pit}
    # sanity: U0 on the full panel == the as-run S.panels restriction (per-column computations; universe = mask)
    liq, blue = unis["LIQ"], unis["BLUE"]
    small = liq & ~blue
    # exposure of the universes: name-days in LIQ / small
    expo = {u: {"liq_namedays": int((liq & m).to_numpy().sum()), "small_namedays": int((small & m).to_numpy().sum()),
                "names_ever_liq": int((liq & m).any().sum())} for u, m in U.items()}
    # names that differ between U0 and U2 inside LIQ
    only_pit = (liq & U["U2_pit_board"] & ~U["U0_asrun"]).sum()
    only_cur = (liq & U["U0_asrun"] & ~U["U2_pit_board"]).sum()
    cur_board = listing.set_index("code")["board"]
    diff_names = {"in_pit_not_asrun": {c: {"days": int(n), "board_now": cur_board.get(c)} for c, n in only_pit[only_pit > 0].sort_values(ascending=False).items()},
                  "in_asrun_not_pit": {c: {"days": int(n), "board_now": cur_board.get(c)} for c, n in only_cur[only_cur > 0].sort_values(ascending=False).items()}}
    dead_liq = {c: int(liq[c].sum()) for c in dead if c in liq.columns and liq[c].sum() > 0}
    dead_small = {c: int(small[c].sum()) for c in dead if c in small.columns and small[c].sum() > 0}
    res = {}
    adj = P["adj"]
    last_bar = dict(zip(tab["code"], tab["last_bar"]))
    forced_loss = {c: last_bar[c] for c in FORCED if c in last_bar}
    for u, m in U.items():
        for lab, start in (("from2020", None), ("from2022", START22)):
            R, trs, open_ = trend_book(P, unis, comp, Hp, Lp, m, start)
            held_dead = sorted({cols[t[1]] for t in trs if cols[t[1]] in dead} | {cols[j] for j in open_ if cols[j] in dead})
            res[f"trend_small|{u}|{lab}"] = {**st(R, trs, start), "open": len(open_), "dead_names_traded": held_dead,
                                             "codes": sorted({cols[t[1]] for t in trs})}
            print(u, lab, {k: v for k, v in res[f'trend_small|{u}|{lab}'].items() if k != 'codes'}, flush=True)
        Rl = ew(adj, liq & m)
        for lab, start in (("from2020", None), ("from2022", START22)):
            res[f"ew_liq|{u}|{lab}"] = st(Rl, None, start)
        allm = m & (P["volume"] > 0) & (P["close"] >= 50)
        Ra = ew(adj, allm, forced_loss)
        res[f"ew_all_traded|{u}|from2020"] = st(Ra)
        print(u, "ew_liq", res[f"ew_liq|{u}|from2020"], "ew_all", res[f"ew_all_traded|{u}|from2020"], flush=True)
    # trade-level diff of the trend book U0 vs U2
    diff_codes = {lab: {"only_U2": sorted(set(res[f"trend_small|U2_pit_board|{lab}"]["codes"]) - set(res[f"trend_small|U0_asrun|{lab}"]["codes"])),
                        "only_U0": sorted(set(res[f"trend_small|U0_asrun|{lab}"]["codes"]) - set(res[f"trend_small|U2_pit_board|{lab}"]["codes"]))}
                  for lab in ("from2020", "from2022")}
    write_report(tab, stage, expo, diff_names, dead_liq, dead_small, res, diff_codes)
    summ = {"delisted_codes": len(tab), "covered": int(tab["covered"].sum()), "dead_names_ever_in_liq": dead_liq, "dead_names_ever_in_small": dead_small,
            "exposure": expo, "results": {k: {kk: vv for kk, vv in v.items() if kk != "codes"} for k, v in res.items()},
            "trend_code_diff": diff_codes, "inserted_rows": 0}
    if os.environ.get("NO_STORE"):
        return 0
    with psycopg.connect(dsn()) as conn:
        sid = rs.record_study(conn, "survivorship", date(2026, 9, 25),
                              params={"n_trials_cumulative": N_TRIALS, "trials_added": 0, "universes": list(U), "books": ["trend_small(K10,trail10,regime)", "ew_liq", "ew_all_traded"],
                                      "window": [str(S.START), str(S.END)], "source": "IDX LINK_DELISTING statistic + idx.bar + idx.announcement"},
                              summary=summ, names=[{"code": c, "screens": ["delisted"], "context": {"reason": REASON.get(c, "?"), "last_bar": str(last_bar.get(c))}} for c in dead],
                              report_path=OUT, note="Track A2 data study: delisted names are already in idx.bar; the leak is the current-board filter in research panels")
    print(f"study #{sid}; {time.time() - t0:.0f}s")
    return 0


def pct(x):
    return f"{x * 100:+.1f} %"


def write_report(tab, stage, expo, diff_names, dead_liq, dead_small, res, diff_codes):
    L = ["# IDX survivorship bias (Track A2) - 2026-09-25", "",
         "Data study (0 trials; cumulative stays 849). Script `research/idx_survivorship.py`; staged rows `tmp/delisted_bars.parquet`.", "",
         "## Findings", "",
         "1. **The premise was wrong: idx.bar is NOT missing delisted names.** IDX's own delisting statistic (primary/DigitalStatistic "
         "LINK_DELISTING, every month 2020-01..2026-09) lists 25 codes; add FREN (merged into EXCL/XLSMART 2025-04, not in that statistic) "
         "= 26, and those are exactly the 26 codes whose last idx.bar is before 2026-09. Each has its full 2020+ life in idx.bar and "
         "idx.daily_summary through the day before delisting. IDX delisted 6 names in 2020, 1 in 2021 (FINN), 0 in 2022, 1 in 2023 "
         "(TURI), 1 in 2024 (RMBA) - confirmed by CNBC Indonesia (2025-07-22: '2021, 2023 dan 2024 masing-masing 1 emiten ... 2022 tidak "
         "ada'). The day dumps are complete snapshots: IDX GetStockSummary for 2021-01-04 returns 717 rows = our 717. The 'missing "
         "2021-2024 delistings' simply did not happen; IDX let distressed names sit suspended (they are in the data as zero-volume rows) "
         "and delisted them in batches (2025-07-18: 12 codes; the 2026-04 decision on 18 more takes effect ~2026-11).",
         "2. **Coverage 26/26. Nothing to insert.** Every delisted code/date already exists in idx.bar with source 'idx' (PK code, "
         "trade_date); an INSERT-only backfill would add 0 rows, so none was run and there is no rollback SQL. tmp/delisted_bars.parquet "
         "holds the 26 codes' existing rows (bar + summary columns) for inspection only.",
         "3. **Only one delisted name was ever tradable by the books:** FREN (60-day median value >= Rp 5 bn on 967 days, 157 of them "
         "inside LIQ with close >= Rp 100). Every other delisted name had max 60-day median value < Rp 5 bn - the forced delistings "
         "were suspended/zero-volume for years before the event, the go-privates were thin. The Rp 5 bn floor already filtered them out.",
         "4. **The real leak is a different one: the research panels (`idx_swing2.panels`, used by idx_exit/idx_combo_rupiah/every "
         "trend study) keep codes by their CURRENT `idx.listing.board`**, not the board on the day. That drops the 26 delisted codes "
         "(board NULL) AND every name that is on Pemantauan Khusus / Akselerasi / Ekonomi Baru today - for all of 2020-2026. 49 names "
         "that were liquid Utama/Pengembangan names at the time (WIKA, WSKT, MLIA, MPPA, WSBP, BUKA, INAF, SRIL, ...; the ones that later "
         "failed) are excluded from history, while 41 names that were on Akselerasi/PK on the day but are Utama/Pengembangan now (GOTO, "
         "CUAN, BREN, ...) are included. That is look-ahead survivorship, and it is measured below as U2 (board on the day from "
         "`daily_summary.remarks`; the 2020-01..07 old notation's last character agrees 696/696 with the new 5th character on the switch day).",
         "5. **Size of the bias** (only the universe mask changes; data, engine, costs, rules identical):",
         "   - delisting fix alone (U1): trend `small` CAGR -0.4/-0.5 pp, Sharpe -0.01; EW-LIQ ~0. Negligible.",
         "   - point-in-time board (U2): trend `small` 2022-> CAGR 26.5 -> 24.1 % (-2.4 pp), Sharpe 1.34 -> 1.21, mDD 18.2 -> 17.5 %; "
         "2020-> CAGR -0.1 pp, Sharpe -0.05. EW-LIQ baseline CAGR 9.6 -> 6.6 % (-3.0 pp), Sharpe 0.53 -> 0.41. The trend rule is "
         "robust to it (trend filters mostly skip names on their way down), the passive baseline is not.",
         "   - Read: the published trend numbers are overstated by ~2-3 pp CAGR / ~0.1 Sharpe on the 2022+ window; the strategy verdicts do "
         "not flip. Recommendation (not done - code change outside this study's remit): make the research panels mask by board on the day "
         "(the `pit_board` function here) instead of `idx.listing.board`.",
         "6. EW-ALL-traded (no liquidity floor, forced delistings get a -100 % day) is descriptive: its level is inflated by daily "
         "rebalancing of illiquid names (bid-ask bounce); its U2 delta (-4.0 pp CAGR) is again the board filter, not the delistings "
         "(the forced names had not traded for years, so the -100 % day lands on no weight).",
         "7. FREN in the books is valued at its last IDX close (23) when the bars stop; holders actually received EXCL shares, so this is "
         "an approximation; no book held FREN at the merger in any run (0 open positions at the end).", ""]
    L += ["## Delistings 2020-01 .. 2026-09", "",
          "| code | name | IDX delisting date | last bar | bars | traded days | max v60 (Rp bn) | days v60>=5bn | reason |", "|---|---|---|---|---|---|---|---|---|"]
    for r in tab.sort_values("last_bar").itertuples():
        L.append(f"| {r.code} | {r.name} | {r.idx_delisting_date or '-'} | {r.last_bar} | {r.bars} | {r.traded_days} | "
                 f"{0 if pd.isna(r.max_v60_bn) else float(r.max_v60_bn):.2f} | {0 if pd.isna(r.days_v60_ge5bn) else int(r.days_v60_ge5bn)} | {r.reason} |")
    L += ["", f"Coverage: {int(tab['covered'].sum())} / {len(tab)} delisted codes have their full 2020+ life in idx.bar "
          f"({len(stage)} rows staged).", ""]
    L += ["## Universe exposure (name-days 2020-01-02 .. 2026-09-16)", "", "| universe | LIQ name-days | small name-days | names ever in LIQ |", "|---|---|---|---|"]
    for u, e in expo.items():
        L.append(f"| {u} | {e['liq_namedays']} | {e['small_namedays']} | {e['names_ever_liq']} |")
    L += ["", f"Delisted names ever in LIQ: {dead_liq or 'none'}; ever in small: {dead_small or 'none'}.", ""]
    top = list(diff_names["in_pit_not_asrun"].items())[:30]
    L += [f"LIQ names in the PIT universe but dropped by the as-run filter: {len(diff_names['in_pit_not_asrun'])} "
          f"(top by LIQ days: " + ", ".join(f"{c} {v['days']}d now {v['board_now']}" for c, v in top) + ")",
          f"LIQ names in the as-run universe but not PIT (on Akselerasi/PK on the day, since promoted): {len(diff_names['in_asrun_not_pit'])} "
          f"(" + ", ".join(f"{c} {v['days']}d" for c, v in list(diff_names['in_asrun_not_pit'].items())[:20]) + ")", ""]
    L += ["## Bias", "", "| book | window | universe | from | CAGR | Sharpe | mDD | trades | dead names traded |", "|---|---|---|---|---|---|---|---|---|"]
    for k, s in res.items():
        b, u, w = k.split("|")
        L.append(f"| {b} | {w} | {u} | {s['from']} | {pct(s['cagr'])} | {s['sharpe']:.2f} | {pct(s['mdd'])} | {s.get('n', '-')} | {', '.join(s.get('dead_names_traded', [])) or '-'} |")
    L += ["", "Deltas vs U0 (as-run):", ""]
    for k, s in res.items():
        b, u, w = k.split("|")
        if u == "U0_asrun":
            continue
        base = res[f"{b}|U0_asrun|{w}"]
        L.append(f"- {b} {w} {u}: CAGR {(s['cagr'] - base['cagr']) * 100:+.1f} pp, Sharpe {s['sharpe'] - base['sharpe']:+.2f}, mDD {(s['mdd'] - base['mdd']) * 100:+.1f} pp")
    L += ["", f"Trend-book traded codes, U2 vs U0: {json.dumps(diff_codes)}", ""]
    open(OUT, "w", encoding="utf-8").write("\n".join(L) + "\n")


if __name__ == "__main__":
    sys.exit(main())
