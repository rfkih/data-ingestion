# IDX menu 29c — a take-profit on the gap-fade, or just the close? — 2023-02-01 -> 2026-09-14

266 events, 115 names, 109 days (menu 29b's g7 population: IDX opens, gap <= -7 %, liquid, no corporate action). Entry unchanged: the open plus a tick. Pre-registered in `research/idx_gapfade_exit.py`; 9 trials (cumulative 544).

## What the day does after the open

- the high reaches +2 % on 91 % of days, +3 % on 86 %, +5 % on 72 %
- the low reaches -3 % on 39 % of days, -5 % on 23 %
- mean high +1130 bps above the open, mean low -280 bps below it

## Exits

| exit | trades | hit | mean | median | vs close | t (paired) | verdict |
|---|---|---|---|---|---|---|---|
| close (deployed) | 266 | 54 % | **+298** | +58 | — | — | reference |
| tp2 | 266 | 86 % | **+25** | +89 | -273 | -4.4 | no |
| tp3 | 266 | 85 % | **+83** | +183 | -215 | -3.5 | no |
| tp5 | 266 | 75 % | **+159** | +363 | -139 | -2.4 | no |
| sl3 | 266 | 41 % | **+189** | -116 | -109 | -3.2 | no |
| sl5 | 266 | 49 % | **+251** | -30 | -47 | -1.8 | no |
| tp3_sl3 | 266 | 57 % | **-80** | +143 | -378 | -6.3 | no |
| tp5_sl5 | 266 | 64 % | **+52** | +351 | -246 | -4.4 | no |
| trail_half | 266 | 67 % | **+190** | +115 | -107 | -3.5 | no |

## The brackets, read both ways (the bar uses the pessimistic one)

| bracket | ambiguous days | pessimistic vs close | optimistic vs close |
|---|---|---|---|
| tp3_sl3 | 28 % | -378 bps | -197 bps |
| tp5_sl5 | 11 % | -246 bps | -133 bps |

## Reading

- Beat the close: none.
- A target caps the right tail, which is where this rule's money is; a stop turns the deepest intraday dip into a
  realised loss on a day that often closes higher. The table says which of those costs more.
