# IDX menu MK-1 PRELIM — two-sided tick capture as a maker on wide-tick names — 2026-09-27 — study #399

Script `research/idx_maker_tick.py` (pre-registered in its docstring). Data: every print (`idx.feed_trade`) and every book update
(`idx.feed_book`), sessions 2026-09-22 .. 09-25, ~135 names. **4 trials; cumulative N 1063 -> 1067. Result: 0 of 4.**

Rule: at 5-minute marks, on names whose one-tick spread is >= theta of the price, rest a bid at the best bid (back of the queue),
then rest an offer one tick higher; stop 2 ticks under, 30-min taker exit, closing auction at 15:40. Size Rp 10 m, fees 0.15/0.25.

| arm | posts | fill rate | round trips | median tick | gross bps | net bps | net @0.10/0.20 | exits at the offer | stopped | adverse 5 min | by day (net) | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| M1 theta 60 bps | 6,487 | 19 % | 1,201 | 80 bps | -69 | **-109** | -99 | 19 % | 38 % | -19 bps | -119 / -83 / -96 / -126 | no |
| M2 theta 100 bps | 1,229 | 13 % | 155 | 156 bps | -124 | **-163** | -153 | 13 % | 37 % | -43 bps | | no |
| M3 M1 + bid-heavy book | 3,397 | 10 % | 335 | 78 bps | -93 | **-132** | -122 | 19 % | 52 % | -33 bps | | no |
| M4 M1 without the stop | 6,487 | 19 % | 1,201 | 80 bps | -63 | **-102** | -92 | 23 % | - | -19 bps | -115 / -64 / -103 / -120 | no |

## Why it loses (diagnostic on M4's 1,201 fills, not a trial)

| how the bid filled | fills | gross bps | net bps | exited at the offer |
|---|---|---|---|---|
| the whole level traded through (price falling) | 859 (72 %) | -81 | -121 | 20 % |
| our turn in the queue came | 342 (28 %) | -16 | -56 | 40 % |

| queue ahead at the post (quartile) | median ahead | gross bps | exited at the offer | adverse 5 min |
|---|---|---|---|---|
| shortest | Rp 26 m | -45 | 30 % | -6 bps |
| longest | Rp 1.1 bn | -88 | 10 % | -41 bps |

**Reading.** A bid at the back of the queue fills mostly when the price is falling through it (72 % of fills) - classic adverse
selection - and the offer one tick up then fills only 20-40 % of the time. The wider the tick, the worse (M2): wide ticks carry
long queues, so only a sweep reaches the back. Even the shortest queues and the fills that came by queue turn are negative
GROSS. The makers who earn the tick on IDX are at the FRONT of the queue (they join a level the moment it opens, with
low-latency connections and exchange-member fees); a retail order placed at a 5-minute mark cannot be there.

**Verdict: 0 of 4.** Do not re-run passive tick capture from a retail seat. The robust fact to keep: on IDX a resting bid that
fills is, three times out of four, a bid the market ran through.
