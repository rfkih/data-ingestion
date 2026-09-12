# Research Plan — L2 Order-Book Liquidity-Provision Reversion (1h) — 2026-07-15

**Status:** PRE-REGISTERED, DATA-GATED (queue-ready ~Sept-Oct 2026). Do NOT queue before the
maturity gate below is met. This is the queue-ready design so it can be dropped straight into the
tick loop the moment `ob_*` history is deep enough.

## Motivation / mechanism (pre-registered, from a MEASURED prior)
The 2026-07-15 OFI/CVD paper (`RESEARCH_PAPER_ORDERFLOW_OFI_CVD_MULTI_15M_v1_CHAR_2026-07-15.md`)
found intraday **directional** order-flow scalping NULL across 54 cells / 903k bars, BUT measured a
small, significant **negative** reversion IC (~−0.03, survives a +1-bar lag): pushes into thin
liquidity **mean-revert**. That is the liquidity-provision premium — the compensation a passive
maker earns for absorbing flow. The hypothesis here is that **L2 book imbalance** (not candle-proxy
OFI) is a cleaner instantaneous read of that thin-liquidity state, so conditioning entries on the
book imbalance extreme should harvest the reversion the OFI proxy could only weakly see.

## Signal (already accruing — verified 2026-07-15)
`feature_values`, hourly, BTC + ETH (global-keyed, symbol encoded in the name):
- `ob_imbalance_btc` / `ob_imbalance_eth` — top-of-book bid/ask size imbalance.
- `ob_imbalance_momentum_8h_btc` / `_eth` — 8h change in imbalance.
- `ob_spread_bps_btc` / `ob_spread_bps_eth` — top-of-book spread (bps), the liquidity-thinness gauge.
Source: `binance_orderbook` worker (`blackheart-ingest/.../sources/binance_orderbook.py`), V137
registry. Confirmed live: rows current to 2026-07-15, ~1050 rows/feature.

## ★ Maturity gate (the DATA-GATED blocker)
As of 2026-07-15 history = **2026-06-01 → 2026-07-15 (~6 weeks, ~1050 hourly obs)**. Too thin for a
walk-forward-clean 1h backtest (n_trades would fall far short of the V11 n≥100 with any selective
gate, and there is no multi-regime span). **Queue only when ≥ ~4-6 months of `ob_*` history exists
(≈ 2026-10 to 2026-12)** — enough for ≥2 non-overlapping WF folds and n≥100 selective entries.
Re-check with: `SELECT MIN(ts), MAX(ts), COUNT(*) FROM feature_values WHERE feature_name='ob_spread_bps_btc';`

## Design (falsifiable, pre-registered)
- **Universe/interval:** BTCUSDT + ETHUSDT, 1h (the cadence the features are computed at).
- **Entry (reversion):** fade a book-imbalance extreme in a thin book. LONG when `ob_imbalance`
  is in its bottom decile (heavy ask/sell pressure) AND `ob_spread_bps` is elevated (thin book);
  SHORT mirror on the top decile. Gate thresholds pre-registered as z-score bands (|z|≥1.5), NOT
  tuned on the test window.
- **Lag discipline:** entry uses the PREVIOUS closed 1h bar's `ob_*` value (ts ≤ entry − 1h). The
  OFI reversion IC only survived the +1-bar lag, so a same-bar read is banned (look-ahead guard).
- **Exit:** short horizon (reversion decays fast) — fixed R (tpR 1.0–1.5) + ATR stop, maxBarsHeld
  ~8–24h. This is a maker-style edge; test BOTH taker-cost and post-only-maker-fee assumptions.
- **Cost realism:** the OFI scalp died on cost. Pre-register a HARD net-of-cost bar: PF-CI-low > 1.0
  at taker cost is the pass; if it only passes at maker fees, flag as maker-conditional (execution
  risk — non-guaranteed fills).

## Discovery-cost ladder (per platform playbook §1.9)
1. **IC screen first** (`POST /signal-screen`, Spearman IC + Newey-West t) on `ob_imbalance` →
   forward 1h return, once history ≥ 3 months. REQUIRED before any confirmatory sweep.
2. Null-screen → confirmatory sweep → walk-forward, only if the IC screen shows a stable
   (sign-consistent) reversion IC.

## Kill criteria (do not resurrect on a re-sweep)
- IC screen shows no stable-sign reversion IC at 1h → DEAD (the 15m OFI proxy already hinted weak).
- Passes gross but PF-CI-low < 1.0 at taker cost AND fills are not credibly maker-achievable at
  ~$191 live (VIP0) → shelve as capital/execution-gated, not a deployable edge.

## Honest caveats
- At ~$191 live / VIP0 fees, a maker-style intraday edge is economically symbolic today — this is a
  "build the track record, pays as capital + fee tier grow" candidate, aligned with the risk-parity
  accumulation endgame, NOT a near-term return engine.
- Only the non-falsified continuous intraday mechanism left after the OFI/CVD NULL — worth the
  cheap IC screen once data matures, low priority until then.
