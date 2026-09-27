# Strategies - value/quality candidates, overlays, the strategy catalog, the registry, the daily board

Read when you touch which names a book buys (`idx/metrics.py`, `idx/candidates.py`, `idx/strategies.py`), the book overlays
(`idx/overlay.py`: regime gate, entry gate, take-profit, trend exit, cash buffer), the desk registry (`idx/registry.py`), the
daily board (`idx/signalboard.py`) or `idx.strategy_signal`. Map: [../../CLAUDE.md](../../CLAUDE.md). **Before changing any live
parameter or quoting a strategy number, read [../MODEL_INVENTORY.md](../MODEL_INVENTORY.md).** Books and tickets that execute
these rules: [BOOKS_TICKETS.md](BOOKS_TICKETS.md). Job times: [JOBS.md](JOBS.md).

## Value/quality book (phase 2 verdict)
Research: `research/IDX_VALUE_QUALITY_2026-09-12.md` rev. 3; review `research/IDX_REVIEW_2026-09-12.md`.
- `idx/metrics.py` is the one PIT evaluator (latest audited + latest quarterly → TTM, loose/strict gates, warnings; information
  cutoff = 16:00 WIB of the as-of day; prior-period comparatives come from the report (`net_profit_prior`, migration 0009) —
  the YoY ratio is only inverted when its sign is certain).
- `idx/candidates.py` applies the rule:
  - board Utama/Pengembangan **on the day** (`board_from_remarks`: 5th char of the day-dump notation string, 1 Utama
    2 Pengembangan 3 Akselerasi 4 Pemantauan Khusus 5 Ekonomi Baru)
  - → traded that day → liquid ≥ Rp 5 bn/day → loose gate
  - → composite **average** rank E/P+B/P+DY → top fifth, min 10, only when the pool has ≥ 20 names.
- `rank_pool(rows, gate=, keys=, sector_cap=)` is the single implementation — `research/idx_value_quality.py` calls
  `candidates.build()`/`rank_pool()` per rebalance date, so backtest and live list cannot drift.
- Rows carry `data_error_ratio` (ratio > 50×), `no_trade_on_date`, `scale_mismatch` warnings.
- `idx/card.py` is the per-name thesis card. `GET /idx/candidates[?all=1&as_of=]`.
- Gates are evaluated on the **audited** year; TTM and quarterly warnings are shown for judgment, never used to exclude
  automatically.
- `idx answers --score` (forward returns per pack stance / veto): [RESEARCH.md](RESEARCH.md).
- `candidates.build` and `pack.build` anchor on the last COMPLETE day: [DATA.md](DATA.md). Workbook scaling behind the
  `scale_mismatch` warning: [DATA.md](DATA.md).

## Book overlays (`idx/overlay.py`, migration 0012, `research/IDX_TREND_OVERLAY_2026-09-13.md`)
Per-book flags:
- `regime_filter` (cash while COMPOSITE < its 200-day average; monthly check on the first trading day of the month inside the
  daily chain -> `cash` ticket when it turns off, `rebalance` ticket when it turns on; an annual rebalance while off becomes a
  cash ticket)
- and `entry_gate` (listed names under their own SMA200 are held back at a rebalance, bought with an `entry` ticket at the
  monthly check they cross).
- Checks recorded in `idx.regime_check`; `idx overlay status | check [--dry-run]`; `/idx/overlay`, `POST /idx/overlay/check`.
- Plus `take_profit_pct` (NULL = off): at the monthly check, held names at or above purchase x (1 + pct) go into an exits ticket
  (`research/IDX_SELL_RULES_2026-09-13.md`).
- Plus `trend_exit` (migration 0014): at the monthly check, a held name that crossed under its 200-day average since the
  previous check goes into an exits ticket, and the entry gate also buys a held-back name when its 14-day RSI is at or under 30
  (the asymmetric rule, `research/IDX_ASYMMETRIC_2026-09-13.md`).
- Plus the cash buffer (migration 0016): `cash_floor_pct` of NAV kept in cash, `stress_cash_pct` while the stress detector
  (`stress_rule` ma | any2; four signals recorded in `idx.stress_check` at the monthly check) is on; the ticket builder uses it
  as the plan's cash reserve and the monthly check issues a rebalance ticket when the target moves 5+ points
  (`research/IDX_CASH_BUFFER_2026-09-14.md`).
- All OFF by default (paper book: the four trend overlays on since 2026-09-13).
- **On a TREND book `regime_filter` is the regime gate:** no NEW entry while the COMPOSITE closes under its 200-day average,
  held names untouched (`trend_book.hold_back`, `overlay.index_regime`; the ticket carries `regime` + `held_back`; validated in
  `research/IDX_REGIME_VALIDATE_2026-09-22.md` and `IDX_ROBUSTNESS_SCORECARD_2026-09-22.md`); on `paper_trend` and
  `trend_live` since 2026-09-22; CLI `idx book set --book X --regime-filter on|off`.
- New job `regime_watch` 17:10 WIB (`overlay.regime_change_alert`) puts the gate on the bus the day it turns, and only then.
- Signals are computed at the check close; tickets are meant to be worked at the next open (delay cost measured in
  `research/idx_execution_delay.py`).
- Minimum ticket line (`ticket.min_trade_for(nav)`): [BOOKS_TICKETS.md](BOOKS_TICKETS.md).

## Strategy catalog (`idx/strategies.py`, migrations 0010 + 0011)
- Families `rule` (baseline) · `strict` (deployed since 2026-09-12, the operator's call ahead of the pre-registered May 2027
  date) · `strict_cash` (tested: passes its criterion on one name, ENRG; not the default) · `value` · `momentum` ·
  `momentum_rank` · `growth`, each `{gate, order, weight[, keys]}`.
- `strategies.deployed()` is the API's default strategy; a choice = family + size (None = natural fifth, 10, 15).
- `strategies.pick(key, rows, size=, weight=)` is the ONE implementation of "which names, what weights" (composite families
  order their gate pool; feature families order the rule's fifth by ep / mom / np_yoy); the research scripts call it too
  (`research/idx_top10.py <10|15>`), so tested == deployed.
- `candidates.build` now stores `mom` (12-1 month momentum, `momentum_at`).
- `idx.book.strategy` + `max_names` say what a book follows; `ticket.build(strategy=, max_names=)` defaults to them and
  `ticket.plan` takes `{code: weight}` targets.
- `idx.strategy_history (strategy, size, month)` holds the research record (`idx strategies import-history <rev3 json>
  <top10 json> <top15 json>`, `idx strategies list`).
- Routes: `GET /idx/strategies`, `GET /idx/strategies/{key}?size=`, `GET /idx/candidates?strategy=&size=&all=`,
  `PUT /idx/book/{b}` accepts `strategy`/`max_names`, `POST /idx/ticket/build?strategy=`.

## The desk registry (`idx/registry.py`, migration 0034, 2026-09-24)
- One entry per edge the desk runs - value, trend, overlays, the gap-fade event book, execution timing, the growth filter,
  allocation - plus the families research closed.
- Two halves on purpose:
  - the STATIC half (in code, reviewed in a commit) is what a strategy IS - rule, falsifier (what would close it), cadence,
    `runs_in`, a `books` filter over `idx.book` resolved live, and its evidence study ids;
  - the IMPORTED half is what it EARNED - `registry.refresh_scorecard(conn)` reads the newest `roi_scorecard` study from
    `idx.study` and writes `idx.strategy_state` (status, scorecard JSON, evidence, source_study, refreshed_at).
- **A strategy with no study shows no performance figure** - that is the rule that keeps the page honest as research moves, so
  never hand-type a number into the registry.
- Routes `GET /idx/registry`, `GET /idx/registry/{key}` (adds the study rows and, for an annual family, its per-size history),
  `POST /idx/registry/refresh` (service_only); nightly job `registry_refresh` 20:05 WIB; CLI `idx registry [list|show KEY|refresh]`.
- The older `/idx/strategies*` routes are untouched - they serve the annual book's family picker (`strategies.CATALOG`,
  `pick()`), a different question.
- Phase 0 of `docs/superpowers/plans/2026-09-24-blackridge-strategies-and-alert-stream-plan.md`. Tests: `tests/idx/test_registry.py`.
- `registry.detail()` gained `today` for the strategy pages: [BOOKS_TICKETS.md](BOOKS_TICKETS.md) (open window section).

## What each strategy said (`idx.strategy_signal`)
- `idx.strategy_signal` (`idx/signals.py`, shipped with the alert bus, migration 0035, 2026-09-24) records what each strategy said on a day, ticket or no ticket;
  `trend_book` writes it nightly (buy / sell / hold_back) and raises one `kind='signal'` summary. The bus it rides:
  [ALERTS.md](ALERTS.md).

## The daily board (`idx/signalboard.py`, 2026-09-24)
- One screen answering "what does each strategy want today", so the operator picks the one they run instead of opening five
  pages.
- Five cards, the top of the registry's ROI rank restricted to **equity-only engines that can speak on any day**: `gapfade` (1),
  `trend_small` (3), `combined_book` (4), `value_strict` (6), `trend_liq` (7).
  - `book_gold` (5), `ew3` and `gem_idr` are left out because they price gold and foreign indices the desk does not trade;
    `trend_small_base_rate` is a yardstick; the overlays are written into a row's reason, never shown as a sixth strategy.
- **Bookless**: no cash, no lots, no ticket - only what the rule saw, so the board never invents a position.
- **Entries only**: an exit depends on what a book holds, which is the ticket's job.
- `trend_rows` keeps a gate refusal visible as `action='hold_back'` rather than dropping it; `value_rows` emits `action='hold'`
  outside the May 1-10 window, because calling an annual target list a buy order would misread the rule, and `buy` inside it;
  `combined_rows` halves each sleeve and tags the row with which one it came from.
- An engine that throws is reported as `error` on its own card - silence and "nothing today" must never look the same.
- `build()` ~1.2 s, so **`GET /idx/board[?as_of=]`** computes live (defaults to the newest bar date). CLI `idx board [--as-of D]
  [--record]`.
- Job `signal_board` **20:15 WIB** Mon-Fri records the rows into `idx.strategy_signal` under `book=''` (a book's own rows are
  written by that book's run and untouched) and raises one `kind='signal'` alert per strategy.
- Screens: `/signals` and `/m/signals` in `blackheart-idx-web`. Tests: `tests/idx/test_signalboard.py`.
