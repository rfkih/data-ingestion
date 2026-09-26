# IDX menu 49 rev.2 - rights (HMETD) exercise arbitrage - 2026-09-26 - 6 trials, cumulative N = 1019

rev.2: the first run (+16.7 %/issue) ignored T+2 settlement, exercise deadlines and limit-down exits and double counted one
issue; it is superseded, not reported. Exit = stock session d + 2 (settle, exercise) + D, rolled past locked closes.

Issues with terms and bars: 80 (291 right trading days). Unit = the issue (mean over its signalled days).
Buy the right at the close + 1 tick, exercise, sell the new share D sessions after exercise (d + 2) - 1 tick; fees 0.15 / 0.25 %.

| arm | thr | D | issues | days | mean | median | t | positive | w/o top 5 % | 2020-22 n / mean | 2023-26 n / mean | exits rolled past a lock | median discount |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A1_main | 5 % | 2 | 17 | 25 | +12.75 % | +8.65 % | 2.21 | 71 % | +8.60 % | 14 / +10.80 % | 3 / +21.85 % | 28 % | 22.6 % |
| A2_thr2 | 2 % | 2 | 21 | 33 | +11.36 % | +6.36 % | 2.37 | 67 % | +5.67 % | 18 / +9.61 % | 3 / +21.85 % | 24 % | 11.2 % |
| A3_thr10 | 10 % | 2 | 10 | 17 | +19.00 % | +10.37 % | 2.13 | 80 % | +12.32 % | 7 / +17.54 % | 3 / +22.39 % | 29 % | 26.5 % |
| A4_D1 | 5 % | 1 | 17 | 25 | +13.54 % | +8.65 % | 2.54 | 71 % | +10.40 % | 14 / +12.91 % | 3 / +16.49 % | 32 % | 22.6 % |
| A5_D3 | 5 % | 3 | 17 | 24 | +10.85 % | +7.48 % | 1.84 | 65 % | +6.12 % | 14 / +7.88 % | 3 / +24.69 % | 29 % | 21.0 % |
| A6_all | - | 2 | 54 | 138 | -3.55 % | -2.58 % | -1.19 | 30 % | -6.90 % | 47 / -5.06 % | 7 / +6.55 % | 7 % | -0.1 % |
| A1_costs15 | 5 % | 2 | 17 | 25 | +12.16 % | +8.32 % | 2.12 | 71 % | +8.04 % | 14 / +10.26 % | 3 / +21.01 % | 28 % | 22.6 % |

MAIN checks: {'mean_t2': True, 'pos55': True, 'halves': True, 'costs15': True, 'wo_top5': True}; neighbours with mean > 0: 4/4.
Post-read diagnostic: MAIN without its two best issues = mean +5.73 %, t 1.70.
**Verdict: ROBUST by the letter, FRAGILE in substance (without its two best issues t 1.70)**

Reading: the two best issues are PACK 2025-12 (the stock ran limit-up for days - the gain is the rally, not the discount)
and BEKS 2020-12 (the right at Rp 1-2 against K 50 and a stock at 120, sold after a limit-down streak). Qualifying issues
are rare (17 in 2020-26, 3 since 2023) and 28 % of exits hit a locked close. Not a sleeve; at most a forward paper watch.

Limits: rights priced at the CLOSE (thin books; the close may not be buyable); settlement T+2 and delivery D are
assumptions (D 1..3); exercise assumed possible until the right's last trading day; exercise fees beyond the broker fee
are ignored; the lock rule is a proxy (no order-book depth); terms come from IDX's yearly table, which lags the current year.
