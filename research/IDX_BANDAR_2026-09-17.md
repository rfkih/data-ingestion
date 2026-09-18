# IDX menu 4 — bandarmologi — 2026-09-17 — 10 trials, cumulative N = 258

Feed: 46 names, 1703 windows of 20 trading days, 2023-09-04 -> 2026-09-16; signals on window ends; entry close t+1 @offer, exit @bid, fees 0.10/0.20 %.

| arm | H | trades | hit | gross/trade | net/trade | t(basket) | total | Sharpe | mDD | expo | years | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| random (signal dates) | 20 | 175 | 38 % | -0.70 % | -1.37 % | -1.1 | -2 % | -0.27 | -3 % | 2 % | 23:-1 24:-0 25:+1 26:-1 | reference |
| random (signal dates) | 60 | 165 | 39 % | -1.47 % | -2.13 % | -0.8 | -1 % | -0.18 | -3 % | 2 % | 23:-0 24:-0 25:+1 26:-1 | reference |
| big_acc | 20 | 80 | 46 % | +1.97 % | +1.30 % | 0.8 | +1 % | 0.27 | -2 % | 1 % | 23:+1 24:+0 25:+1 26:-1 | tested: n,t<2.5,sharpe<1 |
| big_acc | 60 | 77 | 42 % | -2.29 % | -2.93 % | 0.1 | -1 % | -0.20 | -2 % | 1 % | 23:+0 24:+0 25:+0 26:-2 | tested: n,t<2.5,sharpe<1,vs random |
| acc | 20 | 158 | 48 % | +1.58 % | +0.94 % | 0.6 | +2 % | 0.27 | -3 % | 2 % | 23:-0 24:+1 25:+3 26:-2 | tested: t<2.5,years,sharpe<1 |
| acc | 60 | 149 | 50 % | +4.06 % | +3.40 % | 1.6 | +2 % | 0.32 | -3 % | 2 % | 23:+0 24:+1 25:+2 26:-2 | tested: n,t<2.5,sharpe<1 |
| breadth | 20 | 164 | 42 % | +0.79 % | +0.16 % | 0.1 | +0 % | 0.08 | -2 % | 2 % | 23:-0 24:-1 25:+1 26:+0 | tested: t<2.5,years,sharpe<1,vs random |
| asing | 20 | 158 | 46 % | +0.74 % | +0.09 % | 0.2 | -0 % | -0.02 | -4 % | 2 % | 23:-0 24:+1 25:+2 26:-3 | tested: t<2.5,years,sharpe<1,vs random |
| asing | 60 | 151 | 42 % | +0.33 % | -0.31 % | 0.2 | -1 % | -0.10 | -4 % | 2 % | 23:+0 24:-0 25:+2 26:-3 | tested: t<2.5,years,sharpe<1,vs random |
| lokal_quiet | 20 | 89 | 47 % | +0.03 % | -0.60 % | 0.4 | -1 % | -0.22 | -2 % | 1 % | 23:-0 24:-0 25:+0 26:-1 | tested: n,t<2.5,years,sharpe<1,vs random |
| persist | 20 | 28 | 32 % | +2.69 % | +2.11 % | 0.9 | +0 % | 0.22 | -1 % | 0 % | 23:+0 24:+0 25:+1 26:-1 | tested: n,t<2.5,sharpe<1,vs random |
| persist | 60 | 26 | 50 % | +3.26 % | +2.71 % | 0.6 | +0 % | 0.18 | -1 % | 0 % | 23:+0 24:+0 25:+0 26:-0 | tested: n,t<2.5,sharpe<1,vs random |
| dist | 20 | 173 | 44 % | -0.07 % | -0.74 % | -0.4 | -2 % | -0.31 | -5 % | 2 % | 23:+0 24:+1 25:+0 26:-3 | reference (mirror) |

Gross forward returns by the API's own label (no costs, every fetched name, equal weight):

| label | n | P(up 20d) | avg 20d | median 20d | P(up 60d) | avg 60d | median 60d |
|---|---|---|---|---|---|---|---|
| broker_accdist= | 880 | 46 % | +1.06 % | -0.59 % | 46 % | +4.25 % | -1.30 % |
| broker_accdist=Acc | 273 | 52 % | +3.31 % | +0.49 % | 52 % | +10.47 % | +1.44 % |
| broker_accdist=Dist | 305 | 46 % | +1.94 % | -1.10 % | 46 % | +7.55 % | -1.22 % |
| top1_label= | 880 | 46 % | +1.06 % | -0.59 % | 46 % | +4.25 % | -1.30 % |
| top1_label=Big Acc | 90 | 52 % | +3.21 % | +0.52 % | 46 % | +3.60 % | -1.46 % |
| top1_label=Big Dist | 103 | 47 % | +3.14 % | -1.53 % | 51 % | +15.71 % | +1.07 % |
| top1_label=Neutral | 134 | 49 % | +2.06 % | -0.39 % | 47 % | +9.34 % | -1.16 % |
| top1_label=Normal Acc | 62 | 50 % | +1.60 % | +0.00 % | 60 % | +9.53 % | +4.50 % |
| top1_label=Normal Dist | 57 | 47 % | +0.77 % | -0.54 % | 47 % | +6.52 % | -0.53 % |
| top1_label=Small Acc | 56 | 54 % | +3.84 % | +0.94 % | 48 % | +11.06 % | -1.07 % |
| top1_label=Small Dist | 76 | 45 % | +3.28 % | -0.96 % | 45 % | +5.08 % | -2.71 % |

Reading rule applied as declared: 0 candidate(s) of 10.

Limits: 3 years of data (2023-09 →) on 46 names; 20-day windows (a signal only every 20 days per name); the API's labels are
Stockbit's own definitions; net by investor class uses the API's broker classification; close-to-close execution as in menus 1–3.

## Reading (written after the run; the verdicts above were fixed before it)

Two things the table cannot say by itself. (1) The portfolio columns are near-empty by construction: a signal exists only on
window-end dates (37 per name) and each basket is held 20–60 days at 1/(K·H) weight, so exposure is 1–2 % and Sharpe / totals
sit at zero for every arm — the per-trade columns and the random reference are the evidence here, not the portfolio ones.
(2) Sample size: 46 names × 37 windows over 3 years, of which 2025 was a +21 % index year that lifts every mean above its median.

What the per-trade numbers show. Names the API labels "Acc" beat random names drawn on the same dates by +2.3 pp net over the
next 20 days (+0.94 % vs −1.37 %) and by +5.5 pp over 60 days (+3.40 % vs −2.13 %), hit rate 48–50 % vs 38–39 %; "Big Acc" top-1
buyers +1.30 % net over 20 days; a persistent top-1 buyer +2.1–2.7 % (n = 28). Foreign-class net buying and buying breadth carry
nothing (≈ random). The label table (gross, every name, equal weight) agrees: after "Acc" the name is up 60 days later 52 % of
the time, median +1.4 %; after "Dist" 46 %, median −1.2 %; base rate 46 %, −1.3 %. That is a real-looking tilt of the order of
2–3 pp per month — and a t-statistic of 0.6–1.6, i.e. not yet separable from noise with this sample.

**Verdict: 0 of 10 by the declared rule. Broker-level accumulation is the first thing in 62 trials with a positive after-cost
gap over random that survives a straight face, and it is not tradeable on this evidence. The one follow-up worth its cost is
a denser sample — 5-trading-day windows for the last 12 months on the same 46 names (~2,300 requests at 1/s) — which
multiplies the observations by four and lets the signal be re-read at H = 5/10/20. If the gap holds at t >= 2.5 there, a paper
book; if not, closed.** The feed itself stays useful either way: who accumulates or distributes a held name belongs on its card.
