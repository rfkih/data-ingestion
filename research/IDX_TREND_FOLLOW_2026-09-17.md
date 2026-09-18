# IDX menu 6 — trend following with trailing exits — 2026-09-17 — 10 trials, cumulative N = 277

Book of K = 10 slots, entry close t+1 @offer, exit close t+1 @bid, fees 0.10/0.20 %; 2020-01-02 -> 2026-09-16. COMPOSITE buy-and-hold +2.4 % | 20:-5 21:+8 22:+3 23:+6 24:-3 25:+21 26:-26

| arm (entry|exit|universe) | trades | avg hold d | hit | avg net | median | payoff | t | total | CAGR | Sharpe | mDD | years | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| random entries | ma20 | BLUE | 3627 | 4 | 33 % | -0.62 % | -1.06 % | 1.43 | -5.2 | -91 % | -30.6 % | -1.32 | -93 % | 20:-8 21:-5 22:-44 23:-41 24:-45 25:-10 26:-33 | reference |
| random entries | trail10 | BLUE | 436 | 35 | 35 % | +0.24 % | -4.48 % | 1.91 | 0.3 | +20 % | +2.8 % | 0.24 | -53 % | 20:+43 21:+28 22:-16 23:-11 24:-9 25:+8 26:-11 | reference |
| hi60 | ma20 | BLUE | 570 | 15 | 35 % | -0.04 % | -2.75 % | 1.86 | -0.1 | -4 % | -0.7 % | 0.05 | -50 % | 20:+9 21:+26 22:-24 23:-16 24:-13 25:+33 26:-6 | tested: t<2.5,sharpe<1,mdd>25%,years<5/7 |
| hi60 | ma50 | BLUE | 323 | 34 | 34 % | +0.26 % | -3.72 % | 2.00 | 0.2 | +10 % | +1.5 % | 0.17 | -41 % | 20:+12 21:+15 22:-10 23:-16 24:+1 25:+17 26:-6 | tested: t<2.5,sharpe<1,mdd>25%,years<5/7 |
| hi60 | trail10 | BLUE | 332 | 32 | 36 % | +0.71 % | -4.84 % | 2.01 | 0.6 | +17 % | +2.5 % | 0.23 | -35 % | 20:+14 21:+18 22:-11 23:-13 24:-3 25:+18 26:-2 | tested: t<2.5,sharpe<1,mdd>25%,years<5/7,vs random |
| cross | ma20 | BLUE | 390 | 11 | 29 % | -1.09 % | -2.16 % | 1.66 | -2.1 | -33 % | -5.9 % | -0.51 | -39 % | 20:+1 21:-2 22:-7 23:-12 24:-9 25:-9 26:-0 | tested: t<2.5,sharpe<1,mdd>25%,years<5/7 |
| cross | ma50 | BLUE | 333 | 25 | 29 % | +0.10 % | -2.90 % | 2.48 | 0.1 | +2 % | +0.4 % | 0.10 | -31 % | 20:+5 21:+13 22:-8 23:-16 24:+2 25:-0 26:+8 | tested: t<2.5,sharpe<1,mdd>25%,years<5/7 |
| cross | trail10 | BLUE | 265 | 38 | 30 % | -2.36 % | -5.93 % | 1.49 | -2.9 | -38 % | -7.2 % | -0.47 | -53 % | 20:+5 21:+2 22:-11 23:-17 24:-16 25:-14 26:+9 | tested: t<2.5,sharpe<1,mdd>25%,years<5/7,vs random |
| momq | ma20 | BLUE | 1053 | 10 | 29 % | -0.23 % | -2.24 % | 2.30 | -0.5 | -38 % | -7.1 % | -0.23 | -60 % | 20:+5 21:+5 22:-29 23:-8 24:-12 25:+50 26:-34 | tested: t<2.5,sharpe<1,mdd>25%,years<5/7 |
| momq | ma50 | BLUE | 451 | 29 | 34 % | +1.01 % | -3.40 % | 2.25 | 0.9 | +46 % | +6.0 % | 0.36 | -45 % | 20:+20 21:+25 22:-12 23:-2 24:-8 25:+73 26:-28 | tested: t<2.5,sharpe<1,mdd>25%,years<5/7 |
| momq | trail10 | BLUE | 536 | 25 | 34 % | +0.67 % | -5.44 % | 2.15 | 0.6 | -7 % | -1.2 % | 0.06 | -50 % | 20:+29 21:+11 22:-22 23:-0 24:-5 25:+46 26:-40 | tested: t<2.5,sharpe<1,mdd>25%,years<5/7,vs random |
| hi60 | trail10 | LIQ | 480 | 27 | 38 % | +3.10 % | -5.65 % | 2.51 | 2.5 | +206 % | +18.9 % | 0.92 | -36 % | 20:+32 21:+83 22:-4 23:-12 24:+12 25:+76 26:-23 | tested: sharpe<1,mdd>25%,years<5/7 |

Reading rule applied as declared: 0 candidate(s) of 10.

Limits: current listing board (not PIT); signals and exits one day late (close-to-close); no quality gate beyond liquidity; dividends
ignored; costs = quoted closing spread + fees, no extra slippage; positions still open at the last bar are marked, not counted as trades.

## Reading (written after the run; verdicts fixed before it)

Nine of ten arms are what six menus have shown before: a trend rule on IDX blue chips returns roughly nothing after the
spread (best momq|ma50 +6 % a year, Sharpe 0.36, drawdown 45 %). The tenth is different in kind. hi60|trail10 on the WIDER
universe (liquid names down to Rp 100) shows the textbook trend-following signature — hit rate 38 %, payoff 2.5, +3.1 % net per
trade, 27-day average hold — and compounds to +206 % over 2020–2026 (+18.9 %/yr) with t = 2.5, against random entries with the
same exit at +2.8 %/yr. It fails the rule on three counts that all say the same thing: the ride is rough — Sharpe 0.92, a 36 %
drawdown, and three losing years (2022 −4 %, 2023 −12 %, 2026 −23 %) against four winners (2020 +32 %, 2021 +83 %, 2024 +12 %,
2025 +76 %). It is also one arm in ten: on its own it could be a lucky corner of the parameter space.

**Verdict: 0 of 10. One lead worth exactly one more menu — not tuning, robustness: does the wide-universe breakout survive
neighbouring parameters (trail 8/12/15 %, 40/90-day highs, volume 1×/2×) and does the operator's own combination — the
same entry restricted to names that pass the audited fundamental gate (point-in-time) — make it steadier? If the lead holds
across most neighbours and the gated version keeps the return with a shallower drawdown, it goes to a paper book; if it
lives only at 60/10/1.5, it was luck.**
