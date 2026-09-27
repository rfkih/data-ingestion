# IDX menu DT-3 — raising the gross edge (auctions, selectivity, timing) — 2026-09-27

Operator: "ada plan buat meningkatkan keuntungan kotornya?" -> "okay boleh". Follows DT-2 (#397, 0/15). Script
`research/idx_daytrade3.py` (pre-registered in its docstring). Sample: Yahoo 1-hour bars, 713 sessions 2023-09-13 .. 2026-09-25,
plus official auction prints (daily_summary). **6 trials; cumulative N 1057 -> 1063. Result: 0 of 6.**

| arm | lever | trades | hit | gross bps | cost bps | **net bps** | t (daily) | placebo pct | by year (net) | verdict (failed) |
|---|---|---|---|---|---|---|---|---|---|---|
| C1 day momentum, close auction -> next open auction | auctions | 2,367 | 50 % | **+51** | 50 | **+0** | -0.1 | 100 | 23:+0 24:-10 25:+14 26:-13 | no (t, cost x1.5, years) |
| C2 last-hour momentum, same execution | auctions | 2,391 | 40 % | +39 | 50 | -11 | -2.9 | 100 | | no |
| C3 in play (vol >= 5x, up yesterday), open -> close auction | selectivity | 548 | 32 % | -85 | 49 | -134 | -4.3 | 0 | | no |
| C4 ORB-60, RV >= 10, IHSG > MA20 | selectivity | 18 | 44 % | +39 | 83 | -44 | 0.1 | 80 | | no (n) |
| C5 in play, bought at 10:00 | timing | 721 | 27 % | -87 | 81 | -167 | -9.0 | 0 | | no |
| C6 C1 on IHSG > MA20 days | auctions + regime | 1,316 | 54 % | +48 | 50 | -2 | -0.1 | 100 | | no |
| *ref: every eligible name overnight* | | 66,127 | | +24 | 50 | -26 | | | gross 23:+18 24:+18 25:+32 26:+18 | reference |

## Reading

1. **Lever 1 worked on the gross, as predicted.** Moving the trade into the auctions and overnight lifted the best gross edge from
   +41 (DT-2 B2, continuous) to **+51 bps** (C1), and the pick beats random names on the same days (placebo -25 bps, pct 100).
   It stops at break-even because 50 bps of auction costs remain.
2. **Fee sensitivity for C1 (informative, NOT a re-test - the pre-registered verdict stands):**

   | broker fees | net bps | t | CAGR / Sharpe / mDD (K = 5) | years |
   |---|---|---|---|---|
   | 0.15 / 0.25 % (Stockbit, Ajaib) | +0 | -0.1 | -2 % / 0.03 / -29 % | 2/4 |
   | 0.10 / 0.20 % (Panca Global) | +10 | 1.6 | +16 % / 0.78 / -24 % | 3/4 (2024 +0) |
   | ~0.05 / 0.15 % (levy + PPh only, prop-desk level) | +20 | 3.2 | +36 % / 1.54 / -22 % | 4/4 |

   This is the quantitative form of "why others can day trade": the same signal is worthless at retail fees and a real edge at
   exchange-member cost.
3. **Lever 2 backfired: "in play" names lose.** Yesterday's volume spike + up day -> -85 bps the next session (placebo pct 0,
   every year but 2023). Retail-attention reversal (Akbas et al. 2022) - long-only cannot harvest it; it is a do-not-buy signal.
4. **Lever 3 did not help:** buying the in-play names at 10:00 instead of the open is worse (-167 net), because the spread is paid
   and the names keep fading all day.

**Verdict: 0 of 6.** Do not re-run auction momentum at retail fees. Re-open C1 only if the desk's fee drops to <= 0.10 / 0.20 %
AND it is re-tested pre-registered on data after 2026-09-25 (the ARA/ARB regime changes 2026-09-28). Useful now: the "in play
=> fades next day" fact as an avoid-list for the desk's own entries.
