# IDX menu 44 - defensive carry sleeve (low vol + dividend carry) for breadth - 2026-09-26 - 8 trials (968..975), cumulative N = 975

Script `research/idx_defensive.py` (pre-registration in its docstring). Rp 20 M standalone unless stated; quarterly (first trading day of Feb/May/Aug/Nov), 20 names, liquid main-board universe (point-in-time board), closing bid/offer + Stockbit fees, lots of 100, dividends on the ex-date net of 10 % tax. Sleeve window 2021-02-01 -> 2026-09-25. Universe at rebalances: 112..185 names (median 134). Cells CAGR / Sharpe / mDD.

## Standalone vs benchmarks (same window)

| book | full | half 1 Sharpe | half 2 Sharpe | Rp 200 M | turnover/yr | DSR@975 | placebo pct |
|---|---|---|---|---|---|---|---|
| D1 | 4.5 % / 0.42 / -24.1 % | 0.67 | 0.25 | 4.9 % / 0.43 / -26.2 % | 125 % | 0.01 | 90 |
| D2 | 12.5 % / 0.88 / -22.7 % | 1.02 | 0.80 | 11.9 % / 0.85 / -21.7 % | 122 % | 0.11 | 100 |
| D3 | 13.3 % / 0.95 / -22.1 % | 1.11 | 0.82 | 11.6 % / 0.85 / -21.3 % | 127 % | 0.14 | 100 |
| D3_vol126 | 11.1 % / 0.81 / -22.0 % | 0.79 | 0.86 | - | 128 % | nan | nan |
| D3_n10 | 15.1 % / 0.97 / -20.8 % | 0.94 | 1.01 | - | 164 % | nan | nan |
| D3_n30 | 8.1 % / 0.65 / -21.0 % | 0.76 | 0.58 | - | 113 % | nan | nan |
| D3_monthly | 12.6 % / 0.89 / -21.3 % | 1.05 | 0.79 | - | 215 % | nan | nan |
| COMPOSITE_TR (proxy) | 3.4 % / 0.30 / -40.6 % | 0.76 | 0.02 | - | - | - | - |
| COMPOSITE (price) | 0.5 % / 0.11 / -41.5 % | 0.52 | -0.14 | - | - | - | - |
| LQ45 (price) | -7.2 % / -0.33 / -51.4 % | 0.01 | -0.57 | - | - | - | - |
| IDXHIDIV20 (price) | -0.5 % / 0.07 / -39.8 % | 0.64 | -0.34 | - | - | - | - |

By year (Rp 20 M): D1 21:+6 22:+13 23:+1 24:-7 25:+17 26:-3; D2 21:+16 22:+6 23:+17 24:+1 25:+24 26:+8; D3 21:+17 22:+10 23:+16 24:+3 25:+23 26:+7; COMPOSITE_TR 21:+11 22:+7 23:+10 24:+0 25:+26 26:-26.

Placebo (200 random 20-name liquid books, same dates, Rp 20 M): Sharpe median 0.08, p95 0.47.

## Added to the deployed combo (Rp 20 M total; sleeve simulated at its own capital; same run)

Combo (#192 d, recreated): 33.8 % / 1.83 / -17.9 %; halves (split 2024-05-10): 14.5 % / 1.25 / -10.5 % | 56.4 % / 2.27 / -17.9 %. Planning CAGR 19.7 %, 3-year planning drawdown median -18.1 %, 1-in-10 -26.1 %.

| arm | corr w/ combo | share | blend full | blend H1 | blend H2 | halves pass | plan 3y 1-in-10 | Rp 200 M total full |
|---|---|---|---|---|---|---|---|---|
| D1 | 0.39 | 20 % | 27.6 % / 1.76 / -16.2 % | 11.8 % / 1.20 / -8.4 % | 45.7 % / 2.18 / -16.2 % | 0/2 | -23.7 % | 27.8 % / 1.74 / -16.2 % |
| D1 | 0.39 | 33 % | 24.1 % / 1.66 / -14.7 % | 10.1 % / 1.11 / -7.7 % | 40.0 % / 2.08 / -14.7 % | 0/2 | -23.3 % | 24.1 % / 1.65 / -15.0 % |
| D2 | 0.31 | 20 % | 28.9 % / 1.82 / -15.4 % | 12.5 % / 1.24 / -10.0 % | 47.8 % / 2.26 / -15.4 % | 0/2 | -23.1 % | 29.4 % / 1.83 / -15.5 % |
| D2 | 0.31 | 33 % | 26.1 % / 1.79 / -13.8 % | 11.5 % / 1.21 / -9.4 % | 42.6 % / 2.22 / -13.8 % | 0/2 | -22.1 % | 26.6 % / 1.80 / -13.8 % |
| D3 | 0.32 | 20 % | 28.6 % / 1.80 / -15.4 % | 12.5 % / 1.24 / -10.1 % | 47.0 % / 2.22 / -15.4 % | 0/2 | -23.3 % | 29.3 % / 1.83 / -15.5 % |
| D3 | 0.32 | 33 % | 25.9 % / 1.78 / -13.8 % | 11.7 % / 1.24 / -9.4 % | 42.0 % / 2.20 / -13.8 % | 0/2 | -22.2 % | 26.3 % / 1.79 / -13.8 % |
| D3_vol126 | 0.32 | 20 % | 28.6 % / 1.80 / -15.5 % | 12.4 % / 1.24 / -9.8 % | 47.1 % / 2.22 / -15.5 % | 0/2 | - | - |
| D3_vol126 | 0.32 | 33 % | 26.2 % / 1.80 / -13.9 % | 12.1 % / 1.29 / -9.2 % | 42.1 % / 2.19 / -13.9 % | 0/2 | - | - |
| D3_n10 | 0.28 | 20 % | 30.4 % / 1.89 / -15.5 % | 15.4 % / 1.45 / -8.7 % | 47.5 % / 2.25 / -15.5 % | 0/2 | - | - |
| D3_n10 | 0.28 | 33 % | 27.9 % / 1.88 / -13.6 % | 15.1 % / 1.50 / -8.4 % | 42.2 % / 2.20 / -13.6 % | 1/2 | - | - |
| D3_n30 | 0.35 | 20 % | 28.5 % / 1.80 / -15.7 % | 12.4 % / 1.24 / -8.7 % | 47.0 % / 2.22 / -15.7 % | 0/2 | - | - |
| D3_n30 | 0.35 | 33 % | 25.0 % / 1.72 / -14.0 % | 10.9 % / 1.19 / -8.2 % | 41.0 % / 2.13 / -14.0 % | 0/2 | - | - |
| D3_monthly | 0.30 | 20 % | 28.6 % / 1.81 / -14.9 % | 12.5 % / 1.25 / -10.1 % | 47.1 % / 2.24 / -14.9 % | 0/2 | - | - |
| D3_monthly | 0.30 | 33 % | 26.2 % / 1.81 / -13.6 % | 11.9 % / 1.26 / -10.1 % | 42.2 % / 2.23 / -13.6 % | 0/2 | - | - |

## Reading rule per arm

| arm | (a) CAGR>COMP TR & Sharpe+0.2 both halves | (b) corr<0.5 | (c) blends 20/33 % both halves + plan dd | placebo>=95 | costs x1.5 | neighbours | long 2010-19 | verdict |
|---|---|---|---|---|---|---|---|---|
| D1 | no (full no, halves [False, True]) | yes (0.39) | no | 90 | fail (4.2 % / 0.39 / -25.0 %) | n/a | fail | **CLOSED** |
| D2 | yes (full yes, halves [True, True]) | yes (0.31) | no | 100 | fail (12.3 % / 0.87 / -23.0 %) | n/a | fail | **CLOSED** |
| D3 | yes (full yes, halves [True, True]) | yes (0.32) | no | 100 | fail (12.5 % / 0.89 / -22.6 %) | 1/4 | fail | **CLOSED** |

Neighbours (on D3; agree = (a) full, (b), 20 % blend full-window Sharpe >= combo and mDD >= 2 pp shallower): D3_vol126 11.1 % / 0.81 / -22.0 %, corr 0.32, blend20 28.6 % / 1.80 / -15.5 % -> no; D3_n10 15.1 % / 0.97 / -20.8 %, corr 0.28, blend20 30.4 % / 1.89 / -15.5 % -> agree; D3_n30 8.1 % / 0.65 / -21.0 %, corr 0.35, blend20 28.5 % / 1.80 / -15.7 % -> no; D3_monthly 12.6 % / 0.89 / -21.3 %, corr 0.30, blend20 28.6 % / 1.81 / -14.9 % -> no. 1/4 agree.

## Crash behaviour (period return)

| window | D1 | D2 | D3 | combo | D3 blend 20 % | COMPOSITE | IDXHIDIV20 |
|---|---|---|---|---|---|---|---|
| 2020-03 covid | - | - | - | - | - | -33.6 % | -40.1 % |
| 2024-09 -> 2025-04 drawdown | -23.0 % | -20.9 % | -20.4 % | +7.2 % | +1.2 % | -24.2 % | -29.1 % |
| 2026-01-27 -> 02-02 | -8.7 % | -4.5 % | -4.5 % | -15.6 % | -13.6 % | -11.7 % | -5.2 % |
| 2020-02-19 -> 03-24 (975, Yahoo survivors, D1 price only) | -38.1 % | n/a | n/a | n/a | n/a | JKSE -33.6 % | n/a |

## Long history (trial 975): D1 on the Yahoo cache 2010-02 -> 2019-12 - SURVIVORSHIP-BIASED (450 names that still exist), price only

D1 7.4 % / 0.49 / -32.5 % vs JKSE (price) 9.4 % / 0.64 / -25.4 %; random 20-name survivor books Sharpe median 0.28, p95 0.50 (D1 at pct 94). Names in the cache: 142 (2010) -> 266 (2019). 2020 full year D1 -7.9 % vs JKSE -5.1 %. Read: FAIL (Sharpe >= JKSE + 0.2 and mDD shallower). Missing dividends understate D1 by roughly its yield; survivors overstate it.

## Data checks

- Dividend coverage: of 1382 FY reports of ever-liquid names with dividends paid in the cash-flow statement, 1050 (76 %) have a Yahoo event in idx.dividend within 15 months. Market TR-proxy dividend yield by year: 2020 2.4 %, 2021 1.9 %, 2022 2.6 %, 2023 3.3 %, 2024 3.0 %, 2025 2.5 %, 2026 2.4 %.
- D3 gate diagnostics (low-vol half size / with a usable report / failed): 2021-01-29 67/65/9; 2021-04-30 66/65/8; 2021-07-30 67/67/5; 2021-10-29 71/71/8; 2022-01-31 71/71/9; 2022-04-28 71/71/7; 2022-07-29 68/68/13; 2022-10-31 71/71/11; 2023-01-31 62/62/12; 2023-04-28 57/57/11; 2023-07-31 66/66/13; 2023-10-31 61/61/6; 2024-01-31 58/58/2; 2024-04-30 59/59/4; 2024-07-31 56/56/3; 2024-10-31 68/68/5; 2025-01-31 61/61/4; 2025-04-30 60/60/3; 2025-07-31 70/70/4; 2025-10-31 83/83/10; 2026-01-30 92/92/10; 2026-04-30 84/84/13; 2026-07-31 70/70/9.

## Overlap with the value book (#66 strict composite, May holdings)

- D1: 2021-05-03 3/10 (ASII, INDF, TLKM); 2022-05-09 4/12 (BJBR, BJTM, DMAS, INDF); 2023-05-02 1/12 (BBTN); 2024-05-02 2/10 (ASII, PGAS); 2025-05-02 5/12 (ASII, BNGA, ELSA, NISP, PTBA); 2026-05-04 8/15 (AUTO, BBNI, BBRI, BNGA, GJTL, INDF, NISP, PWON)
- D2: 2021-05-03 5/10 (ASII, DMAS, INDF, PTBA, TLKM); 2022-05-09 6/12 (ADRO, BJBR, BJTM, DMAS, INDF, JPFA); 2023-05-02 5/12 (AUTO, MPMX, PGAS, PTBA, UNTR); 2024-05-02 7/10 (ADRO, ASII, ELSA, ITMG, NISP, PGAS, PTBA); 2025-05-02 9/12 (ASII, AUTO, BNGA, ELSA, ITMG, NISP, PTBA, TAPG, UNTR); 2026-05-04 7/15 (AUTO, BBNI, BBRI, BFIN, BNGA, BTPS, UNTR)
- D3: 2021-05-03 5/10 (AKRA, ASII, INDF, PTBA, TLKM); 2022-05-09 6/12 (ADRO, BJBR, BJTM, DMAS, INDF, JPFA); 2023-05-02 4/12 (AUTO, PGAS, PTBA, UNTR); 2024-05-02 7/10 (ADRO, ASII, ELSA, ITMG, NISP, PGAS, PTBA); 2025-05-02 9/12 (ASII, AUTO, BNGA, ELSA, ITMG, NISP, PTBA, TAPG, UNTR); 2026-05-04 6/15 (AUTO, BBNI, BBRI, BFIN, BNGA, BTPS)

## Holdings (last three rebalances)

- D1: 2026-02-02: AALI ASII AUTO AVIA BBCA BFIN BNGA GJTL ICBP INDF ITMG JSMR MARK PGAS PTBA PWON SIDO SMRA ULTJ | 2026-05-04: AALI AUTO AVIA BBCA BBNI BBRI BMRI BNGA GJTL ICBP INDF JSMR LPPF NISP PTBA PWON SIDO SMRA ULTJ | 2026-08-03: AALI ACES BBCA BBNI BBRI BMRI BNGA CMNT CTRA DMAS ERAA ICBP INDF JSMR MIKA MTEL PTBA PWON SIDO
- D2: 2026-02-02: AADI ACES ADRO AKRA AUTO BBNI BBRI BFIN BMRI BNGA EXCL ITMG MAHA MARK PGAS PTBA SIDO TAPG UNTR UNVR | 2026-05-04: AALI ACES ADRO AUTO BBNI BBRI BFIN BNGA BTPS HMSP LPPF MARK PGAS PGEO PTBA SIDO TAPG TLKM UNTR UNVR | 2026-08-03: AADI ACES ADRO ASII BBNI BBRI BFIN BMRI BNGA DMAS ESSA HMSP INTP MARK PGAS SIDO SSMS TAPG TLKM UNVR
- D3: 2026-02-02: AADI ACES ADRO AKRA AUTO BBNI BBRI BFIN BMRI BNGA HMSP ITMG MAHA MARK PGAS PTBA SIDO TAPG UNTR UNVR | 2026-05-04: AALI ACES ADRO ASII AUTO BBNI BBRI BFIN BNGA BTPS HMSP ITMG LPPF MARK PGAS PGEO PTBA SIDO TAPG TLKM | 2026-08-03: AADI ACES ADRO ASII BBNI BBRI BFIN BMRI BNGA DMAS ESSA HMSP INTP MARK PGAS SIDO SSMS TAPG TLKM UNVR

## Reading (written after the run)

1. **All three arms are CLOSED by the pre-registered rule; nothing to wire.** The carry leg is real as a standalone book: D2/D3 are
   12.5-13.3 % / 0.88-0.95 against the COMPOSITE TR proxy's 3.4 % / 0.30, and placebo pct 100. Low vol alone (D1, 4.5 % / 0.42) is not,
   and it failed 2010-19 as well (Yahoo survivors: 7.4 % / 0.49 vs JKSE 9.4 % / 0.64, deeper mDD). The whole return comes from the dividend-carry selection.
2. **It does not add breadth to the combo.** Correlation is low (0.31-0.32), but the sleeve carries equity beta the combo does not carry (the combo
   holds >= 30 % cash). At 20 %/33 %, full-window Sharpe goes 1.83 -> 1.80-1.82 and mDD -17.9 -> -15.4/-13.8 %, but in H1 the mDD gain is only
   0.4-1.1 pp and Sharpe is lower in both halves. The planning 3-year 1-in-10 drawdown improves (-26.1 -> -23.3/-22.2 %), but the CAGR cost is
   larger (33.8 -> 28.6/25.9 %). That is de-risking at a price, the same trade as simply holding more cash, not a new return driver.
3. **Crash behaviour contradicts the "defensive" label on IDX.** In the 2024-09 -> 2025-04 drawdown D2/D3 fell -21/-20 % (COMPOSITE -24 %,
   IDXHIDIV20 -29 %) while the combo made +7 %. In the 2026-01-27 -> 02-02 flush they fell -4.5 % against the combo's -15.6 %, the only window where they helped.
   In 2020-03 D1 (survivors) fell -38 %, more than JKSE (-34 %). IDX low-vol/high-yield names are foreign-held large caps, the names foreigners sell first.
4. "costs x1.5 fail" for D2/D3 comes from the 20 % blend test (it already fails at base costs), not from cost sensitivity: standalone at x1.5 is
   12.3 % / 0.87 and 12.5 % / 0.89. Dividend data: Yahoo covers 76 % of fiscal years where a dividend was paid, so the carry return is understated, not overstated.
5. Overlap with the value book is 4-9 of 10-15 names from 2023 onward (PTBA, ADRO, ITMG, UNTR, ASII, NISP, BNGA...): a dividend screen on IDX
   picks up much of the cheap-value book, so the breadth is less than it looks.
