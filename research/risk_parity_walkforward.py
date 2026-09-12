#!/usr/bin/env python3
"""PORTFOLIO-ADMISSION GATE — offline OOS WALK-FORWARD of the gold+crypto
risk-parity combined book (2026-07-16).

Extends research/risk_parity_combine.py (full-sample, in-sample) to an honest
out-of-sample walk-forward: sequential expanding train->test folds, vol-parity
weights estimated IN-SAMPLE per fold and applied OOS, OOS fold returns
concatenated, then Sharpe / DSR / maxDD / cross-sleeve OOS correlation computed
on the concatenated OOS series. Weights are NEVER tuned on the test fold.

Two sleeves, both reconstructed offline on the daily donchian family so they
share one daily grid and are directly comparable (matches the deployed
DonchianBreakoutEngine and the gold offline validation):
  - crypto: DCB-1d pool BTC/ETH/SOL/XRP, two-sided donchian-20 entry /
    opp-channel-10 exit, equal-weight across coins active that day.
  - gold:   XAUUSD long-only donchian-40 entry / opp-channel-20 exit (the
    robust gold config: d-40/20 PF 2.42 Sharpe 0.62 offline).

DSR: deflated Sharpe ratio (Bailey/Lopez de Prado). We deflate for the number
of configurations tried across this whole gold+crypto research program so the
multiplicity tax is honest (not just 1). Annualization: the combined book lives
on the union daily grid; crypto is 365/day-cadence, gold ~252. We annualize the
COMBINED daily series at 365 (the binding daily grid; gold flat days contribute
0 return) and report a 252-basis sensitivity. Offline; never touches V11 math.

Data: research/.rtmp/rp/<SYM>.csv  (date,high,low,close), pulled from VPS
market_data. 8bps/side cost.
"""
import csv, math, os
from statistics import NormalDist

DATA = os.environ.get("RP_DATA", r"C:\Project\.rtmp\rp")
COST_BPS = 8.0
CRYPTO = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
GOLD = "XAUUSD"
# Number of distinct configs tried across the gold+crypto risk-parity program,
# used to deflate the Sharpe. Gold: 4 donchian cells x 2 sides = 8. Crypto pool
# baseline + 55/Turtle variant + XS 6 cells = ~8. Combination weightings tried:
# vol-parity (this). Be conservative/adversarial: N_TRIALS = 20.
N_TRIALS = 20


def load(sym):
    rows = []
    with open(os.path.join(DATA, sym + ".csv")) as f:
        for d, h, l, c in csv.reader(f):
            try:
                rows.append((d, float(h), float(l), float(c)))
            except ValueError:
                pass
    return rows


def sleeve_daily(sym, entry_n, exit_n, long_only):
    """{date: daily_log_return} for a donchian-breakout + opp-channel-exit sleeve.
    Held-day return = pos * log(c/prev_c); round-trip cost debited on exit bar."""
    b = load(sym)
    highs = [x[1] for x in b]; lows = [x[2] for x in b]; closes = [x[3] for x in b]
    dates = [x[0] for x in b]
    n = len(b); pos = 0; prev = None
    cost = COST_BPS / 10000.0
    daily = {}
    for i in range(entry_n + 1, n):
        upE = max(highs[i - entry_n:i]); loE = min(lows[i - entry_n:i])
        upX = max(highs[i - exit_n:i]); loX = min(lows[i - exit_n:i])
        c = closes[i]
        r = 0.0
        if pos != 0 and prev is not None and prev > 0:
            r = pos * math.log(c / prev)
        prev = c
        if pos == 1 and c <= loX:
            r -= 2 * cost; pos = 0
        elif pos == -1 and c >= upX:
            r -= 2 * cost; pos = 0
        if pos == 0:
            if c > upE:
                pos = 1
            elif c < loE and not long_only:
                pos = -1
        daily[dates[i]] = daily.get(dates[i], 0.0) + r
    return daily


def sharpe(series, ann):
    if len(series) < 2:
        return 0.0, 0.0, 0.0
    mu = sum(series) / len(series)
    sd = math.sqrt(sum((x - mu) ** 2 for x in series) / len(series))
    return (mu / sd * math.sqrt(ann)) if sd > 0 else 0.0, mu, sd


def maxdd(series):
    eq = 1.0; peak = 1.0; mdd = 0.0
    for r in series:
        eq *= math.exp(r); peak = max(peak, eq)
        mdd = max(mdd, (peak - eq) / peak)
    return mdd * 100


def cagr(series, ann):
    if not series:
        return 0.0
    eq = 1.0
    for r in series:
        eq *= math.exp(r)
    yrs = len(series) / ann
    return (eq ** (1.0 / yrs) - 1) * 100 if yrs > 0 else 0.0


def moments_sharpe(series):
    """Non-annualized (per-period) Sharpe + skew + kurtosis of the return series,
    for the deflated-Sharpe computation."""
    n = len(series)
    mu = sum(series) / n
    sd = math.sqrt(sum((x - mu) ** 2 for x in series) / n)
    if sd == 0:
        return 0.0, 0.0, 3.0, n
    sk = (sum((x - mu) ** 3 for x in series) / n) / sd ** 3
    ku = (sum((x - mu) ** 4 for x in series) / n) / sd ** 4
    return mu / sd, sk, ku, n


def deflated_sharpe(series, n_trials):
    """DSR = Prob(true Sharpe > benchmark) after deflating the observed Sharpe for
    the number of trials and the non-normality of returns (Bailey & Lopez de Prado
    2014, "The Deflated Sharpe Ratio"). SR_hat and SR0 are BOTH per-period (daily).

      SR0 (benchmark expected-max Sharpe) = sqrt(V_SR) * E[max_N of standard normal]
      V_SR = (1/(n-1)) * (1 - g3*SR_hat + (g4-1)/4 * SR_hat^2)   [Sharpe estimator var]
      DSR  = Phi( (SR_hat - SR0) / sqrt(V_SR) )

    Under N iid trials, the expected maximum of N standard normals scales the
    estimator-standard-error into a per-period benchmark Sharpe — this is what
    makes DSR fall as N (multiplicity) rises. Returns (DSR, annualized_SR@365)."""
    sr, sk, ku, n = moments_sharpe(series)   # sr = daily (per-period) Sharpe
    if n < 3:
        return 0.0, sr * math.sqrt(365)
    Z = NormalDist()
    e = 0.5772156649015329  # Euler-Mascheroni
    # variance of the Sharpe estimator (skew/kurtosis corrected), per-period^2
    v_sr = (1 - sk * sr + (ku - 1) / 4.0 * sr ** 2) / (n - 1)
    if v_sr <= 0:
        return 0.0, sr * math.sqrt(365)
    se = math.sqrt(v_sr)
    # E[max of N standard normals] (Bailey-LdP approximation)
    if n_trials > 1:
        emax = (Z.inv_cdf(1 - 1.0 / n_trials) * (1 - e)
                + Z.inv_cdf(1 - 1.0 / (n_trials * math.e)) * e)
    else:
        emax = 0.0
    sr0 = se * emax                          # benchmark per-period Sharpe
    dsr = Z.cdf((sr - sr0) / se)
    return dsr, sr * math.sqrt(365)


def corr(a, b):
    pairs = [(x, y) for x, y in zip(a, b) if x != 0 and y != 0]
    if len(pairs) < 3:
        return float("nan"), 0
    ax = [x for x, _ in pairs]; bx = [y for _, y in pairs]
    ma = sum(ax) / len(ax); mb = sum(bx) / len(bx)
    cov = sum((x - ma) * (y - mb) for x, y in pairs) / len(pairs)
    sa = math.sqrt(sum((x - ma) ** 2 for x in ax) / len(ax))
    sb = math.sqrt(sum((y - mb) ** 2 for y in bx) / len(bx))
    return (cov / (sa * sb) if sa > 0 and sb > 0 else 0.0), len(pairs)


def build_sleeves(gold_entry, gold_exit):
    # crypto pool: equal-weight coins active that day
    cd = {}
    for sym in CRYPTO:
        for d, r in sleeve_daily(sym, 20, 10, long_only=False).items():
            cd.setdefault(d, []).append(r)
    crypto = {d: sum(v) / len(v) for d, v in cd.items()}
    gold = sleeve_daily(GOLD, gold_entry, gold_exit, long_only=True)
    return crypto, gold


def run_wf(gold_entry, gold_exit, common_start, n_folds, label, verbose):
    """One walk-forward pass. Returns a dict of concatenated-OOS metrics."""
    crypto, gold = build_sleeves(gold_entry, gold_exit)
    common = sorted(d for d in (set(crypto) & set(gold)) if d >= common_start)
    if not common:
        common = sorted(set(crypto) & set(gold))
    start, end = common[0], common[-1]
    c_full = [crypto.get(d, 0.0) for d in common]
    g_full = [gold.get(d, 0.0) for d in common]
    N = len(common); warm = N // 3; step = (N - warm) // n_folds
    oos_c, oos_g, oos_comb, oos_dates = [], [], [], []
    fold_rows = []
    for k in range(n_folds):
        tr_end = warm + k * step
        te_end = warm + (k + 1) * step if k < n_folds - 1 else N
        tr_c = c_full[:tr_end]; tr_g = g_full[:tr_end]
        te_c = c_full[tr_end:te_end]; te_g = g_full[tr_end:te_end]
        te_d = common[tr_end:te_end]
        if len(te_c) < 5:
            continue
        vc = math.sqrt(sum(x * x for x in tr_c) / len(tr_c)) or 1e-9
        vg = math.sqrt(sum(x * x for x in tr_g) / len(tr_g)) or 1e-9
        wc = (1 / vc) / (1 / vc + 1 / vg); wg = 1 - wc
        te_comb = [wc * te_c[i] + wg * te_g[i] for i in range(len(te_c))]
        oos_c += te_c; oos_g += te_g; oos_comb += te_comb; oos_dates += te_d
        shk, _, _ = sharpe(te_comb, 365)
        shc, _, _ = sharpe(te_c, 365); shg, _, _ = sharpe(te_g, 252)
        fold_rows.append((k + 1, te_d[0], te_d[-1], len(te_c), wc, wg, shc, shg, shk,
                          cagr(te_comb, 365), maxdd(te_comb)))
    sh_c, _, _ = sharpe(oos_c, 365); sh_g, _, _ = sharpe(oos_g, 252)
    sh_k365, _, _ = sharpe(oos_comb, 365); sh_k252, _, _ = sharpe(oos_comb, 252)
    dsr_c, _ = deflated_sharpe(oos_c, N_TRIALS)
    dsr_g, _ = deflated_sharpe(oos_g, N_TRIALS)
    dsr_k, _ = deflated_sharpe(oos_comb, N_TRIALS)
    xcorr, ncorr = corr(oos_c, oos_g)
    fold_sh = [r[8] for r in fold_rows]
    pos_folds = sum(1 for s in fold_sh if s > 0)
    m = dict(label=label, start=start, end=end, N=N, folds=fold_rows, n_folds=len(fold_rows),
             sh_c=sh_c, sh_g=sh_g, sh_k365=sh_k365, sh_k252=sh_k252,
             dsr_c=dsr_c, dsr_g=dsr_g, dsr_k=dsr_k, xcorr=xcorr, ncorr=ncorr,
             dd_c=maxdd(oos_c), dd_g=maxdd(oos_g), dd_k=maxdd(oos_comb),
             cg_c=cagr(oos_c, 365), cg_g=cagr(oos_g, 252), cg_k=cagr(oos_comb, 365),
             pos_folds=pos_folds, warm=warm, step=step)
    if verbose:
        print_detail(m, gold_entry, gold_exit)
    return m


def print_detail(m, ge, gx):
    print("=" * 84)
    print("PORTFOLIO-ADMISSION GATE — OOS WALK-FORWARD  [%s]" % m["label"])
    print("gold long-only d-%d/%d + crypto DCB-1d pool (donchian-20/10, 2-sided)" % (ge, gx))
    print("=" * 84)
    print("common window: %s -> %s  (%d union days)  cost=%.0fbps/side  N_TRIALS(deflate)=%d" % (m["start"], m["end"], m["N"], COST_BPS, N_TRIALS))
    print("walk-forward: expanding train (warmup=%d) -> %d sequential OOS blocks (step~%d d)" % (m["warm"], m["n_folds"], m["step"]))
    print()
    print("PER-FOLD OOS (vol-parity weights fit IN-SAMPLE, applied OOS):")
    print("  fold  test-window            days  wC   wG   Sh_cr  Sh_gd  Sh_COMB  CAGR%   maxDD%")
    for (k, d0, d1, nd, wc, wg, shc, shg, shk, cg, md) in m["folds"]:
        print("   %d    %s..%s %4d %.2f %.2f %+.2f  %+.2f  %+.3f  %+6.1f  %5.1f" %
              (k, d0, d1, nd, wc, wg, shc, shg, shk, cg, md))
    print()
    print("CONCATENATED OOS:")
    print("  SOLO crypto pool :  Sharpe %+.3f (365)  DSR %.3f  maxDD %.1f%%  CAGR %+.1f%%" % (m["sh_c"], m["dsr_c"], m["dd_c"], m["cg_c"]))
    print("  SOLO gold l/only :  Sharpe %+.3f (252)  DSR %.3f  maxDD %.1f%%  CAGR %+.1f%%" % (m["sh_g"], m["dsr_g"], m["dd_g"], m["cg_g"]))
    print("  COMBINED book    :  Sharpe %+.3f (365)  DSR %.3f  maxDD %.1f%%  CAGR %+.1f%%   [252-ann Sh %+.3f]" % (m["sh_k365"], m["dsr_k"], m["dd_k"], m["cg_k"], m["sh_k252"]))
    print("  cross-sleeve OOS corr (n=%d): %.3f | Sharpe lift %+.3f | DSR lift %+.3f | %d/%d folds +" %
          (m["ncorr"], m["xcorr"], m["sh_k365"] - max(m["sh_c"], m["sh_g"]), m["dsr_k"] - max(m["dsr_c"], m["dsr_g"]), m["pos_folds"], m["n_folds"]))
    verdict(m)


def verdict(m):
    admit_edge = True
    admit_orth = (not math.isnan(m["xcorr"])) and abs(m["xcorr"]) < 0.30
    admit_lift = m["dsr_k"] > max(m["dsr_c"], m["dsr_g"])
    clears = m["dsr_k"] >= 0.90 and m["pos_folds"] >= m["n_folds"] - 1
    print()
    print("  VERDICT: (a)edge %s  (b)|corr|<0.30 %s  (c)raises book DSR %s  (d)DSR>=0.90 %s"
          % ("PASS" if admit_edge else "FAIL",
             "PASS(%.3f)" % m["xcorr"] if admit_orth else "FAIL(%.3f)" % m["xcorr"],
             "PASS(%.3f>%.3f)" % (m["dsr_k"], max(m["dsr_c"], m["dsr_g"])) if admit_lift else "FAIL(%.3f<=%.3f)" % (m["dsr_k"], max(m["dsr_c"], m["dsr_g"])),
             "PASS" if clears else "FAIL(%.3f)" % m["dsr_k"]))
    v = "ADMIT" if (admit_orth and admit_lift and clears) else \
        ("ADMIT-CANDIDATE (orthogonality+DSR-lift real; book DSR %.2f short of 0.90)" % m["dsr_k"] if (admit_orth and admit_lift) else "REJECT")
    print("  >>> %s <<<" % v)
    print()


def main():
    # HONEST PRIMARY: full common history (BTC/ETH from 2017, coins active-that-day).
    # The SOL-gated 2020-08 start is a pessimistic corner (excludes 2017-2020 crypto
    # trend) reported as a sensitivity, not the headline.
    print("\n##### PRIMARY (honest full common history) #####")
    prim = run_wf(40, 20, "2017-09-01", 5, "full-history 2017->2026, gold d-40/20", True)

    print("\n##### SENSITIVITY GRID (all honest OOS) #####")
    print("  variant                                 cryptoSh(DSR) goldSh(DSR)  COMB-Sh(DSR)  maxDD  corr  wG")
    for (ge, gx, cs, nf, lab) in [
        (40, 20, "2020-08-12", 5, "SOL-gated 2020, d-40/20 (pessimistic)"),
        (20, 10, "2017-09-01", 5, "full-hist, gold d-20/10"),
        (100, 40, "2017-09-01", 5, "full-hist, gold d-100/40"),
        (40, 20, "2017-09-01", 3, "full-hist, 3 folds"),
    ]:
        s = run_wf(ge, gx, cs, nf, lab, False)
        print("  %-38s  %+.2f(%.2f)  %+.2f(%.2f)  %+.2f(%.2f)  %4.0f%% %.3f %.0f%%" %
              (lab, s["sh_c"], s["dsr_c"], s["sh_g"], s["dsr_g"], s["sh_k365"], s["dsr_k"],
               s["dd_k"], s["xcorr"], 100 * (1 - s["folds"][0][4])))
    return


if __name__ == "__main__":
    main()
