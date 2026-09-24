# IDX menu 31 — the allocation layer on the DESK'S book (gold in rupiah) — 2026-09-23 — 7 trials, cumulative N = 585

Menu 21 family D tested the allocation layer with IHSG as the equity sleeve (EW3 Sharpe 1.14 vs IHSG 0.53, 2006–26). The desk does not hold IHSG; it holds the value book (Sharpe 1.06) and the trend book (1.31). Diversification pays least when the sleeve it dilutes is already good, so that result does not carry over. Untested until now. Script `research/idx_allocbook.py`.

Diversifier: **gold in rupiah only** (`idx.macro` gold × usdidr; the S&P is not in the local macro store) plus cash at BI − 1.5 pts. That is also the implementable version for an Indonesian retail investor (Antam / Pegadaian / digital gold). Monthly rebalance, 0.30 % switch cost on the drift.

**Pre-registered bar:** reference = value 50 % + trend 50 % (the ROBUST combination of menu 21 B); BETTER only if Sharpe ≥ reference + 0.15 AND drawdown no deeper. Grid fixed before the run; the peak is not the recommendation.
**Window:** the value book's, 2020-05 → 2026-09 (77 months, 6.4 years). SHORT — family D had 20 years and 2008; this cannot.

| arm | CAGR | vol | Sharpe | mDD | verdict |
|---|---|---|---|---|---|
| IHSG | +5.2 % | 15 % | 0.41 | −34.7 % | context |
| value only | +21.4 % | 20 % | 1.08 | −17.2 % | context |
| trend only | +29.7 % | 25 % | 1.18 | −23.8 % | context |
| gold IDR only | +19.0 % | 17 % | 1.14 | −17.7 % | context (20-yr Sharpe is 0.77 — this window flatters gold) |
| **book 50/50 (reference)** | **+26.4 %** | 19 % | **1.36** | **−16.0 %** | reference |
| book 90 / gold 10 | +25.9 % | 17 % | 1.46 | −16.0 % | tested (Sharpe short of 1.51) |
| book 80 / gold 20 | +25.4 % | 15 % | 1.56 | −16.1 % | tested: mDD 0.1 pt deeper |
| book 70 / gold 30 | +24.8 % | 14 % | 1.65 | −16.2 % | tested: mDD 0.2 pt deeper |
| book 60 / gold 40 | +24.2 % | 13 % | 1.72 | −16.4 % | tested: mDD 0.4 pt deeper |
| book 50 / gold 50 | +23.5 % | 13 % | 1.74 | −16.5 % | tested: mDD 0.5 pt deeper |
| EW3 value / trend / gold | +24.6 % | 14 % | 1.68 | −16.3 % | tested: mDD 0.3 pt deeper |

## Robustness: the same grid in each half (diversification, or gold's run?)

| half | gold alone | book 50/50 | 80/20 | 70/30 | 60/40 | 50/50 gold |
|---|---|---|---|---|---|---|
| H1 2020-05 → 2023-07 | Sharpe 0.35, +3.9 %/yr (flat) | 1.75 / −10.6 % / +33.1 % | 1.90 / −7.2 % / +27.3 % | 1.96 / −5.4 % / +24.4 % | 1.98 / **−4.2 %** / +21.4 % | 1.91 / −3.9 % / +18.5 % |
| H2 2023-07 → 2026-09 | Sharpe 1.78, +35.9 %/yr (boom) | 1.02 / −16.0 % / +20.1 % | 1.31 / −16.1 % / +23.6 % | 1.46 / −16.2 % / +25.3 % | 1.61 / −16.4 % / +27.0 % | 1.72 / −16.5 % / +28.6 % |

Reading: in H1 gold earned almost nothing and STILL raised Sharpe 1.75 → 1.98 and halved the drawdown — pure diversification, not gold's luck. In H2 it added return as well. The Sharpe gain is monotone in the gold weight and present in 2/2 halves through two different mechanisms.

## Verdict

**0 of 6 BETTER by the letter** — every gold arm clears the Sharpe bar (1.56–1.74 vs 1.51) and misses the drawdown bar by 0.1–0.5 pt. The bar was set before the run and is not loosened after reading. Status: **PARTIAL / candidate for the full battery** (placebo, neighbours, costs ×1.5, DSR). Practical reading if it survives: 20–30 % gold, rebalanced monthly, trades ~1.6 pt of CAGR for a 21 % higher Sharpe and a third less volatility.

**Parked by the operator (2026-09-23): equities only, no gold.** Recorded so the next person does not re-run it blind.

Limits: 6.4 years; value NAV is a backtest, not live returns; 2020–26 is the trend rule's best block in 22 years; one diversifier; no battery.
