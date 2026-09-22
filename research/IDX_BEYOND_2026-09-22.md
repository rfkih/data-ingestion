# IDX menu 21 — beyond the two engines: sizing, combination, sector rotation, allocation — 2026-09-22 — 18 trials, cumulative N = 428

Incumbents: value = strict composite, May, rev. 3 (18-22 %/yr, mDD 22-25 %); trend = hi60 / > MA200 / vol >= 1.5x / trail10, K = 10, `small` (+29.9 %/yr, Sharpe 1.34, mDD -30 % to 2026-09-16). Everything below is measured with the same engines, costs and reading rules as menus 6-20.

## A. Position sizing on the trend sleeve (10 trials)

Only the slot size changes; entry, exit, book, costs, execution as deployed. voltarget / regime_half scale the whole book from the prior close (trade statistics are then the reference's; the book numbers change). Random = random entries with the same sizing and exit.

### Universe `small` (deployed: paper_trend, trend_live)

| arm | trades | hold d | hit | avg net | payoff | t | CAGR | Sharpe | mDD | years | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **equal 1/K** (deployed) | 496 | 24 | 42 % | +4.10 % | 2.38 | 3.4 | +29.5 % | 1.31 | -30 % | 20:+24 21:+65 22:+29 23:-5 24:+1 25:+131 26:-8 | reference |
| random + trail10 | 494 | 31 | 35 % | +2.54 % | 2.68 | 2.1 | +14.5 % | 0.70 | -57 % | 20:+93 21:+38 22:-15 23:-3 24:-20 25:+35 26:+2 | reference |
| invvol | 492 | 24 | 40 % | +3.47 % | 2.30 | 2.9 | +15.7 % | 0.89 | -33 % | 20:+23 21:+39 22:+15 23:-9 24:-2 25:+65 26:-12 | no: sharpe<ref+0.15,cagr<80%ref,mdd deeper / tested: sharpe<1,mdd>25%,years<5,vs random (rnd Sharpe 0.93) |
| risk1 | 474 | 24 | 41 % | +4.24 % | 2.41 | 3.4 | +26.1 % | 1.22 | -33 % | 20:+27 21:+63 22:+20 23:-10 24:+7 25:+120 26:-15 | no: sharpe<ref+0.15,mdd deeper / tested: mdd>25% (rnd Sharpe -0.04) |
| voltarget | 496 | 24 | 42 % | +4.10 % | 2.38 | 3.4 | +23.4 % | 1.26 | -24 % | 20:+22 21:+40 22:+29 23:-5 24:+1 25:+99 26:-8 | no: sharpe<ref+0.15,cagr<80%ref / CANDIDATE (rnd Sharpe 0.55) |
| regime_half | 496 | 24 | 42 % | +4.10 % | 2.38 | 3.4 | +29.2 % | 1.41 | -22 % | 20:+22 21:+63 22:+24 23:-8 24:+6 25:+127 26:-4 | no: sharpe<ref+0.15 / CANDIDATE (rnd Sharpe 0.83) |
| pyramid | 496 | 24 | 31 % | +0.68 % | 2.42 | 0.6 | +20.5 % | 1.15 | -24 % | 20:+21 21:+48 22:+14 23:-2 24:-2 25:+88 26:-10 | no: t<2,sharpe<ref+0.15,cagr<80%ref / tested: t<2.5,years<5 (rnd Sharpe 0.47) |

### Universe `LIQ`

| arm | trades | hold d | hit | avg net | payoff | t | CAGR | Sharpe | mDD | years | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **equal 1/K** (deployed) | 480 | 27 | 38 % | +3.10 % | 2.51 | 2.5 | +19.1 % | 0.92 | -36 % | 20:+32 21:+83 22:-4 23:-12 24:+12 25:+76 26:-22 | reference |
| random + trail10 | 458 | 33 | 34 % | +1.12 % | 2.26 | 1.1 | +3.2 % | 0.25 | -50 % | 20:+65 21:+8 22:-11 23:+4 24:-23 25:+52 26:-36 | reference |
| invvol | 466 | 27 | 38 % | +3.05 % | 2.48 | 2.4 | +11.4 % | 0.68 | -34 % | 20:+26 21:+47 22:-6 23:-10 24:+10 25:+40 26:-16 | no: sharpe<ref+0.15,cagr<80%ref / tested: t<2.5,sharpe<1,mdd>25%,years<5,vs random (rnd Sharpe 0.39) |
| risk1 | 469 | 27 | 36 % | +2.15 % | 2.37 | 1.9 | +13.1 % | 0.71 | -35 % | 20:+27 21:+65 22:-13 23:-16 24:+9 25:+57 26:-14 | no: t<2,sharpe<ref+0.15,cagr<80%ref / tested: t<2.5,sharpe<1,mdd>25%,years<5,vs random (rnd Sharpe 0.63) |
| voltarget | 480 | 27 | 38 % | +3.10 % | 2.51 | 2.5 | +12.9 % | 0.77 | -31 % | 20:+28 21:+46 22:-5 23:-13 24:+11 25:+55 26:-18 | no: sharpe<ref+0.15,cagr<80%ref / tested: sharpe<1,mdd>25%,years<5 (rnd Sharpe 0.19) |
| regime_half | 480 | 27 | 38 % | +3.10 % | 2.51 | 2.5 | +21.9 % | 1.13 | -27 % | 20:+30 21:+83 22:-7 23:-8 24:+17 25:+79 26:-16 | BETTER / tested: mdd>25%,years<5 (rnd Sharpe 0.44) |
| pyramid | 480 | 27 | 29 % | +0.26 % | 2.57 | 0.2 | +15.5 % | 0.90 | -28 % | 20:+28 21:+68 22:-8 23:-9 24:+9 25:+55 26:-17 | no: t<2,sharpe<ref+0.15 / tested: t<2.5,sharpe<1,mdd>25%,years<5 (rnd Sharpe 0.38) |

BETTER than equal slots on both universes (adoption rule): none.
BETTER on one universe only (informative): regime_half.
Candidates for money: 2 of 10.

### Robustness 2005-2019 (`small`, Yahoo survivors file, flat 0.30 % half-spread; descriptive)

| rule | trades | hit | avg net | t | CAGR | Sharpe | mDD | years | read |
|---|---|---|---|---|---|---|---|---|---|
| ref | 612 | 41 % | +3.64 % | 4.2 | +13.3 % | 0.89 | -27 % | 05:+5 06:+41 07:+30 08:-10 09:+26 10:+20 11:+8 12:+20 13:+24 14:+7 15:-15 16:+36 17:+19 18:-4 19:+2 | reference |
| regime_half | 612 | 41 % | +3.64 % | 4.2 | +13.5 % | 0.93 | -22 % | 05:-0 06:+41 07:+30 08:-7 09:+24 10:+19 11:+8 12:+21 13:+24 14:+8 15:-10 16:+34 17:+19 18:-2 19:+1 | not confirmed |

## A2. Follow-up declared after reading A (1 trial, cumulative N = 429): regime-sized ENTRIES, the implementable form

A new position takes half a slot when COMPOSITE < its 200-day average at the signal close, a full slot otherwise; held positions are never resized. Share of trading days with the regime off: 2020: 2 %, 2021: 2 %, 2022: 16 %, 2023: 56 %, 2024: 21 %, 2025: 45 %, 2026: 77 %.

| arm | trades | hold d | hit | avg net | payoff | t | CAGR | Sharpe | mDD | years | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| equal 1/K | small | 496 | 24 | 42 % | +4.10 % | 2.38 | 3.4 | +29.5 % | 1.31 | -30 % | 20:+24 21:+65 22:+29 23:-5 24:+1 25:+131 26:-8 | reference |
| regime_entry | small | 496 | 24 | 42 % | +4.10 % | 2.38 | 3.4 | +26.8 % | 1.34 | -22 % | 20:+12 21:+64 22:+26 23:-6 24:+2 25:+121 26:-6 | no: sharpe<ref+0.15 / CANDIDATE (rnd Sharpe 0.55) |
| equal 1/K | LIQ | 480 | 27 | 38 % | +3.10 % | 2.51 | 2.5 | +19.1 % | 0.92 | -36 % | 20:+32 21:+83 22:-4 23:-12 24:+12 25:+76 26:-22 | reference |
| regime_entry | LIQ | 480 | 27 | 38 % | +3.10 % | 2.51 | 2.5 | +16.4 % | 0.92 | -29 % | 20:+15 21:+77 22:-7 23:-7 24:+9 25:+70 26:-18 | no: sharpe<ref+0.15 / tested: sharpe<1,mdd>25%,years<5,vs random (rnd Sharpe 0.59) |

2005-2019 (`small`, Yahoo survivors file): ref: CAGR +13.3 %, Sharpe 0.89, mDD -27 %, years 05:+5 06:+41 07:+30 08:-10 09:+26 10:+20 11:+8 12:+20 13:+24 14:+7 15:-15 16:+36 17:+19 18:-4 19:+2 | regime_entry: CAGR +13.3 %, Sharpe 0.92, mDD -24 %, years 05:+3 06:+41 07:+30 08:-7 09:+20 10:+20 11:+8 12:+17 13:+23 14:+7 15:-11 16:+35 17:+19 18:+2 19:-1

## B. The combined book: value + trend as one book (3 trials), 2021-01-04 -> 2026-09-21

Daily-return correlation of the sleeves: +0.37. Days with both sleeves > 10 % under water: 17 %. Value at the trend trough (2026-06-08): -23 %; trend at the value trough (2026-06-08): -30 %.

| book | CAGR | vol | Sharpe | mDD | years | verdict |
|---|---|---|---|---|---|---|
| value alone | +16.0 % | 18 % | 0.91 | -23 % | 21:+7 22:+35 23:-8 24:+12 25:+21 26:+25 | reference (what runs today, separately) |
| trend alone | +30.3 % | 23 % | 1.28 | -30 % | 21:+65 22:+29 23:-5 24:+1 25:+131 26:-8 | reference (what runs today, separately) |
| combo_5050 | +23.6 % | 17 % | 1.33 | -22 % | 21:+31 22:+32 23:-6 24:+7 25:+71 26:+7 | no: sharpe<1.43 |
| combo_rp | +22.1 % | 17 % | 1.29 | -22 % | 21:+28 22:+32 23:-6 24:+8 25:+57 26:+11 | no: sharpe<1.43 |
| combo_3way | +19.8 % | 14 % | 1.40 | -18 % | 21:+26 22:+26 23:-4 24:+6 25:+55 26:+7 | no: sharpe<1.43 |

## C. Sector rotation (3 trials), 2021-01-04 -> 2026-09-21, sectors A, B, C, D, E, F, G, H, I, J, K

| arm | trades | hold d | hit | avg net | payoff | t | CAGR | Sharpe | mDD | years | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| sec_mom6 | 496 | 44 | 38 % | -0.94 % | 1.49 | -0.5 | -1.1 % | 0.11 | -50 % | 21:+28 22:-1 23:-22 24:-8 25:+56 26:-34 | tested: t<2.5,sharpe<1,mdd>25%,years<5,vs random |
| sec_mom12_1 | 350 | 59 | 37 % | +0.14 % | 1.69 | 0.1 | -0.7 % | 0.12 | -52 % | 21:-7 22:-5 23:-26 24:-17 25:+139 26:-27 | tested: t<2.5,sharpe<1,mdd>25%,years<5,vs random |
| sec_cmdty | 126 | 58 | 40 % | -0.36 % | 1.46 | -0.2 | +1.9 % | 0.20 | -46 % | 21:-5 22:+51 23:-4 24:+7 25:-0 26:-25 | tested: n<150,t<2.5,sharpe<1,mdd>25%,years<5,vs random |
| random2 | 879 | 24 | 39 % | -0.67 % | 1.41 | -1.0 | +4.5 % | 0.30 | -49 % | 21:-13 22:-23 23:-13 24:+9 25:+144 26:-18 | reference |
| all_liq | 646 | 136 | 23 % | -8.17 % | 2.02 | -2.6 | +0.6 % | 0.13 | -44 % | 21:+13 22:-12 23:-8 24:-2 25:+48 26:-22 | reference |
| COMPOSITE | - | - | - | - | - | - | +0.8 % | 0.13 | -42 % | 21:+8 22:+4 23:+6 24:-3 25:+22 26:-26 | reference |

Sector equal-weight LIQ total return over the window: A +180 %, B +16 %, D -23 %, G -24 %, E -26 %, J -34 %, C -36 %, F -37 %, I -44 %, H -71 %, K -74 %.

## D. The allocation layer in rupiah (2 trials), monthly 2006-02-28 -> 2026-09-30

Cash = BI rate - 1.5 points; BI 2024-25 filled by hand: {'2024-01': 6.0, '2024-04': 6.25, '2024-09': 6.0, '2025-01': 5.75, '2025-05': 5.5, '2025-07': 5.25, '2025-08': 5.0, '2025-09': 4.75}. Switch cost 0.30 %.

| arm | CAGR | vol | Sharpe | mDD | switches | time in IHSG / S&P / gold / cash | years | verdict |
|---|---|---|---|---|---|---|---|---|
| gem_idr | +11.2 % | 12 % | 0.93 | -19 % | 46 | 38 / 24 / 0 / 38 % | 06:+47 07:+52 08:-14 09:+12 10:+46 11:-6 12:+4 13:+23 14:+18 15:+5 16:+4 17:+18 18:+6 19:-8 20:+3 21:+26 22:-8 23:+3 24:+30 25:+6 26:-8 | BETTER |
| dm3_idr | +14.8 % | 19 % | 0.82 | -20 % | 43 | 27 / 34 / 38 / 1 % | 06:+16 07:+52 08:+4 09:+1 10:+46 11:-8 12:+15 13:+54 14:+13 15:+8 16:-10 17:+18 18:-2 19:+12 20:+18 21:+16 22:-8 23:-6 24:+28 25:+70 26:+8 | no: sharpe<IHSG+0.30 |
| IHSG | +8.4 % | 19 % | 0.53 | -55 % | - | - | 06:+47 07:+52 08:-51 09:+87 10:+46 11:+3 12:+13 13:-1 14:+22 15:-12 16:+15 17:+20 18:-3 19:+2 20:-5 21:+10 22:+4 23:+6 24:-3 25:+22 26:-24 | reference |
| SP_IDR | +12.6 % | 15 % | 0.86 | -37 % | - | - | 06:+6 07:+9 08:-27 09:+4 10:+6 11:-0 12:+23 13:+65 14:+13 15:+11 16:+7 17:+20 18:+1 19:+23 20:+16 21:+31 22:-12 23:+23 24:+29 25:+21 26:+21 | reference |
| GOLD_IDR | +13.9 % | 19 % | 0.77 | -29 % | - | - | 06:+7 07:+38 08:+25 09:+5 10:+22 11:+10 12:+16 13:-9 14:+0 15:-0 16:+5 17:+14 18:+5 19:+14 20:+24 21:-0 22:+9 23:+12 24:+33 25:+71 26:+8 | reference |
| CASH | +4.8 % | 1 % | 9.09 | 0 % | - | - | 06:+9 07:+7 08:+7 09:+6 10:+5 11:+5 12:+4 13:+5 14:+6 15:+6 16:+4 17:+3 18:+4 19:+4 20:+3 21:+2 22:+2 23:+4 24:+5 25:+4 26:+3 | reference |
| 60_40 | +7.4 % | 11 % | 0.70 | -35 % | - | - | 06:+31 07:+33 08:-31 09:+50 10:+29 11:+4 12:+10 13:+2 14:+16 15:-5 16:+11 17:+13 18:+0 19:+3 20:-1 21:+7 22:+4 23:+6 24:+0 25:+15 26:-14 | reference |
| EW3 | +12.6 % | 11 % | 1.14 | -28 % | - | - | 06:+19 07:+33 08:-21 09:+29 10:+25 11:+5 12:+18 13:+16 14:+12 15:-0 16:+10 17:+18 18:+2 19:+13 20:+13 21:+13 22:+1 23:+14 24:+19 25:+37 26:+1 | reference |

Dividend sensitivity (descriptive): the same arms with a flat 2.5 %/yr added to IHSG and 1.8 %/yr to the S&P while held (price indices carry none):

| arm | CAGR | Sharpe | mDD |
|---|---|---|---|
| gem_idr | +12.7 % | 1.04 | -18 % |
| dm3_idr | +16.3 % | 0.89 | -19 % |
| IHSG | +11.1 % | 0.66 | -54 % |
| EW3 | +14.2 % | 1.27 | -27 % |


## Verdict (menu 21, study #61) — 18 pre-registered trials + 1 declared follow-up, cumulative N = 429

**By the letter: 0 of 18 arms is "better than what we have"; 1 arm (gem_idr) is better than holding the index.** Three things are nonetheless
new and hold up, and one whole family is dead.

1. **Half-size the trend sleeve while the IHSG is under its 200-day average — the first full money-rule pass of the deployed rule.**
   Book-level (`regime_half`, small): +29.2 %/yr, Sharpe 1.41, mDD −22 % (from −30 %), t 3.4, n 496, DSR 0.73 at N = 428, random + same
   sizing 0.83 → CANDIDATE on every clause. The implementable form (`regime_entry`: a NEW position takes NAV/20 instead of NAV/10 when
   COMPOSITE < MA200 at the signal close, held names untouched): +26.8 %/yr, Sharpe 1.34, mDD −22 %, DSR 0.66 → CANDIDATE. Both miss the
   paper-adoption bar (Sharpe ≥ reference + 0.15) by 0.05 and 0.12, and `regime_entry` also lowers LIQ's return (16.4 vs 19.1 %), so by the
   rule declared before the run neither is adopted. Direction is confirmed out of sample: 2005-2019 on the survivors file mDD −22 / −24 %
   against −27 %, Sharpe 0.93 / 0.92 against 0.89, CAGR unchanged. Why it is nearly free: breakouts are scarce while the index is under water,
   so the half-size bites mostly on the entries of 2023 (regime off 56 % of days), 2025 (45 %) and 2026 (77 %), which are the ones the trail
   stopped anyway (2025: +131 → +127 / +121 %; 2026: −8 → −4 / −6 %). This is the trend-sleeve twin of the value book's regime filter
   (IDX_TREND_OVERLAY): there it cost up to half the return; here it costs 0–3 points because the entry rule already avoids the worst days.
2. **The two engines are one book, and that book passes the money rule that neither sleeve passes alone.** Value alone (strict May, 2021→)
   Sharpe 0.91, mDD −23 %; trend alone Sharpe 1.28, mDD −30 %. 50 / 50 monthly: +23.6 %/yr, Sharpe 1.33, mDD −22 %; 40 / 40 / 20 cash:
   +19.8 %, Sharpe 1.40, mDD −18 %. Daily correlation +0.37; but both troughs fall on the same day (2026-06-08: value −23 %, trend −30 %) and
   17 % of days have both sleeves > 10 % under water — the diversification is in ordinary years, not in the crash. Not "better" by the
   declared bar (Sharpe ≥ best sleeve + 0.15 = 1.43) by 0.03–0.14. The operator's Rp 20 M value + Rp 10 M trend ≈ 67 / 33 sits between
   "value alone" and 50 / 50; moving toward 50 / 50 is what the numbers favour, at the cost of the trend book's daily attention.
3. **Above the desk: rupiah dual momentum beats holding the index, and a plain third-third-third beats the dual momentum.** 2006–2026 monthly,
   `gem_idr` (IHSG when its 12-month return beats cash, else cash; S&P 500 in IDR when it beats IHSG): +11.2 %/yr, Sharpe 0.93, mDD −19 %,
   46 switches, against IHSG +8.4 %, 0.53, −55 % → BETTER by the declared rule (also with dividends: 12.7 % / 1.04 / −18 % vs 11.1 % / 0.66 /
   −54 %). The reference nobody pre-registered as a trial is the honest read: IHSG / S&P (IDR) / gold (IDR) equal weight, rebalanced monthly,
   +12.6 %/yr, Sharpe 1.14, mDD −28 % (with dividends 14.2 % / 1.27 / −27 %) — more return and a higher Sharpe than the momentum switch with
   no signal at all; the switch buys 9 points of drawdown for 1.4 points of return. The lesson is about the operator's long-term capital
   (outside the desk): 100 % IHSG has been the worst of the four choices for twenty years.
4. **Dead: sizing by the name's own risk, and sector rotation.** Inverse-vol slots (Sharpe 0.89 vs 1.31), Turtle 1 % risk units (1.22, mDD
   −33 %) and pyramiding (hit 31 %, t 0.6) all lose to equal slots: the trend edge lives in the volatile names, and sizing them down removes
   it. Book-level vol targeting reaches mDD −24 % but at −6 points of CAGR (Sharpe 1.26) — the regime rule gets the same drawdown for free.
   Sector momentum 6 / 12-1 and Brent-gated energy: Sharpe 0.11 / 0.12 / 0.20, mDD −46…−52 %, below random sectors (0.30) and the flat
   COMPOSITE; only Energy made money 2021-26 (+180 % equal weight; every other sector −23 … −74 %) and momentum did not catch its one run in
   time. Cross-sector structure on IDX is one commodity cycle, not a rotation.

**What the operator can decide (nothing adopted automatically):**
- Trend books: a book option `regime_half_entry` (slot = NAV/2K while COMPOSITE < MA200 at the signal close) — one line in `trend_book.run`
  plus a book setting; two-key on `trend_live`. By the letter it is not adopted; by the evidence it is the cheapest drawdown cut found in
  429 trials. If wanted: switch `paper_trend` first, keep `trend_live` as is, compare after ≥ 60 closed trades.
- Sleeve split: keep both engines; 50 / 50 (or 40 / 40 / 20 cash) is the money-rule pass; the present 67 / 33 is inside the range.
- Long-term capital: a third each IHSG / S&P 500 / gold, rebalanced — evidence, not advice; needs a US-equity and a gold channel.

**Limits.** As menus 6-20 for the trend sleeve (closing quotes, no slippage beyond them, dividends ignored, open positions at the last bar
not counted). Combos assume money moves between sleeves at no cost on the first trading day of the month; the value sleeve is the rev. 3
simulator (dividends net of tax, 25 bps + half tick), the trend sleeve the menu-7 engine. Family D uses price indices (a flat dividend
sensitivity is shown), the BI rate with a hand-filled 2024-25 gap, a flat 0.30 % switch cost, no tax on gold or offshore gains, and does not
model the retail channels' spreads. The 2005-2019 file holds survivors only (same bias for rule and reference). Family C starts 2021-01 (6
calendar years, rule read as 5 of 6).
