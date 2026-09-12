#!/usr/bin/env python3
"""6-sleeve cross-asset book combos vs the DSR 0.90 admission gate (2026-07-18).

Reuses the Phase-1 engine (equity_screen.py: sleeve/run_wf/DSR/corr + /tmp/equity
CSV caches). Adds: DSR@488 (honest cumulative mining count), folds-positive,
common-window reporting, and a Yahoo one-shot CSV cache for the two base-book
Yahoo sleeves (ZC=F, JPY=X) so repeat runs fetch nothing.

Baselines that MUST reproduce (tolerance 0.02 DSR) before combos run:
  BASE4              OOS Sharpe 1.176  DSR@20 0.762  maxDD ~6.9
  BASE4+NVDA(55/20L) DSR@20 0.894

Run ON THE VPS from /tmp/equity (needs equity_screen.py alongside):
    cd /tmp/equity && python3 equity_book_combos.py > /tmp/equity/combo_out.txt
Writes /tmp/equity/combo_results.json. READ-ONLY vs the DB.
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from equity_screen import (OUTDIR, BASE_COST, sleeve, db_ohlc, yf_ohlc,
                           load_csv, run_wf, sharpe, deflated_sharpe, maxdd,
                           avg_pairwise_corr, crypto_pool)

N_FOLDS = 5
TRIALS = [20, 50, 100, 488]      # 488 = honest cumulative equity-screen count
BASE_EXPECT = {'oos_sharpe': 1.176, 'dsr20': 0.762}
NVDA_EXPECT = {'dsr20': 0.894}
TOL = 0.02

# candidate sleeves: (csv ticker, entry, exit, long_only, cost_bps per side)
CAND = {
    'NVDA':   ('NVDA',   55, 20, True, 5.0),
    'AAPL':   ('AAPL',   20, 10, True, 5.0),
    'XLK':    ('XLK',    40, 20, True, 5.0),   # best long-only cell (Sharpe .465)
    'LQD':    ('LQD',    40, 20, True, 5.0),
    'S68.SI': ('S68.SI', 55, 20, True, 15.0),
    'BN4.SI': ('BN4.SI', 20, 10, True, 15.0),
}


def yf_cached(tk):
    """Yahoo OHLC with a one-shot /tmp/equity CSV cache (h,l,c)."""
    path = os.path.join(OUTDIR, tk.replace('^', '_').replace('=', '_') + '.csv')
    if os.path.exists(path):
        m = {}
        with open(path) as f:
            next(f)
            for ln in f:
                d, h, l, c = ln.strip().split(',')
                m[d] = (float(h), float(l), float(c))
        return m
    m = yf_ohlc(tk)
    with open(path, 'w') as f:
        f.write('date,high,low,close\n')
        for d in sorted(m):
            f.write('%s,%r,%r,%r\n' % ((d,) + m[d]))
    return m


def wf_metrics_ext(lst):
    """run_wf + DSR@{20,50,100,488} + folds-positive + common-window dates."""
    common, vecs, oos, N, warm = run_wf(lst, N_FOLDS)
    _, mc = avg_pairwise_corr(vecs)
    step = (N - warm) // N_FOLDS
    folds, idx = [], 0
    for k in range(N_FOLDS):              # identical segmentation to run_wf
        tr_end = warm + k * step
        te_end = warm + (k + 1) * step if k < N_FOLDS - 1 else N
        if te_end - tr_end < 5:
            continue
        ln = te_end - tr_end
        folds.append(sum(oos[idx:idx + ln]))
        idx += ln
    out = {'common_days': N,
           'window': '%s..%s' % (common[0], common[-1]),
           'oos_sharpe': round(sharpe(oos, 252), 3),
           'maxdd': round(maxdd(oos), 1),
           'max_abs_corr': round(mc, 3),
           'folds_pos': '%d/%d' % (sum(1 for x in folds if x > 0), len(folds))}
    for t in TRIALS:
        out['dsr%d' % t] = round(deflated_sharpe(oos, t), 3)
    return out


def pair_max_corr(existing, cand):
    """max |corr| the candidate sleeve adds vs each existing sleeve."""
    common = sorted(set.intersection(*[set(s) for s in existing + [cand]]))
    vecs = [[s.get(d, 0.0) for d in common] for s in existing + [cand]]
    mx = 0.0
    for j in range(len(existing)):
        _, m = avg_pairwise_corr([vecs[j], vecs[-1]])
        if not math.isnan(m):
            mx = max(mx, m)
    return mx


def main():
    # --- base-book sleeves (Phase-1 parity: all 8bps) ---
    base_named = [('CRYPTO', crypto_pool()),
                  ('GOLD', sleeve(db_ohlc('XAUUSD'), 40, 20, True, BASE_COST)[0]),
                  ('CORN', sleeve(yf_cached('ZC=F'), 55, 20, True, BASE_COST)[0]),
                  ('USDJPY', sleeve(yf_cached('JPY=X'), 55, 20, True, BASE_COST)[0])]
    base = [s for _, s in base_named]
    cand = {k: sleeve(load_csv(v[0]), v[1], v[2], v[3], v[4])[0]
            for k, v in CAND.items()}

    results = {}

    def run(name, lst):
        results[name] = wf_metrics_ext(lst)
        v = results[name]
        print('%-24s %5d  %-22s Sh %6.3f  DSR20/50/100/488 %.3f/%.3f/%.3f/%.3f'
              '  mDD %4.1f  mxCor %.3f  folds+ %s'
              % (name, v['common_days'], v['window'], v['oos_sharpe'],
                 v['dsr20'], v['dsr50'], v['dsr100'], v['dsr488'],
                 v['maxdd'], v['max_abs_corr'], v['folds_pos']))
        return v

    print('=== BASELINE REPRODUCTION ===')
    b = run('BASE4', base)
    bn = run('BASE4+NVDA', base + [cand['NVDA']])
    ok = (abs(b['dsr20'] - BASE_EXPECT['dsr20']) <= TOL
          and abs(bn['dsr20'] - NVDA_EXPECT['dsr20']) <= TOL)
    print('baseline check: %s (expect BASE4 dsr20 %.3f got %.3f; '
          'BASE4+NVDA dsr20 %.3f got %.3f; tol %.2f)'
          % ('OK' if ok else 'DISCREPANCY', BASE_EXPECT['dsr20'], b['dsr20'],
             NVDA_EXPECT['dsr20'], bn['dsr20'], TOL))
    if not ok:
        json.dump(results, open(os.path.join(OUTDIR, 'combo_results.json'), 'w'),
                  indent=1)
        sys.exit(2)

    print('')
    print('=== 6-SLEEVE COMBOS ===')
    members = {
        'BASE4+NVDA+AAPL': ['NVDA', 'AAPL'], 'BASE4+NVDA+XLK': ['NVDA', 'XLK'],
        'BASE4+NVDA+LQD': ['NVDA', 'LQD'], 'BASE4+NVDA+S68.SI': ['NVDA', 'S68.SI'],
        'BASE4+NVDA+BN4.SI': ['NVDA', 'BN4.SI'],
        'BASE4+AAPL+LQD': ['AAPL', 'LQD'], 'BASE4+XLK+LQD': ['XLK', 'LQD'],
    }
    combos = {n: base + [cand[m] for m in ms] for n, ms in members.items()}
    for name, lst in combos.items():
        run(name, lst)

    passers = [n for n in combos if results[n]['dsr20'] >= 0.90]
    print('')
    print('6-sleeve passers @DSR20>=0.90: %s' % (passers or 'NONE'))

    if passers:
        best = max(passers, key=lambda n: results[n]['dsr20'])
        used = set(members[best])
        rem = [k for k in CAND if k not in used]
        adds = {k: round(pair_max_corr(base + [cand[m] for m in members[best]],
                                       cand[k]), 3) for k in rem}
        pick = min(adds, key=adds.get)
        print('7-sleeve probe: best=%s, corr-additions=%s -> add %s'
              % (best, adds, pick))
        run(best + '+' + pick, combos[best] + [cand[pick]])
        results['_probe'] = {'best': best, 'corr_additions': adds, 'added': pick}

    json.dump(results, open(os.path.join(OUTDIR, 'combo_results.json'), 'w'),
              indent=1)
    print('')
    print('results -> %s/combo_results.json' % OUTDIR)


if __name__ == '__main__':
    main()
