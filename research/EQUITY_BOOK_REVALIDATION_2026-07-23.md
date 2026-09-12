# Frozen-Book Revalidation Backtest — 2026-07-23 (pre-Alpaca-KYC checkpoint)

**Question:** before the operator creates an Alpaca account, do the two books frozen in
`portfolio_book` (V213 seed, 2026-07-19) still validate on refreshed data?

**Design:** pre-registered replay — the books are evaluated **exactly as frozen** (sleeve
symbols, donchian entry/exit periods, long-only flags, per-venue costs from the seeded JSONB
config). Zero re-mining, zero parameter search. Engine identical to Phase-1
(`/tmp/equity/equity_screen.py`): donchian breakout / opposite-channel exit, costs per side
(US 5bps, SGX 15bps, base sleeves 8bps, charged 2x at exit), 5-fold OOS vol-parity
walk-forward (first ⅓ warmup), DSR ladder @ {20, 50, 100, 488} trials.

**Data:** refreshed 2026-07-23 — `ZC=F`/`JPY=X` newly backfilled to prod `market_data` and
caches rebuilt through 2026-07-22/21; `XAUUSD` topped up through 07-22; crypto live-fed;
US/SGX equity CSVs through 07-17 (3 stale trading days, immaterial). In-flight 07-23 partial
bars excluded everywhere (sessions were open at run time).

## Results

Baseline reproduction: **OK** — BASE4 got Sharpe 1.183 / DSR@20 0.768 vs Phase-1's
1.176 / 0.762 (tol 0.03). The engine + refreshed data reproduce the Phase-1 numbers.

| Book (frozen) | OOS window | Sharpe | Ann ret | DSR@20 | DSR@488 | maxDD | folds+ | Sh 3y | Sh 1y |
|---|---|---|---|---|---|---|---|---|---|
| BASE4 (crypto+gold+corn+USDJPY) | 2017-09→2026-07 | 1.183 | +7.1%/yr | 0.768 | 0.340 | 6.9% | 4/5 | 0.689 | 0.804 |
| **EQ7_AGGRESSIVE** (+NVDA+Keppel+LQD) | 2017-09→2026-07 | **1.719** | **+7.4%/yr** | **0.971** | 0.775 | **5.7%** | **5/5** | **1.431** | **2.107** |
| **EQ6_SURVSAFE** (+XLK+LQD) | 2017-09→2026-07 | 1.399 | +5.9%/yr | 0.888 | 0.528 | **4.1%** | **5/5** | 1.144 | 1.669 |

Per-sleeve solo (frozen params, full history): NVDA Sh 0.67 PF 4.7 · Keppel 0.66 PF 2.97 ·
LQD 0.65 PF 3.28 mDD 7.7% · CRYPTO pool 0.55 · XLK 0.47 · CORN 0.39 PF 2.63 ·
GOLD 0.37 PF 2.42 · USDJPY 0.31 PF 2.05. Max pairwise |corr| inside EQ7: 0.244.

**No decay:** both books' last-3y and last-1y OOS Sharpe are *above* their full-window
Sharpe (EQ7: 1.43 / 2.11 vs 1.72 full — fold P&L [9.6, 6.7, 5.5, 6.4, 9.4]% is remarkably
even). The edge is not a 2001-2010 artifact.

## Honest caveats (unchanged from Phase-1, restated)

1. **Multiplicity:** at honest N=488 mined cells, nothing clears DSR 0.90 (EQ7 best at
   0.775). The @20 pass is conditional on treating the frozen books as the hypothesis.
   ⇒ certification path remains **forward paper evidence**, which is multiplicity-free.
2. **Survivorship:** NVDA/Keppel are history's winners chosen post-hoc; EQ6_SURVSAFE
   (no single names) is the survivorship-safer twin — paper-run BOTH.
3. Ann. return ~7%/yr is unlevered vol-parity at low vol (maxDD 5.7%); sizing/leverage is
   a later, separate decision.
4. `JPY=X` has no 2026-07-22 bar at the source (Yahoo gap); no recurring EOD feed exists
   yet for non-crypto symbols — must be wired before PAPER.

## Verdict

**PROCEED to Alpaca signup.** The frozen books reproduce exactly, show zero recency decay,
and 5/5 positive folds each. The backtest cannot by construction clear the honest-N gate —
only forward paper track record can — so the next evidence gain requires the paper account.
Paper trading needs signup only (no funding, no capital at risk).

*Artifacts:* `research/reval_results_2026-07-23.json` (local copy),
`/tmp/equity/reval_results.json` + `book_reval` runner via `.rtmp/book_reval_20260723.py`;
cache backups `/tmp/equity/{ZC_F,JPY_X}.csv.bak0718.*
