# IDX menu RL-1 - a reinforcement-learning capital allocator over the four tested strategies - 2026-09-26 - 1 trial, cumulative N = 961

Streams (engine #168, costs): gap / trend / ML alone + value book; weekly allocation among 7 templates; reward = log return - 2.0 x drawdown increase - 0.3% x turnover; REINFORCE MLP, 3000 episodes of 26 weeks, 5 seeds; walk-forward test 2024-2026 stitched (2024-01-02 -> 2026-09-16).

Daily return correlation of the streams: {"gap": {"gap": 1.0, "trend": 0.02, "ML": 0.23, "value": 0.09}, "trend": {"gap": 0.02, "trend": 1.0, "ML": 0.17, "value": 0.2}, "ML": {"gap": 0.23, "trend": 0.17, "ML": 1.0, "value": 0.28}, "value": {"gap": 0.09, "trend": 0.2, "ML": 0.28, "value": 1.0}}

| allocator | CAGR | Sharpe | mDD | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|
| FIXED_EQ | +40.1% | 2.38 | -12% | +12% | +70% | +24% |
| REGIME | +30.1% | 2.22 | -12% | +11% | +52% | +16% |
| WF_BEST | +42.5% | 1.97 | -17% | +20% | +73% | +19% |
| RL seed 1 | +21.5% | 1.50 | -13% | +9% | +38% | +9% |
| RL seed 2 | +20.6% | 1.55 | -14% | +5% | +38% | +12% |
| RL seed 3 | +20.7% | 1.45 | -14% | +3% | +35% | +16% |
| RL seed 4 | +16.9% | 1.56 | -11% | +13% | +23% | +7% |
| RL seed 5 | +14.2% | 1.22 | -12% | +4% | +30% | +4% |
| **RL mean** | +18.8% | 1.46 (range 1.22..1.56) | -13% | |

RANDOM placebo (200 draws): Sharpe median 1.52, 95th pct 2.05. WF_BEST picks: {2024: 'ML', 2025: 'ML', 2026: 'ML'}.

Actions taken in test (weeks, per seed): {"EQ": 5, "TREND": 53, "ML": 19, "GAP": 5, "VALUE": 17, "DEF": 16, "OFF": 25}; {"EQ": 7, "TREND": 37, "ML": 17, "GAP": 29, "VALUE": 12, "DEF": 1, "OFF": 37}; {"EQ": 15, "TREND": 24, "ML": 10, "GAP": 11, "VALUE": 19, "DEF": 31, "OFF": 30}; {"EQ": 1, "TREND": 29, "ML": 15, "GAP": 7, "VALUE": 15, "DEF": 8, "OFF": 65}; {"EQ": 13, "TREND": 47, "ML": 7, "GAP": 17, "VALUE": 18, "DEF": 11, "OFF": 27}

## Verdict (pre-registered)

Best baseline: FIXED_EQ. Checks: sharpe no, cagr no, mdd yes, seeds no, random no -> **NOT better - the agent is not given capital**
