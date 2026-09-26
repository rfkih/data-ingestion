# IDX menu 47 - predicting MSCI Indonesia (Standard) additions - 2026-09-26 - 7 trials, cumulative N = 999 - study #286

**Verdict: CLOSED.** Pre-registered in `research/idx_msci_predict.py` (docstring written before any return was computed).

## Events (MSCI's own change lists)

27 quarterly reviews Feb 2020 -> Aug 2026 sourced from MSCI's public change-list PDFs (`app2.msci.com/eqb/gimi/stdindex/MSCI_<Mon><YY>_STPublicList.pdf`, and the SCPublicList twin for Small Cap), cross-checked against the press (sources in the docstring). 18 reviews changed the Standard index; **10 added names (15 adds)**; 3 (Feb/May/Aug 2026) fell under MSCI's Indonesia freeze (2026-01-27: no IMI additions, no upward migrations) and are not traded. Membership chained backward from the post-Aug-2026 list of 9 and consistent at every step.

| review | announced (US) | J (1st IDX session after) | R (as-of close) | Standard adds | Standard deletions | Small Cap adds / dels | members before |
|---|---|---|---|---|---|---|---|
| Feb20 | 2020-02-12 | 2020-02-13 | 2020-02-28 | - | - | 0 / 0 | 28 |
| May20 | 2020-05-12 | 2020-05-13 | 2020-05-29 | - | BBTN PTBA BSDE JSMR TKIM PWON | 10 / 14 | 28 |
| Aug20 | 2020-08-12 | 2020-08-13 | 2020-08-31 | - | - | 0 / 0 | 22 |
| Nov20 | 2020-11-10 | 2020-11-11 | 2020-11-30 | MDKA TOWR | HMSP EXCL | 5 / 4 | 22 |
| Feb21 | 2021-02-09 | 2021-02-10 | 2021-02-26 | ANTM | ACES | 1 / 1 | 22 |
| May21 | 2021-05-11 | 2021-05-17 | 2021-05-27 | TBIG | PGAS | 3 / 3 | 22 |
| Aug21 | 2021-08-11 | 2021-08-12 | 2021-08-31 | - | - | 0 / 0 | 22 |
| Nov21 | 2021-11-11 | 2021-11-12 | 2021-11-30 | - | - | 9 / 3 | 22 |
| Feb22 | 2022-02-09 | 2022-02-10 | 2022-02-25 | ARTO | - | 0 / 0 | 22 |
| May22 | 2022-05-12 | 2022-05-13 | 2022-05-31 | ADMR AMRT INCO | INTP | 11 / 2 | 23 |
| Aug22 | 2022-08-11 | 2022-08-12 | 2022-08-31 | - | - | 0 / 0 | 25 |
| Nov22 | 2022-11-10 | 2022-11-11 | 2022-11-30 | - | ADMR GGRM TBIG | 4 / 3 | 25 |
| Feb23 | 2023-02-09 | 2023-02-10 | 2023-02-28 | - | ARTO | 3 / 1 | 22 |
| May23 | 2023-05-11 | 2023-05-12 | 2023-05-31 | GOTO | - | 0 / 2 | 21 |
| Aug23 | 2023-08-10 | 2023-08-11 | 2023-08-31 | - | - | 3 / 4 | 22 |
| Nov23 | 2023-11-14 | 2023-11-15 | 2023-11-30 | AMMN | INCO | 2 / 5 | 22 |
| Feb24 | 2024-02-12 | 2024-02-13 | 2024-02-29 | - | - | 2 / 1 | 22 |
| May24 | 2024-05-14 | 2024-05-15 | 2024-05-31 | TPIA | TOWR SMGR | 5 / 9 | 22 |
| Aug24 | 2024-08-12 | 2024-08-13 | 2024-08-30 | - | ANTM | 5 / 0 | 21 |
| Nov24 | 2024-11-06 | 2024-11-07 | 2024-11-25 | - | - | 1 / 2 | 20 |
| Feb25 | 2025-02-11 | 2025-02-12 | 2025-02-28 | - | INKP MDKA UNVR | 3 / 4 | 20 |
| May25 | 2025-05-13 | 2025-05-14 | 2025-05-28 | - | - | 2 / 4 | 17 |
| Aug25 | 2025-08-07 | 2025-08-08 | 2025-08-26 | DSSA CUAN | ADRO | 6 / 2 | 17 |
| Nov25 | 2025-11-05 | 2025-11-06 | 2025-11-24 | BREN BRMS | ICBP KLBF | 7 / 3 | 18 |
| Feb26 (freeze) | 2026-02-10 | 2026-02-11 | 2026-02-27 | - | INDF | 1 / 2 | 18 |
| May26 (freeze) | 2026-05-12 | 2026-05-13 | 2026-05-29 | - | AMMN BREN TPIA DSSA CUAN AMRT | 1 / 13 | 17 |
| Aug26 (freeze) | 2026-08-12 | 2026-08-13 | 2026-08-31 | - | CPIN GOTO | 1 / 9 | 11 |

## Step 1 - can the published rule see the adds? (classification, not a trial)

Pooled over 23 traded reviews (15 adds in 10 reviews): precision@1 26 %, precision@3 **16 %**, precision@5 10 %; recall@1 40 %, recall@3 **73 %**, recall@5 73 %. Precision@3 on the reviews that had adds only: 37 %. Rule-pass set (size >= 1.5/1.8 x C^, FF floor): 39 names, precision 26 %, recall 67 %.

| review | price cut-off | C^ (USD bn, 3 smallest members) | FF published | adds (rank among eligible non-members) | top-5 predicted | hits@3 | rule-pass |
|---|---|---|---|---|---|---|---|
| May20 | 2020-04-24 | 0.81 | no | - | TOWR MDKA TBIG TCPI INCO | 0 | TOWR MDKA TBIG TCPI INCO |
| Aug20 | 2020-07-28 | 2.00 | no | - | TOWR MDKA INCO JSMR TBIG | 0 | TOWR |
| Nov20 | 2020-10-22 | 1.76 | no | MDKA #3, TOWR #1 | TOWR INCO MDKA MIKA TBIG | 2 | TOWR INCO MDKA |
| Feb21 | 2021-01-26 | 2.63 | no | ANTM #1 | ANTM INCO TBIG TKIM MIKA | 1 | - |
| May21 | 2021-04-27 | 2.68 | no | TBIG #2 | BRIS TBIG INCO MIKA ISAT | 1 | BRIS TBIG |
| Aug21 | 2021-07-27 | 2.81 | no | - | BRIS AGRO INCO TCPI FREN | 0 | BRIS |
| Nov21 | 2021-10-28 | 3.18 | yes | - | ARTO BRIS BBHI INCO AGRO | 0 | ARTO BRIS BBHI |
| Feb22 | 2022-01-25 | 2.81 | yes | ARTO #1 | ARTO BBHI EMTK BRIS TCPI | 1 | ARTO BBHI EMTK |
| May22 | 2022-04-20 | 2.62 | yes | ADMR inelig(freq), AMRT #3, INCO #2 | EMTK INCO AMRT TCPI PTBA | 2 | EMTK INCO AMRT |
| Aug22 | 2022-07-28 | 2.86 | yes | - | EMTK PTBA ITMG BEBS PGAS | 0 | EMTK |
| Nov22 | 2022-10-27 | 2.94 | yes | - | EMTK BUMI MTEL MSIN MYOR | 0 | EMTK |
| Feb23 | 2023-01-26 | 3.29 | yes | - | ADMR EMTK BUMI MTEL MYOR | 0 | - |
| May23 | 2023-04-26 | 2.90 | yes | GOTO inelig(board/notation) | MTEL MYOR ISAT GGRM PTBA | 0 | - |
| Aug23 | 2023-07-27 | 3.15 | yes | - | ISAT MTEL GGRM MYOR BUMI | 0 | - |
| Nov23 | 2023-10-31 | 2.60 | yes | AMMN inelig(freq) | ISAT MYOR MTEL ADMR GGRM | 0 | ISAT MYOR |
| Feb24 | 2024-01-25 | 2.64 | yes | - | ISAT ADMR MTEL MYOR ARTO | 0 | ISAT |
| May24 | 2024-04-25 | 2.36 | yes | TPIA #1 | TPIA ISAT CUAN MBMA MYOR | 1 | TPIA ISAT CUAN MBMA |
| Aug24 | 2024-07-29 | 2.70 | yes | - | CUAN ISAT MBMA MYOR ADMR | 0 | CUAN ISAT |
| Nov24 | 2024-10-23 | 3.97 | yes | - | CUAN ISAT MYOR ADMR NCKL | 0 | - |
| Feb25 | 2025-01-23 | 2.42 | yes | - | DSSA CUAN ISAT BRMS MYOR | 0 | DSSA CUAN ISAT |
| May25 | 2025-04-24 | 3.52 | yes | - | DSSA CUAN ISAT MYOR BRMS | 0 | DSSA |
| Aug25 | 2025-07-24 | 4.14 | yes | DSSA #1, CUAN #2 | DSSA CUAN ISAT ANTM BRMS | 2 | DSSA CUAN |
| Nov25 | 2025-10-22 | 3.71 | yes | BREN inelig(ff), BRMS #1 | BRMS EMTK ANTM PTRO MBMA | 1 | BRMS |

## Step 2 - trades (bps per trade; excess vs 5 matched controls; t over reviews)

| arm | trades | reviews | hit rate (true adds) | net mean | net median | win | controls | excess (review mean) | t (reviews) | reviews > 0 | days |
|---|---|---|---|---|---|---|---|---|---|---|---|
| M1_T5_jump | 69 | 23 | 16 % | -205 | -154 | 39 % | -63 | -141 | -0.88 | 52 % | 5.0 |
| M2_T10_jump | 69 | 23 | 16 % | -114 | -231 | 36 % | -98 | -16 | -0.09 | 48 % | 10.0 |
| M3_T5_R (main) | 69 | 23 | 16 % | -102 | -70 | 48 % | +10 | -112 | -0.47 | 43 % | 16.2 |
| M4_T10_R | 69 | 23 | 16 % | -12 | +87 | 54 % | -30 | +17 | 0.07 | 57 % | 21.2 |
| M5_top1_T5_R | 23 | 23 | 26 % | -37 | +283 | 52 % | +23 | -60 | -0.18 | 39 % | 16.2 |
| M6_rulepass_T5_R | 39 | 18 | 26 % | -89 | +283 | 54 % | -34 | -94 | -0.28 | 44 % | 15.8 |
| M7_ffcap_T5_R | 69 | 23 | 14 % | -241 | -176 | 41 % | -45 | -196 | -0.97 | 26 % | 16.2 |
| M3 costs x1.5 | 69 | 23 | 16 % | -147 | -105 | 48 % | -40 | -107 | -0.46 | 43 % | 16.2 |
| fact: perfect foresight, T5 -> jump | 15 | 10 | 100 % | +342 | +192 | 53 % | -52 | +468 | 1.36 | 70 % | 5.0 |
| fact: perfect foresight, T5 -> R | 15 | 10 | 100 % | +962 | +1041 | 80 % | +172 | +720 | 1.34 | 60 % | 15.9 |
| fact: DRIFT actual adds, J close -> R close | 15 | 10 | 100 % | +517 | +546 | 67 % | +122 | +255 | 0.81 | 60 % | 10.9 |
| fact: DRIFT deletions (all 18), J close -> R close | 34 | 16 | 0 % | -914 | -430 | 26 % | -186 | -627 | -3.31 | 12 % | 10.4 |
| fact: DRIFT deletions, 2020-2025 only (post-hoc split) | 25 | 13 | 0 % | -532 | -377 | 32 % | -49 | -488 | -2.40 | 15 % | 11.0 |
| fact: announcement reaction (J-1 -> J close, gross) | 15 | 10 | 100 % | +239 | +179 | 60 % | +47 | +155 | 0.99 | 40 % | 1.0 |

Placebo (3 random eligible non-members from score ranks 4-20 per review, 1000 draws): real -112, median +30, 95th pct +271, real's percentile **15**.

DSR of the per-review M3 excess at N = 999: 0.000.

Halves (M3): 2020-22: 33 trades, excess -276, t -1.68; 2023-25: 36 trades, excess +40, t 0.09

BAR (M3): ex>0 FAIL, t>=2 FAIL, net>0 FAIL, ev_pos>=60% FAIL, placebo>=95 FAIL -> **CLOSED**.

## Per review (M3 picks; actual-add drift J -> R) (bps, net / excess, * = true add)

| review | M3 picks | actual adds: J close -> R close |
|---|---|---|
| May20 | TOWR +588/-84, MDKA +456/+3, TBIG -820/-1272 | - |
| Aug20 | TOWR -1122/-960, MDKA -1494/-1377, INCO +201/+318 | - |
| Nov20 | TOWR* +1041/-232, INCO +1195/+258, MDKA* +360/-990 | MDKA +518/+142, TOWR +1047/+621 |
| Feb21 | ANTM* +2116/+990, INCO +315/-173, TBIG -836/-1375 | ANTM -377/-589 |
| May21 | BRIS -2048/-2716, TBIG* -688/-1475, INCO -835/-511 | TBIG -311/-1202 |
| Aug21 | BRIS -1509/-479, AGRO -961/-996, INCO -176/-211 | - |
| Nov21 | ARTO +358/+1037, BRIS -671/+8, BBHI -70/+338 | - |
| Feb22 | ARTO* -378/-59, BBHI -431/-69, EMTK +306/+442 | ARTO +588/+1044 |
| May22 | EMTK -3711/-2982, INCO* +1172/+1539, AMRT* +573/+1697 | ADMR -543/-3, AMRT +1486/+1609, INCO +1824/+1396 |
| Aug22 | EMTK -887/-812, PTBA +238/+471, ITMG -183/+50 | - |
| Nov22 | EMTK -2204/-1669, BUMI +450/+1005, MTEL +325/+1164 | - |
| Feb23 | ADMR -1345/-1480, EMTK -1985/-2537, BUMI -852/-986 | - |
| May23 | MTEL -471/-580, MYOR -146/-785, ISAT +923/+1139 | GOTO +1010/+1416 |
| Aug23 | ISAT +808/+645, MTEL +695/+495, GGRM -629/-231 | - |
| Nov23 | ISAT +283/-904, MYOR -532/-845, MTEL +1543/-31 | AMMN -105/-1198 |
| Feb24 | ISAT +1800/+2078, ADMR +895/+1933, MTEL -771/+267 | - |
| May24 | TPIA* +1701/+2585, ISAT -560/+305, CUAN +347/+1211 | TPIA -166/+711 |
| Aug24 | CUAN +2188/+645, ISAT -282/-1826, MBMA -475/-1428 | - |
| Nov24 | CUAN -1057/-370, ISAT -70/+306, MYOR +430/+1252 | - |
| Feb25 | DSSA -3722/-1708, CUAN -5267/-4256, ISAT -3433/-2382 | - |
| May25 | DSSA +1542/+1639, CUAN +4592/+4905, ISAT +844/+1042 | - |
| Aug25 | DSSA* +3852/+3906, CUAN* +967/+1218, ISAT -995/-1382 | DSSA +1427/+1376, CUAN +683/+1031 |
| Nov25 | BRMS* +1318/+132, EMTK +858/-86, ANTM -679/-2460 | BREN +132/+92, BRMS +546/-524 |

## Current ranking (next review Nov 2026; the freeze is still in force - no adds expected)

Data through 2026-09-25. Largest eligible non-members by full mcap (USD bn): AMMN 19.1, DSSA 11.3, EMAS 6.3, CUAN 5.9, AADI 4.9, IMPC 4.3, ANTM 4.3, ICBP 4.3.
## Reading (written after the run)

1. **The events are solid; the add sample is small.** All 27 reviews come from MSCI's own change-list PDFs (not the press), and the
   membership chain is consistent (28 names before May 2020 -> 9 after Aug 2026). But Indonesia's Standard index is small and
   has been shrinking: 15 adds in 10 of 23 tradable reviews. Since Jan 2026 the freeze means no adds at all. The test clears the
   >= 12 events floor only as reviews, and PARTIAL was the ceiling.
2. **The mechanical rule sees the adds far better than LQ45's rule did (menu 42: precision@5 9 %, recall@5 16 %).** Top-3 by full
   USD market cap among eligible non-members catches 11 of 15 adds (recall@3 73 %), and it ranks an add #1 in 6 of the 10 add reviews
   (TOWR, ANTM, ARTO, TPIA, DSSA, BRMS; TBIG and INCO at #2). Precision is still only 16 % pooled, because 13 of 23 reviews add no one
   and the rule still fires; on reviews that did add someone it is 37 %. Two misses are flaws in the proxy, not in MSCI: the 12-month
   frequency test counts sessions before the IPO, so recent listings (ADMR 2022, AMMN 2023) are wrongly ineligible. The other misses
   are GOTO (special-notation flag) and BREN (free float < 15 %). Serial snubs (EMTK, ISAT, MYOR, MTEL, CUAN in 2024-25) reflect what
   the proxy cannot see: FIF / foreign room, MSCI's investability judgement, and the 2025 non-implementation of BREN, CUAN and PTRO.
3. **The trade still fails.** M3 (top-3, 5 sessions before the notice, out at the rebalance close): -102 bps net, -112 over matched
   controls, t -0.47, 43 % of reviews positive; the placebo is at the 15th percentile. No arm is significant: the best is M4
   (T = 10 -> R) at +17 bps, t 0.07. Costs x1.5 changes nothing; DSR 0. Halves disagree (2020-22 -276 bps, 2023-25 +40 bps).
   **CLOSED.** There is no sleeve, so no correlation / Rp run.
4. **Why a far better classifier still loses:** the prize is thin and noisy. Perfect foresight earns +720 bps excess on the T5 -> R
   window, but only at t 1.34 over 10 reviews: DSSA +3906 and TPIA +2585 carry it, while AMMN and TBIG are -1200 to -1500. The
   non-adds are big, volatile names that the rule keeps flagging (EMTK -2982 / -2537, CUAN -4256 in Feb 2025), and with 16 %
   precision their swings swamp the adds.
5. **Announcement -> effective drift for ACTUAL adds** (buy the closing offer on the first session after the notice, sell at the
   rebalance close; about 11 sessions): +517 bps net, +255 over controls, t 0.81, 60 % of reviews positive. The reaction on the
   notice day itself is +239 bps gross (+155 excess, t 0.99). So unlike LQ45, MSCI adds do not give everything back at once and the
   point estimate stays positive into the effective date. With t < 1 over 10 reviews it is not a finding, and the freeze means no new
   events for now.
6. **Side finding, not a trial: MSCI Standard DELETIONS drift down from the notice to the rebalance close.** -914 bps net, -627 over
   controls, t -3.31 across 16 reviews, 12 % positive. Excluding the 2026 freeze and HSC reviews (a post-hoc split): -488, t -2.40,
   13 reviews. For a long-only desk this is an avoid / exit rule (sell a held name when MSCI announces its deletion), not a trade.
   It needs its own pre-registered menu, run on the desk's actual holdings, before anything changes in a book.
7. **Current ranking**, for the record only: AMMN, DSSA, EMAS, CUAN, AADI. The freeze is in force and the Nov-2026 review may consult on
   Frontier status, so no adds are expected; this is not a buy list.
