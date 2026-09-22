# IDX menu 28b-0 — P(up) and when to post the order — 2026-09-22

Sessions 2026-09-22; split morning -> afternoon (single session); 117 names; train 20,325 / test 16,370 name-minutes.
Base rates on the test half: UP15 (mid +1 tick after 15 min) 0.161; TOUCH (+1 tick reached within 15 min) 0.255.
Pre-registered in `research/idx_updown_prob.py`; 6 one-sided + 4 two-sided policy trials (cumulative 520).

## Model UP15 — AUC 0.605

| p-bin | mean p | realised | n |
|---|---|---|---|
| 1 | 0.024 | 0.071 | 1,033 |
| 2 | 0.061 | 0.106 | 1,033 |
| 3 | 0.125 | 0.126 | 1,033 |
| 4 | 0.202 | 0.136 | 1,033 |
| 5 | 0.276 | 0.150 | 1,033 |
| 6 | 0.352 | 0.147 | 1,033 |
| 7 | 0.429 | 0.212 | 1,033 |
| 8 | 0.502 | 0.206 | 1,033 |
| 9 | 0.583 | 0.204 | 1,033 |
| 10 | 0.712 | 0.235 | 1,033 |

- top decile: mean p 0.712, realised 0.235 (lift 1.48x), mean 15-min mid move +1.6 bps
- importance (gain share): dist_hi 0.184, pos_day 0.145, RET30 0.117, SPRD 0.086, OBIT 0.082, depth_b 0.051, OBI5 0.049, depth_o 0.042

## Model TOUCH — AUC 0.670

| p-bin | mean p | realised | n |
|---|---|---|---|
| 1 | 0.037 | 0.079 | 1,033 |
| 2 | 0.114 | 0.135 | 1,033 |
| 3 | 0.195 | 0.171 | 1,033 |
| 4 | 0.272 | 0.198 | 1,033 |
| 5 | 0.367 | 0.211 | 1,033 |
| 6 | 0.471 | 0.244 | 1,033 |
| 7 | 0.561 | 0.269 | 1,033 |
| 8 | 0.643 | 0.320 | 1,033 |
| 9 | 0.721 | 0.360 | 1,033 |
| 10 | 0.824 | 0.481 | 1,033 |

- top decile: mean p 0.824, realised 0.481 (lift 1.95x), mean 15-min mid move +6.6 bps
- importance (gain share): dist_hi 0.255, pos_day 0.126, SPRD 0.09, RET30 0.068, OBIT 0.059, OBI5 0.054, OBI1 0.047, depth_o 0.046

## Maker policies on the test half (post at the bid when P(UP15) >= p*; queue-aware fills; sell at the offer; 15-min deadline; fee 30 bps)

| p* | queue | signals | fills | fill rate | sold@offer | net bps/fill | P(win) | net bps/signal | verdict |
|---|---|---|---|---|---|---|---|---|---|
| 0.5 | any | 1,879 | 82 | 4 % | 35 % | -51.5 | 10 % | -2.25 | not yet |
| 0.5 | thin | 313 | 65 | 21 % | 29 % | -48.4 | 11 % | -10.05 | not yet |
| 0.6 | any | 1,034 | 45 | 4 % | 29 % | -50.8 | 7 % | -2.21 | not yet |
| 0.6 | thin | 186 | 36 | 19 % | 28 % | -49.8 | 11 % | -9.65 | not yet |
| 0.7 | any | 412 | 16 | 4 % | 38 % | -63.4 | 12 % | -2.46 | not yet |
| 0.7 | thin | 61 | 10 | 16 % | 40 % | -53.3 | 20 % | -8.73 | not yet |

## Two-sided quotes from inventory (bid and offer posted together; queue-aware; lone leg closed at the far side; fee 30 bps)

| condition | exit | quotes | fills | both legs | buy only | sell only | net bps/fill | net both | net lone | P(win) | net/quote | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| bal | deadline | 281 | 125 | 13 | 82 | 30 | -65.0 | +14.4 | -74.2 | 9 % | -28.91 | not yet |
| bal | stop | 297 | 139 | 17 | 93 | 29 | -60.7 | +15.6 | -71.3 | 10 % | -28.39 | not yet |
| any | deadline | 682 | 305 | 21 | 172 | 112 | -58.7 | +21.5 | -64.7 | 9 % | -26.27 | not yet |
| any | stop | 734 | 348 | 26 | 200 | 122 | -59.8 | +14.8 | -65.9 | 9 % | -28.37 | not yet |

## Reading

- Candidates by the declared bar: none.
- The probability model answers 'will it go up'; the policy table answers 'can a retail order be there when it does'. A good AUC with
  no candidate policy means the move is visible but the queue in front of a late order eats it (menu 28's finding).
- Re-run nightly; from the second session the split is by day. Nothing is adoptable before 20 sessions.
