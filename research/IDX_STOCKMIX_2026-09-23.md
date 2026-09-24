# IDX menu 32 — stock-only: the value / trend weight surface — 2026-09-23 — 18 trials (9 weights × 2 panels), cumulative N = 603

Operator ruled out the allocation layer (menu 31): equities only. Menu 21 B found value + trend ROBUST (4/5 weights pass the money rule, 50/50 passes 2/2 halves). Live capital is not at that weight: Rp 20 M value (IPOT) + Rp 10 M trend (Stockbit) ≈ 67/33. This menu measures the whole surface so the choice is made on its shape, not its peak. Script `research/idx_stockmix.py`.

Monthly rebalance, 0.30 % switch cost. Trend sleeve in two panels: plain trail10, and with the **regime gate actually deployed** (`regime_filter = on`, 2026-09-22). Window: the value book's, 2020-05 → 2026-09.

**Pre-registered bar:** reference = 67/33 (live today); BETTER only if Sharpe ≥ reference + 0.15 AND drawdown no deeper; ROBUST only if that also holds in BOTH halves. A flat surface is the finding; a sharp peak would be a warning.

## Full window

| value/trend | plain: CAGR / Sharpe / mDD | **gated: CAGR / Sharpe / mDD** |
|---|---|---|
| 100/0 | +21.4 % / 1.08 / −17.2 % | +21.4 % / 1.08 / −17.2 % |
| 80/20 | +23.6 % / 1.25 / −16.3 % | +24.1 % / 1.32 / −15.9 % |
| **67/33 (live)** | +24.9 % / 1.32 / −15.9 % | **+25.7 % / 1.45 / −15.2 %** |
| 60/40 | +25.5 % / 1.35 / −15.7 % | +26.6 % / 1.50 / −15.2 % |
| 50/50 | +26.4 % / 1.36 / −16.0 % | +27.7 % / 1.54 / −15.2 % |
| 40/60 | +27.2 % / 1.35 / −17.6 % | +28.7 % / **1.55** / −15.4 % |
| 33/67 | +27.7 % / 1.33 / −18.7 % | +29.4 % / 1.53 / −15.7 % |
| 20/80 | +28.6 % / 1.28 / −20.7 % | +30.7 % / 1.47 / −16.1 % |
| 0/100 | +29.7 % / 1.18 / −23.8 % | +32.3 % / 1.35 / −16.8 % |

Bar (gated): 1.45 + 0.15 = 1.60. Nothing reaches it in the full window.

## Halves (gated panel)

| value/trend | H1 2020-05 → 2023-06 | H2 2023-07 → 2026-09 |
|---|---|---|
| 100/0 | 1.23 / −14.2 % / +27.6 % | 0.90 / −17.2 % / +15.7 % |
| 67/33 (ref) | 1.62 / −11.6 % / +30.4 % | 1.27 / −15.2 % / +21.3 % |
| 50/50 | **1.78 / −10.4 % / +31.7 %** BETTER | 1.31 / −15.2 % / +23.9 % tested |
| 40/60 | 1.84 / −9.7 % / +32.3 % BETTER | 1.30 / −15.4 % / +25.4 % |
| 33/67 | **1.86** / −9.2 % / +32.7 % BETTER | 1.27 / −15.7 % / +26.3 % |
| 20/80 | 1.84 / −8.8 % / +33.4 % BETTER | 1.22 / −16.1 % / +28.0 % |
| 0/100 | 1.72 / −9.7 % / +34.2 % | 1.13 / −16.8 % / +30.4 % |

## Verdict

**0 of 18 ROBUST** (50/50 clears the bar in H1 only). Findings that do hold:

- **The surface is flat:** gated 50/50 → 33/67 all sit at Sharpe 1.53–1.55. The peak moves between halves (H1 33/67, H2 50/50) — it is noise; do not chase it.
- **Either sleeve alone is worse than any blend, in every window** (value-only has the lowest Sharpe everywhere; trend-only the deepest drawdown). The costly mistake is concentration, and 67/33 is not it.
- **Direction 67/33 → 50/50 is positive 3/3 windows** (1.45 → 1.54; 1.62 → 1.78; 1.27 → 1.31) but the size (+0.09 Sharpe, +2 pt CAGR, mDD unchanged) is under the bar.
- **The regime gate is worth more than any weight change:** at fixed 67/33 it adds +0.13 Sharpe (1.32 → 1.45) versus +0.09 for the best re-weighting. The largest stock-only lever was pulled on 2026-09-22.
- **H2 is weaker across the board** (value-only 1.23 → 0.90; best blend 1.86 → 1.31). Forward expectations belong at H2's level, not the average.

Operator's decision (2026-09-23): stay at Rp 20 M investing / Rp 10 M trading; add to trading only once its track record reproduces the backtested profile (`idx track`). Recorded as the standing rule.

Limits: 6.4 years; value NAV is a backtest; both panels share the same value sleeve; no placebo/neighbour battery (nothing reached the bar).
