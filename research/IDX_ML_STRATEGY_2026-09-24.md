# IDX menu ML-4 — strategies on the prediction desk's models — 2026-09-24 — 12 trials, cumulative N = 723

Walk-forward scores by test year (fit on purged earlier rows), LIQ universe (60-day value >= Rp 5 bn, close >= Rp 100), closing offer/bid + Stockbit fees, rolling cohorts of K names held H days (slot 1/(K*H)). Book 2022-01 -> 2026-09-24.

| arm | H | K | trades | CAGR | Sharpe | mDD | years + | by year | placebo pct | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| ml5 | 5 | 10 | 11,240 | -20.5 % | -0.49 | -77 % | 1/5 | 22:-46 23:-27 24:-3 25:+33 26:-33 | - | not a candidate: sharpe -0.49 < 1.2; mdd -77 % < -25 %; 1/5 years positive |
| ml5_gate | 5 | 10 | 6,660 | -16.4 % | -0.69 | -62 % | 1/5 | 22:-46 23:-17 24:-1 25:+21 26:-20 | - | not a candidate: sharpe -0.69 < 1.2; mdd -62 % < -25 %; 1/5 years positive |
| ml5_dir | 5 | 10 | 11,240 | -21.8 % | -0.89 | -77 % | 1/5 | 22:-36 23:-32 24:-27 25:+42 26:-31 | - | not a candidate: sharpe -0.89 < 1.2; mdd -77 % < -25 %; 1/5 years positive |
| ml5_k5 | 5 | 5 | 5,620 | -20.8 % | -0.38 | -79 % | 1/5 | 22:-48 23:-24 24:-4 25:+31 26:-33 | - | not a candidate: sharpe -0.38 < 1.2; mdd -79 % < -25 %; 1/5 years positive |
| ml20 | 20 | 10 | 11,090 | -5.0 % | 0.01 | -59 % | 2/5 | 22:-33 23:-12 24:+24 25:+63 26:-34 | - | not a candidate: sharpe 0.01 < 1.2; mdd -59 % < -25 %; 2/5 years positive |
| ml20_gate | 20 | 10 | 6,660 | -6.1 % | -0.21 | -43 % | 2/5 | 22:-35 23:-8 24:+22 25:+38 26:-26 | - | not a candidate: sharpe -0.21 < 1.2; mdd -43 % < -25 %; 2/5 years positive |
| ml250 | 250 | 10 | 8,790 | -2.7 % | -0.09 | -39 % | 2/5 | 22:-17 23:-14 24:+8 25:+22 26:-7 | - | not a candidate: sharpe -0.09 < 1.2; mdd -39 % < -25 %; 2/5 years positive; vs random -0.13 + 0.5 |
| ml250_fund | 250 | 10 | 8,790 | -0.0 % | 0.08 | -34 % | 2/5 | 22:-12 23:-17 24:+14 25:+24 26:-3 | - | not a candidate: sharpe 0.08 < 1.2; mdd -34 % < -25 %; 2/5 years positive; vs random -0.13 + 0.5 |
| combo20 | 20 | 10 | 11,090 | +0.8 % | 0.16 | -54 % | 1/5 | 22:-23 23:-11 24:-6 25:+117 26:-26 | - | not a candidate: sharpe 0.16 < 1.2; mdd -54 % < -25 %; 1/5 years positive |
| combo20_gate | 20 | 10 | 6,660 | +1.6 % | 0.18 | -39 % | 1/5 | 22:-18 23:-8 24:-4 25:+82 26:-19 | 100 | not a candidate: sharpe 0.18 < 1.2; mdd -39 % < -25 %; 1/5 years positive |
| trend_ml | 20 | 10 | 4,401 | +2.1 % | 0.24 | -34 % | 1/5 | 22:-11 23:-1 24:-1 25:+61 26:-22 | 95 | not a candidate: sharpe 0.24 < 1.2; mdd -34 % < -25 %; 1/5 years positive |
| brok20 | 20 | 10 | 2,200 | -25.9 % | -0.30 | -59 % | 1/2 | 25:+13 26:-34 | - | informative only (one year of broker flow); sharpe -0.30 < 1.2; mdd -59 % < -25 %; 1/2 years positive; vs random -0.80 + 0.5 |

| reference | CAGR | Sharpe | mDD |
|---|---|---|---|
| random_H5 | -41.0 % | -2.36 | -93 % |
| random_H20 | -16.6 % | -0.80 | -68 % |
| random_H250 | -2.5 % | -0.13 | -41 % |
| mom60_H20 | -29.8 % | -0.82 | -87 % |
| composite | -1.2 % | 0.01 | -42 % |

Deployed comparables (ROI scorecard #roi_scorecard): value strict annual 21.8 % / 1.06 / -23 %; trend small + gate 32.1 % / 1.54 / -18 %; value 50 / trend 50 gated 27.7 % / 1.54 / -15 %.

## Verdict (menu ML-4, study stored)

Best arm by Sharpe: **trend_ml** (+2.1 %/yr, Sharpe 0.24, mDD -34 %) - not a candidate: sharpe 0.24 < 1.2; mdd -34 % < -25 %; 1/5 years positive.
Candidates: none.

## Diagnostics (after the run; no new trials)

Per-day cross-sectional rank IC of the OOS scores on LIQ (mean over days; t on the daily series), and the top-minus-bottom decile mean:

| score | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|
| s5 (5d) | IC +0.085 t 14, +272 bps | +0.100 t 16, +407 | +0.074 t 10, +332 | +0.055 t 7, +188 | +0.050 t 3.5, +313 |
| s20 (20d excess) | +0.064 t 12, +527 bps | +0.098 t 19, +1090 | +0.076 t 13, +970 | +0.078 t 12, +568 | +0.035 t 4, +254 |
| s250 (250d excess) | +0.090 t 29, +2292 bps | +0.220 t 68, +6190 | +0.061 t 14, +2837 | +0.113 t 24, +2600 | - |
| p5 (P 5d up) | +0.098 t 16, +259 bps | +0.104 t 18, +280 | +0.073 t 10, +180 | +0.083 t 12, +309 | +0.094 t 10, +351 |

Gross (no cost) vs net top-10 books, LIQ, 2022-01 -> 2026-09 (round trip on LIQ = 91 bps: closing offer/bid + fees):

| score / H | gross CAGR | gross Sharpe | net CAGR | net Sharpe | random net |
|---|---|---|---|---|---|
| s5 / 5 | +26.4 % | 0.86 | -20.5 % | -0.49 | -40.6 % |
| s20 / 20 | +5.9 % | 0.35 | -5.0 % | 0.01 | -18.2 % |
| s250 / 250 | -1.9 % | -0.05 | -2.7 % | -0.09 | -2.0 % |

Reading: the ranking is real every year (the 5-day score lifts a random book by ~20 pp/yr gross) but even before costs no
arm reaches the Sharpe bar, and at 5-20 days the IDX round trip (~50 turns/yr x 91 bps) is larger than the edge. At 250 days
the decile spread is the BOTTOM decile falling (small-cap base rate), not the top rising: the long score is a loser filter,
not a picker (menu ML-4b, study #152: excluding the bottom 30 % adds +1.1 %/yr to an equal-weight LIQ book, 4/5 years).
