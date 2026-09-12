# IDX Phase 1 — Donchian Screen on the Primary-Source Data Plane (2026-09-12)

**Verdict: NO-GO for a broad IDX trend sleeve. One admit-candidate (BRPT) for paper-forward evidence only —
nothing is certifiable by mining.**

Script: `research/idx_screen.py` (imports the certified rule/stats from `equity_screen.py`; regression
`research/test_idx_screen.py` = close-fill mode reproduces `equity_screen.sleeve` on all 8 cells to 1e-12).
Raw output `research-scratch/idx-screen/screen_out_{next_open,close}.txt`, per-cell JSON
`screen_results_{next_open,signal_close}.json`. DB reads only (local restored `trading_db` + schema `idx`).

## Data (phase 0, primary source idx.co.id)

| Segment | Source | Coverage |
|---|---|---|
| 2020-01-02 → 2026-09-11 | IDX whole-market day-dumps → `idx.bar`, raw × `adj_factor` (IDX `Previous` resets: splits, rights, bonus; never cash dividends) | 1,610 days, 989 codes incl. 27 delisted/unlisted |
| 2001 → 2019 | Yahoo split-only `close` basis, re-based onto the IDX basis by the median overlap ratio; **rejected when the ratio is > 15 % off** (stale placeholders / missed consolidations: 12 names, e.g. BNBR, COCO, PYFA) | 275 names with pre-2020 history |
| Opens | IDX records opens **before 2025 only for LQ45**; missing opens gap-filled from the Yahoo open rescaled by the same-day close ratio | fills: 77,508 at an open, 462 close-fallback (99 %); open source over all bars: idx 184,700 · yahoo 1,038,101 · none 17,791 |

**Universe** (`research-scratch/idx-screen/universe.json`): Utama + Pengembangan boards (Pemantauan Khusus and
Akselerasi excluded), any trailing-60-day median traded value ≥ Rp 5 bn since 2020 → **451 names** (161
currently liquid; FREN the one delisted name that qualified). 393 screened, 58 skipped (< 750 bars).
**Liquidity gate inside the sleeve:** a new entry is allowed only when the trailing 60-day median value
≥ Rp 5 bn (point-in-time); exits always allowed.

## Method (unchanged platform rules)

Donchian breakout, opposite-channel exit; grid [(20,10),(40,20),(55,20),(100,40)] × {L, LS}; **cost 50 bps
round trip** (25 bps/side charged 2× at exit — IDX retail commission + levy + 0.1 % sales tax); best cell =
max Sharpe among n ≥ 40 cells. **PASS** = PF > 1.2 ∧ Sharpe(252) > 0.35 ∧ n ≥ 40 ∧ |corr BTC| < 0.30 ∧
|corr gold| < 0.30. Additions for IDX: `next_open` fills (signal on close *i*, execution at open *i+1*, gap
risk included), DSR at N = 8 (cells per name) and at **honest N = 3,608** (8 × 451, i.e. picking the best
name after the fact), and a per-name 5-fold expanding walk-forward that selects the cell on the train fold only.

## Result — next-open fills (primary)

| | count |
|---|---|
| Names screened | 393 |
| Names whose best cell has ≥ 40 trades | 83 — best-cell Sharpe quartiles **−0.10 / 0.07 / 0.25**; 49 of 83 positive |
| PASS (certified static gate @ 50 bps) | **12** |
| PASS ∧ DSR@8 ≥ 0.90 ∧ all WF folds positive | **1** (BRPT) |
| PASS ∧ DSR at honest N = 3,608 ≥ 0.90 | **0** |

### The 12 passers

| sym | cfg | side | n | PF | Sharpe | ret % | maxDD % | corrBTC | corrGOLD | DSR@8 | DSR@3608 | WF OOS Sharpe | folds + | div yield* |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| TCPI | 20/10 | LS | 44 | 1.75 | 0.697 | 807 | 68 | +0.03 | +0.05 | 0.697 | 0.052 | **−0.318** | 2/5 | 0.1 % |
| **BRPT** | 20/10 | L | 40 | 5.02 | 0.613 | 6,482 | 60 | +0.01 | +0.03 | **0.952** | 0.314 | 0.550 | **5/5** | 0.5 % |
| ADHI | 20/10 | LS | 90 | 2.55 | 0.503 | 3,714 | 61 | −0.04 | +0.03 | 0.802 | 0.098 | 0.234 | 4/5 | 2.0 % |
| BUMI | 55/20 | LS | 64 | 3.64 | 0.499 | 43,535 | 87 | −0.00 | −0.04 | 0.844 | 0.129 | −0.051 | 2/5 | 0 % |
| ENRG | 40/20 | LS | 50 | 4.33 | 0.458 | 11,089 | 64 | +0.04 | +0.01 | 0.750 | 0.071 | 0.228 | 4/5 | 0 % |
| INCO | 20/10 | L | 70 | 2.52 | 0.457 | 1,693 | 49 | −0.01 | +0.05 | 0.736 | 0.065 | 0.323 | 4/5 | 1.3 % |
| TKIM | 20/10 | LS | 59 | 2.97 | 0.418 | 1,876 | 54 | +0.01 | +0.02 | 0.734 | 0.064 | 0.383 | 3/5 | 0.4 % |
| PGAS | 20/10 | LS | 122 | 2.19 | 0.414 | 1,967 | 65 | −0.01 | −0.02 | 0.691 | 0.050 | −0.000 | 2/5 | 6.2 % |
| TINS | 20/10 | L | 63 | 2.66 | 0.410 | 2,000 | 74 | +0.05 | +0.07 | 0.733 | 0.064 | 0.142 | 2/5 | 3.1 % |
| INKP | 55/20 | LS | 42 | 3.94 | 0.403 | 3,377 | 63 | +0.04 | +0.01 | 0.699 | 0.052 | 0.424 | 4/5 | 0.7 % |
| ANTM | 55/20 | LS | 43 | 2.65 | 0.388 | 599 | 69 | +0.03 | +0.05 | 0.477 | 0.014 | 0.025 | 1/5 | 2.9 % |
| SSIA | 20/10 | LS | 72 | 2.54 | 0.356 | 1,445 | 51 | −0.02 | +0.01 | 0.613 | 0.032 | 0.345 | 3/5 | 1.7 % |

\* Yahoo dividend events, average annual cash yield over the last ~10 years (interim proxy until the IDX
disclosure pipeline, phase 1b). Price return only above; a long-only sleeve is in position ≈ 18–35 % of days,
so the dividend gap is ≤ ~1 %/yr for every passer except PGAS (6.2 % yield, but WF ≈ 0 either way).

### Fill basis

Close fill (the certified reference) gives 14 passers; next-open gives 12. Per name the delta is small and
mostly negative (Sharpe BRPT 0.674 → 0.613, BUMI 0.623 → 0.499, ENRG 0.535 → 0.458; TCPI/PGAS slightly
positive). Gap risk exists but is not what kills the universe — cost and the absence of persistent trend is.
Caveat: 85 % of the open prices used are Yahoo-sourced (IDX itself has opens only for LQ45 before 2025).

### Book-lift (base 4-sleeve book + BRPT, certified `wf_metrics`)

| book | days | Sharpe OOS | DSR@20 | DSR@50 | DSR@100 | maxDD | max\|corr\| |
|---|---|---|---|---|---|---|---|
| BASE (CRYPTO+GOLD+CORN+USDJPY) | 1,967 | 1.183 | 0.768 | 0.639 | 0.541 | 6.9 | 0.176 |
| BASE + BRPT (20/10, L) | 1,867 | **1.477** | **0.909** | 0.831 | 0.759 | 6.8 | 0.178 |

The base reproduces the July certified numbers exactly (1.183 / 0.768). BRPT lifts DSR@20 by +0.141 — more
than NVDA did in July (+0.132) — at unchanged drawdown and correlation.

## Honest reading

1. **The universe has no trend edge at IDX costs.** Among the 83 names with enough trades the median best-cell
   Sharpe is 0.07; only 12 of 393 clear a gate that AAPL/NVDA/1295.KL cleared with room in July. 50 bps
   round trip is roughly 10× the US cost the platform's other equity sleeves pay.
2. **The passers are a survivorship-and-selection story.** BUMI (+43,535 %), ENRG, BRPT (+6,482 %) are the
   historical mega-runs of the exchange, chosen after the fact from 393 names — which is precisely what the
   honest-N DSR (best 0.31) says. Walk-forward confirms it: TCPI, BUMI, PGAS, ANTM go flat or negative out
   of sample.
3. **BRPT is the one name that survives every check except multiplicity**: 40 trades over 24 years, PF 5.0,
   WF 5/5 positive (OOS Sharpe 0.55 — though folds 1 and 4 are ≈ flat at +1.9 % / +4.8 %), DSR@8 0.95, and a
   real book-lift. It is still a single name whose return is dominated by the 2017–2018 run, with a 60 %
   drawdown. Same class of finding as NVDA in July: **admit-candidate, not certifiable by mining**.
4. **Dividends do not change the verdict** (yields ≤ 3 % on the relevant names; PGAS the exception, and PGAS
   fails walk-forward regardless).
5. **Data quality is no longer the limiting factor**: primary source for 2020+, survivorship-free universe,
   splice-checked long history for 275 names, fills at real opens for 99 % of trades.

## Decision (per the build plan gate)

- **Phase 1 gate not met** (no passer at DSR ≥ 0.90 at honest N with 5/5 folds). Phases 2–4 are therefore
  **not justified as trading work**; fundamentals (phase 2) and the nightly loop (phase 3) proceed only as
  thesis-support tooling if the operator wants them.
- **Optional, operator's call:** BRPT 20/10 long-only as a frozen admit-candidate on the paper track
  (operator-in-the-loop, ≥ 60 trading days) — forward evidence being the only honest certification path, as
  with EQ7/EQ6. Recommended sizing if pursued: the same vol-parity slot the base book gives any sleeve; no
  discretionary weight.
- **Not recommended:** lowering the cost assumption, widening the grid, or re-mining until something passes.
  Phase 1b overlays (foreign flow, disclosures) remain worth testing *on BRPT* as conditioning, not as a way to
  rescue the universe.

## Reproduce

```
set -a; source blackheart-ingest/idx-local.env; set +a
blackheart-ingest/.venv/Scripts/python research/test_idx_screen.py          # regression vs certified sleeve
blackheart-ingest/.venv/Scripts/python research/idx_screen.py --fill next_open --top 40
blackheart-ingest/.venv/Scripts/python research/idx_screen.py --fill close --top 40
python research/idx_dividend_proxy.py TCPI,BRPT,ADHI,...
```
