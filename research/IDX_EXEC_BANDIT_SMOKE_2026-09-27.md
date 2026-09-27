# Execution learning on the recorded order book - 2026-09-27

**SMOKE - NOT EVIDENCE.** 4 recorded sessions; the pre-registered read needs 20.

2,180 small-buy decisions in 118 names; 1,607 scored out of sample (walk-forward by session). Cost = bps over the
mid at the decision, spread and waiting drift included, fees excluded (the same for every policy).

| policy | mean cost (bps) |
|---|---|
| CROSS | +30.2 |
| JOIN5 | +26.6 |
| JOIN15 | +24.1 |
| TIGHT5 | +28.8 |
| P_ctx | +23.3 |
| P_best | +26.8 |
| ORACLE | +8.0 |

Passive fill rates: JOIN5 14 %, JOIN15 29 %.

| learner | saving vs CROSS (bps) | t (sessions) | 1st half | 2nd half | choices | pass |
|---|---|---|---|---|---|---|
| P_ctx | +7.2 | 3.40 | +4.5 | +8.6 | JOIN15 52 %, JOIN5 30 %, TIGHT5 11 %, CROSS 6 % | - |
| P_best | +3.6 | 2.01 | +0.1 | +5.4 | JOIN5 65 %, JOIN15 35 % | - |

Compare: the learned EXIT policy (#396) added +0.10 %/trade (10 bps, t 0.14) - closed. ORACLE is the hindsight ceiling of this
decision alone. Limits: small orders only (no own impact); queue position = the back of the best bid; the 10-second grid; buys
only (sells are the mirror); the opening and closing auctions (where the gap-fade trades) are not in this grid.
