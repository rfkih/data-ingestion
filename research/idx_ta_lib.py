#!/usr/bin/env python3
"""Python port of the desk's technical-indicator catalog (blackheart-idx-web/src/lib/ta/core.ts + catalog.ts), 2026-09-25.

Same formulas, same DEFAULT parameters, same null (NaN) conventions as the TS (TradingView's ta.*: SMA-seeded EMA/RMA,
population stdev, Wilder smoothing for RSI/ATR/ADX), vectorised over a (T x N) panel, one column per name.

The chart computes each indicator over the bars that EXIST for a name (no rows on days without a bar). A dated panel has
NaN rows for suspensions / before listing, and a NaN inside a rolling window would null the window where the chart does
not. So `compute()` PACKS every column (its finite-close rows moved to the top, NaN padding at the end), computes on the
packed array (every name then starts at row 0, like the chart), and scatters the results back to the dates.

`plots(id, D, p)` returns the TS plots (the raw lines the chart draws) - used for the spot-check against the TS.
`values(D, params)` returns ONE scale-free number per indicator (the research reading), see VALUES below.
"""
from __future__ import annotations

import math

import numpy as np

# ---------------------------------------------------------------------------------------------------------------- defaults
DEFAULTS: dict[str, dict[str, float]] = {
    "sma": {"len": 20}, "ema": {"len": 20}, "wma": {"len": 20}, "hma": {"len": 9}, "vwma": {"len": 20},
    "alma": {"len": 9, "offset": 0.85, "sigma": 6}, "vwap": {},
    "bb": {"len": 20, "mult": 2}, "kc": {"len": 20, "mult": 2, "atr": 10}, "dc": {"len": 20}, "env": {"len": 20, "pct": 10},
    "ichimoku": {"conv": 9, "base": 26, "spanB": 52, "disp": 26},
    "psar": {"start": 0.02, "inc": 0.02, "max": 0.2}, "supertrend": {"atr": 10, "mult": 3}, "pivots": {},
    "volume": {"ma": 20}, "obv": {}, "mfi": {"len": 14}, "cmf": {"len": 20}, "ad": {}, "chaikinosc": {"fast": 3, "slow": 10},
    "pvt": {}, "volosc": {"fast": 5, "slow": 10}, "efi": {"len": 13}, "eom": {"len": 14, "div": 10000}, "netvol": {},
    "rsi": {"len": 14}, "macd": {"fast": 12, "slow": 26, "sig": 9}, "stoch": {"k": 14, "ks": 1, "d": 3},
    "stochrsi": {"k": 3, "d": 3, "rsi": 14, "st": 14}, "cci": {"len": 20}, "wpr": {"len": 14}, "roc": {"len": 9},
    "mom": {"len": 10}, "ao": {}, "uo": {"f": 7, "m": 14, "s": 28}, "trix": {"len": 18}, "tsi": {"long": 25, "short": 13, "sig": 13},
    "ppo": {"fast": 12, "slow": 26, "sig": 9}, "cmo": {"len": 9}, "bop": {}, "coppock": {"wma": 10, "long": 14, "short": 11},
    "dpo": {"len": 21}, "fisher": {"len": 9},
    "dmi": {"di": 14, "adx": 14}, "aroon": {"len": 14}, "vortex": {"len": 14}, "chop": {"len": 14}, "mass": {"len": 10},
    "atr": {"len": 14}, "stdev": {"len": 20}, "hv": {"len": 10}, "bbpb": {"len": 20, "mult": 2}, "bbw": {"len": 20, "mult": 2},
}
INT_KEYS = {"len", "atr", "conv", "base", "spanB", "disp", "ma", "fast", "slow", "sig", "k", "ks", "d", "rsi", "st", "f", "m", "s",
            "long", "short", "wma", "di", "adx"}


def params_for(ind: str, override: dict | None = None, scale: float = 1.0) -> dict:
    """Default params, optionally with every LENGTH scaled (neighbours: 0.75 / 1.25), then explicit overrides."""
    p = dict(DEFAULTS[ind])
    if scale != 1.0:
        for k, v in p.items():
            if k in INT_KEYS:
                p[k] = max(1, int(round(v * scale)))
    if override:
        p.update(override)
    for k in list(p):
        if k in INT_KEYS:
            p[k] = int(p[k])
    return p


# ---------------------------------------------------------------------------------------------------------------- core.ts
def _fin(x):
    return np.isfinite(x)


def _clean(x):
    x = np.asarray(x, float)
    return np.where(np.isfinite(x), x, np.nan)


def lag(x, k=1):
    x = np.asarray(x, float)
    out = np.full_like(x, np.nan)
    if k == 0:
        return x.copy()
    if k < x.shape[0]:
        out[k:] = x[:-k]
    return out


def change(x, k=1):
    return x - lag(x, k)


def _valid_window(x, n):
    """True where the last n values are all finite (and there are n of them)."""
    f = _fin(x).astype(np.int64)
    c = np.cumsum(f, axis=0)
    prev = np.zeros_like(c)
    if n < x.shape[0]:
        prev[n:] = c[:-n]
    ok = (c - prev) == n
    ok[: n - 1] = False
    return ok


def rsum(x, n):
    x = np.asarray(x, float)
    ok = _valid_window(x, n)
    out = np.zeros_like(x)
    for j in range(n):
        out += np.nan_to_num(lag(x, j))
    return np.where(ok, out, np.nan)


def sma(x, n):
    return rsum(x, n) / n


def _recursive(x, n, alpha):
    x = np.asarray(x, float)
    T = x.shape[0]
    shp = x.shape[1:]
    out = np.full_like(x, np.nan)
    prev = np.full(shp, np.nan)
    seed = np.zeros(shp)
    run = np.zeros(shp)
    for i in range(T):
        v = x[i]
        good = np.isfinite(v)
        started = np.isfinite(prev)
        # not started and null -> reset seed
        reset = ~started & ~good
        seed = np.where(reset, 0.0, seed)
        run = np.where(reset, 0.0, run)
        acc = ~started & good
        seed = np.where(acc, seed + np.nan_to_num(v), seed)
        run = np.where(acc, run + 1, run)
        born = acc & (run == n)
        upd = started & good
        newp = np.where(upd, alpha * np.nan_to_num(v) + (1 - alpha) * np.nan_to_num(prev), prev)
        newp = np.where(born, seed / n, newp)
        out[i] = np.where(born | upd, newp, np.nan)
        prev = newp
    return out


def ema(x, n):
    return _recursive(x, n, 2.0 / (n + 1))


def rma(x, n):
    return _recursive(x, n, 1.0 / n)


def _weighted(x, wts):
    n = len(wts)
    x = np.asarray(x, float)
    out = np.zeros_like(x)
    for j in range(n):                    # wts[j] applies to the j-th value of the window, oldest first
        out += wts[j] * lag(x, n - 1 - j)
    return np.where(_valid_window(x, n), out, np.nan)


def wma(x, n):
    den = n * (n + 1) / 2
    return _weighted(x, [(j + 1) / den for j in range(n)])


def hma(x, n):
    half = wma(x, max(1, n // 2))
    full = wma(x, n)
    return wma(2 * half - full, max(1, int(math.floor(math.sqrt(n) + 0.5))))


def alma(x, n, offset=0.85, sigma=6):
    m = offset * (n - 1)
    s = n / sigma
    w = np.array([math.exp(-((j - m) ** 2) / (2 * s * s)) for j in range(n)])
    return _weighted(x, list(w / w.sum()))


def stdev(x, n):
    m = sma(x, n)
    acc = np.zeros_like(np.asarray(x, float))
    for j in range(n):
        acc += (lag(x, j) - m) ** 2
    return np.sqrt(acc / n)


def mean_dev(x, n):
    m = sma(x, n)
    acc = np.zeros_like(np.asarray(x, float))
    for j in range(n):
        acc += np.abs(lag(x, j) - m)
    return acc / n


def highest(x, n):
    x = np.asarray(x, float)
    out = x.copy()
    for j in range(1, n):
        out = np.fmax(out, lag(x, j))
    return np.where(_valid_window(x, n), out, np.nan)


def lowest(x, n):
    x = np.asarray(x, float)
    out = x.copy()
    for j in range(1, n):
        out = np.fmin(out, lag(x, j))
    return np.where(_valid_window(x, n), out, np.nan)


def _bars_since(x, n, ext):
    """Bars since the most recent extreme in the window (0 = this bar) - TS: n-1 - lastIndexOf(max)."""
    x = np.asarray(x, float)
    m = ext(x, n)
    out = np.full_like(x, np.nan)
    for j in range(n - 1, -1, -1):                 # descending j so the smallest j (most recent) wins last
        hit = lag(x, j) == m
        out = np.where(hit, j, out)
    return np.where(_valid_window(x, n), out, np.nan)


def highest_bars(x, n):
    return _bars_since(x, n, highest)


def lowest_bars(x, n):
    return _bars_since(x, n, lowest)


def cum(x):
    x = np.asarray(x, float)
    started = np.cumsum(_fin(x), axis=0) > 0
    return np.where(started, np.cumsum(np.nan_to_num(x), axis=0), np.nan)


def div(a, b):
    with np.errstate(divide="ignore", invalid="ignore"):
        return _clean(np.where(b == 0, np.nan, a / np.where(b == 0, 1, b)))


# ---------------------------------------------------------------------------------------------------------------- data
class Data:
    """O, H, L, C, V (T x N, packed), month id (period key for VWAP / pivots on daily bars)."""

    def __init__(self, O, H, L, C, V, month):
        C = np.asarray(C, float)
        self.C = C
        self.H = np.where(np.isfinite(H), H, C)
        self.L = np.where(np.isfinite(L), L, C)
        self.O = np.asarray(O, float)
        self.V = np.asarray(V, float)
        self.HL2 = (self.H + self.L) / 2
        self.TP = (self.H + self.L + C) / 3
        self.month = np.asarray(month)


def true_range(d: Data):
    pc = lag(d.C)
    tr = np.fmax(np.fmax(d.H - d.L, np.abs(d.H - pc)), np.abs(d.L - pc))
    return np.where(np.isfinite(pc), tr, d.H - d.L)


def rsi_of(x, n):
    ch = change(x)
    up = rma(np.where(np.isfinite(ch), np.maximum(ch, 0), np.nan), n)
    dn = rma(np.where(np.isfinite(ch), np.maximum(-ch, 0), np.nan), n)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.where(dn == 0, np.where(up == 0, 50.0, 100.0), 100 - 100 / (1 + up / dn))
    return _clean(np.where(np.isfinite(up) & np.isfinite(dn), r, np.nan))


def stoch_of(src, hi, lo, n):
    h, l_ = highest(hi, n), lowest(lo, n)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.where(h == l_, 50.0, 100 * (src - l_) / (h - l_))
    return _clean(np.where(np.isfinite(src) & np.isfinite(h) & np.isfinite(l_), r, np.nan))


def _anchored_vwap(d: Data):
    T = d.C.shape[0]
    out = np.full_like(d.C, np.nan)
    pv = np.zeros(d.C.shape[1:])
    vol = np.zeros(d.C.shape[1:])
    for i in range(T):
        new = (d.month[i] != d.month[i - 1]) if i > 0 else np.ones(d.C.shape[1:], bool)
        pv = np.where(new, 0.0, pv)
        vol = np.where(new, 0.0, vol)
        pv = pv + d.TP[i] * d.V[i]
        vol = vol + d.V[i]
        with np.errstate(divide="ignore", invalid="ignore"):
            out[i] = np.where(vol > 0, pv / vol, np.nan)
    return _clean(out)


def _pivot_p(d: Data):
    T = d.C.shape[0]
    shp = d.C.shape[1:]
    out = np.full_like(d.C, np.nan)
    ph = np.full(shp, np.nan); pl = np.full(shp, np.nan); pc = np.full(shp, np.nan)
    ch = np.full(shp, -np.inf); cl = np.full(shp, np.inf); cc = np.zeros(shp)
    have_prev = np.zeros(shp, bool)
    have_cur = np.zeros(shp, bool)
    for i in range(T):
        new = (d.month[i] != d.month[i - 1]) if i > 0 else np.ones(shp, bool)
        ph = np.where(new & have_cur, ch, ph); pl = np.where(new & have_cur, cl, pl); pc = np.where(new & have_cur, cc, pc)
        have_prev = np.where(new, have_cur, have_prev)
        ch = np.where(new, -np.inf, ch); cl = np.where(new, np.inf, cl)
        have_cur = have_cur | new
        ch = np.fmax(ch, d.H[i]); cl = np.fmin(cl, d.L[i]); cc = d.C[i]
        out[i] = np.where(have_prev, (ph + pl + pc) / 3, np.nan)
    return out


def _psar(d: Data, start, inc, mx):
    H, L, C = d.H, d.L, d.C
    T = C.shape[0]
    shp = C.shape[1:]
    out = np.full_like(C, np.nan)
    if T < 2:
        return out
    up = C[1] >= C[0]
    sar = np.where(up, L[0], H[0])
    ep = np.where(up, H[1], L[1])
    af = np.full(shp, float(start))
    for i in range(1, T):
        sar = sar + af * (ep - sar)
        l2 = L[i - 2] if i > 1 else L[i - 1]
        h2 = H[i - 2] if i > 1 else H[i - 1]
        s_up = np.minimum(np.minimum(sar, L[i - 1]), l2)
        s_dn = np.maximum(np.maximum(sar, H[i - 1]), h2)
        sar = np.where(up, s_up, s_dn)
        flip_dn = up & (L[i] < sar)
        flip_up = ~up & (H[i] > sar)
        ext_up = up & ~flip_dn & (H[i] > ep)
        ext_dn = ~up & ~flip_up & (L[i] < ep)
        new_sar = np.where(flip_dn | flip_up, ep, sar)
        new_ep = np.where(flip_dn, L[i], np.where(flip_up, H[i], np.where(ext_up, H[i], np.where(ext_dn, L[i], ep))))
        new_af = np.where(flip_dn | flip_up, start, np.where(ext_up | ext_dn, np.minimum(af + inc, mx), af))
        up = np.where(flip_dn, False, np.where(flip_up, True, up))
        sar, ep, af = new_sar, new_ep, new_af
        out[i] = sar
    return out


def _supertrend(d: Data, atr_len, mult):
    atr = rma(true_range(d), atr_len)
    T = d.C.shape[0]
    shp = d.C.shape[1:]
    up_l = np.full_like(d.C, np.nan)
    dn_l = np.full_like(d.C, np.nan)
    fu = np.full(shp, np.nan)
    fl = np.full(shp, np.nan)
    dr = np.ones(shp)
    for i in range(T):
        a = atr[i]
        ok = np.isfinite(a)
        hl2, c = d.HL2[i], d.C[i]
        pc = d.C[i - 1] if i > 0 else c
        bu, bl = hl2 + mult * a, hl2 - mult * a
        nfu = np.where(np.isnan(fu) | (bu < fu) | (pc > fu), bu, fu)
        nfl = np.where(np.isnan(fl) | (bl > fl) | (pc < fl), bl, fl)
        both = np.isfinite(fu) & np.isfinite(fl)
        ndr = np.where(both & (dr == 1) & (c < nfl), -1, np.where(both & (dr == -1) & (c > nfu), 1, dr))
        dr = np.where(ok, ndr, dr)
        fu = np.where(ok, nfu, fu)
        fl = np.where(ok, nfl, fl)
        up_l[i] = np.where(ok & (dr == 1), fl, np.nan)
        dn_l[i] = np.where(ok & (dr == -1), fu, np.nan)
    return up_l, dn_l


def _fisher(d: Data, n):
    hh, ll = highest(d.HL2, n), lowest(d.HL2, n)
    T = d.C.shape[0]
    shp = d.C.shape[1:]
    out = np.full_like(d.C, np.nan)
    v = np.zeros(shp)
    f = np.zeros(shp)
    for i in range(T):
        ok = np.isfinite(hh[i]) & np.isfinite(ll[i])
        r = hh[i] - ll[i]
        with np.errstate(divide="ignore", invalid="ignore"):
            frac = np.where(r == 0, 0.0, (d.HL2[i] - ll[i]) / np.where(r == 0, 1, r) - 0.5)
        nv = np.clip(0.66 * frac + 0.67 * v, -0.999, 0.999)
        nf = 0.5 * np.log((1 + nv) / (1 - nv)) + 0.5 * f
        v = np.where(ok, nv, v)
        f = np.where(ok, nf, f)
        out[i] = np.where(ok, f, np.nan)
    return out


def _mfv(d: Data):
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.where(d.H == d.L, 0.0, ((d.C - d.L - (d.H - d.C)) / (d.H - d.L)) * d.V)
    return _clean(np.where(np.isfinite(d.C) & np.isfinite(d.V), r, np.nan))


def _dmi(d: Data, di_len, adx_len):
    upm = change(d.H)
    dnm = -change(d.L)
    ok = np.isfinite(upm) & np.isfinite(dnm)
    plus_dm = np.where(ok, np.where((upm > dnm) & (upm > 0), upm, 0.0), np.nan)
    minus_dm = np.where(ok, np.where((dnm > upm) & (dnm > 0), dnm, 0.0), np.nan)
    tr = rma(true_range(d), di_len)
    plus = div(100 * rma(plus_dm, di_len), tr)
    minus = div(100 * rma(minus_dm, di_len), tr)
    with np.errstate(divide="ignore", invalid="ignore"):
        dx = np.where(plus + minus == 0, 0.0, 100 * np.abs(plus - minus) / (plus + minus))
    dx = _clean(np.where(np.isfinite(plus) & np.isfinite(minus), dx, np.nan))
    return rma(dx, adx_len), plus, minus


def plots(ind: str, d: Data, p: dict | None = None) -> dict[str, np.ndarray]:
    """The TS plots of one indicator (raw lines, as the chart draws them)."""
    p = params_for(ind, p)
    C, H, L, V = d.C, d.H, d.L, d.V
    if ind == "sma":
        return {"ma": sma(C, p["len"])}
    if ind == "ema":
        return {"ma": ema(C, p["len"])}
    if ind == "wma":
        return {"ma": wma(C, p["len"])}
    if ind == "hma":
        return {"ma": hma(C, p["len"])}
    if ind == "vwma":
        return {"ma": div(sma(C * V, p["len"]), sma(V, p["len"]))}
    if ind == "alma":
        return {"ma": alma(C, p["len"], p["offset"], p["sigma"])}
    if ind == "vwap":
        return {"vwap": _anchored_vwap(d)}
    if ind in ("bb", "bbpb", "bbw"):
        b, s = sma(C, p["len"]), stdev(C, p["len"])
        if ind == "bb":
            return {"basis": b, "upper": b + p["mult"] * s, "lower": b - p["mult"] * s}
        if ind == "bbpb":
            with np.errstate(divide="ignore", invalid="ignore"):
                return {"pb": _clean(np.where(s == 0, 0.5, (C - (b - p["mult"] * s)) / (2 * p["mult"] * s)))}
        return {"bbw": div(100 * 2 * p["mult"] * s, b)}
    if ind == "kc":
        b = ema(C, p["len"])
        a = rma(true_range(d), p["atr"])
        return {"basis": b, "upper": b + p["mult"] * a, "lower": b - p["mult"] * a}
    if ind == "dc":
        u, l_ = highest(H, p["len"]), lowest(L, p["len"])
        return {"upper": u, "lower": l_, "basis": (u + l_) / 2}
    if ind == "env":
        b = sma(C, p["len"])
        return {"basis": b, "upper": b * (1 + p["pct"] / 100), "lower": b * (1 - p["pct"] / 100)}
    if ind == "ichimoku":
        mid = lambda n: (highest(H, n) + lowest(L, n)) / 2  # noqa: E731
        conv, base = mid(p["conv"]), mid(p["base"])
        a = (conv + base) / 2
        b = mid(p["spanB"])
        return {"conv": conv, "base": base, "a": lag(a, p["disp"] - 1), "b": lag(b, p["disp"] - 1)}
    if ind == "psar":
        return {"sar": _psar(d, p["start"], p["inc"], p["max"])}
    if ind == "supertrend":
        u, dn = _supertrend(d, p["atr"], p["mult"])
        return {"up": u, "down": dn}
    if ind == "pivots":
        return {"p": _pivot_p(d)}
    if ind == "volume":
        return {"vol": V, "ma": sma(V, p["ma"])}
    if ind == "obv":
        ch = change(C)
        return {"obv": cum(np.where(np.isfinite(ch) & np.isfinite(V), np.sign(ch) * V, np.nan))}
    if ind == "mfi":
        ch = change(d.TP)
        mf = d.TP * V
        okk = np.isfinite(ch) & np.isfinite(mf)
        pos = rsum(np.where(okk, np.where(ch > 0, mf, 0.0), np.nan), p["len"])
        neg = rsum(np.where(okk, np.where(ch < 0, mf, 0.0), np.nan), p["len"])
        with np.errstate(divide="ignore", invalid="ignore"):
            r = np.where(neg == 0, 100.0, 100 - 100 / (1 + pos / neg))
        return {"mfi": _clean(np.where(np.isfinite(pos) & np.isfinite(neg), r, np.nan))}
    if ind == "cmf":
        return {"cmf": div(rsum(_mfv(d), p["len"]), rsum(V, p["len"]))}
    if ind == "ad":
        return {"ad": cum(_mfv(d))}
    if ind == "chaikinosc":
        ad = cum(_mfv(d))
        return {"osc": ema(ad, p["fast"]) - ema(ad, p["slow"])}
    if ind == "pvt":
        ch, pc = change(C), lag(C)
        with np.errstate(divide="ignore", invalid="ignore"):
            r = np.where(pc == 0, 0.0, ch / pc * V)
        return {"pvt": cum(_clean(np.where(np.isfinite(ch) & np.isfinite(pc) & np.isfinite(V), r, np.nan)))}
    if ind == "volosc":
        s = ema(V, p["slow"])
        return {"vo": div(100 * (ema(V, p["fast"]) - s), s)}
    if ind == "efi":
        return {"efi": ema(change(C) * V, p["len"])}
    if ind == "eom":
        ch = change(d.HL2)
        with np.errstate(divide="ignore", invalid="ignore"):
            r = np.where(V == 0, np.nan, p["div"] * ch * (H - L) / V)
        return {"eom": sma(_clean(r), p["len"])}
    if ind == "netvol":
        ch = change(C)
        return {"nv": np.where(np.isfinite(ch) & np.isfinite(V), np.sign(ch) * V, np.nan)}
    if ind == "rsi":
        return {"rsi": rsi_of(C, p["len"])}
    if ind in ("macd", "ppo"):
        f, s_ = ema(C, p["fast"]), ema(C, p["slow"])
        m = f - s_ if ind == "macd" else div(100 * (f - s_), s_)
        sg = ema(m, p["sig"])
        return {"hist": m - sg, "line": m, "signal": sg}
    if ind == "stoch":
        k = sma(stoch_of(C, H, L, p["k"]), p["ks"])
        return {"k": k, "d": sma(k, p["d"])}
    if ind == "stochrsi":
        r = rsi_of(C, p["rsi"])
        k = sma(stoch_of(r, r, r, p["st"]), p["k"])
        return {"k": k, "d": sma(k, p["d"])}
    if ind == "cci":
        m, md = sma(d.TP, p["len"]), mean_dev(d.TP, p["len"])
        with np.errstate(divide="ignore", invalid="ignore"):
            r = np.where(md == 0, 0.0, (d.TP - m) / (0.015 * md))
        return {"cci": _clean(np.where(np.isfinite(m) & np.isfinite(md), r, np.nan))}
    if ind == "wpr":
        h, l_ = highest(H, p["len"]), lowest(L, p["len"])
        with np.errstate(divide="ignore", invalid="ignore"):
            r = np.where(h == l_, -50.0, -100 * (h - C) / (h - l_))
        return {"wpr": _clean(np.where(np.isfinite(h) & np.isfinite(l_), r, np.nan))}
    if ind == "roc":
        pc = lag(C, p["len"])
        return {"roc": div(100 * (C - pc), pc)}
    if ind == "mom":
        return {"mom": change(C, p["len"])}
    if ind == "ao":
        return {"ao": sma(d.HL2, 5) - sma(d.HL2, 34)}
    if ind == "uo":
        pc = lag(C)
        bp = C - np.fmin(L, pc)
        bp = np.where(np.isfinite(pc), bp, np.nan)
        tr = np.where(np.isfinite(pc), np.fmax(H, pc) - np.fmin(L, pc), np.nan)
        avg = lambda n: div(rsum(bp, n), rsum(tr, n))  # noqa: E731
        return {"uo": 100 * (4 * avg(p["f"]) + 2 * avg(p["m"]) + avg(p["s"])) / 7}
    if ind == "trix":
        with np.errstate(divide="ignore", invalid="ignore"):
            lc = _clean(np.log(C))
        return {"trix": change(ema(ema(ema(lc, p["len"]), p["len"]), p["len"])) * 10000}
    if ind == "tsi":
        pc = change(C)
        ds = lambda x: ema(ema(x, p["long"]), p["short"])  # noqa: E731
        t = div(100 * ds(pc), ds(np.abs(pc)))
        return {"tsi": t, "sig": ema(t, p["sig"])}
    if ind == "cmo":
        ch = change(C)
        okk = np.isfinite(ch)
        up = rsum(np.where(okk, np.maximum(ch, 0), np.nan), p["len"])
        dn = rsum(np.where(okk, np.maximum(-ch, 0), np.nan), p["len"])
        with np.errstate(divide="ignore", invalid="ignore"):
            r = np.where(up + dn == 0, 0.0, 100 * (up - dn) / (up + dn))
        return {"cmo": _clean(np.where(np.isfinite(up) & np.isfinite(dn), r, np.nan))}
    if ind == "bop":
        with np.errstate(divide="ignore", invalid="ignore"):
            r = np.where(H == L, 0.0, (C - d.O) / (H - L))
        return {"bop": _clean(np.where(np.isfinite(d.O), r, np.nan))}
    if ind == "coppock":
        roc = lambda n: div(100 * (C - lag(C, n)), lag(C, n))  # noqa: E731
        return {"cc": wma(roc(p["long"]) + roc(p["short"]), p["wma"])}
    if ind == "dpo":
        return {"dpo": C - lag(sma(C, p["len"]), p["len"] // 2 + 1)}
    if ind == "fisher":
        f = _fisher(d, p["len"])
        return {"fish": f, "trig": lag(f)}
    if ind == "dmi":
        a, pl, mi = _dmi(d, p["di"], p["adx"])
        return {"adx": a, "plus": pl, "minus": mi}
    if ind == "aroon":
        n = p["len"]
        return {"up": 100 * (n - highest_bars(H, n + 1)) / n, "down": 100 * (n - lowest_bars(L, n + 1)) / n}
    if ind == "vortex":
        tr = rsum(true_range(d), p["len"])
        vp = rsum(np.abs(H - lag(L)), p["len"])
        vm = rsum(np.abs(L - lag(H)), p["len"])
        return {"vp": div(vp, tr), "vm": div(vm, tr)}
    if ind == "chop":
        s, h, l_ = rsum(true_range(d), p["len"]), highest(H, p["len"]), lowest(L, p["len"])
        with np.errstate(divide="ignore", invalid="ignore"):
            r = np.where(h == l_, np.nan, 100 * np.log10(s / (h - l_)) / math.log10(p["len"]))
        return {"chop": _clean(r)}
    if ind == "mass":
        e1 = ema(H - L, 9)
        return {"mi": rsum(div(e1, ema(e1, 9)), p["len"])}
    if ind == "atr":
        return {"atr": rma(true_range(d), p["len"])}
    if ind == "stdev":
        return {"sd": stdev(C, p["len"])}
    if ind == "hv":
        with np.errstate(divide="ignore", invalid="ignore"):
            lr = _clean(np.log(C / lag(C)))
        return {"hv": 100 * stdev(lr, p["len"]) * math.sqrt(252)}
    raise KeyError(ind)


# ---------------------------------------------------------------------------------------------------------------- research values
# One scale-free number per indicator (higher = the conventional bullish reading, except the non-directional volatility /
# trend-strength ones, whose sign the IC decides). Price overlays are read as the close's distance to the line; band
# indicators as the close's position inside the band; cumulative volume lines (OBV, A/D, PVT) as their distance to their own
# 20-bar SMA in units of the 20-bar average volume; volume-scaled oscillators divided by average volume (and price).
GROUP = {
    "sma": "MA", "ema": "MA", "wma": "MA", "hma": "MA", "vwma": "MA", "alma": "MA", "vwap": "MA",
    "bb": "Bands", "kc": "Bands", "dc": "Bands", "env": "Bands", "ichimoku": "Bands",
    "psar": "Trend", "supertrend": "Trend", "pivots": "Trend", "adx": "Trend", "di": "Trend", "aroon": "Trend", "vortex": "Trend",
    "chop": "Trend", "mass": "Trend",
    "volume": "Volume", "obv": "Volume", "mfi": "Volume", "cmf": "Volume", "ad": "Volume", "chaikinosc": "Volume", "pvt": "Volume",
    "volosc": "Volume", "efi": "Volume", "eom": "Volume", "netvol": "Volume",
    "rsi": "Momentum", "macd": "Momentum", "stoch": "Momentum", "stochrsi": "Momentum", "cci": "Momentum", "wpr": "Momentum",
    "roc": "Momentum", "mom": "Momentum", "ao": "Momentum", "uo": "Momentum", "trix": "Momentum", "tsi": "Momentum", "ppo": "Momentum",
    "cmo": "Momentum", "bop": "Momentum", "coppock": "Momentum", "dpo": "Momentum", "fisher": "Momentum",
    "atr": "Volatility", "stdev": "Volatility", "hv": "Volatility", "bbpb": "Volatility", "bbw": "Volatility",
}
VALUE_NAMES = list(GROUP)
SOURCE = {"adx": "dmi", "di": "dmi"}                     # value name -> catalog id when they differ


def _band_pos(c, lo, up):
    with np.errstate(divide="ignore", invalid="ignore"):
        return _clean((c - lo) / (up - lo))


def value(name: str, d: Data, p: dict | None = None) -> np.ndarray:
    ind = SOURCE.get(name, name)
    q = plots(ind, d, p)
    C, V = d.C, d.V
    v20 = sma(V, 20)
    if GROUP.get(name) == "MA":
        line = q.get("ma", q.get("vwap"))
        return div(C, line) - 1
    if name in ("bb", "kc", "dc", "env"):
        return _band_pos(C, q["lower"], q["upper"])
    if name == "ichimoku":
        return div(C, np.fmax(q["a"], q["b"])) - 1
    if name == "psar":
        return div(C, q["sar"]) - 1
    if name == "supertrend":
        return div(C, np.where(np.isfinite(q["up"]), q["up"], q["down"])) - 1
    if name == "pivots":
        return div(C, q["p"]) - 1
    if name == "adx":
        return q["adx"]
    if name == "di":
        return q["plus"] - q["minus"]
    if name == "aroon":
        return q["up"] - q["down"]
    if name == "vortex":
        return q["vp"] - q["vm"]
    if name == "volume":
        return div(V, q["ma"])
    if name in ("obv", "ad", "pvt"):
        x = q[name]
        return div(x - sma(x, 20), v20)
    if name == "chaikinosc":
        return div(q["osc"], v20)
    if name == "efi":
        return div(q["efi"], v20 * C)
    if name == "eom":
        return div(q["eom"] * v20, C * C)
    if name == "netvol":
        return div(q["nv"], v20)
    if name == "macd":
        return div(100 * q["hist"], C)
    if name == "ppo":
        return q["line"]
    if name in ("stoch", "stochrsi"):
        return q["k"]
    if name in ("mom", "ao", "dpo"):
        return div(100 * q[{"mom": "mom", "ao": "ao", "dpo": "dpo"}[name]], C)
    if name == "fisher":
        return q["fish"]
    if name == "tsi":
        return q["tsi"]
    if name in ("atr", "stdev"):
        return div(q[{"atr": "atr", "stdev": "sd"}[name]], C)
    if name == "bbpb":
        return q["pb"]
    k = next(iter(q))
    return q[k]


# ---------------------------------------------------------------------------------------------------------------- packing
def pack(X: np.ndarray, valid: np.ndarray):
    """Move each column's valid rows to the top. Returns packed array and the (row index) map for unpacking."""
    T, N = X.shape
    order = np.argsort(~valid, axis=0, kind="stable")        # valid rows first, in time order
    Xp = np.take_along_axis(X, order, axis=0)
    cnt = valid.sum(axis=0)
    Xp[np.arange(T)[:, None] >= cnt[None, :]] = np.nan
    return Xp, order, cnt


def unpack(Xp: np.ndarray, order: np.ndarray, cnt: np.ndarray):
    T, N = Xp.shape
    out = np.full((T, N), np.nan)
    keep = np.arange(T)[:, None] < cnt[None, :]
    rows = np.where(keep, order, 0)
    cols = np.broadcast_to(np.arange(N), (T, N))
    out[rows[keep], cols[keep]] = Xp[keep]
    return out


def packed_data(O, H, L, C, V, dates):
    """Data on packed arrays from dated (T x N) panels; valid = finite close > 0."""
    C = np.asarray(C, float)
    valid = np.isfinite(C) & (C > 0)
    month = np.asarray(dates.year * 12 + dates.month)
    Mp = np.broadcast_to(month[:, None], C.shape).astype(float)
    pk = lambda X: pack(np.asarray(X, float), valid)[0]  # noqa: E731
    Cp, order, cnt = pack(C, valid)
    d = Data(pk(O), pk(H), pk(L), Cp, pk(np.nan_to_num(np.asarray(V, float))), pk(Mp))
    return d, order, cnt


def compute(O, H, L, C, V, dates, names=None, params: dict | None = None, scale: float = 1.0) -> dict[str, np.ndarray]:
    """Research values on dated panels (T x N numpy). params: {name: override}; scale: every length x scale (neighbours)."""
    d, order, cnt = packed_data(O, H, L, C, V, dates)
    out = {}
    for nm in names or VALUE_NAMES:
        ind = SOURCE.get(nm, nm)
        p = params_for(ind, (params or {}).get(nm), scale)
        out[nm] = unpack(value(nm, d, p), order, cnt)
    return out
