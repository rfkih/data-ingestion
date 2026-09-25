# IDX menu ML-5 — the prediction desk's scores as an overlay on the proven strategies — 2026-09-24 — 10 trials, cumulative N = 741

Walk-forward OOS scores (ML-4) as that day's percentile among LIQ names; every book from 2022-01 with its reference recomputed on the same window.

## A. Trend book (trail-10, K 10, regime gate) — bar: n >= 150, t >= 2, Sharpe >= ref + 0.15, CAGR >= 0.8 ref, mDD not deeper

| arm | n | hold | hit | avg net | t | CAGR | Sharpe | mDD | verdict |
|---|---|---|---|---|---|---|---|---|---|
| plain gated rule (small) | 266 | 27 | 42 % | +5.88 % | 3.1 | +20.1 % | 1.24 | -18 % | reference |
| trend_rank20 (small) | 263 | 28 | 43 % | +5.22 % | 2.8 | +17.4 % | 1.13 | -23 % | no: sharpe 1.13 < ref 1.24 + 0.15; mdd deeper |
| trend_filt20 (small) | 226 | 30 | 41 % | +4.92 % | 2.4 | +12.6 % | 0.91 | -27 % | no: sharpe 0.91 < ref 1.24 + 0.15; cagr < 80 % ref; mdd deeper |
| trend_filt5 (small) | 239 | 28 | 40 % | +4.48 % | 2.4 | +13.3 % | 0.96 | -18 % | no: sharpe 0.96 < ref 1.24 + 0.15; cagr < 80 % ref; mdd deeper |
| plain gated rule (LIQ) | 278 | 28 | 36 % | +1.14 % | 0.9 | +3.3 % | 0.29 | -28 % | reference |
| trend_rank20 (LIQ) | 258 | 30 | 36 % | +1.14 % | 0.8 | +1.8 % | 0.20 | -27 % | no: t<2; sharpe 0.20 < ref 0.29 + 0.15; cagr < 80 % ref |
| trend_filt20 (LIQ) | 240 | 30 | 39 % | +3.49 % | 1.9 | +8.8 % | 0.68 | -28 % | no: t<2 |
| trend_filt5 (LIQ) | 261 | 29 | 37 % | +1.45 % | 1.0 | +3.8 % | 0.32 | -26 % | no: t<2; sharpe 0.32 < ref 0.29 + 0.15 |

## B. Value book (composite_q, May, 2022-05 -> now) — bar: CAGR >= ref + 2 pp, mDD not deeper, periods won > lost

| arm | total | CAGR | Sharpe | mDD | periods (from each May) | verdict |
|---|---|---|---|---|---|---|
| composite_q (deployed rule) | +67.8 % | +12.6 % | 0.69 | 23 % | 22-05:+10 23-05:-4 24-05:+9 25-05:+38 26-05:+5 | reference |
| value_avoid | +34.0 % | +6.9 % | 0.41 | 23 % | 22-05:-6 23-05:-4 24-05:+8 25-05:+30 26-05:+6 | no: cagr 6.9 < ref 12.6 + 2; mdd deeper; periods won 1 <= lost 4 |
| value_refill | +36.9 % | +7.4 % | 0.44 | 22 % | 22-05:-2 23-05:-4 24-05:+10 25-05:+27 26-05:+4 | no: cagr 7.4 < ref 12.6 + 2; mdd deeper; periods won 1 <= lost 4 |
| value_rerank | +101.2 % | +17.3 % | 0.76 | 30 % | 22-05:-3 23-05:-4 24-05:+6 25-05:+89 26-05:+7 | no: periods won 2 <= lost 3 |

Rebalance log: 2022-05-09: 12 picks, dropped ['ADRO', 'BSSR', 'ITMG', 'TRJA'], rerank in ['BBTN', 'ERAA', 'MNCN', 'SSMS']; 2023-05-02: 12 picks, dropped [], rerank in ['ERAA', 'INKP', 'JPFA', 'TINS']; 2024-05-02: 10 picks, dropped ['ADRO'], rerank in ['BBNI', 'BFIN', 'ENRG', 'INDF']; 2025-05-02: 12 picks, dropped ['LSIP', 'TAPG'], rerank in ['AADI', 'BBRI', 'BSDE', 'ENRG']; 2026-05-04: 15 picks, dropped ['LSIP', 'SRTG'], rerank in ['ASII', 'ELSA', 'ITMG', 'PTBA', 'SIDO', 'TEBE']

## C. Gap-fade (open <= -7 %, buy open + tick, sell close - tick) — bar: mean >= ref + 30 bps, n >= 100, t >= 3

| arm | events | hit | mean net | t | sleeve CAGR | sleeve Sharpe | sleeve mDD | verdict |
|---|---|---|---|---|---|---|---|---|
| g7 (deployed rule) | 288 | 52 % | +304 bps | 3.0 | +19.5 % | 3.91 | -4 % | reference |
| gf_filt5 | 149 | 57 % | +320 bps | 2.3 | +10.2 % | 3.65 | -3 % | no: mean +320 < ref +304 + 30; t<3 |
| gf_rank5 | 276 | 51 % | +284 bps | 2.8 | +17.1 % | 3.48 | -5 % | no: mean +284 < ref +304 + 30; t<3 |

## Verdict (menu ML-5, study stored)

BETTER overlays: none.

## Correction (2026-09-25, after study #157)

The trend-book CAGRs in section A come from idx_exit.stats, which divides by the FULL panel span (2020-01 -> 2026-09) even though
these books only trade from 2022-01; they are understated by the same factor for the reference and every arm, so the verdicts
(relative) stand, but the absolute number is wrong. On daily returns from 2022-01 the plain gated rule (small) is +28.5 %/yr,
Sharpe 1.49, mDD -18 % (study #157), consistent with the full-span 32.0 % / 1.54 / -18 %.
