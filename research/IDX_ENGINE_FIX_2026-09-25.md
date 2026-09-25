# IDX engine fix - trend replay timing + point-in-time board - 2026-09-25

Measurement corrections (0 trials) + one confirmation trial (R1), cumulative N 915 -> 916. Script `research/idx_engine_fix.py`. Deployed book: gap 10 % / trend 5 % / ML ens4 5 % of NAV per trade, 20 slots, Rp 20 M, cash floor 30 %, 2022-01-01 -> 2026-09-16, the #184 engine (= #177 + ens4 pieces). Cells CAGR / Sharpe / mDD.

Study #192 (`engine_fix`). Cumulative N 915 -> 916: the caller quoted 895 -> 896, but the idx.study ledger's highest count before
this run is 915 (#184 construction, ids 903..914), so the one R1 trial is recorded as 916 (the params row carries both numbers).

## Findings

1. **Bug 1 (trend replay one session late) is worth +4.3 pp CAGR / +0.19 Sharpe on the combined book** (30.8 -> 35.1 %). The trend
   sleeve alone goes 8.7 % / 0.92 -> 15.7 % / 1.52: the deployed trend rule was being scored with every entry AND exit one close late.
   (#184's `trend_d0` arm, which re-derived the fill day independently, already showed 35.1 %; it matches (b) exactly.)
2. **Bug 2 (current-board look-ahead) costs -2.9 pp CAGR / -0.16 Sharpe** (30.8 -> 27.8 %); trend alone 8.7 -> 5.4 %. Only the trend
   sleeve reads `idx_swing2.panels`: gap-fade (`idx_daytrade`) already used the board on the day, and the ML panel
   (`idx/ml/daily.build_panel`) has no board filter at all, the same as the live runner (`combo_book.ml_scores`), so the ML cache
   (`tmp/ml_strategy_cache.pkl`) is not affected and was not rebuilt. 22 of 672 ML ens4 rule-trades were in names off the main
   boards on the day (see below). That is a rule question for the operator; it is not look-ahead.
3. **New official baseline (d): 33.8 % CAGR / 1.83 Sharpe / -17.9 % mDD** (Rp 20 M -> Rp 78.5 M), per year +5 / +15 / +15 / +113 / +26 %.
   Versus the old engine: +3.0 pp CAGR, +0.09 Sharpe, mDD 0.6 pp deeper. H1 (2022-01..2024-05) is weaker (14.5 % vs 17.3 %) and H2 stronger.
   2025 still carries the book (+113 %). The published #168 figure in combo_book.py's docstring (39.8 % / 1.86 / -21.5 %, single-rule
   ML, no floor) is a different configuration and was not re-run here.
4. **R1 (foreign-flow trend gate) is NOT confirmed on the corrected engine.** Trend sleeve alone: Sharpe 1.19 -> 1.34 and mDD -11.6 ->
   -8.2 %, but CAGR 12.7 -> 11.6 %, and half 2 fails the pre-registered rule (CAGR 15.3 % < 0.9 x 18.6 %). Placebo pct 99, DSR 0.35.
   0/4 neighbours pass (10 d: 0.85 Sharpe, 40 d: 0.97). On the combined book it reads well (33.8/1.83/-17.9 -> 36.2/2.03/-15.8), but the
   gate was registered on the sleeve rule, and the 10 d/40 d neighbours give the combined book nothing (32.8 % / 33.8 %). It stays
   FRAGILE, as #188 logged it. Do not move it to the live gate.

## Diffs (shared engine only; frozen study scripts untouched)

- `research/idx_combo_rupiah.py:58-92` `trend_trades(dsn, dates, *, cache=None, board=None, legacy_shift=False)`: the mapping is now
  `d_tr[e], d_tr[e + hold]` (e = fill day), with an end-of-panel guard. The comment is corrected. `legacy_shift=True` reproduces the old
  one-day-late mapping.
- `research/idx_swing2.py:91` `load()` also selects `s.remarks`. `:106-155` adds `IDX_BOARD_MODE` (`pit` by default, `current` = old
  filter), `board_digit()` and `pit_board_mask()` (#189's `pit_board` logic), and `panels(bars, listing, board=None)`. In pit mode panels
  keeps every code and adds `P["board_ok"]`. `:177-178` `build()` ANDs `board_ok` into LIQ per day, so BLUE/BASKET/ENERGY/`small`
  inherit it. No columns are dropped.
- `research/idx_exit.py:91-106` `load_all(dsn, cache=None, board=None)` builds under the chosen mode and **refuses a cache written
  under the other mode**. An old cache has no `board_ok` and counts as `current`. Scripts that default IDX_EXIT_CACHE to
  tmp/exit_cache.pkl (alloc_frontier, construction, foreign_gate, ...) now stop with a clear error unless IDX_BOARD_MODE=current,
  so the stale cache can no longer silently bypass the fix. New cache: `tmp/exit_cache_pit.pkl`. `tmp/exit_cache.pkl` is kept.
- New: `research/idx_engine_fix.py` (this report). Its attribution engine is asserted equal to `idx_construction.engine` on (a) and (d).
- Replicas of the bug-1 mapping in frozen scripts (not edited): `idx_foreign_gate.py:215-217` (`TrendSim.trades`, the R1/R2 re-sims).
  Every other user of `E.run_book` consumes its daily return series or its own event loop, not a date remap (`idx_sleeper.py:94` is
  its own event loop, not affected). `idx_construction.trend_signals` already treats tuple e as the fill day (s = e - 1), which is correct.
- Reproducing an old report exactly now needs IDX_BOARD_MODE=current with tmp/exit_cache.pkl AND `legacy_shift=True`. Frozen scripts
  call `CR.trend_trades(d, dates)` and so get the bug-1-fixed trades if re-run.

## Past studies whose headline numbers move

- Bug 1 + bug 2 (they consume `CR.trend_trades` / the combo trend list): #166/#167/#168 combo_rupiah (+ gapsize/trendsize),
  #177 alloc_frontier (the deployed sizing and every overlay/frontier book), #181 combo_plus, #184 construction (its 'deployed'
  reference; the trend_d0/d1 arms were timed correctly), #185 corp_actions, #187 fund_surprise, #188 foreign_gate (trend sleeve,
  R1/R2 re-sims, combined book), #190 calendar, and the unrecorded `idx_rl_alloc.py` (no study row found).
- Bug 2 only (they build universes with `idx_swing2.panels` / `idx_exit.load_all` and use run_book's own return series): every
  trend-book and swing study, including idx_swing2, idx_trend/idx_trend2 (menus 6-7, the trend book's rule), idx_exit/idx_exit2,
  idx_beyond (regime gate), idx_regime_validate, idx_robustness_scorecard, idx_ml_trend, idx_ml_sleeves (#156/157), idx_breakout_filter
  (#180), idx_allocbook, idx_avgdown, idx_range, idx_sleeper(_long), idx_smallcap_*, idx_stockmix, idx_support, idx_sideways_exploit,
  idx_accum*, idx_bandar*, idx_breakout_accum/stats, idx_ml_overlay. #189 measured the size on the trend book: about -2.4 pp CAGR and
  -0.1 Sharpe on 2022+.
- Not affected: gap-fade studies (board on the day already), the ML prediction and ML-strategy studies built on the board-agnostic ML
  panel (`idx_ml_*` using IDX_ML_CACHE), and #189 survivorship itself.

## The four variants (same run)

| variant | trend trades | CAGR | Sharpe | mDD | final NAV | H1 CAGR / mDD | H2 CAGR / mDD | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| (a) old engine | 266 | 30.8 % | 1.74 | -17.3 % | Rp 70.5 M | 17.3 % / -10.5 % | 45.9 % / -17.3 % | +11 % | +13 % | +13 % | +99 % | +21 % |
| (b) bug 1 fixed only | 266 | 35.1 % | 1.93 | -17.6 % | Rp 82.2 M | 17.6 % / -9.1 % | 55.4 % / -17.6 % | +18 % | +10 % | +13 % | +111 % | +27 % |
| (c) bug 2 fixed only | 282 | 27.8 % | 1.58 | -18.4 % | Rp 63.4 M | 12.0 % / -11.7 % | 46.1 % / -18.4 % | -0 % | +16 % | +10 % | +95 % | +23 % |
| (d) both fixed = new baseline | 282 | 33.8 % | 1.83 | -17.9 % | Rp 78.5 M | 14.5 % / -10.5 % | 56.4 % / -17.9 % | +5 % | +15 % | +15 % | +113 % | +26 % |

(a) reproduces #184's 'deployed' (30.8 % / 1.74 / -17.3 %): 30.8 % / 1.74 / -17.3 %.

## Per sleeve

Realised P&L inside the combined book (Rp M, trades, win rate; open = unrealised at the end) and each sleeve alone on the same engine and floor.

| variant | gap P&L | trend P&L | ML P&L | trend alone | gap alone | ML alone |
|---|---|---|---|---|---|---|
| (a) old engine | +23.4 M (165, 48 %, open +0.0) | +11.7 M (257, 37 %, open +0.0) | +15.5 M (541, 54 %, open +0.0) | 8.7 % / 0.92 / -12.6 % | 12.8 % / 1.39 / -4.3 % | 9.8 % / 1.27 / -11.6 % |
| (b) bug 1 fixed only | +24.6 M (176, 47 %, open +0.0) | +21.7 M (255, 41 %, open +0.0) | +15.9 M (553, 55 %, open +0.0) | 15.7 % / 1.52 / -8.9 % | 12.8 % / 1.39 / -4.3 % | 9.8 % / 1.27 / -11.6 % |
| (c) bug 2 fixed only | +20.1 M (168, 48 %, open +0.0) | +8.5 M (272, 37 %, open +0.0) | +14.8 M (531, 54 %, open +0.0) | 5.4 % / 0.58 / -17.8 % | 12.8 % / 1.39 / -4.3 % | 9.8 % / 1.27 / -11.6 % |
| (d) both fixed = new baseline | +24.4 M (179, 47 %, open +0.0) | +18.2 M (271, 41 %, open +0.0) | +16.0 M (547, 54 %, open +0.0) | 12.7 % / 1.19 / -11.6 % | 12.8 % / 1.39 / -4.3 % | 9.8 % / 1.27 / -11.6 % |

Deltas vs (a), combined book: (b) bug 1 fixed only: CAGR +4.3 pp, Sharpe +0.19, mDD -0.3 pp; sleeve P&L gap +1.2 M, trend +10.0 M, ML +0.4 M; (c) bug 2 fixed only: CAGR -2.9 pp, Sharpe -0.16, mDD -1.2 pp; sleeve P&L gap -3.3 M, trend -3.1 M, ML -0.7 M; (d) both fixed = new baseline: CAGR +3.0 pp, Sharpe +0.09, mDD -0.6 pp; sleeve P&L gap +1.0 M, trend +6.5 M, ML +0.5 M.

Trend P&L by year (Rp M): (a) old engine: 22 +2.0 23 +0.2 24 -0.6 25 +12.3 26 -2.3; (b) bug 1 fixed only: 22 +3.5 23 -0.3 24 +0.4 25 +17.4 26 +0.6; (c) bug 2 fixed only: 22 -0.1 23 +0.7 24 -0.9 25 +11.9 26 -3.0; (d) both fixed = new baseline: 22 +1.0 23 +0.6 24 -0.2 25 +16.4 26 +0.3.

ML sleeve and the board: 22 of 672 ML ens4 rule-trades were entered while the name was NOT on Utama/Pengembangan that day (ARKO, BNBR, CSMI, CUAN, KARW, KSIX, NICL, SRAJ). The ML universe is board-agnostic in research AND in the live runner (combo_book.ml_scores), so this is not look-ahead and was not changed; restricting ML to the main boards would be a rule change (operator's call).

## R1 confirmation on the corrected engine (1 trial)

R1 = market-wide 20-day net foreign flow < 0 -> no new trend entry, INSTEAD of IHSG < MA200 (#188). Trend sleeve alone on the engine, halves split at the median ungated entry (2024-01-16); 200 circular-shift placebos of the same mask.

| book | trades | full | half 1 | half 2 |
|---|---|---|---|---|
| trend, IHSG gate (baseline d) | 282 | 12.7 % / 1.19 / -11.6 % | 5.5 % / 0.60 / -8.3 % | 18.6 % / 1.62 / -8.9 % |
| trend, R1 gate | 215 | 11.6 % / 1.34 / -8.2 % | 7.1 % / 0.87 / -6.9 % | 15.3 % / 1.67 / -8.2 % |
| combined book, baseline d | - | 33.8 % / 1.83 / -17.9 % | 14.5 % / 1.25 / -10.5 % | 56.4 % / 2.27 / -17.9 % |
| combined book, R1 | - | 36.2 % / 2.03 / -15.8 % | 17.1 % / 1.58 / -9.0 % | 58.8 % / 2.43 / -15.8 % |

Halves 1/2 (rule: Sharpe up, mDD not deeper, CAGR >= 0.9x); placebo pct 99 (median 0.55, p95 1.06); DSR @ N 916 = 0.35. Verdict: **NOT confirmed**.

Neighbours (counted in #188, not here):

| neighbour (kind, window, thr) | trades | trend alone | passes vs baseline | combined book |
|---|---|---|---|---|
| ('mkt_instead', 10, 0.0) | 242 | 7.8 % / 0.85 / -10.1 % | no | 32.8 % / 1.83 / -17.0 % |
| ('mkt_instead', 40, 0.0) | 206 | 8.2 % / 0.97 / -9.9 % | no | 33.8 % / 1.92 / -16.2 % |
| ('mkt_instead', 20, -0.02) | 282 | 15.4 % / 1.35 / -12.2 % | no | 40.6 % / 2.13 / -14.8 % |
| ('mkt_instead', 20, 0.02) | 151 | 7.9 % / 1.21 / -7.0 % | no | 33.6 % / 1.99 / -14.7 % |
