# IDX menu RL-1 - a reinforcement-learning capital allocator over the four tested strategies - 2026-09-26 - 1 trial, cumulative N = 961

Streams (engine #168, costs): gap / trend / ML alone + value book; weekly allocation among 7 templates; reward = log return - 2.0 x drawdown increase - 0.3% x turnover; REINFORCE MLP, 3000 episodes of 26 weeks, 5 seeds; walk-forward test 2024-2026 stitched (2024-01-02 -> 2026-09-16).

Daily return correlation of the streams: {"gap": {"gap": 1.0, "trend": 0.02, "ML": 0.13, "value": 0.09}, "trend": {"gap": 0.02, "trend": 1.0, "ML": 0.26, "value": 0.2}, "ML": {"gap": 0.13, "trend": 0.26, "ML": 1.0, "value": 0.32}, "value": {"gap": 0.09, "trend": 0.2, "ML": 0.32, "value": 1.0}}

| allocator | CAGR | Sharpe | mDD | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|
| FIXED_EQ | +41.1% | 2.44 | -13% | +13% | +77% | +21% |
| REGIME | +31.6% | 2.36 | -10% | +12% | +56% | +15% |
| WF_BEST | +53.1% | 2.41 | -12% | +13% | +88% | +40% |
| RL seed 1 | +19.9% | 1.42 | -14% | +10% | +29% | +12% |
| RL seed 2 | +16.0% | 1.21 | -22% | +3% | +28% | +10% |
| RL seed 3 | +17.6% | 1.30 | -12% | +3% | +28% | +14% |
| RL seed 4 | +15.4% | 1.19 | -13% | +8% | +25% | +7% |
| RL seed 5 | +13.2% | 1.13 | -14% | +4% | +29% | +2% |
| **RL mean** | +16.4% | 1.25 (range 1.13..1.42) | -15% | |

RANDOM placebo (200 draws): Sharpe median 1.58, 95th pct 2.13. WF_BEST picks: {2024: 'VALUE', 2025: 'ML', 2026: 'GAP'}.

Actions taken in test (weeks, per seed): {"EQ": 3, "TREND": 49, "ML": 13, "GAP": 10, "VALUE": 7, "DEF": 7, "OFF": 51}; {"EQ": 16, "TREND": 27, "ML": 16, "GAP": 7, "VALUE": 12, "DEF": 10, "OFF": 52}; {"EQ": 23, "TREND": 12, "ML": 7, "GAP": 13, "VALUE": 13, "DEF": 22, "OFF": 50}; {"EQ": 4, "TREND": 40, "ML": 14, "GAP": 5, "VALUE": 17, "DEF": 3, "OFF": 57}; {"EQ": 2, "TREND": 66, "ML": 5, "GAP": 7, "VALUE": 9, "DEF": 0, "OFF": 51}

## Verdict (pre-registered)

Best baseline: FIXED_EQ. Checks: sharpe no, cagr no, mdd no, seeds no, random no -> **NOT better - the agent is not given capital**
