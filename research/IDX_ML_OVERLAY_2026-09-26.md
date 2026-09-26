# IDX menu ML-5 — the prediction desk's scores as an overlay on the proven strategies — 2026-09-26 — 10 trials, cumulative N = 741

Walk-forward OOS scores (ML-4) as that day's percentile among LIQ names; every book from 2022-01 with its reference recomputed on the same window.

## A. Trend book (trail-10, K 10, regime gate) — bar: n >= 150, t >= 2, Sharpe >= ref + 0.15, CAGR >= 0.8 ref, mDD not deeper

| arm | n | hold | hit | avg net | t | CAGR | Sharpe | mDD | verdict |
|---|---|---|---|---|---|---|---|---|---|
| plain gated rule (small) | 282 | 26 | 42 % | +4.59 % | 2.7 | +16.3 % | 1.01 | -17 % | reference |
| trend_rank20 (small) | 261 | 28 | 42 % | +3.76 % | 2.1 | +11.2 % | 0.79 | -19 % | no: sharpe 0.79 < ref 1.01 + 0.15; cagr < 80 % ref; mdd deeper |
| trend_filt20 (small) | 222 | 30 | 41 % | +5.08 % | 2.7 | +13.8 % | 1.04 | -22 % | no: sharpe 1.04 < ref 1.01 + 0.15; mdd deeper |
| trend_filt5 (small) | 234 | 28 | 39 % | +3.46 % | 2.1 | +10.2 % | 0.78 | -22 % | no: sharpe 0.78 < ref 1.01 + 0.15; cagr < 80 % ref; mdd deeper |
| plain gated rule (LIQ) | 288 | 27 | 35 % | +0.74 % | 0.6 | +2.0 % | 0.20 | -32 % | reference |
| trend_rank20 (LIQ) | 262 | 30 | 33 % | +0.77 % | 0.5 | +0.7 % | 0.12 | -24 % | no: t<2; sharpe 0.12 < ref 0.20 + 0.15; cagr < 80 % ref |
| trend_filt20 (LIQ) | 239 | 31 | 38 % | +1.78 % | 1.2 | +4.2 % | 0.38 | -26 % | no: t<2 |
| trend_filt5 (LIQ) | 262 | 28 | 38 % | +0.93 % | 0.8 | +3.0 % | 0.28 | -24 % | no: t<2; sharpe 0.28 < ref 0.20 + 0.15 |

## B. Value book (composite_q, May, 2022-05 -> now) — bar: CAGR >= ref + 2 pp, mDD not deeper, periods won > lost

| arm | total | CAGR | Sharpe | mDD | periods (from each May) | verdict |
|---|---|---|---|---|---|---|
| composite_q (deployed rule) | +65.2 % | +12.2 % | 0.67 | 22 % | 22-05:+10 23-05:-4 24-05:+9 25-05:+38 26-05:+4 | reference |
| value_avoid | +31.9 % | +6.5 % | 0.38 | 23 % | 22-05:-6 23-05:-3 24-05:+8 25-05:+30 26-05:+4 | no: cagr 6.5 < ref 12.2 + 2; periods won 1 <= lost 3 |
| value_refill | +34.1 % | +6.9 % | 0.40 | 23 % | 22-05:-2 23-05:-4 24-05:+8 25-05:+27 26-05:+4 | no: cagr 6.9 < ref 12.2 + 2; periods won 0 <= lost 4 |
| value_rerank | +84.3 % | +15.0 % | 0.66 | 31 % | 22-05:-3 23-05:-7 24-05:+4 25-05:+84 26-05:+7 | no: periods won 2 <= lost 3 |

Rebalance log: 2022-05-09: 12 picks, dropped ['ADRO', 'BSSR', 'ITMG', 'TRJA'], rerank in ['BBTN', 'ERAA', 'MNCN', 'SSMS']; 2023-05-02: 12 picks, dropped ['MPMX'], rerank in ['BTPS', 'DSNG', 'INKP', 'TINS']; 2024-05-02: 10 picks, dropped ['ADRO'], rerank in ['BBNI', 'BFIN', 'HATM', 'INDF']; 2025-05-02: 12 picks, dropped ['LSIP', 'TAPG'], rerank in ['AADI', 'ACES', 'BBRI', 'BSDE', 'ENRG']; 2026-05-04: 15 picks, dropped [], rerank in ['ASII', 'LEAD', 'TEBE']

## C. Gap-fade (open <= -7 %, buy open + tick, sell close - tick) — bar: mean >= ref + 30 bps, n >= 100, t >= 3

| arm | events | hit | mean net | t | sleeve CAGR | sleeve Sharpe | sleeve mDD | verdict |
|---|---|---|---|---|---|---|---|---|
| g7 (deployed rule) | 288 | 52 % | +304 bps | 3.0 | +19.5 % | 3.91 | -4 % | reference |
| gf_filt5 | 137 | 53 % | +127 bps | 2.2 | +4.3 % | 4.08 | -2 % | no: mean +127 < ref +304 + 30; t<3 |
| gf_rank5 | 276 | 53 % | +287 bps | 2.8 | +17.5 % | 3.88 | -5 % | no: mean +287 < ref +304 + 30; t<3 |

## Verdict (menu ML-5, study stored)

BETTER overlays: none.
