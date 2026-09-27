# Independent replication of the trend and ML sleeves - 2026-09-26

Track A6 (operator "okay do track A"). As for the gap-fade (IDX_REPLICATION_GAPFADE_2026-09-26.md): one agent per sleeve
re-implemented the rule from a written specification only - no access to `research/` or the ingest source - and compared its
trade list with the stored backtest #386. Code and CSVs: `research-scratch/replication/trend/`, `research-scratch/replication/ml/`.

## Trend (strategy trend_small, 279 stored trades): REPRODUCES

| | replication | stored |
|---|---|---|
| trades | 282 | 279 |
| mean / median net | +4.53 % / -4.64 % | +4.52 % / -4.69 % |
| hit | 42.2 % | 41.9 % |

All 279 stored trades matched: entry and exit dates and prices identical, net return equal to 1e-16. The 3 extra trades are
names whose one lot cost more than a slot (AALI, BYAN, DSSA) - the book's lot rule. Two rules the specification left out were
needed for an exact match, neither a look-ahead: a slot counts as free at the close where the exit signal fires (the sale and
the new buy are worked the same next session), and the lot-size skip. The agent flagged: buying at the next session's closing
offer is optimistic but uses no future information; back-adjusted prices do not leak (all signals are within-window ratios).

## ML (strategy ml_rank, 876 stored rule-trades in four legs): REPRODUCES

| leg | replication | stored | matched | only stored |
|---|---|---|---|---|
| +5/10 | 308 | 279 | 279 | 0 |
| +8/10 | 237 | 215 | 215 | 0 |
| +10/10 | 204 | 172 | 172 | 0 |
| +8/5 | 249 | 210 | 210 | 0 |

Every stored trade matched with the same entry, exit and exit reason; returns agree to 1e-4 at the 90th percentile. The extra
replication trades are signals the rupiah book skipped for cash (expensive lots: BREN, CUAN, TPIA, PANI, AADI, MCOL; crowded days
when the 30 % cash floor binds); they average +1.5..+5.4 %, so the skips cost little. Look-ahead checks: the "trades tomorrow"
candidate condition never binds (0 of 208,023 liquid scored name-days lack a next-day row; an identical list without it); the
same-close stop assumes a market-on-close sale (mildly optimistic); the cache's `liq` flag and score were taken as given.

## Verdict across the three sleeves

Trend and ML reproduce exactly. The gap-fade reproduced only after two look-aheads were removed (#386 supersedes #348). The
backtest engine is now independently confirmed for every live sleeve.
