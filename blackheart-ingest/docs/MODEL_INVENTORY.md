# IDX desk - model inventory and change control

Track A7 (operator 2026-09-26). One entry per model that touches money or the operator's decisions: what it is, where it
lives, how it was validated, what is known to be wrong with it, and what watches it. Review: every month with the kill-rule
report, and whenever a study changes a number below. Owner of every live setting: the operator. Author of the research and code:
the operator + Claude - which is exactly why the independent replication step in the change rule exists.

## Change control (binding)

A live parameter (a book's rule, sizes, stops, confirmation rules, universe, sleeve on/off) changes only when ALL hold:

1. **Pre-registered study** in `idx.study` with the rule, the pass bar and the trial count written before the result.
2. **Independent replication**: an agent (or person) re-implements the changed rule from a written spec, blind to the research
   code, and reproduces the study's trade list. Gap-fade 2026-09-26 is why: the replication found two look-aheads that 400
   studies of the same engine had not.
3. **Journal entry** on the book (who, why, which study) and a settings version (`idx.strategy_config_version`).
4. **Freeze**: `live-fae554` and `paper-edbb01` are frozen until 2027-03-26 (`idx combo freeze`). Allowed during the freeze:
   switching a sleeve OFF (a kill rule's action), cash, fees, broker, label, note. Anything else needs `--override "reason"`,
   which is journalled.

A study that later turns out to be wrong is marked superseded (`research_store.supersede`), never edited; its inputs are
pinned (`idx/snapshot.py`, `idx.study_snapshot`) so the old number can still be re-derived.

## Live models

| model | where | reference | independent replication | status |
|---|---|---|---|---|
| Combined book (construction: 10/5/10 % NAV, cash floor 30 %, ens4, stop 5 %) | `idx/combo_book.py`, books live-fae554 / paper-edbb01 | **#386** (48.7 %/yr, Sharpe 2.15, mDD -18.0 %, 2022-01 -> 2026-09) | construction grid audited (#380 PBO 0.33; #384 SPA p < 0.001) | LIVE, frozen to 2027-03-26, Rp 30 M |
| Gap-fade sleeve | `idx/gapfade.py`, combo `gap` | #386 gap_only (11.0 %/yr, +2.07 %/trade, 256 trades) | **PARTLY -> fixed** (IDX_REPLICATION_GAPFADE_2026-09-26.md): two look-aheads removed, #348 superseded | LIVE in combo |
| Trend sleeve (60-day high / MA200 / 1.5x volume, trail-10, regime gate, small universe) | `idx/trend_book.py`, combo `trend`, book trend_live | #386 trend_only (12.7 %/yr, 279 trades) | **YES** - 279/279 trades, prices identical (IDX_REPLICATION_TREND_ML_2026-09-26.md) | LIVE in combo + trend_live |
| ML sleeve (5-day score, cost-aware entry, ens4 confirmation, same-day stop 5 %) | `idx/combo_book.py` + `idx/intents.py`, combo `ml` | #386 ml_only (29.7 %/yr, 876 rule-trades) | **YES** - 876/876 trades in all four legs | LIVE in combo |
| ML prediction desk (daily LightGBM per horizon, champion/challenger) | `idx/ml/` | purged 3-block validation, placebo per horizon | not replicated (the score is taken as given by the sleeve replication) | forecasts only; the 5d score feeds the ML sleeve |
| Value strict composite (annual May rebalance) | `idx/annual.py`, `candidates.py`; books live-82e98d, live-b877d2 | robustness scorecard (ROBUST; DSR 0.30; 7 rebalances) | not replicated | books hold nothing: Rp 20 M cannot run the ~12-name rule (Rp 5 M/name minimum) |
| Kill rules | `idx/killrules.py` | reference #386 trade lists; declared 2026-09-26 | unit tests | nightly 20:30, alerts only |
| Risk report (VaR/ES, Euler, liquidity, replays, two-factor scenarios) | `idx/risk.py` | #381, #385 | unit tests | nightly 20:25, alerts on breach |
| Regime monitor (price-limit regime, HMM volatility state) | `idx/regime_monitor.py` | #385, #387 | unit tests | nightly; warns on a narrow price limit |

## Known limitations (read before quoting any number)

- **One period, one year carries it.** 2022-26, 4.7 years; 2025 dominates (combined ex-2025 26.1 %/yr; trend ex-2025 1.2 %/yr).
  Planning numbers are ~+20 %/yr with a -20..-30 % drawdown (FE-3, #380), not the backtest.
- **Multiple testing.** ~1,022 trials in the ledger. Deflated Sharpe 0.23-0.70 depending on the effective N (#380); the
  Harvey-Liu-Zhu haircut keeps the Sharpe at 1.45-1.74 (#384). Both are in-sample statements about 2022-26.
- **Gap-fade exists only under a wide price limit** (#387): from 2020-04 to 2023-05 the lower limit was ~7 % and the event
  could not happen. The regime monitor warns if it narrows again. It earns in high-volatility regimes (#385), and its
  selection order differs between backtest (most liquid first) and live (deepest gap first) - 14 days in the sample.
- **Trend loses in high-volatility regimes** (#385) and is sensitive to a one-day-late entry (Sharpe 1.31 -> 0.91, #63).
- **ML stop assumes a market-on-close sale** at the triggering close (#288); the live intent fires 15:40-15:50.
- **Tail dependence**: the sleeves fall together about twice as often as their correlation implies (#385). A 2020-type crash
  (IHSG -47 %) costs a median -26 %, worst -55 % of NAV with no exits (#385 S3).
- **Execution is manual** (two-key tickets worked in the Stockbit app); fills, misses and slippage vs the paper twin are
  measured (scorecard, weekly TCA) but not yet known.
- **Data** comes from the exchange website and Stockbit's app endpoints, not a licensed feed; survivorship verified clean
  (delisted names are in the daily dumps); IDX opening prints are dense only from 2025.

## Pending research (pre-registered, judged later)

| study | judged when | command | bar |
|---|---|---|---|
| Execution bandit (how to place a buy: cross / join the bid 5 or 15 min / wait for a 1-tick spread) | >= 20 recorded order-book sessions, ~2026-10-19 | `python research/idx_exec_bandit.py` | saves >= 5 bps vs crossing, t >= 2 over sessions, both halves |
| Live confirmation per sleeve (#394) | ML 85, gap 92, trend 161 closed live trades | `idx combo kill` | t >= 2 on live net returns |

## Monitoring map

| what | job | when (WIB) | reaches the operator |
|---|---|---|---|
| kill rules + scorecard | combo_expire -> kill_check | 20:30 Mon-Fri | push on breach |
| risk + price-limit regime | risk_check (+ regime_monitor) | 20:25 Mon-Fri | push on breach / narrow limit |
| execution (TCA) | tca_weekly | Fri 20:50 | push, weekly |
| scheduler health | `idx watchdog` (own Windows task) | every 10 min | push at once |
| backups | db_backup / db_backup_full / restore_test | 22:30 daily / Sun 03:00 / 1st Sun 05:00 | push on failure; watchdog if > 26 h old |
