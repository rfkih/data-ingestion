# IDX menu RB-1 — a trading book on the multibagger radar — 2026-09-27

Script `research/idx_radar_book.py` (pre-registered); robustness `research-scratch/idx/daytrade2/r2_robust.py` (declared after the
verdict, before its numbers). TR-2 machinery (PIT cache, K-10 run_book, rupiah replay Rp 20 m / lots / offer-bid / band realism),
window 2023-07-03 -> 2026-09-16. **4 trials; cumulative N 1087 -> 1091. R2 passed the letter, then FAILED all three robustness
checks -> 0 of 4 in substance.**

| book | CAGR | Sharpe | mDD | halves | x2 cost Sharpe | verdict |
|---|---|---|---|---|---|---|
| REF deployed trend | 12.6 % | 1.12 | -18 % | -6 % / +32 % | 0.87 | reference |
| C0 plain (trail 25 %) | 13.6 % | 1.00 | -19 % | +10 % / +17 % | 0.90 | reference |
| R1 top tier (C0 + UMA/event), 10 %, stop -15 % / trail 25 % | 36.4 % | 1.30 | -33 % | +36 % / +37 % | 1.12 | no (mDD) |
| R2 C0 + attention, 5 %, stop -15 % / trail 25 % | 19.7 % | 1.17 | -23 % | +28 % / +13 % | 1.07 | BETTER by the letter |
| R3 tiered 10 / 7.5 / 5 % | 28.1 % | 1.18 | -31 % | +18 % / +38 % | 0.87 | no |
| R4 R3 + book vol targeting | 21.3 % | 1.01 | -30 % | +19 % / +23 % | 0.72 | no |

## R2 robustness (all three fail)

1. Without its best trade (FORU 2024-01-29, +892 %): 11.8 % / Sharpe 0.80 / -27 % - below REF.
2. Neighbours (stop 10/20 % x trail 20/30 %): 0 of 4 beat REF (Sharpe -0.08 .. 0.94).
3. The unseen window: entries 2022-01..2023-06 R2 -0.8 % vs REF +2.0 %; book from 2022-01 to the end R2 0.6 %/0.12/-36 % vs
   REF 9.9 %/0.95/-19 % - starting six months earlier fills the slots with other names and the result disappears (path dependence).

## Reading

R2's pass was one trade and one starting date. The radar's lift is real at the level of NAMES (MB-1), but a book of 5 % slots
turns that lift into a lottery on which rocket happens to be in a slot - a few names (FORU, PANI) decide the whole result. R1's
36 %/yr is the same lottery with bigger slots (-33 % drawdown). No sizing, stop or vol-targeting variant made it robust.
**Keep the deployed trend sleeve; use the radar as a watchlist.** Do not re-open radar-book variants on this data.
