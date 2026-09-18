# IDX menu 7 — robustness of the trend lead + fundamental gate — 2026-09-17 — 10 trials, cumulative N = 287

| arm | trades | hold d | hit | avg net | payoff | t | total | CAGR | Sharpe | mDD | years | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| lead 60/10/1.5 (LIQ) | 480 | 27 | 38 % | +3.10 % | 2.51 | 2.5 | +206 % | +18.9 % | 0.92 | -36 % | 20:+32 21:+83 22:-4 23:-12 24:+12 25:+76 26:-23 | reference (menu 6) |
| random + trail10 (LIQ) | 466 | 33 | 36 % | +1.31 % | 2.14 | 1.1 | +40 % | +5.3 % | 0.35 | -53 % | 20:+67 21:+16 22:-20 23:-11 24:-11 25:+23 26:-7 | reference |
| trail8 (60, 0.08, 1.5) | 660 | 19 | 37 % | +1.19 % | 2.06 | 1.5 | +79 % | +9.4 % | 0.55 | -34 % | 20:+21 21:+50 22:-17 23:-13 24:+17 25:+22 26:-5 | tested: t<2.5,sharpe<1,mdd>25%,years<5/7,vs random |
| trail12 (60, 0.12, 1.5) | 365 | 36 | 36 % | +3.69 % | 2.78 | 2.4 | +185 % | +17.6 % | 0.87 | -32 % | 20:+32 21:+44 22:+19 23:-4 24:+2 25:+60 26:-18 | tested: t<2.5,sharpe<1,mdd>25% |
| trail15 (60, 0.15, 1.5) | 255 | 52 | 38 % | +3.81 % | 2.48 | 2.1 | +171 % | +16.7 % | 0.85 | -33 % | 20:+32 21:+43 22:+12 23:-14 24:-3 25:+44 26:+7 | tested: t<2.5,sharpe<1,mdd>25% |
| hi40 (40, 0.1, 1.5) | 512 | 26 | 38 % | +2.30 % | 2.25 | 2.1 | +145 % | +14.9 % | 0.74 | -43 % | 20:+30 21:+87 22:+0 23:-22 24:-0 25:+36 26:-5 | tested: t<2.5,sharpe<1,mdd>25%,years<5/7,vs random |
| hi90 (90, 0.1, 1.5) | 480 | 27 | 40 % | +3.15 % | 2.29 | 2.7 | +229 % | +20.3 % | 0.98 | -33 % | 20:+32 21:+95 22:-5 23:-14 24:+3 25:+73 26:-13 | tested: sharpe<1,mdd>25%,years<5/7 |
| vol1 (60, 0.1, 1.0) | 503 | 26 | 34 % | +1.77 % | 2.46 | 1.6 | +82 % | +9.7 % | 0.54 | -42 % | 20:+31 21:+67 22:-15 23:-20 24:+8 25:+47 26:-22 | tested: t<2.5,sharpe<1,mdd>25%,years<5/7,vs random |
| vol2 (60, 0.1, 2.0) | 472 | 27 | 38 % | +2.44 % | 2.25 | 2.2 | +150 % | +15.3 % | 0.78 | -35 % | 20:+29 21:+65 22:+11 23:-12 24:+2 25:+52 26:-23 | tested: t<2.5,sharpe<1,mdd>25%,vs random |
| loose | 403 | 31 | 35 % | +0.26 % | 1.96 | 0.3 | +13 % | +1.9 % | 0.19 | -44 % | 20:+23 21:+24 22:-5 23:-22 24:+1 25:+21 26:-19 | tested: t<2.5,sharpe<1,mdd>25%,years<5/7,vs random | not steadier |
| strict | 314 | 35 | 37 % | +1.16 % | 2.05 | 0.8 | +26 % | +3.7 % | 0.31 | -43 % | 20:+11 21:+5 22:-6 23:-14 24:-10 25:+54 26:-3 | tested: t<2.5,sharpe<1,mdd>25%,years<5/7,vs random | not steadier |
| small | 495 | 24 | 42 % | +4.16 % | 2.38 | 3.5 | +442 % | +29.9 % | 1.34 | -30 % | 20:+24 21:+65 22:+29 23:-5 24:+1 25:+137 26:-9 | tested: mdd>25% |

Candidates by the menu-6 rule: 0 of 10.
Robustness read: 5 of 7 neighbours have CAGR >= 10 % with t >= 2.0 -> the lead is **ROBUST** (earns an out-of-sample paper track `trend`, no money).
Gated arms: loose not steadier (mDD -44 % vs -36 %, CAGR +1.9 % vs +18.9 %); strict not steadier (mDD -43 %, CAGR +3.7 %).

Limits: as menu 6; the fundamental gate is point-in-time by publication date, evaluated monthly.

## Reading (written after the run; verdicts and the robustness rule fixed before it)

The lead is not a lucky corner: five of seven neighbours keep a CAGR above 10 % with t >= 2 (trail 12/15 %, 40/90-day highs,
2x volume); the two that fall short (8 % trail, 1x volume) still make +9 %/yr. Moving the high to 90 days is slightly better
than 60. The edge lives where the annual book does not go: restricted to LIQ names that are NOT blue chips (value < Rp 20 bn a day
or price < Rp 1,000) it is +442 % (+29.9 %/yr), Sharpe 1.34, t 3.5, hit 42 %, payoff 2.4, six of seven years positive, drawdown
30 % — failing the money rule on the drawdown alone. The operator's fundamental gate makes it worse, not steadier: names passing the
audited loose gate +1.9 %/yr, strict +3.7 %/yr. Breakouts on volume pay in the names the quality gate rejects — retail-driven,
speculative, and therefore prone to the 30–36 % drawdowns and the losing years (2022–23, 2026) that keep every arm out of the
money rule. Deflated Sharpe at N = 287: lead 0.29, small 0.70 — the small-cap arm is the only figure in seven menus with any
statistical standing after the trial count.

**Verdict: 0 of 10 for money; the lead is ROBUST and earns the declared out-of-sample paper track — a paper book `trend` running
hi60 / >MA200 / volume >= 1.5x / 10 % trailing stop on the liquid universe (the declared rule; the small-cap cut is recorded as a
second paper variant, not chosen after the fact), scored after >= 60 closed trades. No money until a live-paper record
reproduces the profile, and the drawdown rule is still the rule.**
