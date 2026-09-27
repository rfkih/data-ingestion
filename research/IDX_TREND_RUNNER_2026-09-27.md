# IDX menu TR-3 — runner exit and minimum lot for the trend sleeve — 2026-09-27

Script `research/idx_trend_runner.py` (pre-registered in its docstring); same machinery as TR-2 (PIT panels, K-10 run_book,
rupiah replay Rp 20 m / 5 % / lots / offer-bid / band realism). REF reproduces TR-2's REF exactly (sanity). **2 trials;
cumulative N 1077 -> 1079. Result: 0 of 2 BETTER.**

Diagnostic first (no trial): of ANTM / BRIS / PANI / AMMN / HRTA the deployed sleeve bought PANI once (2024-08-22 -> 10-07, +93 %)
and HRTA once (2025-08-08 -> 08-21, -13 %). ANTM, BRIS, AMMN are BLUE and outside the `small` universe by design (the LIQ-wide
trend tested worse: 19.1 %/0.92/-36 % vs 29.5 %/1.31/-30 %, IDX_BEYOND).

| arm | K-10 sim CAGR / Sharpe / mDD | rupiah book CAGR / Sharpe / mDD | halves | x2 cost Sharpe | trades | five names | verdict |
|---|---|---|---|---|---|---|---|
| REF deployed (trail 10 %) | 31.1 % / 1.42 / -18 % | 9.3 % / 0.90 / -18 % | -1.0 % / +22 % | 0.65 | 275 | PANI +93 %, HRTA -13 % | reference |
| T5 runner (half at 10 %, half at 25 %) | 12.8 % / 1.01 / -20 % | 1.8 % / 0.35 / -10 % | -0.8 % / +5 % | 0.26 | 58 | none | no |
| T6 minimum one lot up to 10 % NAV | 31.1 % / 1.42 / -18 % | 9.3 % / 0.90 / -19 % | -0.9 % / +22 % | 0.65 | 276 (1 min-lot) | same as REF | no (halves) |

Reading: the runner keeps a K-10 slot busy with a half position for weeks, so the book takes a fifth of the trades and misses
the next breakouts - the same failure as TR-2's full 25 % trail, halved. The lot constraint bound once in the window (one extra
trade): the expensive-lot leak is real for PANI/AMMN in principle but immaterial here. **The deployed sleeve stays as it is.**
Multibagger catching is closed on this data: the sleeve's exits and universe are at their frontier.
