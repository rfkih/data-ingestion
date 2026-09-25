# IDX menu 36 (Track B1) - index rebalancing effect (LQ45) - 2026-09-25 - 7 trials, cumulative N = 856

**Verdict (adds, long): CLOSED.** Deletions as avoid-filter: not significant; deletion rebound: fails. Pre-registered in `research/idx_index_rebalance.py`.

Events: 17 LQ45 evaluations 2020-01 -> 2026-07 with changes, 51 adds / 51 deletions, sourced from the press (the table below). Codes without IDX bars: none.
Costs: closing offer/bid (open + tick for T2), fees 0.10/0.20 %, floor 70 bps round trip. Excess = net - mean net of 5 names matched on market cap and 60-day traded value at A. t = event-clustered (one mean per event).

## Arms (bps per trade; t over events)

| arm | trades | events | net mean | net median | win | controls | excess (event mean) | t (events) | t (trades) | events > 0 | days |
|---|---|---|---|---|---|---|---|---|---|---|---|
| T1_main | 48 | 16 | -183 | -105 | 33 % | -87 | -12 | -0.11 | -1.10 | 44 % | 2.9 |
| T2_next_open | 18 | 6 | -167 | -70 | 39 % | -131 | +41 | 0.23 | -0.26 | 33 % | 2.9 |
| T3_delay1 | 48 | 16 | -161 | -162 | 33 % | -72 | -54 | -0.54 | -1.18 | 31 % | 1.9 |
| T4_exit_E | 48 | 16 | -36 | -65 | 46 % | -102 | +116 | 1.15 | 0.72 | 50 % | 3.9 |
| T5_hold_E5 | 48 | 16 | -159 | -291 | 38 % | +69 | -172 | -1.29 | -1.53 | 25 % | 8.9 |
| T6_del_avoid | 48 | 16 | -205 | -136 | 21 % | -84 | -31 | -0.22 | -1.64 | 44 % | 2.9 |
| T7_del_rebound | 48 | 16 | -269 | -223 | 38 % | -97 | -208 | -1.18 | -1.03 | 44 % | 10.0 |
| T1 costs x1.5 | 48 | 16 | -233 | -169 | 23 % | -136 | -14 | -0.13 | -1.13 | 44 % | 2.9 |
| fact: day-0 reaction (A close->A+1 close, gross) | 48 | 16 | +368 | +346 | 77 % | -8 | +295 | 3.34 | 4.87 | 88 % | 1.0 |
| fact: 20-day pre-announcement run-up (gross) | 48 | 16 | +267 | +279 | 58 % | +417 | -51 | -0.23 | -0.73 | 50 % | 20.0 |

BAR (T1): excess > 0, t(events) >= 2.0, net > 0, >= 60 % events positive -> **FAIL**. N (T2/T3/T4 excess > 0, 2 of 3): pass; P (both placebos >= 95th pct): fail; T (both halves > 0): fail.

## Placebos (T1 excess, bps)

| placebo | real | median | 95th pct | real's percentile |
|---|---|---|---|---|
| random matched non-changed names (1000) | -12 | +1 | +140 | 43 |
| same adds, window shifted back 20-250 days (1000) | -12 | -1 | +163 | 45 |

## T1 by year and half

| block | trades | events | net | excess | t (events) |
|---|---|---|---|---|---|
| 2020 | 3 | 1 | -350 | -205 | nan |
| 2021 | 4 | 2 | +158 | +674 | 4.54 |
| 2022 | 8 | 2 | +35 | -48 | -0.28 |
| 2023 | 8 | 2 | -280 | -184 | -27.56 |
| 2024 | 7 | 3 | -489 | -232 | -0.79 |
| 2025 | 10 | 3 | -80 | -21 | -0.05 |
| 2026 | 8 | 3 | -270 | -35 | -0.34 |
| 2020-22 | 15 | 5 | -9 | +209 | 1.02 |
| 2023-26 | 33 | 11 | -261 | -112 | -0.90 |

## Per event (T1 adds; T6 deletions same window; bps)

| A (announced) | E (effective) | trading days A+1->R | adds: net / excess | dels: net / excess | source |
|---|---|---|---|---|---|
| 2020-01-27 | 2020-02-03 | 3 | - | - | cnbcindonesia.com/market/20200127170629-17-133126 |
| 2020-07-24 | 2020-08-03 | 3 | MDKA -461/-350, MIKA -72/+94, SMRA -517/-360 | BRPT -1394/-1487, LPPF -221/-650, WSKT -776/-682 | market.bisnis.com/read/20200724/7/1270916 |
| 2021-01-26 | 2021-02-01 | 2 | MEDC -107/+587, TPIA -239/+464 | SCMA -121/+262, SRIL -575/+7 | liputan6.com/saham/read/4466941; kontan 2021-02-01 |
| 2021-07-26 | 2021-08-02 | 3 | BRPT +947/+1532, TINS +32/+112 | BTPS -72/+394, CTRA -257/+57 | investasi.kontan.co.id ...agustus-2021-januari-2022-1 |
| 2022-01-25 | 2022-02-02 | 3 | AMRT +14/+11, BFIN +165/-290, EMTK +27/+174, HRUM -124/-867, WSKT -115/-116 | ACES +220/+272, AKRA -167/-586, BSDE -140/-80, JSMR -190/-179, PWON +160/+251 | cnbcindonesia.com/market/20220126113634-17-310544 |
| 2022-07-25 | 2022-08-01 | 3 | ARTO +98/+30, BRIS -70/+86, INDY +283/+248 | GGRM -442/-534, PTPP -125/-536, TKIM -30/-98 | market.bisnis.com/read/20220726/7/1559173 |
| 2023-01-25 | 2023-02-01 | 3 | ACES +11/+445, AKRA -713/-611, ESSA -327/-301, SCMA -377/-452, SIDO -291/-138, SRTG -233/-84 | BFIN +429/+445, ERAA -78/+200, HMSP -132/+143, MIKA +421/+502, MNCN -102/+57, WIKA +44/+262 | liputan6.com/saham/read/5189966 |
| 2023-07-26 | 2023-08-01 | 2 | GGRM -141/-58, MAPI -170/-296 | JPFA +525/+763, TINS -175/+498 | cnbcindonesia.com/market/20230726113525-17-457412 (article date) |
| 2024-01-25 | 2024-02-01 | 3 | MBMA -328/-426, MTEL -104/-404, PGEO -146/+65, PTMP -2730/-2438 | INDY +3/+3, SCMA -95/+136, TBIG -70/-15, TPIA -70/-67 | infobanknews.com; cnbcindonesia.com/research/20240126132147 |
| 2024-07-25 | 2024-08-01 | 3 | JSMR +156/+170 | SRTG +1602/+1426 | market.bisnis.com/read/20240725/7/1785475 |
| 2024-10-25 | 2024-11-01 | 3 | ADMR -481/-656, SMRA +205/+527 | GGRM -671/-683, HRUM -395/-506 | pusatdata.kontan.co.id ...1-november-2024-31-januari-2025 |
| 2025-01-22 | 2025-02-03 | 3 | CTRA -30/+478, JPFA +530/+1077, MAPA +347/+854 | BUKA -115/+31, INTP -479/-345, MTEL -727/-255 | pusatdata.kontan.co.id ...3-februari-30-april-2025 |
| 2025-07-25 | 2025-08-01 | 3 | AADI -390/-49, SCMA -594/-1002 | ESSA +91/-270, SIDO -224/+0 | market.bisnis.com/read/20250725/7/1896508 |
| 2025-10-27 | 2025-11-03 | 3 | BUMI -30/-631, DSSA -46/+42, EMTK -30/-387, HEAL -70/-451, NCKL -491/-272 | ARTO -548/-1040, BRIS -109/-46, JSMR -773/-1326, MAPA -311/-282, SMRA -121/-225 | indopremier.com ipotnews 477568 |
| 2026-01-27 | 2026-02-02 | 2 | BREN +201/+15 | ACES +72/+184 | antaranews.com/berita/5378378 (article date) |
| 2026-04-24 | 2026-05-04 | 3 | CUAN -984/-432, DEWA -210/+171, ESSA -1077/-819, HRTA -653/-404, WIFI +57/+306 | BREN -499/+86, CTRA -244/+27, DSSA -1362/-777, HEAL -490/-199, NCKL -863/-543 | bareksa.com/berita/saham/2026-04-24 |
| 2026-07-27 | 2026-08-03 | 3 | INDY +7/-150, NCKL +503/+378 | SMGR -205/-253, TOWR -30/-138 | market.bisnis.com/read/20260727/7/1991498 |

## Reading (written after the run; study #186)

1. **The tradable part of the index-add effect is zero on IDX.** Adds bought at the first close after the announcement and sold
   at the rebalance close lose -183 bps net per trade (33 % winners); their size/liquidity-matched controls lose -87 bps over the
   same 2-3 sessions, so the excess is -12 bps, t -0.11 over 16 events, positive in 7 of 16. Both placebos put it at the 43rd-45th
   percentile. Bar FAIL -> **CLOSED** for the long-adds sleeve. Costs x1.5 changes nothing (-14).
2. **The effect exists, but it is priced before anyone outside can trade it.** The announcement-day reaction (last close before
   the notice -> first close after) is +368 bps gross, +295 over controls, t 3.34, positive in 14 of 16 events - a real, large
   repricing. It happens at the next open: the literal next-OPEN entry (T2, the 6 events with IDX opens) keeps only +41 bps
   excess, t 0.23. The IDX window is also short (announcement -> effective is 4-7 sessions), so there is no drift left to harvest.
3. **After the effective date the adds give it back** (T5, exit E+5: -172 bps excess, 25 % of events positive) - consistent with
   a temporary price-pressure premium, but -1.3 t is not a short-side signal and the desk cannot short.
4. **Deletions:** neither an avoid-filter (T6: -31 bps excess, t -0.22) nor a rebound buy (T7: -208, t -1.18). Nothing to
   add to the book checks.
5. **Neighbours are noise around zero** (exit at E: +116, t 1.15; one-day delay: -54). T passes nowhere: 2020-22 +209, 2023-26 -112.
6. **Scope limits, stated:** LQ45 only (IDX30/IDX80/KOMPAS100/MSCI/FTSE not assembled); the 2020-01 event produced no trades
   (60-day liquidity window and share counts start 2020-01-02, so no controls); two announcement dates are article dates
   (2023-07, 2026-01), which can only delay the entry by a day - and day-0 already shows the premium is gone by then anyway.
   The only door left open is *predicting* the adds before the notice (the LQ45 rule is public: liquidity + free-float cap), which
   is a different strategy and a new menu, not a rescue of this one. No sleeve, so no correlation / combo run.
