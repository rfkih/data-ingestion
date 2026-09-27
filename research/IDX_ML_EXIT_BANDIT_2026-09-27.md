# ML sleeve: a learned exit policy (contextual bandit, walk-forward) - 2026-09-27 - 2 trials, cumulative N = 1027

718 ML rule-trades (ens4, #386 engine) with their natural exit; out of sample 2023-02-09 -> 2026-08-13: 509 trades,
each scored by a policy trained only on trades that had already closed (monthly refit). Benchmark = the deployed same-close stop -5 %.

Out-of-sample mean net per trade by arm (every trade under every exit):

| none | stop5 | stop10 | trail10 | trail20 |
|---|---|---|---|---|
| +10.16 % | +7.33 % | +8.95 % | +7.55 % | +8.65 % |

| policy | mean net | stop -5 % | difference | paired t | 1st half | 2nd half | 1st pct vs stop | arms chosen | pass |
|---|---|---|---|---|---|---|---|---|---|
| P1 contextual (LightGBM per arm) | +7.43 % | +7.33 % | +0.10 % | 0.14 | +1.17 % | -0.95 % | -46.36 % vs -15.64 % | stop5 34 %, none 26 %, trail10 20 %, stop10 11 %, trail20 9 % | no |
| P2 best arm so far | +8.29 % | +7.33 % | +0.96 % | 1.10 | -0.62 % | +2.52 % | -46.36 % vs -15.64 % | none 65 %, stop5 17 %, trail20 15 %, stop10 2 % | no |

**Verdict: CLOSED: no learned exit beats the fixed stop -5 % out of sample**

Limits: trade level (a slot freed early is not re-used, which understates every early exit a little and the same way for all
arms); the natural exit comes from the no-stop book; same-close execution for every arm (the deployed stop runs 15:40-15:50);
2022-26 only, the same regime caveats as every IDX study.
