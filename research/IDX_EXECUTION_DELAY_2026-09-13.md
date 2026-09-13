# IDX — The cost of executing late (2026-09-13)

**Why.** The desk does not auto-trade. A signal is computed at the close of the monthly check day, the operator is
notified, and the order is worked the next session or later. Every backtest so far traded at the signal close. This
measures what the delay costs the rules the operator has chosen, on the strict book 2021–2026, four calendars, with the
signal fixed at day 0 and the trade moved to the close of day k (k = 1, 2, 5 trading days). Script
`research/idx_execution_delay.py`; outputs `research-scratch/idx-screen/execution_delay_out.txt`, `execution_delay_results.json`.

## Average across the four calendars (CAGR; worst-calendar drawdown)

| Rule | Same day | 1 session late | 2 sessions | 5 sessions |
|---|---|---|---|---|
| strict, hold to the rebalance | 17.9 % · 22 % | 18.0 % (+0.1) · 23 % | 17.9 % (0.0) · 23 % | 18.1 % (+0.2) · 24 % |
| regime filter (MA200 on the IHSG) | 14.4 % · 22 % | 14.5 % (+0.1) · 22 % | 13.8 % (−0.7) · 20 % | 13.2 % (−1.2) · 23 % |
| asymmetric per-name rule | 15.6 % · 17 % | 14.3 % (−1.3) · 18 % | 13.9 % (−1.7) · 18 % | 12.9 % (−2.7) · 20 % |
| regime filter + asymmetric | 10.8 % · 14 % | 10.4 % (−0.4) · 14 % | 10.2 % (−0.6) · 14 % | 9.4 % (−1.4) · 14 % |

Per calendar, one session late (CAGR · Sharpe · max drawdown):

| Rule | May | Feb | Aug | Nov |
|---|---|---|---|---|
| strict, hold to the rebalance | 18.5 · 1.02 · 23 % | 24.0 · 1.41 · 21 % | 15.6 · 0.89 · 20 % | 13.8 · 0.86 · 21 % |
| regime filter | 14.4 · 0.98 · 22 % | 15.3 · 1.18 · 18 % | 15.8 · 1.10 · 15 % | 12.6 · 0.98 · 19 % |
| asymmetric | 17.1 · 1.21 · 16 % | 16.2 · 1.20 · 18 % | 13.0 · 0.92 · 16 % | 11.1 · 0.87 · 14 % |
| regime + asymmetric | 12.0 · 1.05 · 11 % | 9.8 · 1.01 · 12 % | 11.5 · 0.97 · 14 % | 8.3 · 0.87 · 11 % |

## Reading

1. **The annual rebalance does not care.** Working the May ticket a day or a week late changes nothing measurable; the
   list is the signal, not the day.
2. **The regime filter tolerates a session.** One session late costs nothing; five sessions cost about a point. The
   index crosses its average slowly.
3. **The asymmetric rule is the delay-sensitive one**: 1.3 points of CAGR a session late, 2.7 points five sessions late.
   Oversold entries and trend-break exits are timing signals; the first day after the cross carries part of the move.
   Executed the next session it keeps its drawdown edge (worst 18 % against 23 %) but its Sharpe advantage over the plain
   rule narrows to two calendars of four. Executed a week late it is no better than the regime filter on return.
4. **The stack the operator chose (regime + asymmetric), worked the next session: about 10.4 % a year with a 14 %
   worst drawdown**, against 18 % and 23 % for the plain rule. That is the honest number to plan on: the smoothest path
   the desk can produce, at roughly six points of return a year.

## What the desk does with this

- Tickets from the monthly check carry limit prices one tick through the check close and are meant to be worked at
  the next open; the alert text says so. Working them within the session keeps the cost near the 1-session column.
- The catalog note for the asymmetric option quotes the 1-session and 5-session costs, so the app shows the number a
  notification-driven operator will actually get, not the same-day backtest.
