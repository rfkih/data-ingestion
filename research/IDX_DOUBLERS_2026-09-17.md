# IDX — which financial profile preceded a 2x within 24 months? (2026-09-17)

**Question (operator, 2026-09-16 night):** "cari yang punya probabilitas paling tinggi untuk naik 100 persen dalam 2 tahun" —
from the financial statements, now that the 2020–2026 quarterlies of the whole liquid universe are parsed (1,900 workbooks
backfilled the same night). Script `research/idx_doublers.py` (design pre-registered in its docstring before the first run);
panel `research-scratch/idx-screen/doublers_panel_2026-09-17.csv`; full tables `doublers_2026-09-17.md`; the run is stored as
**study #2 `doublers`** (`idx study show --name doublers`, `GET /idx/study/latest?name=doublers`), the evidence per name in
`idx.evidence` (`idx study name CODE`, `GET /idx/name/CODE`). Trials: 16 features + 5 screens = 21 → cumulative **N = 194**.

## Design

- 22 quarterly snapshots (last trading day of Feb/May/Aug/Nov, 2020-05 → 2025-08; 24-month windows complete through 2024-08),
  point-in-time universe = Utama/Pengembangan on the day, traded, 60-day median value ≥ Rp 5 bn, with an audited report
  (`candidates.build()`, 16:00 WIB cutoff). 2,789 name-snapshots; 2,263 with a full 24-month window.
- Targets: **touched2x_24m** (max adjusted close within 24 months ≥ 2× the snapshot close; primary), **end2x_24m** (still ≥ 2×
  at month 24; the honest one), and the 12-month versions. A delisting inside the window counts as no double / −100 %.
- 16 PIT features (TTM E/P, B/P, DY, ROE, cash conversion, D/E, YTD profit and revenue growth, profit acceleration, margin change,
  turnaround, net cash/mcap, 12-1 momentum, distance from the 52-week high, size, liquidity) in within-date quintiles; a feature
  passes when the extreme quintile's lift ≥ 1.5 on the primary target in ≥ 4 of 5 snapshot years with n ≥ 100.
- 5 pre-registered screens: A cheap_growth, B beaten_value, C small_quality, **D turnaround** (prior-year loss → profit, YTD
  revenue growing, liquid), E accel_cheap.

## Base rates

| target | all | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---|---|---|---|---|---|
| touched 2× within 24 m | **17.3 %** | 33 % | 17 % | 9 % | 13 % | 28 % |
| still 2× at month 24 | **8.2 %** | 15 % | 6 % | 3 % | 9 % | 15 % |
| touched 2× within 12 m | 13.1 % | 23 % | 13 % | 5 % | 5 % | 15 % (2025: 29 %) |

A liquid IDX name picked at random touches a double within two years about one time in six; it is still a double at the end
one time in twelve; the median 24-month return of the universe is **−14 %** (mean +10 %: the distribution is a few rockets and
a long tail of losers).

## What raised the odds (single features, primary target)

| feature | direction that passes | extreme-quintile hit | lift | years | median 24 m return of that quintile |
|---|---|---|---|---|---|
| **size** (log mcap) | small | 27 % (Q1) vs 8 % (Q5) | 1.55 | 5/5 | −12 % |
| **TTM E/P** | low (loss-making / expensive) | 26 % (Q1) | 1.52 | 5/5 | **−29 %** |
| **ROE** | low | 26 % (Q1) | 1.51 | 5/5 | −29 % |
| **profit acceleration** | high | 31 % (Q5) | 1.64 | 5/5 | −1 % |
| **turnaround** (flag) | true | **36 %** (n = 214) vs 15 % | **2.08** | 5/5 | — |
| YTD profit growth | high (and also low: U-shape) | 29 % / 27 % | 1.49 / 1.38 | 4/5, 5/5 | −8 % / −4 % |
| B/P | high | 25 % | 1.42 | 5/5 | −4 % |
| strict gate | **true LOWERS it** | 11 % vs 21 % | 0.66 | 0/5 | — |
| loose gate | true lowers it | 15 % vs 23 % | 0.84 | 0/5 | — |
| momentum, distance from high, net cash, DY, D/E, liquidity | no pass | | | | |

Two readings that matter:

1. The features that raise the *probability of touching a double* are the lottery profile: small, loss-making or barely
   profitable, low ROE. Their median outcome is **−29 %**. "Highest probability of 2×" and "good investment" are different
   questions; the value/quality gates that make the desk's strict rule compound (18 %/yr) actively *lower* the chance of a
   double (11 % vs 21 %) because they exclude exactly those names.
2. Among the growth features only **turnaround** and **acceleration** carry a positive median as well as a high hit rate —
   a business that just stopped losing money is the one profile where the double is not paid for with a median loss.

## Pre-registered screens

| screen | names / date | touched 2× 24 m | lift | years > base | still 2× at 24 m | median 24 m | mean | lose > 50 % |
|---|---|---|---|---|---|---|---|---|
| A cheap_growth | 18.1 | 14 % | 0.80 | 2/4 | 7 % | −11 % | +35 % | 6 % |
| B beaten_value | 8.2 | 24 % | 1.41 | 3/5 | 12 % | −1 % | +42 % | 12 % |
| C small_quality | 6.8 | 24 % | 1.37 | 3/5 | 15 % | −3 % | +57 % | 10 % |
| **D turnaround** | 7.9 | **43 %** | **2.48** | **5/5** | **23 %** | **+8 %** | **+56 %** | 13 % |
| E accel_cheap | 7.5 | 23 % | 1.31 | 3/5 | 13 % | −6 % | +82 % | 5 % |

Only **D passes** (lift ≥ 1.5, every year above that year's base). Post-hoc slices of D (not pre-registered, +0 trials
claimed, reported for the operator's judgment only): D ∩ smaller half of the universe → **58 % touched, 34 % still 2×, median
+42 %** (n = 77, 4/5 years); D ∩ TTM E/P > 5 % → 31 % / 14 % / −2 % (the cheap-and-turned names did *worse*: the market had
already priced the recovery); D ∩ positive momentum → 42 % / 23 % / +11 %.

What D picked, historically (24-month return, * = touched 2×): 2020 INCO +181*, ISAT +169*; 2021 ENRG +136*, BRMS +131*,
FILM +500*, MAPI +161*, MEDC +125*; 2022 FILM +345*, ISAT +100*, TPIA +99*, BUMI +65* but also ARTO −74, BUKA −61, INDY −51;
2023 SSIA +519*, DEWA +245*; 2024 DEWA +821*, OASA +255*, DOOH +443*, MKAP +180*, BULL +172*, PSAB +156*. The failures
cluster in the 2022 cohort (digital banks, coal after the spike) — a turnaround bought at the top of its own cycle.

## Today's D list (2026-09-16) with the operational evidence (web + IDX disclosures, stored in `idx.evidence`)

| code | mcap (Rp T) | TTM E/P | from 52w high | mom 12-1 | what actually turned | read |
|---|---|---|---|---|---|---|
| **SSIA** | 8.1 | 2.5 % | −29 % | −32 % | H1 2026 profit Rp 263 bn from a loss: Subang Smartpolitan + Karawang land sales; 2026 marketing-sales target 135 ha (+188 %), Q2 demand > 400 ha, backlog Rp 727 bn; BYD effect | **the one real operational turnaround in the small-mid bucket**; already delivered 3 doubles from earlier D snapshots (2023-24), this year's −32 % is the reset |
| MBMA | 54 | 2.0 % | −45 % | +21 % | Q1 2026 NPATMI US$ 30 m from a loss; ore mining +143 %; HPAL commissioned end-Q2, awaiting the IUI permit | real, catalyst dated (HPAL start); large |
| MDKA | 70 | ~0 | −28 % | +21 % | Q1 2026 US$ 57.5 m from a loss; Pani first gold Feb 2026; Tujuh Bukit copper FS finalising | real (gold + MBMA); large |
| AMMN | 373 | 2.5 % | −37 % | −48 % | smelter back ~April 2026, all mine output processed by June; H1 46 kt cathode, 3.7 t gold; 2026 target 162 kt / 16 t | real; the largest name on IDX — D's edge came from small names |
| TPIA | 158 | 0.5 % | −78 % | −77 % | H1 2026 US$ 283 m profit; revenue +84 % (Aster / Shell Bukom); chemical segment loss narrowing US$ 148 m → 21 m; Bukom CSU +US$ 20 m EBITDA/month from Q4 | panel's "−78 % yoy" is the prior-year bargain-purchase gain; operations improving, but bear case (Bloomberg Technoz) and size argue against |
| SUPA | 17 | 1.6 % | −60 % | — | H1 2026 profit Rp 183 bn (+790 %), loans +61 %, NPL 1.6 %, CIR 55 %; Rp 217 bn write-off, deficit still large | digital bank — the profile that failed in the 2022 cohort (ARTO, BUKA) |
| KOTA | 2.0 | 3.5 % | −16 % | **+581 %** | H1 2026 profit Rp 16 bn from a loss; revenue ×3.9 (hotel + real estate); rights issue | real but the double already happened |
| GULA | 0.9 | −0.6 % | −3 % | +101 % | H1 sales +122 %; net profit Rp 35 **million** (break-even); new plant 2026, revenue target Rp 336 bn | speculative; catalyst = plant |
| IRSX | 2.5 | 1.2 % | −49 % | +210 % | FY2025 profit after a new controller + acquisition; Q1 2026 revenue +233 %; FolaPlay = official World Cup 2026 platform | one-off driven; thin margin |
| PADA | 0.6 | 0.9 % | −52 % | +291 % | Q1 revenue +82 %, profit Rp 2.8 bn (tiny); new Permenaker limits outsourcing to 6 job types | lottery + regulatory risk |
| MINA | 2.6 | ~0 | −59 % | +44 % | H1 profit from **financial income**, not the villas; liabilities −75 %; 4-ha Sanur project still a plan | accounting turnaround — fails the spirit of the screen |
| SINI | 17 | 3.6 % | −4 % | +191 % | H1 profit Rp 683 bn of which **Rp 663 bn is a bargain-purchase gain** (Kemilau Mulia Sakti, June 2026); rights issue | accounting turnaround — fails the spirit of the screen |

## Answer

- There is no financial-statement profile that *predicts* a double; there is one that raises the odds from 1-in-6 to
  roughly **2-in-5 (touched) / 1-in-4 (kept)** with a positive median: a liquid name whose profit just turned positive after a
  loss year while revenue grows — and it works best on small names (post-hoc 58 % / 34 %). It costs a 13 % chance of losing
  more than half.
- Applied today and read against the operational news, the list reduces to **SSIA** as the clean small-mid case, **MBMA /
  MDKA / AMMN** as real but large (where D's evidence is weakest), and a tail (KOTA, GULA, IRSX, PADA) that is either already
  re-rated or break-even. MINA and SINI are accounting turnarounds and should be ignored. SUPA is the failed-cohort profile.
- This is a screen, not a rule: N = 194 trials, five snapshot years, two crash-rebound years (2020, 2024) carrying most of the
  doubles. Position sizing for a D basket, if the operator wants one, belongs to the judgment tier (small, equal weight, accept
  −50 % on one in eight), not to the strict book.

## Second opinion (Fable 5.1, same day) — every feature at once, validated by year

`research/idx_doublers_model.py` (pre-registered; trials 195–196, cumulative **N = 196**): logistic regression and LightGBM on
the same PIT panel (percentiles of the 15 features + flags + screen memberships), **leave-one-snapshot-year-out**. LightGBM
passes 5/5 years (AUC 0.65–0.82; OOS top decile touched 2× in 25–62 % of cases vs base 9–33 %, lift 2.2–3.7); logistic 4/5.
Weights agree with the screens: turnaround, small, low E/P, low ROE, revenue growth, momentum.

Robustness of the SSIA slice (turnaround & small & TTM E/P ≤ 5 %): without 2020 and 2024 still 70 % / 39 % (base 13 % / 6 %);
**deduplicated by name 61 % / 30 % / median +42 %** (n = 23); 12-month horizon 50 % (base 13 %), but the 2025 snapshots only 25 %.

Today's model ranking (2026-09-16, 158 names): PADA 73 %, GULA 70 %, MINA 68 %, KOTA 60 %, IRSX 55 %, **SSIA 55 % (rank 6)**,
MDIA, AYAM, SUPA … BULL 33 %, MBMA 35 %, DMAS 36 %, GJTL 27 %, **INKP 8 %, TKIM 12 %, AMMN 12 %** (large cheap names confirmed
out). The model is over-confident at the top (OOS calibration: predicted 55 % → realized 47 %; 71 % → 52 %), so SSIA ≈ 47–50 %
touched / 25–30 % kept.

Why the names ranked above SSIA are not the pick — OOS top-decile subsets: **momentum > +150 % ("already ran") 47 % touched but
18 % kept, median −26 %, 38 % lose > 50 %**; micro caps < Rp 1 T 58 % touched but 29 % lose > 50 %; whereas turnaround & ≥ Rp 3 T &
momentum ≤ +150 % (SSIA's bucket) 50 % touched, median +32 %, 8 % lose > 50 %. The operator's constraint (not already re-rated,
minimal risk) is therefore a data statement, not a preference: the lottery names double *and* blow up.
