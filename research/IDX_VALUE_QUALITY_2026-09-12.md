# IDX Phase 2 — Value + Quality, One-Year Holds, Point-in-Time (2026-09-12, rev. 3)

**Verdict: cheap-and-profitable IDX names, held equal-weight for a year, beat the market at every rebalance date tested,
and the size of the edge is now measured on a real portfolio path over the full point-in-time universe. The deployed rule
(loose gate → composite rank → top fifth, "composite_qloose") returned +106 % from May 2021 to September 2026 (CAGR 14.5 %,
Sharpe 0.83, max drawdown 22 %, five of six rebalance years positive) against +47 % for the equal-weight liquid universe with
the same costs and dividends, +10 % for the COMPOSITE, 0 % for the IDX Value 30 and −27 % for LQ45. Moved to February, August
or November, the same rule makes 10.6–17.7 %/yr with a 21–23 % drawdown and stays 8–13 points/yr ahead of the bench. The
strict-gate composite ("composite_q") now does better than the loose one in all four calendars (+146 %, CAGR 18.3 %, Sharpe
0.98, drawdown 22 % at May); rev. 2's reading that a strict gate hurts is withdrawn — it was an artifact of three defects
fixed in this revision. Pure earnings yield ("value_qloose") earns the most (+323 %) but is concentrated, calendar-fragile
and holds Sritex to zero. Nothing here is certifiable: DSR 0.56 (loose) / 0.69 (strict) at N = 13 against the 0.90 bar.
This is evidence-supported discretion, sized as such, and one year (2021) is largely one name (SRTG).**

> **Revision 3 (same day, night).** Rev. 2's numbers came from a backtest with defects found in the review
> (`research/IDX_REVIEW_2026-09-12.md`), all fixed here: (1) the universe was built from *today's* board membership, so names
> later moved to Pemantauan Khusus or delisted (Sritex, Waskita, …) were never eligible — the board is now read per day from the
> IDX notation string in the day-dump and 305 missing audited reports were downloaded (515 filers, was 451); (2) the research
> script re-implemented the rule in pandas without the data-error guard and with a different tie-break and pool rule — it now
> calls the production `candidates.build()`/`rank_pool()`; (3) the "two years of profit" test never fired (the YoY ratio cannot
> be inverted for turnarounds) — comparatives are now stored as reported; (4) ~80 reports had a mis-scaled EPS and PGEO's every
> report was 1000× too big — an EPS × shares check with the publication-day price now repairs both (394 EPS rows, 6 reports);
> (5) market cap multiplied the split-adjusted close by the day's unadjusted share count, making names that later split look up
> to 10× cheaper (PTRO ranked #1 in May 2024 on that; it is #43 now); (6) the P&L path was the daily mean of log returns across
> names — the geometric mean, which understates an equal-weight buy-and-hold book by half the cross-sectional variance, on IDX
> roughly 10 points a year — it is now a real path: units bought at the close, held, dividends net of the 10 % final tax to
> cash, 25 bps a side plus half the tick, names with no trade on the rebalance day carried, delisted names worth zero;
> (7) dividends before a split were counted at a fifth and turnover was charged twice. Every number below is from the corrected
> run; rev. 2's script and output are kept as `research-scratch/idx-screen/idx_value_quality_rev2.py` /
> `value_quality_out_rev2.txt`. The biggest single mover is (6): every equal-weight number rose, the bench from −28 % to +47 %.

Script `research/idx_value_quality.py` (`--months 5,2,8,11`); output `research-scratch/idx-screen/value_quality_out.txt`,
JSON `value_quality_results.json` (full holdings, per-name contributions, per-month results). READ-ONLY on the local DB.

## Data (all primary, all point-in-time)

| Layer | Source | Coverage |
|---|---|---|
| Universe | day-dump `idx.daily_summary`: board digit of the notation string (1 Utama, 2 Pengembangan, 3 Akselerasi, 4 Pemantauan Khusus, 5 Ekonomi Baru), traded that day, 60-day median value ≥ Rp 5 bn | 145 / 167 / 122 / 127 / 129 / 186 eligible names at the six May rebalances |
| Financial statements | IDX standardized workbooks (`idx/fin_parse.py`, `fin_store.py`): 2,615 audited FY2020–FY2025 rows for 515 filers, 0 failures; USD filers at the reporting-date rate; label/neighbour/EPS scale checks; prior-period comparatives as reported | 105 / 142 / 119 / 116 / 115 / 167 names with a usable audited report (< 16 months) on the day |
| Publication time | IDX `File_Modified`; a report counts once published by 16:00 WIB of the rebalance day | e.g. SRIL FY2020 usable from 2021-04-01 |
| Prices, shares, liquidity | `idx.bar` raw close × `daily_summary.listed_shares` (same-day basis) for market cap; adjusted close for returns and dividend yield | 2020-01-02 → 2026-09-11 |
| Dividends | Yahoo dated events (`idx.dividend`), split-adjusted, taxed 10 % | 1,947 events |
| Benchmarks | `idx.index_daily`: COMPOSITE, LQ45, IDXV30, IDXHIDIV20 (price) | 2020 → 2026-09-11 |

## Method

Rebalance on the first trading day on/after the 2nd of the month (May = the reported schedule; Feb/Aug/Nov = robustness);
equal weight at the close; buy-and-hold to the next rebalance; **25 bps per side + half the IDX tick** on every trade; **10 %
dividend tax**; a held name with no trade on the rebalance day is carried; a delisted name is worth zero after its last bar;
fundamentals count only if published by that day's close. Selection = `candidates.rank_pool(gate=, keys=, sector_cap=)`:
average ranks (ties share a rank), top fifth, at least 10 names, only when the pool has ≥ 20 names (else cash).

| Portfolio | Rule |
|---|---|
| bench | every eligible liquid name, same simulation |
| quality | strict gate: ROE ≥ 10 %, profit this **and prior** year, CFO > 0, D/E ≤ 1.5 (financials exempt) |
| value_naive | cheapest fifth by E/P among all eligible names — the value-trap control |
| value_q / composite_q | E/P / composite rank(E/P, B/P, DY) within the strict gate |
| value_qloose / **composite_qloose** | the same within the loose gate (profit > 0, ROE ≥ 5 %) — composite_qloose is the deployed rule |
| composite_qloose_seccap | the rule with at most one third of the selection per IDX-IC sector (pre-registered in the review) |
| composite_qf | composite_q minus the bottom quintile of 20-day foreign flow |
| ep_q1..q5 | E/P quintiles within the strict gate (monotonicity check) |

## Results, May 2021 → 2026-09-11 (May rebalances)

| Portfolio | Total | CAGR | Sharpe | max DD | DSR@13 | PSR | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| bench (EW eligible, div, costs) | +47 % | 7.4 % | 0.37 | 44 % | 0.19 | 0.79 | +19 | −8 | −10 | +5 | +68 | −17 |
| quality (strict gate, all) | +37 % | 6.1 % | 0.37 | 35 % | 0.19 | 0.80 | +14 | +6 | 0 | +3 | +25 | −11 |
| value_naive (no gate) | +232 % | 25.1 % | 1.01 | 29 % | 0.71 | 0.99 | −1 | +24 | −7 | +18 | +121 | +12 |
| value_q (strict) | +231 % | 25.1 % | 1.01 | 32 % | 0.71 | 0.99 | +14 | +29 | −9 | +18 | +75 | +19 |
| **composite_q (strict)** | **+146 %** | **18.3 %** | **0.98** | **22 %** | 0.69 | 0.99 | +15 | +35 | −8 | +12 | +21 | +26 |
| value_qloose | +323 % | 30.9 % | 1.16 | 29 % | 0.81 | 0.99 | +6 | +21 | −7 | +22 | +154 | +15 |
| **composite_qloose (deployed)** | **+106 %** | **14.5 %** | **0.83** | **22 %** | 0.56 | 0.97 | +12 | +17 | −2 | +9 | +20 | +22 |
| composite_qloose_seccap | +106 % | 14.5 % | 0.83 | 22 % | 0.56 | 0.97 | (cap never binds at May) | | | | | |
| composite_qf (flow veto) | +114 % | 15.3 % | 0.78 | 24 % | 0.52 | 0.96 | −3 | +40 | −1 | +6 | +21 | +23 |
| COMPOSITE (price) | +10 % | 1.8 % | 0.11 | 42 % | — | — | +11 | +4 | +6 | −3 | +22 | −24 |
| IDX High Dividend 20 (price) | +8 % | 1.5 % | 0.08 | 40 % | — | — | +13 | +19 | +3 | −11 | 0 | −12 |
| IDX Value 30 (price) | 0 % | 0.0 % | 0.00 | 38 % | — | — | +3 | +15 | −16 | +1 | +10 | −10 |
| LQ45 (price) | −27 % | −5.6 % | −0.32 | 51 % | — | — | +5 | +1 | +4 | −15 | +2 | −23 |

Calendar years are calendar buckets; 2026 is January → 11 September. Rebalance-to-rebalance returns:

| | 2021→22 | 2022→23 | 2023→24 | 2024→25 | 2025→26 | 2026→Sep |
|---|---|---|---|---|---|---|
| bench | +24 | −17 | −5 | +13 | +42 | −7 |
| composite_qloose | +31 | +2 | −1 | +7 | +36 | +7 |
| composite_q | +43 | +10 | −4 | +9 | +38 | +8 |
| value_qloose | +24 | +4 | −5 | +78 | +90 | +2 |

E/P quintiles within the strict gate (cheapest → dearest): **+266 % / +86 % / +43 % / −36 % / −51 %** (DSR 0.74 / 0.36 /
0.17 / 0.01 / 0.00) — monotonic, a 317-point ladder.

### Calendar sensitivity (identical rule, other rebalance months)

| Rebalance month | composite_qloose | composite_q | value_qloose | bench |
|---|---|---|---|---|
| May (reported) | +106 % · 14.5 %/yr · Sh 0.83 · DD 22 % | +146 % · 18.3 % · 0.98 · 22 % | +323 % · 30.9 % · 1.16 · 29 % | +47 % · 7.4 % |
| February (invests from 2022) | +111 % · 17.7 % · 0.93 · 21 % | +224 % · 29.1 % · 1.44 · 22 % | +129 % · 19.7 % · 0.83 · 33 % | +26 % · 4.3 % |
| August | +114 % · 16.0 % · 0.93 · 21 % | +128 % · 17.5 % · 0.94 · 25 % | +55 % · 9.0 % · 0.49 · 28 % | +29 % · 5.1 % |
| November (from Nov 2021) | +63 % · 10.6 % · 0.63 · 23 % | +85 % · 13.5 % · 0.79 · 24 % | +66 % · 11.1 % · 0.57 · 31 % | +15 % · 2.9 % |

The sector cap (one third per sector) changes nothing at May and August, costs 40 points at February (it drops PTRO, the
+34-point name of the Feb-2024 book) and adds 7 at November: no consistent benefit, **not adopted**; the option stays in
`rank_pool(sector_cap=)`.

### Concentration — what carried each year (composite_qloose, May)

| Period | return | top-3 names' share of NAV | worst |
|---|---|---|---|
| 2021→22 | +31 % | **+30.9** (SRTG +19.9, PTBA +6.5, UNTR +4.5) | DMAS −2.3 |
| 2022→23 | +2 % | +8.9 (TRJA, ITMG, BNGA) | MNCN −1.9 |
| 2023→24 | −1 % | +6.3 (BNGA, MEDC, AUTO) | INDY −1.8 |
| 2024→25 | +7 % | +4.9 (ADRO, INDF, ERAA) | MNCN −1.1 |
| 2025→26 | +36 % | +16.5 (TAPG +7.4, INKP +4.8, ELSA +4.3) | SMRA −1.4 |
| 2026→Sep | +7 % | +4.6 (ERAA, BFIN, AUTO) | ASII −0.6 |

Without SRTG the first year is +11 %, not +31 %. The bench's +47 % is the same story writ large: the median liquid stock lost
money, the average gained because a handful went up five to ten times (ENRG, BULL, HRTA, DEWA in 2025–26). Equal weight
buys that tail; the rank decides whether the book holds any of it.

### What the portfolios held (composite_qloose, May)

- **2021** (10): ASII, BJBR, BJTM, DMAS, DSNG, ELSA, INDF, PTBA, SRTG, UNTR
- **2022** (20): AALI, ADRO, BBTN, BJBR, BJTM, BNGA, BSSR, DMAS, DSNG, GGRM, INDF, INKP, ISSP, ITMG, JPFA, MNCN, MPMX, PALM, TKIM, TRJA
- **2023** (19): AALI, ADRO, AUTO, BBTN, BJBR, BNGA, HRUM, INDY, ITMG, LSIP, MEDC, MPMX, PGAS, PNLF, PTBA, SMDR, SRTG, TINS, UNTR
- **2024** (17): ADRO, ASII, AUTO, BBTN, BDMN, BNGA, BTPS, ELSA, ERAA, INDF, INDY, ITMG, MNCN, MPMX, NISP, PGAS, PTBA
- **2025** (17): ADRO, ASII, AUTO, BBNI, BBTN, BNGA, ELSA, GJTL, INKP, ITMG, LSIP, MEDC, NISP, PTBA, SMRA, TAPG, UNTR
- **2026** (24): AALI, ACES, ADRO, ASII, AUTO, BBNI, BBRI, BFIN, BNGA, BTPS, CTRA, ERAA, GJTL, INDF, INTP, JSMR, LSIP, NISP, PWON, SIMP, SMDR, SMRA, SRTG, UNTR

Sritex (SRIL) sat at rank 12 of the 2021 pool with the cut at 10 — the composite missed it by two ranks because it paid no
dividend; the pure-E/P book (value_qloose 2021: AISA, BJBR, BJTM, DMAS, ENRG, GGRM, INDF, PNBN, SRIL, SRTG) holds it, is stuck
in it from the 2021-05-18 suspension, and writes it to zero at delisting. PGEO no longer appears anywhere (its reports were
1000× too big); PTRO no longer appears in May 2024 (market-cap basis bug); both are in the strict/loose pools at their true
ranks (#43 / #59 in May 2024).

## Reading

1. **Cheapness is the driver; the ladder is monotonic and steep.** Cheapest fifth +266 %, dearest fifth −51 % within the same
   gate. The value-trap control (no gate at all) makes +232 % — cheap IDX stocks did not, as a group, keep getting cheaper in
   this window; the trap is a per-name event (Sritex), not a group effect.
2. **The strict gate does not hurt once it actually works.** Rev. 2's "strict hurts" came from a prior-year test that could
   never fail, a book that went to cash in 2021 because the top fifth of a small pool was under ten names, and mis-scaled
   reports. With those fixed, the strict composite leads the loose composite in all four calendars (18.3 vs 14.5 %/yr at May)
   with the same drawdown. The two share most names; the strict form holds 10–15, the loose 10–24.
3. **The composite is the steadier form; pure E/P is the bigger and more fragile one.** value_qloose +323 % at May but +55 %
   at August, drawdown 29–33 %, and it owns Sritex. The composite's calendar range is 10.6–17.7 %/yr with 21–23 % drawdowns.
4. **The bench is positive, not negative.** On a buy-and-hold, dividends-included, cost-charged basis the equal-weight liquid
   universe made +47 % (the median name lost). Rev. 2's −28 % was the geometric-mean artifact. The edge over the bench is
   7–13 points a year depending on the calendar; over the COMPOSITE it is 9–16.
5. **One name can be a year.** SRTG was two thirds of 2021; TAPG/INKP/ELSA were half of 2025; PTRO would have been a third of
   a February-2024 book. Expect lumpy years and do not read a single good year as skill.
6. **Foreign-flow veto and sector cap add nothing consistent.** composite_qf is within noise of composite_q; the sector cap
   is neutral at two calendars, harmful at one, mildly helpful at one.
7. **Data quality is still part of the edge.** Three of the seven fixes in this revision changed who was in the book. The
   EPS × shares check now runs on every parse and leaves 0 power-of-1000 mismatches on audited rows (was 83).

## What this is and is not

- It is: six point-in-time rebalances (four calendars) over the full universe, on a real portfolio path, in which a
  cheap-and-profitable, equal-weight, annually rebalanced IDX book beat the equal-weight universe, the COMPOSITE and the
  official value index at every rebalance date tested, with ~22 % drawdowns.
- It is not: a certified sleeve. DSR 0.56 (loose) / 0.69 (strict) at N = 13 against the 0.90 bar; six decisions per calendar;
  one regime (post-COVID recovery, commodity cycle, 2025 mid-cap mania). Only forward years fix that.
- Costs are inside the numbers (25 bps + half-tick per side, 10 % dividend tax).

## Recommended operating form

- **Rule (unchanged, deployed):** board Utama/Pengembangan on the day → traded → liquid ≥ Rp 5 bn/day → loose gate
  (profit > 0, ROE ≥ 5 %) → composite average rank(E/P, B/P, DY) → top fifth, min 10, pool ≥ 20 else cash; equal weight;
  rebalance in early May. `idx candidates` is the implementation and the backtest calls it.
- **Decision for the operator, pre-registered now, to be taken at the May 2027 rebalance, not before:** switch the book to
  the strict composite (`rank_pool(gate="strict")`, the same list with the strict flags applied as a cut) if it still leads
  the loose composite across all four calendars on the May 2027 refresh. Until then the strict flags remain judgment inputs on
  the card, as today.
- **Operator layer:** the thesis card and the pack for each candidate; `idx answers --score` will show whether that layer
  adds or subtracts, once the first answers are a quarter old.
- **Sizing:** modest, as befits DSR 0.56–0.69 and one-name years.

## Multiplicity ledger

13 portfolios (bench excluded): quality, value_naive, value_q, composite_q, value_qloose, composite_qloose,
composite_qloose_seccap, composite_qf, five quintiles; four rebalance months as robustness with May fixed in advance as the
reported one (no calendar was chosen after seeing results); no threshold search beyond the two gate levels inherited from
rev. 1. DSRs above apply N = 13.

## Reproduce

```
set -a; source blackheart-ingest/idx-local.env; set +a
scripts/idx.sh fin discover --years 2020-2026
# audited reports for every name liquid since 2021 (the PIT universe), then re-parse everything with the scale checks
scripts/idx.sh fin download --codes "$(psql-or-python: DISTINCT code FROM idx.feature_daily WHERE trade_date >= '2021-01-01' AND value_60d_median >= 5e9)" --years 2020-2025 --periods audit
scripts/idx.sh fin parse --reparse ; scripts/idx.sh dividends --universe
blackheart-ingest/.venv/Scripts/python research/idx_value_quality.py --months 5,2,8,11 > research-scratch/idx-screen/value_quality_out.txt
blackheart-ingest/.venv/Scripts/python -m pytest research/test_idx_value_quality.py blackheart-ingest/tests/idx
```
