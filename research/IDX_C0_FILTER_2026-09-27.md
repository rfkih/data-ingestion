# IDX menu FL-1 — earnings and news filters on the C0 wide sleeve — 2026-09-27 — study #406

Script `research/idx_c0_filter.py` (pre-registered). Base = RB-2's wide sleeve trades (994, 2022-01 on). Announcement TEXT is not
stored (titles/kinds only, 2023-07+) and news covers one month, so "news that raises earnings" = the REPORTED earnings published
before entry, and the KIND of recent disclosures. **4 trials; cumulative N 1093 -> 1097. Result: 0 of 4 USEFUL.**

| filter | kept: n / mean / median / 2x / stop | dropped: n / mean / median / 2x / stop | t (kept - dropped) | book Sharpe filtered vs base (by start) | verdict |
|---|---|---|---|---|---|
| K1 earnings up >= 30 % y/y or turnaround | 441 / +14.2 % / -9.6 % / 23 % / 45 % | 553 / +13.9 % / -13.4 % / 23 % / 49 % | 0.06 | 1.62-1.87 vs 1.34-1.65, mDD -11/-12 vs -19/-20 | no (no trade-level difference) |
| K2 not loss-making | 785 / +15.0 % / -11.2 % / 23 % / 47 % | 209 / +10.4 % / -14.3 % / 23 % / 50 % | 0.67 | 1.50-1.80 vs 1.34-1.65, mDD -17/-18 vs -19/-20 | no (t < 2) |
| K3 substantive disclosure in 60 d (2023-07+) | 345 / +13.4 % | 392 / +20.6 % | -1.05 | 1.54-1.56 vs 1.65-1.82 | no (wrong sign) |
| K4 drop attention-only names (UMA / media clarification, no substance) | 606 / +14.7 % | 131 / **+29.0 %**, 2x 31 % | -1.29 | 1.38-1.50 vs 1.65-1.82 | no (wrong sign) |

## Reading

1. **Reported earnings do not tell which radar names will run**: earnings-up names average the same as the rest (t 0.06) and
   touch 2x equally often (23 %). K1's better book is a smaller book (fewer positions, lower exposure, half the drawdown at about
   the same CAGR), not better picks - interesting for sizing, not evidence of selection.
2. **Dropping loss-makers leans the right way** (+15.0 % vs +10.4 %, better book at every start) but is not significant (t 0.67);
   menu 35 found the opposite on the trend sleeve. Not adoptable.
3. **"Noise" is the fuel.** Names whose only recent disclosures are exchange-query replies / media clarifications did BETTER
   (+29 %, 2x 31 %) than names with substantive disclosures (+13 %). On IDX the multibagger run is a speculative-attention event;
   the fundamental story, if any, is priced before it is disclosed (#185) or never arrives.
4. What is NOT testable here: the content of the replies ("no material information" vs a named contract). That needs the PDFs
   (2023-07+) or a forward LLM read of each new disclosure - a measurement to start, not a result.
