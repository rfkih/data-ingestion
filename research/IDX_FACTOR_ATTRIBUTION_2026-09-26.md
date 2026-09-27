# Alpha or small-cap beta? Factor attribution of the combined book (#386) - 2026-09-26

Daily returns 2022-01-04 -> 2026-09-16 (1123 sessions). Factors: COMPOSITE, small-cap spread (IDXSMC-LIQ - COMPOSITE),
momentum (top-minus-bottom decile of liquid names by 120-day return). Newey-West (5 lags). Alpha annualised (x 252, arithmetic). Audit, no trial.

| series | raw mean /yr | M1 alpha /yr (t) | M2 alpha /yr (t) | M3 alpha /yr (t) | beta mkt | beta small-cap | beta momentum | R2 (M3) |
|---|---|---|---|---|---|---|---|---|
| combined | +44.0 % | +43.6 % (4.75) | +44.2 % (4.80) | +40.6 % (4.57) | 0.52 | 0.31 | 0.12 | 0.21 |
| gap_only | +11.4 % | +11.4 % (2.82) | +11.3 % (2.80) | +11.1 % (2.79) | 0.07 | -0.02 | 0.01 | 0.02 |
| trend_only | +13.2 % | +13.1 % (2.25) | +13.3 % (2.30) | +10.8 % (2.01) | 0.20 | 0.13 | 0.08 | 0.14 |
| ml_only | +28.7 % | +28.5 % (3.65) | +28.9 % (3.71) | +26.4 % (3.61) | 0.31 | 0.19 | 0.08 | 0.13 |

Reading: the combined book keeps +40.6 %/yr of alpha (t 4.57) after the market, small caps and
momentum, which explain R2 = 0.21 of its daily variance. The return is NOT mainly factor beta.

Limits: in-sample 2022-26 like everything else (this separates alpha from beta, it does not prove persistence); arithmetic
alpha differs from the geometric CAGR; the momentum factor is equal-weight and gross of costs; no value or liquidity factor.
