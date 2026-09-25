# IDX menu 45: buy the top ARA-tomorrow pick at the open, sell at +20 % / ARA / close (2026-09-26)

7 trials, cumulative N = 982. **Verdict: CLOSED.** Stored as idx.study #200 (`ara_open_tp`).

Operator's rule, tested as stated. Each evening the script takes the name with the highest calibrated p_lock (the #146 model as deployed in `idx/ara_model.py`). It buys that name at the next session's open plus one tick. It sells with a limit at min(+20 %, ARA), and if neither level is reached it sells at that day's close. Fees are 0.15 % to buy and 0.25 % to sell. Each trade uses 10 % of a Rp 20 M sleeve, in lots of 100. If the pick is locked at ARA at the open, the day is skipped (no fallback to the next name).

The pre-registration and code are in `research/idx_ara_open_tp.py`. The machine output is in `IDX_ARA_OPEN_TP_2026-09-26.json`, and the trades are in `tmp/ara_open_tp_trades.pkl`.

## Out-of-sample scores
The scores come from a walk-forward rebuild of #146, because no saved OOF output existed.
- **Training window.** Each test year Y (2022 to 2026) is trained on every row whose label was realised before Y. The last day of Y-1 is purged, because its label falls on Y's first session.
- **Calibration.** Calibration is done the deployed way, with a 250-session holdout inside the training years. The Platt a/b values by year were 0.41/-2.13, 0.69/-3.74, 0.65/-3.95, 0.73/-4.65 and 0.61/-3.84.
- **Ranking accuracy.** The tree AUC by test year was 0.880, 0.886, 0.921, 0.880 and 0.866, which matches #146.
- **Model inputs.** The GRU is refitted per fold, and it is used only for the `ens` neighbour.

## Limit rules (audited against the data)
- **Main-board ARA.** The main-board ARA uses bands of 35 % (price ≤ 200), 25 % (≤ 5,000) and 20 % above that. The price is floored to the tick, using ticks of 1/2/5/10/25 at 200/500/2k/5k.
- **Audit result.** From 2020 to 2026 there are **0** main-board highs above the computed ARA in any year. Between 580 and 2,125 highs per year sit exactly on it. So the formula held in every year, including 2025; the 2020 and 2025 changes were on the ARB side only.
- **Other boards.** The Akselerasi and Pemantauan Khusus boards (10 %) are applied if the name sits there on the entry day. The audit shows breaches on those boards in 2023-2025, because their rules changed over time. None of the traded picks was on those boards at entry, since the universe is main-board only.

## Main arm (the operator's rule)
**Evenings and fills.** There were 1,131 evenings with a pick. On 75 % of them the top pick was already locked at ARA that evening. At the next open:
- 972 picks were bought.
- **95 (8.4 %) were locked at the open** and skipped.
- 63 (5.6 %) had no known open and were skipped.
- 1 had no next session.

So most picks that were locked the evening before still opened below ARA and could be bought.

| sample | n | mean net / trade | t (trade) | t (month-clustered) | take-profit hit | of which at ARA (ARA below +20 %) | win rate |
|---|---|---|---|---|---|---|---|
| all opens 2022-01 to 2026-09 | 972 | **-74 bps** | -1.73 | -1.35 | 32 % | 22 % | 46 % |
| PRIMARY: 2025+ entries on IDX's own open | 316 | **-201 bps** | -2.62 | -1.80 | 36 % | 28 % | 47 % |
| 2025+ entries on a Yahoo open | 1 | -926 bps | n/a | n/a | n/a | n/a | n/a |
| SECONDARY: 2022-2024 (mostly Yahoo opens: 637 of 972 trades are on Yahoo opens, 329 on IDX's, 6 on Stockbit's) | 655 | -11 bps | -0.21 | -0.18 | 29 % | 19 % | 45 % |

**How the trades exit:**
- 213 exit at ARA (mean +11.3 %).
- 94 exit at +20 % (mean +19.8 %).
- 665 exit at the close (mean **-7.5 %**).

The mean gross move from open to close is -1.48 %. The rule has no stop, so only the take-profit matters. Daily bars cannot tell whether the low came before the high, but that does not change this rule's result.

**Picks locked the evening before vs not.** The 702 trades whose pick was locked the evening before averaged -112 bps. The 270 whose pick was not locked averaged +26 bps.

**By year.** Figures are mean net per trade; sleeve figures are CAGR / Sharpe / mDD.

| year | trades | mean net | t | sleeve CAGR | Sharpe | mDD |
|---|---|---|---|---|---|---|
| 2022 | 222 | +149 bps | 1.79 | +36 % | 1.77 | -12 % |
| 2023 | 225 | -55 | -0.65 | -13 % | -0.65 | -22 % |
| 2024 | 208 | -133 | -1.37 | -27 % | -1.48 | -33 % |
| 2025 | 176 | -281 | -2.74 | -41 % | -2.86 | -39 % |
| 2026 YTD | 141 | -107 | -0.93 | -19 % (ann.) | -1.08 | -34 % |

The trade mean is positive in 1 of 5 years (20 %). The whole sleeve returned CAGR -15.8 %, Sharpe -0.82 and mDD -72 %. That comes to about 194 trades a year, with the pick buyable on 86 % of evenings.

## Battery (main arm)
- **Placebo.** In each of 500 draws, one random buyable liquid universe name per traded day, with the same exit and costs, averaged a median of -118 bps (95th percentile -97 bps). The rule's -74 bps is at the **100th percentile**. The model does pick better names than random, but "better than a loser" is still a loser: the base case of buying a random name at the open and selling at the close loses about 1.2 % after the tick and fees.
- **Entry price.** Buying exactly at the open gives **+20 bps (t 0.46)**. Open + 1 tick gives -74 bps (t -1.73), and open + 2 ticks gives -152 bps (t -3.59). The median tick is 0.66 % of price, and 24 % of trades are below Rp 200, so one tick costs about 90 bps. Even the no-slippage case has no edge.
- **Other checks.**
  - Costs x1.5 gives -125 bps (t -2.94).
  - DSR at N = 982 is 0.000.
  - A 1-day delay is not applicable, because the whole trade lives inside one session. There is no 09:05 / first-trade history, so the entry-slippage ladder above stands in for a later entry.
- **Model confidence (p_lock) buckets.**

  | p_lock | trades | mean net |
  |---|---|---|
  | ≤ 3 % | 23 | +63 bps |
  | 3-10 % | 201 | -65 bps |
  | > 10 % | 748 | -80 bps |

  Higher confidence does not help.

## Neighbours
Figures are for all opens, with the primary window in brackets.

| arm | n | mean net | t | take-profit hit | primary n / mean | sleeve CAGR / mDD |
|---|---|---|---|---|---|---|
| fallback to #2 when #1 can't be bought | 1,108 | -68 bps | -1.70 | 32 % | 391 / -202 | -16.6 % / -76 % |
| top-3 equal weight | 3,071 | -123 bps | -5.76 | 22 % | 1,026 / -227 | -24.5 % / -75 % |
| take-profit +10 % | 972 | **+18 bps** | 0.52 | 51 % | 316 / **-91** | +2.3 % / -40 % |
| hold to next open when TP missed | 972 | -109 bps | -2.43 | 32 % | 316 / -195 | -22.4 % / -77 % |
| gate p_lock ≥ 10 % | 748 | -80 bps | -1.58 | 36 % | 253 / -201 | -13.8 % / -69 % |
| ENS rank (the page's order) | 960 | -78 bps | -1.75 | 33 % | 299 / -260 | -16.3 % / -71 % |

The +10 % take-profit is the only arm with a positive mean. That comes from 2022-2023 (+147 and +91 bps); it is negative in 2024, 2025 and 2026 and in the IDX-open window. It is not a candidate.

## Combo effect
The combo NAV is the #192 corrected combo, 2022-01 to 2026-09-16. The sleeve is added as an overlay of 10 % of NAV per trade.

| book | Sharpe | mDD | CAGR |
|---|---|---|---|
| combo alone | 1.80 | -17.9 % | 34.8 % |
| combo + main | 0.62 | -37.6 % | 13.4 % |
| combo + gate10 | 0.76 | -32.5 % | 16.7 % |
| combo + fallback | 0.58 | -39.3 % | 12.4 % |
| combo + top-3 | 0.22 | -41.9 % | 2.5 % |

## Reading rule
The rule was pre-registered. The main arm's checks:

| check | required | result |
|---|---|---|
| mean net per trade | > 0 | **no** (-74 bps) |
| t by trade | ≥ 2.5 | **no** (-1.73) |
| t by month | ≥ 2.5 | **no** (-1.35) |
| years with a positive mean | ≥ 60 % | **no** (20 %) |
| placebo percentile | ≥ 95th | **yes** (100th) |
| combo Sharpe up and mDD not deeper | both | **no** (Sharpe 1.80 → 0.62, mDD -17.9 % → -37.6 %) |
| IDX-open window | ≥ 30 trades with mean > 0 | **no** (316 trades, -201 bps, t -2.62) |

**CLOSED.** The model predicts locks well, but buying its top pick at the next open loses money after one tick and fees. In the IDX-open window it loses about 2 % per trade. The picks that end at ARA pay +11 %, but they are outweighed by the two-thirds that fade to the close at -7.5 %. This agrees with #56 (ARA hunter, 0/24) and #59/#146 ("the buyable picks lose on average"). The ARA freeze stands: no book and no app change.
