# IDX — A standing cash buffer and a stress detector that raises it (2026-09-14)

**The operator's rule.** Hold 30 % cash at all times in case of a crash; when the market turns bad, raise cash to 50 %.

**Verdict.** Built as a book option (`cash_floor_pct`, `stress_cash_pct`, `stress_rule`), off by default. The buffer does
what a buffer does: on the strict book 2021–2026 the constant 30 % takes the return from 18.3 % to 14.2 % a year, the
worst drawdown from 26 % to 18 %, and the Sharpe up in all four calendars. The detector on top (30 % → 50 % while the
COMPOSITE is under its 200-day average) takes a further point of return (13.4 %) for a further three points of drawdown
(15 %) and the shallowest 2025 dip of any arm (−9…−10 % against −17…−20 %). From 2008 on the 100-name basket the same
rule holds the drawdown to 32 % against 56 %, 2008 −28 %, 2020 −28 %. It misses the pre-registered return floor (75 % of
the rule) by two points, so it is not the default; the four detector signals behave alike, and none of them is news or
sentiment, which the desk does not have. What the detector adds over the plain buffer is modest and real; what the
buffer costs is about a quarter of the return.

## Pre-registered menu (7 trials; cumulative 162)

Exposure = the fraction of the book in the list, the rest in cash at 4 %/yr, re-set at every monthly check (every arm,
the reference included, is the list re-weighted monthly). Signals read at the check from data up to that day:

| Signal | Definition |
|---|---|
| ma | the COMPOSITE closes under its 200-day average |
| vol | the COMPOSITE's 20-day realised volatility is above the 80th percentile of its trailing three years |
| dd | the COMPOSITE is more than 10 % under its 252-day high |
| breadth | fewer than 40 % of the names with a 200-bar history close above their own 200-day average |
| any2 | at least two of the four |

Arms: full (1.00 always), cash30 (0.70 always), ma / vol / dd / breadth / any2 (0.70 normally, 0.50 while on),
detector_only (1.00 normally, 0.50 while any2 is on), regime (1.00 / 0.00 on ma, the existing crash filter). Part A the
strict book 2021–2026, four calendars, rev. 3 simulator, real costs, dividends net of tax. Part B the 100-name liquid
basket 2008–2026 (Yahoo cache, survivors), May calendar, price returns. Script `research/idx_cash_buffer.py`; outputs
`research-scratch/idx-screen/cash_buffer_out.txt`, `cash_buffer_results.json`.

Reading rule, written before the run: worth building only if Sharpe beats full's in three of four calendars, the worst
drawdown is at least 5 points shallower, CAGR is at least 75 % of full's, and on the 2008 basket the max drawdown is
40 % or less with 2008 and 2020 no worse than −30 %.

## Part A — the strict book (CAGR · Sharpe · max drawdown; the Jan–Apr 2025 dip in brackets)

| Arm | May | Feb | Aug | Nov | avg CAGR | worst mDD |
|---|---|---|---|---|---|---|
| full (the rule) | 18.7 · 0.98 · 23 % (−17) | 21.9 · 1.11 · 21 % (−18) | 18.0 · 0.96 · 26 % (−20) | 14.5 · 0.83 · 25 % (−19) | **18.3** | 26 % |
| cash30 | 14.5 · 1.11 · 16 % (−13) | 16.8 · 1.24 · 15 % (−13) | 14.0 · 1.09 · 18 % (−14) | 11.6 · 0.96 · 18 % (−14) | 14.2 | 18 % |
| **ma: 30 → 50** | 13.6 · 1.17 · 15 % (−10) | 15.2 · 1.25 · 12 % (−9) | 13.7 · 1.19 · 14 % (−10) | 11.2 · 1.05 · 14 % (−10) | **13.4** | **15 %** |
| vol: 30 → 50 | 13.7 · 1.15 · 16 % | 15.3 · 1.23 · 12 % | 13.3 · 1.13 · 16 % | 10.8 · 0.99 · 15 % | 13.3 | 16 % |
| dd: 30 → 50 | 12.9 · 1.08 · 16 % | 15.4 · 1.23 · 12 % | 13.1 · 1.11 · 16 % | 10.5 · 0.97 · 15 % | 13.0 | 16 % |
| breadth: 30 → 50 | 13.1 · 1.23 · 13 % | 14.3 · 1.27 · 12 % | 12.3 · 1.18 · 14 % | 10.5 · 1.09 · 14 % | 12.6 | 14 % |
| any2: 30 → 50 | 13.2 · 1.16 · 15 % | 14.6 · 1.23 · 12 % | 13.2 · 1.18 · 14 % | 10.6 · 1.03 · 14 % | 12.9 | 15 % |
| detector only: 100 → 50 | 15.4 · 1.04 · 22 % (−10) | 16.5 · 1.06 · 18 % (−9) | 16.0 · 1.09 · 17 % (−10) | 12.2 · 0.92 · 19 % (−10) | 15.0 | 22 % |
| regime: 100 → 0 | 13.9 · 0.96 · 22 % (−1) | 13.8 · 0.92 · 20 % (−1) | 16.2 · 1.13 · 14 % (−1) | 11.9 · 0.94 · 20 % (−1) | 14.0 | 22 % |

Signal on-time on this window: ma 34–39 %, vol 23–26 %, dd 21–24 %, breadth 61–69 %, any2 41–47 %.

## Part B — 2008–2026 basket (CAGR · Sharpe · max drawdown; episode drawdowns)

| Arm | CAGR | Sharpe | mDD | 2008 | 2011 | 2015 | 2018 | 2020 | 2022 | 2025 |
|---|---|---|---|---|---|---|---|---|---|---|
| full | 10.2 | 0.49 | 56 % | −48 | −25 | −32 | −25 | −47 | −14 | −20 |
| cash30 | 8.9 | 0.61 | 41 % | −37 | −18 | −23 | −17 | −35 | −10 | −14 |
| **ma: 30 → 50** | 9.1 | 0.73 | **32 %** | **−28** | −18 | −18 | −14 | **−28** | −10 | −10 |
| any2: 30 → 50 | 8.8 | 0.72 | 32 % | −28 | −18 | −18 | −14 | −28 | −10 | −10 |
| detector only | 10.1 | 0.65 | 38 % | −28 | −24 | −21 | −17 | −31 | −14 | −10 |
| regime: 100 → 0 | 10.7 | 0.76 | 25 % | 0 | −23 | −9 | −11 | −13 | −14 | 0 |

## Verdicts

| Arm | CAGR as % of full | Sharpe wins | worst mDD | 2008 basket mDD | 2008 / 2020 | Verdict |
|---|---|---|---|---|---|---|
| cash30 | 78 % | 4/4 | 18 % | 41 % | −37 / −35 | fails the crash clause |
| ma 30 → 50 | 73 % | 4/4 | 15 % | 32 % | −28 / −28 | fails the return floor by 2 points |
| vol / dd / breadth / any2 | 69–73 % | 4/4 | 14–16 % | 32–34 % | −28…−32 / −26…−29 | same |
| detector only | 82 % | 3/4 | 22 % | 38 % | −28 / −31 | drawdown clause by 1 point, 2020 by 1 point |
| regime | 76 % | 2/4 | 22 % | 25 % | 0 / −13 | Sharpe clause |

Nothing passes by the letter; the ma buffer and the detector-only arm are the near misses, from opposite sides.

## Reading

1. **The buffer is the strategy; the detector is the trim.** Going from 100 % to 70 % invested does most of the work
   (drawdown 26 → 18, Sharpe up everywhere). Raising to 50 % on a signal buys 1–3 more points of drawdown for about a
   point of return. The signals are interchangeable because they fire together; breadth fires most of the time on this
   window (61–69 %) and is therefore the most expensive.
2. **Compared with the binary crash filter.** The graded buffer has the smoother normal years (worst 12–15 % against
   20–22 %) while the filter has the better crashes (2008: 0 against −28 %). They are different insurance policies: the
   buffer pays every year and covers every kind of dip; the filter pays only in trend breaks and covers the big ones.
3. **"Bad news" is not measurable on the desk.** There is no news ingest and no sentiment score; the detector reads
   prices and breadth. When a news feed exists, a sentiment signal can be added as a fifth input to `any2`.
4. **Today's reading (2026-09-11 close):** COMPOSITE under its MA200, 28 % under its 52-week high, breadth 33 %,
   volatility normal: 3 of 4 signals on. A book set to 30 % / 50 % would hold 50 % cash now.

## What was built

- Migration 0016: `idx.book.cash_floor_pct`, `stress_cash_pct`, `stress_rule` (ma | any2); `idx.stress_check` (one row per
  monthly check with the four signals and their inputs).
- `overlay.py`: `stress_from_series` (pure), `stress_signals`, `breadth_asof`, `stress_on`, `cash_target` (pure), record /
  latest / history; the monthly check records the signals and issues a rebalance ticket at the new target when it
  moves 5+ points. `ticket.build` uses the target as the plan's cash reserve, so every rebalance honours it.
- API: `/idx/overlay` carries `stress` and `stress_history`; book PUT accepts the three fields. CLI: `idx book set
  --cash-floor --stress-cash --stress-rule`; `idx overlay status` prints the stress read. Catalog `overlay:cash_buffer` with
  the ma record. Papan: three fields on the book page, the stress read in the overlay status.
