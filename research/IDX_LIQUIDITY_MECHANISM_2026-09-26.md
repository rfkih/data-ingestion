# Liquidity-provision mechanism behind the gap-fade - 2026-09-26 - 3 trials, cumulative N = 1022

Event: liquid name, adjusted close-to-close <= -7 %; buy that close + 1 tick, sell next close - 1 tick, fees 0.10 / 0.20 %.
3,309 events on 642 days, 2020-01 -> 2026-09. Unit = the day (equal-weight mean of its events). All days: -2.72 % per day.

| hypothesis | group A | mean A | n A | group B | mean B | n B | difference | Welch t | pass |
|---|---|---|---|---|---|---|---|---|---|
| H1 Nagel | high-vol close | -2.47 % | 108 | calm close | -2.78 % | 534 | +0.31 % | 0.49 | False |
| H2 forced sale | 2nd+ loss day | -4.09 % | 241 | first loss day | -2.49 % | 595 | -1.59 % | -2.25 | False |
| H3 2020-24 only | high-vol close | -1.89 % | 3 | calm close | -3.44 % | 305 | +1.55 % | 0.30 | None |
| (context) 2025-26 | high-vol close | -2.48 % | 105 | calm close | -1.89 % | 229 | -0.59 % | -0.83 |  |

| year | days | mean per day | high-vol days | mean high-vol | mean calm |
|---|---|---|---|---|---|
| 2021 | 2 | -8.23 % | 0 | - | -8.23 % |
| 2022 | 2 | -4.30 % | 0 | - | -4.30 % |
| 2023 | 116 | -3.39 % | 0 | - | -3.39 % |
| 2024 | 188 | -3.38 % | 3 | -1.89 % | -3.41 % |
| 2025 | 182 | -1.38 % | 34 | -1.20 % | -1.42 % |
| 2026 | 152 | -2.91 % | 71 | -3.10 % | -2.75 % |

**Verdict: MECHANISM NOT SUPPORTED; H3 UNTESTABLE (too few high-vol days in 2020-24)** (H1 False, H2 False, H3 None).

## The finding this test surfaced: the event depends on the exchange's price-limit regime

The worst daily decline of any name priced above Rp 200, by month (idx.daily_summary close / previous): about -7 % from
2020-04 to 2023-05 (the COVID-era lower auto-rejection limit), -15 % from 2023-06, -25 % from 2023-09, -15 % again from
2025-04. Under the -7 % regime a close <= -7 % - and the gap-fade's open <= -7 % - is mechanically almost impossible:
that, not only the late density of IDX opening prints, is why the gap-fade has almost no trades before 2023-06. The
sleeve exists only while the lower limit is wide. If the exchange narrows it in a future crisis (as in 2020-03), the
gap-fade will not trigger at all.

Reading of H1/H2: a close-to-close loser CONTINUES the next day (all days -2.7 %; a 2nd consecutive loss day -4.1 %,
t -2.25 the wrong way): limit-down cascades run on through the next open. The gap-fade's gain (#382: +6 % in names that
were already crashing) comes AFTER the cascade has gapped the open - an intraday bounce - not from providing liquidity
at the close. The generic liquidity-provision (Nagel) story does not explain it on this market.

Limits: a close-to-close loser is a cousin of the gap-down, not the same event (the gap-fade buys the OPEN); the HMM state
is estimated on 2020-26 parameters (the filter is forward-only, the parameters are not); buying a limit-down close assumes
a fill at the queue, which the desk's size can get.
