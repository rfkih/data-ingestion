# Intraday / "Scalping" — Wider-View Scope (2026-07-15)

## The reframe (the core insight)

We spent the whole investigation asking *"what signal predicts the next 15m move?"* — and proved it dead
across every information class we can reach (ML direction sweep = coin-flip; 1h + 15m CVD/OFI = dead;
15m MR/momentum = gross-dead or adverse-selected under maker; candle-proxy order-flow = real but ~10× too
small). **That is the wrong question.** Intraday profit is not a *prediction* problem — it is a
*structure* problem. The order-flow test proved it precisely: the only real 15m edge (the reversion after
taker-buy aggression, ~0.5–1.5 bps) is the **liquidity-provision premium** — it accrues to whoever
*provides* the fill, not whoever *predicts*. So the real question:

> **Which intraday *business model* is winnable for THIS specific stack?**

## Be honest about what this stack is

| Constraint | Implication |
|---|---|
| No co-location (internet latency to Binance) | Lose ANY speed race |
| ~$191 free capital, VIP0 fee tier | Worst fees, no rebates, no scale — the scalping *scale* game is closed |
| Binance-centric, taker-default execution | No maker rebates today; execution is a cost, not a revenue |
| JVM-on-VPS, systematic, patient, 24/7, disciplined | ← the actual STRENGTH: can wait, can react, can run many uncorrelated sleeves |

The stack's edge is **being systematic and patient, not being fast or big.** Any winnable intraday play must
lean into that and avoid fighting HFTs at their own game.

## The landscape of intraday money-making, scored for this stack

| Approach | Edge source | Fits? | Binding gate |
|---|---|---|---|
| Continuous directional scalping | predict next tick | ❌ DEAD (proven, all info classes) | no edge exists |
| Latency arb (cross-venue lead-lag) | be first | ❌ NO-GO | needs co-lo; lose the race (see arb-family scope) |
| Intraday cross-sectional / basis | relative dislocation | ❌ LOW | cost floor; positioning-XS falsified OOS |
| **Event / dislocation reaction** | forced-flow overshoot | ✅ **BEST FIT** | liquidation data maturing ~Aug |
| Market-making (liquidity provision) | earn spread + rebate | ⚠️ real, heavy | L2 book data (~Aug) + quoting engine + fee tier |
| Execution overlay (maker fills on slow book) | save fees on trades you already do | ✅ free-ish | small, available now |

## The doors that are actually open (outside-the-box)

### 1. ★ Liquidation-cascade reaction — "pounce, don't grind" (the best fit)
Forced liquidations overshoot and revert — a **real, well-documented effect**, and the moves are **1–5%,
i.e. ~100× the cost floor.** This is "intraday" but the *opposite* of scalping: rare, high-conviction,
event-triggered — you wait for a fat dislocation instead of grinding bps every bar. Critically:
- **Taker execution is fine** — the edge dwarfs the fee (the thing that killed every scalp is irrelevant here).
- **No co-location needed** — a cascade plays out over minutes; you don't need to be first, just systematic.
- **Plays to the stack's strength** — patient, rule-based, event-driven.
- **Data is already accruing** — `LIQ_FADE` features (liq_usd_rate_zscore/accel, liq_event_count) built on
  branch `feat/liq-fade-features` (V201, not pushed); Binance forceOrder stream live since 2026-06-24 →
  n≥100 reachable ~Aug/Sept. It is literally *providing liquidity to forced sellers* — the same
  liquidity-provision premium the order-flow test found, but in its FAT, cost-insensitive form.

**This is the primary intraday direction.** Not scalping — event-reaction.

### 2. Market-making (liquidity provision) — "provide, don't predict" (the real HFT edge, bigger lift)
The liquidity-provision premium is real (just measured). It's capturable at **maker-rebate fee tiers +
L2 queue management**. Requires: (a) true L2 order-book data (`ob_*` snapshots, thin, ~Aug), (b) a post-only
quoting + inventory-management engine (a build, a new strategy class), (c) a high fee tier (volume/capital
-gated). Competes with co-located MMs on majors → target **thinner pairs / wider spreads** where MM
competition is sparse. Longer-term, an infrastructure + capital bet — but it is the *only* continuous
intraday edge that exists.

### 3. Execution overlay — capture the maker premium on trades you ALREADY make (free-ish, now)
Not a new strategy: switch the **existing** daily-breakout / carry entries to **post-only limit** fills.
On a low-frequency, non-urgent signal you can afford to wait for the fill, and you capture a few bps of the
maker premium (rebate + spread) on trades you were doing anyway. Small, but free execution alpha, and it's
available on the current stack today (needs the maker-fee path wired — currently dead code in the backtest).

## The meta-insight

Intraday profitability is a **scale + structure** game, not a signal game. The levers are **fee-tier /
rebates / capital** and being the **liquidity provider** or the **forced-flow counterparty** — not
out-predicting the market tick-by-tick. This stack cannot win on speed or size, so the winning intraday
plays are the ones where **the move is big enough that costs and latency don't matter (liquidations/events)**,
or where **you earn the premium instead of paying it (market-making)**. Everything in between — continuous
directional scalping — is structurally closed, and no amount of signal search reopens it.

## Recommendation / sequencing

1. **Near-term (data-gated ~Aug):** design + test the **liquidation-reaction** strategy. It's the one
   intraday edge that beats costs because the dislocations are huge. Scope the exact trigger/exit/sizing now
   so it's ready to run the moment `LIQ_FADE` hits n≥100. (Also unblocks with the operator pushing
   `feat/liq-fade-features`.)
2. **Free now:** wire maker post-only entries into the existing daily/carry book — execution alpha on trades
   already happening. (Requires activating the dead maker-fee path.)
3. **Longer-term / capital decision:** market-making (L2 data + quoting engine + fee-tier climb) — the real
   HFT edge, but an infrastructure commitment that only pays at scale.
4. **Do NOT pursue:** continuous directional scalping (dead), latency/cross-venue arb (lose the race).

## Capital caveat (applies to all of the above)
Every intraday approach is scale-sensitive: tiny edges × volume × rebates. At ~$191 / VIP0 the economics are
symbolic. Intraday is a business that needs capital and volume to matter — which is itself the argument for
prioritizing the LOW-frequency, capital-efficient edges (daily breakout, carry) until scale exists, and
treating intraday as a *future* build gated on data (~Aug) + capital, not a near-term profit lever.
