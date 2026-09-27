# Books, tickets, fills, price levels, the combined book and gap-fade

Read when you touch a book (`idx/book.py`), a ticket (`idx/ticket.py`), fills (hand, paper, one-tap), price levels, the open
window, the combined book (`idx/combo_book.py`) or the gap-fade book (`idx/gapfade.py`). Map: [../../CLAUDE.md](../../CLAUDE.md).
**Before changing any live parameter or quoting a strategy number, read [../MODEL_INVENTORY.md](../MODEL_INVENTORY.md)**
(binding change control; combo books frozen to 2027-03-26). What the books follow (value/strict candidates, overlays, the
strategy catalog, the trend rule's regime gate): [STRATEGIES.md](STRATEGIES.md). Job times: [JOBS.md](JOBS.md).

## Position book (`idx/book.py`, migration 0007)
- `idx.book` (live | paper; cash, fee %, dividend tax), `idx.fill` (buy | sell | split; average cost, fees in the basis) →
  `idx.position` rebuilt from fills.
- `idx book mark` writes `idx.book_mark` + `idx.book_nav` per trading day (net dividends credited on the ex-date, splits become
  `split` fills; cash anchored on the live `book.cash`, so a back-dated fill needs `--rebuild`). `--rebuild` belongs to
  `idx book mark` only (`book.mark(..., rebuild=)`): after a back-dated `idx book fill` / `idx ticket fill`, re-run
  `idx book mark --rebuild`; passing it to a fill command does nothing.
- `idx book check` raises deduplicated `idx.alert` rows (`job='book:<name>'`) for held names: material disclosures (last 3
  days), a new report breaking the book rule or with TTM warnings, unrealized loss ≥ 25 %, liquidity below half the floor.
- `idx book fill --date --code --side --lots --price [--fee]` is how the operator records broker fills;
  `idx book paper-seed --book paper --as-of <candidate run date> --amount N` buys the selected list at the next open.
- Both books are marked + checked at the end of the daily chain.
- Routes: `GET /idx/book/{book}`, `POST /idx/book/{book}/fills`, `PUT /idx/book/{book}`.
- `research/idx_book.py` (CSV ledger) is superseded; `idx book import --file fills.csv` reads its format.

## Books per person (`idx/who.py`, migration 0026, 2026-09-17)
- `POST /idx/books {label, kind paper|live, rule annual|trend, cash, broker, fees, strategy, max_names, trend_variant}` -> id
  `<kind>-<6hex>` (`ticket.is_paper` = id starts with `paper`).
- `DELETE /idx/book/{book}` archives (open tickets cancelled, out of every list and job), `GET /idx/books` lists the caller's.
  `book.create_book/list_books/owner_of/archive`.
- `GET /idx/books` lists every book (kind live|paper, rule annual|trend, nav, open ticket) for the phone's selectors; the extra
  fields it returns for the v3 screens (`capital`, `halted_at`, ...) are in [ARCHITECTURE.md](ARCHITECTURE.md).
- Owners, scoping (`own_book` -> 404) and the first-account assignment of `live`, `paper`, `trend_live`, `paper_trend`:
  [ARCHITECTURE.md](ARCHITECTURE.md).

## Rebalance ticket (`idx/ticket.py`, migration 0008)
- `idx ticket build --book live [--mode rebalance|exits] [--as-of run_date] [--max-names N]` → `idx.ticket` + `idx.ticket_line`.
- `rebalance` = hold the selected candidates equal-weight: sell what is no longer selected, trim/add beyond ±1 % of NAV
  (min Rp 5 M), buy new entrants, whole lots, limit = one tick through the reference close clamped inside the auto-rejection
  band, buys capped by cash + expected sale proceeds − 1 % reserve (`cash-limited` flag).
- `exits` = sells only, for held names whose newest report breaks the book rule or whose latest pack answer is `sell`.
- Lines carry rank, strict-gate fails, TTM warnings and the pack stance/veto as flags.
- `ticket.min_trade_for(nav)` scales the minimum line with the book (NAV/20, floor Rp 1M, cap Rp 5M).
- **Paper tickets** fill themselves at the next day's open inside the daily chain (`idx ticket paper-fill --dry-run` previews;
  sells first, buys trimmed to cash, unfillable lines skipped, ticket closed).
- **Live fills** are captured by hand: `idx ticket fill --line ID --lots --price [--fee]` (→ `idx.fill`, book re-marked;
  partial fills tracked), `idx ticket skip --line ID --reason`, `issue|close|cancel`.
- **IDX rules encoded (verify against Peraturan II-A on change):**
  - lot 100;
  - fractions 1/2/5/10/25 below 200/500/2,000/5,000/above;
  - auto-rejection ASYMMETRIC (`ticket.reject_band`): ARA 35/25/20 % for 50–200/200–5,000/>5,000 rounded down to the tick,
    ARB 15 % flat rounded UP to the tick (since 2025-04; kept by the 2026-09-28 rules, Kep-00136/BEI/09-2026) - until
    2026-09-27 the lower side was the symmetric 25/20/35 %, which priced must-fill stops (combo ML stop, same-day intent stop)
    under the ARB where JATS rejects them; the same-day stop now bands on yesterday's close, not the firing price.
- Scheduler: May 1–10 alert if the live book has no rebalance ticket yet.
- Routes: `GET /idx/ticket/latest?book=`, `GET /idx/ticket/{id}`, `POST /idx/ticket/build`, `POST /idx/ticket/{id}/status`,
  `POST /idx/ticket/lines/{id}/fill|skip`. `ticket.build(strategy=, max_names=)` / `ticket.plan`: [STRATEGIES.md](STRATEGIES.md).

## Price levels (`idx/levels.py`, migration 0024 `idx.price_level`, 2026-09-17)
- Per book+code+kind (stop | take_profit | warn) a level and a note saying what to do.
- `levels.check` runs after every mark in the daily chain and the Yahoo-fallback path: stop/warn fire at close <= level,
  take_profit at close >= level; alert critical (stop, take_profit) / warning (warn) through `runlog.alert` (Telegram when
  `IDX_TELEGRAM_TOKEN`/`_CHAT` are set, see notify.py), stamped `triggered_at` so it fires once until `idx levels reset CODE`.
- Index codes (COMPOSITE) read `idx.index_daily`.
- CLI `idx levels set CODE [--stop L] [--tp L] [--warn L] [--note] | list | clear CODE [--kind] | reset CODE | check`.
- Live book 2026-09-17: satellite SSIA stop 1,030 / tp 3,440 / warn 1,250, LPKR 35 / 118 / 45; core names warn -25 % and
  stop -40 % vs avg; COMPOSITE warn 5,800 / stop 5,150.

## Working a ticket at the open (`idx/openwindow.py`, 2026-09-24)
- The half hour when the live tape is streamed, and the only one - the operator's boundary is *no live feed for tomorrow's buy
  list; the feed appears at the open, as a placement read for names that already have a ticket*.
- Two jobs:
  - `open_window_subscribe` **08:55 WIB** puts today's open ticket names on the tick feed (`feed_symbol.reason='ticket'`,
    additive - the standing liquid set is untouched),
  - and `open_window` **09:00** loops until 09:30, re-reading `execwatch.read` for every open line every `POLL_S` (5 s) and
    putting a `kind='exec'` row on the bus **only when a line's read changes** (or every `MIN_REPEAT_S` 30 s), deduped
    `exec:{ticket}:{line}` so a repeat updates in place, with `valid_until` 20 s so a screen drops a stale read by itself;
    then `unsubscribe()` takes only the `reason='ticket'` rows off the feed.
- It stops on its own: no open line, a halted book, a feed quieter than `STALE_FEED_S`, 09:30, or a `pg_try_advisory_lock`
  already held by another process (one writer).
- `line_message` quotes **the side of the book the read points at** - resting at the bid quotes the bid, taking the offer
  quotes the offer; the wrong one is a number somebody might type in.
- The exec rows never go to a phone (`notify.on_alert` drops `kind='exec'`): they are true for seconds, which is useless as a
  notification.
- `registry.detail()` gained `today` (the last run's `strategy_signal` rows + that strategy's open alerts) so the strategy
  pages can show what it is saying right now.
- Tests: `tests/idx/test_openwindow.py`.

## One-tap fill (`idx/fillmatch.py`, 2026-09-22)
- Recording fills by hand is the desk's biggest daily chore. For each still-open line of an **issued** ticket the tape says
  what the market actually traded inside that line's limit today (`idx.feed_trade`, from 09:00).
- `propose()` returns lots + price (VWAP snapped the conservative way — a buy rounds up, a sell down — and never worse than the
  limit) with a confidence (high = the flow was >= 10x the line, medium >= 3x, low under that), the eligible volume, the print
  count and the window.
- It cannot know which prints were the operator's (the feed carries no account), so it only ever proposes; the write still
  goes through `ticket.fill_line` (two-key, journal, book mark). A draft, closed or cancelled ticket proposes nothing.
- Route `GET /idx/ticket/{id}/suggest`, CLI `idx suggest [--ticket N | --book B]`, phone: the card under the line being worked
  on `/m/ticket`. Tests `tests/idx/test_fillmatch.py`.

## Combined book (`idx/combo_book.py`, migration 0039 `idx.book.params` / `idx.combo_watch` / `idx.combo_scorecard`, 2026-09-25)
- Operator: live Rp 20 M on the top-3 strategies, 5 % / 5 % / 10 % of NAV per trade, to measure Stockbit execution for a year.
  **Sizing at creation (2026-09-25), now stale:** the current live construction is 10/5/10 % NAV, same-day ML stop 5 %,
  Rp 30 M (reference study #386) - quote live numbers only from [../MODEL_INVENTORY.md](../MODEL_INVENTORY.md).
- One book (rule `combo`), one cash pool, 20 slots, three sleeves sized from `params.sleeves`:
  - `gap` (the deployed gap-fade scan, <= 5/day, tickets in 'gapfade'/'gapfade_exit' mode),
  - `trend` (the deployed trend rule on `small`, trail-10, regime gate; entry at the next close),
  - `ml` (idx.ml_prediction 5d score, cost-aware: signalled when EMA-3 excess > 2x the name's round trip, bought only when the
    price confirms >= signal close x 1.05 within 10 d, sold on score swap / 60-day expiry).
- Every line carries `sleeve:<name>` in flags; positions per sleeve are derived from filled lines.
- Jobs: `combo_plan` 21:10/21:40 (after `ml_daily`), `combo_preopen` 08:30, `combo_gap_entry` 09:00/09:05, `combo_confirm`
  every 2 min in session (watch level hit on the last feed trade -> one-line buy ticket; live draft + push, paper filled at the
  limit), `combo_gap_exit` 15:50, `combo_nudge` 16:30/19:30, `combo_expire` 20:30 (unexecuted live lines -> skipped 'missed' +
  nightly scorecard: per sleeve fills / misses / slippage bps vs ref_close / delay / P&L vs the backtest yardstick).
- Live tickets are two-key drafts; the paper twin (`paper-edbb01`) is the yardstick for `live-fae554`.
- CLI `idx combo create|set|plan|preopen|confirm|gap-entry|gap-exit|expire|nudge|scorecard|status`.
- Backtest: studies #166-#168 (`research/idx_combo_rupiah.py`): Rp 20 M -> 96.5 M 2022-26, CAGR 39.8 %, Sharpe 1.86,
  mDD -21.5 %, median calendar year +20 %. (The current reference study and live settings: [../MODEL_INVENTORY.md](../MODEL_INVENTORY.md).)
- **2026-09-25 (operator: 'coba a dan b'):**
  - `params.cash_floor` (0.30 on both books; menu 34 #177: mDD -21 -> -15 % for -3.6 pp CAGR) - `invested_ok` holds back any
    NEW buy (trend line, ML confirmation, gap line) that would take the invested share above 1 - floor (`floor_held` in the
    plan / gap result; an ML watch blocked by the floor stays pending);
  - and `params.ml.confirm_rules` = [[0.05,10],[0.08,10],[0.10,10],[0.08,5]] (ML-8 #175 ens4) - one `combo_watch` row per rule
    (migration 0041: `rule`, `size_frac`, unique (book, code, signal_date, rule)), each rule's fill tops the name up to the
    cumulative share of the rules that fired (`triggered_share`; a dust share is marked triggered and rolls into the next
    rule), a second rule on a name already held from the SAME signal adds to it without a new slot.
  - CLI `idx combo set --cash-floor 0.30 --ml-confirm '5/10,8/10,10/10,8/5'|single`.
  - Watches pending from before the switch keep rule '+5/10' / share 1 until they expire.
- Tests `tests/idx/test_combo_book.py` (11).
- Web routes for the combo screens (`/idx/combo/{watch,scorecard,positions,strategies}`, `/idx/combo/catalog`):
  [ARCHITECTURE.md](ARCHITECTURE.md).

## Gap-fade book (`idx/gapfade.py`, research menu 29b, 2026-09-22)
- The desk's first intraday book, PAPER ONLY (`paper_gapfade`, Rp 100 M, K=5, `rule='gapfade'`).
- Rule: a name whose **opening print** is <= -7 % against the previous close is bought at the open + 1 tick (deepest gaps
  first, slot = NAV/K) and sold into the **same** closing auction (close - 1 tick); nothing is ever held overnight.
- Jobs: `gapfade_entry` 09:00 + 09:05 retry (the opening auction prints reach the feed at ~08:58 and are the official open for
  ~90 % of names), `gapfade_exit` 15:50 (sell ticket), and `gapfade.settle` inside the evening daily chain (fills the exit at
  the official close).
- CLI `idx gapfade scan|entry|exit|settle|books|init`.
- Guards: feed coverage (>= 50 opening prints, else no trading + alert), stale bars, **no offer = skip** (a name locked at
  auto-rejection down cannot be bought — the mirror of the ARA trap), leftover positions swept at the next open with a warning,
  one entry + one exit ticket per day under the paper filler's advisory lock, halt respected, live books drafted not filled
  (two-key).
- ★ **The daily summary's "open" is the first trade of the day, not the opening auction** — on 2026-09-22 AALI's "open" printed
  at 10:45 — so the live book trades a stricter subset than the backtest (first print inside 08:55-09:10 only); the paper record
  measures that difference.
- Tests `tests/idx/test_gapfade.py`.
