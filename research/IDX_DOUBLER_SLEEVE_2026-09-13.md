# IDX — Can the doublers be bought? Sleeve, signals, acceleration, cadence (2026-09-13)

Follow-up to `IDX_MULTIBAGGER_2026-09-13.md`. The operator asked for research that finds such names, and suggested
accumulation, foreign flow, news sentiment, and the financial statements as the places to look.

**Verdict.** A basket built on the doubler profile loses money after costs (−3 %, −41 %, −16 % over four years in the
three calendar offsets, drawdowns above 60 %). Of the signals the operator named, one is real and untestable at length,
one is mild, one is noise, and one has no data:

- **Financial statements, yes.** Names whose TTM earnings run-rate is more than double the last audited year reached 2×
  within twelve months 47 % of the time with a *positive median* return (+41 %), the only doubler signal that is not a
  lottery ticket. But quarterly reports exist in the database only from 2024, so every test of it covers 2.3 years of a
  rising market; as a filter on the deployed list it removed names in two quarters out of ten and changed nothing.
- **Accumulation, mildly.** On-balance-volume balance and volume surges tilt the odds smoothly (7.6 % → 16.9 % across
  quintiles); ownership filings and exchange queries mark attention, which comes with a fat left tail.
- **Foreign flow, no.** Flat across quintiles at 5 and 20 days, as in every earlier test.
- **News sentiment, no data.** `idx.news_article` is empty and no news has been scored; this needs an ingest first.

The one thing that looked like an edge, the strict list refreshed quarterly, turned out on the full window to match the
annual rebalance exactly on average (18.9 % against 18.8 %) with twice the trades. The annual cadence stays.

## 1. The v2 signals (hit rate of a 12-month double, by quintile, pooled 2021–2025)

| Signal | Q1 (lowest) | Q2 | Q3 | Q4 | Q5 (highest) |
|---|---|---|---|---|---|
| TTM earnings vs audited year (accel) | 16.7 % | 5.6 | 3.6 | 6.9 | **26.9 %** |
| ownership filings, 30 days | 12.9 | 6.5 | 3.9 | 12.1 | **28.0 %** |
| exchange queries (UMA), 10 days | 12.9 | 6.5 | 3.8 | 10.8 | **29.4 %** |
| OBV balance, 60 days | 7.6 | 10.4 | 13.0 | 15.5 | **16.9 %** |
| volume 20d / 120d | 11.8 | 10.8 | 11.9 | 12.3 | 16.6 % |
| foreign net share, 5 days | 8.9 | 14.0 | 15.6 | 15.4 | 9.5 % |
| foreign net share, 20 days | 9.4 | 12.8 | 15.9 | 14.5 | 10.8 % |

| TTM run-rate vs audited year | Reaches 2× | Mean 12-month | Median | n |
|---|---|---|---|---|
| under −30 % | 35.2 % | +57 % | +10 % | 159 |
| within ±30 % (includes every pre-2024 row, where accel is 0 by construction) | 10.1 % | +4 % | −9 % | 5,836 |
| +30 % to +100 % | 32.3 % | +40 % | 0 % | 167 |
| **over +100 %** | **46.6 %** | **+98 %** | **+41 %** | 103 |

Flags: latest quarter a YTD loss → 31 % double (n=103); YTD profit down more than 50 % → 28 % (n=212); quiet accumulation
(flat three months, volume ×1.5) → 14 % against 13 %. The loss and collapse flags mark speculative turnarounds: high hit
rate, wide dispersion.

Model v2 (all features, LightGBM, walk-forward with a 12-month purge): AUC 0.55 / 0.66 / 0.70 for 2023 / 2024 / 2025,
top-decile lift 1.3× / 2.0× / 1.8×; still under the pre-registered 2× bar in every year.

## 2. The sleeve test (20 names, quarterly, three offsets, 2022-07 → 2026-09; script `idx_doubler_sleeve.py`)

| Arm | Offset 0 | Offset 1 | Offset 2 | Worst mDD | Picked names' 12-month: mean / median / P(< −50 %) |
|---|---|---|---|---|---|
| universe, equal weight | +14 % | −6 % | −1 % | 46 % | +7…14 % / −7…−11 % / 7…9 % |
| doubler profile (rules20) | −3 % | −41 % | −16 % | 63 % | +22…35 % / −11…−13 % / 17…18 % |
| profile, audited growth only | −6 % | −29 % | −22 % | 63 % | +18…26 % / −4…−16 % / 13…15 % |
| profile within the cheap half | +61 % | +49 % | +70 % | 45 % | +32…42 % / −4…−6 % / 3…4 % |
| profile with foreign flow + filings | +21 % | +24 % | +62 % | 58 % | +29…43 % / −4…+4 % / 4…7 % |
| model v2 top twenty | +17 % | +9 % | +57 % | 50 % | +26…36 % / −6…−9 % / 11…13 % |
| profile with earnings acceleration ¹ | +53 % | +136 % | +67 % | 61 % | +57…82 % / +10…+23 % / 3…5 % |
| strict composite, annual May (reference from 2023-05) | +57 % | | | 22 % | |

¹ Starts 2024-05/06/07 only (no quarterly data before), so its window is the 2024–2026 rally and is not comparable.

Reading rule (beats the universe in all offsets, the strict composite in two, worst drawdown ≤ 35 %): nothing passes.
The doubler profile as a strategy is a loser; adding cheapness makes it a worse version of the value book; the
acceleration arm is the only one whose picked names have a positive median, and it has no history to speak of.

## 3. Acceleration on its own and as a filter (script `idx_accel.py`)

| Arm (quarterly, three offsets) | From | CAGR | Sharpe | Worst mDD | Names |
|---|---|---|---|---|---|
| accel ≥ 30 %, all liquid names | 2024-05 | 19 / 39 / 24 % | 0.45–0.94 | 56 % | 19–23 |
| accel ≥ 30 %, light gate | 2024-05 | 34 / 64 / 39 % | 0.68–1.35 | 53 % | 9–12 |
| accel ≥ 30 %, strict gate | 2024-08 | 4 / 41 / 26 % | 0.09–0.83 | 66 % | 4–6 |
| strict list quarterly, minus decelerating names | 2022-07 | 18.6 / 13.7 / 17.0 % | 0.74–0.96 | 27 % | 11 |
| **control: strict list quarterly, no filter** | 2022-07 | 18.8 / 13.3 / 16.3 % | 0.71–0.97 | 26 % | 12 |
| strict composite, annual May | 2022-07 | 14.3 % | 0.76 | 22 % | 12 |

The three acceleration-only arms have 2.3 years of history in a rising market and drawdowns above 50 %: tested, not
adoptable. The filtered list passed the pre-registered bar, but the control shows why: it is the quarterly refresh, not
the filter. Over 2024-05 onward, the only window in which the filter is active, it removed names in two quarters of ten
and moved the result by −0.7 / +2.4 / +4.0 points. Filter credited in 2 of 3 offsets by the letter; in substance, nothing.

## 4. Refresh cadence, pre-registered confirmation (script `idx_refresh_cadence.py`, 2021-05 → 2026-09)

| Cadence | Offsets (CAGR) | Mean CAGR | Worst offset | Mean Sharpe | Worst mDD | Name changes a year |
|---|---|---|---|---|---|---|
| annual (deployed) | May 18.3, Feb 28.1, Aug 18.5, Nov 10.1 | **18.8 %** | 10.1 % | 0.99 | 27 % | 14 |
| semiannual | May/Nov 14.9, Feb/Aug 16.7 | 15.8 % | 14.9 % | 0.85 | 26 % | 21 |
| quarterly | 17.1, 19.3, 20.3 | **18.9 %** | 17.1 % | 0.98 | 26 % | 32 |

Reading rule (mean CAGR at least 2 points above annual, worst drawdown within 5 points): neither passes. **Annual stays.**
What quarterly does buy is a narrower spread across offsets (17–20 % instead of 10–28 %): less calendar luck, at twice the
trades. The earlier "quarterly beats annual" came from a window that started in July 2022 and compared against the May
calendar alone.

## What this thread settles

1. The doublers cannot be bought as a class. Their profile is a lottery ticket and a basket of them loses after costs.
2. The one signal with a decent median, earnings acceleration from the quarterly statements, deserves history: download
   the 2021–2023 quarterly workbooks (about 4,000 files) and re-run `idx_accel.py`; until then it is a card fact, not a
   rule. News sentiment needs a news ingest before it can even be looked at.
3. The strict composite, annual, remains the book. Its own doublers are the earnings-led and loss-to-profit names bought
   cheap, and that is the only way this market's doublings have been owned with a positive median.
4. Trials counted this session: 124.
