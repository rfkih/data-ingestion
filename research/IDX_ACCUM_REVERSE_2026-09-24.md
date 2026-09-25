# IDX - akumulasi sebelum kenaikan tinggi: dua arah kondisional - 2026-09-24 - descriptive, 0 new trials (cumulative N = 711)

Panel 2020-01-02 -> 2026-09-23, a snapshot every 10 trading days (150 snapshots), features over the 60 days ending the snapshot, outcome = the close 60 trading days later. 'Big rise' = +50 % held at day 60; 'touch' = the highest close in the 60 days >= +50 %; 'crash' = -30 % at day 60. Deciles are within-snapshot ranks.

## LIQ - 19,581 name-snapshots (131 names per snapshot)

Base rates: **P(+50 % held) = 5.37 %**, P(touch +50 %) = 9.49 %, P(+30 % held) = 10.51 %, P(-30 %) = 8.23 %; mean 60-day return +1.6 %, median -3.2 %.

### Arah strategi: P(kenaikan | sinyal) - dan cerminnya, P(crash | sinyal)

| signal | snapshots | P(+50 % held) | lift | P(touch +50 %) | lift | P(+30 %) | lift | P(-30 % crash) | lift | mean 60 d | median 60 d |
|---|---|---|---|---|---|---|---|---|---|---|---|
| WYCKOFF | 122 | 9.84 % | 1.83 | 12.30 % | 1.30 | 15.57 % | 1.48 | 9.02 % | 1.10 | +2.6 % | -1.2 % |
| flat only (control) | 10,278 | 3.44 % | 0.64 | 6.25 % | 0.66 | 7.66 % | 0.73 | 4.38 % | 0.53 | +1.1 % | -2.6 % |
| obv60 top decile | 2,041 | 10.04 % | 1.87 | 18.28 % | 1.93 | 16.61 % | 1.58 | 17.88 % | 2.17 | +3.2 % | -5.8 % |
| obv60 top decile & flat | 364 | 3.85 % | 0.72 | 10.44 % | 1.10 | 10.71 % | 1.02 | 12.36 % | 1.50 | -1.3 % | -3.4 % |
| upvol top decile | 2,041 | 10.24 % | 1.91 | 18.47 % | 1.95 | 16.56 % | 1.58 | 18.72 % | 2.27 | +3.1 % | -6.6 % |
| upvol top decile & flat | 358 | 3.63 % | 0.68 | 8.94 % | 0.94 | 8.66 % | 0.82 | 13.97 % | 1.70 | -3.4 % | -4.0 % |
| voltrend top decile | 2,041 | 6.37 % | 1.19 | 12.20 % | 1.29 | 12.49 % | 1.19 | 11.71 % | 1.42 | +0.9 % | -4.2 % |
| voltrend top decile & flat | 733 | 3.41 % | 0.64 | 7.37 % | 0.78 | 7.37 % | 0.70 | 8.19 % | 0.99 | -1.8 % | -3.6 % |
| squeeze_low top decile | 2,042 | 6.95 % | 1.30 | 11.85 % | 1.25 | 12.63 % | 1.20 | 11.75 % | 1.43 | +2.6 % | -3.7 % |
| squeeze_low top decile & flat | 622 | 4.18 % | 0.78 | 7.88 % | 0.83 | 8.04 % | 0.77 | 5.95 % | 0.72 | +2.7 % | -2.1 % |
| quiet top decile | 1,997 | 4.51 % | 0.84 | 7.96 % | 0.84 | 9.26 % | 0.88 | 7.11 % | 0.86 | +0.7 % | -3.4 % |
| quiet top decile & flat | 1,049 | 3.43 % | 0.64 | 5.62 % | 0.59 | 6.86 % | 0.65 | 4.19 % | 0.51 | +0.6 % | -2.2 % |
| fgn60 top decile | 2,041 | 4.70 % | 0.88 | 7.69 % | 0.81 | 9.06 % | 0.86 | 4.80 % | 0.58 | +2.8 % | -1.8 % |
| fgn60 top decile & flat | 1,129 | 2.66 % | 0.50 | 4.61 % | 0.49 | 6.11 % | 0.58 | 3.28 % | 0.40 | +0.3 % | -2.2 % |
| acc_score top decile | 2,037 | 8.35 % | 1.55 | 14.19 % | 1.50 | 14.58 % | 1.39 | 12.86 % | 1.56 | +3.5 % | -4.3 % |
| acc_score top decile & flat | 447 | 2.68 % | 0.50 | 6.26 % | 0.66 | 6.94 % | 0.66 | 8.95 % | 1.09 | -1.9 % | -2.8 % |
| obv60 bottom decile | 1,891 | 2.96 % | 0.55 | 5.39 % | 0.57 | 7.40 % | 0.70 | 6.08 % | 0.74 | -0.4 % | -2.9 % |
| upvol bottom decile | 1,891 | 3.28 % | 0.61 | 5.61 % | 0.59 | 7.24 % | 0.69 | 4.39 % | 0.53 | +1.5 % | -2.0 % |
| voltrend bottom decile | 1,891 | 7.46 % | 1.39 | 12.69 % | 1.34 | 11.69 % | 1.11 | 10.58 % | 1.29 | +2.2 % | -5.1 % |
| squeeze_low bottom decile | 1,893 | 5.49 % | 1.02 | 10.04 % | 1.06 | 10.83 % | 1.03 | 7.40 % | 0.90 | +3.0 % | -2.6 % |
| quiet bottom decile | 14 | 14.29 % | 2.66 | 14.29 % | 1.51 | 21.43 % | 2.04 | 0.00 % | 0.00 | +12.1 % | +6.8 % |
| fgn60 bottom decile | 1,891 | 2.96 % | 0.55 | 5.82 % | 0.61 | 7.93 % | 0.76 | 3.17 % | 0.39 | +2.3 % | -2.6 % |
| acc_score bottom decile | 1,890 | 2.54 % | 0.47 | 4.55 % | 0.48 | 6.46 % | 0.61 | 5.82 % | 0.71 | +0.2 % | -3.0 % |

WYCKOFF permutation p (target shuffled within snapshot day, 2000 draws): 0.03798100949525238

### Arah hindsight: dari semua kenaikan +50 %, berapa yang sebelumnya membawa sinyal ini? (vs seberapa sering sinyalnya muncul)

| signal | signal frequency | share of +50 % risers carrying it | share of touch-+50 % | share of -30 % crashers | hindsight lift (risers / frequency) |
|---|---|---|---|---|---|
| WYCKOFF | 0.6 % | 1.1 % | 0.8 % | 0.7 % | 1.83 |
| obv60 top decile | 10.4 % | 19.5 % | 20.1 % | 22.7 % | 1.87 |
| upvol top decile | 10.4 % | 19.9 % | 20.3 % | 23.7 % | 1.91 |
| voltrend top decile | 10.4 % | 12.4 % | 13.4 % | 14.8 % | 1.19 |
| squeeze_low top decile | 10.4 % | 13.5 % | 13.0 % | 14.9 % | 1.30 |
| quiet top decile | 10.2 % | 8.6 % | 8.6 % | 8.8 % | 0.84 |
| fgn60 top decile | 10.4 % | 9.1 % | 8.4 % | 6.1 % | 0.88 |
| acc_score top decile | 10.4 % | 16.2 % | 15.6 % | 16.3 % | 1.55 |

## THIN - 37,526 name-snapshots (250 names per snapshot)

Base rates: **P(+50 % held) = 5.92 %**, P(touch +50 %) = 10.59 %, P(+30 % held) = 10.94 %, P(-30 %) = 7.79 %; mean 60-day return +2.7 %, median -2.8 %.

### Arah strategi: P(kenaikan | sinyal) - dan cerminnya, P(crash | sinyal)

| signal | snapshots | P(+50 % held) | lift | P(touch +50 %) | lift | P(+30 %) | lift | P(-30 % crash) | lift | mean 60 d | median 60 d |
|---|---|---|---|---|---|---|---|---|---|---|---|
| WYCKOFF | 226 | 7.08 % | 1.20 | 9.73 % | 0.92 | 11.06 % | 1.01 | 8.85 % | 1.14 | +1.7 % | -2.7 % |
| flat only (control) | 20,002 | 3.95 % | 0.67 | 6.98 % | 0.66 | 7.98 % | 0.73 | 4.21 % | 0.54 | +1.8 % | -2.2 % |
| obv60 top decile | 3,835 | 11.68 % | 1.97 | 20.63 % | 1.95 | 18.02 % | 1.65 | 15.78 % | 2.03 | +6.3 % | -4.7 % |
| obv60 top decile & flat | 797 | 6.52 % | 1.10 | 12.17 % | 1.15 | 11.67 % | 1.07 | 10.16 % | 1.31 | -0.2 % | -4.0 % |
| upvol top decile | 3,835 | 11.99 % | 2.03 | 21.20 % | 2.00 | 17.94 % | 1.64 | 16.43 % | 2.11 | +6.0 % | -5.8 % |
| upvol top decile & flat | 750 | 7.60 % | 1.28 | 14.13 % | 1.33 | 12.53 % | 1.15 | 11.07 % | 1.42 | +0.1 % | -5.4 % |
| voltrend top decile | 3,835 | 7.77 % | 1.31 | 15.31 % | 1.45 | 13.66 % | 1.25 | 12.49 % | 1.60 | +2.8 % | -4.8 % |
| voltrend top decile & flat | 1,429 | 4.76 % | 0.80 | 9.17 % | 0.87 | 9.03 % | 0.83 | 7.63 % | 0.98 | -0.2 % | -3.7 % |
| squeeze_low top decile | 3,835 | 6.36 % | 1.07 | 11.45 % | 1.08 | 11.55 % | 1.06 | 10.43 % | 1.34 | +1.9 % | -2.9 % |
| squeeze_low top decile & flat | 1,348 | 4.01 % | 0.68 | 7.64 % | 0.72 | 7.34 % | 0.67 | 5.12 % | 0.66 | +1.5 % | -1.9 % |
| quiet top decile | 3,724 | 5.83 % | 0.98 | 9.61 % | 0.91 | 9.96 % | 0.91 | 5.88 % | 0.76 | +3.7 % | -1.2 % |
| quiet top decile & flat | 2,361 | 3.98 % | 0.67 | 5.97 % | 0.56 | 6.90 % | 0.63 | 3.64 % | 0.47 | +2.2 % | -1.0 % |
| fgn60 top decile | 3,835 | 4.82 % | 0.81 | 7.93 % | 0.75 | 9.15 % | 0.84 | 4.93 % | 0.63 | +3.4 % | -1.5 % |
| fgn60 top decile & flat | 2,117 | 2.60 % | 0.44 | 4.35 % | 0.41 | 5.53 % | 0.51 | 2.98 % | 0.38 | +0.7 % | -1.6 % |
| acc_score top decile | 3,838 | 9.46 % | 1.60 | 16.88 % | 1.59 | 15.66 % | 1.43 | 12.32 % | 1.58 | +5.6 % | -3.6 % |
| acc_score top decile & flat | 902 | 5.21 % | 0.88 | 9.42 % | 0.89 | 8.98 % | 0.82 | 8.31 % | 1.07 | -0.4 % | -3.5 % |
| obv60 bottom decile | 3,685 | 2.93 % | 0.49 | 6.16 % | 0.58 | 6.62 % | 0.61 | 5.83 % | 0.75 | +0.1 % | -2.1 % |
| upvol bottom decile | 3,685 | 2.96 % | 0.50 | 5.35 % | 0.50 | 5.75 % | 0.53 | 4.21 % | 0.54 | +1.6 % | -1.4 % |
| voltrend bottom decile | 3,685 | 6.81 % | 1.15 | 12.40 % | 1.17 | 11.56 % | 1.06 | 8.39 % | 1.08 | +2.3 % | -4.4 % |
| squeeze_low bottom decile | 3,688 | 6.16 % | 1.04 | 11.23 % | 1.06 | 11.52 % | 1.05 | 7.78 % | 1.00 | +4.5 % | -2.7 % |
| quiet bottom decile | 389 | 6.94 % | 1.17 | 11.83 % | 1.12 | 12.34 % | 1.13 | 6.43 % | 0.83 | +2.6 % | -4.0 % |
| fgn60 bottom decile | 3,685 | 4.78 % | 0.81 | 7.68 % | 0.73 | 9.15 % | 0.84 | 3.83 % | 0.49 | +3.9 % | -1.4 % |
| acc_score bottom decile | 3,684 | 2.85 % | 0.48 | 5.37 % | 0.51 | 6.68 % | 0.61 | 4.99 % | 0.64 | +1.4 % | -2.1 % |

WYCKOFF permutation p (target shuffled within snapshot day, 2000 draws): 0.24187906046976512

### Arah hindsight: dari semua kenaikan +50 %, berapa yang sebelumnya membawa sinyal ini? (vs seberapa sering sinyalnya muncul)

| signal | signal frequency | share of +50 % risers carrying it | share of touch-+50 % | share of -30 % crashers | hindsight lift (risers / frequency) |
|---|---|---|---|---|---|
| WYCKOFF | 0.6 % | 0.7 % | 0.6 % | 0.7 % | 1.20 |
| obv60 top decile | 10.2 % | 20.2 % | 19.9 % | 20.7 % | 1.97 |
| upvol top decile | 10.2 % | 20.7 % | 20.5 % | 21.6 % | 2.03 |
| voltrend top decile | 10.2 % | 13.4 % | 14.8 % | 16.4 % | 1.31 |
| squeeze_low top decile | 10.2 % | 11.0 % | 11.0 % | 13.7 % | 1.07 |
| quiet top decile | 9.9 % | 9.8 % | 9.0 % | 7.5 % | 0.98 |
| fgn60 top decile | 10.2 % | 8.3 % | 7.7 % | 6.5 % | 0.81 |
| acc_score top decile | 10.2 % | 16.3 % | 16.3 % | 16.2 % | 1.60 |

## Reading (written after the run) - study #133

The operator's objection was fair: many strategies hunt for accumulation before a big rise, so either the correlation is real or
the desk's measure is wrong. Both directions of the conditional were measured on 57,000 name-snapshots. The answer is that the
correlation is real in the direction people SEE it and empty in the direction a strategy NEEDS it - and that #131's measure was
not wrong, it was asked inside the one place (a flat base) where the signal carries nothing.

1. **The hindsight observation is true.** Of every liquid name that rose +50 % in 60 days, 19.5 % had been in the top decile of
   OBV accumulation beforehand, against a 10.4 % base frequency (THIN: 20.2 % vs 10.2 %). Look back from the winners and one in
   five "shows accumulation" - twice the chance. That is the pattern the folk strategies are built on, and it is not imaginary.
2. **The same tape precedes crashes just as often.** 22.7 % of the names that fell -30 % also carried that top-decile OBV
   beforehand (THIN 20.7 %). Forward: P(+50 %) rises from 5.4 % to 10.0 % (lift 1.87) and P(-30 %) rises from 8.2 % to 17.9 %
   (lift 2.17). Up-volume dominance is a sign that SOMETHING is happening to the name - a volatility signal - not that it is
   going up. The median 60-day return of the "accumulated" decile is -5.8 %, worse than the market's -3.2 %; the mean is
   positive only through the same thin right tail as the breakouts.
3. **Insist on the textbook picture and the signal disappears.** Accumulation is supposed to be stealthy: volume flowing in
   while price goes nowhere. Require flat price (|60-day move| <= 15 %) on top of top-decile OBV and P(+50 %) falls to 3.85 % -
   BELOW the 5.4 % base (lift 0.72) - while the crash lift stays at 1.50. Every accumulation proxy loses its rise-lift once price
   is flat (obv 0.72, upvol 0.68, voltrend 0.64, squeeze 0.78, quiet 0.64, foreign 0.50, composite 0.50; THIN 0.80-1.28). The
   OBV that "predicted" rises in point 2 was measuring a move already under way - up-volume is high because the price is rising -
   and once that is removed there is nothing left. The flat-only control says the same from the other side: flat names rise
   +50 % 3.4 % of the time and crash 4.4 % - half the market on both counts. Nothing is happening to them, in either direction.
4. **The full Wyckoff composite is the one cell that survives a straight face, and it is thin.** Flat + OBV top tercile + volume
   waking (>= 1.2x) + range squeeze (<= 0.5) + a rising floor: 122 liquid snapshots in six years (0.6 % of the tape), P(+50 %) 9.8 %
   (lift 1.83, permutation p 0.038), crash lift only 1.10, mean +2.6 %, median -1.2 %. On THIN - where the bandar stories live -
   the same composite is 226 snapshots, lift 1.20, p 0.24: not there. One tier, 122 events, one of some twenty cells read, and a
   median that is still negative: a lead worth a pre-registered test when the broker panel exists, not a finding.
5. **Foreign accumulation is a stability signal, not a rise signal.** Top-decile foreign net buying halves the crash rate (lift
   0.58) and slightly lowers the rise rate (0.88). It tells you the name will not blow up, which is useful for the value book and
   useless for a hunt for doublers - and it is the opposite of what the bandar narrative expects of it.
6. **Why the narrative persists.** (a) "Accumulation" is usually named after the rise, when the OBV slope is visible in the
   rear-view mirror - see point 1, and in the same mirror it sits behind the crashes nobody writes about. (b) Even the best
   forward cell gives a one-in-ten chance of the +50 % and a one-in-six chance of the -30 %; a strategy with ten names a year
   sees its one doubler and remembers it. (c) The desk's own honest version of the idea - Stockbit's "Acc" label on 20-day
   broker windows, menu 4 - showed the same shape: +2-5 pp over random names, t 0.6-1.6, gone on denser windows (menu 5).

**Was #131's measure wrong?** Its six proxies were computed inside 60-day bases - by construction the flat regime of point 3, the
one place where every tape-based accumulation measure carries nothing. Its nulls were the right answer to a narrower question.
The measure that has NOT been tested is the one the operator actually means - named brokers accumulating for months - and that
waits on the panel the 20:20 capture started building tonight. **Nothing here is a rule. Cumulative trials stay at 711.**
