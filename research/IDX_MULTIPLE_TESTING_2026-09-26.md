# Multiple-testing corrections for the combined book - 2026-09-26

Audit (no trial). (a) data snooping over the 144-configuration construction grid of #380 against IHSG; (b) the deployed
Sharpe against the desk's whole ledger (Harvey-Liu-Zhu haircut).

## (a) Hansen SPA and Romano-Wolf, 144 configurations, 1123 sessions, benchmark COMPOSITE, stationary bootstrap (block 10, B 2000)

| SPA p-value | configurations beating IHSG (Romano-Wolf, FWER 5 %) | deployed t | deployed survives RW | deployed excess vs IHSG /yr |
|---|---|---|---|---|
| **0.000** | 144 of 144 | 4.60 | yes | +44.6 % |

## (b) Harvey-Liu-Zhu haircut, deployed Sharpe 2.21 over 4.7 years (t 4.79, single-test p 1.7e-06)

Ledger p-value population: 6,412 stored arm Sharpes converted at 4.7 years.

| effective tests M | Bonferroni p | Holm p | BHY p | haircut Sharpe (Bonf / Holm / BHY) |
|---|---|---|---|---|
| 100 | 0.0002 | 0.0002 | 0.0004 | 1.74 / 1.74 / 1.62 |
| 300 | 0.0005 | 0.0005 | 0.0004 | 1.61 / 1.61 / 1.62 |
| 1019 | 0.0017 | 0.0016 | 0.0004 | 1.45 / 1.45 / 1.63 |

Reading against #380: the ledger DSR (0.23 at N 1,007) and this haircut (Sharpe 1.45-1.74 still significant at M 1,019)
disagree because of the NULL they assume. The DSR takes the ledger's observed Sharpe spread (sd 0.78) as pure noise - very
conservative, since many arms are variants of genuinely good books; the haircut takes the theoretical noise of a 4.7-year
Sharpe (sd 1/sqrt(4.7) = 0.46). The truth lies between. The bootstrap t in (a) (4.60, autocorrelation-robust) is close to
the iid t (4.79), so serial dependence does not rescue the pessimistic reading. Neither test can say whether 2022-26, a
sample dominated by 2025, is representative of the next five years: that is not a multiple-testing question.

Limits: (a) holds the signal rules fixed, so it only tests the construction search; (b) treats the deployed daily Sharpe
as normal and independent (daily IDX returns are fat-tailed and autocorrelated, which inflates t) and converts every
ledger arm at the same 4.7 years; the effective M is unknown and is shown as a range. The haircut Sharpe is the number
to plan with only in the sense of 'what the evidence still supports', not a forecast.
