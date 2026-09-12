# Equity Expansion Phase 1 — Donchian Screen + Book-Lift (2026-07-18)

Script: `research/equity_screen.py` (ran on VPS; raw output `/tmp/equity/screen_out.txt`,
full per-cell JSON `/tmp/equity/screen_results.json`). DB reads only; no writes, no restarts.

## Universe / backfill (Stage 1 loaded by prior session — not re-fetched)

| Market | Symbols | Rows in market_data | Range | Notes |
|---|---|---|---|---|
| US | 34 | 195,905 | 2001-07 → 2026-07-17 | ETFs (SPY/QQQ/sectors/bonds/cmdty) + mega-caps; cost 5bps/side |
| SGX | 13 (12 + ^STI screen-only) | 67,798 | 2001-07 → 2026-07-17 | .SI blue chips; cost 15bps/side |
| BURSA | 14 (13 + ^KLSE screen-only) | 69,206 | 2001-07 → 2026-07-17 | .KL large caps; cost 30bps/side |

61 back-adjusted daily OHLC CSVs cached at VPS `/tmp/equity/*.csv`. Loader dropped 63 null-OHLC
rows from ^STI and 97 from ^KLSE. Corr refs: BTCUSDT 3,255 ret-days, XAUUSD 6,272 ret-days
(prod `market_data` 1d).

## Method

Donchian breakout, opposite-channel exit (identical rule to `multi_sleeve_walkforward.py`).
Grid [(20,10),(40,20),(55,20),(100,40)] × {L, LS}; round-trip cost charged at exit.
Best cell = max Sharpe among n≥40 cells.
**PASS** = PF>1.2 ∧ Sharpe(252)>0.35 ∧ n≥40 ∧ |corr BTC|<0.30 ∧ |corr gold|<0.30 (min 200
overlapping in-position days).

## Screen — TOP 20 cells overall (by Sharpe, n≥10)

| sym | mkt | cfg | side | n | PF | Sharpe | ret% | maxDD% | corrBTC | corrGOLD |
|---|---|---|---|---|---|---|---|---|---|---|
| AAPL | US | 20/10 | L | 94 | 4.31 | 1.027 | 17841 | 34 | +0.09 | −0.01 |
| AAPL | US | 100/40 | L | 24 | 15.91 | 0.933 | 16723 | 23 | +0.10 | +0.01 |
| 1295.KL | BURSA | 100/40 | L | 20 | 6.53 | 0.838 | 959 | 27 | −0.03 | +0.04 |
| AAPL | US | 40/20 | L | 54 | 6.93 | 0.825 | 8339 | 33 | +0.12 | −0.01 |
| AAPL | US | 55/20 | L | 53 | 5.83 | 0.728 | 4351 | 34 | +0.12 | −0.01 |
| 1295.KL | BURSA | 40/20 | L | 46 | 4.02 | 0.720 | 681 | 24 | −0.00 | +0.03 |
| 1295.KL | BURSA | 55/20 | L | 41 | 4.09 | 0.706 | 592 | 22 | +0.00 | +0.03 |
| NVDA | US | 55/20 | L | 52 | 4.70 | 0.673 | 17264 | 49 | +0.23 | −0.01 |
| BN4.SI | SGX | 20/10 | L | 73 | 2.97 | 0.655 | 643 | 30 | −0.05 | +0.05 |
| LQD | US | 40/20 | L | 51 | 3.29 | 0.652 | 95 | 8 | +0.06 | +0.17 |
| NVDA | US | 20/10 | L | 100 | 2.94 | 0.649 | 15790 | 53 | +0.18 | +0.02 |
| S68.SI | SGX | 55/20 | L | 47 | 4.63 | 0.644 | 1506 | 44 | −0.09 | +0.07 |
| S68.SI | SGX | 100/40 | L | 25 | 6.46 | 0.644 | 1872 | 38 | −0.03 | +0.07 |
| AAPL | US | 100/40 | LS | 41 | 4.55 | 0.629 | 7876 | 46 | −0.00 | +0.02 |
| NVDA | US | 100/40 | L | 27 | 8.39 | 0.629 | 11361 | 50 | +0.21 | +0.02 |
| S68.SI | SGX | 40/20 | L | 55 | 3.57 | 0.616 | 1450 | 40 | −0.08 | +0.07 |
| D05.SI | SGX | 100/40 | L | 27 | 4.79 | 0.607 | 703 | 25 | +0.02 | +0.06 |
| LQD | US | 55/20 | L | 47 | 3.22 | 0.600 | 79 | 7 | +0.03 | +0.17 |
| NVDA | US | 40/20 | L | 59 | 3.61 | 0.598 | 12729 | 64 | +0.23 | +0.00 |
| ES3.SI | SGX | 100/40 | L | 18 | 3.39 | 0.568 | 136 | 16 | +0.01 | +0.06 |

## Screen — ALL PASSERS (22 of 61; best cell per symbol)

| sym | mkt | cfg | side | n | PF | Sharpe | maxDD% | corrBTC | corrGOLD | PASS |
|---|---|---|---|---|---|---|---|---|---|---|
| AAPL | US | 20/10 | L | 94 | 4.31 | 1.027 | 34 | +0.09 | −0.01 | PASS |
| 1295.KL | BURSA | 40/20 | L | 46 | 4.02 | 0.720 | 24 | −0.00 | +0.03 | PASS |
| NVDA | US | 55/20 | L | 52 | 4.70 | 0.673 | 49 | +0.23 | −0.01 | PASS |
| BN4.SI | SGX | 20/10 | L | 73 | 2.97 | 0.655 | 30 | −0.05 | +0.05 | PASS |
| LQD | US | 40/20 | L | 51 | 3.29 | 0.652 | 8 | +0.06 | +0.17 | PASS |
| S68.SI | SGX | 55/20 | L | 47 | 4.63 | 0.644 | 44 | −0.09 | +0.07 | PASS |
| D05.SI | SGX | 100/40 | LS | 41 | 3.71 | 0.561 | 32 | +0.01 | +0.01 | PASS |
| QQQ | US | 40/20 | L | 61 | 3.11 | 0.530 | 27 | +0.22 | +0.03 | PASS |
| O39.SI | SGX | 55/20 | L | 50 | 2.52 | 0.523 | 32 | +0.04 | +0.04 | PASS |
| XLK | US | 40/20 | L | 62 | 2.71 | 0.465 | 22 | +0.20 | +0.04 | PASS |
| HYG | US | 20/10 | L | 86 | 2.28 | 0.464 | 12 | +0.19 | +0.08 | PASS |
| SPY | US | 20/10 | L | 108 | 1.97 | 0.463 | 28 | +0.24 | +0.08 | PASS |
| USO | US | 40/20 | LS | 83 | 2.79 | 0.455 | 61 | −0.05 | +0.02 | PASS |
| 1155.KL | BURSA | 55/20 | L | 43 | 3.00 | 0.452 | 26 | +0.02 | +0.07 | PASS |
| GOOGL | US | 40/20 | L | 56 | 2.48 | 0.438 | 45 | +0.15 | +0.02 | PASS |
| U11.SI | SGX | 55/20 | L | 47 | 2.51 | 0.423 | 34 | +0.02 | +0.04 | PASS |
| ^STI | SGX | 40/20 | L | 55 | 2.13 | 0.415 | 26 | +0.01 | +0.06 | PASS (screen-only) |
| DIA | US | 20/10 | L | 111 | 1.84 | 0.407 | 25 | +0.20 | +0.05 | PASS |
| EEM | US | 55/20 | L | 48 | 2.83 | 0.396 | 23 | +0.21 | +0.24 | PASS |
| F34.SI | SGX | 20/10 | L | 72 | 2.44 | 0.391 | 37 | +0.04 | +0.04 | PASS |
| XLI | US | 20/10 | L | 106 | 1.81 | 0.383 | 33 | +0.20 | +0.03 | PASS |
| MSFT | US | 40/20 | L | 55 | 2.11 | 0.352 | 34 | +0.15 | +0.00 | PASS |

Top near-misses: **GLD** (Sharpe 0.431, PF 2.85 — edge PASS but corrGOLD +0.89 → redundant
with GOLD sleeve, correctly rejected), **1023.KL** (Sharpe 0.330 < 0.35, orthogonality fine),
**XLY** (Sharpe 0.317 < 0.35). Longer-tail fails were all edge (Sharpe), not orthogonality —
donchian-on-equities corr vs BTC/gold is structurally low.

## Book-lift (OOS 5-fold vol-parity walk-forward; candidates = top-3 tradeable passers)

| book | days | OOS Sharpe | DSR@20 | DSR@50 | DSR@100 | maxDD% | max\|corr\| |
|---|---|---|---|---|---|---|---|
| BASE (CRYPTO+GOLD+CORN+USDJPY) | 1964 | +1.176 | 0.762 | 0.632 | 0.533 | 6.9 | 0.176 |
| BASE + NVDA (55/20, L) | 1963 | **+1.413** | **0.894** | 0.808 | 0.731 | 7.4 | 0.176 |
| BASE + AAPL (20/10, L) | 1963 | +1.260 | 0.816 | 0.700 | 0.606 | 6.6 | 0.176 |
| BASE + 1295.KL (40/20, L) | 1858 | +1.171 | 0.748 | 0.615 | 0.515 | 7.3 | 0.193 |

Baseline reproduced exactly (Sharpe +1.176 / DSR@20 0.762 / maxDD 6.9%).
**Verdicts (DSR@20 0.762 →):** NVDA **0.894 LIFT** (+0.132; Sharpe +1.176→+1.413);
AAPL **0.816 LIFT** (+0.054, maxDD improves to 6.6%); 1295.KL **0.748 NO LIFT** (−0.014,
common-window shrinks and 30bps Bursa cost drags).

## Caveats

- **Survivorship**: universe is today's large caps/ETFs picked in 2026 — AAPL/NVDA best cells
  are partly a survivorship artifact; treat single-name Sharpe as upper bounds.
- **In-sample screen**: the 61-symbol grid is a raw in-sample sweep (488 cells mined → DSR
  trial-tax applies to any single-cell claim); only the book-lift is OOS walk-forward.
- **Yahoo data quality**: back-adjusted closes, splits/dividends per Yahoo; ^STI/^KLSE had
  null-OHLC rows dropped (63/97); indices are screen-only (not directly tradable).
- **Local-ccy returns**: .SI (SGD) and .KL (MYR) P&L is local-currency; no FX overlay.
- **Costs are flat per-side estimates** (US 5 / SGX 15 / Bursa 30 bps); no borrow/short
  availability modeled for LS cells; equity sleeves trade at close, no gap/slippage model.
- BTC corr ref covers only 3,255 days (~2017+), so pre-2017 equity P&L is uncorroborated
  vs crypto; gold corr covers the full window.

**Next step (operator decision)**: BASE+NVDA reaches DSR@20 0.894 — still short of the 0.90
admission gate but the largest single-sleeve jump seen; a 5th+6th sleeve combo test
(NVDA+AAPL, or NVDA+an SGX name for venue diversity) is the obvious Phase 2 cell.
