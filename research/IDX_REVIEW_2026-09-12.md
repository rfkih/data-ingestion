# IDX value/quality desk — review of what was built (2026-09-12)

> **Status (same day, evening): all six fix items are done.** PIT universe from the day-dump notation string + 305 missing
> audited reports downloaded + suspension/delisting handling (§1.1); the research script now drives the production
> `candidates.build()`/`rank_pool()` with average ranks and one pool rule (§1.2, §2); stored prior-period comparatives,
> EPS normalisation and the EPS × shares scale check with flags (§3, migration 0009, all 5,903 reports re-parsed: 394 EPS
> rows repaired, 6 whole reports rescaled, 0 power-of-1000 mismatches left on audited rows); a real portfolio path with
> net dividends, 25 bps + half-tick costs and the dividend/cost bugs gone (§1.3–1.5); the research note restated as rev. 3
> with the calendar range and the IDX factor indices (§1.6–1.7); the sector-cap variant pre-registered and run, and
> `idx answers --score` for the pack (§5). One more defect surfaced while re-running and is fixed too: market cap in the
> candidate builder multiplied the split-adjusted close by the day's (unadjusted) share count, so names that later split
> looked up to 10× cheaper in past runs (PTRO ranked #1 in May 2024 on that). Results: `research/IDX_VALUE_QUALITY_2026-09-12.md` rev. 3.
>
> **Later the same night:** four more pre-registered menus (ten names, weights and holding rules, quality, cash conversion; 71 trials in all) left the strict composite the only robust improvement, and the operator moved both books to it on 2026-09-12 (`IDX_TOP10`, `IDX_HOLD_WINNERS`, `IDX_QUALITY`, `IDX_CASH_CONVERSION`, same date). Paper ticket #13 is the switch, drafted and unfilled.

Scope: the prediction/selection pipeline (`research/idx_value_quality.py`, `idx/metrics.py`, `idx/candidates.py`,
`idx/fin_parse.py`, `idx/fin_store.py`, dividends), the backtest behind the "+122 %" verdict, and the operator layer
(pack, book, ticket). Every number below was re-derived on the local restored DB today; scripts and outputs are in
`research-scratch/idx-screen/sens/` (rebalance-month sensitivity) and the session scratchpad (DB checks).

## Verdict in one paragraph

The core claim survives: a cheap-and-profitable, equal-weight, annually rebalanced IDX book beat the equal-weight universe,
the COMPOSITE, LQ45 and the official IDX Value 30 index at every one of four rebalance dates tested, with positive calendar
years in every variant. What does **not** survive is the headline magnitude and some of the readings. The +122 % is the best
of four calendar dates (Feb/Aug/Nov give +93/+91/+60 %; over the common 2022–26 window May and Feb make ~+94 %, Aug and
Nov ~+58 %). The backtest universe is survivorship-biased (built from today's board membership, so Sritex-type collapses
were never eligible), it has no data-error guard (PGEO was held two years on figures 1000× too large), it under-counts
dividends before splits, and the "two years of profit" test in the strict gate is dead code. None of these flips the sign;
together they say the honest expectation is roughly +10–15 %/yr CAGR with 25 % drawdowns, not +16 %, and that the
"strict gate hurts" reading is not robust (at a February rebalance the strict composite beat the loose one, +126 % vs +93 %).

## 1. Backtest validity

### 1.1 Survivorship-biased universe (material)
`universe.json` (451 names) was built from the *current* `idx.listing`: boards Utama/Pengembangan, status ACTIVE. Today
158 names sit on Pemantauan Khusus, 42 on Akselerasi, 27 are delisted; almost none are in the universe. Names that were
liquid on the rebalance day but excluded because of where they are *now*:

| Rebalance | liquid names | excluded by today's board | examples |
|---|---|---|---|
| 2021-05-03 | 145 | 14 | SRIL, WSKT, WIKA, WSBP, PPRO, MPPA, BEKS, ZINC |
| 2022-05-09 | 168 | 16 | BUKA, WIKA, WSKT, BHIT, MPPA, MLIA |
| 2023–2026 | 126–192 | 3–5 | BUKA, DOOH, PACK |

Their financial reports were catalogued (19–26 each) but never downloaded (`fin download --universe`), so the backtest
could not have picked them even in principle. SRIL is the textbook case: profitable FY2020 (public reporting), ~2–3× earnings
at Rp 149 on 2021-05-03, suspended 2021-05-18 at Rp 146, never traded again, delisted. It would almost certainly have been a
top-fifth composite pick in 2021 (a 10-name book → one tenth of the book to zero). The bias is largest in 2021–22, exactly
the years that make the record 6/6.

Second-order: the backtest cannot model that outcome anyway. A suspended name keeps its last close (zero-volume bars,
1.7 % of all bars), so a position that is frozen for years shows 0 % and is "sold" at the next rebalance at the frozen price.
Delisted names have no bars after delisting and silently drop out of the daily mean (pandas skips NaN), i.e. they leave at
their last price rather than at zero or the tender price.

**Fix:** build the universe point-in-time (board and status from the day-dump `idx.daily_summary`, not from today's listing),
download and parse the reports for every name ever liquid (~200 more codes), and treat suspension/delisting explicitly
(cannot sell while suspended; delisting = last tender price or zero).

### 1.2 No data-error guard in the backtest (material, already bit)
`idx/candidates.py` drops names whose E/P, B/P, DY or TTM E/P exceed 50× (`data_error_ratio`); the research script has no
such guard. Replaying the live rule at the six research dates reproduces the backtest's stored holdings exactly **except**
PGEO, which the backtest held in 2024 and 2025 and the live rule rejects. All ten PGEO reports are stored 1000× too large
(FY2023 net profit Rp 2,525 T vs ~Rp 2.5 T real); the neighbour cross-check in `fin_store._scale_fix` cannot see an error
that is consistent across a company's own reports, and the USD asset ceiling (3 T USD) sits just above PGEO's inflated
3.0 T. PGEO went 1205 → 915 → 1030 over those two years, so the effect on the headline is small and conservative, but the
mechanism (a mis-scaled report ranks #1 on both E/P and B/P) is the same one that corrupted the first version of the report.

**Fix:** one implementation. Make the research script call `candidates.build()`/`rank_pool()` per rebalance date instead of
re-implementing the rule in pandas; then the guard, the tie-break, the age window and the publication cutoff cannot drift.

### 1.3 Dividends before splits are under-counted (small, conservative)
`daily_total_return` multiplies the Yahoo dividend by `adj_factor` on the ex-date. Yahoo amounts are already on the current
split basis and so is `close × adj_factor`, so the factor is applied twice: BBCA's 2021 dividends (adj 0.2) enter at one fifth
of their value, BBRI's at 0.93. Affects the 68 split / 143 rights names before their event; direction conservative.

### 1.4 Turnover cost is double-counted (small, conservative)
`turnover × COST × 2` with turnover = |symmetric difference| / n charges 100 bps for a full replacement, not 50. Conservative.

### 1.5 Portfolio path is not a portfolio (methodology)
Returns are the daily mean of per-name log returns, i.e. the geometric mean across names, and every name is silently
re-weighted daily. That understates a buy-and-hold equal-weight book (Jensen) and hides delisting losses (NaN skip). The
book engine in `idx/book.py` already computes a true NAV from fills, marks, splits and net dividends; replaying historical
tickets through it would give the real path and make backtest and paper book one engine.

### 1.6 Calendar sensitivity (material for expectations)
Same rule, same data, rebalance month changed (`research-scratch/idx-screen/sens/`):

| rebalance month | total | CAGR | Sharpe | mDD | common 2022–26 window | bench |
|---|---|---|---|---|---|---|
| May (report) | +122 % | 16.1 % | 0.88 | 24.5 % | +94 % | −28 % |
| Feb | +93 % | 15.3 % | 0.83 | 23.6 % | +93 % | −28 % |
| Aug | +91 % | 13.5 % | 0.77 | 25.4 % | +62 % | −27 % |
| Nov | +60 % | 10.2 % | 0.58 | 25.3 % | +54 % | −34 % |

Sign and ranking vs bench are robust; magnitude is not. Feb only invests from 2022 (no FY report yet in Feb 2021). The strict
composite at Feb: +126 %, Sharpe 1.23 — it beats loose there, loses at Aug/Nov. "Strict hurts" is one draw, not a law.

### 1.7 Benchmarks that were missing
`idx.index_daily` holds the IDX factor indices. Price returns, first rebalance → 2026-09-11: COMPOSITE +10 %, LQ45 −27 %,
IDX Value 30 0 %, IDX High Dividend 20 +8 %, IDX Quality 30 −15 %, IDX Energy +353 %. The book is not "value beta you
could buy via IDXV30"; it is small/mid-cap equal-weight cheapness with a cyclical tilt. Report against IDXV30/IDXHIDIV20
(total-return versions if IDX publishes them) rather than only the COMPOSITE.

### 1.8 Multiplicity is understated
The ledger counts 12 variants. It omits the phase-1 screen and overlays, the loose gate introduced after the strict gate
failed, and the post-fix re-run. DSR 0.62 is optimistic; the conclusion (not certifiable) does not change.

## 2. Live rule vs backtest parity (`idx/candidates.py`, `idx/metrics.py`)

| item | backtest | live | consequence |
|---|---|---|---|
| tie-break in ranks | pandas average rank | ordinal rank, ties in DB row order (no ORDER BY) | 22 of 106 pool names had DY = 0 on 2026-09-11; their `rank_dy` spans ~22 points by chance → non-reproducible cut-off |
| "min 10" | fewer than 10 selected → hold cash | pad selection up to 10 | never triggered in-sample (pools 51–121), but the two rules differ |
| data-error guard | none | ratio > 50 → excluded | see 1.2 |
| publication cutoff | `published_at ≤ D 00:00 UTC` | `published_at < D+1` | up to a day of extra information live |
| report age | 16 months | 480 days | negligible |

**Fix:** average ranks (or a deterministic secondary key) in `rank_pool`; one `min_names` semantic; and 1.2's single implementation.

## 3. Data pipeline

### 3.1 Prior-year-loss test is dead code (logic bug, both backtest and live)
`prior_from_yoy(cur, yoy) = cur / (1 + yoy)` inverts `_yoy = (cur − prior) / |prior|` only when prior > 0. For a turnaround
(cur = 100, prior = −50 → yoy = 3 → "prior" = 25 > 0) the strict check `prior_year_loss` passes. Since a currently profitable
company with a prior loss always has yoy > 1, the check can never fail for a profitable name. 463 of 1,841 profitable audited
rows have yoy > 1. The same inversion feeds TTM = FY + YTD − priorYTD, so TTM is wrong for every name whose prior YTD was a
loss. **Fix:** store the comparative directly (`extract_metrics` already returns `prior["net_profit"]`) as `net_profit_prior`
and `revenue_prior`; stop reconstructing from the ratio.

### 3.2 EPS is mis-scaled in ~83 audited reports, and EPS is the cheapest scale validator
`fin_parse` assumes per-share rows are never scaled by the rounding label, but some filers scale them: BBNI FY2024 EPS is
stored as 0.0006 (net profit correct at Rp 21.5 T), NISP/EXCL/BIRD/BINA likewise; BRMS the other way. The card prints EPS,
so the operator and the pack see garbage for those names. Once EPS is normalised, `net_profit ≈ eps × shares_out` is a
per-report scale check that needs no neighbours and would have caught PGEO, the FY2023 vintage and the USD cases directly.

### 3.3 Dividends come from Yahoo, one third of the score depends on them
The DY leg and the total-return series use Yahoo events. The aggregate cross-check (median 1.00 vs audited `dividends_paid`)
does not protect individual names; a missing Yahoo event gives DY = 0 and a low composite rank. Fallback: `dividends_paid /
shares_out` from the audited cash flow when Yahoo has nothing for the year; longer term, parse the KSEI/IDX schedule.

### 3.4 Consistent mis-scales are invisible to the neighbour check
`_scale_fix` compares a report to the company's own other reports; PGEO is wrong in all ten. Add an absolute cross-check
(EPS as in 3.2, or net margin / ROA plausibility: ROA above ~60 % or margin above 100 % for a non-financial is a scale error).

## 4. Strategy design

- **Cyclical peak-earnings trap.** Trailing E/P is highest exactly when a cyclical's earnings peak. Energy was 3/10, 3/20,
  7/19, 8/17, 5/17, 1/24 of the book; forward price returns of the energy names +39/+24/−9/+49/+39/+6 % vs roughly flat for
  the rest. 2024 (+19 %) was entirely energy (+49 % vs −8 % financials, −7 % other); the worst names were INDY −42 % (2023)
  and ADRO −31 % (2024). The rule is partly an IDX Energy bet (that index made +353 %). Candidate mitigations, to be
  **pre-registered as single variants, not searched**: a sector cap (e.g. max one third of names per IDX-IC sector) or
  cyclically-adjusted E/P (3-year average earnings, feasible from the 2023 rebalance on).
- **One regime.** 2021–26 is post-COVID recovery plus a commodity supercycle plus a small-cap bust. No 2008/2013/2015-type
  drawdown for value in-sample; only forward years fix this. Size accordingly (the report already says so).
- **Spread cost is not modelled.** 50 bps round trip covers commissions, not the tick. IDX ticks are Rp 1 below Rp 200, Rp 2
  below 500, etc.; a Rp 120 stock has a ≥0.8 % spread. The ticket's limit-at-close ± 1 tick handles it operationally; the
  backtest should charge it.
- **Dividend tax** (10 % final) is in the book but not in the backtest; ~0.3 %/yr.

## 5. Operator / LLM layer (pack, book, ticket)

- The pack prompt is well-scoped (pack-only evidence, JSON schema, versioned). But nothing scores the answers. Each stance
  and veto is stored with a date; add `idx answers --score` that attaches 3/6/12-month forward returns per stance so the
  operator learns whether the second reader adds or subtracts value. Without it the veto ledger is a diary.
- Pack "sell" stances create mid-year exits that the backtest never had. Gate-break exits are effectively annual anyway
  (gates are evaluated on the audited report), so the pack is the only untested deviation from the rule; keep it visible
  in the book's realized P&L (a `reason` on the fill) so it can be measured.
- The pack table inherits the EPS problem (3.2) and any TTM error (3.1); fix those before trusting the "warnings" column.
- Operational: the whole desk runs as a Windows scheduled task against a local Postgres; a laptop asleep at 16:30 WIB means
  no bars, no features, no candidates for that day, and the scheduler must be restarted after every code change. Fine for
  a weekly ritual, fragile for daily alerts.

## 6. Priority order

1. Rebuild the universe PIT and download the missing filers; add suspension/delisting handling; re-run. (Changes the record.)
2. Single implementation: research script → `candidates.build()`; average ranks; one min-names rule. (Parity.)
3. Store prior-period comparatives; fix EPS scaling; add the EPS×shares scale check. (Data.)
4. Fix the dividend adj double-scaling and the cost formula; replay through the book engine for a true NAV. (Accuracy.)
5. Report the rebalance-month range and IDXV30/IDXHIDIV20 in the research note; restate the expectation as +10–15 %/yr.
6. Pre-register one sector-cap or cyclically-adjusted variant; add answer scoring for the pack.
