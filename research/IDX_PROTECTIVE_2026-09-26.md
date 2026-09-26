# IDX menu 48 - protective construction rules (young-IPO filter, MSCI-deletion exit) - 2026-09-26 - 8 trials (1000..1007), cumulative N = 1007

Script `research/idx_protective.py` (pre-registration in its docstring, written before any arm was run). Deployed combo, 2022-01-01 -> 2026-09-16, Rp 20 M, gap 10 % / trend 5 % / ML ens4 5 %, 20 slots, cash floor 30 %; cells CAGR / Sharpe / mDD; same run throughout.

## Baseline reproduced

- #192 variant d (all ML): **32.9 % / 1.77 / -16.9 %** (target 33.8 % / 1.83 / -17.9 %); ML 718 rule-trades = 444 (name, fill-day) positions.
- Reference = d + ML main_board_only (the live runner): **33.9 % / 1.81 / -15.9 %** (target 34.6 % / 1.87 / -17.0 %); ML kept 685 of 718 rule-trades (426 of 444 positions). Halves (calendar midpoint): 10.3 % / 0.88 / -13.3 % | 62.5 % / 2.45 / -15.9 %.
- Adjusted prices: in-window daily returns of the caches equal a fresh idx.bar close x adj_factor read after today's repair to 3e-9 (the 641 removed actions sit on 2026-09-21, after the window).
- idx.listing.listing_date missing for 20 panel codes (never young).

## A - young-IPO entry filter

| arm | full | H1 | H2 | list entries removed (ML/trend/gap) | taken by ref book | their mean net (t) | stand-alone mean net (t) | placebo pct (p95) | DSR | halves | trades | neighbours | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| reference | 33.9 % / 1.81 / -15.9 % | 10.3 % / 0.88 / -13.3 % | 62.5 % / 2.45 / -15.9 % | - | - | - | - | - | - | - | - | - | - |
| A125_mt | 28.9 % / 1.64 / -16.2 % | 6.6 % / 0.62 / -12.3 % | 56.0 % / 2.32 / -16.2 % | 76/0/0 | 33 | +13.80 % (2.33) | +12.21 % (3.06) | 0 (1.85) | 0.64 | no | no | no | **no** |
| A250_mt | 28.0 % / 1.60 / -16.2 % | 6.9 % / 0.65 / -11.3 % | 53.3 % / 2.23 / -16.2 % | 100/4/0 | 43 | +9.36 % (1.92) | +11.00 % (2.82) | 1 (1.88) | 0.60 | no | no | no | **no** |
| A500_mt | 29.8 % / 1.69 / -16.3 % | 9.8 % / 0.91 / -10.7 % | 53.6 % / 2.23 / -16.3 % | 186/22/0 | 104 | +6.78 % (2.21) | +8.68 % (3.52) | 10 (1.93) | 0.68 | no | no | no | **no** |
| A125_gap | 30.8 % / 1.70 / -16.2 % | 10.3 % / 0.88 / -13.3 % | 55.3 % / 2.28 / -16.2 % | 0/0/5 | 5 | +5.40 % (1.03) | +5.40 % (1.03) | 4 (1.83) | 0.68 | no | no | no | **no** |
| A250_gap | 30.3 % / 1.71 / -17.2 % | 8.6 % / 0.77 / -13.3 % | 56.4 % / 2.35 / -17.2 % | 0/0/13 | 13 | +7.28 % (1.59) | +7.28 % (1.59) | 14 (1.83) | 0.66 | no | no | no | **no** |
| A500_gap | 27.1 % / 1.58 / -16.4 % | 8.8 % / 0.78 / -13.4 % | 48.7 % / 2.14 / -16.4 % | 0/0/34 | 32 | +6.07 % (2.28) | +5.83 % (2.32) | 4 (1.83) | 0.56 | no | no | no | **no** |

Taken-by-sleeve (positions the reference book held, mean net, t): A125_mt: ML 33 +13.8 % (2.3); A250_mt: ML 39 +9.2 % (1.7), trend 4 +11.0 % (1.5); A500_mt: ML 82 +9.1 % (2.5), trend 22 -1.9 % (-0.4); A125_gap: gap 5 +5.4 % (1.0); A250_gap: gap 13 +7.3 % (1.6); A500_gap: gap 32 +6.1 % (2.3).

Informative (not counted): A250_mt at the candidate level (young names removed from the ML book's eligible set and the trend book's entry matrix, so freed slots refill): 27.1 % / 1.58 / -14.7 %; H1 4.7 % / 0.47 / -12.7 %, H2 54.1 % / 2.30 / -14.7 %; ML 646 rule-trades, trend 281.

## B - MSCI Standard deletion exit

24 Standard deletions with J inside the window (May22 INTP, Nov22 ADMR, Nov22 GGRM, Nov22 TBIG, Feb23 ARTO, Nov23 INCO, May24 TOWR, May24 SMGR, Aug24 ANTM, Feb25 INKP, Feb25 MDKA, Feb25 UNVR, Aug25 ADRO, Nov25 ICBP, Nov25 KLBF, Feb26 INDF, May26 AMMN, May26 BREN, May26 TPIA, May26 DSSA, May26 CUAN, May26 AMRT, Aug26 CPIN, Aug26 GOTO). Held by the reference book at the J-1 close and still held after the J close: **4 positions** (2 name-events; rule pieces listed): May26 BREN ML (in 2026-05-06), May26 BREN ML (in 2026-05-07), May26 CUAN ML (in 2026-04-02), May26 CUAN ML (in 2026-04-08), May26 CUAN ML (in 2026-04-08), May26 CUAN ML (in 2026-04-08). Entries the block would stop: 0 ML/trend list entries, 15 gap events.

What those held positions did from the J close to their planned exit: May26 BREN ML +9.7 %, May26 BREN ML +5.6 %, May26 CUAN ML -29.6 %, May26 CUAN ML -24.3 %, May26 CUAN ML -24.3 %, May26 CUAN ML -24.3 %.

Fewer than 5 held positions: B is UNTESTABLE on the combo; trials 1006/1007 are spent on the fallback below. The engine runs of B_J / B_J1 are printed for information only (one review, both events in the May-2026 freeze deletions).

| arm | full | H1 | H2 | forced sells (rule pieces) | verdict |
|---|---|---|---|---|---|
| B_J | 35.1 % / 1.89 / -15.9 % | 10.3 % / 0.88 / -13.3 % | 65.7 % / 2.60 / -15.9 % | 6 | **UNTESTABLE (4 held positions < 5)** |
| B_J1 | 35.0 % / 1.89 / -15.9 % | 10.3 % / 0.88 / -13.3 % | 65.3 % / 2.59 / -15.9 % | 6 | **UNTESTABLE (4 held positions < 5)** |

Fallback (B untestable on the combo):

- Value book (strict composite, May): 1 deletion(s) held at J: Aug25 ADRO (book of 12, J -> next rebalance +39.7 %, NAV effect of selling -3.34 %); summed NAV effect -3.34 % over the window.
- 'Held names' proxy (deletions whose name was a candidate of any sleeve in the 60 sessions before J): 5 events; J -> R mean -17.1 % (-1.69), J -> J+60 mean +10.0 % (1.43): Feb25 MDKA -7.0/+34.9, Aug25 ADRO -3.1/+6.4, May26 BREN +3.1/+14.4, May26 DSSA -52.5/-4.3, May26 CUAN -25.9/-1.2.
