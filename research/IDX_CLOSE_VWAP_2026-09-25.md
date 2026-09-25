# IDX menu NS-1 - close vs VWAP: buy the close dumped below the day's VWAP - 2026-09-25 - 2 trials, cumulative N = 865

Universe: 60-day value >= Rp 5 bn, close >= Rp 100, day value >= Rp 1 bn; 2020-01-02 -> 2026-09-24. K = 5, dev <= -3%, round-trip cost 0.50% (auction fills, no spread; 0.10 % impact each side).

## Deciles of close / VWAP - 1 (universe name-days)

| decile | n | mean dev | next open | next close | 5 days |
|---|---|---|---|---|---|
| 1 | 26,002 | -3.19% | +0.15% | -0.23% | -0.43% |
| 2 | 26,002 | -1.34% | +0.31% | +0.06% | +0.13% |
| 3 | 26,002 | -0.82% | +0.29% | +0.08% | +0.11% |
| 4 | 26,002 | -0.50% | +0.26% | +0.09% | +0.17% |
| 5 | 26,002 | -0.25% | +0.24% | +0.03% | +0.07% |
| 6 | 26,002 | -0.02% | +0.13% | -0.00% | -0.09% |
| 7 | 26,002 | +0.22% | +0.17% | +0.03% | +0.04% |
| 8 | 26,002 | +0.54% | +0.18% | +0.03% | +0.03% |
| 9 | 26,002 | +1.04% | +0.20% | -0.04% | +0.06% |
| 10 | 26,002 | +3.03% | +0.50% | -0.06% | +0.25% |

Rank IC of dev with next-open -0.040, next-close -0.022, 5-day -0.001 (negative = reversal).
Events with dev <= -3% at/near the lower auto-rejection band vs not: {"at_lower_band": {"n": 2247, "ro": -0.0218, "rc": -0.0177}, "not": {"n": 7310, "ro": 0.005, "rc": -0.0004}}

## Books (net of costs)

| arm | CAGR | Sharpe | t | mDD | days active | avg / active day | win | H1 | H2 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| VW_O | -24.1% | -1.74 | -4.4 | -86% | 542 | -0.31% | 42% | -18% | -80% | -10% | +2% | -7% | -2% | -10% | -49% | -57% |
| VW_C | -90.0% | -4.81 | -12.2 | -100% | 1500 | -0.94% | 32% | -100% | -100% | -60% | -89% | -96% | -93% | -90% | -76% | -88% |
| REV_O | -59.9% | -4.58 | -11.7 | -100% | 1260 | -0.46% | 27% | -81% | -99% | -25% | -41% | -48% | -33% | -26% | -76% | -90% |
| REV_C | -69.9% | -2.96 | -7.5 | -100% | 1261 | -0.58% | 38% | -91% | -100% | -32% | -53% | -58% | -38% | -44% | -85% | -94% |
| VW_O_cost1.5 | -34.1% | -2.60 | -6.6 | -94% | 542 | -0.48% | 32% | -22% | -91% | -11% | +0% | -8% | -4% | -14% | -67% | -70% |
| VW_C_cost1.5 | -93.6% | -5.74 | -14.6 | -100% | 1500 | -1.13% | 29% | -100% | -100% | -68% | -93% | -98% | -96% | -93% | -85% | -92% |
| VW_O_K3 | -36.1% | -1.91 | -4.9 | -96% | 542 | -0.50% | 43% | -24% | -93% | -13% | +5% | -11% | -3% | -14% | -69% | -74% |
| VW_O_K10 | -17.3% | -1.82 | -4.6 | -73% | 542 | -0.22% | 41% | -10% | -67% | -6% | +1% | -4% | -1% | -5% | -28% | -53% |
| VW_O_thr2 | -28.5% | -2.01 | -5.1 | -90% | 847 | -0.25% | 40% | -42% | -80% | -12% | -12% | -20% | -10% | -10% | -51% | -53% |
| VW_O_thr5 | -21.8% | -1.92 | -4.9 | -83% | 354 | -0.44% | 39% | -1% | -79% | -1% | +0% | +0% | +2% | -7% | -42% | -63% |
| VW_C_K3 | -96.3% | -5.14 | -13.1 | -100% | 1500 | -1.33% | 32% | -100% | -100% | -67% | -93% | -99% | -98% | -98% | -93% | -92% |
| VW_C_K10 | -75.8% | -4.25 | -10.8 | -100% | 1500 | -0.59% | 32% | -99% | -99% | -40% | -82% | -86% | -78% | -70% | -53% | -79% |
| VW_C_thr2 | -93.0% | -5.09 | -13.0 | -100% | 1572 | -1.04% | 33% | -100% | -100% | -77% | -90% | -97% | -97% | -94% | -76% | -91% |
| VW_C_thr5 | -76.4% | -4.04 | -10.3 | -100% | 1107 | -0.81% | 32% | -98% | -100% | -33% | -75% | -83% | -80% | -78% | -68% | -78% |
| RAND_O | -49.7% | -5.47 | -13.9 | -99% | 1466 | -0.30% | 26% | -88% | -90% | -21% | -50% | -61% | -55% | -57% | -22% | -48% |
| RAND_C | -70.2% | -3.42 | -8.7 | -100% | 1580 | -0.47% | 36% | -98% | -98% | -58% | -72% | -75% | -75% | -64% | -57% | -67% |

## Verdict (pre-registered)

- **VW_O**: sharpe_t no, years no, halves no, cost1.5 no, beats_rev yes, beats_rand yes, neighbours no -> **not a candidate**
- **VW_C**: sharpe_t no, years no, halves no, cost1.5 no, beats_rev no, beats_rand no, neighbours no -> **not a candidate**

Deflated Sharpe at N = 865: {'VW_O': 6.587470315285555e-15, 'VW_C': 3.8832486650581066e-47}. Capacity: median day value of the picks Rp 26.0 bn (10th pct Rp 4.5 bn).

## Reading (written after the run)

**Not a strategy - and the hypothesis was backwards.** A close dumped below VWAP does NOT come back: the bottom decile
(close 3.2 % under VWAP) loses a further -0.23 % the next day and -0.43 % over five; the dump carries information, it is not
liquidity. What looks like a bounce is the market-wide overnight premium: every decile opens higher (+0.13..+0.50 %) and
gives it back by the close (close-to-close ~0), so buying any name at the close and selling at the open earns ~+0.2 % gross
against a 0.5 % round trip - RAND_O loses -50 %/yr. The one asymmetry: closes marked UP (top decile, +3 % over VWAP) open
+0.50 % higher and fade to -0.06 % by the close - consistent with close-marking, and usable only as an EXIT-timing rule for
names already held (sell such a name at the next open, not the next close), never as an entry.
Lesson for the next search: a one-day holding period cannot carry a 0.5 % round trip on IDX; a new strategy needs a
multi-week horizon or large event moves.
