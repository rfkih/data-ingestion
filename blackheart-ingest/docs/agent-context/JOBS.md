# Scheduled jobs (WIB)

Read when you add, move or debug a scheduled job, or need to know what runs when. Map: [../../CLAUDE.md](../../CLAUDE.md).
The scheduler is `idx/scheduler.py` (`idx run-scheduler`), run by the Windows task "Blackheart IDX scheduler"
(`C:/Project/scripts/idx-scheduler-task.ps1`, logon + 10-minute watchdog: [FEED.md](FEED.md)). This file is an index; the mechanism of
each job lives in the file named in the last column. More jobs (kill rules, risk, TCA, backups, watchdog) are in the monitoring
map of [../MODEL_INVENTORY.md](../MODEL_INVENTORY.md).

## The daily chain (original schedule line)
**Jobs (WIB):** `universe` 16:15 · `daily` every 15 min 16:30–20:00 until today's bar lands → `index` → `publish --since`
→ `features --since -45d` → `candidates` · 18:00 alert if no bar · `announce_recent` 20:30 (all-emiten feed, last 3 days,
one request per day) · `fundamentals` 21:00 Mon–Fri (discover current FY → download pending workbooks for
`metrics.universe_codes` → parse) and Sat 09:00 with the previous FY too · `dividends` 1st of month 09:30 (Yahoo) ·
Sunday `crosscheck` · `bar_backfill` 07:30 + 21:30 · `alert_sweep` 06:00.

Also inside the evening daily chain: books marked + checked at the end (`idx book mark` / `idx book check`), `levels.check`
after every mark, paper tickets filled at the next day's open, the monthly overlay check on the first trading day of the month,
`gapfade.settle`.

## Index of every job named in these docs
| job | when (WIB) | what | detail |
|---|---|---|---|
| `alert_sweep` | 06:00 | `runlog.sweep_info` acks 'info' rows older than 3 days | [ALERTS.md](ALERTS.md) |
| `fin_backlog` | Tue-Sat 05:30 | 2021-2023 quarterly workbooks, 60 a day | [DATA.md](DATA.md) |
| `news` | 06:10/12:10/18:10/22:10 | RSS into `idx.news_article` | [DATA.md](DATA.md) |
| `macro` / `macro_pm` | 07:30 / 14:00 Mon-Sat | macro series incl. BPS | [DATA.md](DATA.md) |
| `bar_backfill` | 07:30 + 21:30 | heals days IDX refused | [DATA.md](DATA.md) |
| `combo_preopen` | 08:30 | combined book | [BOOKS_TICKETS.md](BOOKS_TICKETS.md) |
| `open_window_subscribe` | 08:55 | ticket names onto the tick feed | [BOOKS_TICKETS.md](BOOKS_TICKETS.md) |
| `ara_touch` | every 2 min 08:58-16:01 | held/watched names at the ARA limit | [ARA.md](ARA.md) |
| `open_window` | 09:00 until 09:30 | `kind='exec'` reads per open line | [BOOKS_TICKETS.md](BOOKS_TICKETS.md) |
| `gapfade_entry` | 09:00 + 09:05 retry | gap-fade entry ticket | [BOOKS_TICKETS.md](BOOKS_TICKETS.md) |
| `combo_gap_entry` | 09:00/09:05 | combo gap sleeve entry | [BOOKS_TICKETS.md](BOOKS_TICKETS.md) |
| `combo_confirm` | every 2 min in session | ML watch level hit -> one-line buy ticket | [BOOKS_TICKETS.md](BOOKS_TICKETS.md) |
| `agent_decide` | every minute (acts once per decision minute) | online agent decisions | [ML.md](ML.md) |
| `ml_intraday_predict` | every minute in session | intraday forecasts | [ML.md](ML.md) |
| `ml_evaluate` | every 10 min | realise forecasts | [ML.md](ML.md) |
| `token_guard` | every 10 min | session must reach 16:15 + 30 min | [FEED.md](FEED.md) |
| `token_renew` | every 30 min | renew when < 3 h remain | [FEED.md](FEED.md) |
| `feed_watch` | every 5 min in-session | stale heartbeat / expired token | [FEED.md](FEED.md) |
| `gapfade_exit` / `combo_gap_exit` | 15:50 | sell tickets into the close | [BOOKS_TICKETS.md](BOOKS_TICKETS.md) |
| `universe` | 16:15 | daily chain start | above |
| `dt_watch_pick` | 16:20 | C1 picks | [RESEARCH.md](RESEARCH.md) |
| `daily` | every 15 min 16:30–20:00 | daily chain | above |
| `ml_intraday_train` | 16:30 | intraday training | [ML.md](ML.md) |
| `combo_nudge` | 16:30/19:30 | combined book | [BOOKS_TICKETS.md](BOOKS_TICKETS.md) |
| `agent_settle` | 16:50 | agent samples, paper fills, refit | [ML.md](ML.md) |
| `regime_watch` | 17:10 | regime gate on the bus the day it turns | [STRATEGIES.md](STRATEGIES.md) |
| (no-bar alert) | 18:00 | alert if no bar | above |
| `daily_fallback` | 19:40 weekdays | Yahoo closes when the IDX bar is missing | [DATA.md](DATA.md) |
| `ara_watch` | 20:05 | `ara.settle` then the ARA list | [ARA.md](ARA.md) |
| `registry_refresh` | 20:05 | registry scorecard import | [STRATEGIES.md](STRATEGIES.md) |
| `feed_audit` | 20:10 | coverage < 95 % | [FEED.md](FEED.md) |
| `signal_board` | 20:15 Mon-Fri | board rows into `idx.strategy_signal` | [STRATEGIES.md](STRATEGIES.md) |
| `broker_snapshot` | 20:20 | broker capture (+ token freshness) | [FEED.md](FEED.md) |
| `announce_recent` | 20:30 | all-emiten announcements, last 3 days | above |
| `combo_expire` | 20:30 | missed lines + nightly scorecard | [BOOKS_TICKETS.md](BOOKS_TICKETS.md) |
| `ml_daily` | 20:40 Mon-Fri | evaluate -> train -> predict -> scorecard -> purge | [ML.md](ML.md) |
| `dt_watch_settle` | 20:45 | C1 settle | [RESEARCH.md](RESEARCH.md) |
| `fundamentals` | 21:00 Mon–Fri, Sat 09:00 | workbooks | above |
| `combo_plan` | 21:10/21:40 | combined book plan (after `ml_daily`) | [BOOKS_TICKETS.md](BOOKS_TICKETS.md) |
| `dividends` | 1st of month 09:30 | Yahoo dividends | above |
| `annual` | the 6th, 10:00 | annual reports, <= 8 per run | [DATA.md](DATA.md) |
| `consensus` | Sat 11:00 | Yahoo analyst consensus | [DATA.md](DATA.md) |
| `logos` | Sunday 10:00 | new listings' logos | [DATA.md](DATA.md) |
| `crosscheck` | Sunday | cross-check | above |
| (rebalance reminder) | May 1–10 | alert if the live book has no rebalance ticket yet | [BOOKS_TICKETS.md](BOOKS_TICKETS.md) |
