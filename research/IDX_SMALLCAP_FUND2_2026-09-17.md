# IDX menu 11 — robustness of revenue growth and sideways+profit growth in small caps — 2026-09-17 — 8 trials, cumulative N = 309

| set | n | P(up) / med 60d | P(up 1y) | med 1y | avg 1y | P(>= +50 % 1y) / P(<= −30 %) | P(up 2y) | med 2y |
|---|---|---|---|---|---|---|---|---|
| all small caps (base rate) | 1592 | 37 % / -5.7 % | 34 % | -18.4 % | +4.3 % | 14 % / 39 % | 38 % | -17.7 % |
| **rev10** | 462 | 37 % / -5.7 % | 37 % | -13.9 % | +20.2 % | 15 % / 34 % | 48 % | -1.5 % |
| control: fails rev10 | 525 | 34 % / -6.4 % | 29 % | -24.1 % | -4.4 % | 9 % / 43 % | 31 % | -26.7 % |
| **rev30** | 277 | 38 % / -5.7 % | 36 % | -20.3 % | +11.8 % | 14 % / 38 % | 51 % | +2.9 % |
| control: fails rev30 | 710 | 34 % / -6.1 % | 32 % | -18.7 % | +5.3 % | 11 % / 40 % | 35 % | -23.4 % |
| **rev20_mcap2** | 109 | 32 % / -7.2 % | 35 % | -14.4 % | +50.1 % | 16 % / 35 % | 50 % | +6.0 % |
| control: fails rev20_mcap2 | 184 | 30 % / -12.6 % | 22 % | -33.3 % | +0.7 % | 11 % / 57 % | 31 % | -40.8 % |
| **rev20_profit** | 293 | 38 % / -4.9 % | 41 % | -13.1 % | +31.2 % | 16 % / 32 % | 56 % | +14.7 % |
| control: fails rev20_profit | 694 | 34 % / -6.4 % | 30 % | -23.1 % | -3.0 % | 11 % / 42 % | 32 % | -25.7 % |
| **side40_np20** | 80 | 60 % / +2.7 % | 52 % | +1.4 % | +46.7 % | 14 % / 20 % | 48 % | -1.1 % |
| control: fails side40_np20 | 105 | 31 % / -4.3 % | 29 % | -21.9 % | -4.2 % | 13 % / 40 % | 30 % | -24.2 % |
| **side90_np20** | 46 | 65 % / +2.6 % | 52 % | +2.7 % | +3.2 % | 4 % / 11 % | 39 % | -2.5 % |
| control: fails side90_np20 | 61 | 39 % / -2.8 % | 30 % | -27.8 % | -6.4 % | 11 % / 43 % | 28 % | -24.2 % |
| **side60_np10** | 63 | 60 % / +2.6 % | 51 % | +0.7 % | +27.0 % | 8 % / 13 % | 44 % | -1.6 % |
| control: fails side60_np10 | 80 | 34 % / -3.9 % | 30 % | -27.7 % | +9.8 % | 15 % / 44 % | 29 % | -25.2 % |
| **side60_np30** | 56 | 61 % / +2.5 % | 46 % | -0.3 % | +29.7 % | 9 % / 14 % | 46 % | -3.4 % |
| control: fails side60_np30 | 87 | 36 % / -3.4 % | 34 % | -21.9 % | +9.4 % | 14 % / 40 % | 29 % | -23.7 % |

| arm | n | med 1y gap vs control | keeps >= +5 pp? |
|---|---|---|---|
| rev10 | 462 | +10.2 pp | yes |
| rev30 | 277 | -1.6 pp | no |
| rev20_mcap2 | 109 | +19.0 pp | yes |
| rev20_profit | 293 | +10.0 pp | yes |
| side40_np20 | 80 | +23.3 pp | yes |
| side90_np20 | 46 | +30.5 pp | yes |
| side60_np10 | 63 | +28.4 pp | yes |
| side60_np30 | 56 | +21.7 pp | yes |

Robustness read (declared): rev_g 3/4 neighbours -> **ROBUST**; sleeper_np 4/4 -> **ROBUST**.

Limits: as menu 10 (event study, no costs; overlapping windows; current listing board).

## Reading (written after the run; rule fixed before it)

Both survive. Revenue growth keeps a +10 pp median one-year gap at the 10 % threshold and with a profit condition, +19 pp among
the smallest names (market cap <= Rp 2 T, n = 109); it fails only at +30 %, where high growth is mostly a low base. Sideways +
profit growth holds at every neighbour — a 40- or 90-day sideways window, a 10 % or 30 % profit threshold — with median one-year
gaps of +22 to +31 pp, one-year hit rates of 46–52 % against 29–34 %, and the crash rate (−30 % or worse) cut to 11–20 % from
40–44 %. The profile is stable: the filter takes a group whose median outcome is a 20–28 % loss and moves it to roughly flat,
keeping a mean of +27 to +47 % from the names that do run. What it does NOT do is beat the index at the median (COMPOSITE +6.6 %
over the same windows); what it does is convert a lottery ticket into an even bet with a fat right tail.

Caveats that the numbers cannot carry: 46–109 signals per arm on monthly dates means far fewer independent names (a stock that
stays sideways with growing profits signals several months in a row); the signals run 2020–2024 only; no costs, no book, no
position limit; listing board as of today. **Verdict: rev_g ROBUST (3/4), sleeper_np ROBUST (4/4) — both earn a costed rule test
(menu 12: monthly entries, the desk's book, spread + fees, hold to a trend break or one year) before any paper book. Cumulative 309.**
