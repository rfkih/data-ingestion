# IDX menu ML-7b — lambdarank 5d through the cost-aware book — 2026-09-25 — 5 trials, cumulative N = 826

Same universe (LIQ), costs, panel, walk-forward years and position book as ML-6 (`idx_ml_costaware.book`); the score is the 3-seed lambdarank 5d percentile gap scaled by the training years' decile spread. References e5|... are ML-6's arms recomputed here.

## Ranking accuracy on this universe: daily rank IC on LIQ vs the 5d return (t) | churn = day-to-day rank corr

| year | lr5 | s5 (deployed regression) |
|---|---|---|
| 2022 | 0.126 (24.9) c0.66 | 0.085 (14.0) c0.74 |
| 2023 | 0.124 (19.7) c0.77 | 0.100 (16.0) c0.74 |
| 2024 | 0.086 (13.6) c0.60 | 0.074 (10.5) c0.69 |
| 2025 | 0.119 (17.1) c0.61 | 0.055 (7.3) c0.75 |
| 2026 | 0.106 (11.4) c0.69 | 0.050 (3.5) c0.76 |

## The book

| arm (score, margin, ema, K) | trades | hold d | turns/yr/slot | CAGR | Sharpe | mDD | years + | by year | verdict |
|---|---|---|---|---|---|---|---|---|---|
| e5|2|3|10 | 445 | 25 | 9.4 | +32.7 % | 0.99 | -51 % | 4/5 | 22:-14 23:+37 24:+29 25:+83 26:+36 | reference |
| e5|2|3|5 | 225 | 25 | 9.5 | +47.3 % | 1.13 | -59 % | 4/5 | 22:-34 23:+117 24:+48 25:+63 26:+79 | reference |
| lr5|2|3|10 | 368 | 31 | 7.8 | +14.5 % | 0.60 | -52 % | 3/5 | 22:-10 23:+0 24:+6 25:+137 26:-16 | not a candidate: sharpe 0.60 < 1.2; mdd -52 % < -25 %; 3/5 years positive | not better than ML-6 ref |
| lr5|2|3|5 | 161 | 35 | 6.8 | +22.5 % | 0.78 | -49 % | 4/5 | 22:-0 23:+11 24:+10 25:+108 26:+3 | not a candidate: sharpe 0.78 < 1.2; mdd -49 % < -25 % | not better than ML-6 ref |
| lr5|1|3|10 | 368 | 31 | 7.8 | +14.5 % | 0.60 | -52 % | 3/5 | 22:-10 23:+0 24:+6 25:+137 26:-16 | not a candidate: sharpe 0.60 < 1.2; mdd -52 % < -25 %; 3/5 years positive | not better than ML-6 ref |
| lr5|2|1|10 | 805 | 14 | 17.0 | +25.0 % | 0.86 | -45 % | 4/5 | 22:-1 23:+1 24:+5 25:+140 26:+14 | not a candidate: sharpe 0.86 < 1.2; mdd -45 % < -25 % | not better than ML-6 ref |
| lrblend|2|3|10 | 364 | 31 | 7.7 | +26.7 % | 0.90 | -47 % | 3/5 | 22:-11 23:+21 24:+34 25:+129 26:-7 | not a candidate: sharpe 0.90 < 1.2; mdd -47 % < -25 %; 3/5 years positive | not better than ML-6 ref (placebo pct 100) |

## Verdict (menu ML-7b, study stored)

Best arm: **lrblend|2|3|10** (+26.7 %/yr, Sharpe 0.90, mDD -47 %, hold 31 d) - not a candidate: sharpe 0.90 < 1.2; mdd -47 % < -25 %; 3/5 years positive | not better than ML-6 ref.
CANDIDATES (ML-6 bar): none. BETTER than the ML-6 reference with the same K: none.

## Reading (written after the run)

- The ranker is more accurate and the book is worse: rank IC on LIQ 0.086-0.126 vs 0.050-0.100 (5/5 years), yet K 10 earns
  14.5 %/yr Sharpe 0.60 against the regression's 32.7 %/0.99, K 5 22.5 %/0.78 against 47.3 %/1.13.
- Why: the cost-aware book needs a MAGNITUDE - "is this name's expected excess worth 2x its round trip today?" - and a
  lambdarank score has none. Expressed as a percentile gap x a constant spread (the ML-6 rank5 construction) every day
  looks the same to the book: margin 1 and margin 2 give identical books (368 trades, same P&L), i.e. the cost threshold
  never binds and the arm degenerates into a plain top-K rank book with a 31-day hold. The regression score's edge is not
  its ordering but its calibration of WHEN and by HOW MUCH - days and names with a large expected excess.
- Blending the two expectations (lrblend) also loses to the regression alone (26.7 %/0.90 vs 32.7 %/0.99): the ranker's
  magnitude-free term dilutes the calibrated one.
- The references recomputed here (32.7 %/0.99/-51 % K 10; 47.3 %/1.13/-59 % K 5) sit above the numbers quoted from ML-6
  (29.1/0.91/-51; 41.6/1.04/-61): same cache, same book - the ML-6 figures were printed by an earlier pass of the same
  script; the relative verdict is what this study is for.
- Not tried, and the only construction that could still use the ranker: order by lambdarank, gate the entry by the
  regression's bps (two models, one book). That is a new trial, not this one.
