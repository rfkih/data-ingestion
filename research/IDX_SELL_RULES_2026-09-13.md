# IDX — When to sell a name that has become expensive (2026-09-13)

**The operator's question.** The book's only valuation exit is the annual rebalance: a name that is no longer in the
cheapest fifth leaves in May. Should a name be sold earlier, when its price is "indicated over-priced"? And what does a
Rp 50M book look like?

**Verdict.** Selling early on valuation *hurts*: "no longer cheap against peers" and "P/E above 15" lose to holding in
every calendar (−4 % to −57 % of the return). Take-profit at +50 % loses in three of four. Take-profit at **+100 %** is the
one rule that passes the pre-registered bar (ahead in three of four calendars, no deeper drawdown), but it rests on ten
doubling events in five years: after a double the median name gave back 5 % by the next rebalance and six of ten fell,
while one (PTRO 2024) went on to +185 %. It sells the small reversals and misses the multi-bagger. Offered as a book
option (`take_profit_pct`, off by default); the annual rebalance stays the default valuation exit.

## Pre-registered menu (4 trials; cumulative 104)

The strict composite, 2021–2026, four calendars, drift mode with a one-slot cap, cash 4 %/yr, checked on the first trading
day of each month; a name sold by a rule stays in cash until the next annual rebalance.

| Rule | Sell a held name when |
|---|---|
| none (reference) | never before the rebalance |
| val_median | its earnings yield (audited profit / market value, point-in-time) falls under the light-gate pool's median that day |
| pe15 | its P/E on audited profit exceeds 15 |
| tp50 | it is 50 % above its purchase close |
| tp100 | it is 100 % above its purchase close |

Reading rule, declared before the run: a rule replaces "hold to the rebalance" only if ahead in at least three of four
calendars with no deeper worst drawdown. Script `research/idx_sell_rules.py`; outputs `research-scratch/idx-screen/sell_rules_out.txt`,
`sell_rules_results.json`.

## Results (total return · Sharpe · max drawdown)

| Rule | May | Feb | Aug | Nov | Ahead |
|---|---|---|---|---|---|
| hold to the rebalance | +142 % · 1.00 · 22 % | +234 % · 1.41 · 21 % | +120 % · 0.95 · 19 % | +81 % · 0.81 · 22 % | — |
| no longer cheap vs peers | +136 % · 0.97 · 22 % | +121 % · 1.03 · 22 % | +96 % · 0.84 · 20 % | +70 % · 0.75 · 22 % | 0 of 4 |
| P/E above 15 | +114 % · 0.88 · 22 % | +100 % · 0.92 · 22 % | +78 % · 0.76 · 20 % | +62 % · 0.70 · 21 % | 0 of 4 |
| take profit +50 % | +103 % · 0.87 · 23 % | +170 % · 1.37 · 18 % | +101 % · 0.97 · 19 % | +84 % · 0.92 · 21 % | 1 of 4 |
| take profit +100 % | +146 % · 1.03 · 22 % | +192 % · 1.35 · 17 % | +128 % · 1.09 · 19 % | +88 % · 0.89 · 22 % | 3 of 4 |

## Diagnostic: what happens after a strict name doubles (not a trial)

Ten doubling events across the four calendars (some names counted in two calendars). Return from the first monthly check
at or above twice the entry to the next rebalance:

| Calendar | Events | After the double, to the rebalance |
|---|---|---|
| May | 2 | ELSA 2025 −24 %, SRTG 2021 +13 % |
| Feb | 4 | TOBA 2024 −46 %, DSNG 2024 −14 %, AKRA 2022 −2 %, PTRO 2024 +185 % |
| Aug | 4 | ELSA 2025 −30 %, PTBA 2021 −8 %, PTRO 2023 +5 %, ENRG 2021 +23 % |
| Nov | 0 | — |

Pooled: median −5 %, six of ten fell back, mean +10 % because of PTRO; without the two biggest runs the mean is −13 %.
That is the shape of the trade: take profit at +100 % wins a little most of the time and loses the year's big winner once.
Ten events is not enough to call it; the rule passes its bar and is offered, not imposed.

## Why valuation exits lose here

A cheap name that re-rates from P/E 4 to P/E 8 is "no longer the cheapest" long before its run is over; the pool median
and the P/E 15 line both sell in the first half of the move. The composite's edge is the re-rating itself, and the annual
rebalance already harvests it: names that are no longer in the cheapest fifth leave in May, and the year's turnover is
most of the list. Selling earlier trades the tail of the re-rating for cash.

## A Rp 50M book

With the last prices (2026-09-11) and the strict list of 13 names, the ticket planner:

| Capital | List | Names bought | Invested | Cash left | Per name |
|---|---|---|---|---|---|
| Rp 50M | whole list (13) | 13 | 94 % | 5.4 % | about Rp 3.8M (UNTR one lot, Rp 2.6M) |
| Rp 50M | 10 names | 10 | 98 % | 2.2 % | about Rp 4.9M |
| Rp 30M | 10 names | 10 | 95 % | 4.6 % | about Rp 2.9M |
| Rp 100M | whole list (13) | 13 | 96 % | 4.1 % | about Rp 7.6M |

Cash in the book is not a target; it is the 1 % reserve plus what lot rounding leaves (one lot of a Rp 26,000 stock is
Rp 2.6M, so small books cannot fill that slot evenly). Before this note the ticket refused any line under Rp 5M, which
left a Rp 50M book unable to buy anything; the minimum line now scales with the book (one twentieth of NAV, floor Rp 1M,
cap Rp 5M: Rp 2.5M for Rp 50M). At Rp 50M the ten-name list is the cleaner fit: every slot near Rp 5M, 98 % invested.

## What changed

- `ticket.min_trade_for(nav)`: the minimum line scales with the book.
- Book option `take_profit_pct` (migration 0013, off by default): at the monthly check, held names at or above
  purchase × (1 + pct) go into an "exits" ticket. The paper book runs it at 100 % alongside the other overlays; the live
  book has it off.
- The annual rebalance remains the book's valuation exit; "no longer cheap" and "P/E 15" are recorded as tested, not better.
