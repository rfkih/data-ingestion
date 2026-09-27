# IDX menu DT-2 — day trading rules from the literature, on IDX intraday bars — 2026-09-27 — study #397

Operator: "cari di internet cara day trade / scalping, dapatkan ilmunya, implement di data day trading kita".
Script `research/idx_daytrade2.py` (pre-registered in its docstring); data `research-scratch/idx/daytrade2/` (Yahoo .JK intraday).
**15 trials counted (11 + 4 void re-specified); cumulative N 1042 -> 1057. Result: 0 of 15.**

## Data (verified before use)

| sample | bars | sessions | names | check against the desk's own data |
|---|---|---|---|---|
| A | 5-minute | 58 (2026-07-06 .. 09-25) | 194 | closes = tick feed on 99.2 % of 30,148 overlapping bars; 16:00 bar = closing auction (= daily_summary.close 99.8 %) |
| B | 1-hour | 713 (2023-09-13 .. 2026-09-25) | 189 | = 5-minute aggregate on 100 % of 73,300 bars |

**Defect found:** Yahoo leaves the FIRST bar's volume empty (09:00 5-min 98 %, 09:00 hour 80 %). The first run's relative-volume
filter was therefore void (ORB-5 made 6 trades). A reconstruction from daily totals matched the feed at Spearman 0.59 only and was
rejected; RV was re-specified to data known at decision time (09:05 bar; yesterday's daily volume for sample B) and the void runs
were counted as trials.

## What the literature says (web sweep, 2026-09-27)

| technique | source | published result | grade |
|---|---|---|---|
| ORB on "stocks in play" (5-min range, RV top 20, EOD exit) | Zarattini, Barbon, Aziz 2024 (SSRN 4729284) | Sharpe 2.81, commission only, no slippage; without RV Sharpe 0.48; 15/30/60-min ranges 1.43/0.21/0.40 | weak-moderate, in-sample |
| market intraday momentum (first half-hour -> last half-hour) | Gao, Han, Li, Zhou 2018 JFE; Baltussen et al. 2021; IDX: Hamidi et al. 2024 | exists (strong), ~2.7 bps/trade on SPY before costs | effect strong, tradability weak |
| noise-area momentum + VWAP trail | Zarattini, Aziz, Barbon 2024 (SSRN 4824172) | SPY Sharpe 1.33 net of SPY-level costs | weak-moderate |
| VWAP trend | Zarattini & Aziz 2023 | ~15 trades/day, < 1 bp each; replication worse | weak |
| overnight-intraday reversal / gap fade | Lou, Polk, Skouras 2019; Akbas et al. 2022 | strong in retail-attention names | moderate |
| order-flow imbalance scalping | Cont, Kukanov, Stoikov 2014 | move < 1 tick; only a maker edge | not tradable by a taker |
| retail day traders | Barber et al. (Taiwan, price limits); Chague et al. (Brazil) | < 1 % predictably profitable; 97 % of persistent traders lose | strong |

## Results (net of fees 0.15 % + 0.25 %, half the quoted spread on continuous fills, closing auction fees only)

| arm | trades | hit | gross bps | cost bps | **net bps** | t (daily) | placebo pct | by year (net bps) | verdict |
|---|---|---|---|---|---|---|---|---|---|
| A1 ORB 5-min, RV >= 1 | 186 | 33 % | -11 | 84 | **-94** | -3.1 | 62 | | no |
| A2 ORB 5-min, RV >= 5 | 109 | 32 % | +8 | 84 | **-75** | -2.3 | 74 | | no |
| A3 ORB 15-min, RV >= 1 | 141 | 33 % | -8 | 81 | **-89** | -3.0 | 68 | | no |
| A4 noise area + VWAP trail | 506 | 20 % | -2 | 83 | **-85** | -9.2 | 100 | | no |
| A5 first half-hour -> last half-hour | 279 | 32 % | +33 | 79 | **-46** | -3.8 | 100 | | no |
| A6 gap <= -3 % + green first bar | 29 | 38 % | -22 | 91 | **-112** | -0.6 | 77 | | no |
| A7 VWAP pullback (practitioner) | 191 | 21 % | -14 | 106 | **-120** | -3.7 | 38 | | no |
| B1 ORB 60-min, RV >= 1 | 1,622 | 33 % | +16 | 76 | **-60** | -6.3 | 100 | 23:-76 24:-79 25:-40 26:-51 | no |
| B2 ORB 60-min, RV >= 5 | 159 | 44 % | +41 | 77 | **-36** | -1.2 | 100 | 23:-96 24:-40 25:-15 26:-34 | no |
| B3 first hour -> last hour | 3,418 | 31 % | +28 | 77 | **-49** | -10.7 | 100 | 23:-66 24:-70 25:-39 26:-26 | no |
| B4 gap <= -3 % + green first hour | 340 | 36 % | -0 | 84 | **-85** | -2.1 | 66 | 23:-118 24:-139 25:-112 26:-57 | no |
| *ref: gap <= -3 %, buy open auction, sell close* | 557 | 56 % | +156 | 41 | **+115** | 2.9 | - | 23:-218 24:-62 25:+136 26:+142 | reference |

## Reading

1. **The costs decide it, not the signal.** Five rules pick better than random (placebo pct 100: A4, A5, B1, B2, B3) - the
   literature's effects are real on IDX. But the best gross edge is +41 bps a trade and **the broker fee alone is 40 bps**;
   with a zero spread every rule would still be at or below zero. The published papers charge US commissions of ~1 bp.
2. **The IDX clock pays the wrong way for a day trader** (sample B, 85k name-days, equal weight): overnight +28 bps (t 42),
   09:00 hour -18 bps (t -22), 13:30 re-open -6, 14:00 -4, 11:00 +8, 15:00 +7. A long-only day trade that buys after the open
   gives up the overnight gain and eats the morning sell-off. Same fact as menu 29 (intraday -17 bps/day 2020-26).
3. **Waiting for confirmation destroys the one real edge.** The gap-down fade bought at the opening auction (no spread) earns
   +115 bps (t 2.9, positive only 2025-26 - the regime the live gap-fade sleeve already trades); waiting for a green first bar
   / hour (A6, B4) turns it into -85..-112 bps. The reversal happens in the first minutes; a confirmation pays the spread
   and buys after the bounce.
4. Stops at the opening-range low: 27 % of ORB-5 trades were stopped (ticks of 0.5-2.5 % make tight stops noisy).

**Verdict: 0 of 15. No day-trading / scalping book.** The literature's rules are real but sub-cost on IDX retail fees. Do not
re-run ORB / VWAP / noise-area / intraday momentum / confirmation-gap variants. What remains usable: the hour profile as
execution timing for trades the desk makes anyway (buy in the 09:00-10:00 weakness, not at 11:00 or 15:00), and the existing
opening-auction gap-fade sleeve. Caveat: ARA/ARB rules change from 2026-09-28 (min price Rp 1, ARB 15 % flat, ARA 35/25/20 %);
the samples predate it.
