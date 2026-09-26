# IDX menu 41 - construction changes to the deployed combo book - 2026-09-26 - 12 trials (903..914), cumulative N = 915

Deployed = gap 10 % / trend 5 % / ML ens4 5 % of NAV per trade, 20 slots, cash floor 30 %, Rp 20 M, 2022-01-01 -> 2026-09-16, engine/trades/costs of #168/#177; re-run in this script (same-run pairs only). Halves split at the window's middle date. Rule (pre-registered in `research/idx_construction.py`): IMPROVES if (mDD >= 3 pp shallower and CAGR >= 0.9x) or (CAGR >= +3 pp and mDD <= 1 pp deeper), full window AND both halves, neighbour passing on the full window.

Skipped: #2 gap-fade partial take-profit - menu 29c already has every target losing to the close (-139..-273 bps/trade); a partial TP is a linear mix of a losing target and the close, so it is dominated; idx.feed_bar_1m has 5 sessions (2026-09-21..25) = UNTESTABLE finer than 29c. Book-level overlays and sizing were #177; ML stops #161; ML rule ensemble #175.

| arm | CAGR | Sharpe | mDD | H1 CAGR/mDD | H2 CAGR/mDD | full | H1 | H2 | 2022 | 2023 | 2024 | 2025 | 2026 | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| deployed | 32.9 % | 1.77 | -16.9 % | 10.3 % / -13.3 % | 60.3 % / -16.9 % | ref | ref | ref | +5 % | +6 % | +16 % | +124 % | +23 % | reference |
| trend_d0 | 32.9 % | 1.77 | -16.9 % | 10.3 % / -13.3 % | 60.3 % / -16.9 % | - | - | - | +5 % | +6 % | +16 % | +124 % | +23 % | measurement |
| trend_d1 | 28.8 % | 1.64 | -16.4 % | 9.0 % / -13.1 % | 52.3 % / -16.4 % | - | - | - | -1 % | +9 % | +13 % | +106 % | +23 % | measurement |
| trend_ens | 30.8 % | 1.87 | -15.8 % | 11.0 % / -9.1 % | 54.5 % / -15.8 % | - | pass | - | +5 % | +8 % | +11 % | +107 % | +30 % | no |
| trend_ens_d1 | 29.8 % | 1.84 | -16.0 % | 9.5 % / -10.3 % | 54.3 % / -16.0 % | - | - | - | +3 % | +7 % | +13 % | +101 % | +32 % | measurement |
| trend_stagger | 29.6 % | 1.71 | -16.7 % | 9.4 % / -12.6 % | 53.9 % / -16.7 % | - | - | - | +2 % | +7 % | +9 % | +119 % | +22 % | no |
| cap6 | 30.7 % | 1.90 | -12.1 % | 9.8 % / -8.1 % | 55.7 % / -12.1 % | pass | pass | pass | +7 % | +7 % | +17 % | +99 % | +25 % | no: neighbour fails |
| cap4 | 29.1 % | 2.00 | -9.7 % | 9.5 % / -7.8 % | 52.2 % / -9.7 % | - | pass | - | +8 % | +5 % | +18 % | +77 % | +33 % | no |
| sector3 | 32.3 % | 1.83 | -17.0 % | 10.8 % / -11.8 % | 57.9 % / -17.0 % | - | - | - | +4 % | +6 % | +15 % | +127 % | +22 % | no |
| sector2 | 33.0 % | 1.96 | -14.2 % | 8.1 % / -10.2 % | 63.7 % / -14.2 % | - | - | pass | +2 % | +4 % | +17 % | +115 % | +38 % | no |
| gap_exempt | 32.4 % | 1.76 | -17.9 % | 10.3 % / -13.3 % | 59.0 % / -17.9 % | - | - | - | +5 % | +6 % | +17 % | +120 % | +23 % | no |
| recycle5 | 33.3 % | 1.79 | -16.3 % | 9.6 % / -13.3 % | 62.3 % / -16.3 % | - | - | - | +3 % | +6 % | +17 % | +132 % | +22 % | no |
| recycle10 | 34.2 % | 1.82 | -15.9 % | 10.3 % / -13.3 % | 63.3 % / -15.9 % | - | - | pass | +4 % | +6 % | +16 % | +132 % | +24 % | no |
| trend_ens_loo0 | 31.4 % | 1.87 | -15.6 % | 11.4 % / -9.6 % | 55.5 % / -15.6 % | - | pass | - | +7 % | +8 % | +11 % | +111 % | +30 % | reference |
| trend_ens_loo1 | 31.5 % | 1.90 | -15.6 % | 12.0 % / -9.3 % | 54.7 % / -15.6 % | - | pass | - | +7 % | +8 % | +12 % | +108 % | +30 % | reference |
| trend_ens_loo2 | 30.9 % | 1.84 | -15.8 % | 11.6 % / -9.9 % | 53.8 % / -15.8 % | - | pass | - | +7 % | +7 % | +10 % | +109 % | +29 % | reference |
| trend_ens_loo3 | 30.8 % | 1.86 | -15.8 % | 12.0 % / -9.8 % | 53.3 % / -15.8 % | - | pass | - | +7 % | +8 % | +11 % | +105 % | +30 % | reference |

## #1 trend timing: is a confirmation ensemble less fragile to a late fill?

| trend sleeve alone (same engine, floor) | CAGR | Sharpe | mDD |
|---|---|---|---|
| deployed | 12.7 % | 1.19 | -11.6 % |
| trend_d0 | 12.7 % | 1.19 | -11.6 % |
| trend_d1 | 7.4 % | 0.79 | -15.5 % |
| trend_ens | 5.7 % | 0.98 | -12.5 % |
| trend_ens_d1 | 4.3 % | 0.76 | -11.6 % |
| trend_stagger | 8.0 % | 0.92 | -16.2 % |

CAGR lost to a one-day-late fill: plain +5.2 pp (trend alone) / +4.1 pp (whole book); ensemble +1.4 pp / +1.0 pp. Less fragile by the pre-registered test: YES.

Trend replay diagnostic: of the deployed trend simulator's trades, the entry signal is on the day BEFORE the simulator's fill in 100 % of trades; `idx_combo_rupiah.trend_trades` places the combo's trend entry at simulator-fill + 1 day (its comment reads the tuple's first field as the signal day), i.e. the deployed baseline replays trend one session late; `trend_d0` is the on-time replay.

## Verdict (menu 41, study stored)

IMPROVES: none. CANDIDATE: none. Any change to the live book's params is the operator's call.
