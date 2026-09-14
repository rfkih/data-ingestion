# IDX — Macro series on the desk, and whether they help the stress detector (2026-09-14)

**The operator's ask.** Add macro data (the BI rate, GDP growth, and whatever else moves stock prices).

**What was built.** `idx.macro` (migration 0017) and `blackheart_ingest/idx/macro.py`: twelve series pulled daily by the
scheduler from free sources, shown on the desk home page as a board (latest, 1/3/12-month change, two-year sparkline),
served at `/idx/macro`, and readable by the research scripts.

| Series | Source | Frequency | Notes |
|---|---|---|---|
| BI-Rate | Bank Indonesia's decision table (fetched through `curl`; the site resets Python's TLS) + FRED/OECD to 2023-12 | per decision | 5.75 % since 2026-06 |
| USD/IDR | Yahoo `IDR=X` | daily | |
| GDP growth q/q | FRED (OECD) | quarterly | to 2026-Q1 |
| GDP growth annual | World Bank | annual | 2025: 5.1 % |
| CPI | FRED (OECD) | monthly, lags ~17 months | shown as y/y; weak |
| US 10-year yield, Fed funds, VIX, Brent | FRED | daily / monthly | |
| Gold, crude palm oil | Yahoo `GC=F`, `CPO=F` | daily | |

Not available free: the 10-year Indonesian government bond yield (the old IMF API is gone, the new one needs dataset
mapping, investing.com blocks). It is the gap.

**Verdict on the detector.** No macro signal, alone or combined, improves the cash-buffer detector over the price-and-
breadth version. Macro signals fire rarely (8–15 % of months) and mostly after the market has already moved, so as
30 → 50 % triggers they leave the drawdown where a constant 30 % buffer leaves it (18 % on the strict book, 41 % on the
2008 basket, 2020 −35 %). Adding the five macro signals to the four price signals (any two of nine) matches the price
detector's drawdown (14 % / 34 %) with a point less return. The BI-rate hike is the best single macro input (it was on
before 2008: −28 %) and useless in 2020 (BI was cutting: −35 %). The macro board is for reading; the detector stays
price and breadth.

## Pre-registered menu (7 trials; cumulative 169)

Same set-up as IDX_CASH_BUFFER: 0.70 exposure normally, 0.50 while the signal is on, monthly checks, strict book
2021–2026 (four calendars) and the 100-name basket 2008–2026. Signals from data up to the check day; GDP and CPI
excluded (publication lag, point-in-time dates unknown). Script `research/idx_macro_stress.py`; outputs
`research-scratch/idx-screen/macro_stress_out.txt`, `macro_stress_results.json`.

| Signal | Definition | On-time, strict book |
|---|---|---|
| idr_3m | USD/IDR up more than 5 % over three months | 8–10 % |
| vix_hi | VIX above 25 | 12–15 % |
| us10y_3m | US 10-year yield up more than 0.75 points over three months | 9–11 % |
| bi_hike | BI rate above its level six months earlier | 31–35 % |
| brent_3m | Brent down more than 20 % over three months | 7–8 % |
| macro_any2 | two of the five | 12–15 % |
| all_any2 | two of the nine (four price, five macro) | 61–68 % |

Reading rule, written before the run: a macro arm earns a place only if it passes the cash-buffer rule and beats the
price-only any2 arm's 2008-basket drawdown by at least 3 points.

## Results (strict book avg CAGR · worst mDD; 2008 basket CAGR · mDD · 2008 / 2020 episodes)

| Arm | strict avg CAGR | Sharpe wins | worst mDD | basket CAGR | basket mDD | 2008 / 2020 |
|---|---|---|---|---|---|---|
| full | 18.3 | | 26 % | 10.2 | 56 % | −48 / −47 |
| cash30 | 14.2 | 4/4 | 18 % | 8.9 | 41 % | −37 / −35 |
| ma (price) | 13.4 | 4/4 | 15 % | 9.1 | 32 % | −28 / −28 |
| any2 (price) | 12.9 | 4/4 | 15 % | 8.8 | 32 % | −28 / −28 |
| idr_3m | 14.1 | 4/4 | 18 % | 8.4 | 41 % | −36 / −35 |
| vix_hi | 12.4 | 4/4 | 18 % | 7.7 | 36 % | −32 / −29 |
| us10y_3m | 14.4 | 4/4 | 18 % | 9.1 | 41 % | −37 / −35 |
| bi_hike | 13.7 | 4/4 | 18 % | 9.8 | 40 % | −28 / −35 |
| brent_3m | 13.1 | 4/4 | 18 % | 8.6 | 43 % | −32 / −35 |
| macro_any2 | 13.8 | 4/4 | 18 % | 8.3 | 43 % | −32 / −35 |
| all_any2 | 12.8 | 4/4 | 14 % | 8.6 | 34 % | −28 / −28 |

None passes; none beats the price detector's basket drawdown.

## Reading

1. **Macro is slow and the market is fast.** The rupiah, the VIX and yields move with the crash, not before it; by the
   monthly check that catches them, the index is already under its average, which the price detector already sees.
2. **The BI rate is the one leading input**, and only for the kind of crash that follows tightening (2008). It said
   nothing about 2020, when the shock came from outside and BI was easing.
3. **What the board is for.** Context for the operator (a weakening rupiah and a rising BI rate are pressure on the
   banks and consumer names the list holds; rising Brent and CPO are support for the energy and plantation names), and
   an input for the next research question, not a trigger.

## What changed

- `idx.macro` + `macro.py` (catalog, fetchers, `pull`, `board`), scheduler job `macro` (07:30 WIB, Mon–Sat), CLI
  `idx macro pull|show`, API `/idx/macro` and `/idx/macro/pull`, Papan macro board on the desk home page. Trials: 169.
- The stress detector is unchanged (price and breadth).
