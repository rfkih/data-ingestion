# IDX menu 33 PRELIM — edge sweep without the taker spread and without the day's drift — 2026-09-22, 2026-09-23

118 names; auction prints: {'close': 364, 'open': 247}. Fees Ajaib/Stockbit 15 + 25 bps. Pre-registered in `research/idx_edge_sweep.py`; 5 trials (cumulative 699).
**Two sessions (one overnight): a direction read, not an adoption.**

## S1 — closing-call premium: close_call / mid_15:49 − 1 (bps)

| day | n | mean | median | t | P(>0) | P(|prem| < 1 bp) | IC OFI last-15 (r, t) | IC TFI last-15 (r, t) |
|---|---|---|---|---|---|---|---|---|
| 2026-09-22 | 118 | -11.5 | -21.4 | -1.99 | 33 % | 3 % | -0.12 (-1.3) | -0.07 (-0.7) |
| 2026-09-23 | 118 | -2.6 | -15.1 | -0.51 | 43 % | 2 % | +0.01 (0.1) | -0.01 (-0.1) |

## S2 — closing-call dislocation → next opening call (bps)

| close day | n | IC (r, t) | overnight all (mean, t) | bottom-quintile prem | its overnight NET of 40 bps (n, mean, median, t, P>0) | top-quintile prem | its overnight (mean) | verdict |
|---|---|---|---|---|---|---|---|---|
| 2026-09-22 | 116 | -0.11 (-1.2) | +39.7 (5.6) | -86.8 | 24, +7.7, -29.7, 0.60, 46 % | +68.6 | +40.4 | no |

## S3 — opening call → intraday (bps)

| day | n | jump 09:00:10 vs call (mean, t) | IC gap→09:15 | IC gap→close | IC jump→09:15 | IC jump→close | gap ≥ +3 % intraday (n, mean) | gap ≤ −3 % intraday (n, mean) |
|---|---|---|---|---|---|---|---|---|
| 2026-09-22 | 108 | +6.9 (1.2) | -0.17 (-1.8) | -0.24 (-2.6) | +0.56 (7.0) | +0.15 (1.6) | 1, -859.4 | 0, - |
| 2026-09-23 | 116 | +5.3 (0.9) | -0.34 (-3.8) | +0.13 (1.4) | +0.44 (5.2) | +0.34 (3.9) | 2, -25.2 | 0, - |

## S4 — market-wide order flow (MKT_OFI5) → EW market mid move (bps)

| day / horizon | n | IC (r, t) | top-decile fwd | bottom-decile fwd |
|---|---|---|---|---|
| 2026-09-22/h5m | 1890 | +0.09 (4.1) | +1.3 | -10.0 |
| 2026-09-22/h15m | 1830 | +0.26 (11.3) | -9.6 | -33.4 |
| 2026-09-23/h5m | 1890 | +0.20 (8.7) | +4.4 | +0.9 |
| 2026-09-23/h15m | 1830 | +0.23 (10.1) | +14.8 | -4.2 |

## S5 — cross-sectional: top-decile OFI5 minus bottom-decile forward mid return, liquid names (spread ≤ 30 bps)

| horizon | day | steps | spread bps (mean) | median | t | P(>0) | top-decile move (ticks) | placebo mean | placebo pct | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| h5m | 2026-09-22 | 0 | - | - | - | - % | - | - | 0 | no |
| h5m | 2026-09-23 | 232 | +14.4 | +7.1 | 5.57 | 62 % | +0.92 | -0.1 | 100 | no |
| h15m | 2026-09-22 | 0 | - | - | - | - % | - | - | 0 | no |
| h15m | 2026-09-23 | 182 | +15.4 | -6.6 | 2.87 | 45 % | +1.94 | +0.3 | 100 | no |

## S6 — execution timing: hit the offer/bid now vs wait for the book (OBI1 ≥ 0.3 & microprice > mid; ≤ 15 min), bps improvement

| side | day | decisions | improvement mean | median | t | P(>0) | placebo (wait a random time) | verdict |
|---|---|---|---|---|---|---|---|---|
| buy | 2026-09-22 | 33,230 | +11.7 | +0.0 | 57.86 | 26 % | +6.0 | CANDIDATE |
| buy | 2026-09-23 | 34,164 | +5.8 | +0.0 | 29.31 | 21 % | -3.7 | CANDIDATE |
| sell | 2026-09-22 | 33,230 | +5.6 | +0.0 | 25.25 | 21 % | -5.7 | CANDIDATE |
| sell | 2026-09-23 | 34,164 | +10.9 | +0.0 | 49.26 | 26 % | +4.2 | CANDIDATE |

## Reading

- Candidates: S6/buy, S6/sell.
- S1/S2/S3 trade at ONE price (the call): no spread, only fees. S5 is market-neutral by construction. S6 is money on trades the desk
  makes anyway. Everything else in menus 28-32 paid the spread and rode the day's drift; this sweep is the complement.
- Re-run at >= 20 sessions.

## Post-hoc checks (not trials; run right after the first read)

- **S3 jump IC was mechanical.** `jump` and `ret_915` share `open_call` as the base, so the +0.56 / +0.44 IC is arithmetic, not prediction.
  Honest read = jump vs the return AFTER the jump (09:00:10 → 09:15): IC +0.07 (t 0.8) / +0.06 (t 0.7). Dead. Gap → post-jump 09:15:
  −0.08 (t −0.9) / −0.20 (t −2.1) = a mild first-15-minute gap reversal, consistent with the gap-fade family.
- **S5 was a filter artefact.** With ≥ 20 liquid names per step 09-22 had no steps and 09-23 only 232; with ≥ 10 names (median 17-18 per step,
  ~1,880 steps/day) the top-minus-bottom OFI5 spread is −5.4 bps (t −4.8) on 09-22 and +3.4 (t +3.5) on 09-23 at 5 min, −2.9 / −5.2 at 15 min.
  Sign flips by day → no cross-sectional alpha in liquid names from OFI5 alone.
- Standing after the checks: **S6 execution timing (both days, beyond the random-wait placebo), S4 market-flow → market 15-min move
  (IC 0.23-0.26, t ≥ 10 both days), S1 closing call clears ~15-20 bps below the last mid (median).**
