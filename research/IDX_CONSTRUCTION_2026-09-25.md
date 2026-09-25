# IDX menu 41 - construction changes to the deployed combo book - 2026-09-25 - 12 trials (903..914), cumulative N = 915

Deployed = gap 10 % / trend 5 % / ML ens4 5 % of NAV per trade, 20 slots, cash floor 30 %, Rp 20 M, 2022-01-01 -> 2026-09-16, engine/trades/costs of #168/#177; re-run in this script (same-run pairs only). Halves split at the window's middle date. Rule (pre-registered in `research/idx_construction.py`): IMPROVES if (mDD >= 3 pp shallower and CAGR >= 0.9x) or (CAGR >= +3 pp and mDD <= 1 pp deeper), full window AND both halves, neighbour passing on the full window.

Skipped: #2 gap-fade partial take-profit - menu 29c already has every target losing to the close (-139..-273 bps/trade); a partial TP is a linear mix of a losing target and the close, so it is dominated; idx.feed_bar_1m has 5 sessions (2026-09-21..25) = UNTESTABLE finer than 29c. Book-level overlays and sizing were #177; ML stops #161; ML rule ensemble #175.

| arm | CAGR | Sharpe | mDD | H1 CAGR/mDD | H2 CAGR/mDD | full | H1 | H2 | 2022 | 2023 | 2024 | 2025 | 2026 | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| deployed | 30.8 % | 1.74 | -17.3 % | 17.3 % / -10.5 % | 45.9 % / -17.3 % | ref | ref | ref | +11 % | +13 % | +13 % | +99 % | +21 % | reference |
| trend_d0 | 35.1 % | 1.93 | -17.6 % | 17.6 % / -9.1 % | 55.4 % / -17.6 % | pass | - | pass | +18 % | +10 % | +13 % | +111 % | +27 % | measurement |
| trend_d1 | 32.3 % | 1.81 | -17.6 % | 17.7 % / -9.0 % | 48.8 % / -17.6 % | - | - | - | +12 % | +12 % | +14 % | +100 % | +25 % | measurement |
| trend_ens | 30.0 % | 1.88 | -15.0 % | 14.3 % / -6.0 % | 48.4 % / -15.0 % | - | - | - | +6 % | +14 % | +10 % | +93 % | +31 % | no |
| trend_ens_d1 | 29.5 % | 1.88 | -15.0 % | 13.3 % / -6.9 % | 48.4 % / -15.0 % | - | - | - | +5 % | +13 % | +11 % | +87 % | +34 % | measurement |
| trend_stagger | 33.4 % | 1.94 | -15.6 % | 17.0 % / -8.1 % | 52.6 % / -15.6 % | - | - | pass | +12 % | +11 % | +9 % | +115 % | +27 % | no |
| cap6 | 24.1 % | 1.62 | -12.8 % | 12.5 % / -6.9 % | 37.1 % / -12.8 % | - | - | - | +3 % | +15 % | +9 % | +75 % | +17 % | no |
| cap4 | 20.7 % | 1.56 | -10.5 % | 6.6 % / -6.5 % | 36.8 % / -10.5 % | - | - | - | +3 % | +3 % | +11 % | +68 % | +18 % | no |
| sector3 | 28.9 % | 1.73 | -16.4 % | 12.7 % / -11.1 % | 47.5 % / -16.4 % | - | - | - | +6 % | +6 % | +11 % | +93 % | +31 % | no |
| sector2 | 27.4 % | 1.74 | -14.9 % | 7.3 % / -12.9 % | 51.2 % / -14.9 % | - | - | pass | -2 % | +3 % | +15 % | +90 % | +36 % | no |
| gap_exempt | 30.9 % | 1.70 | -18.1 % | 16.9 % / -10.5 % | 46.9 % / -18.1 % | - | - | - | +11 % | +12 % | +12 % | +102 % | +21 % | no |
| recycle5 | 32.8 % | 1.85 | -16.3 % | 16.9 % / -10.5 % | 51.2 % / -16.3 % | - | - | pass | +11 % | +12 % | +12 % | +106 % | +27 % | no |
| recycle10 | 33.0 % | 1.84 | -17.5 % | 16.9 % / -10.5 % | 51.6 % / -17.5 % | - | - | pass | +11 % | +12 % | +12 % | +114 % | +23 % | no |
| trend_ens_loo0 | 30.7 % | 1.88 | -15.3 % | 15.3 % / -6.3 % | 48.7 % / -15.3 % | - | - | - | +8 % | +14 % | +10 % | +95 % | +30 % | reference |
| trend_ens_loo1 | 30.9 % | 1.91 | -15.1 % | 15.1 % / -5.9 % | 49.2 % / -15.1 % | - | - | pass | +8 % | +13 % | +10 % | +94 % | +32 % | reference |
| trend_ens_loo2 | 30.4 % | 1.86 | -15.3 % | 15.6 % / -6.4 % | 47.5 % / -15.3 % | - | pass | - | +8 % | +14 % | +9 % | +95 % | +29 % | reference |
| trend_ens_loo3 | 30.2 % | 1.86 | -15.4 % | 15.5 % / -6.3 % | 47.3 % / -15.4 % | - | - | - | +8 % | +14 % | +9 % | +93 % | +30 % | reference |

## #1 trend timing: is a confirmation ensemble less fragile to a late fill?

| trend sleeve alone (same engine, floor) | CAGR | Sharpe | mDD |
|---|---|---|---|
| deployed | 8.7 % | 0.92 | -12.6 % |
| trend_d0 | 15.7 % | 1.52 | -8.9 % |
| trend_d1 | 10.7 % | 1.14 | -11.8 % |
| trend_ens | 5.5 % | 1.03 | -7.4 % |
| trend_ens_d1 | 4.3 % | 0.82 | -7.9 % |
| trend_stagger | 9.7 % | 1.16 | -13.2 % |

CAGR lost to a one-day-late fill: plain +5.1 pp (trend alone) / +2.8 pp (whole book); ensemble +1.3 pp / +0.5 pp. Less fragile by the pre-registered test: YES.

Trend replay diagnostic: of the deployed trend simulator's trades, the entry signal is on the day BEFORE the simulator's fill in 100 % of trades; `idx_combo_rupiah.trend_trades` places the combo's trend entry at simulator-fill + 1 day (its comment reads the tuple's first field as the signal day), i.e. the deployed baseline replays trend one session late; `trend_d0` is the on-time replay.

## Verdict (menu 41, study stored)

IMPROVES: none. CANDIDATE: none. Any change to the live book's params is the operator's call.

## Reading (written after the run, study #184)

- **None of the 10 proposal arms clears the pre-registered bar.** The closest are both on the CAGR side and short of +3 pp:
  `recycle5` +2.0 pp CAGR / mDD 1.0 pp shallower (H2 passes, H1 flat because the floor rarely binds before 2024), `recycle10`
  +2.2 pp / -0.2 pp, `trend_stagger` +2.6 pp / 1.7 pp shallower. `cap6`/`cap4` buy 4.5-6.8 pp of drawdown at 0.78x / 0.67x CAGR
  (the same trade-off as shrinking size, worse than cash30). Sector caps cost CAGR without enough drawdown cut. `gap_exempt`
  does nothing (the floor rarely blocks the gap sleeve once the ML pieces are small).
- **#1 trend confirmation ensemble: less fragile, but only because it trades less.** A one-day-late fill costs the trend sleeve
  5.1 pp CAGR (Sharpe 1.52 -> 1.14) and the ensemble 1.3 pp (1.03 -> 0.82), passing the fragility test - but the on-time
  ensemble sleeve earns 5.5 % vs 15.7 % for the plain on-time sleeve. The confirmation drops the fast breakouts that are the
  edge, so it is less fragile at a price larger than the fragility it removes. Not recommended.
- **Baseline finding (not a construction change):** `idx_combo_rupiah.trend_trades` replays every trend trade one session late
  (entry AND exit at simulator fill + 1; verified: 100 % of the simulator's signals sit on the day before its fill). The live
  runner plans after the close and buys the next day = on time. So #168/#177 and this study's `deployed` understate the trend
  sleeve: on-time replay `trend_d0` = 35.1 % / 1.93 / -17.6 % vs 30.8 % / 1.74 / -17.3 % (same run). The engine file is shared
  and was not edited; whoever owns it should fix the `d_in = d_tr[e + 1]` line (it should be `d_tr[e]`, `d_out = d_tr[e + hold]`).
