"""Shared pieces: metrics (no sklearn in the venv), tick rounding, LightGBM params and their nightly perturbation, the
model registry on idx.ml_model, and the promotion rule that decides which model predicts tomorrow."""
from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import psycopg
from psycopg.rows import dict_row, tuple_row
from scipy import stats

logger = logging.getLogger(__name__)
WIB = ZoneInfo("Asia/Jakarta")
UTC = ZoneInfo("UTC")


# ---- metrics ----------------------------------------------------------------------------------------------------------
def auc(y: np.ndarray, p: np.ndarray) -> float:
    """Rank AUC (Mann-Whitney); nan when one class is missing."""
    y = np.asarray(y, dtype=float)
    p = np.asarray(p, dtype=float)
    ok = np.isfinite(y) & np.isfinite(p)
    y, p = y[ok], p[ok]
    n1 = int((y > 0.5).sum())
    n0 = len(y) - n1
    if n1 == 0 or n0 == 0:
        return float("nan")
    r = stats.rankdata(p)
    return float((r[y > 0.5].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 10 or np.std(a[ok]) == 0 or np.std(b[ok]) == 0:
        return float("nan")
    return float(stats.spearmanr(a[ok], b[ok]).statistic)


def hit_rate(pred_up: np.ndarray, realized: np.ndarray) -> tuple[float, float, int]:
    """Direction hit rate on rows that moved, with the majority-direction base rate on the same rows: (hit, base, n)."""
    r = np.asarray(realized, dtype=float)
    u = np.asarray(pred_up, dtype=bool)
    ok = np.isfinite(r) & (r != 0)
    if ok.sum() == 0:
        return float("nan"), float("nan"), 0
    up = r[ok] > 0
    hit = float((u[ok] == up).mean())
    base = float(max(up.mean(), 1 - up.mean()))
    return hit, base, int(ok.sum())


def mae_bps(pred: np.ndarray, realized: np.ndarray) -> tuple[float, float]:
    p = np.asarray(pred, dtype=float)
    r = np.asarray(realized, dtype=float)
    ok = np.isfinite(p) & np.isfinite(r)
    if ok.sum() == 0:
        return float("nan"), float("nan")
    return float(np.abs(p[ok] - r[ok]).mean() * 1e4), float(np.abs(r[ok]).mean() * 1e4)


def metrics_for(task: str, y: np.ndarray, pred: np.ndarray) -> dict[str, float]:
    """The validation numbers stored on every model; ``primary`` is what the promotion rule compares."""
    y = np.asarray(y, dtype=float)
    pred = np.asarray(pred, dtype=float)
    if task == "dir":
        a = auc(y, pred)
        hit, base, n = hit_rate(pred > 0.5, np.where(y > 0.5, 1.0, -1.0))
        return {"primary": a, "auc": a, "hit": hit, "base": base, "n": float(n)}
    ic = spearman(pred, y)
    m, nm = mae_bps(pred, y)
    hit, base, n = hit_rate(pred > 0, y)
    return {"primary": ic, "ic": ic, "mae_bps": m, "naive_mae_bps": nm, "hit": hit, "base": base, "n": float(n)}


# ---- prices -----------------------------------------------------------------------------------------------------------
def tick(px: float) -> float:
    return 1.0 if px < 200 else 2.0 if px < 500 else 5.0 if px < 2000 else 10.0 if px < 5000 else 25.0


def on_tick(px: float) -> float:
    if not np.isfinite(px) or px <= 0:
        return float("nan")
    t = tick(px)
    return float(round(px / t) * t)


def price_from(ref: float, log_ret: float) -> float:
    if not (np.isfinite(ref) and np.isfinite(log_ret)):
        return float("nan")
    return on_tick(ref * math.exp(float(np.clip(log_ret, -1.5, 1.5))))


# ---- params -----------------------------------------------------------------------------------------------------------
BASE_PARAMS: dict[str, dict[str, Any]] = {
    "dir": {"objective": "binary", "learning_rate": 0.05, "num_leaves": 63, "min_data_in_leaf": 400, "feature_fraction": 0.8,
            "bagging_fraction": 0.8, "bagging_freq": 1, "lambda_l2": 10.0, "verbose": -1, "num_threads": 12, "rounds": 300},
    "ret": {"objective": "huber", "alpha": 0.9, "learning_rate": 0.05, "num_leaves": 63, "min_data_in_leaf": 400,
            "feature_fraction": 0.8, "bagging_fraction": 0.8, "bagging_freq": 1, "lambda_l2": 10.0, "verbose": -1,
            "num_threads": 12, "rounds": 300},
}
TUNE_SPACE: dict[str, list[Any]] = {
    "learning_rate": [0.02, 0.03, 0.05, 0.08], "num_leaves": [15, 31, 63, 127], "min_data_in_leaf": [100, 200, 400, 1000],
    "feature_fraction": [0.5, 0.65, 0.8, 0.95], "lambda_l2": [1.0, 3.0, 10.0, 30.0], "rounds": [150, 300, 500],
}


def perturb(params: dict[str, Any], rng: np.random.Generator, n_changes: int = 2) -> dict[str, Any]:
    """The nightly tuning challenger: the champion's params with a couple of knobs moved one notch."""
    p = dict(params)
    keys = list(TUNE_SPACE)
    for k in rng.choice(keys, size=n_changes, replace=False):
        grid = TUNE_SPACE[k]
        cur = p.get(k, grid[len(grid) // 2])
        i = min(range(len(grid)), key=lambda j: abs(grid[j] - cur))
        j = int(np.clip(i + int(rng.choice([-1, 1])), 0, len(grid) - 1))
        p[k] = grid[j]
    return p


def fit(X: np.ndarray, y: np.ndarray, task: str, params: dict[str, Any], features: list[str], seed: int = 20260924):
    import lightgbm as lgb
    p = {k: v for k, v in params.items() if k != "rounds"}
    p["seed"] = seed
    ds = lgb.Dataset(X, y, feature_name=features, free_raw_data=True)
    return lgb.train(p, ds, int(params.get("rounds", 300)))


def importance(booster, features: list[str]) -> dict[str, float]:
    g = np.asarray(booster.feature_importance(importance_type="gain"), dtype=float)
    tot = g.sum() or 1.0
    order = np.argsort(-g)
    return {features[i]: round(float(g[i] / tot), 4) for i in order[:25]}


# ---- registry ----------------------------------------------------------------------------------------------------------
@dataclass
class Model:
    model_id: int
    horizon: str
    task: str
    params: dict[str, Any]
    features: list[str]
    val_metrics: dict[str, Any]
    data_to: date
    status: str
    trained_at: datetime | None = None
    artifact: str | None = None
    booster: Any = field(default=None, repr=False)

    def load(self):
        if self.booster is None:
            import lightgbm as lgb
            if not self.artifact:
                raise RuntimeError(f"model {self.model_id} has no artifact")
            self.booster = lgb.Booster(model_str=self.artifact)
        return self.booster

    def predict(self, X: np.ndarray) -> np.ndarray:
        return np.asarray(self.load().predict(X), dtype=float)


def _row_model(r: dict[str, Any], with_artifact: bool) -> Model:
    return Model(model_id=r["model_id"], horizon=r["horizon"], task=r["task"], params=r["params"], features=list(r["features"]),
                 val_metrics=r["val_metrics"] or {}, data_to=r["data_to"], status=r["status"], trained_at=r.get("trained_at"),
                 artifact=r.get("artifact") if with_artifact else None)


def champion(conn: psycopg.Connection, horizon: str, task: str, with_artifact: bool = True) -> Model | None:
    cols = "model_id, horizon, task, params, features, val_metrics, data_to, status, trained_at" + (", artifact" if with_artifact else "")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"SELECT {cols} FROM idx.ml_model WHERE horizon = %s AND task = %s AND status = 'champion' "
                    "ORDER BY promoted_at DESC LIMIT 1", (horizon, task))
        r = cur.fetchone()
    return _row_model(r, with_artifact) if r else None


def champions(conn: psycopg.Connection, kind: str | None = None) -> dict[tuple[str, str], Model]:
    from .spec import HORIZONS
    out: dict[tuple[str, str], Model] = {}
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT model_id, horizon, task, params, features, val_metrics, data_to, status, trained_at, artifact "
                    "FROM idx.ml_model WHERE status = 'champion'")
        for r in cur.fetchall():
            h = HORIZONS.get(r["horizon"])
            if h and (kind is None or h.kind == kind):
                out[(r["horizon"], r["task"])] = _row_model(r, True)
    return out


def champion_ids(conn: psycopg.Connection) -> dict[tuple[str, str], int]:
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute("SELECT horizon, task, model_id FROM idx.ml_model WHERE status = 'champion'")
        return {(h, t): m for h, t, m in cur.fetchall()}


def register(conn: psycopg.Connection, *, horizon: str, task: str, data_to: date, val_from: date | None, val_to: date | None,
             rows_fit: int, rows_val: int, params: dict[str, Any], features: list[str], val_metrics: dict[str, Any],
             imp: dict[str, float] | None, origin: str, artifact: str | None, reason: str | None = None) -> int:
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute("""INSERT INTO idx.ml_model (horizon, task, data_to, val_from, val_to, rows_fit, rows_val, params, features,
                                                 val_metrics, importance, origin, artifact, reason)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s::jsonb, %s::jsonb, %s, %s, %s) RETURNING model_id""",
                    (horizon, task, data_to, val_from, val_to, rows_fit, rows_val, json.dumps(params), features,
                     json.dumps(plain(val_metrics)), json.dumps(imp) if imp else None, origin, artifact, reason))
        return int(cur.fetchone()[0])


def promote(conn: psycopg.Connection, model_id: int, reason: str) -> None:
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute("SELECT horizon, task FROM idx.ml_model WHERE model_id = %s", (model_id,))
        horizon, task = cur.fetchone()
        cur.execute("UPDATE idx.ml_model SET status = 'retired', retired_at = now() "
                    "WHERE horizon = %s AND task = %s AND status = 'champion' AND model_id <> %s", (horizon, task, model_id))
        cur.execute("UPDATE idx.ml_model SET status = 'champion', promoted_at = now(), reason = %s WHERE model_id = %s", (reason, model_id))


def retire_candidate(conn: psycopg.Connection, model_id: int, reason: str) -> None:
    with conn.cursor() as cur:
        cur.execute("UPDATE idx.ml_model SET status = 'retired', retired_at = now(), artifact = NULL, reason = %s WHERE model_id = %s",
                    (reason, model_id))


def keep_reason(conn: psycopg.Connection, model_id: int, reason: str) -> None:
    with conn.cursor() as cur:
        cur.execute("UPDATE idx.ml_model SET reason = %s WHERE model_id = %s", (reason, model_id))


def purge_artifacts(conn: psycopg.Connection, days: int = 30) -> int:
    with conn.cursor() as cur:
        cur.execute("UPDATE idx.ml_model SET artifact = NULL WHERE status = 'retired' AND artifact IS NOT NULL "
                    "AND retired_at < now() - make_interval(days => %s)", (days,))
        return cur.rowcount


def models(conn: psycopg.Connection, limit: int = 60) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""SELECT model_id, horizon, task, trained_at, data_to, val_from, val_to, rows_fit, rows_val, params, val_metrics,
                              importance, status, origin, reason, promoted_at
                         FROM idx.ml_model ORDER BY trained_at DESC LIMIT %s""", (limit,))
        return [dict(r) for r in cur.fetchall()]


# ---- the promotion rule ------------------------------------------------------------------------------------------------
TOL = 0.005            # a newer model within this of the champion wins: it has seen more data
STALE_DAYS = 45        # a champion older than this is replaced unless the challenger is clearly worse
STALE_TOL = 0.03


@dataclass
class Contender:
    name: str                      # champion | refresh | tune
    primary: float
    trained: date
    model_id: int | None = None
    params: dict[str, Any] | None = None


def choose(contenders: list[Contender], today: date) -> tuple[Contender, str]:
    """Pick tomorrow's model from candidates that were all scored on the same out-of-sample window. Pure, tested.

    * no champion yet -> the best challenger
    * a challenger better than the champion by more than TOL -> promote it
    * the refresh (champion's params, more data) within TOL of the champion -> promote it: newer data wins ties
    * champion older than STALE_DAYS -> promote the best challenger unless it is worse by more than STALE_TOL
    * otherwise keep the champion
    """
    champ = next((c for c in contenders if c.name == "champion"), None)
    chal = [c for c in contenders if c.name != "champion" and np.isfinite(c.primary)]
    if not chal:
        if champ is None:
            raise RuntimeError("no contender has a finite validation metric")
        return champ, "no challenger scored; champion kept"
    best = max(chal, key=lambda c: c.primary)
    if champ is None or not np.isfinite(champ.primary):
        return best, f"first champion ({best.name} {best.primary:.4f})"
    if best.primary > champ.primary + TOL:
        return best, f"{best.name} {best.primary:.4f} beats champion {champ.primary:.4f} by > {TOL}"
    refresh = next((c for c in chal if c.name == "refresh"), None)
    if refresh is not None and refresh.primary >= champ.primary - TOL:
        return refresh, f"refresh {refresh.primary:.4f} within {TOL} of champion {champ.primary:.4f}: newer data wins"
    if (today - champ.trained).days > STALE_DAYS and best.primary >= champ.primary - STALE_TOL:
        return best, f"champion {(today - champ.trained).days} d old; {best.name} {best.primary:.4f} within {STALE_TOL}"
    return champ, f"champion {champ.primary:.4f} kept; best challenger {best.name} {best.primary:.4f}"


# ---- misc --------------------------------------------------------------------------------------------------------------
def plain(v: Any) -> Any:
    if isinstance(v, dict):
        return {k: plain(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [plain(x) for x in v]
    if isinstance(v, (np.floating, float)):
        return None if not np.isfinite(v) else float(v)
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.bool_):
        return bool(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


def to_matrix(df: pd.DataFrame, features: list[str]) -> np.ndarray:
    return df.reindex(columns=features).to_numpy(dtype=np.float32, na_value=np.nan)


def window_bounds(days: pd.Series, n_val: int, min_fit_days: int = 5) -> tuple[Any, Any]:
    """Split the matured rows: everything before the last ``n_val`` distinct days fits, those days validate."""
    uniq = np.sort(pd.unique(days))
    if len(uniq) < n_val + min_fit_days:
        raise RuntimeError(f"only {len(uniq)} matured days; need >= {n_val + min_fit_days}")
    return uniq[-n_val], uniq[-1]


def blocks(days: pd.Series, n_val: int, k: int, min_fit_days: int = 5) -> list[tuple[Any, Any]]:
    """The last ``k`` consecutive validation blocks of ``n_val`` distinct days, oldest first; fewer when history is short."""
    uniq = np.sort(pd.unique(days))
    k = min(k, max(0, (len(uniq) - min_fit_days) // n_val))
    if k == 0:
        raise RuntimeError(f"only {len(uniq)} matured days; need >= {n_val + min_fit_days}")
    return [(uniq[-(i + 1) * n_val], uniq[-i * n_val - 1]) for i in range(k - 1, -1, -1)]


def purge_cut(calendar: np.ndarray, block_from: Any, embargo: int) -> Any:
    """The first day NOT allowed in a fit set for a block starting at ``block_from``: a fit row's label spans ``embargo``
    trading days, so rows within that distance of the block would carry the block's outcomes (Lopez de Prado's purge)."""
    i = int(np.searchsorted(calendar, block_from))
    return calendar[max(0, i - embargo)]


# ---- calibration (isotonic, pool-adjacent-violators) -----------------------------------------------------------------------
def isotonic(p: np.ndarray, y: np.ndarray, min_bin: int = 50) -> tuple[np.ndarray, np.ndarray]:
    """Non-decreasing map raw probability -> realised up-rate. Returns the step knots (x = mean p, y = pooled rate)."""
    p = np.asarray(p, dtype=float)
    y = np.asarray(y, dtype=float)
    ok = np.isfinite(p) & np.isfinite(y)
    p, y = p[ok], y[ok]
    order = np.argsort(p, kind="stable")
    p, y = p[order], y[order]
    # pool into bins of min_bin so the curve is smooth-ish, then PAV over the bins
    nb = max(1, len(p) // min_bin)
    edges = np.linspace(0, len(p), nb + 1).astype(int)
    bx = np.array([p[a:b].mean() for a, b in zip(edges[:-1], edges[1:], strict=True)])
    by = np.array([y[a:b].mean() for a, b in zip(edges[:-1], edges[1:], strict=True)])
    bw = np.array([b - a for a, b in zip(edges[:-1], edges[1:], strict=True)], dtype=float)
    xs, ys, ws = list(bx), list(by), list(bw)
    i = 0
    while i < len(ys) - 1:
        if ys[i] > ys[i + 1]:
            w = ws[i] + ws[i + 1]
            ys[i] = (ys[i] * ws[i] + ys[i + 1] * ws[i + 1]) / w
            xs[i] = (xs[i] * ws[i] + xs[i + 1] * ws[i + 1]) / w
            ws[i] = w
            del ys[i + 1], xs[i + 1], ws[i + 1]
            i = max(0, i - 1)
        else:
            i += 1
    return np.asarray(xs), np.asarray(ys)


def calibrate(p: np.ndarray, knots_p: np.ndarray, knots_y: np.ndarray) -> np.ndarray:
    if len(knots_p) == 0:
        return np.asarray(p, dtype=float)
    return np.interp(np.asarray(p, dtype=float), knots_p, knots_y, left=float(knots_y[0]), right=float(knots_y[-1]))


def save_calibration(conn: psycopg.Connection, horizon: str, n: int, from_at: datetime | None, to_at: datetime | None,
                     knots_p: np.ndarray, knots_y: np.ndarray, raw_hit: float, cal_hit: float) -> None:
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO idx.ml_calibration (horizon, fitted_at, n, from_at, to_at, knots_p, knots_y, raw_hit, cal_hit)
                       VALUES (%s, now(), %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (horizon) DO UPDATE SET fitted_at = now(), n = EXCLUDED.n, from_at = EXCLUDED.from_at, to_at = EXCLUDED.to_at,
                           knots_p = EXCLUDED.knots_p, knots_y = EXCLUDED.knots_y, raw_hit = EXCLUDED.raw_hit, cal_hit = EXCLUDED.cal_hit""",
                    (horizon, n, from_at, to_at, [float(x) for x in knots_p], [float(x) for x in knots_y], raw_hit, cal_hit))


def calibrations(conn: psycopg.Connection) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute("SELECT horizon, knots_p, knots_y FROM idx.ml_calibration")
        return {h: (np.asarray(kp, dtype=float), np.asarray(ky, dtype=float)) for h, kp, ky in cur.fetchall()}


def wib_bar_close(d: date) -> datetime:
    """The daily cut: the bar date at 16:00 WIB, as an aware UTC datetime."""
    return datetime(d.year, d.month, d.day, 16, 0, tzinfo=WIB).astimezone(UTC)


def trading_calendar(conn: psycopg.Connection, since: date | None = None) -> list[date]:
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute("SELECT trade_date FROM idx.index_daily WHERE index_code = 'COMPOSITE' AND (%s::date IS NULL OR trade_date >= %s) "
                    "ORDER BY trade_date", (since, since))
        return [r[0] for r in cur.fetchall()]
