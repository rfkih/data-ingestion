# IDX menu 28b-1 PRELIM — maker bid on P(up), cancelled when the direction turns — train 2026-09-22 → test 2026-09-23

118 names; P(up 5 min) LightGBM, test-day per-name AUC 0.681; thresholds q50 0.044, q80 0.135, q90 0.233.
Queue-aware fills (join the back of bv1), fees 15 + 25 bps, 15-min deadline. Pre-registered in `research/idx_maker_cancel.py`; 8 trials (cumulative 707).
**One test day: a direction read, not an adoption.**

| post at | order | exit | posted | fills | fill rate | cancelled | wait (min) | hold (min) | net/fill mean | median | t | P(win) | adverse (mid −5 min < L) | net/post | placebo mean | placebo pct | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| q80 | cancel | t15 | 1,605 | 144 | 9 % | 72 % | 4.5 | 15.0 | -52.8 | -52.1 | -7.01 | 25 % | 51 % | -4.73 | -49.9 | 40 | no |
| q80 | cancel | signal | 1,637 | 143 | 9 % | 71 % | 4.5 | 15.0 | -52.9 | -40.0 | -7.96 | 18 % | 48 % | -4.62 | -57.4 | 90 | no |
| q80 | hold | t15 | 1,111 | 175 | 16 % | 0 % | 6.0 | 15.0 | -51.1 | -60.8 | -7.30 | 19 % | 50 % | -8.05 | -63.4 | 100 | no |
| q80 | hold | signal | 1,149 | 183 | 16 % | 0 % | 6.0 | 14.0 | -49.9 | -40.0 | -8.59 | 14 % | 46 % | -7.94 | -70.5 | 100 | no |
| q90 | cancel | t15 | 697 | 70 | 10 % | 61 % | 4.9 | 15.0 | -42.8 | -52.1 | -4.28 | 26 % | 57 % | -4.30 | -46.9 | 75 | no |
| q90 | cancel | signal | 709 | 70 | 10 % | 62 % | 4.9 | 15.0 | -40.9 | -50.1 | -4.46 | 24 % | 57 % | -4.03 | -53.8 | 100 | no |
| q90 | hold | t15 | 564 | 87 | 15 % | 0 % | 6.5 | 15.0 | -49.0 | -50.3 | -5.29 | 24 % | 57 % | -7.55 | -58.3 | 100 | no |
| q90 | hold | signal | 577 | 91 | 16 % | 0 % | 6.5 | 15.0 | -50.3 | -50.3 | -6.07 | 21 % | 57 % | -7.93 | -67.3 | 100 | no |

## Reading

- Candidates by the bar (>= 100 fills, >= +20 bps/fill, t >= 2, placebo >= 95): none.
- 'cancel' pulls the bid the moment P(up) drops below the train-day median; 'hold' leaves it for 15 min. The placebo posts and cancels
  from a shuffled score, so it measures what a maker bid earns at random times with the same mechanics.
- Compare 'adverse': the share of fills after which the mid is below the fill price 5 min later — the adverse selection the cancel is meant to avoid.
- Re-run at >= 20 sessions.
