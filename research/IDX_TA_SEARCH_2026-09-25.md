# IDX menu 43 - technical-indicator search (desk chart catalog, alone and combined) - 2026-09-25

Study `ta_search`. 26 counted trials (ids 917..942); cumulative N 916 -> 942 (ledger max before the run = 916, #192; the caller quoted 915). Stage 0 screening (55 readings x 3 horizons) is NOT counted. Script `research/idx_ta_search.py` (pre-registration + addenda A and STAGE1_FROZEN in its docstring), port `research/idx_ta_lib.py`, intermediate files research-scratch/ta_stage0/1/2.json, ta_frozen.json.

## Verdict

- **R10 -> PARTIAL**. OOS 2024-01..2026-09-16 14.4 % / 0.61 / -53.8 % (297 trades); placebo pct 96; passes P, N, T_oos, C; fails T_long, D; DSR 0.01 @ N 942 (0.15 @ search size 26).
- **R05 -> FRAGILE**. OOS 2024-01..2026-09-16 -1.7 % / 0.12 / -62.0 % (385 trades); placebo pct 70; passes none; fails P, N, T_oos, T_long, C, D; DSR 0.00 @ N 942 (0.03 @ search size 26).
- **R21 -> CLOSED**. OOS 2024-01..2026-09-16 29.1 % / 1.34 / -17.5 % (148 trades); placebo pct 39; passes T_long; fails P, N, T_oos, C, D; DSR 0.14 @ N 942 (0.57 @ search size 26).

Nothing is deployable. R10 is PARTIAL only by the letter of the pre-registered rule. It beats random entries (pct 96) and 3 of 4 neighbours, but it earns its whole OOS return in 2025 (+116 %, then -38 % in 2026 YTD). A one-day-late fill kills it (Sharpe 0.61 -> 0.07), its drawdown is -54 %, the DSR is 0.01, and as a 4th sleeve it cuts the combo book's CAGR from 33.8 % to 19.6 %. R05 is FRAGILE on every check. R21 (CMF > 0 on the trend entry) is CLOSED on its pre-registered test: its OOS delta Sharpe on the trend book is negative (-0.29) and below the random-filter median. It does lift the combo book (37.5 % / 2.03 / -15.5 % vs 33.8 % / 1.83 / -17.9 %), but that gain sits mostly in 2022 (in-sample), 2024+ moves only 54.6 % -> 56.9 %, and 3 of 4 neighbours lose. Do not wire it.

## Data notes (read before quoting)

- Port check: all 79 plots of the TS catalog (every indicator at its defaults) reproduced to machine precision on BBCA via Node running catalog.ts; per-name packing checked on GOTO (late listing) and ASPI (gaps). Research readings use split-ADJUSTED OHLC (volume / adj_factor). The chart draws UNADJUSTED exchange bars, so the levels differ across splits. The formulas are identical.
- **idx.bar.open was back-filled from Yahoo at 2026-09-25 23:31 WIB** (open_src = 'yahoo', 885k rows), after #192 ran. `idx_daytrade.load` counts every non-null open as an IDX open, so re-running the combo now gives gap-fade 407 events and 42 % alone, and the baseline reads 73.1 % / 3.11. That is a data change, not an edge. This study pins the pre-backfill view in-process (Yahoo-sourced opens -> NULL), which reproduces #192 exactly (33.8 % / 1.83 / -17.9 %; gap alone 12.8 % / 1.39). **Every gap-fade study re-run from now on is affected until idx_daytrade.load filters open_src.** Stage 0's BoP reading was computed after the backfill (no rule uses BoP).
- Mass Index at the catalog default (10) sits near 10, so the classic 25/27 bulge levels never trigger. R08/R14/R22/R25 had 0 trades. They stay counted and were not fixed.

## Stage 0 - screening, in-sample 2020-07..2023-12 only (853 days, LIQ with the point-in-time board)

Rank IC vs the forward return from the next close (t = overlap-adjusted). Q5 excess = top fifth (by IC sign) minus the LIQ mean at 20 d, against 2 x the real round trip (closing offer/bid + fees). R2 = share of the reading's cross-section explained by the ML model's 30 price/volume/tape features. pt = t of the partial IC after regressing on them.

| family | reading | IC5 t | IC10 t | IC20 t | Q5 excess 20d / hurdle (bps) | R2 vs ML | partial t 5/10/20 |
|---|---|---|---|---|---|---|---|
| F1 | atr | -5.0 | -4.3 | -4.3 | -7 / 147 | 0.98 | -1.7 / -0.3 / +0.0 |
| F1 | stdev | -4.3 | -3.8 | -4.2 | +38 / 160 | 0.78 | -1.6 / -1.3 / -1.0 |
| F1 | bbw | -4.2 | -3.8 | -4.1 | +38 / 160 | 0.78 | -1.6 / -1.4 / -1.1 |
| F1 | hv | -3.8 | -3.6 | -4.1 | -14 / 161 | 0.84 | +0.9 / +0.2 / -0.4 |
| F2 | chop | +1.6 | +1.9 | +1.9 | +19 / 174 | 0.44 | +0.5 / +0.8 / +0.7 |
| F3 | adx | -0.3 | -0.1 | -0.0 | -22 / 171 | 0.44 | -0.3 / +0.1 / +0.5 |
| F4 | volume | +2.0 | +1.9 | +1.5 | +26 / 169 | 1.00 | +1.1 / +0.8 / +0.3 |
| F4 | volosc | +2.0 | +1.8 | +1.4 | +34 / 169 | 0.90 | -0.7 / -0.2 / -0.1 |
| F5 | alma | +1.5 | +1.2 | +1.1 | +94 / 168 | 0.84 | -0.8 / -0.2 / +0.2 |
| F5 | netvol | -0.5 | -0.3 | -0.1 | -20 / 169 | 0.86 | -1.3 / -1.1 / -0.6 |
| F5 | bop | -0.0 | +0.2 | +0.3 | +45 / 165 | 0.86 | -0.3 / -0.3 / -0.2 |
| F5 | hma | -0.5 | -0.1 | -0.0 | -19 / 174 | 0.71 | -0.9 / -0.4 / -0.2 |
| F6 | ichimoku | +3.1 | +2.4 | +2.0 | +136 / 164 | 0.95 | +0.6 / +0.6 / -0.2 |
| F6 | trix | +1.3 | +0.9 | +0.5 | +92 / 168 | 0.94 | +0.8 / +0.5 / +0.2 |
| F7 | uo | +3.7 | +3.0 | +2.7 | +79 / 159 | 0.71 | +2.7 / +2.1 / +1.6 |
| F7 | eom | +2.9 | +2.6 | +3.2 | +114 / 168 | 0.75 | -0.3 / +0.0 / +0.9 |
| F7 | cmf | +2.8 | +2.3 | +2.2 | +114 / 162 | 0.63 | +2.4 / +2.1 / +1.6 |
| F7 | chaikinosc | +3.2 | +2.3 | +2.1 | +99 / 161 | 0.64 | +2.5 / +2.0 / +1.5 |
| F7 | ad | +3.0 | +2.3 | +2.2 | +103 / 161 | 0.65 | +2.5 / +1.9 / +1.6 |
| F7 | vwma | +2.7 | +2.0 | +1.9 | +98 / 162 | 0.97 | +0.1 / +0.3 / -0.1 |
| F7 | vwap | +2.4 | +2.0 | +1.9 | +94 / 164 | 0.91 | +0.3 / +0.9 / +0.8 |
| F7 | supertrend | +2.3 | +2.0 | +1.8 | +120 / 172 | 0.79 | +1.3 / +1.6 / +1.5 |
| F7 | pivots | +2.2 | +1.9 | +1.7 | +124 / 163 | 0.95 | +0.4 / +0.9 / +0.6 |
| F7 | dpo | +2.2 | +1.7 | +1.4 | +115 / 165 | 0.97 | +1.5 / +1.6 / +0.6 |
| F7 | ema | +2.2 | +1.6 | +1.5 | +122 / 164 | 0.98 | -0.7 / +0.2 / -0.1 |
| F7 | ao | +2.1 | +1.6 | +1.2 | +95 / 166 | 0.93 | +1.4 / +1.4 / +0.6 |
| F7 | dc | +2.0 | +1.6 | +1.5 | +82 / 158 | 1.00 | -0.8 / -0.2 / -0.0 |
| F7 | wpr | +1.9 | +1.5 | +1.5 | +64 / 158 | 0.94 | -0.4 / +0.7 / +0.3 |
| F7 | stoch | +1.9 | +1.5 | +1.5 | +64 / 158 | 0.94 | -0.5 / +0.6 / +0.3 |
| F7 | wma | +2.0 | +1.4 | +1.4 | +112 / 165 | 0.98 | -1.6 / +0.1 / +0.1 |
| F7 | ppo | +1.9 | +1.4 | +1.2 | +114 / 166 | 0.97 | +0.9 / +0.9 / +0.6 |
| F7 | env | +2.0 | +1.4 | +1.4 | +116 / 164 | 1.00 | -0.7 / -0.5 / -0.7 |
| F7 | sma | +2.0 | +1.4 | +1.4 | +116 / 164 | 1.00 | -0.7 / -0.5 / -0.6 |
| F7 | kc | +2.0 | +1.3 | +1.2 | +110 / 159 | 0.97 | -0.6 / -0.6 / -0.8 |
| F7 | rsi | +1.9 | +1.3 | +1.0 | +121 / 161 | 0.96 | -0.7 / -1.2 / -1.2 |
| F7 | fisher | +1.8 | +1.2 | +1.0 | +70 / 161 | 0.82 | -0.0 / -0.1 / -0.4 |
| F7 | pvt | -0.8 | -1.1 | -0.9 | -131 / 174 | 0.82 | -0.3 / -0.5 / -0.1 |
| F7 | tsi | +1.7 | +1.1 | +0.8 | +120 / 161 | 0.94 | -0.6 / -0.9 / -0.8 |
| F7 | cmo | +1.7 | +1.1 | +1.0 | +95 / 163 | 0.82 | -0.6 / -0.2 / -0.5 |
| F7 | cci | +1.8 | +1.1 | +1.1 | +138 / 162 | 0.92 | -1.2 / -0.9 / -0.0 |
| F7 | psar | +1.7 | +1.1 | +1.1 | +88 / 169 | 0.78 | -0.2 / -0.2 / +0.2 |
| F7 | roc | +1.7 | +1.1 | +1.1 | +89 / 167 | 0.85 | -0.4 / +0.1 / +0.1 |
| F7 | coppock | +1.4 | +1.0 | +1.1 | +74 / 167 | 0.92 | +1.4 / +0.7 / +0.5 |
| F7 | bb | +1.6 | +1.0 | +1.1 | +143 / 162 | 0.94 | -1.6 / -1.2 / -0.4 |
| F7 | bbpb | +1.6 | +1.0 | +1.1 | +143 / 162 | 0.94 | -1.6 / -1.2 / -0.4 |
| F7 | mom | +1.5 | +1.0 | +1.1 | +89 / 166 | 0.87 | -0.7 / -0.0 / +0.0 |
| F7 | aroon | +1.4 | +1.0 | +0.9 | +71 / 163 | 0.72 | -0.4 / -0.1 / -0.3 |
| F7 | efi | -0.5 | -0.9 | -0.8 | -131 / 174 | 0.81 | -0.8 / -0.7 / -0.1 |
| F7 | stochrsi | +1.4 | +0.9 | +0.9 | +72 / 165 | 0.78 | -1.0 / -0.0 / -0.1 |
| F7 | vortex | +1.3 | +0.8 | +0.9 | +90 / 160 | 0.88 | +0.3 / -0.2 / +0.0 |
| F7 | mfi | -0.1 | -0.4 | -0.6 | -99 / 173 | 0.71 | -0.2 / -0.8 / -1.1 |
| F7 | macd | +0.7 | +0.4 | +0.8 | +65 / 171 | 0.87 | -0.2 / +0.2 / +0.5 |
| F7 | di | +0.9 | +0.2 | +0.2 | +125 / 165 | 0.86 | -1.3 / -1.3 / -0.6 |
| F7 | obv | +0.4 | -0.0 | -0.0 | -117 / 171 | 0.73 | +0.1 / -0.2 / -0.5 |
| F8 | mass | +2.8 | +2.7 | +1.7 | +101 / 168 | 0.62 | +2.2 / +1.9 / +1.2 |

Findings:

1. **Eight families at the pre-registered cut (average |corr| >= 0.5), and one of them is almost the whole catalog.** F7 holds 40 of 55 readings: price vs every MA / band / SAR / Supertrend / pivot, every momentum oscillator, and the flow lines (CMF, A/D, Chaikin, OBV, MFI, EOM, EFI, PVT). On IDX daily bars they are one factor, recent price position. SMA/ENV and BB/%B are identical by construction. Stoch and %R are identical at the same length.
2. **Not one reading's top fifth clears the 2x round-trip hurdle** at 10 or 20 days (best: BB/%B +143 bps vs 162, CCI +138 vs 162). The strongest ICs are the volatility family's NEGATIVE ones (ATR% t -4.3..-5.0: low-vol names rank better), but their top-fifth excess is ~0 bps. The rank edge is in the losers' tail, not in anything a long-only book can buy.
3. **Nothing carries information the ML does not already see** (pre-registered bar |partial t| >= 3: 0 of 55). Largest partial t: UO 2.7, Chaikin / A-D 2.5, CMF 2.4, Mass 2.2 (h = 5). Pure redundancy (R2 >= 0.80 AND partial |t| < 1.5): the moving-average family (SMA/EMA/WMA/VWMA/ALMA, R2 0.84-1.00 = dist_ma20/50), Donchian / Stoch / %R (R2 0.94-1.00 = pos20), Bollinger / Keltner / Envelope / %B, pivots, Ichimoku, TRIX, RSI / CCI / TSI / PPO / MACD / DPO, volume ratio and volume oscillator (R2 0.90-1.00 = volr1/volr5), ATR% / HV (R2 0.84-0.98 = atr_pct/vol20). The least redundant readings (CHOP 0.44, ADX 0.44, Mass 0.62, CMF 0.63) have no partial IC at the bar (|t| <= 2.4).

### Family correlation matrix (mean |within-day rank corr| between members; diagonal = mean within the family)

| | F1 | F2 | F3 | F4 | F5 | F6 | F7 | F8 |
|---|---|---|---|---|---|---|---|---|
| F1 volatility | 0.77 | 0.41 | 0.36 | 0.07 | 0.04 | 0.08 | 0.09 | 0.18 |
| F2 choppiness | 0.41 | 1.00 | 0.33 | 0.07 | 0.01 | 0.01 | 0.02 | 0.22 |
| F3 ADX | 0.36 | 0.33 | 1.00 | 0.01 | 0.01 | 0.23 | 0.11 | 0.23 |
| F4 volume activity | 0.07 | 0.07 | 0.01 | 0.86 | 0.15 | 0.05 | 0.15 | 0.17 |
| F5 fast MA / bar shape | 0.04 | 0.01 | 0.01 | 0.15 | 0.66 | 0.09 | 0.24 | 0.04 |
| F6 Ichimoku / TRIX | 0.08 | 0.01 | 0.23 | 0.05 | 0.09 | 0.88 | 0.46 | 0.22 |
| F7 price position + momentum + flow | 0.09 | 0.02 | 0.11 | 0.15 | 0.24 | 0.46 | 0.68 | 0.32 |
| F8 Mass Index | 0.18 | 0.22 | 0.23 | 0.17 | 0.04 | 0.22 | 0.32 | 1.00 |

Representatives' signed correlation (the stage-1 legs):

| | atr | chop | adx | volume | alma | ichimoku | uo | mass |
|---|---|---|---|---|---|---|---|---|
| atr | +1.00 | -0.22 | +0.23 | -0.10 | -0.13 | -0.11 | -0.21 | +0.01 |
| chop | -0.22 | +1.00 | -0.33 | -0.05 | -0.00 | +0.01 | +0.03 | -0.22 |
| adx | +0.23 | -0.33 | +1.00 | -0.02 | +0.01 | +0.22 | +0.04 | +0.23 |
| volume | -0.10 | -0.05 | -0.02 | +1.00 | +0.24 | +0.04 | +0.16 | +0.16 |
| alma | -0.13 | -0.00 | +0.01 | +0.24 | +1.00 | +0.26 | +0.40 | +0.05 |
| ichimoku | -0.11 | +0.01 | +0.22 | +0.04 | +0.26 | +1.00 | +0.46 | +0.26 |
| uo | -0.21 | +0.03 | +0.04 | +0.16 | +0.40 | +0.46 | +1.00 | +0.24 |
| mass | +0.01 | -0.22 | +0.23 | +0.16 | +0.05 | +0.26 | +0.24 | +1.00 |

Members: F1 volatility: atr, stdev, hv, bbw; F2 choppiness: chop; F3 ADX: adx; F4 volume activity: volume, volosc; F5 fast MA / bar shape: hma, alma, netvol, bop; F6 Ichimoku / TRIX: ichimoku, trix; F7 price position + momentum + flow: sma, ema, wma, vwma, vwap, bb, kc, dc, env, psar, supertrend, pivots, di, aroon, vortex, obv, mfi, cmf, ad, chaikinosc, pvt, efi, eom, rsi, macd, stoch, stochrsi, cci, wpr, roc, mom, ao, uo, tsi, ppo, cmo, coppock, dpo, fisher, bbpb; F8 Mass Index: mass.

## Stage 1 - 26 counted rules, in-sample 2020-07..2023-12 (ML filters 2022-23)

K-10 book on LIQ (pit), entry at the next close paying the closing offer + 0.10 %, exit at a close receiving the bid + 0.20 %. References (not trials): random LIQ entries + trail10 Sharpe 0.03, + hold10 -0.74; trend host 27.9 % / 1.27 / -15.3 % (254 trades); ML ens4 host 2022-23 20.8 % / 1.76 / -12.6 %.

| id | type | rule | exit | trades | CAGR / Sharpe / mDD | vs host |
|---|---|---|---|---|---|---|
| R01 | i | atr_lo | hold 10 | 850 | -14.1 % / -1.12 / -48.8 % |  |
| R02 | i | chop_hi | hold 10 | 836 | -13.6 % / -0.70 / -58.7 % |  |
| R03 | i | adx_lo | hold 10 | 849 | -20.5 % / -1.08 / -69.8 % |  |
| R04 | i | volume_hi | hold 10 | 848 | -28.6 % / -1.08 / -82.9 % |  |
| R05 **finalist** | i | alma_hi | trail 10 % | 459 | 40.1 % / 1.40 / -50.5 % |  |
| R06 | i | ichimoku_hi | trail 10 % | 457 | 41.3 % / 1.32 / -44.2 % |  |
| R07 | i | uo_hi | trail 10 % | 211 | 7.4 % / 0.51 / -30.5 % |  |
| R08 | i | mass_hi | hold 10 | 0 | 0.0 % / 0.00 / 0.0 % |  |
| R09 | ii | adx_hi & uo_lo | trail 10 % | 295 | -14.0 % / -0.57 / -66.0 % |  |
| R10 **finalist** | ii | ichimoku_hi & volume_hi | trail 10 % | 351 | 42.5 % / 1.52 / -38.5 % |  |
| R11 | ii | atr_lo & volume_hi | hold 10 | 756 | -9.1 % / -0.63 / -43.0 % |  |
| R12 | ii | atr_lo & uo_hi | trail 10 % | 92 | -0.0 % / 0.05 / -19.0 % |  |
| R13 | ii | uo_hi & volume_hi | trail 10 % | 184 | 20.5 % / 1.20 / -24.0 % |  |
| R14 | ii | mass_hi & uo_hi | trail 10 % | 0 | 0.0 % / 0.00 / 0.0 % |  |
| R15 | ii | chop_lo & uo_hi | trail 10 % | 216 | 14.4 % / 0.81 / -37.6 % |  |
| R16 | ii | adx_hi & ichimoku_hi | trail 10 % | 313 | -1.3 % / 0.05 / -38.4 % |  |
| R17 | iii | rsi_hi & stoch_hi & uo_hi | trail 10 % | 210 | 18.5 % / 1.00 / -32.3 % |  |
| R18 | iii | rsi_lo & stoch_lo & uo_lo | hold 10 | 559 | -36.5 % / -1.94 / -79.4 % |  |
| R19 | iii | cmf_hi & chaikinosc_hi & ad_hi | trail 10 % | 239 | 2.7 % / 0.24 / -42.8 % |  |
| R20 | iv | composite of 8 reps | hold 20 | 420 | 2.0 % / 0.20 / -34.6 % |  |
| R21 **finalist** | v | cmf_hi on trend | host | 240 | 38.5 % / 1.70 / -15.8 % | dSharpe +0.43, keeps 94 % |
| R22 | v | mass_hi on trend | host | 0 | 0.0 % / 0.00 / 0.0 % | dSharpe -1.27, keeps 0 % |
| R23 | v | atr_lo on trend | host | 40 | 4.9 % / 0.73 / -7.1 % | dSharpe -0.54, keeps 16 % |
| R24 | v | cmf_hi on ML | host | 250 | 24.5 % / 2.03 / -14.6 % | dSharpe +0.27, keeps 92 % |
| R25 | v | mass_hi on ML | host | 0 | 0.0 % / 0.00 / 0.0 % | dSharpe -1.76, keeps 0 % |
| R26 | v | atr_lo on ML | host | 26 | -2.9 % / -1.93 / -5.7 % | dSharpe -3.69, keeps 10 % |

Reading: only the price-position rules made money in-sample, R05/R06/R10 at 40-43 % CAGR. Every one of them earned it in 2021 (+116..+149 %) with -38..-51 % drawdowns. All mean-reversion / weakness-side rules lost heavily (R18 3x oversold: -36.5 %/yr). The composite (R20) is flat.

## Stage 2 - the counted test (run once per frozen finalist)

| | R10 ichimoku_hi & volume_hi | R05 alma_hi | R21 trend & CMF > 0 |
|---|---|---|---|
| in-sample 2020-07..2023 | 42.5 % / 1.52 / -38.5 % | 40.1 % / 1.40 / -50.5 % | 38.5 % / 1.70 / -15.8 % (host 27.9 % / 1.27 / -15.3 %) |
| **OOS 2024-01..2026-09-16** | 14.4 % / 0.61 / -53.8 %, 297 tr | -1.7 % / 0.12 / -62.0 %, 385 tr | 29.1 % / 1.34 / -17.5 % vs host 36.7 % / 1.63 / -17.5 %; dSharpe -0.29 |
| OOS years | 24 +6 25 +116 26 -38 | 24 -24 25 +170 26 -53 | filt - host: 24 +9 25 -46 26 -1 |
| P placebo (200) | pct 96 (p50 -0.15, p95 0.49) PASS | pct 70 (p95 0.60) fail | pct 39 of random filters keeping 81 % (p95 d +0.25) fail |
| N neighbours | len x0.75 0.23, len x1.25 0.57 ok, level x0.75 0.71 ok, level x1.25 0.63 ok -> PASS | len x0.75 -0.12, len x1.25 0.25, exit trail 0.075 0.37, exit trail 0.125 0.30 -> fail | len x0.75 d-0.55, len x1.25 d-0.01, thr -0.0546 d-0.43, thr +0.0546 d+0.02 ok -> fail |
| T 2005-19 Yahoo survivors | 11.9 % / 0.69 / -42.4 %, 800 tr; random 0.42; 10/15 yrs -> fail (bar 0.72) | 10.9 % / 0.56 / -58.6 %; random 0.44; 8/15 -> fail | host 13.3 % / 0.89 / -27.2 % (613) vs filt 14.2 % / 0.95 / -25.9 % (588) -> PASS |
| C costs x1.5 | 8.8 % / 0.44 / -55.2 % ok | -8.5 % / -0.10 / -63.7 % fail | host 1.50 -> filt 1.21 fail |
| D 1 day late | -2.2 % / 0.07 / -54.4 % **fail** | -11.1 % / -0.19 / -59.7 % fail | host 0.65 -> filt 0.30 fail |
| M DSR @ N 942 / @ 26 | 0.01 / 0.15 | 0.00 / 0.03 | 0.14 / 0.57 |
| **verdict** | **PARTIAL** | **FRAGILE** | **CLOSED** |

## Effect on the combo book (corrected #192 engine, same run, gap 10 / trend 5 / ML ens4 5 %, 20 slots, floor 30 %, Rp 20 M, 2022-01..2026-09-16)

Mode fixed before the run: R10 / R05 = a 4th sleeve at 5 % of NAV per trade; R21 = replaces the trend sleeve's trade list. 2024+ = the same NAV path from 2024-01-02.

| book | full CAGR / Sharpe / mDD | 2024+ | sleeve alone on the engine | corr with gap / trend / ML (2024+) | per year |
|---|---|---|---|---|---|
| baseline (reproduces #192) | 33.8 % / 1.83 / -17.9 % | 54.6 % / 2.30 / -17.9 % | - | - | 22 +5 23 +15 24 +15 25 +113 26 +26 |
| + R10 (4th sleeve (5 %)) | 19.6 % / 1.12 / -21.8 % | 31.3 % / 1.50 / -21.8 % | 5.1 % / 0.44 / -32.0 % | +0.07 / +0.55 / +0.35 | 22 +4 23 +5 24 +15 25 +95 26 -12 |
| + R05 (4th sleeve (5 %)) | 7.9 % / 0.50 / -34.2 % | 12.2 % / 0.66 / -34.2 % | -1.5 % / -0.02 / -34.9 % | +0.11 / +0.45 / +0.36 | 22 -24 23 +36 24 -14 25 +104 26 -25 |
| + R21 (replaces the trend trade list) | 37.5 % / 2.03 / -15.5 % | 56.9 % / 2.40 / -15.5 % | 14.3 % / 1.35 / -9.4 % | +0.05 / +0.84 / +0.19 | 22 +19 23 +11 24 +22 25 +105 26 +27 |

The two standalone rules are the trend sleeve's own exposure again (corr +0.45..+0.55 with trend, +0.35 with ML). They compete for the same 20 slots and the 30 % floor and cost the book 14-26 pp CAGR. R21 is the trend sleeve with a flow check (corr +0.84 with the deployed trend). Its combo gain comes mainly from 2022 (+19 % vs +5 %), which is in-sample.

## What this closes

- The desk's ~50 chart indicators at default settings, alone, AND-combined across uncorrelated families, as oscillator agreement, as an equal-weight composite, and as filters on the trend and ML entries: 26 rules, 0 ROBUST. Cumulative N 942.
- On daily IDX bars the catalog is one price-position/momentum factor plus low-vol. The ML already sees both (dist_ma*, pos20, ret*, volr*, atr_pct, vol20), and neither pays a 2x round trip from the long side. More indicators or combinations of them are accuracy work, and #174/#176 already showed that route loses on this desk.
- Left open, not tested: flow readings (CMF / A-D / Chaikin) as an ML FEATURE. They have the highest partial IC (t 2.4-2.5), but it is below the bar, so this is low priority.
