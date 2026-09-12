# Equity book combos vs DSR 0.90 gate — 2026-07-18

Six-sleeve cross-asset books (BASE4 + 2 equity sleeves) through the expanding
5-fold OOS vol-parity walk-forward (`run_wf`, equity_screen.py engine).
Script: `research/equity_book_combos.py` (runs on VPS from `/tmp/equity/`);
raw: VPS `/tmp/equity/combo_results.json`, `/tmp/equity/combo_out.txt`.
Costs per side: base sleeves 8bps, US 5bps, SGX 15bps. ZERO DB writes.

## Baseline reproduction — OK (exact)

| book | expected | got |
|---|---|---|
| BASE4 (CRYPTO+GOLD+CORN+USDJPY) | Sh 1.176, DSR@20 0.762, mDD ~6.9 | Sh 1.176, DSR@20 0.762, mDD 6.9 |
| BASE4+NVDA (55/20 L) | DSR@20 0.894 | DSR@20 0.894 |

## Combo table (concatenated-OOS)

| combo | days | Sharpe | DSR@20 | @50 | @100 | @488 | maxDD% | max\|corr\| | folds+ |
|---|---|---|---|---|---|---|---|---|---|
| BASE4 (ref) | 1964 | 1.176 | 0.762 | 0.632 | 0.533 | 0.333 | 6.9 | 0.176 | 4/5 |
| BASE4+NVDA (ref) | 1963 | 1.413 | 0.894 | 0.808 | 0.731 | 0.541 | 7.4 | 0.176 | 5/5 |
| 1. +NVDA+AAPL(20/10L) | 1963 | 1.436 | **0.902** | 0.821 | 0.747 | 0.560 | 7.3 | 0.457 | 5/5 |
| 2. +NVDA+XLK(40/20L) | 1963 | 1.513 | **0.929** | 0.863 | 0.799 | 0.627 | 6.1 | 0.754 | 5/5 |
| 3. +NVDA+LQD(40/20L) | 1963 | 1.403 | 0.894 | 0.808 | 0.731 | 0.540 | 5.5 | 0.269 | 5/5 |
| 4. +NVDA+S68.SI(55/20L) | 1912 | 1.620 | **0.950** | 0.898 | 0.845 | 0.692 | 4.7 | 0.194 | 5/5 |
| 5. +NVDA+BN4.SI(20/10L) | 1912 | 1.715 | **0.969** | 0.933 | 0.893 | 0.766 | 7.5 | 0.194 | 5/5 |
| 6. +AAPL+LQD (no NVDA) | 1963 | 1.264 | 0.824 | 0.710 | 0.618 | 0.415 | 5.0 | 0.269 | 5/5 |
| 7. +XLK+LQD (surv-safe) | 1963 | 1.411 | 0.892 | 0.805 | 0.728 | 0.537 | 4.1 | 0.269 | 5/5 |
| 8. probe: #5+LQD (7-sleeve) | 1912 | 1.722 | **0.972** | 0.937 | 0.899 | 0.776 | 5.7 | 0.244 | 5/5 |

All windows 2017-09-07..2026-07-15; SGX combos shrink 1963→1912 common days
(~2.6%, calendar holidays — immaterial). 7-sleeve probe add picked by lowest
max-pairwise-corr addition: LQD 0.244 vs AAPL 0.476 / XLK 0.758 / S68.SI 0.325.

## Verdict

- **Clear 0.90 @20 trials:** 4 of 7 six-sleeve combos (#1 0.902, #2 0.929,
  #4 0.950, #5 0.969) + the 7-sleeve probe (0.972).
- **Best book:** BASE4+NVDA+BN4.SI (#5) — Sharpe 1.715, DSR@20 0.969, 5/5 folds,
  max|corr| 0.194 (BN4.SI adds SGX conglomerate exposure nearly orthogonal to
  everything). Adding LQD (#8) nudges to 0.972 and cuts maxDD 7.5→5.7.
- **Honest multiplicity (@488):** NOTHING clears 0.90. Best is #8 at 0.776,
  #5 at 0.766. At the cumulative equity-screen mining count the book is
  admit-candidate-grade, not certified.
- **Survivorship-safe (#7, no single names):** DSR@20 0.892 — misses the gate
  by 0.008. Lowest maxDD of any combo (4.1%) and honest @488 0.537. The gate
  pass is carried by single-name momentum (NVDA and/or BN4.SI).

## Caveats

- **Survivorship:** NVDA/AAPL/BN4.SI/S68.SI are today's mega-winners picked in
  2026; a 2017 self would not have shortlisted NVDA. #7 is the only combo free
  of this bias and it fails (narrowly). Treat single-name DSRs as upper bounds.
- **Multiplicity:** DSR@20 assumes this session's ~20 book-level configs were
  the only trials; the honest cumulative count for the equity screen is 488
  cells, under which nothing passes. @50-@100 is a defensible middle ground
  (#5 holds 0.933/0.893).
- **Local-ccy:** .SI sleeves are SGD price series traded at 15bps/side; no
  SGDUSD hedge modeled — a USD book carries residual FX exposure.
- **Offline-honest:** vol-parity weights use expanding IS vol only; sleeve
  configs come from the Phase-1 screen best cells (that selection is exactly
  what the 488-trial DSR taxes).
