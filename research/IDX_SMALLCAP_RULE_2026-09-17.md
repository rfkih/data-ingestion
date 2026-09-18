# IDX menu 12 — small-cap fundamental signals as costed rules — 2026-09-17 — 4 trials, cumulative N = 313

Book K = 10, monthly entries at the next close @offer, exits @bid, fees 0.10/0.20 %; 2020-01-02 -> 2026-09-16. COMPOSITE buy-and-hold +2.4 % | 20:-5 21:+8 22:+3 23:+6 24:-3 25:+21 26:-26

| arm | trades | hold d | hit | avg net | payoff | t | total | CAGR | Sharpe | mDD | years | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| random small caps | trail20 | 212 | 61 | 31 % | +10.54 % | 4.14 | 1.3 | +69 % | +8.5 % | 0.46 | -57 % | 20:+108 21:+15 22:-22 23:-33 24:+5 25:+65 26:-21 | reference |
| random small caps | hold250 | 50 | 251 | 42 % | +4.34 % | 1.62 | 0.4 | +14 % | +2.0 % | 0.21 | -72 % | 20:+71 21:-5 22:-54 23:-14 24:+3 25:+84 26:-6 | reference |
| sleeper_np | trail20 | 32 | 127 | 44 % | +56.21 % | 11.18 | 1.2 | +76 % | +9.2 % | 1.10 | -11 % | 20:+0 21:-1 22:-0 23:+5 24:+16 25:+41 26:+4 | tested: n<60,t<2.5,years<5/7 |
| sleeper_np | hold250 | 24 | 251 | 46 % | +4.26 % | 1.52 | 0.4 | -2 % | -0.4 % | 0.03 | -35 % | 20:+0 21:-6 22:-2 23:-2 24:-8 25:+29 26:-10 | tested: n<60,t<2.5,sharpe<1,mdd>25%,years<5/7,vs random |
| rev20_profit | trail20 | 175 | 54 | 33 % | +9.50 % | 3.74 | 1.0 | +61 % | +7.7 % | 0.46 | -47 % | 20:+0 21:-6 22:-30 23:-4 24:+20 25:+133 26:-10 | tested: t<2.5,sharpe<1,mdd>25%,years<5/7,vs random |
| rev20_profit | hold250 | 41 | 251 | 32 % | +42.22 % | 6.15 | 1.6 | +106 % | +11.8 % | 0.58 | -50 % | 20:+0 21:-1 22:-21 23:-18 24:+14 25:+157 26:+9 | tested: n<60,t<2.5,sharpe<1,mdd>25%,years<5/7,vs random |

Reading rule applied as declared: 0 candidate(s) of 4; near misses: 0.

Limits: as menus 10-11 (current listing board; growth from published YTD figures); ~1-year holds mean few trades per year and
positions open at the last bar are marked, not counted; costs = quoted closing spread + fees, no extra slippage.

## Reading (written after the run; rule fixed before it)

Costs and a book turn the event-study edge into something much thinner. Sideways + profit growth is RARE as a trade: with monthly
entries and 10 slots it produced 32 closed trades in the whole sample — and almost none before 2023, because the quarterly
comparatives the growth test needs are sparse in 2020–2022 (700–900 fundamental rows a year then, 1,600+ from 2024). Those 32 trades
have the loser-removal profile the event study promised (drawdown 11 %, payoff 11x, Sharpe 1.10, +56 % net per trade) but t = 1.2:
a handful of 2024–2025 winners, not evidence. Held a flat year without a stop it makes nothing (−0.4 %/yr). Revenue growth with profit
trades often enough (175 with the 20 % trail, 41 one-year holds) and compounds to +61 % / +106 %, but with 47–50 % drawdowns, losing
2022–2023, and 2025 alone contributing +133 % / +157 % — a small-cap boom year that random small caps also rode (+65 % / +84 %).
Sharpe 0.46–0.58 against random 0.21–0.46 is not separation.

**Verdict: 0 of 4, no near miss. The fundamental filter is real as a description — it removes the small caps that go to zero — but
it is too rare (profit growth on a sleeping stock) or too boom-dependent (revenue growth) to be a rule with money behind it on
this sample. What it is good for is the desk's existing job: the annual value book's second read, where "revenue up, profit up,
audited" already decides what stays. Cumulative 313 trials; the trend follower of menus 6–7 remains the only costed rule that
compounds through more than one regime, and it does so with drawdowns the money rule rejects.**
