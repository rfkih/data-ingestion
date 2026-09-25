# IDX live/paper books vs backtest yardsticks - audit 2026-09-25

Track A1. Read-only. Asked: is execution eating the edge?
Evidence: `scripts/status.py --json` (22:56 WIB), `idx track --all`, `idx combo status|scorecard`, SQL on `idx.book`,
`idx.book_nav`, `idx.position`, `idx.fill`, `idx.ticket(_line)`, `idx.combo_watch`, `idx.combo_scorecard`, `idx.alert`,
`idx.strategy_backtest_trade`, `idx.bar`, `idx.feed_trade`, and `logs/idx/scheduler.log`.

**Short answer: we cannot tell yet.** No book has enough closed, on-rule trades to compare with its backtest. Across
all the books there are **0 closed on-rule round trips**. The only execution measurement is three live trend entries,
and they show **no sign of execution cost** (mean -11 bps against the paper fills). Every book below is **TOO EARLY**.
The audit did find several operational problems (section 6).

---

## 1. Overview (status.py, 2026-09-25 close)

| Book | Kind | Rule | Started | Capital | NAV now | Pos | Closed trips |
|---|---|---|---|---|---|---|---|
| paper_gapfade | paper | gapfade | 09-22 18:33 WIB | 100.0 M | 100.00 M | 0 | 0 |
| trend_live | live (Stockbit) | trend small | 09-17 | 10.0 M | 10.12 M (+1.2 %) | 1 | 2 (both off-rule) |
| paper_trend | paper | trend small | 09-17 | 100.0 M | 100.69 M (+0.7 %) | 4 | 0 |
| live-fae554 | live (Stockbit) | combo | 09-25 01:21 WIB | 20.0 M | 20.00 M | 0 | 0 |
| paper-edbb01 | paper | combo | 09-25 01:20 WIB | 20.0 M | 20.00 M | 0 | 0 |
| live-82e98d | live | annual strict | 09-18 | 20.0 M | 20.00 M | 0 | 0 |
| live-b877d2 | live | annual strict | 09-24 | 20.0 M | 20.00 M | 0 | 0 |
| live (IPOT) | live | annual strict | 09-12 | ~20 M | 18.74 M | 6 | 0 - **ARCHIVED 09-18 13:53 WIB** |

---

## 2. Gap-fade paper validation (`paper_gapfade`, Rp 100 M, K=5, gap <= -7 %, v60 >= Rp 5 bn)

| Metric | Paper | Yardstick | Note |
|---|---|---|---|
| Sessions since start | 3 (09-23, 09-24, 09-25) | - | book created the evening of 09-22 |
| Sessions with a valid scan | 2 | - | 09-24 **blind**: 0 opening prints, the feed collector was dead (alerts 09:00/09:05) |
| Sessions traded (event days) | **0** | bar = **20** | 0 / 20 |
| Trades / win % / avg return | 0 / - / - | #77 g7: hit 52 %, +300 bps; #166: 227 trades, win 49.8 %, avg +268 bps | nothing to compare |
| Slippage (first-5-min VWAP vs open) | n = 0 | - | not measured yet |
| **Verdict** | **TOO EARLY** | | |

**Were the zero trades correct?** Yes. Official IDX bars for 09-22..09-25 show every open at or below -7 %:
FORU -93 % (v60 Rp 3.1 bn; a basis reset), TEBE -12.3 % (v60 Rp 2.0 bn), NASI -14.6 % / -15.0 % (v60 Rp 0.2 bn),
BPTR -7.1 % (v60 Rp 0.1 bn). **All of them fail the liquidity floor.** The scheduler ran the entry scan at 09:00 and
09:05 on 09-23 and 09-25 (126-131 opening prints seen, 0 candidates), so the zeros are what the rule said. The blind
morning of 09-24 had no liquid gap either, so it cost nothing this time.

**How far is the 20-session bar?** The live scan sees only the names the feed subscribes to. On 09-25 that was
**135 names, of which 114 are among the 167 names with v60 >= Rp 5 bn (68 %)**. That restriction changes the
backtest (#166, 2022-01..2026-09-14, 1,122 sessions):

| Backtest subset | Event sessions | Per session | Avg / trade | Win % |
|---|---|---|---|---|
| All names | 132 | 11.8 % | +268 bps | 49.8 % |
| Names in the current feed | 77 | **6.9 %** | **+195 bps** | 50.0 % |
| Feed names, last 12 m (239 sessions) | 47 | **19.7 %** | | |

- At the rate the feed can see, getting to **20 traded sessions takes about 100 sessions (~5 months) at the last-12-month rate, or about 290 sessions (~14 months) at the full-period rate**. Two valid scans with no events is ordinary: P(0 events) is 0.64-0.87.
- The feed names carry a **lower backtest edge** (+195 bps against +268 bps) than the #77/#166 yardstick. Judge the paper book against the feed-restricted figure, not the headline +300 bps.

---

## 3. Trend: `trend_live` (real, Rp 10 M) and `paper_trend` (Rp 100 M)

Yardsticks: task brief win 38 % / avg +5.2 %; `track.py` profile (#62, regime_gate|small) hit 44 %, payoff 2.74,
avg +6.3 %, 60-closed-trade bar; #166 trade list (`trend_small`, 263 trades) win 37.6 %, avg +3.35 %.

**Closed trades**

| Book | Closed | On-rule closed | Win % | Avg | Verdict |
|---|---|---|---|---|---|
| trend_live | 2 (DEWI +20.3 %, IRSX -4.2 % net of fees) | **0** | - | - | **TOO EARLY** (0/60) |
| paper_trend | 0 | 0 | - | - | **TOO EARLY** (0/60) |

`idx track` reports trend_live as "2/60, hit 50 %, avg 8.0 %". **Do not use that figure.** Both trips are the
2026-09-24 off-rule exits (the broker stop was mis-set to 4 %; the trail-10 levels were 203 for DEWI and 396 for IRSX,
and neither had been hit). They say nothing about the rule.

**Execution: live fills vs the paper twin (same tickets, same days)**

| Code | Date | Ticket limit | ref close | Paper fill (open) | Live fill | Live vs paper |
|---|---|---|---|---|---|---|
| ERAA | 09-18 | 625 | 620 | 625 | 625 | 0 bps |
| DEWI | 09-18 | 184 | 183 | 183 | 184 | +55 bps |
| IRSX | 09-22 | 456 | 454 | 460 | 456 | -87 bps |
| **Mean (n = 3)** | | | | | | **-11 bps** (live paid less) |

- **No sign that execution is eating the edge** for this sleeve. With n = 3 that is anecdote, not proof.
- Fees in the ledger: live 0.10 % buy / 0.20 % sell. The paper fill for IRSX (460) sits above the ticket limit (456): the paper filler takes the open and ignores the limit.
- **Structural difference:** the live 10 M book never bought SINI. One lot cost about Rp 1.68 M, which is 16.8 % of NAV and above the 15 % weight cap. Paper holds SINI at +7.9 %. The two books will keep diverging on high-priced names.

**Open marks at the 09-25 close** (unrealized; not part of any verdict)

| Book | DEWI | ERAA | IRSX | SINI |
|---|---|---|---|---|
| paper_trend | +23.4 % | -4.1 % | **-18.8 %** (sell ticket #688 issued, limit 372, fills at the 09-28 open) | +7.9 % |
| trend_live | sold off-rule @ 222 | -4.1 % (stop 562.5, 6.3 % away) | sold off-rule @ 438 | never bought |

- **IRSX fell 14.6 % on 09-25** (438 -> 374), straight through its trail-10 stop at 396. The paper rule exits at the next open, about 6 % below the stop.
- The live off-rule exit at 438 therefore came out **about +Rp 134 k ahead** on IRSX and about -Rp 22 k behind on DEWI (still 226 against the 222 sale). That is luck, not rule performance, and it is excluded.
- **Data oddity:** trend_live ticket #142 (IRSX buy) has status `cancelled`, but its line is `filled` 21/21 and fill #789 exists.

---

## 4. Combo books: `live-fae554` (live) / `paper-edbb01` (paper twin)

`idx combo scorecard` for both books: **no sleeve lines, 0 filled, 0 missed, slippage n/a, delay n/a, P&L 0**.
Six ML watches are pending (TCPI 1,705, FILM 730, BAIK 290, KOTA 188, HOPE 292, PADA 188; all until 10-10).

| Sleeve | Lines | Filled | Missed | Slip bps | Delay | Why nothing traded |
|---|---|---|---|---|---|---|
| gap (10 %) | 0 | 0 | 0 | - | - | gap_entry ran 09:00/09:05 (128-131 prints); 0 liquid gaps (see §2) |
| trend (5 %) | 0 | 0 | 0 | - | - | regime gate **CLOSED** (COMPOSITE under its 200-d average): 0 new signals, 2 held back (21:10 plan) |
| ml (5 %) | 0 | 0 | 0 | - | - | 6 watches, none confirmed. 09-25 highs were all under their levels (TCPI 1,615 vs 1,705; FILM 710 vs 730; HOPE 286 vs 292; KOTA 181 vs 188; BAIK 282; PADA 180). combo_confirm ran 178 times in session. |

**Verdict: TOO EARLY.** Day 1, 0 trades, and the paper twin matches the live book exactly (same 6 watches). Nothing was
missed that should have traded. The six watches are all pre-switch rows (rule `+5/10`, size_frac 1.0). The 09-25 plans
at 21:10/21:40 added **0 new watches**, so the ens4 multi-rule path has not been exercised yet. Backtest yardstick
(#166-168): CAGR 39.8 %, Sharpe 1.86, mDD -21.5 %; measuring it needs months.

---

## 5. Value strict live books

| Book | Owner | Positions | Tickets ever | State |
|---|---|---|---|---|
| live-82e98d | rfkih234@gmail.com | 0 | 0 | active, cash 20 M |
| live-b877d2 | rfkih23@gmail.com | 0 | 0 | active, cash 20 M |
| live-8389c6 / live-f7734e | rfkih234 | - | - | archived 09-18 (duplicates / mis-taps) |
| **live** (IPOT, the real one) | rfkih23 | **6** (ACES, GJTL, ELSA, LSIP, BMRI, SSIA) | #23 (filled 09-17) | **still ARCHIVED since 2026-09-18 13:53 WIB; un-archive never done** |

- **Being empty is expected under the rule.** `rule=annual` rebalances in the May 1-10 window, and the signal board emits `hold` outside it. A book created in September has nothing to buy on its own until May 2027 unless the operator seeds it by hand. That leaves 2 x Rp 20 M idle for about 7 months. Whether that is intended is the operator's call.
- **The IPOT book holds real positions** worth about Rp 16.65 M, plus Rp 2.09 M cash, for a NAV of Rp 18.74 M (about -6 % since the 09-17 fills; all 6 names are down 2.8-10.4 % against cost). It is still marked nightly: `book_nav` has rows through 09-25. Because it is archived, it is **out of every job and alert list**: there has been no `book:live` alert since 09-18.
- **Latent bug:** `scheduler.check_rebalance_due` hard-codes `book = 'live'` (scheduler.py:218). The May reminder therefore watches the archived book and never covers live-82e98d or live-b877d2.

---

## 6. Operational problems found

1. **Pushes are being dropped for the operator's main account.** User `ff5e52a8` (rfkih23@gmail.com) owns trend_live, paper_trend, paper_gapfade and both combo books, but has **no registered push device**. The only device in `idx.push_device` belongs to `0c9270d1` (rfkih234@gmail.com). The scheduler log shows 13 "no enabled device ... dropped" lines, including both combo plans at 21:10/21:40. **Live combo tickets are two-key drafts that rely on this push**, so the first live signal will reach no phone.
2. **The IPOT live book is still archived** (mis-tap 09-18), with Rp 18.7 M of real holdings outside the alert and stop jobs.
3. **The feed blackout on 09-24** (collector dead, 0 opening prints) blinded the gap-fade and ARA morning. The watchdog has been in place since. It cost nothing that day, but it is the main threat to the 20-session count.
4. **The feed universe is narrower than the backtest universe** (114 of 167 liquid names). The gap sleeve sees about 58 % of the backtest's event days (77 of 132) and trades a lower-edge subset.
5. `check_rebalance_due` points at the archived `live` book (latent until May 2027).
6. Minor: trend_live ticket #142 is `cancelled` with a filled line. The paper filler ignores the limit (IRSX 460 > 456).

**Write during the audit:** `idx combo scorecard` is not read-only. It re-upserted the 2026-09-25 rows in
`idx.combo_scorecard` for both combo books (computed_at 22:57 WIB). The content is the same as the 20:30 scheduler run
(empty sleeves, 6 pending watches). No other writes.
