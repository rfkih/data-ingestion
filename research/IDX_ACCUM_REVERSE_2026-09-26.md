# IDX - akumulasi sebelum kenaikan tinggi: dua arah kondisional - 2026-09-26 - descriptive, 0 new trials (cumulative N = 711)

Panel 2020-01-02 -> 2026-09-25, a snapshot every 10 trading days (150 snapshots), features over the 60 days ending the snapshot, outcome = the close 60 trading days later. 'Big rise' = +50 % held at day 60; 'touch' = the highest close in the 60 days >= +50 %; 'crash' = -30 % at day 60. Deciles are within-snapshot ranks.

## LIQ - 20,392 name-snapshots (136 names per snapshot)

Base rates: **P(+50 % held) = 5.40 %**, P(touch +50 %) = 9.61 %, P(+30 % held) = 10.49 %, P(-30 %) = 8.95 %; mean 60-day return +1.2 %, median -3.6 %.

### Arah strategi: P(kenaikan | sinyal) - dan cerminnya, P(crash | sinyal)

| signal | snapshots | P(+50 % held) | lift | P(touch +50 %) | lift | P(+30 %) | lift | P(-30 % crash) | lift | mean 60 d | median 60 d |
|---|---|---|---|---|---|---|---|---|---|---|---|
| WYCKOFF | 129 | 8.53 % | 1.58 | 11.63 % | 1.21 | 13.95 % | 1.33 | 10.08 % | 1.13 | +0.2 % | -3.2 % |
| flat only (control) | 10,568 | 3.46 % | 0.64 | 6.32 % | 0.66 | 7.66 % | 0.73 | 4.86 % | 0.54 | +0.8 % | -2.9 % |
| obv60 top decile | 2,123 | 9.84 % | 1.82 | 18.23 % | 1.90 | 16.06 % | 1.53 | 18.51 % | 2.07 | +2.5 % | -6.6 % |
| obv60 top decile & flat | 367 | 3.54 % | 0.66 | 10.35 % | 1.08 | 10.63 % | 1.01 | 12.53 % | 1.40 | -2.0 % | -4.1 % |
| upvol top decile | 2,123 | 9.94 % | 1.84 | 18.18 % | 1.89 | 15.87 % | 1.51 | 19.41 % | 2.17 | +2.0 % | -7.4 % |
| upvol top decile & flat | 367 | 3.00 % | 0.55 | 8.99 % | 0.94 | 7.90 % | 0.75 | 15.26 % | 1.70 | -5.1 % | -5.3 % |
| voltrend top decile | 2,123 | 6.74 % | 1.25 | 12.48 % | 1.30 | 12.76 % | 1.22 | 12.67 % | 1.42 | +0.5 % | -4.6 % |
| voltrend top decile & flat | 764 | 4.06 % | 0.75 | 7.85 % | 0.82 | 8.12 % | 0.77 | 9.29 % | 1.04 | -1.8 % | -4.1 % |
| squeeze_low top decile | 2,124 | 7.02 % | 1.30 | 12.05 % | 1.25 | 12.57 % | 1.20 | 12.85 % | 1.44 | +2.2 % | -4.2 % |
| squeeze_low top decile & flat | 628 | 3.98 % | 0.74 | 7.48 % | 0.78 | 7.48 % | 0.71 | 7.17 % | 0.80 | +1.8 % | -3.3 % |
| quiet top decile | 2,075 | 4.82 % | 0.89 | 8.24 % | 0.86 | 9.45 % | 0.90 | 8.10 % | 0.90 | +0.6 % | -3.6 % |
| quiet top decile & flat | 1,088 | 3.58 % | 0.66 | 5.70 % | 0.59 | 6.89 % | 0.66 | 4.69 % | 0.52 | +0.4 % | -2.6 % |
| fgn60 top decile | 2,123 | 4.57 % | 0.85 | 7.40 % | 0.77 | 8.86 % | 0.84 | 4.90 % | 0.55 | +2.7 % | -1.9 % |
| fgn60 top decile & flat | 1,172 | 2.56 % | 0.47 | 4.52 % | 0.47 | 5.97 % | 0.57 | 3.16 % | 0.35 | +0.3 % | -2.3 % |
| acc_score top decile | 2,121 | 8.35 % | 1.54 | 13.91 % | 1.45 | 14.19 % | 1.35 | 13.53 % | 1.51 | +3.1 % | -4.7 % |
| acc_score top decile & flat | 476 | 2.94 % | 0.54 | 6.51 % | 0.68 | 7.14 % | 0.68 | 9.87 % | 1.10 | -2.4 % | -3.6 % |
| obv60 bottom decile | 1,973 | 3.09 % | 0.57 | 5.93 % | 0.62 | 7.75 % | 0.74 | 6.39 % | 0.71 | -0.6 % | -3.0 % |
| upvol bottom decile | 1,973 | 3.40 % | 0.63 | 6.03 % | 0.63 | 7.50 % | 0.72 | 4.92 % | 0.55 | +1.3 % | -2.2 % |
| voltrend bottom decile | 1,973 | 7.05 % | 1.30 | 12.27 % | 1.28 | 11.35 % | 1.08 | 11.35 % | 1.27 | +1.2 % | -5.5 % |
| squeeze_low bottom decile | 1,977 | 5.36 % | 0.99 | 9.76 % | 1.02 | 10.57 % | 1.01 | 8.24 % | 0.92 | +2.2 % | -3.0 % |
| quiet bottom decile | 17 | 11.76 % | 2.18 | 11.76 % | 1.22 | 17.65 % | 1.68 | 5.88 % | 0.66 | +5.9 % | +2.6 % |
| fgn60 bottom decile | 1,973 | 2.99 % | 0.55 | 5.83 % | 0.61 | 8.01 % | 0.76 | 2.94 % | 0.33 | +2.3 % | -2.7 % |
| acc_score bottom decile | 1,977 | 2.58 % | 0.48 | 4.55 % | 0.47 | 6.37 % | 0.61 | 6.02 % | 0.67 | -0.1 % | -3.0 % |

WYCKOFF permutation p (target shuffled within snapshot day, 2000 draws): 0.07546226886556721

### Arah hindsight: dari semua kenaikan +50 %, berapa yang sebelumnya membawa sinyal ini? (vs seberapa sering sinyalnya muncul)

| signal | signal frequency | share of +50 % risers carrying it | share of touch-+50 % | share of -30 % crashers | hindsight lift (risers / frequency) |
|---|---|---|---|---|---|
| WYCKOFF | 0.6 % | 1.0 % | 0.8 % | 0.7 % | 1.58 |
| obv60 top decile | 10.4 % | 19.0 % | 19.7 % | 21.5 % | 1.82 |
| upvol top decile | 10.4 % | 19.1 % | 19.7 % | 22.6 % | 1.84 |
| voltrend top decile | 10.4 % | 13.0 % | 13.5 % | 14.7 % | 1.25 |
| squeeze_low top decile | 10.4 % | 13.5 % | 13.1 % | 15.0 % | 1.30 |
| quiet top decile | 10.2 % | 9.1 % | 8.7 % | 9.2 % | 0.89 |
| fgn60 top decile | 10.4 % | 8.8 % | 8.0 % | 5.7 % | 0.85 |
| acc_score top decile | 10.4 % | 16.1 % | 15.1 % | 15.7 % | 1.54 |

## THIN - 40,205 name-snapshots (268 names per snapshot)

Base rates: **P(+50 % held) = 5.98 %**, P(touch +50 %) = 10.91 %, P(+30 % held) = 10.96 %, P(-30 %) = 8.91 %; mean 60-day return +2.2 %, median -3.1 %.

### Arah strategi: P(kenaikan | sinyal) - dan cerminnya, P(crash | sinyal)

| signal | snapshots | P(+50 % held) | lift | P(touch +50 %) | lift | P(+30 %) | lift | P(-30 % crash) | lift | mean 60 d | median 60 d |
|---|---|---|---|---|---|---|---|---|---|---|---|
| WYCKOFF | 243 | 6.58 % | 1.10 | 9.47 % | 0.87 | 11.11 % | 1.01 | 9.47 % | 1.06 | +0.4 % | -3.2 % |
| flat only (control) | 20,992 | 3.98 % | 0.67 | 7.15 % | 0.66 | 8.05 % | 0.73 | 4.83 % | 0.54 | +1.5 % | -2.5 % |
| obv60 top decile | 4,101 | 11.61 % | 1.94 | 20.78 % | 1.90 | 17.75 % | 1.62 | 17.22 % | 1.93 | +5.6 % | -5.6 % |
| obv60 top decile & flat | 837 | 6.93 % | 1.16 | 12.66 % | 1.16 | 12.07 % | 1.10 | 11.71 % | 1.31 | -0.8 % | -4.8 % |
| upvol top decile | 4,101 | 11.83 % | 1.98 | 21.43 % | 1.97 | 17.80 % | 1.62 | 18.17 % | 2.04 | +5.2 % | -6.5 % |
| upvol top decile & flat | 791 | 7.84 % | 1.31 | 14.66 % | 1.34 | 12.77 % | 1.16 | 13.02 % | 1.46 | -0.8 % | -6.2 % |
| voltrend top decile | 4,101 | 7.88 % | 1.32 | 15.48 % | 1.42 | 13.68 % | 1.25 | 14.05 % | 1.58 | +2.3 % | -5.7 % |
| voltrend top decile & flat | 1,506 | 5.05 % | 0.84 | 9.56 % | 0.88 | 9.36 % | 0.85 | 8.70 % | 0.98 | -0.4 % | -4.2 % |
| squeeze_low top decile | 4,105 | 6.29 % | 1.05 | 11.91 % | 1.09 | 11.25 % | 1.03 | 11.74 % | 1.32 | +1.1 % | -3.4 % |
| squeeze_low top decile & flat | 1,400 | 3.86 % | 0.65 | 7.71 % | 0.71 | 7.14 % | 0.65 | 6.00 % | 0.67 | +0.9 % | -2.5 % |
| quiet top decile | 3,963 | 6.21 % | 1.04 | 9.99 % | 0.92 | 10.24 % | 0.93 | 6.38 % | 0.72 | +3.8 % | -1.3 % |
| quiet top decile & flat | 2,481 | 4.27 % | 0.71 | 6.21 % | 0.57 | 7.17 % | 0.65 | 3.71 % | 0.42 | +2.4 % | -1.0 % |
| fgn60 top decile | 4,101 | 4.85 % | 0.81 | 8.05 % | 0.74 | 9.39 % | 0.86 | 5.46 % | 0.61 | +3.0 % | -1.7 % |
| fgn60 top decile & flat | 2,255 | 2.75 % | 0.46 | 4.57 % | 0.42 | 5.85 % | 0.53 | 3.41 % | 0.38 | +0.6 % | -1.8 % |
| acc_score top decile | 4,097 | 9.49 % | 1.59 | 17.11 % | 1.57 | 15.65 % | 1.43 | 13.45 % | 1.51 | +4.8 % | -4.0 % |
| acc_score top decile & flat | 957 | 5.43 % | 0.91 | 9.93 % | 0.91 | 9.20 % | 0.84 | 9.09 % | 1.02 | -0.7 % | -3.9 % |
| obv60 bottom decile | 3,951 | 3.06 % | 0.51 | 6.88 % | 0.63 | 6.96 % | 0.63 | 7.06 % | 0.79 | -0.5 % | -2.3 % |
| upvol bottom decile | 3,951 | 3.11 % | 0.52 | 5.90 % | 0.54 | 6.13 % | 0.56 | 5.11 % | 0.57 | +1.1 % | -1.7 % |
| voltrend bottom decile | 3,951 | 6.73 % | 1.13 | 12.76 % | 1.17 | 11.52 % | 1.05 | 9.64 % | 1.08 | +1.6 % | -4.6 % |
| squeeze_low bottom decile | 3,955 | 6.42 % | 1.07 | 11.66 % | 1.07 | 11.63 % | 1.06 | 9.00 % | 1.01 | +4.1 % | -3.2 % |
| quiet bottom decile | 276 | 6.16 % | 1.03 | 10.51 % | 0.96 | 10.51 % | 0.96 | 9.06 % | 1.02 | +0.3 % | -4.9 % |
| fgn60 bottom decile | 3,951 | 4.86 % | 0.81 | 8.12 % | 0.74 | 9.31 % | 0.85 | 4.20 % | 0.47 | +4.4 % | -1.4 % |
| acc_score bottom decile | 3,954 | 2.88 % | 0.48 | 5.59 % | 0.51 | 6.85 % | 0.63 | 5.72 % | 0.64 | +1.0 % | -2.4 % |

WYCKOFF permutation p (target shuffled within snapshot day, 2000 draws): 0.31334332833583206

### Arah hindsight: dari semua kenaikan +50 %, berapa yang sebelumnya membawa sinyal ini? (vs seberapa sering sinyalnya muncul)

| signal | signal frequency | share of +50 % risers carrying it | share of touch-+50 % | share of -30 % crashers | hindsight lift (risers / frequency) |
|---|---|---|---|---|---|
| WYCKOFF | 0.6 % | 0.7 % | 0.5 % | 0.6 % | 1.10 |
| obv60 top decile | 10.2 % | 19.8 % | 19.4 % | 19.7 % | 1.94 |
| upvol top decile | 10.2 % | 20.2 % | 20.0 % | 20.8 % | 1.98 |
| voltrend top decile | 10.2 % | 13.4 % | 14.5 % | 16.1 % | 1.32 |
| squeeze_low top decile | 10.2 % | 10.7 % | 11.2 % | 13.5 % | 1.05 |
| quiet top decile | 9.9 % | 10.2 % | 9.0 % | 7.1 % | 1.04 |
| fgn60 top decile | 10.2 % | 8.3 % | 7.5 % | 6.3 % | 0.81 |
| acc_score top decile | 10.2 % | 16.2 % | 16.0 % | 15.4 % | 1.59 |

