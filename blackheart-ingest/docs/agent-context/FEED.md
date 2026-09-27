# Stockbit - tick feed, session tokens, broker capture

Read when you touch the real-time feed (`idx/feed/`), its Windows task, the Stockbit session tokens (`idx/broker.py`,
`idx.feed_token`, the relay page) or the broker-distribution capture. Map: [../../CLAUDE.md](../../CLAUDE.md).
Job times: [JOBS.md](JOBS.md). What reads the feed: gap-fade + combo ([BOOKS_TICKETS.md](BOOKS_TICKETS.md)),
ARA touches ([ARA.md](ARA.md)), intraday ML + the agent ([ML.md](ML.md)), the open window ([BOOKS_TICKETS.md](BOOKS_TICKETS.md)).

## Datafeed collector (`idx/feed/`, migration 0029, 2026-09-21)
- Real-time prints + order books from the operator's OWN Stockbit session (`wss://wss-jkt.trading.stockbit.com/ws`,
  subprotocol `web`, protobuf envelope with a plain `#O|CODE|BID|price;orders;volume|…` body — `feed/proto.py` documents the
  message shapes; no protobuf dependency).
- Personal data: **never into `/pub`, never into Blackridge.** History starts the day it first ran.
- Tables:
  - `idx.feed_trade` (every print; hypertable, compressed after 3 days)
  - `idx.feed_book` (top-10 each side, ≤ 1 sample/s/name, only on change)
  - continuous aggregates `idx.feed_bar_1m`, `idx.feed_book_1m` (refresh every minute)
  - `feed_symbol` (subscription, re-read every 5 min)
  - `feed_token` (24 h session JWT)
  - `feed_status` heartbeat · `feed_event` log · `feed_day` coverage audit (Σqty vs the official daily volume).
- Process: `idx feed run` (ONE websocket; asyncio receive loop + writer thread with its own connection and a bounded retry
  queue; idles outside Mon–Fri 08:40–16:20 WIB).
- Dead-connection detection: transport errors, app-level ping after 15 s silence / pong grace 13 s, and a data watchdog in
  continuous phases (no data 90 s → resubscribe, 180 s → reconnect); reconnect = backoff 1…30 s forever, fresh key + auth +
  re-read symbols; advisory-lock singleton; token-expiry warning 45 min ahead.
- Raw frames archived by default to `logs/idx/feed/<date>.frames.gz` (sync-flushed each second, 7 days) —
  `idx feed replay --file F` re-ingests a day after a DB outage or parser fix.

## The Windows tasks (restart and watchdog)
- Windows task **"Blackheart IDX feed"** (`C:/Project/scripts/idx-feed-task.ps1`; `-Restart` is the only correct restart —
  Stop-ScheduledTask leaves the python child alive holding the lock).
- It carries **two triggers: at logon and a 10-minute watchdog** (daily 00:00 + `PT10M` repetition — Task Scheduler cannot
  express "repeat forever" through `New-ScheduledTaskTrigger`).
- The watchdog is not optional: this box is never logged out, so before it existed a collector killed after the close
  (2026-09-23 18:50, a stray kill of the python processes) stayed dead and the desk woke up blind — no opening prints, so the
  gap-fade scan refused and ARA watch saw nothing.
- A start while it is already running is ignored (`MultipleInstances=IgnoreNew`) and a second collector that finds the
  advisory lock held **exits 0** (a no-op, not a failure — a non-zero exit would arm restart-on-failure every 2 minutes).
- The same watchdog is on **"Blackheart IDX scheduler"** (`C:/Project/scripts/idx-scheduler-task.ps1`), which had the same logon-only
  defect.

## Token (the Stockbit session)
- **The paste:** the operator logs in to stockbit.com and pastes the `credentialStorage` cookie at
  `http://127.0.0.1:8001/idx/feed/relay` — needed only if the laptop was off for 7+ days: **headless renewal works**
  (verified 2026-09-22: `POST exodus.stockbit.com/login/refresh`, refresh token as `Authorization: Bearer`, body `{}`;
  access 24 h, refresh 7 d, both rotate).
- `broker.refresh_and_persist(conn=)` / `idx broker refresh` takes the newest refresh token (the relay row `idx.feed_token`;
  env only as a fallback, by JWT `iat`) and stores the new pair in `idx.feed_token`.
- **Since 2026-09-25 the tokens live ONLY in `idx.feed_token`** (operator: "token nya ditaruh di db aja"): `broker.config()`
  reads the access token from the DB, the relay route no longer writes the env file, and `idx-local.env` holds no Stockbit
  token. The env file is written only as an EMERGENCY copy when the DB write fails after a refresh (the refresh token
  rotates, so a lost pair is a lost session).
- Three places renew: scheduler job `token_renew` every 30 min (`broker.renew_if_needed`, when < 3 h remain), the collector
  itself 45 min before expiry (worker thread, then `load_token`), and the 20:20 broker snapshot (`config_fresh(conn=)`).
- ★ **`token_guard` every 10 min (2026-09-22) is the one that guarantees a session for the trading day**:
  - off-session it keeps the 3-hour freshness rule; on a weekday up to 16:30 it demands enough validity to reach the close
    **16:15 + 30 min** (`broker.minutes_needed`, `renew_if_needed(need_until=)`) and renews from the refresh token.
  - When the session cannot be made to last that long (no refresh token, or Stockbit refused it) it raises ONE critical alert
    (`runlog.alert_once`) and then **pushes the operator's phone on every run — every 10 minutes — until it is fixed**;
    without a session the tick feed goes dark and the gap-fade jobs are blind.
  - The refresh token's own 7-day horizon is watched too (warning under 2 days), so the paste is asked for days ahead, never
    mid-session.
  - The guard passes its own clock into `token_status` (mixing clocks was a real bug in the first cut).
- The relay page shows the token status and has a "Renew now" button (`POST /idx/feed/token/refresh`); pasting a bare
  *refresh* JWT (7-day lifetime) is exchanged for a full pair on the spot, and any paste carrying a refresh token is
  mirrored into `idx-local.env`. **Superseded 2026-09-25** (the DB-only rule above): the env mirror predates it; the relay
  route now stores the paste in `idx.feed_token` only (checked in `idx/api.py` `feed_token`, 2026-09-28), and the env file
  is written only as the emergency copy.
- A re-login in the browser invalidates older refresh tokens — paste the cookie again if renewal answers 401 (alert `feed`:
  "token renewal failed").

## Feed CLI, routes, jobs
- CLI `idx feed status|symbols [--liquid N|--set A,B|--disable A,B]|token [--paste FILE|-]|audit [--date]`.
- Routes `GET /idx/feed/status`, `GET|PUT /idx/feed/symbols`, `POST /idx/feed/token` (service/loopback only).
- Scheduler: `feed_watch` every 5 min in-session (stale heartbeat / expired token → warning alert), `feed_audit` 20:10
  (coverage < 95 %).
- Ticket names put on the feed for the open only (`feed_symbol.reason='ticket'`): the open window in
  [BOOKS_TICKETS.md](BOOKS_TICKETS.md).

## Broker distribution capture, widened (migration 0033, 2026-09-24)
- The free Stockbit `order-trade/broker/distribution` endpoint serves four rolling windows (`period` = LAST_1_DAY /
  LAST_1_MONTH / LAST_3_MONTHS / LAST_1_YEAR, always ending on the last trading day - it cannot be moved into the past; the
  per-window `marketdetectors` history is Pro-only, HTTP 402), three investor splits (ALL / FOREIGN / DOMESTIC), three boards
  (REGULER / ALL incl. negotiated / TUNAI) and value or lots, and every payload carries the buyer->seller matrix.
- `broker.capture(conn, codes, matrix)` walks a matrix of those views (`MATRIX_CORE` = the 4 windows, `MATRIX_DETAIL` = 48
  views), stores:
  - per-broker totals in `idx.broker_summary` (value and lots merged into one row, `period` column, board stored as
    `MARKET_BOARD_REGULER|ALL|TUNAI`),
  - the matrix in `idx.broker_flow` (one row per side/broker/counterparty),
  - the payload in `idx.broker_summary_raw` (key now includes `data_type` + `period`; pre-0033 rows carry `period = 'LEGACY'`);
  - resumable per (name, window, view, day), one request/second.
- **Throttling looks like success**: after roughly a thousand requests the endpoint answers 200 with an empty payload (blank
  `date_info`, no matrix) and serves data again after about a minute of rest - there is no 429.
  - `capture()` counts empties, reads three in a row as pushback, rests `empty_backoff` (60 s) and retries, and stops the run
    after two fruitless rests; empty answers are never stored, so the next run retries them rather than resuming over a hole.
  - So a night takes a slice, not the whole matrix - ask for the core views first, they are the ones that cannot be recovered
    later. Also stops on 401/402/429.
- CLI `idx broker capture [--codes A,B] [--detail --min-v60 5e9] [--max N]`.
- The 20:20 job `broker_snapshot` now runs the core capture over the whole market (`broker.all_codes`, ~760 names) then the
  48-view detail matrix over the whole market too (~36k views, far more than one night's budget - it takes the next slice each
  night, operator's call 2026-09-24); `--min-v60` narrows either to the liquid names (`broker.detail_codes`).
- Why it matters: broker history cannot be bought back, only accumulated forward - this is the panel the
  breakout-vs-accumulation question (study #131) is waiting for.
- Tests: `tests/idx/test_broker.py` (wide capture section).
