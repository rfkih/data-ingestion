"""The daily panel: one row per (name, bar date) with everything the desk knows at that close, and the forward log
return for every daily horizon. Point-in-time throughout: fundamentals by published_at, macro/consensus by
as-of date, events by the day they were public; nothing from the future leaks into a row.

Sources (all read-only): idx.bar (+ adj_factor), idx.daily_summary (foreign legs, bid/offer at the close, frequency,
listed/tradeable shares, index weight, non-regular), idx.index_daily COMPOSITE, idx.macro (12 series), idx.fundamental
(PIT), idx.broker_flow (1-day buyer/seller concentration), idx.sentiment_daily, idx.consensus, idx.feature_daily
(disclosure-event flags), idx.listing (sector). Columns that a source cannot fill are NaN: LightGBM routes them.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

import numpy as np
import pandas as pd
import psycopg
from psycopg.rows import tuple_row

from .spec import DAILY

logger = logging.getLogger(__name__)

MIN_CLOSE = 50.0                       # below this the tick is the whole move
MIN_VALUE20_FIT = 1e8                  # Rp 100 M mean daily value to be a training row
MIN_VALUE20_PREDICT = 2e8              # Rp 200 M to be scored (a forecast on a name that never trades is noise)
MACRO_SERIES = ["usdidr", "bi_rate", "bi_rate_hist", "us10y", "vix", "brent", "gold", "cpo", "fedfunds", "id_cpi", "id_gdp_qoq", "id_inflation_yoy"]
MACRO_RET = {"usdidr", "brent", "gold", "cpo", "vix"}
# When is a reading dated obs_date actually KNOWN at the desk's 16:00 WIB cut? (point-in-time; the release, not the period)
#   same_day   BI-Rate: the RDG decision is announced ~14:00 WIB on obs_date
#   next_day   US close (DGS10, VIX ~04:00 WIB D+1), ICE Brent settlement (~01:30 WIB D+1), COMEX gold (~01:30 WIB D+1),
#              Bursa Malaysia CPO (closes 17:00 WIB, after the cut), Yahoo's daily FX bar for USD/IDR (NY session)
#   month_next_bday   monthly readings dated the 1st (FEDFUNDS average, the OECD monthly policy rate) are complete when the
#              month ends -> first business day of the next month; BPS publishes the CPI on the 1st business day of the next month
#   quarter_release   BPS publishes GDP ~5 weeks after the quarter ends (obs_date = quarter start -> +4 months +5 days -> next bday)
MACRO_RELEASE = {"bi_rate": "same_day", "usdidr": "next_day", "us10y": "next_day", "vix": "next_day", "brent": "next_day", "gold": "next_day",
                 "cpo": "next_day", "fedfunds": "month_next_bday", "bi_rate_hist": "month_next_bday", "id_cpi": "month_next_bday", "id_inflation_yoy": "month_next_bday",
                 "id_gdp_qoq": "quarter_release"}

FEATURES: list[str] = [
    # price / volume (adjusted)
    "ret1", "ret5", "ret20", "ret60", "ret120", "ret250", "dist_ma20", "dist_ma50", "dist_ma200", "vol20", "vol60", "atr_pct",
    "pos20", "dist_hi252", "dist_lo252", "volr1", "volr5", "lvalue20", "lvalue60", "gap", "clv", "up_days", "dow", "month", "age",
    # the day's tape (daily_summary)
    "freq_ratio", "spread_bps", "bo_imb", "fnet1", "fnet5", "fnet20", "lmcap", "free_float", "idx_weight", "nonreg_share",
    # cross-section
    "xs_r1", "xs_r20", "xs_r60", "sec_r20", "breadth", "sector",
    # the market
    "comp_r1", "comp_r5", "comp_r20", "comp_r60", "comp_dma200", "comp_vol20",
    # macro (as-of)
    "usdidr_r20", "bi_rate", "us10y", "vix", "vix_r20", "brent_r20", "gold_r20", "cpo_r20", "fedfunds", "id_cpi_yoy", "id_gdp_qoq",
    # fundamentals (PIT)
    "np_yoy", "rev_yoy", "roe", "roa", "der", "net_margin", "cfo_pos", "profitable", "pe", "pb", "months", "stale_days",
    # broker flow (1-day, regular board)
    "bf_hhi_buy", "bf_hhi_sell", "bf_top1_buy", "bf_top1_sell", "bf_nbuy", "bf_nsell", "bf_foreign_buy_share", "bf_foreign_sell_share",
    # sentiment / consensus / disclosure events
    "sent_score", "sent_neg", "cons_upside", "cons_reco", "cons_n",
    "ev_ownership", "ev_query", "ev_dividend", "ev_buyback", "ev_material", "ev_rights",
]


def _frame(conn: psycopg.Connection, sql: str, params: tuple, cols: list[str]) -> pd.DataFrame:
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(sql, params)
        return pd.DataFrame(cur.fetchall(), columns=cols)


def _num(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    for c in cols:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
    return df


# ---- loaders -----------------------------------------------------------------------------------------------------------
def load_bars(conn: psycopg.Connection, since: date | None) -> pd.DataFrame:
    B = _frame(conn, """
        SELECT b.code, b.trade_date, b.open, b.high, b.low, b.close, b.volume, b.value, b.adj_factor,
               s.frequency, s.bid, s.bid_volume, s.offer, s.offer_volume, s.foreign_buy, s.foreign_sell, s.listed_shares,
               s.tradeable_shares, s.weight_for_index, s.nonreg_value
          FROM idx.bar b
          LEFT JOIN idx.daily_summary s ON s.code = b.code AND s.trade_date = b.trade_date
         WHERE b.source = 'idx' AND b.close > 0 AND (%s::date IS NULL OR b.trade_date >= %s)
         ORDER BY b.code, b.trade_date""", (since, since),
        ["code", "d", "open", "high", "low", "close", "volume", "value", "adj", "frequency", "bid", "bid_vol", "offer", "offer_vol",
         "fbuy", "fsell", "listed", "tradeable", "weight", "nonreg_value"])
    B = _num(B, [c for c in B.columns if c not in ("code", "d")])
    B["d"] = pd.to_datetime(B["d"])
    return B


def load_index(conn: psycopg.Connection) -> pd.DataFrame:
    ix = _frame(conn, "SELECT trade_date, close FROM idx.index_daily WHERE index_code = 'COMPOSITE' AND close > 0 ORDER BY trade_date", (),
               ["d", "comp"])
    ix["d"] = pd.to_datetime(ix["d"])
    ix["comp"] = ix["comp"].astype(float)
    lc = np.log(ix["comp"])
    for h in DAILY:
        if h.basis == "excess":
            ix[f"comp_fwd_{h.key}"] = lc.shift(-h.steps) - lc          # the market's forward return over the same window
    ix["comp_r1"], ix["comp_r5"], ix["comp_r20"], ix["comp_r60"] = lc.diff(1), lc.diff(5), lc.diff(20), lc.diff(60)
    ix["comp_dma200"] = ix["comp"] / ix["comp"].rolling(200, min_periods=100).mean() - 1
    ix["comp_vol20"] = lc.diff(1).rolling(20).std()
    return ix.drop(columns=["comp"])


def release_date(series: str, obs: pd.Timestamp) -> pd.Timestamp:
    """The first day the reading dated ``obs`` is known at the 16:00 WIB cut (see MACRO_RELEASE)."""
    rule = MACRO_RELEASE.get(series, "next_day")
    if rule == "same_day":
        return obs
    if rule == "next_day":
        return obs + pd.Timedelta(days=1)
    if rule == "month_next_bday":
        first_next = (obs + pd.offsets.MonthBegin(1)).normalize() if obs.day != 1 else (obs + pd.DateOffset(months=1)).normalize()
        return first_next + pd.offsets.BDay(0)                       # the 1st itself when it is a business day, else the next one
    if rule == "quarter_release":
        return (obs + pd.DateOffset(months=4, days=5)).normalize() + pd.offsets.BDay(0)   # quarter end + ~5 weeks
    raise ValueError(rule)


def load_macro(conn: psycopg.Connection) -> pd.DataFrame:
    """Every macro series re-dated to its RELEASE date, then as-of joined on that. bi_rate = the RDG decisions (event dates)
    on top of the OECD monthly history; id_cpi becomes the y/y log inflation (the index level is a trend, not a feature)."""
    M = _frame(conn, "SELECT series, obs_date, value FROM idx.macro WHERE series = ANY(%s) ORDER BY series, obs_date", (MACRO_SERIES,),
               ["series", "obs", "value"])
    M["obs"] = pd.to_datetime(M["obs"])
    M["value"] = pd.to_numeric(M["value"], errors="coerce")
    M["d"] = [release_date(s, o) for s, o in zip(M["series"], M["obs"], strict=True)]
    cpi = M[M["series"] == "id_cpi"].sort_values("obs")
    if len(cpi) > 12:
        yoy = np.log(cpi["value"].to_numpy(float))
        yoy = pd.Series(yoy - np.r_[np.full(12, np.nan), yoy[:-12]], index=cpi.index)
        M.loc[cpi.index, "value"] = yoy
        M.loc[cpi.index, "series"] = "id_cpi_yoy"
    bps = M["series"] == "id_inflation_yoy"                             # BPS y/y in pct -> the same log y/y; wins over the OECD index on overlap
    M.loc[bps, "value"] = np.log1p(pd.to_numeric(M.loc[bps, "value"], errors="coerce") / 100.0)
    M.loc[bps, "series"] = "id_cpi_yoy"
    M.loc[bps, "obs"] = M.loc[bps, "obs"] + pd.Timedelta(seconds=1)      # sorts after the OECD row of the same month -> keep="last"
    hist = M["series"] == "bi_rate_hist"
    M.loc[hist, "series"] = "bi_rate"                                    # one policy-rate series; the event rows win on overlap
    M = M.sort_values(["series", "d", "obs"]).drop_duplicates(["series", "d"], keep="last")
    W = M.pivot_table(index="d", columns="series", values="value", aggfunc="last").sort_index().ffill()
    out = pd.DataFrame(index=W.index)
    for sname in list(W.columns):
        if sname in MACRO_RET:
            out[f"{sname}_r20"] = np.log(W[sname].where(W[sname] > 0)).diff(20)
        if sname not in MACRO_RET or sname == "vix":
            out[sname] = W[sname]
    return out.reset_index().rename(columns={"index": "d"})


def load_fundamentals(conn: psycopg.Connection) -> pd.DataFrame:
    F = _frame(conn, """
        SELECT code, published_at::date, months, net_profit, net_profit_yoy, revenue_yoy, roe, roa, der, net_margin, cfo, bvps, shares_out
          FROM idx.fundamental WHERE published_at IS NOT NULL AND months > 0 ORDER BY code, published_at""", (),
        ["code", "pub", "months", "net_profit", "np_yoy", "rev_yoy", "roe", "roa", "der", "net_margin", "cfo", "bvps", "shares_out"])
    F = _num(F, [c for c in F.columns if c not in ("code", "pub")])
    F["pub"] = pd.to_datetime(F["pub"])
    F["cfo_pos"] = (F["cfo"] > 0).astype(float).where(F["cfo"].notna())
    F["profitable"] = (F["net_profit"] > 0).astype(float).where(F["net_profit"].notna())
    F["np_annual"] = F["net_profit"] * 12.0 / F["months"]
    return F.drop(columns=["cfo", "net_profit"])


def load_broker_flow(conn: psycopg.Connection) -> pd.DataFrame:
    """Per (code, day): buyer/seller concentration and the foreign share of value on the regular board (1-day window)."""
    R = _frame(conn, """
        SELECT code, date_to, side, investor_type, broker, sum(value) AS value
          FROM idx.broker_flow
         WHERE period = 'TB_PERIOD_LAST_1_DAY' AND market_board = 'MARKET_BOARD_REGULER' AND investor_type IN ('INVESTOR_TYPE_ALL', 'INVESTOR_TYPE_FOREIGN')
         GROUP BY 1, 2, 3, 4, 5""", (), ["code", "d", "side", "inv", "broker", "value"])
    if R.empty:
        return pd.DataFrame(columns=["code", "d"])
    R["value"] = pd.to_numeric(R["value"], errors="coerce").astype(float)
    R["d"] = pd.to_datetime(R["d"])
    A = R[R["inv"] == "INVESTOR_TYPE_ALL"]
    tot = A.groupby(["code", "d", "side"])["value"].sum().rename("tot")
    A = A.join(tot, on=["code", "d", "side"])
    A["share"] = A["value"] / A["tot"].replace(0, np.nan)
    g = A.groupby(["code", "d", "side"])
    conc = pd.DataFrame({"hhi": g["share"].apply(lambda s: float((s ** 2).sum())), "top1": g["share"].max(), "n": g["share"].count()}).reset_index()
    out = conc.pivot(index=["code", "d"], columns="side", values=["hhi", "top1", "n"])
    out.columns = [f"bf_{a}_{b.lower()}" for a, b in out.columns]
    out = out.rename(columns={"bf_hhi_buy": "bf_hhi_buy", "bf_n_buy": "bf_nbuy", "bf_n_sell": "bf_nsell"})
    fo = R[R["inv"] == "INVESTOR_TYPE_FOREIGN"].groupby(["code", "d", "side"])["value"].sum().rename("f")
    al = tot.rename("a")
    fs = pd.concat([fo, al], axis=1)
    fs["share"] = fs["f"] / fs["a"].replace(0, np.nan)
    fs = fs["share"].unstack("side")
    out["bf_foreign_buy_share"] = fs.get("BUY")
    out["bf_foreign_sell_share"] = fs.get("SELL")
    return out.reset_index()


def load_sentiment(conn: psycopg.Connection) -> pd.DataFrame:
    S = _frame(conn, "SELECT code, trade_date, decayed_score, n_negative_material FROM idx.sentiment_daily", (), ["code", "d", "sent_score", "sent_neg"])
    S["d"] = pd.to_datetime(S["d"])
    return _num(S, ["sent_score", "sent_neg"])


def load_consensus(conn: psycopg.Connection) -> pd.DataFrame:
    C = _frame(conn, "SELECT code, snapshot_date, upside_pct, reco_mean, n_analysts FROM idx.consensus ORDER BY code, snapshot_date", (),
               ["code", "cd", "cons_upside", "cons_reco", "cons_n"])
    C["cd"] = pd.to_datetime(C["cd"])
    return _num(C, ["cons_upside", "cons_reco", "cons_n"])


def load_events(conn: psycopg.Connection) -> pd.DataFrame:
    E = _frame(conn, "SELECT code, trade_date, ev_ownership_30d, ev_exchange_query_10d, ev_dividend_30d, ev_buyback_30d, ev_material_30d, ev_rights_60d "
                     "FROM idx.feature_daily", (), ["code", "d", "ev_ownership", "ev_query", "ev_dividend", "ev_buyback", "ev_material", "ev_rights"])
    E["d"] = pd.to_datetime(E["d"])
    return _num(E, ["ev_ownership", "ev_query", "ev_dividend", "ev_buyback", "ev_material", "ev_rights"])


def load_sectors(conn: psycopg.Connection) -> pd.DataFrame:
    L = _frame(conn, "SELECT code, sector FROM idx.listing", (), ["code", "sector_name"])
    cats = {s: i for i, s in enumerate(sorted(L["sector_name"].dropna().unique()))}
    L["sector"] = L["sector_name"].map(cats).astype(float)
    return L[["code", "sector"]]


# ---- features -----------------------------------------------------------------------------------------------------------
def _streak_up(ret1: np.ndarray, codes: np.ndarray) -> np.ndarray:
    out = np.zeros(len(ret1))
    for i in range(len(ret1)):
        same = i > 0 and codes[i] == codes[i - 1]
        out[i] = (out[i - 1] + 1) if (same and ret1[i] > 0) else float(ret1[i] > 0)
    return out


def price_features(B: pd.DataFrame) -> pd.DataFrame:
    B = B.sort_values(["code", "d"]).reset_index(drop=True)
    adj = B["adj"].fillna(1.0)
    B["ac"], B["ah"], B["al"], B["ao"] = B["close"] * adj, B["high"] * adj, B["low"] * adj, B["open"] * adj
    g = B.groupby("code", sort=False)
    lc = np.log(B["ac"])
    B["lc"] = lc
    for k in (1, 5, 20, 60, 120, 250):
        B[f"ret{k}"] = lc - g["lc"].shift(k)
    for k in (20, 50, 200):
        B[f"dist_ma{k}"] = B["ac"] / g["ac"].transform(lambda x, k=k: x.rolling(k, min_periods=max(5, k // 2)).mean()) - 1
    B["vol20"] = g["ret1"].transform(lambda x: x.rolling(20, min_periods=10).std())
    B["vol60"] = g["ret1"].transform(lambda x: x.rolling(60, min_periods=20).std())
    prev = g["ac"].shift(1)
    B["atr_pct"] = ((B["ah"] - B["al"]) / prev).groupby(B["code"]).transform(lambda x: x.rolling(14, min_periods=5).mean())
    hi20 = g["ah"].transform(lambda x: x.rolling(20, min_periods=5).max())
    lo20 = g["al"].transform(lambda x: x.rolling(20, min_periods=5).min())
    B["pos20"] = (B["ac"] - lo20) / (hi20 - lo20).replace(0, np.nan)
    B["dist_hi252"] = B["ac"] / g["ah"].transform(lambda x: x.rolling(252, min_periods=60).max()) - 1
    B["dist_lo252"] = B["ac"] / g["al"].transform(lambda x: x.rolling(252, min_periods=60).min()) - 1
    v20 = g["volume"].transform(lambda x: x.rolling(20, min_periods=5).mean()).replace(0, np.nan)
    B["volr1"] = B["volume"] / v20
    B["volr5"] = g["volume"].transform(lambda x: x.rolling(5, min_periods=3).mean()) / v20
    B["value20"] = g["value"].transform(lambda x: x.rolling(20, min_periods=5).mean())
    B["lvalue20"] = np.log1p(B["value20"])
    B["lvalue60"] = np.log1p(g["value"].transform(lambda x: x.rolling(60, min_periods=20).mean()))
    B["gap"] = B["ao"] / prev - 1
    rng = (B["ah"] - B["al"]).replace(0, np.nan)
    B["clv"] = (B["ac"] - B["al"]) / rng
    B["up_days"] = _streak_up(B["ret1"].fillna(0).to_numpy(), B["code"].to_numpy())
    B["dow"] = B["d"].dt.dayofweek.astype(float)
    B["month"] = B["d"].dt.month.astype(float)
    B["age"] = np.log1p(g.cumcount().astype(float))
    # the day's tape
    B["freq_ratio"] = B["frequency"] / g["frequency"].transform(lambda x: x.rolling(20, min_periods=5).mean()).replace(0, np.nan)
    B["spread_bps"] = (B["offer"] - B["bid"]) / B["close"] * 1e4
    B.loc[(B["bid"] <= 0) | (B["offer"] <= 0), "spread_bps"] = np.nan
    bo = B["bid_vol"] + B["offer_vol"]
    B["bo_imb"] = (B["bid_vol"] - B["offer_vol"]) / bo.replace(0, np.nan)
    fnet = (B["fbuy"] - B["fsell"]) * B["close"]
    B["fnet1"] = fnet / B["value20"].replace(0, np.nan)
    B["fnet5"] = fnet.groupby(B["code"]).transform(lambda x: x.rolling(5, min_periods=3).sum()) / B["value20"].replace(0, np.nan)
    B["fnet20"] = fnet.groupby(B["code"]).transform(lambda x: x.rolling(20, min_periods=10).sum()) / B["value20"].replace(0, np.nan)
    B["mcap"] = B["close"] * B["listed"]
    B["lmcap"] = np.log(B["mcap"].where(B["mcap"] > 0))
    B["free_float"] = B["tradeable"] / B["listed"].replace(0, np.nan)
    B["idx_weight"] = B["weight"]
    B["nonreg_share"] = B["nonreg_value"].fillna(0) / (B["value"] + B["nonreg_value"].fillna(0)).replace(0, np.nan)
    return B


def cross_section(B: pd.DataFrame) -> pd.DataFrame:
    liquid = B["value20"] >= MIN_VALUE20_FIT
    gd = B[liquid].groupby("d")
    for k in ("ret1", "ret20", "ret60"):
        B[f"xs_r{k[3:]}"] = gd[k].rank(pct=True)
    B["breadth"] = gd["ret1"].transform(lambda x: (x > 0).mean())
    B["sec_r20"] = B[liquid].groupby(["d", "sector"])["ret20"].transform("mean")
    return B


def labels(B: pd.DataFrame) -> pd.DataFrame:
    """Forward log return per horizon; for the excess horizons minus the COMPOSITE's over the same window, so the model
    learns selection (which name beats the market) instead of the market's direction."""
    g = B.groupby("code", sort=False)
    for h in DAILY:
        fwd = g["lc"].shift(-h.steps) - B["lc"]
        if h.basis == "excess" and f"comp_fwd_{h.key}" in B:
            fwd = fwd - B[f"comp_fwd_{h.key}"]
        B[f"fwd_{h.key}"] = fwd
    return B


def build_panel(conn: psycopg.Connection, since: date | None = None) -> pd.DataFrame:
    """Everything joined, PIT-safe. ~1.4 M rows for the whole history; use ``since`` for the prediction cut."""
    B = load_bars(conn, since)
    if B.empty:
        return B
    B = price_features(B)
    B = B.merge(load_sectors(conn), on="code", how="left")
    B = cross_section(B)
    B = B.merge(load_index(conn), on="d", how="left")
    B = pd.merge_asof(B.sort_values("d"), load_macro(conn).sort_values("d"), on="d", direction="backward").sort_values(["code", "d"])
    F = load_fundamentals(conn)
    B = B.assign(pub_key=B["d"]).sort_values("pub_key")
    B = pd.merge_asof(B, F.sort_values("pub"), left_on="pub_key", right_on="pub", by="code", direction="backward")
    B["stale_days"] = (B["d"] - B["pub"]).dt.days.astype(float)
    B["pe"] = B["mcap"] / B["np_annual"].where(B["np_annual"] > 0)
    B["pb"] = B["close"] / B["bvps"].where(B["bvps"] > 0)
    B = B.drop(columns=["pub_key", "pub", "np_annual", "bvps", "shares_out"], errors="ignore")
    BF = load_broker_flow(conn)
    if not BF.empty:
        B = B.merge(BF, on=["code", "d"], how="left")
    B = B.merge(load_sentiment(conn), on=["code", "d"], how="left")
    C = load_consensus(conn)
    if not C.empty:
        B = pd.merge_asof(B.assign(ck=B["d"]).sort_values("ck"), C.sort_values("cd"), left_on="ck", right_on="cd", by="code",
                          direction="backward").drop(columns=["ck", "cd"])
    B = B.merge(load_events(conn), on=["code", "d"], how="left")
    B = B.sort_values(["code", "d"]).reset_index(drop=True)
    B = labels(B)
    for c in FEATURES:
        if c not in B:
            B[c] = np.nan
    return B


def fit_rows(P: pd.DataFrame) -> pd.DataFrame:
    return P[(P["close"] >= MIN_CLOSE) & (P["value20"] >= MIN_VALUE20_FIT)]


def latest_rows(P: pd.DataFrame) -> pd.DataFrame:
    """The rows to score: each name's last bar on the panel's last date, above the liquidity floor."""
    last = P["d"].max()
    L = P[(P["d"] == last) & (P["close"] >= MIN_CLOSE) & (P["value20"] >= MIN_VALUE20_PREDICT)]
    return L


def history_days_for(since_days: int = 420) -> date:
    return date.today() - timedelta(days=since_days)
