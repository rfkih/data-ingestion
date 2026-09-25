# IDX menu 42 - predicting LQ45 adds before the announcement - 2026-09-25 - 7 trials, cumulative N = 903

**Verdict: CLOSED.** Pre-registered in `research/idx_lq45_predict.py` (docstring written before any return was computed).

Reviews: 18 scheduled LQ45 evaluations 2020-07 -> 2026-07 (50 adds; 2025-04 had none). Membership rebuilt point in time from the Feb-2020 list + menu 36's events + three changes menu 36 missed (2021-09 BUKA<-SMRA fast entry, 2022-06 GOTO<-WSKT fast entry, 2024-04 AMMN ISAT in / EMTK PTMP out); the chain stays at 45 names at every step and ends on the published Aug-2026 list.

## Step 1 - can the rule see the adds? (classification, not a trial)

Pooled over 18 reviews: precision@3 9 %, precision@5 **9 %**, precision@10 14 %; recall@3 10 %, recall@5 **16 %**, recall@10 52 %. 'In-rank' set (non-members inside the overall top 45): 141 names, precision 13 %, recall 38 %. Liquidity-only score: precision@5 9 %.

| A | cut-off | window (sessions) | adds (rank among eligible non-members) | top-5 predicted | hits@5 | in-rank set | members ranked > 45 / ineligible |
|---|---|---|---|---|---|---|---|
| 2020-07-24 | 2020-06-30 | 121 | MDKA #1, MIKA #7, SMRA #10 | MDKA TCPI FREN MEDC TPIA | 1 | MDKA TCPI FREN MEDC TPIA | 5 / 0 |
| 2021-01-26 | 2020-12-30 | 242 | MEDC #9, TPIA #12 | BRPT BRIS TCPI KAEF WSKT | 0 | BRPT BRIS TCPI KAEF WSKT BBKP FREN AGRO | 9 / 0 |
| 2021-07-26 | 2021-06-30 | 241 | BRPT #4, TINS #7 | BRIS AGRO FREN BRPT BBKP | 1 | BRIS AGRO FREN BRPT BBKP WSKT TINS KAEF | 10 / 1 |
| 2022-01-25 | 2021-12-30 | 247 | AMRT #29, BFIN #10, EMTK #4, HRUM #12, WSKT #8 | ARTO BRIS AGRO EMTK FREN | 1 | ARTO BRIS AGRO EMTK FREN BBYB BBKP WSKT | 13 / 1 |
| 2022-07-25 | 2022-06-30 | 243 | ARTO #1, BRIS inelig., INDY #8 | ARTO BRMS TCPI BBYB FREN | 1 | ARTO BRMS TCPI BBYB FREN BEBS BBKP INDY | 11 / 3 |
| 2023-01-25 | 2022-12-30 | 246 | ACES #17, AKRA #8, ESSA #6, SCMA #11, SIDO #16, SRTG #13 | BUMI ADMR BRMS TCPI BIPI | 0 | BUMI ADMR BRMS TCPI BIPI ESSA FREN AKRA | 10 / 4 |
| 2023-07-26 | 2023-06-27 | 247 | GGRM #8, MAPI #7 | BUMI BRMS ADMR BIPI FREN | 0 | BUMI BRMS ADMR BIPI FREN TCPI MAPI GGRM | 7 / 2 |
| 2024-01-25 | 2023-12-29 | 240 | MBMA inelig., MTEL #5, PGEO inelig., PTMP inelig. | BUMI BRMS ADMR FILM MTEL | 1 | BUMI BRMS ADMR FILM MTEL PANI TCPI ISAT | 5 / 3 |
| 2024-04-24 | 2024-03-28 | 238 | AMMN inelig., ISAT #8 | TPIA BUMI ADMR BRMS FILM | 0 | TPIA BUMI ADMR BRMS FILM NCKL PANI ISAT | 7 / 2 |
| 2024-07-25 | 2024-06-28 | 235 | JSMR #8 | TPIA BUMI BRMS ADMR PANI | 0 | TPIA BUMI BRMS ADMR PANI FILM NCKL JSMR | 6 / 2 |
| 2024-10-25 | 2024-09-30 | 238 | ADMR #6, SMRA #15 | BREN TPIA CUAN PANI BUMI | 0 | BREN TPIA CUAN PANI BUMI ADMR BRMS FILM | 6 / 2 |
| 2025-01-22 | 2024-12-30 | 237 | CTRA #15, JPFA #9, MAPA #11 | BREN TPIA BRMS PANI BUMI | 0 | BREN TPIA BRMS PANI BUMI CUAN PTRO FILM | 8 / 2 |
| 2025-04-24 | 2025-03-27 | 238 | (no change) | BREN BRMS TPIA PANI BUMI | 0 | BREN BRMS TPIA PANI BUMI CUAN PTRO WIFI | 9 / 1 |
| 2025-07-25 | 2025-06-30 | 236 | AADI inelig., SCMA #18 | BREN BRMS TPIA PANI BUMI | 0 | BREN BRMS TPIA PANI BUMI CUAN PTRO KPIG | 10 / 1 |
| 2025-10-27 | 2025-09-30 | 235 | BUMI #6, DSSA #11, EMTK #9, HEAL #24, NCKL #16 | BRMS BREN CUAN PTRO PANI | 0 | BRMS BREN CUAN PTRO PANI BUMI TPIA WIFI | 13 / 2 |
| 2026-01-27 | 2025-12-30 | 236 | BREN #2 | BRMS BREN CUAN PTRO TPIA | 1 | BRMS BREN CUAN PTRO TPIA PANI DEWA WIFI | 17 / 1 |
| 2026-04-24 | 2026-03-31 | 233 | CUAN #2, DEWA #3, ESSA #24, HRTA #29, WIFI #10 | BRMS CUAN DEWA PTRO ENRG | 2 | BRMS CUAN DEWA PTRO ENRG BUVA PANI TPIA | 15 / 1 |
| 2026-07-27 | 2026-06-30 | 239 | INDY #26, NCKL #16 | BRMS BREN PTRO DSSA TPIA | 0 | BRMS BREN PTRO DSSA TPIA CDIA ENRG BUVA | 17 / 1 |

## Step 2 - buy the predicted adds before the notice, sell on the jump day (bps per trade; t over reviews)

| arm | trades | reviews | hit rate (true adds) | net mean | net median | win | controls | excess (review mean) | t (reviews) | reviews > 0 | days |
|---|---|---|---|---|---|---|---|---|---|---|---|
| P1_main | 90 | 18 | 9 % | -207 | -211 | 41 % | -129 | -78 | -0.52 | 56 % | 6.2 |
| P2_T10 | 90 | 18 | 9 % | +204 | -35 | 48 % | -42 | +246 | 1.31 | 72 % | 11.2 |
| P3_top3 | 54 | 18 | 9 % | -76 | -135 | 43 % | -107 | +31 | 0.16 | 33 % | 6.2 |
| P4_inrank | 141 | 18 | 13 % | -277 | -219 | 40 % | -171 | -79 | -0.55 | 50 % | 6.2 |
| P5_exit_R | 90 | 18 | 9 % | -187 | -300 | 37 % | -97 | -90 | -0.55 | 50 % | 9.0 |
| P6_delay1 | 90 | 18 | 9 % | -258 | -194 | 36 % | -148 | -110 | -0.76 | 44 % | 5.2 |
| P7_value_only | 90 | 18 | 9 % | -351 | -261 | 31 % | -146 | -205 | -1.48 | 44 % | 6.2 |
| P1 costs x1.5 | 90 | 18 | 9 % | -254 | -256 | 38 % | -173 | -80 | -0.54 | 56 % | 6.2 |
| fact: perfect foresight (actual adds) | 50 | 17 | 100 % | +195 | +292 | 66 % | -251 | +433 | 4.19 | 82 % | 6.1 |

Placebo (5 random eligible non-members from ranks 6-25 per review, 1000 draws): real excess -78, median +64, 95th pct +260, real's percentile **6**.

DSR of the per-review excess series at N = 903: 0.000.

Halves (P1): 2020-22: 25 trades, excess +64, t 0.14; 2023-26: 65 trades, excess -133, t -1.07

BAR (P1): excess > 0, t >= 2, net > 0, >= 60 % reviews positive, placebo >= 95th pct -> ex>0 FAIL, t>=2 FAIL, net>0 FAIL, ev_pos>=60% FAIL, placebo>=95 FAIL -> **CLOSED**.

## P1 per review (bps)

| A | names: net / excess (* = true add) |
|---|---|
| 2020-07-24 | MDKA* +2455/+2383, TCPI +154/+263, FREN +4389/+4332, MEDC -366/-722, TPIA -281/-354 |
| 2021-01-26 | BRPT -821/-388, BRIS -1854/-1079, TCPI -765/-432, KAEF -3245/-2737, WSKT -1580/-715 |
| 2021-07-26 | BRIS +1036/+1085, AGRO +2466/+2662, FREN +863/+326, BRPT* +711/+760, BBKP +71/-1025 |
| 2022-01-25 | ARTO -1646/-1697, BRIS +64/+164, AGRO -1350/-1556, EMTK* -730/-629, FREN -1030/-1236 |
| 2022-07-25 | ARTO* +820/+684, BRMS +811/+596, TCPI -77/+119, BBYB -811/-730, FREN +1737/+1522 |
| 2023-01-25 | BUMI +378/-98, ADMR +0/-631, BRMS +640/+171, TCPI +55/-548, BIPI +36/-585 |
| 2023-07-26 | BUMI +119/+98, BRMS +347/+526, ADMR -612/-724, BIPI +378/+699, FREN -202/-392 |
| 2024-01-25 | BUMI -903/-774, BRMS -1408/-778, ADMR +86/+269, FILM +395/+579, MTEL* -70/+114 |
| 2024-04-24 | TPIA +630/+883, BUMI +2016/+1805, ADMR -650/-654, BRMS -883/-641, FILM +20/-91 |
| 2024-07-25 | TPIA -289/+167, BUMI -320/-50, BRMS -651/-291, ADMR -219/+94, PANI -570/-155 |
| 2024-10-25 | BREN -593/-489, TPIA -29/+75, CUAN -563/-183, PANI +298/+513, BUMI -102/+294 |
| 2025-01-22 | BREN +937/+632, TPIA +492/+187, BRMS -227/-548, PANI -3061/-3294, BUMI +176/+204 |
| 2025-04-24 | BREN +598/+172, BRMS -84/-681, TPIA +330/-96, PANI +1816/+1520, BUMI +577/-21 |
| 2025-07-25 | BREN -187/-337, BRMS -297/-177, TPIA -83/-233, PANI +1220/+1181, BUMI -241/-121 |
| 2025-10-27 | BRMS -1222/+132, BREN -474/-93, CUAN -1415/-61, PTRO -402/+1231, PANI -726/+628 |
| 2026-01-27 | BRMS -1132/-876, BREN* -1402/-317, CUAN -2357/-2058, PTRO -4356/-2900, TPIA -1018/+66 |
| 2026-04-24 | BRMS -442/-270, CUAN* -1800/-1115, DEWA* -1030/-477, PTRO -1522/-1440, ENRG -463/+163 |
| 2026-07-27 | BRMS -468/-392, BREN +119/+165, PTRO +1289/+1347, DSSA +114/+190, TPIA -219/-143 |

## Current ranking for the next review (announcement expected late Oct 2026, effective 2026-11-02)

Data through 2026-09-25 (the real cut-off is end-Sep). Top-10 eligible non-members: BRMS (0.989, overall #5), DSSA (0.980, overall #10), TPIA (0.976, overall #12), PTRO (0.972, overall #14), BREN (0.968, overall #19), ENRG (0.962, overall #20), EMAS (0.961, overall #21), CDIA (0.961, overall #22), TINS (0.958, overall #23), BUVA (0.949, overall #25).
Weakest current members: HRTA (#63), ITMG (#66), PGEO (#67), BBTN (#68), SCMA (#86).
## Reading (written after the run; study #191)

1. **The public rule cannot see the adds.** Precision@5 is 9 % (8 true adds in 90 picks), far under the ~30 % the trade needs; recall@5 16 %.
   The failure is structural, not noise: the rule's top non-members are the same names review after review - BRMS, TPIA, BUMI, PANI,
   BREN, PTRO, FREN, TCPI, ADMR - and IDX keeps passing them over (concentrated ownership / HSC, free float, financial condition, the IDX80
   committee's discretion). The actual adds sit at ranks #6-#29 among non-members. Two post-hoc checks (descriptive, never traded) do not
   rescue it: dropping names snubbed at the previous review lifts precision@5 only to 17 %; counting the 6 adds the rule marks ineligible (5 recent
   IPOs with short history in the 12-month window - MBMA, PGEO, PTMP, AMMN, AADI - plus BRIS 2022) as hits would give 16 %.
2. **So the trade is the jump diluted ~11x.** P1 (top-5, 5 sessions before the expected notice, out on the jump day): -207 bps net, -78 over
   matched controls, t -0.52; the placebo (random names from ranks 6-25) sits above it (real at pct 6). Every neighbour fails; the best, P2
   (T = 10), +246 excess at t 1.31, is one of seven arms and driven by a few big non-add movers (FREN, AGRO), not by adds. Costs x1.5 and the
   1-day delay change nothing. DSR ~0. **CLOSED.** No sleeve, so no correlation / combo run and no Rp contribution (it would be ~0).
3. **The prize is real if someone can predict better.** Perfect foresight (the actual adds, same window) earns +195 bps net, +433 over
   controls, t 4.19 over 17 reviews, 82 % positive - a pre-announcement run-up plus the jump. The whole problem is the classifier, which needs
   IDX's non-public inputs (HSC list, committee judgement) - not a data the desk has.
4. **Side finding for menu 36 (#186):** its event list missed the 2024-04 evaluation (AMMN, ISAT in; EMTK, PTMP out) and two fast
   entries (BUKA 2021-09, GOTO 2022-06); membership only chains consistently (45 names, ends on the published Aug-2026 list) with them
   added. Two more adds would not move its verdict (T1 t -0.11), but its sample is 50+2, not 51.
5. **Scope:** LQ45 only. IDX30 / IDX80 are the same IDX methodology (IDX30 drawn from LQ45, LQ45 from IDX80) and would inherit the same
   discretionary layer; MSCI Indonesia (quarterly, rule-based free-float market-cap cut-offs, far more mechanical) is the better candidate
   but needs MSCI's cut-off history and FIF data - future work, not sourced here. Pre-2024 April/October windows were not traded (whether
   LQ45 was reviewed then is not sourced; the membership chain shows no change in them).
6. The current ranking above (BRMS, DSSA, TPIA, PTRO, BREN ...) is recorded in study #191 as a watch list only - by this study's own
   result it is not a buy list.
