# IDX menu 29 — day trading (open -> close, long only) — 2020-01-01 -> 2026-09-21

Universe: main board, v60 >= Rp 5 bn, not locked; 455 names, 206,838 eligible name-days; opens: {'none': 684281, 'yahoo': 389322, 'idx': 292266}.
Execution: buy open + 1 tick, sell close - 1 tick, fees 0.10 % + 0.20 %, up to 10 names a day, equal weight. Pre-registered in `research/idx_daytrade.py`; 8 trials (cumulative 528).

## The market's own intraday vs overnight return (equal-weight across the eligible universe)

| year | intraday bps/day | overnight bps/day | intraday total | overnight total | days |
|---|---|---|---|---|---|
| 2020 | +1.0 | +35.3 | +0.0 % | +51.3 % | 118 |
| 2021 | -18.3 | +23.0 | -37.3 % | +76.2 % | 247 |
| 2022 | -18.9 | +14.1 | -37.7 % | +41.4 % | 246 |
| 2023 | -16.8 | +12.3 | -33.4 % | +34.1 % | 239 |
| 2024 | -15.7 | +14.8 | -31.6 % | +42.0 % | 237 |
| 2025 | -13.6 | +30.8 | -28.5 % | +104.9 % | 236 |
| 2026 | -31.1 | +18.5 | -43.2 % | +35.7 % | 169 |
| all | -16.9 | +20.2 | -92.8 % | +1895.5 % | 1492 |

## Arms

| arm | trades | days | hit | gross/trade | net/trade | t | Sharpe | total | mDD | years + | by year (%) | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| random | 14,920 | 1,492 | 23 % | -17 bps | **-151 bps** | -38.5 | -15.84 | -100 % | -100 % | 0/7 | 20:-134 21:-370 22:-378 23:-369 24:-355 25:-340 26:-302 | reference |
| gap_up | 6,122 | 1,376 | 24 % | -156 bps | **-301 bps** | -28.2 | -12.05 | -100 % | -100 % | 0/7 | 20:-156 21:-630 22:-950 23:-896 24:-714 25:-379 26:-415 | tested: net<=0,t<3,sharpe<1,years,vs random |
| gap_down | 3,831 | 1,209 | 46 % | +229 bps | **+68 bps** | 4.5 | 2.06 | +72131 % | -79 % | 6/7 | 20:+51 21:+161 22:+77 23:+191 24:+338 25:+14 26:-15 | CANDIDATE |
| prev_breakout | 7,683 | 1,405 | 26 % | -28 bps | **-148 bps** | -19.7 | -8.33 | -100 % | -100 % | 0/7 | 20:-141 21:-253 22:-354 23:-361 24:-376 25:-367 26:-225 | tested: net<=0,t<3,sharpe<1,years,vs random |
| prev_drop | 12,261 | 1,473 | 30 % | -10 bps | **-148 bps** | -21.6 | -8.94 | -100 % | -100 % | 0/7 | 20:-133 21:-332 22:-389 23:-373 24:-388 25:-292 26:-270 | tested: net<=0,t<3,sharpe<1,years,vs random |
| mom5 | 14,920 | 1,492 | 29 % | -20 bps | **-155 bps** | -27.3 | -11.24 | -100 % | -100 % | 0/7 | 20:-135 21:-269 22:-394 23:-391 24:-416 25:-345 26:-362 | tested: net<=0,t<3,sharpe<1,years,vs random |
| rev5 | 14,920 | 1,492 | 28 % | -4 bps | **-150 bps** | -24.8 | -10.18 | -100 % | -100 % | 0/7 | 20:-160 21:-355 22:-365 23:-388 24:-362 25:-348 26:-265 | tested: net<=0,t<3,sharpe<1,years,vs random |
| trend_set | 4,382 | 1,203 | 27 % | -14 bps | **-136 bps** | -13.1 | -6.00 | -100 % | -100 % | 0/7 | 20:-102 21:-144 22:-254 23:-281 24:-306 25:-352 26:-201 | tested: net<=0,t<3,sharpe<1,years,vs random |
| vol_surge | 3,687 | 1,233 | 24 % | -72 bps | **-213 bps** | -18.2 | -8.23 | -100 % | -100 % | 0/7 | 20:-175 21:-440 22:-422 23:-398 24:-376 25:-482 26:-338 | tested: net<=0,t<3,sharpe<1,years,vs random |

## Reading

- Candidates by the declared bar: gap_down.
- Every trade pays ~30 bps of fees plus two ticks (the open offer and the closing bid); a day trade has to beat that every day it is on.
- The intraday-vs-overnight table is the structural fact: it says whether being long during the session, on average, is paid at all.

## Validation of the one candidate (read after the run; splits, not tuning)

| gap_down 2 %, split | trades | hit | net/trade | median | t | Sharpe | years + |
|---|---|---|---|---|---|---|---|
| as run (both open sources) | 3,831 | 46 % | +68 bps | -30 | 4.5 | 2.06 | 6/7 |
| **IDX opens only** | 1,762 | 39 % | **-55 bps** | -97 | -2.8 | -1.78 | 1/7 |
| Yahoo-filled opens only | 2,197 | 51 % | +126 bps | +27 | 6.7 | 3.59 | 5/7 |
| Yahoo, open == day low (969 of 2,197 = 44 %) | 969 | 72 % | +347 bps | +234 | 15.6 | 10.1 | 5/5 |
| Yahoo, open != day low | 1,188 | 32 % | -145 bps | -179 | -7.5 | -4.86 | 0/7 |
| IDX, open != day low | 1,514 | 32 % | -142 bps | -157 | -7.5 | -5.04 | 0/7 |
| IDX, fills at +/-2 ticks | 1,762 | 31 % | -146 bps | -177 | -7.5 | -4.78 | 0/7 |
| IDX, v60 >= 20 bn | 1,349 | 39 % | -84 bps | -95 | -5.3 | -3.65 | 0/7 |
| IDX, threshold 1 % / 3 % / 5 % | 4,249 / 1,037 / 516 | 32 / 44 / 49 % | -103 / -3 / +169 bps | -111 / -30 / -7 | -12.6 / -0.1 / 3.0 | | 0 / 3 / 6 of 7 |

**gap_down is a DATA ARTEFACT, not a candidate.** The whole profit sits in Yahoo-filled rows whose "open" equals the day's low (44 % of
those rows vs 14 % of IDX-sourced rows): Yahoo's open for .JK names is often the session low or a stale print, so "buy the open, sell the
close" is mechanically profitable there. On IDX's own opening prices the same rule loses 55 bps a trade (t -2.8). Only the 5 % gap
neighbour on IDX opens is positive (+169 bps, t 3.0, 516 trades, 2025-26 only, median -7): logged as "to watch" when more IDX opens exist,
not a trial result. Lesson for every open-based study (incl. menu 16 ARA, same fill recipe): **opens must be IDX-sourced**; Yahoo opens
are not usable for entry prices. The intraday-vs-overnight table is if anything understated by the artefact (a low open inflates
intraday returns): on 2025-26, where most opens are IDX's, intraday is -14 / -31 bps a day.

**Verdict: 0 of 8.** Long-only day trading on IDX starts 17 bps a day behind before costs and pays ~130 bps a round trip; no rule tested
recovers that. The overnight side (+20 bps a day, +1,895 % over the window) is where the market pays for holding risk - which is what
the desk's books already do.

## The one thing worth a follow-up: gap <= -5 % fade on IDX opens (post-hoc neighbour, NOT a trial result)

516 trades (2020-24: 112, 2025: 141, 2026: 263), mean **+182 bps**, median -7, hit 49 %, daily t 2.97 (233 days), 6/7 years (2023 -138 on n 14).
Skewed: without the top 1 % of trades +142, without the top 5 % +41. By gap: -5..-7 % +66 (n 260), below -7 % +300 (n 256). By market:
on IHSG down days +8 (n 321), on up days +468 (n 195) - the reversal is paid when the index also bounces. Fills at +/-2 ticks still +81;
K = 5 +156. Placebo (random eligible names on the same days) -145 +/- 20 -> the names are special, not the days.
Mechanism is plausible (opening overreaction to idiosyncratic bad news / forced selling, intraday reversion) and the sample grows by
~600 IDX opens a day now. Menu 29b (pre-registered): thresholds -5 / -7 / -10 %, IDX opens only, placebo + neighbours, exits close and
next open, money rule. Not adoptable before that.

