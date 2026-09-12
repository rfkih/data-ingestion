# IDX Phase 1b — Cheap Overlays: Foreign Flow, Disclosures, Events (2026-09-12)

**Verdict: no overlay is certifiable on its own. One survives every honesty check as a *conditioning rule*:
"enter trend trades in large caps only when foreign investors are net buyers" — it roughly doubles the trend
rule's Sharpe on large caps in-sample and holds up out-of-sample (0.61 vs 0.37 unfiltered), but the absolute
level (DSR 0.10 at honest N = 96) is far from the 0.90 gate and the most recent fold is negative. Disclosure
events carry nothing tradeable; the dividend "drift" is the un-adjusted ex-date drop.**

Scripts: `research/idx_overlays.py` (+ the large-cap follow-ups run inline, saved to
`research-scratch/idx-screen/overlays_largecap_wf.json`); raw output `overlays_out.txt`, JSON `overlays_results.json`.
Data: `idx.feature_daily` (phase-1b features, PIT at the 16:00 WIB cut; `blackheart_ingest/idx/features.py`),
`idx.event` from 152,350 disclosures (archive starts **2023-07-03**), `idx.bar` 2020+. READ-ONLY.

## What was built (1b.1 / 1b.2)

| Piece | Result |
|---|---|
| `announce` job | 986 codes, 152,350 disclosures 2023-07 → 2026-09, 0 failures; title-rule classifier (30 kinds), sample precision 29/30; `--reclassify` re-derives kinds/events from stored titles without refetching |
| `idx.event` | 55,113 typed events; `exchange_query` (UMA-type: "Penjelasan atas Volatilitas Transaksi" / "Permintaan Penjelasan Bursa") 6,454; ownership changes 10,644; dividends 2,104; rights 500 |
| `idx.feature_daily` | 1,360,091 rows, 989 codes: foreign net flow share 5d/20d, 60-day median value, market cap + quintile, trailing event counts — every value usable only from that day's 16:00 WIB cut (unit-tested) |
| `feature_values` mirror | registry + values path built (`idx features --publish`); not needed for the verdict, so not populated |

## Tests and results (universe = 451 ever-liquid names, 2020-01-02 → 2026-09-11, 50 bps, PIT liquidity gate)

### A. Foreign flow as an entry filter on the Donchian sleeve (pooled equal-weight, next-open fills)

| Universe | unfiltered | f20 > 0 | f5 > 0 ∧ f20 > 0 | f20 < 0 |
|---|---|---|---|---|
| All 451 (best cell) | **0.63** (55/20 LS) | 0.60 | 0.35 | 0.56 |
| Large caps, 38 names ≥ Rp 50 bn/day (best cell) | 0.37 (100/40 L) | 0.68 | **0.73** (55/20 L) | — |

On the whole universe the filter does nothing (foreign participation in small caps ≈ 0, so the feature is noise
there). On large caps it doubles the Sharpe. Walk-forward on large caps (5 expanding folds, filter *and* cell
picked on the train fold only): the same filter was chosen in every fold; **OOS Sharpe 0.61 vs 0.37
unfiltered, 4/5 folds positive** — the last fold (2025-10 → 2026-09) −24 %. Honest N = 96 (4 filters × 8
cells × 3 universe cuts): **DSR 0.25 in-sample, 0.10 out-of-sample.** By year (filtered / unfiltered, same
cell): 2020 +54/+19, 2021 −31/−42, 2022 +45/+35, 2023 +54/+33, 2024 +23/+22, 2025 +170/+118, 2026 −42/−44.

### B. Foreign flow standalone (weekly quintile sorts on the flow share, cost on turnover, no same-day look-ahead)

| Subset | 5-day flow: Q5 − Q1 spread Sharpe (t) | 20-day | Q1 basket alone |
|---|---|---|---|
| All 451 | −0.10 (−0.25) | −0.08 (−0.19) | — |
| Mid caps 10–50 bn (70) | +0.03 (0.07) | −0.50 (−1.27) | — |
| **Large caps ≥ 50 bn (38)** | **+1.27 (3.20)** | +0.86 (2.18) | −0.68 (−65 % over the window) |

A first version of this test credited a rebalance day's own return to the selection made at that close; fixed
(selection at close *t*, held from *t+1*). The effect is entirely a large-cap phenomenon and lives on the
**sell side**: names foreign investors are dumping underperform badly; names they are buying do not beat the
basket. Long-only, weekly-rebalanced versions **do not beat simply holding the large-cap basket net of cost**
(benchmark 0.74; "all except Q1" 0.50; "Q5 only" 0.62) because the weekly churn costs more than the gross
edge. Retail IDX cannot short, so the spread is not tradeable. What is tradeable is the low-turnover use in A.

### C. Event studies (abnormal return vs COMPOSITE index, from the PIT effective day; 2023-07+)

| Event | n | pre-5d | +10d mean / median / hit | +20d mean / median / hit (t) |
|---|---|---|---|---|
| exchange_query (UMA-type) | 2,912 | +4.7 % (t 14) | +0.7 % / −0.9 % / 0.45 | +1.4 % / −0.9 % / 0.47 (3.1) |
| ownership_change | 6,475 | +1.5 % | +0.9 % / −0.5 % / 0.47 | +1.4 % / −0.8 % / 0.47 (5.8) |
| dividend (announcement) | 1,236 | +1.5 % | −2.8 % / −2.9 % / 0.34 | −2.5 % / −3.3 % / 0.36 (−6.3) |
| rights | 500 | +3.8 % | −0.6 % / −1.8 % / 0.40 | +0.5 % / −1.6 % / 0.44 (0.4) |
| buyback, material_info | 782 / 1,531 | ≈ 0 | ≈ 0 | ≈ 0 |

Reading: the UMA-type query follows a +5 % five-day spike and is followed by **neither reversal nor a
tradeable continuation** — the positive means are a handful of pump names; the typical event is down and the
hit rate is under 50 %. Ownership-change reports show the same skew (direction unknown without the PDF).
The dividend "drift" is the mechanical ex-dividend price drop — our prices are not dividend-adjusted — not
information. Rights issues: nothing after day 1.

### D. BRPT (the phase-1 admit-candidate) with flow filters, 2020+ — 18 trades unfiltered

f20 > 0: 13 trades, Sharpe 0.57 → 0.66; f20 > +5 %: 7 trades, 0.99, max DD 59 % → 22 %; f20 < 0: −0.03.
Directionally consistent with A, far too few trades to weigh.

## Conclusions

1. **Foreign flow is informative, but only in large caps and only cheaply as a filter.** Its value is a veto on
   what foreign investors are selling. Applied as an entry condition to the trend rule in large caps it is
   walk-forward-stable and lifts OOS Sharpe by ≈ 0.25 — worth keeping as a *rule* for any future IDX large-cap
   sleeve (including BRPT if it goes to paper), not worth trading as a signal.
2. **Disclosure events are not a source of alpha at daily resolution** (metadata-only). The only strong,
   consistent event fact is that UMA-type queries follow spikes, and nothing systematic follows them.
3. **Nothing here lifts IDX over the platform's bar.** The phase-1 verdict stands: no certifiable sleeve;
   the data plane, the event table and the flow features are useful thesis-support and screening tools.

## Multiplicity ledger

A: 6 filters × 8 cells × 3 universe cuts (+ 1 extra filter on large caps) → N = 96–104. B: 3 subsets × 2
features × (spread, Q5, veto) + 1 long rule → N ≈ 19. C: 7 kinds × 4 horizons × 2 benchmarks → 56 (no
parameter search). All in-sample Sharpes above are before this deflation; the DSRs quoted apply it.

## Reproduce

```
set -a; source blackheart-ingest/idx-local.env; set +a
scripts/idx.sh announce            # 2023-07 -> today, all codes (resumable)
scripts/idx.sh features            # idx.feature_daily for all codes
blackheart-ingest/.venv/Scripts/python research/idx_overlays.py [--limit N]
```
