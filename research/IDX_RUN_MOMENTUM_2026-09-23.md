# IDX menu 32b PRELIM — 'already up K ticks → it goes higher' as an event study — 2026-09-22, 2026-09-23

118 names, 608 runs over 2 sessions. Event = the first 10-s step at which a run's gain reaches K ticks.
Pre-registered in `research/idx_run_momentum.py`; 8 trials (cumulative 678). **Two sessions: a direction read, not an adoption.**

| K | condition | exit | events | P(≥ +1 tick more) | ticks more (mean / median) | run life left (median min) | net bps (mean / median) | t | P(win) | by day | placebo mean | placebo pct | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 5 | all | trail | 254 | 0.66 | +2.28 / +1.00 | 6.3 | -67.5 / -72.9 | -11.19 | 20 % | -73 (n 94) / -64 (n 160) | -61.4 | 6 | no |
| 5 | all | t15 | 254 | 0.66 | +2.28 / +1.00 | 6.3 | -67.8 / -72.9 | -12.30 | 17 % | -72 (n 94) / -65 (n 160) | -65.4 | 28 | no |
| 5 | mkt_up | trail | 67 | 0.61 | +1.95 / +1.00 | 8.0 | -72.4 / -84.9 | -5.28 | 18 % | -72 (n 67) | -59.8 | 9 | no |
| 5 | mkt_up | t15 | 67 | 0.61 | +1.95 / +1.00 | 8.0 | -75.8 / -84.9 | -6.67 | 12 % | -76 (n 67) | -64.9 | 5 | no |
| 8 | all | trail | 84 | 0.63 | +2.23 / +1.00 | 3.3 | -68.0 / -74.6 | -8.54 | 19 % | -77 (n 25) / -64 (n 59) | -43.6 | 0 | no |
| 8 | all | t15 | 84 | 0.63 | +2.23 / +1.00 | 3.3 | -65.8 / -74.6 | -8.66 | 19 % | -74 (n 25) / -63 (n 59) | -52.9 | 6 | no |
| 8 | mkt_up | trail | 28 | 0.61 | +1.71 / +1.00 | 5.8 | -73.3 / -67.9 | -4.44 | 18 % | -73 (n 28) | -30.3 | 1 | no |
| 8 | mkt_up | t15 | 28 | 0.61 | +1.71 / +1.00 | 5.8 | -74.1 / -67.7 | -5.32 | 18 % | -74 (n 28) | -48.9 | 2 | no |

## Examples — first twelve K=8 events on 2026-09-23

| name | time | ticks more | run life left (min) | net trail bps |
|---|---|---|---|---|
| TINS | 09:01 | +0.0 | 2.2 | -93.0 |
| TCPI | 09:10 | +4.0 | 1.8 | -132.0 |
| INCO | 09:11 | +0.0 | 0.2 | -92.0 |
| GGRM | 09:12 | +1.0 | 5.7 | -58.0 |
| SINI | 09:14 | +0.0 | 0.2 | -92.0 |
| TCPI | 09:23 | +0.0 | 2.3 | -130.0 |
| SINI | 09:25 | +0.0 | 0.5 | -92.0 |
| ARKO | 09:29 | +1.5 | 1.8 | -104.0 |
| AADI | 09:48 | +0.0 | 2.8 | -97.0 |
| SINI | 09:48 | +0.0 | 0.5 | -76.0 |
| DEWI | 09:55 | +1.0 | 5.2 | -131.0 |
| IRSX | 10:07 | +0.0 | 1.3 | -165.0 |

## Reading

- Trade candidates by the bar (>= 100 events, >= +20 bps, t >= 2, both days positive, placebo >= 95): none.
- Forecast read (P(≥ +1 tick more) >= 0.60 with >= 100 events on both days): none.
- 'ticks more' is what a holder could still get from the event; the net columns are what a taker who BUYS at the event keeps after the
  spread and the −2-tick giveback. The placebo places the same number of entries at random in-run steps of the same names.
- Re-run at >= 20 sessions.
