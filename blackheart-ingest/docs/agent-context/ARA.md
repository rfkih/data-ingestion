# ARA watch and ARA prediction vs actual (`idx/ara.py`)

Read when you touch the ARA watch list, the ARA touch monitor, `ara.settle`, `idx.ara_watch` / `idx.ara_touch` /
`idx.ara_scorecard`, or anything about auto-rejection-up (ARA) names. Map: [../../CLAUDE.md](../../CLAUDE.md). ARA/ARB band
arithmetic used by tickets (`ticket.reject_band`): [BOOKS_TICKETS.md](BOOKS_TICKETS.md). Job times: [JOBS.md](JOBS.md).

The prediction-vs-actual record below was added as measurement only, inside the operator's ARA freeze.

**ARA freeze scope** (operator decision 2026-09-23, narrowed 2026-09-24; source: auto-memory `feedback_ara_scope_frozen`):
- Forbidden: ARA books, ARA entry rules, NEW ARA screens, ARA research menus (incl. the pre-registered "ARA approach entry").
- Allowed: keep `idx/ara.py`, the `ara_watch` (20:05) and `ara_touch` (2-min) jobs, `/ara` + `/m/ara` and their alerts as
  they are; the existing page and the 20:05 job MAY carry a better model when the operator asks (done 2026-09-24:
  `idx/ara_model.py`, migration 0037). If the touch alert becomes noise, disable the `ara_touch` job; do not extend it.

## ARA watch (`idx/ara.py`, migration 0032 `idx.ara_watch` / `idx.ara_touch`, 2026-09-23)
Research menus 16, ML-3, 34 = studies #56, #57, #101.
- Tomorrow's ARA touches are predictable from today's bars (walk-forward AUC 0.86-0.92, top-5/day precision 7-18 %) but not
  buyable (the names that keep going open locked) - so this is information, never a ticket.
- Scheduler `ara_watch` 20:05 WIB: LightGBM P(touch next session) on bar-only features (ret1/5/20, lock streak, days since the
  last touch, volume ratio, value, band, range position, age), top-10 + every held name with its ARA price (35/25/20 % over the
  close, rounded down to the tick) -> `idx.ara_watch`, one info alert + push.
- Scheduler `ara_touch` every 2 min 08:58-16:01: held/watched names in the feed whose day high reached the limit -> state
  `locked` (no offer) / `at_ara` (sellers queued) / `faded` (trading under it) -> `idx.ara_touch`, one warning alert per state
  change (a held name's alert is `book:<book>`, so it reaches the owner's phone) carrying the study-#101 numbers:
  - a locked close is followed by +431 bps next day vs the ARA price (liquid, n 440),
  - a faded touch closes -661 bps under it (n 231).
- CLI `idx ara watch|show|touch|today`; API `GET /idx/ara/watch`, `GET /idx/ara/touch`. Tests `tests/idx/test_ara.py`.
- The ARA watch writes two 'info' alerts a night; `runlog.sweep_info` acknowledges them after 3 days ([ALERTS.md](ALERTS.md)).

## Prediction vs actual (migration 0062, 2026-09-27)
Operator: "pencatatan lengkap dari prediksi dan aktualnya"; measurement only, inside the ARA freeze.
- `ara.settle` runs first in the 20:05 job (in-process, before the model subprocess; a failure alerts and never stops the list).
- It fills, for every stored score of every earlier run whose next session's official summary is in (>= 80 % of the run day's
  rows): `ara_watch.next_date / next_prev / next_ara_px` (the limit from IDX's `previous` that session, so corporate actions are
  followed) `/ next_open / high / low / close / volume / offer_volume / touched / locked / ret_close / ret_high / outcome`
  (lock | touch | none | no_trade | no_bar)
  - labels identical to the model's LOCK1/TOUCH1 (test `test_outcome_labels_are_the_models_training_labels`).
- And one `idx.ara_scorecard` row per run: top-5/10/20 locks + touches + settled counts, precision@k, recall20 of the
  universe's locks (universe = `coverage()`'s scoring mask on the bar day), base rate, listed / buyable locks, mean P of the top
  10 (calibration check), AUC + Brier only for whole-ranking runs (2026-09-25 on).
- Runs 09-23 (old list, model NULL, not pooled) and 09-24 stored only the list, so they have precision but no AUC; no
  reconstruction was backfilled.
- CLI `idx ara settle [--run-date D] [--force] | record [--run-date D | --code X] [--all] | scorecard [--days N]`;
  API `GET /idx/ara/record?run_date=&code=&all_rows=`, `GET /idx/ara/scorecard?days=`.
