# IDX menu 23 — re-open the gate on an oversold market — 2026-09-22 — 5 trials, cumulative N = 450

Entries allowed when COMPOSITE >= MA200 at the signal close OR the oversold condition holds; `small`, deployed rule otherwise. allow-under = share of regime-off days on which the arm allows entries.

| arm | allow-under | trades | hit | avg net | t | CAGR | Sharpe | mDD | years | read / money |
|---|---|---|---|---|---|---|---|---|---|---|
| ungated (deployed) | 100 % | 496 | 42 % | +4.10 % | 3.4 | +29.5 % | 1.31 | -30 % | 20:+24 21:+65 22:+29 23:-5 24:+1 25:+131 26:-8 | reference |
| regime_gate | 0 % | 381 | 44 % | +6.30 % | 3.9 | +32.1 % | 1.54 | -18 % | 20:+23 21:+65 22:+24 23:-3 24:+5 25:+147 26:-5 | reference |
| os_rsi30 | 9 % | 390 | 44 % | +6.08 % | 3.9 | +32.0 % | 1.53 | -21 % | 20:+23 21:+65 22:+27 23:-2 24:+2 25:+145 26:-5 | no: cagr<gate+2 / CANDIDATE (rnd Sharpe 0.50) |
| os_rsi30_20d | 38 % | 435 | 42 % | +4.93 % | 3.4 | +28.5 % | 1.35 | -31 % | 20:+23 21:+65 22:+30 23:-7 24:+0 25:+115 26:-5 | no: cagr<gate+2,mdd>25%,sharpe<gate-0.05 / tested: mdd>25% (rnd Sharpe 0.01) |
| os_rsi30_latch | 72 % | 471 | 41 % | +4.16 % | 3.1 | +26.9 % | 1.23 | -31 % | 20:+24 21:+60 22:+30 23:-2 24:+1 25:+99 26:-9 | no: cagr<gate+2,mdd>25%,sharpe<gate-0.05 / tested: mdd>25% (rnd Sharpe 0.40) |
| os_bounce5 | 40 % | 441 | 42 % | +4.57 % | 3.6 | +29.9 % | 1.39 | -23 % | 20:+24 21:+60 22:+24 23:-7 24:+7 25:+122 26:-0 | no: cagr<gate+2,sharpe<gate-0.05 / CANDIDATE (rnd Sharpe 0.49) |
| os_ma50 | 30 % | 423 | 43 % | +5.21 % | 3.9 | +32.6 % | 1.50 | -18 % | 20:+25 21:+68 22:+24 23:+5 24:+5 25:+108 26:+4 | no: cagr<gate+2 / CANDIDATE (rnd Sharpe 0.92) |

Reading rule applied as declared: 0 of 5 recover the rebound.

## 2005-2019 (`small`, Yahoo survivors file, JKSE regime)

| arm | trades | hit | avg net | t | CAGR | Sharpe | mDD | years | 2009 | 2012 |
|---|---|---|---|---|---|---|---|---|---|---|
| ungated | 612 | 41 % | +3.64 % | 4.2 | +13.3 % | 0.89 | -27 % | 05:+5 06:+41 07:+30 08:-10 09:+26 10:+20 11:+8 12:+20 13:+24 14:+7 15:-15 16:+36 17:+19 18:-4 19:+2 | +26 % | +20 % |
| gate | 554 | 43 % | +4.12 % | 4.5 | +14.2 % | 0.96 | -19 % | 05:+3 06:+41 07:+30 08:-3 09:+14 10:+20 11:+8 12:+13 13:+22 14:+10 15:-6 16:+41 17:+19 18:+7 19:+0 | +14 % | +13 % |
| os_rsi30 | 556 | 43 % | +4.06 % | 4.5 | +14.0 % | 0.95 | -19 % | 05:+3 06:+41 07:+30 08:-3 09:+14 10:+20 11:+8 12:+13 13:+23 14:+10 15:-8 16:+40 17:+19 18:+7 19:+0 | +14 % | +13 % |
| os_rsi30_20d | 576 | 41 % | +3.73 % | 4.2 | +13.0 % | 0.89 | -27 % | 05:+4 06:+41 07:+30 08:-8 09:+12 10:+20 11:+8 12:+20 13:+21 14:+9 15:-15 16:+40 17:+19 18:+3 19:+2 | +12 % | +20 % |
| os_rsi30_latch | 599 | 41 % | +3.66 % | 4.2 | +13.1 % | 0.88 | -28 % | 05:+4 06:+41 07:+30 08:-9 09:+24 10:+20 11:+8 12:+20 13:+20 14:+10 15:-15 16:+36 17:+19 18:-4 19:+2 | +24 % | +20 % |
| os_bounce5 | 593 | 41 % | +3.92 % | 4.4 | +14.1 % | 0.94 | -26 % | 05:+4 06:+41 07:+30 08:-10 09:+26 10:+20 11:+8 12:+20 13:+28 14:+9 15:-7 16:+36 17:+19 18:-3 19:-2 | +26 % | +20 % |
| os_ma50 | 586 | 42 % | +4.06 % | 4.6 | +14.6 % | 0.97 | -25 % | 05:+4 06:+41 07:+30 08:-5 09:+26 10:+20 11:+8 12:+13 13:+27 14:+11 15:-7 16:+37 17:+19 18:-2 19:+3 | +26 % | +13 % |

## Reading (written after the run)

0 of 5 clear the declared bar (CAGR >= regime_gate + 2 points with the drawdown kept). The idea splits cleanly by what "oversold" means:

1. **RSI oversold on the index is not the bottom.** Re-opening for 20 days after RSI14 <= 30, or until the next cross above MA200 (latch), gives
   the whole protection back (mDD −31 %, Sharpe 1.35 / 1.23 against the gate's 1.54 / −18 %) and does not even catch 2009 better (12 % / 24 %
   against the gate's 14 % and the ungated 26 %). A bear market prints several oversold readings before its low; the first one is a trap.
   The one-day version (RSI <= 30 on the day) allows only 9 % of the regime-off days and is the gate with noise.
2. **A 5 % bounce off the 60-day low** is in between: it catches 2009 (+26 %) and 2012 (+20 %) but returns the drawdown to −23 % / −26 % with
   a lower Sharpe than the gate in both periods.
3. **"The short trend has turned" (COMPOSITE >= MA50 while still under MA200) is the only re-opening that keeps the gate's protection in
   2020-26** (CAGR 32.6 %, Sharpe 1.50, mDD −18 % — the gate's own numbers) **and recovers the 2009 rebound in full** (+26 %); over 2005-19 it has
   the best CAGR and Sharpe of the family (14.6 %, 0.97) at a drawdown of −25 % against the gate's −19 %. That is the price of being in earlier:
   some MA50 crosses are false bottoms (2008, 2015). Below the declared bar (+0.5 / +0.4 points of CAGR, not +2), so not "recovered", but it is
   the version to prefer if the operator wants the rebound more than the last six points of drawdown.

The picture across menus 21-23: the regime lever is real, the choice inside it is a risk preference — `regime_gate` (MA200 only) for the
shallowest drawdown, `os_ma50` (MA200 or MA50) for the same return profile with the rebound caught and a drawdown around −25 %.
