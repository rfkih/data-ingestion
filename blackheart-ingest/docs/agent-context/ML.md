# ML - the self-learning prediction desk (`idx/ml/`) and the online learning agent (`idx/agent.py`)

Read when you touch `idx/ml/` (panels, training loop, champion/challenger, calibration, evaluation, scorecard, the forecast
record) or `idx/agent.py` (the paper bracket trader). Map: [../../CLAUDE.md](../../CLAUDE.md). The ML sleeve of the combined book
(which reads the 5d score): [BOOKS_TICKETS.md](BOOKS_TICKETS.md). The ARA model: [ARA.md](ARA.md). Live-model status and change
control: [../MODEL_INVENTORY.md](../MODEL_INVENTORY.md). Job times: [JOBS.md](JOBS.md).

# Self-learning prediction desk (`idx/ml/`, migration 0036 `idx.ml_model` / `idx.ml_prediction` / `idx.ml_scorecard`, 2026-09-24)

Operator: "continuous improving learning, training setiap hari, prediksi arah + harga, 1 menit .. 1 tahun".

## What it predicts
- Ten horizons (1m 10m 30m 60m on the tick feed; 1d 5d 20d 60d 120d 250d on bars), two LightGBM models each - `dir` =
  P(higher), `ret` = log return -> price on the tick.

## The panels
- `ml/daily.py` builds the daily panel from everything the desk holds, PIT-safe (bars + adj_factor, daily_summary foreign legs /
  closing book / frequency / float / index weight, COMPOSITE, 9 macro series as-of, fundamentals by published_at, 1-day
  broker-flow concentration + foreign share, sentiment, consensus as-of, disclosure-event flags, sector, cross-sectional ranks).
- `ml/intraday.py` builds the minute panel on the session grid (Mon-Thu 09:00-11:59 + 13:30-15:59, Fri 09:00-11:29 +
  14:00-15:59) from `feed_bar_1m` + `feed_book_1m` (best level = array index 1) - **labels and reference price are the book MID,
  not the last trade** (the last trade alternates bid/offer; on the last trade the 1-minute "hit rate" was 84 %, on the mid it
  is the real 70 %/AUC 0.81, i.e. menu 28's queue-imbalance lead).

## Training loop and promotion (`ml/loop.py`, `common`)
- `train(kind)` refits every (horizon, task) on the matured rows with the last N days held out (daily 40, intraday 1) and
  judges champion / refresh (champion's params, more data) / tune (two params moved one notch) on that same out-of-sample
  window.
- `common.choose` promotes: clear winner > TOL 0.005, refresh wins ties (newer data), a champion > 45 d old is replaced unless
  the challenger is worse by > 0.03; losers keep metrics, lose the artifact after 30 d.
- Params: `common.BASE_PARAMS` / `TUNE_SPACE`; no sklearn in the venv, metrics are scipy/numpy.

## Predict, evaluate, scorecard
- `predict_daily` (every name with 20-day value >= Rp 200 M, cut = bar close 16:00 WIB), `predict_intraday` (every live name at
  the last grid minute; target minute per horizon, none across the close).
- `evaluate` fills `realized_*`/`hit` once the horizon passed (intraday: mid at the target minute within 3 h; daily: the bar
  `steps` COMPOSITE trading days later, adj-factor consistent).
- `scorecard` = per horizon and 1/5/20/60-day window the realised hit rate vs the majority base, AUC, IC, MAE bps vs
  "no change".

## Scheduler, CLI, API
- Scheduler: `ml_daily` 20:40 Mon-Fri (evaluate -> train daily ~15-25 min -> predict -> scorecard -> purge),
  `ml_intraday_train` 16:30, `ml_intraday_predict` every minute in session (champions cached per process, reloaded when the
  registry ids change), `ml_evaluate` every 10 min.
- CLI `idx ml train [--kind daily|intraday|all] [--no-tune] [--horizons 1d,20d] | predict | eval | scorecard | status | show CODE | board [--horizon] | models`.
- API `GET /idx/ml/predictions/{code}`, `/idx/ml/board?horizon=&top=`, `/idx/ml/scorecard`.

## Forecasts, never tickets
- A 1-minute hit rate above base is worth less than the spread (menus 28-33), and the daily horizons must show a positive
  realised IC for months before any book reads them.
- **Menu 35 (study #178, 2026-09-25)** put a number on that for the 1d model: its biggest feature `bo_imb` (closing bid/offer
  volume imbalance) carries 15.4 % of the gain and 0.023 of the 0.136 daily rank IC, 5/5 years - real information (dropping it
  costs IC every year; a shuffled version does worse) - but trading the imbalance directly loses 45-83 bps a DAY net (gross
  close-to-close +29 %/yr, net -84 %/yr; K 10, LIQ, IDX costs).
- So the 1d IC is partly a spread the desk would have to pay: keep the feature, and never build a book on the 1d horizon.

## Second pass (same evening, migration 0038): purged blocks, excess labels, calibration, placebo
- Validation is K purged blocks (daily 3 x 40 d, intraday up to 3 x 1 d), each block's fit set cut `steps` trading days before
  the block (`common.blocks`, `purge_cut`; Lopez de Prado embargo), `primary` = mean over blocks and `primary_min` stored.
- The 20d/60d/120d/250d labels are EXCESS log return over the COMPOSITE (`Horizon.basis='excess'`, `ml_prediction.basis`;
  evaluate subtracts the index's return over the same window; the CLI/API say 'vs IHSG').
- Probabilities are calibrated per horizon by an isotonic curve fitted on the last 60 d of realised predictions
  (`common.isotonic` PAV, `idx.ml_calibration`, applied at predict time, `p_up_raw` kept; needs 400 realised rows and a
  non-flat curve; `idx ml calibrate`, run before every training in the scheduler).
- `idx ml train --placebo N` refits the refresh contender N times with labels shuffled within each day and stores the
  percentile of the real metric (`val_metrics.placebo`; slow, not nightly).

## Macro by RELEASE date (third pass)
- `daily.MACRO_RELEASE` / `release_date` re-date every reading to when it is known at the 16:00 WIB cut (BI-Rate same day; US
  close, Brent, gold, CPO, Yahoo FX = next day; FEDFUNDS / OECD monthly / BPS CPI = first business day of the next month; BPS
  GDP = quarter start +4 months +5 days).
- `id_cpi` -> `id_cpi_yoy` (log y/y; the OECD index stops 2025-04, so the feature is stale-but-honest), `id_gdp_qoq` added.
- `bi_rate` = RDG event rows on top of the OECD monthly history, with the 2024-01..2025-11 gap filled from the public RDG
  decisions (`idx.macro` rows source `manual-rdg`: 2024-04-24 6.25, 2024-09-18 6.00, 2025-01-15 5.75, 2025-05-21 5.50,
  2025-07-16 5.25, 2025-08-20 5.00, 2025-09-17 4.75).
- Tests `tests/idx/test_ml.py` (32).

## Macro source `bps` (LIVE 2026-09-25)
- `macro.fetch_bps` / `bps_find`, series `id_inflation_yoy` = BPS variable **2263** "Inflasi Tahunan (Y-on-Y) 38 Provinsi
  (2022=100)", national row (vervar 9999), monthly, 32 points 2024-01..2026-08 (3.19 % in Aug 2026); the App ID from
  webapi.bps.go.id is the `key` parameter (`INGEST_BPS_API_KEY` in idx-local.env).
- GOTCHAS: `model=var` needs `keyword=` to search; `model=th` rows carry `th`/`th_id` (not label/val); a datacontent key is
  vervar+var+turvar+th+turtahun (turtahun 13 = "Tahunan", a year figure, skipped).
- `daily.load_macro` converts it to the same `id_cpi_yoy` log y/y feature and prefers it over the OECD index on overlap - the two
  agree within 0.0-0.3 pp on their 16 common months - so the feature now runs to today instead of stalling at 2025-04.
- The nightly `run_macro` job pulls it with everything else. The macro table and its jobs: [DATA.md](DATA.md).

## `ret` / `dir` primary = per-cut metrics (fourth pass, 2026-09-25, menu ML-7 study #173)
- **`ret` primary = per-cut rank IC:** `common.cut_ic` / `metrics_for(..., cuts, mask)` - the mean Spearman WITHIN each cut (a
  day for the daily models over LIQ names = value60 >= Rp 5 bn & close >= 100, `loop._cuts`; a minute for the intraday ones,
  all names), its t (`ic_t`) and the cuts counted; the block-pooled Spearman is kept as `ic_pooled` (printed by
  `idx ml train`).
- Reason: the pooled number also rewards getting each day's LEVEL right, which a within-day name picker cannot monetise (ML-7:
  the two metrics disagreed by up to 0.06 on the same model).
- The realised scorecard's `ic` is the same per-cut mean (`loop._realised_ic`, grouped by `made_at`, pooled fallback when a cut
  is thinner than 20 rows).
- `dir` primary = the per-cut AUC likewise (`common.cut_auc`, `auc_pooled` kept; cuts with one class are skipped, pooled
  fallback).
- Champions registered before this date carry the pooled `ic` in `val_metrics`; the nightly loop re-scores them on the current
  blocks with the new metric before comparing.

## Seed ensemble
- `common.ENSEMBLE_SEEDS` = {('5d','ret'): 3} - `common.fit(..., n_seeds)` returns a `common.Ensemble` (boosters that differ by
  seed, predictions averaged, one artifact string joined by `ENS_SEP`; `Model.load` detects it).
- ML-7 (#173) found seed averaging never hurt and is worth ~+0.01 IC at 5d for 3x the fit time.

## Survivorship (checked 2026-09-25)
- idx.bar keeps 989 names; only 24 are dead (6 end 2020, 15 end 2025 - the July-2025 delisting batch), i.e. names delisted
  2021-2024 are largely ABSENT (history was backfilled from the current listing) - a modest upward bias in the 2020-24 training
  rows, mostly illiquid names below the LIQ floor; discount 120d/250d numbers, and backfilling the delisted names' bars from the
  IDX archive is the fix.

## Every forecast ends ok or void (migration 0063, 2026-09-27)
- `ml_prediction.realize_status` - `evaluate` sets 'ok' when it realises a row and 'void' when no price will come (intraday: no
  book/trade near the target 3 days later, `VOID_INTRADAY_DAYS`; daily: no bar 5 COMPOSITE sessions after the target,
  `VOID_DAILY_SESSIONS`; backstop 30 days past `target_at`).
- Void rows leave the realisation queue, which is `ORDER BY made_at LIMIT 50000`, so rows that can never be realised (feed gap,
  suspension, delisting) no longer eat the batch.
- Re-queue after a backfill: `UPDATE idx.ml_prediction SET realize_status = NULL WHERE realize_status = 'void'`.
- No retention policy exists on `ml_prediction` (a Timescale hypertable) - every forecast is kept.
- `loop.record` = forecasts next to actuals, one WIB day with a per-horizon tally (n / realised / void / pending / hit / MAE vs
  naive) or one code; CLI `idx ml record [CODE] [--as-of D] [--horizon H] [--top N]`, API
  `GET /idx/ml/record?day=&horizon=&code=&limit=`.

# Online learning agent (`idx/agent.py`, migrations 0042 `idx.agent_sample` / `idx.agent_decision` / `idx.agent_model` + 0043 `exit_at`, 2026-09-25)

Operator: "kalau untung dapet reward, kita kasih modal" -> trade the live feed and learn from each session.

## What it does
- PAPER ONLY, virtual Rp 20 M, Rp 2 M a position, <= 3 per decision, <= 10 open.
- Decision minutes Mon-Thu 09:15 10:00 11:00 13:45 14:30, Fri 09:15 10:00 11:00 14:15 14:45 (job `agent_decide`, every minute,
  acts once per decision minute).
- Actions (TP, stop, sessions held after entry): TP1 1/1/0, TP2 2/2/0, H1 3/3/1, H2 4/4/2, H5 6/5/5 (operator: "akhir hari ga
  harus menjual"); exit at the bracket or at the bid of the last grid minute of the last holding session; an overnight gap
  through the stop sells at the open.
- Fill model: offer at the decision minute + 0.10 %, TP when a later minute's high reaches it, stop one tick below (both in one
  minute = stop), 0.20 % sell fee, lots.

## The learner
- Full-feedback counterfactual samples (every feed name x decision minute x action, from the tape; a multi-day row is stored only
  once its holding time is over - early bracket hits alone would bias it)
- -> per-action Bayesian linear posterior (ridge 10, rewards clipped +-5 %) whose covariance is inflated by the SESSION design
  effect 1 + (m - 1) rho (same-day names share the market move: 4 sessions gave deff 47-90) and an action needs samples from
  >= 3 sessions;
- a name is bought only when the PESSIMISTIC reward (posterior mean - 1 sd) clears +0.3 %.
- (Thompson sampling was the first design and was dropped the same day: with full feedback, exploring buys no information, and
  the walk-forward replay showed it betting the book on a one-day-old action.)
- Features = ml/intraday.py minute features (same code path live and settled) + yesterday's broker tape (top-3 net-buy share,
  buyer HHI) + the desk's tools (intraday ML 10/30/60m P(up) at the minute, daily ML 1d/5d from the evening before, yesterday's
  stock_state, ARA p_lock).
- Placebo agent 'random' takes the same number of names at random.

## Jobs, CLI, state
- Job `agent_settle` 16:50: samples (today + matured multi-day of the last 7 sessions), paper fills of every open decision, refit.
- CLI `idx agent warmstart [--resample]|settle [--date]|decide|report`.
- State 2026-09-25: model #5 on 6,683 samples; unconditional mean reward -1.3 % for every action; replay 09-23..25 -> no trade
  (best lower bound -2.5 %). Expect weeks of abstaining before the evidence supports a trade.

## Judgement rule (binding for any move to real money)
- **JUDGEMENT RULE (declared 2026-09-25, before any live decision): after >= 20 settled sessions and >= 30 ts trades, the agent
  is a candidate for real capital only if ALL: its cumulative paper P&L > 0; its mean reward per trade beats the random agent's
  by >= 0.5 pp; the t-stat of the daily P&L difference (ts - random, sessions with trades) >= 2; positive P&L on >= 60 % of its
  trading sessions. Otherwise it stays paper.**
- **REVISED 2026-09-27 (before the first live decision): that rule had 9-32 % power for a +0.5 pp edge at 20 sessions. Now: Wald
  SPRT on per-session (ts - random) mean reward over sessions where both traded, H0 0 vs H1 +1.0 pp, sd 3.28 pp (warm-start
  paired difference), alpha 0.05 / beta 0.20 (~60 paired sessions if real, ~34 if not); candidate = H1 accepted AND cumulative
  paper P&L > 0 (`agent.judge`, in `idx agent report`).**
- Real money is the operator's call and goes through draft tickets.
