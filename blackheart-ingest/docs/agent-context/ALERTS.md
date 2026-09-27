# Alerts, the alert bus, the SSE stream, notifications and phone push

Read when you raise, resolve or route an alert, touch `idx.alert`, `runlog`, `notify`, `push`, `prefs`, the SSE stream
(`/idx/stream`) or its tests. Map: [../../CLAUDE.md](../../CLAUDE.md). Price levels that fire alerts:
[BOOKS_TICKETS.md](BOOKS_TICKETS.md). Job times: [JOBS.md](JOBS.md).

## Alert lifecycle (the three rules)
- Alerts are rows in `idx.alert`, shown by the app (`/equities/ops` via `GET /idx/ops` on this server); warning/critical ones
  also go out through `notify` (below).
- Three rules, learned from a desk that woke up with 38 open alerts covering two incidents:
  1. a check that runs on a schedule raises `runlog.alert_once`, never `runlog.alert` - `alert` is for one-off events;
  2. the message must be **stable for the whole incident** (a timestamp, not "53367s ago", or dedup can never match);
  3. whatever raises an alert resolves it when the condition clears - `runlog.resolve(conn, job, like=...)` - because an alert
     only a human can close is one nobody reads.
- `runlog.sweep_info` acknowledges 'info' rows older than 3 days (the ARA watch writes two a night); warnings and criticals are
  never swept (job `alert_sweep` 06:00, [JOBS.md](JOBS.md)).

## The alert bus and its stream (`idx/stream.py`, `idx/prefs.py`, `idx/signals.py`, migration 0035, 2026-09-24)
- A producer INSERTs into `idx.alert` and never picks a channel - the phone push, Telegram and the browser all consume that one
  table.
- `runlog.alert(...)` now takes `kind` (signal|ticket|exec|regime|ara|risk|feed|ops), `strategy`, `code`, `book`, `user_id`,
  `payload`, `dedupe_key`, `valid_until` and returns the id; **all optional**, so every free-text caller is untouched and its
  rows read as `kind IS NULL`.
  - A `dedupe_key` updates the open row in place (what makes a five-second execution read safe to repeat) and `valid_until`
    drops a stale row from `open_alerts` unless `include_expired`.
- A trigger fires `pg_notify('idx_alert', id)`; **`GET /idx/stream`** (SSE, `?since=`/`Last-Event-ID` replay, `?kinds=`
  filter) fans it out - one listener per worker, bounded per-client queues, an `event: gap` when a page falls behind, a
  heartbeat comment every 15 s.
- ⚠ **The listener is a thread, not a coroutine**: psycopg's async mode refuses to run on Windows' ProactorEventLoop, so a
  daemon thread holds the sync LISTEN connection and hands rows over with `call_soon_threadsafe` - same behaviour on both
  platforms. `GET /idx/stream/status` says whether it is connected.
- Scoping: a service sees everything, a person sees the desk's rows plus their own books (the legacy `book:X`/`ticket:X` job
  convention is read too).
- Mutes and quiet hours (`idx.alert_pref`, `GET|PUT /idx/alerts/prefs`) are applied **at the phone channel only** - an open page
  is somebody looking on purpose - and `kind='exec'` is never pushed.
- `idx.strategy_signal` (`idx/signals.py`) and `trend_book`'s nightly signal rows: [STRATEGIES.md](STRATEGIES.md#what-each-strategy-said-idxstrategy_signal).
  `regime_watch` (the gate on the bus the day it turns): [STRATEGIES.md](STRATEGIES.md).

## Checking the stream (hardening, 2026-09-24)
- `GET /idx/stream/status` -> `{connected, subscribers, last_id, dropped}`; `connected` is false until the first subscriber
  arrives (the listener starts lazily), so open a stream before reading it.
- `curl -sN 'http://127.0.0.1:8001/idx/stream?kinds=ops'` shows the raw frames.
- `ops/stream_load.py [clients] [rows]` is the load check: it opens N connections, writes M rows and reports delivery and
  latency, then deletes its own rows - measured 2026-09-24 on this box, **20 clients x 25 rows = 500/500 delivered, p50 2 ms,
  p95 5 ms, 0 dropped**.
- Two failure modes are verified rather than assumed: killing the listener's Postgres backend (`pg_terminate_backend` on the
  `LISTEN idx_alert` pid) reconnects within ~3 s and the **already-open browser connection keeps receiving** - no client
  reconnect needed; and a client that falls `QUEUE_MAX` rows behind gets `event: gap` rather than a quietly short stream.
- ⚠ **httpx's ASGI transport collects a response body before returning it**, so a FastAPI `TestClient` hangs forever on this
  route - the tests call the route coroutine directly and read its `body_iterator` with a timeout (`tests/idx/test_stream.py`).

## Notifications go to a person (from the multi-user change, `idx/who.py`, migration 0026)
- `notify.send(user_id= | book=)` -> the book's owner's phones, alerts `book:X`/`ticket:X` -> X's owner, desk alerts ->
  `IDX_OPS_NOTIFY_EMAIL`'s phones (unset = dropped); `journal.record(user_id=)` defaults to the book's owner.
- Callers and scoping: [ARCHITECTURE.md](ARCHITECTURE.md).

## Phone push (`idx/push.py`, migration 0025 `idx.push_device`, 2026-09-17)
- The operator's notification channel is the Blackridge Android app (`blackheart-idx-web`; renamed from Papan on 2026-09-17 -
  older notes say Papan), not Telegram.
- `notify.send(text, title=, data=)` fans out to every configured channel:
  - the app (`push.broadcast` -> Firebase Cloud Messaging HTTP v1, bearer from a service-account JWT signed with
    `cryptography`, cached; `IDX_FCM_SERVICE_ACCOUNT` = path of the Firebase service-account JSON placed by the operator,
    never through chat or git)
  - and Telegram (only if `IDX_TELEGRAM_*` are set).
- A text's first line is the push title; `data.route` is the app screen a tap opens (`notify.ticket_data(t)` ->
  `/m/ticket?book=`; alerts -> `/m/more`).
- Device tokens come from the app (`POST /idx/push/register {token, platform, label}` + `X-Idx-User` from the app's proxy;
  `DELETE /idx/push/{token}`; `GET /idx/push/devices`; `POST /idx/push/test`); a token FCM reports gone (404 / UNREGISTERED)
  is disabled until the app registers again.
- Nothing here raises into the job that notified.
- CLI `idx push devices | test [--text]`, `idx notify --status` lists the channels.
- The open window's `kind='exec'` rows never go to a phone (`notify.on_alert` drops `kind='exec'`): see
  [BOOKS_TICKETS.md](BOOKS_TICKETS.md).
