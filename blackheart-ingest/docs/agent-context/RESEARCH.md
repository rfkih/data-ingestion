# Research - study store, evidence, the analysis pack, the C1 forward paper watch, study index

Read when you record or read a study (`idx.study`), add evidence to a name, build or import the analysis pack, score pack
answers, touch the C1 forward paper watch (`idx/dt_watch.py`), or need to find where a study/menu number is described.
Map: [../../CLAUDE.md](../../CLAUDE.md).

**Before changing any live parameter or quoting a strategy number, read [../MODEL_INVENTORY.md](../MODEL_INVENTORY.md)**: the live
models, their reference study (#386), validation status, known limitations and the binding change-control rule (pre-registered
study + independent spec-only replication + journal; combo books frozen to 2027-03-26). Pinned study inputs:
`python -m blackheart_ingest.idx.snapshot verify|drift <study>` ([OPS.md](OPS.md)).

## Research store (`idx/research_store.py`, migration 0020 `idx.study` / `idx.study_name` / `idx.evidence`, 2026-09-17)
- Research results as rows. A study run (`record_study`: name, as_of, params, summary, the names it surfaced with their
  figures, screens, score, rank and the screens' historical hit rates).
- Evidence per name (`add_evidence`: kind news | announcement | annual | web | analyst | note, deduplicated on (code, kind,
  url, title); `collect_evidence` pulls material disclosures, press items and the annual-report plan sections the data plane
  already holds).
- `name_view` assembles one name: studies that flag it, evidence by kind, pack answers, consensus, latest candidate row.
- CLI `idx study list|show [--name N|--id I]|name CODE`, `idx evidence collect CODE[,CODE] [--days N] [--study I] | add CODE
  --kind K --title T [--url --summary --tags --ts] | show CODE`.
- API `GET /idx/study?name=`, `/idx/study/latest?name=`, `/idx/study/{id}`, `/idx/name/{code}`, `POST /idx/name/{code}/evidence`.
- `research/idx_doublers.py --store` writes its run (study `doublers`).
- The registry imports its scorecard from the newest `roi_scorecard` study: [STRATEGIES.md](STRATEGIES.md).

## Analysis pack (manual Claude chat, no API)
- `idx pack` → `idx/pack.py` builds one markdown (pinned prompt `pack_v1` + market + candidate table + a compact section per
  name: valuation, gates, 4 quarters + 3 FY, flow, disclosures since the previous pack) for selected candidates + next 10 +
  `idx.watchlist`; stored in `idx.nightly_pack` and written to `research-scratch/idx-pack/<date>/pack.md` (~13k tokens for 32
  names).
- The operator pastes it into Claude chat and saves the JSON block; `idx pack-import answer.json` validates (codes must be in
  the pack, stance buy|hold|avoid|sell, conviction 1-5, veto needs a reason) and writes `idx.sentiment_score` rows
  (`doc_type='pack'`, `model='claude-chat-manual'`) + `nightly_pack.answer_json`.
- `idx answers`, `idx watch list|add|rm`.
- `idx answers --score` = forward returns per pack stance / veto vs COMPOSITE (21/63/126/252 trading days).
- Routes: `GET /idx/pack/latest|{date}`, `POST /idx/pack/build`, `POST /idx/pack/{date}/answer`, `GET /idx/answers`,
  `GET|PUT /idx/watchlist`.
- Pack build/answer is a research write: `service_only` ([ARCHITECTURE.md](ARCHITECTURE.md)).

## C1 forward paper watch (`idx/dt_watch.py`, migration 0059 `idx.dt_watch`, 2026-09-27)
- Research rule C1 from menu DT-3 (#398): at 16:20 WIB (`dt_watch_pick`) the top 5 eligible feed-list names by prev close ->
  15:49 return (first hour also up, not at the upper band) that WOULD be bought in the closing auction and sold at the next
  opening auction, plus 5 date-seeded random names as placebo.
- `dt_watch_settle` 20:45 fills prices from `daily_summary` (net at 0.15/0.25 and 0.10/0.20 fees + 5 bps impact). Prints from
  `feed_bar_1m`, names the feed lacks from Yahoo hourly.
- No orders, no pushes.
- **Judgement rule (revised 2026-09-27, before the first row; the first cut had 6 % power):** Wald SPRT on the daily SELECTION
  edge d = pick gross - eligible-universe gross (one `kind='universe'` row per session, migration 0060), H0 0 vs H1 +27.5 bps,
  sd 153 bps (the 2025+ backtest sessions; review 2026-09-27), alpha 0.05 / beta 0.20, first 500 sessions only (bootstrap: true
  edge accepted 80 %, median 101 sessions; zero edge rejected 97 %, median 84); the universe list is frozen at pick (migration
  0061); candidate = H1 accepted AND live mean net at 0.10/0.20 % fees > 0; a real-money pilot is the operator's call.
- CLI `idx dtwatch pick|settle [--date D] | report`. Tests `tests/idx/test_dt_watch.py`.

## Where each study / menu number is described
| study / menu | subject | file |
|---|---|---|
| #56, #57, #101 (menus 16, ML-3, 34) | ARA watch, touch outcomes | [ARA.md](ARA.md) |
| #74 | queue-imbalance lead ~half a tick vs ~79 bps round trip | [ARCHITECTURE.md](ARCHITECTURE.md) (chart) |
| #131 | breakout-vs-accumulation, waits on broker history | [FEED.md](FEED.md) |
| #166-#168 | combined-book rupiah backtest | [BOOKS_TICKETS.md](BOOKS_TICKETS.md) |
| menu 34 #177 | combo cash floor | [BOOKS_TICKETS.md](BOOKS_TICKETS.md) |
| ML-8 #175 | ens4 confirmation rules | [BOOKS_TICKETS.md](BOOKS_TICKETS.md) |
| ML-7 #173 | per-cut IC, seed ensemble | [ML.md](ML.md) |
| menu 35 #178 | `bo_imb` / 1d horizon | [ML.md](ML.md) |
| menus 28-33, menu 28 | 1-minute hit rate vs spread, queue-imbalance lead | [ML.md](ML.md) |
| menu 29b | gap-fade book | [BOOKS_TICKETS.md](BOOKS_TICKETS.md) |
| DT-3 #398 | C1 forward paper watch | this file |
| #386 | reference study of the live models | [../MODEL_INVENTORY.md](../MODEL_INVENTORY.md) |

## Research notes cited by these docs
`research/IDX_VALUE_QUALITY_2026-09-12.md`, `research/IDX_REVIEW_2026-09-12.md`, `research/IDX_TREND_OVERLAY_2026-09-13.md`,
`research/IDX_SELL_RULES_2026-09-13.md`, `research/IDX_ASYMMETRIC_2026-09-13.md`, `research/IDX_CASH_BUFFER_2026-09-14.md`,
`research/IDX_REGIME_VALIDATE_2026-09-22.md`, `IDX_ROBUSTNESS_SCORECARD_2026-09-22.md` ([STRATEGIES.md](STRATEGIES.md));
`research/IDX_MACRO_STRESS_2026-09-14.md` ([DATA.md](DATA.md)); scripts `research/idx_value_quality.py`, `research/idx_top10.py`,
`research/idx_execution_delay.py` ([STRATEGIES.md](STRATEGIES.md)), `research/idx_combo_rupiah.py`
([BOOKS_TICKETS.md](BOOKS_TICKETS.md)), `research/idx_ohlc_loader.py` ([DATA.md](DATA.md)), `research/idx_book.py`
([BOOKS_TICKETS.md](BOOKS_TICKETS.md)), `research/idx_doublers.py` (above).
