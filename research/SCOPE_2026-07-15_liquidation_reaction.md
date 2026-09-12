# Liquidation-Reaction Strategy — Detailed Design Scope (2026-07-15)

## Thesis (why this is the best intraday door for THIS stack)
Forced liquidations are **price-insensitive flow**: a liquidation engine must market-sell (long liqs) or
market-buy (short liqs) regardless of price. In a cascade, forced selling gaps price down → trips more
liquidations → the move **overshoots fair value** → then **snaps back** as the forced flow exhausts and
opportunistic liquidity steps in. The edge is to **FADE the overshoot**. It fits this stack because:
- **The dislocation is LARGE** (1–5%+ in minutes) → dwarfs the ~15bps taker cost floor that killed every
  scalp. Cost is a non-issue.
- **No co-location needed** — a cascade + reversion plays out over minutes-to-an-hour, not microseconds.
  Systematic bar-triggered entry is fine; you don't need to be *first*, just *disciplined*.
- **It IS liquidity provision in its fat form** — the same premium the order-flow test found (reversion
  after aggression), but where the aggressor is a *forced* seller so the overshoot is huge and capturable.

## Signal design

### Trigger — a liquidation SPIKE (directional)
- **Intensity:** `liq_usd_rate_zscore_24h` > Z (start Z≈3) — an abnormal burst of forced liquidation USD/sec.
- **Direction:** LONG-liquidation spike (longs stopped, price crashing) → **fade UP (buy)**; SHORT-liquidation
  spike (shorts squeezed, price spiking) → **fade DOWN (short)**. Need long-vs-short split — the Binance
  forceOrder stream carries side; confirm the `liq_*` features expose it, else infer from the concurrent
  price move (crash + liq spike ⇒ long liqs ⇒ fade up).
- **Confirmation = EXHAUSTION, not the peak:** do NOT enter mid-cascade (falling-knife). Wait for the liq
  rate to roll over — `liq_usd_rate_accel_1h` turning negative, or the z-score coming off its peak. Entering
  on exhaustion is the difference between fading and getting run over.

### Entry
- After a confirmed spike + exhaustion, enter the fade. Optionally 2-leg scale-in (cascades can overshoot
  further) with a capped total risk.

### Exit
- **Target:** reversion toward pre-cascade price / VWAP / a fixed % bounce (the overshoot typically retraces
  a large fraction fast). Level-defined if possible.
- **Time-stop:** liquidation overshoots revert quickly — exit if no reversion within T (e.g. 4–24 bars of the
  trigger interval). A stale fade that hasn't reverted = the move was real, not an overshoot.
- **Hard stop:** if price CONTINUES beyond a threshold past entry, cut — you're fading, so the stop is wider,
  but a genuine breakdown (real de-risking, not a liquidation wick) must be cut fast. This stop is what caps
  the black-swan tail (see risks).

### Sizing / risk
- **High-conviction but high-variance** (fading a crash). Small fixed risk per event; **vol-targeted**
  (positions sized DOWN when vol is extreme — which it is during a cascade; the dormant vol-target overlay is
  the right home). Kelly-fraction or fixed-fractional. Rare events ⇒ each trade is a real bet, not a grind.
- Only fade **EXTREME** liquidations (biggest cascades overshoot most / most reliably). Small liqs don't
  overshoot enough to matter.

## Data — the binding constraint (this is a TIME-gated strategy)
- **Source:** Binance forceOrder stream, live since **2026-06-12**; `liq_*` features since **2026-06-24**.
  Features built on branch `feat/liq-fade-features` (V201, `raw_aggregation` engine mode, NOT pushed):
  `liq_usd_rate_zscore_24h_<sym>`, `liq_event_count_4h_<sym>`, `liq_usd_rate_accel_1h_<sym>` for core-5.
- **★NOT BACKFILLABLE** — the lifespan worker is the ONLY source; there is no liquidation history before
  2026-06. So the strategy can only ever be validated on **forward-accrued** data.
- **Maturity:** cascade *events* are rare (need big-vol days). n≥100 distinct cascades ≈ **~Aug/Sept**, sooner
  if a high-volatility stretch hits. Until then it CANNOT reach the n≥100 gate — this is the hard blocker.

## Backtest honesty requirements
- **Causal features only** — `liq_*` computed from liquidations ≤ t; exhaustion confirmation uses only past.
- **★ELEVATED SLIPPAGE during cascades** — fading a cascade means trading into a chaotic, wide-spread book.
  The backtest MUST model cascade-time slippage (NOT the calm-market ~8bps) — realistically 20–50bps+ on the
  entry. This is the single most likely edge-killer and must be stress-tested (the edge is big, but so is the
  slippage). Model fills at a haircut to the trigger-bar close, not the mid.
- **Purged WF + regime split** once n allows; the effect should hold across independent cascades.

## Interim validation we CAN do now (before the real data matures)
A **price-proxy pre-test** over full history: proxy a "liquidation cascade" as a large, fast down-move with a
volume spike (big negative return over k bars + volume z-score high), then test "fade the crash" (buy after,
exit on reversion/time/stop), cost-netted with ELEVATED slippage. This is a rough read on whether the
reversion-after-forced-crash mechanism has a tradeable edge AT ALL, and how big — before committing to the
real `liq_*` build. Caveat: price alone doesn't isolate *forced* flow (a fast drop could be news), so a
positive proxy is necessary-not-sufficient; the real `liq_*` signature is what confirms it ~Aug.

## Build requirements (when validated)
1. Push `feat/liq-fade-features` (the `liq_*` features + `raw_aggregation` engine mode) — operator-gated.
2. A **liquidation-reaction engine** (partly scaffolded by the raw_aggregation mode) reading `liq_*` +
   price/vol, implementing the trigger→exhaustion→fade→exit logic + the cascade-slippage cost model.
3. Wire vol-targeted sizing (the dormant overlay) — critical for a high-variance fade sleeve.
4. Seed research `account_strategy` rows; certify via the normal gauntlet (V11+V60, WF, DSR) once n≥100.

## Risks (be explicit)
- **Black-swan tail** — fading a genuine collapse (exchange failure, de-peg, real regime break) where the
  "liquidations" are the START of a crash, not an overshoot. The hard stop is the only defense; size for the
  tail (small). This is the strategy's dominant risk and why sizing discipline > signal cleverness here.
- **Slippage** — as above, the most likely quiet edge-killer.
- **Data timeline** — cannot certify before ~Aug/Sept; it's a *future* build, not a near-term profit lever.
- **Capital** — like all intraday, scale-sensitive; at ~$191 it's symbolic until capital grows.

## Verdict / sequencing

### ★★UPDATE 2026-07-15 — PRICE-PROXY PRE-TEST = NO-GO (do NOT build on the fade mechanism)
The pre-test (`.rtmp/liq_fade_proxy.py`, 240 cfgs × slippage ladder, 8 coins 2021-06→2026-07, ~400-1376
proxy-cascade events — NOT a power problem) FALSIFIED the fade edge:
- **Dies at realistic slippage:** PF>1 in 21/240 cfgs @15bps → 8/240 @30bps → **0/240 @50bps** (max PF 0.975
  even best-selected). Fading a real cascade fills at ≥50bps (worse book), where the edge is already gone.
- **Regime-dependent = bull dip-buying, not forced-flow alpha:** the residual low-slippage edge lives in
  2021 + 2025/26 (PF 1.4-2.1); **2022 bear @30bps PF 0.999 (break-even), 2024 a loser (0.77-0.86).** Crash-fade
  does NOT work when the trend is down — it's "buy the dip in a bull," which inverts in a bear.
- **Crash→fade-long carries all signal; squeeze→fade-short loses** — confirms it's dip-buying, not symmetric
  forced-flow reversion. Exhaustion filter helps only marginally (median PF@30 0.76→0.81, still <1).
- ★The proxy is OPTIMISTICALLY biased (fs_prices has NO volume → fires on any fast move, not just
  forced-flow) → a NULL here is *more* damning. For the real liq_* signal to be worth it, true forced-flow
  overshoots would have to be CATEGORICALLY larger/cleaner than z-scored price moves — no evidence they are.

**REVISED VERDICT: do NOT push the `liq_*` branch or wait until Aug on the fade mechanism.** The mechanism as
designed (fade the overshoot) does not survive the fills you'd actually get, and its apparent edge is
regime-dependent dip-buying that fails in bear markets — the same trap as ATR_MOM. This was my top intraday
pick; the pre-test corrected it. The ONLY non-falsified intraday door left is pure **market-making** (earn
spread+rebate via L2 queue management) — the big infrastructure/capital build, not a signal.
