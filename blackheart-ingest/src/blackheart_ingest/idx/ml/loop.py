"""The learning loop: train (champion vs refresh vs tune on the same out-of-sample blocks), predict, realise, calibrate, score.

Validation (second pass, 2026-09-24): every contender is judged on K consecutive blocks of N_VAL days (daily 3 x 40,
intraday up to 3 x 1 day), each block with its own purged fit set - rows whose label window reaches into the block are
dropped (embargo = the horizon in trading days), so no fit row carries a block's outcome. ``primary`` is the mean over
the blocks; the deployed artifact is the fit for the newest block. The 20d+ horizons are labelled as excess return over
the COMPOSITE (spec.Horizon.basis). Probabilities are calibrated with an isotonic curve fitted on realised predictions.

Every entry point takes a connection and returns a plain dict the CLI prints and the scheduler logs. Commits happen
here, once per step, so a crash mid-training leaves the previous champions in place.
"""
from __future__ import annotations

import logging
import time as _time
from datetime import date, datetime, timedelta
from itertools import pairwise
from typing import Any

import numpy as np
import pandas as pd
import psycopg
from psycopg.rows import dict_row

from .. import runlog
from . import common, daily, intraday
from .common import UTC, WIB, Contender, Model
from .spec import HORIZONS, TASKS, Horizon, of_kind

logger = logging.getLogger(__name__)

N_VAL = {"daily": 40, "intraday": 1}           # one validation block, in distinct days
K_BLOCKS = {"daily": 3, "intraday": 3}          # blocks per contender (fewer when history is short)
RET_CLIP = {"daily": 1.0, "intraday": 0.1}      # log-return label clip (a 250-day 2.7x is +1.0; a 1-minute 10 % is a bad print)
MIN_FIT_ROWS = {"daily": 20000, "intraday": 5000}
MIN_FIT_DAYS = {"daily": 5, "intraday": 2}      # the feed is days old; the daily history is years
CAL_MIN_N = 400                                  # realised predictions needed before a calibration curve is fitted
CAL_DAYS = 60                                    # ... from the last this many days of cuts
LIQ_VALUE60 = 5e9                                # the `ret` primary is the per-cut rank IC on these names: what a book can buy
LIQ_MIN_PRICE = 100.0


# ---- training ----------------------------------------------------------------------------------------------------------
def _panel(conn: psycopg.Connection, kind: str) -> tuple[pd.DataFrame, list[str]]:
    if kind == "daily":
        P = daily.fit_rows(daily.build_panel(conn))
        return P, daily.FEATURES
    days = intraday.feed_days(conn)
    P = intraday.build_panel(conn, days)
    if P.empty:
        return P, intraday.FEATURES
    return intraday.fit_rows(P), intraday.FEATURES


def _label(P: pd.DataFrame, h: Horizon, task: str, kind: str) -> tuple[pd.DataFrame, np.ndarray]:
    col = f"fwd_{h.key}"
    R = P[P[col].notna()]
    if task == "dir":
        R = R[R[col] != 0]
        return R, (R[col] > 0).to_numpy(dtype=float)
    return R, R[col].clip(-RET_CLIP[kind], RET_CLIP[kind]).to_numpy(dtype=float)


def train(conn: psycopg.Connection, kind: str, *, tune: bool = True, today: date | None = None,
          horizons: list[str] | None = None, placebo: int = 0) -> dict[str, Any]:
    """Refit every (horizon, task) of ``kind`` on the matured rows and let the promotion rule pick tomorrow's model."""
    today = today or datetime.now(WIB).date()
    t0 = _time.time()
    rid = runlog.start(conn, f"ml_train_{kind}", str(today))
    conn.commit()
    rep: dict[str, Any] = {"kind": kind, "today": today, "models": [], "promoted": 0, "errors": []}
    try:
        P, feats = _panel(conn, kind)
        rep["panel_rows"] = len(P)
        if P.empty:
            raise RuntimeError(f"{kind}: no rows to fit")
        calendar = np.sort(pd.unique(P["d"]))
        rng = np.random.default_rng(int(today.strftime("%Y%m%d")))
        for h in of_kind(kind):
            if horizons and h.key not in horizons:
                continue
            for task in TASKS:
                try:
                    r = _train_one(conn, P, feats, calendar, h, task, kind, rng, tune, today, placebo)
                    rep["models"].append(r)
                    rep["promoted"] += int(r["promoted"])
                    conn.commit()
                except Exception as e:                          # one horizon failing must not take the others down
                    conn.rollback()
                    rep["errors"].append(f"{h.key}/{task}: {type(e).__name__}: {e}")
                    logger.exception("ml train %s/%s failed", h.key, task)
        rep["seconds"] = round(_time.time() - t0)
        rep["text"] = render_train(rep)
        rr = runlog.RunResult(job=f"ml_train_{kind}", run_key=str(today), status="ok" if not rep["errors"] else "partial",
                              rows_in=rep["panel_rows"], rows_out=len(rep["models"]), detail={"promoted": rep["promoted"], "errors": rep["errors"]})
        if rep["errors"]:
            rr.error = "; ".join(rep["errors"])[:500]
        runlog.finish(conn, rid, rr)
        runlog.alert(conn, "info", "ml", rep["text"], kind="ml", dedupe_key=f"ml_train_{kind}_{today}", notify_channels=False)
        conn.commit()
    except Exception as e:
        conn.rollback()
        rep["errors"].append(f"{type(e).__name__}: {e}")
        rep["text"] = render_train(rep)
        runlog.finish(conn, rid, runlog.RunResult(job=f"ml_train_{kind}", run_key=str(today), status="failed", error=str(e)[:500]))
        runlog.alert(conn, "warning", "ml", f"ML training ({kind}) gagal: {type(e).__name__}: {e}"[:400], kind="ml")
        conn.commit()
        logger.exception("ml train %s failed", kind)
    return rep


def _cuts(R: pd.DataFrame, kind: str) -> tuple[np.ndarray, np.ndarray | None]:
    """Per-row cut key (the day, or the minute) and the mask the `ret` primary is scored on (daily: LIQ names; the intraday
    feed already carries only liquid names)."""
    if kind == "daily":
        liq = (np.expm1(R["lvalue60"].to_numpy(dtype=float)) >= LIQ_VALUE60) & (R["close"].to_numpy(dtype=float) >= LIQ_MIN_PRICE)
        return R["d"].to_numpy(), liq
    return R["minute"].to_numpy(), None


def _block_plan(R: pd.DataFrame, calendar: np.ndarray, h: Horizon, kind: str) -> list[dict[str, Any]]:
    """For each validation block: the purged fit mask and the block mask, oldest block first."""
    embargo = h.steps if kind == "daily" else 0            # intraday labels never cross a day, blocks are whole days
    plan = []
    for b_from, b_to in common.blocks(R["d"], N_VAL[kind], K_BLOCKS[kind], MIN_FIT_DAYS[kind]):
        cut = common.purge_cut(calendar, b_from, embargo)
        fit_m = (R["d"] < cut).to_numpy()
        val_m = ((R["d"] >= b_from) & (R["d"] <= b_to)).to_numpy()
        plan.append({"from": pd.Timestamp(b_from).date(), "to": pd.Timestamp(b_to).date(), "cut": pd.Timestamp(cut).date(),
                     "fit": fit_m, "val": val_m})
    return plan


def _fit_blocks(X: np.ndarray, y: np.ndarray, plan: list[dict[str, Any]], task: str, params: dict[str, Any], feats: list[str],
                cuts: np.ndarray, mask: np.ndarray | None, n_seeds: int = 1):
    """Fit once per block on its purged set, score the block; -> (metrics summary, the newest block's booster)."""
    per_block, booster = [], None
    for b in plan:
        if b["fit"].sum() < 1000 or b["val"].sum() < 200:
            continue
        bst = common.fit(X[b["fit"]], y[b["fit"]], task, params, feats, n_seeds=n_seeds)
        m = common.metrics_for(task, y[b["val"]], np.asarray(bst.predict(X[b["val"]]), dtype=float), cuts[b["val"]],
                               None if mask is None else mask[b["val"]])
        per_block.append({"from": b["from"], "to": b["to"], "cut": b["cut"], "n_fit": int(b["fit"].sum()), **m})
        booster = bst
    if not per_block:
        raise RuntimeError("no block had enough rows to fit and validate")
    return _summarise(task, per_block), booster


def _summarise(task: str, per_block: list[dict[str, Any]]) -> dict[str, Any]:
    prim = np.array([b["primary"] for b in per_block], dtype=float)
    key = "auc" if task == "dir" else "ic"
    last = per_block[-1]
    out = {"primary": float(np.nanmean(prim)), "primary_min": float(np.nanmin(prim)), "blocks": per_block, "k": len(per_block),
           key: float(np.nanmean(prim)), "hit": float(np.nanmean([b["hit"] for b in per_block])),
           "base": float(np.nanmean([b["base"] for b in per_block])), "n": float(sum(b["n"] for b in per_block)),
           "last_primary": float(last["primary"])}
    if task == "dir":
        out["auc_pooled"] = float(np.nanmean([b.get("auc_pooled", float("nan")) for b in per_block]))
    if task == "ret":
        out["ic_pooled"] = float(np.nanmean([b.get("ic_pooled", float("nan")) for b in per_block]))
        out["mae_bps"] = float(np.nanmean([b["mae_bps"] for b in per_block]))
        out["naive_mae_bps"] = float(np.nanmean([b["naive_mae_bps"] for b in per_block]))
    return out


def _train_one(conn: psycopg.Connection, P: pd.DataFrame, feats: list[str], calendar: np.ndarray, h: Horizon, task: str, kind: str,
               rng: np.random.Generator, tune: bool, today: date, placebo: int = 0) -> dict[str, Any]:
    R, y = _label(P, h, task, kind)
    if len(R) < MIN_FIT_ROWS[kind]:
        raise RuntimeError(f"{len(R)} matured rows < {MIN_FIT_ROWS[kind]}")
    plan = _block_plan(R, calendar, h, kind)
    X = common.to_matrix(R, feats)
    cuts, mask = _cuts(R, kind)
    if task == "dir":
        for b in plan:
            yv = y[b["val"]]
            if len(yv) and min(yv.mean(), 1 - yv.mean()) < 0.02:
                raise RuntimeError(f"validation block {b['from']} is one-sided")
    newest = plan[-1]
    data_to = pd.Timestamp(R["d"][newest["fit"]].max()).date()
    champ = common.champion(conn, h.key, task)
    contenders: list[Contender] = []
    out: dict[str, Any] = {"horizon": h.key, "task": task, "basis": h.basis, "rows_fit": int(newest["fit"].sum()), "rows_val": int(newest["val"].sum()),
                           "val_from": newest["from"], "val_to": newest["to"], "embargo_to": newest["cut"], "k": len(plan)}
    if champ is not None:
        try:
            champ_days = int(np.searchsorted(calendar, np.datetime64(champ.data_to)))
            per_block = []
            for b in plan:
                start = int(np.searchsorted(calendar, np.datetime64(b["from"])))
                if champ_days + (h.steps if kind == "daily" else 0) >= start:      # the champion saw this block's outcomes
                    continue
                m = common.metrics_for(task, y[b["val"]], champ.predict(common.to_matrix(R[b["val"]], champ.features)),
                                       cuts[b["val"]], None if mask is None else mask[b["val"]])
                per_block.append({"from": b["from"], "to": b["to"], "cut": b["cut"], "n_fit": 0, **m})
            if not per_block:
                b = newest
                m = common.metrics_for(task, y[b["val"]], champ.predict(common.to_matrix(R[b["val"]], champ.features)),
                                       cuts[b["val"]], None if mask is None else mask[b["val"]])
                per_block.append({"from": b["from"], "to": b["to"], "cut": b["cut"], "n_fit": 0, **m})
            m_champ = _summarise(task, per_block)
            champ_blocks = {b["from"] for b in per_block}          # challengers are compared to the champion on THESE blocks only
            contenders.append(Contender("champion", m_champ["primary"], champ.trained_at.date() if champ.trained_at else today, champ.model_id))
            out["champion"] = {"model_id": champ.model_id, **m_champ}
        except Exception as e:                                   # a feature set that no longer exists, a corrupt artifact
            logger.warning("champion %s/%s could not be scored: %s", h.key, task, e)
    else:
        champ_blocks = None
    base_params = champ.params if champ is not None else common.BASE_PARAMS[task]
    n_seeds = common.ENSEMBLE_SEEDS.get((h.key, task), 1)
    out["seeds"] = n_seeds
    cands: dict[str, int] = {}
    plans = [("refresh", base_params)]
    if tune:
        plans.append(("tune", common.perturb(base_params, rng)))
    for name, params in plans:
        m, bst = _fit_blocks(X, y, plan, task, params, feats, cuts, mask, n_seeds)
        if name == "refresh" and placebo > 0:
            m["placebo"] = _placebo(X, y, R, newest, task, params, feats, placebo, rng, m["last_primary"], cuts, mask, n_seeds)
        mid = common.register(conn, horizon=h.key, task=task, data_to=data_to, val_from=newest["from"], val_to=newest["to"],
                              rows_fit=int(newest["fit"].sum()), rows_val=int(newest["val"].sum()), params=params, features=feats,
                              val_metrics=m, imp=common.importance(bst, feats), origin=name, artifact=bst.model_to_string())
        if n_seeds > 1:
            common.keep_reason(conn, mid, f"ensemble of {n_seeds} seeds")
        cands[name] = mid
        # a champion that saw an older block's outcomes is scored on fewer blocks; judge the challenger on the same ones
        common_prim = m["primary"]
        if champ_blocks and len(champ_blocks) < len(m["blocks"]):
            common_prim = float(np.nanmean([b["primary"] for b in m["blocks"] if b["from"] in champ_blocks]))
            m["primary_vs_champion"] = common_prim
            common.keep_reason(conn, mid, f"judged vs champion on {len(champ_blocks)} common block(s): {common_prim:.4f}")
        contenders.append(Contender(name, common_prim, today, mid, params))
        out[name] = {"model_id": mid, **m}
    chosen, reason = common.choose(contenders, today)
    out["chosen"], out["reason"] = chosen.name, reason
    out["promoted"] = chosen.name != "champion"
    if chosen.name == "champion":
        common.keep_reason(conn, champ.model_id, reason)
    else:
        common.promote(conn, chosen.model_id, reason)
    for mid in cands.values():
        if mid != chosen.model_id:
            common.retire_candidate(conn, mid, f"lost to {chosen.name}: {reason}")
    return out


def _placebo(X: np.ndarray, y: np.ndarray, R: pd.DataFrame, block: dict[str, Any], task: str, params: dict[str, Any], feats: list[str],
             n: int, rng: np.random.Generator, real: float, cuts: np.ndarray, mask: np.ndarray | None, n_seeds: int = 1) -> dict[str, Any]:
    """Shuffle the labels within each day of the fit set, refit, score the newest block: where does the real metric sit?"""
    fit_m, val_m = block["fit"], block["val"]
    days = R["d"].to_numpy()[fit_m]
    yf = y[fit_m]
    order = np.argsort(days, kind="stable")
    d_sorted = days[order]
    bounds = np.flatnonzero(np.r_[True, d_sorted[1:] != d_sorted[:-1], True])
    scores = []
    for _ in range(n):
        ys = yf.copy()
        for a, b in pairwise(bounds):     # permute inside each day: keeps the day's base rate, kills the name signal
            seg = order[a:b]
            ys[seg] = yf[rng.permutation(seg)]
        bst = common.fit(X[fit_m], ys, task, params, feats, n_seeds=n_seeds)
        scores.append(common.metrics_for(task, y[val_m], np.asarray(bst.predict(X[val_m]), dtype=float), cuts[val_m],
                                         None if mask is None else mask[val_m])["primary"])
    scores_a = np.array(scores, dtype=float)
    return {"n": n, "scores": [round(float(s), 4) for s in scores], "pct": float((scores_a < real).mean() * 100),
            "mean": float(np.nanmean(scores_a)), "real": float(real)}


def render_train(rep: dict[str, Any]) -> str:
    L = [f"ML {rep['kind']} {rep['today']}: {len(rep['models'])} model, {rep['promoted']} promosi, {rep.get('panel_rows', 0):,} baris, {rep.get('seconds', 0)} s"]
    for m in rep["models"]:
        c = m.get(m["chosen"], {})
        key = "auc" if m["task"] == "dir" else "ic"
        pl = c.get("placebo") or m.get("refresh", {}).get("placebo")
        L.append(f"  {m['horizon']:>4} {m['task']} {m.get('basis', 'abs'):<6}: {m['chosen']:<8} {key} {c.get(key, float('nan')):.3f} "
                 f"(min {c.get('primary_min', float('nan')):.3f}, {c.get('k', 0)} blok"
                 + (f", pooled {c['ic_pooled']:.3f}" if c.get('ic_pooled') is not None and m['task'] == 'ret' else "")
                 + (f", pooled {c['auc_pooled']:.3f}" if c.get('auc_pooled') is not None and m['task'] == 'dir' else "")
                 + (f", {m['seeds']} seeds" if m.get('seeds', 1) > 1 else "")
                 + f") hit {c.get('hit', float('nan')) * 100:.1f} % "
                 f"(base {c.get('base', float('nan')) * 100:.1f} %) blok akhir {m['val_from']}..{m['val_to']} embargo<{m.get('embargo_to')} "
                 + (f"placebo pct {pl['pct']:.0f} " if pl else "") + f"- {m['reason']}")
    for e in rep.get("errors", []):
        L.append(f"  ! {e}")
    return "\n".join(L)


# ---- prediction --------------------------------------------------------------------------------------------------------
_CACHE: dict[tuple[str, str], Model] = {}


def _models(conn: psycopg.Connection, kind: str) -> dict[tuple[str, str], Model]:
    """Champions of ``kind``, cached in-process and refreshed when the registry's ids change."""
    ids = common.champion_ids(conn)
    want = {k: v for k, v in ids.items() if k[0] in HORIZONS and HORIZONS[k[0]].kind == kind}
    for k in list(_CACHE):
        if k not in want or _CACHE[k].model_id != want[k]:
            _CACHE.pop(k, None)
    missing = [k for k in want if k not in _CACHE]
    if missing:
        fresh = common.champions(conn, kind)
        for k in missing:
            if k in fresh:
                _CACHE[k] = fresh[k]
    return {k: _CACHE[k] for k in want if k in _CACHE}


def _write(conn: psycopg.Connection, rows: list[tuple]) -> int:
    if not rows:
        return 0
    with conn.cursor() as cur:
        cur.executemany("""INSERT INTO idx.ml_prediction (made_at, code, horizon, model_dir, model_ret, ref_price, p_up, p_up_raw, pred_ret, pred_price,
                                                          target_at, basis)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                           ON CONFLICT (code, horizon, made_at) DO UPDATE SET model_dir = EXCLUDED.model_dir, model_ret = EXCLUDED.model_ret,
                               ref_price = EXCLUDED.ref_price, p_up = EXCLUDED.p_up, p_up_raw = EXCLUDED.p_up_raw, pred_ret = EXCLUDED.pred_ret,
                               pred_price = EXCLUDED.pred_price, target_at = EXCLUDED.target_at, basis = EXCLUDED.basis""", rows)
    return len(rows)


def _score(models: dict[tuple[str, str], Model], cal: dict[str, tuple[np.ndarray, np.ndarray]], L: pd.DataFrame, h: Horizon):
    md, mr = models.get((h.key, "dir")), models.get((h.key, "ret"))
    raw = md.predict(common.to_matrix(L, md.features)) if md is not None else None
    p_up = common.calibrate(raw, *cal[h.key]) if (raw is not None and h.key in cal) else raw
    ret = mr.predict(common.to_matrix(L, mr.features)) if mr is not None else None
    return md, mr, raw, p_up, ret


def _rows(L: pd.DataFrame, h: Horizon, made_at: datetime, target: datetime | None, md, mr, raw, p_up, ret) -> list[tuple]:
    rows = []
    for i, (code, ref) in enumerate(zip(L["code"].to_numpy(), L["close"].to_numpy(dtype=float), strict=True)):
        pr = float(ret[i]) if ret is not None else None
        rows.append((made_at, code, h.key, md.model_id if md else None, mr.model_id if mr else None, ref,
                     float(p_up[i]) if p_up is not None else None, float(raw[i]) if raw is not None else None, pr,
                     common.price_from(ref, pr) if pr is not None else None, target, h.basis))
    return rows


def predict_daily(conn: psycopg.Connection) -> dict[str, Any]:
    models = _models(conn, "daily")
    if not models:
        return {"kind": "daily", "rows": 0, "note": "no champion yet"}
    cal = common.calibrations(conn)
    P = daily.build_panel(conn, since=date.today() - timedelta(days=450))
    L = daily.latest_rows(P)
    if L.empty:
        return {"kind": "daily", "rows": 0, "note": "no rows to score"}
    bar_date = pd.Timestamp(L["d"].iloc[0]).date()
    made_at = common.wib_bar_close(bar_date)
    rows: list[tuple] = []
    for h in of_kind("daily"):
        md, mr, raw, p_up, ret = _score(models, cal, L, h)
        if md is None and mr is None:
            continue
        rows += _rows(L, h, made_at, None, md, mr, raw, p_up, ret)
    n = _write(conn, rows)
    conn.commit()
    return {"kind": "daily", "bar_date": bar_date, "names": len(L), "rows": n, "calibrated": sorted(k for k in cal if HORIZONS[k].kind == "daily")}


def predict_intraday(conn: psycopg.Connection, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    models = _models(conn, "intraday")
    if not models:
        return {"kind": "intraday", "rows": 0, "note": "no champion yet"}
    cal = common.calibrations(conn)
    L, targets = intraday.live_rows(conn, now)
    if L.empty:
        return {"kind": "intraday", "rows": 0, "note": "outside the session or no minute to score"}
    minute = L["minute"].iloc[0].to_pydatetime().astimezone(UTC)
    rows: list[tuple] = []
    for h, target in zip(of_kind("intraday"), targets, strict=True):
        if target is None:
            continue
        md, mr, raw, p_up, ret = _score(models, cal, L, h)
        if md is None and mr is None:
            continue
        rows += _rows(L, h, minute, target, md, mr, raw, p_up, ret)
    n = _write(conn, rows)
    conn.commit()
    return {"kind": "intraday", "minute": minute, "names": len(L), "rows": n}


# ---- realisation --------------------------------------------------------------------------------------------------------
def evaluate(conn: psycopg.Connection, now: datetime | None = None, batch: int = 50000) -> dict[str, Any]:
    """Fill realized_* on every prediction whose horizon has passed. Intraday: the mid of the end-of-minute book at or
    before the target minute (within 3 h, so the lunch break is bridged), the last trade when the book is one-sided.
    Daily: the bar ``steps`` trading days after the cut, on the COMPOSITE calendar, adjusted for corporate actions through
    adj_factor; for an 'excess' prediction the realised return is net of the COMPOSITE's over the same window."""
    now = now or datetime.now(UTC)
    out: dict[str, Any] = {"intraday": 0, "daily": 0}
    with conn.cursor() as cur:
        cur.execute("""
            WITH due AS (
                SELECT code, horizon, made_at, target_at FROM idx.ml_prediction
                 WHERE realized_ret IS NULL AND target_at IS NOT NULL AND target_at <= %s - interval '1 minute'
                 ORDER BY made_at LIMIT %s),
            px AS (
                SELECT d.code, d.horizon, d.made_at, COALESCE(k.mid, b.close) AS close, COALESCE(k.minute, b.minute) AS minute
                  FROM due d
                  LEFT JOIN LATERAL (SELECT (bid_px[1] + off_px[1]) / 2.0 AS mid, minute FROM idx.feed_book_1m f
                                      WHERE f.code = d.code AND f.minute <= d.target_at AND f.minute > d.target_at - interval '3 hours'
                                        AND f.bid_px[1] > 0 AND f.off_px[1] >= f.bid_px[1]
                                      ORDER BY f.minute DESC LIMIT 1) k ON true
                  LEFT JOIN LATERAL (SELECT close, minute FROM idx.feed_bar_1m f
                                      WHERE f.code = d.code AND f.minute <= d.target_at AND f.minute > d.target_at - interval '3 hours'
                                      ORDER BY f.minute DESC LIMIT 1) b ON true
                 WHERE COALESCE(k.mid, b.close) IS NOT NULL)
            UPDATE idx.ml_prediction p
               SET realized_price = px.close, realized_ret = ln(px.close / p.ref_price), realized_at = px.minute,
                   hit = CASE WHEN px.close = p.ref_price OR p.p_up IS NULL THEN NULL ELSE (p.p_up > 0.5) = (px.close > p.ref_price) END
              FROM px WHERE p.code = px.code AND p.horizon = px.horizon AND p.made_at = px.made_at""", (now, batch))
        out["intraday"] = cur.rowcount
        for h in of_kind("daily"):
            cur.execute("""
                WITH cal AS (SELECT trade_date, close AS comp, row_number() OVER (ORDER BY trade_date) AS rn
                               FROM idx.index_daily WHERE index_code = 'COMPOSITE'),
                due AS (
                    SELECT p.code, p.horizon, p.made_at, p.ref_price, p.p_up, p.basis, c1.trade_date AS made_date, c2.trade_date AS target_date,
                           ln(c2.comp / c1.comp) AS comp_ret
                      FROM idx.ml_prediction p
                      JOIN cal c1 ON c1.trade_date = (p.made_at AT TIME ZONE 'Asia/Jakarta')::date
                      JOIN cal c2 ON c2.rn = c1.rn + %s
                     WHERE p.horizon = %s AND p.realized_ret IS NULL
                     LIMIT %s),
                px AS (
                    SELECT d.*, b1.close AS c1,
                           ln((b1.close * b1.adj_factor) / (d.ref_price * b0.adj_factor))
                             - CASE WHEN d.basis = 'excess' THEN d.comp_ret ELSE 0 END AS r
                      FROM due d
                      JOIN idx.bar b1 ON b1.code = d.code AND b1.trade_date = d.target_date AND b1.source = 'idx' AND b1.close > 0
                      JOIN idx.bar b0 ON b0.code = d.code AND b0.trade_date = d.made_date AND b0.source = 'idx')
                UPDATE idx.ml_prediction p
                   SET realized_price = px.c1, realized_ret = px.r,
                       realized_at = (px.target_date::timestamp + interval '16 hours') AT TIME ZONE 'Asia/Jakarta',
                       target_at = (px.target_date::timestamp + interval '16 hours') AT TIME ZONE 'Asia/Jakarta',
                       hit = CASE WHEN px.r = 0 OR p.p_up IS NULL THEN NULL ELSE (p.p_up > 0.5) = (px.r > 0) END
                  FROM px WHERE p.code = px.code AND p.horizon = px.horizon AND p.made_at = px.made_at""", (h.steps, h.key, batch))
            out["daily"] += cur.rowcount
    conn.commit()
    return out


# ---- calibration ----------------------------------------------------------------------------------------------------------
def fit_calibration(conn: psycopg.Connection, now: datetime | None = None) -> list[dict[str, Any]]:
    """One isotonic curve per horizon from the realised predictions of the last CAL_DAYS (raw probability -> realised
    up-rate). Applied at prediction time; the hit rate at 0.5 then means what it says. Needs CAL_MIN_N rows."""
    now = now or datetime.now(UTC)
    out: list[dict[str, Any]] = []
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""SELECT horizon, COALESCE(p_up_raw, p_up) AS p, realized_ret, made_at FROM idx.ml_prediction
                        WHERE realized_ret IS NOT NULL AND realized_ret <> 0 AND p_up IS NOT NULL AND made_at > %s""", (now - timedelta(days=CAL_DAYS),))
        D = pd.DataFrame(cur.fetchall())
    if D.empty:
        return out
    for h, H in D.groupby("horizon"):
        if len(H) < CAL_MIN_N:
            continue
        p = H["p"].to_numpy(float)
        y = (H["realized_ret"].to_numpy(float) > 0).astype(float)
        kp, ky = common.isotonic(p, y)
        if len(kp) < 2 or ky[-1] - ky[0] < 0.02:                # a flat curve carries no information: leave the raw probability
            continue
        raw_hit = float(((p > 0.5) == (y > 0.5)).mean())
        cal_hit = float(((common.calibrate(p, kp, ky) > 0.5) == (y > 0.5)).mean())
        common.save_calibration(conn, str(h), len(H), H["made_at"].min().to_pydatetime(), H["made_at"].max().to_pydatetime(),
                                kp, ky, raw_hit, cal_hit)
        out.append({"horizon": h, "n": len(H), "knots": len(kp), "raw_hit": raw_hit, "cal_hit": cal_hit, "lo": float(ky[0]), "hi": float(ky[-1])})
    conn.commit()
    return out


# ---- the scorecard -------------------------------------------------------------------------------------------------------
WINDOWS = (1, 5, 20, 60)


def scorecard(conn: psycopg.Connection, score_date: date | None = None, windows: tuple[int, ...] = WINDOWS) -> list[dict[str, Any]]:
    """Per horizon and trailing window (calendar days of cut times): the realised hit rate against the majority base,
    AUC, IC, and the price error against 'no change'. Written to idx.ml_scorecard and returned."""
    score_date = score_date or datetime.now(WIB).date()
    t_hi = datetime(score_date.year, score_date.month, score_date.day, 23, 59, tzinfo=WIB).astimezone(UTC)
    t_lo = t_hi - timedelta(days=max(windows))
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT made_at, horizon, p_up, pred_ret, realized_ret FROM idx.ml_prediction "
                    "WHERE realized_ret IS NOT NULL AND made_at > %s AND made_at <= %s", (t_lo, t_hi))
        D = pd.DataFrame(cur.fetchall())
    rows: list[dict[str, Any]] = []
    if D.empty:
        return rows
    D["made_at"] = pd.to_datetime(D["made_at"], utc=True)
    for h in HORIZONS.values():
        H = D[D["horizon"] == h.key]
        if H.empty:
            continue
        for w in windows:
            S = H[H["made_at"] > t_hi - timedelta(days=w)]
            if len(S) < 20:
                continue
            r = S["realized_ret"].to_numpy(float)
            p_up = S["p_up"].to_numpy(float)
            pr = S["pred_ret"].to_numpy(float)
            hit, base, _ = common.hit_rate(p_up > 0.5, r)
            a = common.auc((r > 0).astype(float)[r != 0], p_up[r != 0])
            m, nm = common.mae_bps(pr, r)
            rows.append({"score_date": score_date, "horizon": h.key, "window_days": w, "n": len(S), "hit_rate": hit, "base_hit": base,
                         "auc": a, "ic": _realised_ic(S["made_at"].to_numpy(), pr, r), "mae_bps": m, "naive_mae_bps": nm})
    with conn.cursor() as cur:
        for x in rows:
            cur.execute("""INSERT INTO idx.ml_scorecard (score_date, horizon, window_days, n, hit_rate, base_hit, auc, ic, mae_bps, naive_mae_bps)
                           VALUES (%(score_date)s, %(horizon)s, %(window_days)s, %(n)s, %(hit_rate)s, %(base_hit)s, %(auc)s, %(ic)s, %(mae_bps)s, %(naive_mae_bps)s)
                           ON CONFLICT (score_date, horizon, window_days) DO UPDATE SET n = EXCLUDED.n, hit_rate = EXCLUDED.hit_rate,
                               base_hit = EXCLUDED.base_hit, auc = EXCLUDED.auc, ic = EXCLUDED.ic, mae_bps = EXCLUDED.mae_bps,
                               naive_mae_bps = EXCLUDED.naive_mae_bps, computed_at = now()""", common.plain(x) | {"score_date": score_date})
    conn.commit()
    return rows


def _realised_ic(made_at: np.ndarray, pred: np.ndarray, real: np.ndarray) -> float:
    """The scorecard's IC: mean rank IC per cut (predictions made together), the pooled Spearman when cuts are too thin."""
    ic, _, k = common.cut_ic(made_at, pred, real)
    return ic if k > 0 else common.spearman(pred, real)


def render_scorecard(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "belum ada prediksi yang jatuh tempo"

    def f(v: Any, fmt: str, width: int, scale: float = 1.0) -> str:
        if v is None or (isinstance(v, float) and not np.isfinite(v)):
            return "-".rjust(width)
        return (fmt % (float(v) * scale)).rjust(width)

    L = ["horizon  win      n   hit%  base%    auc      ic  mae_bps naive_bps   (20d+ = relatif IHSG; ic = rank IC per cut, rata-rata)"]
    for r in rows:
        L.append(f"{r['horizon']:>7} {r['window_days']:>4}d {r['n']:>6} {f(r['hit_rate'], '%.1f', 6, 100)} {f(r['base_hit'], '%.1f', 6, 100)} "
                 f"{f(r['auc'], '%.3f', 6)} {f(r['ic'], '%.3f', 7)} {f(r['mae_bps'], '%.1f', 8)} {f(r['naive_mae_bps'], '%.1f', 9)}")
    return "\n".join(L)


# ---- reads for the API / CLI ------------------------------------------------------------------------------------------------
def latest_for(conn: psycopg.Connection, code: str) -> list[dict[str, Any]]:
    """The newest prediction per horizon for one name, with the champion's validation numbers and the live scorecard."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""SELECT DISTINCT ON (horizon) made_at, code, horizon, basis, ref_price, p_up, p_up_raw, pred_ret, pred_price, target_at,
                              realized_price, realized_ret, hit, model_dir, model_ret
                         FROM idx.ml_prediction WHERE code = %s AND made_at > now() - interval '30 days' ORDER BY horizon, made_at DESC""", (code,))
        rows = [dict(r) for r in cur.fetchall()]
        cur.execute("SELECT DISTINCT ON (horizon) horizon, window_days, n, hit_rate, base_hit, auc, ic, mae_bps, naive_mae_bps FROM idx.ml_scorecard "
                    "WHERE window_days = 20 ORDER BY horizon, score_date DESC")
        sc = {r["horizon"]: dict(r) for r in cur.fetchall()}
    order = list(HORIZONS)
    rows.sort(key=lambda r: order.index(r["horizon"]) if r["horizon"] in order else 99)
    for r in rows:
        r["label"] = HORIZONS[r["horizon"]].label
        r["track"] = sc.get(r["horizon"])
    return rows


def board(conn: psycopg.Connection, horizon: str, top: int = 20) -> dict[str, Any]:
    """The newest cut of one horizon ranked by predicted return: the top and bottom names."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT max(made_at) AS m FROM idx.ml_prediction WHERE horizon = %s", (horizon,))
        m = cur.fetchone()["m"]
        if m is None:
            return {"horizon": horizon, "made_at": None, "up": [], "down": []}
        cur.execute("""SELECT code, basis, ref_price, p_up, pred_ret, pred_price FROM idx.ml_prediction WHERE horizon = %s AND made_at = %s
                       AND pred_ret IS NOT NULL ORDER BY pred_ret DESC""", (horizon, m))
        rows = [dict(r) for r in cur.fetchall()]
        # an intraday horizon is cut every minute over whatever names the live feed carried, so the newest cut is much
        # narrower than the session: report both, or the screen ends up quoting the daily figure for every horizon
        cur.execute("""SELECT count(DISTINCT code) AS n FROM idx.ml_prediction
                        WHERE horizon = %s AND made_at >= date_trunc('day', %s::timestamptz)""", (horizon, m))
        day = cur.fetchone()
    return {"horizon": horizon, "label": HORIZONS[horizon].label, "basis": HORIZONS[horizon].basis, "made_at": m, "n": len(rows),
            "codes_today": int(day["n"]) if day else len(rows), "cadence": HORIZONS[horizon].kind,
            "up": rows[:top], "down": rows[-top:][::-1]}


def status(conn: psycopg.Connection) -> dict[str, Any]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""SELECT horizon, task, model_id, trained_at, data_to, val_from, val_to, rows_fit, rows_val, val_metrics, origin, reason
                         FROM idx.ml_model WHERE status = 'champion' ORDER BY horizon, task""")
        champs = [dict(r) for r in cur.fetchall()]
        cur.execute("""SELECT horizon, count(*) AS n, count(realized_ret) AS realized, max(made_at) AS last_made
                         FROM idx.ml_prediction WHERE made_at > now() - interval '7 days' GROUP BY horizon""")
        preds = {r["horizon"]: dict(r) for r in cur.fetchall()}
        cur.execute("SELECT * FROM idx.ml_scorecard WHERE score_date = (SELECT max(score_date) FROM idx.ml_scorecard) ORDER BY horizon, window_days")
        sc = [dict(r) for r in cur.fetchall()]
        cur.execute("SELECT horizon, fitted_at, n, raw_hit, cal_hit, array_length(knots_p, 1) AS knots FROM idx.ml_calibration ORDER BY horizon")
        cal = [dict(r) for r in cur.fetchall()]
    order = list(HORIZONS)
    champs.sort(key=lambda r: (order.index(r["horizon"]) if r["horizon"] in order else 99, r["task"]))
    sc.sort(key=lambda r: (order.index(r["horizon"]) if r["horizon"] in order else 99, r["window_days"]))
    return {"champions": champs, "predictions_7d": preds, "scorecard": sc, "calibration": cal}


def render_status(s: dict[str, Any]) -> str:
    L = ["champions (primary = mean over the validation blocks):"]
    for c in s["champions"]:
        m = c["val_metrics"] or {}
        key = "auc" if c["task"] == "dir" else "ic"
        prim = "-" if m.get(key) is None else f"{m[key]:.3f}"
        pmin = "-" if m.get("primary_min") is None else f"{m['primary_min']:.3f}"
        hit = "-" if m.get("hit") is None else f"{m['hit'] * 100:.1f} %"
        pl = m.get("placebo")
        L.append(f"  {c['horizon']:>4} {c['task']} #{c['model_id']} {c['origin']:<7} trained {c['trained_at']:%Y-%m-%d} data_to {c['data_to']} "
                 f"last block {c['val_from']}..{c['val_to']} {key} {prim} (min {pmin}, {m.get('k', 1)} blok) hit {hit}"
                 + (f" placebo pct {pl['pct']:.0f}" if pl else ""))
    L.append("calibration (isotonic on realised predictions):")
    for c in s.get("calibration", []):
        L.append(f"  {c['horizon']:>4}: n {c['n']:,} knots {c['knots']} hit@0.5 raw {c['raw_hit'] * 100:.1f} % -> cal {c['cal_hit'] * 100:.1f} % "
                 f"(in-sample) fitted {c['fitted_at']:%Y-%m-%d %H:%M}")
    L.append("predictions (7 d):")
    for h, p in s["predictions_7d"].items():
        L.append(f"  {h:>4}: {p['n']:,} rows, {p['realized']:,} realised, last cut {p['last_made']:%Y-%m-%d %H:%M} UTC")
    L.append("scorecard:")
    L.append(render_scorecard(s["scorecard"]))
    return "\n".join(L)
