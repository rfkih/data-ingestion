"""The online learning agent: a virtual Rp 20 M book that trades the live tick feed and learns from every new session
(operator, 2026-09-25: "kalau untung dapet reward, kita kasih modal" -> "semenjak 3 hari terakhir kita sudah stream data
live feed ... kita pake itu aja" -> "iya boleh").

Why online and not trained on history: five sessions are five market days - an agent fitted on them learns "Monday went up".
Trading forward on paper and learning after each session makes every decision out-of-sample by construction, and the record it
builds is the honest walk-forward.

WHAT IT DOES. At fixed decision minutes (Mon-Thu 09:15 10:00 11:00 13:45 14:30; Fri 09:15 10:00 11:00 14:15 14:45 WIB) it looks
at every name the tick collector carries and may buy up to 3 of them (10 positions open at most), Rp 2 M each, choosing per
name one of ACTIONS (targets larger than the ~0.5 % round trip - menu 30's lead; one-tick moves never pay the spread, menus
28/31) or nothing. At the end of its holding time a position is sold at the bid of the last grid minute of that session.
PAPER ONLY: nothing here places an order.
FILL MODEL (settled from the tape after the close): buy at the best offer at the end of the decision minute + 0.10 % fee;
the take-profit fills when a later minute's high reaches it; the stop when a minute's low reaches it, at one tick below
(a minute that touches both counts as the stop - conservative); sell fee 0.20 %; whole lots of 100.
WHAT IT SEES: the intraday desk's minute features (ml/intraday.py - the same code path live and in settlement, so what it
learned on is what it acts on) and yesterday's broker tape for the name (share of the value bought net by the top-3 net
buyers, buyer concentration HHI; idx.broker_summary 1-day windows, strictly before the day).
HOW IT LEARNS: full feedback - after each session the tape says what EVERY action would have paid for EVERY name at every
decision minute (idx.agent_sample), not only for the trades taken. One Bayesian linear model per action on those rewards
(ridge prior, rewards clipped to +-5 %); at each decision it takes the names whose PESSIMISTIC expected reward (posterior mean
minus one posterior sd) clears +0.3 %, best first. (Thompson sampling until the 2026-09-25 replay - see ``scores``.)
ACTIONS: TP1 / TP2 sold by the close; H1 / H2 / H5 held up to 1 / 2 / 5 sessions after the entry day with wider brackets
(operator: "akhir hari ga harus menjual"); an action is used only once it has matured samples (H5 needs six sessions).
THE PLACEBO: agent 'random' takes the same number of names at the same minutes, drawn at random with a random bracket. After
20 sessions the ts agent is judged against it (rule declared in docs, not here); until then the numbers are noise.
"""
from __future__ import annotations

import json
import logging
import math
from datetime import date, datetime, time, timedelta
from typing import Any

import numpy as np
import pandas as pd
import psycopg
from psycopg.rows import tuple_row

from .ml import intraday as I
from .ml.common import WIB, tick

logger = logging.getLogger(__name__)

CAPITAL, SLOT_RP, LOT = 20_000_000.0, 2_000_000.0, 100
MAX_PER_DECISION, MAX_OPEN = 3, 10                    # 10 open positions x Rp 2 M = the whole Rp 20 M
FEE_B, FEE_S = 0.0010, 0.0020
# (take profit, stop, sessions it may be held AFTER the entry day). 0 = sold by the close of the entry day. Wider brackets for
# longer holds: a price's range grows with time, and a +-2 % bracket held a week is mostly a coin toss on the stop.
# Operator 2026-09-25: "akhir hari ga harus menjual bisa hold sampe besok lusa atau minggu depan".
ACTIONS: dict[str, tuple[float, float, int]] = {"TP1": (0.01, 0.01, 0), "TP2": (0.02, 0.02, 0),
                                                "H1": (0.03, 0.03, 1), "H2": (0.04, 0.04, 2), "H5": (0.06, 0.05, 5)}
MIN_EDGE = 0.003                                      # a drawn expected reward must clear +0.3 % (operator, 2026-09-25)
DECISIONS = {"mon-thu": [time(9, 15), time(10, 0), time(11, 0), time(13, 45), time(14, 30)],
             "fri": [time(9, 15), time(10, 0), time(11, 0), time(14, 15), time(14, 45)]}
TAPE_FEATS = ["r5", "r15", "r30", "r60", "rv15", "vwap_dev", "volr5", "imb5", "imb15", "obi", "obi3", "spread_bps", "micro_dev",
              "tod", "day_ret", "gap", "day_pos", "day_range", "mom20", "vol20", "lvalue20", "dist_ma200", "b_top3", "b_hhi"]
# The desk's own tools as inputs (operator, 2026-09-25: "agen bisa menggunakan tools yang kita punya juga"), each only as it
# stood BEFORE the decision: the intraday ML's P(up) scored at the decision minute (10/30/60 min), the daily ML's forecasts
# made the evening before (1d P(up), 5d P(up) and return), yesterday's chart state (idx/stock_state.py) and how long it has
# lasted, and the ARA model's P(lock) from the evening before (0 when the name was not on its list). A tool with no reading
# for a (name, time) is left missing - the scaler maps missing to the average, i.e. "no information".
TOOL_FEATS = ["ml10_up", "ml30_up", "ml60_up", "ml1d_up", "ml5d_up", "ml5d_ret",
              "st_breakout", "st_breakdown", "st_sideways", "st_uptrend", "st_downtrend", "st_since", "ara_lock"]
FEATS = TAPE_FEATS + TOOL_FEATS
PRIOR, CLIP = 10.0, 0.05


# ------------------------------------------------------------------------------------------------------------ pure
def decision_minutes(d: date) -> list[datetime]:
    if d.weekday() >= 5:
        return []
    ts = DECISIONS["fri"] if d.weekday() == 4 else DECISIONS["mon-thu"]
    return [datetime.combine(d, t, tzinfo=WIB) for t in ts]


def tp_sl_prices(entry: float, tp: float, sl: float) -> tuple[float, float]:
    """On the tick grid: the target rounded UP, the stop rounded DOWN (never better than asked)."""
    t_up, t_dn = tick(entry * (1 + tp)), tick(entry * (1 - sl))
    return math.ceil(entry * (1 + tp) / t_up) * t_up, math.floor(entry * (1 - sl) / t_dn) * t_dn


def outcome(entry: float, tp: float, sl: float, highs: np.ndarray, lows: np.ndarray, last_bid: float, last_close: float,
            opens: np.ndarray | None = None) -> tuple[float, str, int]:
    """Pure. Walk the minutes AFTER the entry minute: -> (exit price, 'tp' | 'sl' | 'time', minutes walked).
    A minute that OPENS through the stop (an overnight gap down) is sold at that open, not at the stop; one that opens through
    the target is counted at the target (the resting limit would have filled at least there)."""
    tp_px, sl_px = tp_sl_prices(entry, tp, sl)
    for k in range(len(highs)):
        o = opens[k] if opens is not None else float("nan")
        if np.isfinite(o) and o <= sl_px:
            return float(min(o, sl_px - tick(sl_px))), "sl", k + 1
        lo, hi = lows[k], highs[k]
        if np.isfinite(lo) and lo <= sl_px:
            return sl_px - tick(sl_px), "sl", k + 1
        if np.isfinite(hi) and hi >= tp_px:
            return tp_px, "tp", k + 1
    ex = last_bid if np.isfinite(last_bid) and last_bid > 0 else last_close - tick(last_close)
    return float(ex), "time", len(highs)


def reward(entry: float, exit_px: float) -> float:
    return exit_px * (1 - FEE_S) / (entry * (1 + FEE_B)) - 1


MIN_SESSIONS = 3                                      # an action is tradeable only once its samples span 3 sessions


def fit(S: pd.DataFrame) -> dict[str, Any]:
    """Per-action Bayesian linear posterior on the counterfactual samples. S: columns FEATS + action + reward (+ d, the session).

    The samples of one session are NOT independent: every name moves with that day's market (the 2026-09-25 samples: 13-22 %
    of a reward's variance is shared by the names of the same decision minute). Treated as independent, 550 rows from ONE day
    looked like overwhelming evidence and the replay's agent bet the book on it (H1 on 09-24, -2.8 % a trade). So the posterior
    covariance is inflated by the design effect 1 + (m - 1) rho (m = rows per session, rho = the share of residual variance
    that is common to a session), and an action with samples from fewer than MIN_SESSIONS sessions is left out."""
    X0 = S[FEATS].astype(float)
    mean, std = X0.mean().fillna(0.0), X0.std().replace(0, 1.0).fillna(1.0)
    out: dict[str, Any] = {"feats": FEATS, "mean": mean.tolist(), "std": std.tolist(), "actions": {}}
    for a in ACTIONS:
        s = S[S["action"] == a]
        n_sess = int(s["d"].nunique()) if "d" in s else 0
        if len(s) < 50 or ("d" in s and n_sess < MIN_SESSIONS):
            continue
        X = _design(s[FEATS].astype(float).to_numpy(), mean.to_numpy(), std.to_numpy())
        y = np.clip(s["reward"].to_numpy(float), -CLIP, CLIP)
        A = PRIOR * np.eye(X.shape[1]) + X.T @ X
        mu = np.linalg.solve(A, X.T @ y)
        resid = y - X @ mu
        sigma2 = float(max(np.var(resid), 1e-8))
        deff = 1.0
        if "d" in s and n_sess > 1:
            rbar = pd.Series(resid, index=s.index).groupby(s["d"].values).mean()
            m = len(s) / n_sess
            rho = float(np.clip((rbar.var() - sigma2 / m) / sigma2, 0.0, 1.0)) if sigma2 > 0 else 0.0
            deff = 1.0 + (m - 1.0) * rho
        out["actions"][a] = {"mu": mu.tolist(), "cov": (deff * sigma2 * np.linalg.inv(A)).tolist(), "sigma2": sigma2, "n": len(s),
                             "sessions": n_sess, "design_effect": round(deff, 2), "mean_reward": float(y.mean())}
    return out


def _design(X: np.ndarray, mean: np.ndarray, std: np.ndarray) -> np.ndarray:
    Z = np.nan_to_num((X - mean) / std, nan=0.0, posinf=0.0, neginf=0.0)
    return np.hstack([np.ones((len(Z), 1)), np.clip(Z, -5, 5)])


Z_LCB = 1.0


def scores(model: dict[str, Any], F: pd.DataFrame, rng: np.random.Generator | None = None, z: float = Z_LCB) -> dict[str, np.ndarray]:
    """PESSIMISTIC expected reward per (candidate, action): the posterior mean minus z posterior standard deviations of the
    prediction (a lower confidence bound).

    Changed from Thompson sampling on 2026-09-25 after the walk-forward replay: Thompson turns uncertainty into optimism so the
    agent explores - worth paying for only when an agent learns from its own trades alone. This one learns from the tape's
    answer for EVERY name and action (full feedback), so exploring buys no information and only costs spread and fees: with a
    one-day-old action (H1) the Thompson agent filled all 10 slots and lost -2.8 % a trade. The bound makes a thinly observed
    action or name ineligible until the model is sure. ``z = 0`` gives the plain posterior mean. ``rng`` is unused (kept so
    callers need not change)."""
    X = _design(F[model["feats"]].astype(float).to_numpy(), np.array(model["mean"]), np.array(model["std"]))
    out = {}
    for a, p in model["actions"].items():
        mu, cov = np.array(p["mu"]), np.array(p["cov"])
        sd = np.sqrt(np.maximum(np.einsum("ij,jk,ik->i", X, cov, X), 0.0))
        out[a] = X @ mu - z * sd
    return out


def choose(codes: list[str], sc: dict[str, np.ndarray], taken: set[str], room: int) -> list[tuple[str, str, float]]:
    """Pure. Best (code, action) pairs whose drawn reward clears MIN_EDGE, one action per code, codes not already held."""
    best: dict[str, tuple[str, float]] = {}
    for a, v in sc.items():
        for c, s in zip(codes, v, strict=True):
            if c in taken or not np.isfinite(s) or s <= MIN_EDGE:
                continue
            if c not in best or s > best[c][1]:
                best[c] = (a, float(s))
    ranked = sorted(best.items(), key=lambda kv: -kv[1][1])
    return [(c, a, s) for c, (a, s) in ranked[:max(0, min(MAX_PER_DECISION, room))]]


# ------------------------------------------------------------------------------------------------------------ data
def _rows(conn: psycopg.Connection, sql: str, params: tuple = ()) -> list[tuple]:
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def broker_feats(conn: psycopg.Connection, d: date) -> pd.DataFrame:
    """Yesterday's broker tape per name (the latest 1-day window strictly before d)."""
    rows = _rows(conn, """
        SELECT code, broker, buy_value, net_value FROM idx.broker_summary
         WHERE date_from = date_to AND investor_type = 'INVESTOR_TYPE_ALL' AND market_board = 'MARKET_BOARD_REGULER'
           AND date_to = (SELECT max(date_to) FROM idx.broker_summary WHERE date_from = date_to AND date_to < %s)""", (d,))
    if not rows:
        return pd.DataFrame(columns=["code", "b_top3", "b_hhi"])
    B = pd.DataFrame(rows, columns=["code", "broker", "buy", "net"]).astype({"buy": float, "net": float})
    out = []
    for code, g in B.groupby("code"):
        tot = g["buy"].sum()
        if tot <= 0:
            continue
        top3 = g["net"].clip(lower=0).nlargest(3).sum()
        sh = g["buy"] / tot
        out.append((code, float(top3 / tot), float((sh ** 2).sum())))
    return pd.DataFrame(out, columns=["code", "b_top3", "b_hhi"])


def tool_feats(conn: psycopg.Connection, d: date, P: pd.DataFrame) -> pd.DataFrame:
    """Attach TOOL_FEATS to the candidate rows P (code, minute). Point in time: intraday scores at or before the minute (within
    5 min), everything daily strictly before day d."""
    day0 = datetime.combine(d, time(0, 0), tzinfo=WIB)
    codes = sorted(P["code"].unique())
    # intraday ML, scored every grid minute
    rows = _rows(conn, """SELECT code, made_at, horizon, p_up FROM idx.ml_prediction
                           WHERE horizon IN ('10m', '30m', '60m') AND made_at >= %s AND made_at < %s AND code = ANY(%s)""",
                 (day0, day0 + timedelta(days=1), codes))
    out = P.copy()
    if rows:
        Q = pd.DataFrame(rows, columns=["code", "minute", "h", "p"])
        Q["minute"] = pd.to_datetime(Q["minute"], utc=True).dt.tz_convert(WIB)
        Q = Q.pivot_table(index=["code", "minute"], columns="h", values="p").reset_index().sort_values("minute")
        Q = Q.rename(columns={"10m": "ml10_up", "30m": "ml30_up", "60m": "ml60_up"})
        out = pd.merge_asof(out.sort_values("minute"), Q, on="minute", by="code", direction="backward", tolerance=pd.Timedelta(minutes=5))
    # daily ML, the evening before
    rows = _rows(conn, """SELECT DISTINCT ON (code, horizon) code, horizon, p_up, pred_ret FROM idx.ml_prediction
                           WHERE horizon IN ('1d', '5d') AND made_at < %s AND code = ANY(%s) ORDER BY code, horizon, made_at DESC""",
                 (day0, codes))
    if rows:
        D = pd.DataFrame(rows, columns=["code", "h", "p", "r"])
        D = D.pivot_table(index="code", columns="h", values=["p", "r"])
        D.columns = [f"{a}_{b}" for a, b in D.columns]
        D = D.rename(columns={"p_1d": "ml1d_up", "p_5d": "ml5d_up", "r_5d": "ml5d_ret"}).reset_index()
        out = out.merge(D[[c for c in ("code", "ml1d_up", "ml5d_up", "ml5d_ret") if c in D.columns]], on="code", how="left")
    # yesterday's chart state
    from . import stock_state as ss
    prev = _rows(conn, "SELECT max(trade_date) FROM idx.bar WHERE source = 'idx' AND trade_date < %s", (d,))
    if prev and prev[0][0]:
        adj, vol, _ = ss._panel(conn, prev[0][0], codes)
        if not adj.empty:
            st, _ = ss.classify_panel(adj, vol)
            last = st.iloc[-1]
            S = pd.DataFrame({"code": st.columns, "state": last.values, "st_since": [ss.streak(st[c]) for c in st.columns]})
            for s_ in ("breakout", "breakdown", "sideways", "uptrend", "downtrend"):
                S[f"st_{s_}"] = (S["state"] == s_).astype(float)
            out = out.merge(S.drop(columns=["state"]), on="code", how="left")
    # ARA model, the evening before (not on the list = 0)
    rows = _rows(conn, """SELECT code, p_lock FROM idx.ara_watch
                           WHERE run_date = (SELECT max(run_date) FROM idx.ara_watch WHERE run_date < %s)""", (d,))
    A = pd.DataFrame(rows, columns=["code", "ara_lock"]) if rows else pd.DataFrame(columns=["code", "ara_lock"])
    A["ara_lock"] = pd.to_numeric(A["ara_lock"], errors="coerce")
    out = out.merge(A, on="code", how="left")
    out["ara_lock"] = out["ara_lock"].fillna(0.0) if rows else np.nan
    for c in TOOL_FEATS:
        if c not in out:
            out[c] = np.nan
    return out


def candidates(conn: psycopg.Connection, d: date, now: datetime | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(features at the decision minute(s), the raw minutes of the day). ``now`` given: live - the latest grid minute only;
    otherwise every decision minute of a past day (settlement / warm start)."""
    M = I.load_minutes(conn, d, d)
    if M.empty:
        return pd.DataFrame(), M
    if now is not None:
        P, _ = I.live_rows(conn, now)
    else:
        P = I.build_panel(conn, [d])
        if not P.empty:
            P = P[P["minute"].isin(pd.DatetimeIndex(decision_minutes(d)))]
    if P.empty:
        return P, M
    P = P.merge(broker_feats(conn, d), on="code", how="left")
    book = M[["code", "minute", "off_px"]].rename(columns={"off_px": "entry_px"})
    P = P.merge(book, on=["code", "minute"], how="left")
    P = P[P["entry_px"].notna() & (P["entry_px"] > 0)]
    if not P.empty:
        P = tool_feats(conn, d, P)
    return P.reset_index(drop=True), M


def _paths(M: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {c: g.sort_values("minute").set_index("minute") for c, g in M.groupby("code")}


def horizon_end(sessions: list[date], d: date, hold: int) -> tuple[date, bool]:
    """Pure. The last session a position opened on ``d`` may be held to, and whether that session has happened yet
    (sessions = the feed's session dates, sorted). Not happened: the end is the latest session known so far."""
    i = sessions.index(d) if d in sessions else len([s for s in sessions if s < d])
    j = i + hold
    return (sessions[j], True) if j < len(sessions) else (sessions[-1], False)


def _settle_one(paths: dict[str, pd.DataFrame], code: str, minute: pd.Timestamp, entry: float, action: str,
                end_day: date, matured: bool) -> tuple[float, str, pd.Timestamp] | None:
    """(exit price, reason, exit minute), or None while the answer is not known yet: no minutes after the entry, or the
    position has neither hit its bracket nor reached the end of its holding time."""
    g = paths.get(code)
    if g is None:
        return None
    after = g[(g.index > minute) & (g.index.date <= end_day)]
    if after.empty:
        return None
    tp, sl, _ = ACTIONS[action]
    ex, why, k = outcome(entry, tp, sl, after["high"].to_numpy(float), after["low"].to_numpy(float),
                         float(after["bid_px"].iloc[-1]) if pd.notna(after["bid_px"].iloc[-1]) else float("nan"),
                         float(after["close"].iloc[-1]), after["open"].to_numpy(float))
    if why == "time" and not matured:
        return None
    return ex, why, after.index[k - 1]


# ------------------------------------------------------------------------------------------------------------ jobs
def latest_model(conn: psycopg.Connection) -> tuple[int | None, dict[str, Any] | None]:
    r = _rows(conn, "SELECT id, params FROM idx.agent_model ORDER BY id DESC LIMIT 1")
    if not r:
        return None, None
    p = r[0][1]
    return r[0][0], (p if isinstance(p, dict) else json.loads(p))


def decide(conn: psycopg.Connection, now: datetime | None = None, rng: np.random.Generator | None = None) -> dict[str, Any]:
    """One decision minute, live: the ts agent's picks and the random placebo's, written to idx.agent_decision."""
    now = now or datetime.now(WIB)
    d = now.astimezone(WIB).date()
    rng = rng or np.random.default_rng()
    mid, model = latest_model(conn)
    if model is None or not model.get("actions"):
        return {"ok": False, "why": "no model yet - run `idx agent warmstart`"}
    P, _ = candidates(conn, d, now)
    if P.empty:
        return {"ok": False, "why": "no live candidates (outside the session, or the feed has no minutes yet)"}
    minute = P["minute"].iloc[0]
    out = {"ok": True, "minute": minute.isoformat(), "candidates": len(P), "picks": {}}
    for agent in ("ts", "random"):
        # held = every position not yet settled (a multi-day one stays open until its bracket or its time is up; one that
        # hit its bracket earlier today is only known at tonight's settlement, so it still counts - conservative)
        held = {r[0] for r in _rows(conn, "SELECT code FROM idx.agent_decision WHERE agent = %s AND settled_at IS NULL", (agent,))}
        taken = held | {r[0] for r in _rows(conn, "SELECT code FROM idx.agent_decision WHERE agent = %s AND d = %s", (agent, d))}
        room = MAX_OPEN - len(held)
        if agent == "ts":
            sc = scores(model, P, rng)
            picks = choose(P["code"].tolist(), sc, taken, room)
        else:
            n = len(out["picks"].get("ts", []))
            pool = [c for c in P["code"] if c not in taken]
            k = min(n, room, len(pool))
            picks = [(c, str(rng.choice(list(ACTIONS))), None) for c in rng.choice(pool, size=k, replace=False)] if k > 0 else []
        with conn.cursor() as cur:
            for c, a, s in picks:
                row = P[P["code"] == c].iloc[0]
                cur.execute("""INSERT INTO idx.agent_decision (agent, d, minute, code, action, score, model_id, feats)
                               VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (agent, d, minute, code) DO NOTHING""",
                            (agent, d, minute.to_pydatetime(), c, a, s, mid if agent == "ts" else None,
                             json.dumps({f: (None if pd.isna(row.get(f)) else float(row.get(f))) for f in FEATS})))
        conn.commit()
        out["picks"][agent] = [(c, a, None if s is None else round(s, 5)) for c, a, s in picks]
    return out


def samples_for_day(conn: psycopg.Connection, d: date) -> int:
    """The counterfactual rewards of every (name, decision minute, action) of session d whose answer is known by now ->
    idx.agent_sample (upsert: a multi-day action's row appears once its bracket was hit or its holding time is over)."""
    P, _ = candidates(conn, d)
    if P.empty:
        return 0
    sessions = feed_days(conn)
    far, _ = horizon_end(sessions, d, max(h for _, _, h in ACTIONS.values()))
    paths = _paths(I.load_minutes(conn, d, far, sorted(P["code"].unique())))
    ends = {a: horizon_end(sessions, d, h) for a, (_, _, h) in ACTIONS.items()}
    rows = []
    for r in P.itertuples(index=False):
        rd = r._asdict()
        feats = json.dumps({f: (None if pd.isna(rd.get(f)) else float(rd.get(f))) for f in FEATS})
        for a in ACTIONS:
            if not ends[a][1]:
                # not matured: storing only the rows whose bracket already filled would teach the model from the early
                # hits alone (no 'time' exits yet) - a biased sample. The row waits for the end of its holding time.
                continue
            res = _settle_one(paths, rd["code"], rd["minute"], float(rd["entry_px"]), a, *ends[a])
            if res is None:
                continue
            ex, why, _ = res
            rows.append((d, rd["minute"].to_pydatetime(), rd["code"], a, feats, float(rd["entry_px"]), float(ex), why,
                         reward(float(rd["entry_px"]), float(ex))))
    with conn.cursor() as cur:
        cur.executemany("""INSERT INTO idx.agent_sample (d, minute, code, action, feats, entry_px, exit_px, exit_reason, reward)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                           ON CONFLICT (d, minute, code, action) DO UPDATE SET feats = EXCLUDED.feats, entry_px = EXCLUDED.entry_px,
                               exit_px = EXCLUDED.exit_px, exit_reason = EXCLUDED.exit_reason, reward = EXCLUDED.reward""", rows)
    conn.commit()
    return len(rows)


def _complete(conn: psycopg.Connection, d: date) -> bool:
    """Every candidate of session d has an answer for the longest action (the others are known earlier)."""
    r = _rows(conn, """SELECT count(*) FILTER (WHERE action = 'TP1'), count(*) FILTER (WHERE action = 'H5')
                         FROM idx.agent_sample WHERE d = %s""", (d,))
    return bool(r and r[0][0] and r[0][0] == r[0][1])


def settle_decisions(conn: psycopg.Connection) -> dict[str, Any]:
    """Paper-fill every open decision of both agents from the tape: closed once its bracket was hit or its time is up."""
    dec = _rows(conn, "SELECT id, d, minute, code, action FROM idx.agent_decision WHERE settled_at IS NULL ORDER BY d")
    if not dec:
        return {"settled": 0, "still_open": 0}
    sessions = feed_days(conn)
    n = still = 0
    by_day: dict[date, list] = {}
    for x in dec:
        by_day.setdefault(x[1], []).append(x)
    with conn.cursor() as cur:
        for d, items in by_day.items():
            far, _ = horizon_end(sessions, d, max(h for _, _, h in ACTIONS.values()))
            paths = _paths(I.load_minutes(conn, d, far, sorted({x[3] for x in items})))
            for did, _, minute, code, action in items:
                g = paths.get(code)
                mts = pd.Timestamp(minute).tz_convert(WIB)
                entry = float(g.loc[mts, "off_px"]) if g is not None and mts in g.index and g.loc[mts, "off_px"] > 0 else 0.0
                lots = int(SLOT_RP // (entry * (1 + FEE_B) * LOT)) if entry > 0 else 0
                if lots < 1:
                    cur.execute("UPDATE idx.agent_decision SET exit_reason = 'no_fill', settled_at = now(), pnl = 0, reward = 0 WHERE id = %s", (did,))
                    continue
                res = _settle_one(paths, code, mts, entry, action, *horizon_end(sessions, d, ACTIONS[action][2]))
                if res is None:
                    still += 1
                    continue
                ex, why, when = res
                pnl = lots * LOT * (ex * (1 - FEE_S) - entry * (1 + FEE_B))
                cur.execute("""UPDATE idx.agent_decision SET lots = %s, entry_px = %s, exit_px = %s, exit_at = %s, exit_reason = %s,
                               reward = %s, pnl = %s, settled_at = now() WHERE id = %s""",
                            (lots, entry, ex, when.to_pydatetime(), why, reward(entry, ex), round(pnl, 2), did))
                n += 1
    conn.commit()
    return {"settled": n, "still_open": still}


def refit(conn: psycopg.Connection, data_to: date) -> dict[str, Any]:
    rows = _rows(conn, "SELECT d, action, feats, reward FROM idx.agent_sample WHERE d <= %s", (data_to,))
    if not rows:
        return {"fitted": False, "why": "no samples"}
    S = pd.DataFrame([{**(f if isinstance(f, dict) else json.loads(f)), "d": d, "action": a, "reward": float(r)} for d, a, f, r in rows])
    for c in FEATS:
        if c not in S:
            S[c] = np.nan
    model = fit(S)
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute("INSERT INTO idx.agent_model (data_to, n, params) VALUES (%s, %s, %s) RETURNING id", (data_to, len(S), json.dumps(model)))
        mid = cur.fetchone()[0]
    conn.commit()
    return {"fitted": True, "model_id": mid, "n": len(S),
            "actions": {a: {"mean_reward": round(p["mean_reward"], 5), "sessions": p["sessions"], "design_effect": p["design_effect"]}
                        for a, p in model["actions"].items()}}


def feed_days(conn: psycopg.Connection) -> list[date]:
    return sorted(r[0] for r in _rows(conn, "SELECT DISTINCT trade_date FROM idx.feed_day"))


def settle(conn: psycopg.Connection, d: date) -> dict[str, Any]:
    """After the close: today's counterfactual samples, the multi-day ones of the last sessions that matured today, the two
    agents' paper fills (any open position), and tonight's model."""
    sessions = [s for s in feed_days(conn) if s <= d]
    recent = sessions[-(max(h for _, _, h in ACTIONS.values()) + 2):]
    n = {}
    for s in recent:
        if s == d or not _complete(conn, s):
            n[s.isoformat()] = samples_for_day(conn, s)
    st = settle_decisions(conn)
    m = refit(conn, d)
    return {"day": d.isoformat(), "samples": n, **st, "model": m}


def warmstart(conn: psycopg.Connection, resample: bool = False) -> dict[str, Any]:
    """Samples for every feed session not yet sampled (all of them with ``resample``, e.g. after new features), then a
    model. In-sample by definition: it only primes the agent."""
    have = set() if resample else {r[0] for r in _rows(conn, "SELECT DISTINCT d FROM idx.agent_sample")}
    done = {}
    for d in feed_days(conn):
        if d not in have:
            done[d.isoformat()] = samples_for_day(conn, d)
    days = feed_days(conn)
    return {"sampled": done, "model": refit(conn, days[-1]) if days else {"fitted": False}}


def report(conn: psycopg.Connection) -> dict[str, Any]:
    """Realised paper P&L per agent (by entry day), plus what is still open and the mix of actions taken."""
    rows = _rows(conn, """SELECT agent, d, count(*) FILTER (WHERE exit_reason IS DISTINCT FROM 'no_fill'), sum(pnl),
                                 count(*) FILTER (WHERE pnl > 0), count(*) FILTER (WHERE exit_reason = 'tp')
                            FROM idx.agent_decision WHERE settled_at IS NOT NULL GROUP BY 1, 2 ORDER BY 2, 1""")
    out: dict[str, Any] = {"capital": CAPITAL, "agents": {}}
    for agent, n_open in _rows(conn, "SELECT agent, count(*) FROM idx.agent_decision WHERE settled_at IS NULL GROUP BY 1"):
        out["agents"].setdefault(agent, {"days": [], "trades": 0, "wins": 0, "tp": 0, "pnl": 0.0})["open"] = int(n_open)
    for agent, action, n_a, avg_r in _rows(conn, """SELECT agent, action, count(*), avg(reward) FROM idx.agent_decision
                                                   WHERE settled_at IS NOT NULL AND exit_reason <> 'no_fill' GROUP BY 1, 2"""):
        out["agents"].setdefault(agent, {"days": [], "trades": 0, "wins": 0, "tp": 0, "pnl": 0.0}).setdefault("by_action", {})[action] = \
            {"n": int(n_a), "avg_reward": float(avg_r or 0)}
    for agent, d, n, pnl, win, tp in rows:
        a = out["agents"].setdefault(agent, {"days": [], "trades": 0, "wins": 0, "tp": 0, "pnl": 0.0})
        a["trades"] += int(n)
        a["wins"] += int(win)
        a["tp"] += int(tp)
        a["pnl"] += float(pnl or 0)
        a["days"].append({"d": d.isoformat(), "trades": int(n), "pnl": float(pnl or 0), "nav": CAPITAL + a["pnl"]})
    for a in out["agents"].values():
        a["nav"] = CAPITAL + a["pnl"]
        a["win_rate"] = a["wins"] / a["trades"] if a["trades"] else None
        a["sessions"] = len(a["days"])
    return out


def in_decision_window(now: datetime, slack_min: int = 3) -> datetime | None:
    """The decision minute ``now`` falls into (within slack), or None."""
    now = now.astimezone(WIB)
    for m in decision_minutes(now.date()):
        if m <= now < m + timedelta(minutes=slack_min):
            return m
    return None
