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

## The tails: what a stop buys and what a target gives up

| exit | worst trade | p1 | p5 | mean | losses > 5 % | losses > 10 % |
|---|---|---|---|---|---|---|
| close (no stop) | **-2,302 bps** | -1,574 | -838 | **+298** | 17.3 % | 3.0 % |
| stop -5 % | -889 | -781 | -705 | +251 | 25.6 % | **0 %** |
| stop -3 % | -718 | -647 | -546 | +189 | 8.6 % | 0 % |

| exit | p75 | p95 | p99 | best trade | gains > 5 % |
|---|---|---|---|---|---|
| close | +596 | +2,816 | +3,986 | **+5,043 bps** | 27.1 % |
| target +3 % | +213 | +235 | +248 | +266 | 0 % |
| target +5 % | +405 | +428 | +436 | +463 | 0 % |

Sleeve as it would be run (5 slots): close **+207 %, max drawdown -13.3 %, Sharpe 4.50**; with a -5 % stop **+157 %,
-8.0 %, 4.13**.

## Verdict written after the run

**0 of 8. The close is the exit.** Both halves of the intuition are real and both cost money:

- a **target** lifts the hit rate from 54 % to 85-86 % and more than triples the median (+58 -> +183 bps at +3 %) - and
  destroys the mean, +298 -> +83. The day's high reaches +3 % on 86 % of these events, so a target is almost always
  filled; what it fills away is the 27 % of days that gain more than 5 % and the tail out to +50 %, which is the entire
  edge. This is the same shape menu 13 found on the trend book: capping the right tail of a fat-tailed rule is expensive.
- a **stop** is the honest trade-off, not a free lunch. -5 % turns a -23 % worst trade into -8.9 % and removes every
  loss beyond 10 %, and it cuts the sleeve's drawdown from -13.3 % to -8.0 %; it costs 47 bps a trade (t -1.8, i.e. not
  even clearly worse) and 50 points of total return. It also *raises* the share of losing trades from 17 % to 26 %,
  because 39 % of these days dip 3 % or more below the open before closing higher.

So: no target. A -5 % stop is a defensible risk preference - it fails the return bar but not decisively, and it buys a
materially smaller tail - but it is a preference, not an improvement, and the deployed rule stays "sell into the close".
Caveat: a daily bar says whether a level was touched, not when; targets are read optimistically (a touch counts as a
fill), which flatters them, and they still lose.

## A trailing stop cannot be decided from a daily bar — only bounded (descriptive, not a trial)

A trail needs the ORDER of the day: the running high, then the fall from it. A daily bar carries the high and the low but
not which came first, and on **28 % of these events the day both dips 3 % below the open and rises 3 % above it**, so the
order genuinely decides the outcome. The two possible orders bound it (net bps per trade, against +298 for the close):

| trail | high first: fires | mean | vs close | low first: fires | mean | vs close |
|---|---|---|---|---|---|---|
| 2 % | 99 % | +726 | **+429** | 47 % | +155 | -142 |
| 3 % | 97 % | +620 | **+322** | 39 % | +189 | -109 |
| 5 % | 89 % | +427 | **+129** | 23 % | +251 | -47 |
| 8 % | 72 % | +198 | -100 | 5 % | +288 | -10 |

"High first" is the trail at its best: it locks in near the top of a day that later gives the gain back. "Low first" is
the trail at its worst: before any high exists the trail IS a fixed stop at -x from the open, which is the arm already
measured above. The truth lies between, event by event, and the spread is enormous (+429 to -142 bps at 2 %) — which is
precisely why it cannot be called from daily data. Nothing here is a trial and nothing here may be adopted.

What would settle it: the tick feed. It records every print, so once the archive holds gap-down events with their minute
paths the trail can be walked exactly — the same data that settles menu 28b. Roughly 4 events per active day and about one
active day in four, so a usable sample (>= 40 events) is a few months away, not weeks; a first read is worth taking at 20
events with the caveat attached.

## A target at ARA, the ceiling itself (operator, 2026-09-23: "kalau TP di ARA gimana?")

Different in kind from a fixed target: it does not cap the tail, it harvests its very end. Auto-rejection sits 20-35 %
above the PREVIOUS close depending on the price band, which after a 7-12 % gap down is on average **49 % above the entry**.

- the day's high reaches ARA on **5 of 266 events (1.9 %)**: SAPX 2024-12-19, IOTF 2025-07-09, JARR 2025-10-22,
  FILM 2025-12-29, GTSI 2026-02-03 — all of them reversals of 29-55 % from the open in a single day
- on **four of those five the stock closed locked AT ARA**, so selling there and holding to the close are the same price;
  only FILM fell back (-2.7 % off the ceiling)
- over the whole population: **+299 bps against +298 for the close, i.e. +1 bps, t +1.00**

So a resting sell at ARA is **free but idle**: it costs nothing measurable and earns nothing measurable, and it pays only
in the one case in 266 where a name spikes to the ceiling and slides back before the close. Two neighbours, for the
record: a target half way from the open to ARA fires on 12 % of days and loses 35 bps; three quarters of the way fires on
7 % and gains 29 bps — both inside the noise and under the +50 bps bar.

## The whole stop ladder (operator, 2026-09-23: "stop loss at least di 10 persen")

| stop | fires | mean bps | vs close | t | worst trade | losses > 10 % | win | sleeve | max DD | Sharpe |
|---|---|---|---|---|---|---|---|---|---|---|
| none | — | **+298** | — | — | **-23.0 %** | 3.0 % | 54 % | +207 % | -13.3 % | 4.50 |
| -3 % | 39 % | +189 | -109 | -3.2 | -7.2 % | 0 % | 41 % | +118 % | -6.6 % | 4.01 |
| -5 % | 23 % | +251 | -47 | -1.8 | -8.9 % | 0 % | 49 % | +157 % | -8.0 % | 4.13 |
| -6 % | 17 % | +255 | -43 | -1.7 | -9.0 % | 0 % | 50 % | +163 % | -8.7 % | 4.09 |
| **-7 %** | 8 % | **+280** | **-17** | -0.8 | **-10.3 %** | 0.4 % | 52 % | +187 % | -9.4 % | 4.36 |
| -8 % | 5 % | +288 | -10 | -0.5 | -10.8 % | 2.6 % | 53 % | +193 % | -10.1 % | 4.40 |
| **-10 %** | **3 %** | +285 | -12 | -0.6 | -12.5 % | **4.1 %** | 53 % | +189 % | -11.5 % | 4.34 |
| -12 % | 2 % | +287 | -11 | -0.6 | -14.3 % | 3.4 % | 53 % | +191 % | -12.9 % | 4.37 |
| -15 % | 2 % | +282 | -16 | -0.8 | -17.3 % | 3.4 % | 53 % | +183 % | -14.9 % | 4.23 |

A -10 % stop is affordable — 12 bps, t -0.6, nothing — but it barely protects: it fires on 3.4 % of events and the share
of losses beyond 10 % goes UP, from 3.0 % to 4.1 %, because it converts days that would have closed around -9 % into a
realised -10.5 %. **-7 % is the better place if a stop is wanted at all**: 17 bps, caps the worst trade at -10.3 % and the
sleeve's drawdown at -9.4 %.

**The caveat that matters more than the level.** Of the 9 events where a -10 % stop fires, **5 closed locked at ARB** —
there was no bid to sell into, so the stop would not have filled at the level, or at all. The simulation fills every stop
at its price, which flatters it exactly in the cases the protection is for. A stop on this rule reduces the ordinary bad
day; nothing reduces the limit-down day except position size.

