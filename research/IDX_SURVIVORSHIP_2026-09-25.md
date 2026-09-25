# IDX survivorship bias (Track A2) - 2026-09-25

Data study (0 trials; cumulative stays 849). Script `research/idx_survivorship.py`; staged rows `tmp/delisted_bars.parquet`.

## Findings

1. **The premise was wrong: idx.bar is NOT missing delisted names.** IDX's own delisting statistic (primary/DigitalStatistic LINK_DELISTING, every month 2020-01..2026-09) lists 25 codes; add FREN (merged into EXCL/XLSMART 2025-04, not in that statistic) = 26, and those are exactly the 26 codes whose last idx.bar is before 2026-09. Each has its full 2020+ life in idx.bar and idx.daily_summary through the day before delisting. IDX delisted 6 names in 2020, 1 in 2021 (FINN), 0 in 2022, 1 in 2023 (TURI), 1 in 2024 (RMBA) - confirmed by CNBC Indonesia (2025-07-22: '2021, 2023 dan 2024 masing-masing 1 emiten ... 2022 tidak ada'). The day dumps are complete snapshots: IDX GetStockSummary for 2021-01-04 returns 717 rows = our 717. The 'missing 2021-2024 delistings' simply did not happen; IDX let distressed names sit suspended (they are in the data as zero-volume rows) and delisted them in batches (2025-07-18: 12 codes; the 2026-04 decision on 18 more takes effect ~2026-11).
2. **Coverage 26/26. Nothing to insert.** Every delisted code/date already exists in idx.bar with source 'idx' (PK code, trade_date); an INSERT-only backfill would add 0 rows, so none was run and there is no rollback SQL. tmp/delisted_bars.parquet holds the 26 codes' existing rows (bar + summary columns) for inspection only.
3. **Only one delisted name was ever tradable by the books:** FREN (60-day median value >= Rp 5 bn on 967 days, 157 of them inside LIQ with close >= Rp 100). Every other delisted name had max 60-day median value < Rp 5 bn - the forced delistings were suspended/zero-volume for years before the event, the go-privates were thin. The Rp 5 bn floor already filtered them out.
4. **The real leak is a different one: the research panels (`idx_swing2.panels`, used by idx_exit/idx_combo_rupiah/every trend study) keep codes by their CURRENT `idx.listing.board`**, not the board on the day. That drops the 26 delisted codes (board NULL) AND every name that is on Pemantauan Khusus / Akselerasi / Ekonomi Baru today - for all of 2020-2026. 49 names that were liquid Utama/Pengembangan names at the time (WIKA, WSKT, MLIA, MPPA, WSBP, BUKA, INAF, SRIL, ...; the ones that later failed) are excluded from history, while 41 names that were on Akselerasi/PK on the day but are Utama/Pengembangan now (GOTO, CUAN, BREN, ...) are included. That is look-ahead survivorship, and it is measured below as U2 (board on the day from `daily_summary.remarks`; the 2020-01..07 old notation's last character agrees 696/696 with the new 5th character on the switch day).
5. **Size of the bias** (only the universe mask changes; data, engine, costs, rules identical):
   - delisting fix alone (U1): trend `small` CAGR -0.4/-0.5 pp, Sharpe -0.01; EW-LIQ ~0. Negligible.
   - point-in-time board (U2): trend `small` 2022-> CAGR 26.5 -> 24.1 % (-2.4 pp), Sharpe 1.34 -> 1.21, mDD 18.2 -> 17.5 %; 2020-> CAGR -0.1 pp, Sharpe -0.05. EW-LIQ baseline CAGR 9.6 -> 6.6 % (-3.0 pp), Sharpe 0.53 -> 0.41. The trend rule is robust to it (trend filters mostly skip names on their way down), the passive baseline is not.
   - Read: the published trend numbers are overstated by ~2-3 pp CAGR / ~0.1 Sharpe on the 2022+ window; the strategy verdicts do not flip. Recommendation (not done - code change outside this study's remit): make the research panels mask by board on the day (the `pit_board` function here) instead of `idx.listing.board`.
6. EW-ALL-traded (no liquidity floor, forced delistings get a -100 % day) is descriptive: its level is inflated by daily rebalancing of illiquid names (bid-ask bounce); its U2 delta (-4.0 pp CAGR) is again the board filter, not the delistings (the forced names had not traded for years, so the -100 % day lands on no weight).
7. FREN in the books is valued at its last IDX close (23) when the bars stop; holders actually received EXCL shares, so this is an approximation; no book held FREN at the merger in any run (0 open positions at the end).

## Delistings 2020-01 .. 2026-09

| code | name | IDX delisting date | last bar | bars | traded days | max v60 (Rp bn) | days v60>=5bn | reason |
|---|---|---|---|---|---|---|---|---|
| BORN | Borneo Lumbung Energi & Metal Tbk. | 2020-01-20 | 2020-01-17 | 12 | 0 | 0.00 | 0 | forced (long suspension) |
| ITTG | Leo Investments Tbk. | 2020-01-23 | 2020-01-22 | 15 | 0 | 0.00 | 0 | forced (long suspension) |
| APOL | Arpeni Pratama Ocean Line Tbk. | 2020-04-06 | 2020-04-03 | 66 | 0 | 0.00 | 0 | forced (long suspension) |
| SCBD | Danayasa Arthatama Tbk. | 2020-04-20 | 2020-04-17 | 75 | 0 | 0.00 | 0 | voluntary go-private |
| CKRA | Cakra Mineral Tbk. | 2020-08-28 | 2020-08-27 | 159 | 0 | 0.00 | 0 | forced (long suspension) |
| GREN | Evergreen Invesco Tbk. | 2020-11-23 | 2020-11-20 | 217 | 0 | 0.00 | 0 | forced (long suspension) |
| FINN | First Indo American Leasing Tbk. | 2021-05-05 | 2021-05-04 | 326 | 0 | 0.00 | 0 | forced (long suspension) |
| TURI | Tunas Ridean Tbk. | 2023-04-06 | 2023-04-05 | 800 | 495 | 0.39 | 0 | voluntary go-private (tender offer) |
| RMBA | Bentoel Internasional Investama Tbk. | 2024-01-16 | 2024-01-15 | 984 | 368 | 0.05 | 0 | voluntary go-private (BAT tender offer) |
| FREN | Smartfren Telecom Tbk. | - | 2025-04-16 | 1276 | 1274 | 198.50 | 967 | merger into EXCL (XLSMART); shares converted, not in IDX delisting statistic |
| FORZ | Forza Land Indonesia Tbk. | 2025-07-18 | 2025-07-18 | 1334 | 318 | 0.00 | 0 | forced (bankruptcy / 24+ months suspended), IDX batch 2025-07-21 |
| PRAS | Prima Alloy Steel Universal Tbk. | 2025-07-18 | 2025-07-18 | 1334 | 951 | 0.24 | 0 | forced (bankruptcy / 24+ months suspended), IDX batch 2025-07-21 |
| NIPS | Nipress Tbk. | 2025-07-18 | 2025-07-18 | 1334 | 0 | 0.00 | 0 | forced (bankruptcy / 24+ months suspended), IDX batch 2025-07-21 |
| MYRXP | Saham Seri B Hanson International Tbk. | 2025-07-18 | 2025-07-18 | 1334 | 3 | 0.00 | 0 | forced (bankruptcy / 24+ months suspended), IDX batch 2025-07-21 |
| MYRX | Hanson International Tbk. | 2025-07-18 | 2025-07-18 | 1334 | 10 | 0.00 | 0 | forced (bankruptcy / 24+ months suspended), IDX batch 2025-07-21 |
| MAMIP | Mas Murni Tbk (Saham Preferen) | 2025-07-18 | 2025-07-18 | 1334 | 0 | 0.00 | 0 | forced (bankruptcy / 24+ months suspended), IDX batch 2025-07-21 |
| KRAH | Grand Kartech Tbk. | 2025-07-18 | 2025-07-18 | 1334 | 118 | 0.00 | 0 | forced (bankruptcy / 24+ months suspended), IDX batch 2025-07-21 |
| KPAS | Cottonindo Ariesta Tbk. | 2025-07-18 | 2025-07-18 | 1334 | 397 | 0.66 | 0 | forced (bankruptcy / 24+ months suspended), IDX batch 2025-07-21 |
| JKSW | Jakarta Kyoei Steel Works Tbk. | 2025-07-18 | 2025-07-18 | 1334 | 0 | 0.00 | 0 | forced (bankruptcy / 24+ months suspended), IDX batch 2025-07-21 |
| HDTX | Panasia Indo Resources Tbk. | 2025-07-18 | 2025-07-18 | 1334 | 0 | 0.00 | 0 | forced (bankruptcy / 24+ months suspended), IDX batch 2025-07-21 |
| MAMI | Mas Murni Indonesia Tbk | 2025-07-18 | 2025-07-18 | 1334 | 391 | 0.01 | 0 | forced (bankruptcy / 24+ months suspended), IDX batch 2025-07-21 |
| KPAL | Steadfast Marine Tbk. | 2025-07-18 | 2025-07-18 | 1334 | 389 | 0.20 | 0 | forced (bankruptcy / 24+ months suspended), IDX batch 2025-07-21 |
| MFIN | Mandala Multifinance Tbk. | 2025-10-02 | 2025-10-01 | 1385 | 1285 | 4.40 | 0 | voluntary go-private after mandatory tender offer |
| MASA | Multistrada Arah Sarana Tbk. | 2025-10-30 | 2025-10-29 | 1405 | 977 | 0.17 | 0 | voluntary go-private (tender offer) |
| CNTB | Saham Seri B ( Centex Tbk ) | 2026-07-30 | 2026-07-29 | 1580 | 0 | 0.00 | 0 | voluntary go-private (series B of CNTX) |
| CNTX | Century Textile Industry Tbk. | 2026-07-30 | 2026-07-29 | 1580 | 714 | 0.02 | 0 | voluntary go-private |

Coverage: 26 / 26 delisted codes have their full 2020+ life in idx.bar (25888 rows staged).

## Universe exposure (name-days 2020-01-02 .. 2026-09-16)

| universe | LIQ name-days | small name-days | names ever in LIQ |
|---|---|---|---|
| U0_asrun | 204510 | 127911 | 442 |
| U1_plus_dead | 204667 | 128068 | 443 |
| U2_pit_board | 212416 | 134956 | 490 |

Delisted names ever in LIQ: {'FREN': 157}; ever in small: {'FREN': 157}.

LIQ names in the PIT universe but dropped by the as-run filter: 49 (top by LIQ days: WIKA 1008d now Pemantauan Khusus, WSKT 707d now Pemantauan Khusus, MLIA 486d now Pemantauan Khusus, MPPA 452d now Pemantauan Khusus, ZINC 441d now Pemantauan Khusus, MARI 412d now Pemantauan Khusus, BEBS 377d now Pemantauan Khusus, WSBP 345d now Pemantauan Khusus, TECH 340d now Pemantauan Khusus, HILL 332d now Pemantauan Khusus, ABBA 270d now Pemantauan Khusus, BUKA 269d now Ekonomi Baru, IPTV 266d now Pemantauan Khusus, PMMP 253d now Pemantauan Khusus, POLL 246d now Pemantauan Khusus, PURA 225d now Pemantauan Khusus, ACST 192d now Pemantauan Khusus, FREN 157d now None, INAF 145d now Pemantauan Khusus, BIKE 144d now Pemantauan Khusus, JSKY 139d now Pemantauan Khusus, SRIL 132d now Pemantauan Khusus, TOYS 128d now Pemantauan Khusus, KREN 127d now Pemantauan Khusus, KAYU 125d now Pemantauan Khusus, IPPE 123d now Pemantauan Khusus, WMPP 97d now Pemantauan Khusus, SWAT 79d now Pemantauan Khusus, ZBRA 77d now Pemantauan Khusus, RAFI 74d now Pemantauan Khusus)
LIQ names in the as-run universe but not PIT (on Akselerasi/PK on the day, since promoted): 41 (GOTO 131d, SINI 109d, CUAN 66d, LPPF 61d, UVCR 51d, GIAA 41d, COCO 41d, INET 21d, BNBR 20d, PTPS 20d, BELI 19d, DOOH 16d, BREN 15d, FILM 14d, BUVA 14d, MINA 13d, JARR 10d, TEBE 7d, AYAM 7d, BEEF 7d)

## Bias

| book | window | universe | from | CAGR | Sharpe | mDD | trades | dead names traded |
|---|---|---|---|---|---|---|---|---|
| trend_small | from2020 | U0_asrun | 2020-11-04 | +34.2 % | 1.53 | -18.2 % | 385 | - |
| trend_small | from2022 | U0_asrun | 2022-01-04 | +26.5 % | 1.34 | -18.2 % | 270 | - |
| ew_liq | from2020 | U0_asrun | 2020-03-27 | +9.6 % | 0.53 | -45.4 % | - | - |
| ew_liq | from2022 | U0_asrun | 2022-01-03 | -4.0 % | -0.10 | -45.4 % | - | - |
| ew_all_traded | from2020 | U0_asrun | 2020-01-03 | +23.7 % | 1.56 | -33.2 % | - | - |
| trend_small | from2020 | U1_plus_dead | 2020-11-04 | +33.8 % | 1.52 | -18.6 % | 387 | FREN |
| trend_small | from2022 | U1_plus_dead | 2022-01-04 | +26.1 % | 1.33 | -18.6 % | 271 | FREN |
| ew_liq | from2020 | U1_plus_dead | 2020-03-27 | +9.6 % | 0.53 | -45.4 % | - | - |
| ew_liq | from2022 | U1_plus_dead | 2022-01-03 | -4.1 % | -0.10 | -45.4 % | - | - |
| ew_all_traded | from2020 | U1_plus_dead | 2020-01-03 | +23.7 % | 1.57 | -33.2 % | - | - |
| trend_small | from2020 | U2_pit_board | 2020-11-04 | +34.1 % | 1.47 | -17.5 % | 407 | FREN |
| trend_small | from2022 | U2_pit_board | 2022-01-04 | +24.1 % | 1.21 | -17.5 % | 282 | FREN |
| ew_liq | from2020 | U2_pit_board | 2020-03-27 | +6.6 % | 0.41 | -46.0 % | - | - |
| ew_liq | from2022 | U2_pit_board | 2022-01-03 | -5.9 % | -0.19 | -46.0 % | - | - |
| ew_all_traded | from2020 | U2_pit_board | 2020-01-03 | +19.7 % | 1.36 | -33.1 % | - | - |

Deltas vs U0 (as-run):

- trend_small from2020 U1_plus_dead: CAGR -0.4 pp, Sharpe -0.01, mDD -0.4 pp
- trend_small from2022 U1_plus_dead: CAGR -0.5 pp, Sharpe -0.01, mDD -0.4 pp
- ew_liq from2020 U1_plus_dead: CAGR -0.1 pp, Sharpe -0.00, mDD -0.0 pp
- ew_liq from2022 U1_plus_dead: CAGR -0.0 pp, Sharpe -0.00, mDD -0.0 pp
- ew_all_traded from2020 U1_plus_dead: CAGR +0.0 pp, Sharpe +0.01, mDD +0.0 pp
- trend_small from2020 U2_pit_board: CAGR -0.1 pp, Sharpe -0.05, mDD +0.7 pp
- trend_small from2022 U2_pit_board: CAGR -2.4 pp, Sharpe -0.12, mDD +0.7 pp
- ew_liq from2020 U2_pit_board: CAGR -3.0 pp, Sharpe -0.13, mDD -0.6 pp
- ew_liq from2022 U2_pit_board: CAGR -1.8 pp, Sharpe -0.09, mDD -0.6 pp
- ew_all_traded from2020 U2_pit_board: CAGR -4.0 pp, Sharpe -0.20, mDD +0.1 pp

Trend-book traded codes, U2 vs U0: {"from2020": {"only_U2": ["ABBA", "BEKS", "FREN", "KAYU", "KREN", "MARI", "MDLN", "MLIA", "MPPA", "POLL", "PURA", "TOYS", "WIKA", "WSBP", "WSKT", "ZINC"], "only_U0": ["GOTO", "IMAS", "PTPP"]}, "from2022": {"only_U2": ["ABBA", "FREN", "KAYU", "LPKR", "MDLN", "MLIA", "WIKA"], "only_U0": ["GOTO", "PTPP"]}}

